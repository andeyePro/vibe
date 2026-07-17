# Generator report — task_024, cycle 1

Hunk-aware diff parsing in both stream parsers of
`devcontainer/git-hooks/vibe-content-scan.sh`. Closes the added-line
header-spoof hole (task_019 pre-existing + task_023 review INFO) in
`--staged`/`--range`/`--blob-stdin`.

## Baseline

- Pinned sha (`.vs/cycle-1/pre-change-sha.txt`): `c1513945a35309138fd3e9893b0ce0f1177c4275`
- Every differential runs against `git show <sha>:devcontainer/git-hooks/vibe-content-scan.sh`
  (captured at `.vs/cycle-1/scratch-tests/scanner-OLD.sh`).

## Files changed (this Generator)

- `devcontainer/git-hooks/vibe-content-scan.sh` — header comment + both
  stream parsers (`scan_diff_stream`, `scan_blob_stdin`).
- `CHANGELOG.md` — 2026-07-17 task_024 entry, newest at top.
- (bookkeeping) `.vs/tasks.json` task_024 `implementation_status` →
  `complete` (status field only).
- NOT touched: `smoke-test.py` (Tester), `code-check.py`, `TODO.md`, `vibe`,
  hook files.

## Design implemented

State machine keyed on the `@@ -a[,c] +b[,d] @@` count fields (git-generated,
un-forgeable). On a real hunk header: `old_remaining=c` (default 1 when
omitted, `,0` legal), `new_remaining=d`. While `old_remaining+new_remaining>0`
the parser is INSIDE the hunk and classifies purely by first byte:

- empty (zero-byte) line → suppressBlankEmpty context, decrement BOTH
  (checked BEFORE prefix classification);
- `\` → `\ No newline…`, decrement nothing, not scanned;
- `-` → decrement old_remaining;
- `+` → decrement new_remaining AND scan as content (strip exactly one `+`);
- space / any other byte → context, decrement BOTH (drains budget → never
  wedges inside on malformed bodies).

Header classification (`+++ `, `commit `, `@@ `) runs ONLY when both counters
are zero. Malformed `@@` (regex non-match) fails safe: not-a-header, counters
stay zero, scanning continues under the prior state — no `set -e` death, no
unbounded inside-state. EOF mid-hunk tolerated.

Regex is a POSIX ERE held in a variable so literal spaces survive the
unquoted-RHS `[[ =~ ]]` match (`^@@ -([0-9]+)(,([0-9]+))? [+]([0-9]+)(,([0-9]+))? @@`);
`BASH_REMATCH[3]`/`[6]` give the optional counts, `[4]` gives the new-file
start line for `scan_diff_stream`'s `current_line`.

### Reconciliation with the frozen task_022 blob-stdin corpus

The task_022 permanent test feeds `scan_blob_stdin` a *synthetic* stream —
`commit <sha>` + bare `+lines`, **no `@@` header**. The old parser scanned
any `+`-prefixed non-header line as content regardless of hunk state. To keep
that frozen multiset byte-identical, `scan_blob_stdin`'s OUTSIDE-hunk branch
still scans bare `+*` lines as content (after the `+++ `/`---` noise cases).
In real `git log -p`, every added line sits inside a hunk, so this
outside-hunk path is inert there and the spoof fix (a `+++ …`/`+@@ …` added
line) is handled exclusively by the INSIDE-hunk classification. This is the
only reconciliation the design required beyond the spec's literal wording.

### Portability / safety

Builtin-only on the per-line path (`[[ =~ ]]` + `BASH_REMATCH`, `case`,
parameter expansion — no forks). No arrays introduced (nounset-safe by
construction; the pre-existing `commit`-line `awk` is unchanged, off the
content-line path). Decrements use the codebase's proven `[ … ] && …` idiom
(set -e-safe: the `[` is a non-final `&&` element). Case pattern for the
backslash line is `\\)` (SC1003-clean). No `\b`, no bash-4 constructs
(task_022 AC7a static guards green).

## Acceptance criteria — results

Scratch harness `.vs/cycle-1/scratch-tests/run.sh` (real git repos +
hand-built streams, all secrets runtime-built; gitignored). **17/17 green.**

- **AC1** skip-state spoof (`++ /dev/null`): BLOCK fires with correct path,
  exit 1, in `--staged` AND `--range`. PASS.
- **AC2** tier/file flip spoof (`++ b/.vs/x`) with `path-warn:.vs/*`
  allowlist: WARN rfc1918-ip still fires, attributed to real path
  `src/app.txt`, exit 1. PASS.
- **AC3** spoofed content itself scanned (`++ token: ghp…` → rendered
  `+++ token:…`): BLOCK in `--staged` AND `--blob-stdin` (old parser missed
  the blob-stdin case — delta confirmed by running OLD: exit 0). Forged-budget
  probe (`+@@ -99,5 +99,5 @@`) scanned as content, does NOT re-arm counters,
  subsequent real headers keep correct attribution. PASS.
- **AC3b** zero-byte suppressBlankEmpty context exploit: empty context line in
  file A does not leak budget; BLOCK secret in file B attributed to B. Proven
  hand-built AND via real `git -c diff.suppressBlankEmpty=true diff`. PASS.
- **AC4** deleted-line two-line dance (`-- a/x` then `++ b/evil`): does not
  flip file; later real secret keeps correct path/exit. PASS.
- **AC5** real multi-file `--staged` differential (modify+add, delete, new
  file, no-trailing-newline file): NEW == OLD byte-identical
  (`LC_ALL=C sort`). PASS.
- **AC6** history objective oracle: full `git log -p --no-color --all |
  head -n 12000` slice, NEW vs OLD. One difference, **automatically traced**
  by the harness to a `+++ `-prefixed slice line (line 7612, commit
  `401bf18`: an added `++ …/Users/myname/…` line the old parser dropped as
  header noise, now scanned as content → one new WARN home-path). Zero
  untraceable differences, zero OLD-only findings. PASS. Extended to the FULL
  92,681-line history: identical result — that single WARN delta and **zero
  new BLOCK findings** across all history (the audit's pre-existing 57 BLOCK
  history fixtures and its exit code are unchanged by this change).
- **AC7** U3 context lines: context/removed decrement counters and are not
  scanned; exactly one BLOCK from the single `+` line. PASS.
- **AC8** malformed-header fail-safe: `@@ -abc,def +xyz @@` and truncated
  `@@ -5,` neither crash (no `set -e` death) nor wedge — a real `+++ b/…`
  header after them is classified normally and the following secret is caught
  with correct attribution. PASS.

## Gates (AC9)

- `shellcheck devcontainer/git-hooks/vibe-content-scan.sh` — CLEAN (direct).
- `python3 code-check.py` — clean, 15 files.
- `python3 smoke-test.py` — full suite green, zero regressions (task_022
  no-fork/no-`\b`/no-bash-4 shape + frozen corpus, task_023's 19 functions).
- `vibe audit --history` — exit 1 (pre-existing BLOCK history fixtures),
  ~30s on the vibe repo (< 60s gate).

## Docs (AC10)

- Scanner header comment documents the hunk-aware contract (task_024 block).
- CHANGELOG 2026-07-17 entry added.
- TODO.md hardening tick deliberately NOT done here — this Generator's file
  scope excludes TODO.md per its task brief; flag for the Evaluator if the
  tick is wanted in the closing commit.

## Notes for Tester

- Permanent tests belong in `smoke-test.py` (append-only, runtime-built
  literals). The spoof fixtures (AC1–AC4, AC8) and the AC6 objective-oracle
  differential are the freeze targets; the scratch harness is a log, not a
  committed test.
- The one deliberate more-findings delta is `--blob-stdin`/history only for
  `+++ `-shaped added lines; `--staged`/`--range` gain the skip-state and
  tier-flip fixes. All spoof-free corpora are byte-identical vs the pinned sha.
