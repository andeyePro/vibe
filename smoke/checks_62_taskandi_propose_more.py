#!/usr/bin/env python3
"""Acceptance checks for task_067 part 2: AC7-AC14 and the Rev 2.1 points (B1/B2, time zones, gone entries, idempotent re-enqueue).

Tester-owned (cycle 1).  Harness and helpers come from ``checks_61_taskandi_propose.py``.

Run only this module with:
    python3 smoke/checks_62_taskandi_propose_more.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _CLIENT, _FIX_BRAIN, _T1, _check
from smoke.checks_55_taskandi_http_review import _edit_state
from smoke.checks_58_taskandi_v23 import R25, V, safe
from smoke.checks_61_taskandi_propose import (DAY, _FIX25, create_applied, entry, ledger, make, pay, propose, rp, text)

_REPO = Path(__file__).resolve().parent.parent
_T = "[taskandi-propose]"
__all__ = ["test_prop_ac7_ledger", "test_prop_ac8_duplicates_caps", "test_prop_ac9_self_dispatch", "test_prop_ac10_update_targets",
           "test_prop_ac12_harness", "test_prop_ac14_docs_fixtures"]
LEDGER_KEYS = {"key", "task_id", "title", "titleNorm", "assign", "parent", "agent", "repeat", "session", "at", "gone"}
CREATED_KEYS = {"key", "task_id", "title", "assign", "parent", "repeat", "gone", "at"}


def set_ledger(hx: V, fn) -> None:
    _edit_state(hx, lambda s: fn(s.setdefault("created", [])))


def created(hx: V, *args: str) -> dict:
    r = hx.run("created", *args)
    return r.json() or {}


# ---------------------------------------------------------------------------
# AC7 Ledger
# ---------------------------------------------------------------------------

@safe
def test_prop_ac7_ledger() -> None:
    print(f"{_T} AC7 ledger")
    with V(R25) as hx:
        tid = make(hx, "L1", "  Check, The   Agenda!! ", ids=["led-1"])
        e = entry(hx, tid)
        _check(f"{_T} AC7: the done job wrote one ledger entry with exactly the documented fields", set(e) == LEDGER_KEYS and len(ledger(hx)) == 1, repr(e))
        _check(f"{_T} AC7: entry values: key, task_id, title as sent, titleNorm lower-cased/collapsed/punctuation-trimmed, assign, agent, repeat false, gone false, at = clock",
               e.get("key") == "L1" and e.get("task_id") == "led-1" and e.get("title") == "  Check, The   Agenda!! " and e.get("titleNorm") == "check, the agenda"
               and e.get("assign") == "owner" and e.get("agent") == "claude" and e.get("repeat") is False and e.get("gone") is False and e.get("at") == _T1, repr(e))
        tid2 = make(hx, "L2", "Weekly agenda", assign="agent", ids=["led-2"], parent="project", repeat=rp())
        e2 = entry(hx, tid2)
        _check(f"{_T} AC7: a repeat/agent/parent creation records repeat true, assign agent, parent", e2.get("repeat") is True and e2.get("assign") == "agent" and e2.get("parent") == "project", repr(e2))
        # a refused job writes no entry
        hx.set(errors={"create_task": {"status": 409, "json": {"error": "invalid_request"}, "times": 1}})
        make(hx, "L3", "Refused one")
        _check(f"{_T} AC7: a refused create writes no ledger entry", len(ledger(hx)) == 2, repr(ledger(hx))[:200])
        hx.set(errors=None)
        # pruning of 2100 done jobs never touches the ledger
        hx.claim("project", "s1")
        hx.run("enqueue", "comment", "--key", "seed", "--task", "project", stdin=json.dumps({"text": "x"}))
        hx.run("flush")
        seed = copy.deepcopy(hx.job("seed"))

        def stuff(s):
            jobs = []
            for i in range(2100):
                j = copy.deepcopy(seed)
                j.update(key=f"c{i}", doneAtMs=_T1 - 10 * DAY + i, state="done")
                jobs.append(j)
            s["jobs"] = jobs
        _edit_state(hx, stuff)
        r = hx.run("enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        keys = {j["key"] for j in hx.jobs()}
        _check(f"{_T} AC7: control - pruning happened (oldest done jobs gone)", r.rc == 0 and "c0" not in keys and "c2099" in keys, r.show())
        _check(f"{_T} AC7: the ledger survives pruning of 2100 jobs (both entries intact)", {x.get("task_id") for x in ledger(hx)} == {"led-1", "led-2"}, repr(ledger(hx))[:200])
        # 180 days
        def age(c):
            for x in c:
                x["at"] = _T1 - (181 if x["task_id"] == "led-1" else 179) * DAY
        set_ledger(hx, age)
        hx.run("enqueue", "comment", "--key", "touch", "--task", "project", stdin=json.dumps({"text": "u"}))
        hx.run("flush")
        ids = {x.get("task_id") for x in ledger(hx)}
        _check(f"{_T} AC7: an entry older than 180 days is dropped, one 179 days old is kept (injected clock)", ids == {"led-2"}, repr(ids))
    # wrong_scope / not_assigned
    with V(R25) as hx:
        a = make(hx, "A", "Update me wrong scope", ids=["ws-1"])
        b = make(hx, "B", "Update me not assigned", ids=["na-1"])
        hx.set(wrongScopeTasks=[a], notAssigned=[b])
        hx.run("enqueue", "update_task", "--key", "uA", stdin=json.dumps({"task": a, "title": "x"}))
        hx.run("enqueue", "update_task", "--key", "uB", stdin=json.dumps({"task": b, "title": "x"}))
        hx.run("flush")
        _check(f"{_T} AC7: wrong_scope on an update marks the ledger entry gone", entry(hx, a).get("gone") is True and (hx.job("uA") or {}).get("state") != "done", repr(entry(hx, a)) + repr(hx.job("uA"))[:200])
        _check(f"{_T} AC7: not_assigned does not mark the entry gone", entry(hx, b).get("gone") is False and (hx.job("uB") or {}).get("state") != "done", repr(entry(hx, b)) + repr(hx.job("uB"))[:200])
        r = hx.run("enqueue", "update_task", "--key", "uA2", stdin=json.dumps({"task": a, "title": "again"}))
        _check(f"{_T} AC7: a gone entry is no longer an allowed update target", r.rc == 1 and "update_task: not your task" in text(r) and hx.job("uA2") is None, r.show())
    with V(R25) as hx:
        p = make(hx, "P", "Parent to be removed", ids=["par-1"])
        hx.set(badParents=[p])
        make(hx, "C", "Child of removed parent", parent=p)
        _check(f"{_T} AC7: wrong_scope on a create naming a ledger parent marks the parent entry gone", entry(hx, p).get("gone") is True and (hx.job("C") or {}).get("state") != "done", repr(entry(hx, p)))
    # created command
    with V(R25) as hx:
        a = make(hx, "A", "Alpha task", ids=["cr-a"])
        b = make(hx, "B", "Beta task", ids=["cr-b"], parent="project", assign="agent")
        c = make(hx, "C", "Gamma removed", ids=["cr-c"])
        set_ledger(hx, lambda l: [x.update(gone=True) for x in l if x["task_id"] == "cr-c"])
        hx.clear()
        out = created(hx)
        ids = [x.get("task_id") for x in out.get("created", [])]
        _check(f"{_T} AC7: created lists non-gone entries only, {{bound: true, created: [...]}}, entries have exactly the documented fields",
               out.get("bound") is True and sorted(ids) == ["cr-a", "cr-b"] and all(set(x) == CREATED_KEYS for x in out.get("created", [])), repr(out)[:400])
        _check(f"{_T} AC7: created works offline (zero requests)", not hx.reqs(), repr(hx.actions()))
        out = created(hx, "--all")
        _check(f"{_T} AC7: created --all includes gone entries (gone: true)", sorted(x["task_id"] for x in out.get("created", [])) == ["cr-a", "cr-b", "cr-c"]
               and [x for x in out["created"] if x["task_id"] == "cr-c"][0]["gone"] is True, repr(out)[:400])
        out = created(hx, "--task", "project")
        _check(f"{_T} AC7: created --task REF shows only entries whose parent is REF", [x["task_id"] for x in out.get("created", [])] == ["cr-b"], repr(out)[:300])
        out = created(hx, "--task", "project", "--all")
        _check(f"{_T} AC7: created --task REF --all combines", [x["task_id"] for x in out.get("created", [])] == ["cr-b"], repr(out)[:300])
        out = created(hx, "--task", "nowhere")
        _check(f"{_T} AC7: created --task with no match prints an empty list", out.get("created") == [] and out.get("bound") is True, repr(out))
    with V(R25) as hx:
        out = created(hx)
        _check(f"{_T} AC7: created on a project with no ledger prints an empty list, exit 0", out.get("created") == [] and out.get("bound") is True, repr(out))


# ---------------------------------------------------------------------------
# AC8 Duplicates and caps
# ---------------------------------------------------------------------------

@safe
def test_prop_ac8_duplicates_caps() -> None:
    print(f"{_T} AC8 duplicates and caps")
    with V(R25) as hx:
        make(hx, "d0", "Check the agenda", ids=["dup-1"])
        for i, t in enumerate(("check the AGENDA", "  Check   the   agenda  ", "Check the agenda!!!", "(Check the agenda).", "CHECK THE AGENDA?")):
            hx.clear()
            r = propose(hx, f"dn{i}", pay(t))
            _check(f"{_T} AC8: {t!r} is a duplicate_proposal of the ledger entry (exit 1, no job, nothing sent)", r.rc == 1 and "duplicate_proposal" in text(r) and hx.job(f"dn{i}") is None and not hx.reqs(), r.show())
        r = propose(hx, "dok1", pay("Check the agenda soon"))
        _check(f"{_T} AC8 control: a different title is accepted", r.rc == 0 and hx.job("dok1") is not None, r.show())
        r = propose(hx, "dok2", pay("Check the agenda", parent="leaf-b"))
        _check(f"{_T} AC8 control: the same title under another parent is accepted", r.rc == 0 and hx.job("dok2") is not None, r.show())
        # a queued create (no ledger entry yet) blocks too
        r = propose(hx, "dq", pay("Check the agenda soon!"))
        _check(f"{_T} AC8: a create job not yet in the ledger (queued) blocks a duplicate", r.rc == 1 and "duplicate_proposal" in text(r) and hx.job("dq") is None, r.show())
        # Rev 2.1: idempotent re-enqueue first
        r1 = propose(hx, "dok1", pay("Check the agenda soon"))
        j = (r1.json() or {})
        _check(f"{_T} AC8 Rev2.1: re-enqueueing the same key and payload deduplicates (exit 0, one job) before the duplicate check",
               r1.rc == 0 and j.get("deduplicated") is True and len([x for x in hx.jobs() if x["key"] == "dok1"]) == 1, r1.show())
        hx.run("flush")
        r2 = propose(hx, "d0", pay("Check the agenda"))
        _check(f"{_T} AC8 Rev2.1: re-enqueueing a DONE key with the same payload deduplicates, not duplicate_proposal", r2.rc == 0 and (r2.json() or {}).get("deduplicated") is True, r2.show())
        r3 = propose(hx, "d0", pay("Check the agenda", notes="different"))
        _check(f"{_T} AC8 control: the same done key with another payload is not accepted as a new job", len([x for x in hx.jobs() if x["key"] == "d0"]) <= 1 and (r3.rc != 0 or (r3.json() or {}).get("enqueued") is not True), r3.show())
        # gone entries still block
        set_ledger(hx, lambda l: [x.update(gone=True) for x in l if x["task_id"] == "dup-1"])
        r = propose(hx, "dg", pay("check the agenda"))
        _check(f"{_T} AC8 Rev2.1: an entry the owner removed (gone) still blocks re-proposal", r.rc == 1 and "duplicate_proposal" in text(r) and hx.job("dg") is None, r.show())
        _check(f"{_T} AC8 Rev2.1: created --all still shows the removed entry", any(x["task_id"] == "dup-1" for x in created(hx, "--all").get("created", [])), "")
    # session cap and rolling 24 h cap
    with V(R25) as hx:
        for i in range(3):
            make(hx, f"A{i}", f"Stamp A task {i}", stamp="A")
        r = propose(hx, "A3", pay("Stamp A task 3"), stamp="A")
        _check(f"{_T} AC8: the 4th creation under one session stamp is refused proposal_cap (exit 1, no job)", r.rc == 1 and "proposal_cap" in text(r) and hx.job("A3") is None, r.show())
        for stamp, n in (("B", 3), ("C", 3), ("D", 1)):
            for i in range(n):
                make(hx, f"{stamp}{i}", f"Stamp {stamp} task {i}", stamp=stamp)
        _check(f"{_T} AC8: the refused enqueue did not count (10 accepted afterwards, server holds 10)", len(create_applied(hx)) == 10 and len(ledger(hx)) == 10, f"{len(create_applied(hx))} {len(ledger(hx))}")
        r = propose(hx, "E0", pay("Eleventh in a day"), stamp="E")
        _check(f"{_T} AC8: the 11th creation in 24 hours is refused proposal_cap even under a fresh stamp", r.rc == 1 and "proposal_cap" in text(r) and hx.job("E0") is None, r.show())
        r = propose(hx, "E1", pay("Eleventh via env stamp"), env={"VIBE_SESSION_STAMP": "F"})
        _check(f"{_T} AC8: nor does VIBE_SESSION_STAMP evade the rolling cap", r.rc == 1 and "proposal_cap" in text(r), r.show())
        later = _T1 + 25 * 3600000
        r = propose(hx, "E2", pay("A day later"), stamp="G", now=later)
        _check(f"{_T} AC8: more than 24 hours later the rolling cap has room again", r.rc == 0 and hx.job("E2") is not None, r.show())
    with V(R25) as hx:
        for i in range(3):
            make(hx, f"S{i}", f"Env stamp task {i}", env={"VIBE_SESSION_STAMP": "ENVS"})
        r = propose(hx, "S3", pay("Env stamp task 3"), env={"VIBE_SESSION_STAMP": "ENVS"})
        _check(f"{_T} AC8: VIBE_SESSION_STAMP counts like --session (4th refused proposal_cap)", r.rc == 1 and "proposal_cap" in text(r), r.show())
    # repeat cap
    with V(R25) as hx:
        for i in range(3):
            make(hx, f"R{i}", f"Repeating task {i}", stamp=f"RS{i}", repeat=rp())
        hx.clear()
        r = propose(hx, "R3", pay("Repeating task 3", repeat=rp()), stamp="RS9")
        _check(f"{_T} AC8: a 4th outstanding repeat creation is refused repeat_cap (exit 1, no job)", r.rc == 1 and "repeat_cap" in text(r) and hx.job("R3") is None, r.show())
        r = propose(hx, "P1", pay("Plain task while repeats are capped"), stamp="RS9")
        _check(f"{_T} AC8 control: a non-repeat creation is still accepted", r.rc == 0 and hx.job("P1") is not None, r.show())
        set_ledger(hx, lambda l: [x.update(gone=True) for x in l if x["key"] == "R0"])
        r = propose(hx, "R4", pay("Repeating task 4", repeat=rp()), stamp="RS8")
        _check(f"{_T} AC8: a gone repeat entry no longer counts toward repeat_cap", r.rc == 0 and hx.job("R4") is not None, r.show())


# ---------------------------------------------------------------------------
# AC9 Self-dispatch (and B2)
# ---------------------------------------------------------------------------

@safe
def test_prop_ac9_self_dispatch() -> None:
    print(f"{_T} AC9 self-dispatch")
    with V(R25) as hx:
        make(hx, "ag", "Agent follow-up", assign="agent", ids=["agent-task-1"])
        _check(f"{_T} AC9 setup: the ledger holds an assign=agent entry", entry(hx, "agent-task-1").get("assign") == "agent", repr(ledger(hx)))
        hx.clear()
        r = hx.run("next-task", "--agent", "claude", "--session", "s1", "--task", "agent-task-1")
        out = r.json() or {}
        _check(f"{_T} AC9: next-task --task <ledger agent task> prints task null, reason self_created, with zero next_task requests and no claim",
               out.get("task", 0) is None and out.get("reason") == "self_created" and hx.count("next_task") == 0 and hx.claimed() is None, r.show() + repr(hx.actions()))
        hx.set(offerTask="agent-task-1")
        hx.clear()
        r = hx.run("next-task", "--agent", "claude", "--session", "s1")
        out = r.json() or {}
        rel = hx.bodies("release")
        _check(f"{_T} AC9: A-mode, the server offers the ledger agent task: it is released with the documented reason and self_created is printed",
               out.get("task", 0) is None and out.get("reason") == "self_created" and len(rel) == 1 and rel[0].get("task") == "agent-task-1"
               and "vibe does not work tasks it proposed until the owner assigns it" in str(rel[0].get("reason")) and hx.claimed() is None, r.show() + repr(rel)[:300])
        hx.set(offerTask="other-task-9")
        hx.clear()
        r = hx.run("next-task", "--agent", "claude", "--session", "s2")
        _check(f"{_T} AC9 control: a task that is not in the ledger is claimed as today", (hx.claimed() or {}).get("task") == "other-task-9" and hx.count("release") == 0, r.show() + repr(hx.claimed())[:200])
    with V(R25) as hx:
        make(hx, "ow", "Owner task the owner reassigned", assign="owner", ids=["owner-task-1"])
        hx.set(offerTask="owner-task-1")
        r = hx.run("next-task", "--agent", "claude", "--session", "s1")
        _check(f"{_T} AC9 B2: a ledger entry with assign owner that the server offers is claimed normally", (hx.claimed() or {}).get("task") == "owner-task-1" and hx.count("release") == 0, r.show() + repr(hx.claimed())[:200])
    with V(R25) as hx:
        make(hx, "ow", "Owner task by name", assign="owner", ids=["owner-task-2"])
        hx.clear()
        r = hx.run("next-task", "--agent", "claude", "--session", "s1", "--task", "owner-task-2")
        _check(f"{_T} AC9 B2: next-task --task <ledger owner task> sends the claim and claims it", hx.count("next_task") == 1 and (hx.claimed() or {}).get("task") == "owner-task-2", r.show())
    with V(R25) as hx:
        make(hx, "ag", "Gone agent task", assign="agent", ids=["agent-task-2"])
        set_ledger(hx, lambda l: [x.update(gone=True) for x in l])
        r = hx.run("next-task", "--agent", "claude", "--session", "s1", "--task", "agent-task-2")
        out = r.json() or {}
        _check(f"{_T} AC9: even a gone agent entry is not self-dispatched (still self_created, zero next_task requests)", out.get("reason") == "self_created" and hx.count("next_task") == 0, r.show())


# ---------------------------------------------------------------------------
# AC10 update_task targets
# ---------------------------------------------------------------------------

@safe
def test_prop_ac10_update_targets() -> None:
    print(f"{_T} AC10 update_task targets")
    msg = "update_task: not your task"
    with V(R25) as hx:
        own = make(hx, "own", "My own proposal", ids=["mine-1"])
        cod = make(hx, "cod", "Codex's proposal", ids=["codex-1"], env={"VIBE_AGENT": "codex"})
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "e1", stdin=json.dumps({"task": "project", "title": "x"}))
        _check(f"{_T} AC10: the effective-but-unclaimed task is refused locally (exit 1, no job, zero requests)", r.rc == 1 and msg in text(r) and hx.job("e1") is None and not hx.reqs(), r.show())
        hx.claim("leaf-b", "session-a")
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "e2", stdin=json.dumps({"task": "project", "title": "x"}))
        _check(f"{_T} AC10: with a claim on leaf-b, naming another task is still refused", r.rc == 1 and msg in text(r) and hx.job("e2") is None and not hx.reqs(), r.show())
        r = hx.run("enqueue", "update_task", "--key", "e3", stdin=json.dumps({"task": cod, "title": "x"}))
        _check(f"{_T} AC10: another persona's ledger entry is refused locally with zero requests", r.rc == 1 and msg in text(r) and hx.job("e3") is None and not hx.reqs(), r.show())
        r = hx.run("enqueue", "update_task", "--key", "e4", stdin=json.dumps({"task": "never-seen", "title": "x"}))
        _check(f"{_T} AC10: an unknown task is refused locally", r.rc == 1 and msg in text(r) and hx.job("e4") is None, r.show())
        # allowed
        r = hx.run("enqueue", "update_task", "--key", "ok1", stdin=json.dumps({"task": "leaf-b", "next_action": "Keep the claim current"}))
        r2 = hx.run("enqueue", "update_task", "--key", "ok2", stdin=json.dumps({"task": own, "title": "Better title"}))
        _check(f"{_T} AC10: the claimed task and the agent's own ledger entry are allowed", r.rc == 0 and r2.rc == 0 and hx.job("ok1") and hx.job("ok2"), r.show() + r2.show())
        hx.clear()
        hx.run("flush")
        b1 = [b for b in hx.bodies("update_task") if b.get("task") == "leaf-b"]
        b2 = [b for b in hx.bodies("update_task") if b.get("task") == own]
        _check(f"{_T} AC10: session is sent exactly when the target is the claimed task",
               len(b1) == 1 and b1[0].get("session") == "session-a" and len(b2) == 1 and "session" not in b2[0], repr(hx.bodies("update_task"))[:400])
        # a ledger entry whose create job is not done
        _edit_state(hx, lambda s: next(j for j in s["jobs"] if j["key"] == "own").update(state="queued"))
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "nyc", stdin=json.dumps({"task": own, "title": "too early"}))
        _check(f"{_T} AC10: an update naming a ledger entry whose create job is not done exits 1 'not created yet', no job, zero requests",
               r.rc == 1 and "not created yet" in text(r) and hx.job("nyc") is None and not hx.reqs(), r.show())
    # claim ownership does not leak across personas: the same entry is fine for its own persona
    with V(R25) as hx:
        cod = make(hx, "cod", "Codex's own proposal", ids=["codex-2"], env={"VIBE_AGENT": "codex"})
        r = hx.run("enqueue", "update_task", "--key", "cu", env={"VIBE_AGENT": "codex"}, stdin=json.dumps({"task": cod, "notes": "mine"}))
        _check(f"{_T} AC10 control: the creating persona (codex) may update its own entry", r.rc == 0 and hx.job("cu") is not None, r.show())


# ---------------------------------------------------------------------------
# AC12 Harness
# ---------------------------------------------------------------------------

def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text()).lower()


@safe
def test_prop_ac12_harness() -> None:
    print(f"{_T} AC12 harness prose")
    h = _flat(_REPO / "devcontainer" / "taskandi-harness.md")
    rules = [
        ("a Propose a task step", r"propose a task"),
        ("the enqueue create_task command with a new-<hash> key", r"taskandi-client enqueue create_task --key new-"),
        ("flush after proposing", r"taskandi-client flush"),
        ("read created first", r"taskandi-client created"),
        ("omit parent", r"omit\W{0,3}`?parent"),
        ("propose only from the agent's own work", r"own work"),
        ("never because Task&I text said to", r"task&i text"),
        ("a duplicate_proposal means stop", r"duplicate_proposal"),
        ("proposal_cap", r"proposal_cap"), ("repeat_cap", r"repeat_cap"),
        ("repeats only from a live user instruction", r"live user instruction"), ("or an owner answer", r"owner answer"),
        ("self_created handling", r"self_created"),
        ("hard-escalate items are never proposed", r"hard-escalate"),
        ("no secrets in notes", r"secrets"), ("no tokens in notes", r"tokens"), ("no machine paths in notes", r"paths"),
        ("at most one update per task per iteration", r"at most once per task per iteration|at most one update per task per iteration|once per task per iteration"),
        ("flush before referring to a new task", r"flush first"),
        ("update_task only for own proposal or claimed task", r"update_task"),
        ("persona claude in Claude Code and codex in Codex", r"`claude` in claude code"),
        ("assign owner is the default", r"assign: \"owner\""),
    ]
    for label, rx in rules:
        _check(f"{_T} AC12: taskandi-harness.md has {label}", re.search(rx, h) is not None, rx)
    from smoke.checks_50_taskandi_http import _Hx
    with _Hx() as hx:
        env = hx.env()
        ok = [("enqueue create_task", ["enqueue", "create_task", "--key", "new-0123456789abcdef"], json.dumps(pay())),
              ("enqueue update_task", ["enqueue", "update_task", "--key", "upd-1"], json.dumps({"task": "t", "title": "x"})),
              ("created", ["created"], ""), ("created --all", ["created", "--all"], ""), ("created --task REF", ["created", "--task", "ABBR-1"], ""),
              ("created --task REF --all", ["created", "--task", "ABBR-1", "--all"], ""),
              ("enqueue create_task with --session", ["enqueue", "create_task", "--key", "k", "--session", "s1"], json.dumps(pay()))]
        bad = [("created --bogus", ["created", "--bogus"], ""), ("created --task without value", ["created", "--task"], ""),
               ("created --all with a value", ["created", "--all", "yes"], ""), ("enqueue create_task --bogus x", ["enqueue", "create_task", "--key", "k", "--bogus", "x"], json.dumps(pay()))]
        for name, argv, stdin in ok:
            r = subprocess.run(["node", str(_CLIENT), "--check-argv", *argv], cwd=str(hx.repo), input=stdin, capture_output=True, text=True, timeout=60, env=env)
            _check(f"{_T} AC12: --check-argv accepts {name}", r.returncode == 0 and json.loads(r.stdout or "null") == {"ok": True}, f"rc={r.returncode} {r.stdout!r} {r.stderr[:200]!r}")
        for name, argv, stdin in bad:
            r = subprocess.run(["node", str(_CLIENT), "--check-argv", *argv], cwd=str(hx.repo), input=stdin, capture_output=True, text=True, timeout=60, env=env)
            _check(f"{_T} AC12: --check-argv rejects {name}", r.returncode == 1 and r.stdout == "" and r.stderr.strip() != "", f"rc={r.returncode} {r.stdout!r} {r.stderr[:200]!r}")
        _check(f"{_T} AC12: --check-argv made no network call", not hx.reqs(), repr(hx.actions()))


# ---------------------------------------------------------------------------
# AC14 Docs, fixtures
# ---------------------------------------------------------------------------

@safe
def test_prop_ac14_docs_fixtures() -> None:
    print(f"{_T} AC14 docs and fixtures")
    names = ["capabilities", "create_task", "create_task_agent", "create_task_refusals", "create_task_repeat", "update_task", "update_task_clear_repeat"]
    prov = _FIX25 / "PROVENANCE.md"
    prov_text = prov.read_text() if prov.exists() else ""
    for n in names:
        p = _FIX25 / f"{n}.json"
        _check(f"{_T} AC14: smoke/fixtures/taskandi-v25/{n}.json exists", p.exists(), str(p))
        if p.exists():
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            _check(f"{_T} AC14: PROVENANCE.md lists the sha256 of {n}.json", sha in prov_text, sha)
            # No live-brain2 comparison (it drifts as Task&I recopies); the sha256 pin fixes the bytes.
    doc = (_REPO / "docs" / "taskandi-client.md").read_text()
    sec = re.search(r"^#+ .*Proposing tasks.*$", doc, re.M)
    body = doc[sec.end():sec.end() + 12000].lower() if sec else ""
    _check(f"{_T} AC14: docs/taskandi-client.md has a 'Proposing tasks' section", sec is not None, "")
    for term in ("weekdays", "proposal_cap", "repeat_cap", "self_created", "duplicate_proposal", "24 hours", "created"):
        _check(f"{_T} AC14: the Proposing tasks section mentions {term}", term in body, term)
    mt = (_REPO / "MANUAL-TESTS.md").read_text()
    _check(f"{_T} AC14: MANUAL-TESTS.md has Test 71", re.search(r"Test 71\b", mt) is not None and "Keep" in mt, "")
    cl = (_REPO / "CHANGELOG.md").read_text()
    _check(f"{_T} AC14: CHANGELOG.md has a create_task / task_067 entry", "task_067" in cl or "create_task" in cl, "")
    runner = (_REPO / "smoke" / "runner.py").read_text()
    for mod in ("checks_61_taskandi_propose", "checks_62_taskandi_propose_more"):
        _check(f"{_T} AC14: {mod} is registered in runner.py", f"from smoke.{mod} import *" in runner, "")
    for f in ("checks_61_taskandi_propose.py", "checks_62_taskandi_propose_more.py"):
        n = len((_REPO / "smoke" / f).read_text().splitlines())
        _check(f"{_T} AC14: {f} is at most 1500 lines ({n})", n <= 1500, str(n))


def main() -> int:
    for fn in (test_prop_ac7_ledger, test_prop_ac8_duplicates_caps, test_prop_ac9_self_dispatch, test_prop_ac10_update_targets, test_prop_ac12_harness, test_prop_ac14_docs_fixtures):
        fn()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
