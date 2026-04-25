# task_008 — vibe: drain clipboard scratch on exit

**Revised after Spec Critic iteration 1.** 3 BLOCKING + 4 MEDIUM concerns addressed inline.

Key changes from draft:
- **mtime comparison switched to string `!=`** (resolves BLOCKING #1 — `stat -f %m` can return a float on some BSDs, integer `[ -gt ]` would abort the trap under `set -euo pipefail`). Watcher already uses this idiom.
- **Drain step error isolation made explicit** (resolves BLOCKING #2 — `|| true` on the drain branch so a `pbcopy` failure cannot skip the kill).
- **`WATCHER_SEED_MTIME` pre-declaration prohibited outside the Darwin block** (resolves BLOCKING #4 — closes the nounset trap for defensive Generators).
- **`CLIP` variable name locked** (resolves MEDIUM #3).
- **Seed must come from a `stat` call, not a literal** (resolves MEDIUM #5).
- **AC14 grep pattern tightened** to require the mtime guard and `pbcopy <` to appear on consecutive non-blank lines inside the trap (resolves MEDIUM #6).
- **Kill invocation locked exactly** to `kill "$WATCHER_PID" 2>/dev/null || true` (resolves MEDIUM #7).
- **Concurrent vibe instances explicitly out-of-scope** (resolves MEDIUM #8).
- LOW concerns 9–11 folded inline as rationale notes.

---

## Task summary

Fix a race in `/workspace/vibe` where the EXIT trap kills the host-side `vibe-copy-watcher.sh` before it has a chance to `pbcopy` a final write to `/workspace/.vibe/copy-latest.txt`. Symptom (reported 2026-04-25): a user runs `/expaste`, types `/exit`, and finds the Mac clipboard unchanged from before the session — the actual command vibe was supposed to deliver never made it onto the clipboard.

The watcher's commit d38fdcc seeded its `last` mtime to the existing file's mtime so a stale `copy-latest.txt` from a prior session would not clobber the clipboard on startup. That fix is correct and stays. The new race it exposes is at the OTHER end: a write that happens shortly before `/exit` is dropped because the trap fires before the watcher's next poll (0.5s loop without `fswatch`) or before the in-flight `cp + pbcopy` chain completes.

The fix is to extend the existing EXIT trap so that, before killing the watcher, the launcher synchronously runs `pbcopy < "$CLIP"` — but only when the file's mtime has changed since the seed captured at watcher launch. That guarantees the final state of the scratch file lands on the clipboard regardless of whether the polling watcher saw it, and it does NOT clobber the host clipboard with a stale file from a prior session.

**Why direct read, not `cp` to TMP first.** The watcher uses `cp "$CLIP" "$TMP" && pbcopy < "$TMP"` to avoid a partial-read race against a concurrent in-container writer. At the point our drain runs, `devcontainer exec` has already returned — the container process and its claude session are gone, so no concurrent writer exists. Reading `"$CLIP"` directly is safe.

**Why string `!=`, not arithmetic `-gt`.** `stat -f %m` returns sub-second-precision floats on some macOS versions; `[ "$cur" -gt "$WATCHER_SEED_MTIME" ]` would abort the trap mid-body under `set -euo pipefail`. The watcher uses `[ "$cur" != "$last" ]` for the same reason; we mirror that. The downside (a clock step backward could trigger a redundant pbcopy of unchanged content) is harmless: pbcopying the same bytes twice is a no-op the user will not perceive.

## Acceptance criteria

1. **Seed-variable name.** `/workspace/vibe` introduces a shell variable named exactly `WATCHER_SEED_MTIME`, assigned from a `stat` invocation (NOT a hard-coded literal). Grep target: a line matching `WATCHER_SEED_MTIME=$(stat`.

2. **Scratch-path variable name.** `/workspace/vibe` introduces a shell variable named exactly `CLIP`, holding the literal string `"$WORKSPACE/.vibe/copy-latest.txt"` (or equivalent path concat). Grep target: a line matching `CLIP="$WORKSPACE/.vibe/copy-latest.txt"`.

3. **Block scoping.** Both `WATCHER_SEED_MTIME` and `CLIP` are assigned ONLY inside the existing Darwin+pbcopy `if` block (`if [[ "$(uname)" == "Darwin" ]] && command -v pbcopy …; then … fi`, currently at vibe:1111-1117). They MUST NOT be pre-declared, defaulted, or referenced outside this block. Rationale: the launcher runs `set -euo pipefail`; an out-of-block reference on Linux would either hit `nounset` or run a `pbcopy` that does not exist.

4. **Seed-capture timing.** Within the Darwin+pbcopy block, `CLIP` is assigned BEFORE `WATCHER_SEED_MTIME`, and `WATCHER_SEED_MTIME` is assigned AFTER `mkdir -p "$WORKSPACE/.vibe"` and BEFORE the watcher is backgrounded. The seed therefore reflects the file state at the moment the watcher starts polling.

5. **Seed-capture portability.** The mtime read uses the same triple-fallback pattern `vibe-copy-watcher.sh` uses for its own `last` seed: `stat -f %m` (BSD/macOS) `||` `stat -c %Y` (GNU/Linux) `||` `echo 0`, all with `2>/dev/null`. Concrete form: `WATCHER_SEED_MTIME=$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)`.

6. **EXIT trap drains before kill.** The `trap '...' EXIT` set inside the Darwin+pbcopy block has a body of the exact shape:
   ```
   if [ -s "$CLIP" ] && [ "$(stat -f %m "$CLIP" 2>/dev/null || stat -c %Y "$CLIP" 2>/dev/null || echo 0)" != "$WATCHER_SEED_MTIME" ]; then pbcopy < "$CLIP" 2>/dev/null || true; fi; kill "$WATCHER_PID" 2>/dev/null || true
   ```
   Equivalent re-wrappings are allowed (e.g. splitting into multiple `;`-separated statements, factoring the mtime read into a helper var) provided every other AC still holds. The `kill` line MUST appear AFTER the `if … fi`. **The trap body MUST be single-quoted** (so `$(stat …)` and `$WATCHER_SEED_MTIME` expand at trap-fire time, not at trap-registration time). **The existing single-statement trap on vibe:1116 is REPLACED** — there must be exactly ONE `trap '…' EXIT` registration in this block; do not append a second one.

7. **String inequality, not arithmetic.** The mtime comparison MUST use the string operator `!=` inside `[ … ]` or `[[ … ]]`, NOT `-gt`/`-lt`/`-ne`. Rationale: avoid arithmetic abort under `set -euo pipefail` if `stat` returns a float.

8. **Drain failure-safe.** The drain branch (the `pbcopy < "$CLIP"` invocation) ends with `2>/dev/null || true` (or is wrapped in a subshell that has the same swallowing effect). The `kill "$WATCHER_PID" 2>/dev/null || true` step MUST run regardless of any failure inside the drain branch.

9. **Drain is gated on file existence and non-emptiness.** The drain only runs when `[ -s "$CLIP" ]` is true (file exists and has size > 0). A missing or empty `copy-latest.txt` is a silent no-op.

10. **Drain is gated on mtime change.** The drain only runs when the file's current mtime is NOT equal to `"$WATCHER_SEED_MTIME"`. If the file was not written during this vibe session, the host clipboard is NOT touched.

11. **Direct read, not pipe.** The drain calls `pbcopy < "$CLIP"` (input redirection). It does NOT use `cat "$CLIP" | pbcopy` and does NOT cp through a TMP file (rationale documented in task summary).

12. **Kill invocation locked.** The trap body ends with EXACTLY this token sequence (whitespace flexible): `kill "$WATCHER_PID" 2>/dev/null || true`. NOT `kill -9 …`, NOT `pkill …`, NOT `wait`. The signal stays SIGTERM; the silencing-and-swallowing pattern stays identical.

13. **No new files.** The fix is implemented inline in `/workspace/vibe`. No new shell scripts, no helper functions in other files, no new directories, no new dependencies.

14. **Variable hygiene.** `$WATCHER_SEED_MTIME` and `$CLIP` are double-quoted at every reference. No new shellcheck warnings.

15. **No scope drift.** `vibe-copy-watcher.sh` is NOT modified. `/c` and `/expaste` skill bodies are NOT modified. The Dockerfile, `devcontainer.json`, `postStartCommand`, `init-firewall.sh`, `guard-bash.sh`, `settings.local.json`, `credential-helper.sh`, `setup-ssh.sh` are NOT touched.

16. **`code-check.py` passes.** `python3 code-check.py` exits 0.

17. **`smoke-test.py` passes; pre-existing test count unchanged or grows.** `python3 smoke-test.py` exits 0. The pre-existing total check count (today: see Evaluator's pre-change baseline) MUST NOT decrease.

18. **New smoke coverage — AC-locked greps.** `smoke-test.py` gains a new test function (suggested name `test_clipboard_drain_on_exit`) that performs the following file-read greps against `Path(VIBE).read_text()`:
    - **a.** Asserts that exactly one line matches the regex `^\s*CLIP="\$WORKSPACE/\.vibe/copy-latest\.txt"\s*$`.
    - **b.** Asserts that exactly one line matches the regex `^\s*WATCHER_SEED_MTIME=\$\(stat -f %m "\$CLIP"`.
    - **c.** Asserts that the source contains the substring `pbcopy < "$CLIP"`.
    - **d.** Asserts that the source contains the substring `kill "$WATCHER_PID" 2>/dev/null || true`.
    - **e.** Asserts that the substring matched by (b) appears at a smaller byte-offset than (c) (seed precedes drain).
    - **f.** Asserts that the substring matched by (c) appears at a smaller byte-offset than (d) (drain precedes kill).
    - **g.** Asserts that the substring `[ "$cur" -gt "$WATCHER_SEED_MTIME" ]` does NOT appear (negative test for the arithmetic-comparison loophole).
    - **h.** Asserts that the substring `WATCHER_SEED_MTIME=0` does NOT appear as a stand-alone literal (negative test for the hard-coded-seed loophole). Match the literal token only — `WATCHER_SEED_MTIME=$(stat …` containing the `… || echo 0` fallback is fine.
    Each assertion increments the existing smoke check counter by 1 (8 new checks).

19. **Idempotent and safe to re-run.** If a user runs `vibe` twice on the same workspace and never invokes `/c` or `/expaste` in either session, the drain step is a no-op in both (file mtime never advances past the seed) and the host clipboard is NOT touched. A grep confirming the mtime-change guard is present (AC10/AC18) covers this mechanically.

## Out of scope

- Refactoring `vibe-copy-watcher.sh`.
- Replacing the polling loop with a different IPC mechanism (e.g. socket, signal-based).
- Adding a `vibepaste` host helper command (separate TODO entry).
- Stop-hook auto-write of last fenced block (separate TODO entry).
- Any change to `/c` or `/expaste` skill bodies.
- Any change to Dockerfile, devcontainer.json, postStartCommand, firewall, hooks, or auth.
- Cross-platform support beyond what `vibe-copy-watcher.sh` already gates (Darwin + `VIBE_COPY_WATCHER_FORCE=1` testing override).
- **Concurrent vibe instances against the same workspace.** Two simultaneous vibe sessions on one workspace would both drain on exit and could publish each other's stale content. This is preserved-as-is — the bug existed before this fix and is not addressed here. (Arguably the scratch path should be PID-suffixed; that is a separate design conversation.)

## Test location

`/workspace/smoke-test.py` (host-side, no Docker, no network). New tests follow the existing pattern: a function named `test_<topic>` is defined, registered in the `if __name__ == "__main__":` test list, and increments the global check counter via the same helpers existing tests use. File-read greps via `Path(VIBE).read_text()` are the established pattern for source-level assertions; do NOT add a `VIBE_SOURCE_ONLY=1` runtime-source path for this test.

## Proposed budget

1 cycle. Mechanical, ≤15-line edit to a single block of `/workspace/vibe`; tests are 8 source-level grep / negative-grep / byte-offset assertions in `smoke-test.py`.
