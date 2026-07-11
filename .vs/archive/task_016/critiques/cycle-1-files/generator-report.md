# Generator report — task_016 cycle 1

## Summary

Implemented AC1-AC13 (excluding Tester's own AC10/test-writing scope) per spec.md.
All new bash functions live before the `VIBE_SOURCE_ONLY` guard. `smoke-test.py`
was NOT touched (Tester-owned).

## Per-AC delivery

- **AC1 `auto_resume_deactivate`** — vibe, added right after `auto_resume_decrement`
  (~line 519). awk-to-temp+mv, `"${file}.tmp.$$"` temp name, idempotent, missing
  file → return 0 without creating one.
- **AC2 `auto_resume_heartbeat_write`** — same block. Atomic epoch write; on any
  failure (write or rename) the temp file is `rm -f`'d and the function still
  returns 0 — never trips `set -e`.
- **AC3 `auto_resume_stalled`** — same block. `head -1` + digits-only case guard,
  strict `>` comparison via a `gap` local var. Fail-safe (return 1) on missing/
  empty file, non-numeric, future epoch, and the exact boundary.
- **AC4 heartbeat hooks** — settings.local.json heredoc (~1428+): new `PreToolUse`
  entry (matcher `""`), new `PostToolUse` block (matcher `""`), and the pinned
  command appended as a second entry in the existing `Stop` matcher's `hooks`
  array. Command string matches the spec verbatim, character for character.
  Original guard-bash/guard-fs PreToolUse entries, both bell commands,
  `forceLoginMethod`, and `permissions.defaultMode` are all unchanged — additive
  only. Comment block above the heredoc extended to mention the heartbeat hooks.
- **AC5 supervised launch** — `launch_claude`'s body is now `exec devcontainer
  exec ...` (indented, so it does not start a line with `exec devcontainer exec`).
  `VIBE_SESSION_REF=$(mktemp ... ) || VIBE_SESSION_REF=""` added before the first
  supervised launch. `launch_claude_supervised` seeds the heartbeat when a marker
  exists, backgrounds `launch_claude`, captures `$!`, backgrounds
  `vibe_stall_watchdog`, waits with `wait "$claude_pid" || rc=$?`, stores
  `CLAUDE_EXIT`, reaps the watchdog with guarded `kill`/`wait`, and always
  `return 0`s. `AUTO_RESUME_MARKER` / new `AUTO_RESUME_HEARTBEAT` are defined
  once, before the first supervised call. No bare `launch_claude ... || true`
  call remains — both call sites go through `launch_claude_supervised`.
- **AC6a `vibe_container_kill_claude`** — literal, bare, non-`exec`-prefixed
  `devcontainer exec --workspace-folder "$WORKSPACE" --override-config
  "$OVERRIDE_CONFIG" pkill -TERM -x claude || true`. This is the line that keeps
  `test_vibe_final_line_no_exec` assertion (b) passing.
- **AC6b `vibe_stall_watchdog`** — polls `kill -0 "$claude_pid"` every
  `${VIBE_STALL_POLL_SECS:-60}`s. Kill gate split into a small internal
  `_vibe_stall_armed <marker> <ref>` helper (conditions 1+2: `active=1` via
  `auto_resume_field`, and either the literal sentinel `-` or `[ marker -nt ref ]`
  with ref non-empty and existing) combined with `auto_resume_stalled` (condition
  3, default threshold 1800s). On first trigger: stderr warning with bell +
  threshold + cancel instruction, `sleep "$grace"`, re-check both helpers, and
  only if still armed: `vibe_container_kill_claude`, `sleep
  "$kill_pause"` (default 10s), then `kill "$claude_pid" 2>/dev/null || true` as
  host fallback. Every sleep/command is individually guarded. All constructs are
  portable (`[ -nt ]`, no GNU-only `stat`/`date -d`).
- **AC7 countdown Ctrl-C trap** — re-armed at the top of every loop iteration,
  immediately before the countdown `sleep`; `trap - INT` right after; registers
  only the `INT` slot (never touches EXIT — the clipboard-watcher EXIT trap at
  ~1629 is untouched, confirmed by grep). On Ctrl-C: `auto_resume_deactivate`,
  one-line notice, `exit 130`.
- **AC8 exit propagation** — `CLAUDE_EXIT=0` declared globally before first use;
  `launch_claude_supervised` sets it from `wait`'s captured status; the script's
  final statement (after the auto-resume loop's `done`) is `exit "$CLAUDE_EXIT"`.
  The old `|| true` swallow at both call sites is gone.
- **AC9 shellcheck** — `python3 code-check.py` → `✓ shellcheck clean across 15 files`.
- **AC10 (Generator's slice: no NEW failures)** — `python3 smoke-test.py` → all
  1000 checks pass, 0 failures (see Gate outputs below). Did not modify
  `smoke-test.py`.
- **AC11 MANUAL-TESTS.md** — new "Test 32: `--sessions` stall watchdog (task_016)"
  section before `## Test Summary`, with six lettered sub-cases (32a-32f) covering
  simulated stall + relaunch, `remaining=0` clean exit, crash-left-marker no-kill,
  Ctrl-C deactivation + EXIT-trap survival, exit-status propagation, and visible
  heartbeat refresh.
- **AC12 gitignore** — `.vss/heartbeat*` added directly below the existing
  `.vss/auto-resume` line.
- **AC13 docs** — vibe's auto-resume comment block (~479) extended with a full
  "Stall watchdog" paragraph covering heartbeat hooks, the three-part gate,
  the `remaining=0` exit path, in-container-then-client kill order, watchdog
  lifetime bound, Ctrl-C deactivation, and exit propagation. `vsss.md` §
  "Auto-resume across halts" gains a new paragraph documenting the launcher-side
  watchdog contract (heartbeat file, all four `VIBE_STALL_*` env vars + defaults,
  why the skill's existing per-iteration marker refresh is now load-bearing,
  kill-and-countdown / last-window-exit behaviour, and that the skill needs no
  new behaviour). `CHANGELOG.md` gains a `## 2026-07-10` entry.

## Deviations from spec + rationale

- Added one small internal helper, `_vibe_stall_armed <marker> <ref>`, not named
  in the spec's five-function list. It only factors out kill-gate conditions
  1+2 from `vibe_stall_watchdog` (called twice — initial check and post-grace
  re-check) so the two call sites stay identical instead of duplicating a long
  compound test. It follows the codebase's existing underscore-prefixed private
  helper convention (`_build_override_config`, `_brain2_source`,
  `_ensure_op_forwarder`, etc.) and lives in the same before-the-guard block as
  the five spec-named functions, so it is sourceable/stubbable under the same
  `VIBE_SOURCE_ONLY=1` pattern if Tester wants to exercise it directly. No
  spec-mandated behaviour changed; this is pure internal factoring.
- `vibe_stall_watchdog` returns immediately after handling one escalation cycle
  (whether or not the re-check still holds, i.e. even if the trigger conditions
  cleared during the grace period). The spec's prose describes the sequence
  ("re-checks ALL THREE conditions; only if still met: kill... then returns")
  without explicitly stating the no-longer-armed-after-grace case; returning
  either way is the natural reading and keeps the function a single-shot
  escalation (matching all four functional test scenarios in AC6b, none of
  which exercise "armed, then un-armed during grace, then re-armed later").

## Gate outputs

`python3 code-check.py`:
```
✓ shellcheck clean across 15 files
```

`python3 smoke-test.py 2>&1 | tail -20`:
```
  ✓ [onboard] SECURITY.md points at the repo Security tab
  ✓ [onboard] SECURITY.md marks Claude Code + Docker out-of-scope upstream
  ✓ [onboard] SECURITY.md names the in-scope classes
  ✓ [onboard] bug_report.md template exists
  ✓ [onboard] bug template asks for vibe --version
  ✓ [onboard] bug template asks OS + container runtime
  ✓ [onboard] feature_request.md template exists
  ✓ [onboard] feature template points at CONTRIBUTING.md
  ✓ [onboard] PULL_REQUEST_TEMPLATE.md exists
  ✓ [onboard] PR template names both gate scripts
  ✓ [onboard] PR template cites CHANGELOG + MANUAL-TESTS conventions
  ✓ [onboard] ONBOARDING.md exists
  ✓ [onboard] ONBOARDING.md addresses the assisting Claude
  ✓ [onboard] ONBOARDING.md installs from andeyePro/vibe
  ✓ [onboard] ONBOARDING.md verifies with vibe --version
  ✓ [onboard] CONTRIBUTORS.md exists
  ✓ [onboard] CONTRIBUTORS.md carries the revenue-share ledger framing
  ✓ [onboard] CLAUDE.md routes arriving Claudes to ONBOARDING.md

✓ smoke tests passed
```
Full run: 1000/1000 checks passed, 0 entries in `FAILURES` (confirmed via
`grep -c '✓'` against the full log and the exit code). This includes
`test_vibe_auto_resume_helpers` (all 9 checks pass unchanged) and
`test_vibe_final_line_no_exec` (both assertions pass — no line starts with
`exec devcontainer exec`; `vibe_container_kill_claude`'s bare
`devcontainer exec` line satisfies the "at least one bare occurrence" check).
The historically-noted 3 pre-existing `[copy]` TTY failures did not reproduce
in this run (environment-dependent; not a regression — no `[copy]` test
failed).

## Files touched

- `/workspace/vibe`
- `/workspace/.gitignore`
- `/workspace/MANUAL-TESTS.md`
- `/workspace/devcontainer/commands/vsss.md`
- `/workspace/CHANGELOG.md`
- `/workspace/.vs/tasks.json` (status-field mutation only: task_016
  `implementation_status` → `"complete"`)

Not touched: `smoke-test.py`, any file under `devcontainer/` other than
`commands/vsss.md`, `guard-bash.sh`, `guard-fs.sh`, `init-firewall.sh`, the
EXIT trap line in `vibe` (~1629, untouched — confirmed by grep after edits).

No blocks encountered; delivered in 1 attempt (retry budget unused).

Diff: `/workspace/.vs/cycle-1/diff.patch` (git diff, uncommitted).
