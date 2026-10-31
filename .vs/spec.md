# task_066 — Task&I client: contract v2.3 alongside v2.2 — 2026-10-31 (rev 2 after Spec Critic)

## Task summary

Task&I has built contract v2.3. It is on the taskandeye branch `claude/exchange-2-20261031`: service b8121150, fixtures 8dd5c84e, and the record_usage follow-up 72578feb. None of it is pushed yet.

Sources of truth, in order:
1. `/brain2/andeye/Task&I-agent-exchange-fixtures/README.md`, sections "v2.3 changes" and "Decided". Where they conflict with older sections, these win.
2. The thirteen fixture files there.
3. This spec.

vibe's client (task_064/065) refuses any `capabilities.contract` other than v2.2, so it would refuse every call against a v2.3 service. This task makes the client speak both versions:
- **v2.2** exactly as today.
- **v2.3** with its safe retries, sequence cursor, ability to claim a named task, and server-published limits.

The `capabilities` answer chooses the version on each invocation, and the claim records it for the offline `decide`. The harness file gains one new use: claiming the linked task.

## Design decisions (binding)

### Revision handling
- **Negotiation.** `capabilities.contract` must be `vibe-agent-exchange-v2.2` or `vibe-agent-exchange-v2.3`. Any other value is the existing pre-dispatch failure. The answer decides every rule below for the invocation that made the call.
- **Capabilities schema per revision.** v2.2 keeps today's exact keys; a v2.2 answer carrying `limits` or `id_pattern` is malformed. A v2.3 answer has exactly `protocol`, `contract`, `grade`, `calls`, `limits` and `id_pattern`.
  - `limits` has exactly these keys: `unit` = `"code_points"`, `id` (int), `id_unit` = `"utf16_code_units"`, `request_bytes`, `question`, `default`, `options`, `option`, `ask_post`, `comment`, `summary`, `reason`. All are positive integers.
  - `id_pattern` must equal the client's usable-id pattern source exactly. Any mismatch is a pre-dispatch failure (exit 1, nothing sent).
- **Binding digest unchanged.** The digest keeps the literal `contractRevision: 'vibe-agent-exchange-v2.2'`, the descriptor binding's protocol pin. The negotiated revision never enters it.
  - Queued jobs, stored answers and pinned fingerprints stay valid across a v2.2↔v2.3 switch.
  - The digest for a fixed descriptor is byte-identical before and after this task, and a golden hex value is asserted.
- **Where the revision is recorded.**
  - `state.lastContract` is set on every successful `capabilities` call.
  - `claim.contract` is set by `next-task`.
  - Each job records `sentRevision` in the same write that marks it `dispatching`.
  - `decide`, which may send nothing, reads `claim.contract`.

### Frozen wire bodies and request_id (v2.3 writes)

- At enqueue, every outbox write job (`ask`, `comment`, `record_usage`, `record_time`) gets `requestId`: a lowercase UUID v4 from `crypto.randomUUID()`. It is stored on the job outside `payload` and outside the dedup digest.
- **Freezing at first dispatch.** The first dispatch to a v2.3 server builds the exact wire body: fields, `session` resolved now, `agent`, `connection`, `action` and `request_id`. That body is stored on the job as `sentBody` (the serialized JSON string) in the same write that sets `dispatching`. Every later v2.3 attempt sends `sentBody` byte for byte; nothing is recomputed. Bodies sent to v2.2 are built as today and are never frozen.
- **Outcome-unknown on v2.3.**
  - Applies to: a lost response, a timeout, socket loss after send, a non-JSON body, an unrecognised status, or a 200 that fails the schema.
  - The job goes back to `queued` with `lastError` and `attempts += 1`.
  - The next v2.3 flush resends `sentBody`.
  - An *attempt* is one send that ended outcome-unknown; nothing else counts. After 5 attempts the job becomes `uncertain`, as before.
  - Job order is unchanged, and flush still stops at the first outcome-unknown or try-later result.
- **Crash.** A job found `dispatching` at startup with `sentRevision` v2.3 goes back to `queued` and keeps its `sentBody`. With v2.2, or no `sentRevision`, it becomes `uncertain` as today.
- **Downgrade.** If a job has `sentBody` (it was attempted on v2.3) and the current flush negotiates v2.2, the job becomes `uncertain` with `lastError: "attempted on v2.3; the server now speaks v2.2, so a resend could duplicate"`. No request is sent for it.
- **Upgrade.** A job that is `uncertain` from a v2.2 attempt is never retried automatically. `reconcile --action retry` on it, when the next flush is v2.3, sends once with its `requestId` and freezes `sentBody`.
- **receipt_collision.**
  - On a first send it means the `requestId` is already used: the job becomes `refused` (`receipt_collision`).
  - On a resend it means the first send *was* applied with a different body. That can only happen if `sentBody` changed, which the client never does. The job becomes `uncertain` with that explanation and is never retried.
- `request_id` is never sent on reads (`capabilities`, `next_task`, `list_asks`, `ask_status`) and never to a v2.2 server.

### complete / release on v2.3
- The control flow is reordered: run `capabilities` (open), then check `pendingDirect`, then send.
- Before sending, `pendingDirect` is written as `{call, task, at, requestId, sentRevision, fieldsDigest}`, where `fieldsDigest` is the digest of `{task, summary|reason}`.
- If a `pendingDirect` from v2.3 exists for the same call and task:
  - **Same text:** the command resends with the same `requestId` and settles on the replay (claim cleared or kept as today; pending record cleared on any definite answer).
  - **Different text:** exit 1, nothing sent, the record kept.
  - **A v2.2 `pendingDirect`:** blocks as today.
- A `receipt_collision` on a resend keeps the pending record, because the first send was applied.

### Error classes on v2.3

Every 409 now means nothing was applied:

| Code(s) | Job outcome | Effect on flush |
|---|---|---|
| `connection_revoked` | back to `queued`; prints the existing revoked message | stops |
| `connection_unavailable`, `stale_context`, `sync_required`, `lease_held` | back to `queued` | stops |
| `use_native_connection`, `scope_missing`, `invalid_request`, `wrong_scope`, `wrong_thread`, `unknown_ask`, `not_assigned` | `refused` | continues |
| `receipt_collision` | see above | — |
| 400 `invalid_request`, 403 `connection_scope`, 405 `method_not_allowed`, 421 `wrong_origin` (exactly-formed) | nothing applied: try-later, except `invalid_request`, which is rejected | per class |

v2.2 keeps its table unchanged.

### record_usage `at`
- At import, each row gets `at` = the newest timestamp among the messages the row covers. That is the Claude record's `timestamp` field or the Codex event time, as integer ms. If no covered message has a timestamp, `at` is absent. There is no clock fallback.
- `at` is in the payload and therefore in the dedup digest:
  - re-enqueueing the same key with the same `at` is a dedupe;
  - re-enqueueing it with another `at` is a `KEY_CONFLICT`.
- At first v2.3 dispatch, the frozen body applies these rules once:
  - `at` older than 30 days is omitted, with a stderr notice `usage row <key>: at older than 30 days, sent without it`;
  - `at` more than 60 s in the future is clamped to now + 60 s.
- `at` is never sent to v2.2. `JOB_SHAPES` gains `at` as an optional `record_usage` field, so `jobIntact` accepts it.

### list_asks sequence cursor (v2.3)
- The per-task cursor is `{seq}`. `since` is sent as the stored `seq` exactly, with no overlap.
- A valid v2.3 page has exactly the keys `task`, `seq` and `asks`. `now` is forbidden. Every ask carries `seq` (a positive integer), and:
  - each ask's `seq` is greater than `since`;
  - the asks' `seq` values strictly increase;
  - the page `seq` equals the last ask's `seq`, or equals `since` when `asks` is empty.
- Any violation is malformed: exit 1, cursor and answers unchanged.
- A stored v2.2 `{now}` cursor is not used on v2.3. The first v2.3 poll of a task sends `since: 0`, and `(task, ask_id)` dedupe absorbs repeats. A v2.2 poll ignores a stored `{seq}` and starts its own `{now}`.

### next_task (v2.3)
- **Offer schema.**
  - Adds `action` (a string, may be empty; always present on v2.3).
  - `latest_start` (optional ms) is now meaningful.
  - `spent` is `{windows, tokens, cache_read}`: integers, with `cache_read` required on v2.3.
  - `allowance.windows` and `allowance.tokens` are finite nonnegative numbers, so fractions are allowed.
  - `spent.windows` stays an integer.
- **`next-task --task REF`.**
  - REF must be the effective task or the claimed task, per target resolution. Otherwise it is a usage error with zero requests.
  - On v2.3 the call sends `task`.
  - **Claim.** The response's `task` must equal REF. If it differs: exit 1, no claim, and one `release` is sent for the returned task (reason `vibe asked for another task`).
  - **Refusal** (`{task: null, reason}`, where reason is one of `unsafe_id`, `not_assigned`, `closed`, `provisional`, `on_hold`, `blocked`, `open_children`, `waiting_on_ask`, `over_budget`, `leased`):
    - prints `{"bound":true,"channel":"taskandi-http","task":null,"reason":"<reason>"}` and exits 0;
    - leaves `state.claimed` byte-identical, including a claim on another task;
    - writes no body file.
  - A `reason` is valid only when `--task` was sent, and `{task:null}` without `reason` is valid only when it wasn't. Anything else is malformed.
  - **v2.2 server:** `next-task --task` sends no `next_task` request. It prints `{"bound":true,"channel":"taskandi-http","task":null,"reason":"contract_v2_2"}` and exits 0.
  - **MCP binding or unbound:** today's behaviour (usage error under MCP; the file-fallback line when unbound).

### decide
- `pending_tokens` counts input + output + cache_write when `claim.contract` is v2.3, and input + output + cache_read + cache_write when it is v2.2.
- Fractional allowances work in both ratios.
- `latest_start` from the claim and real `deferred` values now arrive from the server. The existing rules apply unchanged, and tests cover them.

### Limits from the server
- Enqueue stays offline and checks the client's own limits as today.
- At flush, and before `complete`/`release`, on v2.3, each job's text fields and final body are checked against the server's `limits`:
  - a job over a stricter server limit becomes `refused` (`over_server_limit`) with no request;
  - a looser server limit changes nothing.

### Harness file
Step 2 of `taskandi-harness.md`:
- **Linked task** (an effective task is set): first run `taskandi-client next-task --agent <agent> --session <session> --task <effective task>`.
  - A claim means the linked task is worked with a full claim, so complete and release work.
  - A refusal prints its reason. Look the reason up in a table that stops or skips work; none of them say "work the task without a claim":

    | reason | action |
    |---|---|
    | `unsafe_id` | stop: tell the owner to rename the task |
    | `not_assigned` | do not work it; fall to A-mode |
    | `closed`, `provisional`, `on_hold`, `blocked`, `open_children`, `waiting_on_ask`, `over_budget`, `leased` | do not work it; note the reason in the session file and fall to A-mode |
    | `contract_v2_2` | the old no-claim linked mode |

- **No linked task:** A-mode runs `next-task` without `--task` as today.

### Fixtures
- Copy the thirteen v2.3 files byte for byte to `smoke/fixtures/taskandi-v23/`, with a `PROVENANCE.md` giving the commits b8121150, 8dd5c84e and 72578feb, the date, and the sha256 of each file. checks verify the hashes.
- The v2.2 copies stay as they are.
- Tests use a fake v2.3 server that serves these fixtures and also replays by `request_id`.

## Acceptance criteria

- **AC1 Negotiation.**
  - Both revisions are accepted, and `state.lastContract` is set to the answer.
  - `v2.4` is refused before any other request.
  - A v2.2 answer with `limits` is malformed.
  - A v2.3 answer is refused before any other request (exit 1) if `limits` is missing a key, has an extra key, has `unit` other than `code_points`, or has `id_pattern` different from the client's.
- **AC2 Binding digest.** A fixed descriptor's fingerprint equals its golden hex. Jobs queued before a switch flush on both revisions without `BINDING_CHANGED`.
- **AC3 Wire per v2.3 fixture.** For each of the thirteen fixtures:
  - The request's sorted key set equals the fixture request plus `connection`, with `request_id` exactly on the six writes and never on reads.
  - stdout or the stored result matches the fixture response.
- **AC4 Frozen body and resend.**
  - A comment is sent with session S1, its response is dropped, and the claim then changes to S2. The next flush resends a body byte-identical to the first, and the fake server holds one comment.
  - After 5 outcome-unknown attempts the job is `uncertain`.
  - `receipt_collision` on a first send makes the job `refused`; on a resend, `uncertain`.
- **AC5 Crash, downgrade and upgrade.**
  - (a) A job left `dispatching` with `sentRevision` v2.3 resends its `sentBody`, and the server has one row.
  - (b) A queued job with `sentBody`, flushed against v2.2, becomes `uncertain` with zero write requests.
  - (c) A v2.2-uncertain job is never retried automatically on v2.3. `reconcile --action retry` sends it once with its `requestId`.
- **AC6 complete/release on v2.3.**
  - An unknown outcome leaves `pendingDirect` with a `requestId`. The same command resends that id and settles: one completion server-side, claim cleared, pending cleared.
  - The same command with different text exits 1 and sends nothing.
  - A collision on a resend keeps the record.
  - A v2.2 pending record blocks as today.
- **AC7 v2.3 error table.** One test per code and status in the table, asserting the job outcome, the flush stop or continue, and the exit code.
- **AC8 Sequence cursor.**
  - Each of these exits 1 with no cursor movement: an ask `seq` ≤ `since`; a page `seq` above the last ask's; non-increasing ask seqs; an empty page whose `seq` ≠ `since`; a `now` key; a missing per-ask `seq`.
  - A valid page stores `{seq}`, and the next poll sends exactly that.
  - Switching revisions resets as described, with no answer counted twice.
- **AC9 Offer schema.** These are accepted on v2.3: `action`, `spent.cache_read`, fractional `allowance.windows: 0.5`, and `latest_start`. A missing `action` or `spent.cache_read` on v2.3 is malformed. The v2.2 offer schema is unchanged.
- **AC10 `next-task --task`.**
  - One test per refusal reason: exit 0, the exact JSON, `state.claimed` byte-identical (also with a pre-existing claim on another task), no body file.
  - The claim case stores a claim.
  - A wrong-task claim response exits 1 and sends one `release`.
  - The `reason`/`--task` pairing rules are enforced.
  - A REF that is neither the effective nor the claimed task is a usage error with zero requests.
  - A v2.2 server gives the `contract_v2_2` output and no `next_task` request.
- **AC11 `at`.**
  - An importer row's `at` equals the newest covered timestamp, and is absent when no covered message has one.
  - Re-enqueue with the same `at` is a dedupe; with another `at`, a `KEY_CONFLICT`.
  - `at` is never sent to v2.2.
  - An `at` older than 30 days is omitted at first dispatch with the notice, and a future one is clamped. Both are frozen thereafter.
- **AC12 decide.**
  - With a pending usage job of input 10, output 20, cache_read 500 and cache_write 5, `pending_tokens` is 35 on v2.3 and 535 on v2.2.
  - `allowance.windows: 0.5` with `--windows-used 1` gives `stop`/`cap`.
  - `deferred: true` with all other conditions met gives `proceed`.
  - A server `latest_start` in the past counts as passed.
- **AC13 Server limits.** A v2.3 server reporting `comment: 100` makes a queued 500-character comment `refused` (`over_server_limit`) with zero write requests. `comment: 9000` changes nothing.
- **AC14 Harness.**
  - `taskandi-harness.md` step 2 contains the linked-task command with `--task <effective task>` and a row for each of the ten reasons plus `contract_v2_2`. None of the rows says to work the task without a claim.
  - `--check-argv` accepts the new command line.
  - The word cap and checks_54 still pass.
- **AC15 v2.2 unchanged.** checks_28/29/47/50/52/53/55 pass unchanged, except for checks named here as changed.
- **AC16 Docs and gates.**
  - `docs/taskandi-client.md` gains a v2.3 section covering: negotiation, request_id and frozen bodies, resend rules, the seq cursor, `next-task --task`, `at`, and server limits.
  - CHANGELOG entry.
  - MANUAL-TESTS Tests 69 and 70 note v2.3.
  - Fixture hashes are verified.
  - `python3 code-check.py` exits 0 and `python3 smoke-test.py < /dev/null` exits 0. New tests go in `smoke/checks_58_taskandi_v23.py` (split if needed), called from `runner.main()`.

## Out of scope

- Dropping v2.2.
- Any server change.
- Writing the Strategy policy (owner-only).
- Sending `at` for the Codex delta path when its events carry no time (the field is simply absent).

## Model plan

- Planner and Evaluator: Opus 5.5.
- Spec Critic: sonnet.
- Generator: opus.
- Tester: sonnet.
- Fable rung: not pre-authorised.

## Rev 2.1 — critic iteration 2 minor fixes (folded before build)

- **M1.** `pendingDirect` for a v2.3 `complete`/`release` stores the frozen `sentBody` (session included), as jobs do. A resend with the same command sends `sentBody` byte for byte. "Same text" means the new `{task, summary|reason}` equals the one inside `sentBody`. `pendingDirectMore` records carry the same fields. The `open_children` 409 on v2.3 maps exactly as on v2.2 (exit 0 output, claim kept), and it clears the pending record because nothing was applied.
- **M2.** `decide` reads `claim.contract`. If that is absent it uses `state.lastContract`, and if that is absent too, v2.2. A renewal whose negotiated revision differs from `claim.contract` replaces `spent` instead of taking the per-dimension maximum, because the two revisions count tokens differently.
- **M3.** The fake v2.3 server lives in a helper module `smoke/taskandi_v23_server.mjs` so `checks_58` stays at 1,500 lines or fewer. `status` gains `lastContract`. One test asserts every client limit constant is ≤ the matching value in the v2.3 `capabilities.json` fixture.
