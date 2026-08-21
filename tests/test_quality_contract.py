#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QualityGateContractTests(unittest.TestCase):
    def test_canonical_runner_is_wired_everywhere(self) -> None:
        runner = (ROOT / "scripts/test.sh").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        release = (ROOT / "scripts/release-audit.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/docs-quality.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("unittest discover", runner)
        self.assertIn(".venvs/gateway/bin/python", runner)
        self.assertIn("test:\n\t./scripts/ai test", makefile)
        self.assertIn("check:", makefile)
        self.assertIn("test) cmd_test", cli)
        self.assertIn("scripts/test.sh", release)
        self.assertIn("./scripts/test.sh", workflow)

    def test_live_default_is_llama_cpp_not_an_internal_gateway(self) -> None:
        runner = (ROOT / "scripts/test.sh").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8082/v1", runner)
        self.assertNotIn("http://127.0.0.1:8083/v1", runner)

    def test_application_endpoint_remains_litellm(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        for text in (readme, cli):
            self.assertIn("http://127.0.0.1:4000/v1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
