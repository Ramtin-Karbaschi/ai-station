#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/config/model-manifest.json"

cd "$ROOT"

echo "============================================================"
echo " AI Station - Model manifest verification"
echo "============================================================"

if [[ ! -f "$MANIFEST" ]]; then
    echo "FAIL: Model manifest is missing."
    exit 1
fi

python3 - "$MANIFEST" <<'PY'
from __future__ import annotations

import json
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])

manifest = json.loads(
    path.read_text(encoding="utf-8")
)

errors = []
models = manifest.get("models", [])

if manifest.get("schema_version") != 1:
    errors.append("Unsupported schema version")

if not models:
    errors.append("No models are defined")

required_fields = {
    "id",
    "role",
    "profiles",
    "repo_id",
    "filename",
    "destination",
    "revision",
    "sha256",
    "size_bytes",
}

ids = set()
destinations = set()
roles = set()

for model in models:
    model_id = model.get("id", "<unknown>")
    missing = required_fields - set(model)

    if missing:
        errors.append(
            f"{model_id}: missing fields {sorted(missing)}"
        )
        continue

    if model_id in ids:
        errors.append(f"Duplicate model id: {model_id}")

    ids.add(model_id)

    destination = model["destination"]

    if destination in destinations:
        errors.append(
            f"Duplicate destination: {destination}"
        )

    destinations.add(destination)
    roles.add(model["role"])

    if not re.fullmatch(
        r"[0-9a-f]{64}",
        model["sha256"],
    ):
        errors.append(
            f"{model_id}: invalid SHA-256"
        )

    if not re.fullmatch(
        r"[0-9a-f]{40,64}",
        model["revision"],
    ):
        errors.append(
            f"{model_id}: revision is not immutable"
        )

    if model.get("revision_is_immutable") is not True:
        errors.append(
            f"{model_id}: immutable revision flag is false"
        )

    if (
        not isinstance(model["size_bytes"], int)
        or model["size_bytes"] <= 0
    ):
        errors.append(
            f"{model_id}: invalid size"
        )

    pure_path = pathlib.PurePosixPath(destination)

    if pure_path.is_absolute():
        errors.append(
            f"{model_id}: destination must be relative"
        )

    if ".." in pure_path.parts:
        errors.append(
            f"{model_id}: destination escapes data root"
        )

    if not model["profiles"]:
        errors.append(
            f"{model_id}: no profile assigned"
        )

for required_role in {
    "general_reasoning",
    "embedding",
}:
    if required_role not in roles:
        errors.append(
            f"Missing required role: {required_role}"
        )

if errors:
    for error in errors:
        print(f"FAIL: {error}")

    print()
    print(f"Manifest errors: {len(errors)}")
    raise SystemExit(1)

print(f"OK: Models defined: {len(models)}")
print(f"OK: Unique roles: {len(roles)}")
print("OK: Every model uses an immutable revision.")
print("OK: Every model has a valid SHA-256 checksum.")
print("OK: Model destinations are data-root relative.")
PY

echo
echo "MODEL MANIFEST VERIFICATION PASSED"
