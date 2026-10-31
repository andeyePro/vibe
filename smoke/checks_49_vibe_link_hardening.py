"""`vibe link` hardening (task_062 cycle 2, spec rev 4 addendum AC14-AC21).
Shares the fixture and expected-argv helpers of checks_48_vibe_link."""
import json
import re
import shutil
import stat
import subprocess
import time

from smoke._core import *
from smoke.checks_48_vibe_link import (_Fx, _VL, _SENTINEL_UUID, _blocks, _launch, _exp, _wrap,
                                       _WRAP_SH, _dry, _setup_demo)


# ═════════════════════════════════════════════════════════════════════════════
# Cycle 2 (rev 4 addendum): AC14 - AC21
# ═════════════════════════════════════════════════════════════════════════════
_URL = "vibe://open?project=demo"
_BTN_OPEN = "button returned:Open, gave up:false"


def _shim(fx: _Fx, name: str, body: str) -> None:
    p = fx.bin / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(0o755)


# ── AC14 ─────────────────────────────────────────────────────────────────────
def test_vl_ac14_registered_folder():
    print(f"\n{_VL} AC14 consent stays on the registered folder")
    fx = _Fx()
    try:
        demo = fx.repo("demo")
        sub = demo / "sub"
        sub.mkdir()
        res = fx.allow(sub, "subproj")
        check(f"{_VL} allow from a subfolder of a repo: exit 1 'refused:'",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr, f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} the subfolder refusal registered nothing", not fx.reg.exists() or fx.reg.read_text() == "")
        res = fx.allow(demo)
        check(f"{_VL} control: allow from the repo root is accepted", res.returncode == 0, res.stderr)
        # nested git repo inside a registered path
        inner = demo / "inner"
        inner.mkdir()
        run(["git", "init", "-q", str(inner)], env=fx.env())
        before = fx.reg.read_bytes()
        res = fx.allow(inner.resolve(), "inner")
        check(f"{_VL} allow of a repo inside an already-registered path: exit 1 'refused:'",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr and fx.reg.read_bytes() == before,
              f"rc={res.returncode} {res.stderr}")
        # a path that contains an already-registered path
        outer = fx.repo("outer")
        nested = outer / "nested"
        nested.mkdir()
        run(["git", "init", "-q", str(nested)], env=fx.env())
        assert fx.allow(nested.resolve(), "nested").returncode == 0
        before = fx.reg.read_bytes()
        res = fx.allow(outer, "outer")
        check(f"{_VL} allow of a path that contains a registered path: exit 1 'refused:'",
              res.returncode == 1 and "refused:" in res.stdout + res.stderr and fx.reg.read_bytes() == before,
              f"rc={res.returncode} {res.stderr}")
        # sibling sharing a string prefix is not containment (control)
        sib = fx.repo("demo-two")
        res = fx.allow(sib, "demo-two")
        check(f"{_VL} control: sibling 'demo-two' (string prefix of 'demo') is accepted",
              res.returncode == 0, res.stderr)
        # the symlink route: a symlink to the repo root resolves to the same pwd -P and is accepted idempotently
        link = fx.root / "lnk"
        link.symlink_to(demo)
        res = fx.allow(link, "demo")
        check(f"{_VL} allow through a symlink to the registered root is idempotent (pwd -P)",
              res.returncode == 0 and f"allowed: demo -> {demo}" in res.stdout + res.stderr, res.stderr)
    finally:
        fx.close("ac14-allow")

    # Re-check immediately before launch, after the dialog returns.
    def swap_case(label: str, action: str, want_rc: int, want_calls: int, launches: bool):
        fx = _Fx()
        try:
            demo = _setup_demo(fx)
            moved = fx.root / "moved"
            _shim(fx, "osascript",
                  f"printf '@@ osascript\\n' >> '{fx.log}'; for a in \"$@\"; do printf '%s\\n' \"$a\" >> '{fx.log}'; done\n"
                  f"case \"$1 $2\" in\n"
                  f"  '-e display dialog'*) {action}\n"
                  f"     printf '%s\\n' '{_BTN_OPEN}' ;;\n"
                  f"esac\nexit 0\n")
            res = fx.open(_URL)
            check(f"{_VL} {label}",
                  res.returncode == want_rc and len(fx.calls("osascript")) == want_calls
                  and (("do script" in str(fx.calls('osascript')[-1])) == launches),
                  f"rc={res.returncode} calls={fx.calls('osascript')} {res.stderr}")
            return res
        finally:
            fx.close("ac14-swap")
    swap_case("control: dialog answered Open and path unchanged: launches (exit 0, dialog + launch)",
              ":", 0, 2, True)
    # (the shim bodies reference $HOME-independent absolute paths via the closure below)
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        away = fx.root / "away"
        away.mkdir()
        for label, action in [
            ("directory replaced by a symlink while the dialog is open", f"mv '{demo}' '{demo}.real' && ln -s '{away}' '{demo}'"),
            ("directory deleted while the dialog is open", f"rm -rf '{demo}'"),
        ]:
            shutil.rmtree(fx.stamps, ignore_errors=True)
            _shim(fx, "osascript",
                  f"printf '@@ osascript\\n' >> '{fx.log}'; for a in \"$@\"; do printf '%s\\n' \"$a\" >> '{fx.log}'; done\n"
                  f"case \"$1 $2\" in\n  '-e display dialog'*) {action}\n     printf '%s\\n' '{_BTN_OPEN}' ;;\nesac\nexit 0\n")
            fx.log.write_text("")
            res = fx.open(_URL)
            check(f"{_VL} {label}: exit 2 and no launch (dialog call only)",
                  res.returncode == 2 and len(fx.calls("osascript")) == 1
                  and "do script" not in str(fx.calls("osascript")), f"rc={res.returncode} {fx.calls('osascript')} {res.stderr}")
            # restore for the next case
            if os.path.islink(demo):
                demo.unlink()
                (Path(str(demo) + ".real")).rename(demo)
            elif not demo.exists():
                demo.mkdir()
    finally:
        fx.close("ac14-recheck")


# ── AC15 ─────────────────────────────────────────────────────────────────────
def test_vl_ac15_wrapper_argv():
    print(f"\n{_VL} AC15 every launch goes through the constant /bin/sh wrapper")
    for os_name, terms in [("Darwin", ["Terminal", "iTerm", "Ghostty", "kitty", "WezTerm"]),
                           ("Linux", ["Ghostty", "kitty", "WezTerm", "gnome-terminal"])]:
        fx = _Fx(os_name)
        try:
            demo = _setup_demo(fx)
            v = fx.vibe_path
            for prog in ("ghostty", "kitty", "wezterm", "gnome-terminal"):
                fx.rec(prog)
            for term in terms:
                fx.write_cfg(f"VIBE_TERMINAL={term}\n")
                for task in (None, "ABBR-9", _SENTINEL_UUID):
                    u = _URL + (f"&task={task}" if task else "")
                    res = fx.vibe("link", "open", u, **_dry())
                    got = _launch(res.stdout)
                    check(f"{_VL} {os_name} {term} task={task}: launch argv uses the wrapper",
                          res.returncode == 0 and got == _exp(os_name, term, demo, v, task),
                          f"{got} {res.stderr}")
                    if term in ("Ghostty", "kitty", "WezTerm", "gnome-terminal") and got:
                        w = _wrap(demo, v, task)
                        check(f"{_VL} {os_name} {term}: wrapper words appear verbatim and consecutively, "
                              "no cwd flag",
                              any(got[i:i + len(w)] == w for i in range(len(got))) and
                              not any(a.startswith(("--working-directory", "--directory", "--cwd")) or a in
                                      ("--directory", "--cwd") for a in got), str(got))
                    if term in ("Terminal", "iTerm") and got:
                        s = "\n".join(got)
                        check(f"{_VL} {os_name} {term}: AppleScript text carries the wrapper with \\\" escapes "
                              "and no bare inner double quote",
                              _WRAP_SH.replace('"', '\\"') in s, s)
            if os_name == "Darwin":
                fx.write_cfg("VIBE_TERMINAL=iTerm\n")
                res = fx.vibe("link", "open", _URL, **_dry())
                g = _launch(res.stdout) or []
                check(f"{_VL} iTerm: no 'create window ... command' (it does not run a shell), uses write text",
                      not any(" command " in x for x in g) and any("write text" in x for x in g), str(g))
        finally:
            fx.close(f"ac15-{os_name}")

    # The wrapper really re-checks the folder: execute the argv from a dry run.
    fx = _Fx("Linux")
    try:
        demo = fx.repo("demo sp")
        assert fx.allow(demo, "demo").returncode == 0
        fx.rec("kitty")
        fx.write_cfg("VIBE_TERMINAL=kitty\n")
        res = fx.vibe("link", "open", _URL + "&task=ABBR-4", **_dry())
        got = _launch(res.stdout)
        fake = fx.root / "fakevibe"
        out = fx.root / "fake.out"
        fake.write_text(f"#!/bin/sh\nprintf '%s|' \"$(pwd -P)\" \"$@\" > '{out}'\n")
        fake.chmod(0o755)
        has_wrap = bool(got) and "/bin/sh" in got
        check(f"{_VL} wrapper-exec precondition: the kitty dry run contains /bin/sh", has_wrap, str(got))
        if not has_wrap:
            return
        argv = list(got[got.index("/bin/sh"):])
        argv[argv.index(fx.vibe_path)] = str(fake)
        r = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(f"{_VL} wrapper: with the registered folder (path has a space) it cd's, then execs vibe with --task",
              r.returncode == 0 and out.exists() and out.read_text() == f"{demo}|--task|ABBR-4|", f"{r} {out.read_text() if out.exists() else None}")
        out.unlink(missing_ok=True)
        other = fx.root / "other"
        other.mkdir()
        link = fx.root / "linkdir"
        link.symlink_to(other)
        bad = list(argv)
        bad[bad.index(str(demo))] = str(link)
        r = subprocess.run(bad, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(f"{_VL} wrapper: a path that is now a symlink (pwd -P differs) does NOT exec vibe",
              r.returncode != 0 and not out.exists(), f"{r}")
        bad[bad.index(str(link))] = str(fx.root / "gone")
        r = subprocess.run(bad, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(f"{_VL} wrapper: a vanished path does NOT exec vibe", r.returncode != 0 and not out.exists(), f"{r}")
    finally:
        fx.close("ac15-exec")


# ── AC16 ─────────────────────────────────────────────────────────────────────
def _dialog_shim(fx: _Fx, answer: str = _BTN_OPEN, rc: int = 0, mark: str | None = None) -> None:
    """osascript recorder that, on the display-dialog call, notes whether the
    lock directory exists at that moment."""
    note = f"[ -d '{fx.stamps}/demo.dialog' ] && echo present >> '{mark}'" if mark else ":"
    _shim(fx, "osascript",
          f"printf '@@ osascript\\n' >> '{fx.log}'; for a in \"$@\"; do printf '%s\\n' \"$a\" >> '{fx.log}'; done\n"
          f"case \"$1 $2\" in\n  '-e display dialog'*) {note}; printf '%s\\n' '{answer}'; exit {rc} ;;\nesac\nexit 0\n")


def test_vl_ac16_dialog_lock():
    print(f"\n{_VL} AC16 one dialog at a time")
    fx = _Fx()
    try:
        _setup_demo(fx)
        mark = fx.root / "mark"
        _dialog_shim(fx, mark=str(mark))
        lock = fx.stamps / "demo.dialog"
        res = fx.open(_URL)
        check(f"{_VL} control: a normal dialog open succeeds (dialog + launch)",
              res.returncode == 0 and len(fx.calls("osascript")) == 2, f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} the lock directory existed while the dialog was shown", mark.exists() and "present" in mark.read_text())
        check(f"{_VL} the lock is removed after the dialog (answer Open)", not lock.exists())
        # young lock
        shutil.rmtree(fx.stamps)
        fx.stamps.mkdir(parents=True)
        lock.mkdir()
        fx.log.write_text("")
        res = fx.open(_URL)
        check(f"{_VL} a young .dialog: exit 3 'a confirmation for demo is already open', no dialog",
              res.returncode == 3 and "a confirmation for demo is already open" in res.stderr
              and fx.calls("osascript") == [], f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} the young lock is left alone (not removed by the refused click)", lock.is_dir())
        # 60 s old is still young
        t = time.time() - 60
        os.utime(lock, (t, t))
        res = fx.open(_URL)
        check(f"{_VL} a 60 s old .dialog is still refused (exit 3)", res.returncode == 3 and fx.calls("osascript") == [],
              f"rc={res.returncode}")
        # stale lock replaced
        t = time.time() - 100
        os.utime(lock, (t, t))
        mark.unlink(missing_ok=True)
        res = fx.open(_URL)
        check(f"{_VL} a 100 s old .dialog is stale: replaced, dialog shown, launch ok",
              res.returncode == 0 and len(fx.calls("osascript")) == 2 and mark.exists(), f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} the replaced stale lock is removed afterwards", not lock.exists())
        # removal whatever the answer
        for label, ans, rc in [("Cancel (osascript exit 1)", "", 1), ("timeout", "button returned:, gave up:true", 0),
                               ("osascript error", "execution error", 1)]:
            shutil.rmtree(fx.stamps, ignore_errors=True)
            _dialog_shim(fx, answer=ans, rc=rc, mark=str(mark))
            res = fx.open(_URL)
            check(f"{_VL} dialog {label}: exit 4 and the lock is removed", res.returncode == 4 and not lock.exists(),
                  f"rc={res.returncode} lock={lock.exists()}")
        # dry run creates nothing
        shutil.rmtree(fx.stamps, ignore_errors=True)
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1")
        check(f"{_VL} dry run with a dialog block creates no lock and no stamp",
              res.returncode == 0 and "DRYRUN dialog" in res.stdout and not lock.exists()
              and not (fx.stamps / "demo").exists(), res.stdout + res.stderr)
        # dry run does not refuse on a young lock either (nothing is shown)
        fx.stamps.mkdir(parents=True, exist_ok=True)
        lock.mkdir()
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1")
        check(f"{_VL} dry run leaves a pre-existing lock untouched", lock.is_dir(), res.stdout + res.stderr)
    finally:
        fx.close("ac16")


# ── AC17 ─────────────────────────────────────────────────────────────────────
def test_vl_ac17_rate_limit_fails_closed():
    print(f"\n{_VL} AC17 rate limit fails closed")
    fx = _Fx()
    try:
        _setup_demo(fx)
        stamp = fx.stamps / "demo"
        fx.stamps.mkdir(parents=True)
        stamp.write_text("")
        t = time.time() - 30
        os.utime(stamp, (t, t))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: a readable 30 s old stamp does not limit", res.returncode == 0, f"rc={res.returncode} {res.stderr}")
        # unreadable mtime: shim stat to fail for mtime formats only
        _shim(fx, "stat", 'case "$*" in *%Y*|*%m*) exit 1 ;; esac\n'
                          'for s in /usr/bin/stat /bin/stat; do [ -x "$s" ] && exec "$s" "$@"; done\nexit 1\n')
        t = time.time() - 30
        os.utime(stamp, (t, t))
        n = len(fx.calls("osascript"))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} an existing stamp whose mtime cannot be read counts as limited (exit 3)",
              res.returncode == 3 and len(fx.calls("osascript")) == n, f"rc={res.returncode} {res.stderr}")
        fx.unrec("stat")
        # future stamp, dry-run as well
        t = time.time() + 3600
        os.utime(stamp, (t, t))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} a stamp one hour in the future is limited (exit 3)", res.returncode == 3, f"rc={res.returncode}")
        res = fx.vibe("link", "open", _URL, **_dry())
        check(f"{_VL} a future stamp is limited in dry run too (exit 3, no launch block)",
              res.returncode == 3 and "DRYRUN launch" not in res.stdout, f"rc={res.returncode}")
        # no stamp at all is not limited
        stamp.unlink()
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: no stamp file is not limited", res.returncode == 0, res.stderr)
    finally:
        fx.close("ac17-a")

    # Concurrent noask opens: the stamp is taken under the lock, so exactly one launches.
    for rnd in range(3):
        fx = _Fx()
        try:
            demo = fx.repo("demo")
            fx.write_reg(f"demo={demo}\tnoask\n")
            procs = [subprocess.Popen(["bash", str(VIBE), "link", "open", _URL], env=fx.env(), cwd=fx.work,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(6)]
            rcs = sorted(p.wait() for p in procs)
            for p in procs:
                p.stdout.close()
                p.stderr.close()
            check(f"{_VL} round {rnd}: 6 racing noask opens: exactly one launches, five exit 3",
                  rcs == [0, 3, 3, 3, 3, 3] and len(fx.calls("osascript")) == 1,
                  f"{rcs} launches={len(fx.calls('osascript'))}")
        finally:
            fx.close(f"ac17-race{rnd}")


# ── AC18 ─────────────────────────────────────────────────────────────────────
def test_vl_ac18_link_last_symlinks():
    print(f"\n{_VL} AC18 no symlink following in ~/.vibe/link-last")
    fx = _Fx()
    try:
        _setup_demo(fx)
        reg_before = fx.reg.read_bytes()
        target = fx.root / "elsewhere"
        target.mkdir()
        (target / "keep").write_text("keep")
        fx.stamps.symlink_to(target)
        # (`deny` through a symlinked link-last changed in cycle 3, AC23: see test_vl_ac23_*.)
        for verb, args in [("open", ("link", "open", _URL))]:
            res = fx.vibe(*args, VIBE_LINK_ASSUME="open")
            check(f"{_VL} link-last is a symlink: {verb} exits 5 with a warning, calls nothing",
                  res.returncode == 5 and "⚠" in res.stdout + res.stderr and fx.calls("osascript") == [],
                  f"rc={res.returncode} {res.stderr}")
            check(f"{_VL} {verb} through a symlinked link-last touched nothing behind it",
                  sorted(p.name for p in target.iterdir()) == ["keep"] and (target / "keep").read_text() == "keep"
                  and fx.reg.read_bytes() == reg_before, str(list(target.iterdir())))
        fx.stamps.unlink()
        # symlinked stamp (dangling and to a real file)
        fx.stamps.mkdir()
        victim = fx.root / "victim"
        victim.write_text("v")
        t = time.time() - 3600
        os.utime(victim, (t, t))
        (fx.stamps / "demo").symlink_to(victim)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} a symlinked stamp: open exits 5 with a warning and no launch",
              res.returncode == 5 and "⚠" in res.stdout + res.stderr and fx.calls("osascript") == [],
              f"rc={res.returncode} {res.stderr}")
        check(f"{_VL} the symlinked stamp's target was neither touched nor rewritten",
              victim.read_text() == "v" and abs(victim.stat().st_mtime - t) < 2)
        (fx.stamps / "demo").unlink()
        ghost = fx.root / "ghost"
        (fx.stamps / "demo").symlink_to(ghost)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} a dangling stamp symlink: exit 5 and the target is not created",
              res.returncode == 5 and not ghost.exists(), f"rc={res.returncode}")
        (fx.stamps / "demo").unlink()
        # symlinked dialog lock
        (fx.stamps / "demo.dialog").symlink_to(target)
        _dialog_shim(fx)
        res = fx.open(_URL)
        check(f"{_VL} a symlinked dialog lock: exit 5 and no dialog",
              res.returncode == 5 and fx.calls("osascript") == [], f"rc={res.returncode} {res.stderr}")
        (fx.stamps / "demo.dialog").unlink()
        # control
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: with the symlinks gone the open works", res.returncode == 0, res.stderr)
    finally:
        fx.close("ac18")


# ── AC19 ─────────────────────────────────────────────────────────────────────
def test_vl_ac19_registry_ownership_and_size():
    print(f"\n{_VL} AC19 registry ownership, ~/.vibe write bits, size")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: owned, 600, 700 dir registry opens", res.returncode == 0, res.stderr)
        n = len(fx.calls("osascript"))
        # Ownership: shim stat so `%u` reports another user; all other formats pass through.
        _shim(fx, "stat", 'case "$*" in *%u*) echo 4242; exit 0 ;; esac\n'
                          'for s in /usr/bin/stat /bin/stat; do [ -x "$s" ] && exec "$s" "$@"; done\nexit 1\n')
        shutil.rmtree(fx.stamps, ignore_errors=True)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} registry owned by another uid (stat shim): open exits 5 with a warning, no launch",
              res.returncode == 5 and "⚠" in res.stdout + res.stderr and len(fx.calls("osascript")) == n,
              f"rc={res.returncode} {res.stderr}")
        res = fx.vibe("link", "list")
        check(f"{_VL} registry owned by another uid: list prints (none), exit 0",
              res.returncode == 0 and "(none)" in res.stdout and "demo" not in res.stdout, res.stdout)
        fx.unrec("stat")
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: without the stat shim the same registry is usable again", res.returncode == 0, res.stderr)
        # ~/.vibe group/other write
        for mode in (0o775, 0o757, 0o777):
            shutil.rmtree(fx.stamps, ignore_errors=True)
            fx.reg.parent.chmod(mode)
            res = fx.open(_URL, VIBE_LINK_ASSUME="open")
            lst = fx.vibe("link", "list")
            fx.reg.parent.chmod(0o700)
            check(f"{_VL} ~/.vibe mode {oct(mode)}: open exits 5 with a warning, list prints (none)",
                  res.returncode == 5 and "⚠" in res.stdout + res.stderr and "(none)" in lst.stdout and "demo" not in lst.stdout,
                  f"rc={res.returncode} {res.stderr} {lst.stdout}")
        fx.reg.parent.chmod(0o755)
        shutil.rmtree(fx.stamps, ignore_errors=True)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: ~/.vibe mode 755 (no group/other write) is fine", res.returncode == 0, res.stderr)
        # Size boundary
        def reg_lines(total):
            return f"demo={demo}\n" + "".join(f"fill{i}=/tmp/fill{i}\n" for i in range(total - 1))
        shutil.rmtree(fx.stamps, ignore_errors=True)
        fx.write_reg(reg_lines(1000))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: exactly 1000 lines is accepted", res.returncode == 0, f"rc={res.returncode} {res.stderr[:200]}")
        shutil.rmtree(fx.stamps, ignore_errors=True)
        fx.write_reg(reg_lines(1001))
        n = len(fx.calls("osascript"))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        lst = fx.vibe("link", "list")
        check(f"{_VL} 1001 lines: open exits 5 with a warning, no launch",
              res.returncode == 5 and "⚠" in res.stdout + res.stderr and len(fx.calls("osascript")) == n,
              f"rc={res.returncode} {res.stderr[:200]}")
        check(f"{_VL} 1001 lines: list prints (none)", lst.returncode == 0 and "(none)" in lst.stdout and "demo" not in lst.stdout,
              lst.stdout[:200])
    finally:
        fx.close("ac19")


# ── AC20 ─────────────────────────────────────────────────────────────────────
def test_vl_ac20_assume_only_from_environment():
    print(f"\n{_VL} AC20 VIBE_LINK_ASSUME is read only from the environment")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        for line in ("VIBE_LINK_ASSUME=open", "export VIBE_LINK_ASSUME=always", 'VIBE_LINK_ASSUME="open"'):
            fx.write_cfg(line + "\n")
            res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1")
            check(f"{_VL} config line `{line}`: the dialog block still appears (dry run)",
                  res.returncode == 0 and [b[0] for b in _blocks(res.stdout)] == ["dialog", "launch"],
                  res.stdout + res.stderr)
        fx.write_cfg("VIBE_LINK_ASSUME=always\n")
        _dialog_shim(fx, answer="", rc=1)
        res = fx.open(_URL)
        check(f"{_VL} real run, config says always, dialog says Cancel: exit 4 and no noask written",
              res.returncode == 4 and fx.reg.read_text() == f"demo={demo}\n" and len(fx.calls("osascript")) == 1,
              f"rc={res.returncode} {fx.reg.read_text()!r}")
        # control: the same value from the environment is honoured
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: VIBE_LINK_ASSUME=open from the environment suppresses the dialog block",
              res.returncode == 0 and [b[0] for b in _blocks(res.stdout)] == ["launch"], res.stdout + res.stderr)
        # the environment wins over a config line
        fx.write_cfg("VIBE_LINK_ASSUME=open\n")
        res = fx.open(_URL, VIBE_LINK_ASSUME="cancel")
        check(f"{_VL} environment cancel beats a config `open` (exit 4)", res.returncode == 4, f"rc={res.returncode}")
        fx.write_cfg("FOO=1\n")
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="always")
        check(f"{_VL} control: environment always still rewrites the line with noask (dry run)",
              res.returncode == 0 and fx.reg.read_text() == f"demo={demo}\tnoask\n", fx.reg.read_text())
    finally:
        fx.close("ac20")


# ── AC21 ─────────────────────────────────────────────────────────────────────
def test_vl_ac21_uuid_task_ids():
    print(f"\n{_VL} AC21 bare UUID task ids")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        v = fx.vibe_path
        upper = _SENTINEL_UUID.upper()
        mixed = "123E4567-e89b-12D3-a456-426614174000"
        for u in (_SENTINEL_UUID, upper, mixed):
            res = fx.vibe("link", "open", f"{_URL}&task={u}", **_dry())
            check(f"{_VL} link task={u} is accepted and passed through unchanged",
                  res.returncode == 0 and _launch(res.stdout) == _exp("Darwin", "Terminal", demo, v, u),
                  res.stdout + res.stderr)
        # still accepted: the older forms
        res = fx.vibe("link", "open", f"{_URL}&task=taskandeye://node/{upper}", **_dry())
        check(f"{_VL} control: taskandeye://node/<UPPER uuid> and ABBR-1 still accepted",
              res.returncode == 0 and _launch(res.stdout) == _exp("Darwin", "Terminal", demo, v, f"taskandeye://node/{upper}"),
              res.stdout + res.stderr)
        bad = {
            "one char short": _SENTINEL_UUID[:-1],
            "one char long": _SENTINEL_UUID + "0",
            "non-hex g": "g23e4567-e89b-12d3-a456-426614174000",
            "no hyphens": _SENTINEL_UUID.replace("-", ""),
            "wrong group length": "123e456-7e89b-12d3-a456-426614174000",
            "trailing slash": _SENTINEL_UUID + "/",
            "leading slash": "/" + _SENTINEL_UUID,
            "other scheme": "node://" + _SENTINEL_UUID,
        }
        for label, u in bad.items():
            shutil.rmtree(fx.stamps, ignore_errors=True)
            n = len(fx.calls())
            res = fx.open(f"{_URL}&task={u}", VIBE_LINK_ASSUME="open")
            check(f"{_VL} link task is refused ({label}): exit 2 'refused URL', no recorder call",
                  res.returncode == 2 and "refused URL" in res.stderr and len(fx.calls()) == n,
                  f"rc={res.returncode} {res.stderr}")
        res = fx.open(f"{_URL}&task={upper}", VIBE_LINK_ASSUME="open")
        c = fx.calls("osascript")
        check(f"{_VL} real run: the recorder sees the upper-case UUID unchanged inside --task",
              res.returncode == 0 and len(c) == 1 and f"'{upper}'" in c[0][1][1], f"rc={res.returncode} {c}")
    finally:
        fx.close("ac21-link")

    # `vibe --task <ref>`: an unknown flag after it stops parsing with a distinct message
    # once the task ref has been accepted; a bad ref stops at the --task message.
    fx = _Fx()
    try:
        for u in (_SENTINEL_UUID, _SENTINEL_UUID.upper(), "123E4567-e89b-12D3-a456-426614174000"):
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            msg = res.stdout + res.stderr
            check(f"{_VL} vibe --task {u}: ref accepted (parser reaches the unknown flag)",
                  res.returncode == 1 and "--task needs" not in msg and "--no-such-flag-zzz" in msg, msg)
        for u in ("ABBR-12", f"taskandeye://node/{_SENTINEL_UUID}"):
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            check(f"{_VL} control: vibe --task {u} still accepted",
                  "--task needs" not in res.stdout + res.stderr and "--no-such-flag-zzz" in res.stdout + res.stderr,
                  res.stdout + res.stderr)
        for u in (_SENTINEL_UUID[:-1], _SENTINEL_UUID + "0", "g23e4567-e89b-12d3-a456-426614174000",
                  _SENTINEL_UUID.replace("-", "")):   # rev 6 AC19: usable ids, now accepted
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            msg = res.stdout + res.stderr
            check(f"{_VL} vibe --task {u}: accepted as a usable id (parser reaches the unknown flag)",
                  res.returncode == 1 and "--task needs" not in msg and "--no-such-flag-zzz" in msg, msg)
        for u in ("{" + _SENTINEL_UUID + "}", "a b", "a'b", "-x", "a" * 201):
            res = fx.vibe("--task", u, "--no-such-flag-zzz")
            check(f"{_VL} vibe --task {u}: rejected with '--task needs'",
                  res.returncode == 1 and "--task needs" in res.stdout + res.stderr, res.stdout + res.stderr)
        res = fx.vibe("--task", _SENTINEL_UUID, "--task", _SENTINEL_UUID.upper(), "--no-such-flag-zzz")
        check(f"{_VL} two --task UUIDs: still 'Only one --task binding'",
              "Only one --task binding" in res.stdout + res.stderr, res.stdout + res.stderr)
    finally:
        fx.close("ac21-cli")


# ═════════════════════════════════════════════════════════════════════════════
# Cycle 3 (rev 5 addendum): AC22 - AC29  (AC30 is an internal refactor with no
# behaviour change beyond AC1-AC29, so it has no test of its own)
# ═════════════════════════════════════════════════════════════════════════════
_UP_UUID = "123E4567-E89B-12D3-A456-426614174000"
_LO_UUID = _UP_UUID.lower()
_MIX_UUID = "123E4567-e89b-12D3-a456-426614174000"
_CLIENT_JS = r'''
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
const mod = await import(pathToFileURL(process.argv[1]).href);
const root = mkdtempSync(join(tmpdir(), 'vl-ac22-'));
execFileSync('git', ['init', '-q'], { cwd: root });
mkdirSync(join(root, '.vibe'), { mode: 0o700 });
writeFileSync(join(root, '.vibe', 'taskandi.json'), JSON.stringify({ endpoint: 'https://fixture.invalid/mcp', task: 'task-1' }));
try { const c = mod.loadConfig(root); console.log('OK ' + c.task); }
catch (e) { console.log('ERR ' + e.message); }
'''


def test_vl_ac22_uuid_task_end_to_end():
    print(f"\n{_VL} AC22 UUID task ids accepted by the Task&I client and the supervisor")
    client = VIBE.parent / "devcontainer" / "taskandi-client.mjs"
    sup = VIBE.parent / "devcontainer" / "codex-supervisor.mjs"
    base = {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")}

    def load(ref):
        env = dict(base)
        if ref is not None:
            env["VIBE_TASK_REF"] = ref
        r = subprocess.run(["node", "--input-type=module", "-e", _CLIENT_JS, str(client)], env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        lines = [l for l in r.stdout.splitlines() if l.startswith(("OK ", "ERR "))]
        return lines[0] if lines else (r.stdout + r.stderr).strip()
    check(f"{_VL} control: no VIBE_TASK_REF -> loadConfig returns the configured task", load(None) == "OK task-1", load(None))
    check(f"{_VL} control: VIBE_TASK_REF=ABBR-12 accepted", load("ABBR-12") == "OK ABBR-12", load("ABBR-12"))
    for u in (_LO_UUID, _UP_UUID, _MIX_UUID):
        out = load(u)
        check(f"{_VL} loadConfig with VIBE_TASK_REF={u} returns that UUID as the task", out == f"OK {u}", out)
    for label, u in [("one char short", _LO_UUID[:-1]), ("non-hex", "g" + _LO_UUID[1:]),
                     ("no hyphens", _LO_UUID.replace("-", "")), ("braced", "{" + _LO_UUID + "}")]:
        out = load(u)
        check(f"{_VL} loadConfig still rejects a malformed UUID ({label})", out.startswith("ERR"), out)
    # The supervisor's launch-binding check is an inline constructor test, not
    # exported and not reachable without starting a Codex run; so test the
    # regex literal it uses, extracted from the source, in node.
    src = sup.read_text()
    m = re.search(r"if \(this\.taskRef && !(/\^.*?\$/)\.test\(this\.taskRef\)\) throw usageError\('invalid launch task binding'\)", src)
    check(f"{_VL} found the supervisor's launch-binding regex literal", m is not None)
    if m:
        js = ("const re = " + m.group(1) + "; const out = {}; "
              "for (const v of JSON.parse(process.argv[1])) out[v] = re.test(v); console.log(JSON.stringify(out));")
        vals = [_LO_UUID, _UP_UUID, _MIX_UUID, "ABBR-12", f"taskandeye://node/{_LO_UUID}",
                _LO_UUID[:-1], "g" + _LO_UUID[1:], _LO_UUID.replace("-", ""), "x y", ""]
        r = subprocess.run(["node", "-e", js, json.dumps(vals)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        try:
            got = json.loads(r.stdout)
        except ValueError:
            got = {}
        for v in vals[:5]:
            check(f"{_VL} supervisor binding regex accepts {v!r}", got.get(v) is True, r.stdout + r.stderr)
        for v in vals[5:]:
            want = v not in ("x y", "")   # rev 6 AC19: other usable ids are accepted
            check(f"{_VL} supervisor binding regex {'accepts' if want else 'rejects'} {v!r}", got.get(v) is want, r.stdout + r.stderr)


# -- AC23 ---------------------------------------------------------------------
def test_vl_ac23_deny_always_withdraws_consent():
    print(f"\n{_VL} AC23 deny withdraws consent even with symlinks in link-last")
    for label in ("folder", "stamp", "lock"):
        fx = _Fx()
        try:
            _setup_demo(fx)
            target = fx.root / "elsewhere"
            target.mkdir()
            (target / "keep").write_text("keep")
            victim = fx.root / "victim"
            victim.write_text("v")
            if label == "folder":
                fx.stamps.symlink_to(target)
                link = fx.stamps
            else:
                fx.stamps.mkdir()
                link = fx.stamps / ("demo" if label == "stamp" else "demo.dialog")
                link.symlink_to(victim if label == "stamp" else target)
            res = fx.vibe("link", "deny", "demo")
            out = res.stdout + res.stderr
            check(f"{_VL} {label} symlink: deny exits 0 and removes the registry line",
                  res.returncode == 0 and "demo=" not in fx.reg.read_text(), f"rc={res.returncode} {out} {fx.reg.read_text()!r}")
            check(f"{_VL} {label} symlink: a warning names the symlink", "⚠" in out and str(link) in out, out)
            check(f"{_VL} {label} symlink: the symlink and its target are untouched",
                  link.is_symlink() and (target / "keep").read_text() == "keep" and victim.read_text() == "v"
                  and sorted(p.name for p in target.iterdir()) == ["keep"], out)
            lst = fx.vibe("link", "list")
            check(f"{_VL} {label} symlink: list no longer shows demo", "demo" not in lst.stdout, lst.stdout)
            # open stays refused for a re-registered project (exit 5), as before
            fx.write_reg(f"demo={fx.proj / 'demo'}\n")
            res = fx.open(_URL, VIBE_LINK_ASSUME="open")
            check(f"{_VL} {label} symlink: open still refuses with exit 5", res.returncode == 5 and "⚠" in res.stdout + res.stderr
                  and fx.calls("osascript") == [], f"rc={res.returncode} {res.stderr}")
        finally:
            fx.close(f"ac23-{label}")
    # control: no symlink, deny is silent success
    fx = _Fx()
    try:
        _setup_demo(fx)
        res = fx.vibe("link", "deny", "demo")
        check(f"{_VL} control: plain deny exits 0 with no warning", res.returncode == 0 and "⚠" not in res.stdout + res.stderr,
              res.stdout + res.stderr)
    finally:
        fx.close("ac23-ctl")


# -- AC24 ---------------------------------------------------------------------
def test_vl_ac24_stale_lock_race():
    print(f"\n{_VL} AC24 racing stale-lock replacement")
    for rnd in range(3):
        fx = _Fx()
        try:
            _setup_demo(fx)
            _shim(fx, "osascript",
                  f"printf '@@ osascript\\n' >> '{fx.log}'; for a in \"$@\"; do printf '%s\\n' \"$a\" >> '{fx.log}'; done\n"
                  f"case \"$1 $2\" in\n  '-e display dialog'*) sleep 1; printf '%s\\n' '{_BTN_OPEN}' ;;\nesac\nexit 0\n")
            fx.stamps.mkdir(parents=True)
            lock = fx.stamps / "demo.dialog"
            lock.mkdir()
            t = time.time() - 120
            os.utime(lock, (t, t))
            procs = [subprocess.Popen(["bash", str(VIBE), "link", "open", _URL], env=fx.env(), cwd=fx.work,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(6)]
            rcs = sorted(p.wait() for p in procs)
            for p in procs:
                p.stdout.close()
                p.stderr.close()
            dialogs = [c for c in fx.calls("osascript") if c[1] and c[1][1].startswith("display dialog")]
            launches = [c for c in fx.calls("osascript") if "do script" in " ".join(c[1])]
            check(f"{_VL} round {rnd}: 6 racers on a stale lock: at most one dialog and one launch",
                  len(dialogs) <= 1 and len(launches) <= 1, f"rcs={rcs} dialogs={len(dialogs)} launches={len(launches)}")
            check(f"{_VL} round {rnd}: every racer exits 0 (winner) or 3 (held), none crash",
                  all(r in (0, 3) for r in rcs) and rcs.count(0) <= 1, f"{rcs}")
            check(f"{_VL} round {rnd}: no lock or .stale.* leftovers",
                  not lock.exists() and not [p for p in fx.stamps.iterdir() if ".stale." in p.name],
                  str(sorted(p.name for p in fx.stamps.iterdir())))
        finally:
            fx.close(f"ac24-{rnd}")
    # positive control: a single open over a stale lock replaces it and works
    fx = _Fx()
    try:
        _setup_demo(fx)
        _dialog_shim(fx)
        fx.stamps.mkdir(parents=True)
        (fx.stamps / "demo.dialog").mkdir()
        t = time.time() - 120
        os.utime(fx.stamps / "demo.dialog", (t, t))
        res = fx.open(_URL)
        check(f"{_VL} control: a lone open over a 120 s stale lock succeeds (dialog + launch)",
              res.returncode == 0 and len(fx.calls("osascript")) == 2, f"rc={res.returncode} {res.stderr}")
        # _link_unlock only removes the lock this process created: a lock that
        # another process re-created while the dialog was up must survive.
        lock = fx.stamps / "demo.dialog"
        shutil.rmtree(fx.stamps, ignore_errors=True)
        fx.stamps.mkdir(parents=True)
        _shim(fx, "osascript",
              f"printf '@@ osascript\\n' >> '{fx.log}'; for a in \"$@\"; do printf '%s\\n' \"$a\" >> '{fx.log}'; done\n"
              f"case \"$1 $2\" in\n  '-e display dialog'*) rm -rf '{lock}'; mkdir '{lock}'; : > '{lock}/other-owner';"
              f" printf '%s\\n' '{_BTN_OPEN}' ;;\nesac\nexit 0\n")
        res = fx.open(_URL)
        check(f"{_VL} a lock replaced by another owner during the dialog is not removed by this process",
              lock.is_dir() and (lock / "other-owner").exists(), f"rc={res.returncode} exists={lock.exists()} {res.stderr}")
    finally:
        fx.close("ac24-ctl")


# -- AC25 ---------------------------------------------------------------------
def test_vl_ac25_writers_use_full_usability_check():
    print(f"\n{_VL} AC25 allow/deny refuse a registry that open would refuse")
    def snapshot(fx):
        return fx.reg.read_bytes()
    cases = []
    cases.append(("foreign owner (stat shim)", "foreign"))
    cases.append(("~/.vibe group/other writable", "dirmode"))
    cases.append(("more than 1000 lines", "big"))
    for label, kind in cases:
        fx = _Fx()
        try:
            demo = _setup_demo(fx)
            other = fx.repo("other")
            if kind == "big":
                fx.write_reg(f"demo={demo}\n" + "".join(f"fill{i}=/tmp/fill{i}\n" for i in range(1001)))
            elif kind == "dirmode":
                fx.reg.parent.chmod(0o777)
            else:
                _shim(fx, "stat", 'case "$*" in *%u*) echo 4242; exit 0 ;; esac\n'
                                  'for s in /usr/bin/stat /bin/stat; do [ -x "$s" ] && exec "$s" "$@"; done\nexit 1\n')
            before = snapshot(fx)
            res = fx.allow(other, "other")
            check(f"{_VL} {label}: allow exits 5 with a warning, registry untouched",
                  res.returncode == 5 and "⚠" in res.stdout + res.stderr and snapshot(fx) == before,
                  f"rc={res.returncode} {res.stderr[:200]}")
            res = fx.vibe("link", "deny", "demo")
            check(f"{_VL} {label}: deny exits 5 with a warning, registry untouched",
                  res.returncode == 5 and "⚠" in res.stdout + res.stderr and snapshot(fx) == before,
                  f"rc={res.returncode} {res.stderr[:200]}")
            # control: back to a good state, writers work again
            if kind == "dirmode":
                fx.reg.parent.chmod(0o700)
            elif kind == "foreign":
                fx.unrec("stat")
            else:
                fx.write_reg(f"demo={demo}\n")
            res = fx.allow(other, "other")
            check(f"{_VL} {label}: control: once the registry is usable allow succeeds", res.returncode == 0, res.stderr[:200])
        finally:
            fx.close(f"ac25-{kind}")
    # only the loose-mode case is still repaired
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        fx.reg.chmod(0o644)
        res = fx.allow(fx.repo("other"), "other")
        check(f"{_VL} a 644 registry is still repaired by allow (exit 0, 'now trusted')",
              res.returncode == 0 and "now trusted" in res.stdout + res.stderr
              and stat.S_IMODE(fx.reg.stat().st_mode) == 0o600, f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac25-644")


# -- AC26 ---------------------------------------------------------------------
def test_vl_ac26_owner_unreadable_registry():
    print(f"\n{_VL} AC26 owner-unreadable registry")
    if os.geteuid() == 0:
        print(f"  SKIP (running as root: chmod 200 does not make the file unreadable)")
        return
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: readable registry opens", res.returncode == 0, res.stderr)
        shutil.rmtree(fx.stamps, ignore_errors=True)
        n = len(fx.calls("osascript"))
        fx.reg.chmod(0o200)
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        msg = res.stdout + res.stderr
        check(f"{_VL} mode 200: open exits 5 with a warning, no launch",
              res.returncode == 5 and "⚠" in msg and len(fx.calls("osascript")) == n, f"rc={res.returncode} {msg}")
        check(f"{_VL} mode 200: no raw bash error text", "Permission denied" not in msg and "line " not in msg.split("⚠")[0], msg)
        lst = fx.vibe("link", "list")
        check(f"{_VL} mode 200: list prints (none), exit 0, no raw bash error",
              lst.returncode == 0 and "(none)" in lst.stdout and "Permission denied" not in lst.stdout + lst.stderr,
              f"rc={lst.returncode} {lst.stdout}{lst.stderr}")
        fx.reg.chmod(0o600)
    finally:
        fx.close("ac26")


# -- AC27 ---------------------------------------------------------------------
def test_vl_ac27_future_dated_recoverable():
    print(f"\n{_VL} AC27 future-dated stamps and locks")
    fx = _Fx()
    try:
        _setup_demo(fx)
        fx.stamps.mkdir(parents=True)
        stamp = fx.stamps / "demo"
        stamp.write_text("")
        t = time.time() + 3600
        os.utime(stamp, (t, t))
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} future stamp: exit 3, message names the stamp path, says it is dated in the future and to delete it",
              res.returncode == 3 and str(stamp) in res.stderr and "dated in the future" in res.stderr and "delete" in res.stderr
              and fx.calls("osascript") == [], f"rc={res.returncode} {res.stderr}")
        stamp.unlink()
        res = fx.open(_URL, VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: after deleting it as advised the open runs", res.returncode == 0, res.stderr)
        # future lock > 70 s ahead is stale and replaced
        shutil.rmtree(fx.stamps, ignore_errors=True)
        fx.stamps.mkdir(parents=True)
        lock = fx.stamps / "demo.dialog"
        lock.mkdir()
        os.utime(lock, (time.time() + 3600, time.time() + 3600))
        _dialog_shim(fx)
        fx.log.write_text("")
        res = fx.open(_URL)
        check(f"{_VL} a lock dated 1 h in the future counts as stale: replaced, dialog shown, launch ok",
              res.returncode == 0 and len(fx.calls("osascript")) == 2 and not lock.exists(), f"rc={res.returncode} {res.stderr}")
    finally:
        fx.close("ac27")


# -- AC28 ---------------------------------------------------------------------
def test_vl_ac28_linear_registry_load():
    print(f"\n{_VL} AC28 a 1000-line registry loads in one pass")
    fx = _Fx()
    try:
        demo = _setup_demo(fx)
        fill = "".join(f"fill{i}=/tmp/fill{i}\n" for i in range(999))
        fx.write_reg(fill + f"demo={demo}\n")
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="open")
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
            if res.returncode != 0:
                break
        check(f"{_VL} 1000-line registry: dry-run open exits 0 with a launch block", res.returncode == 0 and "DRYRUN launch" in res.stdout,
              f"rc={res.returncode} {res.stderr[:200]}")
        print(f"  INFO AC28 best-of-3 wall time for a 1000-line open: {best:.2f}s")
        check(f"{_VL} 1000-line registry open completes in under 2 s (spec: 1 s; best of 3 = {best:.2f}s)", best < 2.0, f"{best:.2f}s")
        # duplicate detection still works at scale (first and last line collide)
        fx.write_reg(f"demo={demo}\n" + "".join(f"fill{i}=/tmp/fill{i}\n" for i in range(998)) + f"demo={demo}\n")
        lines = fx.reg.read_text().count("\n")
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="open")
        check(f"{_VL} duplicate names {lines - 1} lines apart: ignored with a warning, exit 2",
              res.returncode == 2 and "⚠" in res.stdout + res.stderr, f"rc={res.returncode} {res.stderr[:200]}")
        # the 1000th line is still read (the cap is not off by one)
        fx.write_reg(fill + f"demo={demo}\n")
        res = fx.vibe("link", "open", _URL, VIBE_LINK_DRY_RUN="1", VIBE_LINK_ASSUME="open")
        check(f"{_VL} control: the 1000th line is honoured", res.returncode == 0, res.stderr[:200])
    finally:
        fx.close("ac28")


# -- AC29 ---------------------------------------------------------------------
def test_vl_ac29_unknown_dialog_rate_limit():
    print(f"\n{_VL} AC29 unknown-project dialogs are rate-limited globally")
    fx = _Fx()
    try:
        _setup_demo(fx)
        res = fx.open("vibe://open?project=nothere")
        c = fx.calls("osascript")
        check(f"{_VL} first unknown name: exit 2 and exactly one dialog", res.returncode == 2 and len(c) == 1
              and "No vibe project called nothere." in c[0][1][1], f"rc={res.returncode} {c}")
        res = fx.open("vibe://open?project=other-ghost")
        check(f"{_VL} second unknown name within 5 s: exit 2, stderr message only, no recorder call",
              res.returncode == 2 and "no vibe project called" in res.stderr and len(fx.calls("osascript")) == 1,
              f"rc={res.returncode} {res.stderr} calls={len(fx.calls('osascript'))}")
        res = fx.open("vibe://open?project=nothere")
        check(f"{_VL} the same name again within 5 s is suppressed too (global, not per name)",
              res.returncode == 2 and len(fx.calls("osascript")) == 1, f"rc={res.returncode}")
        stamp = fx.stamps / ".unknown"
        check(f"{_VL} the global stamp ~/.vibe/link-last/.unknown exists", stamp.exists())
        if stamp.exists():
            t = time.time() - 10
            os.utime(stamp, (t, t))
            res = fx.open("vibe://open?project=third-ghost")
            c = fx.calls("osascript")
            check(f"{_VL} control: with the stamp 10 s old the next unknown name shows a dialog",
                  res.returncode == 2 and len(c) == 2 and "No vibe project called third-ghost." in c[1][1][1],
                  f"rc={res.returncode} {c}")
        # an unknown name does not consume a known project's per-project stamp or vice versa
        res = fx.open("vibe://open?project=demo", VIBE_LINK_ASSUME="open")
        check(f"{_VL} a known project still opens right after an unknown-name click", res.returncode == 0, res.stderr)
    finally:
        fx.close("ac29")
