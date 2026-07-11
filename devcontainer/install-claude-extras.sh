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
    local RETIRED_COMMANDS=("copy.md" "expaste.md")
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
  # ssh-discipline.md is omitted when the user has opted into autonomous SSH
  # for this project, either via VIBE_SSH_AUTO=1 in ~/.vibe/config (plumbed
  # in through devcontainer.json's remoteEnv/containerEnv) or by touching
  # /workspace/.vibe-allow-ssh in the project root.
  local fragments=()
  if [ -d "$src_dir" ]; then
    local f
    while IFS= read -r f; do
      [ -e "$f" ] || continue
      if [ "$(basename "$f")" = "ssh-discipline.md" ]; then
        if [ "${VIBE_SSH_AUTO:-0}" = "1" ] || [ -f /workspace/.vibe-allow-ssh ]; then
          continue
        fi
      fi
      # brain2.md describes the /brain2 + /zotero mounts; only relevant when the
      # brain2 repo is actually mounted. Generic vibe users without the mount
      # never see it (keeps the shared CLAUDE.md free of brain2-specific noise).
      # VIBE_BRAIN2_MOUNT_DIR is an override for tests; defaults to real /brain2.
      if [ "$(basename "$f")" = "brain2.md" ] && [ ! -d "${VIBE_BRAIN2_MOUNT_DIR:-/brain2}" ]; then
        continue
      fi
      # shared-repos.md (task_017 Cycle 3, AC14) documents the /repos/<name>
      # mount + claim/etiquette rules; only relevant when at least one shared
      # repo is actually mounted this launch. Gated on the runtime manifest
      # (Pinned names: written by the launcher every launch, one line per
      # mounted repo) being non-empty — mirrors the brain2.md mount-existence
      # gate above. VIBE_SHARED_REPOS_MANIFEST is a test override; defaults to
      # the real in-container path.
      if [ "$(basename "$f")" = "shared-repos.md" ] \
         && [ ! -s "${VIBE_SHARED_REPOS_MANIFEST:-/workspace/.vibe/shared-repos.manifest}" ]; then
        continue
      fi
      fragments+=("$f")
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

# surfaces_has_vibe <path-to-SKILL.md> — exit 0 iff the skill declares it can
# run on vibe. Reads the `surfaces:` frontmatter line (e.g. `surfaces: [desktop,
# vibe]`); falls back to a `## Surfaces` body line (the loader-safe form the
# skills-sync canary switches to if the frontmatter key trips claude.ai's
# parser). Either form containing the word `vibe` counts.
surfaces_has_vibe() {
  local skillmd="$1" line
  line=$(grep -m1 -iE '^[[:space:]]*surfaces:' "$skillmd" 2>/dev/null || true)
  if [ -z "$line" ]; then
    line=$(awk 'tolower($0) ~ /^##[[:space:]]+surfaces/ { getline; print; exit }' "$skillmd" 2>/dev/null || true)
  fi
  printf '%s' "$line" | grep -qiE '\bvibe\b'
}

# Sync brain2's canonical skills into $DEST_ROOT/skills/. Source is the MOUNTED
# brain2 repo (not SRC_ROOT) — skills are canonical in brain2, shared with
# Claude Desktop; vibe just mirrors the vibe-runnable subset into containers.
# Only skills whose `surfaces:` includes `vibe` are copied; excel/desktop-only
# skills (e.g. accounts-check, monthly-finance) can't function in a container
# and would only confuse the agent. Gated on the brain2 mount existing, like the brain2.md
# fragment. Overwrites only the canonical skills it copies; user-authored skills
# and skills installed by another path (e.g. md/script, persisted in the
# vibe-claude-config volume) are left untouched.
install_brain2_skills() {
  local brain2="${VIBE_BRAIN2_MOUNT_DIR:-/brain2}"
  local src="$brain2/.claude/skills"
  local dest="$DEST_ROOT/skills"

  [ -d "$src" ] || return 0
  mkdir -p "$dest"

  local skilldir name md
  for skilldir in "$src"/*/; do
    [ -d "$skilldir" ] || continue
    md="$skilldir/SKILL.md"
    [ -f "$md" ] || continue
    surfaces_has_vibe "$md" || continue
    name=$(basename "$skilldir")
    # Replace only this one canonical skill dir; never touch siblings.
    rm -rf "${dest:?}/$name"
    cp -rf "$skilldir" "$dest/$name"
  done
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

# Report drift between sp.md's hardcoded Superpowers skill list and the
# upstream obra/superpowers skills/ directory, so a renamed/added upstream
# skill surfaces in the boot log instead of drifting silently. Informational
# only: check-sp-current.sh always exits 0, caps its network wait at 10s,
# and stays silent when upstream is unreachable. Shares the VIBE_PLUGINS=0
# opt-out with the plugin banner above.
check_sp_drift() {
  if [ "${VIBE_PLUGINS:-1}" = "0" ]; then
    return 0
  fi
  local checker="/usr/local/bin/check-sp-current.sh"
  [ -x "$checker" ] || return 0  # image predates the checker; skip quietly
  SP_MD="$DEST_ROOT/commands/sp.md" "$checker" || true
}

# Ensure /workspace/.gitignore excludes vibe's runtime files. Without this,
# downstream projects using vibe risk committing .claude/settings.local.json
# (an inside-container runtime file) and .vibe/copy-latest.txt (clipboard
# scratch). Both happened in amy-bo/electroPioreactor PR #16; the upstream
# reviewer flagged them. This is the structural fix.
#
# .vibe-signals/ (task_017 cycle 1) is the shared-repos coordination sidecar
# — added here so it's excluded when THIS project is itself a shared repo
# some other project mounts. This is one of TWO independent owners of that
# gitignore entry: the other is shared_repo_ensure_signals (in the `vibe`
# launcher), which directly ensures the same line in a shared checkout's own
# .gitignore at `vibe repos add` / mount-assembly time — needed because a
# shared checkout may not be a vibe project itself and may never have run
# this script. Deliberately NOT `.vibe-repos` — that file is committed by
# design (it's the project's declaration of which shared repos it uses).
#
# Behaviour: add a managed block to /workspace/.gitignore on first
# container start. If the block exists, leave it alone. User opt-out:
# VIBE_AUTO_GITIGNORE=0 (or remove the managed block by hand; it won't
# be re-added because the function checks for the block sentinel).
ensure_project_gitignore() {
  if [ "${VIBE_AUTO_GITIGNORE:-1}" = "0" ]; then
    return 0
  fi
  local project="/workspace"
  [ -d "$project/.git" ] || return 0  # only act in a git repo
  local gitignore="$project/.gitignore"
  local marker='# >>> vibe-managed runtime exclusions (auto-added; do not edit body) >>>'
  local close='# <<< vibe-managed <<<'
  if [ -f "$gitignore" ] && grep -qF "$marker" "$gitignore"; then
    return 0  # block already present; idempotent
  fi
  {
    [ -f "$gitignore" ] && [ -s "$gitignore" ] && echo
    echo "$marker"
    echo "# Files vibe writes to /workspace at runtime. Committing them"
    echo "# leaks per-machine state into the repo (PR-review-noise risk)."
    echo "# Opt out: set VIBE_AUTO_GITIGNORE=0 before container start, or"
    echo "# delete this entire block (won't be re-added once removed)."
    echo ".claude/settings.local.json"
    echo ".vibe/"
    echo ".vibe-signals/"
    echo "$close"
  } >> "$gitignore"
  echo "vibe: added managed runtime-exclusions block to $gitignore" >&2
}

# Shared-repos git ergonomics (AC6, task_017 cycle 1): the runtime manifest
# at /workspace/.vibe/shared-repos.manifest (one "name mode slug" line per
# mounted shared repo, written by the `vibe` launcher STRICTLY BEFORE
# `devcontainer up` in THIS SAME launch — see shared_repos_manifest_lines /
# the SHARED_REPOS_MANIFEST write in the launcher) lists what's bind-mounted
# at /repos/<name>. There's no pre-existing safe.directory mechanism in this
# codebase to mirror — /workspace itself has never needed one, since its
# ownership maps cleanly on the primary Mac platform. A shared-repo checkout
# gets one because it's a bind mount of a DIFFERENT host path owned by the
# same invoking user, and git's dubious-ownership check can still trip on
# the uid mapping a fresh mount presents inside the container. Runs on every
# container start; adds ONE literal per-repo `--add`-style entry (no `*`
# wildcard — a wildcard would trust every future bind, not just today's
# declared set) and de-duplicates first, since `git config --add` is not
# itself idempotent (it would append a second identical line on every
# restart otherwise). Reads the mount root from ${VIBE_REPOS_DIR:-/repos}
# (not a hardcoded /repos) so a smoke fixture can point this at a temp tree
# instead of the real container mount point.
#
# GIT_OPTIONAL_LOCKS=0 guidance (also AC6): shipped as a plain, constant
# containerEnv/remoteEnv entry in devcontainer.json rather than computed
# here — it's a fixed value, not derived from the manifest, and every other
# constant in this container (NODE_OPTIONS, CLAUDE_CONFIG_DIR, ...) is
# already set that way. Applied container-wide rather than scoped to just
# the ro shared checkouts: git optional locks are a read-path optimisation,
# never a correctness requirement, so disabling them everywhere is a safe
# simplification instead of per-repo plumbing that would need a matching
# ro/rw distinction of its own.
ensure_shared_repos_safe_directory() {
  local manifest="${VIBE_SHARED_REPOS_MANIFEST:-/workspace/.vibe/shared-repos.manifest}"
  [ -f "$manifest" ] || return 0
  local repos_root="${VIBE_REPOS_DIR:-/repos}"

  # Manifest lines are "name mode slug" (AC5); only the basename is needed
  # here, but mode/slug must still be consumed positionally so `name` gets
  # just the first field, not the whole line.
  local name dir mode slug
  # shellcheck disable=SC2034  # mode/slug consumed positionally, not used
  while read -r name mode slug; do
    [ -n "$name" ] || continue
    # Defense-in-depth charset guard (security-review, task_017 C1): trust in
    # the manifest rests on the launcher having written it this launch; if a
    # stale or hand-edited manifest smuggles a name with a slash or other
    # metacharacter, skip it rather than feed it to git config.
    case "$name" in
      *[!A-Za-z0-9._-]*|.*) continue ;;
    esac
    dir="$repos_root/$name"
    if ! git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$dir"; then
      git config --global --add safe.directory "$dir"
    fi
  done < "$manifest"
}

install_dir agents
install_dir commands
install_hooks
install_claude_md_fragments
install_brain2_skills
check_superpowers
check_sp_drift
ensure_project_gitignore
ensure_shared_repos_safe_directory
