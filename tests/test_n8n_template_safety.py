#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "config/clients/n8n/workflows"
TEMPLATES = (
    "litellm-chat.json",
    "tika-summarize.json",
    "ticket-reply.json",
    "invoice-ocr.json",
    "meeting-summary.json",
)
ALLOWED_NODE_TYPES = {
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.set",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.httpRequest",
}
EXPECTED_ROUTES = {
    "llm-gateway": (4000, "/v1/chat/completions", "POST"),
    "tika": (9998, "/tika", "PUT"),
}


class N8nTemplateSafetyTests(unittest.TestCase):
    def test_all_station_templates_are_inactive_manual_local_only_and_credential_free(self) -> None:
        self.assertEqual(len(TEMPLATES), 5)
        for filename in TEMPLATES:
            with self.subTest(workflow=filename):
                workflow = json.loads(
                    (WORKFLOWS / filename).read_text(encoding="utf-8")
                )
                self.assertIs(workflow.get("active"), False)
                nodes = workflow.get("nodes") or []
                node_types = [str(node.get("type") or "") for node in nodes]
                self.assertTrue(nodes)
                self.assertEqual(set(node_types), set(node_types) & ALLOWED_NODE_TYPES)
                triggers = [node_type for node_type in node_types if "Trigger" in node_type]
                self.assertEqual(triggers, ["n8n-nodes-base.manualTrigger"])
                self.assertFalse(
                    any(node.get("credentials") for node in nodes),
                    "templates must not embed n8n credentials",
                )
                for node in nodes:
                    if node.get("type") != "n8n-nodes-base.httpRequest":
                        continue
                    params = node.get("parameters") or {}
                    url = urlsplit(str(params.get("url") or ""))
                    self.assertEqual(url.scheme, "http")
                    self.assertIn(url.hostname, EXPECTED_ROUTES)
                    expected_port, expected_path, expected_method = EXPECTED_ROUTES[url.hostname]
                    self.assertEqual(url.port, expected_port)
                    self.assertEqual(url.path, expected_path)
                    self.assertEqual(url.query, "")
                    self.assertEqual(url.fragment, "")
                    self.assertIsNone(url.username)
                    self.assertIsNone(url.password)
                    self.assertEqual(str(params.get("method") or "GET").upper(), expected_method)
                    self.assertNotIn("credentials", node)
                    for header in (
                        (params.get("headerParameters") or {}).get("parameters") or []
                    ):
                        self.assertIn(
                            header.get("name"), {"Content-Type", "Accept"}
                        )


if __name__ == "__main__":
    unittest.main()
