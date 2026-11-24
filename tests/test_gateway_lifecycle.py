from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from apps.gateway.app import lifecycle, main


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, _url):
        return _Response(200)


class GatewayLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def test_gpu_device_request_requires_exact_single_explicit_device(self) -> None:
        valid = [{"Driver": "nvidia", "Count": 0, "DeviceIDs": ["1"]}]
        self.assertTrue(main.valid_gpu_device_requests(valid, "1"))
        self.assertFalse(main.valid_gpu_device_requests([{**valid[0], "DeviceIDs": ["0", "1"]}], "1"))
        self.assertFalse(main.valid_gpu_device_requests([
            {"Driver": "nvidia", "Count": -1, "DeviceIDs": []}, valid[0]
        ], "1"))
        self.assertFalse(main.valid_gpu_device_requests({"Driver": "nvidia"}, "1"))
        self.assertFalse(main.valid_gpu_device_requests([
            {"Driver": "nvidia", "Count": 0, "DeviceIDs": 1}
        ], "1"))

    def test_marker_replacement_is_atomic_and_validates_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            lifecycle.publish_active_profile("general")
            self.assertEqual(lifecycle.read_active_profile(), "general")
            self.assertEqual(list(Path(directory).iterdir()), [Path(directory) / "active"])
            with self.assertRaises(ValueError):
                lifecycle.publish_active_profile("bad\nprofile")

    def test_cli_active_profile_override_wins_over_legacy_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(
                os.environ,
                {
                    "AI_ACTIVE_PROFILE_FILE": str(root / "cli"),
                    "AI_STATION_ACTIVE_PROFILE_FILE": str(root / "legacy"),
                    "AI_STATE_DIR": str(root / "state"),
                },
                clear=False,
            ):
                lifecycle.publish_active_profile("general")
                self.assertEqual(lifecycle.read_active_profile(), "general")
                self.assertTrue((root / "cli").exists())
                self.assertFalse((root / "legacy").exists())

    async def test_reconcile_clears_marker_when_service_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            lifecycle.publish_active_profile("general")
            result = AsyncMock(return_value=__import__("subprocess").CompletedProcess([], 0, "", ""))
            with patch.object(main, "compose", result), patch.object(main, "registry", return_value={"providers": {}}):
                self.assertEqual(await main.reconcile_active_profile(), [])
            self.assertIsNone(lifecycle.read_active_profile())

    async def test_reconcile_repairs_stale_marker_for_healthy_comfyui(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            lifecycle.publish_active_profile("general")
            providers = {
                "providers": {
                    "comfyui-media-experimental": {
                        "id": "comfyui-media-experimental",
                        "service": "comfyui-experimental",
                        "profile": "comfyui-experimental",
                        "heavy": True,
                        "health_endpoint": "http://127.0.0.1:8188/system_stats",
                        "lifecycle_command": "ai provider start comfyui-media-experimental",
                    }
                }
            }
            result = AsyncMock(
                return_value=__import__("subprocess").CompletedProcess(
                    [], 0, "comfyui-experimental\n", ""
                )
            )
            with patch.object(main, "compose", result), patch.object(main, "registry", return_value=providers), patch.object(
                main.httpx, "AsyncClient", return_value=_Client()
            ):
                self.assertEqual(await main.reconcile_active_profile(), ["comfyui-media-experimental"])
            self.assertEqual(lifecycle.read_active_profile(), "comfyui-experimental")

    async def test_reconcile_detects_live_comfyui_without_saved_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            providers = {
                "providers": {
                    "comfyui-media-experimental": {
                        "id": "comfyui-media-experimental",
                        "service": "comfyui-experimental",
                        "profile": "comfyui-experimental",
                        "heavy": True,
                        "health_endpoint": "http://127.0.0.1:8188/system_stats",
                        "lifecycle_command": "ai provider start comfyui-media-experimental",
                    }
                }
            }
            result = AsyncMock(
                return_value=subprocess.CompletedProcess([], 0, "comfyui-experimental\n", "")
            )
            with patch.object(main, "compose", result), patch.object(main, "registry", return_value=providers), patch.object(
                main.httpx, "AsyncClient", return_value=_Client()
            ):
                self.assertEqual(await main.reconcile_active_profile(), ["comfyui-media-experimental"])
            self.assertEqual(lifecycle.read_active_profile(), "comfyui-experimental")

    async def test_reconcile_returns_observed_ids_when_health_is_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            providers = {
                "providers": {
                    "comfy": {
                        "id": "comfy",
                        "service": "comfyui-experimental",
                        "profile": "comfyui-experimental",
                        "heavy": True,
                        "health_endpoint": "http://127.0.0.1:8188/system_stats",
                    },
                    "coder": {
                        "id": "coder",
                        "service": "llm-coder",
                        "profile": "coder",
                        "heavy": True,
                        "health_endpoint": "http://127.0.0.1:8083/v1/models",
                    },
                }
            }
            result = AsyncMock(
                return_value=subprocess.CompletedProcess(
                    [], 0, "comfyui-experimental\nllm-coder\n", ""
                )
            )
            class _Down(_Client):
                async def get(self, _url):
                    raise OSError("unreachable")
            with patch.object(main, "compose", result), patch.object(main, "registry", return_value=providers), patch.object(
                main.httpx, "AsyncClient", return_value=_Down()
            ):
                self.assertEqual(
                    await main.reconcile_active_profile(), ["comfy", "coder"]
                )
            self.assertIsNone(lifecycle.read_active_profile())

    async def test_failed_same_profile_start_preserves_valid_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_STATION_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            lifecycle.publish_active_profile("coder")
            model = {"id": "test", "service": "llm-coder", "profile": "coder", "heavy": True}
            with patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=["coder"])), patch.object(
                main, "evaluate_admission", side_effect=main.HTTPException(status_code=503, detail="queued")
            ):
                with self.assertRaises(main.HTTPException):
                    await main.start_runtime(model)
            self.assertEqual(lifecycle.read_active_profile(), "coder")

    async def test_failed_new_target_is_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AI_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")},
            clear=False,
        ):
            model = {"id": "test", "service": "llm-coder", "profile": "coder", "heavy": True}
            calls = []

            async def fake_compose(args, timeout=180):
                calls.append(args)
                return subprocess.CompletedProcess(args, 1 if len(calls) == 1 else 0, "", "")

            with patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])), patch.object(
                main, "evaluate_admission", return_value={"decision": "START"}
            ), patch.object(main, "compose", fake_compose):
                with self.assertRaises(main.HTTPException):
                    await main.start_runtime(model)
            self.assertEqual(len(calls), 2)
            self.assertIn("stop", calls[1])
            self.assertIsNone(lifecycle.read_active_profile())

    async def test_nonzero_rollback_is_not_reported_as_success(self) -> None:
        calls = []

        async def fake_compose(args, timeout=180):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, "secret", "failure")

        with patch.object(main, "compose", fake_compose):
            await main.rollback_started_target("llm-coder")
        self.assertEqual(len(calls), 1)
        self.assertIn("stop", calls[0])

    async def test_multi_gpu_start_does_not_stop_distinct_gpu_owner(self) -> None:
        model = {"id": "test-model", "service": "llm-target", "heavy": True}
        compose_calls: list[list[str]] = []

        async def fake_compose(args, timeout=180, env_overrides=None):
            compose_calls.append(args)
            if env_overrides is not None:
                compose_calls.append(["ENV", env_overrides["AI_STATION_GPU_DEVICE_ID"]])
            return subprocess.CompletedProcess(args, 0, "", "")

        async def fake_wait_ready(_model):
            return None

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_ACTIVE_PROFILE_FILE": str(Path(directory) / "active")}
        ):
            with (
                patch.object(
                    main, "evaluate_admission", return_value={"decision": "START", "stop_providers": [], "gpu_index": 1}
                ),
                patch.object(main, "heavy_services", return_value=["llm-other", "llm-target"]),
                patch.object(main, "compose", fake_compose),
                patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=["other"])),
                patch.object(main, "verify_active_gpu_placements", new=AsyncMock(return_value=True)),
                patch.object(
                    main,
                    "preferred_provider_by_service",
                    return_value={"llm-other": {"id": "other", "service": "llm-other"}},
                ),
                patch.object(main, "wait_ready", fake_wait_ready),
            ):
                admission = await main.start_runtime(model)

        self.assertEqual(admission["decision"], "START")
        self.assertEqual(len(compose_calls), 2)
        self.assertEqual(compose_calls[0][-3:], ["up", "-d", "llm-target"])
        self.assertEqual(compose_calls[1], ["ENV", "1"])


if __name__ == "__main__":
    unittest.main()
