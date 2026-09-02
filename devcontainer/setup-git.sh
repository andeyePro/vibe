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

# $HOME-relative, not hardcoded /home/node: identical in production (HOME is
# /home/node), but a hardcoded DST made every sandbox-HOME test run overwrite
# the REAL ~/.gitconfig via the cp below — wiping core.hooksPath and silently
# detaching the content-guard hooks (found 2026-08-30 chasing exactly that).
SRC="$HOME/.gitconfig-host"
DST="$HOME/.gitconfig"

if [ -f "$SRC" ]; then
  cp "$SRC" "$DST"
  chmod 644 "$DST"
fi

# Drop every credential helper the host copy carried before wiring vibe's.
# Host helpers (gh, osxkeychain, manager-core, ...) do not exist in the
# container: git still invokes them, so each fetch/push prints
# "/opt/homebrew/bin/gh: not found" (twice: get + store) before falling
# through to vibe's helper. URL-scoped entries such as
# credential.https://github.com.helper survive a plain `git config --global
# credential.helper` (different key), and gh's leading empty `helper =`
# line resets git's helper list — so strip the lot, then set ours alone.
while IFS= read -r _key; do
  [ -n "$_key" ] && git config --global --unset-all "$_key" || true
done < <(git config --global --name-only --get-regexp '^credential\.(.*\.)?helper$' 2>/dev/null || true)
git config --global credential.helper /usr/local/bin/vibe-credential-helper

# task_017 (shared-repos): make git send the repository `path` (owner/repo) to
# the credential helper on every request. Without this git omits `path` and the
# helper cannot tell the project repo apart from a shared repo — so it can only
# fall back to the pathless compat behaviour. Set at the SAME (--global) scope
# as the helper so it applies to /workspace AND every /repos/* shared checkout.
git config --global credential.useHttpPath true
