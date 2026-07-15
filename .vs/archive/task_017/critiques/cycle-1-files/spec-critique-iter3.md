# Spec Critique — task_017 (shared-repos), Iteration 3 (closure verification)

Scope: verify the four iter-2 closures against the actual revised spans of `/workspace/.vs/spec.md`
(not just re-read the Planner's changelog claim), re-check the citations that anchor them against
the real `/workspace/vibe`, and scan those same revised spans only for newly-introduced
contradictions. Settled design is out of bounds; no re-litigation attempted.

## Closure 1 — AC5 manifest-write ordering (was iter-2 finding A, BLOCKING)

AC5 (spec.md) now reads: manifest written "immediately after mount assembly and STRICTLY BEFORE
`devcontainer up` (vibe ~1769) — postStart's install-claude-extras.sh consumes it in the SAME
launch for AC6's safe.directory entries; writing it any later hands postStart a one-launch-stale
manifest, which would break exactly the critical path (the relaunch right after `vibe repos add`)."

Verified against the real file, not just the spec's own prose:

- `devcontainer "${UP_ARGS[@]}"` invocation is at `vibe:1769` (`if ! devcontainer
  "${UP_ARGS[@]}"; then`) — citation exact.
- `OVERRIDE_CONFIG=$(_build_override_config "$WORKSPACE")` is at `vibe:1700` — the one and only
  call site of `_build_override_config` (`grep -n "_build_override_config" vibe` shows a single
  invocation), confirmed by reading the function body (`vibe:1212-1277`). So "immediately after
  mount assembly" has one unambiguous home: inside or immediately after this single call, both
  safely before line 1769.
- Exports die inside `$(...)` (the AC18 trap), but a **file write** does not — `_build_override_config`
  already does host-side side effects inside the subshell today (`mkdir -p "$run_dir"` at
  `vibe:1271`, writing `$dst` via `render_devcontainer_with_mounts` at `vibe:1275`) and those
  persist fine across the subshell boundary. Writing the manifest file (as opposed to exporting an
  env var) from inside this same call is therefore not subject to the AC18 trap at all — the two
  ACs are consistent, not competing.
- `launch_claude_supervised` remains at `vibe:1886`, confirming the old (broken) anchor is fully
  retired, not left as an alternate reading.

Genuinely closed. The new anchor is concrete, single-homed, and verified consistent with the
subshell mechanics AC18 separately pins.

## Closure 2 — dot-prefixed basename reservation (was iter-2 finding B, MEDIUM)

Pinned-names "Mount point" bullet now adds: "Repo basenames beginning with `.` are RESERVED (the
`.signals` sidecar namespace lives beside the repo mounts): rejected at `vibe repos add`, and
skipped-with-warning at mount assembly if one appears in a hand-edited declaration. In-container
scanners use the `${VIBE_REPOS_DIR:-/repos}/*/` glob, which never matches dot-dirs — keep it that
way."

This closes the specific collision iter-2 found (`owner/.signals` colliding with the reserved
`/repos/.signals` sidecar-parent path) and does so more conservatively than the minimum fix asked
for — it bans any dot-leading basename, not just the one literal string, at both call sites
(registration validation and a defensive re-check at mount assembly for hand-edited declarations).
Genuinely closed as a requirement.

One residual, non-blocking gap: this new rule isn't echoed into AC1/AC2/AC3's own bullets or into
AC7's test-enumeration list the way the (now-fixed) gitignore requirement was for closure 4 below —
a Tester working strictly from AC2's listed test cases ("valid line, bad slug skipped with warning,
comment/blank skipped, missing files echo nothing, injection strings... rejected, env-name
sanitisation cases") or AC7's explicit list has no direct prompt to write a dot-prefix-rejection
test. This is the same orphaning *shape* iter-1/iter-2 flagged as concern 6, reappearing for a
different requirement — but unlike that case, the rule here has an unambiguous owner and two named
enforcement points already, so nothing is left undefined; it's purely a test-list-completeness nit.
LOW, non-blocking, one-line fix if the Planner wants it (add "dot-prefixed basename rejected" to
AC2's or AC7's test list).

## Closure 3 — sidecar mkdir guard (was iter-2 finding C, MEDIUM)

AC3 now reads: the mount-assembly `mkdir -p` for each resolved checkout's sidecar "is GUARDED — on
failure (read-only or network volume) the repo is demoted to registered-but-broken with reason
`sidecar unwritable`, BOTH its binds are skipped, and assembly continues with sibling repos (never
a `set -e` abort)." This directly answers iter-2's core complaint: one bad sidecar no longer takes
down mount assembly for every other resolved repo in the same launch.

The registration-time half (`vibe repos add`) is also covered: AC1's `shared_repo_ensure_signals`
helper is explicitly "guarded/idempotent," and AC7's gate list requires a test that the helper
"fails soft on an unwritable one." Read together with the pinned-names bullet ("created host-side...
by BOTH `vibe repos add`... and the mount-assembly step (defensively...)"), the design is
self-consistent: a soft failure at registration time is not fatal to `vibe repos add` because
mount-assembly re-attempts the same `mkdir -p` on every launch and has its own named failure state
if it still fails. No gap between the two call sites; both are now guarded, named, and tested.
Genuinely closed.

## Closure 4 — gitignore ownership via named helper (was iter-2 concern 6 / finding D, LOW-MEDIUM)

AC1 now folds the requirement directly into its own bullet: `shared_repo_ensure_signals <checkout>`
is described in AC1's text itself as doing both jobs — "`mkdir -p`s the `.vibe-signals/` sidecar AND
ensures `.vibe-signals/` is gitignored in the shared checkout, both guarded/idempotent." AC7's gate
list now explicitly enumerates the corresponding tests: "`ensure_project_gitignore`'s managed block
contains `.vibe-signals/`; `shared_repo_ensure_signals` creates sidecar + gitignore entry
idempotently in a temp checkout and fails soft on an unwritable one." This is exactly the fix iter-2
proposed (fold one sentence into AC1's own bullet) and closes the orphaning: a Generator/Tester
pair working only from AC1 and AC7's text — never re-opening the pinned-names section — now gets
the full requirement and its test obligations directly. Genuinely closed.

## Scan of the four revised spans for newly-introduced contradictions

- AC5's new anchor vs. AC18's subshell-export trap: checked above — no conflict (file writes vs.
  exports are different hazards).
- Dot-prefix reservation vs. the slug charset (`[A-Za-z0-9._-]+/[A-Za-z0-9._-]+`, which
  syntactically permits a leading dot in the repo-name segment): no contradiction — the new rule is
  an explicit additional semantic check layered on top of the charset, not a charset change, and is
  described as such ("rejected at `vibe repos add`" as a distinct step from parsing).
- Sidecar-guard reason string (`sidecar unwritable`) vs. AC1's registration-time language
  (`guarded/idempotent`, `fails soft`): different call sites, not required to share a literal reason
  string — no contradiction, and the retry design (mount-assembly re-attempts regardless of
  registration-time outcome) makes the two consistent rather than competing.
- `shared_repo_ensure_signals` (AC1) vs. AC3's independent mount-assembly `mkdir -p`: both exist and
  do overlapping work by design (defensive double-creation is explicitly pinned in the
  "Signals sidecar" bullet as intentional, not accidental duplication) — no contradiction.

No new contradictions found beyond the one LOW test-list-completeness nit under closure 2.

## Verdict

**pass**

All four iter-2 closures are genuine: verified not just by re-reading the spec's own prose but by
checking the anchor line numbers and single-call-site claims against the actual `/workspace/vibe`
file (1700/1769/1886, matching iter-2's own verification discipline). The one BLOCKING item from
iter-2 (finding A, manifest staleness) is fully retired with a concrete, single-homed anchor. The
three MEDIUM items are closed with named failure states, dual call-site coverage, and — for three of
the four patches — explicit test-list entries. The single residual observation (dot-prefix rejection
not yet echoed into AC2/AC7's test enumeration) is LOW, non-blocking, and does not leave any
requirement undefined — it is a test-list-completeness nit, not a design gap, and does not warrant
another revise cycle. Cycle 1 may proceed.
