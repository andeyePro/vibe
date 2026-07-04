# Harness landscape audit — July 2026

Commissioned 2026-07-04 (Martin: "check that vibe is best in class, or if there are any other features/strategies we should employ or indeed if Anthropic already provide something that covers 99% of what we need. Or even if there is a paid harness that we would be better moving to."). Two parallel Sonnet research agents (web-current); synthesis by the Fable session lead. Constraint profile: solo dev, macOS, Claude Max 5x, subscription-only spend (Fable 5 credits by explicit consent only), containerised YOLO safety, adversarial multi-agent QA.

## Verdict in three lines

1. **No paid harness is a better home.** Anthropic's April 2026 enforcement against third-party tools riding Pro/Max OAuth means every commercial agent (Cursor, Devin, Factory, Amp, Warp) meters Claude as separate API spend, and the rest (Antigravity, Jules, Codex) means leaving Claude. vibe sits in the one bucket the subscription still legitimately covers — Claude Code itself.
2. **Anthropic does NOT cover 99% natively — more like 60–70% of the headline pitch**, and the covered part is the container, not the harness. What stays uncovered: the one-command launcher with per-repo PAT blast radius, the `/vs` adversarial build loop with working model tiering, auto-resume across rate-limit resets, the Fable billing gate, `/learn`, `/c`.
3. **vibe is best-in-class on containment among subscription-compatible tools** — every rival orchestrator surveyed (Conductor, vibe-kanban, claude-squad, Nimbalyst, Gas Town, tmux-orchestrators) isolates via git worktrees only, no container/firewall, some with documented permission-propagation bugs.

## Anthropic-native coverage (July 2026)

| vibe capability | Native equivalent | Covered? |
|---|---|---|
| Containerised env + firewall | Official devcontainer feature + reference `init-firewall.sh`; no `--sandbox` mode; bypassPermissions-in-container still the recommended YOLO pattern | Partial |
| One-command launcher, auto-rebuild/retry | none | No |
| Per-repo fine-grained PAT | none | No |
| Guard hooks | Hooks API official, but no default guards shipped | Partial |
| Overnight autonomous runs | **Routines**: cloud-hosted, subscription-quota-included, ~5/day Pro / ~15/day Max, ≥1 h cadence, fresh clones only | Partial |
| Recurring tasks | `/loop` (local) + `/schedule` Routines (cloud) | Yes |
| Adversarial build harness (`/vs`) | Subagents; experimental **Agent Teams** (peer messaging, shared task list, per-teammate models); **Dynamic Workflows** rubric-grader (producer ≠ judge); `/code-review ultra` (review-only) — no native plan/build/test/evaluate loop | Partial |
| Per-role model tiering | `model:` agent frontmatter documented but **broken** (claude-code #44385) — dispatch-param `model:` is the only reliable route; `opusplan` is session-level plan/execute split only | No (declared, not working) |
| Usage visibility | `/usage`, `/status`, `/cost` — no month-to-date or credit-balance surface | Partial (hence `/budget`) |
| Fable 5 billing gate | none — credits deplete silently once enabled | No |
| Auto-resume on window exhaustion | none; feature request closed unimplemented (#36320) | No (hence the 2026-07-04 launcher loop) |
| Superpowers bundling | Official marketplace, one `/plugin install` away | Yes |
| `/learn` cross-project library, `/c` clipboard | none | No |

Fable 5 confirmations: included up to 50% of weekly limits through 7 Jul; metered usage credits $10/$50 per MTok from 8 Jul; no automatic fallback when the allowance ends; Anthropic states intent to restore subscription inclusion "as capacity allows".

## External landscape

- **Commercial**: Devin has the only true built-in adversarial Critic (but ACU billing); Antigravity 2.0 has the best macOS sandboxing (Seatbelt, per-action fs/network toggles — but Gemini). Cursor Bugbot = plan→sandboxed-execute→evaluate, bolt-on review. Replit Agent 3 is the cautionary tale: effort-based pricing with documented $1,000/week blowouts — the argument for `/vsss` budget caps and the `/budget` skill.
- **Claude-Code orchestrators** (subscription carries over): Conductor (free Mac app, parallel worktrees, explicitly "run it in a VM" for safety), vibe-kanban (permission-propagation bugs #844/#1996), claude-squad, Nimbalyst (ex-Crystal), Gas Town (Yegge's 20–30-instance org-chart), tmux-orchestrator family (self-scheduling wake-ups; zero isolation). Terragon shut down Jan 2026. All complement-at-most; none replaces vibe's containment.
- **OSS QA harnesses**: Superpowers (verified ~246k stars; note it has been *retreating* from subagent review toward inline self-review since 5.0); wan-huiyan/agent-review-panel — 4–6 blind independent reviewers + sycophancy/correlated-agreement detection, the most sophisticated adversarial-QA mechanism found (all-Opus cost model though). AutoGen/MetaGPT/CrewAI remain API-key-only — out of scope.

## Adopted / queued from this audit

Adopted 2026-07-04 into `/vs`:

- Structural (not instructed) reviewer independence — `--fuzzy` Reviewer now dispatches as the read-only `code-reviewer` agent type (Amp "Oracle" pattern).
- Never trust the producer's claim — Evaluator must read raw `test-output.log` before any pass verdict (Cursor Bugbot pattern).
- Capability-gated escalation ladder + Model plan (this session's own design, informed by the tiering gap upstream).

Queued in TODO.md:

- Agent Teams + Dynamic Workflows rubric-grader migration when the experimental flag graduates.
- `--panel` blind-verdict + anti-sycophancy mechanics from agent-review-panel.
- tmux-orchestrator-style self-scheduled wake-ups are already covered by `/loop` + ScheduleWakeup + the new launcher auto-resume; no action.

Sources: both agents' full reports (with per-claim URLs) are preserved in this session's transcript; headline sources — code.claude.com/docs (devcontainer, hooks, agent-teams, routines, model-config, scheduled-tasks), anthropic.com/news (redeploying-fable-5, higher-limits-spacex), github.com/anthropics/claude-code issues #44385 & #36320, claude.com/blog (dynamic-workflows), conductor.build, github.com/BloopAI/vibe-kanban, github.com/wan-huiyan/agent-review-panel, obra/superpowers.
