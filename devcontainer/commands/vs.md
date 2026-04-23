---
description: Adversarial agentic harness — Planner + Evaluator (you, Opus) orchestrate independent Generator and Tester subagents (Sonnet) against an agreed spec. Pass the task prompt after the command.
---

# /vs — adversarial harness

You (top-level, Opus) play two roles across the run: **Planner** (Step 1–2) and **Evaluator** (Step 5–6). Between them, you dispatch two independent Sonnet subagents in sequence: **Generator** (writes the feature) then **Tester** (writes and runs tests). Generator and Tester never see each other's output — both work from the same spec. That separation is the point.

Chronological flow per cycle:

```
Planner → Generator → Tester → Evaluator → (iterate Generator on fail, else accept)
```

## Flags

- `/vs --max N <prompt>` — override the cycle ceiling. Default is whatever Planner proposes.

## State directory: `.vs/`

Created at repo root.

- `.vs/spec.md` — sprint contract. Planner writes, user approves. Read-only for subagents. **Committed.**
- `.vs/tasks.json` — structured task list. Status-field mutations only. Schema:
  ```json
  {
    "id": "task_001",
    "description": "one-line goal",
    "implementation_status": "pending|in_progress|complete",
    "test_status": "pending|in_progress|passing|failing",
    "assigned_to": "generator|tester|evaluator",
    "last_modified": "<ISO8601>"
  }
  ```
- `.vs/progress.md` — append-only human-readable log. Each cycle appends a block. **Committed.**
- `.vs/cycle-N/` — per-cycle artifacts. **Gitignored.** Retained across cycles (not overwritten) so you can compare trajectories.
  - `cycle-N/generator-report.md` — Generator's summary of what it did
  - `cycle-N/diff.patch` — what Generator changed this cycle
  - `cycle-N/test-output.log` — full test output from Tester
  - `cycle-N/summary.md` — Tester's 3-line summary (pass/fail counts, key failures)

## Step 1 — Simplicity gate (Planner)

Before anything else, ask: does this task genuinely need `/vs`? Refuse if any of:

- Task is trivial (single file, single function, mechanical edit). Suggest running inline instead.
- Task can't be expressed with verifiable acceptance criteria (exploratory, aesthetic, "make it nicer"). Say so.
- Task requires user decisions mid-flow that a subagent can't make alone.

On refusal, explain which gate tripped and stop. Do not proceed.

## Step 2 — Plan (Planner)

Detect the repo's test convention by inspecting existing test dirs (`tests/`, `test/`, `__tests__/`, `spec/`). If none exists, propose `tests/` and note it in the spec.

Write `.vs/spec.md` with:

- **Task summary** — one paragraph: what's being built and why.
- **Acceptance criteria** — bulleted, each criterion verifiable (a test can decide pass/fail). Aim for 5–15 but don't cap artificially.
- **Out of scope** — explicit list of things NOT to build. Prevents Generator scope creep; Evaluator flags violations.
- **Test location** — the detected/proposed test directory. Tester will write tests here. **Once Tester commits, tests are immutable — Generator cannot edit them.**
- **Proposed budget** — `N cycles` with a one-line rationale referencing complexity signals (surface area touched, novel integration, test depth needed). If the user passed `--max`, honor that and note it.

Append the task to `TODO.md` under `## Open` with marker `[ ]` and the task id.

Show `.vs/spec.md` to the user and wait for explicit approval ("yes", "go", or edits). Do not proceed without it.

## Step 3 — Generate (Sonnet Generator subagent)

Spawn `Agent(subagent_type: "general-purpose", model: "sonnet")` with this brief:

- Read `.vs/spec.md`. That's your source of truth.
- Implement the feature to satisfy every acceptance criterion.
- **Do not touch files under the test directory named in spec.md.** That is Tester's responsibility; any edit there fails the cycle.
- Do not guess what tests Tester will write. Build to the spec.
- When done: write a short summary to `.vs/cycle-<N>/generator-report.md`, update `.vs/tasks.json` (`implementation_status: complete`), produce `.vs/cycle-<N>/diff.patch` via `git diff > .vs/cycle-<N>/diff.patch`.
- Internal retry budget: 3 attempts if blocked. Report the block in the report file.

## Step 4 — Test (Sonnet Tester subagent)

**Spawn a separate Sonnet subagent.** Independence rule: Tester's prompt must NOT include Generator's diff or report. Tester sees only:

- `.vs/spec.md`
- The existing test-dir layout (for conventions)
- The current source tree after Generator finished (so tests can import real symbols) — but not `.vs/cycle-<N>/generator-report.md` or the diff patch

Tester's brief:

- Read `.vs/spec.md`.
- For each acceptance criterion, write a test under the spec's test location that verifies it against the current implementation. Use the repo's existing test conventions.
- Run the tests. Write full output to `.vs/cycle-<N>/test-output.log` and a 3-line summary (total/passed/failed/key-failures) to `.vs/cycle-<N>/summary.md`.
- Update `.vs/tasks.json` (`test_status: passing|failing`).
- **Once you commit these tests, they are frozen.** Evaluator enforces immutability on subsequent cycles.

## Step 5 — Evaluate (Evaluator = you, Opus)

Read in this order, stopping as early as a clear verdict emerges:

1. `.vs/cycle-<N>/summary.md` — quick pulse.
2. `.vs/cycle-<N>/test-output.log` — only if summary shows failures or you need detail.
3. `.vs/cycle-<N>/diff.patch` — scan for scope creep, dead code, swallowed errors, invariant violations. Check `CLAUDE.md § Invariants`.
4. `.vs/cycle-<N>/generator-report.md` — only after forming your own view (avoids anchoring).

Decide strictly:

- Do all tests pass? (mechanical)
- Does the diff satisfy each acceptance criterion beyond mere test-pass? (judgment)
- Any scope creep against the "out of scope" list?
- Any project invariant violations?
- Did Generator touch the test directory? If yes → **automatic fail.**
- On cycle ≥2: did Tester edit tests from a prior cycle? If yes → **automatic fail** (immutability breach).

Default-fail on ambiguity. Adversarial by design.

## Step 6 — Iterate, accept, or escalate

- **Pass:** append a verdict block to `.vs/progress.md`. Move the `TODO.md` entry to `## Done` with a one-line result note. Commit the change with message `/vs cycle <N>: pass`. Report to the user: cycle number, key changes, how each criterion was verified.
- **Fail, cycles remaining:** append specifics to `.vs/progress.md`. Re-dispatch Generator as a *fresh* Sonnet subagent (new context, no conversation carry-over). Hand it: the spec, the failure list, and the path to `cycle-<N>/test-output.log`. Do **not** hand it Tester's test code. Increment cycle counter, continue from Step 3.
- **Fail, ceiling hit:** compare `summary.md` across cycles. Is the failure count trending down? Are new failures appearing? Report the trajectory to the user and ask: *continue with N more cycles, abandon, or switch strategy?* Do not stop unilaterally — user decides.
- **Plateau detection:** if three consecutive cycles show the same failure set, flag proactively to the user *before* the ceiling. Plateaus usually mean the spec is wrong or the approach is wrong, not the effort.

## Rules

- **Immutable tests** — once Tester lands tests, nobody edits or removes them. If acceptance criteria change, Planner writes a revised spec and the run restarts from cycle 1.
- **Status-field mutations only** on `tasks.json`. No unstructured edits, no schema drift.
- **Fresh subagents per cycle** — context reset over compaction. Director retains continuity via `.vs/` files.
- **No cross-subagent context sharing** — Generator never sees Tester's output; Tester never sees Generator's report.
- **Per-cycle commits** after pass or at escalation points, with `/vs cycle <N>: <verdict>` messages. Gives rollback points.

## When to refuse or stop

- Simplicity gate (Step 1).
- User declines the proposed spec and can't articulate the change — ask for clarification, don't guess.
- Plateau across three consecutive cycles — proactively surface to user before ceiling.

---

Read the user's prompt below this line. Start at Step 1.
