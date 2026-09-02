# Regrettable-content guard (git hooks + `vibe audit`)

vibe scans staged diffs, commit messages and outgoing pushes for secrets and
personal PII before they leave the machine, composing with (never replacing)
`guard-bash.sh`'s force-push block. Summary only; rationale and worked
examples: the `### Content guard` section of `README.md`.

## Two tiers

- **BLOCK** — high-precision secrets: GitHub PATs, OpenAI/Anthropic-style
  keys, AWS access key ids, private-key blocks, generic
  secret/token/password/api-key assignments of a long value.
- **WARN** — lower-precision PII: RFC1918/link-local IPs, personal home paths
  (`/Users/<name>/`, `/home/<name>/`, excluding container users `node`/`root`),
  `.local` mDNS hostnames, emails.
- **WARN: commit-identity** — `pre-commit` also checks the effective
  `git config user.email`; anything outside the GitHub-noreply class
  (`*@users.noreply.github.com`, `noreply@github.com`,
  `noreply@anthropic.com`, vibe's `placeholder@vibe.local`) fires: a real
  address in commit metadata is published on every public push. Fix it
  (`git config user.email '<ID>+<USER>@users.noreply.github.com'`) or
  allowlist it. `vibe audit --history` checks all identities in history.

WARN is a severity label, not a softer gate — **both tiers exit non-zero**
(README says why), and both clear the same way. `pre-commit` and `commit-msg`
scan both tiers; `pre-push` re-scans only BLOCK on the outgoing range
(re-flagging already-committed PII every push cries wolf). `git commit
--no-verify` / `git push --no-verify` bypass natively.

## Clearing a finding

- `VIBE_CONTENT_GUARD=off` (or `VIBE_ALLOW_COMMIT=1`) bypasses that one git
  invocation. Never silent: it prints a loud stderr line naming the override
  and every rule id skipped. Use it for a deliberate one-off.
- `.vibe-content-guard-off` — repo-root marker; scanner exits clean, no
  scanning. For end-to-end private repos (brain2's gardener).
- `.vibe-content-allow` — repo-root allowlist, one ERE regex per line
  (`#` comments and blanks ignored, case-sensitive); a finding is suppressed
  iff its WHOLE flagged line matches an entry.
- Built-in, no configuration: `Co-Authored-By:` / `Signed-off-by:` trailers,
  `noreply@anthropic.com` and `*.users.noreply.github.com` are always exempt,
  so the guard never fires on vibe's commit convention.

## `path-warn:<glob>` entries

A `.vibe-content-allow` line `path-warn:<glob>` is a different entry kind: a
bash `case`-style glob matched against the repo-relative path, structurally
excluded from the `grep -E` content loop so a glob can never suppress by
substring. In `--staged`/`--range` only, a matching file's added lines are
scanned at BLOCK tier only — WARN rules (IP, home-path, mdns, email) skipped
— but **BLOCK rules always still fire**: no path suppresses a BLOCK finding,
in any mode. `*` crosses `/`; escape literal `[`, `]`, `?` yourself. Empty
`path-warn:` is malformed and inert, never match-all; `path-warn:*` is
deliberately accepted. Message/history modes (`--message`,
`--messages-stdin`, `--blob-stdin`, `--identity`) have no path: entries are
invisible there. Stale pre-task_023 scanners fall back to ERE-whole-line
matching — never rely on it, and never put an entry's literal text on a
sensitive line. vibe ships `path-warn:.vs/*`, `path-warn:smoke-test.py`.

## `vibe audit [--history|--staged]`

Host-side, from the project directory. `--history` (default) scans full
history at both tiers, including content committed then deleted — the
Private→Public flip case. Exits 1 only on a BLOCK finding; WARN-only history
exits 0 but lists every finding to review. `--staged` runs the `pre-commit`
check on demand. It only reports, never rewrites history — `git filter-repo`
/ BFG is separate and deliberate.
