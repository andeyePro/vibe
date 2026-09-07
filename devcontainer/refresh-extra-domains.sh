#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# refresh-extra-domains.sh (task_042) — re-resolve THIS project's extra
# allowlist domains and add their CURRENT addresses to the running firewall.
#
# Why this exists: init-firewall.sh snapshots A records once, at container
# start, and pins them into the `allowed-domains` ipset. Any host behind a CDN
# with short TTLs (Akamai, Cloudflare, Fastly — i.e. most SaaS APIs) moves to a
# different edge within the hour, so a session that was reaching api.xero.com
# at boot silently stops reaching it later: DNS still resolves, but the new
# edge IP is not in the ipset and the packet is REJECTed. Observed 2026-09-06
# in moneyandeye; the launch header still claimed the host was allowed, which
# was true of boot time and false of the moment.
#
# Deliberately NOT a timer. Martin's call (2026-09-07): a vibe left open for
# weeks would re-resolve thousands of times for nothing. This runs REACTIVELY —
# Claude invokes it when a request to an extra domain fails in the shape a
# stale pin produces, then retries once. See the `extra-domains-refresh.md`
# CLAUDE.md fragment, which is what teaches every vibe session that habit.
#
# Scope discipline — this script is additive and nothing else:
#   * it ONLY calls `ipset -exist add`; it never flushes the set,
#   * it never touches iptables, the policy, or the GitHub ranges,
#   * it never re-fetches /meta and never wants the PAT on stdin,
#   * it takes NO argv, so a caller cannot widen the allowlist with it.
# The domain list comes from a root-owned state file that init-firewall.sh
# wrote from its own already-validated list, and every entry is re-validated
# here anyway: this runs as root and is the thing that widens the firewall, so
# it does not trust what it reads any more than init-firewall.sh trusts argv.
#
# Consequence worth naming: entries accumulate. An edge IP that Akamai has
# since abandoned stays in the ipset until the container restarts. That is the
# price of never flushing — flushing here would race the domain loop and could
# strip api.anthropic.com from a live session — and it is a small, bounded
# widening (a handful of CDN edges for hosts the user already allowlisted),
# not a new class of hole.

# Test hooks. Under sudo these are all inert (the sudoers rule sets env_reset);
# they exist so smoke-test.py can exercise the helpers host-side with no
# root, no ipset and no network, mirroring init-firewall.sh's
# VIBE_FIREWALL_SOURCE_ONLY convention.
STATE_FILE="${VIBE_EXTRA_DOMAINS_STATE:-/run/vibe/extra-domains}"
IPSET_NAME="${VIBE_ALLOWED_IPSET:-allowed-domains}"
REFRESH_DNS_ATTEMPTS="${REFRESH_DNS_ATTEMPTS:-2}"
REFRESH_DNS_BACKOFF="${REFRESH_DNS_BACKOFF:-2}"
EXTRA_DOMAINS_MAX="${EXTRA_DOMAINS_MAX:-32}"

# Every one of the three reaches an arithmetic context, and `$(( ))` evaluates
# a variable's CONTENTS recursively - `REFRESH_DNS_BACKOFF='x[$(id)]'` would
# run `id` as root. sudo's env_reset means none of them survives the granted
# path today, but a script that widens the firewall as root must not depend on
# its caller for that. Anything non-numeric falls back to the default.
for _n in REFRESH_DNS_ATTEMPTS REFRESH_DNS_BACKOFF EXTRA_DOMAINS_MAX; do
    case "${!_n}" in
        ''|*[!0-9]*)
            echo "WARNING: ignoring non-numeric $_n - using the default" >&2
            case "$_n" in
                REFRESH_DNS_ATTEMPTS) REFRESH_DNS_ATTEMPTS=2 ;;
                REFRESH_DNS_BACKOFF)  REFRESH_DNS_BACKOFF=2 ;;
                EXTRA_DOMAINS_MAX)    EXTRA_DOMAINS_MAX=32 ;;
            esac
            ;;
    esac
done
unset _n

# validate_extra_domain <token> — 0 iff <token> is a plain dotted DNS hostname.
# Kept byte-identical to the copies in `vibe` and init-firewall.sh —
# deliberately duplicated, not shared, so no one of the three depends on
# another having run.
validate_extra_domain() {
    local d="$1"
    [ -n "$d" ] || return 1
    [ "${#d}" -le 253 ] || return 1
    [[ "$d" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]] || return 1
    # Spelt as an `if`, not `[[ ]] && return 1`: under `set -e` the && form
    # makes the whole statement exit 1 on the common (non-matching) path.
    if [[ "$d" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then return 1; fi
    return 0
}

# resolve_a_records <domain> <attempts> — one IP per line on stdout, 1 if every
# attempt came up empty. Same shape as init-firewall.sh's, with a shorter
# default attempt count: this runs in front of a waiting user, not at boot.
resolve_a_records() {
    local domain="$1" attempts="$2" attempt=1 ips=""
    while [ "$attempt" -le "$attempts" ]; do
        ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}') || ips=""
        if [ -n "$ips" ]; then
            printf '%s\n' "$ips"
            return 0
        fi
        if [ "$attempt" -lt "$attempts" ]; then
            sleep "$(( REFRESH_DNS_BACKOFF * attempt ))"
        fi
        attempt=$(( attempt + 1 ))
    done
    return 1
}

# valid_ipv4 <token> — 0 iff <token> is a dotted quad with every octet in
# 0-255. Stricter than the bare `[0-9]{1,3}` shape check init-firewall.sh uses
# on the same data: `999.1.1.1` passes that and would be handed to ipset, which
# rejects it with a confusing error. dig should never produce one, so this is
# defence in depth against a poisoned or spoofed resolver, not a live bug.
# (The looser copy in init-firewall.sh is a known parity gap — see TODO.)
valid_ipv4() {
    local ip="$1" o
    [[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || return 1
    local IFS=.
    for o in $ip; do
        # Strip leading zeros before the range test: `010` is not octal here,
        # but `08` would break arithmetic comparison in some shells.
        o=$((10#$o))
        [ "$o" -ge 0 ] && [ "$o" -le 255 ] || return 1
    done
    return 0
}

# Test hook: stop here when sourced, before anything reads state or touches
# the ipset.
if [ -n "${VIBE_REFRESH_SOURCE_ONLY:-}" ]; then
    return 0 2>/dev/null || exit 0
fi

# The state file is input to a root process that widens the firewall, so it is
# checked the way init-firewall.sh checks GH_META_CACHE: a planted file would
# become root-built firewall input. Today `node` cannot reach it (/run is a
# root-owned 0755 tmpfs and only root creates /run/vibe), but that safety is
# ambient — an image change or a `--tmpfs /run:mode=1777` would remove it
# silently. Enforce it at the reader instead of relying on the environment.
_state_dir=$(dirname "$STATE_FILE")
if [ -e "$STATE_FILE" ] || [ -L "$STATE_FILE" ]; then
    if [ -L "$_state_dir" ] || [ ! -d "$_state_dir" ] \
       || [ "$(stat -c %u "$_state_dir" 2>/dev/null)" != "$(id -u)" ]; then
        echo "ERROR: $_state_dir is not a $(id -un)-owned directory - refusing to read the domain list." >&2
        exit 1
    fi
    if [ -L "$STATE_FILE" ] || [ ! -f "$STATE_FILE" ] \
       || [ "$(stat -c %u "$STATE_FILE" 2>/dev/null)" != "$(id -u)" ]; then
        echo "ERROR: $STATE_FILE is not a $(id -un)-owned regular file - refusing to read it." >&2
        echo "       Only init-firewall.sh may write this list. Relaunch the container." >&2
        exit 1
    fi
fi

if [ ! -s "$STATE_FILE" ]; then
    echo "refresh-extra-domains: no extra domains configured for this project - nothing to refresh."
    echo "  (Set them per-project in <workspace>/.vibe/domains, untracked, or machine-wide via"
    echo "   VIBE_EXTRA_DOMAINS in ~/.vibe/config, then relaunch vibe.)"
    exit 0
fi

# No ipset means the firewall was never built (or was torn down). Refusing is
# right: this script's whole contract is "add to an existing allowlist". It
# must NOT try to build one - that is init-firewall.sh's job, and a
# half-built firewall from here would be worse than none.
if ! ipset list -n 2>/dev/null | grep -qx "$IPSET_NAME"; then
    echo "ERROR: ipset '$IPSET_NAME' does not exist - the firewall is not initialised." >&2
    echo "       This script only ADDS to a live allowlist. Relaunch the container." >&2
    exit 1
fi

added=0
resolved_domains=0
failed_domains=""
n=0

while IFS= read -r domain; do
    [ -n "$domain" ] || continue
    if ! validate_extra_domain "$domain"; then
        echo "WARNING: ignoring invalid entry '$domain' in $STATE_FILE - not a plain DNS hostname" >&2
        continue
    fi
    n=$(( n + 1 ))
    if [ "$n" -gt "$EXTRA_DOMAINS_MAX" ]; then
        echo "WARNING: extra domains capped at $EXTRA_DOMAINS_MAX - the rest were ignored" >&2
        break
    fi
    if ! ips=$(resolve_a_records "$domain" "$REFRESH_DNS_ATTEMPTS"); then
        failed_domains="$failed_domains $domain"
        continue
    fi
    resolved_domains=$(( resolved_domains + 1 ))
    while read -r ip; do
        if ! valid_ipv4 "$ip"; then
            echo "WARNING: invalid IP '$ip' from DNS for $domain - skipping" >&2
            continue
        fi
        # -exist makes a re-add a no-op, so the common case (nothing moved)
        # is silent and costs one syscall per address.
        if ipset -exist add "$IPSET_NAME" "$ip"; then
            added=$(( added + 1 ))
            echo "  allowed $ip ($domain)"
        fi
    done < <(echo "$ips" | sort -u)
done < "$STATE_FILE"

if [ -n "$failed_domains" ]; then
    echo "WARNING: could not resolve:$failed_domains (left as they were; DNS may be down)" >&2
fi

echo "refresh-extra-domains: re-resolved $resolved_domains domain(s), $added address(es) now allowed."

# Exit non-zero only if there was work to do and NONE of it succeeded - that is
# a real failure a caller should surface rather than retry into. A partial
# success is a success: the domain the caller cared about may well be the one
# that resolved.
if [ "$resolved_domains" -eq 0 ] && [ "$n" -gt 0 ]; then
    exit 1
fi
exit 0
