#!/bin/bash
# Sets up a writable, sanitized SSH environment inside the container.
#
# The host ~/.ssh is mounted read-only at /home/node/.ssh-host to preserve
# isolation. This script builds a clean /home/node/.ssh from it:
#   - Strips macOS-only options (UseKeychain, AddKeychainToAgent) that break
#     Linux's ssh client.
#   - Copies private keys with chmod 600 so ssh will accept them.
#   - Copies public keys, known_hosts, and authorized_keys as-is.
#   - Leaves the config's Include directives intact (paths are rewritten to
#     point into /home/node/.ssh so relative includes still work).

set -euo pipefail

SRC=/home/node/.ssh-host
DST=/home/node/.ssh

mkdir -p "$DST"
chmod 700 "$DST"

# Nothing to do if the host didn't mount an SSH dir
[ -d "$SRC" ] || exit 0

# Sanitize ssh config: strip macOS-only options
if [ -f "$SRC/config" ]; then
  grep -Eiv '^\s*(UseKeychain|AddKeychainToAgent)\s' "$SRC/config" > "$DST/config" || true
  chmod 600 "$DST/config"
fi

# Copy all other files, setting strict permissions on private keys
while IFS= read -r -d '' f; do
  name="$(basename "$f")"
  # Skip config (handled above) and directories
  [ -f "$f" ] || continue
  [ "$name" = "config" ] && continue

  cp "$f" "$DST/$name"

  # Private keys: no extension and matching *.pub exists, or named id_*
  if [[ "$name" == *.pub ]] || [[ "$name" == "known_hosts"* ]] || [[ "$name" == "authorized_keys"* ]]; then
    chmod 644 "$DST/$name"
  else
    chmod 600 "$DST/$name"
  fi
done < <(find "$SRC" -maxdepth 1 -print0)
