#!/usr/bin/env python3
"""Deterministic OpenCode configuration and API contracts for AI Station."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "http://127.0.0.1:4000/v1"
MODELS = {
    "coder": "Qwen3-Coder-30B-A3B-Instruct-Q4",
    "general": "Qwen3.6-35B-A3B-UD-Q4_K_M",
    "reasoning": "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M",
    "ornith": "Ornith-1.5-35B-Q4_K_M",
}
EXPECTED = {
    MODELS["coder"]: (16384, 4096, True),
    MODELS["general"]: (8192, 2048, True),
    MODELS["reasoning"]: (8192, 2048, False),
    MODELS["ornith"]: (8192, 2048, True),
}
FORBIDDEN = (":8888", ":8083", ":11434", ":30890", ".gguf")


def parse_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    return json.loads(text)


def project_key(path: Path) -> str:
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


def request_json(
    path: str,
    *,
    key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 180,
    master: bool = False,
) -> dict[str, Any]:
    url = "http://127.0.0.1:4000" + path if master else API_BASE + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        if key:
            body = body.replace(key, "[redacted]")
        raise SystemExit(f"FAIL: HTTP {exc.code} on {url}: {body}") from exc


def validate_config(config_path: Path, template_dir: Path | None = None) -> None:
    text = config_path.read_text(encoding="utf-8")
    for needle in FORBIDDEN:
        if needle in text:
            raise SystemExit(f"FAIL: OpenCode config references {needle}")
    config = parse_jsonc(config_path)
    if config.get("enabled_providers") != ["ai-station"]:
        raise SystemExit("FAIL: enabled_providers must be ['ai-station']")
    providers = config.get("provider") or {}
    if set(providers) != {"ai-station"}:
        raise SystemExit("FAIL: exactly one provider named ai-station is required")
    station = providers["ai-station"]
    if (station.get("options") or {}).get("baseURL") != API_BASE:
        raise SystemExit(f"FAIL: baseURL must be {API_BASE}")
    models = station.get("models") or {}
    if set(models) != set(EXPECTED):
        raise SystemExit("FAIL: configured model set does not match AI Station")
    for model_id, (context, output, tools) in EXPECTED.items():
        meta = models[model_id]
        limit = meta.get("limit") or {}
        if (limit.get("context"), limit.get("output"), meta.get("tool_call")) != (
            context,
            output,
            tools,
        ):
            raise SystemExit(f"FAIL: capability contract mismatch for {model_id}")
    permissions = config.get("permission") or {}
    build = (config.get("agent") or {}).get("build") or {}
    build_permissions = build.get("permission") or {}
    if not (
        isinstance(config.get("lsp"), dict)
        and "pyright" in config["lsp"]
        and "bash" in config["lsp"]
        and isinstance(config.get("formatter"), dict)
        and "ruff" in config["formatter"]
        and "shfmt" in config["formatter"]
        and permissions.get("lsp") == "allow"
        and permissions.get("skill") == "allow"
        and permissions.get("attachment_read") == "allow"
        and build_permissions.get("edit") == "allow"
        and build_permissions.get("bash") == "allow"
        and build_permissions.get("attachment_read") == "allow"
        and int(build.get("steps") or 0) >= 32
    ):
        raise SystemExit("FAIL: OpenCode build agent lacks developer capabilities")
    compaction = config.get("compaction") or {}
    if set(compaction) != {"auto", "prune", "reserved"}:
        raise SystemExit("FAIL: compaction must use supported native fields only")
    if template_dir:
        required = [
            "AGENTS.md",
            "agents/build.md",
            "agents/plan.md",
            "agents/review.md",
            "agents/debug.md",
            "agents/station-ops.md",
            "commands/station-status.md",
            "commands/use-coder.md",
            "commands/use-general.md",
            "commands/use-reasoning.md",
            "commands/use-ornith.md",
            "commands/graphify.md",
            "plugins/graphify.js",
            "plugins/local-attachments.js",
        ]
        missing = [item for item in required if not (config_path.parent / item).is_file()]
        if missing:
            raise SystemExit("FAIL: missing managed assets: " + ", ".join(missing))


def command_key_ready(args: argparse.Namespace) -> int:
    return 0 if project_key(args.env_file) else 1


def command_sync_allowlist(args: argparse.Namespace) -> int:
    wanted = [item.strip() for item in args.models.split(",") if item.strip()]
    if args.dry_run:
        print("DRY-RUN: would update the OpenCode LiteLLM allowlist")
        return 0
    key = project_key(args.env_file)
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not key or not master_key:
        raise SystemExit("ERROR: OpenCode project key or LiteLLM master key is missing")
    response = request_json(
        "/key/update",
        key=master_key,
        payload={"key": key, "models": wanted},
        timeout=30,
        master=True,
    )
    print(
        "OK: updated LiteLLM OpenCode allowlist -> "
        + ", ".join(response.get("models") or wanted)
    )

    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("ERROR: PyYAML is required") from exc
    data = yaml.safe_load(args.registry.read_text(encoding="utf-8")) or {}
    projects = list(data.get("projects") or [])
    for project in projects:
        if project.get("id") == "opencode":
            project["models"] = wanted
            project["status"] = "active"
            break
    else:
        raise SystemExit(f"ERROR: project opencode missing from {args.registry}")
    data["projects"] = projects
    args.registry.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print("OK: synchronized the OpenCode project registry")
    return 0


def command_render(args: argparse.Namespace) -> int:
    template = args.template_dir / "opencode.jsonc.template"
    text = template.read_text(encoding="utf-8")
    for needle in FORBIDDEN:
        if needle in text:
            raise SystemExit(f"ERROR: template references forbidden value {needle}")
    if args.placeholder not in text or API_BASE not in text:
        raise SystemExit("ERROR: template placeholder or LiteLLM endpoint is missing")
    if args.dry_run:
        print(f"DRY-RUN: would render OpenCode config under {args.dest}")
        return 0
    key = project_key(args.env_file)
    if not key:
        raise SystemExit(f"ERROR: no usable LLM_API_KEY in {args.env_file}")
    rendered = text.replace(args.placeholder, key)
    args.dest.mkdir(parents=True, exist_ok=True)
    for rel in ("agents", "commands", "plugins"):
        (args.dest / rel).mkdir(parents=True, exist_ok=True)
    config_path = args.dest / "opencode.jsonc"
    credential_backups = list(args.dest.glob("opencode.jsonc.bak-*"))
    for backup in credential_backups:
        backup.unlink()
    if credential_backups:
        print(f"OK: removed {len(credential_backups)} stale credential backup(s)")
    temporary_config = args.dest / ".opencode.jsonc.tmp"
    temporary_config.write_text(rendered, encoding="utf-8")
    os.replace(temporary_config, config_path)
    shutil.copyfile(args.template_dir / "AGENTS.md", args.dest / "AGENTS.md")
    stale = [
        args.dest / "agents/compaction.md",
        args.dest / "plugins/disable-compaction-autocontinue.js",
    ]
    for path in stale:
        if path.is_file():
            path.unlink()
            print(f"OK: removed obsolete managed file {path}")
    for rel, pattern in (("agents", "*.md"), ("commands", "*.md"), ("plugins", "*.js")):
        for source in sorted((args.template_dir / rel).glob(pattern)):
            shutil.copyfile(source, args.dest / rel / source.name)
    validate_config(config_path, args.template_dir)
    print(f"OK: wrote and validated {config_path} (key redacted from logs)")
    return 0


def command_apply_profile(args: argparse.Namespace) -> int:
    validate_config(args.config)
    config = parse_jsonc(args.config)
    ref = f"ai-station/{MODELS[args.profile]}"
    config["model"] = ref
    config["small_model"] = ref
    temporary_config = args.config.with_name(".opencode.jsonc.tmp")
    temporary_config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_config, args.config)
    print(f"OK: OpenCode default -> {args.profile} ({ref})")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    validate_config(args.config, args.template_dir)
    print("OK: OpenCode config and managed developer assets are valid")
    return 0


def command_probe(args: argparse.Namespace) -> int:
    key = project_key(args.env_file)
    if not key:
        raise SystemExit("FAIL: OpenCode project key is missing")
    models = request_json("/models", key=key, timeout=30)
    ids = [item.get("id") for item in models.get("data") or []]
    if args.model not in ids:
        raise SystemExit(f"FAIL: project key cannot see {args.model}")
    print(f"OK: authenticated model listing includes {args.model}")
    chat = request_json(
        "/chat/completions",
        key=key,
        payload={
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a coding agent."},
                {"role": "user", "content": "Reply with the single word pong."},
            ],
            "max_tokens": 64,
            "temperature": 0,
        },
    )
    message = ((chat.get("choices") or [{}])[0].get("message") or {})
    if not (message.get("content") or message.get("tool_calls")):
        raise SystemExit("FAIL: chat returned no content or tool call")
    print(f"OK: short {args.profile} chat returned content")
    if args.profile == "reasoning":
        print("SKIP: reasoning profile is intentionally non-agentic")
        return 0
    tool_result = request_json(
        "/chat/completions",
        key=key,
        payload={
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a coding agent."},
                {"role": "user", "content": "Call get_time with timezone=UTC."},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "description": "Get current time",
                        "parameters": {
                            "type": "object",
                            "properties": {"timezone": {"type": "string"}},
                            "required": ["timezone"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
            "max_tokens": 128,
            "temperature": 0,
        },
    )
    tool_message = ((tool_result.get("choices") or [{}])[0].get("message") or {})
    if not tool_message.get("tool_calls"):
        raise SystemExit("FAIL: model returned no tool call")
    print("OK: tool-call probe returned get_time")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    key = sub.add_parser("key-ready")
    key.add_argument("--env-file", type=Path, required=True)
    key.set_defaults(func=command_key_ready)

    sync = sub.add_parser("sync-allowlist")
    sync.add_argument("--env-file", type=Path, required=True)
    sync.add_argument("--registry", type=Path, required=True)
    sync.add_argument("--models", required=True)
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=command_sync_allowlist)

    render = sub.add_parser("render")
    render.add_argument("--template-dir", type=Path, required=True)
    render.add_argument("--dest", type=Path, required=True)
    render.add_argument("--env-file", type=Path, required=True)
    render.add_argument("--placeholder", required=True)
    render.add_argument("--dry-run", action="store_true")
    render.set_defaults(func=command_render)

    profile = sub.add_parser("apply-profile")
    profile.add_argument("--config", type=Path, required=True)
    profile.add_argument("--profile", choices=sorted(MODELS), required=True)
    profile.set_defaults(func=command_apply_profile)

    validate = sub.add_parser("validate")
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument("--template-dir", type=Path, required=True)
    validate.set_defaults(func=command_validate)

    probe = sub.add_parser("probe")
    probe.add_argument("--env-file", type=Path, required=True)
    probe.add_argument("--profile", choices=sorted(MODELS), required=True)
    probe.add_argument("--model", required=True)
    probe.set_defaults(func=command_probe)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
