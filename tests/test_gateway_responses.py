from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from apps.gateway.app import main as gateway_main


MODEL = "Qwen3-Coder-30B-A3B-Instruct-Q4"


class ResponsesConversionTests(unittest.TestCase):
    def test_string_input_and_function_tools_convert_to_chat(self) -> None:
        converted = gateway_main.responses_to_chat_body(
            {
                "model": MODEL,
                "instructions": "Be concise",
                "input": "hello",
                "max_output_tokens": 64,
                "tools": [
                    {
                        "type": "function",
                        "name": "get_time",
                        "description": "Get time",
                        "parameters": {
                            "type": "object",
                            "properties": {"timezone": {"type": "string"}},
                        },
                    }
                ],
            }
        )
        self.assertEqual(
            converted["messages"],
            [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "hello"},
            ],
        )
        self.assertEqual(converted["max_tokens"], 64)
        self.assertEqual(converted["tools"][0]["function"]["name"], "get_time")
        self.assertFalse(converted["stream"])

    def test_function_call_history_converts_to_assistant_and_tool_messages(self) -> None:
        converted = gateway_main.responses_to_chat_body(
            {
                "model": MODEL,
                "input": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "get_time",
                        "arguments": '{"timezone":"UTC"}',
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "12:00",
                    },
                ],
            }
        )
        self.assertEqual(converted["messages"][0]["role"], "assistant")
        self.assertEqual(
            converted["messages"][0]["tool_calls"][0]["function"]["name"],
            "get_time",
        )
        self.assertEqual(converted["messages"][1]["role"], "tool")
        self.assertEqual(converted["messages"][1]["tool_call_id"], "call_1")

    def test_chat_text_and_tools_convert_to_responses_items(self) -> None:
        converted = gateway_main.chat_to_responses(
            {
                "created": 1,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "done",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_time",
                                        "arguments": '{"timezone":"UTC"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                },
            },
            MODEL,
            "resp_test",
        )
        self.assertEqual(converted["id"], "resp_test")
        self.assertEqual(converted["status"], "completed")
        self.assertEqual([item["type"] for item in converted["output"]], ["message", "function_call"])
        self.assertEqual(converted["output"][0]["content"][0]["text"], "done")
        self.assertEqual(converted["output"][1]["call_id"], "call_1")
        self.assertEqual(converted["usage"]["total_tokens"], 5)


class ResponsesEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        gateway_main.cached_catalog.cache_clear()
        gateway_main.QUEUE.clear()

    async def asyncTearDown(self) -> None:
        gateway_main.QUEUE.clear()

    async def _post(self, body: dict) -> httpx.Response:
        real_async_client = httpx.AsyncClient

        async def fake_start_runtime(model):
            return {"decision": "START"}

        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "id": "chat_test",
                    "created": 1,
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "RESPONSES_OK",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 2,
                        "completion_tokens": 3,
                        "total_tokens": 5,
                    },
                }

        class FakeUpstreamClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                self.request_url = url
                self.request_json = json
                return FakeResponse()

        def async_client_factory(*args, **kwargs):
            if "transport" in kwargs:
                return real_async_client(*args, **kwargs)
            return FakeUpstreamClient(*args, **kwargs)

        with patch.object(
            gateway_main, "start_runtime", fake_start_runtime
        ), patch.object(gateway_main.httpx, "AsyncClient", async_client_factory):
            transport = httpx.ASGITransport(app=gateway_main.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.post("/v1/responses", json=body)

    async def test_nonstream_responses_endpoint(self) -> None:
        response = await self._post(
            {"model": MODEL, "input": "reply", "max_output_tokens": 32}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "response")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["output"][0]["content"][0]["text"], "RESPONSES_OK")
        self.assertEqual(gateway_main.QUEUE, [])

    async def test_stream_responses_endpoint_emits_openai_events(self) -> None:
        response = await self._post(
            {"model": MODEL, "input": "reply", "max_output_tokens": 32, "stream": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = []
        for line in response.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "response.created")
        self.assertIn("response.output_text.delta", event_types)
        self.assertEqual(event_types[-1], "response.completed")
        self.assertEqual(gateway_main.QUEUE, [])


class ChatStreamingErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_upstream_http_error_is_visible_but_telemetry_is_content_free(self) -> None:
        class FakeRequest:
            async def is_disconnected(self):
                return False

        class FakeResponse:
            status_code = 400
            headers = {"content-type": "application/json"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def aread(self):
                return json.dumps(
                    {"error": {"message": "invalid input SECRET_PROMPT"}}
                ).encode()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def stream(self, *args, **kwargs):
                return FakeResponse()

        async def fake_start_runtime(model):
            return {"decision": "START"}

        telemetry = []
        item = {"state": "queued"}
        gateway_main.QUEUE.append(item)
        with patch.object(gateway_main, "start_runtime", fake_start_runtime), patch.object(
            gateway_main.httpx, "AsyncClient", FakeClient
        ), patch.object(
            gateway_main,
            "emit_contract_telemetry",
            lambda event, **fields: telemetry.append({"event": event, **fields}),
        ):
            chunks = [
                chunk
                async for chunk in gateway_main.stream_proxy(
                    FakeRequest(),
                    {"base_url": "http://local"},
                    {"messages": [{"role": "user", "content": "secret"}], "tools": []},
                    item,
                    MODEL,
                )
            ]

        output = b"".join(chunks).decode()
        self.assertIn("Local model returned HTTP 400", output)
        self.assertNotIn("SECRET_PROMPT", output)
        self.assertEqual(telemetry[0]["upstream_error_type"], "http_400")
        self.assertNotIn("SECRET_PROMPT", json.dumps(telemetry))
        self.assertNotIn(item, gateway_main.QUEUE)

if __name__ == "__main__":
    unittest.main()
