# vibe

A single-command containerised Claude Code environment. `cd my-project && vibe` and you're in.

## What you get

- Claude Code running in Anthropic's official devcontainer, with its firewall whitelist in place.
- Claude Pro/Max subscription auth (no API key / no metered billing).
- A per-repo fine-grained GitHub PAT injected as `$GITHUB_TOKEN` and wired into git — `git push` just works.
- SSH out to remote dev machines using your host `~/.ssh` keys (mounted read-only).
- One-time approvals: log in to Claude once, add a PAT once per repo, never asked again.

## Prerequisites

- macOS 13+ or Linux
- [OrbStack](https://orbstack.dev) (recommended, lighter) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Node.js, then `npm install -g @devcontainers/cli`
- [GitHub CLI](https://cli.github.com) — `gh auth login`
- A Claude **Pro or Max** subscription

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
```

The installer clones vibe to `~/.vibe-src`, symlinks `~/bin/vibe`, copies the devcontainer definition to `~/.vibe/devcontainer/`, and prompts for your projects directory.

## Usage

```bash
# From inside a project folder
cd ~/Projects/my-app
vibe

# By project name from anywhere (uses VIBE_PROJECTS_DIR)
vibe my-app

# Force rebuild of the container image
vibe --rebuild

# List available projects
vibe --list
```

## Authentication

vibe uses your **Claude Pro/Max subscription** — no API key required, no per-token billing.

On the first run Claude Code will print a URL in the terminal; open it in your browser and log in. Credentials are stored in a named Docker volume (`vibe-claude-config`) that is shared across all projects, so you log in **once**, not once per project.

> **Note:** if `ANTHROPIC_API_KEY` is set in your environment, vibe prints a warning. The container still forces subscription auth via `forceLoginMethod: "claudeai"`, but you should unset the variable on the host for good measure.

## First-run flows

### Project with an existing GitHub repo
vibe detects the remote, checks `~/.vibe/tokens` for a saved PAT, and if none is found walks you through creating a [fine-grained Personal Access Token](https://github.com/settings/personal-access-tokens/new) scoped to just that repo. The token is saved and never asked for again.

### Project with no GitHub repo
```
No GitHub repo found for this project.
Create a GitHub repo for it? [Y/n/never]
```
- **Y** — prompts for name, public/private, description; creates the repo via `gh`; then does PAT setup
- **n** — skips this time, asks again next run
- **never** — remembers permanently (stored in `~/.vibe/skipped`), never asks again

### Empty folder / new project
vibe handles `git init` and an initial commit automatically before pushing to GitHub.

## GitHub token permissions

When creating a fine-grained PAT, vibe needs:

| Permission | Level |
|---|---|
| Contents | Read and write |
| Metadata | Read-only (auto-selected) |
| Pull requests | Read and write |

Set **Repository access** to *Only select repositories* and choose just the repo you're working on.

## File layout

| Path | Purpose | Synced? |
|---|---|---|
| `~/bin/vibe` | Symlink to the launcher | Up to you |
| `~/.vibe-src/` | Clone of this repo | git-managed |
| `~/.vibe/config` | `VIBE_PROJECTS_DIR` | ❌ keep local |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`) | ❌ keep local |
| `~/.vibe/skipped` | Projects opted out of GitHub | ❌ keep local |
| `~/.vibe/devcontainer/` | Vendored devcontainer def used by `--override-config` | ❌ keep local |

Docker-side state lives in two named volumes:

| Volume | Contents |
|---|---|
| `vibe-claude-config` | `/home/node/.claude` — Claude Pro auth (shared across all vibe projects) |
| `vibe-bash-history`  | `/commandhistory` — shell history |

> **Security:** `~/.vibe/tokens` is `chmod 600`. Never commit or sync it to the cloud.

## How it's built

vibe wraps Anthropic's [reference devcontainer for Claude Code](https://github.com/anthropics/claude-code/tree/main/.devcontainer), lightly patched to:
- share Claude auth across projects (one login, not one-per-project)
- mount your host `~/.ssh` and `~/.gitconfig` read-only
- inject a per-repo GitHub PAT via a git credential helper

Launch uses [`@devcontainers/cli`](https://github.com/devcontainers/cli) with `--override-config` so you never have to commit `.devcontainer/` into each project.

## Security model

- **Network:** iptables firewall allows only npm, GitHub, Claude API, DNS, SSH. No other outbound traffic.
- **GitHub:** fine-grained PAT scoped to one repo — if Claude goes rogue, blast radius is one repo.
- **Host FS:** only the project folder, `~/.ssh` (ro), and `~/.gitconfig` (ro) are mounted in.
- **Claude Pro credentials:** sit in a named Docker volume, not bind-mounted from the host — a compromised container can't leak host credentials unless the firewall is breached.

## License

MIT
