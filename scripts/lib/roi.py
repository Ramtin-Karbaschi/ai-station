#!/usr/bin/env python3
"""One-page local vs cloud cost report from LiteLLM spend (Wave 3)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TARIFF = "config/tariffs/cloud-comparison.example.json"


class RoiError(RuntimeError):
    """ROI report failed."""


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


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


def load_tariff(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RoiError(f"cannot read tariff file: {path}") from exc
    if not isinstance(data, dict):
        raise RoiError("tariff file must be a JSON object")
    rate = data.get("cloud_usd_per_1k_tokens")
    try:
        cloud_rate = float(rate)
    except (TypeError, ValueError) as exc:
        raise RoiError("cloud_usd_per_1k_tokens must be a number") from exc
    if cloud_rate < 0:
        raise RoiError("cloud_usd_per_1k_tokens must be >= 0")
    local_rate = data.get("local_usd_per_1k_tokens", 0)
    try:
        local = float(local_rate)
    except (TypeError, ValueError) as exc:
        raise RoiError("local_usd_per_1k_tokens must be a number") from exc
    currency = str(data.get("currency") or "USD")
    label = str(data.get("label") or "Operator cloud comparison")
    return {
        "currency": currency,
        "label": label,
        "cloud_usd_per_1k_tokens": cloud_rate,
        "local_usd_per_1k_tokens": local,
        "notes": str(data.get("notes") or ""),
        "path": str(path),
    }


@dataclass(frozen=True)
class SpendTotals:
    tokens: int
    spend: float
    source: str


def totals_from_rows(rows: list[tuple[int, float]], *, source: str) -> SpendTotals:
    tokens = sum(item[0] for item in rows)
    spend = sum(item[1] for item in rows)
    return SpendTotals(tokens=tokens, spend=spend, source=source)


def probe_spend(*, days: int) -> SpendTotals:
    user = _load_env_value("POSTGRES_USER") or "openwebui"
    window = max(1, int(days))
    sql = (
        "SELECT COALESCE(SUM(s.total_tokens), 0)::bigint, "
        "COALESCE(SUM(s.spend), 0)::float "
        'FROM "LiteLLM_SpendLogs" s '
        f"WHERE s.\"startTime\" >= NOW() - INTERVAL '{window} days'"
    )
    try:
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
    except (OSError, subprocess.TimeoutExpired):
        return SpendTotals(tokens=0, spend=0.0, source="unavailable")
    if result.returncode != 0:
        return SpendTotals(tokens=0, spend=0.0, source="unavailable")
    line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    parts = line.split(",")
    if len(parts) != 2:
        return SpendTotals(tokens=0, spend=0.0, source="empty")
    try:
        tokens = int(float(parts[0]))
        spend = float(parts[1])
    except ValueError:
        return SpendTotals(tokens=0, spend=0.0, source="empty")
    return SpendTotals(tokens=tokens, spend=spend, source="LiteLLM_SpendLogs")


def build_report(
    totals: SpendTotals,
    tariff: dict[str, Any],
    *,
    days: int,
) -> dict[str, Any]:
    cloud_rate = float(tariff["cloud_usd_per_1k_tokens"])
    local_rate = float(tariff["local_usd_per_1k_tokens"])
    cloud_equivalent = (totals.tokens / 1000.0) * cloud_rate
    local_metered = (totals.tokens / 1000.0) * local_rate
    local_recorded = totals.spend if totals.spend > 0 else local_metered
    savings = cloud_equivalent - local_recorded
    return {
        "period_days": days,
        "tokens": totals.tokens,
        "spend_source": totals.source,
        "local_spend": round(local_recorded, 6),
        "cloud_equivalent": round(cloud_equivalent, 6),
        "savings": round(savings, 6),
        "currency": tariff["currency"],
        "tariff_label": tariff["label"],
        "cloud_usd_per_1k_tokens": cloud_rate,
        "local_usd_per_1k_tokens": local_rate,
        "tariff_path": tariff["path"],
        "notes": tariff["notes"],
        "requests_allowed": True,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"AI Station cost / ROI ({report['period_days']} days)",
        f"Tokens (LiteLLM): {report['tokens']}",
        f"Local spend: {report['local_spend']} {report['currency']} "
        f"(source={report['spend_source']})",
        f"Cloud equivalent: {report['cloud_equivalent']} {report['currency']} "
        f"at {report['cloud_usd_per_1k_tokens']}/1k tokens "
        f"({report['tariff_label']})",
        f"Estimated savings: {report['savings']} {report['currency']}",
        f"Tariff file: {report['tariff_path']}",
    ]
    if report.get("notes"):
        lines.append(str(report["notes"]))
    return "\n".join(lines)


def default_tariff_path() -> Path:
    override = os.environ.get("AI_STATION_TARIFF")
    if override:
        return Path(override)
    return project_root() / DEFAULT_TARIFF


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare LiteLLM spend to an operator-supplied cloud tariff."
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--tariff", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    tariff_path = Path(args.tariff) if args.tariff else default_tariff_path()
    try:
        tariff = load_tariff(tariff_path)
    except RoiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        totals = SpendTotals(tokens=0, spend=0.0, source="dry-run")
    else:
        totals = probe_spend(days=args.days)
    report = build_report(totals, tariff, days=args.days)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
