# task_007 — WebSearch-before-refusing rule shipped to all vibe users

**Revised after Spec Critic iteration 1. 3 blocking concerns + 12 medium/low concerns addressed.**

Key changes from draft:
- **Dropped the `@import` indirection.** Concern #1 was correct: `@vibe-md/<file>` is unverified as a real Claude Code feature. Replaced with **inline prose**: install-claude-extras.sh reads the contents of `$SRC_ROOT/claude-md/*.md` and inlines the concatenated body directly into the managed block (mirrors the proven `write-env-hint.sh` pattern). No separate `vibe-md/` dest dir. No @-import. Simpler and verifiably-works.
- **Block position pinned.** Vibe-managed block goes at END of CLAUDE.md (write-env-hint owns the top; user content is in the middle; vibe-managed bookends the bottom). Two block managers, no spatial overlap.
- **Sort collation pinned** as `LC_ALL=C` (POSIX byte-order).
- **AC1 line floor raised to 50** + sequencing-sentinel grep added; t1 mechanically asserts both.
- **TODO.md line-number reference dropped** — identified by content string.
- **3 new tests** for previously-uncovered scenarios (write-env-hint coexistence, N→N-1 fragment removal, absent-source-with-pre-existing-block).

## Task summary

Bake two operational rules into vibe itself, so every vibe user inherits them on every container start without per-user setup. Today both rules live only in the current operator's personal feedback memory; the goal is to surface the same guidance to all users in a way Claude Code reads on every turn.

**Rule 1 (WebSearch-before-refusing):** when WebFetch fails (firewall, network, content-shape mismatch, 4xx/5xx, empty body), Claude must attempt WebSearch on the same domain or topic BEFORE telling the user the URL is unreachable, BEFORE pivoting to architecture/alternative discussion. Only after WebSearch also returns nothing useful should Claude surface "I can't reach this."

**Rule 2 (no SSH-out without explicit user OK):** SSH-out from a `bypassPermissions` vibe container extends blast radius from the container to the target host. Firewall permission to reach `.local`/LAN hosts is a network-layer allowance, not a behavioral approval. Claude must default to giving the user a command to run on their host shell, NOT running `ssh`/`scp`/`rsync` itself, unless the user explicitly authorises a specific SSH action in the current turn. Rationale captured in feedback memory `feedback_no_ssh_out_of_vibe.md`.

Both rules ship as separate `*.md` fragments in `devcontainer/claude-md/` so future operational rules can land via the same mechanism. Both are always-on behavioral rules — they must be in force from the first turn of every vibe session.

## Chosen shape (Planner decision)

**Inline-prose CLAUDE.md fragment, written into a managed block at the END of `~/.claude/CLAUDE.md` by install-claude-extras.sh on every container start.**

Concrete mechanism:
- **Source:** vibe ships a new dir `devcontainer/claude-md/` containing one or more `*.md` files. For this task the only fragment is `web-research.md` (the WebSearch rule prose, written as a Claude-facing instruction).
- **Image bake:** Dockerfile gains `COPY claude-md /usr/local/share/vibe/claude-md/` — parallel to the existing `agents/` and `commands/` staging.
- **Runtime sync:** `install-claude-extras.sh` extended with a third install path that reads the contents of every `*.md` file under `$SRC_ROOT/claude-md/` (sorted by filename in `LC_ALL=C` byte order) and inlines the concatenated bodies into a delimited managed block written to `$DEST_ROOT/CLAUDE.md`. No separate dest copy of the source files; the contents go directly into the block.
- **Block delimiters:** `<!-- >>> vibe-managed (auto, do not edit) >>>` (opening) and `<!-- <<< vibe-managed <<< -->` (closing). Distinct from write-env-hint.sh's delimiters (`<!-- BEGIN vibe env (managed) -->` / `<!-- END vibe env -->`).
- **Block position:** at the END of the file. Each fragment's body is preceded by a single comment line `<!-- vibe-md: <basename> -->` (so a human reading CLAUDE.md can see which fragment provides which content). Multiple fragments are joined by a blank line.
- **Coexistence:** write-env-hint.sh continues to manage its own block at the TOP of CLAUDE.md. install-claude-extras.sh leaves the write-env-hint block byte-identical. The two scripts never touch each other's delimiters.
- **User content** in the middle (anything not inside either managed block) is preserved verbatim. Whitespace cleanup mirrors write-env-hint.sh's pattern: leading/trailing blank lines collapsed; a single blank line separates user content from the closing-end managed block.

## Acceptance criteria

1. **WebSearch fragment exists with substantive content.** `devcontainer/claude-md/web-research.md` is a tracked file. Its body:
   - Contains the literal phrase `WebSearch` (grepable).
   - Contains the literal phrase `WebFetch` (grepable).
   - Contains a sequencing sentinel — at least one of the case-sensitive strings `BEFORE`, `before`, `first`, or `First` (grepable; signals temporal-order prose).
   - Is at least **50 non-blank lines** (counted by `len([line for line in content.splitlines() if line.strip()])`). Floor is mechanical, not a stub-shaped 20-blank-lines-pad-it.

1b. **SSH-discipline fragment exists with substantive content.** `devcontainer/claude-md/ssh-discipline.md` is a tracked file. Its body:
   - Contains the literal token `ssh` (grepable; the unix command name).
   - Contains the literal token `scp` (grepable; an SSH-family command — guarantees Generator covers the full family, not just ssh).
   - Contains a prohibition / default-disposition sentinel — at least one of the case-sensitive strings `Do not`, `Don't`, `don't`, `Avoid`, or `default to` (grepable; signals "don't do this by default" prose shape).
   - Is at least **50 non-blank lines** (same counting rule as AC1).
   - Content guidance for Generator (NOT additional ACs; informational): the rule should mirror feedback memory `feedback_no_ssh_out_of_vibe.md` — SSH-out from a `bypassPermissions` container extends blast radius from container to target host; firewall network-permission ≠ behavioral approval; Claude's default disposition is to give the user a command to run on their host shell rather than running `ssh`/`scp`/`rsync` itself; explicit per-turn user authorisation is the only override.

2. **Dockerfile stages the source.** `devcontainer/Dockerfile` contains exactly one line matching the canonical form `COPY claude-md /usr/local/share/vibe/claude-md/` (trailing slash on the destination — directory copy semantics, parallels existing agents/commands COPYs). Verified by literal-string grep + count.

3. **install-claude-extras.sh reads source fragments.** install-claude-extras.sh, on each run, enumerates `*.md` files under `$SRC_ROOT/claude-md/` (if directory exists) and uses POSIX byte-order sort by basename (`LC_ALL=C sort` semantics — equivalent to bash `printf '%s\n' "${arr[@]}" | LC_ALL=C sort`). Generator's choice of internal helper naming is unconstrained. **Generator MUST set `LC_ALL=C` explicitly** for the sort step (e.g. `LC_ALL=C sort` or `LC_ALL=C` exported around the sort) — the container's ambient locale is `LC_ALL=C.UTF-8`, which coincides with `C` for ASCII filenames but diverges for non-ASCII. Relying on the ambient locale is non-compliant even though all current fragment names are ASCII.

4. **Managed block at end of CLAUDE.md.** After install-claude-extras.sh runs with at least one `*.md` in `$SRC_ROOT/claude-md/`, `$DEST_ROOT/CLAUDE.md` contains a delimited block whose:
   - Opening line is exactly `<!-- >>> vibe-managed (auto, do not edit) >>>`.
   - Closing line is exactly `<!-- <<< vibe-managed <<< -->`.
   - Body between delimiters contains, for each fragment in sorted order: a header line of the exact form `<!-- vibe-md: <basename> -->` followed by the literal contents of that fragment file. Adjacent fragments separated by a single blank line.
   - Block is positioned at the END of the file: there is no non-blank line after the closing delimiter, and the file terminates with exactly one trailing newline after the closing delimiter.

5. **Block is created if CLAUDE.md doesn't exist.** When `$DEST_ROOT/CLAUDE.md` is absent at install time, install-claude-extras.sh creates it. The created file contains only the managed block (no leading user content), terminated by exactly one newline after the closing delimiter.

6. **Block is regenerated, not appended.** Re-running install-claude-extras.sh strips any pre-existing vibe-managed block (matched by exact-string opening/closing delimiters) before writing the new one. The file does not grow on re-run with unchanged source. Removing a fragment from `$SRC_ROOT/claude-md/` removes its `<!-- vibe-md: <name> -->` header and body from the block on next run.

7. **User content is preserved byte-identical.** Any text in `$DEST_ROOT/CLAUDE.md` outside both managed blocks (the write-env-hint block, if present, and the new vibe-managed block) is byte-identical before and after install-claude-extras.sh runs, regardless of how many times it runs and regardless of fragment-set changes. Verified by writing user prose between (or instead of) the blocks, then asserting byte-identity after re-runs.

8. **Empty-source / missing-source cleanup.** Either of:
   - `$SRC_ROOT/claude-md/` exists but contains no `*.md` files, OR
   - `$SRC_ROOT/claude-md/` does not exist at all.

   Effect: install-claude-extras.sh removes any pre-existing vibe-managed block (delimiters and contents) from `$DEST_ROOT/CLAUDE.md`. User content and the write-env-hint block (if present) are preserved. Trailing blank lines after the removed block are collapsed so the file does not accumulate whitespace across runs (mirrors write-env-hint.sh's blank-line-collapse pattern). If the resulting file would be empty (no user content + no write-env-hint block + no vibe-managed block), install-claude-extras.sh either deletes the file OR leaves an empty file — Generator picks; either is acceptable.

9. **Existing functionality intact.** install-claude-extras.sh continues to sync `agents/` and `commands/` exactly as before. The retired-commands cleanup (`copy.md` removal) still runs. The `VIBE_EXTRAS_SRC_ROOT` env override still works. All existing extras-sync smoke tests (the c.md / agents tests at smoke-test.py:1847+) still pass unchanged. The write-env-hint block, if present in `$DEST_ROOT/CLAUDE.md`, is preserved byte-identical across install-claude-extras.sh runs.

10. **`python3 code-check.py` exits 0.** install-claude-extras.sh remains shellcheck-clean. No new shellcheck findings introduced anywhere in the project.

11. **`python3 smoke-test.py` exits 0** with all pre-existing tests still passing AND the following new test functions (Tester picks the names; the listed t-numbers are spec references for AC mapping). Every t-number must have at least one corresponding `def test_...()` and at least one `check(...)` call:

    - **t1**: `web-research.md` exists and satisfies AC1 — contains `WebSearch`, `WebFetch`, a sequencing sentinel from {`BEFORE`, `before`, `first`, `First`}, and ≥50 non-blank lines.
    - **t2**: Dockerfile contains the canonical `COPY claude-md /usr/local/share/vibe/claude-md/` line (literal-string + count = 1).
    - **t3**: install-claude-extras.sh end-to-end with one fragment in source: managed block in `CLAUDE.md` opens/closes with the exact delimiters, contains the `<!-- vibe-md: web-research.md -->` header, and contains at least one substantive sentinel string from `web-research.md` (Tester picks a unique substring from the actual file body that's unlikely to collide with any other content). Block is at the end of the file (no non-blank line after closing delimiter).
    - **t4**: install-claude-extras.sh creates `CLAUDE.md` from scratch when absent (AC5). File ends with exactly one newline after closing delimiter.
    - **t5**: idempotency — running install twice with the same source produces a byte-identical `CLAUDE.md` (sha256 match, file size match).
    - **t6**: user content above and below the block survives a re-run with changed fragment set. Specifically: write user content into CLAUDE.md (mid-file user prose between two newline blocks), run install, then re-run with a *different* set of source fragments (e.g. add a second fragment), assert user content is byte-identical and only the block contents changed.
    - **t7**: empty-source case — `$SRC_ROOT/claude-md/` exists but is empty: a pre-existing vibe-managed block is removed; user content preserved; trailing blank-line accumulation does not occur on repeated empty-source runs.
    - **t8**: missing-source case — `$SRC_ROOT/claude-md/` directory does not exist: install does not error AND if a vibe-managed block already exists (from a prior run), it is also removed (covers Critic's t8 gap).
    - **t9**: multi-fragment ordering — running with two fragments named so that POSIX byte-order sort (`LC_ALL=C`) differs from locale-aware sort (e.g. `Z-fragment.md` and `a-fragment.md`; in POSIX `Z` < `a`, in many locales `a` < `Z` regardless of case): block headers appear in `LC_ALL=C` order. Test verifies the actual byte-order is used.
    - **t10**: agents-and-commands-still-work — fixture has `claude-md/`, `commands/`, and `agents/` populated; install-claude-extras.sh runs once; all three populate correctly (commands/agents files copied to dest, vibe-managed block in CLAUDE.md).
    - **t11** (NEW from Critic concern #9): write-env-hint coexistence — fixture starts with a CLAUDE.md containing user prose; first run write-env-hint.sh, then run install-claude-extras.sh with one fragment; verify both managed blocks are present, both have correct delimiters, and the write-env-hint block content is byte-identical to its expected output. **Tester derives the expected write-env-hint block content dynamically at test runtime by reading `devcontainer/write-env-hint.sh` and extracting the `BLOCK` variable's value (or running write-env-hint.sh against a fresh tempdir and reading the result) — does NOT hardcode the expected bytes, so the test does not drift if write-env-hint.sh is patched.** Then run install-claude-extras.sh AGAIN with a different fragment set and verify the write-env-hint block is STILL byte-identical.
    - **t12** (NEW from Critic concern #5): N→N-1 fragment removal — start with two fragments, install (block contains both); remove one fragment from source; re-install; verify the removed fragment's header and body are gone from the block but the remaining fragment is still present in correct format. **Additionally: while two fragments are present, t12 asserts that exactly one blank line (not zero, not two) separates the closing of the first fragment's body from the `<!-- vibe-md: ... -->` header of the second fragment — closes the AC4 single-blank-line separator coverage gap.**
    - **t13** (NEW from Critic concern #7 medium): absent-source + pre-existing vibe-managed block — first install with a fragment present (block lands), then delete `$SRC_ROOT/claude-md/` directory entirely, then re-run install; verify block is gone and CLAUDE.md is otherwise intact.
    - **t14** (NEW from Planner amendment 2026-04-25): `ssh-discipline.md` exists and satisfies AC1b — contains literal `ssh`, literal `scp`, a prohibition sentinel from {`Do not`, `Don't`, `don't`, `Avoid`, `default to`}, and ≥50 non-blank lines.

12. **No project-invariant violations.** `vibe` launcher contract unchanged; subscription auth (`forceLoginMethod: "claudeai"`) unchanged; PAT scope unchanged; firewall + hook backstops unchanged; `bypassPermissions` safety unchanged. Specifically NEITHER `web-research.md` NOR `ssh-discipline.md` may instruct Claude to bypass the firewall, hooks, or permissions model; neither may instruct exfiltration; neither may weaken any other invariant. `web-research.md` is purely about retrieval-tool sequencing. `ssh-discipline.md` is purely about disposition (default to user-runs-the-command) — it does NOT disable SSH, does NOT modify the firewall, does NOT alter `init-firewall.sh`'s allowlist, does NOT touch `~/.ssh` handling.

13. **TODO.md updated on landing.** Both relevant open items move from `## Open` to `## Done` with one-line notes naming the chosen shape (inline-prose CLAUDE.md fragment via install-claude-extras.sh-managed block at end of CLAUDE.md) and the final commit SHA. The two items are identified by content match:
    - `vibe: default to WebSearch before declaring a URL unreachable`
    - `vibe: ship "no SSH-out without explicit user OK" as a Claude-facing rule`

    (Line numbers not part of the AC; identification is by content.)

## Out of scope

- A `/research <url>` slash command (deferred — separate future task; this task ships the always-on rule only).
- A PreToolUse / PostToolUse hook on WebFetch that mechanically enforces the retry chain (deferred — heavier infra; spec instruction sufficient for v1).
- Behavioral verification that Claude actually obeys the rule in real WebFetch failures. This is trust-but-verify for the operator in real use, NOT an AC. Spec Critic and Reviewer may not require behavior-test coverage of the rule's effect.
- Touching project-level `/workspace/CLAUDE.md`. The rule lives in the user's `~/.claude/CLAUDE.md` only.
- Touching the personal feedback memory at `~/.claude/projects/-workspace/memory/feedback_try_websearch_before_refusing.md`. Personal memory and shipped vendor rule are separate artifacts; both can coexist without contradiction.
- Migrating other one-off operational rules into this mechanism beyond the two named fragments (extension point exists for future fragments; this task ships exactly two: `web-research.md` and `ssh-discipline.md`).
- Cross-host or cross-machine synchronization of the persistent volume's CLAUDE.md.
- Internationalization or alternative-language versions of the rule prose.
- Visual UI markers (e.g. surfacing in the vibe banner that the rule is active).
- Concurrent install runs (two containers starting simultaneously sharing the persistent volume): the persistent volume is host-local and concurrent vibe sessions are not a real failure mode given the typical user pattern (one container per session). If a concurrent-write race is observed in practice, a follow-up task can add file locking.
- Symlink / read-only / directory-instead-of-file edge cases for `$DEST_ROOT/CLAUDE.md` (Critic concern #6). Trust the persistent volume to be a normal writable directory; surface any failure mode if encountered.
- A `/research` or similar manual-override slash command — explicitly deferred above.
- Renaming the `claude-md/` source dir or the managed-block delimiters (these are pinned interface choices for v1).

## Test location

`smoke-test.py` — Tester appends new test functions following the existing extras-sync test pattern (smoke-test.py:1847 onward). **Once Tester commits these tests, they are immutable — Generator cannot edit them.**

The new fixture content for tests goes in tempdirs created per-test (existing pattern). No new fixture files committed to the repo. Tester may add new module-level path constants at the top of smoke-test.py (e.g. `WEB_RESEARCH_MD = REPO / "devcontainer" / "claude-md" / "web-research.md"` and `SSH_DISCIPLINE_MD = REPO / "devcontainer" / "claude-md" / "ssh-discipline.md"`) — those are Tester writes and Generator must not touch them.

## Proposed budget

**1 cycle** with `--max 2` headroom. Rationale: the change is an extension of an established pattern (install-claude-extras.sh's existing `install_dir`) plus inline-block management modeled directly on `write-env-hint.sh` (which is in-tree, ~40 lines, and proven). No external dependencies, no Docker required for verification, no novel infra. Spec Critic resolved 3 blocking concerns inline (shape change, block position, sort collation) plus 12 medium/low concerns. Planner-amendment 2026-04-25 added a second fragment (`ssh-discipline.md`) — same mechanism, one extra source file + one extra grep test, no structural risk added. If a residual concern surfaces during cycle 1 the budget can flex to 2.
