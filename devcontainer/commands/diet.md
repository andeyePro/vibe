---
description: Lean token-efficiency mode — suppress subagents, skip optional verifications, terse output. Reverse with /feast.
---

Lean mode active. For the rest of this conversation, until `/feast` is called:

- Do not invoke subagents (no `Agent` tool calls).
- Skip optional verifications (linters, type checks, test runs) unless I explicitly ask.
- Responses: bullet points or single sentences. No preamble, no trailing summary.
- Prefer inline `Bash` / `Read` / `Edit` over delegation.
- Ask before writing new files; edit existing ones where possible.

Before acting, briefly evaluate the most token-efficient way to complete what's likely next and suggest it to me:

- If the current model is Opus and the remaining work looks mechanical (edits, linting, straightforward refactors), suggest `/model sonnet` (or `/model haiku` for the most mechanical tasks).
- If the reasoning doesn't need to be deep, suggest `/effort low` or `/effort medium` (available levels: low, medium, high, xhigh, max).
- Avoid thinking-budget keywords ("ultrathink", "think harder", "think hard") in your internal framing — they trigger extended thinking and burn tokens.
- If the conversation is long and prior context isn't load-bearing, suggest `/compact`.

Acknowledge with a single line stating the efficiency choice (or "staying as-is" if none apply) and return to the current task.
