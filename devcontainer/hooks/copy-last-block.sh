#!/usr/bin/env bash
# copy-last-block.sh - Stop hook: write the LAST fenced code block from the
# most recent assistant message to /workspace/.vibe/copy-latest.txt so the
# host-side vibe-copy-watcher.sh can pbcopy it to the Mac clipboard with no
# slash-command round-trip.
#
# Opt-in: only fires if `~/.claude/settings.json` references this script as
# a Stop hook. The script is shipped to every vibe container by
# install-claude-extras.sh but is silent until wired up.
#
# Per-turn opt-out: if the assistant message contains the literal sentinel
# `<!-- vibe: no-copy -->`, the hook skips the write for that turn.
#
# Behaviour: exits 0 in all paths (informational). Tolerates missing transcript,
# empty assistant text, and zero fenced blocks.

set -euo pipefail

CLIP_DIR="${VIBE_CLIP_DIR:-/workspace/.vibe}"
CLIP_FILE="$CLIP_DIR/copy-latest.txt"

payload="$(cat 2>/dev/null || true)"
[ -n "$payload" ] || exit 0

transcript_path="$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
[ -n "$transcript_path" ] || exit 0
[ -r "$transcript_path" ] || exit 0

text="$(jq -rs '
  [.[] | select(.type=="assistant")] | last
  | .message.content[]? | select(.type=="text") | .text
' "$transcript_path" 2>/dev/null || true)"
[ -n "$text" ] || exit 0

# Per-turn opt-out: silent skip when the marker is present anywhere.
case "$text" in
  *'<!-- vibe: no-copy -->'*) exit 0 ;;
esac

# Extract the LAST fenced code block. State machine:
# - Top-level lines that start with ``` toggle in_fence.
# - When entering a fence, reset cur and remember the language tag (for future use).
# - When exiting, save cur into last_block.
# - Lines inside a fence are appended to cur, preserving newlines.
# - At END, print last_block (no trailing newline beyond what the block had).
#
# Note: this does not handle nested fences. Markdown convention is that nested
# fences use a different number of backticks; we only match exactly ``` at line
# start. Mixed-fence-length blocks fall through to whichever pair matches first.
last_block="$(printf '%s\n' "$text" | awk '
  /^```/ {
    if (!in_fence) {
      in_fence = 1
      cur = ""
    } else {
      in_fence = 0
      last_block = cur
    }
    next
  }
  in_fence { cur = cur $0 "\n" }
  END { if (last_block != "") printf "%s", last_block }
')"
[ -n "$last_block" ] || exit 0

# Strip exactly one trailing newline (awk added "$0\n" for the closing line, so
# a block ending on the closing fence has one terminal \n; users pasting tend
# to want no trailing newline, matching /c's behaviour).
last_block="${last_block%$'\n'}"

mkdir -p "$CLIP_DIR" 2>/dev/null || exit 0
printf '%s' "$last_block" > "$CLIP_FILE" 2>/dev/null || true
exit 0
