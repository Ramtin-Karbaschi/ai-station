#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/ai"
KEYS = ROOT / "scripts/lib/litellm_keys.py"
sys.path.insert(0, str(KEYS.parent))
import litellm_keys  # noqa: E402


class ProjectKeyLimitTests(unittest.TestCase):
    def test_default_generate_payload_omits_rate_limits(self) -> None:
        payload = litellm_keys.generate_payload(
            "demo",
            ["Qwen3.8-27B-UD-Q4_K_M"],
        )
        self.assertNotIn("tpm_limit", payload)
        self.assertNotIn("rpm_limit", payload)
        self.assertEqual(payload["key_alias"], "demo")
        self.assertEqual(payload["models"], ["Qwen3.8-27B-UD-Q4_K_M"])

    def test_optional_caps_are_explicit(self) -> None:
        payload = litellm_keys.generate_payload(
            "capped",
            ["Qwen3.8-27B-UD-Q4_K_M"],
            rpm=12,
            tpm=4096,
        )
        self.assertEqual(payload["rpm_limit"], 12)
        self.assertEqual(payload["tpm_limit"], 4096)

    def test_generate_payload_cli_default_has_no_limits(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(KEYS),
                "generate-payload",
                "--alias",
                "n8n",
                "--models",
                "Qwen3.8-27B-UD-Q4_K_M,Qwen3-Embedding-8B-Q4_K_M",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertNotIn("tpm_limit", payload)
        self.assertNotIn("rpm_limit", payload)

    def test_cli_defaults_are_unlimited(self) -> None:
        text = CLI.read_text(encoding="utf-8")
        self.assertNotIn("local tpm=100000", text)
        self.assertNotIn("local rpm=60", text)
        self.assertIn("cmd_projects_unlimit", text)
        self.assertIn("TPM/RPM are off by default", text)
        self.assertIn("scripts/lib/litellm_keys.py", text)


if __name__ == "__main__":
    unittest.main()
