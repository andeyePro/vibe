# task_051 — `$vs`, `$vss`, `$vsss` in Claude Code (plan item 10, branch `astra`)

## Task summary

Command symmetry's Claude-side half (Martin, 2026-09-10: "someone used to vibe on one runtime must be able to use it on the other unchanged"). Claude Code's slash commands are files named by their command; a prompt beginning `$vs` is plain text to it. The deterministic route (a `UserPromptSubmit` hook) is a `settings.local.json` hook edit and therefore Martin-gated (plan D4), so this task ships the instructional route: a CLAUDE.md fragment, synced by `install-claude-extras.sh` like the existing fragments, that tells the lead "a prompt whose first token is `$vs`, `$vss` or `$vsss` means invoke that skill with the rest of the prompt as its arguments — same command, other spelling", plus a one-line "alias form" note in each of the three command files, and the hook-based alternative recorded in TODO for Martin.

## Acceptance criteria

- AC1 `devcontainer/claude-md/dollar-prefix.md` exists, ≤ 25 lines and ≤ 200 words, and states: the three exact tokens; that the match is the FIRST whitespace-delimited token of the prompt, case-sensitive, exact (`$vss:foo`, `$vssx`, `$VS` are not aliases); that the rest of the prompt is passed verbatim as the skill's arguments (`$vsss --hours 2 fix the build` ≡ `/vsss --hours 2 fix the build`); that flags and the hard-escalate list are unchanged; and that Codex's own terminal uses the `$` form natively while `/vs` there is not a vibe-owned file (one sentence, pointing at the plan's D3).
- AC2 `devcontainer/install-claude-extras.sh` syncs the new fragment exactly like the existing `claude-md/*.md` fragments (no special-casing; the test asserts the fragment appears in the synced target the way `web-research.md` does in the existing sync fixture — grep the existing fragment test in `smoke/` and extend it).
- AC3 `devcontainer/commands/vs.md`, `vss.md`, `vsss.md` each gain ONE line, immediately under the H1, of the form `Alias: \`$vs …\` is the same command (see \`claude-md/dollar-prefix.md\`).` with the command's own name; nothing else in the bodies changes (the test asserts the line and that the file's line count grew by exactly one against `git show HEAD:<file>` — HEAD, not a pinned sha).
- AC4 `README.md`'s Codex section gains one sentence on the `$` spelling in Claude Code; `docs/codex-integration-plan.md` § 3 marks item 10 delivered; `TODO.md` gains one `[ ]` line, Martin-gated, for the deterministic `UserPromptSubmit` hook alternative (a `settings.local.json` edit) with the exact hook shape it would take.
- AC5 Tests: `smoke/checks_09_openproject_and_scanner.py` pins the fragment set (`len(all_md_files) == 14` plus an exact name set) and a 6,700-word total budget — the Tester updates both pins in that file (15 fragments, the new name added; the total-words cap raised by exactly the new fragment's word count if the current total plus the fragment exceeds it, with a comment naming task_051, mirroring how task_042 handled the same squeeze) and adds the new assertions to `smoke/checks_13_spec_first.py` (≤ 1,500 lines): fragment presence, line and word size, the pinned phrases (`$vs`, `$vss`, `$vsss`, "first", "case-sensitive", `$vss:foo`); the sync assertion (AC2) extends the existing fixture-isolated sync test in `checks_03` (grep `web-research`); the three alias lines (AC3) with the exact-one-line-growth check; README sentence; TODO line.
- AC6 `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null` fully green.

## Out of scope

- Any hook or settings edit; changing what `/vs`, `/vss`, `/vsss` do; the Codex side (task_047 shipped it); `$ask`, `$review` or any other `$` alias.

## Test location

The smoke part that already asserts fragment sync and command-file docs (`smoke/checks_13_spec_first.py`; ≤ 1,500 lines).

## Proposed budget

1 cycle.

## Model plan

- Spec Critic: sonnet. Generator: sonnet. Tester: haiku. Evaluator: session model (Fable 5.1 chair).
