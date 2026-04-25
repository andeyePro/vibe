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

  # Commands-only retirement: remove files that vibe used to ship but no
  # longer does. Allow-listed; user-authored files in dest are untouched.
  if [ "$kind" = "commands" ]; then
    local RETIRED_COMMANDS=("copy.md")
    local retired
    for retired in "${RETIRED_COMMANDS[@]}"; do
      rm -f "$dest/$retired"
    done
  fi

  # Overwrite only vibe-shipped files; leave user-created ones untouched.
  local file name
  for file in "$src"/*.md; do
    [ -e "$file" ] || continue
    name=$(basename "$file")
    cp -f "$file" "$dest/$name"
  done
}

# Install inline-prose Claude MD fragments into a managed block at the END
# of $DEST_ROOT/CLAUDE.md. The block is delimited by HTML comment markers
# distinct from write-env-hint.sh's block (which sits at the TOP).
install_claude_md_fragments() {
  local src_dir="$SRC_ROOT/claude-md"
  local target="$DEST_ROOT/CLAUDE.md"
  local open_delim='<!-- >>> vibe-managed (auto, do not edit) >>>'
  local close_delim='<!-- <<< vibe-managed <<< -->'

  # Ensure destination directory exists.
  mkdir -p "$(dirname "$target")"
  touch "$target"

  # Strip any pre-existing vibe-managed block (open+body+close) from the file,
  # then trim trailing blank lines from the remaining content.
  # Note: "close" is a reserved awk keyword; use "closetag" instead.
  local remaining
  remaining=$(awk \
    -v opentag="$open_delim" \
    -v closetag="$close_delim" '
    $0 == opentag  { inblock = 1; next }
    $0 == closetag && inblock { inblock = 0; next }
    !inblock    { lines[++n] = $0 }
    END {
      last = 0
      for (i = n; i >= 1; i--) {
        if (lines[i] != "") { last = i; break }
      }
      for (i = 1; i <= last; i++) print lines[i]
    }
  ' "$target")

  # Collect sorted fragment files (LC_ALL=C for POSIX byte-order).
  local fragments=()
  if [ -d "$src_dir" ]; then
    local f
    while IFS= read -r f; do
      [ -e "$f" ] && fragments+=("$f")
    done < <(
      for mdfile in "$src_dir"/*.md; do
        [ -e "$mdfile" ] && printf '%s\n' "$(basename "$mdfile")"
      done | LC_ALL=C sort | while IFS= read -r name; do
        printf '%s\n' "$src_dir/$name"
      done
    )
  fi

  # Build the managed block content. If there are no fragments, we skip the
  # block entirely - only user content (or nothing) will remain.
  local block_body=""
  local first_frag=1
  local frag name body
  for frag in "${fragments[@]}"; do
    name=$(basename "$frag")
    body=$(cat "$frag")
    if [ "$first_frag" -eq 1 ]; then
      block_body="<!-- vibe-md: ${name} -->"$'\n'"${body}"
      first_frag=0
    else
      block_body="${block_body}"$'\n\n'"<!-- vibe-md: ${name} -->"$'\n'"${body}"
    fi
  done

  # Write the final file.
  if [ "${#fragments[@]}" -gt 0 ]; then
    local block
    block="${open_delim}"$'\n'"${block_body}"$'\n'"${close_delim}"
    if [ -n "$remaining" ]; then
      printf '%s\n\n%s\n' "$remaining" "$block" > "$target.tmp"
    else
      printf '%s\n' "$block" > "$target.tmp"
    fi
  else
    # No fragments: write only the remaining user content (may be empty).
    if [ -n "$remaining" ]; then
      printf '%s\n' "$remaining" > "$target.tmp"
    else
      printf '' > "$target.tmp"
    fi
  fi
  mv "$target.tmp" "$target"
}

install_dir agents
install_dir commands
install_claude_md_fragments
