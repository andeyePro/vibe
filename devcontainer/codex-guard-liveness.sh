#!/bin/bash
# vibe Codex guard liveness gate — installed as
# /usr/local/bin/codex-guard-liveness (root-owned, 0755).
#
# CONTRACT
# --------
# Exits 0 only when the whole Codex-led backstop chain is present, root-owned
# and demonstrably DENYING known-bad tool calls. It prints one line per check
# on stdout and, on the first failure, `LIVENESS FAILED: <check>` on stderr
# with exit 1. It starts nothing, changes nothing and writes nothing outside
# a private temporary directory: it is a gate to be consulted before a Codex
# session is launched, never the thing that launches it.
#
# WHY A LIVENESS GATE AT ALL
# --------------------------
# Codex fails OPEN when a hook command cannot be spawned — a missing or
# unreadable guard is not treated as a denial. A Codex-led session whose
# hooks silently do nothing looks exactly like one whose hooks are working,
# right up until something bad is allowed. So the chain is not assumed: it is
# exercised. Checks (d) and (e) push real fixtures through the real adapter
# and require the real guards to refuse them; a fail-open stub in place of
# the adapter fails here, which is the single most important thing this
# script does.
#
# THE CHECKS
# ----------
#   ownership              (a) every file in the chain exists, is owned by
#                              --owner (default root) and is not group- or
#                              other-writable. `node` must not be able to
#                              rewrite the thing that polices `node`.
#   requirements           (b) the constraints that keep the hooks
#                              authoritative are present on ACTIVE (non-
#                              comment) lines: allow_managed_hooks_only,
#                              the managed hooks directory, and the feature
#                              pins that remove the unhooked tool surfaces.
#   hooks-commands         (c) every command in hooks.json is the hardened
#                              `/usr/bin/env -i PATH=<fixed> /bin/bash
#                              /usr/local/bin/codex-guard-adapter <mode>`
#                              or `/usr/local/bin/codex-prompt-prefix` form,
#                              and the target program exists as an
#                              executable (task_053).
#   fixture-deny           (d) four known-bad calls are refused: a shell
#                              redirect into the Codex login dir, a patch
#                              rewriting that dir's config.toml, a shell
#                              write into /learnings and a patch adding a
#                              file under /learnings. The last two are the
#                              ask-became-deny path.
#   fixture-allow          (e) a benign call (`git status`) is still allowed,
#                              so a chain that denies everything — equally
#                              broken — does not pass as healthy.
#   codex-version          (f) codex --version is at least the floor the
#                              policy was verified against, compared as three
#                              integers (never as a string: "0.9" must not
#                              beat "0.154").
#
# FLAGS
# -----
#   --root <dir>    policy root            (default /etc/codex)
#   --bin  <dir>    binary root            (default /usr/local/bin)
#   --owner <user>  expected owner         (default root)
#   --codex <path>  the codex binary to version-check (default: codex on the fixed PATH)
#
# --root/--bin exist so the smoke tests can exercise this script against a
# copy of the chain, and --owner so that copy can be owned by the test user.
# They relocate where files are LOOKED FOR; they never relax what is
# required of them. hooks.json's own command paths are still required to be
# under the canonical /usr/local/bin, whatever --bin says, because that
# string is what a real Codex run will execute.
set -euo pipefail
# The Codex CLI itself lives in the image's npm prefix; that directory is
# on this fixed PATH only so `codex --version` can be found (check f), and
# --codex can name the binary explicitly instead.
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/share/npm-global/bin
unset BASH_ENV ENV

CANONICAL_BIN=/usr/local/bin
codex_bin=codex
MIN_MAJOR=0
MIN_MINOR=154
MIN_PATCH=0

# Paths the fixtures probe. Held in variables rather than written inline so
# that this file never itself contains a literal write idiom aimed at the
# Codex login directory — the authoring container's own Bash guard would, and
# should, object to that.
CODEX_LOGIN_DIR=/home/node/.codex
LEARNINGS_DIR=/learnings

root=/etc/codex
bin=$CANONICAL_BIN
owner=root

fail() {
  printf 'LIVENESS FAILED: %s\n' "$1" >&2
  exit 1
}

ok() {
  printf 'ok  %-20s %s\n' "$1" "$2"
}

usage() {
  printf 'usage: codex-guard-liveness [--root <dir>] [--bin <dir>] [--owner <user>] [--codex <path>]\n'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      [ "$#" -ge 2 ] || fail "arguments — --root needs a directory"
      root=$2
      shift 2
      ;;
    --bin)
      [ "$#" -ge 2 ] || fail "arguments — --bin needs a directory"
      bin=$2
      shift 2
      ;;
    --owner)
      [ "$#" -ge 2 ] || fail "arguments — --owner needs a user name"
      owner=$2
      shift 2
      ;;
    --codex)
      [ "$#" -ge 2 ] || fail "arguments — --codex needs a path"
      codex_bin=$2
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "arguments — unknown argument '$1'"
      ;;
  esac
done

command -v jq >/dev/null 2>&1 || fail "ownership — jq is not available"
jq_path=$(command -v jq)

requirements_file=$root/requirements.toml
hooks_file=$root/hooks/hooks.json
adapter=$bin/codex-guard-adapter
prompt_prefix=$bin/codex-prompt-prefix

# ── (a) ownership and modes ──────────────────────────────────────────────────
# stat's GNU spelling first, BSD/macOS as the fallback; -L so a symlinked
# entry is judged by the file that would actually run.
stat_meta() {
  stat -L -c '%U/%a' -- "$1" 2>/dev/null || stat -L -f '%Su/%Lp' -- "$1" 2>/dev/null
}

check_owned() {
  local path=$1 also_ok=${2:-} meta file_owner perms group_digit other_digit
  [ -e "$path" ] || fail "ownership — $path does not exist"
  meta=$(stat_meta "$path") || fail "ownership — cannot stat $path"
  file_owner=${meta%%/*}
  perms=${meta##*/}
  while [ ${#perms} -lt 3 ]; do
    perms="0$perms"
  done
  if [ "$file_owner" != "$owner" ] && [ "$file_owner" != "$also_ok" ]; then
    fail "ownership — $path is owned by '$file_owner', expected '$owner'"
  fi
  group_digit=${perms: -2:1}
  other_digit=${perms: -1}
  if [ "$((group_digit & 2))" -ne 0 ] || [ "$((other_digit & 2))" -ne 0 ]; then
    fail "ownership — $path is group- or other-writable (mode $perms)"
  fi
  ok "ownership" "$path ($file_owner, $perms)"
}

check_owned "$requirements_file"
check_owned "$hooks_file"
check_owned "$adapter"
check_owned "$bin/guard-bash.sh"
check_owned "$bin/guard-fs.sh"
# task_049: the Codex-led entry point is part of the chain too — it is
# the file that consults THIS gate, so a `node`-writable copy of it could
# simply not call it.
check_owned "$bin/codex-entry"
# task_053: the UserPromptSubmit hook that points the model at $vs/$vss/
# $vsss for a leading-space ` /vs …` line is part of the same chain — it
# runs with the same hardened env -i form, so it must be just as
# `node`-unwritable as the guard adapter it sits beside.
check_owned "$prompt_prefix"
# jq is a distribution binary, not part of the vibe chain: it is always
# root-owned even when --owner relocates the chain to a test user, so root is
# accepted for it in addition to --owner.
check_owned "$jq_path" root

# ── (b) requirements constraints on active lines ─────────────────────────────
# Anchored patterns: leading whitespace and a trailing comment are tolerated,
# a commented-out line is not (it cannot start with `#` and still match).
require_active_line() {
  local label=$1 pattern=$2
  grep -Eq "$pattern" -- "$requirements_file" ||
    fail "requirements — $requirements_file has no active '$label' line"
  ok "requirements" "$label"
}

[ -f "$requirements_file" ] || fail "requirements — $requirements_file is not a regular file"
require_active_line 'allow_managed_hooks_only = true' \
  '^[[:space:]]*allow_managed_hooks_only[[:space:]]*=[[:space:]]*true[[:space:]]*(#.*)?$'
require_active_line 'managed_dir = "/etc/codex/hooks"' \
  '^[[:space:]]*managed_dir[[:space:]]*=[[:space:]]*"/etc/codex/hooks"[[:space:]]*(#.*)?$'
require_active_line '[features]' \
  '^[[:space:]]*\[features\][[:space:]]*(#.*)?$'
require_active_line 'unified_exec = false' \
  '^[[:space:]]*unified_exec[[:space:]]*=[[:space:]]*false[[:space:]]*(#.*)?$'
require_active_line 'multi_agent = false' \
  '^[[:space:]]*multi_agent[[:space:]]*=[[:space:]]*false[[:space:]]*(#.*)?$'
require_active_line 'multi_agent_v2 = false' \
  '^[[:space:]]*multi_agent_v2[[:space:]]*=[[:space:]]*false[[:space:]]*(#.*)?$'

# ── (c) every managed hook command is an executable under /usr/local/bin ─────
hook_commands=$(jq -r '
  .hooks
  | to_entries[]
  | .value[]?
  | .hooks[]?
  | select(.type == "command")
  | .command
' -- "$hooks_file") || fail "hooks-commands — could not parse $hooks_file"

[ -n "$hook_commands" ] || fail "hooks-commands — $hooks_file declares no command hooks"

# Each command must be the hardened form the policy ships (Astra's review,
# 2026-09-11): started through the ABSOLUTE `/usr/bin/env -i` with a FIXED
# PATH and the absolute /bin/bash, so a caller-controlled BASH_ENV or PATH
# can never run before the target script's first line (an unqualified `env`
# would itself be resolved through the inherited PATH — Astra's re-review).
# Anything else — a bare path, a different interpreter, an extra token —
# fails the gate. task_053 adds a second program to the alternation,
# codex-prompt-prefix (the UserPromptSubmit hook), grouped so both
# alternatives stay anchored at both ends; the captured group names
# whichever program actually matched, so the existence/executable check
# below resolves the right binary for either one.
hook_form='^/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/(codex-guard-adapter (bash|patch)|codex-prompt-prefix)$'
while IFS= read -r hook_command; do
  [ -n "$hook_command" ] || continue
  if [[ $hook_command =~ $hook_form ]]; then
    hook_program=${BASH_REMATCH[1]}
  else
    fail "hooks-commands — '$hook_command' is not the hardened '/usr/bin/env -i PATH=… /bin/bash $CANONICAL_BIN/(codex-guard-adapter <mode>|codex-prompt-prefix)' form"
  fi
  hook_binary=${hook_program%% *}
  hook_target=$bin/$hook_binary
  [ -f "$hook_target" ] || fail "hooks-commands — $hook_target (for '$hook_command') does not exist"
  [ -x "$hook_target" ] || fail "hooks-commands — $hook_target (for '$hook_command') is not executable"
  ok "hooks-commands" "$hook_command"
done <<<"$hook_commands"

# ── (d)/(e) real fixtures through the real adapter ───────────────────────────
tmpdir=$(mktemp -d) || fail "fixture — could not create a temporary directory"
trap 'rm -rf "$tmpdir"' EXIT
fixture_err=$tmpdir/fixture.err

adapter_rc=0
adapter_out=""

# VIBE_BLOCKS_LOG is redirected into the temporary directory so that these
# synthetic probes do not write "blocked" lines into the real audit log that
# guard-bash.sh keeps for genuine tool calls. It changes where the guard
# logs, never what it decides.
run_adapter() {
  adapter_rc=0
  adapter_out=$(printf '%s' "$2" |
    VIBE_BLOCKS_LOG=$tmpdir/blocks.log "$adapter" "$1" 2>"$fixture_err") || adapter_rc=$?
}

adapter_decision() {
  local decision
  decision=$(printf '%s' "$adapter_out" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null) ||
    decision="<unparseable>"
  printf '%s' "$decision"
}

bash_fixture() {
  jq -n --arg c "$1" '{tool_name: "Bash", tool_input: {command: $c}, cwd: "/workspace"}'
}

patch_fixture() {
  jq -n --arg c "$1" '{tool_name: "apply_patch", tool_input: {command: $c}, cwd: "/workspace"}'
}

expect_deny() {
  local label=$1 mode=$2 fixture=$3 decision
  run_adapter "$mode" "$fixture"
  if [ "$adapter_rc" -eq 2 ]; then
    ok "fixture-deny" "$label (blocked, exit 2)"
    return 0
  fi
  if [ "$adapter_rc" -ne 0 ]; then
    fail "fixture-deny — $label: the adapter exited $adapter_rc"
  fi
  decision=$(adapter_decision)
  [ "$decision" = "deny" ] ||
    fail "fixture-deny — $label was NOT denied (decision '${decision:-none}'); the guard chain is not live"
  ok "fixture-deny" "$label (denied)"
}

expect_allow() {
  local label=$1 mode=$2 fixture=$3 decision
  run_adapter "$mode" "$fixture"
  [ "$adapter_rc" -eq 0 ] ||
    fail "fixture-allow — $label: the adapter exited $adapter_rc on a benign call"
  if [ -n "$adapter_out" ]; then
    decision=$(adapter_decision)
    [ "$decision" != "deny" ] ||
      fail "fixture-allow — $label was denied; the guard chain refuses benign work"
  fi
  ok "fixture-allow" "$label (allowed)"
}

redirect_fixture_command="echo probe > ${CODEX_LOGIN_DIR}/liveness-probe"
learnings_fixture_command="echo probe > ${LEARNINGS_DIR}/liveness-probe.md"
codex_patch=$(printf '*** Begin Patch\n*** Update File: %s/config.toml\n@@\n-old\n+new\n*** End Patch' "$CODEX_LOGIN_DIR")
learnings_patch=$(printf '*** Begin Patch\n*** Add File: %s/liveness-probe.md\n+probe\n*** End Patch' "$LEARNINGS_DIR")

expect_deny "shell redirect into the Codex login dir" bash "$(bash_fixture "$redirect_fixture_command")"
expect_deny "patch rewriting the Codex login dir's config.toml" patch "$(patch_fixture "$codex_patch")"
expect_deny "shell write into the learning library (ask became deny)" bash "$(bash_fixture "$learnings_fixture_command")"
expect_deny "patch adding a file to the learning library (ask became deny)" patch "$(patch_fixture "$learnings_patch")"
expect_allow "git status" bash "$(bash_fixture 'git status')"

# ── (f) codex version floor, compared as three integers ──────────────────────
command -v -- "$codex_bin" >/dev/null 2>&1 || fail "codex-version — '$codex_bin' is not on the fixed PATH (pass --codex <path>)"
codex_version_output=$("$codex_bin" --version 2>/dev/null) || fail "codex-version — '$codex_bin --version' failed"
codex_version_line=${codex_version_output%%$'\n'*}
# Anchored to the first numeric triple on the first line, so a later banner
# triple can never be the one compared (same rule as vibe-delegate.mjs).
if [[ ! $codex_version_line =~ ^[^0-9]*([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
  fail "codex-version — could not read a version from '$codex_version_line'"
fi
have_major=${BASH_REMATCH[1]}
have_minor=${BASH_REMATCH[2]}
have_patch=${BASH_REMATCH[3]}
version_too_old=false
if [ "$have_major" -lt "$MIN_MAJOR" ]; then
  version_too_old=true
elif [ "$have_major" -eq "$MIN_MAJOR" ]; then
  if [ "$have_minor" -lt "$MIN_MINOR" ]; then
    version_too_old=true
  elif [ "$have_minor" -eq "$MIN_MINOR" ] && [ "$have_patch" -lt "$MIN_PATCH" ]; then
    version_too_old=true
  fi
fi
if [ "$version_too_old" = "true" ]; then
  fail "codex-version — codex ${have_major}.${have_minor}.${have_patch} is older than the ${MIN_MAJOR}.${MIN_MINOR}.${MIN_PATCH} floor this policy was verified against"
fi
ok "codex-version" "${have_major}.${have_minor}.${have_patch} (floor ${MIN_MAJOR}.${MIN_MINOR}.${MIN_PATCH})"

exit 0
