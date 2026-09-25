"""vibe-shot: one command to see a page, via the Mac account.

No real SSH ever happens here. A stub `ssh` on PATH records its argv and then
runs the remote command LOCALLY with bash (so the Mac-side script is really
executed), with stub `node`/`npm` standing in for Playwright: the stub node
checks it was handed a loadable URL (for an upload: the uploaded file on disk)
and writes known PNG bytes where Playwright would.
"""
from smoke._core import *  # noqa: F401,F403

import json
import os
import subprocess
import tempfile

SHOT = REPO / "devcontainer" / "vibe-shot.sh"
PNG = b"\x89PNG\r\n\x1a\nvibe-shot-test-bytes"


def _shot_fixture(td: Path, ssh_config: str = "Host host.docker.internal\n  User claude\n",
                  playwright: bool = True, node_fails: bool = False, rc_noise: bool = False) -> tuple[dict, Path]:
    home = td / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "config").write_text(ssh_config)
    ws = td / "ws"
    (ws / ".vibe").mkdir(parents=True)
    bindir = td / "bin"
    bindir.mkdir()
    log = td / "ssh.log"
    (bindir / "ssh").write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        "cmd=\"${@: -1}\"\n"
        + ("printf 'motd-without-newline'\n" if rc_noise else "")
        # The Mac's login shell is zsh: run the remote command under it when present.
        + "if command -v zsh >/dev/null 2>&1; then sh=\"zsh -f\"; else sh=/bin/bash; fi\n"
        f"PATH={bindir}:/usr/bin:/bin exec $sh -c \"$cmd\"\n")
    # macOS base64 decodes with -D; GNU refuses it. This wrapper accepts -D so
    # the Mac branch of the remote script is the one exercised.
    (bindir / "base64").write_text("#!/bin/bash\nargs=()\nfor a in \"$@\"; do [ \"$a\" = -D ] && a=-d; args+=(\"$a\"); done\n"
                                   "exec /usr/bin/base64 \"${args[@]}\"\n")
    (bindir / "base64").chmod(0o755)
    (bindir / "npm").write_text(f"#!/bin/sh\necho {td}/npm-root\n")
    png_octal = "".join("\\%03o" % b for b in PNG)
    (bindir / "node").write_text(
        "#!/bin/bash\n"
        f"echo \"$*\" >> {td}/node.log\n"
        "if [ \"${1:-}\" = -e ]; then " + ("exit 0" if playwright else "exit 1") + "; fi\n"
        "if [ \"${1:-}\" = - ]; then cat > /dev/null; url=$2; out=$3\n"
        + ("  echo 'page.goto: net::ERR' >&2; exit 3\n" if node_fails else "")
        + "  case \"$url\" in file://*) p=${url#file://}; [ -f \"$p\" ] || { echo \"missing $p\" >&2; exit 9; }; "
        f"cp \"$p\" {td}/uploaded-page; (cd \"${{p%/site/*}}/site\" && find . | sort) > {td}/uploaded-listing ;; esac\n"
        f"  printf '{png_octal}' > \"$out\"; exit 0; fi\nexit 1\n")
    for f in ("ssh", "npm", "node"):
        (bindir / f).chmod(0o755)
    env = {"PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "VIBE_CAP_WORKSPACE": str(ws),
           "TMPDIR": str(td)}
    return env, ws


def _shot(env: dict, *args, cwd: Path | None = None):
    return subprocess.run(["bash", str(SHOT), *args], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=60, cwd=cwd)


def test_vibe_shot_url_round_trip():
    print("\n[vibe-shot] a URL is rendered on the Mac account and the PNG comes back")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td)
        r = _shot(env, "https://example.org/a?b=1&c=2", "--viewport", "390x844", "--wait-for", "main h1")
        check("[vibe-shot] exits 0", r.returncode == 0, r.stderr)
        out = Path(r.stdout.strip()) if r.stdout.strip() else None
        check("[vibe-shot] prints a PNG path under .vibe/shots", out is not None and out.parent == ws / ".vibe" / "shots"
              and out.name.endswith("-390x844.png"), r.stdout)
        check("[vibe-shot] the PNG bytes survived the round trip", out is not None and out.exists()
              and out.read_bytes() == PNG, "")
        ssh_log = (td / "ssh.log").read_text()
        check("[vibe-shot] exactly one SSH connection, to the declared account", ssh_log.count("claude@host.docker.internal") == 1, ssh_log)
        check("[vibe-shot] BatchMode (never a password prompt)", "BatchMode=yes" in ssh_log, ssh_log)
        check("[vibe-shot] the URL never appears raw in the remote command (base64 only)",
              "example.org" not in ssh_log and "&c=2" not in ssh_log, ssh_log)
        node_log = (td / "node.log").read_text()
        check("[vibe-shot] Playwright got the URL, viewport and selector",
              "https://example.org/a?b=1&c=2" in node_log and " 390 844 0 main h1" in node_log, node_log)
        check("[vibe-shot] the Mac-side temp dir is removed", not list(td.glob("vibe-shot.*")), str(list(td.glob("vibe-shot.*"))))


def test_vibe_shot_uploads_a_folder_or_file():
    print("\n[vibe-shot] a local folder or file is uploaded and rendered from disk on the Mac")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td)
        site = td / "dist"
        (site / "about").mkdir(parents=True)
        (site / "index.html").write_text("<h1>home</h1>")
        (site / "about" / "index.html").write_text("<h1>about</h1>")
        (site / "node_modules").mkdir()
        (site / "node_modules" / "big.js").write_text("x")
        out = td / "chosen.png"
        r = _shot(env, str(site), "--out", str(out))
        check("[vibe-shot] folder: exits 0 and writes --out", r.returncode == 0 and out.read_bytes() == PNG, r.stderr)
        check("[vibe-shot] folder: its index.html is what was rendered",
              (td / "uploaded-page").read_text() == "<h1>home</h1>", "")
        (site / ".env").write_text("SECRET=1")
        (site / ".vibe").mkdir()
        (site / ".vibe" / "key").write_text("k")
        r = _shot(env, str(site), "--out", str(out))
        listing = (td / "uploaded-listing").read_text()
        check("[vibe-shot] folder upload leaves out node_modules, .env* and .vibe",
              r.returncode == 0 and "./index.html" in listing and "node_modules" not in listing
              and ".env" not in listing and ".vibe" not in listing, listing)
        r = _shot(env, str(site), "--path", "about/index.html", "--out", str(out))
        check("[vibe-shot] folder + --path renders that page",
              r.returncode == 0 and (td / "uploaded-page").read_text() == "<h1>about</h1>", r.stderr)
        r = _shot(env, str(site / "about" / "index.html"), "--out", str(out))
        check("[vibe-shot] a single file renders", r.returncode == 0 and (td / "uploaded-page").read_text() == "<h1>about</h1>", r.stderr)
        big = td / "big"
        big.mkdir()
        (big / "index.html").write_text("x" * 300000)
        env_small = {**env, "VIBE_SHOT_MAX_KB": "100"}
        r = _shot(env_small, str(big))
        check("[vibe-shot] an upload over the limit is refused before SSH, measured on the real tar",
              r.returncode == 2 and "limit 100 KB" in r.stderr, r.stderr)
        r = _shot(env, str(site), "--full-page", "--out", str(out))
        check("[vibe-shot] --full-page reaches Playwright", r.returncode == 0 and " 1 " in (td / "node.log").read_text().splitlines()[-1], r.stderr)
        r = _shot(env, str(site), "--path", "../etc/passwd")
        check("[vibe-shot] --path cannot leave the folder", r.returncode == 2, r.stderr)
        r = _shot(env, str(site), "--path", "missing.html")
        check("[vibe-shot] a missing page is refused before any SSH", r.returncode == 2 and "has no missing.html" in r.stderr, r.stderr)


def test_vibe_shot_refusals_and_check():
    print("\n[vibe-shot] refusals, the readiness check and Mac-side failures")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td, ssh_config="Host github.com\n  User git\n")
        r = _shot(env, "https://example.org")
        check("[vibe-shot] no Mac account: refused with the setup pointer",
              r.returncode == 1 and "vibe-capabilities --setup mac-account" in r.stderr, r.stderr)
        check("[vibe-shot] ... and no SSH attempted", not (td / "ssh.log").exists())
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td)
        for args, label in ((["https://x", "--viewport", "wide"], "bad viewport"),
                            (["https://x", "--viewport", "50x50"], "tiny viewport"),
                            (["/no/such/file.html"], "missing file"),
                            ([], "no target"),
                            (["https://x", "--bogus"], "unknown option"),
                            (["https://x", "--out"], "an option missing its value")):
            r = _shot(env, *args)
            check(f"[vibe-shot] {label}: usage error before any SSH", r.returncode == 2 and not (td / "ssh.log").exists(), r.stderr)
        r = _shot(env, "--check")
        check("[vibe-shot] --check reports the Mac side ready", r.returncode == 0 and "is ready" in r.stdout, r.stdout + r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td, playwright=False)
        r = _shot(env, "--check")
        check("[vibe-shot] --check without Playwright names the install command",
              r.returncode != 0 and "npm i -g playwright" in r.stderr, r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td, rc_noise=True)
        r = _shot(env, "https://example.org", "--out", str(td / "n.png"))
        check("[vibe-shot] login-shell noise before the markers does not lose the image",
              r.returncode == 0 and (td / "n.png").read_bytes() == PNG, r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td, node_fails=True)
        r = _shot(env, "https://example.org")
        check("[vibe-shot] a page that fails to load: nonzero, message passed through, no stray PNG",
              r.returncode != 0 and "ERR" in r.stderr and not list((ws / ".vibe" / "shots").glob("*.png")), r.stderr)
        check("[vibe-shot] temp dirs are removed on failure too",
              not list(td.glob("vibe-shot.*")) and not list(td.glob("vibe-shot-local.*")), str(list(td.iterdir())))


def test_vibe_shot_playwright_script_parses():
    print("\n[vibe-shot] the Playwright script it sends is valid JavaScript")
    src = SHOT.read_text()
    start = src.index("<<'\"'\"'JS'\"'\"'")
    body = src[src.index("\n", start) + 1:src.index("\nJS\n", start)]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(body)
        js = f.name
    try:
        r = subprocess.run(["node", "--check", js], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        check("[vibe-shot] node --check accepts the Playwright script", r.returncode == 0, r.stderr)
        check("[vibe-shot] it waits for load, not network idle alone", 'waitUntil: "load"' in body, body[:200])
    finally:
        os.unlink(js)


def test_vibe_shot_is_named_wherever_seeing_comes_up():
    print("\n[vibe-shot] installed, and named by the inventory, the nudge and the fragment")
    dockerfile = (REPO / "devcontainer/Dockerfile").read_text()
    check("[vibe-shot] Dockerfile installs it", "COPY --chown=root:root vibe-shot.sh /usr/local/bin/vibe-shot" in dockerfile
          and "/usr/local/bin/vibe-shot " in dockerfile)
    caps = (REPO / "devcontainer/vibe-capabilities.sh").read_text()
    check("[vibe-shot] vibe-capabilities names it", caps.count("vibe-shot") >= 3, "")
    frag = (REPO / "devcontainer/claude-md/capabilities.md").read_text()
    check("[vibe-shot] the CLAUDE.md fragment names it", "vibe-shot" in frag, frag)


def _native_stubs(td: Path, booted: bool = True, console_is_me: bool = True, xcode: bool = True):
    bindir = td / "bin"
    png_octal = "".join("\\%03o" % b for b in PNG)
    me = subprocess.run(["id", "-un"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
    stubs = {
        "sleep": "#!/bin/sh\nexit 0\n",
        "open": f"#!/bin/sh\necho \"open $*\" >> {td}/native.log\n",
        "stat": f"#!/bin/sh\n[ \"$1 $2 $3\" = '-f %Su /dev/console' ] && echo {me if console_is_me else 'someone-else'}\n",
        "screencapture": f"#!/bin/bash\necho \"screencapture $*\" >> {td}/native.log\nprintf '{png_octal}' > \"${{@: -1}}\"\n",
    }
    if xcode:
        stubs["xcrun"] = (
            "#!/bin/bash\n"
            f"echo \"xcrun $*\" >> {td}/native.log\n"
            "case \"$*\" in\n"
            "  'simctl help') exit 0 ;;\n"
            "  'simctl list devices booted') " + ("echo '    iPhone 16 (AAAA-1111) (Booted)'" if booted else "true") + " ;;\n"
            "  'simctl list devices available') echo '    iPhone 16 (AAAA-1111) (Shutdown)' ;;\n"
            f"  simctl\\ io\\ booted\\ screenshot\\ *) printf '{png_octal}' > \"${{@: -1}}\" ;;\n"
            "esac\nexit 0\n")
    for name, body in stubs.items():
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)


def test_vibe_shot_native_simulator_and_screen():
    print("\n[vibe-shot] --sim and --screen capture native apps on the Mac account")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td)
        _native_stubs(td, booted=False)
        r = _shot(env, "--sim", "--open", "com.example.app")
        out = Path(r.stdout.strip()) if r.stdout.strip() else None
        check("[vibe-shot] --sim returns the simulator PNG", r.returncode == 0 and out is not None
              and out.name.endswith("-sim.png") and out.read_bytes() == PNG, r.stderr)
        log = (td / "native.log").read_text()
        check("[vibe-shot] --sim boots an iPhone when none is running, launches the app, then captures",
              log.index("simctl boot AAAA-1111") < log.index("simctl launch booted com.example.app")
              < log.index("simctl io booted screenshot"), log)
        r = _shot(env, "--screen", "--app", "Calculator")
        log = (td / "native.log").read_text()
        check("[vibe-shot] --screen opens the app and captures silently",
              r.returncode == 0 and "open -a Calculator" in log and "screencapture -x" in log, r.stderr + log)
        r = _shot(env, "--check")
        check("[vibe-shot] --check reports each mode", "web pages: ready" in r.stderr
              and "iOS Simulator: ready" in r.stderr and "screen: ready" in r.stderr, r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td, playwright=False)
        _native_stubs(td, console_is_me=False, xcode=False)
        r = _shot(env, "--screen")
        check("[vibe-shot] --screen when the account is not on the display: refused with the fix",
              r.returncode != 0 and "log in as" in r.stderr and "Screen Recording" in r.stderr, r.stderr)
        r = _shot(env, "--sim")
        check("[vibe-shot] --sim without Xcode: refused with the fix", r.returncode != 0 and "install Xcode" in r.stderr, r.stderr)
        r = _shot(env, "--check")
        check("[vibe-shot] --check with nothing ready exits non-zero and lists all three fixes",
              r.returncode != 0 and r.stderr.count("not ready") == 3, r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        env, ws = _shot_fixture(td)
        for args, label in ((["--sim", "https://x"], "--sim with a URL"),
                            (["--sim", "--open", "com.bad app"], "--open with a space"),
                            (["--screen", "--app", "Calc;rm"], "--app with a shell character"),
                            (["https://x", "--open", "com.x"], "--open without --sim")):
            r = _shot(env, *args)
            check(f"[vibe-shot] {label}: usage error before any SSH", r.returncode == 2 and not (td / "ssh.log").exists(), r.stderr)
