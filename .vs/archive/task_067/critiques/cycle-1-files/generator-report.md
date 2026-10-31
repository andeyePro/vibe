# task_067 cycle 1 — Generator report

## Files changed
- `devcontainer/taskandi-client.mjs` — create_task/update_task (validation, repeat validator, gating, results, ledger, caps, duplicates, self_created, update targets, `created`, `reconcile --task-id`).
- `devcontainer/taskandi-harness.md` — new step 8 "Propose a task" (after step 7, "at any point in step 3").
- `docs/taskandi-client.md` — new section "Proposing tasks (contract v2.4, v2.5)"; v2.3-section intro sentence updated.
- `MANUAL-TESTS.md` — Test 71. `CHANGELOG.md` — entry at top of `## 2026-10-31`.
- `smoke/fixtures/taskandi-v25/` — the seven fixtures, byte for byte, plus `PROVENANCE.md` with sha256s.
- `.vs/tasks.json` — task_067 `implementation_status` → `complete` (only that field).
- Scratch: `.vs/cycle-1/scratch-tests/scratch_propose.py` (about 120 checks, AC1–AC11, all pass).

## Per-AC notes
- **AC1** The body is built by the existing `wireBody`/`jobBody`. `agent` is added for both kinds. `session`: a create carries it whenever a claim exists (B1); an update only when its target is the claimed task. All six fixtures match in the scratch test. Note: `create_task_agent.json` has no `request_id`, but the client always sends one (v2.3 family).
- **AC2** `validateProposal(kind, input)` (exported). Errors are named per field. Reserved keys are `action`, `connection`, `agent`, `session` and `request_id`. Text is checked with `wireText` (code points, non-blank after trim) and sent untrimmed. `parent` and `task` must match `USABLE_ID` and are sent verbatim (not lower-cased).
- **AC3** `validateRepeat` (exported). It checks unknown keys first (named themselves, `__proto__`/`constructor` included), then the fields in contract order. If `monthDay` and `nthWeekday` are both given, it reports `monthDay`. A time zone that Intl refuses gives "unknown to this host's tzdata, which may be older than the server's". A case-only difference from `resolvedOptions().timeZone` is refused; links are accepted. The digest uses the sorted `canonical`, so key order does not change it.
- **AC4** Gating is per job in `flush`: rank(contract) must be at least the need (4, or 5 with `repeat`, `null` included), and the call must be in `caps.calls`. Propose kinds are left out of `open()`'s call list, so an old server never fails the whole flush. A gated job stays `queued` with `lastError` `needs_contract_v2.4`/`v2.5`, and `status` lists it in a new `gatedKeys`. A frozen propose body met by a server that does not offer what it needs becomes `uncertain` with no request. On a non-descriptor binding, enqueue exits 1 with `create_task needs a Task&I descriptor binding`; for update_task too, the spec's literal wording.
- **AC5** Resend uses the existing machinery. `reconcile --action done` on an uncertain create needs `--task-id <usable id>` and writes the ledger. `--action retry` on a create unfreezes, issues a fresh requestId, clears `noRetry` (so it is allowed even after a resend `receipt_collision`), and warns "...the owner may now see two proposals".
- **AC6** There are response schemas for `create_task` and `update_task` (exact keys, `provisional: true`, ids that are usable ids, the update echoing its task). For propose kinds a `malformed_response` goes straight to `uncertain`, not the v2.3 resend-requeue path, since a resend would replay the same answer. An `invalid_request` carrying a printable `repeat`/`unsupported` field is appended to `lastError` (`(repeat: time)`).
- **AC7** `state.created` is written in the same `atomicJson` as `done`. `pruneJobs` never touches it except to drop entries older than 180 days (by the injected clock). `wrong_scope` marks entries gone: an update's target, or a create's ledger parent. `created [--task REF] [--all]` works offline.
- **AC8** Order: a same-key, same-digest dedupe first; then `duplicate_proposal` (ledger including gone entries, plus create jobs not in the ledger, any state); then KEY_CONFLICT; then the caps. Caps count ledger entries plus pending create jobs that are not refused. The session comes from `--session` (create_task only), else `VIBE_SESSION_STAMP`, else null.
- **AC9** `--task` on an agent-assigned ledger task gives `self_created` with zero requests (checked before the effective-task rule). An A-mode offer of one is released with the spec's reason and prints `self_created`; the stored claim and the body file are untouched. Also, `next-task --task` now accepts a non-gone ledger task as REF, besides the effective and claimed task: the Tester's AC9 B2 expects it (B2's "claims it normally").
- **AC10** Targets are checked locally. The persona is the claim's when the target is the claimed task, else `VIBE_AGENT`, else `claude`. Messages are `update_task: not your task ...` and `update_task: not created yet ...`, the latter when the target is a create job's key that is not done.
- **AC11** Covered in the scratch test (codex for update/create via `VIBE_AGENT`; default claude).
- **AC12** The harness has the literal rules. `--check-argv` accepts `enqueue create_task --key K [--session S]`, `enqueue update_task --key K`, `created [--task] [--all]` and `reconcile ... --task-id`, and rejects invented flags. **Ambiguity:** checks_54 AC10 requires the harness subcommand set (fenced lines plus backticked `` `taskandi-client X` ``) to be exactly the old nine. So `created` appears in the harness as plain prose ("run taskandi-client created", no backticks) and in `` `created` ``, not as a fenced line. A Tester check for a fenced/backticked `taskandi-client created` would conflict with AC13.
- **AC13** Every pre-existing check passes. In the full run, all 17 failures are in `[taskandi-propose]`, and none elsewhere.
- **AC14** Docs, MANUAL-TESTS, CHANGELOG and the fixtures are done. The CHANGELOG entry is short, so task_066's entry stays within the first 6000 chars (the checks_59 AC16 window).

## Remaining failures: in the Tester's in-progress checks_61/62, which I believe are test-harness issues
1. **`createIds`.** These checks pass `ids=[...]` per `make()`, but the fake server indexes `createIds` by the cumulative count of applied creates (`appliedN.create_task`). From the second create in a server onward, the requested id is ignored and a random uuid is used. This affects:
   - AC2 setup and the six update rows. The target gets a uuid, so `update_task` on `upd-target-1` is correctly `not your task`.
   - AC7 pruning, 180-day, `created` and `--all`/`--task`. The ledger holds a uuid where `led-2`/`cr-b` was expected.
2. **AC6 `errors.times`.** `times: 1` uses a cumulative per-action counter (`bump('err', action)`), so only the first loop iteration gets the error. The later creates are applied for real.
3. **AC8 "refused enqueue did not count".** `hx.clear()` after the first three creates empties the log, so `create_applied` counts 7. The ledger holds 10, the correct number.

Fixed after the first run, from Tester expectations matching the spec:
- the `tzdata` wording;
- the literal `create_task needs ...` message for update_task too;
- create retry allowed after a resend collision;
- `--task` accepting a ledger task;
- "flush first" in the harness.

## Other ambiguities / choices
- **create_task agent.** When a claim exists, a create uses the claim's agent, so it matches the session it sends. Otherwise `VIBE_AGENT`, else `claude`.
- **`created` on non-descriptor bindings.** Unbound prints the file-fallback line; MCP exits 1.
- **update_task done.** It does not update the ledger's title.
- **Gating.** A gated job pushes a stderr notice on every flush and is not counted in the flush JSON (whose keys are unchanged).

## Commands and exit codes
- `python3 code-check.py` → 0
- `python3 .vs/cycle-1/scratch-tests/scratch_propose.py < /dev/null` → 0 (0 failures)
- `python3 smoke/checks_54_harness_prose.py < /dev/null` → 149/149 passed
- `python3 smoke-test.py < /dev/null` → 1. 17 failures, all `[taskandi-propose]` (above); every other check passes. The first run, before the fixes, had 25, also all `[taskandi-propose]`.
- `git add -N smoke/fixtures/taskandi-v25 && git diff -- devcontainer docs CHANGELOG.md MANUAL-TESTS.md smoke/fixtures > .vs/cycle-1/diff.patch` → 0
