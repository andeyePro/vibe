---
description: Claude code-review on the working diff plus opt-in outside-reviewer slots (gemini, codex), merged into one verdict — the fan-out is the default, --solo runs Claude only.
---

# /review

One command: Claude's own code-review on a diff, plus any enabled outside-reviewer slots, merged into one verdict.

Today /review is Claude-only: the fan-out has zero enabled slots.

Usage: `/review [--solo] [--level low|medium|high|max] [--slot <name>] [--comment] [<target>]`

Default level: `high`. Default target: the working diff. `<target>` may instead be a PR number, a branch, or a path.

## What it does

1. Run `Skill(skill: "code-review", args: "<level> [<target>]")` — Claude's own review, always.
2. Run every ENABLED slot from the registry below (none today) on the same target.
3. Merge Claude's findings with every slot's findings per `## Merge`, and print one `## Review verdict` block.

## Flags

- `--solo` = Claude only. Skips the fan-out step even once slots are enabled.
- `--level <low|medium|high|max>` passed through to `code-review`. Default `high`. `--level ultra` is refused with one line: refuses --level ultra — ultra is cloud-billed and must be typed by the user directly, never invoked implicitly by another command.
- `--slot <name>` on a slot that is not enabled → refuse with one line naming what it needs.
- `--comment` is the only way findings reach GitHub: never posts to GitHub unless --comment is passed.
- --comment is GitHub-outward like push: /vss and /vsss treat it as hard-escalate, never auto-fired.
- `<target>` — PR number, branch, or path. Default: the working diff.

With zero enabled slots the default fan-out is identical to --solo.

## Slot registry

| slot | enabled | needs |
|---|---|---|
| gemini | no | `GEMINI_API_KEY` in `~/.vibe/tokens`; a firewall allowlist entry |
| codex | no | a ChatGPT subscription |

A slot is enabled only when every item in its needs column exists; enabling a slot is Martin's step, never this command's.

## Merge

Same correlated-agreement discipline as `/vs § Step 5c`, applied across every enabled reviewer plus Claude: a correlated consensus (near-duplicate reasoning across reviewers) counts as one reviewer's worth of signal, not one-per-reviewer confidence; an independent consensus (same verdict, visibly different routes) earns full confidence; split verdicts are the real product and get explicit adjudication written into the output — quote the dissent, refute or accept it in writing. No averaging, no majority shortcut: an unrefuted BLOCKING dissent from any single reviewer is never a pass (see `/vs § Step 5c`).

Output exactly this block:

```
## Review verdict
### Findings
One line per finding: severity, file:line, which reviewers agree.
### Dissent
Unmerged single-reviewer BLOCKING items, or `none`.
### Verdict
`PASS`, `FAIL`, or `SPLIT` plus one sentence.
```

## Relation to /vs

`/vs --panel` unchanged: it still dispatches Sonnet code-reviewer panellists inside a harness cycle. `/review` works on any diff, not only harness cycles — call it standalone, any time, on any target. Inherits /vss's safety floor: no push, no hook or firewall edits.
