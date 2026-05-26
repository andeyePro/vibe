# Spec critique — task_010 cycle 1, iter 1

## Concerns

### BLOCKING

**1. AC14: "at least 10 new sentinel checks" is unverifiable as stated (AC14)**
The spec says "each AC1-AC12 represented by at least one check" but AC1–AC12 is 12 criteria and the floor is 10 checks. That arithmetic contradiction means a Generator can satisfy "10 checks" without covering all 12 ACs. The count floor should be ≥12 (one per AC), or the coverage rule should say "each of AC1–AC12" without a numeric floor that contradicts it. A Tester can trivially pass by counting 10 sentinel lines without checking coverage.

**2. AC2: step-number assertion is fragile and ambiguous (AC2)**
"After the change: step 4 is the semantic check; step 5 is the preview; step 6 is the Write; step 7 is the post-Write info" — the current `learn.md` has 6 numbered steps. This assertion assumes exactly one new step is inserted. If the Generator splits the semantic check into sub-steps, or renumbers non-consecutively, a test counting literal "4." / "5." / "6." / "7." patterns will either pass on irrelevant text or fail on a valid restructuring. The AC should verify relative ordering of labelled headings/phrases, not absolute step numbers.

**3. AC6: option scheme is under-constrained — Generator can omit N's semantics (AC6)**
The spec says the section must enumerate four labels: Z1, Z2, "edit existing"/"edit an existing", and N. It says nothing about N being described as "cancel" or "drop". A Generator can write "N is the nuclear option" and mechanically satisfy the sentinel check. The AC needs to specify that N must be described as dropping/cancelling the capture and preserving existing entries.

**4. AC14: immutable-test-file rule conflicts with "Generator MUST NOT touch smoke-test.py" (AC14 vs Test Location)**
The spec says Tester writes tests to `smoke-test.py`, but also says "Generator MUST NOT touch smoke-test.py". That's the /vs architecture. However, the AC itself says "smoke-test.py adds at least 10 new sentinel checks" — in the Evaluator's view, is this checked before or after the Tester phase? The AC implies the Generator is being evaluated against Tester-written tests, but the Generator has no way to know whether the Tester will name the function `test_task010_smart_capture` vs `test_task_010_smart_capture` (both spellings are allowed by AC14). The Evaluator needs a single canonical function name, not an alternation.

### MEDIUM

**5. AC5: "zero friction" literal phrase test is evasion-prone (AC5)**
A Generator can satisfy this by writing "the command aims for zero friction in theory" — the phrase appears but the intent (no options surfaced for already-good input) is not tested. The AC should require that the section describes the _behaviour_ of passing through without presenting options, not just that it contains the phrase.

**6. AC7: "always" near "verbatim"/"Z1"/"user-verbatim" is too loose (AC7)**
Proximity is not defined. A Generator can write a sentence with "always" in one paragraph and "verbatim" in the next and pass a grep-based sentinel. The AC needs either a tighter phrase ("Z1 is always the user's verbatim input" or "Z1 is always user-verbatim") or at minimum a same-sentence constraint.

**7. AC8: token-cost mention is style, not behaviour (AC8)**
This is documentation pedantry, not a contract the runtime enforces. That's acceptable in principle, but the AC allows the Generator to satisfy it with a throwaway parenthetical that is later stripped without consequence. More importantly, the spec says "similar token-cost reference" which is too vague — "a handful of tokens" satisfies the intent but fails the grep, while "2–5k tokens" passes it. The sentinel should nail down the exact phrases accepted.

**8. AC9: "preview" and "hook" together — no proximity constraint (AC9)**
Same issue as AC7. Two words appearing anywhere in the section passes the grep. Should require they appear in a meaningful context (e.g. same sentence, or same bullet).

**9. AC3: "verbatim phrase or trivially equivalent" is undefined (AC3)**
"trivially equivalent" is a human judgement call that a mechanical test cannot enforce. If the Tester writes a grep for the exact phrase and the Generator writes a paraphrase, the test fails even though the intent is met. If the Tester accepts paraphrases, it is no longer mechanical. This should be nailed to an exact phrase or a small explicit set of alternatives.

**10. Out-of-scope loophole: semantic-check trigger threshold not excluded**
The spec describes the check as running for every `/learn` invocation but says nothing about whether it can be made conditional (e.g. only when `/learnings` has entries, only above a word-count threshold). A Generator could add a `if [ $(ls /learnings | wc -l) -gt 0 ]` guard that silently skips the check on a fresh library. This conditional path should be explicitly excluded or explicitly permitted.

**11. Out-of-scope loophole: no upper bound on Z-options count**
The spec says Z2..Zn are alternatives Claude constructs. It does not bound n. A Generator could generate 10 alternatives, which is not the intent. The spec should cap n at a small number (e.g. 3) or state "typically 1–2 alternatives".

**12. AC13: "No CLAUDE.md fragment" — doesn't exclude settings.json or agents/ changes (AC13, AC15)**
AC15 says only `learn.md`, `smoke-test.py`, and `.vs/` artifacts. AC13 names CLAUDE.md specifically. These are redundant but fine. However, AC15 uses the word "changes" — does that include `devcontainer/claude-md/` fragments (which are the source of truth for CLAUDE.md population)? If Generator adds a fragment there it would be scope creep that AC15's file-list test would catch — but only if the Tester checks the `devcontainer/claude-md/` directory too. This should be made explicit.

### LOW

**13. AC10: regression sentinels test presence, not correctness (AC10)**
Checking that `"ts=$(date -u"` still appears in the file verifies the string wasn't deleted, but not that the surrounding logic is intact. A Generator could move these strings into a comment block and break the command flow while still passing the sentinel. Acceptable for a doc-only file, but worth noting.

**14. AC1: "Semantic check" exact heading is tested but capitalisation variant not clarified (AC1)**
The AC says "exact phrase: 'Semantic check'" — is "## Semantic check" required, or will "### Semantic check" or bolded text satisfy it? A Tester writing a `##`-anchored grep will fail on a valid `###`-level section. The heading level should be specified.

**15. No AC covers the actual runtime behaviour — only documentation (structural)**
Every AC tests what `learn.md` _says_, not what Claude actually _does_ when `/learn` is invoked. The smart-capture phase is prose instructions to Claude, not executable code, so runtime testing is not possible. This is a known limitation of slash-command spec tasks and is acceptable — but the Evaluator should be aware that "all ACs pass" means "the documentation is correct", not "the feature works".

## Verdict

`revise`
