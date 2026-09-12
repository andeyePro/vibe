"""Independent adversarial checks for task_048 supervisor ownership/control.

These deliberately reuse the pre-existing app-server stub rather than a
second protocol implementation.  They are not wired into runner.py yet.
"""
from smoke._core import *  # noqa: F401,F403

import json
import hashlib
import os
import signal
import subprocess
import tempfile
import time

from smoke.checks_19_codex_supervisor import (
    SUPERVISOR, _DONE_TURN_EVENTS, _agent_message_event, _in_messages,
    _rate_limits_updated_event, _read_state, _run_supervisor,
    _supervisor_fixture, _turn_completed_event, _turn_started_event,
    _write_stub,
)


def _wait_for(path: Path, predicate=lambda p: p.exists(), seconds: float = 8) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate(path):
            return True
        time.sleep(.05)
    return predicate(path)


def _start(args, env):
    return subprocess.Popen(["node", str(SUPERVISOR), *args], env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def test_codex_supervisor_c27_live_lock_rejects_duplicate_and_new_run():
    print("\n[codex-supervisor] C27 exclusive ownership precedes new-run/state changes")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss own it")
        stub = _write_stub(tmp / "stub", {"turns": [{"events": [_turn_started_event(), {"sleep": 4}]}]})
        args = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)]
        owner = _start(args, env)
        lock = ws / ".vss" / "codex-supervisor.json.lock"
        check("[codex-supervisor] owner created lock", _wait_for(lock), "lock absent")
        duplicate = _run_supervisor(args, env)
        new_run = _run_supervisor([*args, "--new-run"], env)
        check("[codex-supervisor] duplicate live run refuses", duplicate.returncode != 0 and "lock" in duplicate.stderr.lower(), duplicate.stderr)
        check("[codex-supervisor] --new-run also refuses live owner", new_run.returncode != 0 and "lock" in new_run.stderr.lower(), new_run.stderr)
        owner.send_signal(signal.SIGTERM)
        owner.communicate(timeout=15)


def test_codex_supervisor_c27_stale_lock_needs_explicit_reconciliation():
    print("\n[codex-supervisor] C27 stale/ambiguous lock is never stolen")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss recover")
        control = ws / ".vss" / "codex-supervisor.json"
        control.parent.mkdir()
        lock = Path(f"{control}.lock")
        lock.write_text('{"version":1,"token":"00000000-0000-0000-0000-000000000000"}')
        old = time.time() - 7200
        os.utime(lock, (old, old))
        stub = _write_stub(tmp / "stub", {"turns": [{"events": _DONE_TURN_EVENTS("i", "done")}]})
        args = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)]
        refused = _run_supervisor(args, env)
        check("[codex-supervisor] stale lock refused with cleanup direction", refused.returncode != 0 and "No stale lock is stolen" in refused.stderr, refused.stderr)
        check("[codex-supervisor] stale lock did not spawn server", not (tmp / "stub" / "meta.json").exists(), "server spawned")
        lock.unlink()  # explicit operator reconciliation, never automatic theft
        resumed = _run_supervisor(args, env)
        check("[codex-supervisor] explicit reconciliation permits run", resumed.returncode == 0, resumed.stderr)


def test_codex_supervisor_c27_stop_is_token_scoped_and_cancellable():
    print("\n[codex-supervisor] C27 stop targets only owner token and bounds quota sleep")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss wait")
        quota = [_turn_started_event(), _rate_limits_updated_event({"primary": {"usedPercent": 100, "resetsAt": int(time.time()) + 5000}}),
                 _turn_completed_event("failed", {"codexErrorInfo": "usageLimitExceeded"})]
        stub = _write_stub(tmp / "stub", {"turns": [{"events": quota}]})
        args = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)]
        proc = _start(args, env)
        state = ws / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] quota wait checkpoint exists", _wait_for(state, lambda p: p.exists() and '"quota-wait"' in p.read_text()), "no quota checkpoint")
        unrelated = tmp / "unrelated.json"
        unrelated.write_text("{}")
        no_owner = _run_supervisor(["stop", "--state", str(unrelated)], env)
        check("[codex-supervisor] stop without unrelated lock fails", no_owner.returncode != 0, no_owner.stderr)
        stopped = _run_supervisor(["stop", "--state", str(state)], env)
        started = time.monotonic()
        proc.communicate(timeout=15)
        check("[codex-supervisor] stop request accepted", stopped.returncode == 0, stopped.stderr)
        check("[codex-supervisor] quota sleep exits promptly", proc.returncode == 130 and time.monotonic() - started < 3, f"rc={proc.returncode}")
        saved = _read_state(ws)
        check("[codex-supervisor] stopped run saves resumable state and frees lock", saved.get("threadId") and not Path(f"{state}.lock").exists(), str(saved))


def test_codex_supervisor_c27_final_marker_and_matching_identity_only():
    print("\n[codex-supervisor] C27 only final matching agent marker completes")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss marker")
        wrong_item = {"method": "item/completed", "params": {"threadId": "other", "turnId": "other-turn", "item": {"type": "agentMessage", "text": "VSSS-EXIT: stolen"}}}
        wrong_done = {"method": "turn/completed", "params": {"threadId": "other", "turn": {"id": "other-turn", "status": "completed", "items": [{"type": "agentMessage", "text": "VSSS-EXIT: stolen"}]}}}
        fixture = {"turns": [
            {"events": [_turn_started_event(), wrong_item, wrong_done,
                        _agent_message_event("a", "VSSS-EXIT: early\nmore prose"), _turn_completed_event("completed")]},
            {"events": [_turn_started_event(), _agent_message_event("b", "```\nVSSS-EXIT: fenced\n```"), _turn_completed_event("completed")]},
            {"events": _DONE_TURN_EVENTS("c", "accepted")},
        ]}
        stub = _write_stub(tmp / "stub", fixture)
        r = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        state = _read_state(ws)
        check("[codex-supervisor] nonfinal/fenced/mismatched markers did not complete", r.returncode == 0 and state.get("exitReason") == "accepted", f"{r.stderr} {state}")
        starts = [m for m in _in_messages(tmp / "stub") if m.get("method") == "turn/start"]
        check("[codex-supervisor] ignored markers required later turns", len(starts) == 3, str(starts))


def test_codex_supervisor_c27_stop_during_active_turn_is_bounded():
    print("\n[codex-supervisor] C27 stop during an active turn checkpoints and releases ownership")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss active")
        stub = _write_stub(tmp / "stub", {"turns": [{"events": [_turn_started_event(), {"sleep": 5}]}]})
        proc = _start(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        state = ws / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] active turn checkpoint exists", _wait_for(state, lambda p: p.exists() and '"operation": "turn"' in p.read_text()), "no active checkpoint")
        started = time.monotonic()
        stop = _run_supervisor(["stop", "--state", str(state)], env)
        proc.communicate(timeout=15)
        saved = _read_state(ws)
        # The owned app-server may be in a non-interruptible tool operation;
        # supervisor-control bounds its EOF/TERM/KILL shutdown sequence to 8s.
        check("[codex-supervisor] active-turn stop is accepted and bounded", stop.returncode == 0 and proc.returncode == 130 and time.monotonic() - started < 10, f"stop={stop.stderr} rc={proc.returncode}")
        check("[codex-supervisor] active-turn stop saved state and released lock", saved.get("threadId") and not Path(f"{state}.lock").exists(), str(saved))


def test_codex_supervisor_c27_status_and_unsafe_persistence_fail_closed():
    print("\n[codex-supervisor] C27 status redacts payload; corrupt/symlink state is refused")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        state = ws / ".vss" / "codex-supervisor.json"; state.parent.mkdir()
        secret = "Bearer very-secret-payload"
        state.write_text(json.dumps({"threadId": secret, "exitReason": secret, "operation": secret, "turns": [], "turnsStarted": 0}))
        report = _run_supervisor(["status", "--state", str(state)], env)
        check("[codex-supervisor] status never exposes arbitrary state payload", secret not in report.stdout, report.stdout)
        state.write_text("{broken")
        prompt = tmp / "prompt"; prompt.write_text("/vsss corrupt")
        stub = _write_stub(tmp / "stub", {"turns": []})
        r = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        check("[codex-supervisor] corrupt state refuses rather than restarts", r.returncode == 2 and not (tmp / "stub" / "meta.json").exists(), r.stderr)
        state.unlink()
        target = tmp / "target"; target.write_text("{}")
        state.symlink_to(target)
        symlink = _run_supervisor(["status", "--state", str(state)], env)
        check("[codex-supervisor] symlink control state is refused", symlink.returncode != 0, symlink.stderr)


def test_codex_supervisor_c27_killed_active_turn_requires_reconciliation_not_replay():
    print("\n[codex-supervisor] C27 killed active turn stays checkpointed; resume is continue")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss original-once")
        stub1 = _write_stub(tmp / "stub1", {"turns": [{"events": [_turn_started_event(), {"sleep": 4}]}]})
        args1 = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub1)]
        proc = _start(args1, env)
        check("[codex-supervisor] active turn was sent", _wait_for(tmp / "stub1" / "stub.log", lambda p: p.exists() and 'turn/start' in p.read_text()), "no turn")
        state = ws / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] active-turn fixture records its acknowledged identity before interruption",
              _wait_for(state, lambda p: p.exists() and (json.loads(p.read_text()).get("unresolvedTurn") or {}).get("turnId") is not None),
              "missing acknowledged turn ID")
        proc.kill(); proc.communicate(timeout=10)
        state = ws / ".vss" / "codex-supervisor.json"
        lock = Path(f"{state}.lock")
        check("[codex-supervisor] killed process leaves lock requiring explicit reconciliation", lock.exists(), "missing crash lock")
        stub2 = _write_stub(tmp / "stub2", {"turns": [{"events": _DONE_TURN_EVENTS("i", "recovered")}]})
        args2 = ["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub2)]
        refused = _run_supervisor(args2, env)
        check("[codex-supervisor] crashed ownership blocks automatic resume", refused.returncode != 0, refused.stderr)
        # Removing a stale lock only makes reconciliation possible; it must
        # not itself authorise a continuation of an effect-ambiguous turn.
        lock.unlink()
        checkpoint = state.read_bytes()
        saved = _read_state(ws)
        evidence = tmp / "reconciliation.json"
        evidence.write_text(json.dumps({
            "stateHash": hashlib.sha256(checkpoint).hexdigest(),
            "threadId": saved["threadId"],
            "turnId": saved["unresolvedTurn"]["turnId"],
            "outcome": "interrupted",
            "effectsReviewed": True,
            "safeToContinue": True,
            "evidence": "operator reviewed the interrupted turn's effects",
        }))
        reconciled = _run_supervisor(["reconcile", "--state", str(state),
                                      "--evidence-file", str(evidence)], env)
        check("[codex-supervisor] explicit evidence reconciliation succeeds without dispatch",
              reconciled.returncode == 0 and "turn reconciled" in reconciled.stdout
              and not (tmp / "stub2" / "meta.json").exists(), reconciled.stderr)
        resumed = _run_supervisor(args2, env)
        turns = [m for m in _in_messages(tmp / "stub2") if m.get("method") == "turn/start"]
        text = turns[0]["params"]["input"][0]["text"] if turns else None
        check("[codex-supervisor] reconciled active-turn resume does not replay original prompt", resumed.returncode == 0 and text == "continue", f"{resumed.stderr} {turns}")


def test_codex_supervisor_c27_unconfirmed_turn_start_is_not_automatically_retried():
    print("\n[codex-supervisor] C27 lost turn/start reply is checkpointed, not blindly retried")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, _, ws, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt"; prompt.write_text("/vsss effect-once")
        # Keep the proven fixture wire implementation, changing only this
        # instance's turn/start branch to simulate EOF after the server has
        # received a request but before the client receives its response.
        stub = _write_stub(tmp / "stub", {"dropTurnStartReply": True, "turns": []})
        source = stub.read_text()
        stub.write_text(source.replace('elif method == "turn/start":',
                                       'elif method == "turn/start":\n            if fixture.get("dropTurnStartReply"):\n                return'))
        first = _run_supervisor(["run", "--cwd", str(ws), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        messages = [m for m in _in_messages(tmp / "stub") if m.get("method") == "turn/start"]
        saved = _read_state(ws)
        check("[codex-supervisor] unknown in-flight request exits checkpointed without retry", first.returncode != 0 and len(messages) == 1, f"{first.stderr} {messages}")
        check("[codex-supervisor] checkpoint records attempted turn and recovery reason", saved.get("turnsStarted") == 1 and saved.get("recoveryReason"), str(saved))
