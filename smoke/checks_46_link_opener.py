"""Link opener (2026-10-26): clicking a link in Claude Code's fullscreen TUI
inside vibe opened nothing, because the TUI captures the click and opens the
link itself via $BROWSER / xdg-open, neither of which reaches a browser in
the container. vibe-open (the container's $BROWSER) queues the link under
.vibe/open-requests/ and the host-side vibe-open-watcher.sh opens it.

The request files are container-written, so the host side must refuse
anything that is not a plain http(s) link and must cap a burst.
"""
from smoke._core import *

VIBE_OPEN = REPO / "devcontainer" / "vibe-open.sh"
OPEN_WATCHER = REPO / "vibe-open-watcher.sh"


def test_link_opener_container_side():
    print("\n[link-opener] vibe-open queues only plain http(s) links")
    with tempfile.TemporaryDirectory() as td:
        q = Path(td) / "ws" / ".vibe" / "open-requests"
        env = {**os.environ, "VIBE_OPEN_QUEUE_DIR": str(q)}
        r = run(["bash", str(VIBE_OPEN), "https://vibe.andeye.com/?a=1&b=(2)"], env=env)
        files = sorted(q.glob("*.url")) if q.exists() else []
        check("[link-opener] an https link is queued as one .url file holding exactly that link",
              r.returncode == 0 and len(files) == 1 and files[0].read_text() == "https://vibe.andeye.com/?a=1&b=(2)\n",
              r.stderr)
        for bad in ["file:///etc/passwd", "https://a.example/x y", "x-apple.systempreferences:x",
                    "javascript:alert(1)", "https://a.example/\x1b]52;c;x\x07", "https://a.example/" + "a" * 2100]:
            r = run(["bash", str(VIBE_OPEN), bad], env=env)
            check(f"[link-opener] refused with exit 2: {bad[:40]!r}", r.returncode == 2, r.stderr)
        check("[link-opener] refused links queue nothing", len(list(q.glob("*.url"))) == 1)
        r = run(["bash", str(VIBE_OPEN)], env=env)
        check("[link-opener] no argument is a usage error", r.returncode == 2, r.stderr)


def test_link_opener_host_watcher():
    print("\n[link-opener] host watcher re-validates, skips symlinks, caps a burst")
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        q = t / "ws" / ".vibe" / "open-requests"
        q.mkdir(parents=True)
        rec = t / "rec.sh"
        opened = t / "opened"
        rec.write_text(f'#!/bin/sh\necho "$1" >> "{opened}"\n')
        rec.chmod(0o755)
        (q / "a-evil.url").write_text("file:///etc/passwd\n")
        (q / "b-scheme.url").write_text("x-apple.systempreferences:com.apple.x\n")
        (q / "c-link.url").symlink_to("/etc/hostname")
        for i in range(5):
            (q / f"d{i}.url").write_text(f"https://example.com/{i}\n")
        env = {**os.environ, "VIBE_OPEN_CMD": str(rec), "VIBE_OPEN_WATCHER_ONCE": "1"}
        r = run(["bash", str(OPEN_WATCHER), str(t / "ws")], env=env)
        got = opened.read_text().splitlines() if opened.exists() else []
        check("[link-opener] watcher opens only http(s) links, at most three per tick",
              r.returncode == 0 and got == ["https://example.com/0", "https://example.com/1", "https://example.com/2"],
              r.stderr + str(got))
        check("[link-opener] every request, refused or over the cap, is consumed",
              list(q.iterdir()) == [], str(list(q.iterdir())))


def test_link_opener_wiring():
    print("\n[link-opener] image, env and launcher wiring")
    dj = json.loads((REPO / "devcontainer" / "devcontainer.json").read_text())
    check("[link-opener] container BROWSER is vibe-open",
          dj.get("containerEnv", {}).get("BROWSER") == "/usr/local/bin/vibe-open")
    df = DOCKERFILE.read_text()
    check("[link-opener] Dockerfile installs vibe-open and makes it executable",
          "COPY vibe-open.sh /usr/local/bin/vibe-open" in df and "/usr/local/bin/vibe-open " in df)
    v = VIBE.read_text()
    check("[link-opener] launcher starts the host watcher and reaps it on exit",
          '"$VIBE_REPO_DIR/vibe-open-watcher.sh" "$WORKSPACE" &' in v
          and "vibe_exit_hook_add 'kill \"$OPEN_WATCHER_PID\"" in v)
    check("[link-opener] watcher script is executable", os.access(OPEN_WATCHER, os.X_OK))
