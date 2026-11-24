# AI Station Piper voice backend

This is a loopback-only, CPU-only provider for LiteLLM's OpenAI-compatible
`POST /v1/audio/speech`. It loads local Piper ONNX voices lazily and returns
real mono MP3 (`audio/mpeg`). It never downloads models or logs request text.

Install `requirements.txt` in a dedicated virtual environment. Configure
`AI_STATION_PIPER_FA_MODEL` and `AI_STATION_PIPER_EN_MODEL` to the verified
`.onnx` files (each must have its `.onnx.json` sidecar), then run:

```sh
python -m apps.voice.service
```

Supported voice values are `auto` (the default), `fa`, `en`, and Open WebUI's
`alloy` alias (both auto-detect the turn language); only `mp3` is accepted.
The service binds to `127.0.0.1` by default (port `8095`); a container may set
`AI_STATION_TTS_HOST=0.0.0.0` on its isolated network. Route it through
LiteLLM; do not expose this provider as a public application API.
