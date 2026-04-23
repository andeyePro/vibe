# TODO

Project backlog and audit log. See `CLAUDE.md` § TODO.md for usage.

Markers: `[ ]` open · `[x]` done · `[!]` failed/abandoned (note what was tried)

## Open

_nothing yet_

## Done

- [x] Implement `/vs` — adversarial agentic harness slash command. Shipped as `devcontainer/commands/vs.md`. Planner → Generator → Tester → Evaluator, independent Sonnet subagents, immutable tests, file-based state under `.vs/`, soft cycle ceiling proposed by Planner (user-overridable with `--max N`). Nomenclature and patterns follow Anthropic's harness-design articles.
