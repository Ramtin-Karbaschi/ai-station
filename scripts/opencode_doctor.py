#!/usr/bin/env python3
"""Read-only OpenCode developer-environment diagnostics for AI Station."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MANIFEST = ROOT / "config/clients/opencode/runtime.json"
TOOLCHAIN_MANIFEST = ROOT / "config/clients/opencode/toolchain.json"
MODEL_REF = "ai-station/Qwen3-Coder-30B-A3B-Instruct-Q4"
API_BASE = "http://127.0.0.1:4000/v1"


def parse_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    return json.loads(text)


def read_project_key(path: Path) -> str:
    if not path.is_file():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "LLM_API_KEY":
            value = value.strip().strip('"').strip("'")
            return "" if value == "REVOKED" else value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    runtime = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    toolchain = json.loads(TOOLCHAIN_MANIFEST.read_text(encoding="utf-8"))
    dev_user = os.environ.get("AI_STATION_DEV_USER", runtime["developer_user"])
    checks: list[dict[str, str | bool]] = []

    def check(name: str, passed: bool, evidence: str) -> None:
        checks.append({"name": name, "passed": passed, "evidence": evidence})

    try:
        account = pwd.getpwnam(dev_user)
    except KeyError:
        account = None
    check(
        "non_root_developer",
        bool(account and account.pw_uid != 0),
        f"user={dev_user}, uid={account.pw_uid if account else 'missing'}",
    )

    binary = Path("/usr/local/bin/opencode")
    installed_version = "missing"
    if binary.exists():
        result = subprocess.run(
            [str(binary), "--version"], capture_output=True, text=True, timeout=15
        )
        installed_version = result.stdout.strip() if result.returncode == 0 else "error"
    check(
        "pinned_runtime",
        installed_version == runtime["version"],
        f"installed={installed_version}, pinned={runtime['version']}",
    )

    service = subprocess.run(
        ["systemctl", "is-active", "ai-station-opencode.service"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    server_health = False
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:4096/global/health", timeout=5
        ) as response:
            server_health = response.status == 200
    except (OSError, urllib.error.HTTPError):
        pass
    listeners = subprocess.run(
        ["ss", "-ltn", "sport = :4096"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    loopback_only = "127.0.0.1:4096" in listeners and "0.0.0.0:4096" not in listeners
    check(
        "desktop_wsl_server",
        service.stdout.strip() == "active" and server_health and loopback_only,
        f"service={service.stdout.strip() or 'inactive'}, health={server_health}, loopback_only={loopback_only}",
    )

    home = Path(account.pw_dir) if account else Path("/nonexistent")
    config_path = home / ".config/opencode/opencode.jsonc"
    try:
        config = parse_jsonc(config_path)
    except (OSError, ValueError) as exc:
        config = {}
        check("valid_config", False, f"{config_path}: {exc}")
    else:
        check("valid_config", True, str(config_path))

    provider = (config.get("provider") or {}).get("ai-station") or {}
    options = provider.get("options") or {}
    check(
        "litellm_boundary",
        options.get("baseURL") == API_BASE,
        f"baseURL={options.get('baseURL')!r}",
    )
    models = provider.get("models") or {}
    coder = models.get("Qwen3-Coder-30B-A3B-Instruct-Q4") or {}
    check(
        "coder_contract",
        bool(coder.get("tool_call"))
        and (coder.get("limit") or {}).get("context") == 16384
        and (coder.get("limit") or {}).get("output") >= 4096,
        f"tool_call={coder.get('tool_call')}, limit={coder.get('limit')}",
    )
    permissions = config.get("permission") or {}
    build = (config.get("agent") or {}).get("build") or {}
    build_permissions = build.get("permission") or {}
    lsp = config.get("lsp") or {}
    formatter = config.get("formatter") or {}
    check(
        "developer_tools",
        isinstance(lsp, dict)
        and {"pyright", "bash"}.issubset(lsp)
        and isinstance(formatter, dict)
        and {"ruff", "shfmt"}.issubset(formatter)
        and config.get("snapshot") is True
        and permissions.get("lsp") == "allow"
        and permissions.get("skill") == "allow"
        and build_permissions.get("edit") == "allow"
        and build_permissions.get("bash") == "allow"
        and build_permissions.get("task") == "allow"
        and int(build.get("steps") or 0) >= 32,
        "LSP/formatters/snapshots enabled; build edit/bash/task allowed; steps="
        + str(build.get("steps")),
    )

    required_tools = (
        "bash-language-server",
        "pyright-langserver",
        "ruff",
        "shellcheck",
        "shfmt",
    )
    missing_tools = [name for name in required_tools if not shutil.which(name)]
    check(
        "language_toolchain",
        not missing_tools,
        "missing=" + (",".join(missing_tools) if missing_tools else "none"),
    )

    editor_commands = [name for name in ("code",) if shutil.which(name)]
    editor_usable = False
    if editor_commands:
        editor_probe = subprocess.run(
            [editor_commands[0], "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        editor_usable = editor_probe.returncode == 0
    extension_id, extension_version = toolchain["vscode_extension"].split("@", 1)
    extension_paths = list(
        Path("/mnt/c/Users").glob(
            f"*/.vscode/extensions/{extension_id}-{extension_version}"
        )
    )
    check(
        "ide_bridge",
        bool(editor_commands) and editor_usable and bool(extension_paths),
        "commands="
        + (",".join(editor_commands) if editor_commands else "none")
        + f", extension={'installed' if extension_paths else 'missing'}",
    )
    compaction = config.get("compaction") or {}
    unsupported = sorted(set(compaction) & {"tail_turns", "preserve_recent_tokens"})
    obsolete_files = [
        home / ".config/opencode/agents/compaction.md",
        home / ".config/opencode/plugins/disable-compaction-autocontinue.js",
    ]
    check(
        "native_compaction",
        compaction.get("auto") is True
        and not unsupported
        and not any(path.exists() for path in obsolete_files),
        f"keys={sorted(compaction)}, obsolete_files={sum(p.exists() for p in obsolete_files)}",
    )

    skill_paths = ((config.get("skills") or {}).get("paths") or [])
    skill_dirs = sorted((ROOT / "config/skills").glob("*/SKILL.md"))
    check(
        "project_skills",
        str(ROOT / "config/skills") in skill_paths and len(skill_dirs) >= 3,
        f"discoverable_skills={len(skill_dirs)}",
    )

    asset_counts = {
        "agents": len(list((home / ".config/opencode/agents").glob("*.md"))),
        "commands": len(list((home / ".config/opencode/commands").glob("*.md"))),
        "plugins": len(list((home / ".config/opencode/plugins").glob("*.js"))),
    }
    check(
        "managed_extensions",
        asset_counts["agents"] >= 5
        and asset_counts["commands"] >= 6
        and asset_counts["plugins"] >= 1,
        ", ".join(f"{name}={count}" for name, count in asset_counts.items()),
    )

    key = read_project_key(ROOT / "projects/opencode.env")
    model_ids: list[str] = []
    if key:
        request = urllib.request.Request(
            API_BASE + "/models", headers={"Authorization": f"Bearer {key}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
                model_ids = [item.get("id", "") for item in payload.get("data") or []]
        except (OSError, ValueError, urllib.error.HTTPError):
            pass
    check(
        "authenticated_model_access",
        bool(key) and MODEL_REF.split("/", 1)[1] in model_ids,
        f"key={'present' if key else 'missing'}, visible_models={len(model_ids)}",
    )

    passed = sum(bool(item["passed"]) for item in checks)
    result = {
        "status": "ready" if passed == len(checks) else "not_ready",
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for item in checks:
            prefix = "OK" if item["passed"] else "FAIL"
            print(f"{prefix}: {item['name']} — {item['evidence']}")
        print(f"OpenCode developer environment: {result['status']} ({passed}/{len(checks)})")
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
