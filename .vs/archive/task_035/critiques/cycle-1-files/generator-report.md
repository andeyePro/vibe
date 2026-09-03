# task_035 cycle 1 — Generator report

## Delivered (per spec, deliverables 1–6)

1. **`smoke/_core.py`**: `run()`/`run_bytes()` now branch on `input`/`input_bytes`
   and pass `stdin=subprocess.DEVNULL` in the else-branch — two literal
   `subprocess.run(...)` call sites each (not a `**kwargs` merge), so an
   AST scan for a literal `input`/`stdin` keyword sees them directly. Never
   both `input=` and `stdin=` on the same call.
   `_isolate_extras_env` now also sets `GH_META_CACHE` to a per-call unique
   path (`tempfile.mkdtemp(dir=scratch)/gh-meta-cache.json`) unless the
   caller already set it, alongside the existing HOME/GIT_CONFIG_GLOBAL/
   CLAUDE_CONFIG_DIR/VIBE_AUTO_GITIGNORE handling.
   `_fw_run` now builds its env via `_isolate_extras_env(dict(os.environ))`,
   layers on PATH/STUB_LOG/VIBE_FIREWALL_SOURCE_ONLY/GH_FETCH_*, then
   overrides `GH_META_CACHE` to its own tmp path afterward.
   Added `HISTORICAL_PINS_ALLOWED = {"3b23b19": "task_034 AC4 golden
   baseline..."}` near the top of the file, documented, and added to
   `__all__` for star-import into `checks_*.py`.

2. **Swept all 27 previously-unguarded `subprocess.run`/`Popen` sites**
   across `smoke/_core.py` and six `checks_*.py` files, adding
   `stdin=subprocess.DEVNULL` (never touching any call that already had
   `input=`). Total spawns now 50 (was 48; +2 from the `run()`/`run_bytes()`
   branch split) — all guarded, confirmed by an AST scan (see below).

3. **`checks_11_patrotation_and_firewall.py`**:
   `test_gh_meta_rate_limit_and_cache_fallback` now builds its env through
   `_isolate_extras_env(dict(os.environ))`, then overrides `GH_META_CACHE`
   to its own `cache` path afterward — no more inline `{**os.environ, ...}`
   dict. Re-ran the function directly: all 38 checks in it still pass.

4. **`CLAUDE.md` § Testing**: added three bullets — spawns never inherit
   stdin (+ `python3 smoke-test.py < /dev/null` for background runs);
   installer/`vibe learn`/firewall-sourcing tests route through
   `_isolate_extras_env`; no permanent sha-pinned test baseline outside
   `HISTORICAL_PINS_ALLOWED`.

5. **`.gitignore`**: removed the hand-written `.vibe/` and
   `.claude/settings.local.json` lines from the top block. Confirmed safe
   by reading `install-claude-extras.sh::ensure_project_gitignore` first —
   it only checks `grep -qF "$marker"` (the managed-block open marker) to
   decide idempotency; it never inspects or depends on any specific line
   inside the block, so removing the duplicate hand-written lines cannot
   cause it to re-add anything or misbehave. `site/.gitignore` left
   untouched per spec (its un-anchored entries are not pure duplicates of
   root's anchored ones).

6. **`CHANGELOG.md`**: added a task_035 entry at the top of
   `## 2026-09-02`, narrating all five fixes and noting the four new tests
   (AC3/AC4/AC6-successor/AC7) are the Tester's, pending.

## Verification

- `python3 code-check.py < /dev/null` — shellcheck clean across 19 files, exit 0.
- `python3 smoke-test.py < /dev/null` (foreground, full run) — `✓ smoke
  tests passed`, exit 0. No rerun needed (first attempt completed within
  the session, no cap trip).
- Scratch TDD under `.vs/cycle-1/scratch-tests/`:
  - `ast_scan_no_unguarded_spawns.py` — AST-scans all `smoke/*.py`,
    finds 50 `subprocess.run/Popen/check_output/call` nodes, 0 unguarded.
    PASS.
  - `held_open_pipe_regression.py` — runs
    `test_gh_meta_rate_limit_and_cache_fallback` (a spawn-heavy test, ~20
    child processes) in a subprocess whose own stdin is an open,
    never-written, never-closed pipe; completed in ~19s (< 60s bound), all
    checks passed. PASS.

## Not done (explicitly out of scope for the Generator)

- The four new tests (AC3 spawn lint, AC4 open-stdin regression, AC6
  whole-suite meta-check successor, AC7 sha-pin lint) — Tester's.
- No other `smoke/*.py` inline `env=` sites beyond
  `test_gh_meta_rate_limit_and_cache_fallback` were routed through the
  builder; AC6's broader "≥1 call site per category" sweep for the
  meta-check successor is the Tester's to verify/extend.

## Notes for Tester / Evaluator

- `HISTORICAL_PINS_ALLOWED` is now in `_core.py`'s `__all__`, importable via
  `from smoke._core import *` in any `checks_*.py`.
- `run()`/`run_bytes()` deliberately use two literal `subprocess.run` calls
  (not a merged kwargs dict) specifically so AC3's lint — which looks for a
  literal `input`/`input_bytes`/`stdin` keyword name on the AST `Call`
  node — sees them as guarded. If AC3's lint is later changed to inspect
  something other than keyword names, this shape assumption should be
  revisited.
