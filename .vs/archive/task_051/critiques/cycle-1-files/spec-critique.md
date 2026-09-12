# Spec Critic — task_051 `$vs`/`$vss`/`$vsss` dollar-prefix

## Concerns

1. **AC1/AC5 — BLOCKING.** Adding `dollar-prefix.md` makes claude-md/ a
   15th fragment, but `smoke/checks_09_openproject_and_scanner.py`
   (`test_task028_fragment_merges_and_fable_grant`) hard-pins
   `len(all_md_files) == 14` and `set(all_md_files) == expected_names`
   against the real `devcontainer/claude-md/` dir. Neither AC1 nor AC5
   names this file — AC5 points at `checks_13_spec_first.py`, AC2 points
   at the fixture-isolated `checks_03` sync test. Following AC5 literally
   leaves checks_09's exact-count/name-set assertions to hard-fail —
   `smoke-test.py` red, AC6 unmet. Fix: name checks_09's AC1 assertions
   explicitly as a required edit.

2. **AC1 — BLOCKING (word budget).** checks_09's AC2 also caps total
   fragment words at 6700; current total is 6400 (300-word headroom —
   raised from 6400 by task_042, which trimmed to fit rather than just
   raising the number). AC1 caps the new fragment by LINES (≤25) not
   words; the required literal examples (`$vss:foo`, the `--hours 2`
   sample, the D3 pointer) can plausibly push it near/over 300 words.
   No word budget or ceiling-check instruction is given.

3. **AC1 — MINOR.** "First whitespace-delimited token, exact" doesn't
   say whether leading blank lines still count, or whether
   directly-appended punctuation (`$vs,` `$vs.`) is rejected the same
   way as the colon-suffix example — implied but never shown.

4. **AC1/AC6 — MINOR.** The mechanism is a natural-language instruction
   to the lead model; no test here (or in `smoke-test.py` generally,
   which never drives a live interactive session) can verify the alias
   fires at runtime — only that the fragment TEXT exists. AC6's "fully
   green" proves the doc shipped, not that `$vs` works. Acceptable given
   the deterministic hook route is explicitly out of scope, but worth
   saying out loud rather than implying behavioral proof.

5. **AC3 — MINOR.** The exact-one-line-growth check should also pin the
   new line's content to AC1's literal wording, not just "a line
   matching the alias pattern exists somewhere."

## Verdict

`revise` — concern 1 is a concrete, demonstrable test-suite collision
(checks_09's exact-count and exact-name-set assertions will break) that
must be fixed before this spec is buildable to a genuinely-green
`smoke-test.py`. Concern 2 is adjacent (same file, same task_028
baseline) and should be resolved in the same pass.
