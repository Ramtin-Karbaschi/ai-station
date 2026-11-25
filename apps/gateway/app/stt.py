"""Unified speech-to-text: Qwen3-ASR-1.7B primary, faster-whisper-large-v3 fallback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_default
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

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$", re.IGNORECASE)
_QWEN_TEXT_PREFIX_RE = re.compile(r"^\s*language\s+[^<]+<asr_text>\s*", re.IGNORECASE)
CALL_ASR_UPSTREAM_MODEL = "whisper-call-1"


def normalize_language(language: str | None) -> str | None:
    """Return a safe Whisper/Qwen language hint, or ``None`` for autodetect.

    OpenAI clients commonly send ``auto`` or locale forms such as ``fa-IR``.
    The local engines need the ISO-639 language portion, so locale suffixes are
    intentionally discarded.  Rejecting malformed hints also keeps them out
    of the subprocess argv used by the Whisper fallback.
    """

    value = str(language or "").strip().replace("_", "-")
    if not value or value.lower() in {"auto", "automatic", "detect"}:
        return None
    if not _LANGUAGE_RE.fullmatch(value):
        raise ValueError("language must be an ISO-639 code such as 'fa' or 'en'")
    return value.split("-", 1)[0].lower()


def clean_qwen_text(text: str) -> str:
    """Remove the local Qwen server's metadata wrapper from transcript text."""

    return _QWEN_TEXT_PREFIX_RE.sub("", str(text or "")).strip()


def extract_audio_request(
    body: bytes,
    *,
    content_type: str | None = None,
    language: str | None = None,
) -> tuple[bytes, str | None, str | None]:
    """Extract audio, language and model from raw or OpenAI multipart data.

    The host gateway historically accepted raw audio bytes.  OpenAI-compatible
    clients send ``multipart/form-data`` with a ``file`` field, so keep raw
    compatibility while accepting either ``file`` or ``audio`` and optional
    language/model fields. The model is the upstream provider model selected
    by LiteLLM; only the dedicated ``whisper-call-1`` marker changes this
    router's strategy. Audio extraction remains byte-preserving.
    """

    if not body:
        raise ValueError("audio body is empty")
    resolved_language = normalize_language(language)
    resolved_model: str | None = None
    content_type = (content_type or "").strip()
    if not content_type.lower().startswith("multipart/"):
        return body, resolved_language, resolved_model

    envelope = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
    message = BytesParser(policy=email_default).parsebytes(envelope)
    audio: bytes | None = None
    form_language: str | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name in {"file", "audio"} and audio is None:
            audio = part.get_payload(decode=True) or b""
        elif name == "language" and form_language is None:
            raw = part.get_payload(decode=True) or b""
            form_language = raw.decode("utf-8", errors="replace").strip()
        elif name == "model" and resolved_model is None:
            raw = part.get_payload(decode=True) or b""
            resolved_model = raw.decode("utf-8", errors="replace").strip() or None
    if audio is None or not audio:
        raise ValueError("multipart request must include a non-empty file field")
    if resolved_language is None and form_language:
        resolved_language = normalize_language(form_language)
    return audio, resolved_language, resolved_model


def transcribe(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    want_timestamps: bool = False,
    whisper_primary: bool = False,
    qwen_available: bool = False,
    qwen_fn: TranscribeFn | None = None,
    whisper_fn: TranscribeFn | None = None,
) -> Transcript:
    language = normalize_language(language)
    if not audio_bytes:
        raise ValueError("audio body is empty")
    if whisper_primary:
        if whisper_fn is None:
            raise RuntimeError(
                "Whisper-primary transcription selected but no engine function was provided"
            )
        try:
            whisper = whisper_fn(audio_bytes, language)
        except Exception as exc:
            if not qwen_available or qwen_fn is None:
                raise
            fallback = qwen_fn(audio_bytes, language)
            return Transcript(
                text=fallback.text,
                engine="qwen3-asr-1.7b",
                language=fallback.language or language,
                timestamps=None,
                fallback_used=True,
                reason=f"Whisper failed: {type(exc).__name__}",
            )
        return Transcript(
            text=whisper.text,
            engine="faster-whisper-large-v3",
            language=whisper.language or language,
            timestamps=whisper.timestamps,
            fallback_used=False,
            reason="call transcription",
        )

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
    whisper = whisper_fn(audio_bytes, language)
    return Transcript(
        text=whisper.text,
        engine="faster-whisper-large-v3",
        language=whisper.language or language,
        timestamps=whisper.timestamps,
        fallback_used=False,
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


ASR_MULTIPART_BOUNDARY = "----ai-station-asr"


def _asr_multipart_body(
    audio_bytes: bytes,
    language: str | None,
    *,
    boundary: str = ASR_MULTIPART_BOUNDARY,
    filename: str = "audio.wav",
) -> bytes:
    dash_boundary = f"--{boundary}".encode("utf-8")
    crlf = b"\r\n"
    body = bytearray()
    body += dash_boundary
    body += crlf
    body += (
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n"
    ).encode("utf-8")
    body += crlf
    body += audio_bytes
    if language:
        body += crlf
        body += dash_boundary
        body += crlf
        body += b'Content-Disposition: form-data; name="language"\r\n'
        body += crlf
        body += language.encode("utf-8")
    body += crlf
    body += dash_boundary
    body += b"--"
    body += crlf
    return bytes(body)


def _qwen_transcribe(audio_bytes: bytes, language: str | None) -> Transcript:
    language = normalize_language(language)
    boundary = ASR_MULTIPART_BOUNDARY
    body = _asr_multipart_body(audio_bytes, language, boundary=boundary)
    req = urllib.request.Request(
        qwen_asr_url() + "/v1/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    text = clean_qwen_text(payload.get("text") or "")
    if not text:
        raise RuntimeError("Qwen3-ASR returned an empty transcript")
    return Transcript(
        text=text,
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
                "import io, sys, json\n"
                "from faster_whisper import WhisperModel\n"
                "audio = sys.stdin.buffer.read()\n"
                "model = WhisperModel('/app/backend/data/cache/whisper/models/faster-whisper-large-v3', "
                "device='cpu', compute_type='int8', local_files_only=True, cpu_threads=3)\n"
                "lang = sys.argv[1] if sys.argv[1] != '-' else None\n"
                "segments, info = model.transcribe(io.BytesIO(audio), language=lang, vad_filter=True)\n"
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
        fallback_used=False,
        reason="whisper transcription",
    )


def transcribe_station_audio(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    want_timestamps: bool = False,
    whisper_primary: bool = False,
) -> Transcript:
    language = normalize_language(language)
    if not audio_bytes:
        raise ValueError("audio body is empty")
    return transcribe(
        audio_bytes,
        language=language,
        want_timestamps=want_timestamps,
        whisper_primary=whisper_primary,
        qwen_available=qwen_asr_available(),
        qwen_fn=_qwen_transcribe,
        whisper_fn=_whisper_transcribe,
    )
