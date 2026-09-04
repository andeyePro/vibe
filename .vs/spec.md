# Spec — task_037: `/vs --TDD` — mandatory red-first Generator trail, Tester-verified (harness prose only)

## Task summary
Martin's queue item 3 (2026-09-04). The Generator brief already invokes `superpowers:test-driven-development`, but nothing checks it happened. `--TDD` makes red-first evidential: for every acceptance criterion the Generator records, BEFORE the implementing edit, the scratch test file, the command run, its non-zero exit and the failing assertion text in `.vs/cycle-N/tdd-trail.md`; the Tester cross-checks that trail against `diff.patch` (each AC has a trail entry; the named test file exists in the scratch dir; the failing assertion names the AC) and fails the cycle when it is missing or unmatched. `--TDD` requires mechanical tests, so it is incompatible with `--fuzzy` (error out, one line). Resolves vs.md Step 3b's dangling "`--TDD` (when implemented)" line. Passthrough in `/vss`/`/vsss` mirrors `--spec-first`. OUT of scope: any hook script or config, `settings.json`, a launcher flag, `.vibe/mode`, a CLAUDE.md directive — enforcement beyond the harness is Martin's later call (safety floor). Baseline b12ec98.

## Acceptance criteria (literal, case-sensitive substrings unless stated)
- AC1 vs.md § Flags has a bullet starting `- `/vs --TDD <prompt>``, ≤ 45 words, containing `red-first`, `tdd-trail.md`, and `incompatible with `--fuzzy``.
- AC2 vs.md § Step 4 contains a paragraph beginning `**Under `--TDD`**` with ALL of: `before the implementing edit`, `.vs/cycle-<N>/tdd-trail.md`, `one entry per acceptance criterion`, `test file`, `command`, `non-zero exit`, `failing assertion`, `written:` (an ISO-8601 timestamp per entry), `scratch-tests/` (the existing scratch dir), the entry shape `AC<n> | test file | command | exit | failing assertion | written:` on one line each (the `command` field must not itself contain `|`; a shared scratch file backing several entries shares one mtime — acknowledged in the weak-proxy wording), and the sentence `A trail entry written after the implementation, or without a failing run, is a cycle fail.`
- AC3 vs.md § Step 5a contains a paragraph beginning `**Under `--TDD`**` with ALL of: `tdd-trail.md`, `diff.patch`, `every acceptance criterion has a trail entry`, `named test file exists`, `assertion names the criterion`, `command` names the same file as `test file`, `written:` timestamp compared with the scratch file's mtime (`a weak proxy, not proof`), `fail the cycle`; it states the `--TDD` carve-out of the independence rule explicitly: `under `--TDD` the Tester additionally reads `tdd-trail.md` and `diff.patch` — only to check the trail, never the Generator's report` (literal `only to check the trail`); and the summary format sentence in § Step 5a is amended to `a 3-line summary (4 lines under `--TDD`: a `TDD trail:` line is appended)` (literal `4 lines under `--TDD``). The Rules bullet `No cross-subagent context sharing` gains the same carve-out clause (literal `except the `--TDD` trail check`).
- AC4 vs.md § Step 3b's sentence (today: `` `--TDD` stacking: the spec gate runs first; `--TDD` (when implemented) governs Step 4 only. ``) becomes `` `--TDD` stacking: the spec gate runs first; `--TDD` governs Step 4 (red-first trail) and Step 5a (trail check) only. `` — the literal `(when implemented)` no longer appears anywhere in vs.md.
- AC5 vs.md § Rules gains one bullet containing `--TDD` and `--fuzzy` stating they cannot combine (`refuse with one line`), and § Step 1's refusal list or § Flags states the same (either location; the Tester checks the Rules bullet).
- AC6 vss.md's flag passthrough sentence (the one naming `--spec-first`) also names `--TDD` (`threads through to `/vs``); vsss.md § Session-budget capture has a bullet starting `- `/vsss --TDD <args>`` containing `/vs § Step 4`.
- AC7 vs.md § State directory lists `cycle-N/tdd-trail.md` with a one-line description (`red-first evidence`), under the per-cycle artifacts. Panel/`--wide` interplay: one sentence in § Step 5c or § Step 5a states `panellists do not check the trail; the Tester does` (literal).
- AC8 Word budget: vs+vss+vsss ≤ 14,300 words; both pins (`smoke/checks_05_numbering_hook.py` /wide AC12 and `smoke/checks_09_openproject_and_scanner.py` task_028 AC8) raised to 14,300 in the same change; the Tester asserts both pins equal and ≥ actual. Target ≤ 350 words added (today 13,848); the pin at 14,300 is the fail line, the 350 is guidance.
- AC9 `smoke/checks_13_spec_first.py` gains `test_tdd_flag_docs()` (registered in `smoke/runner.py`) asserting AC1–AC7; file stays ≤ 1,500 lines; `python3 code-check.py` and `python3 smoke-test.py < /dev/null` exit 0.
- AC10 `TODO.md`: queue item 3 replaced by a one-line pointer noting the harness part shipped and that enforcement (an opt-in hook, a launcher session mode) is a later Martin-gated step; the long `vibe --TDD session mode` entry stays (it IS that later step) with one line added at its top: `Harness half shipped as /vs --TDD (task_037); this entry is the enforcement half.` `CHANGELOG.md` entry in the same commit.

## Out of scope
- Any file under `devcontainer/hooks/`, `settings.local.json`, the launcher, `.vibe/mode`, CLAUDE.md directives.
- Changing what the Generator brief already says about `superpowers:test-driven-development` beyond referencing the trail.
- `--XP` umbrella mode.

## Test location
`smoke/checks_13_spec_first.py` (Tester-owned: `test_tdd_flag_docs`); Generator edits vs/vss/vsss, the two pin literals, TODO, CHANGELOG — never test bodies.

## Proposed budget
2 cycles.

## Model plan
- Planner + Evaluator: session model (Fable 5.1 chair). Spec Critic: sonnet. Generator: sonnet, ceiling opus. Tester: haiku, ceiling sonnet. Fable rung: not pre-authorised.
