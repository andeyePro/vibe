#!/usr/bin/env bash
# vibe-copy-watcher.sh — host-side polling watcher that pbcopies the /c scratch
# file on change. Runs on the Mac; no-op on Linux.
# VIBE_COPY_WATCHER_FORCE=1 bypasses the Darwin check for testing only.
set -euo pipefail

if [ "${VIBE_COPY_WATCHER_FORCE:-0}" != "1" ]; then
  [[ "$(uname)" == "Darwin" ]] || exit 0
fi

COPY_CMD="${VIBE_COPY_CMD:-pbcopy}"

[ $# -eq 1 ] || { echo "usage: vibe-copy-watcher.sh WORKSPACE_ABS_PATH" >&2; exit 2; }
WORKSPACE="$1"
CLIP="$WORKSPACE/.vibe/copy-latest.txt"
mkdir -p "$(dirname "$CLIP")"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Seed `last` with the current mtime so a pre-existing copy-latest.txt from a
# prior vibe session doesn't clobber the Mac clipboard on startup.
last=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)
if command -v fswatch >/dev/null 2>&1; then
  fswatch -0 "$(dirname "$CLIP")" | while IFS= read -r -d '' _; do
    [ -s "$CLIP" ] || continue
    cur=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)
    if [ "$cur" != "$last" ]; then
      last="$cur"
      cp "$CLIP" "$TMP" 2>/dev/null && $COPY_CMD < "$TMP" 2>/dev/null || true
    fi
  done
else
  while sleep 0.5; do
    [ -s "$CLIP" ] || continue
    cur=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)
    if [ "$cur" != "$last" ]; then
      last="$cur"
      cp "$CLIP" "$TMP" 2>/dev/null && $COPY_CMD < "$TMP" 2>/dev/null || true
    fi
  done
fi
