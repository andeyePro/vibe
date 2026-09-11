# task_044 — Generator report (cycle 1)

## Files changed

- `devcontainer/vibe-delegate.mjs`
- `vibe` (launcher)
- `devcontainer/commands/ask.md`
- `devcontainer/commands/review.md`
- `README.md`
- `MANUAL-TESTS.md`
- `.vs/tasks.json` (task_044 `implementation_status` → `complete`)

No file under `smoke/` was touched. No edit to `guard-bash.sh`, `guard-fs.sh`,
`init-firewall.sh`, or `settings.local.json`.

## AC coverage

- **AC1/AC2/AC3** (`devcontainer/vibe-delegate.mjs`, `main()`): the existing
  `operation === 'review' && !slots(...).codex` gate is widened to
  `(operation === 'review' || model === 'astra') && !slots(process.cwd()).codex`,
  evaluated before the payload is read from stdin and before any scratch dir
  or vendor process exists. The failure message is now
  `codex disabled by .vibe/review-slots (codex=off)`, naming both
  `.vibe/review-slots` and `codex=off` as required. Because `slots()` itself
  throws (via `fail()`) for a tracked/symlinked file, a duplicate/unknown
  entry, an unknown value, or a non-git cwd, every one of those failure modes
  already propagates to the top-level `catch` and exits non-zero with zero
  vendor calls — extending the astra gate to consult `slots()` inherits that
  fail-closed behaviour for free. `ask haiku|sonnet|opus|fable` never call
  `slots()`, so they are unaffected both inside and outside a work tree.
- **AC4** (`claude()`): argv changed from `--permission-mode dontAsk` to
  `--permission-mode plan --permission-prompts none`; subscription
  `--settings` value changed from
  `{"forceLoginMethod":"claudeai","disableAllHooks":true}` to
  `{"forceLoginMethod":"claudeai"}` (comment added noting `--safe-mode`
  already disables hooks). Billed-mode path unchanged except for inheriting
  the same flag swap. Verified against the exact golden vector in scratch
  tests (see below).
- **AC5** (`vibe`): new `_codex_dir_mode_warning <dir>` defined immediately
  after `_codex_desired_source` (line ~1653), above the `VIBE_SOURCE_ONLY`
  guard (line 3734+11≈3746 after insertion). Reads the mode via
  `stat -c %a || stat -f %Lp` (the file's existing Linux/Darwin `stat`
  fallback idiom), takes the last three characters of the mode string, and
  warns to stderr (containing `chmod 700` and the path) iff the group+other
  two digits aren't both `0`. Never touches the mode; a non-existent path or
  unreadable stat returns silently. `_codex_desired_source` itself is
  byte-for-byte unchanged. Wired one line after the `codex   :` banner echo,
  inside the same `if [ -n "$_codex_banner" ]` block (line ~4360, i.e. the
  banner block that runs below the `VIBE_SOURCE_ONLY` guard, as required).
- **AC6** (docs): `ask.md` replaced "`/ask` is explicit delegation and does
  not consult `.vibe/review-slots`" with a sentence stating `codex=off`
  refuses `/ask astra` too (contains `codex=off`, `/ask astra` and `refus` in
  one sentence). `review.md` removed "`/ask` is independent of this policy"
  and added a sentence naming `codex=off` as the OpenAI-egress switch and
  `.vibe-allow-codex` as the credential-mount switch (kept the file at
  exactly 850 words — the existing AC1 word-count check caps it there — by
  trimming two other redundant phrases elsewhere in the same file; verified
  no other pinned substring in `smoke/checks_13_spec_first.py` broke).
  `README.md`'s Codex section gained the same two-switch sentence (contains
  `egress switch` and `mount switch` literally) plus a sentence describing
  the launch-header `chmod 700` warning (contains `chmod 700`).
  `MANUAL-TESTS.md` Test 54 step 8 no longer says "explicitly `/ask astra
  ...` still works"; it now reads "`codex=off` refuses `/ask astra` as well,
  not only the `/review` codex slot" and notes `/ask opus|sonnet|haiku|fable`
  are unaffected. Step 4 gained one sentence re-confirming a real `claude -p`
  one-shot returns `type: result`, `subtype: success` under
  `--permission-mode plan --permission-prompts none`.
- **AC8**: see Commands run below — clean/green except the one expected
  failure.

## AC7 (owned by the Tester, not touched here)

`smoke/checks_17_delegation.py`'s `test_delegate_review_policy` still
contains its original assertion:
```
r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
check("[delegate] explicit ask independent of review policy", r.returncode == 0 and len(calls) == 3, r.stderr)
```
This now fails by design: with `.vibe/review-slots` set to `codex=off` (set
two lines earlier in the same test for the `review codex` check), `ask astra`
now also refuses. Per AC7 this assertion is the Tester's to replace with the
AC1 assertion; no `smoke/` file was edited by the Generator.

## Commands run

- `python3 code-check.py` — clean, "shellcheck clean across 20 files".
- `python3 smoke-test.py < /dev/null` (foreground) — **3417 passed, 1 failed**:
  the single expected failure is
  `[delegate] explicit ask independent of review policy`
  (`vibe-delegate: codex disabled by .vibe/review-slots (codex=off)`).
  Every other check, including all other delegate checks and the doc/spec
  sentinel checks in `checks_13_spec_first.py`, passed.

## Scratch TDD (`.vs/cycle-1/scratch-tests/`, gitignored)

- `test_delegate_astra_policy.py` — copied the `_delegate_fixture`/
  `_delegate_call` pattern from `smoke/checks_17_delegation.py` verbatim
  (no import of the smoke module). Covers AC1-AC4 directly: RED before the
  `vibe-delegate.mjs` edit (11 failures), GREEN after (18/18 passed).
- `test_codex_dir_mode_warning.sh` — sources `vibe` with `VIBE_SOURCE_ONLY=1`
  and exercises `_codex_dir_mode_warning` against real directories at modes
  0700/0755/0750/0705/1755/4700 plus a missing path, and confirms the mode is
  never changed. RED before the launcher edit (function not found), GREEN
  after (11/11 passed). Note for reuse: sourcing `vibe` leaks its top-level
  `set -euo pipefail` into the sourcing shell; the script resets to
  `set +e +u +o pipefail` immediately after the `source` line.

## Anything not done / blocked

Nothing blocked. One deliberate trade-off: `review.md`'s two-switch sentence
is worded more tersely than README's (no literal "egress switch"/"mount
switch" phrase pinning is required there per the spec's Pinned-substrings
list — only README needs those exact words) to stay within the file's
existing 850-word cap enforced by `smoke/checks_13_spec_first.py`; the
underlying two-switch content (which file is the OpenAI-egress switch, which
is the credential-mount switch) is present in `review.md` in substance.
