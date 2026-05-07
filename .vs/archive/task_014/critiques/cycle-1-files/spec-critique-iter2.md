# Spec Critique - task_014 - iter 2

## Resolution of iter-1 concerns

### BLOCKING

1. **(cksum/40-hex incompatibility) - RESOLVED.**
   Mechanism section explicitly drops `cksum` from the new helper: "the existing
   third rung, `cksum`, is dropped from this helper because cksum produces a
   decimal CRC32 not a 40-char hex sha1". AC1 now requires `^[0-9a-f]{40}$` on a
   `sha1sum | shasum` two-rung ladder only. The existing inline cksum in
   `_learning_build_override_config` is handled by Out-of-scope item 8, which
   mandates its replacement with a call to `vibe_workspace_sha1`. Clean fix.

2. **(Baseline count 573 vs 574) - RESOLVED.**
   AC9: "All 574 currently-passing smoke checks (baseline verified by
   `python3 smoke-test.py 2>&1 | grep -cE "^  ✓ "` on 2026-04-29)". Confirmed
   by live run: 574 passes. The parked task_013/AC10 fail is explicitly noted as
   excluded from the gate.

3. **(Mixed string/object mount types; mount-order verifiability) - RESOLVED.**
   AC7 now explicitly requires the test to handle BOTH string-format entries
   (parsed by splitting on `,` and extracting `target=`) AND object-format entries
   (parsed via `.get("target")`), and states the test "MUST NOT silently skip
   string entries". Mechanism item 7 mandates the new projects bind uses JSON
   object format, matching the /learnings bind. The prior risk of vacuously-true
   ordering assertions is now caught by the explicit parse requirement.

4. **(AC3 "every mount entry" underspecified) - RESOLVED.**
   AC4 now states: "ALL 4 mount entries from `devcontainer/devcontainer.json`
   (currently `vibe-bash-history`, `vibe-claude-config`, `~/.ssh` bind,
   `~/.gitconfig` bind), preserved verbatim (string format unchanged), PLUS the
   new projects bind object... Total mounts count when /learnings is disabled:
   exactly 5. When /learnings is enabled and not opted out: exactly 6."
   Verified: devcontainer.json has exactly 4 mount entries (lines 37-40).
   The "currently 4" claim is accurate.

### MEDIUM

5. **(Unnamed AC1 helper) - RESOLVED.**
   The helper is now named `vibe_workspace_sha1` in Mechanism item 1 and AC1.
   `vibe_projects_bind_path` is named in Mechanism item 2 and AC2. Tester can
   enumerate both by name in `test_learning_helpers_exist` or new test_task014_*
   checks.

6. **(AC2 testability - mkdir static analysis) - RESOLVED.**
   AC3 is now a dedicated static-analysis criterion: "the test reads `vibe`,
   locates the line invoking `devcontainer up`... and asserts that an earlier
   line... contains a `mkdir -p` call whose argument references the per-project
   bind path". This is a concrete regex/substring match, not an execution test.
   AC2 no longer conflates path-correctness with mkdir behavior.

7. **(AC11 vague manual pass signal) - RESOLVED.**
   AC12 now provides a full setup, steps, and explicit pass/fail criteria:
   "`ls /home/node/.claude/projects/` shows exactly one slug (`-workspace`)
   containing only the projA JSONL(s), not projB's" and "Fail signal: the
   resumed conversation is projB's, OR the `projects/` directory contains JSONLs
   for both projects." Concrete and observable.

8. **(AC4/AC5 must exercise gating function not renderer) - RESOLVED.**
   AC5 and AC6 both explicitly state "Smoke tests for AC5/AC6 MUST exercise the
   FULL builder (`_learning_build_override_config`), NOT the lower-level renderer
   (`learning_render_devcontainer_config`), so the gating logic
   (`learning_should_mount`) is also exercised." AC10 reinforces: "for AC4-AC6
   they call `_learning_build_override_config` (NOT the lower-level renderer)".

9. **(Hash-consistency between run-dir filename and projects bind) - RESOLVED.**
   Mechanism item 1: "Both the existing per-session override-config run-dir
   filename... and the new per-project bind dir... MUST call this helper with the
   SAME input (the absolute workspace path), so the two sha1 values are identical
   for the same workspace."

### LOW

10. **(AC12 fragment quality gate - easy to game) - RESOLVED.**
    AC13 (renumbered from AC12) now requires: "at least 12 non-blank lines" (up
    from 10), the sentinel phrases `per-project`, `/learnings`, `vibe X --continue`,
    AND the substring `"preventing"` to anchor the WHY clause. This is meaningfully
    stronger than the iter-1 version.

11. **(Test naming - "test_task014_* OR descriptive names" was loose) - RESOLVED.**
    AC10 now states "prefix mandatory; the Evaluator must be able to enumerate
    new tests via `grep -n "^def test_task014" smoke-test.py`". OR-clause removed.

12. **(Mount-order claim needs caveat) - RESOLVED.**
    Mechanism item 5: "Verified for Linux Docker engine. If this assumption breaks
    for any runtime, the symptom would be the bind landing under the volume's shadow
    rather than on top - failure is observable, not silent." Hedge present.

13. **(AC3 source field path-template resolution) - RESOLVED.**
    Mechanism item 4: "Source value in the override JSON MUST be the resolved
    absolute host path (output of `vibe_projects_bind_path`), not a
    `${localEnv:HOME}` template - same convention the existing /learnings bind
    uses." AC2 reinforces: "The path is fully resolved (no `${localEnv:HOME}`
    template) so smoke tests can override `$HOME` to a tempdir."

---

## New concerns from the revision

### BLOCKING

None.

### MEDIUM

**M1. Out-of-scope #8 mandates a behavior change to existing functionality with
no AC to verify it.**
Out-of-scope item 8 states: "The existing inline cksum fallback in
`_learning_build_override_config`'s run-dir filename computation MUST be replaced
by a call to `vibe_workspace_sha1`." This is a covert functional change to a
live code path (`_learning_build_override_config` line 804-806 in `vibe`). It is
called "out of scope" but then immediately flagged as MUST. There is no AC that
verifies this replacement was made (no static-analysis check, no test asserting
that the old `cksum` branch is gone from `_learning_build_override_config`, no
test asserting the run-dir filename uses the same sha1 as the projects bind
dir). A Generator could skip it (the cksum branch still works for the run-dir
use case), and the Tester has no AC to cite for failure. The Evaluator cannot
call it a failing criterion.

Fix: either add an AC (e.g. "AC3.b: static check asserts no `cksum` call remains
in `_learning_build_override_config`") or move the replacement requirement into
the Mechanism section explicitly and add a test_task014_* check for it.

**M2. AC4/AC5/AC6 - HOME override for "config absent" case is unspecified.**
AC4 says to call `_learning_build_override_config` "with learning fully disabled
(no `~/.vibe/learning.config` file)". But `_learning_build_override_config`
calls `learning_load` internally, which reads `$HOME/.vibe/learning.config`.
To isolate "config absent" in a smoke test, the test MUST override `HOME` to a
tempdir. This is the pattern used by `test_learning_render_devcontainer_config`
(line 987: `env = {**os.environ, "HOME": str(home), ...}`). AC10 mentions
"appropriate `HOME` overrides" once but does not enumerate which sub-cases
require a HOME override (all three: absent, ENABLED=false, .no-learn). A
Generator omitting the HOME override for the ENABLED=false sub-case would read
the real `~/.vibe/learning.config` from the test runner's host and produce
non-deterministic results depending on whether vibe is configured on the CI host.
The spec should explicitly state that ALL three AC6 sub-cases MUST use a clean
tmpdir HOME.

**M3. AC3 static-analysis check is underspecified as a regex.**
AC3 says: "the test reads `vibe`, locates the line invoking `devcontainer up`
(or the construction of `UP_BASE_ARGS` that feeds it), and asserts that an
earlier line... contains a `mkdir -p` call whose argument references the
per-project bind path (either by calling `vibe_projects_bind_path` and capturing
the output, or by literal `$HOME/.vibe/projects/...`)." The "or by literal" branch
allows a Generator to hardcode `mkdir -p $HOME/.vibe/projects/` (no sha1
component) and pass the static check without actually creating the correct
per-project subdirectory. The regex should require that the mkdir argument
contains either `vibe_projects_bind_path` OR `$HOME/.vibe/projects/` followed by
a variable or subshell, not just the bare prefix.

### LOW

**L1. AC10 "at least 10 new tests" gate is gameable by count-padding.**
The count requirement is now specifically "one per AC plus separation tests for
sub-cases", which is better than iter-1, but a Generator could write 10 thin
assertions (e.g. `assert result != ""`) that satisfy the count without exercising
the behavior. The Tester spec inherited from iter-1 had no quality gate on test
bodies. Given that AC1 already enumerates four distinct sub-assertions (a-d), a
Generator that writes one test covering all four of AC1's sub-assertions would
satisfy quality but might be counted as only 1 toward the 10. The count and the
quality gate are slightly in tension. Recommend the Planner note this to the
Tester: each `test_task014_*` function must contain at least one `check()` call
per bullet in the relevant AC.

**L2. AC9 references `smoke-test.py:1449` for `learning_render_devcontainer_config`
but the actual line is 1449-1450 and the function list includes it at line 1449.**
Minor: the line-number citation in Out-of-scope item 7 ("see `smoke-test.py:1449`")
is correct (verified: line 1449 is `"learning_render_devcontainer_config",`).
No action needed - noted as verified-accurate.

**L3. AC13 sentinel gaming is still possible but acceptable.**
The four sentinels (`per-project`, `/learnings`, `vibe X --continue`,
`preventing`) can appear in a one-liner each, technically satisfying the phrase
requirement with 12+ non-blank lines of padding. The added "preventing" anchor
raises the bar meaningfully over iter-1. Residual gaming risk is low; the
Evaluator can reject on quality grounds under the "explaining WHY" intent even
if sentinels are present. No mechanical fix needed.

**L4. AC7 mount-order test verifies the GENERATED JSON, not runtime Docker order.**
The spec is testing what our code writes, not what Docker does at runtime. This
is correct and intentional - we cannot test Docker mount ordering in a no-Docker
smoke test. The spec is consistent on this: Mechanism item 5 explains the
runtime assumption; AC7 tests only that our output array has the right order.
No issue.

---

## Verdict

`pass`

All four iter-1 BLOCKING concerns are fully resolved. All five MEDIUM and four
LOW concerns are resolved. No new BLOCKING concerns. Three new MEDIUM concerns
(M1 unverified cksum-replacement, M2 HOME-override scope, M3 loose mkdir regex)
and three LOW concerns are noted for the Planner to fold inline as tightening
notes to the Generator and Tester.

## If revise: highest-priority fix

N/A - verdict is `pass`. For the Planner's awareness: M1 is the highest-risk
residual item. Out-of-scope #8's MUST-replace-cksum requirement has no
mechanical test behind it. If the Generator skips it, the Tester cannot fail the
task on that ground. The Planner should either add a `test_task014_cksum_removed`
static check (grep that `_learning_build_override_config` no longer contains
`cksum`) or explicitly tell the Generator that AC9's no-regression gate covers it
(it does not - the existing tests do not assert the absence of the cksum branch).
