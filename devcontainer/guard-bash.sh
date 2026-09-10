#!/usr/bin/env bash
# vibe PreToolUse guardrail for Bash tool calls.
# Reads {tool_input:{command}} from stdin; exit 2 blocks with stderr as reason.
# Every block is also appended to $LOG for post-hoc audit.
#
# Evaluation order (block beats ask - all conditions evaluated before deciding):
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
# match `main:main` (no preceding space) - that's a local:remote refspec.
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

# ── (b2) Evaluate /zotero write idioms — deny, not ask ───────────────────────
# The Zotero library mount is contractually read-only (guard-fs.sh denies the
# structured Write/Edit path); mirror that for the same best-effort shell
# idioms as /learnings. Deny rather than ask for the guard-fs.sh reason:
# there is no legitimate in-container write to the user's Zotero library.
zotero_write=false

if grep -qE '(>|>>|&>|&>>)[[:space:]]*['"'"'"]?/zotero/' <<<"$cmd"; then
  zotero_write=true
fi

if grep -qE '(^|[[:space:]]|;|&|\|)tee([[:space:]]+-[a-zA-Z]+)*[[:space:]]+['"'"'"]?/zotero/' <<<"$cmd"; then
  zotero_write=true
fi

for _bin in cp mv rm ln mkdir chmod chown truncate dd; do
  if grep -qE "(^|[[:space:]]|;|&|\|)${_bin}([[:space:]]+-[a-zA-Z]+)*[[:space:]]+[^|;&]*['\"]?/zotero/" <<<"$cmd"; then
    zotero_write=true
    break
  fi
done

if grep -qE '(^|[[:space:]]|;|&|\|)sed[[:space:]]' <<<"$cmd" && \
   grep -qE '(^|[[:space:]])-[a-zA-Z]*i[a-zA-Z]*([[:space:]]|$)' <<<"$cmd" && \
   grep -q '/zotero/' <<<"$cmd"; then
  zotero_write=true
fi

# Fold into the block tier; the git rules keep precedence for the message.
if [ "$zotero_write" = "true" ] && [ "$should_block" != "true" ]; then
  should_block=true
  block_rule="zotero-write"
  block_msg="the Zotero library at /zotero is mounted read-only - copy the file into /workspace if you need to change it."
fi

# The Codex CLI login directory (/home/node/.codex, bind-mounted read-write
# from the Mac's ~/.codex for token refresh — guard-fs.sh denies the
# structured path). Its config.toml can name programs Codex runs on the HOST,
# so a write here is host code execution waiting for the user's next `codex`.
# Also covered: the /workspace/.vibe-allow-codex opt-in marker, which is the
# switch that grants the mount on the next launch — a session must not be
# able to opt its own project in. Best-effort static matching, like the
# /learnings and /zotero arms (blind to `cd dir && >file`, interpreters,
# symlinks made earlier); guard-fs.sh is the real gate for tool writes.
# Path spellings: container path, ~ / ~user, $HOME / ${HOME}, with any run of
# slashes, ./ hops or ../<seg>/ hops before .codex; the trailing boundary is
# anything that is not a path character, so `rm -rf ~/.codex; …` and
# `(rm -rf ~/.codex)` match too.
_codex_re='(/home/node/+|~[A-Za-z0-9_-]*/+|\$HOME/+|\$\{HOME\}/+)((\.|\.\./[A-Za-z0-9_.-]+)/+)*\.codex(/|[^A-Za-z0-9._/-]|$)'
_codex_marker_re='([^[:space:]"'"'"'|;&]*/)?\.vibe-allow-codex([^A-Za-z0-9._-]|$)'

# _codex_write_idiom <path-regex> — 0 iff $cmd applies a write idiom to a
# path matching the regex: redirects (incl. >| noclobber override), tee, the
# file-mutating binaries, sed -i.
_codex_write_idiom() {
  local re="$1" _bin
  grep -qE '(>\||>|>>|&>|&>>)[[:space:]]*['"'"'"]?'"$re" <<<"$cmd" && return 0
  grep -qE '(^|[[:space:]]|;|&|\||\()tee([[:space:]]+-[a-zA-Z]+)*[[:space:]]+['"'"'"]?'"$re" <<<"$cmd" && return 0
  for _bin in cp mv rm ln mkdir chmod chown truncate dd touch install tar rsync curl wget unzip patch; do
    if grep -qE "(^|[[:space:]]|;|&|\||\()${_bin}([[:space:]]+-[a-zA-Z=0-9]+)*[[:space:]]+[^|;&]*['\"]?${re}" <<<"$cmd"; then
      return 0
    fi
  done
  if grep -qE '(^|[[:space:]]|;|&|\|)sed[[:space:]]' <<<"$cmd" && \
     grep -qE '(^|[[:space:]])-[a-zA-Z]*i[a-zA-Z]*([[:space:]]|$)' <<<"$cmd" && \
     grep -qE "$re" <<<"$cmd"; then
    return 0
  fi
  # git plumbing that materialises a path in the work tree without a shell
  # redirect (restore/checkout-index/update-index/apply/checkout -- <path>).
  if grep -qE '(^|[[:space:]]|;|&|\||\()git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(restore|checkout|checkout-index|update-index|apply|am|stash)([[:space:]]|$)' <<<"$cmd" && \
     grep -qE "$re" <<<"$cmd"; then
    return 0
  fi
  return 1
}

codex_write=false
if _codex_write_idiom "$_codex_re" || _codex_write_idiom "$_codex_marker_re"; then
  codex_write=true
fi

if [ "$codex_write" = "true" ] && [ "$should_block" != "true" ]; then
  should_block=true
  block_rule="codex-write"
  block_msg="the Codex login directory at /home/node/.codex (and the .vibe-allow-codex opt-in marker) is the Mac's own credential store - writes are blocked; only the codex CLI may change it, and the marker is created on the Mac."
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
        permissionDecisionReason: "vibe: shell command modifies the learning library - confirm to proceed"
      }
    }')"
fi

exit 0
