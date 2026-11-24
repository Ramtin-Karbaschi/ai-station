import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from apps.gateway.app.media import assert_media_idle


class MediaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_or_unverifiable_media_blocks_switch(self):
        providers = {"media": {"engine": "comfyui", "endpoint": "http://127.0.0.1:8188"}}
        for queue in ({"queue_running": [[1]], "queue_pending": []},
                      {"queue_running": [], "queue_pending": [[2]]}, {},
                      {"queue_running": None, "queue_pending": []}):
            with self.subTest(queue=queue), patch("apps.gateway.app.media.httpx.AsyncClient") as cls:
                client = AsyncMock()
                cls.return_value.__aenter__.return_value = client
                client.get.return_value = httpx.Response(200, json=queue,
                                          request=httpx.Request("GET", "http://127.0.0.1:8188/queue"))
                with self.assertRaises(HTTPException) as error:
                    await assert_media_idle({"active_heavy": ["media"]}, providers)
                self.assertEqual(error.exception.status_code, 503)
        with patch("apps.gateway.app.media.httpx.AsyncClient") as cls:
            client = AsyncMock()
            cls.return_value.__aenter__.return_value = client
            client.get.side_effect = httpx.ConnectError("offline")
            with self.assertRaises(HTTPException):
                await assert_media_idle({"active_heavy": ["media"]}, providers)

    async def test_idle_media_and_nonmedia_are_allowed(self):
        providers = {"media": {"engine": "comfyui", "endpoint": "http://127.0.0.1:8188"}}
        with patch("apps.gateway.app.media.httpx.AsyncClient") as cls:
            client = AsyncMock()
            cls.return_value.__aenter__.return_value = client
            client.get.return_value = httpx.Response(200, json={"queue_running": [], "queue_pending": []},
                                      request=httpx.Request("GET", "http://127.0.0.1:8188/queue"))
            await assert_media_idle({"active_heavy": ["media"]}, providers)
            client.get.assert_awaited_once()
        with patch("apps.gateway.app.media.httpx.AsyncClient") as cls:
            await assert_media_idle({"active_heavy": ["general"]}, providers)
            cls.assert_not_called()
