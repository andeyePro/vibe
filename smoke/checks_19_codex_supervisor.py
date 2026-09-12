"""task_048: codex-supervisor as an app-server client — authored independently
by the Tester (spec-only read: `.vs/spec.md`, `smoke/_core.py`,
`smoke/checks_18_codex_runtime.py` for conventions, the protocol facts
scratchpad, and the current source tree; no Generator report/diff consulted,
own stub `codex` app-server built from scratch).

Covers AC10's test list against `devcontainer/codex-supervisor.mjs`:
  - AC2 prefix rewrite (REWRITES table + CLI exercise).
  - AC3 spawn/handshake: argv, env, initialize shape, rateLimits ordering.
  - AC4 thread lifecycle: first run, promptHash/cwd mismatch, --new-run
    archive, resume after a kill.
  - AC5 turn loop: normal completion, continue-then-exit, quota (known and
    blind resetsAt), transient 429, exec-policy-forbidden retry (same
    text), sessionBudgetExceeded, interrupted, unattended approval
    requests, a non-terminal `error willRetry:true`.
  - AC7 gates: max-turns, max-quota-waits, max-wall-seconds (mid quota
    wait), and the VSSS-EXIT/`continue` exit contract.
  - AC8 safety: SIGTERM -> exit 130 -> resume with thread/resume + a fresh
    turn/start, never turn/steer; no file written under --cwd beyond
    .vss/codex-supervisor.{json,log} (+ the --new-run archive).
  - AC1 usage errors: relative --cwd, missing CODEX_HOME, generic bad args
    -> exit 2, nothing spawned.
  - AC9 docs: vsss.md's exit section + "Running under Codex" note,
    README's mention, and the plan's D7 method names.

The stub `codex` binary is a small Python program (not read from the
Generator's cycle-1 scratch tests — written fresh here) that speaks the
newline-delimited-JSON app-server wire format described in
`scratchpad/codex-appserver.md`: no `jsonrpc` field, `initialize` ->
`{id,result:{userAgent,codexHome,platformFamily,platformOs}}`,
`account/rateLimits/read` -> `{id,result:{rateLimits:{primary,secondary}}}`,
`thread/start`/`thread/resume` -> `{id,result:{thread:{id}}}`, `turn/start`
-> `{id,result:{turn:{id,status:"inProgress"}}}` followed by a scripted
sequence of notifications (and optional server->client requests) ending in
`turn/completed`. Scenarios are JSON fixtures written per-test next to the
stub script and self-located via `Path(__file__).parent` — the supervisor's
own spawn() env is deliberately restricted to exactly {PATH,HOME,CODEX_HOME,
LANG} (AC3), so the stub cannot receive scenario data via environment
variables and instead reads sibling files."""
from smoke._core import *  # noqa: F401,F403

import signal
import time
import hashlib

SUPERVISOR = REPO / "devcontainer" / "codex-supervisor.mjs"
CODEX_INTEGRATION_PLAN_MD = REPO / "docs" / "codex-integration-plan.md"


# ── the stub `codex` binary ──────────────────────────────────────────────
#
# Self-locating: reads `fixture.json`, writes `stub.log` (every incoming and
# outgoing line, prefixed IN/OUT) and `meta.json` (argv + env, written
# before anything else so a failure-to-spawn assertion still has something
# to check against a NON-existent file) in its own directory — never via
# environment variables, since the supervisor's child env is pinned to
# exactly {PATH,HOME,CODEX_HOME,LANG}.
_CODEX_STUB_SRC = '''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "stub.log"
META = HERE / "meta.json"


def log(prefix, line):
    with LOG.open("a") as f:
        f.write(f"{prefix} {line}\\n")


def send(obj):
    line = json.dumps(obj)
    sys.stdout.write(line + "\\n")
    sys.stdout.flush()
    log("OUT", line)


def read_line():
    line = sys.stdin.readline()
    if line == "":
        return None
    line = line.rstrip("\\n")
    log("IN", line)
    return line


def substitute(obj, turn_id, thread_id):
    if isinstance(obj, dict):
        return {k: substitute(v, turn_id, thread_id) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, turn_id, thread_id) for v in obj]
    if isinstance(obj, str):
        return obj.replace("__TURN_ID__", turn_id).replace("__THREAD_ID__", thread_id)
    return obj


def main():
    argv = sys.argv[1:]
    META.write_text(json.dumps({"argv": argv, "env": dict(os.environ)}))
    if argv != ["app-server"]:
        sys.exit(1)

    fixture = json.loads((HERE / "fixture.json").read_text())
    thread_id = fixture.get("threadId", "11111111-1111-1111-1111-111111111111")
    rate_limits_list = fixture.get("rateLimits", [])
    rl_index = 0
    turns = fixture.get("turns", [])
    turn_index = 0
    handshake = fixture.get("handshake", {})
    next_req_id = 100000

    while True:
        line = read_line()
        if line is None:
            break
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method = msg.get("method")
        mid = msg.get("id")

        if method == "initialize":
            send({"id": mid, "result": {
                "userAgent": handshake.get("userAgent", "codex-stub/1.0"),
                "codexHome": handshake.get("codexHome", "/tmp/.codex"),
                "platformFamily": handshake.get("platformFamily", "unix"),
                "platformOs": handshake.get("platformOs", "linux"),
            }})
        elif method == "account/rateLimits/read":
            if rate_limits_list:
                rl = rate_limits_list[min(rl_index, len(rate_limits_list) - 1)]
                rl_index += 1
            else:
                rl = {"primary": None, "secondary": None}
            send({"id": mid, "result": {"rateLimits": rl}})
        elif method in ("thread/start", "thread/resume"):
            send({"id": mid, "result": {"thread": {"id": thread_id}}})
        elif method == "turn/start":
            idx = turn_index
            turn_index += 1
            if idx >= len(turns):
                tid = f"turn-{idx}"
                send({"id": mid, "result": {"turn": {"id": tid, "status": "inProgress"}}})
                send({"method": "turn/completed",
                      "params": {"threadId": thread_id, "turn": {"id": tid, "status": "completed"}}})
                continue
            script = turns[idx]
            tid = script.get("turnId", f"turn-{idx}")
            send({"id": mid, "result": {"turn": {"id": tid, "status": "inProgress"}}})
            for event in script.get("events", []):
                event = substitute(event, tid, thread_id)
                if "sleep" in event:
                    time.sleep(event["sleep"])
                    continue
                if "request" in event:
                    req = event["request"]
                    rid = next_req_id
                    next_req_id += 1
                    send({"id": rid, "method": req["method"], "params": req.get("params", {})})
                    resp = read_line()
                    if resp is None:
                        return
                    continue
                send(event)
        else:
            if mid is not None:
                send({"id": mid, "error": {"code": -32601, "message": "stub: unhandled method"}})


if __name__ == "__main__":
    main()
'''


def _write_stub(stub_dir: Path, fixture: dict) -> Path:
    stub_dir.mkdir(parents=True, exist_ok=True)
    (stub_dir / "fixture.json").write_text(json.dumps(fixture))
    stub_path = stub_dir / "codex"
    stub_path.write_text(_CODEX_STUB_SRC)
    stub_path.chmod(0o755)
    return stub_path


def _stub_log_lines(stub_dir: Path) -> list[str]:
    log_path = stub_dir / "stub.log"
    if not log_path.exists():
        return []
    return log_path.read_text().splitlines()


def _stub_meta(stub_dir: Path) -> dict | None:
    meta_path = stub_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except json.JSONDecodeError:
        return None


def _in_messages(stub_dir: Path) -> list[dict]:
    out = []
    for line in _stub_log_lines(stub_dir):
        if line.startswith("IN "):
            try:
                out.append(json.loads(line[3:]))
            except json.JSONDecodeError:
                pass
    return out


# ── event-building helpers (fixture authoring) ───────────────────────────

def _turn_started_event() -> dict:
    return {"method": "turn/started",
            "params": {"threadId": "__THREAD_ID__", "turn": {"id": "__TURN_ID__", "status": "inProgress"}}}


def _agent_message_event(item_id: str, text: str) -> dict:
    return {"method": "item/completed",
            "params": {"threadId": "__THREAD_ID__", "turnId": "__TURN_ID__",
                       "item": {"id": item_id, "type": "agentMessage", "text": text}}}


def _turn_completed_event(status: str, error: dict | None = None) -> dict:
    turn = {"id": "__TURN_ID__", "status": status}
    if error is not None:
        turn["error"] = error
    return {"method": "turn/completed", "params": {"threadId": "__THREAD_ID__", "turn": turn}}


def _rate_limits_updated_event(rate_limits: dict) -> dict:
    return {"method": "account/rateLimits/updated", "params": {"rateLimits": rate_limits}}


def _willretry_error_event() -> dict:
    return {"method": "error", "params": {"error": {"message": "transient hiccup, retrying"},
                                           "willRetry": True, "threadId": "__THREAD_ID__",
                                           "turnId": "__TURN_ID__"}}


# ── supervisor invocation helpers ────────────────────────────────────────

def _supervisor_fixture(tmp: Path):
    """A temp home/.codex/workspace triple. Returns (home, codex_home,
    workspace, env) — env is the EXACT four-key set the supervisor itself
    reads from process.env (PATH/HOME/CODEX_HOME/LANG); passing anything
    else here is meaningless since spawnServer() only forwards these four
    to the child regardless of what this test process's own env carries."""
    home = tmp / "home"
    home.mkdir()
    codex_home = home / ".codex"
    codex_home.mkdir()
    workspace = tmp / "ws"
    workspace.mkdir()
    r = run(["git", "init", "-q"], cwd=workspace)
    check("[codex-supervisor] fixture: git init succeeds", r.returncode == 0, r.stderr)
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "LANG": "C.UTF-8",
    }
    return home, codex_home, workspace, env


def _run_supervisor(args: list[str], env: dict, timeout: int = 30) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        ["node", str(SUPERVISOR), *args],
        capture_output=True, text=True, env=env,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )


def _read_state(workspace: Path, state_path: Path | None = None) -> dict:
    path = state_path or (workspace / ".vss" / "codex-supervisor.json")
    return json.loads(path.read_text())


def _extra_files_under_cwd(workspace: Path) -> list[str]:
    """Every file under workspace not accounted for by the supervisor's
    documented footprint: the main state/log pair, or a --new-run archive
    named codex-supervisor.<startedAt>.json. .git/ is pre-existing fixture
    scaffolding, not something the supervisor wrote."""
    allowed = {".vss/codex-supervisor.json", ".vss/codex-supervisor.log"}
    archive_re = re.compile(r"^\.vss/codex-supervisor\.\d+\.json$")
    found = []
    for p in workspace.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(workspace).as_posix()
        if rel.startswith(".git/") or rel == ".git":
            continue
        if rel in allowed or archive_re.match(rel):
            continue
        found.append(rel)
    return found


_DONE_TURN_EVENTS = lambda item_id, reason: [  # noqa: E731
    _turn_started_event(),
    _agent_message_event(item_id, f"Wrapping up.\nVSSS-EXIT: {reason}\n"),
    _turn_completed_event("completed"),
]


# ── AC2: the REWRITES table ───────────────────────────────────────────────

def test_codex_supervisor_rewrites_table():
    print("\n[codex-supervisor] AC2 REWRITES table exported and correct")
    r = subprocess.run(
        ["node", "-e",
         f"import('{SUPERVISOR.as_posix()}').then(m=>console.log(JSON.stringify(m.REWRITES)))"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30,
    )
    check("[codex-supervisor] node import of the module succeeds", r.returncode == 0, r.stderr)
    if r.returncode != 0:
        return
    try:
        table = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        check("[codex-supervisor] REWRITES output is valid JSON", False, f"{exc}: {r.stdout}")
        return
    check("[codex-supervisor] REWRITES == {'/vs':'$vs','/vss':'$vss','/vsss':'$vsss'}",
          table == {"/vs": "$vs", "/vss": "$vss", "/vsss": "$vsss"}, str(table))


def test_codex_supervisor_prefix_rewrite_cli():
    print("\n[codex-supervisor] AC2 prefix rewrite exercised through the CLI + stub echo")
    cases = [
        ("/vs do a thing", "$vs do a thing"),
        ("/vss do a thing", "$vss do a thing"),
        ("/vsss do a thing", "$vsss do a thing"),
        ("$vs do a thing", "$vs do a thing"),
        ("/vss:foo bar", "/vss:foo bar"),
        ("/VS do a thing", "/VS do a thing"),
    ]
    for prompt_text, expected in cases:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home, codex_home, workspace, env = _supervisor_fixture(tmp)
            stub_dir = tmp / "stub"
            fixture = {"turns": [{"events": _DONE_TURN_EVENTS("i1", "done")}]}
            stub_path = _write_stub(stub_dir, fixture)
            prompt = tmp / "prompt.txt"
            prompt.write_text(prompt_text)
            r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                                  "--codex-bin", str(stub_path)], env)
            check(f"[codex-supervisor] prefix-rewrite fixture {prompt_text!r} exits 0",
                  r.returncode == 0, r.stderr)
            turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
            got = None
            if turn_starts:
                inp = turn_starts[0].get("params", {}).get("input", [])
                if inp:
                    got = inp[0].get("text")
            check(f"[codex-supervisor] {prompt_text!r} -> {expected!r} on the wire",
                  got == expected, f"got={got!r}")


# ── AC3: spawn/handshake ─────────────────────────────────────────────────

def test_codex_supervisor_handshake_argv_env():
    print("\n[codex-supervisor] AC3 spawn/handshake — argv, env, initialize, rateLimits ordering")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": _DONE_TURN_EVENTS("i1", "done")}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] handshake fixture run exits 0", r.returncode == 0, r.stderr)

        meta = _stub_meta(stub_dir)
        check("[codex-supervisor] stub meta.json was written (spawned)", meta is not None, "")
        if meta is not None:
            check("[codex-supervisor] argv is exactly ['app-server']",
                  meta["argv"] == ["app-server"], str(meta["argv"]))
            check("[codex-supervisor] child env is the allowlisted base plus unbound Task&I fingerprint",
                  set(meta["env"].keys()) == {"PATH", "HOME", "CODEX_HOME", "LANG", "VIBE_TASK_BINDING"}
                  and meta["env"].get("VIBE_TASK_BINDING") == "unbound",
                  str(sorted(meta["env"].keys())))
            check("[codex-supervisor] child CODEX_HOME matches --cwd's env",
                  meta["env"].get("CODEX_HOME") == str(codex_home), meta["env"].get("CODEX_HOME"))

        msgs = _in_messages(stub_dir)
        check("[codex-supervisor] at least 2 messages received before any turn",
              len(msgs) >= 2, str(msgs[:3]))
        if len(msgs) >= 2:
            init = msgs[0]
            check("[codex-supervisor] first message is initialize, id 1",
                  init.get("id") == 1 and init.get("method") == "initialize", str(init))
            params = init.get("params", {})
            check("[codex-supervisor] initialize clientInfo.name == vibe-codex-supervisor",
                  params.get("clientInfo", {}).get("name") == "vibe-codex-supervisor", str(params))
            check("[codex-supervisor] initialize capabilities == {}",
                  params.get("capabilities") == {}, str(params))

            rl = msgs[1]
            check("[codex-supervisor] second message is account/rateLimits/read, id 2",
                  rl.get("id") == 2 and rl.get("method") == "account/rateLimits/read", str(rl))

        turn_start_idx = next((i for i, m in enumerate(msgs) if m.get("method") == "turn/start"), None)
        check("[codex-supervisor] account/rateLimits/read precedes turn/start",
              turn_start_idx is not None and turn_start_idx > 1, f"turn_start_idx={turn_start_idx}")


# ── AC1: usage errors, nothing spawned ────────────────────────────────────

def test_codex_supervisor_usage_errors_no_spawn():
    print("\n[codex-supervisor] AC1 invalid arguments -> exit 2, nothing spawned")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss hello")
        cases = [
            ["run", "--prompt-file", str(prompt), "--codex-bin", str(stub_path)],
            ["run", "--cwd", str(workspace), "--codex-bin", str(stub_path)],
            ["run", "--cwd", str(workspace), "--prompt-file", str(prompt), "--bogus-flag", "x"],
            ["bogus-command"],
        ]
        for args in cases:
            r = _run_supervisor(args, env)
            check(f"[codex-supervisor] usage error exits 2: {args}",
                  r.returncode == 2, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] usage errors never spawned the stub",
              not (stub_dir / "meta.json").exists(), "")


def test_codex_supervisor_relative_cwd_exit2_no_spawn():
    print("\n[codex-supervisor] AC1 --cwd relative -> exit 2, nothing spawned")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", "relative/dir", "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] relative --cwd exits 2", r.returncode == 2, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names the absolute-path requirement",
              "absolute" in r.stderr, r.stderr)
        check("[codex-supervisor] relative --cwd never spawned the stub",
              not (stub_dir / "meta.json").exists(), "")


def test_codex_supervisor_missing_codex_home_exit2_no_spawn():
    print("\n[codex-supervisor] AC1 missing CODEX_HOME dir -> exit 2, nothing spawned")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        env = dict(env)
        env["CODEX_HOME"] = str(tmp / "does-not-exist")
        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] missing CODEX_HOME exits 2", r.returncode == 2, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names CODEX_HOME", "CODEX_HOME" in r.stderr, r.stderr)
        check("[codex-supervisor] missing CODEX_HOME never spawned the stub",
              not (stub_dir / "meta.json").exists(), "")


# ── AC5/AC7: turn loop and the exit contract ─────────────────────────────

def test_codex_supervisor_normal_completion():
    print("\n[codex-supervisor] AC5/AC7 normal completion with VSSS-EXIT -> exit 0")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [
            _turn_started_event(),
            _willretry_error_event(),  # AC5: willRetry:true is logged and ignored, not terminal
            _agent_message_event("i1", "All done.\nVSSS-EXIT: done\n"),
            _turn_completed_event("completed"),
        ]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] normal completion exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] state.exitReason == 'done'", state.get("exitReason") == "done", str(state))
        check("[codex-supervisor] state.turns has exactly 1 entry (willRetry error was non-terminal)",
              len(state.get("turns", [])) == 1, str(state))
        vss_dir = workspace / ".vss"
        check("[codex-supervisor] no .tmp file left behind (atomic write+rename)",
              not any(p.name.endswith(".tmp") for p in vss_dir.iterdir()), str(list(vss_dir.iterdir())))
        extra = _extra_files_under_cwd(workspace)
        check("[codex-supervisor] no file written under --cwd beyond .vss/codex-supervisor.{json,log}",
              extra == [], str(extra))


def test_codex_supervisor_continue_then_exit():
    print("\n[codex-supervisor] AC7 completion without exit line -> literal 'continue' -> exit line")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(), _agent_message_event("i1", "Nothing special yet."),
                        _turn_completed_event("completed")]},
            {"events": _DONE_TURN_EVENTS("i2", "done2")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] two-turn run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] state.turns has exactly 2 entries", len(state.get("turns", [])) == 2, str(state))
        check("[codex-supervisor] state.exitReason == 'done2'", state.get("exitReason") == "done2", str(state))
        msgs = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] exactly 2 turn/start calls", len(msgs) == 2, str(msgs))
        if len(msgs) == 2:
            text2 = msgs[1].get("params", {}).get("input", [{}])[0].get("text")
            check("[codex-supervisor] second turn's input text is the literal word 'continue'",
                  text2 == "continue", repr(text2))


def test_codex_supervisor_quota_known_resets_at():
    print("\n[codex-supervisor] AC6 usageLimitExceeded with known resetsAt -> wait resetsAt+120s -> success")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        fixture = {
            "rateLimits": [{"primary": None, "secondary": None}],
            "turns": [
                {"events": [
                    _turn_started_event(),
                    _rate_limits_updated_event({"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                                             "resetsAt": T0 + 900}, "secondary": None}),
                    _turn_completed_event("failed", {"message": "usage limit hit",
                                                      "codexErrorInfo": "usageLimitExceeded"}),
                ]},
                {"events": _DONE_TURN_EVENTS("i2", "done")},
            ],
        }
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] quota-known-reset run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] exactly one wait recorded", len(waits) == 1, str(waits))
        if waits:
            check("[codex-supervisor] wait is quota, 1020s (900 + 120s grace)",
                  waits[0].get("reason") == "quota" and waits[0].get("seconds") == 1020, str(waits[0]))
            check("[codex-supervisor] wait.until == resetsAt + grace",
                  waits[0].get("until") == T0 + 900 + 120, str(waits[0]))
        check("[codex-supervisor] state.quotaWaits == 1", state.get("quotaWaits") == 1, str(state))
        check("[codex-supervisor] state.exitReason == 'done'", state.get("exitReason") == "done", str(state))


def test_codex_supervisor_quota_blind_backoff():
    print("\n[codex-supervisor] AC6 quota failure without resetsAt -> blind backoff 300, 600, fresh reads")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        now_source = tmp / "now.txt"
        now_source.write_text("1700000000")
        fail_events = [_turn_started_event(),
                       _turn_completed_event("failed", {"message": "usage limit hit",
                                                         "codexErrorInfo": "usageLimitExceeded"})]
        fixture = {"turns": [
            {"events": fail_events},
            {"events": fail_events},
            {"events": _DONE_TURN_EVENTS("i3", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] blind-backoff run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] two waits recorded", len(waits) == 2, str(waits))
        if len(waits) == 2:
            check("[codex-supervisor] first blind wait is 300s", waits[0].get("seconds") == 300, str(waits[0]))
            check("[codex-supervisor] second blind wait is 600s", waits[1].get("seconds") == 600, str(waits[1]))
        check("[codex-supervisor] state.quotaWaits == 2", state.get("quotaWaits") == 2, str(state))
        msgs = _in_messages(stub_dir)
        rl_reads = [m for m in msgs if m.get("method") == "account/rateLimits/read"]
        check("[codex-supervisor] account/rateLimits/read called 3x (initial + one per blind retry)",
              len(rl_reads) == 3, str(rl_reads))


def test_codex_supervisor_transient_429_backoff():
    print("\n[codex-supervisor] AC5 transient httpConnectionFailed 429 -> 60s backoff -> success")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        now_source = tmp / "now.txt"
        now_source.write_text("1700000000")
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "overloaded",
                                                          "codexErrorInfo":
                                                              {"httpConnectionFailed": {"httpStatusCode": 429}}})]},
            {"events": _DONE_TURN_EVENTS("i2", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] transient-429 run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] one wait recorded, transient, 60s",
              len(waits) == 1 and waits[0].get("reason") == "transient" and waits[0].get("seconds") == 60,
              str(waits))
        check("[codex-supervisor] state.transientRetries == 1", state.get("transientRetries") == 1, str(state))


def test_codex_supervisor_turn_failure_retries_same_text():
    print("\n[codex-supervisor] AC5 exec-policy-forbidden failure -> retry SAME text, turnFailures 1")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "Forbidden: rm -rf / blocked by exec policy"})]},
            {"events": _DONE_TURN_EVENTS("i2", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt_text = "/vsss do the risky thing"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] turn-failure-retry run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] state.turnFailures == 1", state.get("turnFailures") == 1, str(state))
        msgs = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] exactly 2 turn/start calls", len(msgs) == 2, str(msgs))
        if len(msgs) == 2:
            t1 = msgs[0]["params"]["input"][0]["text"]
            t2 = msgs[1]["params"]["input"][0]["text"]
            # AC5 was amended after Astra's second review (cycle 4): the rewritten
            # prompt is sent exactly once per thread; every later turn/start,
            # including a retry after a failed turn, sends the literal `continue`
            # so the thread never repeats actions already taken. The pre-amendment
            # assertion (same text re-sent) is obsolete and flipped here by the
            # chair — the immutability rule protects against a Generator gaming a
            # test, not against the spec itself changing.
            check("[codex-supervisor] retry after a failed turn sends 'continue' (prompt sent exactly once)",
                  t1 != "continue" and t2 == "continue", f"t1={t1!r} t2={t2!r}")


def test_codex_supervisor_session_budget_exceeded_exit1():
    print("\n[codex-supervisor] AC5 sessionBudgetExceeded -> exit 1 naming it")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [
            _turn_started_event(),
            _turn_completed_event("failed", {"message": "budget exceeded",
                                              "codexErrorInfo": "sessionBudgetExceeded"}),
        ]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] sessionBudgetExceeded exits 1", r.returncode == 1, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names sessionBudgetExceeded",
              "sessionBudgetExceeded" in r.stderr, r.stderr)


def test_codex_supervisor_interrupted_exit1():
    print("\n[codex-supervisor] AC5 interrupted turn -> exit 1, never auto-restart")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [_turn_started_event(), _turn_completed_event("interrupted")]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] interrupted turn exits 1", r.returncode == 1, f"rc={r.returncode}")
        msgs = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] never auto-restarts after interruption (exactly 1 turn/start)",
              len(msgs) == 1, str(msgs))


def test_codex_supervisor_approval_request_answered():
    print("\n[codex-supervisor] AC5 server->client approval request answered, never blocks")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [
            _turn_started_event(),
            {"request": {"method": "item/commandExecution/requestApproval",
                         "params": {"command": "rm -rf /tmp/whatever"}}},
            _agent_message_event("i1", "Handled the request, moving on.\nVSSS-EXIT: done\n"),
            _turn_completed_event("completed"),
        ]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] run with an approval request still completes, exit 0",
              r.returncode == 0, r.stderr)
        log_text = "\n".join(_stub_log_lines(stub_dir)).replace(" ", "")
        check("[codex-supervisor] approval request answered with -32601 'unattended' error",
              '"code":-32601' in log_text and '"message":"unattended"' in log_text, log_text[-500:])
        state = _read_state(workspace)
        check("[codex-supervisor] state.exitReason == 'done' despite the approval request",
              state.get("exitReason") == "done", str(state))


# ── AC4/AC8: state, resume, SIGTERM, --new-run ────────────────────────────

def test_codex_supervisor_sigterm_then_resume():
    print("\n[codex-supervisor] AC8 mid-run SIGTERM -> refuse unproven resume -> "
          "evidence reconciliation -> continue-only resume")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")

        stub_dir1 = tmp / "stub1"
        fixture1 = {"turns": [{"events": [
            _turn_started_event(), {"sleep": 6},
            _agent_message_event("i1", "should never get here\nVSSS-EXIT: nope\n"),
            _turn_completed_event("completed"),
        ]}]}
        stub_path1 = _write_stub(stub_dir1, fixture1)

        proc = subprocess.Popen(
            ["node", str(SUPERVISOR), "run", "--cwd", str(workspace), "--prompt-file", str(prompt),
             "--codex-bin", str(stub_path1)],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.time() + 15
        saw_turn_start = False
        while time.time() < deadline:
            log_text = "\n".join(_stub_log_lines(stub_dir1)).replace(" ", "")
            if '"method":"turn/start"' in log_text and (_read_state(workspace).get("unresolvedTurn") or {}).get("turnId"):
                saw_turn_start = True
                break
            time.sleep(0.1)
        check("[codex-supervisor] first run reached turn/start before the kill", saw_turn_start, "")

        proc.send_signal(signal.SIGTERM)
        try:
            _, stderr1 = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr1 = proc.communicate()
        check("[codex-supervisor] SIGTERM exits 130", proc.returncode == 130,
              f"rc={proc.returncode} stderr={stderr1}")

        state1_path = workspace / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] state file exists after the kill", state1_path.exists(), "")
        state1: dict = {}
        if state1_path.exists():
            try:
                state1 = json.loads(state1_path.read_text())
            except json.JSONDecodeError as exc:
                check("[codex-supervisor] state file after kill is valid JSON", False, str(exc))
            else:
                check("[codex-supervisor] state file after kill is valid JSON", True, "")
                check("[codex-supervisor] state file has a threadId", bool(state1.get("threadId")), str(state1))

        stub_dir2 = tmp / "stub2"
        fixture2 = {"threadId": state1.get("threadId", "unknown"),
                    "turns": [{"events": _DONE_TURN_EVENTS("i2", "done")}]}
        stub_path2 = _write_stub(stub_dir2, fixture2)
        resume_args = ["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                       "--codex-bin", str(stub_path2)]
        refused = _run_supervisor(resume_args, env)
        check("[codex-supervisor] first active-turn resume refuses before any RPC",
              refused.returncode != 0 and not (stub_dir2 / "meta.json").exists(), refused.stderr)
        checkpoint = state1_path.read_bytes()
        evidence = tmp / "reconciliation.json"
        evidence.write_text(json.dumps({
            "stateHash": hashlib.sha256(checkpoint).hexdigest(),
            "threadId": state1["threadId"],
            "turnId": state1["unresolvedTurn"]["turnId"],
            "outcome": "interrupted", "effectsReviewed": True,
            "safeToContinue": True, "evidence": "reviewed the actual interrupted turn",
        }))
        reconciled = _run_supervisor(["reconcile", "--state", str(state1_path),
                                      "--evidence-file", str(evidence)], env)
        check("[codex-supervisor] exact checkpoint evidence reconciles without dispatch",
              reconciled.returncode == 0 and not (stub_dir2 / "meta.json").exists(), reconciled.stderr)
        r2 = _run_supervisor(resume_args, env)
        check("[codex-supervisor] reconciled second run (resume) exits 0", r2.returncode == 0, r2.stderr)
        msgs2 = _in_messages(stub_dir2)
        methods2 = [m.get("method") for m in msgs2]
        check("[codex-supervisor] resume run sends thread/resume", "thread/resume" in methods2, str(methods2))
        check("[codex-supervisor] resume run sends turn/start", "turn/start" in methods2, str(methods2))
        if "thread/resume" in methods2 and "turn/start" in methods2:
            check("[codex-supervisor] thread/resume precedes turn/start",
                  methods2.index("thread/resume") < methods2.index("turn/start"), str(methods2))
        resume_msg = next((m for m in msgs2 if m.get("method") == "thread/resume"), None)
        if resume_msg is not None:
            check("[codex-supervisor] thread/resume threadId matches the persisted one",
                  resume_msg.get("params", {}).get("threadId") == state1.get("threadId"), str(resume_msg))
        check("[codex-supervisor] never sends turn/steer", "turn/steer" not in methods2, str(methods2))
        starts2 = [m for m in msgs2 if m.get("method") == "turn/start"]
        check("[codex-supervisor] reconciled active-turn input is literal continue",
              len(starts2) == 1 and starts2[0].get("params", {}).get("input", [{}])[0].get("text") == "continue",
              str(starts2))
        state2 = _read_state(workspace)
        check("[codex-supervisor] state.resumes == 1 after one resume", state2.get("resumes") == 1, str(state2))


def test_codex_supervisor_prompthash_mismatch_and_new_run():
    print("\n[codex-supervisor] AC4 state promptHash/cwd mismatch -> exit 2; --new-run archives it")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss real prompt")
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        fake_started_at = 123456789
        fake_state = {
            "threadId": "fake-thread-id", "cwd": str(workspace), "promptHash": "0" * 64,
            "startedAt": fake_started_at, "turns": [], "resumes": 0, "quotaWaits": 0,
            "transientRetries": 0, "turnFailures": 0, "lastRateLimits": None, "waits": [],
        }
        state_path.write_text(json.dumps(fake_state))

        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] promptHash mismatch exits 2", r.returncode == 2, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names the promptHash mismatch", "promptHash mismatch" in r.stderr, r.stderr)
        check("[codex-supervisor] mismatch run never spawned the stub",
              not (stub_dir / "meta.json").exists(), "")

        stub_dir2 = tmp / "stub2"
        stub_path2 = _write_stub(stub_dir2, {"turns": [{"events": _DONE_TURN_EVENTS("i1", "done")}]})
        r2 = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                               "--codex-bin", str(stub_path2), "--new-run"], env)
        check("[codex-supervisor] --new-run fresh run exits 0", r2.returncode == 0, r2.stderr)
        archive_path = state_dir / f"codex-supervisor.{fake_started_at}.json"
        check("[codex-supervisor] old state archived to codex-supervisor.<startedAt>.json",
              archive_path.exists(), "")
        if archive_path.exists():
            archived = json.loads(archive_path.read_text())
            check("[codex-supervisor] archived file is the OLD state (same fake threadId)",
                  archived.get("threadId") == "fake-thread-id", str(archived))
        new_state = _read_state(workspace)
        check("[codex-supervisor] fresh state has the new promptHash (not the fake one)",
              new_state.get("promptHash") != "0" * 64, str(new_state))
        check("[codex-supervisor] fresh state.exitReason == 'done'", new_state.get("exitReason") == "done", "")
        extra = _extra_files_under_cwd(workspace)
        check("[codex-supervisor] only the main state/log plus the archived state exist under --cwd",
              extra == [], str(extra))


# ── AC7: ceilings -> exit 3 ────────────────────────────────────────────────

def test_codex_supervisor_ceiling_max_turns():
    print("\n[codex-supervisor] AC7 ceiling: --max-turns 1 -> exit 3")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [_turn_started_event(),
                                          _agent_message_event("i1", "no exit line here"),
                                          _turn_completed_event("completed")]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--max-turns", "1"], env)
        check("[codex-supervisor] max-turns ceiling exits 3", r.returncode == 3, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names max-turns", "max-turns" in r.stderr, r.stderr)
        msgs = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] exactly one turn/start before the ceiling stopped it", len(msgs) == 1, str(msgs))


def test_codex_supervisor_ceiling_max_quota_waits():
    print("\n[codex-supervisor] AC7 ceiling: --max-quota-waits 1 -> exit 3")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        now_source.write_text("1700000000")
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [_turn_started_event(),
                                          _turn_completed_event("failed", {"message": "limit",
                                                                            "codexErrorInfo":
                                                                                "usageLimitExceeded"})]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-quota-waits", "1"], env)
        check("[codex-supervisor] max-quota-waits ceiling exits 3", r.returncode == 3, f"rc={r.returncode}")
        check("[codex-supervisor] stderr names max-quota-waits", "max-quota-waits" in r.stderr, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] state.quotaWaits == 1 when the ceiling fired",
              state.get("quotaWaits") == 1, str(state))


def test_codex_supervisor_ceiling_max_wall_seconds_during_quota_wait():
    print("\n[codex-supervisor] AC7 ceiling: --max-wall-seconds hit during a quota wait -> exit 3")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        stub_dir = tmp / "stub"
        fixture = {
            "rateLimits": [{"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                         "resetsAt": T0 + 50000}, "secondary": None}],
            "turns": [{"events": [_turn_started_event(),
                                   _turn_completed_event("failed", {"message": "limit",
                                                                     "codexErrorInfo":
                                                                         "usageLimitExceeded"})]}],
        }
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "1000"], env)
        check("[codex-supervisor] max-wall-seconds ceiling exits 3 (hit mid quota-wait)",
              r.returncode == 3, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)


# ── status ────────────────────────────────────────────────────────────────

def test_codex_supervisor_status_with_and_without_state():
    print("\n[codex-supervisor] status — with and without a state file")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        missing_state = tmp / "no-such-state.json"
        r = _run_supervisor(["status", "--state", str(missing_state)], env)
        check("[codex-supervisor] status with no state file exits 1", r.returncode == 1, f"rc={r.returncode}")
        check("[codex-supervisor] status with no state file prints 'no run'", "no run" in r.stdout, r.stdout)

        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": _DONE_TURN_EVENTS("i1", "all good")}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r_run = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                                  "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] status-fixture run exits 0", r_run.returncode == 0, r_run.stderr)
        state_path = workspace / ".vss" / "codex-supervisor.json"
        r2 = _run_supervisor(["status", "--state", str(state_path)], env)
        check("[codex-supervisor] status with a state file exits 0", r2.returncode == 0, f"rc={r2.returncode}")
        check("[codex-supervisor] status output mentions thread/turns/exit reason",
              "thread" in r2.stdout and "turns" in r2.stdout and "all good" in r2.stdout, r2.stdout)


# ── AC9: docs ────────────────────────────────────────────────────────────

def test_codex_supervisor_dockerfile_lines():
    print("\n[codex-supervisor] Dockerfile COPY/chmod lines")
    text = DOCKERFILE.read_text()
    check("[codex-supervisor] COPY --chown=root:root codex-supervisor.mjs -> /usr/local/bin/codex-supervisor",
          "COPY --chown=root:root codex-supervisor.mjs /usr/local/bin/codex-supervisor" in text, "")
    check("[codex-supervisor] chmod list includes /usr/local/bin/codex-supervisor",
          "/usr/local/bin/codex-guard-liveness /usr/local/bin/codex-supervisor" in text, "")


def test_codex_supervisor_vsss_md_exit_section():
    print("\n[codex-supervisor] AC9 vsss.md — VSSS-EXIT + 'Running under Codex' note")
    text = VSSS_MD.read_text()
    check("[codex-supervisor] vsss.md has 'Reporting back at exit' section",
          "## Reporting back at exit" in text, "")
    exit_start = text.find("## Reporting back at exit")
    codex_start = text.find("## Running under Codex")
    check("[codex-supervisor] vsss.md has 'Running under Codex' section after the exit section",
          exit_start != -1 and codex_start != -1 and codex_start > exit_start, "")
    if exit_start == -1 or codex_start == -1:
        return
    exit_section = text[exit_start:codex_start]
    check("[codex-supervisor] exit section states the literal 'VSSS-EXIT:' marker",
          "VSSS-EXIT:" in exit_section, "")
    next_heading = text.find("\n## ", codex_start + 1)
    codex_section = text[codex_start:next_heading if next_heading != -1 else len(text)]
    body_lines = [l for l in codex_section.splitlines()[1:] if l.strip() and l.strip() != "---"]
    check("[codex-supervisor] 'Running under Codex' section is <= 10 lines",
          len(body_lines) <= 10, f"{len(body_lines)} lines:\n{codex_section}")
    check("[codex-supervisor] 'Running under Codex' names codex-supervisor",
          "codex-supervisor" in codex_section, "")
    check("[codex-supervisor] 'Running under Codex' names re-entering with 'continue'",
          "continue" in codex_section, "")
    check("[codex-supervisor] 'Running under Codex' names stopping on the VSSS-EXIT: line",
          "VSSS-EXIT:" in codex_section, "")


def test_codex_supervisor_readme_mentions():
    print("\n[codex-supervisor] README mentions codex-supervisor")
    check("[codex-supervisor] README.md mentions codex-supervisor",
          "codex-supervisor" in README_MD.read_text(), "")


def test_codex_supervisor_plan_d7_methods():
    print("\n[codex-supervisor] docs/codex-integration-plan.md D7 names the verified methods")
    text = CODEX_INTEGRATION_PLAN_MD.read_text()
    heading_re = re.compile(r"^- D7\b", re.MULTILINE)
    m = heading_re.search(text)
    d7_idx = m.start() if m else -1
    check("[codex-supervisor] plan has a '- D7' entry heading", d7_idx != -1, "")
    section = text[d7_idx:d7_idx + 3000] if d7_idx != -1 else ""
    for token in ("thread/start", "turn/start", "thread/resume", "codex-supervisor.mjs", "app-server"):
        check(f"[codex-supervisor] D7 section mentions {token!r}", token in section, section[:200])
