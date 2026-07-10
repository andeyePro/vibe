# Spec critique iter 2 — task_015: auto-recreate containers built from a superseded image

Audited against `/workspace/.vs/spec.md` (revised), `/workspace/.vs/cycle-1/spec-critique.md` (iter-1 concerns), and the vibe source at `/workspace/vibe`.

---

## Status of prior concerns

1. **BLOCKING-1 (AC4 not harness-testable):** `closed` — AC4 is now a pure-function truth table on `remove_existing_flag`; all four rows are exercisable without docker or the launch path. The "exactly once" guarantee is now a property of the pure function, not of `UP_ARGS` assembly below the guard.

2. **BLOCKING-2 (AC7 below-guard):** `closed` — AC7 is now tagged `[inspection]`; the spec notes a structural grep MAY assist but behaviour is inspection-verified. Split is explicit and non-contradictory.

3. **BLOCKING-3 (SIGPIPE/pipefail):** `partially closed` — see NEW CONCERN 1 below for a surviving trap in the mandated pattern.

4. **MEDIUM-4 (containerd digest mismatch):** `closed` — the normalisation step (re-resolving both sides through `docker image inspect --format '{{.Id}}'`) is specified with a rationale paragraph; the accepted false-positive stance is now explicit.

5. **MEDIUM-5 (AC5 sub-cases conflated):** `closed` — AC5 now enumerates (a)–(d) individually with distinct stub sequences described; the test-location section tells the Generator to branch the stub on `ps` vs `inspect` vs `image inspect`.

6. **MEDIUM-6 (AC3 split not explicit):** `closed` — AC3 is now tagged `[harness]` for the emit decision; AC11 is tagged `[inspection/manual]` for the launch-path append. The split is stated.

7. **LOW-7 (stdout channel conflict):** `closed` — the spec now states "The function MUST NOT write anything else to stdout; any diagnostic goes to stderr."

8. **LOW-8 (UP_BASE_ARGS vs UP_ARGS in retry):** `closed` — the spec explicitly calls out that the retry "intentionally uses `UP_BASE_ARGS` (not `UP_ARGS`)" and instructs the Generator to leave the retry block byte-for-byte unchanged except for position.

9. **LOW-9 (AC8 subjective):** `closed` — AC8 now specifies a mechanical grep criterion: the source must contain substring `drift` or `superseded` in a comment near the drift-check call; AC10 confirms it is harness-tested by source grep.

---

## New concerns

### NEW-1 — BLOCKING — `cids=$(…) || cids=""` is NOT safe under `set -euo pipefail` in all bash versions

The mandated pattern reads:

```sh
local cids cid
cids=$(docker ps -aq --filter "label=devcontainer.local_folder=$1" 2>/dev/null) || cids=""
```

The concern is not about `local` masking the exit status (that trap is correctly avoided by declaring `local cids cid` first and assigning on a separate line). The concern is subtler: **under `set -e`, a command-substitution that exits non-zero on the right-hand side of an assignment is NOT protected by the OR-chain in all bash versions.**

Specifically, in bash 4.x (macOS ships bash 3.2; bash 5.x is typical on Linux but not guaranteed in the container's base image) the rules for when `set -e` fires inside a `$(…)` on the right-hand side of an assignment differ. The assignment `cids=$(docker ps … 2>/dev/null) || cids=""` has two interpretations:

- In bash 5.x: the `||` is visible to `set -e` before the assignment completes; if `docker ps` exits non-zero, the `||` arm fires and `set -e` does not abort. Correct.
- In bash 4.x and 3.2: the assignment operator has lower precedence in the `set -e` machinery; the shell can see the non-zero command-substitution exit status and abort BEFORE the `||` arm is evaluated, because the `||` is treated as part of a list involving the assignment-as-a-whole rather than guarding the substitution. This is bash bug BZ#15430 / POSIX ambiguity.

The vibe container uses the Anthropic Claude Code devcontainer image. The spec does not name the bash version. The spec mandates this exact pattern and explicitly says "The Generator may not substitute a `| head` pipeline", but gives no guidance on the bash version requirement. If the container's bash is < 5.0 and the pattern fails there, the mandated pattern is the source of the bug, not a deviation from it. The Generator follows the spec exactly and ships a script that aborts in production.

**Suggested fix:** the spec should either (a) assert the minimum bash version (e.g. "requires bash ≥ 5.0; the Generator MUST add a version check or accept this as a known constraint"), or (b) mandate the fully defensive alternative that is safe in bash 3.2+:

```sh
local cids cid
cids=""
docker ps -aq --filter "label=devcontainer.local_folder=$1" 2>/dev/null > "$tmpfile" || true
cids=$(cat "$tmpfile")
```

or (c) use a subshell wrapper that overrides `set -e` locally:

```sh
local cids cid
cids=$(set +e; docker ps -aq … 2>/dev/null; true)
```

Without this, BLOCKING-3 is not fully closed.

---

### NEW-2 — MEDIUM — Normalisation introduces a false-negative (stale-container reuse) when the container's image has been deleted from the local store

The normalisation step is:

> `docker image inspect --format '{{.Id}}' <ref>` where `<ref>` is `{{.Image}}` from `docker inspect` on the container.

If the image that created the container has been pruned (`docker image rm`, `docker system prune`), `<ref>` is a digest that no longer exists in the local image store. `docker image inspect <ref>` returns non-zero / empty. The spec says "Empty → echo nothing, return" — i.e. fail-safe = no-recreate.

But in this scenario the container IS stale. Its rootfs was built from a now-deleted (and presumably superseded) image. The fail-safe "echo nothing" verdict keeps the container alive — which is precisely the false-negative reuse bug the task is supposed to kill.

The spec's accepted stance ("a false-positive recreate is acceptable; a false-negative reuse is the bug we're killed") directly conflicts with the normalisation step's behaviour when the container's source image has been deleted.

**Severity: MEDIUM** because this is not an everyday case (pruning images under an active container is unusual) but it is a coherent failure mode that the spec's own stated stance says is the bug being killed. It deserves an explicit scope statement: either "we accept this as a known gap (deleted-image case is out of scope)" or "when normalisation of the container's image reference returns empty, treat as drifted (emit `1`) rather than no-op." The current text does the opposite of the stated stance without acknowledging it.

---

### NEW-3 — MEDIUM — AC5(a) stub ("docker absent / exit 127") cannot be cleanly implemented as a shell function

The test-location section says:

> Stub mechanism: define a `docker()` shell function in the sourced bash snippet before calling the helper.

For sub-case (a) — `docker` absent entirely — the function body needed is one that exits 127 unconditionally (simulating PATH miss). A shell function `docker() { return 127; }` does this for cases where the helper calls `docker ps`. But `docker ps` returning 127 is not the same as docker being absent from PATH: when docker is truly absent, bash emits `command not found` to stderr and the shell variable `$?` is 127, but `2>/dev/null` in the mandated pattern suppresses the stderr noise. The stub `docker() { return 127; }` correctly models the return-code path, but will it model the `2>/dev/null` redirect correctly? Yes — shell function calls honour redirections normally. However:

The detection function calls docker with three different sub-command forms (`ps`, `inspect`, `image inspect`). For AC5(a) ALL calls must return 127. The stub `docker() { return 127; }` does this. For AC5(b)–(d) the stub must return 127 (or empty) for SOME calls and succeed for others. The Generator must branch on `$1`/`$2` to distinguish. This is workable but the spec does not give the branching logic — the Generator must invent it. This is a minor under-specification (the earlier critique raised it at MEDIUM and it was listed as "closed" for enumerating sub-cases, but the test section still leaves the stub branching as an exercise for the Generator).

More concretely: if the Generator writes a stub that branches on `$1` (the docker sub-command), `docker image inspect` will have `$1 = image` and `$2 = inspect`. Some Generators may branch on `"$1 $2"` while others branch on `"$@"`. Neither form is mandated. A Tester may reject a correct stub for using the "wrong" branching form. This is LOW but worth naming.

**Suggested fix:** the spec should show one concrete example stub structure for AC5(b)–(d) (a three-branch `case "$1" in ps) … ;; inspect) … ;; image) … ;; esac` stub) so the Generator and Tester agree on the form.

---

### NEW-4 — LOW — `"${cids%%$'\n'*}"` behaviour when `cids` is empty or contains no newline

The mandated pattern uses:

```sh
cid="${cids%%$'\n'*}"
```

to extract the first line. When `cids` is empty (`docker ps` returns nothing), `${cids%%$'\n'*}` expands to `""` — correct. When `cids` contains one id with no trailing newline (typical for `docker ps -aq` with one match), `${cids%%$'\n'*}` expands to the entire string — correct. When `cids` contains multiple lines, it strips from the first newline — correct.

However, `docker ps -aq` may return ids separated by newlines **with** a trailing newline on the last entry. In that case, for a single-result output of `"abc123\n"`, `${cids%%$'\n'*}` strips the `\n` and everything after it, yielding `"abc123"` — correct. This is fine. No bug here, but it is worth stating the spec is sound on this point (no concern to raise).

**Actual LOW concern:** the spec mandates `local cids cid` as a single declaration. Under `set -u`, if `cid` is declared but never assigned (because `cids` was empty and the function returned early before the `cid=` line), and if the caller somehow references `cid` after the function returns — `set -u` would bite. But since `cid` is a `local` inside the function, it is not visible to the caller. No real trap here. The pattern is sound.

Reclassify: **not a concern**. Included for completeness of the audit trail.

---

### NEW-5 — LOW — AC8 grep scope "near the drift-check call" is undefined

AC8 states the comment must be "near the drift-check call" but does not define "near." A source-level grep for `drift` or `superseded` anywhere in the file would pass even if the comment appeared in a completely unrelated section (e.g. a comment in the image-rebuild staleness block that happens to use the word "superseded"). The word "near" is not mechanically testable without a line-range constraint.

**Suggested fix:** replace "near the drift-check call" with "within N lines of the `image_drift_needs_recreate` call site" (e.g. N=10), or simply accept that a file-wide grep is sufficient for the intent (keeping containers distinguishable doesn't require spatial proximity). If the latter, drop the "near" qualifier to avoid a false Tester rejection.

---

## Verdict

revise

The spec has made genuine progress — six concerns fully closed, significant structural improvements. One BLOCKING remains: the mandated `cids=$(…) || cids=""` SIGPIPE-safe pattern is not demonstrably safe across the bash version range actually present in the container (NEW-1). BLOCKING-3 is partially closed, not fully closed. The normalisation false-negative (NEW-2) is a coherent contradiction of the spec's own stated stance and warrants at least an explicit scope acknowledgment.
