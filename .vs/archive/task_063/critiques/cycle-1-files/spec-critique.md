# Critique of task_063 draft spec (vibe link --install / --uninstall / --status)

Verdict: REVISE. 6 BLOCKING, 9 MINOR. The design is sound (no logic in the handler; launcher re-validates), but several mechanics are wrong or untestable as written, and one test-design choice would make the smoke suite mutate the maintainer's real LaunchServices on a Mac.

Facts checked in /workspace/vibe: shebang is `#!/bin/bash` (3.2 on macOS) with `set -euo pipefail`; `_LINK_PATH_RE='^/[A-Za-z0-9 ._/+@,:=~-]+$'` (note: ALLOWS space and `~`, and `/`); exit 7 is already `refused: launcher path ...` in `_link_open`; `_link_print_argv <label> args...` prints `DRYRUN <label>` then one `  argv: <arg>` per arg (one block per command); `--help` is 76 lines against a `< 80` check (smoke/checks_01 line 183), and the line "(vibe link --install, registering vibe:// with the OS, is next)" is already there; Darwin terminal launches use `open -na`, so the applet's minimal PATH is fine for them.

## Concerns

1. BLOCKING — Test PATH ordering lets smoke touch the real system on a Mac.
   The spec says to PREPEND `/usr/libexec` and the LaunchServices `Support` dir to PATH "so tests can shim". On a real Mac that puts the real PlistBuddy and lsregister ahead of the test shims, so a maintainer running `python3 smoke-test.py` on a Mac would register `vibe://` in their real LaunchServices (and `-u` could unregister their real installed applet). On Linux CI it passes, which hides the bug.
   Fix: resolve each tool as `command -v NAME` first, falling back to the absolute system path only if not on PATH (or append the dirs to PATH, never prepend). Also resolve `HOME` only from `$HOME` (already sandboxed) and never use absolute `/Applications`.
   AC text: "AC-shim. With shims first on PATH and a real-looking `/usr/libexec` unavailable or present, `--install` calls only the shim recorders (assert the recorder log names every tool invoked, and no tool is invoked from an absolute system path when a PATH shim exists). A test that runs on a Darwin host asserts the same with a sentinel real-tool path unchanged."

2. BLOCKING — The edited bundle is never re-signed.
   `osacompile -o X.app` produces an ad-hoc-signed applet; editing `Contents/Info.plist` afterwards breaks the bundle seal. On Apple Silicon a bundle with a broken seal can fail Gatekeeper/LaunchServices checks or be killed, and `codesign -v` fails. The spec has no re-sign step, and "no signing step" in the summary is wrong for local ad-hoc signing.
   Fix: after the PlistBuddy edits and before `mv`/`lsregister`, run `codesign --force --deep --sign - "<tmp>/Vibe Link.app"` (resolved like the others; failure -> exit 1 `refused: codesign failed`). Add it to the dry-run blocks and the recorder order.
   AC text: "Darwin real run with shims records, in order: osacompile, PlistBuddy edits, codesign `--force --deep --sign -`, (mv), lsregister `-f`. A failing codesign shim exits 1 with `refused:` and leaves `~/Applications` untouched."

3. BLOCKING — PlistBuddy operations are not specified (Add vs Set, arrays/dicts) and the identity read is unspecified.
   osacompile's Info.plist already has `CFBundleIdentifier` (`com.apple.ScriptEditor.id.<name>`) and `CFBundleName`, but NOT `LSUIElement` or `CFBundleURLTypes`. `Set` on an absent key and `Add` on an existing key both fail ("Entry Already Exists"/"Does Not Exist"). Nested containers must be added parent-first. "set the four keys" is not testable.
   Fix: specify the exact `-c` strings, one PlistBuddy invocation per command, file last:
   - `Set :CFBundleIdentifier com.andeye.vibe.link`
   - `Set :CFBundleName Vibe Link` (quote the arg; it is one argv element after `-c`)
   - `Add :LSUIElement bool true`
   - `Add :CFBundleURLTypes array`, `Add :CFBundleURLTypes:0 dict`, `Add :CFBundleURLTypes:0:CFBundleURLName string com.andeye.vibe.link`, `Add :CFBundleURLTypes:0:CFBundleURLSchemes array`, `Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string vibe`
   - `Add :VibeLauncherPath string <vibe>` (see 5)
   Pre-existing-key robustness: since the bundle is freshly built each time, use `Set` for the two existing keys, but if `Set` fails fall back to `Add` (or `Delete` then `Add`) so a future macOS that omits the key still works. The identity read is `PlistBuddy -c 'Print :CFBundleIdentifier' "<app>/Contents/Info.plist"`; specify it, because the AC2 recorder must return a scripted value for it.
   AC text: "AC1 asserts the exact ordered PlistBuddy `argv` lines above (each `-c` string verbatim, file path last), and that the identity check is `Print :CFBundleIdentifier` on the existing bundle's Info.plist."

4. BLOCKING — Linux Exec quoting rule is wrong for the path allowlist.
   The Desktop Entry spec requires quoting an Exec argument that contains any of: space, tab, newline, `"`, `'`, `\`, `>`, `<`, `~`, `|`, `&`, `;`, `$`, `*`, `?`, `#`, `(`, `)`, or a backtick. The allowlist permits `~` (and space). The spec only refuses space, so a launcher under `~`-containing path installs a handler that silently breaks. `%` is not in the allowlist (good: no `%%` escaping needed), `=,:+@` are safe.
   Fix (preferred): always quote the program: `Exec="<VIBE>" link-open %u`. Inside double quotes only `"`, backtick, `$`, `\` need backslash-escaping and none can occur (allowlist), so spaces and `~` then work and the "no space" refusal and extra exit-7 case disappear. If keeping unquoted, refuse any of the reserved set (at minimum space and `~`).
   `%u` is correct (one URL, never a file list). Also add `Terminal=false` and `Version=1.0` for strict parsers.
   AC text: "AC3b. A launcher path containing a space and a `~` yields `Exec=\"<path>\" link-open %u` and `desktop-file-validate`-style parse (a Python test splitting per the spec's rules) yields exactly three argv words `<path>`, `link-open`, `%u`."

5. BLOCKING — `--status` baked-path extraction via osadecompile is fragile and unspecified.
   `osacompile -o X.app` lays the compiled script at `Contents/Resources/Scripts/main.scpt` (correct), but `osadecompile` output is reformatted source and the parse rule (find `quoted form of "..."` up to `" & " link-open "`) is not stated. Any change to wording or Apple's decompiler formatting breaks status and its AC6 test depends on the recorder reproducing that exact text.
   Fix: record the baked path as a custom Info.plist key `VibeLauncherPath` (item 3) and read it with `PlistBuddy -c 'Print :VibeLauncherPath'`. Keep `main.scpt` only as the code. Drop osadecompile from the dependencies (one fewer shim). If osadecompile is retained, state the exact extraction rule and recorder text.
   Also specify status output (all fixed substrings, exit 0 always): `handler: <path>` or `handler: not installed`; `launcher: <baked>`; `current: <VIBE_LAUNCHER_PATH>`; `stale: run vibe link --install` (only when they differ); `projects: <N>` (count of VALID registry lines via `_link_registry_load`, 0 when unusable, matching `list`); `terminal: <resolved>` (reuse the task_062 precedence: config VIBE_TERMINAL then OS default; `(none chosen)` on Linux with none). Linux status uses the `Exec=` line parse (strip the surrounding quotes from item 4) and `xdg-mime query default x-scheme-handler/vibe` -> print `default: <file>`; a mismatch prints `not the default handler`.
   AC text: "AC6 asserts each of the fixed lines above for installed/not-installed/stale and for 0, 1 and 2 registered projects, and that an unusable registry prints `projects: 0`."

6. BLOCKING — Dry-run format and scope inconsistent with task_062 and untestable as written.
   task_062's `_link_print_argv` prints ONE command per block: `DRYRUN <label>` + `  argv: ` lines. The draft invents `DRYRUN install` blocks holding many commands plus `  file: <path>` / `  | ` lines, which no existing helper prints and which would make the argv-per-command assertions ambiguous. It also says the dry run "exits 0 without touching the filesystem", but the refusals (launcher path, foreign bundle, missing tools) need reads, and tool-presence checks would fail on a Linux box testing the Darwin path.
   Fix: reuse `_link_print_argv` verbatim: one block per external command, labels `osacompile`, `plistbuddy`, `codesign`, `mv`, `lsregister`, `xdg-mime`, `update-desktop-database`, `uninstall-lsregister`, `rm`; the generated AppleScript/.desktop text printed as a final block `DRYRUN source` with each line as `  | <text>` (new, specify it) preceded by `  path: <dest>`. Dry run: still performs read-only checks (path allowlist, uname, foreign-bundle identity read through the PlistBuddy shim if the bundle exists) but SKIPS tool-presence checks and creates nothing (no tmpdir, no `~/Applications`). Dry-run exit 0, exit codes of refusals unchanged.
   AC text: "AC1 asserts the sequence of `DRYRUN` labels, each block's `  argv: ` lines exactly, and that no file or directory is created under the sandboxed HOME or TMPDIR."

7. MINOR (but fix) — AppleScript shape and the background `&`.
   - The statement relies on precedence: `do shell script quoted form of "X" & " link-open " & quoted form of theURL & " >/dev/null 2>&1 &"`. `quoted form of` binds tightly so it works, but parenthesize each operand for readability and so AC7's static pattern is unambiguous: `do shell script (quoted form of "<VIBE>") & " link-open " & (quoted form of theURL) & " </dev/null >/dev/null 2>&1 &"`.
   - Backgrounding with `&` inside `do shell script` works only if ALL of stdout/stderr are redirected (done); otherwise `do shell script` waits for the pipe and hangs. Add `</dev/null` so the child holds no inherited stdin. With that, the applet returns immediately; the orphaned child is reparented to launchd and keeps running after the applet quits, so the vibe confirmation dialog (up to 60 s) does not block a second click (which then hits task_062's one-dialog-at-a-time lock, exit 3, silently into /dev/null — acceptable, say so).
   - `do shell script` runs `sh` with PATH=/usr/bin:/bin:/usr/sbin:/sbin and no user profile. The launcher is `/bin/bash` and the Darwin terminal launches use `open -na`/`osascript`, so this is fine, but state it as a requirement ("link-open must not need anything off the minimal PATH on Darwin") and add a smoke test running `link-open` dry run with `env -i PATH=/usr/bin:/bin HOME=...` on the Darwin shim. Linux terminals (ghostty/kitty/wezterm by bare name) use the desktop session PATH; note that a `~/.local/bin` terminal may not be found.
   - Add `activate` before `display dialog` in `on run`: an LSUIElement app's dialog otherwise appears behind other windows.
   - Cold launch by a URL event does not run `on run`, so the help dialog only appears on a manual double-click. Say that so nobody tests for a dialog on click.
   - First click triggers a macOS Automation consent prompt ("Vibe Link wants to control Terminal/iTerm"), attributed to the applet as the responsible process. Not mechanically testable; add to MANUAL-TESTS and the README note.
   AC text: "AC7 asserts exactly one `do shell script` in the .applescript and that it equals the pinned template byte-for-byte after replacing the `@@VIBE@@` placeholder; AC7b the substituted launcher path never contains `\"` or `\\` (already guaranteed by the allowlist) and no other `theURL` use exists."

8. MINOR — Substitution method and placeholder.
   `<VIBE>` in a committed .applescript is not valid AppleScript and the allowlist contains `/`, so a `sed s/<VIBE>/$p/` substitution breaks. Use a clearly inert token `@@VIBE@@` and bash `${tpl//@@VIBE@@/$path}` (literal replacement; the allowlist excludes `&` and `\`, so bash 5.2's patsub `&` semantics never apply, but state it). Read the template via `$(cat file)` with the repo dir from `VIBE_REPO_DIR`; it must exist (exit 1 `refused: missing devcontainer/link/VibeLink.applescript`). Write the substituted source to the tmpdir with `printf '%s\n'`, never `echo`. Note `devcontainer/link/` ships to the container too (synced dirs); say it is ignored there or put it under a host-only path (`link/`).

9. MINOR — Replacing an existing bundle: `mv` pitfalls, symlinks, ordering.
   - `mv "<tmp>/Vibe Link.app" ~/Applications/` when the target exists nests the new bundle inside the old one. Specify: after the identity check, `lsregister -u` the old, `rm -rf` the old, then `mv`. Refuse (exit 1 `refused:`) if `~/Applications` or `~/Applications/Vibe Link.app` is a symlink (never `rm -rf` through one), mirroring task_062's no-symlink rules.
   - Foreign bundle where `Print :CFBundleIdentifier` fails or Info.plist is absent: treat as foreign (refuse), not as ours.
   - Order for re-registration: `lsregister -u <old>` (if present) -> remove -> mv new -> `lsregister -f <new>`. `-f` forces re-scan, `-u` unregisters by path; both flags are correct, and the `lsregister` path `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister` is correct on current macOS. If another app already claims `vibe:` the default is not changed by lsregister; `--status` cannot verify the default on Mac, so say that (do not claim "registered as default").
   - Clean up the tmpdir explicitly with `rm -rf` on every exit path. Do NOT use `trap ... EXIT`; this launcher funnels EXIT through `vibe_exit_hook_add`.
   AC text: "AC2b. A second install with an existing vibe bundle yields a single `Vibe Link.app` with no nested `Vibe Link.app/Vibe Link.app`, recorder order `lsregister -u`, then new `lsregister -f`; a symlinked `~/Applications/Vibe Link.app` or `~/Applications` exits 1 `refused:` and the symlink target is untouched."

10. MINOR — Exit codes and messages are incomplete.
    The table covers only some cases. Specify:
    - bare `vibe link --install extra` / unknown flag -> exit 1 `Usage: vibe link` (extend `_link_usage` text; keep the existing `Usage: vibe link` prefix), including `--install --uninstall` combos.
    - launcher unusable (`VIBE_LAUNCHER_PATH` empty, multi-line, fails allowlist, or not an executable file) -> exit 7 `refused: launcher path`; a non-executable/missing launcher file is also exit 7 (do not bake a dead path).
    - missing `osacompile`/`PlistBuddy`/`codesign`/`lsregister` -> exit 1 `refused: <tool> not found`; failure of any build step -> exit 1 `refused: <tool> failed`, tmpdir removed, `~/Applications` untouched.
    - foreign bundle on uninstall -> exit 1 `refused: ... is not vibe's`, nothing removed (draft is silent).
    - success messages: `installed: <path>`, `removed: <path>`, `nothing to remove` (all stdout).
    - non-Darwin/non-Linux (`uname` neither): task_062's `_link_os` treats everything else as Linux; the draft's "other OS exit 1 not supported" contradicts that. Decide: reuse `_link_os` (Linux behaviour) and delete the "other OS" row, or add an explicit check and test it with a `uname` shim printing `FreeBSD`.
    AC text: one AC per row above, each asserting exit code plus the fixed substring.

11. MINOR — Linux details.
    - Honour `XDG_DATA_HOME` (`${XDG_DATA_HOME:-$HOME/.local/share}/applications`) or state deliberately that it is ignored; create the directory (mkdir -p) if missing. `--status`/`--uninstall` must use the same resolution.
    - Missing `xdg-mime` check should run before writing the .desktop file so a refusal writes nothing (AC4 says "writes nothing" only for path refusals). `xdg-mime default` also edits `~/.config/mimeapps.list`; uninstall should remove the handler's association, or say it leaves a dangling entry (acceptable; document it). Verify with `xdg-mime query default x-scheme-handler/vibe` in `--status`.
    - `update-desktop-database` is optional (`command -v`), failure non-fatal, invoked with the applications dir; it refreshes `mimeinfo.cache`, which GLib-based browsers read. In the dry run, print its block only if present on PATH or always? Pick one: always print (dry run skips presence checks, item 6).
    - Write with `mktemp` in the same directory and `mv` (spec says so) with `chmod 644` BEFORE the mv.

12. MINOR — Help size.
    `vibe --help` is 76 lines and the check is `< 80`. Replace the existing two-line "is next" note with one line `vibe link --install | --uninstall | --status  # register vibe:// with the OS (macOS applet / Linux .desktop)` (net 0 to +1 line, 76-77). State a hard budget: help stays <= 78 lines, and the Usage line in `_link_usage` also lists the new options. Update the README and the help-fragment assertions in checks_48 line ~1058 if they pin the old "is next" text (grep first; the old text must be removed from help, README and any docs).
    AC text: "AC-help. `vibe --help` has < 79 lines, contains `vibe link --install`, and no longer contains `is next`."

13. MINOR — Bash 3.2 portability and set -u.
    Under `set -euo pipefail` on bash 3.2, expanding an empty array `"${arr[@]}"` aborts ("unbound variable"); every `argv` array passed to `_link_print_argv` or run must be non-empty or use the `${arr[@]+"${arr[@]}"}` form. No `${var,,}`, no `mapfile`, no `declare -A`, no `[[ -v ]]`, no `read -d ''` tricks, no `&>`, no process-substitution reliance for control flow. `mktemp -d "${TMPDIR:-/tmp}/vibe-link.XXXXXX"` (BSD-compatible form; no `--tmpdir`). `stat` via the existing `_link_mode/_link_owner` helpers. Add to AC9: run the new code paths under `bash` 3.2 if available, or at least `shellcheck -s bash` clean (code-check already covers).

14. MINOR — Mechanical test design on Linux.
    Spell out the harness so the generator does not guess:
    - `uname` shim printing `Darwin`; `osacompile` recorder that parses `-o <out>` and creates `<out>/Contents/Info.plist` (a minimal XML plist containing `CFBundleIdentifier` `com.apple.ScriptEditor.id.x`) and `<out>/Contents/Resources/Scripts/main.scpt`, and copies the source file argument to a log; `PlistBuddy` recorder that logs argv and, for `Print :CFBundleIdentifier`/`:VibeLauncherPath`, prints values from per-test fixture files (so foreign-bundle, stale and missing cases are scriptable); `codesign`, `lsregister` pure recorders with env-controlled failure injection (`SHIM_FAIL=osacompile`, etc.); `xdg-mime`/`update-desktop-database` recorders with the same.
    - Every test builds its env through `_isolate_extras_env` (per CLAUDE.md), sets `HOME` and `TMPDIR` into the fixture, and asserts the recorder log is the only effect.
    - Launcher-path tests (`"`, space, `~`) copy `vibe` to a path under the fixture, since `VIBE_LAUNCHER_PATH` is derived from the script location; the draft's "launcher copied to a path containing `"`" is a path the allowlist already rejects but the copy must still run, so assert it runs far enough to print the refusal.
    - The test file number: the draft names `checks_49_vibe_link_install.py`, but `checks_49_vibe_link_hardening.py` already exists. Use `checks_50_vibe_link_install.py` (keep each part <= 1,500 lines) and register it in `runner.main()`.
    - Final AC: no test pins a commit sha (HISTORICAL_PINS_ALLOWED rule).

15. MINOR — AC7 static check specifics and docs.
    State the exact pinned template (byte-for-byte) in the spec, so AC1 and AC7 compare to the same string rather than two paraphrases (AC1 currently quotes the shell string without the redirect suffix). Extend AC8: README "Open vibe from a link", MANUAL-TESTS Test 68 (add: first-click Automation prompt on macOS, a second click while a dialog is open is ignored, `--status` after moving the launcher says stale, uninstall then clicking shows the macOS "no application set to open" outcome), CHANGELOG and TODO entries per the project convention, and the `devcontainer/link` vs `link/` decision from item 8.

## Verdict

REVISE. Resolve the 6 BLOCKING items (1 shim ordering, 2 codesign, 3 PlistBuddy forms and identity read, 4 Exec quoting, 5 status extraction and output, 6 dry-run format) and fold in the MINORs; none requires a design change, only precision. Re-submit for one more critic pass on items 1-6 only.

## Iteration 2

Iteration-1 BLOCKING items: 1 shim ordering RESOLVED (command -v first, never prepend, AC4). 2 codesign RESOLVED (step 11, AC2). 3 PlistBuddy forms RESOLVED (verbatim -c strings, Print identity read). 4 Exec quoting RESOLVED (always quoted, AC5). 5 status extraction RESOLVED (VibeLauncherPath key, fixed lines, AC8). 6 dry-run format RESOLVED (reuses _link_print_argv, source block, no creation). MINORs 7-15 addressed or reasonably declined (help budget 78 vs 76 is fine: the replacement is net zero or negative).

### Concerns

1. BLOCKING - AC2 says "the ten PlistBuddy calls", but build steps 2-10 are NINE PlistBuddy calls (steps 1 and 11 are osacompile and codesign; AC1's "eleven build steps" is right). Generator and Tester will disagree. Fix: "nine".
2. BLOCKING - AC3 injects `SHIM_FAIL=mv`, but the shim list has no `mv` shim. Either add an `mv` shim that delegates to the real mv unless SHIM_FAIL=mv (and say the recorder log then names mv), or drop mv from AC3's failure list.
3. MINOR - AC3's "osacompile absent from PATH and from its fallback path" holds only on Linux. On a Mac the fallback exists, so the real osacompile and lsregister would run under the fixture HOME. Mark that case Linux-only (skip on Darwin), or make the fallback overridable by an env var that tests point at a nonexistent path.
4. MINOR - Dry run: say whether `lsregister-u` and `rm` blocks print only when a vibe bundle already exists (AC1 has none). If PlistBuddy is neither a shim nor present (Linux box) and a bundle exists, the identity read fails and is treated as foreign, so dry run refuses; state that.
5. MINOR - AC6's non-executable launcher must be run as `bash <copy>` since it cannot be exec'd directly; note it.

### Verdict

REVISE (minor): fix BLOCKING 1 and 2 (one-line edits each); no further critic pass needed.
