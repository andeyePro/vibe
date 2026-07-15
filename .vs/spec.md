# Spec — task_019: regrettable-content guard (secrets/PII pre-commit + pre-push block + pre-publish audit)

## Task summary

vibe containers commit and push freely under `bypassPermissions`, and in practice have committed personal/inappropriate content — PII, private-machine specifics, and even sensitive detail in commit *messages* — that made Time&I's Private→Public flip painful. Build a **vibe-core** guard that stops regrettable content leaving the machine: a git-hook layer (pre-commit + commit-msg + pre-push) that scans staged content AND commit messages AND the outgoing push range, blocking high-precision secrets and warning on lower-precision PII, with an explicit logged override; plus a host-side `vibe audit` command that scans a repo's **full history** for the Private→Public case a forward-looking hook cannot retroactively cover. It ships to every container via `install-claude-extras.sh` and must not false-positive on vibe's own repo (which deliberately contains example PII in its hygiene docs), on the mandatory `Co-Authored-By` commit trailer, or on intentionally-private repos (e.g. a brain2 knowledge base committed by its gardener).

## Design (locked with Martin — not open for re-litigation)

- **Two-tier response, block-by-default:** BLOCK on high-precision secrets; WARN on lower-precision PII. **Both tiers exit non-zero (block) by default** in the non-interactive agent context — the tier is a *confidence/severity label*, not a hard-vs-soft gate (see § WARN semantics). Override bypasses either.
- **Ships core** — installed for every container, not user-specific.
- **Self-contained** — pure POSIX/bash + grep ERE, no `gitleaks`/`trufflehog` (not in the firewall allowlist).
- **Scans commit messages** for secrets, not just diffs (with trailer handling, see below).

## Scanner contract (pinned, so Generator and Tester cannot guess differently)

- **Invocation:** `vibe-content-scan.sh <mode>` where mode is `--staged` | `--message <file>` | `--range <a> <b>` | `--blob-stdin` (raw content on stdin, used by `vibe audit`).
- **Output line format (one per finding), machine-parseable, tab-separated:**
  `<CLASS>\t<location>\t<rule>\t<snippet>` — CLASS is the literal token `BLOCK` or `WARN`; location is `file:line` (or `message` / `commit <sha>` for non-file sources); rule is a short rule id (e.g. `github-pat`, `rfc1918-ip`); snippet is the matched substring, truncated to 60 chars. All findings go to stderr; stdout stays empty.
- **Exit codes:** `0` = clean (or all findings suppressed/overridden); `1` = at least one un-suppressed finding that blocks. **Exit 1, not 2** — 2 is guard-bash.sh's PreToolUse protocol signal and is deliberately not reused here (git only cares zero vs non-zero).
- **Tier scanning by mode:** `--staged` and `--message` scan **both** tiers. `--range` (pre-push backstop) scans **BLOCK tier only** for file content — rationale: PII already committed was seen by the commit-time gate, so re-flagging it on every push of the same branch is the "cries wolf" failure; pre-push exists to catch *secrets* that reach the push range by any route. `vibe audit --history` scans **both** tiers for file content — it is a one-shot, deliberately-invoked scan with no repeat-nag problem, and WARN-tier PII sitting in history is exactly what a Private→Public flip needs surfaced. Every mode that scans commit messages scans both tiers against those messages (subject to the trailer exemption below).
- **Built-in default allowlist (scanner-level, applies to EVERY repo, not opt-in):** the scanner always suppresses (a) the `Co-Authored-By:` / `Signed-off-by:` git trailer lines and the literal address `noreply@anthropic.com` and `*.users.noreply.github.com`; (b) email/IP findings on lines matching a standard git trailer (`^[A-Z][A-Za-z-]+:\s`). This is what stops the guard firing on its own commit convention.
- **Message-tier email rule:** the WARN email rule, when scanning a commit *message*, ignores trailer lines per the built-in allowlist above; it still catches a raw address pasted into free-text message body.

## WARN semantics (resolves the non-TTY ambiguity)

Commits here are made by Claude via the Bash tool with no TTY, so an interactive "confirm y/n" is impossible. Therefore: **both BLOCK and WARN exit non-zero by default** and both are cleared the same way (allowlist entry, opt-out marker, or `VIBE_CONTENT_GUARD=off`). The tier distinction is real but narrow: (1) WARN findings are labelled `WARN` in output and grouped separately in `vibe audit`; (2) a repo can globally silence a whole WARN *class* via config without silencing BLOCK; (3) BLOCK denotes near-certain secrets a human should almost never override, WARN denotes probable PII a human often legitimately keeps (via allowlist). The spec does NOT claim WARN is a softer runtime gate in the agent context — it is not.

## Components (target shape; Generator may refine mechanics, not remove capability)

1. `devcontainer/git-hooks/vibe-content-scan.sh` — the single scanner core implementing the § Scanner contract.
2. `devcontainer/git-hooks/pre-commit`, `commit-msg`, `pre-push` — thin wrappers translating git's real hook contract into scanner modes:
   - `pre-commit` → `--staged`.
   - `commit-msg` → `--message "$1"` ($1 is the message-file path git passes).
   - `pre-push` → reads stdin lines `<localref> <localsha> <remoteref> <remotesha>`; **per line: if `<localsha>` is all-zeros (branch delete) → skip (nothing to scan); if `<remotesha>` is all-zeros (new branch) → scan commits reachable from localsha but not from any existing remote ref (`git rev-list <localsha> --not --remotes`); else → scan `<remotesha>..<localsha>`.** Empty range → exit 0. (`--not --remotes` scopes across all configured remotes; correct for vibe's one-remote-per-container model. A rare multi-remote first-push to a second remote could under-scan commits already tracked via another remote — accepted limitation, not covered by an AC.)
3. `install-claude-extras.sh`: new `install_git_hooks()` — copy the hooks dir to `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/vibe-git-hooks/` (chmod +x on the three wrappers + scanner) and set `git config --global core.hooksPath` to that dir inside the container. Idempotent; added to the existing `install_*` call list.
4. **Per-repo opt-out (single syntax):** a repo-root marker file `.vibe-content-guard-off`. When present, the scanner exits `0` immediately. This exempts an intentionally-private repo whose commits happen *in-container* — the brain2 **gardener** (whose `/workspace` is the brain2 repo and which commits in-container) is the flagship case; reader containers never commit brain2 so are irrelevant here. Absence = guarded (block-by-default).
5. **Override (per-invocation, logged):** `VIBE_CONTENT_GUARD=off` in the environment bypasses the scan for that one git invocation and prints a loud stderr line naming what was skipped (rule ids). git-native `git commit --no-verify` / `git push --no-verify` also bypass and are documented. Never silent. `VIBE_ALLOW_COMMIT=1` is accepted as an alias.
6. **Allowlist (precise semantics):** a repo-root `.vibe-content-allow` file — one **ERE regex per line**, `#` comments and blank lines ignored, case-sensitive. A finding is suppressed iff its **whole flagged line** matches (`grep -E`) any allow entry. vibe's own repo ships a `.vibe-content-allow` covering **doc/fragment literals only**: the hygiene-doc example PII (`/Users/martin`, the example IPs, `mcomz.local`/`pi02.local`) and the SECURITY.md maintainer link — so criterion 6 holds. Test fixtures need no allowlist entry: they are runtime-constructed and never staged as literals (§ Dogfooding).
7. `vibe audit [--history|--staged]` (host-side subcommand in the `vibe` launcher, dispatched like `vibe repos`, before `parse_vibe_args`) — `--history` (default) scans the **full history, BOTH tiers**: all added content across every commit via `git log -p --all` piped through the scanner (`--blob-stdin`), plus every commit message (`git log --all --format=%B`). This catches both a secret and PII (IP/personal-path/`.local`) committed then later deleted — the exact Private→Public case. In `--blob-stdin` audit mode the scanner **tracks the most recent `commit <sha>` header** in the `git log -p` stream and attributes each finding's location to that commit (location = `commit <sha>`), so a human knows where to look. Findings grouped by class (BLOCK then WARN); exit `1` if any BLOCK-class finding, `0` otherwise (WARN-only history exits `0` but still lists the WARN findings — advisory for the flip). `--staged` runs the pre-commit-equivalent scan on demand. Respects `.vibe-content-allow`.
8. `devcontainer/claude-md/content-guard.md` — managed fragment teaching in-container Claude: the two tiers, the `VIBE_CONTENT_GUARD=off` override, the `.vibe-content-allow`/`.vibe-content-guard-off` files, and `vibe audit` (mirrors `learn-hook.md`).
9. Docs/tests: `smoke-test.py` `test_task019_*` cases for every AC; a `MANUAL-TESTS.md` section; a `CHANGELOG.md` entry in the same commit; a README mention.

## Dogfooding (how this task lands without fighting its own guard)

Test fixtures must never commit a *literal* real-shaped secret into vibe's repo. Two rules: (1) smoke-test fixtures **construct** bad strings at runtime by concatenation (e.g. `"ghp_" + "A"*36`, `"-----BEGIN " + "OPENSSH PRIVATE KEY-----"`) and write them into throwaway temp repos — so no contiguous secret pattern is ever staged in vibe's own tree; (2) for any unavoidable literal (illustrative strings in docs/fragment), add a matching `.vibe-content-allow` entry. The landing commit of this task may additionally use `VIBE_CONTENT_GUARD=off` if needed, but rule (1) should make that unnecessary.

## Detection rules

**BLOCK tier (high-precision secrets):**
- GitHub PAT: `ghp_[A-Za-z0-9]{36}`, `github_pat_[A-Za-z0-9_]{22,}`.
- OpenAI/Anthropic-style: `sk-[A-Za-z0-9-]{20,}`.
- AWS access key id: `AKIA[0-9A-Z]{16}`.
- Private key blocks: `-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----`.
- Secret-named assignment: a key matching `(?i)(secret|token|password|passwd|api[_-]?key|bearer)` assigned (`=`/`:`) a value of ≥16 chars from `[A-Za-z0-9+/=_-]`. (Test fixtures for this rule are runtime-constructed per § Dogfooding.)

**WARN tier (lower-precision PII, source list = `devcontainer/claude-md/project-hygiene.md`):**
- RFC1918 / link-local IPs: `10.`, `172.(1[6-9]|2[0-9]|3[01]).`, `192.168.`, `169.254.` octet patterns.
- Personal home paths: `/Users/[^/ ]+/`, `/home/[^/ ]+/` — **excluding** the generic container users `node` and `root`.
- `.local` mDNS hostnames: `[A-Za-z0-9-]+\.local\b`.
- Email addresses: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` — with the trailer/noreply exemptions from § Scanner contract.

## Acceptance criteria (mechanical — each verifiable by a smoke-test; fixtures runtime-constructed per § Dogfooding)

1. `vibe-content-scan.sh --staged` in a temp repo whose staged diff adds a runtime-built `ghp_`+36-char token exits `1` and emits a `BLOCK` line naming rule `github-pat`.
2. `vibe-content-scan.sh --message <file>` where the file contains a runtime-built OpenSSH "BEGIN … PRIVATE KEY" block marker (the real contiguous form, constructed at test time) exits `1` with a `BLOCK` line (message tier scans secrets).
3. `vibe-content-scan.sh --staged` on a diff adding `[redacted-ip]`, no allowlist/override, exits `1` AND emits a `WARN` line (class token distinct from `BLOCK`) naming rule `rfc1918-ip`.
4. `vibe-content-scan.sh --staged` on a clean diff (ordinary code) exits `0` with no findings.
5. With `VIBE_CONTENT_GUARD=off`, the AC1 scan exits `0` AND prints a stderr line naming the bypass and the skipped rule(s).
6. **(mechanism, synthetic)** A temp repo with a `.vibe-content-allow` entry whose regex matches the flagged line → that finding is suppressed; a scan whose only finding is allow-listed exits `0`. A second temp repo without the entry → same content exits `1`. (No coupling to live doc text.)
7. A repo-root `.vibe-content-guard-off` marker makes the scanner exit `0` immediately even on AC1 BLOCK content.
8. Running the real `install-claude-extras.sh` against an isolated `HOME`/`CLAUDE_CONFIG_DIR`/`GIT_CONFIG_GLOBAL` installs the scanner + three wrappers executable under `<cfg>/vibe-git-hooks/`, and afterwards `git config --global core.hooksPath` actually returns that path (real config state, not a stubbed call capture).
9. `vibe audit --history` on a throwaway repo whose HISTORY contains a runtime-built `ghp_` token that was committed and then **deleted** in a later commit exits `1` and reports the finding as a `BLOCK` line whose location names the specific commit sha (full-history, not HEAD-only); a clean-history repo exits `0`.
10. **(integration, end-to-end through the installed hooks)** In a throwaway `git init` repo with a local bare remote and `core.hooksPath` pointed at the installed dir: a real `git commit` of clean content succeeds and a real `git commit` of AC1 BLOCK content fails via the actual `pre-commit` wrapper; a real `git push` of a **new branch** whose tip commit added a secret fails via the actual `pre-push` wrapper (exercises the zero-SHA new-branch range rule).
11. A real Claude-style commit **message** ending `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` scans **clean** (exit `0`) through `--message` — the built-in trailer exemption holds (guards concern 1: the guard must not fire on its own convention).
12. The pre-existing `guard-bash.sh` force-push block still fires unchanged (`git push --force` without lease → exit 2) — no regression.
13. `python3 code-check.py` (shellcheck) clean across all shell files including the new scanner + hooks.
14. `python3 smoke-test.py` — full pre-existing suite still green (no regressions).
15. A managed fragment `devcontainer/claude-md/content-guard.md` exists naming: the two tiers, the `VIBE_CONTENT_GUARD=off` override, the `.vibe-content-allow`/`.vibe-content-guard-off` files, and `vibe audit`.
16. `vibe audit --history` on a throwaway repo whose history has an RFC1918 IP (`[redacted-ip]`) in a file committed then later deleted → the WARN finding is **reported** in the audit output (a `WARN` line whose location names the commit) even though exit is `0` (WARN-only history is advisory, not blocking). Proves audit surfaces **both** tiers in history, not just secrets.
17. A commit whose only finding is WARN-tier file content (an RFC1918 IP), landed with `VIBE_CONTENT_GUARD=off` at commit time, then pushed as a new branch through the real installed `pre-push` wrapper → `git push` **succeeds** with no override (pre-push scans BLOCK-tier only for file content, so already-committed WARN PII does not re-block). Proves the pre-push "cries wolf" fix holds.

## Out of scope (do NOT build)

- Git **history rewriting** / `filter-repo` / BFG. `vibe audit` only *reports*; never rewrites (destructive, separate deliberate op).
- External scanners (`gitleaks`/`trufflehog`) or any new network dependency.
- Full Shannon-entropy detection (only the simple secret-named-assignment heuristic in v1).
- Changing `guard-bash.sh`/`guard-fs.sh`/firewall behaviour beyond composing (AC12 guards this).
- Per-project OpenProject gating (separate finding → TODO, not this task).
- Auto-fixing/redacting flagged content — the guard blocks/warns and reports; the human decides.
- Persisting an override against a specific commit SHA so pre-push doesn't re-scan (avoided instead by pre-push scanning secrets-only — see § Scanner contract).

## Note on `core.hooksPath` global scope (concern 14)

`core.hooksPath` is set `--global` in-container, so it also covers rw `/repos/*` shared repos and (in the gardener) brain2. This is intended — a shared repo may also go public, so guarding it is correct; an intentionally-private one uses `.vibe-content-guard-off`. No interaction with task_017 credential routing (hooks read content, never credentials).

## Test location

`smoke-test.py` — new `test_task019_*` functions (host-side; subprocess-invoke the scanner, install script, and real git hooks against crafted temp repos with runtime-built fixtures; assert exit codes + output tokens), matching the existing `test_task0NN_*` convention. Tester-only and immutable once written. Shellcheck via `code-check.py`.

## Proposed budget

**3 cycles.** C1: scanner core + three wrappers + install wiring + fragment + allowlist/opt-out/override + built-in trailer exemption (ACs 1-8,10-13,15,17). C2: `vibe audit` launcher subcommand + full-history both-tier scan (ACs 9,16). C3: contingency for regressions/AC14 + docs (README, MANUAL-TESTS, CHANGELOG). Fewer if C1 lands broad.

## Model plan

- Planner + Evaluator: session model (Opus chair).
- Spec Critic: sonnet.
- Generator: **sonnet**, ceiling **opus** (security-adjacent shell + regex correctness — escalate on a capability-fail, not on spec/test issues).
- Tester: haiku, → sonnet only if test *quality* is flagged.
- **Fable rung: NOT pre-authorised** (Fable rationing 2026-07-11; no credit spend without a fresh ask). Well-specified — Sonnet-appropriate.

## Invariants (from CLAUDE.md — must hold)

- Don't weaken the firewall or the existing guard hooks (compose only; AC12).
- Every PAT stays single-repo; no change to credential routing.
- Self-contained; must **not** block normal commits in ordinary use — the built-in trailer exemption (AC11), allowlist, opt-out, and pre-push-secrets-only design are what protect this. A guard that cries wolf gets disabled.
