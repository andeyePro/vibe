# task_063 — `vibe link --install` / `--uninstall` / `--status`: register `vibe://` with macOS and Linux — 2026-10-31 (rev 3 after Spec Critic)

## Task summary

task_062 shipped `vibe link open <url>` / `vibe link-open <url>`, which do all validation, consent, confirmation and launching. Nothing yet routes a clicked `vibe://` link to them. This task adds `vibe link --install`, `--uninstall` and `--status`, which register a tiny URL handler with the OS so a click in Task&I's Mac app or a browser runs `vibe link-open '<url>'`. The handler holds no logic. Everything stays in the launcher, which is already tested. The handler is built on the user's own machine and ad-hoc signed there, so there is no download or notarisation. Sketch: `/brain2/andeye/Task&I-vibe-embedding-options.md` §7. Builds on task_062 (`/workspace/.vs/archive/task_062/spec.md`) and reuses its helpers: `VIBE_LAUNCHER_PATH`, `_LINK_PATH_RE` (the path allowlist), `_link_os`, `_link_print_argv`, `_link_registry_load`, the terminal resolution and the `Usage: vibe link` usage text.

## Design decisions (binding)

### Tool resolution (never touches the real system from tests)

Every external tool is resolved with `command -v <name>` first, falling back to its absolute system path only when it is not on PATH:

| tool | fallback path |
|---|---|
| `osacompile` | `/usr/bin/osacompile` |
| `PlistBuddy` | `/usr/libexec/PlistBuddy` |
| `codesign` | `/usr/bin/codesign` |
| `lsregister` | `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister` |
| `xdg-mime` | none |
| `update-desktop-database` | none |

PATH is never prepended. Test shims placed first on PATH always win, even on a Mac.

### macOS: `~/Applications/Vibe Link.app`

- **Template**: committed file `devcontainer/link/VibeLink.applescript` (host-side asset; containers do not use it), exactly:
  ```applescript
  on open location theURL
  	do shell script (quoted form of "@@VIBE@@") & " link-open " & (quoted form of theURL) & " </dev/null >/dev/null 2>&1 &"
  end open location

  on run
  	display dialog "Vibe Link opens vibe:// links from Task&I. Run 'vibe link --status' in a terminal for details." buttons {"OK"} default button "OK" giving up after 30
  end run
  ```
  - The template is read from `$VIBE_REPO_DIR/devcontainer/link/VibeLink.applescript`. `@@VIBE@@` is replaced with `VIBE_LAUNCHER_PATH` by a literal bash `${tpl//@@VIBE@@/$path}`. The allowlist excludes `&`, `\` and `"`, so neither replacement metacharacters nor AppleScript quotes can occur.
  - Because every stream is redirected and the job is backgrounded, `do shell script` returns at once. The applet quits while vibe's own confirmation dialog runs.
  - `quoted form of theURL` is the only place URL text meets a shell, and the launcher re-validates it.
- **Launcher path**: `VIBE_LAUNCHER_PATH` must be non-empty, a single line, pass `_LINK_PATH_RE` and be an executable regular file. Otherwise exit 7 with `refused: launcher path`, and nothing is created. This holds on both OSes.
- **Build**, in a `mktemp -d` directory that is removed on every exit path. Each step is one command, run in this order:
  1. `osacompile -o "<tmp>/Vibe Link.app" "<tmp>/VibeLink.applescript"`
  2. `PlistBuddy -c "Set :CFBundleIdentifier com.andeye.vibe.link" "<tmp>/Vibe Link.app/Contents/Info.plist"`. If `Set` fails, fall back to `Add :CFBundleIdentifier string com.andeye.vibe.link`.
  3. `PlistBuddy -c "Set :CFBundleName Vibe Link" <plist>`, with the same fallback to `Add … string`.
  4. `PlistBuddy -c "Add :LSUIElement bool true" <plist>`
  5. `PlistBuddy -c "Add :CFBundleURLTypes array" <plist>`
  6. `PlistBuddy -c "Add :CFBundleURLTypes:0 dict" <plist>`
  7. `PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string com.andeye.vibe.link" <plist>`
  8. `PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" <plist>`
  9. `PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string vibe" <plist>`
  10. `PlistBuddy -c "Add :VibeLauncherPath string <VIBE_LAUNCHER_PATH>" <plist>`
  11. `codesign --force --deep --sign - "<tmp>/Vibe Link.app"`. The plist edits break osacompile's ad-hoc seal, so re-signing is required.
- **Install**:
  - Refuse with exit 1 `refused:` if `~/Applications` or `~/Applications/Vibe Link.app` is a symlink. Never `rm -rf` through a symlink.
  - Create `~/Applications` if it is missing.
  - If the target exists, read its identity with `PlistBuddy -c "Print :CFBundleIdentifier" "<target>/Contents/Info.plist"`:
    - If it is `com.andeye.vibe.link`, run `lsregister -u "<target>"`, then `rm -rf "<target>"`.
    - Anything else, including a failed read or a missing plist, is foreign. Exit 1 with `refused: ~/Applications/Vibe Link.app exists and is not vibe's`, and touch nothing.
  - Then `mv "<tmp>/Vibe Link.app" "<target>"`, then `lsregister -f "<target>"`.
- **Uninstall**: refuse symlinks as above. If the bundle is present and vibe's, run `lsregister -u` then `rm -rf`, and print `removed: <path>`. If it is foreign, exit 1 with `refused: … is not vibe's` and remove nothing. If it is absent, exit 0 with `nothing to remove`.
- **Tool failures**: a missing tool exits 1 with `refused: <tool> not found`. A failing step exits 1 with `refused: <tool> failed`. In both cases the temp dir is removed and `~/Applications` is untouched, unless the failure was the final `lsregister -f`; then the bundle stays in place and the message says to re-run `--install`.

### Linux: `${XDG_DATA_HOME:-$HOME/.local/share}/applications/vibe-link.desktop`

- The file content is exactly:
  ```
  [Desktop Entry]
  Version=1.0
  Type=Application
  Name=Vibe Link
  Exec="<VIBE_LAUNCHER_PATH>" link-open %u
  Terminal=false
  NoDisplay=true
  MimeType=x-scheme-handler/vibe;
  ```
  The program is always double-quoted. Inside the quotes, only `"`, backtick, `$` and `\` would need escaping, and the allowlist excludes all four, so spaces and `~` are safe.
- Install steps:
  1. Check `command -v xdg-mime` before writing anything. If it is missing, exit 1 with `refused: xdg-mime not found`.
  2. `mkdir -p` the applications dir. Refuse if it is a symlink, or if the target file is a symlink.
  3. Write via a temp file in the same dir, then `mv`, then chmod 644.
  4. Run `xdg-mime default vibe-link.desktop x-scheme-handler/vibe`, then `update-desktop-database <dir>` when it is present.
- Uninstall removes the file only. The `mimeapps.list` association is left dangling, which is documented.
- Any OS other than Darwin uses the Linux path, reusing `_link_os` as task_062 does.

### Commands, exit codes, messages

| command | result |
|---|---|
| `vibe link --install` | 0 `installed: <path>`; 1 `refused: …`; 7 `refused: launcher path` |
| `vibe link --install` again | rebuilds and replaces vibe's own bundle or file (picks up a moved launcher); 0 |
| `vibe link --uninstall` | 0 `removed: <path>` or `nothing to remove`; 1 `refused: … is not vibe's` |
| `vibe link --status` | always 0; prints the lines below |
| `--install extra`, `--install --uninstall`, an unknown flag | 1, `Usage: vibe link` (the usage text lists the three new options) |

`--status` prints these lines, each a fixed prefix. On Darwin `<baked>` is read with `PlistBuddy -c "Print :VibeLauncherPath"`; on Linux it comes from the `Exec=` line with the quotes stripped.
- `handler: <path>` or `handler: not installed`
- `launcher: <baked>` (only when installed)
- `current: <VIBE_LAUNCHER_PATH>`
- `stale: run vibe link --install`, only when baked and current differ
- `projects: <N>`, the count of valid registry lines from `_link_registry_load`; 0 when the registry is unusable, matching `list`
- `terminal: <resolved terminal>`, or `terminal: (none chosen)` on Linux with none set
- Linux only: `default: <xdg-mime query default x-scheme-handler/vibe output>`, plus `not the default handler` when it isn't `vibe-link.desktop`

### Dry run

`VIBE_LINK_DRY_RUN=1` does three things:
- It still performs the read-only checks: launcher path, OS, symlink refusals, and the foreign-bundle identity read through `PlistBuddy`.
- It skips the tool-presence checks and creates nothing: no temp dir, no `~/Applications`, no applications dir.
- It prints one `_link_print_argv` block per external command, in execution order:
  - Labels: `osacompile`, `plistbuddy` (one block per call), `codesign`, `lsregister-u` and `rm` (only when vibe's bundle already exists), `mv`, `lsregister`, `xdg-mime`, `update-desktop-database`.
  - An existing bundle whose identity cannot be read (no PlistBuddy available, or the read fails) counts as foreign, so the dry run refuses as a real run would.
  - Then a final block `DRYRUN source`, followed by `  path: <destination>` and one `  | <line>` per line of the generated AppleScript or .desktop text.

The exit code is 0, unless a read-only check refuses; then its normal code applies.

### Help and docs

- In `vibe --help`, replace the existing "is next" note with the single line `#   vibe link --install | --uninstall | --status  # register vibe:// with the OS (macOS applet, Linux .desktop)`. Help stays at 78 lines or fewer.
- README "Open vibe from a link" gains the install step and the Automation prompt note.
- MANUAL-TESTS Test 68 gains:
  - install;
  - the first click shows the macOS "allow Vibe Link to control …" Automation prompt;
  - clicking `vibe://open?project=<name>` in Safari and in the Task&I Mac app shows the vibe dialog, and Terminal opens in the project;
  - a second click while the dialog is open is refused;
  - `--status` after moving the launcher says `stale`;
  - after uninstall, a click shows macOS's "no application" outcome;
  - the Linux equivalents with `xdg-open vibe://…`.
- CHANGELOG and TODO entries.

### Portability

Bash 3.2 rules as in task_062:
- Use the `${arr[@]+"${arr[@]}"}` form for possibly empty arrays.
- No `${var,,}`, `mapfile`, `declare -A`, `[[ -v ]]` or `&>`.
- Use `mktemp -d "${TMPDIR:-/tmp}/vibe-link.XXXXXX"`.

## Acceptance criteria

Test harness: `smoke/checks_50_vibe_link_install.py`, at most 1,500 lines, called from `runner.main()`. Every env is built by `_isolate_extras_env`, with `HOME` and `TMPDIR` inside the fixture. A shim directory goes first on PATH, containing:
- `uname`, printing Darwin or Linux.
- `osacompile`: parses `-o <out>`, creates `<out>/Contents/Info.plist` (minimal XML containing `CFBundleIdentifier` = `com.apple.ScriptEditor.id.x` and `CFBundleName`) and `<out>/Contents/Resources/Scripts/main.scpt`, and copies the source file to a log.
- `PlistBuddy`: logs argv; for `Print :X` it prints a value from a per-test fixture file, or exits 1 when none.
- Recorders for `codesign`, `lsregister`, `xdg-mime` and `update-desktop-database`, and an `mv` shim that logs and then delegates to the real `mv` (the launcher invokes `mv` by bare name).
- Failure injection: `SHIM_FAIL=<tool>` makes that shim exit 1.

The recorder log must be the only effect besides the files named in the ACs. Launcher-path cases run a copy of `vibe`, together with the `devcontainer/` it needs, placed under the fixture.

- **AC1 Darwin dry run.** The `DRYRUN` labels appear in the order given. Each block's `  argv: ` lines are exactly the design's commands, including the eleven build steps with the `-c` strings verbatim and the plist path last. The `DRYRUN source` block equals the template with `@@VIBE@@` replaced by the launcher path. No file or directory is created under the fixture HOME or TMPDIR.
- **AC2 Darwin real run (shims).**
  - The recorders are called in this order: osacompile, the nine PlistBuddy calls, codesign `--force --deep --sign -`, mv, lsregister `-f`. The bundle directory ends at `$HOME/Applications/Vibe Link.app`, and stdout has `installed:`.
  - A pre-existing bundle whose `Print :CFBundleIdentifier` returns another id, fails, or has no plist is refused with exit 1 and left byte-identical.
  - A second install over vibe's own bundle calls `lsregister -u` and then replaces it.
  - A symlinked `~/Applications`, or a symlinked bundle, is refused with exit 1 and nothing is followed.
- **AC3 Tool failures.** With `SHIM_FAIL` set to each of osacompile, PlistBuddy, codesign and mv, install exits 1 with `refused: <tool> failed`, the temp dir is gone and `~/Applications` is unchanged. With `SHIM_FAIL=lsregister`, it exits 1, the bundle is present, and the message mentions re-running `--install`. On a Linux host only (skipped on Darwin), with no osacompile shim, install exits 1 with `refused: osacompile not found`.
- **AC4 Shim precedence.** Every tool invoked is a PATH shim; the log names each invocation. A source check asserts that the launcher never prepends `/usr/libexec` or the LaunchServices directory to PATH, and resolves each tool with `command -v` before any fallback.
- **AC5 Linux.**
  - The .desktop content equals the design text exactly, has mode 644, and lives under `$XDG_DATA_HOME/applications` when that is set, else under `$HOME/.local/share/applications`.
  - `xdg-mime default vibe-link.desktop x-scheme-handler/vibe` is recorded, and so is `update-desktop-database` when its shim exists; it is skipped silently when the shim is absent.
  - Missing xdg-mime gives exit 1 and writes nothing.
  - A launcher path containing a space and a `~` yields `Exec="<path>" link-open %u`. A Python split following desktop-entry rules gives exactly the words `<path>`, `link-open` and `%u`.
- **AC6 Launcher path.** A launcher copy whose path contains `"` exits 7 with `refused: launcher path` and creates nothing, on both the Darwin and the Linux shim. So does a non-executable launcher file (run as `bash <copy>`).
- **AC7 Uninstall.**
  - On Darwin, vibe's bundle gets `lsregister -u`, is removed, and stdout has `removed:`.
  - A foreign bundle gives exit 1, and nothing is removed.
  - When absent: exit 0 with `nothing to remove`.
  - On Linux, the file is removed, and a second run gives `nothing to remove`.
- **AC8 Status.** Each fixed line from the design is checked in these states: not installed; installed and current; installed and stale (baked path differs); 0, 1 and 2 registered projects; an unusable registry (`projects: 0`). On Linux, the `default:` line appears, plus `not the default handler` when the xdg-mime shim returns another file.
- **AC9 Applet template.** The committed `devcontainer/link/VibeLink.applescript` contains exactly one `do shell script`, matching the design line byte for byte with the `@@VIBE@@` placeholder, and URL text is referenced only as `(quoted form of theURL)`.
- **AC10 Usage and help.**
  - `vibe link --install extra`, `vibe link --install --uninstall` and `vibe link --bogus` each exit 1 with `Usage: vibe link`, and the usage text names `--install`, `--uninstall` and `--status`.
  - `vibe --help` has at most 78 lines, contains `vibe link --install`, and no longer contains `is next`.
- **AC11 Gates and docs.**
  - README contains `vibe link --install`.
  - MANUAL-TESTS Test 68 contains `Automation` and `--status`.
  - CHANGELOG mentions `vibe link --install`.
  - `python3 code-check.py` exits 0 and `python3 smoke-test.py < /dev/null` exits 0.
  - No test pins a commit sha.

## Out of scope

Notarisation, a Dock icon, any logic in the applet beyond the one handler, Windows, removing the Linux `mimeapps.list` association, and Task&I's side of the button.

## Model plan

- Planner and Evaluator: Opus 5.5.
- Spec Critic: sonnet.
- Generator: sonnet, ceiling opus (mechanical plumbing on top of a hardened base).
- Tester: sonnet.
- Fable rung: not pre-authorised.
- `/code-review high` before the pass commit, because `vibe` is a hot file.

## Rev 4 addendum (cycle 2) — `/code-review high` findings (2026-10-31)

Cycle 1 passed (checks_56; full suite 0). The review found the following; cycle 2 fixes them. Where this contradicts earlier sections, this wins. The Tester adds tests for AC12–AC20 and may change only checks asserting the old behaviour named here.

- **AC12 Reinstall never loses the working handler.** On macOS, the new bundle is first moved to a sibling `~/Applications/.Vibe Link.app.new-<pid>` (refused if that path exists), and only then is the old bundle deregistered (`lsregister -u`), renamed to `.Vibe Link.app.old-<pid>`, the new one renamed into place, registered (`lsregister -f`), and the old one removed. If any step before the final rename fails, the old bundle is untouched and still registered, the sibling is removed, and the command exits 1. Test: `SHIM_FAIL=mv` on a reinstall leaves the old bundle byte-identical and no sibling behind.
- **AC13 PlistBuddy values with spaces are quoted.** Every value inside a `-c` string that can contain a space is double-quoted: `Set :CFBundleName "Vibe Link"`, `Add :VibeLauncherPath string "<path>"` (the path allowlist already excludes `"` and `\`). The dry-run argv shows the quotes. The `Print` read back strips nothing (PlistBuddy prints the value unquoted).
- **AC14 One source for the plist edits.** A single bash array of the `-c` strings feeds both the dry-run blocks and the real run.
- **AC15 No nesting on a racing directory.** The final rename refuses (exit 1 `refused:`) if the target appeared since the check (`[ -e ]` immediately before the `mv`, and `mv` never moves into an existing directory: use `mv -n` or test after).
- **AC16 macOS status checks the default handler.** `--status` on macOS adds `default: <bundle path or (unknown)>` from `lsregister -dump` filtered for the `vibe` scheme claim, and `not the default handler` when another bundle claims `vibe:` before ours. If `lsregister -dump` is unavailable or unparsable, print `default: (unknown)` and nothing else.
- **AC17 Linux failure after writing.** If `xdg-mime default` fails after the .desktop file was written, the file is removed again before exiting 1. `--uninstall` runs `update-desktop-database <dir>` when present.
- **AC18 README and MANUAL-TESTS wording.** Replace the Automation note: the applet itself needs no permission; macOS may ask once to let `vibe` (via osascript) control Terminal or iTerm, and may ask again after `--install` re-signs the applet; Ghostty, kitty and WezTerm launch with `open -na` and need no prompt. Test 68 wording follows.
- **AC19 One launcher-path check.** `_link_open` and `--install` share one helper (`_link_launcher_check [--executable]`).
- **AC20 Constants and comments.** `_LINK_LSREGISTER` constant for the LaunchServices path used by install, uninstall and status; fix the stale comment above the plist getter.
- **Process note (not an AC):** the TODO.md entry for task_063 is closed by the Evaluator in the pass commit.
