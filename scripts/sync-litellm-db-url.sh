#!/usr/bin/env bash
# Keep URL-encoded Postgres connection strings synchronized in .env.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 - <<'PY'
from pathlib import Path
from urllib.parse import quote_plus

env_path = Path(".env")
vals = {}
lines = env_path.read_text(encoding="utf-8").splitlines()
for line in lines:
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    k, v = raw.split("=", 1)
    vals[k.strip()] = v.strip().strip('"').strip("'")

user = vals.get("POSTGRES_USER", "openwebui")
password = vals.get("POSTGRES_PASSWORD", "")
db = vals.get("POSTGRES_DB", "openwebui")
if not password:
    raise SystemExit("POSTGRES_PASSWORD missing in .env")

encoded = quote_plus(password)
wanted = {
    "LITELLM_DATABASE_URL": f"postgresql://{user}:{encoded}@postgres:5432/litellm",
    "OPENWEBUI_DATABASE_URL": f"postgresql://{user}:{encoded}@postgres:5432/{db}",
    "PGVECTOR_DB_URL": f"postgresql://{user}:{encoded}@postgres:5432/{db}",
}

out = []
seen = set()
for line in lines:
    if "=" in line and not line.strip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in wanted:
            out.append(f"{key}={wanted[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in wanted.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
print("OK: database URLs synchronized (URL-encoded)")
PY
