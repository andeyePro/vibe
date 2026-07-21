#!/usr/bin/env bash
# RED demo: same test as finding1_failopen.sh but sourcing a copy of vibe
# with the finding-1 fix line reverted (setup_token "$repo" instead of
# setup_token "$repo" || true) — reproduces the cycle-1 hard-abort bug.
set -euo pipefail

VIBE="/workspace/.vs/cycle-2/scratch-tests/vibe-pre-fix1.sh"
TMP=$(mktemp -d)
export HOME="$TMP"
export VIBE_CONFIG="$TMP/no-config"
export VIBE_SOURCE_ONLY=1

# shellcheck disable=SC1090
source "$VIBE"

stored_token_rejected() { return 0; }  # force "rejected" branch

echo "--- calling maybe_reprompt_stored_token with closed stdin, set -euo pipefail live (PRE-FIX code) ---"
maybe_reprompt_stored_token owner/repo ghp_task026_fixture_token < /dev/null
rc=$?
echo "SURVIVED: maybe_reprompt_stored_token returned rc=$rc"
echo "SCRIPT_ALIVE_AFTER_CALL"
