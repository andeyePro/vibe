---
description: Versus Super Solo — runs /vss on the given args, then optimises args and loops /vss in argumentless A-mode until perfection-gate, an explicit user budget cap, or a hard-escalate trigger — persisting across credit windows BY DEFAULT until the task is complete. Higher blast-radius than /vss; intended for end-of-day "burn the rest of my session productively" runs.
---

# /vsss — versus super solo

Autonomous loop wrapper around `/vss`. Higher blast radius — read this whole file before invoking.

`$ARGUMENTS` is the initial task. May be empty (loop starts in Mode A immediately).

## Hard-escalate list

Inherited verbatim from `/vss`. Every iteration of every wrapped `/vss` invocation honours it. See `/vss` for the full list. Summary: physical actuation, SSH-out, `/vs --fuzzy` subjective verdicts, destructive git, `/learnings` writes, firewall/hook/perm edits, scope creep, anything CLAUDE.md flags as needing per-turn auth.

A hard-escalate trigger inside any iteration aborts the entire loop, not just that iteration.

## Session-budget capture

At the very start of `/vsss`, before any work:

1. Capture `START_TIME=$(date -u +%s)` (or equivalent in your context).
2. Read `MEMORY.md` for `feedback_autonomous_session_protocol`, `feedback_default_to_local_time_for_uk_user`, and `feedback_vsss_todo_staleness` (surface stale TODO items before Mode A picks). Apply all three.
3. Set `BUDGET_HOURS=5` unless the user passed an explicit budget. Recognised flags (in order of precedence; first match wins):
   - `/vsss --hours N <args>` — canonical. `N` is a positive integer or decimal (e.g. `2`, `2.5`, `0.5`). Sets the budget cap to `N` hours from `START_TIME`.
   - `/vsss --budget Nh <args>` — backward-compatible alias. Same semantics; `Nh` parsed as a positive integer or decimal followed by literal `h`.
   - `/vsss --budget Nm <args>` — minutes form, for short-runs (e.g. `--budget 30m`).
   - `/vsss --fable-subagents <args>` (alias `--fable`) — standing per-run pre-authorisation of the credit-billed Fable rung, semantics per `/vs § Model economy`; propagated into every wrapped `/vss` iteration and each `/vs` Model plan. Record it in the session file's Initial-plan block and note each Fable dispatch in the per-iter Notes. The grant PERSISTS across auto-resume relaunches: the Resumption protocol restores args from the session file, and that recorded Initial-plan grant IS the authority — never demand a fresh flag mid-run.
   - `/vsss --sessions X <args>` — combinable with the budget flags; CAPS the run at X credit windows TOTAL (`--sessions 3` = the current window plus up to 2 automatic relaunches; `--sessions 1` = single-window opt-out, no relaunch). **Omitting the flag does NOT mean one window** — the default is unbounded persistence. See § Auto-resume across halts. Legacy: `--auto-resume N` (retired 2026-07-08) meant N EXTRA windows — treat it as `--sessions N+1`.
   - No budget flag → `BUDGET_HOURS=5`. This is the per-window clock used to estimate `resume_at` — NOT a finish line, and (absent an explicit `--hours`/`--budget` flag) NOT an exit condition.
   - `/vsss --spec-first <args>` — threads `--spec-first` into every wrapped `/vs` invocation this run dispatches; a checkpoint hit does not stop the loop (§ Interaction with the loop) — semantics: `/vs § Step 3b`.
   - `/vsss --TDD <args>` — threads `--TDD` into every wrapped `/vs` invocation; red-first trail contract per `/vs § Step 4`.

   **Remaining time is never a reason to stop, shrink, or skip work.** There is no graceful-shutdown cushion and none is needed: every iteration commits as it lands, and § Resumption protocol continues an interrupted iteration in the next window — a halt mid-iteration loses nothing. Never bias the optimiser toward "stop" because the clock is running down, and never pass over a queue item because it "won't fit this window" — start it; if the window dies first, resumption finishes it. An explicit `--hours N` / `--budget N[hm]` flag is the ONE user-imposed hard stop: on reaching it with work outstanding, commit what's in flight, write Final state with `Exit reason: user budget cap`, set the marker `active=0`, and stop — never label that stop a perfection gate.
4. Open `.vss/sessions/<start-ISO>.md` (filename uses `T` separator and replaces `:` with `-`, e.g. `2026-05-07T14-29-02Z.md`) and write the audit header per the format defined in `/vss` § Session audit format. The Initial-plan section captures the initial args, priority queue (if any), and budget.

Every iteration appends a full Iter section to the session file (Plan / Files touched / Commit / Outcome / Notes). Final-state line is appended at exit.

The session file is the single canonical audit Martin reviews. There is no separate roll-up index.

## Resumption protocol (after out-of-tokens halt or interrupted session)

A `/vsss` session can be killed by token-exhaustion, a manual interrupt, or any unhandled error. Without resumption the work in flight is dropped: partial commits sit on `main`, the priority queue is forgotten, and the user has to re-issue the original invocation.

### State that survives a halt

The session file at `.vss/sessions/<start-ISO>.md` is the persistence layer: its iter block is up to date after every iter completes (Generator commit landed, Tester commit landed, optimiser verdict written). A most-recent iter block with no `## Final state` section is the signal "this session was alive when killed".

### Detecting an in-progress session at startup

When `/vsss` is invoked (with any args, or `--resume`), Planner first scans `.vss/sessions/*.md` for **in-progress sessions**: files where the most recent section is an `## Iter <N>` block (any iter) and there is NO `## Final state` section yet. If one or more found, sort by start-ISO descending and inspect the most recent.

Three branches:

- **`/vsss --resume` flag passed, in-progress session exists**: load the most recent in-progress session and resume it. The original args, priority queue, budget, and remaining-iter context all come from that file. Continue from the iter AFTER the most recent committed one.

- **`/vsss --resume` flag passed, NO in-progress session exists**: fall back to the most recent COMPLETED session (Final state present). Read its `## Final state` § Deferred list. If non-empty, treat the deferred items as the new priority queue and start iter 1 against the first one. Open a fresh session file at `.vss/sessions/<new-ISO>.md` (do NOT append to the completed one — it's finalised); record in Initial-plan that args were `--resume` and the queue was inherited from `<previous-session-file-path>`. Budget is fresh 5h (or `--hours N` override) since the previous session reached Final state cleanly. If the deferred list is empty, surface to the user "no in-progress session and no deferred items in the last completed session; pass args or no flag to start fresh" and stop.

- **`/vsss <new args>` invoked while an in-progress session exists**: surface the conflict. Two resolutions: (a) `--resume` to pick up the in-progress one, OR (b) mark it halted (write a Final state section with `Exit reason: superseded by new /vsss invocation` and start fresh). Per `/vss`'s hard-escalate list this is "scope-creep beyond announced plan" — do NOT auto-pick. (A Q1=a authorisation does not cover it: the new args might not match the parked session's queue.)

- **`/vsss` with no args, no in-progress session**: normal Mode A start.

### Resume budget arithmetic

Under default persistence (no explicit `--hours`/`--budget` flag on the original invocation) there is NO budget arithmetic to do on resume: each window gets a fresh `BUDGET_HOURS` allowance (see § Budget arithmetic under persistence), the clock is never a reason to stop, and a resumed run just continues. Never compute a "negative budget" from the default 5h and never escalate on the clock — that would reintroduce the time-fit stop this spec outlaws.

Only when the ORIGINAL invocation carried an explicit `--hours`/`--budget` cap does the cap span the halt: `START_TIME` is preserved, resumption does not reset the clock (original cap 5h, 3h consumed before the halt → 2h remain). The session file's header line (`# /vsss session — start <ISO> – budget Nh`) plus current `date -u` lets Planner compute remaining time. If that explicit cap is already exceeded when resuming, Planner asks the user whether to extend it (`/vsss --hours N --resume` to extend to N hours total, NOT N additional hours) or finalise the session with whatever's been committed.

### Resumption procedure

1. Read `.vss/sessions/<resumed-ISO>.md` end-to-end. Identify last completed iter and pending state.
2. Read `git log` since session start (`git log --since="<start-ISO>" --oneline`) to verify the iter blocks match the actual commits. If they don't (e.g. iter block claims commit X but `git log` shows X was reverted), surface to the user — DO NOT silently proceed.
3. Budget check: default persistence (no explicit `--hours`/`--budget` on the original invocation) → nothing to compute, continue. Explicit cap → compute remaining; if exceeded, escalate per § Resume budget arithmetic.
4. Append a new `## Resumption — <ISO>` block to the session file noting: timestamp of resumption, hours-elapsed-during-halt, budget-remaining (explicit caps only), the iter we're picking up at. Rewrite the marker now: `remaining` read back unchanged (launcher-owned — see § Auto-resume), `resume_at` re-based to resumption epoch + 5*3600.
5. Continue the loop from the next iter per the original priority queue / optimiser logic.

### Auto-resume across halts (default since 2026-08-29; `--sessions X` caps it — shipped 2026-07-04 as `--auto-resume N`, renamed 2026-07-08)

Automatic continuation across credit windows is the DEFAULT: a `/vsss` run keeps relaunching after out-of-credit halts until the task genuinely completes. `--sessions X` caps the run at X windows total (X-1 relaunches); `--sessions 1` opts out of relaunch entirely. Skill side (this spec) and launcher side (`/workspace/vibe`) split the work:

**Skill side — you maintain the marker.** At session start, write `.vss/auto-resume` (the marker file keeps its name — it's the launcher-side contract; KEY=VALUE lines, digits only — the launcher rejects anything else):

```
active=1
remaining=<X-1 if --sessions X was passed; 9999 otherwise — FRESH invocations only, see below>
resume_at=<current window's start + 5*3600, epoch seconds>
session_file=.vss/sessions/<start-ISO>.md
```

`9999` is the unbounded-persistence sentinel — the launcher contract is digits-only, and 9999 windows is "as many as it takes" with a runaway failsafe. The launcher decrements it per relaunch like any other value; no launcher change is involved.

- **`remaining` is LAUNCHER-OWNED once first written.** Only a fresh (non-resumed) invocation sets it (X-1 from `--sessions X`, else the 9999 sentinel). On every per-iteration refresh, and at the start of any RESUMED window, read the existing marker's `remaining` back and rewrite it UNCHANGED — never re-derive it from the flag or the sentinel. Re-deriving would silently undo the launcher's per-relaunch decrement, making a `--sessions X` cap unenforceable (the run would relaunch forever). A missing/unreadable marker on a resumed window is the one exception: rewrite it with the value the session file's window count implies, and note the reconstruction in the session file.
- `resume_at` is the best estimate of the 5h-window reset, always computed from the CURRENT window's start: a fresh invocation uses `START_TIME + 5*3600`; a RESUMED window re-bases it from the resumption timestamp (resumption epoch + 5*3600), NOT the original `START_TIME` — a stale `resume_at` already in the past would collapse the launcher's countdown to its 120s past-grace and probe a genuinely exhausted window every 2 minutes, each probe costing a full stall-watchdog cycle. (This re-basing is only about the marker; an explicit `--hours`/`--budget` cap still measures against the original `START_TIME` per § Resume budget arithmetic.) The window may have opened before the current window's `/vsss` start did, so `resume_at` can still be late — the launcher pads and rate-limit-caps it. Refresh the whole marker at the top of every iteration (cheap, atomic: write to `.vss/auto-resume.tmp`, `mv` over; `remaining` preserved as above).
- **Spent marker (`active=1, remaining=0`)**: when the launcher declines the final relaunch, nothing is left running to write `active=0`. That marker is inert — the countdown requires `remaining>=1` and the freshness gates see it as stale — and the next `/vsss` invocation overwrites it wholesale (a resumed final window's own clean exit writes `active=0` as normal). No manual cleanup is required, but deleting it is always safe.
- **On ANY clean exit** (perfection gate, explicit user budget cap, hard-escalate abort, three no-op iterations — anything that writes `## Final state`), rewrite the marker with `active=0`. A finished loop must never relaunch. This is part of the atomic exit write; do not skip it on aborts.
- With `--sessions 1` only, never write the marker (and set `active=0` in any stale one you find at start). Every other invocation — flag or no flag — writes it. Note the trade `--sessions 1` accepts: the stall watchdog never arms (with no marker file the heartbeat hooks stay quiet too; if only a deactivated stale marker exists, the hooks — gated on file existence, not `active` — still write the heartbeat, but the watchdog's `active=1` condition alone keeps it disarmed), so a wedged usage-limit picker in that window hangs until the user intervenes — opting out of relaunch also opts out of the stall kill.

**Launcher side (already implemented in `/workspace/vibe`).** When claude exits while the marker says `active=1` and `remaining>=1` AND the marker was (re)written during the current launcher session (the same mtime-vs-session-ref freshness check the stall watchdog uses — required now that every run writes a marker, so a crash-left marker from an earlier session can't ambush a later plain launch with a surprise countdown; a stale marker instead prints a hint to run `/vsss --resume` explicitly and is left in place), the launcher counts down to `resume_at` (+2 min pad/grace, env-overridable via `VIBE_RESUME_PAST_GRACE_SECS`; 30 min fallback if the field is unusable; Ctrl-C cancels), decrements `remaining`, and relaunches `claude --continue "/vsss --resume"` — which lands in this spec's Resumption protocol above. The relaunch cost is one window from the X budget, whatever the halt cause was — the launcher cannot reliably distinguish credit exhaustion from a crash, and both are legitimate resume cases; a user-typed `/exit` mid-run also triggers the countdown, which is why the countdown is loud and cancellable. The countdown is also rate-limit-AWARE: `resume_at` is a blind worst-case estimate (session start + 5h), so vibe's statusLine drops the REAL 5h-window usage into `.vss/rate-limit` as it renders, and a reading that is fresh (`VIBE_RATE_READING_MAX_AGE`, default 1800s) with headroom (`used` at most `VIBE_RESUME_USED_MAX`, default 50%) caps the wait at the 2-minute grace instead of sitting out a stale estimate — both knobs env-overridable per launch.

**Launcher-side stall watchdog (the reason the marker refresh above is now load-bearing).** Interactive claude does NOT exit when a Pro/Max usage window runs out — it blocks forever at an interactive usage-limit picker, so the relaunch above never fires on its own. The launcher now backgrounds claude, watches a container-side heartbeat file (`.vss/heartbeat`, refreshed by `settings.local.json` hooks on tool activity while a marker exists), and kills a genuinely wedged claude itself. The kill only arms when THREE conditions hold: the marker is `active=1`; the marker was refreshed DURING the current launcher session (proven via the marker's mtime against a session-start reference file) — this is exactly why your per-iteration marker refresh (above) matters: without it, a live persistent run could look like a stale crash-left marker and never get the stall protection — and, since the launcher's countdown gained the same freshness gate, never get an auto-relaunch either; and the heartbeat has gone stale past the threshold. Defaults: `VIBE_STALL_SECS=1800` (heartbeat staleness before a kill is even considered — 30 min, chosen because hooks fire for subagent tool calls too, so long Task/Agent dispatches keep the heartbeat fresh, and a single Bash call is capped at 10 min by Claude Code itself), `VIBE_STALL_POLL_SECS=60` (watchdog poll interval), `VIBE_STALL_GRACE_SECS=120` (warn-then-wait before killing), `VIBE_STALL_KILL_PAUSE_SECS=10` (pause between the in-container kill attempt and the host-side fallback). All four are env-overridable per launch. On kill: with `remaining>=1` the launcher drops straight into the countdown/relaunch above; on the final window (`remaining=0`) the loop is simply not entered and vibe exits cleanly instead of hanging forever. The skill needs NO new behaviour beyond the marker refresh it already specifies above — this is entirely a launcher-side addition.

**Budget arithmetic under persistence (default, and `--sessions X`).** Overriding the resume-budget rule above whenever the marker is active: each auto-resumed window gets a FRESH `BUDGET_HOURS` allowance (the whole point is spanning multiple 5h windows); `remaining` is what bounds total run length (effectively nothing, under the 9999 sentinel — the task's real exit conditions bound it). `--hours` still caps each window individually.

## Loop structure

```
iter 1:  /vss $ARGUMENTS                      (Mode B if args, else A)
opt:     Opus optimiser proposes refined args, OR returns "satisfied"
iter 2:  /vss <optimised args>                (Mode B with optimised args)
         OR /vss                              (Mode A — no args)
iter 2∥3: (--wide) two independent queue items in parallel, each in its own worktree
...
iter N:  loop continues until exit condition
```

### Parallel plan (`--wide`)

Under `--wide`, before iter 1 (and refreshed at every iteration boundary) write a `## Parallel plan` block to the session file: one row per queued item with `files:`, `depends-on:`, `worktree:`, `owner-model:`, plus plan-level `Merge order:` and `Serial because:` lines naming what can't run concurrently and why. See `wide.md` for the concurrency caps this plan must respect.

Worktree convention: `.claude/worktrees/<task-id>`, branch `vsss/<task-id>-<slug>`. Hot shared single-writer files — never assign two concurrent items the same one: `smoke-test.py`, `site/site-check.mjs`, `site/src/content/home.md`, `.vibe-content-allow`, `devcontainer/commands/*.md`.

`.vs/` split under `--wide`: per-task files (`spec.md`, `cycle-N/`) live in the worktree; repo-wide accumulators (`tasks.json`, `progress.md`, `cost-summary.json`) stay chair-owned on main — a worktree task never writes them directly, it appends its cycle summary to `.vs/progress-block.md` instead, folded into `progress.md` by the chair at merge. And worktree tasks never touch CHANGELOG.md or TODO.md — the chair appends both on main at merge, one entry per merged item, in merge order.

**Merging a worktree item**: `rebase` onto current main → `full suite once` (once after rebase, not per-worktree) → `--ff-only` merge → chair appends CHANGELOG/TODO/progress → `git worktree remove`. On a rebase mis-apply (e.g. a duplicated pick), first response is `git rebase --abort`, then `git cherry-pick -n <sha>` onto main with per-file conflict resolution — CHANGELOG/TODO resolved newest-first, chair-owned accumulator files rebuilt from HEAD plus the new entry rather than diffed. If a hot shared file was restructured underneath the worktree (e.g. a test suite split into new modules), re-home the worktree's hunks by context-matching into the new layout and re-run the affected tests. Only then, if still conflicting, finish the item serially. A rebase conflict signals a dependency-analysis miss, not a retry point: drop the parallel attempt for that item and finish it serially instead.

### What "the loop" actually is — read this before iter 1

There is no harness-run loop. The loop is nothing but YOU continuing to emit
tool calls. It ends the instant you emit a message with **no tool call in it**,
and it ends for no other reason.

Two corollaries, both of which have caused real multi-hour stalls:

- **Stopping is the failure, not speaking.** A message may carry prose AND tool
  calls together and the run continues — that is ordinary narration. So do not
  reason "I wrote a summary, therefore the turn ended"; you ended the turn, and
  the summary is what that looked like. Silence fixes nothing either: a silent
  run that stops is equally dead. The rule is **never stop while an exit
  condition below is unmet**.
- **A question is not an exit condition.** Needing Martin's input on the current
  area NEVER ends the loop. Write the ask to the project's fromClaude channel
  and move to the next area that needs no input; pick the answer up at a later
  iteration boundary. Waiting is not a state you can occupy — there is no wall
  clock inside a turn, so "wait 10 minutes and re-check" is not implementable.
  Poll the inbound channel at iteration boundaries instead.

Between iterations, progress belongs in `.vss/sessions/<start-ISO>.md`, not in a
message to the user — it is durable, it survives an abort, and Martin is not
watching a live feed anyway. Questions for the user go through § fromto
channels below — never through stopping.

## fromto channels — asynchronous user Q&A without stopping

Why this exists: a long `/vsss` run scrolls far more through the TTY than the
user will ever read, and they only want to answer what they MUST to unblock
work. So questions leave the terminal: they land in the user's second brain as
a short live list, answers come back the same way, and the loop never waits.

### The three files

In the project's folder of the mounted second brain (`/brain2/<project>/`,
matching the existing per-project channel convention):

- `<project>-fromClaude.md` — Claude's live questions. Claude writes, user reads.
- `<project>-from<User>.md` — the user's answers and instructions. User writes;
  Claude only ever *removes consumed items* from it (and never touches the last
  line — it may be mid-edit).
- `<project>-Q&A-archive.md` — resolved exchanges, grouped by thread. Claude
  writes, nobody needs to read it unless auditing.

`<User>` is the first name from `git config user.name`; `VIBE_FROMTO_USER`
overrides. `<project>` is the workspace folder name.

**Activation.** If the `from<User>` file already exists, fromto is ON — no flag,
nothing to type. If it does not exist and `/brain2` is mounted, ASK at session
start (front-loaded, before the autonomous phase — never mid-run): one line
offering to create the three files, naming all three paths. Declined → run
without; questions then queue for the exit report only. No `/brain2` mount →
same ask but offering `.vss/` in-repo paths instead. On creation and at every
session start while active, print one terminal line: questions land in
`<fromClaude path>`, answers go in `<from-User path>`. The files cross-link
with `[[wikilinks]]` so the user can hop between them in Obsidian.

### fromto format

Default shape of the fromClaude file. The user can replace it (override below).

```
---
state: authored
author: Claude (<harness>, <repo>)
created: <ISO date>
cssclasses: [trust-authored]
---
Reply in [[<project>-from<User>]]. History: [[<project>-Q&A-archive]].

1. <action point: a question to answer, or a test to run> (T<n>)
```

Rules: one ordered list and nothing else: action points only, contiguous
from 1, no session report (§ Question format). Information appears only
where it answers a question the user asked.

Exit appends exactly one line: Session log:
`.vss/sessions/<start-ISO>.md` — <N> commits, <pushed|not pushed>.

When present, `/brain2/meta/fromto-format.md` overrides this default
verbatim — write-files-only, never `git` against it.

### Question format (fromClaude)

One single ordered list, numbered contiguously `1..N`, containing ONLY live
(unanswered) questions — Obsidian renders one OL per file and requires
contiguous numbering, and the user must never have to scan resolved noise.
Each item is one self-contained question ending with a Claude-written thread
tag: `3. Should the API retry on 429s? (T7)`. The user never types thread
tags — they exist so exchanges stay threaded through renumbering. Tags are
monotonic and never reused. Channel hygiene applies: questions and blocking
asks only — no progress notes, no FYIs (progress lives in the session file).

A `--spec-first` checkpoint posts exactly one action point, in this shape: `Approve the spec for <task-id> — <one-line goal>? It's at .vs/spec.md. Reply "approve", or edit that file and reply "approve"; reply with changes instead to redirect. (T<n>)`

### Answer format (from<User>) — the lazy contract

The user answers with a plain OL whose numbers match what fromClaude showed
them: `1. y`, `2. n`, `3. ?`. Meanings:

- Any text — the answer. Terse is expected; `y`/`n` are complete answers.
- `?` — question not understood. Re-ask as a NEW numbered question in the SAME
  thread, expanded/clarified. A `?` is an answer: the original leaves the live
  list.
- `later` — acknowledged, not now. Keep it live (or park it with a note if it
  blocks nothing).
- Omitted — still live; never nag, never re-ask unchanged.

Unnumbered prose or extra numbered items that answer no live question are
INSTRUCTIONS — see precedence below.

### Consume protocol — start of EVERY iteration

1. Read `from<User>`. Nothing new → carry on immediately; never idle-wait.
2. **Map answer numbers to questions via generations, not blindly.** Only
   Claude rewrites fromClaude, so the user can only ever have seen a numbering
   Claude wrote. Before every rewrite, record the outgoing generation (number →
   thread tag → question text) in the session file. When consuming, compare the
   `from<User>` file's mtime against fromClaude's last-rewrite time: answers
   written before the last rewrite map through the PREVIOUS generation. An
   answer number that maps to nothing in the applicable generation is never
   guessed at — re-ask in-thread.
3. Move each resolved pair to the archive under its thread heading
   (`### T7 — <short topic>`), appending the full exchange in order — question,
   any clarifications, final answer — so a dragged-out thread reads as one
   conversation, not chronological interleave.
4. Remove consumed items from `from<User>` (leave anything unparseable and the
   last line untouched). The user should find a clear file ready for a fresh
   contiguous OL.
5. Rewrite fromClaude: drop resolved items, renumber the survivors from 1,
   append any new questions, record the new generation.
6. Fold answers and instructions into the plan BEFORE the optimiser picks the next area — an `approve` reply to a spec-first action point queues `/vs --approve <task-id>` as the next iteration touching that task; a reply with changes is a spec-revision instruction folded into `.vs/spec.md` before re-approving.

### Precedence

Live terminal prompt > `from<User>` instructions > TODO queue. A terminal
prompt is always supreme — "are we safe to exit" means stop cleanly NOW, never
"after I finish the from<User> backlog". Instructions in `from<User>` redirect
the queue (log the redirect in the session file); they are user instructions,
not suggestions.

### Ambiguous dependency analysis (`--wide`)

When the Parallel plan's dependency analysis is ambiguous — unclear whether two queued items touch overlapping state — never guess: post a fromClaude question in the minimal template (§ fromto format above), and run that item serially in the meantime; fold the answer into the plan once it arrives.

### Interaction with the loop

Needing an answer NEVER stops the loop and NEVER blocks an area silently: post
the question, move to the next area needing no input, pick the answer up at a
later iteration boundary. If every remaining area is blocked on unanswered
questions, that is exit-condition territory (no-op iterations) — the exit
report then says exactly which numbered questions unblock which work.

A `--spec-first` checkpoint never blocks the loop either: write the spec, post one action point, move to the next queue item; an `approve` answer later queues `/vs --approve <task-id>` as a future iteration's item.

### After each /vss completes

Dispatch `Agent(subagent_type: "general-purpose", model: "opus")` as **optimiser**:

> You are the optimiser for `/vsss`. The previous iteration ran `/vss` with the args below and produced the diff and notes summarised below.
>
> Decide one of:
>
> 1. **Refine args** — the original brief still has uncovered scope, OR the diff revealed a follow-on improvement worth doing now while context is warm. Output the refined args as a single line (will be passed to next `/vss` iteration).
> 2. **Args satisfied — switch to A-mode** — the brief is genuinely complete; next iteration should TODO-scan or repo-scan instead.
> 3. **Stop the loop** — perfection gate. No further improvement adds positive expected value. Cite concrete reasons (NOT "looks good"). Examples of acceptable reasons: "all open TODO items resolved, repo-scan returned nothing", "test coverage 100% on changed paths and CHANGELOG up to date", "remaining TODO items are all on the hard-escalate list".
>
> **Time is not an input.** You are told nothing about remaining wall clock, window boundaries, or token budget, and you must not reason about any of them (including schedule hints that leak in via the executor's notes). "The next item needs more time/cycles than remain" is grounds for verdict 1 or 2 — NEVER verdict 3: persistence across credit windows is the default, so an oversized item simply spans windows; resumption finishes what a window boundary interrupts. Verdict 3 is lawful ONLY on the concrete task-complete reasons above.
>
> Original args: `<args>`
> Diff stat: `<git diff --stat HEAD~1>`
> Iteration commits: `<git log --oneline HEAD~N..HEAD>`
> Notes from executor: `<executor's report>`

Apply the optimiser's decision. If it returned "stop", exit cleanly — but first check its cited reasons against the verdict-3 whitelist: a ruling that leans on wall-clock, window-fit, or "not enough time/cycles" reasoning is void; treat it as verdict 2 (A-mode) and continue.

## Exit conditions (any one ends the loop)

In priority order — check each at the start of every iteration:

1. **Hard-escalate triggered inside any iteration.** Stop immediately. Surface the trigger reason.
2. **Optimiser returns "stop the loop"** (perfection gate).
3. **User budget cap — explicit flag only.** Fires only when the user passed `--hours`/`--budget` AND `(date -u +%s) - START_TIME` exceeds that cap. The default `BUDGET_HOURS=5` is NOT an exit condition — it only estimates `resume_at` for the marker. Real credit exhaustion needs no exit logic here: the client blocks at the usage-limit picker, the launcher's stall watchdog kills it, and the active marker relaunches `--resume` into the next window. Until that happens, keep emitting tool calls — every remaining minute and token belongs to the task.
4. **Three consecutive A-mode iterations with `no-op` outcomes** (no commits). Indicates TODO is empty AND repo-scan finds nothing high-leverage. Stop.
5. **Destructive-state signal.** If git is in an unrecoverable state (merge conflict, detached HEAD with uncommitted work, dirty tree the executor can't clean up). Stop, mark the abort in the session file's Final state.

On any exit, append the Final-state section to `.vss/sessions/<start-ISO>.md` per `/vss` § Session audit format (Exit reason / End time / Iterations / Commits / Pushed / Escalations / Deferred). Atomic write at exit; do not rely on incremental appends to survive an abort. If aborted by a hard-escalate trigger, write what's known at the abort point, mark the abort in Final state, then exit.

## /vsss safety floor

Even with autonomy turned all the way up, never autonomously:

- Actuate physical hardware.
- SSH out.
- Modify firewall, hooks, settings.json permissions.
- Force-push or delete branches.
- Disable hooks (`--no-verify`, `--no-gpg-sign`).
- Touch `/learnings` (the write-confirm hook will block; respect that).
- Auto-pass a `/vs --fuzzy` subjective-recognisability verdict.
- Edit `init-firewall.sh`, `guard-bash.sh`, `guard-fs.sh`, `settings.local.json` permission lists.
- `git push`. Inherited from `/vss` § Push policy: local commits only by default. User reviews `.vss/sessions/<ISO>.md` and pushes manually, or invokes `/vsss --push-on-pass` to opt in to autonomous push for that single run.

If a wrapped `/vss` iteration tries any of these, the iteration aborts (per `/vss` rules) AND the `/vsss` loop exits per condition 1.

Dispatch rule inherited by every wrapped iteration's subagents: long build/test/ssh runs are foreground with `timeout: 600000`, never `run_in_background`: a backgrounded command's completion notification goes to the chair, not the subagent that launched it, so the subagent parks forever.

## Why `/vsss` exists alongside `/vss`

`/vss` is one bounded unit of work — use it to step away briefly. `/vsss` is "burn the rest of my session productively": hours of session credit spent on the project, with the escalate list catching anything dangerous. Higher blast radius, and more spec-level discipline (the optimiser keeps the loop honest).

Three vacuous iterations are the design saying "nothing useful left to do" — let it stop rather than feeding it noise tasks.

## Reporting back at exit

**At a real exit, and only there.** Before writing a word of this block, name
which numbered exit condition from § Exit conditions has fired. If you cannot
name one, the loop has not ended — run the next iteration instead. The named
condition must be the one that ACTUALLY fired: a stop justified by wall-clock,
window fit, or "the next item needs N cycles" is condition 3, lawful only under
an explicit `--hours`/`--budget` flag, and
must never be reported as a perfection gate. "A version shipped", "a natural
milestone", "I need Martin's input on this bit" and "the context is getting
long" are NOT exit conditions; the pull to report at each is how a run dies
hours early.

When the loop ends (any reason), report to the user:

- Total iterations run.
- Commit count and SHAs.
- Exit reason in plain English.
- One-line note on each commit (sourced from the per-iter blocks in the session file).
- Anything left in escalate-pending state that needs the user.
- An unresolved `--spec-first` checkpoint (task awaiting approval) is listed under `Deferred` with its `/vs --approve <task-id>` line — e.g. `Deferred: task_042 awaiting approval — /vs --approve task_042`.
- Path to the full session audit: `.vss/sessions/<start-ISO>.md` — explicitly named, so the user can open it without guessing the filename.
- Reminder line: "not pushed; review the session file then `git push` if approved" (omit the reminder only if `--push-on-pass` was passed AND the run cleared the perfection-gate).

Lead with `---` before the report block.

**The LAST line of the exit report is `VSSS-EXIT: <exit reason in a few words>`** —
alone on its line, in every runtime, Claude-led and Codex-led alike. It is the
end-of-run marker an unattended supervisor watches for; a report without it
reads as unfinished. Write it once, last, after the bullets above.

## Running under Codex

`$vsss` (`/etc/codex/skills/vsss/SKILL.md`) wraps this file for a Codex-led
session and carries the substitution table for `Agent(...)` and the other
Claude-only primitives it and the wrapped `/vss`/`/vs` use. Role dispatch
becomes `vibe-delegate role <role> --model <model> --cwd <workspace>`.
Unattended runs are driven by `codex-supervisor`: it starts one thread, sends
`$vsss` as the first turn, re-enters with the literal `continue` after every
turn that did not end the run, and stops on the report's `VSSS-EXIT:` line.

---

Read `$ARGUMENTS` below. Run iter 1 of the loop.
