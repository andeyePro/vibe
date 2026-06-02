# vibe

A single-command containerised Claude Code environment. `cd my-project && vibe` and you're in.

## What you get

- Claude Code in Anthropic's official devcontainer, firewall whitelist in place.
- One-time Claude **Pro/Max** subscription auth — no API key, no per-token billing.
- One-time per-repo fine-grained GitHub PAT injected as `$GITHUB_TOKEN`; `git push` just works.
- SSH out to remote dev machines (Raspberry Pis, lab boxes, anything you've keyed). Host `~/.ssh` is bind-mounted read-only; a sanitised writable copy lives inside the container.
- Opt-in cross-org learning library via `vibe learn --init` — you pick where it lives, public or private. Capture is manual; auto-promotion is planned. **Security note:** the bind-mount is read-write on macOS regardless of the `readonly` flag (Docker Desktop / OrbStack `fakeowner` quirk), so a PreToolUse hook gates writes — every Write, Edit, or MultiEdit touching `/learnings` prompts for confirmation. Bash redirects, `tee`, `cp`, `mv`, `rm` etc. are hooked too as defense-in-depth (acknowledged bypass classes in `devcontainer/guard-bash.sh`).
- Slash commands, subagents, and Stop hooks pre-installed. Type `/help` once inside to discover them; `/sp` applies Superpowers methodology, `/vs` runs an adversarial coding harness (see below), `/vss` and `/vsss` automate it. Anything unfamiliar surfaces a one-liner when you first hit it.
- Two house rules baked into every Claude session via a managed `~/.claude/CLAUDE.md` block: try WebSearch before declaring a URL unreachable, and ask before SSHing out of the container (set `VIBE_SSH_AUTO=1` in `~/.vibe/config`, or `touch .vibe-allow-ssh` in a project, to opt into autonomous SSH per project).

## Adversarial coding mode `/vs`

`/vs <prompt>` runs the request through an adversarial harness so a Pro/Max plan does more per session with less back-and-forth. An Opus director plays Planner and Evaluator, dispatching independent subagents (Sonnet Spec Critic before any code, Sonnet Generator, Haiku Tester writing immutable tests, or a Sonnet Reviewer when you pass `--fuzzy` for non-mechanical criteria). Generator never sees Tester's tests and vice versa — independence is the point.

`/vs` extends Claude Code's canonical Software Architect / Code Writer / Code Reviewer pattern: Architect splits into Planner + Spec Critic, Reviewer splits into Tester (mechanical) or Reviewer (`--fuzzy`) + Evaluator. Full mapping and flag reference in [`devcontainer/commands/vs.md`](devcontainer/commands/vs.md).

## Prerequisites

- macOS 13+ or Linux (Linux untested; open an issue if you hit anything)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [OrbStack](https://orbstack.dev)
- Node.js, then `npm install -g @devcontainers/cli`
- [GitHub CLI](https://cli.github.com) — `gh auth login`
- A Claude **Pro or Max** subscription

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
```

The installer clones vibe to `~/.vibe-src`, symlinks `~/bin/vibe`, and prompts for your projects directory. `vibe` reads the devcontainer definition straight from the clone, so `git -C ~/.vibe-src pull` (or re-running the installer) is all you need to update.

**Hacking on vibe itself?** Clone the repo anywhere and run `./install.sh` from inside the clone — the installer detects the in-place checkout and points `~/bin/vibe` at it directly, so your edits take effect with no separate pull step.

## Usage

`cd` into a project and run `vibe`. First-run teaching happens interactively: GitHub repo detection, fine-grained PAT creation, `git init` for empty folders, the Pro/Max login URL. Nothing to read up on in advance.

`vibe --help` shows the full flag list. Common ones:

- `vibe my-app` — launch a named project from anywhere (uses `VIBE_PROJECTS_DIR`)
- `vibe --rebuild` — force rebuild of the container image
- `vibe --continue` — resume the most recent Claude conversation in this project
- `vibe --resume <uuid>` — resume a specific past conversation
- `vibe learn --init` — one-time setup of the cross-org learning library

Fresh conversation is the default — durable memory lives in `TODO.md`, `CLAUDE.md`, and Claude's auto-memory, not in resumed conversations (which accumulate compaction debt). `--continue` / `--resume` are opt-in for short-horizon pickup.

## Host-side state

| Path | Purpose |
|---|---|
| `~/bin/vibe` | Symlink to the launcher |
| `~/.vibe-src/` | Clone of this repo |
| `~/.vibe/config` | `VIBE_PROJECTS_DIR`, `VIBE_SSH_AUTO` (opt-in: `=1` skips the per-action SSH ask in all projects), `VIBE_BRAIN_PATH` / `VIBE_ZOTERO_PATH` (shared brain at `/brain` rw + Zotero at `/zotero` ro; default `~/brain2` / `~/Zotero/storage`, mounted into every container when the dir exists, `=off` to disable) |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`), `chmod 600` — never commit or sync to the cloud |
| `~/.vibe/skipped` | Projects opted out of GitHub |
| `~/.vibe/learning.config` | Learning library location + visibility |

## Security model

- **Network:** iptables firewall allows only npm, GitHub, Claude API, DNS, SSH.
- **GitHub:** fine-grained PAT scoped to one repo — if Claude goes rogue, blast radius is one repo.
- **Host FS:** only the project folder, `~/.ssh` (ro), and `~/.gitconfig` (ro) are mounted in.
- **Claude Pro credentials:** in a named Docker volume (`vibe-claude-config`), not bind-mounted from the host — a compromised container can't leak host credentials unless the firewall is breached.
- **Built on Anthropic's [reference devcontainer for Claude Code](https://github.com/anthropics/claude-code/tree/main/.devcontainer)**, lightly patched (shared Claude auth across projects; read-only `~/.ssh` and `~/.gitconfig`; per-repo PAT via a git credential helper). Launches via [`@devcontainers/cli`](https://github.com/devcontainers/cli) with `--override-config` so you never commit `.devcontainer/` into each project.

## Coming soon

In flight or specced; no firm dates.

- **Language-profile presets** — `vibe --profile python` or auto-detect from `pyproject.toml` / `package.json` / `Cargo.toml`, so the container ships with the toolchain your project needs already in place.
- **`vibe --TDD` session mode** — enforces test-driven discipline across the whole project. Composes with `/vs`. Part of an XP-as-umbrella direction (TDD and spec-first as in-scope subsets).
- **Green-AI backend option** — a route to a transparent-carbon model (GreenPT, Mistral, or self-hosted) for users who'd rather see published mWh-per-100-tokens than nothing.
- **Per-repo Ghostty window titles** — so several vibe windows don't all read "Claude Code".

## License

[MIT](LICENSE)

---

[Martin](https://github.com/Aqueum)'s input, lovingly crafted in Scotland with [vibe](https://github.com/Aqueum/vibe).
