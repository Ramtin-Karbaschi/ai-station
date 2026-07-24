#!/usr/bin/env bash
# Bootstrap AI Station on Ubuntu-class Linux with NVIDIA + Docker.
set -Eeuo pipefail

REPO_URL="${AI_STATION_REPO_URL:-https://github.com/Ramtin-Karbaschi/ai-station.git}"
CLONE_DIR="${AI_STATION_CLONE_DIR:-/tmp/ai-station-src}"
BRANCH="${AI_STATION_BRANCH:-main}"

echo "AI Station Linux bootstrap"
echo "Repo:   $REPO_URL"
echo "Branch: $BRANCH"
echo

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing required command: $1" >&2
    exit 1
  }
}

need git
need docker
need nvidia-smi

echo "GPU:"
nvidia-smi -L | head -1
echo "Docker Compose:"
docker compose version | head -1
echo

if [[ -d "$CLONE_DIR/.git" ]]; then
  git -C "$CLONE_DIR" fetch --prune origin
  git -C "$CLONE_DIR" checkout "$BRANCH"
  git -C "$CLONE_DIR" pull --ff-only origin "$BRANCH"
else
  rm -rf "$CLONE_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$CLONE_DIR"
fi

cd "$CLONE_DIR"
chmod +x scripts/install.sh scripts/ai scripts/*.sh 2>/dev/null || true

./scripts/install.sh --validate-only
sudo ./scripts/install.sh

echo
echo "Done."
echo "Open WebUI: http://127.0.0.1:3000"
echo "App API:    http://127.0.0.1:4000/v1"
echo "Try:        ai status && ai verify"
