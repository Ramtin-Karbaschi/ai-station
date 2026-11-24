# ADR-037: Voice on Existing ASR, LLM, and TTS Services

- Status: Accepted
- Date: 2026-09-03

## Standard voice calls

Open WebUI uses its built-in call session for microphone capture, turn
detection, spoken playback, and microphone rearming. Both audio requests
go through LiteLLM. `ai-station-asr` accepts multipart audio and uses the
station's Qwen3-ASR and local Whisper fallback. `ai-station-speech` uses a
dedicated CPU Piper backend and returns MP3. The speech routes are outside
the chat model selector.

`ai voice setup` installs the hash-checked Ganji Persian and LJ Speech
English voices under the station model directory. The Piper container
mounts the assets read-only. Existing text chat and the operator's
single-turn CLI remain available independently of the call UI.

## 2026-11-22 amendment

Both Qwen3-TTS snapshots now have complete metadata and a verified nested
speech tokenizer on the tested station. `ai voice smoke` checks the model
weight hashes and snapshot structure separately from inference.

Qwen3-TTS CustomVoice returned a 24 kHz English WAV through a disposable
loopback speech endpoint using CPU only. The request took 15.7 seconds and
produced 4.16 seconds of speech. Persian is outside its supported languages.
The independent Piper Ganji Persian trial produced 4.34 seconds of audio in
1.23 seconds on CPU. Offline Whisper found four of five expected keywords.
The Persian trial measured intelligibility on one sentence. It does not
establish fluency across prompts and speakers. See the [voice smoke results](../../benchmarks/results/20261122/voice/isolated-cpu-smoke.json).

The installed production speech route remains gated. No second heavy GPU
process was required for either trial.

On 2026-11-23 the exact pinned LiteLLM 1.93.0 image routed an authenticated
Persian synthesis request through Piper in an isolated network namespace.
The result was HTTP 200, `audio/mpeg`, and a verified mono MP3 at 22,050 Hz.
The request took 0.75 seconds after startup. For OpenAI-compatible speech
providers this LiteLLM version labels the response `audio/mpeg`. Request MP3
when verifying a provider through it so the codec matches the header.

## 2026-09-04 amendment

`ai voice smoke` verifies pinned Qwen3-TTS SHA-256 weights on disk.
Inference is still not run: the on-disk snapshot is weights-only
(no `config.json`), and a second heavy GPU TTS engine beside chat
is forbidden. `POST /v1/audio/speech` stays HTTP 503.

## 2026-09-03 amendment

Live `ai voice turn --transcript` / `--file` returns LiteLLM text.
TTS is still not synthesized. The host gateway exposes
`POST /v1/audio/speech` as HTTP 503 `tts_pending_smoke` so clients
get a contract instead of a 404.

## Context

Voice calls integrate the existing speech-recognition, language-model, and
speech-synthesis services over loopback. The request path must preserve the
station's existing authentication and resource controls.

## Options considered

1. Start a new GPU TTS container as a second heavy provider.
2. Wait until TTS smoke promotes a production endpoint.
3. Ship `ai voice status|turn --dry-run` that chains ASR -> LiteLLM
   -> TTS, using live ASR and LLM when present, and reporting TTS
   as `pending_smoke` until a loopback speech route exists.

## Evidence

- Host gateway already transcribes.
- TTS packs are `configured_pending_smoke` / local-personal use.
- One-heavy-GPU policy forbids a surprise TTS engine beside chat.

## Decision

Adopt option 3. Do not add a TTS Compose service in this item.
Clients still call LiteLLM for text; voice is an operator CLI
pipeline, not a new public port.

## Consequences

- `ai voice turn --dry-run` never sends audio to a cloud STT/TTS.
- Live turn without TTS returns the LLM text (`--transcript` or
  `--file` through ASR).
- `POST http://127.0.0.1:8888/v1/audio/speech` remains HTTP 503 on
  the default production configuration. The isolated smoke exercises
  synthesis and LiteLLM routing without enabling that endpoint on the station.

## Risks

- Users expect synthesized speech today. Mitigation: the host
  gateway answers `POST /v1/audio/speech` with HTTP 503
  `tts_pending_smoke` instead of 404. LiteLLM `:4000` is not a
  TTS backend.

## Rollback

Remove the CLI. ASR and LiteLLM stay.

## Acceptance criteria

- Status reports ASR, LLM, and TTS availability without starting
  GPU work.
- Dry-run turn shows the three stages and loopback-only URLs.
- Live `--transcript` returns LLM text without calling TTS.
- Tests do not require a live TTS server.
- `POST /v1/audio/speech` on the host gateway is HTTP 503.
