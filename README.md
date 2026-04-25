# vibe

A single-command containerised Claude Code environment. `cd my-project && vibe` and you're in.

## What you get

- Claude Code running in Anthropic's official devcontainer, with its firewall whitelist in place.
- One-time Claude Pro/Max subscription auth (no API key required / no metered billing).
- One-time per-repo fine-grained GitHub Personal Access Token (PAT) injected as `$GITHUB_TOKEN` and wired into git – `git push` just works.
- SSH out to remote dev machines (Raspberry Pis, lab boxes, anything you've already keyed). Your host `~/.ssh` bind-mounts read-only – a sanitised writable copy lives inside the container so `known_hosts` prompts and `ssh-keygen` work normally, while your host keys stay untouched.
- An opt-in cross-org learning library (`vibe learn --init`) – you choose where it lives, public or private, and capture patterns from any project. Mounts read-only into every container at `/learnings` so Claude can reference your accumulated notes without write access.
- Two house rules baked into every Claude session via a managed `~/.claude/CLAUDE.md` block – try WebSearch before declaring a URL unreachable, and don't SSH/scp/rsync out of the container without explicit per-turn user approval. Both ship with vibe; no per-user setup.
- Slash commands include `/c` (copy the most recent fenced code block from Claude's last reply to your Mac clipboard via a host-side watcher; Linux hosts fall back to a scratch file under `.vibe/copy-latest.txt`), `/diet` (lean token-frugal mode – no subagents, no optional verifications, terse output), `/feast` to exit `/diet`, and `/vs` (see [Adversarial coding mode](#adversarial-coding-mode-vs) below). Subagents include `shellcheck-fixer` and `security-review`. All pre-installed under `~/.claude/`, synced on every container start so image rebuilds propagate without clobbering anything you've added yourself.

## Adversarial coding mode `/vs`

To maximise Pro/Max plan usage efficiency and minimise user input on complex tasks, `/vs <prompt>` runs the request through an adversarial harness. An Opus director plays Planner and Evaluator, dispatching independent subagents:
1. a Sonnet Spec Critic that audits the spec before any code is written, 
2. a Sonnet Generator that writes the feature
3. a Haiku Tester that writes immutable tests, or 
4. a Sonnet Reviewer with `/vs --fuzzy` for tasks without mechanical acceptance criteria
Generator never sees Tester's output and vice versa – that separation is the point by having independent adversarial agents none of them over-value the work of the others, and you get a completed feature that passes all tests.

Flags: `--max N` (limits number of iterations), `--fuzzy` (Reviewer instead of Tester), `--cost` (opt-in token-spend logging). See full protocol in [`devcontainer/commands/vs.md`](devcontainer/commands/vs.md).

## Prerequisites

- macOS 13+ or Linux (not yet tested on Linux) add an issue if you need other platforms
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [OrbStack](https://orbstack.dev)
- Node.js, then `npm install -g @devcontainers/cli`
- [GitHub CLI](https://cli.github.com) – `gh auth login`
- A Claude **Pro or Max** subscription

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
```

The installer clones vibe to `~/.vibe-src`, symlinks `~/bin/vibe`, and prompts for your projects directory. `vibe` reads the devcontainer definition straight from the clone, so `git -C ~/.vibe-src pull` (or re-running the installer) is all you need to update.

**Hacking on vibe itself?** Clone the repo anywhere you like and run `./install.sh` from inside the clone – the installer detects the in-place checkout and points `~/bin/vibe` at it directly, so your edits take effect with no separate pull step.

## Usage

```bash
# From inside a project folder
cd ~/Projects/my-app
vibe

# By project name from anywhere (uses VIBE_PROJECTS_DIR)
vibe my-app

# Force rebuild of the container image
vibe --rebuild

# Resume the most recent Claude conversation in this project
vibe --continue

# Interactively pick a past Claude conversation to resume
vibe --resume

# Resume a specific Claude conversation by session id
vibe --resume 12345678-1234-1234-1234-123456789abc

# List available projects
vibe --list

# Cross-org learning library (host-side, opt-in)
vibe learn --init                    # one-time setup; choose location + visibility
vibe learn "pattern worth keeping"   # capture from your projects, with confirm
vibe learn --exclude                 # opt this project out
vibe learn --include                 # opt this project back in
```

`vibe` starts a fresh Claude conversation by default – durable cross-session memory lives in `TODO.md`, `CLAUDE.md`, and Claude's auto-memory, not in resumed conversations (which accumulate compaction debt). `--continue`/`--resume` are opt-in for short-horizon pickup (mid-task resumption, debugging a prior session).

## Authentication

vibe uses your **Claude Pro/Max subscription** – no API key required, no per-token billing.

On the first run Claude Code will print a URL in the terminal; open it in your browser and log in. Credentials are stored in a named Docker volume (`vibe-claude-config`) that is shared across all projects, so you log in **once**, not once per project.

> **Note:** if `ANTHROPIC_API_KEY` is set in your environment, vibe prints a warning. The container still forces subscription auth via `forceLoginMethod: "claudeai"`, but you should unset the variable on the host for good measure.

## First-run flows

First-time setup is interactive – vibe walks you through GitHub repo detection, fine-grained PAT creation, and `git init` as needed. Existing GitHub repos: it'll find them. New projects: it offers to create the repo for you. Empty folders: it'll `git init` first.

## Host-side state

| Path | Purpose |
|---|---|
| `~/bin/vibe` | Symlink to the launcher |
| `~/.vibe-src/` | Clone of this repo |
| `~/.vibe/config` | `VIBE_PROJECTS_DIR` |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`), `chmod 600` – never commit or sync to the cloud |
| `~/.vibe/skipped` | Projects opted out of GitHub |
| `~/.vibe/learning.config` | Learning library location + visibility (created by `vibe learn --init`) |

## Security model

- **Network:** iptables firewall allows only npm, GitHub, Claude API, DNS, SSH. No other outbound traffic.
- **GitHub:** fine-grained PAT scoped to one repo – if Claude goes rogue, blast radius is one repo.
- **Host FS:** only the project folder, `~/.ssh` (ro), and `~/.gitconfig` (ro) are mounted in.
- **Claude Pro credentials:** sit in a named Docker volume (`vibe-claude-config`), not bind-mounted from the host – a compromised container can't leak host credentials unless the firewall is breached.
- **Built on Anthropic's [reference devcontainer for Claude Code](https://github.com/anthropics/claude-code/tree/main/.devcontainer)**, lightly patched (shared Claude auth across projects; read-only `~/.ssh` and `~/.gitconfig`; per-repo PAT via a git credential helper). Launches via [`@devcontainers/cli`](https://github.com/devcontainers/cli) with `--override-config` so you never commit `.devcontainer/` into each project.

## Coming soon

In flight or specced; no firm dates.

- **Language-profile presets** – `vibe --profile python` or auto-detect from `pyproject.toml` / `package.json` / `Cargo.toml`, so the container ships with the toolchain your project needs already in place rather than relying on host installs.
- **`vibe --TDD` session mode** – enforces test-driven discipline across the whole project: implementation edits are blocked unless a newer test edit with a recently-observed failing assertion exists. Composes with `/vs`.
- **Green-AI backend option** – a route to a transparent-carbon model (GreenPT, Mistral, or self-hosted) for users who'd rather see published mWh-per-100-tokens than nothing. Subject to a workable tool-calling shape that keeps the agent loop intact.
- **Plain-English `/vs` output** – a `--plain` flag and a 0–9 verbosity knob for spec / tests / verdict, so review passes are skim-friendly without losing the techy mode for power users.
- **Auto-copy of the last fenced block at end of turn** – a Stop hook that does what `/c` does today, with no slash-command round-trip. Pending a design call on the privacy / surprise tradeoff (every block, or marker-based opt-in per turn).
- **Per-repo Ghostty window titles** – so several vibe windows don't all read "Claude Code". Mac-host wrapper fix in flight; in-repo OSC-intercept fallback if needed.

## License

MIT

---

[Martin](https://github.com/Aqueum)'s input, lovingly crafted in Scotland with [vibe](https://github.com/Aqueum/vibe).