#!/usr/bin/env bash
# register-op-mcp.sh — register the OpenProject HTTP MCP for in-container Claude
# Code, but ONLY when its credentials are staged AND the endpoint is actually
# reachable through the Mac-side forwarder. Runs at postStart, after the firewall
# and install-claude-extras. Reachability-gated so we never register a dead
# endpoint (which would error on every Claude start).
#
# Path: container --(--add-host <host>:host-gateway)--> Mac forwarder (127.0.0.1:
# $OPENPROJECT_MCP_FWD_PORT) --> tailnet sidecar :443. TLS is end-to-end, so the
# URL keeps the real hostname (cert/SNI validate); we attach an explicit bare
# `Host:` header so the sidecar's DNS-rebinding guard accepts the non-443 port.
#
# Always exits 0 — a missing/unreachable OP MCP is a normal state, not a failure,
# and must not abort postStart.

set -uo pipefail

URL="${OPENPROJECT_MCP_URL:-}"
BEARER="${OPENPROJECT_MCP_BEARER:-}"
PORT="${OPENPROJECT_MCP_FWD_PORT:-18443}"

# No creds staged → nothing to do (the common case).
if [ -z "$URL" ] || [ -z "$BEARER" ]; then
  exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "register-op-mcp: 'claude' not on PATH — skipping MCP registration."
  exit 0
fi

# Derive scheme / host / path from the canonical URL (e.g.
# https://openproject-mcp.<tailnet>.ts.net/mcp/).
scheme="${URL%%://*}"
rest="${URL#*://}"
host="${rest%%/*}"
host="${host%%:*}"           # strip any port; the forwarder owns the port
path="${rest#*/}"            # e.g. "mcp/"
if [ "$path" = "$rest" ]; then
  path=""                   # URL had no path component
fi

if [ -z "$scheme" ] || [ -z "$host" ]; then
  echo "register-op-mcp: could not parse OPENPROJECT_MCP_URL ('$URL') — skipping."
  exit 0
fi

container_url="${scheme}://${host}:${PORT}/${path}"
healthz_url="${scheme}://${host}:${PORT}/healthz"

# Reachability gate: probe /healthz through the forwarder with the bare Host
# header. A miss is non-fatal (forwarder not up, creds stale, NAS down) — warn
# and leave the MCP unregistered rather than wiring a broken endpoint.
if ! curl -fsS --max-time 6 -H "Host: ${host}" "$healthz_url" >/dev/null 2>&1; then
  echo "register-op-mcp: OP MCP not reachable at ${host}:${PORT} (forwarder down?)"
  echo "                 — leaving /op unregistered this session."
  # Drop any stale registration so a dead server isn't probed on every start.
  claude mcp remove openproject --scope user >/dev/null 2>&1 || true
  exit 0
fi

# Reachable → register idempotently (remove-then-add picks up a rotated bearer
# or changed endpoint).
claude mcp remove openproject --scope user >/dev/null 2>&1 || true
if claude mcp add --transport http openproject "$container_url" \
     --header "Authorization: Bearer ${BEARER}" \
     --header "Host: ${host}" \
     --scope user >/dev/null 2>&1; then
  echo "register-op-mcp: registered OpenProject MCP (HTTP) → ${host}:${PORT}"
else
  echo "register-op-mcp: 'claude mcp add' failed — /op unregistered this session."
fi

exit 0
