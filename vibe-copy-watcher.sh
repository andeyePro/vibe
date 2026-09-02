#!/usr/bin/env bash
# vibe-copy-watcher.sh — host-side polling watcher that copies the /c scratch
# file to the host clipboard on change. Runs on the Mac (pbcopy) and, since
# task_034, on a Linux host whose launcher detected a clipboard tool and
# exported VIBE_COPY_CMD (wl-copy / xclip -selection clipboard / xsel
# --clipboard --input). Still a no-op on a headless host: no tool, no
# VIBE_COPY_CMD, no watcher — /c falls back to the scratch file.
# VIBE_COPY_WATCHER_FORCE=1 bypasses the platform check for testing only.
set -euo pipefail

# 3-way gate: Darwin, OR an explicit VIBE_COPY_CMD (the Linux path), OR the
# test-only FORCE escape hatch. Any one of the three is enough to run.
if [ "${VIBE_COPY_WATCHER_FORCE:-0}" != "1" ] && [ -z "${VIBE_COPY_CMD:-}" ]; then
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
