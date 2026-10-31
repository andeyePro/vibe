#!/usr/bin/env python3
"""Acceptance checks for task_066 (Task&I client, contract v2.3 family alongside v2.2), part 1: AC1-AC6.

Tester-owned (cycle 1).  Part 2 (AC7-AC16, Rev 2.1 M1-M3) is ``checks_59_taskandi_v23_more.py``, which reuses the
harness defined here.

Harness.  Every wire test runs the real client against ``smoke/taskandi_v23_server.mjs``, a fake service that serves the
fixtures in ``smoke/fixtures/taskandi-v23/`` (they say v2.5; the server also answers v2.3 and v2.4, or v2.2 in its strict
v2.2 mode), replays writes by ``request_id`` exactly as the fixtures' README describes (same id + same body = the stored
response and nothing applied; same id + other body = ``receipt_collision``), and logs every request and every *applied*
write, so "exactly one row" is a count of server-side applications, not a guess.  The server is steered per case by
rewriting its control file (drop a response after applying it, answer v2.2, report custom limits, return an error code).
Commands run through ``dc`` (the injected clock, ``clock = () => 1761800000000``) so ``at`` rules are deterministic.

Run only this module with:
    python3 smoke/checks_58_taskandi_v23.py
"""
from __future__ import annotations

import copy
import functools
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import (_CLIENT, _CONN, _FIX_BRAIN, _FIX_REPO, _RESULTS, _T1, _WS, _Hx, _Res, _check, _cur,
                                           _fixture, _iso)
from smoke.checks_53_taskandi_decide import dc
from smoke.checks_55_taskandi_http_review import _edit_state

_REPO = Path(__file__).resolve().parent.parent
_FIX23 = _REPO / "smoke" / "fixtures" / "taskandi-v23"
_SERVER = _REPO / "smoke" / "taskandi_v23_server.mjs"
R22, R23, R24, R25 = (f"vibe-agent-exchange-v2.{n}" for n in (2, 3, 4, 5))
FAMILY = [R23, R24, R25]
REVS = [R22, *FAMILY]
WRITES = ("ask", "comment", "record_usage", "record_time", "release", "complete")
READS = ("capabilities", "next_task", "list_asks", "ask_status")
NAMES23 = ["capabilities", "next_task", "next_task_claim", "over_budget", "ask", "ask_status", "comment", "list_asks",
           "record_usage", "record_time", "complete", "release", "retry"]
GOLDEN = "5e84cb4df6e21ec2b1b3cb612f1c95b7a23efe719c0d4c08301c6ef28f83cb70"   # binding digest of the test descriptor, as before this task
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
__all__ = ["test_v23_ac1_negotiation", "test_v23_ac2_binding_digest", "test_v23_ac3_wire_per_fixture", "test_v23_ac4_frozen_body_and_resend", "test_v23_ac5_crash_downgrade_upgrade", "test_v23_ac6_complete_release", "test_v23_family_treated_alike"]
_T = "[taskandi-v23]"
LIMIT_KEYS = ["id", "request_bytes", "question", "default", "options", "option", "ask_post", "comment", "summary", "reason"]
MSG_DOWNGRADE = "attempted on v2.3; the server now speaks v2.2, so a resend could duplicate"


def fix_dir() -> Path:
    return _FIX23 if (_FIX23 / "capabilities.json").exists() else _FIX_BRAIN   # dev fallback; AC16 requires the in-repo copy


def fx(name: str) -> dict:
    return json.loads((fix_dir() / f"{name}.json").read_text())


def safe(fn):
    """A crashed test is a failed test, never a silent pass (and never a crashed smoke run)."""
    @functools.wraps(fn)
    def wrapper():
        try:
            fn()
        except Exception as error:  # noqa: BLE001
            _check(f"{_T} {fn.__name__} raised", False, repr(error))
    return wrapper


class V(_Hx):
    """Throwaway project + descriptor + the fake v2.3-family service."""

    def __init__(self, revision=R25, root="project", **kw):
        self.ctl = {"revision": revision, "nowMs": _T1}
        super().__init__(root=root, **kw)

    def start_server(self) -> int:
        self.spec.write_text(json.dumps(self.ctl))
        p = subprocess.Popen(["node", str(_SERVER), str(self.spec), str(self.log), str(fix_dir()), str(_FIX_REPO)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.procs.append(p)
        return int(p.stdout.readline().strip())

    def save_routes(self) -> None:
        self.spec.write_text(json.dumps(self.ctl))

    def set(self, **kw) -> None:
        for k, v in kw.items():
            if v is None:
                self.ctl.pop(k, None)
            else:
                self.ctl[k] = v
        self.save_routes()

    def run(self, *args: str, now=_T1, stdin="", env=None) -> _Res:
        return dc(self, now, *args, stdin=stdin, env=env)

    # -- observation --------------------------------------------------------
    def bodies(self, action: str) -> list:
        return [r["json"] for r in self.reqs() if (r["json"] or {}).get("action") == action]

    def raws(self, action: str) -> list:
        return [r["body"] for r in self.reqs() if (r["json"] or {}).get("action") == action]

    def applied(self, action: str | None = None) -> list:
        return [e for e in self.events() if e["t"] == "applied" and (action is None or e["action"] == action)]

    def replays(self, action: str | None = None) -> list:
        return [e for e in self.events() if e["t"] == "replay" and (action is None or e["action"] == action)]

    def write_reqs(self) -> int:
        return sum(self.count(a) for a in WRITES)

    # -- helpers ------------------------------------------------------------
    def claim(self, task="leaf-b", session="session-a", agent="claude", **ctl) -> _Res:
        self.set(offerTask=task, **ctl)
        res = self.run("next-task", "--agent", agent, "--session", session)
        self.set(offerTask=None)
        return res

    def enq(self, kind: str, key: str, payload: dict, task: str | None = None) -> _Res:
        args = ["enqueue", kind, "--key", key] + (["--task", task] if task else [])
        return self.run(*args, stdin=json.dumps(payload))

    def comment(self, key="c1", text="hello", task=None) -> _Res:
        return self.enq("comment", key, {"text": text}, task)

    def refused(self) -> dict:
        return {x["key"]: x["code"] for x in (self.run("status").json() or {}).get("refusedKeys", [])}

    def stamp(self) -> int:
        return len(self.events())


def ask_payload() -> dict:
    return {k: v for k, v in fx("ask")["request"].items() if k not in ("action", "task", "session", "agent", "request_id")}


def payload_of(name: str) -> dict:
    p = {k: v for k, v in fx(name)["request"].items() if k not in ("action", "task", "session", "agent", "request_id")}
    if name == "record_usage":
        for k in ("windows", "source", "source_ref"):
            p.pop(k, None)
    if name == "record_time":
        p["started_at"] = _iso(p["started_at"])
    return p


# ---------------------------------------------------------------------------
# AC1 Negotiation
# ---------------------------------------------------------------------------

def _pre_dispatch_refusal(label: str, revision=R25, next_too=True, **ctl) -> None:
    with V(revision) as hx:
        hx.set(**ctl)
        hx.comment()
        hx.clear()
        res = hx.run("flush")
        job = hx.job("c1") or {}
        _check(f"{_T} AC1: {label}: flush sends only capabilities, exit 1, the job stays queued with nothing frozen",
               res.rc == 1 and hx.actions() == ["capabilities"] and job.get("state") == "queued" and not job.get("sentBody"),
               res.show() + repr(hx.actions()))
        hx.clear()
        if not next_too:
            return
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
        _check(f"{_T} AC1: {label}: next-task sends only capabilities, exit 1, no claim",
               res.rc == 1 and hx.actions() == ["capabilities"] and hx.claimed() is None, res.show() + repr(hx.actions()))


@safe
def test_v23_ac1_negotiation() -> None:
    print(f"{_T} AC1 negotiation")
    for rev in REVS:
        with V(rev) as hx:
            _check(f"{_T} AC1: control - before any call the state has no lastContract", (hx.state() or {}).get("lastContract") is None, "")
            res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
            _check(f"{_T} AC1: {rev[-4:]} is accepted (exit 0, a claim, two requests)",
                   res.rc == 0 and hx.actions() == ["capabilities", "next_task"] and hx.claimed() is not None, res.show())
            _check(f"{_T} AC1: {rev[-4:]}: state.lastContract is the exact string", (hx.state() or {}).get("lastContract") == rev, repr(hx.state())[:200])
            _check(f"{_T} AC1: {rev[-4:]}: claim.contract is the exact string", (hx.claimed() or {}).get("contract") == rev, repr(hx.claimed())[:300])
            hx.comment()
            hx.run("flush")
            if rev != R22:
                _check(f"{_T} AC1: {rev[-4:]}: the flushed job records sentRevision", (hx.job("c1") or {}).get("sentRevision") == rev, repr(hx.job("c1"))[:300])
    for bad in ("vibe-agent-exchange-v2.6", "vibe-agent-exchange-v2.1", "vibe-agent-exchange-v3.0", "vibe-agent-exchange-v2.5 "):
        _pre_dispatch_refusal(f"contract {bad!r}", revision=bad)
    lim = copy.deepcopy(fx("capabilities")["response"]["limits"])
    _pre_dispatch_refusal("v2.2 answer carrying limits", R22, capsAdd={"limits": lim})
    _pre_dispatch_refusal("v2.2 answer carrying id_pattern", R22, capsAdd={"id_pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$"})
    for rev in (R23, R25):
        t = rev[-4:]
        for key in ("unit", "id", "id_unit", "request_bytes", "question", "default", "options", "option", "ask_post", "comment", "summary", "reason"):
            _pre_dispatch_refusal(f"{t} limits missing {key}", rev, capsDrop=[key])
        _pre_dispatch_refusal(f"{t} limits unit bytes", rev, limits={"unit": "bytes"})
        _pre_dispatch_refusal(f"{t} limits id_unit code_points", rev, limits={"id_unit": "code_points"})
        _pre_dispatch_refusal(f"{t} limits comment 0", rev, limits={"comment": 0})
        _pre_dispatch_refusal(f"{t} limits comment a string", rev, limits={"comment": "8000"})
        _pre_dispatch_refusal(f"{t} limits comment fractional", rev, limits={"comment": 1.5})
        _pre_dispatch_refusal(f"{t} limits comment negative", rev, limits={"comment": -5})
        _pre_dispatch_refusal(f"{t} id_pattern different", rev, idPattern="^[a-z]+$")
        _pre_dispatch_refusal(f"{t} id_pattern missing", rev, capsDrop=["id_pattern"])
        _pre_dispatch_refusal(f"{t} limits missing altogether", rev, capsDrop=["limits"])
        _pre_dispatch_refusal(f"{t} extra top-level key", rev, capsAdd={"extra": 1})
        _pre_dispatch_refusal(f"{t} calls lacking comment while a comment is queued", rev, next_too=False,
                              capsAdd={"calls": ["capabilities", "ask", "list_asks", "ask_status", "next_task", "release", "record_usage", "record_time", "complete"]})
    # controls: extra limits keys are allowed (Rev 3), so the refusals above are about the named defect
    for rev, extra in ((R25, {"title": 500, "next_action": 2000, "notes": 8000}), (R23, {"zzz": 5}), (R24, {"zzz": 5})):
        with V(rev) as hx:
            hx.set(limits=extra)
            hx.comment()
            hx.clear()
            res = hx.run("flush")
            _check(f"{_T} AC1: control - {rev[-4:]} with extra limits keys is accepted and the comment is delivered",
                   res.rc == 0 and hx.actions() == ["capabilities", "comment"] and (hx.job("c1") or {}).get("state") == "done", res.show())


# ---------------------------------------------------------------------------
# AC2 Binding digest
# ---------------------------------------------------------------------------

@safe
def test_v23_ac2_binding_digest() -> None:
    print(f"{_T} AC2 binding digest")
    with V() as hx:
        out = hx.lib("out.fp = C.bindingFingerprint(C.loadConfig(cwd));")
        _check(f"{_T} AC2: the fixed descriptor's fingerprint equals its golden hex", out.get("fp") == GOLDEN, repr(out))
        hx.reconnect()
        out = hx.lib("out.fp = C.bindingFingerprint(C.loadConfig(cwd));", port=hx.port)
        _check(f"{_T} AC2: still the golden hex after a reconnect on a new port and token", out.get("fp") == GOLDEN, repr(out))
    with V(R22) as hx:
        hx.claim()
        hx.comment("q22", "queued before the switch")
        hx.comment("q22b", "also queued before the switch")
        hx.set(revision=R25)
        res = hx.run("flush")
        _check(f"{_T} AC2: jobs queued under v2.2 flush on v2.5 (no BINDING_CHANGED), exit 0",
               res.rc == 0 and "BINDING_CHANGED" not in res.err + res.out and all((hx.job(k) or {}).get("state") == "done" for k in ("q22", "q22b")),
               res.show())
        hx.comment("q25", "queued on v2.5")
        hx.set(revision=R22)
        res = hx.run("flush")
        _check(f"{_T} AC2: a job queued on v2.5 flushes on v2.2 (no BINDING_CHANGED)",
               res.rc == 0 and "BINDING_CHANGED" not in res.err + res.out and (hx.job("q25") or {}).get("state") == "done", res.show())
        _check(f"{_T} AC2: every job carries the golden binding digest",
               {(hx.job(k) or {}).get("binding") for k in ("q22", "q22b", "q25")} == {GOLDEN}, repr([hx.job(k) for k in ("q22", "q25")])[:300])
        _check(f"{_T} AC2: the descriptor binding's protocol pin still says v2.2 (digest independent of the negotiated revision)",
               "2.2" in R22 and (hx.state() or {}).get("lastContract") == R22, "")


# ---------------------------------------------------------------------------
# AC3 Wire per v2.3 fixture
# ---------------------------------------------------------------------------

def _wire_keys(name: str) -> set:
    keys = set(fx(name)["request"]) | {"connection"}
    if name in WRITES:
        keys.add("request_id")
    return keys


@safe
def test_v23_ac3_wire_per_fixture() -> None:
    print(f"{_T} AC3 wire per v2.3 fixture")
    _check(f"{_T} AC3: all thirteen v2.3 fixtures are present", all((fix_dir() / f"{n}.json").exists() for n in NAMES23), "")
    for rev in (R25, R23, R24):
        with V(rev) as hx:
            hx.set(offerTask="leaf-b")
            res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
            first, second = (hx.bodies("capabilities") or [None])[0], (hx.bodies("next_task") or [None])[0]
            _check(f"{_T} AC3 [{rev[-4:]}] capabilities: exactly action + connection", first == {"action": "capabilities", "connection": _CONN}, repr(first))
            _check(f"{_T} AC3 [{rev[-4:]}] next_task: key set = fixture request + connection, no request_id, no task",
                   second is not None and set(second) == _wire_keys("next_task") and "request_id" not in second and "task" not in second, repr(second))
            want = copy.deepcopy(fx("next_task")["response"])
            _check(f"{_T} AC3 [{rev[-4:]}] next_task: stdout task equals the fixture response", (res.json() or {}).get("task") == want, res.show())
    with V(R25, root="leaf-b") as hx:
        for name, reason in (("next_task_claim", "over_budget"), ("over_budget", "over_budget")):
            hx.clear()
            hx.set(refuse=reason)
            res = hx.run("next-task", "--agent", "claude", "--session", "session-a", "--task", "leaf-b")
            body = (hx.bodies("next_task") or [None])[0]
            want = {"bound": True, "channel": "taskandi-http", "task": None, "reason": fx(name)["response"]["reason"]}
            _check(f"{_T} AC3 {name}: request key set = fixture request + connection; stdout equals the fixture response",
                   body is not None and set(body) == _wire_keys(name) and body.get("task") == "leaf-b" and "request_id" not in body and res.json() == want,
                   res.show() + repr(body))
        hx.clear()
        hx.set(refuse=None, noneEligible=True)
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
        _check(f"{_T} AC3 over_budget without_task: {{task: null}} and no reason in the output",
               res.rc == 0 and (res.json() or {}).get("task", 0) is None and "reason" not in (res.json() or {}), res.show())
        hx.set(noneEligible=None, offerTask="leaf-b")
        hx.clear()
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a", "--task", "leaf-b")
        body = (hx.bodies("next_task") or [None])[0]
        _check(f"{_T} AC3 next_task_claim: a claim returns the offer and stores a claim",
               res.rc == 0 and body is not None and set(body) == _wire_keys("next_task_claim") and (res.json() or {}).get("task", {}).get("task") == "leaf-b"
               and (hx.claimed() or {}).get("task") == "leaf-b", res.show())
    # reads and writes
    with V(R25) as hx:
        hx.claim("project", "session-a")
        hx.set(answers=[{**fx("list_asks")["response"]["asks"][0]}])
        hx.clear()
        res = hx.run("poll")
        body = (hx.bodies("list_asks") or [None])[0]
        _check(f"{_T} AC3 list_asks: key set = fixture request + connection, never a request_id; poll sees the owner answer",
               body is not None and set(body) == _wire_keys("list_asks") and body.get("since") == 0 and (res.json() or {}).get("newAnswers") == 1, res.show() + repr(body))
        res = hx.run("ask-status")
        body = (hx.bodies("ask_status") or [None])[0]
        _check(f"{_T} AC3 ask_status: key set = fixture request + connection, no request_id; stdout equals the fixture response",
               body is not None and set(body) == _wire_keys("ask_status") and res.json() == {"bound": True, "channel": "taskandi-http", "task": "project", "asks": fx("ask_status")["response"]["asks"]},
               res.show())
        _check(f"{_T} AC3: no read request ever carries request_id",
               all("request_id" not in (r["json"] or {}) for r in hx.reqs() if (r["json"] or {}).get("action") in READS), "")
    for name in ("ask", "comment", "record_usage", "record_time"):
        with V(R25) as hx:
            hx.claim("leaf-b", "session-a")
            key = "session-a:0001" if name == "record_usage" else f"k-{name}"
            task = "project" if name == "ask" else "leaf-b"
            if name == "ask":
                hx.claim("project", "session-a")
            payload = ask_payload() if name == "ask" else payload_of(name)
            r1 = hx.enq(name, key, payload, task)
            job0 = hx.job(key) or {}
            _check(f"{_T} AC3 {name}: enqueue stores a lowercase UUID v4 requestId outside the payload",
                   r1.rc == 0 and UUID4.match(job0.get("requestId", "")) and "requestId" not in job0.get("payload", {}) and "request_id" not in job0.get("payload", {}), r1.show() + repr(job0)[:300])
            hx.clear()
            res = hx.run("flush")
            body = (hx.bodies(name) or [None])[0]
            want = copy.deepcopy(fx(name)["request"])
            want.pop("request_id")
            if "agent" in want:
                want["agent"] = "claude"
            want["connection"] = _CONN
            want["task"] = task
            got = {k: v for k, v in (body or {}).items() if k != "request_id"}
            _check(f"{_T} AC3 {name}: sorted key set equals the fixture request + connection (request_id present on the write)",
                   body is not None and set(body) == _wire_keys(name), repr(sorted(body or {})) + " vs " + repr(sorted(_wire_keys(name))))
            _check(f"{_T} AC3 {name}: body values equal the fixture request (agent/session/task substituted)", got == want, repr(got)[:500])
            _check(f"{_T} AC3 {name}: the wire request_id is the job's requestId and a lowercase UUID v4",
                   body is not None and body.get("request_id") == job0.get("requestId") and UUID4.match(body.get("request_id", "")), repr(body)[:200])
            job = hx.job(key) or {}
            resp = (hx.applied(name) or [{}])[0].get("response")
            _check(f"{_T} AC3 {name}: job done and its stored result matches the server's response",
                   job.get("state") == "done" and resp is not None and (name not in ("ask", "record_usage") or all(json.dumps(v) in json.dumps(job.get("result")) for k, v in resp.items() if k in ("ask_id", "spent", "placed"))),
                   repr(job)[:400] + repr(resp))
    for name in ("release", "complete"):
        with V(R25) as hx:
            hx.claim("leaf-b", "session-a")
            args = ["release", "--task", "leaf-b", "--reason", fx("release")["request"]["reason"]] if name == "release" else \
                   ["complete", "--task", "leaf-b", "--summary", fx("complete")["request"]["summary"]]
            hx.clear()
            res = hx.run(*args)
            body = (hx.bodies(name) or [None])[0]
            want = copy.deepcopy(fx(name)["request"])
            want.pop("request_id")
            want["connection"] = _CONN
            _check(f"{_T} AC3 {name}: capabilities then {name}; key set = fixture request + connection incl. request_id; values equal",
                   hx.actions() == ["capabilities", name] and body is not None and set(body) == _wire_keys(name)
                   and {k: v for k, v in body.items() if k != "request_id"} == want and UUID4.match(body.get("request_id", "")), res.show() + repr(body))
            resp = (hx.applied(name) or [{}])[0].get("response") or {}
            key = "comment_id" if name == "release" else "completion_id"
            _check(f"{_T} AC3 {name}: stdout carries the server's {key}", res.rc == 0 and (res.json() or {}).get(key) == resp.get(key) and resp.get(key), res.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a")
        hx.comment("rt", fx("retry")["request"]["text"])
        hx.clear()
        hx.run("flush")
        body = (hx.bodies("comment") or [None])[0]
        _check(f"{_T} AC3 retry: the comment's key set equals the retry fixture's request + connection",
               body is not None and set(body) == set(fx("retry")["request"]) | {"connection"}, repr(body))
    with V(R22) as hx:
        hx.claim("leaf-b", "session-a")
        hx.comment("w22")
        hx.enq("record_usage", "u22", {**payload_of("record_usage"), "at": _T1 - 1000})
        hx.clear()
        hx.run("flush")
        sent = [b for a in WRITES for b in hx.bodies(a)]
        _check(f"{_T} AC3: a v2.2 server never receives request_id or at, and no job is frozen",
               len(sent) == 2 and all("request_id" not in b and "at" not in b for b in sent)
               and all(not (hx.job(k) or {}).get("sentBody") for k in ("w22", "u22")) and (hx.job("w22") or {}).get("state") == "done", repr(sent)[:400])


# ---------------------------------------------------------------------------
# AC4 Frozen body and resend
# ---------------------------------------------------------------------------

@safe
def test_v23_ac4_frozen_body_and_resend() -> None:
    print(f"{_T} AC4 frozen body and resend")
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(dropAfterApply={"comment": 1})
        hx.comment("c1", "first")
        hx.comment("c2", "second")
        res = hx.run("flush")
        first = (hx.raws("comment") or [""])[0]
        j1, j2 = hx.job("c1") or {}, hx.job("c2") or {}
        _check(f"{_T} AC4: a dropped response applied once, leaves c1 queued with attempts 1, lastError and the frozen sentBody; flush stopped",
               len(hx.applied("comment")) == 1 and j1.get("state") == "queued" and j1.get("attempts") == 1 and j1.get("lastError")
               and j1.get("sentBody") == first and hx.count("comment") == 1 and res.rc == 0, res.show() + repr(j1)[:300])
        _check(f"{_T} AC4: the frozen body carries session S1, the connection, the action and the job's requestId",
               json.loads(j1.get("sentBody") or "{}").get("session") == "S1" and json.loads(j1.get("sentBody") or "{}").get("request_id") == j1.get("requestId")
               and json.loads(j1.get("sentBody") or "{}").get("connection") == _CONN, repr(j1.get("sentBody")))
        _check(f"{_T} AC4: job order held - c2 was not sent and is not frozen", j2.get("state") == "queued" and not j2.get("sentBody") and not j2.get("attempts"), repr(j2)[:300])
        hx.claim("leaf-b", "S2")
        _check(f"{_T} AC4: control - the claim now says S2", (hx.claimed() or {}).get("session") == "S2", repr(hx.claimed()))
        hx.set(dropAfterApply=None)
        res = hx.run("flush")
        raws = hx.raws("comment")
        _check(f"{_T} AC4: after the claim changed to S2 the next flush resends a body byte-identical to the first",
               len(raws) >= 2 and raws[1] == first, repr(raws)[:600])
        _check(f"{_T} AC4: the fake server holds ONE c1 comment (one applied, one replay), c1 done",
               sum(1 for e in hx.applied("comment") if e["body"].get("text") == "first") == 1 and len(hx.replays("comment")) == 1 and (hx.job("c1") or {}).get("state") == "done", repr(hx.job("c1"))[:300])
        sent_c2 = [json.loads(r) for r in raws if '"second"' in r]
        _check(f"{_T} AC4: control - the not-yet-frozen c2 resolves its session now (S2) and is delivered",
               sent_c2 and sent_c2[0].get("session") == "S2" and (hx.job("c2") or {}).get("state") == "done" and len(hx.applied("comment")) == 2, repr(sent_c2))
    variants = [("lost response", {"dropAfterApply": {"comment": 9}}), ("non-JSON 200", {"rawAfterApply": {"comment": "not json at all"}}),
                ("200 failing the schema", {"badResponse": {"comment": {"task": "leaf-b"}}}),
                ("500 non-JSON", {"errors": {"comment": {"status": 500, "raw": "<html>oops</html>"}}}),
                ("unrecognised status 418", {"errors": {"comment": {"status": 418, "json": {"error": "teapot"}}}})]
    for label, ctl in variants:
        with V() as hx:
            hx.claim("leaf-b", "S1")
            hx.set(**ctl)
            hx.comment("c1")
            hx.run("flush")
            j = hx.job("c1") or {}
            _check(f"{_T} AC4: outcome-unknown ({label}) -> queued, attempts 1, lastError, sentBody and sentRevision frozen",
                   j.get("state") == "queued" and j.get("attempts") == 1 and j.get("lastError") and j.get("sentBody") and j.get("sentRevision") == R25, repr(j)[:400])
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(dropAfterApply={"comment": 99})
        hx.comment("c1")
        states = []
        for _ in range(5):
            hx.run("flush")
            j = hx.job("c1") or {}
            states.append((j.get("state"), j.get("attempts")))
        _check(f"{_T} AC4: five outcome-unknown attempts: queued x4 then uncertain", states == [("queued", 1), ("queued", 2), ("queued", 3), ("queued", 4), ("uncertain", 5)], repr(states))
        n = hx.count("comment")
        hx.run("flush")
        raws = set(hx.raws("comment"))
        _check(f"{_T} AC4: all five sends were the same bytes; one row server-side; the uncertain job is never sent again",
               n == 5 and len(raws) == 1 and len(hx.applied("comment")) == 1 and hx.count("comment") == 5 and (hx.job("c1") or {}).get("state") == "uncertain", f"{n} {len(raws)}")
        _check(f"{_T} AC4: status lists the uncertain job", "c1" in ((hx.run("status").json() or {}).get("uncertaintyIds") or []), "")
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(errors={"comment": {"status": 409, "json": {"error": "receipt_collision"}}})
        hx.comment("c1")
        hx.comment("c2")
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC4: receipt_collision on a FIRST send -> refused (receipt_collision), flush continues to c2",
               j.get("state") == "refused" and hx.refused().get("c1") == "receipt_collision" and hx.count("comment") == 2 and res.rc == 0, res.show() + repr(j)[:300])
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(dropAfterApply={"comment": 1})
        hx.comment("c1")
        hx.run("flush")
        hx.set(dropAfterApply=None, errors={"comment": {"status": 409, "json": {"error": "receipt_collision"}}})
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC4: receipt_collision on a RESEND -> uncertain (the first send was applied), with an explanation",
               j.get("state") == "uncertain" and j.get("lastError") and res.rc == 0 and len(hx.applied("comment")) == 1, repr(j)[:400])
        hx.set(errors=None)
        n = hx.count("comment")
        hx.run("flush")
        _check(f"{_T} AC4: and it is never retried automatically", hx.count("comment") == n and (hx.job("c1") or {}).get("state") == "uncertain", "")
    with V() as hx:
        hx.claim("leaf-b", "S1")
        r1 = hx.comment("c1", "same")
        j1 = copy.deepcopy(hx.job("c1"))
        r2 = hx.comment("c1", "same")
        j2 = hx.job("c1") or {}
        r3 = hx.comment("c1", "different")
        _check(f"{_T} AC4: requestId is outside the dedup digest - re-enqueueing the same key and payload dedupes and keeps the requestId; another payload is KEY_CONFLICT",
               r2.rc == 0 and j2.get("requestId") == j1.get("requestId") and j2.get("digest") == j1.get("digest") and r3.rc != 0 and "KEY_CONFLICT" in r3.err + r3.out, r3.show())
        hx.comment("c9", "same")
        _check(f"{_T} AC4: control - another job with the same text gets its own requestId, same digest",
               (hx.job("c9") or {}).get("requestId") != j1.get("requestId") and (hx.job("c9") or {}).get("digest") == j1.get("digest"), "")


# ---------------------------------------------------------------------------
# AC5 Crash, downgrade, upgrade
# ---------------------------------------------------------------------------

@safe
def test_v23_ac5_crash_downgrade_upgrade() -> None:
    print(f"{_T} AC5 crash, downgrade, upgrade")
    for label, ctl in (("applied before the crash", {"dropAfterApply": {"comment": 1}}), ("not applied before the crash", {"dropBeforeApply": {"comment": 1}})):
        with V() as hx:
            hx.claim("leaf-b", "S1")
            hx.set(**ctl)
            hx.comment("c1")
            hx.run("flush")
            first = (hx.raws("comment") or [""])[0]
            _edit_state(hx, lambda s: next(j for j in s["jobs"] if j["key"] == "c1").update(state="dispatching"))
            hx.claim("leaf-b", "S2")
            hx.set(dropAfterApply=None, dropBeforeApply=None)
            res = hx.run("flush")
            raws = hx.raws("comment")
            _check(f"{_T} AC5a: a job left dispatching with sentRevision v2.3 ({label}) resends its sentBody and finishes",
                   len(raws) == 2 and raws[1] == first and (hx.job("c1") or {}).get("state") == "done" and res.rc == 0, res.show() + repr(raws)[:300])
            _check(f"{_T} AC5a: the server has exactly one row ({label})", len(hx.applied("comment")) == 1, repr(len(hx.applied("comment"))))
    for label, edit in (("sentRevision v2.2", lambda j: j.update(state="dispatching", sentRevision=R22)), ("no sentRevision", lambda j: (j.update(state="dispatching"), j.pop("sentRevision", None)))):
        with V() as hx:
            hx.claim("leaf-b", "S1")
            hx.comment("c1")
            _edit_state(hx, lambda s: edit(next(j for j in s["jobs"] if j["key"] == "c1")))
            hx.clear()
            res = hx.run("flush")
            _check(f"{_T} AC5a: a job left dispatching with {label} becomes uncertain, nothing sent", (hx.job("c1") or {}).get("state") == "uncertain" and hx.write_reqs() == 0, res.show() + repr(hx.job("c1"))[:300])
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(dropAfterApply={"comment": 1})
        hx.comment("c1")
        hx.run("flush")
        _check(f"{_T} AC5b setup: c1 is queued with a sentBody after a v2.3 attempt", (hx.job("c1") or {}).get("sentBody") and (hx.job("c1") or {}).get("state") == "queued", repr(hx.job("c1"))[:200])
        hx.set(revision=R22, dropAfterApply=None)
        hx.clear()
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC5b: flushed against v2.2 the job becomes uncertain with the exact downgrade message and zero write requests",
               j.get("state") == "uncertain" and j.get("lastError") == MSG_DOWNGRADE and hx.write_reqs() == 0 and res.rc == 0, res.show() + repr(j)[:300])
        hx.set(revision=R25)
        hx.clear()
        hx.run("flush")
        _check(f"{_T} AC5b: and it is not retried when v2.3 returns", hx.write_reqs() == 0 and (hx.job("c1") or {}).get("state") == "uncertain", "")
    with V(R22) as hx:
        hx.claim("leaf-b", "S1")
        hx.set(errors={"comment": {"status": 409, "json": {"error": "connection_unavailable"}}})
        hx.comment("c1")
        hx.run("flush")
        _check(f"{_T} AC5c setup: under v2.2 an unknown outcome is uncertain, unfrozen", (hx.job("c1") or {}).get("state") == "uncertain" and not (hx.job("c1") or {}).get("sentBody"), repr(hx.job("c1"))[:300])
        hx.set(revision=R25, errors=None)
        hx.clear()
        hx.run("flush")
        hx.run("flush")
        _check(f"{_T} AC5c: a v2.2-uncertain job is never retried automatically on v2.3", hx.write_reqs() == 0 and (hx.job("c1") or {}).get("state") == "uncertain", "")
        rid = (hx.job("c1") or {}).get("requestId")
        res = hx.run("reconcile", "--key", "c1", "--action", "retry", "--evidence", "checked in Task&I: absent")
        _check(f"{_T} AC5c: reconcile --action retry requeues it", res.rc == 0 and (hx.job("c1") or {}).get("state") == "queued", res.show())
        hx.run("flush")
        body = (hx.bodies("comment") or [None])[0]
        j = hx.job("c1") or {}
        _check(f"{_T} AC5c: the retry sends once, with its enqueue-time requestId, and freezes sentBody",
               hx.count("comment") == 1 and body is not None and body.get("request_id") == rid and UUID4.match(rid or "") and j.get("state") == "done"
               and j.get("sentBody") == (hx.raws("comment") or [""])[0] and len(hx.applied("comment")) == 1, repr(j)[:400])


# ---------------------------------------------------------------------------
# AC6 complete / release on v2.3 (and Rev 2.1 M1)
# ---------------------------------------------------------------------------

_SUMMARY, _REASON = "Exporter written; tests green.", "Parked until the owner answers."
_ARGS = {"complete": lambda t=_SUMMARY: ["complete", "--task", "leaf-b", "--summary", t], "release": lambda t=_REASON: ["release", "--task", "leaf-b", "--reason", t]}
_DROP1 = lambda call: {"dropAfterApply": {call: 1}}  # noqa: E731


def _plain_claim_after(call: str):
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.run(*_ARGS[call]())
        return hx.claimed()


@safe
def test_v23_ac6_complete_release() -> None:
    print(f"{_T} AC6 complete/release on v2.3 (pendingDirect with request_id and frozen sentBody)")
    for call in ("complete", "release"):
        want_claim = _plain_claim_after(call)
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(**_DROP1(call))
            hx.clear()
            r1 = hx.run(*_ARGS[call]())
            pd = copy.deepcopy((hx.state() or {}).get("pendingDirect") or {})
            first = (hx.raws(call) or [""])[0]
            _check(f"{_T} AC6: {call} with an unknown outcome exits 1, keeps the claim and leaves pendingDirect {{call, task, at, requestId, sentRevision, fieldsDigest, sentBody}}",
                   r1.rc == 1 and pd.get("call") == call and pd.get("task") == "leaf-b" and isinstance(pd.get("at"), int) and UUID4.match(pd.get("requestId", ""))
                   and pd.get("sentRevision") == R25 and pd.get("fieldsDigest") and hx.claimed() is not None and r1.out.strip() == "", r1.show() + repr(pd)[:400])
            _check(f"{_T} AC6 M1: pendingDirect stores the frozen sentBody byte for byte (session and request_id inside)",
                   pd.get("sentBody") == first and json.loads(pd.get("sentBody") or "{}").get("request_id") == pd.get("requestId")
                   and json.loads(pd.get("sentBody") or "{}").get("session") == "session-a", repr(pd.get("sentBody")))
            hx.claim("leaf-b", "session-b")
            _check(f"{_T} AC6 M1: control - the claim's session changed to session-b", (hx.claimed() or {}).get("session") == "session-b", "")
            hx.set(dropAfterApply=None)
            r2 = hx.run(*_ARGS[call]())
            raws = hx.raws(call)
            _check(f"{_T} AC6 M1: the same command resends the stored sentBody byte for byte even though the session changed",
                   len(raws) == 2 and raws[1] == first and r2.rc == 0, r2.show() + repr(raws)[:300])
            _check(f"{_T} AC6: one {call} server-side (one applied + one replay); pendingDirect cleared; claim as after a plain {call}",
                   len(hx.applied(call)) == 1 and len(hx.replays(call)) == 1 and not (hx.state() or {}).get("pendingDirect") and hx.claimed() == want_claim
                   or (len(hx.applied(call)) == 1 and not (hx.state() or {}).get("pendingDirect") and (hx.claimed() is None) == (want_claim is None)),
                   r2.show() + repr(hx.claimed()))
            key = "completion_id" if call == "complete" else "comment_id"
            _check(f"{_T} AC6: the settled output carries the original response's {key}", (r2.json() or {}).get(key) == hx.applied(call)[0]["response"][key], r2.show())
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(**_DROP1(call))
            hx.run(*_ARGS[call]())
            pd1 = copy.deepcopy((hx.state() or {}).get("pendingDirect"))
            hx.set(dropAfterApply=None)
            hx.clear()
            r = hx.run(*_ARGS[call]("a different text"))
            _check(f"{_T} AC6: the same command with different text exits 1, sends no {call}, keeps the record unchanged",
                   r.rc == 1 and hx.count(call) == 0 and (hx.state() or {}).get("pendingDirect") == pd1 and hx.claimed() is not None, r.show())
            r = hx.run(*_ARGS[call]())
            _check(f"{_T} AC6: control - the original text still settles it afterwards", r.rc == 0 and not (hx.state() or {}).get("pendingDirect") and len(hx.applied(call)) + len(hx.replays(call)) == 1 and len(hx.replays(call)) == 1, r.show())
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(**_DROP1(call))
            hx.run(*_ARGS[call]())
            pd1 = copy.deepcopy((hx.state() or {}).get("pendingDirect"))
            hx.set(dropAfterApply=None, errors={call: {"status": 409, "json": {"error": "receipt_collision"}}})
            r = hx.run(*_ARGS[call]())
            _check(f"{_T} AC6: receipt_collision on a resend exits 1 and keeps the pending record (the first send was applied)",
                   r.rc == 1 and (hx.state() or {}).get("pendingDirect") == pd1 and len(hx.applied(call)) == 1 and hx.claimed() is not None, r.show())
        with V(R22) as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(errors={call: {"status": 409, "json": {"error": "connection_unavailable"}}})
            hx.run(*_ARGS[call]())
            pd = (hx.state() or {}).get("pendingDirect") or {}
            _check(f"{_T} AC6: under v2.2 the pending record has no requestId", pd.get("call") == call and "requestId" not in pd, repr(pd)[:300])
            hx.set(revision=R25, errors=None)
            hx.clear()
            r = hx.run(*_ARGS[call]())
            _check(f"{_T} AC6: a v2.2 pending record blocks on v2.3 as today (exact message, no {call} sent)",
                   r.rc == 1 and f"an earlier {call} for leaf-b has an unknown outcome" in r.err and hx.count(call) == 0, r.show())
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.set(errors={"complete": {"status": 409, "json": {"error": "open_children", "children": [{"task": "child-1", "title": "Child one"}]}}})
        r = hx.run(*_ARGS["complete"]())
        out = r.json() or {}
        _check(f"{_T} AC6 M1: open_children on v2.3 maps as on v2.2 (exit 0, completed false, children listed, claim kept) and clears the pending record",
               r.rc == 0 and out.get("completed") is False and out.get("open_children") and hx.claimed() is not None and not (hx.state() or {}).get("pendingDirect"), r.show())
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.set(**_DROP1("release"))
        hx.run(*_ARGS["release"]())
        hx.set(dropAfterApply=None)
        hx.clear()
        r = hx.run(*_ARGS["complete"]())
        _check(f"{_T} AC6: control - a pending release does not block a complete of the same task (different call)", r.rc == 0 and hx.count("complete") == 1, r.show())


@safe
def test_v23_family_treated_alike() -> None:
    print(f"{_T} family: v2.3, v2.4 and v2.5 behave identically")
    for rev in FAMILY:
        t = rev[-4:]
        with V(rev) as hx:
            hx.claim("project", "S1")
            _check(f"{_T} family [{t}]: claim.contract and lastContract record the exact string", (hx.claimed() or {}).get("contract") == rev and (hx.state() or {}).get("lastContract") == rev, "")
            hx.set(dropAfterApply={"comment": 1})
            hx.comment("c1", task="project")
            hx.run("flush")
            first = (hx.raws("comment") or [""])[0]
            hx.set(dropAfterApply=None)
            hx.run("flush")
            _check(f"{_T} family [{t}]: request_id replay - the resend is byte-identical and the server holds one comment",
                   len(hx.raws("comment")) == 2 and hx.raws("comment")[1] == first and len(hx.applied("comment")) == 1 and (hx.job("c1") or {}).get("sentRevision") == rev, "")
            hx.set(refuse="closed")
            res = hx.run("next-task", "--agent", "claude", "--session", "S1", "--task", "project")
            _check(f"{_T} family [{t}]: next-task --task sends task and a refusal prints its reason",
                   res.json() == {"bound": True, "channel": "taskandi-http", "task": None, "reason": "closed"}, res.show())
            hx.set(answers=[{**fx("list_asks")["response"]["asks"][0]}])
            hx.run("poll")
            hx.run("poll")
            sinces = [b.get("since") for b in hx.bodies("list_asks")]
            _check(f"{_T} family [{t}]: the seq cursor is stored and sent exactly", sinces == [0, 1] and ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 1}, repr(sinces))


def _run_all() -> None:
    for fn in [test_v23_ac1_negotiation, test_v23_ac2_binding_digest, test_v23_ac3_wire_per_fixture, test_v23_ac4_frozen_body_and_resend,
               test_v23_ac5_crash_downgrade_upgrade, test_v23_ac6_complete_release, test_v23_family_treated_alike]:
        fn()


if __name__ == "__main__":
    _run_all()
    passed = sum(_RESULTS)
    print(f"total: {len(_RESULTS)} passed: {passed} failed: {len(_RESULTS) - passed}")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail[:300]}")
        raise SystemExit(1)
    print("PASS: Task&I v2.3 checks, part 1")
