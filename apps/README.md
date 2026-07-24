# Apps layout

## Active runtime components

| Path | Role |
|---|---|
| `apps/gateway` | Host OpenAI-compatible gateway, admission, provider registry |
| `apps/ui-gateway` | OCR-aware Open WebUI attachment proxy |

## Legacy / not deployed by Compose

The following trees are retained for reference and are **not** part of the
active Compose stack or installer path:

- `apps/api`
- `apps/worker`
- `apps/ocr`
- `apps/web`

Do not assume these services are running. Prefer deleting or extracting
useful code into active modules only after an ADR.
