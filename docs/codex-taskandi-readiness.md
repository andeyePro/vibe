# Codex development of Task&I: acceptance and evidence

Source implementation for the 2026-09-12 scoped run. Martin clarified that this
builds Vibe capability; a Task&I checkout is not a prerequisite. Codex stays in
the bounded Vibe container and native Apple work uses the existing dedicated
`claude` Mac account. These sources have not replaced the active container or
activated a live Mac/Task&I connection.

| ID | Requirement | Implementation and evidence | Live status |
| --- | --- | --- | --- |
| C1 | Context survives startup/resume | `codex-context`, SessionStart guidance, runtime skill supplements; smoke 24 discovers root/spec/channel paths without reading referenced secrets | Rebuilt-container hook delivery pending |
| C2 | Honest capability reporting | Executable-helper inventory, guarded entrypoint, owned sidecar and vendor-module checks, protected CLI/shared trees, explicit Python dependency; smoke 18/22/24/25/32 | Existing installed delegate lacked execute permission; source installation fixed, active files untouched |
| Q1 | Async questions and FM2C | Shipped chair/channel/archival instructions; active run consumed C1/C2 archive-first and preserves unfinished `3. `; smoke 24 checks FM2C routing | File channel used in this run; fresh-session model compliance still requires observation |
| B1 | Restricted Mac build loop | Fixed target, explicit snapshot allowlist, private key/config checks, trusted host/wrappers, content fingerprints and bounded artifacts; smoke 26/31 | Project connection and host installation absent here |
| B2 | Observable failure/recovery | SSH timeout/cancel, retained request/evidence, cached identity-bound receipt, unknown-state refusal, bounded cleanup, collision/symlink/lock/tool availability fixtures; smoke 26/31 | macOS process behaviour, Xcode and simulator checks pending |
| S1 | Supported unattended launch/control | `--codex-run`/`--codex-resume` through liveness gate, supervisor status/stop/reconcile, unchanged default Claude invocation; smoke 19/21/22/25/27/30 | Separate rebuilt-container fixture pending; current interactive thread was not converted |
| S2 | No duplicate ownership or blind turn replay | Exclusive token ownership, Linux subreaper, isolated interpreter, fsynced pre-dispatch checkpoints, evidence-bound reconciliation, pinned task binding; smoke 19/21/27/30 | Actual vendor app-server recovery pending; operator evidence is not independently attested |
| A1 | Adversarial roles and usage | OpenAI role aliases and ledger; real subscription role calls on Luna/Terra/Sol/Astra; independent tester worktrees and immutable tool-less review panel; smoke 17/23/24 | Requested model/CLI usage recorded; served-model identity unavailable when CLI omits it |
| T1 | Task binding, asks/answers and usage | `--task`, local mapping, narrow MCP client, durable outbox/cursors/conflicts, explicit transcript usage import, installed-symlink CLI test; smoke 28/29/30 | Provisional fixture contract only; canonical server conformance pending |
| T2 | Scoped MCP opt-in | Untracked endpoint config, separate private token, origin/redirect/schema checks, binding pin, uncertainty refusal and file fallback; smoke 28/29/30 | Token scopes, task attribution and real response semantics require server verification |
| V1 | Whole Task&I development loop | Components independently exercised with local fake servers/transports and process fixtures | Real checkout/build/service scenario is unverified; fixtures do not close this row |

## Verification

The required combined checks passed: `python3 code-check.py` (24 shell files)
and `python3 smoke-test.py < /dev/null` (4,713 passing `check()` assertions,
plus the standalone Task&I fixture assertions included by the runner). The
canonical session audit records the exact run. Independent supervisor verification covered 62 tests across
modules 19/21/27/30. The final immutable source panel received separate Astra
and Sol reviews: Sol passed; Astra's installed-symlink finding was fixed and
independently re-reviewed to PASS. The executable-symlink regression proves
that enqueue persists a job and invalid commands return nonzero.

Other resolved findings include ambiguous-turn replay, premature ownership
release, Python import hijacking, checkpoint durability, effective binding
changes, permissive logs, file descriptor/ancestor checks, response identity,
receipt durability, bounded cleanup and trusted host command wrappers. Final
regression expectations explicitly require reconciliation; common test helpers
do not automatically erase ambiguous state. The foreign-owner log test branch
could not create a foreign-owned file as the test UID; hardlink and private-mode
checks ran. No live ownership or account-isolation assertion is inferred from it.

## Practical limits

- Context/Q&A and task-boundary calls are model-mediated instructions, not an
  unattended background poller. A saved answer still needs consumed-ledger
  reconciliation after a crash.
- Writable worktrees share an OS identity. Independent test ownership and
  immutable reviewer input do not prove that a writer could not read a sibling
  checkout. The run does not claim complete adversarial filesystem isolation.
- The Linux supervisor requires `/usr/bin/python3 -I` and procfs. It retains
  ambiguous ownership and unresolved effects rather than manufacturing recovery.
  Healthy tool silence is not a stall; configured ceilings remain enforced.
- The Mac bridge is an account boundary, not a build sandbox. Node's descriptor
  checks mitigate path swaps without claiming portable `openat` containment.
  Process-group cleanup cannot contain a malicious same-UID `setsid` escape.
  Protocol v1 supports printable ASCII filenames, including spaces, and arbitrary
  file contents. Release/signing secrets must stay outside the development path.
- Task&I schemas/cursors and usage event keys are provisional. An opaque bearer
  token cannot prove its scopes. No exactly-once mutation claim is made; unknown
  outcomes require server evidence before an explicit retry.
- Transcript import supports identified Codex cumulative token metadata only.
  Missing usage stays unknown; delegate totals and other vendor transcripts are
  separate. There is no inferred dollar cost or current weekly quota reading.

## Remaining activation and acceptance

1. Review/rebuild/relaunch the source image on a disposable project after ending
   active work deliberately. Run MANUAL-TESTS Test 56 and verify actual guards,
   startup context, supervision and recovery. Existing project domain opt-in is
   the route for Apple/Swift/OpenAI documentation, not unrestricted browsing.
2. Install the root-owned runner, trusted interpreter and command wrappers on
   the existing `claude` Mac account following `mac-build-protocol.md`. Configure
   the project key and verified host key locally, then record doctor/build/test
   and available simulator evidence. No live connection was configured here.
3. Verify Task&I's exact schemas, cursor ordering, answer authorship/task
   attribution, token scopes, source_ref/idempotency semantics and token/cache
   accounting against the authoritative service. Use an isolated test task
   before activation. The fixture's session-derived usage event keys must not be
   mistaken for a verified server upsert/aggregation contract.
4. With those prerequisites available, run the integrated native Task&I scenario
   and record its actual revision-linked outcome in V1.

Setup, recovery and rollback: `codex-development.md`, `mac-build-protocol.md`,
`taskandi-client.md`, and MANUAL-TESTS Test 56. Canonical run audit:
`.vss/sessions/2026-09-12T05-22-55Z.md`.
