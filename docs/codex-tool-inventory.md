# Codex tool inventory and which vibe layer mediates each tool

Tag **`rust-v0.154.0`** (commit `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`),
read from the OpenAI Codex source tree, not inferred from behaviour. Sources:
`codex-rs/core/src/tools/spec_plan.rs` (registration and gating),
`codex-rs/core/src/tools/hook_names.rs` (the hook-facing name and its
aliases), `codex-rs/features/src/lib.rs` (the `key:` string of every feature
flag), and `codex-rs/config/src/config_requirements.rs` (the requirements
schema). Verified against the image's own binary with `codex features list`.

The point of this file is the last column. For every tool Codex can call, a
vibe container must be able to say which layer stands between the model and
the machine — and, where nothing does, say that instead of implying
otherwise.

## The two senses of "tool name"

A tool has a name the model calls it by and a name the hooks see. They are
computed by different code (`hook_names.rs` is a deliberate compatibility
layer), and Codex's hook-facing names are already Claude Code's: the shell
tool arrives as `Bash` with the command in `tool_input.command`, and
`apply_patch` arrives with the aliases `Write` and `Edit`. That is what lets
vibe reuse `guard-bash.sh` and `guard-fs.sh` unmodified through
`/usr/local/bin/codex-guard-adapter`, rather than maintaining a second set of
rules.

Matchers in `hooks.json` are exact pipe-separated names when the whole string
is `[A-Za-z0-9_|]` (so `apply_patch|Write|Edit` is three exact alternatives,
not a regex), a full regex otherwise, and a missing matcher matches every
tool (`hooks/src/events/common.rs:143-174`).

## The mediation layers

| Layer | What it is |
|---|---|
| **guard via adapter** | The managed PreToolUse hook runs `/usr/local/bin/codex-guard-adapter`, which pipes the call into the unmodified `guard-bash.sh` (shell) or `guard-fs.sh` (per patched path) and rewrites every `ask` to `deny`. |
| **requirements pin** | `features.<key> = false` in `/etc/codex/requirements.toml`. This is a pin, not a default: `normalize_candidate` re-clamps it on every attempt to set the feature set, so no user config, project config or CLI flag can turn it back on. |
| **`mcp_servers` forbid** | The present-but-EMPTY `[mcp_servers]` table in requirements is an allowlist with no entries, so every configured MCP server is disabled. |
| **UNMEDIATED** | Nothing in vibe inspects this call. Listed with its consequence, because a layer that does not exist must not be described as if it did. |

## The inventory

| Model tool | Hook `tool_name` (aliases) | `tool_input` fields | Writes? | Executes? | Gate | Mediated by |
|---|---|---|---|---|---|---|
| `exec_command` | `Bash` | `command` (string; remapped from the model-facing `cmd`) | yes, via the shell | yes | `Feature::ShellTool` (`shell_tool`); unified-exec form gated by `unified_exec` | **guard via adapter** — `codex-guard-adapter bash` → `guard-bash.sh`. With `unified_exec` pinned off, Codex falls back to `ExecCommandHandler::one_shot`, still named `exec_command` and still hooked as `Bash`, so every command is inspected individually. Second layer: the `[rules]` prefix rules forbid `git push --force` / `git push -f` by argv prefix. |
| `write_stdin` | **no PreToolUse fires**; PostToolUse re-reports it as `Bash` | `session_id`, `chars`, `yield_time_ms`, `max_output_tokens` | yes, into a live PTY | writes to an existing session | `Feature::UnifiedExec` (`unified_exec`) — exists only when unified exec is on | **requirements pin** (`unified_exec = false`). Honest note: if that pin were ever removed this row becomes **UNMEDIATED**, because `pre_tool_use_payload` returns `None` for it by design (`unified_exec/write_stdin.rs:124-129`) — the reasoning being that its session was already gated at `exec_command` time. Consequence of trusting that reasoning: a shell whose first command passed the guard could then be fed arbitrary further input that the guard never sees. vibe does not trust it; it removes the tool. |
| `apply_patch` | `apply_patch` (aliases `Write`, `Edit`) | `command` (the RAW patch text, not JSON — the model-facing tool is freeform with a Lark grammar) | yes | no | `Feature::ApplyPatchFreeform` selects the freeform shape; requires the model's `apply_patch_tool_type` | **guard via adapter** — `codex-guard-adapter patch` extracts every path from the `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` directive lines, resolves relative ones against the hook payload's `cwd`, and runs `guard-fs.sh` once per path as a `Write`. Any single denied or asked path denies the whole patch, because apply_patch is atomic. |
| `view_image` | `view_image` | `path`, optional `detail`, optional `environment_id` | no | no | `Feature::ViewImage` (`view_image`) | **UNMEDIATED** — deliberately. It only reads an image into the model's context. Consequence: a Codex-led session can read any image file the `node` user can read, including one outside the repo; it cannot change anything, and every path it could read it could equally read with `cat` through the (hooked, but read-allowing) shell. Reads are not what the backstops gate — the container boundary is. |
| `spawn_agent` | `spawn_agent` (alias `Agent`) | agent-spawn arguments as given | no directly | indirectly — the child agent can exec | `Feature::Collab` (`multi_agent`, default **on**) for v1; `Feature::MultiAgentV2` (`multi_agent_v2`) for v2 | **requirements pin** (`multi_agent = false`, `multi_agent_v2 = false`). The child's own tool calls would be hooked, but its prompt envelope is not auditable from here and openai/codex#26130 (sibling envelopes leaking with `fork_turns: none`) is open. Both keys are pinned because they are separate gates and v1 defaults to on. |
| `mcp__<server>__<tool>` | `mcp__<server>__<tool>` (the `mcp__` prefix is always ensured) | the resolved JSON arguments for that server's tool | tool-dependent | tool-dependent | `mcp_servers` config, filtered by the requirements allowlist | **`mcp_servers` forbid** — the empty `[mcp_servers]` table disables every configured server, so no such tool is ever registered. Omitting the key would allow all servers; it is present and empty on purpose. |
| `request_permissions` | `request_permissions` | `reason`, `permissions` | no | no | `Feature::RequestPermissionsTool` (`request_permissions_tool`, "under development", off in this build) | **requirements pin** by construction — `allowed_approval_policies = ["never"]` leaves nothing for a permission request to escalate to, and the sandbox it would widen is unavailable here anyway. It can grant nothing that `danger-full-access` has not already granted, and it cannot reach past the hooks. |
| `request_user_input` | `request_user_input` | `questions` | no | no | `experimental_request_user_input_enabled` (a config option, not a `Feature`) | Not enabled, and inert if it were: a Codex-led vibe session is unattended, so there is no user to answer. It cannot change the filesystem or run anything. |
| `plan` / `update_plan` | `plan` | the plan steps | no | no | `update_plan_enabled` (config option) | Nothing to mediate — it edits the model's own visible plan, not the machine. |
| `web_search` | none — a hosted tool, no local tool call and therefore no hook | n/a | no | no | `Feature::WebSearchRequest` / `WebSearchCached` / `StandaloneWebSearch` | **requirements pin** by policy key — `allowed_web_search_modes = ["disabled"]`. This one matters: it is served by OpenAI's infrastructure, so the container firewall is not in its path. Disabling it in requirements is the only place it can be stopped. |

## Feature keys pinned off, and why each

| Key | Default at this tag | Reason for the pin |
|---|---|---|
| `unified_exec` | stable, **on** | Removes `write_stdin`, the one tool with no PreToolUse hook of its own. The one-shot `exec_command` fallback is still hooked per command. |
| `multi_agent` | stable, **on** | Sub-agent prompt envelopes are not auditable from inside the container; openai/codex#26130 is open. |
| `multi_agent_v2` | stable, off | A separate gate from `multi_agent`; pinned so a config change cannot flip it. |
| `apps` | stable, **on** | App tools reach third-party surfaces no vibe layer mediates. |
| `js_repl` | removed, off | An in-process JS interpreter would execute code without passing through the `Bash` hook. Marked "removed" in this build, so the pin is belt and braces — it costs nothing and survives the feature returning. |

## What is deliberately NOT claimed

- **No sandbox.** Codex's Linux sandbox is bubblewrap and needs unprivileged
  user namespaces, which the vibe container does not have (F11). Under
  `read-only` or `workspace-write` every tool call fails at exec time rather
  than being contained, so `danger-full-access` is the only mode in which a
  Codex-led session can work at all. The container, the firewall, root
  ownership of `/etc/codex` and `/usr/local/bin`, the exec policy and the
  hooks are the enforcement — the same set that holds a Claude Code-led
  session under `--permission-mode bypassPermissions`.
- **No `deny_read` list.** The requirements schema has one
  (`[permissions].filesystem.deny_read`) and no `deny_write` at all, but
  `deny_read` is enforced by the sandbox. Listing paths there would read as
  protection that is not present, so the file omits it.
- **The `[rules]` exec policy is not coverage.** A prefix rule matches an
  ordered prefix of a directly executed argv — never a substring, never
  inside `bash -c`. It is a narrow second layer for the force-push case. The
  hooks are primary.
