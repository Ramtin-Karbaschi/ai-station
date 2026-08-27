# Troubleshooting

## First diagnostic commands

~~~bash
cd /opt/ai-station

docker compose config --quiet
docker compose ps
./scripts/status.sh
./scripts/verify.sh
nvidia-smi
docker system df
~~~

## Open WebUI is unavailable

Check:

~~~bash
docker compose ps open-webui
docker compose logs --tail=200 open-webui
curl -v http://127.0.0.1:3000
~~~

Common causes:

- PostgreSQL is unhealthy;
- required secret values are missing;
- Tika or the embedding service has not started;
- the CPU reranker on `:8091` is down (hybrid RAG needs it);
- the Open WebUI persistent volume contains incompatible state;
- port 3000 is already in use.

## Knowledge RAG returns empty or ignores documents

Check:

~~~bash
curl -fsS http://127.0.0.1:8091/v1/models
docker compose --profile reranker ps reranker
docker compose logs --tail=100 open-webui reranker
~~~

Common causes:

- Knowledge collection is not attached to the chat;
- Native function calling is on (station default is `default` so chunks
  auto-inject);
- ComfyUI holds the GPU, so the chat model is stopped (CPU embedder stays up; ADR-022);
- hybrid search cannot reach `http://reranker:8091/v1/rerank`.

See [clients/OPENWEBUI.md](clients/OPENWEBUI.md).

## ComfyUI media studio is unavailable

ComfyUI is retained production media and off by default (`ai start` does
not launch it). Open WebUI chat does not start it. Weights must never
be deleted.

~~~bash
ai provider start comfyui-media-experimental --dry-run
curl -v http://127.0.0.1:8188/system_stats
docker logs --tail=200 ai-station-comfyui-experimental
~~~

If the GPU still holds a llama.cpp profile, stop it first
(`ai models stop`). See [clients/COMFYUI.md](clients/COMFYUI.md).

## n8n is unavailable

n8n is optional and off by default (`ai start` does not launch it).
It is CPU-only and does not stop llama.cpp.

~~~bash
ai n8n status
ai provider start n8n --dry-run
curl -v http://127.0.0.1:5678/healthz
ai logs n8n
~~~

Common causes:

- `N8N_ENCRYPTION_KEY` missing from `.env` (first start writes it);
- `/srv/ai-station/runtime/n8n` not writable by uid 1000;
- LiteLLM `:4000` is down, so imported workflows fail even if the UI loads.

See [clients/N8N.md](clients/N8N.md).

## Open WebUI shows stale or missing model names

The picker merges three sources: LiteLLM `/v1/models`, Open WebUI env
(`OPENAI_API_CONFIGS`, `DEFAULT_MODELS`), and custom rows in Postgres
table `model` (database `openwebui`). `ENABLE_PERSISTENT_CONFIG=False`
locks env config; it does not delete stored custom models.

If a dead name such as `general-qwen3.6` or `Arena Model` remains after
catalog changes, inspect and remove only those rows (after a timestamped
`pg_dump` of `openwebui`):

~~~bash
docker exec -i ai-station-postgres-1 \
  psql -U openwebui -d openwebui \
  -c "SELECT id, name, base_model_id, is_active FROM model ORDER BY id;"
~~~

Arena evaluation is disabled with `ENABLE_EVALUATION_ARENA_MODELS=False`.
Recreate `open-webui` after env changes so the container loads current
Compose values. Old chat messages may still mention retired names; they
will not reappear in the picker once the `model` rows are gone.

## Model server does not start

Check:

~~~bash
docker compose logs --tail=300 llm-general
nvidia-smi
ls -lh /srv/ai-station/models/general
./scripts/verify-models.sh --profile core
~~~

Common causes:

- model file missing or checksum mismatch;
- insufficient VRAM;
- another heavy model is active;
- NVIDIA container support is unavailable;
- context size is too large for the available memory.

## NVIDIA GPU is not visible

Host check:

~~~bash
nvidia-smi
~~~

Container check:

~~~bash
docker run --rm --gpus all \
  nvidia/cuda:12.8.0-base-ubuntu24.04 \
  nvidia-smi
~~~

If the host command works but the container command fails, inspect Docker
Desktop WSL integration and NVIDIA container runtime support.

## `nvidia-smi` VRAM free looks wrong after heavy container churn

Symptom (observed 2026-08-19): after repeated heavy-model container
start/stop churn (e.g. a benchmark script that cycles `llm-coder`/`llm-ornith`
many times), `nvidia-smi --query-gpu=memory.used,memory.free` can report an
implausibly low `memory.used` (roughly 1.0-1.2 GiB) and correspondingly high
`memory.free` (roughly 23 GiB) even while a real ~21 GiB heavy model is fully
loaded and actively serving completions. Five repeated polls a few seconds
apart were consistent, so this is not one-off sampling jitter.

Confirm a model is really loaded despite a suspicious `nvidia-smi` reading:

~~~bash
docker logs ai-station-llm-<profile> --tail 60 | grep -E \
  'model loaded|print_timing|tokens per second'
curl -s http://127.0.0.1:<port>/v1/models
~~~

A `llama_server: model loaded` line plus real `prompt eval time` /
`tokens per second` lines for actual completions (not just the load line)
confirms the model is genuinely resident and serving, regardless of what
`nvidia-smi` reports.

What was verified live on this machine while investigating:

- A stale reading was captured at rest: `nvidia-smi` showed `1197 MiB` used /
  `22941 MiB` free while `ai-station-llm-ornith` logs proved the ~21 GiB
  Ornith model was loaded and had served multiple real completions.
- A single clean `docker compose --profile ornith stop llm-ornith` followed
  by `./scripts/ai models use ornith` (cold reload, no rapid churn) produced
  an **accurate** reading immediately after the healthcheck passed
  (`21697 MiB` used / `2441 MiB` free — consistent with a ~21 GiB model plus
  KV cache), and it stayed stable and accurate over 5 polls across 100
  seconds of idle time afterward.
- `docker stats --no-stream` was checked as a second data source; it reports
  container **host RAM** cgroup usage (hundreds of MiB), not GPU VRAM, so it
  cannot corroborate or refute the VRAM number either way — it is not a
  useful cross-check for this specific symptom.
- `nvidia-smi`'s per-process column shows `N/A` for the `llama-server` PID,
  a documented WSL2 GPU-passthrough limitation for per-process attribution.

Conclusion: the aggregate `memory.used`/`memory.free` numbers start out
accurate right after a fresh model load, but can drift to an inaccurate,
much-too-low `memory.used` reading after enough heavy container start/stop
churn (as a rapid benchmark loop performs), and a subsequent clean
stop/start cycle resets the reading back to accurate. The exact trigger
threshold (how much churn, over what time window) was not isolated in this
pass. This is most likely a WSL2 GPU-passthrough VRAM-accounting quirk in
how the Windows host driver reports aggregate usage back into the WSL2
`nvidia-smi` view, not a bug in this repository's code, and reproducing or
fixing it at the NVIDIA driver / WSL2 level is out of scope here.

Why this does not create an immediate double-load/OOM safety risk today:
[`apps/gateway/app/admission.py`](../apps/gateway/app/admission.py)'s
`probe_free_vram_mib()` does shell out to this exact `nvidia-smi` command,
but the one-heavy-GPU invariant in `admit()` is enforced primarily through
the `active_heavy` marker file
(`read_active_heavy_profiles()` / `ACTIVE_PROFILE_FILE`,
`/srv/ai-station/runtime/active-heavy-profile`) — i.e. whether another heavy
profile is *recorded* as active — not through the raw VRAM number. The raw
VRAM number only changes which specific decision (`START` vs
`START_WITH_REDUCED_CONTEXT` vs `STOP_CONFLICTING_PROVIDER_AND_START` vs
`REJECT`/`FALLBACK`) is returned for a *new* provider request; it does not by
itself let a second heavy provider start silently alongside an already-active
one. `admission.py` now also exposes `vram_probe_looks_stale()`, a
non-blocking diagnostic that flags (via `ai status`) when the marker file
says a heavy profile is active but the probed free VRAM is implausibly close
to the full GPU total — this does not change any admission decision, it only
makes a suspicious reading visible instead of silently trusted.

## Embedding server failure

~~~bash
docker compose logs --tail=200 embedder
curl -v http://127.0.0.1:8090/v1/models
./scripts/verify-models.sh --profile core
~~~

## Reranker failure

~~~bash
docker compose --profile reranker logs --tail=200 reranker
curl -v http://127.0.0.1:8091/v1/models
curl -fsS http://127.0.0.1:8091/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"ai-station-reranker","query":"test","documents":["alpha","beta"],"top_n":2}'
~~~

The reranker is CPU-only and starts with `ai start`. Hybrid RAG in Open
WebUI calls `http://reranker:8091/v1/rerank`.

## Persian OCR failure

~~~bash
docker exec ai-station-tika \
  tesseract --list-langs
~~~

The output must contain:

~~~text
fas
~~~

Rebuild Tika when necessary:

~~~bash
docker compose build tika
docker compose up -d --force-recreate tika
~~~

## OpenCode repeats compaction after a PDF attachment

Run `ai opencode configure`, restart the managed Desktop connection, and then
run `ai verify`. The managed `local-attachments.js` plugin must be present under
the `aidev` OpenCode config. It extracts PDFs through local Tika before model
inference and disables synthetic continuation after provider-size overflow.
Audit an old export with `ai opencode audit-session SESSION.json --json`; three
or more compactions, empty assistant messages, or a large inline media payload
are treated as a failed session rather than normal progress.

## SearXNG failure

~~~bash
docker compose logs --tail=200 searxng

curl \
  "http://127.0.0.1:8889/search?q=test&format=json"
~~~

Search availability depends on the configured upstream search engines and
network restrictions.

## Gateway failure

~~~bash
systemctl status ai-station-gateway
systemctl status ai-station-ui-gateway

journalctl -u ai-station-gateway -n 200 --no-pager
journalctl -u ai-station-ui-gateway -n 200 --no-pager

curl -v http://127.0.0.1:8888/health
curl -v http://127.0.0.1:8890/health
~~~

## OpenCode cannot develop or reach local models

The supported client is OpenCode running **inside WSL as `aidev`**. Native
Windows Desktop operating directly on a `\\\\wsl.localhost\\...` worktree is
not the verified path because the shell and filesystem live on different
platform sides.

Run:

~~~bash
ai opencode doctor
ai status
ai health
~~~

Interpret doctor failures directly:

- `non_root_developer`: repair with
  `ai opencode install --create-user --own-project`;
- `pinned_runtime`: reinstall the checksum-pinned WSL binary;
- `valid_config` or `developer_tools`: run `ai opencode configure`;
- `litellm_boundary`: the config must use
  `http://127.0.0.1:4000/v1`, never `:8888` or a llama.cpp port;
- `authenticated_model_access`: repair the `opencode` project key/allowlist
  with `ai opencode configure`.

Confirm the actual developer workflow with:

~~~bash
ai opencode acceptance --keep
~~~

A pass proves tool use, file editing, and a resulting green unit test. A raw
chat response or function-call probe does not prove IDE capability. On failure,
the retained disposable workspace is printed for focused inspection.

Launch with `ai opencode run /opt/ai-station` or Windows Manager option 28.
Do not launch the coding agent as root or grant it the Docker group.

## OpenCode stops early or loses a multi-part task

Abort the stale session and start a new WSL-native session after
`ai opencode configure`. Current configuration gives the build agent 40
iterations and requires the `inspect -> edit -> test -> report` loop.

The old custom compaction agent and
`disable-compaction-autocontinue.js` hook were removed. They depended on
unstable OpenCode internals and could distort the normal agent loop.
Compaction now uses only the supported native fields: `auto`, `prune`, and
`reserved`.

For a large request, state deliverables and acceptance tests explicitly. A task
is complete only when each deliverable has filesystem or test evidence.

## OpenCode input exceeds its client context

OpenCode advertises a 8192-token Ornith/coder limit and 4096-token output
budget. Qwen3.8 general/reasoning advertise 262144 after the 2026-08-27
GPU probe. Avoid attaching generated artifacts, model files,
complete logs, or `GRAPH_REPORT.md`. Use Graphify queries and bounded log
snapshots instead.

If a request still returns empty output, capture the matching LiteLLM and
llama.cpp logs and verify the HTTP status. Do not hide the problem with a custom
client hook or an invented 87k context setting.

## OpenCode edit fails on non-ASCII or RTL content

Re-read the exact file after a failed edit and apply a smaller patch with stable
ASCII context around the target. Verify UTF-8 and run the relevant test. Do not
replace an entire user file merely to work around a patch-context mismatch.


## Chat replies stop mid-sentence

Open WebUI default `max_tokens` is 4096 (raised from 1024). A mid-sentence cut
with `finish_reason` `length` means the completion budget or the 262144-token
context window filled.

~~~bash
# Inspect the last completion via LiteLLM (not llama.cpp :8888)
curl -sS http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen3.8-27B-UD-Q4_K_M","messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
~~~

`choices[0].finish_reason` should be `stop` for short answers. `length` on a
short prompt is an output-cap problem; `length` on a long RAG thread is the
262144 context window. Recreate Open WebUI after changing
`DEFAULT_MODEL_PARAMS`.

## Whisper failure

~~~bash
docker exec -it ai-station-open-webui-1 \
  find /app/backend/data/cache/whisper/models \
  -maxdepth 2 \
  -type f
~~~

Then run:

~~~bash
./scripts/provision-whisper-large-v3-resumable.sh
./scripts/verify.sh
~~~

## Port conflict

Loopback ports that the station publishes:

~~~bash
ss -lntp | grep -E \
  ':(3000|5432|6379|8082|8090|8888|8889|8890|9998)\b'
~~~

### Docker Desktop `/forwards/expose` HTTP 500

On Windows 11 + WSL2, Docker Desktop's userspace port proxy can fail while
publishing `127.0.0.1:9998` (Apache Tika) or another loopback port:

~~~text
Error response from daemon: ports are not available: exposing port
TCP 127.0.0.1:9998 -> 127.0.0.1:0: /forwards/expose returned unexpected
status: 500
~~~

`ai start` retries compose up three times and removes containers stuck in
`Created`. If it still fails:

1. Wait until Docker Desktop shows running.
2. Restart Docker Desktop once.
3. Run Start again from Manager.

Do not bind station ports to `0.0.0.0` to work around this.

## Release audit warning

Do not hide a warning by blindly adding a file to an allowlist.

Identify whether the warning represents:

- a real portability problem;
- generated state committed by mistake;
- a large binary;
- a secret;
- a stale document;
- an intentional installation-contract reference.

Fix the source of the warning where possible, then rerun:

~~~bash
./scripts/release-audit.sh
~~~
