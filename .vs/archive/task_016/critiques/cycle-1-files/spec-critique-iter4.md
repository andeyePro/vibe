# Spec Critique — task_016 (cycle 1 / iteration 4, closure verification)

Narrow re-audit of the three iter-3 closures the spec revision claims: the `-`
sentinel vs empty-ref disarm logic (+ functional test 4), the long-tool-call
closure rationale pinned in AC6b, and the mandated `touch -t 202001010000`
backdating technique. Only the revised spans were read (iter-3 header
paragraph, AC5 ref-file paragraph, AC6b gate/rationale/functional tests).
Settled design decisions were not re-litigated.

## 1. Sentinel disarm logic (AC5/AC6b) — CLOSED

The revision now uses two distinguishable values instead of one overloaded
empty string: the literal sentinel `-` means "relaunch call site, unconditional
arming" (AC6b condition 2, first disjunct), while an empty or missing
`ref_file` explicitly "fails the gate, never arms" (AC6b condition 2, second
disjunct's negation, restated in AC5's fail-safe note). AC5 and AC6b agree on
this in both directions — AC5: "the relaunch call sites use the DISTINCT
literal sentinel `-`, never empty, so a mktemp failure cannot be confused with
unconditional arming"; AC6b: "an EMPTY or missing ref file → gate fails, never
arms." mktemp always returns a full path (never the literal string `-`), so
the two sentinels can't collide in practice. Functional test 4 exercises
exactly the scenario iter-3 said was untested (`marker active=1, heartbeat
stale, ref argument ""` must never arm the kill) — this is the correct
regression test for the mktemp-failure path. No defect found; iter-3 concern
1 is genuinely closed.

## 2. Long-tool-call closure rationale (AC6b) — NOT CLOSED (BLOCKING)

The rationale's claim (a) — "hooks fire for SUBAGENT tool calls too — vibe's
own security model depends on this ... so long-running Agent/Task dispatches
keep the heartbeat fresh via their internal tool calls" — is factually wrong.
Two independent, credible sources say the opposite for exactly this mechanism
(Claude Code's `settings.json`-configured shell-command hooks, which is what
`guard-bash.sh`/`guard-fs.sh`/the new heartbeat entries all are):

- GitHub `anthropics/claude-code` issue #21460, tagged `[SECURITY]`, filed Jan
  2026: "PreToolUse hooks configured in `~/.claude/settings.json` are not
  enforced when subagents spawned via the Task tool make their own tool
  calls ... restrictions that apply to the main agent can be completely
  bypassed by spawning a subagent."
- GitHub issue #34692 (same repo), reproduced with a concrete PostToolUse
  counter example, closed by maintainers as "not planned" — i.e. not disputed
  as a bug, just not going to be changed.

(The Agent SDK docs' note that `agent_id`/`agent_type` populate "when the hook
fires inside a subagent" describes the SDK's own callback-hook mechanism, a
different code path from the CLI's `settings.json` shell-command hooks that
vibe actually uses — it doesn't contradict the two issues above, which are
specifically about the CLI/settings.json mechanism.)

Practical consequence: when the main `/vsss` session dispatches a Generator,
Tester, or Critic subagent via the Task/Agent tool and blocks on it
synchronously (this task's own Model plan is exactly that pattern), the
PreToolUse heartbeat write fires once at dispatch time and PostToolUse fires
once when the subagent returns — the subagent's own internal Bash/Read/Write
calls do not re-fire the parent's hooks and do not refresh
`/workspace/.vss/heartbeat`. If the subagent runs longer than
`VIBE_STALL_SECS + VIBE_STALL_GRACE_SECS` (default ≈ 32 min), the heartbeat
goes stale and the watchdog kills claude mid-dispatch — this is precisely the
false-positive iter-3 flagged as BLOCKING, not the "exotic, non-`/vsss`" case
the rationale now frames it as. The spec's residual-risk framing ("an exotic
tool blocking >30 min with zero session hook events") is the routine case for
`/vsss`, not an edge case.

Claim (b) — a single Bash tool call is capped at 10 minutes — checks out (this
harness's own Bash tool description states the same 600000ms/10-min ceiling,
consistent with long-documented Claude Code behavior) but doesn't rescue the
rationale: it bounds a raw Bash call issued directly by the main session, not
a Task/Agent dispatch that blocks on an independently-running subagent's own
tool-call sequence, which is the scenario actually in question.

This is the same BLOCKING gap iter-3 raised (its concern 2), now reopened
because the spec asserts it is closed on a premise that doesn't hold. Fix
options are the same three iter-3 offered (stop claiming full closure; document
the ≈32-min single-dispatch ceiling in AC13/MANUAL-TESTS for `/vsss --sessions`
users; and/or recommend a larger `VIBE_STALL_SECS` default for that operating
mode) — none require new engineering, but the spec text needs to stop treating
this as resolved.

## 3. `touch -t 202001010000` backdating (AC6b functional tests 1 and 3) — CLOSED

Verified directly: `touch -t 202001010000 file` on this (GNU/Linux) container
sets mtime to 2020-01-01 00:00:00 exactly, per the standard `[[CC]YY]MMDDhhmm`
format GNU documents for `-t`. BSD/macOS `touch(1)` (OpenBSD and Darwin man
pages) documents the identical `[[CC]YY]MMDDhhmm[.SS]` format for `-t`. Since
`smoke-test.py` is the host-side test file (macOS primary, Linux secondary per
this repo's own CLAUDE.md), the mandated 12-digit absolute-backdate technique
works unchanged on both platforms. No flakiness risk; iter-3 concern 3 is
genuinely closed.

## Other revised-span scan — no new contradictions found

Re-read the iter-3 header paragraph, the AC5 ref-file paragraph, and the AC6b
gate/rationale/test block end to end for freshly-introduced inconsistencies
(not just the three tracked closures): none found. The `-`/empty-string
sentinel split is applied consistently everywhere both ACs reference it, and
functional tests 1-4 collectively cover all four gate-condition-2 states
(older ref, newer/stale-ref, empty ref, plus test 2's independent active=0
case).

## Verdict

**revise**

Concern counts: 1 BLOCKING, 0 MEDIUM, 0 LOW. (2 of the 3 targeted iter-3
closures hold; the long-tool-call closure does not — it reopens iter-3's
original BLOCKING concern 2 on a factual error.)

---

## Planner resolution note (2026-07-10, post-iter-4)

The single BLOCKING concern rested on the factual claim that settings-configured
PreToolUse/PostToolUse hooks do NOT fire for a subagent's internal tool calls
(sourced from GitHub issues #21460 / #34692). Empirically REFUTED in this
container: a headless `claude -p` run with `--settings` defining a PreToolUse
probe hook (`jq -r '"PTU " + .tool_name + " :: " + .tool_input.command'`)
produced, in order:

    PTU Agent :: Run the Bash tool exactly once with the command: echo subage
    PTU Bash :: echo subagent-was-here     <- the SUBAGENT's internal call
    PTU Bash :: echo parent-was-here

The subagent's internal Bash call fires the hook in the claude CLI version
shipped in current vibe containers. The cited issues either predate this
behaviour or describe a different configuration. Spec rationale in AC6b
stands (with the empirical evidence now pinned into the AC text); the other
two iter-4 checks were confirmed closed by the critic itself.

Verdict after resolution: PASS (spec locked after 4 critic iterations:
12 -> 6 -> 3 -> 1 concerns, final concern closed by direct experiment).
