# task_045 — Generator report (cycle 1)

Branch `astra`. No commits, no branch switches. `smoke/` untouched; no
container-side file touched (`guard-bash.sh`, `guard-fs.sh`,
`init-firewall.sh`, `settings.local.json` all unmodified).

## Files changed

| File | What |
|---|---|
| `vibe` | registry constant + 4 helpers, `_codex_opted_in` final gate, 5 subcommand functions, dispatch block, `--help` header line, updated gate-list comment |
| `README.md` | three-step Codex opt-in, registry rationale, command list entry, `~/.vibe/codex-allow` table row, `VIBE_CODEX_PATH` wording |
| `MANUAL-TESTS.md` | Test 54 step 1 gains `vibe codex allow`; negative case (d) added |
| `TODO.md` | bundled Phase-1a entry split: registry clause closed, other three re-filed as one still-open `[ ]` line |

Not mine and not done (by instruction): `CHANGELOG.md` (chair writes it at
close-out) and the committed tests (Tester).

## Per-AC coverage

- **AC1** — `_codex_opted_in` keeps its three `⚠` marker branches first and
  unchanged; `codex_allowed` is consulted only after all three pass, and emits
  one new `⚠` line naming `vibe codex allow`. Registry-without-marker still
  returns 1 silently at the `[ -f "$ws/.vibe-allow-codex" ]` line; neither
  returns 1 silently.
- **AC2** — `CODEX_ALLOW_FILE="$HOME/.vibe/codex-allow"`, matched
  `grep -qxF -e "$ws"`. `codex_registry_usable` implements symlink + mode
  (`stat -L -c %a` / `stat -L -f %Lp`, last three octal digits, any of 077 set)
  once; `codex_allowed`, `_codex_list` and `_codex_deny` all call it. Missing
  file = false, silent. Unusable = treated as absent with one `⚠`. An
  unreadable mode also fails closed (extra, same direction).
- **AC3** — `vibe codex allow [path]`: `mkdir -p ~/.vibe`, `touch`,
  `chmod 600`, idempotent; refuses a non-directory and a non-git work tree with
  a one-line reason and exit 1; prints the pinned
  `  ✓ <path> allowed to mount the Codex login (~/.vibe/codex-allow)` plus the
  marker reminder and the relaunch line. Never creates the marker.
  `codex_allow_record` refuses a symlinked registry outright (touch/chmod
  follow symlinks) but repairs a loose mode rather than dead-ending the user.
- **AC4** — `vibe codex deny [path]`: prints
  `  ✓ <path> removed from ~/.vibe/codex-allow`, or the same line with
  `(already absent)`; exit 0 either way; refuses (exit 1) on an unusable
  registry rather than rewriting a symlink; then `docker ps -aq --filter
  "label=devcontainer.local_folder=$path"` and, on a match, the unchanged
  `ask_yes_no "Stop the container for <path> now so the login is unmounted
  immediately?" y`. The prompt is skipped and the stop runs unconditionally when
  `[ ! -t 0 ]` or `VIBE_CODEX_DENY_YES=1` — that logic lives only in
  `_codex_deny`; `ask_yes_no` is byte-identical. `docker stop`, never
  `docker rm`.
- **AC5** — `vibe codex list`: `(marker present)` / `(no marker – not mounted)`
  / `(path missing)`; `  (none)` for an empty, missing or unusable registry;
  exit 0.
- **AC6** — empty or unknown subcommand → `Usage: vibe codex allow|deny|list
  [path]` on stderr, exit 1. Dispatch block sits immediately after the `repos`
  block and before the `--*` parser. `vibe --help` header gains
  `vibe codex allow|deny|list [path]`.
- **AC7** — no change to `codex_mount_drift`; verified by scratch check that a
  removed registry line makes `_codex_desired_source` empty and the comparator
  emit `1` against a matching bind, and that both-present emits nothing.
- **AC8** — README/MANUAL-TESTS/TODO as above.
- **AC9/AC10** — tests are the Tester's; every AC9 case was covered as scratch
  (below) and code-check/smoke were run.

## Implementation note the reviewer should see

Seven new lines that would otherwise have read `echo "… codex …: …"` are
written with `printf '%s\n'`. `smoke/checks_17_delegation.py` locates the
launch-header line for this mount by scanning for the file's FIRST echo that
also carries a lowercase `codex` and a colon; any earlier such line silently
retargets that drift check (it went red until the conversion). Printed strings
are byte-identical to the pinned ones. A comment above `_codex_usage` records
the coupling.

## Scratch tests

`.vs/cycle-1/scratch-tests/test_codex_allow.py` (gitignored under
`.vs/cycle-*/`). 42 checks, all passing. Every call overrides `HOME` to a
fixture dir — the real `~/.vibe` is never read or written; subcommands run the
real launcher with `HOME` overridden and a `docker` PATH stub that appends its
argv to a log. Coverage: marker-only, registry-only, both, neither, committed
marker + registry (COMMITTED line wins, no allow hint), non-work-tree marker +
registry (work-tree line wins), symlinked registry, mode-644 registry (plus
repair-to-600), missing registry silent, canonicalisation (symlinked launch
path refused), AC7 drift both ways, `allow` twice → one line + mode 600,
`allow <path>`, `allow` non-directory and non-git refusals, `list` all four
states + unusable registry, `deny` remove/idempotent/mode-preserving/label
filter/`stop <ids>`/never `rm`, `deny` refusing a symlinked registry,
`VIBE_CODEX_DENY_YES=1` skipping the prompt, a real-pty run proving the prompt
IS asked on a TTY and `n` leaves the container running, usage exit 1 for both
empty and unknown subcommand, and the `--help` line.

## Commands run (foreground)

- `python3 code-check.py` → `✓ shellcheck clean across 20 files`
- `python3 smoke-test.py < /dev/null` → 3471 checks pass, **1 fails**
- `python3 .vs/cycle-1/scratch-tests/test_codex_allow.py` → 42/42

## Expected smoke failure (AC10 — Tester's to update)

- `[codex] login mount present: untracked marker present`
  (`smoke/checks_01_launcher_basics_and_codecheck.py`,
  `test_codex_container_plumbing`) — the fixture workspace carries the marker
  but the fixture `HOME` has no `~/.vibe/codex-allow`, so the mount is now
  correctly refused. Fix: write `<home>/.vibe/codex-allow` containing the
  fixture workspace's `pwd -P` path at mode 600 before the positive case.

Side effect of the same fixture, not a failure: the nested
`[codex] mount is the host dir, bind, read-write` check no longer executes
(it sits inside `if found:`), so the suite reports one fewer check until the
fixture is updated. Every other `[codex]` check in `checks_01` expects NO
mount and still passes.

Nothing else is outstanding.
