#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CatalogContractTests)
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
