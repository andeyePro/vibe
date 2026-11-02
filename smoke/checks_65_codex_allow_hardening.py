"""task_068: `~/.vibe/codex-allow` hardened to the link registry's standard
(shared _vibe_consent_registry_check). Ownership is faked with a `stat` PATH
shim that answers only `%u` (as checks_49 does); decisions are observed through
`vibe codex list`, codex_allowed and _codex_opted_in. Mode-200 cases are
skipped as root. Message strings below are literals copied from the pre-task
launcher, so they pin "byte for byte"."""
import re

from smoke._core import *
from smoke._core import _source_vibe_call
from smoke.checks_17_delegation import _codex_git_ws, _codex_docker_stub

_CX = "[codex-harden]"
_ROOT = os.geteuid() == 0
_STAT_SHIM = ('#!/bin/sh\ncase "$*" in *%u*) echo 4242; exit 0 ;; esac\n'
              'for s in /usr/bin/stat /bin/stat; do [ -x "$s" ] && exec "$s" "$@"; done\nexit 1\n')
_STAT_NOMODE_SHIM = ('#!/bin/sh\ncase "$*" in *%a*|*%Lp*) exit 1 ;; esac\n'
                     'for s in /usr/bin/stat /bin/stat; do [ -x "$s" ] && exec "$s" "$@"; done\nexit 1\n')


class _Fx:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.vdir = self.home / ".vibe"
        self.reg = self.vdir / "codex-allow"
        self.link = self.vdir / "link-projects"
        self.ws = _codex_git_ws(self.root)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        _codex_docker_stub(self.bin, self.root / "docker.log")
        self.shimmed = False

    def close(self):
        self.vdir.chmod(0o700) if self.vdir.exists() else None
        self._td.cleanup()

    def shim(self, body=_STAT_SHIM):
        p = self.bin / "stat"
        p.write_text(body)
        p.chmod(0o755)

    def unshim(self):
        (self.bin / "stat").unlink()

    def env(self):
        return {**os.environ, "HOME": str(self.home), "VIBE_CONFIG": f"{self.home}/no-config",
                "PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}

    def vibe(self, *args, cwd=None, umask=None):
        if umask:
            return run(["bash", "-c", f'umask {umask}; exec bash "$0" "$@"', str(VIBE), *args],
                       env=self.env(), cwd=cwd or self.ws, input="")
        return run(["bash", str(VIBE), *args], env=self.env(), cwd=cwd or self.ws, input="")

    def call(self, expr):
        r = _source_vibe_call({"HOME": str(self.home), "PATH": self.env()["PATH"]},
                              f'if {expr}; then echo "RC=0"; else echo "RC=$?"; fi')
        m = re.search(r"RC=(\d+)", r.stdout)
        return (int(m.group(1)) if m else -1), r

    def write_reg(self, lines=None, mode=0o600, final_newline=True, dirmode=0o700):
        self.vdir.mkdir(exist_ok=True)
        self.vdir.chmod(0o700)
        lines = [str(self.ws)] if lines is None else lines
        self.reg.write_text("\n".join(lines) + ("\n" if final_newline else ""))
        self.reg.chmod(mode)
        self.vdir.chmod(dirmode)

    def listed(self):
        r = self.vibe("codex", "list")
        return r


def _msgs(f, dmode="775"):
    d = os.path.dirname(f)
    return {
        "symlink": f"  ⚠ {f} is a symlink — ignored, so no project counts as allowed (the Codex opt-in registry must be a real file on this machine; delete the symlink and re-run 'vibe codex allow').",
        "nomode": f"  ⚠ {f} permissions could not be read — ignored, so no project counts as allowed (fail closed).",
        "loose": f"  ⚠ {f} is readable or writable by group or others (mode 644) — ignored, so no project counts as allowed; run 'chmod 600 {f}' on the Mac.",
        "foreign": f"  ⚠ {f} is not owned by you (or its owner could not be read) — ignored, so no project counts as allowed (fail closed).",
        "unreadable": f"  ⚠ {f} cannot be read — ignored, so no project counts as allowed; run 'chmod 600 {f}' on the Mac.",
        "dirw": f"  ⚠ {d} is writable by group or others (mode {dmode}) — ignored, so no project counts as allowed; run 'chmod go-w {d}' on the Mac.",
        "notreg": f"  ⚠ {f} is not a regular file — ignored, so no project counts as allowed; remove it and re-run 'vibe codex allow'.",
        "unknown": f"  ⚠ {f} could not be checked — ignored (fail closed).",
        "cap": f"  ⚠ {f} has more than 1000 lines — ignored, so no project counts as allowed.",
    }


def _refused_observed(fx, line, label, marker=True):
    """Every observable of a refusal: list, codex_allowed, _codex_opted_in."""
    r = fx.listed()
    check(f"{_CX} {label}: `vibe codex list` prints (none), exit 0, exact line",
          r.returncode == 0 and "(none)" in r.stdout and str(fx.ws) not in r.stdout and line in r.stderr.splitlines(),
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    rc, r = fx.call(f"codex_allowed {shlex.quote(str(fx.ws))}")
    check(f"{_CX} {label}: codex_allowed false for a listed project, exact line",
          rc == 1 and line in r.stderr.splitlines(), f"rc={rc} err={r.stderr!r}")
    if marker:
        (fx.ws / ".vibe-allow-codex").write_text("")
        rc, r = fx.call(f"_codex_opted_in {shlex.quote(str(fx.ws))}")
        (fx.ws / ".vibe-allow-codex").unlink()
        check(f"{_CX} {label}: _codex_opted_in false", rc == 1 and line in r.stderr.splitlines(), f"rc={rc} err={r.stderr!r}")


def _accepted(fx, label):
    r = fx.listed()
    rc, r2 = fx.call(f"codex_allowed {shlex.quote(str(fx.ws))}")
    check(f"{_CX} {label}: control accepted (listed, allowed, silent)",
          str(fx.ws) in r.stdout and rc == 0 and r.stderr == "" and r2.stderr == "",
          f"out={r.stdout!r} err={r.stderr!r} {r2.stderr!r} rc={rc}")


# ── AC1 ──────────────────────────────────────────────────────────────────────
def test_cx_ac1_foreign_owner():
    print(f"\n{_CX} AC1 foreign-owned registry")
    fx = _Fx()
    try:
        fx.write_reg()
        _accepted(fx, "AC1 owned")
        fx.shim()
        _refused_observed(fx, _msgs(str(fx.reg))["foreign"], "AC1 foreign owner (stat shim)")
        fx.unshim()
        _accepted(fx, "AC1 shim removed")
    finally:
        fx.close()


# ── AC2 ──────────────────────────────────────────────────────────────────────
def test_cx_ac2_unreadable_dir_cap():
    print(f"\n{_CX} AC2 unreadable, writable ~/.vibe, line cap")
    fx = _Fx()
    try:
        m = _msgs(str(fx.reg))
        if _ROOT:
            print(f"{_CX} skipping mode-200 case: running as root")
        else:
            fx.write_reg(mode=0o200)
            _refused_observed(fx, m["unreadable"], "AC2 mode 200")
            fx.reg.chmod(0o600)
            _accepted(fx, "AC2 mode 200 restored")
        for dm in (0o775, 0o757, 0o777):
            fx.write_reg(dirmode=dm)
            _refused_observed(fx, _msgs(str(fx.reg), oct(dm)[2:])["dirw"], f"AC2 ~/.vibe {oct(dm)[2:]} (AC12 mode text)")
        for dm in (0o755, 0o700, 0o705):
            fx.write_reg(dirmode=dm)
            _accepted(fx, f"AC2 ~/.vibe {oct(dm)[2:]}")
        fx.write_reg()
        fill = [f"/nowhere/p{i}" for i in range(1, 1001)]
        for nl in (True, False):
            tag = "with" if nl else "without"
            fx.write_reg([str(fx.ws)] + fill[:999], final_newline=nl)  # 1000 lines
            _accepted(fx, f"AC2 1000 lines {tag} trailing newline")
            fx.write_reg([str(fx.ws)] + fill[:1000], final_newline=nl)  # 1001 lines
            _refused_observed(fx, m["cap"], f"AC2 1001 lines {tag} trailing newline")
    finally:
        fx.close()


# ── helper reason codes ──────────────────────────────────────────────────────
def test_cx_helper_reason_codes():
    print(f"\n{_CX} _vibe_consent_registry_check reason codes")
    fx = _Fx()
    try:
        f = shlex.quote(str(fx.reg))

        def chk(args=""):
            rc, r = fx.call(f'_c=$(_vibe_consent_registry_check {f} {args}); echo "CODE=$_c"; [ "$_c" = ok ] || [ "$_c" = missing ]')
            m = re.search(r"CODE=(\S*)", r.stdout)
            return (m.group(1) if m else None), rc, r

        fx.vdir.mkdir()
        fx.vdir.chmod(0o700)
        code, rc, r = chk()
        check(f"{_CX} helper: missing -> 'missing', usable, silent", code == "missing" and rc == 0 and r.stderr == "", f"{code} {rc} {r.stderr!r}")
        fx.write_reg()
        code, rc, r = chk()
        check(f"{_CX} helper: good file -> 'ok'", code == "ok" and rc == 0, f"{code} {rc}")
        fx.reg.chmod(0o644)
        code, rc, r = chk()
        check(f"{_CX} helper: 644 -> 'loose_mode', unusable, prints no warning", code == "loose_mode" and rc == 1 and r.stderr == "", f"{code} {rc} {r.stderr!r}")
        code, rc, r = chk("writer")
        check(f"{_CX} helper: 644 with writer -> 'ok'", code == "ok" and rc == 0, f"{code} {rc}")
        fx.reg.chmod(0o600)
        fx.shim()
        code, rc, r = chk()
        check(f"{_CX} helper: foreign owner -> 'foreign_owner'", code == "foreign_owner" and rc == 1, f"{code} {rc}")
        code, rc, r = chk("writer")
        check(f"{_CX} helper: foreign owner still refused for writer", code == "foreign_owner" and rc == 1, f"{code} {rc}")
        fx.shim(_STAT_NOMODE_SHIM)
        code, rc, r = chk()
        check(f"{_CX} helper: unreadable mode -> 'mode_unreadable'", code == "mode_unreadable" and rc == 1, f"{code} {rc}")
        fx.unshim()
        fx.vdir.chmod(0o775)
        code, rc, r = chk("writer")
        check(f"{_CX} helper: group-writable dir -> 'dir_writable' (also for writer)", code == "dir_writable" and rc == 1, f"{code} {rc}")
        fx.vdir.chmod(0o700)
        fx.reg.unlink()
        fx.reg.symlink_to(fx.home / "target")
        code, rc, r = chk()
        check(f"{_CX} helper: dangling symlink -> 'symlink'", code == "symlink" and rc == 1, f"{code} {rc}")
        if not _ROOT:
            fx.reg.unlink()
            fx.write_reg(mode=0o200)
            code, rc, r = chk()
            check(f"{_CX} helper: mode 200 -> 'unreadable'", code == "unreadable" and rc == 1, f"{code} {rc}")
    finally:
        fx.close()


# ── AC3 ──────────────────────────────────────────────────────────────────────
def test_cx_ac3_writers_refuse():
    print(f"\n{_CX} AC3 allow / deny / codex_allow_remove refuse")
    fx = _Fx()
    try:
        m = _msgs(str(fx.reg))
        other = _codex_git_ws(fx.root, "other")
        cases = []
        cases.append(("foreign owner", lambda: (fx.write_reg(), fx.shim()), m["foreign"]))
        cases.append(("775 ~/.vibe", lambda: (fx.unshim() if (fx.bin / "stat").exists() else None, fx.write_reg(dirmode=0o775)), m["dirw"]))
        cases.append(("1001 lines", lambda: (fx.unshim() if (fx.bin / "stat").exists() else None,
                                              fx.write_reg([str(fx.ws)] + [f"/n/p{i}" for i in range(1000)])), m["cap"]))
        for label, setup, line in cases:
            setup()
            before = fx.reg.read_bytes()
            bmode = fx.reg.stat().st_mode
            r = fx.vibe("codex", "allow", str(other))
            check(f"{_CX} AC3 allow refused ({label}): exit 1, exact line, file byte-identical",
                  r.returncode == 1 and line in r.stderr.splitlines() and fx.reg.read_bytes() == before
                  and fx.reg.stat().st_mode == bmode, f"rc={r.returncode} {r.stderr!r}")
            r = fx.vibe("codex", "deny")
            check(f"{_CX} AC3 deny refused ({label}): exit 1, new line plus 'unusable' line, untouched",
                  r.returncode == 1 and line in r.stderr.splitlines() and "unusable" in r.stderr
                  and fx.reg.read_bytes() == before, f"rc={r.returncode} {r.stderr!r}")
            rc, r = fx.call(f"codex_allow_remove {shlex.quote(str(fx.ws))}")
            check(f"{_CX} AC3 codex_allow_remove direct refused ({label}): returns 1, exact line, untouched",
                  rc == 1 and line in r.stderr.splitlines() and fx.reg.read_bytes() == before, f"rc={rc} {r.stderr!r}")
        if (fx.bin / "stat").exists():
            fx.unshim()
        # positive controls on a clean registry
        fx.write_reg()
        _codex_git_ws_other = _codex_git_ws(fx.root, "other2")
        r = fx.vibe("codex", "allow", str(_codex_git_ws_other))
        check(f"{_CX} AC3 control: allow on a clean registry appends", r.returncode == 0 and str(_codex_git_ws_other) in fx.reg.read_text(), r.stderr)
        rc, r = fx.call(f"codex_allow_remove {shlex.quote(str(_codex_git_ws_other))}")
        check(f"{_CX} AC3 control: codex_allow_remove removes the line", rc == 0 and str(_codex_git_ws_other) not in fx.reg.read_text()
              and str(fx.ws) in fx.reg.read_text(), r.stderr)
        # 644 repaired by allow
        fx.write_reg(mode=0o644)
        r = fx.vibe("codex", "allow")
        check(f"{_CX} AC3 allow still repairs a 644 file to 600",
              r.returncode == 0 and (fx.reg.stat().st_mode & 0o777) == 0o600, f"rc={r.returncode} {r.stderr!r}")
        # 644 deny: today's refusal
        fx.write_reg(mode=0o644)
        before = fx.reg.read_bytes()
        r = fx.vibe("codex", "deny")
        check(f"{_CX} AC3 deny still refuses a 644 file with today's messages",
              r.returncode == 1 and m["loose"] in r.stderr.splitlines() and "unusable" in r.stderr
              and fx.reg.read_bytes() == before and (fx.reg.stat().st_mode & 0o777) == 0o644, f"rc={r.returncode} {r.stderr!r}")
        # missing file: idempotent
        fx.reg.unlink()
        rc, r = fx.call(f"codex_allow_remove {shlex.quote(str(fx.ws))}")
        check(f"{_CX} AC3 codex_allow_remove on a missing file returns 0, silent, creates nothing",
              rc == 0 and r.stderr == "" and not fx.reg.exists(), f"rc={rc} {r.stderr!r}")
        # missing file inside a 775 dir: remove still 0
        fx.vdir.chmod(0o775)
        rc, r = fx.call(f"codex_allow_remove {shlex.quote(str(fx.ws))}")
        check(f"{_CX} AC3 codex_allow_remove on a missing file in a 775 dir still returns 0", rc == 0 and r.stderr == "", f"rc={rc} {r.stderr!r}")
        # missing registry in group-writable dir is usable (documented), first allow creates it
        rc, r = fx.call("codex_registry_usable")
        check(f"{_CX} missing registry in a 775 ~/.vibe is usable and silent", rc == 0 and r.stderr == "", f"rc={rc} {r.stderr!r}")
        fx.vdir.chmod(0o700)
        # allow on a symlinked registry keeps today's message
        tgt = fx.home / "tgt"
        tgt.write_text("keep\n")
        fx.reg.symlink_to(tgt)
        r = fx.vibe("codex", "allow")
        check(f"{_CX} allow through a symlink: today's 'refusing to write through it', target untouched",
              r.returncode == 1 and f"  ⚠ {fx.reg} is a symlink — refusing to write through it." in r.stderr.splitlines()
              and tgt.read_text() == "keep\n", f"rc={r.returncode} {r.stderr!r}")
    finally:
        fx.close()


# ── AC4 ──────────────────────────────────────────────────────────────────────
def test_cx_ac4_umask_dir():
    print(f"\n{_CX} AC4 umask 002 with no ~/.vibe")
    fx = _Fx()
    try:
        probe = fx.root / "probe"
        run(["bash", "-c", f'umask 002; mkdir -p {shlex.quote(str(probe))}'])
        check(f"{_CX} AC4 positive control: a plain `mkdir -p` under umask 002 is group-writable",
              probe.stat().st_mode & 0o020 != 0, oct(probe.stat().st_mode))
        check(f"{_CX} AC4 precondition: no ~/.vibe yet", not fx.vdir.exists())
        r = fx.vibe("codex", "allow", umask="002")
        check(f"{_CX} AC4 allow under umask 002 succeeds", r.returncode == 0, r.stderr)
        check(f"{_CX} AC4 the created ~/.vibe has no group/other write",
              fx.vdir.is_dir() and fx.vdir.stat().st_mode & 0o022 == 0, oct(fx.vdir.stat().st_mode))
        r = fx.vibe("codex", "list")
        check(f"{_CX} AC4 a following `vibe codex list` shows the project, no warnings",
              r.returncode == 0 and str(fx.ws) in r.stdout and "⚠" not in r.stderr, f"{r.stdout!r} {r.stderr!r}")
        # a pre-existing group-writable dir is NOT silently altered by allow (it is refused instead)
        fx.vdir.chmod(0o775)
        before = fx.reg.read_bytes()
        r = fx.vibe("codex", "allow", umask="002")
        check(f"{_CX} AC4 an existing 775 ~/.vibe is refused, not chmod'ed",
              r.returncode == 1 and (fx.vdir.stat().st_mode & 0o777) == 0o775 and fx.reg.read_bytes() == before, r.stderr)
    finally:
        fx.close()


# ── AC5 ──────────────────────────────────────────────────────────────────────
def test_cx_ac5_existing_messages_literal():
    print(f"\n{_CX} AC5 existing message literals")
    fx = _Fx()
    try:
        m = _msgs(str(fx.reg))
        fx.vdir.mkdir()
        fx.vdir.chmod(0o700)
        fx.reg.symlink_to(fx.home / "t")
        rc, r = fx.call("codex_registry_usable")
        check(f"{_CX} AC5 codex symlink line literal", rc == 1 and r.stderr.splitlines() == [m["symlink"]], r.stderr)
        fx.reg.unlink()
        fx.write_reg(mode=0o644)
        rc, r = fx.call("codex_registry_usable")
        check(f"{_CX} AC5 codex loose-mode line literal (mode 644)", rc == 1 and r.stderr.splitlines() == [m["loose"]], r.stderr)
        fx.reg.chmod(0o600)
        fx.shim(_STAT_NOMODE_SHIM)
        rc, r = fx.call("codex_registry_usable")
        check(f"{_CX} AC5 codex permissions-unreadable line literal", rc == 1 and r.stderr.splitlines() == [m["nomode"]], r.stderr)
        fx.unshim()

        # link registry: every message, usable + writer variants
        lf = "~/.vibe/link-projects"
        L = {
            "symlink": f"  ⚠ {lf} is a symlink — ignored, so no project can be opened from a link (it must be a real file; delete it and re-run 'vibe link allow').",
            "nomode": f"  ⚠ {lf} permissions could not be read — ignored (fail closed).",
            "loose": f"  ⚠ {lf} is readable or writable by group or others (mode 644) — ignored; run 'chmod 600 {lf}' or 'vibe link allow' again.",
            "foreign": f"  ⚠ {lf} is not owned by you (or its owner could not be read) — ignored (fail closed).",
            "unreadable": f"  ⚠ {lf} cannot be read — ignored (fail closed); run 'chmod 600 {lf}'.",
            "dirw": f"  ⚠ ~/.vibe is writable by group or others (mode 775) — {lf} ignored; run 'chmod go-w ~/.vibe'.",
            "cap": f"  ⚠ {lf} has more than 1000 lines — ignored (fail closed).",
        }

        def lcall(arg=""):
            return fx.call(f"_link_registry_usable {arg}")

        def lwrite(mode=0o600, dirmode=0o700):
            fx.vdir.chmod(0o700)
            fx.link.write_text("demo=/nowhere\n")
            fx.link.chmod(mode)
            fx.vdir.chmod(dirmode)

        if fx.link.exists() or fx.link.is_symlink():
            fx.link.unlink()
        rc, r = lcall()
        check(f"{_CX} AC5 link: missing is usable, silent", rc == 0 and r.stderr == "", r.stderr)
        fx.link.symlink_to(fx.home / "t")
        for arg in ("", "writer"):
            rc, r = lcall(arg)
            check(f"{_CX} AC5 link symlink literal ({arg or 'reader'})", rc == 1 and r.stderr.splitlines() == [L["symlink"]], r.stderr)
        fx.link.unlink()
        lwrite(0o644)
        rc, r = lcall()
        check(f"{_CX} AC5 link loose-mode literal", rc == 1 and r.stderr.splitlines() == [L["loose"]], r.stderr)
        rc, r = lcall("writer")
        check(f"{_CX} AC5 link loose mode is accepted for a writer, silent", rc == 0 and r.stderr == "", r.stderr)
        lwrite()
        fx.shim(_STAT_NOMODE_SHIM)
        rc, r = lcall()
        check(f"{_CX} AC5 link mode-unreadable literal", rc == 1 and r.stderr.splitlines() == [L["nomode"]], r.stderr)
        fx.shim()
        for arg in ("", "writer"):
            rc, r = lcall(arg)
            check(f"{_CX} AC5 link foreign-owner literal ({arg or 'reader'})", rc == 1 and r.stderr.splitlines() == [L["foreign"]], r.stderr)
        fx.unshim()
        if not _ROOT:
            lwrite(0o200)
            rc, r = lcall()
            check(f"{_CX} AC5 link unreadable literal", rc == 1 and r.stderr.splitlines() == [L["unreadable"]], r.stderr)
        lwrite(dirmode=0o775)
        for arg in ("", "writer"):
            rc, r = lcall(arg)
            check(f"{_CX} AC5 link dir-writable literal ({arg or 'reader'}, mode 775)", rc == 1 and r.stderr.splitlines() == [L["dirw"]], r.stderr)
        lwrite()
        rc, r = lcall()
        check(f"{_CX} AC5 link control: good registry usable, silent", rc == 0 and r.stderr == "", r.stderr)
        fx.vdir.chmod(0o700)
        fx.link.write_text("".join(f"n{i}=/nowhere/{i}\n" for i in range(1001)))
        fx.link.chmod(0o600)
        r = fx.vibe("link", "list")
        check(f"{_CX} AC5 link 1001-line cap literal via `vibe link list`", L["cap"] in r.stderr.splitlines(), f"{r.stdout!r} {r.stderr!r}")
    finally:
        fx.close()


# ── AC7 ──────────────────────────────────────────────────────────────────────
def _fn_body(src, name):
    m = re.search(rf"^{re.escape(name)}\(\) \{{\n(.*?)^\}}$", src, re.M | re.S)
    return m.group(1) if m else None


def test_cx_ac7_shared_helper_static():
    print(f"\n{_CX} AC7 shared helper, no duplicated stat logic")
    src = VIBE.read_text()
    n = len(re.findall(r"^_vibe_consent_registry_check\(\) \{$", src, re.M))
    check(f"{_CX} AC7 _vibe_consent_registry_check() defined exactly once", n == 1, str(n))
    helper = _fn_body(src, "_vibe_consent_registry_check")
    check(f"{_CX} AC7 helper body is found and non-trivial (uses _link_mode and _link_owner)",
          helper is not None and "_link_mode" in helper and "_link_owner" in helper, str(helper)[:80])
    check(f"{_CX} AC7 _link_mode and _link_owner still defined once each, not renamed",
          len(re.findall(r"^_link_mode\(\) \{$", src, re.M)) == 1 and len(re.findall(r"^_link_owner\(\) \{$", src, re.M)) == 1)
    for fn in ("codex_registry_usable", "_link_registry_usable"):
        body = _fn_body(src, fn)
        check(f"{_CX} AC7 {fn} body found", body is not None)
        if body is None:
            continue
        code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
        check(f"{_CX} AC7 {fn} calls the helper", "_vibe_consent_registry_check" in code)
        check(f"{_CX} AC7 {fn} has no `stat` word on code lines", re.search(r"\bstat\b", code) is None,
              str(re.findall(r".*\bstat\b.*", code)))
        check(f"{_CX} AC7 {fn} has no `id -u`", "id -u" not in code)
    # negative control for the regex itself
    check(f"{_CX} AC7 control: the stat regex does fire on `stat -c %a x`", re.search(r"\bstat\b", "mode=$(stat -c %a x)") is not None)
    check(f"{_CX} AC7 control: `_link_mode` is not matched as stat", re.search(r"\bstat\b", "mode=$(_link_mode x)") is None)


# ── AC9 ──────────────────────────────────────────────────────────────────────
def test_cx_ac9_allow_refuses_writable_dir_without_file():
    print(f"\n{_CX} AC9 allow with a 775 ~/.vibe and no registry")
    fx = _Fx()
    try:
        fx.vdir.mkdir()
        fx.vdir.chmod(0o775)
        r = fx.vibe("codex", "allow")
        check(f"{_CX} AC9 exit 1 with the dir_writable line (mode 775)",
              r.returncode == 1 and _msgs(str(fx.reg))["dirw"] in r.stderr.splitlines(), f"rc={r.returncode} {r.stderr!r}")
        check(f"{_CX} AC9 no registry created, dir mode unchanged",
              not fx.reg.exists() and (fx.vdir.stat().st_mode & 0o777) == 0o775, oct(fx.vdir.stat().st_mode))
        fx.vdir.chmod(0o700)
        r = fx.vibe("codex", "allow")
        check(f"{_CX} AC9 control: same state with a 700 dir succeeds and creates the file",
              r.returncode == 0 and fx.reg.exists(), r.stderr)
    finally:
        fx.close()


# ── AC10 ─────────────────────────────────────────────────────────────────────
def test_cx_ac10_not_regular():
    import socket
    print(f"\n{_CX} AC10 non-regular registry paths")
    fx = _Fx()
    try:
        fx.vdir.mkdir()
        fx.vdir.chmod(0o700)
        line = _msgs(str(fx.reg))["notreg"]
        kinds = []
        kinds.append(("directory", lambda: fx.reg.mkdir(0o700)))
        kinds.append(("FIFO", lambda: os.mkfifo(fx.reg, 0o600)))

        def mksock():
            s = socket.socket(socket.AF_UNIX)
            s.bind(str(fx.reg))
            return s
        kinds.append(("socket", mksock))
        for name, mk in kinds:
            keep = None
            try:
                keep = mk()
            except OSError as e:
                print(f"{_CX} AC10 skipping {name}: cannot create ({e})")
                continue
            try:
                try:
                    r = subprocess.run(["bash", str(VIBE), "codex", "list"], env=fx.env(), cwd=fx.ws,
                                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
                except subprocess.TimeoutExpired:
                    check(f"{_CX} AC10 {name}: `vibe codex list` returns within 10 s", False, "timed out (hang)")
                    continue
                check(f"{_CX} AC10 {name}: list prints (none), exit 0, not_regular line, no crash text",
                      r.returncode == 0 and "(none)" in r.stdout and line in r.stderr.splitlines()
                      and "Is a directory" not in r.stderr, f"rc={r.returncode} {r.stdout!r} {r.stderr!r}")
                rc, r2 = fx.call(f"codex_allowed {shlex.quote(str(fx.ws))}")
                check(f"{_CX} AC10 {name}: codex_allowed false, exact line", rc == 1 and line in r2.stderr.splitlines(), f"{rc} {r2.stderr!r}")
                try:
                    r3 = subprocess.run(["bash", str(VIBE), "codex", "allow"], env=fx.env(), cwd=fx.ws,
                                        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
                    check(f"{_CX} AC10 {name}: allow refuses with exit 1", r3.returncode == 1 and line in r3.stderr.splitlines(), f"{r3.returncode} {r3.stderr!r}")
                except subprocess.TimeoutExpired:
                    check(f"{_CX} AC10 {name}: allow returns within 10 s", False, "timed out (hang)")
            finally:
                if keep is not None:
                    keep.close()
                if fx.reg.is_dir() and not fx.reg.is_symlink():
                    fx.reg.rmdir()
                else:
                    fx.reg.unlink()
        # link registry as a directory
        L = "  ⚠ ~/.vibe/link-projects is not a regular file — ignored (fail closed); remove it and re-run 'vibe link allow'."
        fx.link.mkdir()
        rc, r = fx.call("_link_registry_usable")
        check(f"{_CX} AC10 link registry as a directory: literal line, unusable", rc == 1 and r.stderr.splitlines() == [L], r.stderr)
        rc, r = fx.call("_link_registry_usable writer")
        check(f"{_CX} AC10 link registry directory refused for writers too", rc == 1 and r.stderr.splitlines() == [L], r.stderr)
        fx.link.rmdir()
        # control: a regular file is fine
        fx.write_reg()
        _accepted(fx, "AC10 regular file")
    finally:
        fx.close()


# ── AC11 ─────────────────────────────────────────────────────────────────────
def test_cx_ac11_unknown_code_fails_closed():
    print(f"\n{_CX} AC11 unknown helper codes fail closed")
    fx = _Fx()
    try:
        fx.write_reg()
        want = _msgs(str(fx.reg))["unknown"]
        for code in ("bogus", ""):
            stub = f'_vibe_consent_registry_check() {{ echo "{code}"; return 1; }}; '
            rc, r = fx.call(stub + "codex_registry_usable")
            check(f"{_CX} AC11 codex wrapper, code {code!r}: returns 1 with the unknown line",
                  rc == 1 and want in r.stderr.splitlines(), f"{rc} {r.stderr!r}")
            rc, r = fx.call(stub + "codex_allowed " + shlex.quote(str(fx.ws)))
            check(f"{_CX} AC11 codex_allowed, code {code!r}: false (no grant)", rc == 1, f"{rc} {r.stderr!r}")
            rc, r = fx.call(stub + "_link_registry_usable")
            lw = "  ⚠ ~/.vibe/link-projects could not be checked — ignored (fail closed)."
            lw2 = f"  ⚠ {fx.link} could not be checked — ignored (fail closed)."
            check(f"{_CX} AC11 link wrapper, code {code!r}: returns 1 with an unknown-code line",
                  rc == 1 and any(l in (lw, lw2) for l in r.stderr.splitlines()), f"{rc} {r.stderr!r}")
        # a code that returns 0 but is not ok/missing is still refused
        rc, r = fx.call('_vibe_consent_registry_check() { echo weird; return 0; }; codex_registry_usable')
        check(f"{_CX} AC11 code 'weird' with return 0 is still refused", rc == 1 and want in r.stderr.splitlines(), f"{rc} {r.stderr!r}")
        # no stray abort under set -e: the line prints (checked above) and exit is clean RC=1 (not -1)
        # seam, when present
        rc, r = fx.call(f"declare -F _vibe_consent_reason_message >/dev/null && _vibe_consent_reason_message {shlex.quote(str(fx.reg))} bogus")
        if rc == 0:
            check(f"{_CX} AC11 seam _vibe_consent_reason_message prints the unknown line for 'bogus'",
                  want in r.stderr.splitlines() + r.stdout.splitlines(), f"{r.stdout!r} {r.stderr!r}")
        # controls
        _accepted(fx, "AC11 real helper")
    finally:
        fx.close()


def test_cx_ac11_source_level():
    print(f"\n{_CX} AC11 source-level fail-closed shape")
    src = VIBE.read_text()
    cap = 'reason="$(_vibe_consent_registry_check "$f" "$writer")" || true'
    for fn in ("codex_registry_usable", "_link_registry_usable"):
        body = _fn_body(src, fn) or ""
        lines = [l for l in body.splitlines() if not l.lstrip().startswith("#")]
        code = "\n".join(lines)
        check(f"{_CX} AC11 {fn} captures the reason with `|| true`", cap in code)
        m = re.search(r"^    \*\)\n(.*?)^      ;;\n", code, re.M | re.S)
        branch = m.group(1) if m else ""
        check(f"{_CX} AC11 {fn} has a `*)` branch printing 'could not be checked — ignored (fail closed)' and returning 1",
              "could not be checked — ignored (fail closed)" in branch and re.search(r"^\s+return 1$", branch, re.M) is not None, branch)
        check(f"{_CX} AC11 {fn} `*)` branch does not return 0", "return 0" not in branch)
        bad = []
        for i, l in enumerate(lines):
            if "return 0" not in l:
                continue
            ok_branch = re.match(r"^    (missing|ok|missing\|ok)\).*return 0 ;;$", l) is not None
            final = l == "  return 0" and i == len(lines) - 1
            if not (ok_branch or final):
                bad.append(l)
        check(f"{_CX} AC11 {fn}: `return 0` only in the missing/ok branches (or the final tail)", not bad, str(bad))
        check(f"{_CX} AC11 {fn}: a missing/ok branch with `return 0` exists",
              re.search(r"^    (missing|missing\|ok)\) return 0 ;;$", code, re.M) is not None)
    # control: the regex rejects a stray return 0 in a error branch
    check(f"{_CX} AC11 control: a stray `    symlink) return 0 ;;` would be flagged",
          re.match(r"^    (missing|ok|missing\|ok)\).*return 0 ;;$", "    symlink) return 0 ;;") is None)
