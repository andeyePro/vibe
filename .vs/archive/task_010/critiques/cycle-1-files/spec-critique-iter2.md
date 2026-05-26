# Spec critique — task_010 cycle 1, iter 2

## Concerns

### BLOCKING

**1. AC20: floor of 17 contradicts the per-AC coverage clause (AC20)**
AC20 says "AT LEAST 17 `check(...)` calls" but then mandates: AC1–AC11 each get
at least one check (11 checks), AC12–AC17 each get at least one check (6
checks), AC18 gets at least one check (1 check), AC19 verifies the function
exists (1 check). That sums to 19 minimum implied by coverage — not 17. A
Tester can satisfy the stated floor of 17 while leaving 2 ACs unchecked and
still pass. The floor must be raised to ≥19 (or the per-AC coverage clause
adjusted to match 17).

### MEDIUM

**2. AC18 diff-allowlist excludes `smoke-test.py` (AC18)**
AC18 says the changed-file set after Generator commits cycle-1 must be exactly
`{devcontainer/commands/learn.md, .vs/spec.md, .vs/progress.md, .vs/tasks.json}`
plus optional `.vs/cycle-1/*` artifacts. `smoke-test.py` is not in that list.
Tester writes `smoke-test.py` — if Tester commits in the same commit as
Generator (or if HEAD~1 is measured against a combined commit), the diff check
fails on a legitimate Tester write. The spec needs to clarify whether `HEAD~1`
in AC18 references the Generator's commit specifically, and whether
`smoke-test.py` should be added to the allowlist or excluded by a separate
Tester commit convention. As written, a correct Tester artefact can cause a
false AC18 failure.

### LOW

**3. AC10 negative-grep set is split across AC10 body and Known Limitations (AC10)**
AC10 forbids `skip the` and `skip if`. The Known Limitations section says the
full negative-grep set should also include `bypass the check` and `omit the
check`, and declares this "promoted to a regular AC" — but AC10's body was not
updated to include those two patterns. A Tester reading only the ACs section
misses half the negative-grep set. Move all four negative patterns into AC10
itself and remove the "Tester should include all four" note from Known
Limitations.

## Resolved from iter 1

1. **BLOCKING-1 (AC14 arithmetic):** Fixed. AC coverage now says "AC1 through
   AC11 each get at least one direct check; AC12 through AC17 each get at least
   one direct check; AC18 gets at least one check; AC19 verifies the function
   exists." Floor raised to 17 (though still arithmetically short by 2 — see
   new BLOCKING-1 above).

2. **BLOCKING-2 (AC2 absolute step-numbering):** Fixed. AC2 now uses `awk` line
   numbers and relative phrase ordering (`Formats the entry body` before `Runs
   the semantic check` before `Prints a preview`) instead of asserting step 4/5/6/7.

3. **BLOCKING-3 (AC6 N-semantics):** Fixed. AC6 now requires `N` AND (`drop` or
   `drops` or `cancel` or `cancels`) within 200 characters of each other.
   Proximity is explicit.

4. **BLOCKING-4 (AC14 function-name alternation):** Fixed. AC19 now specifies
   canonical name `test_task010_smart_capture` exactly — no alternation.

5. **MEDIUM-5 (AC5 zero-friction evasion):** Fixed. AC5 now requires BOTH the
   phrase `zero friction` AND one of `no options` / `without surfacing options`
   / `no options surfaced`, nailing the behaviour not just the slogan.

6. **MEDIUM-6 (AC7 verbatim proximity undefined):** Fixed. AC7 requires `Z1 is
   always` (exact phrase) AND `verbatim` within the same paragraph (defined as
   ≤400 chars or between blank lines).

7. **MEDIUM-7 (AC8 token-cost vagueness):** Fixed. AC8 now pins exact phrases:
   `2-5k tokens`, `2–5k tokens`, or `2 to 5k tokens`. No other phrasings accepted.

8. **MEDIUM-8 (AC9 hook/preview proximity):** Fixed. AC9 requires `preview` AND
   `hook` within the same paragraph (defined as ≤400 chars or between blank
   lines).

9. **MEDIUM-9 (AC3 trivially-equivalent):** Fixed. AC3a pins the exact phrase
   `existing /learnings entries`; AC3 requires the exact phrase `Runs the
   semantic check`. No paraphrase tolerance.

10. **MEDIUM-10 (conditional-skip loophole):** Fixed. AC10 explicitly forbids
    the check being conditional. The "Conditional skipping" item is listed in
    Out of scope. AC10 now includes a negative grep for `skip the` and `skip if`.

11. **MEDIUM-11 (no upper bound on Z-options):** Fixed. AC11 requires one of
    `cap n at 3`, `no more than 3`, `up to 3 alternatives`, or `1 or 2
    alternatives`.

12. **MEDIUM-12 (devcontainer/claude-md/ exclusion):** Fixed. AC18 explicitly
    names `devcontainer/claude-md/` and `devcontainer/agents/` as forbidden
    directories.

13. **LOW-13 (regression sentinels test presence only):** Acknowledged in Known
    Limitations; acceptable for a doc-only file.

14. **LOW-14 (heading level unspecified):** Fixed. AC1 now specifies `##`
    heading level and greps for the literal line `## Semantic check`.

15. **LOW-15 (runtime vs documentation gap):** Addressed in Known Limitations
    section with explicit language about what "all ACs pass" means.

## Verdict

`revise`
