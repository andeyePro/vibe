# Spec critique — task_015: auto-recreate containers built from a superseded image

Audited against `/workspace/.vs/spec.md`, `/workspace/vibe` (lines 33-40, 320-354, 893-896, 993-1020, 1128-1153), and `/workspace/smoke-test.py` (lines 143-150, 648-660).

---

## Concerns

### 1 — BLOCKING — AC4 is not testable via the VIBE_SOURCE_ONLY harness

AC4 asserts "the final `UP_ARGS` contains `--remove-existing-container` exactly once — never duplicated." `UP_ARGS` is assembled in the launch path **below** the `VIBE_SOURCE_ONLY` guard (vibe:1128-1134). `smoke-test.py` sources `vibe` with `VIBE_SOURCE_ONLY=1`, which returns before any launch-path code runs. There is no mechanism to reach the caller that builds `UP_ARGS` via the unit-test harness. The spec's AC10 mandates that smoke-test.py covers AC4, and the test location section lists AC4 as harness-verifiable. This is false — a Generator following the spec literally will write a test that either sources dead launch-path code (syntax error) or misses AC4 entirely, and the Tester cannot satisfy this criterion. Either demote AC4 to MANUAL-TESTS.md, or specify that the launch-path block itself must be extracted above the guard (making it testable), or accept that AC4 is integration-only.

### 2 — BLOCKING — AC7 is similarly below-guard and not harness-testable

AC7 ("retry logic preserved, unchanged in behaviour, still present") describes the partial-state retry block at vibe:1136-1152 — entirely below the guard. It is a structural / code-preservation assertion. The harness cannot observe it. The spec's AC10 does not list AC7 explicitly in the test coverage sentence, but the general "smoke-test.py passes" implies all ACs are covered. Either explicitly mark AC7 as verified-by-inspection/shellcheck (structural grep against the source) or move it to MANUAL-TESTS.md. A Generator who writes a smoke test for AC7 will produce a vacuous test (grep the source file for a string), which passes trivially without proving behaviour.

### 3 — BLOCKING — AC5(d): SIGPIPE / pipefail trap is underspecified and leaves an implementation trap unaddressed

The spec states that case (d) — "the `docker ps … | head` pipeline's producer exiting non-zero" — must be fail-safe. Under `set -o pipefail`, `docker ps -aq --filter … | head -1` causes `docker ps` to receive SIGPIPE (exit status 141) when `head` closes the pipe after reading one line. `pipefail` propagates the non-zero status of any pipeline member. The spec says "guarded so a non-zero exit never aborts" but gives the Generator no guidance on the guard form required — and several natural bash idioms fail here:

- `cid=$(docker ps -aq --filter "label=…" | head -1)` — subshell captures output but under `pipefail` the subshell itself exits 141; `set -e` may abort depending on call context.
- `cid=$(docker ps -aq … | head -1) || true` — `|| true` suppresses the exit code but `local cid=$(…)` swallows exit status via the `local` builtin (the classic `local` + `set -e` trap), giving a false sense of safety.
- A safe pattern exists (`mapfile` + process substitution, or `docker ps -aq … | { head -1; cat >/dev/null; }`, or limiting to `docker ps -aq … --format '{{.ID}}' | awk 'NR==1'` which also SIGPIPEs) but the spec does not name it.

Because this is the highest-probability implementation trap (the spec itself says AC5 is "the likeliest place a first attempt slips"), and because the contract says "guarded" without saying how, the Generator is likely to produce a subtly broken implementation on cycle 1. The spec should either mandate a concrete safe pattern (e.g. use `|| true` on the full pipeline and avoid `local` on the same line) or acknowledge this as an accepted Generator risk, explicitly flagging it for the Tester.

### 4 — MEDIUM — Image ID format: `{{.Image}}` vs `{{.Id}}` are not guaranteed to match across all Docker/BuildKit variants

`docker inspect --format '{{.Image}}'` on a running container returns the image reference the daemon used to create that container's layer stack. In classic Docker (non-containerd snapshotter), this is the image config digest (sha256:…) — the same value `docker image inspect --format '{{.Id}}'` returns for a tag. However, with Docker Desktop's containerd image store enabled (opt-in since Docker 24, default in some newer builds), `.Image` on a container can return a *manifest* digest or a short-form reference, while `.Id` on the image tag returns the config digest. A naive string compare then produces a false positive "drifted" verdict on a container that is actually current — triggering an unnecessary recreate. The spec should acknowledge this risk and state the chosen behaviour: the implied stance ("false-positive recreate is acceptable; false-negative reuse is the bug we're killing") is sound but must be made explicit so a Generator doesn't add a defensive equality check that accidentally becomes a false-negative path, and so a Tester doesn't reject a correct implementation that triggers spurious recreates on containerd-mode Docker. Unaddressed, this is an internal contradiction between the "fail safe toward do not recreate" contract and the real-world ID comparison semantics.

### 5 — MEDIUM — AC5 testability: sub-cases (b), (c), (d) each require a distinct docker stub but the spec conflates them

The test location section specifies "AC5's sub-cases" but lists them as a unit. Sub-cases (a) docker absent, (b) image tag not present, (c) container present but image inspect failing, and (d) SIGPIPE from the ps|head pipeline each require a different docker stub response sequence (no-docker, ps-succeeds-but-image-inspect-fails, inspect-returns-empty, ps-exits-141). A Generator who writes one stub covering "docker fails" will not produce four independently verifiable tests. The Tester then cannot tell which sub-cases are actually guarded. Recommend the spec enumerate the four test cases explicitly with their expected stub behaviour — otherwise AC5 is verifiable in name only.

### 6 — MEDIUM — AC3: "launch path adds `--remove-existing-container`" is not harness-testable as written

AC3 has two parts: (i) helper emits its marker, and (ii) the launch path adds the flag. Part (i) is testable via the helper directly. Part (ii) requires the launch-path code, which is below the guard. The spec's test coverage sentence ("Tests assert the emit/no-emit decision for AC1-AC3") covers only part (i). Part (ii) suffers the same structural gap as AC4 (concern 1). The spec should make this split explicit — part (i) is harness-tested, part (ii) is verified by inspection + MANUAL-TESTS.md — so a Tester does not reject a correct implementation for failing to cover an untestable half-criterion.

### 7 — LOW — Helper contract: stdout channel conflicts with `$(…)` expansion in the caller

The helper emits a marker on stdout. The caller does `$(image_drift_needs_recreate "$WORKSPACE" "$IMAGE_TAG")` to capture it. If the helper ever writes a diagnostic/debug line to stdout (e.g. during an error-recovery path) the caller silently captures that noise as a truthy marker, triggering a spurious recreate. The contract specifies stdout for the signal but does not say "no other stdout" explicitly. This is a LOW risk given the fail-safe contract, but is worth one sentence: "the helper MUST NOT write any other output to stdout; use stderr for diagnostics."

### 8 — LOW — No guidance on what `UP_ARGS` append looks like when drift check fires simultaneously with partial-state retry

AC7 says the retry block is "unchanged in behaviour." The partial-state retry (vibe:1147) calls `devcontainer "${UP_BASE_ARGS[@]}" --remove-existing-container` — using `UP_BASE_ARGS`, not `UP_ARGS`. So the drift-check flag appended to `UP_ARGS` has no effect on the retry call. This is fine behaviourally (recreate is still enforced), but a Generator who tries to "thread" the flag through the retry path will inadvertently alter the retry call signature and break AC7. The spec should note explicitly that the retry at vibe:1147 intentionally uses `UP_BASE_ARGS` (not `UP_ARGS`), and the drift-check flag therefore need not be present on the retry path.

### 9 — LOW — AC8 (distinguishable comments) is subjective and not mechanically verifiable

A test that asserts a comment string exists is trivially satisfied by any literal string. "Distinguishable" is a human-reviewable quality criterion. The spec should either drop AC8 from AC10's coverage scope (marking it review-only), or replace it with a minimal grep assertion ("the source file contains the phrase 'drift' or 'superseded image' in a comment within N lines of the drift-check call") so the Tester has a mechanical hook.

---

## Verdict

revise
