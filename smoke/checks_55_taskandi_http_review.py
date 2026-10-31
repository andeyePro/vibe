#!/usr/bin/env python3
"""Acceptance checks for task_064 cycle 2 (spec "Rev 6 addendum", AC19-AC30).

Tester-owned.  Reuses the loopback harness of ``checks_50_taskandi_http.py``.
Run only this module with:
    python3 smoke/checks_55_taskandi_http_review.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import FAILURES
from smoke.checks_48_vibe_link import _Fx, _VL, _SENTINEL_UUID, _setup_demo
from smoke.checks_50_taskandi_http import (_CLIENT, _CONN, _DROP, _REPO, _SUPERVISOR, _T1, _TOKEN, _WS, _RESULTS, _Hx,
                                           _check, _fixture, _fixture_payload, _canon_digest, _la, _CONTRACT)
from smoke.checks_52_taskandi_http_more import _nt, _write_transcript

_T = "[taskandi-http-r6]"
_UNUSABLE = "task id not usable by vibe: rename it in Task&I or recreate the task"
_RELEASE_REASON = "Task id not usable by vibe; rename it in Task&I."


def _j(status, code, **extra):
    return {"status": status, "json": {"error": code, **extra}}


def _next(hx: _Hx, session="session-a"):
    return hx.cli("next-task", "--agent", "claude", "--session", session)


def _tmp_port_closed() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# AC19 launcher and supervisor accept usable ids
# ---------------------------------------------------------------------------

_USABLE = ["leaf-b", "project", "a.b:c-d", "A", "a" * 200, "taskandeye://node/leaf-b", "taskandeye://node/" + "b" * 200,
           "ABBR-12", _SENTINEL_UUID, _SENTINEL_UUID.upper()]
_UNUSABLE_IDS = ["a b", "a" * 201, "-lead", ".lead", "a/b", "a'b", "a;b", "a$b", "taskandeye://node/a b",
                 "taskandeye://node/", "taskandeye://node/" + "b" * 201, "taskandeye://node/-x"]


def test_r6_ac19_launcher_and_supervisor() -> None:
    print(f"{_T} AC19 launcher and supervisor accept usable ids")
    fx = _Fx()
    try:
        for u in _USABLE:
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            msg = res.stdout + res.stderr
            _check(f"{_T} AC19: vibe --task {u[:40]!r} is accepted (parser reaches the unknown flag)",
                   res.returncode == 1 and "--task needs" not in msg and "--no-such-flag-zzz" in msg, msg[:300])
        for u in _UNUSABLE_IDS:
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            msg = res.stdout + res.stderr
            _check(f"{_T} AC19: vibe --task {u[:40]!r} is refused with '--task needs'",
                   res.returncode == 1 and "--task needs" in msg, msg[:300])
        res = fx.vibe("--task", "leaf-b", "--task", "project", "--no-such-flag-zzz")
        _check(f"{_T} AC19: two usable --task ids still give 'Only one --task binding'",
               "Only one --task binding" in res.stdout + res.stderr, res.stdout + res.stderr)
    finally:
        fx.close("r6-ac19-cli")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        url = "vibe://open?project=demo"
        for u in ("leaf-b", "a.b:c", "taskandeye://node/leaf-b"):
            shutil.rmtree(fx.stamps, ignore_errors=True)
            res = fx.open(f"{url}&task={u}", VIBE_LINK_ASSUME="open")
            _check(f"{_T} AC19: `vibe link` still refuses task={u} (links keep the UUID/ABBR pattern)",
                   res.returncode == 2 and "refused URL" in res.stderr, f"rc={res.returncode} {res.stderr}")
        shutil.rmtree(fx.stamps, ignore_errors=True)
        res = fx.open(f"{url}&task=ABBR-4", VIBE_LINK_ASSUME="open")
        _check(f"{_T} AC19: control - `vibe link` task=ABBR-4 is still accepted (refusals above are specific)",
               res.returncode != 2 or "refused URL" not in res.stderr, f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("r6-ac19-link")
    # supervisor: the regex literal of the launch-binding check, extracted from source as checks_49 does.
    src = _SUPERVISOR.read_text()
    lines = src.splitlines()
    idx = next((i for i, ln in enumerate(lines) if "invalid launch task binding" in ln), None)
    _check(f"{_T} AC19: found the supervisor's launch-binding check", idx is not None)
    if idx is None:
        return
    window = "\n".join(lines[max(0, idx - 3):idx + 1])
    lits = re.findall(r"(/\^(?:[^/\\\n]|\\.)*?\$/)", window)
    _check(f"{_T} AC19: found a regex literal next to the launch-binding check", bool(lits), window[-300:])
    if not lits:
        return
    js = ("const re = " + lits[-1] + "; const out = {}; "
          "for (const v of JSON.parse(process.argv[1])) out[v] = re.test(v); console.log(JSON.stringify(out));")
    vals = _USABLE + _UNUSABLE_IDS + [""]
    r = subprocess.run(["node", "-e", js, json.dumps(vals)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    try:
        got = json.loads(r.stdout)
    except ValueError:
        got = {}
    for v in _USABLE:
        _check(f"{_T} AC19: supervisor binding regex accepts {v[:40]!r}", got.get(v) is True, r.stdout + r.stderr)
    for v in _UNUSABLE_IDS + [""]:
        _check(f"{_T} AC19: supervisor binding regex rejects {v[:40]!r}", got.get(v) is False, r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# AC20 409 detail fields
# ---------------------------------------------------------------------------

def test_r6_ac20_409_detail_fields() -> None:
    print(f"{_T} AC20 409 bodies with detail keys")
    mark = "EXTRAMARK-77"
    cases = [
        ("lease_held with until", _j(409, "lease_held", until=123), "queued", 1),
        ("stale_context with detail", _j(409, "stale_context", detail=mark), "queued", 1),
        ("wrong_origin 421 with detail", _j(421, "wrong_origin", detail=mark), "queued", 1),
        ("connection_scope 403 with detail", _j(403, "connection_scope", detail=mark), "queued", 1),
        ("wrong_thread with detail", _j(409, "wrong_thread", detail=mark), "refused", 2),
        ("invalid_request 400 with detail", _j(400, "invalid_request", detail=mark), "refused", 2),
        ("connection_unavailable with detail", _j(409, "connection_unavailable", detail=mark), "uncertain", 1),
        ("unlisted code with detail", _j(409, "made_up_code", detail=mark), "uncertain", 1),
        ("error not a string", {"status": 409, "json": {"error": 5, "until": 1}}, "uncertain", 1),
        ("no error key", {"status": 409, "json": {"until": 1}}, "uncertain", 1),
        ("array body", {"status": 409, "json": [{"error": "lease_held"}]}, "uncertain", 1),
        ("string body", {"status": 409, "json": "lease_held"}, "uncertain", 1),
    ]
    for label, spec, want, reqs in cases:
        with _Hx() as hx:
            hx.enqueue("comment", "k1", {"text": "first"}, task="project")
            hx.enqueue("comment", "k2", {"text": "second"}, task="project")
            hx.route("comment", **spec)
            res = hx.cli("flush")
            j1, j2 = hx.job("k1") or {}, hx.job("k2") or {}
            want2 = "refused" if want == "refused" else "queued"
            _check(f"{_T} AC20: {label}: k1 {want}, k2 {want2}, {reqs} comment request(s)",
                   j1.get("state") == want and j2.get("state") == want2 and hx.count("comment") == reqs,
                   f"{j1.get('state')}/{j2.get('state')} reqs={hx.count('comment')} {res.show()}")
            _check(f"{_T} AC20: {label}: detail keys never printed", mark not in res.out + res.err and "123" not in res.err.replace("\n", " ")
                   .replace(str(hx.port), ""), res.show())
    # open_children keeps strict validation of children, extra keys elsewhere ignored
    with _Hx() as hx:
        hx.claim("leaf-b")
        kids = [{"task": "kid-1", "title": "Kid one"}]
        hx.route("complete", **_j(409, "open_children", children=kids, note="x"))
        res = hx.cli("complete", "--summary", "s")
        out = res.json() or {}
        _check(f"{_T} AC20: open_children with an extra key is still interpreted (exit 0, completed false, claim kept)",
               res.rc == 0 and out.get("completed") is False and out.get("open_children") == kids and hx.claimed() is not None, res.show())
        hx.route("complete", **_j(409, "open_children", children=[{"task": "kid-1"}]))
        res = hx.cli("complete", "--summary", "s")
        _check(f"{_T} AC20: open_children with a malformed child is not interpreted (exit 1, claim kept)",
               res.rc == 1 and hx.claimed() is not None, res.show())
    # direct command classification: lease_held with detail -> refused for now
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.route("release", **_j(409, "lease_held", until=123))
        res = hx.cli("release", "--reason", "r")
        _check(f"{_T} AC20: direct release with lease_held+until prints 'refused for now: lease_held', claim kept",
               res.rc == 1 and "Task&I refused for now: lease_held" in res.err and hx.claimed() is not None, res.show())


# ---------------------------------------------------------------------------
# AC21 TLS counts as not sent
# ---------------------------------------------------------------------------

_TLS_SERVER = r'''
import https from 'node:https';
import net from 'node:net';
import fs from 'node:fs';
const [keyPath, certPath, log, routesJson] = process.argv.slice(2);
const routes = JSON.parse(routesJson);
const w = o => fs.appendFileSync(log, JSON.stringify(o) + '\n');
const tls = https.createServer({ key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }, (req, res) => {
  const chunks = []; req.on('data', c => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks).toString('utf8'); let j = {}; try { j = JSON.parse(body); } catch {}
    w({ t: 'req', action: j.action, auth: req.headers.authorization, host: req.headers.host });
    let r = routes[j.action] ?? { status: 404, json: {} }; let o = r.json;
    if (o && typeof o === 'object' && 'task' in o && typeof j.task === 'string') o = { ...o, task: j.task };
    res.writeHead(r.status ?? 200, { 'content-type': 'application/json' }); res.end(JSON.stringify(o));
  });
});
let n = 0;
const failAfter = Number(process.env.FAIL_AFTER ?? 1e9);
const server = net.createServer(sock => { n += 1; w({ t: 'conn', n }); if (n > failAfter) sock.destroy(); else tls.emit('connection', sock); });
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
'''


def _make_cert(d: Path) -> tuple[Path, Path] | None:
    if not shutil.which("openssl"):
        return None
    key, crt = d / "k.pem", d / "c.pem"
    r = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                        "-days", "2", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       input="", capture_output=True, text=True)
    return (key, crt) if r.returncode == 0 and key.exists() and crt.exists() else None


def test_r6_ac21_tls_counts_as_not_sent() -> None:
    print(f"{_T} AC21 TLS failure is not a sent request")
    with _Hx(bound=False) as hx:
        pair = _make_cert(hx.base)
        if pair is None:
            print(f"{_T} AC21: SKIPPED - openssl unavailable or failed to make a cert")
            return
        key, crt = pair
        routes = {n: {"json": _fixture(n)["response"]} for n in ("capabilities", "comment", "next_task", "release", "complete")}
        log = hx.base / "tls.jsonl"
        log.write_text("")
        procs = []

        def serve(fail_after=None):
            env = {**os.environ, "FAIL_AFTER": str(fail_after if fail_after is not None else 10 ** 9)}
            p = subprocess.Popen(["node", "--input-type=module", "--eval", _TLS_SERVER, "x", str(key), str(crt), str(log),
                                  json.dumps(routes)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, env=env)
            procs.append(p)
            return int(p.stdout.readline().strip())

        def events():
            return [json.loads(x) for x in log.read_text().splitlines() if x.strip()]

        try:
            port = serve()
            hx.port = port
            hx.write_desc(origin=f"https://127.0.0.1:{port}")
            hx.enqueue("comment", "t1", {"text": "x"}, task="project")
            res = hx.cli("flush")
            _check(f"{_T} AC21: untrusted self-signed cert -> exit 1, job stays queued (capabilities never succeeds), nothing leaked",
                   res.rc == 1 and (hx.job("t1") or {}).get("state") == "queued"
                   and not any(e.get("action") == "comment" for e in events() if e["t"] == "req")
                   and _TOKEN not in res.out + res.err, res.show())
            ca = {"NODE_EXTRA_CA_CERTS": str(crt)}
            res = hx.cli("flush", env=ca)
            _check(f"{_T} AC21: control - with the cert trusted the job is delivered over TLS (Bearer token, 2 requests)",
                   res.rc == 0 and (hx.job("t1") or {}).get("state") == "done"
                   and [e["action"] for e in events() if e["t"] == "req"] == ["capabilities", "comment"], res.show())
            # second TLS connection fails during the handshake: the comment was never sent.
            log.write_text("")
            port2 = serve(fail_after=1)
            hx.write_desc(origin=f"https://127.0.0.1:{port2}")
            hx.enqueue("comment", "t2", {"text": "y"}, task="project")
            res = hx.cli("flush", env=ca)
            job = hx.job("t2") or {}
            _check(f"{_T} AC21: a TLS handshake failure on the write leaves the job queued (not uncertain), counted as requeued",
                   (res.json() or {}).get("uncertain") == 0 and job.get("state") == "queued" and any(e["t"] == "conn" and e["n"] >= 2 for e in events()),
                   f"{res.show()} job={job} events={events()}")
            res = hx.cli("flush", env=ca)
            _check(f"{_T} AC21: control - no uncertain job exists afterwards (status counts)",
                   (hx.cli("status").json() or {}).get("counts", {}).get("uncertain", 0) == 0, res.show())
        finally:
            for p in procs:
                p.kill()
                p.wait()
                p.stdout.close()
    src = _CLIENT.read_text()
    _check(f"{_T} AC21: source sets rejectUnauthorized: true and waits for secureConnect",
           "rejectUnauthorized: true" in src and "secureConnect" in src, "")


# ---------------------------------------------------------------------------
# AC22 unusable id releases the lease
# ---------------------------------------------------------------------------

def test_r6_ac22_unusable_id_releases_lease() -> None:
    print(f"{_T} AC22 unusable task id releases its lease")
    for label, tid in (("space", "a b"), ("201 chars", "a" * 201), ("slash", "x/y")):
        with _Hx() as hx:
            hx.route("next_task", json=_nt(task=tid))
            res = _next(hx, session="sess-q")
            rel = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == "release"]
            body = rel[0] if rel else {}
            _check(f"{_T} AC22: id {label}: exit 1, exact message, empty stdout, no claim",
                   res.rc == 1 and _UNUSABLE in res.err and res.out == "" and hx.claimed() is None, res.show())
            _check(f"{_T} AC22: id {label}: exactly one release {{task, reason, session}} is sent after next_task",
                   len(rel) == 1 and body.get("task") == tid and body.get("reason") == _RELEASE_REASON
                   and body.get("session") == "sess-q" and set(body) == {"action", "connection", "task", "reason", "session"}
                   and hx.actions() == ["capabilities", "next_task", "release"], repr(hx.actions()) + repr(body)[:300])
    with _Hx() as hx:
        hx.route("next_task", json=_nt(task="a b"))
        hx.route("release", **_j(409, "stale_context"))
        res = _next(hx)
        _check(f"{_T} AC22: a failed release is reported on stderr and keeps exit 1 with the unusable-id message",
               res.rc == 1 and _UNUSABLE in res.err and "release" in res.err.lower().replace(_UNUSABLE, "") and res.out == "", res.show())
        hx.route("release", raw="not json", status=500)
        res = _next(hx)
        _check(f"{_T} AC22: an unknown-outcome release also keeps exit 1 and the message",
               res.rc == 1 and _UNUSABLE in res.err and res.out == "", res.show())
    with _Hx() as hx:
        hx.route("next_task", json=_nt(task="leaf-b"))
        res = _next(hx)
        _check(f"{_T} AC22: control - a usable id sends no release", res.rc == 0 and "release" not in hx.actions(), res.show())


# ---------------------------------------------------------------------------
# AC23 status with an invalid descriptor
# ---------------------------------------------------------------------------

def test_r6_ac23_status_invalid_descriptor() -> None:
    print(f"{_T} AC23 status with a present but invalid descriptor")
    cases = [("wrong protocol", dict(protocol="other"), 0o600, r"protocol"),
             ("short token", dict(token=_TOKEN[:42]), 0o600, r"token"),
             ("mode 0644", {}, 0o644, r"chmod 600"),
             ("bad origin", dict(origin="http://localhost:1"), 0o600, r"origin")]
    for label, over, mode, pat in cases:
        with _Hx() as hx:
            hx.write_desc(mode=mode, **over)
            res = hx.cli("status")
            lines = [ln for ln in res.err.splitlines() if ln.strip()]
            _check(f"{_T} AC23: status with {label}: exit 1, empty stdout, one stderr line naming the problem",
                   res.rc == 1 and res.out == "" and len(lines) == 1 and re.search(pat, lines[0], re.I)
                   and "file-fallback" not in res.err and hx.reqs() == [], res.show())
    with _Hx() as hx:
        res = hx.cli("status")
        _check(f"{_T} AC23: control - a valid descriptor reports status (taskandi-http)",
               res.rc == 0 and (res.json() or {}).get("channel") == "taskandi-http", res.show())
    with _Hx(bound=False) as hx:
        res = hx.cli("status")
        _check(f"{_T} AC23: control - no descriptor at all is the unbound status (exit 0)", res.rc == 0, res.show())


# ---------------------------------------------------------------------------
# AC24 usage in one pass
# ---------------------------------------------------------------------------

_PRELOAD = r'''
const fs = require('node:fs');
const counts = { lock: 0 };
const orig = fs.openSync;
fs.openSync = function (p, ...rest) { if (typeof p === 'string' && p.endsWith('.lock')) counts.lock += 1; return orig.call(this, p, ...rest); };
require('node:module').syncBuiltinESMExports();
process.on('exit', () => { try { fs.writeFileSync(process.env.LOCK_COUNT_FILE, JSON.stringify(counts)); } catch {} });
'''


def test_r6_ac24_usage_one_pass() -> None:
    print(f"{_T} AC24 usage importer: one config load, one outbox lock")
    with _Hx() as hx:
        pre = hx.base / "preload.cjs"
        pre.write_text(_PRELOAD)
        cnt = hx.base / "lockcount.json"
        tr = hx.base / "big.jsonl"
        rows = [{"type": "turn_context", "payload": {"model": "gpt-test"}}]
        for i in range(1, 501):
            rows.append({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
                "input_tokens": 100 * i, "cached_input_tokens": 10 * i, "cache_write_input_tokens": i, "output_tokens": 20 * i}}}})
        tr.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        t0 = time.time()
        res = hx.cli("usage", "--transcript", str(tr), "--session", "sess-big", "--account", "acct-1", "--cost-estimate", "0.1",
                     env={"NODE_OPTIONS": f"--require {pre}", "LOCK_COUNT_FILE": str(cnt)})
        took = time.time() - t0
        out = res.json() or {}
        locks = json.loads(cnt.read_text()).get("lock") if cnt.exists() else None
        _check(f"{_T} AC24: a large transcript imports many records ({out.get('enqueued')}) under exactly one .lock creation (saw {locks})",
               res.rc == 0 and (out.get("enqueued") or 0) >= 100 and locks == 1 and len(hx.jobs()) == out.get("enqueued"),
               res.show() + f" locks={locks}")
        _check(f"{_T} AC24: the 500-record import completes in a few seconds (took {took:.1f}s)", took < 20, f"{took:.1f}s")
        locks_before = locks
        res = hx.cli("usage", "--transcript", str(tr), "--session", "sess-big", "--account", "acct-1", "--cost-estimate", "0.1",
                     env={"NODE_OPTIONS": f"--require {pre}", "LOCK_COUNT_FILE": str(cnt)})
        locks = json.loads(cnt.read_text()).get("lock")
        _check(f"{_T} AC24: re-import deduplicates everything, still one lock ({locks_before} -> {locks})",
               res.rc == 0 and (res.json() or {}).get("enqueued") == 0 and locks == 1, res.show())


# ---------------------------------------------------------------------------
# AC25 origin host is part of the binding
# ---------------------------------------------------------------------------

_FP = "out.fp = C.bindingFingerprint(C.loadConfig(cwd));"


def _fp_for(workspace, task, host):
    return _canon_digest({"kind": "descriptor-http", "workspace": workspace, "task": task, "contractRevision": _CONTRACT,
                          "originHost": host})


def test_r6_ac25_origin_in_binding() -> None:
    print(f"{_T} AC25 origin scheme+host in the binding digest")
    with _Hx() as hx:
        fp0 = hx.lib(_FP).get("fp")
        _check(f"{_T} AC25: fingerprint = digest({{kind, workspace, task, contractRevision, originHost: 'http://127.0.0.1'}})",
               fp0 == _fp_for(_WS, "project", "http://127.0.0.1"), fp0)
        hx.reconnect()
        _check(f"{_T} AC25: a new port on the same host keeps the fingerprint", hx.lib(_FP).get("fp") == fp0, "")
        hx.write_desc(origin="https://svc.example.test:8443", token=_TOKEN)
        fp_https = hx.lib(_FP).get("fp")
        _check(f"{_T} AC25: an https origin digests as https://svc.example.test", fp_https == _fp_for(_WS, "project", "https://svc.example.test"), fp_https)
        hx.write_desc(origin="https://svc.example.test:9", token=_TOKEN)
        _check(f"{_T} AC25: https port change alone keeps the fingerprint", hx.lib(_FP).get("fp") == fp_https, "")
        hx.write_desc(origin="https://other.example.test:9", token=_TOKEN)
        _check(f"{_T} AC25: a changed host changes the fingerprint", hx.lib(_FP).get("fp") not in (fp_https, fp0), "")
    with _Hx() as hx:
        hx.enqueue("comment", "h1", {"text": "t"}, task="project")
        hx.cli("poll")
        fp0 = hx.lib(_FP).get("fp")
        hx.write_desc(origin="https://other.example.test:9")
        hx.clear()
        res = hx.cli("flush")
        _check(f"{_T} AC25: a changed origin host -> flush fails binding changed, nothing sent",
               res.rc != 0 and re.search(r"binding changed|BINDING_CHANGED", res.err) and hx.reqs() == [], res.show())
        res = hx.cli("poll")
        _check(f"{_T} AC25: a changed origin host -> poll fails `answer binding changed`",
               res.rc != 0 and "answer binding changed" in res.err and hx.reqs() == [], res.show())
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1", env={"VIBE_TASK_BINDING": fp0})
        _check(f"{_T} AC25: a changed origin host -> pinned fingerprint fails `pinned task binding changed`",
               res.rc != 0 and "pinned task binding changed" in res.err, res.show())
        hx.reconnect()
        res = hx.cli("flush", env={"VIBE_TASK_BINDING": fp0})
        _check(f"{_T} AC25: control - same host, new port: queued job flushes under the old pin",
               res.rc == 0 and (hx.job("h1") or {}).get("state") == "done", res.show())


# ---------------------------------------------------------------------------
# AC26 terminal-safe stdout
# ---------------------------------------------------------------------------

def _esc_ok(raw: str, code: str) -> bool:
    return re.search(r"\\u" + code, raw, re.I) is not None


def test_r6_ac26_terminal_safe_stdout() -> None:
    print(f"{_T} AC26 terminal-safe stdout and length caps")
    c1, bidi = "\u009b", "‮"
    with _Hx() as hx:
        hx.route("next_task", json=_nt(task="leaf-b", title=f"ti{c1}tle{bidi}x", owner=f"ow{c1}ner{bidi}"))
        res = _next(hx)
        _check(f"{_T} AC26: next-task title/owner with U+009B and U+202E print as \\u009b / \\u202e (no raw control characters)",
               res.rc == 0 and _esc_ok(res.out, "009b") and _esc_ok(res.out, "202e") and c1 not in res.out and bidi not in res.out
               and (res.json() or {}).get("task", {}).get("title") == f"ti{c1}tle{bidi}x", res.show())
        for ch, code in (("\u0080", "0080"), ("\u009f", "009f"), ("‪", "202a"), ("⁦", "2066"), ("⁩", "2069")):
            hx.route("next_task", json=_nt(task="leaf-b", title=f"a{ch}b"))
            res = _next(hx)
            _check(f"{_T} AC26: U+{code.upper()} in a title is escaped", res.rc == 0 and _esc_ok(res.out, code) and ch not in res.out, res.show())
        hx.route("next_task", json=_nt(task="leaf-b", title="oké   ‍ fine"))
        res = _next(hx)
        _check(f"{_T} AC26: control - ordinary non-ASCII (é) is printed unescaped", res.rc == 0 and "é" in res.out, res.show())
        for label, field, n, ok in (("title 2000", "title", 2000, True), ("title 2001", "title", 2001, False),
                                    ("owner 2000", "owner", 2000, True), ("owner 2001", "owner", 2001, False)):
            hx.route("next_task", json=_nt(task="leaf-b", **{field: "x" * n}))
            res = _next(hx)
            _check(f"{_T} AC26: {label} code points is {'accepted' if ok else 'malformed (exit 1)'}",
                   (res.rc == 0) == ok, res.show()[:200])
        hx.route("next_task", json=_nt(task="leaf-b", title="\U0001F600" * 2000))
        res = _next(hx)
        _check(f"{_T} AC26: the cap counts code points (2000 astral characters accepted)", res.rc == 0, res.show()[:200])
        hx.route("next_task", json=_nt(task="leaf-b", title="\U0001F600" * 2001))
        res = _next(hx)
        _check(f"{_T} AC26: 2001 astral characters are malformed", res.rc == 1, res.show()[:200])
    with _Hx() as hx:
        caps = copy.deepcopy(_fixture("capabilities")["response"])
        caps["grade"] = "g" * 2001
        hx.route("capabilities", json=caps)
        res = _next(hx)
        _check(f"{_T} AC26: a 2001-character grade is malformed (exit 1, no next_task request)",
               res.rc == 1 and "next_task" not in hx.actions(), res.show()[:200])
        caps["grade"] = "g" * 2000
        hx.route("capabilities", json=caps)
        res = _next(hx)
        _check(f"{_T} AC26: control - a 2000-character grade is accepted", res.rc == 0, res.show()[:200])
    with _Hx() as hx:
        hx.claim("leaf-b")
        kids = [{"task": "kid-1", "title": f"kid{c1}{bidi}"}]
        hx.route("complete", **_j(409, "open_children", children=kids))
        res = hx.cli("complete", "--summary", "s")
        _check(f"{_T} AC26: open_children[].title is escaped in complete's stdout",
               res.rc == 0 and _esc_ok(res.out, "009b") and _esc_ok(res.out, "202e") and c1 not in res.out and bidi not in res.out, res.show())
        hx.route("complete", **_j(409, "open_children", children=[{"task": "kid-1", "title": "k" * 2001}]))
        res = hx.cli("complete", "--summary", "s")
        _check(f"{_T} AC26: an open_children title of 2001 code points is malformed (not interpreted, exit 1)", res.rc == 1, res.show()[:200])
    with _Hx() as hx:
        ask = copy.deepcopy(_fixture("list_asks")["response"]["asks"][0])
        ask.update({"task": "project", "answer": f"an{c1}sw{bidi}er", "answered_by": f"by{c1}", "owner_answer": True})
        hx.route("list_asks", json=_la("project", asks=[ask]))
        res = hx.cli("poll")
        _check(f"{_T} AC26: poll answer text is escaped in stdout",
               res.rc == 0 and _esc_ok(res.out, "009b") and _esc_ok(res.out, "202e") and c1 not in res.out and bidi not in res.out
               and "by" not in json.dumps((res.json() or {}).get("answers")), res.show())
        ask["answered_by"] = "b" * 2001
        ask["ask_id"] = "another"
        hx.route("list_asks", json=_la("project", asks=[ask]))
        res = hx.cli("poll")
        _check(f"{_T} AC26: answered_by of 2001 code points is malformed (exit 1)", res.rc == 1, res.show()[:200])


# ---------------------------------------------------------------------------
# AC27 pendingDirect
# ---------------------------------------------------------------------------

def _msg(call: str, task: str) -> str:
    return (f"an earlier {call} for {task} has an unknown outcome; check Task&I, then run "
            f"reconcile --direct {call} --task {task} --action done|retry --evidence TEXT")


def test_r6_ac27_pending_direct() -> None:
    print(f"{_T} AC27 direct writes leave a durable record")
    for call, args in (("complete", ["complete", "--summary", "s"]), ("release", ["release", "--reason", "r"])):
        with _Hx() as hx:
            hx.claim("leaf-b")
            hx.route(call, **_j(409, "connection_unavailable"))
            res = hx.cli(*args)
            pd = (hx.state() or {}).get("pendingDirect")
            _check(f"{_T} AC27: {call} with an unknown outcome stores pendingDirect {{call, task, at}} and keeps the claim",
                   res.rc == 1 and isinstance(pd, dict) and pd.get("call") == call and pd.get("task") == "leaf-b"
                   and isinstance(pd.get("at"), int) and hx.claimed() is not None, res.show() + repr(pd))
            hx.clear()
            res = hx.cli(*args)
            _check(f"{_T} AC27: a second {call} for the same task exits 1 with the exact message and sends no request",
                   res.rc == 1 and _msg(call, "leaf-b") in res.err and hx.reqs() == [], res.show())
            res = hx.cli("reconcile", "--direct", call, "--task", "leaf-b", "--action", "retry", "--evidence", "checked in Task&I")
            _check(f"{_T} AC27: reconcile --direct {call} --action retry succeeds and clears pendingDirect",
                   res.rc == 0 and not (hx.state() or {}).get("pendingDirect"), res.show())
            hx.route(call, json=_fixture(call)["response"], echo=True)
            hx.clear()
            res = hx.cli(*args)
            _check(f"{_T} AC27: after retry one more {call} is sent and succeeds (pendingDirect stays clear)",
                   res.rc == 0 and hx.count(call) == 1 and not (hx.state() or {}).get("pendingDirect"), res.show())
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.route("complete", **_j(409, "connection_unavailable"))
        hx.cli("complete", "--summary", "s")
        res = hx.cli("reconcile", "--direct", "complete", "--task", "leaf-b", "--action", "done", "--evidence", "it was applied")
        _check(f"{_T} AC27: reconcile --direct complete --action done clears the record",
               res.rc == 0 and not (hx.state() or {}).get("pendingDirect"), res.show())
        res = hx.cli("reconcile", "--direct", "complete", "--task", "leaf-b", "--action", "done", "--evidence", "again")
        _check(f"{_T} AC27: reconcile --direct with nothing pending exits 1", res.rc == 1, res.show())
        hx.route("complete", json=_fixture("complete")["response"], echo=True)
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.route("complete", **_j(409, "connection_unavailable"))
        hx.cli("complete", "--summary", "s")
        hx.route("release", json=_fixture("release")["response"], echo=True)
        hx.clear()
        res = hx.cli("release", "--reason", "r")
        _check(f"{_T} AC27: a pending complete does not block a release of the same task (different call)",
               res.rc == 0 and hx.count("release") == 1, res.show())
    for label, spec in (("success", None), ("classified refusal (wrong_thread)", _j(409, "wrong_thread"))):
        with _Hx() as hx:
            hx.claim("leaf-b")
            if spec:
                hx.route("complete", **spec)
            res = hx.cli("complete", "--summary", "s")
            _check(f"{_T} AC27: a definite answer ({label}) leaves no pendingDirect",
                   (res.rc == 0) == (spec is None) and not (hx.state() or {}).get("pendingDirect"), res.show())
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.route("complete", json=_fixture("complete")["response"], echo=True, delayMs=2500)
        p = subprocess.Popen(["node", str(_CLIENT), "complete", "--summary", "s"], cwd=str(hx.repo), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=hx.env())
        seen = None
        for _ in range(40):
            time.sleep(0.15)
            if any((r["json"] or {}).get("action") == "complete" for r in hx.reqs()):
                seen = (hx.state() or {}).get("pendingDirect")
                break
        out, err = p.communicate(timeout=60)
        _check(f"{_T} AC27: pendingDirect is already on disk while the complete request is in flight",
               isinstance(seen, dict) and seen.get("call") == "complete" and seen.get("task") == "leaf-b", repr(seen))
        _check(f"{_T} AC27: and is cleared once it succeeds", p.returncode == 0 and not (hx.state() or {}).get("pendingDirect"), out + err)


# ---------------------------------------------------------------------------
# AC28 re-validation at dispatch
# ---------------------------------------------------------------------------

def _edit_state(hx: _Hx, fn) -> None:
    p = hx.vibe / "taskandi-outbox" / "state.json"
    s = json.loads(p.read_text())
    fn(s)
    p.write_text(json.dumps(s, indent=2) + "\n")
    os.chmod(p, 0o600)


def test_r6_ac28_tampered_jobs() -> None:
    print(f"{_T} AC28 outbox jobs are re-validated at dispatch")

    def job(s, key="tp1"):
        return next(j for j in s["jobs"] if j["key"] == key)
    tamper = [
        ("action added to payload", lambda s: job(s)["payload"].update(action="complete")),
        ("connection added to payload", lambda s: job(s)["payload"].update(connection="evil")),
        ("payload field changed", lambda s: job(s)["payload"].update(text="changed")),
        ("kind changed to record_usage", lambda s: job(s).update(kind="record_usage")),
        ("kind changed to complete", lambda s: job(s).update(kind="complete")),
        ("kind changed to an unknown value", lambda s: job(s).update(kind="capabilities")),
    ]
    for label, fn in tamper:
        with _Hx() as hx:
            hx.enqueue("comment", "tp1", {"text": "original"}, task="project")
            hx.enqueue("comment", "tp2", {"text": "second"}, task="project")
            _edit_state(hx, fn)
            hx.clear()
            res = hx.cli("flush")
            j1 = hx.job("tp1") or {}
            st = hx.cli("status").json() or {}
            keys = {(x.get("key"), x.get("code")) for x in st.get("refusedKeys", [])}
            sent = [a for a in hx.actions() if a not in ("capabilities",)]
            bad_sent = [a for a in sent if a != "comment"]
            tp1_sent = any((r["json"] or {}).get("text") in ("original", "changed") or (r["json"] or {}).get("action") in ("complete", "record_usage")
                           for r in hx.reqs())
            _check(f"{_T} AC28: {label}: job refused with tampered_job, nothing from it sent",
                   j1.get("state") == "refused" and ("tp1", "tampered_job") in keys and not tp1_sent and not bad_sent,
                   f"{res.show()} job={j1} keys={keys} actions={hx.actions()}")
            _check(f"{_T} AC28: {label}: the next untampered job still flushes (refused is not a stop)",
                   (hx.job("tp2") or {}).get("state") == "done", repr(hx.job("tp2")))
    with _Hx() as hx:
        hx.enqueue("comment", "tp1", {"text": "original"}, task="project")
        hx.clear()
        res = hx.cli("flush")
        _check(f"{_T} AC28: control - an untouched job flushes", res.rc == 0 and (hx.job("tp1") or {}).get("state") == "done", res.show())
    with _Hx() as hx:
        hx.enqueue("ask", "tp1", _fixture_payload("ask"), task="project")
        _edit_state(hx, lambda s: job(s)["payload"].update(question="swapped question"))
        hx.clear()
        res = hx.cli("flush")
        _check(f"{_T} AC28: a tampered ask payload is refused too", (hx.job("tp1") or {}).get("state") == "refused" and hx.count("ask") == 0, res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "tp1", {"text": "original"}, task="project")
        _edit_state(hx, lambda s: job(s).pop("digest"))
        hx.clear()
        res = hx.cli("flush")
        _check(f"{_T} AC28: a job without its digest is not sent", hx.count("comment") == 0, res.show())


# ---------------------------------------------------------------------------
# AC29 test seam limits
# ---------------------------------------------------------------------------

_SEAM = r'''
import { pathToFileURL } from 'node:url';
const C = await import(pathToFileURL(process.argv[2]).href);
const [cwd, host, port] = process.argv.slice(3);
const out = {};
try {
  const client = C.createClient({ cwd, httpConnect: { host, port: Number(port) } });
  out.created = true;
  await client.nextTask({ agent: 'claude', session: 'session-a' });
  out.ok = true;
} catch (e) { out.err = String(e.message ?? e); }
console.log(JSON.stringify(out));
'''


def _seam(hx: _Hx, host: str) -> dict:
    r = subprocess.run(["node", "--input-type=module", "--eval", _SEAM, "x", str(_CLIENT), str(hx.repo), host, str(hx.port)],
                       input="", capture_output=True, text=True, timeout=60, env=hx.env("0"))
    if r.returncode != 0:
        return {"__rc": r.returncode, "__err": r.stderr[-300:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_r6_ac29_seam_limits() -> None:
    print(f"{_T} AC29 httpConnect seam limits")
    with _Hx() as hx:
        out = _seam(hx, "127.0.0.1")
        _check(f"{_T} AC29: control - seam host 127.0.0.1 works", out.get("ok") is True and hx.count("next_task") == 1, repr(out))
        for host in ("10.0.0.1", "localhost", "127.0.0.2", "example.com", "host.docker.internal", "0.0.0.0", ""):
            hx.clear()
            out = _seam(hx, host)
            _check(f"{_T} AC29: seam host {host!r} is refused before any connection",
                   (out.get("ok") is not True) and hx.reqs() == [] and hx.events() == [] and "__rc" not in out, repr(out))
        hx.clear()
        out = _seam(hx, "::1")
        _check(f"{_T} AC29: seam host ::1 is accepted by the check (no seam-refusal error)",
               "__rc" not in out and out.get("created") is True, repr(out))
    with _Hx() as hx:
        hx.write_desc(origin=f"https://127.0.0.1:{hx.port}")
        hx.clear()
        out = _seam(hx, "127.0.0.1")
        _check(f"{_T} AC29: the seam is refused for an https origin (throws, listener sees no connection, no token sent)",
               out.get("ok") is not True and "__rc" not in out and hx.events() == [], repr(out))


# ---------------------------------------------------------------------------
# AC30 observable cleanups
# ---------------------------------------------------------------------------

def test_r6_ac30_observable_cleanups() -> None:
    print(f"{_T} AC30 connect-failure text and exports")
    closed = _tmp_port_closed()
    with _Hx() as hx:
        hx.write_desc(origin=f"http://127.0.0.1:{closed}")
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1", container="0")
        _check(f"{_T} AC30: connect failure outside container mode says '(on this machine)' and has no port",
               res.rc == 1 and "could not reach the Task&I service (on this machine)" in res.err and str(closed) not in res.out + res.err, res.show())
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1", container="1")
        _check(f"{_T} AC30: connect failure in container mode says '(via host.docker.internal)' and has no port",
               res.rc == 1 and "could not reach the Task&I service (via host.docker.internal)" in res.err and str(closed) not in res.out + res.err,
               res.show())
        hx.enqueue("comment", "cf1", {"text": "t"}, task="project")
        res = hx.cli("flush", container="1")
        _check(f"{_T} AC30: the flush connect-failure line has no port either; job stays queued",
               res.rc == 1 and str(closed) not in res.out + res.err and (hx.job("cf1") or {}).get("state") == "queued", res.show())
        out = hx.lib("out.t = typeof C.descriptorPresent; out.keys = Object.keys(C).filter(k => /descriptorPresent/i.test(k));")
        _check(f"{_T} AC30: descriptorPresent is no longer exported", out.get("t") == "undefined" and out.get("keys") == [], repr(out))
        out = hx.lib("out.t = typeof C.createClient + typeof C.bindingFingerprint + typeof C.loadConfig;")
        _check(f"{_T} AC30: control - createClient, bindingFingerprint and loadConfig are still exported",
               out.get("t") == "functionfunctionfunction", repr(out))
    r = subprocess.run(["node", "--input-type=module", "--eval",
                        "import {pathToFileURL as p} from 'node:url'; await import(p(process.argv[2]).href); console.log('ok');",
                        "import-probe", _SUPERVISOR.as_posix()], input="", capture_output=True, text=True, timeout=60)
    _check(f"{_T} AC30: codex-supervisor.mjs still imports", r.returncode == 0 and "ok" in r.stdout, r.stderr[-300:])


def _run_all() -> None:
    for fn in [test_r6_ac19_launcher_and_supervisor, test_r6_ac20_409_detail_fields, test_r6_ac21_tls_counts_as_not_sent,
               test_r6_ac22_unusable_id_releases_lease, test_r6_ac23_status_invalid_descriptor, test_r6_ac24_usage_one_pass,
               test_r6_ac25_origin_in_binding, test_r6_ac26_terminal_safe_stdout, test_r6_ac27_pending_direct,
               test_r6_ac28_tampered_jobs, test_r6_ac29_seam_limits, test_r6_ac30_observable_cleanups]:
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
    print("PASS: Task&I v2.2 HTTP review-finding checks (cycle 2)")
