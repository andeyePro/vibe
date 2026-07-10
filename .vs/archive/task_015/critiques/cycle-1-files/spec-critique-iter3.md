# Spec critique iter 3 — task_015: auto-recreate containers built from a superseded image

Audited against `/workspace/.vs/spec.md` (iter 3) and `/workspace/vibe` (lines 1, 33, 119, 191, 619).

---

## Status of iter-2 concerns

- **NEW-1 (BLOCKING — `var=$(cmd) || var=""` unsafe in bash <5):** `closed (correctly rejected)`.
- **NEW-2 (MEDIUM — deleted-image false-negative):** `closed`.
- **NEW-3 (MEDIUM/LOW — stub branching form):** `closed`.
- **NEW-5 (LOW — AC8 "near"):** `closed`.

---

## Detailed evaluation

### NEW-1

The Planner's rebuttal is technically sound.

The iter-2 concern alleged that `cids=$(docker ps … 2>/dev/null) || cids=""` might abort under `set -e` in bash <5 because the `||` might be treated as guarding the assignment-as-a-whole rather than exempting the command substitution inside it. I checked all three cited lines in `vibe`:

- **Line 119:** `url=$(git remote get-url origin 2>/dev/null) || return 1`
- **Line 191:** `gh_user=$(gh api user --jq '.login' 2>/dev/null) || { ... }`
- **Line 619:** `remotes=$(git -C "$lib_path" remote 2>/dev/null) || { ... }`

All three are structurally identical to the mandated pattern: a simple assignment containing a command substitution, followed by `||` with a fallback. All run under `set -euo pipefail` (line 33). The `||`-operand exemption from `set -e` applies to the entire left-hand side of a `||` list — including a command substitution on the right of `=` — and has been POSIX-specified behaviour stable since bash 3.2. This is not a theoretical claim; it is what vibe ships and runs on the macOS host today.

The iter-2 concern cited "bash BZ#15430 / POSIX ambiguity" but produced no concrete bash version or reproduction case where `x=$(cmd) || x=""` actually aborts. The `local x=$(cmd)` masking trap is real and distinct — the spec's "Declare locals first" bullet correctly excludes it. The separate-line `||` assignment is not that trap. NEW-1 is correctly rejected.

The spec's rebuttal note (lines 140-148) is precise, cites the right distinction, and instructs the Generator not to substitute a tmpfile or `set +e` subshell. No further action needed.

### NEW-2

Fully resolved. Step 4 in Function A now explicitly reads: "Empty / non-zero → emit `1` (the image that created this container is no longer resolvable in the local store — pruned or superseded — which IS drift; recreating from the current image is correct)." The "Why normalise (step 4)" paragraph names this case explicitly and explains it is consistent with the stated stance that false-negative reuse is the bug being killed. AC5(d) in the acceptance criteria aligns: `docker image inspect` on the container's image reference returning empty/non-zero → emit `1`.

The step numbers are internally consistent: the prose references ("step 3", "step 4", "Why normalise (step 4)") match the ordered lookup list (1 = container id, 2 = container image ref, 3 = current tag id, 4 = normalise container ref). No contradiction remains between the Out-of-scope stance and the step-4 emit-1 behaviour — the Out-of-scope section says "do not add defensive equality logic that could turn into a false-negative path", which is compatible with step 4 treating a missing source image as drift rather than a no-op.

### NEW-3

Resolved. The Test location section now provides a concrete skeleton stub that branches on `$1` (`ps` / `inspect` / `image`) and, within the `image` branch, on `${@: -1}` (the last argument — the target) to distinguish step-3 (tag) from step-4 (container ref) calls. This is the correct branching: for `docker image inspect <target>`, `$1` is `image`, `$2` is `inspect`, and `${@: -1}` is the target — the stub correctly routes on the sub-command via `$1` and on the target via `${@: -1}`. The spec also notes `${@: -1}` is used inside the test process (bash 5.x in-container), while the helper itself stays bash-3.2-portable. Generator and Tester will agree on the stub form.

One small observation: `$1` for `docker image inspect` is `image`, not `inspect` — the stub routes the whole `image` sub-family through the `image)` arm and ignores `$2` (`inspect`). This is correct and unambiguous: vibe only ever calls `docker image inspect`, not any other `docker image *` sub-command, so no disambiguation is needed within the `image)` arm beyond the target argument.

### NEW-5

Closed. AC8 now specifies "a file-wide source grep" for a comment line containing `drift` or `superseded`, with explicit note that "spatial proximity to the call site is not required (avoids an unmeasurable 'near')". The `near` qualifier is gone. Mechanically testable.

---

## Final consistency sweep

**Step-number references:** The Function A lookup list numbers 1-5 (with step 5 being the final emit comparison). Prose references say "step 3", "step 4", "Why normalise (step 4)" — these all resolve correctly to the intended steps. AC5(c) maps to step 3 (current tag id), AC5(d) maps to step 4 (normalise container ref). Consistent.

**AC tagging:** All ACs are correctly tagged. AC1-AC6, AC8-AC10 are `[harness]`. AC7 and AC11 are `[inspection]` / `[inspection/manual]`. No AC claims `[harness]` while requiring below-guard code or real docker.

**No new internal contradictions introduced:** The Out-of-scope stance ("false-positive recreate is acceptable; false-negative reuse is the bug") is now fully consistent with step-4's emit-1 on missing source image. The "Why normalise" paragraph and the Out-of-scope section reinforce each other rather than contradict.

**Stub note parenthetical:** The spec notes `${@: -1}` runs in the in-container bash 5.x test process. This is accurate and relevant — `${@: -1}` is not bash-3.2-portable (it requires bash 4.2+), so calling it out for the test process only (not the helper) is correct hygiene.

**No new concerns.** No BLOCKING or MEDIUM issues were introduced by the iter-3 revisions.

---

## Verdict

pass
