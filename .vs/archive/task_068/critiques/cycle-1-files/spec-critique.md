## Iteration 1

### Verified facts
- The launcher reads ownership via `stat -c %u` / `stat -f %u` on PATH (`_link_owner`); checks_49 shims `stat` for `*%u*` and execs the real stat otherwise. Same technique works for codex-allow, container-testable. Mode uses `stat -L -c %a`, also on PATH.
- Existing pinned codex behaviour: checks_17 (~597-700, 835-870) asserts symlink "symlink", one ⚠, mode-644 "chmod 600", `deny` on a symlinked registry exits 1 with "unusable".

### Concerns

**BLOCKING 1 - "byte-identical" is unachievable with one `<label>` parameter.**
The two registries' messages differ in more than the name:
- codex prints the EXPANDED `${f}` (`$HOME/.vibe/codex-allow`); link prints the literal `~/.vibe/link-projects`.
- Tails differ: "so no project counts as allowed (the Codex opt-in registry must be ... re-run 'vibe codex allow')" vs "so no project can be opened from a link (... 'vibe link allow')"; mode fix text differs ("chmod 600 ${f}" on the Mac vs "'chmod 600 ~/.vibe/link-projects' or 'vibe link allow' again"); the unreadable-mode text differs ("ignored, so no project counts as allowed (fail closed)" vs "ignored (fail closed)").
Spec also says codex has "two messages"; there are THREE (symlink, mode-unreadable, group/other bits). Fix: the helper takes explicit parameters for the display name, the consequence phrase, and the per-message fix text (or the helper returns a reason code and each wrapper prints its own byte-pinned line); state that every existing codex and link line stays literal, including the unreadable-mode one; add AC4 literals for all three.

**BLOCKING 2 - Line cap moves into the usable check, changing link behaviour (contradicts "changes nothing else about either registry").**
Today the link cap is NOT in `_link_registry_usable`; it lives in `_link_registry_load` and `_link_registry_rewrite` (counted with `read ... || [ -n "$line" ]`, so an unterminated last line counts), emitted via `_link_too_long`. The helper's step 6 adds a second counting pass to every usable call (including `_link_registry_usable` called at 3177, 3815, 2797 and writers 2582/2668). Consequences: an extra read per call; `wc -l` undercounts an unterminated final line (1001 lines with no trailing newline passes), so the helper must count the same way as load; the writers' rewrite returns 2 vs the helper's 1 path may change exit codes (callers exit 5 on 2, other codes elsewhere). Fix: either (a) give the helper an opt-in `max_lines` the link wrapper passes as 0/omitted so link behaviour is literally unchanged and only codex uses it, or (b) state precisely the counting method (same loop, unterminated last line counts), prove link return codes and single-⚠ output unchanged, and add a link test with 1001 lines through each caller. Option (a) is lower risk and still satisfies AC6 if AC6 is reworded.

**BLOCKING 3 - AC3 is wrong for `deny`.**
`_codex_deny` calls non-writer `codex_registry_usable` first (line ~2182) and today REFUSES a 644 registry with "unusable" (exit 1), not repair it. Only `allow` (`codex_allow_record`) repairs 644. "They still repair a 644 file to 600, as today" is false for deny. Fix: state allow repairs 644 and deny keeps refusing it (or explicitly change deny to use the writer flag and add that to scope - which contradicts "changes nothing else"). Also say what `deny` prints for the new refusals: it will print the helper ⚠ plus the existing "is unusable - refusing to rewrite it" line (two lines, exit 1); specify it, and note checks_17 pins "unusable".

**BLOCKING 4 - Writer refusal order and exit outcomes unspecified, and `~/.vibe` writability check is skipped for a missing file.**
Spec says writers refuse "before touching the file" but `codex_allow_record` currently runs newline check -> symlink check -> `mkdir -p` -> `touch` -> `chmod`. Specify: newline check, then `codex_registry_usable writer` (which subsumes the symlink check, but the existing writer symlink message "refusing to write through it" must be kept byte-identical or deliberately replaced - say which), then mkdir/touch/chmod. Also: helper returns 0 for a missing file, so a first-ever `allow` into a group-writable `~/.vibe` succeeds (the same gap exists for link; fine to keep, but state it, and say AC3's "group-writable `~/.vibe`" case needs an existing file). Worse: `mkdir -p` under umask 002 (Debian/Ubuntu default) creates `~/.vibe` as 775, so `allow` would succeed and the very next `list`/launch would refuse with the new dir check - a regression for Linux hosts users. Fix: `codex_allow_record` must `chmod go-w` a directory it just created (or the spec must explicitly accept and document it), with a test under `umask 002`.

**MINOR 5 - `codex_allow_remove` has no usable gate of its own.**
Spec says remove refuses foreign owner etc. "before touching the file", but today it is gated only by its callers (deny). The direct-call tests (`_codex_rc_call ... codex_allow_remove`) need it to carry the writer check itself; say so, and that a missing file still returns 0 (idempotent) before any check.

**MINOR 6 - Renaming `_link_mode/_link_owner` is churn with risk.** Aliases as bash functions are fine in 3.2, but `_link_mtime` is left unrenamed, and `grep -n _link_mode` shows callers at ~2586, 2676, 2838. Simplest: do not rename; codex uses `_link_mode`/`_link_owner` as they are. If renamed, define aliases as wrapper functions (not `alias`, which does not expand in non-interactive scripts).

**MINOR 7 - AC1 observability.** "an allowed project's launch does not mount the Codex login" - name the mechanism (`_codex_opted_in` via `_codex_rc_call`, or `codex_allowed`, as checks_17 does). Under the stat shim, `_codex_opted_in` also emits a second ⚠ (the helper's, plus none from the "not in registry" line since it fires when `codex_allowed` is false: it WILL print both). Assert on ⚠ count accordingly. Also the shim must handle `%u` only; do not shim `%a`.

**MINOR 8 - AC2 shim detail.** Mode-200 file: `-r` is true for root (container may run as root in tests? user is `node`, so ok) but a test run as root would not fail `-r`. Skip or guard that case when `os.geteuid()==0`. The 775 `~/.vibe` case: chmod the dir in the temp HOME, restore after. 1001 vs 1000 lines: specify trailing-newline form.

**MINOR 9 - AC6 grep is brittle.** Greping function bodies for `stat`/`-r` is fine, but define exact method (extract body between `name() {` and the next top-level `}`), and assert `_vibe_consent_registry_usable()` is defined once. The shim for `stat` also affects `id`? No. OK.

**MINOR 10 - bash 3.2 traps.** `${mode: -3}` (space) is already used and is 3.2-safe; avoid `${var,,}`, `local -n`, `mapfile`, `[[ =~ ]]` quoting changes, and `printf -v` with arrays. `local a=$1 b=$2` style fine. Don't use `read -d ''` or `wc -l <` with BSD padding (`$(( $(wc -l < f) ))` or arithmetic compare, since BSD wc pads spaces). The `case` on `[0145][0145]` for dir bits must be copied verbatim.

**MINOR 11 - AC5 wording.** Also run checks_48/49/56 only isn't enough if BLOCKING 2 option (b) is taken; add the link 1001-line test. Also new test file name collision: `checks_65` is free (verified).

### Verdict
NOT READY - fix BLOCKING 1-4 and re-submit. The direction (one shared helper) is sound; the spec over-promises "byte-identical" and "behaviour unchanged" in three places.

## Iteration 2

Spec title says "rev 2". Verified against `vibe` (codex_registry_usable 1935, codex_allow_record 1990, codex_allow_remove 2011, _codex_deny 2176, _link_registry_usable 2415) and checks_17.

### Iteration-1 BLOCKING items
- B1 (byte-identical vs one label): RESOLVED. Helper now returns a reason code; each wrapper prints its own literal line. The three existing codex strings (symlink, "permissions could not be read", "readable or writable by group or others") are real, and AC5 pins them plus the link messages as literals.
- B2 (line cap in usable): RESOLVED. The cap stays in the link load/rewrite; only codex applies it, after `ok`, with the same `read ... || [ -n "$line" ]` counting. Link return codes are untouched.
- B3 (deny repairs 644): RESOLVED. `_codex_deny` keeps the non-writer check and refuses 644; allow repairs. Two-line output (helper line plus "unusable", exit 1) is specified.
- B4 (writer order, umask): RESOLVED. Order is newline, symlink, writer check, mkdir (+ `chmod go-w` if just created), touch/chmod/append. Missing-file-in-775-dir is documented; AC4 tests umask 002. Line 5120's `mkdir -p "$HOME/.vibe"` is in main startup, not in the codex subcommand path, so AC4 is valid.

### MINORs from iteration 1
5 (remove gate): addressed. 6 (no rename): addressed. 7 (observability, mechanism named; ⚠ count not stated): partly, see 12. 8 (root skip, trailing newline): addressed. 9 (body extraction, single definition): addressed. 10 (bash 3.2): addressed. 11: addressed.

### Concerns

No BLOCKING.

**MINOR 12 - Wrappers need the mode value, but the helper only echoes a reason code.** The existing lines include `(mode ${mode})` (codex and link loose-mode) and `(mode ${dmode:-unknown})` (link dir line). The spec doesn't say how the wrapper gets them (second `_link_mode` call in the wrapper, or a global set by the helper). AC7 forbids `stat` in wrapper bodies, but `_link_mode` is not `stat`, so a re-read is allowed. State it, and that AC5 asserts the `mode NNN` text. Also the assertion should count ⚠ lines when `_codex_opted_in` is used (it prints the helper line only if the marker and git checks pass).

**MINOR 13 - Inaccurate claim about checks_17.** The spec says deny refusing a 644 file "checks_17 pins". checks_17 pins deny on a SYMLINK ("unusable", line ~857) and `codex_registry_usable` on 644 (one ⚠, "chmod 600"); deny on a 644 file is not pinned there. AC3 does test it, so no gap, but fix the wording.

**MINOR 14 - AC7 grep on "stat" substring.** A body-level grep for `stat` can match comments or words like "state"/"status". Specify word-boundary `\bstat\b` on non-comment lines, or the test will be brittle.

### Verdict
READY. All four BLOCKING items resolved; the remaining items are MINOR wording and can be fixed during implementation.
