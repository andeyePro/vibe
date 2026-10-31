# task_068 — Harden `~/.vibe/codex-allow` like the link registry — 2026-10-31 (rev 2 after Spec Critic)

## Task summary

`~/.vibe/codex-allow` is the host-side consent record that lets a project's container mount the user's ChatGPT/Codex login (task_045). Its usability check, `codex_registry_usable`, refuses a symlink, an unreadable mode, and group/other mode bits. The link registry's check (`_link_registry_usable`, task_062) also refuses:
- a file the user does not own;
- a file the owner cannot read;
- a group- or other-writable `~/.vibe`.

The link loader and rewriter also refuse a file over 1,000 lines.

This task brings `codex-allow` to the same standard by sharing the check logic. Every existing message, exit code and behaviour of both registries stays exactly as it is.

## Design

- **Shared helper: `_vibe_consent_registry_check <file> [writer]`.** It prints nothing. It echoes one reason code and returns 0 for `ok` or `missing`, 1 otherwise. Checks run in this order:
  1. symlink → `symlink`
  2. missing → `missing` (usable)
  3. mode unreadable → `mode_unreadable`, then group or other bits set → `loose_mode`. Both are skipped when `writer` is given.
  4. owner ≠ `id -u`, or owner unreadable → `foreign_owner`
  5. `[ ! -r ]` → `unreadable`
  6. parent directory group- or other-writable, with the `[0145][0145]` case on the last two mode digits copied verbatim, or its mode unreadable → `dir_writable`
  7. otherwise → `ok`

  It uses the existing `_link_mode` and `_link_owner`, which are not renamed.
- **`_link_registry_usable`.** It calls the helper and maps each reason code to its existing `⚠` line, byte for byte (the same `printf` strings as today). Its return values and writer flag are unchanged. The link line cap stays where it is (`_link_registry_load`/`_link_registry_rewrite`), unchanged.
- **`codex_registry_usable [writer]`.** It calls the helper and prints one `⚠` line per refusal.
  - The existing three lines (symlink, permissions could not be read, readable or writable by group or others) stay byte-identical.
  - New lines, each ending `— ignored, so no project counts as allowed` plus a fix:
    - `foreign_owner`: `  ⚠ ${f} is not owned by you (or its owner could not be read) — ignored, so no project counts as allowed (fail closed).`
    - `unreadable`: `  ⚠ ${f} cannot be read — ignored, so no project counts as allowed; run 'chmod 600 ${f}' on the Mac.`
    - `dir_writable`: `  ⚠ $(dirname "$f") is writable by group or others — ignored, so no project counts as allowed; run 'chmod go-w $(dirname "$f")' on the Mac.`
  - After the helper returns `ok` (not `missing`), a line cap of 1,000 is applied. Lines are counted with the same `while IFS= read -r line || [ -n "$line" ]` loop the link loader uses, so an unterminated last line counts. Over the cap prints `  ⚠ ${f} has more than 1000 lines — ignored, so no project counts as allowed.` and returns 1.
- **`codex_allow_record` (allow), in order:**
  1. the existing newline check;
  2. the existing symlink refusal, with its message unchanged (`refusing to write through it`);
  3. `codex_registry_usable writer`, which refuses `foreign_owner`, `unreadable`, `dir_writable` and the line cap with its `⚠` and exit 1, and skips the mode checks so a 644 file is still repaired;
  4. `mkdir -p "$(dirname …)"`, and if that call created the directory, `chmod go-w` it (so a umask 002 host doesn't make the next read refuse);
  5. `touch`, `chmod 600`, and the append, as today.
- **`codex_allow_remove`.** A missing file returns 0 first, which keeps it idempotent. It then runs `codex_registry_usable writer`, and on refusal prints the helper's line and returns 1 without touching the file. `_codex_deny` keeps calling the non-writer `codex_registry_usable` first. So `deny` still refuses a 644 file with today's messages, which checks_17 pins, and refuses the new cases the same way: the new `⚠` line plus the existing "unusable" line, exit 1.
- **A missing registry inside a group-writable `~/.vibe`** is still usable (no file, so no grant). The first `allow` there creates it. This matches the link registry and is documented, not refused.
- **Bash 3.2.** No `${var,,}`, `local -n`, `mapfile` or `alias`. Arithmetic comparisons only, never `wc -l` output.

## Acceptance criteria

The tests use a temp HOME. Ownership is faked with a `stat` PATH shim that answers only `%u` and passes everything else through, as checks_49 does. The decision is observed through `codex_allowed`/`_codex_opted_in`, called the way checks_17 calls them. Mode-200 cases are skipped when running as root.

- **AC1.** A foreign-owned codex-allow file is refused: `vibe codex list` prints `(none)`, `codex_allowed` returns false for a listed project, and stderr has the exact `foreign_owner` line.
- **AC2.** Each of these is refused the same way with its exact new line: a mode-200 file (`unreadable`), a 775 `~/.vibe` (`dir_writable`), and a 1,001-line file (counted with and without a trailing newline). Positive control: a 1,000-line file is accepted.
- **AC3.** `vibe codex allow` refuses (exit 1, file byte-identical) a foreign owner, a 775 `~/.vibe` with an existing file, and a 1,001-line file. It still repairs a 644 file to 600. `vibe codex deny` refuses the same three, and still refuses a 644 file as today. `codex_allow_remove` called directly refuses them too, and returns 0 on a missing file.
- **AC4.** `vibe codex allow` under `umask 002` with no `~/.vibe` creates the directory without group write. A following `vibe codex list` shows the project.
- **AC5.** The three existing codex messages and every link-registry message match literal strings copied into the test from the current source.
- **AC6.** checks_17, checks_48, checks_49 and checks_56 pass unchanged.
- **AC7.** `vibe` defines `_vibe_consent_registry_check()` exactly once. The bodies of `codex_registry_usable` and `_link_registry_usable` (from `name() {` to the next line that is exactly `}`) both call it, and neither contains `stat` or `id -u`.
- **AC8.** `python3 code-check.py` exits 0, `python3 smoke-test.py < /dev/null` exits 0, and the CHANGELOG has an entry. Tests go in `smoke/checks_65_codex_allow_hardening.py`, registered in `runner.main()`. The TODO item is closed in the pass commit.

## Out of scope

- What `codex-allow` grants.
- The `.vibe-allow-codex` marker.
- The link registry's behaviour.
- Firewall, hooks and settings.

## Model plan

- Planner and Evaluator: Opus 5.5.
- Spec Critic: sonnet.
- Generator: sonnet, ceiling opus.
- Tester: sonnet.
- Fable rung: not pre-authorised.
- `/code-review high` before commit.

## Rev 2.1 — critic minor notes (binding)
- The wrappers re-read the mode with `_link_mode` for their `(mode NNN)` text (allowed: `_link_mode` is not `stat` in the wrapper body). AC5 asserts the `mode NNN` text.
- AC7's `stat` check uses a word boundary (`\bstat\b`) on non-comment lines.
- checks_17 pins `deny` on a symlinked registry; the 644 `deny` refusal is pinned by AC3 here.

## Rev 3 addendum (cycle 2): `/code-review high` findings (2026-10-31)

- **AC9: allow never reports a grant that reads will refuse.** If `~/.vibe` already exists and group or others can write to it, `codex_allow_record` refuses before writing, even when the registry is missing. It prints the `dir_writable` line and exits 1. The `chmod go-w` repair still applies only to a `~/.vibe` that this call created.
- **AC10: only regular files.** The shared helper gains reason `not_regular`, checked right after `missing`, for anything that is not a regular file (directory, FIFO, socket, device). Both wrappers refuse it:
  - codex prints `  ⚠ ${f} is not a regular file — ignored, so no project counts as allowed; remove it and re-run 'vibe codex allow'.`;
  - link prints `  ⚠ ~/.vibe/link-projects is not a regular file — ignored (fail closed); remove it and re-run 'vibe link allow'.`
  
  The cap loop never runs on a non-regular file, so a directory can't crash a read and a FIFO can't hang one.
- **AC11: fail closed on unknown codes.**
  - In both wrappers, only `missing` and `ok` return 0. Any other code, including an empty one, prints `  ⚠ <file> could not be checked — ignored (fail closed).` and returns 1.
  - Each wrapper captures the reason with `reason=$(…) || true`, so a bare call can never abort under `set -e` before its ⚠ prints.
- **AC12: mode in the codex dir message.** The codex `dir_writable` line becomes `  ⚠ $(dirname "$f") is writable by group or others (mode <mode or unknown>) — ignored, so no project counts as allowed; run 'chmod go-w $(dirname "$f")' on the Mac.`
- **AC13: comments match behaviour.** The headers of `codex_registry_usable`, `codex_allow_remove` and `_link_registry_usable` describe what each now does. Each comment sits directly above its own function.
- **Not adopted:**
  - The single-pass awk rewrite. The cost is one bounded read per launch, and an awk rewrite of the grant check is a larger change than this task.
  - The shared message table. Two short case tables with pinned literals are easier to audit than an indirection layer.
- Tests for AC9–AC12. AC9 is tested with an existing 775 `~/.vibe` and no file; AC10 with a directory, a FIFO (opened non-blocking by the test only) and a socket where possible; AC11 with an injected unknown code via a shim of the helper's output, or directly by calling the wrapper's case through a test seam the Generator adds as an environment-free function `_vibe_consent_reason_message <registry> <code>`.
