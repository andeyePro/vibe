#!/usr/bin/env python3
"""Acceptance checks for task_066 cycle 2 (the "Rev 4 addendum", AC17-AC28 of ``.vs/spec.md``).

Tester-owned (cycle 2).  Reuses the harness of ``checks_58_taskandi_v23.py``.  The fake service models Task&I's
replay rule exactly: a ``request_id`` replays only for the SAME connection with the same body; the same id from another
connection is a fresh request.  Server-side application counts therefore prove "no duplicate" across a re-grant.

Run only this module with:
    python3 smoke/checks_60_taskandi_v23_review.py
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _RESULTS, _T1, _check
from smoke.checks_55_taskandi_http_review import _edit_state
from smoke.checks_58_taskandi_v23 import MSG_DOWNGRADE, R22, R25, UUID4, V, _ARGS, _REPO, payload_of, safe
from smoke.checks_59_taskandi_v23_more import _DAY, _open_ask, _usage_job, crec, usage_payload

__all__ = ["test_v23_ac17_v22_negotiation", "test_v23_ac18_new_connection", "test_v23_ac19_definite_answers", "test_v23_ac20_not_sent",
           "test_v23_ac21_limits_after_send", "test_v23_ac22_at_not_identity", "test_v23_ac23_spent_contract", "test_v23_ac24_whole_workspace",
           "test_v23_ac25_action_bound", "test_v23_ac26_frozen_integrity", "test_v23_ac28_prose", "test_v23_ac29_non_proof_answers"]
_T = "[taskandi-v23-r4]"
MSG_CONN = "sent on a previous Task&I connection; replay is unavailable — check Task&I, then reconcile"


def new_connection(hx: V, name="conn-REGRANT-77") -> None:
    hx.conn = name
    hx.write_desc()


def frozen_comment(hx: V, key="c1", text="hello", session="S1", before=False) -> dict:
    """A comment whose first send was lost (applied unless ``before``) and is therefore frozen."""
    hx.claim("leaf-b", session)
    hx.set(**({"dropBeforeApply": {"comment": 1}} if before else {"dropAfterApply": {"comment": 1}}))
    hx.comment(key, text)
    hx.run("flush")
    hx.set(dropAfterApply=None, dropBeforeApply=None)
    return copy.deepcopy(hx.job(key) or {})


# ---------------------------------------------------------------------------
@safe
def test_v23_ac17_v22_negotiation() -> None:
    print(f"{_T} AC17 v2.2 negotiation")
    with V(R22) as hx:
        hx.claim()
        _check(f"{_T} AC17: a v2.2 answer sets state.lastContract and status reports it",
               (hx.state() or {}).get("lastContract") == R22 and (hx.run("status").json() or {}).get("lastContract") == R22, repr((hx.state() or {}).get("lastContract")))
    lim = {"unit": "code_points", "id": 200}
    for label, add in (("limits", {"limits": lim}), ("id_pattern", {"id_pattern": "^x$"})):
        with V(R22) as hx:
            hx.set(capsAdd=add)
            hx.comment()
            hx.clear()
            res = hx.run("flush")
            _check(f"{_T} AC17: a v2.2 answer carrying {label}: exit 1, only capabilities sent, job still queued",
                   res.rc == 1 and hx.actions() == ["capabilities"] and (hx.job("c1") or {}).get("state") == "queued", res.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac18_new_connection() -> None:
    print(f"{_T} AC18 a new connection means no resend")
    with V() as hx:
        job = frozen_comment(hx)
        _check(f"{_T} AC18 setup: c1 is frozen on the first connection and applied once", job.get("sentBody") and len(hx.applied("comment")) == 1, repr(job)[:200])
        new_connection(hx)
        hx.clear()
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC18: after the connection changed the job is uncertain with the exact message and NO write request",
               j.get("state") == "uncertain" and j.get("lastError") == MSG_CONN and hx.write_reqs() == 0 and res.rc == 0, res.show() + repr(j)[:300])
        hx.run("flush")
        _check(f"{_T} AC18: and it is never retried automatically; the server still holds exactly one row", hx.write_reqs() == 0, "")
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.comment("fresh", "unfrozen job on a new connection")
        new_connection(hx)
        hx.clear()
        res = hx.run("flush")
        _check(f"{_T} AC18: control - a never-sent job is sent normally on the new connection",
               res.rc == 0 and (hx.job("fresh") or {}).get("state") == "done" and hx.bodies("comment")[0]["connection"] == "conn-REGRANT-77", res.show())
    for call in ("complete", "release"):
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(dropAfterApply={call: 1})
            hx.run(*_ARGS[call]())
            pd = copy.deepcopy((hx.state() or {}).get("pendingDirect"))
            hx.set(dropAfterApply=None)
            new_connection(hx)
            hx.clear()
            res = hx.run(*_ARGS[call]())
            _check(f"{_T} AC18: {call} after a connection change exits 1 with the message, sends no {call}, keeps the record and the claim",
                   res.rc == 1 and MSG_CONN in res.err and hx.count(call) == 0 and (hx.state() or {}).get("pendingDirect") == pd and hx.claimed() is not None, res.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac19_definite_answers() -> None:
    print(f"{_T} AC19 definite answers to a resend")
    for code in ("stale_context", "sync_required", "lease_held"):   # Rev 5: connection_unavailable/connection_revoked are NOT proof on a resend
        with V() as hx:
            job = frozen_comment(hx, before=True)
            rid = job.get("requestId")
            first = (hx.raws("comment") or [""])[0]
            hx.claim("leaf-b", "S2")
            hx.set(errors={"comment": {"status": 409, "json": {"error": code}}})
            hx.run("flush")
            j = hx.job("c1") or {}
            _check(f"{_T} AC19: try-later ({code}) on a resend: sentBody cleared, job queued, same requestId",
                   j.get("state") == "queued" and not j.get("sentBody") and j.get("requestId") == rid, repr(j)[:300])
            hx.set(errors=None)
            hx.run("flush")
            body = hx.bodies("comment")[-1]
            _check(f"{_T} AC19: the next attempt rebuilds the body with the new session S2 and the same request_id; one row",
                   body.get("session") == "S2" and body.get("request_id") == rid and hx.raws("comment")[-1] != first and len(hx.applied("comment")) == 1
                   and (hx.job("c1") or {}).get("state") == "done", repr(body))
    for code in ("use_native_connection", "scope_missing", "invalid_request", "wrong_scope", "wrong_thread", "unknown_ask", "not_assigned"):
        with V() as hx:
            frozen_comment(hx, before=True)
            hx.set(errors={"comment": {"status": 409, "json": {"error": code}}})
            hx.run("flush")
            _check(f"{_T} AC19: a rejected resend ({code}) is refused, not uncertain", (hx.job("c1") or {}).get("state") == "refused" and hx.refused().get("c1") == code, repr(hx.job("c1"))[:200])
    with V() as hx:
        frozen_comment(hx)
        hx.set(errors={"comment": {"status": 409, "json": {"error": "receipt_collision"}}})
        hx.run("flush")
        _check(f"{_T} AC19: receipt_collision on a resend stays uncertain", (hx.job("c1") or {}).get("state") == "uncertain", "")
    # first sends
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(errors={"comment": {"status": 409, "json": {"error": "stale_context"}}})
        hx.comment("c1")
        hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC19: a definite refusal of a FIRST send leaves no sentBody and counts no attempt", j.get("state") == "queued" and not j.get("sentBody") and not j.get("attempts"), repr(j)[:300])
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.comment("c1")
        rid0 = (hx.job("c1") or {}).get("requestId")
        hx.set(errors={"comment": {"status": 409, "json": {"error": "receipt_collision"}}})
        hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC19: receipt_collision on a first send: refused, and the job got a NEW request_id (the old one is burned)",
               j.get("state") == "refused" and UUID4.match(j.get("requestId", "")) and j.get("requestId") != rid0 and not j.get("sentBody"), repr(j)[:300])
        hx.set(errors=None)
        hx.run("reconcile", "--key", "c1", "--action", "retry", "--evidence", "collision was a reused id")
        hx.run("flush")
        _check(f"{_T} AC19: after a retry the new request_id is what goes on the wire",
               hx.bodies("comment")[-1].get("request_id") == j.get("requestId") and (hx.job("c1") or {}).get("state") == "done", "")
    # pendingDirect
    for call in ("complete", "release"):
        for code, kind in (("stale_context", "try-later"), ("wrong_scope", "rejected")):
            with V() as hx:
                hx.claim("leaf-b", "S1")
                hx.set(dropBeforeApply={call: 1})
                hx.run(*_ARGS[call]())
                _check(f"{_T} AC19 setup: {call} left a pending record", bool((hx.state() or {}).get("pendingDirect")), "")
                hx.set(dropBeforeApply=None, errors={call: {"status": 409, "json": {"error": code}}})
                res = hx.run(*_ARGS[call]())
                _check(f"{_T} AC19: {call}: a {kind} answer to the resend (same connection) settles the pending record (nothing was applied), exit 1",
                       res.rc == 1 and not (hx.state() or {}).get("pendingDirect") and hx.claimed() is not None, res.show())
                hx.set(errors=None)
                res = hx.run(*_ARGS[call]())
                _check(f"{_T} AC19: {call}: the command can then be sent afresh and lands once", res.rc == 0 and len(hx.applied(call)) == 1, res.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac20_not_sent() -> None:
    print(f"{_T} AC20 not-sent attempts never freeze")
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.comment("c1")
        hx.set(stopAfterCaps=True)
        hx.clear()
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC20: a connect failure after capabilities: job queued, no sentBody, attempts not incremented, no write reached the server",
               j.get("state") == "queued" and not j.get("sentBody") and not j.get("attempts") and hx.write_reqs() == 0, res.show() + repr(j)[:300])
    # exact-body size check: request_id and at included
    def size_of(kind: str) -> int:
        with V() as m:
            m.claim("leaf-b", "S1")
            if kind == "usage":
                m.enq("record_usage", "u1", usage_payload(at=_T1 - 1000))
            else:
                m.comment("c1", "size probe")
            m.run("flush")
            return len((m.reqs()[-1]["body"]).encode())
    for kind in ("comment", "usage"):
        n = size_of(kind)
        for limit, refused in ((n, False), (n - 1, True)):
            with V() as hx:
                hx.claim("leaf-b", "S1")
                hx.set(limits={"request_bytes": limit})
                if kind == "usage":
                    hx.enq("record_usage", "u1", usage_payload(at=_T1 - 1000))
                    key, act = "u1", "record_usage"
                else:
                    hx.comment("c1", "size probe")
                    key, act = "c1", "comment"
                hx.clear()
                hx.run("flush")
                j = hx.job(key) or {}
                ok = (j.get("state") == "refused" and hx.count(act) == 0 and hx.refused().get(key) == "over_server_limit") if refused else (j.get("state") == "done")
                _check(f"{_T} AC20: {kind}: request_bytes {limit} vs an exact {n}-byte body (request_id{', at' if kind == 'usage' else ''} included) -> {'refused with zero requests' if refused else 'sent'}",
                       ok, repr(j)[:200])


# ---------------------------------------------------------------------------
@safe
def test_v23_ac21_limits_after_send() -> None:
    print(f"{_T} AC21 server limits only before a first send")
    with V() as hx:
        job = frozen_comment(hx, text="x" * 400)
        first = (hx.raws("comment") or [""])[0]
        hx.set(limits={"comment": 50, "request_bytes": 200})
        hx.run("flush")
        _check(f"{_T} AC21: a frozen job is resent unchanged after the server lowered its limits; the server decides (replay), one row",
               hx.raws("comment")[-1] == first and len(hx.raws("comment")) == 2 and (hx.job("c1") or {}).get("state") == "done" and len(hx.applied("comment")) == 1, repr(hx.job("c1"))[:300])
        hx.comment("c2", "y" * 400)
        hx.run("flush")
        _check(f"{_T} AC21: control - a fresh job over the lowered limits is refused (over_server_limit)", hx.refused().get("c2") == "over_server_limit", repr(hx.refused()))
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.set(dropAfterApply={"complete": 1})
        hx.run(*_ARGS["complete"]("s" * 200))
        hx.set(dropAfterApply=None, limits={"summary": 20})
        res = hx.run(*_ARGS["complete"]("s" * 200))
        _check(f"{_T} AC21: a pending complete is resent unchanged after the summary limit dropped (settles, one row)", res.rc == 0 and len(hx.applied("complete")) == 1, res.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac22_at_not_identity() -> None:
    print(f"{_T} AC22 at is not identity")
    t0 = _T1 - _DAY
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        tr = hx.base / "claude.jsonl"
        tr.write_text(crec("m1", "model-a", None) + "\n")
        r1 = hx.run("usage", "--transcript", str(tr), "--session", "sess-1", "--account", "acct", "--cost-estimate", "0")
        n = len([j for j in hx.jobs() if j.get("kind") == "record_usage"])
        tr.write_text(crec("m1", "model-a", t0) + "\n")
        r2 = hx.run("usage", "--transcript", str(tr), "--session", "sess-1", "--account", "acct", "--cost-estimate", "0")
        jobs = [j for j in hx.jobs() if j.get("kind") == "record_usage"]
        _check(f"{_T} AC22: a pre-upgrade row (no `at`) re-imported with timestamps deduplicates (no KEY_CONFLICT, no new job) and keeps its payload",
               r1.rc == 0 and n == 1 and r2.rc == 0 and len(jobs) == 1 and "at" not in jobs[0]["payload"], r2.show() + repr(jobs)[:300])
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        r1 = hx.enq("record_usage", "u1", usage_payload())
        hx.run("flush")
        j = copy.deepcopy(hx.job("u1"))
        _edit_state(hx, lambda s: (s["jobs"].remove(next(x for x in s["jobs"] if x["key"] == "u1")),
                                   s.setdefault("tombstones", []).append({"key": "u1", "kind": "record_usage", "digest": j["digest"], "doneAtMs": j.get("doneAtMs", _T1)})))
        r2 = hx.enq("record_usage", "u1", usage_payload(at=t0))
        _check(f"{_T} AC22: a tombstone without `at` deduplicates a re-enqueue that carries one (no new job)", r1.rc == 0 and r2.rc == 0 and hx.job("u1") is None, r2.show())
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.enq("record_usage", "u1", usage_payload(at=t0))
        r = hx.enq("record_usage", "u1", usage_payload(at=t0 - 5000))
        _check(f"{_T} AC22: the stored payload keeps the first `at` seen", r.rc == 0 and (hx.job("u1") or {}).get("payload", {}).get("at") == t0, r.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac23_spent_contract() -> None:
    print(f"{_T} AC23 spent carries its counting rule")
    with V(R22) as hx:
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 0, "tokens": 0}, "allowance": {"tokens": 1000}})
        _check(f"{_T} AC23: a v2.2 claim records spentContract v2.2", (hx.claimed() or {}).get("spentContract") == R22, repr(hx.claimed())[:300])
        hx.set(revision=R25)
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 0, "tokens": 0, "cache_read": 0}, "allowance": {"tokens": 1000}})
        c = hx.claimed() or {}
        _check(f"{_T} AC23: a renewal under v2.5 records spentContract v2.5 (and claim.contract)", c.get("spentContract") == R25 and c.get("contract") == R25, repr(c)[:300])
        _usage_job(hx)
        hx.clear()
        _check(f"{_T} AC23: pending_tokens follows spentContract v2.5: 35", (hx.run("decide", "--remaining-minutes", "10").json() or {}).get("budget", {}).get("pending_tokens") == 35, "")
        hx.run("flush")
        # a record_usage answered by a v2.2 service updates spent and its spentContract
        hx.set(revision=R22)
        hx.enq("record_usage", "u2", {"model": "m", "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0, "account": "acct"})
        hx.run("flush")
        c = hx.claimed() or {}
        _check(f"{_T} AC23: a record_usage response from a v2.2 service sets spentContract v2.2 while claim.contract stays v2.5",
               c.get("spentContract") == R22 and c.get("contract") == R25, repr(c)[:400])
        _usage_job(hx, "pu2")
        hx.clear()
        b = (hx.run("decide", "--remaining-minutes", "10").json() or {}).get("budget", {})
        _check(f"{_T} AC23: pending_tokens now uses the v2.2 counting rule that produced `spent` (535), not claim.contract's", b.get("pending_tokens") == 535, repr(b))
        hx.set(revision=R25)
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 0, "tokens": 5, "cache_read": 0}})
        c = hx.claimed() or {}
        _check(f"{_T} AC23: a renewal under v2.5 over v2.2-counted spent REPLACES it (like with like), spentContract back to v2.5",
               c.get("spentContract") == R25 and (c.get("spent") or {}).get("tokens") == 5, repr(c)[:300])


# ---------------------------------------------------------------------------
@safe
def test_v23_ac24_whole_workspace() -> None:
    print(f"{_T} AC24 next-task --task on a whole-workspace connection")
    args = ["next-task", "--agent", "claude", "--session", "session-a", "--task"]
    with V(root=None) as hx:
        hx.set(refuse="closed")
        res = hx.run(*args, "any-usable.id:1")
        _check(f"{_T} AC24: with no effective task any usable id is accepted and sent", res.rc == 0 and (hx.bodies("next_task") or [{}])[0].get("task") == "any-usable.id:1"
               and (res.json() or {}).get("reason") == "closed", res.show())
        hx.clear()
        res = hx.run(*args, "a b")
        _check(f"{_T} AC24: control - an unusable id is a usage error with zero requests", res.rc == 1 and hx.reqs() == [], res.show())
        hx.set(refuse=None)
        hx.claim("leaf-b", "session-a")
        hx.set(offerTask="leaf-b")
        hx.clear()
        res = hx.run(*args, "project")
        _check(f"{_T} AC24: the server returning this client's own claim: exit 1 'the server returned your current claim instead', no release",
               res.rc == 1 and "the server returned your current claim instead" in res.err and hx.count("release") == 0 and (hx.claimed() or {}).get("task") == "leaf-b", res.show() + repr(hx.actions()))
        hx.set(offerTask="somebody-elses")
        hx.clear()
        res = hx.run(*args, "project")
        _check(f"{_T} AC24: control - a foreign task is still handed back with one release",
               res.rc == 1 and hx.count("release") == 1 and (hx.bodies("release") or [{}])[0].get("task") == "somebody-elses", res.show())


# ---------------------------------------------------------------------------
@safe
def test_v23_ac25_action_bound() -> None:
    print(f"{_T} AC25 action is bounded data")
    for label, action, good in (("2000 characters", "a" * 2000, True), ("2001 characters", "a" * 2001, False),
                                ("2000 emoji (code points, not UTF-16 units)", "\U0001F600" * 2000, True), ("2001 emoji", "\U0001F600" * 2001, False)):
        with V() as hx:
            hx.set(offer={"action": action})
            res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
            _check(f"{_T} AC25: an action of {label} is {'accepted' if good else 'malformed (exit 1, no claim)'}",
                   (res.rc == 0 and hx.claimed() is not None) if good else (res.rc == 1 and hx.claimed() is None), res.show()[:200])
    text = (_REPO / "devcontainer" / "taskandi-harness.md").read_text()
    safety = text.split("### Safety rules", 1)[1]
    _check(f"{_T} AC25: the harness safety rule lists `action` with `title` and `body` as data, never instructions",
           re.search(r"`title`[^.\n]*`body`[^.\n]*`action`|`action`[^.\n]*`title`|`title`[^.\n]*`action`", safety) is not None, safety[:400])


# ---------------------------------------------------------------------------
@safe
def test_v23_ac26_frozen_integrity() -> None:
    print(f"{_T} AC26 frozen-body integrity")
    def tamper(label: str, edit, bad: bool, usage=False):
        with V() as hx:
            hx.claim("leaf-b", "S1")
            hx.set(dropBeforeApply={"record_usage" if usage else "comment": 1})   # nothing applied, so an allowed edit is a legitimate resend
            if usage:
                hx.enq("record_usage", "u1", usage_payload(at=_T1 - 1000))
            else:
                hx.comment("c1")
            hx.run("flush")
            hx.set(dropBeforeApply=None)
            key = "u1" if usage else "c1"

            def ed(s):
                job = next(x for x in s["jobs"] if x["key"] == key)
                b = json.loads(job["sentBody"])
                edit(b)
                job["sentBody"] = json.dumps(b)
            _edit_state(hx, ed)
            hx.clear()
            hx.run("flush")
            j = hx.job(key) or {}
            if bad:
                _check(f"{_T} AC26: {label} -> tampered_job, nothing sent", j.get("state") == "refused" and hx.refused().get(key) == "tampered_job" and hx.write_reqs() == 0, repr(j)[:200] + repr(hx.refused()))
            else:
                _check(f"{_T} AC26: {label} -> accepted and resent", j.get("state") in ("done", "queued") and hx.refused().get(key) is None and hx.write_reqs() == 1, repr(j)[:200])
    tamper("a different session in sentBody", lambda b: b.update(session="other-session"), True)
    tamper("an agent that is neither claude nor codex", lambda b: b.update(agent="evil"), True)
    tamper("an `at` outside the freeze-time window (ancient)", lambda b: b.update(at=1000), True, usage=True)
    tamper("an `at` far in the future", lambda b: b.update(at=_T1 + 10 * _DAY), True, usage=True)
    tamper("control: the untouched frozen body", lambda b: None, False)
    tamper("control: agent codex", lambda b: b.update(agent="codex"), False)
    tamper("control: session removed", lambda b: b.pop("session", None), False)


# ---------------------------------------------------------------------------
@safe
def test_v23_ac28_prose() -> None:
    print(f"{_T} AC28 harness and docs agree")
    text = (_REPO / "devcontainer" / "taskandi-harness.md").read_text()
    row = next((l for l in text.splitlines() if l.startswith("|") and "outcome unknown" in l and "complete" in l), "")
    _check(f"{_T} AC28: the complete/release outcome-unknown failure row says to repeat the same command once on v2.3 with the same connection, otherwise not to retry",
           row != "" and "v2.3" in row and "same connection" in row and re.search(r"repeat the same command", row) and re.search(r"do not retry", row), row)
    docs = (_REPO / "docs" / "taskandi-client.md").read_text()
    sent = [s for s in re.split(r"(?<=[.!?])\s+", docs) if "hostile server" in s]
    _check(f"{_T} AC28: the docs have a sentence on a hostile server faking receipt_collision or inflating seq",
           any("receipt_collision" in s and "seq" in s for s in sent) or any("receipt_collision" in s for s in sent) and any("seq" in s for s in sent), repr(sent)[:300])


# ---------------------------------------------------------------------------
# Rev 5: AC29 / AC30
# ---------------------------------------------------------------------------

_NON_PROOF = [("connection_revoked", {"status": 409, "json": {"error": "connection_revoked"}}), ("connection_unavailable", {"status": 409, "json": {"error": "connection_unavailable"}}),
              ("400 invalid_request", {"status": 400, "json": {"error": "invalid_request"}}), ("403 connection_scope", {"status": 403, "json": {"error": "connection_scope"}}),
              ("405 method_not_allowed", {"status": 405, "json": {"error": "method_not_allowed"}}), ("421 wrong_origin", {"status": 421, "json": {"error": "wrong_origin"}}),
              ("unlisted 409 code", {"status": 409, "json": {"error": "made_up_code"}}), ("500 non-JSON", {"status": 500, "raw": "<html>"})]
_TRY_LATER = ["stale_context", "sync_required", "lease_held"]
_REJECTED = ["use_native_connection", "scope_missing", "invalid_request", "wrong_scope", "wrong_thread", "unknown_ask", "not_assigned"]


@safe
def test_v23_ac29_non_proof_answers() -> None:
    print(f"{_T} AC29 only in-transaction answers prove anything on a resend")
    for label, spec in _NON_PROOF:
        with V() as hx:
            frozen_comment(hx, before=True)
            j0 = copy.deepcopy(hx.job("c1") or {})
            hx.set(errors={"comment": spec})
            attempts = [j0.get("attempts")]
            states = []
            for _ in range(4):
                res = hx.run("flush")
                j = hx.job("c1") or {}
                attempts.append(j.get("attempts"))
                states.append(j.get("state"))
                if j.get("sentBody") != j0.get("sentBody") and j.get("state") != "uncertain":
                    break
            j = hx.job("c1") or {}
            _check(f"{_T} AC29: [{label}] on a resend the job keeps sentBody and counts one attempt each time (1..5), queued until the 5th, then uncertain",
                   attempts == [1, 2, 3, 4, 5] and states == ["queued", "queued", "queued", "uncertain"] and j.get("sentBody") == j0.get("sentBody"), repr((attempts, states)))
            if label == "connection_revoked":
                _check(f"{_T} AC29: [{label}] the revoked-connection preface is printed on a resend", "revoked or replaced" in res.err or "revoked or replaced" in res.out, res.show())
        for call in ("complete", "release"):
            with V() as hx:
                hx.claim("leaf-b", "S1")
                hx.set(dropBeforeApply={call: 1})
                hx.run(*_ARGS[call]())
                pd = copy.deepcopy((hx.state() or {}).get("pendingDirect"))
                hx.set(dropBeforeApply=None, errors={call: spec})
                res = hx.run(*_ARGS[call]())
                _check(f"{_T} AC29: [{label}] a pending {call} keeps its record unchanged, exits 1 with the outcome-unknown message, claim kept",
                       res.rc == 1 and pd is not None and (hx.state() or {}).get("pendingDirect") == pd and "outcome unknown" in res.err.lower() and hx.claimed() is not None, res.show())
                if label == "connection_revoked":
                    _check(f"{_T} AC29: [{label}] {call}: the revoked preface is printed", "revoked or replaced" in res.err, res.show())
    # proof codes: behave as AC19 for jobs and pending records
    for code in _TRY_LATER + _REJECTED:
        with V() as hx:
            frozen_comment(hx, before=True)
            hx.set(errors={"comment": {"status": 409, "json": {"error": code}}})
            hx.run("flush")
            j = hx.job("c1") or {}
            ok = (j.get("state") == "queued" and not j.get("sentBody")) if code in _TRY_LATER else (j.get("state") == "refused" and hx.refused().get("c1") == code)
            _check(f"{_T} AC29: proof code {code} on a resend -> {'queued, sentBody cleared' if code in _TRY_LATER else 'refused'}", ok, repr(j)[:250])
        with V() as hx:
            hx.claim("leaf-b", "S1")
            hx.set(dropBeforeApply={"complete": 1})
            hx.run(*_ARGS["complete"]())
            hx.set(dropBeforeApply=None, errors={"complete": {"status": 409, "json": {"error": code}}})
            res = hx.run(*_ARGS["complete"]())
            _check(f"{_T} AC29: proof code {code} settles a pending complete (record cleared, exit 1)", res.rc == 1 and not (hx.state() or {}).get("pendingDirect"), res.show())
    # a proof code from a non-409 status is not proof
    with V() as hx:
        frozen_comment(hx, before=True)
        hx.set(errors={"comment": {"status": 400, "json": {"error": "stale_context"}}})
        hx.run("flush")
        _check(f"{_T} AC29: a proof code under a non-409 status is not proof (sentBody kept)", bool((hx.job("c1") or {}).get("sentBody")) and (hx.job("c1") or {}).get("state") == "queued", repr(hx.job("c1"))[:200])
    # the full sequence
    with V() as hx:
        job = frozen_comment(hx)
        first = (hx.raws("comment") or [""])[0]
        hx.set(errors={"comment": {"status": 409, "json": {"error": "connection_revoked"}}})
        res = hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC29 sequence: the revoked resend keeps the frozen body (queued, attempts 2) and prints the preface",
               j.get("state") == "queued" and j.get("sentBody") == first and j.get("attempts") == 2 and "revoked or replaced" in res.err, res.show() + repr(j)[:200])
        hx.set(errors=None)
        new_connection(hx)
        hx.run("flush")
        j = hx.job("c1") or {}
        _check(f"{_T} AC29 sequence: after a fresh descriptor the job is uncertain (replayLost) with the connection message, nothing sent on the new connection",
               j.get("state") == "uncertain" and j.get("replayLost") is True and j.get("lastError") == MSG_CONN and all(b.get("connection") != "conn-REGRANT-77" for b in hx.bodies("comment")), repr(j)[:300])
        _check(f"{_T} AC29 sequence: the fake server holds exactly one write", len(hx.applied("comment")) == 1, repr(len(hx.applied("comment"))))
        res = hx.run("reconcile", "--key", "c1", "--action", "retry", "--evidence", "checked")
        _check(f"{_T} AC30: reconcile --action retry on a replayLost job prints the new-write warning",
               "this sends a new write on the current connection; Task&I cannot tell it from the earlier one, so check it was not applied" in res.out + res.err and res.rc == 0, res.show())
    with V() as hx:
        hx.claim("leaf-b", "S1")
        hx.set(errors={"comment": {"status": 409, "json": {"error": "connection_unavailable"}}})
        hx.comment("c1")
        hx.run("flush")
        hx.set(errors=None)
        hx.run("flush")
        res = hx.run("reconcile", "--key", "c1", "--action", "retry", "--evidence", "x") if (hx.job("c1") or {}).get("state") == "uncertain" else None
        _check(f"{_T} AC30: control - the warning is only for replay-lost jobs (an ordinary uncertain job does not get it)",
               res is None or "this sends a new write on the current connection" not in res.out + res.err, res.show() if res else "job was not uncertain")


def _run_all() -> None:
    for name in __all__:
        globals()[name]()


if __name__ == "__main__":
    _run_all()
    passed = sum(_RESULTS)
    print(f"total: {len(_RESULTS)} passed: {passed} failed: {len(_RESULTS) - passed}")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail[:300]}")
        raise SystemExit(1)
    print("PASS: Task&I v2.3 checks, cycle 2")
