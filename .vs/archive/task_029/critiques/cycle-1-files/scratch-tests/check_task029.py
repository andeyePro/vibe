#!/usr/bin/env python3
"""Scratch TDD check for task_029 (fromto format). Red before edits, green after.

Not part of the permanent suite. Asserts AC1-AC8 and AC12 from .vs/spec.md.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/workspace")
VSSS_MD = REPO / "devcontainer/commands/vsss.md"
FROMTO_NOTE = Path("/brain2/meta/fromto-format.md")
BASELINE_FILE = REPO / ".vs/cycle-1/scratch-tests/vsss_baseline.md"
BASELINE_FROMCLAUDE_COUNT = 10  # git show 73172fb:devcontainer/commands/vsss.md | grep -c fromClaude
BASELINE_WORDS = None  # computed below

FAILURES = []
PASSES = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILURES.append(f"{label}: {detail}")


def norm(s: str) -> str:
    """Collapse whitespace runs (incl. newlines from markdown line-wrap) to a
    single space, so literal-substring checks survive prose reflow."""
    return re.sub(r"\s+", " ", s)


TEMPLATE = """---
state: authored
author: Claude (<harness>, <repo>)
created: <ISO date>
cssclasses: [trust-authored]
---
Reply in [[<project>-from<User>]]. History: [[<project>-Q&A-archive]].

1. <action point: a question to answer, or a test to run> (T<n>)"""


def main() -> int:
    text = VSSS_MD.read_text()
    lines = text.splitlines()

    # ---- AC1 ----
    idx_three_files = text.find("### The three files")
    idx_fromto = text.find("### fromto format")
    idx_question = text.find("### Question format (fromClaude)")
    check("AC1 fromto heading exists", idx_fromto != -1, "heading not found")
    if idx_fromto != -1:
        check("AC1 fromto after three-files", idx_three_files != -1 and idx_three_files < idx_fromto,
              f"three_files={idx_three_files} fromto={idx_fromto}")
        check("AC1 fromto before question-format", idx_question != -1 and idx_fromto < idx_question,
              f"fromto={idx_fromto} question={idx_question}")

    # Extract the fromto-format section body (between its heading and the next heading)
    fromto_section = ""
    if idx_fromto != -1 and idx_question != -1 and idx_fromto < idx_question:
        fromto_section = text[idx_fromto:idx_question]
    fromto_section_n = norm(fromto_section)

    # ---- AC2 ----
    check("AC2 template verbatim present", TEMPLATE in text,
          "exact fenced template not found verbatim")
    check("AC2 template inside fromto section", TEMPLATE in fromto_section,
          "template not located inside § fromto format")

    # ---- AC3 ----
    ac3_strings = [
        "one ordered list and nothing else",
        "no session report",
        "Information appears only where it answers a question the user asked",
        "action points only",
        "contiguous from 1",
    ]
    for s in ac3_strings:
        check(f"AC3 contains '{s}'", s in fromto_section_n, "not found in § fromto format")

    # ---- AC4 ----
    exit_sentinel = "Session log: `.vss/sessions/<start-ISO>.md` — <N> commits, <pushed|not pushed>."
    check("AC4 exit sentinel present", norm(exit_sentinel) in fromto_section_n, "sentinel not found")
    check("AC4 'exactly one line' present", "exactly one line" in fromto_section_n, "not found")

    # ---- AC5 ----
    check("AC5 brain2 path mentioned", "/brain2/meta/fromto-format.md" in fromto_section_n, "not found")
    check("AC5 'overrides this default verbatim'", "overrides this default verbatim" in fromto_section_n, "not found")
    check("AC5 'write-files-only'", "write-files-only" in fromto_section_n, "not found")
    check("AC5 'never `git` against'", "never `git` against" in fromto_section_n, "not found")

    # ---- AC6 ----
    check("AC6 '### At exit' deleted", "### At exit" not in text, "still present")
    check("AC6 old exit-append mandate deleted",
          "Append the exit report (same content as § Reporting back at exit)" not in text,
          "still present")
    check("AC6 'If fromto channels are active' deleted",
          "If fromto channels are active" not in text, "still present")

    # (a) region from "## Reporting back at exit" to EOF: zero fromClaude / from<User>
    idx_report_heading = text.find("## Reporting back at exit")
    check("AC6a heading found", idx_report_heading != -1, "heading missing")
    tail = text[idx_report_heading:] if idx_report_heading != -1 else ""
    check("AC6a zero 'fromClaude' after Reporting heading", tail.count("fromClaude") == 0,
          f"found {tail.count('fromClaude')}")
    check("AC6a zero 'from<User>' after Reporting heading", tail.count("from<User>") == 0,
          f"found {tail.count('from<User>')}")

    # (b) outside § fromto format, no line matches the paraphrase regex;
    # inside § fromto format, only the AC4 exit-line rule may match.
    pattern = re.compile(r"(append|mirror|copy).{0,60}(report|outcome).{0,60}fromClaude", re.IGNORECASE)
    fromto_start = idx_fromto
    fromto_end = idx_question if idx_question != -1 else len(text)
    bad_outside = []
    bad_inside = []
    pos = 0
    for line in lines:
        line_start = pos
        pos += len(line) + 1
        if pattern.search(line):
            if fromto_start != -1 and fromto_start <= line_start < fromto_end:
                # allow only if this line IS the AC4 exit-line rule
                if exit_sentinel not in line and "exactly one line" not in line:
                    bad_inside.append(line)
            else:
                bad_outside.append(line)
    check("AC6b no paraphrase regex outside § fromto format", not bad_outside, str(bad_outside))
    check("AC6b no disallowed paraphrase regex inside § fromto format", not bad_inside, str(bad_inside))

    # (c) total fromClaude count <= baseline - 2 + mentions inside fromto section
    total_fromclaude = text.count("fromClaude")
    inside_fromclaude = fromto_section.count("fromClaude")
    limit = BASELINE_FROMCLAUDE_COUNT - 2 + inside_fromclaude
    check("AC6c fromClaude total within budget", total_fromclaude <= limit,
          f"total={total_fromclaude} limit={limit} (baseline={BASELINE_FROMCLAUDE_COUNT}, inside={inside_fromclaude})")

    # ---- AC7 ----
    preserved = [
        "## Reporting back at exit",
        "Total iterations run.",
        "Lead with `---` before the report block.",
        "### Question format (fromClaude)",
        "questions and blocking asks only — no progress notes, no FYIs",
    ]
    text_n = norm(text)
    for s in preserved:
        check(f"AC7 preserved '{s}'", norm(s) in text_n, "missing")

    order_headings = [
        "### The three files",
        "### fromto format",
        "### Question format (fromClaude)",
        "### Answer format (from<User>) — the lazy contract",
        "### Consume protocol — start of EVERY iteration",
        "### Precedence",
        "### Interaction with the loop",
        "### After each /vss completes",
    ]
    indices = [text.find(h) for h in order_headings]
    check("AC7 all order headings found", all(i != -1 for i in indices),
          str(list(zip(order_headings, indices))))
    if all(i != -1 for i in indices):
        check("AC7 section order preserved", indices == sorted(indices), str(indices))

    # ---- AC8 ----
    if FROMTO_NOTE.exists():
        note = FROMTO_NOTE.read_text()
        fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", note, re.DOTALL)
        check("AC8 note has frontmatter", fm_match is not None, "no frontmatter block found")
        if fm_match:
            frontmatter, body = fm_match.group(1), fm_match.group(2)
            for field in ["title:", "aliases:", "state: authored", "author:", "checked: []",
                          "reviewed: []", "authorised:", "source_type: internal", "sources:",
                          "created: 2026-09-02", "recorded_at: 2026-09-02",
                          "cssclasses: [trust-authored]", "tags:"]:
                check(f"AC8 frontmatter has '{field}'", field in frontmatter, "missing")
            check("AC8 tags contains vibe", re.search(r"tags:.*vibe", frontmatter) is not None
                  or "vibe" in frontmatter, "vibe not in tags")
            check("AC8 tags contains fromto", "fromto" in frontmatter, "fromto not in tags")
            # authorised: empty
            auth_match = re.search(r"^authorised:[ \t]*(.*)$", frontmatter, re.MULTILINE)
            check("AC8 authorised is empty", auth_match is not None and auth_match.group(1).strip() in ("", "[]"),
                  f"authorised value: {auth_match.group(1) if auth_match else 'NOT FOUND'}")
            check("AC8 state never above authored", "state: authored" in frontmatter and
                  not re.search(r"state:\s*(checked|reviewed|authorised)", frontmatter),
                  "state escalated")
            check("AC8 body has template verbatim", TEMPLATE in body, "template missing from body")
            check("AC8 'every project' present", "every project" in norm(body), "missing")
    else:
        print("NOTE: /brain2/meta/fromto-format.md does not exist yet - AC8 will be asserted after Generator writes it.")

    # ---- AC12 ----
    baseline_words = len(BASELINE_FILE.read_text().split())
    current_words = len(text.split())
    growth = current_words - baseline_words
    check("AC12 word growth <= 120", growth <= 120, f"growth={growth} (baseline={baseline_words}, current={current_words})")

    print(f"\n{PASSES} passed, {len(FAILURES)} failed\n")
    for f in FAILURES:
        print("FAIL:", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
