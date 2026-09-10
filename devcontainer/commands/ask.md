---
description: One-shot delegation to astra, opus, sonnet, haiku, or consent-gated fable; returns the answer and measured token usage.
argument-hint: <model> <prompt>
---

# /ask <model> <prompt>

Claude Code stays the lead. Send one bounded task to another model's own CLI;
return its answer without moving or resuming the lead's session.

**Delegate bulk payloads, not trivial questions.** Measured one-shot floors are
about **5k tokens for Astra** and about **3k for `claude -p`** through this helper
(tools disabled; the earlier **27k** figure was a `claude -p` with its full tool
set loaded, which the helper never does). These are observed overheads, not
guarantees. Move a big file, long log, or large diff when doing so
helps; answer a trivial question in-session. Batch once per payload, not per file.

1. Parse `$ARGUMENTS` as `<model> <prompt>`; accept only `astra`, `opus`, `sonnet`,
   `haiku`, `fable`. Missing model/prompt or an unknown model: show usage and stop.
2. Assemble exactly the task and necessary payload. Read any requested file/diff
   in the lead session under its existing guards. Exclude secrets, credentials,
   unrelated files and conversation history. Delegates have no tools; supply the
   actual content, not just a filename. Limit: 8 MiB; ask the user to scope larger work.
3. **Fable requires explicit per-task credit consent before every invocation.**
   Ask before running, explain it spends credits, and default to no. Merely naming
   Fable, a previous task's approval, `vibe --fable`, or `VIBE_FABLE_CREDITS_OK` is
   insufficient. Likewise require per-task consent if `VIBE_CLAUDE_P_BILLING` is
   `credits` or `api`. Only after that consent append `--consent-credits` below.
4. Write the payload to a private temporary file with the Write tool, then run
   the helper from the project root. Do not interpolate the prompt into shell
   syntax, command substitution or an unquoted heredoc. Replace only the model
   with its validated literal and the file path with a properly quoted path:

   ```bash
   node /usr/local/bin/vibe-delegate ask astra < /tmp/ask-payload.txt
   ```

   The helper invokes `codex exec -m gpt-6-astra --output-schema … --json` for
   Astra; `claude -p --model <opus|sonnet|haiku|fable> --output-format json` for
   Claude. It uses fresh processes in private temporary directories, no session
   resume, no tools/MCP, and removes its response files afterwards. Remove your
   payload file after the call. Never read or copy either CLI's credentials.
5. Parse the helper's JSON. Return `answer`, requested `model`, `served_models`
   when available, and `usage.total_tokens` plus input/output/cache breakdown.
   Codex cached input is a subset of input; Claude cache reads/writes are separate
   components. Report an unexpected served model explicitly. Counts come from
   CLI metadata, never model estimates; unavailable usage is an error, not zero.
6. Nonzero exit, refusal, quota exhaustion or malformed JSON: report the failure;
   do not present it as a successful answer or silently switch model/billing.
   For a confirmed connection failure, refresh extra domains once and retry once.
   No automatic quota loop or credit fallback.

## Configuration

Subscription is the default; Astra always uses ChatGPT login. See README's Codex
setup for the read-write `~/.codex` bind and per-project `.vibe/domains` entries.
`/ask` is explicit delegation and does not consult `.vibe/review-slots`.

Every Claude leg uses the same helper. `VIBE_CLAUDE_P_CONFIG_DIR` selects a
container-visible Claude config directory (default: the existing Claude volume).
`VIBE_CLAUDE_P_BILLING=credits|api` plus `VIBE_CLAUDE_P_SETTINGS` (absolute path to
Claude's settings JSON) selects a future paid route by configuration alone;
Claude itself reads its settings/`apiKeyHelper`. Set these non-secret path/mode
values in `~/.vibe/config` and relaunch. Never put keys in vibe files or copy OAuth
between runtimes. The subscription route pins `forceLoginMethod: claudeai`;
the lead's login policy is unchanged. `/budget` integration is follow-up work;
this command reports each call's usage directly.
