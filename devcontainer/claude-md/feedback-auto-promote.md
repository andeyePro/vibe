# Auto-promote cross-repo feedback memories to `/learnings`

This rule is always active inside every vibe container.

## Background

Claude Code maintains per-conversation auto-memory at
`~/.claude/projects/<slug>/memory/MEMORY.md`. Memories saved there persist
across conversations within the same project but DO NOT propagate across
projects. The `/learnings` library at `/learnings/<ts>-<rand>.md` is the
cross-project store — opt-in, hook-gated, mounted into every vibe container.

There is a structural gap. When Martin corrects you on a behavioral pattern
(e.g. "no em dashes", "lead with the literal command", "don't blame me when
verbatim-pasted commands fail"), you save a `feedback` memory. That memory
is per-project. The next time you start a fresh conversation in a different
vibe project, you don't see it. The same correction has to be made again.

The fix is auto-promotion: when you save a feedback memory that is
**cross-repo applicable**, you offer to write it to `/learnings` so future
conversations in any project pick it up.

## When to propose promotion

Propose promotion when the feedback memory you just saved meets ALL of:

1. **It's a behavioral or preference rule, not a project-specific fact.**
   - YES: "don't use em dashes", "lead with concrete commands", "answer in
     plain English before any approval ask", "default to UK local time
     for wall-clock times without TZ", "never actuate physical hardware
     without per-action permission".
   - NO: "Aqueum's accountant is Jacquelene", "task_014 is parked at
     planner stage", "the merge freeze begins 2026-03-05", "iScot pushes
     for more North Sea extraction".

2. **It applies regardless of which project you're working in.** Style
   rules, communication preferences, anti-patterns, safety rules, writing
   conventions — these all travel. Project deadlines, entity ownership,
   in-flight task state — these don't.

3. **The user has not already promoted an equivalent rule.** Before
   proposing, mentally scan the existing `/learnings/*.md` (use `ls
   /learnings` and grep for keywords) for a duplicate. If one exists,
   skip — duplicates degrade the library's signal-to-noise.

4. **The user has not opted out of this prompt.** If they say "stop
   asking me about /learnings" or set `VIBE_AUTO_PROMOTE=0` in their
   environment (host-side, persisted in `~/.vibe/config`), suppress the
   prompt for the rest of the session.

## How to propose

After saving the feedback memory, in the SAME response (or the next
turn if the memory save was the last action), include a short prompt:

```
Cross-repo applicable - save to /learnings?  Y / n / never-ask
```

- `Y` → run `/learn <one-line distillation of the rule>`. The
  PreToolUse hook on the `/learnings` write will prompt the user
  again at the file-system level (this is the trust boundary, not
  redundant). Standard hook flow applies.
- `n` → drop it; the feedback memory stays per-project only.
- `never-ask` → set a session-level marker (in your conversation
  state) suppressing further prompts. Surface the host-side opt-out
  command (`echo VIBE_AUTO_PROMOTE=0 >> ~/.vibe/config`) so they can
  make it permanent if desired.

The proposal is ALWAYS a single line. No paragraph, no spec details, no
preamble. The user has to choose three keystrokes; don't make them read.

## What NOT to do

- Do NOT auto-write to `/learnings` without proposing. The hook would
  catch it, but the prompt-and-confirm pattern is the trust contract.
- Do NOT promote project-specific memories. Re-read the IS/IS NOT list
  in § "When to propose promotion". If unsure, default to NOT promoting
  (false negatives are recoverable; false positives pollute the library).
- Do NOT promote multiple memories in one response. One prompt per
  cross-repo-applicable memory save. Batching dilutes the signal.
- Do NOT propose if the user explicitly asked you to stop saving
  memories ("don't memorise this", "ephemeral") for this turn.

## Pairs with

This rule pairs with the existing `/learn` slash command (which is the
mechanism by which the promotion actually writes to `/learnings`) and
the `/learn` smart-capture flow shipped 2026-05-07 (which does its own
semantic-check on the proposed pattern body). The auto-promote rule is
the *trigger*; smart-capture is the *quality gate*; the PreToolUse hook
is the *security boundary*. All three layers compose.
