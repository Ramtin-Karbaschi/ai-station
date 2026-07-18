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
- the Open WebUI persistent volume contains incompatible state;
- port 3000 is already in use.

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

## Embedding server failure

~~~bash
docker compose logs --tail=200 embedder
curl -v http://127.0.0.1:8090/v1/models
./scripts/verify-models.sh --profile core
~~~

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

~~~bash
ss -lntp | grep -E \
  ':(3000|5432|6379|8082|8090|8888|8889|8890|9998)\b'
~~~

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
