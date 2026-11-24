#!/usr/bin/env bash
set -Eeuo pipefail

# Create a point-in-time archive of the named Open WebUI data volume. SQLite
# files are copied with sqlite3's online backup API before the archive is made,
# so a live WAL database is never captured as a raw file pair.
VOLUME="${1:-${AI_STATION_OPENWEBUI_VOLUME:-ai-station-openwebui-data}}"
ARCHIVE="${2:?archive output path is required}"
MANIFEST="${3:?manifest output path is required}"
IMAGE="${AI_STATION_OPENWEBUI_IMAGE:-ghcr.io/open-webui/open-webui@sha256:a26effeb220e132482bf7e0560b3404843e7bc40d23051144e062960df8df6b0}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

command -v docker >/dev/null || { echo "ERROR: docker is required for volume backup" >&2; exit 127; }
docker volume inspect "$VOLUME" >/dev/null
mkdir -p "$(dirname "$ARCHIVE")" "$(dirname "$MANIFEST")"

docker run --rm \
  --network none \
  --pull never \
  --entrypoint python3 \
  -v "$VOLUME:/source:ro" \
  -v "$(cd "$(dirname "$ARCHIVE")" && pwd):/backup" \
  --tmpfs /scratch:rw,noexec,nosuid,size=128m \
  -e ARCHIVE_NAME="$(basename "$ARCHIVE")" \
  -e VOLUME_NAME="$VOLUME" \
  -e HOST_UID="$HOST_UID" \
  -e HOST_GID="$HOST_GID" \
  "$IMAGE" -c '
import json, os, sqlite3, tarfile
from pathlib import Path

src = Path("/source")
out = Path("/backup")
archive = out / os.environ["ARCHIVE_NAME"]
snapshots = Path("/scratch/sqlite-snapshots")
sqlite_files = []
for db in sorted(p for p in src.rglob("*") if p.is_file() and p.suffix in (".db", ".sqlite", ".sqlite3")):
    rel = db.relative_to(src)
    if db.is_symlink() and src not in db.resolve().parents:
        raise RuntimeError("external SQLite link")
    target = snapshots / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    sqlite_files.append(str(rel))

def add_safe(bundle, path, rel):
    if path.is_symlink():
        target = path.resolve()
        if src not in target.parents:
            raise RuntimeError("external symlink in volume")
        if target.is_file():
            bundle.add(target, arcname=str(rel), recursive=False)
        elif target.is_dir():
            raise RuntimeError("directory link in volume")
        else:
            raise RuntimeError("unsupported symlink target in volume: " + str(rel))
    elif path.is_file():
        bundle.add(path, arcname=str(rel), recursive=False)
    elif path.is_dir():
        bundle.add(path, arcname=str(rel), recursive=False)
    else:
        raise RuntimeError("special file in volume: " + str(rel))

whisper_files = 0
with tarfile.open(archive, "w:gz", compresslevel=1) as bundle:
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        # Do not copy a live SQLite database, WAL, or shared-memory sidecar.
        if path.is_file() and (path.suffix in (".db", ".sqlite", ".sqlite3") or path.name.endswith(("-wal", "-shm", ".db-wal", ".db-shm"))):
            continue
        add_safe(bundle, path, rel)
        if path.is_file() and path.stat().st_size > 0 and "cache/whisper/" in str(rel).lower():
            whisper_files += 1
    for path in sorted(snapshots.rglob("*")):
        if path.is_file():
            rel = path.relative_to(snapshots)
            bundle.add(path, arcname=str(rel))
            if path.stat().st_size > 0 and "cache/whisper/" in str(rel).lower():
                whisper_files += 1

if not whisper_files:
    raise RuntimeError("Open WebUI volume has no Whisper cache/model files")

manifest = out / ".volume-manifest.json"
manifest.write_text(json.dumps({
    "schema": 1,
    "volume": os.environ.get("VOLUME_NAME", ""),
    "sqlite_snapshot_count": len(sqlite_files),
    "sqlite_snapshots": sqlite_files,
    "whisper_member_count": whisper_files,
}, sort_keys=True) + "\n")
os.chmod(archive, 0o600)
os.chmod(manifest, 0o600)
os.chown(archive, int(os.environ["HOST_UID"]), int(os.environ["HOST_GID"]))
os.chown(manifest, int(os.environ["HOST_UID"]), int(os.environ["HOST_GID"]))
' \

# Move the non-secret manifest generated in the mounted output directory.
test -s "$(dirname "$ARCHIVE")/.volume-manifest.json"
mv -- "$(dirname "$ARCHIVE")/.volume-manifest.json" "$MANIFEST"
