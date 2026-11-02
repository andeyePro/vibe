# task_067 cycle 2 — Generator report (Rev 3 addendum, AC15–AC27)

## Files changed
- `devcontainer/taskandi-client.mjs` — AC15–AC26 (details below).
- `devcontainer/taskandi-harness.md` — step 8 wording (AC27, AC20, AC21); update_task fenced line gains `--session <session>`.
- `docs/taskandi-client.md` — "Proposing tasks" updated for every AC, plus a "Client-side limits" paragraph near the top of the section.
- `CHANGELOG.md` — the task_067 entry gains a "Review hardening (cycle 2)" bullet. task_066's entry still starts at char 3638 (inside the 6000-char window).
- `MANUAL-TESTS.md` — Test 71 gains two items (contains_secret; owner-task next_action / update_cap).
- Scratch: `.vs/cycle-2/scratch-tests/scratch_cycle2.py`, about 60 checks, 0 failures.

## Per-AC notes
- **AC15** `applyUpdate` runs in the same write as `done`, both in flush and in `reconcile --action done`. `outstandingRepeats` counts:
  - ledger repeats that are not gone;
  - create jobs not yet in the ledger, not refused, that carry a repeat;
  - live (queued, dispatching or uncertain) update jobs that add a repeat to a task that has none, counted once per task.

  It is used by both the create and the update `repeat_cap`. `repeat` (`null` included) on a task that is not a non-gone, non-reconciled ledger entry is refused with `repeat only on your own proposals`.
- **AC16** Update checks run in this order: not created yet → repeat-own → not your task → `on the owner's task vibe may only change next_action` → repeat_cap → `update_cap`.
  - `update_cap` covers any non-refused update job with the same target and the same stamp.
  - The stamp is `--session` (new optional flag on `enqueue update_task`, which the Tester's checks use), else `VIBE_SESSION_STAMP`, else the claim's session.
  - With no stamp there is no update_cap (read from AC19).
- **AC17** Order: dedupe, then KEY_CONFLICT, then `creationChecks` (duplicate check excluding the job's own key and refused jobs, then the caps).
- **AC18** New `normaliseTaskId` strips the prefix, checks the id is usable and lower-cases UUIDs. `descriptorTaskRef` is now an ABBR-N refusal plus `normaliseTaskId`. The ABBR refusal stays on `--task` only, because ledger ids such as `led-2` are ABBR-shaped. It is used for parent, update_task.task, reconcile --task-id and created --task.
- **AC19** The session cap applies only when a stamp is given, and null-session entries never match a stamp.
- **AC20** A retry is refused when `noRetry` is set, for every kind. A create_task retry re-runs `creationChecks`; for an uncertain job the earlier attempt goes into `job.priorAttempts`, which `countedCreations` keeps counting.
- **AC21** done --task-id refuses the claimed task, the effective task, and any id already in the ledger under another key. The entry gets `reconciled: true`. `ownEntry` (used by the update and next-task --task allowances) excludes reconciled entries; `self_created` still counts them. `created` output keys are unchanged.
- **AC22** In `jobFields`, a propose-kind job gets `session` only when `claim.agent` equals the job's agent.
- **AC23** `open()` checks only the twelve v2.3 keys and records `send.proposeLimitsFault`. In flush, a first send of a proposal against such a server stays `queued` with `lastError` "Task&I capabilities: limits is missing title" and the rest is delivered. A resend is not blocked.
- **AC24** A create result whose task_id is a ledger id (another key), the claimed task or the effective task is thrown as `malformed_response`, so the job goes uncertain. `assign: "agent"` entries are exempt from 180-day pruning. `selfCreatedTitle`: an A-mode offer whose title matches the titleNorm of a live agent-assigned create job is released as `self_created`.
- **AC25** `SECRET_PATTERNS` are the BLOCK regexes from `devcontainer/git-hooks/vibe-content-scan.sh` (github-pat, openai-key, aws-access-key, private-key), with `gho_` added. The generic secret-assignment rule is not included, since the spec lists only these four. They apply to title, next_action and notes in `validateProposal`, which exits 1 with `contains_secret: <field>` before any state is touched (`--check-argv` refuses too).
- **AC26** A repeat key that is not a plain identifier gives `invalid repeat: unknown key`. `PROPOSE_NEEDS_DESCRIPTOR(kind)`. The `SELF` symbol is replaced by a destructured `{claimed, self}`.
- **AC27** Harness and docs wording, as specified.

## Commands
- `python3 code-check.py` → 0
- `python3 .vs/cycle-2/scratch-tests/scratch_cycle2.py < /dev/null` → 0 failures
- `python3 smoke-test.py < /dev/null` → 1. All 6 failures are listed below; none come from earlier tasks (checks_54: 149/149).

## Remaining smoke failures
1. **checks_61 AC5 (3 checks): create retry after a resend receipt_collision.** These assert cycle-1 behaviour that AC20 reverses (retry must now be refused when noRetry is set). The addendum changed this behaviour.
2. **checks_63 AC15 "duplicate key moved with the retitle".** The test contradicts itself. Its previous check asserts titleNorm == "brand new, title" (which passes), then expects "brand new title" (no comma) to be a duplicate. The spec's titleNorm keeps interior punctuation. This is a Tester issue.
3. **checks_63 AC22 update case.** The persona of an update on the claimed task is the claim's agent (spec §Wire: "resolved at enqueue as for ask/comment"; cycle-1 AC10). So with a codex claim the job's agent is codex, the agents agree, and `session` is sent; the body shown has `agent: codex`. The test assumes `VIBE_AGENT` wins. Spec conflict or Tester issue: if the evaluator wants VIBE_AGENT to win, that changes AC10/AC1.
4. **checks_63 AC23 "complete works without the proposal limits".** This fails identically with every limit present. The fake server answers `complete` with the fixture's task, not the requested `project`, so the client's echo check reports malformed_response. Tester/fake-server issue, unrelated to AC23.

Also: the cycle-1 scratch test's AC2 `repeat:null` on the claimed task, and AC10 notes on the claimed task, now fail by design (AC15/AC16).
