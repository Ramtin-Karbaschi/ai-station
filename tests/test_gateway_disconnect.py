from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from apps.gateway.app import main as gateway


class ASGIRequest:
    def __init__(self, path: str, model: str):
        self.path = path
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.outgoing: list[dict] = []
        self.incoming.put_nowait(
            {
                "type": "http.request",
                "body": json.dumps(
                    {
                        "model": model,
                        "input": "hello",
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                ).encode(),
                "more_body": False,
            }
        )

    def disconnect(self) -> None:
        self.incoming.put_nowait({"type": "http.disconnect"})

    async def send(self, message: dict) -> None:
        self.outgoing.append(message)

    async def run(self) -> None:
        await gateway.app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": self.path,
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
            },
            self.incoming.get,
            self.send,
        )

    @property
    def status(self) -> int:
        return next(
            message["status"]
            for message in self.outgoing
            if message["type"] == "http.response.start"
        )


class GatewayDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.upstream_started = asyncio.Event()
        self.upstream_closed = asyncio.Event()
        self.finish_upstream = asyncio.Event()
        self.started_models: list[str] = []
        self.requests: list[asyncio.Task] = []
        self.addAsyncCleanup(self.cancel_requests)

        async def start_runtime(model, request_body=None):
            self.assertIsInstance(request_body, dict)
            if model["id"] == "next":
                self.assertTrue(self.upstream_closed.is_set())
            self.started_models.append(model["id"])
            return {"decision": "START"}

        test = self

        class UpstreamClient:
            async def __aenter__(self):
                self.blocked = False
                return self

            async def __aexit__(self, *exc):
                if self.blocked:
                    await asyncio.sleep(0)
                    test.upstream_closed.set()

            async def post(self, url, json):
                if url.startswith("http://blocked/"):
                    self.blocked = True
                    test.upstream_started.set()
                    await test.finish_upstream.wait()
                return gateway.httpx.Response(
                    200,
                    json={
                        "id": "chat_test",
                        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                    },
                )

        self.enterContext(patch.object(gateway, "MODEL_LOCK", asyncio.Lock()))
        self.enterContext(patch.object(gateway, "QUEUE", []))
        self.enterContext(
            patch.object(
                gateway,
                "get_model",
                side_effect=lambda model: {
                    "id": model,
                    "backend_model": model,
                    "base_url": f"http://{model}/v1",
                },
            )
        )
        self.enterContext(patch.object(gateway, "start_runtime", start_runtime))
        self.enterContext(
            patch.object(
                gateway.httpx, "AsyncClient", side_effect=lambda **kwargs: UpstreamClient()
            )
        )

    async def cancel_requests(self) -> None:
        for request in self.requests:
            request.cancel()
        await asyncio.gather(*self.requests, return_exceptions=True)

    def begin(self, path: str, model: str) -> tuple[ASGIRequest, asyncio.Task]:
        request = ASGIRequest(path, model)
        task = asyncio.create_task(request.run())
        self.requests.append(task)
        return request, task

    async def wait_for_two_requests(self) -> None:
        async with asyncio.timeout(1):
            while len(gateway.QUEUE) < 2:
                await asyncio.sleep(0)

    async def check_running_disconnect(self, path: str) -> None:
        abandoned_request, abandoned = self.begin(path, "blocked")
        await asyncio.wait_for(self.upstream_started.wait(), 1)
        next_request, successor = self.begin(path, "next")
        await self.wait_for_two_requests()
        self.assertEqual(self.started_models, ["blocked"])

        abandoned_request.disconnect()

        await asyncio.wait_for(asyncio.shield(abandoned), 1)
        await asyncio.wait_for(asyncio.shield(successor), 1)
        self.assertEqual(abandoned_request.status, 499)
        self.assertEqual(next_request.status, 200)
        self.assertTrue(self.upstream_closed.is_set())
        self.assertFalse(self.finish_upstream.is_set())
        self.assertEqual(self.started_models, ["blocked", "next"])
        self.assertEqual(gateway.QUEUE, [])
        self.assertFalse(gateway.MODEL_LOCK.locked())

    async def test_chat_disconnect_releases_running_model(self) -> None:
        await self.check_running_disconnect("/v1/chat/completions")

    async def test_responses_disconnect_releases_running_model(self) -> None:
        await self.check_running_disconnect("/v1/responses")

    async def test_queued_disconnect_never_starts_model(self) -> None:
        path = "/v1/chat/completions"
        _, owner = self.begin(path, "blocked")
        await asyncio.wait_for(self.upstream_started.wait(), 1)
        abandoned_request, abandoned = self.begin(path, "abandoned")
        await self.wait_for_two_requests()

        abandoned_request.disconnect()

        await asyncio.wait_for(asyncio.shield(abandoned), 1)
        self.assertEqual(abandoned_request.status, 499)
        self.assertTrue(gateway.MODEL_LOCK.locked())
        self.assertEqual(len(gateway.QUEUE), 1)
        self.finish_upstream.set()
        await asyncio.wait_for(asyncio.shield(owner), 1)
        self.assertEqual(self.started_models, ["blocked"])
        self.assertEqual(gateway.QUEUE, [])
        self.assertFalse(gateway.MODEL_LOCK.locked())
