---
description: Adversarial agentic harness — Planner + Evaluator (session model) orchestrate independent Spec Critic, Generator, and Tester subagents against a spec, on a per-task Model plan with a capability-gated escalation ladder (haiku→sonnet→opus→ask-before-Fable). `--fuzzy` swaps Tester for an independent Reviewer so tasks without mechanical acceptance criteria still get adversarial review. Pass the task prompt after the command.
---

# /vs — adversarial harness

You (top-level, whatever model this session launched on — Opus by default, Fable 5 via `vibe --fable` for genuinely huge/ambiguous tasks) play two roles across the run: **Planner** (Step 1–2, plus revision in Step 3) and **Evaluator** (Step 6–7). Between them, you dispatch independent subagents: a Sonnet **Spec Critic** that audits the spec before any code runs, a **Generator** that writes the feature (tier per the Model plan, Sonnet default), and — depending on mode — either a Haiku 4.5 **Tester** (default rigorous mode) or a Sonnet **Reviewer** (`--fuzzy` mode). Generator never sees Tester's / Reviewer's output; Tester / Reviewer never sees Generator's report. That separation is the point.

Model choice is part of the plan, not a constant — see § Model economy. Always pass `model:` explicitly in every `Agent(...)` dispatch: per-agent `model:` frontmatter is broken upstream (claude-code issue #44385), so the dispatch parameter is the only reliable routing.

Chronological flow per cycle:

```
default:           Planner → Spec Critic → (revise) → Generator → Tester             → Evaluator → (iterate or accept)
--fuzzy:           Planner → Spec Critic → (revise) → Generator → Reviewer           → Evaluator → (iterate or accept)
--fuzzy --panel:   Planner → Spec Critic → (revise) → Generator → Panel (N blind)    → Evaluator → (iterate or accept)
--panel (rigorous): Planner → Spec Critic → (revise) → Generator → Tester ∥ Panel    → Evaluator → (iterate or accept)
```

Spec Critic runs **once at task start**, before user approval. It does not re-run on cycle iteration — the spec is locked after user approval (changing it restarts at cycle 1 by rule).

## Modes

- **Default (rigorous)** — for tasks with verifiable acceptance criteria. Tester (Haiku 4.5) writes immutable tests; pass/fail is mechanical.
- **`--fuzzy`** — for tasks without verifiable criteria (`fix this bug`, `make this nicer`, `look around for X`). Reviewer (Sonnet) reads Generator's diff + original prompt and produces a written verdict. Pass/fail is judgment, not mechanical. Use when the simplicity gate would otherwise refuse on "no verifiable criteria" grounds.

### Relation to canonical Architect/Writer/Reviewer

Claude Code's welcome banner suggests creating Software Architect, Code Writer, and Code Reviewer agents via `/agents`. `/vs` strictly extends this three-role pattern with two adversarial-separation splits: the canonical Architect role becomes Planner (drafts the spec) plus Spec Critic (audits it BEFORE any code is written), and the canonical Reviewer role becomes Tester (mechanical, Haiku-tier; rigorous mode) or Reviewer (judgment-based, Sonnet-tier; `--fuzzy` mode) plus Evaluator (Opus-tier final verdict). The Tester/Reviewer + Evaluator split lets cheap Haiku do rote test-writing while reserving Opus for the pass/fail call. Full audit: [`../../.vs/audits/architect-writer-reviewer.md`](../../.vs/audits/architect-writer-reviewer.md).

| Canonical role     | `/vs` equivalent                                                |
| ------------------ | --------------------------------------------------------------- |
| Software Architect | Planner + Spec Critic                                           |
| Code Writer        | Generator                                                       |
| Code Reviewer      | Tester (rigorous) or Reviewer (`--fuzzy`) + Evaluator           |

## Model economy

Two principles (Martin, 2026-07-04):

- **Route by task class, not role prestige.** Fable 5's edge concentrates in long-horizon, complex work — big well-specified builds, ambiguous multi-cycle tasks. On small scoped calls Opus is near-parity and credits buy nothing. The manager keeps expensive models away from admin.
- **Subscription models everywhere by default.** Credit-billed models (Fable 5 from 8 Jul 2026) run only with explicit per-task user consent, per `CLAUDE.md § Non-goals`.

### Role defaults

| Role | Default | Why |
| --- | --- | --- |
| Planner + Evaluator | session model (Opus chair normally; `vibe --fable` only for huge/ambiguous tasks) | judgment interleaved with admin — mid-tier chair, expensive consultants |
| Spec Critic | sonnet | adversarial reading, scoped |
| Generator | sonnet, tier per Model plan | bulk tokens — cheapest tier that passes |
| Tester | haiku | mechanical test-writing |
| Reviewer (`--fuzzy`) | sonnet | judgment from a diff |
| Panellists (`--panel`) | sonnet ×N (default 3) | blind fan-out of the review role; the upstream pattern runs all-Opus — deliberately re-tiered, N Sonnets beat 1 Opus here because the mechanism's value is INDEPENDENCE, not depth; one Opus depth-probe is the chair's optional extra on correlated consensus |

### Model plan (lives in spec.md)

Step 2's spec includes a **Model plan**: Planner estimates task difficulty and proposes a starting tier and escalation ceiling per role — e.g. `Generator: sonnet, ceiling opus; Fable rung: not pre-authorised`. The user approves it with the spec, which is also the moment they pre-authorise or withhold the credit-billed rung for this task. **Absent an explicit statement, the Fable rung is NOT pre-authorised.** A hard task should start at the tier the difficulty estimate demands — don't burn two cycles proving Sonnet can't do it.

### Escalation ladder (capability-gated)

Tier bumps happen on the Step-7 fail path, and ONLY when the Evaluator diagnoses a **capability failure** — reasonable approach, execution fell short. Spec ambiguity, brittle tests, scope creep, and wrong-approach failures do NOT escalate (they route to spec revision / plateau handling as before — a model bump can't fix a bad spec).

- **Generator**: sonnet → opus after 2 consecutive capability-fails → **Fable 5 on the locked spec**, only with user consent (Model-plan pre-auth — including a standing `--fable-subagents` grant — or a fresh ask quoting est. credits). The Fable rung re-dispatches the *Generator*, not the chair: compact brief (spec + failure history + repo access), fresh context — Fable's one-shot strength on well-specified builds at minimum credit spend.
- **Tester**: haiku → sonnet when the Evaluator flags test *quality* (shallow tests, ACs unmapped) rather than test results.
- No de-escalation mid-task; new tasks start back at defaults.

Log every escalation in `.vs/progress.md` (`escalated generator sonnet→opus: <one-line diagnosis>`) and, under `--cost`, in `cost.json`. Record the tier that finally passed in the pass verdict — over time that calibrates Planner's starting-tier estimates.

## Flags

- `/vs --gen <haiku|sonnet|opus> <prompt>` — override the Generator's starting tier for this run.
- `/vs --fable-gen <prompt>` — pre-authorise the Fable rung AND start the Generator there. The user is explicitly spending credits; still quote the estimated credit cost in the spec-approval message.
- `/vs --fable-subagents <prompt>` (alias `--fable`) — pre-authorise the credit-billed Fable rung for this invocation WITHOUT forcing it (the alias does NOT imply `--fable-gen` — it grants permission, it never forces a Fable start): the Model plan records `Fable rung: pre-authorised (--fable-subagents)`, the Planner MAY start the Generator at Fable when the difficulty estimate genuinely demands it (huge/ambiguous well-specified builds), and the escalation ladder may take the Fable rung on capability-fails without a fresh ask. Task-class routing still governs: NEVER Fable for mechanical roles (Tester, Spec Critic, cost admin) or for scoped small generations where Opus is near-parity — the flag buys permission, not blanket routing. Without it, the ask-before-Fable gate is unchanged. Distinct from the `vibe --fable` LAUNCHER flag, which sets only the chair/session model and authorises no subagent spend.
- `/vs --max N <prompt>` — override the cycle ceiling. Default is whatever Planner proposes.
- `/vs --fuzzy <prompt>` — run in fuzzy mode (Reviewer replaces Tester). Combinable with `--max`.
- `/vs --panel [N] <prompt>` — fan the review out to N blind, independent panellists (default 3; keep it odd; Sonnet tier). In `--fuzzy` mode the panel REPLACES the single Reviewer; in rigorous mode it ADDS a judgment layer beside the Tester (the mechanical test gate still governs pass/fail — a green suite with a dissenting panel is a chair adjudication, not an automatic pass). See § Step 5c. Orthogonal to `--plain`/`--techy`/`--verbosity` (each panellist honours them) and to `--cost` (each panellist logs as `role: "panel_reviewer"`). Panel disagreement is a spec/approach signal, NOT a capability signal — it never triggers the escalation ladder by itself.
- `/vs --cost <prompt>` — opt in to token-spend logging for this run only. Off by default. Subagent tokens auto-captured per dispatch; chair (Planner/Evaluator) tokens summed from the session's own transcript JSONL; `/budget` gives the month-to-date view without this flag.
- `/vs --max-iter N <prompt>` — cap the Spec Critic loop at N iterations. Distinct from `--max` (which is the cycle ceiling); `--max-iter` controls only the Spec Critic loop. If the cap fires before convergence, Planner escalates to the user — does not silently auto-pass.
- `/vs --plain <prompt>` (default ON) — output mode. Spec Critic critiques, Tester summaries, and Evaluator verdicts written in clear concise English with minimal under-the-hood terminology. Reviewable by readers who don't already have the harness vocabulary loaded. Inverse: `--techy`.
- `/vs --techy <prompt>` — opt out of `--plain`. Spec Critic / Tester / Evaluator output uses terse technical shorthand assuming full context (e.g. "AC8 fails: lit-substring `2-5k tokens` absent from §SC body" rather than "the Semantic check section doesn't mention the expected token cost in the form the spec required").
- `/vs --verbosity N <prompt>` — global verbosity knob, integer 0-9. Default 5. Applied to ALL THREE outputs (Spec Critic critique, Tester summary, Evaluator verdict) unless an output-specific override is passed. Levels:
  - **0**: one-line pass/fail per output (Spec Critic: `pass` or `revise: N concerns`; Tester: `total: N passed: P failed: F`; Evaluator: `pass` or `fail`).
  - **3**: bullet-list of concerns / failures with brief rationale per item; no rationale for passes.
  - **5** (default): full per-AC assessment with one-sentence rationale per assertion; concerns enumerated in numbered list.
  - **7**: as 5, plus mid-section interpretive commentary explaining why each concern matters and what fixing it would change.
  - **9**: full verbose — every AC enumerated even on pass, edge-cases discussed, alternative interpretations surfaced, references to spec line numbers, "why this AC exists" rationale for the report's reader.
  - **1, 2, 4, 6, 8**: linearly interpolated between adjacent named levels. Producers should treat the named levels as anchors and fill intermediate levels with proportional content density.
- `/vs --vN-spec N <prompt>` — Spec Critic-only verbosity override. Same 0-9 scale.
- `/vs --vN-test N <prompt>` — Tester-only verbosity override.
- `/vs --vN-eval N <prompt>` — Evaluator-only verbosity override.

The `--plain` / `--techy` and `--verbosity` flags are independent dimensions: `--plain --verbosity 9` is verbose plain English; `--techy --verbosity 0` is one-line technical pass/fail. The cross-product is always meaningful.

Per-output overrides win over global `--verbosity` when both are passed: `--verbosity 3 --vN-spec 9` means Spec Critic at v9, Tester+Evaluator at v3.

These flags propagate from Planner into the subagent briefs at dispatch time. Each subagent honours both `--plain`/`--techy` and the resolved verbosity in its writing of `.vs/cycle-N/*.md` artifacts.

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
  - **`--panel` runs:** `cycle-N/panel/reviewer-<k>.md` (one per panellist, k = 1..N) + `cycle-N/panel/summary.md` (chair's aggregation: verdict tally, correlation classification, adjudication one-liners). Gitignored with the rest of `cycle-N/`.
  - `cycle-N/cost.json` — token-spend log. JSON array, one record per subagent dispatch, schema:
    ```json
    {"role": "spec_critic|generator|tester|reviewer|panel_reviewer", "model": "haiku|sonnet|opus|fable",
     "iteration": 1, "total_tokens": 0, "tool_uses": 0, "duration_ms": 0,
     "timestamp": "<ISO8601>"}
    ```
- `.vs/cost-summary.json` — per-task rollup, written by Evaluator on Step-7 pass. Aggregates across all cycles. Schema: `{"task_id", "cycles", "subagent_calls", "total_tokens", "by_role": {"spec_critic": N, "generator": N, ...}, "by_model": {"sonnet": N, "haiku": N, "opus": N}, "wall_time_ms"}`. **Committed.**
- `.vs/archive/<task-id>/` — preserved state from prior tasks. See § Multi-task state convention. **`spec.md` is committed; `critiques/` subdirs are committed (renamed out of the `cycle-*/` gitignore pattern).**

## Multi-task state convention

`.vs/`'s files split into two groups:

- **Per-task** (overwritten on new task → must be archived):
  - `.vs/spec.md` — current task's sprint contract
  - `.vs/cycle-N/` directories — current task's per-cycle artifacts (gitignored)
- **Repo-wide accumulating** (stay in `.vs/` across tasks → must NOT be archived):
  - `.vs/tasks.json` — running list of all tasks ever run
  - `.vs/progress.md` — append-only log across all tasks
  - `.vs/cost-summary.json` — rollup of the most recent completed task (overwritten on each Step-7 pass, NOT on task start)

When a `/vs` task is parked mid-flight (Spec Critic passed but user hasn't approved, or cycles ran but the task abandoned without a clean Step-7 verdict), and a NEW `/vs` task needs to start, Planner archives the parked task's per-task state before writing fresh state.

Archive procedure (when new task is starting and `.vs/spec.md` belongs to a different parked task):

1. Read `.vs/tasks.json` to discover the parked task's `id` (e.g. `task_014`). Cross-check by reading `.vs/spec.md`'s heading to confirm.
2. Create `.vs/archive/<task-id>/critiques/` (the inner dir avoids the `.vs/cycle-*/` gitignore pattern matching).
3. `git mv .vs/spec.md .vs/archive/<task-id>/spec.md`.
4. For each existing `.vs/cycle-N/` directory: `mv .vs/cycle-N/* .vs/archive/<task-id>/critiques/cycle-N-files/` (after `mkdir -p` of that subdir). Then `rmdir .vs/cycle-N`. The rename out of `cycle-*/` un-ignores the files so they commit as part of the audit. The `.vs/cycle-*/` gitignore rule still applies to the new task's workspace cycle-N/.
5. Commit with `vs: archive <task-id> state (parked at <stage>)`. Local only — same no-autonomous-push policy as the rest of `/vss`/`/vsss`.
6. Now write fresh `.vs/spec.md` for the new task; `tasks.json` and `progress.md` get appended-to (not overwritten) per their normal usage.

Resuming an archived task:

1. `git mv .vs/archive/<task-id>/spec.md .vs/spec.md` (and ensure no current task's spec is sitting there — archive that one first if so).
2. For each cycle-N preserved: `mkdir -p .vs/cycle-N` and `mv .vs/archive/<task-id>/critiques/cycle-N-files/* .vs/cycle-N/`.
3. Remove the now-empty `.vs/archive/<task-id>/` tree (`rmdir` chain).
4. Commit with `vs: resume <task-id> from archive`.

Note: this is a structural-state convention, not a methodology change. Spec Critic, Generator, Tester, Reviewer, Evaluator all behave identically. The convention only affects how Planner manages multi-task state at task boundaries.

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
- **Model plan** — starting tier + escalation ceiling per role, with a one-line difficulty rationale, and an explicit `Fable rung: pre-authorised / not pre-authorised` line (see § Model economy). Honor `--gen` / `--fable-gen` / `--fable-subagents` if passed — the last records `Fable rung: pre-authorised (--fable-subagents)` and permits (never forces) a Fable Generator start when the difficulty estimate demands it.

Honor `--fable-subagents` at spec-writing time: record `Fable rung: pre-authorised (--fable-subagents)` in the Model plan, and start the Generator at Fable only when the difficulty estimate genuinely demands it.

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

Planner reads critique and applies these stopping rules in priority order:

**Convergence** (good case): iterate until Spec Critic returns `pass`. There is no hardcoded cap — the loop runs as many iterations as the spec needs to reach `pass`.

**Plateau detection**: if iter-N's BLOCKING-concern set is substantively identical to iter-(N-1)'s, the Spec Critic plateaued at iter-N and looping again will not help. Stop the loop and surface three options to the user:
- (a) accept residuals — proceed to Generator with the spec as-is
- (b) restart with a revised brief — user rewrites the spec direction; cycle resets to iter-1
- (c) drop the task — stop here, mark abandoned in TODO.md

Do NOT auto-pass on a plateau. Escalate.

**Divergence detection**: if the Spec Critic divergent pattern emerges — concern count growing across three consecutive iterations — the brief is structurally wrong. Stop and tell the user. Suggest rewriting the spec from scratch. Do NOT auto-pass.

**`--max-iter N` cap**: if the cap fires before convergence, do NOT silently auto-pass. Escalate to the user using the same plateau-style options above (a/b/c).

On `pass` (by any rule path): append task to `TODO.md` Open, show final spec + `spec critic: pass after N iteration(s)` note to user. Wait for approval. In fuzzy mode the user note also includes `mode: --fuzzy`.

## Step 4 — Generate (Generator subagent — tier per Model plan)

Spawn `Agent(subagent_type: "general-purpose", model: "<Model plan tier>")` — `"sonnet"` unless the Model plan or the escalation ladder says otherwise; `"fable"` only when that rung is user-authorised:

- Read `.vs/spec.md`. Source of truth.
- Follow `superpowers:test-driven-development` when implementing against testable ACs — scratch red/green tests under `.vs/cycle-<N>/scratch-tests/` (gitignored with the rest of cycle-N; the spec's test directory stays Tester-only and immutable). Use `superpowers:systematic-debugging` on any bug-shaped AC before proposing a fix.
- Implement to satisfy every acceptance criterion.
- Rigorous mode: **do not touch files under the test directory named in spec.md.** Fuzzy mode: this rule doesn't apply (no test dir).
- Do not guess what Tester / Reviewer will do. Build to the spec.
- When done: write `.vs/cycle-<N>/generator-report.md`, update `.vs/tasks.json` (`implementation_status: complete`), produce `.vs/cycle-<N>/diff.patch` via `git diff > .vs/cycle-<N>/diff.patch`.
- Internal retry budget: 3 attempts if blocked. Report the block in the report file.

## Step 5 — Verify (branches by mode)

### Step 5a — Test (Haiku 4.5 Tester) — RIGOROUS MODE ONLY

Spawn `Agent(subagent_type: "general-purpose", model: "haiku", ...)` (or `"sonnet"` if the ladder escalated the Tester — see § Model economy). Tester work is largely mechanical — Sonnet reserved for Generator, the session model for Planner/Evaluator, Haiku for this. The Tester's brief includes `superpowers:verification-before-completion` discipline: no pass/fail claims without the fresh command output that backs them landing in `test-output.log`.

Independence rule: Tester sees only `.vs/spec.md`, the test-dir layout, and the current source tree — NOT Generator's diff or report.

Tester's brief:
- For each acceptance criterion, write a test in the spec's test location that verifies it. Use repo conventions.
- Run the tests. Write full output to `.vs/cycle-<N>/test-output.log` and a 3-line summary (total/passed/failed/key-failures) to `.vs/cycle-<N>/summary.md`.
- **Mandatory regression check:** also run any pre-existing test suite. Any pre-existing failure caused by Generator's diff is a regression — report under `Regressions:` line.
- Update `.vs/tasks.json` (`test_status: passing|failing`).
- **Once committed, these tests are frozen.** Evaluator enforces immutability on subsequent cycles.

### Step 5b — Review (Sonnet Reviewer) — FUZZY MODE ONLY

**Skip this step entirely when `--panel` is set** — the panel (Step 5c) REPLACES the singular Reviewer in fuzzy mode; never run both.

Spawn `Agent(subagent_type: "code-reviewer", model: "sonnet")`. Reviewer needs judgment, not mechanical execution — Sonnet tier. The `code-reviewer` agent type is deliberate: its toolset is read-only (Bash/Read/Grep, no Edit/Write), so reviewer independence is structural, not just instructed.

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

### Step 5c — Panel review (`--panel [N]`, optional amplifier)

Ported 2026-07-10 from the agent-review-panel pattern (blind verdicts + correlated-agreement detection) per `.vs/audits/harness-landscape-2026-07.md`; re-tiered for vibe's model economy (Sonnet panellists, never all-Opus) and re-sized (upstream runs 4–6 panellists; default 3 here — odd for tie-avoidance, and the marginal independence value of panellists 4+ rarely justifies the extra Sonnet spend at vibe's scale).

Sequencing: in fuzzy mode the panel occupies 5b's slot (5b itself is skipped). In rigorous mode the panel dispatches in the same batch position — after the Generator, alongside or immediately after the Tester (5a); the Evaluator reads both. Verdict interaction in rigorous mode: a red test suite fails the cycle regardless of panel opinion (mechanical gate governs); a green suite + panel dissent goes to chair adjudication per the check below — the panel can sink a green cycle, it can never rescue a red one.

N validation (parse-time, before any dispatch): N must be an odd integer between 3 and 7. Even N → round UP to the next odd and say so in the announce. N < 3 → use 3. N > 7 → clamp to 7 (note it). Non-numeric → refuse the flag with a one-line usage note.

Dispatch N `Agent(subagent_type: "code-reviewer", model: "sonnet")` panellists — ALL IN ONE MESSAGE, a single parallel batch. Blindness is structural, three layers deep: the `code-reviewer` toolset is read-only (no Edit/Write escape hatch); the briefs are identical apart from the one substituted output-path token (no seeded differentiation — genuine disagreement must come from the model, not the prompt); and the batch is concurrent, so no panellist's verdict exists for another to read during its run. Each brief additionally instructs: do not read any file under `.vs/cycle-<N>/panel/`.

Each panellist gets exactly what the 5b Reviewer gets — `.vs/spec.md`, the original user prompt (pasted by Planner), `.vs/cycle-<N>/diff.patch` — and NOT the Generator's report, NOT the Tester's output, NOT any other verdict. Each writes `.vs/cycle-<N>/panel/reviewer-<k>.md` (k = 1..N) with the same three sections as 5b (per-criterion assessment / concerns / verdict `pass`|`revise`|`fail`), honouring the run's `--plain`/`--techy` and resolved verbosity. Panellists do NOT touch `tasks.json` — with N concurrent writers that's a race; the chair updates it once after adjudication (Step 6).

### Correlated-agreement (sycophancy) check — Evaluator-side, mandatory under `--panel`

After reading all N verdicts, and BEFORE forming the final judgment, compare them pairwise on three axes: verdict tally, concern sets (same defects found?), and rationale texture (same arguments in the same order, near-identical phrasing?).

- **Correlated consensus** (all N agree AND concern sets + rationale texture are near-duplicates): treat the panel as ONE reviewer's worth of signal, not N× confidence — unanimous-and-identical usually means the diff's surface steered every panellist down the same path, exactly the failure mode the panel exists to catch. Log `panel: correlated consensus — low-information` in `.vs/progress.md`. For a high-blast-radius diff (security-adjacent files, launcher process control, anything in `CLAUDE.md § Invariants` territory) the chair MAY dispatch ONE additional Opus panellist as a depth probe before deciding; otherwise proceed but weight the panel accordingly.
- **Independent consensus** (all N agree but arrive by visibly different routes — different concern emphases, different evidence): the strong case. N× confidence is earned; say so in the verdict block.
- **Split verdicts**: the panel's real product. Every named disagreement dimension gets explicit chair adjudication in the `.vs/progress.md` verdict block — quote the dissent, refute it or accept it in writing. No averaging, no majority-rules shortcut: a majority `pass` with an unrefuted BLOCKING dissent from any single panellist is NOT a pass (default-fail discipline extends to dissent). Deadlock is impossible by construction — the chair adjudicates and owns the call.

The chair then writes `.vs/cycle-<N>/panel/summary.md` (verdict tally, correlation classification, adjudication one-liners) and updates `tasks.json` `test_status` from the ADJUDICATED outcome (rigorous runs: the mechanical gate must ALSO be green).

## Step 6 — Evaluate (Evaluator = you, Opus)

Read in this order, stopping as early as a clear verdict emerges:

1. `.vs/cycle-<N>/summary.md` — quick pulse. Check for `Regressions:` line (rigorous) or verdict line (fuzzy).
2. Rigorous: `.vs/cycle-<N>/test-output.log` — ALWAYS read this before a pass verdict, not only on failures. Never trust the Tester's summary claim; verify the raw runner output actually shows the passes (structural version of "producer's word is not evidence").
   Fuzzy: `.vs/cycle-<N>/reviewer-verdict.md` — read the per-criterion assessment and concerns.
   Under `--panel` (either mode): EVERY `.vs/cycle-<N>/panel/reviewer-<k>.md`, all N of them — then run the correlated-agreement check (§ Step 5c) and write `panel/summary.md` before moving on. Reading a subset, or skipping the correlation pass, silently defeats the panel; the check is mandatory, not optional reading.
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

- **Pass:** append verdict block to `.vs/progress.md` (including the Generator tier that passed). Update `TODO.md` / `CHANGELOG.md` per convention. Commit with `/vs cycle <N>: pass` (or `/vs --fuzzy cycle <N>: pass`). Report to user: cycle number, key changes, how each criterion was verified (or in fuzzy mode, Reviewer's rationale highlights), and the final tier if the ladder escalated.
- **Fail, cycles remaining:** first classify the failure cause — `capability | spec | test | scope`. Then apply § Model economy's ladder: `capability` twice in a row at the same tier → escalate the Generator one rung (asking the user first if the next rung is credit-billed and not pre-authorised); `spec` → spec revision path (restart cycle 1 by rule); `test` → Tester quality escalation or test regeneration; `scope` → re-brief, same tier. Append the classification + any escalation to `.vs/progress.md`. Re-dispatch Generator as a *fresh* subagent at the resolved tier. Hand it: the spec, the failure list, and either the test-output.log (rigorous) or the reviewer-verdict.md (fuzzy). Do **not** hand rigorous-mode Tester's test code to Generator. Increment cycle counter, continue from Step 4.
- **Fail, ceiling hit:** compare summaries across cycles. Failure count trending down? New failures appearing? Report trajectory to user; ask whether to continue, abandon, or switch strategy.
- **Plateau detection:** if three consecutive cycles show the same failure / concern set, flag proactively before the ceiling. Plateaus usually mean spec or approach is wrong, not effort.

## Token-spend logging (opt-in via `--cost` only)

**Default: OFF.** Without `--cost`, no `cost.json` is written, no `cost-summary.json` is computed, no cost line appears in the pass verdict — `/vs` runs identically to today's behavior with no observability overhead.

**Why opt-in:** observability overhead. Subagent dispatches (Spec Critic, Generator, Tester, Reviewer) each return a `<usage>` block with `total_tokens`, `tool_uses`, `duration_ms` — captured mechanically. The chair's own tokens ARE now readable (superseding the 2026-04-23 "not trackable" finding): every session appends `message.usage` blocks to its own transcript at `~/.claude/projects/<slug>/<session-uuid>.jsonl`, so Planner/Evaluator usage is summed by parsing that file — the same mechanism `/budget` uses. Run `/budget` for the month-to-date rollup regardless of `--cost`.

### When `--cost` IS passed

At cycle 1 start, before launching Spec Critic, Planner prints to the user:

```
cost logging enabled for this /vs run.
  • Subagent tokens (per tier) — auto-captured per dispatch.
  • Chair tokens (Planner + Evaluator) — summed from this session's own
    transcript JSONL at rollup time (also visible any time via /budget).
  • Credit-billed tokens (fable) — priced at $10/$50 per MTok in the report.
```

Then for every `Agent(...)` call, parse the `<usage>` block and append to `/workspace/.vs/cycle-<N>/cost.json`. Schema:
```json
{"role": "spec_critic|generator|tester|reviewer|panel_reviewer", "model": "haiku|sonnet|opus|fable",
 "iteration": 1, "total_tokens": 0, "tool_uses": 0, "duration_ms": 0,
 "timestamp": "<ISO8601>"}
```
If the file doesn't exist, create it with an empty array first. If a result lacks a parseable `<usage>` block, log `total_tokens: null` + a `note` field; don't fail the cycle.

At rollup time, Evaluator sums the chair's own tokens by parsing the current session's transcript (`~/.claude/projects/<slug>/<session-uuid>.jsonl` — most-recently-modified file; sum `message.usage` input+output over the task's wall-clock span) and records the result in `cost.json` with `role: "director_evaluator"`, `model: "<session model>"`, `note: "transcript-summed"`.

On Step-7 pass, Evaluator computes `/workspace/.vs/cost-summary.json` by reading every `cycle-N/cost.json` for this task. Schema:
```json
{
  "task_id": "...",
  "cycles": <N>,
  "subagent_calls": <count>,
  "subagent_tokens_haiku": <int>,
  "subagent_tokens_sonnet": <int>,
  "subagent_tokens_opus": <int>,
  "subagent_tokens_fable": <int>,
  "subagent_tokens_total": <int>,
  "chair_tokens": <int or null>,
  "chair_model": "<session model>",
  "chair_tokens_source": "transcript-summed" | "unknown",
  "est_credits_usd": <float or 0>,
  "wall_time_ms": <int>
}
```
Commit alongside the pass commit. The pass-verdict report to the user includes:
```
cost: <N> cycles, <M> subagent calls, wall <Ts>
  Haiku  (subagent): <H> tokens
  Sonnet (subagent): <S> tokens
  Opus   (subagent): <O> tokens          (only if the ladder escalated)
  Fable  (subagent): <F> tokens ≈ $<X>   (only if the Fable rung ran — credits)
  Chair  (planner + evaluator, <model>): <C> tokens
```
Tiers stay on separate lines because their real per-token costs differ; aggregating hides that. Fable is the only line that is money rather than quota — always show its $ estimate.

No dollar estimates — Pro/Max is flat-rate; tokens are a rate-limit-pressure proxy, not money. If a future Anthropic billing model makes per-token cost meaningful for subscribers, revisit.

### When `--cost` is NOT passed

Skip everything in this section. No file writes under `.vs/cycle-N/cost.json` or `.vs/cost-summary.json`. No cost line in the pass verdict. The token-spend logging is purely opt-in observability.

## Superpowers integration

Superpowers is complementary discipline, not a rival harness — `/vs` supplies the adversarial structure, superpowers supplies per-role craft. Planner folds these into the subagent briefs (subagents invoke them via the Skill tool):

- **Planner (you)**: ambiguous brief → `superpowers:brainstorming` BEFORE Step 2; a spec spanning multiple tasks → shape it with `superpowers:writing-plans`.
- **Generator brief**: `superpowers:test-driven-development` for testable ACs (scratch tests only — never the spec's test dir); `superpowers:systematic-debugging` for bug-shaped ACs.
- **Tester brief**: `superpowers:verification-before-completion` — claims require fresh command output.
- **Evaluator (you)**: `superpowers:verification-before-completion` before any pass verdict; read `diff.patch` with `superpowers:requesting-code-review` heuristics.
- Whole-task worktree isolation when the working tree must stay clean: `superpowers:using-git-worktrees`.

## Rules

- **Ask before credits** — no credit-billed dispatch (Fable 5 from 8 Jul 2026), ever, without user consent: Model-plan pre-authorisation or a fresh ask quoting estimated credits. Inherited by `/vss` / `/vsss` as a hard-escalate item.
- **Immutable tests (rigorous only)** — once Tester lands tests, nobody edits or removes them. If acceptance criteria change, Planner writes a revised spec and restarts cycle 1. Does not apply in fuzzy mode (no tests).
- **Status-field mutations only** on `tasks.json`. No unstructured edits.
- **Fresh subagents per cycle** — context reset over compaction. Continuity via `.vs/` files only.
- **No cross-subagent context sharing** — Generator never sees Tester's / Reviewer's output; Tester / Reviewer never sees Generator's report. Spec Critic sees only the spec.
- **No cross-panellist context sharing (`--panel`)** — panellists never read each other's verdicts or `.vs/cycle-<N>/panel/` at all; blindness is structural (read-only agent type, byte-identical briefs, one concurrent batch). A panellist brief that individuates panellists ("you are the security reviewer") breaks the mechanism — differentiation must emerge, not be assigned.
- **Per-cycle commits** after pass or at escalation points.
- **Regression gate (rigorous only)** — Tester runs pre-existing test suite; failure caused by Generator's diff is automatic cycle fail. Fuzzy mode cannot enforce this automatically — Reviewer is asked to flag suspected regressions in the diff, but Evaluator should run pre-existing tests manually before declaring pass if there is a test suite at all.

## When to refuse or stop

- Simplicity gate (Step 1) — trivial or user-decisions-mid-flow.
- User declines both Step-1 options (tighten brief or `--fuzzy`) — stop, don't guess.
- Plateau across three consecutive cycles — surface to user before ceiling.

---

Read the user's prompt below this line. Start at Step 1.
