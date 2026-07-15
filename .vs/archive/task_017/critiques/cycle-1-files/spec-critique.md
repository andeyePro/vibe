# Spec Critique — task_017 (shared-repos), Cycle 1 review of full spec.md

Adversarial pass over `/workspace/.vs/spec.md` against the actual `/workspace/vibe`,
`/workspace/devcontainer/credential-helper.sh`, `/workspace/devcontainer/install-claude-extras.sh`,
`/workspace/devcontainer/setup-git.sh`, `/workspace/devcontainer/Dockerfile`,
`/workspace/devcontainer/devcontainer.json`, `/workspace/smoke-test.py`, and the archived
`/workspace/.vs/archive/task_016/spec.md`. Design decisions (declaration+registry split,
ro-default+single-writer lock, exit+relaunch handoff, per-repo tokens via useHttpPath,
silent-when-unregistered) are out of bounds — every concern below is about spec mechanics,
internal consistency, or a factual mismatch with the code the spec asks the Generator to extend.

## Concerns

### BLOCKING

**1. The lock/sidecar path is pinned two different ways, and the "all cycles" section is the stale one.**
The top-level "Pinned names and formats **(all cycles)**" section (spec.md:14) states, as if
settled and unchanging:
> **Lock**: `<shared-checkout>/.vibe-rw-lock.d/` — a DIRECTORY...

and its **Gitignore additions** bullet (spec.md:17) says the managed block adds
`.vibe-rw-lock.d/` and `.vibe-rw-request`.

AC12 (Cycle 3, spec.md:40) then overrides this deep inside a dense parenthetical, relocating
everything into a sidecar dir: `lock = <checkout>/.vibe-signals/rw-lock.d/`, `request =
<checkout>/.vibe-signals/rw-request`, `gitignore entry .vibe-signals/` — and explicitly says
**"C2 must implement the lock in that sidecar path from the start."**

The document's own structure defeats that instruction. A section headed "(all cycles)" reads as
authoritative and fixed; nothing in it, or anywhere before AC12, hints that it will be
retroactively amended by a later cycle's AC. A Cycle-2 Generator building AC9's lock helpers has
no textual reason to open AC12 (Cycle 3, not their job) before writing
`shared_repo_lock_acquire`, and every signal in the doc (the "(all cycles)" header, the fact that
AC9 itself never repeats or overrides the path, deferring implicitly to the pinned section) points
it at `.vibe-rw-lock.d/`. Once Cycle 2's Tester commits functional tests against that path
(mkdir target, gitignore pattern, `shared_repo_lock_holder` output), those tests are **frozen**
per this spec's own "Test location" rule ("once a cycle's tests are committed they are frozen;
later cycles append new functions only") — so Cycle 3 cannot rename the path without either
violating that rule or shipping the sidecar path as a second, parallel mechanism alongside a
dead `.vibe-rw-lock.d/` no one cleans up.

Fix: patch the "Pinned names and formats (all cycles)" section itself — replace the
`.vibe-rw-lock.d/` / `.vibe-rw-request` / two-entry-gitignore text with the sidecar form
(`.vibe-signals/rw-lock.d/`, `.vibe-signals/rw-request`, gitignore entry `.vibe-signals/`) so a
Cycle-2 Generator who never reads AC12 still builds the right thing on the first pass. AC12's
prose can then just describe the sidecar's *purpose* (co-locating lock + claim + gitignore) without
needing to silently amend an "all cycles" pin from three cycles away.

**2. Nobody is assigned to create `<shared-checkout>/.vibe-signals/` on the host before the bind is attempted.**
AC12's final mechanism binds `<shared-checkout>/.vibe-signals/` rw at `/repos/.signals/<name>/`
**even when the code mount is ro**. Check who creates that host directory first:
- AC1 (`vibe repos add`) only validates the code-checkout path (`must contain a .git`) and writes
  the registry entry — it never touches a sidecar dir.
- AC3 (mount assembly, Cycle 1) only builds the bind triple for the CODE mount, `/repos/<name>`.
- AC9's `shared_repo_lock_acquire` does an atomic `mkdir` for `rw-lock.d/`, a *subdirectory* of
  the sidecar — but that helper only runs when an `rw` intent is declared and a lock is actually
  attempted. **For an ro-only shared repo, `shared_repo_lock_acquire` never runs, so nothing ever
  creates the parent `.vibe-signals/` directory** before the launcher tries to bind-mount it.
- AC12 pins the mount's *target* and *name* but assigns the *creation* of the host-side source
  directory to no one.

This is a real footgun, not a theoretical one: Docker's bind-mount behaviour when the **source**
path doesn't exist varies by engine/version — some fail the mount outright, others silently
auto-create it, typically owned by the entity that ran the create (root, inside the Docker
Desktop/OrbStack VM, or the daemon's uid on native Linux). The container's default user is
non-root (`Dockerfile:80` — `USER node`), so a root-auto-created sidecar would make the very first
`/repo claim` (an in-container `mkdir`/file-write under `/repos/.signals/<name>/rw-request`) fail
with a plain permission error — with zero mention anywhere in the spec's failure-mode coverage
(AC12 discusses the ro-mount-can't-take-the-request-file problem at length but never the
does-the-sidecar-dir-even-exist-yet problem). Fix: assign an explicit host-side
`mkdir -p "<checkout>/.vibe-signals"` (before the bind is ever attempted — e.g. folded into AC3's
mount-assembly, or into `vibe repos add`/`vibe repos list`'s resolution step) as its own
requirement, independent of whether a lock is ever acquired.

**3. AC10's EXIT-trap consolidation can silently re-disable the very hook it's supposed to add, and this is exactly the class of hazard task_016 deliberately routed around.**
`vibe` runs under `set -euo pipefail` globally (`vibe:43`). AC10 replaces the single
`trap '...' EXIT` (currently at `vibe:1814`, installed only inside the Darwin+pbcopy block) with a
`vibe_on_exit` dispatcher that iterates an appendable `VIBE_EXIT_HOOKS` array, with "lock release
registers alongside" the clipboard-flush hook. Nothing in AC10 requires the dispatcher to guard
each hook invocation individually (`eval "$hook" || true`-style). If it doesn't, and any one hook
returns non-zero, `errexit` aborts the **whole trap handler** at that point, and every
**later-registered** hook in the array silently never runs.

This is not a rare edge case: AC9 defines `shared_repo_lock_release` to release "ONLY if meta
matches both project and pid — never someone else's lock" — meaning a session that registers an
exit-time release hook but never actually held the lock (the common ro-mount-only case) is a
routine scenario for that hook to return non-zero/refuse. If that hook is registered (chronologically,
per the current script's structure) **before** the Darwin clipboard-flush hook — since lock
handling happens up around `_build_override_config`'s mount-assembly (~vibe:1700), well before the
clipboard trap's current install point (~vibe:1807-1814) — an ordinary ro-only session on a Mac
would have its clipboard-flush-on-exit silently stop working, with no error surfaced (the launcher
just exits).

This is precisely the fragility task_016 flagged when it explicitly declined to touch this trap:
*"the EXIT-trap edit is DROPPED entirely (watchdog lifetime is bounded by claude-PID liveness
instead – safer than touching the fragile clipboard trap)"* and listed *"EXIT-trap modifications
of any kind"* under Out of scope. task_017 is right that a real dispatcher is the correct
long-term fix (a single-slot `trap ... EXIT` is inherently clobber-prone the moment two features
both want cleanup), but AC10 as written doesn't require the one thing that makes a multi-hook
dispatcher safe under `set -e` — individually guarding each hook — despite every other multi-step
sequence in this file (AC6b's watchdog, `launch_claude_supervised`) being meticulous about exactly
that pattern. Fix: AC10 must mandate per-hook guarding in the dispatcher's iteration, and AC11
should add a functional test proving a failing/refusing lock-release hook does not suppress a
later-registered clipboard-flush hook.

### MEDIUM

**4. AC18's "threads it through remoteEnv" glosses over a mechanism that doesn't exist yet, and its phrasing invites the exact subshell-export bug documented three lines above the call site.**
Today, `remoteEnv` in `devcontainer/devcontainer.json` is a **fixed** dict of literal keys, each
`${localEnv:NAME}` (`GITHUB_TOKEN`, `ZOTERO_API_KEY`, `OPENPROJECT_MCP_URL`, ...). Nothing in
`render_devcontainer_with_mounts` (`vibe:837-867`) touches `remoteEnv` at all — it only appends to
`mounts` and `runArgs`. AC18 needs a **dynamic**, per-configured-repo set of `remoteEnv` keys
(`VIBE_SHARED_TOKEN_<SLUG>`), which is a genuinely new plumbing path, not a reuse of existing
plumbing — the AC's "threads it through remoteEnv in the override config" phrasing understates
this.

Worse: `_build_override_config` is invoked via command substitution —
`OVERRIDE_CONFIG=$(_build_override_config "$WORKSPACE")` (`vibe:1700`) — a subshell. The very
comment three lines above that call (`vibe:1691-1696`) exists **specifically** to document that
"Exports from inside `$(...)` die with the subshell" (for `learning_load`). AC18's own wording —
"`_build_override_config` (**or** the launch env staging beside GITHUB_TOKEN's export) exports
each configured shared repo's token" — offers both branches with no warning that the first one is
a trap. A Generator who (reasonably) puts the per-repo `export VIBE_SHARED_TOKEN_*` inside
`_build_override_config`, because that's where the per-repo enumeration naturally happens, will
silently lose every export to the subshell: the token file entry exists, the bind mount works, but
`${localEnv:VIBE_SHARED_TOKEN_X}` resolves empty in the container — a silent widen-to-nothing
failure, not a loud one, in a task whose entire security story is "never silently widen." Fix:
AC18 should say explicitly which side of the subshell boundary the export must happen on, and cite
the `learning_load` comment as the reason why.

**5. AC6 asks the Generator to "find" a `safe.directory` mechanism that does not exist anywhere in this codebase.**
`grep -rn "safe.directory" /workspace/devcontainer /workspace/vibe` returns zero hits. AC6 says:
"extend the existing container-side mechanism in setup-git.sh or equivalent — find where
/workspace gets its safe.directory treatment and mirror it for /repos/*." There is no such
treatment to find — `/workspace` apparently never needed one (`Dockerfile:68-69` chowns it to
`node:node`, and/or Docker Desktop/OrbStack's uid-mapping for the `workspaceMount` key keeps
ownership consistent). Whether an arbitrary `mounts`-array bind entry (the exact mechanism shared
repos, brain2, and zotero all use) gets the same treatment as `workspaceMount` is untested in this
repo — brain2 (also a bind-mounted git repo, rw) shows no recorded ownership friction, which
suggests this may be a non-issue on the primary (Mac) platform, but on native Linux Docker (the
documented secondary platform) an arbitrary host directory's uid is unlikely to match the
container's, and the check would plausibly trip there. AC6 should stop presupposing precedent that
isn't there and just specify the new `git config --global --add safe.directory '/repos/*'` line
directly, with a note on why /workspace has apparently never needed one (so the Generator doesn't
waste a cycle hunting for it, or "fix" something that was never broken).

**6. Gitignore-additions-to-the-shared-checkout is a stated requirement with no owning AC.**
The top "Pinned names and formats" section (spec.md:17) requires a managed gitignore block in the
**shared repo's own checkout** (a different directory from the current project, "usually itself a
vibe project"). No AC in Cycles 1-4 assigns this as deliverable work: AC6 (git ergonomics) only
covers `safe.directory`/`GIT_OPTIONAL_LOCKS`; AC9-AC11 (lock helpers) never mention writing to the
shared checkout's `.gitignore`; AC12 only renames the pinned pattern, it doesn't say who writes it
or when (every launch? at `vibe repos add` time? at first lock-acquire?). Real risk this ships
unimplemented and `.vibe-signals/` cruft becomes committable in the shared repo's own history —
exactly the class of bug this same repo's CLAUDE.md ("Project hygiene for shared/upstream-bound
repos") exists to prevent. Fix: give this an explicit AC and owner.

**7. Cross-cycle mount-triple-count assumption risk.**
AC3 (Cycle 1) describes exactly one bind triple per declared shared repo (`/repos/<name>`). AC12
(Cycle 3) later requires a **second** triple per repo (the always-on `.vibe-signals` sidecar). If
Cycle 1's Tester writes the natural AC3-literal assertion — "exactly one mount entry per
configured shared repo" — it becomes a frozen test Cycle 3 cannot satisfy without touching
Cycle-1-committed tests, which this spec's own rules forbid ("Generator never touches
smoke-test.py"; tests are append-only). Fix: an explicit note in AC3 or AC7 telling the Cycle-1
Tester not to assert mount-count exclusivity per repo.

**8. AC13's `\a` emission is unverified against how the statusLine renderer actually treats control bytes, and the cadence differs from the existing bell precedent.**
The existing bell pattern (`Stop`/`Notification` hooks, `vibe:1637,1646`) fires once, on a
discrete event, via stderr. A `statusLine` command re-runs on every UI repaint tick — if a raw
`\a` byte in its stdout is passed through by Claude Code's TUI (unverified — status-line content
is typically single-line rendered/sanitised, not obviously piped straight to the terminal bell),
the segment would ring on every repaint while the condition holds, not once per new request. There
is no existing precedent in this codebase for embedding control characters in statusLine stdout.
Worth flagging the assumption explicitly in AC13, and treating the bell as best-effort/experimental
rather than a flat requirement if it can't be verified against actual Claude Code behaviour.

### LOW

**9. Provenance error: AC13 calls the exact-output fixtures "the task_016 exact-output fixtures."** They aren't. `.vs/archive/task_016/spec.md` (fully reviewed) contains zero statusLine/model-letter ACs — task_016 is entirely the auto-resume heartbeat/watchdog work. The actual fixtures live in `test_vibe_statusline` (`smoke-test.py:6470`), from a different, unarchived task. Cosmetic, but could send a Tester hunting task_016's archive for context that isn't there. The technical requirement (byte-identical output) is unambiguous from the test file itself regardless.

**10. AC1's "follows the vibe learn subcommand precedent" should name the mechanism, not just gesture at it.** The actual precedent is a literal `if [ "${1:-}" = "learn" ]; then ... fi` dispatch block placed *before* `parse_vibe_args "$@"` (`vibe:1401-1405`, itself after the `VIBE_SOURCE_ONLY` guard at `vibe:1396`). Worth being explicit that `repos` needs the identical placement — otherwise a bare `vibe repos add ...` falls through to `parse_vibe_args`'s catch-all positional branch (`vibe:1382-1389`) and gets treated as a project name (since `repos` doesn't start with `--`).

**11. Credential-helper never-widen attack list is good but not exhaustive.** AC16 names path-missing, `.git`-suffix, subdir-suffix, case-difference, and sanitisation-collision as required attacks. Also worth requiring: a trailing-slash-only path (no `.git`, no subdir), and a `path` value containing `..`/traversal segments or an embedded newline (the credential protocol's stdin `key=value` parsing is exactly the kind of surface that should be attacked with injection strings, mirroring AC2's `shared_repos_parse` injection tests). The general "never widen" principle likely catches these if the Tester generalizes, but naming them explicitly removes the ambiguity.

## Verdict

**revise**

Concern 1 (lock-path pin contradiction) and concern 3 (EXIT-trap dispatcher under `set -e`) are
both concrete, well-evidenced, and cheap to fix in the spec text before any cycle starts — but
expensive to discover mid-flight (concern 1 breaks the frozen-test rule; concern 3 produces a
silent regression that no existing test currently covers). Concern 2 (sidecar dir provisioning) is
a real missing-failure-mode gap that AC12's own dense mechanism-resolution paragraph should have
caught given how much other ground it covers. Recommend the Planner patch the "Pinned names and
formats (all cycles)" section directly (concern 1), add an explicit sidecar-mkdir requirement
(concern 2), and add a per-hook-guard requirement to AC10 (concern 3) before Cycle 1 starts.
