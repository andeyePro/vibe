# Spec — task_039: `/review` — Claude code review on the working diff, with empty opt-in fan-out slots

## Task summary
Martin's queue item 6 (2026-09-04): one command that reviews the current diff with Claude's own `/code-review` and, later, outside reviewers, merging the verdicts; fan-out is the default; stackable so a run can be Claude-only. Only the Claude leg is decision-free today: the Gemini leg waits on Martin's Google AI Studio key (fromClaude question 2) and a firewall allowlist entry; a Codex leg would need a ChatGPT subscription he does not have. So this task ships `devcontainer/commands/review.md` as a prompt-instruction command (same shape as diet/wide) that: runs the built-in `code-review` skill at `high` on the working diff (or a named target: PR number, branch, path), collects its findings, then runs every ENABLED slot in a slot registry — none are enabled today — and merges everything into one verdict block using the same correlated-agreement discipline as `/vs § Step 5c` (unrefuted BLOCKING dissent is never a pass). `--solo` forces Claude-only; `--level` passes through; `--slot <name>` runs one named slot and refuses with one line when the slot is not enabled. It never posts to GitHub (`--comment`) unless the user passes `--comment` explicitly. Baseline 21504e4.

## Acceptance criteria (literal, case-sensitive substrings unless stated)
- AC1 `devcontainer/commands/review.md` exists, ≤ 850 words (be terse from the first draft), with YAML frontmatter containing a `description:` line that mentions `code-review` and `fan-out`.
- AC2 review.md contains, above the registry, the plain sentence `Today /review is Claude-only: the fan-out has zero enabled slots.`; contains the usage line `/review [--solo] [--level low|medium|high|max] [--slot <name>] [--comment] [<target>]` states the default level is `high` and the default target is the working diff (`the working diff`); states the invocation literally as `Skill(skill: "code-review", args: "<level> [<target>]")`; and says `--level ultra` is refused with one line (`refuses --level ultra`) because ultra is cloud-billed and must be typed by the user.
- AC3 review.md contains a `## Slot registry` section with a table whose rows are `gemini` and `codex`, each with columns `enabled`, `needs`; both rows' `enabled` cell is `no` (Tester checks with the regex `^\|\s*gemini\s*\|\s*no\s*\|` and the same for codex); the `gemini` row's `needs` names `GEMINI_API_KEY` in `~/.vibe/tokens` and `a firewall allowlist entry`; the `codex` row's `needs` names `a ChatGPT subscription`; the section states `A slot is enabled only when every item in its needs column exists; enabling a slot is Martin's step, never this command's.`
- AC4 review.md contains a `## Merge` section with the literals `correlated consensus`, `independent consensus`, `split verdicts`, `an unrefuted BLOCKING dissent from any single reviewer is never a pass`, and a pointer `see `/vs § Step 5c``. The same section pins the output as one block headed `## Review verdict` with exactly three sub-headings `### Findings` (one line per finding: severity, file:line, which reviewers agree), `### Dissent` (unmerged single-reviewer BLOCKING items, or `none`), `### Verdict` (`PASS`, `FAIL`, or `SPLIT` plus one sentence).
- AC5 review.md contains the rule lines `--solo` = Claude only; `--slot <name>` on a slot that is not enabled → `refuse with one line naming what it needs`; `--comment` is the only way findings reach GitHub (`never posts to GitHub unless --comment is passed`); and `With zero enabled slots the default fan-out is identical to --solo.` Also: `--comment is GitHub-outward like push: /vss and /vsss treat it as hard-escalate, never auto-fired.`
- AC6 review.md states the relation to `/vs`: `/vs --panel` unchanged; `/review` works on any diff, not only harness cycles; and the hard-escalate inheritance line `Inherits /vss's safety floor: no push, no hook or firewall edits.`
- AC7 `README.md` line 12's intro sentence (the one naming `/sp`, `/vs`, `/vss`, `/vsss`, `/wide`, `/narrow`) also names `/review`, and README gains a standalone paragraph starting `` `/review` `` in the style of the `/budget` paragraph (Tester: `grep -c '^`/review`'` ≥ 1); `CLAUDE.md` § Project context's shipped-extras line adds `/review`; `MANUAL-TESTS.md` Test 24's expected list adds `review.md`.
- AC8 `TODO.md` queue item 6 becomes a one-line pointer (`Claude leg shipped as /review (task_039); Gemini/Codex slots wait on fromClaude question 2 and a firewall entry`); `CHANGELOG.md` entry in the same commit.
- AC9 `smoke/checks_13_spec_first.py` gains `test_review_command_docs()` (registered in `smoke/runner.py`) asserting AC1–AC8 (AC8: the TODO pointer sentence and a CHANGELOG line containing `/review` and `task_039`); file stays ≤ 1,500 lines; `python3 code-check.py` and `python3 smoke-test.py < /dev/null` exit 0. The installer syncs `review.md` like every other command (no installer change needed — the sorted-glob sync covers it; the Tester asserts the file is under `devcontainer/commands/`).

## Out of scope
- Any API call, key handling, `~/.vibe/tokens` change, firewall or hook edit, GitHub Action, or workflow file.
- Changing `code-review`'s own behaviour or `/vs --panel`.
- Language profiles (queue item 5).

## Test location
`smoke/checks_13_spec_first.py` (Tester-owned: `test_review_command_docs`); Generator writes review.md, README, CLAUDE.md, MANUAL-TESTS, TODO, CHANGELOG — never test bodies.

## Proposed budget
2 cycles.

## Model plan
- Planner + Evaluator: session model. Spec Critic: sonnet. Generator: sonnet, ceiling opus. Tester: haiku. Fable rung: not pre-authorised.
