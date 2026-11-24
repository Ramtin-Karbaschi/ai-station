#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yml"
PROVIDERS = ROOT / "config/providers.yaml"
CLI = ROOT / "scripts/ai"
COMMON = ROOT / "scripts/lib/ai-common.sh"
N8N_LIB = ROOT / "scripts/lib/ai-n8n.sh"
ADR = ROOT / "docs/adr/ADR-021-optional-n8n-automation-client.md"
DOC = ROOT / "docs/clients/N8N.md"
MANIFEST = ROOT / "config/clients/n8n/manifest.json"
WORKFLOWS = ROOT / "config/clients/n8n/workflows"
CHAT = WORKFLOWS / "litellm-chat.json"
TIKA = WORKFLOWS / "tika-summarize.json"


class N8nContractTests(unittest.TestCase):
    def test_service_is_profile_gated_loopback_cpu_only(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = compose["services"]["n8n"]
        self.assertEqual(service["profiles"], ["n8n"])
        self.assertEqual(service["restart"], "unless-stopped")
        self.assertEqual(
            service["ports"],
            ["127.0.0.1:${N8N_PORT:-5678}:${N8N_PORT:-5678}"],
        )
        self.assertNotIn("gpus", service)
        env = service["environment"]
        self.assertEqual(env["N8N_PORT"], "${N8N_PORT:-5678}")
        self.assertEqual(env["N8N_TEMPLATES_ENABLED"], "false")
        self.assertEqual(env["N8N_DIAGNOSTICS_ENABLED"], "false")
        self.assertEqual(env["N8N_VERSION_NOTIFICATIONS_ENABLED"], "false")
        self.assertEqual(env["N8N_SECURE_COOKIE"], "false")
        self.assertEqual(env["N8N_BLOCK_ENV_ACCESS_IN_NODE"], "true")
        self.assertEqual(env["N8N_COMMUNITY_PACKAGES_ENABLED"], "false")
        self.assertEqual(
            env["N8N_INSTANCE_AI_MODEL_URL"],
            "${N8N_INSTANCE_AI_MODEL_URL:-http://llm-gateway:4000/v1}",
        )
        self.assertEqual(
            env["N8N_INSTANCE_AI_MODEL"],
            "${N8N_INSTANCE_AI_MODEL:-Qwen3.8-27B-UD-Q4_K_M}",
        )
        self.assertEqual(env["N8N_INSTANCE_AI_MODEL_API_KEY"], "${N8N_LLM_API_KEY:-}")
        self.assertIn("searxng:8080", env["N8N_INSTANCE_AI_SEARXNG_URL"])
        self.assertEqual(env["N8N_INSTANCE_AI_SANDBOX_ENABLED"], "true")
        self.assertEqual(env["N8N_INSTANCE_AI_BROWSER_USE_ENABLED"], "false")
        self.assertEqual(env["N8N_INSTANCE_AI_OBSERVER_MESSAGE_TOKENS"], "8192")
        self.assertEqual(env["N8N_INSTANCE_AI_SANDBOX_PROVIDER"], "n8n-sandbox")
        self.assertEqual(
            env["N8N_SANDBOX_SERVICE_URL"],
            "${N8N_SANDBOX_SERVICE_URL:-http://sandbox-api:8080}",
        )
        self.assertEqual(
            env["N8N_SANDBOX_SERVICE_API_KEY"],
            "${N8N_SANDBOX_SERVICE_API_KEY:-}",
        )
        health = " ".join(service["healthcheck"]["test"])
        self.assertIn("/healthz", health)
        self.assertIn("process.env.N8N_PORT", health)
        self.assertNotIn("${N8N_PORT", health)
        self.assertNotIn("http://127.0.0.1:5678/healthz", health)
        volumes = "\n".join(str(item) for item in service["volumes"])
        self.assertIn("runtime/n8n", volumes)
        self.assertIn("config/clients/n8n/workflows", volumes)

    def test_sandbox_is_internal_only_and_profile_gated(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        for name in ("sandbox-certs", "sandbox-api", "sandbox-runner-1"):
            service = compose["services"][name]
            self.assertEqual(service["profiles"], ["n8n"])
            self.assertNotIn("ports", service)
            self.assertNotIn("gpus", service)
        self.assertTrue(compose["services"]["sandbox-runner-1"]["privileged"])
        self.assertNotIn("privileged", compose["services"]["sandbox-api"])
        self.assertNotIn("privileged", compose["services"]["n8n"])
        runner_env = compose["services"]["sandbox-runner-1"]["environment"]
        self.assertIn(
            "n8n-sandbox-service-sandbox@sha256:",
            runner_env["SANDBOX_RUNNER_DOCKER_SANDBOX_IMAGE"],
        )

    def test_default_start_does_not_launch_n8n(self) -> None:
        start = CLI.read_text(encoding="utf-8")
        start_body = start.split("cmd_start()", 1)[1].split("cmd_stop()", 1)[0]
        self.assertNotIn("n8n", start_body)
        self.assertIn("--profile n8n", start.split("cmd_stop()", 1)[1])

    def test_provider_is_optional_cpu_without_compose_overlay(self) -> None:
        providers = yaml.safe_load(PROVIDERS.read_text(encoding="utf-8"))
        provider = providers["providers"]["n8n"]
        self.assertEqual(provider["classification"], "optional_profile")
        self.assertFalse(provider["experimental"])
        self.assertFalse(provider["heavy"])
        self.assertEqual(provider["engine"], "n8n")
        self.assertEqual(provider["port"], 5678)
        self.assertEqual(
            provider["health_endpoint"],
            "http://127.0.0.1:5678/healthz",
        )
        self.assertIsNone(provider.get("compose_files"))
        self.assertEqual(provider["lifecycle_command"], "ai provider start n8n")
        self.assertEqual(provider["minimum_vram_mib"], 0)

    def test_cli_and_uninstall_exist(self) -> None:
        text = N8N_LIB.read_text(encoding="utf-8")
        for needle in (
            "ai n8n start",
            "ai n8n stop",
            "ai n8n status",
            "ai n8n configure",
            "ai n8n uninstall",
            "--purge",
            "--confirm",
            "http://127.0.0.1:5678",
            "llm-gateway:4000",
            "N8N_LLM_API_KEY",
            "N8N_INSTANCE_AI",
            "N8N_SANDBOX_SERVICE",
            "sandbox-api:8080",
            "litellm_keys.py",
            "unlimit --alias",
        ):
            self.assertIn(needle, text)
        cli = CLI.read_text(encoding="utf-8")
        common = COMMON.read_text(encoding="utf-8")
        self.assertIn('source "$ROOT/scripts/lib/ai-n8n.sh"', cli)
        self.assertIn('n8n) cmd_n8n "$@"', cli)
        self.assertIn("ai_n8n_ensure_project", cli)
        self.assertIn("ai_n8n_sync_litellm_key", cli)
        self.assertIn("ai_ensure_n8n_sandbox_secrets", cli)
        self.assertIn("sandbox-certs sandbox-api sandbox-runner-1", cli)
        self.assertIn("--force-recreate n8n", cli)
        self.assertIn("ai_prepare_n8n_runtime_dirs", common)
        self.assertIn("ai_ensure_n8n_encryption_key", common)
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("N8N_LLM_API_KEY=", example)
        self.assertIn("N8N_SANDBOX_SERVICE_API_KEY=", example)

    def test_workflows_call_litellm_canonical_names(self) -> None:
        for path in (CHAT, TIKA):
            data = json.loads(path.read_text(encoding="utf-8"))
            urls = [
                str(node.get("parameters", {}).get("url", ""))
                for node in data.get("nodes") or []
            ]
            joined = "\n".join(urls)
            self.assertTrue(
                any("http://llm-gateway:4000/v1/chat/completions" in url for url in urls),
                path.name,
            )
            self.assertNotIn(":8888", joined)
            self.assertNotIn(":8082", joined)
            self.assertNotIn(":8083", joined)
            text = path.read_text(encoding="utf-8")
            self.assertIn("Qwen3.8-27B-UD-Q4_K_M", text)
        tika = json.loads(TIKA.read_text(encoding="utf-8"))
        tika_urls = [
            str(node.get("parameters", {}).get("url", ""))
            for node in tika.get("nodes") or []
        ]
        self.assertIn("http://tika:9998/tika", tika_urls)

    def test_manifest_and_docs_match_adr(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["classification"], "optional_profile")
        self.assertEqual(data["version"], "2.35.6")
        self.assertEqual(data["port"], 5678)
        self.assertEqual(data["health_path"], "/healthz")
        adr = ADR.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")
        for needle in (
            "Status: Accepted",
            "optional profile",
            "127.0.0.1:5678",
            "LiteLLM",
            "Sustainable Use License",
        ):
            self.assertIn(needle, adr)
        for needle in (
            "http://127.0.0.1:5678",
            "http://127.0.0.1:4000/v1",
            "ai n8n start",
            "uninstall --purge --confirm",
            "N8N_INSTANCE_AI_MODEL_URL",
            "N8N_SANDBOX_SERVICE_URL",
            "sandbox-api:8080",
            "no TPM/RPM",
            "N8N_LLM_API_KEY",
            "Self-hosted",
        ):
            self.assertIn(needle, doc)

    def test_image_lock_pins_n8n_digest(self) -> None:
        lock = (ROOT / "compose.images.lock.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "docker.n8n.io/n8nio/n8n@sha256:",
            lock,
        )
        manifest = json.loads(
            (ROOT / "config/image-lock.json").read_text(encoding="utf-8")
        )
        n8n = manifest["services"]["n8n"]
        self.assertEqual(n8n["source_type"], "registry")
        self.assertIn("@sha256:", n8n["locked_image"])
        self.assertEqual(
            n8n["configured_image"],
            "docker.n8n.io/n8nio/n8n:2.35.6",
        )
        sandbox_api = manifest["services"]["sandbox-api"]
        self.assertEqual(sandbox_api["source_type"], "registry")
        self.assertIn(
            "n8n-sandbox-service-api@sha256:",
            sandbox_api["locked_image"],
        )
        self.assertIn(
            "n8n-sandbox-service-runner-dind@sha256:",
            lock,
        )


if __name__ == "__main__":
    unittest.main()
