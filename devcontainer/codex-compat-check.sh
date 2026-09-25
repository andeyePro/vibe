#!/bin/bash
# codex-compat-check — installed as /usr/local/bin/codex-compat-check and run
# once at image build time, right after the Codex CLI and vibe's managed
# policy are in place.
#
# WHY: vibe now follows the latest Codex release automatically (the launcher
# resolves it from npm and rebuilds when it moves). A new release could quietly
# break what vibe's safety and supervision rely on, so the build fails unless
# the freshly installed binary still (these are smoke checks: a string in the
# binary shows a hook event is known, not that it behaves; the live proof is
# codex-guard-liveness's fixtures at every Codex session start):
#   1. reports a version at or above the policy floor (codex-guard-liveness);
#   2. loads the managed /etc/codex policy without error, with the unhooked
#      tool surfaces still off (multi_agent, multi_agent_v2, apps,
#      unified_exec: "false", or gone upstream as "removed");
#   3. speaks every app-server method codex-supervisor sends;
#   4. still knows the hook events and Stop-hook fields vibe's hooks use.
# A failed build makes the launcher fall back to the last Codex version that
# passed (vibe: build_base_image). Nothing here touches the network; it only
# runs the local binary.
#
# Usage: codex-compat-check [--codex <path>]
set -uo pipefail
export PATH=/usr/local/share/npm-global/bin:/usr/local/bin:/usr/bin:/bin

codex=codex
[ "${1:-}" = --codex ] && [ -n "${2:-}" ] && codex=$2

fail() { printf 'codex-compat-check: FAIL %s\n' "$*" >&2; exit 1; }
ok() { printf 'codex-compat-check: ok   %s\n' "$*"; }

command -v "$codex" >/dev/null 2>&1 || fail "codex is not installed"
version=$("$codex" --version 2>/dev/null | awk '{print $NF}')
[ -n "$version" ] || fail "codex --version printed nothing"
# Floor: the one codex-guard-liveness enforces at every session start.
floor=0.154.0
liveness=/usr/local/bin/codex-guard-liveness
if [ -r "$liveness" ]; then
  f=$(awk -F= '/^MIN_MAJOR=/{a=$2} /^MIN_MINOR=/{b=$2} /^MIN_PATCH=/{c=$2} END{if (a!="" && b!="" && c!="") print a"."b"."c}' "$liveness")
  [ -n "$f" ] && floor=$f
fi
lowest=$(printf '%s\n%s\n' "$floor" "${version%%-*}" | sort -t. -k1,1n -k2,2n -k3,3n | head -n 1)
[ "$lowest" = "$floor" ] || fail "codex $version is below the $floor floor vibe's policy was verified against"
ok "version $version (floor $floor)"

home=$(mktemp -d) || fail "no temp dir"
trap 'rm -rf "$home"' EXIT

features=$(CODEX_HOME=$home "$codex" features list 2>&1) || fail "codex features list failed under the managed policy: $(printf '%s' "$features" | tail -n 3)"
# The output must still parse as "<name> <stage> <true|false>" rows, or an
# absent feature below would prove nothing.
rows=$(printf '%s\n' "$features" | awk 'NF >= 3 && ($NF == "true" || $NF == "false")' | wc -l)
[ "$rows" -ge 10 ] || fail "codex features list no longer prints '<name> <stage> <true|false>' rows; the policy check cannot be trusted"
for feature in multi_agent multi_agent_v2 apps unified_exec; do
  line=$(printf '%s\n' "$features" | awk -v f="$feature" '$1 == f')
  [ -z "$line" ] && { ok "$feature: no longer listed upstream"; continue; }
  case "$(printf '%s' "$line" | awk '{print $2 " " $NF}')" in
    *" false" | "removed "*) ok "$feature: off" ;;
    *) fail "$feature is ON under the managed policy — the requirements pin no longer holds: $line" ;;
  esac
done

CODEX_HOME=$home "$codex" app-server generate-json-schema --out "$home/schema" >/dev/null 2>&1 ||
  fail "codex app-server generate-json-schema failed"
[ -f "$home/schema/ClientRequest.json" ] || fail "the app-server schema has no ClientRequest.json"
for method in initialize thread/start thread/resume turn/start turn/interrupt thread/compact/start account/rateLimits/read; do
  grep -qF "\"$method\"" "$home/schema/ClientRequest.json" || fail "the app-server no longer accepts $method (codex-supervisor sends it)"
done
ok "app-server methods codex-supervisor uses"

binary=$(readlink -f "$(command -v "$codex")")
# The npm entry point is a JS shim; the native binary is in a platform
# package, nested under it (global install) or beside it (hoisted install).
pkg=$(dirname "$binary")/..
native=$(find "$pkg" "$pkg/.." -path '*/vendor/*' -type f -name codex -size +1M 2>/dev/null | head -n 1)
[ -n "$native" ] || fail "cannot find the native codex binary beside $binary"
for token in PreToolUse UserPromptSubmit SessionStart stop_hook_active last_assistant_message; do
  grep -aqF "$token" "$native" || fail "the binary no longer mentions $token (a hook event or field vibe relies on)"
done
ok "hook events and Stop-hook fields"

echo "codex-compat-check: Codex $version is compatible with vibe's policy"
