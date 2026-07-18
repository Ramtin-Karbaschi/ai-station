#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

echo "============================================================"
echo " AI Station - Documentation quality audit"
echo "============================================================"

python3 - "$ROOT" <<'PY'
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()

required_files = [
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs/README_FA.md",
    "docs/ARCHITECTURE.md",
    "docs/INSTALLATION.md",
    "docs/IMAGE_LOCK.md",
    "docs/MODELS.md",
    "docs/OPERATIONS.md",
    "docs/PORTABILITY_POLICY.md",
    "docs/TROUBLESHOOTING.md",
    "docs/ops/AI_STATION_CURRENT_STATE.md",
    "docs/assets/ai-station-banner.svg",
]

errors: list[str] = []

for relative in required_files:
    path = root / relative

    if not path.is_file():
        errors.append(
            f"Required file is missing: {relative}"
        )
    elif path.stat().st_size == 0:
        errors.append(
            f"Required file is empty: {relative}"
        )

readme_path = root / "README.md"

if readme_path.is_file():
    readme_text = readme_path.read_text(
        encoding="utf-8"
    )

    required_readme_fragments = [
        "docs/assets/ai-station-banner.svg",
        "## Overview",
        "## Architecture",
        "## Quick start",
        "## Security",
        "## Documentation",
        "[MIT License](LICENSE)",
        "docs/README_FA.md",
    ]

    for fragment in required_readme_fragments:
        if fragment not in readme_text:
            errors.append(
                "README is missing required content: "
                f"{fragment}"
            )

license_path = root / "LICENSE"

if license_path.is_file():
    license_text = license_path.read_text(
        encoding="utf-8"
    )

    required_license_fragments = [
        "MIT License",
        "Copyright (c) 2026 Ramtin Karbaschi",
    ]

    for fragment in required_license_fragments:
        if fragment not in license_text:
            errors.append(
                f"LICENSE is missing: {fragment}"
            )

notice_path = root / "NOTICE.md"

if notice_path.is_file():
    notice_text = notice_path.read_text(
        encoding="utf-8"
    )

    if "Copyright © 2026 Ramtin Karbaschi" not in notice_text:
        errors.append(
            "NOTICE.md is missing the copyright notice"
        )

result = subprocess.run(
    [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ],
    cwd=root,
    check=True,
    stdout=subprocess.PIPE,
)

release_candidates = [
    item.decode("utf-8")
    for item in result.stdout.split(b"\0")
    if item
]

markdown_files = sorted(
    root / relative
    for relative in release_candidates
    if pathlib.PurePosixPath(relative).suffix.lower() == ".md"
    and (root / relative).is_file()
)

link_pattern = re.compile(
    r"!?\[[^\]]*\]\(([^)]+)\)"
)

for path in markdown_files:
    relative = path.relative_to(root)

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(
            f"Invalid UTF-8 Markdown file: {relative}"
        )
        continue

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if line.rstrip() != line:
            errors.append(
                "Trailing whitespace: "
                f"{relative}:{line_number}"
            )

    for raw_target in link_pattern.findall(text):
        target = raw_target.strip()

        if not target:
            continue

        if " " in target and not target.startswith("<"):
            target = target.split(" ", 1)[0]

        target = target.strip("<>")

        if not target:
            continue

        if target.startswith(
            (
                "http://",
                "https://",
                "mailto:",
                "#",
                "data:",
            )
        ):
            continue

        target_without_fragment = target.split(
            "#",
            1,
        )[0]

        if not target_without_fragment:
            continue

        resolved = (
            path.parent / target_without_fragment
        ).resolve()

        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(
                "Link escapes repository: "
                f"{relative} -> {target}"
            )
            continue

        if not resolved.exists():
            errors.append(
                "Broken relative link: "
                f"{relative} -> {target}"
            )

support_candidates = [
    relative
    for relative in release_candidates
    if relative == "support"
    or relative.startswith("support/")
]

if support_candidates:
    for relative in support_candidates:
        errors.append(
            "Generated support artifact is included "
            f"in the release candidate set: {relative}"
        )

if errors:
    for error in errors:
        print(f"FAIL: {error}")

    print()
    print(f"Documentation errors: {len(errors)}")
    raise SystemExit(1)

print(
    "OK: Required documentation files: "
    f"{len(required_files)}"
)

print(
    "OK: Release-candidate Markdown files checked: "
    f"{len(markdown_files)}"
)

print(
    "OK: Ignored diagnostic and support files "
    "were excluded."
)

print(
    "OK: Relative documentation links are valid."
)

print(
    "OK: License and copyright notice are present."
)

print(
    "OK: README structure and visual identity "
    "are present."
)
PY

# BEGIN MERMAID VALIDATION

"$ROOT/scripts/verify-mermaid.sh"

# END MERMAID VALIDATION

git diff --check

echo "OK: Git whitespace validation passed."

echo
echo "DOCUMENTATION AUDIT PASSED"
