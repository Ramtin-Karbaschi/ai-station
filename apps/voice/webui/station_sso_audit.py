"""Small, content-free OIDC role and login audit helpers for the WebUI image."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _groups(value: Any) -> set[str]:
    if isinstance(value, str):
        values = re.split(r"[,;|\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = ()
    return {str(item).strip().casefold() for item in values if str(item).strip()}


def station_role_from_claim(user_data: dict[str, Any]) -> str | None:
    """Return the Station role for a recognized claim; otherwise deny."""
    claim = os.environ.get("OAUTH_ROLES_CLAIM", "groups").strip() or "groups"
    data: Any = user_data
    for part in claim.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    groups = _groups(data)
    admin = _groups(os.environ.get("AI_STATION_OIDC_ADMIN_GROUP", "ai-station-admin"))
    member = _groups(os.environ.get("AI_STATION_OIDC_MEMBER_GROUP", "ai-station-member"))
    viewer = _groups(os.environ.get("AI_STATION_OIDC_VIEWER_GROUP", "ai-station-viewer"))
    if groups & admin:
        return "admin"
    if groups & member:
        return "member"
    if groups & viewer:
        return "viewer"
    return None


def record_station_login(
    *, subject: str, email: str, role: str, provider: str, outcome: str = "success"
) -> dict[str, str]:
    """Append one minimal audit record; never persist tokens or prompt data."""
    if role not in {"admin", "member", "viewer"}:
        raise ValueError("invalid Station role")
    if outcome not in {"success", "failure"}:
        raise ValueError("invalid login outcome")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "email_hash": hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        if email
        else "",
        "role": role,
        "outcome": outcome,
        "provider": provider,
    }
    target = Path(os.environ.get("AI_STATION_SSO_LOG", "/var/log/ai-station-sso/login.jsonl"))
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return record
