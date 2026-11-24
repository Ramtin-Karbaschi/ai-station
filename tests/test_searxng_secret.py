from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import searxng_secret


class SearXNGSecretTests(unittest.TestCase):
    def test_provision_is_idempotent_private_and_preserves_other_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            original = (
                "COMPOSE_FILE=compose.yml:compose.images.lock.yaml\n"
                "# Preserve this operator comment\n"
                "EXISTING_VALUE=keep-me\n"
                "SEARXNG_SECRET=\n"
            )
            env_file.write_text(original, encoding="utf-8")
            env_file.chmod(0o644)

            self.assertTrue(searxng_secret.provision(env_file))
            first = env_file.read_text(encoding="utf-8")
            values = [
                line.split("=", 1)[1]
                for line in first.splitlines()
                if line.startswith("SEARXNG_SECRET=")
            ]
            self.assertEqual(len(values), 1)
            self.assertRegex(values[0], re.compile(r"^[A-Za-z0-9_-]{48}$"))
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
            self.assertIn("COMPOSE_FILE=compose.yml:compose.images.lock.yaml\n", first)
            self.assertIn("# Preserve this operator comment\n", first)
            self.assertIn("EXISTING_VALUE=keep-me\n", first)
            self.assertTrue(searxng_secret.status(env_file))

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    searxng_secret.main(
                        ["provision", "--env-file", str(env_file)]
                    ),
                    0,
                )
            self.assertEqual(env_file.read_text(encoding="utf-8"), first)
            self.assertNotIn(values[0], stdout.getvalue())
            self.assertIn("no service restarted", stdout.getvalue())

    def test_missing_entry_is_appended_without_replacing_compose_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("COMPOSE_FILE=compose.yml\nOTHER=unchanged\n", encoding="utf-8")

            self.assertTrue(searxng_secret.provision(env_file))
            result = env_file.read_text(encoding="utf-8")
            self.assertIn("COMPOSE_FILE=compose.yml\n", result)
            self.assertIn("OTHER=unchanged\n", result)
            self.assertEqual(sum(line.startswith("SEARXNG_SECRET=") for line in result.splitlines()), 1)
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_duplicate_or_symlinked_env_is_rejected_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".env"
            env_file.write_text(
                "SEARXNG_SECRET=first\nSEARXNG_SECRET=second\n", encoding="utf-8"
            )
            original = env_file.read_text(encoding="utf-8")
            with self.assertRaises(searxng_secret.SecretConfigError):
                searxng_secret.provision(env_file)
            with self.assertRaises(searxng_secret.SecretConfigError):
                searxng_secret.status(env_file)
            self.assertEqual(env_file.read_text(encoding="utf-8"), original)

            target = root / "target.env"
            target.write_text("OTHER=keep\n", encoding="utf-8")
            link = root / "link.env"
            link.symlink_to(target)
            with self.assertRaises(searxng_secret.SecretConfigError):
                searxng_secret.provision(link)
            self.assertEqual(target.read_text(encoding="utf-8"), "OTHER=keep\n")

    def test_missing_env_is_not_created_by_provision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            self.assertFalse(searxng_secret.status(env_file))
            with self.assertRaises(searxng_secret.SecretConfigError):
                searxng_secret.provision(env_file)
            self.assertFalse(env_file.exists())

    def test_compose_uses_env_and_settings_do_not_contain_static_signing_key(self) -> None:
        compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["searxng"]
        self.assertEqual(service["environment"]["SEARXNG_SECRET"], "${SEARXNG_SECRET:-}")
        self.assertEqual(
            service["entrypoint"], ["/bin/sh", "/etc/searxng/secret-entrypoint.sh"]
        )
        guard = (ROOT / "infra/searxng/secret-entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("if [ -z \"${SEARXNG_SECRET:-}\" ]", guard)
        self.assertIn("exec /usr/local/searxng/entrypoint.sh", guard)
        self.assertEqual(service["volumes"][0], "./infra/searxng:/etc/searxng:ro")

        settings = yaml.safe_load(
            (ROOT / "infra" / "searxng" / "settings.yml").read_text(encoding="utf-8")
        )
        self.assertNotIn("secret_key", settings.get("server", {}))

        example_lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            sum(line.strip() == "SEARXNG_SECRET=" for line in example_lines), 1
        )

    def test_existing_installer_generates_blank_secret_values_privately(self) -> None:
        installer = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('r"(PASSWORD|SECRET|ENCRYPTION_KEY)"', installer)
        self.assertIn('secrets.token_urlsafe(36)', installer)
        self.assertIn('chmod 0600 .env', installer)


if __name__ == "__main__":
    unittest.main()
