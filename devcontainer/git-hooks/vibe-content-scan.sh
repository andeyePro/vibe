#!/usr/bin/env bash
# vibe-content-scan.sh — task_019 regrettable-content guard.
#
# Self-contained POSIX/bash + grep ERE scanner for secrets (BLOCK tier) and
# lower-precision PII (WARN tier). No network, no gitleaks/trufflehog.
#
# Invocation:
#   vibe-content-scan.sh --staged
#   vibe-content-scan.sh --message <file>
#   vibe-content-scan.sh --range <a> <b>
#   vibe-content-scan.sh --blob-stdin [--tier block]
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
# See .vs/spec.md (task_019) for the full pinned contract this implements,
# and devcontainer/claude-md/content-guard.md for the in-session summary.

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
# in $ALLOWLIST_FILE (comments/blanks ignored, case-sensitive).
line_is_allowlisted() {
  local content="$1"
  [ -f "$ALLOWLIST_FILE" ] || return 1
  local pattern
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    case "$pattern" in
      ""|\#*) continue ;;
    esac
    if printf '%s' "$content" | grep -qE -- "$pattern" 2>/dev/null; then
      return 0
    fi
  done < "$ALLOWLIST_FILE"
  return 1
}

# record_rule <rule> — append to FOUND_RULES if not already present.
record_rule() {
  local rule="$1" r
  for r in "${FOUND_RULES[@]}"; do
    [ "$r" = "$rule" ] && return 0
  done
  FOUND_RULES+=("$rule")
  return 0
}

# check_rule <class> <rule> <ere-pattern> <icase:0|1> <content> <location>
# Emits a finding line to stderr (unless allowlisted) and marks FOUND=1.
check_rule() {
  local class="$1" rule="$2" pattern="$3" icase="$4" content="$5" location="$6"
  local m
  if [ "$icase" = "1" ]; then
    m=$(printf '%s' "$content" | grep -oiE -- "$pattern" 2>/dev/null | head -n1) || true
  else
    m=$(printf '%s' "$content" | grep -oE -- "$pattern" 2>/dev/null | head -n1) || true
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
  printf '%s' "$1" | grep -qiE '^(Co-authored-by|Signed-off-by):[[:space:]]'
}

# is_trailer_line <content> — a generic git-trailer-shaped line
# (^[A-Z][A-Za-z-]+:\s). Built-in allowlist (b): suppresses email/IP
# findings specifically (not BLOCK findings) on lines shaped like this.
is_trailer_line() {
  printf '%s' "$1" | grep -qE '^[A-Za-z][A-Za-z-]+:[[:space:]]'
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
  local m
  m=$(printf '%s' "$content" | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' 2>/dev/null | head -n1) || true
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
  local m user
  m=$(printf '%s' "$content" | grep -oE '/(Users|home)/[^/ ]+/' 2>/dev/null | head -n1) || true
  [ -z "$m" ] && return 0
  user=$(printf '%s' "$m" | sed -E 's#^/(Users|home)/([^/]+)/#\2#')
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
    check_rule "WARN" "mdns-local" '[A-Za-z0-9-]+\.local\b' "0" "$content" "$location"
    check_email_rule "$content" "$location"
  fi
}

# ── Unified-diff parsing (shared by --staged and --range) ──────────────────
# scan_diff_stream <tier> — reads a `git diff -U0` stream on stdin, tracks
# current file + line number from the hunk headers, and scans every added
# (+) line. Deleted files (+++ /dev/null) are skipped (nothing added).
scan_diff_stream() {
  local tier="$1"
  local current_file="" current_line=0 skip_file=1
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
          scan_line "$content" "${current_file}:${current_line}" "$tier"
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
  *)
    echo "vibe-content-scan.sh: unknown mode '$MODE' (expected --staged|--message|--range|--blob-stdin)" >&2
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
