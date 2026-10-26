#!/usr/bin/env bash
# vibe-open — the container's $BROWSER. Hands a web link to the host so it
# opens in the user's real browser.
#
# Why: Claude Code's fullscreen TUI captures mouse clicks, so clicking a link
# never reaches the terminal's own link handler. Claude Code opens the link
# itself instead, via $BROWSER or xdg-open, and inside the container neither
# reaches a browser. This script queues the link as one file under
# /workspace/.vibe/open-requests/; the host-side vibe-open-watcher.sh picks
# it up and runs `open` (Mac) or `xdg-open` (Linux desktop).
#
# Only http(s) links are accepted, here and again on the host, so nothing in
# the container can make the host open a file, an app or a custom URL scheme.
#
# Exit codes: 0 queued · 1 queue write failed · 2 bad usage / refused link.
# Env override (tests): VIBE_OPEN_QUEUE_DIR (default /workspace/.vibe/open-requests).
set -euo pipefail

MAX_LEN=2048
URL_RE='^https?://[A-Za-z0-9._~:/?#@!$&'"'"'()*+,;=%-]+$'

if [[ $# -ne 1 ]]; then
  printf 'vibe-open: usage: vibe-open URL\n' >&2
  exit 2
fi
url="$1"

if (( ${#url} > MAX_LEN )) || ! [[ "$url" =~ $URL_RE ]]; then
  printf 'vibe-open: refused: only plain http(s) links can be opened on the host\n' >&2
  exit 2
fi

queue="${VIBE_OPEN_QUEUE_DIR:-/workspace/.vibe/open-requests}"
if ! mkdir -p "$queue" 2>/dev/null; then
  printf 'vibe-open: error: cannot create %s\n' "$queue" >&2
  exit 1
fi
# Write to a dot-file then rename, so the watcher never reads half a link.
name="$(date +%s)-$$-$RANDOM.url"
if ! printf '%s\n' "$url" > "$queue/.$name" 2>/dev/null || ! mv -f "$queue/.$name" "$queue/$name" 2>/dev/null; then
  rm -f "$queue/.$name" 2>/dev/null || true
  printf 'vibe-open: error: cannot write to %s\n' "$queue" >&2
  exit 1
fi
printf 'vibe-open: sent to the host browser: %s\n' "$url" >&2
