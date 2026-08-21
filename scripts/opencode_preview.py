#!/usr/bin/env python3
"""Manage one verified, loopback-only static preview for OpenCode."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 4173
STATE_DIR = Path(
    os.environ.get("AI_STATION_PREVIEW_STATE_DIR", Path.home() / ".local/state/ai-station")
).expanduser()
STATE_FILE = STATE_DIR / "opencode-preview.json"
LOG_FILE = STATE_DIR / "opencode-preview.log"


def process_matches(pid: int, directory: Path) -> bool:
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return False
    return "http.server" in command and str(directory) in command


def load_state() -> dict[str, object] | None:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def safe_directory(raw: str) -> Path:
    directory = Path(raw).expanduser().resolve(strict=True)
    lowered = directory.as_posix().lower()
    forbidden = {Path("/"), Path("/home"), Path("/mnt"), Path("/opt"), Path.home()}
    if directory in forbidden or (
        lowered.startswith("/mnt/")
        and "/users/" in lowered
        and lowered.rstrip("/").endswith("/desktop")
    ):
        raise ValueError(f"refusing unsafe preview root: {directory}")
    if not (directory / "index.html").is_file():
        raise ValueError(f"missing required site entrypoint: {directory / 'index.html'}")
    return directory


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def healthy(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.HTTPError):
        return False


def start(directory_arg: str, port: int) -> int:
    try:
        directory = safe_directory(directory_arg)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    state = load_state()
    if state:
        pid = int(state.get("pid", 0))
        old_directory = Path(str(state.get("directory", "")))
        old_port = int(state.get("port", 0))
        if process_matches(pid, old_directory):
            if old_directory == directory and old_port == port and healthy(port):
                print(f"OK: preview already verified at http://127.0.0.1:{port}/")
                return 0
            print("ERROR: another managed preview is running; stop it first", file=sys.stderr)
            return 1
        STATE_FILE.unlink(missing_ok=True)
    if not 1024 <= port <= 65535:
        print("ERROR: port must be between 1024 and 65535", file=sys.stderr)
        return 2
    if not port_available(port):
        print(f"ERROR: loopback port {port} is already in use", file=sys.stderr)
        return 1

    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(directory),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    state_value = {"pid": process.pid, "port": port, "directory": str(directory)}
    STATE_FILE.write_text(json.dumps(state_value, indent=2) + "\n", encoding="utf-8")
    STATE_FILE.chmod(0o600)
    for _ in range(30):
        if process.poll() is not None:
            break
        if healthy(port):
            print(f"OK: preview verified at http://127.0.0.1:{port}/")
            print(f"OK: serving {directory}")
            return 0
        time.sleep(0.1)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    STATE_FILE.unlink(missing_ok=True)
    print(f"ERROR: preview failed its HTTP health check; inspect {LOG_FILE}", file=sys.stderr)
    return 1


def status() -> int:
    state = load_state()
    if not state:
        print("STOPPED: no managed preview")
        return 1
    pid = int(state.get("pid", 0))
    port = int(state.get("port", 0))
    directory = Path(str(state.get("directory", "")))
    if process_matches(pid, directory) and healthy(port):
        print(f"OK: preview verified at http://127.0.0.1:{port}/")
        print(f"OK: serving {directory}")
        return 0
    print("FAILED: preview state exists but the verified server is unavailable", file=sys.stderr)
    return 1


def stop() -> int:
    state = load_state()
    if not state:
        print("OK: no managed preview was running")
        return 0
    pid = int(state.get("pid", 0))
    directory = Path(str(state.get("directory", "")))
    if process_matches(pid, directory):
        os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            if not process_matches(pid, directory):
                break
            time.sleep(0.1)
    STATE_FILE.unlink(missing_ok=True)
    print("OK: managed preview stopped")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("directory", nargs="?", default=".")
    start_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    commands.add_parser("status")
    commands.add_parser("stop")
    args = parser.parse_args()
    if args.command == "start":
        return start(args.directory, args.port)
    if args.command == "status":
        return status()
    return stop()


if __name__ == "__main__":
    raise SystemExit(main())
