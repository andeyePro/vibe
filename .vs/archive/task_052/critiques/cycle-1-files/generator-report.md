# task_052 — Generator report (cycle 1)

## Files changed

- `devcontainer/vibe-delegate.mjs` — the ledger implementation (AC1-AC3), the
  `billing`/`served_models` additions to `codexRole()`/`claudeRole()` (AC2),
  and the usage-recovery-on-failure plumbing (AC2).
- `devcontainer/commands/budget.md` — new "Delegated calls" section (AC4).
- `devcontainer/commands/ask.md`, `devcontainer/commands/review.md`,
  `README.md` — one sentence each naming the ledger (AC5).
- `docs/codex-integration-plan.md` — § 3 item 9 marked
  `**DELIVERED (task_052).**` (AC5).
- `.gitignore`, `devcontainer/install-claude-extras.sh` — **unchanged**: both
  already carry the blanket `.vibe/` rule (`.gitignore:33`,
  `install-claude-extras.sh:406`'s managed block), confirmed by inspection
  and by a scratch check; nothing added per the instruction to add nothing
  unless genuinely missing.
- `.vs/tasks.json` — task_052 `implementation_status: "complete"`.
- `.vs/cycle-1/scratch-tests/test_ledger.py` — throwaway TDD scaffolding
  (standalone, does not import `smoke`), all green; not wired into
  `smoke/runner.py`.
- `.vs/cycle-1/diff.patch`, `.vs/cycle-1/generator-report.md` — this cycle's
  artifacts.

## Design notes worth flagging to the Evaluator/Tester

- **Ledger root**: `repoRootOrNull(process.cwd())`, called at write time
  inside each of `codex()`/`codexRole()`/`claude()`/`claudeRole()`. Since
  nothing in the file calls `process.chdir()`, `process.cwd()` is stable for
  the whole process and always equals the invocation directory — including
  for `role` dispatch, where it is deliberately independent of the role's own
  `--cwd`.
- **"probes never log"**: achieved structurally, not with a flag. The ledger
  write lives inside a `try { ... } catch (error) { ...; throw error }` block
  that starts only AFTER `codexReady()` (version/login probes) has already
  succeeded, so any probe failure exits the function before the try block is
  ever entered and never logs. A later failure *inside* the try (the actual
  `codex exec`/`claude -p` call, or its reply-schema validation) is always
  logged, `ok:false`.
- **Usage recovery on failure**: for Codex, `usage` is a `let` in the
  enclosing function, assigned from `codexEvents()`'s return value — since
  `codexEvents()` and the reply-schema validation that follows it are in the
  *same* function, the value survives a later throw without needing to ride
  on the exception. `codexEvents()` is still split into itself (spawn +
  parse) and a new `reduceCodexUsage()` (validate + reduce), per the
  instruction, though this split isn't load-bearing for the recovery
  mechanism given the above. For Claude, `claudeReply()` genuinely needs the
  error-borne property (`fail(message, usage)` — `fail`'s second, optional
  argument) because usage-extraction and the result-shape check are
  interleaved in one function: `claudeUsageFrom()` best-effort-parses
  `response.usage` and is attached to the thrown Error whenever the
  overall-result-shape check fails, so a reply with `is_error:true` but a
  valid usage block still logs non-null usage. The success path in
  `claudeReply()` is byte-for-byte the pre-task_052 code — same checks, same
  order, same messages.
- **`model` field convention**: I logged `model: 'gpt-6-astra'` for every
  Astra/codex call (ask, review, role) — the same value already in the
  printed JSON's `model` field — rather than the CLI-facing `astra` token,
  since AC4's `/budget` report groups by `runtime`, not `model`, so this
  choice doesn't affect the required report and keeps ledger/printed-JSON
  `model` values trivially consistent. Worth a second look if the Tester
  wants CLI-facing names in the ledger instead.
- **Symlink protection** is scoped exactly as AC3 states: only the ledger
  *file* itself. A symlinked `.vibe/` directory is not specially guarded
  (unlike `slots()`'s check on `.vibe`), since the spec's AC3/AC6 language is
  specific to "a ledger that is a symlink."

## Per-AC coverage

- **AC1** — done. Root = `repoRootOrNull(process.cwd())`; outside a work
  tree: one stderr note, no write, `ask haiku` still succeeds, `ask astra`
  still refuses via `slots()` exactly as before (untouched code path).
  `.vibe/` created 0700 when missing. `.gitignore`/`install-claude-extras.sh`
  blanket rule confirmed present, nothing added.
- **AC2** — done. Exact 10-key object built by `ledgerEntry()` for every
  model-invoking call in `codex()`, `codexRole()`, `claude()`, `claudeRole()`;
  a refusal before the vendor process starts (unknown model/role, `codex=off`,
  bad payload, missing consent, login/version probe failure) never reaches
  the logging code. `codexRole()`/`claudeRole()` now return `billing` and
  `served_models` too. Usage recovery verified for both "schema-invalid
  reply after a completed turn" (non-null usage) and "process exited 1"
  (null usage), for both runtimes, in the scratch tests. No payload,
  thread_id or session_id ever appears in an entry.
- **AC3** — done. `appendFileSync` writes one line ending `\n`; ledger file
  mode 0600; a symlinked ledger is refused with one stderr note, no write,
  call still succeeds; every ledger-write failure path is caught and only
  logged to stderr, never changes the caller's exit code or stdout.
- **AC4** — done. `budget.md` has the exact heading, the exact two line
  templates, the failed-call count instruction, the explicit
  not-included-in-interactive-figures statement, the ChatGPT-plan-not-
  Anthropic's note, and the `jq` one-liner (hand-verified against sample
  ledger data — see the Bash transcript in this cycle).
- **AC5** — done. One sentence each in `ask.md`, `review.md`, README's Codex
  section; `docs/codex-integration-plan.md` item 9 marked delivered.
- **AC6** — Tester's, not attempted in `smoke/`. Scratch coverage of the
  same scenarios lives in `.vs/cycle-1/scratch-tests/test_ledger.py` (all
  green): successful astra/haiku/role calls with the exact key set; refusals
  (unknown model, `codex=off`, login-probe failure) logging nothing;
  schema-invalid-after-completed-turn for both runtimes (non-null usage);
  process-exit-1 for both runtimes (null usage); no payload/id leakage;
  file mode 0600 and `.vibe/` mode 0700; symlinked ledger refused; outside-
  work-tree invocation.
- **AC7** — `python3 code-check.py`: clean (23 files, no shell code touched
  by this task). `python3 smoke-test.py < /dev/null`: **2 failures**, both
  pre-existing pinned assertions in `smoke/checks_18_codex_runtime.py`
  (`test around line 1058` and `1102`) that assert the role JSON's key set is
  exactly `{runtime, model, role, status, report, usage}` — i.e. *without*
  `billing`/`served_models`. This is the exact, spec-anticipated fallout of
  AC2's "codexRole()/claudeRole() outputs gain billing and served_models" —
  the task's own hard rule says the printed JSON must stay byte-identical
  "apart from the two new role keys," which necessarily makes that one old
  pinned assertion stale. Per the hard rule "NEVER edit anything under
  smoke/," I have not touched it; **the Tester needs to update those two
  assertions (in `checks_18_codex_runtime.py`, or wherever AC6's new/renamed
  test file ends up) to include `billing` and `served_models` in the
  expected key set** as part of landing AC6. Every other check in the full
  suite (including the review.md word-count and every other doc-sentinel
  check touched by this task's doc edits) is green.

## Not done / left for the Tester or a follow-up

- The two pinned `checks_18_codex_runtime.py` key-set assertions above need
  updating to include `billing`/`served_models` — this is AC6 territory and
  was left alone per the hard rule.
- `smoke/checks_17_delegation.py` (or `checks_19_codex_ledger.py`) gets no
  new tests from me — AC6 is explicitly the Tester's.
- No behavioural change beyond the spec's scope: usage measurement, the
  panel runner, ledger rotation/pruning, and a machine-wide ledger are all
  untouched, per "Out of scope."

## Verification run transcript summary

- `node --check devcontainer/vibe-delegate.mjs` — clean.
- `.vs/cycle-1/scratch-tests/test_ledger.py` — all scenarios pass (10 test
  functions, ~50 individual checks).
- `python3 code-check.py` — clean.
- `python3 smoke-test.py < /dev/null` — 2 known/expected failures (see AC7
  above), everything else green, including `test_review_command_docs`,
  `test_ask_command_docs`, and `test_codex_switch_docs` re-run individually
  after trimming `review.md` to fit the pinned ≤850-word limit.
