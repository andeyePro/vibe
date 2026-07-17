# Spec — task_023: path-scoped WARN allowlisting (`path-warn:` entries) so vibe's repo is self-clean under its own content guard

## Task summary

vibe's own tree legitimately contains WARN-class example literals — RFC1918 IPs, example emails, hostnames — in `smoke-test.py` test fixtures and `.vs/` harness prose (specs, critiques, archived test logs). Under the task_019 guard, every commit touching those files nags for a `VIBE_CONTENT_GUARD=off` override (it happened three times in this /vsss session alone). The rejected fix is global content-allowlisting of IP/email literals (it would blind the guard everywhere). The right fix is path-scoped: a new `path-warn:<glob>` entry type in `.vibe-content-allow` that demotes MATCHING FILES to BLOCK-tier-only scanning in the diff-based modes — WARN noise suppressed exactly where it is known-deliberate, while secrets still fire everywhere, in every mode, always.

## Design (settled)

- **Syntax**: a `.vibe-content-allow` line of the form `path-warn:<glob>` (prefix literal `path-warn:`, then a bash glob matched against the repo-relative file path; surrounding whitespace around the glob trimmed; `#` comments and blank lines unchanged). All other lines keep today's whole-flagged-line ERE semantics exactly.
- **path-warn lines NEVER enter the ERE loop** (the make-or-break constraint): `line_is_allowlisted` (and any other consumer of the allowlist's ERE entries) must structurally skip `path-warn:`-prefixed lines — neither the full line nor the glob remainder may ever be handed to `grep -E` as a content pattern. A glob like `smoke-test.py` used as an ERE is a live literal-substring match that would suppress ANY finding — including a BLOCK secret — on any line merely mentioning the filename. Mandatory test (AC3b).
- **Glob semantics pinned**: the glob is used as an UNQUOTED bash `case`-style pattern against the repo-relative path — `*` crosses `/` (`.vs/*` matches `.vs/archive/task_099/critiques/foo.md`). A quoted-variable implementation silently kills the feature (glob chars go literal); the nested-path test in AC2 exists to catch exactly that. Glob metacharacters (`[`, `]`, `?`) in a literal path need escaping — documented in content-guard.md, not otherwise handled.
- **Degenerate globs**: `path-warn:` with an empty/whitespace-only glob is malformed — skipped, matches nothing. `path-warn:*` (repo-wide WARN-off) is ACCEPTED: it is the same trust model as today's equally-possible overbroad ERE entry (a lone `.`), and the allowlist is a PR-reviewable committed file; content-guard.md documents the implication rather than the scanner policing it.
- **Mechanism**: in the diff-based modes (`--staged`, `--range`), when a `+++ b/<path>` header sets the current file and `<path>` matches any `path-warn` glob, that file's added lines are scanned at tier `block` instead of the mode's normal tier. This reuses the existing tier mechanism — per-FILE check, zero per-line cost, no forks (bash `case`-style glob match, no external commands).
- **Where it does NOT apply**: `--message`, `--messages-stdin`, `--blob-stdin` (history), `--identity` — no file path exists there (locations are `message` / `commit <sha>` / `identity`), and history findings deliberately keep full visibility for the Private→Public flip case. Document this.
- **BLOCK is never suppressible by path**: a real secret in a fixture file is still a shipped secret. `path-warn` demotes tier; it never disables the BLOCK rules.
- **Ship the repo's own entries**: `path-warn:.vs/*` and `path-warn:smoke-test.py` appended to vibe's `.vibe-content-allow` with a comment block explaining scope (harness prose + runtime-fixture file that deliberately discuss rule examples).
- **Back-compat (corrected after Spec Critic)**: an older scanner reading a new allowlist feeds the WHOLE line — prefix included — to `grep -E`, so the entry `path-warn:smoke-test.py` only matches content containing the literal text `path-warn:smoke-test.py` (essentially: documentation quoting the allowlist). That is a narrow, real over-suppression window on stale-scanner containers; it is accepted and documented in content-guard.md ("a doc line quoting a path-warn entry is exempt on pre-task_023 scanners — never put one on the same line as anything sensitive"). The scanner change and the shipped allowlist entries land in the SAME commit so this repo itself never has a mixed state. New scanner reading an allowlist with no `path-warn` lines behaves byte-identically to today (proven by differential).
- **Rename caveat**: `scan_diff_stream` derives the path from `+++ b/<path>` with no rename detection (pre-existing). Path attribution previously affected only the location string; it now also gates WARN emission. Accepted for `git diff -U0 --no-color` output (rename detection not enabled there), noted here so a future reader doesn't assume path attribution is still cosmetic-only.

## Files in scope

- `devcontainer/git-hooks/vibe-content-scan.sh` — allowlist parsing split (path-warn entries vs ERE entries), per-file tier demotion in `scan_diff_stream`, header/usage comment update.
- `.vibe-content-allow` — the two new `path-warn` entries + comments.
- `devcontainer/claude-md/content-guard.md` — document the new entry type (syntax, WARN-only, mode applicability).
- `smoke-test.py` — Tester appends (append-only; Generator never touches it).
- `TODO.md` (tick item) + `CHANGELOG.md` (2026-07-17 entry) — same commit.

## Acceptance criteria

1. **Parser**: `path-warn:<glob>` entries are recognised (whitespace-tolerant after the prefix); `#`/blank lines unchanged; every non-`path-warn:` line keeps exact ERE whole-line semantics — proven by a differential corpus run (task_022-style: old scanner from `git show <pre-change-sha>` vs new, byte-identical on an allowlist WITHOUT path-warn entries, `LC_ALL=C sort`).
2. **`--staged` suppression**: WARN-class added content (an RFC1918 IP, a non-noreply email, a `/Users/<name>/` path, an mdns `.local` hostname) in a file matching a `path-warn` glob produces NO finding and exit 0; the SAME content staged in a non-matching file produces the normal WARN findings and exit 1. Fixture repo, entries like `path-warn:fixtures/*`. MUST include a nested-path case: `path-warn:.vs/*` (or `fixtures/*`) suppressing WARNs in a file 3 levels deep (e.g. `.vs/archive/task_099/critiques/foo.md`) — this catches the quoted-glob implementation failure. Also: an empty-glob line (`path-warn:`) is ignored (no crash, no match-all).
3. **BLOCK still fires under path-warn**: a runtime-built `ghp_`-shaped token added to a path-warn-matched file in `--staged` → BLOCK finding + exit 1. Same for `--range`. No path may ever suppress a BLOCK finding in any mode.
3b. **No ERE double-parse**: with `path-warn:smoke-test.py` in the allowlist, a runtime-built BLOCK secret staged in a NON-matching file on a line that ALSO contains the literal text `smoke-test.py` (and a variant containing `path-warn:smoke-test.py`) still produces the BLOCK finding + exit 1 — proving path-warn lines (full or stripped) never reach the ERE loop.
3c. **`--range` idempotency**: `--range` output on a dirty fixture is byte-identical with and without `path-warn` entries present (tier demotion is a one-way floor; `--range` is already block-tier) — regression-pins the floor property.
4. **Non-diff modes unaffected**: with `path-warn` entries present in the allowlist, `--message`, `--messages-stdin`, `--blob-stdin`, and `--identity` behave byte-identically to the pre-change scanner on the adversarial corpus (path-warn is invisible where no file path exists).
5. **Self-clean end-to-end**: with the repo's shipped entries, staging a `.vs/spec.md` edit and a `smoke-test.py` edit that each add a WARN-class example literal → `--staged` exits 0 with no findings and no override; planting a runtime-built PAT in each → exit 1. (Fixture-repo simulation of the vibe tree shape is acceptable; do not commit literal WARN examples to the real tree.)
6. **Audit integration**: `vibe audit --staged` inherits the behaviour (same code path). `vibe audit --history` output for historical content is UNCHANGED by path-warn entries, and its runtime stays under 60s on the vibe repo (task_022's gate not regressed).
7. **Static shape guards**: task_022's permanent no-fork/no-`\b`/no-bash-4 checks still pass; the glob match itself introduces no external-command invocation on any per-line or per-file path (bash `case`/pattern match only).
8. **Suite + lint**: full pre-existing `python3 smoke-test.py` green (zero regressions), `python3 code-check.py` clean, AND a direct `shellcheck devcontainer/git-hooks/vibe-content-scan.sh` clean run — `code-check.py` structurally cannot see that directory (its `scripts()` is fixture-frozen; separate queue item), so the direct invocation is the real lint gate for the changed file.
9. **Docs + bookkeeping**: content-guard.md documents `path-warn:` (syntax, WARN-only, diff-modes-only, BLOCK-never-suppressed); scanner header comment updated; TODO item ticked (removed from Open) + CHANGELOG entry — same commit as the code.

## Out of scope

- Path tracking / path-warn application in `--blob-stdin` or `--messages-stdin` (history stays fully visible; also avoids touching task_022's just-verified hot path shape beyond the diff modes).
- Per-file opt-in markers (`# vibe-content-allow-file`) — rejected in favour of the declarative allowlist (no scanner file I/O, works for markdown without embedded markers, one reviewable grant surface).
- Any new rules, tier changes, or global literal allowlist entries for the fixture content (explicitly rejected by the TODO).
- `guard-bash.sh` / `guard-fs.sh` / `init-firewall.sh` / `settings.local.json` (hard-escalate list; not needed).
- `code-check.py` (separate queue item; its `scripts()` body is a smoke-test fixture landmine).

## Test location

`smoke-test.py` — append-only new test functions per existing fixture-repo conventions (task_019/022 precedent). Differentials against the old scanner are one-off (log); permanent tests freeze expected findings. Once committed, tests are immutable.

## Proposed budget

2 cycles.

## Model plan

- Generator: **sonnet**, ceiling opus. Rationale: localized parser + per-file tier demotion on a well-understood file; the dangerous regex-equivalence work was task_022's, not this. Fable rung: **not pre-authorised**.
- Tester: **sonnet** start, ceiling sonnet (haiku quality history on this surface: task_017/019).
- Spec Critic: sonnet. Planner/Evaluator: session model (Fable 5 chair; no credit-billed subagents).
