#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import yaml
from fastapi import HTTPException

from apps.gateway.app import main as gateway_main


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CHAT_MODELS = [
    "Qwen3.8-27B-UD-Q4_K_M",
    "Ornith-1.5-35B-Q4_K_M",
    "Qwen3.8-27B-Reasoning-UD-Q4_K_M",
    "Qwen3.8-27B-Vision-UD-Q4_K_M",
    "LongWriter-Zero-32B-Q4_K_M",
]
CANONICAL_UTILITY_MODELS = [
    "Qwen3-Embedding-8B-Q4_K_M",
    "Qwen3-Reranker-4B-Q6_K",
]
CANONICAL_AUDIO_MODELS = ["ai-station-asr", "ai-station-speech"]
INVALID_PUBLIC_NAMES = {
    "general-qwen3.6",
    "local-general",
    "local-coder",
    "local-reasoning",
    "local-vision",
    "local-ornith",
    "local-qwen38",
    "local-longwriter",
    "coding-qwen3-coder",
    "coding-qwen3-coder-next",
    "thinking-deepseek-r1",
    "arena-model",
    "Arena Model",
}


class CatalogContractTests(unittest.TestCase):
    def test_general_and_coder_advertise_tools(self) -> None:
        catalog = json.loads(
            (ROOT / "config/model-catalog.json").read_text(encoding="utf-8")
        )
        by_id = {m["id"]: m for m in catalog["models"]}
        self.assertTrue(by_id["general-qwen38-27b"].get("supports_tools"))
        self.assertTrue(by_id["coder-ornith-1_5-35b"].get("supports_tools"))
        self.assertTrue(by_id["general-qwen38-27b"].get("supports_json_schema"))
        self.assertTrue(by_id["coder-ornith-1_5-35b"].get("supports_json_schema"))
        self.assertEqual(by_id["coder-ornith-1_5-35b"]["port"], 8083)
        self.assertEqual(
            by_id["coder-ornith-1_5-35b"]["manifest_id"], "ornith-1.5-35b-q4"
        )
        self.assertEqual(by_id["coder-ornith-1_5-35b"]["alias"], "local-coder")
        self.assertTrue(by_id["coder-ornith-1_5-35b"].get("enabled"))
        self.assertEqual(
            by_id["coder-ornith-1_5-35b"].get("default_system_prefix"), ""
        )
        self.assertNotIn("ornith-1_0-35b", by_id)
        manifest = json.loads(
            (ROOT / "config/model-manifest.json").read_text(encoding="utf-8")
        )
        by_manifest = {m["id"]: m for m in manifest["models"]}
        self.assertEqual(
            by_manifest["ornith-1.5-35b-q4"]["revision"],
            "fbbaed45c2f0e200276ffa51701a24d45dc7f57e",
        )
        self.assertNotIn("ornith-1.0-35b-q4", by_manifest)
        self.assertEqual(by_id["vision-qwen38-27b"]["port"], 8085)
        self.assertEqual(by_id["vision-qwen38-27b"]["alias"], "local-vision")
        self.assertEqual(by_id["vision-qwen38-27b"]["manifest_id"], "qwen38-27b-q4")
        self.assertTrue(by_id["vision-qwen38-27b"].get("supports_tools"))
        self.assertTrue(by_id["vision-qwen38-27b"].get("supports_vision"))
        self.assertTrue(by_id["vision-qwen38-27b"].get("supports_json_schema"))
        self.assertEqual(by_id["vision-qwen38-27b"].get("default_system_prefix"), "")
        self.assertTrue(by_id["vision-qwen38-27b"].get("enabled"))
        self.assertEqual(
            by_manifest["qwen38-27b-q4"]["revision"],
            "4ca720788d1e01f1bff70c033e0d0028fd02e502",
        )
        self.assertEqual(
            by_manifest["qwen38-27b-q4"]["sha256"],
            "322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482",
        )
        self.assertEqual(
            by_manifest["qwen38-27b-mmproj-f16"]["filename"],
            "mmproj-F16.gguf",
        )
        self.assertFalse(
            any(item["id"].startswith("experimental-sglang-qwen") for item in manifest["models"])
        )

    def test_rejected_sglang_overlay_is_absent(self) -> None:
        providers = yaml.safe_load(
            (ROOT / "config/providers.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("sglang-general-experimental", providers["providers"])
        self.assertFalse((ROOT / "compose.sglang.experimental.yaml").exists())
        self.assertFalse(
            (ROOT / "scripts/uninstall-sglang-experimental.sh").exists()
        )
        self.assertFalse(
            (ROOT / "benchmarks/configs/sglang-general-experimental.yaml").exists()
        )
        common = (ROOT / "scripts/lib/ai-common.sh").read_text(encoding="utf-8")
        self.assertNotIn("compose.sglang.experimental.yaml", common)

    def test_ornith_provider_is_optional_and_coder_remains(self) -> None:
        providers = yaml.safe_load(
            (ROOT / "config/providers.yaml").read_text(encoding="utf-8")
        )
        ornith = providers["providers"]["llama-cpp-ornith"]
        coder = providers["providers"]["llama-cpp-coder"]
        self.assertEqual(ornith["classification"], "optional_profile")
        self.assertFalse(ornith["experimental"])
        self.assertTrue(ornith["heavy"])
        self.assertEqual(ornith["port"], 8086)
        self.assertEqual(ornith["fallback_provider"], "llama-cpp-general")
        self.assertEqual(ornith["lifecycle_command"], "ai models use ornith")
        self.assertEqual(coder["classification"], "production_default")

        registry = yaml.safe_load(
            (ROOT / "config/registry/models.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("ornith", registry["runtime_policy"]["heavy_profiles"])
        self.assertEqual(registry["runtime_policy"]["max_active_heavy_profiles"], 1)
        self.assertEqual(registry["models"]["local-ornith"]["status"], "compatibility")
        self.assertEqual(registry["models"]["local-coder"]["status"], "production")

    def test_qwen38_provider_is_optional_and_does_not_replace_defaults(self) -> None:
        providers = yaml.safe_load(
            (ROOT / "config/providers.yaml").read_text(encoding="utf-8")
        )
        qwen38 = providers["providers"]["llama-cpp-qwen38"]
        general = providers["providers"]["llama-cpp-general"]
        vision = providers["providers"]["llama-cpp-vision"]
        self.assertEqual(qwen38["classification"], "optional_profile")
        self.assertFalse(qwen38["experimental"])
        self.assertTrue(qwen38["heavy"])
        self.assertEqual(qwen38["port"], 8087)
        self.assertEqual(qwen38["fallback_provider"], "llama-cpp-general")
        self.assertEqual(qwen38["lifecycle_command"], "ai models use qwen38")
        self.assertEqual(general["classification"], "production_default")
        self.assertEqual(vision["classification"], "production_default")

        registry = yaml.safe_load(
            (ROOT / "config/registry/models.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("qwen38", registry["runtime_policy"]["heavy_profiles"])
        self.assertEqual(registry["runtime_policy"]["max_active_heavy_profiles"], 1)
        self.assertEqual(registry["models"]["local-qwen38"]["status"], "compatibility")
        self.assertEqual(registry["models"]["local-general"]["status"], "production")

    def test_qwen38_compose_keeps_vision_mmproj_and_thinking(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-qwen38"]["command"]
        self.assertIn("--mmproj", cmd)
        self.assertEqual(
            cmd[cmd.index("--mmproj") + 1],
            "/models/${LLM_QWEN38_MMPROJ_FILE:-qwen38/mmproj-f16.gguf}",
        )
        self.assertNotIn("--reasoning", cmd)
        self.assertEqual(
            compose["services"]["llm-qwen38"]["ports"],
            ["127.0.0.1:${QWEN38_LLM_PORT:-8087}:8087"],
        )
        lock = yaml.safe_load(
            (ROOT / "compose.images.lock.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            lock["services"]["llm-qwen38"]["image"],
            lock["services"]["llm-general"]["image"],
        )
        self.assertEqual(
            lock["services"]["asr-qwen3"]["image"],
            lock["services"]["llm-general"]["image"],
        )
        self.assertEqual(lock["services"]["ocr-vl"]["pull_policy"], "build")

    def test_longwriter_provider_is_optional_q4_with_full_offload(self) -> None:
        providers = yaml.safe_load(
            (ROOT / "config/providers.yaml").read_text(encoding="utf-8")
        )
        longwriter = providers["providers"]["llama-cpp-longwriter"]
        self.assertEqual(longwriter["classification"], "optional_profile")
        self.assertFalse(longwriter["experimental"])
        self.assertTrue(longwriter["heavy"])
        self.assertEqual(longwriter["port"], 8088)
        self.assertEqual(longwriter["lifecycle_command"], "ai models use longwriter")
        catalog = json.loads(
            (ROOT / "config/model-catalog.json").read_text(encoding="utf-8")
        )
        by_id = {m["id"]: m for m in catalog["models"]}
        self.assertEqual(by_id["longwriter-zero-32b"]["public_model_id"], "LongWriter-Zero-32B-Q4_K_M")
        self.assertTrue(by_id["longwriter-zero-32b"].get("enabled"))
        self.assertFalse(by_id["longwriter-zero-32b"].get("supports_tools"))
        manifest = json.loads(
            (ROOT / "config/model-manifest.json").read_text(encoding="utf-8")
        )
        by_manifest = {m["id"]: m for m in manifest["models"]}
        self.assertEqual(
            by_manifest["longwriter-zero-32b-q4"]["revision"],
            "4ed85f5410b2a3c16414e9e36e4b9810ee380fb1",
        )
        self.assertEqual(
            by_manifest["longwriter-zero-32b-q4"]["sha256"],
            "b4beb52b144dd8f02f274c3172c642102fe2153cdd0313cae5166ed48c51af67",
        )
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-longwriter"]["command"]
        self.assertEqual(cmd[cmd.index("-ngl") + 1], "${LLM_LONGWRITER_GPU_LAYERS:-999}")
        registry = yaml.safe_load(
            (ROOT / "config/registry/models.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("longwriter", registry["runtime_policy"]["heavy_profiles"])
        self.assertEqual(registry["models"]["local-longwriter"]["status"], "optional")

    def test_ornith_compatibility_profile_matches_coder_capacity(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-ornith"]["command"]
        self.assertIn("--reasoning", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning") + 1], "auto")
        self.assertIn("--reasoning-budget", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning-budget") + 1], "2048")
        self.assertEqual(cmd[cmd.index("-c") + 1], "${LLM_ORNITH_CONTEXT:-8192}")
        self.assertEqual(cmd[cmd.index("-ngl") + 1], "${LLM_ORNITH_GPU_LAYERS:-999}")
        self.assertEqual(cmd[cmd.index("--cache-type-k") + 1], "${LLM_ORNITH_CACHE_TYPE_K:-q4_0}")

    def test_vision_compose_enables_template_detected_reasoning(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-vision"]["command"]
        self.assertIn("--mmproj", cmd)
        self.assertIn("--reasoning", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning") + 1], "auto")
        self.assertIn("--reasoning-budget", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning-budget") + 1], "2048")
        self.assertEqual(cmd[cmd.index("-c") + 1], "${VISION_CONTEXT:-16384}")
        general = compose["services"]["llm-general"]["command"]
        self.assertEqual(general[general.index("--reasoning") + 1], "auto")
        self.assertEqual(general[general.index("--n-predict") + 1], "8192")
        self.assertIn("--mmproj", general)
        self.assertIn("--no-mmproj-offload", general)
        catalog = json.loads((ROOT / "config/model-catalog.json").read_text(encoding="utf-8"))
        general_model = next(model for model in catalog["models"] if model["id"] == "general-qwen38-27b")
        self.assertTrue(general_model["supports_vision"])

    def test_reasoning_compose_enables_jinja_for_tools(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-reasoning"]["command"]
        self.assertIn("--jinja", cmd)

    def test_canonical_public_names_are_synced_across_configs(self) -> None:
        catalog = json.loads(
            (ROOT / "config/model-catalog.json").read_text(encoding="utf-8")
        )
        registry = yaml.safe_load(
            (ROOT / "config/registry/models.yaml").read_text(encoding="utf-8")
        )
        litellm = yaml.safe_load(
            (ROOT / "config/gateway/litellm.yaml").read_text(encoding="utf-8")
        )
        compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))

        public_ids = [
            model["public_model_id"]
            for model in catalog["models"]
            if model.get("enabled") is True
        ]
        self.assertEqual(
            public_ids,
            CANONICAL_CHAT_MODELS + CANONICAL_UTILITY_MODELS,
        )

        registry_public_names = [
            registry["models"][alias]["public_name"]
            for alias in [
                "local-general",
                "local-coder",
                "local-reasoning",
                "local-vision",
                "local-longwriter",
                "local-embedding",
                "local-reranker",
            ]
        ]
        self.assertEqual(
            registry_public_names,
            CANONICAL_CHAT_MODELS + CANONICAL_UTILITY_MODELS,
        )

        litellm_model_names = [entry["model_name"] for entry in litellm["model_list"]]
        self.assertEqual(
            litellm_model_names,
            CANONICAL_CHAT_MODELS + CANONICAL_UTILITY_MODELS + CANONICAL_AUDIO_MODELS,
        )

        self.assertIs(litellm["general_settings"]["cancel_on_disconnect"], True)
        routes = {entry["model_name"]: entry for entry in litellm["model_list"]}
        self.assertEqual(routes["ai-station-asr"]["model_info"]["mode"], "audio_transcription")
        self.assertEqual(routes["ai-station-speech"]["model_info"]["mode"], "audio_speech")
        self.assertNotIn("ports", compose["services"]["station-voice"])
        audio_env = compose["services"]["open-webui"]["environment"]
        for kind, model in zip(("STT", "TTS"), CANONICAL_AUDIO_MODELS):
            self.assertEqual(audio_env[f"AUDIO_{kind}_OPENAI_API_BASE_URL"], "http://llm-gateway:4000/v1")
            self.assertEqual(audio_env[f"AUDIO_{kind}_MODEL"], model)

        openai_configs = json.loads(
            compose["services"]["open-webui"]["environment"]["OPENAI_API_CONFIGS"]
        )
        self.assertEqual(openai_configs["0"]["model_ids"], CANONICAL_CHAT_MODELS)
        self.assertEqual(
            compose["services"]["open-webui"]["environment"]["DEFAULT_MODELS"],
            CANONICAL_CHAT_MODELS[0],
        )
        self.assertEqual(
            compose["services"]["open-webui"]["environment"]["DEFAULT_PINNED_MODELS"],
            CANONICAL_CHAT_MODELS[0],
        )
        self.assertEqual(
            compose["services"]["open-webui"]["environment"][
                "ENABLE_EVALUATION_ARENA_MODELS"
            ],
            "False",
        )

    def test_invalid_and_legacy_names_are_not_exposed_publicly(self) -> None:
        litellm = yaml.safe_load(
            (ROOT / "config/gateway/litellm.yaml").read_text(encoding="utf-8")
        )
        compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
        litellm_model_names = {entry["model_name"] for entry in litellm["model_list"]}
        self.assertTrue(INVALID_PUBLIC_NAMES.isdisjoint(litellm_model_names))

        openai_configs = json.loads(
            compose["services"]["open-webui"]["environment"]["OPENAI_API_CONFIGS"]
        )
        self.assertTrue(
            INVALID_PUBLIC_NAMES.isdisjoint(set(openai_configs["0"]["model_ids"]))
        )

    def test_gateway_service_keeps_loopback_bind_with_bridge_proxy(self) -> None:
        unit = (ROOT / "infra/systemd/ai-station-gateway.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Environment=AI_STATION_GATEWAY_HOST=127.0.0.1", unit)
        self.assertIn(
            "ExecStart=/usr/bin/python3 /opt/ai-station/apps/gateway/host_gateway_runner.py",
            unit,
        )

        verifier = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
        self.assertIn("ip -4 -o addr show docker0", verifier)
        self.assertIn('"$allowed_bridge_host:$port"', verifier)
        self.assertNotIn("0.0.0.0:8888", verifier)
        self.assertIn("host.docker.internal", unit)

    def test_chat_models_have_explicit_output_caps(self) -> None:
        litellm = yaml.safe_load(
            (ROOT / "config/gateway/litellm.yaml").read_text(encoding="utf-8")
        )
        for entry in litellm["model_list"]:
            if entry["model_info"].get("mode") != "chat":
                continue
            if entry["model_name"] == "LongWriter-Zero-32B-Q4_K_M":
                self.assertNotIn("max_tokens", entry["litellm_params"])
                continue
            expected = 8192 if entry["model_name"] == "Ornith-1.5-35B-Q4_K_M" else 4096
            self.assertEqual(entry["litellm_params"].get("max_tokens"), expected)


class GatewayContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {"AI_ACTIVE_PROFILE_FILE": str(directory / "active")}))

        class NullLifecycleLock:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        self._lifecycle_lock_patcher = patch.object(
            gateway_main, "LifecycleLock", NullLifecycleLock
        )
        self._lifecycle_lock_patcher.start()
        gateway_main.cached_catalog.cache_clear()
        gateway_main.QUEUE.clear()
        gateway_main.ACTIVE_MODEL_ID = None

    async def asyncTearDown(self) -> None:
        self._lifecycle_lock_patcher.stop()
        gateway_main.QUEUE.clear()
        gateway_main.ACTIVE_MODEL_ID = None

    async def test_denied_admission_does_not_start_compose(self) -> None:
        model = {"id": "test-model", "service": "llm-test", "heavy": False}
        compose_calls: list[list[str]] = []

        class FakeDecision:
            def __init__(self, decision: str):
                self.decision = decision

            def to_dict(self):
                return {"decision": self.decision}

        async def fake_compose(args, timeout=180):
            compose_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        for decision_name in ("QUEUE", "START_WITH_REDUCED_CONTEXT"):
            compose_calls.clear()
            with (
                patch.object(
                    gateway_main,
                    "admit",
                    return_value=FakeDecision(decision_name),
                ),
                patch.object(
                    gateway_main,
                    "provider_for_catalog_model",
                    return_value={"id": "provider"},
                ),
                patch.object(
                    gateway_main,
                    "registry",
                    return_value={"admission": {"enforce": True}},
                ),
                patch.object(gateway_main, "compose", fake_compose),
                patch.object(gateway_main, "reconcile_active_profile", new=AsyncMock(return_value=[])),
            ):
                with self.assertRaises(HTTPException) as raised:
                    await gateway_main.start_runtime(model)

            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(
                raised.exception.detail["decision"]["decision"], decision_name
            )
            self.assertEqual(compose_calls, [])

    async def test_admission_shadow_mode_preserves_non_start_decision(self) -> None:
        class FakeDecision:
            decision = "QUEUE"

            def to_dict(self):
                return {"decision": self.decision}

        with (
            patch.object(gateway_main, "admit", return_value=FakeDecision()),
            patch.object(
                gateway_main,
                "provider_for_catalog_model",
                return_value={"id": "provider"},
            ),
            patch.object(
                gateway_main,
                "registry",
                return_value={"admission": {"enforce": False}},
            ),
        ):
            payload = gateway_main.evaluate_admission({"id": "test-model"})

        self.assertEqual(payload["decision"], "QUEUE")
        self.assertFalse(payload["enforce"])

    async def test_failed_conflict_stop_does_not_start_target(self) -> None:
        model = {"id": "test-model", "service": "llm-target", "heavy": True}
        compose_calls: list[list[str]] = []

        async def fake_compose(args, timeout=180):
            compose_calls.append(args)
            return subprocess.CompletedProcess(
                args, 1, "secret stdout", "secret stderr"
            )

        with (
            patch.object(
                gateway_main, "evaluate_admission", return_value={"decision": "START"}
            ),
            patch.object(
                gateway_main,
                "heavy_services",
                return_value=["llm-other", "llm-target"],
            ),
            patch.object(gateway_main, "compose", fake_compose),
            patch.object(gateway_main, "reconcile_active_profile", new=AsyncMock(return_value=["other"])),
            patch.object(gateway_main, "preferred_provider_by_service", return_value={"llm-other": {"id": "other", "service": "llm-other"}}),
        ):
            with self.assertRaises(HTTPException) as raised:
                await gateway_main.start_runtime(model)

        self.assertEqual(raised.exception.status_code, 503)
        detail = raised.exception.detail
        self.assertEqual(detail["stage"], "stop_runtime")
        self.assertNotIn("secret stdout", str(detail))
        self.assertNotIn("secret stderr", str(detail))
        self.assertEqual(len(compose_calls), 1)
        self.assertIn("stop", compose_calls[0])

    async def test_successful_transition_stops_then_starts_target(self) -> None:
        model = {"id": "test-model", "service": "llm-target", "heavy": True}
        compose_calls: list[list[str]] = []

        async def fake_compose(args, timeout=180):
            compose_calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        async def fake_wait_ready(_model):
            return None

        with (
            patch.object(
                gateway_main, "evaluate_admission", return_value={"decision": "START"}
            ),
            patch.object(
                gateway_main,
                "heavy_services",
                return_value=["llm-other", "llm-target"],
            ),
            patch.object(gateway_main, "compose", fake_compose),
            patch.object(gateway_main, "reconcile_active_profile", new=AsyncMock(return_value=["other"])),
            patch.object(gateway_main, "preferred_provider_by_service", return_value={"llm-other": {"id": "other", "service": "llm-other"}}),
            patch.object(gateway_main, "wait_ready", fake_wait_ready),
        ):
            admission = await gateway_main.start_runtime(model)

        self.assertEqual(admission["decision"], "START")
        self.assertEqual(len(compose_calls), 2)
        self.assertIn("stop", compose_calls[0])
        self.assertEqual(compose_calls[1][-3:], ["up", "-d", "llm-target"])

    async def test_models_endpoint_returns_only_canonical_public_names(self) -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/v1/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["id"] for item in payload["data"]],
            CANONICAL_CHAT_MODELS,
        )
        self.assertTrue(
            INVALID_PUBLIC_NAMES.isdisjoint({item["id"] for item in payload["data"]})
        )

    async def test_unknown_model_error_lists_valid_canonical_names(self) -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "thinking-deepseek-r1",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )

        self.assertEqual(response.status_code, 404)
        detail = response.json()["detail"]
        self.assertEqual(detail["message"], "Unknown model 'thinking-deepseek-r1'.")
        self.assertEqual(detail["valid_model_names"], CANONICAL_CHAT_MODELS)

    async def test_requests_to_different_heavy_models_are_serialized(self) -> None:
        first_release = asyncio.Event()
        first_started = asyncio.Event()
        start_order: list[str] = []
        real_async_client = httpx.AsyncClient

        async def fake_start_runtime(model):
            start_order.append(gateway_main.public_model_id(model))
            return {"decision": "START"}

        class FakeResponse:
            def __init__(self, model_name: str):
                self.status_code = 200
                self._model_name = model_name

            def json(self):
                return {
                    "choices": [
                        {"message": {"content": f"ok:{self._model_name}"}}
                    ]
                }

        class FakeUpstreamClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, _url, json):
                if json["model"] == "ai-station-general":
                    first_started.set()
                    await first_release.wait()
                return FakeResponse(json["model"])

        def async_client_factory(*args, **kwargs):
            if "transport" in kwargs:
                return real_async_client(*args, **kwargs)
            return FakeUpstreamClient(*args, **kwargs)

        async def send_request(model_name: str):
            transport = httpx.ASGITransport(app=gateway_main.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )

        with patch.object(gateway_main, "start_runtime", fake_start_runtime), patch.object(
            gateway_main.httpx, "AsyncClient", async_client_factory
        ):
            first_task = asyncio.create_task(send_request(CANONICAL_CHAT_MODELS[0]))
            await first_started.wait()
            second_task = asyncio.create_task(send_request(CANONICAL_CHAT_MODELS[1]))
            await asyncio.sleep(0.05)

            self.assertEqual(start_order, [CANONICAL_CHAT_MODELS[0]])
            self.assertEqual(len(gateway_main.QUEUE), 2)

            first_release.set()
            first_response, second_response = await asyncio.gather(
                first_task, second_task
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            start_order,
            [CANONICAL_CHAT_MODELS[0], CANONICAL_CHAT_MODELS[1]],
        )
        self.assertEqual(gateway_main.QUEUE, [])

    async def test_empty_content_copies_reasoning_content(self) -> None:
        real_async_client = httpx.AsyncClient

        async def fake_start_runtime(model):
            return {"decision": "START"}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "reasoning_content": "pong",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "get_time"},
                                    }
                                ],
                            }
                        }
                    ]
                }

        class FakeUpstreamClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, _url, json):
                return FakeResponse()

        def async_client_factory(*args, **kwargs):
            if "transport" in kwargs:
                return real_async_client(*args, **kwargs)
            return FakeUpstreamClient(*args, **kwargs)

        with patch.object(gateway_main, "start_runtime", fake_start_runtime), patch.object(
            gateway_main.httpx, "AsyncClient", async_client_factory
        ):
            transport = httpx.ASGITransport(app=gateway_main.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": CANONICAL_CHAT_MODELS[-1],
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )

        self.assertEqual(response.status_code, 200)
        message = response.json()["choices"][0]["message"]
        self.assertEqual(message["content"], "pong")
        self.assertEqual(message["reasoning_content"], "pong")
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "get_time")

    def test_flatten_helpers_cover_message_delta_and_sse(self) -> None:
        payload = {
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "reasoning_content": "think then answer",
                    }
                }
            ]
        }
        gateway_main.flatten_reasoning_into_content(payload)
        self.assertEqual(
            payload["choices"][0]["delta"]["content"], "think then answer"
        )
        filled = {
            "choices": [
                {"message": {"content": "keep me", "reasoning_content": "ignore"}}
            ]
        }
        gateway_main.flatten_reasoning_into_content(filled)
        self.assertEqual(filled["choices"][0]["message"]["content"], "keep me")
        line = gateway_main.flatten_sse_line(
            b'data: {"choices":[{"delta":{"content":"","reasoning_content":"pong"}}]}\n'
        )
        parsed = json.loads(line.decode("utf-8").split("data:", 1)[-1].strip())
        self.assertEqual(parsed["choices"][0]["delta"]["content"], "pong")
        self.assertEqual(gateway_main.flatten_sse_line(b"data: [DONE]\n"), b"data: [DONE]\n")

    async def test_stream_preserves_reasoning_and_content_delta_boundaries(self) -> None:
        source = (
            'data: {"choices":[{"delta":{"reasoning_content":" \\u0641\\u06a9\\u0631  ",'
            '"content":" \\u0633\\u0644\\u0627\\u0645  "}}]}\r\n\r\n'
            'data: [DONE]\r\n\r\n'
        ).encode("utf-8")

        async def chunks():
            for offset in (0, 7, 19, 41):
                if offset < len(source):
                    next_offset = {0: 7, 7: 19, 19: 41, 41: len(source)}[offset]
                    yield source[offset:next_offset]

        output = b"".join(
            [chunk async for chunk in gateway_main.iter_flattened_sse(chunks(), flatten_reasoning=False)]
        )
        self.assertEqual(output, source)
        event = json.loads(output.split(b"data: ", 1)[1].split(b"\r\n", 1)[0])
        delta = event["choices"][0]["delta"]
        self.assertEqual(delta["reasoning_content"], " \u0641\u06a9\u0631  ")
        self.assertEqual(delta["content"], " \u0633\u0644\u0627\u0645  ")


def live_json_contract(endpoint: str, model: str) -> None:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Return only JSON: {\"ok\": true}",
            }
        ],
        "max_tokens": 32,
        "temperature": 0,
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = payload["choices"][0]["message"]["content"]
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text
    parsed = json.loads(text[start : end + 1])
    assert parsed.get("ok") is True, parsed


def live_tools_contract(endpoint: str, model: str) -> None:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Call the tool get_time with timezone=UTC.",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get the current time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string"},
                        },
                        "required": ["timezone"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "max_tokens": 128,
        "temperature": 0,
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        raise AssertionError(f"No tool_calls in response: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8082/v1")
    parser.add_argument("--model", default="ai-station-general")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    if args.live:
        print("Running live JSON contract...")
        live_json_contract(args.endpoint, args.model)
        print("OK: JSON contract")
        print("Running live tools contract...")
        live_tools_contract(args.endpoint, args.model)
        print("OK: tools contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
