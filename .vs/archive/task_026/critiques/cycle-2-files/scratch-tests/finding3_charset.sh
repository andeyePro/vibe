#!/usr/bin/env bash
# Finding 3 (LOW): rotate_token charset hardening — a pasted token
# containing a double-quote, backslash, whitespace, or control character
# must be refused (exit 1, pinned stderr message), store left unchanged.
# The existing empty-input abort must be untouched.
set -uo pipefail

VIBE="/workspace/vibe"
FAIL=0

check() {
  local desc="$1" cond="$2"
  if [ "$cond" = "0" ]; then echo "PASS: $desc"; else echo "FAIL: $desc"; FAIL=1; fi
}

run_case() {
  # $1 = description, $2 = token to feed (raw, will be printf %s piped), $3 = expect_bad(1)/expect_ok(0)
  local desc="$1" token="$2" expect_bad="$3"
  local tmp; tmp=$(mktemp -d)
  local home="$tmp/home"
  mkdir -p "$home/.vibe"
  printf 'owner/repo=ghp_existing\n' > "$home/.vibe/tokens"
  chmod 600 "$home/.vibe/tokens"
  local orig; orig=$(cat "$home/.vibe/tokens")

  local out rc
  out=$(HOME="$home" VIBE_CONFIG="$home/no-config" VIBE_SOURCE_ONLY=1 bash -c "
    set -e
    source '$VIBE'
    printf '%s\\n' \"\$1\" | rotate_token owner/repo
  " _ "$token" 2>&1)
  rc=$?

  local after; after=$(cat "$home/.vibe/tokens")

  if [ "$expect_bad" = "1" ]; then
    check "$desc: exit 1" "$([ "$rc" -eq 1 ] && echo 0 || echo 1)"
    check "$desc: pinned refusal message" "$(echo "$out" | grep -qF 'vibe pat: token contains characters no GitHub PAT uses — not saved' && echo 0 || echo 1)"
    check "$desc: store unchanged" "$([ "$after" = "$orig" ] && echo 0 || echo 1)"
    check "$desc: token value absent from output" "$(echo "$out" | grep -qF "$token" && echo 1 || echo 0)"
  else
    check "$desc: exit 0" "$([ "$rc" -eq 0 ] && echo 0 || echo 1)"
    check "$desc: store WAS updated" "$(echo "$after" | grep -qF "owner/repo=$token" && echo 0 || echo 1)"
  fi
}

# --- RED demo first: confirm these are genuinely rejected characters by
# checking a plain valid fixture-shaped token still saves fine (control). ---
run_case "control: clean token" "ghp_task026_fixture_token" 0

run_case "double-quote" 'ghp_bad"token' 1
run_case "backslash" 'ghp_bad\token' 1
run_case "embedded space" 'ghp_bad token' 1
run_case "embedded tab" "$(printf 'ghp_bad\ttoken')" 1
run_case "embedded newline (via printf, not the empty-input path)" "$(printf 'ghp_bad\x01token')" 1

# --- existing empty-input abort must be untouched ---
tmp=$(mktemp -d); home="$tmp/home"; mkdir -p "$home/.vibe"
printf 'owner/repo=ghp_existing\n' > "$home/.vibe/tokens"; chmod 600 "$home/.vibe/tokens"
orig=$(cat "$home/.vibe/tokens")
out=$(HOME="$home" VIBE_CONFIG="$home/no-config" VIBE_SOURCE_ONLY=1 bash -c "source '$VIBE'; rotate_token owner/repo < /dev/null" 2>&1)
rc=$?
after=$(cat "$home/.vibe/tokens")
check "empty-input abort still exit 1" "$([ "$rc" -eq 1 ] && echo 0 || echo 1)"
check "empty-input abort message unchanged" "$(echo "$out" | grep -qF 'aborted — token store unchanged' && echo 0 || echo 1)"
check "empty-input store unchanged" "$([ "$after" = "$orig" ] && echo 0 || echo 1)"

exit $FAIL
