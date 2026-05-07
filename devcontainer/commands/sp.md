---
description: Apply Superpowers methodology (obra/superpowers, Anthropic-marketplace plugin) to the task that follows. Pass the task prompt after the command.
---

# /sp – Superpowers methodology shortcut

Apply [Superpowers](https://github.com/obra/superpowers) discipline to the task: `$ARGUMENTS`

## Pre-flight

Verify Superpowers is loaded in this Claude Code session. Indicators of a successful install:

- The `superpowers:brainstorming` skill is callable
- The `/using-superpowers` or `/brainstorming` slash command is registered
- A directory exists under `~/.claude/plugins/` matching `superpowers`

If Superpowers is **not installed**, stop and tell the user to run the following in this session, then re-issue `/sp` with the same task. (The marketplace-add line is a one-time setup; skip it if the marketplace is already registered.)

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
```

Alternative install path via the obra direct marketplace if the Anthropic official one is unavailable:

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

## Apply

If Superpowers is loaded, apply its methodology to `$ARGUMENTS`. Lean on the skills as the task requires:

- `superpowers:using-superpowers` – baseline: how to find and apply skills in a session
- `superpowers:brainstorming` – refine requirements before any code
- `superpowers:writing-plans` – decompose into 2-5 minute chunks
- `superpowers:executing-plans` – run a written plan in a separate session with review checkpoints
- `superpowers:subagent-driven-development` – fan out parallel work with two-stage review
- `superpowers:dispatching-parallel-agents` – 2+ independent tasks without shared state
- `superpowers:test-driven-development` – red / green / refactor; tests first, always
- `superpowers:systematic-debugging` – diagnose bugs and unexpected behaviour before proposing fixes
- `superpowers:requesting-code-review` – plan compliance and quality assessment
- `superpowers:receiving-code-review` – verify feedback rigorously, neither rubber-stamp nor blind-implement
- `superpowers:verification-before-completion` – evidence before assertions; verify before claiming "done"
- `superpowers:finishing-a-development-branch` – merge or PR decision
- `superpowers:using-git-worktrees` – isolated workspace per task
- `superpowers:writing-skills` – create or edit skills

## Note: `/sp` is additive, not a wrapper

`/sp` does not intercept or replace Superpowers' UI. Once the plugin is installed, all of these remain available and callable directly:

- `/brainstorming <task>` for Superpowers' structured brainstorming flow
- `/using-superpowers` to signal Superpowers methodology for the rest of the conversation (broader scope than `/sp`, which is task-scoped)
- All 27 Superpowers specialist agents, the EnterPlanMode hook, plan files at `docs/superpowers/plans/`, and bootstrap context injection

Use `/sp <task>` when you want Superpowers discipline applied to one task without picking a specific skill upfront. Use the native commands above when you want a specific Superpowers flow.

## Note on overlap with /vs

`/vs` (vibe's own adversarial harness) and Superpowers cover overlapping territory. Rough division as of XAP 0.0.1 / vibe 2026-04:

- **Use `/sp`** for broad spec-first agentic work where Superpowers' methodology fits. The institutionally-blessed default for most tasks.
- **Use `/vs`** when the task needs immutable mechanical tests (rigorous mode) or written-verdict adversarial review for fuzzy criteria (`--fuzzy` mode). `/vs` is more constrained and surfaces token-spend tracking for cost-sensitive work.

The long-term shape of `/vs` versus `/sp` is an open design decision; until resolved, both ship and the user picks per task.
