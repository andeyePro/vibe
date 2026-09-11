---
name: vsss
description: Runs vibe's /vsss looped autonomous solo by reading and following /usr/local/share/vibe/commands/vsss.md.
---

# $vsss

Read `/usr/local/share/vibe/commands/vsss.md` now, in full, and follow it
exactly as written — it is the single source of truth for this command.
Wherever it calls a Claude-only primitive, apply the substitution below
instead; nothing else about the command body changes.

## Substitutions (identical across `$vs`, `$vss`, `$vsss`)

| Claude primitive | Codex substitution |
|---|---|
| `Agent(subagent_type, model, prompt)` | `vibe-delegate role <role> --model <model> --cwd <workspace> < brief.txt` (roles: `planner`, `spec-critic`, `generator`, `tester`, `reviewer`, `evaluator`) |
| `Skill(skill: "code-review")` | `vibe-delegate review codex < diff`, plus your own read |
| a nested `/vs ...` / `/vss ...` step inside `vss.md` / `vsss.md` | read `/usr/local/share/vibe/commands/<that>.md` now and follow it in this same turn — skill output is never rescanned for `$` mentions, so a nested mention loads nothing |
| `Read` / `Write` / `Edit` | your own file tools |
| `Bash`, `Grep`, `Glob` | your own shell tool (`rg`, `find`) |
| `ScheduleWakeup` | not available; end the turn and let the supervisor re-enter |
| `/learnings` writes | refused; there is no ask in Codex |

## The `/` form

In Codex's own terminal only `$vsss` exists — the composer rejects an
unknown `/vsss` before it is even submitted. `/vsss` is the same command in
Claude Code, and, once the supervisor lands, in unattended Codex runs too.
