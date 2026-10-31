# task_064 cycle 2: Generator report (Rev 6 addendum, AC19–AC30)

## Files changed (this cycle)
- `devcontainer/taskandi-client.mjs`: all AC20–AC30 client work (details below).
- `devcontainer/taskandi-usage.mjs`: AC24. Under a descriptor binding, one `enqueueBatch` call (one config load, one outbox lock). With zero records, `--task` is still checked through `resolveTask`.
- `vibe`: AC19. New `VIBE_LAUNCH_TASK_REF_RE='^(taskandeye://node/)?[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'` and `_valid_launch_task` (C locale) for `parse_vibe_args --task`. `VIBE_TASK_REF_RE` and `_link_valid_task` are unchanged for `vibe link`. The error text still begins `--task needs`.
- `devcontainer/codex-supervisor.mjs`: AC19. The launch-binding literal is now `/^(?:taskandeye:\/\/node\/)?[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/`, still in the `if (this.taskRef && !/…/.test(this.taskRef)) throw usageError('invalid launch task binding')` form that checks_49 extracts.
- `docs/taskandi-client.md`: v2.2 section extended (TLS, connect-failure text, launcher ids, unusable-id release, status error, C1/bidi escaping, 2000-code-point caps, 409 detail keys, `tampered_job`, `pendingDirect` / `reconcile --direct`, origin host in the binding, one-pass usage, seam limits).
- `CHANGELOG.md`: the task_064 entry is extended with a "Review follow-up (cycle 2)" paragraph.

## Per-AC notes
- **AC19**: done as specified. The MCP `TASK_REF` in the client is unchanged. The descriptor client still refuses `ABBR-N`.
- **AC20**: `interpretHttp` interprets the body when it is a plain object with a string `error`, and ignores other keys. 400, 403 and 421 must still carry their one code, otherwise the response is `unrecognised_response`. A `complete` 409 `open_children` validates only `children`; bad children are unknown.
- **AC21**: `rejectUnauthorized: true` is set. For https, `sent` is set on `secureConnect`, so a handshake failure is `not_sent` `connect_failed` and the job stays queued. Positive control: with a trusted CA the request succeeds, and a timeout after the handshake is OUTCOME_UNKNOWN.
- **AC22**: an unusable `next_task` id sends `release {task, reason: "Task id not usable by vibe; rename it in Task&I.", session}`, with the session from argv. If `calls` lacks `release` or the release fails, this preface line is printed: `could not release the lease on the unusable task (<code>); it lapses on its own`. The message then follows, with exit 1 and no claim stored.
- **AC23**: under a descriptor binding, `status` calls `descriptorConfig()` without catching its error, so it exits 1 with one stderr line and empty stdout.
- **AC24**: `enqueueAll(kind, items, options)` validates every item first, then processes all of them under one `withState`. Writes are all-or-nothing, so a key conflict writes nothing. The old `enqueue` is `enqueueAll` with one item.
- **AC25**: the digest is `{kind, workspace, task, contractRevision, originHost: "<scheme>//<hostname>"}` (for example `http://127.0.0.1`). `originHost` is non-enumerable on the config.
- **AC26**: under a descriptor binding, stdout goes through `terminalSafeJson` (exported), which escapes U+0080–009F, U+202A–202E and U+2066–2069 as `\uXXXX`. A new schema scalar `short` caps `title`, `owner`, `grade`, `answered_by` and `open_children[].title` at 2000 code points.
- **AC27**: `pendingDirect: {call, task, at}` is written under the lock after capabilities pass and before the send. `at` is in **ms** (Date.now(); the Tester's checks_55 expects this). It is cleared on success, `open_children`, try-later, rejected and not-sent. Only the **same call and task** is blocked, with the exact message. A record for a different call or task, made while one is held, goes into `pendingDirectMore` (an array) rather than overwriting. `reconcile --direct <call> --task <id> --action done|retry --evidence TEXT` clears the matching record. `done` also drops the claim if it is on that task. A reconciliation-log entry `{direct, task, action, evidence, at}` is written.
- **AC28**: the body is `{...fields, action, connection}`. `jobIntact` checks the kind is one of the four, the exact required and optional payload keys (`JOB_SHAPES`), and `digest({kind, payload}) === job.digest`. A failing job becomes `refused`/`tampered_job`. This runs in the flush pre-pass, so there are zero requests if nothing is sendable, and again at dispatch.
- **AC29**: the seam host must be `127.0.0.1` or `::1`, checked in `createClient`, and in `httpTransport` as a backstop. `::1` uses `family: 6`. The seam is refused for https in `open()` before capabilities, and in the transport too.
- **AC30**:
  - The new `fileRules` is shared by `assertRegular` and `readBounded`. Messages keep "regular non-symlink file", and add "(it is a symlink)", "with a single link (no hard links)", and the chmod 600 hint via `modeHint`.
  - The new `checkVibeDir` and `mappedTask` are shared by `loadConfig` and `loadDescriptor`.
  - There is one `bindingDigest`; `currentBinding` was removed. There is one `claimOf` accessor (the MCP `claimedTask` wraps it) and one `bindAnswers(state, config, bind)`; `checkAnswerBinding` was removed.
  - `tooLarge` and the `descriptorPresent` export were removed. A body-size guard in `send()` marks `notSent`, so `dispatched` is not counted.
  - There is one hard timer; `req.setTimeout` was removed.
  - Connect failures read `Task&I request not sent: connect_failed; could not reach the Task&I service (via host.docker.internal)` or `(on this machine)`, with no port.
- **Extra (for the AC24 test)**: the outbox lock `release()` used to reopen `.lock` to compare the token. checks_55 counts `.lock` opens and saw 2. It now compares the inode and device through the held descriptor and does not reopen the file. This is equivalent or stronger protection against unlinking a replacement owner's lock, and checks_28 passes.

## Commands and exit codes (final run)
- `python3 code-check.py`: 0
- `python3 smoke/checks_28_taskandi_client.py`: 0
- `python3 smoke/checks_29_taskandi_binding_usage.py`: **1** (AC19 conflict, see below)
- `python3 smoke/checks_47_taskandi_contract_v2.py`: **1** (only because it runs checks_29: "AC10 … checks_29 exits 0")
- checks_48: 0. checks_49: **1** (AC19 conflict). Both were run through `.vs/cycle-2/scratch-tests/run_checks_module.py` because these modules have no `__main__`.
- `python3 smoke-test.py < /dev/null`: **1**, with 28 failed checks, all of which follow from the addendum:
  1. **AC19 vs checks_29, also seen through checks_47**: `'AB'` and `taskandeye://node/not-a-uuid` are now accepted by `vibe --task`. Both are usable ids, so AC19 requires accepting them. checks_29 is not on the addendum's list of changeable checks, so the Evaluator must authorize the update.
  2. **AC19 vs checks_49 AC21/AC22**: these malformed-UUID inputs are usable ids and are now accepted by `vibe --task` and the supervisor regex: one char short, one extra, leading `g`, no hyphens. A braced UUID is still refused, and the `vibe link` cases all pass. This also needs Evaluator authorization.
  3. **checks_50 AC4 "direct complete [unknown] …"** (14 checks): the test reuses one project for successive direct completes. After the first unknown outcome, AC27 now blocks the next one until `reconcile --direct`. This is expected, and the test needs adjusting (a fresh project per case, or a reconcile between cases).
  4. **checks_50 AC16 body_too_large at flush**: the test pads `payload.text` in state.json without updating `digest`, so AC28 now refuses it as `tampered_job`. This is expected. To reach `body_too_large`, the test must recompute `digest = sha256(canonical({kind, payload}))`, as my scratch test-errors.mjs does.
- checks_55 (the Tester's r6 file): all AC19–AC30 checks pass after the AC27 (`at` in ms, per-call blocking) and lock-release changes.

## Scratch tests (`.vs/cycle-2/scratch-tests/`, real loopback servers)
- `test-addendum.mjs`: 120 passed, 0 failed (AC19–AC30, including an https self-signed server with zero handler hits and `connect_failed`, and a `::1` seam).
- `test-tls-ok.mjs`: 2 passed (AC21 positive control).
- The cycle-1 suites, copied and adjusted only where the addendum changed behaviour: `test-wire.mjs` 70/0, `test-errors.mjs` 184/0, `test-state.mjs` 127/0.

No commit, no push.
