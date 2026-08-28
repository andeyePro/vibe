# Auto-memory is per-project — cross-project facts go to /learnings

Since task_014, each host project gets its own Claude history and
auto-memory: the launcher binds `~/.vibe/projects/<sha1-of-project-path>/`
over `/home/node/.claude/projects/`, so the auto-memory you read and write
at `/home/node/.claude/projects/-workspace/memory/` is scoped to THIS
project only. The rest of `~/.claude` (login, settings, agents, commands)
stays shared across all vibe containers.

Why the isolation matters: it keeps `vibe X --continue` resuming project
X's most recent conversation instead of the globally-most-recent one, and
it keeps project-specific memory from polluting unrelated work — a fact
about this repo's build system has no business steering a session in a
different repo. The per-project boundary is doing that job by design:
preventing cross-contamination, not losing information.

Consequence for what you save where:

- Project-specific facts (state of tasks, repo conventions not in its
  docs, entity facts for this project) → auto-memory, as normal.
- Cross-project facts (the user's preferences, voice, work style,
  recurring corrections) → they will NOT travel via auto-memory any
  more. Propose them for `/learnings` (the `/learn` flow, hook-gated) —
  that library is mounted into every vibe container.

If a memory you expect is missing, it may predate the per-project split:
conversations and memory recorded before task_014 live in the old shared
volume and are shadowed by the new bind — ask the user rather than
assuming the memory never existed.
