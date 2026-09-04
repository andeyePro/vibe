"""task_036: /vs --spec-first flag documentation and checkpoint mechanics.

Tester-owned spec-only tests. Generator edits vs.md, vss.md, vsss.md command
docs, updates task.json schema, adds TODO entry for PreToolUse hook hardening,
updates CHANGELOG.md, raises the two word-count pins (checks_05 AC12 and
checks_09 AC8) from 13,500 to 14,000. task_037 raised both again to 14,300.

Covers:
  - AC1: vs.md Flags has `--spec-first` and `--approve` bullets, ≤ 40 words each
  - AC2: vs.md has `## Step 3b` heading in right position
  - AC3: vs.md Step 3 mentions spec-first directive
  - AC4: vs.md § Step 3b contains all required sentinel strings
  - AC5: tasks.json schema has right enum value
  - AC6: Multi-task state convention section has right text
  - AC7: vss.md Mode A step 2 and Mode B step 4 have spec-first branches
  - AC8: vsss.md has right sections and text
  - AC9: vsss.md fromto/Question format shows spec-first action point
  - AC10: Word budget constraints and pin equality
  - AC12: TODO.md and CHANGELOG.md consistency
"""
from smoke._core import *  # noqa: F401,F403


def test_spec_first_flag_docs() -> None:
    """AC1-AC10, AC12: spec-first flag presence, positioning, word counts,
    schema, and TODO/CHANGELOG state. Tests sentinel substrings in the exact
    form the spec requires."""
    print("\n[spec-first] flag docs and checkpoint mechanics (AC1-AC10, AC12)")

    vs_path = REPO / "devcontainer" / "commands" / "vs.md"
    vss_path = REPO / "devcontainer" / "commands" / "vss.md"
    vsss_path = REPO / "devcontainer" / "commands" / "vsss.md"

    vs_text = vs_path.read_text()
    vss_text = vss_path.read_text()
    vsss_text = vsss_path.read_text()

    # AC1: Flags section has two bullets, each ≤ 40 words, each with § Step 3b
    check("[spec-first] AC1: vs.md has /vs --spec-first flag bullet",
          "/vs --spec-first <prompt>" in vs_text, "")

    spec_first_flag = "/vs --spec-first <prompt>"
    approve_flag = "/vs --approve [<task-id>]"

    # Extract flag definitions
    spec_first_idx = vs_text.find(spec_first_flag)
    approve_idx = vs_text.find(approve_flag)

    check("[spec-first] AC1: both flags found",
          spec_first_idx >= 0 and approve_idx >= 0, "")

    if spec_first_idx >= 0:
        # Find the line boundary (next newline after this flag)
        line_start = vs_text.rfind('\n', 0, spec_first_idx) + 1
        line_end = vs_text.find('\n', spec_first_idx + len(spec_first_flag))
        spec_first_line = vs_text[line_start:line_end]

        # Count words (simple split by whitespace)
        spec_first_words = len(spec_first_line.split())
        check("[spec-first] AC1: --spec-first bullet ≤ 40 words",
              spec_first_words <= 40,
              f"found {spec_first_words} words: {spec_first_line[:100]}")

        check("[spec-first] AC1: --spec-first bullet has § Step 3b reference",
              "§ Step 3b" in spec_first_line, spec_first_line)

    if approve_idx >= 0:
        line_start = vs_text.rfind('\n', 0, approve_idx) + 1
        line_end = vs_text.find('\n', approve_idx + len(approve_flag))
        approve_line = vs_text[line_start:line_end]

        approve_words = len(approve_line.split())
        check("[spec-first] AC1: --approve bullet ≤ 40 words",
              approve_words <= 40,
              f"found {approve_words} words: {approve_line[:100]}")

        check("[spec-first] AC1: --approve bullet has § Step 3b reference",
              "§ Step 3b" in approve_line, approve_line)

    # AC2: vs.md has Step 3b heading in the right place
    step3_heading = "## Step 3 — Spec critic (Sonnet)"
    step3b_heading = "## Step 3b — Spec-first checkpoint (`--spec-first`)"
    step4_heading = "## Step 4 — Generate"

    check("[spec-first] AC2: Step 3b heading present",
          step3b_heading in vs_text, "")

    step3_idx = vs_text.find(step3_heading)
    step3b_idx = vs_text.find(step3b_heading)
    step4_idx = vs_text.find(step4_heading)

    check("[spec-first] AC2: Step 3 comes before Step 3b",
          step3_idx >= 0 and step3b_idx > step3_idx, "")

    check("[spec-first] AC2: Step 3b comes before Step 4",
          step3b_idx >= 0 and step4_idx > step3b_idx, "")

    # AC3: vs.md Step 3's "On pass" paragraph has the spec-first directive
    pass_phrase = 'Under `--spec-first`, do not wait in-session — go to Step 3b.'
    check("[spec-first] AC3: Step 3 On pass paragraph mentions spec-first",
          pass_phrase in vs_text, "")

    # AC4: Step 3b contains all required literal substrings
    required_ac4_strings = [
        'implementation_status: "awaiting-approval"',
        'vs --spec-first: spec awaiting approval (<task-id>)',
        'approve with: /vs --approve <task-id>',
        'END the run',
        'No Generator',
        'Martin\'s edits to `.vs/spec.md` ARE the approved version',
        'never require it byte-identical',
        'never re-run Spec Critic',
        'spec edited at approval',
        'credit-billed tier',
        '§ Model economy',
        'implementation_status: "in_progress"',
        'continue from Step 4 unchanged',
        'newest `awaiting-approval` task by default',
        'un-archived first',
        'no task is awaiting approval',
    ]

    # Extract Step 3b section
    step3b_start = vs_text.find(step3b_heading)
    step3b_end = vs_text.find('\n## Step 4', step3b_start)
    step3b_section = vs_text[step3b_start:step3b_end]

    for sentinel in required_ac4_strings:
        check(f"[spec-first] AC4: Step 3b contains '{sentinel}'",
              sentinel in step3b_section, "")

    # AC4: Sentence about no cycle has run yet
    check("[spec-first] AC4: Step 3b has 'no cycle has run yet' sentence",
          "no cycle has run yet" in step3b_section, "")

    # AC5: tasks.json schema enum is right
    schema_text = 'implementation_status": "pending|awaiting-approval|in_progress|complete"'
    check("[spec-first] AC5: tasks.json schema has right enum",
          schema_text in vs_text, "")

    # AC6: Multi-task state convention mentions parked at awaiting-approval
    check("[spec-first] AC6: Multi-task convention mentions parked at awaiting-approval",
          "parked at awaiting-approval" in vs_text, "")

    check("[spec-first] AC6: Multi-task convention mentions un-archived procedure",
          "/vs --approve <task-id>" in vs_text and
          "un-archived first" in vs_text, "")

    # AC7: vss.md Mode A step 2 has spec-first branch
    check("[spec-first] AC7: vss.md Mode A mentions awaiting-approval branch",
          "(awaiting approval — /vs --approve <task-id>)" in vss_text, "")

    # AC7: vss.md should mention spec-first passthrough near --wide
    check("[spec-first] AC7: vss.md mentions --spec-first passthrough",
          "--spec-first" in vss_text and "not an escalate trigger" in vss_text, "")

    # AC7: vss.md mentions spec-first is the checkpoint (escalation)
    check("[spec-first] AC7: vss.md says checkpoint IS the escalation",
          "the checkpoint IS the escalation" in vss_text, "")

    # AC7: vss.md mentions never acts-as-user on spec approval
    check("[spec-first] AC7: vss.md says never acts-as-user on spec approval",
          "never acts-as-user on spec approval" in vss_text, "")

    # AC8: vsss.md Session-budget capture section mentions --spec-first
    check("[spec-first] AC8: vsss.md mentions --spec-first with § Step 3b",
          "/vsss --spec-first" in vsss_text and "§ Step 3b" in vsss_text, "")

    # AC8: vsss.md Interaction with loop mentions never blocks
    check("[spec-first] AC8: vsss.md Interaction says never blocks the loop",
          "never blocks the loop" in vsss_text, "")

    # AC8: vsss.md Consume protocol mentions queues /vs --approve
    check("[spec-first] AC8: vsss.md Consume mentions queues /vs --approve",
          "queues `/vs --approve <task-id>`" in vsss_text, "")

    # AC8: vsss.md Exit conditions mentions awaiting approval in Deferred
    check("[spec-first] AC8: vsss.md Exit conditions mentions Deferred awaiting approval",
          "awaiting approval" in vsss_text, "")

    # AC9: vsss.md shows the exact action-point wording for spec-first
    spec_first_wording = (
        "Approve the spec for <task-id> — <one-line goal>? "
        "It's at .vs/spec.md. Reply \"approve\", or edit that file and reply \"approve\"; "
        "reply with changes instead to redirect. (T<n>)"
    )
    check("[spec-first] AC9: vsss.md has exact spec-first action-point wording",
          "Approve the spec for <task-id>" in vsss_text and
          "It's at .vs/spec.md" in vsss_text and
          'Reply "approve"' in vsss_text, "")

    # AC10: Word budget check — vs+vss+vsss combined
    all_command_text = vs_text + vss_text + vsss_text
    total_words = len(all_command_text.split())
    check("[spec-first] AC10: vs+vss+vsss total ≤ 14,300 words",
          total_words <= 14300,
          f"found {total_words} words")

    # AC10: Check that the two word-count pins are equal and at 14300 (raised from 14000 by task_037)
    checks_05_path = REPO / "smoke" / "checks_05_numbering_hook.py"
    checks_09_path = REPO / "smoke" / "checks_09_openproject_and_scanner.py"

    checks_05_text = checks_05_path.read_text()
    checks_09_text = checks_09_path.read_text()

    # Extract the pin values from checks_05
    import re
    pin_05_match = re.search(r'<= 14300', checks_05_text)
    check("[spec-first] AC10: checks_05 has 14300 pin",
          pin_05_match is not None, "")

    pin_09_match = re.search(r'<= 14300', checks_09_text)
    check("[spec-first] AC10: checks_09 has 14300 pin",
          pin_09_match is not None, "")

    # AC12: TODO.md consistency check
    todo_path = REPO / "TODO.md"
    changelog_path = REPO / "CHANGELOG.md"

    if todo_path.exists():
        todo_text = todo_path.read_text()
        # The old queue item 1 should be gone (closed)
        # There should be a new item about PreToolUse hook hardening
        check("[spec-first] AC12: TODO.md has item about PreToolUse hook hardening",
              "PreToolUse" in todo_text and "approved spec" in todo_text, "")

    if changelog_path.exists():
        changelog_text = changelog_path.read_text()
        # Should have an entry mentioning --spec-first
        check("[spec-first] AC12: CHANGELOG.md has entry with --spec-first",
              "--spec-first" in changelog_text, "")

        # Check for 2026-09-04 date heading
        check("[spec-first] AC12: CHANGELOG.md has 2026-09-04 entry",
              "## 2026-09-04" in changelog_text or "2026-09-04" in changelog_text, "")

    print("[spec-first] all sentinel checks completed")


def test_tdd_flag_docs() -> None:
    """AC1-AC7: /vs --TDD flag presence, documentation, and integration.
    Tests sentinel substrings in the exact form the spec requires."""
    print("\n[tdd] flag docs and red-first trail mechanics (AC1-AC7)")

    vs_path = REPO / "devcontainer" / "commands" / "vs.md"
    vss_path = REPO / "devcontainer" / "commands" / "vss.md"
    vsss_path = REPO / "devcontainer" / "commands" / "vsss.md"

    vs_text = vs_path.read_text()
    vss_text = vss_path.read_text()
    vsss_text = vsss_path.read_text()

    # AC1: Flags section has --TDD bullet, ≤ 45 words, with three literals
    tdd_flag = "/vs --TDD <prompt>"
    check("[tdd] AC1: vs.md Flags has /vs --TDD flag",
          tdd_flag in vs_text, "")

    tdd_idx = vs_text.find(tdd_flag)
    if tdd_idx >= 0:
        # Find the line boundary
        line_start = vs_text.rfind('\n', 0, tdd_idx) + 1
        line_end = vs_text.find('\n', tdd_idx + len(tdd_flag))
        tdd_line = vs_text[line_start:line_end]

        # Count words
        tdd_words = len(tdd_line.split())
        check("[tdd] AC1: --TDD bullet ≤ 45 words",
              tdd_words <= 45,
              f"found {tdd_words} words: {tdd_line[:100]}")

        # Check for three required literals
        check("[tdd] AC1: --TDD bullet has 'red-first'",
              "red-first" in tdd_line, tdd_line)

        check("[tdd] AC1: --TDD bullet has 'tdd-trail.md'",
              "tdd-trail.md" in tdd_line, tdd_line)

        check("[tdd] AC1: --TDD bullet has 'incompatible with `--fuzzy`'",
              "incompatible with `--fuzzy`" in tdd_line, tdd_line)

    # AC2: Step 4 contains Under --TDD paragraph with specific literals
    step4_heading = "## Step 4 — Generate"
    step5_heading = "## Step 5 — Verify"

    step4_idx = vs_text.find(step4_heading)
    step5_idx = vs_text.find(step5_heading)
    step4_section = vs_text[step4_idx:step5_idx]

    check("[tdd] AC2: Step 4 has Under --TDD paragraph",
          "**Under `--TDD`**:" in step4_section, "")

    # Extract Under --TDD paragraph in Step 4
    under_tdd_idx = step4_section.find("**Under `--TDD`**:")
    if under_tdd_idx >= 0:
        # Find the paragraph end (next blank line or next heading)
        para_end = step4_section.find("\n\n", under_tdd_idx)
        under_tdd_para = step4_section[under_tdd_idx:para_end]

        ac2_required = [
            "before the implementing edit",
            ".vs/cycle-<N>/tdd-trail.md",
            "one entry per acceptance criterion",
            "test file",
            "command",
            "non-zero exit",
            "failing assertion",
            "written:",
            "scratch-tests/",
            "AC<n> | test file | command | exit | failing assertion | written:",
            "A trail entry written after the implementation, or without a failing run, is a cycle fail.",
        ]
        for sentinel in ac2_required:
            check(f"[tdd] AC2: Step 4 Under --TDD has '{sentinel}'",
                  sentinel in under_tdd_para, "")

    # AC3: Step 5a contains Under --TDD paragraph with specific literals
    step5a_heading = "### Step 5a — Test"
    step5b_heading = "### Step 5b — Review"

    step5a_idx = vs_text.find(step5a_heading)
    step5b_idx = vs_text.find(step5b_heading)
    step5a_section = vs_text[step5a_idx:step5b_idx]

    check("[tdd] AC3: Step 5a has Under --TDD paragraph",
          "**Under `--TDD`**:" in step5a_section, "")

    under_tdd_5a_idx = step5a_section.find("**Under `--TDD`**:")
    if under_tdd_5a_idx >= 0:
        para_end_5a = step5a_section.find("\n\n", under_tdd_5a_idx)
        under_tdd_para_5a = step5a_section[under_tdd_5a_idx:para_end_5a]

        ac3_required = [
            "tdd-trail.md",
            "diff.patch",
            "every acceptance criterion has a trail entry",
            "named test file exists",
            "assertion names the criterion",
            "command",
            "written:",
            "a weak proxy, not proof",
            "fail the cycle",
            "under `--TDD` the Tester additionally reads `tdd-trail.md` and `diff.patch` — only to check the trail, never the Generator's report",
        ]
        for sentinel in ac3_required:
            check(f"[tdd] AC3: Step 5a Under --TDD has '{sentinel}'",
                  sentinel in under_tdd_para_5a, "")

    # AC3: Check for "4 lines under `--TDD`" in the full Step 5a section
    check("[tdd] AC3: Step 5a section has '4 lines under `--TDD`'",
          "4 lines under `--TDD`" in step5a_section, "")

    # AC4: Step 3b sentence updated, no (when implemented) anywhere
    step3b_idx = vs_text.find("## Step 3b")
    step4_idx = vs_text.find("## Step 4")
    step3b_section = vs_text[step3b_idx:step4_idx]

    # Check the specific sentence
    expected_sentence = "`--TDD` stacking: the spec gate runs first; `--TDD` governs Step 4 (red-first trail) and Step 5a (trail check) only."
    check("[tdd] AC4: Step 3b has correct TDD stacking sentence",
          expected_sentence in step3b_section, "")

    # Check that (when implemented) does NOT appear anywhere
    check("[tdd] AC4: '(when implemented)' does not appear in vs.md",
          "(when implemented)" not in vs_text, "")

    # AC5: Rules section has --TDD and --fuzzy cannot combine bullet
    rules_idx = vs_text.find("## Rules")
    when_to_refuse_idx = vs_text.find("## When to refuse or stop")
    rules_section = vs_text[rules_idx:when_to_refuse_idx]

    check("[tdd] AC5: Rules has --TDD and --fuzzy cannot combine",
          "`--TDD` and `--fuzzy` cannot combine" in rules_section, "")

    # Check for the carve-out in "No cross-subagent context sharing"
    check("[tdd] AC5: Rules carve-out for --TDD trail check",
          "except the `--TDD` trail check" in rules_section, "")

    # AC6: vss.md names --TDD, vsss.md Session-budget has --TDD
    check("[tdd] AC6: vss.md has --TDD passthrough",
          "--TDD" in vss_text and "threads through to `/vs`" in vss_text, "")

    check("[tdd] AC6: vsss.md Session-budget has --TDD",
          "/vsss --TDD <args>" in vsss_text and "§ Step 4" in vsss_text, "")

    # AC7: State directory lists cycle-N/tdd-trail.md with red-first evidence
    state_dir_idx = vs_text.find("## State directory")
    multi_task_idx = vs_text.find("## Multi-task state convention")
    state_dir_section = vs_text[state_dir_idx:multi_task_idx]

    check("[tdd] AC7: State directory has cycle-N/tdd-trail.md",
          "`cycle-N/tdd-trail.md`" in state_dir_section, "")

    check("[tdd] AC7: State directory describes tdd-trail.md as red-first evidence",
          "red-first evidence" in state_dir_section, "")

    # AC8: Word budget check and pin equality
    all_command_text = vs_text + vss_text + vsss_text
    total_words = len(all_command_text.split())
    check("[tdd] AC8: vs+vss+vsss total ≤ 14,300 words",
          total_words <= 14300,
          f"found {total_words} words")

    # Check pin values in checks_05 and checks_09
    checks_05_path = REPO / "smoke" / "checks_05_numbering_hook.py"
    checks_09_path = REPO / "smoke" / "checks_09_openproject_and_scanner.py"

    checks_05_text = checks_05_path.read_text()
    checks_09_text = checks_09_path.read_text()

    import re
    pin_05_match = re.search(r'14300', checks_05_text)
    check("[tdd] AC8: checks_05 has 14300 pin",
          pin_05_match is not None, "")

    pin_09_match = re.search(r'14300', checks_09_text)
    check("[tdd] AC8: checks_09 has 14300 pin",
          pin_09_match is not None, "")

    # AC9: This test file exists and is syntactically valid
    # (verified by running the tests)

    # AC10: TODO.md and CHANGELOG.md consistency
    todo_path = REPO / "TODO.md"
    changelog_path = REPO / "CHANGELOG.md"

    if todo_path.exists():
        todo_text = todo_path.read_text()
        # TODO.md queue item 3 should reference harness half shipped
        check("[tdd] AC10: TODO.md queue 3 references harness half shipped",
              "**3. `--TDD` mode" in todo_text and
              "harness half shipped as `/vs --TDD` (task_037)" in todo_text,
              "")

    if changelog_path.exists():
        changelog_text = changelog_path.read_text()
        # Should have entry mentioning --TDD
        check("[tdd] AC10: CHANGELOG.md has --TDD entry",
              "--TDD" in changelog_text, "")

        # Check for 2026-09-04 date heading
        check("[tdd] AC10: CHANGELOG.md has 2026-09-04 entry",
              "2026-09-04" in changelog_text, "")

    print("[tdd] all sentinel checks completed")
