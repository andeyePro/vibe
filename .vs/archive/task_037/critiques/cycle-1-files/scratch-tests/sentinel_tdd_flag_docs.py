#!/usr/bin/env python3
"""Scratch red/green sentinel for task_037 (/vs --TDD docs). Not the Tester's
test — mirrors the ACs so the Generator can verify red-before-green locally.
Mirrors what smoke/checks_13_spec_first.py::test_tdd_flag_docs will assert."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VS = (REPO / "devcontainer/commands/vs.md").read_text()
VSS = (REPO / "devcontainer/commands/vss.md").read_text()
VSSS = (REPO / "devcontainer/commands/vsss.md").read_text()

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


# AC1: Flags bullet
m = re.search(r"^- `/vs --TDD <prompt>`.*$", VS, re.M)
check("AC1: flags bullet exists", m is not None)
if m:
    line = m.group(0)
    words = len(line.split())
    check("AC1: <=45 words", words <= 45)
    check("AC1: contains red-first", "red-first" in line)
    check("AC1: contains tdd-trail.md", "tdd-trail.md" in line)
    check("AC1: contains incompatible with `--fuzzy`", "incompatible with `--fuzzy`" in line)

# AC2: Step 4 paragraph
step4_idx = VS.find("## Step 4 — Generate")
step5_idx = VS.find("## Step 5 — Verify")
step4_body = VS[step4_idx:step5_idx] if step4_idx >= 0 and step5_idx >= 0 else ""
tdd_para_m = re.search(r"\*\*Under `--TDD`\*\*.*", step4_body, re.S)
check("AC2: Under --TDD paragraph present in Step 4", tdd_para_m is not None)
tdd_para = tdd_para_m.group(0) if tdd_para_m else ""
for token in [
    "before the implementing edit",
    ".vs/cycle-<N>/tdd-trail.md",
    "one entry per acceptance criterion",
    "test file",
    "command",
    "non-zero exit",
    "failing assertion",
    "written:",
    "scratch-tests/",
    "A trail entry written after the implementation, or without a failing run, is a cycle fail.",
]:
    check(f"AC2: contains {token!r}", token in tdd_para)
check("AC2: entry shape present", "AC<n> | test file | command | exit | failing assertion | written:" in tdd_para)

# AC3: Step 5a paragraph
step5a_idx = VS.find("### Step 5a")
step5b_idx = VS.find("### Step 5b")
step5a_body = VS[step5a_idx:step5b_idx] if step5a_idx >= 0 and step5b_idx >= 0 else ""
tdd_5a_m = re.search(r"\*\*Under `--TDD`\*\*.*", step5a_body, re.S)
check("AC3: Under --TDD paragraph present in Step 5a", tdd_5a_m is not None)
tdd_5a = tdd_5a_m.group(0) if tdd_5a_m else ""
for token in [
    "tdd-trail.md",
    "diff.patch",
    "every acceptance criterion has a trail entry",
    "named test file exists",
    "assertion names the criterion",
    "a weak proxy, not proof",
    "fail the cycle",
    "only to check the trail",
]:
    check(f"AC3: contains {token!r}", token in tdd_5a)
check(
    "AC3: independence carve-out sentence",
    "under `--TDD` the Tester additionally reads `tdd-trail.md` and `diff.patch` — only to check the trail, never the Generator's report"
    in tdd_5a,
)
check(
    "AC3: summary line amended",
    "a 3-line summary (4 lines under `--TDD`: a `TDD trail:` line is appended)" in step5a_body,
)
rules_idx = VS.find("## Rules")
refuse_idx = VS.find("## When to refuse or stop")
rules_body = VS[rules_idx:refuse_idx] if rules_idx >= 0 and refuse_idx >= 0 else ""
check("AC3: No cross-subagent bullet carve-out", "except the `--TDD` trail check" in rules_body)

# AC4: Step 3b sentence updated, no dangling (when implemented)
check(
    "AC4: new stacking sentence present",
    "`--TDD` stacking: the spec gate runs first; `--TDD` governs Step 4 (red-first trail) and Step 5a (trail check) only."
    in VS,
)
check("AC4: '(when implemented)' gone", "(when implemented)" not in VS)

# AC5: Rules bullet + refusal mention
check(
    "AC5: Rules --TDD/--fuzzy bullet",
    "--TDD" in rules_body and "--fuzzy" in rules_body and "refuse with one line" in rules_body,
)

# AC6: vss.md / vsss.md passthrough
specfirst_sentence_m = re.search(r"[^.]*--spec-first[^.]*\.", VSS)
check("AC6: vss.md passthrough sentence found", specfirst_sentence_m is not None)
if specfirst_sentence_m:
    sent = specfirst_sentence_m.group(0)
    check("AC6: vss.md sentence also names --TDD", "--TDD" in sent)
    check("AC6: vss.md sentence has threads through to /vs", "threads through to `/vs`" in sent)
vsss_tdd_m = re.search(r"^\s*- `/vsss --TDD <args>`.*$", VSSS, re.M)
check("AC6: vsss.md session-budget bullet exists", vsss_tdd_m is not None)
if vsss_tdd_m:
    check("AC6: vsss.md bullet references /vs § Step 4", "/vs § Step 4" in vsss_tdd_m.group(0))

# AC7: state directory + panel sentence
state_idx = VS.find("## State directory")
multitask_idx = VS.find("## Multi-task state convention")
state_body = VS[state_idx:multitask_idx] if state_idx >= 0 and multitask_idx >= 0 else ""
check("AC7: tdd-trail.md listed in state dir", "cycle-N/tdd-trail.md" in state_body and "red-first evidence" in state_body)
check(
    "AC7: panellists-do-not-check-trail sentence",
    "panellists do not check the trail; the Tester does" in VS,
)

# AC8: word budget
total_words = len(VS.split()) + len(VSS.split()) + len(VSSS.split())
check("AC8: total words <= 14300", total_words <= 14300)
print(f"total words: {total_words}")

if failures:
    print(f"RED: {len(failures)} failing assertions:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
else:
    print("GREEN: all sentinel checks passed")
    sys.exit(0)
