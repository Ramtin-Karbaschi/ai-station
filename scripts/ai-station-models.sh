#!/usr/bin/env bash
set -euo pipefail

cd /opt/ai-station

COMPOSE="./scripts/compose-ai-station.sh"

case "${1:-help}" in
  ps)
    $COMPOSE ps
    ;;

  config)
    $COMPOSE config --quiet
    echo "Compose configuration is valid."
    ;;

  all-down)
    $COMPOSE stop llm-general embedder 2>/dev/null || true
    ;;

  general-up)
    $COMPOSE up -d --force-recreate llm-general
    ;;

  general-down)
    $COMPOSE stop llm-general || true
    ;;

  rag-up|embedder-up)
    $COMPOSE up -d --force-recreate embedder
    ;;

  rag-down|embedder-down)
    $COMPOSE stop embedder || true
    ;;

  logs-general)
    $COMPOSE logs -f --tail=150 llm-general
    ;;

  logs-rag|logs-embedder)
    $COMPOSE logs -f --tail=150 embedder
    ;;

  help|*)
    cat <<'HELP'
AI Station Model Commands (verified baseline)

Status:
  ./scripts/ai-station-models.sh ps
  ./scripts/ai-station-models.sh config
  ./scripts/ai-station-models.sh all-down

General LLM:
  ./scripts/ai-station-models.sh general-up
  ./scripts/ai-station-models.sh general-down
  ./scripts/ai-station-models.sh logs-general

Embedding:
  ./scripts/ai-station-models.sh embedder-up
  ./scripts/ai-station-models.sh embedder-down
  ./scripts/ai-station-models.sh logs-embedder

Optional coder/reranker weights may exist under /srv/ai-station/models
but are not part of the verified default Compose runtime.
HELP
    ;;
esac
