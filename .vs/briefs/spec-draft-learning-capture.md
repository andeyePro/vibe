# /vs spec draft — automatic learning capture (Tier 1)

**Status:** draft, not for execution now. Source: `TODO.md` Open ("`vibe learn` is a manual capture command, not the auto background system users expect"); roadmap Tier 1. Evidence at `5125e3c`.


## The gap

Martin: *"I assumed it would be operating in the background saving all my preferences across all projects."* Capture is manual — `/learn <pattern>`, or `learnings.md`'s `Y / n / never-ask` prompt on a `feedback` memory save. Both need the model to *notice it was corrected*, and the model that just ignored a correction is the worst judge of that.

## Shape

**A deterministic hook records candidates; the model distils them later; `/learnings` is still written only behind `guard-fs.sh`.**

### (a) `devcontainer/learn-candidate.sh` → `/usr/local/bin/`

A `UserPromptSubmit` hook — a guard-class script `COPY`d in `Dockerfile`, not `devcontainer/hooks/` (the *unwired* opt-in Stop pair). Reads hook JSON on stdin, tests `.prompt` against an anchored ERE — `^(no,? |actually,? )?(don'?t|never|stop|always) `, `^you (should|shouldn'?t|must|need to|always|never) `, `^i (told|asked) you `, `from now on|in future|every time you` — and appends one line to `/workspace/.vibe/learn-candidates.md`:

`- [ ] 2026-09-02T14:03:11Z · <session-id> · "don't use em dashes"`. It prints **nothing** (UserPromptSubmit stdout is injected into the model's context, so silence is mandatory) and always exits 0.

### (b) False-positive control

The regex is deliberately dumb: precision is recovered at sweep time by a model reading the batch, so a false positive costs one line in a file nobody reads until then. Four filters keep it small — prompts ≤ 400 chars only (a long one containing "don't" is a task spec); skip `/` and `!` prompts; skip duplicates; stop at 20 lines.

### (c) Trust model

The hook writes to `/workspace/.vibe/`, **never** `/learnings`. `.vibe/` is in the managed `.gitignore` block, so raw user prose never reaches a remote. Both gates survive — the model's `Y/n` on a distilled rule, then `guard-fs.sh`'s per-write prompt. No new write path into the library.


### (d) `/learn --sweep`, and `--review` Step 0

`--sweep` is the lightweight pass: read the file, cluster, propose **one distilled rule per cluster** (never the verbatim prompt — that is where the PII is), each through the existing semantic check, `Y/n`, then the normal Write; truncate on completion. `--review`, the whole-library pass, calls `--sweep` as its Step 0.

### (e) When the prompt fires; wiring

`claude-md/learnings.md` loses the per-memory inline prompt: ask once, with the whole batch, on a session-closing signal. Backstop for abrupt exits — one launcher stderr line next launch when the file is non-empty (`✎ 4 learning candidates pending — /learn --sweep`), beside the task_012 review hint.

The launcher's `settings.local.json` heredoc (`vibe:3562`) gains the `UserPromptSubmit` entry — vibe owns that file, so this ships enabled without touching `~/.claude/settings.json`. Wired only when `learning_is_enabled` and not `learning_project_opted_out`; `VIBE_LEARN_CAPTURE=0` disables.

## Acceptance criteria

1. `code-check.py` clean; `smoke-test.py` green, no test deleted.
2. Fixture table: ≥12 corrections fire; ≥12 non-corrections (task specs, questions, long prompts containing "don't", `/…`, `!…`) do not.
3. Hook emits zero stdout bytes and exits 0 for every fixture, match or not.
4. Appended line matches `^- \[ \] <ISO8601Z> · [^ ]+ · ".*"$`; prompt truncated to 200 chars, newlines → spaces.
5. Duplicate normalised prompt appends nothing; 21st distinct candidate appends nothing.
6. Hook writes only under `/workspace/.vibe/`; a test asserts no `/learnings` path in the script.
7. Rendered `settings.local.json` carries the entry when the library is enabled; omits it under `VIBE_LEARN_CAPTURE=0`, `.no-learn`, or no library.
8. Launcher banner prints once when the file is non-empty, silent otherwise, exits 0 either way.
9. `learn.md` documents `--sweep` and `--review` Step 0; `learnings.md`'s inline prompt becomes the batch rule; README:11 drops "planned".
10. **[M]** Live: correct Claude twice, exit, relaunch, see the banner; `/learn --sweep` reaches one hook prompt per accepted rule. → MANUAL-TESTS.

## The one question for Martin

Detection at **hook level** (deterministic regex) or **model level** (the fragment asks Claude to log candidates)? **Recommend hook level:** zero tokens, unit-testable, and it fires precisely when the model failed to notice — the case that produced the complaint. The fragment may *also* append to the same file in the same format when it spots one the regex missed. The hook is the floor, not the ceiling.
