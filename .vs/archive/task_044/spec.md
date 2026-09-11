# task_044 — Codex helper hardening (plan item 2, branch `astra`)

## Task summary

Three security follow-ups from the phase 1a review, all in the delegate helper,
its docs and one launcher warning. (a) `.vibe/review-slots` `codex=off` becomes
the project's "no OpenAI egress" switch: today it stops the `/review` codex slot
but `/ask astra` deliberately ignores it, so project content can still reach
OpenAI through `/ask`. (b) The nested `claude -p` leg gets belt-and-braces
permission flags and stops carrying a redundant `disableAllHooks` setting
(`--safe-mode` already disables hooks). (c) The launcher warns once at launch
when the Codex login directory it is about to bind is readable by group or
others. No guard, firewall or settings-permission file changes.

## Acceptance criteria

- AC1 With an untracked `.vibe/review-slots` containing `codex=off`,
  `node devcontainer/vibe-delegate.mjs ask astra` (payload on stdin, cwd inside
  the work tree) exits non-zero, launches ZERO vendor processes (no `codex`
  call of any kind, not even `--version` or `login status`), prints nothing on
  stdout, and its stderr names both `.vibe/review-slots` and `codex=off`.
- AC2 The same `codex=off` policy leaves `ask haiku`, `ask sonnet` and
  `ask opus` unaffected (exit 0, one `claude` call each). `gemini=off` alone,
  an empty policy file, and no policy file all leave `ask astra` working
  (exit 0, three `codex` calls: version, login status, exec). Every policy
  failure that `slots` already refuses — a tracked file, a symlinked file or
  `.vibe` dir, a duplicate or unknown entry, an unknown value — makes
  `ask astra` exit non-zero with ZERO vendor processes (fail closed; a policy
  read error is never treated as "codex enabled").
- AC3 `ask astra` invoked with cwd OUTSIDE any git work tree exits non-zero
  with zero vendor processes (the policy cannot be resolved, so the helper
  fails closed, mirroring `slots`). `ask haiku` outside a work tree is
  unchanged (it never consults the policy).
- AC4 The Claude leg's argv is pinned as a golden vector: in subscription mode
  the exact list is `['-p', '--model', <model>, '--output-format', 'json',
  '--safe-mode', '--tools', '', '--strict-mcp-config', '--mcp-config',
  '{"mcpServers":{}}', '--setting-sources', 'user', '--permission-mode',
  'plan', '--permission-prompts', 'none', '--no-session-persistence',
  '--disable-slash-commands', '--settings', '{"forceLoginMethod":"claudeai"}']`
  — `--permission-mode dontAsk` and `disableAllHooks` are gone, the two new
  flags are present, and nothing else changed. In a billed mode
  (`VIBE_CLAUDE_P_BILLING=credits` + settings path + `--consent-credits`) the
  vector is identical except the final `--settings` value is the configured
  path.
- AC5 The launcher (sourced with `VIBE_SOURCE_ONLY=1`) exposes
  `_codex_dir_mode_warning <dir>`: it prints exactly one stderr line
  containing `chmod 700` and the directory path when the directory's mode
  grants ANY permission bit to group or others (e.g. 0755, 0750, 0705), and
  prints nothing for 0700. Four-digit modes are judged on their last three
  octal digits (1755 warns, 4700 does not); the path is used as given (the
  caller passes `_codex_desired_source`'s canonical path). It never changes
  the mode. A non-existent path prints nothing. `_codex_desired_source` is
  unchanged. Wiring is verified by SOURCE-TEXT adjacency (the banner runs
  below the `VIBE_SOURCE_ONLY` guard): in `vibe`, a line calling
  `_codex_dir_mode_warning "$_codex_banner"` appears within the five lines
  after the line that echoes the `codex   :` header, inside the same
  `if [ -n "$_codex_banner" ]` block.
- AC6 Docs: `devcontainer/commands/ask.md` states that `codex=off` in
  `.vibe/review-slots` also refuses `/ask astra` (the sentence "`/ask` is
  explicit delegation and does not consult `.vibe/review-slots`" is removed);
  `devcontainer/commands/review.md` drops "`/ask` is independent of this
  policy" and says the file is the project's OpenAI-egress switch while
  `.vibe-allow-codex` is the credential-mount switch; README's Codex setup
  section carries the same two-switch sentence and the `chmod 700` warning.
  Pinned substrings: `ask.md` contains `codex=off` AND `/ask astra` in one
  sentence with `refus`; `review.md` no longer contains "independent of this
  policy"; README contains `chmod 700` and the words `egress switch` and
  `mount switch`; `MANUAL-TESTS.md` Test 54 step 8 no longer says
  "explicitly `/ask astra ...` still works" and instead says `codex=off`
  refuses `/ask astra` as well, and step 4 adds one sentence: re-confirm a
  real `claude -p` one-shot still returns `type: result`, `subtype: success`
  under `--permission-mode plan --permission-prompts none`.
- AC7 `smoke/checks_17_delegation.py`: the existing assertion
  `[delegate] explicit ask independent of review policy` is REPLACED by the
  AC1 assertion (the Tester owns this change). The Generator never edits
  anything under `smoke/`, for any reason. Every other existing delegate
  check still passes.
- AC8 `python3 code-check.py` is clean and `python3 smoke-test.py < /dev/null`
  is fully green.

## Out of scope

- Any edit to `guard-bash.sh`, `guard-fs.sh`, `init-firewall.sh`,
  `settings.local.json`.
- The host-side `~/.vibe/codex-allow` registry (plan item 3), the usage
  ledger (item 9), any `/etc/codex` policy (item 4), `chmod`-ing the user's
  directory, changing the Codex leg's argv, or changing `review codex`
  behaviour.
- `gemini=off` semantics beyond what exists today.

## Test location

`smoke/checks_17_delegation.py` (delegate ACs 1-4, 7) and
`smoke/checks_01_launcher_basics_and_codecheck.py` (AC5, launcher sourced with
`VIBE_SOURCE_ONLY=1` through `_isolate_extras_env`). Docs ACs (AC6) are
asserted by string checks in `smoke/checks_13_spec_first.py` next to the
existing `/ask` and `/review` doc checks. Keep every part ≤ 1,500 lines.

## Proposed budget

2 cycles — three small, independent changes with fixture-based tests already
in place for the helper.

## Model plan

- Spec Critic: sonnet.
- Generator: sonnet (ceiling opus on a second capability failure).
- Tester: haiku.
- Evaluator: session model (Fable 5.1 chair).
- Fable rung: not pre-authorised.
