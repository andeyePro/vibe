#!/usr/bin/env python3
"""Acceptance checks for task_065 (Task&I in /vss and /vsss), Part A: `decide`, storage, usage importer, body cap.

Tester-owned (cycle 1).  AC1-AC8, AC7b, AC7c of ``.vs/spec.md``.  Part B (prose) is ``checks_54_harness_prose.py``.

Harness.  Reuses the loopback server and git-project fixture of ``checks_50_taskandi_http.py`` (``_Hx``).  The real CLI
has no clock seam by design, so every command here runs through a tiny Node driver that calls the exported
``cli(argv, {httpConnect, clock})`` with ``clock = () => <ms>`` (the spec's ``createClient({clock})``).  A case that
passes ``now=None`` gets no clock at all (real time) and is used where the test only needs ordering across real events.
Requests are counted per case from the server log: decide makes one ``capabilities`` and one ``ask_status`` request
when asks are open and none otherwise.

Run only this module with:
    python3 smoke/checks_53_taskandi_decide.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import (_CLIENT, _DROP, _T1, _RESULTS, _Hx, _Res, _check, _fixture, _fixture_payload,
                                           _find_key, _iso)

_T = "[taskandi-decide]"
H = _T1 + 3 * 3600_000            # hard deadline
RM = 45                           # default remaining_minutes of an ask
LS = H - RM * 60000               # latest start for a default ask
LEASE = H + 10 ** 8
SESSION = "session-a"
TASK = "leaf-b"
FLAGS = ([], ["--no-other-work"])

_RUN = r'''
import { pathToFileURL } from 'node:url';
const C = await import(pathToFileURL(process.argv[2]).href);
const opts = { httpConnect: { host: '127.0.0.1', port: Number(process.argv[3]) } };
if (process.argv[4] !== '') { const t = Number(process.argv[4]); opts.clock = () => t; }
await C.cli(JSON.parse(process.argv[5]), opts);
'''


def nt(**over) -> dict:
    r = copy.deepcopy(_fixture("next_task")["response"])
    r.update(task=TASK, hardDeadline=H, defaults_allowed=True, allowance={"tokens": 10 ** 7},
             spent={"windows": 0, "tokens": 0}, lease={"until": LEASE, "session": SESSION})
    for k, v in over.items():
        if v is _DROP:
            r.pop(k, None)
        else:
            r[k] = v
    return r


def dc(hx: _Hx, now, *args: str, stdin: str = "", env: dict | None = None) -> _Res:
    run = hx.base / "run.mjs"
    if not run.exists():
        run.write_text(_RUN)
    res = subprocess.run(["node", str(run), str(_CLIENT), str(hx.port), "" if now is None else str(now), json.dumps(list(args))],
                         cwd=str(hx.repo), input=stdin, capture_output=True, text=True, timeout=120, env=hx.env("0", env))
    return _Res(res.returncode, res.stdout, res.stderr)


def parse(res: _Res):
    """Strict JSON: NaN / Infinity are refused."""
    def bad(token):
        raise ValueError(token)
    try:
        return json.loads(res.out, parse_constant=bad)
    except ValueError:
        return None


def claim(hx: _Hx, clock=_T1, **over) -> _Res:
    hx.route("next_task", json=nt(**over))
    return dc(hx, clock, "next-task", "--agent", "claude", "--session", SESSION)


def mkask(hx: _Hx, clock, aid: str, key: str | None = None, rm: int = RM, blocking: bool = True, reversible: bool = True,
          flush: bool = True, route: dict | None = None, task: str | None = None) -> str:
    key = key or f"k-{aid}"
    hx.route("ask", **(route or {"json": {"ask_id": aid, "placed": "subtask"}}))
    payload = {"question": f"Question {aid}?", "default": "Use X", "order": 1, "estimate_minutes": 2,
               "remaining_minutes": rm, "reversible": reversible, "blocking": blocking}
    args = ["enqueue", "ask", "--key", key] + (["--task", task] if task else [])
    dc(hx, clock, *args, stdin=json.dumps(payload))
    if flush:
        dc(hx, clock, "flush")
    return key


def st(aid: str, seen=_T1 - 1000, deferred=False, answered=False) -> dict:
    return {"ask_id": aid, "seen_at": seen, "deferred": deferred, "answered": answered}


def set_status(hx: _Hx, *entries: dict) -> None:
    hx.route("ask_status", json={"task": TASK, "asks": list(entries)})


def _ru_payload() -> dict:
    p = _fixture_payload("record_usage")
    for k in ("windows", "source", "source_ref"):
        p.pop(k, None)
    return p


def owner_item(aid: str, owner: bool = True, answer: str = "Go with X") -> dict:
    item = copy.deepcopy(_fixture("list_asks")["response"]["asks"][0])
    item.update(ask_id=aid, task=TASK, owner_answer=owner, answer=answer)
    return item


def set_answers(hx: _Hx, *items: dict) -> None:
    hx.route("list_asks", json={"task": TASK, "now": _T1, "asks": list(items)})


def decide(hx: _Hx, now, *flags: str, env: dict | None = None):
    hx.clear()
    res = dc(hx, now, "decide", *flags, env=env)
    return res, parse(res)


def by_id(out: dict | None) -> dict:
    return {a["ask_id"]: a for a in (out or {}).get("asks", [])}


def reqs(hx: _Hx) -> tuple:
    return (hx.count("capabilities"), hx.count("ask_status"), len(hx.reqs()))


def full_state(hx: _Hx) -> dict:
    return hx.state() or {}


# ---------------------------------------------------------------------------
# AC1 Conditions
# ---------------------------------------------------------------------------

def test_td_ac1_conditions_per_ask() -> None:
    """Every per-ask condition fails alone (and in pairs) while the task-level conditions all hold."""
    print(f"{_T} AC1 per-ask conditions")
    with _Hx() as hx:
        claim(hx)
        specs = [("ask-ok", {}, st("ask-ok")), ("ask-def", {}, st("ask-def", seen=None, deferred=True)),
                 ("ask-nb", {"blocking": False}, st("ask-nb")),
                 ("ask-nbirr", {"blocking": False, "reversible": False}, st("ask-nbirr", seen=None)),
                 ("ask-miss", {}, None), ("ask-ans", {}, st("ask-ans", answered=True)),
                 ("ask-unseen", {}, st("ask-unseen", seen=None)), ("ask-irr", {"reversible": False}, st("ask-irr")),
                 ("ask-unseen-irr", {"reversible": False}, st("ask-unseen-irr", seen=None)),
                 ("ask-rm10", {"rm": 10}, st("ask-rm10"))]
        for aid, kw, _ in specs:
            mkask(hx, LS, aid, **kw)
        set_status(hx, *[s for _, _, s in specs if s])
        _check(f"{_T} AC1 setup: all ten asks are done jobs with an ask_id",
               all((hx.job(f"k-{a}") or {}).get("state") == "done" for a, _, _ in specs), repr([j["state"] for j in hx.jobs()]))
        for flag in FLAGS:
            label = "with --no-other-work" if flag else "without --no-other-work"
            res, out = decide(hx, LS, *flag)
            asks = by_id(out)
            _check(f"{_T} AC1 {label}: exit 0 and JSON with next=proceed (control: proceed outranks the rest)",
                   res.rc == 0 and out is not None and out.get("next") == "proceed" and out.get("task") == TASK and out.get("now") == LS,
                   res.show())
            _check(f"{_T} AC1 {label}: one capabilities and one ask_status request, nothing else", reqs(hx) == (1, 1, 2), repr(reqs(hx)))
            blocked = "park" if flag else "wait"
            want = {"ask-ok": ("proceed", "default-allowed"), "ask-def": ("proceed", "default-allowed"),
                    "ask-nb": ("continue", "non-blocking"), "ask-nbirr": ("continue", "non-blocking"),
                    "ask-miss": (blocked, "unknown-ask"), "ask-unseen": (blocked, "unseen"),
                    "ask-unseen-irr": (blocked, "unseen"), "ask-irr": (blocked, "irreversible"),
                    "ask-rm10": (blocked, "before-latest-start")}
            for aid, (action, why) in want.items():
                a = asks.get(aid) or {}
                _check(f"{_T} AC1 {label}: {aid} -> {action} / {why}", (a.get("action"), a.get("why")) == (action, why), repr(a))
            a = asks.get("ask-ans") or {}
            _check(f"{_T} AC1 {label}: ask-ans (answered, not polled) -> never proceed, why answered-not-yet-polled, repoll true",
                   a.get("action") in (("wait", "park") if flag else ("wait",)) and a.get("why") == "answered-not-yet-polled"
                   and (out or {}).get("repoll") is True, repr(a))
            _check(f"{_T} AC1 {label}: ask-ok latest_start_used = hardDeadline - 45 min; ask-rm10 uses its own remaining_minutes",
                   (asks.get("ask-ok") or {}).get("latest_start_used") == LS and (asks.get("ask-rm10") or {}).get("latest_start_used") == H - 10 * 60000,
                   repr((asks.get("ask-ok"), asks.get("ask-rm10"))))
            _check(f"{_T} AC1 {label}: each ask echoes key, question, default, blocking, reversible",
                   all(a.get("key") == f"k-{aid}" and a.get("question") == f"Question {aid}?" and a.get("default") == "Use X"
                       and isinstance(a.get("blocking"), bool) and isinstance(a.get("reversible"), bool) for aid, a in asks.items()) and len(asks) == 10,
                   repr(out)[:400])
        # A non-proceed ask never gets 'proceed'
        _check(f"{_T} AC1: only the two all-conditions-true asks are proceed (deferred+unseen passes condition 5)",
               sorted(k for k, a in by_id(out).items() if a["action"] == "proceed") == ["ask-def", "ask-ok"], repr(out)[:300])


def _one(clock, status_kw=None, ask_kw=None, nt_over=None, nows=None, flags=FLAGS):
    """One ask on a fresh project; returns [(now, flag, out)] for each now (default: clock)."""
    results = []
    with _Hx() as hx:
        claim(hx, **(nt_over or {}))
        mkask(hx, clock, "a1", **(ask_kw or {}))
        set_status(hx, st("a1", **(status_kw or {})))
        for now in (nows or [clock]):
            for flag in flags:
                res, out = decide(hx, now, *flag)
                results.append((now, flag, res, out, reqs(hx)))
    return results


def _first(out):
    return (out or {}).get("asks", [{}])[0] if (out or {}).get("asks") else {}


def test_td_ac1_task_level_conditions() -> None:
    print(f"{_T} AC1 deadline, defaults and ordering")
    # no deadline at all
    for now, flag, res, out, _ in _one(LS, nt_over={"hardDeadline": _DROP}):
        a = _first(out)
        _check(f"{_T} AC1 no deadline ({'park' if flag else 'wait'} mode): why no-deadline, latest_start_used null",
               a.get("why") == "no-deadline" and a.get("action") == ("park" if flag else "wait") and a.get("latest_start_used") is None, res.show())
    # defaults off
    for now, flag, res, out, _ in _one(LS, nt_over={"defaults_allowed": False}):
        a = _first(out)
        _check(f"{_T} AC1 defaults_allowed false ({'park' if flag else 'wait'} mode): why defaults-off",
               a.get("why") == "defaults-off" and a.get("action") == ("park" if flag else "wait"), res.show())
    # exact boundary: now == latest start passes, one ms earlier does not
    rows = _one(LS, nows=[LS - 1, LS, LS + 1], flags=([],))
    got = [(r[0], _first(r[3]).get("action"), _first(r[3]).get("why")) for r in rows]
    _check(f"{_T} AC1 boundary: LS-1 waits (before-latest-start), LS and LS+1 proceed",
           got == [(LS - 1, "wait", "before-latest-start"), (LS, "proceed", "default-allowed"), (LS + 1, "proceed", "default-allowed")], repr(got))
    # deadline already in the past counts as passed
    rows = _one(H + 10 ** 6, flags=([],))
    _check(f"{_T} AC1 a deadline already in the past passes (proceed)", _first(rows[0][3]).get("action") == "proceed", repr(rows[0][3]))
    # latest_start vs hardDeadline - remaining: the later wins, each ordering
    later = LS + 600_000
    rows = _one(LS, nt_over={"latest_start": later}, nows=[later - 1, later], flags=([],))
    got = [(_first(r[3]).get("action"), _first(r[3]).get("why"), _first(r[3]).get("latest_start_used")) for r in rows]
    _check(f"{_T} AC1 latest_start later than hardDeadline-remaining: it is used (waits at L-1, proceeds at L)",
           got == [("wait", "before-latest-start", later), ("proceed", "default-allowed", later)], repr(got))
    earlier = LS - 600_000
    rows = _one(LS, nt_over={"latest_start": earlier}, nows=[LS - 1, LS], flags=([],))
    got = [(_first(r[3]).get("action"), _first(r[3]).get("why"), _first(r[3]).get("latest_start_used")) for r in rows]
    _check(f"{_T} AC1 latest_start earlier than hardDeadline-remaining: the deadline rule is used (waits at LS-1, proceeds at LS)",
           got == [("wait", "before-latest-start", LS), ("proceed", "default-allowed", LS)], repr(got))
    rows = _one(LS, nt_over={"hardDeadline": _DROP, "latest_start": LS}, nows=[LS - 1, LS], flags=([],))
    got = [(_first(r[3]).get("action"), _first(r[3]).get("why")) for r in rows]
    _check(f"{_T} AC1 latest_start alone (no hardDeadline) is enough", got == [("wait", "before-latest-start"), ("proceed", "default-allowed")], repr(got))
    # pinned why order: first failing condition wins
    pairs = [("before-latest-start + defaults-off -> before-latest-start", LS - 1, {"nt_over": {"defaults_allowed": False}}, "before-latest-start"),
             ("defaults-off + irreversible -> defaults-off", LS, {"nt_over": {"defaults_allowed": False}, "ask_kw": {"reversible": False}}, "defaults-off"),
             ("no-deadline + defaults-off -> no-deadline", LS, {"nt_over": {"hardDeadline": _DROP, "defaults_allowed": False}}, "no-deadline"),
             ("unseen + no-deadline -> unseen", LS, {"nt_over": {"hardDeadline": _DROP}, "status_kw": {"seen": None}}, "unseen"),
             ("before-latest-start + irreversible -> before-latest-start", LS - 1, {"ask_kw": {"reversible": False}}, "before-latest-start")]
    for label, now, kw, why in pairs:
        rows = _one(now, flags=([],), **kw)
        _check(f"{_T} AC1 pinned order: {label}", _first(rows[0][3]).get("why") == why and _first(rows[0][3]).get("action") == "wait", repr(rows[0][3])[:300])
    # positive control for the whole table: with every condition true the same builder proceeds
    rows = _one(LS, flags=([],))
    _check(f"{_T} AC1 control: all conditions true -> proceed", _first(rows[0][3]).get("action") == "proceed", repr(rows[0][3])[:300])


# ---------------------------------------------------------------------------
# AC2 Answered and unjudged asks
# ---------------------------------------------------------------------------

def test_td_ac2_answered_and_unjudged() -> None:
    print(f"{_T} AC2 answered and unjudged asks")
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "ask-1")
        set_status(hx, st("ask-1", answered=True))
        set_answers(hx, owner_item("ask-1", owner=False, answer="stranger's answer"))
        res, out = decide(hx, LS)
        a = by_id(out).get("ask-1", {})
        _check(f"{_T} AC2: answered, never polled, all else true -> wait + repoll true (not proceed)",
               res.rc == 0 and a.get("action") == "wait" and a.get("why") == "answered-not-yet-polled" and out.get("repoll") is True and out.get("next") != "proceed",
               res.show())
        res, out = decide(hx, LS, "--no-other-work")
        _check(f"{_T} AC2: the repoll is requested under --no-other-work too, and still no proceed",
               out is not None and out.get("repoll") is True and by_id(out).get("ask-1", {}).get("action") != "proceed", res.show())
        res, out = decide(hx, LS)
        _check(f"{_T} AC2: control - a second decide with no poll in between still says answered-not-yet-polled",
               by_id(out).get("ask-1", {}).get("why") == "answered-not-yet-polled", res.show())
        res = dc(hx, LS, "poll", "--task", TASK)
        pj = parse(res) or {}
        _check(f"{_T} AC2: poll sees the non-owner answer (ignored 1, newAnswers 0)", res.rc == 0 and pj.get("ignored") == 1 and pj.get("newAnswers") == 0, res.show())
        for flag, action in (([], "wait"), (["--no-other-work"], "park")):
            res, out = decide(hx, LS, *flag)
            a = by_id(out).get("ask-1", {})
            _check(f"{_T} AC2: after the poll, still no owner answer -> answered-by-non-owner / {action}",
                   res.rc == 0 and a.get("why") == "answered-by-non-owner" and a.get("action") == action and not out.get("repoll"), res.show())
        _check(f"{_T} AC2: a non-owner answer does not clear the ask (still listed) and next is never proceed",
               "ask-1" in by_id(out) and out.get("next") != "proceed", repr(out)[:300])
    # owner answer removes the ask, and with no other open ask nothing is requested
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "ask-1")
        set_status(hx, st("ask-1", answered=True))
        set_answers(hx, owner_item("ask-1", owner=True))
        res = dc(hx, LS, "poll", "--task", TASK)
        _check(f"{_T} AC2: control - poll stores the owner answer", (parse(res) or {}).get("newAnswers") == 1, res.show())
        res, out = decide(hx, LS)
        _check(f"{_T} AC2: an owner-answered ask does not appear; with no open ask decide makes zero requests",
               res.rc == 0 and out is not None and out.get("asks") == [] and reqs(hx) == (0, 0, 0), res.show() + repr(reqs(hx)))
    # unjudged: queued / uncertain / refused ask jobs
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "a-ref", route={"status": 409, "json": {"error": "invalid_request"}})
        mkask(hx, LS, "a-unc", route={"status": 500, "json": {"error": "boom"}})
        mkask(hx, LS, "a-q", flush=False)
        states = {j["key"]: j["state"] for j in hx.jobs()}
        _check(f"{_T} AC2 setup: refused, uncertain and queued ask jobs exist", states == {"k-a-ref": "refused", "k-a-unc": "uncertain", "k-a-q": "queued"}, repr(states))
        res, out = decide(hx, LS)
        un = {u["key"]: u["state"] for u in (out or {}).get("unjudged", [])}
        _check(f"{_T} AC2: queued, uncertain and refused asks are listed in unjudged and never judged (asks empty, zero requests)",
               res.rc == 0 and un == states and out.get("asks") == [] and reqs(hx) == (0, 0, 0), res.show() + repr(reqs(hx)))
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "a-done")
        mkask(hx, LS, "a-q", flush=False)
        set_status(hx, st("a-done"))
        res, out = decide(hx, LS)
        _check(f"{_T} AC2 control: a done ask is judged (in asks) while the queued one stays unjudged",
               "a-done" in by_id(out) and [u["key"] for u in out.get("unjudged", [])] == ["k-a-q"] and reqs(hx) == (1, 1, 2), res.show())
    # an ask missing from ask_status is never proceed, even with everything else true
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "ask-1")
        set_status(hx)
        res, out = decide(hx, LS)
        a = by_id(out).get("ask-1", {})
        _check(f"{_T} AC2: an ask missing from ask_status -> unknown-ask, not proceed", a.get("why") == "unknown-ask" and a.get("action") != "proceed", res.show())


# ---------------------------------------------------------------------------
# AC3 Resolve
# ---------------------------------------------------------------------------

def test_td_ac3_resolve() -> None:
    print(f"{_T} AC3 resolve")
    with _Hx() as hx:
        claim(hx)
        mkask(hx, LS, "ask-1")
        mkask(hx, LS, "ask-2")
        dc(hx, LS, "enqueue", "comment", "--key", "c-done", stdin=json.dumps({"text": "hello"}))
        dc(hx, LS, "flush")
        mkask(hx, LS, "ask-q", flush=False)
        set_status(hx, st("ask-1"), st("ask-2", seen=None))
        res, out = decide(hx, LS)
        _check(f"{_T} AC3: control - ask-1 is proceed before resolution", by_id(out).get("ask-1", {}).get("action") == "proceed", res.show())
        hx.clear()
        res = dc(hx, LS, "decide", "--resolve", "k-ask-1", "--as", "proceeded")
        _check(f"{_T} AC3: --resolve exits 0 and makes no request", res.rc == 0 and len(hx.reqs()) == 0, res.show() + repr(hx.actions()))
        entry = [r for r in full_state(hx).get("resolved", []) if r.get("ask_id") == "ask-1"]
        _check(f"{_T} AC3: state.resolved holds {{task, ask_id, as: proceeded, at}}",
               len(entry) == 1 and entry[0].get("task") == TASK and entry[0].get("as") == "proceeded" and "at" in entry[0], repr(full_state(hx).get("resolved")))
        res, out = decide(hx, LS)
        _check(f"{_T} AC3: after resolution ask-1 is gone and proceed is not emitted again",
               "ask-1" not in by_id(out) and out.get("next") != "proceed" and "ask-2" in by_id(out), res.show())
        res = dc(hx, LS, "decide", "--resolve", "k-ask-2", "--as", "parked")
        entry = [r for r in full_state(hx).get("resolved", []) if r.get("ask_id") == "ask-2"]
        _check(f"{_T} AC3 (rev 7 AC37): --as parked is a usage error and records nothing", res.rc != 0 and len(entry) == 0, res.show())
        before = json.dumps(full_state(hx).get("resolved"), sort_keys=True)
        for label, args in [("unknown key", ["--resolve", "no-such-key", "--as", "proceeded"]),
                            ("a queued ask job", ["--resolve", "k-ask-q", "--as", "proceeded"]),
                            ("a done non-ask job", ["--resolve", "c-done", "--as", "proceeded"]),
                            ("a bad --as value", ["--resolve", "k-ask-1", "--as", "maybe"]),
                            ("--resolve without --as", ["--resolve", "k-ask-1"]),
                            ("--as without --resolve", ["--as", "proceeded"])]:
            hx.clear()
            res = dc(hx, LS, "decide", *args)
            _check(f"{_T} AC3: {label} exits 1 with empty stdout and no request", res.rc == 1 and res.out == "" and res.err.strip() != "" and not hx.reqs(), res.show())
        _check(f"{_T} AC3: refusals leave the resolved ledger untouched", json.dumps(full_state(hx).get("resolved"), sort_keys=True) == before)
        set_answers(hx, owner_item("ask-1", owner=True, answer="Later owner answer"))
        res = dc(hx, LS, "poll", "--task", TASK)
        pj = parse(res) or {}
        _check(f"{_T} AC3: a later owner answer to a resolved ask still shows in poll",
               pj.get("newAnswers") == 1 and [a.get("ask_id") for a in pj.get("answers", [])] == ["ask-1"], res.show())


# ---------------------------------------------------------------------------
# AC4 Budget
# ---------------------------------------------------------------------------

def _budget(allowance, spent_tokens=0, spent_windows=0, flags=(), env=None, hold=None):
    """Fresh project, claim with the given allowance/spent, one decide.  Returns (res, out, hx-request-count)."""
    with _Hx() as hx:
        claim(hx, allowance=allowance, spent={"windows": spent_windows, "tokens": spent_tokens})
        if hold:
            hold(hx)
        res, out = decide(hx, LS, *flags, env=env)
        return res, out, len(hx.reqs()), hx.jobs()


def test_td_ac4_budget() -> None:
    print(f"{_T} AC4 budget")
    RMF = ["--remaining-minutes", "10"]
    tok = {"tokens": 1000}
    rows = [("allowance null", None, 0, "continue", "no-allowance"), ("allowance {}", {}, 0, "continue", "no-limits"),
            ("tokens 0", {"tokens": 0}, 0, "stop", "zero-allowance"),
            ("spent 790/1000 (79%)", tok, 790, "continue", "under-threshold"), ("spent 799/1000", tok, 799, "continue", "under-threshold"),
            ("spent 800/1000 (80%)", tok, 800, "ask", "most-spent"), ("spent 990/1000 (99%)", tok, 990, "ask", "most-spent"),
            ("spent 1000/1000 (100%)", tok, 1000, "stop", "cap"), ("spent 2500/1000 (250%)", tok, 2500, "stop", "cap")]
    for label, allowance, spent, action, why in rows:
        res, out, n, _ = _budget(allowance, spent, flags=RMF)
        b = (out or {}).get("budget") or {}
        _check(f"{_T} AC4: {label} -> {action} / {why}", res.rc == 0 and (b.get("action"), b.get("why")) == (action, why), res.show())
        _check(f"{_T} AC4: {label}: no open asks -> zero requests; output is strict JSON (no NaN/Infinity)", n == 0 and out is not None and "NaN" not in res.out and "Infinity" not in res.out, res.show())
    res, out, _, _ = _budget(tok, 790, flags=RMF)
    b = out["budget"]
    _check(f"{_T} AC4: ratio is 0.79 at 790/1000 and spent/allowance are echoed",
           abs(b.get("ratio", -1) - 0.79) < 1e-9 and b.get("spent", {}).get("tokens") == 790 and b.get("allowance") == tok and b.get("pending_tokens") == 0, repr(b))
    res, out, _, _ = _budget(tok, 2500, flags=RMF)
    _check(f"{_T} AC4: ratio is clamped to 1 at 250%", out["budget"].get("ratio") == 1, repr(out["budget"]))
    res, out, _, _ = _budget(None, 0, flags=RMF)
    _check(f"{_T} AC4: no allowance -> ratio null", out["budget"].get("ratio") is None, repr(out["budget"]))
    res, out, _, _ = _budget(tok, 800, flags=RMF)
    _check(f"{_T} AC4: the budget ask carries key budget-<task>", out["budget"].get("key") == f"budget-{TASK}", repr(out["budget"]))
    res, out, _, _ = _budget(tok, 800, flags=["--remaining-minutes", "0"])
    _check(f"{_T} AC4: --remaining-minutes 0 at 80% -> continue / nothing-outstanding", (out["budget"]["action"], out["budget"]["why"]) == ("continue", "nothing-outstanding"), repr(out["budget"]))
    res, out, _, _ = _budget(tok, 1000, flags=["--remaining-minutes", "0"])
    _check(f"{_T} AC4: --remaining-minutes 0 does not override the cap (still stop)", out["budget"]["action"] == "stop", repr(out["budget"]))
    res, out, _, _ = _budget(tok, 900, flags=[])
    _check(f"{_T} AC4: without --remaining-minutes there is no budget ask at 90%", out["budget"]["action"] == "continue", repr(out["budget"]))
    # windows
    wa = {"windows": 5}
    res, out, _, _ = _budget(wa, flags=RMF + ["--windows-used", "5"])
    _check(f"{_T} AC4: windows allowance 5, --windows-used 5 -> stop / cap", (out["budget"]["action"], out["budget"]["why"]) == ("stop", "cap"), repr(out["budget"]))
    res, out, _, _ = _budget(wa, flags=RMF + ["--windows-used", "2"])
    _check(f"{_T} AC4: windows allowance 5, --windows-used 2 -> ratio 0.4, continue, nothing unmetered",
           out["budget"]["action"] == "continue" and abs(out["budget"]["ratio"] - 0.4) < 1e-9 and not out["budget"].get("unmetered"), repr(out["budget"]))
    res, out, _, _ = _budget(wa, flags=RMF)
    _check(f"{_T} AC4: windows allowance without --windows-used -> unmetered ['windows'], never stop", out["budget"].get("unmetered") == ["windows"] and out["budget"]["action"] != "stop", repr(out["budget"]))
    res, out, _, _ = _budget(wa, spent_windows=5, flags=RMF)
    _check(f"{_T} AC4: Task&I's own spent.windows still counts without --windows-used (5 of 5 -> stop)", out["budget"]["action"] == "stop", repr(out["budget"]))
    res, out, _, _ = _budget({"tokens": 1000, "windows": 10}, 500, flags=RMF + ["--windows-used", "9"])
    _check(f"{_T} AC4: both dimensions set, windows 90% beats tokens 50% -> ratio 0.9, ask",
           abs(out["budget"]["ratio"] - 0.9) < 1e-9 and out["budget"]["action"] == "ask", repr(out["budget"]))
    res, out, _, _ = _budget({"tokens": 1000, "windows": 10}, 950, flags=RMF + ["--windows-used", "2"])
    _check(f"{_T} AC4: both dimensions set, tokens 95% beats windows 20% -> ratio 0.95", abs(out["budget"]["ratio"] - 0.95) < 1e-9, repr(out["budget"]))
    # spent from the latest record_usage response rather than the claim
    with _Hx() as hx:
        claim(hx, allowance=tok, spent={"windows": 0, "tokens": 0})
        hx.route("record_usage", json={"task": TASK, "spent": {"windows": 0, "tokens": 900}})
        dc(hx, LS - 5000, "enqueue", "record_usage", "--key", "ru-1", stdin=json.dumps(_ru_payload()))
        dc(hx, LS - 5000, "flush")
        res, out = decide(hx, LS, *RMF)
        _check(f"{_T} AC4: spent comes from the latest record_usage response (900, not the claim's 0) -> ask",
               out["budget"]["spent"]["tokens"] == 900 and out["budget"]["action"] == "ask", res.show())
    # a queued usage job counts as pending
    with _Hx() as hx:
        claim(hx, allowance={"tokens": 2000}, spent={"windows": 0, "tokens": 400})
        res, out = decide(hx, LS, *RMF)
        _check(f"{_T} AC4 control: 400/2000 with nothing pending -> continue, pending_tokens 0", out["budget"]["action"] == "continue" and out["budget"]["pending_tokens"] == 0, res.show())
        dc(hx, LS, "enqueue", "record_usage", "--key", "ru-q", stdin=json.dumps(_ru_payload()))
        res, out = decide(hx, LS, *RMF)
        _check(f"{_T} AC4: a queued record_usage job (1000+200+50+10) adds 1260 pending tokens -> (400+1260)/2000 = 0.83 -> ask",
               out["budget"]["pending_tokens"] == 1260 and abs(out["budget"]["ratio"] - 0.83) < 1e-9 and out["budget"]["action"] == "ask", repr(out["budget"]))
    # budget-<task> job suppresses the ask in every state, and never appears in asks
    def budget_job(state):
        def hold(hx):
            route = {"queued": None, "done": {"json": {"ask_id": "bud-1", "placed": "subtask"}},
                     "uncertain": {"status": 500, "json": {"error": "boom"}}, "refused": {"status": 409, "json": {"error": "invalid_request"}}}[state]
            mkask(hx, LS, "bud-1", key=f"budget-{TASK}", blocking=False, flush=state != "queued", route=route)
        return hold
    res, out, n, _ = _budget(tok, 900, flags=RMF)
    _check(f"{_T} AC4 control: with no budget job at 90% the budget ask is raised", out["budget"]["action"] == "ask", repr(out["budget"]))
    for state in ("queued", "done", "uncertain", "refused"):
        res, out, n, jobs = _budget(tok, 900, flags=RMF, hold=budget_job(state))
        got = {j["key"]: j["state"] for j in jobs}.get(f"budget-{TASK}")
        _check(f"{_T} AC4: a {state} budget-<task> job suppresses the budget ask (job really is {state})",
               got == state and out["budget"]["action"] == "continue", f"{got} {out and out.get('budget')}")
        _check(f"{_T} AC4: the {state} budget job never appears in asks/unjudged-as-ask and costs no request",
               all(a["key"] != f"budget-{TASK}" for a in out["asks"]) and n == 0, repr(out)[:300])
    # the env knob
    for value in ("0", "1", "abc", "", "0x1", "-0.5", "1.5"):
        res, out, _, _ = _budget(tok, 600, flags=RMF, env={"VIBE_TASKANDI_BUDGET_ASK": value})
        _check(f"{_T} AC4: VIBE_TASKANDI_BUDGET_ASK={value!r} exits 1 naming the variable with empty stdout",
               res.rc == 1 and res.out == "" and "VIBE_TASKANDI_BUDGET_ASK" in res.err, res.show())
    res, out, _, _ = _budget(tok, 600, flags=RMF, env={"VIBE_TASKANDI_BUDGET_ASK": "0.5"})
    _check(f"{_T} AC4: knob 0.5 is accepted and 60% asks", res.rc == 0 and out["budget"]["action"] == "ask", res.show())
    res, out, _, _ = _budget(tok, 600, flags=RMF, env={"VIBE_TASKANDI_BUDGET_ASK": "0.8"})
    _check(f"{_T} AC4: knob 0.8 is accepted and 60% continues", res.rc == 0 and out["budget"]["action"] == "continue", res.show())


# ---------------------------------------------------------------------------
# AC5 Failure and idle
# ---------------------------------------------------------------------------

def test_td_ac5_failure_and_idle() -> None:
    print(f"{_T} AC5 failure and idle")
    with _Hx() as hx:
        claim(hx, allowance={"tokens": 1000}, spent={"windows": 0, "tokens": 900})
        mkask(hx, LS, "ask-1")
        hx.route("ask_status", status=500, json={"error": "boom"})
        for flag in FLAGS:
            res, out = decide(hx, LS, "--remaining-minutes", "10", *flag)
            a = by_id(out).get("ask-1", {})
            _check(f"{_T} AC5: ask_status 500 ({'--no-other-work' if flag else 'plain'}): exit 0, degraded, status-unavailable, always wait (never park/proceed)",
                   res.rc == 0 and out.get("degraded") == "ask_status" and a.get("action") == "wait" and a.get("why") == "status-unavailable"
                   and out.get("next") not in ("proceed", "park-task"), res.show())
            _check(f"{_T} AC5: degraded output still carries the budget (ask at 90%)", out.get("budget", {}).get("action") == "ask", repr(out.get("budget")))
            _check(f"{_T} AC5: one capabilities and one ask_status request were made", reqs(hx) == (1, 1, 2), repr(reqs(hx)))
        hx.route("ask_status", json={"task": TASK, "asks": [st("ask-1")]})
        res, out = decide(hx, LS)
        _check(f"{_T} AC5 control: with ask_status healthy the same ask is proceed and not degraded", by_id(out).get("ask-1", {}).get("action") == "proceed" and "degraded" not in out, res.show())
        hx.route("capabilities", status=500, json={"error": "boom"})
        res, out = decide(hx, LS)
        _check(f"{_T} AC5: a capabilities failure exits 1 with empty stdout and one stderr line", res.rc == 1 and res.out == "" and len(res.err.strip().splitlines()) == 1, res.show())
    # idle boundary: nothing open -> zero requests
    with _Hx() as hx:
        claim(hx)
        res, out = decide(hx, LS)
        _check(f"{_T} AC5: no open asks -> zero requests, asks empty, next=work", res.rc == 0 and reqs(hx) == (0, 0, 0) and out["asks"] == [] and out["next"] == "work", res.show())
        _check(f"{_T} AC5: output fields bound/task/now/unjudged/budget/reclaimed_parked present",
               out.get("bound") is True and out.get("task") == TASK and out.get("now") == LS and out.get("unjudged") == [] and isinstance(out.get("budget"), dict)
               and out.get("reclaimed_parked") is False, repr(out))
    # no claim
    with _Hx() as hx:
        res = dc(hx, LS, "decide")
        _check(f"{_T} AC5: no claim -> exit 1, exact message, empty stdout, no request",
               res.rc == 1 and res.out == "" and "decide needs the claimed task; run next-task first" in res.err and not hx.reqs(), res.show())
    # MCP binding
    with _Hx(bound=False) as hx:
        p = hx.vibe / "taskandi.json"
        p.write_text(json.dumps({"endpoint": "http://127.0.0.1:9/mcp", "task": "ABBR-1"}))
        os.chmod(p, 0o600)
        res = dc(hx, LS, "decide")
        _check(f"{_T} AC5: an MCP binding -> exit 1 'decide needs a Task&I descriptor binding'",
               res.rc == 1 and res.out == "" and "decide needs a Task&I descriptor binding" in res.err, res.show())
    # unbound
    with _Hx(bound=False) as hx:
        res = dc(hx, LS, "decide")
        _check(f"{_T} AC5: unbound project -> {{bound:false, channel:file-fallback}}, exit 0, no request",
               res.rc == 0 and parse(res) == {"bound": False, "channel": "file-fallback"} and not hx.reqs(), res.show())
    # usage errors
    with _Hx() as hx:
        claim(hx)
        for label, args in [("unknown flag", ["--bogus"]), ("--remaining-minutes without value", ["--remaining-minutes"]),
                            ("--remaining-minutes abc", ["--remaining-minutes", "abc"]), ("--remaining-minutes -1", ["--remaining-minutes", "-1"]),
                            ("--windows-used abc", ["--windows-used", "abc"]), ("repeated --remaining-minutes", ["--remaining-minutes", "1", "--remaining-minutes", "2"]),
                            ("a stray positional", ["extra"])]:
            hx.clear()
            res = dc(hx, LS, "decide", *args)
            _check(f"{_T} AC5: usage error ({label}) -> exit 1, empty stdout", res.rc == 1 and res.out == "" and res.err.strip() != "", res.show())


# ---------------------------------------------------------------------------
# AC6 Reclaim guard, next precedence; A4 release parking
# ---------------------------------------------------------------------------

def _parked_project(hx: _Hx, asks=("ask-1", "ask-2"), release_flags=None, **claim_over) -> None:
    """Claim, ask `asks` (unseen, so they wait), then release with --parked-asks."""
    claim(hx, None, **claim_over)
    for aid in asks:
        mkask(hx, None, aid)
    set_status(hx, *[st(a, seen=None) for a in asks])
    flags = release_flags if release_flags is not None else ["--parked-asks", ",".join(asks)]
    res = dc(hx, None, "release", "--task", TASK, "--reason", "Waiting on questions.", *flags)
    _check(f"{_T} setup: the parking release succeeds", res.rc == 0, res.show())
    time.sleep(0.05)


def test_td_ac6_reclaim_guard() -> None:
    print(f"{_T} AC6 reclaim guard and next precedence")
    with _Hx() as hx:
        _parked_project(hx)
        s = full_state(hx)
        p = (s.get("parked") or [{}])[0]
        _check(f"{_T} AC6/A4: release --parked-asks deletes the claim and writes parked {{task, openAskIds, budgetStopped false, allowance, at}}",
               "claimed" not in s and p.get("task") == TASK and sorted(p.get("openAskIds", [])) == ["ask-1", "ask-2"] and p.get("budgetStopped") is False
               and p.get("allowance") == {"tokens": 10 ** 7} and "at" in p, repr(s.get("parked")))
        claim(hx, None)
        for flag in FLAGS:
            res, out = decide(hx, None, *flag)
            _check(f"{_T} AC6: after a park, the same task from next_task -> reclaimed_parked true, next release-again ({'--no-other-work' if flag else 'plain'}; beats park-task)",
                   res.rc == 0 and out.get("reclaimed_parked") is True and out.get("next") == "release-again", res.show())
        # an owner answer arrives for one parked ask -> not a reclaim of unchanged state
        set_answers(hx, owner_item("ask-1", owner=True))
        time.sleep(0.05)
        dc(hx, None, "poll", "--task", TASK)
        res, out = decide(hx, None)
        _check(f"{_T} AC6: a new owner answer since parking -> reclaimed_parked false, next work (ask-2 still waits)",
               out.get("reclaimed_parked") is False and out.get("next") == "work", res.show())
        res, out = decide(hx, None, "--no-other-work")
        _check(f"{_T} AC6: ... and with --no-other-work the unanswered ask parks the task again (park-task)", out.get("next") == "park-task", res.show())
    with _Hx() as hx:
        _parked_project(hx)
        claim(hx, None)
        mkask(hx, None, "ask-3")
        set_status(hx, st("ask-1", seen=None), st("ask-2", seen=None), st("ask-3", seen=None))
        res, out = decide(hx, None)
        _check(f"{_T} AC6: the open ask set changed (new ask-3) -> reclaimed_parked false, next work", out.get("reclaimed_parked") is False and out.get("next") == "work", res.show())
    # parked, but the latest start has since passed: progress, not release-again
    with _Hx() as hx:
        _parked_project(hx, defaults_allowed=False)
        claim(hx, None, hardDeadline=int(time.time() * 1000) - 3600_000, defaults_allowed=True)
        set_status(hx, st("ask-1"), st("ask-2", seen=None))
        res, out = decide(hx, None)
        _check(f"{_T} AC6: a parked task whose latest start has passed and defaults are allowed -> next proceed (not release-again)",
               by_id(out).get("ask-1", {}).get("action") == "proceed" and out.get("next") == "proceed", res.show())
    # budget-stopped reclaim
    tok = {"tokens": 1000}
    with _Hx() as hx:
        _parked_project(hx, asks=(), release_flags=["--budget-stopped"], allowance=tok, spent={"windows": 0, "tokens": 1000})
        p = (full_state(hx).get("parked") or [{}])[0]
        _check(f"{_T} AC6/A4: release --budget-stopped writes parked budgetStopped true with the claim's allowance",
               p.get("budgetStopped") is True and p.get("allowance") == tok and p.get("openAskIds") == [], repr(p))
        claim(hx, None, allowance=tok, spent={"windows": 0, "tokens": 1000})
        res, out = decide(hx, None, "--remaining-minutes", "5")
        _check(f"{_T} AC6: budget-stopped, allowance unchanged, spent at the cap -> reclaimed true, next release-again (not stop)",
               out.get("reclaimed_parked") is True and out.get("budget", {}).get("why") == "cap" and out.get("next") == "release-again", res.show())
        claim(hx, None, allowance={"tokens": 2000}, spent={"windows": 0, "tokens": 1000})
        res, out = decide(hx, None, "--remaining-minutes", "5")
        _check(f"{_T} AC6: budget-stopped, allowance grown -> reclaimed false, budget continue, next work",
               out.get("reclaimed_parked") is False and out.get("budget", {}).get("action") == "continue" and out.get("next") == "work", res.show())
    with _Hx() as hx:
        _parked_project(hx, asks=(), release_flags=["--budget-stopped"], allowance={"tokens": 1000, "windows": 5})
        claim(hx, None, allowance={"tokens": 1000, "windows": 6})
        res, out = decide(hx, None)
        _check(f"{_T} AC6: allowance larger in any one dimension (windows 5 -> 6) -> reclaimed false", out.get("reclaimed_parked") is False, res.show())
    # stop vs proceed precedence; fresh capped claim
    with _Hx() as hx:
        claim(hx, LS, allowance=tok, spent={"windows": 0, "tokens": 1000})
        mkask(hx, LS, "ask-1")
        set_status(hx, st("ask-1"))
        res, out = decide(hx, LS)
        _check(f"{_T} AC6: a capped, never-parked task -> next stop even over a proceed-eligible ask (hard limit)",
               by_id(out).get("ask-1", {}).get("action") == "proceed" and out.get("next") == "stop", res.show())
    with _Hx() as hx:
        claim(hx, LS, allowance=tok, spent={"windows": 0, "tokens": 0})
        res, out = decide(hx, LS)
        _check(f"{_T} AC6 control: uncapped, nothing open, never parked -> next work, reclaimed false", out.get("next") == "work" and out.get("reclaimed_parked") is False, res.show())
    # zero allowance is also a hard stop
    res, out, _, _ = _budget({"tokens": 0}, 0)
    _check(f"{_T} AC6: zero-allowance -> next stop", out.get("next") == "stop", repr(out)[:200])


def test_td_a4_release_flags_and_windows_used() -> None:
    print(f"{_T} A4 release flags, pendingDirect, windows-used")
    with _Hx() as hx:
        claim(hx, None)
        res = dc(hx, None, "release", "--task", TASK, "--reason", "plain")
        s = full_state(hx)
        _check(f"{_T} A4: control - a plain release deletes the claim and writes no parked entry", res.rc == 0 and "claimed" not in s and not s.get("parked"), res.show() + repr(s.get("parked")))
    with _Hx() as hx:
        claim(hx, None)
        for label, args in [("--budget-stopped with a value", ["--budget-stopped", "yes"]),
                            ("--budget-stopped repeated", ["--budget-stopped", "--budget-stopped"]),
                            ("--parked-asks without a value", ["--parked-asks"])]:
            hx.clear()
            res = dc(hx, None, "release", "--task", TASK, "--reason", "r", *args)
            _check(f"{_T} A4: release {label} exits 1 and sends nothing, keeping the claim",
                   res.rc == 1 and res.out == "" and not hx.reqs() and full_state(hx).get("claimed"), res.show())
        for label, args in [("--no-other-work with a value", ["--no-other-work", "yes"]), ("--no-other-work repeated", ["--no-other-work", "--no-other-work"])]:
            res = dc(hx, None, "decide", *args)
            _check(f"{_T} A4: decide {label} exits 1", res.rc == 1 and res.out == "", res.show())
        res = dc(hx, None, "release", "--task", TASK, "--reason", "r", "--budget-stopped", "--parked-asks", "ask-1")
        _check(f"{_T} A4: control - valueless --budget-stopped together with --parked-asks is accepted", res.rc == 0, res.show())
    # an unknown release outcome carries the parking data into pendingDirect; reconcile --direct done writes parked
    with _Hx() as hx:
        claim(hx, None, allowance={"tokens": 1000})
        mkask(hx, None, "ask-1")      # rev 7 AC36: the park records the open blocking asks found in state
        mkask(hx, None, "ask-2")
        hx.route("release", status=500, json={"error": "boom"})
        res = dc(hx, None, "release", "--task", TASK, "--reason", "r", "--parked-asks", "ask-1,ask-2", "--budget-stopped")
        pd = json.dumps(full_state(hx).get("pendingDirect"))
        _check(f"{_T} A4: an unknown release outcome stores parkedAsks, budgetStopped and allowance in pendingDirect",
               res.rc == 1 and "parkedAsks" in pd and "ask-1" in pd and "budgetStopped" in pd and "allowance" in pd and "1000" in pd, res.show() + pd)
        res = dc(hx, None, "reconcile", "--direct", "release", "--task", TASK, "--action", "done", "--evidence", "comment visible")
        p = (full_state(hx).get("parked") or [{}])[0]
        _check(f"{_T} A4: reconcile --direct release --action done writes the parked entry too",
               res.rc == 0 and p.get("task") == TASK and p.get("budgetStopped") is True and sorted(p.get("openAskIds", [])) == ["ask-1", "ask-2"], res.show() + repr(p))
    with _Hx() as hx:
        claim(hx, LS)
        for given, want in ((3, 3), (1, 3), (7, 7)):
            res, out = decide(hx, LS, "--windows-used", str(given))
            _check(f"{_T} A4: --windows-used {given} -> windowsUsed[{TASK}] = {want} (max of stored and given)",
                   res.rc == 0 and full_state(hx).get("windowsUsed", {}).get(TASK) == want, res.show() + repr(full_state(hx).get("windowsUsed")))


# ---------------------------------------------------------------------------
# AC7 Storage
# ---------------------------------------------------------------------------

def test_td_ac7_storage() -> None:
    print(f"{_T} AC7 storage")
    with _Hx() as hx:
        fpc = "out.fp = C.bindingFingerprint(C.loadConfig(cwd));"
        before = hx.lib(fpc).get("fp")
        res = claim(hx, LS, allowance={"tokens": 5000, "windows": 3}, spent={"windows": 1, "tokens": 77}, defaults_allowed=True, estimate_minutes=12, latest_start=H - 1000)
        c = hx.claimed() or {}
        _check(f"{_T} AC7: the claim stores allowance, spent, defaults_allowed, estimate_minutes, hardDeadline, latest_start",
               res.rc == 0 and c.get("allowance") == {"tokens": 5000, "windows": 3} and c.get("spent") == {"windows": 1, "tokens": 77}
               and c.get("defaults_allowed") is True and c.get("estimate_minutes") == 12 and c.get("hardDeadline") == H and c.get("latest_start") == H - 1000
               and c.get("task") == TASK and c.get("session") == SESSION, repr(c))
        _check(f"{_T} AC7: bindingFingerprint is identical before and after a claim", before and before == hx.lib(fpc).get("fp"), repr(before))
    with _Hx() as hx:
        claim(hx, LS, hardDeadline=_DROP, defaults_allowed=False)
        c = hx.claimed() or {}
        _check(f"{_T} AC7: optional hardDeadline / latest_start / estimate_minutes are not invented when absent; defaults_allowed false is kept",
               "hardDeadline" not in c and "latest_start" not in c and c.get("defaults_allowed") is False, repr(c))
    with _Hx() as hx:
        t0 = LS
        claim(hx, t0, spent={"windows": 0, "tokens": 10})
        # ask job after a successful flush
        mkask(hx, t0 + 1000, "ask-s", key="ask-s", rm=33, blocking=False, reversible=False)
        j = hx.job("ask-s") or {}
        _check(f"{_T} AC7: a flushed v2.2 ask job stores result.ask_id/placed, the full payload, doneAt and doneAtMs",
               j.get("state") == "done" and j.get("result") == {"ask_id": "ask-s", "placed": "subtask"}
               and all(j.get("payload", {}).get(k) == v for k, v in (("reversible", False), ("blocking", False), ("remaining_minutes", 33), ("default", "Use X"), ("question", "Question ask-s?")))
               and isinstance(j.get("doneAtMs"), int) and isinstance(j.get("doneAt"), str), repr(j))
        if isinstance(j.get("doneAtMs"), int) and isinstance(j.get("doneAt"), str):
            from datetime import datetime
            ms = int(datetime.fromisoformat(j["doneAt"].replace("Z", "+00:00")).timestamp() * 1000)
            _check(f"{_T} AC7: doneAt (ISO) and doneAtMs name the same instant (within 1 s)", abs(ms - j["doneAtMs"]) < 1000, repr((j["doneAt"], j["doneAtMs"])))
        # record_usage response updates the claim, with spentAt
        hx.route("record_usage", json={"task": TASK, "spent": {"windows": 0, "tokens": 1260}})
        dc(hx, t0 + 100_000, "enqueue", "record_usage", "--key", "ru", stdin=json.dumps(_ru_payload()))
        dc(hx, t0 + 100_000, "flush")
        c = hx.claimed() or {}
        _check(f"{_T} AC7: after a record_usage response the claim has spent = the response's and a spentAt (ms)",
               c.get("spent") == {"windows": 0, "tokens": 1260} and isinstance(c.get("spentAt"), int), repr(c))
        spent_at = c.get("spentAt")
        # renewal with an older clock keeps the newer record_usage spent; renewal later takes the newer spent
        claim(hx, t0 + 50_000, spent={"windows": 0, "tokens": 5})
        c = hx.claimed() or {}
        _check(f"{_T} AC7: a renewal whose time is older than the record_usage keeps the newer spent (1260, not 5)", c.get("spent", {}).get("tokens") == 1260, repr(c))
        claim(hx, t0 + 900_000, spent={"windows": 0, "tokens": 4000})
        c = hx.claimed() or {}
        _check(f"{_T} AC7: control - a later renewal keeps a consistent spent (1260 or 4000: spec ambiguity on whose time a renewal counts at)", c.get("spent", {}).get("tokens") in (1260, 4000) and c.get("spentAt", 0) >= (spent_at or 0), repr(c))
        # a record_usage response for a different task does not touch the claim
        hx.route("record_usage", json={"task": "other-task", "spent": {"windows": 0, "tokens": 1}})
        before = (hx.claimed() or {}).get("spent")
        dc(hx, t0 + 1_000_000, "enqueue", "record_usage", "--key", "ru-other", "--task", "other-task", stdin=json.dumps(_ru_payload()))
        dc(hx, t0 + 1_000_000, "flush")
        _check(f"{_T} AC7: a record_usage response for another task leaves the claim's spent alone", (hx.claimed() or {}).get("spent") == before, repr(hx.claimed()))
        s = full_state(hx)
        _check(f"{_T} AC7: old-state compatibility - ledgers load empty (resolved/parked lists, windowsUsed map)",
               not s.get("resolved") and not s.get("parked") and not s.get("windowsUsed"), repr({k: s.get(k) for k in ("resolved", "parked", "windowsUsed")}))


# ---------------------------------------------------------------------------
# AC7b Claude transcripts
# ---------------------------------------------------------------------------

_MA, _MB = "claude-test-sonnet", "claude-test-opus"


def _rec(mid, model, i=None, o=None, cr=None, cw=None, extra=True):
    usage = {}
    for k, v in (("input_tokens", i), ("output_tokens", o), ("cache_read_input_tokens", cr), ("cache_creation_input_tokens", cw)):
        if v is not None:
            usage[k] = v
    if extra:
        usage.update(service_tier="standard", server_tool_use={"web_search_requests": 0})
    return json.dumps({"type": "assistant", "message": {"id": mid, "model": model, "role": "assistant", "usage": usage}})


def _usage_jobs(hx: _Hx) -> list:
    return [j for j in hx.jobs() if j.get("kind") == "record_usage"]


def _jkey(session, model, last_id):
    return "usage-" + hashlib.sha256(json.dumps([session, model, last_id], separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()[:16]


def test_td_ac7b_claude_usage() -> None:
    print(f"{_T} AC7b Claude transcript usage")
    with _Hx() as hx:
        claim(hx, LS)
        tr = hx.base / "claude-session.jsonl"
        sub = hx.base / "claude-session" / "subagents"
        sub.mkdir(parents=True)
        main_lines = [json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}),
                      _rec("m1", _MA, 10, 1), _rec("m1", _MA, 10, 5, 100), _rec("m1", _MA, 10, 9, 100, 20),
                      _rec("m2", _MB, 7, 3), _rec("m3", _MA, 5, 5, 5, 5),
                      _rec("s1", "<synthetic>", 0, 0, 0, 0),
                      json.dumps({"type": "summary", "summary": "x"})]
        tr.write_text("\n".join(main_lines) + "\n")
        (sub / "agent-1.jsonl").write_text(_rec("m5", _MB, 2, 4, 6, 8) + "\n")
        args = ["usage", "--transcript", str(tr), "--session", "sess-1", "--account", "acct", "--cost-estimate", "0"]
        hx.clear()
        res = dc(hx, LS, *args)
        jobs = _usage_jobs(hx)
        pay = {j["payload"]["model"]: j["payload"] for j in jobs}
        _check(f"{_T} AC7b: exactly one record_usage job per model (two), no network call", res.rc == 0 and len(jobs) == 2 and set(pay) == {_MA, _MB} and not hx.reqs(), res.show() + repr(pay))
        a, b = pay.get(_MA, {}), pay.get(_MB, {})
        _check(f"{_T} AC7b: model A sums the LAST record of m1 plus m3 (input 15, output 14, cache_read 105, cache_write 25)",
               (a.get("input"), a.get("output"), a.get("cache_read"), a.get("cache_write")) == (15, 14, 105, 25), repr(a))
        _check(f"{_T} AC7b: model B sums m2 plus the subagent's m5 (input 9, output 7, cache_read 6, cache_write 8); <synthetic> is excluded",
               (b.get("input"), b.get("output"), b.get("cache_read"), b.get("cache_write")) == (9, 7, 6, 8) and "<synthetic>" not in pay, repr(b))
        _check(f"{_T} AC7b: payload carries account and cost_estimate 0",
               a.get("account") == "acct" and a.get("cost_estimate") == 0 and b.get("account") == "acct", repr(a))
        keys = {j["payload"]["model"]: j["key"] for j in jobs}
        _check(f"{_T} AC7b: job key is usage-<16 hex of sha256([session, model, last message id])>",
               keys[_MA] == _jkey("sess-1", _MA, "m3") and keys[_MB] in (_jkey("sess-1", _MB, "m5"), _jkey("sess-1", _MB, "m2")), repr(keys))
        # second run with one new message for model A
        with tr.open("a") as fh:
            fh.write(_rec("m6", _MA, 1, 2, 3, 4) + "\n")
        res = dc(hx, LS, *args)
        jobs2 = _usage_jobs(hx)
        new = [j for j in jobs2 if j["key"] not in {x["key"] for x in jobs}]
        _check(f"{_T} AC7b: a second run with one new message enqueues exactly one job, for that model, with only the new tokens",
               res.rc == 0 and len(new) == 1 and new[0]["payload"]["model"] == _MA and
               (new[0]["payload"]["input"], new[0]["payload"]["output"], new[0]["payload"]["cache_read"], new[0]["payload"]["cache_write"]) == (1, 2, 3, 4), res.show() + repr(new))
        res = dc(hx, LS, *args)
        pj = parse(res) or {}
        _check(f"{_T} AC7b: re-importing with nothing new adds no job", res.rc == 0 and len(_usage_jobs(hx)) == 3 and pj.get("enqueued") == 0, res.show())
        # a different session id imports independently (the imported set is per session and file)
        res = dc(hx, LS, "usage", "--transcript", str(tr), "--session", "sess-2", "--account", "acct", "--cost-estimate", "0")
        _check(f"{_T} AC7b: control - another session over the same file imports afresh (2 models -> 5 jobs)", res.rc == 0 and len(_usage_jobs(hx)) == 5, res.show())
        # half-written final line is ignored
        with tr.open("a") as fh:
            fh.write('{"type":"assistant","message":{"id":"m7","model":"' + _MA + '","usa')
        res = dc(hx, LS, *args)
        _check(f"{_T} AC7b: a half-written final line (no newline) is ignored: exit 0, no new job", res.rc == 0 and len(_usage_jobs(hx)) == 5, res.show())
        # a malformed middle line fails
        bad = hx.base / "bad.jsonl"
        bad.write_text(_rec("x1", _MA, 1, 1) + "\n" + '{"type":"assistant","message":{"id":"x2","mod\n' + _rec("x3", _MA, 1, 1) + "\n")
        n0 = len(_usage_jobs(hx))
        res = dc(hx, LS, "usage", "--transcript", str(bad), "--session", "sess-3", "--account", "acct", "--cost-estimate", "0")
        _check(f"{_T} AC7b: a malformed middle line fails the import (exit 1) and enqueues nothing", res.rc == 1 and len(_usage_jobs(hx)) == n0, res.show())
        good = hx.base / "good.jsonl"
        good.write_text(_rec("x1", _MA, 1, 1) + "\n" + _rec("x3", _MA, 1, 1) + "\n")
        res = dc(hx, LS, "usage", "--transcript", str(good), "--session", "sess-3", "--account", "acct", "--cost-estimate", "0")
        _check(f"{_T} AC7b: control - the same file without the bad line imports (exit 0, one job)", res.rc == 0 and len(_usage_jobs(hx)) == n0 + 1, res.show())
        # absent usage fields are 0
        sparse = hx.base / "sparse.jsonl"
        sparse.write_text(_rec("p1", _MB, 4, 6, extra=False) + "\n")
        res = dc(hx, LS, "usage", "--transcript", str(sparse), "--session", "sess-4", "--account", "acct", "--cost-estimate", "0")
        p = [j for j in _usage_jobs(hx) if j["key"] == _jkey("sess-4", _MB, "p1")]
        _check(f"{_T} AC7b: absent cache fields count as 0", res.rc == 0 and len(p) == 1 and p[0]["payload"]["cache_read"] == 0 and p[0]["payload"]["cache_write"] == 0, res.show())
        # a Codex rollout is still imported by the old path
        codex = hx.base / "rollout.jsonl"
        codex.write_text("\n".join(json.dumps(r) for r in [
            {"type": "turn_context", "payload": {"model": "gpt-test"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 10, "cache_write_input_tokens": 0, "output_tokens": 20}}}}]) + "\n")
        res = dc(hx, LS, "usage", "--transcript", str(codex), "--session", "sess-5", "--account", "acct", "--cost-estimate", "0")
        _check(f"{_T} AC7b: control - a Codex rollout still imports one job (old path unchanged)", res.rc == 0 and (parse(res) or {}).get("enqueued") == 1, res.show())


# ---------------------------------------------------------------------------
# AC7c Pruning
# ---------------------------------------------------------------------------

def test_td_ac7c_pruning() -> None:
    print(f"{_T} AC7c pruning")
    with _Hx() as hx:
        hx.enqueue("comment", "seed", {"text": "x"}, task="project")
        hx.cli("flush")
        hx.enqueue("ask", "seed-ask", _fixture_payload("ask"), task="project")
        hx.cli("flush")
        s = full_state(hx)
        seed, seed_ask = copy.deepcopy(hx.job("seed")), copy.deepcopy(hx.job("seed-ask"))
        _check(f"{_T} AC7c setup: seed comment and ask jobs are done with doneAtMs", seed and seed_ask and seed["state"] == "done" and seed_ask["state"] == "done"
               and isinstance(seed.get("doneAtMs"), int), repr(seed))
        if not (seed and seed_ask and isinstance(seed.get("doneAtMs"), int)):
            return
        jobs = []
        for i in range(2100):
            j = copy.deepcopy(seed)
            j.update(key=f"c{i}", doneAtMs=1_000_000 + i, doneAt=_iso(1_000_000 + i))
            jobs.append(j)
        for name, ms in (("open", 1), ("owner", 2), ("res", 3)):
            j = copy.deepcopy(seed_ask)
            j.update(key=f"ask-{name}", doneAtMs=ms, doneAt=_iso(ms))
            j["result"] = {"ask_id": f"id-{name}", "placed": "subtask"}
            jobs.append(j)
        for name, state in (("q", "queued"), ("u", "uncertain"), ("r", "refused"), ("d", "dispatching")):
            j = copy.deepcopy(seed)
            j.update(key=f"nd-{name}", state=state)
            j.pop("doneAtMs", None)
            j.pop("doneAt", None)
            jobs.append(j)
        s["jobs"] = jobs
        s.setdefault("answers", []).append({"task": "project", "id": "id-owner", "content": "yes", "ownerAnswer": True, "seenAt": 1, "answeredAt": 2, "answeredBy": "me", "receivedAt": _iso(5)})
        s["resolved"] = [{"task": "project", "ask_id": "id-res", "as": "proceeded", "at": 5}]
        (hx.vibe / "taskandi-outbox" / "state.json").write_text(json.dumps(s))
        res = hx.enqueue("comment", "trigger", {"text": "t"}, task="project")
        keys = {j["key"]: j for j in hx.jobs()}
        _check(f"{_T} AC7c: the triggering write succeeds", res.rc == 0 and "trigger" in keys, res.show())
        _check(f"{_T} AC7c: the newest 2000 done jobs are kept (c102..c2099 all present)", all(f"c{i}" in keys for i in range(102, 2100)), f"missing {[i for i in range(102, 2100) if f'c{i}' not in keys][:5]}")
        _check(f"{_T} AC7c: the oldest 100 done jobs are dropped (c0..c97 gone)", not any(f"c{i}" in keys for i in range(0, 98)), f"present {[i for i in range(0, 98) if f'c{i}' in keys][:5]}")
        _check(f"{_T} AC7c: every non-done job survives (queued, uncertain, refused, dispatching)", all(f"nd-{n}" in keys for n in "qurd"), repr(sorted(k for k in keys if k.startswith('nd-'))))
        _check(f"{_T} AC7c: the old done ask behind an OPEN ask is kept", "ask-open" in keys)
        _check(f"{_T} AC7c: old done asks with an owner answer, or resolved, are pruned like any done job", "ask-owner" not in keys and "ask-res" not in keys, repr([k for k in keys if k.startswith('ask-')]))
        size = (hx.vibe / "taskandi-outbox" / "state.json").stat().st_size
        _check(f"{_T} AC7c: state.json stays far below the 4 MiB read cap ({size} bytes)", size < 2 * 1024 * 1024)
        _check(f"{_T} AC7c: the client still reads the pruned state (status works)", (hx.cli("status").json() or {}).get("counts", {}).get("queued", 0) >= 2)


# ---------------------------------------------------------------------------
# AC8 Body cap
# ---------------------------------------------------------------------------

def _body_of(out):
    def walk(o):
        if isinstance(o, dict):
            if "body" in o and "title" in o:
                return o
            for v in o.values():
                r = walk(v)
                if r is not None:
                    return r
        return None
    return walk(out) or {}


def test_td_ac8_body_cap() -> None:
    print(f"{_T} AC8 body cap")
    full = "é€" * 524288                       # 1 MiB of code points, BMP only
    with _Hx() as hx:
        hx.route("next_task", json=nt(body=full))
        res = dc(hx, LS, "next-task", "--agent", "claude", "--session", SESSION)
        out = parse(res)
        t = _body_of(out)
        _check(f"{_T} AC8: a 1 MiB body is printed truncated to 20000 code points with body_truncated and body_chars",
               res.rc == 0 and t.get("body") == full[:20000] and t.get("body_truncated") is True and t.get("body_chars") == len(full), res.show()[:300])
        _check(f"{_T} AC8: stdout never holds the full body", len(res.out) < 200_000 and full[:30000] not in res.out, f"{len(res.out)} bytes")
        bf = t.get("body_file")
        path = (hx.repo / bf) if bf and not os.path.isabs(bf) else Path(bf or hx.vibe / "taskandi-body.txt")
        _check(f"{_T} AC8: body_file names .vibe/taskandi-body.txt", isinstance(bf, str) and bf.endswith(".vibe/taskandi-body.txt") or bf == ".vibe/taskandi-body.txt", repr(bf))
        _check(f"{_T} AC8: the file holds the full body, mode 0600", path.exists() and path.read_text(encoding="utf-8") == full and stat.S_IMODE(path.stat().st_mode) == 0o600,
               f"{path} {path.exists() and oct(path.stat().st_mode)}")
        ls = subprocess.run(["git", "ls-files", "--", ".vibe/taskandi-body.txt"], cwd=str(hx.repo), input="", capture_output=True, text=True).stdout
        _check(f"{_T} AC8: the body file is untracked", ls.strip() == "")
        res = dc(hx, LS, "next-task", "--agent", "claude", "--session", SESSION, "--body-max-chars", "10")
        t = _body_of(parse(res))
        _check(f"{_T} AC8: --body-max-chars 10 prints 10 code points", res.rc == 0 and t.get("body") == full[:10] and t.get("body_truncated") is True and t.get("body_chars") == len(full), res.show()[:300])
        hx.route("next_task", json=nt(body="short body"))
        res = dc(hx, LS, "next-task", "--agent", "claude", "--session", SESSION)
        t = _body_of(parse(res))
        _check(f"{_T} AC8: control - a short body prints whole, with no body_truncated", t.get("body") == "short body" and "body_truncated" not in t, res.show()[:300])
        _check(f"{_T} AC8: the body file is overwritten each claim (now the short body)", (hx.vibe / "taskandi-body.txt").exists() and (hx.vibe / "taskandi-body.txt").read_text(encoding="utf-8") == "short body")
        astral = "a\U0001F600b\U0001F600c"
        hx.route("next_task", json=nt(body=astral))
        res = dc(hx, LS, "next-task", "--agent", "claude", "--session", SESSION, "--body-max-chars", "3")
        t = _body_of(parse(res))
        _check(f"{_T} AC8: the cap counts code points, not UTF-16 units ('a<emoji>b')", t.get("body") == "a\U0001F600b" and t.get("body_truncated") is True and t.get("body_chars") in (5, 7), res.show()[:300])


# ---------------------------------------------------------------------------
# A6 --check-argv
# ---------------------------------------------------------------------------

def test_td_a6_check_argv() -> None:
    print(f"{_T} A6 --check-argv")
    ok = [("decide --remaining-minutes 5 --windows-used 2 --no-other-work", ["decide", "--remaining-minutes", "5", "--windows-used", "2", "--no-other-work"], ""),
          ("decide --resolve k --as proceeded", ["decide", "--resolve", "k", "--as", "proceeded"], ""),
          ("release with parking flags", ["release", "--task", TASK, "--reason", "r", "--parked-asks", "a,b", "--budget-stopped"], ""),
          ("next-task with --body-max-chars", ["next-task", "--agent", "claude", "--session", SESSION, "--body-max-chars", "5"], ""),
          ("enqueue comment", ["enqueue", "comment", "--key", "k"], json.dumps({"text": "hi"})),
          ("status", ["status"], ""), ("flush", ["flush"], ""), ("poll", ["poll"], "")]
    bad = [("decide --bogus", ["decide", "--bogus"], ""), ("decide --remaining-minutes without value", ["decide", "--remaining-minutes"], ""),
           ("decide --no-other-work with a value", ["decide", "--no-other-work", "yes"], ""), ("release --budget-stopped with a value", ["release", "--task", TASK, "--reason", "r", "--budget-stopped", "x"], ""),
           ("unknown subcommand", ["frobnicate"], ""), ("enqueue ask with a bad flag", ["enqueue", "ask", "--key", "k", "--bogus", "x"], json.dumps({"question": "q"})),
           ("enqueue comment with a non-object stdin", ["enqueue", "comment", "--key", "k"], "[1,2]"),
           ("next-task without --session", ["next-task", "--agent", "claude"], "")]
    for label, root in (("an unbound project with no .vibe at all", None), ("a bound project", _Hx())):
        td = None
        try:
            if root is None:
                td = tempfile.TemporaryDirectory(prefix="td-checkargv-")
                cwd = Path(td.name)
                subprocess.run(["git", "init", "-q", str(cwd)], check=True, input="", capture_output=True, text=True)
            else:
                cwd = root.repo
            env = {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")} | {"VIBE_CONTAINER": "0"}
            for name, argv, stdin in ok:
                r = subprocess.run(["node", str(_CLIENT), "--check-argv", *argv], cwd=str(cwd), input=stdin, capture_output=True, text=True, timeout=60, env=env)
                _check(f"{_T} A6 ({label}): --check-argv {name} -> {{\"ok\":true}} exit 0", r.returncode == 0 and json.loads(r.stdout or "null") == {"ok": True}, f"rc={r.returncode} {r.stdout!r} {r.stderr[:200]!r}")
            for name, argv, stdin in bad:
                r = subprocess.run(["node", str(_CLIENT), "--check-argv", *argv], cwd=str(cwd), input=stdin, capture_output=True, text=True, timeout=60, env=env)
                _check(f"{_T} A6 ({label}): --check-argv {name} -> exit 1, empty stdout", r.returncode == 1 and r.stdout == "" and r.stderr.strip() != "", f"rc={r.returncode} {r.stdout!r} {r.stderr[:200]!r}")
            if root is not None:
                _check(f"{_T} A6: --check-argv made no network call and left no outbox state", not root.reqs() and root.state() is None, repr(root.actions()))
            else:
                _check(f"{_T} A6: --check-argv created no .vibe state in an unbound project", not (cwd / ".vibe").exists())
        finally:
            if root is not None:
                root.__exit__(None, None, None)
            if td is not None:
                td.cleanup()


_TESTS = [test_td_ac1_conditions_per_ask, test_td_ac1_task_level_conditions, test_td_ac2_answered_and_unjudged, test_td_ac3_resolve,
          test_td_ac4_budget, test_td_ac5_failure_and_idle, test_td_ac6_reclaim_guard, test_td_a4_release_flags_and_windows_used,
          test_td_ac7_storage, test_td_ac7b_claude_usage, test_td_ac7c_pruning, test_td_ac8_body_cap, test_td_a6_check_argv]


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
    print("PASS: task_065 decide acceptance checks")
