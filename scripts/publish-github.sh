#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_NAME="${AI_STATION_GITHUB_REPO:-ai-station}"
VISIBILITY="${AI_STATION_GITHUB_VISIBILITY:-private}"

cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: GitHub CLI is not installed."
    echo
    echo "After installing it, run:"
    echo "  gh auth login"
    echo "  ./scripts/publish-github.sh"
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "ERROR: GitHub CLI is not authenticated."
    echo
    echo "Run:"
    echo "  gh auth login"
    echo "  ./scripts/publish-github.sh"
    exit 1
fi

./scripts/release-audit.sh

git branch -M main

if git remote get-url origin >/dev/null 2>&1; then
    git push -u origin main
else
    LOGIN="$(gh api user --jq '.login')"

    if gh repo view "$LOGIN/$REPO_NAME" >/dev/null 2>&1; then
        git remote add origin \
            "https://github.com/${LOGIN}/${REPO_NAME}.git"

        git push -u origin main
    else
        case "$VISIBILITY" in
            private)
                VISIBILITY_FLAG="--private"
                ;;
            public)
                VISIBILITY_FLAG="--public"
                ;;
            internal)
                VISIBILITY_FLAG="--internal"
                ;;
            *)
                echo "ERROR: Invalid visibility: $VISIBILITY"
                exit 2
                ;;
        esac

        gh repo create "$REPO_NAME" \
            "$VISIBILITY_FLAG" \
            --source=. \
            --remote=origin \
            --push \
            --description \
            "Local-first AI workstation for WSL2 and NVIDIA GPUs"
    fi
fi

echo
echo "GITHUB PUBLICATION PASSED"
git remote -v
