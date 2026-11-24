from __future__ import annotations

import copy
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import model_provider_contract as contract


class ModelProviderContractTests(unittest.TestCase):
    def test_matrix_is_clean_and_preserves_intentional_aliases(self) -> None:
        sources = contract.load_sources(ROOT)
        self.assertEqual(contract.validate(sources), [])
        rows = {row.catalog_id: row for row in contract.build_matrix(sources)}
        self.assertIn("local-general", rows["general-qwen38-27b"].source_aliases)
        self.assertIn("ai-station-general", rows["general-qwen38-27b"].source_aliases)
        self.assertEqual(rows["vision-qwen38-27b"].physical_model, "qwen38/qwen3.8-27b-ud-q4_k_m.gguf")
        self.assertEqual(rows["vision-qwen38-27b"].mmproj, "qwen38/mmproj-f16.gguf")
        self.assertEqual(rows["vision-qwen38-27b"].logical_backend, "ai-station-vision")
        projections = contract.compatibility_projections(sources)
        self.assertIn("local-ornith", {item["alias"] for item in projections})

    def test_intentional_catalog_mutation_is_detected(self) -> None:
        sources = contract.load_sources(ROOT)
        mutated = copy.deepcopy(sources)
        mutated["catalog"]["models"][0]["public_model_id"] = "mutated-public-id"
        errors = contract.validate(mutated)
        self.assertTrue(any("missing LiteLLM route mutated-public-id" in error for error in errors))

    def test_compose_alias_mutation_is_detected(self) -> None:
        sources = contract.load_sources(ROOT)
        mutated = copy.deepcopy(sources)
        for document in mutated["compose"]:
            service = (document.get("services") or {}).get("llm-general")
            if service and service.get("command"):
                command = list(service["command"])
                command[command.index("--alias") + 1] = "mutated-backend"
                service["command"] = command
        errors = contract.validate(mutated)
        self.assertTrue(any("Compose --alias contradicts backend_model" in error for error in errors))

    def test_litellm_mode_mutation_is_detected(self) -> None:
        sources = contract.load_sources(ROOT)
        mutated = copy.deepcopy(sources)
        mutated["litellm"]["model_list"][0]["model_info"]["mode"] = "embedding"
        errors = contract.validate(mutated)
        self.assertTrue(any("LiteLLM mode 'embedding' != 'chat'" in error for error in errors))

    def test_root_fixture_loads_without_secret_diagnostics(self) -> None:
        helper = ROOT / "scripts" / "lib" / "ai-common.sh"
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)
            (fixture / ".env").write_text("COMPOSE_FILE=compose.fixture.yml\nLITELLM_MASTER_KEY=fixture-secret\n", encoding="utf-8")
            command = f"source {helper}; ai_root; printf '%s\\n' \"$PWD\"; ai_load_env_value COMPOSE_FILE"
            env = os.environ.copy()
            env["AI_STATION_ROOT"] = str(fixture)
            result = subprocess.run(["bash", "-lc", command], text=True, capture_output=True, env=env, check=True)
            self.assertEqual(result.stdout.splitlines(), [str(fixture), "compose.fixture.yml"])
            self.assertNotIn("fixture-secret", result.stdout + result.stderr)

    def test_wrapper_fixture_uses_non_default_root_without_secret_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)
            (fixture / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/compose-ai-station.sh", fixture / "scripts/compose-ai-station.sh")
            (fixture / ".env").write_text("COMPOSE_FILE=compose.fixture.yml\nLITELLM_MASTER_KEY=fixture-secret\n", encoding="utf-8")
            fake_bin = fixture / "bin"
            fake_bin.mkdir()
            fake_docker = fake_bin / "docker"
            fake_docker.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\"\n", encoding="utf-8")
            fake_docker.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["AI_STATION_ROOT"] = str(fixture)
            result = subprocess.run([str(fixture / "scripts/compose-ai-station.sh"), "config", "--quiet"], cwd=fixture, text=True, capture_output=True, env=env, check=True)
            self.assertIn("compose --project-name ai-station", result.stdout)
            self.assertNotIn("fixture-secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
