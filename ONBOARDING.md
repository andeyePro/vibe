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

1. A Mac (macOS 13 or newer; Apple Silicon or Intel). Linux works but is less tested – adapt the package steps.
2. A Claude **Pro or Max** subscription – vibe authenticates against it. No subscription, no vibe.
3. A GitHub account (free is fine). If they don't have one, create it at github.com first.
4. About 10 GB free disk for the container tooling and images.

Confirm all four before installing anything.

## Steps

### 1. Open Terminal

Applications → Utilities → Terminal, or ⌘-space and type "Terminal". Everything below is pasted into that window, one line at a time.

### 2. Install Homebrew (the Mac package manager)

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It prints what it will do and asks for the user's Mac login password (typing shows nothing – that's normal). At the end it may print two `echo ... >> ~/.zprofile` lines to add brew to the PATH – have the user run exactly what it printed.

Check: `brew --version` prints a version.

### 3. Install the container runtime – OrbStack

```
brew install --cask orbstack
```

Then open OrbStack once from Applications so it finishes its setup. (Docker Desktop also works if the user already has it; don't install both.)

Check: `docker --version` prints a version.

### 4. Install Node, the devcontainer CLI and the GitHub CLI

```
brew install node gh
```

```
npm install -g @devcontainers/cli
```

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

## When something goes wrong

- The installer and `vibe` itself print actionable messages – read them to the user, they're written for this.
- Search or ask at https://github.com/andeyePro/vibe/discussions – describe what step failed and paste the output (check it for tokens or passwords first; there shouldn't be any, but look).
- Bugs: https://github.com/andeyePro/vibe/issues with the template.

## What to tell the user vibe is NOT

- It never spends beyond their Claude subscription unless they explicitly opt in per launch (`vibe --fable` quotes rates and defaults to No).
- It can only touch the one repo it was opened in – that's the point of the per-repo token.
- It is not an Anthropic product – it's an open-source tool from andeye that wraps Anthropic's own Claude Code devcontainer.
