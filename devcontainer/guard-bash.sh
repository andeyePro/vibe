#!/usr/bin/env bash
# vibe PreToolUse guardrail for Bash tool calls.
# Reads {tool_input:{command}} from stdin; exit 2 blocks with stderr as reason.
# Every block is also appended to $LOG for post-hoc audit.
#
# Evaluation order (block beats ask — all conditions evaluated before deciding):
#   (a) git-push violations  → exit 2 (block)
#   (b) /learnings writes    → emit ask-JSON, exit 0
#   (c) otherwise            → exit 0 silently
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

# ── (a) Evaluate git-push violations ─────────────────────────────────────────
should_block=false
block_rule=""
block_msg=""

if is_push "$cmd"; then
  if has_force "$cmd" && ! has_lease "$cmd"; then
    should_block=true
    block_rule="force-push"
    block_msg="'git push --force' overwrites remote history. Use --force-with-lease."
  fi
  if has_delete "$cmd" || has_colondel "$cmd"; then
    should_block=true
    block_rule="branch-delete"
    block_msg="'git push' deleting a remote branch is irreversible for other clones. Confirm intent or delete via the GitHub UI."
  fi
fi

# ── (b) Evaluate /learnings write idioms ─────────────────────────────────────
should_ask=false

# Shell redirects to /learnings: >, >>, &>, &>>
if grep -qE '(>|>>|&>|&>>)[[:space:]]*['"'"'"]?/learnings/' <<<"$cmd"; then
  should_ask=true
fi

# tee to /learnings
if grep -qE '(^|[[:space:]]|;|&|\|)tee([[:space:]]+-[a-zA-Z]+)*[[:space:]]+['"'"'"]?/learnings/' <<<"$cmd"; then
  should_ask=true
fi

# File-modifying binaries: cp, mv, rm, ln, mkdir, chmod, chown, truncate, dd
for _bin in cp mv rm ln mkdir chmod chown truncate dd; do
  if grep -qE "(^|[[:space:]]|;|&|\|)${_bin}([[:space:]]+-[a-zA-Z]+)*[[:space:]]+[^|;&]*['\"]?/learnings/" <<<"$cmd"; then
    should_ask=true
    break
  fi
done

# sed -i write detection (three separate conditions must ALL hold):
#   (i)  sed invocation token
#   (ii) standalone or combined -i flag (e.g. -i, -ri, -Ei, -iE)
#   (iii) literal /learnings/ substring
if grep -qE '(^|[[:space:]]|;|&|\|)sed[[:space:]]' <<<"$cmd" && \
   grep -qE '(^|[[:space:]])-[a-zA-Z]*i[a-zA-Z]*([[:space:]]|$)' <<<"$cmd" && \
   grep -q '/learnings/' <<<"$cmd"; then
  should_ask=true
fi

# ── (c) Decide ────────────────────────────────────────────────────────────────
# Block beats ask: if (a) fired, exit 2 regardless of (b).
if [ "$should_block" = "true" ]; then
  block "$block_rule" "$block_msg"
fi

if [ "$should_ask" = "true" ]; then
  printf '%s\n' "$(jq -n \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: "vibe: shell command modifies the learning library — confirm to proceed"
      }
    }')"
fi

exit 0
