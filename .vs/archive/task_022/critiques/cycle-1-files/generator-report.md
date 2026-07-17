# Generator report — task_022 (cycle 1)

Model: opus. Files changed: `devcontainer/git-hooks/vibe-content-scan.sh`, `vibe`,
`CHANGELOG.md`, `.vs/tasks.json`. NOT touched: `smoke-test.py`, `code-check.py`, `TODO.md`.

## What changed

### Part A — match primitives (scanner)
- `check_rule`: `printf | grep -o(i)E | head -n1` → `[[ $content =~ $pattern ]]` +
  `BASH_REMATCH[0]`. icase handled by `shopt -s nocasematch … shopt -u nocasematch`,
  the `-u` running on every path out of the icase branch (no leak). Match guarded by
  `&& m=…` for set -e survival. Signature unchanged.
- `check_email_rule`: email extraction via `BASH_REMATCH[0]`; trailer/noreply exemptions
  unchanged.
- `check_home_path_rule`: username now from capture group 2 (`/(Users|home)/([^/ ]+)/`),
  replacing the `sed` fork; full snippet from group 0.
- `is_named_trailer` / `is_trailer_line`: bash-native `[[ =~ ]]` (nocasematch for the
  named-trailer icase), same accepted sets.
- `mdns-local`: moved out of `check_rule` into a dedicated `check_mdns_rule` because the
  GNU `\b` needed a capture-group rewrite. POSIX-ERE form
  `([A-Za-z0-9-]+\.local)([^A-Za-z0-9_]|$)`, snippet = group 1 (excludes the boundary
  char). `foo.localhost` correctly does not match; `foo.local.` and end-of-line `.local`
  do. `check_rule`'s signature/behaviour for the other rules is untouched.

### Part B — single-pass message scan
- New scanner mode `--messages-stdin` (`scan_messages_stdin`): reads NUL-delimited
  `<sha>\n<body>` records via `read -r -d ''`, scans each body line as
  `scan_line "$line" "commit $sha" both` using a here-string (no fork, runs in the
  scanner's own shell so FOUND survives). Empty body / sha-only / malformed (no sha)
  records skipped; NUL is the sole record boundary, so `commit …`/`+…` body lines are
  scanned as content (B3). Usage/error text + header comment updated.
- `vibe` `_audit_history` pass 2: the fork-per-commit `--message`+awk loop and its dead
  `tmp_msgfile` removed; replaced by one
  `git log --all -z --format='%H%n%B' | "$scanner" --messages-stdin 2>>"$tmp_messages"`.
  Passes 1 and 3 structurally unchanged.

## AC compliance

- **AC1 (real-history slice, hard gate):** captured `git log -p --no-color --all | head -n 12000`
  ONCE to `slice.txt`; old scanner vs new scanner over the same file → **35 findings,
  byte-identical** (`LC_ALL=C sort` diff clean).
- **AC2 (adversarial corpus):** `scratch-tests/corpus.txt` exercises every rule id, every
  octet family, node/root exclusions, mdns boundary cases (`foo.local`, `foo.localhost`
  no-match, `foo.local.`, end-of-line, `bar-baz.local`), email + both noreply exemptions,
  both trailer shapes, an allowlist suppression, the clean block, and the nocasematch-leak
  probe (mixed-case secret trigger + `FOO.LOCAL` on one line → mdns does NOT fire).
  Old vs new byte-identical via `--blob-stdin` (22), `--blob-stdin --tier block` (10),
  `--message` (22), `--staged` (23), `--range` (10). Clean block exits 0 (A2b proof).
- **AC3 (message parity):** fixture repo (secret, PII, `Co-authored-by:`, body line
  `commit deadbeef …`) old per-commit loop vs new `--messages-stdin` → byte-identical,
  correct per-sha attribution. Also verified on the **real vibe repo history**: old loop
  vs new pipe both = 2 findings, byte-identical.
- **AC4 (timing, hard gate):** `vibe audit --history` = **20.7s** wall in-container (was
  >280s). Under 60s with wide margin.
- **AC5 (exit codes / malformed):** `--messages-stdin` returns 1 on a BLOCK/WARN finding,
  0 clean; empty record, truncated final record, and body-only (no sha) record each
  neither crash nor misattribute (tested concretely). `vibe audit --history` exit 1
  (pre-existing BLOCK content in repo history — unchanged).
- **AC6 (override + opt-out):** `VIBE_CONTENT_GUARD=off` → exit 0 with the loud override
  line naming `secret-assignment`; `.vibe-content-guard-off` → immediate exit 0.
- **AC7 (static shape):** all five named functions FORK-FREE (no grep/sed/awk/head/cut/tr,
  no `$(`/backtick) — comments reworded to clear false positives. No `\b` or bash-4
  constructs in the scanner (mdns rewritten; no `${v,,}`/mapfile/`declare -A`).
- **AC8 (no regression):** hook files unmodified; `python3 code-check.py` clean (15 files);
  `shellcheck` on the scanner clean; full `python3 smoke-test.py` **passed (39s, exit 0)**.
- **AC9 (docs):** CHANGELOG entry under `## 2026-07-17` (newest at top); scanner header +
  usage text updated. TODO.md intentionally not ticked (chair closes at cycle end).

## Measured timings
- Old scanner slice: 94150 ms / 12000 lines = 0.00785 s/line.
- New scanner slice: 3996 ms / 12000 lines = 0.000333 s/line → ~24x faster, 35 findings.
- Full `vibe audit --history`: 20658 ms (target <60s).

## Commands run (key)
- `git show HEAD:…vibe-content-scan.sh > old-scanner.sh` (baseline; pre-change sha
  a99a8930).
- `bash .vs/cycle-1/scratch-tests/runner.sh` (5-mode differential harness).
- AC1 slice capture + old/new differential; ms timings via `date +%s%3N`.
- `./vibe audit --history` (timed).
- `python3 code-check.py`; `shellcheck` on scanner; `python3 smoke-test.py`.

## Deviations from spec
None. mdns handled via a dedicated `check_mdns_rule` (not a `check_rule` signature change),
consistent with the existing `check_email_rule`/`check_home_path_rule` precedent for rules
needing capture-group extraction; the five AC7 functions and `check_rule`'s contract are
byte-for-byte preserved.

Scratch harness under `.vs/cycle-1/scratch-tests/` (gitignored). `diff.patch` written to
`.vs/cycle-1/diff.patch` (not committed — chair commits after evaluation).
