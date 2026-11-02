"""vibe-delegate recovers from a stale firewall pin by itself.

A mailandeye $vsss run (2026-09-25) stopped after its independent Spec
Critic — a `vibe-delegate role` call to OpenAI — failed six times. The
container's extra firewall domains are pinned at start and CDN addresses
move, so the commonest cause is a stale pin that
`refresh-extra-domains.sh` fixes. The delegate now does that itself: on a
connection-shaped failure of a read-only or tool-less model call it runs
`sudo -n /usr/local/bin/refresh-extra-domains.sh` once and retries once.
A writable role is never retried (it may already have changed files).
"""
from smoke._core import *  # noqa: F401,F403
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call

import json
import tempfile


def _with_sudo_stub(env: dict, home: Path) -> None:
    bins = Path(env["PATH"].split(os.pathsep)[0])
    (bins / "sudo").write_text(f"#!/bin/sh\necho \"$*\" >> {home}/sudo.log\nexit 0\n")
    (bins / "sudo").chmod(0o755)


def _execs(calls):
    return [c for c in calls if c["vendor"] == "claude" or "exec" in c["args"]]


def test_delegate_refreshes_and_retries_a_connection_failure():
    print("\n[delegate] a connection failure refreshes the firewall pins and retries once (read-only calls)")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        _with_sudo_stub(env, home)
        r, calls = _delegate_call(workspace, home, env, ["role", "spec-critic", "--model", "astra", "--cwd", str(workspace)],
                                  {"connection_fail_first": True, "answer": {"report": "fine", "status": "done"}})
        check("[delegate] read-only Codex role: succeeds on the retry", r.returncode == 0, r.stderr)
        check("[delegate] ... after exactly one refresh (sudo -n, the no-argument script)",
              (home / "sudo.log").exists() and (home / "sudo.log").read_text().strip() == "-n /usr/local/bin/refresh-extra-domains.sh",
              (home / "sudo.log").read_text() if (home / "sudo.log").exists() else "no sudo call")
        check("[delegate] ... two model calls in total, and it says so on stderr",
              len(_execs(calls)) == 2 and "refreshing the firewall" in r.stderr, r.stderr)
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        _with_sudo_stub(env, home)
        r, calls = _delegate_call(workspace, home, env, ["ask", "haiku"], {"connection_fail_first": True})
        check("[delegate] tool-less Claude ask: also retried and succeeds", r.returncode == 0 and len(_execs(calls)) == 2, r.stderr)
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        _with_sudo_stub(env, home)
        r, calls = _delegate_call(workspace, home, env, ["role", "generator", "--model", "astra", "--cwd", str(workspace)],
                                  {"connection_fail_first": True, "answer": {"report": "x", "status": "done"}})
        check("[delegate] a writable role is NOT retried (it may already have changed files)",
              r.returncode != 0 and len(_execs(calls)) == 1 and not (home / "sudo.log").exists(), r.stderr)
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        _with_sudo_stub(env, home)
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"], {"exit": 3})
        check("[delegate] a non-connection failure is not retried and needs no refresh",
              r.returncode != 0 and len(_execs(calls)) == 1 and not (home / "sudo.log").exists(), r.stderr)
