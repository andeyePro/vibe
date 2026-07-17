# Spec Critique — iteration 3 (convergence check) — task_019: regrettable-content git guard

Audited: `/workspace/.vs/spec.md` (revised again) against the 6 iteration-2 concerns in
`/workspace/.vs/cycle-1/spec-critique-iter2.md`.

## Resolution of iter-2 concerns

**BLOCKING new-1 (audit inherited BLOCK-only rule) — RESOLVED.**
§ Scanner contract "Tier scanning by mode" (spec line 20) now explicitly splits the
rule: `--range` (pre-push) stays BLOCK-tier-only for file content, with the
cries-wolf rationale scoped to it by name; `vibe audit --history` scans **both**
tiers for file content, with its own stated rationale (one-shot, no repeat-nag
problem). Component 7 restates the same split. New AC16 pins a WARN-tier IP
surfacing in `vibe audit --history` output with exit `0`. Matches the requested fix
exactly.

**MEDIUM-2 (`--blob-stdin` location attribution) — RESOLVED.**
Component 7: "the scanner tracks the most recent `commit <sha>` header in the
`git log -p` stream and attributes each finding's location to that commit
(location = `commit <sha>`)." AC9 now asserts "location names the specific commit
sha," and AC16 likewise requires "a WARN line whose location names the commit."
Pinned in both text and AC, not just intent.

**MEDIUM-3 (no AC for pre-push not re-blocking WARN) — RESOLVED.**
New AC17: lands a WARN-only commit via `VIBE_CONTENT_GUARD=off`, then pushes it
as a new branch through the real installed `pre-push` wrapper, asserting `git
push` succeeds. Directly exercises the cries-wolf fix end-to-end.

**LOW-4 (component 6 fixture/allowlist contradiction) — RESOLVED.**
Component 6 now reads "covering **doc/fragment literals only**... Test fixtures
need no allowlist entry: they are runtime-constructed and never staged as
literals (§ Dogfooding)." Contradiction with § Dogfooding rule 1 is gone.

**LOW-5 (`--not --remotes` multi-remote note) — RESOLVED.**
Component 2 appends the acknowledgment verbatim: multi-remote first-push could
under-scan via another remote's tracking refs, "accepted limitation, not covered
by an AC."

**LOW-6 ("new commit messages" wording) — RESOLVED.**
§ Scanner contract now reads "Every mode that scans commit messages scans both
tiers against those messages" — no "new" qualifier left to misparse against
audit's non-incremental scan.

All six iteration-2 concerns are resolved as written, with the fixes exactly as
specified in the iteration-2 report, not partial rewordings that dodge the
substance.

## Specific checks requested

**AC16/AC17 mechanically testable by Haiku:** yes. AC16 is a single `vibe audit
--history` invocation with two independently checkable assertions (exit code
`0`, and a `WARN` line present in output naming the commit) — no judgment call.
AC17 is a single `git push` invocation with one assertion (exit `0` / push
succeeds) — equally mechanical.

**AC17 setup coherence:** yes. `VIBE_CONTENT_GUARD=off` at commit time is
necessary because `--staged` scans both tiers and WARN also exits non-zero by
default (§ WARN semantics) — without the override, `git commit` would itself
block on the WARN-tier IP before there's anything to push. The subsequent push
(no override) succeeds specifically because `--range` is BLOCK-tier-only for
file content per the now-scoped rule. Setup and expected outcome follow
directly from the rest of the spec; nothing invented for the AC.

**Internal contradictions between audit's "both tiers, exit 0 on WARN-only" and
other ACs:** none found. AC9 (BLOCK, exit 1) and AC16 (WARN-only, exit 0) cover
disjoint scenarios under the same component-7 rule and don't collide. Budget
section's cycle mapping (C1: ACs 1-8,10-13,15,17; C2: ACs 9,16) accounts for
both new ACs; AC14 (full smoke-suite regression) is implicitly continuous
rather than cycle-scoped, which is normal for a "no regressions" criterion and
not a contradiction.

## Any remaining concerns

**1. [LOW, informational only] Pre-push doesn't re-scan commit messages in the push range.**
`--range` mode is described only in terms of file content; message-level
secrets are relied on to have been caught by `commit-msg` at commit time (or
by `vibe audit` retroactively if hooks were bypassed/absent). This is
pre-existing design, unchanged by this revision, and wasn't flagged in
iteration 1 or 2. Not blocking — flagging only because the convergence check
asked me to look for contradictions in the tier-scoping logic. No AC or fix
needed.

## Verdict

**pass**

All five iteration-1 blockers and all six iteration-2 concerns (1 BLOCKING, 3
MEDIUM/LOW substantive, 2 cosmetic) are resolved exactly as requested, with
matching ACs (AC16, AC17) that are mechanically testable and internally
consistent with the rest of the spec. The one remaining item is a pre-existing,
non-blocking design note, not a defect introduced by this revision. Spec is
ready for the Generator.
