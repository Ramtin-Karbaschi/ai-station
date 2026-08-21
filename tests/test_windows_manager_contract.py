#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "AI Station/AI Station Manager.cmd"
MANAGER = ROOT / "AI Station/AI Station Manager.ps1"
LAUNCHER = ROOT / "AI Station/AI Station.ps1"


class WindowsManagerContractTests(unittest.TestCase):
    def test_cmd_is_only_a_compatibility_launcher(self) -> None:
        text = CMD.read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 10)
        self.assertIn("AI Station Manager.ps1", text)

    def test_manager_uses_direct_argument_passing_not_shell_strings(self) -> None:
        text = MANAGER.read_text(encoding="utf-8")
        self.assertIn("$AiPath @AiArgs", text)
        self.assertNotIn("bash -lc", text)
        self.assertIn("Read-SafeId", text)
        self.assertIn("^[A-Za-z0-9]", text)

    def test_manager_exposes_engineering_and_model_paths(self) -> None:
        text = MANAGER.read_text(encoding="utf-8")
        for needle in (
            '@("test")',
            '@("models", "catalog")',
            '@("models", "install", $modelId)',
            '@("models", "add", "--id", $modelId, "--repo", $repo, "--filename", $filename, "--role", $role, "--revision", $revision)',
            '@("models", "remove", $modelId)',
            '@("models", "restore", $modelId, "--confirm")',
            "http://127.0.0.1:4000/ui",
            "Read-SafeRepo",
        ):
            self.assertIn(needle, text)

    def test_manager_menu_choices_are_unique(self) -> None:
        import re

        text = MANAGER.read_text(encoding="utf-8")
        choices = re.findall(r'^\s*"(\d+)"\s*\{', text, flags=re.MULTILINE)
        self.assertEqual(len(choices), len(set(choices)))
        numeric = sorted(int(item) for item in choices)
        self.assertEqual(numeric, list(range(numeric[0], numeric[-1] + 1)))
        self.assertIn('if (Invoke-AIStation @("opencode", "doctor"))', text)

    def test_launcher_contains_no_personal_email(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("@gmail.com", text)
        self.assertIn("local Open WebUI account", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
