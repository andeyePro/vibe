# TODO

Project backlog and audit log. See `CLAUDE.md` § TODO.md for usage.

Markers: `[ ]` open · `[x]` done · `[!]` failed/abandoned (note what was tried)

## Open

- [ ] **/vs: token-spend logging** — wrap each subagent dispatch with usage capture; append per-cycle cost to `.vs/cycle-N/cost.json` (input/output tokens, model, wall-time); roll up to `.vs/cost-summary.json` on task completion. Show user `task_NNN: X cycles, $Y est, Z tokens` at pass verdict. Needs decision on cost model (Pro/Max is flat-rate, but rate-limit pressure ≈ token spend).
- [ ] **vibe: cross-repo + cross-org learning library** — two-tier persistence under `~/.vibe/learnings/`: (a) per-org subdirs `<org>/` mounted into the container only when current repo's `git remote get-url origin` matches that org (prevents cross-org leak); (b) anonymized pattern library at `_patterns/` mounted into every container, holds spec-writing heuristics and test-design gotchas with no project-specific content. Org detection via remote-URL regex; needs schema for what counts as "anonymized."
- [ ] **vibe: container cold-start latency** — persistent per-repo container model: first `vibe` in a repo creates; second `vibe` reattaches if running. Add `vibe --fresh` to force rebuild and `VIBE_IDLE_TIMEOUT` env to auto-stop after N hours idle. Trade-off: stale state across long gaps; document this clearly.
- [ ] **vibe: cloud/async runner (gated, opt-in)** — verified 2026-04-23: Claude Agent SDK bills at API pay-as-you-go rates; subscription credentials cannot be used (hard auth boundary, key-only). No native cloud mode for Claude Code itself. Managed Agents product status unconfirmed in current docs. Implementation: build `vibe --cloud <task>` requiring explicit `ANTHROPIC_API_KEY` env var **and** an opt-in flag (e.g. `VIBE_CLOUD_OPT_IN=1`); refuse to run without both; show estimated spend cap warning before each invocation. Do NOT route through subscription auth — that path doesn't exist and would silently bill nothing/fail. Reference: github.com/anthropics/claude-agent-sdk-python/issues/559.
- [ ] **/vs: stretch — soft mode for fuzzy tasks** — `/vs --soft <prompt>` skips Tester, instead spawns an independent Reviewer (Sonnet) that critiques Generator's diff against the original prompt and produces a verdict. Useful for "fix this bug", "make this nicer", "look around for X" — tasks that fail the Step-1 simplicity gate today because they have no verifiable acceptance criteria. Half-harness for half-spec-able work.

## Done

- [x] **/vs v2: spec critic + Haiku Tester + regression gate** — inserted Sonnet Spec Critic between Planner and Generator (catches fuzzy criteria, scope loopholes, type/schema gaps before any code runs); switched Tester to Haiku 4.5 (mechanical work, cheaper); made regression check on pre-existing test suite mandatory (was discretionary). All in `devcontainer/commands/vs.md`; synced to `~/.claude/commands/vs.md`. Steps renumbered 1–7.
- [x] task_001 — `--json` output for `code-check.py`. Single `argparse` flag; emits one JSON object on stdout (`tool`, `shellcheck_version`, `files_checked`, `findings`, `summary`); exit codes preserved (0 clean, 1 issues, 2 missing-shellcheck → JSON error object); default human output byte-identical. Verified via `/vs` cycle 1: 44/44 new smoke tests + 12/12 pre-existing pass. Spec/log under `.vs/`.
- [x] Implement `/vs` — adversarial agentic harness slash command. Shipped as `devcontainer/commands/vs.md`. Planner → Generator → Tester → Evaluator, independent Sonnet subagents, immutable tests, file-based state under `.vs/`, soft cycle ceiling proposed by Planner (user-overridable with `--max N`). Nomenclature and patterns follow Anthropic's harness-design articles.
