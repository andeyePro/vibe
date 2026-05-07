# Audit — `/vs` role decomposition vs Claude Code canonical Architect/Writer/Reviewer

**Date**: 2026-05-07
**Triggered by**: TODO.md entry "/vs: audit against Claude Code internal tip 'use /agents to optimize specific tasks (Software Architect, Code Writer, Code Reviewer)'"
**Author**: Opus (acting as /vsss iter 7 executor)
**Output**: recommendation, no code change

## Question

Should `/vs`'s role decomposition (Planner / Spec Critic / Generator / Tester / Evaluator) be re-cast against, aliased to, or replaced by Claude Code's canonical three-agent shape (Software Architect / Code Writer / Code Reviewer)?

## What Claude Code's tip recommends

Claude Code's welcome banner surfaces a tip suggesting users invoke `/agents` to create specialised agents along the lines of:

- **Software Architect** — designs, picks patterns, decomposes work
- **Code Writer** — implements per a plan or spec
- **Code Reviewer** — reviews diffs for correctness, style, and concerns

This is a three-role recommendation, not a hard standard. The names are conventional in software engineering literature (architect / engineer / reviewer) and recur in numerous agentic-coding articles.

## What `/vs` actually does

`/vs` ships five top-level roles plus mode-conditional swaps:

| `/vs` role     | Model     | Job                                                                  |
| -------------- | --------- | -------------------------------------------------------------------- |
| Planner        | Opus      | Simplicity gate, draft spec, revise spec after Spec Critic           |
| Spec Critic    | Sonnet    | Audit spec for fuzziness, scope loopholes, schema gaps BEFORE coding |
| Generator      | Sonnet    | Implement to satisfy every AC                                        |
| Tester         | Haiku 4.5 | Write immutable tests; rigorous mode only                            |
| Reviewer       | Sonnet    | Written-verdict review of diff; `--fuzzy` mode only (replaces Tester)|
| Evaluator      | Opus      | Read tests/diff/report; pass/fail decision                           |

Planner and Evaluator are the same Opus session (top-level director). Spec Critic / Generator / Tester / Reviewer are dispatched as fresh subagents per cycle. Independence rule: Generator never sees Tester's tests; Tester never sees Generator's report; Spec Critic sees only the spec.

## Mapping the canonical roles onto `/vs`

| Canonical role     | `/vs` equivalent                                                                  |
| ------------------ | --------------------------------------------------------------------------------- |
| Software Architect | Planner (drafts spec, makes architectural decisions) + Spec Critic (adversarial spec review BEFORE coding) |
| Code Writer        | Generator                                                                         |
| Code Reviewer      | Evaluator (rigorous mode) OR Reviewer (fuzzy mode)                                |
| (no canonical)     | Tester (writes immutable tests; closer to a QA role than a code-review role)      |

`/vs` decomposes the canonical Architect role into TWO subroles (Planner + Spec Critic) for adversarial separation — the planner who drafts the spec is NOT the same agent who critiques it. This is a deliberate design choice motivated by the same rationale as Generator/Tester independence: a single agent reviewing its own draft is much weaker than two agents whose only shared input is the spec text.

`/vs` also adds Tester as a distinct role from Reviewer/Evaluator because mechanical test-writing (Haiku-tier) is genuinely different work from judgment-based review (Sonnet/Opus tier). The canonical three-role pattern collapses these into Code Reviewer; `/vs` doesn't.

## Findings

### `/vs`'s decomposition is NOT a regression on the canonical three-role pattern

`/vs` strictly extends it:

1. The canonical Architect → `/vs` Planner + Spec Critic. The split adds adversarial separation BEFORE any code is written. Caught 4 BLOCKING + 9 MEDIUM/LOW concerns in task_010 cycle 1's Spec Critic iter 1 alone — concerns that would have cost a Generator-Tester round-trip if Spec Critic didn't exist.

2. The canonical Code Writer → `/vs` Generator. 1:1.

3. The canonical Code Reviewer → `/vs` Tester (rigorous, mechanical) OR Reviewer (fuzzy, judgment) + Evaluator (always, top-level). The split between mechanical-Haiku and judgment-Sonnet/Opus is real efficiency: Haiku for the rote test-writing, Sonnet/Opus for the call-it pass-or-fail decision. The canonical single-Reviewer collapses these.

### Where the three canonical names could add value

Two places:

**(a) `/vs`'s internal documentation**: the README and the vs.md spec could note "we extend the canonical Architect/Writer/Reviewer pattern with adversarial-separation Spec Critic and mechanical Tester". This connects users coming from Claude Code's welcome-banner tip to `/vs`'s richer flow without confusing them.

**(b) Pre-configured `devcontainer/agents/` definitions**: vibe could ship Software-Architect, Code-Writer, Code-Reviewer agent files alongside `shellcheck-fixer.md` and `security-review.md`, for users who want the canonical shape one-keystroke. This is independent of `/vs` — the agent definitions could be invoked via `claude --agent` or `/agents` natively, and `/vs` users wouldn't need to know about them.

### Recommendation

**Do not re-cast `/vs`.** The current decomposition is principled (adversarial separation at every stage) and would lose ground if collapsed to three roles.

**Do**:

1. Add a short § "Relation to canonical Architect/Writer/Reviewer" section to `vs.md` (1 paragraph) explaining the mapping table above. Connects Claude Code's welcome-banner tip to `/vs`'s flow.

2. Add a short bullet in README's `## Adversarial coding mode /vs` section explaining the same mapping in 1 sentence.

3. **Optionally** ship `devcontainer/agents/software-architect.md`, `code-writer.md`, `code-reviewer.md` as pre-configured agents for users who want the canonical names without going through `/vs`. These would be 5-10 line agent definitions following the existing `security-review.md` / `shellcheck-fixer.md` shape. This is a small, bounded follow-up — not part of this audit.

### What this audit does NOT recommend

- Aliasing `/vs`'s role names to canonical names. The Planner/Spec-Critic/Generator/Tester/Evaluator names are more precise about what each role does; aliases would create confusion ("which name should the docs use?").
- Replacing `/vs`'s internal flow with the three-role pattern. The five-role pattern exists for adversarial-separation reasons documented in the spec; collapsing it would lose those gains.
- Adding `--canonical` mode that swaps in the three-role pattern. Two parallel flows in one slash-command body is more maintenance burden than the user-clarity payoff justifies.

## Follow-up TODO entries

- [ ] **vs.md / README: add 1-paragraph mapping to canonical Architect/Writer/Reviewer pattern (2026-05-07 audit follow-up)** — see `.vs/audits/architect-writer-reviewer.md`. Bounded direct edit to vs.md `## Modes` section + 1 bullet under README's `## Adversarial coding mode /vs` section.

- [ ] **vibe: ship pre-configured Software Architect / Code Writer / Code Reviewer agents in `devcontainer/agents/` (2026-05-07 audit follow-up)** — bounded /vs task. New files: `software-architect.md`, `code-writer.md`, `code-reviewer.md`. Each ~5-10 lines following the `security-review.md` / `shellcheck-fixer.md` shape. Independent of `/vs`'s flow; provides one-keystroke canonical shape for users coming from Claude Code's welcome-banner tip. Optional.
