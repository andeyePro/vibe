---
description: Versus Solo — autonomous one-shot. No args = pick from TODO.md (or repo-scan with 5-min redirect window) and execute one item. Args = Opus planner picks the right tool (/vs, /sp, superpower, direct edit) and an Opus executor proceeds, acting in the user's place within a hard-escalate list.
---

# /vss — versus solo

You are top-level Opus. `/vss` runs autonomously: no mid-flow approvals from the user except when an item on the **hard-escalate list** is hit. The point is one bounded unit of work end-to-end without back-and-forth.

`$ARGUMENTS` may be empty (Mode A) or a task brief (Mode B).

## Hard-escalate list (inviolable in both modes)

Stop and surface to the user — do NOT autonomously proceed when:

- **Physical hardware actuation.** Pioreactor pumps, heaters, electrolysis, sparging, any IO that drives chemistry or motion in a real space. "The API works" is not permission.
- **SSH-out.** `ssh`, `scp`, `rsync` over SSH, `sftp`. Per `~/.claude/CLAUDE.md` SSH discipline rule. Firewall permission ≠ behavioural approval.
- **`/vs --fuzzy` subjective verdict.** Anything that hinges on "evokes X", "feels like", "sounds like" is paper-pass until the human confirms recognisability. Surface the verdict, do not auto-accept.
- **Destructive git.** Force-push, branch-delete, `git reset --hard`, hook bypass (`--no-verify`, `--no-gpg-sign`).
- **`/learnings` writes.** The write-confirm hook will block these anyway; don't fight it. Tell the user to run `vibe learn` host-side.
- **Firewall / hook / settings perms.** Edits to `init-firewall.sh`, `guard-bash.sh`, `guard-fs.sh`, `settings.local.json` permission lists.
- **Scope creep beyond the announced plan.** If execution reveals the task is materially bigger than planned, stop and re-plan with the user.
- **Anything explicitly flagged in `~/.claude/CLAUDE.md` or `/workspace/CLAUDE.md`** as needing user authorisation per turn.

If a hard-escalate item triggers, write a one-paragraph status to the user, leave the workspace in a clean state (commit or stash partial work), and stop.

## Acts-as-user defaults

For everything NOT on the escalate list, default like Martin would:

- Yes to commit after passing tests.
- Yes to moving TODO entries from Open to Done.
- Yes to running tests, linters, type-checkers.
- Yes to installing dependencies already declared in package.json / requirements.txt / etc.
- Yes to creating subdirectories the spec implies.
- Plain-English summary before any approval-equivalent juncture (intelligent caveman brevity, no recaps).
- No em dashes in user-facing text. Use en dashes ` – ` per his writing-style memory.
- Lead with literal commands, not abstract instructions.
- Single-line paragraphs (no hard wrap) in any markdown intended for him to paste.

Read `MEMORY.md` at start; surface relevant feedback memories into the planner brief so the plan matches Martin's preferences before any execution.

## Mode A — no arguments

1. Read `TODO.md`. Find the first `[ ]` item under `## Open` that is **bounded**: single-PR-sized, no external dependencies, no hard-escalate dependencies (no physical actuation, no SSH-out, no firewall edits).
2. **If found:** announce the item in plain English (one paragraph, what + why-bounded). Begin work immediately. On completion: mark `[x]` with a one-line note + commit SHA, commit, stop.
3. **If no bounded item found:** scan the repo to decide the best next thing to do to improve it. Categories to consider, in order:
   1. Failing tests / lint warnings on `main` that nobody's fixed.
   2. TODO.md `[!]` entries where the failure cause is now solvable (re-attempt-worthy).
   3. Documentation drift: README, CLAUDE.md, MANUAL-TESTS.md vs actual code state.
   4. Dead code / unused exports.
   5. Performance or readability wins under 50 lines of diff.

   Announce the top candidate with one-line rationale (lead with the literal action). **At the moment of announcement, ring the terminal bell to surface the wait window to the user**: `Bash(command: "printf '\\a' >&2", description: "vss A-mode notify – bounce terminal icon + audio cue")`. The bell character maps to a system sound + dock-icon bounce in Ghostty / Terminal.app / iTerm — vibe already uses this idiom for idle hooks (see `vibe` line ~1043). One bell per announcement; do not spam.

   **The announcement MUST include explicit instructions on how the user can skip the wait, approve the plan, and continue immediately.** Add a final line in the announce message in this exact shape (or trivially equivalent — the substance must be present):

   ```
   Type `go` to skip the 270s wait and proceed immediately, or send any other
   message to redirect. Silence for 270s = auto-proceed with the announced item.
   ```

   Then `ScheduleWakeup(delaySeconds=270, reason="vss A-mode 5-min redirect window")` — under the 5-min cache TTL. **The semantics**:

   - **Auto-proceed**: scan the repo, decide the best next thing to do, announce, wait 270s, execute the announced item if no human response arrives within the window. The spec calls this "5-min" colloquially; the actual wait is 270s for cache discipline.
   - **Skip-and-go**: if the user replies with any of the recognised approval phrases — case-insensitive match against `go`, `y`, `yes`, `ok`, `proceed`, `approve`, `approved` — execute the announced item immediately. No further wait. Treat the approval message as ratification of the announced plan.
   - **Redirect**: if the user replies with anything ELSE (any text not matching the approval phrases above), abandon the announced item and follow the user's redirect verbatim. The redirect IS the new task; restart Mode A's decision flow against it.
   - **Cancel**: if the user types only `n`, `no`, `cancel`, `stop`, or `abort` (case-insensitive), abandon without executing the announced item AND without redirecting. Surface a one-line confirmation and stop.

   Whichever branch fires, record the outcome in the session file's iter block as `auto-proceeded` / `user-approved-immediately` / `user-redirected-to <new task>` / `user-cancelled`. The wait-skip information surfacing in the announce is a hard requirement — Martin asked for it explicitly 2026-05-07; a regression silently dropping the instruction is a failure.

Mode A always does **exactly one item**, then stops. For autonomous looping use `/vsss`.

## Mode B — arguments given

`$ARGUMENTS` is the task brief.

### Step 1 — Opus planner

Dispatch `Agent(subagent_type: "general-purpose", model: "opus")` with this brief:

> You are the planner for `/vss`. Decide the single best execution mode for the task below. Options:
>
> - `/vs` (rigorous) — task has mechanical acceptance criteria a Tester can verify. Tests can be written. Pass/fail is automatic.
> - `/vs --fuzzy` — adversarial review needed but no test gate possible. Reviewer judgment, not mechanical.
> - A specific Superpowers skill (name it: brainstorming, writing-plans, test-driven-development, subagent-driven-development, etc.) — when the task fits a Superpowers methodology cleanly.
> - `/sp` — when broad Superpowers discipline applies but no single skill dominates.
> - **Direct in-session edit** — task is small, concrete, mechanically bounded. Most documentation, single-file changes, and config updates fall here.
>
> Output: chosen mode, one-line rationale, and the literal command or flow the executor will run. Read `MEMORY.md` and apply Martin's preferences (intelligent caveman brevity, robust-100%-solutions-pre-alpha, no em dashes, concrete commands).
>
> Task: `$ARGUMENTS`

### Step 2 — Announce the plan

Lead with `---` (horizontal rule before review-able artifact). Then 4–7 plain-English bullets covering: chosen mode, rationale, files affected (best estimate), hard-escalate triggers anticipated, expected commit count.

End with: `Proceeding.`

Do NOT wait for user approval. The whole point of `/vss` is unattended execution.

### Step 3 — Execute

Either run the chosen flow inline (you are Opus) or dispatch `Agent(subagent_type: "general-purpose", model: "opus")` as the executor. Either way, the executor inherits the hard-escalate list and the acts-as-user defaults from this command.

Executor may dispatch its own subagents (Sonnet for generation, Haiku for mechanical tests) per the methodology of the chosen mode. The escalate list propagates: every subagent at every level honours it.

### Step 4 — Close out

On completion:

- Move the implicit task to `TODO.md` `## Done` with a one-line note + commit SHA. (Add to `## Open` first if Mode B was invoked without a pre-existing entry — keep the audit log honest.)
- Commit any uncommitted work. Use the project's commit-message convention.
- Report back: what was done in 2–3 lines, what was NOT done if any escalate triggered, and the final commit SHA.

## State directory: `.vss/`

Created at repo root.

- `.vss/sessions/<ISO8601-UTC-start>.md` — per-session detailed audit trail. **Committed.** One file per `/vss` or `/vsss` invocation. Format below. This is the canonical audit Martin reviews; do not skip writing it.
- `.vss/last-plan.md` — Mode B planner output for the most recent run. **Gitignored.** Useful for debugging when the executor goes off-track.

`/vss` does not need any other state files. The chosen mode (`/vs`, `/sp`, etc.) brings its own state directory if applicable.

### Session audit format

Every `/vss` invocation writes `.vss/sessions/<start-ISO>.md` (filename uses `T` separator and replaces `:` with `-` for filesystem portability — e.g. `2026-05-07T14-29-02Z.md`). Sections:

```markdown
# /vss session <start ISO8601 UTC>

## Mode
A or B

## Args
$ARGUMENTS verbatim, or "(none)" for Mode A

## Initial plan
[the announce block — 4-7 plain-English bullets]

## Iter <N> — <one-line label>
**Plan**: ...
**Files touched**: list
**Commit**: <SHA> — <first line of message>
**Outcome**: success / failure-and-reason / abandoned-with-reason / redirected-by-user
**Notes**: anything noteworthy

## Final state
**Exit reason**: ...
**End time**: <ISO8601 UTC> (~<N> minutes wall)
**Iterations**: <N>
**Commits**: <count> (SHAs: ...)
**Pushed**: no / yes (only if user passed --push-on-pass or pushed manually after)
**Escalations**: none / [list with reasons]
**Deferred**: [list of items I declined to touch and why]
```

For `/vss` (single-shot), there is exactly one Iter section. For `/vsss` (loop wrapper) there are many.

Write the file ATOMICALLY at exit — not incrementally — so a partial-write doesn't leave a malformed audit. If the run is aborted by a hard-escalate trigger, write what you have at the abort point, mark the abort in Final state, then exit.

## Push policy

**Do NOT `git push` autonomously after `/vss` or `/vsss` completes.** Local commits land on the working branch (typically `main`). The user reviews the session audit at `.vss/sessions/<ISO>.md`, optionally inspects `git log` and per-commit diffs, and pushes manually with `git push` (or rejects and `git reset --hard <pre-session SHA>`).

**Rationale**: autonomous push leaks unreviewed AI work to the remote. Local commits are reversible (`git reset HEAD~N`); pushed commits are not without force-push semantics, which the hard-escalate list forbids. The audit-trail-first / push-second order is the trust model.

**Override**: `/vss --push-on-pass <task>` or `/vsss --push-on-pass <task>` opts in to autonomous push for that single invocation, only if the run completes without escalation triggers AND the optimiser (in `/vsss`) reaches a clean perfection-gate exit. A user passing `--push-on-pass` is explicitly accepting the un-reviewed-push trade-off for that run.

Default is no push. Always.

## Why `/vss` exists alongside `/vs` and `/sp`

`/vs` is rigorous adversarial review for a single feature with verifiable criteria. `/sp` is Superpowers discipline applied broadly. Both still expect the human to direct the flow turn-by-turn.

`/vss` is the autonomous wrapper: pick the right tool, run it, deal with the predictable in-flow choices the way Martin would. Use `/vss` when you want to step away. Use `/vs` or `/sp` directly when you want to drive.

---

Read `$ARGUMENTS` below. If empty, start at Mode A. If non-empty, start at Mode B Step 1.
