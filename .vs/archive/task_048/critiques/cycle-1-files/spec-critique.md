# Spec Critique — task_048 codex-supervisor (spec-draft-codex-supervisor.md)

## Verdict: revise

## Concerns

1. **AC4 — BLOCKING — sandbox choice contradicts the plan's own D1.** AC4 sends
   `sandbox:"danger-full-access"`, correct per F11 (no user namespaces here).
   But `docs/codex-integration-plan.md` D1 already decides
   `/etc/codex/requirements.toml` will set `allowed_sandbox_modes` to
   workspace-write/read-only, "never danger-full-access." Once item 4 ships
   that requirements file, F2 says any out-of-allowlist value is rejected at
   config load (`ConstraintError::InvalidValue`) — this supervisor's
   `thread/start`/`thread/resume` would then fail even though item 6 has no
   *code* dependency on item 4. Spec must either flag that D1 needs revising
   to allow `danger-full-access` (matching F11), or define what the
   supervisor does if the sandbox request is refused. Not addressed at all.

2. **AC6/AC7 — BLOCKING — ceilings can never fire during a quota-exhaustion
   loop.** AC7 says ceilings are "checked after every completed turn," but
   AC6's wait/retry cycle by construction never produces a `completed` turn
   while quota is exhausted. A stuck account (no `resetsAt` ever supplied,
   backoff capped at 3600s) loops past `max-wall-seconds` (default 10h)
   forever, since the only checkpoint that could stop it is gated behind an
   event that this exact failure mode never produces. Ceilings (wall-time at
   minimum) must be evaluated before every AC6 wait, not only in AC7's
   completed-turn branch.

3. **AC6 — BLOCKING — "increment resumes" overloads AC4's counter.** AC4
   defines `resumes` for actual process-kill + `thread/resume` events. AC6
   reuses the same field name for in-process quota-wait retries, and AC4's
   state schema has no second counter. A routine multi-window quota stretch
   could burn through `max-resumes` (default 20) purely from backoff cycles
   and trigger an unwarranted exit 3, while conflating it with the
   crash-resume ceiling it's supposed to bound. Give quota retries their own
   field, or state explicitly that the ceiling is deliberately shared and why.

4. **AC5 — BLOCKING — one forbidden command permanently kills the run.**
   Per the verified facts (codex-appserver.md §3, `exec_policy.rs:808-812`),
   an exec-policy-Forbidden command fails the whole Codex *turn*, not just
   that command. AC5 routes any non-quota `failed` turn to a terminal
   `exit 1`. So one blocked shell idiom anywhere in a multi-hour unattended
   run ends the entire supervisor rather than sending `continue` and letting
   the agent try something else — a materially worse failure mode than the
   "durable, failure-aware" framing in the task summary. Needs a distinct
   branch (or justification for treating it as fatal).

5. **AC9 — BLOCKING, test-evasion.** AC7's exit gate depends on `$vsss`'s own
   final message literally containing `VSSS-EXIT: <reason>`, but AC9 only
   requires vsss.md to gain a short *documentation* note describing that the
   skill "must emit" it — it never requires editing the substantive
   "Reporting back at exit" section to actually print that line. AC10's
   tests all run against a stub app-server and never exercise real vsss.md
   text, so the whole suite goes green while the live integration silently
   never emits the marker. State explicitly that AC9 edits the Reporting
   section itself, not just a side-note about it.

6. **AC4 — BLOCKING gap — promptHash mismatch undefined.** No behavior is
   given for an existing state file matching `cwd` but not `promptHash`
   (prompt file changed, same `--state`). Falling through to "first run"
   would silently overwrite/orphan the prior thread's record with no error
   and no AC10 coverage. Define refuse-by-default or explicit overwrite.

7. **AC5 — MINOR.** "the binding window is the one with usedPercent >= 100"
   doesn't say which wins if `primary` AND `secondary` are both ≥100
   simultaneously (plausible in practice); "merged into lastRateLimits"
   doesn't define field-level vs whole-snapshot merge for the genuinely
   sparse `RateLimitSnapshot` (`primary`/`secondary` independently Optional,
   `account.rs`).

8. **AC5 — MINOR.** The quota-detection set omits `sessionBudgetExceeded`
   and the 429-bearing variants `responseStreamConnectionFailed`,
   `responseStreamDisconnected`, `responseTooManyFailedAttempts` (all real
   `CodexErrorInfo` members, `shared.rs`) — these fall into "any other error
   → exit 1" as written. If deliberate, say why; if not, the set is
   incomplete.

9. **AC7 — MINOR, under-specified.** "the agent's final message" isn't
   scoped: matched only against the turn's last `item/agentMessage`, or
   anywhere in the turn's aggregated log? A false-positive substring match
   mid-narration is plausible and untested.

10. **AC5/AC8 — MINOR.** Declining `item/tool/requestUserInput` and
    `mcpServer/elicitation/request` with a generic JSON-RPC error is assumed
    safe by analogy to `item/commandExecution/requestApproval` (independently
    verified here as non-blocking: `bespoke_event_handling.rs:2076-2156`,
    `Ok(Err(_))` → denies gracefully) — the other two request kinds aren't
    checked against source.

11. **AC3/AC10 — MINOR.** AC10's assertion list never names an explicit test
    for the spawned child's env being limited to exactly
    PATH/HOME/CODEX_HOME/LANG — a security-relevant claim central to D1/D2's
    isolation model, left untested by name (only argv is called out).

12. **Task summary — MINOR, citation error.** "the sandbox field's exact enum
    spelling is taken from ... protocol/v2/thread.rs" is wrong: `SandboxMode`
    is defined in `protocol/v2/shared.rs` (verified: `shared.rs:305`);
    `thread.rs` only imports it. Small, but this task's whole premise rests
    on citation discipline.

13. **AC2 — MINOR.** "a prompt whose first token is `/vs`, `/vss` or
    `/vsss`" doesn't state case-sensitivity or exclude near-misses like
    `/vss:foo`/`/vssx`; presumably exact-token match, but not spelled out.
