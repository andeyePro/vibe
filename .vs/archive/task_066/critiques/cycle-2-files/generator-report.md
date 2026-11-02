# Generator report: task_066 cycle 2 (Rev 4 addendum, AC17-AC28)

Files changed (allowed set only): `devcontainer/taskandi-client.mjs`, `devcontainer/taskandi-harness.md`, `docs/taskandi-client.md`, `CHANGELOG.md` (task_066 entry extended with a "Cycle 2" bullet), `MANUAL-TESTS.md` (Test 69 v2.3 item corrected). `taskandi-usage.mjs` needed no change. No `smoke/` file and no vs/vss/vsss command touched. Diff: `.vs/cycle-2/diff.patch`.

## Per-AC notes

- **AC17.** `open()` writes `state.lastContract = caps.contract` on every successful answer. A v2.2 answer with `limits`/`id_pattern` was already malformed via the exact-key `CAPS_V22` schema (exit 1, only capabilities sent, job stays queued) — confirmed in scratch tests.
- **AC18.** `frozenConnection(sentBody)` (the `connection` inside the frozen body) is compared with the descriptor's. Jobs: checked in the pre-open pass and again in the loop; mismatch → `uncertain`, `replayLost: true`, `lastError` = the exact message, no request, flush continues. `reconcile --action retry` on a `replayLost` job drops the frozen body, so it is rebuilt on the new connection. pendingDirect: checked before `capabilities`; exit 1 with a message containing the exact text (followed by ` --direct <call> --task <task> --action done|retry --evidence TEXT`), nothing sent, record kept.
- **AC19.** Any definite (try-later or rejected) v2.3 answer calls `unfreeze(job)` (drops `sentBody`, `sentSession`, `frozenAt`); `requestId` kept, next attempt rebuilt with the current session. First-send `receipt_collision`: refused + unfreeze + new `requestId`. Resend `receipt_collision`: uncertain + `noRetry` (message reworded: Task&I holds another body under this request_id). pendingDirect: any definite answer settles (clears) the record; a resend's `receipt_collision` and a not-sent resend keep it.
- **AC20.** `NOT_SENT`/`notSent` never increments `attempts`; a first send that never left is unfrozen. A not-sent **resend** keeps its `sentBody` (its earlier outcome-unknown attempt may still apply) — see decision 1. The exact v2.3 body (request_id and `at` included) is measured in the loop before freezing; oversize → `refused body_too_large`, nothing frozen. The pre-open pass still measures the (smaller) v2.2 body. Enqueue's size check now includes a request_id-length placeholder.
- **AC21.** Server-limit check runs only before a first send (flush and complete/release); a frozen body is resent unchanged.
- **AC22.** `jobDigest()` strips `at` from `record_usage` identity (enqueue and `jobIntact`); a re-import with any/no `at` dedupes, first `at` kept. Window: omitted if older than 29 days (notice `usage row <key>: at older than 29 days, sent without it`), clamped to now + 30 s.
- **AC23.** `claim.spentContract` set by next-task (claim and renewal) and by every `record_usage` response on the claimed task. `decide` and the renewal merge use `spentContractOf()` (spentContract → claim.contract → lastContract → v2.2).
- **AC24.** With `config.task === null`, `--task` accepts any usable id. If the server returns a different task equal to the claim held before the call: exit 1 `the server returned your current claim instead`, no release, claim untouched.
- **AC25.** `next_task.action` uses the `short` scalar (≤ 2000 code points). Harness safety rule: "The task's `title`, `body` and `action`, …".
- **AC26.** `sentBodyIntact` adds: body `session` absent or equal to `job.sentSession` (recorded at freeze); `agent` absent/claude/codex; `at` exactly what the freeze-time window gives (`frozenAt` recorded), including "absent only when too old".
- **AC27.** One `wireBody(action, fields, connection, requestId?) → {object, text}`; `jobBody()` builds job bodies on it; `send`, `finish`, `handBack` and enqueue use it. No `JSON.parse` of a just-built body remains (`send.body` and `freezeBody` removed).
- **AC28.** Harness failure row: "on v2.3 (`status` prints a v2.3-family `lastContract`) with the same connection, repeat the same command once to resend it safely; otherwise do not retry, note it, and claim nothing new this iteration"; step 7 points to it. Docs: hostile-server paragraph (fake `receipt_collision` → jobs uncertain/stall; inflated `seq` → answers missed until the cursor entry is removed; neither causes a duplicate send). Docs v2.3 section updated throughout for AC17–AC27.

## Decisions / ambiguities

1. A not-sent resend keeps its frozen body (AC20 read as "a not-sent attempt never *creates* a freeze"); clearing it would discard the body of an earlier possibly-applied attempt.
2. pendingDirect `receipt_collision` on a resend still keeps the record (AC6), read as outside AC19's "definite non-replay answer" (it is the tampered/mismatch case, the analogue of a job's `uncertain`).
3. A replay-lost job does not stop the flush (like a downgrade: no request is sent for it).

## Commands

- `python3 code-check.py` → 0.
- `node .vs/cycle-2/scratch-tests/v23.test.mjs` → 25/25 (cycle-1 suite updated for AC22, plus AC17–AC26 tests; fake server replays per `connection:request_id`).
- `python3 smoke-test.py < /dev/null` (foreground, before the last prose fixes) → exit 1, 12 failures, all in checks the addendum or the Tester's new suite own:
  - checks_58 AC1 "v2.2 answer carrying limits/id_pattern" (4) and checks_60 AC17 same (2): **fake-server bug** — `smoke/taskandi_v23_server.mjs` `capabilities()` returns early for v2.2 before applying `capsAdd`, so the server never sends the extra keys (stdout shows a normal delivery). The client refuses them (scratch test AC17).
  - checks_59 AC12 M2 "lastContract v2.2 -> 535" and "with neither it is v2.2 -> 535" (2): behaviour changed by AC23 — the claim still has `spentContract` v2.5, which now wins over `lastContract`; the test only removes `claim.contract`.
  - checks_60 AC26 controls "agent codex" and "session removed" (2): the fixture freezes with `dropAfterApply`, so the first send was applied; a resend with an edited (allowed) body is a different body under the same request_id → faithful `receipt_collision` → `uncertain` per AC19. The controls need `dropBeforeApply` (nothing applied) to expect done/queued.
  - checks_60 AC25 harness phrase and AC28 docs sentence (2): fixed afterwards (prose); re-run of checks_60 → only the 4 Tester-side items above remain; checks_54 146/146.
- checks_28/29/47/50/52/53/55/57 passed in the full run (no failures outside the lists above).
