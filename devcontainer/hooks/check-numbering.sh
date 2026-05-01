#!/usr/bin/env bash
# check-numbering.sh - Stop hook: warn if the most recent assistant turn
# mixes numbered (1./2./3.) and lettered (a./b./c.) lists in the same reply.
#
# Why: Martin's numbering rule (auto-memory feedback_numbering.md) is
#   "1,2,3 = collaborative working list across turns; a,b,c = per-response
#    action picks; never both in one reply".
# Mixed-list responses confuse the working-list state and the action-picks
# state. This hook surfaces the violation so it doesn't slip past unnoticed.
#
# Behavior: exits 0 (non-blocking warning); writes one warning line to stderr
# if both shapes appear in the most recent assistant message text. Claude Code
# surfaces hook stderr to the user.
#
# Input: Stop-hook payload on stdin; `.transcript_path` points at the
# session JSONL transcript.

set -euo pipefail

payload="$(cat 2>/dev/null || true)"
[ -n "$payload" ] || exit 0

transcript_path="$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
[ -n "$transcript_path" ] || exit 0
[ -r "$transcript_path" ] || exit 0

# Pull the text content of the most recent assistant message. Concatenates
# all `type=text` content blocks; ignores tool_use, thinking, and other block
# types. Slurp (-s) so the JSONL stream becomes an array we can index with `last`.
text="$(jq -rs '
  [.[] | select(.type=="assistant")] | last
  | .message.content[]? | select(.type=="text") | .text
' "$transcript_path" 2>/dev/null || true)"
[ -n "$text" ] || exit 0

# Detect mixed-list violation. Anchored at start-of-line (allow leading
# whitespace for indented lists). Skip code-fenced regions: a heuristic
# strip of ``` blocks first, since code samples often contain numbered
# steps or letter labels that aren't list markers.
stripped="$(printf '%s' "$text" | awk '
  /^```/ { in_fence = !in_fence; next }
  !in_fence { print }
')"

has_num=0
has_let=0
printf '%s' "$stripped" | grep -qE '^[[:space:]]*[0-9]+\.[[:space:]]' && has_num=1
printf '%s' "$stripped" | grep -qE '^[[:space:]]*[a-z]\.[[:space:]]'  && has_let=1

if [ "$has_num" -eq 1 ] && [ "$has_let" -eq 1 ]; then
  printf 'vibe: numbering warning - last reply mixed 1./2./3. with a./b./c. (see feedback_numbering.md - working list vs per-reply action picks)\n' >&2
fi
exit 0
