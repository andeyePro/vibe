# Spec critique — task_029 — iteration 2

## Iteration-1 resolution check

1. **AC5 — resolved.** Now requires `write-files-only` + ``never `git` against`` and explicitly forbids `read-only`. Matches the project's established brain2 convention. Mechanically checkable (two substring greps).

2. **AC6 — resolved, mechanically checkable, arithmetic verified.**
   - (a) zero `fromClaude`/`from<User>` after `## Reporting back at exit` — a plain substring count over `sed -n '/## Reporting back at exit/,$p'`. Checkable.
   - (b) no line outside § fromto format matching `(append|mirror|copy).{0,60}(report|outcome).{0,60}fromClaude`, with a named single exception inside § fromto format for AC4's exit-line — `grep -inE` per region, both boundaries derived from AC1/AC7 heading positions. Checkable.
   - (c) arithmetic: HEAD == baseline `73172fb` (verified identical, `diff -q` clean). Current `fromClaude` count in vsss.md = **10** (lines 127, 151, 168, 171, 184, 202, 205, 216, 240, 328). Of these, lines 240 and 328 sit inside the two spans AC6 deletes (§ At exit; § Reporting-back closing paragraph) — the other 8 are untouched elsewhere. Bound = 10 − 2 + X, X = mentions inside the new § fromto format section. Since total = outside + X, the bound algebraically reduces to **outside ≤ 8** — a well-defined, non-circular, mechanically computable check (X cancels).

3. **AC3/AC7 duplication — resolved.** § fromto format may now point to § Question format's existing hygiene sentence instead of restating it; no longer a mandatory duplicate literal-string requirement.

No addressed concern is re-raised below.

## New concerns

4. **MINOR, non-blocking.** All three AC6 structural guards key on the literal token `fromClaude` (guards a, c) or the verb+report/outcome+`fromClaude` regex (guard b). A paraphrase that reintroduces the same mirror-to-question-file mandate while describing the file without ever writing the literal word `fromClaude` (e.g. "also write the outcome into the live-question file from § The three files") would satisfy all three guards while reproducing the original contradiction. This is a narrower residual of the already-fixed evasion path, not the same hole — flagging for awareness; not worth blocking iteration 2 over, since it requires a deliberately indirect phrasing a normal prose edit is unlikely to produce.

## Verdict

**pass**
