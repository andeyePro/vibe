# Task&I Action Window client

`devcontainer/taskandi-client.mjs` is a narrow, project-opt-in MCP client for
Vibe. It queues asks and usage records durably, and polls answered asks. It does
not register a global Codex MCP server, change a shell guard, or relax the Vibe
firewall. Running it remains subject to the existing shell guard and firewall.

## Project setup

Create `.vibe/taskandi.json` locally (the whole `.vibe/` directory is ignored):

```json
{
  "endpoint": "https://taskandi.example/mcp",
  "task": "project-task-id",
  "contractRevision": "vibe-action-window-fixture-v1"
}
```

This untracked file is the explicit project opt-in. The only accepted keys are
`endpoint`, `task`, and optional `contractRevision`, which when present must be
exactly `vibe-action-window-fixture-v1` (the provisional tool contract, distinct from the MCP protocol revision). The endpoint must be HTTPS;
plain HTTP is accepted only for `localhost`, literal loopback, or
`host.docker.internal`. Userinfo, query strings, fragments, symlinks, and any
case-insensitive tracked form of `.vibe/taskandi.json` are refused.

Put the bearer token in `.vibe/taskandi-token`, owned by the current user and
with no group/other permission bits (for example `chmod 600`). The helper reads
no vendor authentication directory. It refuses redirects and sends the token
only to the configured URL origin. Tokens and server response bodies are never
logged. The configured host must already be allowed by Vibe's firewall through
the normal human-controlled project setup; this client adds no bypass.

Without the config, the project is unbound. Enqueues still enter the local
file-channel outbox and `status`, `flush`, and `poll` explicitly report
`file-fallback`; nothing is silently discarded and no network request occurs.
File-fallback jobs remain file-fallback jobs if a binding is added later; they
are never silently promoted into network deliveries.

## CLI

All commands run in the foreground. Network calls use a 30000 ms timeout.
Enqueue reads one bounded JSON object from standard input:

```sh
printf '%s\n' '{"to":"martin","question":"Ship this?","default":"no","options":["yes","no"]}' |
  node devcontainer/taskandi-client.mjs enqueue ask --key release-question-1

printf '%s\n' '{"account":"team","model":"gpt-5.6-terra","input":120,"output":45,"cache_read":0,"cache_write":0,"cost_estimate":0}' |
  node devcontainer/taskandi-client.mjs enqueue record_usage --key usage-run-42

node devcontainer/taskandi-client.mjs flush
node devcontainer/taskandi-client.mjs poll
node devcontainer/taskandi-client.mjs status
```

Ask `task` comes only from the binding. Usage `source` is always `"vibe"` and
`source_ref` is the stable enqueue key. Text and arrays are bounded; usage
token/cache counts must be nonnegative safe integers. Unknown payload fields
are refused.

The outbox is `.vibe/taskandi-outbox/state.json`, in an owner-only directory,
and uses an exclusive invocation lock plus fsynced atomic replacement. A key
with the same canonical payload deduplicates. Reusing it for different data is
refused. Jobs move through `queued`, `dispatching`, `done`, and `uncertain`.
The client persists `dispatching` before a mutating request. A process death,
timeout, transport error, JSON-RPC error, or tool `isError` after sending makes
the result `uncertain`; later flushes never retry it automatically.

Resolve an uncertain result only after obtaining independent evidence:

```sh
node devcontainer/taskandi-client.mjs reconcile --key release-question-1 \
  --action done --evidence 'Task&I audit entry 812 confirms creation'

node devcontainer/taskandi-client.mjs reconcile --key usage-run-42 \
  --action retry --evidence 'Task&I audit query confirms no matching record'
node devcontainer/taskandi-client.mjs flush
```

Evidence and the decision are retained in the reconciliation log. `retry` is
an explicit user decision. This client makes no exactly-once claim: exactly-once
delivery requires verified server-side idempotency keyed to the stable ID.
`status` prints only counts, uncertain IDs, conflict IDs, and cursor sequence;
it does not print tokens, queued payloads, or answer content.

## Offline fixture contract and later conformance

The module exports `createClient`, `createMcp`, `loadConfig`,
`validatePayload`, `fetchTransport`, constants, and `main`. Offline tests inject
an async `transport(request)` into `createClient({cwd, transport})`; there is no
CLI bypass flag. A fixture response has `{status, headers, contentType, body}`.
`body` is bounded JSON, or bounded `text/event-stream` containing exactly one
JSON `data:` event. Redirects and other streaming transports are unsupported.

Every invocation initializes MCP revision `2025-11-25`, sends
`notifications/initialized`, then calls `tools/list`. The fixture must advertise
object input schemas with no fields outside and all required fields from:

- `ask`: required `task`, `to`, `question`, `default`; optional `options`.
- `record_usage`: required `account`, `model`, `input`, `output`, `cache_read`,
  `cache_write`, `cost_estimate`, `source`, `source_ref`.
- `list_asks`: required `task`, `answered`, `since`.

Pre-dispatch discovery/schema failures leave mutating jobs queued. A flush calls
only discovered queued `ask` or `record_usage` tools. Poll calls only
`list_asks` with `{task, answered:true, since:{sequence,value}}`. Its fixture
result (as `structuredContent` or one JSON text content item) is exactly:

```json
{
  "since": {"sequence": 0, "value": ""},
  "cursor": {"sequence": 1, "value": "opaque-1"},
  "answers": [{"id": "answer-id", "content": "untrusted text"}]
}
```

The echoed `since` must equal the request. Sequence must not regress; an equal
sequence with a changed opaque value is noncomparable and refused. Answers are
atomically saved before a second atomic cursor advance. Repeated IDs with the
same content deduplicate; changed content is retained as an explicit conflict
identified by ID and content digests. Answer text is stored and returned as
untrusted data only—it is never evaluated or executed.

This is a fixture-tested Vibe capability, not a claim of compatibility with a
live Task&I service. Before enabling a real endpoint, Task&I must verify the
three exact input schemas above, initialize revision negotiation, session-header
name, JSON/SSE response framing, tool result envelope, the `list_asks` cursor and
answer shape, and whether stable IDs provide server-side idempotency. If the
actual schema differs, update this documented fixture contract and its offline
tests from the authoritative server schema; do not weaken discovery validation.

Ownership locks are never reclaimed automatically from a PID or timestamp. If an invocation crashes, confirm it and its children have ended before explicitly removing `.vibe/taskandi-outbox/.lock`; the next invocation converts persisted dispatching jobs to uncertain. Binding changes (endpoint, task or contract revision) do not silently redirect queued jobs. Conflicting answer content is retained privately alongside its hashes for reconciliation.

## Binding and boundary integration

Run from any directory inside the project: configuration and outbox resolve to
the git worktree root. An untracked `.vibe/taskandi-task` can contain one
`ABBR-123` or `taskandeye://node/UUID` reference. It overrides the JSON default;
`vibe <project> --task ABBR-456` overrides both for that launch. A launch binding
alone does not opt a project into network access: the endpoint configuration
and separately scoped token are still required. Switching task or endpoint
refuses old answer/cursor state and queued deliveries until explicitly
reconciled. Archive the prior private outbox before starting a different task;
never delete uncertain-delivery evidence to obtain a fresh retry.

The installed Codex context instructions direct the chair to enqueue questions,
flush and poll at task boundaries, and retain the Markdown fallback. This is
model-mediated orchestration, not a background poller or a promise every model
will follow instructions. A crash after a poll may leave answers saved but not
consumed: reconcile the saved answers against the chair's consumed ledger.

The `usage` command imports only an explicitly identified session JSONL file:

```sh
taskandi-client usage --transcript /path/to/this-session.jsonl \
  --session stable-session-id --account my-account --cost-estimate 0
```

The estimate is explicit and applies to each new usage record; use zero only
when that is a justified estimate under your billing arrangement. Unknown cost
must not silently become zero. The importer reads `turn_context.model` and
cumulative Codex `event_msg/token_count.info.total_token_usage` fields, including
cache-read and cache-write counts. It emits deltas with stable cumulative keys;
repeated snapshots deduplicate. Missing metadata stays unknown, regressing or
unsupported counts fail, and an unfinished final line waits until the next
boundary. The current importer does not parse Claude transcripts or combine
separate delegate ledgers. Keep those totals separately rather than guessing.

The dedicated bearer token must be constrained by the server to the intended
task and `ask`, `list_asks`, and `record_usage`; Vibe cannot infer token scope
from an opaque token. Verify that usage is attributed to that task before live
activation, because the provisional usage payload has no task field.


The usage `source_ref` is a stable session-derived event key, rather than a
verified server-specific cumulative-upsert key. Confirm that distinction, input
versus cached-input accounting, and task attribution with the actual server
before enabling usage delivery. The current fixtures cannot establish those
service semantics.
