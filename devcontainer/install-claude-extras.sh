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
# _ssh_marker_opted_in — true iff THIS project is authorised to drop the
# per-action SSH ask (i.e. omit the ssh-discipline.md fragment). Runs
# IN-CONTAINER, so it cannot source the host launcher — it MIRRORS the
# launcher's _op_opted_in semantics (see /workspace/vibe) and the two must
# stay semantically paired (smoke-test pins this). Two opt-in signals:
#   - VIBE_SSH_AUTO=1 (plumbed from ~/.vibe/config via containerEnv) —
#     machine-global, and the escape hatch for genuinely non-git projects.
#   - an UNTRACKED /workspace/.vibe-allow-ssh marker — per-project.
# The marker is honoured ONLY with positive proof it is a local, untracked
# file in a verifiable git work tree — fail CLOSED otherwise (the ask is
# kept, nothing breaks). A marker COMMITTED to the repo is refused (a PR
# must not be able to grant every clone autonomous SSH), and a marker where
# git can't confirm tracking state (no git binary, not a work tree, git
# error) is also refused — a ZIP/tarball distribution shipping the marker
# must not silently disable the ask. VIBE_SSH_MARKER_WS is a test override.
_ssh_marker_opted_in() {
  # The workspace override is honoured ONLY under the smoke harness
  # (VIBE_SMOKE=1) — a security-relevant path must not be relocatable by
  # ambient env if the containerEnv plumbing ever broadens.
  local ws=/workspace
  if [ -n "${VIBE_SSH_MARKER_WS:-}" ] && [ "${VIBE_SMOKE:-}" = "1" ]; then
    ws="$VIBE_SSH_MARKER_WS"
  fi
  if [ "${VIBE_SSH_AUTO:-0}" = "1" ]; then
    return 0
  fi
  if [ ! -f "$ws/.vibe-allow-ssh" ]; then
    return 1
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "  ⚠ .vibe-allow-ssh present but git is unavailable to verify it — SSH opt-in refused (fail closed). Set VIBE_SSH_AUTO=1 in ~/.vibe/config to opt in without a marker." >&2
    return 1
  fi
  # String-compare the output — rev-parse exits 0 printing "false" from
  # inside a .git dir.
  if [ "$(git -C "$ws" rev-parse --is-inside-work-tree 2>/dev/null)" != "true" ]; then
    echo "  ⚠ .vibe-allow-ssh present but this workspace isn't a verifiable git work tree — SSH opt-in refused (a marker in a non-git download must not disable the per-action ask). Set VIBE_SSH_AUTO=1 in ~/.vibe/config for a trusted non-git project." >&2
    return 1
  fi
  # :(icase) — the marker's -f test resolves through a case-folding
  # filesystem on macOS bind mounts, so a repo committing .Vibe-Allow-SSH
  # would otherwise satisfy -f while dodging a case-sensitive index lookup.
  if git -C "$ws" ls-files --error-unmatch ':(icase).vibe-allow-ssh' >/dev/null 2>&1; then
    echo "  ⚠ .vibe-allow-ssh is COMMITTED to this repo — ignored (SSH opt-in must be a local, untracked file; a committed marker would grant autonomous SSH to every clone). 'touch .vibe-allow-ssh' locally, untracked, then relaunch." >&2
    return 1
  fi
  # Positive proof of untrackedness — ls-files --error-unmatch exits 1 for
  # "not tracked" AND for any git error, so its failure alone must not open
  # the gate. -o without --exclude-standard: the marker is gitignored by the
  # managed block, and ignored files must still be listed here.
  if [ -z "$(git -C "$ws" ls-files -o -- ':(icase).vibe-allow-ssh' 2>/dev/null)" ]; then
    echo "  ⚠ .vibe-allow-ssh could not be positively verified as an untracked file — SSH opt-in refused (fail closed). Set VIBE_SSH_AUTO=1 in ~/.vibe/config to opt in without a marker." >&2
    return 1
  fi
  return 0
}

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
  # for this project — VIBE_SSH_AUTO=1, or an UNTRACKED .vibe-allow-ssh
  # marker with fail-closed verification (see _ssh_marker_opted_in above).
  local fragments=()
  if [ -d "$src_dir" ]; then
    local f
    while IFS= read -r f; do
      [ -e "$f" ] || continue
      if [ "$(basename "$f")" = "ssh-discipline.md" ]; then
        if _ssh_marker_opted_in; then
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
  # Throttle: at most one upstream probe per 24h across ALL projects — the
  # probe hits api.github.com unauthenticated (60 req/h per IP, shared) and
  # can hold postStart for up to its 10s curl cap. Stamp lives in
  # $DEST_ROOT (the shared vibe-claude-config volume — correct scope:
  # sp.md is shared, not per-project). Stamp is written on EVERY probe
  # attempt, before the checker runs: this guarantees <=1 upstream call
  # per window even when the network is down (a failed probe burns the
  # day's slot — drift news can wait a day; hammering a dead network on
  # every launch cannot). An unwritable $DEST_ROOT skips stamping but
  # never blocks the probe or container start.
  local stamp="$DEST_ROOT/.sp-drift-checked"
  _sp_drift_due "$stamp" || return 0
  date -u +%s > "$stamp" 2>/dev/null || true
  SP_MD="$DEST_ROOT/commands/sp.md" "$checker" || true
}

# _sp_drift_due <stamp_file> — pure read-only predicate: exits 0 iff the
# drift probe should run now. Not due only when a readable stamp holds a
# plausible epoch (digits, not in the future) younger than the window.
# VIBE_SP_DRIFT_MAX_AGE_SECS overrides the 86400s default (0 = always due;
# garbage collapses to the default). Every malformed edge — missing or
# unreadable stamp, garbage bytes, future-dated epoch — counts as stale
# (due), never as an error.
_sp_drift_due() {
  local stamp="${1:-}" max_age now last
  max_age="${VIBE_SP_DRIFT_MAX_AGE_SECS:-86400}"
  case "$max_age" in ''|*[!0-9]*) max_age=86400 ;; esac
  if [ "$max_age" -eq 0 ]; then
    return 0
  fi
  if [ -z "$stamp" ] || [ ! -r "$stamp" ]; then
    return 0
  fi
  now=$(date -u +%s)
  last=$(head -c 32 "$stamp" 2>/dev/null | tr -cd '0-9') || last=""
  if [ -n "$last" ] && [ "$last" -le "$now" ] && [ $(( now - last )) -lt "$max_age" ]; then
    return 1
  fi
  return 0
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
    echo ".vibe-allow-ssh"
    echo ".vibe-allow-op"
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

# Sync the content-guard git hooks (task_019) into $DEST_ROOT/vibe-git-hooks/
# (chmod +x on the scanner + three wrappers) and point git's global
# core.hooksPath at that directory, so pre-commit/commit-msg/pre-push fire
# for every repo the container touches, INCLUDING rw /repos/* shared repos
# and (in the gardener) brain2 (core.hooksPath is --global, same scope as
# ensure_shared_repos_safe_directory's safe.directory entries above — see
# .vs/spec.md's "Note on core.hooksPath global scope"). Idempotent: re-runs
# just re-copy + re-chmod + re-set the same config value. Unlike commands/
# agents, hook files under vibe-git-hooks/ are enforcement code, not
# user-editable content, so there is no "leave user edits alone" carve-out.
install_git_hooks() {
  local src="$SRC_ROOT/git-hooks"
  local dest="$DEST_ROOT/vibe-git-hooks"

  [ -d "$src" ] || return 0
  mkdir -p "$dest"

  local file name
  for file in "$src"/*; do
    [ -f "$file" ] || continue
    name=$(basename "$file")
    cp -f "$file" "$dest/$name"
    chmod +x "$dest/$name"
  done

  git config --global core.hooksPath "$dest"
}

install_dir agents
install_dir commands
install_hooks
install_git_hooks
install_claude_md_fragments
install_brain2_skills
check_superpowers
check_sp_drift
ensure_project_gitignore
ensure_shared_repos_safe_directory
