#!/usr/bin/env bash
# vibe PreToolUse guardrail for Bash tool calls.
# Reads {tool_input:{command}} from stdin; exit 2 blocks with stderr as reason.
# Every block is also appended to $LOG for post-hoc audit.
set -euo pipefail

LOG=${VIBE_BLOCKS_LOG:-/home/node/.claude/vibe-blocks.log}

cmd=$(jq -r '.tool_input.command // empty')

block() {
  local rule=$1 msg=$2
  # Flatten any newlines in the command so one block = one log line.
  local flat=${cmd//$'\n'/\\n}
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
  printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rule" "$flat" >> "$LOG" 2>/dev/null || true
  echo "vibe: $msg" >&2
  exit 2
}

is_push()     { grep -qE '(^|[[:space:]]|;|&|\|)git[[:space:]]+push([[:space:]]|;|&|\||$)' <<<"$1"; }
has_force()   { grep -qE '(^|[[:space:]])(-f|--force)([[:space:]]|$)' <<<"$1"; }
has_lease()   { grep -q 'force-with-lease' <<<"$1"; }
has_delete()  { grep -qE '(^|[[:space:]])--delete([[:space:]]|$)' <<<"$1"; }
# Colon-delete refspec: ` :branchname` (space then colon then name). Does NOT
# match `main:main` (no preceding space) — that's a local:remote refspec.
has_colondel(){ grep -qE '[[:space:]]:[A-Za-z0-9_][A-Za-z0-9_./-]*([[:space:]]|$)' <<<"$1"; }

if is_push "$cmd"; then
  if has_force "$cmd" && ! has_lease "$cmd"; then
    block force-push "'git push --force' overwrites remote history. Use --force-with-lease."
  fi
  if has_delete "$cmd" || has_colondel "$cmd"; then
    block branch-delete "'git push' deleting a remote branch is irreversible for other clones. Confirm intent or delete via the GitHub UI."
  fi
fi

exit 0
