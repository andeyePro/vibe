# task_045 — host-side Codex opt-in registry `~/.vibe/codex-allow` (plan item 3, branch `astra`)

## Task summary

The switch that mounts the Mac's ChatGPT login into a container is today an
untracked `.vibe-allow-codex` file inside the project. A prompt-injected
session can create that file by paths the Bash hook cannot see (`curl -o`,
git plumbing, `M=...; touch "$M"`), and the user's next launch mounts the
token. This task adds the consent layer the container cannot reach, mirroring
`~/.vibe/repos-acks`: a machine-local registry `~/.vibe/codex-allow` (chmod
600, one canonical workspace path per line) that the launcher requires IN
ADDITION to the marker. Three host-side subcommands manage it, and `deny`
stops that project's running container so revocation is immediate.

## Acceptance criteria

- AC1 `_codex_opted_in <ws>` (launcher, above the `VIBE_SOURCE_ONLY` guard)
  returns 0 only when BOTH hold: the existing marker checks pass unchanged
  (untracked `.vibe-allow-codex` in a verifiable git work tree) AND
  `codex_allowed <ws>` is true. Precedence is explicit: the three existing
  marker branches (not a git work tree, COMMITTED, not positively untracked)
  keep their current `⚠` lines and return 1 BEFORE `codex_allowed` is
  consulted; only when all three pass and the registry lacks the path does
  the new single `⚠` stderr line naming `vibe codex allow` fire (return 1).
  Registry-only returns 1 silently (no marker means no request); neither
  returns 1 silently.
- AC2 `codex_allowed <ws>` is true iff `~/.vibe/codex-allow`
  (`CODEX_ALLOW_FILE="$HOME/.vibe/codex-allow"`) contains the line `<ws>`
  matched whole-line fixed-string (`grep -qxF`), where `<ws>` is the
  canonical `pwd -P` path. A missing file is false. A registry file that is
  a symlink, or whose mode grants group/other any bit, is treated as ABSENT
  with one `⚠` stderr line (fail closed). The mode is read with the same
  portable idiom `_codex_dir_mode_warning` already uses
  (`stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f" 2>/dev/null`, last three
  octal digits, warn on any of bits 077); a helper `codex_registry_usable`
  implements the check once and `codex_allowed`, `list` and `deny` all call
  it (an unusable registry makes `list` print the `⚠` line and `(none)`,
  and makes `deny` refuse with exit 1 rather than rewrite a symlink).
- AC3 `vibe codex allow [path]` records `pwd -P` (or the canonical form of
  `path`) in the registry: creates `~/.vibe/` and the file with mode 600,
  idempotent (a second run adds no duplicate line), refuses a path that is
  not a directory or not a git work tree with a one-line reason and exit 1,
  and prints `  ✓ <path> allowed to mount the Codex login (~/.vibe/codex-allow)`
  plus the reminder that the untracked `.vibe-allow-codex` marker is still
  needed in that project. It never creates the marker.
- AC4 `vibe codex deny [path]` removes the exact line, prints
  `  ✓ <path> removed from ~/.vibe/codex-allow`, exits 0 even if the line was
  absent (idempotent, says `already absent`), and then, if a container for
  that workspace exists (`docker ps -aq --filter label=devcontainer.local_folder=<path>`),
  asks `Stop the container for <path> now so the login is unmounted immediately?`
  via the unchanged `ask_yes_no` (default y) and runs `docker stop <ids>` on
  yes. The prompt is skipped and the stop runs unconditionally when stdin is
  not a TTY (`[ ! -t 0 ]`) or `VIBE_CODEX_DENY_YES=1` is set; that skip
  logic lives ONLY in `_codex_deny` — `ask_yes_no` itself is not modified.
  Never `docker rm`.
- AC5 `vibe codex list` prints every registry line with a status suffix:
  `(marker present)` when `<path>/.vibe-allow-codex` exists, `(no marker –
  not mounted)` otherwise, `(path missing)` when the directory is gone; empty
  registry prints `  (none)`. Exit 0.
- AC6 `vibe codex` with no or an unknown subcommand prints usage
  `Usage: vibe codex allow|deny|list [path]` to stderr, exit 1. The
  dispatch block sits before the `--*` flag-parser loop like `repos`/`audit`.
  `vibe --help`'s header gains one line for `vibe codex allow|deny|list`.
- AC7 Drift: with the marker present and the registry line removed,
  `codex_mount_drift "$(_codex_desired_source ws)" <mounts-with-codex-bind>`
  emits `1` (the existing comparator, unchanged — the desired source is now
  empty); with both present it emits nothing against a matching bind.
- AC8 Docs: README's Codex setup section describes the three-step opt-in
  (marker, `vibe codex allow`, relaunch) and names the registry as the
  reason a container cannot opt itself in; `MANUAL-TESTS.md` Test 54 step 1
  adds `vibe codex allow` and its negative cases gain (d) marker present but
  not allowed on this machine: NO mount, one warning line. In `TODO.md`,
  the entry "move the Codex opt-in switch off the container-writable
  filesystem" bundles four follow-ups: ONLY its registry clause is closed
  (CHANGELOG entry); the other three (unguarded `auth.json` reads, hardened
  idioms for the `/learnings`/`/zotero` arms, the `/repos/*/.vibe-allow-codex`
  deny) are re-filed as their own still-open `[ ]` line, guard-edit-gated.
- AC9 Tests: launcher functions sourced with `VIBE_SOURCE_ONLY=1` via
  `_source_vibe_call` with an EXPLICIT `HOME` override to a fixture dir in
  every call (never the real `~/.vibe`; the existing `checks_01` codex
  fixtures already override `HOME` by hand — follow them): marker-only,
  registry-only, both, neither, committed marker + registry (expects the
  COMMITTED line, not the allow hint), non-work-tree marker + registry
  (expects the work-tree line), symlinked registry, mode-644 registry,
  canonicalisation (registry holds the `pwd -P` path, launch from a
  symlinked path is refused); `vibe codex allow` twice yields one line and
  mode 600; `deny` removes and is idempotent and refuses a symlinked
  registry; `list` statuses; usage exit 1. Subcommand tests run the real
  launcher with `HOME` overridden and a `docker` PATH stub that records its
  argv (no real Docker); the `deny` stop path is exercised with stdin not a
  TTY and asserts the stub saw `stop`.
- AC10 `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null`
  fully green; the existing `_codex_opted_in` fixtures in `checks_01` are
  updated by the Tester to register the fixture workspace so their intent
  (marker semantics) still holds.

## Out of scope

- Any edit to `guard-bash.sh`, `guard-fs.sh`, `init-firewall.sh`,
  `settings.local.json`; any container-side change; any `/etc/codex` policy;
  the `~/.codex` bind mechanics themselves; `docker rm`; a machine-wide
  "allow everywhere" switch (deliberately absent, as for the marker).

## Test location

`smoke/checks_17_delegation.py` if under 1,500 lines after the additions,
otherwise a new `smoke/checks_18_codex_allow.py` registered in
`smoke/runner.py`; the `_codex_opted_in` fixtures already in
`smoke/checks_01_launcher_basics_and_codecheck.py` are updated in place.

## Proposed budget

2 cycles.

## Model plan

- Spec Critic: sonnet. Generator: opus (launcher security path; the ladder's
  next rung is Fable, NOT pre-authorised). Tester: haiku. Evaluator: session
  model (Fable 5.1 chair).
