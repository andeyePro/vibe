# Codex integration plan (phase 1a close-out and phase 1b)

Branch `astra`. Written 2026-09-11 by the `/vsss` run, reviewed once by GPT-6
Astra (its five BLOCKING findings and five WARNINGS are folded in below and
recorded verbatim in `.vss/sessions/2026-09-11T17-11-32Z.md`). Every Codex fact
is cited to the release tag of the installed binary or to its `--help`, never
assumed. Scope per Martin's decisions of 2026-09-10
(`/brain2/andeye/vibe-ChatGPT.md` § 10): `/vs`, `/vss`, `/vsss` in both
runtimes, both prefixes; `/ask`; the two backstops are the floor.

## 0. What already shipped (phase 1a, commits 5e329db..b2d41fe)

- `devcontainer/vibe-delegate.mjs`: `ask <astra|opus|sonnet|haiku|fable>` and
  `review codex` — one-shot `codex exec -m gpt-6-astra --output-schema --json`
  in a private temp dir, read-only sandbox, every tool disabled; `claude -p`
  for the Claude tiers with tools off. Usage counts come from CLI metadata.
- `/ask` and `/review` command files; the Codex review slot with a JSON
  findings contract; `.vibe/review-slots` per-project policy.
- Launcher: read-write `~/.codex` bind at `/home/node/.codex`, gated on an
  UNTRACKED `.vibe-allow-codex` marker plus drift-recreate when the opt-in
  changes; fail-closed when a container cannot be inspected.
- Guards: `guard-fs.sh` denies tool writes under `/home/node/.codex` and to
  the marker; `guard-bash.sh` blocks the shell idioms.
- Codex CLI 0.154.0 in the image; version floor enforced by the helper.
- Live partial pass of MANUAL-TESTS Test 54 on real Docker (2026-09-10).

## 1. Facts verified against the Codex source

Source: tag `rust-v0.154.0` = `openai/codex@6b9826e3aa83b1a5947db50f4332cb9c65f1b340`
(the installed binary's release), read 2026-09-11; a few structural facts were
first read on `main@2c9e1a57` and re-checked at the tag where marked. Plus
`codex --help` / `codex features list` from the installed 0.154.0.
"Unverified" marks a claim the research could not tie to source; each such
claim is settled inside the iteration that depends on it before any code
relies on it.

- F1 Config layers (`codex-rs/config/src/loader/mod.rs:100-129`): package <
  admin (macOS managed prefs) < system `/etc/codex/config.toml` < cloud <
  user `$CODEX_HOME/config.toml` < profile < cwd < tree `./.codex/config.toml`
  (walk-up) < repo `<git root>/.codex/config.toml` < runtime flags. So a
  value in the SYSTEM config.toml is a default, not a constraint: user,
  project and `-c` values override it (Astra B1).
- F2 Requirements are a SEPARATE constraint stack
  (`config/src/config_requirements.rs:984`, `loader/mod.rs` `compose_requirements`,
  `constraint.rs`): `/etc/codex/requirements.toml` is composed with cloud
  bundles into `Constrained<T>` allowlists; any user/project/`-c` value
  outside an allowlist is rejected at config load (`ConstraintError::InvalidValue`).
  Top-level keys at the tag include `allowed_approval_policies`,
  `allowed_sandbox_modes`, `allowed_web_search_modes`,
  `allowed_permission_profiles`, `features` (a flattened name→bool map that
  gates feature flags such as `multi_agent`), `permissions.filesystem.deny_read`,
  `experimental_network`, `mcp_servers` (allowlist map), `plugins`, `apps`,
  `rules` (an exec policy, `RequirementsExecPolicyToml`),
  `additional_developer_instructions`, `allow_managed_hooks_only`, and
  `hooks.managed_dir` (a directory holding `hooks.json`). A managed hook that
  fails to LOAD is `HookRequirement::Required` and aborts startup
  (`hooks/src/engine/discovery.rs:58-70,220-240`); every other hook source
  loads as Optional and a bad file is only a warning.
- F3 Hook wire contract is Claude Code's (`hooks/src/schema.rs`,
  `events/pre_tool_use.rs`): stdin `{session_id, turn_id, transcript_path,
  cwd, hook_event_name, model, permission_mode, tool_name, tool_input,
  tool_use_id}`; shell-like tools pass `tool_input.command`. Output honoured:
  `hookSpecificOutput.{hookEventName, permissionDecision: allow|deny|ask,
  permissionDecisionReason, updatedInput, additionalContext}` or legacy
  `decision: approve|block` + `reason`. Exit 2 blocks with stderr as the
  reason (`pre_tool_use.rs:260-289`). Any other non-zero exit, or a missing
  binary (`spawn_error`, `engine/command_runner.rs:248-262`), is
  `HookRunStatus::Failed` with `should_block=false`: a crashing or absent hook
  FAILS OPEN at run time, and no startup check can prevent a later crash
  (Astra B2). `PermissionRequest` hooks answer
  `hookSpecificOutput.decision.behavior: allow|deny`; any deny wins.
  `UserPromptSubmit` may only add `additionalContext`
  (`events/user_prompt_submit.rs`); that text is NOT re-scanned for `$name`
  skill mentions, only the user's typed text is (`tui/src/chatwidget.rs:372`).
- F4 `hooks.json` schema (`config/src/hook_config.rs`): `{hooks: {<Event>:
  [{matcher?, hooks: [{type: "command", command, timeout?, async?, ...}]}]}}`
  for the 12 events `PreToolUse, PermissionRequest, PostToolUse, PreCompact,
  PostCompact, SessionStart, SessionEnd, UserPromptSubmit, SubagentStart,
  SubagentStop, Stop, Interrupt`. `hooks: stable, true` in `features list`.
- F5 Skills: `$name` is a generic text mention (`skills/src/mentions.rs`,
  `TOOL_MENTION_SIGIL = '$'`) resolved per turn in core, so `codex exec`
  prompts carry it too (inferred: same pipeline, no exec-specific loader).
  SKILL.md frontmatter needs `name` (<=64) and `description`
  (`skills/src/parser.rs`). Scopes `User, Repo, System, Admin`
  (`protocol/src/protocol.rs:3822`). Root paths UNVERIFIED against source
  (the enumerating crate is not in the public tree): community docs say repo
  `.agents/skills/`, user `~/.agents/skills/`, admin `/etc/codex/skills/`.
- F6 The Codex TUI REJECTS an unknown slash command before submission:
  `tui/src/bottom_pane/chat_composer.rs` `prepare_submission_text_with_options`
  shows `Unrecognized command '/<name>'`, restores the draft and submits
  nothing. Built-in commands are a fixed enum (`tui/src/slash_command.rs`);
  the only user-defined form is custom prompts in `$CODEX_HOME/prompts/*.md`,
  invoked as `/prompts:<name>` (or `/<name>` once listed), deprecated in
  favour of skills; no repo-scope prompts dir (open issues #4734, #9848).
  So `/vs` in the Codex TUI cannot be a hook or a file vibe owns (Astra B3).
- F7 `codex exec --json` emits ONLY `thread.started {thread_id}`,
  `turn.started`, `turn.completed {usage: {input_tokens,
  cached_input_tokens, cache_write_input_tokens, output_tokens,
  reasoning_output_tokens}}`, `turn.failed {error: {message}}`,
  `item.started|updated|completed`, `error {message}`
  (`exec/src/exec_events.rs`). The JSONL emitter DISCARDS
  `codex_error_info` (`exec/src/event_processor_with_jsonl_output.rs`), so
  a quota failure is indistinguishable from any other failure in exec JSON,
  and no rate-limit snapshot is emitted there at all; exit code is 1 for
  every failed turn. The discriminator and the limits exist only on the
  protocol stream: `EventMsg::Error{codex_error_info: UsageLimitExceeded |
  RateLimitExceeded | ContextWindowExceeded | ServerOverloaded | ...}`
  (`protocol/src/protocol.rs:1851`) and `EventMsg::TokenCount{rate_limits:
  RateLimitSnapshot{primary, secondary: RateLimitWindow{used_percent: f64,
  window_minutes: Option<i64>, resets_at: Option<i64>}, credits,
  rate_limit_reached_type, plan_type}}` — reachable through
  `codex app-server` (Astra B5). Flags (`exec --help`): `--json`,
  `--output-schema FILE`, `-o FILE`, `-C DIR`, `-s read-only|workspace-write|
  danger-full-access`, `--ephemeral`, `--ignore-user-config` (auth still from
  `CODEX_HOME`), `-c key=value`, `--skip-git-repo-check`, `resume`, `fork`;
  NO `--full-auto`.
- F8 `CODEX_HOME` is honoured (`core/src/config/mod.rs`); with
  `cli_auth_credentials_store = "file"` auth is `$CODEX_HOME/auth.json`
  (`login/src/auth/storage.rs`). Rollouts are ALWAYS `$CODEX_HOME/sessions/`
  (`rollout/src/lib.rs:84`); no key or env var relocates them separately.
- F9 app-server is JSON-RPC over stdio/unix/ws (`codex app-server --help`),
  protocol in `app-server-protocol/src/protocol/v2/{thread,turn,thread_data}.rs`
  (`thread/start`, `turn/start`, `thread/resume`; `TurnError` there KEEPS
  `codex_error_info`); `codex exec` is itself an in-process app-server client.
  `@openai/codex-sdk` 0.154.0 spawns the CLI and exchanges JSONL, it does not
  speak JSON-RPC.
- F11 (tag, `core/src/tools/hook_names.rs`, `ext/skills/src/host_roots.rs`,
  `sandboxing/src/manager.rs`; probed in this container 2026-09-11) Hook
  names are already Claude-shaped: the shell tool `exec_command` reaches
  hooks as `tool_name: "Bash"` with `tool_input.command` (a string);
  `apply_patch` reaches them as `apply_patch` with aliases `Write`/`Edit`
  and the raw patch text in `tool_input.command`; `write_stdin` fires no
  PreToolUse of its own; MCP tools are `mcp__<server>__<tool>`; matchers
  are exact pipe-separated names or a regex, missing means all. The admin
  skill root is `<system layer dir>/skills` = `/etc/codex/skills` on Unix.
  `features.<key> = false` in requirements PINS the feature (every set is
  clamped), `rules.prefix_rules` accept only `forbidden`/`prompt`, an EMPTY
  `[mcp_servers]` forbids every server, and there is no `deny_write`.
  Codex's Linux sandbox is bubblewrap and needs unprivileged user
  namespaces, which the vibe container does not have (`unshare -U` and
  `codex sandbox -- echo` both fail here); `read-only`/`workspace-write`
  therefore cannot execute any tool, and a Codex-led session must run
  `danger-full-access` with the container, firewall, root-owned policy,
  exec-policy rules and hooks as the enforcement, exactly as for Claude
  Code. Enabling user namespaces for the container is a security-posture
  change and is Martin-gated.
- F10 `multi_agent` and `multi_agent_v2` are `stable, true` by default;
  issue openai/codex#26130 (sibling prompt envelopes leak with
  `fork_turns: none`) is still OPEN. `codex review` has no `--json` /
  `--output-schema`; `codex exec review` has them and needs an explicit
  `--uncommitted|--base|--commit`.

## 2. Design decisions the facts force

- D1 **Vibe's Codex policy is a REQUIREMENTS file in the image, never in the
  Mac's `~/.codex`.** `/etc/codex/requirements.toml` (root-owned, baked by
  the Dockerfile) carries the constraints, not defaults (F1, F2):
  `allowed_approval_policies = ["never"]`, `allowed_sandbox_modes =
  ["read-only", "danger-full-access"]` (F11: Codex's own sandbox cannot run
  in the container, so `workspace-write` would fail closed at exec time
  while reading as protection; `read-only` stays for the tool-less delegate
  runs), `allowed_web_search_modes = ["disabled"]`, `features` pinning
  `multi_agent`/`multi_agent_v2`/`apps`/`js_repl`/`unified_exec` off
  (`unified_exec` off removes `write_stdin`, which has no PreToolUse of its
  own), an empty `mcp_servers` allowlist, `allow_managed_hooks_only = true`,
  `hooks.managed_dir = "/etc/codex/hooks"`, and `rules` prefix rules
  mirroring exactly what `guard-bash.sh` blocks (force-push), stated as a
  prefix-only second layer. `deny_read` is deliberately omitted: the sandbox
  that would enforce it is unavailable, so listing it would read as
  protection that is not there. Each key's enforcement is verified per key against the
  tag's `TryFrom<ConfigRequirementsWithSources>` before it is relied on. A
  node-user session cannot edit, shadow or relax any of it. The Mac's
  `~/.codex` keeps only what Codex itself writes there (auth, sessions).
- D2 **Guards are reused unchanged through an adapter; hooks are one layer,
  not the boundary.** `devcontainer/codex-guard-adapter.sh` receives Codex's
  PreToolUse JSON (F3), maps Codex tool names onto the `Bash`/`Write` shapes
  `guard-bash.sh` and `guard-fs.sh` parse, execs the unchanged guard, and
  turns every `ask` into `deny` (a deliberate unattended policy, not a Codex
  limitation). Because a crashing hook fails open at run time and a startup
  probe cannot prevent that (F3, Astra B2): (a) the whole chain — adapter,
  guards, `jq`, their parent directories — is root-owned and read-only to
  `node`; (b) the critical prohibitions are ALSO enforced without hooks: the
  Codex sandbox and `deny_read` from D1, the `rules` exec policy, the
  firewall, and the mounts; (c) `devcontainer/codex-guard-liveness.sh` still
  runs before Codex starts, feeding each managed hook a known-bad fixture and
  requiring the deny, and refuses to boot otherwise — it catches
  misconfiguration, not a later crash, and the docs say so. The tool
  inventory (every tool Codex can enable at the tag and its input shape) is
  written down in item 4 and each entry maps to a guard, the sandbox, or an
  explicit "unmediated" line.
- D3 **`/vs` is not achievable inside the Codex TUI by anything vibe owns**
  (F6): the composer rejects unknown slash commands before submission, hooks
  never see the text, and `additionalContext` is not scanned for skills.
  What ships: `$vs`, `$vss`, `$vsss` as native Codex skills (D5); `/vs` and
  `$vs` both accepted by the unattended path (the supervisor, D7, rewrites
  the prefix before dispatch); `/vs` and `$vs` both accepted in Claude Code
  (D4). The one remaining gap — typing `/vs` in Codex's own terminal — has
  exactly one supported route, custom prompts in the user's own
  `$CODEX_HOME/prompts/`, invoked as `/prompts:vs`. That is a Martin decision
  (posted to `vibe-fromClaude.md`): a consented host-side `vibe codex
  prompts` installer, or accept `$vs` there.
- D4 **`$vs` in Claude Code is a CLAUDE.md fragment**, not a hook: a prompt
  beginning `$vs`, `$vss` or `$vsss` means "invoke that skill with the rest as
  arguments". A `UserPromptSubmit` hook would be deterministic but is a
  `settings.local.json` hook edit, Martin-gated; the fragment ships now and
  the hook is listed for him.
- D5 **Codex skills ship as SKILL.md wrappers in the system skill root**
  (`/etc/codex/skills/{vs,vss,vsss}/SKILL.md`, path settled in-iteration per
  F5 with an offline discovery probe), landed in item 5 (task_047). "Thin
  wrapper" is no longer accurate: each SKILL.md names
  `/usr/local/share/vibe/commands/<name>.md` as the text to follow verbatim
  and carries the fixed substitution table those bodies need for every
  Claude-only primitive they use — `Agent`, `Skill(skill: "code-review")`, a
  nested `/vs`/`/vss` mention, `Read`/`Write`/`Edit`, `Bash`/`Grep`/`Glob`,
  `ScheduleWakeup`, and `/learnings` writes. What actually makes the wrapper
  usable is that table plus `vibe-delegate role <role> --model <astra|opus|
  sonnet|haiku|fable> --cwd <workspace>` (`vibe-delegate.mjs`'s new `role`
  operation): one fresh top-level `codex exec` or `claude -p` process per
  `/vs` role — read-only roles (planner, spec-critic, reviewer, evaluator)
  tool-less exactly like `ask`; write roles (generator, tester) run in the
  workspace with tools on, under the same hooks and firewall as the lead.
  The command bodies stay single-sourced. Nothing is written into the Mac's
  `~/.codex` or `~/.agents`.
- D6 **Reviewer isolation = separate top-level (unprivileged `node`)
  sessions with NO tools at all.** Distinct `CODEX_HOME` per reviewer would
  require copying `auth.json` (F8), which vibe never does. The panel runner
  spawns N independent `codex exec` processes exactly as `vibe-delegate`
  already does: read-only sandbox, shell/patch/MCP/apps/multi-agent
  disabled, `--ephemeral`, each in a private temp cwd holding only its own
  diff snapshot on stdin. Threat model: a reviewer can read nothing but its
  stdin, so sibling rollouts under the shared `sessions/` are unreachable by
  construction; the residual risk is the vendor's own spawn path (#26130),
  which is closed by `multi_agent` being pinned off in requirements (D1).
  The shipped test pins the argv vectors (verify vs ship differ by exactly
  `--ephemeral`) and the tool-disable set against a stub; the live nonce
  proof (each reviewer's OWN rollout, by `thread_id`, holds only its own
  nonce) costs N Astra calls and is Martin-gated. The runner is
  `devcontainer/codex-panel.mjs`, shipped as `/usr/local/bin/codex-panel`
  (task_050): `codex-panel run --n <2-5> [--verify] [--out <dir>]`, diff on
  stdin, one JSON object of per-reviewer verdicts on stdout, exit 1 for any
  incomplete panel. `--verify` locates each reviewer's rollout with the
  template pinned at tag `rust-v0.154.0`:
  `$CODEX_HOME/sessions/<YYYY>/<MM>/<DD>/rollout-<YYYY-MM-DDTHH-MM-SS>-<thread_id>.jsonl`
  (`rollout/src/rollout_file_name.rs` render, `rollout/src/recorder.rs`
  precompute_new_rollout_path), plus the
  `rollout-<timestamp>-<thread_id>_<rollout_id>.jsonl` variant a reverted
  thread gets and the `.jsonl.zst` compressed sibling
  (`rollout/src/compression.rs`). The thread id is never a filename prefix.
- D7 **The supervisor is an app-server client, not a `codex exec` wrapper**
  (F7, F9, Astra B5): `devcontainer/codex-supervisor.mjs` (shipped as
  `/usr/local/bin/codex-supervisor`, task_048) spawns `codex app-server` on
  stdio — argv exactly `['app-server']`, child env exactly `PATH`, `HOME`,
  `CODEX_HOME`, `LANG` — and speaks newline-delimited JSON with NO `jsonrpc`
  field. Method names, verified against tag `rust-v0.154.0`
  (`app-server-protocol/src/protocol/common.rs` and `protocol/v2/*`) and
  camelCase on the wire: `initialize` (id 1) then `account/rateLimits/read`
  (id 2) before any turn; `thread/start {cwd, approvalPolicy:"never",
  sandbox:"danger-full-access", ephemeral:false}` → `thread.id`;
  `turn/start {threadId, input:[{type:"text",text}]}`; `thread/resume
  {threadId}`. The terminal event is the `turn/completed` notification —
  there is no `turn/failed` — carrying `turn.status`
  (`completed|interrupted|failed|inProgress`) and, when failed,
  `turn.error.codexErrorInfo`, externally tagged so unit variants are bare
  strings (`"usageLimitExceeded"`, `"rateLimitExceeded"`,
  `"sessionBudgetExceeded"`, `"contextWindowExceeded"`,
  `"serverOverloaded"`) and struct variants single-key objects
  (`{"httpConnectionFailed":{"httpStatusCode":429}}`). Streaming text is
  `item/agentMessage/delta`; completed items arrive as `item/completed`; an
  `error` notification with `willRetry: true` is transient and ignored.
  Quota: `account/rateLimits/read` and the sparse `account/rateLimits/
  updated` carry `RateLimitSnapshot{primary, secondary}` with
  `{usedPercent, windowDurationMins, resetsAt}` — `resetsAt` is UNIX
  SECONDS — merged per window, and the supervisor waits until the binding
  window's `resetsAt` plus a 120 s grace (bounded 300/600/1200/2400 s
  backoff when no reset time is known), then re-sends the turn. After a kill
  it sends `thread/resume {threadId}` and then a FRESH `turn/start`, never
  `turn/steer`: a hard-killed turn is projected as `inProgress` forever.
  Persistence: thread id and every counter are written atomically to
  `<cwd>/.vss/codex-supervisor.json` at each change and before every wait,
  so a killed supervisor resumes idempotently; ceilings on turns, resumes,
  quota waits, transient retries and wall time exit 3; a prompt-hash or cwd
  mismatch exits 2 unless `--new-run` archives the old state. Exit code 1
  alone is never treated as quota — only `codexErrorInfo` is.
- D8 **The opt-in that mounts the ChatGPT login moves to the host.**
  `~/.vibe/codex-allow` (one project path per line, like `~/.vibe/repos`) is
  required IN ADDITION to the untracked `.vibe-allow-codex` marker; a session
  can create the marker by a path the hooks cannot see, but it cannot reach
  the Mac's `~/.vibe`. Withdrawal: `vibe codex deny <path>` also stops that
  project's running container (with confirmation) so revocation is
  immediate, not launch-time only (Astra W4).
- D9 **Astra reviews, Claude leads, until the Codex-led trial passes.** Every
  iteration ends with one `vibe-delegate review codex` call on the diff. A
  BLOCKING finding is fixed and re-reviewed once; if it is still BLOCKING the
  item stays open and uncommitted-to-`main`, it never ships on the cap
  (Astra W5).

## 3. Ordered delivery queue

Each item is one `/vs` task on `astra`, one commit, suite green
(`python3 code-check.py`, `python3 smoke-test.py < /dev/null`), then ONE Astra
review of the diff via `vibe-delegate review codex` (D9). Order follows
Astra's Q5: exact-version contracts, threat model and runtime enforcement
before conveniences; the host registry before any credential-bearing trial.

| # | Item | Files (new or changed) | Mechanical gate | Gen tier |
|---|------|------------------------|-----------------|----------|
| 1 | This plan + Astra's plan review folded in | `docs/codex-integration-plan.md`, TODO, CHANGELOG | doc exists; every F-line cites a path at the tag; suite green | chair |
| 2 | Helper hardening: `codex=off` also stops `/ask astra` (egress switch); `claude -p` argv gains `--permission-mode plan`, drops `disableAllHooks`; launcher warns when the Codex login dir is group/world-readable | `vibe-delegate.mjs`, `ask.md`, `review.md`, README, `vibe`, `checks_17` | fixture `codex=off` makes `ask astra` exit non-zero with zero calls, `ask haiku` unaffected; golden argv vector for the Claude leg; mode-warning fixture | sonnet |
| 3 | Host-side registry `~/.vibe/codex-allow`: launcher requires registry line AND untracked marker; drift-recreate on withdrawal; `vibe codex allow|deny|list` (deny stops the running container) | `vibe`, README, MANUAL-TESTS, `checks_15`/`checks_17` | fixtures: marker-only refused, registry-only refused, both mount, withdrawal drifts, path canonicalisation, deny argv | opus |
| 4 | Requirements policy layer + tool inventory + guard adapter + liveness runner: `/etc/codex/{requirements.toml,hooks/hooks.json}` baked root-owned; `codex-guard-adapter.sh`; `codex-guard-liveness.sh`; `docs/codex-tool-inventory.md` | `devcontainer/codex/*`, adapter, liveness, `Dockerfile`, new `smoke/checks_18_codex_runtime.py` | each requirements key present and shaped per F2; adapter feeds the real guards: a shell write into the Codex login dir denied, a `/learnings` write denied (ask becomes deny), a benign command allowed; liveness exits non-zero against a fail-open stub and against a mutable requirements file; hooks.json validates against F4; inventory covers every tool name the tag can enable | opus |
| 5 | Codex skills `$vs/$vss/$vsss` in the system skill root; fromClaude question on `/prompts:vs` | `devcontainer/codex/skills/*/SKILL.md`, `Dockerfile`, `checks_18`, `vibe-fromClaude.md` | SKILL.md frontmatter valid per F5; skill root path settled with a cited source (or an offline discovery probe) before the COPY lands | sonnet |
| 6 | Supervisor as app-server client: thread/turn/resume, prefix rewrite, quota wait on `resets_at`, persistence, ceilings, cancellation; offline against a stub `codex app-server` | `devcontainer/codex-supervisor.mjs`, `checks_18` | stub emits `codex_error_info: usage_limit_exceeded` with a `rate_limits` snapshot and the supervisor waits (fake clock) then `thread/resume`s the recorded id; plain failure means no resume; kill-and-restart resumes from the persisted state exactly once; ceilings stop; no network | opus |
| 7 | **DELIVERED, pending live trial (task_049).** `vibe --agent codex`: launcher flag + untracked `.vibe/agent` file + `VIBE_AGENT`; refusal before Docker when the login mount is not granted; `launch_codex` / `launch_codex_plain` (no heartbeat, marker or stall watchdog — auto-resume stays Claude-only); root-owned `/usr/local/bin/codex-entry` runs the liveness gate and refuses to start Codex on any failure; `agent   :` header line; `codex-entry` added to the gate's ownership list. `devcontainer.json` NOT changed — the entry script is reached through `devcontainer exec`, not `postStartCommand`. Live trial is MANUAL-TESTS Test 55's Codex-led block (Martin) | `vibe`, `devcontainer/codex-entry.sh`, `devcontainer/codex-guard-liveness.sh`, `devcontainer/Dockerfile`, `devcontainer/install-claude-extras.sh`, `.gitignore`, README, MANUAL-TESTS (Test 55) | launcher fixtures: flag parsing, refusal without registry+marker, argv golden; entry script refuses on liveness failure | opus |
| 8 | Codex panel runner `codex-panel.mjs` for `/vs --panel` on Codex: N tool-less processes, private cwds, nonce, verify/ship argv symmetric difference `{--ephemeral}` | `devcontainer/codex-panel.mjs`, `vs.md`, `checks_18` | argv pins; tool-disable set pinned; nonce assertion against stub rollouts; live proof recorded as Martin-gated | opus |
| 9 | **DELIVERED (task_052).** Usage ledger: helper appends one JSONL line per call (runtime, model, billing, tokens, ISO time; no payload, no ids) to `.vibe/delegate-usage.jsonl` (untracked); `/budget` reports `claude -p` and Astra separately | `vibe-delegate.mjs`, `budget.md`, `.gitignore` block, `checks_17` | record shape asserted; ledger contains no payload bytes; failed calls log `error` rows | sonnet |
| 10 | **DELIVERED (task_051).** `$vs`, `$vss`, `$vsss` in Claude Code: CLAUDE.md fragment synced by `install-claude-extras.sh`; command files gain a one-line "alias form" note | `devcontainer/claude-md/dollar-prefix.md`, `vs.md`, `vss.md`, `vsss.md`, `checks_13` | fragment synced by the installer test; each command file names its `$` form | sonnet |

Items 4-8 depend on 1; 7 depends on 3, 4, 5; 6 is independent of 4-5 except
for the prefix rewrite table. Items 9 and 10 are independent of everything.

## 4. Deliberately not built in this run (Martin-gated)

- Any edit to `guard-bash.sh`, `guard-fs.sh`, `init-firewall.sh` or the
  `settings.local.json` permission lists: the `/learnings`/`/zotero` idiom
  hardening, the `/repos/*/.vibe-allow-codex` deny, and a hook-level gate for
  the Fable consent flag all wait for Martin.
- The remaining live legs of MANUAL-TESTS Test 54, the PR to `main`, and any
  push.
- Anything that writes into the Mac's `~/.codex` (skills, prompts, hooks):
  vibe never modifies the user's own Codex configuration; the `/prompts:vs`
  route in D3 is his call.
- The live blind-panel nonce proof (N Astra calls) and the first Codex-led
  trial (item 7 on real Docker): item 7's code, gate and docs shipped in
  task_049, but nothing in it has ever started a real Codex session — that is
  MANUAL-TESTS Test 55's Codex-led block, and it is Martin's to run.

## 5. Astra call budget

Plus tier: 5-45 Astra messages per 5 hours. This run spends one call on the
plan review (done: 15,137 tokens) and one per delivered iteration (plus at
most one re-review on a FAIL), and no calls on plumbing verification, which
uses stubs.
