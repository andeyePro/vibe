# Spec — task_010: /learn smart-capture (always intelligent)

**Revised after Spec Critic iter 1 + 2.** Iter-1 closed 4 BLOCKING + 9
MEDIUM/LOW. Iter-2 closed 1 BLOCKING (AC20 floor 17→19 to match AC1-AC17 + AC18
+ AC19 coverage clause), 1 MEDIUM (AC18 diff-allowlist now includes
`smoke-test.py` since Tester adds it in the same cycle), and 1 LOW (AC10's
negative-grep set now fully named in AC body, not split across § Known
limitations). All iter-1 concerns confirmed resolved.

## Task summary

Extend `devcontainer/commands/learn.md` to add a Claude-driven semantic-check phase that runs BEFORE the Write tool call but AFTER the existing format-body step. The check has four behaviours:

1. Read existing `/learnings/*.md` entries to detect contradictions with the new pattern.
2. Flag low-quality input (vague references like "do it like Word does"; obvious-nonsense like "the earth is flat") regardless of whether anything contradicts it.
3. Zero-friction passthrough: if the input is already efficient and non-contradictory, just apply it WITHOUT surfacing any options to the user (no friction for good input).
4. When improvement is possible, present numbered options:
   - **Z1** is ALWAYS the user-verbatim original (option 1 is always opt-out from any rewrite).
   - **Z2..Zn** are smarter alternatives Claude constructs (cap n at 3 — typically 1 or 2 alternatives, no more than 3).
   - **Z_n+1** offers to edit an existing contradicting entry rather than add a new file (only present when contradiction exists; omitted otherwise).
   - **N** drops the new capture entirely; existing entries unchanged; no Write issued.

Marginal token cost per `/learn` invocation: ~2-5k tokens. The semantic check runs on EVERY `/learn` invocation (no conditional skipping based on library size, input length, or any other heuristic).

## Acceptance criteria

**File-shape contract for `devcontainer/commands/learn.md`:**

1. `learn.md` contains a section with the exact `##` heading `## Semantic check` (level-2 heading, capitalisation as shown). Tester greps for the literal line `## Semantic check`.

2. The "How it works" section's numbered list is restructured so that the semantic check appears AFTER the format-body step and BEFORE the preview step. Tester verifies relative ordering using `awk` line numbers, not absolute step numbers: in the file, the line containing the literal phrase `Formats the entry body` MUST appear before the line containing `Runs the semantic check` (or trivially equivalent — see AC3a), which MUST appear before the line containing `Prints a preview`. Generator MAY split the semantic check into multiple sub-steps as long as the relative ordering holds.

3. The "How it works" step that introduces the semantic check uses the literal phrase `Runs the semantic check` (Tester greps for this exact phrase, case-sensitive).

3a. The Semantic-check section body contains the literal phrase `existing /learnings entries` (verbatim, case-sensitive). This nails the "reads existing entries" intent without requiring paraphrase tolerance.

4. The Semantic-check section explicitly addresses low-quality input. Tester greps the section body for at least one of the literal phrases: `low-quality input`, `low quality input`, `vague reference`, or `unclear input`.

5. The Semantic-check section explicitly states zero friction for already-good input. Tester verifies BOTH:
   - The section contains the literal phrase `zero friction` (case-insensitive).
   - The section contains the literal phrase `no options` OR `without surfacing options` OR `no options surfaced` (case-insensitive). This catches the behaviour, not just the slogan.

6. The Semantic-check section enumerates the option scheme. Tester greps the section body for ALL of:
   - The literal label `Z1` AND the literal phrase `user-verbatim` (or `user verbatim`) within 200 characters of each other.
   - The literal label `Z2`.
   - The literal phrase `edit existing` OR `edit an existing`.
   - The literal label `N` AND the literal phrase `drop` (or `drops` or `cancel` or `cancels`) within 200 characters of each other. This nails N's drop/cancel semantics.

7. The Semantic-check section states that `Z1` is ALWAYS the user-verbatim original. Tester greps for the literal phrase `Z1 is always` OR `Z1 is ALWAYS` AND the literal phrase `verbatim` within the same paragraph (defined as: between two blank lines, OR within 400 characters of each other if no blank-line separation).

8. The Semantic-check section names the marginal token cost. Tester greps for the literal phrase `2-5k tokens` OR `2–5k tokens` (en-dash) OR `2 to 5k tokens`. No other token-count phrasings accepted.

9. The Semantic-check section preserves the hook-prompt context: the preview still comes BEFORE the Write so the hook prompt has clear context. Tester greps for the literal phrase `preview` AND the literal phrase `hook` within the same paragraph (defined as: between two blank lines, OR within 400 characters of each other).

10. The Semantic-check section explicitly forbids conditional skipping. Tester greps for the literal phrase `every /learn invocation` OR `runs on every invocation` OR `always runs` AND the section MUST NOT contain any of the conditional-skip phrasings: `skip the`, `skip if`, `bypass the check`, `omit the check` (Tester does a negative grep for ALL FOUR). False positives on "skips ahead", "skip-list", "bypass route" tolerated; the forbidden patterns are specifically conditional-skip phrasings.

11. The Semantic-check section caps Z-options. Tester greps for at least one of: the literal phrase `cap n at 3`, OR `no more than 3`, OR `up to 3 alternatives`, OR `1 or 2 alternatives`. This catches the "don't generate 10 alternatives" intent.

**Existing-behaviour regression gate:**

12. Filename format unchanged. `learn.md` MUST still contain the literal substrings `ts=$(date -u` AND `binascii.hexlify` AND `${ts}-${rand}.md`.

13. Body format unchanged. `learn.md` MUST still contain the literal substring `printf '# %s\n\n%s\n'` AND the phrase `# <timestamp> header line`.

14. Multi-line patterns supported. `learn.md` MUST still contain the section heading `## Multi-line patterns` (verbatim).

15. Host-only push instruction preserved. `learn.md` MUST still contain the literal substrings `vibe learn --push` AND `host-only`.

16. `/learnings` mount-check refusal message unchanged. `learn.md` MUST still contain the literal phrase `/learn: /learnings is not mounted`.

17. PreToolUse hook role unchanged. `learn.md` MUST still mention `PreToolUse hook` (case as shown).

**Scope-creep gate:**

18. NO new file is created under `devcontainer/claude-md/`. NO new file is created under `devcontainer/agents/`. NO new file is created under `devcontainer/commands/` other than the existing `learn.md`. NO change to `devcontainer/install-claude-extras.sh`. NO change to `Dockerfile`. NO change to `~/.claude/CLAUDE.md` content rules. Tester verifies via `git diff --name-only HEAD~1 HEAD` (after Generator + Tester commits land in the same cycle) that the changed-file set is a SUBSET of `{devcontainer/commands/learn.md, smoke-test.py, .vs/spec.md, .vs/progress.md, .vs/tasks.json, .vs/cycle-1/...}`. Files outside this allowlist are scope creep. `smoke-test.py` is included because Tester adds the test function in this same cycle.

**Smoke-test contract:**

19. `smoke-test.py` gains exactly one new function named `test_task010_smart_capture` (canonical: lowercase, no extra underscores, exactly this name). Tester writes it; Generator MUST NOT touch `smoke-test.py`.

20. The new function contains AT LEAST 19 `check(...)` calls covering EVERY AC1-AC19 directly (one check per AC minimum, more allowed). Coverage breakdown: AC1-AC11 = 11 checks (file-shape contract); AC12-AC17 = 6 checks (regression gate); AC18 = 1 check (diff-name-only); AC19 = 1 check (function-presence self-reference). Total floor: 19. Running `python3 smoke-test.py` MUST produce at least 19 new `✓` lines whose label includes `task_010` or `task010`.

## Out of scope

- `/learn --review` library hygiene pass — that's task_011.
- Rebuild-time `/learn` efficiency hint — that's task_012.
- Auto-promote feedback memories from `~/.claude/projects/.../memory/` to `/learnings` — separate TODO entry.
- Backend storage changes (filename format, file body format, location). Format stays byte-identical to host-side `vibe learn`.
- Adding `--push` to the host-side `vibe learn` command.
- Multilingual semantic check; English only.
- Persisting the user's chosen Z* option for replay in similar future captures.
- Conditional skipping of the semantic check (explicitly forbidden by AC10).
- Adding new files under `devcontainer/claude-md/` or `devcontainer/agents/` (explicitly forbidden by AC18).

## Test location

`smoke-test.py`. Tester appends `test_task010_smart_capture` and registers it in `main()` per existing convention. Generator MUST NOT touch `smoke-test.py` (immutable test file rule).

## Proposed budget

2 cycles. TODO predicted "Likely 2 cycles `/vs`" — honoring that.

## Known limitations (acknowledged, NOT acceptance criteria)

- All ACs test what `learn.md` SAYS, not what Claude actually DOES at runtime when `/learn` is invoked. The smart-capture phase is prose instructions to the model, not executable code, so runtime testing requires manual `/learn` invocation in a real container with a populated `/learnings` library. This is a known limitation of slash-command-body tasks; it is documented here so the Evaluator (and future readers) understand what "all ACs pass" means: the documentation is correctly shaped, not that the runtime behaviour is verified.

- AC10's negative grep on `skip the` and `skip if` is heuristic. A Generator could write conditional logic in different phrasings (e.g. `bypass`, `omit`). The full negative-grep set is `skip the`, `skip if`, `bypass the check`, `omit the check`. Tester should include all four. (Promoted to a regular AC since this is testable; see AC10 above as the canonical wording.)
