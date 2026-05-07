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

# Sync executable hook scripts into $DEST_ROOT/hooks/ and ensure +x.
# Hooks are referenced by absolute path from the user-level settings.json
# (e.g. Stop hook calling `/home/node/.claude/hooks/check-numbering.sh`),
# so the path must exist for the reference to resolve. User-authored
# hook files in the destination are left untouched.
install_hooks() {
  local src="$SRC_ROOT/hooks"
  local dest="$DEST_ROOT/hooks"

  [ -d "$src" ] || return 0
  mkdir -p "$dest"

  local file name
  for file in "$src"/*.sh; do
    [ -e "$file" ] || continue
    name=$(basename "$file")
    cp -f "$file" "$dest/$name"
    chmod +x "$dest/$name"
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

# Detect whether Superpowers is installed (user-scope) and surface a one-line
# banner + install command if not. Auto-install via direct file write into
# ~/.claude/plugins/ is the long-term goal but requires empirical layout
# discovery (option b in the TODO) - punt for now and at least make the manual
# install command visible on every container start. Opt-out via VIBE_PLUGINS=0.
check_superpowers() {
  # Honour opt-out
  if [ "${VIBE_PLUGINS:-1}" = "0" ]; then
    return 0
  fi

  local plugins_dir="$DEST_ROOT/plugins"
  # Heuristic: any subdir matching */superpowers* or any file containing
  # "obra/superpowers" path components. Layout TBD by empirical probe.
  if [ -d "$plugins_dir" ] && find "$plugins_dir" -maxdepth 3 -name '*superpowers*' 2>/dev/null | grep -q .; then
    return 0
  fi

  # Surface the banner to stderr so it shows up in postStart output.
  cat >&2 <<'EOF'

  vibe: Superpowers plugin not detected at ~/.claude/plugins/.
        For /sp and the 14 superpowers skills, run inside a vibe session:

          /plugin marketplace add anthropics/claude-plugins-official
          /plugin install superpowers@claude-plugins-official

        Persists in the vibe-claude-config volume across all your projects.
        Opt out of this banner: VIBE_PLUGINS=0.
        Auto-install pending empirical layout discovery (TODO: vibe ship
        Superpowers by default).

EOF
}

install_dir agents
install_dir commands
install_hooks
install_claude_md_fragments
check_superpowers
