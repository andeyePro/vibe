# task_026 cycle 2 — Generator report

Fixes exactly the three security-review findings against cycle 1's
implementation. No other lines touched. `smoke-test.py` `test_task026_*`
functions were read-only (for convention) and are unchanged.

## Finding 1 (HIGH) — fail-open on `setup_token` EOF

**File:** `vibe`, `maybe_reprompt_stored_token` (~line 494–508).

**Change:** the rejection branch now calls `setup_token "$repo" || true`
instead of a bare `setup_token "$repo"`, with a comment explaining that
`||` suppresses errexit for the whole command so `setup_token`'s own
unguarded `read` hitting EOF (closed/non-interactive stdin) degrades to its
existing "No token entered — launching without GitHub auth" branch instead
of killing the launcher under `set -euo pipefail`.

**Empirical evidence** (`.vs/cycle-2/scratch-tests/finding1_red.sh` /
`finding1_failopen.sh`):

- RED (reconstructed cycle-1 code, `vibe-pre-fix1.sh` — same file with only
  the `|| true` suffix reverted): sourced with `stored_token_rejected`
  stubbed to return 0 (rejected), ran
  `maybe_reprompt_stored_token owner/repo ghp_task026_fixture_token < /dev/null`
  under `set -euo pipefail` — script aborted at the `read` inside
  `setup_token`, exit 1, `SCRIPT_ALIVE_AFTER_CALL` never printed. Confirmed
  the bug reproduces exactly as described.
- GREEN (current `vibe`): identical repro, same stub, same closed stdin,
  same `set -euo pipefail`. Output tail:
  ```
  /workspace/vibe: line 395: open: command not found
    No token entered — launching without GitHub auth.
  SURVIVED: maybe_reprompt_stored_token returned rc=0
  SCRIPT_ALIVE_AFTER_CALL
  PASS
  exit=0
  ```
  (The `open: command not found` line is expected/harmless — no browser
  binary in this container; it's swallowed by the same errexit suppression
  and doesn't stop `setup_token` reaching its own EOF-handling `read`.)

## Finding 2 (MEDIUM) — slug trust boundary

**File:** `vibe`.

**Change (a):** `pat_handle_subcommand`'s no-arg branch (~line 532–546) now
validates the `detect_github_repo` result with `is_valid_repo_slug` before
calling `rotate_token`; on failure prints
`vibe pat: detected remote slug '<repo>' is not a valid owner/repo` to
stderr and exits 1.

**Change (b):** `maybe_reprompt_stored_token`'s early-return guard
(~line 490) now also fails open when the repo isn't a valid slug:
`if [ "${VIBE_PAT_CHECK:-}" = "0" ] || [ -z "$token" ] || ! is_valid_repo_slug "$repo"; then return 0; fi`
— no probe.

**Empirical evidence** (`.vs/cycle-2/scratch-tests/finding2_slug.sh`, exit
0, all PASS):

- Built a git checkout with `origin` set to
  `https://github.com/owner/re+po.git` — `+` is accepted by
  `detect_github_repo`'s `[^/]+/[^/.]+` regex but rejected by
  `is_valid_repo_slug`'s `[A-Za-z0-9._-]+` charset (sanity-checked directly:
  `is_valid_repo_slug 'owner/re+po'` returns false).
  - `pat_handle_subcommand pat < /dev/null` in that checkout: exit 1,
    stderr = `vibe pat: detected remote slug 'owner/re+po' is not a valid owner/repo`.
  - `maybe_reprompt_stored_token "owner/re+po" ghp_task026_fixture_token`
    with logging stubs: `stored_token_rejected` and `setup_token` both
    uncalled (`PROBE=0`, `SETUP=0`), wrapper still returns 0 (`RC=0`).
- Control: the same wrapper called with a valid slug (`owner/repo`) still
  probes normally (`PROBE=1`) — confirms the new guard isn't over-broad and
  doesn't regress the AC8 cases.

## Finding 3 (LOW) — token charset hardening in `rotate_token`

**File:** `vibe`, `rotate_token` (~line 441–453), inserted between the
existing empty-input abort and `save_token`.

**Change:** after a non-empty read, if the token contains a double-quote,
backslash, any `[[:space:]]`, or any `[[:cntrl:]]` character, prints
`vibe pat: token contains characters no GitHub PAT uses — not saved` to
stderr and exits 1, store untouched. The pre-existing empty-input abort
(`aborted — token store unchanged`) is unmodified and still the first
check.

**Empirical evidence** (`.vs/cycle-2/scratch-tests/finding3_charset.sh`,
exit 0, all PASS):

- Control (clean `ghp_task026_fixture_token`): exit 0, store updated —
  proves the new check doesn't false-positive on a real token.
- Double-quote, backslash, embedded space, embedded tab, and an embedded
  `\x01` control byte: each — exit 1, pinned refusal string on stderr,
  token store byte-identical to before the call, and the bad token value
  itself absent from captured output.
- Existing empty-input abort (closed stdin): unchanged — exit 1, original
  `aborted — token store unchanged` message, store untouched.

## Verification gates

- `python3 code-check.py` — `✓ shellcheck clean across 19 files`.
- `python3 smoke-test.py` (full suite) — exit 0, `✓ smoke tests passed`,
  1804 individual `✓` assertions, zero `✗`/FAIL/Traceback lines. All
  `test_task026_*` functions (frozen, unedited) pass, including AC8's
  placement-aware static check and the AC9 regression-gate/code-check
  clause. Full log: `.vs/cycle-2/scratch-tests/full-smoke-output.log`.

## Conflicts

None. No frozen `test_task026_*` function needed edits or conflicted with
any of the three fixes.

## Files changed this cycle (on top of cycle 1's working tree)

- `vibe` — the three fixes above.
- `.vs/tasks.json` — `task_026.last_modified` bumped (statuses unchanged).
- `.vs/cycle-2/diff.patch` — full working-tree diff (`git diff`, includes
  cycle 1's uncommitted feature plus this cycle's fixes; both were already
  uncommitted before this dispatch).
- `.vs/cycle-2/scratch-tests/*` — red/green scratch harnesses for all three
  findings (not part of the shipped diff).
