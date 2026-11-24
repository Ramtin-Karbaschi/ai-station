#!/usr/bin/env python3
"""Catalog review overlay: last-evaluated date and lifecycle status."""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATUSES = ("active", "retiring", "experimental", "unreviewed")
DEFAULT_STALE_DAYS = 180
REVIEW_RELATIVE = "config/catalog-review.json"
MANIFEST_RELATIVE = "config/model-manifest.json"


class CatalogReviewError(RuntimeError):
    """Catalog review failed."""


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def review_path() -> Path:
    override = os.environ.get("AI_STATION_CATALOG_REVIEW")
    if override:
        return Path(override)
    return project_root() / REVIEW_RELATIVE


def manifest_path() -> Path:
    override = os.environ.get("AI_STATION_MODEL_MANIFEST")
    if override:
        return Path(override)
    return project_root() / MANIFEST_RELATIVE


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogReviewError(f"cannot read {path}") from exc
    if not isinstance(data, dict):
        raise CatalogReviewError(f"{path} must be a JSON object")
    return data


def load_overlay(path: Path | None = None) -> dict[str, Any]:
    target = path or review_path()
    if not target.is_file():
        return {"version": 1, "stale_days": DEFAULT_STALE_DAYS, "reviews": {}}
    data = load_json(target)
    reviews = data.get("reviews") or {}
    if not isinstance(reviews, dict):
        reviews = {}
    prefixes = data.get("status_by_prefix") or []
    if not isinstance(prefixes, list):
        prefixes = []
    stale = data.get("stale_days", DEFAULT_STALE_DAYS)
    try:
        stale_days = int(stale)
    except (TypeError, ValueError):
        stale_days = DEFAULT_STALE_DAYS
    return {
        "version": data.get("version", 1),
        "stale_days": stale_days,
        "reviews": reviews,
        "status_by_prefix": prefixes,
    }


def manifest_ids(path: Path | None = None) -> list[str]:
    data = load_json(path or manifest_path())
    models = data.get("models") or []
    ids: list[str] = []
    for model in models:
        if isinstance(model, dict) and model.get("id"):
            ids.append(str(model["id"]))
    return ids


def _prefix_match(model_id: str, overlay: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_len = -1
    for item in overlay.get("status_by_prefix") or []:
        if not isinstance(item, dict):
            continue
        prefix = str(item.get("prefix") or "")
        if prefix and model_id.startswith(prefix) and len(prefix) > best_len:
            best = item
            best_len = len(prefix)
    return best


@dataclass(frozen=True)
class Review:
    model_id: str
    status: str
    last_evaluated: str | None
    note: str
    stale: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_review(
    model_id: str,
    overlay: dict[str, Any],
    *,
    today: date | None = None,
) -> Review:
    moment = today or datetime.now(timezone.utc).date()
    stale_days = int(overlay.get("stale_days") or DEFAULT_STALE_DAYS)
    reviews = overlay.get("reviews") or {}
    raw = reviews.get(model_id) if isinstance(reviews, dict) else None
    source = "unreviewed"
    status = "unreviewed"
    last_evaluated: str | None = None
    note = ""
    if isinstance(raw, dict):
        source = "explicit"
        status = str(raw.get("status") or "unreviewed")
        last_evaluated = str(raw["last_evaluated"]) if raw.get("last_evaluated") else None
        note = str(raw.get("note") or "")
    else:
        matched = _prefix_match(model_id, overlay)
        if matched:
            source = "prefix"
            status = str(matched.get("status") or "unreviewed")
            last_evaluated = (
                str(matched["last_evaluated"]) if matched.get("last_evaluated") else None
            )
            note = str(matched.get("note") or "")
    if status not in STATUSES:
        status = "unreviewed"
    parsed = _parse_day(last_evaluated)
    stale = False
    if parsed is None:
        stale = status != "unreviewed"
    else:
        stale = parsed < (moment - timedelta(days=stale_days))
        last_evaluated = parsed.isoformat()
    return Review(
        model_id=model_id,
        status=status,
        last_evaluated=last_evaluated,
        note=note,
        stale=stale,
        source=source,
    )


def before_replace(
    model_id: str,
    overlay: dict[str, Any],
    *,
    allow_experimental: bool = False,
    today: date | None = None,
) -> tuple[bool, list[str]]:
    review = resolve_review(model_id, overlay, today=today)
    reasons: list[str] = []
    if review.status == "unreviewed":
        reasons.append("no last-evaluated review; record one in config/catalog-review.json")
    if review.status == "retiring":
        reasons.append("status is retiring; do not use as a replacement")
    if review.status == "experimental" and not allow_experimental:
        reasons.append("status is experimental; pass --allow-experimental only for that class")
    if review.stale:
        reasons.append(
            f"last_evaluated {review.last_evaluated or 'missing'} is stale "
            f"(>{overlay.get('stale_days', DEFAULT_STALE_DAYS)} days)"
        )
    return (not reasons, reasons)


def list_reviews(
    overlay: dict[str, Any],
    ids: list[str],
    *,
    today: date | None = None,
) -> list[Review]:
    return [resolve_review(model_id, overlay, today=today) for model_id in ids]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show catalog review status before replacing a model."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--before-replace")
    parser.add_argument("--allow-experimental", action="store_true")
    args = parser.parse_args(argv)
    try:
        overlay = load_overlay()
        ids = manifest_ids()
    except CatalogReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.before_replace:
        ok, reasons = before_replace(
            args.before_replace,
            overlay,
            allow_experimental=args.allow_experimental,
        )
        review = resolve_review(args.before_replace, overlay)
        payload = {
            "ok": ok,
            "review": review.as_dict(),
            "reasons": reasons,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"{review.model_id}: status={review.status} "
                f"last_evaluated={review.last_evaluated or 'none'} "
                f"stale={str(review.stale).lower()}"
            )
            if ok:
                print("OK: catalog review allows replacement planning")
            else:
                for reason in reasons:
                    print(f"BLOCKED: {reason}")
        return 0 if ok else 2
    rows = [item.as_dict() for item in list_reviews(overlay, ids)]
    if args.json:
        print(json.dumps({"stale_days": overlay.get("stale_days"), "models": rows}, indent=2))
        return 0
    print(
        f"{'id':<48} {'status':<14} {'last_evaluated':<14} stale"
    )
    for row in rows:
        print(
            f"{row['model_id']:<48} {row['status']:<14} "
            f"{(row['last_evaluated'] or '-'):<14} {str(row['stale']).lower()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
