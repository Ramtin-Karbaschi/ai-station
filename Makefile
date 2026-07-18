SHELL := /usr/bin/env bash

.PHONY: \
	help \
	config \
	pull \
	build \
	start \
	stop \
	restart \
	status \
	logs \
	verify \
	models-core \
	models-all \
	models-verify \
	docs-audit \
	audit

help:
	@printf '%s\n' \
		'AI Station commands:' \
		'  make config         Validate Docker Compose configuration' \
		'  make pull           Pull locked registry images' \
		'  make build          Build repository-controlled images' \
		'  make start          Start AI Station' \
		'  make stop           Stop AI Station' \
		'  make restart        Restart AI Station' \
		'  make status         Show service and endpoint status' \
		'  make logs           Follow service logs' \
		'  make verify         Verify the active runtime' \
		'  make models-core    Provision the Core model profile' \
		'  make models-all     Provision the complete model profile' \
		'  make models-verify  Verify the Core model profile' \
		'  make docs-audit     Validate documentation quality' \
		'  make audit          Run the complete release audit'

config:
	docker compose config --quiet

pull:
	docker compose pull --ignore-buildable

build:
	docker compose build

start:
	./scripts/start.sh

stop:
	./scripts/stop.sh

restart: stop start

status:
	./scripts/status.sh

logs:
	./scripts/logs.sh

verify:
	./scripts/verify.sh

models-core:
	./scripts/provision-models.sh --profile core

models-all:
	./scripts/provision-models.sh --profile all

models-verify:
	./scripts/verify-models.sh --profile core

docs-audit:
	./scripts/docs-audit.sh

audit:
	./scripts/release-audit.sh
