# task_065 spec critique (Spec Critic, rigorous, --plain)

Verdict: REVISE. The shape is right (rules as code in `decide`, prose only sequences commands), but `decide` as drafted does not implement the agreed rule safely in several corners, the budget rule cannot work with what vibe posts, the loop can spin, and the parity test is built on a wrong premise (four files, "pre-existing lines" that exist in only one of them). Eleven BLOCKING items below; the rest are MINOR.

Facts I checked in the tree and the brain2 notes:
- `devcontainer/commands/vss.md`, `vsss.md`, `codex/skills/vss/SKILL.md` and `codex/skills/vsss/SKILL.md` contain NO `taskandi`/`Task&I` text today. Only `codex/context.md` does: line 7 (a negative "do not require ... Task&I") and the whole `## Optional Task&I Action Window` section (lines 27-33, v1 `to` shape, "unless `.vibe/taskandi.json`").
- Both Codex skills are one-line delegations ("Read `/usr/local/share/vibe/commands/vss.md` now, in full, and follow it"). They inherit whatever `vss.md` says. The task statement names five files; the draft's parity test and AC9 say "four".
- `vsss.md` writes questions to fromClaude at several sites (lines ~141-146 "a question is not an exit condition", ~213 question format, ~274 ambiguous parallel plan, ~284 `--spec-first` approve checkpoint), and has a "consume protocol" at the start of every iteration.
- In the existing client, `job.result` is stored only for `ask` and only on the v2.1 revision (`taskandi-client.mjs` line ~539); `doneAt` is set on done. task_064's spec says the v2.2 `ask` response is validated but does not pin that `result.ask_id`, `payload.reversible/blocking/remaining_minutes` and `doneAt` survive in `state.json`, nor that the `record_usage` response's `spent` is kept.
- `taskandi-usage.mjs` posts per-snapshot deltas keyed by session+model+cumulative counts, attributing everything not yet imported to whatever task is passed.

---

## Concerns

### 1. BLOCKING — `decide` misclassifies answered asks (rule: "agents never act on an unseen default", 10.3)
The draft says "answered asks are handled by `poll`" and leaves `decide` silent on them. Two live cases break the safety rule:
- **Answer landed between `poll` and `ask_status`.** `ask_status.answered: true`, poll has not returned it. If `decide` only looks at `seen_at`/`deferred`, it can emit `proceed` on the default while an answer exists.
- **Non-owner answer.** `ask_status.answered` is true, but `poll` filtered it (`owner_answer: false`, counted in `ignored`). The ask is still unanswered for vibe, yet `ask_status` cannot say who answered. The draft leaves it neither `wait` nor `park` (deadlock: `next: work` forever) and, worse, could let it be treated as resolved.

Fix: "open" is defined from the outbox, not from `ask_status`: an ask is open iff the outbox has a `done` ask job with an `ask_id` and no stored owner answer for `(task, ask_id)`. For an open ask whose `ask_status.answered` is true, `decide` emits `action: "wait"`, `why: "answered-not-yet-polled"`, plus a top-level `"repoll": true`; it never emits `proceed` for it. If that persists for a second `decide` after a poll returned no owner answer for it (non-owner), emit `park`, `why: "answered-by-non-owner"` once other work is out. A missing ask in `ask_status` is `why: "unknown-ask"`, never proceed.

Proposed AC: "Fixture: ask A open, `ask_status` says `answered:true`, outbox has no owner answer. `decide` returns action `wait`/`why answered-not-yet-polled` with `repoll:true` even when all four proceed conditions hold. With `--no-other-work` and a second call after an empty poll it returns `park`/`answered-by-non-owner`. With an owner answer stored for A, A does not appear in `asks`. An ask absent from `ask_status` never yields `proceed`."

### 2. BLOCKING — nothing stops `proceed` repeating, and the proceed protocol is unspecified
Writes are not idempotent. The ask stays open in Task&I after the agent proceeds on its default, so every later boundary `decide` says `proceed` again and the harness posts another comment. Also the agreed rule requires the agent to "say so in the thread" and the work to land provisional/flagged; the draft's prose never says to post that comment, and does not say what to record so an answer arriving later is applied as a re-rule.

Fix: add `decide --resolve <key> --as proceeded|parked` (or have `enqueue comment` with a reserved key do it) that writes a `resolved` ledger entry `{task, ask_id, as, at}` into the outbox state. `decide` omits resolved asks from `asks` (or marks `resolved:true`, action `done`), so `proceed` is emitted at most once per ask. Prose for `proceed`: (1) enqueue one comment `Proceeding on the default for ask <ask_id> (owner opened it, latest start passed): <default>`, key `<session>-proceed-<ask_id>`; (2) `decide --resolve`; (3) record in the iteration Notes; (4) late owner answer is applied as a re-rule through `poll` as today.

Proposed AC: "Two consecutive `decide` calls with all four conditions holding: the first returns `proceed`; after `decide --resolve <key> --as proceeded` the second does not list the ask. Prose block contains the proceed-comment step and the resolve step (string check on the `decide --resolve` command). A later owner answer for a resolved ask still appears in `poll` output."

### 3. BLOCKING — `wait` with nothing else to do is undefined; the 30-minute park delay cannot be waited out
The agreed rule says: conditions fail, then park (keep the ask open, one comment, release, take the next task). The draft adds `VIBE_TASKANDI_PARK_AFTER_MIN` (default 30) and a model-supplied `--no-other-work` flag. If the model has no other work and the delay has not elapsed, `decide` returns `wait` and the prose gives no action: `vsss.md` says "waiting is not a state you can occupy", Codex has no `ScheduleWakeup`, so the model either spins, polls hot, or improvises. `--no-other-work` is also a subjective assertion by the model, so the park logic hangs on the very thing the code was meant to replace.

Fix: drop the delay and the knob. `decide --no-other-work` returns `park` immediately for any blocking ask that is not `proceed`. Without the flag, a blocking ask is `wait` (keep working on other parts). Tell the model what "other work" means: remaining items of the current task that do not depend on any open blocking ask's answer; the model states it by passing the flag. Also order `why` precedence exactly (test-pinned): `answered-not-yet-polled`, `unknown-ask`, `unseen`, `no-deadline`, `before-latest-start`, `defaults-off`, `irreversible`.

Proposed AC: "`decide` without `--no-other-work`: every non-proceed blocking ask is `wait`. With it: every non-proceed blocking ask is `park` with the first failing `why` in the pinned order (one test per why, plus one with two conditions failing to prove precedence). No env knob exists for park delay (grep of the client for `PARK_AFTER` is empty)."

### 4. BLOCKING — release/claim loop in `/vsss`
After `park-task` the draft does `release` then `next-task`. Task&I may well hand back the same task (it is still top-ranked; nothing says a task with an open blocking ask is ineligible; likewise an over-budget task after `stop`). The loop then claims, polls, parks, releases, with a comment and a lease call each turn, burning tokens until a hard stop. Same hazard after a resumed window.

Fix: the client keeps a `parked` ledger entry `{task, openAskIds, budgetStopped}` on `release` made via the harness. The prose rule: after `next-task` returns a task, run `poll`; if the claimed task is in the ledger with the same open ask set, no new owner answer, and (for budget stop) no larger allowance than recorded, `release` it again WITHOUT working, and count it as a no-op iteration (so the existing "three no-op iterations" exit fires). Alternatively `next-task` prints `"reclaimed_parked": true` for the model. Either way it must be code-computed, not remembered by the model across context resets.

Proposed AC: "Stub server returns the same task from `next_task` after a park. The second claim's output (or `decide`) reports `reclaimed_parked:true`; with a new owner answer in between it reports false. Prose names the no-op counting rule."

### 5. BLOCKING — the budget rule cannot meter `windows`, and the `tokens` metric and freshness are undefined
Spec 10.4 and the brief say vibe raises a question at ~80% and stops at the cap. In the draft:
- **windows**: task_064 pins `record_usage.windows` to always 0. `spent.windows` therefore never moves from vibe's own posting. For an allowance `{windows: 3}`, `ratio` stays 0 forever and the cap never fires: a silent non-enforcement of the one thing 10.4 exists for. (An allowance of `{}`, `windows` only, or `tokens` plus `windows` all hit this.)
- **tokens**: `spent.tokens` is Task&I's roll-up, but nothing says what it sums (input+output? plus cache read/write? vibe posts all four, and cache reads dominate real transcripts). If vibe's idea of "tokens" differs from Task&I's, the ratio is wrong by a large factor either way. This needs an answer from the taskandeye session before the generator starts; the fixtures README does not say.
- **freshness**: the only `spent` the client holds is the claim's, taken at `next_task`. Usage posts during the run do not update it unless the client stores the `record_usage` response (`{task, spent}`). A ratio from claim-time `spent` lags the whole run. Queued or uncertain `record_usage` jobs (flush failed) are also invisible.
- A zero allowance (`{windows: 0}` is valid) divides by zero (and `0/0` is NaN); `ratio` must be a JSON number or null, never Infinity.

Fix:
- Windows: `decide --windows-used <n>` where the harness supplies the number of 5-hour windows this run has spent on the task (from the `/vsss` session file, 1 for `/vss`); `ratio_windows = max(spent.windows, n) / allowance.windows`. If the harness cannot supply it (Codex, no marker), the dimension is reported as `unmetered` and `budget.why` says `windows-unmetered`; documented as "enforced only for tokens". Pick one and test it.
- Tokens: pin the metric with taskandeye (record it in the spec as a cited fact; if unanswered, define `tokens = input + output` in vibe's accounting and say Task&I must agree, with a MANUAL-TESTS check against a real roll-up).
- Freshness: the client stores `claim.spent` and `claim.spentAt` from every successful `record_usage` response; `decide` uses the newest, and adds the token sum of `queued`/`uncertain` `record_usage` jobs for the task, reporting `budget.pending_tokens`.
- Allowance `0` on a dimension: ratio `1`, action `stop`, `why: "zero-allowance"`. Ratio is clamped for display, with `ratio_raw` omitted.

Proposed AC: "Table-driven `decide` budget tests: allowance null -> continue/no-allowance; `{}` -> continue/no-limits; tokens 79%, exactly 80%, 99%, 100%, 250% -> continue, ask, ask, stop, stop; `{windows:3}` with `--windows-used 3` -> stop, and without the flag -> continue with `why windows-unmetered`; `{windows:0}` -> stop/zero-allowance; both dimensions use the larger ratio; after a `record_usage` flush returning `spent.tokens` X, `decide` uses X (not the claim value); a queued `record_usage` job's tokens are added and reported in `pending_tokens`. No NaN/Infinity ever appears in output (JSON parse of every case)."

### 6. BLOCKING — the budget ask as drafted would be a blocking ask and would park the task
The draft enqueues the budget ask with `reversible: true`, default "stop at the cap" and says nothing about `blocking`. The client default is `blocking: true`. At 80% the ask then enters `decide`'s own per-ask loop, fails `no-deadline` (no deadline up the tree is the common case), and with `--no-other-work` parks the task at 80% spent: the opposite of "continue until the cap". Also "default stop at the cap" for a `proceed` would mean stopping.

Fix: the budget ask has `blocking: false`, `reversible: true`, `estimate_minutes` small, `remaining_minutes` taken from the harness, and is excluded from the per-ask loop by its reserved key (`budget-<task>`; deterministic, so a crashed-then-repeated enqueue dedupes on key+payload). "Already sent" means a job with that key exists in ANY state (`queued`, `uncertain`, `refused`, `done`): an `uncertain` one is not re-asked automatically. State what an answer means: it cannot raise the cap (the allowance belongs to the owner in Task&I); the model treats the answer as guidance (for example "wrap up now"); the stop at ratio >= 1 is unconditional until a later `next-task` shows a larger allowance. Spec 10.4 says "most of the allowance is spent **with work outstanding**": the draft drops the second half. Add `--remaining-minutes <n>` (0 = nothing outstanding): `ask` only when n > 0.

Proposed AC: "`decide` at ratio 0.85 with `--remaining-minutes 30` returns `budget.action ask` and `budget.key budget-<task>`; with `--remaining-minutes 0` returns `continue/nothing-outstanding`; after the budget ask job exists in each of the four states, `decide` returns `continue` (never `ask`) below 1 and `stop` at >= 1. The budget key does not appear in `asks`. The prose block states `blocking false` for the budget ask and that the cap is not raised by an answer."

### 7. BLOCKING — `decide`'s inputs are not guaranteed to exist in the task_064 client
Item (2) of the brief. `decide` needs per ask: `reversible`, `blocking`, `default`, `remaining_minutes`, `ask_id`, flush time; per claim: `defaults_allowed`, `hardDeadline`, `latest_start`, `allowance`, `spent`, `lease`. task_064 pins none of the storage, and task_064 is being built now by a generator who will not know slice 4 exists. Specifically: (a) `job.result.ask_id` is stored for v2.1 only today; (b) `job.payload` for a `done` ask may be pruned; (c) `doneAt` is a string today, not ms; (d) `claim` is replaced wholesale by each `next-task`, so a re-claim drops `hardDeadline` of the old task, and `decide --task X` for a non-claimed task has no deadline data; (e) an `uncertain`/`refused` ask has no `ask_id`, so `decide` cannot judge it.

Fix: add a short "Storage contract" to this spec and a regression test in this task (not 064) that fails if 064's output lacks them: state.json job for a flushed v2.2 ask has `result.ask_id`, `result.placed`, `payload.{reversible,blocking,default,remaining_minutes}` and `doneAt`; the claim holds the whole validated next_task object plus `spent`/`spentAt`; asks that are not `done` are excluded from `decide.asks` and listed in `decide.unjudged: [{key, state}]`. `decide` works only on the claimed task; other `--task` values exit 1 `decide needs the claimed task`. Tell the 064 owner now (it is in flight): either ask them to guarantee it, or let 065 patch the stores in a dependent commit.

Proposed AC: "After flushing a fixture ask under a descriptor binding, `state.json` contains the listed fields (asserted by key). `decide` with a queued ask lists it in `unjudged` and never in `asks`. `decide --task other` exits 1 with that exact message, zero requests."

### 8. BLOCKING — no failure table; a failed `decide` must never be able to cause a default-proceed
The draft covers only "flush leaves an ask queued/uncertain/refused". Every other command can fail (exit 1, capabilities mismatch, refusal, outcome unknown, timeout), and the prose gives no step for any of them. Also "binding file present but invalid" is a refusal in 064 ("never fall back to unbound"), while the block says "skip unless the file exists": a broken descriptor makes the model skip the whole feature silently and use the files, or run it and fail on every command with no instruction.

Fix: add a table the block must reproduce. Minimum content:
- `taskandi-client status` is the detection step (not "does the file exist"). `bound:false` -> skip the block. Exit 1 (invalid or two bindings) -> use the file channel for this run, write ONE fromClaude item saying the Task&I binding is broken and quoting the status message.
- `next-task` exit 1 -> TODO.md as today, note "next-task failed: <message>" in the session file. `task:null` -> TODO.md as today, note "Task&I had no task" (two different notes: confirm with Martin that "no assigned task" should fall back to TODO.md in a bound project; this is a product decision the draft makes silently).
- `enqueue comment|usage|record_time` or `flush` failing -> leave queued, continue, note once per run, never block work.
- `poll` failing -> no answers applied this boundary, continue.
- `decide` exit 1 or unparsable JSON -> treat every ask as `wait`, never `proceed`; with no other work and `release` working, release with reason "Task&I decision unavailable"; otherwise end the iteration as no-op.
- `complete`/`release` outcome unknown -> do not retry; note it; the claim is kept by the client; continue to the next iteration without claiming a new task until `reconcile` evidence or a user look (state the rule).
- Lease lost (`not_assigned`, `lease_held`, `stale_context` on a write for the claimed task) -> stop work on that task, commit what exists, note it, take the next task.
Make `decide`'s own degradation explicit: an `ask_status` failure should not kill the offline budget half. `decide` then exits 0 with `"degraded":"ask_status"`, every ask `wait`/`why status-unavailable`, budget still computed. Other failures (no claim, capabilities mismatch) exit 1.

Proposed AC: "`decide` with ask_status returning 500: exit 0, `degraded:"ask_status"`, no ask is `proceed`/`park`, budget block present. `decide` with no claim and no `--task`: exit 1, the no-bound-task message, empty stdout. `decide` unbound: exit 0, stdout `{"bound":false,"channel":"file-fallback"}`. The block contains a failure table naming each command above (string check for each `exit 1` row)."

### 9. BLOCKING — session id, transcript identity and the ordering of usage vs task switches are unspecified (misbilling)
The prose says `--session <session id>` and `usage --transcript <this session's jsonl>`. A Claude model has no machine-readable "session id" or "this session's jsonl" in any instruction. A wrong guess (the newest file in `~/.claude/projects/-workspace/`, which may belong to another concurrent session, or a subagent) bills someone else's tokens to the task, and keys derived from it collide across runs. Also the importer attributes every not-yet-imported snapshot to the task you pass; if usage is imported after `release`/`complete`/`next-task`, the previous task's tokens land on the next task, which corrupts `spent` and so the budget.

Fix: name the session id: the `/vss`/`/vsss` start stamp from the session file name (`2026-10-30T20-58-02Z`; matches the `next-task --session` regex; stable across resumption because vsss restores from the session file). Name the transcript source per runtime (Claude: the path the Stop hook or `CLAUDE_*` env provides; Codex: the rollout path the supervisor already knows) or, if none is reliable, say usage posting is skipped and `budget.why` becomes `usage-unavailable`. Pin the order at every boundary: `usage` -> `flush` -> then (and only then) `complete`/`release`/`next-task`. Give the key scheme in a table (the draft's `--key <session>-T<n>` leaves `n` undefined and a re-run after resume would collide with a different payload):

| call | key |
|---|---|
| ask | `<session>-ask-<sha256(task+question)[:12]>` (same question, same key, safe dedupe) |
| progress comment | `<session>-i<n>-comment` |
| time | `<session>-i<n>-time` |
| proceed/park comment | `<session>-proceed-<ask_id>` / release reason |
| budget ask | `budget-<task>` |

and say `n` is the session-file iteration number (so a resumed window reuses it). `record_time`: give `started_at` (iteration start) and `seconds` (active time, capped; a quota wait spanning a window reset must not be counted, or estimates get corrupted).

Proposed AC: "Block names the session-id source and the exact `usage` argv; a test extracts every `taskandi-client` command line from the block, substitutes sample values for `<...>`, and runs each through the client's argv parser in a no-network mode (`--check-argv` or equivalent) expecting exit 0. A mechanical check asserts `usage` and `flush` precede `complete`, `release` and `next-task` in the block."

### 10. BLOCKING — unbound-parity test is built on a wrong premise
The draft asserts for "each of the four files" that no line outside the block mentions Task&I "except lines already present before this task". In reality:
- Four of the five files have no Task&I text, so the exception list is empty and the test should assert zero, baseline-free. Only `context.md` has pre-existing lines, and most of them (the whole section at lines 27-33) are not "a line", they are an entire v1 section that AC11 says must change.
- The skills delegate to the commands; adding a block to them duplicates the flow and drift is certain. The draft's AC9 says "four files" while the task lists five.
- "First sentence" is not mechanically checkable; "markers" can nest or be unbalanced; the marker lines themselves contain `taskandi`.

Fix, baseline-free:
- `vss.md`, `vsss.md`, both `SKILL.md`: the number of lines matching `/taskandi|task&i/i` outside the block is exactly 0. The skills contain no block at all (they inherit from the command via "read in full"), and the test asserts they still say so. This is robust: any later Task&I text outside a block fails with no baseline list.
- `context.md`: replace the old `## Optional Task&I Action Window` section by the new block (so there is one Task&I region), and allow exactly one line outside it, selected by a regex that states its meaning (a line containing `do not require` or `Do not require` followed by `Task&I`), not by exact content, so a harmless reword does not fail. All other occurrences outside the block fail.
- Block grammar: exactly one start and one end marker, each alone on its own line, start before end, no marker text inside the block, the first non-blank line after the start marker equals the exact skip string (fixed in the spec), and the last non-blank line before the end marker exists.
- Detection step in the skip string is `taskandi-client status` printing `bound:false` or the invalid-binding case from concern 8, not "does a file exist" (which differs from the client's own binding rules).

Proposed AC: "For `vss.md` and `vsss.md`: exactly one well-formed block; first non-blank line inside equals `<exact skip text>`; zero `/taskandi|task&i/i` lines outside the block (case-insensitive). For both `SKILL.md`: zero such lines anywhere and the delegation sentence is intact. For `context.md`: exactly one block, and every match outside it is on a line matching `/not require.*Task&I/i`; the old `to`-shaped ask text (`containing \`to\``) is absent anywhere. A control test: copying `vss.md` with an added `Task&I` line outside the block fails the checker."

### 11. BLOCKING — what task does the session work: `next-task` vs `VIBE_TASK_REF`, `vibe link`, and explicit args
`vibe link` (task_062) opens a session on a specific task via `VIBE_TASK_REF` / `.vibe/taskandi-task`. `next_task` has no `task` parameter: it returns the top eligible task for the agent, which may be a different one. The draft says nothing, and says nothing about Mode B (`/vss <args>`) either. Without a rule the model will either ignore the link or claim an unrelated task.

Fix (pick and test): with explicit args, the user's args are the work; `next-task` is not called; asks/comments/usage target the effective task (target resolution in 064) if there is one, else the file channel for that run. In A-mode with an effective task set by `vibe link`, call `next-task`, and if the returned task is not the effective one, `release` it immediately (reason "session opened on <effective>") and use the effective task as target without a claim only for asks and comments (no `complete`/`release` possible per 064 target resolution), so completion is reported as a comment. State this limitation; if Martin wants link-opened sessions to work the linked task for real, Task&I needs `next_task {task}` (v2.3 item). Record that as an open question in `vibe-fromClaude.md`.

Proposed AC: "Block has one paragraph for args mode and one for effective-task mode; `next-task` does not appear in the args-mode paragraph (string check on the paragraph). MANUAL-TESTS Test 70 includes a `vibe link` launch."

---

### 12. MINOR — the four conditions, exact mapping (what is right, what to tighten)
Mapping the draft against the agreed rule (brief, v2.1 amendment 1, plus v2.2) and 10.3:
- (a) seen or deferred: correct. State that `deferred` is always false today (README); the code must still honour it when true.
- (b) latest start passed, needing a hard deadline: correct in outline. Pin: `latest_start` (ms, never sent today) wins if present; otherwise `hardDeadline - remaining_minutes*60000` using THAT ask's own `remaining_minutes`; with neither, never. "Passed" is `now >= latest_start`, inclusive; a deadline already in the past counts as passed. Clock: `now` is local; Task&I stamps are server ms; allow a seam (`createClient({clock})`) for tests and note skew can only delay (tests must not read the wall clock). If both sources exist and disagree, use the later (more conservative); state it.
- (c) policy: `defaults_allowed` from the claim, which can be stale for a long run; also note it is always false until Task&I wires Strategy, so every proceed path is dead code in production for now: the tests carry the load, and MANUAL-TESTS must not claim a live proceed.
- (d) reversible: from the outbox payload; correct.
- 10.3 "no deadline on questions": nothing in the draft sends one. Add a negative test that the enqueue payload for a prose-built ask contains no `due`/deadline key (064 already forbids; assert the block never mentions one).
- Non-blocking asks: draft says `wait` forever. Rename the action `continue` and state the prose rule: `blocking:false` is allowed only when the work proceeds identically either way; a non-blocking ask must never be used to launder an unseen default into an action.
- Hard-escalate wins over everything: a default may never be proceeded on for a hard-escalate action (credit-billed model, SSH-out, firewall edit, physical actuation). Such items keep going through `AskUserQuestion` and are never sent as Task&I asks with `reversible:true`. State it in the block.
- The model sets `reversible` and `blocking`; tell it what they mean (reversible = undoing is a `git revert`/delete of untracked output with no external effect; otherwise false).

Proposed AC: "One `decide` test per row: `latest_start` present beats computed; computed from `hardDeadline`; neither -> `no-deadline`; `now == latest_start` -> passes, `now == latest_start - 1` -> `before-latest-start`; deadline in the past -> passes; `deferred:true` with `seen_at:null` -> passes (a); each of a, b, c, d alone false -> park with its why; all true -> `proceed/default-allowed`."

### 13. MINOR — JSON shape and exit codes need to be pinned
The shape in the draft is close but incomplete:
- Add per ask: `question`, `default` (the agent's own text, from the outbox), `blocking`, `reversible`, `latest_start_used`, `resolved`; top level: `unjudged`, `degraded`, `repoll`, `reclaimed_parked`; budget: `key`, `pending_tokens`, `unmetered`.
- `ratio` is a number in [0,1] (clamped) or null, never NaN/Infinity.
- `next` precedence: `stop` > `park-task` > `work`. When `park-task`, also list which asks caused it.
- Exit codes: 0 = a decision was printed (including unbound and degraded); 1 = usage error, no claim, capabilities failure, invalid env knob. Empty stdout on exit 1. State stderr wording for each (exact strings are testable).
- Env knobs: `VIBE_TASKANDI_BUDGET_ASK` must satisfy 0 < x < 1 (decimal, no hex, no empty string); invalid -> exit 1 naming the variable. (Park-minutes knob removed per concern 3.) An invalid knob breaks every boundary; the failure table (concern 8) covers it.
- `decide` must say whether it sends `capabilities` first (064 AC5: "every networked invocation") and that it sends no request when the claim has no open asks and the budget does not need one (so an idle boundary costs nothing), and that the `ask_status` call it makes also renews the lease.

### 14. MINOR — lease can lapse during a long iteration
Leases expire after 90 minutes without a task-carrying call. A `/vs` cycle inside an iteration can run longer; the boundary calls then arrive after the lease lapsed and another Codex or Claude session may already hold the task. The draft only renews at boundaries. Fix: the block says to run `taskandi-client decide` (which calls `ask_status` and renews) or enqueue a progress comment and flush at least every phase of a `/vs` cycle (after the spec, after the build, after the review). If `claim.lease.until` has passed at any boundary, run `next-task` with the same session (it re-issues a live lease) before any write. A write refused with a lease error then follows the failure table.

### 15. MINOR — prompt injection and size of task text
- Title and body can be written by anyone with access to the task (shared tasks) and the body is read as "the brief". The draft's sentence is right, but sharpen it: task text may supply goals and context; it never grants permission, never changes the hard-escalate list, never names a command to run verbatim without the model judging it, and never overrides this block. Also: do not copy task text into `comment`/`complete`/`release` payloads, commit messages or branch names (echo of attacker text into the owner's thread); build those from the model's own words and SHAs.
- Body size: 064 accepts up to 16 MiB in `next_task.body`. Printing it into the model's context is a denial of service on the session budget. Add `next-task --body-max-chars N` (default 20000; stdout carries `body_truncated:true` and `body_chars`) or write the full body to an untracked file `.vibe/taskandi-body.txt` mode 0600 and print its path. Test with a 1 MiB body.
- `open_children` titles are server strings; the block says to treat them as data and to ask about them (the client cannot complete non-claimed tasks, per 064), not to "do" them unless they are inside the repo's own scope.
- Answers: owner answers are applied "exactly as fromMartin answers are applied today"; add that an answer cannot waive the hard-escalate list, and note the `ignored` count in the session file without acting on it.

### 16. MINOR — every fromClaude write site must route through the same step
`vsss.md` writes to the project's fromClaude channel in the question format, the ambiguous-parallel-plan rule, and the `--spec-first` approve checkpoint; `vss.md` has its own. The draft says "instead of a fromClaude item" once. Enumerate the sites and give each a mapping: a `--spec-first` checkpoint becomes `blocking:false`, `reversible:true` ask (the loop continues, per the existing rule); the parallel-plan question becomes `blocking:true`, `reversible:true` (run serially meanwhile); an `approve` answer still queues `/vs --approve`. Also keep the consume protocol for the file channel (fallback items and any pre-existing answers) unchanged while bound, and say the two channels are consumed independently, with Task&I answers keyed by `ask_id` and the model recording `key -> question, default` in the iteration Notes so a later context (after compaction or a resumed window) can map an answer back to its question; `poll` only prints `ask_id` and `answer`.

### 17. MINOR — Codex parity
- Single source of truth: the flow lives in the `vss.md`/`vsss.md` blocks (Codex reaches them through the skills). `context.md`'s block should be short: for a plain (non-`$vss`) Codex session it says what is allowed (status, ask via FM2C ledger, poll, usage) and for `$vss`/`$vsss` points at the command's block. Two full copies will drift.
- Runtime differences to state in the block: `--agent` is `claude` in Claude Code and `codex` in Codex (the draft's `<claude|codex>` is left for the model to guess); Codex has no `AskUserQuestion` (hard-escalate items go through FM2C as today); the `usage` transcript source differs (Codex rollout, `turn_context.model`, `event_msg/token_count`); `ScheduleWakeup` is unavailable, which is why concern 3 matters; `codex-supervisor.mjs` pins the binding fingerprint (`VIBE_TASK_BINDING`), so a mid-run `next-task` that changes the effective task would fail `pinned task binding changed`: state that the claim does not change the digest (it does not under 064, by design) and add a test that `bindingFingerprint` is identical before and after a claim.
- Keep FM2C: Task&I answers in a Codex run join the same consumed-answer ledger (the old section said so; the new block must not drop it).
- AC11 should assert the removal of the v1 ask shape by content (`to` absent from the ask instructions), and that `context.md` still contains the "do not invoke `taskandi-client` unless configured" guarantee in the new skip string.

### 18. MINOR — enumerate the prose steps as one numbered procedure with a command per step
The draft's boundary paragraph is a run-on list. A model needs a numbered sequence it can follow after a context reset. Required: (1) detect, (2) pick, (3) work, (4) ask, (5) boundary (comment, usage, flush, time, flush again?, poll, decide), (6) act on `next`, (7) complete. One `taskandi-client` command per line, in fenced blocks, placeholders in `<angle brackets>` only (so the argv test in concern 9 can parse them). State who generates each payload field (for `ask`: `order` = 1..n within this boundary's set, `estimate_minutes` = minutes the owner needs to answer, `remaining_minutes` = the model's honest estimate of the rest of the task including the answer, integer, >= 1).

### 19. MINOR — `usage --cost-estimate 0`
The importer requires an explicit estimate and the context says "do not guess monetary cost", but `0` makes Task&I's cost roll-up read zero for real work. State it as a known limit in docs ("tokens only; cost is not reported") and keep `cost_estimate` out of any budget calculation (the budget is windows/tokens only).

### 20. MINOR — Test and doc items
- `decide` needs an injectable clock; the draft's tests cannot be deterministic otherwise. Add `createClient({clock})` as a test seam; a source check forbids reading the clock from env.
- Every `decide` test must run with no network except the `httpConnect` loopback seam, and a request-count assertion per case (zero for idle boundaries).
- MANUAL-TESTS Test 70 must say which parts are unverified until run (all proceed paths while `defaults_allowed` is false in production; windows metering; a live `spent` roll-up).
- Docs section must list `decide`, its JSON, exit codes and the two env knobs, and the failure table.
- Ask the taskandeye session (via the brief) three questions before the build: what `spent.tokens` sums, whether `next_task` can exclude tasks with open blocking asks (concern 4), and whether `next_task {task}` is planned (concern 11).

---

## Replacement acceptance criteria (concrete, to substitute for the draft AC1-AC12)

**AC1 Decide: conditions.** Table test, injected clock, fixture claim and outbox. One case per row: each of a, b, c, d false alone -> with `--no-other-work` `park` with the pinned `why` (order: `answered-not-yet-polled`, `unknown-ask`, `unseen`, `no-deadline`, `before-latest-start`, `defaults-off`, `irreversible`); without the flag `wait`; all true -> `proceed/default-allowed`; `deferred:true,seen_at:null` passes (a); `latest_start` beats computed; `now == latest_start` passes and `-1` does not; neither source -> `no-deadline`; past deadline passes; `blocking:false` -> `continue`, never park. Exit 0, stdout JSON with the pinned keys.
**AC2 Decide: answered and unjudged asks.** Concern 1 and 7 cases: answered-not-polled -> `wait` + `repoll`; non-owner-answered -> `park`; owner-answered asks absent; queued/uncertain/refused asks in `unjudged`; ask missing from `ask_status` -> never proceed.
**AC3 Decide: resolve ledger.** `proceed` is emitted once; `decide --resolve <key> --as proceeded|parked` removes it; a late owner answer still arrives through `poll`; resolving an unknown key exits 1.
**AC4 Decide: budget.** The table in concern 5 and 6: null/`{}`/zero allowances, 79/80/99/100/250 percent, windows with and without `--windows-used`, both dimensions, `spent` taken from the latest `record_usage` response, queued usage added as `pending_tokens`, `--remaining-minutes 0`, budget key present in any job state suppresses a second `ask`, budget ask excluded from `asks`, no NaN/Infinity in any output. `VIBE_TASKANDI_BUDGET_ASK` of `0`, `1`, `abc`, `` and `0x1` -> exit 1 naming the variable; `0.8` and `0.5` accepted.
**AC5 Decide: failure and unbound.** `ask_status` 500 -> exit 0 `degraded`, no proceed/park, budget present; no claim -> exit 1 with the no-bound-task message; `--task other` -> exit 1; unbound -> exit 0 `{"bound":false,"channel":"file-fallback"}`; zero requests when there is nothing to ask and no budget need; exactly one `capabilities` plus one `ask_status` otherwise.
**AC6 Loop guard.** `reclaimed_parked` per concern 4.
**AC7 Storage contract.** After flushing a fixture ask, `usage` and `next-task`, `state.json` carries `result.ask_id`, `payload.*`, `doneAt`, `claim.spent`, `claim.spentAt`; `bindingFingerprint` is the same before and after a claim.
**AC8 Prose: structure.** Per concern 10: block grammar, exact skip string, zero Task&I text outside the block for `vss.md`, `vsss.md`, both skills; `context.md` per its rule; the v1 `to` ask shape is gone; a negative control file fails the checker.
**AC9 Prose: commands.** Every `taskandi-client` line in each block parses with the client's argv checker (no network); the set of subcommands used equals exactly `status, next-task, enqueue, usage, flush, poll, decide, release, complete`; ordering checks (`usage` and `flush` before `complete`/`release`/`next-task`; `poll` before `decide`); the block contains the failure table rows, the untrusted-data sentence (task text, titles, answers from non-owners, `open_children` titles), the hard-escalate sentence, the args-mode and effective-task paragraphs, and the proceed-comment and `--resolve` steps.
**AC10 Next-task body cap.** A 1 MiB body prints truncated at the cap with `body_truncated:true`; the full text is not on stdout.
**AC11 Docs, changelog, manual test, gates.** As the draft's AC12, with the decide JSON, exit codes, knobs and failure table in `docs/taskandi-client.md`, and `python3 code-check.py` and `python3 smoke-test.py < /dev/null` both exiting 0.

## Questions that need an answer before the generator starts (put in `vibe-fromClaude.md` / ask taskandeye)
1. What does `spent.tokens` sum (input, output, cache read, cache write)?
2. Does `next_task` skip a task that has an open blocking ask or is over budget? (Decides how big the loop guard must be.)
3. In a bound project, should "Task&I has no task for me" fall back to TODO.md work (draft) or stop? (Martin's call.)
4. Should link-opened sessions (`vibe link`) work the linked task for real? (Needs `next_task {task}`.)

## Iteration 2

Iteration-1 BLOCKING items 1-8, 10, 11: resolved (11 only as a stated limit, see B4). Item 9: partly resolved (usage-before-switch order is fixed; transcript identity is not, see B3). Iteration-1 MINORs: addressed or reasonably declined.

### Concerns

**B1. BLOCKING: `next` precedence defeats the reclaim guard and the proceed path.**
- `stop` outranks `release-again`. A budget-stopped reclaim always has `budget.action stop` (cap or zero-allowance), so it resolves to `stop`, never `release-again`. The budget half of the guard is dead code. Stop does the sequence comment, `release --budget-stopped`, pick work, so the same task comes back and posts a comment every turn. Only `release-again` counts as a no-op, so nothing ends the run.
- `release-again` outranks `proceed`. A parked task whose latest start has now passed (the central case) is released again instead of proceeding on the default. It can never make progress.
- Fix: order `next` as proceed, then stop-when-not-reclaimed, then release-again (covering budget-stopped reclaims), then park-task, then work. Or keep the order but have `stop` on a `reclaimed_parked` budget-stopped task return `release-again`. Add AC6 cases: reclaimed + budget-stopped gives `release-again`, and reclaimed + a proceed-eligible ask gives `proceed`.

**B2. BLOCKING: AC1 contradicts A2 on `latest_start`.** AC1 says "`latest_start` present beats the computed value; when both exist, the later one is used." These disagree whenever `latest_start` is earlier. Fix: the later one wins (as in A2 condition 6); delete "beats", and test both orderings.

**B3. BLOCKING: the Claude transcript identification rule is unimplementable.** "The newest jsonl whose first record carries this session's id" mixes two things. `<session>` is a start stamp, not Claude's session UUID, and the record does not contain it. "Newest" is wrong with concurrent sessions or subagents, and misbills another task's tokens. Fix: at session start the harness records the transcript path and Claude session UUID in the session file. Claude: use the UUID that the first `usage`/status call or the hook env supplies. If neither exists, define the rule as "the jsonl containing the unique marker `<session>` that the harness wrote into the conversation". If the path cannot be determined unambiguously, skip `usage` (already stated). Make the prose step name the exact source.

**B4. BLOCKING: args mode and linked-task mode have no claim, but step 5.6 and the failure table assume one.**
- `decide` exits 1 with no claim. The failure row then says "release with reason ...", with nothing to release. Every boundary would fail, or be misread as a decide outage.
- `usage` and `record_time` also need a task target.
- Fix: state that in no-claim modes, step 5 runs `usage`/`record_time` against the effective task only if the client accepts `--task` (say which), and skips `decide`. Asks there are always `wait`, never `proceed` or `park`, and no budget logic runs. Add that to the failure table and AC10.

**B5. MINOR: the `repoll` flag has no prose consumer.** Step 5.6 says nothing on `repoll: true`. Add: re-run `poll`, then `decide` once more. Otherwise a late owner answer costs a whole extra boundary.

**B6. MINOR: `--check-argv` scope.** "Exactly as it would" can include state checks (`--resolve <key>` must be a done ask, `release --task` must be claimed), so sample-value prose lines would fail. Define it as syntactic validation only, with no state checks. Say how a missing stdin is handled for `enqueue` (with `--check-argv` and no stdin, validate argv only). AC10 should also include one stdin-payload case per `enqueue` type.

**B7. MINOR: AC9.** Define "the block" as including its marker lines, or the markers themselves match `/taskandi/i` outside it. State that `context.md` is checked only against its own block markers.

### Verdict

REVISE. B1 to B4 are small spec edits (one precedence change, one wording fix, one transcript rule, one no-claim paragraph) but would each cost a cycle (loop, test conflict, misbilling, unrunnable step). Everything else is fine to start from.

## Iteration 3

Checked against rev 3 and `devcontainer/taskandi-client.mjs` (task_064, uncommitted).

### Iteration-2 BLOCKING items
- B1 (next precedence): resolved. proceed > release-again > stop > park-task > work, with AC6 cases for both.
- B2 (`latest_start`): resolved. Later one wins in A2 and AC1, both orderings tested.
- B3 (transcript identity): resolved for naming. `CLAUDE_CODE_SESSION_ID` exists in this container and equals the transcript file name; `CODEX_THREAD_ID` is already used in the repo. But see N1: the parser cannot read the Claude file.
- B4 (no-claim modes): resolved. The client accepts `--task` on enqueue, usage, poll and ask-status; decide is skipped; failure-table row and AC10 cover it.

### Concerns

**N1. BLOCKING: the `usage` step cannot work for Claude Code; the client cannot read a Claude transcript.** `taskandi-usage.mjs` parses only the Codex rollout shape (`turn_context` model plus `event_msg`/`token_count` `total_token_usage`). A Claude jsonl (`type: assistant`, `message.usage`, `message.model`) yields zero records and returns `usageAvailable: false` with exit 0. So in Claude, the prose step 5.2 silently posts nothing, `claim.spent` never moves, and the whole budget half (cap, ask at 80%) is dead in the main runtime. The spec lists no Part A item for it. Fix: add A7 "usage reads Claude transcripts": sum `message.usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) per assistant message id (dedupe repeated ids, since streaming writes duplicates), model from `message.model`, per-delta keys as in the Codex path, with an AC (fixture jsonl -> the expected `record_usage` payloads; re-run enqueues nothing new; unknown shape -> `usageAvailable:false`, not a throw). Or state that Claude billing is out of scope and remove the claim that budget works under Claude. Also give the exact Codex path glob (rollout files are `rollout-<time>-<id>.jsonl` under dated folders), not "named by".

**N2. BLOCKING: A1 says the claim holds the whole `next_task` object, but the code stores only `{task, agent, session, lease, claimedAt}`; and `decide` condition 8 has no stated source for `defaults_allowed`.** `defaults_allowed` appears only in the `next_task` response and is absent from `ask_status`. Specify: the claim stores `allowance`, `spent`, `hardDeadline`, `latest_start`, `defaults_allowed`, `estimate_minutes`; condition 8 reads `claim.defaults_allowed` (value at claim time) and says so; say whether a lease-renewing `next-task` replacing the claim keeps `spentAt`/`spent` (it should not lose a newer `spent`). Add `claim.defaults_allowed` to AC7 and an AC1 case where the claim says true.

**N3. MINOR: proceed outranks stop.** A budget-capped task with a proceed-eligible ask returns `proceed` and works one more iteration over the cap. Probably acceptable (defaults are off anyway), but say so, or let `stop` with `why: cap` outrank `proceed`.

**N4. MINOR: `release-again` prose says "release with the same reason"** but omits `--parked-asks`/`--budget-stopped`; without them no `parked` entry is rewritten, so `parked.at` stays old. Say to repeat the original flags. Also say when a `parked` entry is cleared (on `complete`, or on a proceed).

**N5. MINOR: flush exits 0 even when jobs are `uncertain`, `refused` or `requeued`** (code returns counts; only `cli()` failures exit 1). The failure-table "flush fails" row and step 4 "if the job is not done after flush" must read the JSON counts, not the exit code. Say so.

**N6. MINOR: no-claim mode lists comment, usage and record_time with `--task`, but not `poll` and the step-4 `enqueue ask`.** A stale `claimed` from an earlier run is preferred over the bound task when `--task` is absent (`targetFrom`). Add `--task` to poll and ask in that mode. Also `--task` is accepted only when it equals the bound task or the claim, so a linked task different from both would fail; state that linked-task mode requires the link to be the descriptor's bound task.

**N7. MINOR: `--check-argv` and `decide` are new** (no `--check-argv` in `main`/`descriptorMain`; strict flag parsing will reject `--parked-asks` etc. until added) - fine, but A6 should say it runs before `readStdinJson` and before `loadConfig`, so it works in an unbound CI project. `doneAtMs` is also new (only `doneAt` exists).

### Verdict
REVISE. N1 and N2 are small spec additions but would each cost a cycle (budget silently dead under Claude; untestable condition 8). N3 to N7 can be fixed in passing. Existing seams (`cli()`, `httpConnect`, `result.ask_id`, `doneAt`, `--task` on usage/poll/enqueue) are all present as A1/A2 assume.

## Iteration 4

Checked rev 4 against the committed `devcontainer/taskandi-client.mjs`, `taskandi-usage.mjs`, and a real Claude transcript (`~/.claude/projects/-workspace/<CLAUDE_CODE_SESSION_ID>.jsonl`).

### Iteration-3 items
- N1 (Claude parser): resolved in A1b. Real file confirms `type:"assistant"`, `message.id`, `message.model`, `message.usage.{input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens}`, `isSidechain`; the file name equals `$CLAUDE_CODE_SESSION_ID`. Duplicate records per `message.id` (up to 6) carry identical usage, so "last wins" is safe. `usage` also has extra keys (`cache_creation`, `iterations`, ...) that the parser must ignore. The 128 MiB / owned-file / final-line handling already exists in `enqueueTranscriptUsage`.
- N2 (claim fields): resolved (A1 list, `defaults_allowed` source, `spent`/`spentAt` merge, AC7).
- N3 resolved (`stop` outranks `proceed`). N4 resolved (repeat flags; clear on complete/proceed). N5 resolved (step 4 reads counts). N6 resolved (`--task` on poll and ask; `VIBE_TASK_REF` becomes `config.task`, so `targetFrom` accepts it). N7 resolved (A6 before config and stdin).

### Concerns

**C1. BLOCKING: valueless flags clash with `strictFlags`.** `descriptorMain` parses every flag as a `flag value` pair (`strictFlags`, step 2). The spec's `release ... --budget-stopped` and `decide --no-other-work` are bare flags; as written they fail with usage (or swallow the next token). Prose lines using them would fail `--check-argv` (AC10) the first time. Fix: say in A2/A4 that `strictFlags` gains a boolean-flag set (`--no-other-work`, `--budget-stopped`, valueless, rejected if given a value or repeated), or change the prose to `--budget-stopped true`. Pick one in the spec.

**C2. MINOR (cost-bearing, fix in passing): zero-usage and synthetic messages.** The real file contains `message.model: "<synthetic>"` records with all four usage fields 0 (2 of 505 here). Skip a message whose four fields are all 0 (the Codex path already skips all-zero deltas), or `enqueueBatch` posts a zero `record_usage` for a fake model that Task&I may refuse, and a refused job then shows in every `status`. State it and add one fixture message to AC7b.

**C3. MINOR (design debt, not this slice): one `record_usage` job per assistant message.** A single session here has hundreds of distinct message ids; the first boundary enqueues and then POSTs every one serially (15 s timeout each), and `state.json` is capped at 4 MiB by `readBounded` and nothing prunes `done` jobs (about 6000 jobs reaches the cap, after which the client refuses to load). `source`/`source_ref` already exist as job fields, so a per-boundary aggregate keyed by `[session, last message id]` would be a small later change. At minimum put the limit in the docs "Harness integration" section, and note that `pending_tokens` can be large right after the first import.

**C4. MINOR: `parked` entry and the unknown-outcome path.** `release` clears the claim inside `finish()`'s `settle(true)`; the `parked` entry (which needs the claim's `allowance`) must be written there, before `delete state.claimed`. If the outcome is unknown, `pendingDirect` holds no parked fields, so `reconcile --direct release --action done` would not write the entry and the reclaim guard is blind (the task comes back, same loop). Either carry `parkedAsks`/`budgetStopped`/`allowance` in the `pendingDirect` record or state the limit (the prose already forbids claiming a new task that iteration, which covers the same run only).

**C5. MINOR: sidechains.** In the real file `isSidechain` is false for all 505 records; subagent transcripts live in separate files (`<session>/subagents/`), so "sidechain records are included" is vacuous and subagent spend is not billed. Say so in the docs limit, or add a documented follow-up.

**C6. MINOR: key shape.** State the Claude usage key: `usage-` + sha256 of `[session, model, message.id]`, so the same message never re-keys when a later record for it arrives with the same totals (and the fixture "three records same id" yields one key).

### Verdict
REVISE (one small spec edit). Only C1 blocks: pick bare-flag support in `strictFlags` or the `true` value form so the prose and `--check-argv` agree. Everything else in rev 4 is consistent with the committed task_064 code and the real Claude transcript format; C2 to C6 can be folded in passing.
