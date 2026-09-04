#!/usr/bin/env python3
"""Scratch red/green sentinel for task_036 (--spec-first). Not the Tester's
test — Generator-owned, gitignored with the rest of cycle-1/. Checks the
literal AC1-AC10, AC12 substrings this Generator is responsible for landing
(AC11's real test lives in smoke/checks_13_spec_first.py, Tester-owned)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VS = (ROOT / "devcontainer/commands/vs.md").read_text()
VSS = (ROOT / "devcontainer/commands/vss.md").read_text()
VSSS = (ROOT / "devcontainer/commands/vsss.md").read_text()
TODO = (ROOT / "TODO.md").read_text()
CHANGELOG = (ROOT / "CHANGELOG.md").read_text()

failures = []


def check(label, cond):
    if not cond:
        failures.append(label)


# AC1
m1 = re.search(r"^- `/vs --spec-first <prompt>`.*$", VS, re.M)
m2 = re.search(r"^- `/vs --approve \[<task-id>\]`.*$", VS, re.M)
check("AC1 spec-first bullet exists", m1 is not None)
check("AC1 approve bullet exists", m2 is not None)
if m1:
    check("AC1 spec-first bullet <=40 words", len(m1.group(0).split()) <= 40)
    check("AC1 spec-first bullet has § Step 3b", "§ Step 3b" in m1.group(0))
if m2:
    check("AC1 approve bullet <=40 words", len(m2.group(0).split()) <= 40)
    check("AC1 approve bullet has § Step 3b", "§ Step 3b" in m2.group(0))

# AC2
h3 = VS.find("## Step 3 — Spec critic (Sonnet)")
h3b = VS.find("## Step 3b — Spec-first checkpoint (`--spec-first`)")
h4 = VS.find("## Step 4 — Generate")
check("AC2 Step 3b heading exists", h3b != -1)
check("AC2 Step 3b positioned after Step 3, before Step 4", h3 != -1 < h3b < h4)

# AC3
check(
    "AC3 fork sentence in Step 3 On pass paragraph",
    "Under `--spec-first`, do not wait in-session — go to Step 3b." in VS,
)

# AC4
step3b_body = VS[h3b:h4] if h3b != -1 and h4 != -1 else ""
ac4_literals = [
    'implementation_status: "awaiting-approval"',
    "vs --spec-first: spec awaiting approval (<task-id>)",
    "approve with: /vs --approve <task-id>",
    "END the run",
    "No Generator",
    "Martin's edits to `.vs/spec.md` ARE the approved version",
    "never require it byte-identical",
    "never re-run Spec Critic",
    "spec edited at approval",
    "credit-billed tier",
    "§ Model economy",
    'implementation_status: "in_progress"',
    "continue from Step 4 unchanged",
    "newest `awaiting-approval` task by default",
    "un-archived first",
    "no task is awaiting approval",
    "no cycle has run",
]
for lit in ac4_literals:
    check(f"AC4 literal present: {lit!r}", lit in step3b_body)

# AC5
check(
    "AC5 schema line",
    '"implementation_status": "pending|awaiting-approval|in_progress|complete"' in VS,
)

# AC6
check("AC6 parked at awaiting-approval", "parked at awaiting-approval" in VS)
mt_idx = VS.find("## Multi-task state convention")
check(
    "AC6 approve-runs-archive-procedure note present",
    "/vs --approve" in VS[mt_idx:mt_idx + 1500] if mt_idx != -1 else False,
)

# AC7
check("AC7 not an escalate trigger", "not an escalate trigger" in VSS)
check("AC7 checkpoint IS the escalation", "the checkpoint IS the escalation" in VSS)
check("AC7 never acts-as-user on spec approval", "never acts-as-user on spec approval" in VSS)
check("AC7 /vs --approve <task-id> in passthrough area", "/vs --approve <task-id>" in VSS)

modeA_start = VSS.find("2. **If found:**")
modeA_end = VSS.find("3. **If no bounded item found:**")
modeA_body = VSS[modeA_start:modeA_end] if modeA_start != -1 and modeA_end != -1 else ""
check("AC7 Mode A branch has awaiting-approval", "awaiting-approval" in modeA_body)
check(
    "AC7 Mode A branch has literal parenthetical",
    "(awaiting approval — /vs --approve <task-id>)" in modeA_body,
)
check("AC7 Mode A branch says Step 3b commit", "Step 3b commit" in modeA_body)
check("AC7 Mode A branch says run is parked", "parked" in modeA_body)

step4_start = VSS.find("### Step 4 — Close out")
next_heading = re.search(r"\n#{2,3} ", VSS[step4_start + 1:]) if step4_start != -1 else None
step4_end = (step4_start + 1 + next_heading.start()) if next_heading else len(VSS)
step4_body = VSS[step4_start:step4_end] if step4_start != -1 else ""
check("AC7 Step 4 branch has awaiting-approval", "awaiting-approval" in step4_body)
check(
    "AC7 Step 4 branch has literal parenthetical",
    "(awaiting approval — /vs --approve <task-id>)" in step4_body,
)
check("AC7 Step 4 branch says Step 3b commit", "Step 3b commit" in step4_body)
check("AC7 Step 4 branch says run is parked", "parked" in step4_body)

# AC8
sb_idx = VSSS.find("## Session-budget capture")
sb_end = VSSS.find("Every iteration appends")
sb_body = VSSS[sb_idx:sb_end] if sb_idx != -1 else ""
m8 = re.search(r"^\s*- `/vsss --spec-first <args>`.*$", sb_body, re.M)
check("AC8 session-budget bullet exists", m8 is not None)
if m8:
    check("AC8 session-budget bullet has /vs § Step 3b", "/vs § Step 3b" in m8.group(0))

il_idx = VSSS.find("### Interaction with the loop")
il_end = VSSS.find("### After each /vss completes")
il_body = VSSS[il_idx:il_end] if il_idx != -1 else ""
check("AC8 never blocks the loop", "never blocks the loop" in il_body)
check(
    "AC8 write/post/move phrase",
    "write the spec, post one action point, move to the next queue item" in il_body,
)

cp_idx = VSSS.find("### Consume protocol")
cp_end = VSSS.find("### Precedence")
cp_body = VSSS[cp_idx:cp_end] if cp_idx != -1 else ""
check("AC8 consume protocol queues approve", "queues `/vs --approve <task-id>`" in cp_body)
check("AC8 consume protocol spec-revision instruction", "spec-revision instruction" in cp_body)

report_idx = VSSS.find("## Reporting back at exit")
report_body = VSSS[report_idx:] if report_idx != -1 else ""
check("AC8 Deferred / awaiting approval line", "Deferred" in report_body and "awaiting approval" in report_body)
check("AC8 Reporting has /vs --approve <task-id>", "/vs --approve <task-id>" in report_body)

# AC9
ac9_literal = (
    'Approve the spec for <task-id> — <one-line goal>? It\'s at .vs/spec.md. '
    'Reply "approve", or edit that file and reply "approve"; reply with changes '
    'instead to redirect. (T<n>)'
)
check("AC9 verbatim action-point sentence", ac9_literal in VSSS)

# AC10
total_words = len(VS.split()) + len(VSS.split()) + len(VSSS.split())
check("AC10 total word budget <=14000", total_words <= 14000)
print(f"word totals: vs={len(VS.split())} vss={len(VSS.split())} vsss={len(VSSS.split())} total={total_words}")

# AC12
check("AC12 TODO queue item 1 removed", "1. `--spec-first` mode for `/vs`" not in TODO)
check("AC12 TODO new hardening item present", "blocks it unless the matching spec has been approved" in TODO)
check("AC12 CHANGELOG has 2026-09-04 heading", "## 2026-09-04" in CHANGELOG)

if failures:
    print(f"\n{len(failures)} FAILURES:")
    for f in failures:
        print(f" - {f}")
    sys.exit(1)
else:
    print("\nALL SENTINEL CHECKS PASS")
    sys.exit(0)
