# Generator report: task_066 cycle 1 (Task&I client v2.3 family alongside v2.2)

Spec: `.vs/spec.md` rev 2 + Rev 2.1 + Rev 3 addendum (the coordinator's re-scope: accept v2.2/v2.3/v2.4/v2.5; v2.4/v2.5 = v2.3; limits may carry extra keys; fixtures copied as v2.5).

## Files changed

- `devcontainer/taskandi-client.mjs`: all client rules.
- `devcontainer/taskandi-usage.mjs`: `at` on importer rows.
- `devcontainer/taskandi-harness.md`: step 2 linked-task claim plus the reason table.
- `docs/taskandi-client.md`: new section "Contract v2.3 (and v2.4, v2.5) alongside v2.2".
- `CHANGELOG.md`: entry at the top of `## 2026-10-31`.
- `MANUAL-TESTS.md`: a v2.3 item in each of Tests 69 and 70.
- `smoke/fixtures/taskandi-v23/`: the thirteen files byte for byte (all say v2.5), plus `PROVENANCE.md` with sha256s.
- `.vs/tasks.json`: task_066 `implementation_status` → `complete`.

Not touched: `smoke/checks_58_*`, `smoke/taskandi_v23_server.mjs`, `smoke/runner.py`, launcher, firewall, hooks, settings, Dockerfile, brain2, and vs/vss/vsss.

## Per-AC notes

- **AC1 Negotiation.**
  - New constants: `HTTP_CONTRACT_REVISIONS` (v2.2..v2.5), `isV23()` (exported) and `SERVER_LIMIT_KEYS`.
  - `capabilities` schema is chosen by the answer's contract:
    - v2.3 family: the v2.2 keys plus `limits` (object) and `id_pattern`;
    - otherwise: exactly the v2.2 keys, so a v2.2 answer with `limits` is malformed.
  - `open()` then fails PREDISPATCH (exit 1, only capabilities sent) in these cases:
    - an unknown contract (v2.6);
    - a missing limit key, `unit` ≠ `code_points`, `id_unit` ≠ `utf16_code_units`, or a non-positive count;
    - `id_pattern` ≠ `USABLE_ID.source`.
  - Extra limit keys are allowed (Rev 3).
  - `state.lastContract` (see Ambiguity 1).
  - `status` gains `lastContract`.
- **AC2 Binding digest.**
  - `bindingDigest` is untouched, and `HTTP_CONTRACT_REVISION` is still `'vibe-agent-exchange-v2.2'` and exported.
  - Golden value: `{kind:'descriptor-http', workspace:'ws-fixture', task:'leaf-b', contractRevision:'vibe-agent-exchange-v2.2', originHost:'https://task.example'}` → `545b5ec3686cbc8de1db26e78a8c7287d8cf4a80a3b30cff867afc25beabea44`. That is the same from `git show HEAD:` and from the working tree.
- **AC3 Wire.**
  - Writes (`ask`, `comment`, `record_usage`, `record_time`, `complete`, `release`) carry `request_id` on v2.3.
  - Reads use `send()`, which never adds it.
  - Key sets match fixture request + `connection` (scratch test). `record_usage` and `record_time` carry no `agent`, as in the fixtures.
- **AC4 Frozen body.**
  - `requestId` (`randomUUID()`, outside payload and digest) is set at enqueue. Jobs from before this change get one at their first v2.3 dispatch.
  - The first v2.3 dispatch builds `sentBody` with `freezeBody()` and stores it, together with `sentRevision`, in the write that marks the job `dispatching`.
  - Every resend sends `sentBody` byte for byte (`send.raw`).
  - `sentBodyIntact()` re-checks a stored body against the payload, so an edited one is refused as `tampered_job`.
  - Outcome-unknown on v2.3: the job goes back to `queued` with `attempts += 1`, becomes `uncertain` at 5, and the flush stops.
  - `receipt_collision` on a first send: `refused`, flush continues. On a resend: `uncertain` with `noRetry`, flush stops, and `reconcile --action retry` refuses it.
- **AC5 Crash, downgrade, upgrade.**
  - `recoverDispatching`: a v2.3 `sentRevision` with a `sentBody` goes back to `queued` (attempt +1); anything else becomes `uncertain`.
  - Downgrade: a job with `sentBody` flushed on v2.2 becomes `uncertain` with the exact spec message and no request, and the flush continues.
  - Upgrade: after `reconcile retry`, the next v2.3 flush is a first send (freezes the body, uses `requestId`). `reconcile retry` also clears `attempts`.
- **AC6 complete/release.**
  - Pending-record handling, in order:
    - a v2.2 `pendingDirect` blocks **before** capabilities, with zero requests, as today. checks_55 AC27 needs zero requests.
    - a v2.3 record with different text: exit 1, zero requests.
    - same text: capabilities runs. If the server now speaks v2.2, the command exits 1 and the record is kept. Otherwise `sentBody` is resent.
  - A v2.3 pending record stores `requestId`, `sentRevision`, `fieldsDigest` and `sentBody`, plus the park fields. A resend reuses the record's park data.
  - A collision on a resend keeps the record (exit 1).
  - `open_children` clears the record.
  - Server limits are checked before the pending write; over a limit: exit 1, nothing sent.
- **AC7 Error table.**
  - `HTTP_ERRORS_V23` and `ERROR_STATUS_V23` (adds 405 `method_not_allowed`) are selected by the negotiated contract.
  - `connection_revoked` is try-later on v2.3, and the flush prints the revoked preface: notices now include `preface` on the later and unknown branches.
  - An unknown 409 code on v2.3 is try-later, because every 409 applies nothing.
  - v2.2 tables are unchanged.
- **AC8 seq cursor.**
  - `RESPONSE_SCHEMA_V23.list_asks`: exact keys `{task, seq, asks}`, and each ask has the v2.2 ask schema plus `seq`.
  - The rule enforces: each ask's seq > `since`, strictly increasing, and page `seq` = last ask's seq (or `since` when empty).
  - The poll reads both cursor shapes before `open()` and picks `since` after negotiation. The concurrency check compares the whole stored cursor.
  - Cursor shapes: `{seq}` on v2.3, `{now}` on v2.2. Each ignores the other.
- **AC9 Offer schema (v2.3).**
  - New fields: `action` (required string) and `spent.cache_read` (required).
  - `allowance.windows/tokens` are `num`: finite and ≥ 0, so fractions are allowed.
  - The v2.2 schema is unchanged.
- **AC10 `next-task --task`.**
  - REF must be the effective or the claimed task (strict; see Ambiguity 3).
  - On v2.2: `{"bound":true,"channel":"taskandi-http","task":null,"reason":"contract_v2_2"}` after capabilities only.
  - On v2.3:
    - sends `task`;
    - a refusal prints the exact JSON, exits 0, and touches neither the claim nor the body file;
    - a wrong task triggers `handBack` (release with reason `vibe asked for another task` and a fresh request_id), then exit 1;
    - reason/`--task` pairing is enforced in the schema `rule`.
  - Unbound: the file-fallback line. MCP: USAGE.
  - `--check-argv` accepts `--task`, and `HTTP_USAGE` names it.
  - The claim stores `contract`. A renewal across families replaces `spent` (M2).
- **AC11 `at`.**
  - `recordTime()` reads a record's `timestamp` (ISO string or integer ms) and never the clock.
  - Claude: the newest time over each message's records, then over the messages of the row. Codex: the event's own `timestamp`.
  - `at` travels beside the payload and is put into the payload only on the descriptor (HTTP) path. MCP/v2.1 payloads never get it, since their exact-key validation would refuse it.
  - `HTTP_PAYLOAD_KEYS` and `JOB_SHAPES` accept an optional `at`.
  - `jobFields` strips `at` for v2.2.
  - `freezeBody` drops an `at` older than 30 days (with the exact notice) and clamps one more than 60 s ahead.
- **AC12 decide.** `usageTokens(payload, v23)`. The revision is `claimContract()`: `claim.contract`, else `lastContract`, else v2.2. Fractional allowances, `deferred` and a past `latest_start` already work under the existing rules (scratch-tested for `windows: 0.5`).
- **AC13 Server limits.** `overServerLimit()` checks, against a final body:
  - request_bytes;
  - id (UTF-16) for `task`/`in_reply_to`;
  - question, default, options, option, ask_post;
  - comment, summary, reason.

  A job over a limit is refused `over_server_limit` (lastError names the limit) with no request. HTTP_LIMITS are all ≤ the fixture's limits (M3).
- **AC14 Harness.** Step 2 is split into (b) A-mode and (c) Linked task:
  - (c) runs `next-task … --task <effective task>`, then acts on the reason table: all ten reasons plus `contract_v2_2`. No row says to work without a claim.
  - The `contract_v2_2` row keeps the old no-claim linked mode, including the "session opened on another task" sentence that checks_54 pins.
  - `--check-argv` accepts the new line, and checks_54 passes (146/146).
- **AC15 v2.2 unchanged.** checks_28/29/47/50/52/53/54/55/57 all pass unchanged.
- **AC16 Docs and gates.** Docs section, CHANGELOG and MANUAL-TESTS are done. Fixture hashes are in `PROVENANCE.md`; checks_58 (Tester) verifies them.

## Ambiguities and decisions

1. **`state.lastContract` vs checks_50 `hx.core()`.**
   - The conflict: checks_50 AC4 compares the whole state minus `jobs/reconciliationLog/lastGrade/pendingDirect` before and after a v2.2 flush. Writing `lastContract` on every v2.2 call would break it (AC15).
   - The decision: `lastContract` is written on every v2.3-family answer, and on every answer once it exists. Absent means v2.2, since every older state negotiated v2.2. `status.lastContract` reports v2.2 when `lastGrade` exists and `lastContract` doesn't. A v2.3→v2.2 switch updates it.
   - The Tester should assert `lastContract` after v2.3 calls and after a v2.3→v2.2 switch, not after a v2.2-only history.
2. **sentBody is kept after any v2.3 dispatch**, even a try-later or refused one. This follows "every later v2.3 attempt sends sentBody byte for byte" literally. One consequence: a job that only ever got a definite not-applied answer on v2.3 still becomes `uncertain` on a downgrade. This is conservative. A refused job's `reconcile retry` resends the same frozen body.
3. **`next-task --task` REF.** REF must equal `config.task` (the effective task) or the claimed task exactly. On a whole-workspace descriptor (`root: null`, no `VIBE_TASK_REF`) only the claimed task qualifies; target resolution would otherwise accept any explicit id.
4. **The frozen body includes `connection`** (per the spec). If the descriptor is reconnected between attempts, the resend still carries the old connection. Not handled further.
5. **Crash recovery counts as an attempt** (`attempts += 1`); at 5 the job becomes `uncertain`.
6. **An unknown 409 code on v2.3** is try-later (the README says every 409 applies nothing). An unrecognised **status** is still outcome-unknown.
7. **Wrong-task and unusable-task hand-back releases on v2.3** carry a fresh `request_id` and are not recorded as pending.

## Commands and exit codes

- `python3 code-check.py` → 0.
- Existing taskandi checks run individually, each `< /dev/null` → all 0:
  - `smoke/checks_28_taskandi_client.py`, `checks_29_taskandi_binding_usage.py`, `checks_47_taskandi_contract_v2.py`;
  - `checks_50_taskandi_http.py`, `checks_52_taskandi_http_more.py`, `checks_53_taskandi_decide.py`;
  - `checks_54_harness_prose.py` (146/146), `checks_55_taskandi_http_review.py`, `checks_57_taskandi_decide_review.py`.
- `node .vs/cycle-1/scratch-tests/v23.test.mjs` → 0 (16/16). It has its own minimal in-process v2.3 fake server with request_id replay and covers AC1–AC13.
- `node devcontainer/taskandi-client.mjs --check-argv next-task --agent claude --session s --task leaf-b` → `{"ok":true}`.
- `python3 smoke-test.py < /dev/null` → 0 ("✓ smoke tests passed"; run under `timeout 590`, finished in time).
