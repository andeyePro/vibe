# vibe onboarding – a guide for the assisting Claude

You are probably reading this because a user asked you to take them through vibe onboarding. This file is written for you, the assisting Claude – on claude.ai, the Claude app, Claude Desktop or Claude Code. Your job is to get the user from zero to their first vibe session, at their pace, without assuming they know what a terminal is.

vibe is a single command that opens a Claude Code session inside an isolated container on the user's machine: pre-authenticated against their Claude Pro/Max subscription (no API key, no per-token billing), GitHub access scoped to one repo at a time, an outbound firewall and tool-call guards so the session can run without permission prompts and still be safe.

## Ground rules for you

- One step at a time. Give one command, explain in one sentence what it does, wait for the user to report back before the next.
- The user runs everything. If you cannot execute commands on their machine, have them open Terminal and paste each command; they paste the output back to you. If you can execute commands (Claude Code, computer use), still tell them what you're about to run and why.
- Verify every step before moving on – each step below has a check. Never stack unverified steps.
- If an error appears, read it with the user and resolve it before continuing. Do not guess ahead.
- No step here needs `sudo` beyond what the official installers themselves ask for. If something demands more, stop and reconsider.
- Expect 20–40 minutes end to end on a fresh Mac, mostly download time.

## What the user needs before starting

1. A Mac (macOS 13 or newer; Apple Silicon or Intel) **or** a Linux box (reference: Ubuntu 24.04 LTS with Docker Engine). Steps 2–4 fork by platform; everything from step 5 on is identical.
2. A Claude **Pro or Max** subscription – vibe authenticates against it. No subscription, no vibe.
3. A GitHub account (free is fine). If they don't have one, create it at github.com first.
4. About 10 GB free disk for the container tooling and images.

Confirm all four before installing anything.

## Steps

Steps 2, 3 and 4 have a **Mac** version and a **Linux** version. Ask the user which they're on before step 2 and follow only that branch; do not read both aloud.

### 1. Open Terminal

**Mac:** Applications → Utilities → Terminal, or ⌘-space and type "Terminal".

**Linux:** the terminal app for their desktop (GNOME Terminal, Konsole, …), or Ctrl-Alt-T on most distributions.

Everything below is pasted into that window, one line at a time.

### 2. Install Homebrew (the Mac package manager) — **Mac only**

Linux users skip to step 2L.

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It prints what it will do and asks for the user's Mac login password (typing shows nothing – that's normal). At the end it may print two `echo ... >> ~/.zprofile` lines to add brew to the PATH – have the user run exactly what it printed.

Check: `brew --version` prints a version.

### 2L. Update the package index — **Linux only**

Debian/Ubuntu:

```
sudo apt-get update
```

Fedora/RHEL: nothing to do; substitute `sudo dnf install -y` for `sudo apt-get install -y` throughout.

There is no Homebrew step on Linux and no `xcode-select` – the distribution's package manager is the equivalent.

Check: `apt-get --version` (or `dnf --version`) prints a version.

### 3. Install the container runtime – OrbStack — **Mac only**

```
brew install --cask orbstack
```

Then open OrbStack once from Applications so it finishes its setup. (Docker Desktop also works if the user already has it; don't install both.)

Check: `docker --version` prints a version.

### 3L. Install the container runtime – Docker Engine — **Linux only**

Not Docker Desktop: follow the official Docker Engine (`docker-ce` repo) instructions for the distribution at https://docs.docker.com/engine/install/ubuntu/ (or `/fedora/`). The distro's own `docker.io` package is usually too old.

Then start it and add the user to the `docker` group so vibe doesn't need `sudo` for every container command:

```
sudo systemctl enable --now docker
```

```
sudo usermod -aG docker $USER
```

The group change only takes effect on a new login – have the user log out and back in (or run `newgrp docker` in that terminal).

Check: `docker run --rm hello-world` prints "Hello from Docker!" **without** sudo. (If they run rootless Docker, the group step is unnecessary and the check still passes.)

### 4. Install Node, the devcontainer CLI and the GitHub CLI

**Mac:**

```
brew install node gh
```

**Linux (Debian/Ubuntu):**

```
sudo apt-get install -y git nodejs npm gh
```

(Fedora/RHEL: `sudo dnf install -y git nodejs npm gh`. If `node --version` is below 18, install a current LTS from NodeSource instead.)

**Both:**

```
npm install -g @devcontainers/cli
```

On Linux that may need `sudo npm install -g @devcontainers/cli` depending on how npm's global prefix is set up.

Check: `node --version`, `devcontainer --version` and `gh --version` each print a version.

### 5. Sign the GitHub CLI in

```
gh auth login
```

Choose: GitHub.com → HTTPS → authenticate in the browser. The user follows the browser prompts with their GitHub account.

Check: `gh auth status` says logged in.

### 6. Install vibe

```
bash <(curl -fsSL https://raw.githubusercontent.com/andeyePro/vibe/main/install.sh)
```

The installer first checks every prerequisite above and says exactly what's missing if anything is – fix and re-run. It clones vibe, links the `vibe` command onto the PATH, and asks where the user keeps (or wants to keep) their projects.

Check: `vibe --version` prints a version like `vibe 0.1.0`.

### 7. First session

Pick or create a project folder, then:

```
cd ~/path/to/your-project
vibe
```

First run teaches as it goes, interactively: it detects or creates the GitHub repo, walks through creating the one-repo fine-grained access token (the browser opens on the right GitHub page; the user pastes the token back), builds the container (a few minutes, once), and shows the Claude Pro/Max login URL. Stay with the user through this – it's the step with the most new concepts. Nothing here is dangerous; every credential stays on their machine.

Check: they see the Claude Code prompt. Have them type a small request and watch it work.

### 8. Leaving and coming back

- Exit a session: type `/exit` (or ⌃-C twice).
- Come back to a project: `cd` there and run `vibe` again – it's fast after the first build.
- Update vibe later: re-run the installer one-liner from step 6, or `git -C ~/.vibe-src pull`.

### Second session onward

Everyday use is just `cd project && vibe` — same command as step 7, every time. It starts a fresh Claude conversation by default; `vibe --continue` resumes the last one instead (README's Usage section covers both). The GitHub token from step 7 is reused automatically until it expires (90 days by default, at whatever the user chose when creating it) or is revoked; when that happens vibe notices and re-prompts on the next launch, or the user can rotate it ahead of time with `vibe pat` from that project's folder.

## When something goes wrong

- The installer and `vibe` itself print actionable messages – read them to the user, they're written for this.
- Search or ask at https://github.com/andeyePro/vibe/discussions – describe what step failed and paste the output (check it for tokens or passwords first; there shouldn't be any, but look).
- Bugs: https://github.com/andeyePro/vibe/issues with the template.

## What to tell the user vibe is NOT

- It never spends beyond their Claude subscription unless they explicitly opt in per launch (`vibe --fable` quotes rates and defaults to No).
- It can only touch the one repo it was opened in – that's the point of the per-repo token.
- It is not an Anthropic product – it's an open-source tool from andeye that wraps Anthropic's own Claude Code devcontainer.
