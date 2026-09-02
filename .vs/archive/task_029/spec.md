# Spec — task_029: fromto format — minimal fromClaude template, brain2 override, exit-append rule removed

## Task summary
`/vsss` § fromto channels tells Claude to write ONLY live questions to the user's fromClaude file (§ Question format: "questions and blocking asks only — no progress notes, no FYIs"), then § At exit (vsss.md ~237–242) and the closing paragraph of § Reporting back at exit (~327–329) mandate appending the full exit report to the same file. That contradiction is why "Session report" sections keep appearing and why Martin re-explains his format to every model (`/brain2/andeye/Money&I-Q&A-archive.md` "Session reports moved out of fromClaude, 2026-08-21"). Fix: define the minimal fromClaude template once in vsss.md as the default, let `/brain2/meta/fromto-format.md` override it verbatim when present, delete both exit-append mandates, replace them with ONE exit line, and write the brain2 override note holding the same default. Terminal report to the user (§ Reporting back at exit) is unchanged. Baseline commit: 73172fb.

## Acceptance criteria
- AC1 `devcontainer/commands/vsss.md` has a heading line exactly `### fromto format` positioned after the `### The three files` heading and before the `### Question format (fromClaude)` heading.
- AC2 The § fromto format body contains this fenced template verbatim (line for line, inside a ```` ``` ```` fence):
  ```
  ---
  state: authored
  author: Claude (<harness>, <repo>)
  created: <ISO date>
  cssclasses: [trust-authored]
  ---
  Reply in [[<project>-from<User>]]. History: [[<project>-Q&A-archive]].

  1. <action point: a question to answer, or a test to run> (T<n>)
  ```
- AC3 vsss.md contains, in § fromto format, each of these literal strings: `one ordered list and nothing else`; `no session report`; `Information appears only where it answers a question the user asked`; `action points only`; `contiguous from 1`. (§ Question format already carries the no-progress-notes/no-FYIs sentence; § fromto format may point to it rather than restate.)
- AC4 vsss.md § fromto format contains the exit-line rule with the literal sentinel ``Session log: `.vss/sessions/<start-ISO>.md` — <N> commits, <pushed|not pushed>.`` and the words `exactly one line`.
- AC5 vsss.md § fromto format contains `/brain2/meta/fromto-format.md`, `overrides this default verbatim`, and the credential-boundary sentence containing both `write-files-only` and ``never `git` against`` (brain2 is writable at file level from a container; only git is forbidden — do not write `read-only`).
- AC6 Deleted: the string `### At exit` does not occur in vsss.md; the string `Append the exit report (same content as § Reporting back at exit)` does not occur; the string `If fromto channels are active` does not occur. Structural guards against paraphrase: (a) the text from the `## Reporting back at exit` heading to end-of-file contains zero occurrences of `fromClaude` and zero of `from<User>`; (b) outside § fromto format, vsss.md contains no line matching the regex `(append|mirror|copy).{0,60}(report|outcome).{0,60}fromClaude` (case-insensitive), and § fromto format itself contains no such line except the single exit-line rule of AC4; (c) the total count of `fromClaude` in vsss.md is ≤ the 73172fb count minus 2 plus the number of mentions inside § fromto format (Tester computes both numbers and asserts).
- AC7 Preserved: vsss.md still contains `## Reporting back at exit`, `Total iterations run.`, ``Lead with `---` before the report block.``, the § Question format heading `### Question format (fromClaude)` and its hygiene sentence `questions and blocking asks only — no progress notes, no FYIs`; and `### After each /vss completes` still follows § fromto format's subsections in the same order as today (three files → fromto format → Question format → Answer format → Consume protocol → Precedence → Interaction with the loop → After each /vss completes).
- AC8 `/brain2/meta/fromto-format.md` exists with YAML frontmatter fields `title`, `aliases`, `state: authored`, `author`, `checked: []`, `reviewed: []`, `authorised:` (empty value), `source_type: internal`, `sources`, `created: 2026-09-02`, `recorded_at: 2026-09-02`, `cssclasses: [trust-authored]`, `tags` (containing `vibe` and `fromto`); its body contains the same fenced template as AC2 verbatim and the sentence `Edit this note to change the format for every project` (or an equivalent containing `every project`); it never sets `state` above `authored` and never fills `authorised:`.
- AC9 `smoke-test.py` gains `test_vsss_fromto_format()` (defined near the other `test_vsss_*` functions, registered in `main()` next to them) asserting AC1–AC7 against `VSSS_MD`; AC8 is asserted only when `/brain2/meta/fromto-format.md` exists (skip-with-note otherwise, since brain2 is a per-machine mount). No existing test is edited.
- AC10 `python3 code-check.py` exits 0 and `python3 smoke-test.py` exits 0 (foreground, timeout 600000).
- AC11 Scope lock: `git diff --name-only 73172fb` plus untracked files list only `devcontainer/commands/vsss.md`, `smoke-test.py`, `CHANGELOG.md`, `TODO.md`, `.vs/`, `.vss/`; brain2 is written by file only (no git commands against /brain2).
- AC12 vsss.md word count does not grow by more than 120 words versus 73172fb (`wc -w`): the block is added, two mandates are deleted.

## Out of scope
- Any change to § Reporting back at exit's terminal report content, the exit conditions, the optimiser brief, the auto-resume marker, or § Question format / Answer format / Consume protocol semantics.
- Changing the from<User> answer contract or the Q&A-archive format.
- Rewriting existing fromClaude files in brain2 (the chair may separately re-emit `/brain2/andeye/vibe-fromClaude.md` in the new format after the pass).
- Any file other than those in AC11.

## Test location
`smoke-test.py` — Tester adds `test_vsss_fromto_format()`; Generator does not touch smoke-test.py at all in this task.

## Proposed budget
2 cycles.

## Model plan
- Planner + Evaluator: session model (Fable 5.1 chair).
- Spec Critic: sonnet.
- Generator: sonnet, ceiling opus (small, fully specified prose surgery).
- Tester: haiku, ceiling sonnet.
- Fable rung: pre-authorised (--fable-subagents, user prose grant for this /vsss run), not indicated.
