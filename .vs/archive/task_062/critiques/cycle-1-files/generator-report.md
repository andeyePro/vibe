# task_062 cycle 1 — Generator report

## Files changed
- `vibe`: new section "`vibe link`" (constants, `_link_*` helpers, `link_handle_subcommand`) inserted just after `codex_handle_subcommand`; `link` and `link-open` dispatch blocks after the `codex` block; 4 help-header lines after the `vibe codex` line. `parse_vibe_args` untouched; nothing else in `vibe` changed.
- `README.md`: "### Open vibe from a link" section (before "Second brain"); one row for `~/.vibe/link-projects` in the Host-side state table.
- `MANUAL-TESTS.md`: Test 68 after Test 67.
- `CHANGELOG.md`: entry under a new `## 2026-10-31` heading above `## 2026-10-30`.
- `.vs/tasks.json`: task_062 implementation_status -> complete.

## Per-AC notes
- AC1: `allow` prints `  ✓ allowed: <name> -> <path>`; idempotent allow does not rewrite (byte-identical; only chmods 600 + note if mode loose). `deny` drops every line whose name part equals the name (also removes `~/.vibe/link-last/<name>`). `list` prints `  (none)`.
- AC2: path allowlist checked before name; derived name = basename lowercased via `tr 'A-Z' 'a-z'`. Writer repairs 644 -> 600 with the `now trusted` note. Also refused: a name that only appears on invalid/duplicate lines (appending would create another duplicate; message says deny it first).
- AC3: `_link_registry_usable` mirrors `codex_registry_usable`; `_link_registry_load` warns per invalid line and per duplicate line. Registry text only ever compared with `=`/`case` against literals or used as `=~` SUBJECT.
- AC4: `_link_parse_url` (LC_ALL=C local to it, so the C locale never reaches the launched terminal) runs steps 1-4 on the string only. Also refused: leading `&`, a key with no `=`, a value containing `=`.
- AC5/AC6: argv exactly per spec. Launcher path = BASH_SOURCE resolved through symlinks, dir via `pwd -P` sentinel, plus basename.
- AC7: `_link_terminal` accepts the UNION of both OS lists (a config may be set from either OS); prints a note if not drivable on this OS. `open` re-validates per OS.
- AC8: dialog/launch blocks via `_link_print_argv`. Darwin dialog: `display dialog "Open a vibe session in project <name>?" & return & return & "<path>" with title "vibe" buttons {...} default button "Cancel" cancel button "Cancel" giving up after 60`. Real run parses `button returned:`/`gave up:true`. Linux zenity argv: `zenity --question --no-markup --title=vibe --text=... --ok-label=Open --cancel-label=Cancel --timeout=60`.
- AC9: stamp checked after terminal resolution; written (rm -f then touch) after confirmation, before launch, never in dry run.
- AC10: launcher path check -> exit 7, placed after URL validation and before the registry read (so it fires even when the project is unregistered).
- AC11/AC12: help header now 76 lines (smoke `[help] under 80 lines` limit; first draft at 80 failed it, so the header is 4 lines).

## Choices the spec left open
- `VIBE_LINK_ASSUME` counts only when non-empty (empty = unset -> real dialog, the fail-safe direction).
- Unknown/vanished project on Darwin shows the informational dialog (`No vibe project called <name>. Run "vibe link allow" in its folder.`) unless `VIBE_LINK_ASSUME` is set; in dry run it is printed as a `DRYRUN dialog` block. Vanished project message: `no vibe project called <name> at <path> any more ...`.
- Linux real launch `exec`s the terminal program (handler does not block until the window closes; rc irrelevant). Mac launches (osascript / open -na) run and are checked: failure -> exit 1 `could not start <term>` (spec lists no code for this).
- Linux installed-check maps Ghostty->ghostty, kitty->kitty, WezTerm->wezterm, gnome-terminal->gnome-terminal via `command -v`.
- Blank registry lines are skipped silently (not warned).

## Commands run
- `python3 code-check.py` -> exit 0 (shellcheck clean, 30 files).
- `python3 .vs/cycle-1/scratch-tests/t_link.py` -> exit 0, 0 failures (covers AC1-AC12 incl. real Darwin dialog "Always", Linux gnome-terminal exec, 1024 vs 1025-byte URL).
- `python3 smoke-test.py < /dev/null` -> exit 1 with ONE failure: `[taskandi-v2] AC10 control: the diff contains both allowed kinds ([], [])`. PRE-EXISTING and unrelated: smoke/checks_47 runs `git diff HEAD -- smoke/checks_28_taskandi_client.py smoke/checks_29_taskandi_binding_usage.py` and expects task_061's edits to be uncommitted; task_061 was committed in 9b1d7a7, so that diff is empty at any clean HEAD. This change touches neither file. (First run also failed `[help] under 80 lines` and the empty-array lint on `launch=()`; both fixed, gone in the second run.)
- Note: the smoke run was auto-moved to background by the harness after 180 s despite being issued in the foreground; waited for completion.
