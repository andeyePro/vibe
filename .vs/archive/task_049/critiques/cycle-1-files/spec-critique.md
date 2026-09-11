# Spec Critique — task_049 `vibe --agent codex` (spec-draft-codex-agent.md)

## Concerns

1. **BLOCKING (AC3)** — foreground `exec launch_codex` bypasses ALL exit-hook
   cleanup the Claude path relies on. `launch_claude` is only ever invoked
   *backgrounded* (`launch_claude ... &`, vibe:4978), so its internal `exec`
   replaces the subshell, not the main script — the main process lives on to
   `wait`, `restore_terminal` (task_031) and run the copy-watcher teardown
   (`vibe_exit_hook_add 'kill "$WATCHER_PID"…'`, vibe:4904/5002). AC3 instead
   wants `launch_codex` called directly, foreground, un-backgrounded — that
   `exec` replaces the *main vibe process*, and bash EXIT traps do not fire
   across a successful `exec`. Net effect: the copy-watcher is orphaned on
   every Codex-led launch, and terminal-state restore after the TUI exits is
   skipped. AC3 must say how watcher/terminal cleanup survives this path
   (e.g. wait on `launch_codex` like the supervised path does, minus only
   marker/heartbeat/relaunch) or explicitly accept the leak.

2. **BLOCKING (AC4 vs AC7)** — `codex-entry.sh`'s two preconditions are
   hardcoded absolute paths (`/etc/codex/requirements.toml`,
   `/home/node/.codex`), unlike `codex-guard-liveness.sh`'s deliberate
   `--root`/`--bin` override. AC7 claims to test both branches by running
   the copied script "with a temp `HOME` whose `.codex` dir exists or not" —
   but the script never reads `$HOME`; it tests the literal path. Verified
   live: in this dev container `$HOME` already *is* `/home/node`
   (`id`→node, `echo $HOME`→`/home/node`) and `/etc/codex` doesn't exist at
   all, so the fixture can't control either check without mutating real
   root-owned system paths — which needs privileges the test shouldn't
   need and could clobber a real Codex login mount on the host running the
   suite. The "success path" and "missing login dir" cases in AC7 are not
   mechanically achievable as written.

3. **BLOCKING (AC4 vs AC7/AC8)** — AC4 requires codex-entry be added to
   `codex-guard-liveness.sh`'s ownership check (a). `smoke/checks_18_codex_
   runtime.py`'s `_codex_liveness_fixture` builds an isolated `bin_dir`
   fixture *without* a codex-entry file, and several passing tests
   (`test_codex_liveness_ownership_failure`, the success-path test) run
   liveness against it. Adding the check without updating that fixture
   breaks those tests. AC7's "Test files" list only names `checks_17`/
   `checks_21` — checks_18 is never named as in-scope — yet AC8 demands
   the whole suite green.

4. **BLOCKING (AC1)** — "reuse the `.vibe/domains` verification idiom" is
   contradicted by "must be untracked **and not a symlink**". The cited
   idiom (`_extra_domains_file_ok`) and its sibling (`_codex_opted_in`'s
   marker check) have **no** `[ -L ]` test anywhere — only a git tracked/
   untracked check, which does not exclude a symlink. The precedent being
   cited doesn't do what AC1 demands: the Generator must invent new
   behaviour with no specified warning text (every other `⚠` line in this
   file is spelled out verbatim; this one isn't) and the Tester has no
   golden wording to assert against.

## Minor concerns

5. **MINOR (AC3)** — "the `pkill -TERM -x claude` cleanup gains a `codex`
   sibling on the same code path" is likely dead code: its only call site
   (`vibe_container_kill_claude`) fires from the stall-watchdog kill branch,
   which AC3 itself says is skipped entirely for Codex. A codex-sibling
   pkill can't fire in a real session under this spec; only a synthetic
   unit test calling the function directly would exercise it.

6. **MINOR** — `docs/codex-integration-plan.md` §3's item-7 row lists
   `devcontainer.json` as changed; no AC here mentions it. Plausibly fine
   (reuses phase-1a's existing mount/exec plumbing) but the spec should say
   the deviation is deliberate rather than leave it for later dispute.

7. **MINOR (AC1)** — never states `parse_vibe_args` gains an explicit
   `--agent)` case, unlike `--profile`/`--model`, both spelled out there.
   Without one, `--agent codex` falls into the generic `--*) Unknown flag`
   branch. Probably obvious, but every sibling flag is named and this isn't.

8. **MINOR (Out of scope)** — excludes `guard-bash.sh`, `guard-fs.sh`,
   `init-firewall.sh`, `settings.local.json`, sudoers, but not
   `devcontainer/codex/{requirements,config}.toml`, `hooks.json` or
   `codex-guard-adapter.sh`. Given concern 3, a Generator under budget
   pressure could "fix" a failing liveness fixture by loosening the policy
   layer instead of fixing the test fixture — worth an explicit exclusion.

## Verdict

**revise** — concerns 1-4 are each independently blocking: #1 is a real
functional regression (orphaned watcher, skipped terminal restore) with no
mitigation specified; #2 and #3 make parts of AC7's own test plan
mechanically non-executable as written; #4 hands the Generator an
under-specified security-adjacent check with no reference behaviour to copy
and no wording for the Tester to pin.
