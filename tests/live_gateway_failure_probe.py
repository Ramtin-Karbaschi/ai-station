"""Disposable live HTTP evidence for Gateway readiness failure handling.

Run from WSL with the gateway environment:
  .venvs/gateway/bin/python tests/live_gateway_failure_probe.py

The fake Compose helper only records invocations and exits successfully; no
production service, socket, model, or Docker state is touched.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx


class UnreadyHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b"warming")

    def log_message(self, *_args):
        return


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-station-gateway-live-") as raw:
        root = Path(raw)
        calls = root / "compose.calls"
        helper = root / "compose-helper.py"
        helper.write_text(
            "import pathlib, sys, time\n"
            f"pathlib.Path({str(calls)!r}).open('a').write(f'{time.monotonic():.6f} ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "sys.exit(7 if 'stop' in sys.argv else 0)\n",
            encoding="utf-8",
        )
        catalog = root / "catalog.json"
        catalog.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "probe-model",
                            "public_model_id": "probe-model",
                            "alias": "probe-model",
                            "enabled": True,
                            "kind": "chat",
                            "heavy": True,
                            "service": "probe-runtime",
                            "profile": "probe",
                            "backend_model": "probe-backend",
                            "base_url": "http://127.0.0.1:1/v1",
                            "readiness_attempts": 1,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        providers = root / "providers.yaml"
        providers.write_text(
            "version: 1\n"
            "admission:\n  enforce: true\n  max_active_heavy: 1\n"
            "providers:\n  probe-provider:\n"
            "    id: probe-provider\n    heavy: true\n    service: probe-runtime\n"
            "    profile: probe\n    catalog_ids: [probe-model]\n"
            "    model_aliases: []\n    minimum_vram_mib: 0\n"
            "    minimum_ram_mib: 0\n    minimum_storage_mib: 0\n"
            "    required_features: []\n    lifecycle_command: ai provider start probe-provider\n",
            encoding="utf-8",
        )
        upstream_port = free_port()
        upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), UnreadyHandler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        catalog.write_text(catalog.read_text(encoding="utf-8").replace("127.0.0.1:1", f"127.0.0.1:{upstream_port}"), encoding="utf-8")

        gateway_port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                "AI_STATION_MODEL_CATALOG": str(catalog),
                "AI_STATION_PROVIDERS": str(providers),
                "AI_STATION_COMPOSE_HELPER": f"{sys.executable} {helper}",
                "AI_ACTIVE_PROFILE_FILE": str(root / "active-profile"),
            }
        )
        # main accepts a helper path, so use a tiny executable wrapper rather
        # than altering the repository's production Compose helper.
        wrapper = root / "compose-wrapper"
        wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {helper} \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        env["AI_STATION_COMPOSE_HELPER"] = str(wrapper)
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "apps.gateway.app.main:app", "--host", "127.0.0.1", "--port", str(gateway_port)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            client = httpx.Client(timeout=10)
            for _ in range(50):
                try:
                    if client.get(f"http://127.0.0.1:{gateway_port}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            url = f"http://127.0.0.1:{gateway_port}/v1/chat/completions"
            body = {"model": "probe-model", "messages": [{"role": "user", "content": "hi"}]}
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: client.post(url, json=body), range(2)))
            elapsed = time.monotonic() - started
            payloads = [response.json() for response in responses]
            recorded = calls.read_text(encoding="utf-8").splitlines()
            assert all(response.status_code == 503 for response in responses), payloads
            assert all(payload["detail"]["stage"] == "wait_ready" for payload in payloads), payloads
            assert sum(" up " in f" {line} " for line in recorded) == 2, recorded
            assert sum(" stop " in f" {line} " for line in recorded) == 2, recorded
            # Each readiness failure waits two seconds; MODEL_LOCK therefore
            # makes overlapping requests take roughly two serial waits.
            assert elapsed >= 3.5, elapsed
            assert not (root / "active-profile").exists()
            print(json.dumps({"requests": 2, "elapsed_seconds": round(elapsed, 3), "http_statuses": [r.status_code for r in responses], "failure_stages": [p["detail"]["stage"] for p in payloads], "marker_exists": False, "compose_calls": recorded}))
            return 0
        finally:
            client.close()
            server.terminate()
            server.wait(timeout=5)
            upstream.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
