#!/usr/bin/env bash
# Finding 2 (MEDIUM): slug trust boundary — detect_github_repo's regex is
# looser than is_valid_repo_slug. Two sinks must now refuse a malformed
# detected slug: (a) pat_handle_subcommand no-arg path, (b)
# maybe_reprompt_stored_token's early-return guard.
set -uo pipefail  # not -e: we want to inspect non-zero exits inline

VIBE="/workspace/vibe"
FAIL=0

check() {
  local desc="$1" cond="$2"
  if [ "$cond" = "0" ]; then
    echo "PASS: $desc"
  else
    echo "FAIL: $desc"
    FAIL=1
  fi
}

# --- (a) pat_handle_subcommand no-arg path, malformed detected slug ---
TMP=$(mktemp -d)
CHECKOUT="$TMP/checkout"
mkdir -p "$CHECKOUT"
(cd "$CHECKOUT" && git init -q && git remote add origin 'https://github.com/owner/repo.with.dots.git')
# detect_github_repo's regex [^/]+/[^/.]+ rejects a repo segment containing
# a literal dot before .git is stripped by the trailing (\.git)? — but a
# space or other odd char in the remote slug is a cleaner "looser than
# is_valid_repo_slug" demo. Use a slug containing a character
# is_valid_repo_slug disallows but detect_github_repo's [^/.]+ allows: '+'.
(cd "$CHECKOUT" && git remote set-url origin 'https://github.com/owner/re+po.git')

OUT=$(cd "$CHECKOUT" && HOME="$TMP/home" VIBE_CONFIG="$TMP/home/no-config" VIBE_SOURCE_ONLY=1 \
  bash -c "set -e; source '$VIBE'; pat_handle_subcommand pat < /dev/null" 2>&1)
RC=$?
echo "$OUT"
check "(a) detected malformed slug 're+po' refused, exit 1" "$([ "$RC" -eq 1 ] && echo 0 || echo 1)"
check "(a) stderr names the invalid detected slug" "$(echo "$OUT" | grep -q "detected remote slug 'owner/re+po' is not a valid owner/repo" && echo 0 || echo 1)"

# Sanity: is_valid_repo_slug itself rejects '+'.
VIBE_SOURCE_ONLY=1 HOME="$TMP/home-sanity" bash -c "set -e; source '$VIBE'; if is_valid_repo_slug 'owner/re+po'; then exit 9; else exit 0; fi"
check "(sanity) is_valid_repo_slug rejects 'owner/re+po'" "$?"

# --- (b) maybe_reprompt_stored_token guard, malformed slug ---
SCRIPT='
set -e
source '"'$VIBE'"'
probe_called=0
setup_called=0
stored_token_rejected() { probe_called=1; return 0; }
setup_token() { setup_called=1; }
set +e
maybe_reprompt_stored_token "owner/re+po" ghp_task026_fixture_token
RC=$?
set -e
echo "RC=$RC"
echo "PROBE=$probe_called"
echo "SETUP=$setup_called"
'
OUT2=$(HOME="$TMP/home2" VIBE_CONFIG="$TMP/home2/no-config" VIBE_SOURCE_ONLY=1 bash -c "$SCRIPT")
echo "$OUT2"
check "(b) malformed repo -> no probe" "$(echo "$OUT2" | grep -q 'PROBE=0' && echo 0 || echo 1)"
check "(b) malformed repo -> no setup_token" "$(echo "$OUT2" | grep -q 'SETUP=0' && echo 0 || echo 1)"
check "(b) malformed repo -> wrapper still returns 0 (fail-open)" "$(echo "$OUT2" | grep -q 'RC=0' && echo 0 || echo 1)"

# --- control: a VALID slug still probes normally (guard isn't over-broad) ---
SCRIPT_VALID='
set -e
source '"'$VIBE'"'
probe_called=0
setup_called=0
stored_token_rejected() { probe_called=1; return 1; }
setup_token() { setup_called=1; }
set +e
maybe_reprompt_stored_token "owner/repo" ghp_task026_fixture_token
RC=$?
set -e
echo "RC=$RC"
echo "PROBE=$probe_called"
'
OUT3=$(HOME="$TMP/home3" VIBE_CONFIG="$TMP/home3/no-config" VIBE_SOURCE_ONLY=1 bash -c "$SCRIPT_VALID")
echo "$OUT3"
check "(control) valid slug still probes" "$(echo "$OUT3" | grep -q 'PROBE=1' && echo 0 || echo 1)"

exit $FAIL
