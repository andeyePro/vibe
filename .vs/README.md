# `.vs/` — `/vs` adversarial harness state

This directory holds the shared state that the `/vs` slash command
(`devcontainer/commands/vs.md`) uses across cycles.

## Tracked files

These are committed and represent the current shape of the harness's
backlog and history.

- **`spec.md`** — the active task's spec (assumptions, acceptance criteria,
  out-of-scope, test location, proposed budget). Spec Critic iterates on
  this before user approval; Generator and Tester read it as the
  contract. Replaced when a new task starts.
- **`tasks.json`** — append-only ledger of all tasks the Planner has
  drafted. Each entry tracks `id`, `description`,
  `implementation_status`, `test_status`, `assigned_to`, `mode`
  (rigorous / fuzzy), and a `last_modified` timestamp.
  `parked_note` field captures escalations that paused mid-cycle.
- **`progress.md`** — narrative log of `/vs` runs (cycle-by-cycle outcomes,
  blockers, lessons). Optional but recommended for retrospect.
- **`cost-summary.json`** — only present when a task ran with `--cost`;
  rolled up per-task token totals at Step-7 pass.
- **`AUTONOMOUS-MEMO-*.md`** — session-specific deliverables that Martin
  asked the assistant to write up; tracked so they survive `git clean`.

## Untracked / gitignored

- **`cycle-N/`** (e.g. `cycle-1/`, `cycle-2/`) — per-cycle artifacts.
  Spec Critic iterations (`spec-critique-iter*.md`), Generator/Tester
  output, Reviewer verdicts (in `--fuzzy` mode), `cost.json`. These are
  large and ephemeral; the `.gitignore` rule `.vs/cycle-*/` keeps them
  out of git. If you're resuming a parked cycle, the `cycle-N/` dir on
  your local working tree is what matters; you cannot pull it from a
  remote.

## Lifecycle

1. User runs `/vs <prompt>` (or `/vs --fuzzy <prompt>`).
2. Planner drafts spec + appends a task entry to `tasks.json`.
3. Spec Critic loops until convergence / plateau / divergence (see
   vs.md Step 3).
4. User approves; Generator + Tester (or Reviewer in fuzzy mode) run as
   independent Sonnet/Haiku subagents.
5. Evaluator audits the cycle and either passes, requests another
   cycle, or escalates.
6. On pass, the task entry's `implementation_status` and `test_status`
   flip to `complete`; `progress.md` gets a one-line outcome.

## Resumption protocol

If you're picking up parked work (any task entry with
`assigned_to: "parked"`):

1. Read the `parked_note` for the resume options.
2. Look at `cycle-N/spec-critique-iter*.md` for what the Spec Critic
   already flagged.
3. Working-tree changes in `devcontainer/commands/vs.md`,
   `smoke-test.py`, etc. that aren't yet committed represent
   Generator/Tester output from the parked cycle. The TODO entry for
   the parked task says whether to discard or rebuild on top of them.

## Don't commit cycle-N artifacts

If you find yourself about to `git add .vs/cycle-1/` — stop. The
gitignore keeps these local because they balloon repo size, contain
intermediate Sonnet/Haiku output not meant for review, and become noise
once the cycle's verdict is in `tasks.json` + `progress.md`.
