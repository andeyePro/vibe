# Spec Critique — task_044 (cycle 1)

## Concerns

1. **[AC5] BLOCKING — placement requirement is untestable by the assigned
   method.** AC5 requires the warning be "emitted from the launch banner code
   path immediately after the `codex :` header line." But `vibe` has
   `[ "${VIBE_SOURCE_ONLY:-}" = "1" ] && return 0` at line 3714, and the
   `codex :` banner block (`_codex_banner=...`, line ~4337) sits well *below*
   that guard — sourcing with `VIBE_SOURCE_ONLY=1` (the only method the Test
   location section names for AC5) never executes it. No smoke test today
   exercises the real banner output (`grep -rn "codex   :" smoke/*.py` is
   empty) and none is scoped here. As written, a Generator can implement
   `_codex_dir_mode_warning` correctly, pass every named test, and never wire
   it into the banner at all (or wire it in the wrong spot) with nothing
   catching it. Fix: either name a source-text-adjacency check (the codebase
   already does this pattern — see `checks_01`'s `(REPO / "vibe").read_text()`
   greps) as the verification method for the wiring clause, or drop the
   "immediately after" placement language from the AC and accept placement is
   enforced by review only.

2. **[AC6] BLOCKING — MANUAL-TESTS.md Test 54 step 8 directly contradicts the
   new behaviour and is out of the doc-update scope.** Test 54 step 8 today
   reads "With Codex disabled, explicitly `/ask astra ...` still works" — the
   exact behaviour AC1 reverses. Test 54's own preamble says "Run on branch
   `astra` before merging its PR," i.e. this is the merge-gate manual check,
   and it will now describe the old, wrong contract. AC6 lists only
   `ask.md`, `review.md` and README; MANUAL-TESTS.md isn't named anywhere in
   the spec. Needs an AC (or an amendment to AC6) requiring step 8 be
   corrected to reflect `codex=off` now blocking `/ask astra` too.

3. **[AC2] BLOCKING — malformed-policy behaviour for `ask astra` is
   unspecified.** AC1/AC2 pin exactly four `.vibe/review-slots` shapes for
   `ask astra` (`codex=off`, `gemini=off` alone, empty, absent). Nothing says
   what `ask astra` must do when the policy is tracked, symlinked, or has
   duplicate/invalid entries (all cases `slots()`/`review` already fail
   closed on). Given the task's own "no OpenAI egress" framing, a Generator
   could plausibly wrap the new check in a try/catch that treats a policy
   *read* error as "codex enabled" (fail open) purely because no test forbids
   it — that would be the exact regression this task exists to close. Add an
   explicit AC (or extend AC2) requiring `ask astra` to fail closed on every
   `slots()` failure mode, not just the literal `codex=off` case.

4. **[AC4] MINOR — golden vector is argv-only, never exercised against the
   real `claude` binary.** All existing delegate tests run against a stub
   (file's own docstring: "fake vendor CLIs, no network/auth"), so this is a
   pre-existing limitation, not new — but `--permission-mode plan` +
   `--permission-prompts none` combined with `--tools ''` is a materially
   different flag set from what shipped and was manually verified in Test 54
   step 4. No MANUAL-TESTS update is scoped to re-confirm a real `claude -p`
   one-shot still returns `type: result, subtype: success` under the new
   flags before merge.

5. **[AC6] MINOR — required doc phrasing is not pinned.** AC6 says ask.md
   must state that `codex=off` "also refuses `/ask astra`" and README must
   carry "the same two-switch sentence" — no literal substrings are given
   (contrast AC1, which pins exact stderr text). Low risk since Generator and
   Tester are the same cycle's outputs, but a haiku Tester may write a
   substring check that's satisfied by prose that doesn't actually convey the
   semantic change. Recommend pinning 1-2 required substrings per file.

6. **[AC5] MINOR — mode-check edge cases unaddressed.** Examples given are
   only 3-digit modes (0755/0750/0705/0700). Undefined: 4-digit modes with
   setuid/setgid/sticky bits (e.g. 1755), and a Codex dir reached via a
   symlink. Low real-world likelihood (the dir is created by `codex login`),
   but worth one clarifying sentence so the Generator doesn't need to guess.

7. **[AC7] MINOR — "Generator must not edit smoke/" scope is ambiguous.** The
   sentence grammatically scopes the ban to the one assertion replacement;
   intent is almost certainly a blanket ban on Generator touching anything
   under `smoke/`. Worth stating as its own sentence to remove doubt, since
   this Generator also touches `vibe` and `vibe-delegate.mjs` whose tests
   live in the same directory.

## Verdict

**revise**
