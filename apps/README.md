# Apps layout

## Active runtime components

| Path | Role |
|---|---|
| `apps/gateway` | Host OpenAI-compatible gateway, admission, provider registry |
| `apps/ui-gateway` | Attachment proxy for Open WebUI (Tika path) |

Legacy application trees (`api`, `worker`, `ocr`, `web`) were removed from the
repository once confirmed unused by Compose, the installer, and the release
audit.
