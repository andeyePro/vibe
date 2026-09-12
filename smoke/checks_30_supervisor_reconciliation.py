"""Independent reconciliation and process-containment checks for the supervisor."""
from smoke._core import *  # noqa: F401,F403

import hashlib
import json
import os
import subprocess
import time

from smoke.checks_19_codex_supervisor import (
    SUPERVISOR, _DONE_TURN_EVENTS, _in_messages, _read_state,
    _run_supervisor, _supervisor_fixture, _turn_completed_event, _turn_started_event, _write_stub,
)
from smoke.checks_27_supervisor_control import _start, _wait_for


def _drop_start_reply_stub(tmp: Path) -> Path:
    stub = _write_stub(tmp / "stub", {"dropTurnStartReply": True, "turns": []})
    source = stub.read_text()
    stub.write_text(source.replace('elif method == "turn/start":',
        'elif method == "turn/start":\n            if fixture.get("dropTurnStartReply"):\n                return'))
    return stub


def _evidence(state: Path, saved: dict, **overrides) -> Path:
    evidence = state.parent / "evidence.json"
    payload = {
        "stateHash": hashlib.sha256(state.read_bytes()).hexdigest(),
        "threadId": saved["threadId"],
        "turnId": saved["unresolvedTurn"]["turnId"],
        "outcome": "interrupted", "effectsReviewed": True,
        "safeToContinue": True, "evidence": "reviewed recorded effects",
    }
    payload.update(overrides)
    evidence.write_text(json.dumps(payload))
    return evidence


def test_codex_supervisor_c30_lost_start_never_dispatches_again_before_reconciliation():
    print("\n[codex-supervisor] C30 ambiguous turn/start blocks run and --new-run")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss only once")
        first_stub = _drop_start_reply_stub(tmp)
        args = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(first_stub)]
        first = _run_supervisor(args, env)
        state = ws / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] lost reply leaves exactly one attempted turn", first.returncode != 0
              and len([m for m in _in_messages(tmp / "stub") if m.get("method") == "turn/start"]) == 1, first.stderr)
        for flag in ([], ["--new-run"]):
            blocked_stub = _write_stub(tmp / ("new" if flag else "second"),
                                       {"turns": [{"events": _DONE_TURN_EVENTS("x", "bad")}]})
            result = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt),
                                      "--codex-bin", str(blocked_stub), *flag], env)
            check(f"[codex-supervisor] {'--new-run' if flag else 'second run'} does not dispatch ambiguous turn",
                  result.returncode != 0 and not blocked_stub.parent.joinpath("meta.json").exists(), result.stderr)
        check("[codex-supervisor] ambiguous checkpoint remains unchanged", _read_state(ws).get("unresolvedTurn") is not None, state.read_text())


def test_codex_supervisor_c30_reconciliation_rejects_stale_or_invalid_evidence():
    print("\n[codex-supervisor] C30 reconciliation binds evidence to the exact checkpoint")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss evidence")
        stub = _write_stub(tmp / "stub", {"turns": [{"events": [_turn_started_event(), {"sleep": 4}]}]})
        proc = _start(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        state = ws / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] active checkpoint records an unresolved turn",
              _wait_for(state, lambda p: p.exists() and (json.loads(p.read_text()).get("unresolvedTurn") or {}).get("turnId") is not None),
              "missing unresolved-turn state")
        proc.kill(); proc.communicate(timeout=10)
        Path(f"{state}.lock").unlink()
        saved = _read_state(ws)
        cases = [
            ("stale hash", {"stateHash": "0" * 64}),
            ("missing review", {"effectsReviewed": False}),
            ("wrong turn", {"turnId": "other-turn"}),
            ("empty evidence", {"evidence": ""}),
        ]
        for label, changes in cases:
            result = _run_supervisor(["reconcile", "--state", str(state), "--evidence-file",
                                      str(_evidence(state, saved, **changes))], env)
            check(f"[codex-supervisor] {label} evidence is refused", result.returncode == 2, result.stderr)
            check(f"[codex-supervisor] {label} leaves unresolved checkpoint", _read_state(ws).get("unresolvedTurn") is not None, state.read_text())


def test_codex_supervisor_c30_final_marker_is_final_unindented_plain_text_only():
    print("\n[codex-supervisor] C30 only a final unindented marker completes")
    cases = {
        "final plain": "VSSS-EXIT: accepted",
        "indented": "  VSSS-EXIT: rejected",
        "code": "```\nVSSS-EXIT: rejected\n```",
        "trailing prose": "VSSS-EXIT: rejected\nmore",
    }
    for name, text in cases.items():
        r = subprocess.run(["node", "-e", f"import({json.dumps(str(SUPERVISOR))}).then(m => console.log(m.exitReasonFrom({json.dumps(text)})))"],
                           capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        expected = "accepted" if name == "final plain" else "null"
        check(f"[codex-supervisor] {name} marker result", r.returncode == 0 and r.stdout.strip() == expected, r.stderr or r.stdout)


def test_codex_supervisor_c30_existing_mode0644_log_is_repaired_before_first_dispatch():
    print("\n[codex-supervisor] C30 owned mode0644 log is made private before first dispatch")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss private-log")
        log = ws / ".vss" / "codex-supervisor.log"; log.parent.mkdir(); log.write_text("old")
        os.chmod(log, 0o644)
        stub = _write_stub(tmp / "stub", {"turns": [{"events": _DONE_TURN_EVENTS("x", "done")} ]})
        r = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        mode = log.stat().st_mode & 0o777 if log.exists() else None
        check("[codex-supervisor] owned mode0644 log is repaired and run dispatches", r.returncode == 0 and (tmp / "stub" / "meta.json").exists(), r.stderr)
        check("[codex-supervisor] log is mode0600 at its first append/dispatch", mode == 0o600, oct(mode or 0))


def test_codex_supervisor_c30_subreaper_reaps_detached_descendants():
    print("\n[codex-supervisor] C30 Linux subreaper cleans a double-forked setsid child")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss reap")
        stub = _write_stub(tmp / "stub", {"doubleFork": True,
                                            "turns": [{"events": _DONE_TURN_EVENTS("x", "done")}]})
        source = stub.read_text()
        injection = '''fixture = json.loads((HERE / "fixture.json").read_text())
    if fixture.get("doubleFork"):
        first = os.fork()
        if first == 0:
            os.setsid()
            second = os.fork()
            if second == 0:
                (HERE / "detached.pid").write_text(str(os.getpid()))
                time.sleep(30)
                os._exit(0)
            os._exit(0)'''
        stub.write_text(source.replace('fixture = json.loads((HERE / "fixture.json").read_text())', injection))
        r = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env, timeout=20)
        pid_file = stub.parent / "detached.pid"
        pid = pid_file.read_text().strip() if pid_file.exists() else ""
        check("[codex-supervisor] detached descendant was created and parent run completed", r.returncode == 0 and pid.isdigit(), r.stderr)
        check("[codex-supervisor] no detached fake app-server descendant remains live", bool(pid) and not Path(f"/proc/{pid}").exists(), f"pid={pid}")


def test_codex_supervisor_c30_unconfirmed_cleanup_retains_ownership_lock():
    print("\n[codex-supervisor] C30 unconfirmed process-tree cleanup keeps lock")
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "control.json"
        script = f'''import {{ acquire, closeServer }} from {json.dumps(str(REPO / "devcontainer" / "supervisor-control.mjs"))};
import {{ existsSync }} from 'node:fs';
const owner = acquire({json.dumps(str(state))});
const child = {{ treeEmpty: false, exitCode: null, signalCode: null, pid: 12345, kill() {{ return true; }} }};
try {{ await closeServer({{ child, closeStdin() {{}}, shutdown() {{}} }}); }}
catch {{ owner.retain(); console.log(existsSync({json.dumps(str(state) + '.lock')})); }}'''
        r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
        check("[codex-supervisor] unconfirmed cleanup reports retained lock", r.returncode == 0 and r.stdout.strip() == "true" and Path(f"{state}.lock").exists(), r.stderr or r.stdout)


def test_codex_supervisor_c30_task_ref_is_forwarded_and_bound_on_resume():
    print("\n[codex-supervisor] C30 task binding reaches child and cannot change on resume")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        env = {**env, "VIBE_TASK_REF": "VIBE-27"}
        prompt = tmp / "prompt"; prompt.write_text("/vsss task")
        first_stub = _write_stub(tmp / "first", {"turns": [{"events": _DONE_TURN_EVENTS("x", "done")}]})
        first = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(first_stub)], env)
        check("[codex-supervisor] task-bound child started", first.returncode == 0 and (first_stub.parent / "meta.json").exists(), first.stderr)
        meta = json.loads((first_stub.parent / "meta.json").read_text())
        check("[codex-supervisor] VIBE_TASK_REF is forwarded to app-server", meta["env"].get("VIBE_TASK_REF") == "VIBE-27", str(meta))
        other_stub = _write_stub(tmp / "other", {"turns": []})
        changed = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(other_stub)],
                                  {**env, "VIBE_TASK_REF": "VIBE-28"})
        check("[codex-supervisor] changed task reference refuses before dispatch", changed.returncode == 2
              and not (other_stub.parent / "meta.json").exists(), changed.stderr)


def test_codex_supervisor_c30_hostile_workspace_python_modules_never_run():
    print("\n[codex-supervisor] C30 /usr/bin/python3 -I ignores hostile workspace ctypes/signal")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        marker = tmp / "hostile-import-ran"
        payload = f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')\n"
        (ws / "ctypes.py").write_text(payload)
        (ws / "signal.py").write_text(payload)
        prompt = tmp / "prompt"; prompt.write_text("/vsss isolated imports")
        stub = _write_stub(tmp / "stub", {"turns": [{"events": _DONE_TURN_EVENTS("x", "done")} ]})
        result = subprocess.run(["node", str(SUPERVISOR), "run", "--cwd", str(ws),
                                 "--prompt-file", str(prompt), "--codex-bin", str(stub)],
                                cwd=ws, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30)
        check("[codex-supervisor] isolated subreaper run completes", result.returncode == 0, result.stderr)
        check("[codex-supervisor] workspace ctypes.py and signal.py were never imported", not marker.exists(), "hostile workspace import executed")


def test_codex_supervisor_c30_hardlinked_and_foreign_logs_refuse_before_server():
    print("\n[codex-supervisor] C30 hardlinked and foreign-owned logs refuse")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss log safety")
        log = ws / ".vss" / "codex-supervisor.log"; log.parent.mkdir(); log.write_text("old")
        os.link(log, tmp / "log-link")
        stub = _write_stub(tmp / "hardlinked", {"turns": []})
        result = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt),
                                  "--codex-bin", str(stub)], env)
        check("[codex-supervisor] hardlinked log refuses before app-server dispatch",
              result.returncode != 0 and not (stub.parent / "meta.json").exists(), result.stderr)
    if os.geteuid() != 0:
        print("[codex-supervisor] foreign-owner check skipped: test user cannot create a foreign-owned fixture")
        return
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss foreign log")
        log = ws / ".vss" / "codex-supervisor.log"; log.parent.mkdir(); log.write_text("old")
        os.chown(log, 65534, 65534)
        stub = _write_stub(tmp / "foreign", {"turns": []})
        result = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt),
                                  "--codex-bin", str(stub)], env)
        check("[codex-supervisor] foreign-owned log refuses before app-server dispatch",
              result.returncode != 0 and not (stub.parent / "meta.json").exists(), result.stderr)


def test_codex_supervisor_c30_fsync_failure_prevents_dispatch():
    print("\n[codex-supervisor] C30 failed temp-file or parent-directory fsync prevents dispatch")
    compiler = subprocess.run(["gcc", "--version"], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    if compiler.returncode != 0:
        check("[codex-supervisor] fsync fault injector compiler is available", False, compiler.stderr)
        return
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        injector_c = tmp / "fsync-fail.c"; injector_so = tmp / "fsync-fail.so"
        injector_c.write_text(r'''#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int fsync(int fd) {
  static int (*real_fsync)(int);
  struct stat st; const char *kind = getenv("SUPERVISOR_TEST_FSYNC_FAIL");
  if (!real_fsync) real_fsync = dlsym(RTLD_NEXT, "fsync");
  if (kind && fstat(fd, &st) == 0 &&
      ((!strcmp(kind, "file") && S_ISREG(st.st_mode)) || (!strcmp(kind, "dir") && S_ISDIR(st.st_mode)))) {
    errno = EIO; return -1;
  }
  return real_fsync(fd);
}''')
        built = subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(injector_so), str(injector_c), "-ldl"],
                               capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        check("[codex-supervisor] fsync fault injector builds", built.returncode == 0, built.stderr)
        if built.returncode != 0:
            return
        for kind in ("file", "dir"):
            fixture_root = tmp / kind; fixture_root.mkdir()
            home, codex_home, ws, env = _supervisor_fixture(fixture_root)
            prompt = tmp / f"{kind}-prompt"; prompt.write_text("/vsss sync")
            stub = _write_stub(tmp / f"{kind}-stub", {"turns": []})
            result = subprocess.run(["node", str(SUPERVISOR), "run", "--cwd", str(ws),
                                     "--prompt-file", str(prompt), "--codex-bin", str(stub)],
                                    env={**env, "LD_PRELOAD": str(injector_so), "SUPERVISOR_TEST_FSYNC_FAIL": kind},
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            check(f"[codex-supervisor] {kind} fsync failure refuses before app-server dispatch",
                  result.returncode != 0 and not (stub.parent / "meta.json").exists(), result.stderr)


def _taskandi_config(ws: Path, endpoint: str, mapped_task: str) -> None:
    vibe = ws / ".vibe"; vibe.mkdir(exist_ok=True); os.chmod(vibe, 0o700)
    (vibe / "taskandi.json").write_text(json.dumps({"endpoint": endpoint, "task": "VIBE-100"}))
    (vibe / "taskandi-task").write_text(mapped_task)


def _nonterminal_bound_checkpoint(tmp: Path, endpoint: str, mapped_task: str):
    _, _, ws, env = _supervisor_fixture(tmp)
    _taskandi_config(ws, endpoint, mapped_task)
    prompt = tmp / "prompt"; prompt.write_text("/vsss bind checkpoint")
    failed = {"events": [_turn_started_event(),
              _turn_completed_event("failed", {"message": "ordinary failure"})]}
    stub = _write_stub(tmp / "first", {"turns": [failed]})
    first = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt),
                             "--codex-bin", str(stub), "--max-turn-failures", "1"], env)
    check("[codex-supervisor] local binding fixture creates a nonterminal checkpoint", first.returncode == 1, first.stderr)
    return ws, env, prompt


def test_codex_supervisor_c30_default_mapping_and_endpoint_changes_refuse_resume():
    print("\n[codex-supervisor] C30 effective local task mapping and endpoint bind a resume")
    for label, before, after in [
        ("mapping", ("http://127.0.0.1:8765/mcp", "VIBE-101"), ("http://127.0.0.1:8765/mcp", "VIBE-102")),
        ("endpoint", ("http://127.0.0.1:8765/mcp", "VIBE-101"), ("http://127.0.0.1:8766/mcp", "VIBE-101")),
    ]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ws, env, prompt = _nonterminal_bound_checkpoint(tmp, *before)
            _taskandi_config(ws, *after)
            blocked = _write_stub(tmp / "blocked", {"turns": []})
            result = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt),
                                      "--codex-bin", str(blocked)], env)
            check(f"[codex-supervisor] changed default local {label} refuses before RPC",
                  result.returncode == 2 and not (blocked.parent / "meta.json").exists(), result.stderr)


def test_codex_supervisor_c30_pinned_client_rejects_changed_config():
    print("\n[codex-supervisor] C30 VIBE_TASK_BINDING pins taskandi client configuration")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        _taskandi_config(ws, "http://127.0.0.1:8765/mcp", "VIBE-101")
        fingerprint = subprocess.run(["node", "--input-type=module", "-e",
            f"import {{ loadConfig, bindingFingerprint }} from {json.dumps(str(REPO / 'devcontainer' / 'taskandi-client.mjs'))}; console.log(bindingFingerprint(loadConfig(process.argv[1])));", str(ws)],
            env=env, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        check("[codex-supervisor] fixture binding fingerprint is available", fingerprint.returncode == 0, fingerprint.stderr)
        _taskandi_config(ws, "http://127.0.0.1:8766/mcp", "VIBE-101")
        client = subprocess.run(["node", str(REPO / "devcontainer" / "taskandi-client.mjs"), "enqueue", "ask", "--key", "pinned-binding"], cwd=ws,
                                env={**env, "VIBE_TASK_BINDING": fingerprint.stdout.strip()},
                                input=json.dumps({"to": "tester", "question": "q", "default": "d"}),
                                capture_output=True, text=True, timeout=20)
        check("[codex-supervisor] pinned client refuses after configuration changes",
              client.returncode != 0 and "pinned task binding changed" in client.stderr, client.stderr)
