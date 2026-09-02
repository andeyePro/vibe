# Review focus policy

Adopted 2026-09-02 alongside the smoke-test.py -> smoke/ split (task031).
Two things this records: which files always get an eyes-on review before
merge regardless of diff size, and the module-size budget that motivated
the split in the first place.

## Hot files — always `/code-review high` before merge

These touch the container's trust boundary (firewall, permission guards,
credential routing, SSH setup) or the permission lists that make
`--permission-mode bypassPermissions` safe to run at all. A change here
gets `/code-review high` on its own diff even when it rides along with an
unrelated commit, no exceptions:

- `vibe` (the launcher itself — auth, token handling, settings.local.json
  templating, firewall/container wiring)
- `devcontainer/guard-bash.sh`
- `devcontainer/guard-fs.sh`
- `devcontainer/init-firewall.sh`
- `devcontainer/credential-helper.sh`
- `devcontainer/setup-ssh.sh`
- the permission lists in `settings.local.json` — templated inline in
  `vibe` itself (search `cat > "$WORKSPACE/.claude/settings.local.json"`),
  not a standalone file under `devcontainer/`
- `devcontainer/git-hooks/*` (commit-msg, pre-commit, pre-push,
  vibe-content-scan.sh — the content-guard layer)

## Module size budget

Any single file under active review — source or test — is budgeted at
**1,500 lines**. When a file crosses that line, split it before adding
more to it rather than after. `smoke-test.py` hit 14,486 lines and 487
`test_*` functions before this rule existed; the split into
`smoke/_core.py` + `smoke/checks_*.py` + `smoke/runner.py` (see
`CLAUDE.md` § Testing for the layout) is the fix, and the budget exists so
it doesn't recur. The same budget applies to `vibe` itself and to any
`devcontainer/*.sh` script — if one of the hot files above approaches
1,500 lines, that's a split-it conversation, not a defer-it one.

## Review cadence

- Review the **diff**, never the whole file — `/code-review high` scoped
  to the cycle's changes.
- `/code-review high` on every review cycle's diff, unconditionally for
  the hot files above.
- `ultra` (the deep multi-agent cloud review) is reserved for
  pre-release passes, not routine cycles — it's slower and, depending on
  plan, credit-billed.
- Weekly: diff since `.vs/last-review.sha` (whatever that file currently
  points at) gets a `/code-review high` pass even if no hot file changed
  in the window, so drift in the rest of the tree doesn't go unreviewed
  indefinitely between feature work.
