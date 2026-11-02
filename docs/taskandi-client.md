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
(`task`, `agent`, `session`, `lease`, `claimedAt`; under a descriptor binding
also `claimedAtMs`, `allowance`, `spent`, `spentAt`, `defaults_allowed` and,
when sent, `hardDeadline`, `latest_start`, `estimate_minutes`) is written to
`state.json` before printing; a second `next-task` replaces it (or clears it on `null`). The
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
boundary.

Claude Code transcripts are recognised by content (records with `type:
"assistant"` and `message.usage`). Each distinct `message.id` counts once (the
last record for it): `input_tokens`, `output_tokens`, `cache_read_input_tokens`
and `cache_creation_input_tokens` (absent = 0; other usage keys are ignored);
all-zero messages such as `<synthetic>` are skipped. Every `*.jsonl` in the
sibling `<transcript without .jsonl>/subagents/` directory is read too, so the
session pays for its subagents. One import makes one `record_usage` job per
model, summing every message not imported before, keyed `usage-` + the first
16 hex digits of sha256 of `[session, model, last message id]`. Per session
and transcript file, `state.json` (`usageImports`) keeps a small ledger entry
`{offset, prefixLen, prefixSha, tailIds}`: the byte offset already imported
(transcripts only grow), the sha256 of the first `prefixLen` bytes (at most
4 KiB), and the counted message ids in the last 64 KiB before the offset, so a
message whose records straddle the offset is not counted twice. It is written
in the same locked write as the jobs, on the descriptor and the MCP/file paths
alike, so a re-run imports only new messages and a re-run with nothing new
enqueues nothing. A file that shrank, or whose prefix changed, is re-read from
0 (as is a file with an older id-list entry): a message counts as already
imported when it comes at or before the last message the old entry names, or,
per model, at or before the last message whose one-message key
(`[session, model, id]`) a live job or tombstone already holds. Only the final,
unfinished line may be unparseable; any other bad line fails the import. The
importer does not combine separate delegate ledgers (`vibe-delegate`); keep
those totals separately rather than guessing.

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

## Contract v2.3 (and v2.4, v2.5) alongside v2.2

Task&I's v2.3 adds safe retries, a sequence cursor for answers, claiming a named task, and limits the server publishes. The client speaks v2.2 and the v2.3 family, chosen per invocation. Wire facts: `/brain2/andeye/Task&I-agent-exchange-fixtures/README.md`, sections "v2.3 changes" and "Decided" (v2.4 and v2.5 add `create_task`, `update_task` and `repeat`: see "Proposing tasks" below). Fixtures: `smoke/fixtures/taskandi-v23/` (copied as v2.5; see its `PROVENANCE.md`).

**Negotiation.** Every command's one `capabilities` request decides the revision. `contract` must be `vibe-agent-exchange-v2.2`, `-v2.3`, `-v2.4` or `-v2.5`; anything else fails before any other request (exit 1). v2.4 and v2.5 follow every v2.3 rule below.
- A v2.2 answer has exactly today's keys; one carrying `limits` or `id_pattern` is malformed.
- A v2.3-family answer also carries `limits` and `id_pattern`. `limits` must hold the twelve keys `unit` (`code_points`), `id`, `id_unit` (`utf16_code_units`), `request_bytes`, `question`, `default`, `options`, `option`, `ask_post`, `comment`, `summary` and `reason`, each count a positive integer. Extra keys are ignored. `id_pattern` must equal the client's own task-id pattern exactly. Any mismatch fails before any other request.
- Every successful answer, v2.2 included, is stored as `state.lastContract` (`status` prints it as `lastContract`). `next-task` records it on the claim as `claim.contract`, and every job records `sentRevision` when it is dispatched.
- The binding digest does not change: it keeps the literal `vibe-agent-exchange-v2.2`, so queued jobs, stored answers and pinned fingerprints stay valid when the server switches revision.

**request_id and frozen bodies.** Each queued write (`ask`, `comment`, `record_usage`, `record_time`) gets a `requestId` (a lowercase UUID v4) at enqueue. It is kept outside the payload and the dedupe digest.
- On v2.3 the first dispatch builds the exact body once: the fields, the session resolved from the claim now, `agent`, `request_id`, `action` and `connection`. It is stored as `sentBody`, with the session and the time it was frozen, in the same state write that marks the job `dispatching`. One builder makes every body; size and server-limit checks measure exactly the text that is sent.
- A later v2.3 attempt sends `sentBody` byte for byte. A job edited after freezing (a payload field, a session other than the recorded one, an `agent` other than `claude`/`codex`, an `at` outside the window applied at freeze time) is refused as `tampered_job`.
- `request_id` is never sent on reads or to a v2.2 server. Bodies sent to v2.2 are built as before and never frozen.

**Why a resend is safe, and when it is not.** Task&I replays a `request_id`'s original answer only for the same body from the same connection. So, on the same connection, an answer to a resend proves no attempt was ever applied only when it comes from inside the exchange transaction, after the replay lookup: HTTP 409 with one of `stale_context`, `sync_required`, `lease_held`, `use_native_connection`, `scope_missing`, `invalid_request`, `wrong_scope`, `wrong_thread`, `unknown_ask`, `not_assigned` (`RESEND_PROOF_CODES`). Any other answer to a resend (`connection_revoked`, `connection_unavailable`, HTTP 400/403/405/421, any other 409 code, any other status) is outcome unknown. After a re-grant (the descriptor's `connection` changed) replay is impossible, so a frozen body is never resent: the job becomes `uncertain` with `sent on a previous Task&I connection; replay is unavailable — check Task&I, then reconcile`, and nothing is sent. `reconcile --action retry` on it rebuilds the body on the new connection and prints `this sends a new write on the current connection; Task&I cannot tell it from the earlier one, so check it was not applied`. So a resend answered `connection_revoked` stays `queued` with its body (and prints the revoked message); once a fresh descriptor is installed, the next flush marks it `uncertain` this way and never resends it.

**Send rules (v2.3).** On a first send, every 409 and every exactly-formed 400/403/405/421 means nothing was applied. On a resend only the proof codes above do; every other answer is treated as a lost response (first row).

| answer | job | flush |
|---|---|---|
| lost response, timeout, socket loss, non-JSON body, unrecognised status, 200 that fails the schema; on a resend also any answer that is not a proof code (`sentBody` kept) | back to `queued`, `attempts` + 1; `uncertain` after 5 attempts | stops |
| any send: `stale_context`, `sync_required`, `lease_held`; first send only: `connection_revoked` (prints the revoked message), `connection_unavailable`, 403 `connection_scope`, 405 `method_not_allowed`, 421 `wrong_origin` | back to `queued`, `sentBody` dropped (rebuilt next time with the same `requestId`) | stops |
| `use_native_connection`, `scope_missing`, `invalid_request` (409; 400 on a first send only), `wrong_scope`, `wrong_thread`, `unknown_ask`, `not_assigned` | `refused`, `sentBody` dropped | continues |
| `receipt_collision` on a first send | `refused`, `sentBody` dropped, a new `requestId` | continues |
| `receipt_collision` on a resend (Task&I holds another body under this `request_id`: only a changed or mismatched stored body explains it) | `uncertain`, never retried (`reconcile --action retry` refuses it) | stops |
| not sent (connect failure, a local size refusal) | as try-later; a first send freezes nothing, a resend keeps its body; `attempts` unchanged | stops |

- **Crash.** A job found `dispatching` with a v2.3 `sentRevision` goes back to `queued` and keeps its `sentBody`. Any other becomes `uncertain`, as on v2.2.
- **Downgrade.** A job that has a `sentBody`, flushed against a v2.2 server, becomes `uncertain` with no request ("attempted on v2.3; the server now speaks v2.2, so a resend could duplicate").
- **Upgrade.** A job that became `uncertain` on v2.2 is never retried automatically. After `reconcile --action retry`, the next v2.3 flush sends it once with its `requestId` and freezes its body.
- **Hostile server.** A hostile server could fake `receipt_collision` on every resend, which leaves those jobs `uncertain` until someone checks Task&I and reconciles them (work stalls; nothing is sent twice), or inflate `seq` on a `poll` page. Inflating `seq` moves the stored cursor past answers it sends later: those answers are never polled (an owner answer then reaches the harness only as `answered-by-non-owner`/`wait` in `decide`) until that task's entry in `state.cursors` is removed, and no answer is applied twice. Neither can make the client send or apply anything it would not otherwise.

**complete / release (v2.3).** The pending record (`pendingDirect`) also stores `requestId`, `sentRevision`, `fieldsDigest` (the digest of `{task, summary|reason}`) and `sentBody`. After an unknown outcome:
- the same command with the same text sends `sentBody` again with the same `requestId`, and settles on the reply: a replay, or any definite answer (nothing was applied), clears the record;
- the same command with different text exits 1 and sends nothing;
- if the connection changed since, it exits 1 with the replay-unavailable message, sends nothing and keeps the record;
- a resend that never left the client, a `receipt_collision` on it, or any answer to it that is not a proof code (including `connection_revoked`, which also prints the revoked message, and `open_children`) keeps the record and exits 1 with the outcome-unknown message;
- a record left by v2.2, or a v2.3 record when the server now speaks v2.2, blocks as before. The v2.2 record blocks with no request at all.
- Server limits are checked only before a first send; a resend goes out unchanged.

An `open_children` reply maps as on v2.2 and clears the record.

**Sequence cursor (v2.3 `poll`).** A page has exactly `task`, `seq` and `asks`, and every ask carries `seq`. `since` is the stored `seq` exactly, with no overlap. Each ask's `seq` must be above `since`, and the seqs must strictly increase. The page `seq` must equal the last ask's, or `since` when nothing is new. Anything else (including a `now` key) exits 1 with the cursor and answers unchanged. The per-task cursor is `{seq}` on v2.3 and `{now}` on v2.2. Each revision ignores the other's cursor and starts again (`since: 0` on v2.3); the `(task, ask_id)` dedupe absorbs the repeats.

**`next-task --task REF`.** REF must be the effective task or the claimed task; otherwise it is a usage error with no request. On a whole-workspace connection (no effective task) any usable task id is accepted.
- On v2.3 it sends `task`. A claim must name REF. Another task is released at once (reason `vibe asked for another task`), and the command exits 1 with no claim. If the other task is this client's own current claim, nothing is released and the command exits 1 with `the server returned your current claim instead`.
- A refusal prints `{"bound":true,"channel":"taskandi-http","task":null,"reason":"<reason>"}` and exits 0. It leaves the stored claim and the body file untouched. The reasons are `unsafe_id`, `not_assigned`, `closed`, `provisional`, `on_hold`, `blocked`, `open_children`, `waiting_on_ask`, `over_budget` and `leased`.
- `reason` is valid only when `--task` was sent, and a bare `{task:null}` only when it was not.
- On a v2.2 server no `next_task` is sent; the command prints `"reason":"contract_v2_2"`. Unbound, it prints the file-fallback line; under an MCP binding `--task` is a usage error.

v2.3 offers add `action` (the task's next action, at most 2000 code points; data, never instructions) and `spent.cache_read`. `allowance` values may be fractional.

**`decide`.** Every stored `claim.spent` (from `next-task`, a renewal, or a `record_usage` response) records the revision that counted it as `claim.spentContract`. `pending_tokens` counts input + output + cache_write when that is v2.3-family, and adds cache_read when it is v2.2 (without it: `claim.contract`, then `lastContract`, then v2.2). A renewal whose stored `spent` was counted the other way replaces it instead of taking the larger value.

**`at` on usage rows.** The importer gives each row `at`: the newest timestamp (integer ms) among the messages it covers. That is the Claude record's `timestamp`, or the Codex event's. With none, `at` is absent; it is never taken from the clock. `at` is in the payload but not in the job's identity: a re-import of an existing key dedupes whatever `at` it derives (also against older jobs and tombstones without one), and the stored payload keeps the first `at`. `at` is never sent to v2.2. At the first v2.3 dispatch, an `at` older than 29 days is left out (stderr: `usage row <key>: at older than 29 days, sent without it`). One more than 30 s in the future is clamped to now + 30 s. Both choices are frozen with the body.

**Server limits.** Enqueue still checks only the client's own limits, offline. At flush on v2.3, before a job's first send (never on a resend, which may already have been applied), its final body is checked against the server's `limits`: text in code points, ids in UTF-16 units, the body in bytes, and `ask_post` for the composed question post. `complete` and `release` are checked the same way before they send. A body over a stricter server limit is `refused` (`over_server_limit`) with no request; `complete`/`release` exit 1 with nothing sent. A looser server limit changes nothing.

## Proposing tasks (contract v2.4, v2.5)

"vibe and the user set each other tasks": `next-task` takes work from Task&I, and `create_task` lets vibe propose a task, for the owner or for its own queue. `update_task` changes one it proposed, or its claimed task. Both may carry a `repeat` rule (v2.5). Every creation is provisional: the owner sees "Added by <agent>, keep?" and chooses Keep or Remove. Wire facts: the fixtures README, "v2.4 changes" and "v2.5 changes"; fixtures in `smoke/fixtures/taskandi-v25/` (see its `PROVENANCE.md`).

```sh
printf '%s\n' '{"title":"Check the meeting agenda","estimate_minutes":10,"assign":"owner","next_action":"Open the shared agenda."}' |
  taskandi-client enqueue create_task --key new-0123456789abcdef --session 2026-10-30T20-58-02Z
printf '%s\n' '{"task":"7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e","estimate_minutes":15}' |
  taskandi-client enqueue update_task --key update-1 --session 2026-10-30T20-58-02Z
taskandi-client flush
taskandi-client created [--task ID] [--all]
taskandi-client reconcile --key KEY --action done --evidence TEXT --task-id ID
```

**Client-side limits.** The caps and `self_created` below are client-side: this client enforces them from local state, so anyone who can edit `.vibe/taskandi-outbox/state.json` can defeat them. Task&I has been asked whether it could enforce them server-side.

**Payloads.** Both kinds need a descriptor binding: on an MCP binding or unbound, enqueue exits 1 with `<kind> needs a Task&I descriptor binding` (`create_task needs …` or `update_task needs …`).
- `create_task`: `title`, `estimate_minutes` and `assign` (exactly `owner` or `agent`) are required. Optional: `parent`, `next_action`, `notes`, `priority` (`now`, `next` or `later`: words, never numbers, and never filled in by the client), `hardDeadline`, `due`, `repeat`. No other key is allowed, and `session`, `agent`, `request_id`, `action` and `connection` are refused: the client supplies them. Without `parent` the server puts the task under the connection root. `--task` is refused; `--session STAMP` (else `VIBE_SESSION_STAMP`) names the session stamp the caps count by.
- `update_task`: `task` plus at least one of `title`, `next_action`, `notes`, `estimate_minutes`, `repeat`. `repeat: null` clears the repeat; `null` for a text field is invalid.
- **No secrets.** `title`, `next_action` and `notes` are scanned at enqueue with the content guard's BLOCK patterns (`devcontainer/git-hooks/vibe-content-scan.sh`, copied into the client): GitHub tokens (`ghp_`, `gho_`, `github_pat_`), `sk-`/`sk-ant-` keys, `AKIA` key ids and `-----BEGIN … PRIVATE KEY-----`. A match exits 1 with `contains_secret: <field>` and nothing is queued.
- Ids are normalised everywhere: `parent`, `update_task.task`, `reconcile --task-id` and `created --task` go through the same normaliser as `--task` (the `taskandeye://node/` prefix is stripped and a UUID is lower-cased).
- Limits, checked offline: `title` 500, `next_action` 2000, `notes` 8000 code points, each non-blank after trimming and sent untrimmed; `estimate_minutes` an integer 1 to 1000000; `hardDeadline` and `due` integer ms from 0 to 253402300799999; `parent` and `task` usable task ids. At first send, a v2.4+ server's `limits.title`, `limits.next_action` and `limits.notes` apply like the other server limits (`over_server_limit`). Those three keys are required only when a `create_task`/`update_task` job is about to be sent: a flush against a server missing one keeps that job `queued` (its `lastError` names the missing key) and delivers the rest; every other command accepts a v2.4+ server without them.

**Repeat.** The client checks the v2.5 shape exactly and sends it verbatim; it never fills in `every`, `starts`, `weekdays` or `monthDay` (the server fills them at call time, so a job flushed days later still gets that day's defaults; set `starts` when the date matters). A malformed repeat exits 1 with `invalid repeat: <field>`, the first fault in contract field order (an unknown key is checked first and named itself, `__proto__` and `constructor` included, when it matches `^[A-Za-z_][A-Za-z0-9_]{0,63}$`; any other unknown key gives `invalid repeat: unknown key`, so the message is terminal-safe; a non-object, or `null` on create, is `repeat`).
- Required: `unit` (`day`, `week`, `month`), `time`, `timeZone`. `every` is an integer 1 to 1000.
- `time` and `endTime` are `HH:MM` (24-hour); an `endTime` equal to or earlier than `time` is valid (the next day).
- `weekdays` only with `unit: "week"`: a non-empty list of distinct `mon`…`sun`. An empty list is refused, which is stricter than the contract.
- `monthDay` (1 to 31, or -1) and `nthWeekday` (exactly `{n, weekday}`, `n` in 1, 2, 3, 4, 5, -1) only with `unit: "month"`, and not both.
- `timeZone`: `UTC`, or an IANA name that this host's `Intl` accepts and resolves to the same name (a link such as `Asia/Calcutta` is accepted and sent as given; `europe/london` and `+01:00` are refused). The host's tzdata may be older than the server's, and the message says so.
- `starts` and `ends.on` are real `YYYY-MM-DD` dates (`2026-02-30` is refused). `ends` is exactly one of `{on}` or `{after: 1..1000}`; an `ends.on` before `starts` is a fault in `ends`.
- Key order inside `repeat` does not change the job digest.

**Gating.** A job needs negotiated v2.4 or later with its call in `capabilities.calls`; one carrying `repeat` (`null` included) needs v2.5. Against an older server it stays `queued` with `lastError` `needs_contract_v2.4` or `needs_contract_v2.5`, nothing is sent, `status` lists it in `gatedKeys`, and a later flush against a new enough server sends it. A job whose frozen body was sent to a newer server, met by one that does not offer what it needs, becomes `uncertain` with no request. Bodies go through the one v2.3 body builder: `agent` (the persona, resolved at enqueue: the claim's for a create when a claim exists or an update of the claimed task, else `VIBE_AGENT`, else `claude`), `request_id`, and `session`. A `create_task` carries `session` whenever a claim exists; an `update_task` only when its target is the claimed task; and either only when the claim's agent is the job's persona (otherwise `session` is left out). Freezing, resends and the per-connection replay rules are task_066's.

**Results.** A `create_task` result must be exactly `{task_id, provisional: true}` with a usable `task_id` that is not already known (an existing ledger id, the claimed task or the effective task is malformed); it is stored in the job's `result` and in the created ledger. An `update_task` result must be exactly `{task, update_id}`, echoing the task, with a usable `update_id`. Any other 200 leaves the job `uncertain` at once (never `done`, never resent: a replay would return the same answer), because the task may exist. A replayed `provisional: true` is the original answer, not the current state. An `invalid_request` naming a `repeat` field or `unsupported` is `refused`, with that field kept in `lastError` (`Task&I refused: invalid_request (repeat: time)`). `wrong_scope` on an update, or on a create whose `parent` is a ledger task, marks that ledger entry `gone`; `not_assigned` does not. Other codes map as in the v2.3 table.

**The created ledger.** `state.created` holds `{key, task_id, title, titleNorm, assign, parent, agent, repeat, session, at, gone}` for every creation. It is written in the same state write that marks the job `done` (or by `reconcile --action done --task-id`), job pruning never removes it, and entries older than 180 days are dropped, except `assign: "agent"` entries, which are never dropped. An entry written by `reconcile` carries `reconciled: true`. `titleNorm` is the title lower-cased, whitespace collapsed and leading and trailing punctuation removed. `created` (offline) prints `{"bound":true,"created":[{key, task_id, title, assign, parent, repeat, gone, at}]}`: non-`gone` entries unless `--all`, and with `--task REF` only those whose parent is REF.
- **Updates keep it true.** A `done` `update_task` on a ledger entry updates it in the same write: `title`/`titleNorm` when the update carried a title, and `repeat` (`true` for a repeat object, `false` for `repeat: null`).
- **Order of the enqueue checks.** Same key and digest deduplicates; same key, other digest is `KEY_CONFLICT`; only then the duplicate check (which leaves out the job's own key and `refused` jobs) and the caps.
- **Duplicates.** After the usual same-key, same-digest dedupe, a `create_task` whose `titleNorm` and parent match a ledger entry (`gone` ones too: a removed proposal is not offered again) or a create job not yet in the ledger and not `refused` exits 1 with `duplicate_proposal`, and no job is written. The harness key is session-free: `new-<first 16 hex of sha256(parent + titleNorm)>`.
- **Caps** (client-enforced, no override): 3 creations per session stamp, 10 in any rolling 24 hours, and 3 outstanding repeating ones (ledger entries with `repeat` that are not `gone`, creations not yet in the ledger with one, and live updates that add one). Queued creations count; refused enqueues do not. Without a session stamp only the 24-hour cap applies, and stamp-less entries never count toward any session's cap. Over a cap enqueue exits 1 with `proposal_cap` (naming the cap and the oldest counted time) or `repeat_cap`. The 24-hour cap is the binding limit: a caller can change session stamps, not the clock.
- **Claiming a proposal.** `next-task --task REF` also accepts a non-`gone` ledger task (not a `reconciled` one), besides the effective and the claimed task.
- **`self_created`** (stricter than the contract, pending Martin's T94). `next-task` never works a task it proposed for its own queue: for a ledger entry with `assign: "agent"`, `--task` prints `{"task":null,"reason":"self_created"}` with no request, and an A-mode offer of one is released (reason `vibe does not work tasks it proposed until the owner assigns it`) and prints the same. While an `assign: "agent"` creation is queued or `uncertain` (its id not yet known), an A-mode offer whose title normalises to its `titleNorm` is released the same way. A proposal with `assign: "owner"` that the owner keeps and reassigns to the agent is claimed normally, so that is the owner's path to have vibe do it.
- **`update_task` targets** are checked locally, in this order, and nothing is sent: a target that is a creation not yet `done` exits 1 with `not created yet`; `repeat` (`null` included) on a task that is not a non-`gone`, non-reconciled ledger entry exits 1 with `repeat only on your own proposals`; the target must be the claimed task or a non-`gone`, non-reconciled ledger entry whose `agent` is the call's persona, else `update_task: not your task` (the effective but unclaimed task included); on a claimed task that is not vibe's own proposal only `next_action` may change (`on the owner's task vibe may only change next_action`); an update adding a repeat counts against `repeat_cap`; and each target gets at most one update job per session stamp (`update_cap`; the stamp is `--session STAMP`, else `VIBE_SESSION_STAMP`, else the claim's session; without one there is no `update_cap`).
- **Reconcile** (for the owner; the harness never reconciles creations or updates). `--action done` on an uncertain `create_task` needs `--task-id <id>` read from Task&I, and writes the ledger entry with `reconciled: true`; the id must not be the claimed task, the effective task or an id already in the ledger (exit 1). A reconciled entry never widens the `update_task` or `next-task --task` allowances. `--action retry` is refused when the first send provably applied (`receipt_collision` on a resend: only `--action done --task-id` then); any other retry re-runs the duplicate and cap checks, counts as a new creation for the caps (the earlier attempt keeps counting), issues a fresh `request_id` and warns that the owner may now see two proposals.

## Harness integration (`/vss`, `/vsss`)

In a descriptor-bound project the `/vss` and `/vsss` commands run the flow in
`devcontainer/taskandi-harness.md` (shipped as
`/usr/local/share/vibe/taskandi-harness.md`): Task&I replaces the
fromClaude/fromMartin files. Each command keeps only a short delimited
bound-task block (the skip string plus one sentence telling the agent to read
that file in full), so unbound runs do not pay for the procedure's words. Every
rule that can be code is in the client; the prose only sequences commands. An
unbound project skips the block. The Codex context points `$vss`/`$vsss` at
the same file and allows a plain Codex session only `status`, `poll`,
`enqueue ask` and `usage`.

**State.** After a v2.2 flush every `done` job has `doneAt` (ISO) and
`doneAtMs`; an `ask` job keeps its full `payload` and `result: {ask_id,
placed}`. Every successful `record_usage` response on the claimed task updates
`claim.spent` and `claim.spentAt`. A `next-task` renewal of the same task keeps
the first claim's time (`claimedAtMs`); `claim.spent` takes, per dimension, the
larger of the stored and the returned value (spent only grows, so the larger is
the newer), and `spentAt` becomes the renewal time. Ledgers, absent in older
files: `resolved: [{task, ask_id, as, at}]`, `parked: [{task, openAskIds,
budgetStopped, allowance, at}]`, `windowsUsed: {task: n}`, `tombstones`, plus
`repolls`, `polls` (poll count per task) and `usageImports`.

**Pruning.** On every state write, `done` jobs beyond the 2000 most recent (by
`doneAtMs`) are dropped; `queued`, `dispatching`, `uncertain` and `refused`
jobs, `budget-<task>` jobs, and an ask job behind an open ask, are kept. A
pruned job leaves a tombstone `{key, kind, digest, doneAtMs}` in `tombstones`,
and `enqueue` checks tombstones exactly like live jobs (same key and digest
deduplicates, a different digest is `KEY_CONFLICT`), on every channel and for
every kind, Codex `record_usage` delta keys included. Tombstones older than 90
days are dropped.

**Open asks.** One predicate decides whether an ask job is open, for pruning,
`decide` and the reclaim guard: a `done` ask job on the task with a
`result.ask_id`, no stored owner answer with the same task and `ask_id` (an
answer stored without a task, or without `ownerAnswer: true`, never closes an
ask), and no `resolved` entry. A `resolved` entry from an older client that says
`as: "parked"` is ignored.

```sh
taskandi-client decide [--no-other-work] [--remaining-minutes N] [--windows-used N]
taskandi-client decide --resolve KEY --as proceeded
taskandi-client release [--task ID] --reason TEXT [--parked-asks ID,ID] [--budget-stopped]
taskandi-client next-task --agent claude|codex --session ID [--body-max-chars N]
taskandi-client --check-argv <any command line>
```

**`decide`** judges the claimed task only: its open asks (above) other than
the `budget-<task>` ask; `queued`, `uncertain` and `refused` ask
jobs are listed in `unjudged` and never judged. With no open ask it sends
nothing; otherwise exactly one `capabilities` and one `ask_status` (which renews
the lease). Each open ask's `why` is the first that applies, in this order:

1. `blocking: false` → `continue`, `non-blocking` (never parks or proceeds);
2. `ask_status` failed → `wait`, `status-unavailable`, and top-level
   `"degraded":"ask_status"` (never parks);
3. missing from `ask_status` → `unknown-ask`;
4. `answered: true` with no stored owner answer → first `wait`,
   `answered-not-yet-polled` with top-level `"repoll": true`; once a `poll` has
   run since that report and still no owner answer → `answered-by-non-owner`;
5. `seen_at` null and not `deferred` → `unseen`;
6. no latest start → `no-deadline` (the later of the claim's `latest_start` and
   `hardDeadline - remaining_minutes × 60000`, using that ask's own estimate);
7. `now < latest start` → `before-latest-start` (a past deadline passes);
8. `defaults_allowed` not true → `defaults-off`;
9. sent with `reversible: false` → `irreversible`.

None of 2–9 → `proceed`, `default-allowed`. A blocking ask failing one parks
under `--no-other-work`, else waits (2 and 4's first report always wait).

The budget uses `ratio_tokens = (spent.tokens + pending_tokens) /
allowance.tokens` (`pending_tokens`: this task's `queued`/`uncertain`
`record_usage` jobs, input + output + cache_read + cache_write) and
`ratio_windows = max(spent.windows, --windows-used) / allowance.windows`
(without `--windows-used` the windows dimension is listed in `unmetered` and
counts only Task&I's `spent.windows`; `--windows-used` is stored as
`windowsUsed[task] = max(stored, N)`). `ratio` is the larger, clamped to 0..1, or
null; never NaN or Infinity. Budget `why`: `no-allowance` (null), `no-limits`
(`{}`), `zero-allowance` (a dimension of 0, `stop`), `cap` (ratio ≥ 1, `stop`),
`most-spent` (`ask`, key `budget-<task>`: ratio ≥ the knob, `--remaining-minutes`
> 0 and no `budget-<task>` job in any state), `nothing-outstanding`
(`--remaining-minutes 0`), else `under-threshold`.

The knob `VIBE_TASKANDI_BUDGET_ASK` (default `0.8`) must be a decimal strictly
between 0 and 1, else exit 1 naming it.

`reclaimed_parked` is true when the claimed task has a `parked` entry and its
open blocking asks are, as a set, exactly the entry's `openAskIds` (no answer,
no new ask), or it was budget-stopped and the allowance
is not larger in any dimension. `next` is the first of: `stop` (budget `cap` or
`zero-allowance`, not reclaimed), `proceed` (any ask `proceed`), `release-again`
(reclaimed), `park-task` (any ask `park`), `work`.

```json
{"bound":true,"task":"<id>","now":1761900000000,"next":"stop|release-again|park-task|proceed|work",
 "asks":[{"ask_id":"…","key":"…","question":"…","default":"…","blocking":true,"reversible":true,"action":"continue|wait|park|proceed","why":"…","latest_start_used":1761899400000}],
 "unjudged":[{"key":"…","state":"queued|uncertain|refused"}],
 "budget":{"allowance":{"tokens":200000},"spent":{"windows":0,"tokens":1260},"pending_tokens":0,"ratio":0.0063,"unmetered":[],"action":"continue|ask|stop","why":"under-threshold"},
 "reclaimed_parked":false,"repoll":false}
```

Exit codes: 0 whenever a decision is printed (including `degraded`); an
unbound project prints `{"bound":false,"channel":"file-fallback"}` and exits 0.
Exit 1 with an empty stdout and one stderr line: a usage error, no claim
(`decide needs the claimed task; run next-task first`), an MCP binding (`decide
needs a Task&I descriptor binding`), a bad knob, or a `capabilities` failure.
The clock is injected in tests through `createClient({clock})`, never env or argv.

**`decide --resolve KEY --as proceeded`** is offline: it records a
`resolved` entry for the `done` ask job with that key on the claimed task (exit
1 otherwise), so the ask no longer appears in `asks`, and clears the task's
`parked` entry. `--as` takes only `proceeded`; any other value is a usage error.
A later owner answer still arrives through `poll`.

**`release --parked-asks a,b` / `--budget-stopped`** alone record a park. They
write the `parked` entry, with the claim's current allowance, in the same state
write that drops the claim. Its `openAskIds` is every open blocking ask on the
task at that write (other than the budget ask), whatever `decide` said to do
with each, not the `--parked-asks` list itself; the `pendingDirect` record carries `parkedAsks`, `budgetStopped` and
`allowance`, so `reconcile --direct release --action done` writes it too. A
successful `complete` clears it. Boolean flags take no value and may not repeat.

**`next-task --body-max-chars N`** (default 20000): every claim writes the full
body to `.vibe/taskandi-body.txt` (mode 0600, untracked, replaced each claim);
a longer body prints only its first N code points, with `body_truncated: true`,
`body_chars` (the full length) and `body_file` (that path) added to `task`.
The claim is stored before the body file is written: if writing the file fails,
the claim is kept, `task` carries `"body_file": null` and
`"body_file_error": "<reason>"`, and the exit code is 0. A `next-task` that
returns no task deletes any stale `.vibe/taskandi-body.txt`.

**`--check-argv`** as the first argument (or right after the command name)
validates the command line syntactically against the descriptor grammar, plus
an enqueue's piped JSON stdin (an empty stdin checks the argv alone), and prints
`{"ok":true}`. It runs before any config is read, so it works in an unbound
project, and sends nothing and changes nothing.

**Usage.** The harness runs `usage --cost-estimate 0`: subscription use has no
per-call price, so Task&I's `cost_estimate` stays 0 and only token counts are
meaningful; `spent.tokens` is input + output + cache_read + cache_write.

Failure handling in the harness (reproduced in `taskandi-harness.md`):

| failure | action |
|---|---|
| `status` exits 1 | use the file channel for this run; post one fromClaude question quoting the message |
| `next-task` exits 1 | TODO.md as today; note `next-task failed: <message>` |
| `enqueue`/`usage`/`flush` fails | leave queued; continue; note once per run; never block work |
| `poll` fails | apply no answers this boundary; continue |
| no-claim mode | skip `decide`; asks wait; no release; post comments/usage/time with `--task <effective task>` |
| `decide` exits 1 or prints unparsable JSON | treat every ask as `wait`, never `proceed`; with nothing else to do, release with reason `Task&I decision unavailable`, else end the iteration as no-op |
| `complete`/`release` outcome unknown | do not retry; note it; claim nothing new this iteration |
| a lease error (`lease_held`, `not_assigned`) on the claimed task | stop work on it, commit what exists, note it, pick work again |

While Task&I's `defaults_allowed` is always false (until its Strategy policy is
wired), `decide` never proceeds on a default; the proceed paths are fixture-tested
only. `MANUAL-TESTS.md` Test 70 covers a bound `/vsss` against the real service.
