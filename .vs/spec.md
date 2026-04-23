# spec — task_005: OSC 52 clipboard bridge (`vibe-copy` + `/copy`)

**Revised after cycle-1 Spec Critic (iteration 2).**

## Task summary

Add an inside-container OSC 52 clipboard bridge so exact-byte copy of Claude-produced content reaches the Mac clipboard without the terminal-selection padding mangling that affects rendered-code-block mouse-copy. Two surfaces: (a) a shell helper `vibe-copy` installed on `$PATH` inside the container — reads stdin or a file path, emits a well-formed OSC 52 escape sequence to the controlling terminal, and also writes a bind-mounted scratch file so users on OSC-52-less terminals (Apple Terminal.app) retain a path; (b) a `/copy` slash command synced into `~/.claude/commands/copy.md` that instructs Claude to identify the most recent fenced code block in its prior turn, write the block's raw bytes to a temp file, and invoke `vibe-copy` on it.

**Design decisions fixed here (previously open questions in TODO.md):**

1. **How does `/copy` identify "the last code block"?** The most recent fenced code block in Claude's immediately-prior assistant turn. `/copy <hint>` disambiguates when the prior turn contains several blocks; Claude selects the one whose language tag or first-line content best matches the hint. If no prior assistant turn exists, OR the prior turn contains no fenced code block, `/copy` refuses with a one-line message and stops.
2. **Payload size thresholds.** **8192 bytes** warn threshold (stderr note; still emits and writes scratch), **1048576 bytes (1 MiB)** hard refuse (stderr error; does NOT emit OSC 52 but STILL writes scratch).
3. **Test strategy for OSC 52.** `vibe-copy` respects `VIBE_COPY_TTY` (redirects escape sequence) and `VIBE_COPY_SCRATCH_DIR` (redirects scratch dir) env vars — set both for tests. `install-claude-extras.sh` gains an analogous `VIBE_EXTRAS_SRC_ROOT` env override so the extras-sync test can stage fixtures without hardcoded paths.

**Installation mechanism.** `vibe-copy.sh` ships via Dockerfile `COPY` + `chmod +x` (the same image-bake pattern as `guard-bash.sh`, `init-firewall.sh`, `setup-ssh.sh` at `devcontainer/Dockerfile:113-130`). This requires an image rebuild on landing, which the existing marker-based auto-rebuild triggers on `devcontainer/` changes — no user action required. The `/copy` slash command markdown ships through the existing `install-claude-extras.sh` sync path (like `/vs`, `/diet`, `/feast`).

**Note on "extras-sync-only" framing.** The Planner's original pointer to "ship via the extras-sync path like /diet and /vs" is inaccurate for shell binaries: extras-sync operates on `.md` files under `/usr/local/share/vibe/{agents,commands}/`, not on `$PATH` executables. Binaries must be image-baked. The rebuild cost is one-time on landing, same as when /diet and /vs were introduced.

## Exit-code and stderr-message table (normative)

This table is the authoritative reference; individual ACs cross-reference it.

| Exit | Condition | stderr message template |
|---|---|---|
| 0 | Input ≤ 1 MiB; scratch file written; sequence emitted (or skipped because TTY absent) | (none normally) |
| 0 | Input > 8192 bytes and ≤ 1 MiB; warn issued; sequence emitted; scratch written | `vibe-copy: warning: input is <N> bytes; some terminals truncate OSC 52 payloads larger than 8192 bytes` |
| 0 | `VIBE_COPY_TTY` unset/empty AND `/dev/tty` not writable; scratch written; no sequence emitted | `vibe-copy: note: no terminal available for OSC 52 write; scratch file written to <path>` |
| 1 | Input > 1 MiB; scratch file written; no OSC 52 emit | `vibe-copy: error: input is <N> bytes; refusing to emit OSC 52 for payloads larger than 1048576 bytes (1 MiB); scratch file written to <path>` |
| 1 | Scratch directory creation failed OR scratch file write failed | `vibe-copy: error: cannot write scratch file at <path>: <reason>` |
| 2 | Argument validation: more than one positional argument | `vibe-copy: usage: vibe-copy [FILE]; accepts stdin or a single file path` |
| 2 | Argument validation: positional argument is a path that does not exist or is not readable | `vibe-copy: error: cannot read file: <path>` |

`<N>` is the literal byte count as a decimal integer. `<path>` is the fully-resolved absolute path actually used at runtime. `<reason>` is a short human-readable cause (e.g. "permission denied"); tests only assert it is non-empty and the line starts with the fixed prefix.

## Acceptance criteria

1. **AC1 — vibe-copy.sh tracked in repo.** A shell helper exists at `devcontainer/vibe-copy.sh` with `#!/usr/bin/env bash` shebang and `set -euo pipefail`.

2. **AC2 — argument validation.** `vibe-copy` reads from stdin when no positional argument is supplied and from the file path given as `$1` when one positional argument is supplied. More than one positional argument, or a non-existent / unreadable file path, exits 2 with the exact stderr prefix given in the exit-code table. Long options (`--help`, `--version`, etc.) are not supported in v1.

3. **AC3 — OSC 52 sequence format.** For non-empty input ≤ 1 MiB, `vibe-copy` emits exactly the byte sequence `ESC ] 5 2 ; c ; <BASE64> BEL` (hex: `1b 5d 35 32 3b 63 3b <b64-bytes> 07`) to its target stream. No preceding or trailing bytes on that stream, no newline, no whitespace. The target stream is:
   - `$VIBE_COPY_TTY` if set and non-empty (treated as a filesystem path);
   - else `/dev/tty` if writable;
   - else no emission (see AC16).
   Implementation MUST use `printf '\033]52;c;%s\007' "$b64"` (or an equivalent that appends no trailing newline — `echo -e` is forbidden because it trails a newline by default). The BASE64 value MUST use standard RFC 4648 encoding (`+/=` alphabet) with all linefeeds stripped (portable: `base64 | tr -d '\n'`; or `openssl base64 -A`). URL-safe base64 is forbidden.

4. **AC4 — base64 round-trip.** The base64 portion of the emitted sequence, when decoded with standard RFC 4648, yields exactly the input bytes — same length, same byte values, including any trailing newlines in the input. Tests capture the full byte stream written to `$VIBE_COPY_TTY` and assert `captured == b'\x1b]52;c;' + b64payload + b'\x07'` byte-for-byte.

5. **AC5 — scratch file write.** On every invocation that passes argument validation (AC2) and reaches the size-gate logic, `vibe-copy` writes the raw input bytes verbatim to `<SCRATCH_DIR>/copy-latest.txt`, where `<SCRATCH_DIR>` is `$VIBE_COPY_SCRATCH_DIR` if set and non-empty, else `/workspace/.vibe`. The directory is created via `mkdir -p` if absent. Scratch write occurs even on the 1-MiB-refuse path (AC7) and the TTY-absent path (AC16); the only exit paths that do NOT write scratch are the exit-2 argument-validation failures (AC2). If `mkdir -p` fails OR the file write fails, `vibe-copy` exits 1 with the stderr message from the exit-code table. Atomicity is not required (non-atomic truncating overwrite is acceptable; no `mktemp+mv` pattern).

6. **AC6 — 8 KiB warn.** For input strictly greater than 8192 bytes and ≤ 1048576 bytes, `vibe-copy` writes the exact `vibe-copy: warning:` line from the exit-code table to stderr (substituting the real byte count). The OSC 52 sequence is still emitted (per AC3); the scratch file is still written (per AC5); exit code is 0.

7. **AC7 — 1 MiB refuse.** For input strictly greater than 1048576 bytes, `vibe-copy` writes the exact `vibe-copy: error: input is <N> bytes; refusing...` line from the exit-code table to stderr, does NOT emit the OSC 52 sequence to any stream, DOES write the scratch file (AC5), and exits 1.

8. **AC8 — exit code 0 happy path.** For input ≤ 1 MiB with no I/O errors, `vibe-copy` exits 0. The scratch-write and sequence-emit are obligations under AC3/AC5 and are enforced by their own tests; AC8 is purely the exit-code contract for the happy path.

9. **AC9 — empty input.** For zero-byte input (immediate stdin EOF, or a zero-byte file), `vibe-copy` emits the exact bytes `1b 5d 35 32 3b 63 3b 07` (the valid "clear clipboard" OSC 52 form with empty base64 payload) to the target stream, writes a zero-byte scratch file to `<SCRATCH_DIR>/copy-latest.txt`, issues no warning, and exits 0.

10. **AC10 — /copy slash command file.** `devcontainer/commands/copy.md` exists with YAML frontmatter (at minimum `description:` field) and a body that instructs the executing Claude to:
    - (a) Identify the target code block: the most recent fenced code block in Claude's immediately-prior assistant turn, OR — if `$ARGUMENTS` is non-empty — the one whose language tag or first non-blank line best matches the `$ARGUMENTS` hint.
    - (b) Refuse cleanly in BOTH these cases: no prior assistant turn exists, OR the prior assistant turn contains no fenced code block. Refusal message: `no prior code block to copy`.
    - (c) Write the block's raw bytes (between the fences, excluding both fence lines and the language tag line) to a temp file at `/tmp/copy-<ISO8601>.txt` using the Write tool.
    - (d) Invoke `vibe-copy /tmp/copy-<ISO8601>.txt` via the Bash tool.
    - (e) Report success to the user with the byte count and the actual scratch file path (`/workspace/.vibe/copy-latest.txt` when `VIBE_COPY_SCRATCH_DIR` is unset; otherwise `<$VIBE_COPY_SCRATCH_DIR>/copy-latest.txt`).
    - (f) Note that `/copy` targets UTF-8 text code blocks; the Write tool round-trips UTF-8, so non-UTF-8 byte sequences in code blocks are NOT supported via `/copy`. Binary-safe copy is via `vibe-copy <file>` directly.

11. **AC11 — Dockerfile COPY + chmod.** `devcontainer/Dockerfile` has a new `COPY vibe-copy.sh /usr/local/bin/` line inserted into the helper-COPY block between lines 113 and 119 (the block preceding the agents/ and commands/ COPYs). The existing `RUN chmod +x ...` command includes `/usr/local/bin/vibe-copy` in its argument list. The insertion is placed BEFORE any `USER root` directive that precedes the chmod (same position as `guard-bash.sh` etc.) so ownership matches the existing helper set. No other Dockerfile changes.

12. **AC12 — install-claude-extras.sh env override + /copy sync.** `install-claude-extras.sh` is updated so `SRC_ROOT` accepts an env override: `SRC_ROOT="${VIBE_EXTRAS_SRC_ROOT:-/usr/local/share/vibe}"` (single-line change). `DEST_ROOT` continues to use the existing `CLAUDE_CONFIG_DIR` override. The markdown sync loop is unchanged; `copy.md` is picked up automatically by the existing `*.md` glob. The script remains shellcheck-clean (AC13).

13. **AC13 — shellcheck clean.** `python3 code-check.py` exits 0 after the changes. `devcontainer/vibe-copy.sh` is included automatically via the existing `devcontainer/*.sh` glob in `code-check.py`. The `install-claude-extras.sh` env-override edit is also shellcheck-clean.

14. **AC14 — smoke test coverage.** `python3 smoke-test.py` passes all pre-existing checks (no regressions) and adds the following new test functions. Every test uses `VIBE_COPY = REPO / "devcontainer" / "vibe-copy.sh"` and invokes via `["bash", str(VIBE_COPY), ...]` with `VIBE_COPY_TTY` and `VIBE_COPY_SCRATCH_DIR` set to paths inside a `tempfile.TemporaryDirectory()`. Each test resets state and sets env vars explicitly (no reliance on inherited state).
    - `test_vibe_copy_stdin_roundtrip` — pipe `b"hello world\n"` to vibe-copy; read captured TTY bytes; assert exactly `b"\x1b]52;c;" + b64(b"hello world\n") + b"\x07"`; decode payload; assert equal to input.
    - `test_vibe_copy_file_arg_roundtrip` — write `b"hello world\n"` to a temp file; call `vibe-copy <file>`; assert the same byte-for-byte equality.
    - `test_vibe_copy_scratch_file_written` — assert `<SCRATCH_DIR>/copy-latest.txt` contains exact input bytes after a successful invocation.
    - `test_vibe_copy_empty_input_stdin` — pipe nothing; assert captured TTY bytes are exactly `b"\x1b]52;c;\x07"`; assert `copy-latest.txt` exists and is zero bytes; assert exit 0; assert stderr is empty.
    - `test_vibe_copy_warn_at_8kib_plus_one` — 8193-byte input; assert stderr contains the literal substring `vibe-copy: warning: input is 8193 bytes` AND the literal substring `8192 bytes`; assert TTY bytes contain a valid OSC 52 sequence whose decoded base64 equals input; assert scratch contains input; assert exit 0.
    - `test_vibe_copy_refuse_at_1mib_plus_one` — 1048577-byte input; assert stderr contains the literal substrings `vibe-copy: error: input is 1048577 bytes` AND `1048576`; assert the captured TTY output contains NO `\x1b]52;c;` sequence anywhere; assert scratch file contains input (all 1048577 bytes); assert exit 1.
    - `test_vibe_copy_refuses_two_args` — invoke `vibe-copy a b`; assert exit 2; assert stderr starts with `vibe-copy: usage:`.
    - `test_vibe_copy_refuses_missing_file` — invoke `vibe-copy /nonexistent-<uuid>`; assert exit 2; assert stderr starts with `vibe-copy: error: cannot read file:`.
    - `test_vibe_copy_tty_absent_note` — `VIBE_COPY_TTY=/does/not/exist/<uuid>`; pipe `b"text\n"`; assert exit 0; assert stderr contains the literal prefix `vibe-copy: note: no terminal available`; assert scratch file written with exact bytes; assert NO OSC 52 sequence was written to `/dev/tty` or anywhere else reachable by the test.
    - `test_vibe_copy_scratch_failure_exits_1` — set `VIBE_COPY_SCRATCH_DIR` to a path inside a read-only directory created in the test fixture; pipe `b"text\n"`; assert exit 1; assert stderr starts with `vibe-copy: error: cannot write scratch file`.
    - `test_copy_slash_command_synced` — stage a fixture dir with `commands/copy.md` (containing a sentinel string like `SENTINEL_COPY_FIXTURE`); set `VIBE_EXTRAS_SRC_ROOT=<fixture>` and `CLAUDE_CONFIG_DIR=<tmp-dest>`; run `install-claude-extras.sh`; assert `<tmp-dest>/commands/copy.md` exists and contains the sentinel. Then re-run the script (idempotency check) and assert destination still matches source byte-for-byte.
    - `test_copy_slash_command_body_matches_spec` — open `devcontainer/commands/copy.md`; assert the body contains all of: `vibe-copy`, `/workspace/.vibe/copy-latest.txt`, `no prior code block to copy`, and `UTF-8` (or `UTF8`) — proves AC10(a–f) are actually described.

15. **AC15 — Dockerfile assertion test.** `smoke-test.py` gains `test_dockerfile_installs_vibe_copy` which reads `devcontainer/Dockerfile` and asserts: (a) it contains exactly one line matching the regex `^COPY vibe-copy\.sh /usr/local/bin/vibe-copy$` (the canonical form — NOT a trailing-slash form, which would install the binary at `/usr/local/bin/vibe-copy.sh` and leave `vibe-copy` not-on-$PATH as a bare command); (b) the chmod RUN command includes the literal substring `/usr/local/bin/vibe-copy`. This is a static assertion — does not require building the image. Path reachability inside a built image is out of scope for smoke tests (validated by the existing MANUAL-TESTS.md container-lifecycle checklist).

16. **AC16 — /dev/tty absent fallback.** When `VIBE_COPY_TTY` is unset or empty AND `/dev/tty` cannot be opened for writing (non-interactive subprocess, CI, piped execution), `vibe-copy` writes the exact `vibe-copy: note: no terminal available` line from the exit-code table to stderr, does NOT emit any OSC 52 sequence, DOES write the scratch file (AC5), and exits 0. Rationale: the scratch file is the designed fallback for non-OSC-52-capable environments; failing the invocation would make CI pipelines and piped usage unusable.

## Out of scope

- OSC 52 *read* (pasting the Mac clipboard into the container). Security-sensitive; most terminals gate read off by default; not needed for the stated pain point.
- Detecting whether the outer terminal supports OSC 52. There is no reliable universal probe. `vibe-copy` always emits the sequence (when it has a TTY) AND always writes the scratch file.
- Chunking oversize payloads across multiple OSC 52 sequences. 1 MiB refuse is simpler and covers realistic code-block sizes.
- Auto-mirroring to host `pbcopy` / `xclip`. Out of scope — host-side clipboard is the user's shell.
- Atomic scratch writes (`mktemp+mv`). Non-atomic truncating overwrite is acceptable; concurrent `vibe-copy` invocations may race on `copy-latest.txt` — the "latest-wins" semantics of a scratch file tolerate this.
- SIGPIPE handling on stdin. If upstream closes prematurely, the default bash behaviour (fail) is acceptable; no custom trap required.
- Binary-safe `/copy` (non-UTF-8 byte sequences in code blocks). Users with binary payloads use `vibe-copy <file>` directly. The shell helper is byte-safe; only the Write-tool hop inside `/copy` is UTF-8-only.
- URL-safe base64 variant. Standard RFC 4648 only.
- Any changes to `vibe` (the host launcher). The Terminal.app advisory comment at `vibe:1083` already references OSC 52 / `vibe-copy`; no further launcher edits.
- Any changes to README.md. If the feature lands and is worth surfacing, that's a follow-up doc PR.
- Any tests that require building the Docker image. Smoke tests remain host-only, no-docker, no-network.

## Test location

`smoke-test.py` (existing host-side test file). All new tests are added there as top-level `test_*` functions and invoked from `main()`. `devcontainer/vibe-copy.sh` must be directly invokable by `bash` on the host (macOS or Linux) — no container dependencies beyond the `VIBE_COPY_TTY` / `VIBE_COPY_SCRATCH_DIR` env escape hatches. `install-claude-extras.sh` becomes similarly host-testable via `VIBE_EXTRAS_SRC_ROOT` + `CLAUDE_CONFIG_DIR`.

**Immutability rule:** once Tester writes these tests in cycle 1, they are frozen. Generator may not edit them on subsequent cycles; revisions require a fresh spec and a restart at cycle 1.

## Proposed budget

**2 cycles.** Rationale: moderately scoped — one new shell helper (~60 lines after the exit-code/stderr discipline), one new markdown slash-command file (~30 lines), one env-override single-line edit to `install-claude-extras.sh`, two small edits to `devcontainer/Dockerfile`, and ~12 new test functions. Main risks are OSC 52 byte-sequence quoting (caught by AC4's byte-for-byte round-trip) and the exit-code discipline (every exit path has a test). If anything slips through cycle 1, one fix-up cycle should finish it.
