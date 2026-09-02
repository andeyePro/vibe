# Spec critique — task_029

## Concerns

1. **AC5, BLOCKING — "read-only" contradicts the accurate wording it replaces.** The current § At exit sentence being deleted (line 243) reads "brain2 is **write-files-only** from a container — never `git` against it" — this matches the project's own established convention (global CLAUDE.md: "Never run git against /brain2 - just write files; the Mac auto-commit / gardener persists them"; brain2's trust-model.md confirms Claude *writes* notes). AC5 mandates the relocated sentence contain the literal word **`read-only`**, which is factually wrong for this repo's mount (it's writable at the file level, only `git push` is blocked) and regresses the existing accurate phrasing. Fix: AC5's required word should be `write-files-only` (or drop the specific-word requirement and just require the `git` clause).

2. **AC6, BLOCKING — deletion sentinels are substring-only; real test-evasion path exists.** grep confirms only two spans mandate the fromClaude exit-append (lines 239 and 327) and both are targeted. But AC6 checks absence of three literal strings, not removal of the surrounding paragraphs. A Generator can satisfy AC6 mechanically while (a) leaving orphaned dangling prose around the excised phrase, or (b) — more seriously — paraphrasing the exact same mandate ("when fromto is active, also mirror the report into fromClaude") without using the forbidden literal strings. That reproduces precisely the contradiction task_029 exists to remove, yet passes every AC6/AC9 sentinel. Recommend AC6 add a semantic assertion (e.g. Tester diffs the two spans' surrounding paragraphs, or the section's total line count drops by N), not string-absence alone.

3. **AC3 vs AC7, MINOR — duplicated hygiene language across adjacent sections.** New § fromto format sentinel "no FYIs, no progress notes, no session report" substantially overlaps § Question format's preserved sentinel "questions and blocking asks only — no progress notes, no FYIs" (AC7). Two adjacent subsections both asserting near-identical hygiene rules reads as redundant and eats into the AC12 word budget for no new information. Consider whether § fromto format should reference § Question format instead of restating it.

4. **AC12, MINOR — tight but plausible.** Estimated net add: heading (~3w) + intro/override prose (~60-70w) + AC2 template (31w, verified by `wc -w`) + AC4/AC5 prose (~35w) ≈ 150-165w added; minus deleted § At exit (52w) and § Reporting-back closing paragraph (30w) = 82w removed. Net ≈ +70-85w, under the 120 cap — but the estimate has real variance (placeholder explanations for `<harness>`/`<repo>`/`<project>`, plus concern #3's redundancy, could push it over). Not blocking since AC10/AC12 will mechanically catch an overrun, but flag for the Generator to write tersely.

5. **AC9, not blocking — accepted design.** Skip-with-note for AC8 when `/brain2` isn't mounted matches existing project convention for per-machine mounts (graceful degradation elsewhere in the codebase). No objection.

## Verification notes
- Confirmed no third location in vsss.md mandates the fromClaude exit-append beyond lines 239/327 (grep clean).
- Confirmed heading order claim in AC7 matches current structure exactly.
- Confirmed AC8's frontmatter field list matches the brain2 meta-note convention (trust-model.md, zotero-operation.md have `aliases`; vibe-operation.md's `author` is a bracketed model-id list, distinct from AC2's `Claude (<harness>, <repo>)` placeholder — but that placeholder is template *body content*, not the note's own frontmatter, so no conflict).
- `/brain2/andeye/vibe-fromClaude.md` already exists in AC2's exact template shape (dated 2026-09-02) — corroborates AC2 is the right target shape, out of scope per spec.
- No pre-existing `/brain2/meta/fromto-format.md` or other doc of this format — AC8 is not a duplicate.

## Verdict
**revise** — concerns 1 and 2 are BLOCKING (a factual regression and a live test-evasion path); fix both before Generator dispatch.
