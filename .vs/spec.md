# task_062 — `vibe link`: registry, URL handling, confirmation and terminal launch — 2026-10-31 (rev 3 after Spec Critic)

## Task summary

Host-side (Mac/Linux shell) support in the `vibe` launcher for a `vibe://` link that opens an interactive vibe session in a registered project, in the user's preferred terminal. This slice is the bash: the subcommand, the consent registry, strict URL parsing, the per-click confirmation and rate limit, and the terminal launchers, all testable in the container through a dry-run mode and PATH shims. Registering the URL scheme with the OS (`vibe link --install`: the `osacompile` applet and the Linux `.desktop` file) is the next slice. Sketch: `/brain2/andeye/Task&I-vibe-embedding-options.md` §7; product rule: `Task&I-spec.md` §10.1. Security model mirrors `vibe codex allow` (task_045): the URL is a request, the registry on this machine is the consent, nothing inside a container can reach the registry, and a link only ever starts an interactive `vibe` that waits for the user.

## Design decisions (binding)

### Dispatch and subcommands

- Two dispatch blocks before `parse_vibe_args`, next to the `codex` block: `vibe link …` and `vibe link-open <url>` (the latter is exactly `vibe link open <url>`; the OS handler passes one argument). Like `codex`, a project folder literally named `link` can no longer be launched by name; plain `vibe` and `vibe --version` are unaffected.
- `vibe link allow [name]` registers the current directory (`pwd -P`); there is no path argument. `vibe link deny <name>`, `vibe link list`, `vibe link terminal <name>`, `vibe link open <url>`.
- Exit codes and fixed message substrings (tests assert both):

| case | exit | stderr/stdout must contain |
|---|---|---|
| bare `vibe link`, unknown subcommand, wrong arg count | 1 | `Usage: vibe link` |
| `allow` ok (new or idempotent) | 0 | `allowed: <name> -> <path>` |
| `allow` refused (bad name, bad path, not a git work tree, name taken by another path, path already registered under another name, symlinked registry) | 1 | `refused:` |
| `deny <name>` (present or absent) | 0 | (nothing required) |
| `deny` with a bad name | 1 | `refused:` |
| `list` | 0 | one line per valid entry `  <name>  <path>` plus ` (no confirm)` when `noask`; `(none)` when empty, missing or unusable |
| `terminal <name>` ok | 0 | `VIBE_TERMINAL=<name>` |
| `terminal` with a bad name or symlinked config | 1 | `refused:` |
| `open` launched, or dry run | 0 | |
| `open` with a refused URL | 2 | `refused URL` |
| `open` with an unknown, invalid or vanished project, or a `tty=` not valid on this OS | 2 | `no vibe project called` / `not available on this system` |
| `open` rate-limited | 3 | `opened less than 5 seconds ago` |
| `open` cancelled, or no way to confirm (Linux without zenity) | 4 | `cancelled` / `cannot ask for confirmation` |
| `open` with an unusable registry (symlink, group/other bits, unreadable mode) | 5 | `⚠` |
| `open` when the launcher's own canonical path fails the path allowlist | 7 | `refused: launcher path` |
| `deny` against a symlinked registry | 1 | `refused:` |
| `open` with no usable terminal on Linux (none configured or the configured one not installed) | 6 | `vibe link terminal` |

### Shared validation (one helper each, used everywhere)

- **Name**: `^[a-z0-9][a-z0-9._-]{0,63}$`. With no name, `allow` uses the cwd basename lowercased with `tr 'A-Z' 'a-z'`, refusing if the result fails the regex.
- **Path allowlist** (the injection defence; no per-terminal escaping is relied on): ASCII only, `^/[A-Za-z0-9 ._/+@,:=~-]+$`, no `//`-free requirement, ≤ 1024 bytes. Applied at `allow` (the `pwd -P` path), to every registry line at read time, and to the launcher's own canonical path. This refuses `'`, `"`, `\`, `$`, backtick, `;`, `|`, `&`, `<`, `>`, `(`, `)`, `*`, `?`, `!`, `#`, tab, newline and any control or non-ASCII byte.
- **Task ref**: exactly the regex `parse_vibe_args` uses for `--task` (copy it into a variable; do not change the parser).
- **Terminal names**: Mac `Terminal`, `iTerm`, `Ghostty`, `kitty`, `WezTerm`; Linux `Ghostty`, `kitty`, `WezTerm`, `gnome-terminal`. Case-sensitive. Mac default `Terminal`; Linux has no default.
- All regex tests run with `LC_ALL=C`, the regex held in a variable and expanded unquoted in `[[ =~ ]]`.

### Registry `~/.vibe/link-projects`

- Path: `$HOME/.vibe/link-projects`; chmod 600. Usability exactly as `codex_registry_usable` (symlink, any group/other bit, or unreadable mode → unusable; missing → usable and empty).
- Line grammar: `<name>=<path>` optionally followed by exactly `\tnoask` (a literal tab then `noask`). Split at the first `=`. A line is valid only if the name passes the name regex, the path passes the path allowlist, and the suffix is empty or exactly `\tnoask`. Invalid lines are skipped with one `⚠ ignoring invalid line N in ~/.vibe/link-projects` per line. If two valid lines share a name, every line for that name is ignored with a ⚠ and the name counts as unregistered. Names are compared as exact strings; registry text never reaches `grep -E`, `sed` patterns or an unquoted `=~`.
- Writers (`allow`, `deny`, "Always") refuse a symlinked registry, create `~/.vibe` if needed, rewrite through `mktemp` in the same directory then `mv`, then `chmod 600`. "Always" rewrites that project's line in place with the `\tnoask` suffix; it never appends a second line. Repairing a 644 file to 600 (writers only) prints `note: existing entries in ~/.vibe/link-projects are now trusted`.
- One name per path: `allow` refuses a path already registered under another name.
- At `open`, the registered path must still exist as a directory and `cd <path> && pwd -P` must equal the stored string (a path swapped for a symlink does not retarget consent); otherwise exit 2.

### URL grammar (normative order; nothing touches the filesystem until step 6)

1. `LC_ALL=C`; `${#url}` ≤ 1024 bytes.
2. Whole URL matches `^vibe://open/?\?[A-Za-z0-9._~:/&=-]+$`. Scheme and host are lowercase only. This refuses `%`, space, `;`, tab, newline, ESC, `#`, `+` and anything else. The `:` and `/` in the charset exist so `task=taskandeye://node/<uuid>` parses.
3. Split the query on `&`. Every pair must contain exactly one `=` with non-empty key and value; an empty pair (`&&`, leading or trailing `&`) refuses.
4. Keys are case-sensitive. Known keys: `project` (required, name regex), `task` (optional, task-ref regex), `tty` (optional, any name from the union of the Mac and Linux terminal lists; anything else refuses here). A duplicated known key refuses; unknown keys, duplicated or not, are ignored.
5. Any refusal in 1–4 → exit 2 `refused URL`, with no registry read, no dialog, no stamp, no other file touched.
6. Registry lookup (exit 2 `no vibe project called`), then terminal resolution (a `tty=` not valid on this OS → exit 2 `not available on this system`; no usable terminal → exit 6), then the stamp check (exit 3), then confirmation (exit 4), then launch. No dialog and no stamp before terminal resolution succeeds.

### Terminal preference

- `vibe link terminal <name>` writes to `$CONFIG_FILE` (which honours `VIBE_CONFIG`). It refuses a symlinked config, replaces every existing line matching `^[[:space:]]*(export[[:space:]]+)?VIBE_TERMINAL=` with exactly one `VIBE_TERMINAL=<name>` (no quotes, no `export`), preserves all other lines and the file mode, creates the file 600 if absent, and rewrites via `mktemp` in the same directory then `mv`.
- At `open`, precedence: URL `tty=`, then `$VIBE_TERMINAL` (the config is sourced at launcher start, so a config value wins over the environment; tests set it in config), then the OS default. The value is re-validated against the OS's terminal list at use time; an invalid configured value prints a ⚠ and falls back to the default on Mac, or exit 6 on Linux.
- A configured terminal whose program is not installed (`command -v` for CLI terminals; on Mac, not checked) → exit 6 on Linux.

### Confirmation and rate limit

- Rate limit: `$HOME/.vibe/link-last/<name>`; mtime read with `stat -c %Y || stat -f %m`. Checked after registry lookup and before the dialog: age 0–4 s → exit 3; a future mtime (age < 0) is not limited. The stamp is written after confirmation succeeds and immediately before launch (a cancelled dialog does not consume it; a launch failure does).
- Confirmation is skipped when the registry line has `noask`. Otherwise:
  - `VIBE_LINK_ASSUME=open|always|cancel` replaces the dialog (test and scripting hook, documented as such; anything able to set the Mac's environment could already run vibe). Any other value counts as `cancel`. `always` rewrites the line with `noask`, also in dry-run mode.
  - Mac: `osascript -e 'display dialog …'` with buttons `Cancel`, `Always for this project`, `Open`, `default button "Cancel"`, `cancel button "Cancel"`, `giving up after 60`. The text shows only the registry name and path (both already allowlisted). A cancel, timeout or osascript error → exit 4.
  - Linux: `zenity --question --no-markup` when `command -v zenity` succeeds (Open/Cancel only; no "Always"); otherwise exit 4 `cannot ask for confirmation`. There is no terminal y/N prompt.
- Unknown-project dialog on Mac (exit 2): `No vibe project called <name>. Run "vibe link allow" in its folder.`; `<name>` has passed the name regex, and no other URL text is ever shown. No dialog is shown for a refused URL or exits 3 and 5 (stderr only).

### Launch

- The command run in the new terminal is `cd '<path>' && exec '<vibe>'`, plus ` --task '<ref>'` when a task was given. `<path>` comes from the registry and `<vibe>` is this launcher's canonical path; both have passed the path allowlist, so neither single nor double quotes can be closed. The task ref regex admits no quote either.
- Per terminal (every external command is invoked by bare name so a PATH shim wins: `osascript`, `open`, `kitty`, `wezterm`, `ghostty`, `gnome-terminal`, `zenity`, `uname`, `stat`):
  - Terminal: `osascript -e 'tell application "Terminal" to do script "<cmd>"' -e 'tell application "Terminal" to activate'`
  - iTerm: `osascript -e 'tell application "iTerm" to create window with default profile command "<cmd>"'`
  - Ghostty: Mac `open -na Ghostty --args --working-directory=<path> -e <vibe> [--task <ref>]`; Linux `ghostty --working-directory=<path> -e <vibe> [--task <ref>]`
  - kitty: Mac `open -na kitty --args --directory <path> <vibe> [--task <ref>]`; Linux `kitty --directory <path> <vibe> [--task <ref>]`
  - WezTerm: Mac `open -na WezTerm --args start --cwd <path> -- <vibe> [--task <ref>]`; Linux `wezterm start --cwd <path> -- <vibe> [--task <ref>]`
  - gnome-terminal (Linux): `gnome-terminal --working-directory=<path> -- <vibe> [--task <ref>]`
- The optional `--task <ref>` pair is an array that may be empty; expand it as `${arr[@]+"${arr[@]}"}` (bash 3.2 under `set -u`).
- Whether terminals started by `open -na` get a login shell with `docker` on PATH is a Mac manual-test item (Test 68), not tested here.

### Dry run

`VIBE_LINK_DRY_RUN=1` runs everything (validation, registry, stamp check, confirmation decision, `always` rewrite) except that it executes no dialog and no launch, and writes no stamp. It prints, in order, an optional dialog block then a launch block:

```
DRYRUN dialog
  argv: osascript
  argv: -e
  argv: display dialog "…" …
DRYRUN launch
  argv: osascript
  argv: -e
  argv: tell application "Terminal" to do script "cd '/p' && exec '/v'"
  argv: -e
  argv: tell application "Terminal" to activate
```

One `  argv: ` line per argument, exactly. The dialog block appears only when a real dialog would be shown (no `noask`, no `VIBE_LINK_ASSUME`). Exit 0.

### Portability (macOS bash 3.2)

No `${var,,}`/`${var^^}`, associative arrays, `mapfile`/`readarray`, `local -n` or `readlink -f`; use `cd … && pwd -P` and the `_codex_canonical_path` sentinel trick; portable `stat`/`mktemp` idioms already in the launcher; empty-array expansion as above.

### Docs

`_usage_text`'s header comment block gains `vibe link allow|deny|list|terminal|open` lines and a note that `vibe link --install` (registering the link with macOS/Linux) is coming in the next release. `README.md` gains a short "Open vibe from a link" section. `MANUAL-TESTS.md` gains Test 68 (one checklist line per terminal, plus iTerm's application name and login-shell PATH), to be run on the Mac after the install slice.

## Acceptance criteria

All run the launcher with `HOME` a temp dir, `VIBE_CONFIG` unset, env built via `smoke/_core.py`'s `_isolate_extras_env`, stdin `/dev/null`, and a PATH shim directory providing `uname` (Darwin or Linux) plus recorders for every external command.

- **AC1 allow/list/deny.** In a temp git repo `demo`: `vibe link allow` exits 0 with `allowed: demo -> <pwd -P>`, the registry contains exactly `demo=<path>` and is mode 600; a second `allow` leaves the file byte-identical; `list` prints `  demo  <path>`; `deny demo` exits 0 and leaves the registry 600 without the line; `deny demo` again exits 0; `list` then prints `(none)`.
- **AC2 allow refusals.** Exit 1 with `refused:` and the registry unchanged for: `allow Demo`, `allow 'de mo'`, a 65-char name, a cwd that is not a git work tree, a cwd path containing `'`, `"`, `$`, a backtick, or a non-ASCII byte, a name already registered to another path, a path already registered under another name, and a symlinked registry. A 644 registry is repaired to 600 by `allow` with the `now trusted` note.
- **AC3 Registry fail-closed and line grammar.** A symlinked or 644 registry makes `open vibe://open?project=demo` exit 5 with a `⚠` line and no recorder call; `list` prints `(none)` exit 0. A hand-written registry with lines `bad name=/x`, `demo2=/tmp/x$(touch PWNED)`, `demo3=/tmp/ok\tbogus`, and two `dup=` lines: each of those names opens with exit 2, a `⚠ ignoring invalid line` (or duplicate) line appears, and no file `PWNED` is ever created anywhere under the temp dir.
- **AC4 URL refusals.** Each of these exits 2 with `refused URL`, no recorder call, and the registry and stamp directory untouched (mtimes unchanged): `http://open?project=demo`, `VIBE://open?project=demo`, `vibe://OPEN?project=demo`, `vibe://run?project=demo`, `vibe://open?task=ABBR-1`, `vibe://open?project=Demo`, `vibe://open?project=../x`, `vibe://open?project=demo;id`, `vibe://open?project=demo%20x`, `vibe://open?project=demo&project=demo`, `vibe://open?project=demo&&task=ABBR-1`, `vibe://open?project=demo&`, `vibe://open?project=demo&task=ABBR-1;x`, `vibe://open?project=demo&task=`, `vibe://open?project=demo&tty=Hyper`, `vibe://open?project=demo#x`, a URL containing a newline, a tab or ESC, and a 1025-byte URL. `vibe://open?project=nothere` exits 2 with `no vibe project called`.
- **AC5 Darwin dry-run, Terminal.** With `demo` registered, `VIBE_LINK_DRY_RUN=1 VIBE_LINK_ASSUME=open`: `open 'vibe://open?project=demo'` prints no dialog block and a launch block whose argv lines are exactly `osascript`, `-e`, `tell application "Terminal" to do script "cd '<path>' && exec '<vibe>'"`, `-e`, `tell application "Terminal" to activate`, where `<vibe>` is the launcher's canonical path; with `&task=ABBR-12` the third argv ends `exec '<vibe>' --task 'ABBR-12'"`; with `&task=taskandeye://node/<uuid>` likewise; with `&foo=bar&foo=baz` the result equals the no-extra-key case; `vibe link-open <url>` prints the same as `vibe link open <url>`.
- **AC6 Per-terminal dry runs.** With `VIBE_TERMINAL=<x>` written into `$HOME/.vibe/config`, the launch block's argv equals the design's list for iTerm, Ghostty, kitty and WezTerm on Darwin, with `<path>`, `<vibe>` and the task pair substituted; `tty=kitty` in the URL overrides a configured `Terminal`; `tty=iTerm` on the Linux shim exits 2 `not available on this system`; on Linux with no `VIBE_TERMINAL`, exit 6 mentioning `vibe link terminal`; with `VIBE_TERMINAL=gnome-terminal` and a `gnome-terminal` recorder on PATH, the gnome-terminal argv; with `VIBE_TERMINAL=kitty` but no `kitty` on PATH, exit 6; a configured `VIBE_TERMINAL=Hyper` on Darwin prints a `⚠` and uses Terminal.
- **AC7 `vibe link terminal`.** `terminal kitty` with no config creates `$HOME/.vibe/config` mode 600 containing exactly `VIBE_TERMINAL=kitty`; with a config containing `FOO=1`, `export VIBE_TERMINAL="iTerm"` and ` VIBE_TERMINAL=Ghostty`, the result is `FOO=1` and exactly one `VIBE_TERMINAL=kitty` line, mode preserved; with `VIBE_CONFIG` pointing elsewhere, that file is the one written; `terminal Hyper` exits 1 `refused:`; a symlinked config exits 1 and is not followed.
- **AC8 Confirmation.** Darwin, dry run, no `VIBE_LINK_ASSUME`: a dialog block precedes the launch block, its `display dialog` script contains the name and path, `default button "Cancel"` and `giving up after 60`, and no other URL text (a `&foo=SENTINELX` in the URL does not appear). `VIBE_LINK_ASSUME=cancel` and `VIBE_LINK_ASSUME=bogus` exit 4 `cancelled` with no recorder call. `VIBE_LINK_ASSUME=always` exits 0 and rewrites the line to `demo=<path>\tnoask` (one line, file 600); afterwards `VIBE_LINK_ASSUME=cancel` still launches and prints no dialog block, and `list` shows ` (no confirm)`. Linux without `zenity` on PATH and no ASSUME: exit 4 `cannot ask for confirmation`; with a `zenity` recorder: the dialog block's argv starts `zenity`, `--question`, `--no-markup`.
- **AC9 Rate limit.** Real runs (no dry run) with `VIBE_LINK_ASSUME=open` and an `osascript` recorder: the first open exits 0, calls the recorder once and writes the stamp; a second open exits 3 with no further recorder call; after `os.utime` sets the stamp 10 s in the past, a third open runs; with the stamp 60 s in the future, an open runs; a cancelled open (`VIBE_LINK_ASSUME=cancel`) on a fresh project writes no stamp.
- **AC10 Launch-path containment.** With the launcher copied (with its `devcontainer/` sibling it needs) to a temp path containing `"` (or `$`), `open` exits 7 `refused: launcher path` and no recorder is called; the recorder never receives an argv containing `$(`, a backtick or an unbalanced `"`.
- **AC11 Help and docs.** `vibe --help` contains `vibe link allow`, `vibe link open` and `--install`; `README.md` contains `Open vibe from a link`; `MANUAL-TESTS.md` contains `Test 68`; `CHANGELOG.md` mentions `vibe link`.
- **AC12 No collateral change (baseline-free).** `vibe --version` prints the contents of `VERSION`; `vibe codex list` with an empty HOME prints `(none)`; `vibe --help` still contains `vibe codex allow`, `vibe repos add` and `vibe clean`; `vibe link` with no args does not start Docker (a `docker` recorder on PATH is never called by any `vibe link` command in this suite).
- **AC13 Gates.** `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null` exits 0 (the new tests called from `runner.main()`). The Evaluator also checks once, outside the suite, that `git diff` of `vibe` touches only the new functions, the two dispatch blocks and the help header.

## Out of scope

- `vibe link --install` (applet, `.desktop`, `lsregister`, `xdg-mime`): next slice; only the help-text mention lands here.
- Any change to `init-firewall.sh`, hooks, `settings.local.json`, the Dockerfile, `devcontainer/commands/*`, the Task&I client, `parse_vibe_args`.
- Detecting an already-running container for the project (README note only).
- Warp, Alacritty, Hyper, xterm.
- A machine-wide rate limit across projects.

## Test location

`smoke/checks_48_vibe_link.py` (new, ≤ 1,500 lines) plus its import line and one `runner.main()` call per `test_*` function in `smoke/runner.py`. Tester-owned and immutable once committed.

## Proposed budget

3 cycles.

## Model plan

- Planner + Evaluator: the lead (Opus 5.5).
- Spec Critic: sonnet.
- Generator: opus (a URL feeding a shell is security-critical), ceiling opus.
- Tester: sonnet (adversarial shell fixtures; haiku's test quality is likely too shallow here), ceiling sonnet.
- Fable rung: not pre-authorised.
- Before the pass commit: `security-review` agent on the diff and `/code-review high` (`vibe` is a hot file per `.vs/review-focus.md`).
