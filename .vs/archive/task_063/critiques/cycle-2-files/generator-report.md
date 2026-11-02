# Generator report, task_063 cycle 2 (AC12-AC20)

Edited: vibe, README.md, MANUAL-TESTS.md, CHANGELOG.md (task_063 entry extended). Template untouched.

- AC12: reinstall stages to `~/Applications/.Vibe Link.app.new-<pid>`, then lsregister -u, mv old to `.old-<pid>`, mv new into place, lsregister -f, rm old. Failure before the final rename restores/re-registers old and removes the sibling (exit 1). Refuses if a staging path exists. Fresh install: direct mv. Dry-run block order for a vibe bundle: mv(new), lsregister-u, mv(old), mv(final), lsregister, rm(old).
- AC13/14: `_link_plist_cmds` fills `_LINK_PLIST_CMDS` (quoted `"Vibe Link"` and `"<path>"`), used by dry run and real run; failed `Set :K V` falls back to `Add :K string V` (`_link_plist_run`).
- AC15: `[ -e ]`/`-L` check on the target right before mv (both paths).
- AC16: `_link_mac_default`: first `path:` then first `bindings:`/`claimed schemes:` line with ` vibe:` (or `,vibe:`); strips ` (0x..)`; none/failure -> `default: (unknown)` only; prints `not the default handler` when first claimant != our bundle and ours is installed.
- AC17: xdg-mime failure removes the written .desktop; uninstall runs update-desktop-database (also a dry-run block).
- AC19: `_link_launcher_check [--executable]` shared (open: exit 7, same message as before; install: --executable).
- AC20: `_LINK_LSREGISTER`; comment fixed.

Results: code-check 0. Scratch tests (.vs/cycle-2/scratch-tests/run.sh) behave as expected (mv failure leaves old bundle + no sibling; dump parsing; xdg failure). Full smoke: one failure, expected: checks_56 "existing vibe bundle: lsregister-u and rm blocks between codesign and mv" (asserts the old dry-run order changed by AC12).
Artifacts: .vs/cycle-2/diff.patch
