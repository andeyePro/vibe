#!/usr/bin/env python3
"""Acceptance checks for task_067 cycle 2 (Rev 3 addendum): AC15-AC27.

Tester-owned.  Harness and helpers come from ``checks_61_taskandi_propose.py`` / ``checks_62_taskandi_propose_more.py``.
Secret-shaped strings are assembled at run time so this file never contains one literally.

Run only this module with:
    python3 smoke/checks_63_taskandi_propose_cycle2.py
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _T1, _check, _Hx
from smoke.checks_55_taskandi_http_review import _edit_state
from smoke.checks_58_taskandi_v23 import R25, V, safe
from smoke.checks_61_taskandi_propose import DAY, create_applied, entry, ledger, make, mcp_hx, pay, propose, rp, text
from smoke.checks_62_taskandi_propose_more import set_ledger

_REPO = Path(__file__).resolve().parent.parent
_T = "[taskandi-cycle2]"
__all__ = ["test_c2_ac15_updates_ledger", "test_c2_ac16_claimed_limits", "test_c2_ac17_order", "test_c2_ac18_ids", "test_c2_ac19_stampless",
           "test_c2_ac20_retry", "test_c2_ac21_reconciled", "test_c2_ac22_session_agent", "test_c2_ac23_limits_when_needed",
           "test_c2_ac24_hostile", "test_c2_ac25_secrets", "test_c2_ac26_terminal_safe", "test_c2_ac27_prose"]
UP = "AB12CD34-5678-4ABC-9DEF-0123456789AB"
LO = UP.lower()


def upd(hx: V, key: str, payload: dict, stamp=None, env=None):
    return hx.run("enqueue", "update_task", "--key", key, *(["--session", stamp] if stamp else []), stdin=json.dumps(payload), env=env)


def synth(key: str, tid: str, title: str, **kw) -> dict:
    e = {"key": key, "task_id": tid, "title": title, "titleNorm": title.lower(), "assign": "owner", "parent": None, "agent": "claude",
         "repeat": False, "session": None, "at": _T1, "gone": False}
    e.update(kw)
    return e


def uncertain_job(hx: V, key: str, **kw) -> None:
    _edit_state(hx, lambda s: next(j for j in s["jobs"] if j["key"] == key).update(state="uncertain", **kw))


# ---------------------------------------------------------------------------
@safe
def test_c2_ac15_updates_ledger() -> None:
    print(f"{_T} AC15 updates keep the ledger true")
    with V(R25) as hx:
        e1 = make(hx, "e1", "Original title", ids=["u15-1"])
        upd(hx, "u1", {"task": e1, "title": "  Brand NEW, title!! "})
        hx.run("flush")
        e = entry(hx, e1)
        _check(f"{_T} AC15: a done retitle updates the entry's title and titleNorm in the same write", (hx.job("u1") or {}).get("state") == "done" and e.get("title") == "  Brand NEW, title!! " and e.get("titleNorm") == "brand new, title", repr(e))
        r = propose(hx, "d1", pay("brand new, title"))
        r2 = propose(hx, "d2", pay("Original title"))
        _check(f"{_T} AC15: the duplicate key moved with the retitle (new title blocked, old title free)", r.rc == 1 and "duplicate_proposal" in text(r) and r2.rc == 0, r.show() + r2.show())
    with V(R25) as hx:
        a = make(hx, "a", "Plain A", ids=["u15-a"])
        b = make(hx, "b", "Plain B", ids=["u15-b"])
        c = make(hx, "c", "Plain C", ids=["u15-c"])
        for i in range(2):
            make(hx, f"r{i}", f"Repeating {i}", repeat=rp(), stamp=f"S{i}")
        r1 = upd(hx, "ua", {"task": a, "repeat": rp()})
        r2 = upd(hx, "ub", {"task": b, "repeat": rp()})
        _check(f"{_T} AC15: with 2 ledger repeats, one queued update adding a repeat fits, a second would be the 4th and is refused repeat_cap",
               r1.rc == 0 and r2.rc == 1 and "repeat_cap" in text(r2) and hx.job("ub") is None, r1.show() + r2.show())
        hx.run("flush")
        _check(f"{_T} AC15: a done update with a repeat object sets repeat true on the entry", entry(hx, a).get("repeat") is True, repr(entry(hx, a)))
        r3 = propose(hx, "r9", pay("Fourth repeat", repeat=rp()), stamp="S9")
        _check(f"{_T} AC15: a 4th outstanding repeat creation is refused after the update made the 3rd", r3.rc == 1 and "repeat_cap" in text(r3), r3.show())
        upd(hx, "uclr", {"task": a, "repeat": None})
        hx.run("flush")
        _check(f"{_T} AC15: a done update with repeat null sets repeat false", entry(hx, a).get("repeat") is False, repr(entry(hx, a)))
        r4 = upd(hx, "ub2", {"task": b, "repeat": rp()})
        _check(f"{_T} AC15: clearing a repeat frees a slot", r4.rc == 0, r4.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a")
        r = upd(hx, "np", {"task": "leaf-b", "repeat": rp()})
        _check(f"{_T} AC15: repeat on a non-ledger (claimed) task is refused", r.rc == 1 and "repeat only on your own proposals" in text(r) and hx.job("np") is None, r.show())
        t = make(hx, "g", "Will be gone", ids=["u15-g"])
        set_ledger(hx, lambda l: [x.update(gone=True) for x in l])
        r = upd(hx, "gp", {"task": t, "repeat": rp()})
        _check(f"{_T} AC15: repeat on a gone entry is refused", r.rc == 1 and ("repeat only on your own proposals" in text(r) or "not your task" in text(r)) and hx.job("gp") is None, r.show())


@safe
def test_c2_ac16_claimed_limits() -> None:
    print(f"{_T} AC16 claimed non-ledger task")
    msg = "on the owner's task vibe may only change next_action"
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a")
        for i, p in enumerate(({"title": "x"}, {"notes": "n"}, {"estimate_minutes": 5}, {"next_action": "ok", "title": "x"}, {"repeat": None})):
            r = upd(hx, f"c{i}", {"task": "leaf-b", **p})
            _check(f"{_T} AC16: update of the claimed non-ledger task with {sorted(p)} is refused", r.rc == 1 and hx.job(f"c{i}") is None and (msg in text(r) or "repeat only" in text(r)), r.show())
        r = upd(hx, "ok1", {"task": "leaf-b", "next_action": "Do the next bit"}, stamp="SS")
        _check(f"{_T} AC16: next_action alone is accepted", r.rc == 0 and hx.job("ok1") is not None, r.show())
        r = upd(hx, "ok2", {"task": "leaf-b", "next_action": "Another"}, stamp="SS")
        _check(f"{_T} AC16: a second update of the same target under the same stamp is refused update_cap", r.rc == 1 and "update_cap" in text(r) and hx.job("ok2") is None, r.show())
        r = upd(hx, "ok3", {"task": "leaf-b", "next_action": "Another"}, stamp="SS2")
        _check(f"{_T} AC16 control: another session stamp may update it", r.rc == 0, r.show())
        t = make(hx, "m", "Mine", ids=["u16-m"])
        r1 = upd(hx, "m1", {"task": t, "title": "T1"}, stamp="SS")
        r2 = upd(hx, "m2", {"task": t, "title": "T2"}, stamp="SS")
        _check(f"{_T} AC16: the one-update-per-target-per-stamp rule holds for own proposals too", r1.rc == 0 and r2.rc == 1 and "update_cap" in text(r2), r2.show())


@safe
def test_c2_ac17_order() -> None:
    print(f"{_T} AC17 order of enqueue checks")
    with V(R25) as hx:
        r1 = propose(hx, "k1", pay("Alpha"))
        r2 = propose(hx, "k1", pay("Alpha"))
        _check(f"{_T} AC17: same key, same payload deduplicates", r1.rc == 0 and r2.rc == 0 and (r2.json() or {}).get("deduplicated") is True, r2.show())
        propose(hx, "k2", pay("Gamma"))
        r3 = propose(hx, "k1", pay("Beta"))
        _check(f"{_T} AC17: same key, different payload is KEY_CONFLICT, not duplicate_proposal", r3.rc != 0 and "KEY_CONFLICT" in text(r3) and "duplicate_proposal" not in text(r3), r3.show())
        r4 = propose(hx, "k1", pay("Gamma"))
        _check(f"{_T} AC17: KEY_CONFLICT wins even when the new title duplicates another proposal", r4.rc != 0 and "KEY_CONFLICT" in text(r4) and "duplicate_proposal" not in text(r4), r4.show())
    with V(R25) as hx:
        hx.set(errors={"create_task": {"status": 409, "json": {"error": "invalid_request"}}})
        propose(hx, "bad", pay("Fix me"))
        hx.run("flush")
        hx.set(errors=None)
        _check(f"{_T} AC17 setup: the first proposal was refused", (hx.job("bad") or {}).get("state") == "refused", repr(hx.job("bad"))[:200])
        r = propose(hx, "good", pay("Fix me", notes="corrected"))
        _check(f"{_T} AC17: a refused create does not block a corrected proposal with the same title", r.rc == 0 and hx.job("good") is not None, r.show())


@safe
def test_c2_ac18_ids() -> None:
    print(f"{_T} AC18 ids normalised")
    forms = [("upper-case UUID", UP), ("taskandeye://node/ prefix", f"taskandeye://node/{UP}"), ("prefix with lower-case", f"taskandeye://node/{LO}")]
    for label, form in forms:
        with V(R25) as hx:
            hx.set(createIds={"Ledger one": LO})
            make(hx, "l1", "Ledger one")
            hx.clear()
            propose(hx, "p1", pay("Child", parent=form))
            hx.run("flush")
            b = (hx.bodies("create_task") or [{}])[0]
            _check(f"{_T} AC18: parent as {label} is sent lower-cased without the prefix", b.get("parent") == LO, repr(b)[:200])
            r = upd(hx, "u1", {"task": form, "title": "Renamed"})
            hx.run("flush")
            b = (hx.bodies("update_task") or [{}])[0]
            _check(f"{_T} AC18: update_task.task as {label} is accepted against the ledger and sent normalised", r.rc == 0 and b.get("task") == LO, r.show() + repr(b)[:200])
            out = hx.run("created", "--task", form).json() or {}
            _check(f"{_T} AC18: created --task {label} matches the normalised parent", [x["task_id"] for x in out.get("created", [])] == [x["task_id"] for x in out.get("created", [])] and len(out.get("created", [])) == 1 and out["created"][0].get("title") == "Child", repr(out)[:300])
        with V(R25) as hx:
            hx.set(dropAfterApply={"create_task": 1})
            propose(hx, "s2", pay("Collide"))
            hx.run("flush")
            hx.set(dropAfterApply=None, errors={"create_task": {"status": 409, "json": {"error": "receipt_collision"}, "times": 1}})
            hx.run("flush")
            r = hx.run("reconcile", "--key", "s2", "--action", "done", "--task-id", form, "--evidence", "seen")
            _check(f"{_T} AC18: reconcile --task-id as {label} is stored normalised", r.rc == 0 and entry(hx, LO).get("key") == "s2", r.show() + repr(ledger(hx))[:200])


@safe
def test_c2_ac19_stampless() -> None:
    print(f"{_T} AC19 no stamp, no session cap")
    with V(R25) as hx:
        for i in range(4):
            t = make(hx, f"n{i}", f"Stampless {i}")
            _check(f"{_T} AC19: stamp-less create #{i + 1} is accepted (no per-session cap)", t is not None, "")
        for i in range(3):
            t = make(hx, f"s{i}", f"Stamped {i}", stamp="S")
            _check(f"{_T} AC19: stamped create #{i + 1} under S is accepted although 4 stamp-less ones exist", t is not None, "")
        for i in range(3):
            make(hx, f"m{i}", f"More stampless {i}")
        _check(f"{_T} AC19: ten creations so far", len(ledger(hx)) == 10, str(len(ledger(hx))))
        r = propose(hx, "x11", pay("Eleventh"))
        _check(f"{_T} AC19: the rolling 24-hour cap still applies to stamp-less creates", r.rc == 1 and "proposal_cap" in text(r), r.show())


@safe
def test_c2_ac20_retry() -> None:
    print(f"{_T} AC20 retrying a creation")
    with V(R25) as hx:
        propose(hx, "j", pay("Retry subject"))
        uncertain_job(hx, "j", noRetry=True)
        r = hx.run("reconcile", "--key", "j", "--action", "retry", "--evidence", "e")
        _check(f"{_T} AC20: retry of a noRetry create is refused (exit 1, still uncertain, nothing queued)", r.rc == 1 and (hx.job("j") or {}).get("state") == "uncertain", r.show())
        r = hx.run("reconcile", "--key", "j", "--action", "done", "--task-id", "owner-id-77", "--evidence", "e")
        _check(f"{_T} AC20: done --task-id is still allowed on a noRetry create", r.rc == 0 and entry(hx, "owner-id-77"), r.show())
    with V(R25) as hx:
        propose(hx, "j", pay("Retry dup"))
        uncertain_job(hx, "j")
        set_ledger(hx, lambda l: l.append(synth("other", "other-1", "retry dup")))
        r = hx.run("reconcile", "--key", "j", "--action", "retry", "--evidence", "e")
        _check(f"{_T} AC20: a retry re-runs the duplicate check (refused duplicate_proposal)", r.rc == 1 and "duplicate_proposal" in text(r) and (hx.job("j") or {}).get("state") == "uncertain", r.show())
    with V(R25) as hx:
        propose(hx, "j", pay("Retry cap"))
        uncertain_job(hx, "j")
        set_ledger(hx, lambda l: l.extend(synth(f"f{i}", f"fill-{i}", f"Filler {i}") for i in range(10)))
        r = hx.run("reconcile", "--key", "j", "--action", "retry", "--evidence", "e")
        _check(f"{_T} AC20: a retry re-runs the caps (refused proposal_cap)", r.rc == 1 and "proposal_cap" in text(r) and (hx.job("j") or {}).get("state") == "uncertain", r.show())
    with V(R25) as hx:
        propose(hx, "j", pay("Retry fine"))
        uncertain_job(hx, "j")
        r = hx.run("reconcile", "--key", "j", "--action", "retry", "--evidence", "e")
        _check(f"{_T} AC20 control: a retry with no conflicts is queued", r.rc == 0 and (hx.job("j") or {}).get("state") == "queued", r.show())


def _uncertain_via_collision(hx: V, key="s", title="Reconciled one") -> None:
    hx.set(dropAfterApply={"create_task": 1})
    propose(hx, key, pay(title, assign="agent"))
    hx.run("flush")
    hx.set(dropAfterApply=None, errors={"create_task": {"status": 409, "json": {"error": "receipt_collision"}, "times": 1}})
    hx.run("flush")
    hx.set(errors=None)


@safe
def test_c2_ac21_reconciled() -> None:
    print(f"{_T} AC21 reconciled entries")
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a")
        mine = make(hx, "have", "Existing entry", ids=["exists-1"])
        _uncertain_via_collision(hx)
        for label, tid in (("the claimed task", "leaf-b"), ("the effective task", "project"), ("an existing ledger id", mine)):
            r = hx.run("reconcile", "--key", "s", "--action", "done", "--task-id", tid, "--evidence", "e")
            _check(f"{_T} AC21: reconcile --task-id {label} exits 1 and writes nothing", r.rc == 1 and (hx.job("s") or {}).get("state") == "uncertain" and not entry(hx, tid) or (tid == mine and len(ledger(hx)) == 1 and r.rc == 1), r.show())
        r = hx.run("reconcile", "--key", "s", "--action", "done", "--task-id", "rec-1", "--evidence", "e")
        e = entry(hx, "rec-1")
        _check(f"{_T} AC21: a valid id writes the entry with reconciled true", r.rc == 0 and e.get("reconciled") is True, r.show() + repr(e))
        r = upd(hx, "ur", {"task": "rec-1", "title": "x"})
        _check(f"{_T} AC21: a reconciled entry does not widen the update_task allowance", r.rc == 1 and "not your task" in text(r), r.show())
        hx.clear()
        r = hx.run("next-task", "--agent", "claude", "--session", "s9", "--task", "rec-1")
        _check(f"{_T} AC21: a reconciled assign=agent entry is still not dispatchable (no next_task request)", hx.count("next_task") == 0, r.show() + repr(hx.actions()))
        _check(f"{_T} AC21 control: the normally-made entry is not marked reconciled", not entry(hx, mine).get("reconciled"), repr(entry(hx, mine)))


@safe
def test_c2_ac22_session_agent() -> None:
    print(f"{_T} AC22 session only when persona and claim agree")
    with V(R25) as hx:
        propose(hx, "p", pay("Proposed as claude"))
        hx.claim("leaf-b", "session-a", agent="codex")
        hx.clear()
        hx.run("flush")
        b = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC22: job agent claude, claim agent codex: session omitted", b.get("agent") == "claude" and "session" not in b, repr(b))
    with V(R25) as hx:
        propose(hx, "p", pay("Proposed as claude"))
        hx.claim("leaf-b", "session-a", agent="claude")
        hx.clear()
        hx.run("flush")
        b = (hx.bodies("create_task") or [{}])[0]
        _check(f"{_T} AC22 control: matching agents send session", b.get("agent") == "claude" and b.get("session") == "session-a", repr(b))
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", agent="codex")
        upd(hx, "u0", {"task": "leaf-b", "next_action": "go"})
        hx.clear()
        hx.run("flush")
        bs = hx.bodies("update_task")
        _check(f"{_T} AC22: an update on the claimed task takes the claim's persona, so the agents agree and session is sent", len(bs) == 1 and bs[0].get("agent") == "codex" and bs[0].get("session") == "session-a", repr(bs)[:300])
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", agent="claude")
        upd(hx, "u", {"task": "leaf-b", "next_action": "go"})
        hx.claim("leaf-b", "session-a", agent="codex")
        hx.clear()
        hx.run("flush")
        bs = hx.bodies("update_task")
        _check(f"{_T} AC22: an update job whose agent differs from the claim's agent also omits session", all("session" not in b for b in bs), repr(bs)[:300])


@safe
def test_c2_ac23_limits_when_needed() -> None:
    print(f"{_T} AC23 proposal limits only when needed")
    with V(R25) as hx:
        hx.set(capsDrop=["title", "next_action", "notes"])
        r = hx.claim("leaf-b", "session-a")
        _check(f"{_T} AC23: next-task works against a v2.5 server without the proposal limits", r.rc == 0 and hx.claimed() is not None, r.show())
        hx.run("enqueue", "comment", "--key", "c1", "--task", "leaf-b", stdin=json.dumps({"text": "hello"}))
        propose(hx, "pr", pay("Needs limits"))
        hx.clear()
        res = hx.run("flush")
        _check(f"{_T} AC23: flush delivers the comment and sends no proposal", (hx.job("c1") or {}).get("state") == "done" and hx.count("create_task") == 0 and (hx.job("pr") or {}).get("state") != "done", res.show() + repr(hx.job("pr"))[:200])
        res = hx.run("complete", "--task", "leaf-b", "--summary", "done")
        _check(f"{_T} AC23: complete works without the proposal limits", res.rc == 0 and (res.json() or {}).get("completed") is True, res.show())
        hx.set(capsDrop=None)
        hx.run("flush")
        _check(f"{_T} AC23 control: once the limits are present the proposal is sent", (hx.job("pr") or {}).get("state") == "done", repr(hx.job("pr"))[:200])


@safe
def test_c2_ac24_hostile() -> None:
    print(f"{_T} AC24 hostile results")
    for label, setup in (("an existing ledger id", "ledger"), ("the claimed task", "leaf-b"), ("the effective task", "project")):
        with V(R25) as hx:
            hx.claim("leaf-b", "session-a")
            have = make(hx, "have", "Existing", ids=["h24-1"])
            tid = have if setup == "ledger" else setup
            hx.set(badResponse={"create_task": {"task_id": tid, "provisional": True}})
            propose(hx, "new", pay("Echo attack"))
            hx.run("flush")
            _check(f"{_T} AC24: a create result echoing {label} goes uncertain, adds no entry", (hx.job("new") or {}).get("state") == "uncertain" and len(ledger(hx)) == 1, repr(hx.job("new"))[:250])
    with V(R25) as hx:
        make(hx, "ag", "Agent job", assign="agent", ids=["ag-old"])
        make(hx, "ow", "Owner job", assign="owner", ids=["ow-old"])
        old = _T1 - 200 * DAY
        set_ledger(hx, lambda l: [x.update(at=old) for x in l])
        hx.claim("project", "s1")
        hx.run("enqueue", "comment", "--key", "seed", "--task", "project", stdin=json.dumps({"text": "x"}))
        hx.run("flush")
        seed = copy.deepcopy(hx.job("seed"))
        def stuff(s):
            s["jobs"] = [dict(copy.deepcopy(seed), key=f"c{i}", doneAtMs=_T1 - 10 * DAY + i, state="done") for i in range(2100)]
        _edit_state(hx, stuff)
        hx.run("enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        hx.run("flush")
        ids = {x["task_id"] for x in ledger(hx)}
        _check(f"{_T} AC24: an assign=agent entry survives age and pruning; the same-age owner entry is dropped", "ag-old" in ids and "ow-old" not in ids, repr(ids))
    with V(R25) as hx:
        propose(hx, "ag", pay("Do the thing", assign="agent"))
        uncertain_job(hx, "ag")
        hx.set(offerTask="x-task-1", offer={"title": "do THE thing."})
        r = hx.run("next-task", "--agent", "claude", "--session", "s1")
        out = r.json() or {}
        _check(f"{_T} AC24: an offer whose title matches an uncertain agent creation is released as self_created",
               out.get("reason") == "self_created" and out.get("task", 0) is None and hx.claimed() is None and len(hx.bodies("release")) == 1, r.show())
        hx.set(offer={"title": "Something unrelated"})
        hx.run("next-task", "--agent", "claude", "--session", "s2")
        _check(f"{_T} AC24 control: an unrelated title is claimed", (hx.claimed() or {}).get("task") == "x-task-1", repr(hx.claimed())[:200])


@safe
def test_c2_ac25_secrets() -> None:
    print(f"{_T} AC25 no secrets in proposals")
    pats = {"ghp": "ghp" + "_" + "a1B2" * 9, "gho": "gho" + "_" + "a1B2" * 9, "github_pat": "github" + "_pat_" + "A1b2C3d4E5" * 5,
            "sk": "sk" + "-" + "abcdEFGH1234" * 4, "sk-ant": "sk" + "-ant-" + "abcdEFGH1234" * 4, "AKIA": "AKIA" + "ABCDEFGHIJKLMNOP",
            "private key": "-----BEGIN RSA " + "PRIVATE KEY-----" + "\nMIIE\n"}
    with V(R25) as hx:
        tid = make(hx, "tg", "Secret target", ids=["sec-1"])
        wipe_jobs = lambda: _edit_state(hx, lambda s: s.update(jobs=[], tombstones=[]))
        for name, val in pats.items():
            for field in ("title", "next_action", "notes"):
                wipe_jobs()
                p = pay("Plain title")
                p[field] = f"see {val} for access"
                r = propose(hx, "sc", p)
                _check(f"{_T} AC25: create with a {name} secret in {field} exits 1 'contains_secret: {field}', nothing queued",
                       r.rc == 1 and f"contains_secret: {field}" in text(r) and hx.job("sc") is None and val[:12] not in text(r), r.show())
                r = upd(hx, "su", {"task": tid, field: f"see {val} for access"})
                _check(f"{_T} AC25: update with a {name} secret in {field} exits 1 'contains_secret: {field}'", r.rc == 1 and f"contains_secret: {field}" in text(r) and hx.job("su") is None, r.show())
        wipe_jobs()
        r = propose(hx, "ok", pay("A skill and a ghost: AKIA is a word, sk-1 is short", notes="ghp_ alone is not a token"))
        _check(f"{_T} AC25 control: text that only resembles a prefix is accepted", r.rc == 0 and hx.job("ok") is not None, r.show())


@safe
def test_c2_ac26_terminal_safe() -> None:
    print(f"{_T} AC26 terminal-safe errors")
    with V(R25) as hx:
        for label, key in (("an escape sequence", "\x1b[31mevil"), ("a space", "a b"), ("a leading digit", "1abc"), ("65 characters", "k" * 65), ("a newline", "x\ny")):
            r = hx.run("enqueue", "create_task", "--key", "h", stdin=json.dumps(pay("Hostile", repeat={**rp(), key: 1})))
            _check(f"{_T} AC26: an unknown repeat key with {label} is not echoed ('invalid repeat: unknown key')",
                   r.rc == 1 and "invalid repeat: unknown key" in text(r) and "\x1b" not in text(r) and key not in text(r), r.show())
        r = hx.run("enqueue", "create_task", "--key", "h", stdin=json.dumps(pay("Safe", repeat={**rp(), "colour_2": 1})))
        _check(f"{_T} AC26 control: a well-formed unknown key is still named", r.rc == 1 and "invalid repeat: colour_2" in text(r), r.show())
    for label, mk in (("MCP binding", mcp_hx), ("unbound project", lambda: _Hx(bound=False))):
        with mk() as hx:
            r = hx.cli("enqueue", "update_task", "--key", "m", stdin=json.dumps({"task": "x", "title": "t"}))
            _check(f"{_T} AC26: update_task on a {label} says 'update_task needs a Task&I descriptor binding'", r.rc == 1 and "update_task needs a Task&I descriptor binding" in text(r), r.show())


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text()).lower()


@safe
def test_c2_ac27_prose() -> None:
    print(f"{_T} AC27 harness and docs wording")
    h = _flat(_REPO / "devcontainer" / "taskandi-harness.md")
    sec = h[h.find("propose a task"):] if "propose a task" in h else ""
    _check(f"{_T} AC27: the harness has a Propose a task step", bool(sec), "")
    _check(f"{_T} AC27: the step proposes only with assign: \"owner\"", re.search(r"only .{0,60}assign: ?\"owner\"|assign: ?\"owner\".{0,80}only", sec) is not None, sec[:300])
    _check(f"{_T} AC27: no sentence implies the owner can unblock an assign: \"agent\" proposal", "unblock" not in sec, "")
    _check(f"{_T} AC27: owner answer means an answer to a question vibe asked", re.search(r"owner answer.{0,200}question", sec) is not None, "")
    _check(f"{_T} AC27: the no-secrets rule covers title, next_action and notes", re.search(r"secret.{0,160}title.{0,20}next_action.{0,20}notes|title.{0,20}next_action.{0,40}notes.{0,160}secret", sec) is not None, "")
    _check(f"{_T} AC27: never retry a create_task, report it in fromClaude", re.search(r"never retry", sec) is not None and "fromclaude" in sec, "")
    _check(f"{_T} AC27: reconciling creations or updates is for the owner only", re.search(r"reconcil.{0,120}owner only|owner only.{0,120}reconcil", sec) is not None, "")
    d = _flat(_REPO / "docs" / "taskandi-client.md")
    i = d.find("proposing tasks")
    body = d[i:i + 15000]
    _check(f"{_T} AC27: the docs say the caps and self_created are client-side and can be defeated by editing local state", "client-side" in body and "local state" in body, "")
    _check(f"{_T} AC27: the docs say Task&I has been asked about server-side enforcement", "server-side" in body and re.search(r"task&i has been asked|asked task&i|asked whether", body) is not None, "")


def main() -> int:
    for fn in (test_c2_ac15_updates_ledger, test_c2_ac16_claimed_limits, test_c2_ac17_order, test_c2_ac18_ids, test_c2_ac19_stampless, test_c2_ac20_retry,
               test_c2_ac21_reconciled, test_c2_ac22_session_agent, test_c2_ac23_limits_when_needed, test_c2_ac24_hostile, test_c2_ac25_secrets,
               test_c2_ac26_terminal_safe, test_c2_ac27_prose):
        fn()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
