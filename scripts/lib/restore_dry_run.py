#!/usr/bin/env python3
"""Verify a station backup without applying it (Wave 0 / ADR disaster recovery)."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

BACKUP_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}$")
EXPECTED_FILES = (
    "ai_station_postgres.dump",
    "ai_station_files.tar.gz",
    "compose.yml",
    "env.example",
    "SHA256SUMS",
)
OPTIONAL_VOLUME_FILES = (
    "ai_station_openwebui_data.tar.gz",
    "openwebui_volume_manifest.json",
)
OPTIONAL_DATABASE_FILES = (
    "ai_station_litellm.dump",
    "database_backup_manifest.json",
)
PG_CUSTOM_MAGIC = b"PGDMP"
SHA256_LINE = re.compile(
    r"^([0-9a-fA-F]{64}) [ *](.+)$"
)


class RestoreError(RuntimeError):
    """A backup check failed."""


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def backups_root(root: Path | None = None) -> Path:
    return (root or data_root()) / "backups"


def is_station_backup(path: Path) -> bool:
    base_ok = (
        BACKUP_ID_RE.fullmatch(path.name) is not None
        and not path.is_symlink()
        and path.is_dir()
        and all(
            (path / name).is_file() and not (path / name).is_symlink()
            for name in EXPECTED_FILES
        )
    )
    optional_pairs = (OPTIONAL_VOLUME_FILES, OPTIONAL_DATABASE_FILES)
    pairs_ok = all(
        not any((path / name).exists() for name in pair)
        or all((path / name).is_file() and not (path / name).is_symlink() for name in pair)
        for pair in optional_pairs
    )
    if not (base_ok and pairs_ok):
        return False
    database_manifest = path / OPTIONAL_DATABASE_FILES[1]
    if database_manifest.is_file():
        try:
            payload = json.loads(database_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if payload.get("mode") == "complete" and not all(
            (path / name).is_file() and not (path / name).is_symlink()
            for name in OPTIONAL_VOLUME_FILES
        ):
            return False
    return True


def resolve_backup_dir(
    backup_id: str | None = None,
    *,
    root: Path | None = None,
) -> Path:
    base = backups_root(root)
    if backup_id:
        if not BACKUP_ID_RE.fullmatch(backup_id):
            raise RestoreError(
                "backup id must be YYYYMMDD-HHMMSS from ai backup"
            )
        candidate = base / backup_id
        if not candidate.is_dir():
            raise RestoreError(f"backup not found: {backup_id}")
        if not is_station_backup(candidate):
            raise RestoreError(
                f"{backup_id} is not an ai backup (missing dump, tar, or SHA256SUMS)"
            )
        return candidate
    if not base.is_dir():
        raise RestoreError(f"no backups directory: {base}")
    qualifying = sorted(
        (path for path in base.iterdir() if is_station_backup(path)),
        key=lambda path: path.name,
        reverse=True,
    )
    if not qualifying:
        raise RestoreError(
            f"no restorable ai backups under {base} "
            "(need dump, tar, compose.yml, env.example, SHA256SUMS)"
        )
    return qualifying[0]


def parse_sha256sums(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = SHA256_LINE.match(line)
        if not match:
            raise RestoreError(f"unreadable SHA256SUMS line: {line[:80]}")
        digest, listed = match.group(1).lower(), match.group(2).strip()
        mapping[Path(listed).name] = digest
    return mapping


def verify_checksums(backup_dir: Path) -> list[str]:
    errors: list[str] = []
    listed = parse_sha256sums(
        (backup_dir / "SHA256SUMS").read_text(encoding="utf-8")
    )
    names = EXPECTED_FILES + tuple(
        name for pair in (OPTIONAL_VOLUME_FILES, OPTIONAL_DATABASE_FILES)
        for name in pair if (backup_dir / name).exists()
    )
    for name in names:
        if name == "SHA256SUMS":
            continue
        path = backup_dir / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        expected = listed.get(name)
        if expected is None:
            errors.append(f"{name} not listed in SHA256SUMS")
        elif digest.hexdigest() != expected:
            errors.append(f"checksum mismatch: {name}")
    return errors


def inspect_volume_backup(backup_dir: Path) -> dict[str, Any] | None:
    archive = backup_dir / OPTIONAL_VOLUME_FILES[0]
    manifest = backup_dir / OPTIONAL_VOLUME_FILES[1]
    if not archive.exists() and not manifest.exists():
        return None
    info: dict[str, Any] = {"present": archive.is_file() and manifest.is_file()}
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        info["manifest_valid"] = (
            isinstance(payload, dict)
            and payload.get("schema") == 1
            and isinstance(payload.get("volume"), str)
            and isinstance(payload.get("sqlite_snapshots"), list)
            and isinstance(payload.get("sqlite_snapshot_count"), int)
            and payload.get("sqlite_snapshot_count") == len(payload.get("sqlite_snapshots"))
            and isinstance(payload.get("whisper_member_count"), int)
            and payload.get("whisper_member_count") > 0
        )
        info["sqlite_snapshot_count"] = payload.get("sqlite_snapshot_count")
    except (OSError, ValueError, TypeError):
        info["manifest_valid"] = False
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="ai-volume-dry-run-"))
        try:
            members = extract_archive(archive, temp_dir)
            info["archive_extractable"] = bool(members)
            info["archive_member_count"] = len(members)
            with tarfile.open(archive, "r:gz") as bundle:
                raw_members = bundle.getmembers()
            info["whisper_member_count_observed"] = sum(
                ("cache/whisper/" in name.lower())
                and bundle_member.isfile()
                and bundle_member.size > 0
                for bundle_member, name in zip(raw_members, members)
            )
            info["whisper_coverage_ok"] = (
                info["whisper_member_count_observed"] >= payload.get("whisper_member_count", 1)
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except (OSError, tarfile.TarError, RestoreError, EOFError):
        info["archive_extractable"] = False
        info["whisper_coverage_ok"] = False
    return info


def inspect_database_backup(
    backup_dir: Path,
    *,
    lister: DumpLister | None = None,
) -> dict[str, Any] | None:
    dump_path = backup_dir / OPTIONAL_DATABASE_FILES[0]
    manifest_path = backup_dir / OPTIONAL_DATABASE_FILES[1]
    if not dump_path.exists() and not manifest_path.exists():
        return None
    info: dict[str, Any] = {"present": dump_path.is_file() and manifest_path.is_file()}
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        started = str(payload.get("snapshot_started_utc", ""))
        finished = str(payload.get("snapshot_finished_utc", ""))
        try:
            timing_ok = (
                started.endswith("Z")
                and finished.endswith("Z")
                and dt.datetime.fromisoformat(started[:-1] + "+00:00")
                <= dt.datetime.fromisoformat(finished[:-1] + "+00:00")
            )
        except ValueError:
            timing_ok = False
        info["manifest_valid"] = (
            isinstance(payload, dict)
            and payload.get("schema") == 1
            and payload.get("mode") == "complete"
            and isinstance(payload.get("database"), str)
            and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", payload["database"]))
            and timing_ok
            and payload.get("artifacts") == list(("ai_station_postgres.dump", "ai_station_litellm.dump"))
        )
        info["database"] = payload.get("database")
        info["mode"] = payload.get("mode")
        info["snapshot_finished_utc"] = payload.get("snapshot_finished_utc")
    except (OSError, ValueError, TypeError):
        info["manifest_valid"] = False
    if dump_path.is_file():
        dump_info = inspect_dump(dump_path, lister=lister)
        info.update({f"dump_{key}": value for key, value in dump_info.items()})
    else:
        info.update({"dump_present": False, "dump_custom_format": False, "dump_toc_listed": False, "dump_toc_skipped": False})
    info["restorable"] = bool(
        info.get("present")
        and info.get("manifest_valid")
        and info.get("dump_custom_format")
        and (info.get("dump_toc_listed") or info.get("dump_toc_skipped"))
    )
    return info


def _unsafe_tar_member(member: tarfile.TarInfo, dest: Path) -> str | None:
    if member.issym() or member.islnk():
        return f"refusing link in archive: {member.name}"
    if not (member.isfile() or member.isdir()):
        return f"refusing special file in archive: {member.name}"
    target = (dest / member.name).resolve()
    dest_resolved = dest.resolve()
    if target != dest_resolved and dest_resolved not in target.parents:
        return f"unsafe tar member: {member.name}"
    return None


def extract_archive(tar_path: Path, dest: Path) -> list[str]:
    names: list[str] = []
    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive.getmembers():
            reason = _unsafe_tar_member(member, dest)
            if reason:
                raise RestoreError(reason)
            names.append(member.name)
        archive.extractall(dest)
    if not names:
        raise RestoreError("archive is empty")
    return names


DumpLister = Callable[[Path], tuple[int, str]]


def list_dump_pg_restore(dump_path: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["pg_restore", "-l", str(dump_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def list_dump_docker(dump_path: Path) -> tuple[int, str]:
    compose = project_root() / "scripts" / "compose-ai-station.sh"
    cmd: list[str]
    if compose.is_file():
        cmd = [str(compose), "exec", "-T", "postgres", "pg_restore", "-l"]
    else:
        cmd = ["docker", "compose", "exec", "-T", "postgres", "pg_restore", "-l"]
    try:
        with dump_path.open("rb") as handle:
            result = subprocess.run(
                cmd,
                check=False,
                stdin=handle,
                capture_output=True,
                timeout=60,
                cwd=str(project_root()),
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return 127, str(exc)
    output = (
        result.stdout.decode("utf-8", errors="replace")
        + result.stderr.decode("utf-8", errors="replace")
    )
    return result.returncode, output


def default_dump_lister(dump_path: Path) -> tuple[int, str]:
    code, output = list_dump_pg_restore(dump_path)
    if code != 127:
        return code, output
    return list_dump_docker(dump_path)


def inspect_dump(
    dump_path: Path,
    *,
    lister: DumpLister | None = None,
) -> dict[str, Any]:
    with dump_path.open("rb") as handle:
        payload = handle.read(len(PG_CUSTOM_MAGIC))
    present = bool(payload)
    magic_ok = payload.startswith(PG_CUSTOM_MAGIC)
    runner = lister or default_dump_lister
    code, output = runner(dump_path)
    listed = code == 0
    skipped = code == 127
    return {
        "present": present,
        "custom_format": magic_ok,
        "toc_listed": listed,
        "toc_skipped": skipped,
        "detail": output.strip()[:400],
    }


def dry_run(
    backup_dir: Path,
    *,
    dump_lister: DumpLister | None = None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "backup_dir": str(backup_dir),
        "backup_id": backup_dir.name,
    }
    checksum_errors = verify_checksums(backup_dir)
    checks["checksums_ok"] = not checksum_errors
    checks["checksum_errors"] = checksum_errors

    dump_info = inspect_dump(
        backup_dir / "ai_station_postgres.dump",
        lister=dump_lister,
    )
    checks["dump"] = dump_info
    volume_info = inspect_volume_backup(backup_dir)
    checks["openwebui_volume"] = volume_info
    database_info = inspect_database_backup(backup_dir, lister=dump_lister)
    checks["litellm_database"] = database_info

    tar_members: list[str] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="ai-restore-dry-run-"))
    try:
        tar_members = extract_archive(
            backup_dir / "ai_station_files.tar.gz",
            temp_dir,
        )
        checks["archive_extractable"] = True
        checks["archive_members"] = tar_members[:20]
        checks["archive_member_count"] = len(tar_members)
    except (RestoreError, tarfile.TarError, OSError, EOFError) as exc:
        checks["archive_extractable"] = False
        checks["archive_error"] = str(exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        checks["temp_dir_removed"] = not temp_dir.exists()

    dump_ok = bool(dump_info["present"] and dump_info["custom_format"]) and (
        dump_info["toc_listed"] or dump_info["toc_skipped"]
    )
    volume_ok = volume_info is None or bool(
        volume_info.get("present")
        and volume_info.get("manifest_valid")
        and volume_info.get("archive_extractable")
        and volume_info.get("whisper_coverage_ok")
    )
    database_ok = database_info is None or bool(database_info.get("restorable"))
    if database_info and database_info.get("mode") == "complete":
        database_ok = database_ok and volume_ok

    restorable = (
        checks["checksums_ok"]
        and checks["archive_extractable"]
        and checks["temp_dir_removed"]
        and dump_ok
        and volume_ok
        and database_ok
    )
    warnings: list[str] = []
    if database_info is None:
        warnings.append(
            "LiteLLM dump absent; accepted as a legacy backup without complete recovery coverage"
        )
    if dump_info["toc_skipped"] and dump_info["custom_format"]:
        warnings.append(
            "dump TOC not listed; pg_restore unavailable (magic+size accepted)"
        )
    checks["warnings"] = warnings
    checks["restorable"] = restorable
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the latest (or named) AI Station backup without restoring it."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Required. Never apply a restore from this command.",
    )
    parser.add_argument(
        "--id",
        dest="backup_id",
        default=None,
        help="Backup timestamp directory (YYYYMMDD-HHMMSS).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run:
        print(
            "ERROR: live restore is not implemented. Use: ai restore --dry-run",
            file=sys.stderr,
        )
        return 2
    try:
        backup_dir = resolve_backup_dir(args.backup_id)
        report = dry_run(backup_dir)
    except (RestoreError, OSError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "RESTORABLE" if report["restorable"] else "NOT RESTORABLE"
        print(f"{status}: {report['backup_dir']}")
        print(f"  checksums: {'ok' if report['checksums_ok'] else 'FAIL'}")
        dump = report["dump"]
        toc = "listed" if dump["toc_listed"] else (
            "skipped" if dump["toc_skipped"] else "FAIL"
        )
        print(
            "  dump: "
            f"present={dump['present']} custom={dump['custom_format']} toc={toc}"
        )
        database = report.get("litellm_database")
        if database is None:
            print("  litellm database: absent (legacy backup)")
        else:
            print(
                "  litellm database: "
                f"present={database.get('present')} manifest={database.get('manifest_valid')} "
                f"restorable={database.get('restorable')}"
            )
        print(
            "  archive: "
            f"{'extractable' if report['archive_extractable'] else 'FAIL'} "
            f"(temp removed={report['temp_dir_removed']})"
        )
        for warning in report.get("warnings") or []:
            print(f"  warning: {warning}")
        for error in report.get("checksum_errors") or []:
            print(f"  error: {error}")
        if report.get("archive_error"):
            print(f"  error: {report['archive_error']}")
    return 0 if report["restorable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
