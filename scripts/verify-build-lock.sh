#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/config/dockerfile-base-lock.json"

cd "$ROOT"

echo "============================================================"
echo " AI Station - Dockerfile build lock verification"
echo "============================================================"

if [[ ! -f "$MANIFEST" ]]; then
    echo "FAIL: Dockerfile base-image manifest is missing."
    exit 1
fi

python3 - "$ROOT" "$MANIFEST" <<'PY'
from __future__ import annotations

import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1]).resolve()
manifest_path = pathlib.Path(sys.argv[2])

manifest = json.loads(
    manifest_path.read_text(encoding="utf-8")
)

expected_entries = {
    (
        entry["dockerfile"],
        entry["line"],
        entry["locked"],
    )
    for entry in manifest.get("dockerfiles", [])
}

from_pattern = re.compile(
    r"^\s*FROM\s+"
    r"(?:--platform=\S+\s+)?"
    r"(?P<image>\S+)",
    re.IGNORECASE,
)

actual_entries = set()
errors = []

dockerfiles = sorted(
    path
    for path in root.rglob("Dockerfile*")
    if path.is_file()
    and ".git" not in path.parts
    and "_archive" not in path.parts
)

for dockerfile in dockerfiles:
    relative = dockerfile.relative_to(root).as_posix()

    for line_number, line in enumerate(
        dockerfile.read_text(
            encoding="utf-8"
        ).splitlines(),
        start=1,
    ):
        match = from_pattern.match(line)

        if not match:
            continue

        image = match.group("image")

        if image.lower() == "scratch":
            actual_entries.add(
                (relative, line_number, image)
            )
            continue

        if "$" in image:
            errors.append(
                f"{relative}:{line_number}: "
                f"dynamic FROM reference: {image}"
            )
            continue

        if "@sha256:" not in image:
            errors.append(
                f"{relative}:{line_number}: "
                f"base image is not digest-pinned: {image}"
            )
            continue

        actual_entries.add(
            (relative, line_number, image)
        )

missing_from_manifest = actual_entries - expected_entries
stale_manifest_entries = expected_entries - actual_entries

for item in sorted(missing_from_manifest):
    errors.append(
        "Dockerfile entry missing from manifest: "
        f"{item}"
    )

for item in sorted(stale_manifest_entries):
    errors.append(
        "Stale Dockerfile manifest entry: "
        f"{item}"
    )

if errors:
    for error in errors:
        print(f"FAIL: {error}")

    print()
    print(f"Build-lock errors: {len(errors)}")
    raise SystemExit(1)

print(
    "OK: Digest-pinned Dockerfile entries: "
    f"{len(actual_entries)}"
)
print("OK: Dockerfile build lock is valid.")
PY

echo
echo "BUILD LOCK VERIFICATION PASSED"
