# task_048 CYCLE 4 — Generator report

Three targeted fixes in `devcontainer/codex-supervisor.mjs`, per the
amended AC4/AC5/AC7 in `.vs/spec.md`. Full diff: `.vs/cycle-4/diff.patch`
(whole-file, per the requested `git diff --no-index` form); a minimal
before/after diff is inlined below each fix. No file under `smoke/` was
touched.

## Fix 1 — AC5 retry input: the prompt is sent exactly once per thread

`loop()` used to set `text = 'continue'` only in the `completed`-without-exit
branch, so a quota wait, a transient back-off, or a turn failure resend
reused whatever `text` was passed into the current `runTurn()` call — the
rewritten prompt, unchanged, if the very first turn hadn't completed yet.

Fix: `runTurn(text)` has, by the time it returns, always sent whatever
`text` held (it's now unconditionally set on the request before anything
else happens in `runTurn`). So the single line `text = 'continue';` right
after `await this.runTurn(text)` — before branching on outcome — covers
every subsequent iteration: after a completed turn, a quota wait, a
transient back-off, or a turn failure. The old `text = 'continue';` inside
the `completed` branch became redundant and was removed.

```js
const { turn, turnId, agentMessage } = await this.runTurn(text);
text = 'continue';   // NEW — every turn/start after the first is 'continue'
const status = turn.status;
```

Verified with a red-then-green scratch scenario
(`t_c4_turn_failure_before_any_completion_retries_with_continue`):  first
turn/start carries the rewritten prompt, fails with a generic (non-quota,
non-transient, non-fatal) error; second turn/start — the failure retry — is
the literal `continue`.

### Known conflict with a cycle-1 pinned test (not fixed, cannot fix)

`smoke/checks_19_codex_supervisor.py::test_codex_supervisor_turn_failure_retries_same_text`
was written in cycle 1 against the **pre-amendment** AC5 wording ("re-send
until `--max-turn-failures`" — no mention of `continue`), and its assertion
is `t2 == t1 and t2 != "continue"` ("retry resends the SAME (rewritten)
text, not 'continue'"). This is the exact scenario the amended AC5 and this
task's fix (a) require to change: a turn failure before completion must now
re-send `continue`, not the same text. The two requirements — "implement
the amended, authoritative AC5" and "keep everything the existing tests pin
byte-identical" — are mutually exclusive for this one assertion; grepping
both smoke files confirms it is the *only* place either file checks a
`turn/start` message's `text` field (`grep -n '\["text"\]' smoke/checks_19*
smoke/checks_21*`), so no other pinned assertion is affected. I did not
edit `smoke/` (forbidden) and did not weaken the fix to keep it passing
(the spec is explicit that it's authoritative and this task's fix (a) names
this exact scenario). This is a genuine spec-supersedes-test situation, not
an implementation bug — the Tester/Evaluator should update that one
docstring + assertion (flip `t2 != "continue"` to `t2 == "continue"`, and
the "SAME (rewritten) text" wording) in a pass that's allowed to touch
`smoke/`.

## Fix 2 — AC7a: the wall deadline bounds every outstanding request

Previously every request (`initialize`, `account/rateLimits/read`,
`thread/start`, `thread/resume`, `turn/start`) used a fixed 30s timeout
(`HANDSHAKE_TIMEOUT_MS`/`REQUEST_TIMEOUT_MS`) regardless of the wall
budget, and a timeout always rejected with the ordinary `failError` (exit
1) — so a request that ran out of wall budget mid-flight could exit 1
instead of the required exit 3.

Fix:
- `AppServer.request()` gained an `onTimeout` factory option: when given,
  it builds the rejection error in place of the default `failError`.
- New `Supervisor.boundedRequest(method, params, opts)`: computes
  `remainingMs = max(0, (deadline() - now()) * 1000)`, uses
  `min(timeoutMs, remainingMs)` as the actual timeout, and if the wall
  budget (not the request's own limit) is what's binding, `onTimeout`
  builds a `ceilingError` naming `max-wall-seconds`; otherwise the ordinary
  `failError` (`"<method> timeout"`) as before.
- `deadline()` needed to work *before* `this.state` exists — `initialize`
  and the first `account/rateLimits/read` happen ahead of both
  `thread/start` and `thread/resume`. New `this.startedAtAnchor`, set once
  at the top of `run()` right before `spawnServer()` (a resumed run reuses
  the persisted `resumed.startedAt`; a fresh run anchors to `clock.now()`),
  is `deadline()`'s fallback when `this.state` is still null.
  `startThread()` now persists this same anchor as the new state's
  `startedAt`, instead of a second, later `clock.now()` call.
- All five request call sites (`handshake`, `readRateLimits`,
  `startThread`, `resumeThread`, `runTurn`) switched from
  `this.server.request(...)` to `this.boundedRequest(...)`.

Verified with a red-then-green scratch scenario
(`t_c4_turn_start_never_answered_near_deadline_exits_3`): the stub
acknowledges `initialize`/`account/rateLimits/read`/`thread/start`
normally but never answers `turn/start` at all (not even the id/result
ack — distinct from the existing "hang after `turn/started`" scenario,
which exercises the *notification*-await deadline, already covered and
unaffected). With `--max-wall-seconds 2` the run exits 3 naming
`max-wall-seconds` in well under the 30s `REQUEST_TIMEOUT_MS`, never exit
1; `turnsStarted` is still recorded (it's persisted before the request is
sent, unaffected by this fix).

No pinned test exercises a real request timeout (handshake or otherwise) —
`grep -i timeout smoke/checks_19* smoke/checks_21*` shows only
subprocess-level Python timeouts, none of which approach 30s — so this
change has no interaction with any pinned assertion.

## Fix 3 — AC4: the fresh rateLimits snapshot always wins on resume

`resumeThread()` only adopted the pre-resume `account/rateLimits/read`
snapshot (`this.pendingRateLimits`) when the persisted `lastRateLimits` was
exactly `null`:

```js
if (this.pendingRateLimits !== undefined && this.state.lastRateLimits === null) {
  this.state.lastRateLimits = this.pendingRateLimits;
}
```

A non-null persisted value — e.g. a stale window whose `resetsAt` had
already passed — was kept outright, discarding the fresh read entirely.
Fixed to always merge field-wise, per window, via the existing
`mergeRateLimits()` helper (already used for `account/rateLimits/updated`
during a turn):

```js
if (this.pendingRateLimits !== undefined) {
  this.state.lastRateLimits = mergeRateLimits(this.state.lastRateLimits, this.pendingRateLimits);
}
```

`mergeRateLimits(previous, update)` replaces `primary`/`secondary` whole
when the update carries them, so a fresh window always displaces a stale
persisted one — never the reverse.

Verified with a red-then-green scratch scenario
(`t_c4_resume_merges_fresh_ratelimits_over_stale_persisted`): a hand-built
state file's `lastRateLimits.primary.resetsAt` is `T0 - 100` (past); the
stub's `account/rateLimits/read` returns `resetsAt: T0 + 900` (future). The
resumed turn fails with `usageLimitExceeded`; the recorded quota wait is
`1020s` (900 + 120 grace) — the fresh value — not the ~20s the stale
persisted value would have produced. Before the fix this scenario computed
20s and adopted the stale window unchanged (confirmed red).

No pinned test exercises this path: every hand-built resume fixture in
both smoke files sets `"lastRateLimits": None` (`grep -n lastRateLimits
smoke/checks_19* smoke/checks_21*`), so old and new behaviour coincide for
every pinned scenario — this was a genuinely untested bug.

## TDD scratch harness

`.vs/cycle-4/scratch-tests/` — copied from `.vs/cycle-2/scratch-tests/` as
instructed, then extended:
- `stub-codex.py`: added a `"noResult"` turn-script flag (never answers the
  `turn/start` *request* at all, distinct from the existing `"hang"` flag
  which answers the request and only withholds `turn/completed`) — needed
  for fix 2's scenario.
- `drive.py`: three new `t_c4_*` scenarios, one per fix, run red (against
  the pre-fix file, restored from a snapshot for the purpose) then green
  (against the fixed file). All pre-existing cycle-1/cycle-2 scratch
  scenarios in the same file still pass, **except** one stale scratch
  relic, `t_resume_with_no_turns_sends_the_prompt`: it kills a run right
  after `turn/start` is sent (so `turnsStarted` is already persisted as 1)
  and asserts the resume sends the *rewritten prompt* — that was the
  cycle-2-era understanding, superseded by cycle 3's `turnsStarted`
  counter (a turn that was ever started resumes with `continue`, which is
  what actually happens now, correctly). This is scratch scaffolding, not
  a pinned test; the equivalent pinned smoke test
  (`test_codex_supervisor_c2_resume_never_started_sends_rewritten_prompt`)
  uses a hand-built state file with no `turnsStarted` key at all (correctly
  defaults to 0) and passes.

Run: `cd .vs/cycle-4/scratch-tests && python3 drive.py` — 0 failing checks
except the one noted stale relic above (pre-existing scratch scaffolding,
not touched by this cycle's fixes).

## Verification

- `python3 code-check.py` — clean, shellcheck across 22 files (no `.sh`
  changed this cycle; run for completeness).
- `python3 smoke-test.py < /dev/null` — **4118 passed, 1 failed**, exit 1.
  The one failure is `test_codex_supervisor_turn_failure_retries_same_text`
  (see Fix 1's "known conflict" section above) — the direct, unavoidable,
  and fully expected consequence of implementing the amended AC5 exactly as
  this task's fix (a) specifies, against a cycle-1 test that encodes the
  wording the amendment superseded. No other regression: every other test
  in `checks_19_codex_supervisor.py` (24 of 25) and all 11 tests in
  `checks_21_codex_supervisor_c2.py` pass, along with the rest of the
  suite.

## Recommendation to the Evaluator/Planner

This is a spec-vs-pinned-test conflict, not a bug in this diff. Since the
Generator role here is barred from touching `smoke/`, resolving it needs a
pass that can: update
`test_codex_supervisor_turn_failure_retries_same_text`'s docstring and its
`t2 != "continue"` assertion to `t2 == "continue"` (and rename it, e.g.
`test_codex_supervisor_turn_failure_retries_with_continue`), matching the
now-authoritative AC5 text. I have not made that edit myself.
