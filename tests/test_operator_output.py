#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operator_output
import graphify_view


class OperatorOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / "srv"
        self.data.mkdir()
        os.environ["AI_STATION_DATA"] = str(self.data)
        os.environ.pop("AI_STATION_OPERATOR_PREFS", None)
        os.environ.pop("AI_STATION_OPERATOR_ENV", None)

    def tearDown(self) -> None:
        self.temp.cleanup()
        os.environ.pop("AI_STATION_DATA", None)
        os.environ.pop("AI_STATION_OPERATOR_PREFS", None)
        os.environ.pop("AI_STATION_OPERATOR_ENV", None)

    def test_set_media_stays_under_runtime(self) -> None:
        target = self.data / "runtime" / "media" / "clips"
        rc = operator_output.cmd_set("media", str(target))
        self.assertEqual(rc, 0)
        prefs = operator_output.load_prefs()
        self.assertEqual(prefs["outputs"]["media"], str(target.resolve()))
        env_text = operator_output.env_file_path().read_text(encoding="utf-8")
        self.assertIn("AI_STATION_COMFYUI_OUTPUT=", env_text)
        self.assertIn(str(target.resolve()), env_text)

    def test_rejects_system_paths(self) -> None:
        rc = operator_output.cmd_set("media", "/etc/passwd")
        self.assertEqual(rc, 2)
        rc = operator_output.cmd_set("graphify", "/opt/ai-station/secrets/keys")
        self.assertEqual(rc, 2)

    def test_export_accepts_runtime_subdir(self) -> None:
        target = self.data / "runtime" / "exports" / "win"
        rc = operator_output.cmd_set("export", str(target))
        self.assertEqual(rc, 0)

    def test_station_map_html_is_loopback_only(self) -> None:
        html = graphify_view.station_map_html(3, 4, "/srv/x", "/srv/y", "/srv/z", True)
        self.assertIn("GRAPH_TREE.html", html)
        self.assertIn("http://127.0.0.1:3000", html)
        self.assertIn("http://127.0.0.1:5678", html)
        self.assertIn("graph.html", html)
        self.assertNotIn("0.0.0.0", html)


class OperatorConsoleContractTests(unittest.TestCase):
    def test_cli_and_manager_expose_output_and_view(self) -> None:
        dispatcher = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        graphify = (ROOT / "scripts/lib/ai-graphify.sh").read_text(encoding="utf-8")
        output = (ROOT / "scripts/lib/ai-output.sh").read_text(encoding="utf-8")
        manager = (ROOT / "AI Station/AI Station Manager.ps1").read_text(
            encoding="utf-8"
        )
        overlay = (ROOT / "compose.comfyui.experimental.yaml").read_text(
            encoding="utf-8"
        )
        adr = (
            ROOT / "docs/adr/ADR-016-operator-console-and-selectable-outputs.md"
        ).read_text(encoding="utf-8")
        self.assertIn("output) cmd_output", dispatcher)
        self.assertIn("view) cmd_graphify_view", graphify)
        self.assertIn("--out|--output", graphify)
        self.assertIn("ai output set", output)
        self.assertIn('@("graphify", "view")', manager)
        self.assertIn('@("output", "set", "media", $folder)', manager)
        self.assertIn("http://127.0.0.1:4174", manager)
        self.assertIn("AI_STATION_COMFYUI_OUTPUT", overlay)
        self.assertIn("Status: Accepted", adr)
        self.assertIn("127.0.0.1:4174", adr)
        compose = (ROOT / "scripts/compose-ai-station.sh").read_text(encoding="utf-8")
        self.assertIn("compose-operator.env", compose)


if __name__ == "__main__":
    unittest.main()
