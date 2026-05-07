---
description: Versus Super Solo — runs /vss on the given args, then optimises args and loops /vss in argumentless A-mode until perfection-gate, session-credit exhaustion, or a hard-escalate trigger. Higher blast-radius than /vss; intended for end-of-day "burn the rest of my session productively" runs.
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
2. Read `MEMORY.md` for `feedback_autonomous_session_protocol` and `feedback_default_to_local_time_for_uk_user`. Apply both.
3. Set `BUDGET_HOURS=5` unless the user passed an explicit budget. Recognised flags (in order of precedence; first match wins):
   - `/vsss --hours N <args>` — canonical. `N` is a positive integer or decimal (e.g. `2`, `2.5`, `0.5`). Sets the budget cap to `N` hours from `START_TIME`.
   - `/vsss --budget Nh <args>` — backward-compatible alias. Same semantics; `Nh` parsed as a positive integer or decimal followed by literal `h`.
   - `/vsss --budget Nm <args>` — minutes form, for short-runs (e.g. `--budget 30m`).
   - No flag → 5h default. Intended to consume a full Pro/Max session when `/vsss` is invoked at session start.

   There is no graceful-shutdown cushion — if the loop is approaching the cap, the optimiser should bias toward "stop the loop" (perfection gate) so pending work is committed cleanly before the cap rather than mid-iteration. If you want a softer cap, pass `--hours 4` explicitly.
4. Open `.vss/sessions/<start-ISO>.md` (filename uses `T` separator and replaces `:` with `-`, e.g. `2026-05-07T14-29-02Z.md`) and write the audit header per the format defined in `/vss` § Session audit format. The Initial-plan section captures the initial args, priority queue (if any), and budget.

Every iteration appends a full Iter section to the session file (Plan / Files touched / Commit / Outcome / Notes). Final-state line is appended at exit.

The session file is the single canonical audit Martin reviews. There is no separate roll-up index.

## Resumption protocol (after out-of-tokens halt or interrupted session)

A `/vsss` session can be killed by token-exhaustion, a manual interrupt, or any unhandled error. Without a resumption protocol the work in flight is dropped — partial commits sit on `main`, the priority queue is forgotten, the user has to re-issue the original `/vsss` invocation. Resumption fixes that.

### State that survives a halt

The session file at `.vss/sessions/<start-ISO>.md` is the persistence layer. After every iter completes (Generator commit landed, Tester commit landed, optimiser verdict written), the iter block in the session file is up to date. If the session halts, that file's most recent iter block plus the absence of a `## Final state` section is the signal "this session was alive when killed".

### Detecting an in-progress session at startup

When `/vsss` is invoked (with any args, or `--resume`), Planner first scans `.vss/sessions/*.md` for **in-progress sessions**: files where the most recent section is an `## Iter <N>` block (any iter) and there is NO `## Final state` section yet. If one or more found, sort by start-ISO descending and inspect the most recent.

Three branches:

- **`/vsss --resume` flag passed**: load the most recent in-progress session and resume it. The original args, priority queue, budget, and remaining-iter context all come from that file. Continue from the iter AFTER the most recent committed one.

- **`/vsss <new args>` invoked while an in-progress session exists**: surface the conflict to the user. Two reasonable resolutions: (a) `--resume` to pick up the in-progress one, OR (b) explicitly mark the in-progress session as halted (write a Final state section with `Exit reason: superseded by new /vsss invocation` and start fresh). Per `/vss`'s hard-escalate list this is "scope-creep beyond announced plan" — do NOT auto-pick; surface to the user. (User has Q1=a authorisation? They still need to disambiguate this case explicitly; the new args might not match the parked session's queue.)

- **`/vsss` with no args, no in-progress session**: normal Mode A start.

### Resume budget arithmetic

The in-progress session's `START_TIME` is preserved. Resumption does NOT reset the clock. If the original budget was 5h and 3h have already been consumed (the session halted after running, then the user resumed via `vibe --continue`), the resumed `/vsss` has 2h of budget remaining. The session file's header line (`# /vsss session — start <ISO> – budget Nh`) plus current `date -u` lets Planner compute remaining time.

If remaining budget is negative (clock-wall exceeded the original cap during the halt period), Planner asks the user whether to extend the budget (`/vsss --hours N --resume` to extend to N hours total, NOT N additional hours) or finalise the session with whatever's been committed.

### Resumption procedure

1. Read `.vss/sessions/<resumed-ISO>.md` end-to-end. Identify last completed iter and pending state.
2. Read `git log` since session start (`git log --since="<start-ISO>" --oneline`) to verify the iter blocks match the actual commits. If they don't (e.g. iter block claims commit X but `git log` shows X was reverted), surface to the user — DO NOT silently proceed.
3. Compute remaining budget. If positive, continue. If negative, escalate.
4. Append a new `## Resumption — <ISO>` block to the session file noting: timestamp of resumption, hours-elapsed-during-halt, budget-remaining, the iter we're picking up at.
5. Continue the loop from the next iter per the original priority queue / optimiser logic.

### Auto-resume across halts (host-launcher feature, NOT in this spec)

The user's stated long-term goal: automatic continuation across N out-of-session-tokens halts without manual `vibe --continue` invocation. This requires host-side launcher integration:

- A marker file (e.g. `.vss/auto-resume.json` containing `{ "active": true, "remaining_halts": N, "session_file": "<path>" }`) written by `/vsss --auto-resume N`.
- The vibe launcher (`/workspace/vibe`) checking the marker on every container start. If `active: true` and `remaining_halts > 0`, the launcher invokes `claude --continue` automatically and decrements the counter.
- Exhaustion detection: when claude session ends, the launcher distinguishes "session ran out of tokens" (auto-resume eligible) from "user typed /exit" (do not auto-resume; clear marker). Heuristic: if claude's exit code or last-stderr indicates 5h-cap-hit, treat as token exhaustion.

This requires changes to `/workspace/vibe` (host-side bash) and possibly to the Mac-side `~/.zshrc` wrapper. **Out of scope for the `/vsss` slash-command body.** Tracked as a separate TODO entry.

## Loop structure

```
iter 1:  /vss $ARGUMENTS                      (Mode B if args, else A)
opt:     Opus optimiser proposes refined args, OR returns "satisfied"
iter 2:  /vss <optimised args>                (Mode B with optimised args)
         OR /vss                              (Mode A — no args)
...
iter N:  loop continues until exit condition
```

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
> Original args: `<args>`
> Diff stat: `<git diff --stat HEAD~1>`
> Iteration commits: `<git log --oneline HEAD~N..HEAD>`
> Notes from executor: `<executor's report>`

Apply the optimiser's decision. If it returned "stop", exit cleanly.

## Exit conditions (any one ends the loop)

In priority order — check each at the start of every iteration:

1. **Hard-escalate triggered inside any iteration.** Stop immediately. Surface the trigger reason.
2. **Optimiser returns "stop the loop"** (perfection gate).
3. **Session credit exhaustion signal.** Operationalised as: `(date -u +%s) - START_TIME` exceeds `BUDGET_HOURS * 3600`. Default 5h consumes a full Pro/Max session when `/vsss` is invoked at session start.
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

## Why `/vsss` exists alongside `/vss`

`/vss` is one bounded unit of work. Use it when you want to step away briefly. `/vsss` is "burn the rest of my session productively" — when you have hours of session credit, want it spent on the project, and trust the escalate list to catch anything dangerous. Higher blast radius, more discipline required at the spec level (the optimiser is what keeps the loop honest).

If the loop produces three vacuous iterations, that's the design saying "nothing useful left to do" — let it stop. Don't keep feeding it noise tasks.

## Reporting back at exit

When the loop ends (any reason), report to the user:

- Total iterations run.
- Commit count and SHAs.
- Exit reason in plain English.
- One-line note on each commit (sourced from the per-iter blocks in the session file).
- Anything left in escalate-pending state that needs the user.
- Path to the full session audit: `.vss/sessions/<start-ISO>.md` — explicitly named, so the user can open it without guessing the filename.
- Reminder line: "not pushed; review the session file then `git push` if approved" (omit the reminder only if `--push-on-pass` was passed AND the run cleared the perfection-gate).

Lead with `---` before the report block.

---

Read `$ARGUMENTS` below. Run iter 1 of the loop.
