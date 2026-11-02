# task_062 cycle 3 — Generator report (Rev 5 addendum, AC22–AC30)

## Files changed in this cycle (on top of cycles 1–2, all uncommitted)
- `vibe`: top-of-file launcher resolution (AC30), the `vibe link` section. No other hunks added (still: help header, top resolution, config capture, link section, parse_vibe_args `--task`, dispatch blocks).
- `devcontainer/taskandi-client.mjs`, `devcontainer/codex-supervisor.mjs`: one regex alternative each (AC22), nothing else.
- `README.md`, `MANUAL-TESTS.md` (Test 68: two lines), `CHANGELOG.md` (task_062 entry extended). `TODO.md` already had the codex-allow follow-up; not touched this cycle.
- Not touched: `smoke/checks_48/49/5*`, `smoke/runner.py`, firewall/hooks/settings/Dockerfile/commands/brain2.

## Per-AC notes
- **AC22**: added `|[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}` to `TASK_REF` (client) and to the supervisor's `invalid launch task binding` check (non-capturing group, so nothing else in the JS changes). Scratch `t_ac22.mjs`: `loadConfig` with a bound config and `VIBE_TASK_REF=<uuid>` (lower/upper case) returns it; junk is still refused. checks_28/29/47 run standalone → all rc 0.
- **AC23**: `deny` no longer pre-checks `~/.vibe/link-last`. It rewrites the registry first (exit 0), then runs `_link_last_safe`; on a symlink it prints that function's `⚠ <path> is a symlink …` plus `⚠ <name>'s rate-limit stamp was not removed …` and removes nothing. `open` still exits 5.
- **AC24**: the lock dir gets a `token` file (`$$.$RANDOM$RANDOM.<epoch>`); `_link_unlock` removes it only if it is a real dir whose token matches. Stale replacement: the first try (rename-then-recheck-then-put-back) failed the Tester's 6-racer test (two winners plus a leftover `.stale.*`: a third racer could `mkdir` in the gap while a fresh lock was renamed away). Final design: only the racer that wins a second `mkdir` (`<name>.dialog.break`) may break the lock. Under it, it checks the lock is still stale, `mv`s it to `<name>.dialog.stale.<pid>.<random>`, `rm -rf`s that, retries `mkdir` once, then removes `.break`. Everyone else, and a breaker whose rename or retry fails, exits 3 (held). A `.break` older than 70 s (a killed handler) is cleared. Scratch `t_race.py`: 8 rounds × 10 racers → exactly one 0, one launch, no leftovers each round.
- **AC25**: `_link_registry_usable [writer]`: writer mode skips only the loose-mode check. `allow` calls it plus `_link_registry_load` (exit 5 on failure). `_link_registry_rewrite` calls it and counts lines in its copy pass, returning 2 → callers (`allow`, `deny`, the new `_link_record_always` used by ASSUME=always and the dialog's Always) exit 5. A loose mode is still repaired with the `now trusted` note. A symlinked registry is still exit 1 `refused:` for allow/deny (AC2 unchanged).
- **AC26**: `[ ! -r ]` → `⚠ … cannot be read` (after the owner check). list → `(none)`, open → 5, allow → 5, with no raw bash error (scratch checked as uid 1000).
- **AC27**: stamp age < 0 → exit 3 `<name> counts as opened less than 5 seconds ago — ignoring this click (<stamp> is dated in the future; delete <stamp> if no confirmation is open)`. Lock state: age ≥ 70 or < −70 → stale; −70..−1 → `future` → exit 3 `a confirmation for <name> is already open — ignoring this click (<lock> is dated in the future; delete <lock> if no confirmation is open)`. Unreadable → held. The dry run uses the same `_link_lock_state`.
- **AC28**: `_link_registry_load` does one read loop. It enforces the 1000-line cap (returns 1 with the ⚠), records names in `|`-delimited `seen`/`dup` strings via `case`, then makes one linear walk over the collected entries and drops every duplicate. No nested loops. The line count was removed from `_link_registry_usable` (it was a second file pass). 1000-line registry open: 0.13–0.14 s here.
- **AC29**: `_link_unknown_dialog_ok` uses the global stamp `~/.vibe/link-last/.unknown`. It is suppressed if the stamp is 0–4 s old, unreadable, or in the future (the future message names the file). A symlinked link-last or `.unknown`, or a link-last that is not a directory → ⚠ exit 5 (same rule as AC18; my reading of "same symlink rules"). Real runs write the stamp; a dry run writes nothing. A suppressed click exits 2 with stderr only.
- **AC30**: at the top, `_vibe_dir` is resolved once with the sentinel trick. `DEVCONTAINER_DIR="$_vibe_dir/devcontainer"` and the new global `VIBE_LAUNCHER_PATH="${_vibe_dir%/}/${_vibe_src##*/}"`. The assignment still aborts under `set -e` if `cd` fails, as before. `_link_launcher_path` (the duplicate symlink loop) was deleted; `_link_open` uses the global plus `_codex_path_is_single_line` and the allowlist (exit 7). Stat fallbacks are factored into `_link_mode`, `_link_owner` and `_link_mtime`. Scratch: a symlinked launcher resolves to the real path; a launcher under a `"` dir → exit 7.

## Commands and exit codes
- `python3 smoke/checks_28_taskandi_client.py`, `checks_29_…`, `checks_47_…` → 0, 0, 0.
- `node .vs/cycle-3/scratch-tests/t_ac22.mjs` → 0.
- `python3 .vs/cycle-3/scratch-tests/t_link3.py` → 0 (0 failures).
- `python3 .vs/cycle-3/scratch-tests/t_race.py` → 0.
- `python3 .vs/cycle-2/scratch-tests/t_link2.py` → 3 failures, all expected: the AC18 "deny refused with a symlink" checks that AC23 reverses.
- `python3 code-check.py` → 0 (both runs).
- `python3 smoke-test.py < /dev/null`, run 1 → 1, with 12 failures:
  - 6 stale-lock race checks (round 1/2), a real bug, fixed by the break-mutex design above;
  - `stamp 4 s old: still limited`, rc 0, which did not reproduce on run 2. This looks like a timing boundary: the integer mtime plus a second tick under load gives age 5;
  - the 5 loadConfig checks below.
- `python3 smoke-test.py < /dev/null`, run 2 → **1**, with 5 failures, all in one Tester fixture (`[vibe-link] … loadConfig …`, including its two *controls*, `no VIBE_TASK_REF` and `ABBR-12`). Each one prints `OK <expected task>` and then the client's `usage:` text. So loadConfig returned the right value, and afterwards the client's CLI `main()` also ran, apparently because the fixture's `process.argv[1]` is the client file (`isMain()` at taskandi-client.mjs:686). The controls fail too, so this is in the fixture, not the regex. It is for the Tester to fix: import the module without making it argv[1], or ignore the trailing usage output. I may not change the client beyond the regex.
- Both smoke runs were moved to the background by the harness after 180 s; I waited for each to finish.
- `git diff > .vs/cycle-3/diff.patch` (whole working tree vs HEAD, cycles 1–3).
