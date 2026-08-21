# Graphify integration for AI Station.
# Sourced by scripts/ai after OpenCode integration is available.

GRAPHIFY_MANIFEST="$ROOT/config/clients/graphify/manifest.json"
GRAPHIFY_VENV="$ROOT/.venvs/graphify"
GRAPHIFY_RUNTIME_ROOT="/srv/ai-station/runtime/graphify"

ai_graphify_usage() {
  cat <<'EOF'
Usage:
  ai graphify install [--dry-run]
  ai graphify configure [--dry-run]
  ai graphify status
  ai graphify extract [PATH] [--code-only|--docs] [--dry-run] [--force]
  ai graphify query "<question>" [--graph PATH]
  ai graphify path "<A>" "<B>" [--graph PATH]
  ai graphify explain "<concept>" [--graph PATH]
  ai graphify uninstall [--purge] [--dry-run]

Default extract is --code-only (tree-sitter, no GPU). --docs uses LiteLLM :4000.
Graphs live under /srv/ai-station/runtime/graphify/ (not committed).
EOF
}

ai_graphify_version() {
  python3 - "$GRAPHIFY_MANIFEST" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data["version"])
PY
}

ai_graphify_bin() {
  printf '%s\n' "$GRAPHIFY_VENV/bin/graphify"
}

ai_graphify_default_out() {
  printf '%s\n' "$GRAPHIFY_RUNTIME_ROOT/ai-station"
}

ai_graphify_find_graph() {
  local explicit="${1:-}"
  if [[ -n "$explicit" && -f "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return 0
  fi
  local candidate
  for candidate in \
    "$PWD/graphify-out/graph.json" \
    "$ROOT/graphify-out/graph.json" \
    "$(ai_graphify_default_out)/graphify-out/graph.json"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

cmd_graphify() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    install) cmd_graphify_install "$@" ;;
    configure) cmd_graphify_configure "$@" ;;
    status) cmd_graphify_status ;;
    extract) cmd_graphify_extract "$@" ;;
    query) cmd_graphify_query "$@" ;;
    path) cmd_graphify_path "$@" ;;
    explain) cmd_graphify_explain "$@" ;;
    uninstall) cmd_graphify_uninstall "$@" ;;
    -h|--help|help|"") ai_graphify_usage ;;
    *)
      echo "Unknown graphify command: $sub" >&2
      ai_graphify_usage >&2
      exit 2
      ;;
  esac
}

cmd_graphify_install() {
  local dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: ai graphify install [--dry-run]" >&2
        exit 2
        ;;
    esac
  done
  local version
  version="$(ai_graphify_version)"
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN: would create $GRAPHIFY_VENV"
    echo "DRY-RUN: would pip install graphifyy[openai,pdf]==${version} (LiteLLM loopback extra; no Gemini/cloud extras)"
    return 0
  fi
  if [[ ! -x "$GRAPHIFY_VENV/bin/python" ]]; then
    python3 -m venv "$GRAPHIFY_VENV"
  fi
  "$GRAPHIFY_VENV/bin/python" -m pip install \
    --disable-pip-version-check \
    "graphifyy[openai,pdf]==${version}"
  local reported
  reported="$("$(ai_graphify_bin)" --version 2>/dev/null | awk '{print $2}')"
  if [[ "$reported" != "$version" ]]; then
    echo "ERROR: expected graphify ${version}, got ${reported:-unknown}" >&2
    exit 1
  fi
  echo "OK: graphify ${reported} at $(ai_graphify_bin)"
}

cmd_graphify_configure() {
  local dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: ai graphify configure [--dry-run]" >&2
        exit 2
        ;;
    esac
  done
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN: would ensure pinned graphify venv"
    echo "DRY-RUN: would refresh OpenCode graphify command/plugin via ai opencode configure"
    echo "DRY-RUN: would refresh OpenCode graphify command/plugin via ai opencode configure"
    return 0
  fi
  if [[ ! -x "$(ai_graphify_bin)" ]]; then
    cmd_graphify_install
  fi
  cmd_opencode_configure
  echo "OK: OpenCode graphify command/plugin deployed with opencode configure"
  echo "OK: OpenCode graphify command/plugin deployed with opencode configure"
  echo "Restart the OpenCode WSL client to load the new command/plugin."
}

cmd_graphify_status() {
  local version bin graph
  version="$(ai_graphify_version)"
  bin="$(ai_graphify_bin)"
  echo "pin:     graphifyy==${version}"
  echo "venv:    $GRAPHIFY_VENV"
  if [[ -x "$bin" ]]; then
    echo "cli:     $bin ($("$bin" --version 2>/dev/null || echo missing))"
  else
    echo "cli:     not installed (run: ai graphify install)"
  fi
  if graph="$(ai_graphify_find_graph 2>/dev/null)"; then
    echo "graph:   $graph"
  else
    echo "graph:   missing (run: ai graphify extract --code-only)"
  fi
}

cmd_graphify_extract() {
  local dry_run=0 mode="code-only" force=0 target="$ROOT"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --code-only) mode="code-only"; shift ;;
      --docs) mode="docs"; shift ;;
      --force) force=1; shift ;;
      --help|-h) ai_graphify_usage; return 0 ;;
      --*)
        echo "Unknown argument: $1" >&2
        echo "Usage: ai graphify extract [PATH] [--code-only|--docs] [--dry-run] [--force]" >&2
        exit 2
        ;;
      *)
        target="$1"
        shift
        ;;
    esac
  done
  local out tag
  tag="$(basename "$(readlink -f "$target")")"
  out="$GRAPHIFY_RUNTIME_ROOT/$tag"
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN: would extract $target -> $out/graphify-out/ (mode=$mode, force=$force)"
    if [[ "$mode" == "docs" ]]; then
      echo "DRY-RUN: would set OPENAI_BASE_URL=http://127.0.0.1:4000/v1 (key not printed)"
      echo "DRY-RUN: would pass --backend openai --max-concurrency 1 --token-budget 4096"
    fi
    return 0
  fi
  if [[ ! -x "$(ai_graphify_bin)" ]]; then
    cmd_graphify_install
  fi
  mkdir -p "$out"
  local args=(extract "$target" --out "$out")
  if [[ "$force" -eq 1 ]]; then
    args+=(--force)
  fi
  if [[ "$mode" == "code-only" ]]; then
    args+=(--code-only)
    "$(ai_graphify_bin)" "${args[@]}"
  else
    if ! curl -fsS --max-time 5 "http://127.0.0.1:4000/health/liveliness" >/dev/null; then
      echo "ERROR: LiteLLM gateway is not healthy on :4000" >&2
      exit 1
    fi
    if ! ai_opencode_key_ready; then
      echo "ERROR: projects/opencode.env is missing a usable LLM_API_KEY" >&2
      echo "Run: ai opencode configure" >&2
      exit 1
    fi
    local model
    model="$(public_name_for_profile coder)"
    python3 - "$(ai_opencode_env_file)" "$(ai_graphify_bin)" "$model" "${args[@]}" <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

env_file = Path(sys.argv[1])
bin_path = sys.argv[2]
model = sys.argv[3]
cmd = [bin_path, *sys.argv[4:]]
key = ""
for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() == "LLM_API_KEY":
        key = value.strip().strip('"').strip("'")
        break
if not key or key == "REVOKED":
    raise SystemExit("ERROR: LLM_API_KEY missing")
env = os.environ.copy()
env["OPENAI_API_KEY"] = key
env["OPENAI_BASE_URL"] = "http://127.0.0.1:4000/v1"
env["OPENAI_MODEL"] = model
cmd += ["--backend", "openai", "--model", model, "--max-concurrency", "1", "--token-budget", "4096"]
raise SystemExit(subprocess.call(cmd, env=env))
PY
  fi
  if [[ "$(readlink -f "$target")" == "$(readlink -f "$ROOT")" ]]; then
    ln -sfn "$out/graphify-out" "$ROOT/graphify-out"
    echo "OK: linked $ROOT/graphify-out -> $out/graphify-out"
  fi
  echo "OK: graph at $out/graphify-out/graph.json"
}

cmd_graphify_query() {
  local graph="" question=""
  local extra=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --graph) graph="${2:-}"; shift 2 ;;
      --help|-h) ai_graphify_usage; return 0 ;;
      *)
        if [[ -z "$question" ]]; then
          question="$1"
        else
          extra+=("$1")
        fi
        shift
        ;;
    esac
  done
  if [[ -z "$question" ]]; then
    echo "Usage: ai graphify query \"<question>\" [--graph PATH]" >&2
    exit 2
  fi
  local resolved
  if ! resolved="$(ai_graphify_find_graph "$graph")"; then
    echo "ERROR: graph.json not found. Run: ai graphify extract --code-only" >&2
    exit 1
  fi
  if [[ ! -x "$(ai_graphify_bin)" ]]; then
    cmd_graphify_install
  fi
  "$(ai_graphify_bin)" query "$question" --graph "$resolved" "${extra[@]}"
}

cmd_graphify_path() {
  local graph="" a="" b=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --graph) graph="${2:-}"; shift 2 ;;
      --help|-h) ai_graphify_usage; return 0 ;;
      --*)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
      *)
        if [[ -z "$a" ]]; then a="$1"; else b="$1"; fi
        shift
        ;;
    esac
  done
  if [[ -z "$a" || -z "$b" ]]; then
    echo "Usage: ai graphify path \"<A>\" \"<B>\" [--graph PATH]" >&2
    exit 2
  fi
  local resolved
  if ! resolved="$(ai_graphify_find_graph "$graph")"; then
    echo "ERROR: graph.json not found. Run: ai graphify extract --code-only" >&2
    exit 1
  fi
  if [[ ! -x "$(ai_graphify_bin)" ]]; then
    cmd_graphify_install
  fi
  "$(ai_graphify_bin)" path "$a" "$b" --graph "$resolved"
}

cmd_graphify_explain() {
  local graph="" concept=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --graph) graph="${2:-}"; shift 2 ;;
      --help|-h) ai_graphify_usage; return 0 ;;
      --*)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
      *)
        concept="$1"
        shift
        ;;
    esac
  done
  if [[ -z "$concept" ]]; then
    echo "Usage: ai graphify explain \"<concept>\" [--graph PATH]" >&2
    exit 2
  fi
  local resolved
  if ! resolved="$(ai_graphify_find_graph "$graph")"; then
    echo "ERROR: graph.json not found. Run: ai graphify extract --code-only" >&2
    exit 1
  fi
  if [[ ! -x "$(ai_graphify_bin)" ]]; then
    cmd_graphify_install
  fi
  "$(ai_graphify_bin)" explain "$concept" --graph "$resolved"
}

cmd_graphify_uninstall() {
  local dry_run=0 purge=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --purge) purge=1; shift ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: ai graphify uninstall [--purge] [--dry-run]" >&2
        exit 2
        ;;
    esac
  done
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN: would remove $GRAPHIFY_VENV"
    if [[ "$purge" -eq 1 ]]; then
      echo "DRY-RUN: would remove $GRAPHIFY_RUNTIME_ROOT and $ROOT/graphify-out"
    fi
    return 0
  fi
  rm -rf "$GRAPHIFY_VENV"
  echo "OK: removed graphify venv"
  if [[ "$purge" -eq 1 ]]; then
    rm -rf "$GRAPHIFY_RUNTIME_ROOT"
    rm -f "$ROOT/graphify-out"
    echo "OK: purged runtime graphs"
  fi
}
