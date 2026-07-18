#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

python3 - "$ROOT" <<'PY'
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()

result = subprocess.run(
    [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "*.md",
    ],
    cwd=root,
    check=True,
    stdout=subprocess.PIPE,
)

files = [
    root / raw.decode("utf-8")
    for raw in result.stdout.split(b"\0")
    if raw
]

fence_pattern = re.compile(
    r"^(?P<fence>`{3,}|~{3,})mermaid[ \t]*\n"
    r"(?P<body>.*?)"
    r"^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

unsafe_pattern = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_-]*"
    r"\[/[^\]\r\n]+\]"
)

errors: list[str] = []
diagram_count = 0

for path in files:
    if not path.is_file():
        continue

    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root)

    for match in fence_pattern.finditer(text):
        diagram_count += 1

        for unsafe in unsafe_pattern.finditer(
            match.group("body")
        ):
            offset = (
                match.start("body")
                + unsafe.start()
            )

            line = text.count(
                "\n",
                0,
                offset,
            ) + 1

            errors.append(
                f"{relative}:{line}: "
                f"{unsafe.group(0)}"
            )

if errors:
    for error in errors:
        print(f"FAIL: {error}")

    print()
    print(f"Mermaid errors: {len(errors)}")
    raise SystemExit(1)

print(f"OK: Mermaid diagrams checked: {diagram_count}")
print("OK: Mermaid path labels are safely quoted.")
PY

echo "MERMAID VERIFICATION PASSED"
