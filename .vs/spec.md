# Spec: task_006 — /c host-watched clipboard bridge

**Revised after cycle-1 Spec Critic (iteration 1). 13 concerns resolved in this revision.**

## Task summary

Rewire the in-container `/copy` slash command to `/c` with zero-keystroke delivery to the Mac clipboard. The prior design (task_005) assumed `vibe-copy` — invoked from a Claude Code Bash tool call — could reach the user's terminal via OSC 52. Empirical test on 2026-04-23 proved this false: inside a Bash tool call, stdout redirects to a file, stderr to `/dev/null`, and `/dev/tty` resolves but isn't connected to Ghostty. OSC 52 embedded in assistant text is also sanitised by Claude Code. The only surviving leg today is the scratch-file fallback.

The new design moves the Mac-clipboard leg OUT of the container entirely: `/c` inside the container writes the code block to `$WORKSPACE/.vibe/copy-latest.txt` (visible on the host via the `workspaceMount` bind), and a **host-side watcher** spawned by the `vibe` launcher detects the change and runs `pbcopy` on the host. No Bash tool call from the skill, no OSC 52 dependency, no terminal plumbing inside the container.

Scope: host is macOS (`pbcopy`). Linux hosts are a no-op — the watcher self-disables on non-Darwin.

## Canonical process identity

To avoid ambiguity across the normative and test criteria, the watcher's process identity is defined ONCE here and referenced by number below:

> **[P]** The watcher is launched by `vibe` as a background job executing the script `vibe-copy-watcher.sh` with exactly one positional argument: the absolute `$WORKSPACE` path. Therefore every watcher process's `ps`/argv string contains, verbatim, the substring `vibe-copy-watcher.sh <WORKSPACE_PATH>` where the separator between the two tokens is a single space. The canonical match pattern used by both orphan-reap (`pkill -f`) and tests (`pgrep -f`) is:
>
> `pkill -f "vibe-copy-watcher\.sh ${WORKSPACE}\$"` (regex: `.sh`, literal space, workspace path escaped for regex, `$` end-of-line anchor)
>
> The end-of-line anchor prevents path-prefix collisions (e.g. `/proj` matching a running watcher for `/proj-extra`). Tests assert both the argv form and collision-freedom.

## Acceptance criteria

1. **File presence after rename.** `devcontainer/commands/c.md` exists in the repo; `devcontainer/commands/copy.md` does not exist in the repo. Both conditions must hold — AC17g explicitly tests absence of `copy.md`.

2. **Skill body drops `vibe-copy` invocation.** The happy path of `c.md` (code-block-found path) instructs the model to perform exactly ONE tool call: a `Write` to the scratch file. No `Bash` tool call is permitted in the happy path. Mentioning `!vibe-copy` in the UTF-8 note (AC5) as a user-typed fallback is allowed — that's prose, not a model instruction.

3. **Skill writes to the canonical scratch path.** `c.md` instructs the model to write the extracted code-block bytes directly to `/workspace/.vibe/copy-latest.txt` (hardcoded path; no `$VIBE_COPY_SCRATCH_DIR` indirection for the `/c` path — AC11 clarifies the relationship with the `vibe-copy` helper's env var). No `/tmp/copy-<ISO>.txt` intermediate step.

4. **Refusal message preserved.** `c.md` still emits the exact string `no prior code block to copy` when there is no prior assistant turn or no fenced block in it, and performs zero tool calls in that case.

5. **UTF-8 note preserved.** `c.md` retains a note explaining that the Write-tool hop is UTF-8-safe but not byte-safe for binary, and directs users to `!vibe-copy <file>` for binary-safe copy via the host shell.

6. **No Dockerfile change.** The rename propagates via the existing `COPY commands/ /usr/local/share/vibe/commands/` line — no Dockerfile edit is permitted or needed for the rename or the watcher. The watcher runs on the **host** only; it must NOT be `COPY`'d into the image. AC17h tests that the watcher script is not present at any path under `/usr/local/` in the built image (skipped on non-Docker CI).

7. **Stale `copy.md` in the persistent claude-config volume is deleted on container start.** `install-claude-extras.sh` removes retired vibe-shipped filenames from `$DEST_ROOT/commands/` before its copy loop. The retirement list is a static allowlist: `RETIRED_COMMANDS=("copy.md")`. The cleanup applies **exclusively to the `commands` destination directory** — the `agents` directory is untouched by the retirement mechanism. User-authored `*.md` files in `$DEST_ROOT/commands/` that were never on the vibe-shipped retirement list must NOT be deleted.

8. **Watcher spawns on vibe start on macOS.** When `vibe` runs on Darwin with `pbcopy` available, it:
   - **Defines `VIBE_REPO_DIR` explicitly** as `VIBE_REPO_DIR="$(dirname "$DEVCONTAINER_DIR")"`, placed after the existing `DEVCONTAINER_DIR` resolution block (lines 42–48 of current `vibe`)
   - `mkdir -p "$WORKSPACE/.vibe"` before spawning (watcher polls a file in this dir; path must exist)
   - Reaps any orphan watcher for this **exact** `$WORKSPACE` from a prior crashed session using the canonical pattern [P]: `pkill -f "vibe-copy-watcher\.sh ${WORKSPACE}\$" 2>/dev/null || true`. The end-of-line anchor (`$`) prevents path-prefix collisions on sibling workspaces
   - Launches `"$VIBE_REPO_DIR/vibe-copy-watcher.sh" "$WORKSPACE"` as a background job (`&`)
   - Captures the watcher PID into a shell variable (e.g. `WATCHER_PID=$!`) for PID-based cleanup

9. **Watcher pbcopies on change.** When `$WORKSPACE/.vibe/copy-latest.txt` is created or its mtime changes, the watcher reads it (via a tempfile copy — see implementation notes) and pipes the contents to the copy command within **≤ 1 second** of the write. Watcher tolerates the file not existing at spawn time (baseline mtime = 0; first write triggers copy). Watcher MUST NOT re-copy a file whose mtime has not changed since the last copy.

10. **`VIBE_COPY_CMD` override is normative.** The watcher MUST read `VIBE_COPY_CMD` from its environment and use its value as the copy command, defaulting to `pbcopy` when unset or empty. This hook enables Linux-CI testability (AC17d). The watcher must tolerate the override command failing without dying — a failed copy is logged to `/dev/null` and the loop continues.

11. **Polling fallback is the default.** The watcher uses `fswatch` only if `command -v fswatch` succeeds; otherwise it falls back to a `stat`-based polling loop with interval ≤ 1 second. No dependency on any non-base-macOS tool. The loop MUST be robust against a file disappearing between the `stat` check and the subsequent read (e.g. user deletes the scratch file mid-loop) — achieved via `|| true` / explicit conditional guards, not by relying on `set -e` to skip iterations.

12. **Watcher dies on vibe exit.** After `vibe` returns (normal exit, Ctrl+C / SIGINT, SIGTERM, or `claude` exiting non-zero), `pgrep -f "vibe-copy-watcher\.sh ${WORKSPACE}\$"` returns no matching PID. Cleanup is via a **mandatory EXIT trap** wired around the `devcontainer exec ...` call, with **PID-based** `kill "$WATCHER_PID"` (not `pkill -f`, to eliminate residual collision risk). INT and TERM traps are optional reinforcement — bash's `set -e` termination already triggers EXIT. The final line's `exec` keyword MUST be removed so the trap fires.

13. **Trap body must preserve vibe's exit code.** All commands in the EXIT trap body MUST be guarded with `|| true` (or equivalent non-failure suppression) so a failed `kill` (e.g. watcher already dead) does not alter `vibe`'s exit status. Example: `trap 'kill "$WATCHER_PID" 2>/dev/null || true' EXIT`.

14. **Exit code propagation preserved.** If `claude` exits with code N, `vibe` exits with code N. `set -euo pipefail` (already at the top of `vibe`) propagates non-zero; the trap body (AC13) does not clobber the code.

15. **Multi-session isolation.** Two `vibe` sessions on different `$WORKSPACE` paths run independent watchers distinguished by the canonical pattern [P]. `/c` in one session does NOT pbcopy the other session's scratch file. Per-session watcher termination in one session does NOT kill the watcher in the other (verified by AC17i — path-prefix collision test). Acceptable semantics: last `/c` across all sessions wins the Mac clipboard (user has accepted this).

16. **Non-Darwin hosts are no-ops for the watcher.** On Linux (including smoke-test.py CI runs), `vibe` does NOT spawn a watcher and does not error. The watcher script itself exits 0 immediately when `uname` is not `Darwin` — this is its first guard, before argument validation. The `/c` skill still writes the scratch file (which sits harmlessly on the host).

17. **`code-check.py` passes.** No new shellcheck warnings introduced in `vibe`, the new `vibe-copy-watcher.sh`, or any modified `.sh` file. Run with `python3 code-check.py`.

18. **Existing `smoke-test.py` tests pass.** All pre-existing checks that don't reference `copy.md` stay green. Tests that reference `copy.md` (the `COPY_MD` constant, `test_copy_slash_command_synced`, `test_copy_slash_command_body_matches_spec`, and the `copy.md`-mention assertions inside `test_dockerfile_installs_vibe_copy`) are updated in place to the new filename and new body. Content assertions updated to match the rewritten skill: the "mentions `vibe-copy`" assertion is removed or weakened (the body may mention `vibe-copy` in the UTF-8 note but no longer as a Bash-tool-call instruction); the scratch-path assertion stays; the refusal-message assertion stays.

19. **New smoke tests.** Tester adds at minimum the following checks. All must be runnable on a Linux CI host (no `pbcopy`, no macOS):

    a. **Extras-sync deletes retired `copy.md`.** Seed `dest/commands/copy.md` with sentinel content. Run `install-claude-extras.sh` with a fixture `VIBE_EXTRAS_SRC_ROOT` whose `commands/` dir contains only `c.md`. Assert: after sync, `dest/commands/copy.md` does NOT exist, and `dest/commands/c.md` exists with fixture content.
    b. **Extras-sync preserves user-authored commands.** Seed `dest/commands/my-custom.md` with user content. Run sync with fixture SRC containing only `c.md`. Assert: `my-custom.md` still exists with original content; `c.md` synced.
    c. **Extras-sync does NOT touch `agents/` via retirement logic.** Seed `dest/agents/some-retired-agent.md` with sentinel content. Run sync with fixture SRC containing only `commands/c.md` and `agents/other.md`. Assert: `dest/agents/some-retired-agent.md` still exists (retirement list applies to commands only, as per AC7).
    d. **Watcher is a no-op on non-Darwin.** Invoke `vibe-copy-watcher.sh <tempdir>` directly on the Linux test host. Assert: exit code 0 AND immediately after exit, `pgrep -f "vibe-copy-watcher\.sh <tempdir>\$"` returns empty (no lingering process). Use a 1-second pgrep delay to give the shell time to exit fully.
    e. **Watcher polling detects a scratch-file change (Linux-runnable via `VIBE_COPY_CMD`).** Strategy: patch/override the watcher's platform guard for the test (simplest: set env var `VIBE_COPY_WATCHER_FORCE=1` that bypasses the Darwin check, ONLY for testing — this is an additional normative requirement below, AC20). Then: create tempdir `td/.vibe/`, set `VIBE_COPY_CMD='tee td/sentinel.txt >/dev/null'`, launch watcher in background with workspace=`td`, wait 0.5s, write `hello-c\n` to `td/.vibe/copy-latest.txt`, wait 1.5s (at least 3 polling intervals at 0.5s), assert `td/sentinel.txt` contents == `hello-c\n`. THEN: send SIGTERM to watcher PID, wait 1s, assert `pgrep -f` returns empty.
    f. **`c.md` body matches new spec.** `c.md` file exists; body contains the exact string `/workspace/.vibe/copy-latest.txt`; body contains the exact string `no prior code block to copy`; body mentions UTF-8; body does NOT contain a Bash-tool instruction to invoke `vibe-copy` (i.e. no line that says "Use the Bash tool to run: `vibe-copy`" or equivalent).
    g. **`copy.md` is absent from the repo.** Assert `not (REPO / "devcontainer" / "commands" / "copy.md").exists()`.
    h. **`vibe` final-line `exec` dropped.** Grep `vibe`: assert no line matches the regex `^exec devcontainer exec` AND assert at least one line matches the regex `^devcontainer exec ` (with leading anchor, no `exec` prefix, space after command).
    i. **Multi-session path-prefix collision test.** Spawn two watchers with workspaces `$TMP/proj` and `$TMP/proj-extra`. Use `VIBE_COPY_WATCHER_FORCE=1` to bypass Darwin guard. Run the orphan-reap command for `$TMP/proj`: `pkill -f "vibe-copy-watcher\.sh $TMP/proj\$"`. Assert: the `$TMP/proj` watcher is killed; the `$TMP/proj-extra` watcher is still alive. Then tear down.
    j. **`vibe` exits with the inner command's exit code (regression guard for dropping `exec`).** Shim `devcontainer` in a tempdir prepended to PATH to emit exit code 7. Run `vibe` in that env with all other checks stubbed enough to reach the launch line. Assert `vibe` returns 7. (If fully shimming `vibe`'s full preflight is infeasible, split the assertion into a narrow unit test of the exec-drop property: e.g. source-test the final launch block in isolation — Tester's choice of approach.)

20. **`VIBE_COPY_WATCHER_FORCE` test hook.** The watcher script MUST honor an environment variable `VIBE_COPY_WATCHER_FORCE`: when set to `1`, it skips the `uname` Darwin check (but NOT the `pbcopy` / `VIBE_COPY_CMD` availability check). This enables AC19e and AC19i to run on Linux CI. This hook is documented in `vibe-copy-watcher.sh` as a test-only override with a one-line comment.

21. **TODO.md is updated.** Before Generator's implementation completes: a new `## Open` entry tracks task_006. On `/vs` pass: the entry is moved to `## Done` with a one-line summary. The existing task_005 Done entry gets a one-line amendment noting its OSC-52-from-tool-call design was superseded by the host-watcher approach on 2026-04-23 after the stdio-sandbox finding. No other rewrite of history.

## Out of scope

- Linux / Windows clipboard targets (`xclip`, `xsel`, Windows `clip.exe`). Darwin-only for the clipboard leg. Linux hosts get the scratch file and nothing else.
- Binary-safe copy via `/c`. UTF-8 text only. Users wanting exact bytes use `!vibe-copy <file>` via the host shell.
- In-container `/c` for non-vibe Claude Code installs — no watcher means the scratch file is a dead drop (acceptable, documented).
- Removing `devcontainer/vibe-copy.sh` or `/usr/local/bin/vibe-copy` from the image. The shell helper stays.
- Changing `vibe-copy.sh`'s `$VIBE_COPY_SCRATCH_DIR` env var behaviour. `/c` hardcodes its scratch path to `/workspace/.vibe/copy-latest.txt` (AC3) and does NOT read `$VIBE_COPY_SCRATCH_DIR`. The two paths (skill path and helper path) are independent; if a user has `VIBE_COPY_SCRATCH_DIR` set, `!vibe-copy <file>` will write somewhere the watcher doesn't look — user is responsible for not setting this var in a vibe session if they want the watcher to pick it up.
- User notification of `/c` completion (toast, bell). Mac clipboard simply gets the content.
- CLI flag to disable the watcher (`vibe --no-copy-watcher`). Not needed; watcher is cheap and silent.
- Auto-starting the watcher when running Claude Code outside vibe.
- Changing task_005's Done entry beyond a single appended amendment line.
- Backward-compat shim that keeps `/copy` alive alongside `/c`. Clean break.
- Adding the watcher to the container image (`COPY` line). Watcher is host-only (AC6).

## Review focus / Test location

Test location: `smoke-test.py` at repo root. New tests follow the existing `test_<area>_<behavior>` naming convention.

**Tester MUST NOT edit any file outside `smoke-test.py`** plus tempdir fixtures it creates at runtime.

Additional scrutiny Tester should apply:
- shellcheck cleanliness of `vibe-copy-watcher.sh` and the watcher-launch block in `vibe`
- Quoting of `$WORKSPACE` (paths with spaces, regex metacharacters)
- The canonical `pgrep`/`pkill` pattern [P] from the header — escape special regex chars in the workspace path when building the pattern in tests (`re.escape` in Python when building the expected argv string for assertions)
- Atomicity of read vs concurrent rewrite: the watcher uses an intermediate tempfile copy before piping to the copy command
- AC19d must verify actual process exit (pgrep empty after 1s), not just the watcher's exit code 0
- AC19e timing: at least 1.5s between writing the scratch file and sending SIGTERM, to give three polling cycles at 0.5s

## Proposed budget

**2 cycles.** Rationale: multi-file but bounded. Cycle 1: rename + skill rewrite + extras-sync cleanup + watcher script + vibe-launcher integration + exec-drop + all 10 new smoke tests (AC19a–j). Cycle 2 reserved for the likely failure mode — shell edge cases in the watcher, macOS-ism / Linux-CI drift, or a missed out-of-scope creep. Cycle 3 would signal a spec defect.

## Implementation notes (non-normative)

Suggestions; Generator may deviate if ACs can still be met.

- Watcher lives at repo root as `vibe-copy-watcher.sh` (peer to `vibe`). The `vibe` launcher derives `VIBE_REPO_DIR="$(dirname "$DEVCONTAINER_DIR")"` after the existing symlink-resolution block.

- Watcher skeleton:
  ```
  #!/usr/bin/env bash
  # vibe-copy-watcher.sh — host-side polling watcher that pbcopies the /c scratch
  # file on change. Runs on the Mac; no-op on Linux.
  # VIBE_COPY_WATCHER_FORCE=1 bypasses the Darwin check for testing only.
  set -euo pipefail

  if [ "${VIBE_COPY_WATCHER_FORCE:-0}" != "1" ]; then
    [[ "$(uname)" == "Darwin" ]] || exit 0
  fi

  COPY_CMD="${VIBE_COPY_CMD:-pbcopy}"

  [ $# -eq 1 ] || { echo "usage: vibe-copy-watcher.sh WORKSPACE_ABS_PATH" >&2; exit 2; }
  WORKSPACE="$1"
  CLIP="$WORKSPACE/.vibe/copy-latest.txt"
  mkdir -p "$(dirname "$CLIP")"

  TMP=$(mktemp)
  trap 'rm -f "$TMP"' EXIT

  last=0
  if command -v fswatch >/dev/null 2>&1; then
    fswatch -0 "$(dirname "$CLIP")" | while IFS= read -r -d '' _; do
      [ -s "$CLIP" ] || continue
      cur=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)
      if [ "$cur" != "$last" ]; then
        last="$cur"
        cp "$CLIP" "$TMP" 2>/dev/null && $COPY_CMD < "$TMP" 2>/dev/null || true
      fi
    done
  else
    while sleep 0.5; do
      [ -s "$CLIP" ] || continue
      cur=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)
      if [ "$cur" != "$last" ]; then
        last="$cur"
        cp "$CLIP" "$TMP" 2>/dev/null && $COPY_CMD < "$TMP" 2>/dev/null || true
      fi
    done
  fi
  ```
  Note the `|| true` on the cp/copy compound — prevents `set -e` killing the watcher on transient file-disappearance races. Uses both BSD `stat -f` and GNU `stat -c` for portability between macOS and Linux test hosts.

- `vibe` integration block (placed immediately before the current `exec devcontainer exec ...` line):
  ```
  VIBE_REPO_DIR="$(dirname "$DEVCONTAINER_DIR")"
  WATCHER_PID=""
  if [[ "$(uname)" == "Darwin" ]] && command -v pbcopy >/dev/null 2>&1; then
    mkdir -p "$WORKSPACE/.vibe"
    pkill -f "vibe-copy-watcher\.sh ${WORKSPACE}\$" 2>/dev/null || true
    "$VIBE_REPO_DIR/vibe-copy-watcher.sh" "$WORKSPACE" &
    WATCHER_PID=$!
    trap 'kill "$WATCHER_PID" 2>/dev/null || true' EXIT
  fi
  ```
  Note: `VIBE_REPO_DIR` derivation happens inside the Darwin branch if preferred, but defining it globally is fine and future-proofs other host-side helpers.

- Change final `exec devcontainer exec ...` to `devcontainer exec ...` (drop the `exec` keyword, keep all arguments identical).

- `install-claude-extras.sh` retired-list cleanup:
  ```
  install_dir() {
    local kind="$1"
    local src="$SRC_ROOT/$kind"
    local dest="$DEST_ROOT/$kind"

    [ -d "$src" ] || return 0
    mkdir -p "$dest"

    # Commands-only retirement: remove files that vibe used to ship but no
    # longer does. Allow-listed; user-authored files in dest are untouched.
    if [ "$kind" = "commands" ]; then
      local retired
      for retired in copy.md; do
        rm -f "$dest/$retired"
      done
    fi

    local file name
    for file in "$src"/*.md; do
      [ -e "$file" ] || continue
      name=$(basename "$file")
      cp -f "$file" "$dest/$name"
    done
  }
  ```
