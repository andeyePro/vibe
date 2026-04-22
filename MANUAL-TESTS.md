# vibe Integration Test Checklist

Use this checklist to test vibe's full end-to-end functionality including container lifecycle. Complete the prerequisites first, then work through each test case.

## Prerequisites

Before running integration tests, ensure:

- [ ] `docker` is installed (OrbStack on macOS or Docker Desktop)
- [ ] `devcontainer` CLI is installed: `npm install -g @devcontainers/cli`
- [ ] `gh` CLI is installed and authenticated: `gh auth login`
- [ ] Run the vibe installer:
  ```bash
  bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
  ```
- [ ] Verify installation: `which vibe` (should be in ~/bin or on PATH)
- [ ] Create a test project: `mkdir -p ~/Projects/vibe-test && cd ~/Projects/vibe-test`

---

## Test Cases

### Test 1: Basic Launch from Project Directory
```bash
cd ~/Projects/vibe-test
vibe
```

**Expected:**
- [ ] Displays: "🚀 vibe session starting"
- [ ] Project path shown correctly
- [ ] Banner includes `hooks : tool-call guards + idle bell`
- [ ] Container builds (first run only)
- [ ] Claude Code launches in the container
- [ ] Can interact with Claude Code

**If Git Repo Not Found:**
- [ ] Prompted: "Create a GitHub repo for it?"
- [ ] Can enter repo name or skip
- [ ] If skipped, still launches without GitHub

**If Token Needed:**
- [ ] Browser opens to GitHub fine-grained token creation page
- [ ] Can paste token
- [ ] Token saved to ~/.vibe/tokens (chmod 600)

---

### Test 2: Launch with Project Name
```bash
vibe vibe-test
```

**Expected:**
- [ ] Resolves to ~/Projects/vibe-test
- [ ] Skips GitHub setup (token already saved from Test 1)
- [ ] Container starts
- [ ] Claude Code launches

---

### Test 3: Multiple Projects
```bash
mkdir -p ~/Projects/project-a ~/Projects/project-b
cd ~/Projects/project-a && git init
cd ~/Projects/project-b && git init

vibe --list
```

**Expected:**
- [ ] Lists both projects
- [ ] Each has own token (or "never ask" skip)

---

### Test 4: Rebuild Container
```bash
vibe --rebuild
```

**Expected:**
- [ ] Removes old container
- [ ] Rebuilds image from devcontainer.json
- [ ] Launches fresh container
- [ ] Claude Code starts

---

### Test 5: GitHub Integration
```bash
cd ~/Projects/vibe-test
# If repo exists:
git remote add origin https://github.com/YOUR_USERNAME/vibe-test.git
```

**Expected:**
- [ ] vibe detects the GitHub remote
- [ ] Prompts for token setup
- [ ] Token saved for that specific repo
- [ ] Token file shows: `github.com/YOUR_USERNAME/vibe-test=ghp_...`

---

### Test 6: Settings File Verification
```bash
# Inside the container (after vibe launches):
cat .claude/settings.local.json
git status
```

**Expected:**
- [ ] `.claude/settings.local.json` exists and contains:
  - `permissions.defaultMode: "bypassPermissions"`
  - `forceLoginMethod: "claudeai"`
  - `hooks.PreToolUse` matcher `Bash` → `/usr/local/bin/guard-bash.sh`
  - `hooks.Stop` and `hooks.Notification` each → `printf '\a' >&2`
- [ ] File not shown in `git status` (in .gitignore)
- [ ] `.claude/settings.local.json` appears in `.gitignore`

---

### Test 7: Claude Pro/Max Subscription Auth
Inside the container:

```bash
# Check Claude Code is using subscription auth
claude --version
```

**Expected:**
- [ ] Claude Code launches without asking for API key
- [ ] Uses Claude Pro/Max subscription from `forceLoginMethod: claudeai`
- [ ] Never prompts for ANTHROPIC_API_KEY

---

### Test 8: GitHub Token Isolation
```bash
# On host machine:
cat ~/.vibe/tokens
```

**Expected:**
- [ ] Shows only repos you've accessed
- [ ] Each entry format: `github.com/user/repo=ghp_xxxxx`
- [ ] Tokens are isolated per repo (fine-grained scope)
- [ ] File has restrictive permissions: `rw-------` (600)

---

### Test 9: Never Ask Again
```bash
cd ~/Projects/vibe-test
vibe
# Decline GitHub setup: "n"
vibe
# Run again, should not ask again
```

**Expected:**
- [ ] First run: Asks about GitHub
- [ ] Answer "never"
- [ ] Confirmation: "✓ Got it — won't ask about GitHub for this project again."
- [ ] Second run: No GitHub prompt
- [ ] ~/.vibe/skipped contains: `/path/to/vibe-test`

---

### Test 10: API Key Warning
```bash
export ANTHROPIC_API_KEY="sk-test-key-123"
cd ~/Projects/vibe-test && vibe
```

**Expected:**
- [ ] Warning shown before docker check:
  ```
  ⚠  ANTHROPIC_API_KEY is set — Claude Code inside the container would bill
     against API credits if it honoured it...
  ```
- [ ] Container still launches (settings override prevents API key use)
- [ ] Claude Code uses subscription auth, not API key

---

### Test 11: New Repository Initialization
```bash
mkdir -p ~/Projects/brand-new && cd ~/Projects/brand-new
vibe
```

**Expected:**
- [ ] vibe initializes git: `git init`
- [ ] Creates initial commit (if needed)
- [ ] Proceeds to GitHub setup
- [ ] Option to create GitHub repo

---

### Test 12: SSH Access (if remote dev machines configured)
Inside the container:

```bash
# Assuming SSH keys are mounted:
ssh remote-dev-machine
```

**Expected:**
- [ ] SSH to outbound hosts works
- [ ] Can clone repos, push, pull
- [ ] SSH keys from host machine are accessible

---

### Test 13: Container Isolation
Inside container:

```bash
env | grep GITHUB_TOKEN
```

**Expected:**
- [ ] GITHUB_TOKEN is available in container
- [ ] Other host environment variables NOT leaked
- [ ] Container sees only mounted project directory

---

### Test 14: Workspace Mount
Inside container:

```bash
pwd
ls -la
```

**Expected:**
- [ ] Working directory is the project root
- [ ] Can see all project files
- [ ] Git history intact
- [ ] Can commit and push (with token)

---

### Test 15: Exit and Resume
```bash
# Inside container:
exit  # or Ctrl+D

# Back on host:
cd ~/Projects/vibe-test && vibe
```

**Expected:**
- [ ] Exit cleanly
- [ ] Can re-enter container
- [ ] Previous session state lost (expected)
- [ ] New Claude Code session starts

---

### Test 16: Auto-rebuild on devcontainer/ changes
```bash
# After a successful vibe run (image marker exists):
touch ~/.vibe-src/devcontainer/Dockerfile
cd ~/Projects/vibe-test && vibe
```

**Expected:**
- [ ] Prints: "devcontainer/ changed since last build — rebuilding image."
- [ ] Runs `docker build`
- [ ] Old container is removed (`--remove-existing-container`)
- [ ] New container starts cleanly
- [ ] Next `vibe` run (without touching any file) does NOT rebuild

---

### Test 17: Partial-fail recovery
```bash
# Simulate postStart failure. Easiest way:
# 1. Edit ~/.vibe-src/devcontainer/init-firewall.sh to `exit 1` on line 4
# 2. vibe --rebuild    # builds image with broken script
# 3. vibe              # first run fails

# Now restore the script (from the same clone):
git -C ~/.vibe-src checkout devcontainer/init-firewall.sh
cd ~/Projects/vibe-test && vibe
```

**Expected on the broken-script run:**
- [ ] "postStartCommand failed — container is in a partial state."
- [ ] Automatic retry with `--remove-existing-container`
- [ ] If retry also fails (it will, script is still broken), clean error message pointing at `vibe --rebuild`
- [ ] No half-configured container left running

**Expected on the fixed run:**
- [ ] Auto-rebuild fires (file changed)
- [ ] Container comes up cleanly on first attempt

---

### Test 18: SSH env hint in Claude
Inside the container, ask Claude directly: "Can you SSH to other machines?"

**Expected:**
- [ ] Claude answers yes without being argued with
- [ ] `/home/node/.claude/CLAUDE.md` exists and contains the `<!-- BEGIN vibe env (managed) -->` block
- [ ] Project `/workspace/CLAUDE.md` still loads (project instructions visible to Claude)

---

### Test 19: Fresh-Mac safety (no ~/.ssh or ~/.gitconfig on host)
```bash
# On a host that has never used SSH or git:
ls -la ~/.ssh ~/.gitconfig 2>&1  # should show "No such file"
vibe
ls -la ~/.ssh ~/.gitconfig        # should now exist
```

**Expected:**
- [ ] vibe creates `~/.ssh` (0700) and `~/.gitconfig` (empty file) before launching
- [ ] Bind mounts don't fail
- [ ] Container launches normally

---

### Test 21: Force-push guardrail
Inside a vibe session, ask Claude to run:

```bash
git push --force origin main
```

**Expected:**
- [ ] Hook blocks the call with: `vibe: 'git push --force' overwrites remote history. Use --force-with-lease.`
- [ ] `git push --force-with-lease origin main` is NOT blocked
- [ ] `git push origin main` (no force) is NOT blocked

Bonus: exit Claude and ring the bell check — after Claude stops responding, the outer terminal tab should badge (Terminal.app dot, iTerm2 bell indicator).

---

### Test 22: Remote-branch-delete guardrail
Inside a vibe session, ask Claude to run each of:

```bash
git push --delete origin foo
git push origin :foo
```

**Expected:**
- [ ] Both blocked with: `vibe: 'git push' deleting a remote branch is irreversible for other clones. Confirm intent or delete via the GitHub UI.`
- [ ] `git push origin main:main` (refspec, NOT a delete) is NOT blocked
- [ ] `git push origin HEAD:refs/heads/foo` is NOT blocked

---

### Test 23: Hook audit log
After triggering any blocked command (Test 21 or 22), on the host:

```bash
docker volume inspect vibe-claude-config --format '{{ .Mountpoint }}'
# Or from inside the container:
cat /home/node/.claude/vibe-blocks.log
```

**Expected:**
- [ ] File exists at `/home/node/.claude/vibe-blocks.log`
- [ ] One tab-separated line per block: `<ISO8601-UTC>\t<rule>\t<command>`
- [ ] `rule` is `force-push` or `branch-delete`
- [ ] Multi-line commands are flattened (newlines shown as `\n`)
- [ ] Log persists across vibe sessions (survives container recreate — lives on `vibe-claude-config` volume)

---

### Test 20: `git config --global` works inside the container
Regression test for the `.gitconfig` bind-mount EBUSY failure: host `~/.gitconfig`
is mounted read-only at `~/.gitconfig-host`, and `setup-git.sh` copies it to a
writable `~/.gitconfig` so `git config --global` can rename-over-tempfile.

```bash
vibe
# inside the container:
git config --global user.email "test@example.com"
git config --global --get user.email      # should print test@example.com
git config --global --get credential.helper  # should print /usr/local/bin/vibe-credential-helper
```

**Expected:**
- [ ] No `Device or resource busy` error on postStartCommand
- [ ] `git config --global` writes succeed
- [ ] `credential.helper` points to vibe's helper
- [ ] Host `~/.gitconfig` is unchanged after the container exits

---

## Troubleshooting

### Docker not found
```bash
# Install OrbStack (macOS) or Docker Desktop
# Then: docker --version
```

### devcontainer CLI not found
```bash
npm install -g @devcontainers/cli
devcontainer --version
```

### gh CLI not authenticated
```bash
gh auth login
gh api user --jq '.login'  # Should show your username
```

### Token file has wrong permissions
```bash
ls -l ~/.vibe/tokens
# Should show: -rw------- (600)
# If not: chmod 600 ~/.vibe/tokens
```

### Claude Code won't launch
```bash
# Check settings.local.json
cat .claude/settings.local.json

# Check Claude Code is installed
which claude
claude --version
```

---

## Test Summary

After completing all tests, check:

- [ ] All help flags work
- [ ] Workspace resolution works (current dir, by name, from VIBE_PROJECTS_DIR)
- [ ] GitHub detection and token setup work
- [ ] Container builds and launches correctly
- [ ] Claude Code uses subscription auth (not API key)
- [ ] Settings applied correctly (.claude/settings.local.json)
- [ ] Token stored securely (chmod 600)
- [ ] Can commit and push via GitHub token
- [ ] SSH outbound works (if configured)
- [ ] No credentials leaked to host/container boundary

---

## Notes

- Tests can be run in any order, but prerequisite installation must complete first
- Each test is independent (can run individually)
- Safe to repeat tests (no destructive operations)
- Use `vibe --help` in doubt
- Check ~/.vibe/ for configuration files if needed
