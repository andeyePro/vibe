# vibe

A single-command, containerised YOLO coding environment for Claude Code. `cd project && vibe` launches an isolated Docker container with Claude Code pre-authenticated against the user's Claude Pro/Max subscription, a per-repo fine-grained GitHub PAT, and outbound SSH to remote dev machines.

## Project context

- Script: `./vibe` (bash) — the entrypoint users invoke as `vibe`.
- Container: Anthropic's official Claude Code devcontainer, vendored under `devcontainer/` with vibe-specific patches (openssh-client, shellcheck, credential helper, firewall tweaks, mDNS, env hint, PreToolUse/Stop hooks, curated agents/commands sync).
- Shipped extras: `devcontainer/commands/` (/diet, /feast, /vs) and `devcontainer/agents/` (shellcheck-fixer, security-review). Synced into the persistent `~/.claude/` volume by `install-claude-extras.sh` on every container start; user-authored files in the same dirs are left alone.
- Target users: macOS primary (tested on Darwin), Linux secondary. Uses OrbStack or Docker Desktop.
- Auth model: Claude Pro/Max subscription (never API key); GitHub fine-grained PAT per repo (blast-radius argument — each container can only touch one repo).

## Testing

- `python3 code-check.py` — shellcheck over `vibe` + all `.sh` files. Fast. Run on every change. Add `--json` for machine-readable output (single JSON object on stdout: `tool`, `shellcheck_version`, `files_checked`, `findings`, `summary`).
- `python3 smoke-test.py` — host-side black-box tests (no docker, no network). Fast. Covers `--help`, write-env-hint block management, token helpers.
- `MANUAL-TESTS.md` — end-to-end checklist for container lifecycle behaviour (auto-rebuild, partial-fail retry, SSH, bind mounts). Run before shipping changes that touch the Dockerfile, devcontainer.json, postStartCommand, or the vibe launcher.

## TODO.md

`TODO.md` is this project's canonical backlog and audit log. Keep it honest — don't quietly drop items.

- **Plan step:** when the user approves a plan or you break work into discrete tasks, append them under `## Open` in `TODO.md` with a one-line description. Markers: `[ ]` open · `[x]` done · `[!]` failed/abandoned.
- **Review step:** when closing a task, move it to `## Done` with a one-line note on what was done (or the final commit SHA). If a task failed or was abandoned, mark it `[!]` with a one-line note on what was tried and why it didn't work — that failure memory is the point.
- Keep entries bullet-sized. Commit TODO.md updates alongside the code change that resolves (or creates) the task, so history stays paired.
- TODO.md is for persistent, cross-session work tracking — distinct from in-session `TaskCreate` todos, which are ephemeral scratchpad.

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
- **Anything that bills against API rates or extended credits separately from the user's Pro/Max subscription.** If a feature requires the Anthropic API (e.g. Claude Agent SDK, cloud/async agent runners as they exist today), it stays out of vibe core — the project is for Pro/Max subscribers who do not want to pay extra. Defer such features until Anthropic ships a path that runs against subscription quota. See `TODO.md` Done block for the cloud-runner dismissal record.
