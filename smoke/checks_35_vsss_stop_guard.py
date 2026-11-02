"""The /vsss keep-going guard (devcontainer/vsss-stop-guard.sh).

One Stop hook for both runtimes: while the /vsss run this session owns is
live (its session file has no `## Final state`), ending the turn is refused
with a `{"decision":"block","reason":…}` reply telling the model to post its
questions and carry on with unblocked work. Ownership is the marker's
`owner=` line matched exactly against the payload's session_id. Every doubt
must allow the stop — the guard may never trap a session — so most of these
checks are allow paths, plus the cap on refusals without a new commit.
"""
from smoke._core import *  # noqa: F401,F403

import json
import os
import subprocess
import tempfile
import time

STOP_GUARD = REPO / "devcontainer" / "vsss-stop-guard.sh"
CODEX_HOOKS_JSON = REPO / "devcontainer" / "codex" / "hooks" / "hooks.json"
LIVENESS_SH = REPO / "devcontainer" / "codex-guard-liveness.sh"
SESSION_REL = ".vss/sessions/2026-09-25T01-09-47Z.md"
SID = "59891436-b16a-4a36-aecb-9e916123d430"
GUARD_CMD_CODEX = "/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /usr/local/bin/codex-stop-guard"
GUARD_CMD_CLAUDE = "[ ! -x /usr/local/bin/vsss-stop-guard ] || /usr/local/bin/vsss-stop-guard"


def _guard_fixture(td: Path, *, active: str = "1", session_rel: str = SESSION_REL,
                   final: bool = False, owner: str | None = SID) -> Path:
    root = td / "ws"
    (root / ".vss" / "sessions").mkdir(parents=True)
    lines = f"active={active}\nremaining=9999\nresume_at=1\nsession_file={session_rel}\n"
    if owner is not None:
        lines += f"owner={owner}\n"
    (root / ".vss" / "auto-resume").write_text(lines)
    body = "# /vsss session\n\n## Iter 1\n"
    if final:
        body += "\n## Final state\nExit reason: perfection gate\n"
    (root / SESSION_REL).write_text(body)
    return root


def _git(root: Path, *args: str) -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root),
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env=env, stdin=subprocess.DEVNULL, timeout=30)


def _run_guard(root: Path, payload, extra_env: dict | None = None):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "VIBE_STOP_GUARD_ROOT": str(root)}
    if extra_env:
        env.update(extra_env)
    data = payload if isinstance(payload, str) else json.dumps(payload)
    # env -i + /bin/bash: the same bare environment Codex's managed hook gives it.
    return subprocess.run(["/usr/bin/env", "-i", *[f"{k}={v}" for k, v in env.items()],
                           "/bin/bash", str(STOP_GUARD)],
                          input=data, capture_output=True, text=True, timeout=30)


def _blocked(r) -> bool:
    try:
        return r.returncode == 0 and json.loads(r.stdout).get("decision") == "block"
    except (json.JSONDecodeError, AttributeError):
        return False


def _reason(r) -> str:
    return json.loads(r.stdout).get("reason", "") if _blocked(r) else ""


def _allowed(r) -> bool:
    return r.returncode == 0 and r.stdout.strip() == ""


def _payload(session_id: str | None = SID, last: str | None = None) -> dict:
    p = {"hook_event_name": "Stop", "cwd": "/workspace", "stop_hook_active": False,
         "transcript_path": None}
    if session_id is not None:
        p["session_id"] = session_id
    if last is not None:
        p["last_assistant_message"] = last
    return p


def test_stop_guard_blocks_a_live_owned_run():
    print("\n[stop-guard] a live /vsss run this session owns cannot end its turn")
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r = _run_guard(root, _payload())
        check("[stop-guard] live owned run: replies decision=block", _blocked(r), r.stdout + r.stderr)
        reason = _reason(r)
        check("[stop-guard] reason names the session file", SESSION_REL in reason, reason)
        check("[stop-guard] reason says a question is not an exit condition",
              "NOT an exit condition" in reason, reason)
        check("[stop-guard] reason names both answer channels",
              "fromClaude" in reason and "FM2C" in reason, reason)
        check("[stop-guard] reason says how to exit lawfully",
              "## Final state" in reason and "active=0" in reason and "VSSS-EXIT" in reason, reason)
        check("[stop-guard] reason tells it the user's own stop wins",
              "told you in this conversation to stop or pause" in reason, reason)
        check("[stop-guard] no VSSS-EXIT note when the message did not end on one",
              "You ended on a VSSS-EXIT line" not in reason, reason)
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r = _run_guard(root, _payload(last="Report...\n\nVSSS-EXIT: waiting for Martin\n\n"))
        check("[stop-guard] a VSSS-EXIT without Final state is refused", _blocked(r), r.stdout)
        check("[stop-guard] ... and the reason challenges that exit",
              "You ended on a VSSS-EXIT line" in _reason(r), _reason(r))


def test_stop_guard_allow_paths():
    print("\n[stop-guard] every doubt allows the stop")
    cases = [
        ("Final state present", dict(final=True), _payload()),
        ("active=0", dict(active="0"), _payload()),
        ("another session (session_id != owner)", {}, _payload(session_id="someone-else")),
        ("marker has no owner= line", dict(owner=None), _payload()),
        ("marker has an empty owner=", dict(owner=""), _payload()),
        ("payload has no session_id", {}, _payload(session_id=None)),
        ("session_file with traversal", dict(session_rel=".vss/sessions/../../etc/passwd.md"), _payload()),
    ]
    for label, kw, payload in cases:
        with tempfile.TemporaryDirectory() as td:
            root = _guard_fixture(Path(td), **kw)
            check(f"[stop-guard] {label} -> allowed", _allowed(_run_guard(root, payload)))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / ".vss" / "auto-resume").unlink()
        check("[stop-guard] no marker -> allowed", _allowed(_run_guard(root, _payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / ".vss" / "awaiting-human").write_text("1\n")
        check("[stop-guard] a pending human decision -> allowed", _allowed(_run_guard(root, _payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / SESSION_REL).unlink()
        check("[stop-guard] missing session file -> allowed", _allowed(_run_guard(root, _payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        real = root / ".vss" / "marker-real"
        (root / ".vss" / "auto-resume").rename(real)
        (root / ".vss" / "auto-resume").symlink_to(real)
        check("[stop-guard] symlinked marker -> allowed", _allowed(_run_guard(root, _payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / ".vss" / "stop-guard").mkdir()
        check("[stop-guard] counter path is a directory -> allowed", _allowed(_run_guard(root, _payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        check("[stop-guard] non-JSON stdin -> allowed", _allowed(_run_guard(root, "not json {")))
        check("[stop-guard] empty stdin -> allowed", _allowed(_run_guard(root, "")))
        check("[stop-guard] allow paths leave no counter file",
              not (root / ".vss" / "stop-guard").exists())
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        old = time.time() - 7 * 3600
        os.utime(root / ".vss" / "auto-resume", (old, old))
        check("[stop-guard] marker not refreshed for 7h (crash-left) -> allowed",
              _allowed(_run_guard(root, _payload())))
        check("[stop-guard] freshness window is env-tunable",
              _blocked(_run_guard(root, _payload(), {"VIBE_STOP_GUARD_FRESH_SECS": "90000"})))


def test_stop_guard_caps_refusals_without_a_commit():
    print("\n[stop-guard] refusals without a new commit are capped; the release sticks; a commit re-arms")
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        _git(root, "init", "-q")
        _git(root, "commit", "-q", "--allow-empty", "-m", "one")
        results = [_run_guard(root, _payload()) for _ in range(5)]
        check("[stop-guard] refusals 1-3 block", all(_blocked(r) for r in results[:3]),
              " | ".join(r.stdout[:40] for r in results))
        check("[stop-guard] refusal count is shown in the reason",
              "refusal 1 of 3" in results[0].stdout and "refusal 3 of 3" in results[2].stdout)
        check("[stop-guard] the 4th stop with no new commit is let through", _allowed(results[3]), results[3].stdout)
        check("[stop-guard] ... and says why on stderr", "letting this and later stops through" in results[3].stderr,
              results[3].stderr)
        check("[stop-guard] the release is remembered (5th stop allowed too)", _allowed(results[4]), results[4].stdout)

        with (root / SESSION_REL).open("a") as fh:
            fh.write("\n## Iter 2\nnothing to do\n")
        check("[stop-guard] editing the session file alone does NOT re-arm it",
              _allowed(_run_guard(root, _payload())))

        _git(root, "commit", "-q", "--allow-empty", "-m", "two")
        r = _run_guard(root, _payload())
        check("[stop-guard] a new commit re-arms the guard", _blocked(r), r.stdout)
        check("[stop-guard] ... back to refusal 1", "refusal 1 of 3" in r.stdout, r.stdout)
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r1 = _run_guard(root, _payload(), {"VIBE_STOP_GUARD_MAX": "1"})
        r2 = _run_guard(root, _payload(), {"VIBE_STOP_GUARD_MAX": "1"})
        check("[stop-guard] VIBE_STOP_GUARD_MAX=1: one refusal then allow",
              _blocked(r1) and _allowed(r2), f"{r1.stdout!r} {r2.stdout!r}")
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        _run_guard(root, _payload())
        check("[stop-guard] a different session never inherits the owner's count",
              _allowed(_run_guard(root, _payload(session_id="other"))))


def test_stop_guard_wiring():
    print("\n[stop-guard] wired into both runtimes, root-owned, in the liveness chain")
    hooks = json.loads(CODEX_HOOKS_JSON.read_text()).get("hooks", {})
    stop = hooks.get("Stop", [])
    cmds = [h.get("command") for g in stop for h in g.get("hooks", [])]
    check("[stop-guard] Codex Stop runs the guard exactly once", cmds.count(GUARD_CMD_CODEX) == 1, str(stop))
    check("[stop-guard] every Codex Stop hook is a hardened env -i form",
          all(c == GUARD_CMD_CODEX or c.startswith("/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/") for c in cmds), str(cmds))
    check("[stop-guard] Codex Stop hook has a timeout and no async",
          all("timeout" in h and "async" not in h for g in stop for h in g.get("hooks", [])), str(stop))
    elsewhere = [h.get("command", "") for ev, gs in hooks.items() if ev != "Stop"
                 for g in gs for h in g.get("hooks", [])]
    check("[stop-guard] Codex runs the guard on Stop only",
          not any("vsss-stop-guard" in c for c in elsewhere), str(elsewhere))

    launcher = VIBE.read_text()
    start = launcher.index('cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\'')
    body = launcher[launcher.index("\n", start) + 1:launcher.index("\nEOF\n", start)]
    config = json.loads(body)
    claude_stop = [h.get("command") for g in config["hooks"].get("Stop", []) for h in g.get("hooks", [])]
    check("[stop-guard] Claude settings.local.json Stop runs the guard (skipped on an image without it)",
          GUARD_CMD_CLAUDE in claude_stop, str(claude_stop))

    dockerfile = (REPO / "devcontainer" / "Dockerfile").read_text()
    check("[stop-guard] Dockerfile installs it root-owned",
          "COPY --chown=root:root vsss-stop-guard.sh /usr/local/bin/vsss-stop-guard" in dockerfile)
    check("[stop-guard] Dockerfile marks it executable", "/usr/local/bin/vsss-stop-guard " in dockerfile)

    liveness = LIVENESS_SH.read_text()
    check("[stop-guard] liveness gate accepts the hardened Stop command form",
          "|vsss-stop-guard|" in liveness)
    check("[stop-guard] liveness gate checks its ownership",
          'check_owned "$bin/vsss-stop-guard"' in liveness)

    vsss = (REPO / "devcontainer" / "commands" / "vsss.md").read_text()
    check("[stop-guard] vsss.md's marker carries owner= for both runtimes",
          "owner=<$CLAUDE_CODE_SESSION_ID, or $CODEX_THREAD_ID" in vsss)
    check("[stop-guard] its counter is gitignored",
          ".vss/stop-guard*" in (REPO / ".gitignore").read_text())


def test_liveness_ties_each_hook_program_to_its_event():
    print("\n[stop-guard] liveness refuses a hook program wired to the wrong event")
    from smoke.checks_18_codex_runtime import (CURRENT_OWNER, _codex_liveness_fixture,
                                                _codex_version_stub, _run_liveness)
    with tempfile.TemporaryDirectory() as td:
        root, bin_dir = _codex_liveness_fixture(Path(td))
        stub_dir = _codex_version_stub(Path(td), "codex-stub", "codex-cli 0.156.1")
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[stop-guard] shipped chain is healthy in the fixture", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
        check("[stop-guard] shipped hooks.json passes the event mapping",
              "not where it belongs" not in (r.stdout + r.stderr), r.stdout + r.stderr)
        hooks_path = root / "hooks" / "hooks.json"
        data = json.loads(hooks_path.read_text())
        data["hooks"]["PreToolUse"].append(data["hooks"].pop("Stop")[0])
        hooks_path.write_text(json.dumps(data))
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[stop-guard] the keep-going guard moved to PreToolUse fails liveness",
              r.returncode != 0 and "codex-stop-guard is wired to the PreToolUse event" in (r.stdout + r.stderr),
              f"rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}")


def _run_ask(root: Path, payload, extra_env: dict | None = None):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "VIBE_STOP_GUARD_ROOT": str(root)}
    if extra_env:
        env.update(extra_env)
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(["/usr/bin/env", "-i", *[f"{k}={v}" for k, v in env.items()],
                           "/bin/bash", str(STOP_GUARD), "ask"],
                          input=data, capture_output=True, text=True, timeout=30)


def _ask_payload(session_id: str | None = SID) -> dict:
    p = {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
         "tool_input": {"questions": [{"question": "Which licence?"}]}}
    if session_id is not None:
        p["session_id"] = session_id
    return p


def _denied(r) -> bool:
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"]
        return r.returncode == 0 and out["permissionDecision"] == "deny" and out["hookEventName"] == "PreToolUse"
    except (json.JSONDecodeError, KeyError, TypeError):
        return False


def test_ask_mode_parks_no_live_run_on_a_question():
    print("\n[stop-guard ask] AskUserQuestion mid-run is denied; everything else is allowed and marked")
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r = _run_ask(root, _ask_payload())
        check("[stop-guard ask] live owned run past its start: question denied", _denied(r), r.stdout + r.stderr)
        reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if _denied(r) else ""
        check("[stop-guard ask] reason sends it to fromClaude and says to carry on",
              "fromClaude" in reason and "carry on" in reason, reason)
        check("[stop-guard ask] reason leads with the hard-escalate rule",
              reason.split("unattended. ", 1)[-1].startswith("If this question is on the hard-escalate list, you must NOT carry on")
              and "## Final state" in reason and "active=0" in reason, reason)
        check("[stop-guard ask] a denied question writes no awaiting-human marker",
              not (root / ".vss" / "awaiting-human").exists())
        check("[stop-guard ask] ask mode never touches the Stop counter",
              not (root / ".vss" / "stop-guard").exists())
    allow_cases = [
        ("front-loaded (no Iter block yet)", {}, _ask_payload(), lambda root: (root / SESSION_REL).write_text("# /vsss session\n")),
        ("Final state written (a hard-escalate)", dict(final=True), _ask_payload(), None),
        ("another session", {}, _ask_payload(session_id="other"), None),
        ("active=0", dict(active="0"), _ask_payload(), None),
    ]
    for label, kw, payload, tweak in allow_cases:
        with tempfile.TemporaryDirectory() as td:
            root = _guard_fixture(Path(td), **kw)
            if tweak:
                tweak(root)
            r = _run_ask(root, payload)
            check(f"[stop-guard ask] {label}: allowed", _allowed(r), r.stdout + r.stderr)
            check(f"[stop-guard ask] {label}: awaiting-human written, as the old hook did",
                  (root / ".vss" / "awaiting-human").is_file())
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / ".vss" / "auto-resume").unlink()
        r = _run_ask(root, _ask_payload())
        check("[stop-guard ask] no marker: allowed and no awaiting-human (old hook's gate)",
              _allowed(r) and not (root / ".vss" / "awaiting-human").exists(), r.stdout)
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        (root / ".vss" / "awaiting-human").write_text("1\n")
        r = _run_ask(root, _ask_payload())
        check("[stop-guard ask] a stale awaiting-human marker does not let the question through",
              _denied(r), r.stdout)
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        old = time.time() - 7 * 3600
        os.utime(root / ".vss" / "auto-resume", (old, old))
        check("[stop-guard ask] a marker not refreshed for 7h: question allowed",
              _allowed(_run_ask(root, _ask_payload())))
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r = _run_guard(root, {**_ask_payload(), "hook_event_name": "PreToolUse"})
        check("[stop-guard] stop mode handed a PreToolUse payload (old image, new settings) fails open",
              _allowed(r), r.stdout)
    with tempfile.TemporaryDirectory() as td:
        root = _guard_fixture(Path(td))
        r = _run_ask(root, "not json")
        check("[stop-guard ask] garbage input fails open and still marks the pending question",
              _allowed(r) and (root / ".vss" / "awaiting-human").is_file(), r.stdout)

    launcher = VIBE.read_text()
    start = launcher.index('cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\'')
    body = launcher[launcher.index("\n", start) + 1:launcher.index("\nEOF\n", start)]
    pre = json.loads(body)["hooks"]["PreToolUse"]
    ask_cmds = [h["command"] for g in pre if g.get("matcher") == "AskUserQuestion" for h in g["hooks"]]
    check("[stop-guard ask] Claude's AskUserQuestion PreToolUse hook runs the guard in ask mode",
          len(ask_cmds) == 1 and ask_cmds[0].startswith("[ -x /usr/local/bin/vsss-stop-guard ] && /usr/local/bin/vsss-stop-guard ask || "),
          str(ask_cmds))
