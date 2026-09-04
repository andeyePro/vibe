# Spec Critique — task_036 (cycle 1)

## Concerns

1. **[BLOCKING, AC7]** AC7 requires both `not an escalate trigger` and `the checkpoint IS the escalation` in the same passthrough sentence. These read as contradictory unless the prose explicitly reconciles them (not on the enumerated hard-escalate list vs. functionally stops the flow like one). As worded, a Generator can paste both literal phrases adjacent to satisfy the sentinel without producing coherent, non-self-contradictory prose — test-evasion risk. Spec should require the reconciling clause explicitly (e.g. "does not abort the whole /vsss loop the way hard-escalate does, but does stop this iteration").

2. **[BLOCKING, AC7/vss Step 4]** vss.md's Mode A Step 2 ("mark `[x]`... commit, stop") and Mode B Step 4 Close-out ("move to Done", "report what was done") assume the executed flow reached a terminal state. Neither AC7 nor any AC requires editing these to special-case a spec-first checkpoint outcome. Without it, `/vss` picking `/vs --spec-first` for a TODO item will fall through to Close-out and incorrectly mark the item `[x]`/Done, or the Generator satisfies AC7's four phrases while leaving this bug live. Add an explicit AC requiring Close-out to branch on `implementation_status: awaiting-approval`.

3. **[BLOCKING, under-specified]** `/vs --approve` with NO task at `awaiting-approval` (all pending/complete, or none exist) has no defined behavior. AC4's "newest awaiting-approval task by default" only covers the multiple-candidates case. Needs an explicit "nothing to approve" message/exit path.

4. **[MINOR, under-specified — flagged by task, worth stating]** `/vsss` reaching its perfection-gate verdict-3 while a spec-first item sits at `awaiting-approval` with an unresolved fromClaude action point is unaddressed. Since spec-first is declared "not an escalate trigger" (AC7) it's unclear whether the optimiser must treat it as blocking exit (report under Final-state Deferred) or may ignore it as satisfied-by-posting-the-question. Recommend requiring it listed under Deferred, mirroring the "remaining TODO items... hard-escalate" verdict-3 precedent in vsss.md.

5. **[MINOR]** Spec doesn't explicitly connect to vs.md's existing rule "changing it restarts at cycle 1 by rule" (line 20). The mechanics are consistent (spec-first edits happen pre-Step-4, before any cycle exists, so there's nothing to restart) but AC4's phrase "spec edited at approval" doesn't make the "this is not a post-approval edit" distinction explicit for a careful reader/Generator. Low risk since Step 3b structurally can't run after cycle 1, but one clarifying sentence would close it.

6. **[MINOR, word budget]** Current vs+vss+vsss = 13,253 words; new ceiling 13,900 leaves ~647 words for all of AC1–AC9's additions. AC4 alone requires 14 literal substrings woven into readable prose (spec-approval semantics, default-task selection, archive interplay) — plausibly 250–400 words on its own once AC1(≤80w for two bullets)+AC3(~12w)+AC6(~40w)+AC7(~50w)+AC8(~90w across 3 bullets)+AC9(~35w, verbatim example) are added. Tight but not obviously infeasible; flag as a real risk of AC10 failure on first draft, not a certainty.

7. **[MINOR, AC11 line budget]** checks_05 is at 1,385/1,500 lines; ~115 lines headroom for a test asserting AC1–AC9 (9 criteria, several multi-substring). Workable if compact, but close to the ceiling — a second part-split may be needed if the Generator writes verbose assertions.

8. Anchors verified present verbatim: `## Step 3 — Spec critic (Sonnet)`, `## Step 4 — Generate` (prefix match, fine), the On-`pass` paragraph, the `--wide` passthrough sentence (vss.md), `### Interaction with the loop`, Consume-protocol step 6. No missing anchors found.

9. No `--approve` flag collision found (only natural-language "approve/approval" usage exists today).

## Verdict
revise
