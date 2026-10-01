"""OpenProject (/op) diagnostics (2026-09-30).

After a Mac reboot /op stayed unreachable although the forwarder was
listening. The forwarder dropped connections it could not carry to the
tailnet without a word, and the container only said "forwarder down?".
Now the forwarder logs upstream failures, and the container says which
side failed.
"""
from smoke._core import *  # noqa: F401,F403

import os
import socket
import subprocess
import tempfile
import time

FORWARDER = REPO / "op-mcp-forwarder.py"
REGISTER = REPO / "devcontainer" / "register-op-mcp.sh"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_forwarder_logs_unreachable_upstream() -> None:
    print("\n[op-diagnostics] the forwarder logs when it cannot reach OpenProject")
    listen, dead = _free_port(), _free_port()
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "fwd.log"
        with open(log, "w") as fh:
            proc = subprocess.Popen(["python3", str(FORWARDER), str(listen), "127.0.0.1", str(dead)],
                                    stdin=subprocess.DEVNULL, stdout=fh, stderr=fh)
        try:
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", listen), timeout=1) as c:
                        c.settimeout(3)
                        c.recv(1)  # the forwarder closes it once the upstream fails
                    break
                except OSError:
                    time.sleep(0.1)
            for _ in range(30):
                if "cannot reach" in log.read_text():
                    break
                time.sleep(0.1)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        text = log.read_text()
        check("[op-diagnostics] upstream failure is logged",
              f"cannot reach 127.0.0.1:{dead}" in text and "Tailscale" in text, text[-400:])


def _register_run(tmp: Path, curl_rc: int) -> subprocess.CompletedProcess:
    binn = tmp / "bin"
    binn.mkdir(exist_ok=True)
    (binn / "curl").write_text(f"#!/bin/sh\nexit {curl_rc}\n")
    (binn / "claude").write_text("#!/bin/sh\nexit 0\n")
    for f in ("curl", "claude"):
        (binn / f).chmod(0o755)
    env = {**os.environ, "PATH": f"{binn}:{os.environ.get('PATH', '')}",
           "OPENPROJECT_MCP_URL": "https://op.example.ts.net/mcp/",
           "OPENPROJECT_MCP_BEARER": "fixture"}
    return run(["bash", str(REGISTER)], env=env)


def test_register_names_the_failing_side() -> None:
    print("\n[op-diagnostics] register-op-mcp says which side failed")
    with tempfile.TemporaryDirectory() as td:
        cases = ((7, "forwarder down?"), (56, "Tailscale down on the Mac?"),
                 (35, "Tailscale down on the Mac?"), (28, "timed out"), (60, "curl exit 60"))
        for rc, want in cases:
            r = _register_run(Path(td), rc)
            check(f"[op-diagnostics] curl {rc} -> '{want}'",
                  "not reachable" in r.stdout and want in r.stdout and r.returncode == 0,
                  r.stdout + r.stderr)
        r = _register_run(Path(td), 0)
        check("[op-diagnostics] reachable -> registered", "registered OpenProject MCP" in r.stdout,
              r.stdout + r.stderr)
