#!/usr/bin/env bash
# copy-last-block.sh - Stop hook: when the assistant message contains the
# literal sentinel `<!-- vibe: copy -->`, write the LAST fenced code block
# of that message to /workspace/.vibe/copy-latest.txt so the host-side
# vibe-copy-watcher.sh can pbcopy it to the Mac clipboard with no slash-
# command round-trip. Without the sentinel the hook is silent.
#
# Opt-in twice: (1) wire the hook in `~/.claude/settings.json` as a Stop
# hook (the script is shipped to every vibe container by install-claude-
# extras.sh but does nothing until wired); (2) the assistant must include
# `<!-- vibe: copy -->` in the message for that specific turn to copy.
# Default is silent so the user's clipboard is only touched when the
# assistant has explicitly flagged a block as paste-worthy.
#
# Behaviour: exits 0 in all paths (informational). Tolerates missing transcript,
# empty assistant text, missing marker, and zero fenced blocks.

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

# Per-turn opt-in: silent unless the sentinel is present anywhere in the text.
case "$text" in
  *'<!-- vibe: copy -->'*) : ;;
  *) exit 0 ;;
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
