from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
CHAT_HELPER = ROOT / "scripts/lib/chat-readiness.sh"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/lib"))
import hardware_detect  # noqa: E402


class ChatCanaryHandler(BaseHTTPRequestHandler):
    response_status = 200
    response_payload = {"choices": [{"message": {"content": "ready"}}]}
    requests: list[tuple[dict[str, str], dict[str, object]]] = []

    def do_POST(self) -> None:  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((dict(self.headers), payload))
        body = json.dumps(type(self).response_payload).encode()
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


class ChatResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ChatCanaryHandler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ChatCanaryHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}/v1/chat/completions"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        ChatCanaryHandler.requests = []
        ChatCanaryHandler.response_status = 200
        ChatCanaryHandler.response_payload = {"choices": [{"message": {"content": "ready"}}]}

    def run_canary(
        self,
        key: str,
        *,
        attempts: int = 1,
        max_tokens: int = 128,
        allow_reasoning: bool = False,
        require_key: bool = True,
        reasoning_effort: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash", "-c",
                'source "$1"; ai_chat_generation_canary "$2" "$3" "$4" fixture "$5" 2 "$7" "$6" "$8" "$9"',
                "bash", str(CHAT_HELPER), self.endpoint, "fixture-model", key, str(attempts),
                str(max_tokens), str(require_key).lower(), str(allow_reasoning).lower(), reasoning_effort,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_public_canary_requires_auth_and_validates_generated_content(self) -> None:
        result = self.run_canary("fixture-key")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("non-empty chat completion", result.stdout)
        headers, payload = ChatCanaryHandler.requests[0]
        self.assertEqual(headers["Authorization"], "Bearer fixture-key")
        self.assertEqual(payload["model"], "fixture-model")
        self.assertEqual(payload["max_tokens"], 128)
        self.assertFalse(payload["stream"])
        self.assertNotIn("reasoning_effort", payload)

    def test_direct_runtime_accepts_reasoning_only_but_public_api_requires_visible_text(self) -> None:
        ChatCanaryHandler.response_payload = {
            "choices": [{"message": {"content": "", "reasoning_content": "thinking"}}]
        }
        direct = self.run_canary(
            "", max_tokens=8, allow_reasoning=True, require_key=False
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)

        public = self.run_canary("fixture-key", max_tokens=512)
        self.assertNotEqual(public.returncode, 0)
        self.assertIn("empty or invalid completion", public.stderr)

    def test_direct_cpu_canary_sets_reasoning_none_but_still_requires_visible_text(self) -> None:
        ChatCanaryHandler.response_payload = {
            "choices": [{"message": {"content": "", "reasoning_content": "thinking"}}]
        }
        result = self.run_canary("", reasoning_effort="none", require_key=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty or invalid completion", result.stderr)
        self.assertEqual(ChatCanaryHandler.requests[0][1]["reasoning_effort"], "none")

        ChatCanaryHandler.response_payload = {
            "choices": [{"message": {"content": "ready"}}]
        }
        result = self.run_canary("", reasoning_effort="none", require_key=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(ChatCanaryHandler.requests[0][1]["reasoning_effort"], "none")

    def test_public_canary_fails_on_http_503_and_does_not_print_key(self) -> None:
        ChatCanaryHandler.response_status = 503
        secret = "fixture-secret-never-print"
        result = self.run_canary(secret)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 503", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_public_canary_fails_on_empty_http_200_completion(self) -> None:
        ChatCanaryHandler.response_payload = {
            "choices": [{"message": {"content": "  "}}]
        }
        result = self.run_canary("fixture-key")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty or invalid completion", result.stderr)

    def test_public_canary_fails_without_key_without_sending_request(self) -> None:
        result = self.run_canary("")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires the LiteLLM master key", result.stderr)
        self.assertEqual(ChatCanaryHandler.requests, [])

    def test_verify_uses_only_the_public_litellm_chat_route(self) -> None:
        verify = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
        self.assertIn("ai_chat_generation_canary", verify)
        self.assertIn("http://127.0.0.1:4000/v1/chat/completions", verify)
        self.assertNotIn("http://127.0.0.1:8082/v1/chat/completions", verify)
        self.assertIn('active_profile="$(ai_active_heavy_profile || true)"', verify)
        self.assertNotIn("/srv/ai-station/runtime/active-heavy-profile", verify)
        self.assertIn("chat_max_tokens=512", verify)

    def test_verify_profile_selection_prefers_live_container_over_stale_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            marker.write_text("general\n", encoding="utf-8")
            docker = directory / "docker"
            docker.write_text("#!/bin/sh\nprintf '%s\\n' ai-station-llm-coder\n", encoding="utf-8")
            docker.chmod(0o755)
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; ai_active_heavy_profile', "bash",
                 str(ROOT / "scripts/lib/ai-common.sh")],
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{directory}:{os.environ['PATH']}",
                    "AI_ACTIVE_PROFILE_FILE": str(marker),
                    "AI_STATE_DIR": str(directory),
                    "AI_STATION_ROOT": str(ROOT),
                },
                timeout=5,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "coder")

    def test_runtime_gpu_probe_distinguishes_missing_tool_from_failed_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = hardware_detect.probe_runtime_gpu(
                which=lambda _name: None,
                wsl_tool_path=Path(temporary) / "nvidia-smi",
            )
        self.assertEqual(missing["status"], "tool_missing")

        failed = hardware_detect.probe_runtime_gpu(
            executable="nvidia-smi",
            runner=Mock(return_value=subprocess.CompletedProcess(
                ["nvidia-smi"], 1, stdout="", stderr="driver error"
            )),
        )
        self.assertEqual(failed["status"], "query_failed")
        self.assertIn("/dev/dxg", failed["message"])
        self.assertNotIn("driver error", json.dumps(failed))

        with patch.dict(os.environ, {"WSL_INTEROP": "1"}, clear=False), patch(
            "scripts.lib.hardware_detect.Path.read_text",
            return_value="6.18.33.2-microsoft-standard-WSL2",
        ):
            known_wsl = hardware_detect.probe_runtime_gpu(
                executable="nvidia-smi",
                runner=Mock(
                    return_value=subprocess.CompletedProcess(
                        ["nvidia-smi"],
                        1,
                        stdout="",
                        stderr="Failed to initialize NVML: Generic operating system error",
                    )
                ),
            )
        self.assertEqual(known_wsl["status"], "wsl_gpu_unavailable")
        self.assertNotIn("Generic operating system error", json.dumps(known_wsl))

    def test_runtime_gpu_probe_parses_live_adapter_inventory(self) -> None:
        result = hardware_detect.probe_runtime_gpu(
            executable="nvidia-smi",
            runner=Mock(return_value=subprocess.CompletedProcess(
                ["nvidia-smi"], 0,
                stdout="NVIDIA Example, 24564\n",
                stderr="",
            )),
        )
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["adapter_count"], 1)
        self.assertEqual(result["adapters"][0]["vram_total_mib"], 24564)

    def test_runtime_gpu_probe_distinguishes_successful_empty_inventory(self) -> None:
        result = hardware_detect.probe_runtime_gpu(
            executable="nvidia-smi",
            runner=Mock(return_value=subprocess.CompletedProcess(
                ["nvidia-smi"], 0, stdout="", stderr=""
            )),
        )
        self.assertEqual(result["status"], "no_adapters")
        self.assertIn("reports no NVIDIA adapters", result["message"])


if __name__ == "__main__":
    unittest.main()
