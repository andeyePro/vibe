# task_048 — Generator report, CYCLE 2

Branch `astra`, no commits made. One production file changed:
`devcontainer/codex-supervisor.mjs`. `smoke/` was read but never edited.
The spec was re-read first; AC4, AC6 and AC7 as AMENDED are what the fixes
implement.

## Finding 1 — resume input and terminal state (AC4 amendment)

Two defects: `run()` always re-sent the original prompt after
`thread/resume`, and `adoptState()` rebuilt the state through `freshState()`,
which has no `exitReason` key — so a completed run silently restarted.

- `adoptState()` now copies `exitReason` onto the adopted state when the
  previous file carries one (after the `--new-run`, cwd and promptHash
  checks, so a mismatch is still exit 2 and `--new-run` still archives).
- `run()` treats such a state as TERMINAL: it writes
  `already complete: <reason>` to stdout and returns `EXIT_OK` **before**
  `spawnServer()`, so nothing is spawned. `--new-run` remains the way to
  start over.
- The first input on a resumed run is chosen from the history:
  `resumed.turns.length ? 'continue' : promptText`. A never-started run
  (thread/start persisted, killed before any turn completed) still sends the
  user's rewritten prompt; a run with recorded turns nudges the thread that
  already holds the prompt with the literal `continue`.

## Finding 2 — no deadline while awaiting a turn (AC7(a))

`runTurn()` called `this.server.nextNotification()` with no bound, so a
silent or endlessly-retrying server could hold the supervisor for ever.

- New `deadline(state)` helper: `startedAt + maxWallSeconds`, one definition
  shared by every wall-clock decision.
- New `nextNotificationOrDeadline()` races the next notification against that
  deadline. With the real clock it arms one `setTimeout` for the remaining
  budget; with `--now-source` the clock only moves when the file moves, so it
  polls `clock.now()` every 100 ms and fires on the first observation past
  the deadline (tests advance the virtual clock and the supervisor notices).
  Both timers are `unref`'d and cleared in a `finally`. A deadline already in
  the past short-circuits before any timer is armed.
- On expiry `expireDuringTurn(turnId)` logs, sends `turn/interrupt
  {threadId, turnId}` (fire-and-forget via the new `AppServer.send()`, since
  a server that never completed a turn may never answer either), closes the
  server's stdin, persists the state and throws the ceiling error → exit 3
  naming `max-wall-seconds`.

## Finding 3 — waits not capped by the remaining budget (AC7(b))

`recordWait()` is the single funnel both the quota and the transient path go
through before sleeping, so the cap went there: it still appends
`{reason, seconds, until}` and persists first — the state file remains the
record of why the run stopped — and then, if `until > deadline()`, throws the
ceiling error instead of sleeping. Neither `quotaWait()` nor
`transientWait()` can now sleep past the ceiling, and with the real clock the
process leaves immediately rather than burning the full back-off first.

## Finding 4 — `checkGates()` omitted `turnFailures`; `--max-*` validation

- `checkGates()` gained `turnFailures >= maxTurnFailures` → exit 3 naming
  `max-turn-failures`. AC5(v)'s in-loop exit 1 (with the last message) still
  fires first during a run, because it is checked immediately after the
  increment; the gate's job is the restart path the review named — a resumed
  run carrying an exhausted count can no longer walk back into the loop.
- `parseArgs()` rejects any `--max-*` below 1 with exit 2
  (`<flag> must be at least 1, got: 0`), nothing spawned.
- Gates on resume run before anything is sent: `run()` calls `checkGates()`
  on the adopted state before `spawnServer()` (and `resumeThread()` keeps its
  own check).

## Finding 5 — outstanding wait ignored on resume (AC4 amendment)

New `honourOutstandingWait(state)`, called in `run()` between the two gate
checks and before `spawnServer()`. If the last `waits[]` entry has a finite
`until` still in the future it either sleeps the remainder (a no-op under
`--now-source`, where the virtual clock advances by it, exactly as AC6's
waits do) or, if `until` is past the deadline, throws the ceiling error →
exit 3 without spawning anything. Gates are re-checked after the sleep, so a
wait that consumes the wall budget is caught immediately.

## Untouched, as required

Child `env` ({PATH, HOME, CODEX_HOME, LANG}), argv `['app-server']`, the
`initialize` line and its id/ordering with `account/rateLimits/read`, the
`REWRITES` prefix table, and `writeStateFile()`'s `.tmp` + rename atomicity
are byte-for-byte as cycle 1 left them.

## TDD

`.vs/cycle-2/scratch-tests/` (created this cycle; the stub is a fresh
self-locating variant of cycle 1's, since the pinned child env cannot carry
scenario data): `stub-codex.py` (app-server stub, now also answering
`turn/interrupt` and able to `hang` a turn) and `drive.py`, 13 scenarios /
48 assertions, at least two per finding:

- finding 1 — terminal state exits 0 without spawning and preserves
  `exitReason`; resume with recorded turns sends `continue`; resume with no
  recorded turn sends the rewritten prompt.
- finding 2 — a hanging turn under a virtual clock advanced past the ceiling
  exits 3 having sent `turn/interrupt {threadId,turnId}`; the same under the
  real clock with `--max-wall-seconds 2`.
- finding 3 — an over-long quota wait exits 3 with the would-be 50120 s wait
  recorded and the turn never re-sent; the transient equivalent; and a
  real-clock transient case that must return in well under the 60 s back-off.
- finding 4 — all six `--max-* 0` forms exit 2 with nothing spawned; a
  resumed state at `turnFailures: 3` exits 3 naming `max-turn-failures`
  without spawning.
- finding 5 — an outstanding wait past the ceiling exits 3 without spawning;
  one inside the ceiling is slept (the recorded turn timestamps show the
  clock advanced by exactly the remaining 400 s) and the run then completes 0.

Run RED first: 23 failing checks across findings 1, 2, 4, 5, plus the
real-clock finding-3 case (which hung past its 25 s timeout on the old
code — the virtual-clock quota case could not show red, because a no-op
sleep makes the old and new behaviour indistinguishable, which is why the
real-clock case was added). After the fixes: 0 failing checks.

## Commands run

- `python3 .vs/cycle-2/scratch-tests/drive.py` — red (23 failing) → green (0 failing).
- `python3 code-check.py` — `✓ shellcheck clean across 22 files`, exit 0.
- `smoke/checks_19_codex_supervisor.py` alone (25 functions) — 0 failures.
- `python3 smoke-test.py < /dev/null` — `✓ smoke tests passed`, exit 0,
  4037 passing checks, no `✗`. Full log: `.vs/cycle-2/smoke-output.log`.

## Not done / notes

- Nothing committed, no branch change, no push (as instructed).
- `.vs/cycle-2/diff.patch` is `git diff` (tracked files: `.vs/tasks.json`
  only — the rest of the working tree's modifications are cycle 1's, already
  captured in `.vs/cycle-1/diff.patch`) followed by a
  `git diff --no-index` rendering of the untracked
  `devcontainer/codex-supervisor.mjs`, which is where every change of this
  cycle lives; cycle 1's `git diff` could not show that file either.
- No docs change was needed: AC9's `vsss.md` / README / plan D7 assertions
  still pass unchanged, and the amendments touch runtime behaviour only.
