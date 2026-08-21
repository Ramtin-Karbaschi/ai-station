#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "ai-station-operations",
    "ai-station-engineering",
    "ai-station-client-integration",
)


class ProjectSkillTests(unittest.TestCase):
    def test_skills_have_valid_frontmatter_and_three_evals(self) -> None:
        for name in SKILLS:
            directory = ROOT / "config/skills" / name
            text = (directory / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), name)
            self.assertRegex(text, rf"(?m)^name: {re.escape(name)}$")
            description = re.search(r"(?m)^description: (.+)$", text)
            self.assertIsNotNone(description, name)
            self.assertIn("Use", description.group(1), name)
            self.assertLess(len(text.splitlines()), 500, name)
            evals = json.loads((directory / "evals/evals.json").read_text(encoding="utf-8"))
            self.assertEqual(evals["skill_name"], name)
            self.assertEqual(len(evals["evals"]), 3)
            for case in evals["evals"]:
                self.assertGreaterEqual(len(case["expectations"]), 4)

    def test_every_skill_preserves_public_api_boundary(self) -> None:
        for name in SKILLS:
            text = (ROOT / "config/skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("http://127.0.0.1:4000/v1", text, name)

    def test_operations_skill_uses_safe_model_lifecycle(self) -> None:
        text = (ROOT / "config/skills/ai-station-operations/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("ai models remove <manifest-id>              # dry-run", text)
        self.assertIn("recoverable quarantine", text)
        self.assertIn("Do not use `rm`", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
