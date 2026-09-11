# task_050 Generator report — cycle 1

Branch `astra`. Nothing committed, nothing pushed, no branch switch. No `smoke/`
file touched. No live model call made: every check ran against a local stub `codex`.

## Files created

- `devcontainer/codex-panel.mjs` — the panel runner (Node ESM, builtins only).
- `.vs/cycle-1/scratch-tests/run.py`, `.vs/cycle-1/scratch-tests/stub.py` — TDD scratch
  checks and the stub `codex` they drive (not the shipped test; AC7 is the Tester's).

## Files changed

- `devcontainer/Dockerfile` — `COPY --chown=root:root codex-panel.mjs /usr/local/bin/codex-panel`
  next to `codex-supervisor`, and `/usr/local/bin/codex-panel` added to the `chmod +x` list.
- `devcontainer/commands/vs.md` — § Step 5c "Running under Codex" note (1 line), plus
  rationale trims elsewhere to stay under the word cap (below).
- `README.md` — two sentences on `codex-panel` in the Codex delegation section.
- `docs/codex-integration-plan.md` — D6 names the tool and pins the rollout template.
- `.vs/tasks.json` — task_050 `implementation_status: complete` (edited in place).

## What was reused vs copied from the delegate

`devcontainer/vibe-delegate.mjs` exports nothing and calls `main()` at import time, so
importing it is impossible: everything shared is COPIED VERBATIM, inside a block marked
`--- copied from vibe-delegate.mjs (verbatim) ---`:

- `MAX_BYTES`, `object`/`string`, `REVIEW_SCHEMA`
- `fail`, `parse`, `record`, `exact`, `count`
- `run`, `git`, `repoRoot`, `slots`
- `codexEnv`, `CODEX_MIN`

Three pieces are the delegate's logic with a stated, deliberate structural change; each
carries a comment saying so at its definition:

1. `codexReady` — the delegate's `codexVersionOk` + `codexReady` checks, order and
   messages unchanged, but the two probe spawns are hoisted so BOTH always run before
   either is judged. AC1 requires readiness failures to account for exactly the two probe
   calls; the delegate's fail-fast would spawn one on a version-floor failure.
2. `reduceEvents` — `codexEvents()`'s reduction rules verbatim (turn.failed/error refusal,
   no-completed-turn refusal, per-key `count()`, cached ⊄ input check, cached never added
   twice), with the spawn hoisted out because the panel starts all N reviewers before
   awaiting any. It additionally picks up the last `thread.started` `thread_id`.
3. `validateReview` — the delegate's review-reply validation verbatim, including the
   semantic rule the JSON schema cannot express (PASS + any BLOCKING finding is invalid).

`reviewArgs()` holds the delegate's review vector verbatim with only the two scratch paths
substituted (same `schema.json` / `answer.json` basenames, so a basename-normalised list
comparison against the delegate's recorded argv is exact). `REVIEW_INSTRUCTION` is the
delegate's review instruction text verbatim.

`devcontainer/vibe-delegate.mjs` itself is untouched — the diff contains no change to it.

## Per-AC coverage

**AC1 — CLI and exit codes.** `codex-panel run --n <N> [--verify] [--out <dir>]`, diff on
stdin. Order of operations: argv parse → `slots(process.cwd())` (which calls `repoRoot`,
so the git-work-tree check happens here) → stdin read → readiness → reviewers. Exit 2 with
zero vendor processes for: missing `--n`, non-numeric `--n`, `--n < 2`, `--n > 5`, an
unknown flag, a subcommand other than `run`, empty stdin, stdin over 8 MiB, a cwd outside a
git work tree, `codex=off`, and any `slots()` policy failure (tracked / symlinked /
duplicate / malformed file — `slots()` fails closed). Usage or the specific refusal goes to
stderr. Exit 1 after exactly the two probe calls (`--version`, `login status`) on a
readiness failure, with no reviewer spawned. Exit 1 for an incomplete panel, 0 for a
complete one. A complete run spawns exactly 2 + N `codex` processes.

**AC2 — per-reviewer argv.** Ship mode is the delegate's review vector element for element,
in order, including its single `--ephemeral`. Verify mode is `args.filter(a => a !==
'--ephemeral')`, guarded by an assertion that the vector carries exactly one `--ephemeral`
so the filter can never silently drop two. Each reviewer gets its own `mkdtempSync` cwd
under `tmpdir()` (outside the repo), holding only its own `schema.json` and `answer.json`;
all N are removed in a `finally`. Nothing is written under the repo unless `--out` names a
path there.

**AC3 — blind input.** Reviewer k's stdin is exactly the delegate's review instruction,
then `PANEL-NONCE: <nonce>`, then the diff. Nonces are `randomBytes(16).toString('hex')` —
32 lowercase hex, one per reviewer. Reviewers are started with `spawn` inside a `map`, so
all N processes exist before the first `await`; the scratch stub sleeps 0.5 s per exec call
and the check asserts `max(start) < min(end)` across reviewers (true overlap).

**AC4 — collection.** Per reviewer: non-zero exit / signal / spawn failure, a refusal or
any non-JSON answer, a schema violation, the PASS-with-BLOCKING semantic violation, and a
missing or invalid usage block each produce `{"k":k,"error":"…"}` — exactly those two keys —
which is excluded from the tally and forces exit 1. Vendor stderr is drained and never
echoed (the delegate's rule). Successful reviewers produce
`{k, nonce, thread_id, verdict, summary, findings, usage}`; stdout is
`{"n":N,"mode":"ship"|"verify","reviewers":[…],"tally":{"PASS":x,"FAIL":y,"SPLIT":z}}`.
The tool never adjudicates — it only reports completeness.

**AC5 — verify extras.** `thread_id` comes from the reviewer's `thread.started` event
(`{"type":"thread.started","thread_id":"…"}`, pinned from
`codex-rs/exec/src/exec_events.rs` and `event_processor_with_jsonl_output.rs`). The rollout
lookup expands `$CODEX_HOME/sessions/*/*/*/` by hand (three `readdirSync` levels, no shell,
no glob dependency) and matches `rollout-*-<thread_id>.jsonl` and
`rollout-*-<thread_id>_*.jsonl` — never a `<thread_id>`-prefixed name. If neither exists it
retries the `.jsonl.zst` siblings and decompresses with `zstd -dc`; if `zstd` is absent (it
is absent from this image) or the archive is unreadable the outcome is `rollout-compressed`.
The text is scanned for `PANEL-NONCE:` lines. Outcomes: any OTHER reviewer's nonce present
→ `foreign-nonce-found` (checked first, so own+sibling lands here); else own nonce present
→ `own-only`; else → `rollout-not-found`. Judgement call worth the Evaluator's eye: a
rollout that is found but carries no nonce at all maps to `rollout-not-found` — the enum has
only four values and "no rollout proving reviewer k's session was located" is the closest
true statement; it fails the panel either way. `retention: "rollouts kept under
$CODEX_HOME/sessions"` is emitted in verify mode only.

Template verified against the vendor at tag `rust-v0.154.0` before the glob was written:
`rollout/src/rollout_file_name.rs` `render()` (the `_<rollout_id>` form appears only when
`thread_id != rollout_id`), `rollout/src/recorder.rs` `precompute_new_rollout_path` (the
`sessions/<YYYY>/<MM>/<DD>` directory), `rollout/src/compression.rs`
(`COMPRESSED_SUFFIX = ".zst"`).

**AC6 — docs.** `vs.md` § Step 5c gains a one-line "Running under Codex." note carrying the
literal `codex-panel run --n`, the separate-process point, the chair's correlated-agreement
check on the JSON, and `--verify` as the Martin-gated live proof that leaves rollouts in
`~/.codex/sessions`. README's Codex section gains two sentences naming `codex-panel`. D6
names `devcontainer/codex-panel.mjs` / `/usr/local/bin/codex-panel`, its argv and the
`rollout-…` template.

Word cap: `vs.md` + `vss.md` + `vsss.md` was 14,289 of the pinned 14,300 — 11 words of
headroom. The note cost ~115, so ~120 words of RATIONALE prose were trimmed from `vs.md`
(none of it rules, and no asserted literal touched): the Architect/Writer/Reviewer lineage
paragraph, the Step 5c "Ported 2026-07-10" paragraph, the `--cost` "Why opt-in" paragraph,
and four short redundant clauses in Step 5c. New total 14,295. Both word-count pins
(`checks_05`, `checks_13`) and every `[vs-panel]` literal assertion still pass.

**AC7 — not mine.** Note for the Tester: `smoke/checks_20_codex_panel.py` is not available
as a name — `smoke/checks_20_linux_host.py` already exists. `checks_19_codex_supervisor.py`
is 1,026 lines, so appending there risks the 1,500-line rule; `smoke/checks_23_codex_panel.py`
is the free slot.

**AC8 —** `python3 code-check.py` clean; `python3 smoke-test.py < /dev/null` exit 0.

## Commands run

- `python3 .vs/cycle-1/scratch-tests/run.py < /dev/null` — 48 checks, 0 failures
  (red before the implementation existed, green after).
- `python3 code-check.py` — `✓ shellcheck clean across 23 files`.
- `python3 smoke-test.py < /dev/null` — `✓ smoke tests passed`, exit 0 (run twice:
  once after the docs edits, once after the final source edit).

## Deliberate decisions the Evaluator should check

1. Both readiness probes always spawn (see "copied vs changed" #1). AC1 says "exactly the
   two probe calls"; the delegate's fail-fast would give one on a version-floor failure.
2. A found-but-nonce-less rollout maps to `rollout-not-found` (AC5 above).
3. `--out` writes `reviewer-<k>.json` per reviewer into the named directory, created if
   absent. The spec names the flag but not its contents; `.vs/cycle-N/panel/` is inside the
   repo, so `--out` is NOT refused for repo paths — AC2's "nothing written under the repo"
   holds for runs without `--out`.
4. The tool pins `--n` to 2–5 per AC1, which is deliberately narrower than `vs.md`'s
   panel-size rule (odd, 3–7). The chair resolves N before calling.

## Diff

`.vs/cycle-1/diff.patch` was produced after `git add -N devcontainer/codex-panel.mjs`
(intent-to-add only — nothing staged, nothing committed) so the new file's full contents
are in the patch rather than invisible to the Tester and Evaluator. Remaining untracked
paths are the chair's own (`.vs/spec.md`, `.vs/briefs/*`), not this task's.

`TODO.md` / `CHANGELOG.md` are deliberately untouched: `vs.md` § Step 7 makes those the
chair's on a pass.
