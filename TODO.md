# TODO

Project backlog and audit log. See `CLAUDE.md` § TODO.md for usage.

Markers: `[ ]` open · `[x]` done · `[!]` failed/abandoned (note what was tried)

## Open

_nothing yet_

## Done

- [x] task_001 — `--json` output for `code-check.py`. Single `argparse` flag; emits one JSON object on stdout (`tool`, `shellcheck_version`, `files_checked`, `findings`, `summary`); exit codes preserved (0 clean, 1 issues, 2 missing-shellcheck → JSON error object); default human output byte-identical. Verified via `/vs` cycle 1: 44/44 new smoke tests + 12/12 pre-existing pass. Spec/log under `.vs/`.
- [x] Implement `/vs` — adversarial agentic harness slash command. Shipped as `devcontainer/commands/vs.md`. Planner → Generator → Tester → Evaluator, independent Sonnet subagents, immutable tests, file-based state under `.vs/`, soft cycle ceiling proposed by Planner (user-overridable with `--max N`). Nomenclature and patterns follow Anthropic's harness-design articles.
