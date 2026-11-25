from __future__ import annotations

import subprocess
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from apps.gateway.app import main
from apps.gateway.app.admission import load_hardware


def _general_model() -> dict:
    return {
        "id": "general-qwen38-27b",
        "public_model_id": "Qwen3.8-27B-UD-Q4_K_M",
        "service": "llm-general",
        "profile": "general",
        "port": 8082,
        "base_url": "http://127.0.0.1:8082/v1",
        "backend_model": "ai-station-general",
        "heavy": True,
        "supports_vision": True,
        "supports_tools": True,
    }


def _chat_body(**kwargs) -> dict:
    body = {
        "model": "ai-station-general",
        "messages": [{"role": "user", "content": "Give a short answer."}],
        "max_tokens": 64,
    }
    body.update(kwargs)
    return body


def _enabled_policy() -> dict:
    return {
        "enabled": True,
        "local_only": True,
        "provider_id": "llama-cpp-general-cpu",
        "max_context_tokens": 2048,
        "max_output_tokens": 512,
    }


@asynccontextmanager
async def _fake_lifecycle_lock(_action: str):
    yield


class GatewayCpuFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_cpu_only_opt_in_is_disabled_by_default_and_hard_caps_match_registry(self) -> None:
        self.assertFalse(main.cpu_fallback_policy()["enabled"])
        registry = main.registry()
        cpu_provider = registry["providers"]["llama-cpp-general-cpu"]
        service = yaml.safe_load((Path(main.PROJECT_DIR) / "compose.models.yml").read_text(encoding="utf-8"))["services"]["llm-general-cpu"]
        self.assertEqual(cpu_provider["minimum_ram_mib"], 24_576)
        self.assertEqual(cpu_provider["max_context"], 2048)
        self.assertEqual(cpu_provider["port"], 8089)
        self.assertEqual(cpu_provider["endpoint"], "http://127.0.0.1:8089/v1")
        self.assertEqual(registry["admission"]["safety_margin_ram_mib"], 4096)
        self.assertEqual(service["cpus"], 6)
        self.assertEqual(service["mem_limit"], "24g")
        self.assertEqual(service["memswap_limit"], "24g")
        self.assertTrue(str(service["ports"][0]).startswith("127.0.0.1:"))
        command = service["command"]
        self.assertEqual(command[command.index("-ngl") + 1], "0")
        self.assertEqual(command[command.index("-c") + 1], "2048")
        self.assertEqual(command[command.index("-n") + 1], "512")

    def test_cpu_fallback_rejects_non_loopback_provider_endpoint(self) -> None:
        providers = main.registry()
        provider = dict(providers["providers"]["llama-cpp-general-cpu"])
        provider["endpoint"] = "https://remote.example:8089/v1"
        replacement = {**providers, "providers": {**providers["providers"], "llama-cpp-general-cpu": provider}}
        with patch.object(main, "registry", return_value=replacement):
            with self.assertRaises(main.HTTPException) as exc:
                main.cpu_runtime_model(_general_model(), _enabled_policy())
        self.assertEqual(exc.exception.status_code, 503)

    async def test_health_reports_cpu_only_while_opted_in_service_is_ready(self) -> None:
        prior_id = main.ACTIVE_MODEL_ID
        prior_mode = main.ACTIVE_RUNTIME_MODE
        main.ACTIVE_MODEL_ID = "Qwen3.8-27B-UD-Q4_K_M"
        main.ACTIVE_RUNTIME_MODE = "cpu_fallback"
        try:
            with (
                patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
                patch.object(main, "get_model", return_value=_general_model()),
                patch.object(main, "runtime_endpoint_ready", new=AsyncMock(return_value=True)) as ready,
            ):
                live = await main.health()
            self.assertEqual(live["active_runtime_mode"], "cpu_fallback")
            self.assertEqual(live["active_model_id"], "Qwen3.8-27B-UD-Q4_K_M")
            ready.assert_awaited_once()

            with (
                patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
                patch.object(main, "get_model", return_value=_general_model()),
                patch.object(main, "runtime_endpoint_ready", new=AsyncMock(return_value=False)),
            ):
                stopped = await main.health()
            self.assertIsNone(stopped["active_runtime_mode"])
            self.assertIsNone(stopped["active_model_id"])

            with (
                patch.object(main, "cpu_fallback_policy", return_value={**_enabled_policy(), "enabled": False}),
                patch.object(main, "runtime_endpoint_ready", new=AsyncMock()) as ready,
            ):
                disabled = await main.health()
            self.assertIsNone(disabled["active_runtime_mode"])
            self.assertIsNone(disabled["active_model_id"])
            ready.assert_not_awaited()
        finally:
            main.ACTIVE_MODEL_ID = prior_id
            main.ACTIVE_RUNTIME_MODE = prior_mode

    async def test_chat_fallback_then_gpu_recovery_never_mutates_catalog_object(self) -> None:
        cached_model = _general_model()
        incoming = {
            "model": cached_model["public_model_id"],
            "messages": [{"role": "user", "content": "hi"}],
        }
        calls: list[tuple[str, dict]] = []

        class CompletionResponse:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "hello"}}]}

        class InferenceClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def post(self, url, json):
                calls.append((url, json))
                return CompletionResponse()

        class Request:
            async def json(self):
                return dict(incoming)

        async def complete_without_disconnect(_request, operation):
            return await operation

        async def fake_compose(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, "", "")

        with (
            patch.object(main, "get_model", return_value=cached_model),
            patch.object(main, "cancel_on_disconnect", complete_without_disconnect),
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(
                main,
                "live_gpu_visibility",
                side_effect=[
                    {"available": False, "status": "no_adapters"},
                    {"available": True, "status": "available", "adapter_count": 1},
                ],
            ),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "runtime_endpoint_ready", new=AsyncMock(side_effect=[False, False])),
            patch.object(main, "evaluate_admission", return_value={"decision": "START", "stop_providers": []}),
            patch.object(main, "stop_other_heavy", new=AsyncMock()),
            patch.object(main, "compose", fake_compose),
            patch.object(main, "wait_ready", new=AsyncMock(return_value=None)),
            patch.object(main.httpx, "AsyncClient", return_value=InferenceClient()),
        ):
            first = await main.chat(Request())
            second = await main.chat(Request())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(calls[0][0], "http://127.0.0.1:8089/v1/chat/completions")
        self.assertEqual(calls[1][0], "http://127.0.0.1:8082/v1/chat/completions")
        self.assertEqual(cached_model["service"], "llm-general")
        self.assertEqual(cached_model["base_url"], "http://127.0.0.1:8082/v1")
        self.assertNotIn("_cpu_fallback", cached_model)

    async def test_no_adapter_routes_general_text_to_bounded_cpu_service(self) -> None:
        model = _general_model()
        body = _chat_body()
        compose_calls: list[list[str]] = []

        async def fake_compose(args, **_kwargs):
            compose_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(main, "live_gpu_visibility", return_value={"available": False, "status": "no_adapters"}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "runtime_endpoint_ready", new=AsyncMock(side_effect=[False, False])),
            patch.object(main, "evaluate_admission", return_value={"decision": "START", "stop_providers": []}) as admit,
            patch.object(main, "compose", fake_compose),
            patch.object(main, "wait_ready", new=AsyncMock(return_value=None)),
            patch.object(main, "publish_active_profile") as publish,
        ):
            admission = await main.start_runtime(model, body)

        self.assertTrue(model["_cpu_fallback"])
        self.assertEqual(model["service"], "llm-general-cpu")
        self.assertEqual(model["base_url"], "http://127.0.0.1:8089/v1")
        self.assertEqual(body["model"], "ai-station-general-cpu")
        self.assertEqual(admission["runtime_mode"], "cpu_fallback")
        self.assertTrue(admission["degraded"])
        self.assertEqual(compose_calls[0][-3:], ["up", "-d", "llm-general-cpu"])
        self.assertEqual(admit.call_args.args[0]["_provider_id"], "llama-cpp-general-cpu")
        admit.assert_called_once()
        publish.assert_not_called()
        self.assertEqual(main.ACTIVE_RUNTIME_MODE, "cpu_fallback")

    async def test_unknown_gpu_probe_does_not_start_cpu_fallback(self) -> None:
        model = _general_model()
        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(main, "live_gpu_visibility", return_value={"available": False, "status": "tool_missing"}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "evaluate_admission", side_effect=main.HTTPException(status_code=503, detail="busy")) as admit,
            patch.object(main, "compose", new=AsyncMock()) as compose,
        ):
            with self.assertRaises(main.HTTPException):
                await main.start_runtime(model, _chat_body())
        admit.assert_called_once()
        compose.assert_not_called()
        self.assertNotIn("_cpu_fallback", model)

    async def test_gpu_contention_does_not_fall_back_to_cpu(self) -> None:
        model = _general_model()
        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=["llama-cpp-general"])),
            patch.object(main, "live_gpu_visibility", return_value={"available": True, "status": "available", "adapter_count": 1}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "evaluate_admission", side_effect=main.HTTPException(status_code=503, detail="busy")) as admit,
            patch.object(main, "compose", new=AsyncMock()) as compose,
        ):
            with self.assertRaises(main.HTTPException):
                await main.start_runtime(model, _chat_body())
        admit.assert_called_once()
        compose.assert_not_called()
        self.assertEqual(model["service"], "llm-general")

    async def test_visible_gpu_wins_over_running_cpu_fallback_without_stopping_cpu(self) -> None:
        model = _general_model()
        compose_calls: list[list[str]] = []

        async def fake_compose(args, **_kwargs):
            compose_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            # The CPU provider is deliberately non-heavy, so reconciliation
            # does not turn it into a GPU owner or a stop target.
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(main, "live_gpu_visibility", return_value={"available": True, "status": "available", "adapter_count": 1}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "evaluate_admission", return_value={"decision": "START", "stop_providers": [], "gpu_index": 0}),
            patch.object(main, "stop_other_heavy", new=AsyncMock()) as stop_heavy,
            patch.object(main, "compose", fake_compose),
            patch.object(main, "wait_ready", new=AsyncMock(return_value=None)),
            patch.object(main, "publish_active_profile") as publish,
        ):
            admission = await main.start_runtime(model, _chat_body())

        self.assertEqual(admission["runtime_mode"], "gpu")
        self.assertEqual(model["service"], "llm-general")
        self.assertNotIn("_cpu_fallback", model)
        self.assertEqual(compose_calls[0][-3:], ["up", "-d", "llm-general"])
        stop_heavy.assert_awaited_once()
        publish.assert_called_once_with("general")

    async def test_ready_general_runtime_is_kept_when_gpu_probe_reports_no_adapters(self) -> None:
        model = _general_model()
        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(main, "live_gpu_visibility", return_value={"available": False, "status": "no_adapters"}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "runtime_endpoint_ready", new=AsyncMock(return_value=True)),
            patch.object(main, "evaluate_admission") as admit,
            patch.object(main, "compose") as compose,
        ):
            admission = await main.start_runtime(model, _chat_body())
        self.assertEqual(admission["runtime_mode"], "existing_runtime")
        self.assertEqual(model["service"], "llm-general")
        admit.assert_not_called()
        compose.assert_not_called()

    async def test_ready_cpu_service_is_reused_without_ram_readmission_or_compose(self) -> None:
        model = _general_model()
        body = _chat_body()
        with (
            patch.object(main, "LifecycleLock", _fake_lifecycle_lock),
            patch.object(main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            patch.object(main, "live_gpu_visibility", return_value={"available": False, "status": "no_adapters"}),
            patch.object(main, "cpu_fallback_policy", return_value=_enabled_policy()),
            patch.object(main, "runtime_endpoint_ready", new=AsyncMock(side_effect=[False, True])),
            patch("apps.gateway.app.admission.probe_free_ram_mib", return_value=1_000) as ram_probe,
            patch.object(main, "compose") as compose,
        ):
            admission = await main.start_runtime(model, body)
        self.assertEqual(admission["decision"], "REUSE_READY_CPU_RUNTIME")
        self.assertTrue(admission["degraded"])
        self.assertEqual(body["model"], "ai-station-general-cpu")
        ram_probe.assert_not_called()
        compose.assert_not_called()

    async def test_unsupported_vision_tool_and_structured_requests_are_rejected(self) -> None:
        policy = {"max_output_tokens": 512}
        cases = (
            _chat_body(messages=[{"role": "user", "content": [{"type": "image_url"}]}]),
            _chat_body(tools=[{"type": "function", "function": {"name": "f"}}]),
            _chat_body(response_format={"type": "json_object"}),
        )
        for body in cases:
            with self.subTest(body=body):
                self.assertIsNotNone(main.cpu_chat_unsupported_reason(body, policy))
        self.assertIsNone(
            main.cpu_chat_unsupported_reason(
                {"messages": [{"role": "user", "content": "text"}]}, policy
            )
        )
        self.assertIsNotNone(
            main.cpu_chat_unsupported_reason(
                _chat_body(max_tokens=513), policy
            )
        )

    def test_cpu_admission_enforces_ram_headroom_without_gpu(self) -> None:
        decision = main.admit(
            "llama-cpp-general-cpu",
            registry=main.registry(),
            hardware=load_hardware(),
            free_vram_mib=0,
            free_ram_mib=28_671,
            free_storage_mib=100_000_000,
            active_heavy=["llama-cpp-coder"],
        )
        self.assertEqual(decision.decision, "REJECT")
        self.assertIn("insufficient system RAM", " ".join(decision.reasons))

    def test_known_wsl_nvml_failure_is_classified_without_exposing_diagnostic(self) -> None:
        result = subprocess.CompletedProcess(
            ["nvidia-smi"], 1, "", "Failed to initialize NVML: Generic operating system error"
        )
        with (
            patch("apps.gateway.app.main.shutil.which", return_value="/usr/bin/nvidia-smi"),
            patch("apps.gateway.app.main.subprocess.run", return_value=result),
            patch.object(Path, "read_text", return_value="6.18.33.2-microsoft-standard-WSL2"),
            patch.dict("os.environ", {}, clear=False),
        ):
            visibility = main.live_gpu_visibility()
        self.assertEqual(visibility, {"available": False, "status": "wsl_gpu_unavailable"})
        self.assertNotIn("Generic operating system error", str(visibility))

    def test_generic_or_non_wsl_probe_failures_remain_unknown(self) -> None:
        result = subprocess.CompletedProcess(["nvidia-smi"], 1, "", "permission denied")
        with (
            patch("apps.gateway.app.main.shutil.which", return_value="/usr/bin/nvidia-smi"),
            patch("apps.gateway.app.main.subprocess.run", return_value=result),
            patch.object(Path, "read_text", return_value="Linux"),
            patch.dict("os.environ", {"WSL_INTEROP": ""}, clear=False),
        ):
            self.assertEqual(main.live_gpu_visibility()["status"], "query_failed")

    def test_wsl_absolute_nvidia_smi_fallback_is_used(self) -> None:
        result = subprocess.CompletedProcess(["nvidia-smi"], 0, "NVIDIA GPU\n", "")
        with (
            patch("apps.gateway.app.main.shutil.which", return_value=None),
            patch.object(Path, "is_file", return_value=True),
            patch("apps.gateway.app.main.subprocess.run", return_value=result) as run,
        ):
            visibility = main.live_gpu_visibility()
        self.assertTrue(visibility["available"])
        self.assertEqual(run.call_args.args[0][0], "/usr/lib/wsl/lib/nvidia-smi")

    async def test_cpu_reuse_requires_expected_model_alias(self) -> None:
        model = main.cpu_runtime_model(
            _general_model(), {"provider_id": "llama-cpp-general-cpu", "local_only": True}
        )

        class Response:
            status_code = 200

            def __init__(self, model_id: str):
                self.model_id = model_id

            def json(self):
                return {"data": [{"id": self.model_id}]}

        class Client:
            def __init__(self, model_id: str):
                self.response = Response(model_id)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, _url):
                return self.response

        with patch.object(main.httpx, "AsyncClient", side_effect=[Client("wrong-alias"), Client("ai-station-general-cpu")]):
            self.assertFalse(await main.runtime_endpoint_ready(model))
            self.assertTrue(await main.runtime_endpoint_ready(model))

    def test_cpu_provider_is_not_a_heavy_profile_owner(self) -> None:
        self.assertFalse(main.cpu_fallback_policy()["enabled"])
        providers = main.registry()["providers"]
        cpu_provider = providers["llama-cpp-general-cpu"]
        self.assertFalse(cpu_provider["heavy"])
        self.assertEqual(cpu_provider["resource_group"], "cpu")
        self.assertNotIn(cpu_provider["service"], main.heavy_services())


if __name__ == "__main__":
    unittest.main()
