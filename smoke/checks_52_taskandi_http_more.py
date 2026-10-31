#!/usr/bin/env python3
"""Acceptance checks for the Task&I contract v2.2 HTTP transport (task_064), part 2.

Tester-owned (cycle 1).  AC9-AC18.  The harness (loopback Node server, throwaway
git project, descriptor writer, CLI runner) lives in checks_50_taskandi_http.py.

Run only this module with:
    python3 smoke/checks_52_taskandi_http_more.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import (_CLIENT, _CONN, _DROP, _FIX_BRAIN, _FIX_REPO, _HOSTILE, _LEAKS, _NAMES, _REPO,
                                           _T1, _TOKEN, _WS, _RESULTS, _Hx, _check, _fixture, _fixture_payload, _iso, _la, _canon_digest)

_DOCS = _REPO / "docs" / "taskandi-client.md"
_NO_BOUND = "no bound task: the connection covers the whole workspace; claim one with next-task"
_NEED_SESSION = "complete/release needs the session that claimed the task; run next-task first"
_UNUSABLE = "task id not usable by vibe: rename it in Task&I or recreate the task"


def _nt(**over) -> dict:
    r = copy.deepcopy(_fixture("next_task")["response"])
    for k, v in over.items():
        if v is _DROP:
            r.pop(k, None)
        else:
            r[k] = v
    return r


def _next(hx: _Hx, session="session-a") -> object:
    return hx.cli("next-task", "--agent", "claude", "--session", session)


def _ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# AC9 / AC17 next_task shape and unusable ids
# ---------------------------------------------------------------------------

def test_taskandi_http_ac9_next_task_shape() -> None:
    print("[taskandi-http] AC9 next_task shape")
    accept = [("allowance null", _nt(allowance=None)), ("allowance {}", _nt(allowance={})),
              ("priority null", _nt(priority=None)), ("effective_priority null", _nt(effective_priority=None)),
              ("no hardDeadline", _nt(hardDeadline=_DROP)), ("latest_start present", _nt(latest_start=_T1)),
              ("defaults_allowed true", _nt(defaults_allowed=True)), ("empty body string", _nt(body=""))]
    for label, resp in accept:
        with _Hx() as hx:
            hx.route("next_task", json=resp)
            res = _next(hx)
            printed = (res.json() or {}).get("task") or {}
            ok = res.rc == 0 and (hx.claimed() or {}).get("task") == "leaf-b" and printed.get("task") == "leaf-b"
            if label == "defaults_allowed true":
                ok = ok and printed.get("defaults_allowed") is True
            if label == "no hardDeadline":
                ok = ok and "hardDeadline" not in printed
            _check(f"[taskandi-http] AC9: accepted and stored as the claim - {label}", ok, res.show())
    with _Hx() as hx:
        hx.route("next_task", json={"task": None})
        res = _next(hx)
        _check("[taskandi-http] AC9: control - {task:null} is valid: exit 0, printed task null",
               res.rc == 0 and res.json() == {"bound": True, "channel": "taskandi-http", "task": None}, res.show())
    refuse = [("hardDeadline null", _nt(hardDeadline=None)), ("missing defaults_allowed", _nt(defaults_allowed=_DROP)),
              ("owner null", _nt(owner=None)), ("allowance {windows:null}", _nt(allowance={"windows": None})),
              ("missing lease", _nt(lease=_DROP)), ("{task:null, x:1}", {"task": None, "x": 1}),
              ("unknown extra key", _nt(surprise=1)), ("defaults_allowed 'yes'", _nt(defaults_allowed="yes")),
              ("lease.until as ISO string", _nt(lease={"until": "2026-10-31T00:00:00Z", "session": "session-a"}))]
    with _Hx() as hx:
        first = hx.claim("project")
        _check("[taskandi-http] AC9: control - a valid next_task claim for project is stored",
               first.rc == 0 and (hx.claimed() or {}).get("task") == "project", first.show())
        for label, resp in refuse:
            hx.route("next_task", json=resp)
            before = hx.claimed()
            res = _next(hx)
            _check(f"[taskandi-http] AC9: refused (exit 1, empty stdout, previous claim kept) - {label}",
                   res.rc == 1 and res.out == "" and hx.claimed() == before and before.get("task") == "project", res.show())


def test_taskandi_http_ac17_unusable_task_id() -> None:
    print("[taskandi-http] AC17 unusable task id")
    for label, tid in (("space in id", "a b"), ("201 characters", "a" * 201), ("leading dash", "-lead"), ("slash", "a/b")):
        with _Hx() as hx:
            hx.route("next_task", json=_nt(task=tid))
            res = _next(hx)
            _check(f"[taskandi-http] AC17: next_task returning {label} -> exact message, empty stdout, no claim",
                   res.rc == 1 and _UNUSABLE in res.err and res.out == "" and hx.claimed() is None, res.show())
    with _Hx() as hx:
        hx.route("next_task", json=_nt(task="a" * 200))
        res = _next(hx)
        _check("[taskandi-http] AC17: control - a 200-character usable id is accepted",
               res.rc == 0 and (hx.claimed() or {}).get("task") == "a" * 200, res.show())
        hx.route("next_task", json=_nt(task="a b"))
        res = _next(hx)
        _check("[taskandi-http] AC17: an unusable id does not clear the previous claim",
               res.rc == 1 and (hx.claimed() or {}).get("task") == "a" * 200, res.show())


# ---------------------------------------------------------------------------
# AC10 Sessions and agents
# ---------------------------------------------------------------------------

def _last_body(hx: _Hx, action: str) -> dict:
    found = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == action]
    return found[-1] if found else {}


def test_taskandi_http_ac10_sessions_and_agents() -> None:
    print("[taskandi-http] AC10 sessions and agents")
    with _Hx() as hx:
        hx.claim("leaf-b", session="sess-xyz", agent="codex")
        res = hx.cli("complete", "--summary", "done")
        _check("[taskandi-http] AC10: complete on the claimed task sends the claim's session",
               res.rc == 0 and _last_body(hx, "complete").get("session") == "sess-xyz", res.show())
        hx.claim("leaf-b", session="sess-xyz", agent="codex")
        res = hx.cli("release", "--reason", "parked")
        _check("[taskandi-http] AC10: release on the claimed task sends the claim's session",
               res.rc == 0 and _last_body(hx, "release").get("session") == "sess-xyz", res.show())
        hx.claim("leaf-b", session="sess-xyz", agent="codex")
        e = hx.enqueue("comment", "ag1", {"text": "hello"}, task="leaf-b")
        hx.clear()
        res = hx.cli("flush")
        body = _last_body(hx, "comment")
        job = hx.job("ag1") or {}
        _check("[taskandi-http] AC10: a comment enqueued on the claimed task carries the claim's agent (codex) and session at flush",
               e.rc == 0 and res.rc == 0 and body.get("agent") == "codex" and body.get("session") == "sess-xyz", res.show() + repr(body))
        _check("[taskandi-http] AC10: agent is stored on the job outside payload",
               "agent" not in job.get("payload", {}) and "codex" in json.dumps({k: v for k, v in job.items() if k != "payload"}), repr(job)[:300])
    with _Hx() as hx:
        for key, env, want in (("u-codex", {"VIBE_AGENT": "codex"}, "codex"), ("u-none", {}, "claude"),
                               ("u-bogus", {"VIBE_AGENT": "bogus"}, "claude"), ("u-claude", {"VIBE_AGENT": "claude"}, "claude")):
            hx.enqueue("comment", key, {"text": key}, task="project", env=env)
            hx.clear()
            hx.cli("flush")
            body = _last_body(hx, "comment")
            _check(f"[taskandi-http] AC10: unclaimed task, VIBE_AGENT={env.get('VIBE_AGENT')} -> agent {want}, no session key",
                   body.get("agent") == want and "session" not in body and body.get("text") == key, repr(body))
        a = hx.enqueue("comment", "dd1", {"text": "same"}, task="project", env={"VIBE_AGENT": "claude"})
        b = hx.enqueue("comment", "dd1", {"text": "same"}, task="project", env={"VIBE_AGENT": "codex"})
        _check("[taskandi-http] AC10: same key and payload under two VIBE_AGENT values deduplicates (one job)",
               a.rc == 0 and b.rc == 0 and (b.json() or {}).get("deduplicated") is True
               and len([j for j in hx.jobs() if j["key"] == "dd1"]) == 1, a.show() + b.show())
        for kind, pay in (("comment", {"text": "t"}), ("ask", _fixture_payload("ask"))):
            for field in ("connection", "session", "agent", "action"):
                key = f"inj-{kind}-{field}"
                res = hx.enqueue(kind, key, {**pay, field: "evil"}, task="project")
                _check(f"[taskandi-http] AC10: a {kind} payload with `{field}` is refused at enqueue (exit 1, no job)",
                       res.rc == 1 and hx.job(key) is None, res.show())
        for flag in ("--agent", "--session", "--connection", "--action"):
            res = hx.cli("enqueue", "comment", "--key", "argv-" + flag.strip("-"), flag, "x", stdin=json.dumps({"text": "t"}))
            _check(f"[taskandi-http] AC10: argv `{flag}` on enqueue is refused", res.rc == 1, res.show())
        res = hx.cli("complete", "--task", "project", "--summary", "s", "--agent", "codex")
        _check("[taskandi-http] AC10: argv --agent on complete is refused", res.rc == 1, res.show())


# ---------------------------------------------------------------------------
# AC11 record_time and usage
# ---------------------------------------------------------------------------

def _write_transcript(path: Path) -> None:
    rows = [
        {"type": "turn_context", "payload": {"model": "gpt-test"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 100, "cached_input_tokens": 10, "cache_write_input_tokens": 0, "output_tokens": 20}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 150, "cached_input_tokens": 20, "cache_write_input_tokens": 5, "output_tokens": 40}}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_taskandi_http_ac11_record_time_and_usage() -> None:
    print("[taskandi-http] AC11 record_time and usage")
    now = _ms()
    whole = (now // 1000) * 1000 - 7200_000
    with _Hx() as hx:
        for secs in (0, 604801):
            res = hx.enqueue("record_time", f"s{secs}", {"seconds": secs, "started_at": _iso(whole)}, task="project")
            _check(f"[taskandi-http] AC11: seconds {secs} is refused", res.rc == 1 and hx.job(f"s{secs}") is None, res.show())
        for secs in (1, 604800):
            res = hx.enqueue("record_time", f"s{secs}", {"seconds": secs, "started_at": _iso(whole - 700_000_000)}, task="project")
            _check(f"[taskandi-http] AC11: control - seconds {secs} is accepted", res.rc == 0 and hx.job(f"s{secs}") is not None, res.show())
        # Fresh clock, taken right before this enqueue: the run ends ~5 s in the
        # future, inside the old 60 s slack, so acceptance would prove slack exists.
        fut = _iso((_ms() // 1000) * 1000 - 55_000)
        res = hx.enqueue("record_time", "fut", {"seconds": 60, "started_at": fut}, task="project")
        _check("[taskandi-http] AC11: a 60 s run ending 1 s in the future is refused at enqueue, with no slack",
               res.rc == 1 and hx.job("fut") is None, res.show() + fut)
        past = _iso((now // 1000) * 1000 - 120_000)
        res = hx.enqueue("record_time", "past", {"seconds": 60, "started_at": past}, task="project")
        _check("[taskandi-http] AC11: control - a run that ended a minute ago is accepted", res.rc == 0, res.show())
        z, ms0 = _iso(whole), _iso(whole)[:-1] + ".000Z"
        a = hx.enqueue("record_time", "dup", {"seconds": 30, "started_at": z}, task="project")
        b = hx.enqueue("record_time", "dup", {"seconds": 30, "started_at": ms0}, task="project")
        _check("[taskandi-http] AC11: `...Z` and `....000Z` with the same key deduplicate",
               a.rc == 0 and b.rc == 0 and (b.json() or {}).get("deduplicated") is True, a.show() + b.show())
    with _Hx() as hx:
        hx.enqueue("record_time", "dup", {"seconds": 30, "started_at": z}, task="project")
        hx.enqueue("record_time", "frac", {"seconds": 30, "started_at": _iso(whole)[:-1] + ".345Z"}, task="project")
        res = hx.cli("flush")
        times = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == "record_time"]
        by_ms = sorted(t["started_at"] for t in times)
        _check("[taskandi-http] AC11: the wire started_at is the ms value; fractional ms are kept",
               res.rc == 0 and by_ms == sorted([whole, whole + 345]) and all(isinstance(t["started_at"], int) for t in times)
               and all(t.get("seconds") == 30 and "actor" not in t for t in times), res.show() + repr(times))
    with _Hx() as hx:
        tr = hx.base / "transcript.jsonl"
        _write_transcript(tr)
        res = hx.cli("usage", "--transcript", str(tr), "--session", "sess-u", "--account", "acct-1", "--cost-estimate", "0.1")
        out = res.json() or {}
        _check("[taskandi-http] AC11: the usage importer enqueues record_usage jobs under a descriptor binding",
               res.rc == 0 and out.get("enqueued") == 2 and all(j["kind"] == "record_usage" for j in hx.jobs()), res.show())
        hx.clear()
        res = hx.cli("flush")
        usage = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == "record_usage"]
        keys = {"action", "connection", "task", "model", "input", "output", "cache_read", "cache_write", "cost_estimate",
                "windows", "account", "source", "source_ref"}
        _check("[taskandi-http] AC11: imported usage reaches the wire with windows 0, the bound task, source vibe and the table's key set",
               res.rc == 0 and len(usage) == 2 and all(u["windows"] == 0 and u["task"] == "project" and u["source"] == "vibe"
                                                          and set(u) == keys and u["source_ref"].startswith("usage-") for u in usage),
               res.show() + repr(usage)[:400])
        res = hx.cli("usage", "--transcript", str(tr), "--session", "sess-u", "--account", "acct-1", "--cost-estimate", "0.1")
        _check("[taskandi-http] AC11: re-importing the same transcript deduplicates", (res.json() or {}).get("enqueued") == 0, res.show())


# ---------------------------------------------------------------------------
# AC12 root:null
# ---------------------------------------------------------------------------

def test_taskandi_http_ac12_root_null_targets() -> None:
    print("[taskandi-http] AC12 target resolution under root: null")
    with _Hx(root=None) as hx:
        res = _next(hx)
        _check("[taskandi-http] AC12: next-task works under root:null", res.rc == 0 and (hx.claimed() or {}).get("task") == "leaf-b", res.show())
        st = hx.cli("status")
        _check("[taskandi-http] AC12: status works under root:null", st.rc == 0 and (st.json() or {}).get("claimedTask") == "leaf-b", st.show())
    cmds = [("enqueue comment without --task", ["enqueue", "comment", "--key", "n1"], json.dumps({"text": "t"})),
            ("bare poll", ["poll"], ""), ("bare ask-status", ["ask-status"], ""),
            ("bare complete", ["complete", "--summary", "s"], ""), ("bare release", ["release", "--reason", "r"], "")]
    with _Hx(root=None) as hx:
        for label, args, stdin in cmds:
            hx.clear()
            res = hx.cli(*args, stdin=stdin)
            _check(f"[taskandi-http] AC12: {label} -> exact no-bound-task message, empty stdout, zero requests",
                   res.rc == 1 and _NO_BOUND in res.err and res.out == "" and hx.reqs() == [], res.show())
        for what, args in (("complete", ["complete", "--task", "X", "--summary", "s"]), ("release", ["release", "--task", "X", "--reason", "r"])):
            hx.clear()
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC12: {what} --task X with no claim -> the session message, zero requests",
                   res.rc == 1 and _NEED_SESSION in res.err and hx.reqs() == [], res.show())
        hx.route("list_asks", json=_la("X"))
        hx.clear()
        res = hx.cli("poll", "--task", "X")
        _check("[taskandi-http] AC12: poll --task X is accepted", res.rc == 0 and (res.json() or {}).get("task") == "X", res.show())
        res = hx.cli("ask-status", "--task", "X")
        _check("[taskandi-http] AC12: ask-status --task X is sent (the token bounds it server-side)",
               hx.count("ask_status") == 1, res.show())
        res = hx.enqueue("comment", "x1", {"text": "t"}, task="X")
        _check("[taskandi-http] AC12: enqueue --task X is accepted", res.rc == 0 and (hx.job("x1") or {}).get("payload", {}).get("task") == "X", res.show())
    with _Hx(root=None) as hx:
        hx.claim("leaf-b")
        hx.route("list_asks", json=_la("leaf-b"))
        res = hx.cli("poll")
        la = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == "list_asks"]
        _check("[taskandi-http] AC12: after a claim, bare poll targets the claimed task",
               res.rc == 0 and la and la[0]["task"] == "leaf-b", res.show())
        res = hx.enqueue("comment", "c-claimed", {"text": "t"})
        _check("[taskandi-http] AC12: after a claim, enqueue comment without --task targets the claimed task",
               res.rc == 0 and (hx.job("c-claimed") or {}).get("payload", {}).get("task") == "leaf-b", res.show())
        res = hx.cli("complete", "--task", "X", "--summary", "s")
        _check("[taskandi-http] AC12: complete --task X while leaf-b is claimed is the session refusal",
               res.rc == 1 and _NEED_SESSION in res.err, res.show())
    with _Hx(root="project") as hx:
        res = hx.cli("poll", "--task", "leaf-b")
        _check("[taskandi-http] AC12: under a non-null root, --task other than the claimed/effective task is refused (zero requests)",
               res.rc == 1 and hx.reqs() == [], res.show())
        hx.claim("leaf-b")
        hx.route("list_asks", json=_la("leaf-b"))
        res = hx.cli("poll", "--task", "leaf-b")
        _check("[taskandi-http] AC12: control - the claimed task is accepted under a non-null root", res.rc == 0, res.show())


# ---------------------------------------------------------------------------
# AC13 No leakage
# ---------------------------------------------------------------------------

def test_taskandi_http_ac13_no_leakage() -> None:
    """Every CLI call in this harness is scanned for the token, connection id and hostile string; the hostile server
    below puts all three into error codes, non-JSON bodies and unknown keys.  Positive control: the sentinels are
    really in the server's replies (the request log shows the connection id was sent, so the scan is not vacuous)."""
    print("[taskandi-http] AC13 no leakage")
    junk = f"{_HOSTILE} {_TOKEN} {_CONN} {_WS}"
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.enqueue("comment", "l1", {"text": "t"}, task="leaf-b")
        hx.enqueue("comment", "l2", {"text": "t2"}, task="leaf-b")
        scenarios = [
            ("capabilities error code", "capabilities", {"status": 409, "json": {"error": junk}}, ["next-task", "--agent", "claude", "--session", "s1"]),
            ("capabilities non-JSON", "capabilities", {"status": 500, "raw": junk}, ["poll"]),
            ("capabilities extra key", "capabilities", {"json": {**_fixture("capabilities")["response"], junk: junk}}, ["ask-status"]),
            ("capabilities redirect", "capabilities", {"status": 302, "raw": "", "headers": {"location": "http://127.0.0.1:1/" + _TOKEN}}, ["flush"]),
            ("capabilities 421 with junk", "capabilities", {"status": 421, "json": {"error": "wrong_origin", "detail": junk}}, ["poll"]),
        ]
        for label, action, spec, args in scenarios:
            hx.route(action, **spec)
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC13: {label} -> exit 1 and no sentinel in stdout/stderr",
                   res.rc != 0 and not any(s in res.out + res.err for s in (_TOKEN, _CONN, _WS, "\x1b", "HOSTILE")), res.show())
        hx.route("capabilities", json=_fixture("capabilities")["response"])
        later = [("next_task junk", "next_task", {"json": {"task": None, junk: junk}}, ["next-task", "--agent", "claude", "--session", "s1"]),
                 ("list_asks junk", "list_asks", {"json": {**_la("leaf-b"), "x": junk}}, ["poll"]),
                 ("ask_status junk", "ask_status", {"json": {"task": "leaf-b", "asks": [], "x": junk}}, ["ask-status"]),
                 ("comment error code", "comment", {"status": 409, "json": {"error": junk}}, ["flush"]),
                 ("comment non-JSON", "comment", {"status": 200, "raw": junk}, ["flush"]),
                 ("complete error code", "complete", {"status": 409, "json": {"error": junk}}, ["complete", "--summary", "s"]),
                 ("complete open_children junk code", "complete", {"status": 409, "json": {"error": "open_children", "children": [], "x": junk}}, ["complete", "--summary", "s"]),
                 ("release non-JSON", "release", {"status": 409, "raw": junk}, ["release", "--reason", "r"])]
        for label, action, spec, args in later:
            hx.route(action, **spec)
            res = hx.cli(*args)
            bad = [s for s in (_TOKEN, _CONN, _WS, "\x1b", "HOSTILE") if s in res.out + res.err]
            _check(f"[taskandi-http] AC13: {label} -> no sentinel in stdout/stderr", not bad, f"leaked={bad} {res.show()}")
        reqs_with_conn = [r for r in hx.reqs() if (r["json"] or {}).get("connection") == _CONN]
        _check("[taskandi-http] AC13: control - the connection id really was on the wire (scan is not vacuous)", len(reqs_with_conn) > 3, "")
        st = hx.cli("status")
        blob = st.out + st.err
        _check("[taskandi-http] AC13: status shows no token, connection, workspace, origin host or port",
               st.rc == 0 and not any(s in blob for s in (_TOKEN, _CONN, _WS, "127.0.0.1", f":{hx.port}", str(hx.port))), st.show())
        _check("[taskandi-http] AC13: status carries the channel and refusedKeys",
               (st.json() or {}).get("channel") == "taskandi-http" and "refusedKeys" in (st.json() or {}), st.show())
    _check("[taskandi-http] AC13: no CLI call anywhere in the HTTP suites leaked a sentinel", _LEAKS == [], repr(_LEAKS[:5]))


# ---------------------------------------------------------------------------
# AC14 Regression and matrix
# ---------------------------------------------------------------------------

def test_taskandi_http_ac14_regression_and_matrix() -> None:
    print("[taskandi-http] AC14 regression and command matrix")
    # Rev 6: the permanent `git diff HEAD` check on checks_28/29/47 was removed; they are run unchanged by the suite.
    with _Hx() as hx:
        tr = hx.base / "t.jsonl"
        _write_transcript(tr)
        rcs = {}
        rcs["next-task"] = _next(hx).rc
        hx.clear()
        for kind, pay in (("ask", _fixture_payload("ask")), ("comment", {"text": "t"}),
                          ("record_usage", {k: v for k, v in _fixture_payload("record_usage").items() if k not in ("windows", "source", "source_ref")}),
                          ("record_time", {"seconds": 5, "started_at": _iso(_ms() - 3_600_000)})):
            rcs[f"enqueue {kind}"] = hx.enqueue(kind, f"mx-{kind}", pay, task="leaf-b").rc
        rcs["usage"] = hx.cli("usage", "--transcript", str(tr), "--session", "s", "--account", "a", "--cost-estimate", "0.1", "--task", "leaf-b").rc
        rcs["flush"] = hx.cli("flush").rc
        hx.route("list_asks", json=_la("leaf-b"))
        rcs["poll"] = hx.cli("poll").rc
        hx.route("ask_status", json={"task": "leaf-b", "asks": []})
        rcs["ask-status"] = hx.cli("ask-status").rc
        rcs["status"] = hx.cli("status").rc
        rcs["release"] = hx.cli("release", "--reason", "r").rc
        hx.claim("leaf-b")
        rcs["complete"] = hx.cli("complete", "--summary", "s").rc
        hx.enqueue("comment", "mx-unc", {"text": "u"}, task="project")
        hx.route("comment", status=500, raw="oops")
        hx.cli("flush")
        res = hx.cli("reconcile", "--key", "mx-unc", "--action", "retry", "--evidence", "checked")
        rcs["reconcile"] = res.rc
        _check("[taskandi-http] AC14: every command runs at least once under a descriptor binding (all exit 0)",
               all(v == 0 for v in rcs.values()) and len(rcs) == 13, repr(rcs))
        _check("[taskandi-http] AC14: the four enqueued kinds and the usage import all delivered",
               all((hx.job(f"mx-{k}") or {}).get("state") == "done" for k in ("ask", "comment", "record_usage", "record_time")),
               repr([(j["key"], j["state"]) for j in hx.jobs()]))


# ---------------------------------------------------------------------------
# AC15 Docs and gates
# ---------------------------------------------------------------------------

def test_taskandi_http_ac15_docs_and_gates() -> None:
    print("[taskandi-http] AC15 docs, fixtures, changelog, manual test")
    _check("[taskandi-http] AC15: in-repo fixture copy has all ten files",
           all((_FIX_REPO / f"{n}.json").exists() for n in _NAMES), repr(sorted(p.name for p in _FIX_REPO.glob("*")) if _FIX_REPO.exists() else "missing"))
    prov = _FIX_REPO / "PROVENANCE.md"
    ptxt = prov.read_text() if prov.exists() else ""
    _check("[taskandi-http] AC15: PROVENANCE.md gives the source path, taskandeye commit 62e50fa5 and a date",
           "Task&I-agent-exchange-fixtures" in ptxt and "62e50fa5" in ptxt and re.search(r"20\d\d-\d\d-\d\d", ptxt) is not None, ptxt[:200])
    if _FIX_BRAIN.is_dir():
        same = all((_FIX_REPO / f"{n}.json").exists() and (_FIX_REPO / f"{n}.json").read_bytes() == (_FIX_BRAIN / f"{n}.json").read_bytes() for n in _NAMES)
        _check("[taskandi-http] AC15: the fixture copy is byte-identical to /brain2", same, "")
    else:
        print("  (skip) /brain2 not mounted: byte-identity check not run")
    docs = _DOCS.read_text() if _DOCS.exists() else ""
    for needle in ("taskandi-descriptor.json", "chmod 600", "host.docker.internal", "Host: 127.0.0.1:<port>", "wrong_origin",
                   "connection_scope", "connection_revoked", "refused", "ask-status"):
        _check(f"[taskandi-http] AC15: docs mention `{needle}`", needle in docs, "")
    _check("[taskandi-http] AC15: docs say uncertain writes are never retried automatically",
           re.search(r"never retried automatically", docs, re.I) is not None, "")
    _check("[taskandi-http] AC15: docs give check-before-retry advice (ask-status/poll or Task&I, then reconcile --action retry)",
           re.search(r"(check|verify)[^\n]{0,200}(before|first)[^\n]{0,200}reconcile|before[^\n]{0,120}reconcile --action retry", docs, re.I) is not None, "")
    stale = [ln for ln in docs.splitlines() if "30000" in ln and "MCP" not in ln]
    _check("[taskandi-http] AC15: no unqualified `30000 ms` statement remains (each names MCP)", stale == [], repr(stale[:2]))
    _check("[taskandi-http] AC15: docs state the HTTP timeout (15 s)", re.search(r"15\s?(s\b|seconds|000)", docs) is not None, "")
    _check("[taskandi-http] AC15: no unqualified 'only MCP' statement remains",
           not [ln for ln in docs.splitlines() if re.search(r"only (the )?MCP|MCP only", ln, re.I) and not re.search(r"HTTP|descriptor|v2\.2", ln)], "")
    cl = (_REPO / "CHANGELOG.md").read_text()
    _check("[taskandi-http] AC15: CHANGELOG.md has a task_064 entry", re.search(r"task_064|taskandi-descriptor|v2\.2 HTTP", cl[:20000]) is not None, "")
    mt = (_REPO / "MANUAL-TESTS.md").read_text()
    i = mt.find("Test 69")
    _check("[taskandi-http] AC15: MANUAL-TESTS.md gains Test 69 (real service through host.docker.internal)",
           i >= 0 and "host.docker.internal" in mt[i:i + 6000] and "ask" in mt[i:i + 6000], "")
    for f in ("checks_50_taskandi_http.py", "checks_52_taskandi_http_more.py"):
        n = len((_REPO / "smoke" / f).read_text().splitlines())
        _check(f"[taskandi-http] AC15: smoke/{f} stays within 1,500 lines ({n})", n <= 1500, str(n))
    runner = (_REPO / "smoke" / "runner.py").read_text()
    _check("[taskandi-http] AC15: runner.py imports and calls the new tests",
           "checks_50_taskandi_http" in runner and "test_taskandi_http_ac1_descriptor" in runner and "test_taskandi_http_ac18_list_asks_shape" in runner, "")


# ---------------------------------------------------------------------------
# AC16 Limits
# ---------------------------------------------------------------------------

def _composed(q: str, d: str, opts: list) -> int:
    return len("Question: " + q + "\nDefault: " + d + ("\nOptions: " + " / ".join(opts) if opts else ""))


def _ask(question="q", default="d", **extra) -> dict:
    base = {"question": question, "default": default, "order": 1, "estimate_minutes": 1, "remaining_minutes": 1,
            "reversible": True, "blocking": True}
    base.update(extra)
    return base


def test_taskandi_http_ac16_limits() -> None:
    print("[taskandi-http] AC16 limits")
    E = "\U0001F600"   # one code point, two UTF-16 code units
    with _Hx() as hx:
        n = [0]

        def edge(label, kind, payload, ok, task="project"):
            n[0] += 1
            key = f"lim-{n[0]}"
            hx.clear()
            res = hx.enqueue(kind, key, payload, task=task)
            good = res.rc == 0 and hx.job(key) is not None if ok else res.rc == 1 and hx.job(key) is None and hx.reqs() == []
            _check(f"[taskandi-http] AC16: {label} -> {'accepted' if ok else 'refused (exit 1, no job, zero requests)'}", good, res.show()[:300])

        qmax = 8000 - _composed("", "d", [])
        edge("question at the composed-post maximum (astral characters, proving code points)", "ask", _ask(E * qmax), True)
        edge("question one code point over the composed-post maximum", "ask", _ask(E * (qmax + 1)), False)
        edge("question of 8001 code points (field limit)", "ask", _ask(E * 8001), False)
        print("  note: `question` of exactly 8000 is unreachable as specified: the composed post adds 'Question: ' and 'Default: ' text")
        edge("default of 2000 code points", "ask", _ask(default="d" * 2000), True)
        edge("default of 2001 code points", "ask", _ask(default="d" * 2001), False)
        edge("20 options", "ask", _ask(options=["o"] * 20), True)
        edge("21 options", "ask", _ask(options=["o"] * 21), False)
        edge("an option of 500 code points", "ask", _ask(options=["o" * 500]), True)
        edge("an option of 501 code points", "ask", _ask(options=["o" * 501]), False)
        opts = ["a", "b"]
        nopt = 8000 - _composed("", "d", opts)
        edge("composed post exactly 8000 with options", "ask", _ask("x" * nopt, options=opts), True)
        edge("composed post 8001 with options", "ask", _ask("x" * (nopt + 1), options=opts), False)
        nno = 8000 - _composed("", "d", [])
        edge("composed post exactly 8000 without options", "ask", _ask("x" * nno), True)
        edge("composed post 8001 without options", "ask", _ask("x" * (nno + 1)), False)
        edge("comment text 8000 code points (astral)", "comment", {"text": E * 8000}, True)
        edge("comment text 8001 code points (astral)", "comment", {"text": E * 8001}, False)
        for field, base in (("model", {"account": "a", "model": "m", "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0.1}),
                            ("account", {"account": "a", "model": "m", "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0.1})):
            edge(f"{field} of 200 code units", "record_usage", {**base, field: "a" * 200}, True)
            edge(f"{field} of 201 code units", "record_usage", {**base, field: "a" * 201}, False)
        edge("model of 100 astral characters (200 code units)", "record_usage",
             {"account": "a", "model": E * 100, "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0.1}, True)
        edge("model of 101 astral characters (202 code units)", "record_usage",
             {"account": "a", "model": E * 101, "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0.1}, False)
        edge("in_reply_to of 200 code units", "ask", _ask(in_reply_to="r" * 200), True)
        edge("in_reply_to of 201 code units", "ask", _ask(in_reply_to="r" * 201), False)
        for key_len, ok in ((200, True), (201, False)):
            hx.clear()
            res = hx.enqueue("comment", "k" * key_len, {"text": "t"}, task="project")
            _check(f"[taskandi-http] AC16: key of {key_len} characters -> {'accepted' if ok else 'refused'}",
                   (res.rc == 0) == ok and hx.reqs() == [], res.show()[:200])
        edge("whitespace-only comment text", "comment", {"text": " \n\t "}, False)
        edge("whitespace-only question", "ask", _ask(question="   "), False)
        edge("whitespace-only default", "ask", _ask(default=" "), False)
        edge("comment text with a lone surrogate", "comment", {"text": "a\ud800b"}, False)
        edge("question with a lone surrogate", "ask", _ask(question="a\udc00b"), False)
    with _Hx() as hx:
        for label, args, ok_len, bad_len in (("complete.summary", ["complete", "--summary"], 7950, 7951),
                                             ("release.reason", ["release", "--reason"], 2000, 2001)):
            hx.claim("leaf-b")
            res = hx.cli(*args, "s" * ok_len)
            _check(f"[taskandi-http] AC16: {label} of {ok_len} -> accepted and sent", res.rc == 0 and hx.count(args[0]) == 1, res.show()[:300])
            hx.claim("leaf-b")
            res = hx.cli(*args, "s" * bad_len)
            _check(f"[taskandi-http] AC16: {label} of {bad_len} -> exit 1, zero requests", res.rc == 1 and hx.reqs() == [], res.show()[:300])
            hx.claim("leaf-b")
            res = hx.cli(*args, "  ")
            _check(f"[taskandi-http] AC16: whitespace-only {label} -> exit 1, zero requests", res.rc == 1 and hx.reqs() == [], res.show()[:300])
        hx.clear()
        res = hx.cli("next-task", "--agent", "claude", "--session", "s" * 200)
        ok200 = res.rc == 0
        hx.clear()
        res = hx.cli("next-task", "--agent", "claude", "--session", "s" * 201)
        _check("[taskandi-http] AC16: session of 200 accepted, 201 refused with zero requests", ok200 and res.rc == 1 and hx.reqs() == [], res.show()[:200])
    with _Hx(root=None) as hx:
        hx.route("list_asks", json=_la("t" * 200))
        res = hx.cli("poll", "--task", "t" * 200)
        _check("[taskandi-http] AC16: task id of 200 code units accepted", res.rc == 0, res.show()[:200])
        hx.clear()
        res = hx.cli("poll", "--task", "t" * 201)
        _check("[taskandi-http] AC16: task id of 201 code units refused with zero requests", res.rc == 1 and hx.reqs() == [], res.show()[:200])
    with _Hx() as hx:
        hx.enqueue("comment", "big", {"text": "t"}, task="project")
        hx.enqueue("comment", "small", {"text": "t2"}, task="project")
        st = hx.state()
        for j in st["jobs"]:
            if j["key"] == "big":
                j["payload"]["text"] = "x" * 66000
                j["digest"] = _canon_digest({"kind": j["kind"], "payload": j["payload"]})   # rev 6 AC28: keep the job self-consistent
        p = hx.vibe / "taskandi-outbox" / "state.json"
        p.write_text(json.dumps(st))
        os.chmod(p, 0o600)
        res = hx.cli("flush")
        stt = hx.cli("status").json() or {}
        _check("[taskandi-http] AC16: a final body over 65536 bytes at flush -> job refused with code body_too_large, no comment request for it",
               (hx.job("big") or {}).get("state") == "refused" and {"key": "big", "code": "body_too_large"} in stt.get("refusedKeys", []),
               res.show() + repr(stt)[:300])
        sent = [r["json"].get("text") for r in hx.reqs() if (r["json"] or {}).get("action") == "comment"]
        _check("[taskandi-http] AC16: the oversize job is never sent while the next job still is (flush continues past a refusal)",
               "x" * 66000 not in sent and sent == ["t2"], repr([s[:10] for s in sent]))


# ---------------------------------------------------------------------------
# AC18 list_asks / ask_status shape
# ---------------------------------------------------------------------------

def test_taskandi_http_ac18_list_asks_shape() -> None:
    print("[taskandi-http] AC18 list_asks shape")
    base = _fixture("list_asks")["response"]
    E = "\U0001F600"

    def page(**ask_over):
        p = copy.deepcopy(base)
        for k, v in ask_over.items():
            if v is _DROP:
                p["asks"][0].pop(k, None)
            else:
                p["asks"][0][k] = v
        return p

    dup = copy.deepcopy(base)
    dup["asks"].append(copy.deepcopy(dup["asks"][0]))
    bad = [("a deferred key", page(deferred=False)), ("seen_at null", page(seen_at=None)), ("answer null", page(answer=None)),
           ("answered_by null", page(answered_by=None)), ("answered_at null", page(answered_at=None)),
           ("subtask_id set with placed thread", page(placed="thread")),
           ("subtask_id null with placed subtask", page(subtask_id=None)), ("options absent", page(options=_DROP)),
           ("agent gemini", page(agent="gemini")), ("answer of 8001 code points", page(answer=E * 8001)),
           ("repeated ask_id", dup), ("ask for a different task", page(task="someone-else")),
           ("in_reply_to absent", page(in_reply_to=_DROP)), ("owner_answer not boolean", page(owner_answer="yes"))]
    with _Hx() as hx:
        ok = hx.cli("poll")
        _check("[taskandi-http] AC18: control - the fixture page itself is accepted", ok.rc == 0 and (ok.json() or {}).get("newAnswers") == 1, ok.show())
        for label, resp in bad:
            hx.route("list_asks", json=resp)
            before = (hx.state() or {})
            snap = (before.get("cursors"), before.get("answers"), before.get("conflicts"))
            res = hx.cli("poll")
            after = (hx.state() or {})
            _check(f"[taskandi-http] AC18: malformed page ({label}) -> exit 1, cursor and answers unchanged",
                   res.rc == 1 and (after.get("cursors"), after.get("answers"), after.get("conflicts")) == snap, res.show())
    with _Hx() as hx:
        hx.route("list_asks", json=page(answer=E * 8000, subtask_id=None, placed="thread"))
        res = hx.cli("poll")
        _check("[taskandi-http] AC18: control - an 8000-code-point answer on a thread-placed ask is accepted",
               res.rc == 0 and (res.json() or {}).get("newAnswers") == 1, res.show())
    ask_ok = _fixture("ask_status")["response"]
    with _Hx() as hx:
        res = hx.cli("ask-status")
        _check("[taskandi-http] AC18: control - the ask_status fixture is accepted", res.rc == 0, res.show())
        variants = [("deferred 'no'", {**ask_ok, "asks": [{**ask_ok["asks"][0], "deferred": "no"}]}),
                    ("answered not boolean", {**ask_ok, "asks": [{**ask_ok["asks"][0], "answered": 1}]}),
                    ("seen_at a string", {**ask_ok, "asks": [{**ask_ok["asks"][0], "seen_at": "yesterday"}]}),
                    ("extra ask key", {**ask_ok, "asks": [{**ask_ok["asks"][0], "x": 1}]}),
                    ("missing ask key", {**ask_ok, "asks": [{k: v for k, v in ask_ok["asks"][0].items() if k != "deferred"}]}),
                    ("task differs", {**ask_ok, "task": "someone-else"})]
        for label, resp in variants:
            hx.route("ask_status", json=resp)
            res = hx.cli("ask-status")
            _check(f"[taskandi-http] AC18: ask_status ({label}) is refused with exit 1", res.rc == 1, res.show())
        hx.route("ask_status", json={"task": "project", "asks": [{**ask_ok["asks"][0], "seen_at": None}]})
        res = hx.cli("ask-status")
        _check("[taskandi-http] AC18: control - ask_status seen_at null is valid", res.rc == 0, res.show())


def _run_all() -> None:
    for fn in [test_taskandi_http_ac9_next_task_shape, test_taskandi_http_ac17_unusable_task_id,
               test_taskandi_http_ac10_sessions_and_agents, test_taskandi_http_ac11_record_time_and_usage,
               test_taskandi_http_ac12_root_null_targets, test_taskandi_http_ac16_limits,
               test_taskandi_http_ac18_list_asks_shape, test_taskandi_http_ac13_no_leakage,
               test_taskandi_http_ac14_regression_and_matrix, test_taskandi_http_ac15_docs_and_gates]:
        try:
            fn()
        except Exception as error:  # a crashed test is a failed test, never a silent pass
            _check(f"[taskandi-http] {fn.__name__} raised", False, repr(error))


if __name__ == "__main__":
    _run_all()
    passed = sum(_RESULTS)
    print(f"total: {len(_RESULTS)} passed: {passed} failed: {len(_RESULTS) - passed}")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        raise SystemExit(1)
    print("PASS: Task&I v2.2 HTTP acceptance checks (part 2)")
