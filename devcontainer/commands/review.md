---
description: Claude code-review on the working diff plus opt-in outside-reviewer slots (gemini, codex), merged into one verdict — the fan-out is the default, --solo runs Claude only.
---

# /review

One command: Claude's own code-review on a diff, plus any enabled outside-reviewer slots, merged into one verdict.

The `gemini` slot is wired: it runs whenever `GEMINI_API_KEY` is present in the
container. With no key, /review is Claude-only.

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

With no key present the default fan-out is identical to --solo.

## Invoking the gemini slot

Send the same diff Claude reviewed, ask for the same finding shape, and treat the reply as one reviewer's verdict into `## Merge`. Never send anything but the diff and the review instruction.

```bash
jq -Rs '{contents:[{parts:[{text:.}]}]}' <<<"$(git diff)$(printf '\n\nReview this diff. List correctness bugs only, as: SEVERITY file:line - one sentence. No praise, no style notes.')" \
  | curl -sS -X POST \
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' --data-binary @- \
  | jq -r '.candidates[0].content.parts[0].text'
```

If the model id 404s, a preview has retired: swap it here for a current one (`gemini-3.5-flash` is the GA fallback). If the call fails with a connection error or HTTP 000, run `sudo /usr/local/bin/refresh-extra-domains.sh` once and retry before reporting it — the edge has moved.

The slot is read-only by construction: it receives a diff and returns text. It never gets a shell, never writes, and its findings reach GitHub only through `--comment`, same as Claude's.

## Slot registry

| slot | enabled | needs |
|---|---|---|
| gemini | auto | `GEMINI_API_KEY` in `~/.vibe/tokens`; `generativelanguage.googleapis.com` in the project's `.vibe/domains` |
| codex | no | a ChatGPT subscription that entitles the account to the model; Codex CLI >= 0.153.0 in the image |

A slot is enabled only when every item in its needs column exists. `auto` means this command detects the condition at run time and needs no flip; `no` means the slot is documented but not wired, and wiring it is Martin's step, never this command's.

The allowlist entry belongs in `.vibe/domains` (per-project, untracked), NOT in the shipped `init-firewall.sh` list: `generativelanguage.googleapis.com` is CDN-fronted and moves edges within the hour, and only extra domains are covered by `sudo /usr/local/bin/refresh-extra-domains.sh`. A shipped entry would go stale mid-session with no in-container fix.

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
