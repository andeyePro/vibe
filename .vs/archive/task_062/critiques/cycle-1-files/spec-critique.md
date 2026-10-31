# Spec Critic: task_062 `vibe link` — critique

Verdict: **revise** (9 BLOCKING, the rest MINOR). The shape is right (registry = consent, URL = request). The holes are in quoting, in what exactly gets printed and asserted, and in two ACs that cannot be tested permanently.

## Concerns

1. **[Launch command / Registry] BLOCKING — AppleScript string injection through the registry path.** The Terminal/iTerm command is embedded inside an AppleScript double-quoted string (`do script "cd '<path>' && exec '<vibe>'"`). The spec only refuses `'` at `allow` time. A path or vibe path containing `"` or `\` closes the AppleScript string, and AppleScript can then run `do shell script`. The same string is used by `display dialog`. A hand-edited registry line, or a legitimate dir name containing `"`, reaches it. Fix: define one positive path allowlist, e.g. `^/[A-Za-z0-9 ._/+@,:=~-]+$`, ASCII only and no control chars. Apply it in three places: at `allow`, when reading each registry line, and to the launcher's own canonical path. Anything else is refused. State that the allowlist, not per-terminal escaping, is the defence. This replaces "a `'` in the path is refused" and also covers `$(…)`, backticks, `<>&` (zenity Pango markup), newline and tab. Also pass `--no-markup` to `zenity` as defence in depth.

2. **[AC10 vs Design] BLOCKING — contradiction and undefined "exit 5-class".** AC10 says the path `/tmp/x$(touch /tmp/pwned)` is "refused at allow", but the design only refuses `'` and newline. `$(...)` is safe inside single quotes, so a Generator following the design would accept it. AC10 also says a hand-written bad line gives "exit 5-class ⚠, registry line ignored". Exit 5 is defined as "registry unusable" (symlink or mode), not "one bad line". Fix: with the allowlist from (1), `allow` exits 1 on a bad path. A malformed or disallowed line at read time is skipped with one ⚠ line to stderr, so the project behaves as unregistered (exit 2). Only symlink or mode problems give 5. Make AC10 assert exactly that.

3. **[Registry format] BLOCKING — the line grammar is under-specified.** "`name=path[\tnoask]`" does not say how to split. Does the path may contain `=` or a tab? "A path containing a newline or `=`-free line is never written or read" is garbled. Fix: split at the first `=`. The name must match the name regex and the path must match the allowlist, so a tab can only be the `\tnoask` separator. The only valid suffix is exactly `\tnoask`. Any other suffix invalidates the line. Duplicate names in a hand-edited file: ignore all lines for that name with a ⚠. Match names with exact string comparison, never `grep -E` and never an unquoted `=~` on registry data. Rewrites for `deny` and "Always" go through mktemp, then `mv`, then `chmod 600`, as in `codex_allow_remove`. "Always" must rewrite the existing line in place. The spec says "appends `\tnoask`" without saying how. Say it is a rewrite, not a second line.

4. **[Output format] BLOCKING — dry-run output is not defined.** "One argv element per line, `osascript` scripts verbatim" is not enough for a Tester to assert on. A launch command can be several commands (the Terminal case has two `-e` scripts, and a dialog can precede it), and AC8 needs to assert that the dialog is absent when `noask` is set. Fix: specify a framing, for example:
   - Each command starts with a line `DRYRUN dialog` or `DRYRUN launch`.
   - Then one argv element per line, each prefixed by a fixed marker such as `  argv: `.
   - Argv elements containing a newline are refused earlier.
   Also state the order (dialog block first, then launch block). A dry run with an unset `VIBE_LINK_ASSUME` on Darwin prints both blocks and exits 0. State whether `VIBE_LINK_ASSUME=always` in dry-run mode still writes `noask`. AC8 needs this, so say yes.

5. **[AC12] BLOCKING — not permanently testable.** `git show HEAD:vibe` is the baseline. The test is committed and immutable, and after the pass commit HEAD contains the change, so the check is vacuous or the help diff fails. CLAUDE.md § Testing forbids fixed-baseline pins that drift. Fix: make AC12 a one-time Evaluator check outside `smoke/`, or replace it with permanent assertions that need no baseline: `--version` equals `VERSION`; `vibe codex list` prints `(none)` with an empty HOME; every pre-existing help line is still present (compare against a stored list of key lines, or just assert `usage` still mentions `codex`/`repos`); a non-`link` first arg still reaches the parser. Also say so for AC11's "TODO closed in the pass commit": that is a process step, not a Tester AC.

6. **[Config / Terminal preference] BLOCKING — how `VIBE_TERMINAL` is read and written is unstated.** The launcher already runs `source "$CONFIG_FILE"` at the top (line ~114), before any dispatch, so config is executable shell. The registry hardening does not extend to config. Fix, and state it in the spec:
   - `vibe link` consumes only the sourced `$VIBE_TERMINAL` variable and re-validates it against the allowlist at use time. A bad value is a ⚠ and falls back to the default, or refuses; pick one.
   - The writer writes only `VIBE_TERMINAL=<allowlisted-name>` (no quotes, no `export`).
   - The writer replaces all existing `VIBE_TERMINAL=` lines, whatever their form, with exactly one.
   - It uses the existing `$CONFIG_FILE`, which honours `VIBE_CONFIG`, not a hard-coded `$HOME/.vibe/config`.
   - It rewrites via a temp file in the same directory and preserves the mode, or creates the file 600.
   - Precedence is `tty=` URL, then config, then default. Also say whether a `VIBE_TERMINAL` environment variable counts. Since config is sourced, config wins over env when both set it, so the Tester cannot rely on env alone. AC6 and AC7 should say "in config".

7. **[URL grammar] BLOCKING — no exact parse algorithm, so the Generator and Tester will diverge.** The spec lists refusals but not the algorithm, and the AC4 list relies on unstated rules. Fix with a normative procedure:
   - Run under `LC_ALL=C` so `${#url}` counts bytes and `[[ =~ ]]` is ASCII.
   - Allow the whole URL only if it matches `^vibe://open/?\?[A-Za-z0-9._~:/&=-]+$` (query charset explicit). This rejects `%`, space, `;`, tab, newline, ESC and `#`.
   - Split the query on `&`. Every pair must contain exactly one `=` with a non-empty key and a non-empty value. An empty pair (`&&`, trailing `&`) refuses the URL.
   - Keys are case-sensitive.
   - A duplicate known key refuses. State whether a duplicate unknown key is tolerated (suggest yes, ignored).
   - Scheme and host are lowercase only. `VIBE://` and `vibe://OPEN` are refused.
   - The `task` charset must permit `://` and `-`. Say the query charset above is deliberate so AC5's `task=taskandeye://node/<uuid>` passes.
   - Reuse the exact `--task` regex from `parse_vibe_args`. Do not change the parser (AC12). The spawned `vibe` re-validates it anyway.
   - Validation completes before the registry is even opened (no dialog, no stamp, no filesystem touch on a refused URL). Tester asserts that.

8. **[Exit codes / messages] BLOCKING — gaps that a Tester has to guess.**
   - Linux with no usable terminal (AC6: "default refuses with a message naming `vibe link terminal`"): which exit code? Suggest 1 for config problems or add a dedicated exit; right now it is outside the table.
   - `tty=` naming a terminal that is not valid on this OS (e.g. `iTerm` on Linux): exit 2.
   - Registry path no longer exists or is no longer a directory: exit 2. Also re-canonicalise the registered path and require it to equal the stored string (a swapped symlink must not retarget a consent).
   - `deny <missing>`, `list` on empty or unusable registry, bare `vibe link`, unknown subcommand, extra args: say exit codes. Mirror codex: usage exit 1, `list` always exit 0 with `(none)`, `deny` of an absent name is idempotent exit 0.
   - Which messages are asserted: tests should assert exit code plus a short fixed substring per case. List those substrings (including the `list` line format, the `allow` success line, and the ⚠ line). AC1's "prints the line" is ambiguous; define `list` as `  <name>  <path>` plus ` (no confirm)` when `noask`.
   - `VIBE_LINK_ASSUME` with an unrecognised value must be treated as `cancel` (fail closed).

9. **[AC9 / Rate limit] BLOCKING — semantics and testability.** Missing: when the stamp is written (before the dialog, after confirm, after a successful launch?), how a clock-skewed future mtime is treated, atomicity, and which commands the PATH shim must cover. Fix:
   - Check the stamp after URL and registry validation and before the dialog. Write it after confirmation succeeds and just before launch (a cancelled dialog does not consume it; a launch failure still does).
   - A future mtime (age < 0) is not limited, otherwise a skewed clock locks the project out forever.
   - Read mtime with the repo's portable `stat -c %Y || stat -f %m`.
   - Tests must set the stamp age with `os.utime` (not `touch -d`, which differs on macOS).
   - Every external command (`osascript`, `open`, `kitty`, `zenity`, `uname`) must be invoked by bare name so a PATH shim wins; no `/usr/bin/osascript`.
   - Consider also a machine-wide stamp (e.g. 2 s) so a hostile page cannot cycle projects; MINOR.

10. **[AC2 / allow semantics] MINOR — `allow [name]` vs "(or the given path)".** The Project names bullet says "requires the current directory (or the given path) to be a git work tree", but the grammar is `allow [name]`. Decide: `allow [name]` always registers the cwd; delete "or the given path". Also state whether two names may point at the same path (suggest: refuse, to keep list unambiguous) and that all `allow`/`deny` validation failures exit 1.

11. **[Confirmation] MINOR — unknown-project dialog shows URL text.** The Confirmation bullet says "only registry data, never URL text, is shown", while the unknown-project dialog shows "No vibe project called X". Resolve: X is the name only after it has passed the name regex, so it is safe to show; say so, and say nothing else from the URL is shown. Also, dialogs are the only user-visible channel on a Mac applet (no stderr): exits 3, 4 (cancel is fine silent) and 5 are silent for the user. Say whether 5 and the refused-URL case should also show a short dialog; MINOR UX. Suggest `default button "Cancel"` so a held Enter key cannot approve, and `giving up after 60`. Map a dialog cancel (osascript error) to exit 4.

12. **[Confirmation] MINOR — the `y/N` TTY prompt.** "`vibe link open` typed by hand ... may also read `y/N`" is optional behaviour that no AC covers and that makes the zenity-absent case environment-dependent. Remove it (Linux without zenity and without ASSUME: exit 4) or fully specify it. Tests run with stdin on /dev/null per CLAUDE.md. Also say how to simulate missing zenity (PATH dir without it; note `command -v` must be the check).

13. **[Terminals] MINOR — xterm is undefined.** "`xterm -e <vibe> ...` run with `cd`" has no argv. Either drop xterm (simplest, and no AC covers it) or specify `xterm -e sh -c 'cd "$1" && exec "$2" "${@:3}"' sh <path> <vibe> ...` with the exact shape. Also Ghostty/kitty/WezTerm started by `open -na`/direct exec do not get a login shell: `docker` may not be on PATH. Say the Generator should verify and, if needed, launch via `/bin/sh -lc`-style wrapper on Mac for these, or note it as a manual-test item (Test 68). Check whether `tell application "iTerm"` is correct for iTerm2 (it is `iTerm` on current versions; flag as Test 68 manual verification).

14. **[Bash 3.2 portability] MINOR — the spec should call these out explicitly** for the Generator, since macOS ships bash 3.2 and AC11 must also pass on the Mac:
   - No `${var,,}`; lowercase the cwd basename with `tr 'A-Z' 'a-z'`.
   - No associative arrays, no `mapfile`/`readarray`, no `local -n`, no `${var^^}`, no `read -d ''` tricks.
   - Argv arrays that may be empty (no `--task`) must expand as `${arr[@]+"${arr[@]}"}` under `set -u`, exactly as the existing `TASK_BIND_ENV` comment says. The optional `--task <ref>` pair is precisely this case.
   - In `[[ =~ ]]` put the regex in a variable and expand it unquoted (3.2 quoting differs).
   - No `readlink -f` (absent on older macOS); use `cd … && pwd -P`.
   - `stat -c` vs `stat -f`, `sed -i`, `touch -d` and `mktemp` template differ between GNU and BSD; use the existing portable idioms.
   - No `$(...)` that must preserve trailing newlines; use the sentinel trick from `_codex_canonical_path`.

15. **[Dispatch] MINOR — `link-open` alias and positional `link`.** Add `link` and `link-open` dispatch blocks before `parse_vibe_args`, like `codex`. Note that `vibe link` as a project directory name stops working (same as `codex`/`repos`); AC12-style test should still pass for plain `vibe` and `vibe --version`. The `--help` text is the header comment block of `vibe` (see `_usage_text`), so AC11 means editing that header, and the "next release" `--install` mention must live there too.

16. **[Test location] MINOR.** `smoke/checks_47_*` is free; the spec jumps to 48. Fine if another task is reserving 47, otherwise use 47. The new file needs its `from smoke.checks_48_vibe_link import *` line in `smoke/runner.py` and tests built with `_isolate_extras_env`. A bare `{**os.environ, ...}` is not allowed. Pass `HOME` in a temp dir; also unset `VIBE_CONFIG` so the host's value cannot leak in. Tester should also assert the `/tmp/pwned` file is never created and that `VIBE_LINK_ASSUME`/`VIBE_LINK_DRY_RUN` are documented as test-only (anything able to set the Mac's environment can already bypass the dialog; fine, but say it).

17. **[Registry trust] MINOR — "repairs 644 to 600" blesses whatever is inside.** Same as codex, so acceptable, but add: on repair, say in the output that existing entries are now trusted.

## Verdict

**revise**

BLOCKING items: 1, 2, 3, 4, 5, 6, 7, 8, 9.

## Iteration 2

Iteration-1 BLOCKING status: 1 resolved (positive path allowlist at allow, read, and launcher path; verified the task regex admits no quote, backslash or `$`). 2 resolved (bad line is skipped with a warning, exit 5 only for symlink or mode). 3 resolved (split at first `=`, exact `\tnoask` suffix, duplicates ignored, in-place rewrite). 4 resolved (DRYRUN framing, order, `always` rewrites in dry run). 5 resolved (baseline-free AC12). 6 resolved (`$CONFIG_FILE`, config-over-env precedence, single-line writer, revalidated at use). 7 resolved (normative URL algorithm). 8 resolved except the contradiction in concern 1 below. 9 resolved (stamp timing, future mtime, bare-name shims). MINOR 10-17 all addressed or reasonably declined (machine-wide rate limit declined, xterm dropped, y/N prompt dropped).

### Concerns

1. **BLOCKING - `tty=` on the wrong OS: step 5 and AC6 disagree.** URL step 4 says `tty` must be "a terminal name valid on the current OS", and step 5 says any refusal in steps 1-4 exits 2 with `refused URL`. But the exit table and AC6 expect `tty=iTerm` on Linux to exit 2 with `not available on this system`. A Generator following step 5 prints only `refused URL`, and the AC6 substring then fails. Fix: in step 4 `tty` need only be a terminal name from the union of both OS lists (otherwise `refused URL`, as `tty=Hyper` in AC4). The per-OS check is made at step 6, before the dialog, and exits 2 with `not available on this system`. Or keep it in step 4 and require both substrings in that one message. Pick one in the spec.

2. **MINOR - launcher-path refusal has no exit code or message row.** AC10 accepts "`refused:` or `⚠`, non-zero". Add a table row (suggest exit 5 with `⚠`, or exit 2 with `refused:`) and say it is checked before the dialog and the stamp. Also state how `<vibe>` is derived (`cd "$(dirname "$0")" && pwd -P` plus basename; the file itself is not symlink-resolved, so `~/bin/vibe` stays valid).

3. **MINOR - ordering of terminal resolution (exit 6, exit 2 for tty) versus dialog and stamp is unstated.** Resolve the terminal before the rate-limit check and dialog so a user is not asked to confirm something that cannot launch, and no stamp is consumed. AC6 cases that expect 6 should state `VIBE_LINK_ASSUME=open`.

4. **MINOR - AC3 wording.** `bad name=/x` can never be opened (the URL is refused at the name regex, not "no vibe project called"), and `demo3=/tmp/ok\tbogus` should say "a literal tab". The `⚠` lines come from the registry read triggered by the other opens; say that. Also AC2 contains "a space-free backtick", which is garbled, and the allowlist text "no `//`-free requirement" is garbled; reword (double slashes are allowed).

5. **MINOR - `deny`/`allow` against an unusable registry or `read` quirks.** `deny` with a symlinked registry: say exit 1 `refused:`. Reading must handle a final line with no newline and use `IFS= read -r`.

### Verdict

**revise** (one BLOCKING: concern 1; a one-line spec fix, no redesign).
