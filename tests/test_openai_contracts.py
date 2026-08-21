#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml

from apps.gateway.app import main as gateway_main


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CHAT_MODELS = [
    "Qwen3.6-35B-A3B-UD-Q4_K_M",
    "Qwen3-Coder-30B-A3B-Instruct-Q4",
    "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M",
    "Qwen3-VL-32B-Instruct-Q4_K_M",
    "Ornith-1.0-35B-Q4_K_M",
]
CANONICAL_UTILITY_MODELS = [
    "Qwen3-Embedding-0.6B-Q8_0",
    "Qwen3-Reranker-0.6B-Q8_0",
]
INVALID_PUBLIC_NAMES = {
    "general-qwen3.6",
    "local-general",
    "local-coder",
    "local-reasoning",
    "local-vision",
    "local-ornith",
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
        self.assertTrue(by_id["general-qwen3_6-35b-a3b"].get("supports_tools"))
        self.assertTrue(by_id["coder-qwen3-coder-30b-a3b"].get("supports_tools"))
        self.assertTrue(
            by_id["general-qwen3_6-35b-a3b"].get("supports_json_schema")
        )
        self.assertTrue(by_id["ornith-1_0-35b"].get("supports_tools"))
        self.assertTrue(by_id["ornith-1_0-35b"].get("supports_json_schema"))
        self.assertEqual(by_id["ornith-1_0-35b"]["port"], 8086)
        self.assertEqual(by_id["ornith-1_0-35b"]["manifest_id"], "ornith-1.0-35b-q4")
        self.assertEqual(by_id["ornith-1_0-35b"]["alias"], "local-ornith")
        self.assertEqual(
            by_id["ornith-1_0-35b"].get("default_system_prefix"), "/no_think"
        )

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
        self.assertEqual(registry["models"]["local-ornith"]["status"], "optional")
        self.assertEqual(registry["models"]["local-coder"]["status"], "production")

    def test_ornith_compose_disables_reasoning(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        )
        cmd = compose["services"]["llm-ornith"]["command"]
        self.assertIn("--reasoning", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning") + 1], "off")
        self.assertIn("--reasoning-budget", cmd)
        self.assertEqual(cmd[cmd.index("--reasoning-budget") + 1], "0")

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

        public_ids = [model["public_model_id"] for model in catalog["models"]]
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
                "local-ornith",
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
            CANONICAL_CHAT_MODELS + CANONICAL_UTILITY_MODELS,
        )

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


class GatewayContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        gateway_main.cached_catalog.cache_clear()
        gateway_main.QUEUE.clear()
        gateway_main.ACTIVE_MODEL_ID = None

    async def asyncTearDown(self) -> None:
        gateway_main.QUEUE.clear()
        gateway_main.ACTIVE_MODEL_ID = None

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
