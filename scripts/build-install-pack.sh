#!/usr/bin/env bash
# Build ai-station-install-pack.zip for GitHub Releases.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/release-output}"
STAMP="$(date -u +%Y%m%d)"
NAME="ai-station-install-pack"
STAGE="$OUT_DIR/$NAME"
ZIP="$OUT_DIR/${NAME}-${STAMP}.zip"

mkdir -p "$OUT_DIR"
rm -rf "$STAGE"
mkdir -p "$STAGE/install/windows" "$STAGE/install/linux" "$STAGE/AI Station"

cp -a "$ROOT/install/README.md" "$STAGE/install/"
cp -a "$ROOT/install/windows/Install-AIStation.ps1" "$STAGE/install/windows/"
cp -a "$ROOT/install/linux/install-ai-station.sh" "$STAGE/install/linux/"
chmod +x "$STAGE/install/linux/install-ai-station.sh"
cp -a "$ROOT/AI Station/"*.cmd "$STAGE/AI Station/" 2>/dev/null || true
cp -a "$ROOT/AI Station/README.md" "$STAGE/AI Station/" 2>/dev/null || true
cp -a "$ROOT/docs/MULTI_MACHINE_DEPLOYMENT.md" "$STAGE/MULTI_MACHINE_DEPLOYMENT.md"

(
  cd "$OUT_DIR"
  rm -f "$NAME.zip" "$ZIP"
  if command -v zip >/dev/null 2>&1; then
    zip -r -q "$(basename "$ZIP")" "$NAME"
  else
    python3 - <<PY
import pathlib, zipfile
root = pathlib.Path(r"$OUT_DIR")
src = root / "$NAME"
out = root / "$(basename "$ZIP")"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in src.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(root).as_posix())
print(out)
PY
  fi
  # Stable name for release asset
  cp -f "$(basename "$ZIP")" "$NAME.zip"
)

echo "Wrote $ZIP"
echo "Wrote $OUT_DIR/$NAME.zip"
ls -lh "$OUT_DIR/$NAME.zip"
