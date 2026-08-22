#!/usr/bin/env python3
from __future__ import annotations

import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QualityGateContractTests(unittest.TestCase):
    def test_canonical_runner_is_wired_everywhere(self) -> None:
        runner = (ROOT / "scripts/test.sh").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        release = (ROOT / "scripts/release-audit.sh").read_text(encoding="utf-8")

        self.assertIn("unittest discover", runner)
        self.assertIn(".venvs/gateway/bin/python", runner)
        self.assertIn("test:\n\t./scripts/ai test", makefile)
        self.assertIn("check:", makefile)
        self.assertIn("test) cmd_test", cli)
        self.assertIn("scripts/test.sh", release)
        lock = (ROOT / "scripts/verify-image-lock.sh").read_text(encoding="utf-8")
        self.assertIn("--require-local", lock)
        self.assertIn("AI_STATION_IMAGE_LOCK_REQUIRE_LOCAL", lock)
        installer = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        self.assertIn("verify-image-lock.sh --require-local", installer)
        self.assertIn(
            'export AI_STATION_PROJECT_DIR="${AI_STATION_PROJECT_DIR:-$ROOT}"',
            runner,
        )

    def test_runner_resolves_unqualified_python_command_names(self) -> None:
        import shutil
        import subprocess
        import tempfile

        runner = ROOT / "scripts/test.sh"
        real = shutil.which("python3") or shutil.which("python")
        self.assertIsNotNone(real, "need python3 or python on PATH")
        names = [name for name in ("python3", "python") if shutil.which(name)]
        for name in names:
            result = subprocess.run(
                [str(runner), "--print-python"],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AI_STATION_TEST_PYTHON": name},
            )
            printed = result.stdout.strip()
            self.assertTrue(os.access(printed, os.X_OK), printed)
            self.assertTrue(Path(printed).is_file(), printed)

        with tempfile.TemporaryDirectory() as directory:
            shim = Path(directory) / "python"
            shim.symlink_to(real)
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            env["AI_STATION_TEST_PYTHON"] = "python"
            result = subprocess.run(
                [str(runner), "--print-python"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            printed = Path(result.stdout.strip())
            self.assertTrue(printed.is_file())
            self.assertTrue(os.access(printed, os.X_OK))

    def test_operator_scripts_are_executable(self) -> None:
        for relative in (
            "scripts/test.sh",
            "scripts/model_manager.py",
            "scripts/install-opencode-wsl.sh",
            "scripts/ensure-wsl-idle-timeout.sh",
            "scripts/verify-startup-stability.sh",
            "scripts/uninstall-comfyui-experimental.sh",
            "scripts/comfyui-media-smoke.sh",
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertTrue(os.access(path, os.X_OK), relative)

    def test_live_default_is_llama_cpp_not_an_internal_gateway(self) -> None:
        runner = (ROOT / "scripts/test.sh").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8082/v1", runner)
        self.assertNotIn("http://127.0.0.1:8083/v1", runner)

    def test_application_endpoint_remains_litellm(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        for text in (readme, cli):
            self.assertIn("http://127.0.0.1:4000/v1", text)

    def test_live_adr_index_excludes_superseded_compaction_note(self) -> None:
        index = (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
        self.assertIn("ADR-009", index)
        self.assertIn("ADR-013", index)
        self.assertFalse(
            (ROOT / "docs/adr/ADR-010-opencode-compaction-task-loss-fix.md").exists()
        )

    def test_github_metadata_is_untracked(self) -> None:
        import subprocess

        tracked = subprocess.check_output(
            ["git", "ls-files", ".github"], cwd=ROOT, text=True
        )
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(tracked.strip(), "")
        self.assertNotIn("!.github/", gitignore)
        self.assertNotIn("!.github/**", gitignore)

    def test_tracked_files_do_not_name_vendor_editor(self) -> None:
        import subprocess

        needle = bytes.fromhex("637572736f72").decode("ascii")
        listed = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        )
        for raw in listed.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8")
            path = ROOT / relative
            if relative == ".gitignore" or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                self.assertNotIn(
                    needle,
                    line.lower(),
                    f"{relative}:{line_number}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
