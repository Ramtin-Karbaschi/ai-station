#!/usr/bin/env python3
"""Safe, manifest-driven inventory and quarantine lifecycle for model files."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MUTABLE_REVISIONS = {"main", "master", "HEAD", "latest"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def manifest_model(manifest: dict[str, Any], model_id: str) -> dict[str, Any]:
    matches = [model for model in manifest.get("models", []) if model["id"] == model_id]
    if not matches:
        raise SystemExit(f"ERROR: unknown model id: {model_id}")
    return matches[0]


def model_path(data_root: Path, model: dict[str, Any]) -> Path:
    models_root = (data_root / "models").resolve()
    path = (data_root / model["destination"]).resolve()
    if path != models_root and models_root not in path.parents:
        raise SystemExit(f"ERROR: manifest destination escapes models root: {path}")
    return path


def active_profile(data_root: Path) -> str:
    marker = data_root / "runtime/active-heavy-profile"
    return marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""


def profile_for_model(root: Path, model_id: str) -> str:
    catalog = load_json(root / "config/model-catalog.json")
    for model in catalog.get("models", []):
        if model.get("manifest_id") == model_id:
            return str(model.get("profile") or "")
    return ""


def records(data_root: Path, model_id: str | None = None) -> list[dict[str, Any]]:
    record_root = data_root / "quarantine/models"
    found: list[dict[str, Any]] = []
    if not record_root.is_dir():
        return found
    for path in sorted(record_root.rglob("*.quarantine.json"), reverse=True):
        try:
            record = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        record["record_path"] = str(path)
        if model_id is None or record.get("model_id") == model_id:
            found.append(record)
    return found


def catalog(root: Path, data_root: Path, as_json: bool) -> None:
    manifest = load_json(root / "config/model-manifest.json")
    rows = []
    for model in manifest.get("models", []):
        path = model_path(data_root, model)
        rows.append(
            {
                "id": model["id"],
                "role": model["role"],
                "profiles": model["profiles"],
                "required": bool(model.get("required_for_runtime")),
                "installed": path.is_file(),
                "size_bytes": model["size_bytes"],
                "path": str(path),
                "quarantined_versions": len(records(data_root, model["id"])),
            }
        )
    if as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return
    for row in rows:
        state = "installed" if row["installed"] else "missing"
        required = "core" if row["required"] else "optional"
        print(
            f"{row['id']:<42} {state:<9} {required:<8} "
            f"{row['size_bytes'] / (1024**3):>6.2f} GiB"
        )


def quarantine(
    root: Path,
    data_root: Path,
    model_id: str,
    confirm: bool,
    allow_required: bool,
) -> None:
    manifest = load_json(root / "config/model-manifest.json")
    model = manifest_model(manifest, model_id)
    source = model_path(data_root, model)
    if not source.is_file():
        raise SystemExit(f"ERROR: model is not installed: {source}")
    profile = profile_for_model(root, model_id)
    active = active_profile(data_root)
    if profile and profile == active:
        raise SystemExit(
            f"ERROR: {model_id} backs active profile '{active}'. Run 'ai models stop' first."
        )
    if model.get("required_for_runtime") and not allow_required:
        raise SystemExit(
            "ERROR: refusing to quarantine a required core model without --allow-required"
        )

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    relative = source.relative_to((data_root / "models").resolve())
    destination = data_root / "quarantine/models" / stamp / relative
    record_path = destination.with_name(destination.name + ".quarantine.json")
    print(f"Model:       {model_id}")
    print(f"Source:      {source}")
    print(f"Quarantine:  {destination}")
    print(f"Restore:     ai models restore {model_id} --confirm")
    if not confirm:
        print("DRY-RUN: add --confirm to perform the recoverable move")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    record = {
        "schema_version": 1,
        "model_id": model_id,
        "source": str(source),
        "destination": str(destination),
        "quarantined_at": stamp,
        "restored_at": None,
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.chmod(record_path, 0o600)
    print("OK: model moved to recoverable quarantine")


def restore(root: Path, data_root: Path, model_id: str, confirm: bool) -> None:
    manifest = load_json(root / "config/model-manifest.json")
    model = manifest_model(manifest, model_id)
    destination = model_path(data_root, model)
    if destination.exists():
        raise SystemExit(f"ERROR: destination already exists: {destination}")
    candidates = [record for record in records(data_root, model_id) if not record["restored_at"]]
    if not candidates:
        raise SystemExit(f"ERROR: no unrestored quarantine record for {model_id}")
    record = candidates[0]
    source = Path(record["destination"])
    if not source.is_file():
        raise SystemExit(f"ERROR: quarantined file is missing: {source}")
    print(f"Model:       {model_id}")
    print(f"Source:      {source}")
    print(f"Restore to:  {destination}")
    if not confirm:
        print("DRY-RUN: add --confirm to restore")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    record["restored_at"] = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    Path(record["record_path"]).write_text(
        json.dumps({k: v for k, v in record.items() if k != "record_path"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("OK: model restored from quarantine")


def planned_entry(
    model_id: str,
    repo_id: str,
    filename: str,
    role: str,
    revision: str,
    destination: str,
    size_bytes: int,
    sha256: str,
) -> dict[str, Any]:
    return {
        "destination": destination,
        "filename": filename,
        "id": model_id,
        "profiles": ["custom"],
        "repo_id": repo_id,
        "required_for_runtime": False,
        "revision": revision,
        "revision_is_immutable": True,
        "role": role,
        "sha256": sha256.lower(),
        "size_bytes": size_bytes,
    }


def add_model(
    root: Path,
    model_id: str,
    repo_id: str,
    filename: str,
    role: str,
    revision: str,
    destination: str | None,
    size_bytes: int | None,
    sha256: str | None,
    confirm: bool,
) -> None:
    if not MODEL_ID_RE.match(model_id):
        raise SystemExit("ERROR: invalid model id")
    if not repo_id or "/" not in repo_id:
        raise SystemExit("ERROR: --repo must look like org/name")
    if not filename or "/" in filename or filename in {".", ".."}:
        raise SystemExit("ERROR: --filename must be a single file name")
    if not role:
        raise SystemExit("ERROR: --role is required")
    if not revision or revision in MUTABLE_REVISIONS:
        raise SystemExit("ERROR: --revision must be an immutable commit SHA, not a branch name")
    relative = destination or f"models/custom/{filename}"
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise SystemExit("ERROR: --destination must be a relative path under models/")
    if not relative.startswith("models/"):
        raise SystemExit("ERROR: --destination must start with models/")

    manifest_path = root / "config/model-manifest.json"
    manifest = load_json(manifest_path)
    existing = {model["id"] for model in manifest.get("models", [])}
    if model_id in existing:
        raise SystemExit(
            f"ERROR: model id already exists: {model_id}. Use: ai models install {model_id}"
        )

    entry = planned_entry(
        model_id,
        repo_id,
        filename,
        role,
        revision,
        relative,
        size_bytes or 0,
        sha256 or ("0" * 64),
    )
    print(f"Model:       {model_id}")
    print(f"Repository:  {repo_id}")
    print(f"Revision:    {revision}")
    print(f"Filename:    {filename}")
    print(f"Role:        {role}")
    print(f"Destination: {relative}")
    print("Next:        ai models install " + model_id)
    print(
        "Then update config/model-catalog.json, config/providers.yaml, "
        "and config/gateway/litellm.yaml if this model should be a runtime profile."
    )
    if not confirm:
        print("DRY-RUN: add --confirm --sha256 <64-hex> --size-bytes N to write the manifest")
        return
    if not size_bytes or size_bytes <= 0:
        raise SystemExit("ERROR: --size-bytes is required with --confirm")
    if not sha256 or not SHA256_RE.match(sha256):
        raise SystemExit("ERROR: --sha256 must be a 64-character hex digest")
    entry["size_bytes"] = size_bytes
    entry["sha256"] = sha256.lower()
    manifest.setdefault("models", []).append(entry)
    profiles = manifest.setdefault("profiles", {})
    profiles.setdefault(
        "custom",
        {"description": "Operator-registered models that are not part of core or all."},
    )
    dump_json(manifest_path, manifest)
    print("OK: manifest entry written. Download with: ai models install " + model_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--data-root", default=os.getenv("AI_STATION_DATA", "/srv/ai-station"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--json", action="store_true")
    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--id", required=True, dest="model_id")
    add_parser.add_argument("--repo", required=True, dest="repo_id")
    add_parser.add_argument("--filename", required=True)
    add_parser.add_argument("--role", required=True)
    add_parser.add_argument("--revision", required=True)
    add_parser.add_argument("--destination")
    add_parser.add_argument("--sha256")
    add_parser.add_argument("--size-bytes", type=int)
    add_parser.add_argument("--confirm", action="store_true")
    for name in ("quarantine", "restore"):
        command = subparsers.add_parser(name)
        command.add_argument("model_id")
        command.add_argument("--confirm", action="store_true")
        if name == "quarantine":
            command.add_argument("--allow-required", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    data_root = Path(args.data_root).resolve()

    if args.command == "catalog":
        catalog(root, data_root, args.json)
    elif args.command == "add":
        add_model(
            root,
            args.model_id,
            args.repo_id,
            args.filename,
            args.role,
            args.revision,
            args.destination,
            args.size_bytes,
            args.sha256,
            args.confirm,
        )
    elif args.command == "quarantine":
        quarantine(root, data_root, args.model_id, args.confirm, args.allow_required)
    else:
        restore(root, data_root, args.model_id, args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
