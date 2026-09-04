# Generator report — task_036 (`--spec-first`), cycle 1

## Files changed

- `devcontainer/commands/vs.md` — AC1 (two `§ Flags` bullets: `--spec-first`, `--approve [<task-id>]`), AC2/AC4 (new `## Step 3b — Spec-first checkpoint` section between Step 3 and Step 4, carrying every AC4 literal), AC3 (fork sentence in Step 3's `On pass` paragraph), AC5 (four-value `implementation_status` enum in the `tasks.json` schema), AC6 (`parked at awaiting-approval` + `/vs --approve` resume-from-archive note in `§ Multi-task state convention`).
- `devcontainer/commands/vss.md` — AC7: `--spec-first` passthrough beside `--wide` with the four reconciliation literals; a branch in Mode A step 2 (`2. **If found:**`) and in Mode B's `### Step 4 — Close out`, both leaving a parked TODO entry with the literal `(awaiting approval — /vs --approve <task-id>)` appended instead of ticking it.
- `devcontainer/commands/vsss.md` — AC8/AC9: `§ Session-budget capture` bullet for `/vsss --spec-first <args>`; `never blocks the loop` sentence in `### Interaction with the loop`; `§ Consume protocol` step 6 folds an approve/redirect reply into `/vs --approve <task-id>` or a spec-revision instruction; verbatim AC9 action-point sentence added after `### Question format (fromClaude)`; a `Deferred` line format added to `## Reporting back at exit`.
- `smoke/checks_05_numbering_hook.py` — both `13500` pin occurrences (comment + AC12 check + label) raised to `14000`.
- `smoke/checks_09_openproject_and_scanner.py` — the AC8 pin (comment + check + label) raised to `14000`, comment updated to record task_036 as the bump's cause.
- `TODO.md` — priority-queue item 1 (`--spec-first`) removed (closed); new `[ ]` item added recording the later PreToolUse-hook hardening, needs Martin (safety floor, out of scope here).
- `CHANGELOG.md` — new `## 2026-09-04` heading (didn't exist yet) with the `[x]` entry for this task.
- README.md — no change (grepped for `--fable-subagents` and any `/vs` flag enumeration; README's `/vs` sections are prose-only, no flag list to extend, per spec instruction).

Not touched: `smoke/checks_13_spec_first.py` (Tester-owned, AC11), any test bodies.

## Word counts (AC10)

| file | before | after | added |
|---|---|---|---|
| vs.md | 5872 | 6160 | 288 |
| vss.md | 2056 | 2196 | 140 |
| vsss.md | 5325 | 5492 | 167 |
| **total** | **13253** | **13848** | **595** |

13,848 ≤ 14,000 (both pins raised to 14,000 in the same change, per AC10). Note: the brief's soft target was ≤450 added words; actual is 595, driven mainly by Step 3b needing to carry all 17 AC4 literals verbatim plus the stacking/cycle-1-restart rationale sentences — trimmed as far as possible without dropping a required literal. Hard AC10 cap (14,000) is met with 152 words of headroom.

## Verification

- Scratch sentinel `/.vs/cycle-1/scratch-tests/sentinel_spec_first.py` (TDD red→green, gitignored, Generator-owned — not the Tester's `smoke/checks_13_spec_first.py`): red before edits (47 failures, confirmed against baseline), green after (`ALL SENTINEL CHECKS PASS`), exit 0.
- `python3 code-check.py < /dev/null` — exit 0 (`✓ shellcheck clean across 19 files`).
- `python3 smoke-test.py < /dev/null` — exit 0 (`✓ smoke tests passed`), including `[wide] AC12: combined vs+vss+vsss word count ≤ 14,000` and `[ac8] vs+vss+vsss total words <= 14000` both green at the new pin.

## Notes for Tester / Evaluator

- All AC1–AC9 literals are written as single unwrapped source lines (no hard-wrap) where the AC required an exact multi-word substring — several early scratch-test failures were false negatives from my own wrapped prose breaking a substring across a line break, not from missing content; fixed by joining those spans onto one line.
- AC4's no-cycle-has-run rationale and the credit-billed-tier exception live in the Step 3b section's second paragraph.
- `tasks.json` `implementation_status` for task_036 set to `complete` (only that field); `test_status` left `pending` for the Tester.
