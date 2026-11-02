#!/usr/bin/env python3
"""Acceptance checks for task_066 (Task&I client, contract v2.3 family), part 2: AC7-AC16 and Rev 2.1 M2/M3.

Tester-owned (cycle 1).  Part 1 (AC1-AC6) and the harness (``V``, the fake service) live in ``checks_58_taskandi_v23.py``.

Run only this module with:
    python3 smoke/checks_59_taskandi_v23_more.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _CLIENT, _FIX_BRAIN, _RESULTS, _T1, _check, _cur, _fixture
from smoke.checks_53_taskandi_decide import H, LS
from smoke.checks_55_taskandi_http_review import _edit_state
from smoke.checks_58_taskandi_v23 import (MSG_DOWNGRADE, NAMES23, R22, R23, R25, UUID4, V, _FIX23, _REPO, fix_dir, fx,
                                          payload_of, ask_payload, safe)

__all__ = ["test_v23_ac7_error_table", "test_v23_ac8_seq_cursor", "test_v23_ac9_offer_schema", "test_v23_ac10_next_task_named", "test_v23_ac11_at", "test_v23_ac12_decide", "test_v23_ac13_server_limits", "test_v23_ac14_harness", "test_v23_ac16_fixtures_docs_limits"]
_T = "[taskandi-v23]"
_DAY = 86400_000
_ANOTHER = {"task": "x"}


def _j(status, code, **extra):
    return {"status": status, "json": {"error": code, **extra}}


# ---------------------------------------------------------------------------
# AC7 v2.3 error table
# ---------------------------------------------------------------------------

_QUEUED_STOP = [("connection_revoked", _j(409, "connection_revoked")), ("connection_unavailable", _j(409, "connection_unavailable")),
                ("stale_context", _j(409, "stale_context")), ("sync_required", _j(409, "sync_required")), ("lease_held", _j(409, "lease_held")),
                ("403 connection_scope", _j(403, "connection_scope")), ("405 method_not_allowed", _j(405, "method_not_allowed")),
                ("421 wrong_origin", _j(421, "wrong_origin"))]
_REFUSED = [(c, _j(409, c)) for c in ("use_native_connection", "scope_missing", "invalid_request", "wrong_scope", "wrong_thread", "unknown_ask", "not_assigned")] + \
           [("400 invalid_request", _j(400, "invalid_request"))]
_MALFORMED = [("403 other body", {"status": 403, "json": {"foo": 1}}), ("405 other body", _j(405, "nope")), ("421 other body", _j(421, "nope")),
              ("400 other body", _j(400, "nope")), ("403 non-JSON", {"status": 403, "raw": "<html>"})]


@safe
def test_v23_ac7_error_table() -> None:
    print(f"{_T} AC7 v2.3 error table")
    for label, spec in _QUEUED_STOP:
        with V() as hx:
            hx.comment("e1", "first")
            hx.comment("e2", "second")
            hx.set(errors={"comment": spec})
            hx.clear()
            res = hx.run("flush")
            e1, e2 = hx.job("e1") or {}, hx.job("e2") or {}
            _check(f"{_T} AC7: {label}: e1 and e2 back to queued with no attempt counted, flush stops after 1 request, exit 0",
                   e1.get("state") == "queued" and e2.get("state") == "queued" and not e1.get("attempts") and hx.count("comment") == 1 and res.rc == 0,
                   res.show() + repr(e1)[:300])
            _check(f"{_T} AC7: {label}: lastError records the code (or its class)", bool(e1.get("lastError")), repr(e1))
            if label == "connection_revoked":
                _check(f"{_T} AC7: connection_revoked prints the revoked message", "the Task&I connection was revoked or replaced" in res.err, res.show())
            hx.set(errors=None)
            hx.run("flush")
            _check(f"{_T} AC7: {label}: control - once the service recovers both jobs are delivered, one row each",
                   (hx.job("e1") or {}).get("state") == "done" and (hx.job("e2") or {}).get("state") == "done" and len(hx.applied("comment")) == 2, "")
    for label, spec in _REFUSED:
        with V() as hx:
            hx.comment("e1", "first")
            hx.comment("e2", "second")
            hx.set(errors={"comment": spec})
            hx.clear()
            res = hx.run("flush")
            code = spec["json"]["error"]
            _check(f"{_T} AC7: {label}: both jobs refused, flush continues (2 requests), exit 0, status names the code",
                   (hx.job("e1") or {}).get("state") == "refused" and (hx.job("e2") or {}).get("state") == "refused" and hx.count("comment") == 2
                   and res.rc == 0 and hx.refused().get("e1") == code, res.show() + repr(hx.refused()))
    for label, spec in _MALFORMED:
        with V() as hx:
            hx.comment("e1", "first")
            hx.comment("e2", "second")
            hx.set(errors={"comment": spec})
            hx.clear()
            res = hx.run("flush")
            e1 = hx.job("e1") or {}
            _check(f"{_T} AC7: {label} (not exactly formed) is outcome-unknown: queued with attempts 1, flush stops",
                   e1.get("state") == "queued" and e1.get("attempts") == 1 and hx.count("comment") == 1 and res.rc == 0, res.show() + repr(e1)[:300])
    # v2.2 keeps its table
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.comment("e1", "first")
        hx.comment("e2", "second")
        hx.set(errors={"comment": _j(409, "connection_unavailable")})
        hx.run("flush")
        _check(f"{_T} AC7: v2.2 unchanged - connection_unavailable leaves the job uncertain, flush stopped", (hx.job("e1") or {}).get("state") == "uncertain" and hx.count("comment") == 1, "")
        hx.set(errors={"comment": _j(409, "receipt_collision")})
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.comment("e1", "first")
        hx.set(errors={"comment": _j(409, "receipt_collision")})
        hx.run("flush")
        _check(f"{_T} AC7: v2.2 unchanged - receipt_collision is a plain rejection", (hx.job("e1") or {}).get("state") == "refused", "")


# ---------------------------------------------------------------------------
# AC8 sequence cursor
# ---------------------------------------------------------------------------

def item(seq, aid=None, **over) -> dict:
    a = copy.deepcopy(fx("list_asks")["response"]["asks"][0])
    a.update(ask_id=aid or f"ask-{seq}", seq=seq, task="project")
    a.update(over)
    return a


def page(seq, asks) -> dict:
    return {"task": "project", "seq": seq, "asks": asks}


@safe
def test_v23_ac8_seq_cursor() -> None:
    print(f"{_T} AC8 sequence cursor")
    with V() as hx:
        hx.set(answers=[item(1)])
        res = hx.run("poll")
        out = res.json() or {}
        _check(f"{_T} AC8: first poll sends since 0 and counts the answer", res.rc == 0 and hx.bodies("list_asks")[0].get("since") == 0 and out.get("newAnswers") == 1, res.show())
        _check(f"{_T} AC8: a valid page stores {{seq}} for the task and nothing else", ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 1}, repr((hx.state() or {}).get("cursors")))
        hx.set(answers=[item(1), item(3)])
        res = hx.run("poll")
        _check(f"{_T} AC8: the next poll sends exactly the stored seq (no overlap) and counts only the new answer",
               hx.bodies("list_asks")[1].get("since") == 1 and (res.json() or {}).get("newAnswers") == 1 and ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 3}, res.show())
        res = hx.run("poll")
        _check(f"{_T} AC8: an empty page keeps the cursor at 3 and sends since 3",
               hx.bodies("list_asks")[2].get("since") == 3 and (res.json() or {}).get("newAnswers") == 0 and ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 3}, res.show())
    bad = [("an ask seq equal to since", page(6, [item(5, "x1")])), ("an ask seq below since", page(6, [item(4, "x2")])),
           ("a page seq above the last ask's", page(8, [item(6, "x3")])), ("a page seq below the last ask's", page(5, [item(6, "x4")])),
           ("equal ask seqs", page(7, [item(7, "x5"), item(7, "x6")])), ("decreasing ask seqs", page(7, [item(8, "x7"), item(7, "x8")])),
           ("an empty page with seq above since", page(6, [])), ("an empty page with seq below since", page(4, [])),
           ("a now key", {**page(6, [item(6, "x9")]), "now": _T1}), ("an ask without seq", page(6, [{k: v for k, v in item(6, "xa").items() if k != "seq"}])),
           ("an ask seq as a string", page(6, [item("6", "xb")])), ("a fractional ask seq", page(6, [item(6.5, "xc")])),
           ("an extra page key", {**page(6, [item(6, "xd")]), "extra": 1}), ("a page without seq", {"task": "project", "asks": [item(6, "xe")]})]
    with V() as hx:
        hx.set(answers=[item(5, "a5")])
        hx.run("poll")
        for label, pg in bad:
            snap = json.dumps(_cur(hx), sort_keys=True)
            hx.set(listRaw=pg)
            res = hx.run("poll")
            _check(f"{_T} AC8: {label} -> exit 1, cursor and answers unchanged", res.rc == 1 and json.dumps(_cur(hx), sort_keys=True) == snap, res.show())
        hx.set(listRaw=page(7, [item(6, "ok6"), item(7, "ok7")]))
        res = hx.run("poll")
        _check(f"{_T} AC8: control - a valid page (asks 6 and 7, page seq 7) is accepted: cursor {{seq: 7}}, 2 new answers",
               res.rc == 0 and ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 7} and (res.json() or {}).get("newAnswers") == 2, res.show())
        hx.set(listRaw=page(7, []))
        res = hx.run("poll")
        _check(f"{_T} AC8: control - an empty page whose seq equals since is accepted", res.rc == 0, res.show())
    # switching revisions
    v22_page = copy.deepcopy(_fixture("list_asks")["response"])
    ask22 = v22_page["asks"][0]
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.set(listRaw=v22_page)
        res = hx.run("poll")
        _check(f"{_T} AC8: under v2.2 a poll still stores {{now}}", (res.json() or {}).get("newAnswers") == 1 and ((hx.state() or {}).get("cursors") or {}).get("project") == {"now": _T1}, res.show())
        hx.set(revision=R25, listRaw=page(1, [item(1, ask22["ask_id"])]))
        res = hx.run("poll")
        since = hx.bodies("list_asks")[-1].get("since")
        _check(f"{_T} AC8: a stored v2.2 {{now}} cursor is not used on v2.3: the first v2.3 poll sends since 0",
               since == 0 and res.rc == 0, res.show() + repr(since))
        _check(f"{_T} AC8: dedupe absorbs the repeat: no answer counted twice, no conflict", (res.json() or {}).get("newAnswers") == 0 and len((hx.state() or {}).get("answers") or []) == 1
               and not (hx.state() or {}).get("conflicts"), repr((hx.state() or {}).get("answers"))[:300])
        _check(f"{_T} AC8: the cursor is now {{seq: 1}}", ((hx.state() or {}).get("cursors") or {}).get("project") == {"seq": 1}, "")
        hx.set(revision="vibe-agent-exchange-v2.2", listRaw=v22_page)
        res = hx.run("poll")
        since = hx.bodies("list_asks")[-1].get("since")
        _check(f"{_T} AC8: back on v2.2 the stored {{seq}} is ignored: since 0, and the answer is not counted again", since == 0 and (res.json() or {}).get("newAnswers") == 0, res.show() + repr(since))
        hx.set(revision=R25, listRaw=page(1, [item(1, ask22["ask_id"])]))
        res = hx.run("poll")
        _check(f"{_T} AC8: and the v2.2 {{now}} written meanwhile is again ignored on v2.3 (since 0)", hx.bodies("list_asks")[-1].get("since") == 0 and res.rc == 0, res.show())


# ---------------------------------------------------------------------------
# AC9 offer schema
# ---------------------------------------------------------------------------

@safe
def test_v23_ac9_offer_schema() -> None:
    print(f"{_T} AC9 offer schema")
    ok = [("fixture offer", {}, None), ("empty action", {"offer": {"action": ""}}, None),
          ("fractional allowance.windows 0.5", {"offer": {"allowance": {"windows": 0.5}}}, {"windows": 0.5}),
          ("fractional allowance.tokens", {"offer": {"allowance": {"tokens": 1000.5}}}, {"tokens": 1000.5}),
          ("zero allowance.tokens", {"offer": {"allowance": {"tokens": 0}}}, {"tokens": 0}),
          ("allowance null", {"offer": {"allowance": None, "defaults_allowed": False}}, None),
          ("latest_start", {"offer": {"latest_start": 1761899700000}}, None),
          ("spent.cache_read large", {"offer": {"spent": {"windows": 2, "tokens": 5, "cache_read": 900000}}}, None)]
    for rev in (R23, R25):
        for label, ctl, allowance in ok:
            with V(rev) as hx:
                hx.ctl.update(ctl)
                hx.save_routes()
                res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
                claim = hx.claimed() or {}
                good = res.rc == 0 and claim.get("task") == "leaf-b"
                if allowance is not None:
                    good = good and claim.get("allowance") == allowance
                _check(f"{_T} AC9 [{rev[-4:]}]: {label} is accepted (exit 0, claim stored)", good, res.show())
    with V(R25) as hx:
        hx.set(offer={"latest_start": 1761899700000})
        hx.run("next-task", "--agent", "claude", "--session", "session-a")
        _check(f"{_T} AC9: latest_start is kept on the claim", (hx.claimed() or {}).get("latest_start") == 1761899700000, repr(hx.claimed())[:300])
    bad = [("missing action", {"offerDrop": ["action"]}), ("action not a string", {"offer": {"action": 5}}), ("action null", {"offer": {"action": None}}),
           ("missing spent.cache_read", {"offerDrop": ["spent.cache_read"]}), ("spent.cache_read fractional", {"offer": {"spent": {"windows": 0, "tokens": 0, "cache_read": 1.5}}}),
           ("spent.cache_read negative", {"offer": {"spent": {"windows": 0, "tokens": 0, "cache_read": -1}}}),
           ("spent.windows fractional", {"offer": {"spent": {"windows": 1.5, "tokens": 0, "cache_read": 0}}}),
           ("spent.tokens fractional", {"offer": {"spent": {"windows": 0, "tokens": 1.5, "cache_read": 0}}}),
           ("negative allowance", {"offer": {"allowance": {"tokens": -1}}}), ("allowance as a string", {"offer": {"allowance": {"windows": "1"}}}),
           ("latest_start as a string", {"offer": {"latest_start": "soon"}}), ("unknown extra key", {"offer": {"surprise": 1}})]
    for rev in (R23, R25):
        for label, ctl in bad:
            with V(rev) as hx:
                hx.ctl.update(ctl)
                hx.save_routes()
                res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
                _check(f"{_T} AC9 [{rev[-4:]}]: {label} is malformed (exit 1, no claim)", res.rc == 1 and hx.claimed() is None, res.show())
    r22 = "vibe-agent-exchange-v2.2"
    with V(r22) as hx:
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
        _check(f"{_T} AC9: control - the unchanged v2.2 offer is accepted", res.rc == 0 and hx.claimed() is not None, res.show())
    for label, over in (("an action key", {"action": "x"}), ("spent.cache_read", {"spent": {"windows": 0, "tokens": 0, "cache_read": 0}})):
        with V(r22) as hx:
            hx.set(offer=over)
            res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
            _check(f"{_T} AC9: the v2.2 offer schema is unchanged - {label} is still malformed", res.rc == 1 and hx.claimed() is None, res.show())


# ---------------------------------------------------------------------------
# AC10 next-task --task
# ---------------------------------------------------------------------------

REASONS = ["unsafe_id", "not_assigned", "closed", "provisional", "on_hold", "blocked", "open_children", "waiting_on_ask", "over_budget", "leased"]


@safe
def test_v23_ac10_next_task_named() -> None:
    print(f"{_T} AC10 next-task --task")
    args = ["next-task", "--agent", "claude", "--session", "session-a", "--task", "project"]
    for reason in REASONS:
        with V() as hx:
            hx.set(refuse=reason)
            res = hx.run(*args)
            body = (hx.bodies("next_task") or [{}])[0]
            _check(f"{_T} AC10: refusal {reason}: exit 0 and the exact JSON",
                   res.rc == 0 and res.out == json.dumps({"bound": True, "channel": "taskandi-http", "task": None, "reason": reason}, separators=(",", ":")) + "\n", res.show())
            _check(f"{_T} AC10: refusal {reason}: the request carried task, no claim stored, no body file",
                   body.get("task") == "project" and hx.claimed() is None and not (hx.vibe / "taskandi-body.txt").exists(), repr(body))
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            snap = json.dumps(hx.claimed(), sort_keys=True)
            core = json.dumps(hx.core(), sort_keys=True)
            hx.set(refuse=reason)
            res = hx.run(*args)
            _check(f"{_T} AC10: refusal {reason} with a claim on another task: state.claimed is byte-identical",
                   res.rc == 0 and json.dumps(hx.claimed(), sort_keys=True) == snap and (res.json() or {}).get("reason") == reason, res.show())
    with V() as hx:
        res = hx.run(*args)
        claim = hx.claimed() or {}
        body = (hx.bodies("next_task") or [{}])[0]
        _check(f"{_T} AC10: control - a claim stores the claim for the named task, with claim.contract",
               res.rc == 0 and claim.get("task") == "project" and claim.get("contract") == R25 and body.get("task") == "project" and (res.json() or {}).get("task", {}).get("task") == "project", res.show())
        _check(f"{_T} AC10: the claim writes the body file", (hx.vibe / "taskandi-body.txt").exists(), "")
        hx.set(refuse="closed")
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a", "--task", "project")
        _check(f"{_T} AC10: REF equal to the claimed task is allowed", res.rc == 0 and (res.json() or {}).get("reason") == "closed", res.show())
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        hx.set(refuse="leased")
        hx.clear()
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a", "--task", "leaf-b")
        _check(f"{_T} AC10: REF equal to the claimed task (not the effective one) is allowed", res.rc == 0 and hx.count("next_task") == 1 and (res.json() or {}).get("reason") == "leased", res.show())
        hx.clear()
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a", "--task", "somewhere-else")
        _check(f"{_T} AC10: REF that is neither the effective nor the claimed task: usage error, exit 1, zero requests",
               res.rc == 1 and res.out == "" and hx.reqs() == [] and res.err.strip() != "", res.show())
    with V() as hx:
        wrong = {"offerTask": "other-task"}
        hx.set(**wrong)
        res = hx.run(*args)
        rel = hx.bodies("release")
        _check(f"{_T} AC10: a claim response for another task: exit 1, no claim, exactly one release for the returned task",
               res.rc == 1 and hx.claimed() is None and len(rel) == 1 and rel[0].get("task") == "other-task" and rel[0].get("reason") == "vibe asked for another task"
               and rel[0].get("session") == "session-a" and hx.actions() == ["capabilities", "next_task", "release"], res.show() + repr(hx.actions()))
    pair = [("a reason without --task", ["next-task", "--agent", "claude", "--session", "session-a"], {"nextRaw": {"task": None, "reason": "closed"}}),
            ("--task with {task: null} and no reason", args, {"nextRaw": {"task": None}}),
            ("--task with an unknown reason", args, {"nextRaw": {"task": None, "reason": "bogus"}}),
            ("--task with a non-string reason", args, {"nextRaw": {"task": None, "reason": 7}})]
    for label, a, ctl in pair:
        with V() as hx:
            hx.set(**ctl)
            res = hx.run(*a)
            _check(f"{_T} AC10: pairing rule - {label} is malformed (exit 1, no claim)", res.rc == 1 and hx.claimed() is None, res.show())
    with V() as hx:
        hx.set(nextRaw={"task": None})
        res = hx.run("next-task", "--agent", "claude", "--session", "session-a")
        _check(f"{_T} AC10: control - {{task: null}} without --task and without reason is valid", res.rc == 0 and (res.json() or {}).get("task", 0) is None, res.show())
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.claim("leaf-b", "session-a")
        snap = json.dumps(hx.claimed(), sort_keys=True)
        hx.clear()
        res = hx.run(*args)
        _check(f"{_T} AC10: a v2.2 server: contract_v2_2 output, exit 0, no next_task request, claim untouched",
               res.rc == 0 and res.out == '{"bound":true,"channel":"taskandi-http","task":null,"reason":"contract_v2_2"}\n' and hx.actions() == ["capabilities"]
               and json.dumps(hx.claimed(), sort_keys=True) == snap, res.show() + repr(hx.actions()))


# ---------------------------------------------------------------------------
# AC11 record_usage at
# ---------------------------------------------------------------------------

def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def crec(mid: str, model: str, ms, i=1, o=1, cr=0, cw=0) -> str:
    rec = {"type": "assistant", "message": {"id": mid, "model": model, "role": "assistant",
                                            "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}}}
    if ms is not None:
        rec["timestamp"] = _ts(ms)
    return json.dumps(rec)


def usage_payload(**over) -> dict:
    p = payload_of("record_usage")
    p.pop("at", None)
    p.update(over)
    return p


@safe
def test_v23_ac11_at() -> None:
    print(f"{_T} AC11 record_usage at")
    t0 = _T1 - _DAY
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        tr = hx.base / "claude.jsonl"
        tr.write_text("\n".join([crec("m1", "model-a", t0 + 3000), crec("m2", "model-a", t0 + 1000), crec("m3", "model-b", None),
                                 crec("m4", "model-c", t0 + 500), crec("m5", "model-c", None)]) + "\n")
        res = hx.run("usage", "--transcript", str(tr), "--session", "sess-1", "--account", "acct", "--cost-estimate", "0")
        rows = {j["payload"]["model"]: j["payload"] for j in hx.jobs() if j.get("kind") == "record_usage"}
        _check(f"{_T} AC11: import enqueues one row per model", res.rc == 0 and set(rows) == {"model-a", "model-b", "model-c"}, res.show() + repr(list(rows)))
        _check(f"{_T} AC11: row `at` is the newest covered timestamp as integer ms (model-a: the later of two, out of order)", rows.get("model-a", {}).get("at") == t0 + 3000, repr(rows.get("model-a")))
        _check(f"{_T} AC11: a row whose messages have no timestamp has no `at` (no clock fallback)", "at" not in rows.get("model-b", {"at": 1}), repr(rows.get("model-b")))
        _check(f"{_T} AC11: only covered messages that have a timestamp count (model-c: m4's)", rows.get("model-c", {}).get("at") == t0 + 500, repr(rows.get("model-c")))
        codex = hx.base / "rollout.jsonl"
        codex.write_text("\n".join(json.dumps(r) for r in [
            {"type": "turn_context", "payload": {"model": "gpt-test"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 10, "cache_write_input_tokens": 0, "output_tokens": 20}}}}]) + "\n")
        res = hx.run("usage", "--transcript", str(codex), "--session", "sess-2", "--account", "acct", "--cost-estimate", "0")
        gp = [j for j in hx.jobs() if j.get("kind") == "record_usage" and j["payload"].get("model") == "gpt-test"]
        _check(f"{_T} AC11: a Codex delta without an event time has no `at`", res.rc == 0 and len(gp) == 1 and "at" not in gp[0]["payload"], res.show() + repr(gp)[:300])
        res = hx.run("flush")
        sent = {b["model"]: b for b in hx.bodies("record_usage")}
        _check(f"{_T} AC11: control - the imported rows are delivered; `at` rides on the wire only where the row has it",
               sent.get("model-a", {}).get("at") == t0 + 3000 and "at" not in sent.get("model-b", {"at": 1}) and all(UUID4.match(b.get("request_id", "")) for b in sent.values()), res.show() + repr(sent)[:300])
    with V() as hx:
        hx.claim("leaf-b", "session-a")
        r1 = hx.enq("record_usage", "u1", usage_payload(at=t0))
        n = len(hx.jobs())
        r2 = hx.enq("record_usage", "u1", usage_payload(at=t0))
        r3 = hx.enq("record_usage", "u1", usage_payload(at=t0 + 1))
        r4 = hx.enq("record_usage", "u1", usage_payload())
        _check(f"{_T} AC11: re-enqueue with the same `at` is a dedupe (exit 0, no new job)", r1.rc == 0 and r2.rc == 0 and len(hx.jobs()) == n and "deduplicated" in r2.out, r2.show())
        _check(f"{_T} AC11/AC22: `at` is not identity (Rev 4) - another `at`, or none, deduplicates and the stored payload keeps the first `at`",
               r3.rc == 0 and r4.rc == 0 and len(hx.jobs()) == n and (hx.job("u1") or {}).get("payload", {}).get("at") == t0, r3.show() + r4.show())
        r5 = hx.enq("record_usage", "u1", usage_payload(at=t0, input=999))
        _check(f"{_T} AC11/AC22: but another figure under the same key is still a KEY_CONFLICT", r5.rc != 0 and "KEY_CONFLICT" in r5.err + r5.out, r5.show())
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.claim("leaf-b", "session-a")
        hx.enq("record_usage", "u1", usage_payload(at=t0))
        res = hx.run("flush")
        b = (hx.bodies("record_usage") or [{}])[0]
        _check(f"{_T} AC11: `at` is never sent to a v2.2 server (the job is accepted and delivered)", res.rc == 0 and "at" not in b and (hx.job("u1") or {}).get("state") == "done", res.show() + repr(b))
    cases = [("a recent at", _T1 - 5000, _T1 - 5000, False), ("28 days old", _T1 - 28 * _DAY, _T1 - 28 * _DAY, False),
             ("exactly 29 days old", _T1 - 29 * _DAY, _T1 - 29 * _DAY, False), ("exactly 30 s ahead", _T1 + 30000, _T1 + 30000, False),
             ("29 days and 1 ms old", _T1 - 29 * _DAY - 1, None, True), ("31 days old", _T1 - 31 * _DAY, None, True),
             ("5 minutes ahead", _T1 + 300000, _T1 + 30000, False), ("30 s and 1 ms ahead", _T1 + 30001, _T1 + 30000, False)]
    for label, at, want, old in cases:
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.enq("record_usage", "u1", usage_payload(at=at))
            hx.set(dropAfterApply={"record_usage": 1})
            res = hx.run("flush")
            b1 = (hx.bodies("record_usage") or [{}])[0]
            j = hx.job("u1") or {}
            frozen = json.loads(j.get("sentBody") or "{}")
            ok = (b1.get("at") == want) if want is not None else ("at" not in b1)
            _check(f"{_T} AC11: {label}: the first dispatch sends at={want!r}", ok and frozen.get("at") == b1.get("at"), repr(b1) + res.show())
            _check(f"{_T} AC11: {label}: stderr notice for an old `at`" if old else f"{_T} AC11: {label}: no notice",
                   (re.search(r"usage row u1: at older than \d+ days, sent without it", res.err) is not None) == old, res.err)
            hx.set(dropAfterApply=None)
            hx.run("flush", now=_T1 + 7200_000)
            raws = hx.raws("record_usage")
            _check(f"{_T} AC11: {label}: frozen thereafter - the resend two hours later is byte-identical, one row", len(raws) == 2 and raws[1] == raws[0]
                   and len(hx.applied("record_usage")) == 1 and (hx.job("u1") or {}).get("state") == "done", repr(raws)[:300])


# ---------------------------------------------------------------------------
# AC12 decide + M2
# ---------------------------------------------------------------------------

def _usage_job(hx: V, key="pu") -> None:
    hx.enq("record_usage", key, {"model": "m", "input": 10, "output": 20, "cache_read": 500, "cache_write": 5, "cost_estimate": 0, "account": "acct"})


def _budget(hx: V, *flags: str):
    res = hx.run("decide", "--remaining-minutes", "10", *flags)
    return res, ((res.json() or {}).get("budget") or {})


def _open_ask(hx: V, key="a1") -> str:
    hx.enq("ask", key, ask_payload())
    hx.run("flush")
    return hx.applied("ask")[-1]["response"]["ask_id"]


@safe
def test_v23_ac12_decide() -> None:
    print(f"{_T} AC12 decide")
    for rev, want in ((R25, 35), (R23, 35), ("vibe-agent-exchange-v2.2", 535)):
        with V(rev) as hx:
            hx.claim("leaf-b", "session-a", offer={"allowance": {"tokens": 1000}, "spent": {"windows": 0, "tokens": 0} if rev == "vibe-agent-exchange-v2.2" else {"windows": 0, "tokens": 0, "cache_read": 0}})
            _usage_job(hx)
            res, b = _budget(hx)
            _check(f"{_T} AC12 [{rev[-4:]}]: input 10 + output 20 + cache_read 500 + cache_write 5 -> pending_tokens {want}",
                   res.rc == 0 and b.get("pending_tokens") == want and abs(b.get("ratio", -1) - want / 1000) < 1e-9, res.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", offer={"allowance": {"tokens": 1000}})
        _usage_job(hx)
        hx.set(revision="vibe-agent-exchange-v2.2")
        hx.clear()
        res, b = _budget(hx)
        _check(f"{_T} AC12 M2: decide reads claim.contract - a service that now speaks v2.2 changes nothing (35, nothing sent)", b.get("pending_tokens") == 35 and hx.actions() == [], res.show())
        _edit_state(hx, lambda s: (s["claimed"].pop("contract", None), s["claimed"].pop("spentContract", None)))
        res, b = _budget(hx)
        _check(f"{_T} AC12 M2: without claim.contract it falls back to state.lastContract (v2.5 -> 35)", b.get("pending_tokens") == 35, res.show())
        _edit_state(hx, lambda s: s.update(lastContract=R22))
        res, b = _budget(hx)
        _check(f"{_T} AC12 M2: lastContract v2.2 -> 535", b.get("pending_tokens") == 535, res.show())
        _edit_state(hx, lambda s: s.pop("lastContract", None))
        res, b = _budget(hx)
        _check(f"{_T} AC12 M2: with neither it is v2.2 -> 535", b.get("pending_tokens") == 535, res.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", offer={"allowance": {"windows": 0.5}})
        res, b = _budget(hx, "--windows-used", "1")
        _check(f"{_T} AC12: allowance.windows 0.5 with --windows-used 1 -> stop / cap", res.rc == 0 and (b.get("action"), b.get("why")) == ("stop", "cap"), res.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", offer={"allowance": {"windows": 0.5}})
        res, b = _budget(hx, "--windows-used", "0")
        _check(f"{_T} AC12: control - 0 of 0.5 windows used -> continue / under-threshold", res.rc == 0 and (b.get("action"), b.get("why")) == ("continue", "under-threshold"), res.show())
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", offer={"allowance": {"tokens": 1000.5}, "spent": {"windows": 0, "tokens": 900, "cache_read": 0}})
        res, b = _budget(hx)
        _check(f"{_T} AC12: a fractional token allowance works in the ratio (900/1000.5 -> ask / most-spent)",
               res.rc == 0 and abs(b.get("ratio", -1) - 900 / 1000.5) < 1e-9 and (b.get("action"), b.get("why")) == ("ask", "most-spent"), res.show())
    # deferred and latest_start from the server
    lease = {"until": H + 10 ** 8, "session": "session-a"}
    offer = {"hardDeadline": H, "defaults_allowed": True, "allowance": {"tokens": 10 ** 7}, "lease": lease}
    for label, status, want in (("deferred, unseen", {"seen_at": None, "deferred": True, "answered": False}, ("proceed", "default-allowed")),
                                ("control: not deferred, unseen", {"seen_at": None, "deferred": False, "answered": False}, ("wait", "unseen"))):
        with V(R25) as hx:
            hx.claim("leaf-b", "session-a", offer=offer, offerDrop=["latest_start"])
            aid = _open_ask(hx)
            hx.set(statusRaw={"task": "leaf-b", "asks": [{"ask_id": aid, **status}]})
            res = hx.run("decide", now=LS)
            a = next(iter((res.json() or {}).get("asks") or [{}]))
            _check(f"{_T} AC12: {label}, every other condition met -> {want[0]} / {want[1]}", res.rc == 0 and (a.get("action"), a.get("why")) == want, res.show())
    for label, ls, want in (("a server latest_start in the past", LS - 1000, ("proceed", "default-allowed")),
                            ("control: latest_start in the future", LS + 3600_000, ("wait", "before-latest-start"))):
        with V(R25) as hx:
            hx.claim("leaf-b", "session-a", offer={"defaults_allowed": True, "allowance": {"tokens": 10 ** 7}, "latest_start": ls, "lease": lease}, offerDrop=["hardDeadline"])
            _check(f"{_T} AC12: the claim keeps the server's latest_start", (hx.claimed() or {}).get("latest_start") == ls, repr(hx.claimed())[:300])
            aid = _open_ask(hx)
            hx.set(statusRaw={"task": "leaf-b", "asks": [{"ask_id": aid, "seen_at": _T1 - 1000, "deferred": False, "answered": False}]})
            res = hx.run("decide", now=LS)
            a = next(iter((res.json() or {}).get("asks") or [{}]))
            _check(f"{_T} AC12: {label} -> {want[0]} / {want[1]}", res.rc == 0 and (a.get("action"), a.get("why")) == want, res.show())
    # M2: renewal across revisions replaces spent; within a revision it keeps the per-dimension maximum
    with V("vibe-agent-exchange-v2.2") as hx:
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 3, "tokens": 1000}})
        hx.set(revision=R25)
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 1, "tokens": 200, "cache_read": 800}})
        s = (hx.claimed() or {}).get("spent")
        _check(f"{_T} AC12 M2: a renewal under another revision REPLACES spent (v2.2 tokens count cache_read, v2.5 do not)",
               s == {"windows": 1, "tokens": 200, "cache_read": 800} and (hx.claimed() or {}).get("contract") == R25, repr(hx.claimed())[:300])
    with V(R25) as hx:
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 3, "tokens": 1000, "cache_read": 5}})
        hx.claim("leaf-b", "session-a", offer={"spent": {"windows": 1, "tokens": 200, "cache_read": 9}})
        s = (hx.claimed() or {}).get("spent") or {}
        _check(f"{_T} AC12 M2: control - a renewal under the same revision keeps the per-dimension maximum", (s.get("windows"), s.get("tokens")) == (3, 1000), repr(s))


# ---------------------------------------------------------------------------
# AC13 server limits
# ---------------------------------------------------------------------------

@safe
def test_v23_ac13_server_limits() -> None:
    print(f"{_T} AC13 limits from the server")
    ask = ask_payload()
    cases = [("comment 100 vs 500 chars", "comment", {"text": "c" * 500}, {"comment": 100}, True),
             ("comment 9000 vs 500 chars (looser)", "comment", {"text": "c" * 500}, {"comment": 9000}, False),
             ("comment 100 vs 100 emoji (code points, not UTF-16 units)", "comment", {"text": "\U0001F600" * 100}, {"comment": 100}, False),
             ("comment 100 vs 101 emoji", "comment", {"text": "\U0001F600" * 101}, {"comment": 100}, True),
             ("question 10", "ask", ask, {"question": 10}, True), ("default 5", "ask", ask, {"default": 5}, True),
             ("options 1 (two given)", "ask", ask, {"options": 1}, True), ("option 5", "ask", ask, {"option": 5}, True),
             ("ask_post 50", "ask", ask, {"ask_post": 50}, True), ("ask loose limits", "ask", ask, {"question": 9000, "ask_post": 9000}, False),
             ("request_bytes 120", "comment", {"text": "short"}, {"request_bytes": 120}, True),
             ("request_bytes 65536", "comment", {"text": "short"}, {"request_bytes": 65536}, False)]
    for rev in (R25, R23):
        for label, kind, payload, limits, refused in cases:
            if rev == R23 and not label.startswith(("comment 100 vs 500", "ask_post", "request_bytes 120")):
                continue
            with V(rev) as hx:
                hx.claim("project", "session-a")
                hx.set(limits=limits)
                hx.enq(kind, "j1", payload)
                hx.comment("j2", "tail")
                hx.clear()
                res = hx.run("flush")
                j1 = hx.job("j1") or {}
                if refused:
                    sent_long = [b for b in hx.bodies(kind) if b.get("text", b.get("question")) == payload.get("text", payload.get("question"))]
                    _check(f"{_T} AC13 [{rev[-4:]}]: {label} -> refused (over_server_limit) with no write request for it",
                           j1.get("state") == "refused" and hx.refused().get("j1") == "over_server_limit" and not sent_long and res.rc == 0, res.show() + repr(j1)[:200])
                    if "request_bytes" not in limits:
                        _check(f"{_T} AC13 [{rev[-4:]}]: {label}: the next job still goes out (flush continues)", (hx.job("j2") or {}).get("state") == "done", res.show())
                else:
                    _check(f"{_T} AC13 [{rev[-4:]}]: {label} -> delivered as before", j1.get("state") == "done" and res.rc == 0, res.show() + repr(j1)[:200])
    for call, flag, long in (("release", "--reason", "r" * 50), ("complete", "--summary", "s" * 50)):
        key = "reason" if call == "release" else "summary"
        with V() as hx:
            hx.claim("leaf-b", "session-a")
            hx.set(limits={key: 10})
            hx.clear()
            res = hx.run(call, "--task", "leaf-b", flag, long)
            _check(f"{_T} AC13: {call} over the server's {key} limit: exit 1, nothing sent, no pending record, claim kept",
                   res.rc == 1 and hx.count(call) == 0 and not (hx.state() or {}).get("pendingDirect") and hx.claimed() is not None, res.show())
            res = hx.run(call, "--task", "leaf-b", flag, "short")
            _check(f"{_T} AC13: control - a text within the limit goes out", res.rc == 0 and hx.count(call) == 1, res.show())


# ---------------------------------------------------------------------------
# AC14 harness
# ---------------------------------------------------------------------------

@safe
def test_v23_ac14_harness() -> None:
    print(f"{_T} AC14 harness")
    text = (_REPO / "devcontainer" / "taskandi-harness.md").read_text()
    step2 = text.split("2. **Pick work.**", 1)[1].split("3. **Work.**", 1)[0]
    _check(f"{_T} AC14: step 2 has the linked-task command with --task <effective task>",
           "taskandi-client next-task --agent <agent> --session <session> --task <effective task>" in step2, "")
    _check(f"{_T} AC14: control - step 2 still has A-mode's command without --task",
           re.search(r"^taskandi-client next-task --agent <agent> --session <session>$", step2, re.M) is not None, "")
    rows = [l for l in step2.splitlines() if l.startswith("|")]
    for reason in REASONS + ["contract_v2_2"]:
        hit = [r for r in rows if f"`{reason}`" in r]
        _check(f"{_T} AC14: the table has a row for {reason}", len(hit) == 1, repr(hit))
    for reason in REASONS:
        row = next((r for r in rows if f"`{reason}`" in r), "")
        _check(f"{_T} AC14: the {reason} row never says to work the task without a claim",
               row != "" and not re.search(r"without a claim|no-claim|no claim|work it without", row, re.I) and re.search(r"stop|do not work", row), row)
    with tempfile.TemporaryDirectory(prefix="v23-argv-") as td:
        subprocess.run(["git", "init", "-q", td], check=True, input="", capture_output=True, text=True)
        res = subprocess.run(["node", str(_CLIENT), "--check-argv", "next-task", "--agent", "claude", "--session", "s1", "--task", "leaf-b"],
                             cwd=td, input="", capture_output=True, text=True, timeout=60)
        _check(f"{_T} AC14: --check-argv accepts the new command line", res.returncode == 0 and res.stdout.strip() == '{"ok":true}', res.stdout + res.stderr)
        res = subprocess.run(["node", str(_CLIENT), "--check-argv", "next-task", "--agent", "claude", "--session", "s1", "--task"],
                             cwd=td, input="", capture_output=True, text=True, timeout=60)
        _check(f"{_T} AC14: control - --task without a value is refused by --check-argv", res.returncode != 0, res.stdout + res.stderr)


# ---------------------------------------------------------------------------
# AC16 fixtures, docs, M3
# ---------------------------------------------------------------------------

@safe
def test_v23_ac16_fixtures_docs_limits() -> None:
    print(f"{_T} AC16 fixtures, docs, limits")
    present = [n for n in NAMES23 if (_FIX23 / f"{n}.json").exists()]
    _check(f"{_T} AC16: the thirteen fixtures are in smoke/fixtures/taskandi-v23/", present == NAMES23, repr(sorted(set(NAMES23) - set(present))))
    prov = _FIX23 / "PROVENANCE.md"
    ptext = prov.read_text() if prov.exists() else ""
    _check(f"{_T} AC16: PROVENANCE.md exists and names the date and the README sections", bool(ptext) and "2026-10-31" in ptext and "v2.3 changes" in ptext and "Decided" in ptext, "")
    for n in NAMES23:
        f = _FIX23 / f"{n}.json"
        if not f.exists():
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        _check(f"{_T} AC16: {n}.json sha256 matches PROVENANCE.md", h in ptext, h)
        # No live-brain2 comparison: Task&I recopies its fixtures as its contract
        # moves on, and the sha256 pin above already fixes these bytes.
        _check(f"{_T} AC16: {n}.json has the family contract string", json.loads(f.read_text()).get("contract") == R25, "")
    docs = (_REPO / "docs" / "taskandi-client.md").read_text()
    sect = docs.split("v2.3", 1)[1] if "v2.3" in docs else ""
    for word in ("negotiat", "request_id", "sentBody", "seq", "next-task --task", "`at`", "limits"):
        _check(f"{_T} AC16: docs/taskandi-client.md has a v2.3 section covering {word!r}", word.lower() in sect.lower(), "")
    cl = (_REPO / "CHANGELOG.md").read_text()
    _check(f"{_T} AC16: CHANGELOG.md has a task_066 / v2.3 entry near the top", "v2.3" in cl[:6000] and "066" in cl[:6000], "")
    mt = (_REPO / "MANUAL-TESTS.md").read_text()
    for n in (69, 70):
        m = re.search(rf"### Test {n}:.*?(?=\n### Test \d+:|\Z)", mt, re.S)
        _check(f"{_T} AC16: MANUAL-TESTS Test {n} notes v2.3", m is not None and "v2.3" in m.group(0), "")
    # M3: every client limit constant is <= the fixture's limit
    with V() as hx:
        out = hx.lib("out.l = C.HTTP_LIMITS;")
    lim = fx("capabilities")["response"]["limits"]
    mapping = {"id": "id", "question": "question", "default": "default", "options": "options", "option": "option", "post": "ask_post",
               "comment": "comment", "summary": "summary", "reason": "reason", "body": "request_bytes"}
    mine = out.get("l") or {}
    for ck, fk in mapping.items():
        _check(f"{_T} AC16 M3: client limit {ck} ({mine.get(ck)}) <= fixture limits.{fk} ({lim.get(fk)})",
               isinstance(mine.get(ck), int) and isinstance(lim.get(fk), int) and mine[ck] <= lim[fk], repr(mine))
    with V() as hx:
        st = hx.run("status")
        _check(f"{_T} AC16 M3: status reports lastContract null before any call", (st.json() or {}).get("lastContract") is None, st.show())
        hx.run("next-task", "--agent", "claude", "--session", "session-a")
        st = hx.run("status")
        _check(f"{_T} AC16 M3: status reports lastContract after a call", (st.json() or {}).get("lastContract") == R25, st.show())


def _run_all() -> None:
    for fn in [test_v23_ac7_error_table, test_v23_ac8_seq_cursor, test_v23_ac9_offer_schema, test_v23_ac10_next_task_named, test_v23_ac11_at,
               test_v23_ac12_decide, test_v23_ac13_server_limits, test_v23_ac14_harness, test_v23_ac16_fixtures_docs_limits]:
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
    print("PASS: Task&I v2.3 checks, part 2")
