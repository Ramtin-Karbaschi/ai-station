#!/usr/bin/env python3
"""Provision the local SearXNG signing secret without exposing its value."""

from __future__ import annotations

import argparse
import fcntl
import os
import secrets
import sys
import tempfile
from pathlib import Path

ENV_KEY = "SEARXNG_SECRET"


class SecretConfigError(RuntimeError):
    """A safe configuration error that never includes secret bytes."""


def _root() -> Path:
    configured = os.environ.get("AI_STATION_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _env_file(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else _root() / ".env"


def _read_lines(path: Path) -> list[str]:
    if path.is_symlink():
        raise SecretConfigError("Refusing to provision a symlinked .env file.")
    if not path.is_file():
        raise SecretConfigError("AI Station .env is missing; run the installer first.")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.readlines()


def _entry(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        return None
    key, value = line.split("=", 1)
    if key.strip() != ENV_KEY:
        return None
    raw = value.strip()
    if raw[:1] in {"'", '"'} and len(raw) >= 2 and raw[-1] == raw[0]:
        raw = raw[1:-1]
    else:
        raw = raw.split("#", 1)[0].strip()
    return ENV_KEY, raw


def _find_secret(lines: list[str]) -> tuple[int | None, str | None]:
    matches = [
        (index, entry[1])
        for index, line in enumerate(lines)
        if (entry := _entry(line)) is not None
    ]
    if len(matches) > 1:
        raise SecretConfigError("AI Station .env contains duplicate SearXNG secret entries.")
    return matches[0] if matches else (None, None)


def status(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    _, value = _find_secret(_read_lines(path))
    return bool(value)


def _atomic_write(path: Path, lines: list[str]) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def provision(path: Path) -> bool:
    """Create a missing value in .env; return whether a value was generated."""

    if path.is_symlink():
        raise SecretConfigError("Refusing to provision a symlinked .env file.")
    if not path.is_file():
        raise SecretConfigError("AI Station .env is missing; run the installer first.")
    lock_path = path.with_name(path.name + ".searxng-secret.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        lines = _read_lines(path)
        index, current = _find_secret(lines)
        if current:
            os.chmod(path, 0o600)
            return False

        value = secrets.token_urlsafe(36)
        if index is None:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += "\n"
            lines.append(f"{ENV_KEY}={value}\n")
        else:
            line = lines[index]
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            content = line[: -len(newline)] if newline else line
            key_text, old_value = content.split("=", 1)
            comment = ""
            if "#" in old_value:
                before, after = old_value.split("#", 1)
                if not before.strip():
                    comment = "#" + after
            suffix = f" {comment}" if comment else ""
            lines[index] = f"{key_text}={value}{suffix}{newline}"
        _atomic_write(path, lines)
        return True
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "provision"))
    parser.add_argument("--env-file", help="AI Station .env path")
    args = parser.parse_args(argv)
    path = _env_file(args.env_file)
    try:
        if args.action == "status":
            if status(path):
                print("SearXNG secret is configured in .env (value hidden).")
                return 0
            print("SearXNG secret is missing; run ai searxng secret provision.")
            return 1
        if provision(path):
            print("SearXNG secret provisioned in .env (value hidden); no service restarted.")
        else:
            print("SearXNG secret already configured (value hidden); no service restarted.")
        return 0
    except SecretConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
