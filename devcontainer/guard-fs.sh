#!/usr/bin/env bash
# vibe PreToolUse guardrail for Write/Edit/MultiEdit tool calls.
# Reads PreToolUse JSON from stdin; if the target path is inside /learnings,
# emits a permissionDecision:ask envelope to stdout so Claude Code prompts
# the user y/n before proceeding. Otherwise exits 0 silently.
set -euo pipefail

raw_path=$(jq -r '.tool_input.file_path // empty')

# Nothing to check if no path was supplied.
if [ -z "$raw_path" ]; then
  exit 0
fi

# Normalize the path (resolve .., ., double-slashes) without requiring it to
# exist. realpath -m is the POSIX-extension form that works on absent paths.
norm_path=$(realpath -m "$raw_path")

# Check whether the normalized path equals /learnings or is nested beneath it.
if [ "$norm_path" = "/learnings" ] || [[ "$norm_path" == /learnings/* ]]; then
  printf '%s\n' "$(jq -n \
    --arg reason "vibe: modifying the learning library at ${norm_path} — confirm to proceed" \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: $reason
      }
    }')"
fi

exit 0
