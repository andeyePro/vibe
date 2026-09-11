# Vibe&I

Vibe&I (the command is still `vibe`) is a single-command containerised Claude Code environment. `cd my-project && vibe` and you're in.

## What you get

- Claude Code in Anthropic's official devcontainer, firewall whitelist in place.
- One-time Claude **Pro/Max** subscription auth — no API key, no per-token billing.
- One-time per-repo fine-grained GitHub PAT injected as `$GITHUB_TOKEN`; `git push` just works.
- SSH out to remote dev machines (Raspberry Pis, lab boxes, anything you've keyed). Host `~/.ssh` is bind-mounted read-only; a sanitised writable copy lives inside the container.
- Opt-in cross-org learning library via `vibe learn --init` — you pick where it lives, public or private. Capture is manual; auto-promotion is planned. **Security note:** the bind-mount is read-write on macOS regardless of the `readonly` flag (Docker Desktop / OrbStack `fakeowner` quirk), so a PreToolUse hook gates writes — every Write, Edit, or MultiEdit touching `/learnings` prompts for confirmation. Bash redirects, `tee`, `cp`, `mv`, `rm` etc. are hooked too as defense-in-depth (acknowledged bypass classes in `devcontainer/guard-bash.sh`).
- Slash commands, subagents, and Stop hooks pre-installed. Type `/help` once inside to discover them; `/sp` applies Superpowers methodology, `/vs` runs an adversarial coding harness (see below), `/vss` and `/vsss` automate it, `/review` code-reviews any diff, `/ask` delegates a bulk task to another model, `/wide` and `/narrow` toggle how many agents run concurrently. Anything unfamiliar surfaces a one-liner when you first hit it.
- House rules baked into every Claude session via a managed `~/.claude/CLAUDE.md` block — among them: try WebSearch before declaring a URL unreachable, and ask before SSHing out of the container (set `VIBE_SSH_AUTO=1` in `~/.vibe/config`, or `touch .vibe-allow-ssh` in a project, to opt into autonomous SSH per project).
- **Shared repos**: declare a private repo your public project needs live cross-repo access to in a committed `.vibe-repos` file (`owner/repo [ro|rw]`, one per line); `vibe repos add [--rw] owner/repo /path/to/local/checkout` registers where it actually lives on THIS machine (`~/.vibe/repos`, never committed), authorises it for THIS project (`~/.vibe/repos-acks` — a PR editing `.vibe-repos` alone can never mount anything), and mints the repo its own single-repo PAT. It mounts at `/repos/<name>` on the next launch — read-only by default; an `rw` intent is refereed by a per-session single-writer lock in the shared checkout, so two projects can never both write (contention falls back to ro with a loud header line naming the holder). `/repo claim` in a read-only session files a handoff request the rw holder sees in its status line; the holder exits, you relaunch, the lock is yours. Projects with shared repos also get a managed CLAUDE.md fragment teaching the session the seam discipline: code under `/repos/*` is proprietary, never copied into `/workspace`, consumed only via the project's declared interface/feature-flag seam. Community contributors who never registered the repo see nothing at all; a registered-but-broken one (missing checkout, missing token) warns loudly instead of failing silently. `vibe repos list` / `vibe repos remove [--purge]` round it out. Per-repo credential routing means each repo is pushed with its own single-repo PAT (routed via `credential.useHttpPath`) — one repo's token can never touch another.

## Adversarial coding mode `/vs`

`/vs <prompt>` runs the request through an adversarial harness so a Pro/Max plan does more per session with less back-and-forth. An Opus director plays Planner and Evaluator, dispatching independent subagents (Sonnet Spec Critic before any code, Sonnet Generator, Haiku Tester writing immutable tests, or a Sonnet Reviewer when you pass `--fuzzy` for non-mechanical criteria). Generator never sees Tester's tests and vice versa — independence is the point.

`/vs` extends Claude Code's canonical Software Architect / Code Writer / Code Reviewer pattern: Architect splits into Planner + Spec Critic, Reviewer splits into Tester (mechanical) or Reviewer (`--fuzzy`) + Evaluator. Full mapping and flag reference in [`devcontainer/commands/vs.md`](devcontainer/commands/vs.md).

## Prerequisites

- macOS 13+ (primary) or Linux — see [Linux hosts](#linux-hosts) below
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [OrbStack](https://orbstack.dev)
- Node.js, then `npm install -g @devcontainers/cli`
- [GitHub CLI](https://cli.github.com) — `gh auth login`
- A Claude **Pro or Max** subscription

## Linux hosts

Reference platform: **Ubuntu 24.04 LTS with Docker Engine** (the `docker-ce`
repo), not Docker Desktop. Fedora/RHEL works the same way with `dnf`.

```bash
# Docker Engine — follow https://docs.docker.com/engine/install/ubuntu/
sudo apt-get install -y git nodejs npm gh
sudo npm install -g @devcontainers/cli
sudo usermod -aG docker $USER   # then log out and back in
gh auth login
bash <(curl -fsSL https://raw.githubusercontent.com/andeyePro/vibe/main/install.sh)
```

The installer runs three extra Linux checks: the Docker daemon is reachable,
your user is in the `docker` group, and `devcontainer` is on `PATH`. The group
check **warns rather than fails** — rootless Docker legitimately doesn't use
that group.

Two Linux-specific things to know:

- **`host.docker.internal`** is how anything in the container reaches the host.
  Docker Engine has no built-in name for the host, so vibe passes
  `--add-host=host.docker.internal:host-gateway` on every launch. This is the
  supported host path on Linux, and it also keeps the Mac build bridge and the
  OpenProject MCP forwarder working identically on both platforms.
- **`.local` (mDNS) names may not resolve.** The image ships
  `avahi-daemon`/`libnss-mdns`, but the Docker bridge NATs multicast, so a
  container's `.local` lookup depends on the host resolver. Install
  `avahi-daemon` on the host, or set `MulticastDNS=yes` in
  `/etc/systemd/resolved.conf` and restart `systemd-resolved`. vibe probes this
  once per machine at launch and warns with the remedy if it fails (marker:
  `~/.vibe/mdns-probe`; delete it to see the warning again). If you'd rather not
  bother, reach the host by `host.docker.internal` and LAN boxes by IP.

**Existing images need one cache-busted rebuild.** Images built before
2026-09-02 carry a duplicated `mdns4_minimal [NOTFOUND=return]` entry in
`/etc/nsswitch.conf` — the Dockerfile's `sed` wasn't idempotent. The fix only
lands on a real rebuild: run `vibe --rebuild` once (cache-busted, so the
nsswitch layer is actually re-run), then confirm with
`grep -c mdns4_minimal /etc/nsswitch.conf` inside the container, which must
print `1`.

Not covered on Linux: the Mac build bridge (below) is macOS-only, as is
`/c` clipboard support beyond Wayland/X11 — headless servers fall back to the
`.vibe/copy-latest.txt` scratch file.

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
- `vibe codex allow|deny|list [path]` — host-side, manage the machine's Codex login-mount consent registry (`~/.vibe/codex-allow`); `deny` also offers to stop that project's container so the login is unmounted at once (see Codex setup below)
- `vibe audit [--history|--staged]` — host-side, scans the current project's full git history (default) or its staged diff for secrets and PII the git-hook layer below can't retroactively catch (see Content guard below)

Fresh conversation is the default — durable memory lives in `TODO.md`, `CLAUDE.md`, and Claude's auto-memory, not in resumed conversations (which accumulate compaction debt). `--continue` / `--resume` are opt-in for short-horizon pickup.

### Model selection and Fable 5

`--fable` and `--model <id>` apply per-launch; they don't change the default model Claude Code has persisted in its shared config volume. Set a standing default with `VIBE_MODEL="<id>"` in `~/.vibe/config` (flags win over config). Inside a session, `/model` still works as usual.

Fable 5 is billing-aware: since 8 Jul 2026 it bills usage credits at API list rates ($10/MTok in, $50/MTok out) on top of your subscription. That collides with vibe's subscription-only-spend default, so `--fable` asks before launching (default No, falling back to your default model). Standing opt-in: `VIBE_FABLE_CREDITS_OK=1` in `~/.vibe/config`. Anthropic has said it intends to fold Fable 5 back into subscriptions once capacity allows — the gate can be revisited then.

Getting the most from Fable 5 on a subscription: reserve it for genuinely huge or ambiguous tasks — its edge concentrates in long-horizon complex work, and on small scoped calls Opus is near-parity at zero extra cost. Two placements pay: `vibe --fable` as the session lead for a big ambiguous run, or the `/vs` escalation ladder's top rung (Fable as Generator on a locked spec — compact brief, fresh context, one-shot strength). Either way the mechanical work stays on subscription tiers — `/vs` pins Sonnet/Haiku for its worker roles, `code-writer` and `shellcheck-fixer` pin Sonnet. `/diet` composes well with a Fable session for the same reason.

### Language profiles

A profile is a thin child image — `devcontainer/profiles/<name>/Dockerfile`, built `FROM` the base `vibe-dev:latest` image — that adds a language toolchain on top of the base container, never project dependencies. `vibe --profile python` builds (once, then caches) and launches on `vibe-dev:python`, which adds `python3`/`python3-venv`/`python3-pip`, `uv`, `ruff`, and `mypy`. `--profile none` launches on the plain base image and silences the suggestion below.

Astro, React and other JavaScript or TypeScript projects need no profile at all: the base image is already Node 20 with npm. Only the `python` profile ships today; the base build's context includes `profiles/`, which is harmless because the base Dockerfile has no `COPY .`.

Persistent selection, so you don't have to pass the flag every launch: put the profile name on the first line of `.vibe/profile` in the project (wins over config, loses to the flag), or set `VIBE_PROFILE="python"` in `~/.vibe/config` for a machine-wide default. Precedence, first hit wins: `--profile` flag → `.vibe/profile` → `VIBE_PROFILE`.

Custom profiles: drop a `Dockerfile` at `~/.vibe/profiles/<name>/Dockerfile` (same `ARG BASE=vibe-dev:latest` / `FROM ${BASE}` shape) and `vibe --profile <name>` picks it up — a shipped profile of the same name always wins on a clash. `vibe --profile <bogus-name>` exits with an error listing every profile actually available (shipped and custom).

Everything a profile installs happens at **build time**, before `init-firewall.sh` ever runs, so no firewall allowlist entry is needed for a profile's own installer traffic (the built image already has the toolchain baked in by the time the container's network lockdown starts). Astro/React projects need no profile at all — the base image is already Node 20 (`FROM node:20`). One incidental note: the base image's build context includes `devcontainer/profiles/` (there's no `.dockerignore`), which is harmless since the base `Dockerfile` has no `COPY .`, but worth knowing if the profiles directory grows large.

### Overnight auto-resume

`/vsss` (inside a session) runs an autonomous loop that persists across five-hour credit windows by default, by writing a `.vss/auto-resume` marker: it keeps going until the task is genuinely complete, not until the window runs out. If the session dies — typically 5-hour-window credit exhaustion — the launcher notices the active marker after `claude` exits, counts down to the estimated window reset (Ctrl-C cancels; deleting the marker deactivates), then relaunches `claude --continue "/vsss --resume"`. `--sessions X` caps the run at X windows total (X-1 relaunches); `--sessions 1` opts out of relaunch for a single-window run. The `/vsss` loop clears the marker whenever it exits cleanly, so finished runs never relaunch. (Unbounded-by-default since 2026-08-29; before that, omitting `--sessions` meant one window. The flag was `--auto-resume N` — N extra windows — until 2026-07-08.)

### Building on the Mac from inside a container (build bridge) — macOS-only

**macOS-only.** This section describes driving a *Mac* host over SSH from the container; there is no equivalent on a Linux host (nor a need for one — a Linux host's toolchain is generally installable in the image itself).

For projects whose build or test step must run on macOS (Xcode, Mac-only toolchains), a container can drive the Mac over SSH at `host.docker.internal`. The recurring setup, so the next project doesn't re-derive it (timeandeye's `mac-test.sh` is the working precedent):

1. **Enable Remote Login** on the Mac (System Settings → General → Sharing), scoped to the account the build should run as.
2. **Generate a workspace keypair** in-container (e.g. `ssh-keygen -t ed25519 -f /workspace/.vibe/mac-bridge -N ""`) and add the `.pub` to that account's `~/.ssh/authorized_keys` on the Mac — **restricted to the build**, not a full shell: prefix the line with `command="/path/to/build.sh",restrict` (`restrict` implies no-agent-forwarding/no-port-forwarding/no-pty), so the unencrypted key can only ever run the build. Revoke by deleting that `authorized_keys` line and `/workspace/.vibe/mac-bridge`. Keep the private key under `/workspace/.vibe/` — it persists on the bind mount and sits in the managed gitignore block (verify the block exists in `.gitignore`; it's not re-added if deleted, and the content-guard's private-key BLOCK remains the backstop if the key is ever staged). Don't use the host-mounted keys; they're for hosts you already ssh to.
3. **Host key**: nothing to do — `setup-ssh.sh` seeds `host.docker.internal`'s key into `known_hosts` at every container start (the file is rebuilt from the read-only host mount each launch, so in-session appends don't survive; the seed does, being re-scanned and replaced every start). It's an unattended trust-on-first-use pin: the fingerprint is printed in the postStart log — compare it against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the Mac if you want it verified. Unattended runs never hit the first-connect prompt.
4. **Autonomous runs**: the per-action SSH ask still applies. `touch .vibe-allow-ssh` in the project (or `VIBE_SSH_AUTO=1` host-side) to pre-authorise — then **relaunch**: the marker is read at container start, not per-turn, so a mid-session `touch` does nothing. The marker only counts as a **local untracked file in a git work tree** — a committed marker (which would grant autonomous SSH to every clone) is refused with a warning, as is one in a non-git download; `VIBE_SSH_AUTO=1` is the escape hatch for trusted non-git projects. It's also in vibe's managed `.gitignore` block so it stays untracked by default.

Then `ssh -i /workspace/.vibe/mac-bridge <account>@host.docker.internal` runs the pinned build from any session, including overnight `/vsss` loops. Note what the bridge trades away: the first-connect host-key prompt was an incidental last brake on an unattended (or prompt-injected) agent reaching the Mac — with the seed plus a pre-authorised ask there is no interactive step left in the chain, which is exactly why the `command=` restriction in step 2 matters.

### Budget visibility

`/budget` (inside any session) reports month-to-date tokens per model across all vibe sessions on this machine, with estimated Fable 5 credit spend at list rates. Estimates, not invoices — the authoritative credit balance is the Anthropic console.

### Code review on demand

`/review` runs Claude's own code review on the working diff (or a PR, branch, or path you name) and merges in any enabled outside-reviewer slots. It is Claude-only until you opt in, so nothing outside Anthropic is contacted by default. `--solo` makes that explicit; `--comment` is the only way findings post back to GitHub.

The **Gemini** slot is wired and self-enabling: put a key in `~/.vibe/tokens` as `GEMINI_API_KEY=<key>` and add `generativelanguage.googleapis.com` to the project's `.vibe/domains`, and the next launch fans out to it. The key travels by `remoteEnv` only, exactly like your GitHub PAT — it never reaches the firewall or postStart layer — and the slot only ever receives a diff and returns text: no shell, no writes. The allowlist entry goes in `.vibe/domains` rather than the shipped list because Google's endpoint is CDN-fronted, and only per-project domains get the mid-session `refresh-extra-domains.sh` re-resolve. Note that Google Workspace accounts are **not** allocated the Gemini API free tier — a key minted from a Workspace identity needs Cloud billing on its project; a personal Google account is the free-tier route. The **Codex** slot is also wired (setup below), using your ChatGPT subscription through the unmodified Codex CLI. Claude Code remains the lead.

Both outside slots default to enabled when their prerequisites are available. To disable one for this repo, create an **untracked** `.vibe/review-slots` containing `codex=off` or `gemini=off` (one entry per line). Missing entries mean `on`; comments and blank lines are allowed. Invalid, duplicate, symlinked or tracked policy files are refused. `--slot` never overrides `off`; `--solo` skips all outside reviewers. A failed or malformed response is reported as incomplete, never treated as agreement. Two separate switches, two separate jobs: `.vibe/review-slots` `codex=off` is the **OpenAI-egress switch** and also refuses `/ask astra`, not only this `/review` slot, since otherwise project content could still reach OpenAI through `/ask` alone; `.vibe-allow-codex` (below) is the **credential-mount switch**, deciding whether the ChatGPT login directory is bound into the container at all.

### Codex setup and one-shot delegation

The image includes Codex CLI 0.154.0. On the Mac, use Codex's own login with file storage:

```bash
codex -c 'cli_auth_credentials_store="file"' login
codex -c 'cli_auth_credentials_store="file"' login status
```

An existing login held only in the Mac Keychain cannot be mounted into Linux; sign in again with the command above. **Trade-off, stated plainly:** that moves the ChatGPT OAuth token out of the Keychain into a plaintext file (`~/.codex/auth.json`) on your Mac. If you would rather not, skip Codex in vibe; nothing else depends on it.

The login mount is **opt-in per project and off by default**, and there is deliberately no machine-wide switch that turns it on. Opting a project in takes three deliberate steps, all on the Mac, and all three are required:

1. **Log in**, so `~/.codex` exists — vibe never creates that directory itself.
2. **`touch .vibe-allow-codex`** in the project folder. The marker must be **untracked**: a committed marker, or one in a non-git download, is refused, exactly like `.vibe-allow-op`.
3. **`vibe codex allow`** from that same folder, which records the project's canonical path in `~/.vibe/codex-allow` (`chmod 600`, one path per line). `vibe codex list` shows every allowed project and whether its marker is in place; `vibe codex deny` withdraws the grant and offers to stop that project's running container so the login is unmounted immediately rather than at the next launch.

Then relaunch. Step 3 exists because step 2 lives in the project tree, which is exactly the filesystem the container can write: the in-container hooks deny the obvious writes to the marker, but not every shell idiom that could create it, so a prompt-injected session could plant a marker and the user's next launch would bind the token. The registry is the half a container cannot reach — it lives under the Mac's `$HOME` and is never mounted into any container, so **a container cannot opt itself in**. The marker states a request; the registry is the consent, and only you can give it. Removing either half is enough to revoke: the mount needs both on every launch. Network reach is a separate decision: the hosts below go in `.vibe/domains`, so a project can allowlist OpenAI without receiving the token. `VIBE_CODEX_PATH=off` in `~/.vibe/config` disables the mount everywhere, and withdrawing the opt-in recreates an existing container so the token never lingers. Read-write is required because Codex rewrites its auth cache on refresh. Inside the container the Write/Edit hook **denies** every structured write under `/home/node/.codex` and to the marker (a planted `config.toml` could name programs Codex runs on your Mac); the Bash hook blocks the same paths on a best-effort basis, with the same acknowledged limits as the `/learnings` and `/zotero` rules. Nothing in vibe has a reason to touch that directory apart from the codex binary, though the Bash hook cannot enforce that against every idiom. vibe itself never reads, copies or forwards the credential, but the hooks stop writes, not reads: anything running inside an opted-in container can read the token, so opt in only for projects you would trust with your ChatGPT account. The launch header announces the mount (`codex : /home/node/.codex (rw, ChatGPT login)`) whenever it is active, and warns once, in the same header, if that directory's permissions grant group or others any access: run `chmod 700 ~/.codex` on the Mac to fix it, since vibe never changes the mode itself. No OpenAI API key is required or accepted by these delegates.

Add these hosts to this project's **untracked** `.vibe/domains`, preserving any existing entries, then relaunch with `vibe --rebuild`:

```text
chatgpt.com
api.openai.com
auth.openai.com
```

These use the existing per-project firewall mechanism, never the shipped allowlist. `chatgpt.com` serves Codex's subscription backend; `auth.openai.com` serves login/refresh. After a CDN connection failure, run `sudo /usr/local/bin/refresh-extra-domains.sh` and retry once. Model entitlement is checked by the first actual request; no silent downgrade or paid fallback.

`/ask astra <prompt>` calls `codex exec -m gpt-6-astra` with a JSON output schema; `/ask opus|sonnet|haiku <prompt>` calls `claude -p --model … --output-format json`. Each returns the answer and CLI-reported input/output/cache/total tokens, with Claude's actual served model when supplied. **Delegate bulk payloads, not trivial questions:** measured floors are about **5k tokens per Astra one-shot** and about **3k per `claude -p`** through the helper (tools disabled; a `claude -p` with its full tool set loaded costs about 27k, which the helper never does). Move a large file, long log or big diff in one batch; do small questions in the lead session. Delegates receive only the supplied payload, with shell/tools disabled and no session resume. `/ask fable` requires explicit credit consent for this task; a previous task or launch consent does not count. That gate is a flag the lead passes after asking you, so an autonomous `/vss` run could satisfy it by itself; it is a convention, not a launcher-level prompt like `vibe --fable`.

Claude delegation has its own configurable billing route, independent of the subscription-only lead. In `~/.vibe/config`, set `VIBE_CLAUDE_P_CONFIG_DIR` to an existing container-visible Claude config directory if needed. Default `VIBE_CLAUDE_P_BILLING=subscription` pins `forceLoginMethod: claudeai`. A future `credits` or `api` route requires `VIBE_CLAUDE_P_SETTINGS` pointing at a container-visible settings JSON file; Claude itself reads that file and any `apiKeyHelper` (which is a command Claude runs, so treat that file with the care you give any config that can execute something). This takes configuration changes only, always requires explicit per-task credit consent, and adds no keys to vibe config, source or environment plumbing. Use the vendor's documented billing controls for the selected pool; vibe cannot invent or guarantee a future subscription/credit product. `/ask` reports usage per call; adding those calls to `/budget` is still follow-up work.

**Codex-led sessions: how the backstops hold.** Everything above is Claude Code leading and Codex answering a single question. When Codex itself leads a session, the same two backstops have to hold with a different runtime behind them, and they do — through a root-owned system policy baked into the image at `/etc/codex/`, not through anything in your Mac's `~/.codex`. `requirements.toml` there is a set of constraints, not defaults: it clamps whatever a user or project config asks for, pins the unhooked tool surfaces off (unified exec's `write_stdin`, the JS REPL, sub-agents, apps), forbids every MCP server with an empty allowlist, disables hosted web search — which the firewall cannot see, since it is fetched by OpenAI rather than by this container — and declares `/etc/codex/hooks` the only place hooks may come from, so a project cannot add or disable one. Those managed hooks run `codex-guard-adapter`, which feeds Codex's `PreToolUse` JSON into the **same, unmodified** `guard-bash.sh` and `guard-fs.sh` the Claude Code hooks use (Codex's hook names are already Claude-shaped: `Bash` with `tool_input.command`, `apply_patch` aliased `Write`/`Edit`), and turns every `ask` into a `deny` — an unattended session has nobody to answer a prompt, so the safe answer is no. Stated plainly: **Codex's own sandbox cannot run here.** It is bubblewrap, it needs unprivileged user namespaces, and the container does not have them, so a mode below `danger-full-access` would fail every tool call rather than contain it. What holds instead is the container boundary, the firewall, root ownership the `node` user cannot touch, an argv-prefix exec policy for force-pushes, and those hooks — exactly the set that already holds a Claude Code session under `--permission-mode bypassPermissions`. Because Codex fails *open* when a hook binary cannot be spawned, `codex-guard-liveness` exists to refuse that silence: it checks every file in the chain for root ownership and permissions, then pushes real known-bad calls through the real adapter and requires real denials before a Codex-led session is considered safe to start. `docs/codex-tool-inventory.md` lists every Codex tool at the pinned version against the layer that mediates it, including the two rows that are honestly marked unmediated.

See **MANUAL-TESTS Test 54** for the post-relaunch end-to-end checks, and **Test 55** for the Codex system policy and liveness checks.

### Second brain (optional)

vibe can mount a shared "second brain" — any local git repo of Markdown notes — into every container at `/brain2` (read-write), so cross-project knowledge (decisions, conventions, operational notes) is readable and appendable from any session, independent of any single project's git history. Point `VIBE_BRAIN2_PATH` at the repo in `~/.vibe/config` (default `~/brain2`; `=off` to disable). It is entirely optional: vibe works fully without it, and a machine with no such repo gets a silent no-op.

It's worth setting up if you: work across several repos and want durable knowledge that outlives any one project; already keep notes in Obsidian or a Markdown vault (the mount is Obsidian-friendly); or want Claude to consult and append to a persistent knowledge base instead of re-deriving context each session.

The name is only a convention — "brain2" is shorthand for "second brain". The in-container mount point is `/brain2`, but the source can be any directory; nothing requires the folder or repo itself to be called "brain2".

Every launch also auto-refreshes `<brain2>/meta/vibe-operation.md` (fail-soft — a no-op if brain2 isn't mounted or the dir isn't writable): a managed block holding the currently-installed `vibe --help` output, so an in-container Claude with no visibility into the host-side launcher has a ground-truth reference instead of guessing. Prose you add outside that block is preserved untouched on every refresh.

## Host-side state

| Path | Purpose |
|---|---|
| `~/bin/vibe` | Symlink to the launcher |
| `~/.vibe-src/` | Clone of this repo |
| `~/.vibe/config` | `VIBE_PROJECTS_DIR`, `VIBE_SSH_AUTO` (opt-in: `=1` skips the per-action SSH ask in all projects), `VIBE_BRAIN2_PATH` / `VIBE_ZOTERO_PATH` (shared brain2 at `/brain2` rw + Zotero at `/zotero` ro; default `~/brain2` / `~/Zotero/storage`, mounted into every container when the dir exists, `=off` to disable), `VIBE_CODEX_PATH` (the Codex CLI login dir, default `~/.codex`; unlike the two above it is mounted read-write and ONLY into projects that carry an untracked `.vibe-allow-codex` marker AND are listed in `~/.vibe/codex-allow` — see the Codex setup section; `=off` disables it everywhere), `VIBE_MODEL` (default model id for every launch; flags win), `VIBE_FABLE_CREDITS_OK` (`=1` skips the Fable 5 usage-credits confirm from 8 Jul 2026), `VIBE_OP_AUTO` (`=1` opts every project into the OpenProject MCP; off by default so `/op` never auto-activates in a public/upstream project's container — see below), `VIBE_GITHUB_OWNER` (default owner — personal account or org — offered when vibe creates a new repo; you can still type a different owner at the prompt) |
| `~/.vibe/tokens` | GitHub PATs (`owner/repo=ghp_...`); optional `ZOTERO_API_KEY=...` line (slash-free key → no collision with a repo entry) surfaced in-container as `$ZOTERO_API_KEY` for direct Zotero web-API calls; optional `OPENPROJECT_MCP_URL=...` + `OPENPROJECT_MCP_BEARER=...` lines — the OpenProject MCP endpoint and bearer, loaded only into projects that opt in (see Security model). A shared repo's PAT lives here too, keyed by its slug — same store, same `chmod 600`. Rotate an expired/revoked PAT with `vibe pat [owner/repo]` (re-prompts, hidden input, overwrites in place — no rebuild needed); a launch also auto-detects a stored PAT GitHub now rejects with `401` and re-runs the same prompt right when it bites (`VIBE_PAT_CHECK=0` skips the check). Never commit or sync to the cloud |
| `~/.vibe/repos` | Shared-repo machine registry (`owner/repo=/local/path`), `chmod 600`. Written by `vibe repos add`; per-machine, so two Macs sharing a project each register their own local checkout path |
| `~/.vibe/codex-allow` | Codex login-mount consent registry (one canonical project path per line), `chmod 600`. Written by `vibe codex allow`, cleared by `vibe codex deny`. Never mounted into a container, so nothing running inside one can grant itself the ChatGPT login — the in-project `.vibe-allow-codex` marker alone is not enough |
| `~/.vibe/skipped` | Projects opted out of GitHub |
| `~/.vibe/learning.config` | Learning library location + visibility |

## Uninstall

- **Launcher**: remove the `~/bin/vibe` symlink. If you installed via `install.sh`'s curl path, also `rm -rf ~/.vibe-src` (the cloned source it symlinked into); if `~/bin/vibe` points at your own in-place dev clone, deleting that clone is enough — there's no separate `~/.vibe-src` to clean up.
- **Credentials**: `rm -rf ~/.vibe` removes `~/.vibe/tokens` (your GitHub PATs and any `ZOTERO_API_KEY`/OpenProject creds) along with `~/.vibe/config`, `~/.vibe/repos`, `~/.vibe/skipped`, and `~/.vibe/learning.config`. This deletes the local copies only — it does not revoke anything GitHub-side, so also revoke the fine-grained PATs vibe created at [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens).
- **Docker**: containers aren't named `vibe-*` — they're built from one shared image and matched to a project by a devcontainer label, so `docker ps -a --filter ancestor=vibe-dev:latest -q | xargs -r docker rm -f` removes any that are still around, then `docker rmi vibe-dev:latest` drops the image. Two named volumes persist across every project: `vibe-claude-config` (your Claude Pro login and Claude Code history — deleting it logs you out of every vibe project) and `vibe-bash-history`. `docker volume rm vibe-claude-config vibe-bash-history` clears both if you want a clean slate.
- **Left alone by the above**: `rm -rf ~/.vibe` takes `~/.vibe/config` with it (it's a file inside that directory, like tokens), but the optional `/learnings` library itself lives at whatever path `~/.vibe/learning.config` pointed to — a separate directory, untouched — remove it by hand if you want it gone too. Per-project `.vibe/` and `.claude/settings.local.json` inside each project folder are gitignored runtime files, not host-side state; they go away with the project folder itself.

## Security model

- **Network:** iptables firewall allows only an allowlist of hosts a coding session needs (GitHub, npm, Anthropic, VS Code marketplace, a few opt-in extras — the list is `devcontainer/init-firewall.sh`), plus DNS and outbound SSH. If the boot-time fetch of GitHub's IP ranges fails, the firewall falls back to a re-validated, root-owned cached copy (max 7 days old) rather than failing closed outright; no fetch and no valid cache still fails closed.
- **GitHub:** every fine-grained PAT stays scoped to a single repo. A container's blast radius is exactly the repos in its launch header — the project repo, plus any private repos it declares in `.vibe-repos` and mounts under `/repos/*` (read-only by default; `--rw` intents are lock-refereed) — each reached via its own single-repo token (routed by `credential.useHttpPath`), never a multi-repo token. If Claude goes rogue, it can only touch those announced repos.
- **Host FS:** only the project folder, `~/.ssh` (ro), and `~/.gitconfig` (ro) are mounted in.
- **Claude Pro credentials:** in a named Docker volume (`vibe-claude-config`), not bind-mounted from the host — a compromised container can't leak host credentials unless the firewall is breached.
- **Extra firewall domains are per-project, never shipped defaults.** The allowlist in `devcontainer/init-firewall.sh` is vibe's public default — every container, every user — so a project that needs one extra host (a private accounting API, an internal package registry) extends it locally instead of editing that list. Put one hostname per line in `.vibe/domains` in the project (`#` comments and blank lines are ignored), or set `VIBE_EXTRA_DOMAINS="a.example.com b.example.com"` in `~/.vibe/config` for every project on the machine; the file wins where both exist. The per-project file must be **untracked** — a `.vibe/domains` committed to a repo is refused, so a malicious PR can't punch a hole in the firewall of everyone who clones it (use the config variable for a trusted non-git project). Entries must be plain DNS hostnames: anything else is dropped with a warning, and the launcher and the firewall validate independently. The resolved list is printed in the launch header, and the extras join at the *optional* tier, so one that fails to resolve warns rather than blocking boot. The list is read at container start by `init-firewall.sh`, which does not re-run against an already-running container — so vibe compares the list against the existing container's own environment and **recreates the container when it changed** (`extra firewall domains changed since this container was created - recreating it`). A plain `vibe` relaunch is therefore enough; you never need `--rebuild` for a domain change. Editing the *shipped* allowlist in `devcontainer/init-firewall.sh` is different — that file lives in the image, so it needs `vibe --rebuild`.

- **Extra domains behind a CDN go stale, and the session heals itself.** `init-firewall.sh` resolves each extra host once, at container start, and pins those addresses. Most SaaS APIs sit behind Akamai, Cloudflare or Fastly and move to a different edge within the hour, so a host that was reachable at boot can start refusing connections mid-session — DNS still resolves, the packet is rejected, and the launch header still says (truthfully, of boot time) that the host is allowed. The fix is `sudo /usr/local/bin/refresh-extra-domains.sh` inside the container: it re-resolves *only* this project's extra domains and adds their current addresses to the live allowlist. It is additive and cheap — it never flushes the allowlist, never touches iptables or the GitHub ranges, takes no arguments, and needs no token — so re-running it when nothing has moved is a no-op. You rarely run it yourself: when the project has extra domains, Claude is given a CLAUDE.md fragment telling it to run the refresh and retry once whenever a request to one of those hosts fails in that shape. It is deliberately reactive rather than a background timer — a session left open for weeks would otherwise re-resolve thousands of times for nothing. Addresses accumulate until the container restarts (the script never removes an old edge), which is a small, bounded widening within hosts you already allowlisted.

- **OpenProject MCP is opt-in per project.** `/op` reaches your *private* OpenProject, so its bearer is never loaded into a container that didn't ask for it — a public/upstream repo's session gets no OP access by default. Enable it with `VIBE_OP_AUTO=1` in `~/.vibe/config` (all projects) or a local `touch .vibe-allow-op` in a specific project. The per-project marker must be **untracked** — a `.vibe-allow-op` committed to a repo is refused, so a malicious PR can't turn it on. With the opt-in satisfied and `OPENPROJECT_MCP_URL`/`OPENPROJECT_MCP_BEARER` staged in `~/.vibe/tokens`, everything else is automatic at launch: vibe spawns a Mac-side forwarder so the firewalled container can reach a tailnet-only endpoint, and the container registers the MCP at start only after a health probe succeeds (`register-op-mcp.sh`) — an unreachable endpoint leaves `/op` unregistered for the session instead of erroring on every Claude start. Opt-in, creds, and the `--add-host` route are fixed at container creation, so enabling OP in an existing container is always `vibe --rebuild`.
- **Built on Anthropic's [reference devcontainer for Claude Code](https://github.com/anthropics/claude-code/tree/main/.devcontainer)**, lightly patched (shared Claude auth across projects; read-only `~/.ssh` and `~/.gitconfig`; per-repo PAT via a git credential helper). Launches via [`@devcontainers/cli`](https://github.com/devcontainers/cli) with `--override-config` so you never commit `.devcontainer/` into each project.

### Content guard: secrets/PII pre-commit + pre-push block + pre-publish audit

vibe containers commit and push under `bypassPermissions`, so a self-contained (no `gitleaks`/`trufflehog`, no network) git-hook layer scans everything before it leaves the machine: `pre-commit` (staged diff), `commit-msg` (the message itself), and `pre-push` (the outgoing push range). Two severities — **BLOCK** on high-precision secrets (GitHub PATs, API keys, AWS keys, private-key blocks, secret-shaped assignments), **WARN** on lower-precision PII (RFC1918/link-local IPs, personal home paths, `.local` hostnames, email addresses) — both exit non-zero by default, since commits here run non-interactively with no TTY for a y/n prompt. Clear a finding with a repo-root `.vibe-content-allow` entry (one ERE regex per line, whole-line match), a `.vibe-content-guard-off` marker (exempts an intentionally-private repo like the brain2 gardener entirely), or `VIBE_CONTENT_GUARD=off` (alias `VIBE_ALLOW_COMMIT=1`) for a one-off override — always logged loudly, never silent. A built-in allowlist (the `Co-Authored-By`/`Signed-off-by` trailer convention, `noreply@anthropic.com`) needs no configuration. `vibe audit --history` (host-side, run from the project directory) covers what a forward-looking hook can't: a repo's full history, both tiers, including content committed then later deleted — the case a Private→Public flip actually needs surfaced before it happens. It only reports; never rewrites history.

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
