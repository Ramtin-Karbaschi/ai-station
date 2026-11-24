from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "apps" / "voice" / "webui"))

import sso  # noqa: E402
import patch_sso_backend  # noqa: E402
import station_sso_audit  # noqa: E402


class SsoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_env = dict(os.environ)
        os.environ["AI_STATION_ENV"] = str(self.root / ".env")
        os.environ["AI_STATION_SSO_LOG"] = str(self.root / "login.jsonl")
        sso.count_users_fn = lambda: 1
        sso.count_groups_fn = lambda names: len(names)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        sso.count_users_fn = None
        sso.count_groups_fn = None
        self.temp.cleanup()

    def configure_args(self, *extra: str) -> list[str]:
        os.environ["AI_STATION_OIDC_CLIENT_SECRET"] = "fixture-client-secret"
        return [
            "configure",
            "--issuer",
            "http://127.0.0.1:8091/issuer",
            "--client-id",
            "station-fixture",
            *extra,
        ]


class RoleMappingTests(SsoTestCase):
    def test_admin_member_viewer_and_unmapped(self) -> None:
        self.assertEqual(sso.map_station_role(["ai-station-admin"]), "admin")
        self.assertEqual(sso.map_station_role(["ai-station-member"]), "member")
        self.assertEqual(sso.map_station_role(["ai-station-viewer"]), "viewer")
        self.assertIsNone(sso.map_station_role(["unmapped-group"]))
        self.assertIsNone(sso.map_station_role([]))
        self.assertEqual(sso.openwebui_role("admin"), "admin")
        self.assertEqual(sso.openwebui_role("member"), "user")
        self.assertEqual(sso.openwebui_role("viewer"), "user")
        with self.assertRaises(sso.SSOError):
            sso.openwebui_role("unmapped")

    def test_admin_wins_when_multiple_station_groups_are_claimed(self) -> None:
        self.assertEqual(
            sso.map_station_role(
                ["ai-station-viewer", "ai-station-member", "ai-station-admin"]
            ),
            "admin",
        )

    def test_upstream_role_guard_denies_empty_and_unknown_claims(self) -> None:
        os.environ["OAUTH_ROLES_CLAIM"] = "groups"
        self.assertIsNone(station_sso_audit.station_role_from_claim({"groups": []}))
        self.assertIsNone(
            station_sso_audit.station_role_from_claim({"groups": ["external"]})
        )
        self.assertEqual(
            station_sso_audit.station_role_from_claim(
                {"groups": ["ai-station-viewer"]}
            ),
            "viewer",
        )


class ValidationTests(SsoTestCase):
    def test_issuer_and_client_validation(self) -> None:
        self.assertEqual(sso.validate_issuer("https://login.example.test/tenant"),
                         "https://login.example.test/tenant")
        self.assertEqual(sso.validate_issuer("http://127.0.0.1:9000/issuer"),
                         "http://127.0.0.1:9000/issuer")
        for invalid in (
            "ldaps://example.test",
            "http://idp.example.test/issuer",
            "https://user:pass@example.test/issuer",
            "https://example.test/issuer?next=x",
            "https://example.test/issuer#fragment",
            "https://example.test:bad/issuer",
            "http://127.0.0.1:99999/issuer",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(sso.SSOError):
                sso.validate_issuer(invalid)
        self.assertEqual(sso.validate_client_id("station-fixture"), "station-fixture")
        for invalid_client in ("", "   ", "bad client", "x\nsecret"):
            with self.subTest(invalid_client=invalid_client), self.assertRaises(sso.SSOError):
                sso.validate_client_id(invalid_client)

    def test_probe_requires_matching_issuer_and_secure_endpoints(self) -> None:
        payload = {
            "issuer": "http://127.0.0.1:8091/issuer",
            "jwks_uri": "http://127.0.0.1:8091/jwks",
            "authorization_endpoint": "http://127.0.0.1:8091/authorize",
            "token_endpoint": "http://127.0.0.1:8091/token",
        }
        report = sso.probe_issuer(
            payload["issuer"], fetch_fn=lambda _url: json.dumps(payload).encode()
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["issuer"], payload["issuer"])
        wrong = dict(payload, issuer="http://127.0.0.1:8092/issuer")
        with self.assertRaises(sso.SSOError):
            sso.probe_issuer(
                payload["issuer"], fetch_fn=lambda _url: json.dumps(wrong).encode()
            )
        unsafe = dict(payload, token_endpoint="http://idp.example.test/token")
        with self.assertRaises(sso.SSOError):
            sso.probe_issuer(
                payload["issuer"], fetch_fn=lambda _url: json.dumps(unsafe).encode()
            )

    def test_redirect_uri_must_use_oidc_callback_path(self) -> None:
        self.assertEqual(
            sso.validate_redirect_uri("http://127.0.0.1:3000/oauth/oidc/callback"),
            "http://127.0.0.1:3000/oauth/oidc/callback",
        )
        with self.assertRaises(sso.SSOError):
            sso.validate_redirect_uri("http://127.0.0.1:3000/other")


class ConfigurationTests(SsoTestCase):
    def test_dry_run_redacts_secret_and_does_not_write_config(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = sso.main(self.configure_args("--dry-run"))
        self.assertEqual(result, 0)
        self.assertFalse((self.root / ".env").exists())
        report = json.loads(output.getvalue())
        self.assertEqual(report["ENABLE_OAUTH"], "True")
        self.assertEqual(report["OAUTH_CLIENT_SECRET"], "set")
        self.assertNotIn("fixture-client-secret", output.getvalue())
        self.assertIn("/.well-known/openid-configuration", report["OPENID_PROVIDER_URL"])
        self.assertEqual(report["OAUTH_MERGE_ACCOUNTS_BY_EMAIL"], "False")

    def test_live_configuration_requires_local_admin_and_all_role_groups(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = sso.main(self.configure_args())
        self.assertEqual(result, 0)
        configured = sso.load_env_file()
        self.assertEqual(configured["ENABLE_OAUTH"], "True")
        self.assertEqual(configured["ENABLE_OAUTH_GROUP_MANAGEMENT"], "True")
        self.assertEqual(configured["ENABLE_OAUTH_GROUP_CREATION"], "False")
        self.assertEqual(configured["AI_STATION_SSO_ENFORCE_ROLE_GROUPS"], "True")
        self.assertEqual(configured["OAUTH_CLIENT_SECRET"], "fixture-client-secret")
        self.assertNotIn("fixture-client-secret", output.getvalue())

    def test_configuration_refuses_when_break_glass_admin_or_groups_missing(self) -> None:
        sso.count_users_fn = lambda: 0
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sso.main(self.configure_args()), 1)
        self.assertFalse((self.root / ".env").exists())
        sso.count_users_fn = lambda: 1
        sso.count_groups_fn = lambda _names: 2
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sso.main(self.configure_args()), 1)
        self.assertFalse((self.root / ".env").exists())

    def test_env_updates_are_atomic_private_and_preserve_unrelated_values(self) -> None:
        target = self.root / ".env"
        previous_umask = os.umask(0o022)
        try:
            sso.upsert_env_file(
                {"OAUTH_CLIENT_SECRET": "fixture-secret", "ENABLE_OAUTH": "True"},
                path=target,
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            target.write_text("PRESERVE_ME=yes\nENABLE_OAUTH=False\n", encoding="utf-8")
            target.chmod(0o644)
            sso.upsert_env_file(
                {"OAUTH_CLIENT_SECRET": "fixture-secret", "ENABLE_OAUTH": "True"},
                path=target,
            )
        finally:
            os.umask(previous_umask)
        contents = target.read_text(encoding="utf-8")
        self.assertIn("PRESERVE_ME=yes", contents)
        self.assertIn("ENABLE_OAUTH=True", contents)
        self.assertEqual(contents.count("OAUTH_CLIENT_SECRET="), 1)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_blank_client_id_and_group_alias_collision_are_refused(self) -> None:
        args = self.configure_args()
        args[args.index("station-fixture")] = ""
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sso.main(args), 1)
        collision = self.configure_args("--viewer-group", "ai-station-member")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sso.main(collision), 1)
        casefold_collision = self.configure_args(
            "--member-group", "AI-STATION-ADMIN"
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sso.main(casefold_collision), 1)


class AuditTests(SsoTestCase):
    def test_audit_is_content_free_and_private(self) -> None:
        record = station_sso_audit.record_station_login(
            subject="fixture-subject",
            email="fixture-user@example.test",
            role="viewer",
            provider="oidc",
        )
        encoded = json.dumps(record).casefold()
        for forbidden in ("fixture-user@example.test", "access_token", "prompt", "messages"):
            self.assertNotIn(forbidden, encoded)
        self.assertNotIn("prompt", json.dumps(record))
        self.assertEqual(stat.S_IMODE((self.root / "login.jsonl").stat().st_mode), 0o600)
        self.assertEqual(len((self.root / "login.jsonl").read_text().splitlines()), 1)


class BackendPatchTests(unittest.TestCase):
    def test_pinned_patch_inserts_guard_audit_and_scrubs_sensitive_logs(self) -> None:
        fixture = """from __future__ import annotations
def callback_logs():
    log.error(f'Invalid token response for client_id {client_id}: {token}')
    log.warning(f'OAuth callback failed, user data is missing: {token}')
    log.warning(f'OAuth callback failed, sub is missing: {user_data}')
    log.warning(f'OAuth callback failed, email is missing: {user_data}')
    log.warning(f'OAuth callback failed, e-mail domain is not in the list of allowed domains: {user_data}')
class M:
    async def get_user_role(self, user, user_data):
        auth_config = await get_oauth_runtime_config()
        user_count = await Users.get_num_users()
        if user and user_count == 1:
            # If the user is the only user, assign the role "admin" - actually repairs role for single user on login
            log.debug('Assigning the only user the admin role')
            return 'admin'
        if not user and user_count == 0:
            log.debug('First user bootstrap: using default role')
            return auth_config.DEFAULT_USER_ROLE

async def callback_errors(client, request, provider, auth_params):
            try:
                token = await client.authorize_access_token(request, **auth_params)
            except BadSignatureError:
                log.warning('OIDC bad signature')
                if True:
                    pass
                try:
                    token = await client.authorize_access_token(request, **auth_params)
                except Exception as retry_exc:
                    detailed_error = _build_oauth_callback_error_message(retry_exc)
                    log.warning(
                        'OAuth callback error during authorize_access_token retry for provider %s: %s',
                        provider,
                        detailed_error,
                        exc_info=True,
                    )
                    raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
            except Exception as e:
                detailed_error = _build_oauth_callback_error_message(e)
                log.warning(
                    'OAuth callback error during authorize_access_token for provider %s: %s',
                    provider,
                    detailed_error,
                    exc_info=True,
                )
                raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)

async def post_insert(user, user_data, auth_config, db):
                    if await Users.get_num_users(db=db) == 1:
                        await Users.update_user_role_by_id(user.id, 'admin', db=db)
                        user = await Users.get_user_by_id(user.id, db=db)

async def callback(self):
        try:
            if auth_config.ENABLE_OAUTH_GROUP_MANAGEMENT:
                await self.update_user_groups(
                    user=user,
                    user_data=user_data,
                    default_permissions=await Config.get('user.permissions'),
                    db=db,
                )

        except Exception as e:
            log.error(f'Error during OAuth process: {e}')
"""
        patched = patch_sso_backend.patch_source(fixture)
        self.assertIn("station_role_from_claim(user_data)", patched)
        self.assertIn("record_station_login(", patched)
        self.assertNotIn("{token}", patched)
        self.assertNotIn("{user_data}", patched)
        self.assertNotIn("detailed_error", patched)
        self.assertNotIn("exc_info=True", patched)
        self.assertIn("user_count == 0 and station_role != 'admin'", patched)
        self.assertIn("auth_config.ENABLE_OAUTH_ROLE_MANAGEMENT and getattr(user, 'oauth', None)", patched)
        self.assertIn("station_role_from_claim(user_data) == 'admin'", patched)

    def test_patch_fails_closed_on_unrecognized_upstream_source(self) -> None:
        with self.assertRaises(ValueError):
            patch_sso_backend.patch_source("from __future__ import annotations\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
