# Security

vibe runs Claude Code in a `--permission-mode bypassPermissions` container. That is safe only because two backstops hold: a fail-closed network firewall (`devcontainer/init-firewall.sh` — egress DROP by default, allowlist for GitHub/npm/Anthropic/VS Code plus outbound SSH) and PreToolUse tool-call hooks (`devcontainer/guard-bash.sh`, `devcontainer/guard-fs.sh`). Credentials stay on the host: the GitHub token is a per-repo fine-grained PAT (blast radius is one repo), auth is the user's Claude Pro/Max subscription and never an API key, and secrets never leave the machine unencrypted beyond `~/.vibe/tokens` (chmod 600).

A security issue in vibe is anything that breaks one of those backstops.

## In scope

- Firewall bypass — reaching a non-allowlisted host from inside the container, or a change that leaves egress open on error instead of failing closed.
- Hook bypass — getting a Write/Edit/MultiEdit or a shell-write idiom past `guard-fs.sh`/`guard-bash.sh` (path traversal, split writes, interpreter-embedded writes) when it should have prompted.
- Credential leakage — a PAT, subscription token, or SSH key escaping the container, landing in the repo, or being written anywhere beyond `~/.vibe/tokens`.
- PAT scope escalation — a workflow that needs, grants, or exploits GitHub access broader than the single target repo.
- Anything that lets the container mutate the host outside the intended bind mounts.

## Out of scope

- Bugs in Claude Code itself, Docker Desktop, OrbStack, or the base devcontainer image. Report those to their own projects upstream.
- The container being able to run arbitrary code or reach allowlisted hosts. That is the design, not a vulnerability.
- Outbound SSH to hosts the user already has keys for. That is a deliberate capability.

## How to report

Use this repository's Security tab, "Report a vulnerability" (GitHub private vulnerability reporting). That keeps the report private until there's a fix.

If private reporting is unavailable, contact the maintainer via https://github.com/Aqueum and we'll open a private channel from there.

Please don't open a public issue for a vulnerability.

vibe is maintained by one person. There's no response-time guarantee — reports are read and acted on as fast as is realistic, not on an SLA.
