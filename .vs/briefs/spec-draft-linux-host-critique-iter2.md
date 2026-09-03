# Spec Critique — Linux host support (Tier 2), iteration 2

## Concerns

All three iteration-1 BLOCKING items are resolved: the watcher gate is now a correct 3-way OR (Darwin / `VIBE_COPY_CMD` / `VIBE_COPY_WATCHER_FORCE`), preserving `test_vibe_path_prefix_isolation`; AC4 pins the golden to a literal pre-task string, not a self-referential derivation; AC10 now requires a real cache-busting rebuild plus a MANUAL-TESTS check, and the live duplicate `mdns4_minimal` line is independently confirmed in this container's `/etc/nsswitch.conf` today. All four MINORs (host-side clipboard statement, uname-shim self-proof, trimmed dedup reasoning, post-ship Mac re-verification) are also addressed.

Two new issues:

1. **Stale test citations.** Changes (b) and AC5 still cite `smoke-test.py:3907, 3957, 8590` and `:2954` for the byte-pinned exit-hook strings. `smoke-test.py` is now a 28-line thin re-export; that content actually lives in `smoke/checks_04_hooks_guards.py` (`test_task008_ac3_block_scoping` ~L6, `test_task008_ac11_direct_read` ~L56, `test_clipboard_drain_on_exit` ~L80) and `smoke/checks_07_sharedrepos_cycles.py:803-804`. Update the citations or the Generator/Tester will hunt for line 3907 in a 28-line file.

2. **AC6 vs. the amendment disagree on the Linux clipboard commands.** The amendment (line 74) correctly specifies `xclip -selection clipboard` and `xsel --clipboard --input` — bare `xclip`/`xsel` write to the X11 PRIMARY selection, not the paste clipboard. But Changes (b) and AC6 still say plain `wl-copy`/`xclip`/`xsel`, no flags. AC6 is the literal contract; a Generator following it would ship a silently-wrong-selection bug that no smoke test catches (only surfaces at `[L]` AC13 on real X11). Align AC6's wording with the amendment's flagged invocations.

## Verdict

**revise (minor)** — both are one-line citation/wording fixes, not re-scoping; no new blocking issues found.
