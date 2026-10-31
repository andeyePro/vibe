# task_064 cycle 1 — Generator report

## Files changed
- `devcontainer/taskandi-client.mjs` — new v2.2 section (descriptor loader, `httpTransport` on node:http/https, `HTTP_ERRORS` table constant, `RESPONSE_SCHEMA` constant with one `conform` validator, `validateHttpPayload`, target resolution, `createHttpClient`), `bindingDigest` shared by fingerprint/job/answer bindings, dispatch from `createClient` methods when `.vibe/taskandi-descriptor.json` exists, `descriptorMain` CLI, new exported `cli(argv, clientOptions)` entry (stderr printing + exit code), `main(argv, clientOptions)`. MCP code paths untouched apart from the shared digest helper (identical value) and `reconcile` accepting `refused` (http-channel jobs only).
- `devcontainer/taskandi-usage.mjs` — uses the task returned by `resolveTask` (lower-cased UUID under a descriptor).
- `docs/taskandi-client.md` — intro no longer "MCP client" only; timeout line now per transport (30000 ms / 1 MiB MCP, 15 s / 16 MiB HTTP); new "Contract v2.2: HTTP transport (descriptor binding)" section with all AC15 strings.
- `smoke/fixtures/taskandi-v22/` — ten fixtures byte for byte (`cmp` clean) + `PROVENANCE.md`.
- `MANUAL-TESTS.md` Test 69; `CHANGELOG.md` entry at top of `## 2026-10-31`.
- Not mine, present in the diff: `smoke/runner.py`, `smoke/checks_50_*.py`, `smoke/checks_52_*.py` (Tester, concurrent), `.vss/sessions/…` (orchestrator).

## Test seam / harness notes for the Tester
- `createClient({cwd, httpConnect: {host, port, timeoutMs?}})`; CLI from a harness: `import {cli} …; process.chdir(dir); await cli(argv, {httpConnect})` (see `.vs/cycle-1/scratch-tests/runner.mjs`). The seam replaces only the connect target; Host stays `127.0.0.1:<origin port>`.
- Container mode: `VIBE_CONTAINER=1`, or `/.dockerenv` (present in this container) unless `VIBE_CONTAINER=0`.

## Ambiguities resolved
1. **Flush exit code**: flush always exits 0 with counts (as MCP flush does for `uncertain`); each affected job gets a stderr line `taskandi-client: <key>: <message>`; `connection_revoked` prints the exact revoked line first. Capabilities failure / BINDING_CHANGED exit 1.
2. **`body_too_large` with zero requests vs the capabilities gate**: flush pre-checks every queued job's final body (real connection, claim session, agent) before capabilities; oversize jobs become `refused`, and if nothing sendable remains no request is made. Re-checked again per job at dispatch.
3. **Connect failure before the socket connects** = not sent: job goes back to `queued` (`requeued`), flush stops; direct commands exit 1 naming `host.docker.internal:<P>` and `127.0.0.1:<P>`. Once TCP-connected, any failure is outcome unknown (conservative).
4. **Status codes**: 3xx → unknown, code `redirect`; other status → `unexpected_status`; 200/400/403/409/421 with a non-exact body → `unrecognised_response`; 200 failing the schema → `malformed_response (<schema path>)` (paths only, never server keys/values).
5. **Direct-command messages**: unknown `Task&I outcome unknown: <code>`; later `Task&I refused for now: <code>`; rejected `Task&I refused: <code>`; complete/release unknown → `outcome unknown; check the task in Task&I: <code>`. Capabilities failures inside complete/release are not wrapped (nothing was sent for the write).
6. **open_children** recognised only for `complete` with exactly `{error, children[1..200 of {task,title}]}`; otherwise unknown.
7. **UUID lower-casing** applied to every user-typed ref (`--task`, payload `task`, `VIBE_TASK_REF`, `.vibe/taskandi-task`), not to `root` or server ids.
8. **ABBR check precedes the usable-id check** (so `ABBR-12`, which is a syntactically usable id, gets the ABBR message).
9. **`--task` outside acceptance** (non-null effective task, neither claimed nor effective) → exit 1 `task is neither the bound task nor the claimed task`. For complete/release the claim check comes first.
10. **Token/connection/origin/workspace** are non-enumerable on the config object so no JSON print shows them. `lastGrade` is stored raw.
11. `status` keeps `cursorSequence` (MCP field) for "as today".

## Commands (all foreground)
- `python3 code-check.py` → exit 0
- `python3 smoke/checks_28_taskandi_client.py` → exit 0
- `python3 smoke/checks_29_taskandi_binding_usage.py` → exit 0
- `python3 smoke/checks_47_taskandi_contract_v2.py` → exit 0
- `node .vs/cycle-1/scratch-tests/test-wire.mjs` → 70 passed (AC2, AC3, AC5, AC5b, AC6)
- `node .vs/cycle-1/scratch-tests/test-errors.mjs` → 181 passed (AC4, AC13; one earlier run hit an unexplained enqueue miss, three reruns clean)
- `node .vs/cycle-1/scratch-tests/test-state.mjs` → 127 passed (AC1, AC7–AC12, AC16–AC18)
- `python3 smoke-test.py < /dev/null` → exit 1, one failure, in the Tester's in-progress `checks_52`: "AC11: a 60 s run ending 1 s in the future". Test timing bug: it computes `now` in Python, then runs several enqueue subprocesses before this one, so by the time Node checks, `floor_sec(now)+1000` is already past. The client check is `started_at + seconds*1000 > Date.now()` → refuse (no slack). The fix belongs in the test: compute `now` immediately before that enqueue, and/or use a margin of several seconds. Every other check, including all other checks_50/52 tests, passed.
