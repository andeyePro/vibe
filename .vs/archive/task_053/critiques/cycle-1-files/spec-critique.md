# Spec Critique — task_053 re-scope (codex-prompt-prefix / leading-space)

## Concerns

1. **AC2/AC5, BLOCKING — "one permitted smoke/ edit" contradicts AC5's hooks.json assertion.**
   `checks_18_codex_runtime.py:334` (`test_codex_hooks_json_ac3`) hardcodes
   `set(hooks.keys()) == {"PreToolUse"}`. AC5 requires "hooks.json has exactly two
   events (PreToolUse, UserPromptSubmit)" — that assertion lives in the AC3 test, not
   the liveness-fixture builder (`_codex_liveness_fixture`, ~line 129) AC2 names as
   "the one permitted smoke/ edit." Shipping AC1-AC4 as written breaks this
   pre-existing test (AC6 can't be green) unless the Generator makes a *second* edit
   inside checks_18, violating AC2. Spec must widen the edit scope or name the file.

2. **AC2, BLOCKING — the described regex extension unanchors check (c) if applied literally.**
   Current: `hook_form='^/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-guard-adapter (bash|patch)$'`.
   AC2 says "regex is extended to `codex-guard-adapter (bash|patch)|codex-prompt-prefix`."
   Spliced in verbatim, the bare `|` sits outside any group; ERE alternation has the
   lowest precedence, splitting into `^.../codex-guard-adapter (bash|patch)` (no
   trailing `$` — matches as a prefix of any longer string) and
   `codex-prompt-prefix$` (no leading `^` — matches anything merely *ending* in that
   text). That silently turns the exact-form gate — this file's own docstring calls
   it "the single most important thing this script does" — into a substring match,
   exactly the bypass check (c) exists to catch. Spec must give the grouped form:
   `^/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/(codex-guard-adapter (bash|patch)|codex-prompt-prefix)$`.

3. **AC5, MINOR — no-leading-space fixture's premise needs a caveat.** Verified
   (`chat_composer.rs:3079`, `trim_submission: true` default at line 494): the
   leading-space bypass (`slash_input.rs:79`) checks the *original* untrimmed input,
   but trimming then strips the space before submission — so the TUI never emits a
   `.prompt` that both starts with `/vsss` (no space) AND skipped validation; a bare
   `/vsss ...` is rejected pre-submission and never reaches the hook. Valid as a
   unit test of the *script*; matches a real `codex exec`/programmatic path (hook
   fires generically, not TUI-only) — AC5's parenthetical should say that.

4. **AC4, MINOR — doc-rewrite framing risk.** Per #3, the leading space is a
   submission-time bypass only and does not survive to the model/hook. AC4 should
   say the space "lets Codex accept the line," not imply the hook sees a
   space-prefixed prompt, or a future reader "fixes" the script to require one.

## Source verifications

1. **Leading-space bypass; space stripped before submission by default:**
   `slash_input.rs:71-87` `validate_submission` returns `Valid` whenever
   `input_starts_with_space`, before checking the command exists — confirmed.
   `chat_composer.rs:3064` computes the flag from untrimmed `original_input`, but
   `chat_composer.rs:3079-3082` (`if self.config.trim_submission { text = text.trim() }`,
   default `true` at line 494) strips the space from `text` before it is
   validated/returned — the space does not reach the submitted message.

2. **Hook input/output shape; runs in TUI too:** input field is `prompt: String` on
   `UserPromptSubmitCommandInput` (`schema.rs:566-582`, wire key literally `prompt`,
   no camelCase rename). Output is `hookSpecificOutput.additionalContext`
   (`schema.rs:429-438` flatten+deny_unknown_fields, `schema.rs:443-448`
   camelCase); no top-level `additionalContext` exists (`schema.rs:90-98`). Runs in
   the TUI, not only `codex exec`: `core/src/hook_runtime.rs:660-684`
   (`inspect_pending_input`) fires `UserPromptSubmitRequest` for any
   `TurnInput::UserInput`, shared code for every front end.

3. **Managed hooks.json may declare `UserPromptSubmit`:** no restriction found.
   `discovery.rs:208-239` loads `managed_hooks.get().hooks` — the same
   `HookEventsToml` (`hook_config.rs:36-61`, includes `user_prompt_submit`) used for
   unmanaged sources — via the same append path, no per-event managed-only
   allowlist. `matcher_pattern_for_event` (`events/common.rs:112-126`) treats it
   like `Stop`/`Interrupt` (matcher ignored) — a note for the Generator, not a defect.

## Verdict

**revise** — concerns 1-2 are mechanically verifiable and land a broken test suite
(1) or a security-relevant regex bypass (2) if the AC text is followed literally.
