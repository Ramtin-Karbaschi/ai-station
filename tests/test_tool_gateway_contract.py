#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

from apps.tool_gateway.app.contracts import SearchRequest
from apps.tool_gateway.app.main import _entity_score, _verified_asset_media_type, app


ROOT = Path(__file__).resolve().parents[1]


class ToolGatewayContractTests(unittest.TestCase):
    def test_typed_routes_are_published(self) -> None:
        paths = {route.path for route in app.routes}
        for path in (
            "/healthz",
            "/v1/capabilities",
            "/v1/search",
            "/v1/fetch",
            "/v1/entities/resolve",
            "/v1/assets/import",
        ):
            self.assertIn(path, paths)

    def test_search_contract_is_bounded(self) -> None:
        request = SearchRequest(query="Kia Pride", limit=20)
        self.assertEqual(request.limit, 20)
        with self.assertRaises(ValueError):
            SearchRequest(query="Kia Pride", limit=21)

    def test_service_is_loopback_only_and_managed_by_cli(self) -> None:
        unit = (ROOT / "infra/systemd/ai-station-tool-gateway.service").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/ai").read_text(encoding="utf-8")
        tool_lib = (ROOT / "scripts/lib/ai-tools.sh").read_text(encoding="utf-8")
        user_unit = (ROOT / "infra/systemd/user/ai-station-tool-gateway.service").read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1 --port 8892", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn('source "$ROOT/scripts/lib/ai-tools.sh"', cli)
        self.assertIn('tools) cmd_tools "$@"', cli)
        self.assertIn("http://127.0.0.1:8892", tool_lib)
        self.assertIn("systemctl --user", tool_lib)
        self.assertIn("WantedBy=default.target", user_unit)
        self.assertTrue((ROOT / "scripts/install-tool-gateway-user.sh").is_file())
        start_fn = tool_lib.split("ai_tools_start()", 1)[1].split("ai_tools_stop()", 1)[0]
        self.assertIn("already healthy", start_fn)
        self.assertIn("id -u", start_fn)
        self.assertIn("/etc/systemd/system", tool_lib)
        self.assertIn("install-tool-gateway-user.sh", start_fn)
        self.assertIn("ai_tools_user_unit_exists", start_fn)
        self.assertIn("ai_tools_install_system_unit", start_fn)
        user_restart_index = start_fn.find('systemctl --user restart')
        self.assertGreater(user_restart_index, start_fn.find("ai_tools_user_unit_exists"))

    def test_searxng_json_and_safe_search_are_enabled(self) -> None:
        settings = (ROOT / "infra/searxng/settings.yml").read_text(encoding="utf-8")
        self.assertIn("formats:", settings)
        self.assertIn("- json", settings)
        self.assertIn("safe_search: 1", settings)

    def test_asset_type_is_verified_from_bytes(self) -> None:
        self.assertEqual(_verified_asset_media_type(b"\x89PNG\r\n\x1a\nrest", "image/png"), "image/png")
        with self.assertRaises(Exception):
            _verified_asset_media_type(b"<html>not an image</html>", "image/png")

    def test_place_kind_disambiguates_landmark_from_same_named_film(self) -> None:
        bridge = _entity_score(
            "Si-o-Se Pol", "Si-o-se Pol", "bridge in Isfahan, Iranian heritage site", "place"
        )
        film = _entity_score("Si-o-Se Pol", "Si-o-se Pol", "2013 film", "place")
        self.assertGreaterEqual(bridge, 0.94)
        self.assertGreater(bridge - film, 0.06)


if __name__ == "__main__":
    unittest.main()
