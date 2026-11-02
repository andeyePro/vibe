# Spec critique, task_061, cycle 1

Read: spec.md, taskandi-client.mjs (outbox/poll/main), the brain2 brief "Contract v2" plus "confirmation and amendments".

## Concerns

1. [Shapes, `next_task` result] BLOCKING. Draft residue: "title (<= id... use LIMITS.text)". A Generator and a Tester will pick different limits. Fix: write "title: non-empty string <= LIMITS.text". Also name the 32000 body cap as a constant (for example `LIMITS.body`) so tests can import it.

2. [Shapes, "task ref"] BLOCKING. "task ref" is used in the `next_task` result and in `open_children[].task` but never defined. The binding task is only text <= LIMITS.id today. Fix: state exactly what is accepted (the `ABBR-<n>` and `taskandeye://node/<uuid>` forms from the brief, or simply "string <= LIMITS.id matching the stableKey class") and use it for `--task`, `claimed.task`, and the result fields.

3. [Shapes, all "ISO string" fields] BLOCKING. Only `started_at` has a stated format (Z only, <= 64 chars). `lease.until`, `hardDeadline`, `latest_start`, `seen_at`, `answered_at` and `claimedAt` just say "ISO string". Does that allow offsets such as +01:00? Date-only values? Impossible dates such as 2026-02-31T00:00:00Z (the regex accepts them)? Fix: define one `isoUtc()` rule: the regex plus a round-trip through `new Date()` that must produce the same calendar fields. Use it everywhere, and say whether offsets are refused. AC4 and AC6 "bad lease.until" and "non-ISO" tests then have one meaning.

4. [AC1, v1-pinned behaviour] BLOCKING. A v1-pinned binding is said to keep v1 behaviour "exactly", but nothing says what `next-task`, `complete`, `release`, `enqueue comment` and `enqueue record_time` do under v1. The v1 fixture does not advertise them. Fix: say they are refused with a usage-style error (exit 1, no transport call, nothing queued) naming the revision. Also say what `--task` and the claimed-task rule do under v1 (suggest: `--task` refused, as v1 had no redirect).

5. [Design "State file", AC5, AC9] BLOCKING. Migration of already-queued jobs. Existing jobs store `binding = digest({endpoint, task, contractRevision})`. Once the default revision changes from v1 to v2.1, every v1 job queued before the upgrade has a stale binding. A v1 `ask` payload with `to` and no `reversible` would also be dispatched into a v2.1 server. Fix: specify the outcome. Suggest: a queued job whose binding digest or payload revision no longer matches is not dispatched, stays `queued` or goes to a named blocked state, and `status` shows a reason. Add one AC with a state-file fixture saved from v1.

6. [All direct calls: `next_task`, `complete`, `release`, `poll`] BLOCKING. Failure modes are unspecified. There is no outbox for these calls, so what happens on:
   - transport error or timeout;
   - a malformed result;
   - JSON-RPC error;
   - tool-level `isError`;
   - a `complete`/`release` request that was sent but whose reply was lost (the server state is unknown)?
   Fix: give one table. Suggest: exit 1, a single stderr line, no stdout JSON, and `claimed` unchanged. For `complete`/`release` with a lost or malformed reply, the message says "outcome unknown", and `claimed` is kept. Add ACs that check exit code, stdout empty, and state-file bytes unchanged.

7. [Output shapes, AC6 vs AC8] BLOCKING. Contradictory printed JSON. AC6 prints `{"bound":true,"task":null}`, which is `bound` merged with the result. AC8 prints `{completed:true,state:...}` with no `bound`. A well-formed task result is just "printed". Fix: state one rule, for example "stdout is one compact JSON object `{bound:true, ...result}`", and write out all five cases (task, null, completed, refused-with-children, released). Also give the exit code for `complete` refused with `open_children`. It is a valid server reply, so suggest exit 0, but say so explicitly.

8. [AC6, AC8, AC3] BLOCKING. Precedence between usage errors, unbound fallback and task-targeting is undefined. Examples:
   - Unbound plus missing `--session`: usage error, or file-fallback?
   - Unbound plus `--task X`: the claim cannot be checked, so is X accepted or refused?
   - Unbound `enqueue` with `--task`?
   Fix: set an order: (1) argument syntax/usage errors always win, exit 1; (2) then the unbound check returns the fallback and ignores the targeting rule; or alternatively refuse. Pick one and test it. Also state that the exit code for every "usage error" is 1 (main sets exitCode 1 on any throw) and the message starts with `usage:` or names the flag.

9. [Design "Task targeting", AC6] BLOCKING. A second `next-task` while a claim exists is undefined. Does it overwrite `claimed`, and does that drop the previous task's targetability without a `release`? What if the new task differs? What if `claimed` is in state but the lease has expired (the client has no timing logic)? Fix: say `next-task` replaces `claimed` unconditionally (the server owns the lease), and that an expired local claim is still accepted until `release`/`complete`/replacement. State this plainly in the docs and test it.

10. [AC7, "Owner-only answers"] BLOCKING. Poll storage is under-specified. "v1 record shape plus new fields": the stored field names are not listed. Name them: `owner_answer`, `seen_at`, `answered_at`. Several cases are also open:
    - A non-owner answer and an owner answer for the same `ask_id` with different content: does v1 conflict detection fire and block the run, or is the non-owner one excluded? Suggest: conflict detection is over owner answers only; non-owner answers are stored but never conflict.
    - Duplicate `ask_id` inside one page.
    - What `poll` prints: the key for `ignored` and where it sits. "newAnswers: 2" is not tied to a full output object.
    - Does the cursor advance when all answers are ignored?
    Fix: list the exact poll output keys and add the cases as ACs.

11. [Shapes table, AC5] BLOCKING. Schema validation is incomplete. The table lists required/optional name sets but not the per-property JSON types. The code has a type map (`TOOL_TYPES`). A fixture with `order: "string"` or `reversible: "integer"` is a different failure from an extra field. Also unsaid:
    - Must `required` equal the set exactly (so a fixture requiring an extra field fails) or merely include it?
    - Is validation per tool or for the whole tool list (a v2.1 fixture lacking `complete` must not block `flush`)?
    - What is the exit code of a pre-dispatch failure, and which job states?
    Fix: add the type column to the table, say "required set must equal, properties must equal, types must match", validate lazily per tool, and say that on a pre-dispatch failure flush exits 1 with `PREDISPATCH` and jobs stay `queued`.

12. [Design "Two kinds", Shapes] BLOCKING. `usage` / `taskandi-usage.mjs` is in scope in the text (`--task REF`) but the file is not listed as a change target, there is no AC for `usage --task`, and the spec does not say how a record_usage payload gains `task` (a cycle-0 `record_usage` payload was task-less). Fix: add an AC (usage default carries binding task; `--task` accepted only for binding/claimed; the usage CLI is listed as in scope).

13. [Design "Revisions" vs brief] MINOR. Contract drift to confirm:
    - The brief's `next_task` request is `{agent}` plus `session`. The spec adds `task` (binding). That is reasonable for a subtree-scoped server, but it is a vibe invention. Mark it as such in the docs, or drop it.
    - The brief says `list_asks` answers originally carried `answered_by`; amendment 5 adds `owner_answer` and does not say `answered_by` is removed. Exact-key refusal would reject a live server that still sends it. Fix: record the choice (strict, per "exact keys") as a decision in the docs and flag it as a risk.
    - `hardDeadline` is camelCase while `latest_start`/`effective_priority` are snake_case. This is in the brief, so keep it, but document it deliberately.

14. [Out of scope, test edits] MINOR. The one allowed edit to `checks_28`/`checks_29` ("add contractRevision to fixture configs that exercise v1 shapes") has no enforcement. Fix: require that `git diff` of those two files consists only of added lines containing `contractRevision`, and have the Evaluator check it. Also, the CLI usage string changes. A grep of checks_28/29 shows `"usage:"` substring checks only (checks_29 line 231), so that one is safe. Mention it so the Generator does not worry.

15. [AC4, AC2] MINOR. Details to nail down:
    - AC2 lists a refusal for missing `reversible` only. The other required keys (`question`, `default`, `order`, `estimate_minutes`, `remaining_minutes`) also need a missing-key refusal. Say "each required key missing".
    - Option limits (`LIMITS.options`, `LIMITS.option`) are inherited from v1 but not restated; restate them.
    - `seconds` of 0, and the maximum (safe integer).
    - `started_at` in the future.
    - Empty `options` array.
    - AC4 "exactly `text`": say whether a non-string `text` and an empty string are refused (the rules say non-empty).

16. [AC11] MINOR. "documents every v2.1 call, the exact schemas" is not mechanically checkable as written. Fix: the Tester greps `docs/taskandi-client.md` for each tool name, each required field name, the strings `vibe-agent-exchange-v2.1` and `vibe-action-window-fixture-v1`, and the three CLI commands. "TODO.md task_061 closed" can only be checked after the commit; move it to the Evaluator's pass step.

17. [AC12] MINOR. "contains no question/answer text" needs seeded sentinel strings in a test (use a unique marker in question, answer, comment text, and body, then assert absence from `status` output and stderr). Also say whether `next-task` stdout may contain `body`. It must, since the harness needs it. Add a note that `body` is untrusted data (it can be written by others), as the brief's prompt-injection rule says; consider printing it under a key the harness can treat as data.

18. [AC5, malformed ask result] MINOR. "missing or malformed result makes the job uncertain". Say whether `placed` outside {subtask, thread}, extra keys, and a non-string `ask_id` are malformed (they should be, by "exact keys"), and test one of each.

19. [AC9] MINOR. "killed invocation becomes uncertain" is a v1 invariant. Say it is re-tested for the new kinds by a fixture that simulates the kill (state file with a `dispatching` job), and that `reconcile --action done` also works on the new kinds.

## Verdict

revise

## Iteration 2

Read: revised spec.md, iteration-1 critique, taskandi-client.mjs (TOOL_CONTRACT, readState, bindAnswers, main/argValue), checks_28 and checks_29 fixture lines.

### Iteration-1 BLOCKING concerns

1. `next_task` title limit: resolved (title is text, LIMITS.body named).
2. task ref undefined: resolved (Definitions give the regex).
3. Timestamps: resolved (`utcTimestamp` with round-trip, Z only).
4. v1 behaviour of new commands: resolved for commands (exit 1, named stderr). Not fully resolved for `record_usage` (see new concern 2).
5. Pre-upgrade queued jobs: resolved (BINDING_CHANGED, `staleBindingKeys`, AC9). Residual gap in new concern 6.
6. Direct-call failures: resolved (before/after-send rules, "outcome unknown").
7. Printed JSON shapes: resolved (all five cases written out, exit 0 for open_children).
8. Precedence: resolved by the 7-step order, but step 1 conflicts with v1 (new concern 1).
9. Second `next-task`: resolved (replace, no local expiry).
10. Poll storage and output: resolved (stored keys, `ignored`, cursor rule, duplicate ask_id).
11. Schema validation: resolved (type column, required set equality, per tool, PREDISPATCH exit 1).
12. Usage importer: resolved (AC11).

### Concerns

1. [AC10, Out of scope] BLOCKING. AC10 cannot be met. It says the diff of checks_28/29 has "no removed lines", but both files build their configs with `contractRevision: CONTRACT_REVISION` (checks_28 line 59, checks_29 line 53). Once `CONTRACT_REVISION` is v2.1, pinning to v1 means changing those lines to `LEGACY_CONTRACT_REVISION`, which is a removal plus an addition. Also, step 1 of the precedence order validates payloads "regardless of binding", so an unbound project validates against the default v2.1 rules. checks_28 line 71 enqueues `{to:'owner', question, default}` in an unbound project and expects `bound === false`. That now fails as unknown key `to`, and the fix is a payload edit, not a `contractRevision` addition. Fix: replace the diff test with an explicit allow-list. The only permitted edits to the two files are (a) lines containing `CONTRACT_REVISION` changed to `LEGACY_CONTRACT_REVISION` (plus its import), and (b) unbound-project v1-shaped `ask` payloads rewritten to v2.1 shape. AC10 then checks that every removed line matches one of these two patterns. Alternatively say unbound payload validation uses the v1 rules, which is worse. Pick one in the spec.

2. [Task targeting, Shapes, AC4, v1] BLOCKING. "Every payload carries `task`" and "`record_usage` ... gains `task`", but v1 `record_usage` has no `task` property in its schema or payload (TOOL_CONTRACT line 15) and the spec says v1 behaviour is kept "exactly". A Generator who adds `task` under v1 breaks v1 fixture argument checks, and one who does not contradicts AC4/AC11. Fix: state that under v1 the `record_usage` payload is exactly the v1 key set (no `task`), and that `usage --task` under v1 is a revision-gate error. Also state that `ask` under v1 keeps `task` (it already has it).

3. [Order of checks] MINOR. Step 1 validates payloads before `loadConfig`, but ask validation depends on the pinned revision. Fix: say "payload validation uses the revision from the loaded config, or v2.1 when unbound; an invalid config exits 1 first in the case of both errors".

4. [AC3] MINOR. AC3 says `next-task` with another task is "refused the same way", but `next-task` has no `--task` flag, and the existing `argValue` parser silently ignores unknown flags. Fix: either drop `next-task` from AC3 or state that unknown flags are a usage error (exit 1, zero requests) for the new commands, and test `next-task --task X`.

5. [Shapes, `--session`] MINOR. "matching stableKey's character class" gives the Tester no literal. Fix: state the regex and length cap.

6. [Pre-upgrade, bindAnswers] MINOR. `answerBinding` also embeds the revision, so an unpinned binding with stored v1 answers fails `poll` with "answer binding changed". Say so in the docs, or state that it is the same remedy as for jobs (pin v1 or archive).

7. [AC9] MINOR. The old code digests an unpinned binding with `contractRevision: null`; AC9's "computed with revision v1 under an unpinned binding" is not what v1 code produced. Reword to "any binding digest that differs from the current one".

8. [Direct-call failures, AC13] MINOR. "Schema" failures for `next_task`/`complete`/`release` happen after discovery but before the request; AC8/AC6 test none of them. Add one AC line: a fixture lacking the tool, or with a wrong type, exits 1 with zero `tools/call` requests.

### Convergence check

Field names, flags, exit codes and stdout shapes are fully written out, so Generator and Tester converge, except for concerns 1, 2 and 4.

### Verdict

revise

## Iteration 3

Read: spec.md rev 3, iteration-2 critique, and the `CONTRACT_REVISION`, `to:` and `enqueue` lines in checks_28 and checks_29.

### Iteration-2 BLOCKING concerns

1. AC10 diff allow-list: resolved. The only lines that must change are checks_28:53 and :59, checks_29:44 and :53 (CONTRACT_REVISION to LEGACY_CONTRACT_REVISION), checks_28:71 (unbound ask with `to`) and checks_29:212 (symlink test, no config so unbound, payload with `to`). Rules (a) and (b) cover all of them. The remaining `to:` payloads (checks_28 lines 87-185) run under a v1-pinned config and need no edit. The `usage:` substring check at checks_29:231 survives the new usage string.
2. v1 `record_usage` has no `task`: resolved. The spec says v1 payloads are exactly the v1 key sets and that `usage --task` under v1 is a revision-gate error.

### Iteration-2 MINOR concerns

3 (check order vs loadConfig): addressed in precedence steps 1-2. 4 (unknown flags): addressed, and AC3 tests `next-task --task X`. 5 (session regex): addressed with a literal regex and length cap. 6 (answerBinding): addressed in "Pre-upgrade queued jobs". 7 (AC9 digest wording): addressed. 8 (pre-dispatch for direct calls): addressed by AC8b.

### Concerns

1. [AC11] MINOR. There is no AC that checks `usage --task` under a v1 pin exits 1 with the `requires contract` line. The Tester may add it from "Task targeting"; it is not worth a cycle.
2. [AC10] MINOR. "Every changed line" implies a `git diff HEAD` baseline. If the Tester's `checks_47` file is committed first, that is fine, because the diff is limited to the two named files. No change needed.

No new contradictions found. Precedence, printed shapes, exit codes and the AC set are consistent with each other.

### Verdict

pass
