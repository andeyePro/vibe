# task_049 — Generator report, cycle 1

`vibe --agent codex`: a Codex-led container launch behind the liveness gate.
Branch `astra`, no commit, no push, no branch switch.

## Commands run

```
python3 .vs/cycle-1/scratch-tests/scratch_task049.py   # 71/71 ok (TDD driver, red first)
python3 code-check.py                                  # ✓ shellcheck clean across 23 files
python3 smoke-test.py < /dev/null                      # ✓ smoke tests passed (foreground, full run)
bash -n vibe                                           # syntax gate after every launcher edit
git diff > .vs/cycle-1/diff.patch
```

`code-check.py` picks `devcontainer/codex-entry.sh` up automatically (its
`--json` `files_checked` list now names it), so the new script is shellcheck-gated
from this commit on.

## Files changed

| File | What |
|---|---|
| `vibe` | `--help` header line for `--agent`; `AGENT_ARG` + `--agent` case in `parse_vibe_args`; new `_agent_resolve` above the `VIBE_SOURCE_ONLY` guard; `LEAD_AGENT` resolution + the AC2 refusal before the image build; the `agent   :` header line; `launch_codex`; `launch_codex_plain`; the codex dispatch before `launch_claude_supervised` |
| `devcontainer/codex-entry.sh` | **new** — root-owned Codex-led entry point (installed as `/usr/local/bin/codex-entry`) |
| `devcontainer/codex-guard-liveness.sh` | check (a) ownership list gains `$bin/codex-entry` (so `--bin` relocates it too) |
| `devcontainer/Dockerfile` | `COPY --chown=root:root codex-entry.sh /usr/local/bin/codex-entry` next to the task_046/048 lines; `/usr/local/bin/codex-entry` added to the `chmod +x` list |
| `devcontainer/install-claude-extras.sh` | `ensure_project_gitignore`'s managed block gains `.vibe/agent` |
| `.gitignore` | `.vibe/agent`, with the same security rationale as `.vibe/domains` |
| `README.md` | `vibe --agent <claude|codex>` in the Usage flag list; new `#### Codex-led sessions (vibe --agent codex)` subsection |
| `MANUAL-TESTS.md` | Test 55 gains the six-step Codex-led launch block plus the negative case; Pass line extended |
| `docs/codex-integration-plan.md` | §3 item 7 marked delivered-pending-live-trial with the real file list; §4 says the live trial is still Martin's |
| `TODO.md` | phase 1b entry: item 7 shipped, live trial named as Martin's |
| `smoke/checks_18_codex_runtime.py` | the one permitted `smoke/` edit: `_codex_liveness_fixture` copies `codex-entry` (AC4 names this explicitly) |

New untracked files: `devcontainer/codex-entry.sh` (shipped) and
`.vs/cycle-1/scratch-tests/scratch_task049.py` + `.vs/cycle-1/generator-report.md`
+ `.vs/cycle-1/diff.patch` (harness artefacts; `.vs/cycle-*/` is gitignored, so
the scratch checks do not appear in `diff.patch`).

`devcontainer.json` untouched, as AC6 requires. `guard-bash.sh`, `guard-fs.sh`,
`init-firewall.sh`, `settings.local.json` and the sudoers block are untouched.
`codex` was never run with a prompt.

## Per-AC coverage

### AC1 — parsing

- `_agent_resolve <flag> <workspace>` lives above the `VIBE_SOURCE_ONLY` guard,
  in its own section after the profile helpers. Precedence flag > `.vibe/agent`
  > `VIBE_AGENT` > `claude`.
- The file rung implements the rule verbatim: `[ ! -L "$ws/.vibe/agent" ]`,
  `[ ! -L "$ws/.vibe" ]`, not a regular file, not a git work tree,
  `ls-files --error-unmatch ':(icase).vibe/agent'` succeeding (tracked),
  `ls-files -o` empty (not positively untracked), and a first non-blank
  non-comment line that is not exactly `claude`/`codex` — each prints exactly
  ONE `⚠ .vibe/agent ignored: <reason>` line on stderr and falls through.
  An absent file is silent. `-e || -L` is the presence test so a dangling
  symlink is reported rather than skipped.
- Out of caution the flag and env rungs also refuse a non-`claude`/`codex`
  value with one `⚠ --agent ignored:` / `⚠ VIBE_AGENT ignored:` line and fall
  through; the spec only pins the file rung's warnings, and neither of these
  fires in any of the specified matrix cases.
- `parse_vibe_args` initialises `AGENT_ARG=""` and validates `--agent` itself
  (mirroring `--model`/`--profile`), so `vibe --agent bogus` and bare
  `vibe --agent` print `--agent needs 'claude' or 'codex', got: '…'` and exit 1
  before workspace resolution, preflight or any Docker/devcontainer call.
  Verified against the REAL launcher with a `devcontainer` PATH stub: exit 1,
  stub log file never created.
- `.vibe/agent` added to both the managed block in `ensure_project_gitignore`
  and the repo `.gitignore`. The managed block already carries a blanket
  `.vibe/`; the explicit entry is there because untrackedness is a security
  property for this file, and the added comment says so.
- `vibe --help` shows the `--agent <claude|codex>` line (checked by running it).

### AC2 — gate

`LEAD_AGENT="$(_agent_resolve "$AGENT_ARG" "$WORKSPACE")"` resolves immediately
after profile resolution and before the `# ── Build the image` section. When it
is `codex` and `_codex_desired_source "$WORKSPACE"` is empty the launcher prints
the AC2 message verbatim on stderr and exits 1. Proved end-to-end against the
real launcher (fixture `HOME`, `~/.vibe/skipped` to bypass GitHub setup, stub
`docker`/`devcontainer`/`gh`, `VIBE_CODEX_PATH=off`): exit 1, exact message, no
`devcontainer` invocation, no `docker build`.

### AC3 — launch

- `launch_claude` is byte-for-byte unchanged — asserted in the scratch checks by
  extracting the function body from the working tree and from `git show HEAD:vibe`
  and comparing them.
- `launch_codex` is its sibling: same `exec devcontainer exec --workspace-folder
  … --override-config … /bin/bash --noprofile --norc` shape, command string
  `exec env SHELL=/bin/bash LC_ALL=C.UTF-8 LANG=C.UTF-8
  CODEX_HOME=/home/node/.codex /usr/local/bin/codex-entry`. No model, approval
  or sandbox flag; it takes no arguments at all.
- `launch_codex_plain` prints the pre-launch line
  `  codex-led session: auto-resume and the stall watchdog are Claude-only; run
  codex-supervisor inside the session for unattended work`, then
  `launch_codex <&9 &`, `wait "$codex_pid"`, `CLAUDE_EXIT="$rc"`,
  `restore_terminal || true`. No heartbeat seed, no marker refresh, no
  `vibe_stall_watchdog` (asserted). FD 9 is reused for the same non-TTY-stdin
  reason documented in `launch_claude_supervised`.
- Dispatch: an `if [ "$LEAD_AGENT" = "codex" ]` block immediately before the
  `launch_claude_supervised …` call runs `launch_codex_plain` and exits with
  `CLAUDE_EXIT`, so the Claude-only auto-resume loop below is never entered and
  the EXIT traps still fire. `pkill -TERM -x claude` left exactly as it was; no
  `codex` sibling added.

### AC4 — entry script

`devcontainer/codex-entry.sh`: `#!/bin/bash`, `set -euo pipefail`,
`export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/share/npm-global/bin`,
`unset BASH_ENV ENV`. Flags `--root` (default `/etc/codex`), `--bin` (default
`/usr/local/bin`), `--login-dir` (default `/home/node/.codex`), `--codex`, then
`--`; `-h/--help` prints usage and exits 0; a missing flag value or an unknown
argument exits 1.

(a) Refuses with exit 1 and one `codex-led session refused: …` line when
`<root>/requirements.toml` is missing, when `<login-dir>` is not a directory, or
when `<bin>/codex-guard-liveness --root <root> --bin <bin> [--codex <path>]`
exits non-zero — the gate's own stdout/stderr are passed through unredirected
first, then `codex-led session refused: the guard chain did not prove itself`.
(There is also a refusal when the gate binary itself is missing or not
executable, which is the same fail-closed direction.)
(b) On success prints `codex-led session: guard chain proven, starting codex`
and `exec`s `codex` (resolved through the fixed PATH, or the `--codex` path)
with only the arguments after `--`, cwd unchanged.
(c) The file contains no `dangerously` and no ` -c ` anywhere, including
comments — asserted in the scratch checks, which is why the header comment
describes the launcher's bash invocation in prose rather than quoting it. The
login dir is only ever `-d`-tested.

Offline proof with a temp `--root` (real `requirements.toml` content), a temp
`--bin` holding a stub `codex-guard-liveness` (exit 0, or exit 1 printing
`LIVENESS FAILED: fixture`) and an argv-recording stub `codex`, and a present or
absent `--login-dir`: all four paths behave as specified and the stub `codex` is
never executed on any refusal.

Installation: `COPY --chown=root:root codex-entry.sh /usr/local/bin/codex-entry`
sits with the task_046/048 COPY lines, and `/usr/local/bin/codex-entry` is in the
same `chmod +x` list. `codex-guard-liveness` check (a) now calls
`check_owned "$bin/codex-entry"`, so `--bin` relocates it for tests, and
`smoke/checks_18_codex_runtime.py`'s `_codex_liveness_fixture` copies
`codex-entry` into the fixture bin dir (the one permitted `smoke/` edit) — every
existing liveness test stays green.

### AC5 — header

Inside the existing `if [ -n "$_codex_banner" ]` block, directly under the
`codex   : /home/node/.codex (rw, …)` line:
`[ "$LEAD_AGENT" != "codex" ] || echo "     agent   : codex (policy: /etc/codex,
gate: codex-guard-liveness)"`. Nothing new is printed for a Claude launch.

Two deliberate shape choices, both load-bearing: `[ … ] || echo` rather than
`if/fi` keeps it a single statement (so `set -e` cannot trip on the false
branch) **and** keeps `checks_17_delegation.py`'s source-adjacency walk intact —
that check counts any line starting with `fi` to find the end of the
`_codex_banner` block, so a nested `fi` between the header line and the
`_codex_dir_mode_warning` call would have broken it. The explanatory comment
therefore sits above the `if`, not between the two echoes, so
`_codex_dir_mode_warning` stays within the 5-line window the same check
enforces. Both invariants are asserted in the scratch checks.

### AC6 — docs

- README: `vibe --agent <claude|codex>` in the Usage flag list, and a new
  `#### Codex-led sessions (vibe --agent codex)` subsection covering how to
  launch (flag, `.vibe/agent`, `VIBE_AGENT`, and the precedence), the three
  prerequisites (`~/.codex` on the Mac, the untracked marker, the
  `vibe codex allow` registry line), what is enforced (`codex-entry` runs
  `codex-guard-liveness` and refuses on any failure; no launcher-side model,
  approval or sandbox flag), that Claude Code remains the default and the
  recommended lead, and that auto-resume and the stall watchdog are Claude-only
  for now with `codex-supervisor` as the unattended path.
- `MANUAL-TESTS.md` Test 55 gains a six-step Codex-led block (launch + header
  line; the `guard chain proven` line; approval `never`; the denied
  `/home/node/.codex/config.toml` write; `git status` allowed and
  `git push --force` denied; exit and relaunch plainly to confirm Claude
  returns) plus the negative step (`--agent codex` without the registry line
  refused before Docker, checked with `docker ps -a`), and the Pass line is
  extended to cover them.
- `docs/codex-integration-plan.md` §3 item 7 is marked
  **DELIVERED, pending live trial (task_049)** with the actual file list and an
  explicit note that `devcontainer.json` was NOT changed; §4 now says item 7's
  live trial is still Martin's.
- `TODO.md`'s phase 1b entry names item 7 as shipped with the live trial as
  Martin's (run Test 55's Codex-led block on real Docker and report).

### AC7 — tests

Not written here (Tester's, by assignment). The Generator's scratch driver at
`.vs/cycle-1/scratch-tests/scratch_task049.py` covers the same ground offline —
the `_agent_resolve` matrix, the parser error path against the real launcher
with a `devcontainer` stub, the AC2 refusal end-to-end, the launcher source
shape (including the `launch_claude` byte-identity check and the checks_17
adjacency invariants), and the entry script's four paths — and is not part of
the shipped suite.

### AC8 — gates

`python3 code-check.py` → `✓ shellcheck clean across 23 files`.
`python3 smoke-test.py < /dev/null` → `✓ smoke tests passed` (full run,
foreground, including the updated checks_18 liveness fixture).

## Not done / notes for the Evaluator

- The Tester still owns AC7's shipped checks. Per the spec's test-location rule
  they go in `smoke/checks_17_delegation.py` (925 lines today, so there is room)
  or a new `smoke/checks_21_codex_agent.py`.
- A live `--agent codex` launch has never been run: nothing in this change (or
  in the suite) starts a real Codex session. That is Test 55's Codex-led block
  and it is Martin's, as the plan and TODO now say.
- `CLAUDE.md`'s convention is that anything needing Martin's hands belongs in
  `/brain2/andeye/vibe-fromClaude.md`. The live-trial item is recorded in
  `TODO.md` and the plan as the spec asks; adding the fromClaude line is outside
  the Generator's brief and is left for the chair.
- `--continue`, `--resume`, `--model` and `--fable` are still accepted alongside
  `--agent codex` and are simply ignored by the Codex path (they only shape
  `CLAUDE_RESUME_ARGS`/`CLAUDE_MODEL_ARGS`). The spec does not ask for a
  refusal; a future task could warn.
