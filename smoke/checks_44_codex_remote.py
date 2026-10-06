"""Codex remote control in vibe (2026-10-06).

Codex's phone remote control needs the TUI on a shared app-server, and
Codex's own managed daemon drops `-c agents.enabled=false`, self-updates
outside the compat gate and keeps its files in the Mac's shared ~/.codex.
So with VIBE_CODEX_REMOTE=1, codex-entry starts the image's codex as a
plain `app-server --remote-control -c agents.enabled=false` on a socket in
the container's /tmp, and points the TUI at it with `--remote`.
codex-remote (devcontainer/codex-remote.mjs) talks to that server.

Everything here runs offline against a stub app-server that speaks the
same WebSocket-over-unix-socket JSON-RPC as the real one.
"""
from smoke._core import *  # noqa: F401,F403

import json
import os
import subprocess
import sys
import tempfile
import time

from smoke.checks_22_codex_agent import _extract_func

CODEX_REMOTE = REPO / "devcontainer" / "codex-remote.mjs"
CODEX_ENTRY_SH = REPO / "devcontainer" / "codex-entry.sh"
DOCKERFILE = REPO / "devcontainer" / "Dockerfile"
LIVENESS_SH = REPO / "devcontainer" / "codex-guard-liveness.sh"

# A stub app-server: `--listen unix://PATH`, WebSocket upgrade, one JSON-RPC
# message per text frame. Behaviour comes from fixture.json beside it; every
# request (method + params) is appended to requests.jsonl.
_STUB_SERVER = r'''
import base64, hashlib, json, os, socket, struct, sys, threading
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = json.load(open(os.path.join(HERE, "fixture.json")))
LOG = os.path.join(HERE, "requests.jsonl")
path = sys.argv[sys.argv.index("--listen") + 1][len("unix://"):]
polls = {"n": 0, "status": 0}

def recv_exact(c, n, buf):
    while len(buf[0]) < n:
        d = c.recv(65536)
        if not d: raise EOFError
        buf[0] += d
    out, buf[0] = buf[0][:n], buf[0][n:]
    return out

def send(c, obj):
    d = json.dumps(obj).encode(); n = len(d)
    h = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n))
    c.sendall(h + d)

def answer(m):
    meth, p = m.get("method"), m.get("params") or {}
    if meth == "initialize": return {"userAgent": "stub"}
    if meth == "remoteControl/status/read":
        polls["status"] += 1
        if polls["status"] <= FIX.get("connectingReads", 0):
            return {"status": "connecting", "serverName": "stub-host", "installationId": "inst", "environmentId": None}
        return {"status": FIX.get("status", "connected"), "serverName": "stub-host",
                "installationId": "inst", "environmentId": FIX.get("environmentId", "env-1")}
    if meth == "remoteControl/client/list": return {"data": FIX.get("clients", [])}
    if meth == "remoteControl/client/revoke": return {}
    if meth == "remoteControl/pairing/start":
        return {"environmentId": "env-1", "expiresAt": FIX.get("expiresAt", 4102444800),
                "pairingCode": "LONG-PAIRING-TOKEN", "manualPairingCode": FIX.get("code", "ABCD-1234")}
    if meth == "remoteControl/pairing/status":
        polls["n"] += 1
        return {"claimed": polls["n"] >= FIX.get("claimAfter", 2)}
    return None

def serve(c):
    buf = [b""]
    try:
        while b"\r\n\r\n" not in buf[0]:
            d = c.recv(4096)
            if not d: return
            buf[0] += d
        head, buf[0] = buf[0].split(b"\r\n\r\n", 1)
        key = [l.split(b":", 1)[1].strip() for l in head.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
        acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
        c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
        while True:
            b1, b2 = recv_exact(c, 2, buf)
            n = b2 & 127
            if n == 126: n = struct.unpack(">H", recv_exact(c, 2, buf))[0]
            elif n == 127: n = struct.unpack(">Q", recv_exact(c, 8, buf))[0]
            mask = recv_exact(c, 4, buf) if b2 & 0x80 else b"\0\0\0\0"
            data = bytes(x ^ mask[i % 4] for i, x in enumerate(recv_exact(c, n, buf)))
            if b1 & 15 == 8: return
            m = json.loads(data)
            with open(LOG, "a") as f: f.write(json.dumps({"method": m.get("method"), "params": m.get("params")}) + "\n")
            if "id" not in m: continue
            r = answer(m)
            if r is None: send(c, {"id": m["id"], "error": {"code": -32601, "message": "unknown"}})
            else: send(c, {"id": m["id"], "result": r})
            if m.get("method") == "remoteControl/pairing/status" and FIX.get("closeAfterPairingStatus"):
                return
    except (EOFError, OSError):
        return
    finally:
        c.close()

try: os.unlink(path)
except FileNotFoundError: pass
s = socket.socket(socket.AF_UNIX); s.bind(path); s.listen(8)
while True:
    c, _ = s.accept()
    threading.Thread(target=serve, args=(c,), daemon=True).start()
'''


def _stub_dir(tmp: Path, fixture: dict) -> Path:
    d = tmp / "stub"
    d.mkdir(exist_ok=True)
    (d / "server.py").write_text(_STUB_SERVER)
    (d / "fixture.json").write_text(json.dumps(fixture))
    return d


def _start_stub(stub: Path, sock: Path):
    p = subprocess.Popen([sys.executable, "-I", str(stub / "server.py"), "--listen", f"unix://{sock}"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if sock.exists():
            return p
        time.sleep(0.05)
    _stop(p)
    raise RuntimeError(f"stub app-server never created {sock}")


def _stop(p):
    p.kill()
    p.wait()


def _remote(sock: Path, *args: str):
    return run(["node", str(CODEX_REMOTE), "--socket", str(sock), *args])


def _requests(stub: Path) -> list:
    f = stub / "requests.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_codex_remote_frames_round_trip():
    print("\n[codex-remote] WebSocket frames round-trip at every length class")
    js = (
        f"import {{ encodeFrame, decodeFrames }} from {json.dumps(str(CODEX_REMOTE))};\n"
        "const out = [];\n"
        "for (const n of [0, 5, 125, 126, 65535, 65536, 70000]) {\n"
        "  const text = 'x'.repeat(n);\n"
        "  const two = Buffer.concat([encodeFrame(text), encodeFrame('tail')]);\n"
        "  const { frames, rest } = decodeFrames(two.subarray(0, two.length - 1));\n"
        "  const all = decodeFrames(two);\n"
        "  out.push(frames.length === 1 && frames[0].payload.toString() === text && rest.length > 0\n"
        "    && all.frames.length === 2 && all.frames[1].payload.toString() === 'tail'\n"
        "    && all.frames[0].fin && all.frames[0].opcode === 1);\n"
        "}\n"
        "console.log(JSON.stringify(out));\n"
    )
    r = run(["node", "--input-type=module", "-e", js])
    ok = r.returncode == 0 and r.stdout.strip() == json.dumps([True] * 7).replace(" ", "")
    check("[codex-remote] masked client frames decode back to the same text, partial tail kept",
          ok, r.stdout + r.stderr)


def test_codex_remote_status_clients_revoke():
    print("\n[codex-remote] status, clients and revoke against a stub app-server")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sock = tmp / "s.sock"
        stub = _stub_dir(tmp, {"status": "connected", "clients": [
            {"clientId": "c-1", "displayName": "Martin's iPhone", "lastSeenAt": 1791300000}]})
        p = _start_stub(stub, sock)
        try:
            r = _remote(sock, "status")
            check("[codex-remote] status connected -> exit 0 and says the app can reach it",
                  r.returncode == 0 and "connected" in r.stdout and "stub-host" in r.stdout, r.stdout + r.stderr)
            r = _remote(sock, "clients")
            check("[codex-remote] clients lists id and name",
                  r.returncode == 0 and r.stdout.startswith("c-1\tMartin's iPhone\tlast seen "), r.stdout + r.stderr)
            r = _remote(sock, "revoke", "c-1")
            revokes = [q for q in _requests(stub) if q["method"] == "remoteControl/client/revoke"]
            check("[codex-remote] revoke sends the client id and the connected environment",
                  r.returncode == 0 and revokes == [{"method": "remoteControl/client/revoke",
                                                     "params": {"environmentId": "env-1", "clientId": "c-1"}}],
                  r.stdout + r.stderr + str(revokes))
            inits = [q for q in _requests(stub) if q["method"] == "initialize"]
            check("[codex-remote] initialize opts into the experimental API (remoteControl/* needs it)",
                  bool(inits) and all((q["params"] or {}).get("capabilities", {}).get("experimentalApi") is True
                                      for q in inits), str(inits))
        finally:
            _stop(p)

        (tmp / "x").mkdir()
        stub2 = _stub_dir(tmp / "x", {"status": "errored", "environmentId": None})
        sock2 = tmp / "x" / "s.sock"
        p = _start_stub(stub2, sock2)
        try:
            r = _remote(sock2, "status")
            check("[codex-remote] status errored -> exit 1 with a login hint",
                  r.returncode == 1 and "errored" in r.stdout and "codex login status" in r.stdout, r.stdout + r.stderr)
            r = _remote(sock2, "--timeout", "1", "clients")
            check("[codex-remote] clients while not connected -> exit 1, says so",
                  r.returncode == 1 and "not connected" in r.stderr, r.stdout + r.stderr)
        finally:
            _stop(p)

        (tmp / "y").mkdir()
        stub3 = _stub_dir(tmp / "y", {"connectingReads": 2})
        sock3 = tmp / "y" / "s.sock"
        p = _start_stub(stub3, sock3)
        try:
            r = _remote(sock3, "status")
            check("[codex-remote] status without --timeout reports the first read (connecting) -> exit 1",
                  r.returncode == 1 and "connecting" in r.stdout, r.stdout + r.stderr)
            r = _remote(sock3, "--timeout", "10", "status")
            check("[codex-remote] status --timeout waits through 'connecting' to 'connected'",
                  r.returncode == 0 and "connected" in r.stdout, r.stdout + r.stderr)
        finally:
            _stop(p)

        r = run(["node", str(CODEX_REMOTE), "status"])
        check("[codex-remote] no --socket and no VIBE_CODEX_REMOTE_SOCKET -> exit 1, says where it works",
              r.returncode == 1 and "VIBE_CODEX_REMOTE=1" in r.stderr, r.stderr)
        r = _remote(tmp / "missing.sock", "status")
        check("[codex-remote] no server -> exit 1 naming VIBE_CODEX_REMOTE=1",
              r.returncode == 1 and "VIBE_CODEX_REMOTE=1" in r.stderr, r.stderr)
        r = run(["node", str(CODEX_REMOTE), "frobnicate"])
        check("[codex-remote] unknown subcommand -> usage exit 2", r.returncode == 2, r.stderr)
        r = run(["node", str(CODEX_REMOTE), "revoke"])
        check("[codex-remote] revoke without an id -> usage exit 2", r.returncode == 2, r.stderr)


def test_codex_remote_pair_prints_code_only_to_stdout():
    print("\n[codex-remote] pair prints the manual code, waits for the claim, writes no file")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sock = tmp / "s.sock"
        stub = _stub_dir(tmp, {"code": "WXYZ-9876", "claimAfter": 2})
        p = _start_stub(stub, sock)
        work = tmp / "cwd"
        work.mkdir()
        try:
            r = run(["node", str(CODEX_REMOTE), "--socket", str(sock), "pair"], cwd=work)
        finally:
            _stop(p)
        check("[codex-remote] pair -> exit 0 and 'Paired.' after the phone claims the code",
              r.returncode == 0 and "WXYZ-9876" in r.stdout and "Paired." in r.stdout, r.stdout + r.stderr)
        statuses = [q for q in _requests(stub) if q["method"] == "remoteControl/pairing/status"]
        check("[codex-remote] pair polls status with the manual code it showed",
              len(statuses) >= 2 and all(q["params"] == {"manualPairingCode": "WXYZ-9876"} for q in statuses),
              str(statuses))
        starts = [q for q in _requests(stub) if q["method"] == "remoteControl/pairing/start"]
        check("[codex-remote] pair asks for a manual (typeable) code",
              starts == [{"method": "remoteControl/pairing/start", "params": {"manualCode": True}}], str(starts))
        check("[codex-remote] pair writes nothing to its working directory",
              list(work.iterdir()) == [], str(list(work.iterdir())))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sock = tmp / "s.sock"
        stub = _stub_dir(tmp, {"claimAfter": 99, "closeAfterPairingStatus": True})
        p = _start_stub(stub, sock)
        try:
            r = _remote(sock, "pair")
        finally:
            _stop(p)
        check("[codex-remote] server going away mid-pair -> exit 1 with a reason, not a silent 0",
              r.returncode == 1 and "closed the connection" in r.stderr and "Paired." not in r.stdout,
              f"rc={r.returncode} " + r.stdout + r.stderr)
    src = CODEX_REMOTE.read_text()
    check("[codex-remote] source never writes a file (no fs write API imported)",
          "writeFile" not in src and "appendFile" not in src and "createWriteStream" not in src, "")


# ── codex-entry --remote-control ───────────────────────────────────────────

def _entry_chain(tmp: Path, fixture: dict):
    root = tmp / "root"; root.mkdir()
    (root / "requirements.toml").write_text("# fixture\n")
    bindir = tmp / "bin"; bindir.mkdir()
    login = tmp / "login"; login.mkdir()
    entry = bindir / "codex-entry"
    entry.write_text(CODEX_ENTRY_SH.read_text()); entry.chmod(0o755)
    helper = bindir / "codex-remote"
    helper.write_text(CODEX_REMOTE.read_text()); helper.chmod(0o755)
    gate = bindir / "codex-guard-liveness"
    gate.write_text("#!/bin/bash\nprintf 'ok stub-check\\n'\n"); gate.chmod(0o755)
    stub = _stub_dir(tmp, fixture)
    argv_log = tmp / "argv.jsonl"
    codex = tmp / "codex"
    codex.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"open({str(argv_log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
        "if sys.argv[1:2] == ['app-server']:\n"
        f"    os.execv({sys.executable!r}, [{sys.executable!r}, '-I', {str(stub / 'server.py')!r}] + sys.argv[1:])\n"
    )
    codex.chmod(0o755)
    return root, bindir, login, codex, argv_log, stub


def _run_entry_remote(tmp, root, bindir, login, codex, *extra, pre=()):
    env = {**os.environ, "TMPDIR": str(tmp)}
    env.pop("VIBE_CODEX_REMOTE_SOCKET", None)
    return run(["bash", str(bindir / "codex-entry"), *pre, "--root", str(root), "--bin", str(bindir),
                "--login-dir", str(login), "--codex", str(codex), "--remote-control", "--", *extra], env=env)


def _calls(argv_log: Path) -> list:
    return [json.loads(l) for l in argv_log.read_text().splitlines()] if argv_log.exists() else []


def test_codex_entry_remote_control_runs_owned_server():
    print("\n[codex-remote] codex-entry --remote-control: owned server keeps the override; TUI is a client")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, login, codex, argv_log, stub = _entry_chain(tmp, {"status": "connected", "clients": []})
        r = _run_entry_remote(tmp, root, bindir, login, codex, "--x")
        calls = _calls(argv_log)
        listen = calls[0][-1] if calls and calls[0] else ""
        sock_dir = Path(listen[len("unix://"):]).parent if listen.startswith("unix://") else None
        check("[codex-remote] entry exits 0 with the remote-control banner",
              r.returncode == 0 and "starting codex with remote control" in r.stdout, r.stdout + r.stderr)
        check("[codex-remote] server argv: app-server --remote-control, sub-agents off, unix socket",
              bool(calls) and calls[0][:5] == ["app-server", "--remote-control", "-c", "agents.enabled=false",
                                               "--listen"] and listen.endswith("/app-server.sock"), str(calls))
        check("[codex-remote] the socket is in a fresh mktemp directory, not a fixed path",
              sock_dir is not None and sock_dir.parent == tmp and sock_dir.name.startswith("vibe-codex-remote.")
              and sock_dir.name != "vibe-codex-remote.XXXXXXXX", str(sock_dir))
        check("[codex-remote] TUI argv: --remote to that socket, the override too, then the caller's args",
              len(calls) == 2 and calls[1] == ["--remote", listen, "-c", "agents.enabled=false", "--x"], str(calls))
        check("[codex-remote] no pairing prompt without a terminal on stdin",
              "Pair one now?" not in r.stdout, r.stdout)
        check("[codex-remote] the socket directory is removed when the session ends",
              sock_dir is not None and not sock_dir.exists(), str(sock_dir))
        time.sleep(0.3)
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        check("[codex-remote] the server is stopped when the session ends",
              str(stub / "server.py") not in ps, "")

        # Not connected: the session still starts, and says remote control is off.
        argv_log.unlink()
        (stub / "fixture.json").write_text(json.dumps({"status": "errored", "environmentId": None}))
        r = _run_entry_remote(tmp, root, bindir, login, codex)
        check("[codex-remote] server errored -> session still starts, says remote control is unavailable",
              r.returncode == 0 and "Remote control is not available this session" in r.stdout, r.stdout + r.stderr)


def test_codex_entry_remote_control_falls_back_and_refuses():
    print("\n[codex-remote] codex-entry --remote-control: falls back if the server never answers; refusals")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, login, codex, argv_log, stub = _entry_chain(tmp, {})
        # A Codex whose app-server dies at once: the session must still start,
        # on the ordinary path, with the override.
        (stub / "server.py").write_text("import sys; sys.exit(3)\n")
        r = _run_entry_remote(tmp, root, bindir, login, codex, "--y")
        calls = _calls(argv_log)
        check("[codex-remote] server never answers -> exit 0, says it continues without remote control",
              r.returncode == 0 and "did not start; continuing without remote control" in r.stderr,
              r.stdout + r.stderr)
        check("[codex-remote] fallback runs the ordinary TUI with the override",
              len(calls) == 2 and calls[1] == ["-c", "agents.enabled=false", "--y"], str(calls))
        check("[codex-remote] fallback leaves no socket directory behind",
              not list(tmp.glob("vibe-codex-remote.*")), str(list(tmp.glob("vibe-codex-remote.*"))))

        r = _run_entry_remote(tmp, root, bindir, login, codex, pre=("--supervise",))
        check("[codex-remote] --remote-control with --supervise is refused",
              r.returncode == 1 and "remote control is for interactive Codex sessions" in r.stderr,
              r.stdout + r.stderr)
        (bindir / "codex-remote").unlink()
        r = _run_entry_remote(tmp, root, bindir, login, codex)
        check("[codex-remote] a missing helper is refused",
              r.returncode == 1 and "codex-remote is missing" in r.stderr, r.stdout + r.stderr)


def test_codex_entry_pairing_offer_on_a_terminal():
    print("\n[codex-remote] codex-entry offers pairing on a terminal; 'y' pairs, then Codex starts")
    import pty
    import select
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, login, codex, argv_log, stub = _entry_chain(
            tmp, {"status": "connected", "clients": [], "code": "PTY-4242", "claimAfter": 1})
        env = {**os.environ, "TMPDIR": str(tmp)}
        env.pop("VIBE_CODEX_REMOTE_SOCKET", None)
        argv = ["bash", str(bindir / "codex-entry"), "--root", str(root), "--bin", str(bindir),
                "--login-dir", str(login), "--codex", str(codex), "--remote-control", "--"]
        pid, fd = pty.fork()
        if pid == 0:
            os.execve("/bin/bash", argv, env)
        out = b""
        answered = False
        deadline = time.time() + 30
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if fd not in ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if not answered and b"Pair one now? [y/N]" in out:
                os.write(fd, b"y\n")
                answered = True
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        text = out.decode("utf-8", "replace")
        calls = _calls(argv_log)
        check("[codex-remote] the offer appears on a terminal while no phone is paired", answered, text[-600:])
        check("[codex-remote] 'y' prints the code and waits for the claim",
              "PTY-4242" in text and "Paired." in text, text[-600:])
        check("[codex-remote] Codex starts after pairing, as a client of the server",
              os.WEXITSTATUS(status) == 0 and len(calls) == 2 and calls[1][0] == "--remote", str(calls))


def test_codex_remote_wiring():
    print("\n[codex-remote] Dockerfile, liveness, launcher wiring")
    df = DOCKERFILE.read_text()
    check("[codex-remote] Dockerfile installs codex-remote root-owned",
          "COPY --chown=root:root codex-remote.mjs /usr/local/bin/codex-remote" in df, "")
    check("[codex-remote] codex-remote is in a chmod +x list",
          any("/usr/local/bin/codex-remote " in l for l in df.splitlines() if "chmod +x" in l), "")
    check("[codex-remote] the liveness gate checks codex-remote's ownership",
          'check_owned "$bin/codex-remote"' in LIVENESS_SH.read_text(), "")
    func = _extract_func(VIBE.read_text(), "launch_codex")
    check("[codex-remote] launcher passes a fixed --remote-control only when VIBE_CODEX_REMOTE=1",
          '[ "${VIBE_CODEX_REMOTE:-0}" != 1 ] || CODEX_REMOTE_FLAG=" --remote-control"' in func
          and "/usr/local/bin/codex-entry$CODEX_REMOTE_FLAG\"" in func, func)
    check("[codex-remote] the supervised path never gets --remote-control",
          func.index("CODEX_REMOTE_FLAG") > func.index("--supervise"), "")
