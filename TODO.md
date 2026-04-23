# TODO

Project backlog and audit log. See `CLAUDE.md` § TODO.md for usage.

Markers: `[ ]` open · `[x]` done · `[!]` failed/abandoned (note what was tried)

## Open

_nothing yet_

## Done

- [x] **/vs v2: spec critic + Haiku Tester + regression gate** — inserted Sonnet Spec Critic between Planner and Generator (catches fuzzy criteria, scope loopholes, type/schema gaps before any code runs); switched Tester to Haiku 4.5 (mechanical work, cheaper); made regression check on pre-existing test suite mandatory (was discretionary). All in `devcontainer/commands/vs.md`; synced to `~/.claude/commands/vs.md`. Steps renumbered 1–7.
- [x] task_001 — `--json` output for `code-check.py`. Single `argparse` flag; emits one JSON object on stdout (`tool`, `shellcheck_version`, `files_checked`, `findings`, `summary`); exit codes preserved (0 clean, 1 issues, 2 missing-shellcheck → JSON error object); default human output byte-identical. Verified via `/vs` cycle 1: 44/44 new smoke tests + 12/12 pre-existing pass. Spec/log under `.vs/`.
- [x] Implement `/vs` — adversarial agentic harness slash command. Shipped as `devcontainer/commands/vs.md`. Planner → Generator → Tester → Evaluator, independent Sonnet subagents, immutable tests, file-based state under `.vs/`, soft cycle ceiling proposed by Planner (user-overridable with `--max N`). Nomenclature and patterns follow Anthropic's harness-design articles.
