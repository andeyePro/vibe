# Spec critique: task_066 (Task&I client, contract v2.3 alongside v2.2)

Reviewed: the draft spec, the exchange README ("v2.3 changes", "Decided"), the v2.3 fixtures (capabilities, list_asks, retry, record_usage, next_task, next_task_claim, over_budget, ask_status, complete, ask, release, record_time, comment), `devcontainer/taskandi-client.mjs`, `taskandi-usage.mjs`, `taskandi-harness.md`, the task_064 spec, and the smoke tests that pin v2.2 behaviour.

Overall: the draft has the right shape (negotiate per invocation, add `request_id`, switch the cursor, add `--task`). It has not worked through four things the code makes unavoidable. The retried body must be byte-identical. A v2.2<->v2.3 switch between attempts must never double-send. `decide` runs without negotiating. The refusal fallback in the harness defeats the server's own refusals. Several of its rules are also not implementable as written. Verdict at the end.

## Concerns

### 1. BLOCKING: the binding digest pins `contractRevision` to v2.2

`bindingDigest` hashes `config.contractRevision`, and `loadDescriptor` sets that to the constant `HTTP_CONTRACT_REVISION = 'vibe-agent-exchange-v2.2'`. The task_064 spec pins the digest as `digest({kind:'descriptor-http', workspace, task, contractRevision:'vibe-agent-exchange-v2.2'})`.

If the implementation bumps that constant, or makes it per-negotiation, every queued job, stored answer and supervisor fingerprint reports `BINDING_CHANGED` on upgrade. A v2.2<->v2.3 server switch would do the same.

Fix: the digest keeps the literal v2.2 string. The negotiated revision is a separate value (`state.lastContract`, plus a per-claim `contract`). Add `HTTP_CONTRACT_REVISIONS = ['vibe-agent-exchange-v2.2','vibe-agent-exchange-v2.3']` and leave `HTTP_CONTRACT_REVISION` exported and unchanged. Tests in checks_50/52 import or assert it.

Proposed AC: "The binding digest for a fixed descriptor is byte-identical before and after this task (golden hex asserted). Queued jobs written by the pre-task code flush without `BINDING_CHANGED` against a v2.3 server. Switching the server between v2.2 and v2.3 between two flushes raises no binding error."

### 2. BLOCKING: a retry is not byte-identical as designed, so legitimate retries become `receipt_collision`

The draft says `request_id` is "sent unchanged on every attempt". The body it labels is not stable. `jobFields(job, claim)` rebuilds `session` from the current claim at each dispatch. A comment or ask is first sent with session S1. The response is lost. The claim is then released and re-claimed with S2, or dropped. The retry carries a different `session`, or none, and the server answers 409 `receipt_collision`.

The client would classify that as `refused` (not applied). In fact the first attempt was applied. The operator's natural `reconcile --action retry` then creates the duplicate this feature exists to prevent.

The same problem applies to `at`. The draft clamps or drops it "at send time" (see 4), which also changes the body between attempts.

Fix: on the first dispatch, store the exact wire fields (`job.wire`: the final object minus `action` and `connection`, including `request_id`, `session`, `agent` and `at` as decided). Every retry resends `job.wire`. Dispatch re-checks that `job.wire` is the payload plus the permitted extras (tamper check). A queued job that never reached the wire keeps being rebuilt as today. Reconcile can then treat `receipt_collision` on a resent job as "the earlier send was applied". See 5 for the direct calls.

Proposed AC: "A comment is sent with session S1 and the response is dropped. The claim then changes to S2. The next flush resends a body byte-identical to the first (same session S1, same `request_id`). The fake server's replay returns the original response, the job is `done`, and the server holds exactly one comment."

### 3. BLOCKING: a version switch or a crash between attempts can double-send

The draft says "never to v2.2" and "existing uncertain jobs from v2.2 are never retried". It leaves out three states that exist in the code.

- **Downgrade.** A job is `queued` after an unknown outcome on v2.3 (attempts >= 1). The next flush negotiates v2.2, for example after a server rollback. It would resend the job with no `request_id`. A v2.2 server may have applied the first send, so this duplicates the write.
- **Crash while dispatching.** `recoverDispatching` (client.mjs:267, run inside every `withState`) turns any `dispatching` job into `uncertain`. A process killed mid-send on v2.3 would therefore never auto-retry, although the id makes it safe. It would also never be marked `queued` in a way a downgrade could distinguish.
- **Revision memory.** The draft does not say where "was sent to a v2.3 server" is recorded.

Fix: write `job.sentRevision = 'v2.3'` in the same state write that sets `dispatching` (that write already exists before the send). Rules:

- `recoverDispatching`: `dispatching` with `sentRevision` v2.3 becomes `queued` with `attempts` incremented. Otherwise `uncertain` as today.
- At flush, after negotiation, any `queued` job with `sentRevision === 'v2.3'` and `attempts > 0` against a v2.2 server becomes `uncertain` (message names the downgrade) before anything is sent. Nothing for it goes on the wire.
- A job never sent (`attempts` 0) is sent normally in either revision, with `request_id` only on v2.3.

Proposed AC: "(a) Kill the client mid-send on v2.3 (state `dispatching`). The next v2.3 flush resends with the same `request_id`, and the server has one row. (b) A job left `queued` after a timeout on v2.3, flushed against v2.2, becomes `uncertain`, with zero write requests to the v2.2 server. (c) A job first attempted on v2.2 (uncertain) is not retried automatically on v2.3. `reconcile --action retry` on it sends once with its enqueue-time `request_id`."

### 4. BLOCKING: the `at` decision and the "old row" rule are unsafe as drafted

The draft leaves "is `at` in the digest" open and also invents an enqueue-time fallback.

**Digest.** Decision: `at` is in the payload and therefore in the digest. The server treats `at` as one of the figures (a different `at` is `receipt_collision`), so a payload without it would not identify the row. The same-key different-payload check then catches a changed `at` locally.

**Fallback.** That decision makes the enqueue-time fallback ("else enqueue time") incompatible with the importer. A re-run that re-enqueues the same key gets a new `at`, which becomes `KEY_CONFLICT`. Today it is a clean dedupe. So: `at` is set only when the covered rows carry a parseable timestamp. It is never synthesised from the clock. With no timestamp, omit `at`, and the server uses its receipt time.

**30-day rule.** "A row older than 30 days at send time is sent without `at`" changes the figures. If an earlier attempt already carried `at`, the retry collides. Under (2) the frozen first-send body decides: if the first attempt carried `at`, retries keep it. If the first dispatch finds `at` older than 30 days, it is omitted and the omission is frozen. Print a notice ("usage row older than 30 days; recorded at receipt time"). A future `at` (more than 60 s ahead) is clamped once at first dispatch to the dispatch time and frozen.

**Wire per revision.** `at` and `request_id` must not go to a v2.2 server. Its validators likely reject unknown keys (task_064's body table says "must equal this table exactly"). Today `jobFields` spreads `payload`, so a stored `at` would be sent to v2.2. Strip by revision at body construction.

**Shape and tamper.** `JOB_SHAPES.record_usage` needs `at` as an optional key. `HTTP_PAYLOAD_KEYS.record_usage` and the importer must produce it. Otherwise `jobIntact` marks every such job `tampered_job`.

Proposed AC: "Importer rows get `at` equal to the newest covered message timestamp (ms integer) when one exists. With none, `at` is absent. Re-enqueueing the same key and payload is a dedupe. Re-enqueueing with another `at` is `KEY_CONFLICT`. A v2.2 server never sees `at` or `request_id`. Frozen `at` is resent byte-identical across retries. A row older than 30 days at first dispatch goes without `at` and emits the notice. A future `at` is clamped once."

### 5. BLOCKING: the `complete`/`release` resend design is not implementable in the current control flow, and mishandles collisions

- `finish()` calls `refusePendingDirect` before `open()`, so before the revision is known. The draft needs "on v2.3, resend instead of blocked". The order must change: read the pending record, `open()`, then decide. On v2.2 the block stays as today.
- The pending record must carry `requestId`, `sentRevision` and a digest of the sent fields (task, session, summary or reason). A resend is allowed only when the pending record's revision is v2.3, the current revision is v2.3, and the new command's fields match. If the operator runs `complete --summary` with different text, that is a different body for the same id. The result would be `receipt_collision` and the cleared pending record would hide that the first send was applied. Rule: mismatched fields fail locally (exit 1, nothing sent, pending kept) and say to repeat the same text or `reconcile --direct`.
- "pendingDirect is cleared on any definite answer" is wrong for `receipt_collision` on a resent record, because it proves the original was stored. Keep the pending record in that case, and tell the operator the earlier call was applied.
- Mixed `pendingDirectMore` records (different call or task) need the same fields. Say so.
- `park` data (`parkedAsks`, `budgetStopped`, `allowance`) lives in the pending record. A resend reuses it and does not recompute it.

Proposed AC: "complete with an unknown outcome on v2.3 leaves `pendingDirect{requestId,...}`. The same command resends the same id and settles on the replay response (claim cleared, pending cleared, one completion server-side). The same command with different text exits 1, sends nothing, and keeps the record. After a v2.2 unknown outcome the old block message still appears. A `receipt_collision` on a resend keeps the pending record."

### 6. BLOCKING: the `list_asks` cursor rules are looser than the fixture and can silently skip answers

The draft only requires "response `seq` >= `since`". README and fixture say: `seq` is the last returned `seq`, or `since` when nothing is new. Each ask carries `seq`, and answers come in answer order. A looser check lets a server (or a bug) return `seq` greater than the last returned ask's `seq`. The client then stores a cursor beyond answers it never received, and they are never fetched.

Fix: new schema for v2.3 `list_asks`, exact keys `{task, seq, asks}` with `now` forbidden. Each ask is the v2.2 ask shape without `answered_at` changes, plus `seq`, minus nothing else. Check, in this order:

1. Every ask `seq` is a safe integer > `since`.
2. The ask `seq` values are strictly increasing in array order.
3. If `asks` is empty, page `seq === since`. Otherwise page `seq === asks.at(-1).seq`.
4. `ask_id` is unique.

A violation is `malformed_response`, which is exit 1, and the cursor is not advanced. Keep answers-durable-before-cursor ordering. Compare-and-set must compare the revision-appropriate field (`seq` vs `now`). The existing check reads `.now` only.

On storage, `state.cursors[task] = {seq}` overwrites `{now}`. That is fine: a later v2.2 poll then sends `since: 0` and `(task, ask_id)` dedupe absorbs it. Say so, and test it in both directions.

Cursor `since` must be a nonnegative safe integer sent as a number (fixture: `0`). The "first v2.3 poll sends 0 after a stored `{now}`" rule in the draft is correct.

Proposed AC: "Fake server cases, each exit 1 with no cursor movement: seq below since, page seq above the last ask seq, non-increasing ask seqs, an ask with seq <= since, empty page with seq != since, a `now` key present, a missing per-ask `seq`. Valid page: cursor stored `{seq}` and `since` equals it exactly on the next poll (no overlap)."

### 7. BLOCKING: `next-task --task` details the draft misses

- **Claim left intact on refusal.** The existing `nextTask` does `if (task.task === null) delete state.claimed`. For `{task:null, reason}` after `--task`, that would drop the claim on a different task that is still leased. Rule: a refusal never touches `state.claimed` or the body file. (Plain `next-task` returning `{task:null}` keeps today's behaviour.)
- **Echo check.** A successful claim response must have `task === requested`. A mismatch is `malformed_response`, with no claim stored. The lease is already taken at that point, so do the existing hand-back (`release`) as the unusable-id path does.
- **Schema per case.** `next_task` response schemas become:
  - with `--task`: `{task:null, reason ∈ the ten}`, or a full offer.
  - without `--task`: `{task:null}` exactly (`reason` present is malformed), or a full offer.
  - an offer must carry `action`; a v2.2 offer must not.
- **Scope of `--task`.** Reuse the `targetFrom` rule: the id must be the effective (bound) task or the currently claimed task, else `USAGE`. With no effective task, a usable id is accepted.
- **Which bindings.** `--task` under an MCP binding is a usage error. When unbound, it returns the existing file-fallback result with exit 0 (the existing "same argv rules, then file-fallback" path).
- **v2.2 signal.** The draft says `--task` on v2.2 is "a usage error naming v2.3". The harness has to tell "this server cannot do it" from "next-task failed", and both would be exit 1. See 8 for the output I recommend. Exit code 1 is fine as long as the stderr line is stable and tested. Whatever is chosen, no `next_task` request goes out on v2.2.
- **`wrong_scope`** (409 for an id outside the subtree) is `rejected`: exit 1, no state change.
- Output for a refusal is exactly `{"bound":true,"channel":"taskandi-http","task":null,"reason":<reason>}`, exit 0. The draft has this right.

Proposed AC: "Ten tests, one per reason, each: exit 0, the exact JSON above, `state.claimed` byte-identical before and after (including with a pre-existing claim on another task), no body file written. A claim response naming another task: exit 1, no claim, one `release` sent. `{task:null}` without `--task` and `{task:null,reason}` without a requested task: malformed. `--task` equal to neither the effective nor the claimed task: usage error, zero requests."

### 8. BLOCKING: the harness fallback undoes the server's own refusals, and the call order wastes a lease

Draft: "a refusal prints its reason and the run falls back to the no-claim mode with that reason noted". The no-claim mode still posts comments, usage and time to the task and works it. For `over_budget`, `on_hold`, `blocked`, `closed`, `provisional` and `waiting_on_ask` that overrides exactly what v2.3 added these reasons to enforce (the over-budget fixture says the agent must not re-claim a parked task). It defeats the budget stop.

Fix, as a table in the harness file and in `docs/taskandi-client.md`:

- `over_budget`, `on_hold`, `blocked`, `closed`, `provisional`, `waiting_on_ask`, `not_assigned`, `open_children`: do not work the linked task. Report the reason and stop the Task&I part of the run (fall to TODO.md, or ask the user, as the harness's existing next-task-failure row does).
- `leased` (another session holds it): the owner or another agent is working it. Stop, same as above. If the user insists, they can start args mode, which does not claim.
- `unsafe_id`: Task&I steps are skipped, as for an unusable id today.

Ordering: today step 2 calls plain `next-task` first, which may lease some other task (90 minutes), and step 2(c) then releases it. On v2.3 with an effective task, call `next-task --task <effective>` first and skip plain `next-task`. To do that the harness must know the revision before it calls. Either the v2.2 case answers with a stable, parseable result (preferred: exit 0, `{"bound":true,"channel":"taskandi-http","task":null,"reason":"contract_v2_2"}`, no `next_task` sent, so the harness continues with today's 2(c)), or `status` reports `lastContract` (stale, so not recommended). Pick one and test it.

The existing harness prose tests (checks_54 pins "Never retry an uncertain delivery without reconcile evidence") must still pass. Keep that sentence. The `--check-argv` argv table needs `next-task --agent A --session S --task T`.

Proposed AC: "The harness prose has a reason table covering all ten reasons plus `contract_v2_2`, none of which says 'work the task without a claim'. `--check-argv` accepts `next-task ... --task T` and rejects `--task` with no value. A smoke test pins one stop-or-skip action per reason."

### 9. BLOCKING: `decide` makes no request, so "the negotiated revision decides" cannot apply to it

`decide` sends nothing unless an ask is open. The `pending_tokens` rule (cache_read excluded on v2.3) therefore has no negotiation to read. The draft's `lastContract` can be stale or absent (first run, or a state file from before this task).

Fix: `next-task` writes the negotiated revision into the claim (`claim.contract`). `decide` uses `claim.contract`, with `state.lastContract` as fallback and v2.2 as the final default when neither exists. A job's own `sentRevision` is irrelevant. Pending usage is summed with the claim's rule. On a renewal where the revision changed from the claim's recorded one, do not merge the old `spent` (tokens mean different things); take the new `next_task`'s `spent`.

Also v2.3 turns on two inputs that were dead under v2.2: `latest_start` (the service used to never send it) and `deferred` (always false). The decide code already branches on both (`before-latest-start`, `unseen`/`deferred`), so default-on-silence can fire for the first time. The draft has no AC for this. Add one.

Proposed AC: "With `claim.contract = v2.3` and a pending usage job (input 10, output 20, cache_read 500, cache_write 5), `pending_tokens` is 35. With v2.2 it is 535. With `latest_start` in the past, `defaults_allowed` true, a reversible ask unanswered and `deferred:true`, `decide` returns `proceed` / `default-allowed` (use the existing semantics, add the case). Fractional `allowance.windows: 0.5` with `windowsUsed: 1` gives ratio 1 and action `stop`/`cap`."

### 10. BLOCKING: the limits and `id_pattern` negotiation is incoherent as written

- "A stricter server makes the client use the server's number" cannot happen at enqueue, which is offline and runs before any capabilities call. It can only be applied at flush time and at `complete`/`release` time, to already-validated jobs. Say so: before sending, re-check each job (and the direct-call text) against the effective limit (the minimum of the client's and the server's). A job that exceeds it is refused locally as `over_server_limit` (class `rejected`, not sent, `body_too_large`-style).
- Define "own pre-send limits" explicitly: `id`, `request_bytes`, `question`, `default`, `options`, `option`, `ask_post`, `comment`, `summary`, `reason` (ten keys, all positive safe integers), plus `unit === 'code_points'` and `id_unit === 'utf16_code_units'`. Any other value, a missing key, or an extra key makes the capabilities response malformed (pre-dispatch failure). The v2.3 capabilities schema is exact-key `{protocol, contract, grade, calls, limits, id_pattern}`. The v2.2 schema forbids `limits` and `id_pattern`. Currently one constant schema serves both, and the contract must be peeked before conforming.
- `id_pattern` cannot be checked for "accepts nothing the server refuses" in general (regex inclusion). Do not compile and run a server-supplied regex. Decision: the string must equal `USABLE_ID.source` (the fixture value is `^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`, the same as the client's). Any other value is a pre-dispatch failure naming the mismatch.
- Add a test that every client limit constant is `<=` the number in `smoke/fixtures/taskandi-v23/capabilities.json`, so a fixture update that tightens a limit fails loudly.

Proposed AC: "A server reporting `comment: 100` makes a queued 500-char comment `refused` as `over_server_limit` with zero write requests. A server reporting a looser value (`comment: 9000`) changes nothing. `limits` missing a key, with an extra key, with `unit` other than `code_points`, or `id_pattern` other than the client's: exit 1 before any other request. v2.2 capabilities carrying `limits`: malformed."

### 11. MINOR: the error table per revision, and what counts as an attempt

- Make the error table a per-revision structure, so v2.2 literally keeps today's constant. For v2.3 the table differs only in `connection_unavailable` and `connection_revoked`, which become `later`.
- Add `405 method_not_allowed` to the exactly-formed non-200 bodies (README answer 1 says nothing applied). Today it falls to malformed, which is unknown, so a v2.3 write would go `uncertain` or be retried needlessly. `ERROR_STATUS` currently lists 409, 400, 421 and 403.
- Everything that is not an exactly-formed coded body is still outcome unknown on v2.3: lost response, timeout, redirect, 5xx and other non-JSON statuses, a malformed 200. "Every 409 means nothing applied" must not be read to cover those.
- `connection_revoked` as `later` requeues the job. Each later flush re-sends one request and stops. That is fine, and flush must still print the revoked message. It does not count as an attempt.
- Define the counter. `attempts` counts sends that ended outcome-unknown. A `later`-class result (any 409 or NOT_SENT) does not increment it. The 5th unknown makes the job `uncertain`, so 5 sends is the maximum. Five is reasonable. Flush stops at the first unknown, so one hung server costs one 15 s timeout per flush and cannot starve the rest. Keep that `break` behaviour. Order stays array order, so the stuck job is first next time and nothing overtakes it.
- Flush output: keep the existing keys. Count resendable unknowns under `requeued`, with a notice `<key>: outcome unknown; will resend with the same request id (attempt n of 5)`. Exit stays 0.
- `reconcile --action retry` on an `uncertain` job that carries a v2.3 id keeps the id and resets `attempts`. On a job `refused` as `receipt_collision` it mints a new id (the old id is bound to a different body) and requires the evidence text as today.

Proposed AC: "One test per code, v2.3 against v2.2: `connection_unavailable` and `connection_revoked` give `queued` on v2.3 and `uncertain` on v2.2. 405 `method_not_allowed` is `later` on v2.3 and is unchanged on v2.2. A 502 with an HTML body is unknown on both. Five consecutive timeouts on a v2.3 write give `uncertain` after the fifth send (assert the request counter is 5)."

### 12. MINOR: `request_id` details

- Generate with `crypto.randomUUID()` (lowercase v4). On dispatch, validate it against `UUID_SHAPE` and refuse `tampered_job` if it is not valid. Ids must be unique across jobs.
- State clearly that `next_task`, `capabilities`, `list_asks` and `ask_status` never carry `request_id`. The README lists writes only, and `next_task` is a read-like claim whose repeat is already idempotent per session.
- Do not add `request_id` to the dedupe digest or `payload`. The draft has this right.
- The draft's own AC2 ("request keys incl. `request_id` on writes only") needs adapting: the fixtures `ask`, `comment`, `record_time`, `release` and `complete` already carry a request id, and `next_task` does not. The test is: client body equals the fixture `request` plus `connection`, with `request_id` compared by UUID shape.

### 13. MINOR: schema details for v2.3 responses

- `next_task` offer on v2.3: add required `action` (string, may be empty; apply a code-point cap, 'short'-style, or leave it uncapped and say so). `latest_start` stays optional. `spent` is exactly `{windows, tokens, cache_read}`, all safe nonnegative integers (reported windows are integers, tokens are integers). `allowance.windows` and `allowance.tokens` are finite numbers >= 0 (not `Infinity` or `NaN`). The draft also allows fractional `spent.windows`, which nothing in the contract supports. Keep `spent.*` integer.
- v2.2 offers must keep rejecting `action` and `cache_read`. Add AC both ways.
- `record_usage` responses carry `spent` with `cache_read`. `SPENT` must be revision-specific. The current claim `spent` merge logic keys on `tokens` and must not break with the extra field.
- The tier allowance can be fractional (README: 0.5), so `decide` ratio math and any docs examples must handle it. Add a numeric test (windows 0.5, 0.25, tokens).
- Output of `next-task` exposes `action`, `cache_read` and fractional values to the harness. Check the harness prose does not describe `spent` as `{windows,tokens}` only.
- The usage importer's `usageTokens` helper counts `cache_read`. It is also used in `decide`. Make the v2.3 variant explicit rather than editing the helper in place.

### 14. MINOR: fixtures, docs and tests

- 13 files byte for byte, plus `PROVENANCE.md`. Add the sha256 of each copied file to PROVENANCE and test against it, because `/brain2` is not in CI or the repo. Say whether the brain2 copy is compared when mounted (skip if absent).
- `checks_52` line 408 pins the docs sentence "uncertain writes are never retried automatically". The docs must keep the v2.2 sentence and add the v2.3 exception beside it, rather than rewriting it.
- `checks_53`/`55` pin that `dispatching` survives pruning and that unlisted codes are `uncertain` on v2.2 (v2.2 fake). They stay green only if the v2.2 table is untouched (see 11).
- A v2.3 fake server is needed in the smoke harness: it must implement replay by `request_id`, `receipt_collision`, the seq cursor, and `next_task {task}` reasons. Say which `checks_NN` part holds it (each part is limited to 1,500 lines, so probably a new `checks_56_...`).
- `status` output: say whether it gains `lastContract`. If it does, update the tests that pin its exact keys. If not, say that it does not.
- MANUAL-TESTS: a v2.3 end-to-end note against a real Task&I is Martin-gated. State it explicitly as hands-on with the specific action; do not tick.
- `--task` must be added to `HTTP_USAGE`, the harness usage table, README or docs, and `--check-argv`.

### 15. MINOR: smaller points

- Record `record_usage` replay semantics in docs: a repeat returns the current roll-up, not the original, so `job.result.spent` may be newer than the first response. The claim `spent`/`spentAt` merge already handles equal-time cases.
- A `record_usage` job for an already-recorded `source_ref` with different figures is `refused` as `receipt_collision`. The message should say the row was recorded earlier with other figures (for example a changed price estimate) and that no fix is needed; otherwise it looks like an error.
- Rows journalled before v2.3 are not deduplicated against (README). That is the reason the draft's "v2.2 uncertain jobs never retried" is right for `record_usage` too, even though v2.3 would dedupe. Put the reason in the spec, or someone will "optimise" it away.
- `source_ref` is the job key. The importer keys include the session hash, so uniqueness is per workspace in practice. Two projects bound to one workspace with hand-chosen keys (`enqueue record_usage --key a`) can collide or silently dedupe. Document that the key must be unique across the workspace, or prefix it.
- Aggregated Claude rows cover many messages, possibly across 5-hour windows. `at` = newest covered timestamp, so the window count can understate. Acceptable, but say so.
- Pre-existing queued v2.2-era `record_usage` jobs carry no `at` and are sent without it. State that explicitly.

## Answers to the points the brief asked me to decide

- **`at` in the digest:** yes (see 4), with no clock fallback.
- **Is 5 attempts right:** yes. It counts sends that ended outcome-unknown (see 11). Resends are safe, so the cap only bounds a hung server, and `reconcile --action retry` re-arms it safely.
- **Ordering of jobs:** unchanged, array order, flush stops at the first unknown or `later` result.
- **Interaction with `refused`:** a resend can come back refused (any `rejected` code). That settles the job as `refused` and keeps its id. A `receipt_collision` on a resend means the earlier send was applied (see 2, 5, 11).
- **v2.2<->v2.3 switch between runs:** see 3 and 1.

## Verdict

REVISE. Do not start the build from this draft.

BLOCKING items:

1. Binding digest and `HTTP_CONTRACT_REVISION` must stay v2.2 (concern 1).
2. Retried bodies are not byte-identical (session, `at`): freeze the first-send wire body (2).
3. v2.3-to-v2.2 downgrade and crash-while-dispatching double-send risks (3).
4. `at` decision (in the digest, no clock fallback), the 30-day and future rules, never sent to v2.2, job-shape update (4).
5. `complete`/`release` resend: check ordering, pending record contents, field-mismatch refusal, collision keeps the pending record (5).
6. `list_asks` v2.3 schema: strict seq rules, otherwise answers can be skipped (6).
7. `next-task --task`: refusal must not clear the claim, echo check, schemas, scope rule, binding kinds, v2.2 behaviour (7).
8. Harness: per-reason action table (no working on over_budget and similar), call order, a stable v2.2 signal (8).
9. `decide` has no negotiation: use `claim.contract`; add ACs for newly live `latest_start` and `deferred` (9).
10. Limits and `id_pattern`: make them implementable (flush-time check, exact schema, `id_pattern` equality, per-revision capabilities schema) (10).

Items 11 to 15 are MINOR and should be folded into the ACs, which currently are one-line headings and not mechanically checkable as written.

## Iteration 2

Spec title says "rev 2". Items 1-10 each checked against the rev 2 text.

1. Digest literal v2.2, golden hex (AC2): resolved.
2. Frozen `sentBody`, `at` clamp/drop frozen at first dispatch (AC4, AC11): resolved.
3. Downgrade, crash, upgrade, revision memory (`sentRevision`, `sentBody`; AC5): resolved.
4. `at` in digest, never synthesised, KEY_CONFLICT on change (AC11): resolved.
5. complete/release reorder, `requestId`, same/different text, collision keeps record, v2.2 blocks: resolved, except the gaps in Concern M1.
6. Strict seq cursor schema and reset rules (AC8): resolved.
7. `next-task --task`: claim untouched on refusal, echo check with release, pairing rules (AC10): resolved.
8. Harness refusal table, no "work without a claim" (AC14): resolved.
9. `decide` reads `claim.contract` (AC12 incl. latest_start/deferred/fractional): resolved, see M2.
10. Limits applied at flush and before complete/release, exact key set, `id_pattern` equality: resolved. The "client limits <= fixture limits" test is not carried over (M3).

MINOR 11-15: 11 (405, per-revision table, attempt counter) addressed. 12 (UUID, no request_id on reads, not in digest) addressed. 13 (offer schema both ways) addressed. 14 (hashes, docs sentence) addressed; fake server location and `status`/`lastContract` not stated (see M3). 15 (docs on replay semantics, receipt_collision message wording for record_usage, key uniqueness) declined silently; acceptable.

### Concerns

BLOCKING: none.

MINOR
- M1. `pendingDirect` fingerprint is `{task, summary|reason}` only. The complete/release wire body also carries `session` (fixture complete.json). If the claim's session changes between the unknown attempt and the resend, the body differs and the server answers `receipt_collision` although the first send applied. Store the frozen `sentBody` (or add `session` to `fieldsDigest` and resend that session) on the pending record. `pendingDirectMore` records need the same fields; park data (`parkedAsks`, `budgetStopped`, `allowance`) should be reused from the pending record, not recomputed. Also say how `open_children` (complete 409 with `children`) maps on v2.3.
- M2. `decide` fallback when `claim.contract` is absent (pre-task claim): say `state.lastContract`, then v2.2. Say a renewal that changes revision does not merge the old `spent`.
- M3. Say which smoke part holds the v2.3 fake (checks_58 is named; confirm it stays within 1,500 lines), whether `status` gains `lastContract`, and add the test that client limit constants are <= the fixture's capabilities limits.

Verdict: PASS. No BLOCKING items; proceed to the Generator, folding M1 in if cheap.
