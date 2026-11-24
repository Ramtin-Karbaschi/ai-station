#!/usr/bin/env python3
"""Local voice status and a single spoken-input diagnostic turn."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

import tts_smoke

LLM_URL = "http://127.0.0.1:4000/v1"
ASR_URL = f"{LLM_URL}/audio/transcriptions"
TTS_URL = f"{LLM_URL}/audio/speech"
ASR_HEALTH = "http://127.0.0.1:8092/v1/models"
LLM_HEALTH = "http://127.0.0.1:4000/health/liveliness"
DEFAULT_MODEL = "Qwen3.8-27B-UD-Q4_K_M"
CompleteFn = Callable[[str], str]
TranscribeFn = Callable[[bytes], str]


class VoiceError(RuntimeError):
    """Voice pipeline failed."""


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def _probe(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 500
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def load_api_key() -> str:
    for key in ("AI_STATION_VOICE_API_KEY", "LLM_API_KEY"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    env_file = _load_env_file(project_root() / "projects" / "opencode.env")
    value = (env_file.get("LLM_API_KEY") or "").strip()
    if value:
        return value
    raise VoiceError(
        "no project API key; set AI_STATION_VOICE_API_KEY or create a LiteLLM project"
    )


def status(*, probe: bool = True) -> dict[str, Any]:
    asr_up = _probe(ASR_HEALTH) if probe else False
    llm_up = _probe(LLM_HEALTH) if probe else False
    tts_up = False
    if probe:
        try:
            result = subprocess.run(
                [str(project_root() / "scripts/compose-ai-station.sh"), "--profile", "voice",
                 "exec", "-T", "station-voice", "python", "-c",
                 "import json, urllib.request; "
                 "assert json.load(urllib.request.urlopen('http://127.0.0.1:8095/health', timeout=2))['ready']"],
                capture_output=True, timeout=5, check=False,
            )
            tts_up = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "asr": {
            "url": ASR_URL,
            "health": ASR_HEALTH,
            "available": asr_up,
            "engine": "qwen3-asr-1.7b with faster-whisper fallback",
        },
        "llm": {
            "url": f"{LLM_URL}/chat/completions",
            "health": LLM_HEALTH,
            "available": llm_up,
            "model": DEFAULT_MODEL,
        },
        "tts": {
            "url": TTS_URL,
            "status": "ready" if tts_up else "unavailable" if probe else "not_probed",
            "available": tts_up,
            "model": "ai-station-speech",
            "engine": "Piper CPU",
            "client": "Open WebUI Voice Mode",
        },
        "loopback_only": True,
    }


def turn_plan(transcript: str | None = None) -> dict[str, Any]:
    text = (transcript or "<asr-text>").strip() or "<asr-text>"
    return {
        "dry_run": True,
        "stages": [
            {
                "name": "asr",
                "method": "POST",
                "url": ASR_URL,
                "body": "audio bytes (wav/mp3); not logged",
            },
            {
                "name": "llm",
                "method": "POST",
                "url": f"{LLM_URL}/chat/completions",
                "model": DEFAULT_MODEL,
                "max_tokens": 256,
                "user": text if text != "<asr-text>" else "<asr-text>",
            },
            {
                "name": "tts",
                "method": "POST",
                "url": TTS_URL,
                "status": "skipped",
                "skipped": True,
            },
        ],
        "live_turn_without_tts": "returns LLM text only",
        "cloud": False,
    }


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        exc.read()
        raise VoiceError(f"LiteLLM HTTP {exc.code}") from None
    except (OSError, urllib.error.URLError) as exc:
        raise VoiceError("LiteLLM is not reachable at http://127.0.0.1:4000/v1") from exc
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise VoiceError("LiteLLM returned non-JSON") from exc
    if not isinstance(parsed, dict):
        raise VoiceError("LiteLLM returned a non-object")
    return parsed


def complete_chat(
    text: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    post: Callable[..., dict[str, Any]] = post_json,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "max_tokens": 256,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = post(f"{LLM_URL}/chat/completions", payload, headers)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceError("LiteLLM response missing choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise VoiceError("LiteLLM returned empty content")
    return content.strip()


def transcribe_audio(audio: bytes) -> str:
    if not audio:
        raise VoiceError("audio file is empty")
    boundary = "----ai-station-voice-" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="model"\r\n\r\n'
        "ai-station-asr\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + audio + f"\r\n--{boundary}--\r\n".encode("ascii")
    req = urllib.request.Request(
        ASR_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        exc.read()
        raise VoiceError(f"ASR HTTP {exc.code}") from None
    except (OSError, urllib.error.URLError) as exc:
        raise VoiceError("LiteLLM ASR is not reachable at http://127.0.0.1:4000/v1") from exc
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise VoiceError("ASR returned non-JSON") from exc
    text = parsed.get("text") if isinstance(parsed, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise VoiceError("ASR returned empty text")
    return text.strip()


def live_turn(
    *,
    transcript: str | None = None,
    audio_path: Path | None = None,
    complete_fn: CompleteFn | None = None,
    transcribe_fn: TranscribeFn | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    if audio_path is not None:
        raw = audio_path.read_bytes()
        text = (transcribe_fn or transcribe_audio)(raw)
    elif transcript and transcript.strip():
        text = transcript.strip()
    else:
        raise VoiceError("pass --transcript TEXT or --file AUDIO")
    if complete_fn is not None:
        reply = complete_fn(text)
    else:
        reply = complete_chat(text, api_key=api_key or load_api_key())
    return {
        "dry_run": False,
        "transcript": text,
        "reply": reply,
        "tts": {
            "skipped": True,
            "status": "skipped",
            "url": TTS_URL,
        },
        "cloud": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Voice MVP: ASR and LiteLLM live; TTS pending smoke."
    )
    sub = parser.add_subparsers(dest="command")
    status_cmd = sub.add_parser("status")
    status_cmd.add_argument("--no-probe", action="store_true")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--dry-run", action="store_true")
    smoke.add_argument("--write", default="")
    turn = sub.add_parser("turn")
    turn.add_argument("--dry-run", action="store_true")
    turn.add_argument("--transcript", default="")
    turn.add_argument("--file", default="")
    args = parser.parse_args(argv)
    command = args.command or "status"
    if command == "status":
        no_probe = bool(getattr(args, "no_probe", False))
        print(json.dumps(status(probe=not no_probe), indent=2))
        return 0
    if command == "smoke":
        data_root = Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station"))
        report = tts_smoke.smoke_report(
            project_root=project_root(),
            data_root=data_root,
            hash_files=not args.dry_run,
        )
        write = (args.write or "").strip()
        if write:
            tts_smoke.write_report(report, Path(write))
        print(json.dumps(report, indent=2))
        if report.get("dry_run"):
            return 0
        return 0 if report.get("weights_verified") else 2
    if command == "turn":
        if args.dry_run:
            print(json.dumps(turn_plan(args.transcript or None), indent=2))
            return 0
        try:
            audio = Path(args.file) if args.file else None
            if audio is not None and not audio.is_file():
                raise VoiceError(f"audio file not found: {audio}")
            result = live_turn(transcript=args.transcript or None, audio_path=audio)
        except VoiceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0
    print(
        "Usage: ai voice status|smoke|turn [--dry-run] [--transcript TEXT]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
