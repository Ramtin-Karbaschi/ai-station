#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

echo "============================================================"
echo " AI Station - Installer validation"
echo "============================================================"

for SCRIPT in \
    scripts/install.sh \
    scripts/preflight-install.sh \
    scripts/verify-build-lock.sh
do
    if [[ ! -x "$SCRIPT" ]]; then
        echo "FAIL: Script is missing or not executable: $SCRIPT"
        exit 1
    fi

    bash -n "$SCRIPT"
    echo "OK: Shell syntax: $SCRIPT"
done

scripts/install.sh --help >/dev/null
scripts/preflight-install.sh --help >/dev/null

echo "OK: Installer help interfaces are valid."

scripts/verify-build-lock.sh

scripts/install.sh \
    --validate-only \
    --source "$ROOT"

echo
echo "INSTALLER VALIDATION PASSED"
