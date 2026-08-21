#!/usr/bin/env bash
# Deterministic AI Station test entrypoint for local development and CI.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: ./scripts/test.sh [--live] [--endpoint URL] [--model NAME]

Runs the complete offline unit and contract suite in the gateway Python
environment. --live additionally probes JSON-schema and tool-calling against
the selected llama.cpp OpenAI endpoint (default: general on :8082/v1).

Override the interpreter in CI with AI_STATION_TEST_PYTHON=/path/to/python.
EOF
}

live=0
endpoint="http://127.0.0.1:8082/v1"
model="ai-station-general"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --live) live=1; shift ;;
    --endpoint) endpoint="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown test argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -n "${AI_STATION_TEST_PYTHON:-}" ]]; then
  PYTHON="$AI_STATION_TEST_PYTHON"
elif [[ -x "$ROOT/.venvs/gateway/bin/python" ]]; then
  PYTHON="$ROOT/.venvs/gateway/bin/python"
else
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  echo "ERROR: no usable Python interpreter found" >&2
  exit 1
fi

if ! "$PYTHON" -c 'import fastapi, httpx, pydantic, yaml' 2>/dev/null; then
  cat >&2 <<EOF
ERROR: test dependencies are missing from $PYTHON
Install the gateway environment first, or run:
  python3 -m venv .venvs/gateway
  .venvs/gateway/bin/pip install -r apps/gateway/requirements.txt
EOF
  exit 1
fi

echo "Python: $PYTHON ($("$PYTHON" --version 2>&1))"
echo "Running offline unit and contract tests..."
"$PYTHON" -m compileall -q apps benchmarks/runners scripts tests
"$PYTHON" -m unittest discover -s tests -p 'test_*.py' -v

if [[ "$live" -eq 1 ]]; then
  echo
  echo "Running live llama.cpp OpenAI contract probes..."
  "$PYTHON" tests/test_openai_contracts.py \
    --live \
    --endpoint "$endpoint" \
    --model "$model"
fi

echo
echo "TEST SUITE PASSED"
