---
description: Wide mode — maximise concurrent agents to cut wall time without lowering quality. Orthogonal to /diet↔/feast (token axis) and --fable-subagents (model axis). Reverse with /narrow.
---

# /wide — the width axis

`/wide` widens how many agents run at once. It is orthogonal to two other axes: `/diet` ↔ `/feast` is the token-spend axis (how much each agent does), and `--fable-subagents` is the model axis (which tier runs). `/wide` changes only how many dispatches are in flight together — never what runs, never which tier. Default (no `/wide`): strictly serial dispatch, unchanged from today.

## Caps

- **6 default, 8 ceiling** — overall concurrent agents across the whole harness. `/wide N` overrides the default; N is always clamped to 8, the hard max however requested.
- **max 2 concurrent** heavy verifications (full `smoke-test.py`, `npm run check`, docker builds) — rationale: the **10-minute Bash cap** on any single foreground command means several full suites running at once starve each other's wall-clock budget before finishing; two is the most that reliably land inside it.
- **single-writer-per-file** — no two concurrent agents ever hold write access to the same file. Two queued items that would touch the same file run serially, or one moves to its own worktree.
- **max 1 concurrent Fable dispatch** — `/wide` never widens the Fable grant: `--fable-subagents` still gates whether the rung runs at all; `/wide` only ever raises the count of everything ELSE running alongside it (`/wide` never widens the grant). At most one of the concurrent slots may be a live Fable call, at the 8-ceiling or below it.

## Stacking table

| | no Fable | `--fable-subagents` |
|---|---|---|
| `/wide` + `/diet` | mandatory roles only, concurrently where legal; Heavy-verify cap 1 | same, plus the one mandatory Fable-tier role may run |
| `/wide` + default | 6 default, 8 ceiling; heavy-verify cap 2 | same, max 1 concurrent Fable dispatch |
| `/wide` + `/feast` | 8 agents, full roster, `--panel 3` reviewers fan out concurrently | 8 agents, `--panel 3`, max 1 concurrent Fable dispatch |

`/narrow` × any cell = strictly serial — `/narrow` collapses every cell above to one-at-a-time, full stop.

## What may overlap, what must stay serial

May run concurrently:
- **Tester ∥ panel** — the mechanical Tester and a `--panel` review batch, once the Generator's diff exists.
- **Evaluator pre-reads** — the chair reading earlier artifacts (spec, diff, prior verdicts) while a later subagent is still in flight.
- The **next queue item's Planner + Spec Critic**, run while the current item's Generator or Tester is still working — spec-shaping shares no state with in-flight code.

Must stay serial:
- **Spec Critic iterations** (serial) — each iteration reads the Planner's revision to the previous critique; iterating against itself is incoherent.
- **Generator → Tester of the same cycle** (serial) — Tester needs the Generator's diff to exist first.
- The rule that subagents run long commands in the foreground and `never run_in_background` still applies unchanged: concurrency is agent-level (several simultaneous `Agent(...)` dispatches), never achieved by one agent backgrounding its own command.

## Chair discipline

Discipline: one notification per completion; never poll agent status between dispatches. The chair does not end its turn while agents are running unless waiting for them is the only remaining action — if other unblocked work exists, do it while agents run. Dispatch every legally-concurrent batch as one message with multiple tool uses.

## Within-cycle clarification

`/vs`'s rule 'No cross-subagent context sharing' is within-cycle: it governs Generator/Tester/Reviewer/panellists inside ONE cycle of ONE task. It is not breached by overlapping the NEXT item's Planner/Spec Critic with THIS item's Generator — different tasks, no shared cycle state.

## Inverse: `/narrow`

`/narrow` turns `/wide` off — see [`narrow.md`](narrow.md).
