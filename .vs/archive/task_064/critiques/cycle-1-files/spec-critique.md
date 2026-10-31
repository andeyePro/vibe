# Spec critique: task_064 (Task&I client, contract v2.2, HTTP transport)

Checked against: the ten fixtures plus README, `devcontainer/taskandi-client.mjs`, `taskandi-usage.mjs`, `docs/taskandi-client.md`, `checks_47`, `codex-supervisor.mjs` (it pins the binding fingerprint), `init-firewall.sh`, and live experiments on Node v22.23.4 in this container.

## Verified facts that decide the design

- **`fetch` cannot set Host.** On Node 22 (undici), `fetch(url,{headers:{host:'127.0.0.1:9999'}})` is silently ignored. The server saw `Host: 127.0.0.1:<real port>`. It also adds `sec-fetch-mode: cors`, `accept-language: *`, `user-agent: node`, `accept: */*`. `http.request({host, port, path, method:'POST', setHost:false, headers:{host:'127.0.0.1:9999', ...}})` does deliver the overridden Host, and the raw headers contain only host, connection and content-length plus whatever the caller sets. So the transport must be `node:http`/`node:https`. The existing `fetchTransport` cannot be reused for this path.
- **The wire task ids in the fixtures are not UUIDs.** `task` is `"project"` and `"leaf-b"`. `ask_id`, `comment_id`, `entry_id`, `completion_id` and `subtask_id` are UUID-shaped. `session` is `"session-a"`.
- **Firewall is IPv4-only.** `init-firewall.sh` allows `host.docker.internal` via `host_internal_ipv4` (`getent ahostsv4`). In this container `getent hosts host.docker.internal` returns an IPv6 ULA address only. A default `http.request` to `host.docker.internal` can therefore pick an address the firewall never allowed, or fail non-deterministically.
- **`bindingFingerprint(loadConfig(cwd))` is consumed outside the client.** `codex-supervisor.mjs:1278` stores it and refuses resume with "effective Task&I binding changed". A descriptor binding that changes on every reconnect would break supervisor resume.

## Concerns

### 1. BLOCKING. "Task ids are UUIDs; any other task id in a v2.2 result is refused" contradicts the authoritative fixtures.
AC2 and AC6 could never pass: `next_task` returns `task:"leaf-b"`, and `ask`, `list_asks`, `comment` and the rest echo `"project"`/`"leaf-b"`. The README says `root` is "task id of the granted subtree", not a UUID. Separately, the existing `TASK_REF` (`ABBR-12` or `taskandeye://node/UUID`) rejects `leaf-b`, so `--task leaf-b` currently dies at `taskRef()`.

Also, the server cannot resolve `ABBR-12` over v2.2. Sending it would produce `wrong_scope` or `invalid_request` after a round trip.

**Fix.**
- Define a v2.2 wire task id: opaque, `^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`. UUIDs are the production-expected shape but are not enforced.
- `taskandeye://node/<id>` is accepted as a ref and sent as bare `<id>`.
- Under a descriptor binding, `ABBR-N` refs are a usage error with no network call: `Task&I descriptor bindings take task ids, not ABBR-N references`.
- Descriptor `root` is that id form or `null`.
- Case: a UUID-shaped id is lowercased before send and before comparison with the claim. Other ids are verbatim. This avoids `checkTarget` string-compare mismatches ("accepted case-insensitively" in the draft otherwise sends mixed-case ids the server may not match).

**AC text.** AC6: "With the descriptor binding, `--task leaf-b`, `--task project` and a lower-case or upper-case UUID are accepted and sent as given (UUIDs lower-cased); `--task ABBR-12` exits 1 before any request; `taskandeye://node/<id>` is sent as `<id>`; a v2.2 result whose `task` differs from the requested or claimed task is refused."

### 2. BLOCKING. Transport mechanism unspecified. The draft implies `fetch`, which cannot send the required Host.
Under `fetch`, a real service would answer 421 `wrong_origin` on every container call.

**Specify.**
- New `httpTransport` on `node:http` (and `node:https` for `https://` origins).
- Container rule: `http.request({ host:'host.docker.internal', port:P, path:'/api/browser-agent', method:'POST', setHost:false, family:4, agent:false, headers:{ host:'127.0.0.1:P', 'content-type':'application/json', authorization:'Bearer …', 'content-length':N, connection:'close' } })`.
- `family:4` is needed because of the IPv4-only firewall.
- Non-container loopback: connect `127.0.0.1:P` and let Host default (it equals the descriptor host).
- `https://`: default Host, normal TLS verification (`servername`), no container rewrite.
- The only hosts the token may ever be sent to are the descriptor's own host and, for `http://127.0.0.1:P` in a container, the literal `host.docker.internal` on the same port. The connect host must never come from env or CLI.
- The test seam is an injected `connectHost` option on `createClient`, not an env var or CLI flag. That keeps the existing "no CLI bypass flag" invariant.
- Reject any 3xx. Enforce the 15 s timeout with `req.setTimeout` plus a hard timer. Count bytes on the stream: cap 16 MiB, check `content-length` up front.
- Existing `guardedMcp` asserts `new URL(request.url).origin === config.origin`. That check would reject the host.docker.internal rewrite. The v2.2 guard must instead compare the planned connect target against the allowed pair above.

**AC text (replaces AC3).** "A real loopback `http.createServer` test (not a fake fetch) records `req.rawHeaders` and `req.headers.host`. With the connect-host seam pointed at 127.0.0.1 and container mode on, Host is exactly `127.0.0.1:<descriptor port>` and not the listener's port. Header names present are exactly {host, content-type, authorization, content-length, connection}. No origin, cookie, referer, sec-fetch-*, user-agent or accept-language. Outside container mode Host equals `127.0.0.1:<port>` by default. A server answering 421 `{"error":"wrong_origin"}` and one answering 403 `{"error":"connection_scope"}` each produce exactly one request (a counter proves no retry), exit 1, and a stderr line naming the code. A 302 is refused with no second request. A source-level assertion shows the v2.2 transport calls neither `fetch(` nor passes a connect host from `process.env`." A fake `fetch` test cannot establish any of this.

### 3. BLOCKING. Printed result shapes for each command are never defined, yet AC2 says "yields the documented output".
Today `next-task` prints `{bound,task:{...}}`, `complete` prints `{bound,completed,state:'done-provisional'}`, `poll` prints `{bound,newAnswers,answers,ignored,conflicts,cursor:{sequence,value}}`, and `flush` prints counts. The v2.2 results differ in state value, ids, ms timestamps and cursor. Slice 4 (the harness) will parse stdout, so this is a contract.

**Fix.** Add a table to the spec and keep v2.1 key names where the meaning is unchanged:
- `next-task`: `{bound:true, channel:'taskandi-http', task:null}` or `{bound:true, channel, task:{task,title,body,priority,effective_priority,allowance,spent,hardDeadline?,latest_start?,estimate_minutes?,owner,lease:{until,session},defaults_allowed}}`. Timestamps stay as the server's ms numbers, never converted. `hardDeadline` absent or null is omitted.
- `complete` success: `{bound:true, completed:true, state:'provisional', completion_id}`. Note that `state` changes spelling from `done-provisional`; say so explicitly in the docs.
- `complete` with `open_children`: `{bound:true, completed:false, open_children:[{task,title}]}`, exit 0, claim kept.
- `release`: `{bound:true, released:true, comment_id}`.
- `poll`: `{bound:true, task, newAnswers, answers:[{ask_id,answer,seen_at,answered_at}], ignored, conflicts, cursor:{now}}`. Never emit `answered_by`. Say it is stored, not printed, and never compared.
- `ask-status`: `{bound:true, task, asks:[{ask_id,seen_at,deferred,answered}]}`.
- `flush`: v2.1 shape plus `refused` and `requeued` counts (see 7).
- Unbound: `{bound:false, channel:'file-fallback'}` as today.

**AC text (AC2 tightened).** "For each of the ten fixtures a harness serves `response` verbatim; `stdout` of the corresponding CLI command deep-equals the table's output derived from that fixture; and the request the client sent has exactly the key set in section 6 below (no extras, no omissions)."

### 4. BLOCKING. The binding fingerprint, outbox binding and answer binding for a descriptor binding are undefined. Getting it wrong either strands the outbox after a reconnect or lets jobs flow to a different workspace.
Existing code derives `bindingFingerprint`, `currentBinding` (jobs) and `bindAnswers` (answers) from `{endpoint, task, contractRevision}`. The supervisor pins the fingerprint across resume.

The draft's recovery path for `connection_revoked` is "copy a fresh descriptor". A reconnect issues a new `connection` and a new `token`, and may come with a new origin port after `npm run serve:account` restarts. If any of those are in the digest, every queued job fails `BINDING_CHANGED`, `poll` fails `answer binding changed`, and supervisor resume refuses. The documented remedy would not work.

**Fix.** Digest for a descriptor binding = `{kind:'descriptor-http', workspace, task (effective: VIBE_TASK_REF > .vibe/taskandi-task > root, null when none), contractRevision:'vibe-agent-exchange-v2.2'}`. It excludes token, connection and origin (a different origin serving the same workspace id is the same data; the workspace id identifies it). Switching workspace or bound root still gives `BINDING_CHANGED` and `answer binding changed`.

State the choice and its rationale. If the spec author prefers including the origin, then say plainly that recovery from a revoke or a port change needs an archive step, and that supervisor resume will refuse.

Also:
- Jobs get `channel:'taskandi-http'`. `status.channel` must report it (today it hard-codes `'taskandi-mcp'`).
- A binding switch between MCP and descriptor must give `BINDING_CHANGED`, not a silent redirect.

**AC text.** "Re-reading a descriptor with a changed `token` and `connection` (same workspace/root) leaves `bindingFingerprint`, queued jobs and the answer binding valid: `flush` delivers and `poll` succeeds. Changing `workspace`, or the effective task, makes `flush` fail `BINDING_CHANGED` and `poll` fail `answer binding changed`. `VIBE_TASK_BINDING=<fingerprint>` equals the fingerprint under a rotated token; `loadConfig` under a different workspace fails 'pinned task binding changed'. `codex-supervisor` still loads (import-level test)."

### 5. BLOCKING. A single global answer cursor and `poll` with no target cannot work with `root:null` or claimed leaf tasks.
`state.cursor` and `bindAnswers` assume one polled task (`config.task`). The draft says "`poll`/`ask-status` with an explicit claimed task", but today `poll` takes no flags. Under `root:null` there is no default task at all. Under a bound root, answers for asks on the claimed leaf are never polled. If the claim changes (A then B), the shared `now` cursor from A silently skips older answers on B, which is permanent loss.

**Fix.**
- Cursors become per task: `state.cursors[taskId] = {now}`.
- `poll [--task REF]` (and `ask-status [--task REF]`): the target is `--task`, else the claimed task, else the effective bound task, else a usage error. This is a deliberate behaviour for v2.2 and must be documented.
- `answerBinding` stays workspace-level; answers are keyed by `(task, ask_id)`.
- `--task` must pass the same targeting rule (bound or claimed task only).
- The initial `since` is 0 (a number); the client sends `since` from the stored `now`; accept `now >= since`, otherwise refuse the page and keep the cursor.
- The v2.1/v1 `state.cursor` shape is untouched; the two never mix because the answer binding differs.

**AC text.** "Poll A (answers a1, now=T1) then claim B and poll B: B's request carries `since:0`, not T1. Polling A again sends `since:T1`. A `now` lower than the request's `since` is refused and leaves the cursor and answers unchanged."

### 6. BLOCKING. Request body rules ("the call's fields plus action, connection, agent, session") conflict with the fixtures. Sending uninvited fields is a service contract risk; omitting `agent` mis-attributes.
Per-fixture `request` key sets:
- `next_task`: action, agent, session. It does **not** carry `task`. The old client sent `task: config.task`; the subtree is implied by the token. Sending it would be an extra key.
- `ask`: includes agent and session (both optional). `comment`: includes agent (the note says the default persona is `codex`, so a Claude client that omits it posts as codex) and session.
- `list_asks`, `ask_status`, `complete`, `release`, `record_time`, `record_usage`: only task/fields plus session. No `agent`.
- `capabilities`: only `action` (plus `connection`). No session.

**Fix.** Pin exact key sets:
- `agent` is sent exactly on `next_task`, `ask` and `comment`.
- `session` is sent on every task-bearing call, only when known; never on `capabilities`.
- No `task` on `next_task`.
- `connection` is always sent, never read from payloads. A payload carrying `connection`, `action`, `agent` or `session` is refused.

Where `agent` and `session` come from for enqueued jobs is not specified. `enqueue ask|comment` has no `--agent`, and flush runs possibly hours later. Proposal:
- `agent` is resolved at enqueue time (claim.agent when the target task is the claimed one, else `VIBE_AGENT` if `claude|codex`, else `claude`) and stored on the job outside `payload` and outside the dedup digest (otherwise one key could conflict by agent).
- `session` is resolved at dispatch: the current claim's session if the job's task is the claimed task, else omitted.
- State this, and say that a `comment` or `ask` on a task whose lease another session holds can be refused `lease_held` (the fixture notes say any call carrying the task renews the lease, so it likely checks it). That is transient (see 7).
- Drop the "`--session` on other commands overrides" idea unless it is specified and tested: it adds flags to `strictFlags` and lets a caller send a session different from the lease holder.

**AC text.** "For every call the recorded request's sorted key set equals the fixture request's key set (after substituting the client's own agent/session) plus `connection`: asserted per fixture, including `next_task` having no `task`, `complete` having no `agent`, and `comment` having `agent:'claude'` when the client's agent is claude. A payload with `connection` or `session` is refused at enqueue. Two jobs with the same key and payload but different resolved agents deduplicate."

### 7. BLOCKING. The error and state model is incomplete, and some of it is wrong.
**a) `connection_revoked` must not turn a job into `refused`.** The draft says any 409 makes a job `refused`. For a revoked token the job was not rejected on its merits. The documented recovery is to copy a fresh descriptor, after which the same job should be deliverable. Marking it terminal forces manual re-enqueue under new keys.

Proposed table (client-side classification, all 409 bodies `{error:<code>}`):
- **Not applied, transient or environmental** → job back to `queued` with `lastError`, flush stops, exit 1, plain stderr message: `connection_revoked`, `connection_changed`, `descriptor_origin_changed`, `use_native_connection`, `sync_required`, `lease_held`, plus HTTP 421 `wrong_origin` and 403 `connection_scope`.
- **Not applied, terminal on content** → `refused` with `lastError=<code>`, flush continues with the next job (these jobs do not block ordering): `scope_missing`, `wrong_scope`, `wrong_thread`, `unknown_ask`, `ask_answered`, `not_assigned`, `invalid_request`, `stale_context`.
- **Unknown or ambiguous** → `uncertain`, flush stops: `connection_unavailable` (README: "any other server failure", so the effect may have happened), `receipt_collision`, and any unrecognised code, any non-409 status, non-JSON, truncation, timeout, socket error after send.

Please have Task&I confirm that `receipt_collision` and `stale_context` mean "not applied". If unconfirmed, put them in the uncertain row. The point is that `refused` is only for codes the server defines as rejected before any effect.

**b) `refused` is new and its lifecycle is not defined.** `reconcile` only accepts `uncertain` jobs. `status` counts only four states. Define:
- `status.counts.refused` and `refusedIds` with their codes (codes are validated, see 7e).
- `reconcile --key K --action retry` allowed for `refused`. `--action done` is not allowed for `refused`: the server said no.
- Add `discard`? Keep it minimal. Without a way out, a refused job lives forever. Recommend allowing `retry` only, with evidence required, for refused jobs.
- The v2.1 and v1 paths must still reject `refused` as an unknown state (they never produce it).

**c) Non-409 statuses are unspecified.** 401, 404, 429, 5xx, 200 with non-JSON or with an `error` key, a 409 whose body is not `{error:string[,children]}`. Rule: HTTP 200 with a body that fails exact validation → treated as a post-send failure (uncertain for jobs; `outcome unknown` for `complete`/`release`). Any non-200/409 → the same ambiguous class. Only exactly-formed 409/421/403 bodies are interpreted.

**d) Direct commands.** Draft covers `open_children` and `connection_revoked` only. State the rule for every direct command: `next-task`, `ask-status`, `poll` (read-only; failure leaves state untouched; exit 1; stdout empty); `complete`/`release` (any failure after send: stderr `outcome unknown; check the task in Task&I:` for ambiguous class, a plain `Task&I refused: <code>` for a definite 409; claim kept; exit 1). Note that `complete` is documented idempotent ("Repeating it returns the same completion"), so ambiguous `complete` can be safely retried. Add that to the docs.

**e) Server-controlled strings in stderr.** Error `code` and `children[].title` come from the network. Print a code only if it matches `^[a-z][a-z_]{0,63}$`, else `unknown_error`. Titles stay as data in the JSON (as v2.1) and never go to stderr. Bound `children` to 1..200.

**f) `capabilities` failing with `connection_revoked`/421/403.** Same handling as above, pre-dispatch: nothing changed, jobs stay queued.

**AC text (AC4 replacement).** One test per row of the table: serve the code from a fake server and assert the job state (`queued`/`refused`/`uncertain`), flush's `stopped`/`continued`, exit code, stdout empty or JSON, stderr text, and that `state.json` claim/cursor are unchanged. Plus: `connection_revoked` message equals the draft's text exactly and the request counter shows no retry; a 409 with a hostile `error` value (`"x\u001b[2J"`) prints `unknown_error`; `reconcile --action retry` re-queues a refused job; `--action done` on a refused job exits 1.

### 8. BLOCKING. Nullability and optionality in `next_task` (and `list_asks`) are guessed; the fixture notes contradict the draft in at least one place.
- Notes say `allowance` is "the task's own, else its nearest ancestor's, else **null**". The existing `strictObject(value.allowance…)` throws on null, so a legitimate response would be refused after the server already took a lease (the claim is then not stored; the lease sits for 90 min).
- `priority`/`effective_priority`: "null means none set". The draft says number-or-null; the existing code requires a nonnegative integer. Make it finite number or null.
- `hardDeadline`: "nearest one on the task or above" — likely absent or null when none. Accept absent or null.
- `owner`: could be null for an agent-assigned task. Accept string or null.
- `latest_start`, `estimate_minutes`: optional, as draft.
- `defaults_allowed`: required boolean in the fixture and "always false" for now; draft says absent means false. Prefer required (it is in the fixture), absent → false is the lenient choice. Pick one and test it.
- `list_asks` per-ask fields: only a single sample exists. Decide and document: `seen_at` number|null; `in_reply_to` string|null; `subtask_id` string|null (it should be null for `placed:'thread'`); `options` array of strings (may be absent if none were given); `agent` string|null; `answer` string (empty allowed as today); `answered_by` string (stored, never printed, never compared).
- Ask Task&I to confirm these nullabilities in writing. Then the strict "unknown key refuses" rule is defensible. Record in the spec which fields are guessed. If a guess is wrong, a whole poll page is refused forever (the cursor never advances).

Also decide an explicit text bound for answers. The existing `LIMITS.text` = 8000 refuses the whole page if one answer is longer, and that would block polling permanently. The server's limit is unknown; either match it, or store a bounded prefix with a digest and a `truncated:true` flag. Needs a decision.

**AC text.** "next_task with `allowance:null`, `priority:null`, `effective_priority:null`, `owner:null`, no `hardDeadline` is accepted and stored as the claim; with a missing `lease` or a non-number `hardDeadline` it is refused with no claim stored and any previous claim kept; `defaults_allowed` behaviour is pinned both ways."

### 9. BLOCKING (acceptance criteria not mechanically testable as written). AC1, AC5, AC6 and AC8 are one-liners; "draft, to be tightened" leaves them unverifiable.
Proposed replacements:

- **AC1 (descriptor).** One subtest per row, each asserting exit 1, a stderr message naming the rule, and zero requests: wrong `protocol`; missing/extra key; `token` of 42 or 44 chars or with a character outside `[A-Za-z0-9_-]`; `origin` with trailing slash, path, query, fragment, userinfo, `localhost`, `[::1]`, `http://` non-loopback, `http://127.0.0.1` without a port, port 0 or 65536 or leading zero; `connection`/`workspace` empty or over 200 chars; `root` empty string or an invalid id form; file mode 0644 (message mentions `chmod 600`), hard link (nlink 2), symlink, foreign owner (skipped when not root, as the existing tests do), tracked by git, tracked under a different case, over 32 KiB, `.vibe` a symlink; both `taskandi.json` and the descriptor present (`two Task&I bindings; keep one`). Positive controls: a valid descriptor loads; `root:null` loads with `task:null`. Origin rule should be `new URL(origin).origin === origin`.
- **`root:null` rows.** With no override: `next-task`, `poll --task X`, `ask-status --task X`, and `status` work; `enqueue … ` without `--task`, `complete`, `release`, bare `poll`/`ask-status` exit 1 with the exact draft message, zero requests; with a claim they use the claim. State that the error is a usage error, exit 1, stdout empty.
- **AC5 (capabilities).** "Each invocation that touches the network sends exactly one `capabilities` request first. Cases: `contract:'vibe-agent-exchange-v2.1'` → exit 1, jobs remain `queued`, no later request; `calls` lacking the call about to be made (per call kind, and for `flush` per queued kind) → same; `protocol` different from the descriptor's → same; response with extra or missing keys → same; `grade` is recorded (not gated; say so) and shown in `status` only if known from a prior call, because `status` stays offline (see 10). `capabilities` returning 409 `connection_revoked` gets the plain message. No request for `status` and `reconcile`, and none when unbound."
- **AC7 (regression).** Not only "checks_28/29/47 pass untouched". Also assert: `requireV2`, `TOOL_SPECS`, `validatePayload` v1 flag, `flush`'s `revision === CONTRACT_REVISION` ask-result branch, and `status` all behave for the third revision, not by accident. Matrix: every command (`enqueue` ×4 kinds, `flush`, `poll`, `status`, `next-task`, `complete`, `release`, `usage`, `reconcile`) under the descriptor binding is exercised at least once. `taskandi-usage.mjs`'s `enqueueTranscriptUsage` calls `client.resolveTask` and `requireV2`, so the usage importer must be in the matrix.
- **AC8 (docs/gates).** Name the checks: `docs/taskandi-client.md` contains a v2.2 section with the strings `taskandi-descriptor.json`, `host.docker.internal`, `Host: 127.0.0.1`, `wrong_origin`, `connection_scope`, `connection_revoked`, `refused`; the stale lines are fixed (30000 ms timeout, "only MCP"); `CHANGELOG.md` has an entry; `python3 code-check.py` exits 0; `python3 smoke-test.py < /dev/null` exits 0 with the new tests registered in `smoke/runner.py`; new test file name and ≤1,500 lines. Add a test that the fixtures copy under `smoke/fixtures/taskandi-v22/` is byte-identical to `/brain2/...` when brain2 is mounted (skip otherwise) and carries a provenance note.
- **AC for no leakage** (missing from the draft, present in checks_47 AC13). Token sentinel and a hostile server body never appear in stdout or stderr on any error path, including node transport errors; the descriptor file is never echoed.

### 10. MINOR. `status` "gains nothing new" contradicts the draft's own additions.
`status` must show `channel:'taskandi-http'`, the `refused` count and ids, and `claimedTask`. Keep `status` offline (no capabilities probe). State: no token, no connection id, no origin port in the output. Say so; add it to AC13-style leakage test.

### 11. MINOR. Response size and timeout.
"Use the existing response limit if smaller" is ambiguous: the existing limit is 1 MiB, which is smaller than the README's 16 MiB, so literally it picks 1 MiB. A page of 1000 answers at up to 8000 characters each could exceed 1 MiB. Decide: v2.2 transport enforces 16 MiB (MCP keeps 1 MiB). Docs currently say a 30000 ms timeout; v2.2 is 15 s. Update the docs. Test: a 1.5 MiB valid body is accepted; 16 MiB + 1 is refused with the connection destroyed (assert early abort via a streaming server), and a `content-length` above the cap is refused before reading.

### 12. MINOR. `record_time` and `record_usage` details.
- Server: "the run may not end in the future". The draft's 60 s client slack means a job with `started_at + seconds` 30 s ahead passes the client and is then refused `invalid_request` by the server. Make the client check strict at enqueue (`end <= now`) or say plainly that slack-induced refusals become `refused`.
- Check the time conversion: ISO with fractional seconds must keep ms; `seconds` integer 1..604800 (today 0 is allowed; max is new); `started_at` must be a positive safe integer ms in the payload digest, so the same key with the same ISO input dedupes and the same instant spelled differently (`…Z` vs `….000Z`) also dedupes.
- `record_usage`: `windows:0` is sent. The existing payload has `account` and `cost_estimate` required; the wire has them optional. Keep them required in the client (stricter is allowed) but say so. `source_ref` stays the enqueue key.
- Response validation: echoed `task` must equal the request; `spent.tokens`/`windows` safe nonnegative integers. Echo check applies to every task-bearing response; the draft never states it.
- Fixture `ask_status.json` has `deferred` always false for now. Validate as boolean, not as `false`.

### 13. MINOR. `session` semantics.
- `next-task --session ID` uses `stableKey` charset; the wire only shows `session-a`. Fine, but say the 200-char limit and the charset in the spec and in the docs.
- The stored lease is the one returned by `next_task` and is not refreshed by later calls, though the service renews it. Say that `claimed.lease` is "as of next_task" and the client never judges expiry.

### 14. MINOR. Container detection and the file path.
- Define precedence: `VIBE_CONTAINER=0` should force direct; `/.dockerenv` alone is also true under other container runtimes where host.docker.internal may not exist. A failed connect to `host.docker.internal` should say so (`ENOTFOUND`/`ECONNREFUSED` → message names both the rewrite and the descriptor port), as a transport error.
- The Connect Codex flow writes the descriptor on the Mac at `<state>/browser-agent-taskandeye/connection.json` (0600). Copying into `.vibe/taskandi-descriptor.json` must keep 0600; `cp` normally yields the umask default and will trip the mode check. The error message should include `chmod 600 .vibe/taskandi-descriptor.json`. Docs should say it is the user's step (out-of-scope in the draft is fine, but the docs must not leave this implicit).
- Live reachability of a 127.0.0.1-bound service through `host.docker.internal` depends on the Docker runtime (OrbStack and Docker Desktop forward it to the host loopback; plain Linux Docker does not). The spec should add a MANUAL-TESTS.md step for a real service and say it is unverified until run; no AC can prove it.

### 15. MINOR. Draft-internal inconsistencies to tidy.
- Section "Origin and Host" says origin forms `https://…` or `http://127.0.0.1:<port>`; the Descriptor bullet says "case-insensitive" tracked check applies; keep it identical to `.vibe/taskandi.json`'s `trackedCaseInsensitive`.
- "If both files exist, refuse": also specify what a half state does — descriptor present but unreadable. Refuse; never silently fall back to `taskandi.json` or to unbound.
- `VIBE_TASK_BINDING` handling in `loadConfig` for a missing-config project (`'unbound'`) must also cover a missing descriptor.
- New command `ask-status` must be added to `USAGE`, to `strictFlags`, and to the harness docs; `poll --task` likewise.
- `next-task` result stored as `claimed`; the existing check "a failed next-task keeps any previous claim" must also hold when capabilities fails or when the response is refused for nullability.
- Redirect refusal and timeouts apply to `capabilities` as well.

## Verdict

**NEEDS REVISION. Not ready to start.** The overall shape (descriptor-selected node:http transport beside the unchanged MCP paths) is sound, but as written the spec contradicts the authoritative fixtures in its first rule, would fail every container request, and leaves the binding and error semantics open.

BLOCKING items: 1 (task ids are opaque strings, not UUIDs; ABBR refs unusable), 2 (transport must be node:http with `setHost:false`, IPv4, no fetch; guard rework; real-socket test), 3 (stdout shapes per command undefined), 4 (binding fingerprint, outbox and answer binding must exclude token/connection/origin, supervisor pin), 5 (per-task cursors and poll/ask-status target rule), 6 (exact request key sets per call; where agent/session come from at flush), 7 (error to job-state table: revoked is not `refused`; transient vs terminal vs uncertain; non-409 statuses; refused lifecycle in status/reconcile; hostile code strings), 8 (nullable allowance/priority/owner/hardDeadline, ask-field nullability, answer text bound), 9 (ACs 1, 5, 6, 7, 8 to be replaced with the concrete wording above; add a leakage AC).

## Iteration 2

Checked rev 2 (`spec-task_064-client-v22.md`) against the ten fixtures plus README.

### Iteration-1 BLOCKING items
1. Task ids: resolved (opaque wire id, UUID lower-casing, ABBR usage error, AC6).
2. Transport: resolved (node:http, setHost false, family 4, seam, header set, AC3 with a real listener).
3. Printed output: resolved by the table, except see concern 2 below (six fixtures have no stdout row).
4. Binding digest: resolved (kind/workspace/task/revision; AC7; supervisor import test).
5. Cursors: resolved (per-task, target rule, AC8), but see concern 1 for the root:null edge.
6. Request key sets: resolved and consistent with all ten fixtures (next_task has no task; complete/release/list_asks/ask_status/record_* have no agent; comment and ask/next_task carry agent; capabilities has none).
7. Error model: resolved (three classes, refused lifecycle, hostile-code rule, direct-command rules, AC4). Consistent with AC4 and AC3. `receipt_collision` and `stale_context` are provisional in one constant: acceptable.
8. Nullability: resolved as a decision (allowance/priority/owner/hardDeadline nullable; per-ask nullabilities; 64000 answer cap), marked guessed.
9. ACs: resolved; AC1/5/6/8 are now mechanical.

### Concerns

1. BLOCKING. root:null versus the complete/release session rule and the `--task` targeting rule disagree, and AC12 pins the exact message.
   - Sessions bullet: `complete`/`release` on a task that is not the claimed task are refused with `complete/release needs the session that claimed the task; run next-task first`.
   - AC12: `complete --task X` and `release --task X` with `root:null` and no claim must exit 1 with `no bound task: the connection covers the whole workspace; claim one with next-task`.
   - Both describe the same input, so a Generator has an even chance of failing one test.
   - The Cursors section also says `--task` is accepted for "bound or claimed only". With `root:null` nothing is bound, so `poll --task X` would be refused, yet the root:null section and AC12 treat `--task X` as valid for `enqueue`/`poll`.
   - Fix: add one precedence line. Order of checks for `complete`/`release`: (a) no target resolvable (no `--task`, no claim, no effective task) gives the no-bound-task message; (b) a target that is not the claimed task gives the session message, including `complete --task X` under `root:null`. Change AC12 to use bare `complete`/`release` for the no-bound-task message and `--task X` for the session message. State that under `root:null` any wire id is a valid `--task` for `poll`/`ask-status`/`enqueue` (the token bounds it server-side), and under a non-null root `--task` is limited to the claimed task or the root.

2. MINOR. AC2 requires stdout to deep-equal the printed-output table for all ten fixtures, but `capabilities`, `ask`, `comment`, `record_usage` and `record_time` have no stdout row of their own (they go through `flush`/`enqueue`). Say that for these the check is on the recorded request and on `flush` counts plus the stored job result, not on stdout.
3. MINOR. The `httpConnect` seam is described as a "connect-host override" but AC3 needs a different port as well (listener port differs from the descriptor port P). Say it is `{host, port}`.
4. MINOR. The size cap (16 MiB, early abort, `content-length` precheck) and the 15 s timeout are in the design but have no AC. Add a streaming-server test for each, as proposed in iteration 1 concern 11.
5. MINOR. "reported, see Errors" for an over-long answer points to nothing in the Errors section. Say: the page is refused as a malformed 200 (direct `poll` exits 1, cursor unchanged), so a single oversize answer blocks polling that task until Task&I fixes it; this is accepted.
6. MINOR. The user note says guessed nullabilities must live in one place. Only the error table is called out as one constant. Add: the `next_task`/`list_asks` nullability rules are one schema constant in the code.
7. MINOR. `session` charset and 200-char limit for `next-task --session`, the "lease is as of next_task and never judged" note, and `list_asks` `asks[].task` equalling the requested task are still unstated. One line each.
8. MINOR. AC5 "each networked invocation sends one capabilities request": say whether `flush` with an empty queue counts (suggest no request).

## Verdict (iteration 2)

**revise** (one BLOCKING: concern 1, a one-paragraph precedence fix). Everything else may be folded in while fixing it; with concern 1 resolved the spec is ready to implement.

## Iteration 3

Checked rev 3 plus "Rev 4" against README "Wire details" and the fixtures (next_task, list_asks, capabilities read in full).

### Iteration-2 BLOCKING item (target-resolution precedence)
Resolved. The "Target resolution (precedence)" section orders the checks (no target gives the no-bound-task message; a non-claimed target for complete/release gives the session message; `--task` acceptance differs for root:null), and AC12 now uses bare complete/release for the first message and `complete --task X` for the second. One leftover: the Cursors section still says `--task` is "bound or claimed only", which contradicts precedence rule (3) (any wire id under root:null). See MINOR 1.

### Rev 4 against the README
The new classes match the README table: connection_unavailable and connection_revoked are unknown; stale_context, sync_required, lease_held (and open_children) are not-applied-retryable; use_native_connection, scope_missing, invalid_request, wrong_scope, wrong_thread, unknown_ask, not_assigned, receipt_collision are rejected; connection_changed, descriptor_origin_changed, ask_answered fall to "other code" = unknown. Limits, the 7950 summary bound, 65536 body with HTTP 400, id charset policy, the next_task shape, the list_asks shape, no-idempotency and the cursor overlap all match. No Rev 4 statement contradicts the README.

### Concerns

1. BLOCKING. Rev 4 is an overlay, and rev 3 text that it contradicts is still live and in places tested. A Generator or Tester reading top to bottom will implement the old text. Fold Rev 4 into the body (edit in place, delete the superseded text) rather than "wins over anything above". At minimum these are still contradictory:
   - "Errors and job states" table rows and its footnote ("`receipt_collision` and `stale_context` provisional", `connection_revoked` "never retried" under the old class) versus Rev 4 classes; AC4 still says "every code in the three rows".
   - Same table: "a repeated `complete` is safe" versus Rev 4 "complete is idempotent only while unresolved" (after the owner reopens, or a partial failure, a retry posts a second comment).
   - Responses, `next_task`: `priority`/`effective_priority` "finite number or null", `allowance` "optional", `owner` "string or null", `hardDeadline` "ms, null or absent", `defaults_allowed` "absent treated as false", "nullability marked guessed", and the original AC9 cases (`owner: null`, no `defaults_allowed` accepted and printed `false`) versus Rev 4 (`owner: null`, `hardDeadline: null`, missing `defaults_allowed` refused). Rev 4 says AC9 "replaces its nullability cases" but the old AC9 sentence is still there.
   - Responses, `list_asks`: `answer`/`question`/`default` "≤ 64000", the "over-long answer blocks polling" paragraph, and `seen_at`/`subtask_id`/`agent`/`answer` nullable, versus Rev 4 (answer 8000, question 8000, default 2000, non-null in list_asks, `subtask_id` null iff thread, `options` always an array).
   - Definitions: "UUID ids lower-cased before sending and before any comparison" and AC6 "comparisons with the claim are case-insensitive" versus Rev 4 "compare exactly; lower-casing only for user-typed `--task`". Say once: user-typed `--task` UUIDs are lower-cased on input, and every later comparison (claim, response echo, descriptor `root`) is exact.
   - AC8: "poll A again sends `since: T1`" versus Rev 4 "second poll sends `now - 2000`". These cannot both pass. Also state that the "response `now` ≥ request `since`" check uses the sent (overlapped) `since`, and that the stored cursor is the response `now`.
   - AC15: requires "provisional/guessed markers" in docs. After Rev 4 nothing is guessed; the markers should be dropped (or restricted to the one remaining unverified item, the 421/403 classes, see MINOR 4). Docs must instead carry the "uncertain is never auto-retried; check `ask-status`/`poll`/Task&I before `reconcile --action retry`" guidance, which has no AC today.

2. BLOCKING. The "question + default + options joined ≤ 7980" rule is not defined exactly enough for AC16's edge tests ("at its edge and one over"). The README's bound comes from the composed thread post `Question: …\nDefault: …[\nOptions: a / b]` ≤ 8000 code points. With options present the joined-length reading and the composed-length reading differ, so the edge is ambiguous. Fix: state the check as `[...("Question: " + q + "\nDefault: " + d + (options.length ? "\nOptions: " + options.join(" / ") : ""))].length ≤ 8000`, and have AC16 test the edge both without and with options. Same for `complete.summary` (≤ 7950, code points) and "code points" versus "code units" (texts in code points; ids in UTF-16 units).

### MINOR

1. Cursors section: replace "(bound or claimed only)" with a pointer to Target resolution rule (3).
2. Body cap: say where the 65536-byte check runs. An `ask` of 20 options x 500 code points x 4 bytes already exceeds it, and `connection`/`agent`/`session` are added only at flush. Fix: check the serialized final body at flush too; a job that overflows then is `refused` locally with zero requests (enqueue checks with worst-case 200-char session/connection). Count UTF-8 bytes of the JSON text.
3. AC16 omits: whitespace-only text, lone surrogates (README: "well-formed"), and the 201-code-unit id fields (`model`, `source`, `source_ref`, `account`, `session`, `in_reply_to`). Add them.
4. HTTP 421 `wrong_origin` and 403 `connection_scope` are not in the README (it names no non-409/400 status). Say where they come from (BT/AS source) or mark them provisional, and say what a 421/403/400 with a body other than the exact `{"error": code}` is (suggest `uncertain`, as for any other status). AC4 should include the HTTP 400 `{"error":"invalid_request"}` case explicitly, and a 400 with another body.
5. Direct `complete`/`release` with `connection_revoked`: both "outcome unknown; check the task…" and the exact revoked message apply. State the order (suggest: revoked message first, then the outcome-unknown line) and put both in AC4.
6. No AC covers the Rev 4 list_asks shape (`seen_at`/`answer`/`answered_by`/`answered_at` non-null, `subtask_id` null iff thread, `options` array, `agent` claude|codex, no `deferred` key, `ask_status.deferred` boolean). Add an AC with one malformed-page case per rule (exit 1, cursor unchanged). Also an AC9 case each for `allowance: {windows: null}` (refused), `latest_start` present (accepted), `defaults_allowed: true` (accepted and printed `true`), and a `next_task` `{task: null, x: 1}` (refused).
7. Cursor overlap: say how `ignored` and `conflicts` behave on repeated pages (a repeated non-owner answer must not inflate `ignored`; an identical repeat is not a conflict). Persist the dedupe set per `(task, ask_id)` and say whether it is bounded.
8. AC15's `Host: 127.0.0.1` needle: Rev 3 already requires `Host: 127.0.0.1:<port>` semantics; make the needle the exact literal that the docs will contain.

## Verdict (iteration 3)

**revise.** Iteration-2's BLOCKING item is resolved and Rev 4 is consistent with the README, but two BLOCKING items remain: (1) fold Rev 4 into the body so superseded text and ACs (error table, "complete is safe", next_task nullability and original AC9, 64000 caps, case-insensitive comparison, AC8 `since: T1`, AC15 "guessed" markers) cannot be followed by a Generator; (2) define the 7980 composed-length rule exactly. Both are editorial; no new design is needed.

## Iteration 4

Checked rev 5 (consolidated) against the iteration-3 items, itself, the README "Wire details" and all ten fixture requests/responses.

### Iteration-3 items
- BLOCKING 1 (fold Rev 4 in): resolved. No overlay remains; error table, complete idempotency, next_task nullability, list_asks shape and caps, exact-compare ids, AC8 `since: T1 - 2000`, and AC15 (no guessed markers; check-before-retry sentence required) are all single-voiced.
- BLOCKING 2 (composed-post rule): resolved. The exact formula is stated in code points, and AC16 tests it without and with options.
- MINOR 1-8: all addressed (Cursors points to Target resolution; body cap at enqueue and flush with `body_too_large`; AC16 whitespace, lone surrogate and 200/201 id fields; 421/403 sourced to the taskandeye session and other bodies are unrecognised; revoked message then outcome-unknown line, in AC4; AC18 and expanded AC9; repeat-page dedupe and unbounded set; AC15 literal `Host: 127.0.0.1:<port>`).

### README agreement
No disagreement found. Request key sets match all ten fixtures (next_task has no task, complete and release have no agent, comment/ask carry agent), class table matches README section 3, limits and 7950 bound match, list_asks and ask_status shapes match.

### Concerns

BLOCKING: none.

MINOR:
1. AC2 says the request values equal the fixture `request` after substituting agent and session, but the `record_usage` fixture has `source_ref: "session-a"` while the spec defines `source_ref` as the enqueue key. Say the test uses `session-a` as the key (or also substitutes `source_ref`), otherwise the byte comparison fails.
2. `next_task.body` is capped at 32000 here, but the README says workspace text has no length cap. An over-long context would be refused after the server already issued a 90-minute lease. Acceptable, but state the message/exit is the same as AC17 (no claim, empty stdout), or drop the cap.
3. AC3 "421, 403 and 302 each produce exactly one request": say which call the server answers (suggest a `capabilities` request, so the count is one). The 421/403 rows are "not applied, try later" for jobs, which would need a second case on a queued job after a successful capabilities call.
4. Poll dedupe: say whether non-owner answers are stored in the `(task, ask_id)` set, so a repeated non-owner answer does not inflate `ignored` (one sentence).
5. AC4 "the counter shows no retry": name the counter (for example the recorded request count on the loopback server).
