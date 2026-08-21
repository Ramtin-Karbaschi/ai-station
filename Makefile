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
	test \
	check \
	verify \
	models-core \
	models-all \
	models-verify \
	models-use \
	projects-list \
	docs-audit \
	audit

help:
	@printf '%s\n' \
		'AI Station commands:' \
		'  make config         Validate Docker Compose configuration' \
		'  make pull           Pull locked registry images' \
		'  make build          Build repository-controlled images' \
		'  make start          Start AI Station (default: general profile)' \
		'  make stop           Stop AI Station' \
		'  make restart        Restart AI Station' \
		'  make status         Show service and endpoint status' \
		'  make logs           Follow LiteLLM gateway logs' \
		'  make test           Run offline unit and contract tests' \
		'  make check          Run all offline quality gates' \
		'  make verify         Verify the active runtime' \
		'  make models-core    Provision the Core model profile' \
		'  make models-all     Provision the complete model profile' \
		'  make models-verify  Verify the Core model profile' \
		'  make models-use PROFILE=coder   Switch heavy model profile' \
		'  make projects-list  List registered application projects' \
		'  make docs-audit     Validate documentation quality' \
		'  make audit          Run the complete release audit' \
		'' \
		'Platform CLI: ai --help'

config:
	docker compose config --quiet

pull:
	docker compose pull --ignore-buildable

build:
	docker compose build

start:
	./scripts/ai start

stop:
	./scripts/ai stop

restart:
	./scripts/ai restart

status:
	./scripts/ai status

logs:
	./scripts/ai logs gateway

test:
	./scripts/ai test

check:
	./scripts/test.sh
	docker compose config --quiet
	./scripts/verify-model-manifest.sh
	./scripts/verify-image-lock.sh
	./scripts/verify-build-lock.sh
	./scripts/docs-audit.sh

verify:
	./scripts/ai verify

models-core:
	./scripts/provision-models.sh --profile core

models-all:
	./scripts/provision-models.sh --profile all

models-verify:
	./scripts/verify-models.sh --profile core

models-use:
	./scripts/ai models use $(PROFILE)

projects-list:
	./scripts/ai projects list

docs-audit:
	./scripts/docs-audit.sh

audit:
	./scripts/release-audit.sh
