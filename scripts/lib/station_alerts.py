#!/usr/bin/env python3
"""Lean local alerts: usage (ADR-033) and health (ADR-034). Never rate-cap."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUESTS_ALWAYS_ALLOWED = True
USAGE_MULTIPLIER = 3.0
USAGE_FLOOR_TOKENS = 1_000_000
USAGE_MIN_DAYS = 3
DISK_THRESHOLD_PERCENT = 85.0
MAX_ALERT_BYTES = 262144
MAX_ALERT_AGE_HOURS = 72
ALWAYS_ON_SERVICES = (
    "postgres",
    "redis",
    "searxng",
    "tika",
    "embedder",
    "reranker",
    "llm-gateway",
    "open-webui",
    "asr-qwen3",
)
OOM_PATTERN = re.compile(
    r"cuda(?:error)?(?:memoryallocation)?|"
    r"cuda out of memory|"
    r"out of memory.*cuda|"
    r"ggml_cuda.*(?:out of memory|failed)|"
    r"cudaErrorMemoryAllocation",
    re.IGNORECASE,
)
FORBIDDEN_ALERT_TEXT = re.compile(
    r"\b(prompt|messages|content|completion|response_text)\b",
    re.IGNORECASE,
)


class AlertError(RuntimeError):
    """Alert evaluation failed."""


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def alerts_dir(root: Path | None = None) -> Path:
    override = os.environ.get("AI_STATION_ALERTS_DIR")
    if override:
        return Path(override)
    return (root or data_root()) / "runtime" / "alerts"


def alerts_path(root: Path | None = None) -> Path:
    return alerts_dir(root) / "alerts.jsonl"


def state_path(root: Path | None = None) -> Path:
    return alerts_dir(root) / "state.json"


@dataclass(frozen=True)
class DailyUsage:
    key_id: str
    day: str
    tokens: int


@dataclass(frozen=True)
class Alert:
    kind: str
    fired_at: str
    subject: str
    message: str

    def as_dict(self) -> dict[str, str]:
        payload = asdict(self)
        if FORBIDDEN_ALERT_TEXT.search(payload["message"]):
            payload["message"] = f"{self.kind} signal (details redacted)"
        return payload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).date().isoformat()


def load_state(path: Path | None = None) -> dict[str, Any]:
    target = path or state_path()
    if not target.is_file():
        return {"last_fired": {}}
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"last_fired": {}}
    if not isinstance(loaded, dict):
        return {"last_fired": {}}
    last_fired = loaded.get("last_fired", {})
    if not isinstance(last_fired, dict):
        last_fired = {}
    return {"last_fired": last_fired}


def save_state(state: dict[str, Any], path: Path | None = None) -> None:
    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)


def should_fire_usage(
    today_tokens: int,
    prior_tokens: list[int],
    *,
    multiplier: float = USAGE_MULTIPLIER,
    floor: int = USAGE_FLOOR_TOKENS,
    min_days: int = USAGE_MIN_DAYS,
) -> tuple[bool, int]:
    if len(prior_tokens) >= min_days:
        mean = sum(prior_tokens) / len(prior_tokens)
        threshold = int(max(floor, mean * multiplier))
    else:
        threshold = floor
    return today_tokens > threshold, threshold


def usage_alerts(
    series: Iterable[DailyUsage],
    *,
    today: str,
    last_fired: Mapping[str, str] | None = None,
    multiplier: float = USAGE_MULTIPLIER,
    floor: int = USAGE_FLOOR_TOKENS,
) -> list[Alert]:
    by_key: dict[str, dict[str, int]] = defaultdict(dict)
    for row in series:
        by_key[row.key_id][row.day] = row.tokens
    fired_map = dict(last_fired or {})
    alerts: list[Alert] = []
    for key_id, days in sorted(by_key.items()):
        today_tokens = int(days.get(today, 0))
        prior = [tokens for day, tokens in days.items() if day < today]
        prior.sort()
        fire, threshold = should_fire_usage(
            today_tokens,
            prior,
            multiplier=multiplier,
            floor=floor,
        )
        if not fire:
            continue
        dedupe_key = f"usage:{key_id}"
        if fired_map.get(dedupe_key) == today:
            continue
        alerts.append(
            Alert(
                kind="usage",
                fired_at=f"{today}T00:00:00+00:00",
                subject=key_id,
                message=(
                    f"key {key_id} used {today_tokens} tokens "
                    f"(threshold {threshold}, ~{multiplier:g}x daily mean or floor)"
                ),
            )
        )
    return alerts


def disk_alert(
    percent_used: float,
    *,
    today: str,
    last_fired: Mapping[str, str] | None = None,
    threshold: float = DISK_THRESHOLD_PERCENT,
) -> Alert | None:
    if percent_used < threshold:
        return None
    if (last_fired or {}).get("disk") == today:
        return None
    return Alert(
        kind="disk",
        fired_at=f"{today}T00:00:00+00:00",
        subject="disk",
        message=(
            f"disk usage {percent_used:.1f}% is at or above {threshold:.0f}%"
        ),
    )


def oom_alerts(
    hits: Mapping[str, int],
    *,
    today: str,
    last_fired: Mapping[str, str] | None = None,
) -> list[Alert]:
    alerts: list[Alert] = []
    fired_map = last_fired or {}
    for name, count in sorted(hits.items()):
        if count < 1:
            continue
        dedupe = f"oom:{name}"
        if fired_map.get(dedupe) == today:
            continue
        alerts.append(
            Alert(
                kind="oom",
                fired_at=f"{today}T00:00:00+00:00",
                subject=name,
                message=f"CUDA OOM pattern matched {count} time(s) in {name}",
            )
        )
    return alerts


def container_alerts(
    statuses: Mapping[str, str],
    *,
    today: str,
    last_fired: Mapping[str, str] | None = None,
    required: tuple[str, ...] = ALWAYS_ON_SERVICES,
) -> list[Alert]:
    alerts: list[Alert] = []
    fired_map = last_fired or {}
    for name in required:
        state = statuses.get(name, "missing")
        running = state.lower() in {"running", "healthy", "up"}
        if running:
            continue
        dedupe = f"container:{name}"
        if fired_map.get(dedupe) == today:
            continue
        alerts.append(
            Alert(
                kind="container",
                fired_at=f"{today}T00:00:00+00:00",
                subject=name,
                message=f"always-on container {name} is {state}",
            )
        )
    return alerts


def requests_allowed(_alert_would_fire: bool = False) -> bool:
    return REQUESTS_ALWAYS_ALLOWED


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or alerts_path()
    if not target.is_file():
        return []
    records: list[dict[str, Any]] = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def prune_records(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_age_hours: int = MAX_ALERT_AGE_HOURS,
    max_bytes: int = MAX_ALERT_BYTES,
) -> list[dict[str, Any]]:
    moment = now or _utc_now()
    cutoff = moment - timedelta(hours=max_age_hours)
    kept: list[dict[str, Any]] = []
    for record in records:
        fired = str(record.get("fired_at", ""))
        try:
            parsed = datetime.fromisoformat(fired.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed >= cutoff:
            kept.append(record)

    def encoded_size(items: list[dict[str, Any]]) -> int:
        if not items:
            return 0
        return len(
            ("\n".join(json.dumps(item, separators=(",", ":")) for item in items)
             + "\n").encode("utf-8")
        )

    while kept and encoded_size(kept) > max_bytes:
        kept.pop(0)
    return kept


def write_records(
    records: list[dict[str, Any]],
    *,
    path: Path | None = None,
    now: datetime | None = None,
    max_age_hours: int = MAX_ALERT_AGE_HOURS,
    max_bytes: int = MAX_ALERT_BYTES,
) -> list[dict[str, Any]]:
    target = path or alerts_path()
    pruned = prune_records(
        records,
        now=now,
        max_age_hours=max_age_hours,
        max_bytes=max_bytes,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(item, separators=(",", ":")) + "\n" for item in pruned
    )
    target.write_text(payload, encoding="utf-8")
    target.chmod(0o600)
    return pruned


def persist_alerts(
    alerts: list[Alert],
    *,
    path: Path | None = None,
    state_file: Path | None = None,
    today: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    target = path or alerts_path()
    moment = now or _utc_now()
    day = today or _day_key(moment)
    existing = load_records(target)
    existing.extend(alert.as_dict() for alert in alerts)
    pruned = write_records(existing, path=target, now=moment)
    state_target = state_file or (target.parent / "state.json")
    current_state = load_state(state_target)
    last_fired = dict(current_state.get("last_fired") or {})
    for alert in alerts:
        last_fired[f"{alert.kind}:{alert.subject}"] = day
        if alert.kind == "disk":
            last_fired["disk"] = day
    save_state({"last_fired": last_fired}, path=state_target)
    return pruned


def evaluate(
    *,
    usage: Iterable[DailyUsage] | None = None,
    disk_percent: float | None = None,
    oom_hits: Mapping[str, int] | None = None,
    container_statuses: Mapping[str, str] | None = None,
    today: str | None = None,
    last_fired: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    moment_day = today or _day_key(_utc_now())
    fired = last_fired or load_state()["last_fired"]
    alerts: list[Alert] = []
    if usage is not None:
        alerts.extend(
            usage_alerts(usage, today=moment_day, last_fired=fired)
        )
    if disk_percent is not None:
        disk = disk_alert(disk_percent, today=moment_day, last_fired=fired)
        if disk:
            alerts.append(disk)
    if oom_hits is not None:
        alerts.extend(oom_alerts(oom_hits, today=moment_day, last_fired=fired))
    if container_statuses is not None:
        alerts.extend(
            container_alerts(
                container_statuses,
                today=moment_day,
                last_fired=fired,
            )
        )
    return {
        "alerts": [alert.as_dict() for alert in alerts],
        "requests_allowed": requests_allowed(bool(alerts)),
        "today": moment_day,
    }


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


def probe_disk_percent(path: Path | None = None) -> float:
    usage = shutil.disk_usage(str(path or data_root()))
    if usage.total <= 0:
        return 0.0
    return (usage.used / usage.total) * 100.0


def probe_usage_series() -> list[DailyUsage]:
    user = _load_env_value("POSTGRES_USER") or "openwebui"
    sql = (
        "SELECT COALESCE(v.key_alias, left(s.api_key, 8)) AS key_id, "
        "to_char((s.\"startTime\" AT TIME ZONE 'UTC')::date, 'YYYY-MM-DD') AS day, "
        "SUM(s.total_tokens)::bigint AS tokens "
        'FROM "LiteLLM_SpendLogs" s '
        'LEFT JOIN "LiteLLM_VerificationToken" v ON v.token = s.api_key '
        "WHERE s.\"startTime\" >= NOW() - INTERVAL '14 days' "
        "GROUP BY 1, 2 ORDER BY 1, 2"
    )
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
            "litellm",
            "-v",
            "ON_ERROR_STOP=1",
            "-t",
            "-A",
            "-F",
            ",",
            "-c",
            sql,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    rows: list[DailyUsage] = []
    for line in result.stdout.splitlines():
        parts = line.split(",")
        if len(parts) != 3:
            continue
        key_id, day, tokens = parts
        if not key_id or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            continue
        try:
            count = int(tokens)
        except ValueError:
            continue
        rows.append(DailyUsage(key_id=key_id, day=day, tokens=count))
    return rows


def probe_containers() -> dict[str, str] | None:
    compose = project_root() / "scripts" / "compose-ai-station.sh"
    cmd = [str(compose), "ps", "-a", "--format", "json"]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    statuses: dict[str, str] = {}
    blob = result.stdout.strip()
    if not blob:
        return statuses
    if blob.startswith("["):
        try:
            items = json.loads(blob)
        except ValueError:
            return None
    else:
        items = []
        for line in blob.splitlines():
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Service") or item.get("Name") or "")
        state = str(item.get("State") or item.get("Status") or "")
        if name:
            statuses[name] = state
    return statuses


def probe_oom_hits(statuses: Mapping[str, str] | None) -> dict[str, int]:
    hits: dict[str, int] = {}
    names = [
        name
        for name, state in (statuses or {}).items()
        if state.lower() in {"running", "healthy", "up"}
        and (
            name.startswith("llm-")
            or name in {"comfyui-experimental", "llm-gateway"}
        )
    ]
    for name in names:
        result = subprocess.run(
            [
                str(project_root() / "scripts" / "compose-ai-station.sh"),
                "logs",
                "--tail",
                "200",
                name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root()),
        )
        text = (result.stdout or "") + (result.stderr or "")
        count = len(OOM_PATTERN.findall(text))
        if count:
            hits[name] = count
    return hits


def live_evaluate() -> tuple[list[Alert], dict[str, Any]]:
    today = _day_key(_utc_now())
    last_fired = load_state()["last_fired"]
    notes: dict[str, Any] = {"requests_allowed": True}
    try:
        usage = probe_usage_series()
        notes["usage_rows"] = len(usage)
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
        usage = []
        notes["usage_rows"] = 0
        notes["usage_error"] = type(exc).__name__
    try:
        disk = probe_disk_percent()
        notes["disk_percent"] = round(disk, 2)
    except OSError as exc:
        disk = None
        notes["disk_error"] = type(exc).__name__
    try:
        statuses = probe_containers()
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        statuses = None
    if statuses is None:
        notes["containers"] = "unavailable"
        oom: dict[str, int] = {}
        container_input: Mapping[str, str] | None = None
    else:
        notes["containers"] = len(statuses)
        container_input = statuses
        try:
            oom = probe_oom_hits(statuses)
        except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            oom = {}
            notes["oom_error"] = "unavailable"
    notes["oom_sources"] = sorted(oom)
    report = evaluate(
        usage=usage,
        disk_percent=disk,
        oom_hits=oom,
        container_statuses=container_input,
        today=today,
        last_fired=last_fired,
    )
    alerts = [
        Alert(
            kind=item["kind"],
            fired_at=item["fired_at"],
            subject=item["subject"],
            message=item["message"],
        )
        for item in report["alerts"]
    ]
    notes["alert_count"] = len(alerts)
    return alerts, notes


def summary_text(path: Path | None = None, *, hours: int = 24) -> str:
    records = load_records(path)
    cutoff = _utc_now() - timedelta(hours=hours)
    recent = 0
    for record in records:
        try:
            parsed = datetime.fromisoformat(
                str(record.get("fired_at", "")).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed >= cutoff:
            recent += 1
    return f"Alerts ({hours}h): {recent} (ai alerts)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lean local usage and health alerts. Never rejects requests."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "command",
        nargs="?",
        default="check",
        choices=("check", "summary"),
    )
    args = parser.parse_args(argv)
    if args.command == "summary":
        print(summary_text())
        return 0
    alerts, notes = live_evaluate()
    payload = {
        "alerts": [alert.as_dict() for alert in alerts],
        "requests_allowed": True,
        "dry_run": args.dry_run,
        "notes": notes,
        "store_bytes_cap": MAX_ALERT_BYTES,
        "store_age_hours": MAX_ALERT_AGE_HOURS,
    }
    if not args.dry_run:
        try:
            persist_alerts(alerts)
            payload["stored"] = True
        except OSError:
            payload["stored"] = False
            notes["store_error"] = "unwritable"
    else:
        payload["stored"] = False
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"alerts={len(alerts)} requests_allowed=yes "
            f"disk={notes.get('disk_percent')}% stored={payload['stored']}"
        )
        for alert in alerts:
            print(f"  {alert.kind} {alert.subject}: {alert.message}")
        if not alerts:
            print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
