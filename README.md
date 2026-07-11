# vibe

A single-command containerised Claude Code environment. `cd my-project && vibe` and you're in.

## What you get

- Claude Code in Anthropic's official devcontainer, firewall whitelist in place.
- One-time Claude **Pro/Max** subscription auth — no API key, no per-token billing.
- One-time per-repo fine-grained GitHub PAT injected as `$GITHUB_TOKEN`; `git push` just works.
- SSH out to remote dev machines (Raspberry Pis, lab boxes, anything you've keyed). Host `~/.ssh` is bind-mounted read-only; a sanitised writable copy lives inside the container.
- Opt-in cross-org learning library via `vibe learn --init` — you pick where it lives, public or private. Capture is manual; auto-promotion is planned. **Security note:** the bind-mount is read-write on macOS regardless of the `readonly` flag (Docker Desktop / OrbStack `fakeowner` quirk), so a PreToolUse hook gates writes — every Write, Edit, or MultiEdit touching `/learnings` prompts for confirmation. Bash redirects, `tee`, `cp`, `mv`, `rm` etc. are hooked too as defense-in-depth (acknowledged bypass classes in `devcontainer/guard-bash.sh`).
- Slash commands, subagents, and Stop hooks pre-installed. Type `/help` once inside to discover them; `/sp` applies Superpowers methodology, `/vs` runs an adversarial coding harness (see below), `/vss` and `/vsss` automate it. Anything unfamiliar surfaces a one-liner when you first hit it.
- House rules baked into every Claude session via a managed `~/.claude/CLAUDE.md` block — among them: try WebSearch before declaring a URL unreachable, and ask before SSHing out of the container (set `VIBE_SSH_AUTO=1` in `~/.vibe/config`, or `touch .vibe-allow-ssh` in a project, to opt into autonomous SSH per project).
- **Shared repos** (in flight, cycle 3 of 4 landed): declare a private repo your public project needs live cross-repo access to in a committed `.vibe-repos` file (`owner/repo [ro|rw]`, one per line); `vibe repos add [--rw] owner/repo /path/to/local/checkout` registers where it actually lives on THIS machine (`~/.vibe/repos`, never committed), authorises it for THIS project (`~/.vibe/repos-acks` — a PR editing `.vibe-repos` alone can never mount anything), and mints the repo its own single-repo PAT. It mounts at `/repos/<name>` on the next launch — read-only by default; an `rw` intent is refereed by a per-session single-writer lock in the shared checkout, so two projects can never both write (contention falls back to ro with a loud header line naming the holder). `/repo claim` in a read-only session files a handoff request the rw holder sees in its status line; the holder exits, you relaunch, the lock is yours. Projects with shared repos also get a managed CLAUDE.md fragment teaching the session the seam discipline: code under `/repos/*` is proprietary, never copied into `/workspace`, consumed only via the project's declared interface/feature-flag seam. Community contributors who never registered the repo see nothing at all; a registered-but-broken one (missing checkout, missing token) warns loudly instead of failing silently. `vibe repos list` / `vibe repos remove [--purge]` round it out. Per-repo credential routing (each repo pushed with its own PAT via `credential.useHttpPath`) is the final cycle.

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
bash <(curl -fsSL https://raw.githubusercontent.com/andeyePro/vibe/main/install.sh)
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
- `vibe --fable` — launch this session on Claude Fable 5 (billing-aware, see below)
- `vibe --model <id>` — launch this session on any Claude model id
- `vibe learn --init` — one-time setup of the cross-org learning library
- `vibe repos add <owner/repo> [path]` — register a private repo this machine mounts read-only at `/repos/<name>` for every project that declares it (`vibe repos list` / `vibe repos remove [--purge]` manage it; see Shared repos above)

Fresh conversation is the default — durable memory lives in `TODO.md`, `CLAUDE.md`, and Claude's auto-memory, not in resumed conversations (which accumulate compaction debt). `--continue` / `--resume` are opt-in for short-horizon pickup.

### Model selection and Fable 5

`--fable` and `--model <id>` apply per-launch; they don't change the default model Claude Code has persisted in its shared config volume. Set a standing default with `VIBE_MODEL="<id>"` in `~/.vibe/config` (flags win over config). Inside a session, `/model` still works as usual.

Fable 5 is billing-aware: since 8 Jul 2026 it bills usage credits at API list rates ($10/MTok in, $50/MTok out) on top of your subscription. That collides with vibe's subscription-only-spend default, so `--fable` asks before launching (default No, falling back to your default model). Standing opt-in: `VIBE_FABLE_CREDITS_OK=1` in `~/.vibe/config`. Anthropic has said it intends to fold Fable 5 back into subscriptions once capacity allows — the gate can be revisited then.

Getting the most from Fable 5 on a subscription: reserve it for genuinely huge or ambiguous tasks — its edge concentrates in long-horizon complex work, and on small scoped calls Opus is near-parity at zero extra cost. Two placements pay: `vibe --fable` as the session lead for a big ambiguous run, or the `/vs` escalation ladder's top rung (Fable as Generator on a locked spec — compact brief, fresh context, one-shot strength). Either way the mechanical work stays on subscription tiers — `/vs` pins Sonnet/Haiku for its worker roles, `code-writer` and `shellcheck-fixer` pin Sonnet. `/diet` composes well with a Fable session for the same reason.

### Overnight auto-resume

`/vsss --sessions X` (inside a session) runs an autonomous loop across up to X five-hour credit windows total, by writing a `.vss/auto-resume` marker. If the session dies — typically 5-hour-window credit exhaustion — the launcher notices the active marker after `claude` exits, counts down to the estimated window reset (Ctrl-C cancels; deleting the marker deactivates), then relaunches `claude --continue "/vsss --resume"`, up to X-1 times. The `/vsss` loop clears the marker whenever it exits cleanly, so finished runs never relaunch. (The flag was `--auto-resume N` — N extra windows — until 2026-07-08.)

### Budget visibility

`/budget` (inside any session) reports month-to-date tokens per model across all vibe sessions on this machine, with estimated Fable 5 credit spend at list rates. Estimates, not invoices — the authoritative credit balance is the Anthropic console.

## Host-side state

| Path | Purpose |
|---|---|
| `~/bin/vibe` | Symlink to the launcher |
| `~/.vibe-src/` | Clone of this repo |
| `~/.vibe/config` | `VIBE_PROJECTS_DIR`, `VIBE_SSH_AUTO` (opt-in: `=1` skips the per-action SSH ask in all projects), `VIBE_BRAIN2_PATH` / `VIBE_ZOTERO_PATH` (shared brain2 at `/brain2` rw + Zotero at `/zotero` ro; default `~/brain2` / `~/Zotero/storage`, mounted into every container when the dir exists, `=off` to disable), `VIBE_MODEL` (default model id for every launch; flags win), `VIBE_FABLE_CREDITS_OK` (`=1` skips the Fable 5 usage-credits confirm from 8 Jul 2026), `VIBE_GITHUB_OWNER` (default owner — personal account or org — offered when vibe creates a new repo; you can still type a different owner at the prompt) |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`); optional `ZOTERO_API_KEY=...` line (slash-free key → no collision with a repo entry) surfaced in-container as `$ZOTERO_API_KEY` for direct Zotero web-API calls. A shared repo's PAT lives here too, keyed by its slug — same store, same `chmod 600`. Never commit or sync to the cloud |
| `~/.vibe/repos` | Shared-repo machine registry (`owner/repo=/local/path`), `chmod 600`. Written by `vibe repos add`; per-machine, so two Macs sharing a project each register their own local checkout path |
| `~/.vibe/skipped` | Projects opted out of GitHub |
| `~/.vibe/learning.config` | Learning library location + visibility |

## Security model

- **Network:** iptables firewall allows only an allowlist of hosts a coding session needs (GitHub, npm, Anthropic, VS Code marketplace, a few opt-in extras — the list is `devcontainer/init-firewall.sh`), plus DNS and outbound SSH.
- **GitHub:** fine-grained PAT scoped to one repo — if Claude goes rogue, blast radius is one repo.
- **Host FS:** only the project folder, `~/.ssh` (ro), and `~/.gitconfig` (ro) are mounted in.
- **Claude Pro credentials:** in a named Docker volume (`vibe-claude-config`), not bind-mounted from the host — a compromised container can't leak host credentials unless the firewall is breached.
- **Built on Anthropic's [reference devcontainer for Claude Code](https://github.com/anthropics/claude-code/tree/main/.devcontainer)**, lightly patched (shared Claude auth across projects; read-only `~/.ssh` and `~/.gitconfig`; per-repo PAT via a git credential helper). Launches via [`@devcontainers/cli`](https://github.com/devcontainers/cli) with `--override-config` so you never commit `.devcontainer/` into each project.

<!-- task_017 C2: fold this subsection into C1's "Shared repos" README section at integration -->
### Shared repos: write access (`rw`)

A shared repo declared `rw` in `.vibe-repos` (set it with `vibe repos add --rw <owner/repo>`) mounts read-write only when this launch wins the repo's single-writer lock — one writer per shared checkout per machine, refereed by an atomic lock directory at `<checkout>/.vibe-signals/rw-lock.d/`. If another live vibe session already holds it, the launch header names the holding project and since-when, and the repo falls back to a read-only mount for this session; exit the holder (the lock releases on exit) and relaunch to take over. A crashed holder is handled automatically: the next rw launch sees the dead pid and reclaims the stale lock. Mount modes are fixed at container creation, so a handoff is always exit-and-relaunch, never live.

## Coming soon

In flight or specced; no firm dates.

- **Language-profile presets** — `vibe --profile python` or auto-detect from `pyproject.toml` / `package.json` / `Cargo.toml`, so the container ships with the toolchain your project needs already in place.
- **`vibe --TDD` session mode** — enforces test-driven discipline across the whole project. Composes with `/vs`. Part of an XP-as-umbrella direction (TDD and spec-first as in-scope subsets).
- **Per-repo Ghostty window titles** — so several vibe windows don't all read "Claude Code".

## Versioning and releases

`vibe --version` prints the current version, read from the `VERSION` file at the repo root. Releases are source-only for now (install via `install.sh` or a git clone). Maintainer release steps are in [`RELEASING.md`](RELEASING.md).

## Contributing

Contribute to vibe using vibe — clone it, `./install.sh` (or symlink `~/bin/vibe` at the clone), then `vibe` in the repo and open PRs against `main`. Run `python3 code-check.py` and `python3 smoke-test.py` before a PR. Full guide in [`CONTRIBUTING.md`](CONTRIBUTING.md); merged contributors are recorded in [`CONTRIBUTORS.md`](CONTRIBUTORS.md), the ledger andeye's revenue-share promise operates on.

**Not a developer?** Ask your Claude to look at [our CLAUDE.md](https://github.com/andeyePro/vibe/blob/main/CLAUDE.md) and take you through the vibe onboarding process.

## License

[MIT](LICENSE). We considered AGPL-3.0 + CLA and set it aside — for a dev tool, MIT's freedom to adopt and contribute wins. Nothing extra to sign. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

[Martin](https://github.com/Aqueum)'s input, lovingly crafted in Scotland with [vibe](https://github.com/andeyePro/vibe).
