# task_065 cycle 1 — Generator report

## Files changed
- `devcontainer/taskandi-client.mjs` — A1 storage, A2 `decide`, A3 `--resolve`, A4 release flags + boolean `strictFlags`, A5 `--body-max-chars`, A6 `--check-argv`, pruning, `createClient({clock})`.
- `devcontainer/taskandi-usage.mjs` — A1b Claude parser, subagents, per-model jobs, imported-id ledger.
- `devcontainer/commands/vss.md`, `devcontainer/commands/vsss.md` — one `## Bound task tracker (optional)` heading + one delimited block each (generated from one template; only the intro sentence differs).
- `devcontainer/codex/context.md` — old `## Optional Task&I Action Window` replaced by `## Optional task tracker` + short block; the two unrelated trailing paragraphs (vibe-delegate, `$vsss`) now sit under `## Delegation and \`$vsss\``. Skills untouched.
- `docs/taskandi-client.md` ("Harness integration" section; importer and claim paragraphs updated), `MANUAL-TESTS.md` Test 70, `CHANGELOG.md` (top of 2026-10-31).
- `smoke/runner.py` appears in `diff.patch` but was edited by the Tester, not me.

## Per-AC notes
- AC1/AC2: `decide` per spec; the `why` order is pinned in code. `answered-not-yet-polled` always `wait` (spec case 4 says wait; never parks, like `status-unavailable`). Repoll vs "polled since" uses a per-task poll counter (`state.polls`) recorded with each `repolls` entry, not timestamps, so a fixed injected clock cannot confuse ordering.
- AC3: `decide --resolve` offline; refuses unknown/non-done/non-ask/other-task keys; same-`as` repeat is idempotent, a different `as` is refused; `proceeded` clears the task's `parked` entry.
- AC4: budget per spec. Zero-allowance dimension counts as ratio 1 (no division). With ratio ≥ threshold but no `--remaining-minutes`, the result is `under-threshold` (literal "otherwise"). Knob validated after the binding check, before the claim check.
- AC5: no open asks → zero requests; else capabilities + ask_status. Capabilities failure (incl. ask_status not offered) → exit 1; ask_status failure → `degraded`.
- AC6: reclaim = open **blocking** ask set exactly equals `parked.openAskIds` (fixed after the first run: subset was too loose), or budget-stopped with no dimension larger (`null`/absent = unlimited).
- AC7: claim gains `claimedAtMs`, `allowance`, `spent`, `spentAt`, `defaults_allowed`, optional `hardDeadline`/`latest_start`/`estimate_minutes`. Renewal rule (ambiguity): a renewal keeps the first claim's time (`claimedAtMs`) and its `spent` counts as of that time, so a later `record_usage` spent survives; ties keep the larger roll-up. Done jobs get `doneAtMs` (also on `reconcile --action done`). MCP claim unchanged (decide refuses MCP).
- AC7b: Claude chosen by content; last record per `message.id`; all-zero skipped; `subagents/*.jsonl` read in name order; one job per model, key `usage-`+16 hex of sha256 `[session, model, last id]`; ledger `usageImports[session][abs file]` written in the same lock as the jobs (HTTP) — a raced import is refused. Codex path unchanged.
- AC7c: pruning in `atomicJson` (every state write), keeps newest 2000 done + non-done + ask jobs behind an open ask.
- AC8: body file written on every non-null claim (0600, untracked check, no symlink follow); truncation keys `body_truncated`, `body_chars`, `body_file` are added **inside `task`** (ambiguity; untruncated output stays byte-identical to before, which checks_50 asserts).
- AC9/AC10: blocks verified by `.vs/cycle-1/scratch-tests/prose_check.py` (structure, outside-block grep, every fenced line through `--check-argv`, subcommand set exactly the nine). Step-3 `decide` and the linked-task release are inline (not fenced) so fenced `poll` precedes fenced `decide`. `--check-argv` accepted as argv[0] or right after the command; empty stdin checks argv only.
- context.md plain-session block names only status/poll/enqueue ask/usage (no flush), per spec: such asks are delivered at the next harness boundary.

## Spec conflict (needs Planner decision)
- Existing word-cap checks (`[wide] AC12`, `[ac8]`, `[spec-first] AC10`, `[tdd] AC8`) require vs+vss+vsss ≤ 14,300 words; the tree was at 14,297 before this task. The spec requires the full flow in **both** vss.md and vsss.md (~1,570 words each), so total is 17,445. No compliant wording fits in 3 words. Options: raise the cap (edit those four checks), or move the flow into one shared file referenced by both blocks (changes the spec's AC9/AC10 shape). I did not edit the existing checks.

## Tester-side issues seen in checks_53/54 (not changed by me)
- checks_53 AC4 ×2 and AC7 ×2: `_fixture_payload("record_usage")` includes `windows`, `source`, `source_ref`, which `enqueue record_usage` refuses (checks_50/52 strip them), so the enqueue exits 1 and nothing is pending/flushed.
- checks_53 AC3 "a queued ask job" (+ "refusals leave the ledger untouched"): `mkask(..., flush=False)` is followed by a `flush` for the comment, which delivers `ask-q` too, so it is `done` when resolved.
- checks_53 AC7 "bindingFingerprint identical": `hx.lib` adds `out.ms` (elapsed time) to the dict, so before/after differ by timing (passed once by chance).
- checks_54 "vsss/SKILL.md keeps its delegation sentence": expects `Read \`/usr/local/share/vibe/commands/vsss.md\` now, in full, and follow it`; the unchanged vsss SKILL.md says `` `/usr/local/share/vibe/commands/vsss.md` in full. The Codex contract overrides`` (only vss SKILL.md uses the "now, in full" wording).
- checks_54 guarantee check is case-sensitive (`never invoke taskandi-client`); I reworded the in-block sentence to `Guarantee: never invoke …`, now passing.

## Commands run (exit codes)
- `node .vs/cycle-1/scratch-tests/decide.test.mjs < /dev/null` → 0 (100 passed)
- `python3 .vs/cycle-1/scratch-tests/prose_check.py` → 0
- `python3 code-check.py` → 0
- `python3 smoke/checks_{28,29,47,50,52,55}_*.py < /dev/null` → 0 each (unchanged suites pass)
- `python3 smoke/checks_53_taskandi_decide.py` → 1 (7 failures, all listed above as tester-side)
- `python3 smoke/checks_54_harness_prose.py` → 1 (1 failure, SKILL.md sentence, tester-side)
- `python3 smoke-test.py < /dev/null` → 1: see final-run section below.

## Final full run
`python3 smoke-test.py < /dev/null` → exit 1 with 11 failures: the four word-cap checks (spec conflict above), six checks_53 cases and one checks_54 case (all tester-side, listed above). Everything else passes, including all pre-existing taskandi suites. The checks_53 fingerprint case passed this run (it depends on timing). `python3 code-check.py` → 0.
