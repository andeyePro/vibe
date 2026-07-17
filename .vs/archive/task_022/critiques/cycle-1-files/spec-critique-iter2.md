# Spec Critique — iteration 2 — task_022: `vibe audit --history` performance

Plain English, adversarial read of the REVISED `/workspace/.vs/spec.md`, checked against my own iteration-1 critique at `/workspace/.vs/cycle-1/spec-critique.md`. Default to flagging.

## Part 1 — disposition of iteration-1's 5 BLOCKING concerns

1. **10-min old-scanner budget / no fallback — RESOLVED.** AC1 no longer requires the full-history run to finish inside a wall-clock cap. The hard gate is now a bounded 12,000-line slice of `git log -p --no-color --all` (estimated ~2 min at the measured per-line rate), with full-history diff downgraded to best-effort/reported-only. This removes the timeout risk that made AC1 fragile.

2. **No AC mechanically enforces the mandated implementation shape — RESOLVED.** AC7(b) is now a permanent static check: the five named functions' bodies must contain no per-line subprocess-forking idioms (enumerated: `grep`/`sed`/`awk`/`head`/`printf`-pipeline forks), with `line_is_allowlisted` explicitly exempted per A3. This closes the "pass fidelity+timing by some other speedup, never actually stop forking" loophole.

3. **"Location normalisation" loophole in AC3 — RESOLVED.** AC3 now states plainly: "No normalisation step is permitted — both paths emit `commit <sha>` locations already; any difference is a bug, not a formatting artefact." The undefined escape hatch is gone; the comparison is a true byte-identical check.

4. **`set -e` + bare `[[ =~ ]]` guard — RESOLVED.** A2b is now an explicit pinned constraint: every `[[ $content =~ $pattern ]]` must be the condition of an `if`/`&&`/`||` construct (or otherwise guarded), with the failure mode (script death on the first non-matching line) spelled out as the reason. Note: no AC *directly* re-verifies this constraint (see new minor 14 below) — it's pinned in prose but only indirectly covered by AC1/AC2 (a genuinely unguarded bare `[[ ]]` would crash mid-slice and blow the fidelity byte-comparison). That indirect coverage is adequate; not re-opening as blocking.

5. **Nocasematch leak coverage — RESOLVED.** AC2's corpus now explicitly requires "a single line containing both a mixed-case `secret-assignment` trigger and an uppercase `FOO.LOCAL` token" where the case-sensitive `mdns-local` rule must not fire — exactly the leak probe iteration 1 asked for, and it's placed correctly (same line, same `scan_line` call, so it exercises the early-return-before-restore path named in Part A).

All 5 BLOCKING concerns from iteration 1 are resolved in the spec text, not merely waived.

## Part 2 — disposition of iteration-1's 6 minors

6. **AC5 omitted `--messages-stdin` — RESOLVED.** Mode list now includes it explicitly, plus malformed-input sub-cases.

7. **B1 malformed-input untested — RESOLVED.** AC5 now names three concrete fixtures: empty record, truncated final record, body-only record (no sha line).

8. **Sort locale unpinned — RESOLVED.** `LC_ALL=C sort` is now specified in AC1, AC2, and AC3.

9. **`pre-change-sha` undefined — RESOLVED.** AC1 now defines it as "the commit immediately preceding the Generator's first commit for this task."

10. **AC2 doesn't test `--message`/`--range` parity directly — PARTIALLY RESOLVED.** `--range` was added (now covers the tier-`block` path). `--message` mode itself still has no direct old-vs-new fidelity check anywhere — AC3 compares NEW `--messages-stdin` against the OLD `--message`+awk *loop*, which is a different comparison (new mode vs old mode), not a same-mode `--message` old-vs-new differential. The shared-code-path argument (all modes funnel through the same swapped primitives) is reasonable but is still implicit, not stated as a deliberate coverage decision the way the recommendation asked. Downgrading to a minor still-open item rather than treating it as fully closed — see new item 14 below, which folds this in.

11. **No permanent regression guard against the fork-storm reappearing — RESOLVED.** The Test-location section now names AC7's static checks explicitly as "the permanent guard against the fork-storm quietly returning," and AC7(b) (closing old concern 2) gives it real teeth. This is the same fix as concern 2; flagging it once is enough.

## Part 3 — fresh adversarial pass over the revised text (new weaknesses)

12. **BLOCKING (new) — AC1's "IDENTICAL bounded stream" is not guaranteed identical if captured by two live invocations.** AC1 says: run the OLD scanner and the NEW scanner "over the IDENTICAL bounded stream `git log -p --no-color --all | head -n 12000` of the vibe repo." The scanner *binaries* are pinned (one via `git show <pre-change-sha>`, fixed regardless of live HEAD), but the *input stream* is not similarly pinned — it's a live command against `--all` refs of the same repo this task is committing into (TODO.md/CHANGELOG.md bookkeeping, the scanner file itself, smoke-test.py additions — all Part A/B deliverables land in this exact repo). If the Tester runs the command twice (once piped into the old binary, once into the new binary) at two different wall-clock moments, any commit landing in between — including this cycle's own bookkeeping commit, or another concurrent vibe session in the same repo (a documented drift risk per this environment's own memory: "Multi-session targets drift — re-audit before mutating") — shifts the top-of-history window that `head -n 12000` captures. A one-line commit landing between the two invocations changes the diff content in the 12k-line window and produces a false byte-identical mismatch on a *hard gate*, unrelated to actual scanner fidelity. The spec's own rigor elsewhere in this same AC (pinning locale, pinning `pre-change-sha`) shows the standard this should be held to, and this gap doesn't meet it. Fix: require the stream be captured to a single file (or variable) exactly once, then fed unchanged into both scanner invocations — not re-derived from a second live `git log --all` call. Word it explicitly, e.g. "capture the stream once via `git log -p --no-color --all | head -n 12000 > slice.txt`; both scanner runs read from `slice.txt`, not from a second live git invocation."

13. **Minor (new) — AC7(b)'s function-body extraction method is unspecified, leaving room for a loose static check.** A2c enumerates the forbidden idioms concretely (`| grep`, `| sed`, `| awk`, `| head`, `$(printf …)`, `$(grep …)`, "etc."), which is reasonably tight. But AC7(b) requires scoping the check to *within* five named function bodies only, and the spec doesn't say how a Tester should extract those boundaries (brace-matched range, `sed -n '/^fn()/,/^}/p'` assuming column-0 closing braces, or something more robust). A naive whole-file grep for the same strings would false-positive on `line_is_allowlisted`'s permitted `grep -qE` sitting textually near the five functions, or on comments/docstrings mentioning "grep"; an overly narrow line-range extraction could false-negative if a function's closing brace isn't at column 0. Not blocking — A2c's enumeration is concrete enough that a competent Tester can write a correct extraction — but worth a one-line spec note pinning the extraction approach, since this check is now explicitly load-bearing as "the permanent guard" (per resolved concern 11).

14. **Minor (carried over, sharpened) — `--message` mode has no direct fidelity test, and A2b's guard-discipline constraint has no dedicated static check.** Folding old minor 10's residue in here: `--message` routes through the same swapped primitives as every tested mode but is never itself old-vs-new differentially compared (only asserted "retained unchanged" at the interface level in B4). Separately, A2b's "must be guarded, not bare" constraint (resolved as concern 4 above) has no AC that verifies it by inspection — only indirect coverage via AC1/AC2 crashing if it's violated. Neither is dangerous enough to block (both have adequate indirect coverage through shared code paths and the real-history slice), but calling them out so the Tester doesn't assume they're independently verified.

## Verdict

BLOCKING: 1 new (item 12). Minors: 2 new/carried (items 13, 14). All 5 original BLOCKING and all 6 original minors from iteration 1 are resolved (one, item 10/14, only partially — downgraded and re-flagged rather than closed).

revise
