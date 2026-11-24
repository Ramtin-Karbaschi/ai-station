#!/usr/bin/env python3
"""Regression test for the Ornith double-system-message bug.

Root cause (see docs/adr/ADR-009-opencode-local-client.md): real OpenCode
requests always send a leading system message. `rewrite_messages()` used to
unconditionally insert a second `{"role": "system", ...}` message ahead of
it whenever `default_system_prefix` was set. Ornith's Jinja chat template
rejects a body with two system messages ("System message must be at the
beginning"), llama.cpp swallows that exception internally, and the gateway
forwards an HTTP 200 with an empty, zero-token response.

These tests assert `rewrite_messages` merges the prefix into an existing
leading system message instead of inserting a second one.
"""
from __future__ import annotations

import unittest

from fastapi import HTTPException

from apps.gateway.app import main as gateway_main


ORNITH_MODEL = {
    "backend_model": "ornith-backend",
    "default_system_prefix": "/no_think",
}

NO_PREFIX_MODEL = {
    "backend_model": "some-backend",
    "default_system_prefix": "",
}

LONGWRITER_MODEL = {
    "id": "longwriter-zero-32b",
    "backend_model": "ai-station-longwriter",
}


class RewriteMessagesTests(unittest.TestCase):
    def test_merges_prefix_into_existing_leading_system_message(self) -> None:
        body = {
            "model": "ornith-1_5-35b",
            "messages": [
                {"role": "system", "content": "You are a coding agent."},
                {"role": "user", "content": "hi"},
            ],
        }

        result = gateway_main.rewrite_messages(ORNITH_MODEL, body)

        messages = result["messages"]
        system_messages = [m for m in messages if m.get("role") == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("/no_think", messages[0]["content"])
        self.assertIn("You are a coding agent.", messages[0]["content"])
        self.assertEqual(messages[1], {"role": "user", "content": "hi"})

    def test_inserts_new_system_message_when_none_exists(self) -> None:
        body = {
            "model": "ornith-1_5-35b",
            "messages": [{"role": "user", "content": "hi"}],
        }

        result = gateway_main.rewrite_messages(ORNITH_MODEL, body)

        messages = result["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], {"role": "system", "content": "/no_think"})
        self.assertEqual(messages[1], {"role": "user", "content": "hi"})

    def test_no_prefix_leaves_messages_unchanged(self) -> None:
        original_messages = [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": "hi"},
        ]
        body = {"model": "some-model", "messages": list(original_messages)}

        result = gateway_main.rewrite_messages(NO_PREFIX_MODEL, body)

        self.assertEqual(result["messages"], original_messages)

    def test_handles_multi_part_list_content_defensively(self) -> None:
        body = {
            "model": "ornith-1_5-35b",
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "You are a coding agent."}],
                },
                {"role": "user", "content": "hi"},
            ],
        }

        result = gateway_main.rewrite_messages(ORNITH_MODEL, body)

        messages = result["messages"]
        system_messages = [m for m in messages if m.get("role") == "system"]
        self.assertEqual(len(system_messages), 1)
        content = messages[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["text"], "/no_think")
        self.assertEqual(content[1]["text"], "You are a coding agent.")

    def test_longwriter_preserves_a_single_text_prompt(self) -> None:
        prompt = "  \u062f\u0631\u0628\u0627\u0631\u0647\u0654 \u067e\u0644 \u0628\u0646\u0648\u06cc\u0633.\n"
        messages = [{"role": "user", "content": prompt}]
        result = gateway_main.rewrite_messages(LONGWRITER_MODEL, {"messages": messages})
        self.assertEqual(result["messages"], messages)

    def test_longwriter_stops_at_its_answer_boundary(self) -> None:
        body = {"messages": [{"role": "user", "content": "Answer briefly."}]}
        default = gateway_main.rewrite_messages(LONGWRITER_MODEL, body)
        custom = gateway_main.rewrite_messages(LONGWRITER_MODEL, {**body, "stop": ["END"]})
        self.assertEqual(default["stop"], ["</answer>"])
        self.assertEqual(custom["stop"], ["END"])

    def test_longwriter_projects_history_and_sources_into_its_first_message(self) -> None:
        messages = [
            {"role": "system", "content": "Write in Persian."},
            {"role": "user", "content": "Brief A"},
            {"role": "assistant", "content": "Draft A"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<source>Latest evidence</source>"},
                    {"type": "text", "text": "Revise the draft with this source."},
                ],
            },
        ]
        body = {"messages": messages, "stream": True}

        result = gateway_main.rewrite_messages(LONGWRITER_MODEL, body)

        self.assertEqual(result["model"], "ai-station-longwriter")
        self.assertTrue(result["stream"])
        self.assertEqual(result["messages"], [{
            "role": "user",
            "content": (
                "[system]\nWrite in Persian.\n\n[user]\nBrief A\n\n"
                "[assistant]\nDraft A\n\n[user]\n<source>Latest evidence</source>\n"
                "Revise the draft with this source."
            ),
        }])
        self.assertEqual(body["messages"][-1]["content"][0]["text"], "<source>Latest evidence</source>")
        self.assertEqual(gateway_main.rewrite_messages(NO_PREFIX_MODEL, body)["messages"], messages)

    def test_longwriter_rejects_nontext_parts_instead_of_discarding_them(self) -> None:
        body = {
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "image"}}]}],
        }
        with self.assertRaises(HTTPException) as error:
            gateway_main.rewrite_messages(LONGWRITER_MODEL, body)
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
