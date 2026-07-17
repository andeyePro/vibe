# Spec — task_025: `code-check.py` shellchecks `devcontainer/git-hooks/` (via a fixture-safe env seam)

## Task summary

`code-check.py`'s `scripts()` lists the shell files to shellcheck but omits `devcontainer/git-hooks/` — the content-guard scanner + the three git hooks, all hardened across task_019/022/023/024, have no standing `python3 code-check.py` coverage (each iteration had to shellcheck the scanner by a separate direct invocation). Extending `scripts()` is blocked by a landmine: `smoke-test.py`'s `_patched_code_check()` rewrites `scripts()` by a LITERAL source-text `.replace()` of its exact current body, so any edit to `scripts()` silently no-ops the patch (leaving the real-repo glob) and breaks the JSON-count fixture tests. The fix does both together: add coverage AND replace the brittle text-patch with a stable env-var seam so future `scripts()` edits never break the fixture again.

## Pinned contract (so Generator and Tester build to the same seam without seeing each other's work)

- **Env seam**: `code-check.py`'s `scripts()` checks environment variable `CODE_CHECK_SCRIPTS` FIRST. If set to a non-empty string, it returns exactly the `os.pathsep`-separated list of paths it contains, as `Path` objects, in order, with NO globbing and NO `.exists()` filtering (the caller is declaring the exact target set — a non-existent path in the override is the caller's error to surface, matching how the fixture feeds deliberately-crafted temp files). If the variable is unset OR the empty string, `scripts()` computes the default set (below).
- **Named shebang predicate (pinned, importable)**: `code-check.py` defines a module-level `is_shell_script(path: Path) -> bool` — the sole shebang test, so the Tester imports and calls it directly for AC2 (the env seam bypasses the default branch, so the predicate MUST be independently callable). Contract: read the file's first line defensively (`open(..., 'r', errors='ignore')`, read one line; ANY OSError/UnicodeError, or an empty/first-lineless file → return `False`, never raise). Return `True` iff the first line starts with `#!` AND the basename of the interpreter resolves to a known shell. Interpreter resolution (every step guards against a missing token — a short/degenerate shebang returns `False`, never raises or index-errors): strip `#!`, split the remainder on whitespace into tokens. If there are ZERO tokens (bare `#!`, or `#!` followed by only whitespace) → `False`. Let `first = basename(tokens[0])`. If `first != "env"` → the interpreter basename is `first`. If `first == "env"`: take the FIRST token in `tokens[1:]` that does NOT start with `-` (this skips option tokens such as the `-S` in `#!/usr/bin/env -S bash -x`), and use its basename as the interpreter. (The rare bundled `-Sbash` single-token form is not a hook shape in this repo and is out of scope — it would resolve to `False`, harmless.) If no such token exists (`#!/usr/bin/env` alone, or `#!/usr/bin/env -S` with nothing after) → `False`. Known-shell whitelist (exact basename match, case-sensitive): `sh`, `bash`, `dash`, `ksh`, `zsh`, `ash`. This EXCLUDES `fish` (the `"sh" in "fish"` substring false-positive the brief flagged — `fish`'s basename is `fish`, not in the set) and `python`/`perl`/etc. `csh`/`tcsh` are deliberately omitted (not shellcheck targets); add only if a real csh hook ever appears.
- **Default set (env unset), one pinned algorithm**: build a single list = `[vibe, install.sh]` + `sorted(devcontainer/*.sh)` + `sorted(devcontainer/hooks/*.sh)` + the git-hooks contribution, then `.exists()`-filter the whole list (as today). The git-hooks contribution is: `sorted(p for p in devcontainer/git-hooks/ NON-recursively if p.is_file() and is_shell_script(p))` — ONE flat shebang-gated pass over the directory (NOT a separate `*.sh` glob), so a hypothetical shebang-less `.sh` file would be excluded and ordering is a single `sorted()` by path within the git-hooks block (`commit-msg`, `pre-commit`, `pre-push`, `vibe-content-scan.sh` in that sorted order). This block is appended after the `hooks/*.sh` block; the four fixed entries keep their existing relative positions.
- **`os` import**: `code-check.py` gains `import os` (currently absent).

## Files in scope

- `code-check.py` — `scripts()` env seam + git-hooks default coverage + `import os`.
- `smoke-test.py` — Tester reshapes `_patched_code_check()` (and only that helper + any of its own call sites needed) to drive code-check via `CODE_CHECK_SCRIPTS` instead of source-text replacement. This is a SANCTIONED fixture amendment (the freeze-anchor exception: a frozen fixture that blocks legitimate work is amended, not worked around) — every EXISTING assertion that used it must stay semantically identical and green. Append new coverage tests too.
- `TODO.md` (tick the 2026-07-15 item) + `CHANGELOG.md` (2026-07-17 entry) — same commit.

## Acceptance criteria

1. **git-hooks covered (default)**: with `CODE_CHECK_SCRIPTS` unset, `scripts()` (invoked in-process or via `python3 code-check.py --json` and inspecting `files_checked`) includes all four `devcontainer/git-hooks/` files — `vibe-content-scan.sh`, `commit-msg`, `pre-commit`, `pre-push` — by their repo-relative paths.
2. **Shebang predicate (unit-tested directly)**: import `is_shell_script` and assert against crafted temp files: `#!/usr/bin/env bash` with no `.sh` extension → `True`; `#!/bin/sh`, `#!/bin/bash`, `#!/usr/bin/env zsh` → `True`; `#!/usr/bin/env fish` → `False` (the substring false-positive); `#!/usr/bin/python3` → `False`; a first line not starting `#!` → `False`; an empty file → `False`; a non-UTF-8/binary first line → `False` (no exception raised); and the degenerate-shebang cases: `#!/usr/bin/env -S bash -x` → `True` (skips the `-S` option, resolves `bash`), `#!/usr/bin/env` alone → `False`, bare `#!` (nothing after) → `False`, `#!   ` (only whitespace) → `False` — none may raise.
3. **Env seam exact-list**: with `CODE_CHECK_SCRIPTS` set to two `os.pathsep`-separated paths (one of them non-existent), `scripts()` returns exactly those two `Path`s in order — no globbing, no dedup, no `.exists()` drop. Any env mutation in this test is subprocess-scoped (passed via `run(env=...)`) or wrapped in try/finally restoring the prior value — the parent process's `os.environ["CODE_CHECK_SCRIPTS"]` MUST NOT leak into later tests in `main()`'s fixed sequence (two frozen tests, `test_learning_code_check_clean` and `test_task009_code_check_clean`, run a bare `code-check.py` later and would inherit a leaked override).
4. **Empty/unset env falls through**: `CODE_CHECK_SCRIPTS` unset OR set to empty string → the default set (AC1) is used.
5. **Real run green**: `python3 code-check.py` (default set, now including git-hooks) exits 0 — all four git-hooks files are shellcheck-clean today (the scanner is verified clean every prior iteration; the three hooks were shellcheck-clean at task_019). `python3 code-check.py --json` stays a single valid JSON object with the documented keys, and `summary.files` reflects the larger set.
6. **Fixture reshape preserves existing behaviour**: the three existing tests that use `_patched_code_check` — `test_code_check_json_finding_schema`, `test_code_check_json_findings_exit1_and_count`, `test_code_check_json_summary_counts` (grep-verified; the clean-exit test does NOT use it) — still pass with identical assertions after the helper is reshaped to the env seam, because the seam feeds the same explicit path sets (e.g. exactly `[bad]`, `[bad1, bad2, good]`).
7. **No source-text-match fragility remains**: `_patched_code_check` (however reshaped) contains no `.replace(` call whose argument text includes the substring `def scripts()` — grep/AST-proven absent — so a future edit to `scripts()`'s body can never silently no-op the fixture again. The regression guard targets the PATTERN (a `.replace` keyed on `scripts()`'s source), not one literal string.
8. **Suite + lint**: full `python3 smoke-test.py` green (zero regressions, incl. task_022/023/024's scanner tests), `python3 code-check.py` clean, and `code-check.py` itself passes `python3 -m py_compile` (it is Python, not shell, so shellcheck does not cover it — the compile check is the lint gate for the changed file).
9. **Docs + bookkeeping**: TODO 2026-07-15 item ticked (removed from Open); CHANGELOG 2026-07-17 entry; same commit as code.

## Out of scope

- Any change to shellcheck invocation, severity handling, `--json` schema keys, or the findings format beyond the larger file set.
- Recursion into subdirectories of `git-hooks/` (there are none; keep it a flat listing like the existing `hooks/` handling).
- The scanner/hook shell logic itself (untouched — this is pure test-infrastructure coverage).
- `vibe` launcher, mount-drift (queue item 4), firewall/guards/settings (hard-escalate; not touched).
- Making `scripts()` env seam do anything security-sensitive — it is a dev-lint file selector; default/CI behaviour is unchanged when the var is unset.

## Test location

`smoke-test.py` — Tester appends new tests AND performs the sanctioned `_patched_code_check` reshape (the one existing helper this task must touch, per the pinned contract). All literals runtime-built where they would otherwise trip the content guard. Frozen after commit.

## Proposed budget

2 cycles.

## Model plan

- Generator: **sonnet**, ceiling opus. Rationale: bounded Python change against a pinned seam contract; no regex-engine or security-boundary judgment. Fable rung: **not pre-authorised**.
- Tester: **sonnet**, ceiling sonnet (the fixture reshape + count-invariance is the fiddly part; haiku's quality history on this repo's test surface is poor — task_017/019).
- Spec Critic: sonnet. Planner/Evaluator: session model (Fable 5 chair).

## Note — not security-review-gated

Unlike task_022/023/024, this task does not touch the scanner, hooks, guards, firewall, or credential paths — it changes a dev-lint file-selector and its test fixture. The standard Evaluator diff read covers it; no `security-review` agent dispatch required.
