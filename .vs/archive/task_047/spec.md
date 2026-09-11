# task_047 — Codex skills `$vs`, `$vss`, `$vsss` and the role-dispatch helper (plan item 5, branch `astra`)

## Task summary

Make `$vs`, `$vss` and `$vsss` invocable inside a Codex-led vibe container.
Two parts. (1) Three SKILL.md wrappers in the system skill root
(`/etc/codex/skills/<name>/SKILL.md`, the Admin scope root, verified at tag
`rust-v0.154.0`: `ext/skills/src/host_roots.rs:73-124` resolves Admin to
`<system config layer dir>/skills` and the system layer dir is
`/etc/codex/config.toml`'s directory, `config/src/loader/mod.rs:66`). Each
wrapper tells Codex to read the single-sourced command body at
`/usr/local/share/vibe/commands/<name>.md` and follow it, with a fixed
substitution table for the Claude-only primitives the bodies use. (2) The
substitution the bodies cannot do without: `/vs` dispatches Planner, Spec
Critic, Generator, Tester and Evaluator as separate subagents, but
`multi_agent` is pinned OFF for Codex (task_046, D1/D6), so role dispatch
becomes a subprocess: `vibe-delegate role <role> --model <astra|opus|sonnet|
haiku> --cwd <workspace>` runs ONE fresh top-level `codex exec` (Astra) or
`claude -p` (Claude tiers) with the tools that role needs, in the workspace,
under the same hooks and firewall as the lead, and returns the report and
usage as JSON. The lead stays whichever runtime the container was launched
with; this task ships the plumbing and its offline tests, not the live trial
(item 7). Nothing is written into the Mac's `~/.codex` or `~/.agents`.

## Acceptance criteria

- AC1 `devcontainer/codex/skills/{vs,vss,vsss}/SKILL.md` exist. Each has
  YAML frontmatter with exactly `name` (the command name, ≤ 64 chars) and
  `description` (non-empty, one sentence naming the vibe command it maps
  to), per `skills/src/parser.rs` at the tag; the body (a) names the
  command file `/usr/local/share/vibe/commands/<name>.md` as the text to
  follow verbatim, (b) carries the substitution table below, (c) states
  that in Codex's own terminal only the `$` form exists (the composer
  rejects an unknown `/vs` before submission, plan F6) while `/vs` is the
  same command in Claude Code and, once the supervisor lands, in unattended
  Codex runs, and (d) is under 60 lines. Substitution table (identical in
  all three): `Agent(subagent_type, model, prompt)` → `vibe-delegate role
  <role> --model <model> --cwd <workspace> < brief.txt` (roles: `planner`,
  `spec-critic`, `generator`, `tester`, `reviewer`, `evaluator`);
  `Skill(skill: "code-review")` → `vibe-delegate review codex < diff` plus
  the lead's own read; a nested `/vs ...` or `/vss ...` step inside `vss.md`
  / `vsss.md` → "read `/usr/local/share/vibe/commands/<that>.md` now and
  follow it in this same turn" (skill output is never rescanned for `$`
  mentions, plan F3, so a nested mention would not load anything);
  `Read`/`Write`/`Edit` → Codex's own file tools; `Bash`, `Grep`, `Glob` →
  Codex's shell tool (`rg`, `find`); `ScheduleWakeup` → "not available; end
  the turn and let the supervisor re-enter"; `/learnings` writes → refused
  (no ask in Codex).
- AC2 `devcontainer/Dockerfile` COPYs `codex/skills/` to `/etc/codex/skills/`
  with `--chown=root:root` (root-owned, 0644 files, 0755 dirs) in the same
  block as task_046's `/etc/codex` COPY; the smoke test asserts the COPY
  line and that no COPY targets `/home/node/.codex` or `~/.agents`.
- AC3 `vibe-delegate.mjs` gains the operation `role <planner|spec-critic|
  generator|tester|reviewer|evaluator> --model <astra|opus|sonnet|haiku|
  fable> --cwd <abs dir> [--consent-credits]`, payload (the role brief) on
  stdin. Validation fails closed: unknown role, unknown model, missing or
  relative `--cwd`, a `--cwd` that is not inside a git work tree, or an
  empty payload → non-zero exit, zero vendor processes. `fable` and any
  billed `VIBE_CLAUDE_P_BILLING` keep the per-task `--consent-credits`
  gate exactly as `ask` does.
- AC4 Role capability table, pinned as golden argv vectors: read-only
  roles (`planner`, `spec-critic`, `reviewer`, `evaluator`) run with every
  tool disabled exactly like `ask` (Astra: the existing `--disable` set,
  `--sandbox read-only`; Claude: `--tools ''`, `--permission-mode plan`);
  write roles (`generator`, `tester`) run IN the workspace with tools on:
  Astra `codex exec -m gpt-6-astra -C <cwd> --sandbox danger-full-access
  --ephemeral --skip-git-repo-check --json -c approval_policy="never" -c
  forced_login_method="chatgpt" -c cli_auth_credentials_store="file" -c
  web_search="disabled" --disable multi_agent --disable apps --disable
  js_repl --output-schema <schema> --output-last-message <file> -` (there
  is NO `-a` flag on `codex exec` 0.154.0 — approval is controlled only by
  the `-c approval_policy` key, as `codex()` already does; no
  `--ignore-user-config`, so the system requirements and managed hooks
  apply; no `--dangerously-bypass-*` flag ever), with `<schema>` and
  `<file>` ABSOLUTE paths inside the helper's private temp dir, never
  inside the workspace (the existing `codex()` joins them onto `cwd`,
  which is only safe because `cwd` is scratch today; the write roles pass
  `-C <workspace>` as the process cwd and keep their scratch files out of
  the tree). Claude `claude -p --model <m> --output-format json
  --permission-mode bypassPermissions --tools
  Bash,Read,Write,Edit,Glob,Grep --strict-mcp-config --mcp-config
  '{"mcpServers":{}}' --setting-sources user --no-session-persistence
  --disable-slash-commands --settings <inline JSON>` where the inline JSON is
  `{"forceLoginMethod":"claudeai","disableAllHooks":false,"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"/usr/local/bin/guard-bash.sh"}]},{"matcher":"Write|Edit|MultiEdit","hooks":[{"type":"command","command":"/usr/local/bin/guard-fs.sh"}]}]}}`
  (Astra's review: the lead's guard hooks live in the PROJECT's
  `.claude/settings.local.json`, which `--setting-sources user` excludes, so
  the write role carries both guards inline in the highest-precedence source
  with `disableAllHooks` pinned false; in a billed mode the user's settings
  file is merged with those keys into a private scratch copy that the
  helper passes instead), run with `cwd` = the workspace (hooks ON — no
  `--safe-mode`, so `guard-bash.sh`/`guard-fs.sh` mediate every tool call as
  they do for the lead; the tool allowlist deliberately excludes
  `Agent`/`Task`, `WebFetch`, `WebSearch` and `NotebookEdit`, so a role
  cannot spawn its own subagents or reach the web, and MCP stays empty so
  nothing unmediated by the guards can load). The test asserts each vector
  by exact list equality against the stub's recorded argv, that
  `--dangerously-bypass-approvals-and-sandbox` and `-a` never appear, that
  no scratch file lands under `--cwd`, and that the write roles' process
  cwd equals `--cwd` while the read-only roles' cwd is a private temp dir
  outside the repo.
- AC5 The role reply contract: Astra roles use an output schema
  `{report: string, status: "done"|"blocked"}`; Claude roles return the
  `result` text with `status` derived from the presence of a final line
  `STATUS: done|blocked` in the report (missing → `blocked`). The helper's
  JSON output is `{runtime, model, role, status, report, usage}` with the
  same usage accounting rules as `ask`; a clean reply whose status is
  `blocked` is still exit 0 (the helper succeeded, the role reported a
  block); a Codex `turn.failed`/`error` event or a Claude `is_error` reply
  → non-zero exit, never a `done`.
- AC6 The commands' Codex-substitution note: `vs.md`, `vss.md` and
  `vsss.md` each gain one short section "Running under Codex" (≤ 8 lines)
  pointing at the SKILL.md substitution table and stating that role
  dispatch is `vibe-delegate role`; no other change to the bodies.
- AC7 Docs: README's Codex section gains a "Skills in a Codex-led
  container" paragraph (where the skills live, why the Mac's `~/.codex`
  is never touched, what `vibe-delegate role` is, and that the live trial
  is item 7 / MANUAL-TESTS Test 55); `ask.md` gains a one-line pointer to
  `role`; `docs/codex-integration-plan.md` D5 is updated to say the
  substitution table and the role helper are what make the wrappers
  usable (the "thin wrapper" wording is no longer accurate).
- AC8 Tests in `smoke/checks_18_codex_runtime.py` (created by task_046;
  stays ≤ 1,500 lines, else a new `checks_19_codex_skills.py` registered
  in `smoke/runner.py`): SKILL.md frontmatter parsed with a minimal YAML
  reader (the two keys only), name/description/length/body assertions;
  Dockerfile COPY assertion; the `role` helper driven through the existing
  `_delegate_fixture` stubs for every AC3 refusal (zero calls), every AC4
  golden vector, AC5 status derivation (`done`, `blocked`, missing line,
  failed turn), and that read-only roles never receive `-C <cwd>`.
- AC9 `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null`
  fully green.

## Out of scope

- The supervisor (item 6) and `vibe --agent codex` (item 7); any live
  model call; `/prompts:vs` (Martin's decision, fromClaude T35); any
  `UserPromptSubmit` hook; edits to `guard-*.sh`, `init-firewall.sh`,
  `settings.local.json`; the usage ledger (item 9); changing what the
  command bodies do when Claude leads.

## Test location

`smoke/checks_18_codex_runtime.py` if under 1,500 lines after the
additions, otherwise a new `smoke/checks_19_codex_skills.py` registered in
`smoke/runner.py`; `smoke/checks_17_delegation.py`'s `_delegate_fixture`
may be imported, not modified.

## Proposed budget

2 cycles.

## Model plan

- Spec Critic: sonnet. Generator: sonnet (ceiling opus on a second
  capability failure; Fable NOT pre-authorised). Tester: haiku (escalate to
  sonnet if the golden vectors need a second pass). Evaluator: session
  model (Fable 5.1 chair).
