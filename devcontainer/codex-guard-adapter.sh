#!/bin/bash
# vibe Codex PreToolUse guard adapter — installed as
# /usr/local/bin/codex-guard-adapter (root-owned, 0755), invoked by the
# managed hooks in /etc/codex/hooks/hooks.json as:
#
#   codex-guard-adapter bash     (matcher "Bash")
#   codex-guard-adapter patch    (matcher "apply_patch|Write|Edit")
#
# CONTRACT
# --------
# Codex's PreToolUse wire format is Claude Code's (verified at tag
# rust-v0.154.0, core/src/tools/hook_names.rs): the shell tool reaches hooks
# as tool_name "Bash" with the command STRING in tool_input.command, and
# apply_patch reaches them as "apply_patch" (aliases "Write"/"Edit") with the
# RAW PATCH TEXT in tool_input.command. That compatibility is the whole
# reason this adapter can reuse vibe's existing, unmodified guards rather
# than fork them:
#
#   bash  -> stdin is piped UNCHANGED into guard-bash.sh.
#   patch -> every path the patch touches is extracted and passed to
#            guard-fs.sh one at a time, shaped as a Claude Code Write call.
#
# guard-bash.sh and guard-fs.sh are NOT modified by this file and must never
# need to be: one wire format, one set of rules, one place to audit them.
#
# ASK BECOMES DENY
# ----------------
# The guards answer `ask` for the /learnings library, because in a Claude
# Code session a human is at the prompt to say yes. A Codex-led vibe session
# is unattended — there is nobody to ask, and Codex treats an unanswered
# permission decision as its own business. So every `ask` this adapter sees
# is rewritten to `deny`, keeping the guard's original reason. Erring toward
# deny costs a refused write; erring toward allow costs an unreviewed one.
#
# FAIL CLOSED
# -----------
# Codex fails OPEN if a hook command cannot be spawned at all (a missing
# binary is not a denial), which is exactly the wrong default for a guard.
# This adapter therefore refuses loudly — exit 2 with a reason on stderr,
# which Codex surfaces as a blocked tool call — whenever it cannot do its
# job: unknown mode, wrong argument count, unreadable or non-JSON stdin, a
# guard that is missing or not executable, a guard that exits non-zero for
# an unexpected reason, a guard that prints something that is not JSON, or a
# relative patch path with no cwd to resolve it against. Silence from this
# script always means "the guards looked and had nothing to say".
#
# GUARD LOCATION
# --------------
# The guards are taken from the directory this script itself lives in, which
# in the image is /usr/local/bin — so the installed adapter runs
# /usr/local/bin/guard-bash.sh and /usr/local/bin/guard-fs.sh, the same
# root-owned files the Claude Code hooks use. Resolving relative to $0 (and
# not a hard-coded path) is what lets the smoke tests and
# codex-guard-liveness exercise a COPY of the whole chain — adapter and
# guards side by side in one directory — without a second code path. There
# is deliberately NO environment override (Astra's review of this file,
# 2026-09-11): an env var naming the guard directory would let whoever
# controls the hook's environment point it at guards that exit 0. The
# `node` user cannot write /usr/local/bin, and codex-guard-liveness asserts
# the ownership and modes of every file in the chain before a Codex-led
# session is allowed to start.
#
# ENVIRONMENT
# -----------
# Same review: a hook started as `/usr/bin/env bash` under a caller-
# controlled environment can be defeated before its first line runs (a
# BASH_ENV file that says `exit 0`; a PATH that resolves `bash` or `jq` to
# something else). So this script names /bin/bash directly in its shebang,
# the managed hooks.json starts it through `/usr/bin/env -i PATH=<fixed>
# /bin/bash` (absolute `env`, so PATH cannot pick a fake one either),
# and the first thing it does is pin PATH and drop the Bash start-up hooks
# again, so that even a direct invocation gets the same fixed environment.
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin
unset BASH_ENV ENV

CODEX_HOOK_EVENT=PreToolUse

die() {
  printf 'vibe codex-guard-adapter: %s\n' "$1" >&2
  exit 2
}

# Single deny reply on stdout, in the PreToolUse shape Codex expects.
emit_deny() {
  jq -n \
    --arg event "$CODEX_HOOK_EVENT" \
    --arg reason "$1" \
    '{
      hookSpecificOutput: {
        hookEventName: $event,
        permissionDecision: "deny",
        permissionDecisionReason: $reason
      }
    }'
}

command -v jq >/dev/null 2>&1 || die "jq is not available; cannot inspect the hook payload"

[ "$#" -eq 1 ] || die "expected exactly one argument (bash|patch), got $#"
mode=$1
case "$mode" in
  bash | patch) ;;
  *) die "unknown mode '${mode}' (expected 'bash' or 'patch')" ;;
esac

self_path=$0
if command -v realpath >/dev/null 2>&1; then
  self_path=$(realpath -- "$0" 2>/dev/null || printf '%s' "$0")
fi
guard_dir=$(dirname -- "$self_path")
guard_bash=$guard_dir/guard-bash.sh
guard_fs=$guard_dir/guard-fs.sh

require_guard() {
  [ -f "$1" ] || die "guard $1 is missing; refusing to let the tool call through"
  [ -x "$1" ] || die "guard $1 is not executable; refusing to let the tool call through"
}

tmpdir=$(mktemp -d) || die "could not create a temporary directory"
trap 'rm -rf "$tmpdir"' EXIT
guard_err=$tmpdir/guard.err

payload=""
if ! payload=$(cat); then
  die "could not read the hook payload from stdin"
fi
[ -n "$payload" ] || die "empty hook payload on stdin"
printf '%s' "$payload" | jq -e . >/dev/null 2>&1 ||
  die "hook payload on stdin is not valid JSON"

# Pass a guard's own reply through, rewriting `ask` to `deny`. Anything that
# is not parseable JSON is a fault, not an allow.
relay_guard_reply() {
  local reply=$1 decision reason
  if [ -z "$reply" ]; then
    return 0
  fi
  printf '%s' "$reply" | jq -e . >/dev/null 2>&1 ||
    die "guard reply was not valid JSON; refusing to let the tool call through"
  decision=$(printf '%s' "$reply" | jq -r '.hookSpecificOutput.permissionDecision // empty')
  if [ "$decision" = "ask" ]; then
    reason=$(printf '%s' "$reply" | jq -r '.hookSpecificOutput.permissionDecisionReason // empty')
    emit_deny "$reason"
    return 0
  fi
  printf '%s\n' "$reply"
}

if [ "$mode" = "bash" ]; then
  require_guard "$guard_bash"

  rc=0
  guard_out=$(printf '%s' "$payload" | "$guard_bash" 2>"$guard_err") || rc=$?

  # exit 2 is the guards' documented block: propagate it verbatim, stderr and
  # all, so the operator sees the guard's own wording and the block is logged
  # by guard-bash.sh exactly as it is for a Claude Code session.
  if [ "$rc" -eq 2 ]; then
    cat "$guard_err" >&2
    exit 2
  fi
  if [ "$rc" -ne 0 ]; then
    cat "$guard_err" >&2
    die "guard-bash.sh exited ${rc}; refusing to let the command through"
  fi

  relay_guard_reply "$guard_out"
  exit 0
fi

# ── patch mode ───────────────────────────────────────────────────────────────
# apply_patch's envelope names every file it touches on a directive line:
#   *** Add File: <path>
#   *** Update File: <path>
#   *** Delete File: <path>
#   *** Move to: <path>            (the destination of a rename)
# The rest of the line is the path and MAY contain spaces, so the prefix is
# stripped literally rather than tokenised. A patch with no directive lines
# touches nothing and is allowed in silence.
require_guard "$guard_fs"

patch_text=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
hook_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')

check_path() {
  local path=$1 abs fs_payload reply rc=0 decision reason

  case "$path" in
    /*) abs=$path ;;
    *)
      [ -n "$hook_cwd" ] ||
        die "patch path '${path}' is relative and the hook payload has no cwd to resolve it against"
      abs=$hook_cwd/$path
      ;;
  esac

  fs_payload=$(jq -n --arg fp "$abs" '{tool_name: "Write", tool_input: {file_path: $fp}}')
  reply=$(printf '%s' "$fs_payload" | "$guard_fs" 2>"$guard_err") || rc=$?
  if [ "$rc" -ne 0 ]; then
    cat "$guard_err" >&2
    die "guard-fs.sh exited ${rc} for ${abs}; refusing to let the patch through"
  fi
  [ -n "$reply" ] || return 0

  printf '%s' "$reply" | jq -e . >/dev/null 2>&1 ||
    die "guard-fs.sh reply for ${abs} was not valid JSON; refusing to let the patch through"
  decision=$(printf '%s' "$reply" | jq -r '.hookSpecificOutput.permissionDecision // empty')
  case "$decision" in
    deny | ask)
      # One deny for the whole patch, carrying the FIRST offending path's
      # reason: apply_patch is atomic, so a single bad path is enough.
      reason=$(printf '%s' "$reply" | jq -r '.hookSpecificOutput.permissionDecisionReason // empty')
      emit_deny "$reason"
      exit 0
      ;;
    "" | allow) return 0 ;;
    *) die "guard-fs.sh returned an unknown decision '${decision}' for ${abs}" ;;
  esac
}

if [ -n "$patch_text" ]; then
  while IFS= read -r line; do
    line=${line%$'\r'}
    case "$line" in
      '*** Add File: '*) patch_path=${line#'*** Add File: '} ;;
      '*** Update File: '*) patch_path=${line#'*** Update File: '} ;;
      '*** Delete File: '*) patch_path=${line#'*** Delete File: '} ;;
      '*** Move to: '*) patch_path=${line#'*** Move to: '} ;;
      *) continue ;;
    esac
    [ -n "$patch_path" ] || continue
    check_path "$patch_path"
  done <<<"$patch_text"
fi

exit 0
