# Project hygiene for shared / upstream-bound repos

If the repo you're working in WILL go to an upstream maintainer (PR review, plugin submission, public release), apply stricter hygiene than for your own private project. This rule prevents the recurring failure mode of committing personal/per-machine cruft and getting flagged in code review.

Triggered 2026-05-08 by amy-bo/electroPioreactor PR #16 review comments.

## Don't commit per-machine runtime files

vibe writes runtime files into `/workspace` that should never reach the upstream repo. The vibe `install-claude-extras.sh` auto-adds these to `.gitignore` (managed block on first container start), but if that block has been removed or `VIBE_AUTO_GITIGNORE=0` is set, you must add them by hand:

- `.claude/settings.local.json` — inside-container runtime config
- `.vibe/` — vibe state directory (contains `.vibe/copy-latest.txt` clipboard scratch and similar)

These are auto-excluded by vibe's managed `.gitignore` block. If you see them in `git status`, check `.gitignore` for the vibe-managed block; if missing, restore it or add the lines manually.

## Don't commit setup-specific notes in shared repos

Files containing personal-machine specifics — local IP addresses, hostname like `mcomz.local` or `pi02.local`, your user path `/Users/martin/...`, your network subnet — should NOT land in a repo that goes upstream. Reviewers will flag them as "too specific to your setup".

Examples that triggered the rule (AEP-Plugin PR #16):

- `pi02-setup-notes.md` containing "Pi is running at 192.168.0.96 on the andeye WiFi"
- README sections referencing your specific Pioreactor IP

If you must keep such notes in the repo for your own reference, gitignore them (`/.local-notes/` or similar) or move them to a separate scratchpad outside the repo.

## Don't ship system-modifying scripts without consent flow

If the project includes scripts that patch user systems (`apply-X-patch.sh`, system-config rewriters, things that touch `~/.config` or system services), wrap them in an explicit user-consent flow:

- Show what's about to change BEFORE changing it.
- Ask for confirmation. Don't auto-apply on install or container start.
- Provide a documented revert path in the same commit.
- Prefer "require minimum version X" to "we'll patch your system to fit".

The reviewer-flagged pattern (AEP-Plugin PR #16): `apply-pr615-patch.sh` patched users' Pioreactor frontends without asking. Reviewer's correction: "I don't like this idea of patching people's systems without their consent. Maybe just require 26.5.0 as a minimum?"

## Don't hardcode magic channel/port assignments in user-facing config

If a config exposes a channel/port/pin/socket selector to end users, don't pin to a specific one ("LED channel D", "PWM channel 4"). Make it configurable. Hardcoded picks fail the reviewer's "what if PWM 4 is set to something else?" smell test.

## Pre-commit checklist (informal)

Before staging files for an upstream-bound commit, scan for:

- Per-machine paths (`/Users/<your-name>/`, `~/.something-personal/`)
- Local IP addresses (`192.168.x.x`, `10.x.x.x`, `169.254.x.x`)
- Hostnames that aren't your project's (`*.local`, your home WiFi name)
- Runtime artifacts (`.claude/settings.local.json`, `.vibe/`, `*.tokens`, `.env*`)
- Setup-specific notes files (`pi02-setup-notes.md`, `my-laptop-config.md`)
- System-patching scripts not gated by explicit user consent

If any of these are staged, prefer one of: gitignore them, move them to a scratchpad path outside the repo, or refactor them to be machine-agnostic.

## When this rule does NOT apply

Your own private repo where you ARE the only audience. Personal-machine specifics, runtime artifacts, and ad-hoc patching scripts are fine there. The discipline is for when the repo's audience extends beyond you.
