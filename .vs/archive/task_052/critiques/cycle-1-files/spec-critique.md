# Spec Critic — task_052 delegate usage ledger + `/budget` split

## Concerns

1. **AC1 — BLOCKING (redundant/contradicts existing invariant).**
   `.vibe/` is ALREADY blanket-ignored in the repo's `.gitignore` and in
   `install-claude-extras.sh`'s `ensure_project_gitignore` managed block
   (confirmed present in both today). Requiring an explicit
   `.vibe/delegate-usage.jsonl` entry is either a no-op (if AC6's test
   matches the `.vibe/` prefix, nothing new verified) or a genuinely
   redundant literal line. State it's already covered, or justify and
   test for the redundant line specifically.

2. **AC1 — BLOCKING (path resolution ambiguous vs. actual code).**
   "the root from `repoRoot()`" doesn't say which directory feeds it.
   Every function here reuses `cwd` for the per-call SCRATCH dir
   (`mkdtempSync`) — `main()` calls `codex(payload, review, scratch)`;
   `repoRoot(scratch)` would always fail. Neither `ask`/`review` (no
   repo-root concept today) nor `role` (`--cwd` is *a* work tree, not
   necessarily its top) says what real directory to resolve from.

3. **AC1 — BLOCKING (fail-closed regression, untested).** `repoRoot()`
   today throws when there's no work tree. AC1 requires non-astra `ask`
   to keep succeeding outside one, but never says to use a non-throwing
   lookup — a naive build turns every currently-OK "ask outside a repo"
   call into a hard failure. AC6 tests neither of AC1's carved-out
   branches.

4. **AC2/AC6 — BLOCKING (role: billing/served_models unspecified).**
   The schema requires `"billing"` unconditionally and `"served_models"`
   for every op, but `codexRole()`/`claudeRole()` return neither today
   (`claudeRole` even discards the `servedModels` `claudeReply()`
   already computes). AC6's only role test is "records role" — it never
   pins a billing/served_models value, so `"billing":null` passes every
   named test while violating AC2's non-nullable shape.

5. **AC2 — BLOCKING (failure path unachievable, "ran" ambiguous).**
   "Before stdout is written" describes only the success path; `fail()`
   throws a bare `Error` caught by `main()`'s handler — no channel
   carries partial usage from before the throw (`codexEvents()` builds a
   valid total, then a later check can discard it), and AC6 never pins
   `usage` non-null when available, so `usage:null` always passes. Also,
   `codexVersionOk()`/`codexReady()` shell out to `codex --version`/
   `login status` *before* the accounted-for `codex exec` — whether
   their failure is "vendor ran" or a refusal is untested either way.

6. **MINOR (three small gaps).** AC3 checks the ledger FILE for
   symlink-ness but not the `.vibe` dir itself, unlike `slots()` in this
   file. AC1/AC6 say nothing about creating `.vibe/` when absent in a
   fresh work tree (`_delegate_fixture` always pre-creates it). AC2/AC6's
   test only greps for the payload literal and `thread_id`/`session_id`,
   not an exact key-set match (cf. this file's `exact()` helper), so a
   stray field (e.g. review `findings[].message`) would slip past.

## Verdict

`revise` — concerns 1-5 are concrete gaps between the ACs and the code's
actual shape, several invisible to AC6's own tests: fully green can
still miss the ledger's accounting/privacy purpose on failed calls.
