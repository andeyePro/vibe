---
description: Claude code-review on the working diff plus opt-in outside-reviewer slots (gemini, codex), merged into one verdict — the fan-out is the default, --solo runs Claude only.
---

# /review

The `gemini` slot runs whenever `GEMINI_API_KEY` is present and the project enables it.
The `codex` slot uses a ChatGPT subscription through Codex CLI.
Without available outside slots, /review is Claude-only.

Usage: `/review [--solo] [--level low|medium|high|max] [--slot <name>] [--comment] [<target>]`

Default: `high`, the working diff; alternatively a PR, branch, or path.

## What it does

Resolve the shared diff snapshot before dispatching either leg.

1. Run `Skill(skill: "code-review", args: "<level> [<target>]")` — Claude's own review, always.
2. Unless `--solo`, read `node /usr/local/bin/vibe-delegate slots` from the repo root.
   Run every available, enabled slot below, or only the explicitly requested `--slot`.
   A policy error stops fan-out and is reported; never ignore it to enable reviewers.
3. Merge Claude's findings with every slot's findings per `## Merge`, and print one `## Review verdict` block.

## Flags

- `--solo` = Claude only. Skips the fan-out step even once slots are enabled.
- `--level <low|medium|high|max>` passed through to `code-review`. Default `high`. `--level ultra` is refused with one line: refuses --level ultra — ultra is cloud-billed and must be typed by the user directly, never invoked implicitly by another command.
- `--slot <name>` on a slot that is not enabled → refuse with one line naming what it needs.
- `--comment` is the only way findings reach GitHub: never posts to GitHub unless --comment is passed.
- --comment is GitHub-outward like push: /vss and /vsss treat it as hard-escalate, never auto-fired.
- `<target>` — PR number, branch, or path. Default: the working diff.

With no available outside slots the default fan-out is identical to --solo.
`--solo --slot` is contradictory: refuse it. Disabled means disabled even with `--slot`.
Report skipped slots and their missing prerequisite; never count absence as agreement.

## Invoking the gemini slot

Resolve the target ONCE and save a private diff file for all reviewers: working tree
means staged plus unstaged (`git diff HEAD`); identify untracked files separately.
For a branch use its merge-base diff; for a PR obtain its diff; for a path filter
the working diff. Claude reviews that same snapshot. Never substitute plain
`git diff` for a named target. Send only the diff and review instructions.

```bash
jq -Rs '{contents:[{parts:[{text:(. + "\nReview this diff. List correctness bugs only: SEVERITY file:line - one sentence.")}]}]}' < "$diff_file" \
  | curl --fail-with-body -sS --connect-timeout 10 --max-time 600 -X POST \
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent" \
      -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' --data-binary @- \
  | jq -er '.candidates[0].content.parts[0].text | select(length > 0)'
```

It never gets a shell, never writes. Failure or refusal is never a PASS.
For a connection error, run `sudo /usr/local/bin/refresh-extra-domains.sh` once
and retry once. No retry loop or silent model substitution.

## Invoking the codex slot

Check prerequisites with `node /usr/local/bin/vibe-delegate status codex`, then
send the SAME saved diff, batched once, from the repo root:

```bash
node /usr/local/bin/vibe-delegate review codex < "$diff_file"
```

The helper uses `codex exec -m gpt-6-astra --output-schema … --json` because
`codex review` in 0.154.0 lacks `--output-schema`. It runs a fresh, ephemeral,
read-only process outside the repository with shell/MCP/apps disabled, passing
only the diff. Codex alone accesses its login; never inspect its auth file.
Parse JSON `findings` (severity/file/line/message), `verdict`, `summary`, and
`usage`. The helper validates types, required fields and completion metadata.
Never recover findings by parsing prose. Invalid JSON, missing usage, login or
quota failure, refusal, or any nonzero exit must appear as an incomplete slot;
final verdict is at least SPLIT until reviewed, never a silent PASS.

## Slot registry

| slot | enabled | needs |
|---|---|---|
| gemini | auto | `GEMINI_API_KEY` in `~/.vibe/tokens`; `generativelanguage.googleapis.com` in the project's `.vibe/domains` |
| codex | auto | ChatGPT subscription with Astra access; Codex CLI 0.154.0+ (helper-enforced); file-store `codex login` on the Mac; untracked `.vibe-allow-codex` marker (mounts the login dir); OpenAI hosts in `.vibe/domains` |

A slot is enabled only when every item in its needs column exists.
`.vibe/review-slots` is per-project and UNTRACKED: `codex=off` or `gemini=off`
disables that slot. Missing file/entries default to all enabled; comments and
blank lines are allowed. Malformed, duplicate, tracked or symlinked policy is
refused. Claude's own review always runs. `/ask` is independent of this policy.

Allowlist entries belong in `.vibe/domains`, NOT in the shipped `init-firewall.sh` list:
`chatgpt.com`, `api.openai.com`, `auth.openai.com` for Codex, and Google's host
above for Gemini. Only extra domains get mid-session CDN re-resolution.

## Merge

Apply `/vs § Step 5c`: a correlated consensus counts as one signal; an independent consensus earns full confidence. Adjudicate split verdicts explicitly: quote and
accept or refute each dissent. No averaging or majority shortcut:
an unrefuted BLOCKING dissent from any single reviewer is never a pass.
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

`/vs --panel` is unchanged. `/review` works on any diff. Inherits /vss's safety floor: no push, no hook or firewall edits.
