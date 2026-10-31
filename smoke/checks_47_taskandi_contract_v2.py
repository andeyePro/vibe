#!/usr/bin/env python3
"""Offline acceptance checks for the Task&I agent-exchange contract v2.1 (task_061).

Tester-owned (cycle 1).  Every check runs the real client CLI
(``devcontainer/taskandi-client.mjs``) or its library exports in a throwaway
git project.  Network is replaced, not mocked in-process: a ``--import``
preload swaps ``globalThis.fetch`` (which ``fetchTransport`` uses) for a fixture
MCP endpoint and appends every request it receives to a log.  "Zero transport
requests" is therefore observed as an empty request log, and "the recorder never
sees an authorization header for that origin" is observed in the same log.

The fixture endpoint is served only for ``https://fixture.invalid/mcp``; no
live Task&I host is ever contacted.

Run only this module with:
    python3 smoke/checks_47_taskandi_contract_v2.py

Mechanism controls.  Each acceptance criterion is paired with a positive
control (an accept case that must succeed, or an observation that must be
non-empty) so that a refusal is only credited when the same harness can see the
operation succeed.  Where a check depends on a mechanism, its docstring says what
the check would report if that mechanism were absent.
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
from pathlib import Path

# Allow both `python3 smoke/checks_47_taskandi_contract_v2.py` (this module's own
# documented standalone entry point) and package import via runner.py: a direct
# script invocation puts smoke/ on sys.path[0], not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import check, FAILURES


_REPO = Path(__file__).resolve().parent.parent
_CLIENT = _REPO / "devcontainer" / "taskandi-client.mjs"
_USAGE_MJS = _REPO / "devcontainer" / "taskandi-usage.mjs"
_DOCS = _REPO / "docs" / "taskandi-client.md"
_CHANGELOG = _REPO / "CHANGELOG.md"

_CONTRACT = "vibe-agent-exchange-v2.1"
_LEGACY = "vibe-action-window-fixture-v1"
_BIND = "ABBR-1"
_CLAIM = "ABBR-2"
_OTHER = "ABBR-9"
_ENDPOINT = "https://fixture.invalid/mcp"
_TOKEN_SENTINEL = "-".join(("TOKEN", "SENTINEL", "7f3a"))  # built, so the content guard does not read it as a credential
_QUESTION_SENTINEL = "QUESTION-SENTINEL-9c1d"
_COMMENT_SENTINEL = "COMMENT-SENTINEL-2e8b"
_ANSWER_SENTINEL = "ANSWER-SENTINEL-4a6f"
_SENTINELS = (_TOKEN_SENTINEL, _QUESTION_SENTINEL, _COMMENT_SENTINEL, _ANSWER_SENTINEL)
_MAX_SAFE = 9007199254740991
_UNSAFE = 9007199254740992
_C0 = {"sequence": 0, "value": ""}

_RESULTS: list[bool] = []


def _check(name: str, cond: bool, detail: str = "") -> bool:
    _RESULTS.append(bool(cond))
    return check(name, bool(cond), detail)


def _sanitized_env() -> dict:
    """Strip ambient VIBE_TASK_* so a bound parent task cannot change child resolution."""
    return {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")}


# Fixture MCP endpoint, loaded into every CLI child with `node --import`.
# It reads its response table from TASKANDI_FIXTURE on load and appends one
# JSON line per request to TASKANDI_LOG.  It never performs real network I/O.
_PRELOAD = r'''
import { appendFileSync, readFileSync } from 'node:fs';
const spec = JSON.parse(readFileSync(process.env.TASKANDI_FIXTURE, 'utf8'));
const log = process.env.TASKANDI_LOG;
const reply = (message, result, headers = {}) => new Response(JSON.stringify({ jsonrpc: '2.0', id: message.id, result }), { status: 200, headers: { 'content-type': 'application/json', 'mcp-session-id': 'fixture-session', ...headers } });
globalThis.fetch = async (url, init) => {
  const message = JSON.parse(init.body);
  appendFileSync(log, JSON.stringify({ url: String(url), method: message.method, name: message.params?.name ?? null, args: message.params?.arguments ?? null, authorization: init.headers?.authorization ?? null }) + '\n');
  if (message.method === 'notifications/initialized') return new Response('', { status: 202 });
  if (message.method === 'initialize') return reply(message, { protocolVersion: '2025-11-25' });
  if (message.method === 'tools/list') return reply(message, { tools: spec.tools });
  if (message.method !== 'tools/call') return reply(message, {});
  const r = spec.calls?.[message.params.name];
  if (!r) return reply(message, { isError: true, content: [{ type: 'text', text: 'no fixture for tool' }] });
  if (r.transport) throw new Error(r.transport);
  if (r.redirect) return new Response('', { status: 307, headers: { location: r.redirect } });
  if (r.rpcError) return new Response(JSON.stringify({ jsonrpc: '2.0', id: message.id, error: { code: -32000, message: 'fixture rpc error' } }), { status: 200, headers: { 'content-type': 'application/json', 'mcp-session-id': 'fixture-session' } });
  if (r.isError) return reply(message, { isError: true, content: [{ type: 'text', text: 'tool failed' }] });
  return reply(message, { structuredContent: r.result });
};
'''

# Library-level harness: prints one JSON object built by the snippet in `body`.
_LIB_HEAD = r'''
const C = await import((await import('node:url')).pathToFileURL(process.argv[2]).href);
const cwd = process.argv[3];
const out = {};
'''


def _lib(body: str, cwd: Path) -> dict:
    code = _LIB_HEAD + body + "\nconsole.log(JSON.stringify(out));\n"
    res = subprocess.run(["node", "--input-type=module", "--eval", code, "lib-runner", str(_CLIENT), str(cwd)],
                         input="", capture_output=True, text=True, timeout=120, env=_sanitized_env())
    if res.returncode != 0:
        return {"__rc": res.returncode, "__err": res.stderr}
    return json.loads(res.stdout.strip().splitlines()[-1])


def _schema(required: dict, optional: dict | None = None) -> dict:
    props = {}
    for name, typ in {**required, **(optional or {})}.items():
        props[name] = {"type": "array", "items": {"type": "string"}} if typ == "array" else {"type": typ}
    return {"type": "object", "properties": props, "required": list(required)}


_USAGE_FIELDS = {"account": "string", "model": "string", "input": "integer", "output": "integer",
                 "cache_read": "integer", "cache_write": "integer", "cost_estimate": "number",
                 "source": "string", "source_ref": "string"}


def _tools() -> list:
    """The exact v2.1 tool table from the spec (required and optional columns)."""
    return [
        {"name": "next_task", "inputSchema": _schema({"task": "string", "agent": "string", "session": "string"})},
        {"name": "ask", "inputSchema": _schema(
            {"task": "string", "question": "string", "default": "string", "order": "integer",
             "estimate_minutes": "integer", "remaining_minutes": "integer", "reversible": "boolean", "blocking": "boolean"},
            {"options": "array", "in_reply_to": "string"})},
        {"name": "list_asks", "inputSchema": _schema({"task": "string", "since": "object"})},
        {"name": "comment", "inputSchema": _schema({"task": "string", "text": "string"})},
        {"name": "record_usage", "inputSchema": _schema({"task": "string", **_USAGE_FIELDS})},
        {"name": "record_time", "inputSchema": _schema({"task": "string", "seconds": "integer", "started_at": "string", "actor": "string"})},
        {"name": "complete", "inputSchema": _schema({"task": "string", "summary": "string"})},
        {"name": "release", "inputSchema": _schema({"task": "string", "reason": "string"})},
    ]


class _Res:
    def __init__(self, rc: int, out: str, err: str):
        self.rc, self.out, self.err = rc, out, err

    def json(self):
        try:
            return json.loads(self.out)
        except ValueError:
            return None

    def show(self) -> str:
        return f"rc={self.rc} stdout={self.out!r} stderr={self.err!r}"


class _Fx:
    """A throwaway git project plus a fixture MCP endpoint wired in by preload."""

    def __init__(self, *, bound: bool = True, binding: str = _BIND, revision: str | None = None,
                 token: str = "fixture-token"):
        self._td = tempfile.TemporaryDirectory(prefix="taskandi-v2-")
        base = Path(self._td.name)
        self.base = base
        self.root = base / "repo"
        self.root.mkdir()
        self.log = base / "requests.jsonl"
        self.log.write_text("")
        self.spec_path = base / "fixture.json"
        self.preload = base / "fixture.mjs"
        self.preload.write_text(_PRELOAD)
        self._tools = _tools()
        self._calls: dict = {}
        self._write_spec()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, input="", capture_output=True, text=True)
        vibe = self.root / ".vibe"
        vibe.mkdir(mode=0o700)
        if bound:
            cfg = {"endpoint": _ENDPOINT, "task": binding}
            if revision is not None:
                cfg["contractRevision"] = revision
            (vibe / "taskandi.json").write_text(json.dumps(cfg))
        self.set_token(token)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._td.cleanup()
        return False

    def set_token(self, value: str) -> None:
        path = self.root / ".vibe" / "taskandi-token"
        path.write_text(value)
        os.chmod(path, 0o600)

    def _write_spec(self) -> None:
        self.spec_path.write_text(json.dumps({"tools": self._tools, "calls": self._calls}))

    def set_tools(self, tools: list) -> None:
        self._tools = tools
        self._write_spec()

    def set_call(self, name: str, response: dict) -> None:
        """response: {"result": obj} | {"transport": msg} | {"redirect": url} | {"rpcError": True} | {"isError": True}."""
        self._calls[name] = response
        self._write_spec()

    def cli(self, *args: str, stdin: str = "") -> _Res:
        env = _sanitized_env()
        env["TASKANDI_FIXTURE"] = str(self.spec_path)
        env["TASKANDI_LOG"] = str(self.log)
        res = subprocess.run(["node", "--import", self.preload.as_uri(), str(_CLIENT), *args], cwd=str(self.root),
                             input=stdin, capture_output=True, text=True, timeout=120, env=env)
        return _Res(res.returncode, res.stdout, res.stderr)

    def requests(self) -> list:
        return [json.loads(line) for line in self.log.read_text().splitlines() if line.strip()]

    def tool_calls(self) -> list:
        return [r for r in self.requests() if r["method"] == "tools/call"]

    def clear_log(self) -> None:
        self.log.write_text("")

    def state(self):
        path = self.root / ".vibe" / "taskandi-outbox" / "state.json"
        return json.loads(path.read_text()) if path.exists() else None

    def jobs(self) -> list:
        state = self.state()
        return state["jobs"] if state else []

    def job(self, key: str):
        return next((j for j in self.jobs() if j["key"] == key), None)

    def claimed(self):
        state = self.state()
        return state.get("claimed") if state else None

    def write_state(self, state: dict) -> None:
        d = self.root / ".vibe" / "taskandi-outbox"
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = d / "state.json"
        path.write_text(json.dumps(state))
        os.chmod(path, 0o600)


def _next_obj(task: str = _CLAIM) -> dict:
    return {"task": task, "title": "Write the thing", "body": "Body text", "priority": 3, "effective_priority": 4,
            "allowance": {"windows": 2, "tokens": 1000}, "spent": {"windows": 1, "tokens": 10},
            "hardDeadline": "2026-11-01T00:00:00Z", "latest_start": "2026-10-31T00:00:00Z", "estimate_minutes": 30,
            "owner": "owner-1", "lease": {"until": "2026-10-30T23:00:00Z", "session": "sess-1"}}


def _claim(fx: _Fx, task: str = _CLAIM, session: str = "sess-1") -> _Res:
    fx.set_call("next_task", {"result": _next_obj(task)})
    return fx.cli("next-task", "--agent", "claude", "--session", session)


def _full_ask(**extra) -> dict:
    base = {"question": "Ship it?", "default": "wait", "options": ["yes", "no"], "order": 1,
            "estimate_minutes": 5, "remaining_minutes": 5, "reversible": True, "in_reply_to": "ASK-0"}
    base.update(extra)
    return base


def _without(d: dict, key: str) -> dict:
    out = copy.deepcopy(d)
    del out[key]
    return out


def _page(since: dict, cursor: dict, answers: list) -> dict:
    return {"since": since, "cursor": cursor, "answers": answers}


def _ans(ask_id: str, answer: str, owner: bool, seen="2026-10-30T10:00:00Z", answered="2026-10-30T10:01:00Z") -> dict:
    return {"ask_id": ask_id, "answer": answer, "owner_answer": owner, "seen_at": seen, "answered_at": answered}


def _cur(seq: int, value: str) -> dict:
    return {"sequence": seq, "value": value}


_PRE_UPGRADE_DIGEST = hashlib.sha256(
    ('{"contractRevision":null,"endpoint":"%s","task":"%s"}' % (_ENDPOINT, _BIND)).encode()).hexdigest()


def _stored_comment_job(key: str, state: str, binding=None) -> dict:
    return {"key": key, "kind": "comment", "digest": "x", "payload": {"task": _BIND, "text": "old"},
            "binding": binding, "channel": "taskandi-mcp", "state": state, "lastError": "fixture"}


def _write_transcript(path: Path) -> None:
    rows = [
        {"type": "turn_context", "payload": {"model": "gpt-test"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 100, "cached_input_tokens": 10, "cache_write_input_tokens": 0, "output_tokens": 20}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 150, "cached_input_tokens": 20, "cache_write_input_tokens": 5, "output_tokens": 40}}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


# ---------------------------------------------------------------------------
# AC1 Revision handling
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac1_revision_handling() -> None:
    """AC1. Mechanism: revisionOf()/loadConfig revision resolution.  If the default
    were absent, the unpinned binding would load as null or v1 and the first check fails.
    Positive control: the pinned-v1 binding loads with the legacy string."""
    print("[taskandi-v2] AC1 revision handling")
    with _Fx() as fx:
        out = _lib("out.contract = C.CONTRACT_REVISION; out.legacy = C.LEGACY_CONTRACT_REVISION;", fx.root)
        _check("[taskandi-v2] AC1: CONTRACT_REVISION exported as v2.1",
               out.get("contract") == _CONTRACT, repr(out))
        _check("[taskandi-v2] AC1: LEGACY_CONTRACT_REVISION exported as v1 string",
               out.get("legacy") == _LEGACY, repr(out))
    with _Fx() as fx:
        out = _lib("out.loaded = C.loadConfig(cwd).contractRevision;", fx.root)
        _check("[taskandi-v2] AC1: unpinned binding loads with effective v2.1 revision",
               out.get("loaded") == _CONTRACT, repr(out))
    with _Fx(revision=_LEGACY) as fx:
        out = _lib("out.loaded = C.loadConfig(cwd).contractRevision;", fx.root)
        _check("[taskandi-v2] AC1: v1-pinned binding loads with the legacy string",
               out.get("loaded") == _LEGACY, repr(out))
    with _Fx(revision="vibe-something-else") as fx:
        out = _lib("try { C.loadConfig(cwd); out.loaded = true; } catch (e) { out.error = e.message; }", fx.root)
        _check("[taskandi-v2] AC1: unknown revision string makes loadConfig fail",
               "contractRevision must exactly equal" in str(out.get("error")), repr(out))
        res = fx.cli("enqueue", "comment", "--key", "bad-rev", stdin=json.dumps({"text": "x"}))
        _check("[taskandi-v2] AC1: unknown revision string makes enqueue exit 1",
               res.rc == 1 and "contractRevision" in res.err, res.show())
    # v1-pinned binding keeps v1 rules.
    with _Fx(revision=_LEGACY) as fx:
        res = fx.cli("enqueue", "ask", "--key", "v1-ok", stdin=json.dumps({"to": "owner", "question": "q", "default": "d"}))
        _check("[taskandi-v2] AC1: v1-pinned ask with `to` and no reversible is accepted",
               res.rc == 0 and fx.job("v1-ok") is not None, res.show())
        res = fx.cli("enqueue", "ask", "--key", "v1-bad", stdin=json.dumps(
            {"to": "owner", "question": "q", "default": "d", "reversible": True}))
        _check("[taskandi-v2] AC1: v1-pinned ask with reversible is refused as unknown key",
               res.rc == 1 and "unknown key reversible" in res.err and fx.job("v1-bad") is None, res.show())
        _check("[taskandi-v2] AC1: v1 enqueue made no transport call", fx.requests() == [], repr(fx.requests()))


def test_taskandi_v2_ac1_v1_gate_refusals() -> None:
    """AC1 gate. Mechanism: requireV2 at the CLI and client layers.  If the gate were
    absent, these commands would reach the fixture (non-empty request log) or write state.
    Positive control: the same commands succeed on an unpinned v2.1 binding."""
    print("[taskandi-v2] AC1 v1 gate refusals")
    stdin_comment = json.dumps({"text": "x"})
    stdin_time = json.dumps({"seconds": 0, "started_at": "2026-10-30T21:00:00Z"})
    stdin_ask = json.dumps({"to": "owner", "question": "q", "default": "d"})
    cases = [
        ("next-task", ["next-task", "--agent", "claude", "--session", "sess-1"], None),
        ("complete", ["complete", "--task", _BIND, "--summary", "s"], None),
        ("release", ["release", "--task", _BIND, "--reason", "r"], None),
        ("enqueue comment", ["enqueue", "comment", "--key", "g-c"], stdin_comment),
        ("enqueue record_time", ["enqueue", "record_time", "--key", "g-t"], stdin_time),
        ("enqueue ask --task", ["enqueue", "ask", "--key", "g-a", "--task", _BIND], stdin_ask),
    ]
    with _Fx(revision=_LEGACY) as fx:
        for label, args, stdin in cases:
            res = fx.cli(*args, stdin=stdin or "")
            _check(f"[taskandi-v2] AC1: v1 {label} exits 1 with the v2.1 requirement message",
                   res.rc == 1 and f"requires contract {_CONTRACT}" in res.err, f"{label}: {res.show()}")
        _check("[taskandi-v2] AC1: v1 gate made zero transport requests", fx.requests() == [], repr(fx.requests()))
        _check("[taskandi-v2] AC1: v1 gate changed no state", fx.state() is None, repr(fx.state()))
    with _Fx() as fx:
        res = _claim(fx)
        _check("[taskandi-v2] AC1 control: the same next-task succeeds on unpinned v2.1",
               res.rc == 0 and res.json() is not None and fx.claimed() is not None, res.show())


# ---------------------------------------------------------------------------
# AC2 ask v2.1 validation
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac2_ask_validation() -> None:
    """AC2. Mechanism: validatePayload ask branch (exactKeys, required fields, safeCount,
    boolean, text/id length and option limits).  If exactKeys were dropped, the unknown-key
    cases would exit 0 and show up as jobs; if the length limits were dropped the 8001/201/51/1001
    cases would enqueue.  Positive control: the full ask and the default-blocking ask are accepted."""
    print("[taskandi-v2] AC2 ask v2.1 validation")
    with _Fx() as fx:
        res = fx.cli("enqueue", "ask", "--key", "ask-full", stdin=json.dumps(_full_ask(blocking=False)))
        job = fx.job("ask-full")
        _check("[taskandi-v2] AC2: full ask with blocking false is accepted",
               res.rc == 0 and job is not None, res.show())
        _check("[taskandi-v2] AC2: accepted ask is stored with the binding task and blocking false",
               job is not None and job["payload"].get("task") == _BIND and job["payload"].get("blocking") is False,
               repr(job))
        res = fx.cli("enqueue", "ask", "--key", "ask-default", stdin=json.dumps(_full_ask()))
        job = fx.job("ask-default")
        _check("[taskandi-v2] AC2: ask without blocking is stored with blocking true",
               res.rc == 0 and job is not None and job["payload"].get("blocking") is True, res.show())

        negatives = {
            "unknown key to": _full_ask(to="owner"),
            "unknown key actor": _full_ask(actor="agent"),
            "reversible not boolean": _full_ask(reversible="yes"),
            "blocking not boolean": _full_ask(blocking="yes"),
            "order negative": _full_ask(order=-1),
            "order fractional": _full_ask(order=1.5),
            "order string": _full_ask(order="3"),
            "order unsafe": _full_ask(order=_UNSAFE),
            "estimate_minutes negative": _full_ask(estimate_minutes=-1),
            "estimate_minutes fractional": _full_ask(estimate_minutes=1.5),
            "estimate_minutes unsafe": _full_ask(estimate_minutes=_UNSAFE),
            "remaining_minutes string": _full_ask(remaining_minutes="5"),
            "question 8001 chars": _full_ask(question="q" * 8001),
            "in_reply_to 201 chars": _full_ask(in_reply_to="x" * 201),
            "51 options": _full_ask(options=["o"] * 51),
            "option 1001 chars": _full_ask(options=["o" * 1001]),
        }
        for field in ["question", "default", "order", "estimate_minutes", "remaining_minutes", "reversible"]:
            negatives[f"missing {field}"] = _without(_full_ask(), field)
        for index, (label, payload) in enumerate(negatives.items()):
            key = f"ask-neg-{index}"
            res = fx.cli("enqueue", "ask", "--key", key, stdin=json.dumps(payload))
            _check(f"[taskandi-v2] AC2: refused ({label}) exits 1 and queues nothing",
                   res.rc == 1 and fx.job(key) is None, f"{label}: {res.show()}")
        _check("[taskandi-v2] AC2: refused asks made zero transport requests", fx.requests() == [], repr(fx.requests()))


# ---------------------------------------------------------------------------
# AC3 Task targeting
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac3_task_targeting() -> None:
    """AC3. Mechanism: enqueue/complete/release/next-task target check (binding or claimed task
    only, plus strict argv).  If checkTarget were absent, `--task ABBR-9` would exit 0 and a
    payload would be stored; the zero-request assertion would then fail.  Positive control:
    the binding and claimed tasks are accepted and recorded, and the claim is visibly stored."""
    print("[taskandi-v2] AC3 task targeting")
    with _Fx() as fx:
        res = _claim(fx)
        _check("[taskandi-v2] AC3 control: claim on ABBR-2 is stored", res.rc == 0 and fx.claimed() is not None
               and fx.claimed().get("task") == _CLAIM, res.show())
        fx.clear_log()
        comment = json.dumps({"text": "c"})
        res = fx.cli("enqueue", "comment", "--key", "t-bind", "--task", _BIND, stdin=comment)
        _check("[taskandi-v2] AC3: --task equal to the binding task is accepted",
               res.rc == 0 and (fx.job("t-bind") or {}).get("payload", {}).get("task") == _BIND, res.show())
        res = fx.cli("enqueue", "comment", "--key", "t-claim", "--task", _CLAIM, stdin=comment)
        _check("[taskandi-v2] AC3: --task equal to the claimed task is accepted and recorded",
               res.rc == 0 and (fx.job("t-claim") or {}).get("payload", {}).get("task") == _CLAIM, res.show())
        res = fx.cli("enqueue", "comment", "--key", "t-other", "--task", _OTHER, stdin=comment)
        _check("[taskandi-v2] AC3: --task neither bound nor claimed exits 1 with the refusal",
               res.rc == 1 and "task is neither the bound task nor the claimed task" in res.err and fx.job("t-other") is None,
               res.show())
        res = fx.cli("enqueue", "comment", "--key", "t-bad", "--task", "not-a-ref", stdin=comment)
        _check("[taskandi-v2] AC3: --task not-a-ref exits 1", res.rc == 1 and fx.job("t-bad") is None, res.show())
        res = fx.cli("enqueue", "comment", "--key", "t-both", "--task", _BIND,
                     stdin=json.dumps({"text": "c", "task": _BIND}))
        _check("[taskandi-v2] AC3: task in JSON plus --task is a usage error",
               res.rc == 1 and fx.job("t-both") is None, res.show())
        res = fx.cli("complete", "--task", _OTHER, "--summary", "s")
        _check("[taskandi-v2] AC3: complete --task neither bound nor claimed exits 1", res.rc == 1, res.show())
        res = fx.cli("release", "--task", _OTHER, "--reason", "r")
        _check("[taskandi-v2] AC3: release --task neither bound nor claimed exits 1", res.rc == 1, res.show())
        res = fx.cli("next-task", "--task", _BIND, "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC3: next-task --task is an unknown-flag usage error",
               res.rc == 1, res.show())
        _check("[taskandi-v2] AC3: refused targets made zero transport requests",
               fx.requests() == [], repr(fx.requests()))
    with _Fx(bound=False) as fx:
        res = fx.cli("enqueue", "ask", "--key", "unbound-task", "--task", _OTHER, stdin=json.dumps(_full_ask()))
        job = fx.job("unbound-task")
        _check("[taskandi-v2] AC3: unbound enqueue ask --task ABBR-9 is accepted into a file-fallback job",
               res.rc == 0 and job is not None and job.get("channel") == "file-fallback"
               and job["payload"].get("task") == _OTHER, res.show() + repr(job))


# ---------------------------------------------------------------------------
# AC4 Other job payloads
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac4_comment_time_usage() -> None:
    """AC4. Mechanism: validatePayload for comment, record_time and record_usage.  If the
    actor, timestamp or safe-integer checks were dropped, the refused cases would queue jobs.
    Positive control: the accepted comment, the MAX_SAFE record_time and the v1-field record_usage."""
    print("[taskandi-v2] AC4 comment, record_time, record_usage")
    with _Fx() as fx:
        res = fx.cli("enqueue", "comment", "--key", "c-ok", stdin=json.dumps({"text": "hello"}))
        job = fx.job("c-ok")
        _check("[taskandi-v2] AC4: comment {text} is accepted with the binding task",
               res.rc == 0 and job is not None and job["payload"] == {"task": _BIND, "text": "hello"}, res.show())
        comment_bad = {
            "extra key": {"text": "x", "extra": 1},
            "empty text": {"text": ""},
            "8001 chars": {"text": "t" * 8001},
        }
        for index, (label, payload) in enumerate(comment_bad.items()):
            key = f"c-bad-{index}"
            res = fx.cli("enqueue", "comment", "--key", key, stdin=json.dumps(payload))
            _check(f"[taskandi-v2] AC4: comment refused ({label})", res.rc == 1 and fx.job(key) is None, res.show())

        res = fx.cli("enqueue", "record_time", "--key", "rt-zero",
                     stdin=json.dumps({"seconds": 0, "started_at": "2026-10-30T21:00:00Z"}))
        job = fx.job("rt-zero")
        _check("[taskandi-v2] AC4: record_time seconds 0 is accepted",
               res.rc == 0 and job is not None and job["payload"].get("seconds") == 0, res.show())
        _check("[taskandi-v2] AC4: record_time stores actor agent",
               job is not None and job["payload"].get("actor") == "agent", repr(job))
        res = fx.cli("enqueue", "record_time", "--key", "rt-max",
                     stdin=json.dumps({"seconds": _MAX_SAFE, "started_at": "2026-10-30T21:00:00Z"}))
        _check("[taskandi-v2] AC4: record_time seconds MAX_SAFE_INTEGER is accepted", res.rc == 0, res.show())
        time_bad = {
            "actor key": {"seconds": 1, "started_at": "2026-10-30T21:00:00Z", "actor": "me"},
            "seconds -1": {"seconds": -1, "started_at": "2026-10-30T21:00:00Z"},
            "seconds 1.5": {"seconds": 1.5, "started_at": "2026-10-30T21:00:00Z"},
            "seconds unsafe": {"seconds": _UNSAFE, "started_at": "2026-10-30T21:00:00Z"},
            "impossible date": {"seconds": 1, "started_at": "2026-02-31T00:00:00Z"},
            "offset not Z": {"seconds": 1, "started_at": "2026-10-30T21:00:00+01:00"},
            "word": {"seconds": 1, "started_at": "yesterday"},
        }
        for index, (label, payload) in enumerate(time_bad.items()):
            key = f"rt-bad-{index}"
            res = fx.cli("enqueue", "record_time", "--key", key, stdin=json.dumps(payload))
            _check(f"[taskandi-v2] AC4: record_time refused ({label})", res.rc == 1 and fx.job(key) is None, res.show())

        usage = {"account": "acct", "model": "m", "input": 1, "output": 2, "cache_read": 3, "cache_write": 4, "cost_estimate": 0.5}
        res = fx.cli("enqueue", "record_usage", "--key", "ru-ok", stdin=json.dumps(usage))
        job = fx.job("ru-ok")
        _check("[taskandi-v2] AC4: record_usage v1 fields are accepted",
               res.rc == 0 and job is not None, res.show())
        _check("[taskandi-v2] AC4: record_usage gains task, source vibe and source_ref",
               job is not None and job["payload"].get("task") == _BIND and job["payload"].get("source") == "vibe"
               and job["payload"].get("source_ref") == "ru-ok", repr(job))
        res = fx.cli("enqueue", "record_usage", "--key", "ru-bad", stdin=json.dumps({**usage, "to": "owner"}))
        _check("[taskandi-v2] AC4: record_usage refuses unknown key", res.rc == 1 and fx.job("ru-bad") is None, res.show())
        _check("[taskandi-v2] AC4: enqueue made zero transport requests", fx.requests() == [], repr(fx.requests()))


# ---------------------------------------------------------------------------
# AC5 Flush against a v2.1 fixture
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac5_flush_v21_fixture() -> None:
    """AC5 (accept path). Mechanism: flush dispatches each kind with the stored payload and
    records the ask result.  If dispatch or the result check were absent, the ask job would lack
    `result` or the tool-call arguments would differ from the stored payload.  Positive control:
    the fixture records four tool calls, one per kind."""
    print("[taskandi-v2] AC5 flush against v2.1 fixture")
    with _Fx() as fx:
        fx.cli("enqueue", "ask", "--key", "f-ask", stdin=json.dumps(_full_ask(blocking=True)))
        fx.cli("enqueue", "comment", "--key", "f-comment", stdin=json.dumps({"text": "c"}))
        fx.cli("enqueue", "record_usage", "--key", "f-usage", stdin=json.dumps(
            {"account": "acct", "model": "m", "input": 1, "output": 2, "cache_read": 3, "cache_write": 4, "cost_estimate": 0.5}))
        fx.cli("enqueue", "record_time", "--key", "f-time", stdin=json.dumps({"seconds": 60, "started_at": "2026-10-30T21:00:00Z"}))
        fx.set_call("ask", {"result": {"ask_id": "ASK-1", "placed": "subtask"}})
        fx.set_call("comment", {"result": {}})
        fx.set_call("record_usage", {"result": {}})
        fx.set_call("record_time", {"result": {}})
        fx.clear_log()
        res = fx.cli("flush")
        out = res.json() or {}
        _check("[taskandi-v2] AC5: one flush dispatches all four kinds",
               res.rc == 0 and out.get("done") == 4 and out.get("uncertain") == 0, res.show())
        names = sorted(r["name"] for r in fx.tool_calls())
        _check("[taskandi-v2] AC5: the fixture saw one tool call per kind",
               names == ["ask", "comment", "record_time", "record_usage"], repr(names))
        ask_job = fx.job("f-ask") or {}
        _check("[taskandi-v2] AC5: ask job records result ask_id and placed",
               ask_job.get("result") == {"ask_id": "ASK-1", "placed": "subtask"}, repr(ask_job))
        status = (fx.cli("status").json() or {}).get("counts", {})
        _check("[taskandi-v2] AC5: status shows four done", status.get("done") == 4, repr(status))
        sent = {r["name"]: r["args"] for r in fx.tool_calls()}
        _check("[taskandi-v2] AC5 control: dispatched arguments equal the stored ask payload",
               sent.get("ask") == ask_job.get("payload"), repr(sent.get("ask")))


def test_taskandi_v2_ac5_flush_schema_drift_and_ask_results() -> None:
    """AC5 (refusal paths). Mechanism: validateTool before dispatch and validateAskResult after.
    Without validateTool the drifted schemas would dispatch (tool-call count 1); without
    validateAskResult the four malformed results would leave the job done.  Positive control:
    a well-formed `thread` result is accepted and the job reaches done."""
    print("[taskandi-v2] AC5 schema drift and ask result refusals")

    def drift(mutator) -> list:
        tools = copy.deepcopy(_tools())
        mutator(tools)
        return tools

    def ask_props(tools):
        return next(t for t in tools if t["name"] == "ask")["inputSchema"]

    variants = {
        "extra property": drift(lambda t: ask_props(t)["properties"].__setitem__("extra", {"type": "string"})),
        "required lacks reversible": drift(lambda t: ask_props(t)["required"].remove("reversible")),
        "order typed string": drift(lambda t: ask_props(t)["properties"].__setitem__("order", {"type": "string"})),
    }
    for label, tools in variants.items():
        with _Fx() as fx:
            fx.cli("enqueue", "ask", "--key", "drift", stdin=json.dumps(_full_ask()))
            fx.set_tools(tools)
            fx.clear_log()
            res = fx.cli("flush")
            _check(f"[taskandi-v2] AC5: flush refuses ask schema ({label}) with exit 1",
                   res.rc == 1, res.show())
            _check(f"[taskandi-v2] AC5: schema refusal ({label}) leaves the job queued and sends no tools/call",
                   (fx.job("drift") or {}).get("state") == "queued" and fx.tool_calls() == [],
                   f"{fx.job('drift')!r} {fx.tool_calls()!r}")

    results = {
        "missing ask_id": ({"placed": "subtask"}, "ask_id"),
        "numeric ask_id": ({"ask_id": 7, "placed": "subtask"}, "ask_id"),
        "placed email": ({"ask_id": "a", "placed": "email"}, "placed"),
        "extra key": ({"ask_id": "a", "placed": "thread", "extra": 1}, "extra"),
    }
    for label, (result, field) in results.items():
        with _Fx() as fx:
            fx.cli("enqueue", "ask", "--key", "ar", stdin=json.dumps(_full_ask()))
            fx.set_call("ask", {"result": result})
            res = fx.cli("flush")
            job = fx.job("ar") or {}
            _check(f"[taskandi-v2] AC5: malformed ask result ({label}) leaves the job uncertain",
                   job.get("state") == "uncertain", f"{res.show()} {job!r}")
            _check(f"[taskandi-v2] AC5: malformed ask result ({label}) lastError names {field}",
                   field in str(job.get("lastError")), repr(job.get("lastError")))
            fx.cli("flush")
            _check(f"[taskandi-v2] AC5: uncertain ask ({label}) is never re-sent automatically",
                   len(fx.tool_calls()) == 1, repr(fx.tool_calls()))
    with _Fx() as fx:
        fx.cli("enqueue", "ask", "--key", "ar-ok", stdin=json.dumps(_full_ask()))
        fx.set_call("ask", {"result": {"ask_id": "ASK-9", "placed": "thread"}})
        res = fx.cli("flush")
        job = fx.job("ar-ok") or {}
        _check("[taskandi-v2] AC5 control: well-formed thread result reaches done",
               job.get("state") == "done" and job.get("result") == {"ask_id": "ASK-9", "placed": "thread"}, f"{res.show()} {job!r}")


# ---------------------------------------------------------------------------
# AC6 next-task
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac6_next_task() -> None:
    """AC6. Mechanism: strict argv for next-task, validateNextTask, and the atomic claim write.
    If validateNextTask were absent, the invalid results would print and write a claim.
    If the claim write were absent, the state.json assertions fail.  Positive control: a valid
    result claims, and a body of exactly 32000 characters is accepted."""
    print("[taskandi-v2] AC6 next-task")
    with _Fx() as fx:
        for args in (["--agent", "gemini", "--session", "s"],
                     ["--agent", "claude"],
                     ["--agent", "claude", "--session", "a b"]):
            res = fx.cli("next-task", *args)
            _check(f"[taskandi-v2] AC6: bad next-task argv {args} exits 1", res.rc == 1, res.show())
        _check("[taskandi-v2] AC6: bad next-task argv made zero transport requests", fx.requests() == [], repr(fx.requests()))

    with _Fx() as fx:
        res = _claim(fx)
        out = res.json() or {}
        _check("[taskandi-v2] AC6: well-formed result prints bound true with every field echoed",
               res.rc == 0 and out == {"bound": True, "task": _next_obj()}, res.show())
        claimed = fx.claimed() or {}
        _check("[taskandi-v2] AC6: claim stores task, agent, session, lease and claimedAt",
               claimed.get("task") == _CLAIM and claimed.get("agent") == "claude" and claimed.get("session") == "sess-1"
               and claimed.get("lease") == _next_obj()["lease"] and isinstance(claimed.get("claimedAt"), str), repr(claimed))
        calls = fx.tool_calls()
        _check("[taskandi-v2] AC6: request is tools/call next_task with binding, agent and session",
               len(calls) == 1 and calls[0]["name"] == "next_task"
               and calls[0]["args"] == {"task": _BIND, "agent": "claude", "session": "sess-1"}, repr(calls))
        fx.set_call("next_task", {"result": {"task": None}})
        res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC6: task null prints bound true with task null",
               res.rc == 0 and res.json() == {"bound": True, "task": None}, res.show())
        _check("[taskandi-v2] AC6: task null clears the existing claim", fx.claimed() is None, repr(fx.state()))

    invalid = {
        "unknown key": {**_next_obj(), "extra": 1},
        "lease.until soon": {**_next_obj(), "lease": {"until": "soon", "session": "sess-1"}},
        "spent.tokens -1": {**_next_obj(), "spent": {"windows": 1, "tokens": -1}},
        "body 32001 chars": {**_next_obj(), "body": "b" * 32001},
        "task not a ref": {**_next_obj(), "task": "not a ref"},
    }
    for label, result in invalid.items():
        with _Fx() as fx:
            fx.set_call("next_task", {"result": result})
            res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
            _check(f"[taskandi-v2] AC6: invalid next_task result ({label}) exits 1 with empty stdout",
                   res.rc == 1 and res.out == "", res.show())
            _check(f"[taskandi-v2] AC6: invalid next_task result ({label}) writes no claim",
                   fx.claimed() is None, repr(fx.state()))
    with _Fx() as fx:
        fx.set_call("next_task", {"result": {**_next_obj(), "body": "b" * 32000}})
        res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC6 control: body of exactly 32000 characters is accepted",
               res.rc == 0 and fx.claimed() is not None, res.show())

    with _Fx() as fx:
        _claim(fx)
        fx.set_call("next_task", {"transport": "fixture transport failure"})
        res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC6: transport error exits 1 with empty stdout",
               res.rc == 1 and res.out == "", res.show())
        _check("[taskandi-v2] AC6: transport error leaves the previous claim unchanged",
               (fx.claimed() or {}).get("task") == _CLAIM, repr(fx.claimed()))
        res = _claim(fx, task="ABBR-3")
        _check("[taskandi-v2] AC6: a second well-formed call replaces the claim",
               res.rc == 0 and (fx.claimed() or {}).get("task") == "ABBR-3", res.show())

    with _Fx(bound=False) as fx:
        res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC6: unbound next-task prints the file-fallback line and exits 0",
               res.rc == 0 and res.json() == {"bound": False, "channel": "file-fallback"}, res.show())
        _check("[taskandi-v2] AC6: unbound next-task makes zero transport requests", fx.requests() == [], repr(fx.requests()))


# ---------------------------------------------------------------------------
# AC7 poll v2.1
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac7_poll_v21() -> None:
    """AC7. Mechanism: the v2.1 list_asks page validator, owner-only filtering, the
    conflict detector and the cursor-advance rule.  If owner filtering were absent, newAnswers would
    be 3 and not 2.  If the malformed-page refusal were absent, the cursor or answers would change.
    Positive control: the same since and cursor are accepted once the page is well formed."""
    print("[taskandi-v2] AC7 poll v2.1")
    c0, c1, c2, c3, c4, c5 = _C0, _cur(1, "c1"), _cur(2, "c2"), _cur(3, "c3"), _cur(4, "c4"), _cur(5, "c5")
    with _Fx() as fx:
        fx.set_call("list_asks", {"result": _page(c0, c1, [
            _ans("A1", "yes", True), _ans("A2", "no", True), _ans("A3", "maybe", False)])})
        fx.clear_log()
        res = fx.cli("poll")
        out = res.json() or {}
        _check("[taskandi-v2] AC7: three-answer page prints newAnswers 2 and ignored 1",
               res.rc == 0 and out.get("newAnswers") == 2 and out.get("ignored") == 1, res.show())
        _check("[taskandi-v2] AC7: answers holds only the two owner answers with the exact keys",
               [a.get("ask_id") for a in out.get("answers", [])] == ["A1", "A2"]
               and set(out["answers"][0].keys()) == {"ask_id", "answer", "seen_at", "answered_at"}, repr(out))
        _check("[taskandi-v2] AC7: cursor advanced to the page cursor", out.get("cursor") == c1 and fx.state()["cursor"] == c1,
               repr(out.get("cursor")))
        stored = fx.state()["answers"]
        _check("[taskandi-v2] AC7: all three answers are stored with ownerAnswer, seenAt and answeredAt",
               len(stored) == 3 and all({"ownerAnswer", "seenAt", "answeredAt"} <= set(a) for a in stored), repr(stored))
        polls = [r for r in fx.tool_calls() if r["name"] == "list_asks"]
        _check("[taskandi-v2] AC7: request is list_asks {task, since} with no answered key",
               len(polls) == 1 and set(polls[0]["args"]) == {"task", "since"} and polls[0]["args"]["since"] == c0
               and polls[0]["args"]["task"] == _BIND, repr(polls))

        fx.set_call("list_asks", {"result": _page(c1, c2, [_ans("A4", "later", False)])})
        res = fx.cli("poll")
        out = res.json() or {}
        _check("[taskandi-v2] AC7: an all-ignored page still advances the cursor",
               res.rc == 0 and out.get("newAnswers") == 0 and out.get("ignored") == 1 and fx.state()["cursor"] == c2,
               res.show())

        malformed = {
            "missing owner_answer": [{k: v for k, v in _ans("A5", "x", True).items() if k != "owner_answer"}],
            "answered_at 2026-13-01": [_ans("A5", "x", True, answered="2026-13-01T00:00:00Z")],
            "seen_at 5": [_ans("A5", "x", True, seen=5)],
            "repeated ask_id": [_ans("A6", "x", True), _ans("A6", "x", True)],
        }
        before = len(fx.state()["answers"])
        for label, answers in malformed.items():
            fx.set_call("list_asks", {"result": _page(c2, c3, answers)})
            res = fx.cli("poll")
            _check(f"[taskandi-v2] AC7: malformed page ({label}) exits 1 with empty stdout",
                   res.rc == 1 and res.out == "", res.show())
            _check(f"[taskandi-v2] AC7: malformed page ({label}) leaves cursor and answers unchanged",
                   fx.state()["cursor"] == c2 and len(fx.state()["answers"]) == before, repr(fx.state()["cursor"]))
        fx.set_call("list_asks", {"result": _page(c2, c3, [_ans("A5", "x", True)])})
        res = fx.cli("poll")
        _check("[taskandi-v2] AC7 control: the same since and cursor are accepted once the page is well formed",
               res.rc == 0 and (res.json() or {}).get("newAnswers") == 1 and fx.state()["cursor"] == c3, res.show())

        fx.set_call("list_asks", {"result": _page(c3, c4, [_ans("A1", "yes", False)])})
        res = fx.cli("poll")
        _check("[taskandi-v2] AC7: same content with flipped owner_answer records no conflict",
               res.rc == 0 and (res.json() or {}).get("conflicts") == [] and fx.state()["conflicts"] == [], res.show())
        fx.set_call("list_asks", {"result": _page(c4, c5, [_ans("A1", "no", True)])})
        res = fx.cli("poll")
        _check("[taskandi-v2] AC7: different content records a conflict on A1",
               res.rc == 0 and (res.json() or {}).get("conflicts") == ["A1"], res.show())

        refusals = {
            "echo mismatch": _page(_cur(5, "other"), _cur(6, "c6"), []),
            "regression": _page(c5, _cur(4, "c4"), []),
            "noncomparable": _page(c5, _cur(5, "zz"), []),
        }
        for label, page in refusals.items():
            fx.set_call("list_asks", {"result": page})
            res = fx.cli("poll")
            _check(f"[taskandi-v2] AC7: v1 cursor refusal ({label}) still refuses",
                   res.rc == 1 and fx.state()["cursor"] == c5, res.show())
        fx.set_call("list_asks", {"result": _page(c5, _cur(6, "c6"), [])})
        res = fx.cli("poll")
        _check("[taskandi-v2] AC7 control: a valid page from the same cursor is accepted",
               res.rc == 0 and fx.state()["cursor"] == _cur(6, "c6"), res.show())


# ---------------------------------------------------------------------------
# AC8 complete and release
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac8_complete_release() -> None:
    """AC8. Mechanism: validateComplete / validateRelease and the claim-clearing rule.  If the
    `completed:true` branch cleared nothing, claimed would survive.  If the post-send wrapper were
    absent, the transport failure would not start with `outcome unknown`.  Positive control: the
    successful complete and release clear the claim that the same flow created."""
    print("[taskandi-v2] AC8 complete and release")
    with _Fx() as fx:
        _claim(fx)
        fx.set_call("complete", {"result": {"completed": True, "state": "done-provisional"}})
        fx.clear_log()
        res = fx.cli("complete", "--task", _CLAIM, "--summary", "all done")
        _check("[taskandi-v2] AC8: complete completed:true prints bound, completed and state, exit 0",
               res.rc == 0 and res.json() == {"bound": True, "completed": True, "state": "done-provisional"}, res.show())
        _check("[taskandi-v2] AC8: complete completed:true deletes the claim", fx.claimed() is None, repr(fx.state()))
        _check("[taskandi-v2] AC8: complete request carries task and summary",
               [r["args"] for r in fx.tool_calls() if r["name"] == "complete"] == [{"task": _CLAIM, "summary": "all done"}],
               repr(fx.tool_calls()))

        _claim(fx)
        fx.set_call("complete", {"result": {"completed": False, "open_children": [{"task": _CLAIM, "title": "x"}]}})
        res = fx.cli("complete", "--task", _CLAIM, "--summary", "s")
        _check("[taskandi-v2] AC8: complete completed:false prints the open children, exit 0",
               res.rc == 0 and res.json() == {"bound": True, "completed": False, "open_children": [{"task": _CLAIM, "title": "x"}]},
               res.show())
        _check("[taskandi-v2] AC8: open children keep the claim", (fx.claimed() or {}).get("task") == _CLAIM, repr(fx.state()))

        for label, result in {"completed true without state": {"completed": True},
                              "open_children empty": {"completed": False, "open_children": []}}.items():
            fx.set_call("complete", {"result": result})
            res = fx.cli("complete", "--task", _CLAIM, "--summary", "s")
            _check(f"[taskandi-v2] AC8: invalid complete result ({label}) exits 1 with empty stdout and keeps the claim",
                   res.rc == 1 and res.out == "" and (fx.claimed() or {}).get("task") == _CLAIM, res.show())

        fx.set_call("complete", {"transport": "boom"})
        res = fx.cli("complete", "--task", _CLAIM, "--summary", "s")
        _check("[taskandi-v2] AC8: post-send complete failure says outcome unknown and keeps the claim",
               res.rc == 1 and res.err.startswith("taskandi-client: outcome unknown; check the task in Task&I:")
               and (fx.claimed() or {}).get("task") == _CLAIM, res.show())

        fx.set_call("release", {"result": {"released": True}})
        res = fx.cli("release", "--task", _CLAIM, "--reason", "r")
        _check("[taskandi-v2] AC8: release released:true prints bound and released, exit 0",
               res.rc == 0 and res.json() == {"bound": True, "released": True}, res.show())
        _check("[taskandi-v2] AC8: release deletes the claim", fx.claimed() is None, repr(fx.state()))

        _claim(fx)
        fx.set_call("release", {"result": {"released": False}})
        res = fx.cli("release", "--task", _CLAIM, "--reason", "r")
        _check("[taskandi-v2] AC8: release released:false exits 1 and keeps the claim",
               res.rc == 1 and res.out == "" and fx.claimed() is not None, res.show())
        fx.set_call("release", {"transport": "boom"})
        res = fx.cli("release", "--task", _CLAIM, "--reason", "r")
        _check("[taskandi-v2] AC8: post-send release failure says outcome unknown and keeps the claim",
               res.rc == 1 and res.err.startswith("taskandi-client: outcome unknown; check the task in Task&I:")
               and fx.claimed() is not None, res.show())

        for label, args in {"complete missing --summary": ["complete", "--task", _CLAIM],
                            "complete missing --task": ["complete", "--summary", "s"],
                            "release missing --reason": ["release", "--task", _CLAIM]}.items():
            fx.clear_log()
            res = fx.cli(*args)
            _check(f"[taskandi-v2] AC8: {label} exits 1 with zero requests", res.rc == 1 and fx.requests() == [], res.show())

    with _Fx(bound=False) as fx:
        res = fx.cli("complete", "--task", _CLAIM, "--summary", "s")
        _check("[taskandi-v2] AC8: unbound complete prints the file-fallback line and exits 0",
               res.rc == 0 and res.json() == {"bound": False, "channel": "file-fallback"}, res.show())
        res = fx.cli("release", "--task", _CLAIM, "--reason", "r")
        _check("[taskandi-v2] AC8: unbound release prints the file-fallback line and exits 0",
               res.rc == 0 and res.json() == {"bound": False, "channel": "file-fallback"}, res.show())
        _check("[taskandi-v2] AC8: unbound direct calls made zero transport requests", fx.requests() == [], repr(fx.requests()))


# ---------------------------------------------------------------------------
# AC8b Direct-call pre-dispatch
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac8b_direct_call_predispatch() -> None:
    """AC8b. Mechanism: validateTool inside targeted()/nextTask() before any tools/call.  If
    validateTool were skipped, the call would be sent (non-empty tool_calls) and the claim could
    change.  Positive control: with the correct tools list the same release succeeds."""
    print("[taskandi-v2] AC8b direct-call pre-dispatch")
    commands = {
        "next_task": ["next-task", "--agent", "claude", "--session", "sess-1"],
        "complete": ["complete", "--task", _CLAIM, "--summary", "s"],
        "release": ["release", "--task", _CLAIM, "--reason", "r"],
    }
    for tool, args in commands.items():
        variants = {}
        variants["tool absent"] = [t for t in _tools() if t["name"] != tool]
        widened = _tools()
        next(t for t in widened if t["name"] == tool)["inputSchema"]["properties"]["task"] = {"type": "integer"}
        variants["task typed integer"] = widened
        for label, tools in variants.items():
            with _Fx() as fx:
                _claim(fx)
                fx.set_tools(tools)
                fx.clear_log()
                res = fx.cli(*args)
                _check(f"[taskandi-v2] AC8b: {tool} with {label} exits 1 with empty stdout",
                       res.rc == 1 and res.out == "", res.show())
                _check(f"[taskandi-v2] AC8b: {tool} with {label} sends zero tools/call",
                       fx.tool_calls() == [], repr(fx.tool_calls()))
                _check(f"[taskandi-v2] AC8b: {tool} with {label} leaves the claim unchanged",
                       (fx.claimed() or {}).get("task") == _CLAIM, repr(fx.state()))
        with _Fx() as fx:
            _claim(fx)
            fx.set_call("release", {"result": {"released": True}})
            fx.clear_log()
            res = fx.cli("release", "--task", _CLAIM, "--reason", "r")
            _check("[taskandi-v2] AC8b control: with the correct tools list release succeeds",
                   res.rc == 0 and fx.claimed() is None and len(fx.tool_calls()) == 1, res.show())


# ---------------------------------------------------------------------------
# AC9 Outbox invariants for the new kinds
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac9_outbox_invariants() -> None:
    """AC9. Mechanism: enqueue dedup and KEY_CONFLICT, the dispatching-to-uncertain recovery,
    reconcile, and the binding-digest check in flush and status.  If the digest check were absent,
    flush would send the stale job (tool calls non-empty).  Positive control: a fresh job with
    the current digest is not listed as stale."""
    print("[taskandi-v2] AC9 outbox invariants")
    with _Fx() as fx:
        comment = json.dumps({"text": "same"})
        res = fx.cli("enqueue", "comment", "--key", "c-1", stdin=comment)
        _check("[taskandi-v2] AC9: first comment enqueues", res.rc == 0 and (res.json() or {}).get("enqueued") is True, res.show())
        res = fx.cli("enqueue", "comment", "--key", "c-1", stdin=comment)
        _check("[taskandi-v2] AC9: same key and same comment payload is deduplicated",
               res.rc == 0 and (res.json() or {}).get("deduplicated") is True, res.show())
        res = fx.cli("enqueue", "comment", "--key", "c-1", stdin=json.dumps({"text": "different"}))
        _check("[taskandi-v2] AC9: same key with a different payload exits 1",
               res.rc == 1 and "different payload" in res.err, res.show())
        lib = _lib("try { await C.createClient({ cwd }).enqueue('comment', 'c-1', { text: 'different' }); out.code = null; }"
                   " catch (e) { out.code = e.code ?? null; }", fx.root)
        _check("[taskandi-v2] AC9: the library reports KEY_CONFLICT for the same case",
               lib.get("code") == "KEY_CONFLICT", repr(lib))

    with _Fx() as fx:
        fx.write_state({"version": 1, "jobs": [_stored_comment_job("hw-comment", "dispatching")],
                        "reconciliationLog": [], "cursor": None, "answers": [], "conflicts": []})
        res = fx.cli("status")
        out = res.json() or {}
        _check("[taskandi-v2] AC9: a comment job left dispatching is listed as uncertain by status",
               res.rc == 0 and "hw-comment" in out.get("uncertaintyIds", []), res.show())
        _check("[taskandi-v2] AC9: the stored job state becomes uncertain",
               (fx.job("hw-comment") or {}).get("state") == "uncertain", repr(fx.job("hw-comment")))

    with _Fx() as fx:
        fx.cli("enqueue", "comment", "--key", "fresh", stdin=json.dumps({"text": "fresh"}))
        state = fx.state()
        stale = _stored_comment_job("stale-1", "queued", binding=_PRE_UPGRADE_DIGEST)
        state["jobs"].append(stale)
        fx.write_state(state)
        fx.clear_log()
        res = fx.cli("status")
        out = res.json() or {}
        _check("[taskandi-v2] AC9: status lists the pre-upgrade job under staleBindingKeys",
               out.get("staleBindingKeys") == ["stale-1"], res.show())
        res = fx.cli("flush")
        _check("[taskandi-v2] AC9: flush exits 1 with BINDING_CHANGED naming the stale key",
               res.rc == 1 and "binding changed" in res.err and "stale-1" in res.err, res.show())
        _check("[taskandi-v2] AC9: stale binding dispatches nothing and sends zero tools/call",
               fx.tool_calls() == [], repr(fx.tool_calls()))
        _check("[taskandi-v2] AC9: every queued job stays queued after the refusal",
               (fx.job("stale-1") or {}).get("state") == "queued" and (fx.job("fresh") or {}).get("state") == "queued",
               repr(fx.jobs()))

    with _Fx() as fx:
        fx.write_state({"version": 1, "jobs": [
            {"key": "hw-time", "kind": "record_time", "digest": "x", "payload": {"task": _BIND, "seconds": 60,
             "started_at": "2026-10-30T21:00:00Z", "actor": "agent"}, "binding": None, "channel": "taskandi-mcp",
             "state": "uncertain", "lastError": "fixture"},
            _stored_comment_job("hw-c2", "uncertain")],
            "reconciliationLog": [], "cursor": None, "answers": [], "conflicts": []})
        res = fx.cli("reconcile", "--key", "hw-time", "--action", "retry", "--evidence", "checked by operator")
        _check("[taskandi-v2] AC9: reconcile retry requeues an uncertain record_time job",
               res.rc == 0 and (fx.job("hw-time") or {}).get("state") == "queued", res.show())
        res = fx.cli("reconcile", "--key", "hw-c2", "--action", "done", "--evidence", "checked by operator")
        _check("[taskandi-v2] AC9: reconcile done closes an uncertain comment job",
               res.rc == 0 and (fx.job("hw-c2") or {}).get("state") == "done", res.show())
        fx.cli("enqueue", "comment", "--key", "queued-c", stdin=json.dumps({"text": "q"}))
        res = fx.cli("reconcile", "--key", "queued-c", "--action", "done", "--evidence", "x")
        _check("[taskandi-v2] AC9 control: reconcile refuses a job that is not uncertain",
               res.rc == 1 and (fx.job("queued-c") or {}).get("state") == "queued", res.show())


# ---------------------------------------------------------------------------
# AC10 v1 regression, diff rule, unbound parity
# ---------------------------------------------------------------------------

_OLD_REV = re.compile(r"(?<![A-Z_])CONTRACT_REVISION\b")
_V1_TO_KEY = re.compile(r"""[{,]\s*["']?to["']?\s*:""")


def _allowed_minus(line: str, plus_pool: list) -> str | None:
    """Kind (a): CONTRACT_REVISION replaced by LEGACY_CONTRACT_REVISION (paired plus line exists).
    Kind (b): a v1-shaped ask payload line carrying `to`, rewritten to v2.1 shape."""
    if _OLD_REV.search(line):
        expected = _OLD_REV.sub("LEGACY_CONTRACT_REVISION", line)
        if expected in plus_pool:
            plus_pool.remove(expected)
            return "a"
        return None
    if _V1_TO_KEY.search(line) and "question" in line:
        return "b"
    return None


def _allowed_plus(line: str) -> str | None:
    if "LEGACY_CONTRACT_REVISION" in line:
        return "a"
    if "estimate_minutes" in line and "reversible" in line and "question" in line and not _V1_TO_KEY.search(line):
        return "b"
    return None


def test_taskandi_v2_ac10_v1_regression_and_diff() -> None:
    """AC10 (part 1). Runs the two v1 test files and applies the diff rule.  If the v1 files
    had any other edit, a `-` or `+` line would fall outside both allowed kinds.  The classifier's
    own controls: a known-good pair is accepted and an arbitrary removed assertion is refused."""
    print("[taskandi-v2] AC10 v1 regression and diff rule")
    for name in ("checks_28_taskandi_client.py", "checks_29_taskandi_binding_usage.py"):
        res = subprocess.run(["python3", f"smoke/{name}"], cwd=str(_REPO), input="", capture_output=True, text=True, timeout=600)
        _check(f"[taskandi-v2] AC10: python3 smoke/{name} exits 0", res.returncode == 0, (res.stdout + res.stderr)[-2000:])

    diff = subprocess.run(["git", "-C", str(_REPO), "diff", "HEAD", "--",
                           "smoke/checks_28_taskandi_client.py", "smoke/checks_29_taskandi_binding_usage.py"],
                          input="", capture_output=True, text=True, timeout=60).stdout
    minus, plus = [], []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line.startswith("-"):
            minus.append(line[1:])
        elif line.startswith("+"):
            plus.append(line[1:])
    pool = list(plus)
    kinds_minus = [_allowed_minus(line, pool) for line in minus]
    kinds_plus = [_allowed_plus(line) for line in plus]
    bad_minus = [line for line, kind in zip(minus, kinds_minus) if kind is None]
    bad_plus = [line for line, kind in zip(plus, kinds_plus) if kind is None]
    _check("[taskandi-v2] AC10: every removed line is kind (a) or kind (b)", not bad_minus, repr(bad_minus))
    _check("[taskandi-v2] AC10: every added line is kind (a) or kind (b)", not bad_plus, repr(bad_plus))
    # The diff rule guards the one uncommitted task_061 edit; once committed the
    # diff against HEAD is empty, so "both kinds present" only applies while a
    # diff exists (a permanent test must not depend on an uncommitted tree).
    _check("[taskandi-v2] AC10 control: any uncommitted diff contains both allowed kinds",
           not diff.strip() or ("a" in kinds_minus and "b" in kinds_minus and "a" in kinds_plus and "b" in kinds_plus),
           repr((kinds_minus, kinds_plus)))
    _check("[taskandi-v2] AC10 control: classifier refuses an arbitrary removed assertion",
           _allowed_minus("-  assert.equal(x, 1)", []) is None and _allowed_minus("check('x', True)", []) is None)


def test_taskandi_v2_ac10_unbound_parity() -> None:
    """AC10 (part 2). Mechanism: loadConfig unbound branch and FALLBACK short-circuit.  If an
    unbound direct call reached the network, the request log would be non-empty.  Positive control:
    each enqueue kind does write a file-fallback job, so the state path is live."""
    print("[taskandi-v2] AC10 unbound parity")
    with _Fx(bound=False) as fx:
        enqueues = [
            ("ask", _full_ask()),
            ("comment", {"text": "c"}),
            ("record_usage", {"account": "a", "model": "m", "input": 1, "output": 1, "cache_read": 0, "cache_write": 0, "cost_estimate": 0}),
            ("record_time", {"seconds": 1, "started_at": "2026-10-30T21:00:00Z"}),
        ]
        for kind, payload in enqueues:
            key = f"u-{kind}"
            res = fx.cli("enqueue", kind, "--key", key, stdin=json.dumps(payload))
            job = fx.job(key) or {}
            _check(f"[taskandi-v2] AC10: unbound enqueue {kind} writes a file-fallback job",
                   res.rc == 0 and job.get("channel") == "file-fallback" and job.get("binding") is None, res.show())
        for args in (["flush"], ["poll"], ["next-task", "--agent", "claude", "--session", "sess-1"],
                     ["complete", "--task", _CLAIM, "--summary", "s"], ["release", "--task", _CLAIM, "--reason", "r"]):
            res = fx.cli(*args)
            _check(f"[taskandi-v2] AC10: unbound {args[0]} reports bound false and exits 0",
                   res.rc == 0 and (res.json() or {}).get("bound") is False, res.show())
        _check("[taskandi-v2] AC10: unbound project made zero transport requests", fx.requests() == [], repr(fx.requests()))


# ---------------------------------------------------------------------------
# AC11 Usage importer
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac11_usage_importer() -> None:
    """AC11. Mechanism: resolveTask targeting in enqueueTranscriptUsage.  If resolveTask were
    absent, `--task ABBR-999` would enqueue records and exit 0.  Positive control: the default run
    enqueues records whose task is the binding task."""
    print("[taskandi-v2] AC11 usage importer")
    with _Fx() as fx:
        transcript = fx.base / "session.jsonl"
        _write_transcript(transcript)
        base_args = ["usage", "--transcript", str(transcript), "--account", "a", "--cost-estimate", "0"]
        res = fx.cli(*base_args, "--session", "s-bind")
        usage_jobs = [j for j in fx.jobs() if j["kind"] == "record_usage"]
        _check("[taskandi-v2] AC11: default usage import exits 0 and enqueues record_usage jobs",
               res.rc == 0 and len(usage_jobs) >= 1, res.show())
        _check("[taskandi-v2] AC11: every usage record carries the binding task",
               usage_jobs and all(j["payload"].get("task") == _BIND for j in usage_jobs), repr(usage_jobs))
        _claim(fx)
        res = fx.cli(*base_args, "--session", "s-claim", "--task", _CLAIM)
        claim_jobs = [j for j in fx.jobs() if j["kind"] == "record_usage" and j["payload"].get("task") == _CLAIM]
        _check("[taskandi-v2] AC11: --task with the claimed task sets task on every record",
               res.rc == 0 and len(claim_jobs) >= 1, res.show())
        before = len(fx.jobs())
        res = fx.cli(*base_args, "--session", "s-neither", "--task", "ABBR-999")
        _check("[taskandi-v2] AC11: --task neither bound nor claimed exits 1 and enqueues nothing",
               res.rc == 1 and len(fx.jobs()) == before, res.show())


# ---------------------------------------------------------------------------
# AC12 Docs, usage string, changelog
# ---------------------------------------------------------------------------

_FIELD_NAMES = ["task", "agent", "session", "question", "default", "order", "estimate_minutes", "remaining_minutes",
                "reversible", "since", "text", "account", "model", "input", "output", "cache_read", "cache_write",
                "cost_estimate", "source", "source_ref", "seconds", "started_at", "actor", "summary", "reason"]
_TOOL_NAMES = ["next_task", "ask", "list_asks", "comment", "record_usage", "record_time", "complete", "release"]


def test_taskandi_v2_ac12_docs_usage_changelog() -> None:
    """AC12. Grep-based: docs, the bad-usage string and CHANGELOG.  The gate runs (code-check,
    smoke-test) are the lead's commands, not asserted here.  Mechanism: the docs text.  If a token
    were absent from docs/taskandi-client.md, the corresponding check fails.  Positive control:
    the same regex finds the token in the copy that is present."""
    print("[taskandi-v2] AC12 docs, usage string, changelog")
    docs = _DOCS.read_text() if _DOCS.exists() else ""
    _check("[taskandi-v2] AC12 control: docs file is readable and non-empty", len(docs) > 0, str(_DOCS))
    literals = [_CONTRACT, _LEGACY, "next-task", "complete --task", "release --task", "staleBindingKeys",
                "owner_answer", "untrusted"]
    missing = [s for s in literals if s not in docs]
    _check("[taskandi-v2] AC12: docs contain the contract strings and required terms", not missing, repr(missing))
    missing_tools = [t for t in _TOOL_NAMES if not re.search(r"\b" + re.escape(t) + r"\b", docs)]
    _check("[taskandi-v2] AC12: docs name every v2.1 tool", not missing_tools, repr(missing_tools))
    missing_fields = [f for f in _FIELD_NAMES if not re.search(r"\b" + re.escape(f) + r"\b", docs)]
    _check("[taskandi-v2] AC12: docs name every required field from the table", not missing_fields, repr(missing_fields))

    res = subprocess.run(["node", str(_CLIENT), "bogus-command"], cwd=str(_REPO), input="", capture_output=True,
                         text=True, timeout=30, env=_sanitized_env())
    _check("[taskandi-v2] AC12: bad usage exits 1", res.returncode == 1, res.stderr)
    missing_usage = [w for w in ["next-task", "complete --task", "release --task", "comment", "record_time"] if w not in res.stderr]
    _check("[taskandi-v2] AC12: CLI usage string names next-task, complete, release, comment and record_time",
           not missing_usage, repr(missing_usage) + " " + res.stderr)
    changelog = _CHANGELOG.read_text() if _CHANGELOG.exists() else ""
    _check("[taskandi-v2] AC12: CHANGELOG mentions vibe-agent-exchange-v2.1", _CONTRACT in changelog)


# ---------------------------------------------------------------------------
# AC13 No secret or payload leakage
# ---------------------------------------------------------------------------

def test_taskandi_v2_ac13_no_leakage() -> None:
    """AC13. Mechanism: status and error paths print no token, question, comment or answer text.
    If the status or error paths echoed payloads, a sentinel would appear in stdout or stderr.
    Positive controls: each sentinel is observably stored (state file) or sent (request log) first,
    so its absence from output is meaningful."""
    print("[taskandi-v2] AC13 no secret or payload leakage")
    with _Fx(token=_TOKEN_SENTINEL) as fx:
        fx.cli("enqueue", "ask", "--key", "q-1", stdin=json.dumps(_full_ask(question=_QUESTION_SENTINEL)))
        fx.cli("enqueue", "comment", "--key", "c-s", stdin=json.dumps({"text": _COMMENT_SENTINEL}))
        fx.set_call("list_asks", {"result": _page(_C0, _cur(1, "c1"), [_ans("A1", _ANSWER_SENTINEL, True)])})
        res = fx.cli("poll")
        _check("[taskandi-v2] AC13 setup: poll stored the answer sentinel", res.rc == 0, res.show())
        fx.set_call("ask", {"result": {"ask_id": "ASK-1", "placed": "subtask"}})
        fx.set_call("comment", {"result": {}})
        res = fx.cli("flush")
        _check("[taskandi-v2] AC13 control: flush sent authorization with the token sentinel",
               res.rc == 0 and any(r.get("authorization") == f"Bearer {_TOKEN_SENTINEL}" for r in fx.requests()), res.show())
        state_text = (fx.root / ".vibe" / "taskandi-outbox" / "state.json").read_text()
        _check("[taskandi-v2] AC13 control: question, comment and answer sentinels are stored in state",
               all(s in state_text for s in (_QUESTION_SENTINEL, _COMMENT_SENTINEL, _ANSWER_SENTINEL)))
        res = fx.cli("status")
        leaked = [s for s in _SENTINELS if s in res.out or s in res.err]
        _check("[taskandi-v2] AC13: status stdout contains no token, question, comment or answer sentinel",
               res.rc == 0 and not leaked, f"leaked={leaked} {res.show()}")

        fx.cli("enqueue", "ask", "--key", "q-2", stdin=json.dumps({**_full_ask(question=_QUESTION_SENTINEL), "to": "x"}))
        fx.cli("enqueue", "comment", "--key", "c-2", stdin=json.dumps({"text": _COMMENT_SENTINEL, "extra": 1}))
        fx.set_call("list_asks", {"result": _page(_cur(1, "c1"), _cur(2, "c2"), [{"ask_id": "A9", "answer": _ANSWER_SENTINEL, "owner_answer": True}])})
        fx.set_call("next_task", {"result": {**_next_obj(), "title": _ANSWER_SENTINEL, "lease": {"until": "soon", "session": "s"}}})
        fx.set_call("complete", {"transport": "boom"})
        fx.set_call("next_task", {"result": {**_next_obj(), "title": _ANSWER_SENTINEL, "lease": {"until": "soon", "session": "s"}}})
        fx.cli("enqueue", "ask", "--key", "q-4", stdin=json.dumps(_full_ask(question=_QUESTION_SENTINEL)))
        fx.set_tools([t if t["name"] != "ask" else {**t, "inputSchema": {**t["inputSchema"], "required": [r for r in t["inputSchema"]["required"] if r != "reversible"]}}
                      for t in fx._tools])
        failing = {
            "ask unknown key with question sentinel": ["enqueue", "ask", "--key", "q-3"],
            "comment extra key with comment sentinel": ["enqueue", "comment", "--key", "c-3"],
            "poll malformed page with answer sentinel": ["poll"],
            "flush schema drift with queued ask": ["flush"],
            "next-task invalid result with sentinel title": ["next-task", "--agent", "claude", "--session", "sess-1"],
            "complete post-send failure": ["complete", "--task", _BIND, "--summary", "s"],
        }
        stdins = {"ask unknown key with question sentinel": json.dumps({**_full_ask(question=_QUESTION_SENTINEL), "to": "x"}),
                  "comment extra key with comment sentinel": json.dumps({"text": _COMMENT_SENTINEL, "extra": 1})}
        for label, args in failing.items():
            res = fx.cli(*args, stdin=stdins.get(label, ""))
            leaked = [s for s in _SENTINELS if s in res.err or s in res.out]
            _check(f"[taskandi-v2] AC13: failing command ({label}) exits non-zero with a stderr line and no sentinel",
                   res.rc != 0 and res.err.strip() != "" and not leaked, f"leaked={leaked} {res.show()}")

    with _Fx() as fx:
        fx.set_call("next_task", {"redirect": "https://evil.invalid/mcp"})
        res = fx.cli("next-task", "--agent", "claude", "--session", "sess-1")
        _check("[taskandi-v2] AC13: a redirect to another origin exits 1 with empty stdout",
               res.rc == 1 and res.out == "" and "redirects are refused" in res.err, res.show())
        urls = [r["url"] for r in fx.requests()]
        _check("[taskandi-v2] AC13: the recorder saw no request to the other origin and no credential for it",
               urls and all(u.startswith("https://fixture.invalid/") for u in urls)
               and not any("evil.invalid" in (r.get("authorization") or "") or "evil.invalid" in r["url"] for r in fx.requests()),
               repr(urls))
    with _Fx() as fx:
        out = _lib("try { globalThis.fetch = async () => ({ status: 307, headers: new Headers({ location: 'https://evil.invalid/mcp' }), body: null });"
                   " await C.fetchTransport({ url: 'https://fixture.invalid/mcp', origin: 'https://fixture.invalid', headers: {}, body: {} });"
                   " out.code = 'none'; } catch (e) { out.code = e.code ?? null; out.message = e.message; }", fx.root)
        _check("[taskandi-v2] AC13: fetchTransport refuses a redirect",
               "redirect" in str(out.get("message")), repr(out))
        _check("[taskandi-v2] AC13: the refused redirect is a post-send failure, not PREDISPATCH (spec rev 4)",
               out.get("code") not in (None, "none", "PREDISPATCH"), repr(out))


def _run_all() -> None:
    for fn in [test_taskandi_v2_ac1_revision_handling, test_taskandi_v2_ac1_v1_gate_refusals,
               test_taskandi_v2_ac2_ask_validation, test_taskandi_v2_ac3_task_targeting,
               test_taskandi_v2_ac4_comment_time_usage, test_taskandi_v2_ac5_flush_v21_fixture,
               test_taskandi_v2_ac5_flush_schema_drift_and_ask_results, test_taskandi_v2_ac6_next_task,
               test_taskandi_v2_ac7_poll_v21, test_taskandi_v2_ac8_complete_release,
               test_taskandi_v2_ac8b_direct_call_predispatch, test_taskandi_v2_ac9_outbox_invariants,
               test_taskandi_v2_ac10_v1_regression_and_diff, test_taskandi_v2_ac10_unbound_parity,
               test_taskandi_v2_ac11_usage_importer, test_taskandi_v2_ac12_docs_usage_changelog,
               test_taskandi_v2_ac13_no_leakage]:
        try:
            fn()
        except Exception as error:  # a crashed test is a failed test, never a silent pass
            _check(f"[taskandi-v2] {fn.__name__} raised", False, repr(error))


if __name__ == "__main__":
    _run_all()
    passed = sum(_RESULTS)
    print(f"total: {len(_RESULTS)} passed: {passed} failed: {len(_RESULTS) - passed}")
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        raise SystemExit(1)
    print("PASS: Task&I contract v2.1 acceptance checks")
