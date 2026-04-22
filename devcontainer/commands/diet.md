---
description: Lean token-efficiency mode — suppress subagents, skip optional verifications, terse output. Reverse with /feast.
---

Lean mode active. For the rest of this conversation, until `/feast` is called:

- Do not invoke subagents (no `Agent` tool calls).
- Skip optional verifications (linters, type checks, test runs) unless I explicitly ask.
- Responses: bullet points or single sentences. No preamble, no trailing summary.
- Prefer inline `Bash` / `Read` / `Edit` over delegation.
- Ask before writing new files; edit existing ones where possible.

Acknowledge with a single line and return to the current task.
