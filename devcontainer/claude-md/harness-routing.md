# Harness routing — plain prompts get the best tool, unprompted

The user should only ever need to prompt; you propose the right harness. Explicit invocations (`/vs`, `/vss`, `/vsss`, `/loop`, `/sp`) always win — never second-guess them. For a plain prompt, route:

- **Answer/assess** — questions, problem descriptions, thinking-out-loud: just answer. No harness, no offer.
- **Small bounded change** (single file, mechanical, config/docs): do it directly. Superpowers process skills (`brainstorming`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`) still apply per their own triggers.
- **Multi-step build with verifiable criteria**: do the work, and if it is genuinely `/vs`-shaped (spec-able, testable, single feature), say so in one line and offer it — "this would suit `/vs` — want the adversarial harness on it?". One offer, then respect the answer.
- **"Do this without asking me anything"** intent: suggest `/vss <task>` (acts-as-user within the hard-escalate list).
- **"Keep going / burn my session"** intent: suggest `/vsss`, plus `--auto-resume N` if they want it to span credit-window resets.
- **Recurring/polling-shaped** ("check X every ...", "keep an eye on ..."): `/loop` (in-session, machine on) or Claude Code's `/schedule` Routines (cloud, subscription-included, ≥1 h cadence) — pick by whether the Mac stays awake.
- **Model routing**: never dispatch a credit-billed model (Fable 5) without explicit user consent; subscription tiers per `/vs § Model economy` (haiku mechanical, sonnet generation, opus judgment). Monthly spend/quota questions → `/budget`.

Calibrate offers to Martin's asking-discipline: at most one routing suggestion per task, made at the start, never mid-flow.
