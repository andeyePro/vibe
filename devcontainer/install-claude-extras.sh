#!/usr/bin/env bash
# Sync vibe's curated agents + slash commands into the persistent
# /home/node/.claude volume. Runs on every container start so image
# rebuilds propagate, but user-authored files in sibling dirs are left
# alone.
set -euo pipefail

SRC_ROOT="${VIBE_EXTRAS_SRC_ROOT:-/usr/local/share/vibe}"
DEST_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

install_dir() {
  local kind="$1"  # "agents" or "commands"
  local src="$SRC_ROOT/$kind"
  local dest="$DEST_ROOT/$kind"

  [ -d "$src" ] || return 0
  mkdir -p "$dest"

  # Overwrite only vibe-shipped files; leave user-created ones untouched.
  local file name
  for file in "$src"/*.md; do
    [ -e "$file" ] || continue
    name=$(basename "$file")
    cp -f "$file" "$dest/$name"
  done
}

install_dir agents
install_dir commands
