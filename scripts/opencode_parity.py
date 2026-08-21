#!/usr/bin/env python3
"""Report the verified OpenCode agentic-development contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    doctor_process = subprocess.run(
        [sys.executable, str(ROOT / "scripts/opencode_doctor.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        doctor = json.loads(doctor_process.stdout)
    except json.JSONDecodeError:
        print(doctor_process.stdout + doctor_process.stderr, file=sys.stderr)
        return 1

    live_status = "not_run"
    live_output = ""
    if args.live and doctor_process.returncode == 0:
        live = subprocess.run(
            [
                str(ROOT / "scripts/ai"),
                "opencode",
                "acceptance",
                "--timeout",
                str(args.timeout),
            ],
            capture_output=True,
            text=True,
            timeout=args.timeout + 90,
        )
        live_status = "passed" if live.returncode == 0 else "failed"
        live_output = (live.stdout + live.stderr).strip()

    check_names = {item["name"] for item in doctor.get("checks", []) if item["passed"]}
    capabilities = [
        {"capability": "repository search, read, edit, patch, and shell", "status": "verified" if live_status == "passed" else "configured"},
        {"capability": "multi-file implementation and test execution", "status": "verified" if live_status == "passed" else "requires --live"},
        {"capability": "Python and Bash LSP, formatting, and lint toolchain", "status": "verified" if "language_toolchain" in check_names else "failed"},
        {"capability": "project rules, skills, agents, subagents, and commands", "status": "verified" if {"project_skills", "managed_extensions"}.issubset(check_names) else "failed"},
        {"capability": "filesystem snapshots and native compaction", "status": "verified" if {"developer_tools", "native_compaction"}.issubset(check_names) else "failed"},
        {"capability": "VS Code editor bridge from WSL", "status": "verified" if "ide_bridge" in check_names else "failed"},
        {"capability": "MCP and plugin extension surface", "status": "available; no MCP server enabled"},
    ]
    non_equivalents = [
        "Proprietary editor tab completion is out of scope.",
        "Cloud-hosted background agents are out of scope; AI Station remains local-first.",
        "Commercial GitHub review bots are out of scope.",
        "OpenCode uses its TUI and IDE extension rather than a third-party editor-native interface.",
    ]
    usable = doctor_process.returncode == 0 and live_status != "failed"
    if doctor_process.returncode != 0 or live_status == "failed":
        contract_status = "not_ready"
    elif live_status == "passed":
        contract_status = "verified"
    else:
        contract_status = "configured"
    result = {
        "status": contract_status,
        "doctor": doctor,
        "live_acceptance": live_status,
        "capabilities": capabilities,
        "intentional_non_equivalents": non_equivalents,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"OpenCode agentic-development contract: {result['status']}")
        for item in capabilities:
            print(f"{item['status'].upper()}: {item['capability']}")
        print("Intentional product non-equivalences:")
        for item in non_equivalents:
            print(f"- {item}")
        if live_output:
            print("Live acceptance evidence:")
            print(live_output)
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
