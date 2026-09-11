# task_046 — Generator report (cycle 1)

Branch `astra`, no commits, no branch switches. AC9 (the smoke tests) is the
Tester's and was deliberately left unwritten; everything else is implemented.

## Files

### New (untracked — `git diff` does NOT contain these; read them directly)

- `devcontainer/codex/requirements.toml`
- `devcontainer/codex/config.toml`
- `devcontainer/codex/hooks/hooks.json`
- `devcontainer/codex-guard-adapter.sh` (mode 0755)
- `devcontainer/codex-guard-liveness.sh` (mode 0755)
- `docs/codex-tool-inventory.md`
- `.vs/cycle-1/scratch-tests/check_codex_runtime.py` (gitignored scratch, 64 checks)

### Changed (in `.vs/cycle-1/diff.patch`)

- `devcontainer/Dockerfile` — three `COPY --chown=root:root` lines immediately
  after `COPY vibe-delegate.mjs …`, plus the two new scripts appended to the
  existing `chmod +x` list and two explicit `chmod` calls fixing `/etc/codex`
  to dirs 0755 / files 0644. The sudoers block is byte-for-byte unchanged
  (still exactly three `node ALL=(root) NOPASSWD:` rules).
- `README.md` — new "**Codex-led sessions: how the backstops hold.**"
  paragraph in the Codex section, and the trailing pointer now names Test 55.
- `MANUAL-TESTS.md` — new Test 55 with the required step 0.
- `.vs/tasks.json` — task_046 `implementation_status: complete`.

`docs/codex-integration-plan.md` was left alone: F11 is already present at
§ 1 (lines 127-146), as the brief said it would be.

## Per-AC coverage

**AC1 — `devcontainer/codex/requirements.toml`.** Parses as TOML
(`tomllib`). Exactly the constrained set and nothing outside
`ConfigRequirementsToml`: `allowed_approval_policies = ["never"]`;
`allowed_sandbox_modes = ["read-only", "danger-full-access"]`;
`allowed_web_search_modes = ["disabled"]`; `allow_managed_hooks_only = true`;
`[features]` with the five pins; present-and-empty `[mcp_servers]`;
`[hooks]` with `managed_dir = "/etc/codex/hooks"`; `[rules]` with two
`prefix_rules`, both `decision = "forbidden"`, patterns
`["git","push","--force"]` and `["git","push","-f"]`, each `justification`
stating the ordered-argv-prefix limitation. No `sudo` rule (the
`refresh-extra-domains.sh` remedy needs it) and no rule for the
branch-delete case (not expressible as a prefix — `--delete` follows the
remote name), so the file mirrors `guard-bash.sh` and is nothing stricter.
Every constraint key and every table header is preceded by a comment naming
its `ConfigRequirementsToml` field with the file and line at the tag.

**AC2 — `devcontainer/codex/config.toml`.** Parses; sets only
`approval_policy = "never"`, `sandbox_mode = "danger-full-access"`,
`web_search = "disabled"`. `project_doc_max_bytes` is explicitly NOT set (a
comment says why). The header comment explains the bubblewrap/user-namespace
reason the Codex sandbox cannot run here (F11) and enumerates what enforces
safety instead.

**AC3 — `devcontainer/codex/hooks/hooks.json`.** Exactly the F4 schema: one
event (`PreToolUse`), two matcher groups (`Bash`, `apply_patch|Write|Edit`),
each with one `type: "command"` handler, absolute `/usr/local/bin/…` command,
`timeout: 30`. No `async` key, no other events.

**AC4 — `devcontainer/codex-guard-adapter.sh`.** `bash` mode pipes stdin
unchanged into `guard-bash.sh`; exit 2 propagates as exit 2 with the guard's
stderr; an `ask` reply is rewritten to `deny` with the identical reason;
`allow`/empty passes through. `patch` mode strips the four directive
prefixes literally (so paths containing spaces survive), resolves relative
paths against `.cwd`, calls `guard-fs.sh` per path with
`{"tool_name":"Write","tool_input":{"file_path":…}}`, and emits ONE deny
carrying the first offending reason if any path is denied or asked —
otherwise nothing, exit 0. Fails closed with exit 2 + stderr on: unknown
mode, wrong argument count, unreadable/empty/non-JSON stdin, a missing or
non-executable guard, a guard exiting non-zero for any other reason, a guard
reply that is not JSON, an unknown decision, and a relative patch path with
no `cwd`.

One deliberate design note for the reviewer: the guards are resolved from the
directory the adapter itself lives in (`$VIBE_GUARD_DIR` overrides), which in
the image IS `/usr/local/bin`. That is what lets the smoke tests and the
liveness gate exercise a copy of the whole chain without a second code path,
and it is not a weakening — `node` cannot write `/usr/local/bin`, and
`codex-guard-liveness` asserts ownership and mode of every file in the chain.
The header comment states this.

**AC5 — `devcontainer/codex-guard-liveness.sh`.** `--root` (default
`/etc/codex`), `--bin` (default `/usr/local/bin`), `--owner` (default
`root`); one `ok …` line per check on stdout; `LIVENESS FAILED: <check>` on
stderr with exit 1 on the first failure; starts nothing.
(a) ownership/mode of `requirements.toml`, `hooks/hooks.json`,
`codex-guard-adapter`, `guard-bash.sh`, `guard-fs.sh` and `jq`, via
`stat -L -c '%U/%a'` with the `stat -L -f '%Su/%Lp'` BSD fallback, rejecting
group- or other-writable modes. (b) anchored `grep -E` on non-comment lines
for `allow_managed_hooks_only = true`, `managed_dir = "/etc/codex/hooks"`,
`[features]`, `unified_exec = false`, `multi_agent = false`,
`multi_agent_v2 = false` (a commented-out line cannot match). (c) hook
commands enumerated with `jq`, each required to be an absolute path under the
canonical `/usr/local/bin` and to exist as an executable under `--bin`.
(d) the four deny fixtures through the adapter from `--bin`, composed with
`jq -n --arg`, accepting exit 2 or a JSON `deny`. (e) `git status` allowed.
(f) `codex --version` compared as three integers against 0.154.0.

Two judgement calls worth flagging, both documented in the script:
- `jq` is accepted as `root`-owned in addition to `--owner`. It is a
  distribution binary, not part of the vibe chain, and is always root-owned
  even when `--owner` relocates the chain to the test user — without this,
  `--owner $(id -un)` could never pass.
- `hooks.json`'s command strings are still required to start with the literal
  `/usr/local/bin/`, whatever `--bin` says, because that string is what a real
  Codex run executes; `--bin` only relocates where the file is looked for.
- Fixture runs redirect `VIBE_BLOCKS_LOG` into the script's temp dir so
  synthetic probes do not write "blocked" lines into the real audit log.

**AC6 — Dockerfile.** `COPY --chown=root:root codex/ /etc/codex/` and the two
scripts to `/usr/local/bin/codex-guard-adapter` / `codex-guard-liveness`,
placed directly after `COPY vibe-delegate.mjs`. `--chown` is required even
inside the `USER node` region because COPY otherwise keeps build-context
ownership. Modes are made deterministic in the existing root `RUN` (the two
scripts added to `chmod +x`; `chmod 0755 /etc/codex /etc/codex/hooks`;
`chmod 0644` on the three policy files). The sudoers block itself is
untouched — still exactly `init-firewall.sh`, `refresh-extra-domains.sh ""`
and `avahi-daemon`.

**AC7 — `docs/codex-tool-inventory.md`.** Every tool at the tag
(`exec_command`, `write_stdin`, `apply_patch`, `view_image`, `spawn_agent`,
`mcp__<server>__<tool>`, `request_permissions`, `request_user_input`, `plan`,
`web_search`) with hook name + aliases, `tool_input` fields, writes?,
executes?, gate, and mediating layer. `view_image` is marked **UNMEDIATED**
with its consequence (reads only, and reads are not what the backstops gate);
`write_stdin` is pinned off, with an explicit note that removing the pin
would make that row UNMEDIATED and why the upstream reasoning is not trusted.
Plus a table of the five pinned feature keys with each default at this tag,
and a "what is deliberately NOT claimed" section (no sandbox, no `deny_read`,
the exec policy is not coverage).

**AC8 — docs.** README paragraph added; `docs/codex-integration-plan.md`
already has F11 so it was left unchanged; MANUAL-TESTS Test 55 added with
step 0 (`vibe --rebuild` → `codex-guard-liveness` exits 0, `ls -la /etc/codex`
shows root ownership) plus four further steps and a Pass block.

**AC9 — NOT DONE, by instruction.** `smoke/checks_18_codex_runtime.py` and its
`smoke/runner.py` registration are the Tester's. Nothing under `smoke/` was
touched.

**AC10 — both suites green** (see below). The existing suites do not cover the
new files, so there were no expected failures.

## Commands run

- `shellcheck devcontainer/codex-guard-adapter.sh devcontainer/codex-guard-liveness.sh` → clean
- `python3 code-check.py` → `✓ shellcheck clean across 22 files`
- `python3 smoke-test.py < /dev/null` → `✓ smoke tests passed` (foreground, ~4 min)
- `python3 .vs/cycle-1/scratch-tests/check_codex_runtime.py` → 64/64 pass
- `codex features list` (no model contact) → confirmed the five pinned feature
  keys exist by that exact spelling, and their defaults at this build:
  `multi_agent` stable/true, `multi_agent_v2` stable/false, `apps`
  stable/true, `unified_exec` stable/true, `js_repl` **removed**/false.
- `codex --version` → `codex-cli 0.154.0`

No `codex exec` / `codex review` / any model-contacting command was run.

## Facts looked up, and where

Everything below was read from the cached Codex tree at tag `rust-v0.154.0`
(`scratchpad/codex/`, `scratchpad/codex-src/codex-rs/`), never guessed:

- `ConfigRequirementsToml` field names — `config_requirements.rs:984-1027`
  (cached `requirements/config_requirements_full.rs`). Note
  `allow_managed_hooks_only` is a top-level sibling bool (line 1002), NOT
  nested under `[hooks]`, and `features` is `#[serde(rename = "features")]`
  over `feature_requirements` (line 1010).
- `SandboxModeRequirement` variant spellings — explicit `#[serde(rename)]`
  at `config_requirements.rs:1392-1404`: `"read-only"`, `"workspace-write"`,
  `"danger-full-access"`, `"external-sandbox"`.
- `WebSearchModeRequirement` — `#[serde(rename_all = "snake_case")]` at
  `config_requirements.rs:789-796`, so `Disabled` → `"disabled"`.
- `AskForApproval` — `#[serde(rename_all = "kebab-case")]` at
  `protocol/src/protocol.rs:965-994`, so `Never` → `"never"`.
- `prefix_rules` shape — `requirements_exec_policy.rs:14-36`: array of
  `{pattern: [{token | any_of}], decision, justification}`; `decision =
  "allow"` is rejected at parse (`AllowDecisionNotAllowed`).
- `[hooks].managed_dir` — `ManagedHooksRequirementsToml` in
  `config/src/hook_config.rs`; the hooks-file shape (`HooksFile`, `MatcherGroup`,
  `HookHandlerConfig::Command` with `#[serde(rename = "timeout")]`) comes from
  the same file, which is why `hooks.json` uses `"timeout": 30` and no
  `description` key.
- `config.toml` key names — `config/src/config_toml.rs:155` (`approval_policy`
  176, `sandbox_mode` 205, `project_doc_max_bytes` 309, `web_search` 446);
  `WebSearchMode`/`SandboxMode` spellings in
  `protocol/src/config_types.rs:104,375`.
- Feature `key:` strings — `features/src/lib.rs`: `shell_tool` 916,
  `view_image` 922, `unified_exec` 940, `js_repl` 994, `multi_agent` 1260,
  `multi_agent_v2` 1266, `apps` 1284. Cross-checked against the image's own
  `codex features list`.
- apply_patch directive prefixes — `apply-patch/src/lib.rs` (`*** Add File:`,
  `*** Update File:`, `*** Delete File:`, `*** Move to:`; see the
  update+move test at lines 1073-1123).
- `write_stdin` has no PreToolUse — `tools/handlers/unified_exec/write_stdin.rs:124-129`.
- System config layer = `/etc/codex/config.toml` on Unix
  (`config/src/loader/mod.rs:66`), which is also what makes `/etc/codex/skills`
  the Admin skill root (`ext/skills/src/host_roots.rs:112-118`).

## Nothing was done to

`smoke/*`, `devcontainer/guard-bash.sh`, `devcontainer/guard-fs.sh`,
`devcontainer/init-firewall.sh`, `devcontainer/settings.local.json`, the
Dockerfile's sudoers block, `docs/codex-integration-plan.md`, `TODO.md`,
`CHANGELOG.md`. No commits, no pushes, no branch changes.
