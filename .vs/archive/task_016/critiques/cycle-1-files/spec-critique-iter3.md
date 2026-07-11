# Spec Critique — task_016 (cycle 1 / iteration 3)

Re-audit of `/workspace/.vs/spec.md` against iter-1 (`spec-critique.md`) and iter-2
(`spec-critique-iter2.md`) concerns, plus a fresh hunt focused on the ref-file `-nt`
gate, the relaunch-arming asymmetry, the three functional tests, the `VIBE_STALL_SECS`
default bump, and the new PreToolUse matcher `""` entry. Verified against the current
`vibe` script (no watchdog code exists yet — this is still pre-Generator) and
`devcontainer/commands/vsss.md`.

## Iter-2 concern closure status

Genuinely closed: #1 (AC6a now explicitly required to be a bare, non-`exec`-prefixed
`devcontainer exec` line — confirmed this correctly satisfies both halves of the
pre-existing `test_vibe_final_line_no_exec` at smoke-test.py:2672), #3 (kill-pause now
named `VIBE_STALL_KILL_PAUSE_SECS`, env-overridable; negative sub-test now uses a
short-lived fake claude with explicit backgrounded cleanup), #4 (EXIT-trap edit
dropped entirely — replaced by a self-terminating claude-PID-liveness loop condition,
which removes the whole fragile-trap-edit problem rather than patching it), #5 (the
`$$`-in-heredoc claim is still explicitly flagged as unverified-but-benign, which was
the only ask).

**Only partially closed: #2 (false-positive kill of a live, working session).** See
concern 2 below — the ordinary-interactive-use-with-leftover-marker sub-case is now
solidly closed by the ref-file gate, but the long-single-tool-call sub-case is only
mitigated, not structurally closed, and the workload most likely to trigger it is
`/vsss`'s own core operating pattern.

## Concerns

1. **[BLOCKING, AC5/AC6b] The mktemp-failure fail-safe claim in AC5 contradicts AC6b's own gate semantics — on `mktemp` failure the watchdog arms *unconditionally*, not "never".**
   AC5 says: "on mktemp failure the variable stays empty and the watchdog then never arms on the initial window (fail-safe toward NOT killing)." But AC6b's gate condition (2) is: "`<ref_file>` is empty (relaunch call site — unconditional arming) OR `[ marker -nt ref ]`." These two statements use the exact same sentinel — an empty `ref_file` string — to mean opposite things. If `VIBE_SESSION_REF=$(mktemp ...)` fails on the *initial* launch, the variable is empty, gets passed to `launch_claude_supervised` as `<ref_file>`, and condition (2) reads that as "relaunch call site — unconditional arming" (because that is literally what an empty ref file means to the gate), not "never arm." The mechanism does the opposite of what the fail-safe comment claims: instead of failing safe toward not-killing on the very first window, a `mktemp` failure would make the watchdog behave exactly like a relaunch — arming without the ref-mtime protection — against what may be an ordinary interactive session with a stale, crash-left marker. Nothing in the three functional tests (AC6b) exercises "ref file empty due to mktemp failure on the initial call site" (they only test explicit older-ref, newer-ref, and active=0 cases), so this wouldn't be caught in testing either. Fix needs a distinguishable sentinel — e.g. a dedicated value/flag meaning "gate permanently disarmed" that is checked separately from the "" used at the intentional relaunch call site — not the same empty string doing both jobs. (Note: substituting a nonexistent-path sentinel doesn't fix it either — POSIX/bash `-nt` returns true when the second operand doesn't exist, which is the same "arms anyway" outcome.)

2. **[BLOCKING, AC4/AC6b — iter-2 #2(a) not genuinely closed] The PreToolUse heartbeat write only resets the staleness clock at the START of a tool call; it does not keep the heartbeat fresh for the DURATION of one long call, and `/vsss`'s own primary workload is exactly the shape that trips this.**
   With the grace-period re-check, the real tolerance for a single tool invocation with no other tool activity is `VIBE_STALL_SECS + VIBE_STALL_GRACE_SECS` from that call's start (default 1800 + 120 = 1920s ≈ 32 minutes) — if the call is still running past that point, the watchdog kills claude mid-call. Every `/vss`/`/vsss` iteration is, from the parent session's perspective, one or more single Task/Agent-dispatch tool calls that block until the subagent returns — Generator/Tester/Critic dispatches for "subtle bash + docs" work (this very task's own Model plan) can easily run past 32 minutes, especially at a higher rung of the escalation ladder. That means the fix for "`/vsss --sessions` doesn't survive the picker-stall" can now kill a `/vsss --sessions` run that is doing nothing wrong at all — mid-Generator-cycle — which is a materially worse failure mode for the user than the original bug in one respect: the original bug just hung silently; this one actively terminates a productive autonomous run with an in-container `pkill`. The spec's revision summary states the false-positive surface "is closed"; per this analysis it is only closed for the "stale marker + ordinary interactive use" sub-case (via the ref-gate), not the "long legitimate single tool call" sub-case iter-2 also flagged. This doesn't necessarily need new engineering to resolve — the honest fix may be to (a) stop claiming the surface is fully closed, (b) explicitly document the ~32-minute single-call ceiling in AC13/MANUAL-TESTS so users running `/vsss --sessions` with long Generator cycles know to raise `VIBE_STALL_SECS` accordingly, and/or (c) recommend a larger default specifically for this operating mode. As written, a Generator/Tester building strictly to the AC text has no signal that this gap exists, and no test could catch it (a live 30+ minute subagent dispatch isn't something smoke-test.py can exercise).

3. **[MEDIUM, AC6b functional tests 1 and 3] The spec leaves the ref-vs-marker mtime ordering technique as an unpinned "sleep/backdate — or `touch -t`" choice, risking a flaky test on filesystems with 1-second mtime granularity.**
   Test 1 (positive) needs the ref file demonstrably OLDER than the marker; test 3 (negative) needs it demonstrably NEWER. The spec offers "create ref, sleep/backdate, then write marker — or write ref with `touch -t` in the past" as alternatives without requiring either. A Tester (haiku, ceiling sonnet per the Model plan) that just creates the two files back-to-back without an explicit ≥1-second gap or an explicit `touch -t` backdate is exposed to exactly the same-second `-nt` race the task brief asks about: two files created within the same filesystem mtime tick can compare equal-or-ambiguous under `-nt`, making the test intermittently flaky rather than deterministically pass/fail. Recommend the spec mandate the deterministic technique (`touch -t` backdating one file, not wall-clock ordering with a sleep) for both tests, since a sleep-based approach is exactly the thing that can fail under coarse mtime granularity that this concern is about. (Real-world production risk from the same underlying granularity issue is low — container/claude startup latency between `VIBE_SESSION_REF` creation and the skill's first marker write is realistically several seconds, well outside a 1-second collision window — so this is a test-construction concern only, not a production one.)

## Other items checked, no defect found

- **PreToolUse matcher `""` colliding with guard-bash/guard-fs adjudication**: confirmed via Claude Code hooks documentation that PreToolUse hook-group entries with different matchers run in parallel and merge independently; a hook that exits 0 with empty stdout (which the heartbeat command does — its `date +%s` output goes to a *file* via redirect, not stdout, and the whole thing is guarded with `|| true`) is documented as "no decision — normal permission flow applies," so it cannot suppress or reorder guard-bash.sh's/guard-fs.sh's own `ask`/`deny` decisions. No defect.
- **Relaunch-arming asymmetry (`ref=""` on relaunch) — no hole found**: `launch_claude_supervised`'s heartbeat-seed step ("seeds the heartbeat via `auto_resume_heartbeat_write` whenever the marker file exists") runs before the watchdog starts polling, on *every* call site including relaunches. That means a relaunched window's heartbeat is always fresh at the moment the watchdog arms, even though the actual `.vss/heartbeat` file may be hours stale from the previous window's stall — closing the "immediately-stale-at-relaunch" failure mode the ref="" design otherwise looks exposed to.
- **`mv`-based marker refresh mtime vs `-nt`**: `mv` (rename) takes the source (freshly-written tmp file)'s mtime, so the `/vsss` skill's per-iteration marker refresh does produce a genuinely current mtime each time, consistent with the "marker was refreshed during this session" claim.
- **`VIBE_STALL_SECS` default of 1800**: no conflict found with AC11's manual-test values (all explicitly overridden inline), `resume_at` padding (independent arithmetic, unaffected), or the 5h window math in `vsss.md`. The coincidental reuse of "1800" as both the new stall-threshold default and the launcher's pre-existing `_ar_wait` fallback constant (vibe:1665) is unrelated code with no shared variable — not a conflict, just a coincidence.
- **AC6a / `test_vibe_final_line_no_exec` cross-test dependency (iter-2 #1)**: verified directly against smoke-test.py:2672 — the existing test's two assertions (no line starts with literal `exec devcontainer exec`; at least one stripped line starts with `devcontainer exec` and not `exec `) are both satisfied once AC6a's kill command is the required bare, non-`exec`-prefixed invocation. Confirmed closed.
- Internal contradictions elsewhere (AC1–AC3 boundary semantics, AC7 trap re-arming, AC8 exit propagation, AC12 gitignore pattern, AC13 doc scope) were re-read end to end; none found.

## Verdict

**revise**

Concern counts: 2 BLOCKING, 1 MEDIUM, 0 LOW.
