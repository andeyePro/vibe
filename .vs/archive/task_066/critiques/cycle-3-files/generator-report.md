# Generator report: task_066 cycle 3 (Rev 5 addendum, AC29-AC30)

Files changed: `devcontainer/taskandi-client.mjs`, `docs/taskandi-client.md`, `CHANGELOG.md` (one clause appended to the task_066 Cycle 2 bullet). No `smoke/` file touched. `diff.patch` is `git diff -- devcontainer docs CHANGELOG.md` against HEAD, so it holds cycles 1-3 together (all uncommitted).

## Per-AC notes

- **AC29.**
  - `interpretHttp` now tags every interpreted non-200 error with `error.status`.
  - There is one constant, `RESEND_PROOF_CODES` (the ten codes in the spec), and a `resendProof(error)` check: `status === 409` and the code is in the list.
  - **Jobs.** On a v2.3 resend that left the client and is not `receipt_collision`, any non-proof answer is classed `unknown`. The job keeps `sentBody` and goes back to `queued` with `attempts + 1`, becoming `uncertain` on the 5th attempt. The flush stops. `lastError` reads `outcome unknown; the next flush resends the same body and request_id: Task&I outcome unknown on a resend: <code> (HTTP <status>)`. The revoked preface is pushed to notices.
  - **Pending `complete`/`release`.** The same predicate runs before the `open_children` and `receipt_collision` branches. It throws `sentWriteFailure(error, true, force=true)`: exit 1 with the outcome-unknown message, the preface kept, no settle, and the record and claim kept.
  - Proof codes on a resend behave as before (try-later or rejected, unfrozen or settled). First sends are unchanged.
  - The revoked → fresh descriptor sequence needed no new code: the existing AC18 `replayLost` check marks the job `uncertain` with no request.
- **AC30.** `reconcile --action retry` on a `replayLost` job returns, via `withNotices`, the notice `<key>: this sends a new write on the current connection; Task&I cannot tell it from the earlier one, so check it was not applied`. The CLI prints it on stderr as `taskandi-client: <key>: ...`.
- **Docs.** The "Why a resend is safe" paragraph now lists the proof codes and describes the revoked → fresh-descriptor path and the AC30 message. The resend-rules lead sentence and table rows now separate first sends from resends (400/403/405/421, `connection_revoked` and `connection_unavailable` count as proof on a first send only). The pendingDirect bullet covers non-proof answers.

## Decisions

1. **`receipt_collision` on a resend** keeps its own stricter cycle-2 handling: a job becomes `uncertain` + `noRetry`, and pendingDirect keeps the record with its own message. It is never treated as proof either way.
2. **`open_children` on a `complete` resend** is a 409 code outside the list, so under AC29 it is outcome unknown: the record is kept and the command exits 1. It no longer settles. On a first send nothing changes.
3. **A not-sent resend** is unchanged (AC20): the body is kept, `attempts` is not incremented, and it is classed try-later. It is not an answer from the server.

## Commands

- `python3 code-check.py` → 0.
- `node .vs/cycle-3/scratch-tests/ac29.test.mjs` → 7/7. It covers: every non-proof answer on a job resend (409 connection_revoked/connection_unavailable/unknown code/open_children, 400, 403, 405, 421, 500, 503), each queued with its body and `uncertain` at attempt 5; every proof code on a job resend; first sends unchanged; non-proof and proof answers on a `complete` resend plus a `release` case; the full lost response → revoked → `conn-2` sequence, ending `uncertain`/`replayLost` with exactly one applied comment on the fake server and no conn-2 comment request; and the AC30 notice from the API and the CLI.
- `node .vs/cycle-2/scratch-tests/v23.test.mjs` → 25/25.
- `python3 smoke-test.py < /dev/null`: see the "Smoke" section below.

## Smoke

- `python3 smoke-test.py < /dev/null` (started in the foreground, moved to the background by the harness after 180 s) → exit 0, "✓ smoke tests passed", 8m30s, no ✗ lines. Log: `.vs/cycle-3/smoke.log`. The run already included a `[taskandi-v23-r4]` group with AC29/AC30 checks, and it passed. No test failed for asserting the old resend classification.
