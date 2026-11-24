#!/usr/bin/env python3
"""ComfyUI prompt filter and hashed audit log. Never stores raw prompts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_AUDIT_BYTES = 262144
MAX_AUDIT_AGE_HOURS = 72
MAX_PROMPT_CHARS = 8192
SKIP_NODE_TYPES = frozenset(
    {
        "MarkdownNote",
        "Note",
        "n8n-nodes-base.stickyNote",
    }
)
TEXT_KEYS = frozenset(
    {
        "text",
        "prompt",
        "positive",
        "negative",
        "lyrics",
        "caption",
        "prompt_text",
    }
)
FILENAME_RE = re.compile(
    r"\.(gguf|safetensors|ckpt|pt|bin|json|png|jpg|jpeg|wav|mp3)$",
    re.IGNORECASE,
)
DENY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("csam", re.compile(r"\bcsam\b", re.IGNORECASE)),
    (
        "sexual-content-involving-minors",
        re.compile(
            r"\b(child|minor|underage)\b.{0,48}\b(sex|sexual|porn|nude|naked)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "sexual-content-involving-minors",
        re.compile(
            r"\b(sex|sexual|porn|nude|naked)\b.{0,48}\b(child|minor|underage)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "child-pornography",
        re.compile(r"\bchild\s+porn", re.IGNORECASE),
    ),
)
FORBIDDEN_AUDIT_TEXT = re.compile(
    r"\b(prompt|lyrics|caption|messages|content|completion)\b",
    re.IGNORECASE,
)


class MediaGuardError(RuntimeError):
    """Prompt filter failed."""


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def audit_dir(root: Path | None = None) -> Path:
    override = os.environ.get("AI_STATION_MEDIA_AUDIT_DIR")
    if override:
        return Path(override)
    return (root or data_root()) / "runtime" / "media" / "audit"


def audit_path(root: Path | None = None) -> Path:
    return audit_dir(root) / "prompts.jsonl"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_prompt(text: str) -> str:
    normalized = " ".join(text.split()).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _looks_like_prompt(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    if stripped.startswith("##"):
        return False
    if FILENAME_RE.search(stripped) and " " not in stripped:
        return False
    if "\n" not in stripped and " " not in stripped:
        return False
    return True


def _walk_prompts(value: Any, *, skip_notes: bool = True) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        node_type = str(value.get("type") or value.get("class_type") or "")
        if skip_notes and node_type in SKIP_NODE_TYPES:
            return found
        for key, item in value.items():
            if str(key) in TEXT_KEYS and isinstance(item, str) and _looks_like_prompt(item):
                found.append(item)
            else:
                found.extend(_walk_prompts(item, skip_notes=skip_notes))
        named = value.get("widgets_values_named")
        if isinstance(named, dict):
            for key in TEXT_KEYS:
                item = named.get(key)
                if isinstance(item, str) and _looks_like_prompt(item):
                    found.append(item)
        widgets = value.get("widgets_values")
        if isinstance(widgets, list):
            for item in widgets:
                if isinstance(item, str) and _looks_like_prompt(item):
                    found.append(item)
        return found
    if isinstance(value, list):
        for item in value:
            found.extend(_walk_prompts(item, skip_notes=skip_notes))
    return found


def extract_prompts(payload: Any) -> list[str]:
    texts = _walk_prompts(payload)
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        key = " ".join(text.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def classify(text: str) -> tuple[str, str | None]:
    if len(text) > MAX_PROMPT_CHARS:
        return "deny", "max_length"
    for rule, pattern in DENY_PATTERNS:
        if pattern.search(text):
            return "deny", rule
    return "allow", None


@dataclass(frozen=True)
class GuardResult:
    decision: str
    source: str
    prompt_count: int
    hashes: tuple[str, ...]
    rule: str | None
    checked_at: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hashes"] = list(self.hashes)
        message = json.dumps(payload)
        if FORBIDDEN_AUDIT_TEXT.search(message) and "prompt_count" in payload:
            # Record shape is fixed; reject accidental raw-prompt fields.
            payload.pop("text", None)
            payload.pop("prompt", None)
        return payload


def evaluate(
    payload: Any,
    *,
    source: str,
    now: datetime | None = None,
) -> GuardResult:
    moment = now or _utc_now()
    texts = extract_prompts(payload)
    hashes: list[str] = []
    decision = "allow"
    rule: str | None = None
    for text in texts:
        hashes.append(hash_prompt(text))
        outcome, matched = classify(text)
        if outcome == "deny" and decision != "deny":
            decision = "deny"
            rule = matched
    if not texts:
        hashes = []
    return GuardResult(
        decision=decision,
        source=source,
        prompt_count=len(texts),
        hashes=tuple(hashes),
        rule=rule,
        checked_at=moment.isoformat(),
    )


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or audit_path()
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
    max_age_hours: int = MAX_AUDIT_AGE_HOURS,
    max_bytes: int = MAX_AUDIT_BYTES,
) -> list[dict[str, Any]]:
    moment = now or _utc_now()
    cutoff = moment - timedelta(hours=max_age_hours)
    kept: list[dict[str, Any]] = []
    for record in records:
        stamped = str(record.get("checked_at", ""))
        try:
            parsed = datetime.fromisoformat(stamped.replace("Z", "+00:00"))
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


def append_audit(result: GuardResult, path: Path | None = None) -> Path:
    target = path or audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    records = load_records(target)
    records.append(result.as_dict())
    pruned = prune_records(records)
    encoded = "\n".join(json.dumps(item, separators=(",", ":")) for item in pruned)
    if encoded:
        encoded += "\n"
    target.write_text(encoded, encoding="utf-8")
    return target


def load_workflow(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MediaGuardError(f"cannot read workflow: {path}") from exc


def cmd_guard(args: argparse.Namespace) -> int:
    workflow = Path(args.file)
    if not workflow.is_file():
        print(f"ERROR: workflow not found: {workflow}", file=sys.stderr)
        return 2
    result = evaluate(load_workflow(workflow), source=str(workflow))
    if not args.dry_run:
        append_audit(result)
    print(json.dumps(result.as_dict(), indent=2))
    if result.decision == "deny":
        print(
            f"DENIED: rule={result.rule} (raw prompt not stored)",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    records = prune_records(load_records())
    limit = max(1, int(args.limit))
    print(json.dumps(records[-limit:], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hash and filter ComfyUI prompts. Never prints raw prompt text."
    )
    sub = parser.add_subparsers(dest="command")
    guard = sub.add_parser("guard")
    guard.add_argument("--file", required=True)
    guard.add_argument("--dry-run", action="store_true")
    audit = sub.add_parser("audit")
    audit.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "guard":
        return cmd_guard(args)
    if args.command == "audit":
        return cmd_audit(args)
    print("Usage: ai media guard --file WORKFLOW.json [--dry-run]", file=sys.stderr)
    print("       ai media audit [--limit N]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
