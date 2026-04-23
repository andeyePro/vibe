# spec — task_004: cross-org learning library for vibe

## Task summary

Add an **opt-in, host-only-capture** cross-org learning library so `vibe` users can record and reference abstract patterns / lessons across all their repos without leaking project content. Capture is **host-only** for v1 (in-container slash command deferred to a follow-up): user runs `vibe learn "<pattern>"` from a host shell; vibe shows the exact bytes that will be saved and requires explicit `y` confirmation; nothing is read from session state. The library lives at a **user-chosen absolute path** (private local dir, or a user-controlled git repo for "public" sharing). When opted in, the library is bind-mounted **read-only** into every vibe container at `/learnings` so Claude can `ls` / `grep` it while working. Per-project opt-out via marker file. Default: completely off — until `vibe learn --init` is run, no config, no mount, no behavior change.

**Opt-in is per-user, universal-by-default once enabled.** A single `vibe learn --init` opts the user in; every vibe invocation thereafter — existing projects, brand-new projects — automatically participates (mounts `/learnings`, capture works from any cwd). To exclude a specific project, the user places a `.vibe-no-learn` marker in its root. There is **no per-project opt-in step**; that would be hostile UX and is explicitly out of scope.

Anonymization is the **user's responsibility**: vibe captures only what the user explicitly types, presents it back verbatim, asks confirm. No regex scrubbing, no LLM pass, no auto-extraction from sessions — those would be leakier than user-controlled text.

## Acceptance criteria

### Config & init

1. **Config file** at `$HOME/.vibe/learning.config`. Format: one `KEY="VALUE"` per line, no other content. Recognized keys (exactly these four, case-sensitive): `VIBE_LEARNING_ENABLED` (`true` or `false`), `VIBE_LEARNING_PATH` (absolute host path), `VIBE_LEARNING_VISIBILITY` (`private` or `public`), `VIBE_LEARNING_GIT_REMOTE` (string; only meaningful when visibility is `public`).

2. **Strict parser** (no `source`/eval): `learning_load` reads the config line-by-line and accepts only lines matching the regex `^[A-Z_]+="[^"\\$\`]*"$` AND whose key is in the recognized set above. Any other line is silently ignored. Implemented via a `python3 -c "..."` one-shot or pure-bash parsing — never `source` and never `eval`. After parsing, vibe exports the four vars (or leaves them empty if not present). Verifiable: a config file containing `VIBE_LEARNING_ENABLED="true"; rm -rf /tmp/x"` does NOT execute the rm.

3. **`vibe learn --init`** is interactive:
   - Prompts for absolute library path (rejects relative paths or paths whose parent doesn't exist; if the path itself doesn't exist, offers `mkdir -p`).
   - Prompts for visibility: `private` (default on Enter) or `public`.
   - If `public`: prompts for git remote name; validates by running `git -C <path> remote` and checking the entered name appears in the output. If the path is not a git repo, refuses with: `vibe learn: <path> is not a git repo. Run 'git init' there and add a remote, then re-run vibe learn --init`.
   - Writes `$HOME/.vibe/learning.config` with `chmod 600`, contents: the four `KEY="VALUE"` lines including `VIBE_LEARNING_ENABLED="true"`.
   - Refuses to overwrite an existing config that has `VIBE_LEARNING_ENABLED="true"` unless `--reinit` is passed.

4. **Default-off behavior:** with no config file, OR config present but `VIBE_LEARNING_ENABLED!="true"`:
   - No mount logic runs (vibe behaves byte-identically to the pre-task `vibe` for non-learn invocations).
   - `vibe learn "<text>"` (without `--init` first) exits 1 with stderr message `vibe learn: not initialized — run 'vibe learn --init' first` and writes nothing.
   - No new file in `~/.claude/commands/` is added by the install-claude-extras flow (this task ships **no** new in-container slash command).

### Mount mechanism

5. **Mount via generated override config:** when opt-in is active AND the project is not opted out (per AC10), vibe materializes a per-invocation devcontainer config at `$HOME/.vibe/run/devcontainer-<sha1-of-workspace>.json` (the run dir is created `mkdir -p`). The generated file is the contents of `$DEVCONTAINER_DIR/devcontainer.json` with the `mounts` array extended by `{"source": "<VIBE_LEARNING_PATH>", "target": "/learnings", "type": "bind", "readonly": true}`. Vibe passes `--override-config $HOME/.vibe/run/devcontainer-<sha1>.json` to **both** the `devcontainer up` AND the subsequent `devcontainer exec` invocations (replacing the existing `--override-config` arg in each). JSON manipulation uses `python3` (already a vibe dep — see `ensure_docker_hints_off`) to avoid string-edit fragility.

6. **Read-only mount enforced at container layer:** `readonly: true` in the generated mounts entry means the container sees `/learnings` as read-only regardless of host permissions. AC test (mechanical, no real docker): inspect the generated JSON file and assert the new mount entry has `"readonly": true`.

### `vibe learn` dispatch & capture

7. **Dispatch point:** in the launcher, immediately after the `VIBE_SOURCE_ONLY=1` early-return guard and BEFORE the existing `--*` flag-parser loop, vibe checks `if [ "${1:-}" = "learn" ]`. If so, it dispatches to the `learning_handle_subcommand "$@"` function (which consumes `$@`, runs the appropriate sub-flow, and exits the script). The `--*` flag loop, workspace resolution, preflight, image build, GitHub setup, and container launch are NOT entered when the first arg is `learn`.

8. **`vibe learn "<pattern>"`** capture flow (host-side, requires opt-in per AC1–4):
   - If invoked from a cwd inside a project containing `.vibe-no-learn` in any ancestor up to the cwd's filesystem-root walk OR matching `$WORKSPACE/.vibe-no-learn` if `$WORKSPACE` is somehow set, refuse per AC10. (Practical implementation: walk from cwd toward `/`, stop at first dir containing `.vibe-no-learn`; if found, refuse. Stop the walk at `$HOME` to avoid false positives from a `.vibe-no-learn` placed maliciously high.)
   - Compute filename: `<VIBE_LEARNING_PATH>/<UTC ISO8601 timestamp>-<6-char lowercase hex>.md`. Timestamp from `date -u +%Y-%m-%dT%H:%M:%SZ`. Random suffix from `head -c 3 /dev/urandom | xxd -p` (or equivalent portable form pinned in the helper contract).
   - Compose entry body via `learning_format_entry` (see AC12).
   - Print to stderr: `Will save to <full_path>:` then `----` then the entry body then `----` then `Confirm? [y/N]: ` and read one line from stdin.
   - On exact `y` (case-insensitive, trimmed): write the file, then proceed to AC9 (push prompt) only if visibility is `public`.
   - On any other input INCLUDING EOF (stdin closed before any input): exit 0 with stderr `vibe learn: cancelled, nothing written`. **EOF must default to cancel.** Verifiable test: `printf '' | vibe learn "x"` writes nothing and exits 0.

9. **Public-mode push prompt** (only when AC8 wrote a file AND `VIBE_LEARNING_VISIBILITY="public"`):
   - Print to stderr `Push to '<remote>'? [y/N]: ` and read from stdin.
   - On exact `y`: in order, run `git -C "$VIBE_LEARNING_PATH" add "<new_file>"`, then `git -C "$VIBE_LEARNING_PATH" commit --file=<tempfile>` where `<tempfile>` contains the output of `learning_commit_message <pattern>` (see AC12), then `git -C "$VIBE_LEARNING_PATH" push <remote>`. The `--file` form (NOT `-m`) is mandatory: it eliminates shell-arg injection through the pattern. Tempfile is created with `mktemp` and **registered for cleanup via `trap '<rm cmd>' EXIT INT TERM`** before any git command runs, so an interrupt during `git push` does not leak the message to disk.
   - On any other input including EOF: no git ops; exit 0 (entry is saved locally; user can commit manually later).
   - On any git failure (non-zero exit): print the failing command's stderr and exit 0 (the entry is saved locally; we don't lose data on push failure).

10. **`VIBE_LEARNING_VISIBILITY="private"`**: AC9 is fully skipped — no push prompt, no git invocation, `VIBE_LEARNING_GIT_REMOTE` not read.

### Per-project opt-out

11. **Marker file `.vibe-no-learn`** at `$WORKSPACE` root suppresses the `/learnings` mount for that project's vibe session (AC5 mount logic checks for the marker and skips generating the override config OR generates it without the learning mount). Empty file is sufficient — content is ignored. AC8 capture refusal (above) implements the marker-walk for the host-side `vibe learn` invocation.

### Help & banner

12. **Help and banner**:
   - `vibe --help` lists `vibe learn "<pattern>"` and `vibe learn --init` with one-line descriptions each.
   - When opt-in active AND project not opted out, vibe's launch banner includes a line `learn   : <visibility> @ <path>` (alongside `project`, `path`, `github`, `hooks`, `extras`).
   - When NOT opted in OR project opted out, banner does not include the `learn` line and behaves identically to the pre-task banner (banner-text regression check).

### Security invariants (every one is a hard fail if violated)

13. **Hard invariants** — Tester writes one assertion per:
   - Generated mount entry always has `"readonly": true`.
   - No `vibe learn` write occurs without literal `y` from confirm prompt (EOF, empty, `n`, anything else → no write).
   - No `git` command runs in private mode (verifiable via fake-`git` PATH stub that records invocations).
   - No `git` command runs in public mode without an explicit `y` from the push prompt.
   - vibe NEVER reads `~/.claude/projects/`, `*.jsonl`, or any session state during `learn` (verifiable: tester runs `vibe learn` with `~/.claude/` containing fixture files; assertion that none of those file paths appear in any subprocess stdin/stdout/log produced by the run).
   - `~/.vibe/learning.config` is created with `chmod 600`; AC test inspects mode bits.
   - `learning_load` does NOT execute shell injected via the config (test: write a config file with `VIBE_LEARNING_ENABLED="true"\nVIBE_LEARNING_PATH="/tmp"; touch /tmp/vibe-injection-canary"` and assert the canary is NOT created after `learning_load` runs).
   - Marker-walk stops at `$HOME` (test: place `.vibe-no-learn` at `/tmp/foo/.vibe-no-learn` with `$HOME=/tmp/foo/bar/baz`; assert capture from `/tmp/foo/bar/baz` is NOT blocked).
   - **`$HOME` unset is fail-safe:** if `$HOME` is unset or empty, `learning_project_opted_out` exits 0 (i.e. treat as "opted out") rather than walking to `/`. Test: invoke with `env -i HOME= vibe learn "x"` style and assert no write occurs.

### Helper-function exposure (testable via `VIBE_SOURCE_ONLY=1`)

14. **Helpers defined BEFORE the `VIBE_SOURCE_ONLY=1` early-return guard**, with these contracts:
   - `learning_config_path` — echoes `$HOME/.vibe/learning.config`. No args.
   - `learning_load` — strict-parses the config file, exports the four vars (or unsets them if missing/invalid). Never `source`, never `eval`. No prompts. Returns 0 always (silent on missing config).
   - `learning_is_enabled` — exits 0 iff loaded config has `VIBE_LEARNING_ENABLED="true"` AND `VIBE_LEARNING_PATH` is non-empty AND points at an existing directory. Silent.
   - `learning_project_opted_out <walk_start_abs_path>` — walks from `<walk_start_abs_path>` upward toward `/`, stopping at `$HOME` or the first dir containing `.vibe-no-learn`; exits 0 if marker found (and walk did not exceed `$HOME`) OR if `$HOME` is unset/empty (fail-safe: treat as opted-out); exits 1 otherwise. Silent.
   - `learning_should_mount <workspace_abs_path>` — exits 0 iff `learning_is_enabled` AND NOT `learning_project_opted_out <workspace_abs_path>`. Silent.
   - `learning_entry_path <library_abs_path> <iso8601> <rand6_hex>` — pure string composition: echoes `<library_abs_path>/<iso8601>-<rand6_hex>.md`. No filesystem, no docker.
   - `learning_format_entry <iso8601> <pattern>` — pure: echoes `# <iso8601>\n\n<pattern>\n` (literal `\n` are real newlines). No I/O.
   - `learning_commit_message <pattern>` — pure: echoes `learn: ` + the first 60 chars of `<pattern>` after replacing newlines with single spaces and collapsing runs of whitespace to one space. No shell-metachar escaping needed because the message is delivered to git via `--file=<tempfile>` not `-m`.
   - `learning_render_devcontainer_config <src_json_path> <dst_json_path> <library_abs_path>` — reads `<src>`, adds the learning mount entry to its `mounts` array, writes `<dst>`. Uses `python3 -c "..."` for JSON safety. No prompts.
   - `learning_handle_subcommand <args...>` — the dispatcher for `vibe learn ...`. Top-level handler called by AC7. Routes `--init` / `--reinit` / `<pattern>` to internal sub-functions. Returns the script's exit code via `exit` (not `return`).

### Build & regression

15. **`python3 code-check.py`** passes (shellcheck clean) on the modified `vibe`.

16. **`python3 smoke-test.py`** — every pre-existing test (count from `main()` in current `smoke-test.py`) continues to pass with no modifications. Regression gate.

## Out of scope

- **In-container `/learn` slash command** — deferred to follow-up TODO (host-only capture this iteration; eliminates the readonly-mount-vs-write contradiction and the install-claude-extras-can't-see-opt-in problem).
- Any auto-extraction or scraping from sessions, `.jsonl` files, conversation history, env vars, or vibe internal state.
- LLM-based or regex-based "auto-anonymization" of user input.
- Multi-library support — exactly one library per user.
- Editing or deleting existing entries via `vibe learn` (append-only; user can manually edit files in a private library; for public use the normal git workflow).
- Search / browse UX inside the container — `/learnings` is a flat dir.
- Cross-user library merging or peer-to-peer sync.
- A daemon, watcher, or hook that triggers capture automatically.
- Modifying `init-firewall.sh`, the Dockerfile, the existing postStart sequence, or `install-claude-extras.sh`.
- Modifying `code-check.py`, `README.md` text beyond a single Usage-section line, or `MANUAL-TESTS.md` (Planner / Evaluator handle docs after pass).
- Modifying `devcontainer.json` (the source-of-truth file). Mount injection happens via the generated per-session override config under `$HOME/.vibe/run/`.
- Touching `smoke-test.py` (Tester's territory).
- Per-org subdirectories (the original TODO mentioned this; the new framing is one anonymized library, simpler and safer — anonymization is what protects against cross-org leak, not directory segregation).
- A `--public` / `--private` global flag separate from the per-init choice.
- Encryption-at-rest of library entries.
- Symlink / hardlink tricks to bypass the `readonly` mount (we trust Docker's `readonly` flag).
- Cleaning up the `$HOME/.vibe/run/` dir (it accumulates per-workspace JSONs; cleanup is a follow-up).

## Test location

`smoke-test.py` at repo root. Tester **appends** new test functions and registers them in `main()`. Generator must not edit `smoke-test.py` at all. Tests use:
- The existing `_source_vibe_call` helper pattern (env + `VIBE_SOURCE_ONLY=1`) for unit-testing helpers.
- `tempfile.TemporaryDirectory()` for fake `$HOME` and library paths.
- `subprocess.run(..., input="y\n")` for stdin-piping the confirm prompt.
- For the public-mode push test: a temp git repo as the library + a sibling temp dir initialized as a bare repo set as `origin`, so push is local and offline.
- For the fake-git stub on injection-resistance tests: a temp dir on `PATH` containing a `git` script that records argv and exits 0.

## Proposed budget

**3 cycles.** Multi-file (vibe launcher with ~10 new helpers + dispatch + flag handling, `$HOME/.vibe/run/` materialization, override-config plumbing), security-sensitive (8 hard invariants in AC13 each requiring a dedicated test), real regression risk on flag parsing and the existing `--override-config` plumbing. Three cycles gives Generator one revision after Tester surfaces a corner case (re-init flow, push failure, marker-walk edge cases, EOF default).
