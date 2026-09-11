# task_048 CYCLE 3 — Generator report

## The bug (cycle-2 Tester finding)

A turn killed mid-flight — SIGTERM after `turn/start` was sent, before
`turn/completed` arrived — left `state.turns` empty (a turn is only
appended to `turns` on completion). On the next `run`, `resumeThread()`
decided the resume input with `if (resumed.turns.length) firstText =
'continue';` — and an empty `turns` array is indistinguishable, by that
check alone, from a thread that never got a `turn/start` at all. So the
resumed run re-sent the original (rewritten) prompt into a thread that had
already seen it once, instead of the literal `continue` the amended AC4
requires.

## The fix

One targeted change in `devcontainer/codex-supervisor.mjs`: a persisted
`turnsStarted` counter, independent of `turns` (which only ever records
*completed* turns).

- `freshState()` — starts at `0`.
- `adoptState()` — carried through the existing per-key copy loop
  (`for (const key of ['turnsStarted', 'resumes', ...])`), defaulting to
  `0` for a legacy state file written before this field existed.
- `runTurn()` — incremented and persisted **atomically** (`this.persist()`,
  the existing tmp-file-then-rename helper) at the very top of the
  function, immediately before the `turn/start` request is sent. Because
  the main loop (`loop()`) always re-enters `runTurn(text)` for every
  re-send — after a quota wait, a transient back-off, or a turn-failure
  retry — this single call site covers every `turn/start`, not just the
  first one, satisfying "including re-sends after quota/transient/
  turn-failure retries" without a second increment site.
- `run()`'s resume branch — now decides `firstText` from
  `Number(resumed.turnsStarted || 0) >= 1` (→ literal `continue`) instead
  of `resumed.turns.length`. Only a thread whose state file shows
  `turnsStarted === 0` (no `turn/start` was ever sent) gets the rewritten
  prompt.
- `statusReport()` — a `turns started` row was added so the counter is
  visible in `codex-supervisor status` output, per the amended AC4.

Everything else — argv, the child env allowlist, the `initialize` line,
notification ordering, the wait/back-off ladders, gate checks, and
state-file atomicity — is untouched.

## Diff shape

```
freshState():        + turnsStarted: 0,
adoptState():         for (const key of ['turnsStarted', 'resumes', 'quotaWaits', 'transientRetries', 'turnFailures'])
runTurn():           + this.state.turnsStarted = Number(this.state.turnsStarted || 0) + 1;
                     + this.persist();
                       (placed immediately before the `turn/start` request)
run() resume branch:  if (Number(resumed.turnsStarted || 0) >= 1) firstText = 'continue';
statusReport():      + ['turns started', String(state.turnsStarted ?? 0)],
```

Full diff: `.vs/cycle-3/diff.patch`.

## Verification

- `python3 code-check.py` — clean, 22 files, shellcheck (no `.mjs` changes
  affect this; run for completeness).
- `python3 smoke-test.py < /dev/null` — fully green, exit 0, 4120 `check()`
  lines, 0 failed. In particular:
  - `test_codex_supervisor_c2_resume_after_sigterm_sends_continue` — now
    **passes** (was the sole cycle-2 failure).
  - `test_codex_supervisor_c2_resume_never_started_sends_rewritten_prompt`
    — still passes (a hand-built state file with no `turnsStarted` key at
    all falls back to `0` via the `Number(resumed.turnsStarted || 0)`
    guard, so the rewritten-prompt path is unaffected).
  - All 25 `checks_19_codex_supervisor.py` tests and all 11
    `checks_21_codex_supervisor_c2.py` tests pass, including the ones that
    pin exact argv, env keys, the `initialize` line, message ordering,
    wait durations, exit codes, and "no `.tmp` left / no stray files under
    `--cwd`" atomicity assertions — none of which this change touches.

No file under `smoke/` was edited.
