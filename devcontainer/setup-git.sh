#!/bin/bash
# Build a writable ~/.gitconfig from the host-mounted read-only copy at
# ~/.gitconfig-host, then wire vibe's credential helper. Mirrors the
# setup-ssh.sh .ssh-host → .ssh pattern.
#
# Why not bind-mount ~/.gitconfig directly: `git config` writes via
# rename-over-tempfile, and renaming over a single-file bind mount raises
# EBUSY ("Device or resource busy") on Docker-for-Mac, which breaks
# postStartCommand deterministically.

set -euo pipefail

SRC=/home/node/.gitconfig-host
DST=/home/node/.gitconfig

if [ -f "$SRC" ]; then
  cp "$SRC" "$DST"
  chmod 644 "$DST"
fi

git config --global credential.helper /usr/local/bin/vibe-credential-helper
