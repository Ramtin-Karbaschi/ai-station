from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.gateway.app import paths as gateway_paths


ROOT = Path(__file__).resolve().parents[1]


class GatewayProjectDirTests(unittest.TestCase):
    def test_env_override_wins(self) -> None:
        override = ROOT / "apps"
        with patch.dict(os.environ, {"AI_STATION_PROJECT_DIR": str(override)}):
            self.assertEqual(gateway_paths.project_dir(), override.resolve())

    def test_walks_to_repo_when_installed_catalog_is_absent(self) -> None:
        env = os.environ.copy()
        env.pop("AI_STATION_PROJECT_DIR", None)
        with patch.dict(os.environ, env, clear=True), patch.object(
            gateway_paths,
            "INSTALLED_ROOT",
            Path("/nonexistent/ai-station"),
        ):
            found = gateway_paths.project_dir()
        self.assertEqual(found, ROOT)
        self.assertTrue((found / "config/model-catalog.json").is_file())

    def test_imported_gateway_catalog_exists(self) -> None:
        from apps.gateway.app import main as gateway_main

        self.assertTrue(Path(gateway_main.CATALOG_PATH).is_file(), gateway_main.CATALOG_PATH)
