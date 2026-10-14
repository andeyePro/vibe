#!/bin/bash
# vibe /vsss keep-going guard — installed as /usr/local/bin/vsss-stop-guard
# (root-owned, 0755). One script, two runtimes: Claude Code runs it from the
# Stop hook vibe templates into settings.local.json, Codex from the managed
# Stop hook in /etc/codex/hooks/hooks.json (Codex 0.154 accepts the same
# `{"decision":"block","reason":…}` reply, and feeds the reason back to the
# model as its next prompt).
#
# WHY: a /vsss run is nothing but the model continuing to emit tool calls.
# The run ends the instant a turn ends, and the commonest way it ends early is
# the model deciding that a question or a blocker is a reason to stop and
# wait. vsss.md already says it is not; this hook makes that deterministic.
# While the run THIS session owns is live (no `## Final state` in its session
# file), ending the turn is refused and the model is told to post the
# question to the answer channel and carry on with work that does not depend
# on it. A real exit writes Final state and `active=0` first, and then the
# hook lets it go.
#
# OWNERSHIP is explicit, never inferred: /vsss writes `owner=<session id>`
# into .vss/auto-resume (Claude Code's $CLAUDE_CODE_SESSION_ID, Codex's
# $CODEX_THREAD_ID), and the guard acts only when the Stop payload's
# session_id is exactly that value. Another session in the same workspace —
# or one that merely read the session file — is never touched.
#
# It never traps a session. Every doubt allows the stop:
#   * no marker, a symlinked marker, `active` not exactly 1, no `owner=`, or
#     a session_file value that is not a plain .vss/sessions/<name>.md;
#   * the payload has no session_id, or it is not the owner;
#   * the marker has not been refreshed for VIBE_STOP_GUARD_FRESH_SECS
#     (default 6h; /vsss refreshes it every iteration) — a crash-left marker
#     must not capture a conversation resumed days later;
#   * the session file is missing or already has `## Final state`;
#   * a human decision is pending (.vss/awaiting-human, task_058);
#   * VIBE_STOP_GUARD_MAX (default 3) refusals in a row with no new commit:
#     the stop is let through, and every later stop is too until HEAD moves
#     (the release is remembered, so a `continue` from codex-supervisor or a
#     new user turn does not re-arm another round of refusals);
#   * its own counter is not a regular file, or anything fails: unreadable or
#     non-JSON input, jq missing, a failed write.
#
# ASK MODE (`vsss-stop-guard ask`, Claude Code's PreToolUse hook on
# AskUserQuestion): the other way a live run halts. An AskUserQuestion never
# ends the turn, so the Stop check above never fires, and the pending question
# (.vss/awaiting-human) also stands the launcher's stall watchdog down — one
# routine question would park an unattended run until someone came back. So
# while the owned run is live and past its front-loaded start (its session
# file has an `## Iter` block), the tool call is DENIED with the same "post it
# to fromClaude and carry on" instruction. A hard-escalate is still asked: it
# ends the run, so vsss.md has it write Final state and active=0 first, after
# which this lets the question through. On every allow in ask mode it writes
# .vss/awaiting-human exactly as the plain hook it replaces did (only when a
# marker file exists); it never writes it on a deny. There is no refusal cap
# here: a denied question traps nothing — the model can carry on or exit; a
# model that retries the same question forever only burns its own window
# (each retry is a tool call, so the heartbeat stays fresh). An existing
# .vss/awaiting-human does NOT short-circuit ask mode: a stale one (an
# answered question whose PostToolUse never ran) would otherwise let every
# later question through.
#
# Besides that marker, the only thing it ever writes is its own counter,
# .vss/stop-guard.
set -uo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

root=${VIBE_STOP_GUARD_ROOT:-/workspace}
max=${VIBE_STOP_GUARD_MAX:-3}
fresh=${VIBE_STOP_GUARD_FRESH_SECS:-21600}
case "$max" in '' | *[!0-9]*) max=3 ;; esac
case "$fresh" in '' | *[!0-9]*) fresh=21600 ;; esac

mode=stop
[ "${1:-}" = ask ] && mode=ask

allow() {
  if [ "$mode" = ask ] && [ -f "$root/.vss/auto-resume" ]; then
    { date +%s > "$root/.vss/awaiting-human.tmp.$$" && mv -f -- "$root/.vss/awaiting-human.tmp.$$" "$root/.vss/awaiting-human"; } 2>/dev/null ||
      rm -f -- "$root/.vss/awaiting-human.tmp.$$" 2>/dev/null
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || allow
payload=$(cat 2>/dev/null) || allow
[ -n "$payload" ] || allow
session_id=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null) || allow
[ -n "$session_id" ] || allow
last_message=$(printf '%s' "$payload" | jq -r '.last_assistant_message // empty' 2>/dev/null) || last_message=""

vss=$root/.vss
marker=$vss/auto-resume
[ -f "$marker" ] && [ ! -L "$marker" ] || allow
[ "$mode" = stop ] && [ -e "$vss/awaiting-human" ] && allow
# Stop mode answers only the Stop event: a newer settings file pointing an
# older image's guard at another event must fail open, not block the tool.
if [ "$mode" = stop ]; then
  event=$(printf '%s' "$payload" | jq -r '.hook_event_name // "Stop"' 2>/dev/null) || allow
  [ "$event" = Stop ] || allow
fi

field() { sed -n "s/^$1=//p" "$marker" 2>/dev/null | tail -n1; }
[ "$(field active)" = 1 ] || allow
owner=$(field owner)
[ -n "$owner" ] && [ "$owner" = "$session_id" ] || allow
session_rel=$(field session_file)
[[ $session_rel =~ ^\.vss/sessions/[A-Za-z0-9._-]+\.md$ ]] || allow
session=$root/$session_rel
[ -f "$session" ] && [ ! -L "$session" ] || allow
grep -q '^## Final state' "$session" 2>/dev/null && allow

now=$(date +%s)
mtime=$(stat -c %Y -- "$marker" 2>/dev/null || stat -f %m -- "$marker" 2>/dev/null) || allow
[ $((now - mtime)) -le "$fresh" ] || allow

if [ "$mode" = ask ]; then
  # Front-loaded questions (vsss.md asks some before the autonomous phase)
  # come before the first iteration block.
  grep -q '^## Iter' "$session" 2>/dev/null || allow
  reason="vibe /vsss keep-going guard: the /vsss run in $session_rel is live and unattended. If this question is on the hard-escalate list, you must NOT carry on: write '## Final state' (the abort) to $session_rel and set active=0 in .vss/auto-resume, then ask again and it is allowed. Otherwise do not ask it here, because it would park the run until someone comes back: put it in the fromClaude answer file as a short numbered action point with your recommended reversible default, note in the session file which work it parks, and carry on with the next item that does not depend on it."
  jq -n --arg reason "$reason" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}' 2>/dev/null || allow
  exit 0
fi

# Progress is a new commit, nothing else: a note appended to the session file
# is cheap to produce and would let a stuck run reset the count forever.
head_sha=$(git -C "$root" rev-parse -q --verify HEAD 2>/dev/null || echo none)
key="$session_id $head_sha"

state=$vss/stop-guard
count=0
if [ -e "$state" ] || [ -L "$state" ]; then
  [ -f "$state" ] && [ ! -L "$state" ] || allow
  if [ "$(sed -n 's/^key=//p' "$state" 2>/dev/null | head -n1)" = "$key" ]; then
    [ "$(sed -n 's/^released=//p' "$state" 2>/dev/null | head -n1)" = 1 ] && allow
    count=$(sed -n 's/^count=//p' "$state" 2>/dev/null | head -n1)
    case "$count" in '' | *[!0-9]*) count=0 ;; esac
  fi
fi
count=$((count + 1))
released=0
[ "$count" -gt "$max" ] && released=1

tmp=$(mktemp "$vss/stop-guard.tmp.XXXXXX" 2>/dev/null) || allow
if ! { printf 'key=%s\ncount=%s\nreleased=%s\n' "$key" "$count" "$released" > "$tmp" && mv -f -- "$tmp" "$state"; } 2>/dev/null; then
  rm -f -- "$tmp" 2>/dev/null
  allow
fi
if [ "$released" = 1 ]; then
  printf 'vsss-stop-guard: %s refusals with no new commit on %s; letting this and later stops through until HEAD moves\n' "$max" "$session_rel" >&2
  allow
fi

exit_note=""
last_line=$(printf '%s' "$last_message" | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba' -e '}' | tail -n1)
case "$last_line" in
  VSSS-EXIT:*) exit_note=" You ended on a VSSS-EXIT line, but the session file has no Final state. If that exit is one of vsss.md's numbered exit conditions, write the Final state and active=0 first, then end on the VSSS-EXIT line again; a question or a wait for an answer is not one." ;;
esac

reason="vibe /vsss keep-going guard (refusal $count of $max): the /vsss run in $session_rel is still live — it has no '## Final state' — so ending the turn now would silently stop it. A question, a missing answer or a blocker on one item is NOT an exit condition.$exit_note Now: (1) put each question that needs the user into the answer channel (Claude: the fromClaude file; Codex: the FM2C questions file) as a short numbered action point with your recommended reversible default, and note in the session file which work it parks; (2) pick the next queue item, TODO item or repo-scan area that does not depend on those answers, and carry on working. Stop only when an exit condition in vsss.md § Exit conditions has really fired — then append '## Final state' to $session_rel, set active=0 in .vss/auto-resume, and end the report with the VSSS-EXIT line. If the user has told you in this conversation to stop or pause, that is their call: set active=0 in .vss/auto-resume and stop."
jq -n --arg reason "$reason" '{decision: "block", reason: $reason}' 2>/dev/null || allow
exit 0
