# Spec Critique — task_036 (cycle 1, iteration 2)

## Concerns

Prior BLOCKING items resolved: AC7 now requires the reconciling clause (`not an escalate trigger` / `the checkpoint IS the escalation`) plus an explicit vss.md Close-out branch on `awaiting-approval` (TODO stays open, literal `awaiting-approval` in both places). AC4 now defines the no-candidate path (`no task is awaiting approval` → print and stop). AC8 now requires the Deferred listing for an unresolved checkpoint at verdict-3. MINORs resolved: AC4 adds the restart-at-cycle-1 disclaimer (`no cycle has run`); AC10 raises the ceiling to 14,000 with a ≤450-word target (13,253 current + 450 = 13,703, comfortable headroom, no longer tight); AC11 routes the test to a new `checks_13_spec_first.py` part instead of crowding checks_05.

**[NEW, testability]** AC7's "Mode A step 2 and Mode B Step 4 close-out gain a branch" is asymmetric and only half-anchored. Mode B's target is a real heading (`### Step 4 — Close out`, vss.md line ~115) — clean to slice. Mode A has **no such heading**: steps 1–3 are a bare numbered list under `## Mode A — no arguments` (line 44), and step 2 is one list item among three, starting `2. **If found:**` and ending where `3. **If no bounded item found:**` begins. As written, a Tester asked to verify "Mode A step 2 gained a branch" has no unambiguous anchor to slice on — it must locate the list item by literal-text match rather than heading, and nothing in AC7 says so. Recommend AC7 name the exact anchors explicitly: for Mode B, `### Step 4 — Close out` through the next `##`/`###`; for Mode A, the span from the literal string `2. **If found:**` up to (not including) `3. **If no bounded item found:**`. Without this, the Generator and Tester may disagree on what text region AC7's required literal (`(awaiting approval — /vs --approve <task-id>)`, etc.) must appear inside, or the Tester's slice could accidentally capture step 3's text too.

No other new weaknesses found; anchors for AC1–AC6, AC8, AC9 checked against current vs.md/vsss.md headings and all exist verbatim.

## Verdict
revise
