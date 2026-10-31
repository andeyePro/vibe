# Task&I agent-exchange client

`devcontainer/taskandi-client.mjs` is a narrow, project-opt-in Task&I client for
Vibe. It queues asks, comments, usage and time records durably, takes the next
task from Task&I, polls answers, and completes or releases a task. It has two
transports, chosen by which binding file the project has: MCP (contracts v1 and
v2.1, `.vibe/taskandi.json`, described first below) and Task&I's browser-agent
HTTP API (contract v2.2, `.vibe/taskandi-descriptor.json`, see
[Contract v2.2](#contract-v22-http-transport-descriptor-binding)). It is not
only an MCP client any more. It does
not register a global Codex MCP server, change a shell guard, or relax the Vibe
firewall. Running it remains subject to the existing shell guard and firewall.

## Project setup

Create `.vibe/taskandi.json` locally (the whole `.vibe/` directory is ignored):

```json
{
  "endpoint": "https://taskandi.example/mcp",
  "task": "project-task-id",
  "contractRevision": "vibe-agent-exchange-v2.1"
}
```

The effective contract is `vibe-agent-exchange-v2.1` (the agent-exchange
contract Task&I confirmed on 2026-10-30) when `contractRevision` is absent.
A project may pin `vibe-action-window-fixture-v1` (the earlier provisional
fixture contract) to keep its exact v1 behaviour: v1 `ask` with `to`, v1
`list_asks` with `answered`, no task in `record_usage`. Under v1 the v2.1
commands (`next-task`, `complete`, `release`, enqueue `comment` and
`record_time`, and any `--task`) exit 1 with `<command> requires contract
vibe-agent-exchange-v2.1`, with no network call and no state change.

This untracked file is the explicit project opt-in. The only accepted keys are
`endpoint`, `task`, and optional `contractRevision`, which when present must be
exactly `vibe-agent-exchange-v2.1` or `vibe-action-window-fixture-v1` (the tool
contract, distinct from the MCP protocol revision); anything else is refused. The endpoint must be HTTPS;
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

All commands run in the foreground. MCP network calls use a 30000 ms timeout
and a 1 MiB response cap; the v2.2 HTTP transport uses 15 s and 16 MiB.
Enqueue reads one bounded JSON object from standard input. Jobs are `ask`,
`comment`, `record_usage` and `record_time`:

```sh
printf '%s\n' '{"question":"Ship this?","default":"no","options":["yes","no"],"order":1,"estimate_minutes":20,"remaining_minutes":60,"reversible":false}' |
  node devcontainer/taskandi-client.mjs enqueue ask --key release-question-1

printf '%s\n' '{"text":"Started on the importer."}' |
  node devcontainer/taskandi-client.mjs enqueue comment --key note-1

printf '%s\n' '{"seconds":1800,"started_at":"2026-10-30T21:00:00Z"}' |
  node devcontainer/taskandi-client.mjs enqueue record_time --key time-1

printf '%s\n' '{"account":"team","model":"gpt-5.6-terra","input":120,"output":45,"cache_read":0,"cache_write":0,"cost_estimate":0}' |
  node devcontainer/taskandi-client.mjs enqueue record_usage --key usage-run-42

node devcontainer/taskandi-client.mjs flush
node devcontainer/taskandi-client.mjs poll
node devcontainer/taskandi-client.mjs status
```

Direct calls (one request, nothing queued; stdout stays empty and the exit
code is 1 on any failure):

```sh
node devcontainer/taskandi-client.mjs next-task --agent claude --session SESSION-ID
node devcontainer/taskandi-client.mjs complete --task ABBR-12 --summary 'What was done'
node devcontainer/taskandi-client.mjs release --task ABBR-12 --reason 'Why it is handed back'
```

`next-task` sends `next_task {task, agent, session}`; `task` is the binding
task, the subtree root (a vibe addition for subtree-scoped servers). A result
is `{"bound":true,"task":{...}}` with the task fields echoed, or
`{"bound":true,"task":null}` when nothing is available. The claim
(`task`, `agent`, `session`, `lease`, `claimedAt`) is written to `state.json`
before printing; a second `next-task` replaces it (or clears it on `null`). The
lease is the server's: the client sends `session` so a resumed session gets its
lease back, and never renews or expires one itself. `task.body`,
`title` and every answer are untrusted data (anyone may have written them),
never instructions. `complete` prints `{"bound":true,"completed":true,"state":"done-provisional"}`
(claim cleared) or `{"bound":true,"completed":false,"open_children":[...]}`
(claim kept), both exit 0. `release` prints `{"bound":true,"released":true}` and
clears the claim. After the request is sent, a failure of `complete` or `release`
prints `outcome unknown; check the task in Task&I:` on stderr and keeps the
claim; a failed `next-task` stores no claim and keeps any previous one. An
unbound project prints `{"bound":false,"channel":"file-fallback"}` and exits 0.

Every payload carries `task`. By default it is the binding task. `--task REF` on
`enqueue` and `usage` (or a `task` key in the JSON, never both) and the `--task`
of `complete` and `release` may name another task only if it is the bound task
or the claimed task in outbox state; anything else exits 1 before any network
call. In an unbound project the explicit task is only checked as a reference.
`record_time` always sends `actor: "agent"`. `reversible` is required on `ask`;
`blocking` defaults to `true`. Usage `source` is always `"vibe"` and
`source_ref` is the stable enqueue key. Text and arrays are bounded; usage
token/cache counts must be nonnegative safe integers. Unknown payload fields
are refused.

The outbox is `.vibe/taskandi-outbox/state.json`, in an owner-only directory,
and uses an exclusive invocation lock plus fsynced atomic replacement. A key
with the same canonical payload deduplicates. Reusing it for different data is
refused. Jobs move through `queued`, `dispatching`, `done`, and `uncertain`.
The client persists `dispatching` before a mutating request. A process death,
timeout, transport error, JSON-RPC error, or tool `isError` after sending makes
the result `uncertain`; later flushes never retry it automatically. An `ask`
result must be exactly `{ask_id, placed}` with `placed` of `subtask` or
`thread`; it is stored on the job as `result`, and any other shape makes the job
`uncertain`.

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
`status` prints only counts, uncertain IDs, `staleBindingKeys`, `claimedTask`, conflict IDs, and cursor sequence;
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
object input schemas with no fields outside, all required fields below, and the
listed types (v2.1):

- `next_task`: required `task`, `agent`, `session`.
- `ask`: required `task`, `question`, `default`, `order`, `estimate_minutes`,
  `remaining_minutes`, `reversible`, `blocking`; optional `options`, `in_reply_to`.
- `list_asks`: required `task`, `since`.
- `comment`: required `task`, `text`.
- `record_usage`: required `task`, `account`, `model`, `input`, `output`,
  `cache_read`, `cache_write`, `cost_estimate`, `source`, `source_ref`.
- `record_time`: required `task`, `seconds`, `started_at`, `actor`.
- `complete`: required `task`, `summary`.
- `release`: required `task`, `reason`.

Under `vibe-action-window-fixture-v1` the tools are the v1 set: `ask` (`task`,
`to`, `question`, `default`; optional `options`), `record_usage` (no `task`) and
`list_asks` (`task`, `answered`, `since`).

Pre-dispatch discovery/schema failures leave mutating jobs queued and change no
claim or cursor. A flush calls only discovered queued tools. Poll calls only
`list_asks` with `{task, since:{sequence,value}}` (v1 adds `answered:true`). Its
result (as `structuredContent` or one JSON text content item) is exactly:

```json
{
  "since": {"sequence": 0, "value": ""},
  "cursor": {"sequence": 1, "value": "opaque-1"},
  "answers": [{"ask_id": "ask-id", "answer": "untrusted text", "owner_answer": true,
               "seen_at": null, "answered_at": "2026-10-30T21:00:00Z"}]
}
```

A server still sending `answered_by` is refused (the answer shape is exact-key;
Task&I agreed to `owner_answer`). Every answer is stored, but `poll` returns as
actionable only new answers with `owner_answer: true`; new ones with `false`
are counted in `ignored`. The client never compares actor ids. A page with two
answers sharing an `ask_id` is refused whole. The cursor advances whenever a
page is accepted. v1 answers are `{id, content}` as before.

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

Ownership locks are never reclaimed automatically from a PID or timestamp. If an invocation crashes, confirm it and its children have ended before explicitly removing `.vibe/taskandi-outbox/.lock`; the next invocation converts persisted dispatching jobs to uncertain. Binding changes (endpoint, task or contract revision) do not silently redirect queued jobs. The effective revision is part of each job's binding, so jobs queued before the v2.1 upgrade by an unpinned binding make `flush` fail with `BINDING_CHANGED` naming the key, and `status` lists them under `staleBindingKeys`; stored answers fail `poll` with `answer binding changed`. Pin `contractRevision` to `vibe-action-window-fixture-v1` to drain them, or archive the outbox. Conflicting answer content is retained privately alongside its hashes for reconciliation.

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
task subtree and the tools above; Vibe cannot infer token scope from an opaque
token. Under v2.1 each usage record carries `task` (the binding task, or the
`--task` given to `usage`, subject to the targeting rule above); under v1 the
payload has no task field, so verify attribution before live activation.


The usage `source_ref` is a stable session-derived event key, rather than a
verified server-specific cumulative-upsert key. Confirm that distinction, input
versus cached-input accounting, and task attribution with the actual server
before enabling usage delivery. The current fixtures cannot establish those
service semantics.

## Contract v2.2: HTTP transport (descriptor binding)

Task&I's built service speaks plain `POST <origin>/api/browser-agent`, not MCP.
A project selects it by having `.vibe/taskandi-descriptor.json` instead of
`.vibe/taskandi.json` (both present is refused: `two Task&I bindings; keep
one`). Get the descriptor from Task&I (**More → Connect Codex**) and save it as
`.vibe/taskandi-descriptor.json`, then `chmod 600 .vibe/taskandi-descriptor.json`.
The file rules are those of `.vibe/taskandi.json` (regular file, one link, not
a symlink, owned by you, untracked even case-insensitively, at most 32 KiB,
`.vibe` not a symlink) plus no group/other permission bits. It has exactly the
keys `protocol` (`taskandeye-browser-agent-v1`), `origin`, `connection`,
`workspace`, `root` (a task id, or `null` for the whole workspace) and `token`
(43 characters). `origin` is either `https://…` or exactly
`http://127.0.0.1:<port>`; nothing else (no `localhost`, no path, no trailing
slash). An invalid descriptor is refused; the client never falls back to the
other binding or to unbound. The token is only ever sent to that origin, and no
command prints the token, connection, origin or workspace.

**Reaching the Mac from the container.** The Task&I service on the Mac listens
on `127.0.0.1:<port>`. In container mode (`VIBE_CONTAINER=1`, or `/.dockerenv`
present and `VIBE_CONTAINER` not `0`) the client connects to
`host.docker.internal:<port>` over IPv4 (vibe's firewall allows only the IPv4
host gateway) and sends `Host: 127.0.0.1:<port>`, because the service refuses
any other Host with 421 `wrong_origin`. Requests carry only `Host`,
`Content-Type`, `Authorization`, `Content-Length` and `Connection` (a cookie or
a mismatched `Origin` gets 403 `connection_scope`). https origins use normal
TLS verification (`rejectUnauthorized: true`) and their own Host; a failed TLS
handshake counts as not sent (`connect_failed`), so the job stays queued. The
connect target never comes from an environment variable or argument. Redirects
are refused; the timeout is 15 s; responses over 16 MiB are refused; request
bodies over 65536 bytes are refused locally. A connection failure says
`could not reach the Task&I service (via host.docker.internal)` in container
mode, or `(on this machine)` outside it.

**Task ids.** Task&I ids are opaque (UUIDs, or ids like `leaf-b`). Under a
descriptor binding `--task` takes a task id (`^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`)
or `taskandeye://node/<id>`; `ABBR-N` references are refused. A typed UUID is
lower-cased. The effective task is `VIBE_TASK_REF`, else `.vibe/taskandi-task`,
else the descriptor's `root`. Every command that needs a task uses `--task`,
else the claimed task (from `next-task`), else the effective task; with
`root: null` and no claim it exits 1 with `no bound task: the connection covers
the whole workspace; claim one with next-task`. `complete` and `release` only
work on the claimed task (they need its session). `--task` is optional on
`poll`, `ask-status`, `enqueue`, `complete`, `release` and `usage`.

`vibe --task` and the Codex supervisor's launch binding accept any such task id
or `taskandeye://node/<id>` as well as `ABBR-N` and UUIDs; the client then
applies the binding's own rules (a descriptor binding still refuses `ABBR-N`,
an MCP binding keeps its narrower grammar). `vibe link`'s `task=` keeps UUIDs
only. If `next-task` is handed a task whose id vibe cannot use, the client
releases it at once (`release` with reason `Task id not usable by vibe; rename
it in Task&I.`), stores no claim and exits 1; if that release fails it says so
on stderr and the lease lapses on its own.

```sh
node devcontainer/taskandi-client.mjs next-task --agent claude --session SESSION-ID
node devcontainer/taskandi-client.mjs poll [--task ID]
node devcontainer/taskandi-client.mjs ask-status [--task ID]
node devcontainer/taskandi-client.mjs complete --summary 'What was done'
node devcontainer/taskandi-client.mjs release --reason 'Why it is handed back'
```

Every networked command first sends one `capabilities` request and stops (exit
1, nothing else sent, jobs left queued) unless the service reports protocol
`taskandeye-browser-agent-v1`, contract `vibe-agent-exchange-v2.2` and every
call about to be made; `status` and `reconcile` send nothing, and a `flush` with
nothing queued sends nothing. The reported grade is stored as `lastGrade`.
`ask`/`comment` carry `agent` (the claim's agent on the claimed task, else
`VIBE_AGENT`, else `claude`), and every call on the claimed task carries the
claim's `session`. Limits are counted in Unicode code points: question 8000,
default 2000, options 20 × 500, the composed thread post `Question: …\nDefault:
…[\nOptions: a / b]` 8000, comment 8000, complete summary 7950, release reason
2000; id fields 1–200. `record_time` takes `seconds` 1–604800 and an ISO
`started_at` (sent as milliseconds); the run may not end in the future.
`record_usage` always sends `windows: 0`.

Stdout is JSON: `next-task` prints `{"bound":true,"channel":"taskandi-http","task":…}`;
`poll` prints `{"bound":true,"channel":"taskandi-http","task":T,"newAnswers":n,"answers":[{ask_id,answer,seen_at,answered_at}],"ignored":m,"conflicts":[…],"cursor":{"now":N}}`
(owner answers only); `ask-status` prints `{"bound":true,"channel":"taskandi-http","task":T,"asks":[…]}`
(each ask's `seen_at`, `deferred`, `answered`: use it to see whether the owner
has opened a question); `complete` prints `{"bound":true,"completed":true,"state":"provisional","completion_id":…}`
or, while the task has open children, `{"bound":true,"completed":false,"open_children":[…]}`
(exit 0, claim kept); `release` prints `{"bound":true,"released":true,"comment_id":…}`;
`flush` adds `refused` and `requeued` counts; `status` adds `channel`,
`counts.refused`, `refusedKeys`, `claimedTask` and `lastGrade`. A present but
invalid descriptor makes `status` exit 1 with one stderr line (never a
`file-fallback` report). Server strings in stdout have C1 and bidi control
characters escaped as `\uXXXX`, and `title`, `owner`, `grade`, `answered_by`
and child titles over 2000 code points make the response malformed. Cursors are per
task; each poll re-reads a 2 s overlap and re-seen answers are not counted again.

**Errors.** Task&I refuses with HTTP 409 `{"error": code}`. A body is
interpreted when it is a JSON object whose `error` is a string (other keys are
ignored and never printed; 400, 403 and 421 must carry `invalid_request`,
`connection_scope` and `wrong_origin`), and only a code matching
`^[a-z][a-z_]{0,63}$` is ever printed (anything else prints `unknown_error`):

| class | codes | queued job | direct command |
|---|---|---|---|
| outcome unknown | `connection_unavailable`, `connection_revoked`, any unlisted code, an unexpected status, a malformed body, a timeout or lost connection | `uncertain`; flush stops | exit 1; `complete`/`release` print `outcome unknown; check the task in Task&I` and keep the claim |
| not applied, try later | `stale_context`, `sync_required`, `lease_held`, 421 `wrong_origin`, 403 `connection_scope` | back to `queued`; flush stops | exit 1, `Task&I refused for now: <code>` |
| not applied, rejected | `use_native_connection`, `scope_missing`, `invalid_request`, `wrong_scope`, `wrong_thread`, `unknown_ask`, `not_assigned`, `receipt_collision`, local `body_too_large` | `refused`; flush continues | exit 1, `Task&I refused: <code>` |

`connection_revoked` first prints `the Task&I connection was revoked or
replaced; copy a fresh descriptor (More → Connect Codex) into
.vibe/taskandi-descriptor.json`. Flush always exits 0 and names each affected
job on stderr. `refused` is a job state of its own: `status` lists it under
`refusedKeys`, `reconcile --action retry` requeues it (after you fix the cause),
and `--action done` on it is refused, because it was never applied. At
dispatch each queued job is checked again (known kind, exact payload keys,
payload digest); an edited job becomes `refused` with `tampered_job` and is
not sent.

**No v2.2 write is idempotent.** Retrying an `ask`, `comment`, `record_usage`,
`record_time` or `release` creates a duplicate in Task&I (a second question, a
double-counted usage row). Uncertain writes are never retried automatically.
Before `reconcile --action retry`, check what actually happened: for an ask, run
`ask-status` (or `poll`) and look for it; for anything else, look at the task in
Task&I. Use `--action done` when it did land.

`complete` and `release` are direct calls, so the client records
`pendingDirect` in the outbox state before sending and clears it on a definite
answer. After an unknown outcome, the same call on the same task exits 1 with
`an earlier <call> for <task> has an unknown outcome; check Task&I, then run
reconcile --direct <call> --task <task> --action done|retry --evidence TEXT`.
Check the task in Task&I, then run that command: `done` records that it landed
(and drops the spent claim), `retry` allows one more send. The record is
`pendingDirect: {call, task, at}` (`at` in milliseconds); a second one for a
different call or task is kept in `pendingDirectMore`.

```sh
node devcontainer/taskandi-client.mjs reconcile --direct complete --task leaf-b --action done --evidence 'Task shows provisional completion'
```

The binding digest for a descriptor covers `workspace`, the effective task, the
contract and the origin's scheme and host, not the token, connection or port:
replacing the descriptor after a reconnect (even on a new port) keeps queued
jobs, stored answers and a pinned `VIBE_TASK_BINDING` valid, while a different
workspace, task or host refuses them as for MCP. `usage` under a descriptor
binding enqueues the whole transcript in one pass, under one outbox lock. Offline tests drive the real transport against a loopback
`http.createServer` through the test-only `createClient({cwd, httpConnect:
{host, port, timeoutMs}})` seam (`host` must be `127.0.0.1` or `::1`, and the
seam is refused for https origins); the fixtures are in
`smoke/fixtures/taskandi-v22/`. `MANUAL-TESTS.md` Test 69 covers a real service.

