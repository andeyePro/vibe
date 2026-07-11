#!/bin/bash
# Git credential helper — per-repo token router (task_017 shared-repos, C4).
#
# Invoked by git for every credential `get` (push/pull/fetch). Reads the git
# credential key=value protocol on stdin and writes username/password on stdout.
# It serves a DIFFERENT single-repo PAT depending on WHICH repo git is asking
# about, and — critically — NEVER serves the project token ($GITHUB_TOKEN) for
# any repo other than the project's own. That "never-widen" guarantee is the
# whole point of the slice: a container's blast radius is exactly the repos it
# declares in its launch header, each reached via its own single-repo token.
#
# Routing (https + github.com only; any other host is a silent no-op so git
# falls through to the next helper / fails):
#   path == $GITHUB_REPO_SLUG            -> serve $GITHUB_TOKEN   (the project)
#   path == a configured shared slug     -> serve VIBE_SHARED_TOKEN_<SANITISED>
#   path == anything else                -> serve NOTHING (git fails loud)
#   no path at all (useHttpPath off/old) -> serve $GITHUB_TOKEN ONLY when NO
#                                           shared repos are configured (compat);
#                                           otherwise NOTHING (fail closed — a
#                                           mis-set useHttpPath must not widen).
#
# Inputs are ENV ($GITHUB_TOKEN, $GITHUB_REPO_SLUG, VIBE_SHARED_TOKEN_*) plus
# stdin; the only output is stdout. Deliberately a pure filter so it is trivially
# unit-attackable. Dependency-free beyond bash + tr (coreutils; always present).
set -e

# Only respond to "get". git also sends "store"/"erase" — ignore (no storage).
if [ "${1:-}" != "get" ]; then
  exit 0
fi

# ── Emit-and-exit helper ─────────────────────────────────────────────────────
# serve <token>: emit the credential answer, then exit. Refuses to emit an EMPTY
# password — an unset/empty token must never look like a successful auth, and
# must never fall through to a wider token.
serve() {
  local tok="$1"
  if [ -n "$tok" ]; then
    echo "username=x-access-token"
    echo "password=$tok"
  fi
  exit 0
}

# _sanitise_slug <slug>: uppercase, then every non-alphanumeric byte -> `_`.
# MUST stay byte-identical to the launcher-side `shared_repo_env_name`
# (task_017 AC2) so a slug maps to the SAME VIBE_SHARED_TOKEN_* name on both
# sides. LC_ALL=C keeps tr's ranges byte-stable; printf '%s' avoids a trailing
# newline that would otherwise become a trailing `_`.
_sanitise_slug() {
  LC_ALL=C printf '%s' "$1" \
    | LC_ALL=C tr '[:lower:]' '[:upper:]' \
    | LC_ALL=C tr -c 'A-Z0-9' '_'
}

# _any_shared_tokens: return 0 iff at least one VIBE_SHARED_TOKEN_* var is set
# (even if EMPTY — a declared-but-tokenless shared repo still counts as
# "configured", which forces the no-path branch to fail closed rather than
# widen to $GITHUB_TOKEN).
_any_shared_tokens() {
  set -- "${!VIBE_SHARED_TOKEN_@}"
  [ "$#" -gt 0 ]
}

# ── Parse key=value input from stdin ─────────────────────────────────────────
# git sends one `key=value` per line, terminated by a blank line. Values never
# contain newlines (the protocol is strictly line-oriented), so an injected
# newline in a remote URL cannot smuggle a second field past git's own parser.
# We ALSO record whether a `path` key was present at all — distinct from
# present-but-empty — because the no-path compat branch turns on that.
declare -A cred
have_path=0
while IFS='=' read -r key value; do
  [ -z "$key" ] && break
  cred[$key]="$value"
  [ "$key" = "path" ] && have_path=1
done

# ── Host/protocol guard ──────────────────────────────────────────────────────
# Everything below is github.com over https only. Bail out (serving nothing) for
# any other host/protocol so a token can never leak off-platform.
if [ "${cred[protocol]:-}" != "https" ] || [ "${cred[host]:-}" != "github.com" ]; then
  exit 0
fi

# ── No-path case (useHttpPath off / pre-path git) ────────────────────────────
# Legacy single-repo behaviour is safe ONLY when this container declares no
# shared repos — then the sole token in play is the project's own single-repo
# PAT, so serving it is not a widen. If ANY shared repo is configured, refuse:
# a mis-set useHttpPath must fail loud, never silently hand $GITHUB_TOKEN to a
# pathless request that might actually be for a shared repo.
if [ "$have_path" -eq 0 ]; then
  if _any_shared_tokens; then
    exit 0                       # never-widen: shared repos present, no path -> nothing
  fi
  serve "${GITHUB_TOKEN:-}"      # compat: single-repo project, legacy pathless git
fi

# ── Normalise the requested path to owner/repo ───────────────────────────────
raw="${cred[path]:-}"

# Reject traversal outright (e.g. `owner/../other/repo`). `..` never appears in
# a real GitHub slug; failing closed here is the safe direction.
case "$raw" in
  *..*) exit 0 ;;                # never-widen: traversal -> nothing
esac
# Reject any control character (embedded NUL/CR/LF/injection bytes).
case "$raw" in
  *[[:cntrl:]]*) exit 0 ;;       # never-widen: control bytes -> nothing
esac

# Take the FIRST TWO slash-separated segments as owner/repo. With useHttpPath
# git can append subpaths (e.g. `owner/repo.git/info/refs`); those trailing
# segments are discarded. `|| true` keeps a herestring-EOF read status from
# tripping `set -e` (the assignments still happen before read returns).
IFS='/' read -r _owner _repo _rest <<< "$raw" || true
_repo="${_repo%.git}"           # strip a single trailing `.git` from the repo segment

# Validate BOTH segments against the pinned slug charset. Anything outside
# [A-Za-z0-9._-] (spaces, `;`, quotes, an empty segment from a leading/only
# slash, leftover injection) fails the match and serves nothing.
case "$_owner" in
  ''|*[!A-Za-z0-9._-]*) exit 0 ;;   # never-widen: bad/empty owner -> nothing
esac
case "$_repo" in
  ''|*[!A-Za-z0-9._-]*) exit 0 ;;   # never-widen: bad/empty repo -> nothing
esac
slug="$_owner/$_repo"

# ── Route ────────────────────────────────────────────────────────────────────
# (1) EXACT match against the project's own slug -> the project PAT. This is the
#     ONLY code path permitted to emit $GITHUB_TOKEN, and only on a case-
#     sensitive equality: a differently-cased or otherwise different repo can
#     never reach it.
if [ -n "${GITHUB_REPO_SLUG:-}" ] && [ "$slug" = "$GITHUB_REPO_SLUG" ]; then
  serve "${GITHUB_TOKEN:-}"     # never-widen anchor: project slug only
fi

# (2) Otherwise a configured shared repo -> ITS OWN scoped PAT, never the project
#     token. The env name is derived by the same sanitiser the launcher used to
#     export it; an unset/empty var means "not configured / no token staged" and
#     serve() declines the empty password (git then fails loud).
#     Sanitisation is LOSSY (foo-bar/baz and foo/bar-baz both -> FOO_BAR_BAZ),
#     so a matched env name is NOT proof the requested slug is the declared
#     one — re-verify against the launcher-exported VIBE_SHARED_SLUG_* twin
#     (the exact declared slug) and serve only on equality (security-review
#     C4 LOW: request-vs-config sanitisation collision).
_san="$(_sanitise_slug "$slug")"
_env="VIBE_SHARED_TOKEN_${_san}"
_slugvar="VIBE_SHARED_SLUG_${_san}"
if [ "${!_slugvar:-}" = "$slug" ]; then
  serve "${!_env:-}"            # never-widen: shared repo's OWN token, or nothing
fi
exit 0                          # never-widen: sanitisation collision or undeclared -> nothing

# (3) serve() always exits; reaching here means no token matched -> nothing.
exit 0
