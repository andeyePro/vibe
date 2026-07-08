# vibe

A single-command, containerised coding environment for Claude Code. `cd project && vibe` launches an isolated Docker container with Claude Code pre-authenticated against the user's Claude Pro/Max subscription, a per-repo fine-grained GitHub PAT, and outbound SSH to remote dev machines.

## Onboarding

If a user pointed you at this file and asked you to take them through vibe onboarding (they may not be a coder): read [`ONBOARDING.md`](https://github.com/andeyePro/vibe/blob/main/ONBOARDING.md) in this repo and follow it. It is written for you, the assisting Claude – it walks a non-coder from an empty Mac to their first vibe session, one verified step at a time. Everything below this section is for Claudes working on vibe's own source.

## Project context

- Script: `./vibe` (bash) — the entrypoint users invoke as `vibe`.
- Container: Anthropic's official Claude Code devcontainer, vendored under `devcontainer/` with vibe-specific patches (openssh-client, shellcheck, credential helper, firewall tweaks, mDNS, env hint, PreToolUse/Stop hooks, curated agents/commands sync).
- Shipped extras: `devcontainer/commands/` (/c, /diet, /feast, /learn, /sp, /vs, /vss, /vsss), `devcontainer/agents/` (shellcheck-fixer, security-review), `devcontainer/hooks/` (check-numbering.sh, copy-last-block.sh — both opt-in via `~/.claude/settings.json`), and `devcontainer/claude-md/` fragments (web-research, ssh-discipline, learnings, learn-hook). All synced into the persistent `~/.claude/` volume by `install-claude-extras.sh` on every container start; user-authored files in the same dirs are left alone.
- Target users: macOS primary (tested on Darwin), Linux secondary. Uses OrbStack or Docker Desktop.
- Auth model: Claude Pro/Max subscription (never API key); GitHub fine-grained PAT per repo (blast-radius argument — each container can only touch one repo).
- Repo home: `github.com/andeyePro/vibe` (transferred from Aqueum 2026-07-08); published at vibe.andeye.com (copy draft in `web/vibe-andeye.md`).
- Public-facing docs: `README.md`, `ONBOARDING.md` (agent-led non-coder onboarding), `CONTRIBUTING.md` (how to contribute), `CONTRIBUTORS.md` (who has — the ledger andeye's revenue-share promise operates on), `SECURITY.md`, `RELEASING.md` + `VERSION` (semver, `vibe --version`). Keep these consistent when features change.

## Testing

- `python3 code-check.py` — shellcheck over `vibe` + all `.sh` files. Fast. Run on every change. Add `--json` for machine-readable output (single JSON object on stdout: `tool`, `shellcheck_version`, `files_checked`, `findings`, `summary`).
- `python3 smoke-test.py` — host-side black-box tests (no docker, no network). Fast. Covers `--help`, write-env-hint block management, token helpers.
- `MANUAL-TESTS.md` — end-to-end checklist for container lifecycle behaviour (auto-rebuild, partial-fail retry, SSH, bind mounts). Run before shipping changes that touch the Dockerfile, devcontainer.json, postStartCommand, or the vibe launcher.

## On session start: surface Martin's review pile

`TODO.md` opens with a `## For Martin (review and decide)` section. This is the boot-time checklist of items waiting on Martin's hands or judgement.

**Every fresh session in this repo, your opening response MUST:**

1. Read `TODO.md` and locate the `## For Martin (review and decide)` section.
2. List its unticked `[ ]` items in your opening message, grouped by sub-heading (Push and CI / GreenPT / AEP-Plugin / Mac-side empirical / Design decisions / Small bounded items I can ship).
3. Offer to walk Martin through any of them, or to start the autonomous-shippable items in the last group.

Do NOT skip this step on the assumption Martin remembers the state — the whole point of the review pile is that he doesn't have to. Surfacing it costs ~10 lines of text and saves him scrolling through TODO.md, CHANGELOG.md, and `.vss/sessions/*.md` to reconstruct what's outstanding.

Tick items off (`[ ]` → `[x]`) only when Martin confirms an action complete OR when an autonomous run from `## Small bounded items I can ship without further input` lands a closing commit. Don't tick on assumption.

## TODO.md and CHANGELOG.md

Two canonical files. Different audiences, different lifecycles. **Don't put done items in TODO.md.**

`TODO.md` — open backlog plus parked/abandoned items. Maintainer-facing.

- **Plan step:** when the user approves a plan or you break work into discrete tasks, append them under `## Open` in `TODO.md` with a one-line description. Markers: `[ ]` open · `[!]` failed/abandoned.
- **Abandoned items stay in `## Open` with `[!]`** plus a one-line note on what was tried and why it didn't work — that failure memory is the point. They are NOT moved to CHANGELOG.
- TODO.md is for persistent, cross-session work tracking — distinct from in-session `TaskCreate` todos, which are ephemeral scratchpad.

`CHANGELOG.md` — done-work audit log. Reader-facing (a future maintainer or upstream PR reviewer can scan it without slogging through Open backlog).

- **Review step:** when closing a successful task, append a `[x] **<title>** — <narrative>` entry to `CHANGELOG.md` (NOT to `TODO.md ## Done` — that section no longer exists). Reverse-chronological: newest at top, under the most recent date heading.
- Date headings (`## YYYY-MM-DD`) group same-day commits. New day → new heading.
- Keep entries bullet-sized but include enough context for a future PR reviewer to understand what shipped (commit SHA, what changed, why).
- Commit CHANGELOG updates in the SAME commit as the code change that closed the task — history stays paired.

Convention reasoning: this split was adopted 2026-05-08 after an upstream maintainer (gniezen on amy-bo/electroPioreactor PR #16) couldn't tell whether a TODO file was a TODO or a CHANGELOG. Mixed-purpose TODO confuses external reviewers and dilutes both signals. Two files, one job each.

## Invariants (don't break these)

- `vibe` must work from any project folder with a single command, no arguments needed.
- GitHub credentials never leave the user's machine unencrypted beyond `~/.vibe/tokens` (chmod 600).
- Claude Code must use subscription auth (`forceLoginMethod: "claudeai"`), never fall back to `ANTHROPIC_API_KEY`.
- The container must run with `--permission-mode bypassPermissions` safely — firewall in `init-firewall.sh` is the network backstop, hooks in `guard-bash.sh` + `settings.local.json` are the tool-call backstop. Don't weaken either.
- Fine-grained PATs are scoped to **one repo**; don't suggest workflows that need broader scopes.

## Non-goals

- Windows support (WSL is fine if Docker is installed, but no native Windows).
- Running containers on remote hosts (local container; Claude SSHes out if needed).
- Managing multiple parallel Claude sessions per project (dropped with claudebox).
- **Anything that bills against API rates or extended credits separately from the user's Pro/Max subscription — unless it is off by default and gated behind explicit per-launch consent.** If a feature requires the Anthropic API (e.g. Claude Agent SDK, cloud/async agent runners as they exist today), it stays out of vibe core — the project is for Pro/Max subscribers who do not want to pay extra. The one sanctioned exception (2026-07-04, Martin's decision): optional credit-billed model launches like `vibe --fable`, which warn, quote the rates, and default to No; the `/vs` escalation ladder must likewise ask before any credit-billed rung. Everything else defers until Anthropic ships a path that runs against subscription quota. See `TODO.md` Done block for the cloud-runner dismissal record.
