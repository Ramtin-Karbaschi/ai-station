#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/config/clients/opencode/runtime.json"
TOOLCHAIN_MANIFEST="$ROOT/config/clients/opencode/toolchain.json"
DRY_RUN=0
CREATE_USER=0
OWN_PROJECT=0
DEV_USER=""

usage() {
  cat <<'EOF'
Usage: install-opencode-wsl.sh [options]

Options:
  --user NAME       Developer account (default from runtime.json)
  --create-user     Create the non-root account when absent
  --own-project     Make the developer account own this Git worktree
  --dry-run         Print the plan without changing the host
  -h, --help        Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) DEV_USER="${2:-}"; shift 2 ;;
    --create-user) CREATE_USER=1; shift ;;
    --own-project) OWN_PROJECT=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: missing $MANIFEST" >&2
  exit 1
fi
if [[ ! -f "$TOOLCHAIN_MANIFEST" ]]; then
  echo "ERROR: missing $TOOLCHAIN_MANIFEST" >&2
  exit 1
fi

mapfile -t manifest_values < <(
  python3 - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in ("version", "url", "sha256", "install_root", "developer_user"):
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"ERROR: runtime manifest field {key} is missing")
    print(value)
PY
)

VERSION="${manifest_values[0]}"
URL="${manifest_values[1]}"
SHA256="${manifest_values[2]}"
INSTALL_ROOT="${manifest_values[3]}"
DEFAULT_USER="${manifest_values[4]}"
DEV_USER="${DEV_USER:-$DEFAULT_USER}"

if [[ ! "$DEV_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
  echo "ERROR: invalid developer user '$DEV_USER'" >&2
  exit 2
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root; installation writes /srv and /usr/local/bin" >&2
  exit 1
fi

DEST_DIR="$INSTALL_ROOT/$VERSION"
DEST_BIN="$DEST_DIR/opencode"
LINK="/usr/local/bin/opencode"

mapfile -t toolchain_values < <(
  python3 - "$TOOLCHAIN_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data["install_root"])
print(" ".join(data["apt_packages"]))
print(data["vscode_extension"])
for name, version in sorted(data["npm_packages"].items()):
    print(f"npm:{name}@{version}")
for name, version in sorted(data["npm_overrides"].items()):
    print(f"override:{name}@{version}")
for name, version in sorted(data["python_packages"].items()):
    print(f"python:{name}=={version}")
PY
)
TOOLCHAIN_ROOT="${toolchain_values[0]}"
APT_PACKAGES="${toolchain_values[1]}"
VSCODE_EXTENSION="${toolchain_values[2]}"
NPM_SPECS=()
PYTHON_SPECS=()
NPM_OVERRIDES=()
for spec in "${toolchain_values[@]:3}"; do
  case "$spec" in
    npm:*) NPM_SPECS+=("${spec#npm:}") ;;
    override:*) NPM_OVERRIDES+=("${spec#override:}") ;;
    python:*) PYTHON_SPECS+=("${spec#python:}") ;;
  esac
done

echo "OpenCode WSL runtime:"
echo "  version: $VERSION"
echo "  binary:  $DEST_BIN"
echo "  user:    $DEV_USER"

if ! id "$DEV_USER" >/dev/null 2>&1; then
  if [[ "$CREATE_USER" -ne 1 ]]; then
    echo "ERROR: developer user '$DEV_USER' does not exist; add --create-user" >&2
    exit 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: would create non-root user $DEV_USER"
  else
    useradd --create-home --shell /bin/bash "$DEV_USER"
    echo "OK: created non-root user $DEV_USER"
  fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ -x "$DEST_BIN" && "$($DEST_BIN --version 2>/dev/null || true)" == "$VERSION" ]]; then
    echo "DRY-RUN: pinned binary is already installed; would only refresh $LINK"
  else
    echo "DRY-RUN: would download $URL"
    echo "DRY-RUN: would verify SHA-256 $SHA256"
    echo "DRY-RUN: would install $DEST_BIN and update $LINK"
  fi
  if [[ "$OWN_PROJECT" -eq 1 ]]; then
    echo "DRY-RUN: would set $DEV_USER ownership on $ROOT"
  fi
  echo "DRY-RUN: would install the pinned OpenCode Python/Bash toolchain"
  exit 0
fi

if [[ -x "$DEST_BIN" && "$($DEST_BIN --version 2>/dev/null || true)" == "$VERSION" ]]; then
  echo "OK: pinned OpenCode binary already installed"
else
  tmp_dir="$(mktemp -d)"
  cleanup() { rm -rf -- "$tmp_dir"; }
  trap cleanup EXIT
  archive="$tmp_dir/opencode.tar.gz"

  curl -fL --retry 3 --connect-timeout 15 -o "$archive" "$URL"
  printf '%s  %s\n' "$SHA256" "$archive" | sha256sum --check --status || {
    echo "ERROR: OpenCode archive checksum mismatch" >&2
    exit 1
  }

  mkdir -p "$tmp_dir/extracted"
  tar -xzf "$archive" -C "$tmp_dir/extracted"
  source_bin="$(find "$tmp_dir/extracted" -maxdepth 2 -type f -name opencode -print -quit)"
  if [[ -z "$source_bin" ]]; then
    echo "ERROR: archive does not contain the opencode binary" >&2
    exit 1
  fi

  install -d -m 0755 "$DEST_DIR"
  install -m 0755 "$source_bin" "$DEST_BIN"
fi
ln -sfn "$DEST_BIN" "$LINK"

actual_version="$($LINK --version)"
if [[ "$actual_version" != "$VERSION" ]]; then
  echo "ERROR: installed version is '$actual_version', expected '$VERSION'" >&2
  exit 1
fi

missing_apt=()
for package in $APT_PACKAGES; do
  dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed" \
    || missing_apt+=("$package")
done
if [[ ${#missing_apt[@]} -gt 0 ]]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing_apt[@]}"
fi

install -d -m 0755 "$TOOLCHAIN_ROOT"
npm install --save-exact --install-strategy=shallow --omit=dev --prefix "$TOOLCHAIN_ROOT" "${NPM_SPECS[@]}"
for override in "${NPM_OVERRIDES[@]}"; do
  npm pkg set "overrides.${override%@*}=${override#*@}" --prefix "$TOOLCHAIN_ROOT"
done
npm install --install-strategy=shallow --omit=dev --prefix "$TOOLCHAIN_ROOT"
npm audit --audit-level=high --omit=dev --prefix "$TOOLCHAIN_ROOT"
python3 -m venv "$TOOLCHAIN_ROOT/python"
"$TOOLCHAIN_ROOT/python/bin/python" -m pip install --disable-pip-version-check "${PYTHON_SPECS[@]}"
for executable in bash-language-server pyright pyright-langserver; do
  ln -sfn "$TOOLCHAIN_ROOT/node_modules/.bin/$executable" "/usr/local/bin/$executable"
done
ln -sfn "$TOOLCHAIN_ROOT/python/bin/ruff" /usr/local/bin/ruff

windows_code="/mnt/c/Program Files/Microsoft VS Code/bin/code"
if [[ -r "$windows_code" ]]; then
  install -d -m 0755 "$TOOLCHAIN_ROOT/bin"
  bridge="$TOOLCHAIN_ROOT/bin/code"
  vscode_folder="$(sed -n 's/^VERSIONFOLDER="\([^"]*\)"/\1/p' "$windows_code" | head -n 1)"
  if [[ -z "$vscode_folder" ]]; then
    echo "ERROR: could not determine the VS Code CLI folder" >&2
    exit 1
  fi
  printf '%s\n' \
    '#!/usr/bin/env sh' \
    'export ELECTRON_RUN_AS_NODE=1' \
    'export WSLENV="ELECTRON_RUN_AS_NODE/w${WSLENV:+:$WSLENV}"' \
    "exec /init '/mnt/c/Program Files/Microsoft VS Code/Code.exe' '/mnt/c/Program Files/Microsoft VS Code/Code.exe' 'C:/Program Files/Microsoft VS Code/$vscode_folder/resources/app/out/cli.js' \"\$@\"" \
    >"$bridge"
  chmod 0755 "$bridge"
  ln -sfn "$bridge" /usr/local/bin/code
  /usr/local/bin/code --install-extension "$VSCODE_EXTENSION" --force
fi

for executable in bash-language-server pyright-langserver ruff shellcheck shfmt; do
  command -v "$executable" >/dev/null || {
    echo "ERROR: OpenCode toolchain executable is missing: $executable" >&2
    exit 1
  }
done

home_dir="$(getent passwd "$DEV_USER" | cut -d: -f6)"
install -d -o "$DEV_USER" -g "$DEV_USER" -m 0700 "$home_dir/.config"
install -d -o "$DEV_USER" -g "$DEV_USER" -m 0700 "$home_dir/.config/opencode"

if [[ "$OWN_PROJECT" -eq 1 ]]; then
  resolved_root="$(realpath "$ROOT")"
  if [[ "$resolved_root" != "$ROOT" || "$resolved_root" == "/" || "$resolved_root" == "/opt" ]]; then
    echo "ERROR: refusing broad ownership change for $resolved_root" >&2
    exit 1
  fi
  chown -R "$DEV_USER:$DEV_USER" "$resolved_root"
  echo "OK: $DEV_USER owns the project worktree"
fi

echo "OK: OpenCode $VERSION installed with a verified archive"
echo "OK: $LINK -> $DEST_BIN"
echo "OK: pinned Python/Bash language toolchain is installed"
if [[ -x /usr/local/bin/code ]]; then
  echo "OK: WSL administrator can launch the VS Code editor bridge"
fi
