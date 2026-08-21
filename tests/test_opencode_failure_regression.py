from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "scripts/opencode_preview.py"
AUDIT = ROOT / "scripts/opencode_session_audit.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("opencode_session_audit", AUDIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenCodeFailureRegressionTests(unittest.TestCase):
    def test_export_audit_rejects_the_known_failure_shape(self) -> None:
        module = load_audit_module()
        payload = {
            "info": {
                "directory": "C:\\Users\\Developer\\Desktop",
                "summary": {"files": 0, "additions": 0, "deletions": 0},
                "model": {"id": "wrong-model"},
                "version": "0.0.0",
            },
            "messages": [
                {
                    "info": {"role": "user"},
                    "parts": [{"type": "text", "text": "Create a website file"}],
                },
                {
                    "info": {"role": "assistant", "finish": "tool-calls"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "input": {
                                    "command": "cd C:\\Users\\Developer\\Desktop && npx http-server -p 8080"
                                },
                                "output": "Directory Listings: visible\nAvailable on:\n  http://192.168.1.2:8080\n<shell_metadata>shell tool terminated command after exceeding timeout 30000 ms</shell_metadata>",
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "user"},
                    "parts": [
                        {
                            "type": "text",
                            "text": "Continue",
                            "synthetic": True,
                            "metadata": {"compaction_continue": True},
                        }
                    ],
                },
                {
                    "info": {"role": "assistant", "finish": "stop", "summary": True},
                    "parts": [{"type": "text", "text": "done: server running and available"}],
                },
                {
                    "info": {"role": "user"},
                    "parts": [
                        {
                            "type": "file",
                            "mime": "application/pdf",
                            "url": "data:application/pdf;base64," + ("A" * 40000),
                        },
                        {"type": "compaction"},
                    ],
                },
                {"info": {"role": "assistant"}, "parts": []},
                {"info": {"role": "user"}, "parts": [{"type": "compaction"}]},
                {"info": {"role": "assistant"}, "parts": []},
                {"info": {"role": "user"}, "parts": [{"type": "compaction"}]},
                {"info": {"role": "assistant"}, "parts": []},
            ],
        }
        codes = {item["code"] for item in module.audit(payload)}
        self.assertTrue(
            {
                "unsafe_workspace",
                "wrong_build_model",
                "runtime_drift",
                "synthetic_autocontinue",
                "compaction_loop",
                "empty_assistant_loop",
                "oversized_inline_media",
                "unmanaged_preview",
                "unsafe_serve_root",
                "directory_listing",
                "lan_exposure",
                "server_timeout",
                "missing_final_response",
                "artifact_free_completion_claim",
            }.issubset(codes)
        )

    def test_managed_preview_persists_and_is_loopback_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            home = base / "home"
            site = base / "site"
            home.mkdir()
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><title>Verified</title>", encoding="utf-8")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env["HOME"] = str(home)
            start = subprocess.run(
                [sys.executable, str(PREVIEW), "start", str(site), "--port", str(port)],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )
            self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"Verified", response.read())
                state = json.loads(
                    (home / ".local/state/ai-station/opencode-preview.json").read_text(encoding="utf-8")
                )
                listening = subprocess.run(
                    ["ss", "-ltnp", f"sport = :{port}"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                local_address = next(
                    line.split()[3] for line in listening.splitlines() if "LISTEN" in line
                )
                self.assertTrue(local_address.startswith("127.0.0.1:"), listening)
                self.assertGreater(int(state["pid"]), 1)
            finally:
                subprocess.run(
                    [sys.executable, str(PREVIEW), "stop"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=env,
                    check=False,
                )

    def test_managed_contract_forbids_the_old_server_path(self) -> None:
        build = (ROOT / "config/clients/opencode/agents/build.md").read_text(encoding="utf-8")
        service = (ROOT / "infra/systemd/ai-station-opencode.service").read_text(encoding="utf-8")
        desktop = (ROOT / "scripts/configure-opencode-desktop.ps1").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/lib/ai-opencode.sh").read_text(encoding="utf-8")
        attachment_plugin = (
            ROOT / "config/clients/opencode/plugins/local-attachments.js"
        ).read_text(encoding="utf-8")
        self.assertIn("ai opencode preview start .", build)
        self.assertIn("Never serve a home, Desktop, parent, or drive", build)
        self.assertIn("--hostname 127.0.0.1 --port 4096", service)
        self.assertIn("defaultServerUrl", desktop)
        self.assertIn('$projectRoot = "/opt/ai-station"', desktop)
        self.assertIn("worktree = $projectRoot", desktop)
        self.assertIn("$projectsByServer[$ServerUrl]", desktop)
        self.assertIn("opencode.global.dat", desktop)
        self.assertIn('foreach ($relative in @("agents", "commands", "plugins"))', desktop)
        self.assertIn("native-sidecar-disabled-use-wsl-server", desktop)
        self.assertIn("opencode.jsonc.bak-*", desktop)
        self.assertIn("audit-session)", cli)
        self.assertIn("desktop)", cli)
        self.assertIn('part.mime !== "application/pdf"', attachment_plugin)
        self.assertIn("output.parts.splice(index, 1, textPart(part, notice))", attachment_plugin)
        self.assertIn("if (input.overflow) output.enabled = false", attachment_plugin)
        self.assertIn("output.message.model.modelID = CODER_MODEL", attachment_plugin)
        self.assertNotIn("output.parts.push(\n              textPart(part", attachment_plugin)

    def test_read_only_summary_does_not_require_a_changed_artifact(self) -> None:
        module = load_audit_module()
        payload = {
            "info": {
                "directory": "/opt/ai-station",
                "summary": {"files": 0},
                "model": {"id": module.EXPECTED_MODEL},
                "version": module.EXPECTED_VERSION,
            },
            "messages": [
                {
                    "info": {"role": "user"},
                    "parts": [{"type": "text", "text": "Summarize this document"}],
                },
                {
                    "info": {"role": "assistant", "finish": "stop"},
                    "parts": [{"type": "text", "text": "Summary completed."}],
                },
            ],
        }
        codes = {item["code"] for item in module.audit(payload)}
        self.assertNotIn("artifact_free_completion_claim", codes)


if __name__ == "__main__":
    unittest.main()
