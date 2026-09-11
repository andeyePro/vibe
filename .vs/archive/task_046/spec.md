# task_046 — Codex system policy layer, guard adapter, liveness gate, tool inventory (plan item 4, branch `astra`)

## Task summary

Everything a Codex-led vibe container needs so that the two backstops hold
with Codex as the runtime, built as NEW files only (no guard edits): a
root-owned system policy under `/etc/codex/` baked into the image
(`requirements.toml` constraints, `config.toml` defaults, a managed
`hooks/hooks.json`), an adapter that feeds Codex's PreToolUse JSON to the
unchanged `guard-bash.sh` / `guard-fs.sh` and turns every `ask` into `deny`,
a liveness gate that refuses to start Codex unless the whole chain is
root-owned and demonstrably denies known-bad fixtures, and a written tool
inventory mapping every Codex tool at tag `rust-v0.154.0` to its guard.
Facts this rests on (plan § 1, F1-F4, F11): the hook wire contract is Claude
Code's (`tool_name` `Bash` with `tool_input.command`; `apply_patch` aliased
`Write`/`Edit` with the raw patch text in `tool_input.command`); requirements
allowlists constrain user/project config; `features.<key> = false` in
requirements PINS a feature off; `rules.prefix_rules` may only add
`forbidden`/`prompt`; `mcp_servers = {}` forbids every server; Codex's own
bubblewrap sandbox CANNOT run in the vibe container (no unprivileged user
namespaces), so `danger-full-access` is the only sandbox mode under which a
tool can execute (`read-only` stays allowed for the tool-less delegate runs)
and the container, the firewall, root ownership, the exec policy and the
hooks are the enforcement, exactly as for Claude Code. The `rules` exec
policy matches an ORDERED PREFIX of argv tokens only (never substrings, never
inside `bash -c`), so it is a narrow second layer for the force-push case,
not coverage; the hooks stay primary.

## Acceptance criteria

- AC1 `devcontainer/codex/requirements.toml` parses as TOML and contains
  exactly these constraints: `allowed_approval_policies = ["never"]`;
  `allowed_sandbox_modes = ["read-only", "danger-full-access"]`;
  `allowed_web_search_modes = ["disabled"]`; `allow_managed_hooks_only = true`;
  `[features]` with `multi_agent = false`, `multi_agent_v2 = false`,
  `apps = false`, `js_repl = false`, `unified_exec = false` (pinning
  unified exec off removes `write_stdin`, which has no PreToolUse of its own
  and would otherwise feed unhooked input into a live PTY; the one-shot
  `exec_command` fallback is still hooked as `Bash` per command);
  `[mcp_servers]` present and EMPTY; `[hooks]` with
  `managed_dir = "/etc/codex/hooks"`; `[rules]` with `prefix_rules` entries
  of `decision = "forbidden"` mirroring exactly what `guard-bash.sh` blocks
  and nothing stricter: the token prefixes `git push --force` and
  `git push -f` (`--force-with-lease` stays allowed as in the guard; no
  `sudo` rule, since the documented `refresh-extra-domains.sh` remedy needs
  it), each with a `justification` that states the prefix-only limitation.
  Every constraint line is preceded by a comment naming its field in the
  tag's `ConfigRequirementsToml` (`codex-rs/config/src/config_requirements.rs`);
  the test asserts that comment is present for every constraint key; no key
  outside that struct.
- AC2 `devcontainer/codex/config.toml` parses and sets only defaults the
  requirements allow: `approval_policy = "never"`,
  `sandbox_mode = "danger-full-access"`, `web_search = "disabled"`,
  `project_doc_max_bytes = 0` is NOT set (project docs stay readable in a
  led session), and a header comment explains that the Codex sandbox is
  unavailable in the container (F11) and what enforces safety instead.
- AC3 `devcontainer/codex/hooks/hooks.json` validates against the F4 schema:
  `{"hooks": {"PreToolUse": [ {matcher: "Bash", hooks:[{type:"command",
  command:"/usr/local/bin/codex-guard-adapter bash", timeout: 30}]},
  {matcher: "apply_patch|Write|Edit", hooks:[{type:"command", command:
  "/usr/local/bin/codex-guard-adapter patch", timeout: 30}]} ]}}` — no other
  events, no `async`, every command an absolute path under `/usr/local/bin`.
- AC4 `devcontainer/codex-guard-adapter.sh` (installed as
  `/usr/local/bin/codex-guard-adapter`, mode 0755 root): `bash` mode pipes
  stdin unchanged into `/usr/local/bin/guard-bash.sh`; exit 2 from the guard
  propagates as exit 2 with the guard's stderr; a JSON reply whose
  `hookSpecificOutput.permissionDecision` is `ask` is rewritten to `deny`
  with the same reason (Codex-led sessions are unattended); `allow`/empty
  passes through. `patch` mode extracts every path from the patch text in
  `tool_input.command` (`*** Add File: `, `*** Update File: `,
  `*** Delete File: ` and `*** Move to: ` lines), resolves relative paths
  against the hook JSON's `cwd`, runs `/usr/local/bin/guard-fs.sh` once per
  path with `{"tool_name":"Write","tool_input":{"file_path":<path>}}`, and
  emits a single `deny` (first reason) if ANY path is denied or asked;
  otherwise emits nothing and exits 0. Unknown mode, unreadable stdin, or a
  guard that is missing or not executable → exit 2 with a reason on stderr
  (fail CLOSED inside the adapter, even though Codex would fail open on a
  spawn error).
- AC5 `devcontainer/codex-guard-liveness.sh` (installed as
  `/usr/local/bin/codex-guard-liveness`, 0755 root) exits 0 only when ALL
  hold, printing one line per check: (a) `/etc/codex/requirements.toml`,
  `/etc/codex/hooks/hooks.json`, `/usr/local/bin/codex-guard-adapter`,
  `/usr/local/bin/guard-bash.sh`, `/usr/local/bin/guard-fs.sh` and `jq`
  exist, are owned by `--owner` (default `root`) and are not group/other
  writable (`stat -L -c %U/%a`, BSD fallback `%Su/%Lp`); (b) requirements.toml
  has, on a NON-comment line, `allow_managed_hooks_only = true` and
  `managed_dir = "/etc/codex/hooks"` (matched with anchored `grep -E`
  patterns that ignore leading whitespace and trailing comments; a
  commented-out line does NOT satisfy the check) and the `[features]` pins
  `unified_exec = false`, `multi_agent = false`, `multi_agent_v2 = false`;
  (c) every `command` in hooks.json (enumerated with `jq`) is an existing
  executable under `/usr/local/bin`; (d) three fixtures through the adapter:
  a shell redirect into the Codex login dir → deny (exit 2 or JSON deny), a
  patch updating `/home/node/.codex/config.toml` → JSON deny, a shell
  fixture writing under `/learnings` → JSON deny (ask became deny), and a
  patch adding a file under `/learnings` → JSON deny (patch-mode ask became
  deny); (e) a benign fixture (`git status`) → allowed; (f) `codex --version`
  ≥ 0.154.0 compared as three integers (the same rule as `vibe-delegate.mjs`
  `codexVersionOk`, never a string compare).
  `--root <dir>` and `--bin <dir>` relocate the policy and binary roots for
  tests; `--owner <user>` sets the expected owner. Any failure → exit 1 with
  `LIVENESS FAILED: <check>` on stderr; nothing is ever started by it.
- AC6 `devcontainer/Dockerfile` COPYs `codex/` to `/etc/codex/` and the two
  scripts to `/usr/local/bin/`, all root-owned (`--chown=root:root`), files
  0644 / dirs 0755 / scripts 0755, placed after the existing `COPY
  vibe-delegate.mjs` line; the `node` user has no sudo rule that could
  modify them (the existing sudoers block is unchanged and the test asserts
  it lists only the three existing commands).
- AC7 `docs/codex-tool-inventory.md` lists every tool name at the tag from
  `codex-rs/core/src/tools/spec_plan.rs` / `hook_names.rs` (`exec_command`
  → hook `Bash`; `write_stdin` (no PreToolUse of its own, PostToolUse as
  `Bash`); `apply_patch` → hook `apply_patch`/`Write`/`Edit`; `view_image`;
  `spawn_agent`/`Agent`; `mcp__<server>__<tool>`; `request_permissions`;
  `request_user_input`; `plan`; `web_search`) with columns: hook name, input
  fields, writes/executes?, gate (feature flag or requirements key), and
  which layer mediates it (guard via adapter, requirements pin, `mcp_servers`
  forbid, or `UNMEDIATED` with a one-line consequence — `write_stdin` and
  `view_image` are the honest `UNMEDIATED` rows, `write_stdin` because its
  session was already gated at `exec_command` time and `view_image` because
  it only reads).
- AC8 Docs: README's Codex section gains a "Codex-led sessions: how the
  backstops hold" paragraph (system policy, no sandbox, liveness gate,
  ask-becomes-deny); `docs/codex-integration-plan.md` § 1 gains F11 (sandbox
  unavailable; hook names Claude-compatible; `/etc/codex/skills` is the
  admin skill root) if not already present; MANUAL-TESTS gains Test 55 step
  0: after `vibe --rebuild`, `codex-guard-liveness` exits 0 in the
  container and `ls -la /etc/codex` shows root ownership.
- AC9 Tests in a new `smoke/checks_18_codex_runtime.py` (registered in
  `smoke/runner.py`): TOML/JSON parse of the three policy files
  (`tomllib`); AC1 key set and values exactly; AC3 schema; adapter `bash`
  mode against the REAL `devcontainer/guard-bash.sh` (fixture text built in
  Python, never via a shell redirect) for: redirect into the login dir →
  deny, force-push → exit 2, `/learnings` write → deny (was ask), `git
  status` → allow; adapter `patch` mode against the REAL `guard-fs.sh` for a
  patch touching `/home/node/.codex/config.toml` → deny, a patch touching
  `/workspace/.vibe-allow-codex` → deny, a relative-path patch resolved
  against `cwd` → allow, a patch whose `*** Update File:` path contains
  spaces and a `*** Move to:` line pointing into the login dir → deny,
  a patch with no directive lines → allow (nothing to check), a patch
  adding a file under `/learnings` → deny; missing guard → exit 2; AC1's
  per-constraint citation comments present; liveness with `--root`/`--bin`
  pointing at a fixture copy: `--owner $(id -un)` → exit 0 and one line per
  check; default owner (root) against node-owned fixtures → exit 1 naming
  the ownership check; a fixture where the adapter is replaced by `exit 0`
  (fail-open stub) → exit 1 naming the fixture check; a requirements file
  missing `allow_managed_hooks_only` → exit 1. Dockerfile assertions: the
  COPY lines exist with `--chown=root:root` and the sudoers block is
  unchanged (compare against the literal three-rule block).
- AC10 `python3 code-check.py` clean (both new scripts are shellcheck-clean);
  `python3 smoke-test.py < /dev/null` fully green.

## Out of scope

- Any edit to `guard-bash.sh`, `guard-fs.sh`, `init-firewall.sh`,
  `settings.local.json`, sudoers, or the container's capabilities/seccomp
  (enabling user namespaces for Codex's sandbox is Martin-gated and recorded
  in TODO); the Codex skills (item 5); the supervisor (item 6); `vibe --agent
  codex` and the container entry script (item 7); any `UserPromptSubmit`
  hook; `deny_read` permissions (inert without the sandbox, deliberately
  omitted rather than falsely reassuring).

## Test location

New `smoke/checks_18_codex_runtime.py` (≤ 1,500 lines), registered in
`smoke/runner.py`. Fixture text for guard inputs is composed in Python
strings and passed on stdin to the scripts, never written through a shell
redirect (the Bash hook in the authoring container blocks those idioms).

## Proposed budget

3 cycles — two new shell scripts plus a policy tree, opus tier.

## Model plan

- Spec Critic: sonnet. Generator: opus (security-shaped; next rung Fable is
  NOT pre-authorised). Tester: haiku (escalate to sonnet if the adapter
  fixtures need more than one pass). Evaluator: session model (Fable 5.1
  chair).
