"""Gateway lifecycle state and shared active-profile marker helpers.

The marker is an observed fact, not a startup intent.  Writers publish it by
replacement so readers never see a partial profile.  Reconciliation is
deliberately conservative: a failed Docker observation does not justify
deleting a marker or stopping a workload whose ownership is unknown.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def active_profile_path() -> Path:
    data_root = os.getenv("AI_STATION_DATA", "/srv/ai-station")
    state_dir = os.getenv("AI_STATE_DIR", os.path.join(data_root, "runtime"))
    return Path(
        os.getenv(
            "AI_ACTIVE_PROFILE_FILE",
            os.getenv("AI_STATION_ACTIVE_PROFILE_FILE", os.path.join(state_dir, "active-heavy-profile")),
        )
    )


def read_active_profile() -> str | None:
    path = active_profile_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return value or None


def publish_active_profile(profile: str) -> None:
    """Atomically publish a profile after its caller has observed readiness."""
    if not profile or any(char in profile for char in "\r\n\x00"):
        raise ValueError("invalid active profile")
    path = active_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(profile + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o660)
        try:
            os.chown(temporary, -1, path.parent.stat().st_gid)
        except (PermissionError, OSError):
            # Non-root developer installs still need a usable marker; the
            # parent-group ownership is best-effort in that environment.
            pass
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def clear_active_profile(profile: str | None = None) -> bool:
    """Clear the marker, optionally only when it still names ``profile``."""
    path = active_profile_path()
    if profile is not None and read_active_profile() != profile:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def preferred_provider_by_service(providers: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Select one lifecycle owner when aliases share a Compose service."""
    result: dict[str, dict[str, Any]] = {}
    for provider in providers:
        service = provider.get("service")
        if not service or not provider.get("heavy"):
            continue
        current = result.get(str(service))
        owner = provider.get("lifecycle_command") == f"ai provider start {provider.get('id')}"
        current_owner = current and current.get("lifecycle_command") == f"ai provider start {current.get('id')}"
        if current is None or (owner and not current_owner):
            result[str(service)] = dict(provider)
    return result
