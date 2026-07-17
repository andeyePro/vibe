# Spec — task_022: `vibe audit --history` performance (fork-storm removal + single-pass message scan)

## Task summary

`vibe audit --history` timed out at 280s on the vibe repo (~230 commits). Two causes, both in the task_019 content guard: (1) the scanner's match primitives fork `printf | grep -oE` subprocess pairs per rule per line — `git log -p --all` yields ~47k added lines × ~9 rule checks ≈ 400k+ forks in pass 1 alone; (2) `_audit_history` pass 2 spawns one scanner subprocess per commit to scan messages. Fix both: swap the scanner's inner match primitives to bash-native `[[ =~ ]]` + `BASH_REMATCH`, and add a `--messages-stdin` scanner mode so pass 2 becomes one delimited pipe. The finding set over any input must be **identical** to the current scanner's — this is a security boundary shared by pre-commit, commit-msg, pre-push, and `vibe audit`; a silently-narrowed rule is a shipped hole.

## Files in scope

- `devcontainer/git-hooks/vibe-content-scan.sh` — match-primitive swap (Part A) + new `--messages-stdin` mode (Part B).
- `vibe` — `_audit_history` pass-2 rewrite only (lines ~2254-2263 region). Pass 1 and pass 3 invocations stay structurally as-is.
- `smoke-test.py` — Tester appends test functions (append-only; Generator does not touch this file).
- `TODO.md` + `CHANGELOG.md` — same-commit bookkeeping.

## Part A — match primitives (scanner)

Replace the subprocess-forking match inside these functions with bash-native `[[ $content =~ $pattern ]]` and `BASH_REMATCH`-derived snippets, keeping each function's signature, exemption logic, allowlist call, output format, and `FOUND`/`FOUND_RULES` mutations byte-for-byte equivalent:

- `check_rule` — icase=1 handled via `shopt -s nocasematch` … `shopt -u nocasematch` (restore on EVERY exit path from the icase evaluation, including the no-match early return — a leaked nocasematch would silently make every later case-sensitive rule on the same line case-insensitive; AC2's corpus tests this exact leak).
- `check_email_rule` — email extraction via `BASH_REMATCH`; `is_noreply_email` / trailer exemptions unchanged.
- `check_home_path_rule` — username extraction from a capture group instead of the `sed` fork.
- `is_named_trailer`, `is_trailer_line` — bash-native (`=~` or `case` glob), same accepted set.

Pinned constraints:

- **A1 — engine portability**: the scanner runs host-side on macOS (bash 3.2, BSD libc `regcomp`) AND in-container (bash 5, glibc). No bash-4+ features (no associative arrays, no `${var,,}`, no `mapfile`). No `\b` and no other GNU-only regex escapes inside any `[[ =~ ]]` pattern — POSIX `regcomp` does not guarantee them. The mdns rule `[A-Za-z0-9-]+\.local\b` must be rewritten to a provably-equivalent POSIX ERE (e.g. capture-group form matching `\.local` followed by end-of-string or a non-word character, with the snippet taken from the capture group so reported snippets are unchanged).
- **A2 — leftmost match parity**: current code takes `grep -oE … | head -n1` (first match on the line). `BASH_REMATCH[0]` (or the designated capture group) must yield the same matched substring for the same line. Where POSIX leftmost-longest vs grep behaviour could diverge on a rule, the Generator proves parity in the differential fixture rather than asserting it.
- **A2b — `set -e` survival**: the script runs under `set -euo pipefail`. Every `[[ $content =~ $pattern ]]` MUST be the condition of an `if`/`&&`/`||` construct (or otherwise guarded) — a bare `[[ … ]]` statement returning 1 on the no-match case (the overwhelmingly common case) would kill the whole scanner on the first clean line. Same guard discipline for any other new non-zero-returning statement.
- **A2c — no per-line subprocess forks (the point of the task)**: after the change, the five named functions (`check_rule`, `check_email_rule`, `check_home_path_rule`, `is_named_trailer`, `is_trailer_line`) contain NO pipeline or command substitution that forks on the per-line hot path — no `| grep`, `| sed`, `| awk`, `| head`, `$(printf …)`, `$(grep …)` etc. inside them. (`line_is_allowlisted` is exempt: it keeps `grep -qE` per A3 and runs only on candidate findings.) This is a permanent static test, not just a review note — see AC7.
- **A3 — allowlist semantics unchanged**: `line_is_allowlisted` keeps `grep -qE` (user-supplied EREs are a documented grep -E contract; it only runs on candidate findings, so it is off the hot path). `.vibe-content-guard-off`, `VIBE_CONTENT_GUARD=off` / `VIBE_ALLOW_COMMIT=1` override reporting, and the exit-code block are untouched.
- **A4 — output + exit contract frozen**: finding line format `<CLASS>\t<location>\t<rule>\t<snippet>` (snippet truncated at 60), all findings on stderr, stdout empty, exit 0/1 only (never 2).

## Part B — single-pass message scan

- **B1**: new scanner mode `--messages-stdin`: reads NUL-delimited records on stdin (each record = commit sha on the first line, raw message body as the remaining lines — produced by `git log --all -z --format='%H%n%B'`). Scans every message line with `scan_line … "commit <sha>" both` — same tier and trailer-exemption semantics as `--message`, but with the location emitted as `commit <sha>` directly (no awk rewrite needed). A record with an empty body is skipped without error. Malformed input (no sha line) must not crash the scanner (`set -euo pipefail` is active); skip the record.
- **B2**: `_audit_history` pass 2 becomes exactly one scanner invocation fed by one `git log --all -z --format='%H%n%B'` pipe, findings captured to `$tmp_messages` as today. The per-commit `while read sha` loop and `$tmp_msgfile` disappear (drop the dead mktemp/cleanup for it). Pass 1 (`--blob-stdin`) and pass 3 (`--identity` per unique email) are structurally unchanged.
- **B3**: message bodies containing lines that start with `commit ` (or `+`/`@@`/`+++`) must not be misattributed or misparsed — the NUL delimiter, not line-shape sniffing, is the record boundary. (This is why the mode cannot reuse `scan_blob_stdin`.)
- **B4**: `--message <file>` mode is retained unchanged (commit-msg hook depends on it), and `vibe-content-scan.sh`'s usage/error text plus the header comment block gain the new mode.

## Acceptance criteria

1. **Fidelity — real-history slice (hard gate)**: capture the bounded stream ONCE to a file (`git log -p --no-color --all | head -n 12000 > slice.txt`), then run the OLD scanner (from `git show <pre-change-sha>` where `<pre-change-sha>` = the commit immediately preceding the Generator's first commit for this task) and the NEW scanner each over that SAME captured file; finding lines, each set sorted with `LC_ALL=C sort`, are byte-identical. Never re-invoke `git log` between the two runs — commits landing mid-cycle would shift the window and fake a mismatch. (Bounded because the old scanner measures ~0.0085s/line — full history ≈ 8-10 min is over the test-tool timeout with no margin; 12k lines ≈ 2 min. A full-history old-vs-new diff MAY be run best-effort and reported, but the hard gate is the captured slice + AC2's corpus.)
2. **Fidelity — adversarial corpus**: a crafted corpus exercising EVERY rule id (`github-pat`, `openai-key`, `aws-access-key`, `private-key`, `secret-assignment` incl. mixed-case trigger words, `rfc1918-ip` all four octet families, `home-path` incl. `node`/`root` exclusions, `mdns-local` incl. boundary cases `foo.local`, `foo.localhost` (must NOT match), `foo.local.` and end-of-line, `email-address` incl. `noreply@anthropic.com` + `x@y.users.noreply.github.com` exemptions) plus both trailer exemption shapes, an allowlist suppression, AND the nocasematch-leak probe: a single line containing both a mixed-case `secret-assignment` trigger and an uppercase `FOO.LOCAL` token — the case-sensitive `mdns-local` rule must NOT fire on it (it would iff nocasematch leaked). Old vs new byte-identical per line (`LC_ALL=C sort`), via `--blob-stdin`, via `--staged` on a fixture repo, via `--message` on the corpus written to a file (direct parity for the commit-msg hook's mode), and via `--range` on the same fixture repo (covers the tier-`block` path the other entry points miss). The corpus MUST also include a block of lines matching no rule at all — the scanner must exit 0 with zero findings on it, which is the direct `set -e` survival proof for A2b (a bare unguarded `[[ =~ ]]` would die on the first clean line).
3. **Message parity**: for a fixture repo whose commit messages include a secret, PII, a `Co-authored-by:` trailer line, and a body line starting with `commit deadbeef`, the new pass 2 (`--messages-stdin` pipe) produces a byte-identical sorted finding set to the old per-commit `--message`+awk loop, with correct per-sha attribution. No normalisation step is permitted — both paths emit `commit <sha>` locations already; any difference is a bug, not a formatting artefact.
4. **Timing (hard gate)**: `vibe audit --history` on the vibe repo completes in under 60 seconds in-container (baseline: >280s timeout). Record the measured wall time in the test log.
5. **Exit codes**: `vibe audit --history` exits 1 iff a BLOCK finding exists in the aggregate; WARN-only exits 0 (both proven on fixture repos). Scanner modes `--staged`, `--message`, `--messages-stdin`, `--blob-stdin` (+ `--tier block`), `--range`, `--identity` each retain (or, for the new mode, establish) their 0/1 behaviour on crafted clean + dirty fixtures. `--messages-stdin` malformed-input handling is tested concretely: an empty record, a truncated final record, and a body-only record (no sha line) must neither crash the scanner nor produce misattributed findings.
6. **Override + opt-out**: `VIBE_CONTENT_GUARD=off` still exits 0 with the loud override line naming skipped rules under the new primitives; `.vibe-content-guard-off` still short-circuits to 0.
7. **Static shape checks (permanent suite members — they are history-independent and guard the fork-storm against reappearing)**: (a) the changed scanner contains no bash-4+ constructs and no `\b` (or other GNU-only escapes) inside `[[ =~ ]]` patterns — macOS bash 3.2 cannot be executed in-container, so this is the portability gate; (b) per A2c, the five named functions' bodies contain no per-line subprocess-forking idioms (pipeline or command-substitution calls to grep/sed/awk/head/printf-pipelines), `line_is_allowlisted` exempt. Extraction method pinned so the check is mechanical: each body is the text from the line matching `^<name>() {` to the first subsequent line matching `^}` (the scanner's uniform function style); within that text, assert no occurrence of the external-command names `grep`, `sed`, `awk`, `head`, `cut`, `tr` in ANY invocation form (piped, command-substituted, herestring/heredoc-fed, or bare), and no `$(` or backtick command substitution at all. Builtins (`printf` as a statement, `case`, `[[`) are fine; `$(printf …)` is not. This closes the direct-invocation loophole (`grep -qE … <<<"$content"` forks just as hard as a pipe). A false positive from a comment line mentioning those strings is acceptable and fixed by rewording the comment, not by loosening the check.
8. **No hook regression**: pre-commit/commit-msg/pre-push hook files are unmodified (they gain Part A's speed for free); `python3 code-check.py` clean; full pre-existing `python3 smoke-test.py` suite passes (no regressions).
9. **Docs + bookkeeping**: TODO.md item ticked, CHANGELOG.md entry under 2026-07-17, scanner header comment updated — all in the same commit as the code.

## Out of scope

- Path-scoped allowlisting / `# vibe-content-allow-file` markers (queued as its own task).
- `code-check.py` coverage of `devcontainer/git-hooks/` (separate task; do NOT touch `code-check.py`'s `scripts()` — smoke-test's `_patched_code_check()` fixture text-replaces its exact body).
- Any change to rule patterns' matching semantics, tier assignments, or new rules.
- Pass 3 (`--identity`) restructuring; hook file edits; awk/perl full rewrite of the scanner (forbidden — regex-semantic drift risk; only reach for it with a fresh spec if the 60s AC proves unreachable, which recon says it will not).
- Any `.vs/`-fixture allowlisting for the repo's own WARN findings (that is queue item 2).

## Test location

`smoke-test.py` — Tester appends new test functions following the existing `VIBE_SOURCE_ONLY`/fixture-repo patterns (see the task_019 scanner tests). Once committed, tests are immutable; Generator never edits `smoke-test.py`. The real-history slice differential (AC1) and the timing run (AC4) live in the Tester's log as one-offs — permanent tests must not depend on the vibe repo's own mutable history. The permanent suite members are: the AC2 corpus differential re-expressed as fixed expected-findings assertions (old-scanner comparison is one-off; the expected lines are frozen into the test), the AC3/AC5 fixture-repo tests, and the AC7 static shape checks (which are the permanent guard against the fork-storm quietly returning).

## Proposed budget

2 cycles — recon is complete and the change is bounded, but the fidelity gate is strict enough that one repair cycle is plausible.

## Model plan

- Generator: **opus**, ceiling opus. Rationale: security-scanner hot path where the whole risk is regex-engine equivalence judgment; sonnet's failure mode here (plausible-but-drifted patterns) is exactly what the fidelity gate would catch a cycle late. Fable rung: **not pre-authorised** (rationing on; task is scoped).
- Tester: **sonnet** start, ceiling sonnet. Rationale: the differential harness (old-vs-new scanner, fixture repos, corpus construction) exceeds haiku's demonstrated quality on this exact surface — haiku Testers failed quality twice on scanner-adjacent tasks (task_017 C1, task_019) and were escalated both times.
- Spec Critic: sonnet. Planner/Evaluator: session model (Fable 5 chair — Martin's /model choice; no credit-billed subagents).
