#!/usr/bin/env bash
# vibe PreToolUse guardrail for Write/Edit/MultiEdit tool calls.
# Reads PreToolUse JSON from stdin and inspects the target path:
#   /learnings  -> permissionDecision:ask   (user confirms y/n before the write)
#   /zotero     -> permissionDecision:deny  (bind mount is contractually
#                  read-only; there is no legitimate write to the user's
#                  Zotero library from in here)
#   /home/node/.codex -> permissionDecision:deny (the Codex CLI login dir is
#                  bind-mounted READ-WRITE from the Mac for token refresh;
#                  its config.toml can name programs Codex runs on the host,
#                  so no tool write there is ever legitimate — only the
#                  codex binary itself touches it)
# Anything else exits 0 silently.
#
# Both mounts are declared readonly in devcontainer.json, but macOS Docker's
# fakeowner overlay silently drops that flag (task_009 finding), so this hook
# is the real guarantee, not the mount flag.
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
    --arg reason "vibe: modifying the learning library at ${norm_path} - confirm to proceed" \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: $reason
      }
    }')"
  exit 0
fi

# Check whether the normalized path equals /zotero or is nested beneath it.
# The -d test keeps this inert on machines with no Zotero mount: without the
# mount there is no library to protect, and /zotero is just an ordinary
# (absent) container path.
if [ -d /zotero ] && { [ "$norm_path" = "/zotero" ] || [[ "$norm_path" == /zotero/* ]]; }; then
  printf '%s\n' "$(jq -n \
    --arg reason "vibe: the Zotero library at ${norm_path} is mounted read-only - writes are blocked; copy the file into /workspace if you need to change it" \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: $reason
      }
    }')"
  exit 0
fi

# Codex login directory: deny unconditionally (no -d gate — the deny costs
# nothing when the mount is absent, and a session must never be able to plant
# a config.toml that the user's next `codex` run on the Mac would execute).
# The /workspace/.vibe-allow-codex marker is the switch that GRANTS that
# mount on the next launch, so a session may not create it either.
if [ "$norm_path" = "/home/node/.codex" ] || [[ "$norm_path" == /home/node/.codex/* ]] || \
   [ "$norm_path" = "/workspace/.vibe-allow-codex" ]; then
  printf '%s\n' "$(jq -n \
    --arg reason "vibe: ${norm_path} controls the Mac's Codex credential store - writes are blocked; only the codex CLI changes ~/.codex, and the .vibe-allow-codex opt-in is created on the Mac" \
    '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: $reason
      }
    }')"
  exit 0
fi

exit 0
