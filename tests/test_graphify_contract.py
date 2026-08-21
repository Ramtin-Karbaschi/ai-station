#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/clients/graphify/manifest.json"
ADR = ROOT / "docs/adr/ADR-012-graphify-code-knowledge-graph.md"
CLI = ROOT / "scripts/ai"
GRAPHIFY_MODULE = ROOT / "scripts/lib/ai-graphify.sh"
OPENCODE_CMD = ROOT / "config/clients/opencode/commands/graphify.md"
OPENCODE_PLUGIN = ROOT / "config/clients/opencode/plugins/graphify.js"
OPENCODE_AGENTS = ROOT / "config/clients/opencode/AGENTS.md"
GRAPHIFY_DOC = ROOT / "docs/clients/GRAPHIFY.md"
GITIGNORE = ROOT / ".gitignore"


class GraphifyContractTests(unittest.TestCase):
    def test_manifest_pins_verified_wheel(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["package"], "graphifyy")
        self.assertEqual(data["cli"], "graphify")
        self.assertEqual(data["version"], "0.9.47")
        self.assertEqual(
            data["wheel_sha256"],
            "2a8b13ccd53d507d16dcc12aebe488517c369afa547938464474fd3e772938ab",
        )
        self.assertEqual(data["classification"], "optional_profile")
        self.assertEqual(data["license"], "Apache-2.0")

    def test_adr_records_decision_and_non_overlap(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for needle in (
            "Status: Accepted",
            "optional profile",
            "pgvector",
            "--code-only",
            "http://127.0.0.1:4000/v1",
            "ai graphify uninstall",
        ):
            self.assertIn(needle, text)

    def test_cli_exposes_graphify_and_defaults_to_code_only(self) -> None:
        dispatcher = CLI.read_text(encoding="utf-8")
        module = GRAPHIFY_MODULE.read_text(encoding="utf-8")
        self.assertIn("ai graphify install|configure|status|extract", dispatcher)
        self.assertIn('source "$ROOT/scripts/lib/ai-graphify.sh"', dispatcher)
        self.assertIn("graphify) cmd_graphify", dispatcher)
        self.assertIn('--code-only', module)
        self.assertIn("http://127.0.0.1:4000/v1", module)
        self.assertIn("/srv/ai-station/runtime/graphify", module)
        self.assertIn("graphifyy[openai,pdf]==", module)
        self.assertIn('"--token-budget", "4096"', module)
        self.assertNotIn("generativelanguage.googleapis.com", module)
        self.assertNotIn("api.openai.com", module)

    def test_opencode_command_stays_short(self) -> None:
        text = OPENCODE_CMD.read_text(encoding="utf-8")
        self.assertLess(len(text), 2500)
        self.assertIn("ai graphify query", text)
        self.assertNotIn("GEMINI_API_KEY", text)

    def test_opencode_plugin_reminds_once_without_shell_injection(self) -> None:
        text = OPENCODE_PLUGIN.read_text(encoding="utf-8")
        self.assertIn("tool.execute.before", text)
        self.assertIn("ai graphify query", text)
        self.assertNotIn("$(", text)
        self.assertNotIn("`", text)

    def test_agents_and_docs_prefer_station_cli(self) -> None:
        agents = OPENCODE_AGENTS.read_text(encoding="utf-8")
        docs = GRAPHIFY_DOC.read_text(encoding="utf-8")
        self.assertIn("ai graphify query", agents)
        self.assertIn("ai graphify query", docs)
        self.assertIn("optional", docs.lower())
        self.assertNotIn("GEMINI_API_KEY", docs)

    def test_gitignore_excludes_generated_graph(self) -> None:
        text = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("/graphify-out", text)


if __name__ == "__main__":
    unittest.main()
