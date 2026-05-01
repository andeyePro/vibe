#!/usr/bin/env bash
# check-sp-current.sh - report drift between sp.md's hardcoded Superpowers
# skill list and the upstream obra/superpowers skills/ directory.
#
# Usage:
#   check-sp-current.sh                 # online: fetch upstream + compare
#   check-sp-current.sh --offline       # offline: skip fetch, exit silent
#   check-sp-current.sh --fixture FILE  # read upstream skill names from FILE
#                                       # (one per line; testable mode)
#
# Behavior: exits 0 in all cases (informational). Writes a summary to
# stderr if drift detected. Falls back gracefully when upstream is
# unreachable or curl/jq are missing.
#
# Override SP_MD env var to point at a different sp.md (used by smoke tests).

set -euo pipefail

SP_MD_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/commands/sp.md"
SP_MD="${SP_MD:-$SP_MD_DEFAULT}"
UPSTREAM_API="${UPSTREAM_API:-https://api.github.com/repos/obra/superpowers/contents/skills}"

mode="online"
fixture=""
case "${1:-}" in
  --offline) mode="offline" ;;
  --fixture)
    mode="fixture"
    fixture="${2:-}"
    if [ -z "$fixture" ] || [ ! -r "$fixture" ]; then
      echo "check-sp-current: --fixture requires a readable file" >&2
      exit 1
    fi
    ;;
  '') ;;
  *) echo "check-sp-current: unknown arg: $1" >&2; exit 1 ;;
esac

# Extract local skill names from sp.md - matches `superpowers:foo-bar` tokens
# and strips the prefix. Sort + uniq for deterministic comparison.
extract_local() {
  [ -r "$SP_MD" ] || { echo "check-sp-current: sp.md not readable: $SP_MD" >&2; return 1; }
  grep -oE 'superpowers:[a-z][a-z0-9-]*' "$SP_MD" \
    | sed 's/^superpowers://' \
    | sort -u
}

# Fetch upstream skill names. Requires curl + jq. Returns empty + warns on
# any error (network, missing tools, malformed JSON) so the caller can
# fall back to "no upstream data, skip drift check".
fetch_upstream() {
  command -v curl >/dev/null || { echo "check-sp-current: curl missing, skipping" >&2; return 1; }
  command -v jq >/dev/null   || { echo "check-sp-current: jq missing, skipping"   >&2; return 1; }
  local payload
  payload="$(curl -fsS --max-time 10 "$UPSTREAM_API" 2>/dev/null)" \
    || { echo "check-sp-current: upstream fetch failed, skipping" >&2; return 1; }
  printf '%s' "$payload" | jq -r '.[]? | select(.type=="dir") | .name' 2>/dev/null \
    | sort -u
}

local_set="$(extract_local)" || exit 0
[ -z "$local_set" ] && { echo "check-sp-current: no skills in sp.md, nothing to compare" >&2; exit 0; }

case "$mode" in
  offline)
    # Silent in offline mode - the local list is good if no online check is desired.
    exit 0
    ;;
  fixture)
    upstream_set="$(sort -u < "$fixture")"
    ;;
  online)
    upstream_set="$(fetch_upstream)" || exit 0
    ;;
esac

[ -z "$upstream_set" ] && { echo "check-sp-current: empty upstream set, skipping" >&2; exit 0; }

# Set diff (POSIX comm needs sorted input - both already sorted by extract/fetch).
local_tmp="$(mktemp)"
upstream_tmp="$(mktemp)"
trap 'rm -f "$local_tmp" "$upstream_tmp"' EXIT
printf '%s\n' "$local_set"    > "$local_tmp"
printf '%s\n' "$upstream_set" > "$upstream_tmp"

# Missing locally = in upstream but not in sp.md (stale skill list).
# Extra locally  = in sp.md  but not in upstream (skill removed/renamed).
missing="$(comm -23 "$upstream_tmp" "$local_tmp")"
extra="$(comm -13 "$upstream_tmp" "$local_tmp")"

if [ -n "$missing" ] || [ -n "$extra" ]; then
  {
    echo "check-sp-current: DRIFT - sp.md skill list differs from upstream obra/superpowers"
    if [ -n "$missing" ]; then
      echo "  Missing from sp.md (in upstream skills/):"
      printf '%s\n' "$missing" | sed 's/^/    - /'
    fi
    if [ -n "$extra" ]; then
      echo "  Extra in sp.md (not in upstream skills/):"
      printf '%s\n' "$extra" | sed 's/^/    - /'
    fi
  } >&2
fi
exit 0
