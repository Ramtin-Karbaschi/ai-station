"""Cross-process lifecycle lock shared with the ``ai`` operator CLI.

The lock is an advisory Linux ``flock`` on the stable runtime inode.  It is
intentionally held only for the runtime transition (admission, Compose
mutation, readiness, and marker publication), never for model inference.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import time
from pathlib import Path

try:  # Native Windows contract tests import gateway modules too.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on Windows.
    fcntl = None  # type: ignore[assignment]


class LifecycleBusy(TimeoutError):
    """The bounded lifecycle lock wait expired."""


HELD_FD: contextvars.ContextVar[int | None] = contextvars.ContextVar("ai_station_lifecycle_fd", default=None)

class LifecycleLock:
    def __init__(self, action: str, timeout: float = 30.0) -> None:
        data_root = Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station"))
        self.path = Path(
            os.environ.get(
                "AI_LIFECYCLE_LOCK_FILE",
                str(Path(os.environ.get("AI_STATE_DIR", str(data_root / "runtime"))) / "lifecycle.lock"),
            )
        )
        self.action = action
        self.timeout = timeout
        self._file = None

    async def __aenter__(self) -> "LifecycleLock":
        if fcntl is None:
            raise RuntimeError("AI Station lifecycle transitions require Linux flock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+")
        try:
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._context_token = HELD_FD.set(self._file.fileno())
                    try:
                        os.chmod(self.path, 0o660)
                        os.chown(self.path, -1, os.stat(self.path.parent).st_gid)
                    except OSError:
                        pass
                    self._file.seek(0)
                    self._file.truncate()
                    self._file.write(f"gateway action={self.action} pid={os.getpid()}\n")
                    self._file.flush()
                    return self
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LifecycleBusy(
                            f"AI Station lifecycle transition is busy (action={self.action})"
                        )
                    await asyncio.sleep(min(0.25, max(0.01, deadline - time.monotonic())))
        except BaseException:
            self._file.close()
            self._file = None
            raise

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._file is not None:
            if hasattr(self, "_context_token"):
                HELD_FD.reset(self._context_token)
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            finally:
                self._file.close()
                self._file = None
