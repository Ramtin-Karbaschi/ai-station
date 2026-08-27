# ADR-027: Speech-to-text primary and fallback

- Status: Accepted
- Date: 2026-08-27

## Context

Open WebUI already runs faster-whisper-large-v3 offline. The operator
wants Qwen3-ASR-1.7B as the default transcriber, with Whisper kept for
timestamps and compatibility.

## Decision

One station API: `POST http://127.0.0.1:8888/v1/audio/transcriptions`.

Routing:

- normal transcription → Qwen3-ASR-1.7B (ggml-org Q8_0 + mmproj Q8_0)
- timestamps / Qwen unavailable / Qwen error → faster-whisper-large-v3

Qwen ASR is CPU-first so it can coexist with the heavy GPU chat model.
Whisper is an intentional fallback, not a superseded model.

## Consequences

Applications must not choose the engine. Persian and English are both in
scope. Qwen weights are provisioned from an immutable revision; runtime
must not download models.
