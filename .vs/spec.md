# Spec — task_035: harness hygiene — stdin-immune suite, one sandbox builder with a whole-suite meta-check, sha-pin lint, SAFE prunes

## Task summary
This session's own harness debris, each patched at the point of pain and none prevented from recurring: (1) a background suite run hung 55 minutes inside a `vibe learn` test because `run()` inherits stdin when no `input` is given (`smoke/_core.py:116`; `run_bytes` `:127`; four `Popen` watcher spawns and ~10 direct `subprocess.run` calls likewise); (2) two live `~/.claude` writes — the CLAUDE.md managed block and a fixture GitHub-meta cache — because sandboxing was ad hoc: `_isolate_extras_env` lacks `GH_META_CACHE`, `_fw_run` sets it inline, and the only meta-check (`test_extras_invocations_isolated`, `checks_06`) scans `Path(__file__)` alone so it cannot see the other twelve files; (3) task_028/029's tests compared the tree against fixed commit shas and tripped on the very next commit. Fix all three structurally, record the rules in CLAUDE.md § Testing, and fold in the remaining SAFE prunes. Single stream on main. Baseline c7bf110.

## Acceptance criteria (mechanical; the Tester adds them to the suite)
- AC1 `smoke/_core.py`'s `run()` and `run_bytes()` pass `stdin=subprocess.DEVNULL` exactly when no `input`/`input_bytes` argument is given, and never pass both `input=` and `stdin=` (subprocess raises).
- AC2 Every `subprocess.run(`/`subprocess.Popen(`/`subprocess.check_output(` call in `smoke/*.py` that supplies neither `input=` nor an explicit `stdin=` passes `stdin=subprocess.DEVNULL` (or routes through `run()`/`run_bytes()`).
- AC3 A new lint test `test_harness_spawns_never_inherit_stdin()` scans every `smoke/*.py` source, finds every spawn, and fails on any that satisfies neither condition; it asserts it found ≥ 20 spawns (non-vacuous).
- AC4 Regression test `test_harness_survives_open_stdin()`: runs a small representative child (a sourced `vibe learn`-shaped invocation through `run()`, or `python3 -c` importing the entry module and calling one test that spawns `vibe`) with a never-written open pipe as stdin; it completes within 60 s.
- AC5 `_isolate_extras_env` also sets `GH_META_CACHE` under the scratch HOME (and keeps HOME, GIT_CONFIG_GLOBAL, CLAUDE_CONFIG_DIR, VIBE_AUTO_GITIGNORE=0); `_fw_run` consumes it instead of setting its own; no other test sets these keys by hand except through the builder (a test may override AFTER calling it).
- AC6 The meta-check `test_extras_invocations_isolated` (or a successor) scans ALL `smoke/*.py`, not `Path(__file__)`, for every invocation of `INSTALL_EXTRAS`, `SETUP_GIT_SH`, a `vibe learn` argv, and `INIT_FIREWALL` sourcing, and fails on any `env=` at those call sites not routed through `_isolate_extras_env` (or `_fw_run`, which must itself call the builder); it asserts ≥ 1 call site per category (non-vacuous), listing the counts in its labels.
- AC7 A sha-pin lint `test_no_fixed_sha_baselines()` scans `smoke/*.py` for `git show <7-40 hex>:` and `git diff <7-40 hex>` in test bodies and fails unless the occurrence is registered in a documented allowlist constant `HISTORICAL_PINS_ALLOWED` in `_core.py` with a one-line reason each; the sole initial entry is `_task034_baseline_text`'s `3b23b19` (its comment explains why). `HEAD`, temp-repo shas produced at runtime, and `checks_09`'s `git show -s <sha>` against a repo the test itself created must not trip it (the regex must require a literal hex sha token in source, not a variable).
- AC8 `CLAUDE.md` § Testing gains three bullets: spawns never inherit stdin (and `python3 smoke-test.py < /dev/null` for background runs); every real-installer / `vibe learn` / firewall-sourcing test goes through `_isolate_extras_env`; no permanent test pins a fixed commit sha (allowlist in `_core.py`).
- AC9 `.gitignore`: the hand-written `.vibe/` and `.claude/settings.local.json` lines (top block) are removed, the vibe-managed block is byte-identical, and `install-claude-extras.sh`'s `ensure_project_gitignore` still finds its block (the Generator reads that function first; if the block's presence is what stops re-adding, nothing else changes). `site/.gitignore` reduces to `public/vendor/` (root already ignores `site/node_modules/`, `site/dist/`, `site/.astro/`). MANUAL-TESTS double rule: already gone, out of scope.
- AC10 `python3 code-check.py` exits 0; `python3 smoke-test.py < /dev/null` exits 0; and the same suite invoked with an inherited open pipe on stdin (`sleep 1000 | python3 smoke-test.py` shape, or a Python harness holding the write end) exits 0 within the Bash cap — the Tester runs this once as the decisive check.
- AC11 Scope lock: only `smoke/*.py`, `CLAUDE.md`, `.gitignore`, `site/.gitignore`, `TODO.md`, `CHANGELOG.md`, `.vs/`, `.vss/`.

## Out of scope
- Any change to the launcher, installer, hooks, firewall, or site.
- Rewriting test bodies beyond the spawn-argument sweep and the sandbox routing.
- Removing lines from the vibe-managed `.gitignore` block.

## Test location
`smoke/checks_06_autoresume_and_sharedrepos.py` (the meta-check home; keep ≤ 1,500 lines — if it would exceed, the Tester creates `smoke/checks_12_harness_lints.py` and registers it in `runner.py` and the entry file's star-import list). Generator edits `_core.py`, the spawn sites across `checks_*.py`, CLAUDE.md, the two `.gitignore`s, CHANGELOG.md; Generator does NOT write the three new tests (AC3, AC4, AC6-successor, AC7) — those are the Tester's — but may add the `HISTORICAL_PINS_ALLOWED` constant and the `_isolate_extras_env` change.

## Proposed budget
2 cycles.

## Model plan
- Planner + Evaluator: session model (Fable 5.1 chair). Spec Critic: sonnet (attack the three lint regexes for vacuous pass / false positives). Generator: sonnet, ceiling opus. Tester: sonnet, ceiling opus. Fable rung: pre-authorised (--fable-subagents grant), not indicated.
