"""vibe-capabilities: the inventory an agent reads before saying "I can't".

Martin's report (2026-09-25): agents keep saying they can't look at an output
when the Mac they run on gives them a dedicated account to build and observe
anything. The inventory must find that account from the mirrored SSH config
(one entry on the Mac declares it for every container), say how to use it,
say how to switch on what is missing, and never connect anywhere to find out.
"""
from smoke._core import *  # noqa: F401,F403

import json
import os
import subprocess
import tempfile

CAPS = REPO / "devcontainer" / "vibe-capabilities.sh"
FRAGMENT = REPO / "devcontainer" / "claude-md" / "capabilities.md"


def _caps_fixture(td: Path, ssh_config: str | None) -> tuple[Path, Path, Path]:
    home = td / "home"
    (home / ".ssh").mkdir(parents=True)
    if ssh_config is not None:
        (home / ".ssh" / "config").write_text(ssh_config)
    ws = td / "ws"
    (ws / ".vibe").mkdir(parents=True)
    # A bin dir whose ssh/scp record any call: the inventory must never connect.
    bindir = td / "bin"
    bindir.mkdir()
    for tool in ("ssh", "scp"):
        stub = bindir / tool
        stub.write_text(f"#!/bin/sh\necho called >> {td}/{tool}.called\nexit 99\n")
        stub.chmod(0o755)
    return home, ws, bindir


def _caps(td: Path, home: Path, ws: Path, bindir: Path, *args, extra: dict | None = None):
    env = {"PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin", "HOME": str(home),
           "VIBE_CAP_WORKSPACE": str(ws), "VIBE_CAP_NO_PROBE": "1",
           "VIBE_CAP_BRAIN2": str(td / "no-brain2"), "VIBE_CAP_ZOTERO": str(td / "no-zotero"),
           "VIBE_CAP_LEARNINGS": str(td / "no-learnings"), "VIBE_CAP_RUN_DIR": str(td / "run")}
    if extra:
        env.update(extra)
    return subprocess.run(["bash", str(CAPS), *args], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=30)


MAC_CONFIG = "Host github.com\n  User git\nHost shack\n  HostName shack.example\n  User pi\nHost host.docker.internal\n    User claude\n"


def test_capabilities_finds_the_mac_account_from_the_ssh_config():
    print("\n[caps] the Mac account declared in the mirrored SSH config is reported, with how to use it")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, MAC_CONFIG)
        r = _caps(td, home, ws, bindir)
        out = r.stdout
        check("[caps] exits 0", r.returncode == 0, r.stderr)
        avail = out.split("## Available now", 1)[-1].split("## Could be", 1)[0]
        check("[caps] Mac account listed under Available now",
              "Mac account `claude@host.docker.internal`" in avail, out[:600])
        check("[caps] ... says how to see: vibe-shot renders it, Read tool displays images",
              "screenshot" in avail and "vibe-shot <url|folder|file>" in avail and "Read tool displays images" in avail, avail)
        check("[caps] ... names where the declaration came from", "the SSH config (Host host.docker.internal)" in avail, avail)
        check("[caps] ... SSH needs a per-action OK without the project marker", "per-action OK" in avail, avail)
        check("[caps] other SSH hosts listed by name only (not github.com)",
              "shack" in avail and "github.com " not in avail.split("Other SSH hosts", 1)[-1].split("\n", 1)[0], avail)
        check("[caps] never runs ssh or scp", not (td / "ssh.called").exists() and not (td / "scp.called").exists())
        notes = out.split("## Genuinely not here", 1)[-1]
        check("[caps] 'no browser in the container' points at the Mac account", "Use the Mac account above" in notes, notes)

        (ws / ".vibe-allow-ssh").write_text("")
        r = _caps(td, home, ws, bindir)
        check("[caps] .vibe-allow-ssh -> SSH is pre-authorised", "is pre-authorised in this project" in r.stdout, r.stdout[:600])
        check("[caps] ... and the 'switch on' list no longer offers it", "touch .vibe-allow-ssh" not in r.stdout, r.stdout)


def test_capabilities_missing_mac_key_is_not_available():
    print("\n[caps] a Mac account whose IdentityFile is absent here is not offered as available")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        missing = td / "nope" / "id_ed25519_other_project"
        home, ws, bindir = _caps_fixture(td, MAC_CONFIG + f"    IdentityFile {missing}\n")
        r = _caps(td, home, ws, bindir)
        avail = r.stdout.split("## Available now", 1)[-1].split("## Could be", 1)[0]
        check("[caps] missing key -> not under Available now", "Mac account `claude@" not in avail, avail)
        check("[caps] ... the switch-on list names the missing key",
              str(missing) in r.stdout and "is in this container" in r.stdout, r.stdout)
        brief = _caps(td, home, ws, bindir, "--brief").stdout
        check("[caps] ... and --brief leaves it out", "claude@" not in brief, brief)
        present = ws / ".vibe" / "id_ed25519_mac"
        present.write_text("")
        (home / ".ssh" / "config").write_text(
            MAC_CONFIG + f"    IdentityFile {missing}\n    IdentityFile {present}\n")
        r = _caps(td, home, ws, bindir)
        avail = r.stdout.split("## Available now", 1)[-1].split("## Could be", 1)[0]
        check("[caps] one of several keys present -> available", "Mac account `claude@" in avail, avail)
        (home / ".ssh" / "config").write_text(
            MAC_CONFIG + f"    IdentityFile {missing}\nHost *\n  IdentityFile=\"{present}\"\n")
        r = _caps(td, home, ws, bindir)
        avail = r.stdout.split("## Available now", 1)[-1].split("## Could be", 1)[0]
        check("[caps] a key from `Host *` (=, quoted) counts too", "Mac account `claude@" in avail, avail)
        (home / ".ssh" / "config").write_text(MAC_CONFIG + "    IdentityFile %d/.ssh/nope\n")
        r = _caps(td, home, ws, bindir)
        check("[caps] %d expands to home (missing key reported under its real path)",
              f"{home}/.ssh/nope" in r.stdout, r.stdout)


def test_capabilities_without_a_mac_account_says_how_to_get_one():
    print("\n[caps] no Mac account declared: the inventory says exactly how to switch one on")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, "Host github.com\n  User git\n")
        r = _caps(td, home, ws, bindir)
        check("[caps] no Mac account under Available now",
              "Mac account `" not in r.stdout.split("## Could be", 1)[0], r.stdout[:600])
        check("[caps] switch-on list names the setup command", "vibe-capabilities --setup mac-account" in r.stdout, r.stdout)
        check("[caps] 'no browser' says to ask for the Mac account", "Ask for the Mac account" in r.stdout, r.stdout)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, None)
        r = _caps(td, home, ws, bindir)
        check("[caps] no SSH config at all still exits 0", r.returncode == 0, r.stderr)


def test_capabilities_parsing_edges():
    print("\n[caps] SSH-config parsing: multi-host lines, case, overrides, unsafe names")
    cases = [
        ("Host foo host.docker.internal\n  user agentuser\n", {}, "agentuser@host.docker.internal"),
        ("HOST host.docker.internal\n\tUSER tester\n", {}, "tester@host.docker.internal"),
        ("Host *.internal\n  User wild\n", {}, None),
        ("Host host.docker.internal\n  User claude\n", {"VIBE_MAC_USER": "builder"}, "builder@host.docker.internal"),
        ("Host host.docker.internal\n  User bad;rm\n", {}, None),
    ]
    for config, extra, want in cases:
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            home, ws, bindir = _caps_fixture(td, config)
            r = _caps(td, home, ws, bindir, extra=extra)
            label = config.splitlines()[0] + (f" + {extra}" if extra else "")
            if want:
                check(f"[caps] {label!r} -> {want}", f"Mac account `{want}`" in r.stdout, r.stdout[:400])
            else:
                check(f"[caps] {label!r} -> no Mac account", "Mac account `" not in r.stdout, r.stdout[:400])


def test_capabilities_bridge_brief_and_setup_modes():
    print("\n[caps] Mac build bridge detection, --brief, --setup mac-account, bad arguments")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, MAC_CONFIG)
        (ws / ".vibe" / "mac-build.json").write_text("{}")
        r = _caps(td, home, ws, bindir)
        check("[caps] configured bridge listed", "`mac-build doctor|build|test|screenshot`" in r.stdout, r.stdout[:800])
        r = _caps(td, home, ws, bindir, "--brief")
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        check("[caps] --brief is one bullet per capability, Mac account first",
              r.returncode == 0 and all(l.startswith("- ") for l in lines) and "Mac account" in lines[0], r.stdout)
        r = _caps(td, home, ws, bindir, "--setup", "mac-account")
        check("[caps] --setup mac-account gives the steps and this container's status",
              "Remote Login" in r.stdout and "Host host.docker.internal" in r.stdout
              and "declared as claude" in r.stdout, r.stdout)
        r = _caps(td, home, ws, bindir, "--bogus")
        check("[caps] unknown argument exits 2", r.returncode == 2, r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, MAC_CONFIG)
        real = ws / ".vibe" / "elsewhere.json"
        real.write_text("{}")
        (ws / ".vibe" / "mac-build.json").symlink_to(real)
        r = _caps(td, home, ws, bindir)
        check("[caps] a symlinked bridge config is not reported as configured",
              "`mac-build doctor|build|test|screenshot`" not in r.stdout, r.stdout[:800])


def test_capabilities_reach_every_agent():
    print("\n[caps] every agent is pointed at the inventory: Claude fragment, Codex context and session start")
    frag = FRAGMENT.read_text()
    check("[caps] CLAUDE.md fragment tells Claude to run vibe-capabilities before 'I can't'",
          "run `vibe-capabilities`" in frag and "Never stop at \"I can't\"" in frag, frag[:300])
    check("[caps] fragment keeps the SSH per-action ask", "per-action ask" in frag, "")
    check("[caps] Codex context names it", "vibe-capabilities" in (REPO / "devcontainer/codex/context.md").read_text())
    check("[caps] Codex SessionStart additionalContext names it",
          "vibe-capabilities" in (REPO / "devcontainer/codex-prompt-prefix.sh").read_text())
    dockerfile = (REPO / "devcontainer" / "Dockerfile").read_text()
    check("[caps] Dockerfile installs it root-owned and executable",
          "COPY --chown=root:root vibe-capabilities.sh /usr/local/bin/vibe-capabilities" in dockerfile
          and "/usr/local/bin/vibe-capabilities " in dockerfile)


def _nudge(td: Path, home: Path, ws: Path, bindir: Path, message: str, active: bool = False,
           session: str | None = None, tmpdir: Path | None = None):
    payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": active, "last_assistant_message": message,
                          "session_id": session or "s-" + str(abs(hash(message)))})
    if tmpdir is None:
        tmpdir = Path(tempfile.mkdtemp(dir=td))
    env = {"PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "VIBE_CAP_WORKSPACE": str(ws),
           "VIBE_CAP_NO_PROBE": "1", "VIBE_CAP_BRAIN2": str(td / "nb"), "VIBE_CAP_ZOTERO": str(td / "nz"),
           "VIBE_CAP_LEARNINGS": str(td / "nl"), "VIBE_CAP_RUN_DIR": str(td / "run"), "TMPDIR": str(tmpdir)}
    return subprocess.run(["bash", str(CAPS), "--stop-hook"], input=payload, capture_output=True,
                          text=True, env=env, timeout=30)


def _nudged(r) -> bool:
    try:
        return r.returncode == 0 and json.loads(r.stdout).get("decision") == "block"
    except json.JSONDecodeError:
        return False


def test_capability_nudge_sends_a_cant_back_once():
    print("\n[caps nudge] a final 'I can't see/run/build' is sent back once with the capability list")
    denials = [
        "Done. I can't see the rendered page from here, so please check the spacing.",
        "The build passes, but I cannot run the Mac app in this container.",
        "I'm unable to view the output of that command.",
        "I don't have a browser, so I couldn't verify the layout.",
        "Could you send me a screenshot of the error?",
        "You'll need to look at the page on a phone to confirm.",
        "I can\u2019t see the rendered output, sorry.",
    ]
    fine = [
        "Done: built, screenshotted on the Mac account and checked the layout.",
        "I can't push from here by policy; the commits are local.",
        "```\nI can't see the page\n```\nThat quote is from the old log; the new build renders fine.",
        "> I cannot run it\nThat was the user's earlier message; it runs now.",
        "The API can't reach the proxy, so the request timed out.",
        "I can't reach pi02.local; the Pi looks offline.",
        "I can't test on Windows from here.",
        "You'll need to run the launcher on your Mac: vibe --rebuild",
        "The new hook matches `I can't see` phrases.",
        "",
    ]
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        home, ws, bindir = _caps_fixture(td, MAC_CONFIG)
        for msg in denials:
            r = _nudge(td, home, ws, bindir, msg)
            check(f"[caps nudge] sent back: {msg[:48]!r}", _nudged(r), r.stdout + r.stderr)
        r = _nudge(td, home, ws, bindir, denials[0])
        reason = json.loads(r.stdout)["reason"] if _nudged(r) else ""
        check("[caps nudge] reason quotes the claim and carries the live list with the Mac account",
              "i can't see" in reason and "Mac account `claude@host.docker.internal`" in reason, reason[:400])
        check("[caps nudge] reason says what to do when nothing covers it",
              "Could be switched on" in reason and "genuinely cannot be done here" in reason, reason)
        check("[caps nudge] without SSH pre-authorisation it says to OFFER the command, not to connect",
              "offer it to the user in one line" in reason and "do it now" not in reason, reason)
        shared = Path(tempfile.mkdtemp(dir=td))
        r1 = _nudge(td, home, ws, bindir, denials[0], session="same", tmpdir=shared)
        r2 = _nudge(td, home, ws, bindir, denials[1], session="same", tmpdir=shared)
        check("[caps nudge] own loop guard: a second nudge in the same session within 10 min is suppressed",
              _nudged(r1) and r2.stdout.strip() == "", r2.stdout)
        r3 = _nudge(td, home, ws, bindir, denials[1], session="other", tmpdir=shared)
        check("[caps nudge] ... per session", _nudged(r3), r3.stdout)
        (ws / ".vibe-allow-ssh").write_text("")
        r = _nudge(td, home, ws, bindir, denials[0])
        check("[caps nudge] with .vibe-allow-ssh it says to do it now",
              _nudged(r) and "do it now (SSH is pre-authorised" in json.loads(r.stdout)["reason"], r.stdout[:300])
        (ws / ".vibe-allow-ssh").unlink()
        for msg in fine:
            r = _nudge(td, home, ws, bindir, msg)
            check(f"[caps nudge] left alone: {msg[:48]!r}", r.returncode == 0 and r.stdout.strip() == "", r.stdout)
        r = _nudge(td, home, ws, bindir, denials[0], active=True)
        check("[caps nudge] never twice in one stop chain (stop_hook_active)", r.stdout.strip() == "", r.stdout)
        payload = json.dumps({"stop_hook_active": False, "session_id": "envi", "last_assistant_message": denials[0]})
        r = subprocess.run(["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", f"TMPDIR={td}",
                            "/bin/bash", str(CAPS), "--stop-hook"], input=payload, capture_output=True, text=True, timeout=30)
        check("[caps nudge] runs under env -i (the Codex form) with no HOME", _nudged(r), r.stdout + r.stderr)
        r = subprocess.run(["bash", str(CAPS), "--stop-hook"], input="not json", capture_output=True, text=True, timeout=30)
        check("[caps nudge] garbage input fails open", r.returncode == 0 and r.stdout.strip() == "", r.stdout)
        check("[caps nudge] never runs ssh or scp", not (td / "ssh.called").exists())


def test_capability_nudge_is_wired_into_both_runtimes():
    print("\n[caps nudge] wired as a Stop hook in Claude Code and Codex, in the liveness chain")
    hooks = json.loads((REPO / "devcontainer/codex/hooks/hooks.json").read_text())["hooks"]
    stop_cmds = [h["command"] for g in hooks.get("Stop", []) for h in g.get("hooks", [])]
    check("[caps nudge] Codex Stop runs it in the hardened form",
          "/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/vibe-capabilities --stop-hook" in stop_cmds,
          str(stop_cmds))
    launcher = VIBE.read_text()
    start = launcher.index('cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\'')
    body = launcher[launcher.index("\n", start) + 1:launcher.index("\nEOF\n", start)]
    claude_stop = [h["command"] for g in json.loads(body)["hooks"]["Stop"] for h in g["hooks"]]
    check("[caps nudge] Claude Stop runs it (skipped on an image without it)",
          "[ ! -x /usr/local/bin/vibe-capabilities ] || /usr/local/bin/vibe-capabilities --stop-hook" in claude_stop,
          str(claude_stop))
    liveness = (REPO / "devcontainer/codex-guard-liveness.sh").read_text()
    check("[caps nudge] liveness accepts it only on Stop and checks its ownership",
          "vibe-capabilities:Stop" in liveness and 'check_owned "$bin/vibe-capabilities"' in liveness)
