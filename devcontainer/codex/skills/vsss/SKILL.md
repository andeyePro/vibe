---
name: vsss
description: Runs vibe's /vsss looped autonomous solo by reading and following /usr/local/share/vibe/commands/vsss.md.
---

# $vsss

Read `/usr/local/share/vibe/codex-vsss.md` first and apply its supervised
handoff before starting work. Inside the owned supervised thread, read
`/usr/local/share/vibe/commands/vsss.md` in full. The Codex contract overrides
its launcher, loop, clock and Stop-hook paragraphs; other workflow rules apply.
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
| `ScheduleWakeup` | not available; do other queued work instead (in a live `$vsss` run the Stop hook refuses an early turn end, and the supervisor re-enters after a quota wait) |
| `/learnings` writes | refused; there is no ask in Codex |

## The `/` form

In Codex's own terminal, only `$vsss` is a guaranteed match: the composer
rejects an unknown `/vsss` before it is even submitted. Typing ` /vsss …`
with one leading space also works — the composer lets a space-prefixed line
through as plain text and trims the space before it reaches the model — and
a managed `UserPromptSubmit` hook then adds context pointing the model at
this `$vsss` skill with the rest of the line as arguments, verbatim; that is
model-mediated, not deterministic, so `$vsss …` remains the reliable form.
`/vsss` is the same command in Claude Code, and, once the supervisor lands,
in unattended Codex runs too.

## Runtime-native roles and FM2C

Read `/usr/local/share/vibe/codex-context.md` at startup and on resumption. `FM2C` means the configured Codex answer channel; check it between tasks and on a user reminder. Model routing (enforced by `vibe-delegate` through `vibe-models`): you, the lead, are whatever model the user picked for this conversation; `vibe-models status` shows it, the latest model in each class, and what you may use without asking. `--model` takes a class (`terra`, `luna`, `sol`, `astra`), which always resolves to the newest model of that class in this account's catalog, never a fixed id. Cost per token: Astra > Sol > Luna > Terra (Claude: Fable > Opus > Sonnet > Haiku; tiers compare by position across vendors). Use classes at or below your own tier: `luna`/`terra` for bounded mechanical work, your own class for judgment. A dearer class needs the user's explicit, current permission: ask first, then pass `--consent-model` or run `vibe-models grant <class> --for <duration>`. Older models only when the user asks: record it with `vibe-models pin <class> <model-id> --for <duration>` after asking how long it should stand; at the start of each significant task, and whenever the helper says so (every 8 hours), ask whether it still stands and `vibe-models confirm` or `unpin`. Log actual usage. Use only available subscription routes. A Claude model in a shared command's example is not the Codex default: substitute by task class. Cross-vendor roles require explicit user opt-in. Never silently use paid/API fallback.
