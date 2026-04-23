---
description: Adversarial agentic harness — Planner + Evaluator (Opus) orchestrate independent Spec Critic, Generator (Sonnet), and Tester (Haiku) subagents against a spec. `--fuzzy` swaps Tester for an independent Reviewer (Sonnet) so tasks without mechanical acceptance criteria still get adversarial review. Pass the task prompt after the command.
---

# /vs — adversarial harness

You (top-level, Opus) play two roles across the run: **Planner** (Step 1–2, plus revision in Step 3) and **Evaluator** (Step 6–7). Between them, you dispatch independent subagents: a Sonnet **Spec Critic** that audits the spec before any code runs, a Sonnet **Generator** that writes the feature, and — depending on mode — either a Haiku 4.5 **Tester** (default rigorous mode) or a Sonnet **Reviewer** (`--fuzzy` mode). Generator never sees Tester's / Reviewer's output; Tester / Reviewer never sees Generator's report. That separation is the point.

Chronological flow per cycle:

```
default:   Planner → Spec Critic → (revise) → Generator → Tester   → Evaluator → (iterate or accept)
--fuzzy:   Planner → Spec Critic → (revise) → Generator → Reviewer → Evaluator → (iterate or accept)
```

Spec Critic runs **once at task start**, before user approval. It does not re-run on cycle iteration — the spec is locked after user approval (changing it restarts at cycle 1 by rule).

## Modes

- **Default (rigorous)** — for tasks with verifiable acceptance criteria. Tester (Haiku 4.5) writes immutable tests; pass/fail is mechanical.
- **`--fuzzy`** — for tasks without verifiable criteria (`fix this bug`, `make this nicer`, `look around for X`). Reviewer (Sonnet) reads Generator's diff + original prompt and produces a written verdict. Pass/fail is judgment, not mechanical. Use when the simplicity gate would otherwise refuse on "no verifiable criteria" grounds.

## Flags

- `/vs --max N <prompt>` — override the cycle ceiling. Default is whatever Planner proposes.
- `/vs --fuzzy <prompt>` — run in fuzzy mode (Reviewer replaces Tester). Combinable with `--max`.

## State directory: `.vs/`

Created at repo root.

- `.vs/spec.md` — sprint contract. Planner writes, Spec Critic reviews, Planner revises, user approves. Read-only for Generator / Tester / Reviewer. **Committed.**
- `.vs/tasks.json` — structured task list. Status-field mutations only. Schema:
  ```json
  {
    "id": "task_001",
    "description": "one-line goal",
    "implementation_status": "pending|in_progress|complete",
    "test_status": "pending|in_progress|passing|failing",
    "assigned_to": "generator|tester|reviewer|evaluator",
    "mode": "rigorous|fuzzy",
    "last_modified": "<ISO8601>"
  }
  ```
- `.vs/progress.md` — append-only human-readable log. Each cycle appends a block. **Committed.**
- `.vs/cycle-N/` — per-cycle artifacts. **Gitignored.** Retained across cycles so you can compare trajectories.
  - `cycle-1/spec-critique.md` — Spec Critic's audit (cycle-1 only — spec doesn't change after that)
  - `cycle-N/generator-report.md` — Generator's summary of what it did
  - `cycle-N/diff.patch` — what Generator changed this cycle
  - **Rigorous mode:** `cycle-N/test-output.log` (full Tester output) + `cycle-N/summary.md` (3-line pass/fail summary).
  - **Fuzzy mode:** `cycle-N/reviewer-verdict.md` (Reviewer's written verdict with rationale) + `cycle-N/summary.md` (3-line summary: verdict line + concerns count + key concern).

## Step 1 — Simplicity gate (Planner)

Before anything else, ask: does this task genuinely need `/vs`? Refuse if any of:

- Task is trivial (single file, single function, mechanical edit). Suggest running inline instead.
- Task requires user decisions mid-flow that a subagent can't make alone.

Special handling for **"no verifiable acceptance criteria"** (exploratory, aesthetic, "make it nicer"):

- If the user passed `--fuzzy` explicitly → no gate trip; proceed to Step 2 in fuzzy mode.
- Otherwise → **do not refuse outright.** Explain briefly which aspect makes verification hard, then offer the user two options:
  1. **Tighten the brief:** propose 2–3 sketched deterministic acceptance criteria (even if partial) and ask whether they want to run rigorous `/vs` with those. If yes, incorporate into Step 2.
  2. **Run `--fuzzy`:** reply with `--fuzzy` to use a Reviewer instead of a Tester. Judgment verdict, not pass/fail tests.

Wait for the user to pick. If they decline both, stop.

For the other two refusal cases (trivial, user-decisions-mid-flow), refuse with the reason and stop.

## Step 2 — Plan: draft spec (Planner)

Write a first draft of `.vs/spec.md` with:

- **Task summary** — one paragraph: what's being built and why.
- **Acceptance criteria** — bulleted.
  - Rigorous mode: each criterion verifiable by a test (a test can decide pass/fail). Aim for 5–15.
  - Fuzzy mode: heuristic criteria acceptable ("should preserve backward compatibility", "should not leak secrets in log output"). Still aim for 5–15, and prefer criteria that a thoughtful reviewer can judge from reading the diff.
- **Out of scope** — explicit list of things NOT to build. Prevents Generator scope creep; Evaluator / Reviewer flags violations. Still enforced in both modes.
- **Review focus** (rigorous mode writes this as **Test location**) —
  - Rigorous: the detected/proposed test directory or file. Tester writes tests here. **Once Tester commits, tests are immutable — Generator cannot edit them.**
  - Fuzzy: a short bulleted list of what Reviewer should scrutinize hardest (e.g. "secret-handling paths", "error-swallowing silence"). No immutability rule because there's no test file.
- **Proposed budget** — `N cycles` with a one-line rationale. If user passed `--max`, honor that.

Rigorous mode detects the repo's test convention (`tests/`, `test/`, `__tests__/`, `spec/`); if none, proposes `tests/`. Fuzzy mode skips this step.

Proceed to Step 3 (Spec Critic) — do **not** show the draft to the user yet.

## Step 3 — Spec critic (Sonnet)

Spawn `Agent(subagent_type: "general-purpose", model: "sonnet")`:

- Read `.vs/spec.md`. Find weaknesses BEFORE they cost a cycle. Adversarial; default to flagging.
- Each acceptance criterion:
  - Rigorous mode: is it mechanically verifiable by a test? Flag fuzzy phrasing.
  - Fuzzy mode: is it concrete enough for a reviewer to judge from the diff? Flag criteria that are pure vibes ("should feel nicer") with no observable manifestation.
- Out of scope: list loopholes — features not excluded but should be.
- Internal contradictions between criteria.
- Trivial test-evasion (rigorous) or trivial review-evasion (fuzzy — criteria Reviewer would rubber-stamp without scrutiny).
- Type / schema / format fuzziness.
- Under-specified failure modes.
- Output `.vs/cycle-1/spec-critique.md` with **Concerns** (numbered, with AC#) and **Verdict** (`pass` or `revise`).

Planner reads critique. If `revise`, update spec, re-spawn critic (max 2 iterations). If `pass` or max hit, append task to `TODO.md` Open, show final spec + `spec critic: pass after N iteration(s)` note to user. Wait for approval. In fuzzy mode the user note also includes `mode: --fuzzy`.

## Step 4 — Generate (Sonnet Generator subagent)

Spawn `Agent(subagent_type: "general-purpose", model: "sonnet")`:

- Read `.vs/spec.md`. Source of truth.
- Implement to satisfy every acceptance criterion.
- Rigorous mode: **do not touch files under the test directory named in spec.md.** Fuzzy mode: this rule doesn't apply (no test dir).
- Do not guess what Tester / Reviewer will do. Build to the spec.
- When done: write `.vs/cycle-<N>/generator-report.md`, update `.vs/tasks.json` (`implementation_status: complete`), produce `.vs/cycle-<N>/diff.patch` via `git diff > .vs/cycle-<N>/diff.patch`.
- Internal retry budget: 3 attempts if blocked. Report the block in the report file.

## Step 5 — Verify (branches by mode)

### Step 5a — Test (Haiku 4.5 Tester) — RIGOROUS MODE ONLY

Spawn `Agent(subagent_type: "general-purpose", model: "haiku", ...)`. Tester work is largely mechanical — Sonnet reserved for Generator, Opus for Planner/Evaluator, Haiku for this.

Independence rule: Tester sees only `.vs/spec.md`, the test-dir layout, and the current source tree — NOT Generator's diff or report.

Tester's brief:
- For each acceptance criterion, write a test in the spec's test location that verifies it. Use repo conventions.
- Run the tests. Write full output to `.vs/cycle-<N>/test-output.log` and a 3-line summary (total/passed/failed/key-failures) to `.vs/cycle-<N>/summary.md`.
- **Mandatory regression check:** also run any pre-existing test suite. Any pre-existing failure caused by Generator's diff is a regression — report under `Regressions:` line.
- Update `.vs/tasks.json` (`test_status: passing|failing`).
- **Once committed, these tests are frozen.** Evaluator enforces immutability on subsequent cycles.

### Step 5b — Review (Sonnet Reviewer) — FUZZY MODE ONLY

Spawn `Agent(subagent_type: "general-purpose", model: "sonnet")`. Reviewer needs judgment, not mechanical execution — Sonnet tier, same as Generator.

Independence rule: Reviewer sees only `.vs/spec.md`, the original user prompt (pasted into the Reviewer brief by Planner), and `.vs/cycle-<N>/diff.patch` — NOT Generator's report or reasoning.

Reviewer's brief:
- Read the spec, the original user prompt, and the diff.
- For each acceptance criterion, judge whether the diff delivers it. Fuzzy criteria require defensible prose reasoning.
- Look hardest at the **Review focus** items from spec.md.
- Independently check: scope creep against "Out of scope", sloppy code, swallowed errors, invariants in `CLAUDE.md § Invariants`, vibes-off solutions (solved a different problem than asked), missing edge cases a thoughtful colleague would spot.
- Output `.vs/cycle-<N>/reviewer-verdict.md` with three sections:
  1. **Per-criterion assessment** — bullet per AC: `✓ delivered`, `✗ missing/broken`, or `? unclear` with one-sentence rationale.
  2. **Concerns** — numbered list of issues beyond the criteria (scope creep, sloppy code, etc.).
  3. **Verdict** — `pass`, `revise`, or `fail`. `revise` means concerns fixable next cycle; `fail` means the approach is wrong and the spec/direction needs rethinking.
- Also write a 3-line `.vs/cycle-<N>/summary.md`: verdict line, concerns count, single key concern.
- Update `.vs/tasks.json` (`test_status: passing|failing` — map verdict: pass → passing, revise/fail → failing).
- No immutability rule. Reviewer's verdict is per-cycle, not frozen.

## Step 6 — Evaluate (Evaluator = you, Opus)

Read in this order, stopping as early as a clear verdict emerges:

1. `.vs/cycle-<N>/summary.md` — quick pulse. Check for `Regressions:` line (rigorous) or verdict line (fuzzy).
2. Rigorous: `.vs/cycle-<N>/test-output.log` if summary shows failures or you need detail.
   Fuzzy: `.vs/cycle-<N>/reviewer-verdict.md` — read the per-criterion assessment and concerns.
3. `.vs/cycle-<N>/diff.patch` — scope creep, dead code, swallowed errors, invariant violations. Check `CLAUDE.md § Invariants`.
4. `.vs/cycle-<N>/generator-report.md` — only after forming your own view (avoids anchoring).

Decide strictly:

- Rigorous: all NEW tests pass? All PRE-EXISTING tests still pass? (mechanical — regression → automatic fail)
- Fuzzy: Reviewer verdict `pass`? Concerns addressed in diff? Do YOU agree with the Reviewer after reading diff yourself? (judgment — your call, Reviewer is input)
- Does the diff satisfy each acceptance criterion beyond mere verification-pass?
- Any scope creep against "out of scope"?
- Any project invariant violations?
- Rigorous: Generator touched test directory? → automatic fail.
- Cycle ≥2 rigorous: Tester edited prior-cycle tests? → automatic fail (immutability breach).

Default-fail on ambiguity. Adversarial by design.

## Step 7 — Iterate, accept, or escalate

- **Pass:** append verdict block to `.vs/progress.md`. Move `TODO.md` entry to `## Done`. Commit with `/vs cycle <N>: pass` (or `/vs --fuzzy cycle <N>: pass`). Report to user: cycle number, key changes, how each criterion was verified (or in fuzzy mode, Reviewer's rationale highlights).
- **Fail, cycles remaining:** append specifics to `.vs/progress.md`. Re-dispatch Generator as a *fresh* Sonnet subagent. Hand it: the spec, the failure list, and either the test-output.log (rigorous) or the reviewer-verdict.md (fuzzy). Do **not** hand rigorous-mode Tester's test code to Generator. Increment cycle counter, continue from Step 4.
- **Fail, ceiling hit:** compare summaries across cycles. Failure count trending down? New failures appearing? Report trajectory to user; ask whether to continue, abandon, or switch strategy.
- **Plateau detection:** if three consecutive cycles show the same failure / concern set, flag proactively before the ceiling. Plateaus usually mean spec or approach is wrong, not effort.

## Rules

- **Immutable tests (rigorous only)** — once Tester lands tests, nobody edits or removes them. If acceptance criteria change, Planner writes a revised spec and restarts cycle 1. Does not apply in fuzzy mode (no tests).
- **Status-field mutations only** on `tasks.json`. No unstructured edits.
- **Fresh subagents per cycle** — context reset over compaction. Continuity via `.vs/` files only.
- **No cross-subagent context sharing** — Generator never sees Tester's / Reviewer's output; Tester / Reviewer never sees Generator's report. Spec Critic sees only the spec.
- **Per-cycle commits** after pass or at escalation points.
- **Regression gate (rigorous only)** — Tester runs pre-existing test suite; failure caused by Generator's diff is automatic cycle fail. Fuzzy mode cannot enforce this automatically — Reviewer is asked to flag suspected regressions in the diff, but Evaluator should run pre-existing tests manually before declaring pass if there is a test suite at all.

## When to refuse or stop

- Simplicity gate (Step 1) — trivial or user-decisions-mid-flow.
- User declines both Step-1 options (tighten brief or `--fuzzy`) — stop, don't guess.
- Plateau across three consecutive cycles — surface to user before ceiling.

---

Read the user's prompt below this line. Start at Step 1.
