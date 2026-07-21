#!/usr/bin/env bash
# Finding 1 (HIGH): maybe_reprompt_stored_token must survive setup_token's
# unguarded `read` hitting EOF on closed stdin, under set -euo pipefail.
# Empirical repro per Generator instructions: stub stored_token_rejected to
# return 0 (rejected), call the real (unmodified) setup_token via the real
# maybe_reprompt_stored_token, closed stdin, set -euo pipefail shell.
set -euo pipefail

VIBE="/workspace/vibe"
TMP=$(mktemp -d)
export HOME="$TMP"
export VIBE_CONFIG="$TMP/no-config"
export VIBE_SOURCE_ONLY=1

# shellcheck disable=SC1090
source "$VIBE"

stored_token_rejected() { return 0; }  # force "rejected" branch

echo "--- calling maybe_reprompt_stored_token with closed stdin, set -euo pipefail live ---"
maybe_reprompt_stored_token owner/repo ghp_task026_fixture_token < /dev/null
rc=$?
echo "SURVIVED: maybe_reprompt_stored_token returned rc=$rc"
echo "SCRIPT_ALIVE_AFTER_CALL"

if [ "$rc" -ne 0 ]; then
  echo "FAIL: expected return 0, got $rc"
  exit 1
fi

echo "PASS"
