#!/usr/bin/env bash
# Ensure Windows %UserProfile%\.wslconfig keeps the WSL2 VM from idle-shutdown.
# Idempotent. Safe to run from ai start / installer. Does not call wsl --shutdown.
set -Eeuo pipefail

find_wslconfig() {
  local candidate
  # Prefer the Windows user that owns /mnt/c/Users when only one profile has .wslconfig
  # or when USERPROFILE is visible via Windows env in WSL.
  if [[ -n "${WSLCONFIG_PATH:-}" && -f "${WSLCONFIG_PATH}" ]]; then
    printf '%s\n' "$WSLCONFIG_PATH"
    return 0
  fi
  if [[ -n "${USERPROFILE:-}" ]]; then
    candidate="$(wslpath -u "$USERPROFILE" 2>/dev/null || true)/.wslconfig"
    candidate="${candidate//\\//}"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  # Common single-user workstation layout
  for candidate in /mnt/c/Users/*/.wslconfig; do
    [[ -f "$candidate" ]] || continue
    # Skip Default / Public / Administrator templates when RamtiN-style profiles exist
    case "$candidate" in
      */Users/Public/*|*/Users/Default/*|*/Users/Default\ User/*) continue ;;
    esac
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

ensure_vm_idle_timeout() {
  local path="$1"
  if grep -Eq '^[[:space:]]*vmIdleTimeout[[:space:]]*=[[:space:]]*-1[[:space:]]*$' "$path"; then
    echo "OK: vmIdleTimeout=-1 already set in $path"
    return 0
  fi

  python3 - "$path" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
newline = "\r\n" if "\r\n" in text else "\n"
lines = text.replace("\r\n", "\n").split("\n")

# Remove any existing vmIdleTimeout lines (commented or not) under consideration
cleaned = []
for line in lines:
    if re.match(r"^\s*#?\s*vmIdleTimeout\s*=", line):
        continue
    cleaned.append(line)

# Find [wsl2] section and insert after it (after existing keys if present)
out = []
inserted = False
in_wsl2 = False
for i, line in enumerate(cleaned):
    out.append(line)
    if re.match(r"^\s*\[wsl2\]\s*$", line, flags=re.IGNORECASE):
        in_wsl2 = True
        continue
    if in_wsl2 and re.match(r"^\s*\[.+\]\s*$", line):
        # entered next section — insert before this line
        out.pop()
        out.append("vmIdleTimeout=-1")
        out.append(line)
        inserted = True
        in_wsl2 = False
        continue

if in_wsl2 and not inserted:
    # append before trailing blank comments at end of section: just add at end of file section
    # Insert after last non-empty non-comment content following [wsl2], else right after [wsl2]
    out.append("vmIdleTimeout=-1")
    inserted = True

if not any(re.match(r"^\s*\[wsl2\]\s*$", l, flags=re.IGNORECASE) for l in cleaned):
    # no [wsl2] — create one
    body = newline.join(out).rstrip("\n")
    addition = "[wsl2]" + newline + "vmIdleTimeout=-1" + newline
    path.write_text((body + newline + newline + addition) if body else addition, encoding="utf-8")
else:
    path.write_text(newline.join(out).rstrip("\n") + newline, encoding="utf-8")

print(f"UPDATED: set vmIdleTimeout=-1 in {path}")
PY
}

main() {
  if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo "SKIP: not running under WSL"
    exit 0
  fi

  local path
  if ! path="$(find_wslconfig)"; then
    # Create under first real Windows user home we can write
    local home
    for home in /mnt/c/Users/*; do
      case "$home" in
        */Users/Public|*/Users/Default|*/Users/Default\ User|*/Users/All\ Users) continue ;;
      esac
      [[ -d "$home" ]] || continue
      path="$home/.wslconfig"
      printf '%s\n' "[wsl2]" "vmIdleTimeout=-1" >"$path"
      echo "CREATED: $path"
      exit 0
    done
    echo "WARNING: could not locate Windows user profile to write .wslconfig" >&2
    exit 1
  fi

  ensure_vm_idle_timeout "$path"
}

main "$@"
