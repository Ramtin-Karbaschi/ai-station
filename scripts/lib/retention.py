#!/usr/bin/env python3
"""Chat and document TTL. Off until the operator enables it (Wave 0)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

DEFAULT_TTL_DAYS = 90
MAX_TTL_DAYS = 3650
TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chat", ("updated_at", "created_at")),
    ("file", ("updated_at", "created_at")),
    ("document", ("timestamp", "updated_at", "created_at")),
    ("document_chunk", ("created_at", "timestamp", "updated_at")),
    ("memory", ("updated_at", "created_at")),
)
EPOCH_TYPES = {"bigint", "integer", "smallint", "numeric"}
TIMESTAMP_TYPES = {
    "timestamp without time zone",
    "timestamp with time zone",
    "timestamp",
    "date",
}


class RetentionError(RuntimeError):
    """Retention configuration or apply failed."""


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def policy_path() -> Path:
    override = os.environ.get("AI_STATION_RETENTION_POLICY")
    if override:
        return Path(override)
    return data_root() / "runtime" / "retention.json"


@dataclass(frozen=True)
class RetentionPolicy:
    enabled: bool = False
    ttl_days: int = DEFAULT_TTL_DAYS

    def as_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "ttl_days": self.ttl_days}


def default_policy() -> RetentionPolicy:
    return RetentionPolicy(enabled=False, ttl_days=DEFAULT_TTL_DAYS)


def load_policy(path: Path | None = None) -> RetentionPolicy:
    target = path or policy_path()
    if not target.is_file():
        return default_policy()
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RetentionError(f"unreadable retention policy: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RetentionError("retention policy must be a JSON object")
    ttl = loaded.get("ttl_days", DEFAULT_TTL_DAYS)
    if not isinstance(ttl, int) or isinstance(ttl, bool):
        raise RetentionError("ttl_days must be an integer")
    if ttl < 1 or ttl > MAX_TTL_DAYS:
        raise RetentionError(f"ttl_days must be between 1 and {MAX_TTL_DAYS}")
    enabled = loaded.get("enabled", False)
    if not isinstance(enabled, bool):
        raise RetentionError("enabled must be a boolean")
    return RetentionPolicy(enabled=enabled, ttl_days=ttl)


def save_policy(policy: RetentionPolicy, path: Path | None = None) -> Path:
    target = path or policy_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(policy.as_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    target.chmod(0o600)
    return target


class SchemaCatalog(Protocol):
    def tables(self) -> Mapping[str, Mapping[str, str]]:
        """Map table name -> column name -> data_type."""


class Executor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Run SQL and return affected/count rows. Never log row bodies."""


@dataclass(frozen=True)
class PlannedPurge:
    table: str
    column: str
    sql: str
    params: tuple[Any, ...]
    skipped: str = ""


def _ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise RetentionError(f"refusing unsafe SQL identifier: {name}")
    return name


def cutoff_epoch(now: datetime, ttl_days: int) -> int:
    return int(now.timestamp()) - (ttl_days * 86400)


def plan_purges(
    catalog: SchemaCatalog,
    *,
    cutoff: int,
) -> list[PlannedPurge]:
    tables = catalog.tables()
    plans: list[PlannedPurge] = []
    for table, columns in TARGETS:
        info = tables.get(table)
        if info is None:
            plans.append(
                PlannedPurge(
                    table=table,
                    column="",
                    sql="",
                    params=(),
                    skipped="table missing",
                )
            )
            continue
        chosen = next((column for column in columns if column in info), "")
        if chosen:
            data_type = info[chosen].lower()
            table_sql = _ident(table)
            column_sql = _ident(chosen)
            if data_type in TIMESTAMP_TYPES:
                sql = (
                    f"FROM {table_sql} "
                    f"WHERE {column_sql} < to_timestamp(%s)"
                )
            elif data_type in EPOCH_TYPES:
                sql = f"FROM {table_sql} WHERE {column_sql} < %s"
            else:
                plans.append(
                    PlannedPurge(
                        table=table,
                        column=chosen,
                        sql="",
                        params=(),
                        skipped=f"unsupported type {data_type}",
                    )
                )
                continue
            plans.append(
                PlannedPurge(
                    table=table,
                    column=chosen,
                    sql=sql,
                    params=(cutoff,),
                )
            )
            continue
        if "metadata" in info:
            table_sql = _ident(table)
            sql = (
                f"FROM {table_sql} WHERE COALESCE("
                f"(metadata->>'created_at')::bigint, "
                f"(metadata->>'timestamp')::bigint"
                f") < %s"
            )
            plans.append(
                PlannedPurge(
                    table=table,
                    column="metadata",
                    sql=sql,
                    params=(cutoff,),
                )
            )
            continue
        plans.append(
            PlannedPurge(
                table=table,
                column="",
                sql="",
                params=(),
                skipped="no timestamp column",
            )
        )
    return plans


def apply_policy(
    policy: RetentionPolicy,
    catalog: SchemaCatalog,
    executor: Executor,
    *,
    now: datetime | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "enabled": policy.enabled,
        "ttl_days": policy.ttl_days,
        "deleted": {},
        "counted": {},
        "skipped": {},
        "applied": False,
    }
    if not policy.enabled:
        report["reason"] = "retention is off until the operator enables it"
        return report
    cutoff = cutoff_epoch(moment, policy.ttl_days)
    report["cutoff_epoch"] = cutoff
    for plan in plan_purges(catalog, cutoff=cutoff):
        if plan.skipped:
            report["skipped"][plan.table] = plan.skipped
            continue
        count_sql = "SELECT COUNT(*) " + plan.sql
        counted = executor.execute(count_sql, plan.params)
        report["counted"][plan.table] = counted
        if delete:
            delete_sql = (
                "WITH _d AS (DELETE " + plan.sql + " RETURNING 1) "
                "SELECT count(*) FROM _d"
            )
            deleted = executor.execute(delete_sql, plan.params)
            report["deleted"][plan.table] = deleted
        else:
            report["deleted"][plan.table] = 0
    report["applied"] = delete
    return report


class MappingCatalog:
    def __init__(self, tables: Mapping[str, Mapping[str, str]]) -> None:
        self._tables = tables

    def tables(self) -> Mapping[str, Mapping[str, str]]:
        return self._tables


class RecordingExecutor:
    """Test double. Returns scripted counts; records SQL without row bodies."""

    def __init__(self, counts: Mapping[str, int] | None = None) -> None:
        self.counts = dict(counts or {})
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.statements.append((sql, params))
        for table in self.counts:
            if re.search(rf"\b{_ident(table)}\b", sql):
                return self.counts[table]
        return 0


def _load_env_value(key: str) -> str:
    env_path = project_root() / ".env"
    try:
        if not env_path.is_file():
            return ""
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def docker_psql(sql: str, *, database: str | None = None) -> str:
    db_name = database or _load_env_value("POSTGRES_DB") or "openwebui"
    user = _load_env_value("POSTGRES_USER") or "openwebui"
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ai-station-postgres-1",
            "psql",
            "-U",
            user,
            "-d",
            db_name,
            "-v",
            "ON_ERROR_STOP=1",
            "-t",
            "-A",
            "-c",
            sql,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RetentionError(result.stderr.strip() or result.stdout.strip() or "psql failed")
    return result.stdout.strip()


class LiveCatalog:
    def tables(self) -> Mapping[str, Mapping[str, str]]:
        raw = docker_psql(
            "SELECT json_agg(json_build_object("
            "'table', table_name, 'column', column_name, 'type', data_type"
            ")) FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
        rows = json.loads(raw or "[]")
        tables: dict[str, dict[str, str]] = {}
        for row in rows or []:
            tables.setdefault(row["table"], {})[row["column"]] = row["type"]
        return tables


class LiveExecutor:
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        rendered = sql
        for value in params:
            if not isinstance(value, int):
                raise RetentionError("retention SQL only binds integers")
            rendered = rendered.replace("%s", str(value), 1)
        raw = docker_psql(rendered)
        if not raw:
            return 0
        try:
            return int(raw.splitlines()[0])
        except ValueError as exc:
            raise RetentionError("psql did not return a count") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Chat/document TTL. Off by default; default TTL is 90 days once enabled."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    enable = sub.add_parser("enable")
    enable.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    sub.add_parser("disable")
    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    command = args.command or "status"
    try:
        if command == "enable":
            policy = RetentionPolicy(enabled=True, ttl_days=args.ttl_days)
            if policy.ttl_days < 1 or policy.ttl_days > MAX_TTL_DAYS:
                raise RetentionError(
                    f"ttl_days must be between 1 and {MAX_TTL_DAYS}"
                )
            path = save_policy(policy)
            print(f"OK: retention enabled ttl_days={policy.ttl_days} ({path})")
            print("No rows deleted until: ai retention apply")
            return 0
        if command == "disable":
            current = load_policy()
            path = save_policy(
                RetentionPolicy(enabled=False, ttl_days=current.ttl_days)
            )
            print(f"OK: retention disabled ({path})")
            return 0
        policy = load_policy()
        if command == "status":
            print(
                json.dumps(
                    {
                        **policy.as_dict(),
                        "policy_path": str(policy_path()),
                        "default_ttl_days": DEFAULT_TTL_DAYS,
                    },
                    indent=2,
                )
            )
            return 0
        if command == "apply":
            if not policy.enabled:
                report = apply_policy(
                    policy,
                    MappingCatalog({}),
                    RecordingExecutor(),
                    delete=False,
                )
                print(json.dumps(report, indent=2))
                return 0
            catalog = LiveCatalog()
            executor = LiveExecutor()
            report = apply_policy(
                policy,
                catalog,
                executor,
                delete=not args.dry_run,
            )
            print(json.dumps(report, indent=2))
            return 0
        parser.error(f"unknown command: {command}")
        return 2
    except RetentionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
