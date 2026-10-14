# Codex unattended /vsss

This Codex-only contract overrides the shared command's launcher, loop,
clock and Stop-hook paragraphs. Claude keeps its existing command and hooks.

## Start or resume

Before creating a session audit or changing project files, run
`codex-autonomy context --cwd <project-root>`. With `supervised: true`,
continue the shared /vsss loop in this thread. Never launch a nested runner.
A supervisor using a custom state path names it in thread instructions: pass
`--state <path>` to context/status/stop and add `supervisor_state=<path>`
to your owned auto-resume marker so the Stop hook routes to that supervisor.
Otherwise write a private project-local prompt file starting with `$vsss`,
followed by the user's complete arguments and relevant conversation decisions,
then run `codex-autonomy start --cwd <project-root> --prompt-file <file>`.
Do not substitute a vague reference to an earlier conversation: the supervised
thread is separate. Checkpoint any current edits before transfer. If this
invocation already has an unfinished audit, carry `$vsss --resume` and its
path in the brief so the worker resumes it, rather than creating a conflict.

A successful handoff prints its state and log paths. Stop editing this
workspace and tell the user it is running unattended. This is a transfer,
not task completion: do not print VSSS-EXIT, invent a perfection gate or run
another implementation in the interactive chair. If you wrote a parent-owned
`.vss/auto-resume`, deactivate it before transfer and record the handoff in
its audit. Do not overwrite the worker's marker after transfer.

The skill performs the interactive handoff; it is model-mediated. Explicit
`codex-autonomy start` or host `vibe --codex-run <prompt-file>` is deterministic.
A conflicting/stale owner refuses launch. Inspect status and reconcile; never
remove someone else's lock or quietly create a second writer. An unfinished
supervisor checkpoint uses host `vibe --codex-resume` with the original saved
prompt, not a new prompt. The saved handoff prompt is
`.vss/codex-supervisor.json.prompt.txt`.

`codex-autonomy status --cwd <root>` shows ownership and paths;
`codex-autonomy stop --cwd <root>` cooperatively stops the runner, including
retry waits. `codex-supervisor status/stop --state <path>` also works for an
active child. Private output is `.vss/codex-supervisor.json.runner.output.log`.
The detached runner survives the initiating tool and terminal closing. It does
not survive container shutdown, host reboot or death of the outer runner;
those require explicit ownership reconciliation before resuming.

## Continuation and clocks

The supervisor owns the loop. A completed turn is a checkpoint, not the end
of the run. Codex's Stop hook allows the owned supervisor to receive it and
validate completion or submit the next turn. An unsupervised owned vsss
marker has no fourth-stop or Final-heading escape: hand off as above.
An explicit user stop deactivates the owned marker and always takes precedence.

Default five hours only estimates a credit window. An explicit leading
`--hours N` or `--budget Nh|Nm` cap measures elapsed UTC seconds from the
original supervisor start, including downtime; `--hours` wins. Never reset it
on recovery. Put options before the task text. The supervisor enforces this
cap as well as its separate runaway ceilings. Reaching a ceiling checkpoints
unfinished work; it is never a perfection gate. Routine questions go to FM2C;
continue independent authorised work. Claude-only wakeup/budget prose does
not override these rules.

## Completion evidence

The final `VSSS-EXIT:` line requests validation; it cannot terminate a run by
itself. Read `.vss/codex-supervisor.json` for `completion.runId`, `threadId`,
`promptHash` (SHA-256 of original prompt bytes) and `startedAt`. For a custom
supervisor state path, use that path throughout. Finish the canonical session
audit first, then atomically write `<state-path>.completion.json` using a
temporary file and rename. Required JSON fields:

```
{
  "version": 1,
  "runId": "copy completion.runId",
  "threadId": "copy threadId",
  "turnId": "copy unresolvedTurn.turnId",
  "promptHash": "copy promptHash",
  "startedAt": 0,
  "at": 0,
  "sessionFile": ".vss/sessions/<session>.md",
  "auditSha256": "SHA-256 of the exact audit bytes",
  "condition": 2,
  "reason": "perfection gate: brief and independent follow-ups covered",
  "evidence": ["exact audit text identifying completed verification"],
  "verification": "passed",
  "optimiser": "exact audit text with concrete optimiser rationale",
  "remaining": []
}
```

Use actual epoch seconds for `startedAt` and `at`; copy original `startedAt`
unchanged. Audit must contain `## Final state`, reason and every evidence
string. Condition 2 additionally requires `verification: passed`, the
optimiser rationale in the audit and an empty actionable `remaining` array.
For condition 1 include `trigger`: hardware, ssh, subjective-verdict,
destructive-git, learnings, permissions, paid-dispatch, scope, verification,
or explicit-authority. For condition 3 the original explicit cap must really
have elapsed. For condition 4 the last three `## Iter` audit blocks must each
contain literal lines `Outcome: no-op` and `Commits: none`; include `questions`
as an array of exact audit references to the unanswered questions (empty
only if no question blocks work). Condition 5 needs `destructiveState` with
the actual unrecoverable Git state. All conditions require evidence.

Missing/stale/malformed evidence yields a continuation explaining what is
missing. Do not manufacture evidence to satisfy the validator. These checks
establish audit consistency, not an independent proof of semantic perfection.
The supervisor records accepted evidence in its terminal checkpoint. Legacy
completed checkpoints stay completed; unfinished legacy runs gain this check.

## Recovery

Transient retry limits count consecutive errors; a successful turn resets
the streak, while total retries remain in telemetry. The outer Linux runner
owns the supervisor's entire child tree. It may restart only after its
subreaper confirms every descendant ended, retaining original run state and
budgets. Foreign/stale locks are never stolen.

For a known interrupted turn, recovery first uses read-only `thread/read`
and requires that exact thread's last turn to be completed. It processes the
saved result, then continues; it never resends the original prompt. Unknown
turn IDs, incomplete/failed/interrupted turns or unavailable proof remain
checkpointed for explicit effects review. Successful tool effects are never
blindly replayed. A runner crash loop is bounded independently of model
retries. Status, stop requests and logs remain available during retry waits.


## Validation details

Time-cap grammar is `N = digits[.digits]`, positive and finite, with resulting
seconds at most Number.MAX_SAFE_INTEGER; `--budget` adds literal `h` or `m`.
No signs, exponent notation or leading decimal point. The first occurrence
of each cap option is parsed; later occurrences of that same option are
ignored. When both are present, the first `--hours` wins over `--budget`.
Only the initial whitespace-separated option sequence after `$vsss` or
`/vsss` counts, including options after `--resume`; task prose and unknown
options end this scan. Known non-cap options are skipped (including the
optional numeric width after `--wide`). Invalid first cap values refuse the
run. This parser establishes cap authority, not a full shared-skill flag parser.

The supervisor mints a UUID `completion.runId`; threadId and the pending
turnId come from app-server acknowledgements. Identity fields in evidence
must exactly equal the current state, including promptHash and integer
startedAt. `context` recognises ownership only when its CODEX_THREAD_ID equals
the state threadId, cwd equals the canonical checkout root, and that state's
version-1 UUID-token ownership lock is currently heartbeating. All other
existing locks are conflicting, including stale locks. Matching context means
continue in the existing worker, never launch again. The shared audit rules
define an unfinished audit: an Iter section without Final state.

Evidence fields `version`, `condition`, `at` and `startedAt` are numbers:
version must be 1, condition an integer 1–5, and at a safe integer from the
original start through current time plus five seconds. runId/threadId/turnId/
promptHash must match state exactly. reason, evidence entries and optimiser
are nonblank strings. evidence is a nonempty array; every entry and reason
must occur literally in the audit. Condition 2 requires verification equal
to `passed`, optimiser present in the audit and an empty remaining array.
Condition 3 additionally checks the original time cap. Condition 4 requires
three final consecutive numbered Iter blocks, exact no-op/no-commit lines and
a questions array whose entries occur in the audit; it may be empty when no
question blocks work. Condition 1 requires one of the listed trigger enum
values; condition 5 requires a nonblank destructiveState description. These
last two declare the shared workflow's escalation judgement; they are not
a machine proof of hardware, permissions or Git state. Additional fields are
permitted but cannot change these predicates.

sessionFile must match `.vss/sessions/[A-Za-z0-9._-]+.md` exactly. Absolute
paths and traversal components are rejected. Its resolved path must equal
the path joined to the canonical checkout; symlinked parents are rejected at
that check. The file is opened with O_NOFOLLOW, must be regular with link count
1 and at most 16 MiB; content and hash are read from that same descriptor.
The completion file has the same regular-file checks. These checks do not
create a new filesystem sandbox or forbid existing mounted directories;
the container's normal permissions remain authoritative. Concurrent hostile
parent-directory replacement is outside this consistency protocol.

Write the audit as UTF-8. Hash its exact bytes with SHA-256. Write evidence to
a new mode-0600 temporary file in the state file's directory, fsync it, rename
it over `<state>.completion.json`, and fsync that directory. A stale record
may be replaced; its old run/turn identity cannot complete a new turn. The
reader sees either complete version after atomic rename and rejects partial
JSON. The supervisor itself uses fsynced atomic state writes; it does not
claim to infer how a model created a submitted file.

For a stale outer-runner or handoff lock, first independently verify all
previous owners and descendants for this checkout have ended (stopping its
container is one way to establish container-process termination). An operator
may then remove only the identified stale `<state>.runner.lock`,
`<state>.handoff.lock`, `<state>.lock` and their matching token-specific stop
files. No automatic command steals these records. If the checkpoint has an
uncertain turn, use `codex-supervisor reconcile --state <state> --evidence-file
<private-json>` after reviewing effects; its help specifies the checkpoint
hash and explicit effectsReviewed/safeToContinue fields. It takes the now-free
state lock, records that evidence and changes unresolved state to a checkpoint
without sending any model request. Only then resume the original prompt with
`vibe --codex-resume`. Automatic recovery remains limited to the exact completed
turn proof described above; missing proof is never permission to replay.
