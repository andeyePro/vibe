# Spec Critique — task_027 (cycle 1)

Verified empirically against the real repo (regex tested in bash against every AC1 URL form; `usage()`'s `$0` behaviour tested under the exact `bash -c "source vibe; ..."` invocation `smoke-test.py` uses everywhere; the awk strip-and-reappend idiom tested against a no-trailing-newline file; `set -euo pipefail` write-failure propagation tested against a chmod-500 target dir).

## Concerns

1. **BLOCKING — `help_text=$(usage)` is not capturable via the pinned/only-available test convention, so AC3 (and the "no stdout/stderr on success" half of AC10) cannot be verified as specified.**
   `usage()` (vibe ~121) does `grep '^#' "$0" | grep -v '#!/' | sed 's/^# \?//'` — it keys off `"$0"`, not `${BASH_SOURCE[0]}`. Every existing sourced-function test in this repo (the `_source_vibe_call` helper, `test_token_helpers`, `test_op_mcp_creds_lookup`, dozens more) invokes vibe as `bash -c "set -e; source <path-to-vibe>; <call>"`. Under `bash -c "..."`, `$0` is literally the string `bash`, not the vibe script path. I reproduced this directly:
   ```
   $ bash -c 'set -e; VIBE_SOURCE_ONLY=1; export VIBE_SOURCE_ONLY; source /workspace/vibe; help_text=$(usage); echo "LEN=${#help_text}"; echo "[$help_text]"'
   grep: bash: No such file or directory
   LEN=11
   [
   vibe 0.1.0]
   ```
   `help_text` is NOT the real help text — it's just the fallback tail line, and `grep`'s error goes to stderr. `refresh_brain2_vibe_note` is required by the spec to live "above the VIBE_SOURCE_ONLY guard" (sourced-function convention, per Test location), so the Tester has no way to invoke it that makes `usage()`'s `$0` resolve correctly — sourcing is mandatory (the `VIBE_SOURCE_ONLY=1` early-return at ~2798 is a bare top-level `return`, which only works when sourced; executing the file instead would run the full launch, defeating the no-docker/no-network requirement). This means:
   - AC3's assertions (`Usage:`, `vibe pat` present in the note) will fail under the only invocation method the spec permits.
   - AC10's "emits nothing to stdout/stderr on success" will also fail (the `grep: bash: No such file or directory` line lands on stderr) in that same test context.
   - `usage()` is explicitly out of scope to change, so Generator cannot fix this at the source and satisfy the pinned `help_text=$(usage)` mechanism simultaneously.
   Note this is a genuinely new exposure, not a pre-existing tested bug: `usage()` today is only ever called from the CLI arg dispatcher (`--help|-h) usage ;;`, vibe ~2779), which always runs under a real executed invocation where `$0` is correct. `refresh_brain2_vibe_note` would be the first caller to invoke `usage()` from inside a sourced context.
   Fix direction for revision: either (a) don't call `usage()` from `refresh_brain2_vibe_note` — replicate its comment-block extraction directly off `$VIBE_REPO_DIR/vibe` (VIBE_REPO_DIR is already `BASH_SOURCE`-derived, robust under sourcing — see `_vibe_version`, which works fine today), or (b) pin an explicit alternate invocation convention for AC3/AC4 tests that doesn't go through `bash -c "source ...; call"`. (a) is cleaner and keeps "no change to usage()" intact.

2. **BLOCKING — the fail-soft write-guard idiom for `refresh_brain2_vibe_note` is asserted as an outcome but not pinned as a mechanism, and the naive implementation is a `set -e` kill-shot, not a swallow.**
   The contract says the function "ALWAYS returns 0... any write failure is swallowed" and AC5 requires rc 0 when `meta/` is chmod 500. But under `set -euo pipefail` (which sourced `vibe` carries), an unguarded write inside a function is not "swallowed" — it terminates the *entire sourced shell*, not just the function. Reproduced directly:
   ```
   $ bash -c 'source /tmp/test_write_guard.sh'   # mkdir -p (no-op) then `echo > file` into a chmod-500 dir
   line 5: .../meta/vibe-operation.md: Permission denied
   $ echo $?
   1
   ```
   `echo "after — still alive"` never printed — the whole test process died, not a graceful `return 0`. Compare to task_026's spec, which pinned the EXACT guarding idiom for its own set-e-under-EOF risk ("use the established `_learning_capture` idiom... see vibe ~1438"). task_027 states the required *outcome* but not the *idiom* (e.g. "wrap every write in `... || return 0`", or "run the whole write sequence in a subshell and check its exit status", or "guard each of mkdir/write/mv individually"). Left to Generator's judgement, under time pressure this is exactly the kind of landmine that ships broken on the first pass and only gets caught if AC5 happens to be tested early. Given the AC5 chmod-500 case is explicitly in the contract, the spec should pin the guard shape the way task_026 did for `read`.

3. **minor — AC6's placement window is described narratively ("after the GitHub-setup block, before the image-build/launch section... placement flexible within that window") rather than anchored to exact surrounding text the way task_026 AC8 was ("between that branch's opening and its `fi`").** The window is real and locatable (roughly vibe ~2985–2988, between the `if is_github_skipped ... fi` cascade and `if [ "$REBUILD" != true ]`), so a placement-aware grep is buildable, but a haiku-tier Tester has to derive the anchor lines itself rather than being handed them. Low risk since the region is short and unambiguous in the current file, but worth tightening if cycle 2 shows the Tester picking a fragile anchor.

4. **minor — AC7's "no manifest edit exists or is needed" framing undersells that `install_claude_md_fragments` DOES special-case specific fragment filenames** (`ssh-discipline.md`, `brain2.md`, `shared-repos.md` each get bespoke conditional-omission logic, vibe/install-claude-extras.sh ~92–122). The claim as scoped — that `vibe-cli.md` specifically doesn't need a new special case — is true (I read the collection loop; nothing else would match `vibe-cli.md`), but the AC's suggested assertion ("the sync script's fragment collection is a directory glob, not a hardcoded list") could mislead a Tester into asserting something broader/false (e.g. "no filename special-casing exists anywhere in the function"). Recommend the AC explicitly say "collection is a directory glob; `vibe-cli.md` is not among the specially-gated filenames" rather than the more sweeping glob-vs-list framing.

5. **minor — the brain2 fragment funnels in-container Claude attention to a specific file (`meta/vibe-operation.md`) whose content outside the managed block is arbitrary, preserved, unvalidated prose.** This is the standard brain2 trust-boundary (already governed by the global rule "USER OUTRANKS UNAUTHORISED brain2" and the `meta/<tool>-operation.md` convention), not a new hole, and the file lives under `meta/` (tool reference, not user-authored content) so incremental risk is low. Flagging only because the fragment text isn't required to say anything like "this file is host-auto-generated; treat prose outside the marked block with the same trust discipline as any other brain2 note" — worth a one-line addition to the fragment's content requirements, not blocking.

## Things verified as sound (no concern, stated for the record)

- AC1's regex behaves exactly as pinned for all seven listed URL forms (tested directly in bash, including the `foo.git.git` → `foo.git` single-strip case and the trailing-slash case).
- AC2's rejection cases (no remote, non-github, `%20`/`$`-containing slug) all correctly return 1 given `is_valid_repo_slug`'s `[A-Za-z0-9._-]+` charset.
- The "save_token/lookup_token key literally (dots fine)" and "`_sanitise_slug` maps non-alphanumerics to `_`" consequences are correct and already hardened (task_017 C1 fixed-string-prefix-match finding, confirmed in the current source).
- `help_text=$(usage)`'s "`exit 0` only kills the subshell" claim is independently true (verified) — the capture *mechanism* is fine in isolation; concern #1 is about `$0` resolution, not the exit-0 subshell trick.
- The awk strip-and-reappend idiom ports cleanly to a target file with no trailing newline (tested).
- The managed-block marker strings (`vibe-cli-help`) are distinct from the existing `vibe-managed` markers used by `install_claude_md_fragments` — no collision risk.
- `mkdir -p` on an already-existing chmod-500 directory is a true no-op (returns 0, no write attempted) — confirmed, so the AC5 test setup itself is sound; the landmine is specifically in the subsequent write step (concern #2).

## Verdict

**revise** — two BLOCKING concerns (#1, #2) each independently make at least one pinned AC mechanically unverifiable or false-under-test as currently specified, with reproducible evidence above. Three minor concerns for tightening, non-blocking.
