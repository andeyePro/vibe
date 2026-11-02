#!/usr/bin/env bash
# vibe-open-watcher.sh — host-side half of the container's link opener.
# The container's $BROWSER (devcontainer/vibe-open.sh) drops one link per file
# into WORKSPACE/.vibe/open-requests/; this loop opens each in the host's
# browser and deletes the request.
#
# Safety: the request files are written by the container, so they are
# untrusted. Each link is re-validated here as plain http(s) with no spaces
# or control characters, symlinks and non-regular files are skipped, and at
# most MAX_PER_TICK links open per poll, so a runaway process in the
# container can neither open local files/apps nor flood the browser.
#
# Opener: `open` on macOS; VIBE_OPEN_CMD overrides (the launcher sets it to
# xdg-open on a Linux desktop host). VIBE_OPEN_WATCHER_ONCE=1 processes the
# queue once and exits (tests).
set -euo pipefail

[ $# -eq 1 ] || { echo "usage: vibe-open-watcher.sh WORKSPACE_ABS_PATH" >&2; exit 2; }
QUEUE="$1/.vibe/open-requests"
OPEN_CMD="${VIBE_OPEN_CMD:-open}"
MAX_PER_TICK=3
MAX_LEN=2048
URL_RE='^https?://[A-Za-z0-9._~:/?#@!$&'"'"'()*+,;=%-]+$'

mkdir -p "$QUEUE"

tick() {
  local n=0 f url
  for f in "$QUEUE"/*.url; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    if [ -L "$f" ] || [ ! -f "$f" ]; then rm -f "$f"; continue; fi
    url=$(head -c "$((MAX_LEN + 1))" "$f" | head -n 1 || true)
    rm -f "$f"
    if [ "$n" -ge "$MAX_PER_TICK" ]; then continue; fi
    if [ "${#url}" -le "$MAX_LEN" ] && [[ "$url" =~ $URL_RE ]]; then
      $OPEN_CMD "$url" >/dev/null 2>&1 || true
      n=$((n + 1))
    fi
  done
}

if [ "${VIBE_OPEN_WATCHER_ONCE:-0}" = "1" ]; then
  tick
  exit 0
fi
# Requests left over from a previous session are stale: drop, don't open.
find "$QUEUE" -mindepth 1 -maxdepth 1 -name '*.url' -delete 2>/dev/null || true
while sleep 0.3; do
  tick
done
