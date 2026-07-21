# Spec Critique — task_026 iteration 3 (`vibe pat [repo]` PAT rotation + launch-time 401 reprompt)

Re-audit against the revised `/workspace/.vs/spec.md`, verifying each iteration-2 concern's disposition, then sweeping fresh at the same adversarial standard.

## Iteration-2 concern disposition (all 5 checked against the revised text)

1. **BLOCKING (AC3 / `rotate_token`, guarded `read`) — RESOLVED.** Contract bullet 11 now pins the exact idiom: "the read MUST be errexit-guarded so immediate EOF cannot abort before the message prints: use the established `_learning_capture` idiom (`if ! IFS= read -rsp "..." token; then token=""; fi` or equivalent; see vibe ~1438)." Verified `if ! IFS= read -rsp "prompt" token; then token=""; fi` is errexit-safe (the read sits inside a negated conditional, exactly the class `set -e` exempts) and that a lone-`\n` input (successful read, empty value) and immediate EOF (guarded failure branch) now converge on the same `[ -z "$token" ]` abort path. AC3 also now states both stdin shapes explicitly ("tested BOTH ways: immediate EOF ... and a lone `\n`"). Genuinely closed, not reworded.

2. **BLOCKING (AC5, `set +e` bracketing) — RESOLVED.** The Test location section (not just an AC) now states: "any bare call to a function expected to return non-zero (`stored_token_rejected` in AC5, the stubs' callers in AC8) MUST be bracketed `set +e; …; set -e` (precedent: the task_017 c2 lock tests, e.g. `test_task017_c2_lock_release_wrong_project_refused_intact`) or written as `if fn; then … else … fi` — never `fn; echo $?` bare." Verified this precedent exists verbatim at `smoke-test.py:7649-7653` and that the named idiom is errexit-safe. The instruction is now global (covers AC5/AC6/AC8), not buried in one AC. Genuinely closed.

3. **Minor (AC4 stdin shape) — RESOLVED.** AC4 now reads "(test feeds closed/empty stdin so the run terminates via the abort path rather than blocking at the prompt)."

4. **Minor (wrapper's pinned return 0) — RESOLVED IN PROSE, but see new concern 1 below.** Contract bullet 13 now states: "The wrapper ALWAYS returns 0, whichever branch runs (never propagate `stored_token_rejected`'s status) — its bare one-line call site sits under `set -e`, and a non-zero return would turn every healthy launch into a hard failure." The prose fix is real and correctly reasoned. However, verifying whether the *test* actually enforces it turned up a fresh gap — see below.

5. **Minor (curl config-line escaping) — RESOLVED.** Bullet 12 now states: "The config line is unescaped: tokens containing `"` or `\` are out of contract — GitHub PAT charset is alphanumeric+`_`, and the fixture token complies."

All five iteration-2 concerns are substantively fixed. Four are fully closed both in prose and in test coverage; the fifth (return-0 contract) is fixed in prose but the fix reveals an AC gap, detailed below.

## Concerns (new, found in this iteration-3 audit)

1. **BLOCKING (AC8, wrapper's own return code untested in branches c/d).** Bullet 13's fix ("ALWAYS returns 0, whichever branch runs") is a correctness requirement with a real consequence if violated: the call site is a bare statement under `set -e`, so any non-zero return kills the entire `vibe` launch. AC8 tests this explicitly for (a) `VIBE_PAT_CHECK=0` and (b) empty-token — both say "returns 0" in terms. But (c) and (d) — the two branches that exercise `stored_token_rejected`, i.e. the ones bullet 13 exists to protect — say nothing about the wrapper's return code: "(c) token present + rejection stub returns 0 → warning line emitted (pinned string) and `setup_token` stub called once with the repo arg; (d) token present + rejection stub returns 1 → `setup_token` stub not called, no warning." Neither asserts `returns 0`.
   This is not a paper gap. The spec's *own* established style for the sibling function in this same task — `stored_token_rejected`'s decision rule ("capture the `-w` output; ignore curl's own exit status entirely") — is exactly the "capture rc, then decide" pattern. A Generator carrying that same muscle-memory into `maybe_reprompt_stored_token` could plausibly write:
   ```
   stored_token_rejected "$repo" "$token"; rc=$?
   if [ "$rc" -eq 0 ]; then
     printf '  ⚠ Stored PAT for %s was rejected...\n' "$repo"
     setup_token "$repo"
   fi
   return "$rc"
   ```
   This passes AC8(a)-(d) as currently worded — right stub called/not called, right message present/absent — but in branch (d) (`rc=1`, the *common* case of a still-valid stored token) it returns 1, which under the bare `set -e` call site kills every ordinary launch that has a valid stored PAT. AC8 would show green while shipping a script that breaks on the majority-case launch. Pin the fix by adding an explicit "returns 0" assertion to AC8(c) and AC8(d), mirroring (a)/(b) — closing exactly the gap bullet 13's prose was added to prevent.

2. **Minor (launch-path integration, AC8's static check is presence-only, not placement- or reachability-aware).** Bullet 14 already correctly specifies *where* the call goes ("the branch where `lookup_token` returned a value... Never called after a fresh interactive paste"), and that prose is unambiguous enough that a competent Generator is unlikely to misplace it. But AC8's only enforcement is "one static assertion that the launch path contains a `maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"` call line" — a bare text-presence grep. It would pass equally whether the call sits correctly inside an `else` paired with `if [ -z "$GITHUB_TOKEN" ]; then setup_token ...; fi`, or incorrectly as a statement following the closed `if`/`fi` (which — since `setup_token` reassigns `GITHUB_TOKEN` as a side effect at `vibe:400` — would fire the 401 probe on a token pasted seconds earlier, exactly what bullet 14 forbids), or even inside a comment. Given this is explicitly accepted in iteration 2's disposition as an architectural residual (the real call site is unreachable to `smoke-test.py`'s `VIBE_SOURCE_ONLY=1` convention), full closure isn't required — but tightening the static check to require the call line appear between an `else` and its paired `fi` (rather than anywhere in the file) would close the concrete double-probe failure mode cheaply, without needing the deeper architecture change iteration 1 already rejected as infeasible.

## Verdict

revise
