from smoke._core import *  # noqa: F401,F403




def test_skipped_marker_unrelated_path_rejected() -> None:
    """is_github_skipped returns false for a path that wasn't marked."""
    print("\n[skipped: unrelated path rejected]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj_a = home / "proj_a"
        proj_b = home / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()
        rc, out, _ = _run_skipped_probe(
            workspace=str(proj_b),
            marker_state=[str(proj_a)],
            home=home,
        )
        check("[skipped] unrelated WORKSPACE returns false",
              "SKIPPED=false" in out, out)


def test_skipped_marker_back_compat_literal() -> None:
    """Pre-existing literal (non-canonical) entries still resolve."""
    print("\n[skipped: back-compat with non-canonical entries]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Marker file has a non-canonical literal (e.g. trailing-slash entry
        # from before this fix). Lookup with the same literal should match.
        literal_with_slash = f"{proj}/"
        rc, out, _ = _run_skipped_probe(
            workspace=literal_with_slash,
            marker_state=[literal_with_slash],
            home=home,
        )
        check("[skipped] literal-with-slash entry still matches its own path",
              "SKIPPED=true" in out, out)


def test_check_numbering_exists_and_executable() -> None:
    """check-numbering.sh exists, is executable, and is a bash script."""
    print("\n[check-numbering: file shape]")
    check("[numbering] script exists", CHECK_NUMBERING.exists(), str(CHECK_NUMBERING))
    if not CHECK_NUMBERING.exists():
        return
    check("[numbering] script is executable",
          os.access(CHECK_NUMBERING, os.X_OK), "")
    head = CHECK_NUMBERING.read_text().splitlines()[0]
    check("[numbering] starts with bash shebang",
          head == "#!/usr/bin/env bash", head)


def test_check_numbering_silent_on_clean() -> None:
    """No warning when reply has only numbered list (1./2./3.)."""
    print("\n[check-numbering: silent on numbered-only]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Three options:\\n1. First\\n2. Second\\n3. Third"}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent on numbered-only", "warning" not in err, err[:200])


def test_check_numbering_silent_on_lettered_only() -> None:
    """No warning when reply has only lettered list (a./b./c.)."""
    print("\n[check-numbering: silent on lettered-only]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Pick one:\\na. cancel\\nb. proceed"}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent on lettered-only", "warning" not in err, err[:200])


def test_check_numbering_warns_on_mixed() -> None:
    """Warning when reply mixes 1./2./3. and a./b./c."""
    print("\n[check-numbering: warns on mixed]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Working list:\\n1. First task\\n2. Second task\\n\\nNext:\\n'
        'a. Do A\\nb. Do B"}]}}\n'
    )
    check("[numbering] exits 0 (non-blocking)", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] stderr contains 'numbering warning'",
          "numbering warning" in err, err[:200])


def test_check_numbering_ignores_code_fences() -> None:
    """Numbering inside ``` blocks does not trigger the warning."""
    print("\n[check-numbering: ignores code fences]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Sample:\\n```\\n1. step\\na. label\\n```\\nNo lists outside fence."}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent when only fenced numbering",
          "warning" not in err, err[:200])


def test_check_numbering_handles_missing_transcript() -> None:
    """Hook tolerates empty stdin / missing transcript / unreadable file."""
    print("\n[check-numbering: edge cases]")
    if not CHECK_NUMBERING.exists():
        return
    for label, payload in (
        ("empty stdin", ""),
        ("no transcript_path", '{"foo":"bar"}'),
        ("unreadable transcript", '{"transcript_path":"/no/such/file.jsonl"}'),
    ):
        r = subprocess.run(
            ["bash", str(CHECK_NUMBERING)],
            input=payload, capture_output=True, text=True,
        )
        check(f"[numbering] {label}: exit 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check(f"[numbering] {label}: silent",
              r.stderr.strip() == "", r.stderr[:200])


def test_numbering_hook_readme_present() -> None:
    """devcontainer/hooks/README.md explains the hook + opt-in wiring."""
    print("\n[check-numbering: hooks/README.md]")
    check("[numbering] hooks/README.md exists",
          NUMBERING_HOOK_README.exists(), str(NUMBERING_HOOK_README))
    if not NUMBERING_HOOK_README.exists():
        return
    content = NUMBERING_HOOK_README.read_text()
    check("[numbering] readme names hook script path",
          "/home/node/.claude/hooks/check-numbering.sh" in content, "")
    check("[numbering] readme explains working-list/action-pick split",
          "working list" in content and "action pick" in content, "")


def test_copy_last_block_exists_and_executable() -> None:
    print("\n[copy-last-block: file shape]")
    check("[copy-block] script exists",
          COPY_LAST_BLOCK.exists(), str(COPY_LAST_BLOCK))
    if not COPY_LAST_BLOCK.exists():
        return
    check("[copy-block] script is executable",
          os.access(COPY_LAST_BLOCK, os.X_OK), "")
    head = COPY_LAST_BLOCK.read_text().splitlines()[0]
    check("[copy-block] starts with bash shebang",
          head == "#!/usr/bin/env bash", head)


def test_copy_last_block_single_block() -> None:
    """Marker + single fenced block → block content written, fence stripped."""
    print("\n[copy-last-block: single block]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nResult:\n```\necho hello\n```",
            cd,
        )
        check("[copy-block] single: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] single: file content matches",
              out == "echo hello", repr(out))


def test_copy_last_block_language_tag() -> None:
    """Marker + fence with language tag → tag dropped, only content written."""
    print("\n[copy-last-block: language-tagged fence]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\n```bash\necho hi\n```",
            cd,
        )
        check("[copy-block] langtag: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] langtag: language line dropped",
              out == "echo hi", repr(out))


def test_copy_last_block_multiple_blocks_last_wins() -> None:
    """Marker + multiple blocks → LAST one is written."""
    print("\n[copy-last-block: multiple blocks, last wins]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nfirst:\n```\nblock A\n```\nsecond:\n```\nblock B\n```",
            cd,
        )
        check("[copy-block] multi: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] multi: last block wins (B not A)",
              out == "block B", repr(out))


def test_copy_last_block_no_fence_no_write() -> None:
    """Marker but no fenced blocks → no file written."""
    print("\n[copy-last-block: no fence, no write]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nJust plain text, no code samples here.",
            cd,
        )
        check("[copy-block] nofence: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] nofence: file NOT written",
              out == "<NO_FILE>", repr(out))


def test_copy_last_block_no_marker_silent() -> None:
    """Default is opt-in: without `<!-- vibe: copy -->`, no write even with a block."""
    print("\n[copy-last-block: no marker = silent]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "Result:\n```\nshould-not-be-copied\n```",
            cd,
        )
        check("[copy-block] no-marker: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] no-marker: file NOT written without sentinel",
              out == "<NO_FILE>", repr(out))


def test_copy_last_block_multiline_preserved() -> None:
    """Marker + multi-line block → interior newlines preserved."""
    print("\n[copy-last-block: multi-line preservation]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\n```\nline 1\nline 2\nline 3\n```",
            cd,
        )
        check("[copy-block] multiline: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] multiline: interior newlines preserved",
              out == "line 1\nline 2\nline 3", repr(out))


def test_copy_last_block_empty_stdin() -> None:
    """Empty stdin / no transcript → silent exit 0, no write."""
    print("\n[copy-last-block: empty stdin]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        env = {**os.environ, "VIBE_CLIP_DIR": str(cd)}
        r = subprocess.run(
            ["bash", str(COPY_LAST_BLOCK)],
            input="", capture_output=True, text=True, env=env,
        )
        check("[copy-block] empty stdin: exit 0", r.returncode == 0,
              f"rc={r.returncode}")
        clip_file = cd / "copy-latest.txt"
        check("[copy-block] empty stdin: no file",
              not clip_file.exists(), str(clip_file))


def test_vss_md_exists_with_frontmatter() -> None:
    """vss.md has frontmatter and the required structure markers."""
    print("\n[/vss: file shape]")
    check("[vss] vss.md exists", VSS_MD.exists(), str(VSS_MD))
    if not VSS_MD.exists():
        return
    content = VSS_MD.read_text()
    check("[vss] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[vss] description: in frontmatter",
          "description:" in content.split("---\n")[1] if "---\n" in content else False, "")
    check("[vss] declares Mode A header", "## Mode A" in content, "")
    check("[vss] declares Mode B header", "## Mode B" in content, "")
    check("[vss] cites 270s redirect window", "270" in content, "")
    check("[vss] mentions terminal bell", "printf" in content and "\\\\a" in content, "")
    check("[vss] announce includes skip-the-wait instruction",
          "skip the 270s wait" in content or "skip the wait" in content, "")
    check("[vss] documents approval-phrase recognition (go/y/yes/...)",
          "`go`" in content and ("`y`" in content or "yes" in content), "")
    check("[vss] documents redirect branch",
          "redirect" in content.lower() and ("any other" in content or "anything ELSE" in content or "anything else" in content), "")
    check("[vss] documents cancel branch",
          ("`n`" in content or "no`" in content) and ("cancel" in content.lower() or "abort" in content.lower()), "")
    check("[vss] outcome labels named in session file rules",
          "auto-proceeded" in content and "user-approved-immediately" in content, "")


def test_vss_md_hard_escalate_sentinels() -> None:
    """vss.md preserves the canonical hard-escalate list. These are
    safety boundaries; a regression silently dropping a sentinel is the
    failure this test exists to catch."""
    print("\n[/vss: hard-escalate sentinels]")
    if not VSS_MD.exists():
        check("[vss-escalate] vss.md exists", False, "missing")
        return
    content = VSS_MD.read_text()
    sentinels = [
        ("physical hardware actuation", "Physical hardware actuation"),
        ("SSH-out idiom", "SSH-out"),
        ("Pioreactor named in actuation context", "Pioreactor"),
        ("/vs --fuzzy subjective verdict", "fuzzy"),
        ("force-push named", "Force-push" in content or "force-push" in content),
        ("hook bypass --no-verify", "--no-verify"),
        ("/learnings writes", "/learnings"),
        ("firewall/hook/settings scope", "firewall" in content.lower()),
        ("scope creep", "Scope creep" in content or "scope creep" in content),
    ]
    for label, pattern in sentinels:
        if isinstance(pattern, bool):
            check(f"[vss-escalate] {label}", pattern, "")
        else:
            check(f"[vss-escalate] {label}", pattern in content, f"missing: {pattern!r}")


def test_vsss_md_inherits_escalate_and_budget() -> None:
    """vsss.md inherits /vss's escalate list, repeats its own safety floor,
    and pins BUDGET_HOURS=5 (full Pro/Max session, no graceful-shutdown
    cushion). A flip back to 4h would be a regression."""
    print("\n[/vsss: inherited escalate + budget]")
    check("[vsss] vsss.md exists", VSSS_MD.exists(), str(VSSS_MD))
    if not VSSS_MD.exists():
        return
    content = VSSS_MD.read_text()
    check("[vsss] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[vsss] inherits /vss escalate list",
          "Inherited verbatim from `/vss`" in content, "")
    check("[vsss] BUDGET_HOURS=5 default", "BUDGET_HOURS=5" in content, "")
    check("[vsss] no stale 4h default",
          "BUDGET_HOURS=4" not in content,
          "found 4h default — should be 5h since 2026-05-07")
    check("[vsss] safety floor section present",
          "/vsss safety floor" in content, "")
    floor_sentinels = [
        ("physical hardware", "Actuate physical hardware"),
        ("SSH-out", "SSH out"),
        ("force-push", "Force-push"),
        ("hook disable", "--no-verify"),
        ("/learnings", "/learnings"),
        ("--fuzzy auto-pass refusal", "fuzzy"),
    ]
    for label, pattern in floor_sentinels:
        check(f"[vsss-floor] {label}", pattern in content, f"missing: {pattern!r}")
    check("[vsss] points at .vss/sessions/ audit trail",
          ".vss/sessions/" in content, "")
    check("[vsss] --hours N flag canonical",
          "--hours N" in content or "--hours `N`" in content, "")
    check("[vsss] --budget Nh alias preserved",
          "--budget Nh" in content, "")
    check("[vsss] --budget Nm minutes form",
          "--budget Nm" in content, "")
    check("[vsss] § Resumption protocol header",
          "## Resumption protocol" in content, "")
    check("[vsss] resumption detects in-progress session",
          "in-progress session" in content, "")
    check("[vsss] --resume flag named",
          "`/vsss --resume`" in content, "")
    check("[vsss] resume budget arithmetic documented",
          "Resume budget arithmetic" in content or "Resumption budget" in content or "remaining budget" in content.lower(), "")
    check("[vsss] --sessions flag + launcher integration documented",
          "--sessions X" in content and "Launcher side" in content, "")
    check("[vsss] --sessions semantics are total windows (X-1 relaunches)",
          "X-1" in content, "")
    check("[vsss] auto-resume marker cleared on clean exit",
          "active=0" in content, "")
    check("[vsss] auto-resume marker file path named",
          ".vss/auto-resume" in content, "")
    check("[vsss] no stale .vss/loop.md references",
          ".vss/loop.md" not in content,
          "found .vss/loop.md - per-session audit replaced loop.md 2026-05-07")
    check("[vsss] three-no-op exit condition",
          "Three consecutive A-mode" in content or "three consecutive A-mode" in content, "")
    check("[vsss] inherits no-autonomous-push rule",
          "git push" in content.lower() and ("push-on-pass" in content or "Push policy" in content), "")


def test_vsss_persist_until_complete() -> None:
    """Persist-until-complete default (2026-08-29, prompted by a run that
    exited 1h25 early on a time-fit ruling laundered through the perfection
    gate). Pins the invariants so the spec can't drift back: time is not an
    optimiser input, the chair voids time-justified stop verdicts, every run
    except --sessions 1 writes the marker (remaining=9999 unbounded
    sentinel), exit condition 3 is explicit-flag-only, exit reports must name
    the condition that actually fired, and the launcher's countdown carries
    the freshness gate that stops crash-left markers ambushing later plain
    launches."""
    print("\n[/vsss: persist-until-complete invariants]")
    content = VSSS_MD.read_text()
    check("[vsss-persist] time-is-not-an-input rule in optimiser prompt",
          "Time is not an input" in content, "")
    check("[vsss-persist] chair voids time-justified stop verdicts",
          "wall-clock, window-fit" in content and "treat it as verdict 2" in content, "")
    check("[vsss-persist] no stop-bias cushion clause",
          "bias toward \"stop the loop\" (perfection gate)" not in content,
          "old cushion clause is back — it caused the 1h25-early stop")
    check("[vsss-persist] remaining time never a reason to stop",
          "Remaining time is never a reason to stop" in content, "")
    check("[vsss-persist] 9999 unbounded sentinel documented",
          "9999" in content and "unbounded" in content, "")
    check("[vsss-persist] marker written unless --sessions 1",
          "With `--sessions 1` only, never write the marker" in content, "")
    check("[vsss-persist] exit condition 3 explicit-flag-only",
          "explicit flag only" in content, "")
    check("[vsss-persist] default 5h is not an exit condition",
          "NOT an exit condition" in content, "")
    check("[vsss-persist] exit-report honesty rule",
          "must never be reported as a perfection gate" in content
          or "never be reported as a perfection gate" in content, "")
    check("[vsss-persist] resume path never escalates on default clock",
          "Never compute a \"negative budget\"" in content, "")
    check("[vsss-persist] remaining is launcher-owned (refresh preserves it)",
          "LAUNCHER-OWNED" in content and "never re-derive" in content, "")
    check("[vsss-persist] resume_at re-based on resumed windows",
          "re-bases it from the resumption timestamp" in content, "")
    check("[vsss-persist] spent marker end-state documented",
          "Spent marker" in content and "overwrites it wholesale" in content, "")
    vibe_src = (REPO / "vibe").read_text()
    check("[vsss-persist] launcher countdown freshness-gated",
          "_vibe_stall_armed \"$AUTO_RESUME_MARKER\" \"$VIBE_SESSION_REF\"" in vibe_src, "")
    check("[vsss-persist] launcher stale-marker hint",
          "stale /vsss marker" in vibe_src, "")
    manual = (REPO / "MANUAL-TESTS.md").read_text()
    check("[vsss-persist] MANUAL-TESTS pins marker write-timing",
          "Marker write-timing matters" in manual and "AFTER the" in manual,
          "Test 32 must teach the freshness gate or fixtures regress")
    banner_at = vibe_src.find("relaunch(es) left")
    decrement_at = vibe_src.find('auto_resume_decrement "$AUTO_RESUME_MARKER"')
    check("[vsss-persist] countdown banner prints pre-decrement remaining",
          0 <= banner_at < decrement_at,
          "banner echo must precede the decrement call — 32i's expected "
          "values (9999 then 9998) depend on it")
    check("[vsss-persist] MANUAL-TESTS 32i documents pre-decrement banner",
          "PRE-decrement" in manual, "")
    check("[vsss-persist] countdown grace knob defaults to 120 in launcher",
          "VIBE_RESUME_PAST_GRACE_SECS:-120" in vibe_src, "")
    check("[vsss-persist] MANUAL-TESTS 32 names the countdown grace knob",
          "VIBE_RESUME_PAST_GRACE_SECS" in manual,
          "Test 32's timing claims depend on the countdown floor being "
          "overridable — the preamble must say so")


def test_vsss_fromto_format() -> None:
    """Task 029: fromto format — minimal fromClaude template, brain2 override,
    exit-append rule removed. AC1–AC7 and AC12 assertions against vsss.md."""
    print("\n[/vsss: fromto format]")
    check("[fromto] vsss.md exists", VSSS_MD.exists(), str(VSSS_MD))
    if not VSSS_MD.exists():
        return
    content = VSSS_MD.read_text()

    # AC1: heading present and positioned correctly
    three_files_idx = content.find("### The three files")
    fromto_heading_idx = content.find("### fromto format")
    question_format_idx = content.find("### Question format (fromClaude)")

    check("[fromto] AC1: '### fromto format' heading exists",
          fromto_heading_idx >= 0, "")
    check("[fromto] AC1: fromto heading after '### The three files'",
          three_files_idx >= 0 and fromto_heading_idx > three_files_idx,
          f"three_files={three_files_idx}, fromto={fromto_heading_idx}")
    check("[fromto] AC1: fromto heading before '### Question format'",
          question_format_idx >= 0 and fromto_heading_idx < question_format_idx,
          f"fromto={fromto_heading_idx}, question_format={question_format_idx}")

    # Extract fromto format section (from heading to next ### heading)
    next_heading_idx = content.find("###", fromto_heading_idx + 10)
    if next_heading_idx < 0:
        next_heading_idx = len(content)
    fromto_section = content[fromto_heading_idx:next_heading_idx]

    # AC2: nine-line template appears verbatim
    template_lines = [
        "---",
        "state: authored",
        "author: Claude (<harness>, <repo>)",
        "created: <ISO date>",
        "cssclasses: [trust-authored]",
        "---",
        "Reply in [[<project>-from<User>]]. History: [[<project>-Q&A-archive]].",
        "",
        "1. <action point: a question to answer, or a test to run> (T<n>)",
    ]
    template_text = "\n".join(template_lines)
    check("[fromto] AC2: nine-line template appears verbatim",
          template_text in fromto_section,
          "Template not found as contiguous block")

    # AC3: literal strings in fromto format section (account for line breaks)
    ac3_checks = [
        ("one ordered list and nothing else", "one ordered list and nothing else"),
        ("no session report", "no session report"),
        ("Information appears only", "Information appears only"),
        ("action points only", "action points only"),
        ("contiguous", "contiguous"),
        ("from 1", "from 1"),
    ]
    for label, pattern in ac3_checks:
        check(f"[fromto] AC3: '{label}' in fromto section",
              pattern in fromto_section, f"missing: {pattern!r}")

    # AC4: exit-line sentinel and "exactly one line"
    # Check for the key parts of the sentinel (account for line breaks)
    check("[fromto] AC4: 'Exit appends exactly one line:' present",
          "Exit appends exactly one line:" in fromto_section, "")
    check("[fromto] AC4: 'Session log:' present",
          "Session log:" in fromto_section, "")
    check("[fromto] AC4: '.vss/sessions/<start-ISO>.md' present",
          ".vss/sessions/<start-ISO>.md" in fromto_section, "")
    check("[fromto] AC4: '<N> commits, <pushed|not pushed>' present",
          "<N> commits, <pushed|not pushed>" in fromto_section, "")

    # AC5: brain2 override note and credential boundary
    check("[fromto] AC5: '/brain2/meta/fromto-format.md' mentioned",
          "/brain2/meta/fromto-format.md" in fromto_section, "")
    check("[fromto] AC5: 'overrides this default' present",
          "overrides this default" in fromto_section, "")
    check("[fromto] AC5: 'verbatim' present",
          "verbatim" in fromto_section, "")
    check("[fromto] AC5: 'write-files-only' present",
          "write-files-only" in fromto_section, "")
    check("[fromto] AC5: \"never `git` against\" present",
          "never `git` against" in fromto_section, "")
    check("[fromto] AC5: 'read-only' NOT in fromto section",
          "read-only" not in fromto_section,
          "found 'read-only' in fromto section — should use 'write-files-only' instead")

    # AC6: deletions and structural guards
    check("[fromto] AC6: '### At exit' NOT in file",
          "### At exit" not in content,
          "Old '### At exit' section should be deleted")
    check("[fromto] AC6: 'Append the exit report' NOT in file",
          "Append the exit report (same content as § Reporting back at exit)" not in content,
          "Old exit-append mandate should be deleted")
    check("[fromto] AC6: 'If fromto channels are active' NOT in file",
          "If fromto channels are active" not in content,
          "Old conditional should be deleted")

    # AC6: structural guard (a) — no fromClaude/from<User> in Reporting section
    reporting_idx = content.find("## Reporting back at exit")
    if reporting_idx >= 0:
        reporting_section = content[reporting_idx:]
        check("[fromto] AC6: no 'fromClaude' in Reporting section",
              "fromClaude" not in reporting_section, "")
        check("[fromto] AC6: no 'from<User>' in Reporting section",
              "from<User>" not in reporting_section, "")

    # AC6: structural guard (b) — regex check for (append|mirror|copy).{0,60}(report|outcome).{0,60}fromClaude
    pattern = re.compile(r"(append|mirror|copy).{0,60}(report|outcome).{0,60}fromClaude", re.I)
    outside_fromto = content[:fromto_heading_idx] + content[next_heading_idx:]
    outside_matches = len(pattern.findall(outside_fromto))
    check("[fromto] AC6: no append/mirror/copy...report/outcome...fromClaude outside fromto section",
          outside_matches == 0,
          f"found {outside_matches} matches outside fromto section")
    inside_matches = len(pattern.findall(fromto_section))
    check("[fromto] AC6: at most 1 match of pattern inside fromto section",
          inside_matches <= 1,
          f"found {inside_matches} matches (expect ≤1, the exit-line rule of AC4)")

    # AC6: stable invariants replace cycle-time gate pins removed in task_028
    # The frozen-baseline fromClaude count pin (expected_max) and word-count pin (+120)
    # fail on any legitimate edit to vsss.md, exactly the cycle-time gate the chair removed.
    # Stable invariants: (a) no fromClaude/from<User> in Reporting section (checked above),
    # (b) no exit-append regex outside fromto section (checked above).

    # AC7: preserved sections still exist and in correct order
    required_strings = [
        "## Reporting back at exit",
        "Total iterations run.",
        "Lead with `---` before the report block.",
        "### Question format (fromClaude)",
        "questions and blocking",
        "asks only",
        "no progress notes, no FYIs",
    ]
    for s in required_strings:
        check(f"[fromto] AC7: '{s}' preserved",
              s in content, f"missing: {s!r}")

    # AC7: heading order check
    headings_to_check = [
        ("### The three files", "The three files"),
        ("### fromto format", "fromto format"),
        ("### Question format (fromClaude)", "Question format"),
        ("### Answer format (from<User>)", "Answer format"),
        ("### Consume protocol", "Consume protocol"),
        ("### Precedence", "Precedence"),
        ("### Interaction with the loop", "Interaction with the loop"),
        ("### After each /vss completes", "After each /vss completes"),
    ]
    indices = {}
    for heading, label in headings_to_check:
        idx = content.find(heading)
        indices[label] = idx
        if idx < 0:
            check(f"[fromto] AC7: heading '{label}' exists", False, f"missing: {heading!r}")

    # Verify order
    last_idx = -1
    for _, label in headings_to_check:
        idx = indices.get(label, -1)
        if idx >= 0:
            check(f"[fromto] AC7: '{label}' after previous heading",
                  idx > last_idx, f"idx={idx}, last={last_idx}")
            last_idx = idx

    # AC12: word count invariant — vs.md+vss.md+vsss.md ≤13500 checked in test_wide_mode()

    # AC8: brain2 file check (only if it exists)
    brain2_file = Path("/brain2/meta/fromto-format.md")
    if brain2_file.exists():
        brain2_content = brain2_file.read_text()

        # Check frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---", brain2_content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            check("[fromto] AC8: brain2 frontmatter has 'state: authored'",
                  "state: authored" in frontmatter, "")
            check("[fromto] AC8: brain2 frontmatter has 'authorised:' with empty value",
                  "authorised:" in frontmatter and re.search(r"authorised:\s*$", frontmatter, re.M),
                  "")
            check("[fromto] AC8: brain2 frontmatter has 'created: 2026-09-02'",
                  "created: 2026-09-02" in frontmatter, "")
            check("[fromto] AC8: brain2 frontmatter has 'cssclasses: [trust-authored]'",
                  "cssclasses: [trust-authored]" in frontmatter, "")
            check("[fromto] AC8: brain2 frontmatter has 'vibe' tag",
                  "vibe" in frontmatter and "tags:" in frontmatter, "")
            check("[fromto] AC8: brain2 frontmatter has 'fromto' tag",
                  "fromto" in frontmatter, "")

        # Check body contains template (normalize whitespace)
        normalized_brain2_body = re.sub(r'\s+', ' ', brain2_content)
        normalized_template = re.sub(r'\s+', ' ', template_text)
        check("[fromto] AC8: brain2 body contains template (normalized)",
              normalized_template in normalized_brain2_body, "")

        # Check for "every project" phrase (accounting for line breaks)
        # Normalize whitespace for this check
        normalized_brain2 = re.sub(r'\s+', ' ', brain2_content)
        check("[fromto] AC8: brain2 body contains 'every project'",
              "every project" in normalized_brain2, "")
    else:
        print("  [skip] AC8: /brain2/meta/fromto-format.md not found (brain2 is per-machine mount)")


def test_wide_mode() -> None:
    """Task 033: /wide and /narrow parallelism mode. AC1–AC11, AC13, AC14 sentinels."""
    print("\n[/wide and /narrow: parallelism mode]")

    # AC1: wide.md and narrow.md exist with description
    check("[wide] AC1: wide.md exists", WIDE_MD.exists(), str(WIDE_MD))
    check("[wide] AC1: narrow.md exists", NARROW_MD.exists(), str(NARROW_MD))

    if WIDE_MD.exists():
        wide_content = WIDE_MD.read_text()
        check("[wide] AC1: wide.md has description in frontmatter",
              "description:" in wide_content, "")
        check("[wide] AC1: wide.md mentions /narrow", "/narrow" in wide_content, "")

    if NARROW_MD.exists():
        narrow_content = NARROW_MD.read_text()
        check("[wide] AC1: narrow.md has description in frontmatter",
              "description:" in narrow_content, "")
        check("[wide] AC1: narrow.md mentions /wide", "/wide" in narrow_content, "")
        check("[wide] AC1: narrow.md states strictly serial dispatch",
              "strictly serial" in narrow_content, "")

    # AC2: wide.md contains concurrency caps with specific literals
    if WIDE_MD.exists():
        check("[wide] AC2: '6 default, 8 ceiling' present",
              "6 default, 8 ceiling" in wide_content, "")
        check("[wide] AC2: 'max 2 concurrent' heavy verifications present",
              "max 2 concurrent" in wide_content, "")
        check("[wide] AC2: '10-minute Bash cap' present",
              "10-minute Bash cap" in wide_content, "")
        check("[wide] AC2: 'single-writer-per-file' present",
              "single-writer-per-file" in wide_content, "")
        check("[wide] AC2: 'max 1 concurrent Fable dispatch' present",
              "max 1 concurrent Fable dispatch" in wide_content, "")
        check("[wide] AC2: 'never widens the grant' present",
              "never widens the grant" in wide_content, "")

    # AC3: stacking table with specific rows
    if WIDE_MD.exists():
        check("[wide] AC3: 'mandatory roles only' present",
              "mandatory roles only" in wide_content, "")
        check("[wide] AC3: 'Heavy-verify cap 1' present",
              "Heavy-verify cap 1" in wide_content, "")
        check("[wide] AC3: '--panel 3' present",
              "--panel 3" in wide_content, "")
        check("[wide] AC3: '8 agents' present",
              "8 agents" in wide_content, "")
        check("[wide] AC3: 'strictly serial' present",
              "strictly serial" in wide_content, "")

    # AC4: what may overlap and must stay serial
    if WIDE_MD.exists():
        check("[wide] AC4: 'Tester ∥ panel' present",
              "Tester ∥ panel" in wide_content, "")
        check("[wide] AC4: 'Evaluator pre-reads' present",
              "Evaluator pre-reads" in wide_content, "")
        check("[wide] AC4: \"next queue item's Planner + Spec Critic\" present",
              "next queue item's Planner + Spec Critic" in wide_content, "")
        check("[wide] AC4: 'Spec Critic iterations' present",
              "Spec Critic iterations" in wide_content, "")
        check("[wide] AC4: 'Generator → Tester of the same cycle' present",
              "Generator → Tester of the same cycle" in wide_content, "")
        check("[wide] AC4: 'subagents run long commands in the foreground' present",
              "subagents run long commands in the foreground" in wide_content, "")
        check("[wide] AC4: 'never run_in_background' present",
              "never run_in_background" in wide_content, "")

    # AC5: chair discipline
    if WIDE_MD.exists():
        check("[wide] AC5: 'one notification per completion' present",
              "one notification per completion" in wide_content, "")
        check("[wide] AC5: 'never poll' present",
              "never poll" in wide_content, "")

    # AC6: vs.md updated
    if VS_MD.exists():
        vs_content = VS_MD.read_text()
        check("[wide] AC6: vs.md mentions '/vs --wide'",
              "/vs --wide" in vs_content, "")
        check("[wide] AC6: vs.md mentions '--narrow'",
              "--narrow" in vs_content, "")
        check("[wide] AC6: vs.md 'propagates into wrapped invocations'",
              "propagates into wrapped invocations" in vs_content, "")
        check("[wide] AC6: vs.md references 'wide.md'",
              "wide.md" in vs_content, "")
        check("[wide] AC6: vs.md 'max 1 concurrent Fable dispatch'",
              "max 1 concurrent Fable dispatch" in vs_content, "")

    # AC7: vss.md updated
    if VSS_MD.exists():
        vss_content = VSS_MD.read_text()
        check("[wide] AC7: vss.md '--wide' passthrough documented",
              "--wide" in vss_content, "")
        check("[wide] AC7: vss.md 'five concurrent read-only' Explore agents",
              "five concurrent read-only" in vss_content, "")
        check("[wide] AC7: vss.md '270' seconds redirect window preserved",
              "270" in vss_content, "")

    # AC8: vsss.md Parallel plan documented
    if VSSS_MD.exists():
        vsss_content = VSSS_MD.read_text()
        check("[wide] AC8: vsss.md 'Parallel plan' block documented",
              "## Parallel plan" in vsss_content, "")
        check("[wide] AC8: vsss.md 'files:' key present",
              "files:" in vsss_content, "")
        check("[wide] AC8: vsss.md 'depends-on:' key present",
              "depends-on:" in vsss_content, "")
        check("[wide] AC8: vsss.md 'worktree:' key present",
              "worktree:" in vsss_content, "")
        check("[wide] AC8: vsss.md 'owner-model:' key present",
              "owner-model:" in vsss_content, "")
        check("[wide] AC8: vsss.md 'Merge order:' present",
              "Merge order:" in vsss_content, "")
        check("[wide] AC8: vsss.md 'Serial because:' present",
              "Serial because:" in vsss_content, "")
        check("[wide] AC8: vsss.md worktree convention documented",
              ".claude/worktrees/<task-id>" in vsss_content, "")
        check("[wide] AC8: vsss.md branch convention documented",
              "vsss/<task-id>-<slug>" in vsss_content, "")
        check("[wide] AC8: vsss.md 'worktree tasks never touch CHANGELOG.md or TODO.md'",
              "worktree tasks never touch CHANGELOG.md or TODO.md" in vsss_content, "")

    # AC9: merge step order
    if VSSS_MD.exists():
        check("[wide] AC9: vsss.md merge sequence 'rebase'",
              "rebase" in vsss_content, "")
        check("[wide] AC9: vsss.md merge sequence 'full suite once'",
              "full suite once" in vsss_content, "")
        check("[wide] AC9: vsss.md merge sequence '--ff-only'",
              "--ff-only" in vsss_content, "")

    # AC10: fromto channels dependency analysis
    if VSSS_MD.exists():
        check("[wide] AC10: vsss.md fromto channels 'never guess'",
              "never guess" in vsss_content, "")
        check("[wide] AC10: vsss.md 'fromClaude question in the minimal template'",
              "fromClaude question in the minimal template" in vsss_content, "")

    # AC11: README.md and CLAUDE.md mention /wide and /narrow
    if README_MD.exists():
        readme_content = README_MD.read_text()
        check("[wide] AC11: README.md mentions '/wide'",
              "/wide" in readme_content, "")
        check("[wide] AC11: README.md mentions '/narrow'",
              "/narrow" in readme_content, "")

    claude_md_path = REPO / "CLAUDE.md"
    if claude_md_path.exists():
        claude_content = claude_md_path.read_text()
        check("[wide] AC11: CLAUDE.md shipped extras list includes '/wide'",
              "/wide" in claude_content, "")
        check("[wide] AC11: CLAUDE.md shipped extras list includes '/narrow'",
              "/narrow" in claude_content, "")

    # AC11: MANUAL-TESTS.md Test 24
    if MANUAL_TESTS_MD.exists():
        manual_content = MANUAL_TESTS_MD.read_text()
        check("[wide] AC11: MANUAL-TESTS.md Test 24 includes 'wide.md'",
              "wide.md" in manual_content, "")
        check("[wide] AC11: MANUAL-TESTS.md Test 24 includes 'narrow.md'",
              "narrow.md" in manual_content, "")

    # AC13: diet.md gains /wide precedence sentence
    if DIET_MD.exists():
        diet_content = DIET_MD.read_text()
        check("[wide] AC13: diet.md mentions '/wide'",
              "/wide" in diet_content, "")
        check("[wide] AC13: diet.md mentions 'mandatory'",
              "mandatory" in diet_content, "")

    # AC13: feast.md names /wide
    if FEAST_MD.exists():
        feast_content = FEAST_MD.read_text()
        check("[wide] AC13: feast.md mentions '/wide'",
              "/wide" in feast_content, "")

    # AC14: wide.md within-cycle rule
    if WIDE_MD.exists():
        check("[wide] AC14: wide.md 'within-cycle' present",
              "within-cycle" in wide_content, "")

    # AC14: vsss.md diagram shows parallel items
    if VSSS_MD.exists():
        check("[wide] AC14: vsss.md shows '∥' or 'in parallel' for concurrent items",
              "∥" in vsss_content or "in parallel" in vsss_content, "")

    # AC12 word budget: vs.md + vss.md + vsss.md ≤ 13,500 words
    if VS_MD.exists() and VSS_MD.exists() and VSSS_MD.exists():
        vs_content_full = VS_MD.read_text()
        vss_content_full = VSS_MD.read_text()
        vsss_content_full = VSSS_MD.read_text()
        vs_words = len(vs_content_full.split())
        vss_words = len(vss_content_full.split())
        vsss_words = len(vsss_content_full.split())
        total_words = vs_words + vss_words + vsss_words
        check("[wide] AC12: combined vs+vss+vsss word count ≤ 13,500",
              total_words <= 13500,
              f"vs={vs_words}, vss={vss_words}, vsss={vsss_words}, total={total_words}")


def test_todo_changelog_split() -> None:
    """TODO/CHANGELOG split adopted 2026-05-08 after AEP-Plugin PR #16
    review. CLAUDE.md must instruct: open work in TODO.md, done in
    CHANGELOG.md, abandoned items stay in TODO ## Open with [!] marker.
    A cross-project fragment ships the convention to all vibe projects."""
    print("\n[TODO/CHANGELOG split convention]")
    claude_md = REPO / "CLAUDE.md"
    if claude_md.exists():
        c = claude_md.read_text()
        check("[todo-cl] CLAUDE.md names TODO.md and CHANGELOG.md split",
              "TODO.md and CHANGELOG.md" in c, "")
        check("[todo-cl] CLAUDE.md says don't put done in TODO",
              "Don't put done items in TODO" in c or "don't put done items in TODO" in c.lower(), "")
        check("[todo-cl] CLAUDE.md retains [!] for abandoned in Open",
              "[!]" in c and "Abandoned" in c, "")
        # Note: CLAUDE.md may still mention `TODO.md ## Done` as a "no longer
        # exists" historical pointer; that's intended. Don't grep for # ## Done
        # absent. The "Don't put done items in TODO" check above is the
        # forward-looking guard.
    check("[todo-cl] CHANGELOG.md exists",
          CHANGELOG_MD.exists(), str(CHANGELOG_MD))
    if CHANGELOG_MD.exists():
        cl = CHANGELOG_MD.read_text()
        check("[todo-cl] CHANGELOG.md has header",
              cl.startswith("# CHANGELOG"), "")
        check("[todo-cl] CHANGELOG.md is non-trivial (migrated entries)",
              len(cl) > 500, f"size={len(cl)}")
    check("[todo-cl] cross-project fragment ships",
          TODO_CHANGELOG_MD.exists(), str(TODO_CHANGELOG_MD))
    if TODO_CHANGELOG_MD.exists():
        f = TODO_CHANGELOG_MD.read_text()
        check("[todo-cl-frag] explains TODO is open + abandoned",
              "open backlog" in f.lower() and "abandoned" in f.lower(), "")
        check("[todo-cl-frag] explains CHANGELOG is reader-facing",
              "Reader-facing" in f or "reader-facing" in f.lower(), "")
        check("[todo-cl-frag] cites the AEP-Plugin trigger",
              "Pioreactor" in f or "PR" in f, "")
    todo = REPO / "TODO.md"
    if todo.exists():
        t = todo.read_text()
        check("[todo-cl] TODO.md no longer has ## Done section",
              "## Done" not in t, "stale ## Done section in TODO.md")


def test_project_hygiene_fragment() -> None:
    """devcontainer/claude-md/project-hygiene.md ships the cross-project
    rule learned from AEP-Plugin PR #16: don't commit per-machine runtime
    cruft, setup-specific notes, or unconsented system-patching scripts in
    upstream-bound repos."""
    print("\n[project-hygiene fragment]")
    check("[hygiene] fragment exists",
          PROJECT_HYGIENE_MD.exists(), str(PROJECT_HYGIENE_MD))
    if not PROJECT_HYGIENE_MD.exists():
        return
    f = PROJECT_HYGIENE_MD.read_text()
    check("[hygiene] flags .claude/settings.local.json",
          ".claude/settings.local.json" in f, "")
    check("[hygiene] flags .vibe/ runtime dir",
          ".vibe/" in f, "")
    check("[hygiene] flags hardcoded local IPs",
          "192.168" in f and "IP" in f, "")
    check("[hygiene] flags hostname/.local pattern",
          ".local" in f, "")
    check("[hygiene] consent rule for system-patching scripts",
          "without consent" in f.lower() or "consent flow" in f.lower(), "")
    check("[hygiene] cites the PR review trigger (AEP-Plugin)",
          "AEP-Plugin" in f or "electroPioreactor" in f.lower() or "PR #16" in f, "")
    check("[hygiene] pre-commit checklist present",
          "Pre-commit checklist" in f or "pre-commit checklist" in f.lower(), "")


def test_install_extras_ensures_project_gitignore() -> None:
    """install-claude-extras.sh adds a managed block to /workspace/.gitignore
    that excludes vibe's runtime files. Idempotent on re-run; opt-out via
    VIBE_AUTO_GITIGNORE=0; respects user-removed-block (no re-add)."""
    print("\n[install-extras: ensure_project_gitignore]")
    src = INSTALL_EXTRAS.read_text()
    check("[gi-fn] function defined",
          "ensure_project_gitignore()" in src, "")
    check("[gi-fn] honours VIBE_AUTO_GITIGNORE=0 opt-out",
          "VIBE_AUTO_GITIGNORE" in src, "")
    check("[gi-fn] checks for git repo before acting",
          "/workspace/.git" in src or "$project/.git" in src, "")
    check("[gi-fn] managed-block sentinel present",
          "vibe-managed runtime exclusions" in src, "")
    check("[gi-fn] excludes .claude/settings.local.json",
          ".claude/settings.local.json" in src, "")
    check("[gi-fn] excludes .vibe/",
          '".vibe/"' in src or "echo \".vibe/\"" in src, "")
    check("[gi-fn] excludes .vibe-allow-ssh",
          'echo ".vibe-allow-ssh"' in src, "")
    check("[gi-fn] called from main script body",
          "ensure_project_gitignore\n" in src or "ensure_project_gitignore$" in src.rstrip() + "\n", "")


def test_feedback_auto_promote_fragment() -> None:
    """Auto-promotion rules spec'd 2026-05-07 (shipped as their own fragment
    until task_028 merged them into claude-md/learnings.md). Behavioral rules
    for when to propose /learnings promotion after saving a feedback memory.
    A regression dropping them, the IS/IS-NOT list, or the opt-out hook would
    silently lose the cross-repo behavioral propagation channel."""
    print("\n[auto-promote rules (in learnings.md): shape]")
    check("[auto-promote] host fragment file exists",
          LEARNINGS_MD.exists(), str(LEARNINGS_MD))
    if not LEARNINGS_MD.exists():
        return
    content = LEARNINGS_MD.read_text()
    check("[auto-promote] § When to propose promotion present",
          "When to propose promotion" in content, "")
    check("[auto-promote] IS/NOT examples present",
          "YES:" in content and "NO:" in content, "")
    check("[auto-promote] cross-repo-applicable filter named",
          "cross-repo applicable" in content.lower() or "cross-repo-applicable" in content.lower(), "")
    check("[auto-promote] Y/n/never-ask three-option prompt",
          "Y / n / never-ask" in content or "Y, n, never-ask" in content, "")
    check("[auto-promote] VIBE_AUTO_PROMOTE opt-out env var",
          "VIBE_AUTO_PROMOTE" in content, "")
    check("[auto-promote] PreToolUse hook still gates the write",
          "PreToolUse hook" in content, "")
    check("[auto-promote] uses /learn command for the write",
          "/learn" in content, "")
    check("[auto-promote] explicit no-auto-write rule",
          "do NOT auto-write" in content.lower() or "Do NOT auto-write" in content, "")
    check("[auto-promote] one-prompt-per-memory rule",
          "One prompt per" in content or "one prompt per" in content, "")


def test_vs_md_plain_techy_verbosity_flags() -> None:
    """vs.md spec'd --plain / --techy / --verbosity flags 2026-05-07. The
    flags govern Spec Critic / Tester / Evaluator output mode; a regression
    silently dropping any of them would let the canonical default drift,
    hence this guard."""
    print("\n[/vs: --plain / --techy / --verbosity flags]")
    if not VS_MD.exists():
        check("[vs-flags] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-flags] --plain flag named",
          "`/vs --plain " in content, "")
    check("[vs-flags] --plain default ON documented",
          "default ON" in content, "")
    check("[vs-flags] --techy inverse flag named",
          "`/vs --techy " in content, "")
    check("[vs-flags] --verbosity N global flag named",
          "--verbosity N" in content, "")
    check("[vs-flags] verbosity scale 0-9 documented",
          "0-9" in content, "")
    check("[vs-flags] verbosity default 5",
          "Default 5" in content or "default 5" in content, "")
    check("[vs-flags] level 0 anchor (one-line pass/fail)",
          "**0**" in content and "one-line" in content, "")
    check("[vs-flags] level 5 anchor (default)",
          "**5**" in content, "")
    check("[vs-flags] level 9 anchor (full verbose)",
          "**9**" in content, "")
    check("[vs-flags] --vN-spec per-output override",
          "--vN-spec" in content, "")
    check("[vs-flags] --vN-test per-output override",
          "--vN-test" in content, "")
    check("[vs-flags] --vN-eval per-output override",
          "--vN-eval" in content, "")
    check("[vs-flags] flags propagate to subagent briefs",
          "propagate" in content.lower() and "subagent" in content.lower(), "")


def test_fable_subagents_flag_docs() -> None:
    """--fable-subagents (alias --fable) spec'd 2026-07-11 on Martin's live
    request ("use Fable for any subagents that will get better or faster
    results"). Guards the consent semantics: per-invocation pre-auth only,
    task-class routing preserved (never mechanical roles), the no-flag
    ask-gate unchanged, /vsss propagation + audit note, and the explicit
    distinction from the vibe-launcher --fable (chair-model-only) flag.
    task_028: the semantics are defined ONCE in vs.md \u00a7 Model economy;
    vss.md and vsss.md must point at it rather than restate it."""
    print("\n[/vs+/vss+/vsss: --fable-subagents standing pre-auth flag]")
    vs = VS_MD.read_text()
    # task_028: the grant is defined ONCE, in vs.md § Model economy
    # (### Fable grant); vss.md and vsss.md carry pointers, not restatements.
    check("[fable-flag] vs.md documents --fable-subagents",
          "`/vs --fable-subagents " in vs, "")
    check("[fable-flag] vs.md: single definition lives in § Model economy",
          "### Fable grant (`--fable-subagents`)" in vs, "")
    check("[fable-flag] vs.md: Model plan records the grant",
          "Fable rung: pre-authorised (--fable-subagents)" in vs, "")
    check("[fable-flag] vs.md: never mechanical roles",
          "NEVER Fable for mechanical roles" in vs, "")
    check("[fable-flag] vs.md: permits, never forces",
          "permits, never forces" in vs, "")
    check("[fable-flag] vs.md: permission, not blanket routing",
          "permission, not routing" in vs, "")
    check("[fable-flag] vs.md: without it the ask-gate is unchanged",
          "the ask-before-Fable gate is unchanged" in vs, "")
    check("[fable-flag] vs.md: ladder honours the standing grant",
          "the ladder MAY take that rung on capability-fails without a fresh ask" in vs, "")
    check("[fable-flag] vs.md: distinct from vibe --fable launcher flag",
          "sets only the chair/session model and authorises no subagent spend" in vs, "")
    check("[fable-flag] vs.md: alias documented",
          "(alias `--fable`)" in vs, "")
    check("[fable-flag] vs.md: --fable-gen forces the start it pre-authorises",
          "`--fable-gen` forces a Fable" in vs, "")
    check("[fable-flag] vs.md: Step-2 point-of-use honours the flag",
          "Honor `--gen` / `--fable-gen` / `--fable-subagents`" in vs, "")
    vss = (REPO / "devcontainer" / "commands" / "vss.md").read_text()
    check("[fable-flag] vss.md: hard-escalate carve-out names the flag",
          "--fable-subagents" in vss and "Credit-billed model dispatch" in vss, "")
    check("[fable-flag] vss.md: planner-brief carve-out present",
          "UNLESS this invocation carries `--fable-subagents`" in vss, "")
    check("[fable-flag] vss.md: threads the grant into whatever tool it picks",
          "threaded into whatever tool /vss picks" in vss, "")
    check("[fable-flag] vss.md: points at the single definition, never restates it",
          all("/vs \u00a7 Model economy" in ln
              for ln in vss.splitlines() if "--fable-subagents" in ln), "")
    vsss = (REPO / "devcontainer" / "commands" / "vsss.md").read_text()
    check("[fable-flag] vsss.md: flag documented with alias",
          "`/vsss --fable-subagents <args>` (alias `--fable`)" in vsss, "")
    check("[fable-flag] vsss.md: propagates into every wrapped /vss",
          "propagated into every wrapped `/vss` iteration" in vsss, "")
    check("[fable-flag] vsss.md: session-audit recording required",
          "Record it in the session file" in vsss, "")
    check("[fable-flag] vsss.md: points at the single definition",
          all("/vs \u00a7 Model economy" in ln
              for ln in vsss.splitlines() if "--fable-subagents" in ln), "")
    check("[fable-flag] vsss.md: grant persists across auto-resume relaunches",
          "The grant PERSISTS across auto-resume relaunches" in vsss, "")


def test_vs_md_panel_flag() -> None:
    """vs.md spec'd --panel 2026-07-10 (blind independent panellists +
    correlated-agreement/sycophancy check, ported from the agent-review-panel
    pattern per the 2026-07 harness-landscape audit, re-tiered to Sonnet).
    Guards the mechanism's load-bearing properties: structural blindness,
    identical briefs, the sycophancy check's direction (correlated consensus
    weakens confidence), dissent handling, and the Sonnet tiering."""
    print("\n[/vs: --panel blind review panel]")
    if not VS_MD.exists():
        check("[vs-panel] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-panel] --panel flag named",
          "`/vs --panel [N] " in content, "")
    check("[vs-panel] default 3, odd", "default 3" in content and "odd" in content, "")
    check("[vs-panel] Step 5c section present", "Step 5c" in content, "")
    check("[vs-panel] panellists dispatched in one parallel batch",
          "IN ONE MESSAGE" in content or "one concurrent batch" in content, "")
    check("[vs-panel] read-only code-reviewer panellist dispatch",
          'Dispatch N `Agent(subagent_type: "code-reviewer", model: "sonnet")` panellists' in content, "")
    check("[vs-panel] briefs identical except output-path token",
          "identical apart from the one substituted output-path token" in content, "")
    check("[vs-panel] no assigned personas (differentiation must emerge)",
          "differentiation must emerge" in content, "")
    check("[vs-panel] per-panellist artifact path",
          "panel/reviewer-<k>.md" in content, "")
    check("[vs-panel] chair aggregation artifact",
          "panel/summary.md" in content, "")
    check("[vs-panel] sycophancy/correlated-agreement check named",
          "sycophancy" in content and "orrelated" in content, "")
    check("[vs-panel] correlated consensus = low-information (weakens, not strengthens)",
          "low-information" in content, "")
    check("[vs-panel] unrefuted blocking dissent blocks pass",
          "NOT a pass" in content, "")
    check("[vs-panel] Sonnet panellists (not all-Opus)",
          "sonnet ×N" in content, "")
    check("[vs-panel] panellists never touch tasks.json",
          "do NOT touch `tasks.json`" in content, "")
    check("[vs-panel] rigorous mode keeps mechanical gate",
          "mechanical test gate still governs" in content, "")
    check("[vs-panel] cost role panel_reviewer",
          "panel_reviewer" in content, "")
    check("[vs-panel] panel disagreement never escalates ladder by itself",
          "never triggers the escalation ladder by itself" in content, "")
    check("[vs-panel] 5b explicitly skipped under --panel",
          "Skip this step entirely when `--panel` is set" in content, "")
    check("[vs-panel] rigorous interaction: sink green, never rescue red",
          "it can never rescue a red one" in content, "")
    check("[vs-panel] N validated: odd integer between 3 and 7",
          "odd integer between 3 and 7" in content, "")
    check("[vs-panel] Step 6 mandates reading all N panel verdicts",
          "all N of them" in content, "")
    check("[vs-panel] flow diagram shows panel variants",
          "--fuzzy --panel:" in content, "")
    check("[vs-panel] upstream 4-6 divergence annotated",
          "upstream runs 4–6 panellists" in content, "")


def test_vs_md_multi_task_archive_convention() -> None:
    """vs.md spec'd a multi-task archive convention 2026-05-07. The convention
    distinguishes per-task state (overwritten -> must archive) from repo-wide
    state (must NOT archive). A regression where someone re-broadens the
    archive scope to include tasks.json/progress.md would silently drop
    historical data, hence this guard."""
    print("\n[/vs: multi-task archive convention]")
    if not VS_MD.exists():
        check("[vs-archive] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-archive] § Multi-task state convention header",
          "## Multi-task state convention" in content, "")
    check("[vs-archive] documents .vs/archive/<task-id>/ path",
          ".vs/archive/<task-id>/" in content, "")
    check("[vs-archive] names spec.md as per-task (archived)",
          "Per-task" in content and ".vs/spec.md" in content, "")
    check("[vs-archive] names tasks.json as repo-wide (NOT archived)",
          "Repo-wide accumulating" in content and "tasks.json" in content, "")
    check("[vs-archive] explicit MUST NOT for tasks.json/progress.md",
          "must NOT be archived" in content, "")
    check("[vs-archive] critiques rename to bypass gitignore documented",
          "critiques/" in content and "cycle-*/" in content, "")
    check("[vs-archive] archive procedure references git mv",
          "git mv .vs/spec.md" in content, "")
    check("[vs-archive] resume procedure documented",
          "Resuming an archived task" in content, "")
    check("[vs-archive] inherits no-autonomous-push",
          "no-autonomous-push" in content, "")


def test_vss_md_audit_trail_and_push_policy() -> None:
    """vss.md defines the per-session audit format and the no-autonomous-push
    rule. Both are safety boundaries (audit = reviewability; no-push = trust
    model). A regression silently dropping either is the failure this guards."""
    print("\n[/vss: audit trail + push policy]")
    if not VSS_MD.exists():
        check("[vss-policy] vss.md exists", False, "missing")
        return
    content = VSS_MD.read_text()
    check("[vss-policy] § Session audit format header",
          "Session audit format" in content, "")
    check("[vss-policy] sessions/ path declared",
          ".vss/sessions/" in content, "")
    check("[vss-policy] format names per-iter blocks",
          "Iter " in content and "Final state" in content, "")
    check("[vss-policy] § Push policy header",
          "## Push policy" in content, "")
    check("[vss-policy] explicit no-autonomous-push wording",
          "Do NOT" in content and "push" in content.lower(), "")
    check("[vss-policy] --push-on-pass override flag named",
          "--push-on-pass" in content, "")
    check("[vss-policy] sessions file marked Committed",
          "**Committed.**" in content and ".vss/sessions" in content, "")


def test_conversation_history_fragment() -> None:
    """Transcript-search rules (their own fragment until task_028 merged them
    into claude-md/auto-memory-scope.md) teach Claude to search
    ~/.claude/projects/<slug>/*.jsonl transcripts when memory misses a user
    reference to past conversation. Regression dropping them, the JSONL path,
    the schema crib, or the jq recipes silently breaks the "search before
    saying I have no record" behavior."""
    print("\n[transcript search (in auto-memory-scope.md): shape]")
    check("[conv-history] host fragment file exists",
          AUTO_MEMORY_SCOPE_MD.exists(), str(AUTO_MEMORY_SCOPE_MD))
    if not AUTO_MEMORY_SCOPE_MD.exists():
        return
    content = AUTO_MEMORY_SCOPE_MD.read_text()
    check("[conv-history] names the JSONL path glob",
          "~/.claude/projects/" in content and ".jsonl" in content, "")
    check("[conv-history] names the -workspace slug",
          "-workspace" in content, "")
    check("[conv-history] documents user-prompt schema (string content)",
          'type: "user"' in content and "string" in content, "")
    check("[conv-history] documents assistant-text schema",
          'type: "assistant"' in content and 'type: "text"' in content, "")
    check("[conv-history] mentions skipping thinking and tool_use blocks",
          "thinking" in content and "tool_use" in content, "")
    check("[conv-history] ships a jq recipe",
          "jq -r" in content, "")
    check("[conv-history] tells Claude to filter tool_result entries",
          "tool_result" in content, "")
    check("[conv-history] mentions Docker volume single-machine limit",
          "vibe-claude-config" in content or "Docker volume" in content, "")
    check("[conv-history] warns against duplicating into a parallel file",
          "duplicate" in content.lower() or "duplicating" in content.lower(), "")


def test_install_extras_ssh_discipline_opt_in() -> None:
    """install-claude-extras.sh omits ssh-discipline.md from CLAUDE.md when
    VIBE_SSH_AUTO=1; includes it (alongside other fragments) when unset."""
    print("\n[ssh-opt-in: install-claude-extras.sh honours VIBE_SSH_AUTO]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Real source dir so we exercise the actual ssh-discipline.md + siblings.
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: opt-in OFF — ssh-discipline content should be present.
        dest_off = tmp_path / "off"
        dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off.pop("VIBE_SSH_AUTO", None)
        r_off = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=_isolate_extras_env(env_off), capture_output=True, text=True,
        )
        check("[ssh-opt-in] install exits 0 with VIBE_SSH_AUTO unset",
              r_off.returncode == 0, f"rc={r_off.returncode} err={r_off.stderr[:200]}")
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[ssh-opt-in] ssh-discipline.md marker present when opt-in unset",
              "<!-- vibe-md: ssh-discipline.md -->" in md_off, "marker missing")
        check("[ssh-opt-in] ssh-discipline.md body present when opt-in unset",
              "SSH Discipline" in md_off, "body missing")
        # Sanity: another fragment should also be present (proves the loop ran).
        check("[ssh-opt-in] other fragments still installed (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "web-research absent")

        # Pass 2: opt-in ON via env — ssh-discipline content should be absent.
        dest_on = tmp_path / "on"
        dest_on.mkdir()
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_SSH_AUTO"] = "1"
        r_on = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=_isolate_extras_env(env_on), capture_output=True, text=True,
        )
        check("[ssh-opt-in] install exits 0 with VIBE_SSH_AUTO=1",
              r_on.returncode == 0, f"rc={r_on.returncode} err={r_on.stderr[:200]}")
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[ssh-opt-in] ssh-discipline.md marker ABSENT with VIBE_SSH_AUTO=1",
              "<!-- vibe-md: ssh-discipline.md -->" not in md_on,
              "marker still present despite opt-in")
        check("[ssh-opt-in] other fragments still present with opt-in",
              "<!-- vibe-md: web-research.md -->" in md_on,
              "opt-in dropped unrelated fragments")


def test_ssh_marker_fail_closed() -> None:
    """.vibe-allow-ssh forge-resistance (mirrors task_020's _op_opted_in for
    the OP marker): the marker disables the per-action-SSH-ask fragment ONLY
    as a local untracked file in a verifiable git work tree. Committed or
    non-git markers are refused fail-closed (fragment kept) with a stderr ⚠;
    VIBE_SSH_AUTO=1 stays the non-git escape hatch."""
    print("\n[ssh-marker: fail-closed forge resistance]")
    git_ws = ('git -C "$WS" init -q && git -C "$WS" config user.email t@t '
              '&& git -C "$WS" config user.name t '
              '&& git -C "$WS" config core.hooksPath /dev/null')
    state, _ = _ssh_marker_result({}, f'{git_ws}; touch "$WS/.vibe-allow-ssh"')
    check("[ssh-marker AC1] untracked marker in git ws -> opted IN", state == "IN", state)
    state, err = _ssh_marker_result(
        {}, f'{git_ws}; touch "$WS/.vibe-allow-ssh"; '
            'git -C "$WS" add .vibe-allow-ssh; git -C "$WS" commit -qm x')
    check("[ssh-marker AC2] COMMITTED marker -> refused (fragment kept)", state == "OUT", state)
    check("[ssh-marker AC2] committed refusal warns on stderr", "COMMITTED" in err, err[:300])
    state, err = _ssh_marker_result({}, 'touch "$WS/.vibe-allow-ssh"')
    check("[ssh-marker AC3] marker in NON-git ws -> refused (fail closed)", state == "OUT", state)
    check("[ssh-marker AC3] non-git refusal warns on stderr",
          "verifiable git work tree" in err, err[:300])
    state, _ = _ssh_marker_result({"VIBE_SSH_AUTO": "1"}, 'touch "$WS/.vibe-allow-ssh"')
    check("[ssh-marker AC4] VIBE_SSH_AUTO=1 in non-git ws -> opted IN", state == "IN", state)
    src = INSTALL_EXTRAS.read_text()
    check("[ssh-marker AC5] fragment gate wired to _ssh_marker_opted_in",
          "if _ssh_marker_opted_in; then" in src, "")
    check("[ssh-marker AC5] helper mirrors launcher semantics (pairing note)",
          "_op_opted_in" in src and "semantically paired" in src,
          "helper must name its launcher twin so drift is visible")
    vibe_src = VIBE.read_text(encoding="utf-8")
    check("[ssh-marker AC5] launcher twin still exists",
          "_op_opted_in()" in vibe_src, "")


def test_task012_review_due_banner() -> None:
    """task_012: learning_review_due implements learn.md's frozen due
    contract (30+ entries / >90 days since reviewed: / >5 entries since the
    receipt count; missing receipt = never reviewed, floor of 5), fails soft
    on every malformed input, and the rebuild-path banner is gated on
    REBUILD + learning_is_enabled + not-opted-out."""
    print("\n[task_012: /learn --review due banner]")
    mk = 'for i in $(seq 1 %d); do echo x > "$LIB/e$i.md"; done'
    receipt = 'printf "reviewed: %s\\nentries: %s\\n" > "$LIB/.last-review"'
    check("[t012] 4 entries, no receipt -> NOT (below floor)",
          _review_due_result(mk % 4) == "NOT", "")
    check("[t012] 6 entries, no receipt -> DUE (never reviewed)",
          _review_due_result(mk % 6) == "DUE", "")
    check("[t012] 5 entries, no receipt -> NOT (floor is >5)",
          _review_due_result(mk % 5) == "NOT", "")
    check("[t012] 30 entries, fresh receipt -> DUE (30+ always due)",
          _review_due_result(
              mk % 30 + '; ' + receipt % ('$(date -u +%Y-%m-%dT%H:%M:%SZ)', '30')
          ) == "DUE", "")
    check("[t012] 12 entries, receipt entries:5 -> DUE (>5 captured since)",
          _review_due_result(
              mk % 12 + '; ' + receipt % ('$(date -u +%Y-%m-%dT%H:%M:%SZ)', '5')
          ) == "DUE", "")
    check("[t012] 12 entries, receipt entries:8, fresh -> NOT",
          _review_due_result(
              mk % 12 + '; ' + receipt % ('$(date -u +%Y-%m-%dT%H:%M:%SZ)', '8')
          ) == "NOT", "")
    check("[t012] 6 entries, reviewed 100 days ago -> DUE (>90 days)",
          _review_due_result(
              mk % 6 + '; ' + receipt % (
                  '$(date -u -d "@$(( $(date -u +%s) - 100*24*3600 ))" +%Y-%m-%dT%H:%M:%SZ)', '6')
          ) == "DUE", "")
    check("[t012] 6 entries, reviewed now, entries:6 -> NOT",
          _review_due_result(
              mk % 6 + '; ' + receipt % ('$(date -u +%Y-%m-%dT%H:%M:%SZ)', '6')
          ) == "NOT", "")
    check("[t012] garbage receipt, 6 entries -> DUE (treated never reviewed)",
          _review_due_result(
              mk % 6 + '; echo "not a receipt" > "$LIB/.last-review"'
          ) == "DUE", "")
    check("[t012] garbage receipt, 5 entries -> NOT (floor holds)",
          _review_due_result(
              mk % 5 + '; echo "not a receipt" > "$LIB/.last-review"'
          ) == "NOT", "")
    check("[t012] unparseable date, entries delta 4 -> NOT (date test skipped)",
          _review_due_result(
              mk % 10 + '; ' + receipt % ('yesterdayish', '6')
          ) == "NOT", "")
    check("[t012] missing library dir -> NOT",
          _review_due_result('rmdir "$LIB"; true') == "NOT", "")
    src = VIBE.read_text(encoding="utf-8")
    check("[t012] banner gated on REBUILD + enabled + not opted out",
          'if [ "$REBUILD" = true ] && learning_is_enabled' in src
          and 'learning_project_opted_out "$WORKSPACE"' in src, "")
    check("[t012] banner names /learn --review",
          "run /learn --review in a session" in src, "")
    check("[t012] predicate never writes to the library",
          "Pure read-only predicate" in src, "")
