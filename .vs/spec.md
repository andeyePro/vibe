# task_009 — vibe: in-container `/learn` slash command + `/learnings` write-confirm hook

**Revised after Spec Critic iterations 1 + 2.** Iter-1: 4 BLOCKING + 8 MEDIUM addressed. Iter-2 returned `revise` with 2 BLOCKING + 5 MEDIUM/LOW; all addressed inline below per the /vs 2-iteration cap. Iter-2 BLOCKING fixes: (a) the generic `sed -i` regex was rewritten to require an explicit standalone `-i` token alongside `/learnings/`, so `sed -n '/learnings/p'` no longer false-positives; (b) `tee --` (and analogous `--` end-of-options bypasses for `cp`/`mv`/`rm`/etc.) explicitly added to the out-of-scope bypass list. Iter-2 MEDIUM fixes: AC12 fixture list expanded to cover all 9 binaries (was 3); AC9 git-diff check pinned to `git diff HEAD` (commit-state-independent); AC2 architectural "evaluate ALL conditions" requirement clarified — the existing `is_push` short-circuit is acceptable because all guard-bash exit paths run on the full command string, so block-beats-ask is preserved by the existing structure.

Key changes from draft:
- **Hook output schema cited** (resolves BLOCKING #1) — primary source URL pinned in spec body, AC10 fixture asserts the exact key path so a wrong schema fails the test (not just silently no-ops).
- **Bash detection bypass acknowledged inside AC2** (resolves BLOCKING #2) — moved the best-effort scope language out of preamble prose into the AC's body, with a concrete enumerated list of out-of-scope bypass classes.
- **Compound-command "block beats ask" rule** (resolves BLOCKING #3) — guard-bash.sh now refactored to evaluate ALL conditions before deciding; exit-2 always wins over ask. New AC explicit.
- **Path normalization required for guard-fs.sh** (resolves BLOCKING #5) — `realpath -m` before the prefix check; AC1 + AC10/AC11 fixtures cover `..` traversal.
- **NotebookEdit dropped from matcher** (resolves MEDIUM #16) — learning entries are markdown, notebooks are out of scope; documented.
- **`sed -i` and other multi-clause patterns specified explicitly** (resolves MEDIUM #3).
- **`learn-hook.md` content sentinels locked** (resolves LOW #8) — three required phrases verifiable by grep.
- **jq host-dependency handling for smoke tests** (resolves MEDIUM #13).
- **`code-check.py` file-count assertion replaced by exit-0 check** (resolves LOW #12).
- **Dockerfile COPY + chmod tested separately** (resolves MEDIUM #10).
- **Trust-model justification moved into spec body** (resolves MEDIUM #14).
- **`permissionDecisionReason` UX text specified more carefully** (resolves MEDIUM #15) — generic "modifying" wording covers writes/edits/deletes accurately.

---

## Task summary

Today vibe's cross-org learning library at `/learnings` is bind-mounted into every container with `readonly: True` set in the per-session devcontainer override config. Verified 2026-04-25: the readonly flag is silently ignored on macOS by Docker Desktop / OrbStack's `fakeowner` overlay — `mount` reports `rw,nosuid,nodev,relatime,fakeowner` and a write test (`echo > /learnings/test`) succeeds. A buggy or compromised in-container Claude could overwrite, delete, or amend library entries; in public-mode (git-tracked) libraries, those changes can be committed and pushed before the user notices.

Separately: there is no in-container slash command for capturing learnings. The user has to switch to their Mac shell and run `vibe learn "<pattern>"` host-side, breaking session flow. The blocker for shipping `/learn` inside the container has been the same write-bridge design question — until we have a trust gate, a `/learn` command can write anything anywhere under `/learnings` unprompted.

This task ships both halves of the answer at once, because they are interdependent and the trust model only makes sense when shipped together:

1. **A PreToolUse hook gates every write to `/learnings`.** Write tool, Edit tool, MultiEdit tool, and Bash tool (for the common shell-write idioms) all go through it. On detection the hook emits a Claude Code `permissionDecision: ask` JSON envelope so Claude Code itself prompts the user y/n. Trust nothing; no token-bypass; same trust boundary as host-side `vibe learn`'s confirm flow. The mount staying RW is now intended state — the hook is the security layer.

2. **A `/learn` slash command writes a proposed entry.** `/learn <pattern>` produces a filename and body that exactly match the host-side `vibe learn` output (`/learnings/${ts}-${rand}.md` with body `# ${ts}\n\n${pattern}\n`), then issues a Write tool call to land it. The hook fires, the user sees the prompt with the proposed file path and reason, the user confirms, the Write proceeds. Push-to-git stays host-only — the command output tells the user to run `vibe learn --push` (a stub that does NOT yet exist; explicit out-of-scope) on the Mac shell when ready.

This shape resolves the existing `vibe learn: /learnings mount is RW, not RO (security)` TODO and lays groundwork for the `auto-promote feedback memories to learning library` TODO.

### Hook output schema (canonical)

Source: Claude Code hooks documentation at `https://code.claude.com/docs/en/hooks.md`. PreToolUse hooks return JSON to stdout and exit 0; the JSON envelope is:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "<text shown to the user in the prompt>"
  }
}
```

Claude Code renders its standard permission prompt with the reason text. AC10/AC12 assert the EXACT key path (`.hookSpecificOutput.permissionDecision == "ask"`) so an implementation that uses the wrong shape (e.g. flat `{"decision": "ask"}`) fails the test rather than silently no-opping.

### Block-beats-ask invariant

The existing guard-bash.sh emits `exit 2` for `git push --force` (without `--force-with-lease`) and for `git push --delete <branch>`. This task adds an `ask` path for `/learnings` writes. **If a single command triggers BOTH an exit-2 condition AND a /learnings write detection, exit 2 wins.** The script must evaluate ALL conditions before choosing, never short-circuit on the ask path. AC2 specifies this. Without this rule a compound command like `rm /learnings/old.md && git push --force origin main` would prompt the user to confirm the `rm`, and on yes the entire compound runs — including the unprotected force-push.

### CLAUDE.md invariant analysis

CLAUDE.md says: "hooks in `guard-bash.sh` + `settings.local.json` are the tool-call backstop. Don't weaken either." This change does not weaken the existing hook — the existing exit-2 conditions are preserved byte-for-byte (AC3). It adds a NEW `ask` path for `/learnings` writes that previously had NO hook protection (the `readonly` mount was the supposed boundary, but it never worked on macOS). Going from "no protection" to "ask the user" is strictly stronger, not weaker. The block-beats-ask rule (above) ensures the new path never undermines existing block paths.

### Defense-in-depth scope: what the Bash hook CANNOT catch

Static pattern matching against the Bash command string detects literal write idioms but cannot detect (and AC2 explicitly excludes from the contract):
- Variable indirection (`f=/learnings/x; echo > "$f"`) — the redirect target is a variable, not a literal path.
- Env-var path (`OUT=/learnings/x command-that-uses-OUT`) — same reason.
- Interpreter-embedded writes (`python3 -c "open('/learnings/x','w').write('y')"`, `perl -e "open(F,'>/learnings/x')"`, `node -e "require('fs').writeFileSync('/learnings/x','y')"`).
- Heredoc-redirected writes where the destination is constructed via expansion.
- Multi-stage pipelines (`some-cmd | tee >(cat > /learnings/x)`) — the redirect inside process substitution is harder to detect.
- `eval`, `bash -c <constructed string>`, and other dynamic-command-execution paths.
- `tee -- /learnings/x` specifically. The `tee` regex anchors directly on `\s+['"]?/learnings/` after the flag group with no `[^|;&]*` wildcard, so `--` between `tee` and the path defeats it. The other binaries in the family (`cp`, `mv`, `rm`, `ln`, `mkdir`, `chmod`, `chown`, `truncate`, `dd`) use a generic regex with `[^|;&]*` wildcard before `/learnings/`, which DOES match across `--`; `rm -- /learnings/x` is correctly caught. Acknowledged limitation only for tee.
- Long-form GNU flags (e.g. `sed --in-place …` rather than `sed -i …`). The sed-write detection regex requires short-form `-i` (standalone or combined like `-ri`); `--in-place` is not matched. Acknowledged limitation.

These are real bypass vectors. The Write/Edit/MultiEdit hook (AC1) is the primary gate — it sees the structured `tool_input.file_path` and is reliable. The Bash hook is layered defense-in-depth that catches the obvious shell idioms; AC2 enumerates what it covers and what it does not. The README paragraph (AC8) communicates this scope to the user.

## Acceptance criteria

1. **`devcontainer/guard-fs.sh` exists** as an executable shell script using `set -euo pipefail`. Reads PreToolUse JSON from stdin. Extracts `tool_input.file_path` via `jq -r '.tool_input.file_path // empty'`. **Normalizes** the extracted path via `realpath -m` (which resolves `..`, `.`, and double-slashes without requiring the path to exist). If the normalized path equals `/learnings` OR starts with `/learnings/`, the script emits the canonical ask-JSON to stdout (with a `permissionDecisionReason` of the exact form `vibe: modifying the learning library at <normalized-path> — confirm to proceed`) and exits 0. Otherwise the script prints nothing and exits 0. Reasoning for `realpath -m`: a literal `/learnings/../etc/passwd` "starts with" `/learnings/` but resolves outside the library; without normalization, a confirmed write would land outside the library while the user thought they were confirming a learning-library change.

2. **`devcontainer/guard-bash.sh` extended** with a `/learnings` write-detection step. Implementation requirements:
   - The script evaluates all conditions before deciding the exit path. **No early-exit on the ask path** — block beats ask.
   - Evaluation order: (a) detect git-push violations as today (`is_push && has_force && !has_lease` → block; `is_push && (has_delete || has_colondel)` → block); (b) detect `/learnings` write idioms; (c) decide. If (a) fires → `exit 2` with the existing stderr message. Else if (b) fires → emit canonical ask-JSON to stdout, `exit 0`. Else → `exit 0` silently.
   - The detection in (b) MUST cover at minimum these idioms; each is matched against the literal command text:
     - Shell redirect to /learnings: regex `(>|>>|&>|&>>)\s*['"]?/learnings/`
     - tee to /learnings: regex `(^|[[:space:]]|;|&|\|)tee([[:space:]]+-[a-zA-Z]+)*\s+['"]?/learnings/`
     - File-modifying binaries against /learnings: any of `cp`, `mv`, `rm`, `ln`, `mkdir`, `chmod`, `chown`, `truncate`, `dd`. For each, the regex is `(^|[[:space:]]|;|&|\|)<binary>([[:space:]]+-[a-zA-Z]+)*\s+[^|;&]*['"]?/learnings/`. Note: this generic regex inherently false-positives on `<binary>` followed by `/learnings/` substring inside a quoted argument, but the listed binaries are all destructive/modifying so any `/learnings/` reference deserves the prompt. The `dd` case relies on `[^|;&]*` skipping past `if=…` and `bs=…` arguments to find `of=/learnings/...`.
     - **`sed -i` write detection (special case).** The generic regex above is NOT used for `sed`, because `sed -n '/learnings/p'` (a read) contains the literal `/learnings/` inside the sed expression and would false-positive. Instead, the detection requires THREE separate conditions all to hold against the command string: (i) a `sed` invocation token via regex `(^|[[:space:]]|;|&|\|)sed[[:space:]]`; (ii) an explicit standalone `-i` flag via regex `(^|[[:space:]])-i([[:space:]]|$)` OR a combined-flag form like `-ri`/`-Ei`/`-iE` via regex `(^|[[:space:]])-[a-zA-Z]*i[a-zA-Z]*([[:space:]]|$)` — the second alternative is a superset of the first (it also matches plain `-i` since `[a-zA-Z]*` allows zero chars on each side); the two are an OR for clarity, not a partition. Implementation can use either single combined-flag regex alone or both — same result.; (iii) the literal substring `/learnings/`. Implementation guidance: a triple-`grep -qE` chain (each emitting a result, all three required to be true) is the canonical implementation. Tester fixture `sed -n '/learnings/p' /tmp/file` MUST exit 0 (read; no `-i`); fixture `sed -i 's/foo/bar/' /learnings/x.md` MUST trigger ask (write; `-i` present, `/learnings/` present).
   - Read commands MUST NOT trigger detection: `cat`, `ls`, `grep`, `head`, `tail`, `less`, `find /learnings`, `wc`, `awk`, `diff`, `cmp` against `/learnings` paths exit 0 with no output.
   - **Out-of-scope bypass classes** (acknowledged in AC, not contract violations): variable-indirection redirects, env-var path commands, interpreter-embedded writes (`python3 -c`, `perl -e`, `node -e`, etc.), `eval`, `bash -c <constructed>`, dynamic heredoc destinations, process-substitution redirects. The Write tool hook (AC1) covers tool-call writes; the Bash hook is layered best-effort for the common literal idioms only.

3. **Existing guard-bash.sh git-push protections preserved unchanged.** `git push --force` (without `--force-with-lease`) still hits `exit 2` with the existing stderr message; `git push origin :branchname` still hits `exit 2`. After the change a command like `rm /learnings/old.md && git push --force origin main` MUST exit 2 (block beats ask), NOT exit 0 with ask-JSON.

4. **`/workspace/vibe`'s settings.local.json heredoc is updated.** **Critical location note:** `.claude/settings.local.json` is gitignored and runtime-generated by the `vibe` launcher itself — there is a `cat > "$WORKSPACE/.claude/settings.local.json" << 'EOF'` heredoc at vibe lines ~974–1007 that overwrites the file fresh on every launch. The edit MUST land in this heredoc, NOT in the runtime artifact at `.claude/settings.local.json` (which would be wallpaper — overwritten next launch). Required change inside the heredoc: APPEND a new entry to the `hooks.PreToolUse` array (after the existing Bash entry; order is documented but not behaviorally critical since a single tool call matches a single matcher). The new entry has `matcher` field exactly `"Write|Edit|MultiEdit"` (NOT `NotebookEdit` — see Out of scope) and a hooks array pointing to `/usr/local/bin/guard-fs.sh`. The existing Bash matcher entry stays byte-identical. The Stop and Notification entries stay byte-identical. `permissions.defaultMode` and `forceLoginMethod` stay byte-identical. The heredoc must remain valid JSON when emitted (`python3 -c 'import json; json.load(open("…"))'` against a freshly-launched vibe's runtime file exits 0). The smoke test for AC4 reads `/workspace/vibe`'s text and asserts the heredoc body contains the new matcher entry — NOT the runtime `.claude/settings.local.json`.

5. **Dockerfile updated.** Two distinct changes verified by separate greps:
   - **5a.** A line matching exactly `COPY guard-fs.sh /usr/local/bin/` (canonical no-trailing-slash form, mirroring the existing guard-bash.sh COPY). One occurrence.
   - **5b.** `/usr/local/bin/guard-fs.sh` appears in the `chmod +x` chain. One occurrence in a `chmod +x` line.

6. **`devcontainer/commands/learn.md` exists** as a slash command markdown file. Body must include all of:
   - A description that `/learn <pattern>` captures a cross-org learning into `/learnings/`.
   - The exact Bash one-liners to compute filename components (must be present verbatim so the format matches host-side byte-for-byte):
     ```
     ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
     rand=$(python3 -c 'import binascii,os; print(binascii.hexlify(os.urandom(3)).decode())')
     ```
   - A description of the file path: `/learnings/${ts}-${rand}.md`.
   - The exact body format (matching host-side `learning_format_entry`): `printf '# %s\n\n%s\n' "$ts" "$pattern"` — timestamp header, blank line, pattern body, single trailing newline.
   - Instruction that the model issues a single Write tool call to that path with that body.
   - Instruction that the model PRINTS the proposed path + body preview to the user BEFORE issuing the Write, so the hook prompt's context is clear.
   - Refusal text: if `/learnings` does not exist as a directory, respond with the exact one-line message `/learn: /learnings is not mounted (run 'vibe learn --init' on host first)` and do NOT issue the Write tool call.
   - Note that pushing the new entry (in public-mode libraries) is host-only — point user at `vibe learn --push` (acknowledged as not-yet-built, separate task) or to `cd $VIBE_LEARNING_PATH; git add … && git commit && git push` manually.
   - Multi-line `<pattern>` is supported — embedded newlines pass through to the body as-is.

7. **`devcontainer/claude-md/learn-hook.md` fragment exists**, picked up by `install-claude-extras.sh`'s existing `claude-md/*.md` sync. Content explains the hook trust model to in-container Claude. Mechanically: ≥30 non-blank lines AND contains all three sentinel phrases (locked for Tester grep): `permissionDecision`, `do not bypass`, and `host-only`.

8. **README.md gets a paragraph** in or directly under the existing `/learnings` discussion. Content explains: the bind-mount is read-write on macOS regardless of `readonly` (Docker Desktop / OrbStack `fakeowner` quirk); a PreToolUse hook intercepts every tool call writing under `/learnings` and prompts the user y/n; this is the security boundary, not the mount itself; the Bash gate is best-effort and detailed bypass classes are documented in `devcontainer/guard-bash.sh`. Verifiable via grep for the sentinel phrase `PreToolUse hook gates writes` (exact match locked).

9. **`install-claude-extras.sh` requires NO change.** `git diff HEAD -- devcontainer/install-claude-extras.sh` is empty (uses `HEAD` so the check is commit-state-independent for the smoke-test runner). (The slash command and CLAUDE.md fragment are picked up by existing sync mechanisms.)

10. **`/usr/local/bin/guard-fs.sh` produces correct ask-JSON for /learnings writes.** Smoke test fixture set, each as its own subprocess invocation:
    - Input `{"tool_input":{"file_path":"/learnings/2026-04-26T17:00:00Z-abcdef.md"}}` → stdout is valid JSON with `.hookSpecificOutput.hookEventName == "PreToolUse"`, `.hookSpecificOutput.permissionDecision == "ask"`, `.hookSpecificOutput.permissionDecisionReason` non-empty and contains the substring `/learnings/`. Exit 0.
    - Input `{"tool_input":{"file_path":"/learnings"}}` → same ask-JSON. Exit 0.
    - Input `{"tool_input":{"file_path":"/learnings/sub/dir/file.md"}}` → same. Exit 0.

11. **`/usr/local/bin/guard-fs.sh` correctly handles non-/learnings AND traversal-attempt paths.** Smoke test fixture set:
    - Input `{"tool_input":{"file_path":"/workspace/foo/bar.md"}}` → empty stdout, exit 0.
    - Input `{"tool_input":{"file_path":"/learnings/../etc/passwd"}}` → empty stdout, exit 0 (after normalization `/etc/passwd` is not under `/learnings`).
    - Input `{"tool_input":{"file_path":"/learnings/../../tmp/x"}}` → empty stdout, exit 0 (normalizes to `/tmp/x`).
    - Input `{"tool_input":{}}` (no file_path key) → empty stdout, exit 0.

12. **`devcontainer/guard-bash.sh` produces correct ask-JSON for /learnings shell-write idioms.** Smoke test fixture set, iterated (one assertion per fixture):
    - `echo hi > /learnings/test.md` → ask-JSON, exit 0.
    - `echo hi >> /learnings/test.md` → ask-JSON, exit 0.
    - `cmd | tee /learnings/z.md` → ask-JSON, exit 0.
    - `tee -a /learnings/z.md < /tmp/x` → ask-JSON, exit 0.
    - `cp /tmp/x /learnings/y.md` → ask-JSON, exit 0.
    - `cp -r /tmp/dir /learnings/sub` → ask-JSON, exit 0.
    - `mv /tmp/x /learnings/y.md` → ask-JSON, exit 0.
    - `rm /learnings/old.md` → ask-JSON, exit 0.
    - `rm -rf /learnings/old/` → ask-JSON, exit 0.
    - `ln -s /tmp/target /learnings/link` → ask-JSON, exit 0.
    - `mkdir /learnings/newdir` → ask-JSON, exit 0.
    - `chmod 644 /learnings/x.md` → ask-JSON, exit 0.
    - `chown node:node /learnings/x.md` → ask-JSON, exit 0.
    - `truncate -s 0 /learnings/x.md` → ask-JSON, exit 0.
    - `dd if=/dev/zero of=/learnings/x bs=1M count=1` → ask-JSON, exit 0.
    - `sed -i 's/foo/bar/' /learnings/x.md` → ask-JSON, exit 0.
    - `sed -ri 's/foo/bar/' /learnings/x.md` → ask-JSON, exit 0 (combined `-ri` flag).

13. **`devcontainer/guard-bash.sh` correctly allows /learnings reads.** Smoke test fixture set:
    - `cat /learnings/x.md` → empty stdout, exit 0.
    - `ls /learnings/` → empty stdout, exit 0.
    - `grep -r foo /learnings/` → empty stdout, exit 0.
    - `head /learnings/x.md` → empty stdout, exit 0.
    - `sed -n '/learnings/p' /tmp/file` → empty stdout, exit 0 (`sed` without `-i` is a read).

14. **`devcontainer/guard-bash.sh` preserves git-push behavior AND enforces block-beats-ask.** Smoke test fixture set:
    - `git push --force origin main` → exit 2, stderr matches existing `vibe: 'git push --force'` message.
    - `git push origin :branchname` → exit 2, stderr matches existing branch-delete message.
    - `git push origin main` (normal push) → exit 0, no output.
    - `rm /learnings/old.md && git push --force origin main` → exit 2 (NOT 0 with ask-JSON — block beats ask).
    - `git push --force origin main && echo hi > /learnings/x.md` → exit 2 (same — block beats ask regardless of order).

15. **`python3 code-check.py` exits 0.** No new shellcheck warnings. (Do not assert on a specific file count — `code-check.py` is the source of truth for which files it scans; check exit 0, not the count.)

16. **`python3 smoke-test.py` exits 0.** Pre-existing check count (360) MUST NOT decrease. New tests for ACs 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 added. The hook-fixture tests (AC10–14) are guarded by a `which jq` and `which bash` check at smoke-test startup; if either is absent, the affected tests SKIP with a clear stderr warning, but the rest of the suite still runs (and the absence of these tools must NOT cause smoke-test to exit non-zero). The new test functions are registered in `main()` and follow the existing `test_task009_<topic>` naming convention.

17. **MANUAL-TESTS.md gets a new entry** describing how to verify end-to-end in a live container: launch vibe in a project with `/learnings` enabled, in the container have Claude attempt to Write to `/learnings/test.md`, confirm the user sees a permission prompt with the reason text, confirm "yes" lets the Write proceed, confirm "no" blocks the Write. Three numbered steps. This is the safety-net for the hook-output-schema risk — if the schema is somehow wrong despite passing AC10's structural check, this manual test catches it before users hit it.

## Out of scope

- Host-side `vibe learn --push` helper. Mentioned in `/learn` output as the pointer; building it is a separate task.
- Auto-promote feedback memories to /learnings (separate TODO).
- Volume-vs-bind-mount design (separate TODO).
- Backup mechanism (separate TODO).
- **NotebookEdit tool coverage.** Learning entries are markdown (`.md`), not Jupyter notebooks. NotebookEdit's input schema uses `notebook_path`, not `file_path`, and would require separate handling. Excluded from this task; if a future use-case emerges, add then.
- Bash detection bypass classes enumerated in spec body (variable indirection, interpreter-embedded writes, etc.) — by design, not by omission. Documented in spec body and AC2.
- Behavior when the user denies the prompt — Claude Code's standard "tool call denied by user" path applies; no custom recovery.
- Updating the existing RW-mount-security TODO entry to Done (Planner does this manually post-pass).
- Live in-container schema verification — handled via MANUAL-TESTS.md entry (AC17), not by an automated AC, since the smoke-test host typically does not have Claude Code installed.

## Test location

`/workspace/smoke-test.py`. Hook tests use `subprocess.run([…], input=<json>, capture_output=True)` to feed synthetic stdin to the shell scripts and assert on stdout / exit code. Tests guard against host absence of `jq` or `bash` (skip with warning).

## Proposed budget

2 cycles. Wide diff (new file + 4 modified files + new slash command + new CLAUDE.md fragment + README + ~15 new smoke tests) on security-sensitive surface; one cycle is plausible if Generator nails it but Spec Critic + Evaluator should be ready for a second pass.
