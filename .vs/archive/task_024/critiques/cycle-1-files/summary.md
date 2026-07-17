# Tester summary — task_024 (hunk-aware diff parsing), cycle 1

**Totals:** 17 new permanent AC1-AC10 checks added to `smoke-test.py` (all pass), full suite 1699 passed / 1 failed, exit 1. `python3 code-check.py` clean (15 files), direct `shellcheck` clean.

**Regressions:** none. The one failure (`[task_024 AC10] the hardening item is no longer open ('- [ ]') in TODO.md`) is not a code regression - it is a genuine, unfixed Generator omission: TODO.md line 52's "harden `scan_diff_stream` against added-line header spoofing" item is the exact backlog entry this task closes and is still `- [ ]` (CHANGELOG.md's task_024 entry IS present and correct). Not caused by, or fixable by, the Tester.

**AC6 objective-oracle verdict: PASS.** `git log -p --no-color --all | head -n 12000` old-vs-new (`--blob-stdin`, `LC_ALL=C sort`) diff = exactly ONE line: a new `WARN home-path /Users/myname/` finding for commit `401bf18d`. Binary-search isolation traced it to stream line 7612, `+++        test_file.write_text("Path to config: /Users/myname/project\n")` - an added line inside a real hunk (an archived `diff.patch` file being committed) whose raw text happens to render `"+++ "` (three plus + space), which the OLD parser's shape-based header case swallowed as noise; the NEW hunk-aware parser correctly stays inside the real hunk budget and scans it as content. This is the exact spoof-shaped-line class AC1/AC3 exist to fix, occurring organically in the repo's own history - a deliberate, spec-sanctioned MORE-findings change, not a regression. Zero other differences; both exit 1; no crash.

**AC9 timing:** `vibe audit --history` ran in 30.3s (under the 60s gate).

**Coverage gaps / notes for the Evaluator:**
- AC10's TODO.md tick is outstanding (see Regressions note) - Generator follow-up needed, one line.
- AC6/AC5 differentials and AC9 timing are one-offs per spec ("Test location"), logged in `test-output.log`, not added as permanent tests (they'd depend on this repo's own mutable history).
- Full raw command output, including the AC6 trace and both differentials, is in `test-output.log`.
