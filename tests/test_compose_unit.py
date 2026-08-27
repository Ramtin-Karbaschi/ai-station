#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_COMPOSE_FILE = (
    "compose.yml:compose.models.yml:compose.comfyui.experimental.yaml:"
    "compose.hardening.yaml:compose.local-builds.yaml:compose.images.lock.yaml"
)
MANIFEST = ROOT / "config/model-manifest.json"
MODELS_DOC = ROOT / "docs/MODELS.md"


class ComposeUnitAndRecommendedModelsTests(unittest.TestCase):
    def test_env_example_compose_file_is_one_project_chain(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn(f"COMPOSE_FILE={CANONICAL_COMPOSE_FILE}", text)
        self.assertIn("COMPOSE_PROJECT_NAME=ai-station", text)

    def test_installer_expected_compose_file_matches_canonical_chain(self) -> None:
        text = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        self.assertIn("compose.yml:compose.models.yml:compose.comfyui.experimental.yaml:", text)
        self.assertIn(
            "compose.local-builds.yaml:compose.images.lock.yaml",
            text,
        )

    def test_image_lock_scripts_expect_the_same_chain(self) -> None:
        escaped = (
            r"^COMPOSE_FILE=compose\.yml:compose\.models\.yml:"
            r"compose\.comfyui\.experimental\.yaml:"
            r"compose\.hardening\.yaml:compose\.local-builds\.yaml:"
            r"compose\.images\.lock\.yaml$"
        )
        verify = (ROOT / "scripts/verify-image-lock.sh").read_text(encoding="utf-8")
        update = (ROOT / "scripts/update-image-lock.sh").read_text(encoding="utf-8")
        self.assertIn(escaped, verify)
        self.assertIn(escaped, update)

    def test_compose_yml_declares_the_single_project(self) -> None:
        text = (ROOT / "compose.yml").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# One Compose project."))
        self.assertIn("\nname: ai-station\n", text)

    def test_general_reasoning_vision_enable_flash_attn_and_kv_cache(self) -> None:
        text = (ROOT / "compose.models.yml").read_text(encoding="utf-8")
        for service in ("llm-general:", "llm-reasoning:", "llm-vision:"):
            self.assertIn(service, text)
        self.assertGreaterEqual(text.count("--flash-attn"), 3)
        self.assertIn("LLM_GENERAL_CACHE_TYPE_K", text)
        self.assertIn("REASONING_CACHE_TYPE_K", text)
        self.assertIn("VISION_CACHE_TYPE_K", text)

    def test_models_doc_lists_every_manifest_id_and_total_gib(self) -> None:
        doc = MODELS_DOC.read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        total = 0
        for model in manifest["models"]:
            self.assertIn(f"`{model['id']}`", doc, model["id"])
            total += int(model["size_bytes"])
        expected_gib = f"{total / 1024**3:.2f}"
        self.assertIn(expected_gib, doc)
        self.assertRegex(doc, r"Application size excluding model weights")
        self.assertRegex(doc, re.compile(r"one heavy GPU profile", re.I))
