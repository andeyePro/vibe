# Spec — task_015: auto-recreate containers built from a superseded image

**Revised after Spec Critic iter 1** (closed 3 BLOCKING + 6 MEDIUM/LOW).
Key changes: split the logic into a pure decision function (testable above the
guard) + a docker-touching detector; mandated a SIGPIPE-safe bash pattern;
normalised both image IDs to kill the containerd/classic digest-format
false-positive; re-mapped each AC to harness-tested vs inspection/manual.

## Task summary

The `vibe` launcher rebuilds the shared `vibe-dev:latest` image when any file
under `devcontainer/` is newer than the global `~/.vibe/.image-built` marker,
and passes `--remove-existing-container` to `devcontainer up` **only** when
`REBUILD=true` (vibe:1134). Because the marker is global across all projects,
when project A triggers a rebuild only A's container is recreated. Every other
project keeps running the container it was first created with, built from a now
superseded image. `devcontainer up` reuses an existing container as-is whenever
it succeeds, so those projects silently drift onto a stale container until they
happen to trigger their own rebuild. Observed failure: a stale container's
rootfs predates the current claude-code install, so the launcher's
`env … claude …` exec (vibe:1194) dies with `env: 'claude': No such file or
directory` even though the image is current and healthy.

The fix detects, before `devcontainer up`, whether the existing container for
the current workspace was created from a different image than the current
`vibe-dev:latest`, and adds `--remove-existing-container` to the up args when it
was — so a drifted container is recreated from the current image automatically,
with no `--rebuild` needed.

## Architecture & testability (load-bearing)

`smoke-test.py` unit-tests `vibe` helpers by sourcing the script with
`VIBE_SOURCE_ONLY=1`, which `return`s at vibe:896 before any launch-path code
runs (see the pattern at smoke-test.py:143-150, 648-660, and the vibe comment at
347-348). Therefore **only code defined above the guard is harness-testable.**
The launch path that assembles `UP_ARGS` and calls `devcontainer up`
(vibe:1128-1152) is below the guard and is NOT reachable from the harness.

To make the decision logic testable, split it into TWO functions, both defined
**above the `VIBE_SOURCE_ONLY` guard**, near the other helpers:

### Function A — `image_drift_needs_recreate <workspace> <image_tag>` (docker-touching)

- **Inputs:** `$1` = workspace path (the devcontainer `local_folder` label
  value), `$2` = image tag (e.g. `vibe-dev:latest`). Both args are always
  supplied by the caller; missing-arg call forms are not supported.
- **Output:** echoes `1` (and nothing else) on **stdout** when an existing
  container for the workspace was created from an image whose normalised ID
  differs from the current `$2` image's normalised ID; echoes nothing
  otherwise. The function MUST NOT write anything else to stdout; any
  diagnostic goes to stderr (so the caller's `$(...)` capture is clean).
- **Lookups, in order, each fail-safe (see mandated pattern below):**
  1. Container id: `docker ps -aq --filter "label=devcontainer.local_folder=$1"`.
     Take the **first line only** without a `head` pipe (see mandated pattern).
     Empty → echo nothing, return (no container to recreate).
  2. Container's image reference: `docker inspect --format '{{.Image}}' <cid>`.
     Empty → echo nothing, return (anomalous — can't determine).
  3. Current image's canonical id:
     `docker image inspect --format '{{.Id}}' "$2"`. Empty → echo nothing,
     return (no current image to compare against or recreate from — the build
     step that precedes this in the launcher should have produced it, so an
     empty result here is an anomaly, not drift).
  4. Normalise the container's image reference (from step 2) to a canonical
     config id: `docker image inspect --format '{{.Id}}' <ref>`.
     - **Empty / non-zero → emit `1`** (the image that created this container is
       no longer resolvable in the local store — pruned or superseded — which
       IS drift; recreating from the current image is correct). This branch is
       what resolves the otherwise-contradictory "deleted source image" case.
     - Non-empty → continue.
  5. Emit `1` when the step-4 normalised container id differs from the step-3
     current id; otherwise echo nothing.
- **Why normalise (step 4):** on classic Docker `{{.Image}}` on a container and
  `{{.Id}}` on a tag are both the image **config** digest and compare directly;
  but with Docker Desktop's containerd image store `{{.Image}}` can be a
  *manifest* digest while `{{.Id}}` is the *config* digest, so a direct compare
  would report "drifted" on a container that is in fact current — causing the
  container to be recreated on **every** launch. Re-resolving the container's
  image reference through `docker image inspect --format '{{.Id}}'` yields the
  config id in both store backends, so a current container compares equal. The
  one case where this normalisation *fails* (the container's source image was
  deleted) is deliberately treated as drift (step 4, emit `1`), not a no-op —
  so the detector never keeps a container whose underlying image has vanished,
  staying consistent with the stated stance that false-negative reuse is the
  bug being killed.

### Function B — `remove_existing_flag <rebuild_bool> <drift_marker>` (pure, no docker)

- **Inputs:** `$1` = the `REBUILD` value (`true`/`false`), `$2` = the marker
  emitted by Function A (`1` or empty).
- **Output:** echoes the single token `--remove-existing-container` when
  `$1` is `true` OR `$2` is non-empty; echoes nothing otherwise. It echoes the
  token **at most once** regardless of both inputs being set — this is what
  guarantees AC4's "exactly once".
- This function exists so the idempotency rule is a provable property of a pure,
  docker-free function the harness can exercise directly.

### Launch-path wiring (below the guard — inspection + MANUAL-TESTS only)

Replace the current vibe:1133-1134 lines so that, after `UP_BASE_ARGS` is built,
the launch path calls the two helpers and appends the flag at most once. Sketch
(Generator may adjust naming/locals to satisfy shellcheck):

```sh
UP_ARGS=("${UP_BASE_ARGS[@]}")
drift_marker="$(image_drift_needs_recreate "$WORKSPACE" "$IMAGE_TAG")"
extra_flag="$(remove_existing_flag "$REBUILD" "$drift_marker")"
[ -n "$extra_flag" ] && UP_ARGS+=("$extra_flag")
```

When the flag is added because of drift (not `--rebuild`), print one status line
to the user, worded distinctly from the partial-state-retry message — e.g.
`image moved on since this project's container was built — recreating it.`

The partial-state retry at vibe:1147 intentionally uses `UP_BASE_ARGS` (not
`UP_ARGS`) and already appends `--remove-existing-container` itself; the
drift flag therefore neither needs to nor should be threaded through the retry
path. Leave the retry block byte-for-byte unchanged except for its position.

## Mandated SIGPIPE/`set -e`-safe pattern (AC5)

The launcher runs under `set -euo pipefail` (vibe:33). The detector MUST follow
these rules; the Generator may not substitute a `| head` pipeline:

- **No `head` pipe** for the first container id. Capture all ids, then take the
  first line with parameter expansion:
  ```sh
  local cids cid
  cids=$(docker ps -aq --filter "label=devcontainer.local_folder=$1" 2>/dev/null) || cids=""
  cid="${cids%%$'\n'*}"
  ```
  This avoids `docker ps` receiving SIGPIPE (exit 141) when `head` closes the
  pipe, which `pipefail` would otherwise propagate.
- **Declare locals first, assign on a separate line** with `|| fallback=""`.
  Never `local x=$(cmd)` — the `local` builtin's own exit status masks the
  command-substitution failure and defeats the guard.
- Every `docker` invocation gets `2>/dev/null` and a `|| <var>=""` fallback so a
  non-zero exit (docker absent, image/tag absent, daemon down) never aborts the
  script and always degrades to a defined verdict.

**On errexit-safety of `var=$(cmd 2>/dev/null) || var=""`:** this is correct and
proven, not a theoretical risk. The `cmd || fallback` form exempts `cmd` from
`set -e` back to bash 3.2 (the version `/bin/bash` resolves to on the macOS host
that runs this launcher — `vibe`'s shebang is `#!/bin/bash`). `vibe` already
uses this exact idiom under `set -euo pipefail` in shipped code at lines 119,
191, and 619, so it is verified in the production environment. Do NOT replace it
with a tmpfile or `set +e` subshell — those add complexity without fixing a real
bug. The trap to avoid is only the `local x=$(cmd)` masking form (covered above),
not the separate-line `||` form.

## Acceptance criteria

Each AC is tagged **[harness]** (mechanically tested in smoke-test.py via sourced
helpers + stubbed `docker`, or pure-function call, or source grep) or
**[inspection/manual]** (verified by reading the diff and/or in MANUAL-TESTS.md,
because the code is below the source-guard and unreachable from the harness).

1. **[harness]** No container → no-op. `image_drift_needs_recreate` with a
   `docker ps` stub returning empty emits nothing.
2. **[harness]** Matching image → no-op. With stubs where the container's
   normalised image id equals the tag's id, the function emits nothing.
3. **[harness]** Drifted image → marker. With stubs where the two normalised ids
   differ, the function emits `1`. (The launch-path append that consumes this
   marker is AC's inspection half — see AC11.)
4. **[harness]** Idempotent flag. `remove_existing_flag` truth table:
   `(true, "1")`→one token, `(true, "")`→one token, `(false, "1")`→one token,
   `(false, "")`→empty. Never two tokens.
5. **[harness]** Fail-safe under `set -euo pipefail`. Sourcing `vibe` under
   `set -euo pipefail` and calling `image_drift_needs_recreate` does not abort
   the shell, and yields the specified verdict, for each stub scenario:
   - (a) every `docker` call fails (binary missing / daemon down): no container
     id obtainable → **emit nothing**.
   - (b) `docker ps` returns an id but `docker inspect` (`{{.Image}}`) is
     empty / non-zero → **emit nothing** (anomalous, can't determine).
   - (c) `docker ps` + `docker inspect` succeed, but `docker image inspect` on
     the **current tag** (`$2`, step 3) is empty / non-zero → **emit nothing**
     (no current image to recreate from).
   - (d) `docker ps` + `docker inspect` succeed and the current tag resolves,
     but `docker image inspect` on the **container's image reference** (step 4)
     is empty / non-zero — its source image was pruned → **emit `1`** (drift).
   AC5 has two halves: (i) no scenario aborts under `set -euo pipefail`, and
   (ii) each produces the verdict above. Both are asserted.
6. **[harness]** Multiple matching containers tolerated. With a `docker ps` stub
   returning several ids (multiple lines), the function inspects the first line
   only and returns a well-defined emit/no-emit decision (no crash, no
   multi-line comparison).
7. **[inspection]** Retry preserved. The partial-state retry block
   (the `if ! devcontainer "${UP_ARGS[@]}"` … `--remove-existing-container`
   path, currently vibe:1136-1152) is unchanged in behaviour and still present,
   still using `UP_BASE_ARGS` on the retry call. Verified by reading the diff;
   a structural grep in smoke-test.py MAY assert the retry block's key line
   still exists, but behaviour is inspection-verified.
8. **[harness]** Comment present. The `vibe` source contains a comment line (a
   line whose first non-space character is `#`) containing the substring `drift`
   or `superseded`, documenting the new trigger so the three
   `--remove-existing-container` triggers (`--rebuild`, drift, partial-state
   retry) are distinguishable. Tested by a file-wide source grep — spatial
   proximity to the call site is not required (avoids an unmeasurable "near").
9. **[harness]** shellcheck clean. `python3 code-check.py` passes with no new
   findings over `vibe` and all `.sh` files.
10. **[harness]** Smoke tests pass. `python3 smoke-test.py` passes — existing
    tests plus the new tests for AC1-AC6 and AC8.
11. **[inspection/manual]** Launch-path append wiring. The below-guard wiring
    appends `--remove-existing-container` to `UP_ARGS` when (and only when)
    `remove_existing_flag` returns the token, and prints a distinct status line
    on a drift-triggered recreate. Verified by reading the diff and by the
    MANUAL-TESTS end-to-end step.

## Out of scope (do NOT build / change)

- The firewall (`init-firewall.sh`), tool-call hooks (`guard-bash.sh`,
  `guard-fs.sh`, `settings.local.json`), credential/auth paths, or SSH setup.
  Do not weaken either backstop.
- The override-config builder (`_learning_build_override_config`) and the
  learning-library machinery.
- The image-rebuild / staleness logic (vibe:993-1020) and the global
  `IMAGE_MARKER` mechanism — this task changes only whether a drifted
  *container* is recreated, not *when the image is rebuilt*.
- `parse_vibe_args` and the flag set — no new user-facing flags.
- The `env … claude …` exec line (vibe:1194).
- The partial-state retry block's behaviour (may move position, must not change
  behaviour; do NOT thread the drift flag through it).
- Any attempt to "normalise away" a legitimate drift by canonicalising digests
  beyond the single `docker image inspect` re-resolution specified above. The
  accepted stance is: a false-positive recreate (recreating a container that was
  actually fine) is acceptable; a false-negative reuse (keeping a stale
  container) is the bug being killed. Do not add defensive equality logic that
  could turn into a false-negative path.
- No new external dependencies; only `docker`, already required.

## Test location

`smoke-test.py` (repo convention — no `tests/` dir; `code-check.py` +
`smoke-test.py` at repo root are the suite). Tester adds test functions here,
exercising the two extracted helpers via the existing `VIBE_SOURCE_ONLY=1`
source-and-call pattern with `docker` stubbed. Stub mechanism: define a
`docker()` shell function in the sourced bash snippet before calling the helper
(a shell function shadows PATH lookup), or place a fake `docker` executable
first on `PATH`. The `docker()` stub branches on its sub-command — `$1` is `ps`
for `docker ps`, `inspect` for `docker inspect`, and `image` for `docker image
inspect`. For the two `docker image inspect` calls (step 3 on the tag, step 4 on
the container ref), distinguish them by the **target argument** (the tag `$2`
the helper was called with vs the container's image ref) so AC5(c) and AC5(d)
can be driven independently. Illustrative skeleton (Tester adapts; not
prescriptive code):

```sh
docker() {
  case "$1" in
    ps)      printf '%s\n' "$STUB_PS_IDS"; return "$STUB_PS_RC" ;;
    inspect) printf '%s\n' "$STUB_CREF";   return "$STUB_CREF_RC" ;;
    image)   # docker image inspect <target>; last arg is the target
             case "${@: -1}" in
               "$STUB_TAG") printf '%s\n' "$STUB_TAG_ID"; return "$STUB_TAG_RC" ;;
               *)           printf '%s\n' "$STUB_REF_ID"; return "$STUB_REF_RC" ;;
             esac ;;
  esac
}
```

`remove_existing_flag` needs no stub (pure). AC8 is a `grep` over the `vibe`
source text. (`${@: -1}` and the stub run inside this container's bash 5.x test
process — fine for tests; the helper itself stays bash-3.2-portable for the
macOS host.) **Tests are immutable once committed.**

## Manual verification (MANUAL-TESTS.md — not harness-runnable)

The harness has no docker, so the end-to-end recreate and AC7/AC11 are verified
on the maintainer's real Docker. Add a MANUAL-TESTS.md checklist item:

1. Build the image; launch project A so its container exists.
2. Force the image to move on (bump a `devcontainer/` file, or `vibe --rebuild`
   from a *different* project), so `vibe-dev:latest` now differs from A's
   container's image.
3. Launch project A again **with no flags**. Expect: A's container is recreated
   (status line about the image having moved on), and claude starts.
4. **Containerd false-positive guard:** launch project A a second time
   immediately, no image change. Expect: the container is **reused**, NOT
   recreated (confirms the normalised-id compare reports equal on the current
   image under whichever image store Docker Desktop uses).

## Notes for the Generator (not ACs)

- Add a `CHANGELOG.md` entry under a **2026-05-27** date heading (newest at top),
  describing what changed and why, in the same commit as the code change, per
  the repo's TODO/CHANGELOG convention. Note in it that the MANUAL-TESTS
  auto-recreate path (incl. the containerd false-positive guard) should be
  exercised before shipping.

## Proposed budget

`2 cycles` — one extracted-helper pair + a few-line call site + new tests. One
cycle should suffice; the second is buffer for AC5 `set -euo pipefail`
robustness, still the likeliest place a first attempt slips.
