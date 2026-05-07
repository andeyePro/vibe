# Spec Critique - task_014 - iter 1

## Concerns

### BLOCKING (must address before Generator runs)

1. **[AC1 + AC7] cksum fallback cannot produce 40 hex characters.**
   The spec requires the helper echo "exactly 40 hex characters" and mandates
   the `sha1sum | shasum | cksum` fallback ladder. `cksum` produces a decimal
   CRC32, e.g. `3945841790` (10 decimal digits, not hex, not 40 chars). A smoke
   test asserting `len==40 and all-hex` would fail on any system where both
   `sha1sum` and `shasum` are missing. The ladder is copied from
   `_learning_build_override_config` where the cksum output is used only as a
   filename fragment (no length/format assertion), so the original code silently
   tolerates the mismatch - the new AC1 length requirement makes it a hard
   failure. The per-project bind path would also become
   `~/.vibe/projects/3945841790/` (10 chars) not a 40-char hex dir, breaking
   AC7's "exactly 40 hex characters" invariant.
   **Proposed fix:** AC1 should read: "The helper MUST use the same
   `sha1sum | shasum | cksum` fallback ladder. When `sha1sum` or `shasum` is
   available the output is a 40-char lowercase hex string; when only `cksum` is
   available the output is a decimal CRC32 string of variable length. AC1 and
   AC7 MUST NOT assert a fixed length or hex-only character set; they MUST
   assert only that the output is non-empty and stable (same input produces same
   output)." Alternatively: drop the cksum branch and require perl (which
   provides shasum) as a stated dependency on both macOS and Linux.

2. **[AC8] Baseline count is wrong by 1.**
   The spec states "573 currently-passing checks (baseline as of 2026-04-29)"
   but the actual count as of this date is **574** (verified with three
   consecutive runs of `python3 smoke-test.py 2>&1 | grep -cE "^  ✓ "`).
   If the Generator targets 573 and the Tester asserts >= 574, the AC fails at
   the wrong threshold. If the Generator targets 574 + new tests and the Tester
   asserts >= 573, the gate is weaker than intended.
   **Proposed fix:** Replace `573` with `574` in AC8. Tester should assert
   final count >= 574 + (number of new checks added in this task).

3. **[AC6] Mount order claim is unverified and the string/object mixed-type
   array makes the AC mechanically underspecified.**
   The spec claims "Docker mounts in array order" but cites no source. More
   critically, the existing `devcontainer.json` mounts are **strings** (e.g.
   `"source=vibe-claude-config,target=/home/node/.claude,type=volume"`) while
   `learning_render_devcontainer_config` appends an **object** dict. A smoke
   test checking AC6 ordering via `m.get("target")` will silently skip all
   string entries and find the `vibe-claude-config` entry at index -1 (not
   found), making the ordering assertion vacuously true without actually
   verifying anything. The spec does not specify whether the new projects bind
   should be added as a string or object, nor does it specify how AC9 tests
   should parse mixed-type arrays.
   **Proposed fix:** AC6 should explicitly state: "For AC9 test purposes,
   when locating the `vibe-claude-config` string mount entry, the test MUST
   parse string-format entries by splitting on `,` and extracting `target=`
   fields, not via `.get('target')`. The new projects bind entry format
   (string vs. object) MUST match the format used for the /learnings bind
   (object dict) so AC9 tests can use a consistent parsing strategy." Also
   add a note that Docker/devcontainer CLI respects JSON array order for mounts
   targeting nested paths in the same volume tree (cite
   https://containers.dev/implementors/json_reference/ or equivalent).

4. **[AC3] "every mount entry from devcontainer/devcontainer.json" is
   underspecified as a verifiable criterion.**
   Does "every mount entry" mean: (a) identical count of entries, (b) identical
   string/object values, or (c) same semantic mount semantics? The existing
   mounts include `${localEnv:HOME}` interpolation tokens - these are preserved
   as literal strings in the override JSON (confirmed by testing). A Generator
   could omit one of the 4 source mounts and a test checking only "projects
   mount is present" (but not all 4 originals are present) would pass AC3
   partially. The spec doesn't say "exactly 4 original entries preserved".
   **Proposed fix:** AC3 should state: "The generated file MUST contain all N
   mount entries from the source `devcontainer/devcontainer.json` (currently
   4), preserved verbatim (type and value unchanged), plus the new projects
   bind entry, for a total of N+1 entries when /learnings is disabled, N+2
   when both are enabled."

---

### MEDIUM (likely to bite, recommend fixing)

5. **[AC1] New helper function has no specified name - AC9 cannot assert its
   existence by name.**
   The spec says "A function (new or extended)" without naming it. The
   `test_learning_helpers_exist` test (smoke-test.py:1440) enumerates specific
   function names. If a new function is added, its name is only known after the
   Generator runs; the Tester must guess or discover it. This creates a
   coordination gap: the spec doesn't tell the Tester what to look for.
   **Proposed fix:** Name the helper in the spec, e.g.
   `projects_bind_path <workspace_abs_path>` (by analogy with the learning
   pattern). Tester then adds it to the `helpers` list in
   `test_learning_helpers_exist`.

6. **[AC2] "invoking the launcher with VIBE_SOURCE_ONLY=1 plus the resolution
   helpers exposed must allow a smoke test to verify the directory creation
   path"** is ambiguous about WHAT is being verified.
   The AC says the smoke test asserts "the helper produces the expected path AND
   that calling `mkdir -p` against that path leaves the dir present." This
   conflates two assertions: (a) the path string is correct, and (b) mkdir
   works. Assertion (b) is trivially true for any valid path - it tests bash,
   not vibe. The real intent is presumably that the LAUNCHER ITSELF calls
   `mkdir -p` as part of its normal flow - but `VIBE_SOURCE_ONLY=1` bypasses
   the launch flow entirely. The only way to test that the launcher creates the
   dir is to inspect the vibe source for the `mkdir -p` call site (a static
   analysis check), not to execute it.
   **Proposed fix:** AC2 should say: "AC9 MUST include a static-analysis check
   asserting that `mkdir -p` (or equivalent) appears in the vibe source after
   the per-project bind path is computed and before the `devcontainer up`
   invocation, by string-searching the source. Additionally, MUST assert the
   helper echoes a path whose parent directories match `$HOME/.vibe/projects/`."

7. **[AC11] Manual test pass/fail criterion is vague.**
   "Verify the resumed conversation is A's most recent (not B's)" gives the
   user no observable signal to check. The user needs to know: look at the
   Claude session title, or look for project-A-specific context in the resumed
   session? Without a concrete observable (e.g. "the resumed session shows
   project A's `/workspace/CLAUDE.md` content, not project B's"), this is a
   judgment call that varies by user.
   **Proposed fix:** Add: "Pass criterion: after `vibe A --continue`, Claude's
   opening turn references project A's context (e.g. project A's `CLAUDE.md`
   or the most recent conversation in project A). The `/home/node/.claude/projects/`
   directory inside the container should contain only the per-project JSONLs for
   project A, verifiable via `ls /home/node/.claude/projects/` at the container
   shell."

8. **[AC4 / AC5] `.no-learn` walk-to-`$HOME` path not specified for smoke
   tests.**
   AC4 says "workspace not opted out (no `.no-learn` marker on the walk to
   `$HOME`)" and AC5 says "a `.no-learn` marker present in the workspace's
   walk-to-`$HOME` chain." The existing `test_learning_render_devcontainer_config`
   doesn't test the walk logic - it just calls `learning_render_devcontainer_config`
   directly. AC9 tests for AC4/AC5 must go through `_learning_build_override_config`
   (the higher-level builder) to cover the `learning_should_mount` gating. The
   spec says to use `_source_vibe_call` "or equivalent" but doesn't say which
   function to call. A Generator could satisfy AC4/AC5 with direct calls to
   the renderer without exercising the gating logic.
   **Proposed fix:** Specify that AC4/AC5 smoke tests MUST call
   `_learning_build_override_config` (not `learning_render_devcontainer_config`
   directly), with appropriate env setup including `VIBE_LEARNING_PATH`,
   `VIBE_LEARNING_ENABLED`, and workspace path with/without `.no-learn`.

9. **[Composition] The spec does not address the run-dir sha1 vs. per-project
   sha1 relationship.**
   Currently `_learning_build_override_config` uses a sha1 of the workspace
   path to name the run-dir file (`$HOME/.vibe/run/devcontainer-<sha1>.json`).
   After the change, the same sha1 will also name the per-project bind dir
   (`$HOME/.vibe/projects/<sha1>/`). The spec doesn't say these must use the
   same hash (they should, for consistency, but a Generator could use a
   different input or different hash for each). If they differ, the bind path
   in the override JSON would point to a different directory than the one
   `mkdir -p` created.
   **Proposed fix:** Add to Mechanism section: "The sha1 used for the
   per-project bind dir name and the sha1 used for the override JSON filename
   MUST be computed from the same input (absolute workspace path) using the
   same fallback ladder, so they are identical."

---

### LOW (nice-to-have polish)

10. **[AC12] "At least 10 non-blank lines" is easy to game.**
    A Generator could write 10 lines of single-word bullets or padding that
    technically contain the two sentinel phrases without delivering useful
    content. The fragment requirement has no prose quality gate.
    **Proposed fix:** Add: "The fragment MUST include at least one sentence
    explaining WHY the per-project isolation matters (i.e. preventing `vibe X
    --continue` from resuming an unrelated project's session)." This anchors
    content intent without being subjective.

11. **[AC9 / test naming] "test_task014_* OR descriptive names" is loose.**
    The Out-of-scope section names `test_learning_helpers_exist` and
    `test_learning_render_devcontainer_config` as must-not-break references.
    The new tests have no naming requirement, making it harder for the
    Evaluator to locate them in the diff.
    **Proposed fix:** Mandate `test_task014_*` prefix (not "or descriptive
    names") so the Evaluator can `grep test_task014` to find all new tests.

12. **[Mechanism section] Docker mount-order claim needs a hedge.**
    "Docker mounts in array order" is true in practice for Linux overlapping
    bind mounts onto volumes, but is not formally guaranteed by the
    devcontainer spec for all runtimes (OrbStack vs Docker Desktop may differ
    in edge cases). The spec states this as fact without citation or caveat.
    **Proposed fix:** Add a parenthetical: "(verified behavior for Linux Docker
    engine; devcontainer CLI passes mounts to `docker run --mount` in array
    order; if this assumption breaks in production, fallback is to set
    `source` for the vibe-claude-config volume mount explicitly)."

13. **[AC3] Source field value for projects bind is underspecified.**
    AC3 says "source set to the per-project host bind path" but doesn't
    specify whether this is a resolved absolute path or a template like
    `${localEnv:HOME}/.vibe/projects/<hash>`. The existing /learnings bind
    uses a resolved absolute path. Smoke tests will override `$HOME` to a
    tempdir, so a resolved path is necessary for smoke-test correctness.
    **Proposed fix:** Add: "The source value MUST be a fully resolved absolute
    path (no `${localEnv:HOME}` templates), consistent with how the /learnings
    bind source is set."

---

## Verdict

`revise`

## Highest-priority fix

The cksum fallback (concern 1) and the wrong baseline count (concern 2) are
both factual errors that will cause mechanical test failures regardless of how
well the Generator implements the feature. Fix concern 1 first: either remove
the "exactly 40 hex characters" requirement from AC1/AC7 (simplest - just
require stable non-empty output), or explicitly drop the cksum branch and
state that `sha1sum` or `shasum` is a hard dependency. Fix concern 2 by
changing `573` to `574` in AC8. Without these two fixes the Tester will write
assertions that either fail on macOS (cksum case) or have the wrong threshold
(baseline count), and the cycle will fail not because the feature is broken but
because the spec's ground-truth assertions were wrong before the Generator
touched a line of code.
