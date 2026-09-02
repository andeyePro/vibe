#!/usr/bin/env bash
# Capture the PRE-CHANGE rendered override for a fixed fixture input.
# MUST be run before any edit to vibe / devcontainer/devcontainer.json.
set -euo pipefail
root="$(cd "$(dirname "$0")/../../.." && pwd)"
shim="$root/.vs/cycle-1/scratch-tests/shimbin-darwin"
[ "$(PATH="$shim:$PATH" uname -s)" = "Darwin" ] || { echo "shim not effective" >&2; exit 1; }
out="$root/.vs/cycle-1/fixtures"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

render() { # <dstname> <op_host>
  PATH="$shim:$PATH" VIBE_SOURCE_ONLY=1 VIBE_OP_ADDHOST="$2" \
  bash -c '
    set -euo pipefail
    . "$1" >/dev/null 2>&1 || true
    render_devcontainer_with_mounts "$2" "$3" \
      /fixture/host/projects /home/node/.claude/projects 0 \
      /fixture/host/brain2 /brain2 0 \
      /fixture/host/zotero /zotero 1
  ' _ "$root/vibe" "$root/devcontainer/devcontainer.json" "$out/$1"
}
render golden-override-op-off.json ""
render golden-override-op-on.json  "op.example.invalid"
echo "captured:"; md5sum "$out"/golden-override-op-*.json
