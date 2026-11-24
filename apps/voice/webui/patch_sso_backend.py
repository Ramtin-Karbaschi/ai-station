"""Patch the pinned Open WebUI OAuth callback with Station's OIDC gates."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Unexpected Open WebUI OAuth anchor count {count}: {old.splitlines()[0]}")
    return source.replace(old, new, 1)


ROLE_GATE = """        auth_config = await get_oauth_runtime_config()
        user_count = await Users.get_num_users()
"""
ROLE_GATE_PATCH = """        auth_config = await get_oauth_runtime_config()
        user_count = await Users.get_num_users()
        if auth_config.ENABLE_OAUTH_ROLE_MANAGEMENT:
            from open_webui.utils.station_sso_audit import station_role_from_claim

            station_role = station_role_from_claim(user_data)
            if station_role is None or (
                user is None and user_count == 0 and station_role != 'admin'
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
                )
"""

SOLE_USER_PROMOTION = """        if user and user_count == 1:
            # If the user is the only user, assign the role "admin" - actually repairs role for single user on login
            log.debug('Assigning the only user the admin role')
            return 'admin'
"""
SOLE_USER_PROMOTION_PATCH = """        if user and user_count == 1 and not (
            auth_config.ENABLE_OAUTH_ROLE_MANAGEMENT and getattr(user, 'oauth', None)
        ):
            # Keep Open WebUI's native repair for local and non-Station users.
            log.debug('Assigning the only user the admin role')
            return 'admin'
"""

FIRST_USER_PROMOTION = """                    if await Users.get_num_users(db=db) == 1:
                        await Users.update_user_role_by_id(user.id, 'admin', db=db)
                        user = await Users.get_user_by_id(user.id, db=db)
"""

AUDIT_ANCHOR = """            if auth_config.ENABLE_OAUTH_GROUP_MANAGEMENT:
                await self.update_user_groups(
                    user=user,
                    user_data=user_data,
                    default_permissions=await Config.get('user.permissions'),
                    db=db,
                )

        except Exception as e:
"""
AUDIT_PATCH = """            if auth_config.ENABLE_OAUTH_GROUP_MANAGEMENT:
                await self.update_user_groups(
                    user=user,
                    user_data=user_data,
                    default_permissions=await Config.get('user.permissions'),
                    db=db,
                )
            from open_webui.utils.station_sso_audit import (
                record_station_login,
                station_role_from_claim,
            )

            station_role = station_role_from_claim(user_data)
            if station_role is None:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
                )
            try:
                record_station_login(
                    subject=str(user.id),
                    email=str(user.email or ''),
                    role=station_role,
                    provider=str(provider),
                )
            except Exception as exc:
                log.error('Station SSO audit write failed; refusing OAuth login')
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail='Authentication audit unavailable',
                ) from exc
        except Exception as e:
"""


SAFE_LOGS = (
    (
        "log.error(f'Invalid token response for client_id {client_id}: {token}')",
        "log.error('Invalid token response for configured OIDC client')",
    ),
    (
        "log.warning(f'OAuth callback failed, user data is missing: {token}')",
        "log.warning('OAuth callback failed: user data is missing')",
    ),
    (
        "log.warning(f'OAuth callback failed, sub is missing: {user_data}')",
        "log.warning('OAuth callback failed: subject claim is missing')",
    ),
    (
        "log.warning(f'OAuth callback failed, email is missing: {user_data}')",
        "log.warning('OAuth callback failed: email claim is missing')",
    ),
    (
        "log.warning(f'OAuth callback failed, e-mail domain is not in the list of allowed domains: {user_data}')",
        "log.warning('OAuth callback failed: email domain is not allowed')",
    ),
    (
        "log.error(f'Error during OAuth process: {e}')",
        "log.error('OAuth callback failed during account processing')",
    ),
    (
        """                    detailed_error = _build_oauth_callback_error_message(retry_exc)
                    log.warning(
                        'OAuth callback error during authorize_access_token retry for provider %s: %s',
                        provider,
                        detailed_error,
                        exc_info=True,
                    )""",
        """                    log.warning(
                        'OIDC callback token exchange retry failed for provider %s',
                        provider,
                    )""",
    ),
    (
        """                detailed_error = _build_oauth_callback_error_message(e)
                log.warning(
                    'OAuth callback error during authorize_access_token for provider %s: %s',
                    provider,
                    detailed_error,
                    exc_info=True,
                )""",
        """                log.warning(
                    'OIDC callback token exchange failed for provider %s',
                    provider,
                )""",
    ),
)


def patch_source(source: str) -> str:
    marker = "# AI_STATION_OIDC_GUARD_AND_AUDIT"
    if marker in source:
        raise ValueError("Station OIDC patch is already present")
    patched = source
    for old, new in SAFE_LOGS:
        patched = replace_once(patched, old, new)
    patched = replace_once(patched, ROLE_GATE, ROLE_GATE_PATCH)
    patched = replace_once(patched, SOLE_USER_PROMOTION, SOLE_USER_PROMOTION_PATCH)
    patched = replace_once(
        patched,
        FIRST_USER_PROMOTION,
        """                    if await Users.get_num_users(db=db) == 1:
                        if not auth_config.ENABLE_OAUTH_ROLE_MANAGEMENT:
                            await Users.update_user_role_by_id(user.id, 'admin', db=db)
                            user = await Users.get_user_by_id(user.id, db=db)
                        else:
                            from open_webui.utils.station_sso_audit import station_role_from_claim

                            if station_role_from_claim(user_data) == 'admin':
                                await Users.update_user_role_by_id(user.id, 'admin', db=db)
                                user = await Users.get_user_by_id(user.id, db=db)
                            else:
                                raise HTTPException(
                                    status.HTTP_403_FORBIDDEN,
                                    detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
                                )
""",
    )
    patched = replace_once(patched, AUDIT_ANCHOR, AUDIT_PATCH)
    patched = marker + "\n" + patched
    ast.parse(patched)
    return patched


def patch_backend(root: Path) -> None:
    target = root / "utils" / "oauth.py"
    source = target.read_text(encoding="utf-8")
    target.write_text(patch_source(source), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Open WebUI backend package directory")
    patch_backend(parser.parse_args().root)
    print("patched pinned Open WebUI OAuth callback with Station guard and audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
