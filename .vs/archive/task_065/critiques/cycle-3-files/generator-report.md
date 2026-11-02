# task_065 cycle 3 — Generator report (Rev 7 addendum, AC32–AC40)

## Files changed this cycle
- `devcontainer/taskandi-client.mjs`
  - AC32: `pruneJobs` writes tombstones `{key, kind, digest, doneAtMs}` to `state.tombstones` for every pruned done job, drops tombstones older than 90 days on every state write, and never prunes `budget-<task>` jobs. Enqueue on both paths (HTTP `enqueueAll`, new MCP/file `fileEnqueueAll`) checks `jobs ?? tombstones`: same digest → `deduplicated` (state `done`), different → `KEY_CONFLICT`. `readState` accepts `tombstones` as an array. The prune clock is the client's (`withState(cwd, now, fn)` attaches it to the state as a non-enumerable symbol, so `createClient({clock})` drives tombstone expiry). Every `withState` call now passes `now`.
  - KEY_CONFLICT message is now `same key was already used with a different payload (KEY_CONFLICT)`: checks_57 looks for the literal `KEY_CONFLICT` in the CLI output, and the code alone never reached stderr.
  - AC33: `markImported` stores the new per-file entry and refuses a race when the stored entry is not the one the import read. New `usageKeys()` lists the record_usage keys of live jobs and tombstones. MCP/file `enqueueBatch` now validates every item first and writes all jobs plus `mark` in one locked write (it used to take one lock per item plus a separate lock for the ledger).
  - AC35: a renewal sets `spent[d] = max(stored, returned)` for each dimension, and `spentAt` = the renewal time. `claimedAtMs` still keeps the first claim's time.
  - AC36: `recordParked` sets `openAskIds` from state: every open blocking ask on the task, excluding the `budget-<task>` ask, whatever its action. This applies to both `release` and `reconcile --direct ... done`. The `--parked-asks` list now only marks the release as a park. Budget ask excluded because decide's guard set excludes it too; otherwise the two sets could never be equal.
  - AC37: `--as` takes only `proceeded` (argv parser, `--check-argv` and library `resolve` all refuse anything else as a usage error), and the usage text is updated. `resolve` always clears the task's `parked` entry. Old `resolved` entries with `as: parked` are ignored by the predicate (migration).
  - AC38: one function, `isOpenAsk(state, job, task)`, is used by pruning, `openAskJobs` (decide) and `openBlockingAskIds` (park/guard). An open ask is a done ask job on the task with `result.ask_id`, no answer with the same task and id and `ownerAnswer !== false`, and not resolved. An answer stored without `task` (MCP binding) counts for the job's task.
  - AC39: `nextTask` stores the claim first, then writes the body file. If the write fails, the claim is kept and `task` carries `body_file: null, body_file_error: "<reason>"` with exit 0. A null task calls `removeBodyFile`, which unlinks `.vibe/taskandi-body.txt` only inside a real `.vibe` dir and ignores errors. The success output is unchanged (no `body_file` key unless truncated).
- `devcontainer/taskandi-usage.mjs` (AC33): new ledger entry `{offset, prefixLen, prefixSha, tailIds}`. `prefixLen` is min(4 KiB, offset), stored so a file that was under 4 KiB at first import does not look rewritten once it grows. `tailIds` are the counted message ids whose records end in the last 64 KiB before the offset.
  - On the incremental path, only records starting at or after the offset count, minus `tailIds`. That covers straddling messages.
  - The re-read path runs when the file shrank, its prefix hash differs, or it has a legacy id-array entry. Each message's one-message key `[session, model, id]` is checked against live jobs and tombstones. Every message at or before the last named id, or, per model, at or before the last message whose key exists, counts as imported. This works because each import's job key is its last message per model. A first import (no entry) skips the key lookup.
  - Readers now work on Buffers with byte offsets (`readTranscriptBytes`, `parseRecords`); the Codex path is unchanged.
- Prose (AC34): the exact new skip string is in `vss.md` and `vsss.md` (blocks), as the first line of `taskandi-harness.md`, and in the `context.md` block. `taskandi-harness.md` gained one sentence after the park-task release: the client records every open blocking ask itself.
- Word cap: the new skip string adds 16 words × 2 command files, giving 14,327. I tightened two rationale clauses in `vsss.md` (no setting or behaviour removed). Total is now **14,289** (cap 14,300).
  1. Stall-watchdog paragraph: "— this is exactly why your per-iteration marker refresh (above) matters: without it, a live persistent run could look like a stale crash-left marker and never get the stall protection — and, since the launcher's countdown gained the same freshness gate, never get an auto-relaunch either;" became "— without your per-iteration refresh a live run looks crash-left and gets neither the stall kill nor a relaunch;" (−27 words).
  2. `resume_at` bullet: "— a stale `resume_at` already in the past would collapse the launcher's countdown to its 120s past-grace and probe a genuinely exhausted window every 2 minutes, each probe costing a full stall-watchdog cycle." became "— a stale past `resume_at` would make the launcher re-probe an exhausted window every 2 minutes, each probe a full stall-watchdog cycle." (−11 words).
- `docs/taskandi-client.md`: State, new Pruning and Open-asks paragraphs, the renewal rule, `--as proceeded` only, how a park computes `openAskIds`, body-file failure / null-task cleanup, and the Claude usage ledger.
- `MANUAL-TESTS.md` Test 70: new bullet: an unbound project runs no `taskandi-client` at all.
- `CHANGELOG.md`: cycle-3 sentence appended to the task_065 entry.
- `smoke/fixtures/taskandi-v22/PROVENANCE.md` (AC40): new section with a fenced block in `sha256sum` format (`<64 hex>  <name>.json`, ten lines). The fixture files themselves are unchanged in git.

## Spec conflict to note
- AC31 said each command block is ≤ 60 words. The AC34 skip string alone is 50 words, and with the fixed pointer sentence the block is **71** words. Any check enforcing 60 needs raising (my scratch prose check uses 80). No checks_* currently fail on it.

## Commands run
- `node .vs/cycle-3/scratch-tests/cycle3.test.mjs < /dev/null` → 26 passed, 0 failed (AC32 HTTP + file path, AC33 straddle / prefix change / shrink / legacy, AC35, AC36 + guard, AC37, AC39).
- `node .vs/cycle-1/scratch-tests/decide.test.mjs < /dev/null` → 99/100. The 1 failure is `--check-argv ... --as parked`, which AC37 now forbids, so it is expected.
- `python3 .vs/cycle-3/scratch-tests/prose_check.py` → 0 (new skip string, word cap 14,289).
- `python3 code-check.py` → 0.
- `python3 smoke-test.py < /dev/null` → exit 1, 4 failures, all expected or on the tester side:
  1. checks_53 `AC3: --as parked records as=parked`: the behaviour AC37 removed.
  2. checks_53 `A4: reconcile --direct release --action done writes the parked entry too`: expects `openAskIds == ["ask-1","ask-2"]` from `--parked-asks`. AC36 now records the open blocking asks from state, and there are none in that fixture.
  3. checks_57 `AC32 ... different payload it is a KEY_CONFLICT`: fixed after the run by putting `(KEY_CONFLICT)` in the message; a standalone checks_57 run now passes it.
  4. checks_57 `AC38 setup: a done seed ask`: a tester-side bug. The seed `enqueue ask` payload has no `remaining_minutes` (required in v2.2: "remaining_minutes must be a nonnegative safe integer") and no `ask` route, so the ask never reaches `done`.
- Standalone re-runs after the fix: checks_47/50/52/54/55 show no failures; checks_53 shows only the 2 expected; checks_57 shows only the AC38 setup.

Not touched: `smoke/checks_*.py`, `smoke/runner.py`, launcher, Dockerfile (this cycle), firewall, hooks. No commit.
