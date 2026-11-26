"""Small, CPU-only OpenAI-compatible Piper speech service.

The service is intentionally independent from the application gateway.  LiteLLM
is the only application-facing API; this process is a loopback provider that
LiteLLM may route to.  Models are loaded lazily and never downloaded by this
module.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

MAX_TEXT_CHARS = int(os.getenv("AI_STATION_TTS_MAX_CHARS", "4000"))
MAX_BODY_BYTES = 64 * 1024
MAX_SCRIPT_RUNS = 64
SYNTHESIS_TIMEOUT_SECONDS = float(os.getenv("AI_STATION_TTS_TIMEOUT", "30"))
MAX_CONCURRENT = int(os.getenv("AI_STATION_TTS_MAX_CONCURRENT", "1"))
DEFAULT_FORMAT = "mp3"

# Stable aliases keep client configuration independent of model filenames.
VOICE_ALIASES = {
    "fa": ("fa", "AI_STATION_PIPER_FA_MODEL", "/models/fa.onnx"),
    "en": ("en", "AI_STATION_PIPER_EN_MODEL", "/models/en.onnx"),
}


class VoiceServiceError(RuntimeError):
    """An expected synthesis/configuration failure without sensitive details."""


def configured_model(alias: str) -> tuple[str, Path]:
    try:
        language, env_name, default = VOICE_ALIASES[alias]
    except KeyError as exc:
        raise VoiceServiceError("unsupported voice") from exc
    return language, Path(os.getenv(env_name, default)).expanduser()


def detect_language(text: str) -> str:
    """Return the turn language; Persian script wins when present."""
    return "fa" if _has_persian(text) else "en"


def _has_persian(text: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in text)


def _has_latin(text: str) -> bool:
    return any("a" <= char.lower() <= "z" for char in text)


def _script_alias(char: str) -> str | None:
    if "a" <= char.lower() <= "z":
        return "en"
    if "\u0600" <= char <= "\u06ff":
        return "fa"
    return None


def split_script_runs(text: str, default_alias: str) -> list[tuple[str, str]]:
    """Split mixed Persian/Latin text while keeping punctuation with its phrase."""
    runs: list[tuple[str, str]] = []
    pending = ""
    for char in text:
        alias = _script_alias(char)
        if alias is None:
            pending += char
            continue
        if runs and runs[-1][0] == alias:
            runs[-1] = (alias, runs[-1][1] + pending + char)
        else:
            if runs:
                runs[-1] = (runs[-1][0], runs[-1][1] + pending)
            runs.append((alias, char))
        pending = ""
    if runs:
        runs[-1] = (runs[-1][0], runs[-1][1] + pending)
    elif pending:
        runs.append((default_alias, pending))
    return [(alias, chunk) for alias, chunk in runs if chunk.strip()]


def _load_piper(model_path: Path) -> Any:
    try:
        from piper import PiperVoice  # type: ignore
    except ImportError as exc:
        raise VoiceServiceError("Piper dependency is not installed") from exc
    if not model_path.is_file() or not model_path.with_suffix(".onnx.json").is_file():
        raise VoiceServiceError("configured voice model is unavailable")
    try:
        # Explicitly CPU-only: this service must not compete with llama.cpp GPU work.
        return PiperVoice.load(model_path, use_cuda=False)
    except Exception as exc:  # provider errors must not leak paths/model details
        raise VoiceServiceError("voice model failed to load") from exc


def _wav_bytes(voice: Any, text: str, speed: float) -> bytes:
    try:
        from piper import SynthesisConfig  # type: ignore

        out = io.BytesIO()
        with wave.open(out, "wb") as wav_file:
            voice.synthesize_wav(
                text,
                wav_file,
                syn_config=SynthesisConfig(length_scale=1.0 / speed),
            )
        return out.getvalue()
    except VoiceServiceError:
        raise
    except Exception as exc:
        raise VoiceServiceError("speech synthesis failed") from exc


def _mp3_bytes(wav_data: bytes, timeout: float = SYNTHESIS_TIMEOUT_SECONDS) -> bytes:
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-f", "wav", "-i", "pipe:0", "-f", "mp3", "-codec:a", "libmp3lame",
                "-ar", "22050", "-ac", "1", "pipe:1",
            ],
            input=wav_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceServiceError("audio encoding timed out") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise VoiceServiceError("audio encoding failed") from exc
    if not proc.stdout.startswith(b"ID3") and not proc.stdout.startswith(b"\xff\xfb"):
        raise VoiceServiceError("audio encoder returned invalid MP3")
    return proc.stdout


class PiperBackend:
    def __init__(self, loader: Callable[[Path], Any] = _load_piper) -> None:
        self._loader = loader
        self._voices: dict[str, Any] = {}
        self._lock = threading.Lock()

    def synthesize(self, alias: str, text: str, speed: float) -> bytes:
        _, path = configured_model(alias)
        with self._lock:
            voice = self._voices.get(alias)
            if voice is None:
                voice = self._loader(path)
                self._voices[alias] = voice
            wav_data = _wav_bytes(voice, text, speed)
        return _mp3_bytes(wav_data)

    def synthesize_runs(self, runs: list[tuple[str, str]], speed: float) -> bytes:
        if len(runs) == 1:
            alias, text = runs[0]
            return self.synthesize(alias, text, speed)
        wav_parts: list[bytes] = []
        params: tuple[int, int, int] | None = None
        for alias, text in runs:
            _, path = configured_model(alias)
            with self._lock:
                voice = self._voices.get(alias)
                if voice is None:
                    voice = self._loader(path)
                    self._voices[alias] = voice
                wav_data = _wav_bytes(voice, text, speed)
            with wave.open(io.BytesIO(wav_data), "rb") as source:
                current = (source.getnchannels(), source.getsampwidth(), source.getframerate())
                if params is None:
                    params = current
                if current != params:
                    raise VoiceServiceError("voice outputs have incompatible audio formats")
                wav_parts.append(source.readframes(source.getnframes()))
        if params is None:
            raise VoiceServiceError("speech synthesis returned no audio")
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(params[0])
            target.setsampwidth(params[1])
            target.setframerate(params[2])
            target.writeframes(b"".join(wav_parts))
        return _mp3_bytes(output.getvalue())


app = FastAPI(title="AI Station Piper Voice", docs_url=None, redoc_url=None)
backend = PiperBackend()
slots = asyncio.Semaphore(max(1, MAX_CONCURRENT))


def _release_finished(task: asyncio.Task[Any]) -> None:
    # A timed-out thread may continue briefly; retain its slot until it really ends.
    try:
        task.result()
    except BaseException:
        pass
    slots.release()


async def _bounded_json(request: Request) -> dict[str, Any]:
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="request too large")
            chunks.append(chunk)
        payload = json.loads(b"".join(chunks))
    except HTTPException:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid JSON request") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request must be an object")
    return payload


@app.middleware("http")
async def body_limit(request: Request, call_next: Callable[..., Any]) -> Response:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return Response("request too large", status_code=413, media_type="text/plain")
        except ValueError:
            return Response("invalid content length", status_code=400, media_type="text/plain")
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, Any]:
    assets: dict[str, bool] = {}
    for alias in VOICE_ALIASES:
        _, path = configured_model(alias)
        assets[alias] = path.is_file() and path.with_suffix(".onnx.json").is_file()
    host = os.getenv("AI_STATION_TTS_HOST", "127.0.0.1")
    return {
        "ok": all(assets.values()),
        "ready": all(assets.values()),
        "assets": assets,
        "engine": "piper",
        "cpu_only": True,
        "loopback_only": host in {"127.0.0.1", "::1", "localhost"},
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": alias, "object": "model", "owned_by": "ai-station"} for alias in VOICE_ALIASES]}


@app.post("/v1/audio/speech")
async def speech(request: Request) -> Response:
    payload = await _bounded_json(request)
    text = payload.get("input")
    requested_voice = payload.get("voice", "auto")
    if not isinstance(requested_voice, str):
        raise HTTPException(status_code=400, detail="voice must be a string")
    alias = requested_voice
    response_format = payload.get("response_format", DEFAULT_FORMAT)
    model = payload.get("model", "piper")
    speed = payload.get("speed", 1.0)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=400, detail=f"input must be 1-{MAX_TEXT_CHARS} characters")
    if alias in {"auto", "alloy"}:
        alias = detect_language(text)
    if not isinstance(alias, str) or alias not in VOICE_ALIASES:
        raise HTTPException(status_code=400, detail="voice must be auto, fa, or en")
    if response_format != "mp3":
        raise HTTPException(status_code=400, detail="only mp3 response_format is supported")
    if not isinstance(model, str) or len(model) > 128 or model not in {"piper", "tts-1", alias}:
        raise HTTPException(status_code=400, detail="unsupported speech model")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.5 <= float(speed) <= 2.0:
        raise HTTPException(status_code=400, detail="speed must be between 0.5 and 2.0")
    try:
        language, _ = configured_model(alias)
        requested_language = payload.get("language")
        if requested_language is not None and (not isinstance(requested_language, str) or requested_language.lower()[:2] != language):
            raise HTTPException(status_code=400, detail="voice does not match requested language")
        contradictory = (
            requested_voice == "fa" and _has_latin(text) and not _has_persian(text)
        ) or (
            requested_voice == "en" and _has_persian(text) and not _has_latin(text)
        )
        if contradictory:
            raise HTTPException(status_code=400, detail="voice does not match input language")
        runs = (
            split_script_runs(text.strip(), alias)
            if requested_voice in {"auto", "alloy"}
            else [(alias, text.strip())]
        )
        if len(runs) > MAX_SCRIPT_RUNS:
            # Preserve the complete text and request budget for pathological alternation.
            runs = [(alias, text.strip())]
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.05)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=429, detail="voice service is busy") from None
        synthesize = backend.synthesize if len(runs) == 1 else backend.synthesize_runs
        synthesize_args = (
            (runs[0][0], runs[0][1], float(speed))
            if len(runs) == 1
            else (runs, float(speed))
        )
        task = asyncio.create_task(run_in_threadpool(synthesize, *synthesize_args))
        try:
            audio = await asyncio.wait_for(asyncio.shield(task), timeout=SYNTHESIS_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            task.add_done_callback(_release_finished)
            raise
        except BaseException:
            slots.release()
            raise
        else:
            slots.release()
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="speech synthesis timed out") from None
    except VoiceServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return Response(audio, media_type="audio/mpeg", headers={"Content-Disposition": "inline"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("AI_STATION_TTS_HOST", "127.0.0.1"),
        port=int(os.getenv("AI_STATION_TTS_PORT", "8095")),
        log_level="warning",
    )
