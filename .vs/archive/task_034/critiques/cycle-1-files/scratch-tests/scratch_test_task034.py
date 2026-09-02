#!/usr/bin/env python3
"""Generator scratch proof for task_034 (Linux host support).

Run with --head to exercise the PRE-CHANGE sources (expect RED), or with no
argument to exercise the working tree (expect GREEN).

Not the deliverable test suite -- the Tester writes the spec's smoke tests.
"""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / ".vs/cycle-1/fixtures"
SHIM_DARWIN = ROOT / ".vs/cycle-1/scratch-tests/shimbin-darwin"

FAILS, PASSES = [], []
def check(name, cond, detail=""):
    (PASSES if cond else FAILS).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if not cond and detail else ""))

def materialise(use_head):
    """Return a dir holding the sources under test."""
    d = Path(tempfile.mkdtemp())
    for rel in ("vibe", "vibe-copy-watcher.sh", "install.sh",
                "devcontainer/devcontainer.json", "devcontainer/Dockerfile"):
        dst = d / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if use_head:
            dst.write_bytes(subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"],
                                           capture_output=True, check=True).stdout)
        else:
            shutil.copy(ROOT / rel, dst)
        dst.chmod(0o755)
    return d

def mkshim(d, name, body):
    p = d / name
    p.write_text(body); p.chmod(0o755)
    return p

# ── 0. shim infrastructure proof (spec amendment: prove before relying) ───────
def t_shim(_src):
    print("\n[0] uname PATH shim shadows the real uname")
    real = subprocess.run(["uname", "-s"], capture_output=True, text=True).stdout.strip()
    env = {**os.environ, "PATH": f"{SHIM_DARWIN}:{os.environ['PATH']}"}
    shimmed = subprocess.run(["uname", "-s"], capture_output=True, text=True, env=env).stdout.strip()
    which = subprocess.run(["bash", "-c", "command -v uname"], capture_output=True, text=True, env=env).stdout.strip()
    check("real uname is Linux here", real == "Linux", real)
    check("shimmed uname -s prints Darwin", shimmed == "Darwin", shimmed)
    check("command -v uname resolves to the shim", which == str(SHIM_DARWIN / "uname"), which)

# ── AC3/AC4. rendered override ────────────────────────────────────────────────
def render(src, op_host):
    out = Path(tempfile.mkdtemp()) / "override.json"
    subprocess.run(
        ["bash", "-c",
         'set -euo pipefail; . "$1" >/dev/null 2>&1 || true; '
         'render_devcontainer_with_mounts "$2" "$3" '
         '/fixture/host/projects /home/node/.claude/projects 0 '
         '/fixture/host/brain2 /brain2 0 '
         '/fixture/host/zotero /zotero 1',
         "_", str(src / "vibe"), str(src / "devcontainer/devcontainer.json"), str(out)],
        env={**os.environ, "PATH": f"{SHIM_DARWIN}:{os.environ['PATH']}",
             "VIBE_SOURCE_ONLY": "1", "VIBE_OP_ADDHOST": op_host},
        check=True, capture_output=True)
    return out.read_text()

ADDHOST = "--add-host=host.docker.internal:host-gateway"

def t_override(src):
    print("\n[AC3] exactly one host.docker.internal:host-gateway, /op off and on")
    for label, op in (("op off", ""), ("op on", "op.example.invalid")):
        txt = render(src, op)
        cfg = json.loads(txt)
        n = cfg["runArgs"].count(ADDHOST)
        check(f"[AC3/{label}] exactly one {ADDHOST}", n == 1, f"count={n} runArgs={cfg['runArgs']}")
    print("\n[AC4] Darwin path = LITERAL pre-change golden + that one line, nothing else")
    # The golden is the pre-change launcher's own output bytes, captured before
    # any edit in this task (see capture_golden.sh) -- NOT derived from the
    # post-change sources, so it cannot be tautological. The ONLY permitted
    # transform is appending the one add-host to runArgs: we apply exactly that
    # to the golden, re-serialise the way the launcher's Python does
    # (json.dump indent=2 + trailing newline), and demand byte equality.
    for label, op, gold in (("op off", "", "golden-override-op-off.json"),
                            ("op on", "op.example.invalid", "golden-override-op-on.json")):
        got = render(src, op)
        golden_text = (FIX / gold).read_text()
        cfg = json.loads(golden_text)
        # Sanity: the golden itself must NOT already carry the flag.
        check(f"[AC4/{label}] golden predates the change (no add-host in it)",
              ADDHOST not in golden_text, "golden is contaminated")
        args = cfg["runArgs"]
        # Base runArgs come first, then /op's injection -- insert ours after the
        # cap-adds, i.e. at the position the base devcontainer.json declares it.
        base_len = len([a for a in args if a.startswith("--cap-add=")])
        cfg["runArgs"] = args[:base_len] + [ADDHOST] + args[base_len:]
        expected = json.dumps(cfg, indent=2) + "\n"
        check(f"[AC4/{label}] rendered == golden + exactly the one add-host line, byte for byte",
              got == expected,
              "".join(__import__("difflib").unified_diff(
                  expected.splitlines(1), got.splitlines(1), "golden+addhost", "got")))

# ── AC6. vibe_clipboard_cmd precedence ────────────────────────────────────────
def clipboard_cmd(src, os_name, tools):
    d = Path(tempfile.mkdtemp())
    mkshim(d, "uname", f'#!/bin/sh\necho {os_name}\n')
    for t in tools:
        mkshim(d, t, "#!/bin/sh\nexit 0\n")
    r = subprocess.run(
        ["bash", "-c", 'set -euo pipefail; . "$1" >/dev/null 2>&1 || true; vibe_clipboard_cmd',
         "_", str(src / "vibe")],
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(d), "VIBE_SOURCE_ONLY": "1"},
        capture_output=True, text=True)
    return r.stdout, r.returncode

def t_clipboard(src):
    print("\n[AC6] vibe_clipboard_cmd precedence")
    cases = [
        ("Darwin + pbcopy",            "Darwin", ["pbcopy"],                       "pbcopy"),
        ("Darwin, no pbcopy",          "Darwin", [],                               ""),
        ("Linux, all three",           "Linux",  ["wl-copy", "xclip", "xsel"],     "wl-copy"),
        ("Linux, xclip+xsel",          "Linux",  ["xclip", "xsel"],                "xclip -selection clipboard"),
        ("Linux, xsel only",           "Linux",  ["xsel"],                         "xsel --clipboard --input"),
        ("Linux, headless",            "Linux",  [],                               ""),
        ("Linux ignores pbcopy",       "Linux",  ["pbcopy"],                       ""),
    ]
    for label, osn, tools, want in cases:
        got, rc = clipboard_cmd(src, osn, tools)
        check(f"[AC6] {label} -> {want!r}", got == want and rc == 0, f"got={got!r} rc={rc}")

# ── AC7. watcher gate ─────────────────────────────────────────────────────────
def t_watcher(src):
    print("\n[AC7] watcher 3-way gate (Darwin OR VIBE_COPY_CMD OR FORCE)")
    w = src / "vibe-copy-watcher.sh"
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td); (ws / ".vibe").mkdir()
        base = {k: v for k, v in os.environ.items()
                if k not in ("VIBE_COPY_CMD", "VIBE_COPY_WATCHER_FORCE")}
        r = subprocess.run(["bash", str(w), str(ws)], env=base, capture_output=True, timeout=20)
        check("[AC7] Linux, no clipboard tool -> exits 0 immediately", r.returncode == 0, str(r.returncode))
        # With VIBE_COPY_CMD set it must RUN (i.e. not exit immediately).
        sent = ws / "sentinel"
        shim = ws / "cp.sh"
        shim.write_text(f"#!/usr/bin/env bash\ncat > {sent}\n"); shim.chmod(0o755)
        p = subprocess.Popen(["bash", str(w), str(ws)],
                             env={**base, "VIBE_COPY_CMD": str(shim)},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        import time
        time.sleep(0.8)
        alive = p.poll() is None
        (ws / ".vibe/copy-latest.txt").write_text("task034-payload\n")
        time.sleep(1.5)
        p.terminate(); p.wait(timeout=10)
        check("[AC7] VIBE_COPY_CMD set -> watcher stays running on Linux", alive, "exited immediately")
        check("[AC7] VIBE_COPY_CMD invoked with the scratch content",
              sent.exists() and "task034-payload" in sent.read_text(),
              sent.read_text() if sent.exists() else "sentinel absent")
        # FORCE alone still works (existing test_vibe_path_prefix_isolation).
        p2 = subprocess.Popen(["bash", str(w), str(ws)],
                              env={**base, "VIBE_COPY_WATCHER_FORCE": "1"},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.8)
        alive2 = p2.poll() is None
        p2.terminate(); p2.wait(timeout=10)
        check("[AC7] FORCE alone still starts the watcher", alive2, "exited immediately")

# ── AC5. byte-pinned Darwin exit hook ─────────────────────────────────────────
def t_pins(src):
    print("\n[AC5] Darwin exit-hook literals unchanged")
    s = (src / "vibe").read_text()
    check('[AC5] pbcopy < "$CLIP" present', 'pbcopy < "$CLIP"' in s)
    check("[AC5] exactly one CLIP=... line",
          len(re.findall(r'^\s*CLIP="\$WORKSPACE/\.vibe/copy-latest\.txt"\s*$', s, re.M)) == 1)
    check("[AC5] exactly one WATCHER_SEED_MTIME=$(stat -f %m line",
          len(re.findall(r'^\s*WATCHER_SEED_MTIME=\$\(stat -f %m "\$CLIP"', s, re.M)) == 1)

# ── AC8/AC9. installer ────────────────────────────────────────────────────────
def installer(src, osname, pkg=""):
    r = subprocess.run([str(ROOT / ".vs/cycle-1/scratch-tests/run_installer_hints.sh"),
                        str(src / "install.sh"), osname, pkg],
                       capture_output=True, text=True, timeout=60)
    return r.stdout

def t_installer(src):
    print("\n[AC8] Darwin installer output byte-identical to pre-change golden")
    got = installer(src, "Darwin")
    want = (FIX / "golden-install-darwin.txt").read_text()
    check("[AC8] Darwin output byte-identical", got == want,
          "".join(__import__("difflib").unified_diff(want.splitlines(1), got.splitlines(1), "golden", "got")))
    print("\n[AC9] Linux preflight names apt/dnf, docker group, devcontainer; exits on missing deps")
    apt = installer(src, "Linux", "apt")
    dnf = installer(src, "Linux", "dnf")
    check("[AC9/apt] names apt-get", "apt-get install" in apt, apt)
    check("[AC9/apt] points at docker-ce Engine docs", "docs.docker.com/engine/install" in apt, apt)
    check("[AC9/dnf] names dnf install", "dnf install" in dnf, dnf)
    check("[AC9] no brew/xcode-select in Linux output",
          "brew " not in apt and "xcode-select" not in apt, apt)
    check("[AC9] devcontainer hint present", "npm install -g @devcontainers/cli" in apt, apt)
    check("[AC9] bash -n clean",
          subprocess.run(["bash", "-n", str(src / "install.sh")]).returncode == 0)
    # Group check warns rather than exits: exercise it with deps present.
    d = Path(tempfile.mkdtemp())
    for t in ("git", "docker", "node", "devcontainer", "gh"):
        mkshim(d, t, "#!/bin/sh\nexit 0\n")          # docker info -> 0
    mkshim(d, "uname", "#!/bin/sh\necho Linux\n")
    mkshim(d, "id", "#!/bin/sh\n[ \"${1:-}\" = -nG ] && { echo 'users wheel'; exit 0; }\necho tester\n")
    for real in ("grep", "mkdir", "ln", "rm", "cat", "sed", "dirname", "basename", "pwd", "cd", "tr", "head"):
        w = shutil.which(real)
        if w: (d / real).symlink_to(w)
    home = d / "home"; (home / ".vibe").mkdir(parents=True)
    (home / ".vibe/config").write_text('VIBE_PROJECTS_DIR="/tmp/p"\n')
    r = subprocess.run(["/bin/bash", str(src / "install.sh")],
                       env={"PATH": str(d), "HOME": str(home), "VIBE_OS": "Linux", "VIBE_PKG": "apt"},
                       capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    check("[AC9] docker-group failure WARNS and exits 0", r.returncode == 0, f"rc={r.returncode} {out}")
    check("[AC9] warning names usermod -aG docker", "usermod -aG docker" in out, out)

# ── AC10. Dockerfile nsswitch idempotent ──────────────────────────────────────
def t_nsswitch(src):
    print("\n[AC10] nsswitch sed is idempotent")
    df = (src / "devcontainer/Dockerfile").read_text()
    m = re.search(r"^RUN (sed -i .*nsswitch\.conf)$", df, re.M)
    check("[AC10] nsswitch RUN line found", m is not None)
    if not m:
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "nsswitch.conf"
        f.write_text("hosts:          files dns\n")
        cmd = m.group(1).replace("/etc/nsswitch.conf", str(f))
        for _ in range(2):
            subprocess.run(["bash", "-c", cmd], check=True)
        n = f.read_text().count("mdns4_minimal")
        check("[AC10] twice-applied => exactly one mdns4_minimal", n == 1, f"count={n}: {f.read_text()!r}")
        check("[AC10] mdns4_minimal precedes dns",
              re.search(r"mdns4_minimal \[NOTFOUND=return\] dns", f.read_text()) is not None, f.read_text())

# ── AC11 / (f). docs ──────────────────────────────────────────────────────────
def t_docs(_src):
    print("\n[AC11] README + ONBOARDING Linux sections; MANUAL-TESTS 44-50")
    readme = (ROOT / "README.md").read_text()
    check("[AC11] README has a Linux section", "## Linux" in readme or "### Linux" in readme)
    check("[AC11] README names Ubuntu 24.04 LTS + Docker Engine",
          "Ubuntu 24.04" in readme and "Docker Engine" in readme)
    check("[AC11] README no longer says 'Linux untested'", "Linux untested" not in readme)
    check("[AC11] build bridge marked macOS-only",
          re.search(r"build bridge.{0,120}macOS.only|macOS.only.{0,120}build bridge", readme, re.I | re.S) is not None)
    check("[AC10/docs] README says a cache-busted --rebuild is needed",
          "--rebuild" in readme and "nsswitch" in readme)
    onb = (ROOT / "ONBOARDING.md").read_text()
    check("[AC11] ONBOARDING has a Linux fork", "apt-get" in onb or "apt install" in onb)
    mt = (ROOT / "MANUAL-TESTS.md").read_text()
    for n in range(44, 51):
        check(f"[f] MANUAL-TESTS Test {n} exists", re.search(rf"^#+ .*Test {n}\b", mt, re.M) is not None)
    check("[f] Linux host section header", re.search(r"^#+ Linux host \(Ubuntu 24\.04 LTS\)", mt, re.M) is not None)
    check("[AC10] MANUAL-TESTS checks one mdns4_minimal after rebuild", "mdns4_minimal" in mt)

def main():
    use_head = "--head" in sys.argv
    src = materialise(use_head)
    print(f"=== task_034 scratch proof :: sources = {'HEAD (pre-change, expect RED)' if use_head else 'working tree (expect GREEN)'} ===")
    for t in (t_shim, t_override, t_clipboard, t_watcher, t_pins, t_installer, t_nsswitch, t_docs):
        try:
            t(src)
        except Exception as e:
            check(f"{t.__name__} raised", False, f"{type(e).__name__}: {e}")
    print(f"\n=== {len(PASSES)} passed, {len(FAILS)} failed ===")
    for f in FAILS:
        print(f"  FAILED: {f}")
    return 1 if FAILS else 0

sys.exit(main())
