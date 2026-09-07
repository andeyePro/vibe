#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

# Fail CLOSED, never open. A network backstop must lock the box down if it
# cannot finish wiring the allowlist - the opposite of the historic bug where a
# single unresolvable domain hit `exit 1` BEFORE the DROP policy further down,
# leaving the container at the kernel default (OUTPUT ACCEPT = wide open). This
# trap guarantees that ANY non-zero exit, from any line, ends with egress
# DROP-by-default - only the DNS/SSH/loopback ACCEPT rules added at the top
# survive, which is deliberate (SSH stays open for recovery; no arbitrary
# internet). On a clean exit (rc=0) the body has already set DROP + the allow
# rules, so the handler is a harmless no-op.
fail_closed() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "init-firewall: exiting rc=$rc before completion - failing CLOSED (egress DROP, only DNS/SSH/loopback remain)"
    iptables -P INPUT DROP   || true
    iptables -P FORWARD DROP || true
    iptables -P OUTPUT DROP  || true
  fi
}

# --- helpers ------------------------------------------------------------
# Defined BEFORE the first side-effecting command (and before the trap is
# installed) so smoke-test.py can source this script with
# VIBE_FIREWALL_SOURCE_ONLY=1 and exercise them host-side, with no iptables,
# no Docker and no network. Mirrors `vibe`'s own VIBE_SOURCE_ONLY convention.

GH_META_URL="${GH_META_URL:-https://api.github.com/meta}"
GH_FETCH_ATTEMPTS="${GH_FETCH_ATTEMPTS:-6}"
GH_FETCH_BACKOFF="${GH_FETCH_BACKOFF:-2}"
# Last good /meta body. Lives in a ROOT-OWNED 0700 directory inside the
# persistent ~node/.claude volume (this script runs as root under sudo with
# env_reset, so $HOME/$CLAUDE_CONFIG_DIR are root's and unusable): it must
# survive container recreation — which is exactly when the fetch runs — yet an
# unprivileged in-container process must not be able to plant it, because a
# planted cache would become root-built firewall input. Read-side ownership and
# mode checks below make a substituted (node-owned) directory or file invisible.
# Why at all: the anonymous 60/h /meta limit for the Mac's public IP was
# exhausted by a day of container starts (2026-09-02) and every launch then
# failed closed with no egress; stale-but-genuine GitHub ranges beat that.
GH_META_CACHE="${GH_META_CACHE:-/home/node/.claude/vibe-firewall/gh-meta-cache.json}"
GH_META_CACHE_MAX_AGE="${GH_META_CACHE_MAX_AGE:-604800}"   # 7 days, seconds
# Token for the /meta fetch: authenticated requests get 5,000/h per token, the
# anonymous limit is 60/h per IP shared by every container on the machine.
# postStartCommand pipes $GITHUB_TOKEN on STDIN (sudo's env_reset drops env and
# argv is world-readable via /proc); manual/sourced runs may use $GITHUB_TOKEN.
# It is attached only to api.github.com (never to an overridden GH_META_URL)
# and only via a curl config on stdin — never argv, never a log line.
GH_META_TOKEN="${GITHUB_TOKEN:-}"
_gh_meta_token_from_stdin() {
    local tok=""
    if [ ! -t 0 ]; then
        IFS= read -r -t 2 tok 2>/dev/null || true
    fi
    if [ -n "$tok" ]; then GH_META_TOKEN="$tok"; fi
    return 0
}
# _gh_meta_open_dir <dir>: opens the cache directory ONCE in THIS shell and
# leaves the fd in GH_META_FD (not printed: a $(...) capture would open it in
# a subshell and close it again on return).
# All later checks and I/O go through /proc/self/fd/<fd>/..., so the
# directory that was validated is the directory that is used — an
# unprivileged owner of the PARENT (node owns ~/.claude) cannot rename the
# root-owned directory away and substitute a symlink between check and use.
# The directory must be a real directory owned by the uid running this
# script (root in production), mode 0700, and not a symlink.
GH_META_FD=""
_gh_meta_open_dir() {
    local dir="$1" fd
    GH_META_FD=""
    [ ! -L "$dir" ] && [ -d "$dir" ] || return 1
    exec {fd}<"$dir" || return 1
    # -L: stat the directory the fd refers to, not the /proc magic link itself
    # (which always reports the running uid and mode 500).
    if [ "$(stat -L -c %u "/proc/self/fd/$fd" 2>/dev/null)" = "$(id -u)" ] \
       && [ "$(stat -L -c %a "/proc/self/fd/$fd" 2>/dev/null)" = "700" ]; then
        GH_META_FD="$fd"
        return 0
    fi
    exec {fd}<&-
    return 1
}

# _gh_meta_cache_write <body>: best effort, never fails the boot. Creates the
# 0700 directory (no -p: its parent, the volume root, must already exist),
# then writes through mktemp INSIDE the opened directory handle and renames
# within it, so no path component can be swapped underneath root.
_gh_meta_cache_write() {
    local dir fd tmp base; dir=$(dirname "$GH_META_CACHE"); base=$(basename "$GH_META_CACHE")
    if [ ! -e "$dir" ] && [ ! -L "$dir" ]; then mkdir -m 0700 "$dir" 2>/dev/null || return 0; fi
    if ! _gh_meta_open_dir "$dir"; then
        echo "WARNING: GitHub meta cache directory $dir exists but is not a $(id -un)-owned 0700 directory - not caching" >&2
        return 0
    fi
    fd="$GH_META_FD"
    tmp=$(mktemp "/proc/self/fd/$fd/.gh-meta.XXXXXX" 2>/dev/null) || { exec {fd}<&-; return 0; }
    if printf '%s' "$1" > "$tmp" 2>/dev/null && chmod 0600 "$tmp" 2>/dev/null \
       && mv -f "$tmp" "/proc/self/fd/$fd/$base" 2>/dev/null; then
        :
    else
        rm -f "$tmp" 2>/dev/null || true
    fi
    exec {fd}<&-
    return 0
}

# _gh_meta_cache_read: prints the cached body iff the directory opens clean
# (above), the file inside that handle is a regular non-symlink owned by this
# uid with mode 0600, is younger than GH_META_CACHE_MAX_AGE, and — read ONCE
# into a variable so validated bytes are served bytes — carries .web/.api/.git
# whose every IPv4 entry passes _public_ipv4_cidr.
_gh_meta_cache_read() {
    local dir fd f body now mtime age; dir=$(dirname "$GH_META_CACHE")
    _gh_meta_open_dir "$dir" || return 1
    fd="$GH_META_FD"
    f="/proc/self/fd/$fd/$(basename "$GH_META_CACHE")"
    if [ -L "$f" ] || [ ! -f "$f" ] \
       || [ "$(stat -c %u "$f" 2>/dev/null)" != "$(id -u)" ] \
       || [ "$(stat -c %a "$f" 2>/dev/null)" != "600" ]; then
        exec {fd}<&-; return 1
    fi
    now=$(date +%s); mtime=$(stat -c %Y "$f" 2>/dev/null) || { exec {fd}<&-; return 1; }
    age=$(( now - mtime ))
    body=$(cat "$f" 2>/dev/null) || body=""
    exec {fd}<&-
    [ "$age" -ge 0 ] && [ "$age" -le "$GH_META_CACHE_MAX_AGE" ] || return 1
    _gh_meta_body_ok "$body" || return 1
    printf '%s' "$body"
    return 0
}

# _gh_meta_body_ok <body>: the shape check AND every IPv4 CIDR public — used
# before caching too, so a body with one bad range never gets persisted and
# re-served (which would fail every later boot closed for the cache lifetime).
_gh_meta_body_ok() {
    local c
    [ -n "$1" ] || return 1
    printf '%s' "$1" | jq -e '.web and .api and .git' >/dev/null 2>&1 || return 1
    while IFS= read -r c; do
        [ -n "$c" ] || continue
        case "$c" in *:*) continue ;; esac   # IPv6 entries are dropped by aggregate below
        _public_ipv4_cidr "$c" || return 1
    done < <(printf '%s' "$1" | jq -r '(.web + .api + .git)[]' 2>/dev/null)
    return 0
}

# _public_ipv4_cidr <a.b.c.d/p>: shape AND range. Rejects prefixes shorter than
# /16 (GitHub's real /meta ranges are /20, /22 and /32 as of 2026-09) and every
# non-public or special-purpose block (0/8, 10/8, 100.64/10, 127/8, 169.254/16,
# 172.16/12, 192.0.0/24, 192.0.2/24, 192.168/16, 198.18/15 — OrbStack's host
# side lives in 198.19.x — 198.51.100/24, 203.0.113/24, 224/3). Anything else
# reaching ipset would mean a poisoned source, and the caller exits 1.
_public_ipv4_cidr() {
    [[ "$1" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})/([0-9]{1,2})$ ]] || return 1
    local a=${BASH_REMATCH[1]} b=${BASH_REMATCH[2]} c=${BASH_REMATCH[3]} d=${BASH_REMATCH[4]} p=${BASH_REMATCH[5]}
    [ "$a" -le 255 ] && [ "$b" -le 255 ] && [ "$c" -le 255 ] && [ "$d" -le 255 ] || return 1
    [ "$p" -ge 16 ] && [ "$p" -le 32 ] || return 1
    [ "$a" -eq 0 ] && return 1
    [ "$a" -eq 10 ] && return 1
    [ "$a" -eq 127 ] && return 1
    [ "$a" -ge 224 ] && return 1
    [ "$a" -eq 100 ] && [ "$b" -ge 64 ] && [ "$b" -le 127 ] && return 1
    [ "$a" -eq 169 ] && [ "$b" -eq 254 ] && return 1
    [ "$a" -eq 172 ] && [ "$b" -ge 16 ] && [ "$b" -le 31 ] && return 1
    [ "$a" -eq 192 ] && [ "$b" -eq 168 ] && return 1
    [ "$a" -eq 192 ] && [ "$b" -eq 0 ] && { [ "$c" -eq 0 ] || [ "$c" -eq 2 ]; } && return 1
    [ "$a" -eq 198 ] && { [ "$b" -eq 18 ] || [ "$b" -eq 19 ]; } && return 1
    [ "$a" -eq 198 ] && [ "$b" -eq 51 ] && [ "$c" -eq 100 ] && return 1
    [ "$a" -eq 203 ] && [ "$b" -eq 0 ] && [ "$c" -eq 113 ] && return 1
    return 0
}

# Fetch GitHub's published IP ranges, retrying a transient failure.
#
# Why retry: this fetch runs from postStartCommand while the container's
# network is still settling, and a single failure here used to be terminal.
# The trap above then locks the box down, `vibe` reuses the running container
# on relaunch WITHOUT re-running postStartCommand, and nothing ever retries -
# so one blip stranded a container with no reachable API until the user
# rebuilt it. Observed live 2026-07-29 (curl rc=28 at this exact line).
#
# Validation lives inside the retry loop deliberately: an empty body, a
# non-JSON error page and a rate-limit JSON body without the fields we need
# are all transient conditions that a later attempt can clear.
#
# Patience: 6 attempts x linear backoff (2,4,6,8,10s sleeps = ~30s + fetch
# time). The original 3x2s (~6s) was not enough for a cold Docker Desktop
# container whose network settles late - observed live 2026-08-03: postStart
# failed 3/3 with an unusable (non-empty!) body, while the identical fetch
# succeeded manually minutes later. The unusable body is now logged (first
# 160 printable chars) so the next occurrence identifies itself - rate-limit
# JSON, proxy error page and half-ready-network garbage all look identical
# without it.
# Prints the response body on stdout; returns 1 if every attempt failed.

fetch_gh_ranges() {
    local attempt=1 resp="" body="" code="" snippet="" tok="$GH_META_TOKEN"
    case "$GH_META_URL" in
        https://api.github.com/*) ;;
        *) tok="" ;;   # never send the token anywhere but GitHub's API host
    esac
    while [ "$attempt" -le "$GH_FETCH_ATTEMPTS" ]; do
        if [ -n "$tok" ]; then
            resp=$(printf 'header = "Authorization: Bearer %s"\n' "$tok" \
                   | curl -s --connect-timeout 5 --max-time 20 -H "Accept: application/vnd.github+json" \
                          -K - -w '\n%{http_code}' "$GH_META_URL") || resp=""
        else
            resp=$(curl -s --connect-timeout 5 --max-time 20 -H "Accept: application/vnd.github+json" \
                        -w '\n%{http_code}' "$GH_META_URL") || resp=""
        fi
        # curl -w appends the status as a final line; a stub/proxy that omits it
        # leaves code empty and the body is judged on content alone.
        code="${resp##*$'\n'}"
        if [[ "$code" =~ ^[0-9]{3}$ ]]; then body="${resp%$'\n'*}"; else body="$resp"; code=""; fi
        if _gh_meta_body_ok "$body"; then
            _gh_meta_cache_write "$body"
            printf '%s' "$body"
            return 0
        fi
        if [ -n "$body" ]; then
            # Slice BEFORE piping: an oversized body through `head -c` would
            # SIGPIPE `tr` and, under pipefail, abort the script (rc 141) before
            # the cache fallback below could run.
            snippet=$(printf '%s' "${body:0:160}" | tr -d '\n\r' | tr -c '[:print:]' '.')
            if [ "$code" = "429" ] || { { [ "$code" = "403" ] || [ -z "$code" ]; } && [[ "$body" == *"rate limit exceeded"* ]]; }; then
                # Retrying inside the same hour cannot succeed; go straight to
                # the cache instead of burning ~30s of boot on backoff.
                echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS is rate-limited - not retrying (body starts: ${snippet})" >&2
                break
            elif [ -n "$tok" ] && { [ "$code" = "401" ] || [[ "$body" == *"Bad credentials"* ]]; }; then
                echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS rejected the token - retrying anonymously" >&2
                tok=""
            else
                echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS returned an unusable response - retrying (body starts: ${snippet})" >&2
            fi
        else
            echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS could not fetch $GH_META_URL - retrying" >&2
        fi
        if [ "$attempt" -lt "$GH_FETCH_ATTEMPTS" ]; then
            sleep "$(( GH_FETCH_BACKOFF * attempt ))"
        fi
        attempt=$(( attempt + 1 ))
    done
    if body=$(_gh_meta_cache_read); then
        echo "WARNING: GitHub meta unreachable - using the cached IP ranges at $GH_META_CACHE (last fetched $(date -u -r "$GH_META_CACHE" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown))" >&2
        printf '%s' "$body"
        return 0
    fi
    return 1
}

# Tiered allowlist (task_031 follow-up, flagged by security-review on the
# fail-closed PR). The per-domain loop below is deliberately non-fatal so one
# dead OPTIONAL domain (the statsig.anthropic.com case) cannot abort before the
# DROP policy — but that softness let a transient miss on a CRITICAL domain
# boot a container that is firewalled yet unable to reach Anthropic: worse than
# no boot, because `vibe` reuses a running container without re-running
# postStart, so nothing ever retries. Domains listed here are must-have: a miss
# gets the same patience as the GitHub meta fetch (retries with linear backoff
# below), and if it STILL cannot resolve we exit 1 → the fail_closed trap locks
# the box → `devcontainer up` reports failure → the launcher removes the
# container and retries once fresh. Everything else stays warn-and-skip.
#
# Keep this tier conservative: only domains without which a vibe session is
# pointless. GitHub (web/api/git) is covered separately by fetch_gh_ranges,
# which is already fatal-after-retries.
MUST_HAVE_DOMAINS="api.anthropic.com"

DNS_RESOLVE_ATTEMPTS="${DNS_RESOLVE_ATTEMPTS:-6}"
DNS_RESOLVE_BACKOFF="${DNS_RESOLVE_BACKOFF:-2}"

# Resolve a domain's A records, retrying up to $2 attempts with the same
# linear backoff shape as fetch_gh_ranges (2,4,6,8,10s for 6 attempts).
# Prints one IP per line on stdout; returns 1 if every attempt came up empty.
# Callers pass attempts=1 for optional domains so a genuinely dead domain
# costs one dig, not ~30s of boot latency per miss.
resolve_a_records() {
    local domain="$1" attempts="$2" attempt=1 ips=""
    while [ "$attempt" -le "$attempts" ]; do
        ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}') || ips=""
        if [ -n "$ips" ]; then
            printf '%s\n' "$ips"
            return 0
        fi
        if [ "$attempt" -lt "$attempts" ]; then
            echo "WARNING: DNS attempt $attempt/$attempts could not resolve $domain - retrying" >&2
            sleep "$(( DNS_RESOLVE_BACKOFF * attempt ))"
        fi
        attempt=$(( attempt + 1 ))
    done
    return 1
}

# ── Extra domains (task_041) ─────────────────────────────────────────────────
# $1 is an optional space/comma-separated allowlist EXTENSION, resolved
# launcher-side from <workspace>/.vibe/domains (untracked) or VIBE_EXTRA_DOMAINS
# in ~/.vibe/config, and handed over as ARGV because the sudoers rule for this
# script sets env_reset (an exported name would never survive the sudo).
#
# Every entry is re-validated HERE. The launcher already validated it, but this
# script runs as root and is the thing that actually widens the firewall, so it
# does not trust the argv it was handed — a compromised or merely buggy caller
# must not be able to smuggle a token through to `dig`. Extras join the loop at
# the OPTIONAL tier only: a project's private endpoint failing to resolve is a
# warning, never a reason to refuse the whole container a network.
EXTRA_DOMAINS_MAX="${EXTRA_DOMAINS_MAX:-32}"

# validate_extra_domain <token> — 0 iff <token> is a plain dotted DNS hostname.
# The LDH-label charset excludes every shell metacharacter, glob character,
# path separator and URL scheme, so a hostile entry cannot become a command;
# the all-numeric guard rejects a bare IPv4 literal. Kept byte-identical to the
# launcher's copy in `vibe` — deliberately duplicated, not shared, so neither
# side depends on the other having run.
validate_extra_domain() {
    local d="$1"
    [ -n "$d" ] || return 1
    [ "${#d}" -le 253 ] || return 1
    [[ "$d" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]] || return 1
    # Spelt as an `if`, not `[[ ]] && return 1`: under `set -e` the && form
    # makes the whole statement exit 1 on the common (non-matching) path, which
    # would kill the script the moment this is called outside a condition.
    if [[ "$d" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then return 1; fi
    return 0
}

# EXTRA_DOMAINS is built NEWLINE-separated, and the separators in $1 are
# normalised to newlines first, because line 3 sets IFS=$'\n\t' — this script
# does NOT split words on spaces. A space-joined list would arrive at the
# resolve loop as one unsplittable token, so the allowlist would look
# configured and quietly allow nothing. _extra_seen keeps a space-joined twin
# purely for the O(1) duplicate test and the log line.
EXTRA_DOMAINS=""
_extra_seen=""
if [ -n "${1:-}" ]; then
    _extra_n=0
    # Globbing off: an entry like `*.example.com` must reach the validator as a
    # literal to be rejected, not be expanded against the filesystem first.
    set -f
    # \r is in the separator set too: a list that came from a CRLF file would
    # otherwise carry a trailing \r into the validator and be rejected wholesale.
    for _extra_d in $(printf '%s' "$1" | tr ',\r \t' '\n\n\n\n'); do
        if ! validate_extra_domain "$_extra_d"; then
            echo "WARNING: ignoring invalid extra domain '$_extra_d' - not a plain DNS hostname"
            continue
        fi
        case " $_extra_seen " in *" $_extra_d "*) continue ;; esac
        _extra_n=$(( _extra_n + 1 ))
        if [ "$_extra_n" -gt "$EXTRA_DOMAINS_MAX" ]; then
            echo "WARNING: extra domains capped at $EXTRA_DOMAINS_MAX - the rest were ignored"
            break
        fi
        _extra_seen="$_extra_seen $_extra_d"
        EXTRA_DOMAINS="${EXTRA_DOMAINS}${EXTRA_DOMAINS:+
}$_extra_d"
    done
    set +f
    [ -n "$_extra_seen" ] && echo "Extra allowlist domains (project-supplied):$_extra_seen"
fi

# Test hook: stop here when sourced for unit testing, before anything mutates
# the host's network state.
if [ -n "${VIBE_FIREWALL_SOURCE_ONLY:-}" ]; then
    return 0 2>/dev/null || exit 0
fi

trap fail_closed EXIT

# Read the postStart-piped token only now, with the fail-closed trap armed.
if [ -z "${VIBE_FIREWALL_SOURCE_ONLY:-}" ]; then
    _gh_meta_token_from_stdin
fi

# 1. Extract Docker DNS info BEFORE any flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules and delete existing ipsets
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# `iptables -F` flushes RULES but NOT the default policies, so a DROP left
# behind by a previous failed run (or by the fail_closed trap) survives into
# this one - and then blocks the GitHub meta fetch below, stranding this run
# in exactly the same failure. That made an already-closed container unable to
# self-heal in place: re-running this script could only ever re-fail. Reset the
# policies for the build phase.
#
# This widens nothing on net. A first, clean boot already starts from the
# kernel default of ACCEPT, so the open window here is the same one the normal
# path has always had; the body re-establishes DROP below before any allow rule
# is load-bearing, and the trap re-establishes DROP on any failure in between.
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT

# 2. Selectively restore ONLY internal Docker DNS resolution
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore"
fi

# First allow DNS and localhost before any restrictions
# Allow outbound DNS
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
# Allow inbound DNS responses
iptables -A INPUT -p udp --sport 53 -j ACCEPT
# Allow outbound SSH
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
# Allow inbound SSH responses
iptables -A INPUT -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT
# Allow localhost
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Create ipset with CIDR support
ipset create allowed-domains hash:net

# Fetch GitHub meta information and aggregate + add their IP ranges.
# fetch_gh_ranges retries, validates, and falls back to the last good cached
# body; a hard failure here (no fetch AND no cache) is genuine and stays
# fatal, so the trap locks the container down.
echo "Fetching GitHub IP ranges..."
if ! gh_ranges=$(fetch_gh_ranges); then
    echo "ERROR: Failed to fetch usable GitHub IP ranges after $GH_FETCH_ATTEMPTS attempts"
    exit 1
fi

echo "Processing GitHub IPs..."
while read -r cidr; do
    if ! _public_ipv4_cidr "$cidr"; then
        echo "ERROR: Invalid or non-public CIDR range from GitHub meta: $cidr"
        rm -f "$GH_META_CACHE" 2>/dev/null || true   # never re-serve a body that failed here
        exit 1
    fi
    echo "Adding GitHub range $cidr"
    ipset add --exist allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

# Persist the validated extra-domain list where refresh-extra-domains.sh can
# find it (task_042). That script takes NO argv on purpose - a caller must not
# be able to widen the allowlist by passing a different list - so the names it
# is allowed to re-resolve have to come from a root-owned file that only this
# script writes. Written here, immediately before the resolve loop, so it
# always describes exactly what the firewall was built to allow.
VIBE_RUN_DIR="${VIBE_RUN_DIR:-/run/vibe}"
EXTRA_DOMAINS_STATE="$VIBE_RUN_DIR/extra-domains"
# Best effort, deliberately: this file is bookkeeping for a convenience script,
# NOT part of the allowlist. Under `set -e` an unwritable /run (a read-only
# mount, a full tmpfs) would otherwise abort here, the fail_closed trap would
# fire, and a container that used to boot with a perfectly good firewall would
# now refuse to start over a missing hint file. Losing the file costs exactly
# one thing: `refresh-extra-domains.sh` says "no extra domains configured".
# Refuse a pre-existing /run/vibe that is a symlink or not root-owned: `mkdir
# -p` would accept it, `chmod 0755` would leave a node-owned directory writable
# by node, and the redirect below would follow a symlink into wherever it
# points. refresh-extra-domains.sh makes the mirror-image check on read.
_extra_state_ok=1
if [ -L "$VIBE_RUN_DIR" ]; then
    _extra_state_ok=0
elif [ -e "$VIBE_RUN_DIR" ]; then
    if [ ! -d "$VIBE_RUN_DIR" ] || [ "$(stat -c %u "$VIBE_RUN_DIR" 2>/dev/null)" != "$(id -u)" ]; then
        _extra_state_ok=0
    fi
elif ! mkdir -m 0755 "$VIBE_RUN_DIR" 2>/dev/null; then
    _extra_state_ok=0
fi
if [ "$_extra_state_ok" = "1" ] && [ -L "$EXTRA_DOMAINS_STATE" ]; then
    # Never write through a symlink planted where the list belongs.
    rm -f "$EXTRA_DOMAINS_STATE" 2>/dev/null || _extra_state_ok=0
fi
if [ "$_extra_state_ok" = "1" ]; then
    if [ -n "$EXTRA_DOMAINS" ]; then
        if printf '%s\n' "$EXTRA_DOMAINS" > "$EXTRA_DOMAINS_STATE" 2>/dev/null; then
            chmod 0644 "$EXTRA_DOMAINS_STATE" 2>/dev/null || true
        else
            _extra_state_ok=0
        fi
    else
        # No extras this launch: remove any file a previous run left behind, so
        # a relaunch that dropped .vibe/domains cannot keep refreshing
        # yesterday's hosts. (postStart re-runs this on every container start.)
        rm -f "$EXTRA_DOMAINS_STATE" 2>/dev/null || true
    fi
fi
if [ "$_extra_state_ok" != "1" ]; then
    echo "Note: could not write $EXTRA_DOMAINS_STATE - mid-session domain refresh unavailable (firewall itself is unaffected)"
fi

# Resolve and add other allowed domains
# NOTE: statsig.anthropic.com was removed - it has no A record (decommissioned)
# and was the exact domain whose resolution failure tripped the old fail-open
# bug every boot. statsig.com (Claude Code telemetry) is kept. api.zotero.org is
# allowlisted so vibe's direct Zotero web-API access keeps working now that the
# firewall actually enforces (it only worked before because the box was open).
# seed.radicle.garden is the public Radicle seed node: it serves repos over
# HTTPS git (443) and the Radicle node protocol (8776). The ipset match below is
# destination-IP only, so allowlisting the host covers both ports. Needed to
# `claude plugin marketplace add` a Radicle-hosted marketplace and to push/fetch
# `rad://` remotes from inside a container.
# shellcheck disable=SC2086  # EXTRA_DOMAINS holds validated hostname tokens;
# word splitting is exactly what turns them into separate loop items.
for domain in \
    "registry.npmjs.org" \
    "api.anthropic.com" \
    "api.zotero.org" \
    "seed.radicle.garden" \
    "download.swift.org" \
    "sentry.io" \
    "statsig.com" \
    "marketplace.visualstudio.com" \
    "vscode.blob.core.windows.net" \
    "update.code.visualstudio.com" \
    $EXTRA_DOMAINS; do
    echo "Resolving $domain..."
    # Two tiers (see MUST_HAVE_DOMAINS above). Optional: a domain that fails to
    # resolve (e.g. a decommissioned endpoint) must NOT abort the whole
    # allowlist build - skip it and carry on, so the rest of the firewall is
    # still configured and the script still reaches the DROP policy. Must-have:
    # retry with backoff first, then exit 1 so the fail_closed trap fires and
    # the launcher's fresh-container retry gets a second go - a container that
    # cannot reach this domain is not worth booting.
    tier="optional"
    case " $MUST_HAVE_DOMAINS " in
        *" $domain "*) tier="must-have" ;;
    esac
    if [ "$tier" = "must-have" ]; then
        if ! ips=$(resolve_a_records "$domain" "$DNS_RESOLVE_ATTEMPTS"); then
            echo "WARNING: must-have domain $domain did not resolve after $DNS_RESOLVE_ATTEMPTS attempts - failing CLOSED (tier: must-have; a session without $domain is unusable)"
            exit 1
        fi
    else
        ips=$(resolve_a_records "$domain" 1) || true
        if [ -z "$ips" ]; then
            echo "WARNING: could not resolve $domain - skipping (not allowlisted this run; tier: optional)"
            continue
        fi
    fi

    while read -r ip; do
        if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "WARNING: invalid IP '$ip' from DNS for $domain - skipping"
            continue
        fi
        echo "Adding $ip for $domain"
        ipset -exist add allowed-domains "$ip"
    done < <(echo "$ips" | sort -u)
done

# Get host IP from default route
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi

HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Host network detected as: $HOST_NETWORK"

# Set up remaining iptables rules
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# OpenProject MCP forwarder reachability (optional). The tailnet-only OP MCP is
# reached via a Mac-side forwarder the container hits through
# `host.docker.internal` (mapped with --add-host). On Docker Desktop / OrbStack
# that host-gateway frequently sits OUTSIDE the default-route /24 ACCEPTed above
# (observed: 192.168.65.254), so without an explicit allow it would be DROPped.
# Non-fatal, exactly like the per-domain loop earlier: a resolution miss must
# NOT abort before the DROP policy below — warn and carry on, so /op simply
# stays unavailable rather than the firewall being left half-built (fail-closed).
HOST_INTERNAL_IP=$(getent hosts host.docker.internal 2>/dev/null | awk '{print $1; exit}') || true
if [ -z "$HOST_INTERNAL_IP" ]; then
    echo "Note: host.docker.internal did not resolve - OP MCP forwarder path not allowlisted (harmless unless using /op)"
elif [[ "$HOST_INTERNAL_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    if [ "${HOST_INTERNAL_IP%.*}" = "${HOST_NETWORK%.0/24}" ]; then
        echo "host.docker.internal ($HOST_INTERNAL_IP) already within $HOST_NETWORK - no extra rule needed"
    else
        echo "Allowing host.docker.internal at $HOST_INTERNAL_IP (host-gateway outside $HOST_NETWORK)"
        iptables -A INPUT  -s "$HOST_INTERNAL_IP" -j ACCEPT
        iptables -A OUTPUT -d "$HOST_INTERNAL_IP" -j ACCEPT
    fi
else
    echo "WARNING: host.docker.internal resolved to non-IPv4 '$HOST_INTERNAL_IP' - skipping (OP MCP forwarder path not allowlisted)"
fi

# Set default policies to DROP first
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# First allow established connections for already approved traffic
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Then allow only specific outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Explicitly REJECT all other outbound traffic for immediate feedback
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

echo "Firewall configuration complete"
echo "Verifying firewall rules..."
if curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - was able to reach https://example.com"
    exit 1
else
    echo "Firewall verification passed - unable to reach https://example.com as expected"
fi

# Verify GitHub API access
if ! curl --connect-timeout 5 https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - unable to reach https://api.github.com"
    exit 1
else
    echo "Firewall verification passed - able to reach https://api.github.com as expected"
fi
