# Spec Critique — spec-draft-codex-policy.md (task_046)

## Concerns

1. **BLOCKING (AC1, AC7).** `[features]` pins `multi_agent`, `multi_agent_v2`,
   `apps`, `js_repl` off but omits `unified_exec` / `allow_tty`. Per the
   inventory, `write_stdin` gets **no PreToolUse hook at all** — it feeds
   arbitrary further bytes into an already-open PTY opened by a prior,
   innocuous `exec_command` (e.g. a bare `bash`). Every later command typed
   into that shell (a real `git push --force origin main`, `rm -rf
   ~/.codex`, `sudo …`) skips the adapter, guard-bash.sh, and the `rules`
   exec policy entirely — both hook backstop and hook-free backstop are
   bypassed at once. AC7's "UNMEDIATED … because its session was already
   gated at exec_command time" is not true once the PTY exists. The fix is
   available and in-scope: pin `unified_exec = false` (inventory confirms
   this forces `ExecCommandHandler::one_shot`, still hooked as `Bash` per
   invocation, shell use unaffected). AC1 and AC7's rationale both need
   revision.

2. **BLOCKING (AC1).** `rules.prefix_rules` matches an ordered **prefix** of
   argv tokens (confirmed in the inventory's §3), not a substring/regex.
   `pattern=[git,push,--force]` only fires when `--force` is literally the
   third token — `git push --force origin main` matches, but the equally
   common `git push origin --force` or `git push origin main --force` does
   not, nor does anything routed through `bash -c "..."`/`env`/a wrapper
   (argv then starts with `bash`, not `git`). Likewise `sudo` as a bare
   first-token pattern is trivially evaded by any indirection. This makes
   the rules-based backstop — the one D2(b) relies on precisely because
   hooks fail open — unreliable for its stated purpose on ordinary,
   non-adversarial usage, not just a crafted bypass. Spec and AC9 need to
   either accept/document this as a known-weak layer (and lean harder on
   the guard/adapter path + firewall) or specify a pattern set that covers
   realistic token orders; right now it silently overclaims coverage.

3. **BLOCKING (AC5b).** The liveness check for `allow_managed_hooks_only =
   true` and the `managed_dir` line is spec'd as a "contains" check (no
   TOML parse mentioned, unlike (a)/(c) which do use `stat`/`jq`). A
   commented-out `# allow_managed_hooks_only = true` line satisfies a naive
   `grep -q`. For a liveness gate whose entire job is refusing to boot on
   misconfiguration, this is exactly the trivial-evasion failure mode the
   task is meant to close. Require a real TOML read (`tomllib`/`jq`-style,
   consistent with (c)) here too.

4. **BLOCKING (AC1) — inconsistent with the existing guard.** Forbidding
   `git push --force-with-lease` outright contradicts guard-bash.sh's own
   policy, which explicitly *permits* (and its block message recommends)
   `--force-with-lease` as the safe alternative to `--force`. Nothing in
   the spec or the plan doc justifies making Codex-led sessions strictly
   less capable here; it reads like a copy-paste of the three force
   variants without checking guard-bash's actual semantics. Either drop
   `--force-with-lease` from the forbidden list or state explicitly why
   Codex sessions get a stricter git-push policy than Claude sessions.

5. **MINOR (AC1 vs. task summary) — internal contradiction.** The task
   summary states "danger-full-access is the **only** working sandbox
   mode" (bwrap needs user namespaces, unavailable here), yet AC1 sets
   `allowed_sandbox_modes = ["read-only", "danger-full-access"]`. If
   read-only also depends on bwrap it can't "work" either (it would just
   fail-closed per command, which may be intended but isn't said); if it
   instead uses the Landlock fallback and truly works without user
   namespaces, the summary's "only" claim is overstated. Either is fine,
   but the doc contradicts itself and a reader can't tell which is true.
   Resolve before AC8's F11 write-up locks it in.

6. **MINOR (AC1).** `sudo` is blanket-forbidden via `rules`, but the
   Dockerfile's sudoers block already scopes `node`'s passwordless sudo to
   three specific commands, including `refresh-extra-domains.sh` — a
   documented, benign remedy for a stale firewall pin. Forbidding all
   `sudo` removes that path for Codex-led sessions with no stated
   rationale; confirm this is deliberate (and note it in AC8's docs) rather
   than an unexamined side effect.

7. **MINOR (AC4).** Patch-mode path extraction is grep/line-prefix based on
   `*** Add File: ` etc. The AC doesn't say whether matching is anchored to
   line-start only (excluding hunk-body lines that happen to contain the
   same literal text) or how trailing whitespace/CRLF in the extracted path
   is handled before it's passed to `guard-fs.sh`. Given this is the entire
   mediation path for `apply_patch`, the matching rule should be pinned
   down and AC9 should include an adversarial fixture (a patch whose body
   content embeds a decoy `*** Update File:`-looking line) rather than only
   well-formed patches.

8. **MINOR (AC5d).** The three liveness fixtures cover bash-mode
   ask-becomes-deny (`/learnings`) and patch-mode structural deny
   (`.codex/config.toml`), but never patch-mode ask-becomes-deny (e.g. a
   patch touching `/learnings/x.md`). If that code path regresses, nothing
   at boot would catch it. Add a fourth fixture.

9. **MINOR (AC1).** The "cite the struct field in a comment above each key"
   requirement is untested — AC9's list never checks for the comments'
   presence, so a Generator can satisfy AC1's key/value checks while
   dropping the citation discipline entirely. Either add a mechanical check
   or drop the requirement from AC1 (don't leave a documentation mandate
   with no corresponding test).

10. **MINOR (AC5f).** "`codex --version` ≥ 0.154.0" doesn't specify the
    comparison method (string vs. semver-aware) or behavior on a version
    string with a suffix (`0.154.0-dev`); low risk but worth one line so
    the Tester and Generator agree.

## Verdict

**revise** — concerns 1-4 are BLOCKING: #1 and #2 are real, low-effort
bypasses of exactly the property the task exists to guarantee ("both vibe
backstops hold"), #3 is a liveness gate that can be trivially satisfied by
a commented-out line, and #4 is an unjustified behavioral inconsistency
with the sibling guard. None require touching an out-of-scope file — all
are fixable inside `requirements.toml`'s own AC1 plus one liveness-check
tightening and one liveness fixture addition.
