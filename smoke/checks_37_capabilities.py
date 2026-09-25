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
        check("[caps] ... says how to see: screenshot, scp back, Read tool displays images",
              "screenshot" in avail and "scp" in avail and "Read tool displays images" in avail, avail)
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
