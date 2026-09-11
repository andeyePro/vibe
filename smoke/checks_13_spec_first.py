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


def test_ask_command_docs() -> None:
    """Phase 1a command guidance and integration are executable acceptance contracts."""
    text = (REPO / "devcontainer/commands/ask.md").read_text()
    check("[ask] discoverable command", text.startswith("---\n") and "description:" in text, "")
    for marker in ("5k", "27k", "bulk payloads, not trivial questions", "per-task credit consent",
                   "--consent-credits", "--output-schema", "--output-format json",
                   "VIBE_CLAUDE_P_SETTINGS", "VIBE_CLAUDE_P_BILLING", "usage.total_tokens"):
        check(f"[ask] guidance includes {marker}", marker in text, "")
    review = (REPO / "devcontainer/commands/review.md").read_text()
    for marker in ("vibe-delegate slots", "vibe-delegate review codex", ".vibe/review-slots",
                   "same snapshot", "--solo --slot", "never a silent PASS", "Never recover findings by parsing prose"):
        check(f"[review] phase 1a contract includes {marker}", marker in review, "")
    check("[ask] installer auto-syncs new commands",
          'install_dir commands' in INSTALL_EXTRAS.read_text(), "")
    check("[ask] post-relaunch manual coverage", "### Test 54:" in MANUAL_TESTS_MD.read_text(), "")


def test_review_command_docs() -> None:
    """AC1-AC8: /review command documentation and integration.
    Tests sentinel substrings and file presence in the exact form the spec requires."""
    print("\n[review] command docs and fan-out architecture (AC1-AC8)")

    review_path = REPO / "devcontainer" / "commands" / "review.md"

    # AC1: review.md exists, ≤ 850 words, starts with ---, has description with code-review and fan-out
    check("[review] AC1: review.md exists",
          review_path.exists(), "")

    if review_path.exists():
        review_text = review_path.read_text()

        # Check word count
        word_count = len(review_text.split())
        check("[review] AC1: review.md ≤ 850 words",
              word_count <= 850,
              f"found {word_count} words")

        # Check starts with ---
        check("[review] AC1: review.md starts with ---",
              review_text.startswith("---"), "")

        # Check for description line with both code-review and fan-out
        has_description = "description:" in review_text
        check("[review] AC1: review.md has description: line",
              has_description, "")

        if has_description:
            check("[review] AC1: description mentions code-review",
                  "code-review" in review_text, "")
            check("[review] AC1: description mentions fan-out",
                  "fan-out" in review_text, "")

    # AC2: specific sentences and usage patterns
    if review_path.exists():
        review_text = review_path.read_text()

        # task_043: the gemini slot is wired, so the old "zero enabled slots"
        # sentence is gone. What must hold now is that the slot is key-gated and
        # that the no-key state is still Claude-only.
        check("[review] AC2: gemini slot is key-gated",
              "runs whenever `GEMINI_API_KEY` is present" in review_text, "")
        check("[review] AC2: no available outside slots is Claude-only",
              "Without available outside slots, /review is Claude-only." in review_text, "")

        # Usage line
        usage_line = "/review [--solo] [--level low|medium|high|max] [--slot <name>] [--comment] [<target>]"
        check("[review] AC2: usage line present",
              usage_line in review_text, "")

        # Default level is high
        check("[review] AC2: mentions default level high",
              "high" in review_text and "default" in review_text, "")

        # Default target is the working diff
        check("[review] AC2: mentions working diff as default",
              "the working diff" in review_text, "")

        # Skill invocation literal
        check("[review] AC2: Skill invocation literal",
              'Skill(skill: "code-review", args: "<level> [<target>]")' in review_text, "")

        # Refuses --level ultra
        check("[review] AC2: refuses --level ultra",
              "--level ultra" in review_text, "")

    # AC3: Slot registry section
    if review_path.exists():
        review_text = review_path.read_text()

        check("[review] AC3: has Slot registry heading",
              "## Slot registry" in review_text, "")

        # Check for gemini and codex rows with no enabled status using regex
        import re
        check("[review] AC3: gemini row has enabled=auto (task_043 wired it)",
              re.search(r'^\|\s*gemini\s*\|\s*auto\s*\|', review_text, re.MULTILINE) is not None,
              "")

        check("[review] AC3: codex row has enabled=auto",
              re.search(r'^\|\s*codex\s*\|\s*auto\s*\|', review_text, re.MULTILINE) is not None,
              "")

        # Check for gemini needs content
        check("[review] AC3: gemini needs GEMINI_API_KEY",
              "GEMINI_API_KEY" in review_text, "")

        check("[review] AC3: gemini needs the API host allowlisted",
              "generativelanguage.googleapis.com" in review_text, "")

        # task_043: the entry must be per-project (.vibe/domains), NOT the
        # shipped list — only extra domains get the mid-session re-resolve, and
        # the Google endpoint is CDN-fronted.
        check("[review] AC3: allowlist entry is per-project, not shipped",
              ".vibe/domains" in review_text
              and "NOT in the shipped `init-firewall.sh` list" in review_text, "")
        check("[review] AC3: shipped firewall list untouched by the gemini slot",
              "generativelanguage" not in (REPO / "devcontainer" / "init-firewall.sh").read_text(), "")

        check("[review] AC3: codex needs ChatGPT subscription",
              "a ChatGPT subscription" in review_text, "")

        # Check for the key sentence about slot enablement
        slot_sentence = "A slot is enabled only when every item in its needs column exists."
        check("[review] AC3: slot enablement sentence",
              slot_sentence in review_text, "")

    # AC4: Merge section and verdict structure
    if review_path.exists():
        review_text = review_path.read_text()

        check("[review] AC4: has Merge heading",
              "## Merge" in review_text, "")

        # Required literals
        check("[review] AC4: mentions correlated consensus",
              "correlated consensus" in review_text, "")

        check("[review] AC4: mentions independent consensus",
              "independent consensus" in review_text, "")

        check("[review] AC4: mentions split verdicts",
              "split verdicts" in review_text, "")

        check("[review] AC4: mentions unrefuted BLOCKING dissent rule",
              "an unrefuted BLOCKING dissent from any single reviewer is never a pass" in review_text, "")

        check("[review] AC4: references /vs Step 5c",
              "see `/vs § Step 5c`" in review_text or "§ Step 5c" in review_text, "")

        # Review verdict structure
        check("[review] AC4: has Review verdict heading",
              "## Review verdict" in review_text, "")

        check("[review] AC4: has Findings sub-heading",
              "### Findings" in review_text, "")

        check("[review] AC4: has Dissent sub-heading",
              "### Dissent" in review_text, "")

        check("[review] AC4: has Verdict sub-heading",
              "### Verdict" in review_text, "")

        # Verdict values
        check("[review] AC4: mentions PASS verdict",
              "PASS" in review_text, "")

        check("[review] AC4: mentions FAIL verdict",
              "FAIL" in review_text, "")

        check("[review] AC4: mentions SPLIT verdict",
              "SPLIT" in review_text, "")

    # AC5: Option behavior rules
    if review_path.exists():
        review_text = review_path.read_text()

        check("[review] AC5: describes --solo",
              "--solo" in review_text, "")

        check("[review] AC5: slot refuses with one line about needs",
              "refuse with one line naming what it needs" in review_text, "")

        check("[review] AC5: --comment is GitHub-outward",
              "never posts to GitHub unless --comment is passed" in review_text, "")

        check("[review] AC5: default fan-out matches solo with no available slots",
              "With no available outside slots the default fan-out is identical to --solo." in review_text, "")

        check("[review] AC5: comment is hard-escalate",
              "--comment is GitHub-outward like push: /vss and /vsss treat it as hard-escalate, never auto-fired." in review_text, "")

    # AC6: Relation to /vs and safety floor
    if review_path.exists():
        review_text = review_path.read_text()

        check("[review] AC6: mentions /vs --panel",
              "/vs --panel" in review_text, "")

        check("[review] AC6: works on any diff",
              "/review` works on any diff" in review_text or "works on any diff" in review_text, "")

        check("[review] AC6: inherits /vss safety floor",
              "Inherits /vss's safety floor: no push, no hook or firewall edits." in review_text, "")

    # AC7: Integration with README, CLAUDE.md, MANUAL-TESTS.md
    readme_path = REPO / "README.md"
    claude_md_path = REPO / "CLAUDE.md"
    manual_tests_path = REPO / "MANUAL-TESTS.md"

    if readme_path.exists():
        readme_text = readme_path.read_text()
        readme_lines = readme_text.split('\n')

        # Line 12 (index 11) should contain /review
        check("[review] AC7: README.md line 12 mentions /review",
              len(readme_lines) > 11 and "/review" in readme_lines[11],
              f"line 12: {readme_lines[11] if len(readme_lines) > 11 else 'N/A'}")

        # README should have a paragraph starting with /review
        check("[review] AC7: README.md has /review paragraph",
              "^`/review`" in readme_text or "\n`/review`" in readme_text or
              "/review" in readme_text,
              "")

    if claude_md_path.exists():
        claude_text = claude_md_path.read_text()
        # task_043: this asserted "/review is on CLAUDE.md line 13", which broke
        # the moment an unrelated bullet was inserted above it (it had never run
        # — the whole function was unregistered). Pin the CONTENT instead: the
        # shipped-extras bullet must list /review among the commands.
        extras_line = next(
            (ln for ln in claude_text.split("\n")
             if ln.lstrip().startswith("- Shipped extras:")), "")
        check("[review] AC7: CLAUDE.md shipped-extras bullet lists /review",
              "/review" in extras_line, f"shipped-extras bullet: {extras_line[:160]}")

    if manual_tests_path.exists():
        manual_tests_text = manual_tests_path.read_text()
        check("[review] AC7: MANUAL-TESTS.md mentions review.md",
              "review.md" in manual_tests_text, "")

    # AC8: TODO.md and CHANGELOG.md consistency
    todo_path = REPO / "TODO.md"
    changelog_path = REPO / "CHANGELOG.md"

    if todo_path.exists():
        todo_text = todo_path.read_text()
        check("[review] AC8: TODO.md has /review queue pointer",
              "/review" in todo_text and "task_039" in todo_text, "")

    if changelog_path.exists():
        changelog_text = changelog_path.read_text()
        check("[review] AC8: CHANGELOG.md has /review and task_039",
              "/review" in changelog_text and "task_039" in changelog_text, "")

    print("[review] all sentinel checks completed")


def test_gemini_slot_wiring() -> None:
    """task_043: the /review `gemini` outside-reviewer slot is wired end to end.

    Three properties, none of which the doc-string checks above can see:
      - the launcher resolves GEMINI_API_KEY from ~/.vibe/tokens, and the
        slash-free key does not collide with an `owner/repo` PAT line;
      - the value crosses into the container by remoteEnv ONLY — never
        containerEnv, which is the layer the firewall/postStart step reads, so
        the secret must not be reachable from it;
      - the key never appears in postStartCommand.
    """
    print("\n[gemini] /review slot wiring (task_043)")

    # ── launcher: lookup_token resolves the reserved slash-free key ──────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        save_token "amybo/vibe" "ghp_repo"
        save_token "GEMINI_API_KEY" "AIzaTestKey=="
        echo "GEMINI=$(lookup_token GEMINI_API_KEY)"
        echo "REPO=$(lookup_token amybo/vibe)"
        """
        r = run(["bash", "-c", script], env=env)
        check("[gemini] token helpers run cleanly", r.returncode == 0, r.stderr)
        check("[gemini] key resolves whole (trailing '=' padding kept)",
              "GEMINI=AIzaTestKey==" in r.stdout, r.stdout)
        check("[gemini] repo PAT still resolves (no slash-free collision)",
              "REPO=ghp_repo" in r.stdout, r.stdout)

    # ── launcher exports it at top-level scope (not inside a subshell) ───────
    vibe_text = VIBE.read_text()
    check("[gemini] launcher looks the key up from the tokens file",
          'GEMINI_API_KEY=$(lookup_token "GEMINI_API_KEY")' in vibe_text, "")
    check("[gemini] launcher exports it",
          "\nexport GEMINI_API_KEY\n" in vibe_text, "")

    # ── devcontainer.json: remoteEnv only, never containerEnv ────────────────
    dc = json.loads((REPO / "devcontainer" / "devcontainer.json").read_text())
    check("[gemini] GEMINI_API_KEY is a remoteEnv passthrough",
          dc.get("remoteEnv", {}).get("GEMINI_API_KEY") == "${localEnv:GEMINI_API_KEY}",
          str(dc.get("remoteEnv", {}).get("GEMINI_API_KEY")))
    check("[gemini] GEMINI_API_KEY is NOT in containerEnv (secret layer)",
          "GEMINI_API_KEY" not in dc.get("containerEnv", {}),
          str(list(dc.get("containerEnv", {}))))
    check("[gemini] GEMINI_API_KEY never reaches postStartCommand",
          "GEMINI" not in dc.get("postStartCommand", ""),
          dc.get("postStartCommand", "")[:160])

    # ── the AC4 golden was hand-edited to match (not regenerated) ────────────
    golden = json.loads(TASK034_GOLDEN_DEVCONTAINER_RENDER_OP_OFF)
    check("[gemini] AC4 golden carries the same remoteEnv entry",
          golden.get("remoteEnv", {}).get("GEMINI_API_KEY") == "${localEnv:GEMINI_API_KEY}",
          "golden not updated for the new remoteEnv key")
    check("[gemini] AC4 golden keeps GEMINI_API_KEY out of containerEnv",
          "GEMINI_API_KEY" not in golden.get("containerEnv", {}), "")

    # ── review.md carries a usable, read-only invocation ─────────────────────
    review_text = (REPO / "devcontainer" / "commands" / "review.md").read_text()
    for needle, label in [
        ("generativelanguage.googleapis.com", "API host"),
        (":generateContent", "endpoint verb"),
        ("x-goog-api-key: $GEMINI_API_KEY", "auth header"),
        ("refresh-extra-domains.sh", "stale-edge retry"),
    ]:
        check(f"[gemini] recipe names the {label}", needle in review_text, "")
    check("[gemini] slot is documented as read-only",
          "It never gets a shell, never writes" in review_text, "")

    print("[gemini] all wiring checks completed")


def test_codex_switch_docs() -> None:
    """AC6: Documentation mentions codex=off policy and chmod 700 warning."""
    print("\n[codex] documentation for policy and file mode warning (AC6)")
    
    # AC6: ask.md contains `codex=off` AND `/ask astra` in one sentence with `refus`
    ask_md_path = REPO / "devcontainer" / "commands" / "ask.md"
    check("[codex] ask.md exists", ask_md_path.exists(), "")
    
    if ask_md_path.exists():
        ask_text = ask_md_path.read_text()
        
        # Check that the old sentence about independence is removed
        check("[codex] ask.md removes 'independent of this policy' sentence",
              "independent of this policy" not in ask_text, "")
        
        # Check for codex=off, /ask astra, and refus in connection
        has_codex_off = "codex=off" in ask_text
        has_ask_astra = "/ask astra" in ask_text
        
        check("[codex] ask.md mentions codex=off", has_codex_off, "")
        check("[codex] ask.md mentions /ask astra", has_ask_astra, "")
        
        # Check for a sentence with all three keywords
        import re
        has_combined = re.search(r'codex=off.*refus.*astra|astra.*refus.*codex=off|refus.*codex=off.*astra', ask_text, re.IGNORECASE | re.DOTALL)
        check("[codex] ask.md connects codex=off, refus, and astra",
              has_combined is not None, "")
    
    # AC6: review.md drops "independent of this policy" and mentions the two switches
    review_md_path = REPO / "devcontainer" / "commands" / "review.md"
    check("[codex] review.md exists", review_md_path.exists(), "")
    
    if review_md_path.exists():
        review_text = review_md_path.read_text()
        
        check("[codex] review.md removes 'independent of this policy'",
              "independent of this policy" not in review_text, "")
        
        # Check for OpenAI-egress or OpenAI egress (may be on different lines)
        import re
        has_egress = re.search(r'OpenAI[\s-]*egress.*switch|switch.*OpenAI[\s-]*egress', review_text, re.IGNORECASE | re.DOTALL)
        check("[codex] review.md calls it OpenAI-egress switch",
              has_egress is not None,
              "")
        
        check("[codex] review.md mentions credential-mount switch",
              "mount switch" in review_text or "credential-mount switch" in review_text,
              "")
    
    # AC6: README contains chmod 700 warning and both switch descriptions
    readme_path = REPO / "README.md"
    check("[codex] README.md exists", readme_path.exists(), "")
    
    if readme_path.exists():
        readme_text = readme_path.read_text()
        
        check("[codex] README mentions chmod 700",
              "chmod 700" in readme_text, "")
        
        check("[codex] README mentions egress switch",
              "egress switch" in readme_text, "")
        
        check("[codex] README mentions mount switch",
              "mount switch" in readme_text, "")
    
    # AC6: MANUAL-TESTS.md Test 54 step 8 no longer says "explicitly works"
    # and instead says codex=off refuses
    manual_tests_path = REPO / "MANUAL-TESTS.md"
    check("[codex] MANUAL-TESTS.md exists", manual_tests_path.exists(), "")
    
    if manual_tests_path.exists():
        manual_text = manual_tests_path.read_text()
        
        # Check for Test 54 step 8
        import re
        test_54_match = re.search(r'### Test 54:.*?(?=### Test \d+:|$)', manual_text, re.DOTALL)
        if test_54_match:
            test_54_text = test_54_match.group(0)
            
            # Step 8 should not mention "explicitly /ask astra ... still works"
            check("[codex] Test 54 step 8 removes 'explicitly works' language",
                  "explicitly" not in test_54_text or "/ask astra" not in test_54_text or
                  "still works" not in test_54_text or 
                  not re.search(r'explicitly.*ask astra.*still works|still works.*ask astra.*explicitly', test_54_text),
                  "")
            
            # Step 8 should mention codex=off refuses
            check("[codex] Test 54 step 8 mentions codex=off refuses /ask astra",
                  re.search(r'codex=off.*refus.*astra|astra.*refus.*codex=off', test_54_text, re.IGNORECASE) is not None,
                  "")
        
        # Check for Test 54 step 4: re-confirm real claude -p one-shot behavior
        if test_54_match:
            test_54_text = test_54_match.group(0)
            
            # Step 4 should mention --permission-mode plan and --permission-prompts none
            step_4_match = re.search(r'(?:^|\n).*step 4.*$', test_54_text, re.IGNORECASE | re.MULTILINE)
            if step_4_match:
                # Find text after step 4
                step_4_start = step_4_match.start()
                step_4_text = test_54_text[step_4_start:]
                
                has_plan = "--permission-mode plan" in step_4_text or "permission-mode plan" in step_4_text
                has_none = "--permission-prompts none" in step_4_text or "permission-prompts none" in step_4_text
                
                check("[codex] Test 54 step 4 mentions --permission-mode plan",
                      has_plan, "")
                
                check("[codex] Test 54 step 4 mentions --permission-prompts none",
                      has_none, "")
