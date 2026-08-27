"""Unified speech-to-text: Qwen3-ASR-1.7B primary, faster-whisper-large-v3 fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Transcript:
    text: str
    engine: str
    language: str | None
    timestamps: list[dict] | None
    fallback_used: bool
    reason: str


TranscribeFn = Callable[[bytes, str | None], Transcript]


def transcribe(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    want_timestamps: bool = False,
    qwen_available: bool = False,
    qwen_fn: TranscribeFn | None = None,
    whisper_fn: TranscribeFn | None = None,
) -> Transcript:
    use_whisper = want_timestamps or not qwen_available
    if not use_whisper and qwen_fn is not None:
        try:
            result = qwen_fn(audio_bytes, language)
            return Transcript(
                text=result.text,
                engine="qwen3-asr-1.7b",
                language=result.language or language,
                timestamps=None,
                fallback_used=False,
                reason="normal transcription",
            )
        except Exception as exc:
            if whisper_fn is None:
                raise
            fallback = whisper_fn(audio_bytes, language)
            return Transcript(
                text=fallback.text,
                engine="faster-whisper-large-v3",
                language=fallback.language or language,
                timestamps=fallback.timestamps,
                fallback_used=True,
                reason=f"Qwen3-ASR failed: {type(exc).__name__}",
            )
    if whisper_fn is None:
        raise RuntimeError("Whisper fallback selected but no engine function was provided")
    fallback = whisper_fn(audio_bytes, language)
    return Transcript(
        text=fallback.text,
        engine="faster-whisper-large-v3",
        language=fallback.language or language,
        timestamps=fallback.timestamps,
        fallback_used=True,
        reason="timestamp / compatibility path" if want_timestamps else "Qwen3-ASR unavailable",
    )


def qwen_asr_url() -> str:
    return os.getenv("AI_STATION_ASR_URL", "http://127.0.0.1:8092").rstrip("/")


def qwen_asr_available() -> bool:
    url = qwen_asr_url() + "/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def _qwen_transcribe(audio_bytes: bytes, language: str | None) -> Transcript:
    boundary = "----ai-station-asr"
    filename = "audio.wav"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body += audio_bytes + f"\r\n--{boundary}\r\n".encode("utf-8")
    if language:
        body += (
            'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{language}\r\n"
        ).encode("utf-8")
    body += f"--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        qwen_asr_url() + "/v1/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return Transcript(
        text=str(payload.get("text") or "").strip(),
        engine="qwen3-asr-1.7b",
        language=payload.get("language") or language,
        timestamps=None,
        fallback_used=False,
        reason="normal transcription",
    )


def _whisper_transcribe(audio_bytes: bytes, language: str | None) -> Transcript:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ai-station-open-webui-1",
            "python",
            "-c",
            (
                "import sys, json\n"
                "from faster_whisper import WhisperModel\n"
                "audio = sys.stdin.buffer.read()\n"
                "open('/tmp/ai-station-stt.bin', 'wb').write(audio)\n"
                "model = WhisperModel('/app/backend/data/cache/whisper/models/faster-whisper-large-v3', device='cpu')\n"
                "lang = sys.argv[1] if sys.argv[1] != '-' else None\n"
                "segments, info = model.transcribe('/tmp/ai-station-stt.bin', language=lang)\n"
                "rows = [{'start': s.start, 'end': s.end, 'text': s.text} for s in segments]\n"
                "print(json.dumps({'text': ''.join(r['text'] for r in rows).strip(), "
                "'language': getattr(info, 'language', lang), 'segments': rows}))\n"
            ),
            language or "-",
        ],
        input=audio_bytes,
        check=True,
        capture_output=True,
        timeout=300,
    )
    payload = json.loads(result.stdout.decode("utf-8"))
    return Transcript(
        text=str(payload.get("text") or "").strip(),
        engine="faster-whisper-large-v3",
        language=payload.get("language") or language,
        timestamps=payload.get("segments"),
        fallback_used=True,
        reason="whisper fallback",
    )


def transcribe_station_audio(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    want_timestamps: bool = False,
) -> Transcript:
    return transcribe(
        audio_bytes,
        language=language,
        want_timestamps=want_timestamps,
        qwen_available=qwen_asr_available(),
        qwen_fn=_qwen_transcribe,
        whisper_fn=_whisper_transcribe,
    )
