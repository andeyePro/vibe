# task_023 Tester summary — cycle 1

Total checks (full `python3 smoke-test.py` run): 1656 passed / 0 failed (exit 0).
`python3 code-check.py`: clean across 15 files (exit 0).

19 new permanent task_023 test functions appended to `smoke-test.py` (append-only, after the
task_022 section, before `main()`), covering: AC1 (ERE-regression corpus with path-warn lines
interspersed + prefix whitespace tolerance), AC2 (all 4 WARN categories matching-vs-non-matching,
3-level nested-path glob, empty-glob no-op), AC3 (BLOCK fires under path-warn, staged + range), AC3b
(no ERE double-parse, full-line and stripped-prefix literal-collision variants), AC3c (`--range`
byte-identical with/without path-warn entries), AC4 (`--message`/`--blob-stdin`/`--messages-stdin`/
`--identity` byte-identical regardless of path-warn presence), AC5 (self-clean end-to-end fixture
simulation, clean + planted-secret cases), AC7 (path-warn-specific no-fork shape guards on
`load_path_warn_globs`/`file_is_path_warn`/`scan_diff_stream`), plus `path-warn:*` repo-wide-accept
and `?` glob-metacharacter sanity. All WARN/BLOCK-shaped literals built at runtime (string
concatenation), never embedded raw.

Regressions: none. All pre-existing tests (task_017/019/020/021/022 and earlier) still pass; no
implementation, existing test, or `code-check.py` files were modified.

One-offs (logged in `test-output.log`, not permanent tests):
- AC1 differential vs OLD scanner (`git show HEAD`) on a no-path-warn allowlist: byte-identical
  across `--message`/`--staged`/`--blob-stdin`.
- AC4 differential vs OLD scanner on the non-diff modes WITH path-warn entries present in the
  allowlist: byte-identical (path-warn is invisible there on both old and new scanners).
- Direct `shellcheck devcontainer/git-hooks/vibe-content-scan.sh`: clean (exit 0).
- `vibe audit --history`: 27.4s (task_022 baseline ~22s preserved, well under the 60s AC6 gate),
  exit 1 on pre-existing WARN-only history findings (not a regression — `--history` scans both
  tiers by design, unaffected by path-warn since no file path exists there).
- AC5/AC9 real-tree check: cloned `/workspace`, applied the Generator's uncommitted diff, staged a
  WARN-class literal edit in `.vs/spec.md` + `smoke-test.py` in the clone only — `--staged` exits 0
  with no findings and no override, confirming self-clean with the shipped `.vibe-content-allow`
  entries. Real `/workspace` index/working tree verified unmodified by this check.

Coverage gaps / notes for the Evaluator:
- `TODO.md` still shows the task_023 entry as `[ ]` (not yet ticked) despite `CHANGELOG.md` already
  carrying the 2026-07-17 entry and `.vs/tasks.json` marking `implementation_status: complete` —
  spec AC9 calls for both to land in the same commit. Out of scope for the Tester to fix (would mean
  editing a non-test file); flagging for the Evaluator/Generator to close before commit.
- AC9's content-guard.md doc-content wording wasn't independently re-verified beyond confirming the
  `path-warn` section exists and is non-trivial (grep only) — not in the Tester's assigned permanent-
  test list.
