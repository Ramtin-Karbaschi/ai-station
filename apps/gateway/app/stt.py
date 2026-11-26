"""Unified speech-to-text: Qwen3-ASR-1.7B primary, faster-whisper-large-v3 fallback.
"""

from __future__ import annotations

import json
import io
import logging
import os
import re
import subprocess
import struct
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_default
from typing import Callable


logger = logging.getLogger(__name__)


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
_MAX_SEGMENTS = 3
_MIN_SEGMENT_SECONDS = 0.45
_MIN_SILENCE_SECONDS = 0.55
_SILENCE_WINDOW_SECONDS = 0.02
_SEGMENT_PAD_SECONDS = 0.0
_SEGMENT_DEADLINE_SECONDS = 40.0
_MAX_SEGMENTABLE_SECONDS = 40.0
_PERSIAN_WHISPER_DEADLINE_SECONDS = 45.0
_SILENCE_PEAK_THRESHOLD = 64
_SILENCE_RMS_THRESHOLD = 16.0


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


def _decode_pcm16(audio_bytes: bytes) -> tuple[bytes, int] | None:
    """Decode common audio to mono 16-bit PCM for conservative silence splits."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                return None
            if not source.getframerate() or source.getnframes() / source.getframerate() > _MAX_SEGMENTABLE_SECONDS:
                return None
            return source.readframes(source.getnframes()), source.getframerate()
    except (EOFError, wave.Error):
        pass
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-t", str(_MAX_SEGMENTABLE_SECONDS + 1), "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
            input=audio_bytes,
            capture_output=True,
            check=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if len(result.stdout) > int(_MAX_SEGMENTABLE_SECONDS * 16000 * 2):
        return None
    return result.stdout, 16000


def _silence_metadata(decoded: tuple[bytes, int] | None) -> tuple[int | None, bool]:
    """Return bounded duration/silence metadata without retaining audio text."""
    if decoded is None:
        return None, False
    pcm, rate = decoded
    if not pcm or rate <= 0:
        return 0, True
    samples = struct.unpack("<%dh" % (len(pcm) // 2), pcm)
    peak = max((abs(value) for value in samples), default=0)
    mean_square = sum(value * value for value in samples) / max(1, len(samples))
    rms = mean_square ** 0.5
    duration_ms = int(len(samples) * 1000 / rate)
    return duration_ms, peak <= _SILENCE_PEAK_THRESHOLD and rms <= _SILENCE_RMS_THRESHOLD


def _split_audio_on_pause(
    audio_bytes: bytes, *, decoded: tuple[bytes, int] | None = None
) -> list[bytes] | None:
    """Return bounded WAV segments, or None when the input is not safely split."""
    decoded = decoded if decoded is not None else _decode_pcm16(audio_bytes)
    if decoded is None:
        return None
    pcm, rate = decoded
    frame_bytes = 2
    window = max(1, int(rate * _SILENCE_WINDOW_SECONDS))
    samples = struct.unpack("<%dh" % (len(pcm) // frame_bytes), pcm)
    if len(samples) < int(rate * _MIN_SEGMENT_SECONDS * 2):
        return None
    energies = [
        sum(abs(value) for value in samples[start : start + window]) / max(1, len(samples[start : start + window]))
        for start in range(0, len(samples), window)
    ]
    peak = max(energies, default=0.0)
    threshold = max(180.0, peak * 0.035)
    silence_windows = max(1, int(_MIN_SILENCE_SECONDS / _SILENCE_WINDOW_SECONDS))
    cuts: list[tuple[int, int]] = []
    run_start: int | None = None
    for index, energy in enumerate(energies + [peak]):
        if energy <= threshold and run_start is None:
            run_start = index
        elif energy > threshold and run_start is not None:
            if index - run_start >= silence_windows:
                cuts.append((run_start * window, index * window))
            run_start = None
    if not cuts:
        return None
    total = len(samples)
    # Prefer the longest reliable pauses.  Taking the first pauses biases a
    # natural mixed-language recording toward early intra-sentence gaps and
    # leaves the language boundary in one oversized segment.  Keep the same
    # bounded segment count, reject cuts that would create short segments, and
    # use the midpoint as a deterministic tie-breaker.
    minimum = int(rate * _MIN_SEGMENT_SECONDS)
    selected: list[int] = []
    ranked = sorted(cuts, key=lambda cut: (-(cut[1] - cut[0]), (cut[0] + cut[1]) // 2))
    for start, end in ranked:
        midpoint = (start + end) // 2
        if midpoint < minimum or total - midpoint < minimum:
            continue
        if any(abs(midpoint - chosen) < minimum for chosen in selected):
            continue
        selected.append(midpoint)
        if len(selected) >= _MAX_SEGMENTS - 1:
            break
    boundaries = [0, *sorted(selected)]
    if len(boundaries) == 1:
        return None
    boundaries.append(total)
    segments: list[bytes] = []
    for start, end in zip(boundaries, boundaries[1:]):
        pad = int(rate * _SEGMENT_PAD_SECONDS)
        start = max(0, start - pad)
        end = min(total, end + pad)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(struct.pack("<%dh" % (end - start), *samples[start:end]))
        segments.append(buffer.getvalue())
    return segments


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
            if not whisper.text.strip():
                raise RuntimeError("Whisper returned an empty transcript")
        except Exception as exc:
            if not qwen_available or qwen_fn is None:
                raise
            fallback = qwen_fn(audio_bytes, language)
            if not fallback.text.strip():
                raise RuntimeError("Qwen3-ASR returned an empty transcript") from exc
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
            if not result.text.strip():
                raise RuntimeError("Qwen3-ASR returned an empty transcript")
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
    if not whisper.text.strip():
        raise RuntimeError("Whisper returned an empty transcript")
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


def _qwen_transcribe(
    audio_bytes: bytes, language: str | None, *, timeout: float = 180.0
) -> Transcript:
    language = normalize_language(language)
    boundary = ASR_MULTIPART_BOUNDARY
    body = _asr_multipart_body(audio_bytes, language, boundary=boundary)
    req = urllib.request.Request(
        qwen_asr_url() + "/v1/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
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


def _whisper_transcribe(
    audio_bytes: bytes, language: str | None, *, timeout: float = 300.0
) -> Transcript:
    # Keep the worker deadline inside the host-side deadline.  If the request
    # is cancelled or the outer docker exec times out, the in-container
    # timeout still terminates the model worker instead of leaving it resident.
    worker_timeout = max(1.0, timeout - 5.0)
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ai-station-open-webui-1",
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=5s",
            f"{worker_timeout:.3f}s",
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
        timeout=timeout,
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
    decoded = _decode_pcm16(audio_bytes)
    duration_ms, is_silent = _silence_metadata(decoded)
    route = (
        "whisper-call" if whisper_primary else
        "whisper-fa" if language == "fa" else
        "whisper-timestamps" if want_timestamps else
        "qwen-auto" if language is None else "qwen-explicit"
    )
    logger.info(
        "stt_audio_metadata language=%s route=%s duration_ms=%s silence=%s",
        language or "auto", route, duration_ms if duration_ms is not None else "unknown", is_silent,
    )
    if is_silent:
        return Transcript(
            text="", engine="silence-gate", language=language, timestamps=None,
            fallback_used=False, reason="no speech detected",
        )
    qwen_available = qwen_asr_available()
    # The browser's explicit Persian preference is a quality request.  Keep
    # Auto/English on the Qwen pause-splitting route, but use the validated
    # local Whisper model for Persian before falling back to Qwen.
    if language == "fa" and not whisper_primary:
        return transcribe(
            audio_bytes,
            language=language,
            want_timestamps=want_timestamps,
            whisper_primary=True,
            qwen_available=qwen_available,
            qwen_fn=_qwen_transcribe,
            whisper_fn=lambda data, lang: _whisper_transcribe(
                data, lang, timeout=_PERSIAN_WHISPER_DEADLINE_SECONDS
            ),
        )
    if language is None and not want_timestamps and not whisper_primary and qwen_available:
        segments = _split_audio_on_pause(audio_bytes, decoded=decoded)
        if segments and len(segments) > 1:
            started = time.monotonic()
            texts: list[str] = []
            try:
                for segment in segments:
                    if time.monotonic() - started >= _SEGMENT_DEADLINE_SECONDS:
                        raise TimeoutError("pause-segmented transcription deadline exceeded")
                    remaining = _SEGMENT_DEADLINE_SECONDS - (time.monotonic() - started)
                    if remaining <= 1.0:
                        raise TimeoutError("pause-segmented transcription deadline exceeded")
                    result = _qwen_transcribe(segment, None, timeout=remaining)
                    if not result.text.strip():
                        raise RuntimeError("pause segment returned empty transcript")
                    texts.append(result.text.strip())
                return Transcript(
                    text=" ".join(texts),
                    engine="qwen3-asr-1.7b",
                    language=None,
                    timestamps=None,
                    fallback_used=False,
                    reason="pause-segmented transcription",
                )
            except Exception as split_error:
                # A split must never lose audio. Retry the original intact clip
                # only within the shared budget for this segmented request.
                remaining = _SEGMENT_DEADLINE_SECONDS - (time.monotonic() - started)
                if remaining <= 1.0:
                    raise split_error
                try:
                    return _qwen_transcribe(audio_bytes, None, timeout=remaining)
                except Exception:
                    raise split_error
    return transcribe(
        audio_bytes,
        language=language,
        want_timestamps=want_timestamps,
        whisper_primary=whisper_primary,
        qwen_available=qwen_available,
        qwen_fn=_qwen_transcribe,
        whisper_fn=_whisper_transcribe,
    )
