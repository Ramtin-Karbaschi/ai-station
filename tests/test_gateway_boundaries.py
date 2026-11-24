from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from apps.gateway.app import catalog, readiness


class GatewayBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_catalog_selection_is_independent_of_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            catalog, "CATALOG_PATH", Path(directory) / "catalog.json"
        ):
            catalog.CATALOG_PATH.write_text(
                json.dumps(
                    {
                        "models": [
                            {"id": "chat", "public_model_id": "public-chat", "enabled": True, "kind": "chat"},
                            {"id": "disabled", "enabled": False, "kind": "chat"},
                            {"id": "embed", "enabled": True, "kind": "embedding"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            catalog.cached_catalog.cache_clear()
            self.assertEqual(catalog.valid_public_model_ids(), ["public-chat"])
            self.assertTrue(catalog.model_matches(catalog.selectable_models()[0], "chat"))

    async def test_readiness_reports_provider_http_failure_without_compose(self) -> None:
        class Response:
            status_code = 503
            text = "warming"

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, _url):
                return Response()

        # One attempt is enough to characterize the stable failure shape;
        # avoid a real two-second retry in the unit lane.
        with patch.object(readiness.httpx, "AsyncClient", return_value=Client()), patch.object(
            readiness.asyncio, "sleep", return_value=None
        ) as sleep:
            with self.assertRaises(HTTPException) as raised:
                await readiness.wait_ready(
                    {"id": "demo", "service": "demo", "base_url": "http://127.0.0.1:1"},
                    attempts=1,
                )
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["stage"], "wait_ready")
        self.assertIn("HTTP 503", raised.exception.detail["last_error"])
        sleep.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
