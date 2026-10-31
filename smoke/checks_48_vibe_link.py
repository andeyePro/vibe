"""`vibe link` (task_062): registry, strict vibe:// URL handling, per-click
confirmation, rate limit and terminal launchers, exercised black-box through
the launcher with a temp HOME and PATH shims (uname, osascript, open, kitty,
wezterm, ghostty, gnome-terminal, zenity, docker) that record their argv.

Control convention: every refusal test is paired with a positive control (a
valid open that DOES call the recorder), and says in a comment what the test
would report if the mechanism under test were absent.
"""
import re
import shutil
import stat
import subprocess
import time

from smoke._core import *

_VL = "[vibe-link]"
_SENTINEL_UUID = "123e4567-e89b-12d3-a456-426614174000"
_AMBIENT_DROP = ("VIBE_CONFIG", "VIBE_TERMINAL", "VIBE_LINK_ASSUME",
                 "VIBE_LINK_DRY_RUN", "VIBE_TASKANDI_URL")


class _Fx:
    """One temp world: HOME, PATH shim dir, call log, work dir, projects."""

    def __init__(self, os_name: str = "Darwin"):
        self._td = tempfile.TemporaryDirectory(prefix="vibe-link.")
        self.root = Path(self._td.name).resolve()
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.work = self.root / "work"
        self.proj = self.root / "projects"
        for d in (self.home, self.bin, self.work, self.proj):
            d.mkdir()
        self.log = self.root / "calls.log"
        self.log.write_text("")
        self.vibe_path = str(VIBE.resolve())
        self.set_os(os_name)
        self.rec("docker")
        self.rec("osascript")
        self.rec("open")

    # -- shims ---------------------------------------------------------------
    def set_os(self, os_name: str) -> None:
        p = self.bin / "uname"
        p.write_text(f"#!/bin/sh\nprintf '%s\\n' '{os_name}'\n")
        p.chmod(0o755)
        self.os_name = os_name

    def rec(self, name: str, rc: int = 0, out: str = "") -> None:
        (self.bin / f".{name}.out").write_text(out)
        p = self.bin / name
        p.write_text(
            "#!/bin/sh\n"
            f"{{ printf '@@ %s\\n' '{name}'; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> '{self.log}'\n"
            f"cat '{self.bin}/.{name}.out'\n"
            f"exit {rc}\n")
        p.chmod(0o755)

    def unrec(self, name: str) -> None:
        (self.bin / name).unlink(missing_ok=True)

    def calls(self, name: str | None = None) -> list:
        res = []
        for line in self.log.read_text().split("\n"):
            if line.startswith("@@ "):
                res.append([line[3:], []])
            elif res and line != "":
                res[-1][1].append(line)
        return [c for c in res if name is None or c[0] == name]

    # -- running -------------------------------------------------------------
    def env(self, **extra) -> dict:
        base = {k: v for k, v in os.environ.items() if k not in _AMBIENT_DROP}
        base["HOME"] = str(self.home)
        base["PATH"] = f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}"
        base.pop("VIBE_CONFIG", None)
        env = _isolate_extras_env(base)
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        return env

    def vibe(self, *args, cwd: Path | None = None, **extra):
        return run(["bash", str(VIBE), *args], env=self.env(**extra), cwd=cwd or self.work)

    def open(self, url: str, **extra):
        return self.vibe("link", "open", url, **extra)

    # -- project / registry helpers -----------------------------------------
    def repo(self, name: str) -> Path:
        p = self.proj / name
        p.mkdir(parents=True)
        run(["git", "init", "-q", str(p)], env=self.env())
        return p.resolve()

    def allow(self, repo: Path, *names, **extra):
        return self.vibe("link", "allow", *names, cwd=repo, **extra)

    @property
    def reg(self) -> Path:
        return self.home / ".vibe" / "link-projects"

    @property
    def stamps(self) -> Path:
        return self.home / ".vibe" / "link-last"

    def write_reg(self, text: str, mode: int = 0o600) -> None:
        self.reg.parent.mkdir(parents=True, exist_ok=True)
        self.reg.write_text(text)
        self.reg.chmod(mode)

    def write_cfg(self, text: str) -> None:
        (self.home / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.home / ".vibe" / "config").write_text(text)

    def pwned(self) -> list:
        return [os.path.join(d, f) for d, ds, fs in os.walk(self.root) for f in fs + ds if f == "PWNED"]

    def close(self, label: str) -> None:
        # Spec AC12: no `vibe link` command ever starts Docker. If a link path
        # fell through into the normal launcher, the docker recorder is hit.
        check(f"{_VL} docker never invoked ({label})", self.calls("docker") == [],
              str(self.calls("docker")))
        self._td.cleanup()


def _blocks(out: str) -> list:
    res = []
    for line in out.split("\n"):
        if line.startswith("DRYRUN "):
            res.append([line[7:], []])
        elif line.startswith("  argv: ") and res:
            res[-1][1].append(line[8:])
    return res


def _launch(out: str):
    b = [x for x in _blocks(out) if x[0] == "launch"]
    return b[0][1] if len(b) == 1 else None


_WRAP_SH = 'cd -P -- "$1" && [ "$(pwd -P)" = "$1" ] && shift && exec "$@"'


def _wrap(path, vibe, task=None) -> list:
    """AC15: the constant wrapper argv every launch runs."""
    return ["/bin/sh", "-c", _WRAP_SH, "vibe-link", str(path), vibe] + (["--task", task] if task else [])


def _as_inner_re(path, vibe, task=None) -> str:
    """Regex for the wrapper command line inside an AppleScript string literal:
    single-quoted words, inner double quotes written as backslash-quote."""
    wrap_as = _WRAP_SH.replace('"', '\\"')
    r = (r"'?/bin/sh'? -c '" + re.escape(wrap_as) + r"' '?vibe-link'? '" + re.escape(str(path))
         + r"' '" + re.escape(vibe) + r"'")
    if task:
        r += r" '?--task'? '" + re.escape(task) + r"'"
    return r


class _Argv(list):
    """Expected argv. Plain elements compare exactly; a compiled regex element
    fullmatches; `pred`, if set, replaces the comparison entirely."""

    def __init__(self, items, pred=None):
        super().__init__(items)
        self.pred = pred

    def __eq__(self, other):
        if not isinstance(other, list):
            return False
        if self.pred is not None:
            return bool(self.pred(list(other)))
        if len(self) != len(other):
            return False
        for e, o in zip(self, other):
            if hasattr(e, "fullmatch"):
                if not e.fullmatch(o):
                    return False
            elif e != o:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None


def _exp(os_name: str, term: str, path, vibe, task=None) -> list:
    w = _wrap(path, vibe, task)
    if os_name == "Darwin":
        if term == "Terminal":
            return _Argv(["osascript", "-e",
                          re.compile(re.escape('tell application "Terminal" to do script "')
                                     + _as_inner_re(path, vibe, task) + '"'),
                          "-e", 'tell application "Terminal" to activate'])
        if term == "iTerm":
            wt = re.compile(re.escape('tell current session of current window to write text "')
                            + _as_inner_re(path, vibe, task) + '"')

            def pred(o):
                return (len(o) >= 5 and o[0] == "osascript" and len(o) % 2 == 1
                        and all(x == "-e" for x in o[1::2])
                        and 'tell application "iTerm"' in o[2::2]
                        and "create window with default profile" in o[2::2]
                        and any(wt.fullmatch(x) for x in o[2::2])
                        and not any("command" in x.split("profile")[-1] for x in o[2::2]
                                    if x.startswith("create window")))
            return _Argv(["osascript"], pred)
        if term == "Ghostty":
            return ["open", "-na", "Ghostty", "--args", "-e"] + w
        if term == "kitty":
            return ["open", "-na", "kitty", "--args"] + w
        if term == "WezTerm":
            return ["open", "-na", "WezTerm", "--args", "start", "--"] + w
    else:
        if term == "Ghostty":
            return ["ghostty", "-e"] + w
        if term == "kitty":
            return ["kitty"] + w
        if term == "WezTerm":
            return ["wezterm", "start", "--"] + w
        if term == "gnome-terminal":
            return ["gnome-terminal", "--"] + w
    raise AssertionError((os_name, term))


def _dry(**extra):
    return dict(VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="open", **extra)


def _setup_demo(fx: _Fx):
    r = fx.repo("demo")
    res = fx.allow(r)
    assert res.returncode == 0, res.stderr
    return r


# ── AC1 ──────────────────────────────────────────────────────────────────────
def test_vl_ac1_allow_list_deny():
    print(f"\n{_VL} AC1 allow / list / deny round trip")
    fx = _Fx()
    try:
        r = fx.repo("demo")
        res = fx.allow(r)
        check(f"{_VL} allow exits 0 and prints 'allowed: demo -> <pwd -P>'",
              res.returncode == 0 and f"allowed: demo -> {r}" in res.stdout + res.stderr,
              res.stdout + res.stderr)
        check(f"{_VL} registry holds exactly demo=<path>",
              fx.reg.read_text() == f"demo={r}\n", repr(fx.reg.read_text() if fx.reg.exists() else None))
        check(f"{_VL} registry is mode 600",
              fx.reg.exists() and stat.S_IMODE(fx.reg.stat().st_mode) == 0o600)
        before = fx.reg.read_bytes()
        res = fx.allow(r)
        check(f"{_VL} second allow is idempotent (exit 0, bytes identical)",
              res.returncode == 0 and fx.reg.read_bytes() == before and "allowed: demo" in res.stdout + res.stderr)
        res = fx.vibe("link", "list")
        check(f"{_VL} list prints '  demo  <path>'",
              res.returncode == 0 and f"  demo  {r}" in res.stdout.split("\n"), res.stdout)
        res = fx.vibe("link", "deny", "demo")
        check(f"{_VL} deny exits 0, registry 600 without the line",
              res.returncode == 0 and fx.reg.exists() and "demo=" not in fx.reg.read_text()
              and stat.S_IMODE(fx.reg.stat().st_mode) == 0o600, res.stderr)
        res = fx.vibe("link", "deny", "demo")
        check(f"{_VL} deny of an absent name still exits 0", res.returncode == 0, res.stderr)
        res = fx.vibe("link", "list")
        check(f"{_VL} list then prints (none)", res.returncode == 0 and "(none)" in res.stdout, res.stdout)
        # allow via a symlinked cwd registers the pwd -P path (control that
        # the realpath, not the symlink spelling, is stored)
        ln = fx.root / "alias"
        ln.symlink_to(r)
        res = fx.allow(ln)
        check(f"{_VL} allow from a symlinked cwd stores the pwd -P path",
              res.returncode == 0 and fx.reg.read_text() == f"demo={r}\n", res.stderr + fx.reg.read_text())
        # no-name allow uses the lowercased basename
        r2 = fx.repo("MyRepo")
        res = fx.allow(r2)
        check(f"{_VL} allow with no name lowercases the cwd basename",
              res.returncode == 0 and f"myrepo={r2}\n" in fx.reg.read_text(), res.stderr)
        # list formats noask
        fx.write_reg(f"demo={r}\tnoask\n")
        res = fx.vibe("link", "list")
        check(f"{_VL} list marks noask entries ' (no confirm)'",
              f"  demo  {r} (no confirm)" in res.stdout.split("\n"), res.stdout)
    finally:
        fx.close("ac1")


# ── AC2 ──────────────────────────────────────────────────────────────────────
def test_vl_ac2_allow_refusals():
    print(f"\n{_VL} AC2 allow refusals leave the registry unchanged")
    fx = _Fx()
    try:
        other = fx.repo("other")
        assert fx.allow(other).returncode == 0
        fx.write_reg(fx.reg.read_text() + "")  # keep 600
        before = fx.reg.read_bytes()
        demo = fx.repo("demo")

        def refused(label, repo, *names, **extra):
            res = fx.allow(repo, *names, **extra)
            ok = (res.returncode == 1 and "refused:" in res.stdout + res.stderr
                  and fx.reg.read_bytes() == before)
            check(f"{_VL} refused (exit 1, 'refused:', unchanged): {label}", ok,
                  f"rc={res.returncode} {res.stdout}{res.stderr}")

        refused("uppercase name", demo, "Demo")
        refused("space in name", demo, "de mo")
        refused("65-char name", demo, "a" * 65)
        refused("name with slash", demo, "a/b")
        notgit = fx.proj / "plain"
        notgit.mkdir()
        refused("not a git work tree", notgit, "plain")
        # 64-char name is the accepted boundary (positive control)
        res = fx.allow(demo, "a" * 64)
        check(f"{_VL} control: a 64-char name is accepted", res.returncode == 0, res.stderr)
        fx.reg.write_bytes(before)
        for label, dirname in [("single quote", "it's"), ("double quote", 'dq"x'),
                               ("dollar", "dol$lar"), ("backtick", "bt`x"),
                               ("semicolon", "a;b"), ("backslash", "a\\b"),
                               ("non-ASCII byte", "café")]:
            d = fx.proj / dirname
            try:
                d.mkdir()
            except OSError:
                continue
            run(["git", "init", "-q", str(d)], env=fx.env())
            refused(f"cwd path containing {label}", d, "okname")
        res = fx.vibe("link", "allow", "a", "b", cwd=demo)
        check(f"{_VL} allow with two names is a usage error (exit 1)",
              res.returncode == 1 and "Usage: vibe link" in res.stdout + res.stderr, res.stderr)
        # bad basename when no name given
        d = fx.proj / "my repo"
        d.mkdir()
        run(["git", "init", "-q", str(d)], env=fx.env())
        refused("no name and basename 'my repo' fails the regex", d)
        # name registered to another path
        refused("name already registered to another path", demo, "other")
        # path registered under another name
        refused("path already registered under another name", other, "different")
        # control: a fresh name+path pair IS accepted
        res = fx.allow(demo, "demo")
        check(f"{_VL} control: a fresh name and path is accepted", res.returncode == 0, res.stderr)
    finally:
        fx.close("ac2a")
    # symlinked registry
    fx = _Fx()
    try:
        demo = fx.repo("demo")
        real = fx.root / "real-registry"
        real.write_text("")
        real.chmod(0o600)
        fx.reg.parent.mkdir(parents=True)
        fx.reg.symlink_to(real)
        res = fx.allow(demo)
        check(f"{_VL} allow refuses a symlinked registry and does not write through it",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr and real.read_text() == ""
              and fx.reg.is_symlink(), res.stderr)
        res = fx.vibe("link", "deny", "demo")
        check(f"{_VL} deny refuses a symlinked registry (exit 1)",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr and real.read_text() == "",
              res.stderr)
    finally:
        fx.close("ac2b")
    # 644 registry repaired
    fx = _Fx()
    try:
        demo = fx.repo("demo")
        fx.write_reg("", mode=0o644)
        res = fx.allow(demo)
        check(f"{_VL} allow repairs a 644 registry to 600 with the 'now trusted' note",
              res.returncode == 0 and stat.S_IMODE(fx.reg.stat().st_mode) == 0o600
              and "now trusted" in res.stdout + res.stderr, res.stdout + res.stderr)
    finally:
        fx.close("ac2c")


# ── AC3 ──────────────────────────────────────────────────────────────────────
def test_vl_ac3_registry_fail_closed():
    print(f"\n{_VL} AC3 symlinked / group-readable registry fails closed")
    # Without the usability check the open would reach the osascript recorder
    # (exit 0); with it the exit is 5 and the recorder log stays empty.
    for kind in ("symlink", "mode644"):
        fx = _Fx()
        try:
            demo = fx.repo("demo")
            url = "vibe://open?project=demo"
            if kind == "symlink":
                real = fx.root / "real-registry"
                real.write_text(f"demo={demo}\n")
                real.chmod(0o600)
                fx.reg.parent.mkdir(parents=True)
                fx.reg.symlink_to(real)
            else:
                fx.write_reg(f"demo={demo}\n", mode=0o644)
            res = fx.open(url, VIBE_LINK_ASSUME="open")
            check(f"{_VL} {kind}: open exits 5 with a warning line",
                  res.returncode == 5 and "⚠" in res.stdout + res.stderr, f"rc={res.returncode} {res.stderr}")
            check(f"{_VL} {kind}: no recorder was called", fx.calls() == [], str(fx.calls()))
            res = fx.vibe("link", "list")
            check(f"{_VL} {kind}: list prints (none), exit 0",
                  res.returncode == 0 and "(none)" in res.stdout and str(demo) not in res.stdout, res.stdout)
            # positive control: a good registry opens
            if kind == "symlink":
                fx.reg.unlink()
                fx.write_reg(f"demo={demo}\n")
            else:
                fx.reg.chmod(0o600)
            res = fx.open(url, VIBE_LINK_ASSUME="open")
            check(f"{_VL} {kind}: control: after repair the same open launches (recorder called)",
                  res.returncode == 0 and len(fx.calls("osascript")) == 1, f"rc={res.returncode} {res.stderr}")
        finally:
            fx.close(f"ac3-{kind}")


def test_vl_ac3_line_grammar():
    print(f"\n{_VL} AC3 registry line grammar, duplicates, no command substitution")
    fx = _Fx()
    try:
        ok = fx.repo("okproj")
        reg = (f"bad name=/x\n"
               f"demo2=/tmp/x$(touch PWNED)\n"
               f"demo3=/tmp/ok\tbogus\n"
               f"demo4=/tmp/ok\\tnoask\n"
               f"dup={ok}\n"
               f"dup={ok}\n"
               f"okproj={ok}\n"
               f"demo5=/tmp/`touch PWNED`\n"
               f"demo6=/tmp/a;touch PWNED\n"
               f"demo7=relative/path\n"
               f"demo8={ok}\tnoask\textra\n")
        fx.write_reg(reg)
        for name in ("demo2", "demo3", "demo4", "dup", "demo5", "demo6", "demo7", "demo8"):
            res = fx.open(f"vibe://open?project={name}", VIBE_LINK_ASSUME="open")
            check(f"{_VL} {name}: unregistered (exit 2)", res.returncode == 2
                  and "no vibe project called" in res.stdout + res.stderr, f"rc={res.returncode} {res.stderr}")
        res = fx.open("vibe://open?project=demo2", VIBE_LINK_ASSUME="open")
        check(f"{_VL} an invalid line prints '⚠ ignoring invalid line 2'",
              "⚠ ignoring invalid line 2" in res.stderr + res.stdout, res.stderr)
        check(f"{_VL} the bad-name line 1 is also warned about",
              "ignoring invalid line 1" in res.stderr + res.stdout)
        res = fx.open("vibe://open?project=dup", VIBE_LINK_ASSUME="open")
        check(f"{_VL} duplicate name prints a warning naming the duplicate",
              "⚠" in res.stderr and "dup" in res.stderr and "duplicate" in res.stderr.lower(), res.stderr)
        check(f"{_VL} no PWNED file was created anywhere (no command substitution/exec of registry text)",
              fx.pwned() == [], str(fx.pwned()))
        check(f"{_VL} nothing launched for any broken entry", fx.calls("osascript") == [], str(fx.calls()))
        res = fx.vibe("link", "list")
        check(f"{_VL} list shows only the valid entry",
              res.stdout.rstrip().split("\n") == [f"  okproj  {ok}"], res.stdout)
        # positive control: the valid line in the same file opens
        res = fx.open("vibe://open?project=okproj", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: the valid line in the same registry opens",
              res.returncode == 0 and len(fx.calls("osascript")) == 1, f"rc={res.returncode} {res.stderr}")
        # a registered path that no longer exists / was swapped for a symlink
        gone = fx.repo("gone")
        fx.write_reg(f"gone={gone}\nswap={fx.proj}/swap\n")
        shutil.rmtree(gone)
        res = fx.open("vibe://open?project=gone", VIBE_LINK_ASSUME="open")
        check(f"{_VL} a vanished project folder exits 2 'no vibe project called'",
              res.returncode == 2 and "no vibe project called" in res.stdout + res.stderr, res.stderr)
        sw = fx.repo("elsewhere")
        (fx.proj / "swap").symlink_to(sw)
        n_before = len(fx.calls("osascript"))
        res = fx.open("vibe://open?project=swap", VIBE_LINK_ASSUME="open")
        check(f"{_VL} a registered path swapped for a symlink does not retarget consent (exit 2)",
              res.returncode == 2 and len(fx.calls("osascript")) == n_before, f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac3-grammar")


# ── AC4 ──────────────────────────────────────────────────────────────────────
def test_vl_ac4_url_refusals():
    print(f"\n{_VL} AC4 URL refusals touch nothing")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        fx.stamps.mkdir(parents=True)
        # Make the registry unusable on purpose: a refused URL must exit 2 BEFORE
        # the registry is read (otherwise this reports 5, not 2).
        good_reg = fx.reg.read_bytes()
        fx.reg.chmod(0o644)
        bad = [
            "http://open?project=demo", "VIBE://open?project=demo", "vibe://OPEN?project=demo",
            "vibe://run?project=demo", "vibe://open?task=ABBR-1", "vibe://open?project=Demo",
            "vibe://open?project=../x", "vibe://open?project=demo;id", "vibe://open?project=demo%20x",
            "vibe://open?project=demo&project=demo", "vibe://open?project=demo&&task=ABBR-1",
            "vibe://open?project=demo&", "vibe://open?&project=demo",
            "vibe://open?project=demo&task=ABBR-1;x", "vibe://open?project=demo&task=",
            "vibe://open?project=demo&tty=Hyper", "vibe://open?project=demo#x",
            "vibe://open?project=demo\nx", "vibe://open?project=demo\tx", "vibe://open?project=demo\x1b[0m",
            "vibe://open?project=demo x", "vibe://open?project=demo+x",
            "vibe://open?project=demo&task=ABBR-1&task=ABBR-2", "vibe://open?project=demo&tty=kitty&tty=kitty",
            "vibe://open?Project=demo", "vibe://open?project=demo&tty=kitty2", "vibe://open?project=demo&tty=terminal",
            "vibe://open?project=demo&task=nohyphen", "vibe://open?project=demo&task=ABBR-1x",
            "vibe://open?project=demo&task=taskandeye://node/not-a-uuid",
            "vibe://open?project=demo&a=b=c", "vibe://open?project", "vibe://open?=demo", "vibe://open?",
            "vibe://open", "vibe://open?project=demo&x=" + "a" * (1025 - len("vibe://open?project=demo&x=")),
            "vibe://open?project=" + "a" * 65, "", "vibe://open?project=demo`x`", "vibe://open?project=$(x)",
            "vibe://open?project=demo'", 'vibe://open?project=demo"', "vibe://open?project=demo\\x",
            "vibe://other/open?project=demo", "vibe:/open?project=demo", "xvibe://open?project=demo",
        ]
        snap = lambda: (fx.reg.stat().st_mtime_ns, fx.stamps.stat().st_mtime_ns,
                        sorted(p.name for p in (fx.home / ".vibe").iterdir()))
        before = snap()
        regbytes = fx.reg.read_bytes()
        fails = []
        for u in bad:
            res = fx.open(u, VIBE_LINK_ASSUME="open")
            if not (res.returncode == 2 and "refused URL" in res.stdout + res.stderr):
                fails.append((u[:50], res.returncode, res.stderr[:80]))
        check(f"{_VL} all {len(bad)} malformed URLs exit 2 'refused URL' (and not 5: registry unread)",
              fails == [], str(fails))
        check(f"{_VL} no recorder call for any refused URL (no dialog, no launch)",
              fx.calls() == [], str(fx.calls())[:200])
        check(f"{_VL} registry bytes and mtime, stamp dir and ~/.vibe listing untouched",
              snap() == before and fx.reg.read_bytes() == regbytes)
        check(f"{_VL} no stamp file was created", list(fx.stamps.iterdir()) == [])
        check(f"{_VL} URL of exactly 1025 bytes is in the list above",
              any(len(u) == 1025 for u in bad))
        # Positive controls on the same fixture.
        fx.reg.chmod(0o600)
        fx.reg.write_bytes(good_reg)
        res = fx.open("vibe://open?project=nothere", VIBE_LINK_ASSUME="open")
        check(f"{_VL} a well-formed URL for an unknown project exits 2 'no vibe project called'",
              res.returncode == 2 and "no vibe project called" in res.stderr and "refused URL" not in res.stderr,
              res.stderr)
        pad = "vibe://open?project=demo&x=" + "a" * (1024 - len("vibe://open?project=demo&x="))
        res = fx.vibe("link", "open", pad, VIBE_LINK_ASSUME="open", VIBE_LINK_DRY_RUN="1")
        check(f"{_VL} control: a 1024-byte URL is accepted (boundary)", len(pad) == 1024 and res.returncode == 0,
              f"rc={res.returncode} {res.stderr}")
        res = fx.open("vibe://open?project=demo", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: a plain valid open reaches the recorder",
              res.returncode == 0 and len(fx.calls("osascript")) == 1, res.stderr)
        check(f"{_VL} no PWNED created", fx.pwned() == [])
    finally:
        fx.close("ac4")


def test_vl_ac4_accepts():
    print(f"\n{_VL} AC4/AC5 accepted URL shapes")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        base = _exp("Darwin", "Terminal", demo, v)
        for u, want in [
            ("vibe://open?project=demo", base),
            ("vibe://open/?project=demo", base),
            ("vibe://open?project=demo&foo=bar&foo=baz", base),
            ("vibe://open?foo=bar&project=demo&tty=Terminal", base),
            ("vibe://open?project=demo&Task=ABBR-1", base),  # keys are case-sensitive: Task is unknown, ignored
            ("vibe://open?project=demo&task=abbr-7", _exp("Darwin", "Terminal", demo, v, "abbr-7")),
        ]:
            res = fx.vibe("link", "open", u, **_dry())
            check(f"{_VL} accepts {u[:60]}", res.returncode == 0 and _launch(res.stdout) == want,
                  f"rc={res.returncode} {res.stdout} {res.stderr}")
    finally:
        fx.close("ac4-accepts")


# ── AC5 ──────────────────────────────────────────────────────────────────────
def test_vl_ac5_darwin_terminal_dry_run():
    print(f"\n{_VL} AC5 Darwin dry run, Terminal")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        res = fx.vibe("link", "open", "vibe://open?project=demo", **_dry())
        check(f"{_VL} no dialog block and exactly the Terminal launch argv",
              res.returncode == 0 and [b[0] for b in _blocks(res.stdout)] == ["launch"]
              and _launch(res.stdout) == _exp("Darwin", "Terminal", demo, v), res.stdout + res.stderr)
        check(f"{_VL} stdout is only DRYRUN / argv lines",
              all(l == "" or l.startswith("DRYRUN ") or l.startswith("  argv: ") for l in res.stdout.split("\n")),
              res.stdout)
        check(f"{_VL} dry run executed nothing and wrote no stamp",
              fx.calls() == [] and not (fx.stamps / "demo").exists())
        for u, task in [("vibe://open?project=demo&task=ABBR-12", "ABBR-12"),
                        (f"vibe://open?project=demo&task=taskandeye://node/{_SENTINEL_UUID}",
                         f"taskandeye://node/{_SENTINEL_UUID}")]:
            res = fx.vibe("link", "open", u, **_dry())
            got = _launch(res.stdout)
            check(f"{_VL} task {task[:24]} appended as --task '<ref>' inside the command",
                  got == _exp("Darwin", "Terminal", demo, v, task)
                  and f"'{task}'" in got[2] and "--task" in got[2], str(got) + res.stderr)
        r1 = fx.vibe("link", "open", "vibe://open?project=demo&foo=bar&foo=baz", **_dry())
        r0 = fx.vibe("link", "open", "vibe://open?project=demo", **_dry())
        check(f"{_VL} repeated unknown keys are ignored (output equals the plain case)",
              r1.returncode == 0 and r1.stdout == r0.stdout)
        r2 = fx.vibe("link-open", "vibe://open?project=demo&task=ABBR-12", **_dry())
        r3 = fx.vibe("link", "open", "vibe://open?project=demo&task=ABBR-12", **_dry())
        check(f"{_VL} 'vibe link-open <url>' prints the same as 'vibe link open <url>'",
              r2.returncode == 0 and r2.stdout == r3.stdout and "DRYRUN launch" in r2.stdout, r2.stderr)
        # path with spaces and allowed punctuation is carried verbatim
        sp = fx.repo("sp ace+at@co,mma=tilde~")
        res = fx.allow(sp, "spaced")
        res = fx.vibe("link", "open", "vibe://open?project=spaced", **_dry())
        check(f"{_VL} a registered path with space and + @ , = ~ is launched verbatim",
              res.returncode == 0 and _launch(res.stdout) == _exp("Darwin", "Terminal", sp, v), res.stdout + res.stderr)
    finally:
        fx.close("ac5")


# ── AC6 ──────────────────────────────────────────────────────────────────────
def test_vl_ac6_darwin_terminals():
    print(f"\n{_VL} AC6 Darwin per-terminal dry runs")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        for term in ("iTerm", "Ghostty", "kitty", "WezTerm", "Terminal"):
            fx.write_cfg(f"VIBE_TERMINAL={term}\n")
            for task in (None, "ABBR-12"):
                u = "vibe://open?project=demo" + (f"&task={task}" if task else "")
                res = fx.vibe("link", "open", u, **_dry())
                check(f"{_VL} Darwin {term} task={task}: argv matches the design",
                      res.returncode == 0 and _launch(res.stdout) == _exp("Darwin", term, demo, v, task),
                      f"{res.stdout} {res.stderr}")
        fx.write_cfg("VIBE_TERMINAL=Terminal\n")
        res = fx.vibe("link", "open", "vibe://open?project=demo&tty=kitty", **_dry())
        check(f"{_VL} tty=kitty in the URL overrides a configured Terminal",
              _launch(res.stdout) == _exp("Darwin", "kitty", demo, v), res.stdout + res.stderr)
        fx.write_cfg("VIBE_TERMINAL=Hyper\n")
        res = fx.vibe("link", "open", "vibe://open?project=demo", **_dry())
        check(f"{_VL} configured VIBE_TERMINAL=Hyper on Darwin: warning and Terminal fallback",
              res.returncode == 0 and "⚠" in res.stderr + res.stdout
              and _launch(res.stdout) == _exp("Darwin", "Terminal", demo, v), res.stdout + res.stderr)
        fx.write_cfg("VIBE_TERMINAL=gnome-terminal\n")
        res = fx.vibe("link", "open", "vibe://open?project=demo", **_dry())
        check(f"{_VL} Linux-only terminal configured on Darwin: warning and Terminal fallback",
              res.returncode == 0 and "⚠" in res.stderr + res.stdout
              and _launch(res.stdout) == _exp("Darwin", "Terminal", demo, v), res.stdout + res.stderr)
        res = fx.vibe("link", "open", "vibe://open?project=demo&tty=gnome-terminal", **_dry())
        check(f"{_VL} tty=gnome-terminal on Darwin exits 2 'not available on this system'",
              res.returncode == 2 and "not available on this system" in res.stderr, res.stderr)
        # config beats the environment; environment alone is honoured
        fx.write_cfg("VIBE_TERMINAL=iTerm\n")
        res = fx.vibe("link", "open", "vibe://open?project=demo", **_dry(VIBE_TERMINAL="kitty"))
        check(f"{_VL} a config VIBE_TERMINAL wins over the environment",
              _launch(res.stdout) == _exp("Darwin", "iTerm", demo, v), res.stdout)
        fx.write_cfg("FOO=1\n")
        res = fx.vibe("link", "open", "vibe://open?project=demo", **_dry(VIBE_TERMINAL="kitty"))
        check(f"{_VL} control: with no config line the environment VIBE_TERMINAL is used",
              _launch(res.stdout) == _exp("Darwin", "kitty", demo, v), res.stdout)
    finally:
        fx.close("ac6-darwin")


def test_vl_ac6_linux():
    print(f"\n{_VL} AC6 Linux terminals and exit 6 / exit 2 ordering")
    fx = _Fx("Linux")
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        fx.rec("zenity")
        url = "vibe://open?project=demo"
        # No terminal configured: exit 6 mentioning 'vibe link terminal' — and
        # no dialog (zenity recorder untouched) and no stamp, since terminal
        # resolution precedes both.
        res = fx.open(url)
        check(f"{_VL} Linux with no VIBE_TERMINAL: exit 6 mentioning 'vibe link terminal'",
              res.returncode == 6 and "vibe link terminal" in res.stderr, f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} exit 6 showed no dialog and wrote no stamp",
              fx.calls("zenity") == [] and not (fx.stamps / "demo").exists())
        res = fx.vibe("link", "open", url + "&tty=iTerm", **_dry())
        check(f"{_VL} tty=iTerm on Linux exits 2 'not available on this system'",
              res.returncode == 2 and "not available on this system" in res.stderr, res.stderr)
        check(f"{_VL} exit 2 (terminal) showed no dialog and wrote no stamp",
              fx.calls("zenity") == [] and not (fx.stamps / "demo").exists())
        # Configured but not installed: exit 6.
        fx.write_cfg("VIBE_TERMINAL=kitty\n")
        check(f"{_VL} precondition: no real kitty on the test PATH",
              shutil.which("kitty", path=fx.env()["PATH"]) is None)
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} VIBE_TERMINAL=kitty with kitty not installed: exit 6",
              res.returncode == 6 and fx.calls("kitty") == [], f"rc={res.returncode} {res.stderr}")
        # Installed: each Linux terminal's argv (positive controls)
        for term, prog in [("kitty", "kitty"), ("Ghostty", "ghostty"), ("WezTerm", "wezterm"),
                           ("gnome-terminal", "gnome-terminal")]:
            fx.rec(prog)
            fx.write_cfg(f"VIBE_TERMINAL={term}\n")
            for task in (None, "ABBR-3"):
                u = url + (f"&task={task}" if task else "")
                res = fx.vibe("link", "open", u, **_dry())
                check(f"{_VL} Linux {term} task={task}: dry-run argv matches the design",
                      res.returncode == 0 and _launch(res.stdout) == _exp("Linux", term, demo, v, task),
                      res.stdout + res.stderr)
        res = fx.open(url + "&task=ABBR-3", VIBE_LINK_ASSUME="open")
        c = fx.calls("gnome-terminal")
        check(f"{_VL} real Linux run executes the gnome-terminal recorder with the design argv",
              res.returncode == 0 and len(c) == 1 and c[0][1] == _exp("Linux", "gnome-terminal", demo, v, "ABBR-3")[1:],
              f"rc={res.returncode} {c} {res.stderr}")
        # tty= overrides config on Linux when installed (the real run above stamped demo)
        shutil.rmtree(fx.stamps, ignore_errors=True)
        res = fx.vibe("link", "open", url + "&tty=kitty", **_dry())
        check(f"{_VL} tty=kitty overrides the configured gnome-terminal on Linux",
              _launch(res.stdout) == _exp("Linux", "kitty", demo, v), res.stdout + res.stderr)
        # Invalid configured value on Linux: warning + exit 6
        fx.write_cfg("VIBE_TERMINAL=Hyper\n")
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} configured VIBE_TERMINAL=Hyper on Linux: warning and exit 6",
              res.returncode == 6 and "⚠" in res.stderr + res.stdout, f"rc={res.returncode} {res.stderr}")
        # Registry lookup precedes terminal resolution
        fx.write_cfg("FOO=1\n")
        res = fx.open("vibe://open?project=nothere", VIBE_LINK_ASSUME="open")
        check(f"{_VL} unknown project is exit 2 even when no terminal is configured (lookup first)",
              res.returncode == 2 and "no vibe project called" in res.stderr, f"rc={res.returncode}")
        # Terminal resolution precedes the rate-limit check
        fx.stamps.mkdir(parents=True, exist_ok=True)
        (fx.stamps / "demo").write_text("")
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} fresh stamp + no terminal: exit 6 (terminal before rate limit)", res.returncode == 6,
              f"rc={res.returncode}")
        res = fx.open(url + "&tty=iTerm", VIBE_LINK_ASSUME="open")
        check(f"{_VL} fresh stamp + tty not on this OS: exit 2 (terminal before rate limit)",
              res.returncode == 2, f"rc={res.returncode}")
        fx.write_cfg("VIBE_TERMINAL=kitty\n")
        res = fx.open(url)
        check(f"{_VL} fresh stamp, no zenity needed: exit 3 before any dialog",
              res.returncode == 3 and fx.calls("zenity") == [], f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac6-linux")


# ── AC7 ──────────────────────────────────────────────────────────────────────
def test_vl_ac7_terminal_preference():
    print(f"\n{_VL} AC7 vibe link terminal")
    fx = _Fx()
    try:
        cfg = fx.home / ".vibe" / "config"
        res = fx.vibe("link", "terminal", "kitty")
        check(f"{_VL} terminal kitty exits 0 printing VIBE_TERMINAL=kitty",
              res.returncode == 0 and "VIBE_TERMINAL=kitty" in res.stdout + res.stderr, res.stderr)
        check(f"{_VL} creates the config 600 containing exactly VIBE_TERMINAL=kitty",
              cfg.exists() and cfg.read_text() == "VIBE_TERMINAL=kitty\n" and stat.S_IMODE(cfg.stat().st_mode) == 0o600,
              repr(cfg.read_text() if cfg.exists() else None))
        cfg.write_text('FOO=1\nexport VIBE_TERMINAL="iTerm"\n VIBE_TERMINAL=Ghostty\nBAR=2\n')
        cfg.chmod(0o640)
        res = fx.vibe("link", "terminal", "kitty")
        txt = cfg.read_text()
        check(f"{_VL} existing VIBE_TERMINAL lines (export/quoted/indented) collapse to one, others kept, mode kept",
              res.returncode == 0 and txt.split("\n")[:-1] == ["FOO=1", "VIBE_TERMINAL=kitty", "BAR=2"]
              and stat.S_IMODE(cfg.stat().st_mode) == 0o640, repr(txt))
        for bad in ("Hyper", "Kitty", "terminal", "kitty2", ""):
            before = cfg.read_text()
            res = fx.vibe("link", "terminal", bad)
            check(f"{_VL} terminal {bad!r} exits 1 'refused:' and leaves the config alone",
                  res.returncode == 1 and "refused:" in res.stdout + res.stderr and cfg.read_text() == before,
                  f"rc={res.returncode} {res.stderr}")
        for good in ("Terminal", "iTerm", "Ghostty", "WezTerm", "gnome-terminal"):
            res = fx.vibe("link", "terminal", good)
            check(f"{_VL} terminal {good} accepted", res.returncode == 0 and f"VIBE_TERMINAL={good}\n" in cfg.read_text(),
                  res.stderr)
        # VIBE_CONFIG redirects the write
        other = fx.root / "elsewhere.conf"
        cfg.unlink()
        res = fx.vibe("link", "terminal", "WezTerm", VIBE_CONFIG=str(other))
        check(f"{_VL} with VIBE_CONFIG set, that file is written and ~/.vibe/config is not",
              res.returncode == 0 and other.read_text() == "VIBE_TERMINAL=WezTerm\n" and not cfg.exists(),
              res.stderr)
        # symlinked config is not followed
        real = fx.root / "real.conf"
        real.write_text("KEEP=1\n")
        lnk = fx.root / "link.conf"
        lnk.symlink_to(real)
        res = fx.vibe("link", "terminal", "kitty", VIBE_CONFIG=str(lnk))
        check(f"{_VL} a symlinked config exits 1 and is not followed",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr and real.read_text() == "KEEP=1\n"
              and lnk.is_symlink(), res.stderr)
        # wrong arg counts
        for args in (("link", "terminal"), ("link", "terminal", "kitty", "x")):
            res = fx.vibe(*args)
            check(f"{_VL} {' '.join(args)}: usage error (exit 1)",
              res.returncode == 1 and "Usage: vibe link" in res.stdout + res.stderr)
    finally:
        fx.close("ac7")


# ── AC8 ──────────────────────────────────────────────────────────────────────
def test_vl_ac8_dialog_and_assume():
    print(f"\n{_VL} AC8 confirmation dialog text and VIBE_LINK_ASSUME")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        res = fx.vibe("link", "open", "vibe://open?project=demo&foo=SENTINELX", VIBE_LINK_DRY_RUN="1")
        b = _blocks(res.stdout)
        check(f"{_VL} dry run without ASSUME: a dialog block precedes the launch block",
              res.returncode == 0 and [x[0] for x in b] == ["dialog", "launch"], res.stdout + res.stderr)
        dlg = b[0][1] if b else []
        script = dlg[2] if len(dlg) >= 3 else ""
        check(f"{_VL} dialog argv is osascript -e <display dialog script>",
              dlg[:2] == ["osascript", "-e"] and len(dlg) == 3 and script.startswith("display dialog"), str(dlg))
        for frag in ("demo", str(demo), 'default button "Cancel"', 'cancel button "Cancel"',
                     "giving up after 60", "Always for this project", '"Open"'):
            check(f"{_VL} dialog script contains {frag!r}", frag in script, script)
        check(f"{_VL} dialog shows no other URL text (SENTINELX absent everywhere)",
              "SENTINELX" not in res.stdout, res.stdout)
        check(f"{_VL} dialog block is followed by the normal Terminal launch",
              b[1][1] == _exp("Darwin", "Terminal", demo, v) if len(b) == 2 else False)
        check(f"{_VL} dry run ran no dialog or launch", fx.calls() == [])
        # cancel / bogus ASSUME: exit 4, no recorder (control: ASSUME=open reaches it, see below)
        for val in ("cancel", "bogus", "OPEN", "yes"):
            res = fx.open("vibe://open?project=demo", VIBE_LINK_ASSUME=val)
            check(f"{_VL} VIBE_LINK_ASSUME={val}: exit 4 'cancelled', nothing launched",
                  res.returncode == 4 and "cancelled" in res.stderr and fx.calls("osascript") == [],
                  f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} cancel consumed no stamp", not (fx.stamps / "demo").exists())
        res = fx.open("vibe://open?project=demo", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: ASSUME=open on the same project launches (recorder called once)",
              res.returncode == 0 and len(fx.calls("osascript")) == 1, res.stderr)
    finally:
        fx.close("ac8a")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        res = fx.vibe("link", "open", "vibe://open?project=demo", **dict(VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="always"))
        check(f"{_VL} ASSUME=always exits 0 (even in dry run)", res.returncode == 0, res.stderr)
        check(f"{_VL} ASSUME=always rewrites the line to demo=<path><TAB>noask, one line, mode 600",
              fx.reg.read_text() == f"demo={demo}\tnoask\n" and stat.S_IMODE(fx.reg.stat().st_mode) == 0o600,
              repr(fx.reg.read_text()))
        res = fx.vibe("link", "open", "vibe://open?project=demo", **dict(VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="cancel"))
        check(f"{_VL} afterwards ASSUME=cancel still launches with no dialog block (noask)",
              res.returncode == 0 and [x[0] for x in _blocks(res.stdout)] == ["launch"], res.stdout + res.stderr)
        res = fx.vibe("link", "open", "vibe://open?project=demo", VIBE_LINK_DRY_RUN="1")
        check(f"{_VL} noask also skips the dialog with no ASSUME at all",
              [x[0] for x in _blocks(res.stdout)] == ["launch"], res.stdout)
        res = fx.vibe("link", "list")
        check(f"{_VL} list shows ' (no confirm)'", f"  demo  {demo} (no confirm)" in res.stdout.split("\n"), res.stdout)
        res = fx.open("vibe://open?project=demo", VIBE_LINK_ASSUME="cancel")
        check(f"{_VL} real run with noask and ASSUME=cancel launches (recorder called once)",
              res.returncode == 0 and len(fx.calls("osascript")) == 1, f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac8b")


def test_vl_ac8_real_dialog_replies():
    print(f"\n{_VL} AC8 real (non-dry) dialogs: osascript replies and zenity")
    url = "vibe://open?project=demo"
    cases = [("Open", 0, "button returned:Open, gave up:false", 0, 2),
             ("Cancel button", 1, "", 4, 1),
             ("osascript error", 1, "execution error", 4, 1),
             ("timeout", 0, "button returned:, gave up:true", 4, 1)]
    for label, rc, out, want_rc, want_calls in cases:
        fx = _Fx()
        try:
            _setup_demo(fx)
            fx.rec("osascript", rc=rc, out=out)
            res = fx.open(url)
            check(f"{_VL} Mac dialog reply {label}: exit {want_rc}, {want_calls} osascript call(s)",
                  res.returncode == want_rc and len(fx.calls("osascript")) == want_calls,
                  f"rc={res.returncode} calls={len(fx.calls('osascript'))} {res.stderr}")
            if want_rc == 4:
                check(f"{_VL} Mac dialog {label}: 'cancelled' and no stamp consumed",
                      "cancelled" in res.stderr and not (fx.stamps / "demo").exists())
            else:
                first = fx.calls("osascript")[0][1]
                check(f"{_VL} Mac dialog is osascript -e display dialog (first call), launch second",
                      first[0] == "-e" and first[1].startswith("display dialog")
                      and "do script" in fx.calls("osascript")[1][1][1], str(first)[:100])
        finally:
            fx.close(f"ac8-mac-{label}")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        fx.rec("osascript", out="button returned:Always for this project, gave up:false")
        res = fx.open(url)
        check(f"{_VL} Mac reply 'Always for this project' launches and rewrites the line with noask",
              res.returncode == 0 and fx.reg.read_text() == f"demo={demo}\tnoask\n" and len(fx.calls("osascript")) == 2,
              f"rc={res.returncode} {fx.reg.read_text()!r}")
    finally:
        fx.close("ac8-always")
    # Linux
    fx = _Fx("Linux")
    try:
        demo = _setup_demo(fx)
        fx.rec("kitty")
        fx.write_cfg("VIBE_TERMINAL=kitty\n")
        check(f"{_VL} precondition: no real zenity on the test PATH",
              shutil.which("zenity", path=fx.env()["PATH"]) is None)
        res = fx.open(url)
        check(f"{_VL} Linux without zenity: exit 4 'cannot ask for confirmation', nothing launched",
              res.returncode == 4 and "cannot ask for confirmation" in res.stderr and fx.calls("kitty") == [],
              f"rc={res.returncode} {res.stderr}")
        fx.rec("zenity")
        res = fx.vibe("link", "open", url, VIBE_LINK_DRY_RUN="1")
        b = _blocks(res.stdout)
        check(f"{_VL} Linux with zenity (dry run): dialog block argv starts zenity --question --no-markup",
              [x[0] for x in b] == ["dialog", "launch"] and b[0][1][:3] == ["zenity", "--question", "--no-markup"],
              res.stdout + res.stderr)
        check(f"{_VL} zenity dialog names the project and path", "demo" in " ".join(b[0][1]) and str(demo) in " ".join(b[0][1]))
        res = fx.open(url)
        check(f"{_VL} real run: zenity answering OK launches kitty",
              res.returncode == 0 and len(fx.calls("zenity")) == 1 and len(fx.calls("kitty")) == 1,
              f"rc={res.returncode} {res.stderr}")
        shutil.rmtree(fx.stamps)
        fx.rec("zenity", rc=1)
        k0 = len(fx.calls("kitty"))
        res = fx.open(url)
        check(f"{_VL} real run: zenity answering Cancel gives exit 4 'cancelled', no launch",
              res.returncode == 4 and "cancelled" in res.stderr and len(fx.calls("kitty")) == k0,
              f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac8-linux")


def test_vl_unknown_project_dialog():
    print(f"\n{_VL} unknown-project dialog on macOS")
    fx = _Fx()
    try:
        _setup_demo(fx)
        res = fx.vibe("link", "open", "vibe://open?project=nothere&foo=SENTINELX", VIBE_LINK_DRY_RUN="1")
        b = _blocks(res.stdout)
        check(f"{_VL} exit 2 with a dialog naming the project, and no other URL text",
              res.returncode == 2 and b and b[0][0] == "dialog" and "No vibe project called nothere." in " ".join(b[0][1])
              and "vibe link allow" in " ".join(b[0][1]) and "SENTINELX" not in res.stdout + res.stderr,
              res.stdout + res.stderr)
        res = fx.open("vibe://open?project=nothere")
        c = fx.calls("osascript")
        check(f"{_VL} real run: exactly one osascript dialog call, no launch",
              res.returncode == 2 and len(c) == 1 and "No vibe project called nothere." in c[0][1][1]
              and "do script" not in " ".join(c[0][1]), str(c))
        n = len(fx.calls("osascript"))
        res = fx.open("vibe://open?project=Bad;x")
        check(f"{_VL} a refused URL shows no dialog", res.returncode == 2 and len(fx.calls("osascript")) == n)
    finally:
        fx.close("unknown-dialog")


# ── AC9 ──────────────────────────────────────────────────────────────────────
def test_vl_ac9_rate_limit():
    print(f"\n{_VL} AC9 rate limit")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        url = "vibe://open?project=demo"
        stamp = fx.stamps / "demo"
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} first open: exit 0, recorder called once, stamp written",
              res.returncode == 0 and len(fx.calls("osascript")) == 1 and stamp.exists(), res.stderr)
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} second open: exit 3 'opened less than 5 seconds ago', no further call",
              res.returncode == 3 and "opened less than 5 seconds ago" in res.stderr
              and len(fx.calls("osascript")) == 1, f"rc={res.returncode} {res.stderr}")
        res = fx.open(url)
        check(f"{_VL} the stamp check precedes the dialog (no ASSUME: still exit 3, no dialog)",
              res.returncode == 3 and len(fx.calls("osascript")) == 1)
        now = time.time()
        os.utime(stamp, (now - 10, now - 10))
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} stamp 10 s old: third open runs", res.returncode == 0 and len(fx.calls("osascript")) == 2,
              f"rc={res.returncode} {res.stderr}")
        os.utime(stamp, (now + 60, now + 60))
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} stamp 60 s in the future is limited, exit 3 (AC17 fail-closed)",
              res.returncode == 3 and len(fx.calls("osascript")) == 2, f"rc={res.returncode} {res.stderr}")
        os.utime(stamp, (now - 2, now - 2))
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} stamp 2 s old: still limited (exit 3)", res.returncode == 3, f"rc={res.returncode}")
        os.utime(stamp, (now - 7, now - 7))
        res = fx.open(url, VIBE_LINK_ASSUME="open")
        check(f"{_VL} stamp 7 s old: runs", res.returncode == 0, f"rc={res.returncode}")
        # per-project: a different project is unaffected
        d2 = fx.repo("demo2")
        fx.allow(d2)
        res = fx.open("vibe://open?project=demo2", VIBE_LINK_ASSUME="open")
        check(f"{_VL} the limit is per project", res.returncode == 0, res.stderr)
        # cancelled open on a fresh project writes no stamp, and a dry run writes none
        d3 = fx.repo("fresh")
        fx.allow(d3)
        res = fx.open("vibe://open?project=fresh", VIBE_LINK_ASSUME="cancel")
        check(f"{_VL} cancelled open: exit 4 and no stamp", res.returncode == 4 and not (fx.stamps / "fresh").exists())
        res = fx.vibe("link", "open", "vibe://open?project=fresh", **_dry())
        check(f"{_VL} dry run writes no stamp", res.returncode == 0 and not (fx.stamps / "fresh").exists())
        res = fx.open("vibe://open?project=fresh", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: after a cancel the next open is not rate limited",
              res.returncode == 0 and (fx.stamps / "fresh").exists(), res.stderr)
        # a launch failure consumes the stamp
        d4 = fx.repo("failing")
        fx.allow(d4)
        fx.rec("osascript", rc=1)
        res = fx.open("vibe://open?project=failing", VIBE_LINK_ASSUME="open")
        check(f"{_VL} a failed launch still consumes the stamp",
              (fx.stamps / "failing").exists() and res.returncode != 0, f"rc={res.returncode}")
        # the stamp dir does not hold registry text: names only
        check(f"{_VL} stamps are plain files named after the project",
              sorted(p.name for p in fx.stamps.iterdir()) == ["demo", "demo2", "failing", "fresh"],
              str(list(fx.stamps.iterdir())))
    finally:
        fx.close("ac9")


# ── AC10 ─────────────────────────────────────────────────────────────────────
def test_vl_ac10_launch_path_containment():
    print(f"\n{_VL} AC10 launcher path containment")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        url = "vibe://open?project=demo"

        def stage(dirname: str) -> Path:
            d = fx.root / "copies" / dirname
            d.mkdir(parents=True)
            shutil.copy2(VIBE, d / "vibe")
            (d / "devcontainer").symlink_to(REPO / "devcontainer")
            return d / "vibe"

        # Positive control first: a plain path launches and the recorder gets that path.
        good = stage("plain dir")
        res = run(["bash", str(good), "link", "open", url], env=fx.env(VIBE_LINK_ASSUME="open"), cwd=fx.work)
        c = fx.calls("osascript")
        check(f"{_VL} control: launcher copied to a plain path launches with that path in the argv",
              res.returncode == 0 and len(c) == 1 and f"'{good.resolve()}'" in c[0][1][1],
              f"rc={res.returncode} {res.stderr} {c}")
        n0 = len(fx.calls())
        fails = []
        for label, name in [("double quote", 'dq"x'), ("dollar", "dol$x"), ("command substitution", "x$(touch PWNED)"),
                            ("backtick", "bt`touch PWNED`"), ("single quote", "sq'x"), ("backslash", "bs\\x"),
                            ("semicolon", "a;touch PWNED"), ("non-ASCII", "café")]:
            try:
                bad = stage(name)
            except OSError:
                continue
            for dry in (False, True):
                extra = dict(VIBE_LINK_ASSUME="open")
                if dry:
                    extra["VIBE_LINK_DRY_RUN"] = "1"
                shutil.rmtree(fx.stamps, ignore_errors=True)
                res = run(["bash", str(bad), "link", "open", url], env=fx.env(**extra), cwd=fx.work)
                if not (res.returncode == 7 and "refused: launcher path" in res.stdout + res.stderr
                        and "DRYRUN" not in res.stdout):
                    fails.append((label, dry, res.returncode, res.stderr[:80]))
        check(f"{_VL} launcher under a path with quote/$/backtick/;/\\/non-ASCII: exit 7 'refused: launcher path'",
              fails == [], str(fails))
        check(f"{_VL} no recorder called for any rejected launcher path", len(fx.calls()) == n0, str(fx.calls()[n0:]))
        log = fx.log.read_text().replace(_WRAP_SH.replace('"', '\\"'), "").replace(_WRAP_SH, "")
        check(f"{_VL} no recorder ever received '$(' or a backtick or an unbalanced double quote",
              "$(" not in log and "`" not in log and all(l.count('"') % 2 == 0 for l in log.split("\n")), log[:300])
        check(f"{_VL} no PWNED file created anywhere", fx.pwned() == [], str(fx.pwned()))
    finally:
        fx.close("ac10")


# ── AC11 ─────────────────────────────────────────────────────────────────────
def test_vl_ac11_help_and_docs():
    print(f"\n{_VL} AC11 help text and docs")
    fx = _Fx()
    try:
        res = fx.vibe("--help")
        out = res.stdout + res.stderr
        for frag in ("vibe link allow", "vibe link open", "--install"):
            check(f"{_VL} vibe --help contains {frag!r}", frag in out, out[:200])
    finally:
        fx.close("ac11")
    check(f"{_VL} README.md has 'Open vibe from a link'", "Open vibe from a link" in (REPO / "README.md").read_text())
    check(f"{_VL} MANUAL-TESTS.md has 'Test 68'", "Test 68" in (REPO / "MANUAL-TESTS.md").read_text())
    check(f"{_VL} CHANGELOG.md mentions 'vibe link'", "vibe link" in (REPO / "CHANGELOG.md").read_text())


# ── AC12 ─────────────────────────────────────────────────────────────────────
def test_vl_ac12_no_collateral_change():
    print(f"\n{_VL} AC12 usage errors and no collateral change")
    fx = _Fx()
    try:
        res = fx.vibe("--version")
        want = (REPO / "VERSION").read_text().strip()
        check(f"{_VL} vibe --version prints the contents of VERSION", want in res.stdout and res.returncode == 0,
              res.stdout + res.stderr)
        res = fx.vibe("codex", "list")
        check(f"{_VL} vibe codex list with an empty HOME prints (none)",
              res.returncode == 0 and "(none)" in res.stdout, res.stdout + res.stderr)
        res = fx.vibe("--help")
        out = res.stdout + res.stderr
        check(f"{_VL} --help still contains codex allow, repos add and clean",
              all(s in out for s in ("vibe codex allow", "vibe repos add", "vibe clean")), out[:200])
        usage_cases = [("link",), ("link", "bogus"), ("link", "--install"), ("link", "allow", "a", "b"),
                       ("link", "deny"), ("link", "deny", "a", "b"), ("link", "list", "x"),
                       ("link", "terminal"), ("link", "open"), ("link", "open", "a", "b"), ("link-open",),
                       ("link-open", "a", "b")]
        for args in usage_cases:
            res = fx.vibe(*args)
            check(f"{_VL} vibe {' '.join(args)}: exit 1 'Usage: vibe link'",
                  res.returncode == 1 and "Usage: vibe link" in res.stdout + res.stderr,
                  f"rc={res.returncode} {res.stderr}")
        r = fx.repo("demo")
        res = fx.vibe("link", "deny", "Bad Name")
        check(f"{_VL} deny with a bad name exits 1 'refused:'",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr)
        res = fx.vibe("link", "list")
        check(f"{_VL} list with no registry prints (none), exit 0", res.returncode == 0 and "(none)" in res.stdout)
        fx.write_reg("\n\n")
        res = fx.vibe("link", "list")
        check(f"{_VL} list with an empty registry prints (none), exit 0", res.returncode == 0 and "(none)" in res.stdout)
    finally:
        fx.close("ac12")

