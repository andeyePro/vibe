# task_051 AC5 — Tester summary (cycle 1)

`python3 code-check.py`: clean, shellcheck across 23 files, exit 0. `python3 smoke-test.py < /dev/null`: 4,445 checks passed, 0 failures, exit 0 (full log at `.vs/cycle-1/test-output.log`).

Pins updated in `smoke/checks_09_openproject_and_scanner.py`: AC1 fragment count 14→15 and `dollar-prefix.md` added to `expected_names`; AC2's 6,700-word cap left unchanged (new 15-fragment total is 6,563 words — the new fragment fit, so per task_042's precedent the cap was not raised, only commented). New `test_dollar_prefix_fragment_and_aliases()` added to `smoke/checks_13_spec_first.py` (37 checks: fragment size/content, alias lines under each H1, vs.md's exact +1 line-count vs HEAD, vsss.md's protected phrases, README/plan/TODO content) and registered in `smoke/runner.py`. New `test_task051_ac2_dollar_prefix_synced_like_web_research()` added to `smoke/checks_03_vibecopy_and_watcher.py` (extends the task_007/t3 fixture-isolated sync pattern with a second fragment) and registered in `runner.py`; added `DOLLAR_PREFIX_MD` constant to `smoke/_core.py` `__all__`.

Not covered: the live/manual side of the deterministic `UserPromptSubmit` hook alternative — out of scope per spec (instructional-route-only task); TODO.md's content for that hook was asserted only for the required sentinel words, not full prose fidelity.
