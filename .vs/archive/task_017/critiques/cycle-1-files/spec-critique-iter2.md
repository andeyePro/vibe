# Spec Critique — task_017 (shared-repos), Iteration 2

Re-review of `/workspace/.vs/spec.md` (revised) against `/workspace/.vs/cycle-1/spec-critique.md`
(iter-1, 11 concerns) plus fresh adversarial reading of the revised text, `/workspace/vibe`,
`/workspace/devcontainer/devcontainer.json`, `/workspace/devcontainer/install-claude-extras.sh`,
`/workspace/smoke-test.py`, and `git log`/`git show` for the cited commit. Design decisions remain
out of bounds; everything below is spec mechanics, internal consistency, or fact-checks against the
actual code the spec asks the Generator to extend.

## Part 1 — Disposition of the 11 iter-1 concerns

1. **Lock/sidecar path pinned two ways — CLOSED.** `grep -n "vibe-rw-lock\|vibe-rw-request"
   spec.md` returns zero hits; the old naming is gone entirely, not left as a dangling second
   mechanism. The "Pinned names and formats (all cycles)" section (spec.md:14-16) now states the
   sidecar path directly (`.vibe-signals/`, `.vibe-signals/rw-lock.d/`, `.vibe-signals/rw-request`)
   as the one and only pin, before any cycle. AC12 (spec.md:41) only cross-references it. A
   Cycle-2 Generator building AC9 never needs to read AC12 to get the right path. Holds.

2. **Nobody creates `.vibe-signals/` before the bind — CLOSED.** The "Signals sidecar" bullet
   (spec.md:14) now explicitly assigns creation to BOTH `vibe repos add` (registration time) and
   the mount-assembly step (defensively, before any bind referencing it), and gives the reason
   (never rely on Docker bind auto-vivification, which can create it root-owned). AC3 (spec.md:26)
   repeats the mount-assembly half. Holds — see Part 2 finding C below for a related but distinct
   residual gap (failure mode when the mkdir itself fails).

3. **EXIT-trap dispatcher under `set -e` — CLOSED.** AC10 (spec.md:36) now states plainly: "The
   dispatcher MUST invoke every registered hook individually guarded (`eval "$hook" || true` or
   equivalent)" and names the exact failure mode being prevented (an unguarded refusing
   `shared_repo_lock_release` silently killing the later-registered clipboard-flush hook). AC11
   (spec.md:37) adds the corresponding functional test ("a REFUSING earlier-registered hook does
   not suppress a later-registered hook in the dispatcher"). Holds.

4. **AC18 subshell-export trap — CLOSED.** AC18 (spec.md:50) now pins the export to "the
   launcher's top-level scope beside the existing `export GITHUB_TOKEN` (vibe ~1660s) — NEVER
   inside `_build_override_config`" and cites the subshell comment. Verified against the actual
   file: `export GITHUB_TOKEN` is at vibe:1663 (matches "~1660s"), and the cited comment ("Exports
   from inside `$(...)` die with the subshell") is at vibe:1691-1696 verbatim, immediately above
   `OVERRIDE_CONFIG=$(_build_override_config "$WORKSPACE")` at vibe:1700. Citation is accurate, not
   just plausible-sounding. Holds.

5. **AC6 presupposing a nonexistent safe.directory precedent — CLOSED.** AC6 (spec.md:29) now
   states directly "there is NO existing safe.directory mechanism in this codebase to mirror
   (verified...)" and specifies the exact command (`git config --global --add safe.directory
   /repos/<name>`, literal per-repo, no wildcard, de-duplicated). No more "find where /workspace
   gets its treatment" scavenger hunt. Holds as far as it goes — see Part 2 finding A for a new
   timing problem in the *mechanism* this AC now specifies (install-claude-extras reading the
   manifest).

6. **Gitignore-additions-to-shared-checkout has no owning AC — PARTIALLY CLOSED, see Part 2
   finding D.** The pin section now names both owners explicitly (spec.md:18: `ensure_project_
   gitignore`'s managed block, AND `vibe repos add` directly ensuring it in the shared checkout at
   registration). That's real progress over iter-1 (which had literally nobody assigned). But
   neither AC1 (which implements `vibe repos add`) nor AC7 (Cycle 1's gate, "smoke-test additions
   for AC1-AC5") repeats or names this as a specific deliverable/test target — a Tester reading
   AC7's generic gate language has no explicit prompt to write a test asserting the shared
   checkout's `.gitignore` actually gained the entry. Downgraded from BLOCKING (iter-1) to MEDIUM
   because the requirement is at least stated with a concrete mechanism in the all-cycles pin,
   which every cycle's Generator is expected to read before touching AC1 — but it's still an
   orphaned requirement relative to the doc's own gate structure.

7. **Cross-cycle mount-triple-count assumption — CLOSED.** AC3 (spec.md:26) ends with "Cycle-1
   Testers must NOT assert one-mount-per-repo exclusivity; each shared repo contributes TWO bind
   triples (code + sidecar) from C1 onward." Explicit and in the right place (the AC whose Tester
   would otherwise write the offending assertion). Holds.

8. **AC13 bell assumption — CLOSED.** AC13 (spec.md:42) now says the `\a` bell is
   "BEST-EFFORT/experimental... no test asserts terminal behaviour... if it rings per-repaint or is
   stripped, drop the byte in the same commit without failing the AC." Converts the unverified
   assumption into an explicitly non-blocking, self-correcting requirement. Holds.

9. **Provenance error (task_016 fixtures) — CLOSED and verified against git.** AC13 now cites
   "the statusLine commit ee5cb81" and "`test_vibe_statusline` (smoke-test.py ~6470)". Checked
   directly: `git show ee5cb81` is titled "vibe: statusLine — single-letter model (F/O/S/H) +
   ctx/5h% in every window", dated 2026-07-10, and `smoke-test.py:6470` is exactly
   `def test_vibe_statusline()`. Both citations are correct, not just corrected-sounding. Holds.

10. **AC1 dispatch placement vagueness — CLOSED and verified against git.** AC1 (spec.md:24) now
    pins "a literal `if [ "${1:-}" = "repos" ]` block placed BEFORE `parse_vibe_args "$@"`, exactly
    like the `learn` block at vibe:1401-1405". Checked directly: `if [ "${1:-}" = "learn" ]; then`
    is at vibe:1401, and the block's `exit $?` safety net is at vibe:1404, closing at 1405 — the
    citation is exact. Holds.

11. **Credential-helper attack list not exhaustive — CLOSED.** AC16 (spec.md:48) now includes "a
    trailing-slash-only path" and "traversal segments like `owner/../other/repo`, and
    embedded-newline/injection strings in any credential-protocol stdin field" alongside the
    original five. All iter-1-requested additions are present verbatim. Holds.

**Summary: 9 of 11 fully closed and independently re-verified against the actual codebase (not
just re-read against the spec's own prose); concern 6 is meaningfully improved but not fully
closed (see finding D below); concern 2 is closed for the "who creates the dir" question but a
sibling question (what happens when creation fails) is newly exposed — see finding C.**

## Part 2 — New problems found in the revised text

### BLOCKING

**A. AC5's manifest-write ordering pin is relative to the wrong anchor — it doesn't guarantee the
manifest is current before `install-claude-extras.sh` (AC6's whole mechanism) reads it.**

AC6's new, concrete mechanism (closing concern 5) is: "install-claude-extras.sh (runs every
container start) reads the runtime manifest and runs `git config --global --add safe.directory
/repos/<name>`..." — this is correct in isolation, but it depends entirely on the manifest file
(`/workspace/.vibe/shared-repos.manifest`) already reflecting the CURRENT launch's mount set by the
time `install-claude-extras.sh` executes.

`install-claude-extras.sh` runs via `postStartCommand`
(`devcontainer/devcontainer.json:61`), which fires as part of the `devcontainer up` call — verified
at `vibe:1769` (`if ! devcontainer "${UP_ARGS[@]}"; then`). AC5 (spec.md:28) pins the manifest write
as happening "before `launch_claude_supervised` runs" — verified that `launch_claude_supervised` is
first invoked at `vibe:1886`, i.e. **117 lines after** `devcontainer up` at `vibe:1769`. AC5's own
anchor point permits (and, read literally, invites) placing the manifest-write code anywhere in
that 117-line span — which is entirely AFTER `devcontainer up`/postStartCommand has already run and
already read whatever the manifest contained from the PREVIOUS launch (or nothing, on first use).

Consequence: on the exact critical path AC1 itself calls out — "Both `add` and `remove` end by
noting a relaunch is needed" — the FIRST relaunch after `vibe repos add` is precisely the moment
`install-claude-extras.sh` reads a manifest that is one launch stale (missing the just-added repo),
so no `safe.directory` entry gets added for it, and the user hits raw "detected dubious ownership"
git errors inside `/repos/<name>` — the exact friction AC6 exists to prevent. This isn't a one-off:
because the manifest is only ever updated relative to `launch_claude_supervised` (always after
`devcontainer up` in the current script structure), this is a **permanent one-launch lag on every
launch**, not a first-use-only edge case, unless the write is explicitly pinned to happen before
line 1769.

Fix: AC5 should anchor the manifest write to "before the `devcontainer up` invocation (`vibe:1769`
today)", not to `launch_claude_supervised`. The natural spot is right alongside
`OVERRIDE_CONFIG=$(_build_override_config "$WORKSPACE")` at `vibe:1700` (same launch, same resolved
repo set, safely before `devcontainer up`) — note this is a plain top-level statement, not inside
the `$(...)` subshell, so it does not fall into the same trap as concern 4/AC18.

### MEDIUM

**B. A shared-repo slug whose basename is exactly `.signals` collides with the reserved sidecar
mount namespace, and nothing rejects it.**

The slug charset is `[A-Za-z0-9._-]+/[A-Za-z0-9._-]+` (spec.md:11) — `.` is explicitly permitted,
so `owner/.signals` is a syntactically valid, declarable slug. Its mount point per the "Mount
point" bullet (spec.md:13) would be `/repos/.signals` — but `/repos/.signals/` is *also* the fixed,
reserved parent directory holding every repo's sidecar (`/repos/.signals/<name>/`, spec.md:14).
The existing collision check ("Collisions between two slugs with the same basename are rejected at
`vibe repos add` time") only guards against two *configured* slugs sharing a basename — it says
nothing about a single slug's basename colliding with this one hardcoded reserved name. The result
would be a code-mount bind target and the sidecar-parent bind target both resolving to
`/repos/.signals`, which is either a Docker mount-target conflict at container-creation time or one
silently shadowing the other, depending on ordering — neither outcome is a clean, named failure
mode the way AC1's "one-line reason" validation-failure discipline requires everywhere else.
(Side note, not a bug: default bash globbing without `dotglob` means `${VIBE_REPOS_DIR:-/repos}/*/`
— the statusLine/fragment scanning pattern from spec.md:20 — correctly skips `.signals` on its own,
so that particular half of the worry is already fine; the actual gap is purely the missing
reservation check at `vibe repos add` time.)

Fix: add one clause to the "Mount point" bullet or AC1: reject any slug whose basename equals the
literal reserved name `signals` prefixed with `.` (i.e. `.signals`) at `vibe repos add` time, same
enforcement point as the existing basename-collision check.

**C. No pinned failure mode for a shared checkout whose parent is read-only or an unreachable
network volume when the sidecar `mkdir -p` fails.**

Concern 2 (now closed) assigns `.vibe-signals/` creation to both `vibe repos add` and mount
assembly, but neither AC1 nor AC3 says what happens when that `mkdir -p` itself fails — e.g. the
registered checkout path is on a read-only mount, an unmounted/detached network share, or owned by
another uid. `vibe` runs under `set -euo pipefail` throughout; AC1 promises "All three [add/remove/
list] exit non-zero on validation failure with a one-line reason" for validation failures, but a
bare `mkdir -p` failure inside `vibe repos add` (after the `.git`-presence validation has already
*passed*) is not itself framed as a "validation failure" anywhere in AC1's text, so it's ambiguous
whether the Generator is expected to catch and re-frame it (one-line reason) or let it raw-abort
under `set -e`. More concerning: at mount-assembly time, the same `mkdir -p` runs *inside*
`_build_override_config`, which builds the override config for potentially several shared repos in
one invocation per launch — if one repo's sidecar directory is unwritable, an unguarded failure
there would abort the whole function under `set -e`, taking down mount assembly for every OTHER
already-resolved, healthy shared repo in that same launch, not just the broken one. AC3's existing
"Registered-but-broken" bucket (path missing/not a git repo/token absent → skip + header warning)
is the right shape for this but doesn't currently list "sidecar directory not creatable" as a
qualifying reason.

Fix: add "sidecar directory not creatable (permission denied / read-only fs)" as an explicit
BROKEN-state reason in AC3, guarded (`|| true`-style) so one bad sidecar doesn't abort assembly for
siblings, and require `vibe repos add` to catch the same failure at registration time with a
one-line reason rather than a raw shell abort.

### LOW

**D. (Cross-reference to Part 1, concern 6.) Consider folding one sentence of the gitignore
dual-owner requirement directly into AC1's own bullet** — e.g. "...and ensures `.vibe-signals/` is
gitignored in the shared checkout" appended to the existing "writes the registry entry, appends the
declaration line..." clause — so the requirement survives a Generator/Tester pair that works from
AC1's bullet text in isolation and never re-opens the all-cycles pin section while implementing it.
Cheap, and removes the last bit of ambiguity noted in finding on concern 6 above.

## Verdict

**revise**

9 of 11 iter-1 concerns are fully closed and independently re-verified against the real codebase
(line numbers, commit hash, and file citations all check out — this is a good sign for how the
Planner is patching, not just rewording). Concern 6 is meaningfully improved but not fully closed.
Recommend one more pass before Cycle 1 starts, fixing finding A (BLOCKING — pin the manifest write
to before `devcontainer up`/`vibe:1769`, not before `launch_claude_supervised`) plus, ideally in the
same pass, findings B and C (both MEDIUM, both cheap one-clause fixes) and D (LOW, one sentence).
None of these require re-litigating the settled design — all are spec-mechanics/ordering pins, the
same category as the 11 iter-1 concerns.
