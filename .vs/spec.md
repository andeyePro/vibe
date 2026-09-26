# task_060 — Codex unattended continuation contract — 2026-09-26

Scope: apply the five reviewed Codex weaknesses; retain Claude command, launcher recovery and shared Stop guard behavior byte-for-byte. User has authorised Codex-specific hook/runner integration and local commits; no push, no credentials/API fallback.

AC1: Codex vsss skill defaults to a single durable supervised handoff before implementation. A helper reads current thread ownership to avoid recursive handoff; conflicting owners refuse. Detached runner survives the initiating tool, exposes status/stop/log and uses existing liveness entry gate. Direct --codex-run uses the same outer runner. Interactive chair checkpoints first and yields workspace ownership; no automatic TUI killing. Default path is model-mediated via skill, explicit helper launch is deterministic.
AC2: New vsss supervisor runs require completion JSON bound to runId/threadId/promptHash, canonical session audit path/content hash, allowed numeric condition and explicit evidence. Condition 2 requires passed verification, optimiser rationale and no actionable remaining tasks; condition 4 requires three logged consecutive no-commit no-op iterations plus references to any blocking questions (empty when none). Condition 3 requires parsed original explicit time cap actually expired. Missing/malformed/stale evidence and arbitrary VSSS-EXIT prose cause continuation with feedback, never success. Existing terminal legacy runs remain terminal; unfinished legacy vsss runs upgrade to evidence requirement. Evidence checks establish consistency, not semantic proof of perfection.
AC3: Codex gets separate Stop routing. A live matching supervisor owns continuation and receives completed turns without local refusal limits. Interactive vsss stops without valid evidence remain blocked beyond fourth attempt; unrelated conversations and explicit deactivation remain unaffected. Claude shared guard and hook template remain identical.
AC4: Consecutive transient retry counter drives backoff/limit, resets on successful turn; existing transientRetries stays lifetime telemetry. Persist/migrate both safely, retain wall/turn/quota safeguards.
AC5: Outer Linux subreaper owns supervisor and all descendants, serialises launches and retries only after tree-empty proof. No stale foreign lock stealing. Crash after known turn completion can recover by read-only thread/read proving that exact last turn completed; unknown/start-in-flight, partial/failed/in-progress turns and ambiguous identity stay checkpointed for explicit effects review. No replay of original input or tool mutations. Stop and configured ceilings never restart. Bounded consecutive process failures; successful progress resets failure streak.
AC6: Codex-specific instructions override contradictory shared clock/loop statements: explicit original caps survive interruption; defaults are not stop conditions; supervised turns may end; no implicit handoff loops. Claude texts are unchanged except a pointer within Codex-specific section if needed.
AC7: Add negative/positive behavioural tests for evidence/retries/recovery/handoff and preserve Claude tests. Full smoke and code-check pass; separate subscription-model diff review; no fixture-only claim of live Docker/long-duration proof.

Model plan: sol planner and spec critic (subscription confirmed); chair implementation; independent sol reviewer/test design; no credit-billed escalation. Implementation split in scoped local commits. Out of scope: changing Claude persistence, disabling policy, blind replay, host reboot/container survival, guarantee semantic completeness from self-report.

## Resolved design details after independent critique
- Preserve devcontainer/commands/vsss.md, vss.md, vs.md, vsss-stop-guard.sh and the entire host vibe launcher byte-identically to the start of this task. Put all overrides in devcontainer/codex/vsss.md. Source fingerprints below are integrity fixtures, not fixed Git revisions.
- One .vss/codex-supervisor.json.runner.lock per checkout (existing exclusive-create UUID-token protocol). A handoff lock serialises prompt storage/start. Only the wrapper's own same-token child lock may be removed, only after its directly owned Linux subreaper acknowledges empty. No PID inference; double-fork/setsid descendants are adopted. Death of outer wrapper requires manual reconciliation.
- Entry: codex-autonomy context/start/status/stop --cwd ROOT; start --prompt-file FILE. It stores exact prompt bytes privately and detaches codex-entry --supervise, which runs codex-autonomy watch -- run ... after liveness. Matching active supervisor thread avoids recursive handoff. Other owners refuse; user remains able to stop; skill chair yields workspace without killing TUI.
- Completion version 1 fields/types and all five conditions are specified in devcontainer/codex/vsss.md. Extra keys are permitted for future audit metadata but never authority. JSON is atomically renamed; canonical safe session path, no symlinks, regular files with link count 1, content SHA256. runId is minted by supervisor, promptHash comes from original bytes, cap from leading original options. Unsupported completion consumes ordinary turn/wall budgets and receives correction, not success. Completed legacy state is terminal; unfinished state upgrades once.
- Stop checked before turn and at poll boundaries; explicit stop/ceiling never restarts. Concurrent stop after final successful persistence may observe already completed state; it cannot initiate a new run. Completion is accepted only from a completed turn. Valid original time caps constrain all request/wait deadlines including recovery; defaults remain independent runaway bounds.
- Existing transient error taxonomy retained; increment total/streak together before waiting, reset streak on completed turn. Conservative legacy streak=total; original counts retained. Process retries bounded at three consecutive exits without completed-turn progress; no retry on stop, usage or ceiling codes. Reconciliation only accepts matching known last completed turn with items, never compaction/unknown/partial/failed/in-progress outcomes. It first reads only, then resumes original thread; no original-input replay.
- All control logs/files are regular, private 0600, with no prompt in status. Test fixtures use private HOME/CODEX_HOME, no credentials. Verification: python3 code-check.py and python3 smoke-test.py < /dev/null, Linux fixture coverage. Subscription sol independent review of complete diff; Mac/Docker overnight acceptance is documented separately and not claimed from fixtures.
- Preserved vibe: SHA256 5024e624cc73edf9852e95e224ddf88aa8c1f19b23b27346c61ebb58f7cf92cf
- Preserved devcontainer/commands/vsss.md: SHA256 5e74721e1cdcc86912aef851e4b5c368b7d20e495b88fa77a5d8b7e034b94f28
- Preserved devcontainer/commands/vss.md: SHA256 8a34c74bc69463f59a75a0cee5e21ec70ddddde4d33fb458989b864608a5d3c7
- Preserved devcontainer/commands/vs.md: SHA256 3e0fd5eb12321c5140c039d2a4487a016fe7cd112a16200a10f70e6095432c67
- Preserved devcontainer/vsss-stop-guard.sh: SHA256 0426f8abb81fbd03c353f614e294e52b12d4d4efaf2a24583b8ab05788afafe5


## Exact validation and ownership definitions
The runtime contract's Validation details section is normative for grammar,
schema, file checks and recovery. Extra condition fields are ignored when
not applicable, never used as authority. Numeric conditions are exactly 1–5.
Hard escalation and destructive-state eligibility remain the shared workflow's
human/model judgement; the validator checks the declared enum/detail and
supporting audit consistency, not the truth of external effects. No cryptographic
attestation, hostile-filesystem isolation or automatic operator lock removal is
claimed. A completed turn with an invalid completion remains non-terminal and
consumes the normal run ceilings; the next completed ordinary turn clears the
correction. The operator may explicitly remove stale ownership records only
after independently proving all previous owners/children have ended. Automated
code never infers that proof from a PID, timestamp or stale lock alone.
