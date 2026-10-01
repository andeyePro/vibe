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
#   5. keeps every SQLite database under the requirements' sqlite_home pin,
#      even against -c and $CODEX_SQLITE_HOME decoys.
# A failed build makes the launcher fall back to the last Codex version that
# passed (vibe: build_base_image). Nothing here touches the network; it only
# runs the local binary, apart from `codex doctor`'s endpoint probes in the
# sqlite_home check (time-limited; they fail harmlessly offline).
#
# Usage: codex-compat-check [--codex <path>] [--config <config.toml>]
#   --config layers a policy file as the user config, so the smoke tests can
#   check the repo's policy against a container built from an older one.
set -uo pipefail
export PATH=/usr/local/share/npm-global/bin:/usr/local/bin:/usr/bin:/bin

codex=codex config=""
while [ $# -gt 0 ]; do
  case "$1" in
    --codex) codex=${2:-}; shift 2 || shift ;;
    --config) config=${2:-}; shift 2 || shift ;;
    *) printf 'codex-compat-check: unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
done
[ -n "$codex" ] || { echo "codex-compat-check: --codex needs a path" >&2; exit 2; }

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
if [ -n "$config" ]; then cp -- "$config" "$home/config.toml" || fail "cannot read $config"; fi

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
for method in initialize thread/start thread/resume thread/read turn/start turn/interrupt thread/compact/start account/rateLimits/read; do
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

# Behavioural, not just flags: what the model is actually offered under the
# managed policy must not include native sub-agents (the multi_agent pins
# alone never removed them; [agents] enabled = false does).
prompt=$(CODEX_HOME=$home "$codex" debug prompt-input "vibe compatibility probe" 2>/dev/null) ||
  fail "codex debug prompt-input failed; cannot see what the model is offered"
[ -n "$prompt" ] || fail "codex debug prompt-input printed nothing"
if printf '%s' "$prompt" | grep -qE 'spawn_agent|wait_agent'; then
  fail "the model is offered native sub-agents (spawn_agent) under the managed policy"
fi
ok "no native sub-agents offered to the model"

# Codex's SQLite databases must land on the container-only volume the
# requirements pin (sqlite_home), never in the Mac's shared ~/.codex, where the
# Mac's Codex app writes the same files and locking fails across Docker's VM
# boundary (2026-09-30). `codex doctor --json` resolves every database path
# without a login and creates none. It does probe OpenAI's endpoints (the one
# network touch in this script; they fail harmlessly offline), hence the
# timeout. The decoys are the strongest competitors a requirement has: a
# command-line `-c sqlite_home` (the top config layer) and $CODEX_SQLITE_HOME.
# Only an enforced EXACT requirement survives both — the system config.toml
# default alone would lose to `-c`, so this proves requirements.toml, not it.
req=${VIBE_CODEX_REQUIREMENTS:-/etc/codex/requirements.toml}
# Top-level key only (stop at the first [table]); "…" or '…' string.
want=$(awk '/^[[:space:]]*\[/ { exit }
  /^[[:space:]]*sqlite_home[[:space:]]*=/ {
    v = $0; sub(/^[^=]*=[[:space:]]*/, "", v)
    q = substr(v, 1, 1); if (q != "\"" && q != "'"'"'") exit
    v = substr(v, 2); sub(q ".*$", "", v); print v; exit
  }' "$req" 2>/dev/null)
[ -n "$want" ] || fail "$req does not pin sqlite_home; Codex would keep its databases in the shared ~/.codex"
doctor=$(CODEX_HOME=$home CODEX_SQLITE_HOME=$home/decoy-env timeout 60 "$codex" doctor --json \
  -c "sqlite_home=\"$home/decoy-cli\"" 2>/dev/null) # exits 1 without a login
verdict=$(printf '%s' "$doctor" | node -e '
  let s = ""; process.stdin.on("data", d => s += d).on("end", () => {
    let d; try { d = JSON.parse(s).checks["state.paths"].details; } catch { console.log("unreadable"); return; }
    if (!d || d["sqlite home"] === undefined) { console.log("unreadable"); return; }
    const want = process.argv[1], path = v => String(v).replace(/ \(.*\)$/, "");
    const dbs = Object.entries(d).filter(([k]) => / DB$/.test(k));
    if (path(d["sqlite home"]) !== want) { console.log("sqlite home is " + d["sqlite home"]); return; }
    // At least one database must be listed, or the stray check below proves
    // nothing; the stray check, not a fixed count, is what matters, so a
    // Codex that adds, drops or merges a database is not refused for it.
    if (dbs.length < 1) { console.log("no databases listed"); return; }
    const stray = dbs.filter(([, v]) => !path(v).startsWith(want + "/"));
    console.log(stray.length ? "outside " + want + ": " + stray.map(([k, v]) => k + " " + v).join(", ") : "ok " + dbs.length);
  });' "$want")
case "$verdict" in
  unreadable) fail "codex doctor --json gave no readable state.paths report (timed out, failed, or changed shape); cannot check the sqlite_home pin" ;;
  "ok "*) ok "all ${verdict#ok } Codex databases under $want (the requirement beats -c and \$CODEX_SQLITE_HOME decoys)" ;;
  *) fail "Codex databases are not pinned to $want: $verdict" ;;
esac

echo "codex-compat-check: Codex $version is compatible with vibe's policy"
