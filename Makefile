.PHONY: config build core llm obs edge down logs ps backup restore-test gpu-test

config:
	docker compose config

build:
	docker compose build

core:
	docker compose up -d postgres redis api worker web

llm:
	docker compose --profile llm up -d llm

obs:
	docker compose --profile obs up -d prometheus grafana

edge:
	docker compose --profile edge up -d edge

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

gpu-test:
	docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi

backup:
	bash scripts/backup.sh
