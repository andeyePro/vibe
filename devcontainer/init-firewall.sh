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
    local attempt=1 body="" snippet=""
    while [ "$attempt" -le "$GH_FETCH_ATTEMPTS" ]; do
        body=$(curl -s --connect-timeout 5 --max-time 20 "$GH_META_URL") || body=""
        if [ -n "$body" ] && echo "$body" | jq -e '.web and .api and .git' >/dev/null 2>&1; then
            printf '%s' "$body"
            return 0
        fi
        if [ -n "$body" ]; then
            snippet=$(printf '%s' "$body" | tr -d '\n\r' | tr -c '[:print:]' '.' | head -c 160)
            echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS returned an unusable response - retrying (body starts: ${snippet})" >&2
        else
            echo "WARNING: GitHub meta attempt $attempt/$GH_FETCH_ATTEMPTS could not fetch $GH_META_URL - retrying" >&2
        fi
        if [ "$attempt" -lt "$GH_FETCH_ATTEMPTS" ]; then
            sleep "$(( GH_FETCH_BACKOFF * attempt ))"
        fi
        attempt=$(( attempt + 1 ))
    done
    return 1
}

# Test hook: stop here when sourced for unit testing, before anything mutates
# the host's network state.
if [ -n "${VIBE_FIREWALL_SOURCE_ONLY:-}" ]; then
    return 0 2>/dev/null || exit 0
fi

trap fail_closed EXIT

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
# fetch_gh_ranges retries and validates; a hard failure here is genuine (not a
# blip) and must stay fatal, so the trap locks the container down.
echo "Fetching GitHub IP ranges..."
if ! gh_ranges=$(fetch_gh_ranges); then
    echo "ERROR: Failed to fetch usable GitHub IP ranges after $GH_FETCH_ATTEMPTS attempts"
    exit 1
fi

echo "Processing GitHub IPs..."
while read -r cidr; do
    if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        echo "ERROR: Invalid CIDR range from GitHub meta: $cidr"
        exit 1
    fi
    echo "Adding GitHub range $cidr"
    ipset add --exist allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

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
    "update.code.visualstudio.com"; do
    echo "Resolving $domain..."
    # Non-fatal: a single domain that fails to resolve (e.g. a decommissioned
    # endpoint) must NOT abort the whole allowlist build - skip it and carry on,
    # so the rest of the firewall is still configured and the script still
    # reaches the DROP policy. `|| true` stops pipefail from tripping `set -e`;
    # the empty-check below handles the miss.
    ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}') || true
    if [ -z "$ips" ]; then
        echo "WARNING: could not resolve $domain - skipping (not allowlisted this run)"
        continue
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
