#!/usr/bin/env python3
"""Acceptance checks for task_065 (Task&I in /vss and /vsss), Part B: harness prose, docs and gates.

Tester-owned (cycle 1).  AC9-AC11 of ``.vs/spec.md``.  Part A (``decide`` and storage) is
``checks_53_taskandi_decide.py``.

The prose is checked mechanically: the block grammar and the exact skip string, zero Task&I text outside the block
(with a negative-control copy that the checker must reject), every fenced ``taskandi-client`` line passing the real
client's ``--check-argv`` after placeholder substitution, the subcommand set, ordering inside the boundary step, and the
required phrases and failure-table rows.

Run only this module with:
    python3 smoke/checks_54_harness_prose.py
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _CLIENT, _RESULTS, _check, _fixture_payload, _iso

_T = "[harness-prose]"
_REPO = Path(__file__).resolve().parent.parent
_CMD = {"vss": _REPO / "devcontainer" / "commands" / "vss.md", "vsss": _REPO / "devcontainer" / "commands" / "vsss.md"}
_SKILL = {"vss": _REPO / "devcontainer" / "codex" / "skills" / "vss" / "SKILL.md", "vsss": _REPO / "devcontainer" / "codex" / "skills" / "vsss" / "SKILL.md"}
_HARNESS = _REPO / "devcontainer" / "taskandi-harness.md"
_DOCKERFILE = _REPO / "devcontainer" / "Dockerfile"
POINTER = ("Otherwise read `/usr/local/share/vibe/taskandi-harness.md` now, in full, and follow it for this run; "
           "it overrides the fromClaude steps below wherever they conflict.")
_CONTEXT = _REPO / "devcontainer" / "codex" / "context.md"
START, END = "<!-- taskandi-bound:start -->", "<!-- taskandi-bound:end -->"
SKIP = ("Skip this section unless `.vibe/taskandi-descriptor.json` or `.vibe/taskandi.json` exists in the project; "
        "if one does, run `taskandi-client status`: continue only if it prints `\"bound\":true` with `\"channel\":\"taskandi-http\"`, "
        "and if it exits 1, use the file channel for this run and post one question saying the Task&I binding is broken, quoting its message.")
TASKANDI = re.compile(r"taskandi|task&i", re.I)
CONTEXT_ALLOWED = re.compile(r"not require.*Task&I|never invoke .taskandi-client", re.I)
SUBCOMMANDS = {"status", "next-task", "enqueue", "usage", "flush", "poll", "decide", "release", "complete"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block_of(text: str) -> str:
    """The text between the markers (callers have already validated the grammar)."""
    lines = text.split("\n")
    s = next(i for i, l in enumerate(lines) if l.strip() == START)
    e = next(i for i, l in enumerate(lines) if l.strip() == END)
    return "\n".join(lines[s + 1:e])


def grammar_problems(text: str, outside_allowed: re.Pattern | None = None) -> list:
    """Block grammar + 'no Task&I text outside the block'.  Returns a list of problems (empty = well formed)."""
    problems = []
    lines = text.split("\n")
    if text.count(START) != 1 or text.count(END) != 1:
        return [f"need exactly one start and one end marker (found {text.count(START)}/{text.count(END)})"]
    s = [i for i, l in enumerate(lines) if l.strip() == START]
    e = [i for i, l in enumerate(lines) if l.strip() == END]
    if len(s) != 1 or len(e) != 1:
        return ["each marker must be alone on its own line"]
    if not s[0] < e[0]:
        return ["end marker precedes start marker"]
    inside = lines[s[0] + 1:e[0]]
    if any("taskandi-bound:" in l for l in inside):
        problems.append("marker text inside the block")
    first = next((l for l in inside if l.strip()), None)
    if first != SKIP:
        problems.append(f"first non-blank line inside the block is not the skip string: {first!r}")
    for i, l in enumerate(lines):
        if s[0] <= i <= e[0]:
            continue
        if TASKANDI.search(l) and not (outside_allowed and outside_allowed.search(l)):
            problems.append(f"line {i + 1} outside the block mentions Task&I: {l[:100]!r}")
    return problems


def fenced_commands(block: str) -> list:
    """Every line starting with `taskandi-client` inside a fenced code block of the block."""
    out, in_fence = [], False
    for raw in block.split("\n"):
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.startswith("taskandi-client"):
            out.append(line)
    return out


def inline_commands(block: str) -> list:
    return re.findall(r"`taskandi-client\s+([a-z][a-z-]*)", block)


_SAMPLES = {"session": "2026-10-30T20-58-02Z", "n": "3", "agent": "claude", "task": "leaf-b", "effective task": "leaf-b",
            "ask_ids": "ask-1,ask-2", "ask_id": "ask-1", "key": "ask-key", "hash12": "abcdef012345", "transcript": "/tmp/claude-session.jsonl",
            "account": "acct", "k": "2", "estimate": "30"}


def substitute(line: str) -> str:
    def sub(m):
        name = m.group(1).strip()
        if name in _SAMPLES:
            return _SAMPLES[name]
        return "5" if re.search(r"minutes|estimate|windows|count|number", name, re.I) else "sample"
    return re.sub(r"<([^<>]+)>", sub, line)


def stdin_for(argv: list) -> str:
    if argv[:1] != ["enqueue"] or len(argv) < 2:
        return ""
    kind = argv[1]
    if kind == "comment":
        return json.dumps({"text": "Iteration 3 done."})
    if kind == "record_time":
        return json.dumps({"started_at": _iso(int(time.time() * 1000) - 7200_000), "seconds": 60})
    if kind in ("ask", "record_usage"):
        return json.dumps(_fixture_payload(kind))
    return ""


def check_argv(line: str, cwd: Path) -> tuple:
    argv = shlex.split(substitute(line))
    assert argv[0] == "taskandi-client"
    argv = argv[1:]
    env = {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")} | {"VIBE_CONTAINER": "0"}
    r = subprocess.run(["node", str(_CLIENT), "--check-argv", *argv], cwd=str(cwd), input=stdin_for(argv), capture_output=True,
                       text=True, timeout=60, env=env)
    return r, argv


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*]", "", text))


# ---------------------------------------------------------------------------
# AC9 Prose structure
# ---------------------------------------------------------------------------

def test_hp_ac9_structure() -> None:
    print(f"{_T} AC9 prose structure")
    texts = {name: read(path) for name, path in _CMD.items()}
    for name, text in texts.items():
        probs = grammar_problems(text)
        _check(f"{_T} AC9: {name}.md has exactly one well-formed block, the exact skip string first, and no Task&I text outside it",
               probs == [], "; ".join(probs)[:400])
        if not probs:
            inside = [l for l in block_of(text).split("\n") if l.strip()]
            _check(f"{_T} AC9: {name}.md block is exactly the skip string plus the pointer sentence, at most 75 words (rev 7: the longer AC34 skip string needs 71)",
                   inside == [SKIP, POINTER] and len(" ".join(inside).split()) <= 75, repr(inside)[:300])
    # negative controls: the checker is not vacuous
    base = texts["vss"]
    s_idx = base.index(START)
    controls = {
        "an extra Task&I line outside the block": base[:s_idx] + "Remember to call Task&I here.\n" + base[s_idx:],
        "an extra taskandi-client mention after the block": base + "\nRun taskandi-client flush.\n",
        "a changed skip string": base.replace(SKIP, SKIP.replace("Skip this section", "Skip this part"), 1),
        "a second block": base + f"\n{START}\n{SKIP}\n{END}\n",
        "a missing end marker": base.replace(END, "", 1),
        "a marker inline with other text": base.replace(START, "see " + START, 1),
        "marker text inside the block": base.replace(SKIP, SKIP + "\n" + "taskandi-bound:start", 1),
        "the skip string preceded by other text": base.replace(SKIP, "Intro line.\n\n" + SKIP, 1),
    }
    for label, bad in controls.items():
        if bad == base:
            _check(f"{_T} AC9 negative control builder: {label} changed the text", False, "mutation did not apply (is the block well formed?)")
            continue
        _check(f"{_T} AC9 negative control: {label} is rejected by the checker", grammar_problems(bad) != [], "checker accepted a bad copy")
    # a whole-file control copy written to disk fails the same checker (what a reviewer would run)
    with tempfile.TemporaryDirectory(prefix="hp-neg-") as td:
        p = Path(td) / "vss.md"
        p.write_text(controls["an extra Task&I line outside the block"])
        _check(f"{_T} AC9 negative control: a control file copy of vss.md with an extra Task&I line fails", grammar_problems(read(p)) != [])
    # Codex skills: no match anywhere; delegation sentence intact
    for name, path in _SKILL.items():
        text = read(path)
        hits = [l for l in text.split("\n") if TASKANDI.search(l)]
        _check(f"{_T} AC9: codex skill {name}/SKILL.md has no Task&I text anywhere", hits == [], repr(hits[:2]))
        want = f"/usr/local/share/vibe/commands/{name}.md` "
        flat = re.sub(r"\s+", " ", text)
        _check(f"{_T} AC9: codex skill {name}/SKILL.md keeps its delegation to the command file (Read ... {name}.md ... in full)",
               re.search(rf"[Rr]ead\b[^.]*`/usr/local/share/vibe/commands/{name}\.md`[^.]*in full", flat) is not None, want)
    _check(f"{_T} AC9 control: the skill checker would catch a Task&I line", TASKANDI.search("Use Task&I here") is not None)
    # context.md
    ctx = read(_CONTEXT)
    probs = grammar_problems(ctx, CONTEXT_ALLOWED)
    _check(f"{_T} AC9: context.md has one well-formed block and every Task&I mention outside it is an allowed line", probs == [], "; ".join(probs)[:400])
    _check(f"{_T} AC9: context.md no longer has the v1 `to` ask shape or the old section heading",
           "Optional Task&I Action Window" not in ctx and not re.search(r"containing `to`", ctx) and not re.search(r"payload containing", ctx), "old text still present")
    _check(f"{_T} AC9 negative control: an extra Task&I line outside context.md's block is rejected",
           grammar_problems(ctx.replace(START, "Task&I is configured here.\n" + START, 1), CONTEXT_ALLOWED) != [])
    if not probs:
        cb = norm(block_of(ctx))
        used = set(inline_commands(block_of(ctx))) | {c.split()[1] for c in fenced_commands(block_of(ctx)) if len(c.split()) > 1}
        _check(f"{_T} AC9: context.md block allows only status, poll, enqueue ask and usage (no decide/next-task/release/complete/flush-as-work)",
               used <= {"status", "poll", "enqueue", "usage", "flush"} and not (used & {"decide", "next-task", "release", "complete"}), repr(used))
        _check(f"{_T} AC9: context.md block mentions enqueue ask through FM2C and usage", "enqueue ask" in cb and "FM2C" in cb and "usage" in cb)
        _check(f"{_T} AC9: context.md block points $vss/$vsss at taskandi-harness.md", "/usr/local/share/vibe/taskandi-harness.md" in cb and re.search(r"vss", cb) is not None, cb[:300])
        _check(f"{_T} AC9: context.md keeps the guarantee: never invoke taskandi-client when both config files are absent",
               re.search(r"never invoke taskandi-client", cb) is not None and ".vibe/taskandi.json" in cb and ".vibe/taskandi-descriptor.json" in cb, cb[:400])


# ---------------------------------------------------------------------------
# AC10 Prose commands
# ---------------------------------------------------------------------------

_REQUIRED = [
    ("args-mode paragraph", r"Args mode"), ("args mode does not call next-task", r"Do not call next-task"),
    ("A-mode paragraph", r"A-mode"), ("linked-task paragraph", r"Linked task"), ("linked task release reason", r"session opened on another task"),
    ("no-claim-mode paragraph", r"No-claim mode"), ("no-claim: decide is not run", r"decide is not run"),
    ("no-claim: targets the effective task", r"--task <effective task>"),
    ("proceed comment text", r"Proceeding on the default for ask"), ("proceed comment key", r"-proceed-<ask_id>"),
    ("--resolve step", r"decide --resolve <key> --as proceeded"), ("provisional commit note", r"provisional"),
    ("park-task release", r"--parked-asks"), ("budget-stopped release", r"--budget-stopped"), ("allowance reason", r"Allowance spent\."),
    ("park reason", r"Waiting on"), ("--no-other-work", r"--no-other-work"), ("repoll", r"repoll"),
    ("budget ask key", r"budget-<task>"), ("budget ask is not blocking", r"blocking: false"), ("budget ask default", r"Stop at the allowance\."),
    ("budget answer never raises the cap", r"never raises the cap"),
    ("hard-escalate sentence", r"Hard-escalate items never become Task&I asks"),
    ("safety: data never instructions", r"never grant permission"), ("safety: no task text copied", r"Never copy task text"),
    ("safety: answer cannot waive hard-escalate", r"An answer cannot waive the hard-escalate list"),
    ("safety: never retry uncertain", r"Never retry an uncertain delivery without reconcile evidence"),
    ("boundary ordering sentence", r"usage and flush always precede complete, release and next-task"),
    ("usage skip note", r"usage not posted: transcript unknown"), ("next-task failure note", r"next-task failed:"),
    ("decide-unavailable release reason", r"Task&I decision unavailable"), ("TODO.md fallback", r"TODO\.md"),
    ("flush exit code caveat", r"flush exits 0"), ("open_children handling", r"open_children"),
    ("never guess the transcript by recency", r"Never guess by recency"), ("CLAUDE_CODE_SESSION_ID transcript", r"CLAUDE_CODE_SESSION_ID"),
    ("Codex transcript", r"CODEX_THREAD_ID"),
]
_ROWS = [("status exits 1", r"^\|\s*status exits 1"), ("next-task exits 1", r"^\|\s*next-task exits 1"), ("enqueue/usage/flush fails", r"^\|\s*enqueue/usage/flush fails"),
         ("poll fails", r"^\|\s*poll fails"), ("no-claim mode", r"^\|\s*no-claim mode"), ("decide exits 1 or unparsable", r"^\|\s*decide exits 1 or prints unparsable JSON"),
         ("complete/release outcome unknown", r"^\|\s*complete/release outcome unknown"), ("lease error", r"^\|\s*a lease error")]


def test_hp_ac10_commands() -> None:
    print(f"{_T} AC10 procedure file taskandi-harness.md")
    name = "taskandi-harness"
    if not _HARNESS.exists():
        _check(f"{_T} AC10: devcontainer/taskandi-harness.md exists", False, "missing")
        return
    text = read(_HARNESS)
    block = text
    first = next((l for l in text.split("\n") if l.strip()), None)
    _check(f"{_T} AC10: taskandi-harness.md starts with the exact skip string", first == SKIP, repr(first))
    _check(f"{_T} AC10: taskandi-harness.md carries no block markers (the whole file is the procedure)", START not in text and END not in text)
    df = read(_DOCKERFILE)
    line = "COPY --chown=root:root taskandi-harness.md /usr/local/share/vibe/taskandi-harness.md"
    ctx_i = df.find("codex/context.md")
    _check(f"{_T} AC10: the Dockerfile copies taskandi-harness.md to /usr/local/share/vibe/ next to the codex/context.md COPY",
           line in df and ctx_i >= 0 and abs(df.index(line) - ctx_i) < 600, "COPY line missing or not near codex/context.md")
    # the two command blocks are identical
    blocks = [block_of(read(p)) for p in _CMD.values() if not grammar_problems(read(p))]
    _check(f"{_T} AC10: the vss.md and vsss.md blocks are identical", len(blocks) == 2 and blocks[0] == blocks[1])
    cmds = fenced_commands(block)
    _check(f"{_T} AC10: {name}.md has a real set of fenced taskandi-client lines (>= 14; not vacuous)", len(cmds) >= 14, f"{len(cmds)} lines")
    with tempfile.TemporaryDirectory(prefix="hp-argv-") as td:
        cwd = Path(td)
        subprocess.run(["git", "init", "-q", str(cwd)], check=True, input="", capture_output=True, text=True)
        for line in cmds:
            r, argv = check_argv(line, cwd)
            _check(f"{_T} AC10: {name}.md: `{line[:90]}` passes --check-argv",
                   r.returncode == 0 and json.loads(r.stdout or "null") == {"ok": True} and "<" not in substitute(line),
                   f"rc={r.returncode} {r.stdout!r} {r.stderr[:200]!r} argv={argv}")
        for bad in ("taskandi-client enqueue ask --key k --bogus x", "taskandi-client decide --no-other-work yes", "taskandi-client release --task t --reason r --budget-stopped yes"):
            r, _ = check_argv(bad, cwd)
            _check(f"{_T} AC10 negative control: `{bad}` fails --check-argv", r.returncode == 1 and r.stdout == "", f"rc={r.returncode} {r.stdout!r}")
    used = {c.split()[1] for c in cmds if len(c.split()) > 1} | set(inline_commands(block))
    _check(f"{_T} AC10: {name}.md subcommand set is exactly status, next-task, enqueue, usage, flush, poll, decide, release, complete",
           used == SUBCOMMANDS, f"extra={sorted(used - SUBCOMMANDS)} missing={sorted(SUBCOMMANDS - used)}")
    seq = [(c.split()[1], c.split()[2] if c.split()[1] == "enqueue" else None) for c in cmds if len(c.split()) > 1]
    names = [x[0] for x in seq]
    try:
        u = names.index("usage")
        f = names.index("flush", u)
        p = names.index("poll", f)
        d = names.index("decide", p)
        ok = not (set(names[u:d]) & {"complete", "release", "next-task"})
        kinds = [x[1] for x in seq[:u]]
        _check(f"{_T} AC10: {name}.md boundary order: usage < flush < poll < decide with no complete/release/next-task between", ok, repr(names[u:d + 1]))
        _check(f"{_T} AC10: {name}.md boundary: the progress comment is enqueued before usage and record_time sits between usage and flush",
               "comment" in kinds and any(x == ("enqueue", "record_time") for x in seq[u:f]), repr(seq[max(0, u - 2):f + 1]))
    except ValueError as error:
        _check(f"{_T} AC10: {name}.md boundary order exists", False, str(error))
    dl = [c for c in cmds if c.split()[1:2] == ["decide"] and "--remaining-minutes" in c]
    _check(f"{_T} AC10: {name}.md has the boundary decide with --remaining-minutes and --windows-used", any("--windows-used" in c for c in dl), repr(dl))
    n = norm(block)
    for label, rx in _REQUIRED:
        _check(f"{_T} AC10: {name}.md contains {label}", re.search(rx, n) is not None, rx)
    rows = [norm(l).strip() for l in block.split("\n") if l.strip().startswith("|")]
    for label, rx in _ROWS:
        _check(f"{_T} AC10: {name}.md failure table has the row '{label}'", any(re.search(rx, r) for r in rows), repr(rows[:3]))
    steps = {k: re.search(rx, n) is not None for k, rx in (("1 Detect", r"Detect"), ("2 Pick work", r"Pick work"), ("3 Work", r"\bWork\b"), ("4 Ask", r"\bAsk\b"),
                                                             ("5 Boundary", r"Boundary"), ("6 Act on next", r"Act on"), ("7 Done", r"\bDone\b"))}
    _check(f"{_T} AC10: {name}.md names the seven procedure steps", all(steps.values()), repr(steps))
    # the commands themselves no longer carry the procedure
    for cname, path in _CMD.items():
        _check(f"{_T} AC10: {cname}.md carries no fenced taskandi-client lines (the procedure lives in taskandi-harness.md)", fenced_commands(read(path)) == [])


# ---------------------------------------------------------------------------
# AC11 Docs and gates
# ---------------------------------------------------------------------------

def _section(text: str, heading_rx: str, level: str) -> str:
    m = re.search(heading_rx, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(rf"^{level}\s", rest, re.M)
    return rest[:n.start()] if n else rest


def test_hp_ac11_docs_and_gates() -> None:
    print(f"{_T} AC11 docs and gates")
    docs = read(_REPO / "docs" / "taskandi-client.md")
    sec = _section(docs, r"^##\s+Harness integration[^\n]*$", "##")
    _check(f"{_T} AC11: docs/taskandi-client.md has a 'Harness integration' section", sec.strip() != "", "heading missing")
    sn = norm(sec)
    for label, rx in [("the decide command", r"decide"), ("the decide JSON (next, asks, unjudged, budget, reclaimed_parked, repoll)", r"\"next\".*asks.*unjudged.*budget.*reclaimed_parked.*repoll|next.*asks.*unjudged.*budget.*reclaimed_parked.*repoll"),
                      ("next values", r"release-again.*park-task|park-task.*release-again"), ("exit codes", r"[Ee]xit (code|0|1)|exits? (0|1)"),
                      ("the VIBE_TASKANDI_BUDGET_ASK knob with default 0.8", r"VIBE_TASKANDI_BUDGET_ASK.*0\.8|0\.8.*VIBE_TASKANDI_BUDGET_ASK"),
                      ("the failure table", r"\|\s*failure\s*\|"), ("the cost-estimate 0 limit", r"cost-estimate 0"), ("--resolve", r"--resolve"),
                      ("--body-max-chars", r"--body-max-chars"), ("--check-argv", r"--check-argv"), ("the Claude transcript importer", r"[Cc]laude")]:
        _check(f"{_T} AC11: docs 'Harness integration' covers {label}", re.search(rx, sn) is not None, rx)
    log = read(_REPO / "CHANGELOG.md")
    head = log[:60000]
    m = re.search(r"^- \[x\] \*\*[^\n]*task_065[^\n]*", head, re.M) or re.search(r"task_065", head)
    _check(f"{_T} AC11: CHANGELOG.md has a task_065 entry near the top", m is not None)
    if m:
        entry = head[m.start():m.start() + 6000]
        entry = entry.split("\n- [", 1)[0]
        _check(f"{_T} AC11: the CHANGELOG entry names decide, the harness commands and the reclaim guard / usage importer",
               "decide" in entry and re.search(r"vss", entry) and re.search(r"reclaim|usage|Claude transcript|importer", entry, re.I), entry[:200])
    mt = read(_REPO / "MANUAL-TESTS.md")
    sec = _section(mt, r"^###\s+Test 70[^\n]*$", "###")
    _check(f"{_T} AC11: MANUAL-TESTS.md has 'Test 70'", sec.strip() != "", "heading missing")
    mn = norm(sec)
    for label, rx in [("a bound /vsss run", r"/vsss"), ("the real service", r"real (Task&I )?service|real service"), ("vibe link", r"vibe link"),
                      ("unverified paths marked", r"unverified"), ("defaults_allowed false in production", r"defaults_allowed"), ("windows metering", r"windows")]:
        _check(f"{_T} AC11: MANUAL-TESTS Test 70 covers {label}", re.search(rx, mn) is not None, rx)
    # the smoke files respect the size policy and are registered
    for f in ("checks_53_taskandi_decide.py", "checks_54_harness_prose.py"):
        n = len(read(_REPO / "smoke" / f).splitlines())
        _check(f"{_T} AC11: smoke/{f} is at most 1,500 lines ({n})", n <= 1500)
    runner = read(_REPO / "smoke" / "runner.py")
    _check(f"{_T} AC11: runner.py imports both new parts",
           "checks_53_taskandi_decide" in runner and "checks_54_harness_prose" in runner, "not registered")
    for fn in re.findall(r"^def (test_(?:td|hp)_\w+)", read(_REPO / "smoke" / "checks_53_taskandi_decide.py") + read(_REPO / "smoke" / "checks_54_harness_prose.py"), re.M):
        _check(f"{_T} AC11: runner.main() calls {fn}", f"    {fn}()" in runner, fn)


_TESTS = [test_hp_ac9_structure, test_hp_ac10_commands, test_hp_ac11_docs_and_gates]


def _run_all() -> None:
    for fn in _TESTS:
        try:
            fn()
        except Exception as error:  # a crashed test is a failed test, never a silent pass
            _check(f"{_T} {fn.__name__} raised", False, repr(error))


if __name__ == "__main__":
    _run_all()
    passed = sum(_RESULTS)
    print(f"total: {len(_RESULTS)} passed: {passed} failed: {len(_RESULTS) - passed}")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        raise SystemExit(1)
    print("PASS: task_065 harness prose acceptance checks")
