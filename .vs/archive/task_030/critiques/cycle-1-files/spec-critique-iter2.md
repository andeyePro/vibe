# Spec Critique — task_030, iteration 2

## Iteration-1 concerns: verified addressed
1. chipBlock extraction — spec now specifies `id="step-<id>"[^>]*>` attribute-agnostic match. Confirmed necessary: current `dist/index.html` renders `id="step-launch" data-astro-cid-j7pv25f6>` — a literal `id="step-launch">` match would never fire. No nested `<div>` inside a `.dstep` block, so "up to closing `</div>` or next `id="step-`" is sound.
2. `path    : ` correctly flagged as new content — verified absent from current launch lines, and launcher order (project/path/github/hooks/extras) matches `vibe:3691-3695` exactly.
3. Sign-in line declared site copy — spec text now explicit and non-mechanical-claim.
5. Contiguous-step check includes tone lines — verified against home.md: all 11 existing chips (including curl/leak, whose `tone: fail` lines carry `step:1`) already satisfy 1..len(checklist) contiguity, confirming AC8 is a real, non-invented invariant.
6. Lock-gate limitation recorded as a documented non-defect — present.
7. AC12 holistic read — scoped to Evaluator, distinct from mechanical ACs — present.

Arithmetic check: current build has 11 chips; +2 (first-launch, pat) = 13, matches AC1.

## New concerns
1. (AC4/AC6, MINOR) The current launch checklist's bullet 1 — "finds your project and its GitHub remote, then asks once for a fine-grained PAT – scoped to that one repo" — conflates an everyday behavior (repo discovery) with a first-launch-only one (the PAT prompt) in a single sentence. The spec's "moved verbatim" language cleanly covers the `lines:` transcript entries but gives no explicit instruction for splitting this compound checklist prose. AC5's negative-string list and AC12's holistic read will catch a bad outcome, but won't tell the Generator *how* to phrase the split — worth a one-line steer to save a cycle, not blocking.

No other new gaps found; AC5's lines-map key disambiguation (`"launch":` vs `"first-launch":`) is safe since JSON key quoting prevents substring collision.

## Verdict
pass
