# Generator report — task_029 (fromto format), cycle 1

## What changed

1. **`devcontainer/commands/vsss.md`**
   - Inserted a new `### fromto format` subsection between `### The three
     files` and `### Question format (fromClaude)` (AC1). Contains, verbatim:
     - The AC2 fenced template.
     - The AC3 sentinels: `one ordered list and nothing else`, `action
       points only`, `contiguous from 1`, `no session report`,
       `Information appears only where it answers a question the user
       asked` — plus a pointer to `(§ Question format)` for the
       no-progress-notes/no-FYIs hygiene rule and thread tags (not
       restated).
     - The AC4 exit rule: exact sentinel `Session log:
       ` `.vss/sessions/<start-ISO>.md` ` — <N> commits, <pushed|not
       pushed>.` plus the words `exactly one line`.
     - The AC5 override rule (`/brain2/meta/fromto-format.md`,
       `overrides this default verbatim`) and the credential-boundary
       sentence (`write-files-only`, `never `git` against`).
   - Deleted the whole `### At exit` subsection (heading + paragraph).
   - Deleted § Reporting back at exit's closing "If fromto channels are
     active…" paragraph.
   - Section order preserved: three files → fromto format → Question
     format → Answer format → Consume protocol → Precedence →
     Interaction with the loop → After each /vss completes.
   - Preserved: `## Reporting back at exit`, `Total iterations run.`,
     `` Lead with `---` before the report block. ``, `### Question format
     (fromClaude)` and its hygiene sentence.

2. **`/brain2/meta/fromto-format.md`** (new file, write-only — no git
   command run against `/brain2`): frontmatter with `state: authored`,
   `authorised:` empty, `author: [claude-sonnet-5]`, `created`/
   `recorded_at: 2026-09-02`, `cssclasses: [trust-authored]`, `tags:
   [meta, vibe, vsss, fromto]`, plus `title`, `aliases`, `checked: []`,
   `reviewed: []`, `source_type: internal`, `sources: []`. Body: an
   `> [!authored]` callout, an explanatory paragraph containing "every
   project", the same fenced template verbatim, and an 8-bullet rule
   list.

3. **`CHANGELOG.md`**: new entry at the top of the existing `##
   2026-09-02` section (newest-first), describing the fix and the
   contradiction it removes.

4. **`.vs/tasks.json`**: task_029 `implementation_status` →
   `"complete"` (only that value edited; JSON validated after edit).

## Word counts (AC12 + cross-task collision)

- `vsss.md`: baseline (73172fb) 4955 words → final 4958 words. **Net
  growth: +3 words** (well under the AC12 cap of ≤120).
- Mid-draft the new section was ~172 words (before trimming), which
  produced a net growth of +81 words. That tripped a **different,
  pre-existing test** in `smoke-test.py`
  (`test_task028_fragment_merges_and_fable_grant`'s
  `[ac8] vs+vss+vsss total words <= 12700`, a task_028 assertion
  unrelated to this spec) because `vs.md` (5746w) + `vss.md` (1995w) +
  `vsss.md` (5036w at that point) = 12777 > 12700. Since task_029's
  own AC10 requires `smoke-test.py` to exit 0, and I'm not permitted to
  edit `smoke-test.py`, I tightened the new § fromto format prose
  (kept every literal AC2–AC5 sentinel, cut connective wording) until
  `vsss.md` landed at 4958 words. Final combined total: 5746 + 1995 +
  4958 = **12699** (≤ 12700, 1-word margin).
  - Trade-off taken to hit this budget: the new section states the
    exit-line rule and the override rule tersely; it does not restate
    (as a separate sentence) that "the terminal report to the user in
    § Reporting back at exit is unchanged" — that invariant is instead
    enforced structurally (§ Reporting back at exit is preserved
    byte-for-byte in content, and no mandate anywhere else duplicates
    it into fromClaude), and AC4/AC7 only test for the literal
    sentinel/preserved strings, not for that explanatory cross-reference.

## Scratch TDD

Script: `/workspace/.vs/cycle-1/scratch-tests/check_task029.py` (plus a
frozen `vsss_baseline.md` fixture pulled via `git show
73172fb:devcontainer/commands/vsss.md`). Not part of the permanent
suite — scoped to this cycle's scratch-tests dir per instructions.

- **Red** (before any edits): 10 passed, 20 failed — all failures were
  the not-yet-done work (AC1–AC6 not-present checks, AC7 heading order
  incomplete). Exit code 1.
- **Green** (after all edits, including the brain2 note): 53 passed, 0
  failed. Exit code 0.

Two bugs found and fixed in the scratch checker itself during the
red→green loop (both false negatives from markdown line-wrap and a
regex `\s*` accidentally spanning a YAML newline) — documented as
comments in the script; they did not affect the real files, only the
checker's own string matching.

## Verification commands run

- `python3 code-check.py` → exit 0 (shellcheck clean, 19 files;
  vsss.md itself isn't shell but the run confirms nothing else broke).
- `python3 smoke-test.py` (foreground, timeout 600000) → exit 0, full
  suite green including `test_task028_fragment_merges_and_fable_grant`'s
  `[ac8] vs+vss+vsss total words <= 12700` (passing at 12699). Run
  twice: once after the word-budget trim, once more after a final
  1-word readability polish to the purpose line — both green; no
  further file edits followed the second run.
- `git diff --name-only 73172fb` + `git ls-files --others
  --exclude-standard` → `.vs/briefs/roadmap-2026-09-02.md`, `.vs/spec.md`,
  `.vs/tasks.json`, `.vss/sessions/2026-09-02T16-04-16Z.md`,
  `CHANGELOG.md`, `TODO.md`, `devcontainer/commands/vsss.md`,
  `smoke-test.py` — all within AC11's allowed list (`.vs/`, `.vss/`,
  `CHANGELOG.md`, `TODO.md`, `devcontainer/commands/vsss.md`,
  `smoke-test.py`). Note: `smoke-test.py`, `.vs/tasks.json` (formatting),
  `CHANGELOG.md`, `TODO.md`, and the `.vss/sessions/` file already
  carried unrelated, pre-existing working-tree diffs from a prior
  task_028 session before this Generator run started (verified via
  `git diff 73172fb -- <file>` at the top of this session); I did not
  touch `smoke-test.py` and did not revert those pre-existing changes.
- `/brain2/meta/fromto-format.md` written via the Write tool only; no
  `git` command was run against `/brain2` at any point.

## Anything unsatisfied

Nothing outstanding against AC1–AC8, AC11, AC12. AC9 (the
`test_vsss_fromto_format()` smoke test) and re-verifying AC10 with that
new test included are the Tester's job per the spec's "Test location"
section — Generator did not touch `smoke-test.py`.

One judgment call flagged for the Evaluator: the terse final wording of
§ fromto format (see word-count trade-off above) satisfies every AC
literal-string requirement but is leaner in explanatory prose than my
first draft — worth a read to confirm it's still clear enough for a
cold read at session start.
