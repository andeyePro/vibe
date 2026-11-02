#!/usr/bin/env python3
"""Acceptance checks for task_067 (vibe proposes tasks: create_task / update_task / repeat), part 1: AC1-AC6.

Tester-owned (cycle 1).  Part 2 (AC7-AC14, Rev 2.1) is ``checks_62_taskandi_propose_more.py``, which reuses the harness here.

Harness.  The real client runs against ``smoke/taskandi_v23_server.mjs``.  The fake service answers ``create_task`` and
``update_task`` on v2.4 and later (``repeat`` on v2.5 only), replays writes per connection by ``request_id``, refuses with
``wrong_scope`` / ``not_assigned`` / closed / ``receipt_collision``, and validates ``repeat`` with its OWN validator written
from the README and the brief (it shares no code with the client).  Every applied write is logged, so "exactly one task" is
a count of server-side applications.  Commands run through ``dc`` with the injected clock ``_T1``.

Run only this module with:
    python3 smoke/checks_61_taskandi_propose.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _CONN, _FIX_BRAIN, _T1, _Hx, _Res, _check
from smoke.checks_55_taskandi_http_review import _edit_state
from smoke.checks_58_taskandi_v23 import R23, R24, R25, UUID4, V, safe

_REPO = Path(__file__).resolve().parent.parent
_FIX25 = _REPO / "smoke" / "fixtures" / "taskandi-v25"
_T = "[taskandi-propose]"
__all__ = ["test_prop_ac1_wire", "test_prop_ac2_payload", "test_prop_ac3_repeat", "test_prop_ac4_gating", "test_prop_ac5_resend_reconcile",
           "test_prop_ac6_results"]
DAY = 86400000


def f25(name: str) -> dict:
    d = _FIX25 if (_FIX25 / f"{name}.json").exists() else _FIX_BRAIN   # dev fallback; AC14 requires the in-repo copy
    return json.loads((d / f"{name}.json").read_text())


# -- helpers shared with part 2 ------------------------------------------------

def text(res: _Res) -> str:
    return res.out + res.err


def pay(title="Look at the agenda", assign="owner", **extra) -> dict:
    return {"title": title, "estimate_minutes": 10, "assign": assign, **extra}


def propose(hx: V, key: str, payload, stamp=None, now=_T1, env=None) -> _Res:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return hx.run("enqueue", "create_task", "--key", key, *(["--session", stamp] if stamp else []), stdin=raw, now=now, env=env)


def make(hx: V, key: str, title: str, assign="owner", ids=None, env=None, stamp=None, now=_T1, **extra):
    """Enqueue a create_task, flush, and return the server-assigned task id (None if it was not made)."""
    if ids:
        hx.set(createIds={**(hx.ctl.get('createIds') if isinstance(hx.ctl.get('createIds'), dict) else {}), title: ids[0]})
    r = propose(hx, key, pay(title, assign, **extra), stamp=stamp, now=now, env=env)
    if r.rc != 0:
        return None
    hx.run("flush", now=now, env=env)
    return ((hx.job(key) or {}).get("result") or {}).get("task_id")


def ledger(hx: V) -> list:
    return (hx.state() or {}).get("created") or []


def entry(hx: V, task_id: str) -> dict:
    return next((e for e in ledger(hx) if e.get("task_id") == task_id), {})


def wipe(hx: V, keep_ledger=True) -> None:
    def f(s):
        s["jobs"] = []
        s["tombstones"] = []
        if not keep_ledger:
            s["created"] = []
    if hx.state() is not None:
        _edit_state(hx, f)


def create_applied(hx: V) -> list:
    return hx.applied("create_task")


def mcp_hx() -> _Hx:
    hx = _Hx(bound=False)
    (hx.vibe / "taskandi.json").write_text(json.dumps({"endpoint": "https://fixture.invalid/mcp", "task": "ABBR-1"}))
    return hx


def fixture_payload(name: str) -> dict:
    return {k: v for k, v in f25(name)["request"].items() if k not in ("action", "agent", "session", "request_id")}


def same_wire(body: dict, want: dict) -> bool:
    drop = ("connection", "request_id")
    return {k: v for k, v in body.items() if k not in drop} == {k: v for k, v in want.items() if k not in drop}


# ---------------------------------------------------------------------------
# AC1 Wire (+ AC11 parity)
# ---------------------------------------------------------------------------

@safe
def test_prop_ac1_wire() -> None:
    print(f"{_T} AC1 wire per fixture")
    with V(R25) as hx:
        fx = f25("create_task")
        hx.set(createIds=[fx["response"]["task_id"]])
        r = propose(hx, "k1", fixture_payload("create_task"))
        job0 = hx.job("k1") or {}
        _check(f"{_T} AC1 create_task: enqueue ok, requestId is a UUID v4 stored outside the payload",
               r.rc == 0 and UUID4.match(job0.get("requestId", "")) and "request_id" not in job0.get("payload", {}), r.show() + repr(job0)[:200])
        hx.clear()
        hx.run("flush")
        bodies = hx.bodies("create_task")
        _check(f"{_T} AC1 create_task: one request; frozen body = fixture request (agent claude, no session), connection added",
               len(bodies) == 1 and same_wire(bodies[0], fx["request"]) and bodies[0].get("connection") == _CONN and bodies[0].get("request_id") == job0.get("requestId"),
               repr(bodies)[:400])
        job = hx.job("k1") or {}
        _check(f"{_T} AC1 create_task: done, stored result equals the fixture response, sentBody is the wire bytes",
               job.get("state") == "done" and job.get("result") == fx["response"] and job.get("sentBody") == (hx.raws("create_task") or [""])[0], repr(job)[:400])
        _check(f"{_T} AC1 create_task: the server holds exactly one task", len(create_applied(hx)) == 1, "")
        up = f25("update_task")
        hx.set(updateIds=[up["response"]["update_id"]])
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "u1", stdin=json.dumps(fixture_payload("update_task")))
        hx.run("flush")
        bodies = hx.bodies("update_task")
        job = hx.job("u1") or {}
        _check(f"{_T} AC1 update_task: frozen body = fixture request (no session: the target is not the claimed task); result = fixture response",
               r.rc == 0 and len(bodies) == 1 and same_wire(bodies[0], up["request"]) and "session" not in bodies[0] and job.get("state") == "done" and job.get("result") == up["response"],
               r.show() + repr(bodies)[:300] + repr(job)[:200])
    with V(R25) as hx:
        fx, up = f25("create_task_repeat"), f25("update_task_clear_repeat")
        hx.set(createIds=[fx["response"]["task_id"]], updateIds=[up["response"]["update_id"]])
        r = propose(hx, "k2", fixture_payload("create_task_repeat"))
        hx.clear()
        hx.run("flush")
        bodies = hx.bodies("create_task")
        job = hx.job("k2") or {}
        _check(f"{_T} AC1 create_task_repeat: frozen body = fixture request; repeat sent verbatim; result = fixture response",
               r.rc == 0 and len(bodies) == 1 and same_wire(bodies[0], fx["request"]) and bodies[0].get("repeat") == fx["request"]["repeat"] and job.get("result") == fx["response"],
               r.show() + repr(bodies)[:400])
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "u2", stdin=json.dumps(fixture_payload("update_task_clear_repeat")))
        hx.run("flush")
        bodies = hx.bodies("update_task")
        job = hx.job("u2") or {}
        _check(f"{_T} AC1 update_task_clear_repeat: body has repeat null and equals the fixture request; result = fixture response",
               r.rc == 0 and len(bodies) == 1 and same_wire(bodies[0], up["request"]) and "repeat" in bodies[0] and bodies[0]["repeat"] is None and job.get("result") == up["response"],
               r.show() + repr(bodies)[:300])
    with V(R25) as hx:
        fx = f25("create_task_agent")
        hx.claim("leaf-b", "session-a", agent="codex")
        hx.set(createIds=[fx["response"]["task_id"]])
        r = propose(hx, "k3", fixture_payload("create_task_agent"))
        hx.clear()
        hx.run("flush")
        bodies = hx.bodies("create_task")
        _check(f"{_T} AC1 create_task_agent: with a codex claim the body equals the fixture (agent codex, session session-a, no parent)",
               r.rc == 0 and len(bodies) == 1 and same_wire(bodies[0], fx["request"]) and bodies[0].get("agent") == "codex" and bodies[0].get("session") == "session-a",
               r.show() + repr(bodies)[:300])
        hx.clear()
        propose(hx, "k4", pay("With parent elsewhere", parent="project"))
        hx.run("flush")
        b = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC1 B1: with a claim, create_task sends session although parent is not the claimed task", b.get("session") == "session-a" and b.get("parent") == "project", repr(b))
    with V(R25) as hx:
        propose(hx, "k5", pay("No claim", parent="leaf-b"))
        hx.clear()
        hx.run("flush")
        b = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC1 B1: without a claim, create_task has no session key (even when parent is leaf-b)", bool(b) and "session" not in b, repr(b))
    with V(R25) as hx:
        fx = f25("create_task_refusals")
        req = {k: v for k, v in fx["invalid_repeat"]["request"].items() if k != "action"}
        r = propose(hx, "bad1", req)
        _check(f"{_T} AC1 refusals.invalid_repeat: the client refuses the 9am repeat offline (invalid repeat: time), no job, no request",
               r.rc == 1 and "invalid repeat: time" in text(r) and hx.job("bad1") is None and not hx.reqs(), r.show())
        hx.set(errors={"create_task": {"status": 409, "json": fx["invalid_repeat"]["response"], "times": 1}})
        propose(hx, "bad2", pay("Server says bad time", repeat={"unit": "day", "time": "09:00", "timeZone": "UTC"}))
        hx.run("flush")
        j = hx.job("bad2") or {}
        _check(f"{_T} AC1 refusals: a server invalid_request naming a repeat field ends refused, the field is in lastError, nothing applied",
               j.get("state") == "refused" and "time" in str(j.get("lastError")) and not create_applied(hx), repr(j)[:300])
        hx.set(errors=None)
        propose(hx, "bad3", pay("Outside the subtree", parent="private"))
        hx.run("flush")
        j = hx.job("bad3") or {}
        _check(f"{_T} AC1 refusals.outside_subtree: wrong_scope leaves the job not done and applies nothing",
               j.get("state") not in ("done", None) and not create_applied(hx), repr(j)[:300])
    # AC11 persona parity
    for env, want in (({"VIBE_AGENT": "codex"}, "codex"), ({}, "claude"), ({"VIBE_AGENT": "claude"}, "claude")):
        with V(R25) as hx:
            make(hx, "p1", "Persona check", env=env)
            b = (hx.bodies("create_task") or [{}])[0]
            _check(f"{_T} AC11: create_task body agent is {want!r} with env {env or 'unset'}", b.get("agent") == want, repr(b))
    with V(R25) as hx:
        tid = make(hx, "p1", "Persona upd", env={"VIBE_AGENT": "codex"})
        hx.clear()
        r = hx.run("enqueue", "update_task", "--key", "pu", env={"VIBE_AGENT": "codex"}, stdin=json.dumps({"task": tid, "title": "Renamed"}))
        hx.run("flush", env={"VIBE_AGENT": "codex"})
        b = (hx.bodies("update_task") or [{}])[0]
        _check(f"{_T} AC11: update_task by the creating codex persona carries agent codex and is accepted",
               r.rc == 0 and b.get("agent") == "codex" and (hx.job("pu") or {}).get("state") == "done", r.show() + repr(b))


# ---------------------------------------------------------------------------
# AC2 Payload validation
# ---------------------------------------------------------------------------

def _table(hx: V, kind: str, rows, prefix: str) -> None:
    for i, (label, payload, ok, frag) in enumerate(rows):
        wipe(hx)
        hx.clear()
        key = f"{prefix}{i}"
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        r = hx.run("enqueue", kind, "--key", key, stdin=raw)
        if ok:
            _check(f"{_T} AC2 valid: {label}: enqueued (exit 0, a job exists)", r.rc == 0 and hx.job(key) is not None, r.show())
        else:
            _check(f"{_T} AC2 invalid: {label}: exit 1, no job, nothing sent", r.rc == 1 and frag in text(r) and hx.job(key) is None and not hx.reqs(), r.show())


@safe
def test_prop_ac2_payload() -> None:
    print(f"{_T} AC2 payload validation")
    base = pay()
    em, astral = "é", "\U0001F600"
    rows = [
        ("minimal", base, True, ""),
        ("all optional fields", pay(parent="project", next_action="Do it", notes="Why", priority="later", hardDeadline=0, due=253402300799999), True, ""),
        ("missing title", {"estimate_minutes": 10, "assign": "owner"}, False, ""),
        ("missing estimate_minutes", {"title": "t", "assign": "owner"}, False, ""),
        ("missing assign", {"title": "t", "estimate_minutes": 10}, False, ""),
        ("assign agent", pay(assign="agent"), True, ""),
        ("assign both", pay(assign="both"), False, ""), ("assign empty", pay(assign=""), False, ""), ("assign OWNER", pay(assign="OWNER"), False, ""),
        ("assign a number", pay(assign=1), False, ""),
        ("priority now", pay(priority="now"), True, ""), ("priority next", pay(priority="next"), True, ""),
        ("priority number 1", pay(priority=1), False, ""), ("priority number 2", pay(priority=2), False, ""), ("priority high", pay(priority="high"), False, ""),
        ("priority NOW", pay(priority="NOW"), False, ""),
        ("title 500 code points", pay("t" * 500), True, ""), ("title 501", pay("t" * 501), False, ""),
        ("title 500 two-byte chars", pay(em * 500), True, ""), ("title 500 astral chars (1000 UTF-16 units)", pay(astral * 500), True, ""),
        ("title 501 astral chars", pay(astral * 501), False, ""),
        ("title blank", pay("   "), False, ""), ("title empty", pay(""), False, ""), ("title tab-newline", pay("\t\n"), False, ""),
        ("title not a string", pay(5), False, ""),
        ("next_action 2000", pay(next_action="n" * 2000), True, ""), ("next_action 2001", pay(next_action="n" * 2001), False, ""),
        ("next_action blank", pay(next_action="  "), False, ""),
        ("notes 8000", pay(notes="n" * 8000), True, ""), ("notes 8001", pay(notes="n" * 8001), False, ""), ("notes blank", pay(notes=" \n"), False, ""),
        ("notes null", pay(notes=None), False, ""),
        ("estimate_minutes 1", {**base, "estimate_minutes": 1}, True, ""),
        ("estimate_minutes 1000000", {**base, "estimate_minutes": 1000000}, True, ""), ("estimate_minutes 0", {**base, "estimate_minutes": 0}, False, ""),
        ("estimate_minutes 1000001", {**base, "estimate_minutes": 1000001}, False, ""), ("estimate_minutes 1.5", {**base, "estimate_minutes": 1.5}, False, ""),
        ("estimate_minutes -3", {**base, "estimate_minutes": -3}, False, ""), ("estimate_minutes a string", {**base, "estimate_minutes": "10"}, False, ""),
        ("estimate_minutes true", {**base, "estimate_minutes": True}, False, ""),
        ("hardDeadline 0", pay(hardDeadline=0), True, ""), ("hardDeadline max", pay(hardDeadline=253402300799999), True, ""),
        ("hardDeadline max+1", pay(hardDeadline=253402300800000), False, ""), ("hardDeadline -1", pay(hardDeadline=-1), False, ""),
        ("hardDeadline 1.5", pay(hardDeadline=1.5), False, ""), ("hardDeadline a string", pay(hardDeadline="1762000000000"), False, ""),
        ("due 0", pay(due=0), True, ""), ("due max+1", pay(due=253402300800000), False, ""), ("due -1", pay(due=-1), False, ""),
        ("parent a usable id", pay(parent="leaf-b"), True, ""), ("parent with a slash", pay(parent="a/b"), False, ""), ("parent empty", pay(parent=""), False, ""),
        ("parent 201 chars", pay(parent="p" * 201), False, ""),
        ("unknown key softTarget", pay(softTarget=5), False, ""), ("unknown key tags", pay(tags=["a"]), False, ""),
        ("reserved key session", pay(session="s"), False, ""), ("reserved key agent", pay(agent="claude"), False, ""),
        ("reserved key request_id", pay(request_id="x"), False, ""), ("reserved key action", pay(action="create_task"), False, ""),
        ("reserved key connection", pay(connection="c"), False, ""),
        ("payload is an array", [base], False, ""), ("payload is not JSON", "{nope", False, ""),
    ]
    with V(R25) as hx:
        _table(hx, "create_task", rows, "c")
        wipe(hx)
        hx.clear()
        padded = "  Padded title  "
        propose(hx, "pad", pay(padded, next_action=" go ", notes="\nnote\n"))
        hx.run("flush")
        b = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC2: title, next_action and notes are sent untrimmed", b.get("title") == padded and b.get("next_action") == " go " and b.get("notes") == "\nnote\n", repr(b)[:300])
        _check(f"{_T} AC2: the client never fills in priority", "priority" not in b, repr(b))
        wipe(hx, keep_ledger=False)
        tid = make(hx, "tgt", "Target of the updates", ids=["upd-target-1"])
        _check(f"{_T} AC2 setup: a created task exists in the ledger", tid == "upd-target-1" and bool(entry(hx, tid)), repr(ledger(hx))[:200])
        u = {"task": "upd-target-1"}
        urows = [
            ("title only", {**u, "title": "New"}, True, ""), ("next_action only", {**u, "next_action": "n"}, True, ""), ("notes only", {**u, "notes": "n"}, True, ""),
            ("estimate_minutes only", {**u, "estimate_minutes": 5}, True, ""), ("repeat object only", {**u, "repeat": {"unit": "day", "time": "09:00", "timeZone": "UTC"}}, True, ""),
            ("repeat null only (clears)", {**u, "repeat": None}, True, ""),
            ("no field at all", dict(u), False, ""), ("task missing", {"title": "x"}, False, ""),
            ("title null", {**u, "title": None}, False, ""), ("next_action null", {**u, "next_action": None}, False, ""), ("notes null", {**u, "notes": None}, False, ""),
            ("estimate_minutes null", {**u, "estimate_minutes": None}, False, ""),
            ("title 501", {**u, "title": "t" * 501}, False, ""), ("title blank", {**u, "title": " "}, False, ""),
            ("notes 8001", {**u, "notes": "n" * 8001}, False, ""), ("next_action 2001", {**u, "next_action": "n" * 2001}, False, ""),
            ("estimate_minutes 0", {**u, "estimate_minutes": 0}, False, ""),
            ("unknown key assign", {**u, "title": "x", "assign": "owner"}, False, ""), ("unknown key priority", {**u, "title": "x", "priority": "now"}, False, ""),
            ("reserved key session", {**u, "title": "x", "session": "s"}, False, ""), ("reserved key agent", {**u, "title": "x", "agent": "claude"}, False, ""),
            ("reserved key request_id", {**u, "title": "x", "request_id": "r"}, False, ""),
        ]
        _table(hx, "update_task", urows, "u")


# ---------------------------------------------------------------------------
# AC3 Repeat validation
# ---------------------------------------------------------------------------

BASE_R = {"unit": "week", "time": "09:00", "timeZone": "Europe/London"}


def rp(**kw):
    d = {**BASE_R, **kw}
    for k in [k for k, v in d.items() if v == "<drop>"]:
        del d[k]
    return d


# (label, repeat object or raw JSON text, expected fault field or None, the independent fake service agrees)
REPEAT_ROWS = [
    ("week with weekdays", rp(weekdays=["fri"], every=2), None, True),
    ("day minimal", {"unit": "day", "time": "00:00", "timeZone": "UTC"}, None, True),
    ("month minimal (defaults from starts)", {"unit": "month", "time": "23:59", "timeZone": "UTC"}, None, True),
    ("endTime equal to time", rp(endTime="09:00"), None, True), ("endTime earlier than time (next day)", rp(endTime="08:00"), None, True),
    ("every 1000", rp(every=1000), None, True), ("every 1", rp(every=1), None, True),
    ("weekdays all seven", rp(weekdays=["mon", "tue", "wed", "thu", "fri", "sat", "sun"]), None, True),
    ("month monthDay -1", rp(unit="month", monthDay=-1), None, True), ("month monthDay 31", rp(unit="month", monthDay=31), None, True),
    ("month nthWeekday last friday", rp(unit="month", nthWeekday={"n": -1, "weekday": "fri"}), None, True),
    ("month nthWeekday n=5", rp(unit="month", nthWeekday={"n": 5, "weekday": "mon"}), None, True),
    ("timeZone UTC", rp(timeZone="UTC"), None, True), ("timeZone Europe/London", rp(timeZone="Europe/London"), None, True),
    ("timeZone link name Asia/Calcutta accepted and sent as given", rp(timeZone="Asia/Calcutta"), None, True),
    ("timeZone America/Argentina/Buenos_Aires (three segments)", rp(timeZone="America/Argentina/Buenos_Aires"), None, True),
    ("starts and ends.on equal", rp(starts="2026-11-06", ends={"on": "2026-11-06"}), None, True),
    ("ends.after 1000", rp(ends={"after": 1000}), None, True), ("ends.after 1", rp(ends={"after": 1}), None, True),
    ("starts leap day 2028-02-29", rp(starts="2028-02-29"), None, True),
    ("unit missing", {"time": "09:00", "timeZone": "UTC"}, "unit", True), ("unit year", rp(unit="year"), "unit", True), ("unit uppercase", rp(unit="DAY"), "unit", True),
    ("time missing", rp(time="<drop>"), "time", True), ("timeZone missing", rp(timeZone="<drop>"), "timeZone", True),
    ("every 0", rp(every=0), "every", True), ("every 1001", rp(every=1001), "every", True), ("every 1.5", rp(every=1.5), "every", True),
    ("every a string", rp(every="2"), "every", True), ("every null", rp(every=None), "every", True),
    ("weekdays empty (stricter than the contract)", rp(weekdays=[]), "weekdays", True), ("weekdays uppercase", rp(weekdays=["Mon"]), "weekdays", True),
    ("weekdays duplicate", rp(weekdays=["mon", "mon"]), "weekdays", True), ("weekdays with unit month", rp(unit="month", weekdays=["mon"]), "weekdays", True),
    ("weekdays with unit day", rp(unit="day", weekdays=["mon"]), "weekdays", True), ("weekdays unknown day", rp(weekdays=["funday"]), "weekdays", True),
    ("weekdays a string", rp(weekdays="mon"), "weekdays", True),
    ("monthDay with unit week", rp(monthDay=5), "monthDay", True), ("monthDay 0", rp(unit="month", monthDay=0), "monthDay", True),
    ("monthDay 32", rp(unit="month", monthDay=32), "monthDay", True), ("monthDay -2", rp(unit="month", monthDay=-2), "monthDay", True),
    ("monthDay and nthWeekday together", rp(unit="month", monthDay=5, nthWeekday={"n": 1, "weekday": "fri"}), "monthDay", True),
    ("nthWeekday n=6", rp(unit="month", nthWeekday={"n": 6, "weekday": "fri"}), "nthWeekday", True),
    ("nthWeekday n=0", rp(unit="month", nthWeekday={"n": 0, "weekday": "fri"}), "nthWeekday", True),
    ("nthWeekday missing weekday", rp(unit="month", nthWeekday={"n": 2}), "nthWeekday", True),
    ("nthWeekday extra key", rp(unit="month", nthWeekday={"n": 2, "weekday": "fri", "x": 1}), "nthWeekday", True),
    ("nthWeekday bad weekday", rp(unit="month", nthWeekday={"n": 2, "weekday": "friday"}), "nthWeekday", True),
    ("nthWeekday with unit week", rp(nthWeekday={"n": 2, "weekday": "fri"}), "nthWeekday", True),
    ("time 9am", rp(time="9am"), "time", True), ("time 24:00", rp(time="24:00"), "time", True), ("time 9:00", rp(time="9:00"), "time", True),
    ("time 09:60", rp(time="09:60"), "time", True), ("time with seconds", rp(time="09:00:00"), "time", True),
    ("endTime 25:00", rp(endTime="25:00"), "endTime", True), ("endTime 9pm", rp(endTime="9pm"), "endTime", True),
    ("timeZone lowercase europe/london (case differs from the canonical name)", rp(timeZone="europe/london"), "timeZone", False),
    ("timeZone Europe/london", rp(timeZone="Europe/london"), "timeZone", False), ("timeZone utc lowercase", rp(timeZone="utc"), "timeZone", False),
    ("timeZone numeric +01:00", rp(timeZone="+01:00"), "timeZone", True),
    ("timeZone unknown Mars/Olympus", rp(timeZone="Mars/Olympus"), "timeZone", True), ("timeZone with a trailing space", rp(timeZone="Europe/London "), "timeZone", True),
    ("timeZone empty", rp(timeZone=""), "timeZone", True), ("timeZone a number", rp(timeZone=5), "timeZone", True),
    ("starts 2026-02-30", rp(starts="2026-02-30"), "starts", True), ("starts 2026-13-01", rp(starts="2026-13-01"), "starts", True),
    ("starts 2026-2-3", rp(starts="2026-2-3"), "starts", True), ("starts non-leap 2027-02-29", rp(starts="2027-02-29"), "starts", True),
    ("ends with both on and after", rp(ends={"on": "2026-12-01", "after": 3}), "ends", True), ("ends empty", rp(ends={}), "ends", True),
    ("ends.after 0", rp(ends={"after": 0}), "ends", True), ("ends.after 1001", rp(ends={"after": 1001}), "ends", True),
    ("ends.on 2026-02-30", rp(ends={"on": "2026-02-30"}), "ends", True), ("ends.on before starts", rp(starts="2026-11-06", ends={"on": "2026-11-05"}), "ends", True),
    ("ends a string", rp(ends="never"), "ends", True), ("ends unknown key", rp(ends={"until": "2026-12-01"}), "ends", True),
    ("unknown key colour", rp(colour="red"), "colour", True), ("unknown key skip", rp(skip=1), "skip", True),
    ('unknown key "__proto__" is named itself', '{"unit":"day","time":"09:00","timeZone":"UTC","__proto__":{"x":1}}', "__proto__", True),
    ('unknown key "constructor" is named itself', rp(constructor=1), "constructor", True),
    ("repeat is a string", "weekly", "repeat", True), ("repeat is a number", 5, "repeat", True), ("repeat is an array", [rp()], "repeat", True),
    ("repeat is null on create", None, "repeat", True),
    ("first fault in contract order: every before time", rp(every=0, time="bad"), "every", True),
    ("first fault in contract order: time before timeZone", rp(time="bad", timeZone="x"), "time", True),
    ("first fault in contract order: weekdays before time", rp(weekdays=[], time="bad"), "weekdays", True),
    ("first fault in contract order: starts before ends", rp(starts="2026-02-30", ends={}), "starts", True),
]


def _rep_json(rep) -> str:
    return rep if isinstance(rep, str) and rep.startswith("{") else json.dumps(rep)


def _repeat_payload(rep) -> str:
    return '{"title":"Repeat check","estimate_minutes":5,"assign":"owner","repeat":' + _rep_json(rep) + "}"


def server_says(hx: V, repeat) -> tuple:
    """Post straight to the fake service: its independent validator is the oracle for the field name."""
    body = '{"action":"create_task","connection":"%s","title":"direct","estimate_minutes":5,"assign":"owner","repeat":%s}' % (_CONN, _rep_json(repeat))
    req = urllib.request.Request(f"http://127.0.0.1:{hx.port}/api/browser-agent", data=body.encode(), headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@safe
def test_prop_ac3_repeat() -> None:
    print(f"{_T} AC3 repeat validation")
    with V(R25) as hx:
        for i, (label, rep, field, server_agrees) in enumerate(REPEAT_ROWS):
            wipe(hx, keep_ledger=False)
            hx.clear()
            key = f"r{i}"
            r = hx.run("enqueue", "create_task", "--key", key, stdin=_repeat_payload(rep))
            if field is None:
                ok = r.rc == 0 and hx.job(key) is not None
                if ok:
                    hx.run("flush")
                    ok = (hx.job(key) or {}).get("state") == "done" and len(create_applied(hx)) == 1
                _check(f"{_T} AC3 valid: {label}: enqueued, and the independent fake service accepts the frozen repeat", ok, r.show() + repr(hx.job(key))[:200])
            else:
                _check(f"{_T} AC3 invalid: {label}: exit 1 'invalid repeat: {field}', no job, nothing sent",
                       r.rc == 1 and f"invalid repeat: {field}" in text(r) and hx.job(key) is None and not hx.reqs(), r.show())
                if server_agrees:
                    code, js = server_says(hx, rep)
                    _check(f"{_T} AC3 oracle: {label}: the independent fake validator names the same field {field!r}", code == 409 and js.get("repeat") == field, f"{code} {js}")
        wipe(hx, keep_ledger=False)
        r = hx.run("enqueue", "create_task", "--key", "tz", stdin=_repeat_payload(rp(timeZone="Mars/Olympus")))
        _check(f"{_T} AC3: an Intl-refused time zone mentions that the host tzdata may be older than the server's", r.rc == 1 and "tzdata" in text(r), r.show())
        wipe(hx, keep_ledger=False)
        hx.clear()
        tid = make(hx, "tg", "Repeat updates", ids=["rep-target-1"])
        r = hx.run("enqueue", "update_task", "--key", "ub", stdin=json.dumps({"task": tid, "repeat": rp(every=0)}))
        _check(f"{_T} AC3: update_task with a bad repeat is refused 'invalid repeat: every'", r.rc == 1 and "invalid repeat: every" in text(r) and hx.job("ub") is None, r.show())
        r = hx.run("enqueue", "update_task", "--key", "un", stdin=json.dumps({"task": tid, "repeat": 5}))
        _check(f"{_T} AC3: update_task with a non-object non-null repeat is 'invalid repeat: repeat'", r.rc == 1 and "invalid repeat: repeat" in text(r), r.show())
        wipe(hx, keep_ledger=False)
        a = {"unit": "week", "weekdays": ["fri"], "every": 2, "time": "09:00", "timeZone": "Europe/London", "ends": {"after": 3}}
        b = {"ends": {"after": 3}, "timeZone": "Europe/London", "time": "09:00", "every": 2, "weekdays": ["fri"], "unit": "week"}
        r1 = propose(hx, "ord", pay("Order test", repeat=a))
        rid = (hx.job("ord") or {}).get("requestId")
        r2 = propose(hx, "ord", pay("Order test", repeat=b))
        _check(f"{_T} AC3: the same key with the repeat keys reordered is the same job (exit 0, one job, same requestId)",
               r1.rc == 0 and r2.rc == 0 and len([j for j in hx.jobs() if j["key"] == "ord"]) == 1 and (hx.job("ord") or {}).get("requestId") == rid, r2.show())
        r3 = propose(hx, "ord", pay("Order test", repeat=rp(every=3)))
        _check(f"{_T} AC3 control: the same key with a different repeat does not replace the job",
               (hx.job("ord") or {}).get("requestId") == rid and (hx.job("ord") or {}).get("payload", {}).get("repeat", {}).get("every") == 2, r3.show() + repr(hx.job("ord"))[:200])
        wipe(hx, keep_ledger=False)
        hx.clear()
        minimal = {"unit": "month", "time": "09:00", "timeZone": "Europe/London"}
        propose(hx, "nof", pay("No fill-in", repeat=minimal))
        hx.run("flush")
        body = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC3: a repeat without every/starts/weekdays/monthDay is sent without them (the server fills them)",
               body.get("repeat") == minimal and not {"every", "starts", "weekdays", "monthDay"} & set(body.get("repeat", {})), repr(body)[:300])


# ---------------------------------------------------------------------------
# AC4 Gating
# ---------------------------------------------------------------------------

@safe
def test_prop_ac4_gating() -> None:
    print(f"{_T} AC4 gating")
    with V(R23) as hx:
        propose(hx, "g1", pay("Gated create"))
        hx.clear()
        hx.run("flush")
        j = hx.job("g1") or {}
        _check(f"{_T} AC4: a create against v2.3 stays queued with needs_contract_v2.4 and zero create requests",
               j.get("state") == "queued" and "needs_contract_v2.4" in str(j.get("lastError")) and hx.count("create_task") == 0 and not j.get("sentBody"), repr(j)[:300] + repr(hx.actions()))
        st = hx.run("status")
        _check(f"{_T} AC4: status shows the gate", "needs_contract_v2.4" in text(st), st.show())
        hx.set(revision=R24)
        hx.clear()
        hx.run("flush")
        _check(f"{_T} AC4: a later v2.4 flush sends it once and it is done", (hx.job("g1") or {}).get("state") == "done" and hx.count("create_task") == 1 and len(create_applied(hx)) == 1, repr(hx.job("g1"))[:300])
    with V(R24) as hx:
        propose(hx, "g2", pay("Gated repeat", repeat=rp()))
        hx.clear()
        hx.run("flush")
        j = hx.job("g2") or {}
        _check(f"{_T} AC4: a repeat create against v2.4 stays queued with needs_contract_v2.5 and zero create requests",
               j.get("state") == "queued" and "needs_contract_v2.5" in str(j.get("lastError")) and hx.count("create_task") == 0, repr(j)[:300])
        propose(hx, "g2b", pay("Plain on v2.4"))
        hx.run("flush")
        _check(f"{_T} AC4 control: a plain create on the same v2.4 server is sent", (hx.job("g2b") or {}).get("state") == "done", repr(hx.job("g2b"))[:200])
        hx.set(revision=R25)
        hx.run("flush")
        _check(f"{_T} AC4: after the server speaks v2.5 the repeat create is sent", (hx.job("g2") or {}).get("state") == "done", repr(hx.job("g2"))[:200])
    with V(R25) as hx:
        hx.set(dropAfterApply={"create_task": 1})
        propose(hx, "g3", pay("Frozen repeat", repeat=rp()))
        hx.run("flush")
        j = hx.job("g3") or {}
        _check(f"{_T} AC4 setup: a v2.5 repeat create is frozen (sentBody) after a lost response", j.get("state") == "queued" and bool(j.get("sentBody")) and len(create_applied(hx)) == 1, repr(j)[:300])
        hx.set(dropAfterApply=None, revision=R24)
        hx.clear()
        hx.run("flush")
        j = hx.job("g3") or {}
        _check(f"{_T} AC4: the frozen v2.5 repeat create met by v2.4 becomes uncertain with no create request", j.get("state") == "uncertain" and hx.count("create_task") == 0, repr(j)[:300])
    with V(R24) as hx:
        tid = make(hx, "t0", "Update gate target", ids=["gate-target-1"])
        hx.run("enqueue", "update_task", "--key", "ug1", stdin=json.dumps({"task": tid, "title": "Plain update"}))
        hx.run("enqueue", "update_task", "--key", "ug2", stdin=json.dumps({"task": tid, "repeat": None}))
        hx.clear()
        hx.run("flush")
        _check(f"{_T} AC4: update_task without repeat is sent on v2.4", (hx.job("ug1") or {}).get("state") == "done", repr(hx.job("ug1"))[:200])
        j = hx.job("ug2") or {}
        _check(f"{_T} AC4: update_task with repeat null stays queued on v2.4 with needs_contract_v2.5", j.get("state") == "queued" and "needs_contract_v2.5" in str(j.get("lastError")) and hx.count("update_task") == 1, repr(j)[:300])
        hx.set(revision=R23)
        hx.run("enqueue", "update_task", "--key", "ug3", stdin=json.dumps({"task": tid, "notes": "later"}))
        hx.clear()
        hx.run("flush")
        j = hx.job("ug3") or {}
        _check(f"{_T} AC4: update_task against v2.3 stays queued with needs_contract_v2.4, nothing sent", j.get("state") == "queued" and "needs_contract_v2.4" in str(j.get("lastError")) and hx.count("update_task") == 0, repr(j)[:300])
    with V(R25) as hx:
        calls = ["capabilities", "ask", "list_asks", "ask_status", "next_task", "release", "comment", "record_usage", "record_time", "complete"]
        hx.set(capsAdd={"calls": calls})
        propose(hx, "g4", pay("No such call"))
        hx.clear()
        hx.run("flush")
        _check(f"{_T} AC4: a v2.5 server whose calls lack create_task gets no create request; the job is not done", hx.count("create_task") == 0 and (hx.job("g4") or {}).get("state") != "done", repr(hx.job("g4"))[:200])
    for label, limits, payload in (("title 20", {"title": 20}, pay("t" * 21)), ("next_action 5", {"next_action": 5}, pay(next_action="123456")), ("notes 7", {"notes": 7}, pay(notes="12345678"))):
        with V(R25) as hx:
            hx.set(limits=limits)
            propose(hx, "L", payload)
            hx.clear()
            hx.run("flush")
            _check(f"{_T} AC4/limits: server limit {label} refuses the job (refused) and nothing is sent", (hx.job("L") or {}).get("state") == "refused" and hx.count("create_task") == 0, repr(hx.job("L"))[:300])
        with V(R25) as hx:
            hx.set(limits={k: 500 for k in limits})
            propose(hx, "L", payload)
            hx.run("flush")
            _check(f"{_T} AC4/limits control: with a looser limit ({label}) the job is sent", (hx.job("L") or {}).get("state") == "done", repr(hx.job("L"))[:200])
    for key in ("title", "next_action", "notes"):
        with V(R25) as hx:
            hx.set(capsDrop=[key])
            propose(hx, "L", pay("x"))
            hx.clear()
            hx.run("flush")
            _check(f"{_T} AC4/limits: a v2.5 capabilities answer missing limits.{key} sends no create request and the job is not done", hx.count("create_task") == 0 and (hx.job("L") or {}).get("state") != "done", repr(hx.job("L"))[:200])
    for label, mk in (("MCP binding", mcp_hx), ("unbound project", lambda: _Hx(bound=False))):
        with mk() as hx:
            for kind, p in (("create_task", pay()), ("update_task", {"task": "x", "title": "t"})):
                r = hx.cli("enqueue", kind, "--key", "m1", stdin=json.dumps(p))
                _check(f"{_T} AC4: enqueue {kind} on a {label} exits 1 with 'create_task needs a Task&I descriptor binding'", r.rc == 1 and "needs a Task&I descriptor binding" in text(r) and (kind != "create_task" or "create_task needs a Task&I descriptor binding" in text(r)), r.show())


# ---------------------------------------------------------------------------
# AC5 Resend and reconcile
# ---------------------------------------------------------------------------

@safe
def test_prop_ac5_resend_reconcile() -> None:
    print(f"{_T} AC5 resend and reconcile")
    for label, ctl in (("applied before the crash", {"dropAfterApply": {"create_task": 1}}), ("not applied before the crash", {"dropBeforeApply": {"create_task": 1}})):
        with V(R25) as hx:
            hx.set(**ctl)
            propose(hx, "s1", pay("Resend me"))
            hx.run("flush")
            first = (hx.raws("create_task") or [""])[0]
            rid = (hx.job("s1") or {}).get("requestId")
            hx.set(dropAfterApply=None, dropBeforeApply=None)
            hx.run("flush")
            raws = hx.raws("create_task")
            j = hx.job("s1") or {}
            _check(f"{_T} AC5 ({label}): the resend has identical bytes and the same request_id, the job is done",
                   len(raws) == 2 and raws[1] == first and json.loads(first).get("request_id") == rid and j.get("state") == "done", repr(raws)[:300])
            _check(f"{_T} AC5 ({label}): the fake server holds exactly one task", len(create_applied(hx)) == 1, repr(len(create_applied(hx))))
            _check(f"{_T} AC5 ({label}): the ledger has exactly one entry", len(ledger(hx)) == 1 and ledger(hx)[0].get("task_id") == (j.get("result") or {}).get("task_id"), repr(ledger(hx))[:200])
    with V(R25) as hx:
        hx.set(dropAfterApply={"create_task": 1})
        propose(hx, "s2", pay("Collide"))
        hx.run("flush")
        hx.set(dropAfterApply=None, errors={"create_task": {"status": 409, "json": {"error": "receipt_collision"}, "times": 1}})
        hx.run("flush")
        j = hx.job("s2") or {}
        _check(f"{_T} AC5: receipt_collision on a resend leaves the job uncertain (never done, no ledger entry)", j.get("state") == "uncertain" and not ledger(hx), repr(j)[:300])
        hx.set(errors=None)
        hx.clear()
        hx.run("flush")
        _check(f"{_T} AC5: an uncertain create is not resent automatically", hx.count("create_task") == 0, repr(hx.actions()))
        r = hx.run("reconcile", "--key", "s2", "--action", "done", "--evidence", "seen in Task&I")
        _check(f"{_T} AC5: reconcile --action done without --task-id exits 1 and writes nothing", r.rc == 1 and (hx.job("s2") or {}).get("state") == "uncertain" and not ledger(hx), r.show())
        for bad in ("a/b", "x" * 201):
            r = hx.run("reconcile", "--key", "s2", "--action", "done", "--task-id", bad, "--evidence", "e")
            _check(f"{_T} AC5: reconcile --task-id {bad[:12]!r} (not a usable id) exits 1", r.rc == 1 and not ledger(hx), r.show())
        r = hx.run("reconcile", "--key", "s2", "--action", "done", "--task-id", "owner-read-id-1", "--evidence", "seen in Task&I")
        e = entry(hx, "owner-read-id-1")
        _check(f"{_T} AC5: reconcile --action done --task-id writes the ledger entry and marks the job done",
               r.rc == 0 and (hx.job("s2") or {}).get("state") == "done" and e.get("title") == "Collide" and e.get("gone") is False and e.get("key") == "s2", r.show() + repr(ledger(hx))[:300])
    with V(R25) as hx:
        hx.set(dropAfterApply={"create_task": 1})
        propose(hx, "s3", pay("Retry me"))
        hx.run("flush")
        hx.set(dropAfterApply=None, errors={"create_task": {"status": 409, "json": {"error": "receipt_collision"}, "times": 1}})
        hx.run("flush")
        r = hx.run("reconcile", "--key", "s3", "--action", "retry", "--evidence", "checked: absent")
        _check(f"{_T} AC5/AC20: reconcile --action retry after a resend receipt_collision is refused (exit 1, still uncertain, nothing queued)",
               r.rc == 1 and (hx.job("s3") or {}).get("state") == "uncertain", r.show())
    with V(R25) as hx:
        propose(hx, "s4", pay("Retry me too"))
        _edit_state(hx, lambda st: next(j for j in st["jobs"] if j["key"] == "s4").update(state="uncertain"))
        old = (hx.job("s4") or {}).get("requestId")
        r = hx.run("reconcile", "--key", "s4", "--action", "retry", "--evidence", "checked: absent")
        _check(f"{_T} AC5: reconcile --action retry warns that the owner may now see two proposals", r.rc == 0 and "two proposals" in text(r) and (hx.job("s4") or {}).get("state") == "queued", r.show())
        new = (hx.job("s4") or {}).get("requestId")
        _check(f"{_T} AC5: the retry carries a fresh request_id", bool(new) and new != old and bool(UUID4.match(new or "")), f"{old} {new}")
        hx.clear()
        hx.run("flush")
        bodies = hx.bodies("create_task")
        _check(f"{_T} AC5: the retried create is sent once with the new request_id and is done", len(bodies) == 1 and bodies[0].get("request_id") == new and (hx.job("s4") or {}).get("state") == "done", repr(bodies)[:300])


# ---------------------------------------------------------------------------
# AC6 Results
# ---------------------------------------------------------------------------

GOOD_ID = "7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e"


@safe
def test_prop_ac6_results() -> None:
    print(f"{_T} AC6 results")
    variants = [("an extra key", {"task_id": GOOD_ID, "provisional": True, "extra": 1}), ("provisional false", {"task_id": GOOD_ID, "provisional": False}),
                ("provisional missing", {"task_id": GOOD_ID}), ("task_id containing a slash", {"task_id": "a/b", "provisional": True}),
                ("task_id missing", {"provisional": True}), ("task_id a number", {"task_id": 7, "provisional": True}), ("task_id empty", {"task_id": "", "provisional": True}),
                ("provisional a string", {"task_id": GOOD_ID, "provisional": "true"}), ("an empty object", {}), ("a bare string", "ok")]
    for label, resp in variants:
        with V(R25) as hx:
            hx.set(badResponse={"create_task": resp})
            propose(hx, "v1", pay("Odd result"))
            hx.run("flush")
            j = hx.job("v1") or {}
            _check(f"{_T} AC6 create: {label} -> uncertain (never done), no ledger entry", j.get("state") == "uncertain" and not ledger(hx), repr(j)[:300])
    with V(R25) as hx:
        propose(hx, "ok", pay("Fine result"))
        hx.run("flush")
        _check(f"{_T} AC6 control: the genuine response is done with {{task_id, provisional: true}} and one ledger entry",
               (hx.job("ok") or {}).get("state") == "done" and len(ledger(hx)) == 1 and (hx.job("ok") or {}).get("result", {}).get("provisional") is True, repr(hx.job("ok"))[:300])
    with V(R25) as hx:
        tid = make(hx, "t0", "Update result target", ids=["res-target-1"])
        uvariants = [("task echo mismatch", {"task": "other", "update_id": GOOD_ID}), ("update_id missing", {"task": tid}), ("extra key", {"task": tid, "update_id": GOOD_ID, "x": 1}),
                     ("update_id with a slash", {"task": tid, "update_id": "a/b"}), ("task missing", {"update_id": GOOD_ID})]
        for i, (label, resp) in enumerate(uvariants):
            hx.set(badResponse={"update_task": resp})
            hx.run("enqueue", "update_task", "--key", f"u{i}", stdin=json.dumps({"task": tid, "title": f"T{i}"}))
            hx.run("flush")
            _check(f"{_T} AC6 update: {label} -> uncertain, never done", (hx.job(f"u{i}") or {}).get("state") == "uncertain", repr(hx.job(f"u{i}"))[:300])
        hx.set(badResponse=None)
        hx.run("enqueue", "update_task", "--key", "uok", stdin=json.dumps({"task": tid, "title": "Fine"}))
        hx.run("flush")
        _check(f"{_T} AC6 control: the genuine update response is done", (hx.job("uok") or {}).get("state") == "done", repr(hx.job("uok"))[:200])
    with V(R25) as hx:
        for i, body in enumerate(({"error": "invalid_request", "repeat": "weekdays"}, {"error": "invalid_request", "unsupported": "repeat"}, {"error": "invalid_request"})):
            hx.set(errors={"create_task": {"status": 409, "json": body}})
            propose(hx, f"e{i}", pay(f"Rejected {i}"))
            hx.run("flush")
            hx.set(errors=None)
            j = hx.job(f"e{i}") or {}
            kept = body.get("repeat") or body.get("unsupported")
            _check(f"{_T} AC6: invalid_request {body} -> refused" + (f" with {kept!r} kept in lastError" if kept else ""),
                   j.get("state") == "refused" and (kept is None or kept in str(j.get("lastError"))) and not ledger(hx), repr(j)[:300])
        _check(f"{_T} AC6: the server applied none of the rejected creates", not create_applied(hx), "")
    with V(R25) as hx:
        hx.set(dropAfterApply={"create_task": 1})
        propose(hx, "rp", pay("Replayed"))
        hx.run("flush")
        hx.set(dropAfterApply=None)
        hx.run("flush")
        _check(f"{_T} AC6: a replayed create is done once, one server task, one replay logged",
               (hx.job("rp") or {}).get("state") == "done" and len(create_applied(hx)) == 1 and len(hx.replays("create_task")) == 1, "")


def main() -> int:
    for fn in (test_prop_ac1_wire, test_prop_ac2_payload, test_prop_ac3_repeat, test_prop_ac4_gating, test_prop_ac5_resend_reconcile, test_prop_ac6_results):
        fn()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
