# Cycle 2 test summary (task_017 AC8-AC11)

Totals: smoke-test.py 1273/1273 checks passing (0 failures) — the full frozen C1 suite plus 18 new Cycle-2 test functions (lock helpers AC9, rw-intent resolution AC8 incl. CLI-level `vibe repos add --rw` fresh-add/upgrade-in-place/no-silent-downgrade/position-agnostic, exit dispatcher AC10, mode coherence) appended after the C1 delta block; code-check.py shellcheck clean across 15 files; full fresh run ~34s, the new C2 functions alone add well under 2s.

Regressions: none - every frozen C1/pre-existing test still passes unmodified; only new functions appended and their `main()` call lines added after the last C1 call.

Key note: two bugs found and fixed during test-writing (both in the new C2 tests, not in vibe's source) - (1) checking lock-meta persistence from Python after the bash subprocess exited was structurally wrong (a real launch's AC10 exit hook releases the lock on that same exit), so the assertion moved inside the still-running script; (2) two `set -e`-guarded snippets calling a refusing helper needed a `set +e`/`set -e` bracket per the task_016 pattern. The initially-missing `vibe repos add --rw` CLI wiring was flagged, landed as an integrator edit mid-cycle, and is now covered by flag-level tests (test_task017_c2_repos_add_rw_flag_cli_level).
