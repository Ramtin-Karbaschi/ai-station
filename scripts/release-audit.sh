#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ERRORS=0
WARNINGS=0

pass() {
    printf 'OK: %s\n' "$1"
}

warn() {
    printf 'WARNING: %s\n' "$1"
    WARNINGS=$((WARNINGS + 1))
}

fail() {
    printf 'FAIL: %s\n' "$1"
    ERRORS=$((ERRORS + 1))
}

echo "============================================================"
echo " AI Station - Release audit"
echo "============================================================"

# ------------------------------------------------------------
# Docker Compose
# ------------------------------------------------------------

if docker compose config --quiet; then
    pass "Docker Compose configuration is valid"
else
    fail "Docker Compose configuration is invalid"
fi

# ------------------------------------------------------------
# Runtime verification
# ------------------------------------------------------------

if [[ -x scripts/verify.sh ]]; then
    if scripts/verify.sh; then
        pass "Runtime verification passed"
    else
        fail "Runtime verification failed"
    fi
else
    warn "scripts/verify.sh was not found or is not executable"
fi

# ------------------------------------------------------------
# Ignore rules
# ------------------------------------------------------------

check_ignored() {
    local PATH_TO_CHECK="$1"
    local DESCRIPTION="$2"

    if git check-ignore -q "$PATH_TO_CHECK"; then
        pass "$DESCRIPTION"
    else
        fail "$DESCRIPTION"
    fi
}

check_ignored ".env" ".env is ignored by Git"
check_ignored "_archive/example.txt" "Historical archives are ignored by Git"
check_ignored "example.bak-20260718" "Timestamped backups are ignored by Git"
check_ignored "models/example.gguf" "Model artifacts are ignored by Git"
check_ignored "backups/example.dump" "Database backups are ignored by Git"

# ------------------------------------------------------------
# Build the exact set of files eligible for a Git commit
# ------------------------------------------------------------

declare -a RELEASE_FILES=()

while IFS= read -r -d '' FILE; do
    [[ -f "$FILE" ]] || continue
    RELEASE_FILES+=("$FILE")
done < <(
    git ls-files \
        --cached \
        --others \
        --exclude-standard \
        -z
)

if [[ "${#RELEASE_FILES[@]}" -eq 0 ]]; then
    fail "No release files were detected"
else
    pass "${#RELEASE_FILES[@]} release candidate files detected"
fi

# ------------------------------------------------------------
# Allowlist helper
# ------------------------------------------------------------

is_path_allowlisted() {
    local FILE="$1"

    [[ -f config/release-path-allowlist.txt ]] || return 1

    grep -Fxq "$FILE" < <(
        grep -vE '^[[:space:]]*(#|$)' \
            config/release-path-allowlist.txt
    )
}

# Avoid storing the full canonical path as one literal in this script.
INSTALL_ROOT_NEEDLE="/opt""/ai-station"

# ------------------------------------------------------------
# Inspect release candidate files
# ------------------------------------------------------------

for FILE in "${RELEASE_FILES[@]}"; do
    SIZE="$(stat -c '%s' "$FILE")"

    # 90 MiB safety threshold: below GitHub's 100 MiB hard block.
    if (( SIZE > 94371840 )); then
        fail "Release file exceeds 90 MiB: $FILE"
    fi

    case "$FILE" in
        *.gguf|*.safetensors|*.onnx|*.pt|*.pth|*.ckpt)
            fail "Model binary is eligible for commit: $FILE"
            ;;
    esac

    case "$FILE" in
        .env|*/.env|.env.*|*/.env.*)
            case "$FILE" in
                .env.example|*/.env.example)
                    ;;
                *)
                    fail "Real environment file is eligible for commit: $FILE"
                    ;;
            esac
            ;;
    esac

    # Only inspect text-like files with grep.
    if grep -Iq . "$FILE" 2>/dev/null; then
        SECRET_MATCHES="$(
            grep -nE \
                '-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' \
                "$FILE" 2>/dev/null || true
        )"

        if [[ -n "$SECRET_MATCHES" ]]; then
            fail "Possible private key or access token found: $FILE"
            printf '%s\n' "$SECRET_MATCHES"
        fi

        if ! is_path_allowlisted "$FILE"; then
            PATH_MATCHES="$(
                grep -nF "$INSTALL_ROOT_NEEDLE" \
                    "$FILE" 2>/dev/null || true
            )"

            if [[ -n "$PATH_MATCHES" ]]; then
                warn "Unexpected canonical install path found: $FILE"
                printf '%s\n' "$PATH_MATCHES"
            fi
        fi
    fi
done

# ------------------------------------------------------------
# Confirm models and large runtime data are not release files
# ------------------------------------------------------------

MODEL_RELEASE_FILES="$(
    printf '%s\n' "${RELEASE_FILES[@]}" \
        | grep -Ei '\.(gguf|safetensors|onnx|pt|pth|ckpt)$' \
        || true
)"

if [[ -z "$MODEL_RELEASE_FILES" ]]; then
    pass "No model binary is included in the release"
fi

LARGE_RELEASE_FILES=""

for FILE in "${RELEASE_FILES[@]}"; do
    SIZE="$(stat -c '%s' "$FILE")"

    if (( SIZE > 94371840 )); then
        LARGE_RELEASE_FILES+="${FILE}"$'\n'
    fi
done

if [[ -z "$LARGE_RELEASE_FILES" ]]; then
    pass "No release file exceeds 90 MiB"
fi

# BEGIN IMAGE LOCK VALIDATION

if [[ -x scripts/verify-image-lock.sh ]]; then
    if scripts/verify-image-lock.sh; then
        pass "Docker image lock is valid"
    else
        fail "Docker image lock is invalid"
    fi
else
    fail "Docker image-lock verifier is missing"
fi

# END IMAGE LOCK VALIDATION

# BEGIN INSTALLER VALIDATION

if [[ -x scripts/verify-build-lock.sh ]]; then
    if scripts/verify-build-lock.sh; then
        pass "Dockerfile base-image lock is valid"
    else
        fail "Dockerfile base-image lock is invalid"
    fi
else
    fail "Dockerfile build-lock verifier is missing"
fi

if [[ -x scripts/validate-installer.sh ]]; then
    if scripts/validate-installer.sh; then
        pass "Clean installer is valid"
    else
        fail "Clean installer is invalid"
    fi
else
    fail "Installer validator is missing"
fi

# END INSTALLER VALIDATION

# BEGIN MODEL MANIFEST VALIDATION

if [[ -x scripts/verify-model-manifest.sh ]]; then
    if scripts/verify-model-manifest.sh; then
        pass "Model download manifest is valid"
    else
        fail "Model download manifest is invalid"
    fi
else
    fail "Model-manifest verifier is missing"
fi

# END MODEL MANIFEST VALIDATION

# ------------------------------------------------------------
# Final result
# ------------------------------------------------------------

echo
echo "Audit summary:"
echo "  Errors:   $ERRORS"
echo "  Warnings: $WARNINGS"

if (( ERRORS > 0 )); then
    echo
    echo "RELEASE AUDIT FAILED"
    exit 1
fi

if (( WARNINGS > 0 )); then
    echo
    echo "RELEASE AUDIT PASSED WITH WARNINGS"
    exit 0
fi

echo
echo "RELEASE AUDIT PASSED"
