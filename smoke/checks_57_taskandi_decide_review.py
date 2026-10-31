#!/usr/bin/env python3
"""Acceptance checks for task_065 cycle 3 (the "Rev 7 addendum", AC32-AC40 of ``.vs/spec.md``).

Tester-owned (cycle 3).  Reuses the loopback harness of ``checks_50`` and the decide driver of ``checks_53``.
Every command runs through ``dc`` (the injected clock ``clock = () => <ms>``) so pruning, tombstone expiry and renewal
times are deterministic.

Run only this module with:
    python3 smoke/checks_57_taskandi_decide_review.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_50_taskandi_http import _CLIENT, _FIX_REPO, _NAMES, _RESULTS, _T1, _Hx, _check
from smoke.checks_53_taskandi_decide import (H, LS, SESSION, TASK, _MA, _body_of, _rec, _ru_payload, _usage_jobs, by_id, claim, dc, decide,
                                             full_state, mkask, nt, owner_item, parse, set_answers, set_status, st)

_T = "[taskandi-review]"
_DAY = 86400_000
_NOW = _T1
_STATE = lambda hx: hx.vibe / "taskandi-outbox" / "state.json"


def _write_state(hx: _Hx, s: dict) -> None:
    _STATE(hx).write_text(json.dumps(s))


def _seed_comment(hx: _Hx) -> dict:
    dc(hx, _NOW, "enqueue", "comment", "--key", "seed", "--task", "project", stdin=json.dumps({"text": "x"}))
    dc(hx, _NOW, "flush")
    return copy.deepcopy(hx.job("seed"))


def _done(seed: dict, key: str, ms: int) -> dict:
    j = copy.deepcopy(seed)
    j.update(key=key, doneAtMs=ms, state="done")
    j["doneAt"] = "2026-01-01T00:00:00Z"
    return j


def _tomb_keys(hx: _Hx) -> dict:
    return {t.get("key"): t for t in (full_state(hx).get("tombstones") or []) if isinstance(t, dict)}


# ---------------------------------------------------------------------------
# AC32 Pruning never breaks deduplication
# ---------------------------------------------------------------------------

def test_rv_ac32_tombstones() -> None:
    print(f"{_T} AC32 tombstones")
    with _Hx() as hx:
        seed = _seed_comment(hx)
        if not (seed and seed.get("state") == "done"):
            _check(f"{_T} AC32 setup: a done seed job", False, repr(seed))
            return
        s = full_state(hx)
        jobs = [_done(seed, f"c{i}", _NOW - 10 * _DAY + i) for i in range(2100)]
        jobs.append(_done(seed, "budget-project", _NOW - 10 * _DAY - 5))   # the oldest of all
        s["jobs"] = jobs
        _write_state(hx, s)
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        keys = {j["key"] for j in hx.jobs()}
        _check(f"{_T} AC32: the triggering write succeeds and the oldest done jobs are pruned", res.rc == 0 and "trigger" in keys and "c0" not in keys, res.show())
        _check(f"{_T} AC32: the newest done jobs survive (control: pruning is bounded)", "c2099" in keys and "c1500" in keys)
        _check(f"{_T} AC32: a job keyed budget-<task> is never pruned, however old", "budget-project" in keys, repr(sorted(k for k in keys if k.startswith("budget"))))
        tk = _tomb_keys(hx)
        t0 = tk.get("c0") or {}
        _check(f"{_T} AC32: a pruned job leaves a tombstone {{key, kind, digest, doneAtMs}}",
               t0.get("kind") == "comment" and t0.get("digest") == seed["digest"] and t0.get("doneAtMs") == _NOW - 10 * _DAY, repr(t0))
        _check(f"{_T} AC32: no tombstone for a job that was kept", "c2099" not in tk and "budget-project" not in tk, repr(sorted(tk)[:3]))
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "c0", "--task", "project", stdin=json.dumps({"text": "x"}))
        out = parse(res) or {}
        _check(f"{_T} AC32: re-enqueueing a pruned key with the same payload is deduplicated (no new job)",
               res.rc == 0 and out.get("deduplicated") is True and out.get("enqueued") is False and hx.job("c0") is None, res.show())
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "c0", "--task", "project", stdin=json.dumps({"text": "DIFFERENT"}))
        _check(f"{_T} AC32: ... and with a different payload it is a KEY_CONFLICT (non-zero exit, nothing queued)",
               res.rc != 0 and "KEY_CONFLICT" in (res.out + res.err) and hx.job("c0") is None, res.show())
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "fresh-never-seen", "--task", "project", stdin=json.dumps({"text": "x"}))
        _check(f"{_T} AC32 control: a key that never existed enqueues normally", res.rc == 0 and (parse(res) or {}).get("enqueued") is True, res.show())

    # record_usage keys of the Codex delta path are covered like any other job
    with _Hx() as hx:
        seed = _seed_comment(hx)
        claim(hx, _NOW)
        dc(hx, _NOW, "enqueue", "record_usage", "--key", "usage-old", stdin=json.dumps(_ru_payload()))
        dc(hx, _NOW, "flush")
        ru = copy.deepcopy(hx.job("usage-old"))
        if not (ru and ru.get("state") == "done" and seed):
            _check(f"{_T} AC32 setup: a done record_usage job", False, repr(ru))
            return
        s = full_state(hx)
        ru["doneAtMs"] = _NOW - 20 * _DAY
        s["jobs"] = [ru] + [_done(seed, f"c{i}", _NOW - 10 * _DAY + i) for i in range(2100)]
        _write_state(hx, s)
        dc(hx, _NOW, "enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        gone = hx.job("usage-old") is None
        res = dc(hx, _NOW, "enqueue", "record_usage", "--key", "usage-old", stdin=json.dumps(_ru_payload()))
        _check(f"{_T} AC32: a pruned record_usage key re-enqueued with the same payload is deduplicated",
               gone and res.rc == 0 and (parse(res) or {}).get("deduplicated") is True, res.show())

    # expiry: tombstones older than 90 days are dropped, younger ones keep deduplicating
    with _Hx() as hx:
        seed = _seed_comment(hx)
        if not seed:
            return
        s = full_state(hx)
        jobs = [_done(seed, f"c{i}", _NOW - 91 * _DAY + i) for i in range(50)]              # oldest; would tombstone, but already expired
        jobs += [_done(seed, f"c{i}", _NOW - 89 * _DAY + i) for i in range(50, 100)]
        jobs += [_done(seed, f"c{i}", _NOW - 1 * _DAY + i) for i in range(100, 2100)]
        s["jobs"] = jobs
        s["tombstones"] = [{"key": "t-fresh", "kind": "comment", "digest": seed["digest"], "doneAtMs": _NOW - 89 * _DAY},
                           {"key": "t-stale", "kind": "comment", "digest": seed["digest"], "doneAtMs": _NOW - 91 * _DAY}]
        _write_state(hx, s)
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        tk = _tomb_keys(hx)
        _check(f"{_T} AC32: tombstone expiry - a 91-day-old tombstone is dropped, an 89-day-old one kept",
               res.rc == 0 and "t-stale" not in tk and "t-fresh" in tk, repr(sorted(tk)[:5]) + res.show())
        _check(f"{_T} AC32: tombstones for the 89-day-old pruned jobs exist; none for the 91-day-old ones",
               "c60" in tk and "c0" not in tk and "c49" not in tk, repr(sorted(tk)[:6]))
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "c60", "--task", "project", stdin=json.dumps({"text": "x"}))
        _check(f"{_T} AC32: a key whose tombstone is 89 days old still deduplicates", (parse(res) or {}).get("deduplicated") is True, res.show())
        res = dc(hx, _NOW, "enqueue", "comment", "--key", "c0", "--task", "project", stdin=json.dumps({"text": "x"}))
        _check(f"{_T} AC32: a key whose tombstone is past 90 days enqueues afresh (the dedup window ended)",
               res.rc == 0 and (parse(res) or {}).get("enqueued") is True, res.show())
        # the injected clock drives expiry: 2 days later the 89-day tombstone is past 90 days
        dc(hx, _NOW + 2 * _DAY, "enqueue", "comment", "--key", "trigger2", "--task", "project", stdin=json.dumps({"text": "t2"}))
        s2 = full_state(hx)
        s2["jobs"] = s2["jobs"] + [_done(seed, f"d{i}", _NOW + i) for i in range(150)]   # force another pass
        _write_state(hx, s2)
        dc(hx, _NOW + 2 * _DAY, "enqueue", "comment", "--key", "trigger3", "--task", "project", stdin=json.dumps({"text": "t3"}))
        _check(f"{_T} AC32: two days later (clock +2d) the 89-day tombstone has expired too", "t-fresh" not in _tomb_keys(hx), repr(sorted(_tomb_keys(hx))[:5]))


# ---------------------------------------------------------------------------
# AC33 The usage ledger stays small
# ---------------------------------------------------------------------------

def _usage(hx: _Hx, tr: Path, session="sess-1"):
    return dc(hx, _NOW, "usage", "--transcript", str(tr), "--session", session, "--account", "acct", "--cost-estimate", "0")


def _tok(j: dict) -> tuple:
    p = j["payload"]
    return (p.get("input"), p.get("output"), p.get("cache_read"), p.get("cache_write"))


def test_rv_ac33_usage_offset() -> None:
    print(f"{_T} AC33 usage ledger")
    with _Hx() as hx:
        claim(hx, _NOW)
        tr = hx.base / "t.jsonl"
        first = ("A" * 5000)
        tr.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": first}}) + "\n" + _rec("m1", _MA, 10, 1) + "\n" + _rec("m2", _MA, 20, 2) + "\n")
        res = _usage(hx, tr)
        jobs = _usage_jobs(hx)
        _check(f"{_T} AC33: first import: one job with the sums of m1 and m2", res.rc == 0 and len(jobs) == 1 and _tok(jobs[0]) == (30, 3, 0, 0), res.show())
        res = _usage(hx, tr)
        _check(f"{_T} AC33: re-import with nothing new adds no job", res.rc == 0 and len(_usage_jobs(hx)) == 1 and (parse(res) or {}).get("enqueued") == 0, res.show())
        # append: only the new message is imported
        with tr.open("a") as fh:
            fh.write(_rec("m3", _MA, 4, 5, 6, 7) + "\n")
        res = _usage(hx, tr)
        jobs = _usage_jobs(hx)
        new = [j for j in jobs if _tok(j) == (4, 5, 6, 7)]
        _check(f"{_T} AC33: after an append the re-import picks up only the new message", res.rc == 0 and len(jobs) == 2 and len(new) == 1, res.show() + repr([_tok(j) for j in jobs]))
        # a message whose records straddle the offset is counted once
        with tr.open("a") as fh:
            fh.write(_rec("m4", _MA, 100, 1) + "\n")
        _usage(hx, tr)
        n_before = len(_usage_jobs(hx))
        with tr.open("a") as fh:
            fh.write(_rec("m4", _MA, 100, 9, 50) + "\n" + _rec("m5", _MA, 8, 8) + "\n")    # m4's later record lands after the offset
        res = _usage(hx, tr)
        jobs = _usage_jobs(hx)
        added = jobs[n_before:]
        total = sum(_tok(j)[0] for j in jobs)
        _check(f"{_T} AC33: a message whose records straddle the offset is counted once (m4 is not re-imported; only m5 is new)",
               res.rc == 0 and len(added) == 1 and _tok(added[0]) == (8, 8, 0, 0), res.show() + repr([_tok(j) for j in added]))
        _check(f"{_T} AC33: total input over all jobs = 10+20+4+100+8 (m4's 100 once)", total == 142, repr(total))
        # a rewritten prefix re-reads from 0 without double counting
        sums_before = [sum(_tok(j)[i] or 0 for j in _usage_jobs(hx)) for i in range(4)]
        body = tr.read_text().split("\n", 1)[1]
        tr.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "B" * 5000}}) + "\n" + body)
        res = _usage(hx, tr)
        sums_after = [sum(_tok(j)[i] or 0 for j in _usage_jobs(hx)) for i in range(4)]
        _check(f"{_T} AC33: a file whose first 4 KiB changed is re-read from 0 and nothing is double counted",
               res.rc == 0 and sums_after == sums_before, res.show() + repr((sums_before, sums_after)))
        with tr.open("a") as fh:
            fh.write(_rec("m6", _MA, 1, 1) + "\n")
        res = _usage(hx, tr)
        sums_after2 = [sum(_tok(j)[i] or 0 for j in _usage_jobs(hx)) for i in range(4)]
        _check(f"{_T} AC33: ... and a later append after the rewrite adds only the new message", res.rc == 0 and sums_after2 == [sums_before[0] + 1, sums_before[1] + 1, sums_before[2], sums_before[3]], repr(sums_after2))
        # a shrunk file is re-read from 0 too
        tr.write_text("\n".join(tr.read_text().split("\n")[:3]) + "\n")
        res = _usage(hx, tr)
        sums_after3 = [sum(_tok(j)[i] or 0 for j in _usage_jobs(hx)) for i in range(4)]
        _check(f"{_T} AC33: a file that shrank is re-read from 0 and adds nothing", res.rc == 0 and sums_after3 == sums_after2, res.show())

    # bounded ledger
    with _Hx() as hx:
        claim(hx, _NOW)
        tr = hx.base / "big.jsonl"
        tr.write_text("")
        total_in = 0
        sizes = []
        for chunk in range(5):
            lines = []
            for i in range(1000):
                n = chunk * 1000 + i
                total_in += 3
                lines.append(_rec(f"msg_{n:06d}_" + hashlib.sha256(str(n).encode()).hexdigest()[:16], _MA, 3, 1))
            with tr.open("a") as fh:
                fh.write("\n".join(lines) + "\n")
            res = _usage(hx, tr, "sess-big")
            sizes.append(_STATE(hx).stat().st_size)
            if res.rc != 0:
                _check(f"{_T} AC33: big import chunk {chunk} succeeds", False, res.show())
                return
        jobs = _usage_jobs(hx)
        _check(f"{_T} AC33: 5,000 synthetic messages are all accounted for exactly once (input {total_in})", sum(_tok(j)[0] for j in jobs) == total_in and sum(_tok(j)[1] for j in jobs) == 5000,
               repr((sum(_tok(j)[0] for j in jobs), len(jobs))))
        # 5,000 ids stored whole would be >150 KB; a 64 KiB window holds ~300 records
        _check(f"{_T} AC33: state.json stays bounded after 5,000 messages ({sizes[-1]} bytes)", sizes[-1] < 70_000, repr(sizes))
        _check(f"{_T} AC33: the ledger does not grow with the transcript (size after 5,000 < 1.5 x size after 1,000 + 10 KB)", sizes[-1] < sizes[0] * 1.5 + 10_000, repr(sizes))


# ---------------------------------------------------------------------------
# AC35 Renewal keeps the larger spend
# ---------------------------------------------------------------------------

def test_rv_ac35_renewal_max() -> None:
    print(f"{_T} AC35 renewal")
    with _Hx() as hx:
        claim(hx, _NOW, spent={"windows": 2, "tokens": 100})
        claim(hx, _NOW + 5000, spent={"windows": 1, "tokens": 500})
        c = hx.claimed() or {}
        _check(f"{_T} AC35: a renewal takes the larger value per dimension (windows 2 from the store, tokens 500 from the response)",
               c.get("spent") == {"windows": 2, "tokens": 500}, repr(c.get("spent")))
        _check(f"{_T} AC35: spentAt becomes the time of the renewal", c.get("spentAt") == _NOW + 5000, repr(c.get("spentAt")))
        claim(hx, _NOW + 9000, spent={"windows": 0, "tokens": 40})
        c = hx.claimed() or {}
        _check(f"{_T} AC35: a response that is smaller in every dimension changes nothing but spentAt", c.get("spent") == {"windows": 2, "tokens": 500} and c.get("spentAt") == _NOW + 9000, repr(c))
        claim(hx, _NOW + 12000, spent={"windows": 3, "tokens": 600})
        _check(f"{_T} AC35: a response that is larger in every dimension wins", (hx.claimed() or {}).get("spent") == {"windows": 3, "tokens": 600}, repr(hx.claimed()))
    with _Hx() as hx:
        claim(hx, _NOW, spent={"windows": 2, "tokens": 900})
        claim(hx, _NOW + 1000, spent={"windows": 0, "tokens": 5}, task="other-task")
        _check(f"{_T} AC35 control: a claim on a different task takes the response as is", (hx.claimed() or {}).get("spent") == {"windows": 0, "tokens": 5}, repr(hx.claimed()))


# ---------------------------------------------------------------------------
# AC36 / AC37 / AC38 Reclaim guard, --as parked, open-ask predicate
# ---------------------------------------------------------------------------

def _park_with_mixed_actions(hx: _Hx, flag_ids: str):
    """ask-1 is unseen (park under --no-other-work); ask-2 is answered but not polled (wait)."""
    claim(hx, None)
    mkask(hx, None, "ask-1")
    mkask(hx, None, "ask-2")
    set_status(hx, st("ask-1", seen=None), st("ask-2", answered=True))
    res, out = decide(hx, None, "--no-other-work")
    acts = {k: v.get("action") for k, v in by_id(out).items()}
    rel = dc(hx, None, "release", "--task", TASK, "--reason", "Waiting on questions.", "--parked-asks", flag_ids)
    return acts, rel


def test_rv_ac36_reclaim_set() -> None:
    print(f"{_T} AC36 reclaim guard")
    for flag_ids in ("ask-1,ask-2", "ask-1"):
        with _Hx() as hx:
            acts, rel = _park_with_mixed_actions(hx, flag_ids)
            _check(f"{_T} AC36 setup ({flag_ids}): one ask parks and one waits; the release succeeds",
                   acts.get("ask-1") == "park" and acts.get("ask-2") == "wait" and rel.rc == 0, repr(acts) + rel.show())
            p = (full_state(hx).get("parked") or [{}])[0]
            _check(f"{_T} AC36 ({flag_ids}): the park records every open blocking ask, whatever its action", sorted(p.get("openAskIds", [])) == ["ask-1", "ask-2"], repr(p))
            claim(hx, None)
            res, out = decide(hx, None, "--no-other-work")
            _check(f"{_T} AC36 ({flag_ids}): reclaimed with both asks still open -> reclaimed_parked true, next release-again",
                   out is not None and out.get("reclaimed_parked") is True and out.get("next") == "release-again", res.show())
            # control: a new open ask changes the set
            mkask(hx, None, "ask-3")
            set_status(hx, st("ask-1", seen=None), st("ask-2", answered=True), st("ask-3", seen=None))
            res, out = decide(hx, None, "--no-other-work")
            _check(f"{_T} AC36 control ({flag_ids}): a third open ask -> reclaimed_parked false", (out or {}).get("reclaimed_parked") is False, res.show())


def test_rv_ac37_as_parked() -> None:
    print(f"{_T} AC37 --as parked")
    with _Hx() as hx:
        claim(hx, _NOW)
        key = mkask(hx, _NOW, "ask-1")
        res = dc(hx, _NOW, "decide", "--resolve", key, "--as", "parked")
        _check(f"{_T} AC37: `decide --resolve KEY --as parked` is a usage error (non-zero, nothing recorded)", res.rc != 0 and not full_state(hx).get("resolved"), res.show())
        res = dc(hx, _NOW, "decide", "--resolve", key, "--as", "bogus")
        _check(f"{_T} AC37: any other value is a usage error too", res.rc != 0 and not full_state(hx).get("resolved"), res.show())
        res = dc(hx, _NOW, "decide", "--resolve", key)
        _check(f"{_T} AC37: omitting --as is a usage error", res.rc != 0, res.show())
        res = dc(hx, _NOW, "decide", "--resolve", key, "--as", "proceeded")
        r = full_state(hx).get("resolved") or []
        _check(f"{_T} AC37 control: --as proceeded still records the resolution", res.rc == 0 and len(r) == 1 and r[0].get("as") == "proceeded", res.show())
        _check(f"{_T} AC37: the usage text no longer offers `parked` for --as", "--as proceeded|parked" not in (dc(hx, _NOW, "decide", "--resolve", key, "--as", "parked").err + res.err), "")
        res = dc(hx, _NOW, "decide", "--resolve", key, "--as", "parked")
        _check(f"{_T} AC37: ... after a proceeded resolution `--as parked` is still refused", res.rc != 0, res.show())


def test_rv_ac38_open_ask_predicate() -> None:
    print(f"{_T} AC38 one open-ask predicate")
    # pruning: a legacy answer without `task` does not make the ask job prunable
    with _Hx() as hx:
        seed = _seed_comment(hx)
        hx.route("ask", json={"ask_id": "seed-ask", "placed": "subtask"})
        dc(hx, _NOW, "enqueue", "ask", "--key", "seed-ask", "--task", "project", stdin=json.dumps(
            {"question": "Q?", "default": "d", "order": 1, "estimate_minutes": 2, "remaining_minutes": 45, "reversible": True, "blocking": True}))
        dc(hx, _NOW, "flush")
        sa = copy.deepcopy(hx.job("seed-ask"))
        if not (seed and sa and sa.get("state") == "done"):
            _check(f"{_T} AC38 setup: a done seed ask", False, repr(sa))
            return
        s = full_state(hx)
        jobs = [_done(seed, f"c{i}", _NOW - 5 * _DAY + i) for i in range(2100)]
        for name in ("legacy", "tasked"):
            j = copy.deepcopy(sa)
            j.update(key=f"ask-{name}", doneAtMs=_NOW - 6 * _DAY, state="done")
            j["result"] = {"ask_id": f"id-{name}", "placed": "subtask"}
            jobs.append(j)
        s["jobs"] = jobs
        base = {"content": "yes", "ownerAnswer": True, "seenAt": 1, "answeredAt": 2, "answeredBy": "me", "receivedAt": "2026-01-01T00:00:00Z"}
        s.setdefault("answers", []).extend([dict(base, id="id-legacy"), dict(base, id="id-tasked", task="project")])
        _write_state(hx, s)
        dc(hx, _NOW, "enqueue", "comment", "--key", "trigger", "--task", "project", stdin=json.dumps({"text": "t"}))
        keys = {j["key"] for j in hx.jobs()}
        _check(f"{_T} AC38: an old ask job whose only 'answer' is a legacy record without a task is still open, so it is kept", "ask-legacy" in keys, repr(sorted(k for k in keys if k.startswith("ask-"))))
        _check(f"{_T} AC38 control: the same answer WITH the matching task makes the ask job prunable", "ask-tasked" not in keys, repr(sorted(k for k in keys if k.startswith("ask-"))))
    # decide: a legacy answer does not hide the ask
    with _Hx() as hx:
        claim(hx, LS)
        mkask(hx, LS, "ask-1")
        set_status(hx, st("ask-1"))
        s = full_state(hx)
        s.setdefault("answers", []).append({"id": "ask-1", "content": "yes", "ownerAnswer": True, "seenAt": 1, "answeredAt": 2, "answeredBy": "me", "receivedAt": "2026-01-01T00:00:00Z"})
        _write_state(hx, s)
        res, out = decide(hx, LS)
        _check(f"{_T} AC38: a legacy answer record without a task does not hide the ask from decide", "ask-1" in by_id(out), res.show())
        s = full_state(hx)
        s["answers"][-1]["task"] = TASK
        _write_state(hx, s)
        res, out = decide(hx, LS)
        _check(f"{_T} AC38 control: the same record with the claimed task hides it (it is answered)", "ask-1" not in by_id(out), res.show())


# ---------------------------------------------------------------------------
# AC39 Claim stored before the body file
# ---------------------------------------------------------------------------

def test_rv_ac39_body_file() -> None:
    print(f"{_T} AC39 body file")
    full = "é€" * 40000
    with _Hx() as hx:
        body = hx.vibe / "taskandi-body.txt"
        body.write_text("tracked\n")
        subprocess.run(["git", "add", "-f", ".vibe/taskandi-body.txt"], cwd=str(hx.repo), input="", capture_output=True, text=True, check=True)
        hx.route("next_task", json=nt(body=full))
        res = dc(hx, _NOW, "next-task", "--agent", "claude", "--session", SESSION)
        out = parse(res) or {}
        t = _body_of(out)
        c = hx.claimed() or {}
        _check(f"{_T} AC39: a tracked body file does not fail the claim: exit 0 and the claim is stored", res.rc == 0 and c.get("task") == TASK, res.show())
        _check(f"{_T} AC39: stdout carries body_file null and a body_file_error reason", t.get("body_file") is None and "body_file" in t and isinstance(t.get("body_file_error"), str) and t["body_file_error"], res.show()[:400])
        _check(f"{_T} AC39: the tracked file was not overwritten", body.read_text() == "tracked\n", repr(body.read_text()[:30]))
        _check(f"{_T} AC39: the truncated body is still printed", t.get("body_truncated") is True and t.get("body") == full[:20000], res.show()[:200])
    with _Hx() as hx:
        hx.route("next_task", json=nt(body=full))
        res = dc(hx, _NOW, "next-task", "--agent", "claude", "--session", SESSION)
        t = _body_of(parse(res))
        _check(f"{_T} AC39 control: untracked, the body file is written and named, with no body_file_error", res.rc == 0 and isinstance(t.get("body_file"), str) and "body_file_error" not in t, res.show()[:300])
        bf = hx.vibe / "taskandi-body.txt"
        _check(f"{_T} AC39 control: the file exists", bf.exists())
        hx.route("next_task", json={"task": None})
        res = dc(hx, _NOW + 1000, "next-task", "--agent", "claude", "--session", SESSION)
        _check(f"{_T} AC39: a next-task that returns no task deletes the stale body file (and the claim)", res.rc == 0 and not bf.exists() and hx.claimed() is None, res.show())
        res = dc(hx, _NOW + 2000, "next-task", "--agent", "claude", "--session", SESSION)
        _check(f"{_T} AC39: ... and doing it again with no file present is harmless", res.rc == 0, res.show())


# ---------------------------------------------------------------------------
# AC34 Projects without a binding are never touched
# ---------------------------------------------------------------------------

_SKIP34 = ("Skip this section unless `.vibe/taskandi-descriptor.json` or `.vibe/taskandi.json` exists in the project; "
        "if one does, run `taskandi-client status`: continue only if it prints `\"bound\":true` with `\"channel\":\"taskandi-http\"`, "
        "and if it exits 1, use the file channel for this run and post one question saying the Task&I binding is broken, quoting its message.")
_OLD_SKIP = "Skip this section unless `taskandi-client status` prints"


def test_rv_ac34_unbound_never_touched() -> None:
    print(f"{_T} AC34 unbound projects")
    root = Path(__file__).resolve().parent.parent / "devcontainer"
    files = {"vss.md": root / "commands" / "vss.md", "vsss.md": root / "commands" / "vsss.md",
             "taskandi-harness.md": root / "taskandi-harness.md", "codex/context.md": root / "codex" / "context.md"}
    for name, path in files.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        flat = re.sub(r"\s+", " ", text)
        _check(f"{_T} AC34: {name} carries the exact new skip string", _SKIP34 in flat, "missing")
        _check(f"{_T} AC34: {name} has no remnant of the old skip string", _OLD_SKIP not in flat, "old text present")
        _check(f"{_T} AC34: {name} names both config files", ".vibe/taskandi-descriptor.json" in flat and ".vibe/taskandi.json" in flat)
    # the file check matters: outside a git worktree `status` fails, so the old skip condition would have run it
    with tempfile.TemporaryDirectory(prefix="taskandi-nogit-") as td:
        res = subprocess.run(["node", str(_CLIENT), "status"], cwd=td, input="", capture_output=True, text=True, timeout=60)
        _check(f"{_T} AC34 control: in a non-git folder with no config, `taskandi-client status` exits 1 (so only the file check keeps an unbound project clean)",
               res.returncode == 1, f"rc={res.returncode} {res.stderr[:200]!r}")
    # a project with neither file: the skip condition is false, so the prose never reaches the client
    with _Hx(bound=False) as hx:
        neither = not (hx.vibe / "taskandi-descriptor.json").exists() and not (hx.vibe / "taskandi.json").exists()
        _check(f"{_T} AC34: setup - a project with neither config file (skip condition true)", neither)


# ---------------------------------------------------------------------------
# AC40 Fixture copies pinned by hash
# ---------------------------------------------------------------------------

def _pin_problems(dirpath: Path) -> list:
    prov = dirpath / "PROVENANCE.md"
    text = prov.read_text() if prov.exists() else ""
    problems = []
    for n in _NAMES:
        f = dirpath / f"{n}.json"
        line = next((ln for ln in text.splitlines() if f"{n}.json" in ln and re.search(r"\b[0-9a-f]{64}\b", ln)), None)
        if line is None:
            problems.append(f"{n}.json: no sha256 listed")
        elif not f.exists():
            problems.append(f"{n}.json: file missing")
        elif hashlib.sha256(f.read_bytes()).hexdigest() not in line:
            problems.append(f"{n}.json: hash mismatch")
    return problems


def test_rv_ac40_fixture_pins() -> None:
    print(f"{_T} AC40 fixture pins")
    probs = _pin_problems(_FIX_REPO)
    _check(f"{_T} AC40: PROVENANCE.md lists a sha256 for each of the ten files and every file matches", probs == [], "; ".join(probs))
    with tempfile.TemporaryDirectory(prefix="taskandi-pins-") as td:
        d = Path(td)
        for p in _FIX_REPO.iterdir():
            (d / p.name).write_bytes(p.read_bytes())
        _check(f"{_T} AC40 control: an untouched copy passes the same check", _pin_problems(d) == [], "; ".join(_pin_problems(d)))
        f = d / "ask.json"
        f.write_bytes(f.read_bytes() + b" ")
        _check(f"{_T} AC40 control: a tampered copy fails the check", any("ask.json" in p for p in _pin_problems(d)), repr(_pin_problems(d)))
        (d / "PROVENANCE.md").write_text((_FIX_REPO / "PROVENANCE.md").read_text().replace("ask.json", "ask-x.json"))
        _check(f"{_T} AC40 control: a PROVENANCE.md that does not list a file fails the check", any("no sha256" in p for p in _pin_problems(d)))


_TESTS = [test_rv_ac32_tombstones, test_rv_ac33_usage_offset, test_rv_ac34_unbound_never_touched, test_rv_ac35_renewal_max,
          test_rv_ac36_reclaim_set, test_rv_ac37_as_parked, test_rv_ac38_open_ask_predicate, test_rv_ac39_body_file, test_rv_ac40_fixture_pins]


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
        sys.exit(1)
    print("PASS: task_065 cycle 3 acceptance checks")
