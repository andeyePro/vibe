#!/usr/bin/env python3
"""Acceptance checks for the Task&I contract v2.2 HTTP transport (task_064), part 1.

Tester-owned (cycle 1).  Covers AC1-AC8 incl. AC5b; AC9-AC18 live in
``checks_52_taskandi_http_more.py``, which reuses the harness defined here.

Harness.  Every wire test runs the real client against a real loopback
``http.createServer`` (a Node child process).  The server logs method, url,
rawHeaders and body of every request to a JSONL file, serves a per-action
response table that the test rewrites between calls (the fixtures' ``response``
objects by default), and counts requests.  Most tests drive the real CLI
(``node taskandi-client.mjs ...``) with ``VIBE_CONTAINER=0`` and a descriptor
whose origin is the listener itself; the CLI has no connect-target seam by
design, so the container-mode rewrite (AC3) and the transport limits (AC5b) are
driven through ``createClient({cwd, httpConnect})`` in a Node harness.

Run only this module with:
    python3 smoke/checks_50_taskandi_http.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import check, FAILURES

_REPO = Path(__file__).resolve().parent.parent
_CLIENT = _REPO / "devcontainer" / "taskandi-client.mjs"
_SUPERVISOR = _REPO / "devcontainer" / "codex-supervisor.mjs"
_FIX_REPO = _REPO / "smoke" / "fixtures" / "taskandi-v22"
_FIX_BRAIN = Path("/brain2/andeye/Task&I-agent-exchange-fixtures")
_NAMES = ["capabilities", "next_task", "ask", "comment", "list_asks", "ask_status", "record_usage",
          "record_time", "complete", "release"]
_CONTRACT = "vibe-agent-exchange-v2.2"
_PROTOCOL = "taskandeye-browser-agent-v1"
_TOKEN = ("SENTINELtoken_7f3a-9c1d" + "Q" * 30)[:43]   # built, so the content guard sees no literal credential
_CONN = "conn-SENTINEL-8b1c"
_WS = "ws-SENTINEL-3c9d"
_HOSTILE = "HOSTILE-\x1b[2J-5d2e"
_T1 = 1761800000000
_DROP = object()
_RESULTS: list[bool] = []
_LEAKS: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> bool:
    _RESULTS.append(bool(cond))
    return check(name, bool(cond), detail)


def _fixture(name: str) -> dict:
    d = _FIX_REPO if (_FIX_REPO / f"{name}.json").exists() else _FIX_BRAIN   # dev fallback; AC15 requires the in-repo copy
    return json.loads((d / f"{name}.json").read_text())


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _la(task: str, now: int = _T1, asks: list | None = None) -> dict:
    return {"task": task, "now": now, "asks": asks or []}


def _canon_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


_SERVER = r'''
import http from 'node:http';
import fs from 'node:fs';
const [spec, log] = process.argv.slice(2);
const w = o => fs.appendFileSync(log, JSON.stringify(o) + '\n');
const counts = {}; let next = 0;
const server = http.createServer((req, res) => {
  const id = ++next; const chunks = [];
  req.on('data', c => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks).toString('utf8');
    let action = null; try { action = JSON.parse(body).action; } catch {}
    w({ t: 'req', id, method: req.method, url: req.url, rawHeaders: req.rawHeaders, body });
    let sent = 0;
    res.on('close', () => w({ t: 'close', id, action, sent }));
    let r = JSON.parse(fs.readFileSync(spec, 'utf8'));
    r = r[action] ?? r['*'] ?? { status: 404, raw: '' };
    if (Array.isArray(r)) { counts[action] = (counts[action] ?? 0) + 1; r = r[Math.min(counts[action], r.length) - 1]; }
    const go = () => {
      if (r.hang) return;
      if (r.claimLen) { res.writeHead(200, { 'content-type': 'application/json', 'content-length': r.claimLen }); res.write('{'); sent = 1; return; }
      if (r.flood) {
        res.writeHead(200, { 'content-type': 'application/json' });
        const chunk = Buffer.alloc(65536, 0x20);
        const pump = () => { while (sent < 64 * 1024 * 1024) { sent += chunk.length; if (!res.write(chunk)) return res.once('drain', pump); } res.end(); };
        res.write('{"pad":"'); return pump();
      }
      let j = r.json;
      if (r.echo && j && typeof j === 'object') {
        let t = null; try { t = JSON.parse(body).task; } catch {}
        if (typeof t === 'string' && 'task' in j) { j = { ...j, task: t }; if (Array.isArray(j.asks)) j.asks = j.asks.map(a => (a && 'task' in a ? { ...a, task: t } : a)); }
      }
      const payload = r.raw !== undefined ? r.raw : JSON.stringify(j);
      res.writeHead(r.status ?? 200, { 'content-type': 'application/json', ...(r.headers ?? {}) });
      res.end(payload); sent = payload.length;
    };
    r.delayMs ? setTimeout(go, r.delayMs) : go();
  });
});
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
'''

_LIB = r'''
import { pathToFileURL } from 'node:url';
const C = await import(pathToFileURL(process.argv[2]).href);
const cwd = process.argv[3];
const seam = { host: '127.0.0.1', port: Number(process.argv[4]) };
if (process.argv[5]) seam.timeoutMs = Number(process.argv[5]);
const client = C.createClient({ cwd, httpConnect: seam });
const out = {}; const t0 = Date.now();
'''


class _Res:
    def __init__(self, rc: int, out: str, err: str):
        self.rc, self.out, self.err = rc, out, err

    def json(self):
        try:
            return json.loads(self.out)
        except ValueError:
            return None

    def show(self) -> str:
        return f"rc={self.rc} stdout={self.out[:300]!r} stderr={self.err[:400]!r}"


class _Hx:
    """Throwaway git project + descriptor + loopback server."""

    def __init__(self, root="project", bound=True, token=_TOKEN):
        self._td = tempfile.TemporaryDirectory(prefix="taskandi-http-")
        self.base = Path(self._td.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, input="", capture_output=True, text=True)
        self.vibe = self.repo / ".vibe"
        self.vibe.mkdir(mode=0o700)
        self.log = self.base / "requests.jsonl"
        self.log.write_text("")
        self.spec = self.base / "routes.json"
        (self.base / "server.mjs").write_text(_SERVER)
        self.routes = {n: {"json": _fixture(n)["response"], "echo": True} for n in _NAMES}
        self.root, self.token, self.conn, self.ws = root, token, _CONN, _WS
        self.procs: list = []
        self.port = self.start_server()
        self.save_routes()
        if bound:
            self.write_desc()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for p in self.procs:
            p.kill()
            p.wait()
            p.stdout.close()
        self._td.cleanup()
        return False

    def start_server(self) -> int:
        self.spec.write_text(json.dumps(self.routes))
        p = subprocess.Popen(["node", str(self.base / "server.mjs"), str(self.spec), str(self.log)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.procs.append(p)
        return int(p.stdout.readline().strip())

    def save_routes(self) -> None:
        self.spec.write_text(json.dumps(self.routes))

    def route(self, action: str, **spec) -> None:
        self.routes[action] = spec
        self.save_routes()

    def seq(self, action: str, specs: list) -> None:
        self.routes[action] = specs
        self.save_routes()

    def write_desc(self, mode=0o600, **over) -> Path:
        d = {"protocol": _PROTOCOL, "origin": f"http://127.0.0.1:{self.port}", "connection": self.conn,
             "workspace": self.ws, "root": self.root, "token": self.token}
        for k, v in over.items():
            if v is _DROP:
                d.pop(k, None)
            else:
                d[k] = v
        path = self.vibe / "taskandi-descriptor.json"
        if path.is_symlink() or path.exists():
            path.unlink()
        path.write_text(json.dumps(d))
        os.chmod(path, mode)
        return path

    def reconnect(self, **over) -> None:
        """A new token, connection and port; same workspace and root."""
        self.port = self.start_server()
        self.token = ("RECONNECTtoken_" + "Z" * 40)[:43]
        self.conn = "conn-reconnected-2"
        self.write_desc(**over)

    # -- running ------------------------------------------------------------
    def env(self, container="0", extra: dict | None = None) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("VIBE_TASK_") and k not in ("VIBE_AGENT", "VIBE_CONTAINER")}
        env["VIBE_CONTAINER"] = container
        for k, v in (extra or {}).items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        return env

    def cli(self, *args: str, stdin="", env: dict | None = None, container="0") -> _Res:
        res = subprocess.run(["node", str(_CLIENT), *args], cwd=str(self.repo), input=stdin, capture_output=True,
                             text=True, timeout=120, env=self.env(container, env))
        blob = res.stdout + res.stderr
        for secret in (self.token, self.conn, _HOSTILE):
            if secret in blob:
                _LEAKS.append(f"{secret[:12]}... in {' '.join(args)[:60]}")
        return _Res(res.returncode, res.stdout, res.stderr)

    def lib(self, body: str, container="0", timeout_ms=None, port=None) -> dict:
        code = _LIB + body + "\nout.ms = Date.now() - t0;\nconsole.log(JSON.stringify(out));\n"
        res = subprocess.run(["node", "--input-type=module", "--eval", code, "x", str(_CLIENT), str(self.repo),
                              str(port or self.port), str(timeout_ms or "")],
                             input="", capture_output=True, text=True, timeout=90, env=self.env(container))
        if res.returncode != 0:
            return {"__rc": res.returncode, "__err": res.stderr[-400:]}
        return json.loads(res.stdout.strip().splitlines()[-1])

    # -- observation --------------------------------------------------------
    def events(self) -> list:
        return [json.loads(x) for x in self.log.read_text().splitlines() if x.strip()]

    def reqs(self) -> list:
        out = []
        for e in self.events():
            if e["t"] == "req":
                try:
                    e["json"] = json.loads(e["body"])
                except ValueError:
                    e["json"] = None
                out.append(e)
        return out

    def actions(self) -> list:
        return [(r["json"] or {}).get("action") for r in self.reqs()]

    def count(self, action: str) -> int:
        return self.actions().count(action)

    def clear(self) -> None:
        self.log.write_text("")

    def state(self):
        p = self.vibe / "taskandi-outbox" / "state.json"
        return json.loads(p.read_text()) if p.exists() else None

    def core(self) -> dict:
        s = self.state() or {}
        return {k: v for k, v in s.items() if k not in ("jobs", "reconciliationLog", "lastGrade", "pendingDirect")}   # pendingDirect: rev 6 AC27

    def jobs(self) -> list:
        return (self.state() or {}).get("jobs", [])

    def job(self, key: str):
        return next((j for j in self.jobs() if j["key"] == key), None)

    def claimed(self):
        return (self.state() or {}).get("claimed")

    # -- helpers ------------------------------------------------------------
    def claim(self, task="leaf-b", session="session-a", agent="claude") -> _Res:
        resp = copy.deepcopy(_fixture("next_task")["response"])
        resp["task"] = task
        resp["lease"]["session"] = session
        self.route("next_task", json=resp)
        res = self.cli("next-task", "--agent", agent, "--session", session)
        self.clear()
        return res

    def enqueue(self, kind: str, key: str, payload: dict, task: str | None = None, env: dict | None = None) -> _Res:
        args = ["enqueue", kind, "--key", key] + (["--task", task] if task else [])
        return self.cli(*args, stdin=json.dumps(payload), env=env)


def _fixture_payload(name: str) -> dict:
    req = {k: v for k, v in _fixture(name)["request"].items() if k not in ("action", "task", "session", "agent")}
    return req


def _expected(name: str, **over) -> dict:
    body = copy.deepcopy(_fixture(name)["request"])
    if "agent" in body:
        body["agent"] = "claude"
    body["connection"] = _CONN
    for k, v in over.items():
        if v is _DROP:
            body.pop(k, None)
        else:
            body[k] = v
    return body


def _cur(hx: "_Hx") -> tuple:
    s = hx.state() or {}
    return (s.get("cursors"), s.get("answers"), s.get("claimed"), s.get("conflicts"))


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


# ---------------------------------------------------------------------------
# AC1 Descriptor
# ---------------------------------------------------------------------------

def _git_add(hx: _Hx, rel: str) -> None:
    subprocess.run(["git", "-C", str(hx.repo), "add", "-f", rel], check=True, input="", capture_output=True, text=True)


def _break_hardlink(hx: _Hx) -> None:
    os.link(hx.vibe / "taskandi-descriptor.json", hx.base / "second-link")


def _break_symlink(hx: _Hx) -> None:
    real = hx.base / "real-descriptor.json"
    (hx.vibe / "taskandi-descriptor.json").rename(real)
    (hx.vibe / "taskandi-descriptor.json").symlink_to(real)


def _break_tracked(hx: _Hx) -> None:
    _git_add(hx, ".vibe/taskandi-descriptor.json")


def _break_tracked_upper(hx: _Hx) -> None:
    d = hx.repo / ".VIBE"
    d.mkdir()
    (d / "TASKANDI-DESCRIPTOR.JSON").write_text("{}")
    _git_add(hx, ".VIBE/TASKANDI-DESCRIPTOR.JSON")


def _break_big(hx: _Hx) -> None:
    p = hx.vibe / "taskandi-descriptor.json"
    p.write_text(p.read_text() + " " * 33000)
    os.chmod(p, 0o600)


def _break_vibe_symlink(hx: _Hx) -> None:
    (hx.repo / ".vibe").rename(hx.repo / ".vibe-real")
    (hx.repo / ".vibe").symlink_to(hx.repo / ".vibe-real")


def _break_both(hx: _Hx) -> None:
    (hx.vibe / "taskandi.json").write_text(json.dumps({"endpoint": "https://fixture.invalid/mcp", "task": "ABBR-1"}))


def test_taskandi_http_ac1_descriptor() -> None:
    """AC1.  Positive controls first: a valid descriptor and a root:null one load.  If the
    refusals were not specific, the control would still pass while every refusal check
    (rc 1 + message naming the rule + zero requests) would flag the gap."""
    print("[taskandi-http] AC1 descriptor validation")
    with _Hx() as hx:
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1")
        _check("[taskandi-http] AC1: control - a valid descriptor drives next-task (2 requests)",
               res.rc == 0 and hx.actions() == ["capabilities", "next_task"], res.show())
        out = hx.lib("out.task = C.loadConfig(cwd).task;")
        _check("[taskandi-http] AC1: control - loadConfig task = root", out.get("task") == "project", repr(out))
    with _Hx(root=None) as hx:
        out = hx.lib("out.task = C.loadConfig(cwd).task; out.isNull = C.loadConfig(cwd).task === null;")
        _check("[taskandi-http] AC1: control - root:null loads with task null", out.get("isNull") is True, repr(out))
        res = hx.cli("status")
        _check("[taskandi-http] AC1: control - status works under root:null",
               res.rc == 0 and (res.json() or {}).get("channel") == "taskandi-http", res.show())

    tok = _TOKEN
    cases = [
        ("wrong protocol", dict(protocol="other"), None, r"protocol"),
        ("missing key", dict(token=_DROP), None, r"token|key|missing"),
        ("extra key", dict(extra="x"), None, r"extra|unknown|key"),
        ("token 42 chars", dict(token=tok[:42]), None, r"token"),
        ("token 44 chars", dict(token=tok + "Q"), None, r"token"),
        ("token with +", dict(token=tok[:42] + "+"), None, r"token"),
        ("origin trailing slash", dict(origin="http://127.0.0.1:5/"), None, r"origin"),
        ("origin path", dict(origin="http://127.0.0.1:5/x"), None, r"origin"),
        ("origin query", dict(origin="http://127.0.0.1:5?x=1"), None, r"origin"),
        ("origin fragment", dict(origin="http://127.0.0.1:5#x"), None, r"origin"),
        ("origin userinfo", dict(origin="http://u:p@127.0.0.1:5"), None, r"origin"),
        ("origin localhost", dict(origin="http://localhost:1"), None, r"origin"),
        ("origin ipv6", dict(origin="http://[::1]:1"), None, r"origin"),
        ("origin other http host", dict(origin="http://10.0.0.1:1"), None, r"origin"),
        ("origin no port", dict(origin="http://127.0.0.1"), None, r"origin"),
        ("origin port 0", dict(origin="http://127.0.0.1:0"), None, r"origin"),
        ("origin port 65536", dict(origin="http://127.0.0.1:65536"), None, r"origin"),
        ("origin port 01234", dict(origin="http://127.0.0.1:01234"), None, r"origin"),
        ("connection empty", dict(connection=""), None, r"connection"),
        ("connection 201", dict(connection="a" * 201), None, r"connection"),
        ("workspace empty", dict(workspace=""), None, r"workspace"),
        ("workspace 201", dict(workspace="a" * 201), None, r"workspace"),
        ("root empty string", dict(root=""), None, r"root"),
        ("root with space", dict(root="a b"), None, r"root"),
        ("mode 0644", dict(mode=0o644), None, r"chmod 600 \.vibe/taskandi-descriptor\.json"),
        ("hard link (nlink 2)", {}, _break_hardlink, r"link|regular"),
        ("symlink", {}, _break_symlink, r"symlink|regular"),
        ("tracked by git", {}, _break_tracked, r"track"),
        ("tracked, case-insensitive", {}, _break_tracked_upper, r"track"),
        ("over 32 KiB", {}, _break_big, r"32|exceed|large|bytes"),
        (".vibe is a symlink", {}, _break_vibe_symlink, r"symlink|\.vibe"),
        ("both binding files", {}, _break_both, r"two Task&I bindings; keep one"),
    ]
    for label, over, breaker, pattern in cases:
        with _Hx() as hx:
            hx.write_desc(**over)
            if breaker:
                breaker(hx)
            res = hx.cli("next-task", "--agent", "claude", "--session", "s1")
            _check(f"[taskandi-http] AC1: {label} -> exit 1, rule named, zero requests, no fallback",
                   res.rc == 1 and re.search(pattern, res.err, re.I) is not None and res.out == ""
                   and hx.reqs() == [], res.show())


# ---------------------------------------------------------------------------
# AC2 Wire per fixture
# ---------------------------------------------------------------------------

def _wire_case(name: str) -> None:
    label = f"[taskandi-http] AC2 {name}"
    with _Hx() as hx:
        if name == "capabilities":
            res = hx.cli("next-task", "--agent", "claude", "--session", "session-a")
            first = hx.reqs()[0] if hx.reqs() else {}
            _check(f"{label}: capabilities is a POST /api/browser-agent with exactly action+connection",
                   res.rc == 0 and first.get("method") == "POST" and first.get("url") == "/api/browser-agent"
                   and first.get("json") == {"action": "capabilities", "connection": _CONN}, res.show() + repr(first)[:200])
            _check(f"{label}: grade 'comment' is stored as lastGrade in state.json",
                   _find_key(hx.state(), "lastGrade") == "comment", repr(hx.state())[:300])
        elif name == "next_task":
            res = hx.cli("next-task", "--agent", "claude", "--session", "session-a")
            bodies = [r["json"] for r in hx.reqs()]
            want = {"action": "next_task", "agent": "claude", "session": "session-a", "connection": _CONN}
            _check(f"{label}: body equals fixture request (agent/session substituted), no task key",
                   len(bodies) == 2 and bodies[1] == want and "task" not in bodies[1], repr(bodies))
            _check(f"{label}: stdout is the printed-output table row",
                   res.json() == {"bound": True, "channel": "taskandi-http", "task": _fixture("next_task")["response"]}, res.show())
        elif name in ("ask", "list_asks", "ask_status"):
            hx.claim("project")
            if name == "ask":
                r1 = hx.enqueue("ask", "k-ask", _fixture_payload("ask"), task="project")
                hx.clear()
                res = hx.cli("flush")
                bodies = [r["json"] for r in hx.reqs()]
                _check(f"{label}: enqueue accepted", r1.rc == 0, r1.show())
                _check(f"{label}: flush sends capabilities then ask; body equals fixture request",
                       hx.actions() == ["capabilities", "ask"] and bodies[1] == _expected("ask"), repr(bodies)[:500])
                _check(f"{label}: body key set is the table's set (no in_reply_to when unset)",
                       set(bodies[1]) == {"action", "connection", "task", "question", "default", "options", "order",
                                          "estimate_minutes", "remaining_minutes", "reversible", "blocking", "agent", "session"},
                       repr(sorted(bodies[1])))
                job = hx.job("k-ask") or {}
                ask_id = _fixture("ask")["response"]["ask_id"]
                _check(f"{label}: job done and its stored result carries the server's ask_id",
                       job.get("state") == "done" and ask_id in json.dumps(job), repr(job)[:300])
            elif name == "list_asks":
                res = hx.cli("poll")
                bodies = [r["json"] for r in hx.reqs()]
                _check(f"{label}: poll sends capabilities then list_asks; body equals fixture request",
                       hx.actions() == ["capabilities", "list_asks"] and bodies[1] == _expected("list_asks"), repr(bodies))
                a = _fixture("list_asks")["response"]["asks"][0]
                want = {"bound": True, "channel": "taskandi-http", "task": "project", "newAnswers": 1,
                        "answers": [{"ask_id": a["ask_id"], "answer": a["answer"], "seen_at": a["seen_at"],
                                     "answered_at": a["answered_at"]}], "ignored": 0, "conflicts": [], "cursor": {"now": _T1}}
                _check(f"{label}: stdout deep-equals the printed-output table row", res.json() == want, res.show())
            else:
                res = hx.cli("ask-status")
                bodies = [r["json"] for r in hx.reqs()]
                _check(f"{label}: ask-status sends capabilities then ask_status; body equals fixture request",
                       hx.actions() == ["capabilities", "ask_status"] and bodies[1] == _expected("ask_status"), repr(bodies))
                want = {"bound": True, "channel": "taskandi-http", "task": "project", "asks": _fixture("ask_status")["response"]["asks"]}
                _check(f"{label}: stdout deep-equals the printed-output table row", res.json() == want, res.show())
        elif name in ("comment", "record_usage", "record_time"):
            hx.claim("leaf-b")
            payload = _fixture_payload(name)
            key = "session-a" if name == "record_usage" else f"k-{name}"
            if name == "record_usage":
                payload = {k: v for k, v in payload.items() if k not in ("windows", "source", "source_ref")}
            if name == "record_time":
                payload["started_at"] = _iso(payload["started_at"])
            r1 = hx.enqueue(name, key, payload, task="leaf-b")
            hx.clear()
            res = hx.cli("flush")
            bodies = [r["json"] for r in hx.reqs()]
            _check(f"{label}: enqueue accepted and flush sends capabilities then {name}",
                   r1.rc == 0 and hx.actions() == ["capabilities", name], r1.show() + repr(hx.actions()))
            _check(f"{label}: body equals fixture request (agent/session substituted) + connection",
                   len(bodies) == 2 and bodies[1] == _expected(name), repr(bodies[1:])[:500])
            if name == "comment":
                _check(f"{label}: comment carries agent claude", bodies[1].get("agent") == "claude", repr(bodies[1]))
            _check(f"{label}: job done", (hx.job(key) or {}).get("state") == "done", repr(hx.job(key)))
        else:
            hx.claim("leaf-b")
            if name == "complete":
                res = hx.cli("complete", "--task", "leaf-b", "--summary", _fixture("complete")["request"]["summary"])
                want_out = {"bound": True, "completed": True, "state": "provisional",
                            "completion_id": _fixture("complete")["response"]["completion_id"]}
            else:
                res = hx.cli("release", "--task", "leaf-b", "--reason", _fixture("release")["request"]["reason"])
                want_out = {"bound": True, "released": True, "comment_id": _fixture("release")["response"]["comment_id"]}
            bodies = [r["json"] for r in hx.reqs()]
            _check(f"{label}: sends capabilities then {name}; body equals fixture request",
                   hx.actions() == ["capabilities", name] and bodies[1] == _expected(name), repr(bodies))
            if name == "complete":
                _check(f"{label}: complete has no agent key", "agent" not in bodies[1], repr(bodies[1]))
            _check(f"{label}: stdout deep-equals the printed-output table row", res.json() == want_out, res.show())


def test_taskandi_http_ac2_wire_per_fixture() -> None:
    """AC2.  Observable control: the server logs show the exact body for each of the ten fixtures; if the
    client sent nothing or the wrong shape the key-set and equality checks fail."""
    print("[taskandi-http] AC2 wire per fixture")
    for name in _NAMES:
        _wire_case(name)


# ---------------------------------------------------------------------------
# AC3 Host, headers, error statuses, source
# ---------------------------------------------------------------------------

_FORBIDDEN_HEADERS = re.compile(r"^(origin|cookie|referer|user-agent|accept.*|sec-fetch-.*)$", re.I)


def test_taskandi_http_ac3_host_and_headers() -> None:
    """AC3.  Container mode: Host is rewritten to the descriptor's 127.0.0.1:<P> while the socket goes to the seam
    listener on another port; if the client sent Node's default Host the check on req.headers.host fails."""
    print("[taskandi-http] AC3 host and headers")
    P = 39123
    with _Hx() as hx:
        hx.write_desc(origin=f"http://127.0.0.1:{P}")
        out = hx.lib("try { out.r = await client.nextTask({ agent: 'claude', session: 'session-a' }); } catch (e) { out.err = e.message; }",
                     container="1")
        reqs = hx.reqs()
        _check("[taskandi-http] AC3: container mode reaches the seam listener (control)",
               "err" not in out and len(reqs) == 2, repr(out)[:300])
        for r in reqs:
            raw = r["rawHeaders"]
            names = {n.lower() for n in raw[0::2]}
            hdr = {raw[i].lower(): raw[i + 1] for i in range(0, len(raw), 2)}
            _check("[taskandi-http] AC3: Host is 127.0.0.1:<descriptor port>, not the listener port",
                   hdr.get("host") == f"127.0.0.1:{P}" and str(hx.port) not in hdr.get("host", ""), repr(raw))
            _check("[taskandi-http] AC3: raw header names are exactly the five allowed",
                   names == {"host", "content-type", "authorization", "content-length", "connection"}, repr(sorted(names)))
            _check("[taskandi-http] AC3: bearer token, JSON content type, content-length matches, connection close",
                   hdr.get("authorization") == f"Bearer {_TOKEN}" and hdr.get("content-type") == "application/json"
                   and hdr.get("content-length") == str(len(r["body"].encode())) and hdr.get("connection") == "close"
                   and r["method"] == "POST" and r["url"] == "/api/browser-agent", repr(raw))
    with _Hx() as hx:
        res = hx.cli("next-task", "--agent", "claude", "--session", "session-a", container="0")
        reqs = hx.reqs()
        ok = res.rc == 0 and len(reqs) == 2
        _check("[taskandi-http] AC3: container mode off connects straight to 127.0.0.1:<port> (control)", ok, res.show())
        for r in reqs:
            raw = r["rawHeaders"]
            hdr = {raw[i].lower(): raw[i + 1] for i in range(0, len(raw), 2)}
            names = set(hdr)
            _check("[taskandi-http] AC3: off mode Host is 127.0.0.1:<listener port>; no forbidden headers",
                   hdr.get("host") == f"127.0.0.1:{hx.port}" and not any(_FORBIDDEN_HEADERS.match(n) for n in names)
                   and {"host", "content-type", "authorization", "content-length"} <= names, repr(raw))


def test_taskandi_http_ac3_status_refusals_and_source() -> None:
    """AC3.  421, 403 and 302 on capabilities: one request each, exit 1, the code (or 'redirect') named."""
    print("[taskandi-http] AC3 421/403/302 and source check")
    cases = [("421 wrong_origin", {"status": 421, "json": {"error": "wrong_origin"}}, "wrong_origin"),
             ("403 connection_scope", {"status": 403, "json": {"error": "connection_scope"}}, "connection_scope"),
             ("302 redirect", {"status": 302, "raw": "", "headers": {"location": "http://127.0.0.1:1/elsewhere"}}, "redirect")]
    for label, spec, word in cases:
        with _Hx() as hx:
            ok = hx.cli("next-task", "--agent", "claude", "--session", "s1")
            hx.clear()
            hx.route("capabilities", **spec)
            res = hx.cli("next-task", "--agent", "claude", "--session", "s1")
            _check(f"[taskandi-http] AC3: control - the default route works", ok.rc == 0, ok.show())
            _check(f"[taskandi-http] AC3: {label} -> exactly one request, exit 1, stderr names it",
                   res.rc == 1 and len(hx.reqs()) == 1 and word in res.err, res.show() + str(len(hx.reqs())))
    src = _CLIENT.read_text()
    m = re.search(r"(?:async\s+)?function\s+httpTransport\b", src) or re.search(r"\bhttpTransport\s*=", src)
    _check("[taskandi-http] AC3: source has an httpTransport on node:http", m is not None and "node:http" in src, "")
    if m:
        i = src.index("{", m.end())
        depth, j = 0, i
        while j < len(src):
            depth += {"{": 1, "}": -1}.get(src[j], 0)
            j += 1
            if depth == 0:
                break
        body = src[m.start():j]
        _check("[taskandi-http] AC3: httpTransport does not call fetch( and does not read process.env",
               "fetch(" not in body and "process.env" not in body, body[:200])
    _check("[taskandi-http] AC3: no connect host/port is ever assigned from process.env",
           re.search(r"(host|hostname|port)\s*[:=][^;\n]*process\.env", src) is None, "")


# ---------------------------------------------------------------------------
# AC4 Errors
# ---------------------------------------------------------------------------

def _j(status, code, **extra):
    return {"status": status, "json": {"error": code, **extra}}


_UNKNOWN = [
    ("connection_unavailable", _j(409, "connection_unavailable")), ("connection_revoked", _j(409, "connection_revoked")),
    ("connection_changed", _j(409, "connection_changed")), ("descriptor_origin_changed", _j(409, "descriptor_origin_changed")),
    ("ask_answered", _j(409, "ask_answered")), ("unlisted code", _j(409, "made_up_code")),
    ("500 JSON", _j(500, "boom")), ("500 non-JSON", {"status": 500, "raw": "<html>oops</html>"}),
    ("200 non-JSON", {"status": 200, "raw": "not json"}), ("404", {"status": 404, "raw": ""}),
    ("400 other body", _j(400, "nope")), ("403 other body", {"status": 403, "json": {"foo": 1}}),
    ("421 other body", _j(421, "nope")), ("409 without error key", {"status": 409, "json": {}}),
    ("200 extra key", {"json": {"task": "project", "comment_id": "c-1", "extra": 1}}),
]
_LATER = [("stale_context", _j(409, "stale_context")), ("sync_required", _j(409, "sync_required")),
          ("lease_held", _j(409, "lease_held")), ("wrong_origin", _j(421, "wrong_origin")),
          ("connection_scope", _j(403, "connection_scope"))]
_REJECT = [("use_native_connection", _j(409, "use_native_connection")), ("scope_missing", _j(409, "scope_missing")),
           ("invalid_request", _j(409, "invalid_request")), ("invalid_request (400)", _j(400, "invalid_request")),
           ("wrong_scope", _j(409, "wrong_scope")), ("wrong_thread", _j(409, "wrong_thread")),
           ("unknown_ask", _j(409, "unknown_ask")), ("not_assigned", _j(409, "not_assigned")),
           ("receipt_collision", _j(409, "receipt_collision"))]
_REVOKED = ("taskandi-client: the Task&I connection was revoked or replaced; copy a fresh descriptor "
            "(More → Connect Codex) into .vibe/taskandi-descriptor.json")


def _code_of(label: str) -> str:
    return label.split(" ")[0]


def test_taskandi_http_ac4_flush_job_states() -> None:
    """AC4 (flush).  Two queued comments; the comment route answers per case.  Request counts prove flush stops
    (1 comment request) or continues (2); job states follow the table; claim/cursors in state.json are unchanged."""
    print("[taskandi-http] AC4 flush job states")
    groups = [("unknown", _UNKNOWN, "uncertain", 1), ("later", _LATER, "queued", 1), ("rejected", _REJECT, "refused", 2)]
    for klass, rows, want_state, want_reqs in groups:
        for label, spec in rows:
            with _Hx() as hx:
                hx.enqueue("comment", "e1", {"text": "first"}, task="project")
                hx.enqueue("comment", "e2", {"text": "second"}, task="project")
                hx.route("comment", **spec)
                before = hx.core()
                res = hx.cli("flush")
                e1, e2 = hx.job("e1") or {}, hx.job("e2") or {}
                s2 = {"uncertain": "queued", "queued": "queued", "refused": "refused"}[want_state]
                _check(f"[taskandi-http] AC4: [{klass}] {label}: e1 {want_state}, e2 {s2}, {want_reqs} comment request(s)",
                       e1.get("state") == want_state and e2.get("state") == s2 and hx.count("comment") == want_reqs,
                       f"{e1.get('state')}/{e2.get('state')} reqs={hx.count('comment')} {res.show()}")
                _check(f"[taskandi-http] AC4: [{klass}] {label}: claim and cursors unchanged, no hostile text leaked",
                       hx.core() == before and "\x1b" not in res.out + res.err, res.show())
                if klass == "later":
                    _check(f"[taskandi-http] AC4: [later] {label}: lastError records the code",
                           _code_of(label) in str(e1.get("lastError", "")), repr(e1))
                if klass == "unknown":
                    _check(f"[taskandi-http] AC4: [unknown] {label}: lastError is set",
                           bool(e1.get("lastError")), repr(e1))
                if klass == "rejected":
                    st = hx.cli("status").json() or {}
                    keys = {(x.get("key"), x.get("code")) for x in st.get("refusedKeys", [])}
                    want_code = _code_of(label)
                    _check(f"[taskandi-http] AC4: [rejected] {label}: status counts refused and lists key+code",
                           st.get("counts", {}).get("refused") == 2 and ("e1", want_code) in keys, repr(st)[:400])


def test_taskandi_http_ac4_direct_and_extras() -> None:
    """AC4 (direct commands, revoked, hostile code, open_children, reconcile)."""
    print("[taskandi-http] AC4 direct commands and extras")
    for klass, rows in (("unknown", _UNKNOWN[:14]), ("later", _LATER), ("rejected", _REJECT)):
        for label, spec in rows:
            with _Hx() as hx:
                hx.claim("leaf-b")
                before = hx.core()
                hx.route("complete", **spec)
                res = hx.cli("complete", "--task", "leaf-b", "--summary", "s")
                code = _code_of(label)
                if klass == "unknown":
                    ok = "outcome unknown; check the task in Task&I" in res.err
                elif klass == "later":
                    ok = f"Task&I refused for now: {code}" in res.err
                else:
                    ok = f"Task&I refused: {code}" in res.err
                _check(f"[taskandi-http] AC4: direct complete [{klass}] {label}: exit 1, class line, claim kept",
                       res.rc == 1 and ok and hx.core() == before and (hx.claimed() or {}).get("task") == "leaf-b"
                       and "\x1b" not in res.err, res.show())
    with _Hx() as hx:
        hx.claim("leaf-b")
        hx.route("complete", **_j(409, "connection_revoked"))
        res = hx.cli("complete", "--task", "leaf-b", "--summary", "s")
        i, k = res.err.find(_REVOKED), res.err.find("outcome unknown; check the task in Task&I")
        _check("[taskandi-http] AC4: direct complete + connection_revoked prints the revoked line, then outcome unknown, keeps the claim",
               res.rc == 1 and i >= 0 and k > i and (hx.claimed() or {}).get("task") == "leaf-b", res.show())
        hx.route("release", **_j(409, "connection_revoked"))
        res = hx.cli("release", "--task", "leaf-b", "--reason", "r")
        _check("[taskandi-http] AC4: direct release + connection_revoked behaves the same",
               res.rc == 1 and _REVOKED in res.err and "outcome unknown; check the task in Task&I" in res.err
               and (hx.claimed() or {}).get("task") == "leaf-b", res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "r1", {"text": "one"}, task="project")
        hx.route("comment", **_j(409, "connection_revoked"))
        res = hx.cli("flush")
        n = hx.count("comment")
        res2 = hx.cli("flush")
        _check("[taskandi-http] AC4: flush + connection_revoked prints the exact message; job uncertain; request counter shows no retry",
               _REVOKED in res.err and (hx.job("r1") or {}).get("state") == "uncertain" and n == 1
               and hx.count("comment") == 1, res.show())
        _check("[taskandi-http] AC4: a second flush with nothing queued sends no further request",
               res2.rc == 0 and hx.count("comment") == 1 and hx.count("capabilities") == 1, res2.show())
    with _Hx() as hx:
        hx.claim("leaf-b")
        for cmd, action in (("complete", "complete"), ("release", "release")):
            hx.route(action, **_j(409, "x\x1b[2J"))
            args = ("complete", "--task", "leaf-b", "--summary", "s") if cmd == "complete" else ("release", "--task", "leaf-b", "--reason", "r")
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC4: a 409 code with an escape sequence prints unknown_error ({cmd})",
                   res.rc == 1 and "unknown_error" in res.err and "\x1b" not in res.err, res.show())
    with _Hx() as hx:
        hx.claim("leaf-b")
        kids = [{"task": "leaf-c", "title": "Child task"}]
        hx.route("complete", **_j(409, "open_children", children=kids))
        res = hx.cli("complete", "--task", "leaf-b", "--summary", "s")
        _check("[taskandi-http] AC4: open_children on complete -> exit 0, completed:false with the children, claim kept",
               res.rc == 0 and res.json() == {"bound": True, "completed": False, "open_children": kids}
               and (hx.claimed() or {}).get("task") == "leaf-b", res.show())
        hx.route("complete", **_j(409, "open_children", children=[]))
        res = hx.cli("complete", "--task", "leaf-b", "--summary", "s")
        _check("[taskandi-http] AC4: open_children with an empty children list is not exactly formed -> outcome unknown",
               res.rc == 1 and "outcome unknown" in res.err, res.show())
    with _Hx() as hx:
        for k in ("m1", "m2"):
            hx.enqueue("comment", k, {"text": k}, task="project")
        hx.route("comment", **_j(409, "wrong_scope"))
        hx.cli("flush")
        res = hx.cli("reconcile", "--key", "m1", "--action", "done", "--evidence", "x")
        _check("[taskandi-http] AC4: reconcile --action done on a refused job exits 1 and leaves it refused",
               res.rc == 1 and (hx.job("m1") or {}).get("state") == "refused", res.show())
        res = hx.cli("reconcile", "--key", "m1", "--action", "retry", "--evidence", "checked in Task&I")
        _check("[taskandi-http] AC4: reconcile --action retry requeues a refused job",
               res.rc == 0 and (hx.job("m1") or {}).get("state") == "queued" and (hx.job("m2") or {}).get("state") == "refused", res.show())
        hx.route("comment", json={"task": "project", "comment_id": "c-9"})
        res = hx.cli("flush")
        out = res.json() or {}
        _check("[taskandi-http] AC4: the requeued job delivers; flush reports refused and requeued counts",
               (hx.job("m1") or {}).get("state") == "done" and "refused" in out and "requeued" in out, res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "u1", {"text": "x"}, task="project")
        hx.route("comment", **_j(409, "connection_unavailable"))
        hx.cli("flush")
        res = hx.cli("reconcile", "--key", "u1", "--action", "retry", "--evidence", "x")
        _check("[taskandi-http] AC4: control - reconcile retry still works on an uncertain job",
               res.rc == 0 and (hx.job("u1") or {}).get("state") == "queued", res.show())


# ---------------------------------------------------------------------------
# AC5 Capabilities gate
# ---------------------------------------------------------------------------

def _caps(**over):
    c = copy.deepcopy(_fixture("capabilities")["response"])
    for k, v in over.items():
        if v is _DROP:
            c.pop(k, None)
        else:
            c[k] = v
    return c


def test_taskandi_http_ac5_capabilities_gate() -> None:
    print("[taskandi-http] AC5 capabilities gate")
    with _Hx() as hx:
        res = hx.cli("flush")
        _check("[taskandi-http] AC5: flush with nothing queued sends no request", res.rc == 0 and hx.reqs() == [], res.show())
        hx.cli("status")
        hx.cli("reconcile", "--key", "nokey", "--action", "retry", "--evidence", "x")
        _check("[taskandi-http] AC5: status and reconcile send nothing", hx.reqs() == [], repr(hx.actions()))
    with _Hx(bound=False) as hx:
        outs = [hx.cli(*a) for a in (["flush"], ["poll"], ["next-task", "--agent", "claude", "--session", "s1"], ["status"])]
        _check("[taskandi-http] AC5: an unbound project sends nothing", hx.reqs() == [] and all(o.rc == 0 for o in outs),
               " ".join(o.show() for o in outs))
    with _Hx() as hx:
        hx.claim("leaf-b")
        for k, kind, pay in (("a1", "ask", _fixture_payload("ask")), ("c1", "comment", {"text": "t"})):
            hx.enqueue(kind, k, pay, task="project")
        for args, action in ((["next-task", "--agent", "claude", "--session", "session-a"], "next_task"), (["poll"], "list_asks"),
                             (["ask-status"], "ask_status"), (["flush"], "ask"),
                             (["complete", "--summary", "s"], "complete"), (["release", "--reason", "r"], "release")):
            hx.clear()
            hx.cli(*args)
            acts = hx.actions()
            _check(f"[taskandi-http] AC5: `{args[0]}` sends exactly one capabilities request, first",
                   acts[:1] == ["capabilities"] and acts.count("capabilities") == 1, repr(acts))
            hx.claim("leaf-b")
            hx.route("ask", json=_fixture("ask")["response"])
    base = [("contract v2.1", _caps(contract="vibe-agent-exchange-v2.1")), ("other protocol", _caps(protocol="other-protocol")),
            ("extra key", {**_caps(), "extra": 1}), ("missing grade key", _caps(grade=_DROP)),
            ("missing calls key", _caps(calls=_DROP)), ("calls not a list", _caps(calls="all"))]
    for label, caps in base:
        with _Hx() as hx:
            hx.enqueue("comment", "g1", {"text": "t"}, task="project")
            hx.route("capabilities", json=caps)
            for args in (["next-task", "--agent", "claude", "--session", "s1"], ["flush"]):
                hx.clear()
                res = hx.cli(*args)
                _check(f"[taskandi-http] AC5: {label} -> `{args[0]}` exits 1 after one request; job stays queued; no claim",
                       res.rc == 1 and hx.actions() == ["capabilities"] and (hx.job("g1") or {}).get("state") == "queued"
                       and hx.claimed() is None, res.show() + repr(hx.actions()))
    needs = {"next-task": "next_task", "poll": "list_asks", "ask-status": "ask_status", "complete": "complete", "release": "release"}
    for cmd, call in needs.items():
        with _Hx() as hx:
            hx.claim("leaf-b")
            args = {"next-task": ["next-task", "--agent", "claude", "--session", "session-a"], "poll": ["poll"],
                    "ask-status": ["ask-status"], "complete": ["complete", "--summary", "s"], "release": ["release", "--reason", "r"]}[cmd]
            hx.route("capabilities", json=_caps(calls=[c for c in _caps()["calls"] if c != call]))
            hx.route("list_asks", json=_la("leaf-b"))
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC5: calls missing {call} -> `{cmd}` exits 1 after the capabilities request only",
                   res.rc == 1 and hx.actions() == ["capabilities"], res.show() + repr(hx.actions()))
            hx.clear()
            hx.route("capabilities", json=_caps(calls=["capabilities", call]))
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC5: control - calls listing only {call} lets `{cmd}` through",
                   res.rc == 0 and hx.actions() == ["capabilities", call], res.show() + repr(hx.actions()))
    kinds = {"ask": _fixture_payload("ask"), "comment": {"text": "t"},
             "record_usage": {k: v for k, v in _fixture_payload("record_usage").items() if k not in ("windows", "source", "source_ref")},
             "record_time": {"seconds": 5, "started_at": _iso(int(time.time() * 1000) - 600000)}}
    for kind, pay in kinds.items():
        with _Hx() as hx:
            hx.enqueue(kind, "q1", pay, task="project")
            hx.route("capabilities", json=_caps(calls=[c for c in _caps()["calls"] if c != kind]))
            res = hx.cli("flush")
            _check(f"[taskandi-http] AC5: flush with queued {kind} and calls missing {kind} exits 1, job stays queued, one request",
                   res.rc == 1 and (hx.job("q1") or {}).get("state") == "queued" and hx.actions() == ["capabilities"], res.show())
            hx.route("capabilities", json=_caps(calls=["capabilities", kind]))
            res = hx.cli("flush")
            _check(f"[taskandi-http] AC5: control - calls listing only {kind} lets flush deliver it",
                   res.rc == 0 and (hx.job("q1") or {}).get("state") == "done", res.show())


# ---------------------------------------------------------------------------
# AC5b Transport limits
# ---------------------------------------------------------------------------

_MIB = 1024 * 1024
_NEXT = "try { out.r = await client.nextTask({ agent: 'claude', session: 'session-a' }); } catch (e) { out.err = e.message; }"


def test_taskandi_http_ac5b_transport_limits() -> None:
    print("[taskandi-http] AC5b transport limits")
    with _Hx() as hx:
        big = copy.deepcopy(_fixture("next_task")["response"])
        big["body"] = "x" * int(1.5 * _MIB)
        hx.route("next_task", json=big)
        out = hx.lib(_NEXT, timeout_ms=20000)
        _check("[taskandi-http] AC5b: control - a 1.5 MiB valid body is accepted", "err" not in out and "__rc" not in out, repr(out)[:300])
    with _Hx() as hx:
        hx.route("capabilities", claimLen=16 * _MIB + 1)
        out = hx.lib(_NEXT, timeout_ms=30000)
        closes = [e for e in hx.events() if e["t"] == "close"]
        _check("[taskandi-http] AC5b: content-length 16 MiB + 1 is refused at once (no wait for the body, far below the timeout)",
               "err" in out and out.get("ms", 99999) < 5000 and hx.actions() == ["capabilities"] and closes, repr(out)[:300])
    with _Hx() as hx:
        hx.route("capabilities", flood=True)
        out = hx.lib(_NEXT, timeout_ms=30000)
        sent = max([e["sent"] for e in hx.events() if e["t"] == "close"] or [0])
        _check("[taskandi-http] AC5b: a body growing past 16 MiB without a length is cut off (client destroys the connection)",
               "err" in out and 16 * _MIB <= sent < 48 * _MIB, f"{out!r:.300} sent={sent}")
    with _Hx() as hx:
        hx.route("capabilities", hang=True)
        out = hx.lib(_NEXT, timeout_ms=500)
        _check("[taskandi-http] AC5b: a silent server is abandoned after httpConnect.timeoutMs (500)",
               "err" in out and 400 <= out.get("ms", 0) < 6000, repr(out)[:300])


# ---------------------------------------------------------------------------
# AC6 Task ids
# ---------------------------------------------------------------------------

def test_taskandi_http_ac6_task_ids() -> None:
    print("[taskandi-http] AC6 task ids")
    uuid_mixed = "0F7F8F0E-6c4b-4C62-9d4c-1B2F3A4D5E6F"
    with _Hx(root=None) as hx:
        for ref, sent in (("leaf-b", "leaf-b"), ("project", "project"), (uuid_mixed, uuid_mixed.lower()),
                          ("taskandeye://node/leaf-b", "leaf-b")):
            hx.route("list_asks", json=_la(sent))
            hx.clear()
            res = hx.cli("poll", "--task", ref)
            la = [r["json"] for r in hx.reqs() if (r["json"] or {}).get("action") == "list_asks"]
            _check(f"[taskandi-http] AC6: poll --task {ref} accepted; wire task is {sent}",
                   res.rc == 0 and len(la) == 1 and la[0].get("task") == sent, res.show())
        hx.route("list_asks", json=_la("leaf-b"))
        for what, args in (("poll", ["poll", "--task", "ABBR-12"]), ("ask-status", ["ask-status", "--task", "ABBR-12"]),
                           ("complete", ["complete", "--task", "ABBR-12", "--summary", "s"])):
            hx.clear()
            res = hx.cli(*args)
            _check(f"[taskandi-http] AC6: {what} --task ABBR-12 -> ABBR message, exit 1, zero requests",
                   res.rc == 1 and "Task&I descriptor bindings take task ids, not ABBR-N references" in res.err and hx.reqs() == [],
                   res.show())
        hx.clear()
        res = hx.enqueue("comment", "ab1", {"text": "t"}, task="ABBR-12")
        _check("[taskandi-http] AC6: enqueue --task ABBR-12 -> ABBR message, exit 1, no job",
               res.rc == 1 and "not ABBR-N references" in res.err and hx.job("ab1") is None and hx.reqs() == [], res.show())
        hx.route("list_asks", json=_la("someone-else"))
        before = _cur(hx)
        res = hx.cli("poll", "--task", "leaf-b")
        _check("[taskandi-http] AC6: a poll response echoing a different task exits 1; cursors and answers unchanged",
               res.rc == 1 and _cur(hx) == before, res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "ec1", {"text": "t"}, task="project")
        hx.route("comment", json={"task": "someone-else", "comment_id": "c-1"})
        res = hx.cli("flush")
        _check("[taskandi-http] AC6: a job response echoing a different task makes the job uncertain",
               (hx.job("ec1") or {}).get("state") == "uncertain", res.show())
        hx.clear()
        res = hx.cli("poll", "--task", "ABBR-12")
        _check("[taskandi-http] AC6: ABBR-N is refused under a non-null root too", res.rc == 1 and hx.reqs() == [], res.show())


# ---------------------------------------------------------------------------
# AC7 Binding digest
# ---------------------------------------------------------------------------

_FP = "out.fp = C.bindingFingerprint(C.loadConfig(cwd));"


def _fp_expected(workspace: str, task, origin_host: str = "http://127.0.0.1") -> str:
    # Rev 6 AC25: the digest includes the origin's scheme and host (not its port).
    return _canon_digest({"kind": "descriptor-http", "workspace": workspace, "task": task, "contractRevision": _CONTRACT,
                          "originHost": origin_host})


def test_taskandi_http_ac7_binding_digest() -> None:
    print("[taskandi-http] AC7 binding digest")
    with _Hx() as hx:
        hx.enqueue("comment", "b1", {"text": "t"}, task="project")
        out = hx.lib(_FP)
        fp0 = out.get("fp")
        _check("[taskandi-http] AC7: fingerprint = digest({kind:descriptor-http, workspace, task, contractRevision v2.2})",
               fp0 == _fp_expected(_WS, "project"), repr(out))
        res = hx.cli("poll")
        _check("[taskandi-http] AC7: control - poll before the reconnect succeeds", res.rc == 0, res.show())
        old_token = hx.token
        hx.reconnect()
        fp1 = hx.lib(_FP).get("fp")
        _check("[taskandi-http] AC7: a reconnect (new token, connection, port) leaves the fingerprint unchanged",
               fp1 == fp0 and hx.token != old_token, f"{fp0} {fp1}")
        res = hx.cli("flush", env={"VIBE_TASK_BINDING": fp0})
        flushed = [r for r in hx.reqs() if (r["json"] or {}).get("action") == "comment"]
        _check("[taskandi-http] AC7: the queued job flushes to the new connection; the pinned fingerprint still matches",
               res.rc == 0 and (hx.job("b1") or {}).get("state") == "done" and flushed
               and flushed[-1]["json"]["connection"] == "conn-reconnected-2", res.show())
        res = hx.cli("poll")
        _check("[taskandi-http] AC7: poll succeeds after the reconnect (answers keep their binding)", res.rc == 0, res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "b2", {"text": "t"}, task="project")
        hx.cli("poll")
        fp0 = hx.lib(_FP).get("fp")
        hx.write_desc(workspace="ws-other")
        hx.clear()
        res = hx.cli("flush")
        _check("[taskandi-http] AC7: a different workspace makes flush fail with the binding-changed refusal; nothing sent",
               res.rc != 0 and re.search(r"binding changed|BINDING_CHANGED", res.err) and hx.count("comment") == 0, res.show())
        res = hx.cli("poll")
        _check("[taskandi-http] AC7: a different workspace makes poll fail `answer binding changed`",
               res.rc != 0 and "answer binding changed" in res.err, res.show())
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1", env={"VIBE_TASK_BINDING": fp0})
        _check("[taskandi-http] AC7: VIBE_TASK_BINDING=<old fingerprint> then fails `pinned task binding changed`",
               res.rc != 0 and "pinned task binding changed" in res.err, res.show())
        hx.write_desc()
        res = hx.cli("next-task", "--agent", "claude", "--session", "s1", env={"VIBE_TASK_BINDING": fp0})
        _check("[taskandi-http] AC7: control - restoring the workspace makes the same pin pass", res.rc == 0, res.show())
    with _Hx() as hx:
        hx.enqueue("comment", "b3", {"text": "t"}, task="project")
        hx.cli("poll")
        other = {"VIBE_TASK_REF": "leaf-b"}
        fp_other = hx.lib(_FP).get("fp")
        res_lib = subprocess.run(["node", "--input-type=module", "--eval",
                                  "import {pathToFileURL as p} from 'node:url'; const C = await import(p(process.argv[1]).href); console.log(C.bindingFingerprint(C.loadConfig(process.argv[2])));",
                                  _CLIENT.as_posix(), str(hx.repo)], input="", capture_output=True, text=True, env=hx.env("0", other))
        _check("[taskandi-http] AC7: a different effective task (VIBE_TASK_REF) changes the fingerprint to the expected digest",
               res_lib.stdout.strip() == _fp_expected(_WS, "leaf-b") != fp_other, res_lib.stdout + res_lib.stderr)
        hx.clear()
        res = hx.cli("flush", env=other)
        _check("[taskandi-http] AC7: a different effective task makes flush fail with the binding-changed refusal",
               res.rc != 0 and re.search(r"binding changed|BINDING_CHANGED", res.err) and hx.count("comment") == 0, res.show())
        res = hx.cli("poll", env=other)
        _check("[taskandi-http] AC7: a different effective task makes poll fail `answer binding changed`",
               res.rc != 0 and "answer binding changed" in res.err, res.show())
    r = subprocess.run(["node", "--input-type=module", "--eval",
                        "import {pathToFileURL as p} from 'node:url'; await import(p(process.argv[2]).href); console.log('ok');", "import-probe", _SUPERVISOR.as_posix()],
                       input="", capture_output=True, text=True, timeout=60)
    _check("[taskandi-http] AC7: codex-supervisor.mjs still imports", r.returncode == 0 and "ok" in r.stdout, r.stderr[-300:])


# ---------------------------------------------------------------------------
# AC8 Cursors
# ---------------------------------------------------------------------------

def test_taskandi_http_ac8_cursors() -> None:
    print("[taskandi-http] AC8 cursors")
    la_fix = _fixture("list_asks")["response"]
    ask = la_fix["asks"][0]
    with _Hx() as hx:
        res = hx.cli("poll")
        first = [r["json"] for r in hx.reqs() if r["json"]["action"] == "list_asks"][0]
        cur = ((hx.state() or {}).get("cursors") or {}).get("project")
        _check("[taskandi-http] AC8: first poll of A sends since 0 and stores cursors[A] = {now}",
               res.rc == 0 and first["since"] == 0 and cur == {"now": _T1}, res.show() + repr(cur))
        hx.claim("leaf-b")
        hx.route("list_asks", json=_la("leaf-b", now=_T1 + 5000))
        res = hx.cli("poll")
        b = [r["json"] for r in hx.reqs() if r["json"]["action"] == "list_asks"][0]
        _check("[taskandi-http] AC8: after claiming B, poll of B sends since 0 (cursors are per task)",
               res.rc == 0 and b["task"] == "leaf-b" and b["since"] == 0, res.show() + repr(b))
        hx.clear()
        hx.route("list_asks", json=la_fix)
        res = hx.cli("poll", "--task", "project")
        a2 = [r["json"] for r in hx.reqs() if r["json"]["action"] == "list_asks"][0]
        out = res.json() or {}
        _check("[taskandi-http] AC8: polling A again sends since = T1 - 2000",
               res.rc == 0 and a2["since"] == _T1 - 2000, res.show() + repr(a2))
        _check("[taskandi-http] AC8: the repeated (task, ask_id, same answer) is neither new, ignored nor a conflict",
               out.get("newAnswers") == 0 and out.get("ignored") == 0 and out.get("conflicts") == [] and out.get("answers") == [], res.show())
        changed = copy.deepcopy(la_fix)
        changed["asks"][0]["answer"] = "A different answer"
        hx.route("list_asks", json=changed)
        res = hx.cli("poll", "--task", "project")
        out = res.json() or {}
        _check("[taskandi-http] AC8: the same ask_id with a different answer is a conflict",
               res.rc == 0 and out.get("conflicts") == [ask["ask_id"]] and out.get("newAnswers") == 0, res.show())
        before = hx.state()
        stale = copy.deepcopy(la_fix)
        stale["now"] = _T1 - 2001
        hx.route("list_asks", json=stale)
        res = hx.cli("poll", "--task", "project")
        after = hx.state()
        _check("[taskandi-http] AC8: a response with now < since is refused; cursor and answers unchanged",
               res.rc == 1 and before["cursors"] == after["cursors"] and before["answers"] == after["answers"], res.show())
    with _Hx() as hx:
        ok = copy.deepcopy(la_fix)
        extra = copy.deepcopy(ask)
        extra["ask_id"] = "second-ask"
        extra["owner_answer"] = False
        extra["answer"] = "someone else's"
        ok["asks"].append(extra)
        hx.route("list_asks", json=ok)
        out = hx.cli("poll").json() or {}
        _check("[taskandi-http] AC8: answers lists owner answers only; a non-owner answer is counted as ignored",
               out.get("newAnswers") == 1 and out.get("ignored") == 1 and [a["ask_id"] for a in out.get("answers", [])] == [ask["ask_id"]],
               repr(out)[:400])
        res = hx.cli("poll")
        out = res.json() or {}
        _check("[taskandi-http] AC8: a second poll of both is neither new nor ignored (stored non-owner answers are keyed too)",
               out.get("newAnswers") == 0 and out.get("ignored") == 0 and out.get("conflicts") == [], res.show())


def _run_all() -> None:
    for fn in [test_taskandi_http_ac1_descriptor, test_taskandi_http_ac2_wire_per_fixture,
               test_taskandi_http_ac3_host_and_headers, test_taskandi_http_ac3_status_refusals_and_source,
               test_taskandi_http_ac4_flush_job_states, test_taskandi_http_ac4_direct_and_extras,
               test_taskandi_http_ac5_capabilities_gate, test_taskandi_http_ac5b_transport_limits,
               test_taskandi_http_ac6_task_ids, test_taskandi_http_ac7_binding_digest, test_taskandi_http_ac8_cursors]:
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
    print("PASS: Task&I v2.2 HTTP acceptance checks (part 1)")
