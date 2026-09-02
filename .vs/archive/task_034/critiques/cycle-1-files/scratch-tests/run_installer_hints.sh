#!/usr/bin/env bash
# Render install.sh's preflight hint text for a given platform with EVERY dep
# missing (so it stops at preflight and never clones/symlinks anything).
# usage: run_installer_hints.sh <install.sh path> <Darwin|Linux> [pkg]
set -uo pipefail
script="$1"; os="$2"; pkg="${3:-}"
box="$(mktemp -d)"; trap 'rm -rf "$box"' EXIT
cat > "$box/uname" <<SHIM
#!/bin/sh
[ "\${1:-}" = "-s" ] && { echo "$os"; exit 0; }
echo "$os"
SHIM
chmod +x "$box/uname"
# PATH holds the uname shim ONLY: git/docker/node/devcontainer/gh all absent.
env -i HOME="$box/home" PATH="$box" VIBE_OS="$os" VIBE_PKG="$pkg" \
  /bin/bash "$script" 2>&1
echo "EXIT=$?"
