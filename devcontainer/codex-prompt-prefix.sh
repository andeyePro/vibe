#!/bin/bash
# vibe Codex UserPromptSubmit prefix hook — installed as
# /usr/local/bin/codex-prompt-prefix (root-owned, 0755), invoked by the
# managed hook in /etc/codex/hooks/hooks.json for every UserPromptSubmit
# event (task_053).
#
# This hook ADDS CONTEXT; it never guards. When the prompt's first
# non-whitespace token is exactly /vs, /vss or /vsss (case-sensitive) it
# tells the model that the typed command is the same as the matching
# $-form skill and to invoke that skill now with everything after the
# token — every following line included — as its arguments, verbatim.
# Anything else, and ANY failure of its own (unreadable or non-JSON stdin,
# jq missing or failing), produces no output and exits 0: a broken or
# confused hook here must never block a prompt (Astra's review, 2026-09-12:
# every jq call is guarded, and the arguments travel on jq's stdin, never
# as a command-line argument, so their length cannot make the hook fail).
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin
unset BASH_ENV ENV

command -v jq >/dev/null 2>&1 || exit 0

payload=$(cat) || exit 0
event=$(printf '%s' "$payload" | jq -r '.hook_event_name // empty' 2>/dev/null) || exit 0
if [ "$event" = "SessionStart" ]; then
  jq -n '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext:
    "Read /usr/local/share/vibe/codex-context.md for project context discovery and FM2C asynchronous answers. Run codex-context to locate configured references. Read project AGENTS.md and CLAUDE.md before work; preserve active task state on resume."}}' || true
  exit 0
fi
# Sentinel capture (Astra re-review): `$(...)` would strip trailing newlines,
# which are argument content; the marker keeps them.
prompt=$(printf '%s' "$payload" | jq -r '.prompt // empty' 2>/dev/null; printf x) || exit 0
prompt=${prompt%x}
prompt=${prompt%$'\n'}   # jq -r's own line terminator, not prompt content
[ -n "$prompt" ] || exit 0

# First token = up to the first whitespace (space, tab or newline) after any
# leading whitespace; the remainder keeps every later line intact and loses
# only the whitespace that separated it from the token.
stripped=${prompt#"${prompt%%[![:space:]]*}"}
help_text=${stripped%"${stripped##*[![:space:]]}"}
help_text=$(printf '%s' "$help_text" | tr '[:upper:]' '[:lower:]')
case "$help_text" in
  help|help\?|commands|\?|"what can i do"|"what can i do?"|"what can you do"|"what can you do?")
    jq -n '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext:
      "The user is asking for Vibe help. Give a short practical command guide, not a development task. Explain: ordinary text describes what to build; $vs runs adversarial implementation/testing; $vss handles one task autonomously; $vsss continues within the task scope until finished or externally blocked; see FM2C reads the configured reply file; ask to switch to Claude or Codex to queue a change with vibe-agent, then exit normally to reopen. In Codex the $ spellings are reliable. A bare /vs, /vss or /vsss may be rejected by the composer before submission; one leading space makes the slash form reach Vibe. Interactive $vsss is not automatically supervised after process exit. Host terminal: vibe reopens the project, vibe --help lists launcher options, vibe --codex-run <project-local-prompt> provides supervised execution. Mention other commands only after checking installed skills/command documents; do not invent parity with Claude-only commands. Do not execute a harness merely to answer help."}}' || true
    exit 0
    ;;
esac
fm2c=0
if [[ "$stripped" =~ (^|[[:space:]])[Ff][Mm]2[Cc]([[:space:][:punct:]]|$) ]]; then fm2c=1; fi
fm2c_note='FM2C means the configured Codex answer file (vibe-fromMartin-toCodex.md). Read /usr/local/share/vibe/codex-context.md and that channel now; apply answers and continue the active objective, preserving concurrent edits and archiving safely.'
first=${stripped%%[[:space:]]*}
rest=${stripped#"$first"}
rest=${rest#"${rest%%[![:space:]]*}"}

case "$first" in
  /vs | /vss | /vsss) name=${first#/} ;;
  *)
    if [ "$fm2c" = 1 ]; then
      jq -n --arg note "$fm2c_note" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $note}}' || true
    fi
    exit 0 ;;

esac

if [ -n "$rest" ]; then
  out=$(printf '%s' "$rest" | jq -Rs --arg name "$name" \
    '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext:
      ("The user typed the vibe command /" + $name +
       "; it is the same command as the $" + $name + " skill. Invoke the $" +
       $name + " skill now with these arguments, verbatim (they may span several lines): " + .)}}' \
    2>/dev/null) || exit 0
else
  out=$(jq -n --arg name "$name" \
    '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext:
      ("The user typed the vibe command /" + $name +
       "; it is the same command as the $" + $name + " skill. Invoke the $" +
       $name + " skill now with no arguments.")}}' 2>/dev/null) || exit 0
fi
[ -n "$out" ] || exit 0
if [ "$fm2c" = 1 ]; then
  out=$(printf '%s' "$out" | jq --arg note "$fm2c_note" '.hookSpecificOutput.additionalContext += ("\n" + $note)') || exit 0
fi
printf '%s\n' "$out"
exit 0
