# Spec Critique — iteration 2 — task_024 (hunk-aware diff parsing, revised)

## Part 1 — iter-1 concern resolution check

All six iter-1 concerns confirmed resolved in the revised text.

1. **Zero-byte context-line rule** — RESOLVED. Design bullet now states the empty check runs BEFORE prefix classification ("an empty string matches no prefix case") and decrements BOTH counters, scoped explicitly to inside-hunk. AC3b is now a permanent fixture (not folded into AC7) covering the exact `diff.suppressBlankEmpty=true` exploit chain from the iter-1 repro, asserting correct file/line attribution on the secret in file B.

2. **Malformed-`@@` fail-safe now AC-tested + forged-budget regression fixture** — RESOLVED. Design bullet explicitly says "This claim is AC-tested (AC8), not just asserted," and AC8 now requires both a `@@ -abc,def +xyz @@` and a truncated `@@ -5,` fixture, asserting no crash AND recovery of header classification after the malformed line. Separately, AC3 folds in the `+@@ -99,5 +99,5 @@` forged-budget probe as a permanent regression fixture per the iter-1 suggestion, even though provably safe by construction today.

3. **AC6 objective oracle + truncated-tail EOF** — RESOLVED. AC6 now requires the Tester to list each differing line with its traced-to stream line, and states "Any difference NOT so traceable is an AUTOMATIC FAIL — not Tester's judgment to waive," closing the subjective-waiver gap. The truncated-tail EOF state (from `head -n 12000` cutting a hunk mid-stream) is now explicitly pinned as expected, non-error, non-finding-affecting behavior.

4. **Pre-change-sha pinned** — RESOLVED. AC5 now specifies capture to `.vs/cycle-1/pre-change-sha.txt` before the first edit of cycle 1, reused by every later differential (both cycles).

5. **Binary-file section in AC5 corpus** — RESOLVED. AC5's fixture list now names a binary-file section (`Binary files … differ`, no `@@`) explicitly.

6. **Mode-change-only section in AC5 corpus** — RESOLVED. AC5's fixture list now names a mode-change-only section (`old mode`/`new mode`, no hunks) explicitly.

## Part 2 — fresh adversarial pass on the revised text

### Verified-safe (answers to the specific questions posed, no spec change needed)

- **Can an attacker ADD a genuinely empty line?** No. An added blank line renders as `"+"` — one byte, the `+` prefix with empty content after stripping. It is never zero bytes on the wire, so it cleanly matches the `+*` case before the empty-check would even matter. A truly zero-byte line (no prefix byte at all) is achievable only by git itself, only for a context line, only under `diff.suppressBlankEmpty=true` — confirmed by the iter-1 repro and unchanged by the revision. The empty-check-before-prefix ordering is correctly scoped to that one git-generated case, not to attacker-controlled content.
- **Does `scan_diff_stream`'s `-U0` world ever see an empty line?** No — confirmed in iter-1's verified-safe list that `-U0` never emits context lines at all (0 context by definition), so the empty-line branch is unreachable dead code in that parser's real call path. Applying the same rule there anyway is harmless: it's git's genuine context semantics generalized, not a special-cased hack, so even if some future call site fed `scan_diff_stream` a non-`-U0` stream, the branch would do the right thing rather than the wrong one.
- **Is the AC3b fixture buildable deterministically?** Yes. `git -c diff.suppressBlankEmpty=true diff -U3 …` is a scoped one-shot config override (no persistent repo/global config mutation, no cross-test pollution), and the "or hand-built equivalent" escape hatch covers any git-version concern. `diff.suppressBlankEmpty` is long-standing (pre-dates any git version plausibly in play here) — not worth a spec change, noting only as a non-blocking portability aside.

### Minor — AC6's real-history corpus will very likely hit non-adversarial "spoof-shaped" content, and the spec doesn't say so (AC6)

The objective-oracle definition ("a line the hunk-aware parser classifies as content but the old parser classified as header noise, or vice versa") is purely syntactic, not intent-based — good, it already covers this case mechanically. But it's near-certain the `git log -p --all | head -n 12000` slice over *this repo's own history* contains organic, non-malicious lines starting with `+++ `, `--- `, `@@ `, `diff --git`, or `commit ` as literal prose — this task's own predecessors (task_019/022/023) document this exact scanner's spoof strings in CHANGELOG.md/TODO.md entries and in `vibe-content-scan.sh`'s own comments. AC6's "Zero differences is also a pass" framing could read as an implicit expectation that differences are rare/exceptional; in practice the Tester should expect a non-trivial count and trace each one, which the spec already permits but doesn't forecast. Not blocking — the mechanism handles it correctly — but a one-line expectation-setting note would save the Tester a false-alarm moment.

### Minor — mid-hunk "prefix matches nothing" fallback is unaddressed, but appears provably unreachable given the design's own trust boundary

Both parsers only ever consume git-generated diff text (`git diff`/`git log -p` output), never raw attacker-supplied streams directly. Given that, every line inside a real hunk is guaranteed by git's own format to carry exactly one of `+`/`-`/space/backslash — or be the zero-byte context case now handled. A "non-empty, no-recognized-prefix" line mid-hunk should be impossible through the legitimate call paths, so no fixture is needed for it. Flagging only so the Tester doesn't go looking for one, or invent a synthetic fixture that's testing an input shape outside the trust boundary the design already relies on.

No blocking findings. No new exploit found; nothing the revision broke.

## Verdict

**pass**
