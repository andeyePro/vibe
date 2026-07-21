# Generator report — task_025

## Contract point-by-point

1. **`import os`** — added at top of `code-check.py`, alongside existing stdlib imports.
2. **`is_shell_script(path: Path) -> bool`** — module-level function. Reads first line via `open(path, "r", errors="ignore")`, catches `(OSError, UnicodeError)` → `False`. Empty file / no `#!` prefix → `False`. Tokenizes `first_line[2:].split()`; zero tokens → `False`. `first = Path(tokens[0]).name`; if `!= "env"` that's the interpreter; if `== "env"`, scans `tokens[1:]` for the first token not starting with `-`, uses its basename, `None` (no such token) → `False`. Membership test against `KNOWN_SHELLS = {"sh","bash","dash","ksh","zsh","ash"}`.
3. **`scripts()`** — checks `os.environ.get("CODE_CHECK_SCRIPTS")` first; if truthy, returns `[Path(p) for p in value.split(os.pathsep)]` verbatim (no glob, no `.exists()`). Else builds `[vibe, install.sh] + sorted(devcontainer/*.sh) + sorted(devcontainer/hooks/*.sh) + sorted(p for p in devcontainer/git-hooks/.iterdir() if p.is_file() and is_shell_script(p))`, then `.exists()`-filters the whole list, matching today's behaviour for the first three blocks.

## Method

Wrote a scratch TDD harness first at `/workspace/.vs/cycle-1/scratch-tests/scratch_check.py` (gitignored via `.vs/cycle-*/`) covering all of AC2's 13 shebang-shape cases, the AC3 env-seam exact-list + no-leak check, AC4 empty/unset fallthrough, and AC1 default-set git-hooks inclusion (names + sorted-block + count). Ran it against the unmodified `code-check.py` first — confirmed red (`AttributeError: no attribute 'is_shell_script'`). Implemented the contract. Re-ran — all 23 scratch checks green.

## Gates run

- `python3 -m py_compile code-check.py` — clean, exit 0.
- `python3 code-check.py` — exit 0, 19 files (was 15), all four `devcontainer/git-hooks/*` files now listed and shellcheck-clean.
- `python3 code-check.py --json` — single valid JSON object; `files_checked` includes `devcontainer/git-hooks/{commit-msg,pre-commit,pre-push,vibe-content-scan.sh}`; `summary = {"files": 19, "files_with_issues": 0, "total_findings": 0}`.
- `python3 smoke-test.py` (full suite, 2485 lines of output) — exit 1, but **only** 5 checks failed, all inside the three tests the spec predicted would break: `test_code_check_json_finding_schema` (AC3, 1 check), `test_code_check_json_findings_exit1_and_count` (AC4, 2 checks), `test_code_check_json_summary_counts` (AC9, 2 checks). Grep-confirmed no other `✗`/`FAIL`/`Traceback` anywhere in the run — every other check across task_019/021/022/023/024 coverage still passes. This is the sanctioned, expected `_patched_code_check` no-op landmine described in the spec (its literal `.replace()` keys on `scripts()`'s exact old source text, which this edit necessarily changed) — it is the Tester's job to reshape the fixture to the `CODE_CHECK_SCRIPTS` env seam, not mine.

## Files changed

- `/workspace/code-check.py` — `import os`, `is_shell_script()`, `scripts()` env seam + git-hooks block.
- `/workspace/CHANGELOG.md` — new 2026-07-17 task_025 entry, placed above the task_024 entry (newest first).

Diff: `/workspace/.vs/cycle-1/diff.patch`.

Not touched (per instructions): `smoke-test.py`, `TODO.md`, any shell file.
