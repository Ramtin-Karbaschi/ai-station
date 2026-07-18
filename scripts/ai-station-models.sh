#!/usr/bin/env bash
set -euo pipefail

cd /opt/ai-station

if [ ! -f .env.models ]; then
  echo "ERROR: .env.models not found in /opt/ai-station"
  exit 1
fi

COMPOSE="docker compose --env-file .env.models -f compose.yml -f compose.models.yml"

case "${1:-help}" in
  ps)
    $COMPOSE --profile llm-general --profile coder --profile thinking --profile vision --profile rag --profile reranker ps
    ;;

  config)
    $COMPOSE --profile llm-general --profile coder --profile thinking --profile vision --profile rag --profile reranker config
    ;;

  all-down)
    $COMPOSE stop llm-general llm-coder llm-thinking vlm embedder reranker 2>/dev/null || true
    $COMPOSE rm -f llm-general llm-coder llm-thinking vlm embedder reranker 2>/dev/null || true
    ;;

  general-up)
    $COMPOSE --profile llm-general up -d --force-recreate llm-general
    ;;

  general-down)
    $COMPOSE stop llm-general || true
    ;;

  coder-up)
    $COMPOSE --profile coder up -d --force-recreate llm-coder
    ;;

  coder-down)
    $COMPOSE stop llm-coder || true
    ;;

  thinking-up)
    $COMPOSE --profile thinking up -d --force-recreate llm-thinking
    ;;

  thinking-down)
    $COMPOSE stop llm-thinking || true
    ;;

  vision-up)
    $COMPOSE --profile vision up -d --force-recreate vlm
    ;;

  vision-down)
    $COMPOSE stop vlm || true
    ;;

  rag-up)
    $COMPOSE --profile rag up -d --force-recreate embedder
    ;;

  rag-down)
    $COMPOSE stop embedder || true
    ;;

  reranker-up)
    $COMPOSE --profile reranker up -d --force-recreate reranker
    ;;

  reranker-down)
    $COMPOSE stop reranker || true
    ;;

  logs-general)
    $COMPOSE logs -f --tail=150 llm-general
    ;;

  logs-coder)
    $COMPOSE logs -f --tail=150 llm-coder
    ;;

  logs-thinking)
    $COMPOSE logs -f --tail=150 llm-thinking
    ;;

  logs-vision)
    $COMPOSE logs -f --tail=150 vlm
    ;;

  logs-rag)
    $COMPOSE logs -f --tail=150 embedder
    ;;

  logs-reranker)
    $COMPOSE logs -f --tail=150 reranker
    ;;

  help|*)
    cat <<'HELP'
AI Station Model Commands

Status:
  ./scripts/ai-station-models.sh ps
  ./scripts/ai-station-models.sh config
  ./scripts/ai-station-models.sh all-down

General:
  ./scripts/ai-station-models.sh general-up
  ./scripts/ai-station-models.sh general-down
  ./scripts/ai-station-models.sh logs-general

Coder:
  ./scripts/ai-station-models.sh coder-up
  ./scripts/ai-station-models.sh coder-down
  ./scripts/ai-station-models.sh logs-coder

Thinking:
  ./scripts/ai-station-models.sh thinking-up
  ./scripts/ai-station-models.sh thinking-down
  ./scripts/ai-station-models.sh logs-thinking

Vision:
  ./scripts/ai-station-models.sh vision-up
  ./scripts/ai-station-models.sh vision-down
  ./scripts/ai-station-models.sh logs-vision

RAG:
  ./scripts/ai-station-models.sh rag-up
  ./scripts/ai-station-models.sh rag-down
  ./scripts/ai-station-models.sh logs-rag

Reranker:
  ./scripts/ai-station-models.sh reranker-up
  ./scripts/ai-station-models.sh reranker-down
  ./scripts/ai-station-models.sh logs-reranker
HELP
    ;;
esac
