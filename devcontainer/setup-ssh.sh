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
#   - Seeds host.docker.internal's host key into known_hosts (see below).

set -euo pipefail

SRC=/home/node/.ssh-host
DST=/home/node/.ssh

mkdir -p "$DST"
chmod 700 "$DST"

if [ -d "$SRC" ]; then
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
fi

# Seed the Mac's own host key under the name containers reach it by. Runs
# AFTER the copy loop (the host-file cp would overwrite it) and also when no
# host ~/.ssh was mounted (the Mac-build-bridge pattern uses a workspace
# keypair, not host keys). host.docker.internal never appears in the host's
# known_hosts (a Mac doesn't ssh to itself by that name), and this file is
# rebuilt from the read-only mount on EVERY container start, so an
# in-session `ssh-keyscan >> ~/.ssh/known_hosts` is wiped on the next
# launch. Without the seed, an unattended run's first
# `ssh host.docker.internal` hangs at the host-key prompt — a failure that
# only shows when nobody is watching. Hashed (-H) like client-written
# entries; non-fatal on any failure (no Remote Login, no resolution, slow
# scan), same stance as the firewall's optional-tier domains: never block
# container start. Deliberately NOT `StrictHostKeyChecking accept-new` —
# that would blanket-trust any first contact; seeding pins the key actually
# seen at container start.
seed_tmp=$(mktemp) || seed_tmp=""
if [ -z "$seed_tmp" ]; then
  echo "Note: host.docker.internal known_hosts seed skipped (mktemp failed)." >&2
else
  trap 'rm -f "$seed_tmp"' EXIT
  if ssh-keyscan -H -T 3 host.docker.internal > "$seed_tmp" 2>/dev/null \
     && [ -s "$seed_tmp" ]; then
    # Replace any prior entry rather than accumulate: postStart re-runs on
    # reused containers, so blind appends grow forever; and replacement
    # means a poisoned or rotated key is displaced by the next clean scan
    # instead of persisting (ssh-keygen -R handles hashed entries).
    if [ -f "$DST/known_hosts" ]; then
      ssh-keygen -R host.docker.internal -f "$DST/known_hosts" >/dev/null 2>&1 || true
      rm -f "$DST/known_hosts.old"
      # Guard against a host file with no trailing newline — appending onto
      # a partial line would corrupt a real pinned key AND leave the seed
      # unparsed.
      if [ -s "$DST/known_hosts" ] && [ -n "$(tail -c1 "$DST/known_hosts")" ]; then
        echo >> "$DST/known_hosts"
      fi
    fi
    cat "$seed_tmp" >> "$DST/known_hosts"
    chmod 644 "$DST/known_hosts"
    # TOFU visibility: this is an unattended trust-on-first-use pin, so
    # surface the fingerprint the way an interactive first connect would.
    echo "known_hosts: seeded host.docker.internal (unverified TOFU pin — compare against 'ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub' on the Mac if in doubt):" >&2
    ssh-keygen -lf "$seed_tmp" >&2 || true
  else
    echo "Note: host.docker.internal host-key scan unavailable (Remote Login off, or name unresolvable) — the first in-container ssh to it may prompt for the host key." >&2
  fi
  rm -f "$seed_tmp"
  trap - EXIT
fi
