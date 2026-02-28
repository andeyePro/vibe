# vibe

A thin wrapper around [ClaudeBox](https://github.com/RchGrav/claudebox) that makes per-project YOLO vibe coding sessions as simple as `cd my-project && vibe`.

- **Detects your GitHub remote automatically** — no arguments needed
- **Walks you through fine-grained PAT setup** on first use per repo, then remembers
- **Offers to create a GitHub repo** if none exists, including for empty folders
- **Works with Dropbox** (or any directory) — mount your project folder directly
- **Never nags** — answer `never` once and a project is quietly skipped forever

## How it works

```
cd my-project
vibe
```

That's it. On first run for a repo, `vibe` walks you through any setup it needs. Every subsequent run goes straight in.

## Prerequisites

- macOS (tested) / Linux (should work)
- [ClaudeBox](https://github.com/RchGrav/claudebox) — `wget https://github.com/RchGrav/claudebox/releases/latest/download/claudebox.run && chmod +x claudebox.run && ./claudebox.run`
- A Docker backend — [OrbStack](https://orbstack.dev) (recommended, lighter) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [GitHub CLI](https://cli.github.com) (`gh`) — for repo creation and auth
- `ANTHROPIC_API_KEY` set in your environment

## Installation

```bash
# 1. Clone or download vibe
git clone https://github.com/Aqueum/vibe.git ~/.vibe-src

# 2. Symlink the script onto your PATH
ln -sf ~/.vibe-src/vibe ~/bin/vibe   # or /usr/local/bin/vibe

# 3. Create your config (sets your projects directory)
mkdir -p ~/.vibe
cat > ~/.vibe/config <<'EOF'
VIBE_PROJECTS_DIR="$HOME/Projects"   # adjust to your projects folder
EOF

# 4. Add your Anthropic key to ~/.zshrc or ~/.bashrc if not already set
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc
```

## Usage

```bash
# From inside a project folder
cd ~/Projects/my-app
vibe

# By project name from anywhere (uses VIBE_PROJECTS_DIR)
vibe my-app

# Force rebuild of the ClaudeBox image
vibe --rebuild

# List available projects
vibe --list
```

## First-run flows

### Project with an existing GitHub repo
`vibe` detects the remote, checks `~/.vibe/tokens` for a saved PAT, and if none is found walks you through creating a [fine-grained Personal Access Token](https://github.com/settings/personal-access-tokens/new) scoped to just that repo. The token is saved and never asked for again.

### Project with no GitHub repo
```
No GitHub repo found for this project.
Create a GitHub repo for it? [Y/n/never]
```
- **Y** — prompts for name, public/private, description; creates the repo via `gh`; then does PAT setup
- **n** — skips this time, asks again next run
- **never** — remembers permanently (stored in `~/.vibe/skipped`), never asks again

### Empty folder / new project
`vibe` handles `git init` and an initial commit automatically before pushing to GitHub.

## File layout

| Path | Purpose | Synced? |
|---|---|---|
| `~/bin/vibe` | Symlink to the script | Up to you |
| `~/.vibe/config` | Your `VIBE_PROJECTS_DIR` | ❌ keep local |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`) | ❌ keep local |
| `~/.vibe/skipped` | Projects opted out of GitHub | ❌ keep local |

> **Security:** `~/.vibe/tokens` is `chmod 600` and should never be committed or synced to the cloud.

## GitHub token permissions

When creating a fine-grained PAT, `vibe` needs:

| Permission | Level |
|---|---|
| Contents | Read and write |
| Metadata | Read-only (auto-selected) |
| Pull requests | Read and write |

Set **Repository access** to *Only select repositories* and choose just the repo you're working on.

## Why fine-grained PATs?

Inside a ClaudeBox YOLO session Claude has full execution permissions. A fine-grained PAT scoped to a single repo limits the blast radius — if something goes wrong, Claude can only affect that one repo, not your entire GitHub account.

## License

MIT
