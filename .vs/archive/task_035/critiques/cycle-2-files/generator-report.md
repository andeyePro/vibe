# Generator report — task_035, cycle 2

## What failed in cycle 1

`test_extras_invocations_isolated` (AC6 meta-check, `smoke/checks_12_harness_lints.py`,
FROZEN, not edited) found 29 `env=` call sites building a bare
`{**os.environ, "HOME": ...}` literal instead of routing through
`smoke/_core.py`'s `_isolate_extras_env`:

- 27 `vibe learn` argv sites in `smoke/checks_02_image_drift_and_learning.py`
- 2 `SETUP_GIT_SH` sites in `smoke/checks_08_credential_and_contentscan.py`

## Fix

At every flagged call site, the nearest preceding `env = {...}` assignment in
each function was rewritten to `env = _isolate_extras_env({...})`, keeping the
dict literal's own keys unchanged (so this is exactly a wrap, not a rewrite) —
23 unique assignment sites in checks_02 (fixing 27 call-site violations, some
sharing one `env` across multiple `run()` calls in the same function) and 2 in
checks_08. Post-assignment mutations already present (`env["PATH"] = ...`)
were left as-is; the routed-through rule explicitly permits overrides after
the routing assignment.

One regression surfaced by the affected-suite rerun (not by the meta-check,
which only checks routing, not runtime behaviour):
`test_setup_git_strips_host_credential_helpers` (checks_08) started failing
`[cred-strip] host user.name survives the strip`. Cause: `_isolate_extras_env`
defaults `GIT_CONFIG_GLOBAL` to a scratch-dir path whenever it isn't already
set; for this test HOME is already a fresh sandbox (not the real HOME), so
that default isn't needed for safety, but it silently redirects every
`git config --global` read/write — the script's own and the test's
verification calls — away from `$HOME/.gitconfig` (which is where the
host_cfg-seeded `user.name` lives) to an unrelated empty file. Fixed with a
one-line `del env["GIT_CONFIG_GLOBAL"]` immediately after the builder call —
an explicit override-after-the-builder, per the routed-through rule's own
permitted pattern — restoring `git config --global` to target
`$HOME/.gitconfig` exactly as before the routing change. The sibling test
(`test_task017_c4_ac17_setup_git_functional_in_sandbox_home`) doesn't inspect
`user.name` and was already green with the default GIT_CONFIG_GLOBAL in
place, so it was left untouched.

## Files touched

- `/workspace/smoke/checks_02_image_drift_and_learning.py` — 23 assignment
  sites wrapped in `_isolate_extras_env(...)`.
- `/workspace/smoke/checks_08_credential_and_contentscan.py` — 2 assignment
  sites wrapped in `_isolate_extras_env(...)`; one of them (the
  credential-strip test) also drops the builder's `GIT_CONFIG_GLOBAL` default
  immediately after the call to preserve the test's `$HOME/.gitconfig`
  semantics.

No changes to `smoke/checks_12_harness_lints.py` (FROZEN, Tester-owned) or to
any test's assertions. `.vs/tasks.json` untouched by this cycle.

## Verification

1. `test_extras_invocations_isolated()` — green, 0 violations across all
   4 categories (install_extras 77, setup_git 6, init_firewall 43,
   vibe_learn 27 call sites scanned).
2. `test_harness_spawns_never_inherit_stdin()` — green (unaffected by this
   change; re-run for the required check-pair).
3. All 39 `test_learning*` functions in checks_02 — green, 0 failures.
4. `test_task017_c4_ac17_setup_git_functional_in_sandbox_home`,
   `test_setup_git_strips_host_credential_helpers`,
   `test_task017_c4_ac17_usehttppath_same_scope_as_helper_registration`
   (checks_08) — green, 0 failures (the `user.name` regression above was
   caught here and fixed before this final run).
5. `python3 code-check.py` — exit 0, shellcheck clean across 19 files.
6. `python3 smoke-test.py < /dev/null` (foreground, timeout 600000) — **exit
   0** on the first attempt, no rerun needed. Full log: 3684 lines, final
   line `✓ smoke tests passed`. The sole `✗` glyph in the log is inside a
   passing check's own label text (`[json] AC5 no '✗ shellcheck' human line
   in stdout`), not a failure.

## Outputs

- `/workspace/.vs/cycle-2/generator-report.md` (this file)
- `/workspace/.vs/cycle-2/diff.patch` (`git diff 0795659`, full working-tree
  diff since baseline, includes cycle-1's already-landed changes plus this
  cycle's two-file fix)
