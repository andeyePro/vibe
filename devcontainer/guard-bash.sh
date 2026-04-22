#!/usr/bin/env bash
# vibe PreToolUse guardrail for Bash tool calls.
# Reads {tool_input:{command}} from stdin; exit 2 blocks with stderr as reason.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // empty')

# Block history-overwriting force-push. --force-with-lease is allowed (it
# refuses on divergence, so it can't silently clobber a teammate's work).
is_push()   { grep -qE '(^|[[:space:]]|;|&|\|)git[[:space:]]+push([[:space:]]|;|&|\||$)' <<<"$1"; }
has_force() { grep -qE '(^|[[:space:]])(-f|--force)([[:space:]]|$)' <<<"$1"; }
has_lease() { grep -q 'force-with-lease' <<<"$1"; }

if is_push "$cmd" && has_force "$cmd" && ! has_lease "$cmd"; then
  echo "vibe: 'git push --force' overwrites remote history. Use --force-with-lease." >&2
  exit 2
fi

exit 0
