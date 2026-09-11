# task_048 — Generator report (cycle 1)

Branch `astra`. Nothing committed, nothing pushed.

## Files

New (untracked):

- `devcontainer/codex-supervisor.mjs` — the supervisor (Node ESM, node builtins only).
- `.vs/cycle-1/scratch-tests/stub-codex.py` — scratch stub `codex` whose `app-server`
  mode speaks the wire format from `$CODEX_HOME/scenario.json` and records argv, the
  env key set and every received message to `$CODEX_HOME/record.jsonl`.
- `.vs/cycle-1/scratch-tests/drive.py` — scratch driver: 20 scenarios / 116 assertions
  covering every AC10 case. Generator-side TDD only; the shipped tests
  (`smoke/checks_19_codex_supervisor.py`) are the Tester's, and nothing under `smoke/`
  was touched.
- `.vs/cycle-1/generator-report.md`, `.vs/cycle-1/diff.patch` (this report and the diff).

Changed (tracked):

- `devcontainer/Dockerfile` — `COPY --chown=root:root codex-supervisor.mjs
  /usr/local/bin/codex-supervisor` next to the task_046 root-owned scripts, and
  `/usr/local/bin/codex-supervisor` appended to the existing `RUN chmod +x` chain.
- `devcontainer/commands/vsss.md` — AC9 (see below).
- `README.md` — one paragraph, "The unattended supervisor", in the Codex section.
- `docs/codex-integration-plan.md` — D7 rewritten with the verified method names.

## Per-AC coverage

- **AC1 CLI.** `run` and `status` subcommands with every listed flag; `--cwd` must be
  absolute, a directory, and inside a git work tree (`git -C <dir> rev-parse
  --is-inside-work-tree`); the prompt file is read once; defaults exactly as specified
  (state `<cwd>/.vss/codex-supervisor.json`, 50/20/12/6/3/36000). Numeric flags accept
  only `^\d+$`. Every invalid argument path exits 2 before anything is spawned (driver
  `test_status_and_usage` asserts nine invalid argvs plus "no record file written").
- **AC2 Prefix rewrite.** `REWRITES = {'/vs':'$vs','/vss':'$vss','/vsss':'$vsss'}` is
  exported; the first token is the text before the first whitespace (or the whole
  string), matched exactly and case-sensitively. Driver exercises all ten cases through
  the CLI against the stub's echoed `turn/start` input: `/vs`, `/vss`, `/vsss`, `$vs`,
  `/vss:foo`, `/VS`, `/vssx`, bare `/vsss`, a plain prompt, and a leading-space prompt.
  Trailing whitespace in the prompt file is stripped before sending (documented choice —
  a prompt file usually ends in a newline); the `promptHash` is sha256 of the file's raw
  bytes, so the identity check is reproducible with `sha256sum <prompt-file>`.
- **AC3 Spawn and handshake.** `spawn(codexBin, ['app-server'])`, child `env` built from
  scratch with exactly `PATH`, `HOME`, `CODEX_HOME`, `LANG` (asserted: the stub records
  `sorted(os.environ)` == `['CODEX_HOME','HOME','LANG','PATH']`). `CODEX_HOME` defaults
  to `$HOME/.codex` and must exist as a directory or the run exits 2 *before* spawning.
  The first line is `{"id":1,"method":"initialize","params":{"clientInfo":{"name":
  "vibe-codex-supervisor","version":"<VERSION>"},"capabilities":{}}}` (key order is the
  literal object-literal order). 30 s timeout → exit 1 `handshake timeout`. `account/
  rateLimits/read` is id 2 and is sent before any turn (asserted on the recorded method
  order). The server's working directory is deliberately NOT changed — the workspace
  travels in `thread/start.cwd`.
- **AC4 Thread lifecycle and state.** First run: `thread/start {cwd, approvalPolicy:
  "never", sandbox:"danger-full-access", ephemeral:false}` (plus `model` only when
  `--model` is given), then the exact state object from the spec written atomically
  (`<state>.tmp` + `rename`) before the first `turn/start`. A matching state file
  (`cwd` AND `promptHash`) → `thread/resume {threadId}`, `resumes += 1`, then a fresh
  `turn/start`; never `turn/steer`, never `thread/fork` (asserted). A mismatch names
  which field mismatched and exits 2; `--new-run` renames the old file to
  `codex-supervisor.<old startedAt>.json` in the state dir and starts fresh. Every
  counter change is persisted immediately (`persist()` after each mutation).
  Documented choice: after a resume the supervisor re-sends the run's own
  (rewritten) prompt text, not `continue` — a hard-killed turn recorded nothing, and
  the prompt is the only text the supervisor can reconstruct from its own state.
- **AC5 Turn loop.** `turn/start {threadId, input:[{type:'text',text}]}`; notifications
  drained until `turn/completed` for that `turnId`; `error` with `willRetry:true` logged
  and ignored; `item/agentMessage/delta` appended verbatim to
  `<state dir>/codex-supervisor.log`; `account/rateLimits/updated` merged per window
  (a window is replaced only when present and non-null in the update). Outcomes:
  completed → record + gates; `usageLimitExceeded`/`rateLimitExceeded` → quota;
  `serverOverloaded`, `httpConnectionFailed` with `httpStatusCode` 429,
  `responseStreamConnectionFailed`, `responseStreamDisconnected`,
  `responseTooManyFailedAttempts` → transient ladder 60/120/240/480/960/1920 (cap 3600);
  `sessionBudgetExceeded`/`contextWindowExceeded` → exit 1 naming it; any other error →
  `turnFailures += 1` and the SAME text re-sent until `--max-turn-failures`, then exit 1
  quoting the last message; `interrupted` → exit 1, never auto-restarted. Every
  server→client request is answered immediately with
  `{"id":<id>,"error":{"code":-32601,"message":"unattended"}}` and logged — the driver
  fires all six named methods in one turn and asserts six answers and a clean exit 0.
- **AC6 Quota path.** Binding window = the one at `usedPercent >= 100` (later `resetsAt`
  if both), else the later `resetsAt`; wait `resetsAt + 120 - now`; with no known
  `resetsAt`, 300/600/1200/2400 (cap 3600) with a fresh `account/rateLimits/read` before
  each retry (blind branch only, so the timed branch's message sequence stays minimal).
  `quotaWaits += 1`, the wait appended to `waits` as `{reason, seconds, until}` and
  persisted BEFORE sleeping, then the same text re-sent. `--now-source` replaces the
  clock (re-read on every `now()`) and turns sleeps into no-ops that still advance a
  virtual offset, so durations are recorded and a wall-clock ceiling can be reached
  inside a wait. Quota waits never touch `resumes` (asserted).
- **AC7 Gates and exit.** `checkGates()` runs after a completed turn, before every
  quota/transient wait, before every re-send, and once on the loaded state before the
  server is spawned or resumed; it raises exit 3 naming the ceiling
  (`max-turns`/`max-resumes`/`max-quota-waits`/`max-transient-retries`/
  `max-wall-seconds`, the last measured from `startedAt` with waits included). Exit 0
  when the LAST completed `agentMessage` of the turn contains `^VSSS-EXIT:` at line
  start (tracked from `item/completed`, falling back to the last `agentMessage` in
  `turn.items`); `exitReason` is written to the state file. Otherwise the next turn is
  the literal `continue`. `status` prints an aligned label/value table and exits 0;
  a missing or unparseable state file prints `no run` and exits 1.
- **AC8 Safety.** No `--dangerously-bypass-approvals-and-sandbox`, no `-c` (argv is
  exactly `['app-server']`), no read of `auth.json` anywhere, writes confined to the
  state file, its `.tmp`, the `--new-run` archive and `codex-supervisor.log` (the driver
  asserts the workspace contains only `.vss/codex-supervisor.{json,log}`), and the only
  texts ever sent are the rewritten prompt and `continue`. SIGTERM/SIGINT close the
  server's stdin (EOF is the documented stdio shutdown), persist the state and exit 130;
  the driver kills a run mid-turn and the next run resumes the same thread.
- **AC9 Docs.** `vsss.md` § "Reporting back at exit" now ends with the requirement that
  the report's LAST line is `VSSS-EXIT: <exit reason in a few words>`, in every runtime;
  § "Running under Codex" gained three lines (7 non-blank lines total, within the
  existing `checks_18` ≤ 8 cap) naming `codex-supervisor`, the `continue` re-entry and
  the stop condition. README's Codex section gained the "The unattended supervisor"
  paragraph. Plan D7 rewritten with verified names (see below).
  **Word-budget note:** the shipped `vs.md+vss.md+vsss.md ≤ 14,300` cap (pinned in
  `checks_05`, `checks_09`, `checks_13`) had 11 words of headroom, so the additions were
  paid for by compressing rationale prose in `vsss.md` (resumption preamble, session-file
  paragraph, fromto rationale, "Why /vsss exists", the exit-report preamble, one
  resumption branch). No rule, flag, sentinel or asserted phrase was removed — total is
  now 14,289. One rewrap detail worth knowing: `checks_05` matches the literal
  `never be reported as a perfection gate`, so that phrase must stay on ONE line.
- **AC10 Tests.** Out of scope for the Generator, but every listed scenario was driven
  through the real CLI first (`.vs/cycle-1/scratch-tests/drive.py`, 116 assertions).
- **AC11** `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null` fully green.

## Protocol facts looked up (source, tag `rust-v0.154.0`)

All paths under `scratchpad/codex-src/codex-rs/`.

| Fact | Where |
|---|---|
| Method names `initialize`, `thread/start`, `thread/resume`, `turn/start`, `account/rateLimits/read` and the six server→client request methods | `app-server-protocol/src/protocol/common.rs:507,552,558,1010,1272,1728-1759` |
| Notification names `turn/completed`, `item/started`, `item/completed`, `item/agentMessage/delta`, `error`, `account/rateLimits/updated` | `common.rs:1881,1908,1912,1917,1922,1945` |
| `SandboxMode` is kebab-case → `"danger-full-access"` | `protocol/v2/shared.rs:303-309` |
| `AskForApproval::Never` is kebab-case → `"never"` | `protocol/v2/shared.rs:174-192` |
| `ThreadStartParams` field names (`cwd`, `approvalPolicy`, `sandbox`, `ephemeral`, `model`, `config`) | `protocol/v2/thread.rs:62-130` |
| `ThreadStartResponse.thread.id`; `TurnStartResponse.turn` | `protocol/v2/thread.rs:181`, `protocol/v2/turn.rs:268` |
| `Turn{id, items, status, error, ...}`; `TurnStatus` camelCase `completed/interrupted/failed/inProgress`; `TurnError{message, codexErrorInfo, ...}` | `protocol/v2/thread_data.rs:386-436`, `protocol/v2/turn.rs:31-37` |
| `CodexErrorInfo` externally tagged camelCase; unit variants bare strings; `httpConnectionFailed`/`responseStream*`/`responseTooManyFailedAttempts` carry `{httpStatusCode: Option<u16>}` (so they can arrive as `{"name":{"httpStatusCode":null}}` — both shapes classified) | `protocol/v2/shared.rs:70-120` |
| `ThreadItem` is `#[serde(tag="type")]` camelCase, so an agent message is `{"type":"agentMessage","id","text"}` | `protocol/v2/item.rs:230-260` |
| `ItemCompletedNotification{item, threadId, turnId, completedAtMs}` | `protocol/v2/item.rs:1399-1406` |
| `ErrorNotification{error, willRetry, threadId, turnId}` | `protocol/v2/notification.rs:62-69` |
| `RateLimitSnapshot{primary, secondary, ...}` sparse rolling update; `RateLimitWindow{usedPercent, windowDurationMins, resetsAt}` with `resetsAt` Option<i64> in UNIX SECONDS | `protocol/v2/account.rs:585-600,673-679` |
| `GetAccountRateLimitsResponse.rateLimits`; params fully optional | `protocol/v2/account.rs:320-346` |
| NDJSON framing, no `jsonrpc` field | `app-server-transport/src/transport/stdio.rs:42-92`, `app-server-protocol/src/rpc.rs:31-79` |
| stdin EOF shuts the stdio server down | `app-server/src/lib.rs:733,1042,1061-1064` |
| `CODEX_HOME` must already exist | `utils/home-dir/src/lib.rs:13-51` |
| `codex app-server` accepts `-c`, `--listen`, … (we pass none) | `app-server/src/main.rs:30-68`, confirmed live with `codex app-server --help` |

Two implementation consequences worth flagging to the Tester: `resetsAt` is
`Option<i64>`, and `Number(null)` is `0` in JS — the first draft treated an absent reset
as "now" until the driver caught it; the fix is an explicit null/undefined guard in
`bindingResetsAt`. And `httpConnectionFailed` is treated as transient only at status
429, per AC5's literal list; other status codes fall to the generic turn-failure path.

## Commands run

- `python3 .vs/cycle-1/scratch-tests/drive.py` → 116 checks passed, 0 failed
  (run red first: the initial version failed 3 checks — the `resetsAt: null` bug above
  and a stub-rewind artefact in the driver).
- `node -e "import('./devcontainer/codex-supervisor.mjs')"` → imports cleanly, exports
  `REWRITES`, `rewritePrompt`, `classifyError`, `mergeRateLimits`, `bindingResetsAt`,
  `backoffSeconds`, `exitReasonFrom`, `parseArgs`, `statusReport`, `main`, exit-code
  constants; the CLI does NOT run on import (`import.meta.url` vs `process.argv[1]`,
  realpath-compared so a symlinked `/usr/local/bin/codex-supervisor` still runs).
- `codex app-server --help` (no model contacted).
- `python3 code-check.py` → shellcheck clean across 22 files.
- `python3 smoke-test.py < /dev/null` → all checks passed (foreground, 600 s timeout).

## Not done / notes for the Evaluator

- AC10's `smoke/checks_19_codex_supervisor.py` and its `smoke/runner.py` registration are
  the Tester's; nothing under `smoke/` was touched.
- `clientInfo.version` resolves from `<script dir>/../VERSION`, falling back to
  `/usr/local/share/vibe/VERSION` and then `0.0.0`. In the repo (where the tests run) it
  is the real `VERSION`; inside the image it is `0.0.0` today, because the Docker build
  context is `devcontainer/` and the repo's `VERSION` is outside it. Shipping the version
  into the image would need a new COPY source under `devcontainer/` — out of scope here,
  flagged for item 7.
- Control requests (`initialize` aside) use a 30 s response timeout; the spec only
  mandates the handshake one.
- A child exit while the supervisor is waiting rejects with exit 1 rather than hanging.
