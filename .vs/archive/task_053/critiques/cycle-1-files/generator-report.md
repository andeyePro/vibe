# task_053 — Generator report (cycle 1)

## Files created

- `devcontainer/codex-prompt-prefix.sh` — new hook script, 41 lines, `#!/bin/bash`, `set -euo pipefail`, fixed PATH, `unset BASH_ENV ENV`. Reads `UserPromptSubmit` JSON on stdin via `jq`, takes `.prompt`, splits it with `read -r first rest` (trims leading whitespace, preserves the rest verbatim). Matches `first` against exactly `/vs`, `/vss`, `/vsss` (bash `case`, no globbing → exact string match, case-sensitive). On match, emits `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"..."}}` via `jq -n --arg name --arg rest`. On no match, empty stdin, or non-JSON stdin: no output, exit 0 in every path. No `dangerously`, no ` -c ` literal. Shellcheck-clean.

## Files changed

- `devcontainer/codex/hooks/hooks.json` — added a `UserPromptSubmit` group (no `matcher` key — there is no tool to match on a prompt), one command `/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-prompt-prefix`, `timeout: 10`, no `async`. `PreToolUse` group unchanged.
- `devcontainer/codex-guard-liveness.sh` — check (a): new `prompt_prefix=$bin/codex-prompt-prefix` variable + `check_owned "$prompt_prefix"`. Check (c): `hook_form` regex changed to the exact grouped form from the spec (`^...(codex-guard-adapter (bash|patch)|codex-prompt-prefix)$`); the loop now uses `[[ $hook_command =~ $hook_form ]]` + `BASH_REMATCH[1]` to capture which alternative matched, then `${hook_program%% *}` to get the binary name, so `hook_target` resolves correctly for **both** programs instead of being hardcoded to `codex-guard-adapter`. Header comment for check (c) updated to match.
- `devcontainer/Dockerfile` — `COPY --chown=root:root codex-prompt-prefix.sh /usr/local/bin/codex-prompt-prefix` added next to the task_046 adapter/liveness COPY lines, with a short rationale comment; added to the `chmod +x` list in the same `RUN` as the rest of the Codex chain.
- `devcontainer/codex/skills/{vs,vss,vsss}/SKILL.md` — "The `/` form" section rewritten: only `$<name>` is a **guaranteed** match (composer rejects a bare `/<name>` before submission); a leading-space ` /<name> …` line also works (composer passes it through as plain text, trims the space) and a managed `UserPromptSubmit` hook then adds context pointing the model at the `$<name>` skill — model-mediated, not deterministic, so `$<name> …` remains the reliable form. Wording chosen to also satisfy the existing task_047 smoke assertions verbatim (see Testing below) while being accurate about the new route. No `/prompts` mention.
- `README.md` — "Skills in a Codex-led container" paragraph gains two sentences (before the `/vs --panel N` sentence, so the existing `Test 55` substring-position check is unaffected): the leading-space mechanism, and an explicit withdrawal of the `/prompts:`-based idea (nothing is written to `~/.codex`).
- `docs/codex-integration-plan.md` — F6 gains an addendum (task_053, Spec Critic 2026-09-11 attribution) citing `tui/src/bottom_pane/slash_commands.rs` (only `SlashCommandItem::{Builtin, ServiceTier}`, no user-prompts variant, nothing under `codex-rs/` reads a `prompts/` dir) and `tui/src/bottom_pane/chat_composer/slash_input.rs:71-87` / `chat_composer.rs:3064,494,3079-3082` (the leading-space mechanism). D3 fully rewritten to the shipped design (leading-space pass-through + `codex-prompt-prefix` hook, model-mediated, `$vs` remains the one guaranteed form, nothing written to the Mac). Also touched the "Deliberately not built" out-of-scope bullet that referenced "the `/prompts:vs` route in D3 is his call" — updated for consistency since it directly contradicted the rewritten D3 (not separately named in AC4, but leaving it would have made the doc self-contradictory).
- `MANUAL-TESTS.md` — Test 55 gains one step: new step 4 "The leading-space `/vs` form (task_053)" under "The Codex-led launch itself", renumbering the old 4/5/6 to 5/6/7 and updating "Six further steps" → "Seven further steps". The **Pass:** summary line at the end of Test 55 gained a clause naming the new step, for consistency.
- `TODO.md` — "Martin's answers of 2026-09-11" entry (b) checked against the shipped design: already accurate (leading-space pass-through, `UserPromptSubmit` hook pointing at `$vs`, model-mediated, no Mac write). No edit made — it was not stale.
- `smoke/checks_18_codex_runtime.py` — the two permitted edits only:
  1. `_codex_liveness_fixture`'s copy tuple gains `("codex-prompt-prefix", PROMPT_PREFIX)` (new `PROMPT_PREFIX` constant declared next to `CODEX_ENTRY`), so the fixture chain has the new script the ownership check now requires.
  2. `test_codex_hooks_json_ac3`: the event-set assertion changed from `{"PreToolUse"}` to `{"PreToolUse", "UserPromptSubmit"}`; added assertions on the new `UserPromptSubmit` matcher group — exactly one group, one hook entry, `type == "command"`, the exact hardened `codex-prompt-prefix` command string, `timeout == 10`, no `async` key.

## Per-AC coverage

- **AC1** — `devcontainer/codex-prompt-prefix.sh` matches the spec's contract exactly: verified against all named fixture shapes by hand (` /vs fix the build` → `$vs` / "fix the build"; `/vsss --hours 2 go` → `$vsss` / "--hours 2 go"; `$vs go`, `/vss:foo`, `/vssx`, `/VS`, `hello /vs` → no output, exit 0; empty stdin and non-JSON stdin → no output, exit 0; `/vs` alone → "(no arguments)"). 41 lines, shellcheck-clean, no `dangerously`, no ` -c `.
- **AC2** — hooks.json gains the `UserPromptSubmit` group in the exact hardened form, `timeout: 10`, no `async`. Liveness check (c) regex is exactly the spec's grouped form; check (a) ownership list covers `codex-prompt-prefix`; the (c) loop resolves `hook_target` for both programs via `BASH_REMATCH`. Both permitted `checks_18` edits made exactly as named, nothing else touched in `smoke/`.
- **AC3** — Dockerfile COPY + chmod +x done as specified.
- **AC4** — all six doc touch points done: three SKILL.md files, README (two sentences, no `/prompts:`), `docs/codex-integration-plan.md` (F6 addendum with both citations, D3 rewritten), MANUAL-TESTS Test 55 (one new step + Pass-line mention), TODO.md entry (b) verified not stale.
- **AC5** — explicitly the Tester's; not touched beyond the two named `checks_18` edits.
- **AC6** — `python3 code-check.py`: clean, shellcheck across 24 files (was 23; `codex-prompt-prefix.sh` is new). `python3 smoke-test.py < /dev/null`: 4453 checks passed, 1 failed — see below.

## Test results

- `python3 code-check.py`: **clean**, shellcheck across 24 files.
- `python3 smoke-test.py < /dev/null`: 4453 passed, **1 failed**:
  `[task051] vs.md line count grew by exactly one vs HEAD` (`HEAD had 462 lines, now 462`).

  This is **pre-existing and unrelated to task_053**. It lives in `smoke/checks_13_spec_first.py` (task_051's own test, not touched by me — not one of the two permitted `checks_18` edits and out of my scope regardless). The check computes `len(current vs.md) == len(git show HEAD:devcontainer/commands/vs.md) + 1`. It was written to pass while task_051's change to `vs.md` was still uncommitted (working tree = parent HEAD + 1 line); the moment task_051's commit landed (`4bffdb8`, already `HEAD` at the start of this cycle), the working tree became byte-identical to the new HEAD, so the delta is permanently 0, not 1 — a self-referential test that can only pass pre-commit and fails forever after. I verified this is not caused by anything in this diff: `git stash push --include-untracked` (then immediately `git stash pop` — no changes lost) reproduces the identical failure against a working tree that exactly matches `HEAD` with zero task_053 changes present. `devcontainer/commands/vs.md` itself is untouched by task_053. Left unfixed per instructions ("NOTHING else under `smoke/`" beyond the two named edits); flagging for the Evaluator/Tester.

## Not done / notes

- Nothing from AC1-AC4 was skipped.
- The one smoke failure above is flagged, not fixed, per scope.
- `.vs/tasks.json`: `task_053.implementation_status` set to `complete` in place (no `git checkout`); `test_status` left `pending` for the Tester.
