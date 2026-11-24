#!/usr/bin/env python3
"""OIDC SSO policy for human users (ADR-030). LDAP is not supported."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse
from urllib.request import urlopen

DEFAULT_ADMIN_GROUP = "ai-station-admin"
DEFAULT_MEMBER_GROUP = "ai-station-member"
DEFAULT_VIEWER_GROUP = "ai-station-viewer"
STATION_ROLES = ("admin", "member", "viewer")
SECRET_ENV_KEYS = frozenset({"OAUTH_CLIENT_SECRET"})
LOGIN_FORBIDDEN = re.compile(
    r"\b(prompt|messages|content|completion|authorization|bearer|access_token|"
    r"id_token|refresh_token|client_secret)\b",
    re.IGNORECASE,
)
ISSUER_RE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")
LOOPBACK_HTTP_RE = re.compile(
    r"^http://(127\.0\.0\.1|localhost)(:[0-9]+)?(/.*)?$",
    re.IGNORECASE,
)
LDAP_FORBIDDEN = re.compile(
    r"\b(ENABLE_LDAP|LDAP_SERVER|LDAP_BIND|ldap://|ldaps://)\b",
    re.IGNORECASE,
)


class SSOError(RuntimeError):
    """SSO configuration failed."""


CountUsersFn = Callable[[], int | None]
FetchFn = Callable[[str], bytes]
count_users_fn: CountUsersFn | None = None


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def discovery_url(issuer: str) -> str:
    trimmed = issuer.rstrip("/")
    if trimmed.endswith("/.well-known/openid-configuration"):
        return trimmed
    return trimmed + "/.well-known/openid-configuration"


def _count_users_postgres() -> int | None:
    script = project_root() / "scripts" / "compose-ai-station.sh"
    try:
        proc = subprocess.run(
            [
                str(script),
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "openwebui",
                "-d",
                "openwebui",
                "-Atc",
                "SELECT count(*) FROM auth;",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_root()),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return int(lines[-1])
    except ValueError:
        return None


def count_local_operators() -> int | None:
    fn = count_users_fn or _count_users_postgres
    return fn()


def require_local_operator() -> int:
    count = count_local_operators()
    if count is None:
        raise SSOError(
            "cannot count Open WebUI users (postgres not reachable). "
            "Start the stack and create the break-glass operator before "
            "ai sso configure"
        )
    if count < 1:
        raise SSOError(
            "Open WebUI has no local operator. Create the break-glass "
            "account before enabling OAuth signup"
        )
    return count


def probe_issuer(issuer: str, fetch_fn: FetchFn | None = None) -> dict[str, Any]:
    validated = validate_issuer(issuer)
    url = discovery_url(validated)
    fetch = fetch_fn or _fetch_bytes
    try:
        raw = fetch(url)
    except SSOError:
        raise
    except Exception as exc:
        raise SSOError(f"issuer discovery failed: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SSOError("issuer discovery returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise SSOError("issuer discovery returned a non-object")
    issuer_claim = str(payload.get("issuer") or "").strip()
    jwks = str(payload.get("jwks_uri") or "").strip()
    if not issuer_claim or not jwks:
        raise SSOError("discovery document missing issuer or jwks_uri")
    return {
        "ok": True,
        "discovery_url": url,
        "issuer": issuer_claim,
        "jwks_uri": jwks,
        "authorization_endpoint": bool(payload.get("authorization_endpoint")),
        "token_endpoint": bool(payload.get("token_endpoint")),
    }


def _fetch_bytes(url: str) -> bytes:
    try:
        with urlopen(url, timeout=10) as resp:
            return resp.read(1_048_576)
    except Exception as exc:
        raise SSOError(f"issuer discovery HTTP failed: {exc}") from exc


def env_path() -> Path:
    override = os.environ.get("AI_STATION_ENV")
    if override:
        return Path(override)
    return project_root() / ".env"


def login_log_path() -> Path:
    override = os.environ.get("AI_STATION_SSO_LOG")
    if override:
        return Path(override)
    return data_root() / "runtime" / "sso" / "login.jsonl"


@dataclass(frozen=True)
class GroupPolicy:
    admin_groups: tuple[str, ...] = (DEFAULT_ADMIN_GROUP,)
    member_groups: tuple[str, ...] = (DEFAULT_MEMBER_GROUP,)
    viewer_groups: tuple[str, ...] = (DEFAULT_VIEWER_GROUP,)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "admin_groups": list(self.admin_groups),
            "member_groups": list(self.member_groups),
            "viewer_groups": list(self.viewer_groups),
        }


def parse_groups(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r"[,;|\s]+", value)
        return tuple(item.strip() for item in parts if item.strip())
    return tuple(str(item).strip() for item in value if str(item).strip())


def map_station_role(
    groups: Iterable[str],
    policy: GroupPolicy | None = None,
) -> str:
    """Map IdP groups to Admin / Member / Viewer. Unmapped is Viewer, never Admin."""
    current = policy or GroupPolicy()
    claimed = {item.casefold() for item in parse_groups(list(groups))}
    if claimed & {item.casefold() for item in current.admin_groups}:
        return "admin"
    if claimed & {item.casefold() for item in current.member_groups}:
        return "member"
    return "viewer"


def openwebui_role(station_role: str) -> str:
    if station_role == "admin":
        return "admin"
    return "user"


def validate_issuer(url: str) -> str:
    text = url.strip()
    if not text:
        raise SSOError("OIDC issuer URL is required")
    if "ldap" in text.casefold():
        raise SSOError("LDAP URLs are not a supported identity path")
    parsed = urlparse(text)
    if parsed.scheme not in {"https", "http"}:
        raise SSOError("issuer must be an https URL (http only on loopback)")
    if parsed.scheme == "http" and not LOOPBACK_HTTP_RE.match(text):
        raise SSOError("http issuers are allowed only on 127.0.0.1 or localhost")
    if parsed.scheme == "https" and not ISSUER_RE.match(text):
        raise SSOError("issuer URL is not a valid https URL")
    return text


def oauth_env(
    *,
    enabled: bool,
    issuer: str = "",
    client_id: str = "",
    client_secret: str = "",
    provider_name: str = "SSO",
    policy: GroupPolicy | None = None,
) -> dict[str, str]:
    current = policy or GroupPolicy()
    allowed = ",".join(
        list(current.admin_groups)
        + list(current.member_groups)
        + list(current.viewer_groups)
    )
    admin = ",".join(current.admin_groups)
    flag = "True" if enabled else "False"
    return {
        "ENABLE_SIGNUP": "False",
        "ENABLE_LOGIN_FORM": "True",
        "ENABLE_PASSWORD_AUTH": "True",
        "ENABLE_OAUTH": flag,
        "ENABLE_OAUTH_SIGNUP": flag,
        "ENABLE_OAUTH_ROLE_MANAGEMENT": flag,
        "ENABLE_OAUTH_PERSISTENT_CONFIG": "False",
        "ENABLE_PROFILE_IMAGE_URL_FORWARDING": "False",
        "OPENID_PROVIDER_URL": issuer if enabled else issuer,
        "OAUTH_CLIENT_ID": client_id,
        "OAUTH_CLIENT_SECRET": client_secret,
        "OAUTH_PROVIDER_NAME": provider_name or "SSO",
        "OAUTH_SCOPES": "openid email profile groups",
        "OAUTH_ROLES_CLAIM": "groups",
        "OAUTH_ALLOWED_ROLES": allowed,
        "OAUTH_ADMIN_ROLES": admin,
        "OAUTH_MERGE_ACCOUNTS_BY_EMAIL": "False",
        "DEFAULT_USER_ROLE": "user",
        "OPENID_REDIRECT_URI": "http://127.0.0.1:3000/oauth/oidc/callback",
    }


def redact_env(values: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in values.items():
        if key in SECRET_ENV_KEYS:
            redacted[key] = "set" if value else "unset"
        else:
            redacted[key] = value
    return redacted


def load_env_file(path: Path | None = None) -> dict[str, str]:
    target = path or env_path()
    values: dict[str, str] = {}
    try:
        if not target.is_file():
            return values
        text = target.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def upsert_env_file(
    updates: Mapping[str, str],
    *,
    path: Path | None = None,
) -> Path:
    target = path or env_path()
    existing: list[str]
    try:
        existing = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        existing = []
    seen: set[str] = set()
    lines: list[str] = []
    for raw in existing:
        if "=" in raw and not raw.lstrip().startswith("#"):
            name = raw.split("=", 1)[0].strip()
            if name in updates:
                lines.append(f"{name}={updates[name]}")
                seen.add(name)
                continue
        lines.append(raw)
    missing = [key for key in updates if key not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# OIDC SSO (ADR-030). Do not commit real values.")
        for key in missing:
            lines.append(f"{key}={updates[key]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    target.write_text(payload, encoding="utf-8")
    return target


def is_oidc_configured(values: Mapping[str, str] | None = None) -> bool:
    env = dict(values) if values is not None else load_env_file()
    enabled = env.get("ENABLE_OAUTH", "").lower() in {"true", "1", "yes"}
    issuer = env.get("OPENID_PROVIDER_URL", "").strip()
    client = env.get("OAUTH_CLIENT_ID", "").strip()
    return enabled and bool(issuer) and bool(client)


def record_login(
    *,
    subject: str,
    email: str = "",
    role: str,
    outcome: str,
    provider: str = "oidc",
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    if role not in STATION_ROLES:
        raise SSOError(f"unknown station role: {role}")
    moment = now or datetime.now(timezone.utc)
    record = {
        "ts": moment.isoformat(),
        "subject": subject,
        "email_hash": hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        if email
        else "",
        "role": role,
        "outcome": outcome,
        "provider": provider,
    }
    serialized = json.dumps(record, separators=(",", ":"))
    if LOGIN_FORBIDDEN.search(serialized):
        raise SSOError("login record contained forbidden fields")
    target = path or login_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(serialized + "\n")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return record


def sanitize_login_line(line: str) -> dict[str, str] | None:
    if LOGIN_FORBIDDEN.search(line):
        return None
    if not re.search(r"oauth|oidc|signin|login", line, re.IGNORECASE):
        return None
    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        line,
    )
    email = email_match.group(0) if email_match else ""
    role = "viewer"
    lowered = line.casefold()
    if re.search(r"(ai-station-admin|\brole[=: ]admin\b)", lowered):
        role = "admin"
    elif re.search(r"(ai-station-member|\brole[=: ]member\b)", lowered):
        role = "member"
    outcome = "failure" if re.search(r"fail|error|denied", lowered) else "success"
    return record_login(
        subject="log-line",
        email=email,
        role=role,
        outcome=outcome,
    )


def compose_contains_ldap(text: str) -> bool:
    return bool(LDAP_FORBIDDEN.search(text))


def status_payload(values: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = dict(values) if values is not None else load_env_file()
    policy = GroupPolicy(
        admin_groups=parse_groups(env.get("OAUTH_ADMIN_ROLES") or DEFAULT_ADMIN_GROUP)
        or (DEFAULT_ADMIN_GROUP,),
        member_groups=parse_groups(env.get("OAUTH_MEMBER_GROUPS") or DEFAULT_MEMBER_GROUP)
        or (DEFAULT_MEMBER_GROUP,),
        viewer_groups=parse_groups(env.get("OAUTH_VIEWER_GROUPS") or DEFAULT_VIEWER_GROUP)
        or (DEFAULT_VIEWER_GROUP,),
    )
    return {
        "configured": is_oidc_configured(env),
        "enable_oauth": env.get("ENABLE_OAUTH", "False"),
        "issuer": env.get("OPENID_PROVIDER_URL", ""),
        "client_id": env.get("OAUTH_CLIENT_ID", ""),
        "client_secret": "set" if env.get("OAUTH_CLIENT_SECRET") else "unset",
        "provider_name": env.get("OAUTH_PROVIDER_NAME", "SSO"),
        "break_glass": True,
        "local_signup": False,
        "ldap": False,
        "groups": policy.as_dict(),
        "redirect_uri": env.get(
            "OPENID_REDIRECT_URI",
            "http://127.0.0.1:3000/oauth/oidc/callback",
        ),
        "login_log": str(login_log_path()),
        "merge_accounts_by_email": env.get(
            "OAUTH_MERGE_ACCOUNTS_BY_EMAIL", "False"
        ),
        "local_operator_required": True,
    }


def _read_secret(secret_file: str | None) -> str:
    if not secret_file:
        env_secret = os.environ.get("AI_STATION_OIDC_CLIENT_SECRET", "")
        return env_secret.strip()
    path = Path(secret_file)
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SSOError(f"cannot read secret file: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OIDC SSO for Open WebUI. LDAP is not supported."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    configure = sub.add_parser("configure")
    configure.add_argument("--issuer", required=True)
    configure.add_argument("--client-id", required=True)
    configure.add_argument("--secret-file", default=None)
    configure.add_argument("--provider-name", default="SSO")
    configure.add_argument("--admin-group", default=DEFAULT_ADMIN_GROUP)
    configure.add_argument("--member-group", default=DEFAULT_MEMBER_GROUP)
    configure.add_argument("--viewer-group", default=DEFAULT_VIEWER_GROUP)
    configure.add_argument("--dry-run", action="store_true")
    probe = sub.add_parser("probe")
    probe.add_argument("--issuer", required=True)
    probe.add_argument("--dry-run", action="store_true")
    disable = sub.add_parser("disable")
    disable.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    command = args.command or "status"
    try:
        if command == "status":
            print(json.dumps(status_payload(), indent=2))
            return 0
        if command == "configure":
            issuer = validate_issuer(args.issuer)
            secret = _read_secret(args.secret_file)
            if not secret:
                raise SSOError(
                    "client secret required via --secret-file or "
                    "AI_STATION_OIDC_CLIENT_SECRET"
                )
            policy = GroupPolicy(
                admin_groups=(args.admin_group,),
                member_groups=(args.member_group,),
                viewer_groups=(args.viewer_group,),
            )
            values = oauth_env(
                enabled=True,
                issuer=issuer,
                client_id=args.client_id.strip(),
                client_secret=secret,
                provider_name=args.provider_name,
                policy=policy,
            )
            if args.dry_run:
                print(json.dumps(redact_env(values), indent=2))
                return 0
            require_local_operator()
            path = upsert_env_file(values)
            print(f"OK: OIDC enabled ({path})")
            print("Recreate Open WebUI to apply: ai restart")
            print("Break-glass local operator login remains on the sign-in form.")
            print(
                "Create that local operator before the first OAuth signup; "
                "Open WebUI promotes the first user to admin."
            )
            print("Account merge by email is off (OAUTH_MERGE_ACCOUNTS_BY_EMAIL=False).")
            return 0
        if command == "probe":
            issuer = validate_issuer(args.issuer)
            url = discovery_url(issuer)
            if args.dry_run:
                print(json.dumps({"dry_run": True, "discovery_url": url}, indent=2))
                return 0
            print(json.dumps(probe_issuer(issuer), indent=2))
            return 0
        if command == "disable":
            current = load_env_file()
            values = oauth_env(
                enabled=False,
                issuer=current.get("OPENID_PROVIDER_URL", ""),
                client_id=current.get("OAUTH_CLIENT_ID", ""),
                client_secret=current.get("OAUTH_CLIENT_SECRET", ""),
                provider_name=current.get("OAUTH_PROVIDER_NAME", "SSO"),
            )
            if args.dry_run:
                print(json.dumps(redact_env(values), indent=2))
                return 0
            path = upsert_env_file(
                {
                    "ENABLE_OAUTH": "False",
                    "ENABLE_OAUTH_SIGNUP": "False",
                    "ENABLE_OAUTH_ROLE_MANAGEMENT": "False",
                }
            )
            print(f"OK: OIDC disabled ({path}). Local operator login remains.")
            return 0
        parser.error(f"unknown command: {command}")
        return 2
    except SSOError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
