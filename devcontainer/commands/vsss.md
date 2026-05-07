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
3. Set `BUDGET_HOURS=5` unless the user passed an explicit budget in `$ARGUMENTS` (e.g. `/vsss --budget 2h <task>`). 5h is intended to consume a full Pro/Max session when `/vsss` is invoked at session start. There is no graceful-shutdown cushion — if the loop is approaching the limit, the optimiser should bias toward "stop the loop" (perfection gate) so pending work is committed cleanly before the cap rather than mid-iteration. If you want a softer cap, pass `--budget 4h` explicitly.
4. Write `.vss/loop.md` with a header line: `# /vsss session — start <ISO8601 UTC> – budget <Nh>`.

Every iteration appends one line to `.vss/loop.md`: `<iter#> <ISO8601> <mode A|B> <one-line summary> <commit SHA or "no-op">`.

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
5. **Destructive-state signal.** If git is in an unrecoverable state (merge conflict, detached HEAD with uncommitted work, dirty tree the executor can't clean up). Stop, leave a status note in `.vss/loop.md`.

On any exit, write a final-state line to `.vss/loop.md`: `# session ended <ISO8601 UTC> – exit reason: <reason> – iterations: <N> – commits: <M>`.

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

If a wrapped `/vss` iteration tries any of these, the iteration aborts (per `/vss` rules) AND the `/vsss` loop exits per condition 1.

## Why `/vsss` exists alongside `/vss`

`/vss` is one bounded unit of work. Use it when you want to step away briefly. `/vsss` is "burn the rest of my session productively" — when you have hours of session credit, want it spent on the project, and trust the escalate list to catch anything dangerous. Higher blast radius, more discipline required at the spec level (the optimiser is what keeps the loop honest).

If the loop produces three vacuous iterations, that's the design saying "nothing useful left to do" — let it stop. Don't keep feeding it noise tasks.

## Reporting back at exit

When the loop ends (any reason), report to the user:

- Total iterations run.
- Commit count and SHAs.
- Exit reason in plain English.
- One-line note on each commit (from the rolling log).
- Anything left in escalate-pending state that needs the user.

Lead with `---` before the report block.

---

Read `$ARGUMENTS` below. Run iter 1 of the loop.
