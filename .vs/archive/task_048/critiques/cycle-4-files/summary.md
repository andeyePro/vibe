# task_048 cycle 4 — Tester summary

Appended 6 `test_codex_supervisor_c4_*` functions to `smoke/checks_21_codex_supervisor_c2.py` (951 lines) covering the AC4/AC5/AC7 amendments from the reviewer's second pass: the rewritten prompt sent exactly once per thread (three fresh scenarios — quota, transient, plain-failed-turn — each asserting both turn/start texts), the wall deadline bounding outstanding requests themselves (turn/start and thread/start each never-answered, via a new hang-stub, exit 3 naming `max-wall-seconds`, never exit 1), and the fresh `account/rateLimits/read` snapshot winning field-wise over a stale persisted `lastRateLimits` on resume (1020s quota wait, not a stale/negative one). Registered in `smoke/runner.py`; checks_19 and the existing checks_21 tests are untouched.

`python3 code-check.py` clean (22 files). `python3 smoke-test.py < /dev/null` fully green: exit 0, 4155 `check()` lines passing, 0 failed, including all 30 new c4 assertions and every prior checks_19/checks_21 test — no regressions.

Nothing left uncovered for this cycle's scope (amended AC4/AC5/AC7). `.vs/tasks.json` task_048 updated: `test_status: pass`, `assigned_to: evaluator`, cycle_4_tester_note appended.
