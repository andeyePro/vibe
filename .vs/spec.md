# task_064 — Task&I client: align to the built service (contract v2.2, HTTP transport) — 2026-10-31 (rev 5, consolidated)

## Task summary

task_061 built the v2.1 client against MCP-shaped fixtures. Task&I has since built its side (taskandeye branch `claude/exchange-20261030` at 62e50fa5), and it differs: plain `POST <origin>/api/browser-agent`, not MCP; opaque task ids; ms-since-epoch timestamps; HTTP 409 `{"error": code}` refusals; and v2.2 adds `ask_status` and `defaults_allowed`. Authority, in order: `/brain2/andeye/Task&I-agent-exchange-fixtures/README.md` section "Wire details (answers for the vibe client, 2026-10-31)" (read from Task&I's code), then the ten fixture files there, then this spec. This task adds a descriptor-selected HTTP transport to `devcontainer/taskandi-client.mjs` (and `taskandi-usage.mjs`). The MCP v1 and v2.1 paths stay exactly as they are. The outbox, file fallback, task targeting, owner-only answers and claim handling carry over, with the changes below.

## Definitions

- **Usable task id** (what vibe works on): `^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`. The wire accepts any 1–200 UTF-16 code-unit string, but agents paste ids into shell commands, so vibe refuses anything else. Server-issued ids (UUIDs and the fixtures' `project`/`leaf-b`) are compared exactly. A user-typed `--task` that is UUID-shaped is lower-cased once at parse time; nothing else is case-folded.
- **Task ref under a descriptor binding**: a usable task id, or `taskandeye://node/<usable id>` (sent as the bare id). `ABBR-N` refs are a usage error under a descriptor binding: `Task&I descriptor bindings take task ids, not ABBR-N references` (exit 1, no request). Under MCP bindings, refs are unchanged.
- **ms timestamp**: a nonnegative safe integer.
- **Text**: well-formed (no lone surrogates), not whitespace-only, length counted in code points (`[...s].length`). **Id fields** (`model`, `source`, `source_ref`, `account`, `session`, `in_reply_to`, task ids): 1–200 UTF-16 code units.
- **Descriptor binding**: the project has `.vibe/taskandi-descriptor.json`. **MCP binding**: the project has `.vibe/taskandi.json` (unchanged).

## Descriptor

- `.vibe/taskandi-descriptor.json`: same file rules as `.vibe/taskandi.json` (regular file, single link, not a symlink, owned by the user, `.vibe` not a symlink, untracked case-insensitively, ≤ 32 KiB), plus no group/other mode bits (message includes `chmod 600 .vibe/taskandi-descriptor.json`).
- Exactly the keys `protocol` (= `taskandeye-browser-agent-v1`), `origin`, `connection` and `workspace` (each 1–200 chars of `^[A-Za-z0-9][A-Za-z0-9._:@/-]*$`), `root` (a usable task id or `null`), `token` (exactly 43 chars of `[A-Za-z0-9_-]`).
- `origin`: `new URL(origin).origin === origin`, and either `https:` (any host) or exactly `http://127.0.0.1:<port>` with port 1–65535 and no leading zero. Nothing else is accepted (`localhost`, `[::1]`, other http hosts, paths, userinfo, a trailing slash).
- Both `.vibe/taskandi.json` and the descriptor present → refuse `two Task&I bindings; keep one`. A descriptor that is present but invalid → refuse; never fall back to the other file or to unbound.
- **Effective task**: `VIBE_TASK_REF` > `.vibe/taskandi-task` > `root`. With `root: null` and no override, the effective task is `null`.
- **Binding digest** (fingerprint, job binding, answer binding): `digest({kind: 'descriptor-http', workspace, task: <effective task or null>, contractRevision: 'vibe-agent-exchange-v2.2'})`. It excludes `token`, `connection` and `origin`, so a reconnect (new token and connection, possibly a new port) keeps queued jobs, stored answers and a pinned supervisor fingerprint valid. Changing `workspace` or the effective task gives `BINDING_CHANGED`, `answer binding changed` or `pinned task binding changed` as today. MCP and descriptor digests never match (different `kind`). `bindingFingerprint` keeps its signature, so `codex-supervisor.mjs` needs no change.

## Transport

- New `httpTransport` on `node:http` (`node:https` for https origins). Never `fetch` (it cannot set `Host`).
- **Container mode** is on when `VIBE_CONTAINER=1`, or when `/.dockerenv` exists and `VIBE_CONTAINER` is not `0`. In container mode an `http://127.0.0.1:<P>` origin is reached with `http.request({host: 'host.docker.internal', port: P, family: 4, agent: false, setHost: false, path: '/api/browser-agent', method: 'POST', headers: {host: '127.0.0.1:<P>', 'content-type': 'application/json', authorization: 'Bearer <token>', 'content-length': <n>, connection: 'close'}})`. `family: 4` is required because vibe's firewall allows only the IPv4 host gateway. The service refuses any other Host with 421 `wrong_origin` (taskandeye session, 2026-10-31, verified against the live service). Outside container mode it connects to `127.0.0.1:<P>`, and `Host` defaults to the same value. https origins use the default `Host` and normal TLS verification, never rewritten.
- The token is sent only to the descriptor host or, for `http://127.0.0.1:<P>` in container mode, to `host.docker.internal:<P>`. The connect target never comes from env or argv. Test seam: `createClient({cwd, httpConnect: {host, port, timeoutMs?}})`, used only by tests.
- Only those headers are sent: no `origin`, `cookie`, `referer`, `user-agent`, `accept*` or `sec-fetch-*` (a cookie or a mismatched Origin gets 403 `connection_scope`, per the taskandeye session).
- 3xx refused; 15 s timeout (socket timeout plus a hard timer); response cap 16 MiB (a `content-length` above the cap is refused before reading; the stream is counted and destroyed past it). MCP keeps its 1 MiB and 30 s.
- A connect failure to `host.docker.internal` names both the rewrite and the port in the error.

## Requests

Every body has `action` and `connection`. A payload or argv can never supply `action`, `connection`, `agent` or `session`; they are refused at enqueue or parse. Recorded body keys must equal this table exactly:

| call | body keys besides action, connection |
|---|---|
| `capabilities` | none |
| `next_task` | `agent`, `session` (no `task`) |
| `ask` | `task`, `question`, `default`, `options`?, `order`, `estimate_minutes`, `remaining_minutes`, `reversible`, `blocking`, `in_reply_to`?, `agent`, `session`? |
| `comment` | `task`, `text`, `agent`, `session`? |
| `list_asks` | `task`, `since`, `session`? |
| `ask_status` | `task`, `session`? |
| `record_usage` | `task`, `model`, `input`, `output`, `cache_read`, `cache_write`, `cost_estimate`, `windows` (always 0), `account`, `source` (`vibe`), `source_ref` (the enqueue key), `session`? |
| `record_time` | `task`, `seconds`, `started_at` (ms), `session`? |
| `complete` | `task`, `summary`, `session` |
| `release` | `task`, `reason`, `session` |

- **agent** (`claude`|`codex`). For `next-task`, it comes from `--agent` (required, as today). For enqueued `ask` and `comment` it is resolved at enqueue, in this order: the claim's agent when the job's task is the claimed task; else `VIBE_AGENT` when it is `claude`/`codex`; else `claude`. It is stored on the job outside `payload` and outside the dedup digest, so the same key and payload with a different resolved agent still deduplicates.
- **session**. For `next-task`, from `--session` (required; 1–200 chars of `^[A-Za-z0-9][A-Za-z0-9._:@/-]*$`). For other calls it is resolved at dispatch: the claim's session when the call's task is the claimed task, else omitted. The stored lease is as `next_task` returned it; the client never judges its expiry.
- **Limits, checked before anything is queued or sent** (usage error, exit 1, zero requests):
  - `question` ≤ 8000 code points, `default` ≤ 2000, `options` ≤ 20 entries of ≤ 500 each.
  - The composed thread post `[...("Question: " + question + "\nDefault: " + default + (options.length ? "\nOptions: " + options.join(" / ") : ""))].length` ≤ 8000, because placement cannot be predicted.
  - `comment.text` ≤ 8000; `complete.summary` ≤ 7950; `release.reason` ≤ 2000.
  - Id fields 1–200 code units; no whitespace-only or ill-formed text.
  - `record_time`: `seconds` 1–604800 (0 is refused). `started_at` is converted from the input's ISO UTC timestamp to ms, keeping fractional ms; `…Z` and `….000Z` give the same payload and dedupe. `started_at + seconds*1000 <= now` is checked at enqueue, with no slack.
  - `record_usage`: `account` and `cost_estimate` stay required in the client (stricter than the wire).
- **Body cap**: the serialized JSON body (UTF-8 bytes) must be ≤ 65536. Enqueue checks it with worst-case 200-character `connection`, `session` and `agent` values. Flush checks the final body again; a job that overflows there becomes `refused` with code `body_too_large`, and no request is sent.

## Responses

Validated with exact keys. Every task-bearing response must echo the requested task exactly.

- `capabilities` → `{protocol, contract, grade, calls}`. `protocol` must equal the descriptor's, `contract` must be `vibe-agent-exchange-v2.2`, and `calls` must include every call about to be made (for `flush`, every queued kind). `grade` is stored in `state.json` as `lastGrade` but not gated on.
- `next_task` → `{"task": null}` (no other key), or an object whose keys are always present:
  - `task`: a usable task id, else exit 1 with `task id not usable by vibe: rename it in Task&I or recreate the task`, no claim stored, empty stdout; the lease lapses in 90 minutes.
  - `title`: string; `body`: string, may be empty (no client cap beyond the 16 MiB response limit, so a lease is never taken for a task vibe then refuses).
  - `priority`, `effective_priority`: integer or null.
  - `allowance`: null, or an object with optional nonnegative-integer `windows`/`tokens`; `{}` is valid, a null inside it is refused.
  - `spent`: `{windows, tokens}`.
  - `owner`: string.
  - `lease`: `{until: ms, session}`.
  - `defaults_allowed`: boolean.
  - Optional keys: `hardDeadline` (ms; absent when none, never null), `estimate_minutes` (count), and `latest_start` (ms; not sent today, accepted for v2.3).
- `ask` → `{ask_id, placed: 'subtask'|'thread'}`.
- `list_asks` → `{task, now, asks}`, with `now` an ms value ≥ the request's `since`. Each ask has exactly these keys, all present:
  - `ask_id`, `task` (= requested), `question`, `default`.
  - `subtask_id`: string when `placed` is `subtask`, null when it is `thread`.
  - `placed`.
  - `options`: always an array of strings.
  - `order`, `estimate_minutes`, `remaining_minutes`: counts.
  - `reversible`, `blocking`: booleans.
  - `in_reply_to`: string or null.
  - `agent`: `claude`|`codex`.
  - `created_at`: ms.
  - `seen_at`, `answered_at`: ms, non-null.
  - `answer`: string ≤ 8000 code points, non-null.
  - `answered_by`: string, non-null; stored but never printed or compared.
  - `owner_answer`: boolean.
  - There is no `deferred` key, and no `ask_id` repeats within a page.
- `ask_status` → `{task, asks: [{ask_id, seen_at: ms|null, deferred: boolean, answered: boolean}]}`.
- `comment` → `{task, comment_id}`.
- `record_usage` → `{task, spent: {windows, tokens}}`.
- `record_time` → `{entry_id, task, start, end, actor: 'agent'}`.
- `complete` → `{task, state: 'provisional', completion_id}`.
- `release` → `{task, released: true, comment_id}`.

All validation rules for `next_task` and `list_asks` live in one schema constant, and all error classes live in one table constant.

## Cursors

- Cursors are per task: `state.cursors[<task id>] = {now}`, for descriptor bindings only. The v1/v2.1 `state.cursor` is untouched; the two never mix because their answer bindings differ.
- Target selection follows "Target resolution" below.
- The first poll of a task sends `since: 0`. Later polls send `since = max(0, stored now - 2000)`, because `now` is wall-clock and same-millisecond answers can otherwise be skipped.
- Stored answers (owner and non-owner alike) are keyed by `(task, ask_id)`. A repeated `(task, ask_id)` with the same `answer` counts as neither new, ignored nor a conflict; a different `answer` is a conflict as today. The stored set is unbounded, like today's answers list.

## Target resolution

For every command that needs a task:
1. Use `--task` if given, else the claimed task, else the effective task. If none, exit 1 with `no bound task: the connection covers the whole workspace; claim one with next-task` (empty stdout, no request).
2. For `complete`/`release`, if the resolved target is not the claimed task, exit 1 with `complete/release needs the session that claimed the task; run next-task first`. This includes `complete --task X` under `root: null`.
3. `--task` acceptance: when the effective task is non-null, only the claimed task or the effective task is accepted. Under `root: null`, any usable id is accepted for `poll`, `ask-status` and `enqueue` (the token bounds it server-side).

## Printed output

stdout is JSON, and slice 4 parses it.

| command | stdout |
|---|---|
| `next-task` | `{"bound":true,"channel":"taskandi-http","task":null}` or `…"task":{<validated object, ms numbers kept>}}` |
| `poll` | `{"bound":true,"channel":"taskandi-http","task":T,"newAnswers":n,"answers":[{"ask_id","answer","seen_at","answered_at"}],"ignored":m,"conflicts":[ids],"cursor":{"now":N}}`; `answers` holds owner answers only |
| `ask-status` | `{"bound":true,"channel":"taskandi-http","task":T,"asks":[…]}` |
| `complete` | `{"bound":true,"completed":true,"state":"provisional","completion_id":…}`, or `{"bound":true,"completed":false,"open_children":[{"task","title"}]}` (exit 0, claim kept) |
| `release` | `{"bound":true,"released":true,"comment_id":…}` |
| `flush` | the v2.1 shape plus `"refused":n` and `"requeued":n` |
| `status` | as today, plus `"channel":"taskandi-http"`, `counts.refused`, `refusedKeys` `[{key, code}]`, `claimedTask` and `lastGrade`. It sends no request and never shows the token, connection, origin or workspace |

For `capabilities`, `ask`, `comment`, `record_usage` and `record_time` there is no stdout of their own; tests check the recorded request, `flush` counts and the stored job result.

## Errors and job states

Only exactly-formed bodies are interpreted: a 409 `{"error": code}` (plus `children`, 1–200 `{task, title}`, for `open_children`), a 400 `{"error":"invalid_request"}`, a 421 `{"error":"wrong_origin"}` or a 403 `{"error":"connection_scope"}`. Any of those statuses with another body counts as an unrecognised response (outcome unknown). A code is printed only if it matches `^[a-z][a-z_]{0,63}$`; otherwise `unknown_error` is printed. Titles and other server strings never reach stderr.

| class | codes and conditions | outbox job | direct command |
|---|---|---|---|
| outcome unknown | `connection_unavailable`; `connection_revoked`; any code not listed in this table (including the owner-only `connection_changed`, `descriptor_origin_changed`, `ask_answered`); a status other than 200/400/403/409/421; a malformed or non-JSON body; timeout or socket loss after sending | `uncertain`; flush stops | exit 1, state unchanged; `complete`/`release` also print `taskandi-client: outcome unknown; check the task in Task&I: …` and keep the claim |
| not applied, try later | `stale_context`, `sync_required`, `lease_held`, 421 `wrong_origin`, 403 `connection_scope` | back to `queued` with `lastError`; flush stops | exit 1, `taskandi-client: Task&I refused for now: <code>`, state unchanged |
| not applied, rejected | `use_native_connection`, `scope_missing`, `invalid_request` (409, or 400 with exactly that body), `wrong_scope`, `wrong_thread`, `unknown_ask`, `not_assigned`, `receipt_collision`; local `body_too_large` | `refused` with the code; flush continues | exit 1, `taskandi-client: Task&I refused: <code>`, state unchanged |

- `connection_revoked` first prints exactly `taskandi-client: the Task&I connection was revoked or replaced; copy a fresh descriptor (More → Connect Codex) into .vibe/taskandi-descriptor.json`. It can follow a write that already committed, so it is outcome unknown; for `complete`/`release` the outcome-unknown line follows.
- `open_children` on `complete` gives the exit-0 output above.
- **No v2.2 write is idempotent.** A retried `ask`, `comment`, `record_usage`, `record_time` or `release` creates a duplicate. `complete` returns the existing completion only while that completion is unresolved. So `uncertain` jobs are never retried automatically. The docs tell the user to check with `ask-status`/`poll` (for asks) or in Task&I before `reconcile --action retry`.
- `refused` is a new terminal job state: `status` counts it, `reconcile --action retry --evidence …` requeues it, and `--action done` on it exits 1. MCP paths never produce or accept `refused`.
- `request_id` is not sent. A later task adds it once `capabilities.contract` is `vibe-agent-exchange-v2.3`.

## root: null

When there is no effective task:
- `next-task` and `status` work.
- `poll`, `ask-status`, `enqueue`, `complete` and `release` work on the claimed task or on an explicit `--task`, per Target resolution.
- Anything else that needs a task gives the no-bound-task message.

## Acceptance criteria

**Fixtures.** The ten files are copied byte for byte into `smoke/fixtures/taskandi-v22/`, with a `PROVENANCE.md` giving the source path, taskandeye commit 62e50fa5 and the date. Wire tests use a real loopback `http.createServer`, reached through the `httpConnect` seam, that records `req.method`, `req.url`, `req.rawHeaders` and the body, and serves each fixture's `response` or an error.

- **AC1 Descriptor.** Each of these exits 1 with a message naming the rule and makes zero requests:
  - wrong `protocol`; a missing key; an extra key;
  - `token` of 42 or 44 chars, or containing `+`;
  - `origin` with a trailing slash, a path, a query, a fragment or userinfo; `http://localhost:1`, `http://[::1]:1`, `http://10.0.0.1:1`, `http://127.0.0.1` (no port), port 0, 65536 or `01234`;
  - `connection` or `workspace` empty or 201 chars;
  - `root` of `""` or `a b`;
  - mode 0644 (message contains `chmod 600`); nlink 2; a symlink; tracked by git; tracked as `.VIBE/TASKANDI-DESCRIPTOR.JSON` under a case-insensitive check; over 32 KiB; `.vibe` a symlink;
  - both binding files present (`two Task&I bindings; keep one`).
  
  Positive controls: a valid descriptor loads with `task` = `root`, and `root: null` loads with `task: null`.
- **AC2 Wire per fixture.** (The `record_usage` test enqueues with key `session-a`, so `source_ref` matches the fixture.) For each of the ten fixtures:
  - The recorded request body's sorted key set equals the table's set, and its values equal the fixture `request`, after substituting the client's agent and session and adding `connection`.
  - For commands with stdout, stdout deep-equals the printed-output table derived from the fixture `response`; for the others, see Printed output.
  - Specifically: `next_task` has no `task`; `complete` has no `agent`; `comment` has `agent:"claude"` when the client's agent is claude.
- **AC3 Host and headers.**
  - With container mode on and origin `http://127.0.0.1:<P>`, and the listener on another port reached via the seam: `req.headers.host === '127.0.0.1:<P>'`, and the raw header names are exactly {host, content-type, authorization, content-length, connection}.
  - With container mode off, Host is `127.0.0.1:<listener port>` by default and the seam is unused.
  - Served in answer to `next-task`'s `capabilities` call: a 421 `wrong_origin`, a 403 `connection_scope` and a 302 each produce exactly one request (counted), exit 1, and a stderr line naming the code (`redirect` for the 302).
  - A source check asserts that the v2.2 transport path does not call `fetch(` and reads no connect host from `process.env`.
- **AC4 Errors.** For every code and condition in the three error-table rows (including the 400 `invalid_request` body, a 400 with another body, and local `body_too_large`), a flush of one queued job ends in the table's job state. It also checks:
  - that flush stops or continues as stated;
  - the exit code and stderr;
  - that the claim and cursors in `state.json` are unchanged.
  
  Further cases:
  - `connection_revoked` on a job prints the exact message and the loopback server's request counter shows no retry.
  - Direct `complete` with `connection_revoked` prints the revoked line, then the outcome-unknown line, and keeps the claim.
  - A 409 with `{"error":"x\u001b[2J"}` prints `unknown_error`.
  - A 200 with an extra key gives `uncertain`, and so does a non-JSON 500.
  - `reconcile --action retry` requeues a `refused` job; `--action done` on it exits 1.
  - `status` lists `refusedKeys`.
- **AC5 Capabilities gate.** A `flush` with nothing queued sends no request. Every other networked invocation sends exactly one `capabilities` request first. Each of these makes it exit 1, leaves jobs `queued` and sends no further request:
  - `contract` of `"vibe-agent-exchange-v2.1"`;
  - `calls` missing the needed call (per call; for `flush`, per queued kind);
  - a different `protocol`;
  - an extra or missing key.
  
  `status`, `reconcile` and unbound projects send nothing. `lastGrade` is stored after a successful capabilities call.
- **AC5b Transport limits.** A streaming loopback server checks that:
  - a `content-length` of 16 MiB + 1 is refused before the body is read;
  - a body growing past 16 MiB without a length is cut off (connection destroyed, exit 1);
  - a 1.5 MiB valid body is accepted;
  - a silent server is abandoned after the timeout (`httpConnect.timeoutMs` = 500 in the test).
- **AC6 Task ids.**
  - `--task leaf-b`, `--task project` and a mixed-case UUID are accepted; the UUID is sent lower-cased.
  - `--task ABBR-12` exits 1 with the ABBR message and zero requests.
  - `taskandeye://node/<id>` is sent as `<id>`.
  - A response echoing a different task is refused (`uncertain` for jobs, exit 1 for direct calls).
- **AC7 Binding digest.**
  - A descriptor rewritten with a new `token`, `connection` and port (same `workspace` and `root`) leaves `bindingFingerprint` unchanged; queued jobs flush and poll succeeds.
  - A different `workspace`, or a different effective task, makes flush fail `BINDING_CHANGED` and poll fail `answer binding changed`; `VIBE_TASK_BINDING=<old fingerprint>` then fails `pinned task binding changed`.
  - `import('codex-supervisor.mjs')` still succeeds.
- **AC8 Cursors.**
  - Poll A (a fixture answer, `now: T1`), then claim B: poll B sends `since: 0`.
  - Polling A again sends `since: T1 - 2000` and returns the same answer, which is counted in neither `newAnswers` nor `ignored` nor `conflicts`. The same `ask_id` with a different `answer` is a conflict.
  - A response with `now < since` is refused, with cursor and answers unchanged.
- **AC9 next_task shape.**
  - Accepted and stored as the claim: `allowance: null`; `allowance: {}`; `priority: null`; `effective_priority: null`; no `hardDeadline`; `latest_start` present; `defaults_allowed: true` (printed `true`).
  - Refused, with exit 1, no claim stored and the previous claim kept: `hardDeadline: null`; missing `defaults_allowed`; `owner: null`; `allowance: {windows: null}`; a missing `lease`; `{task: null, x: 1}`.
- **AC10 Sessions and agents.**
  - `complete`/`release` on the claimed task send the claim's session.
  - An enqueued `comment` on the claimed task carries the claim's agent at flush.
  - The same key and payload enqueued under two `VIBE_AGENT` values deduplicates.
  - A payload containing `connection`, `session`, `agent` or `action` is refused at enqueue.
- **AC11 record_time and usage.**
  - `seconds: 0` and `604801` are refused, and so is a run ending 1 s in the future.
  - `2026-10-30T21:00:00Z` and `2026-10-30T21:00:00.000Z` with the same key dedupe, and the wire `started_at` is the ms value.
  - The `usage` importer under a descriptor binding enqueues `record_usage` jobs whose wire body has `windows: 0` and `task`.
- **AC12 Target resolution under `root: null`.**
  - `next-task` and `status` work.
  - Each of these exits 1 with the exact no-bound-task message, empty stdout and zero requests: `enqueue comment` without `--task`, bare `poll`, bare `ask-status`, bare `complete --summary s`, bare `release --reason r`.
  - `complete --task X --summary s` with no claim exits 1 with the session message.
  - `poll --task X` is accepted.
  - After a claim, `poll` and `enqueue comment` target the claimed task.
- **AC13 No leakage.** With a token sentinel and a hostile server error string, no stdout or stderr on any path in AC3–AC12 contains the token, the connection id or the hostile string. `status` contains no token, connection, origin port or workspace.
- **AC14 Regression and matrix.**
  - `checks_28`, `checks_29` and `checks_47` pass unchanged.
  - Every command is exercised at least once under a descriptor binding: `enqueue` × 4 kinds, `flush`, `poll`, `ask-status`, `status`, `next-task`, `complete`, `release`, `usage`, `reconcile`.
- **AC15 Docs and gates.**
  - `docs/taskandi-client.md` has a v2.2 section containing `taskandi-descriptor.json`, `chmod 600`, `host.docker.internal`, `Host: 127.0.0.1:<port>`, `wrong_origin`, `connection_scope`, `connection_revoked`, `refused`, `ask-status`, and the sentence that uncertain writes are never retried automatically, with the check-before-retry advice.
  - The stale "30000 ms" and "only MCP" statements are corrected per transport.
  - `CHANGELOG.md` has an entry.
  - The fixture copy matches `/brain2/...` byte for byte when brain2 is mounted (skipped otherwise).
  - `MANUAL-TESTS.md` gains Test 69: a real service through host.docker.internal (capabilities, next-task, ask, poll), unverified until run.
  - `python3 code-check.py` exits 0 and `python3 smoke-test.py < /dev/null` exits 0, with the new tests in `smoke/checks_50_taskandi_http.py` (≤ 1,500 lines, split if needed) called from `runner.main()`.
- **AC16 Limits.** Each limit is tested at its edge (accepted) and one over (exit 1, zero requests):
  - `question` 8000 code points (with an astral character, to prove code points); `default` 2000; 20 and 21 options; an option of 500;
  - the composed-post rule without and with options;
  - `comment.text` 8000; `complete.summary` 7950; `release.reason` 2000;
  - each id field at 200 and 201 code units;
  - whitespace-only text; a lone surrogate.
  
  Also: a final body of 65537 bytes at flush becomes `refused` with code `body_too_large`, with zero requests.
- **AC17 Unusable task id.** `next_task` returning `a b`, or a 201-character id, exits 1 with the exact message, no claim stored and empty stdout.
- **AC18 list_asks shape.** Each of these makes the page malformed (exit 1, cursor and answers unchanged): a `deferred` key; `seen_at: null`; `answer: null`; `subtask_id` non-null with `placed: thread`; `subtask_id` null with `placed: subtask`; `options` absent; `agent: "gemini"`; an `answer` of 8001 code points; a repeated `ask_id`; an ask whose `task` differs from the requested task. `ask_status` with `deferred: "no"` is refused.

## Out of scope

- Harness behaviour (`/vss`, `/vsss`, Codex `context.md`): that is slice 4.
- Firewall changes: the IPv4 host gateway is already allowed.
- Writing or fetching the descriptor for the user.
- `request_id` and v2.3.
- Any change to the MCP paths beyond sharing helpers.

## Model plan

- Planner + Evaluator: Opus 5.5.
- Spec Critic: sonnet.
- Generator: opus, ceiling opus.
- Tester: sonnet.
- Fable rung: not pre-authorised.
