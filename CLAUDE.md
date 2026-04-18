# vibe

A single-command, containerised YOLO coding environment for Claude Code. `cd project && vibe` launches an isolated Docker container with Claude Code pre-authenticated against the user's Claude Pro/Max subscription, a per-repo fine-grained GitHub PAT, and outbound SSH to remote dev machines.

## Project context

- Script: `./vibe` (bash) — the entrypoint users invoke as `vibe`.
- Current status: the repo is mid-modernisation. The old implementation wrapped `claudebox` (now stale; last commit Aug 2025). The rewrite drops `claudebox` and switches to Anthropic's official Claude Code devcontainer as the base.
- Target users: macOS primary (tested on Darwin), Linux secondary. Uses OrbStack or Docker Desktop.
- Auth model: Claude Pro/Max subscription (never API key); GitHub fine-grained PAT per repo (blast-radius argument — each container can only touch one repo).

## Current work

See **[PLAN.md](PLAN.md)** for the full implementation plan for the claudebox-removal rewrite. PLAN.md is the authoritative work list — it's structured in phases with exact file paths, contents, commands, and a test matrix. Work through it phase by phase; do not skip phases.

## Invariants (don't break these)

- `vibe` must work from any project folder with a single command, no arguments needed.
- GitHub credentials never leave the user's machine unencrypted beyond `~/.vibe/tokens` (chmod 600).
- Claude Code must use subscription auth (`forceLoginMethod: "claudeai"`), never fall back to `ANTHROPIC_API_KEY`.
- The container must run with `--dangerously-skip-permissions` safely — i.e. the firewall in `init-firewall.sh` is the backstop. Don't weaken the firewall.
- Fine-grained PATs are scoped to **one repo**; don't suggest workflows that need broader scopes.

## Non-goals

- Windows support (WSL is fine if Docker is installed, but no native Windows).
- Running containers on remote hosts (local container; Claude SSHes out if needed).
- Managing multiple parallel Claude sessions per project (dropped with claudebox).
