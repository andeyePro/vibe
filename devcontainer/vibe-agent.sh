#!/bin/bash
# Queue a runtime change; only the host launcher can apply it or grant login.
set -euo pipefail
case "${1:-}" in
  claude|codex) [ "$#" = 1 ] || { echo 'Usage: vibe-agent claude|codex' >&2; exit 1; } ;;
  --help|-h) echo 'Usage: vibe-agent claude|codex'; echo 'Queue a change, then exit the current session normally.'; exit 0 ;;
  *) echo 'Usage: vibe-agent claude|codex'; echo 'Queue the other agent, then exit this session normally. Active autonomous runs must be stopped first.'; exit 1 ;;
esac
# The devcontainer mounts the launcher-selected folder here, even in a monorepo.
project=/workspace
exec /usr/bin/python3 -I /usr/local/share/vibe/host-onboarding.py request-agent "$project" "$1"
