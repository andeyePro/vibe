---
name: vss
description: Runs vibe's /vss autonomous one-shot by reading and following /usr/local/share/vibe/commands/vss.md.
---

# $vss

Read `/usr/local/share/vibe/commands/vss.md` now, in full, and follow it
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

In Codex's own terminal, only `$vss` is a guaranteed match: the composer
rejects an unknown `/vss` before it is even submitted. Typing ` /vss …` with
one leading space also works — the composer lets a space-prefixed line
through as plain text and trims the space before it reaches the model — and
a managed `UserPromptSubmit` hook then adds context pointing the model at
this `$vss` skill with the rest of the line as arguments, verbatim; that is
model-mediated, not deterministic, so `$vss …` remains the reliable form.
`/vss` is the same command in Claude Code, and, once the supervisor lands,
in unattended Codex runs too.

## Runtime-native roles and FM2C

Read `/usr/local/share/vibe/codex-context.md` at startup and on resumption. `FM2C` means the configured Codex answer channel; check it between tasks and on a user reminder. Codex-led roles default to OpenAI models: `luna` for bounded mechanical tests, `terra` or `sol` for ordinary implementation and spec/diff review, `astra` for difficult design, security and evaluation. These are `vibe-delegate role --model` aliases; verify model access at dispatch and log actual usage. Use only available subscription routes. A Claude model in a shared command's example is not the Codex default: substitute by task class. Cross-vendor roles require explicit user opt-in. Never silently use paid/API fallback.
