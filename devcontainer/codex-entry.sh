#!/bin/bash
# vibe Codex-led session entry point — installed as
# /usr/local/bin/codex-entry (root-owned, 0755) and reached ONLY through the
# launcher's `vibe --agent codex` path: the launcher runs `devcontainer exec`
# with `/bin/bash --noprofile --norc`, whose command string is one `exec env`
# of this script with a fixed environment (SHELL=/bin/bash, LC_ALL and LANG
# C.UTF-8, CODEX_HOME=/home/node/.codex) and nothing else.
#
# CONTRACT
# --------
# Prove the backstop chain, then get out of the way. This script starts a
# Codex session if and only if `codex-guard-liveness` has just exited 0 in
# this container, right now — and it starts nothing at all otherwise. On any
# refusal it prints ONE line beginning `codex-led session refused:` on stderr
# and exits 1; the liveness gate's own output is passed through unchanged
# first, so the operator sees which check failed rather than a summary of it.
#
# WHY A SEPARATE SCRIPT, ROOT-OWNED
# ---------------------------------
# The gate is worthless if the thing that consults it can be edited by the
# session it gates. The launcher cannot run the gate itself (it is host-side,
# outside the container), and a shell one-liner inside `devcontainer exec`
# would put the policy decision in a string the session could never verify.
# So the decision lives in a root-owned file next to the task_046 chain, and
# `codex-guard-liveness` check (a) asserts the ownership and mode of THIS
# file too: `node` cannot rewrite the thing that decides whether `node` gets
# a Codex session.
#
# WHAT IT DELIBERATELY DOES NOT DO
# --------------------------------
# It passes NO model, approval or sandbox flag, and no config override, to
# the Codex CLI. Every one of those is owned by the root-owned system policy
# at /etc/codex (requirements.toml clamps whatever a user or project config
# asks for), and a flag here would be a second, unauditable source of truth —
# in particular the approvals-and-sandbox bypass flag, which must never be
# spelled anywhere in this image outside the supervisor's own documented
# app-server call. It never reads, writes or creates anything in the Codex
# login directory beyond testing that the mount is there.
#
# FLAGS
# -----
#   --root <dir>       policy root                 (default /etc/codex)
#   --bin  <dir>       binary root                 (default /usr/local/bin)
#   --login-dir <dir>  Codex login mount           (default /home/node/.codex)
#   --codex <path>     the codex binary to start   (default: codex on the fixed PATH)
#   --                 everything after this is passed to codex unchanged
#
# As in codex-guard-liveness, the flags exist ONLY so the offline tests can
# point the script at a copy of the chain. They relocate what is looked for;
# they never relax what is required of it, and there is no flag that skips
# the gate.
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/share/npm-global/bin
unset BASH_ENV ENV

root=/etc/codex
bin=/usr/local/bin
login_dir=/home/node/.codex
codex_bin=codex
codex_bin_given=0

refuse() {
  printf 'codex-led session refused: %s\n' "$1" >&2
  exit 1
}

usage() {
  printf 'usage: codex-entry [--root <dir>] [--bin <dir>] [--login-dir <dir>] [--codex <path>] [-- <codex args>]\n'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      [ "$#" -ge 2 ] || refuse "--root needs a directory"
      root=$2
      shift 2
      ;;
    --bin)
      [ "$#" -ge 2 ] || refuse "--bin needs a directory"
      bin=$2
      shift 2
      ;;
    --login-dir)
      [ "$#" -ge 2 ] || refuse "--login-dir needs a directory"
      login_dir=$2
      shift 2
      ;;
    --codex)
      [ "$#" -ge 2 ] || refuse "--codex needs a path"
      codex_bin=$2
      codex_bin_given=1
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      refuse "unknown argument '$1'"
      ;;
  esac
done

# (a) the policy must be installed. A missing requirements.toml means the
# image was built without the task_046 layer (or someone moved it), and every
# constraint that makes the managed hooks authoritative is absent with it.
[ -f "$root/requirements.toml" ] ||
  refuse "$root/requirements.toml is missing — the root-owned Codex policy is not installed in this image"

# (a) the login mount must be there. Codex without its ChatGPT login cannot
# do anything useful, and a session that starts anyway would look identical
# to a working one until the first request fails. Tested with -d and nothing
# else: this script never looks inside that directory.
[ -d "$login_dir" ] ||
  refuse "$login_dir is not a directory — the Codex login mount is not present (run 'vibe codex allow' on the Mac and relaunch)"

liveness=$bin/codex-guard-liveness
[ -x "$liveness" ] ||
  refuse "$liveness is missing or not executable — the guard chain cannot be proven"

# Astra's review (2026-09-11): `--bin` selects the executable trusted to
# prove liveness, so it must be AUTHENTICATED before it is believed. The
# rule: the gate must be owned by the same user that owns THIS script (root
# for the installed copy; the test user for a fixture copy of the chain) and
# must not be group- or other-writable. A `--bin` pointing at a writable
# directory holding a `codex-guard-liveness` that exits 0 therefore fails
# here, before anything runs — the override relocates where the gate is
# looked for, never who is allowed to have written it.
stat_owner_mode() {
  stat -L --format='%U/%a' -- "$1" 2>/dev/null || stat -L -f '%Su/%Lp' -- "$1" 2>/dev/null
}
self_path=$0
if command -v realpath >/dev/null 2>&1; then
  self_path=$(realpath -- "$0" 2>/dev/null || printf '%s' "$0")
fi
# Astra's re-review: ownership and mode do not authenticate IDENTITY — a
# symlink to /usr/bin/true is root-owned 0755 and "passes". So the gate must
# be a REGULAR file (never a symlink) that lives in the SAME directory as
# this script's own real path: `--bin` may only name that directory. The
# installed entry point lives in /usr/local/bin, so the only gate it will
# ever run is /usr/local/bin/codex-guard-liveness; a fixture copy of the
# chain runs the copy of this script placed beside its own stub gate.
[ ! -L "$liveness" ] ||
  refuse "$liveness is a symlink — the gate must be a regular file, never a link to something else"
[ -f "$liveness" ] ||
  refuse "$liveness is not a regular file"
self_dir=$(dirname -- "$self_path")
gate_dir=$(cd -- "$(dirname -- "$liveness")" 2>/dev/null && pwd -P) ||
  refuse "cannot resolve the directory of $liveness"
[ "$gate_dir" = "$self_dir" ] ||
  refuse "$liveness is not beside this entry point ($self_dir) — --bin may only name the directory the entry point itself lives in"
self_meta=$(stat_owner_mode "$self_path") || refuse "cannot stat $self_path"
gate_meta=$(stat_owner_mode "$liveness") || refuse "cannot stat $liveness"
self_owner=${self_meta%%/*}
gate_owner=${gate_meta%%/*}
gate_perms=${gate_meta##*/}
while [ ${#gate_perms} -lt 3 ]; do gate_perms="0$gate_perms"; done
[ "$gate_owner" = "$self_owner" ] ||
  refuse "$liveness is owned by '$gate_owner', not by '$self_owner' who owns this entry point — an unauthenticated gate proves nothing"
if [ "$(( ${gate_perms: -2:1} & 2 ))" -ne 0 ] || [ "$(( ${gate_perms: -1} & 2 ))" -ne 0 ]; then
  refuse "$liveness is group- or other-writable (mode $gate_perms) — an editable gate proves nothing"
fi

# (a) the gate itself. Its stdout (one `ok` line per check) and its stderr
# (`LIVENESS FAILED: <check>`) are passed through UNCHANGED, so the reason a
# session was refused survives to the terminal; only then is the one-line
# refusal added. Codex fails OPEN on a hook it cannot spawn, which is exactly
# why this is proven before the session rather than assumed during it.
liveness_args=(--root "$root" --bin "$bin")
if [ "$codex_bin_given" = "1" ]; then
  liveness_args+=(--codex "$codex_bin")
fi
if ! "$liveness" "${liveness_args[@]}"; then
  refuse "the guard chain did not prove itself"
fi

# (b) proven: hand over to the unmodified vendor binary, in the cwd
# `devcontainer exec` put us in (the workspace), with only the arguments the
# caller passed after `--`.
printf 'codex-led session: guard chain proven, starting codex\n'
exec "$codex_bin" "$@"
