# spec — task_001: `--json` output for `code-check.py`

## Task summary

Add a `--json` flag to `code-check.py` so machine consumers (CI, editor integrations, downstream tooling) can ingest shellcheck findings as structured data instead of parsing human-readable lines. The default invocation must remain byte-for-byte unchanged so existing users and the `MANUAL-TESTS.md` flow are unaffected. When `--json` is set, the script runs shellcheck with `-f json` over the same target list, aggregates the per-file findings into one JSON object on stdout, prints nothing else to stdout, and preserves the existing exit-code semantics (0 clean, 1 issues, 2 missing shellcheck).

## Acceptance criteria

1. `python3 code-check.py --json` exits 0 when there are no findings and writes valid JSON to stdout (parseable by `json.loads`).
2. The emitted JSON is a single top-level object with keys: `tool` (string, equals `"shellcheck"`), `shellcheck_version` (string, e.g. `"0.9.0"`), `files_checked` (list of strings, repo-relative POSIX paths), `findings` (list of objects), and `summary` (object with int keys `files`, `files_with_issues`, `total_findings`).
3. Each entry in `findings` is an object with at least these keys: `file` (string, repo-relative POSIX path), `line` (int), `column` (int), `level` (string: `"error" | "warning" | "info" | "style"`), `code` (int, the shellcheck SC code as integer), `message` (string).
4. When at least one target script has shellcheck warnings/errors, `python3 code-check.py --json` exits 1 and the JSON's `summary.total_findings` is > 0 and equals `len(findings)`.
5. With `--json`, **nothing** is printed to stdout other than the single JSON object (no `→ shellcheck …` progress lines, no trailing newline beyond what `print` adds, no human summary). Diagnostic prose may go to stderr.
6. Without `--json`, stdout output is byte-identical to the current `code-check.py` behavior (the existing progress + summary format).
7. When `shellcheck` is not installed and `--json` is set, stdout is a single JSON object `{"error": "shellcheck-not-installed", "tool": "shellcheck"}` and exit code is 2. (Without `--json`, the existing human error message and exit 2 are preserved.)
8. `python3 code-check.py --help` exits 0 and the help text mentions `--json`.
9. `summary.files` equals `len(files_checked)`; `summary.files_with_issues` equals the count of distinct `file` values appearing in `findings`.
10. The list of target scripts scanned with `--json` is identical to the list scanned without `--json` (same `scripts()` helper, no divergence).

## Out of scope

- Changing the default human output format, color, or wording.
- Adding any flag other than `--json` (no `--severity`, no `--format=…`, no `--output FILE`, no `--quiet`).
- Writing to files; output goes to stdout only.
- Caching, parallelism, or performance work.
- Refactoring `scripts()` or its target list.
- Touching `smoke-test.py` (Tester's territory), `vibe`, or any shell script under audit.
- Adding new dependencies beyond the Python standard library and the already-required `shellcheck` binary.
- Extending `MANUAL-TESTS.md` (Tester appends to `smoke-test.py`; manual checklist is unrelated).
- Modifying any pre-existing test in `smoke-test.py` (Tester only appends).

## Test location

`smoke-test.py` at repo root (existing file). Tester **appends** new test functions (e.g. `test_code_check_json_*`) and registers them in `main()`. The pre-existing tests in `smoke-test.py` are out of scope for this run; only the test code Tester adds for this task is subject to the immutability rule on cycle ≥2. Generator must not edit `smoke-test.py` at all (whole file is off-limits, not just appended sections).

## Proposed budget

**2 cycles.** Single file, well-scoped surface, but: JSON-schema fidelity, exit-code preservation, byte-identical default output, and graceful handling of missing-shellcheck are four easy-to-miss invariants. One cycle for the build, one for any shellcheck-version or schema corrections caught by Tester.
