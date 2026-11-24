#!/usr/bin/env python3
"""Operator-selectable output roots for media, Graphify, and exports."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

KINDS = ("media", "graphify", "export")
SAFE_ABS = re.compile(r"^(/[A-Za-z0-9._-]+)+$")
PREFS_VERSION = 1


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def runtime_root() -> Path:
    return data_root() / "runtime"


def prefs_path() -> Path:
    override = os.environ.get("AI_STATION_OPERATOR_PREFS")
    if override:
        return Path(override)
    return runtime_root() / "operator-prefs.json"


def env_file_path() -> Path:
    override = os.environ.get("AI_STATION_OPERATOR_ENV")
    if override:
        return Path(override)
    return runtime_root() / "compose-operator.env"


def default_paths() -> dict[str, str]:
    runtime = runtime_root()
    return {
        "media": str(runtime / "comfyui" / "output"),
        "graphify": str(runtime / "graphify" / "ai-station"),
        "export": str(runtime / "exports"),
    }


def empty_prefs() -> dict[str, Any]:
    return {"version": PREFS_VERSION, "outputs": default_paths()}


def load_prefs() -> dict[str, Any]:
    path = prefs_path()
    if not path.is_file():
        return empty_prefs()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_prefs()
    if not isinstance(loaded, dict):
        return empty_prefs()
    outputs = loaded.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    merged = default_paths()
    for kind in KINDS:
        value = outputs.get(kind)
        if isinstance(value, str) and value.strip():
            merged[kind] = value.strip()
    return {"version": PREFS_VERSION, "outputs": merged}


def write_prefs(prefs: dict[str, Any]) -> None:
    path = prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_compose_env(prefs: dict[str, Any]) -> None:
    media = prefs["outputs"]["media"]
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"AI_STATION_COMFYUI_OUTPUT={media}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_path(kind: str, raw: str) -> Path:
    if not SAFE_ABS.match(raw):
        raise ValueError(
            "path must be absolute and use only letters, numbers, "
            "dot, underscore, hyphen, and slashes"
        )
    path = Path(raw).resolve()
    runtime = runtime_root()
    forbidden = (
        Path("/etc"),
        Path("/usr"),
        Path("/bin"),
        Path("/boot"),
        Path("/dev"),
        Path("/proc"),
        Path("/sys"),
        Path("/opt/ai-station/secrets"),
        data_root() / "models",
        data_root() / "quarantine",
        data_root() / "backups",
    )
    for parent in forbidden:
        if path == parent or is_under(path, parent):
            raise ValueError(f"refusing path under {parent}")
    if kind in ("media", "graphify"):
        if not is_under(path, runtime):
            raise ValueError(f"{kind} output must stay under {runtime}")
        return path
    if is_under(path, runtime):
        return path
    posix = path.as_posix()
    if posix.startswith("/mnt/") and "/users/" in posix.lower():
        lowered = posix.lower()
        if "/appdata/" in lowered or "/windows/" in lowered:
            raise ValueError("refusing Windows system folders")
        return path
    raise ValueError(
        "export path must stay under runtime or /mnt/<drive>/Users/..."
    )


def cmd_show() -> int:
    prefs = load_prefs()
    for kind in KINDS:
        print(f"{kind}: {prefs['outputs'][kind]}")
    print(f"prefs: {prefs_path()}")
    print(f"compose-env: {env_file_path()}")
    return 0


def cmd_path(kind: str) -> int:
    if kind not in KINDS:
        print(f"ERROR: unknown output kind: {kind}", file=sys.stderr)
        return 2
    print(load_prefs()["outputs"][kind])
    return 0


def cmd_set(kind: str, raw: str) -> int:
    if kind not in KINDS:
        print(f"ERROR: unknown output kind: {kind}", file=sys.stderr)
        return 2
    try:
        path = validate_path(kind, raw)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    path.mkdir(parents=True, exist_ok=True)
    prefs = load_prefs()
    prefs["outputs"][kind] = str(path)
    write_prefs(prefs)
    write_compose_env(prefs)
    print(f"OK: {kind} -> {path}")
    if kind == "media":
        print(
            "Restart comfyui-media-experimental if it is running "
            "so the bind mount moves."
        )
    return 0


def cmd_ensure() -> int:
    prefs = load_prefs()
    for kind in KINDS:
        Path(prefs["outputs"][kind]).mkdir(parents=True, exist_ok=True)
    write_compose_env(prefs)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    path_cmd = sub.add_parser("path")
    path_cmd.add_argument("kind", choices=KINDS)
    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("kind", choices=KINDS)
    set_cmd.add_argument("path")
    sub.add_parser("ensure")
    args = parser.parse_args(argv)
    if args.command == "show":
        return cmd_show()
    if args.command == "path":
        return cmd_path(args.kind)
    if args.command == "set":
        return cmd_set(args.kind, args.path)
    if args.command == "ensure":
        return cmd_ensure()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
