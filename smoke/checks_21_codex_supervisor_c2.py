"""task_048 CYCLE 2 — codex-supervisor: amended AC4/AC6/AC7 (Astra review),
authored independently by the Tester (spec-only read: `.vs/spec.md`,
`smoke/checks_19_codex_supervisor.py` for the stub app-server and fixture
helpers, and the current `devcontainer/codex-supervisor.mjs` source; no
Generator report/diff consulted).

Split into its own numbered part per the smoke/ convention (each part
≤1,500 lines): appending these to checks_19_codex_supervisor.py would have
crossed that line, so cycle 1's file there is untouched and this file holds
only the cycle-2 additions, reusing its stub app-server and fixture
builders unchanged.

Covers the AC4/AC6/AC7 amendments from cycle 1's Astra review, driven
through the real `devcontainer/codex-supervisor.mjs`:
  - AC4 terminal state: an `exitReason` in the state file makes a plain
    `run` print `already complete: <reason>` and exit 0 WITHOUT spawning
    anything; `--new-run` archives it and starts fresh.
  - AC4 resume input: `continue` after a turn was already in flight when
    the process was killed vs. the rewritten prompt when no turn was ever
    attempted (turns: [] written before the first `turn/start`).
  - AC7(a) the wall deadline while AWAITING a turn's completion: a
    `turn/interrupt` is sent, the state is written, exit 3.
  - AC7(b) every quota/transient wait is capped by the remaining wall
    budget: the would-be wait is still recorded, then exit 3 instead of
    sleeping past the deadline.
  - AC5/AC7 the `turnFailures` gate (exit 1 on the failure that crosses
    --max-turn-failures, exit 3 without spawning on a resumed run already
    at the ceiling) and every `--max-*` flag must be >= 1.
  - AC4 an outstanding persisted `waits[]` entry is honoured (via the
    virtual clock under --now-source) before anything is sent on resume,
    or exit 3 without spawning if it would end past the deadline.
"""
from smoke._core import *  # noqa: F401,F403

import signal
import time
import hashlib

from smoke.checks_19_codex_supervisor import (
    SUPERVISOR,
    _DONE_TURN_EVENTS,
    _agent_message_event,
    _in_messages,
    _rate_limits_updated_event,
    _run_supervisor,
    _stub_log_lines,
    _supervisor_fixture,
    _read_state,
    _turn_completed_event,
    _turn_started_event,
    _write_stub,
)


# ═══════════════════════════════════════════════════════════════════════

def _prompt_hash(text: str) -> str:
    """sha256 of the RAW prompt-file bytes, exactly as codex-supervisor.mjs
    computes promptHash (createHash('sha256').update(promptRaw) on the
    untrimmed, unrewritten file content) — used to hand-construct state
    files that resume cleanly against a real --prompt-file."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _out_messages(stub_dir: Path) -> list[dict]:
    """Notifications/responses the stub SENT (its 'OUT ' log lines) — the
    counterpart to `_in_messages`, needed to observe stub-initiated
    notifications like `turn/started` that the supervisor never echoes
    back on the wire."""
    out = []
    for line in _stub_log_lines(stub_dir):
        if line.startswith("OUT "):
            try:
                out.append(json.loads(line[4:]))
            except json.JSONDecodeError:
                pass
    return out


# ── AC4 (c2): terminal state — exitReason short-circuits `run` ──────────

def test_codex_supervisor_c2_terminal_state_no_spawn():
    print("\n[codex-supervisor] AC4 (c2) terminal state: exitReason -> 'already complete', "
          "exit 0, stub NEVER spawned")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss already done prompt"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        fake_state = {
            "threadId": "term-thread-id", "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": 1700000000,
            "turns": [{"turnId": "turn-0", "status": "completed", "at": 1700000001}],
            "resumes": 0, "quotaWaits": 0, "transientRetries": 0, "turnFailures": 0,
            "lastRateLimits": None, "waits": [], "exitReason": "all done here",
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] terminal-state run exits 0", r.returncode == 0,
              f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stdout prints 'already complete: all done here'",
              "already complete: all done here" in r.stdout, r.stdout)
        check("[codex-supervisor] terminal-state run never spawned the stub (no meta.json)",
              not (stub_dir / "meta.json").exists(), "")
        state_after = _read_state(workspace)
        check("[codex-supervisor] state file still records the same exitReason",
              state_after.get("exitReason") == "all done here", str(state_after))


def test_codex_supervisor_c2_terminal_state_new_run_starts_fresh():
    print("\n[codex-supervisor] AC4 (c2) terminal state + --new-run archives it and starts fresh")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss already done prompt 2"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        started_at = 1700000000
        fake_state = {
            "threadId": "term-thread-id-2", "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": started_at,
            "turns": [], "resumes": 0, "quotaWaits": 0, "transientRetries": 0,
            "turnFailures": 0, "lastRateLimits": None, "waits": [], "exitReason": "already finished",
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": _DONE_TURN_EVENTS("i1", "fresh-done")}]}
        stub_path = _write_stub(stub_dir, fixture)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--new-run"], env)
        check("[codex-supervisor] --new-run over a terminal state exits 0", r.returncode == 0, r.stderr)
        check("[codex-supervisor] --new-run spawned the stub (fresh run, not short-circuited)",
              (stub_dir / "meta.json").exists(), "")
        archive_path = state_dir / f"codex-supervisor.{started_at}.json"
        check("[codex-supervisor] old terminal state archived to codex-supervisor.<startedAt>.json",
              archive_path.exists(), "")
        if archive_path.exists():
            archived = json.loads(archive_path.read_text())
            check("[codex-supervisor] archived file is the OLD terminal state",
                  archived.get("exitReason") == "already finished", str(archived))
        new_state = _read_state(workspace)
        check("[codex-supervisor] fresh state has the NEW exitReason",
              new_state.get("exitReason") == "fresh-done", str(new_state))
        check("[codex-supervisor] fresh state threadId differs from the archived one",
              new_state.get("threadId") != "term-thread-id-2", str(new_state))


# ── AC4 (c2): resume input — 'continue' vs the rewritten prompt ─────────

def test_codex_supervisor_c2_resume_after_sigterm_sends_continue():
    print("\n[codex-supervisor] AC4 (c2) active-turn SIGTERM requires evidence before 'continue'")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go c2")

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
        check("[codex-supervisor] c2 first run reached turn/start before the kill", saw_turn_start, "")

        proc.send_signal(signal.SIGTERM)
        try:
            _, stderr1 = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr1 = proc.communicate()
        check("[codex-supervisor] c2 SIGTERM exits 130", proc.returncode == 130,
              f"rc={proc.returncode} stderr={stderr1}")

        state1_path = workspace / ".vss" / "codex-supervisor.json"
        state1: dict = {}
        if state1_path.exists():
            try:
                state1 = json.loads(state1_path.read_text())
            except json.JSONDecodeError:
                state1 = {}
        check("[codex-supervisor] c2 state after the kill has empty turns (never completed)",
              state1.get("turns") == [], str(state1))

        stub_dir2 = tmp / "stub2"
        fixture2 = {
            "threadId": state1.get("threadId", "unknown"),
            "turns": [{"events": _DONE_TURN_EVENTS("i2", "done2")}],
        }
        stub_path2 = _write_stub(stub_dir2, fixture2)
        resume_args = ["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                       "--codex-bin", str(stub_path2)]
        refused = _run_supervisor(resume_args, env)
        check("[codex-supervisor] c2 first resume refuses with zero RPCs",
              refused.returncode != 0 and not (stub_dir2 / "meta.json").exists(), refused.stderr)
        state_path = workspace / ".vss" / "codex-supervisor.json"
        lock = Path(f"{state_path}.lock")
        if lock.exists():
            lock.unlink()
        checkpoint = state_path.read_bytes()
        evidence = tmp / "reconciliation.json"
        evidence.write_text(json.dumps({
            "stateHash": hashlib.sha256(checkpoint).hexdigest(),
            "threadId": state1["threadId"], "turnId": state1["unresolvedTurn"]["turnId"],
            "outcome": "interrupted", "effectsReviewed": True, "safeToContinue": True,
            "evidence": "operator reviewed the persisted active-turn checkpoint",
        }))
        reconciled = _run_supervisor(["reconcile", "--state", str(state_path),
                                      "--evidence-file", str(evidence)], env)
        check("[codex-supervisor] c2 reconciliation accepts exact turn/thread/checkpoint evidence",
              reconciled.returncode == 0 and not (stub_dir2 / "meta.json").exists(), reconciled.stderr)
        r2 = _run_supervisor(resume_args, env)
        check("[codex-supervisor] c2 reconciled second run (resume) exits 0", r2.returncode == 0, r2.stderr)
        turn_starts = [m for m in _in_messages(stub_dir2) if m.get("method") == "turn/start"]
        check("[codex-supervisor] c2 resume run sends exactly one turn/start", len(turn_starts) == 1,
              str(turn_starts))
        if turn_starts:
            text = turn_starts[0].get("params", {}).get("input", [{}])[0].get("text")
            check("[codex-supervisor] c2 resumed input text is the literal word 'continue' "
                  "(a turn was already in flight on this thread when it was killed)",
                  text == "continue", repr(text))


def test_codex_supervisor_c2_resume_never_started_sends_rewritten_prompt():
    print("\n[codex-supervisor] AC4 (c2) resume with turns:[] and NO turn ever attempted "
          "sends the rewritten prompt, not 'continue'")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss never started yet"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        # --now-source pins startedAt's era to the test's own clock so the
        # elapsed-wall-time gate never fires here — this test is about the
        # resume TEXT, not the wall ceiling (the ceiling itself is covered
        # by the dedicated ceiling tests above).
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        fake_state = {
            "threadId": "never-started-thread", "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": T0,
            "turns": [], "resumes": 0, "quotaWaits": 0, "transientRetries": 0,
            "turnFailures": 0, "lastRateLimits": None, "waits": [],
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        fixture = {"threadId": "never-started-thread", "turns": [{"events": _DONE_TURN_EVENTS("i1", "done")}]}
        stub_path = _write_stub(stub_dir, fixture)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] never-started resume exits 0", r.returncode == 0, r.stderr)
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] resume sends exactly one turn/start", len(turn_starts) == 1, str(turn_starts))
        if turn_starts:
            text = turn_starts[0].get("params", {}).get("input", [{}])[0].get("text")
            expected = "$vsss never started yet"
            check("[codex-supervisor] resume with no attempted turn sends the REWRITTEN prompt, not 'continue'",
                  text == expected, repr(text))
        methods = [m.get("method") for m in _in_messages(stub_dir)]
        check("[codex-supervisor] resume still sends thread/resume before turn/start",
              "thread/resume" in methods and "turn/start" in methods
              and methods.index("thread/resume") < methods.index("turn/start"), str(methods))


# ── AC7(a) (c2): wall deadline while AWAITING a turn ────────────────────

def test_codex_supervisor_c2_wall_deadline_during_turn_sends_interrupt():
    print("\n[codex-supervisor] AC7(a) (c2) wall deadline while awaiting a turn -> "
          "turn/interrupt, exit 3, state written")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        stub_dir = tmp / "stub"
        # After turn/started the stub idles (a long sleep) without ever
        # completing the turn — the wall deadline is the only thing that
        # can end this run.
        fixture = {"turns": [{"events": [_turn_started_event(), {"sleep": 3}]}]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")

        proc = subprocess.Popen(
            ["node", str(SUPERVISOR), "run", "--cwd", str(workspace), "--prompt-file", str(prompt),
             "--codex-bin", str(stub_path), "--now-source", str(now_source), "--max-wall-seconds", "50"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.time() + 15
        saw_turn_started = False
        while time.time() < deadline:
            if any(m.get("method") == "turn/started" for m in _out_messages(stub_dir)):
                saw_turn_started = True
                break
            time.sleep(0.1)
        check("[codex-supervisor] stub sent turn/started before the clock was advanced", saw_turn_started, "")

        # Advance the virtual clock past startedAt + max-wall-seconds while
        # the supervisor is awaiting the next notification.
        now_source.write_text(str(T0 + 60))
        try:
            _, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        check("[codex-supervisor] wall deadline mid-turn exits 3", proc.returncode == 3,
              f"rc={proc.returncode} stderr={stderr}")
        check("[codex-supervisor] stderr names max-wall-seconds", "max-wall-seconds" in stderr, stderr)

        state_path = workspace / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] state file exists after the wall-deadline exit", state_path.exists(), "")
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
            except json.JSONDecodeError as exc:
                check("[codex-supervisor] state file after the wall-deadline exit is valid JSON", False, str(exc))
            else:
                check("[codex-supervisor] state file after the wall-deadline exit is valid JSON", True, "")
                check("[codex-supervisor] state file retains its threadId", bool(state.get("threadId")), str(state))

        # The stub was mid-sleep when interrupted; give it time to wake,
        # read the buffered turn/interrupt line, and log it.
        interrupt_msg = None
        wait_until = time.time() + 12
        while time.time() < wait_until and interrupt_msg is None:
            for m in _in_messages(stub_dir):
                if m.get("method") == "turn/interrupt":
                    interrupt_msg = m
                    break
            if interrupt_msg is None:
                time.sleep(0.2)
        check("[codex-supervisor] stub received turn/interrupt", interrupt_msg is not None,
              str(_in_messages(stub_dir)))
        if interrupt_msg is not None:
            params = interrupt_msg.get("params", {})
            check("[codex-supervisor] turn/interrupt carries threadId and the turnId",
                  bool(params.get("threadId")) and params.get("turnId") == "turn-0", str(params))


# ── AC7(b) (c2): waits capped by the remaining wall budget ──────────────

def test_codex_supervisor_c2_quota_wait_capped_by_wall_budget():
    print("\n[codex-supervisor] AC7(b) (c2) a quota wait that would end past the deadline -> "
          "exit 3, would-be wait recorded, no second turn/start")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        stub_dir = tmp / "stub"
        fail_events = [
            _turn_started_event(),
            _rate_limits_updated_event({"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                                      "resetsAt": T0 + 50000}, "secondary": None}),
            _turn_completed_event("failed", {"message": "usage limit hit",
                                              "codexErrorInfo": "usageLimitExceeded"}),
        ]
        fixture = {"turns": [
            {"events": fail_events},
            {"events": _DONE_TURN_EVENTS("i2", "canary-should-not-run")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "100"], env)
        check("[codex-supervisor] quota-wait-exceeds-deadline exits 3", r.returncode == 3,
              f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] the would-be quota wait was still recorded in waits[]",
              len(waits) == 1 and waits[0].get("reason") == "quota" and waits[0].get("seconds") == 50120,
              str(waits))
        check("[codex-supervisor] state.quotaWaits was incremented before the ceiling fired",
              state.get("quotaWaits") == 1, str(state))
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] no second turn/start was sent (the canary turn never ran)",
              len(turn_starts) == 1, str(turn_starts))


def test_codex_supervisor_c2_transient_wait_capped_by_wall_budget():
    print("\n[codex-supervisor] AC7(b) (c2) a transient back-off that would end past the "
          "deadline -> exit 3, wait recorded, no second turn/start")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        stub_dir = tmp / "stub"
        fail_events = [_turn_started_event(),
                       _turn_completed_event("failed", {"message": "overloaded",
                                                         "codexErrorInfo": "serverOverloaded"})]
        fixture = {"turns": [
            {"events": fail_events},
            {"events": _DONE_TURN_EVENTS("i2", "canary-should-not-run")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "10"], env)
        check("[codex-supervisor] transient-wait-exceeds-deadline exits 3", r.returncode == 3,
              f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] the would-be transient wait (60s) was still recorded",
              len(waits) == 1 and waits[0].get("reason") == "transient" and waits[0].get("seconds") == 60,
              str(waits))
        check("[codex-supervisor] state.transientRetries was incremented before the ceiling fired",
              state.get("transientRetries") == 1, str(state))
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] no second turn/start was sent (the canary turn never ran)",
              len(turn_starts) == 1, str(turn_starts))


# ── AC5/AC7 (c2): the turnFailures gate ──────────────────────────────────

def test_codex_supervisor_c2_turn_failures_gate_exit1_then_exit3_on_resume():
    print("\n[codex-supervisor] AC5/AC7 (c2) --max-turn-failures 1: exit 1 on the first "
          "failure, then exit 3 on a resumed run without spawning")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "plain failure, no codexErrorInfo"})]},
            {"events": _DONE_TURN_EVENTS("i2", "should-not-be-reached")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--max-turn-failures", "1"], env)
        check("[codex-supervisor] first failure with max-turn-failures 1 exits 1 (AC5 v), not 3",
              r.returncode == 1, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr mentions max-turn-failures",
              "max-turn-failures" in r.stderr, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] state.turnFailures == 1", state.get("turnFailures") == 1, str(state))
        check("[codex-supervisor] state has no exitReason (a failure exit, not a completion)",
              "exitReason" not in state, str(state))
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] only one turn/start (never reached the canary success turn)",
              len(turn_starts) == 1, str(turn_starts))

        stub_dir2 = tmp / "stub2"
        stub_path2 = _write_stub(stub_dir2, {"turns": []})
        r2 = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                               "--codex-bin", str(stub_path2), "--max-turn-failures", "1"], env)
        check("[codex-supervisor] resuming a state already at the turnFailures ceiling exits 3",
              r2.returncode == 3, f"rc={r2.returncode} stderr={r2.stderr}")
        check("[codex-supervisor] stderr names max-turn-failures", "max-turn-failures" in r2.stderr, r2.stderr)
        check("[codex-supervisor] resume-at-ceiling never spawned the stub",
              not (stub_dir2 / "meta.json").exists(), "")


def test_codex_supervisor_c2_max_flags_zero_exit2_no_spawn():
    print("\n[codex-supervisor] AC7 (c2) every --max-* flag with 0 -> exit 2, nothing spawned")
    flags = ["--max-turns", "--max-resumes", "--max-quota-waits", "--max-transient-retries",
             "--max-turn-failures", "--max-wall-seconds"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go")
        for flag in flags:
            stub_dir = tmp / f"stub-{flag.strip('-')}"
            stub_path = _write_stub(stub_dir, {"turns": []})
            r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                                  "--codex-bin", str(stub_path), flag, "0"], env)
            check(f"[codex-supervisor] {flag} 0 exits 2", r.returncode == 2, f"rc={r.returncode} stderr={r.stderr}")
            check(f"[codex-supervisor] {flag} 0 stderr names 'at least 1'", "at least 1" in r.stderr, r.stderr)
            check(f"[codex-supervisor] {flag} 0 never spawned the stub",
                  not (stub_dir / "meta.json").exists(), "")


# ── AC4 (c2): an outstanding persisted wait is honoured on resume ───────

def test_codex_supervisor_c2_outstanding_wait_honoured_then_resumes():
    print("\n[codex-supervisor] AC4 (c2) an outstanding wait still in the future is honoured "
          "(via the virtual clock) before thread/resume + turn/start")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss outstanding wait test"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        fake_state = {
            "threadId": "outstanding-thread", "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": T0,
            "turns": [], "resumes": 0, "quotaWaits": 1, "transientRetries": 0,
            "turnFailures": 0, "lastRateLimits": None,
            "waits": [{"reason": "quota", "seconds": 500, "until": T0 + 500}],
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        fixture = {"threadId": "outstanding-thread", "turns": [{"events": _DONE_TURN_EVENTS("i1", "done")}]}
        stub_path = _write_stub(stub_dir, fixture)
        start = time.time()
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "1000"], env, timeout=20)
        elapsed = time.time() - start
        check("[codex-supervisor] outstanding-wait resume exits 0", r.returncode == 0, r.stderr)
        check("[codex-supervisor] honouring the wait used the VIRTUAL clock, not a real 500s sleep",
              elapsed < 15, f"elapsed={elapsed:.1f}s")
        methods = [m.get("method") for m in _in_messages(stub_dir)]
        check("[codex-supervisor] thread/resume was sent", "thread/resume" in methods, str(methods))
        check("[codex-supervisor] turn/start followed thread/resume (wait honoured first)",
              "thread/resume" in methods and "turn/start" in methods
              and methods.index("thread/resume") < methods.index("turn/start"), str(methods))
        state = _read_state(workspace)
        check("[codex-supervisor] state.exitReason == 'done' after honouring the outstanding wait",
              state.get("exitReason") == "done", str(state))


def test_codex_supervisor_c2_outstanding_wait_exceeds_deadline_exit3_no_spawn():
    print("\n[codex-supervisor] AC4/AC7 (c2) an outstanding wait ending past the wall "
          "ceiling -> exit 3, nothing spawned")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss outstanding wait too far"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        fake_state = {
            "threadId": "outstanding-thread-2", "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": T0,
            "turns": [], "resumes": 0, "quotaWaits": 1, "transientRetries": 0,
            "turnFailures": 0, "lastRateLimits": None,
            "waits": [{"reason": "quota", "seconds": 500, "until": T0 + 500}],
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        stub_path = _write_stub(stub_dir, {"turns": []})
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "100"], env)
        check("[codex-supervisor] outstanding wait past the ceiling exits 3", r.returncode == 3,
              f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)
        check("[codex-supervisor] outstanding-wait-past-ceiling never spawned the stub",
              not (stub_dir / "meta.json").exists(), "")


# ═══════════════════════════════════════════════════════════════════════
# task_048 CYCLE 4 — codex-supervisor: AC4/AC5/AC7 amended AGAIN after the
# reviewer's second pass (Tester's spec-only read: `.vs/spec.md`, this
# file's and checks_19's stub/fixture helpers, the current
# `devcontainer/codex-supervisor.mjs` source; no cycle-4 generator report,
# diff, or scratch tests consulted).
#
# Covers:
#   - AC5 (again): the rewritten prompt is sent EXACTLY ONCE per thread —
#     every later turn/start, whatever caused it (a completed turn, a
#     quota wait, a transient back-off, or a failed turn), sends the
#     literal `continue`. Exercised as three fresh scenarios below, each
#     asserting BOTH the first and the second turn/start text explicitly
#     (checks_19's turn_failure_retries_same_text already covers the
#     failed-turn case for its own purpose and is frozen; these three are
#     independent, cycle-4-authored confirmations of the same rule across
#     all three retry paths).
#   - AC7 (again): the wall deadline bounds every OUTSTANDING REQUEST, not
#     just the wait for a turn's completion notification — including the
#     turn/start and thread/start REQUEST/RESPONSE round-trip itself. A
#     server that reads the request and never answers it must still be
#     bounded: running out of wall budget mid-request -> exit 3 naming
#     max-wall-seconds, never exit 1 (a "handshake timeout"-style exit 1
#     would be wrong here per the reviewer's second pass).
#   - AC4/AC6 (again): on EVERY run, including a resumed one, the fresh
#     account/rateLimits/read snapshot is merged field-wise into the
#     adopted lastRateLimits -- a persisted stale value (here, a resetsAt
#     1000s in the past) must never win over the fresher one.
# ═══════════════════════════════════════════════════════════════════════


# ── AC5 (c4): the rewritten prompt is sent exactly once per thread ──────

def test_codex_supervisor_c4_quota_before_completion_then_success_continue_text():
    print("\n[codex-supervisor] AC5 (c4) quota failure BEFORE any completed turn, then success -- "
          "first turn/start is the rewritten prompt, second is the literal 'continue'")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        now_source.write_text("1700000000")
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "usage limit hit",
                                                          "codexErrorInfo": "usageLimitExceeded"})]},
            {"events": _DONE_TURN_EVENTS("i2", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt_text = "/vsss quota c4 test"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] c4 quota-before-completion run exits 0", r.returncode == 0, r.stderr)
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] c4 exactly 2 turn/start calls", len(turn_starts) == 2, str(turn_starts))
        if len(turn_starts) == 2:
            t1 = turn_starts[0]["params"]["input"][0]["text"]
            t2 = turn_starts[1]["params"]["input"][0]["text"]
            check("[codex-supervisor] c4 first turn/start is the rewritten prompt",
                  t1 == "$vsss quota c4 test", repr(t1))
            check("[codex-supervisor] c4 second turn/start (after the quota wait) is 'continue'",
                  t2 == "continue", repr(t2))


def test_codex_supervisor_c4_transient_before_completion_then_success_continue_text():
    print("\n[codex-supervisor] AC5 (c4) transient failure BEFORE any completed turn, then success -- "
          "first turn/start is the rewritten prompt, second is the literal 'continue'")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        now_source = tmp / "now.txt"
        now_source.write_text("1700000000")
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "overloaded",
                                                          "codexErrorInfo":
                                                              {"httpConnectionFailed":
                                                                   {"httpStatusCode": 429}}})]},
            {"events": _DONE_TURN_EVENTS("i2", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt_text = "/vsss transient c4 test"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] c4 transient-before-completion run exits 0", r.returncode == 0, r.stderr)
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] c4 exactly 2 turn/start calls", len(turn_starts) == 2, str(turn_starts))
        if len(turn_starts) == 2:
            t1 = turn_starts[0]["params"]["input"][0]["text"]
            t2 = turn_starts[1]["params"]["input"][0]["text"]
            check("[codex-supervisor] c4 first turn/start is the rewritten prompt",
                  t1 == "$vsss transient c4 test", repr(t1))
            check("[codex-supervisor] c4 second turn/start (after the transient back-off) is 'continue'",
                  t2 == "continue", repr(t2))


def test_codex_supervisor_c4_failed_turn_before_completion_then_success_continue_text():
    print("\n[codex-supervisor] AC5 (c4) a plain failed turn BEFORE any completed turn, then success -- "
          "first turn/start is the rewritten prompt, second is the literal 'continue'")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        fixture = {"turns": [
            {"events": [_turn_started_event(),
                        _turn_completed_event("failed", {"message": "generic failure, no codexErrorInfo"})]},
            {"events": _DONE_TURN_EVENTS("i2", "done")},
        ]}
        stub_path = _write_stub(stub_dir, fixture)
        prompt_text = "/vsss failed-turn c4 test"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] c4 failed-turn-before-completion run exits 0", r.returncode == 0, r.stderr)
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] c4 exactly 2 turn/start calls", len(turn_starts) == 2, str(turn_starts))
        if len(turn_starts) == 2:
            t1 = turn_starts[0]["params"]["input"][0]["text"]
            t2 = turn_starts[1]["params"]["input"][0]["text"]
            check("[codex-supervisor] c4 first turn/start is the rewritten prompt",
                  t1 == "$vsss failed-turn c4 test", repr(t1))
            check("[codex-supervisor] c4 second turn/start (after the turn failure) is 'continue'",
                  t2 == "continue", repr(t2))


# ── AC7 (c4): the wall deadline bounds outstanding REQUESTS too ─────────
#
# A stub variant that never answers one chosen request method: it logs
# receipt (read_line() always logs "IN ..." before dispatch) and then
# idles, watching stdin for EOF (so it exits cleanly once the supervisor
# closes the pipe on its own wall-deadline exit, instead of leaking a
# process that sleeps for real hours). Self-locating and env-free exactly
# like the base stub (AC3 pins the child env to {PATH,HOME,CODEX_HOME,
# LANG}), it reads which method to hang on from a sibling file since it
# cannot receive that via an environment variable.

_CODEX_STUB_HANG_SRC = '''#!/usr/bin/env python3
import json
import os
import select
import sys
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


def main():
    argv = sys.argv[1:]
    META.write_text(json.dumps({"argv": argv, "env": dict(os.environ)}))
    if argv != ["app-server"]:
        sys.exit(1)

    hang_on = (HERE / "hang_on.txt").read_text().strip()
    thread_id = (HERE / "thread_id.txt").read_text().strip()

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

        if method == hang_on:
            # Deliberately never respond to this request. Idle until the
            # supervisor closes stdin on its own wall-deadline exit (an
            # EOF here), then exit cleanly rather than sleeping for real.
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 5)
                if ready:
                    nxt = sys.stdin.readline()
                    if nxt == "":
                        return

        if method == "initialize":
            send({"id": mid, "result": {"userAgent": "codex-stub-hang/1.0", "codexHome": "/tmp/.codex",
                                         "platformFamily": "unix", "platformOs": "linux"}})
        elif method == "account/rateLimits/read":
            send({"id": mid, "result": {"rateLimits": {"primary": None, "secondary": None}}})
        elif method in ("thread/start", "thread/resume"):
            send({"id": mid, "result": {"thread": {"id": thread_id}}})
        elif method == "turn/start":
            send({"id": mid, "result": {"turn": {"id": "turn-0", "status": "inProgress"}}})
        else:
            if mid is not None:
                send({"id": mid, "error": {"code": -32601, "message": "stub: unhandled method"}})


if __name__ == "__main__":
    main()
'''


def _write_hang_stub(stub_dir: Path, hang_on: str,
                      thread_id: str = "22222222-2222-2222-2222-222222222222") -> Path:
    stub_dir.mkdir(parents=True, exist_ok=True)
    (stub_dir / "hang_on.txt").write_text(hang_on)
    (stub_dir / "thread_id.txt").write_text(thread_id)
    stub_path = stub_dir / "codex"
    stub_path.write_text(_CODEX_STUB_HANG_SRC)
    stub_path.chmod(0o755)
    return stub_path


def test_codex_supervisor_c4_wall_deadline_turn_start_never_answers():
    print("\n[codex-supervisor] AC7 (c4) turn/start request never answered, remaining wall "
          "budget only a few seconds -> exit 3 naming max-wall-seconds (never exit 1), "
          "state written, stub log shows the request was received")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        stub_path = _write_hang_stub(stub_dir, "turn/start")
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go c4 hang turnstart")
        # No --now-source needed: boundedRequest() computes a REAL setTimeout
        # of min(request's own limit, remaining wall budget) at the moment
        # each request is issued (codex-supervisor.mjs:512-521) -- it is not
        # re-derived by polling the clock afterward. With a tiny
        # --max-wall-seconds and instant stub replies for initialize/
        # rateLimits/read/thread-start, only a few REAL seconds of budget
        # remain by the time turn/start is sent and the stub goes silent, so
        # the process actually waits that long before timing out.
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--max-wall-seconds", "5"], env, timeout=20)
        check("[codex-supervisor] c4 turn/start-never-answered exits 3 (never exit 1)",
              r.returncode == 3, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] c4 stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)
        # thread/start already succeeded (a threadId is known, this.state was
        # set) before turn/start hung, so the exit path's `if (this.state)`
        # persists a state file here -- unlike the thread/start-hang test
        # below, where no threadId is ever obtained.
        state_path = workspace / ".vss" / "codex-supervisor.json"
        check("[codex-supervisor] c4 state file exists (thread/start already succeeded before "
              "turn/start hung)", state_path.exists(), "")
        if state_path.exists():
            try:
                json.loads(state_path.read_text())
                valid_json = True
            except json.JSONDecodeError:
                valid_json = False
            check("[codex-supervisor] c4 state file is valid JSON", valid_json, "")
        check("[codex-supervisor] c4 stub log shows the turn/start request was received",
              any(m.get("method") == "turn/start" for m in _in_messages(stub_dir)),
              str(_in_messages(stub_dir)))


def test_codex_supervisor_c4_wall_deadline_thread_start_never_answers():
    print("\n[codex-supervisor] AC7 (c4) thread/start request never answered, remaining wall "
          "budget only a few seconds -> exit 3 naming max-wall-seconds (never exit 1), "
          "stub log shows the request was received")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        stub_dir = tmp / "stub"
        stub_path = _write_hang_stub(stub_dir, "thread/start")
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go c4 hang threadstart")
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--max-wall-seconds", "5"], env, timeout=20)
        check("[codex-supervisor] c4 thread/start-never-answered exits 3 (never exit 1)",
              r.returncode == 3, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] c4 stderr names max-wall-seconds", "max-wall-seconds" in r.stderr, r.stderr)
        # No threadId was ever obtained here (thread/start never returned),
        # so there is nothing valid to persist -- the supervisor's state
        # object is created only once thread/start succeeds (AC4), and the
        # exit path only writes a file `if (this.state)`. Unlike the
        # turn/start case above, no state-file assertion applies here.
        check("[codex-supervisor] c4 stub log shows the thread/start request was received",
              any(m.get("method") == "thread/start" for m in _in_messages(stub_dir)),
              str(_in_messages(stub_dir)))


# ── AC4/AC6 (c4): fresh rateLimits snapshot merged, stale persisted value never wins ──

def test_codex_supervisor_c4_stale_lastratelimits_merged_with_fresh_snapshot():
    print("\n[codex-supervisor] AC4/AC6 (c4) a resumed run's fresh account/rateLimits/read "
          "snapshot is merged field-wise into lastRateLimits -- a persisted resetsAt 1000s in "
          "the past (stale) never wins over the fresh resetsAt = now+900")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt_text = "/vsss resume merge test"
        prompt = tmp / "prompt.txt"
        prompt.write_text(prompt_text)
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        state_dir = workspace / ".vss"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "codex-supervisor.json"
        thread_id = "resume-thread-quota-merge"
        fake_state = {
            "threadId": thread_id, "cwd": str(workspace),
            "promptHash": _prompt_hash(prompt_text), "startedAt": T0 - 5000,
            "turnsStarted": 1,
            "turns": [{"turnId": "turn-0", "status": "completed", "at": T0 - 4000}],
            "resumes": 0, "quotaWaits": 0, "transientRetries": 0, "turnFailures": 0,
            "lastRateLimits": {"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                            "resetsAt": T0 - 1000}, "secondary": None},
            "waits": [],
        }
        state_path.write_text(json.dumps(fake_state))
        stub_dir = tmp / "stub"
        fixture = {
            "threadId": thread_id,
            "rateLimits": [{"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                         "resetsAt": T0 + 900}, "secondary": None}],
            "turns": [
                {"events": [_turn_started_event(),
                            _turn_completed_event("failed", {"message": "usage limit hit",
                                                              "codexErrorInfo": "usageLimitExceeded"})]},
                {"events": _DONE_TURN_EVENTS("i2", "done")},
            ],
        }
        stub_path = _write_stub(stub_dir, fixture)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source),
                              "--max-wall-seconds", "100000"], env)
        check("[codex-supervisor] c4 stale-lastRateLimits-merge run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] c4 exactly one wait recorded", len(waits) == 1, str(waits))
        if waits:
            check("[codex-supervisor] c4 quota wait is 1020s (fresh resetsAt T0+900, +120s grace) "
                  "-- the stale persisted resetsAt (1000s in the past) did NOT win",
                  waits[0].get("reason") == "quota" and waits[0].get("seconds") == 1020, str(waits[0]))
            check("[codex-supervisor] c4 wait.until == T0 + 900 + 120",
                  waits[0].get("until") == T0 + 900 + 120, str(waits[0]))
        check("[codex-supervisor] c4 state.quotaWaits == 1", state.get("quotaWaits") == 1, str(state))
        check("[codex-supervisor] c4 state.resumes == 1 (this was a resume, not a first run)",
              state.get("resumes") == 1, str(state))
        check("[codex-supervisor] c4 state.exitReason == 'done'", state.get("exitReason") == "done", str(state))
        methods = [m.get("method") for m in _in_messages(stub_dir)]
        check("[codex-supervisor] c4 thread/resume was sent (not thread/start, this is a resume)",
              "thread/resume" in methods and "thread/start" not in methods, str(methods))
        turn_starts = [m for m in _in_messages(stub_dir) if m.get("method") == "turn/start"]
        check("[codex-supervisor] c4 exactly 2 turn/start calls (failing turn + quota retry)",
              len(turn_starts) == 2, str(turn_starts))
        if len(turn_starts) == 2:
            t1 = turn_starts[0]["params"]["input"][0]["text"]
            t2 = turn_starts[1]["params"]["input"][0]["text"]
            check("[codex-supervisor] c4 both turn/start texts are 'continue' "
                  "(resume path, turnsStarted already >= 1)",
                  t1 == "continue" and t2 == "continue", f"t1={t1!r} t2={t2!r}")
