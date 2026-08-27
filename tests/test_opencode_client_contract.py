from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "config/clients/opencode"
TEMPLATE = TEMPLATE_DIR / "opencode.jsonc.template"


def load_jsonc(path: Path) -> dict:
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    return json.loads(text)


class OpenCodeClientContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_jsonc(TEMPLATE)
        cls.station = cls.config["provider"]["ai-station"]
        cls.models = cls.station["models"]

    def test_endpoint_is_litellm_loopback_only(self) -> None:
        self.assertEqual(
            self.station["options"]["baseURL"], "http://127.0.0.1:4000/v1"
        )
        rendered = TEMPLATE.read_text(encoding="utf-8")
        for forbidden in (":8888", ":8083", ":11434", ".gguf"):
            self.assertNotIn(forbidden, rendered)

    def test_template_is_keyless_and_provider_is_curated(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("__AI_STATION_OPENCODE_API_KEY__", text)
        self.assertEqual(self.config["enabled_providers"], ["ai-station"])
        self.assertEqual(set(self.config["provider"]), {"ai-station"})
        self.assertEqual(self.station["npm"], "@ai-sdk/openai-compatible")

    def test_models_match_catalog_and_capabilities(self) -> None:
        expected = {
            "Ornith-1.5-35B-Q4_K_M": (8192, 4096, True),
            "Qwen3.8-27B-UD-Q4_K_M": (262144, 2048, True),
            "Qwen3.8-27B-Reasoning-UD-Q4_K_M": (262144, 2048, True),
        }
        self.assertEqual(set(self.models), set(expected))
        for model_id, (context, output, tools) in expected.items():
            with self.subTest(model=model_id):
                self.assertEqual(self.models[model_id]["limit"]["context"], context)
                self.assertEqual(self.models[model_id]["limit"]["output"], output)
                self.assertIs(self.models[model_id]["tool_call"], tools)

    def test_build_agent_has_a_real_developer_toolchain(self) -> None:
        self.assertEqual(set(self.config["lsp"]), {"pyright", "bash"})
        self.assertEqual(set(self.config["formatter"]), {"ruff", "shfmt"})
        self.assertTrue(self.config["snapshot"])
        self.assertEqual(self.config["permission"]["lsp"], "allow")
        self.assertEqual(self.config["permission"]["skill"], "allow")
        self.assertEqual(self.config["permission"]["attachment_read"], "allow")
        self.assertEqual(self.config["permission"]["external_directory"], "deny")
        build = self.config["agent"]["build"]
        self.assertGreaterEqual(build["steps"], 32)
        self.assertEqual(build["permission"]["edit"], "allow")
        self.assertEqual(build["permission"]["bash"], "allow")
        self.assertEqual(build["permission"]["lsp"], "allow")
        self.assertEqual(build["permission"]["attachment_read"], "allow")
        self.assertEqual(build["permission"]["external_directory"], "deny")

    def test_compaction_uses_supported_native_configuration(self) -> None:
        compaction = self.config["compaction"]
        self.assertEqual(set(compaction), {"auto", "prune", "reserved"})
        self.assertTrue(compaction["auto"])
        self.assertTrue(compaction["prune"])
        self.assertGreaterEqual(compaction["reserved"], 2048)
        self.assertFalse((TEMPLATE_DIR / "agents/compaction.md").exists())
        self.assertFalse(
            (TEMPLATE_DIR / "plugins/disable-compaction-autocontinue.js").exists()
        )
        self.assertTrue((TEMPLATE_DIR / "plugins/local-attachments.js").is_file())

    def test_project_skills_are_discoverable(self) -> None:
        self.assertIn(
            "/opt/ai-station/config/skills", self.config["skills"]["paths"]
        )
        skills = sorted((ROOT / "config/skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 3)

    def test_runtime_install_is_pinned_and_checksum_verified(self) -> None:
        manifest = json.loads(
            (TEMPLATE_DIR / "runtime.json").read_text(encoding="utf-8")
        )
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(manifest["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(f"/v{manifest['version']}/", manifest["url"])
        self.assertEqual(manifest["developer_user"], "aidev")
        self.assertTrue(manifest["install_root"].startswith("/usr/local/lib/"))

        installer = (ROOT / "scripts/install-opencode-wsl.sh").read_text(
            encoding="utf-8"
        )
        toolchain = json.loads(
            (TEMPLATE_DIR / "toolchain.json").read_text(encoding="utf-8")
        )
        self.assertIn("sha256sum --check --status", installer)
        self.assertIn("--create-user", installer)
        self.assertIn("--own-project", installer)
        self.assertIn('if [[ "$(id -u)" -ne 0 ]]', installer)
        self.assertNotIn("curl -fsSL https://opencode.ai/install | bash", installer)
        self.assertEqual(set(toolchain["npm_packages"]), {"pyright", "bash-language-server"})
        self.assertEqual(set(toolchain["python_packages"]), {"ruff"})
        self.assertEqual(toolchain["npm_overrides"], {"minimatch": "9.0.7"})
        self.assertIn("shellcheck", toolchain["apt_packages"])
        self.assertIn("shfmt", toolchain["apt_packages"])
        self.assertIn("TOOLCHAIN_MANIFEST", installer)
        self.assertIn("/usr/local/bin/code", installer)
        self.assertIn("Microsoft VS Code/bin/code", installer)
        self.assertIn("npm audit --audit-level=high", installer)
        self.assertEqual(toolchain["vscode_extension"], "sst-dev.opencode@0.0.13")

    def test_cli_dispatcher_delegates_opencode_to_a_module(self) -> None:
        dispatcher = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        module = (ROOT / "scripts/lib/ai-opencode.sh").read_text(encoding="utf-8")
        self.assertLess(len(dispatcher.splitlines()), 1800)
        self.assertIn('source "$ROOT/scripts/lib/ai-opencode.sh"', dispatcher)
        self.assertNotIn("cmd_opencode() {", dispatcher)
        for command in (
            "install",
            "configure",
            "doctor",
            "parity",
            "run",
            "acceptance",
            "preview",
            "audit-session",
            "desktop",
        ):
            self.assertRegex(module, rf"\b{command}\)")

    def test_doctor_and_acceptance_prove_development_not_just_chat(self) -> None:
        doctor = (ROOT / "scripts/opencode_doctor.py").read_text(encoding="utf-8")
        acceptance = (ROOT / "scripts/opencode_acceptance.py").read_text(
            encoding="utf-8"
        )
        for contract in (
            "non_root_developer",
            "pinned_runtime",
            "developer_tools",
            "language_toolchain",
            "ide_bridge",
            "native_compaction",
            "authenticated_model_access",
        ):
            self.assertIn(contract, doctor)
        self.assertIn("run this acceptance test as the non-root developer user", acceptance)
        self.assertIn("You must edit all three", acceptance)
        self.assertIn('"unittest"', acceptance)
        self.assertIn("return left + right", acceptance)
        self.assertIn("def multiply(", acceptance)
        self.assertIn('"lsp", "diagnostics"', acceptance)
        self.assertIn("PDF_ATTACHMENT_OK", acceptance)
        self.assertIn("02-clean-digital.pdf", acceptance)
        self.assertIn("ORNITH_MODEL", acceptance)

    def test_parity_report_is_honest_and_live_verifiable(self) -> None:
        parity = (ROOT / "scripts/opencode_parity.py").read_text(encoding="utf-8")
        self.assertIn("multi-file implementation and test execution", parity)
        self.assertIn("Proprietary editor tab completion is out of scope.", parity)
        self.assertIn("Cloud-hosted background agents are out of scope", parity)
        self.assertIn('"acceptance"', parity)

    def test_managed_assets_remove_obsolete_compaction_hacks(self) -> None:
        manager = (ROOT / "scripts/opencode_config.py").read_text(encoding="utf-8")
        self.assertIn("removed obsolete managed file", manager)
        self.assertIn('args.dest / "agents/compaction.md"', manager)
        self.assertIn(
            'args.dest / "plugins/disable-compaction-autocontinue.js"', manager
        )
        self.assertIn('glob("opencode.jsonc.bak-*")', manager)
        self.assertNotIn("shutil.copy2", manager)

    def test_build_prompt_requires_inspect_edit_test_report(self) -> None:
        prompt = (TEMPLATE_DIR / "agents/build.md").read_text(encoding="utf-8")
        for term in ("inspect", "edit", "test", "report"):
            self.assertIn(term, prompt)
        self.assertIn("mode: primary", prompt)
        self.assertIn("steps: 40", prompt)
        self.assertIn("external_directory: deny", prompt)

    def test_windows_manager_launches_wsl_non_root_client(self) -> None:
        manager = (ROOT / "AI Station/AI Station Manager.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('-u aidev --cd /opt/ai-station', manager)
        self.assertIn("OPENCODE_EXPERIMENTAL_LSP_TOOL=true", manager)
        self.assertIn('/usr/local/bin/opencode .', manager)

    def test_desktop_guard_keeps_all_wsl_picker_models_visible(self) -> None:
        desktop = (ROOT / "scripts/configure-opencode-desktop.ps1").read_text(
            encoding="utf-8"
        )
        for model_id in self.models:
            self.assertIn(f'"{model_id}" = [ordered]@{{', desktop)
        self.assertIn("native-sidecar-disabled-use-wsl-server", desktop)

    def test_desktop_state_is_scoped_and_migrated_to_wsl_server(self) -> None:
        desktop = (ROOT / "scripts/configure-opencode-desktop.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("$projectsByServer[$ServerUrl]", desktop)
        self.assertIn("$lastProjectByServer[$ServerUrl]", desktop)
        self.assertNotIn('projects = @{ local =', desktop)
        self.assertIn('$_.server -eq "sidecar"', desktop)
        self.assertIn('server = $ServerUrl', desktop)
        self.assertIn('directory = $projectRoot', desktop)
        self.assertIn("ConvertTo-Json -InputObject $remoteTabs", desktop)
        self.assertIn("$hasMalformedRemoteTabs", desktop)
        self.assertIn('Copy-Item -LiteralPath $windowPath', desktop)

    def test_repo_contributing_explains_real_development_loop(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("llama.cpp", contributing)
        self.assertIn("http://127.0.0.1:4000/v1", contributing)
        self.assertIn("smallest relevant code", contributing)
        self.assertIn("make check", contributing)
        self.assertIn("development", contributing)
        self.assertIn("stage", contributing)

    def test_cli_can_update_project_allowlists_in_place(self) -> None:
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        self.assertIn("cmd_projects_update()", cli)
        self.assertIn("ai projects list|create|update|revoke|show", cli)
        self.assertIn("/key/update", cli)

    def test_opencode_manager_context_matches_template(self) -> None:
        manager = (ROOT / "scripts/opencode_config.py").read_text(encoding="utf-8")
        self.assertIn('MODELS["coder"]: (8192, 4096, True)', manager)
        self.assertNotIn("16384", manager)
        doctor = (ROOT / "scripts/opencode_doctor.py").read_text(encoding="utf-8")
        self.assertIn("== 8192", doctor)
        self.assertNotIn("== 16384", doctor)


if __name__ == "__main__":
    unittest.main()
