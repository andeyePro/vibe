# Spec - task_014: per-project Claude `projects/` bind

**Revised after Spec Critic iter 1 + 2.** Iter-1 closed 4 BLOCKING (cksum /
40-hex incompatibility, baseline count 573 vs 574, mount-order verifiability
under mixed string/object mounts, AC3 underspecified preservation) + 5
MEDIUM + 4 LOW. Iter-2 returned `pass` with 3 MEDIUM residuals folded
inline below: (M1) AC14 added to verify cksum removal from
`_learning_build_override_config` via static grep; (M2) AC4/AC5/AC6/AC10
explicitly require a clean tmpdir `HOME` override for ALL three /learnings
sub-cases (config absent, `ENABLED=false`, `.no-learn` marker present);
(M3) AC3 mkdir-p regex tightened to reject the bare `$HOME/.vibe/projects/`
prefix without a sha1 component. Plus 1 LOW (test-quality gate per AC):
AC10 now requires each `test_task014_*` function to contain at least one
`check()` call per assertion bullet in its target AC.

## Task summary

Inside the vibe container, every host project mounts at `/workspace`, and the
entire `/home/node/.claude` is a single shared Docker volume
(`vibe-claude-config`). Claude Code keys conversation history by working
directory, so all sessions land in `/home/node/.claude/projects/-workspace/`,
jumbled together across projects. Result: `vibe voting --continue` resumes the
globally-most-recent vibe session regardless of project. The same leak hits the
in-container `/resume` picker and the per-`/workspace` auto-memory at
`/home/node/.claude/projects/-workspace/memory/MEMORY.md`.

This task gives each host project its own `/home/node/.claude/projects/`
directory inside the container, while keeping the rest of `/home/node/.claude`
(login, agents, settings, slash commands) shared via the existing
`vibe-claude-config` volume. After this lands, `vibe X --continue` resumes
the most recent conversation FOR project X, not globally.

## Mechanism

1. **Single shared hash helper.** Add a function
   `vibe_workspace_sha1 <abs_workspace_path>` that echoes a 40-character
   lowercase hex sha1 of the input. Implementation uses the
   `sha1sum | shasum` two-rung fallback ladder (the existing third rung,
   `cksum`, is dropped from this helper because cksum produces a decimal
   CRC32 not a 40-char hex sha1; both `sha1sum` (Linux coreutils) and
   `shasum` (Perl, ships with macOS) are available on every supported host
   and at least one of them is required). Both the existing per-session
   override-config run-dir filename (`$HOME/.vibe/run/devcontainer-<sha1>.json`)
   and the new per-project bind dir (`$HOME/.vibe/projects/<sha1>/`) MUST
   call this helper with the SAME input (the absolute workspace path), so
   the two sha1 values are identical for the same workspace.
2. **Per-project bind path helper.** Add `vibe_projects_bind_path
   <abs_workspace_path>` that echoes
   `<HOME>/.vibe/projects/<sha1>` where `<sha1>` is the output of
   `vibe_workspace_sha1`. The path is fully resolved (no `${localEnv:HOME}`
   template) so smoke tests can override `$HOME` to a tempdir and inspect
   the result.
3. **Launcher creates the dir.** The vibe launcher calls `mkdir -p` on the
   per-project bind path BEFORE `devcontainer up` runs, idempotent across
   invocations.
4. **Bind mounted at `/home/node/.claude/projects`.** Type=bind, NOT
   readonly. Source value in the override JSON MUST be the resolved
   absolute host path (output of `vibe_projects_bind_path`), not a
   `${localEnv:HOME}` template - same convention the existing /learnings
   bind uses.
5. **Mount order: vibe-claude-config volume FIRST, projects bind AFTER.**
   In the override JSON's `mounts` array, the entry whose target is
   `/home/node/.claude` (the `vibe-claude-config` volume) MUST appear at a
   strictly lower array index than the entry whose target is
   `/home/node/.claude/projects`. The devcontainer CLI passes mount entries
   to `docker run --mount` in array order; Docker mounts in the order
   given; nesting works only when the parent (volume) mounts first.
   Verified for Linux Docker engine. If this assumption breaks for any
   runtime, the symptom would be the bind landing under the volume's
   shadow rather than on top - failure is observable, not silent.
6. **Override JSON ALWAYS exists.** The per-session override-config builder
   in vibe (today: `_learning_build_override_config`, which falls back to
   echoing the source `devcontainer/devcontainer.json` path when /learnings
   is opted out) MUST be modified so it ALWAYS produces a real override
   file. The projects bind is added unconditionally; the /learnings bind
   is added only when `learning_should_mount` returns 0. The function name
   is preserved (smoke tests reference it by name; see Out-of-scope #6).
7. **Mount entry format.** The new projects bind MUST be added as a JSON
   OBJECT (not a comma-separated string), matching the format
   `learning_render_devcontainer_config` already uses for the /learnings
   bind. Schema:
   ```json
   {"source": "<resolved-abs-path>", "target": "/home/node/.claude/projects",
    "type": "bind"}
   ```
   No `readonly` field (defaults to false).

## Acceptance criteria

AC1. **`vibe_workspace_sha1` helper exists and is exposed under
`VIBE_SOURCE_ONLY=1`.** Takes a single argument (an absolute workspace
path) and echoes a 40-character lowercase hexadecimal string. Uses the
`sha1sum | shasum` two-rung fallback ladder. The ladder MUST exit
successfully with at least one rung available; if neither is on PATH, the
helper exits non-zero with an error message to stderr. Test asserts:
(a) output length is exactly 40, (b) output matches `^[0-9a-f]{40}$`,
(c) calling with the same input twice produces identical output,
(d) calling with two distinct inputs produces distinct outputs.

AC2. **`vibe_projects_bind_path` helper exists and is exposed under
`VIBE_SOURCE_ONLY=1`.** Takes a single argument (an absolute workspace
path) and echoes a path of the form `<HOME>/.vibe/projects/<sha1>` where
`<sha1>` is the output of `vibe_workspace_sha1` for the same input. Test
asserts the echoed path equals `$HOME/.vibe/projects/$(vibe_workspace_sha1
<input>)` exactly.

AC3. **Launcher calls `mkdir -p` on the per-project bind path before
`devcontainer up`.** Verified by static analysis of the vibe source: the
test reads `vibe`, locates the line invoking `devcontainer up` (or the
construction of `UP_BASE_ARGS` that feeds it), and asserts that an earlier
line in the same file contains a `mkdir -p` call whose argument refers to
the per-project bind path. The argument MUST reference `vibe_projects_bind_path`
(via captured output, e.g. `mkdir -p "$(vibe_projects_bind_path "$WORKSPACE")"`
or assigned-then-passed) OR include a `$HOME/.vibe/projects/` prefix
followed by a variable, subshell, or sha1-shaped component (`$sha1`,
`$(...)`, `${VAR}`). The bare literal `mkdir -p "$HOME/.vibe/projects/"` (no
per-workspace component) MUST NOT pass the check. The static check is a
regex/substring match; no Docker invocation required.

AC4. **Override JSON exists unconditionally.** With learning fully
disabled (no `~/.vibe/learning.config` file in the test's tmpdir-overridden
`HOME`), and called against any workspace, `_learning_build_override_config
<workspace>` MUST echo a path that is NOT equal to
`$DEVCONTAINER_DIR/devcontainer.json` AND that points to a real, readable
JSON file. The generated file's `mounts` array MUST contain ALL 4 mount
entries from `devcontainer/devcontainer.json` (currently `vibe-bash-history`,
`vibe-claude-config`, `~/.ssh` bind, `~/.gitconfig` bind), preserved verbatim
(string format unchanged), PLUS the new projects bind object whose target is
`/home/node/.claude/projects`. Total mounts count when /learnings is
disabled: exactly 5. When /learnings is enabled and not opted out: exactly
6 (the additional /learnings bind). The smoke test for AC4 MUST set
`HOME` to a clean tmpdir to ensure no stray `~/.vibe/learning.config` from
the test runner's host leaks into the result.

AC5. **Composition with /learnings enabled and not opted out.** With
`~/.vibe/learning.config` configured (`VIBE_LEARNING_ENABLED=true`, valid
existing `VIBE_LEARNING_PATH`) AND the workspace not opted out (no
`.no-learn` marker on the walk to `$HOME`), calling
`_learning_build_override_config <workspace>` MUST produce an override
whose `mounts` array contains BOTH the projects bind (target
`/home/node/.claude/projects`) AND the existing /learnings bind (target
`/learnings`, readonly). Smoke tests for AC5 MUST exercise the FULL
builder (`_learning_build_override_config`), NOT the lower-level
renderer (`learning_render_devcontainer_config`), so the gating logic
(`learning_should_mount`) is also exercised.

AC6. **Composition with /learnings disabled or excluded.** With learning
config absent OR `VIBE_LEARNING_ENABLED=false` OR a `.no-learn` marker
present in the workspace's walk-to-`$HOME` chain, calling
`_learning_build_override_config <workspace>` MUST produce an override
whose `mounts` array contains the projects bind but NOT a /learnings bind
(no mount entry whose target is `/learnings`). Smoke tests MUST cover all
three sub-cases (config absent, ENABLED=false, .no-learn marker present)
and MUST exercise the FULL builder, not the renderer directly. ALL three
sub-cases MUST run with a clean tmpdir `HOME` (separate `tempfile.TemporaryDirectory()`
per sub-case), set the `~/.vibe/learning.config` content explicitly per
sub-case (absent: no file written; ENABLED=false: file written with
`VIBE_LEARNING_ENABLED="false"`; .no-learn: config enabled AND a `.no-learn`
marker created in the workspace tmpdir under HOME). This isolation is
required so the result does not depend on whether vibe is configured on
the test runner's actual host.

AC7. **Mount order in override JSON.** Within the override JSON's
`mounts` array, the entry whose target is `/home/node/.claude` (string-
or object-formatted) MUST appear at a strictly lower array index than
the entry whose target is `/home/node/.claude/projects`. AC9 test
parsing MUST handle BOTH string-format mount entries (e.g.
`"source=...,target=/home/node/.claude,type=volume"`, parsed by
splitting on `,` and extracting `target=` substring) AND object-format
entries (e.g. `{"target": "/home/node/.claude/projects"}`, parsed via
`.get("target")`). A helper test function MAY be written; the test
MUST NOT silently skip string entries.

AC8. **Hash determinism (covers AC1.c, AC1.d explicitly as a separate
gate).** Two distinct absolute workspace paths produce two distinct
per-project bind dirs. Same path produces same dir. Verified by calling
`vibe_projects_bind_path` with two different paths in a tempdir and
asserting different outputs.

AC9. **No regression.** All 574 currently-passing smoke checks (baseline
verified by `python3 smoke-test.py 2>&1 | grep -cE "^  ✓ "` on
2026-04-29; the parked `task_013/AC10 diff scope check` is a single
pre-existing fail and remains excluded from this gate per its parked
status in TODO.md) MUST still pass after this change. In particular
`test_learning_render_devcontainer_config`, `test_learning_helpers_exist`,
`test_learning_banner_*` family, `test_learning_marker_*` family, and
`test_vibe_resume_args_*` must continue to pass without modification.

AC10. **New smoke tests.** Tester adds new `test_task014_*` functions
(prefix mandatory; the Evaluator must be able to enumerate new tests via
`grep -n "^def test_task014" smoke-test.py`) covering AC1 through AC8
plus AC14 (cksum-removal static check) without invoking docker. Tests
parse the generated override JSON via Python's `json` module. Tests
exercise `_source_vibe_call` with `VIBE_SOURCE_ONLY=1` for helper-level
checks; for AC4-AC6 they call `_learning_build_override_config` (NOT the
lower-level renderer) inside the same source-only environment, ALWAYS
with a clean tmpdir `HOME` override (use `tempfile.TemporaryDirectory()`
in each test), and with explicit per-sub-case `~/.vibe/learning.config`
setup as described in AC4 (absent), AC5 (enabled+valid path), and AC6
(three sub-cases). The new test count MUST be at least 10 (one per AC
plus separation tests for sub-cases). EACH `test_task014_*` function
MUST contain at least one `check()` call per assertion bullet enumerated
in its target AC (e.g. AC1 has four sub-assertions a/b/c/d; the test
covering AC1 MUST emit at least 4 `check()` calls). Thin tests that
satisfy the count via single-assertion bodies do NOT pass AC10.

AC11. **shellcheck clean.** `python3 code-check.py` exits 0 across all
shell files (currently 11). No new shellcheck findings introduced.

AC12. **MANUAL-TESTS.md updated with concrete pass/fail signal.** A new
section is appended to `MANUAL-TESTS.md` describing the per-project
resume verification with an OBSERVABLE pass criterion:

> **Setup:** in two distinct host directories `~/work/projA` and
> `~/work/projB`, each containing a unique sentinel file
> (`projA/CLAUDE.md` says "this is project A", `projB/CLAUDE.md` says
> "this is project B"). **Steps:**
> (1) `cd ~/work/projA && vibe`, hold a brief conversation, type
>     `/exit`.
> (2) `cd ~/work/projB && vibe`, hold a brief conversation, type
>     `/exit`.
> (3) `vibe projA --continue`.
> **Pass criterion:** the resumed Claude session is the projA
> conversation from step 1 (Claude's most recent prior turn references
> "this is project A" or projA-specific content), NOT the projB
> conversation. Additionally inside the container, `ls
> /home/node/.claude/projects/` shows exactly one slug (`-workspace`)
> containing only the projA JSONL(s), not projB's.
> **Fail signal:** the resumed conversation is projB's, OR the
> `projects/` directory contains JSONLs for both projects.

AC14. **cksum removal verification (static).** A test_task014_*
function asserts that `_learning_build_override_config` no longer
contains the `cksum` token by reading `vibe` source and checking the
function body (delimited by `_learning_build_override_config()` start
through the next top-level function or end-of-section delimiter). A
single static-grep / regex check is sufficient. This anchors the
Mechanism-section requirement that `_learning_build_override_config`
calls the new `vibe_workspace_sha1` helper (which uses only
sha1sum/shasum) instead of the inline cksum fallback. The check ensures
the run-dir filename and the per-project bind dir use the SAME hash
function, not just claim to.

AC13. **CLAUDE.md fragment.** A new file at
`devcontainer/claude-md/auto-memory-scope.md` (per task_007 convention,
shipped to all vibe containers via `install-claude-extras.sh`) explains:
(a) auto-memory at `/home/node/.claude/projects/-workspace/memory/`
is now scoped per-host-project after task_014;
(b) cross-project facts (preferences, voice, work style) belong in
`/learnings`, not auto-memory;
(c) at least one sentence explaining WHY the per-project isolation
matters - i.e. preventing `vibe X --continue` from resuming an
unrelated project's conversation, and preventing project-specific
memory from polluting unrelated work.
The fragment MUST be at least 12 non-blank lines, MUST contain the
sentinel phrases `per-project`, `/learnings`, and `vibe X --continue`,
AND MUST contain the substring "preventing" (anchors the WHY clause).

## Out of scope (do NOT implement)

- Migration of existing JSONLs from the shared volume's
  `projects/-workspace/` to per-project dirs. No clean signal exists
  (JSONLs do not record host project). One-time loss accepted.
- Auto-promotion of cross-project memories from current `MEMORY.md` to
  `/learnings`. Separate task.
- Cleanup of orphaned `~/.vibe/projects/<hash>/` directories when host
  projects are deleted. Future TODO.
- Any change to behavior under concurrent vibe launches against the same
  project (no change from today; share the same bind dir, last writer
  wins, same as the current shared volume).
- Any change to `~/.vibe/learning.config` schema or learning subcommand
  behavior. Untouched.
- Any change to the `vibe-bash-history` volume mount or to the workspace
  bind at `/workspace`.
- Any rename of `_learning_build_override_config` or
  `learning_render_devcontainer_config`. Generator MAY refactor internals
  but MUST NOT break the public surface that smoke tests reference by
  name (specifically `learning_render_devcontainer_config` is referenced
  by `test_learning_helpers_exist`; see `smoke-test.py:1449`).
- Removing the cksum branch from anywhere OTHER than the new
  `vibe_workspace_sha1` helper. The existing inline cksum fallback in
  `_learning_build_override_config`'s run-dir filename computation MUST
  be replaced by a call to `vibe_workspace_sha1` (so the same hash is
  used everywhere) but that removal is the only place cksum-related
  code is touched.

## Test location

`smoke-test.py` (project convention - all unit and structural tests live
in this single file; see existing `test_learning_*` family for shape).
Tester adds new `test_task014_*` functions (prefix mandatory) and wires
them into `main()`.

## Proposed budget

**2 cycles.** Rationale: the mechanism is tightly specified but composes
with two existing systems (the /learnings override-config logic and the
mount-order semantics of devcontainer CLI / Docker). Composition bugs
typically catch a Generator on first pass; cycle 2 reserved for
integration polish if cycle 1 surfaces interaction issues. If cycle 1
passes cleanly, accept and stop.

## Known irreversible side effect

After this lands, the existing JSONLs in the shared `vibe-claude-config`
volume (under `projects/-workspace/`) become inaccessible from inside
new vibe containers - they are still in the volume, but shadowed by
the empty per-project bind that mounts on top. Existing per-`/workspace`
auto-memory is similarly shadowed. This is a one-time loss on first
launch after upgrade, and MUST be documented in the TODO.md Done entry
when this task completes.
