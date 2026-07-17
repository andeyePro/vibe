#!/usr/bin/env bash
# vibe-content-scan.sh — task_019 regrettable-content guard.
#
# Self-contained POSIX/bash + grep ERE scanner for secrets (BLOCK tier) and
# lower-precision PII (WARN tier). No network, no gitleaks/trufflehog.
#
# Invocation:
#   vibe-content-scan.sh --staged
#   vibe-content-scan.sh --message <file>
#   vibe-content-scan.sh --messages-stdin
#   vibe-content-scan.sh --range <a> <b>
#   vibe-content-scan.sh --blob-stdin [--tier block]
#   vibe-content-scan.sh --identity [<email>]
#
# --messages-stdin reads NUL-delimited records on stdin, each record being a
# commit sha on the first line and the raw message body on the remaining lines
# (produced by `git log --all -z --format='%H%n%B'`). It scans every message
# line with the same both-tier + trailer-exemption semantics as --message, but
# emits the location as `commit <sha>` directly — one scanner process for the
# whole history instead of one per commit (task_022).
#
# Match primitives are bash-native `[[ =~ ]]` + BASH_REMATCH (task_022): no
# per-line subprocess forks on the hot path. Patterns stay POSIX ERE only
# (no word-boundary or other GNU escapes) so they compile under BSD regcomp
# (macOS bash 3.2) and glibc (container bash 5) alike.
#
# Output: one line per finding on STDERR, tab-separated:
#   <CLASS>\t<location>\t<rule>\t<snippet>
# CLASS is BLOCK or WARN. stdout is always empty.
#
# Exit codes: 0 = clean (or every finding suppressed/overridden); 1 = at
# least one un-suppressed finding. Never 2 (that is guard-bash.sh's
# PreToolUse protocol signal, deliberately not reused here).
#
# Overrides (both logged loudly, never silent):
#   VIBE_CONTENT_GUARD=off   — skip enforcement for this invocation
#   VIBE_ALLOW_COMMIT=1      — alias for the same
# Per-repo opt-out: a repo-root .vibe-content-guard-off marker file makes
# this script exit 0 immediately, before any scanning.
# Per-repo allowlist: a repo-root .vibe-content-allow file, one ERE regex
# per line (# comments / blank lines ignored, case-sensitive); a finding is
# suppressed iff its whole flagged line matches (grep -E) any entry.
#
# task_023: a line of the form `path-warn:<glob>` is a DIFFERENT entry kind
# — a bash case-style glob matched against the repo-relative file path
# (`*` crosses `/`), not an ERE. In `--staged`/`--range` only, a file whose
# path matches a path-warn glob is scanned at tier `block` for its added
# lines: WARN-class rules are skipped for that file, BLOCK rules always
# still fire (path never suppresses a secret). path-warn lines are
# structurally excluded from the ERE allowlist loop — neither the whole
# line nor the glob remainder is ever handed to grep -E as a content
# pattern (a glob like `smoke-test.py` used as an ERE would be a live
# literal-substring suppressor for ANY finding, including BLOCK, on any
# line merely mentioning the filename). Not applied in --message,
# --messages-stdin, --blob-stdin, or --identity — no file path exists
# there. See devcontainer/claude-md/content-guard.md for the full contract.
#
# See .vs/spec.md (task_019, task_023) for the full pinned contract this
# implements, and devcontainer/claude-md/content-guard.md for the
# in-session summary.

set -euo pipefail

# ── Repo root + per-repo opt-out ─────────────────────────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"

if [ -f "$REPO_ROOT/.vibe-content-guard-off" ]; then
  exit 0
fi

ALLOWLIST_FILE="$REPO_ROOT/.vibe-content-allow"

# ── Override detection (does not skip scanning — still reports what would
# have fired, then exits 0 with a loud stderr line naming the bypass). ──────
GUARD_OVERRIDE=0
if [ "${VIBE_CONTENT_GUARD:-}" = "off" ] || [ "${VIBE_ALLOW_COMMIT:-}" = "1" ]; then
  GUARD_OVERRIDE=1
fi

# ── Finding accumulators (global, mutated by scan_line/check_rule) ─────────
FOUND=0
declare -a FOUND_RULES=()

# line_is_allowlisted <content> — true iff the whole line matches any ERE
# in $ALLOWLIST_FILE (comments/blanks/path-warn: entries ignored,
# case-sensitive). path-warn: entries are a structurally different kind
# (task_023, see file header) and MUST NEVER reach grep -E here — this is
# what keeps a path glob from acting as a live literal-substring suppressor
# for arbitrary content (AC3b).
line_is_allowlisted() {
  local content="$1"
  [ -f "$ALLOWLIST_FILE" ] || return 1
  local pattern
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    case "$pattern" in
      ""|\#*|path-warn:*) continue ;;
    esac
    if printf '%s' "$content" | grep -qE -- "$pattern" 2>/dev/null; then
      return 0
    fi
  done < "$ALLOWLIST_FILE"
  return 1
}

# ── path-warn glob parsing (task_023) ───────────────────────────────────────
# Structurally separate from the ERE loop above — path-warn lines never
# reach grep -E in any form. Populated once (lazy, idempotent) and reused
# per-file by scan_diff_stream's per-FILE tier-demotion check.
PATH_WARN_GLOBS_LOADED=0
declare -a PATH_WARN_GLOBS=()

# load_path_warn_globs — parses $ALLOWLIST_FILE once, extracting the glob
# remainder of every path-warn:<glob> line (leading/trailing whitespace
# trimmed). An empty/whitespace-only glob is malformed and skipped — it
# matches nothing, never treated as match-all.
load_path_warn_globs() {
  [ "$PATH_WARN_GLOBS_LOADED" -eq 1 ] && return 0
  PATH_WARN_GLOBS_LOADED=1
  [ -f "$ALLOWLIST_FILE" ] || return 0
  local pattern glob
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    case "$pattern" in
      path-warn:*)
        glob="${pattern#path-warn:}"
        glob="${glob#"${glob%%[![:space:]]*}"}"
        glob="${glob%"${glob##*[![:space:]]}"}"
        [ -n "$glob" ] && PATH_WARN_GLOBS+=("$glob")
        ;;
      *) : ;;
    esac
  done < "$ALLOWLIST_FILE"
  return 0
}

# file_is_path_warn <repo-relative-path> — true iff the path matches any
# path-warn glob. Unquoted bash case-style pattern match (no external
# command, no fork): `*` crosses `/`, so `path-warn:.vs/*` matches a file
# nested arbitrarily deep under .vs/.
file_is_path_warn() {
  local path="$1" glob
  load_path_warn_globs
  # Length check BEFORE expanding: under bash 3.2 + set -u (macOS host),
  # "${arr[@]}" on an EMPTY array is an "unbound variable" fatal — only
  # bash 4.4 made it safe. ${#arr[@]} is safe everywhere.
  [ "${#PATH_WARN_GLOBS[@]}" -eq 0 ] && return 1
  for glob in "${PATH_WARN_GLOBS[@]}"; do
    # shellcheck disable=SC2254  # intentional glob match, not literal
    case "$path" in
      $glob) return 0 ;;
    esac
  done
  return 1
}

# record_rule <rule> — append to FOUND_RULES if not already present.
record_rule() {
  local rule="$1" r
  # Same bash 3.2 + set -u empty-array guard as file_is_path_warn: the
  # FIRST finding reaches this loop with FOUND_RULES still empty, which is
  # fatal on the macOS host shell (pre-4.4 "${arr[@]}" nounset gotcha).
  if [ "${#FOUND_RULES[@]}" -gt 0 ]; then
    for r in "${FOUND_RULES[@]}"; do
      [ "$r" = "$rule" ] && return 0
    done
  fi
  FOUND_RULES+=("$rule")
  return 0
}

# check_rule <class> <rule> <ere-pattern> <icase:0|1> <content> <location>
# Emits a finding line to stderr (unless allowlisted) and marks FOUND=1.
check_rule() {
  local class="$1" rule="$2" pattern="$3" icase="$4" content="$5" location="$6"
  local m=""
  # BASH_REMATCH[0] is the leftmost match — the same substring the old
  # first-match primitive returned. The && m= guard keeps the no-match test
  # (exit 1) off set -e (A2b); shopt -u nocasematch runs on EVERY path out of
  # the icase branch, since a leaked nocasematch would silently make later
  # case-sensitive rules case-insensitive.
  if [ "$icase" = "1" ]; then
    shopt -s nocasematch
    [[ $content =~ $pattern ]] && m="${BASH_REMATCH[0]}"
    shopt -u nocasematch
  else
    [[ $content =~ $pattern ]] && m="${BASH_REMATCH[0]}"
  fi
  [ -z "$m" ] && return 0

  if line_is_allowlisted "$content"; then
    return 0
  fi

  local snippet="${m:0:60}"
  printf '%s\t%s\t%s\t%s\n' "$class" "$location" "$rule" "$snippet" >&2
  FOUND=1
  record_rule "$rule"
}

# is_named_trailer <content> — Co-Authored-By: / Signed-off-by: lines are
# fully exempt from ALL rules (built-in allowlist (a)).
is_named_trailer() {
  local pat='^(Co-authored-by|Signed-off-by):[[:space:]]' rc=1
  shopt -s nocasematch
  [[ $1 =~ $pat ]] && rc=0
  shopt -u nocasematch
  return "$rc"
}

# is_trailer_line <content> — a generic git-trailer-shaped line
# (^[A-Z][A-Za-z-]+:\s). Built-in allowlist (b): suppresses email/IP
# findings specifically (not BLOCK findings) on lines shaped like this.
is_trailer_line() {
  local pat='^[A-Za-z][A-Za-z-]+:[[:space:]]'
  [[ $1 =~ $pat ]] && return 0
  return 1
}

# is_noreply_email <matched-address> — the literal exemptions in the
# built-in allowlist: noreply@anthropic.com and *@*.users.noreply.github.com.
is_noreply_email() {
  case "$1" in
    noreply@anthropic.com) return 0 ;;
    *@*.users.noreply.github.com) return 0 ;;
    *) return 1 ;;
  esac
}

# check_email_rule <content> <location> — WARN email rule with the
# noreply/trailer exemptions applied inline (can't be expressed as a single
# ERE, so it gets its own small function instead of going through check_rule).
check_email_rule() {
  local content="$1" location="$2"
  is_trailer_line "$content" && return 0
  local m="" pat='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
  [[ $content =~ $pat ]] && m="${BASH_REMATCH[0]}"
  [ -z "$m" ] && return 0
  is_noreply_email "$m" && return 0
  if line_is_allowlisted "$content"; then
    return 0
  fi
  local snippet="${m:0:60}"
  printf '%s\t%s\t%s\t%s\n' "WARN" "$location" "email-address" "$snippet" >&2
  FOUND=1
  record_rule "email-address"
}

# check_home_path_rule <content> <location> — WARN home-path rule, excluding
# the generic container users node/root.
check_home_path_rule() {
  local content="$1" location="$2"
  # Capture group 2 is the username (previously extracted by a subprocess);
  # group 0 is the full /Users|home/<user>/ snippet, byte-identical to the
  # old match.
  local m="" user="" pat='/(Users|home)/([^/ ]+)/'
  if [[ $content =~ $pat ]]; then
    m="${BASH_REMATCH[0]}"
    user="${BASH_REMATCH[2]}"
  fi
  [ -z "$m" ] && return 0
  case "$user" in
    node|root) return 0 ;;
  esac
  if line_is_allowlisted "$content"; then
    return 0
  fi
  local snippet="${m:0:60}"
  printf '%s\t%s\t%s\t%s\n' "WARN" "$location" "home-path" "$snippet" >&2
  FOUND=1
  record_rule "home-path"
}

# check_mdns_rule <content> <location> — WARN mdns-local rule. POSIX-ERE
# equivalent of the old word-boundary form (the boundary escape is a GNU
# extension, absent from POSIX regcomp): match up to `.local`, then require a
# non-word char ([^A-Za-z0-9_], the word set) or end-of-string. The reported
# snippet is taken from capture group 1, which stops at `.local` and excludes
# that boundary char — byte-identical to the old match. `foo.localhost` (word
# char `h` after `.local`) correctly does NOT match; `foo.local.` and a
# trailing `.local` at end-of-line do.
check_mdns_rule() {
  local content="$1" location="$2"
  local m="" pat='([A-Za-z0-9-]+\.local)([^A-Za-z0-9_]|$)'
  [[ $content =~ $pat ]] && m="${BASH_REMATCH[1]}"
  [ -z "$m" ] && return 0
  if line_is_allowlisted "$content"; then
    return 0
  fi
  local snippet="${m:0:60}"
  printf '%s\t%s\t%s\t%s\n' "WARN" "$location" "mdns-local" "$snippet" >&2
  FOUND=1
  record_rule "mdns-local"
}

# check_ip_rule <content> <location> — WARN rfc1918-ip rule, suppressed on
# trailer-shaped lines (built-in allowlist (b)).
check_ip_rule() {
  local content="$1" location="$2"
  is_trailer_line "$content" && return 0
  local pattern='(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|169\.254\.[0-9]{1,3}\.[0-9]{1,3})'
  check_rule "WARN" "rfc1918-ip" "$pattern" "0" "$content" "$location"
}

# scan_line <content> <location> <tier: both|block> — runs every applicable
# rule against one line of content.
scan_line() {
  local content="$1" location="$2" tier="$3"

  is_named_trailer "$content" && return 0

  # BLOCK tier — always scanned regardless of mode.
  check_rule "BLOCK" "github-pat" 'ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}' "0" "$content" "$location"
  check_rule "BLOCK" "openai-key" 'sk-[A-Za-z0-9-]{20,}' "0" "$content" "$location"
  check_rule "BLOCK" "aws-access-key" 'AKIA[0-9A-Z]{16}' "0" "$content" "$location"
  check_rule "BLOCK" "private-key" '-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----' "0" "$content" "$location"
  check_rule "BLOCK" "secret-assignment" '(secret|token|password|passwd|api[_-]?key|bearer)[A-Za-z0-9_]*[[:space:]]*[:=][[:space:]]*"?'"'"'?[A-Za-z0-9+/=_-]{16,}' "1" "$content" "$location"

  if [ "$tier" = "both" ]; then
    check_ip_rule "$content" "$location"
    check_home_path_rule "$content" "$location"
    check_mdns_rule "$content" "$location"
    check_email_rule "$content" "$location"
  fi
}

# ── Unified-diff parsing (shared by --staged and --range) ──────────────────
# scan_diff_stream <tier> — reads a `git diff -U0` stream on stdin, tracks
# current file + line number from the hunk headers, and scans every added
# (+) line. Deleted files (+++ /dev/null) are skipped (nothing added).
#
# task_023: at each `+++ b/<path>` header, current_file_tier is set to the
# mode's tier and then demoted to "block" if <path> matches a path-warn
# glob — a per-FILE, one-way floor (never raises tier above what the mode
# already requested; --range is already "block" so this is a no-op there,
# pinning AC3c). BLOCK rules run unconditionally inside scan_line
# regardless of tier, so this only ever suppresses WARN-class findings.
scan_diff_stream() {
  local tier="$1"
  local current_file="" current_line=0 skip_file=1 current_file_tier="$tier"
  local diffline
  while IFS= read -r diffline || [ -n "$diffline" ]; do
    case "$diffline" in
      "+++ "*)
        local f="${diffline#+++ }"
        if [ "$f" = "/dev/null" ]; then
          skip_file=1
          current_file=""
        else
          current_file="${f#b/}"
          skip_file=0
          current_file_tier="$tier"
          if file_is_path_warn "$current_file"; then
            current_file_tier="block"
          fi
        fi
        ;;
      "@@ "*)
        local hunk="${diffline#@@ }"
        hunk="${hunk%% @@*}"
        local plus="${hunk#*+}"
        current_line="${plus%%,*}"
        ;;
      +*)
        if [ "$skip_file" -eq 0 ] && [ -n "$current_file" ]; then
          local content="${diffline#+}"
          scan_line "$content" "${current_file}:${current_line}" "$current_file_tier"
          current_line=$((current_line + 1))
        fi
        ;;
      *) : ;;
    esac
  done
}

# ── blob-stdin: raw content on stdin, tracking `commit <sha>` headers ──────
scan_blob_stdin() {
  local tier="$1"
  local current_commit="stdin"
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      commit\ *)
        current_commit="commit ${line#commit }"
        # Trim any trailing " (something)" merge annotation down to the sha token.
        current_commit="commit $(printf '%s' "${current_commit#commit }" | awk '{print $1}')"
        ;;
      "+++ "*|"---"*|"@@ "*) : ;;  # header noise, not content
      +*)
        local content="${line#+}"
        scan_line "$content" "$current_commit" "$tier"
        ;;
      *) : ;;
    esac
  done
}

# scan_messages_stdin — reads NUL-delimited records on stdin, each record being
# a commit sha on the first line followed by the raw message body (produced by
# `git log --all -z --format='%H%n%B'`). Every body line is scanned with
# scan_line "…" "commit <sha>" both — same both-tier + trailer-exemption
# semantics as --message, but the location is attributed to the commit sha
# directly (no awk relabel). The NUL delimiter — not line-shape sniffing — is
# the record boundary, so a body line like `commit deadbeef` or `+foo` is
# scanned as ordinary content and never mistaken for a header (B3). An empty
# body, or a malformed record with no body/sha, is skipped without error.
scan_messages_stdin() {
  local record sha body line
  while IFS= read -r -d '' record || [ -n "$record" ]; do
    sha="${record%%$'\n'*}"
    [ -n "$sha" ] || continue          # malformed / empty record — skip
    [ "$sha" = "$record" ] && continue # sha-only record, empty body — skip
    body="${record#*$'\n'}"
    [ -n "$body" ] || continue
    # Here-string (builtin redirect, no fork/subshell): the while loop runs in
    # THIS shell so FOUND/FOUND_RULES survive. A body line equal to a heredoc
    # delimiter can't break it (here-strings have no delimiter).
    while IFS= read -r line || [ -n "$line" ]; do
      scan_line "$line" "commit $sha" "both"
    done <<< "$body"
  done
}

# is_exempt_identity <email> — commit identities that are fine to publish:
# GitHub noreply forms (ID-prefixed or bare-username), Anthropic's noreply,
# and vibe's own synthetic placeholder fallback.
is_exempt_identity() {
  case "$1" in
    *@users.noreply.github.com) return 0 ;;
    *@*.users.noreply.github.com) return 0 ;;
    noreply@anthropic.com) return 0 ;;
    noreply@github.com) return 0 ;;
    placeholder@vibe.local) return 0 ;;
    *) return 1 ;;
  esac
}

# check_identity <email> — WARN commit-identity finding unless the email is
# an exempt (noreply-class) form or allowlisted. A real email in author/
# committer metadata publishes to harvesters on every public push — the
# root cause of the 2026-07-17 cross-org exposure (setup-git.sh inherited
# the host's real user.email and nothing checked it).
check_identity() {
  local email="$1"
  [ -z "$email" ] && return 0   # unset identity: git itself will refuse the commit
  is_exempt_identity "$email" && return 0
  if line_is_allowlisted "$email"; then
    return 0
  fi
  printf '%s\t%s\t%s\t%s\n' "WARN" "identity" "commit-identity" "${email:0:60}" >&2
  echo "vibe-content-scan.sh: commit email '$email' is not a GitHub noreply address and will publish on every public push." >&2
  echo "  fix:   git config user.email '<ID>+<USER>@users.noreply.github.com'   (GitHub → Settings → Emails)" >&2
  echo "  keep:  echo '^${email}\$' >> .vibe-content-allow   (deliberate identity for this repo)" >&2
  FOUND=1
  record_rule "commit-identity"
}

# ── Mode dispatch ────────────────────────────────────────────────────────────
MODE="${1:-}"
[ "$#" -gt 0 ] && shift

case "$MODE" in
  --staged)
    # Process substitution, NOT a pipe: scan_diff_stream mutates global
    # FOUND/FOUND_RULES, which must survive in THIS shell, not a pipeline
    # subshell (`cmd | scan_diff_stream` would run the function in a
    # subshell and silently lose every finding).
    scan_diff_stream "both" < <(git diff --cached -U0 --no-color 2>/dev/null)
    ;;
  --message)
    MSG_FILE="${1:-}"
    if [ -z "$MSG_FILE" ] || [ ! -f "$MSG_FILE" ]; then
      echo "vibe-content-scan.sh --message: missing or unreadable message file '$MSG_FILE'" >&2
      exit 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
      scan_line "$line" "message" "both"
    done < "$MSG_FILE"
    ;;
  --messages-stdin)
    scan_messages_stdin
    ;;
  --range)
    A="${1:-}"; B="${2:-}"
    if [ -z "$A" ] || [ -z "$B" ]; then
      echo "vibe-content-scan.sh --range: needs two revisions" >&2
      exit 1
    fi
    scan_diff_stream "block" < <(git diff -U0 --no-color "$A" "$B" 2>/dev/null)
    ;;
  --blob-stdin)
    TIER="both"
    if [ "${1:-}" = "--tier" ] && [ "${2:-}" = "block" ]; then
      TIER="block"
    fi
    scan_blob_stdin "$TIER"
    ;;
  --identity)
    # With an argument: check that literal email (audit's per-identity path).
    # Without: check the effective commit identity, `git config user.email`.
    if [ "$#" -gt 0 ]; then
      check_identity "$1"
    else
      check_identity "$(git config user.email 2>/dev/null || true)"
    fi
    ;;
  *)
    echo "vibe-content-scan.sh: unknown mode '$MODE' (expected --staged|--message|--messages-stdin|--range|--blob-stdin|--identity)" >&2
    exit 1
    ;;
esac

# ── Decide exit code ─────────────────────────────────────────────────────────
if [ "$GUARD_OVERRIDE" -eq 1 ]; then
  if [ "$FOUND" -eq 1 ]; then
    rules_list="${FOUND_RULES[*]}"
    echo "vibe-content-scan.sh: OVERRIDE (VIBE_CONTENT_GUARD=off / VIBE_ALLOW_COMMIT=1) — skipped enforcement for: ${rules_list// /, }" >&2
  fi
  exit 0
fi

if [ "$FOUND" -eq 1 ]; then
  exit 1
fi
exit 0
