# Spec Critique — task_037 (`/vs --TDD`)

## Concerns

1. **BLOCKING (AC3 vs. Independence rule/Rules) — Tester reading `diff.patch` contradicts the standing rule.** Step 5a's independence rule says Tester sees only `spec.md`, test-dir layout, and source tree — "NOT Generator's diff or report" — and the Rules bullet repeats this. AC3 requires Tester to cross-check `tdd-trail.md` against `diff.patch`, directly contradicting the unrevised rule. Add an explicit `--TDD`-only exception to *both* the Step 5a independence sentence and the Rules bullet ("Tester also reads `diff.patch`, `--TDD` only").

2. **BLOCKING (quoted anchor mismatch, AC4).** The spec's literal old sentence is `--TDD (when implemented) governs Step 4 only` — the actual file (line 249) reads `` `--TDD` (when implemented) governs Step 4 only. `` (backtick right after `TDD`). The spec's quoted substring is NOT a verbatim match — it will not `grep -F` against the real file. Quote the anchor with the backtick in place.

3. **BLOCKING (AC2/AC3 ordering is not mechanically checkable).** AC2 requires trail entries "before the implementing edit"; AC3 says Tester fails the cycle when an entry was written after — but no field or artifact lets Tester check *order*. `diff.patch` carries no timestamps; `scratch-tests/` mtimes are gameable and not required by AC2 anyway. Recommend: add a per-entry ISO8601 `written:` field to AC2's required trail fields, and have AC3 instruct Tester to compare it against the scratch test file's mtime — explicitly a weak, corroborating proxy, not proof; say so, rather than leaving "before the implementing edit" an unfalsifiable claim.

4. **BLOCKING (AC3 summary.md conflicts with the existing "3-line" wording).** Step 5a fixes a 3-line summary (total/passed/failed/key-failures). AC3's mandatory `TDD trail:` line is a 4th line under `--TDD`, but nothing authorizes amending that sentence. Add: under `--TDD`, the summary becomes 4-line (or `TDD trail:` replaces one of the three) — pick one and say so explicitly.

5. **MINOR (sentinel-stuffing).** A Generator could satisfy AC2/AC3 with disconnected boilerplate (`test file: x.py`, `command: true`, `non-zero exit: 1`, `failing assertion: AC1 fails`) that never ran anything coherent. Add one coherence literal: the `command` field must contain the same filename as the `test file` field — a simple, mechanical cross-field check that rules out disconnected sentinels.

6. **MINOR (`--TDD` + `--panel`/`--wide` under-specified).** Silent on whether panellists under `--TDD --panel` also check `tdd-trail.md` (they already get `diff.patch`). One line — "panel does not check the TDD trail; Tester-only" — removes ambiguity. `--wide` interplay is low-risk (trail-writing is internal/sequential to Generator) but deserves one confirming clause.

7. **MINOR (budget headroom).** Target "≤350 words added" (13,848→14,198) sits well under the 14,300 hard pin — fine as guidance, but worth stating that 14,300 is the fail line, not the target.

Nothing else found: AC1, AC5, AC6, AC7, out-of-scope, and Model plan are internally consistent and mechanically checkable as written.

## Verdict

**revise** — concerns 1–4 are BLOCKING (a rule contradiction, a non-matching literal anchor, and an unfalsifiable ordering claim); 5–7 are MINOR hardening suggestions.
