#!/usr/bin/env python3
"""Rebuild Open WebUI Knowledge vectors at the live embedder dimension.

Drops mixed-width pgvector rows, alters document_chunk.vector to match the
live llama.cpp embedder, then re-embeds every chunk. Source text is preserved.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = Path("/srv/ai-station/backups")
EMBED_URL = os.getenv("AI_STATION_EMBED_URL", "http://127.0.0.1:8090/v1/embeddings")
EMBED_MODEL = os.getenv("AI_STATION_EMBED_MODEL", "ai-station-embedding")


def load_env(key: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def psql(sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "ai-station-postgres-1",
            "psql",
            "-U",
            load_env("POSTGRES_USER") or "openwebui",
            "-d",
            load_env("POSTGRES_DB") or "openwebui",
            "-v",
            "ON_ERROR_STOP=1",
            "-t",
            "-A",
            "-c",
            sql,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def embed_texts(texts: list[str]) -> list[list[float]]:
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    rows = sorted(data["data"], key=lambda item: int(item["index"]))
    return [row["embedding"] for row in rows]


def probe_embed_dim() -> int:
    return len(embed_texts(["dimension probe"])[0])


def main() -> int:
    os.environ.setdefault("DOCKER_CONTEXT", "default")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump = BACKUP_DIR / f"document_chunk-{stamp}.sql"
    print(f"Backing up document_chunk to {dump}")
    dump_proc = subprocess.run(
        [
            "docker",
            "exec",
            "ai-station-postgres-1",
            "pg_dump",
            "-U",
            load_env("POSTGRES_USER") or "openwebui",
            "-d",
            load_env("POSTGRES_DB") or "openwebui",
            "-t",
            "document_chunk",
            "--data-only",
        ],
        check=True,
        capture_output=True,
    )
    dump.write_bytes(dump_proc.stdout)

    live_dim = probe_embed_dim()
    print(f"Live embedder dimension: {live_dim}")
    if live_dim not in {1024, 1536, 4096}:
        print(f"ERROR: unexpected embedding width {live_dim}", file=sys.stderr)
        return 2

    count = int(psql("SELECT COUNT(*) FROM document_chunk;"))
    print(f"Chunks to rebuild: {count}")

    psql("DROP INDEX IF EXISTS idx_document_chunk_vector;")
    psql("ALTER TABLE document_chunk DROP COLUMN IF EXISTS vector;")
    psql(f"ALTER TABLE document_chunk ADD COLUMN vector vector({live_dim});")

    if count == 0:
        print("No chunks; schema updated only.")
        return 0

    raw = psql(
        "SELECT COALESCE(json_agg(json_build_object('id', id, 'text', COALESCE(text, ''))), '[]'::json) "
        "FROM document_chunk;"
    )
    items = json.loads(raw)
    batch = 4
    updated = 0
    for offset in range(0, len(items), batch):
        group = items[offset : offset + batch]
        vectors = embed_texts([str(item.get("text") or " ") for item in group])
        for item, vector in zip(group, vectors):
            if len(vector) != live_dim:
                raise RuntimeError(f"embed dim {len(vector)} != {live_dim}")
            literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
            escaped = str(item["id"]).replace("'", "''")
            psql(
                "UPDATE document_chunk SET vector = '"
                + literal
                + "'::vector WHERE id = '"
                + escaped
                + "';"
            )
            updated += 1
        print(f"Re-embedded {updated}/{len(items)}")

    if live_dim > 2000:
        print(
            f"Skip ANN index: pgvector ivfflat/hnsw cap is 2000-d; live dim is {live_dim}. "
            "Exact cosine scan is used (acceptable for small Knowledge collections)."
        )
    else:
        psql(
            "CREATE INDEX idx_document_chunk_vector ON document_chunk "
            "USING hnsw (vector vector_cosine_ops);"
        )
    dims = psql(
        "SELECT vector_dims(vector)::text || ' x ' || COUNT(*)::text "
        "FROM document_chunk WHERE vector IS NOT NULL GROUP BY 1;"
    )
    print(f"Post-migration dims: {dims}")
    print(f"OK: rebuilt {updated} chunks at {live_dim}-d; backup {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
