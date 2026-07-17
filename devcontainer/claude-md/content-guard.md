# Regrettable-content guard (git hooks + `vibe audit`)

Every vibe container ships a git-hook layer that scans content BEFORE it
leaves the machine — staged diffs, commit messages, and outgoing pushes —
for secrets and personal/private-machine PII. It composes with, and never
replaces, `guard-bash.sh`'s force-push/branch-delete block.

## Two tiers, both non-blocking-by-default only via explicit override

- **BLOCK** — high-precision secrets: GitHub PATs, OpenAI/Anthropic-style
  keys, AWS access key ids, private-key blocks, and a generic
  secret/token/password/api-key-shaped assignment of a long value.
- **WARN** — lower-precision PII: RFC1918/link-local IPs, personal home
  paths (`/Users/<name>/`, `/home/<name>/` — excluding the generic
  container users `node`/`root`), `.local` mDNS hostnames, and email
  addresses.
- **WARN: commit identity** — `pre-commit` also checks the *effective*
  `git config user.email`: anything that isn't a GitHub-noreply-class
  address (`*@users.noreply.github.com`, `noreply@github.com`,
  `noreply@anthropic.com`, or vibe's `placeholder@vibe.local`) fires a
  `commit-identity` WARN, because a real email in author/committer
  metadata publishes to harvesters on every public push. Fix with
  `git config user.email '<ID>+<USER>@users.noreply.github.com'`, or
  allowlist the address (`^you@corp\.com$` in `.vibe-content-allow`) if
  it's deliberate for that repo. `vibe audit --history` runs the same
  check over every author/committer identity in history.

Because commits here run non-interactively via the Bash tool (no TTY for a
y/n prompt), **both tiers exit non-zero by default** — WARN is not a softer
runtime gate, it is a severity label. Both are cleared the same way: an
allowlist entry, the opt-out marker, or the loud override below. `git commit
--no-verify` / `git push --no-verify` also bypass, git-natively.

`pre-commit` and `commit-msg` scan both tiers. `pre-push` re-scans only the
BLOCK tier on the outgoing push range — PII already committed was already
seen by the commit-time gate, so re-flagging it on every push of the same
branch is the "cries wolf" failure that gets a guard disabled; pre-push
exists to catch secrets that reach the push range by any other route.

## Override: `VIBE_CONTENT_GUARD=off` (or `VIBE_ALLOW_COMMIT=1`)

Set either in the environment to bypass enforcement for that one git
invocation. Never silent — the scanner prints a loud stderr line naming the
override and every rule id it skipped. Prefer this over disabling the guard
outright when a finding is a deliberate one-off (e.g. Martin's own IP in a
throwaway test fixture that never gets committed for real).

## Per-repo opt-out: `.vibe-content-guard-off`

A repo-root marker file that makes the scanner exit clean immediately, no
scanning at all. For a repo that's intentionally private end-to-end — the
brain2 gardener (whose `/workspace` IS the brain2 repo and commits
in-container) is the flagship case. Reader containers never commit brain2,
so this never applies to them.

## Per-repo allowlist: `.vibe-content-allow`

A repo-root file, one ERE regex per line (`#` comments and blank lines
ignored, case-sensitive). A finding is suppressed iff its **whole flagged
line** matches any entry. Use this for known, deliberate literals — vibe's
own repo ships one covering the example PII in its own hygiene docs
(`/Users/martin`, the example IPs, `mcomz.local`/`pi02.local`) and the
SECURITY.md maintainer link, so the guard never fires on its own
documentation.

The scanner also has a **built-in allowlist that needs no configuration**:
`Co-Authored-By:`/`Signed-off-by:` trailer lines, `noreply@anthropic.com`,
and `*.users.noreply.github.com` are always exempt — this is what stops the
guard firing on its own commit convention.

## `vibe audit [--history|--staged]`

Host-side command (run from the project directory, like `vibe repos`) that
scans **beyond** what the forward-looking git hooks can retroactively cover
— the case a Private→Public repo flip actually needs. `--history` (default)
scans the full history, both tiers, including content that was committed
and later deleted: a secret or an IP that only ever existed for a few
commits is still visible to a clone of the repo's history. Exits `1` only
if a BLOCK-class finding turns up anywhere in history; WARN-only history
exits `0` but still lists every WARN finding — advisory, for the human
doing the flip to review. `--staged` runs the same check as `pre-commit`,
on demand. `vibe audit` never rewrites history — it only reports; a real
Private→Public flip needing history rewritten is a separate, deliberate
operation (`git filter-repo` / BFG), never automated by this guard.
