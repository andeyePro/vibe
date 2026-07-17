# Generator report — task_023: `path-warn:<glob>` allowlist entries

## What changed

- `devcontainer/git-hooks/vibe-content-scan.sh`:
  - `line_is_allowlisted` now structurally skips `path-warn:*` lines in its
    `case` guard (alongside `""`/`\#*`) — path-warn lines never reach the
    `grep -E` loop, whole line or stripped, in any code path (make-or-break
    constraint, AC3b).
  - New `PATH_WARN_GLOBS` global array + `load_path_warn_globs` (lazy,
    idempotent, single pass over `$ALLOWLIST_FILE`, no forks) +
    `file_is_path_warn <path>` (unquoted bash `case`-style glob match, no
    external command).
  - `scan_diff_stream` gains `current_file_tier`, set to the mode's tier at
    each `+++ b/<path>` header and demoted to `block` when the path matches
    a path-warn glob — a one-way floor (BLOCK rules run unconditionally
    inside `scan_line` regardless of tier, so only WARN-class rules are
    ever suppressed; `--range` is already `block`, so the demotion is a
    provable no-op there, AC3c). `scan_blob_stdin`, `scan_messages_stdin`,
    `--message`, `--identity` are untouched — no file path exists in those
    modes (AC4).
  - Header comment + usage block documents the new entry kind, glob
    semantics, tier-demotion mechanism, and mode applicability.
- `.vibe-content-allow`: appended `path-warn:.vs/*` and
  `path-warn:smoke-test.py` with a scope comment (harness prose +
  runtime-fixture file that deliberately hold WARN-class example literals).
- `devcontainer/claude-md/content-guard.md`: new `## Per-file WARN
  allowlist: path-warn:<glob> entries (task_023)` section — syntax, glob
  semantics (`*` crosses `/`, metachar escaping caveat), empty-glob and
  `path-warn:*` degenerate cases, the ERE-loop structural exclusion and
  why it matters, diff-modes-only scope, the stale-scanner back-compat
  caveat (a pre-task_023 scanner falls back to whole-line ERE matching, so
  `path-warn:smoke-test.py` only suppresses content containing that exact
  literal text — narrow, accepted, documented), and the two shipped
  entries.
- `CHANGELOG.md`: 2026-07-17 entry (newest, above the existing task_022
  entry for the same date).
- `.vs/tasks.json`: `task_023.implementation_status` → `"complete"` (status
  field only, surgical edit — did not run the whole file through a JSON
  formatter, which would have reformatted all ~40 other task entries and
  produced a 320-line noise diff; caught and reverted before finalizing).

Per the harness's explicit file scope for this Generator run, `TODO.md`,
`smoke-test.py`, `code-check.py`, and the hook files (`pre-commit` etc.)
were NOT touched — `TODO.md`'s tick and `smoke-test.py`'s permanent tests
are left for the Tester/finalizer stage.

## AC-by-AC

All 9 ACs verified via a scratch differential/fixture harness at
`.vs/cycle-1/scratch-tests/` (gitignored, not committed — `run-tests.sh`
+ `old-scanner.sh` + `fixture-repo/`), TDD red-then-green:

1. **Parser / differential**: `AC1` — old scanner (`git show HEAD:...`)
   vs new, `LC_ALL=C sort`-compared, byte-identical on an allowlist with
   no `path-warn` entries. PASS.
2. **`--staged` suppression**: matching-file WARN suppressed exit 0;
   non-matching-file control still WARNs exit 1; 3-levels-deep nested path
   (`.vs/archive/task_099/critiques/foo.md` under `path-warn:.vs/*`)
   suppressed; empty-glob line (`path-warn:`) matches nothing, no crash.
   PASS (4/4 sub-cases).
3. **BLOCK never path-suppressible**: runtime-built `ghp_`-shaped token in
   a path-warn-matched file → BLOCK + exit 1, both `--staged` and
   `--range`. PASS.
3b. **No ERE double-parse**: BLOCK secret on a line also containing the
   literal text `smoke-test.py`, and separately the literal text
   `path-warn:smoke-test.py`, in a NON-matching file, with
   `path-warn:smoke-test.py` in the allowlist — BLOCK still fires both
   times, proving path-warn lines never reach the ERE loop in either form.
   PASS (2/2 sub-cases).
3c. **`--range` idempotency**: `--range` output on a dirty fixture,
   byte-identical with and without `path-warn:fixtures/*` present (`--range`
   is already block-tier, so the floor is a no-op). PASS.
4. **Non-diff modes unaffected**: `--message`, `--blob-stdin`,
   `--messages-stdin`, `--identity` — old vs new scanner byte-identical
   with `path-warn:*`/`path-warn:fixtures/*` present in the allowlist.
   PASS (4/4 sub-cases).
5. **Self-clean end-to-end**: fixture simulating vibe's shape with the
   shipped entries — WARN-class literals in `.vs/spec.md` and
   `smoke-test.py` → exit 0, no findings, no override; planted PAT in the
   same two files → exit 1 with a `github-pat` finding. PASS (2/2
   sub-cases).
6. **Audit integration**: `vibe audit --history` (run directly via `bash
   ./vibe audit --history` against the real vibe repo — the audit
   subcommand is plain bash calling the same scanner, no host-only
   dependency) completed in ~28s, well under the 60s gate, no blow-up;
   `--blob-stdin` (history's content pass) doesn't consult path-warn at
   all, per design, so history output is unaffected by the new entries.
7. **Static shape guards**: task_022's permanent smoke checks (no
   `declare -A`, no `mapfile`/`readarray`, no `${var,,}`, no `\b`, no
   forks/command-substitution in the five named hot-path functions) all
   still pass unmodified — `load_path_warn_globs`/`file_is_path_warn` are
   new functions outside that fixed list but were independently written
   fork-free (bash `case`/`for`/string-expansion only).
8. **Suite + lint**: `shellcheck devcontainer/git-hooks/vibe-content-scan.sh`
   clean; `python3 code-check.py` clean (15 files, doesn't see the
   git-hooks dir, as documented); `python3 smoke-test.py` full suite green,
   zero regressions.
9. **Docs + bookkeeping**: content-guard.md updated; scanner header/usage
   comment updated; CHANGELOG.md entry added. `TODO.md` intentionally NOT
   ticked here (out of this Generator run's file scope — see above).

## Commands run (chronological, key ones)

```
bash /workspace/.vs/cycle-1/scratch-tests/run-tests.sh   # red, then green (16/16)
shellcheck devcontainer/git-hooks/vibe-content-scan.sh   # rc=0
python3 code-check.py                                    # rc=0, 15 files
time python3 smoke-test.py                                # green, 38.8s
time bash ./vibe audit --history                          # ~28s, no blow-up
```

## Timings

- `run-tests.sh` (16 scratch AC checks incl. two differentials): a few
  seconds; one transient overlayfs "unable to get current working
  directory" hiccup on rapid `rm -rf`+`mkdir` fixture resets, reproduced
  in isolation as NOT a real bug (isolated repro passed clean), confirmed
  by an immediate clean re-run (16/16 green, twice).
- `python3 smoke-test.py`: 38.8s wall, full suite green.
- `bash ./vibe audit --history` on the real vibe repo: ~27.7s wall
  (task_022 baseline ~22s; within normal variance, well under the 60s
  gate — no blow-up).

## Deviations from spec

None functionally. Two scoping notes, both per this run's explicit
instructions rather than the spec's literal AC9 wording:
- `TODO.md` was not ticked (explicitly excluded from this Generator's file
  scope; spec AC9 nominally asks for it in the same commit, but no commit
  is made by this Generator role — deferred to the finalizer).
- `.vs/tasks.json` was edited surgically (targeted string replace) rather
  than via a JSON dump/reformat, to avoid an unrelated ~320-line
  reformatting diff across every other task entry (caught during
  verification, reverted, redone minimally).

No `VIBE_CONTENT_GUARD=off` overrides were needed at any point.
