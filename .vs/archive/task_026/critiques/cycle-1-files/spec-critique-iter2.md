# Spec Critique — task_026 iteration 2 (`vibe pat [repo]` PAT rotation + launch-time 401 reprompt)

Re-audit from scratch against the revised `/workspace/.vs/spec.md`, plus verification of each iteration-1 concern.

## Iteration-1 concern disposition (all 11 checked against the revised text)

1. **lookup_token empty-branch ambiguity** — RESOLVED. `maybe_reprompt_stored_token`'s own guard clause ("returns 0 immediately … when `<token>` is empty") now carries the correctness burden instead of prose about "the lookup_token success branch," and AC8(b) exercises it directly.
2. **AC8 untestable / static-assertion escape hatch** — RESOLVED (adequately). The wrapper is now sourced-and-stubbed directly (AC8 a–d), which is genuinely mechanical; only the launch-site wiring itself falls back to a static grep, and the spec is honest about that being the residual.
3. **No pinned string for "print target repo"** — RESOLVED. `Repo: <owner/repo>` is now pinned verbatim as line 1 of `rotate_token` output.
4. **AC10 gameable presence check** — RESOLVED. Now requires two distinct phrases per file (`vibe pat` + `401` in README; `vibe pat` + `VIBE_PAT_CHECK=0` in MANUAL-TESTS).
5. **Help-text caveat untested** — RESOLVED. AC9 now requires the literal phrase `HOST shell`, which matches the file's own existing top-of-file convention (`vibe:27`, "All `vibe learn` subcommands run on the HOST shell…") — verified against source, not just self-consistent.
6. **ps-argv token exposure unaddressed** — RESOLVED via the `curl -K -` config-from-stdin mechanism. I built and ran a local HTTP echo server and confirmed empirically that `printf 'header = "Authorization: Bearer TOKEN"\n' | curl -s -o /dev/null -w '%{http_code}' -K - URL` delivers the header correctly and the token never appears in argv. The mechanism is real and works as pinned.
7. **AC1 stream unspecified** — RESOLVED. Both "too many args" and "invalid slug" are now explicitly pinned to stderr.
8. **AC7 vacuous for AC1** — RESOLVED. Rescoped to "every AC2/AC3/AC5/AC6 run" only.
9. **`vibe pat --help` unspecified** — RESOLVED. Explicitly special-cased before slug validation, mirroring other subcommands.
10. **AC9 "unmodified" contradicts Test-location** — RESOLVED. Reworded to "every pre-existing test function … unchanged, still passes."
11. **curl exit-code reconciliation** — RESOLVED. Explicit decision rule: capture `-w` output, ignore curl's own exit status, exact-`401`-string match only.

All eleven are substantively fixed, not reworded restatements of the same hole.

## Concerns (new, found in this iteration-2 audit)

1. **BLOCKING (AC3 / `rotate_token` contract).** The pinned flow — `read -rsp` then "Empty input → `aborted — token store unchanged`" — is described as a bare sequence, and a Generator writing it literally as described (`read -rsp "..." token` as a standalone statement, no guard) will ship a function that **fails AC3 on genuinely empty/closed stdin** because `vibe` runs under `set -euo pipefail` (`vibe:43`, unconditional, applies to the whole file including the subcommand-dispatch path). I reproduced this directly:
   ```
   set -euo pipefail
   read -rsp "P: " tok      # bare, unguarded
   echo "GOT=[$tok]"
   ```
   fed truly-empty stdin (`: | bash script.sh`, or Python `subprocess.run(..., stdin=subprocess.DEVNULL)`): the script prints nothing past the read and exits 1 **without ever reaching the `echo`/message logic** — `read` itself returns nonzero on immediate EOF, and as a bare statement that trips `errexit` before the intended `if [ -z "$token" ]; then echo "aborted…" ; exit 1; fi` branch ever runs. The eventual exit code (1) coincidentally matches what AC3 wants, but **the pinned stderr message is never printed**, which is exactly what AC3 checks for.
   This is not hypothetical: `smoke-test.py`'s own `run()` helper (line ~73) converts `input=""` to `input=None` (`input if input else None`), which — per the pre-existing precedent at line ~1866 (`vibe learn` capture, comment `# Empty input triggers EOF`) — reliably produces exactly this immediate-EOF condition in this test environment (I reproduced the identical effect with `stdin=subprocess.DEVNULL`). A haiku Tester writing AC3 the same way every other "empty input" test in this file is written (`input=""`) will hit this landmine.
   The codebase already has the correct fix pattern in the same file: `_learning_capture`'s prompt at `vibe:1438` uses `if ! IFS= read -r confirm; then … cancelled …; fi` — i.e. the read is inside a negated conditional, which is errexit-safe. The spec should pin the same idiom for `rotate_token` (or explicitly state "the `read` must be guarded so EOF cannot trip `set -e` before the abort message prints — see `_learning_capture` for the established pattern"), and AC3 should say what stdin shape the test uses (0 bytes / EOF vs. a lone newline) since they exercise genuinely different code paths under `errexit`.

2. **BLOCKING (AC5, testability).** Same root cause, different function: AC5 requires `stored_token_rejected` to return 1 for three of its four shim cases (`200`, `404`, `000`) when "sourced directly" and invoked by the Tester. Because the sourced file carries the same `set -euo pipefail`, a bare invocation like `stored_token_rejected owner/repo "$TOK"; echo "RC=[$?]"` — the natural way to write "call it, check the return code," and the exact literal pattern already used **elsewhere in this same file** for functions expected to return nonzero (e.g. `test_task017_c2_lock_release_wrong_project_refused_intact`, `smoke-test.py:7652`) — will abort the sourced bash snippet before the `echo "RC=[$?]"` runs, for any case where `stored_token_rejected` correctly returns 1. I reproduced this directly (`f() { return 1; }; f; echo "RC=[$?]"` under `set -e` never reaches the echo). Those existing precedent tests all wrap the bare call in `set +e; …; set -e` — but that convention lives in the task_017 tests, not in `test_token_helpers` (the convention the spec's "Test location" section actually points Tester at), so a haiku Tester following only the referenced precedent has no signal it's needed here. Pin it explicitly: either require the AC5/AC6 test snippets to bracket bare boolean-function calls with `set +e`/`set -e` (name the idiom, point at the task_017 c2 lock tests as precedent), or require the test to use `if stored_token_rejected …; then … else … fi` instead of capturing `$?` after a bare call.

3. **Minor (AC4, stdin hygiene).** AC4's "no arg… prints `Repo: <slug>`" doesn't say what stdin the harness supplies. If run without closing/pre-seeding stdin in an environment where the parent's stdin is a live, non-EOF pipe (unlike this sandbox), `rotate_token` would block on the subsequent `read -rsp` prompt rather than return, and a test that only wants to check the first output line would hang instead of completing. Given concern 1's fix will (correctly) make the read's behavior on EOF well-defined, this is now low-risk in practice, but the AC should still say explicitly that the test feeds closed/empty stdin (or is expected to send SIGTERM/read only partial output) so Tester doesn't leave it to chance.

4. **Minor (contract, defensive completeness).** `maybe_reprompt_stored_token`'s own return code is never pinned (only its side effects are). In every natural implementation I traced (`if stored_token_rejected …; then …; fi` with no `else`, or `stored_token_rejected … || return 0` guard-clause style), the function happens to return 0 on the "do nothing" path, which is what keeps the unguarded launch-path call site (`maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"`, inserted as a bare statement per the contract) safe under `set -e`. That safety is incidental, not contractual. One sentence pinning "`maybe_reprompt_stored_token` always returns 0, regardless of branch taken" would remove the remaining chance a Generator writes a variant (e.g. propagating `stored_token_rejected`'s own exit code via `return $?`) that turns every ordinary launch with a still-valid stored PAT into a hard launch failure.

5. **Minor (contract bullet on curl config line, edge case).** The `header = "Authorization: Bearer <token>"` line written into curl's `-K -` config is unescaped with respect to embedded `"` or `\` in the token. Not exploitable given GitHub PAT charset and the fixed fixture value used throughout testing, but worth one clause acknowledging the constraint (token must not contain `"`) rather than leaving it silently assumed.

## Verdict

revise
