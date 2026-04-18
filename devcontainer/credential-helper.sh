#!/bin/bash
# Git credential helper: returns $GITHUB_TOKEN as the password for github.com.
# Invoked by git when pushing/pulling — reads protocol/host/etc. from stdin,
# writes username=x / password=<token> to stdout. Any other host is a no-op,
# and git falls through to the next helper (or fails, which is what we want).
set -e

# Only respond to "get" operations. git also sends "store" and "erase" —
# ignore those (we're not managing storage here).
if [ "$1" != "get" ]; then
  exit 0
fi

# Parse key=value input from stdin.
declare -A cred
while IFS='=' read -r key value; do
  [ -z "$key" ] && break
  cred[$key]="$value"
done

# Only serve github.com over https with a token present.
if [ "${cred[protocol]}" = "https" ] && \
   [ "${cred[host]}" = "github.com" ] && \
   [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "username=x-access-token"
  echo "password=$GITHUB_TOKEN"
fi
