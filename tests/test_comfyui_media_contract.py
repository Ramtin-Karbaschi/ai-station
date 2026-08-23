#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "compose.comfyui.experimental.yaml"
PROVIDERS = ROOT / "config/providers.yaml"
MANIFEST = ROOT / "config/model-manifest.json"
DOCKERFILE = ROOT / "infra/comfyui/Dockerfile"
BASE_LOCK = ROOT / "config/dockerfile-base-lock.json"
WORKFLOWS = ROOT / "config/clients/comfyui/workflows"
COMPOSE = ROOT / "compose.yml"
CLI = ROOT / "scripts/ai"
COMMON = ROOT / "scripts/lib/ai-common.sh"
UNINSTALL = ROOT / "scripts/uninstall-comfyui-experimental.sh"
SMOKE = ROOT / "scripts/comfyui-media-smoke.sh"
CLIENT_MANIFEST = ROOT / "config/clients/comfyui/manifest.json"
ADR = ROOT / "docs/adr/ADR-015-comfyui-minimax-media-studio.md"
UI_GATEWAY = ROOT / "apps/ui-gateway/ui_gateway.py"


class ComfyuiMediaContractTests(unittest.TestCase):
    def test_overlay_is_profile_gated_and_loopback_only(self) -> None:
        overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
        service = overlay["services"]["comfyui-experimental"]
        self.assertEqual(service["profiles"], ["comfyui-experimental"])
        self.assertEqual(service["restart"], "no")
        self.assertEqual(service["ports"], ["127.0.0.1:${COMFYUI_PORT:-8188}:8188"])
        self.assertTrue(str(service["volumes"][0]).endswith(":ro"))
        volumes = "\n".join(str(item) for item in service["volumes"])
        self.assertIn("custom_nodes/ai_station_minimax", volumes)
        self.assertIn("AI_STATION_COMFYUI_OUTPUT", volumes)
        health = " ".join(service["healthcheck"]["test"])
        self.assertIn("/system_stats", health)
        start = CLI.read_text(encoding="utf-8")
        self.assertIn("ai_retry_compose up -d postgres redis searxng tika embedder", start)
        self.assertNotIn("comfyui-experimental", start.split("cmd_start()", 1)[1].split("cmd_stop()", 1)[0])

    def test_default_start_does_not_reference_comfyui_profile(self) -> None:
        common = COMMON.read_text(encoding="utf-8")
        self.assertIn("ai_stop_experimental_gpu_overlays", common)
        self.assertIn("compose.comfyui.experimental.yaml", common)

    def test_provider_is_retained_heavy_overlay(self) -> None:
        providers = yaml.safe_load(PROVIDERS.read_text(encoding="utf-8"))
        provider = providers["providers"]["comfyui-media-experimental"]
        self.assertEqual(provider["classification"], "production_default")
        self.assertFalse(provider["experimental"])
        self.assertTrue(provider["heavy"])
        self.assertEqual(provider["engine"], "comfyui")
        self.assertEqual(provider["port"], 8188)
        self.assertEqual(provider["health_endpoint"], "http://127.0.0.1:8188/system_stats")
        self.assertEqual(provider["stability_class"], "production")
        self.assertEqual(
            provider["compose_files"],
            ["compose.yml", "compose.comfyui.experimental.yaml"],
        )
        self.assertIsNone(provider.get("fallback_provider"))

    def test_manifest_pins_comfy_org_files_outside_core(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("experimental-comfyui", data["profiles"])
        models = [
            model
            for model in data["models"]
            if "experimental-comfyui" in model.get("profiles", [])
        ]
        self.assertGreaterEqual(len(models), 8)
        required_ids = {
            "experimental-comfyui-music3-dit-int8",
            "experimental-comfyui-music3-text-encoder-int8",
            "experimental-comfyui-music3-vae",
            "experimental-comfyui-h3-fl2va-int8",
            "experimental-comfyui-h3-ref2va-int8",
            "experimental-comfyui-h3-text-encoder-nvfp4",
            "experimental-comfyui-h3-video-vae",
            "experimental-comfyui-h3-audio-vae",
            "experimental-comfyui-flux2-dit-q4",
            "experimental-comfyui-flux2-text-encoder-fp4",
            "experimental-comfyui-flux2-vae",
        }
        ids = {model["id"] for model in models}
        self.assertTrue(required_ids <= ids)
        for model in models:
            self.assertNotIn("core", model["profiles"])
            self.assertNotIn("all", model["profiles"])
            self.assertTrue(model["revision_is_immutable"])
            self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(model["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(model["size_bytes"], 0)
            self.assertTrue(model["destination"].startswith("models/comfyui/"))
            self.assertTrue(model.get("operator_retained"))

    def test_dockerfile_from_is_digest_pinned_in_build_lock(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        first = dockerfile.splitlines()[0]
        self.assertTrue(first.startswith("FROM pytorch/pytorch:"))
        self.assertIn("@sha256:", first)
        lock = json.loads(BASE_LOCK.read_text(encoding="utf-8"))
        entries = {
            (item["dockerfile"], item["line"], item["locked"])
            for item in lock["dockerfiles"]
        }
        image = first.split(None, 1)[1]
        self.assertIn(("infra/comfyui/Dockerfile", 1, image), entries)
        client = json.loads(CLIENT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(client["version"], "0.33.3")
        self.assertEqual(client["classification"], "production_default")
        self.assertEqual(client["port"], 8188)
        self.assertEqual(client["listen"], "127.0.0.1")
        self.assertIn(client["git_commit"], dockerfile)
        self.assertEqual(
            client["comfyui_gguf_git_commit"],
            "6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
        )
        self.assertIn(client["comfyui_gguf_tarball_sha256"], dockerfile)
        self.assertIn("city96/ComfyUI-GGUF", dockerfile)

    def test_workflows_parse_and_name_pinned_files(self) -> None:
        expected = {
            "music3-text-to-music.json": [
                "minimax_music3_dit_int8_convrot.safetensors",
                "minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
                "minimax_music3_dav.safetensors",
            ],
            "h3-text-to-video.json": [
                "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                "SaveVideo",
            ],
            "h3-image-to-video.json": [
                "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                "MiniMaxH3ImageToVideo",
                "SaveVideo",
            ],
            "h3-reference-to-video.json": [
                "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
                "MiniMaxH3ReferenceToVideo",
                "SaveVideo",
            ],
        }
        for name, needles in expected.items():
            path = WORKFLOWS / name
            data = json.loads(path.read_text(encoding="utf-8"))
            blob = json.dumps(data)
            self.assertIn("prompt", data)
            self.assertIn('"type": "minimax"', blob, name)
            for needle in needles:
                self.assertIn(needle, blob, name)
        flux2 = json.loads((WORKFLOWS / "flux2-text-to-image.json").read_text(encoding="utf-8"))
        flux_blob = json.dumps(flux2)
        self.assertIn("prompt", flux2)
        self.assertIn("UnetLoaderGGUF", flux_blob)
        self.assertIn("EmptyFlux2LatentImage", flux_blob)
        self.assertIn("flux2-dev-Q4_K_M.gguf", flux_blob)
        self.assertIn("mistral_3_small_flux2_fp4_mixed.safetensors", flux_blob)
        self.assertIn("flux2-vae.safetensors", flux_blob)
        self.assertIn("SaveImage", flux_blob)
        self.assertNotIn('"type": "minimax"', flux_blob)
        music = json.loads((WORKFLOWS / "music3-text-to-music.json").read_text(encoding="utf-8"))
        music_blob = json.dumps(music)
        self.assertIn("VAEDecodeAudioTiled", music_blob)
        self.assertIn("KSampler", music_blob)
        self.assertIn("nodes", music)

    def test_frontend_replaces_flux_default_graph(self) -> None:
        overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
        volumes = overlay["services"]["comfyui-experimental"]["volumes"]
        self.assertTrue(
            any("ai_station_minimax" in str(item) for item in volumes)
        )
        init = ROOT / "infra/comfyui/custom_nodes/ai_station_minimax/__init__.py"
        js = ROOT / "infra/comfyui/custom_nodes/ai_station_minimax/web/station_defaults.js"
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("WEB_DIRECTORY", init.read_text(encoding="utf-8"))
        js_text = js.read_text(encoding="utf-8")
        self.assertIn("EmptySD3LatentImage", js_text)
        self.assertIn("workflows%2Fmusic3-text-to-music.json", js_text)
        self.assertIn("flux2-text-to-image.json", js_text)
        self.assertIn("UnetLoaderGGUF", js_text)
        self.assertIn("queuePrompt", js_text)
        self.assertIn("custom_nodes/ai_station_minimax", dockerfile)
        common = COMMON.read_text(encoding="utf-8")
        self.assertIn("Comfy.TutorialCompleted", common)

    def test_gitignore_excludes_comfyui_dumps_and_media(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.flac", gitignore)
        self.assertIn("*.mp4", gitignore)
        self.assertIn("benchmarks/results/**/comfyui/*", gitignore)
        self.assertIn("!benchmarks/results/**/comfyui/health.json", gitignore)
        self.assertIn("!benchmarks/results/**/comfyui/*-smoke.json", gitignore)

    def test_open_webui_image_generation_stays_off(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        env = compose["services"]["open-webui"]["environment"]
        self.assertEqual(env["ENABLE_IMAGE_GENERATION"], "False")
        self.assertIn('"image_generation": false', env["DEFAULT_MODEL_METADATA"])
        ui = UI_GATEWAY.read_text(encoding="utf-8")
        self.assertIn('"image_generation": False', ui)

    def test_uninstall_and_smoke_scripts_exist(self) -> None:
        uninstall = UNINSTALL.read_text(encoding="utf-8")
        smoke = SMOKE.read_text(encoding="utf-8")
        self.assertIn("compose.comfyui.experimental.yaml", uninstall)
        self.assertIn("--remove-weights", uninstall)
        self.assertIn("must never be deleted", uninstall)
        self.assertNotIn("mv \"$TARGET\"", uninstall)
        self.assertNotIn("rm -rf /srv/ai-station/models", uninstall)
        self.assertIn("http://127.0.0.1:8188/system_stats", smoke)
        self.assertIn("runtime/comfyui/smoke", smoke)
        self.assertNotIn("$OUT_DIR/system_stats.json", smoke)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("Status: Accepted", adr)
        self.assertIn("experimental", adr)
        self.assertIn("Reject SGLang-Omni", adr)
        flux_adr = (ROOT / "docs/adr/ADR-018-flux2-dev-comfyui.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: Accepted", flux_adr)
        self.assertIn("Do **not** enable Open WebUI", flux_adr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
