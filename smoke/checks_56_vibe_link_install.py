"""`vibe link --install | --uninstall | --status` (task_063): register vibe://
with macOS (a local ad-hoc-signed applet) and Linux (.desktop), exercised
black-box through the launcher with PATH shims for every external tool, a temp
HOME and a temp TMPDIR. Reuses the fixture of checks_48_vibe_link.

Control convention: refusal tests sit beside a positive control; a comment
says what each would report if the mechanism under test were missing.
"""
import hashlib
import re
import shutil
import stat
import subprocess

from smoke._core import *
from smoke.checks_48_vibe_link import _Fx

_VI = "[vibe-link-install]"
_TOOLS = ("osacompile", "PlistBuddy", "codesign", "lsregister", "xdg-mime", "update-desktop-database")
_TEMPLATE = REPO / "devcontainer" / "link" / "VibeLink.applescript"
_MY_ID = "com.andeye.vibe.link"
_PB = "-c"

_PRIOR = ("Set :CFBundleIdentifier com.andeye.vibe.link", 'Set :CFBundleName "Vibe Link"',
          "Add :LSUIElement bool true", "Add :CFBundleURLTypes array", "Add :CFBundleURLTypes:0 dict",
          "Add :CFBundleURLTypes:0:CFBundleURLName string com.andeye.vibe.link",
          "Add :CFBundleURLTypes:0:CFBundleURLSchemes array",
          "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string vibe")


def _pb_cmds(launcher: str) -> list:
    return list(_PRIOR) + [f'Add :VibeLauncherPath string "{launcher}"']


class _IFx(_Fx):
    def __init__(self, os_name: str = "Darwin", tools=_TOOLS):
        super().__init__(os_name)
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.pbv = self.root / "pbvals"
        self.pbv.mkdir()
        for t in tools:
            self.tool(t)
        self.tool("mv", delegate="/bin/mv")

    # -- shims ---------------------------------------------------------------
    def tool(self, name: str, delegate: str | None = None) -> None:
        head = (f"{{ printf '@@ %s\\n' '{name}'; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> '{self.log}'\n"
                f"[ \"$SHIM_FAIL\" = '{name}' ] && exit 1\n")
        if name == "osacompile":
            body = ('out=; src=\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) src="$1"; shift;; esac; done\n'
                    'mkdir -p "$out/Contents/Resources/Scripts" || exit 1\n'
                    "printf '%s' '<?xml version=\"1.0\"?><plist><dict><key>CFBundleIdentifier</key>"
                    "<string>com.apple.ScriptEditor.id.x</string><key>CFBundleName</key><string>x</string></dict></plist>'"
                    ' > "$out/Contents/Info.plist"\n'
                    ': > "$out/Contents/Resources/Scripts/main.scpt"\n'
                    f'cp "$src" \'{self.root}/osa-source\'\nexit 0\n')
        elif name == "PlistBuddy":
            body = ('cmd="$2"; file="$3"\ncase "$cmd" in\n'
                    f'  "Print :"*) key="${{cmd#Print :}}"; [ -f "$file" ] || exit 1\n'
                    f'     f=\'{self.pbv}/\'"$key"; [ -f "$f" ] && {{ cat "$f"; exit 0; }}; exit 1 ;;\n'
                    '  "Set "*) [ -n "$SHIM_PB_FAIL_SET" ] && exit 1 ;;\nesac\nexit 0\n')
        elif name == "xdg-mime":
            body = (f'if [ "$1" = query ]; then cat \'{self.root}/xdg-query\' 2>/dev/null; fi\nexit 0\n')
        elif delegate:
            body = f'exec {delegate} "$@"\n'
        else:
            body = "exit 0\n"
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + head + body)
        p.chmod(0o755)

    def pbval(self, key: str, val: str) -> None:
        (self.pbv / key).write_text(val + "\n")

    def xdg_query(self, val: str) -> None:
        (self.root / "xdg-query").write_text(val + "\n")

    # -- running -------------------------------------------------------------
    def env(self, **extra) -> dict:
        e = super().env(**extra)
        e.setdefault("TMPDIR", str(self.tmp))
        for k in ("SHIM_FAIL", "SHIM_PB_FAIL_SET", "XDG_DATA_HOME", "VIBE_LINK_DRY_RUN"):
            if k not in extra:
                e.pop(k, None)
        return e

    def link(self, *args, launcher=None, **extra):
        v = str(launcher) if launcher else str(VIBE)
        return run(["bash", v, "link", *args], env=self.env(**extra), cwd=self.work)

    def stage(self, dirname: str, executable: bool = True) -> Path:
        d = self.root / "copies" / dirname
        d.mkdir(parents=True)
        shutil.copy2(VIBE, d / "vibe")
        (d / "devcontainer").symlink_to(REPO / "devcontainer")
        if not executable:
            (d / "vibe").chmod(0o644)
        return d / "vibe"

    # -- paths ---------------------------------------------------------------
    @property
    def apps(self) -> Path:
        return self.home / "Applications"

    @property
    def target(self) -> Path:
        return self.apps / "Vibe Link.app"

    @property
    def desk_dir(self) -> Path:
        return self.home / ".local" / "share" / "applications"

    @property
    def desk(self) -> Path:
        return self.desk_dir / "vibe-link.desktop"

    def make_bundle(self, ident: str | None = _MY_ID, plist: bool = True, launcher: str | None = None) -> Path:
        (self.target / "Contents").mkdir(parents=True)
        (self.target / "marker.txt").write_text("old bundle\n")
        if plist:
            (self.target / "Contents" / "Info.plist").write_text("<plist/>")
        if ident is not None:
            self.pbval("CFBundleIdentifier", ident)
        if launcher is not None:
            self.pbval("VibeLauncherPath", launcher)
        return self.target

    def names(self) -> list:
        return [c[0] for c in self.calls()]


def _tree(p: Path) -> dict:
    out = {}
    p = Path(p)
    if not os.path.lexists(p):
        return {".": "ABSENT"}
    if p.is_symlink() or p.is_file():
        return {".": ("L", os.readlink(p)) if p.is_symlink() else ("F", hashlib.sha256(p.read_bytes()).hexdigest())}
    for d, ds, fs in os.walk(p):
        for n in ds + fs:
            f = Path(d) / n
            rel = str(f.relative_to(p))
            if f.is_symlink():
                out[rel] = ("L", os.readlink(f))
            elif f.is_dir():
                out[rel] = ("D",)
            else:
                out[rel] = ("F", hashlib.sha256(f.read_bytes()).hexdigest())
    return out


def _world(fx: _IFx) -> dict:
    return {"home": _tree(fx.home), "tmp": _tree(fx.tmp)}


def _out(res) -> str:
    return res.stdout + res.stderr


def _template(launcher: str) -> str:
    return _TEMPLATE.read_text().replace("@@VIBE@@", launcher)


def _desktop(launcher: str) -> str:
    return ("[Desktop Entry]\nVersion=1.0\nType=Application\nName=Vibe Link\n"
            f'Exec="{launcher}" link-open %u\nTerminal=false\nNoDisplay=true\n'
            "MimeType=x-scheme-handler/vibe;\n")


def _exec_words(value: str) -> list:
    """Split a desktop-entry Exec value: double quotes group, backslash
    escapes the next char inside quotes, unquoted spaces separate."""
    words, cur, inq, i, have = [], "", False, 0, False
    while i < len(value):
        c = value[i]
        if inq:
            if c == "\\" and i + 1 < len(value):
                cur += value[i + 1]
                i += 1
            elif c == '"':
                inq = False
            else:
                cur += c
        elif c == '"':
            inq, have = True, True
        elif c == " ":
            if have or cur:
                words.append(cur)
            cur, have = "", False
        else:
            cur += c
        i += 1
    if have or cur:
        words.append(cur)
    return words


def _dry_blocks(out: str) -> list:
    """[(label, [argv...], extra{})] in print order; the source block carries
    path and lines."""
    res = []
    for line in out.split("\n"):
        if line.startswith("DRYRUN "):
            res.append([line[7:], [], {"path": None, "lines": []}])
        elif res and line.startswith("  argv: "):
            res[-1][1].append(line[8:])
        elif res and line.startswith("  path: "):
            res[-1][2]["path"] = line[8:]
        elif res and line.startswith("  | "):
            res[-1][2]["lines"].append(line[4:])
    return res


def _isbase(a: str, tool: str) -> bool:
    return a == tool or a.endswith("/" + tool)


# ── AC1 ──────────────────────────────────────────────────────────────────────
def test_vli_ac1_darwin_dry_run():
    print(f"\n{_VI} AC1 Darwin dry run")
    fx = _IFx("Darwin", tools=())  # NO tool shims: the dry run skips presence checks
    try:
        before = _world(fx)
        res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
        check(f"{_VI} dry run with no tools on PATH: exit 0", res.returncode == 0, _out(res)[:300])
        blocks = _dry_blocks(res.stdout)
        known = ("osacompile", "plistbuddy", "codesign", "lsregister-u", "rm", "mv", "lsregister", "source")
        labels = [b[0] for b in blocks if b[0] in known]
        check(f"{_VI} labels in design order, no lsregister-u/rm without an existing bundle",
              labels == ["osacompile"] + ["plistbuddy"] * 9 + ["codesign", "mv", "lsregister", "source"], str(labels))
        v = str(VIBE.resolve())
        app = None
        by = {}
        for b in blocks:
            by.setdefault(b[0], []).append(b)
        try:
            o = by["osacompile"][0][1]
            app = o[2]
            ok = (len(o) == 4 and _isbase(o[0], "osacompile") and o[1] == "-o" and app.endswith("/Vibe Link.app")
                  and o[3].endswith("VibeLink.applescript") and os.path.dirname(app) == os.path.dirname(o[3]))
            check(f"{_VI} osacompile argv: -o '<tmp>/Vibe Link.app' '<tmp>/VibeLink.applescript'", ok, str(o))
            plist = app + "/Contents/Info.plist"
            got = [b[1] for b in by["plistbuddy"]]
            want = [[_PB, c, plist] for c in _pb_cmds(v)]
            check(f"{_VI} nine plistbuddy blocks: -c strings verbatim, plist path last",
                  all(_isbase(g[0], "PlistBuddy") and g[1:] == w for g, w in zip(got, want)) and len(got) == 9, str(got))
            c = by["codesign"][0][1]
            check(f"{_VI} codesign argv --force --deep --sign - <app>",
                  _isbase(c[0], "codesign") and c[1:] == ["--force", "--deep", "--sign", "-", app], str(c))
            tgt = str(fx.target)
            m = by["mv"][0][1]
            check(f"{_VI} mv argv: <tmp app> then target", _isbase(m[0], "mv") and m[-2:] == [app, tgt], str(m))
            l = by["lsregister"][0][1]
            check(f"{_VI} lsregister -f <target>", _isbase(l[0], "lsregister") and l[1:] == ["-f", tgt], str(l))
            src = by["source"][0]
            check(f"{_VI} DRYRUN source: path is the destination ('<tgt>' or its script)",
                  src[2]["path"] is not None and src[2]["path"].startswith(str(fx.home)) or src[2]["path"] == tgt, str(src[2]["path"]))
            check(f"{_VI} DRYRUN source lines equal the template with @@VIBE@@ replaced",
                  "\n".join(src[2]["lines"]).rstrip("\n") == _template(v).rstrip("\n"), "\n".join(src[2]["lines"])[:300])
            check(f"{_VI} source block is last", blocks[-1][0] == "source", str([b[0] for b in blocks]))
        except (KeyError, IndexError) as e:
            check(f"{_VI} dry run printed every expected block", False, f"{e!r} {res.stdout[:300]}")
        check(f"{_VI} nothing created under HOME or TMPDIR", _world(fx) == before, "world changed")
        check(f"{_VI} no external tool was run", fx.names() == [], str(fx.names()))

        # existing vibe bundle -> lsregister-u + rm appear between codesign and mv (PlistBuddy shim answers the read)
        fx.tool("PlistBuddy")
        fx.make_bundle(_MY_ID)
        before = _world(fx)
        res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
        labels = [b[0] for b in _dry_blocks(res.stdout) if b[0] in known]
        check(f"{_VI} existing vibe bundle: reinstall order (mv to sibling, lsregister-u, mv, mv, lsregister, rm); exit 0",
              res.returncode == 0 and labels == ["osacompile"] + ["plistbuddy"] * 9 + ["codesign", "mv", "lsregister-u", "mv", "mv", "lsregister", "rm", "source"],
              f"rc={res.returncode} {labels}")
        lu = [b for b in _dry_blocks(res.stdout) if b[0] == "lsregister-u"]
        check(f"{_VI} lsregister-u argv is '-u <target>'", lu and lu[0][1][1:] == ["-u", str(fx.target)], str(lu))
        check(f"{_VI} dry run with an existing bundle changes nothing", _world(fx) == before, "world changed")
        # foreign / unreadable identity -> refused as a real run would
        for label, ident in [("another identifier", "com.example.other"), ("unreadable identity", None)]:
            fx.pbval("CFBundleIdentifier", ident) if ident else (fx.pbv / "CFBundleIdentifier").unlink()
            res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
            check(f"{_VI} dry run, bundle with {label}: exit 1 'refused:' and 'not vibe's'",
                  res.returncode == 1 and "refused:" in _out(res) and "not vibe's" in _out(res), f"rc={res.returncode} {_out(res)[:200]}")
        # no PlistBuddy at all: an existing bundle counts as foreign (skip where a real one exists)
        fx.unrec("PlistBuddy")
        if not os.path.exists("/usr/libexec/PlistBuddy"):
            res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
            check(f"{_VI} dry run, existing bundle and no PlistBuddy: counts as foreign, exit 1",
                  res.returncode == 1 and "refused:" in _out(res), f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac1")


# ── AC2 ──────────────────────────────────────────────────────────────────────
def test_vli_ac2_darwin_real_run():
    print(f"\n{_VI} AC2 Darwin real run")
    v = str(VIBE.resolve())
    fx = _IFx("Darwin")
    try:
        res = fx.link("--install")
        check(f"{_VI} install: exit 0 and 'installed:' with the path",
              res.returncode == 0 and f"installed: {fx.target}" in res.stdout, f"rc={res.returncode} {_out(res)[:300]}")
        n0 = fx.names()
        want = ["osacompile"] + ["PlistBuddy"] * 9 + ["codesign"]
        check(f"{_VI} recorders called in design order (osacompile, 9 PlistBuddy, codesign, mv..., lsregister -f last)",
              n0[:11] == want and n0[11:-1] and set(n0[11:-1]) == {"mv"} and n0[-1] == "lsregister", str(n0))
        cs = fx.calls()
        pcs = [c[1] for c in cs if c[0] == "PlistBuddy"]
        check(f"{_VI} nine PlistBuddy calls: -c string verbatim, plist path last",
              [p[:2] for p in pcs] == [[_PB, c] for c in _pb_cmds(v)] and all(p[2].endswith("/Vibe Link.app/Contents/Info.plist") for p in pcs),
              str(pcs)[:300])
        check(f"{_VI} codesign --force --deep --sign - <tmp app>", cs[10][1][:4] == ["--force", "--deep", "--sign", "-"] and len(cs[10][1]) == 5, str(cs[10]))
        check(f"{_VI} lsregister -f <target>", cs[-1][1] == ["-f", str(fx.target)], str(cs[-1]))
        check(f"{_VI} last mv puts the app onto the target", cs[-2][1][-1] == str(fx.target), str(cs[-2]))
        check(f"{_VI} bundle directory ends at ~/Applications/Vibe Link.app",
              (fx.target / "Contents" / "Info.plist").is_file() and (fx.target / "Contents" / "Resources" / "Scripts" / "main.scpt").exists())
        check(f"{_VI} osacompile compiled the template with @@VIBE@@ replaced by the launcher path",
              (fx.root / "osa-source").read_text() == _template(v) and "@@VIBE@@" not in (fx.root / "osa-source").read_text(),
              (fx.root / "osa-source").read_text()[:200] if (fx.root / "osa-source").exists() else "no source logged")
        check(f"{_VI} temp dir removed on success", list(fx.tmp.iterdir()) == [], str(list(fx.tmp.iterdir())))

        # Set fails -> Add fallback for identifier and name
        fx2 = _IFx("Darwin")
        try:
            res = fx2.link("--install", SHIM_PB_FAIL_SET="1")
            pb = [c[1][1] for c in fx2.calls("PlistBuddy")]
            check(f"{_VI} Set failing falls back to Add for CFBundleIdentifier and CFBundleName",
                  res.returncode == 0 and "Add :CFBundleIdentifier string com.andeye.vibe.link" in pb
                  and 'Add :CFBundleName string "Vibe Link"' in pb, f"rc={res.returncode} {pb}")
        finally:
            fx2.close("ac2-fallback")
    finally:
        fx.close("ac2-fresh")

    # foreign bundle: another id, failing read, missing plist -> refused, byte-identical, never replaced
    for label, kw in [("another identifier", dict(ident="com.example.other")),
                      ("failing read (no value)", dict(ident=None)),
                      ("no Info.plist", dict(ident=None, plist=False))]:
        fx = _IFx("Darwin")
        try:
            fx.make_bundle(**kw)
            before = _tree(fx.target)
            res = fx.link("--install")
            ran = fx.names()
            check(f"{_VI} foreign bundle ({label}): exit 1 \"refused: ... not vibe's\"",
                  res.returncode == 1 and "refused:" in _out(res) and "not vibe's" in _out(res), f"rc={res.returncode} {_out(res)[:200]}")
            check(f"{_VI} foreign bundle ({label}): left byte-identical, no lsregister/mv ever ran",
                  _tree(fx.target) == before and "mv" not in ran and "lsregister" not in ran, f"{ran}")
            check(f"{_VI} foreign bundle ({label}): temp dir removed", list(fx.tmp.iterdir()) == [], str(list(fx.tmp.iterdir())))
        finally:
            fx.close("ac2-foreign")

    # second install over vibe's own bundle: lsregister -u then replace
    fx = _IFx("Darwin")
    try:
        fx.make_bundle(_MY_ID)
        res = fx.link("--install")
        n = fx.names()
        lr = [c[1] for c in fx.calls("lsregister")]
        first_mv = n.index("mv")
        check(f"{_VI} reinstall over vibe's bundle: exit 0; lsregister -u <target> (after the sibling mv) then lsregister -f <target> last",
              res.returncode == 0 and lr == [["-u", str(fx.target)], ["-f", str(fx.target)]]
              and first_mv < n.index("lsregister") and n[-1] == "lsregister", f"rc={res.returncode} {n} {lr}")
        check(f"{_VI} reinstall replaced the old bundle (marker gone, new plist present)",
              not (fx.target / "marker.txt").exists() and (fx.target / "Contents" / "Info.plist").is_file())
    finally:
        fx.close("ac2-reinstall")

    # symlinks are never followed
    fx = _IFx("Darwin")
    try:
        elsewhere = fx.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "keep.txt").write_text("k")
        fx.apps.symlink_to(elsewhere)
        before = _tree(elsewhere)
        res = fx.link("--install")
        check(f"{_VI} symlinked ~/Applications: exit 1 'refused:', link and target untouched, no mv",
              res.returncode == 1 and "refused:" in _out(res) and fx.apps.is_symlink() and _tree(elsewhere) == before
              and "mv" not in fx.names(), f"rc={res.returncode} {_out(res)[:200]} {fx.names()}")
        res = fx.link("--uninstall")
        check(f"{_VI} symlinked ~/Applications: --uninstall also refuses (exit 1)", res.returncode == 1 and _tree(elsewhere) == before,
              f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac2-symapps")
    fx = _IFx("Darwin")
    try:
        victim = fx.root / "victim.app"
        (victim / "Contents").mkdir(parents=True)
        (victim / "Contents" / "Info.plist").write_text("<plist/>")
        fx.apps.mkdir()
        fx.target.symlink_to(victim)
        fx.pbval("CFBundleIdentifier", _MY_ID)  # even if it claims to be vibe's
        before = _tree(victim)
        for cmd in ("--install", "--uninstall"):
            res = fx.link(cmd)
            check(f"{_VI} symlinked bundle, {cmd}: exit 1 'refused:', victim untouched, link kept",
                  res.returncode == 1 and "refused:" in _out(res) and _tree(victim) == before and fx.target.is_symlink(),
                  f"rc={res.returncode} {_out(res)[:200]}")
        check(f"{_VI} no rm/lsregister -u ran through the symlink", "lsregister" not in fx.names(), str(fx.names()))
    finally:
        fx.close("ac2-symbundle")


# ── AC3 ──────────────────────────────────────────────────────────────────────
def test_vli_ac3_tool_failures():
    print(f"\n{_VI} AC3 tool failures")
    for tool in ("osacompile", "PlistBuddy", "codesign", "mv"):
        fx = _IFx("Darwin")
        try:
            fx.apps.mkdir()
            (fx.apps / "Other.app").mkdir()
            before = _tree(fx.apps)
            res = fx.link("--install", SHIM_FAIL=tool)
            check(f"{_VI} SHIM_FAIL={tool}: exit 1 'refused: {tool} failed'",
                  res.returncode == 1 and f"refused: {tool} failed" in _out(res), f"rc={res.returncode} {_out(res)[:200]}")
            check(f"{_VI} SHIM_FAIL={tool}: temp dir gone and ~/Applications unchanged (no bundle)",
                  list(fx.tmp.iterdir()) == [] and _tree(fx.apps) == before, f"{list(fx.tmp.iterdir())}")
            check(f"{_VI} SHIM_FAIL={tool}: no lsregister -f ran", all(c[1][:1] != ["-f"] for c in fx.calls("lsregister")), str(fx.calls("lsregister")))
        finally:
            fx.close("ac3-" + tool)
    fx = _IFx("Darwin")
    try:
        res = fx.link("--install", SHIM_FAIL="lsregister")
        check(f"{_VI} SHIM_FAIL=lsregister: exit 1, bundle stays, message says to re-run --install",
              res.returncode == 1 and (fx.target / "Contents" / "Info.plist").is_file() and "--install" in _out(res)
              and re.search(r"re-?run", _out(res)), f"rc={res.returncode} {_out(res)[:300]}")
        check(f"{_VI} SHIM_FAIL=lsregister: temp dir gone", list(fx.tmp.iterdir()) == [], str(list(fx.tmp.iterdir())))
    finally:
        fx.close("ac3-lsr")
    # missing tool (control for the missing-tool wording): only where the system has no osacompile
    if not os.path.exists("/usr/bin/osacompile"):
        fx = _IFx("Darwin", tools=[t for t in _TOOLS if t != "osacompile"])
        try:
            res = fx.link("--install")
            check(f"{_VI} no osacompile anywhere: exit 1 'refused: osacompile not found', nothing created",
                  res.returncode == 1 and "refused: osacompile not found" in _out(res) and not fx.apps.exists()
                  and list(fx.tmp.iterdir()) == [], f"rc={res.returncode} {_out(res)[:200]}")
        finally:
            fx.close("ac3-missing")
    else:
        print(f"{_VI} (skipped: real /usr/bin/osacompile exists)")


# ── AC4 ──────────────────────────────────────────────────────────────────────
def test_vli_ac4_shim_precedence():
    print(f"\n{_VI} AC4 shim precedence")
    fx = _IFx("Darwin")
    try:
        res = fx.link("--install")
        used = set(fx.names())
        check(f"{_VI} every external tool of the install ran as its PATH shim (log names each)",
              res.returncode == 0 and {"osacompile", "PlistBuddy", "codesign", "lsregister", "mv"} <= used, str(sorted(used)))
    finally:
        fx.close("ac4")
    src = VIBE.read_text()
    check(f"{_VI} source: PATH is never prepended with /usr/libexec or the LaunchServices directory",
          not re.search(r"PATH=[^\n]*(/usr/libexec|LaunchServices)", src) and not re.search(r"export PATH=[^\n]*(/usr/libexec|LaunchServices)", src))
    for tool, fb in [("osacompile", "/usr/bin/osacompile"), ("PlistBuddy", "/usr/libexec/PlistBuddy"),
                     ("codesign", "/usr/bin/codesign"),
                     ("lsregister", "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister")]:
        check(f"{_VI} source: fallback {fb} present and a 'command -v' resolution exists",
              fb in src and "command -v" in src and tool in src, tool)
    i = src.find("PlistBuddy")
    check(f"{_VI} source: 'command -v' appears before the first absolute-path fallback use",
          0 <= src.find("command -v") < len(src) and src.find("command -v", src.find("_link_valid_path()")) != -1)


# ── AC5 ──────────────────────────────────────────────────────────────────────
def test_vli_ac5_linux():
    print(f"\n{_VI} AC5 Linux")
    v = str(VIBE.resolve())
    fx = _IFx("Linux")
    try:
        res = fx.link("--install")
        check(f"{_VI} Linux install: exit 0 and 'installed: <path>'", res.returncode == 0 and f"installed: {fx.desk}" in res.stdout,
              f"rc={res.returncode} {_out(res)[:300]}")
        check(f"{_VI} .desktop content equals the design text exactly",
              fx.desk.exists() and fx.desk.read_text() == _desktop(v), fx.desk.read_text() if fx.desk.exists() else "missing")
        check(f"{_VI} .desktop mode 644 and no temp leftovers in the applications dir",
              fx.desk.exists() and stat.S_IMODE(fx.desk.stat().st_mode) == 0o644 and [p.name for p in fx.desk_dir.iterdir()] == ["vibe-link.desktop"],
              str([p.name for p in fx.desk_dir.iterdir()]))
        check(f"{_VI} xdg-mime default vibe-link.desktop x-scheme-handler/vibe recorded",
              [c[1] for c in fx.calls("xdg-mime")] == [["default", "vibe-link.desktop", "x-scheme-handler/vibe"]], str(fx.calls("xdg-mime")))
        check(f"{_VI} update-desktop-database <dir> recorded after xdg-mime",
              [c[1] for c in fx.calls("update-desktop-database")] == [[str(fx.desk_dir)]]
              and fx.names().index("xdg-mime") < fx.names().index("update-desktop-database"), str(fx.names()))
        check(f"{_VI} temp dir untouched/removed", list(fx.tmp.iterdir()) == [], str(list(fx.tmp.iterdir())))
        # reinstall (own file) replaces and exits 0
        fx.desk.write_text(_desktop("/old/place/vibe"))
        res = fx.link("--install")
        check(f"{_VI} reinstall over vibe's own .desktop: exit 0 and content rewritten",
              res.returncode == 0 and fx.desk.read_text() == _desktop(v), f"rc={res.returncode}")
    finally:
        fx.close("ac5-main")
    # XDG_DATA_HOME wins when set
    fx = _IFx("Linux")
    try:
        xdg = fx.root / "xdgdata"
        res = fx.link("--install", XDG_DATA_HOME=str(xdg))
        check(f"{_VI} XDG_DATA_HOME set: file under $XDG_DATA_HOME/applications, not under ~/.local/share",
              res.returncode == 0 and (xdg / "applications" / "vibe-link.desktop").is_file() and not fx.desk.exists(),
              f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac5-xdg")
    # no update-desktop-database shim: skipped silently
    fx = _IFx("Linux", tools=("xdg-mime",))
    try:
        res = fx.link("--install")
        sys_udd = shutil.which("update-desktop-database", path="/usr/bin:/bin:/usr/local/bin")
        check(f"{_VI} no update-desktop-database: exit 0, no complaint about it",
              res.returncode == 0 and (sys_udd or "update-desktop-database" not in _out(res)) and fx.desk.is_file(),
              f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac5-noudd")
    # no xdg-mime: refuse before writing anything (skip if the system has one)
    if shutil.which("xdg-mime", path="/usr/bin:/bin:/usr/local/bin") is None:
        fx = _IFx("Linux", tools=("update-desktop-database",))
        try:
            before = _world(fx)
            res = fx.link("--install")
            check(f"{_VI} no xdg-mime: exit 1 'refused: xdg-mime not found', nothing written",
                  res.returncode == 1 and "refused: xdg-mime not found" in _out(res) and _world(fx) == before and not fx.desk_dir.exists(),
                  f"rc={res.returncode} {_out(res)[:200]}")
        finally:
            fx.close("ac5-noxdg")
    else:
        print(f"{_VI} (skipped: real xdg-mime exists)")
    # symlinked applications dir / target file refused
    fx = _IFx("Linux")
    try:
        elsewhere = fx.root / "elsewhere"
        elsewhere.mkdir()
        fx.desk_dir.parent.mkdir(parents=True)
        fx.desk_dir.symlink_to(elsewhere)
        res = fx.link("--install")
        check(f"{_VI} symlinked applications dir: exit 1 'refused:', nothing written through it",
              res.returncode == 1 and "refused:" in _out(res) and list(elsewhere.iterdir()) == [], f"rc={res.returncode} {_out(res)[:200]}")
        res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
        check(f"{_VI} symlinked applications dir is also refused in a dry run (read-only check)", res.returncode == 1, f"rc={res.returncode}")
    finally:
        fx.close("ac5-symdir")
    fx = _IFx("Linux")
    try:
        fx.desk_dir.mkdir(parents=True)
        victim = fx.root / "victim.desktop"
        victim.write_text("precious\n")
        fx.desk.symlink_to(victim)
        res = fx.link("--install")
        check(f"{_VI} symlinked .desktop target: exit 1 'refused:', victim untouched",
              res.returncode == 1 and "refused:" in _out(res) and victim.read_text() == "precious\n", f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac5-symfile")
    # space and ~ in the launcher path
    fx = _IFx("Linux")
    try:
        copy = fx.stage("sp ace~dir")
        lp = str(copy.resolve())
        res = fx.link("--install", launcher=copy)
        text = fx.desk.read_text() if fx.desk.exists() else ""
        check(f"{_VI} space and ~ in launcher path: exit 0 and Exec=\"<path>\" link-open %u",
              res.returncode == 0 and f'Exec="{lp}" link-open %u\n' in text, f"rc={res.returncode} {_out(res)[:200]} {text}")
        line = [l for l in text.split("\n") if l.startswith("Exec=")]
        check(f"{_VI} desktop-entry word split of Exec gives exactly [path, link-open, %u]",
              line and _exec_words(line[0][5:]) == [lp, "link-open", "%u"], str(line))
        check(f"{_VI} control: the splitter would break an UNquoted path", _exec_words(lp + " link-open %u") != [lp, "link-open", "%u"])
    finally:
        fx.close("ac5-space")
    # dry run (Linux): blocks and source
    fx = _IFx("Linux", tools=())
    try:
        before = _world(fx)
        res = fx.link("--install", VIBE_LINK_DRY_RUN="1")
        blocks = _dry_blocks(res.stdout)
        labels = [b[0] for b in blocks if b[0] in ("xdg-mime", "update-desktop-database", "source")]
        check(f"{_VI} Linux dry run: exit 0, blocks xdg-mime, update-desktop-database, source (last)",
              res.returncode == 0 and labels == ["xdg-mime", "update-desktop-database", "source"] and blocks[-1][0] == "source",
              f"rc={res.returncode} {[b[0] for b in blocks]} {_out(res)[:200]}")
        d = {b[0]: b for b in blocks}
        if "xdg-mime" in d and "update-desktop-database" in d and "source" in d:
            check(f"{_VI} Linux dry run argv: xdg-mime default ..., update-desktop-database <dir>",
                  d["xdg-mime"][1][1:] == ["default", "vibe-link.desktop", "x-scheme-handler/vibe"]
                  and d["update-desktop-database"][1][1:] == [str(fx.desk_dir)], str(d["xdg-mime"][1]) + str(d["update-desktop-database"][1]))
            check(f"{_VI} Linux dry run source: path is the destination and lines equal the .desktop text",
                  d["source"][2]["path"] == str(fx.desk) and "\n".join(d["source"][2]["lines"]).rstrip("\n") == _desktop(str(VIBE.resolve())).rstrip("\n"),
                  str(d["source"][2])[:300])
        check(f"{_VI} Linux dry run creates nothing and runs nothing", _world(fx) == before and fx.names() == [], str(fx.names()))
    finally:
        fx.close("ac5-dry")


# ── AC6 ──────────────────────────────────────────────────────────────────────
def test_vli_ac6_launcher_path():
    print(f"\n{_VI} AC6 launcher path")
    for os_name in ("Darwin", "Linux"):
        fx = _IFx(os_name)
        try:
            good = fx.stage("plain dir")
            res = fx.link("--install", launcher=good)
            check(f"{_VI} control ({os_name}): a plain executable launcher copy installs", res.returncode == 0, f"rc={res.returncode} {_out(res)[:200]}")
            shutil.rmtree(fx.apps, ignore_errors=True)
            shutil.rmtree(fx.home / ".local", ignore_errors=True)
            fx.log.write_text("")
            before = _world(fx)
            fails = []
            for label, name in [("double quote", 'dq"x'), ("dollar", "dol$x"), ("backtick", "bt`touch PWNED`"),
                                ("single quote", "sq'x"), ("backslash", "bs\\x"), ("semicolon", "a;b")]:
                bad = fx.stage(name)
                r = fx.link("--install", launcher=bad)
                if not (r.returncode == 7 and "refused: launcher path" in _out(r)):
                    fails.append((label, r.returncode, _out(r)[:80]))
            check(f"{_VI} {os_name}: launcher path with quote/$/backtick/'/\\/; exits 7 'refused: launcher path'", fails == [], str(fails))
            check(f"{_VI} {os_name}: rejected launcher paths create nothing and run no tool",
                  _world(fx) == before and fx.names() == [] and fx.pwned() == [], str(fx.names()))
            nx = fx.stage("not exec", executable=False)
            r = fx.link("--install", launcher=nx)
            check(f"{_VI} {os_name}: non-executable launcher file: exit 7 'refused: launcher path', nothing created",
                  r.returncode == 7 and "refused: launcher path" in _out(r) and _world(fx) == before and fx.names() == [],
                  f"rc={r.returncode} {_out(r)[:200]}")
        finally:
            fx.close("ac6-" + os_name)


# ── AC7 ──────────────────────────────────────────────────────────────────────
def test_vli_ac7_uninstall():
    print(f"\n{_VI} AC7 uninstall")
    fx = _IFx("Darwin")
    try:
        fx.make_bundle(_MY_ID)
        res = fx.link("--uninstall")
        check(f"{_VI} Darwin: vibe's bundle: exit 0, lsregister -u <target>, removed, 'removed:' printed",
              res.returncode == 0 and f"removed: {fx.target}" in res.stdout and not fx.target.exists()
              and [c[1] for c in fx.calls("lsregister")] == [["-u", str(fx.target)]], f"rc={res.returncode} {_out(res)[:200]} {fx.calls('lsregister')}")
        res = fx.link("--uninstall")
        check(f"{_VI} Darwin: absent bundle: exit 0 'nothing to remove'", res.returncode == 0 and "nothing to remove" in _out(res),
              f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac7-darwin")
    for label, kw in [("another identifier", dict(ident="com.example.other")), ("unreadable identity", dict(ident=None))]:
        fx = _IFx("Darwin")
        try:
            fx.make_bundle(**kw)
            before = _tree(fx.target)
            res = fx.link("--uninstall")
            check(f"{_VI} Darwin: foreign bundle ({label}): exit 1 \"not vibe's\", nothing removed, no lsregister -u",
                  res.returncode == 1 and "not vibe's" in _out(res) and _tree(fx.target) == before and fx.calls("lsregister") == [],
                  f"rc={res.returncode} {_out(res)[:200]}")
        finally:
            fx.close("ac7-foreign")
    fx = _IFx("Linux")
    try:
        assert fx.link("--install").returncode == 0
        mime = fx.home / ".config" / "mimeapps.list"
        mime.parent.mkdir(parents=True)
        mime.write_text("[Default Applications]\nx-scheme-handler/vibe=vibe-link.desktop\n")
        before = mime.read_bytes()
        res = fx.link("--uninstall")
        check(f"{_VI} Linux: file removed, exit 0 'removed:'", res.returncode == 0 and f"removed: {fx.desk}" in res.stdout and not fx.desk.exists(),
              f"rc={res.returncode} {_out(res)[:200]}")
        check(f"{_VI} Linux: mimeapps.list association left alone", mime.read_bytes() == before)
        res = fx.link("--uninstall")
        check(f"{_VI} Linux: second run exit 0 'nothing to remove'", res.returncode == 0 and "nothing to remove" in _out(res),
              f"rc={res.returncode} {_out(res)[:200]}")
    finally:
        fx.close("ac7-linux")


# ── AC8 ──────────────────────────────────────────────────────────────────────
def _line(out: str, prefix: str):
    for l in out.split("\n"):
        if l.startswith(prefix):
            return l
    return None


def test_vli_ac8_status():
    print(f"\n{_VI} AC8 status")
    v = str(VIBE.resolve())
    fx = _IFx("Darwin")
    try:
        res = fx.link("--status")
        o = res.stdout
        check(f"{_VI} Darwin not installed: exit 0, 'handler: not installed', current:, projects: 0, terminal:",
              res.returncode == 0 and _line(o, "handler: ") == "handler: not installed" and _line(o, "current: ") == f"current: {v}"
              and _line(o, "projects: ") == "projects: 0" and (_line(o, "terminal: ") or "").startswith("terminal: "), f"rc={res.returncode} {o}")
        check(f"{_VI} not installed: no launcher:/stale: lines", _line(o, "launcher: ") is None and _line(o, "stale:") is None, o)
        fx.write_cfg("VIBE_TERMINAL=iTerm\n")
        check(f"{_VI} terminal: line shows the resolved terminal", _line(fx.link("--status").stdout, "terminal: ") == "terminal: iTerm")
        # installed and current
        fx.make_bundle(_MY_ID, launcher=v)
        o = fx.link("--status").stdout
        check(f"{_VI} installed and current: handler path, launcher == current, no stale line",
              _line(o, "handler: ") == f"handler: {fx.target}" and _line(o, "launcher: ") == f"launcher: {v}"
              and _line(o, "current: ") == f"current: {v}" and _line(o, "stale:") is None, o)
        # stale
        fx.pbval("VibeLauncherPath", "/old/place/vibe")
        o = fx.link("--status").stdout
        check(f"{_VI} installed and stale: launcher shows the baked path, 'stale: run vibe link --install'",
              _line(o, "launcher: ") == "launcher: /old/place/vibe" and _line(o, "stale: ") == "stale: run vibe link --install", o)
        # project counts
        for n, names in [(1, ["demo"]), (2, ["demo2"])]:
            for nm in names:
                assert fx.allow(fx.repo(nm), nm).returncode == 0
            o = fx.link("--status").stdout
            check(f"{_VI} {n} registered project(s): 'projects: {n}'", _line(o, "projects: ") == f"projects: {n}", o)
        # unusable registry
        fx.write_reg(fx.reg.read_text(), mode=0o644)
        res = fx.link("--status")
        check(f"{_VI} unusable registry (group-readable): exit 0 'projects: 0' (matches list)",
              res.returncode == 0 and _line(res.stdout, "projects: ") == "projects: 0", f"rc={res.returncode} {res.stdout}")
        fx.write_reg(fx.reg.read_text(), mode=0o600)
        check(f"{_VI} control: restoring mode 600 brings the count back", _line(fx.link("--status").stdout, "projects: ") == "projects: 2")
    finally:
        fx.close("ac8-darwin")
    fx = _IFx("Linux")
    try:
        fx.xdg_query("vibe-link.desktop")
        res = fx.link("--status")
        o = res.stdout
        check(f"{_VI} Linux not installed: exit 0, handler: not installed, a default: line",
              res.returncode == 0 and _line(o, "handler: ") == "handler: not installed" and _line(o, "default: ") is not None, f"rc={res.returncode} {o}")
        none_ok = not any(shutil.which(t) for t in ("ghostty", "kitty", "wezterm", "gnome-terminal"))
        t = _line(o, "terminal: ")
        check(f"{_VI} Linux with no terminal chosen: 'terminal: (none chosen)'",
              t == "terminal: (none chosen)" if none_ok else (t or "").startswith("terminal: "), str(t))
        assert fx.link("--install").returncode == 0
        n_before = len(fx.calls())
        o = fx.link("--status").stdout
        check(f"{_VI} Linux installed and current: handler, launcher (quotes stripped), no stale, default ok",
              _line(o, "handler: ") == f"handler: {fx.desk}" and _line(o, "launcher: ") == f"launcher: {v}" and _line(o, "stale:") is None
              and _line(o, "default: ") == "default: vibe-link.desktop" and "not the default handler" not in o, o)
        fx.desk.write_text(_desktop("/old/place/vibe"))
        o = fx.link("--status").stdout
        check(f"{_VI} Linux stale: launcher shows the Exec path, stale line printed",
              _line(o, "launcher: ") == "launcher: /old/place/vibe" and _line(o, "stale: ") == "stale: run vibe link --install", o)
        fx.xdg_query("firefox.desktop")
        o = fx.link("--status").stdout
        check(f"{_VI} Linux other default: 'default: firefox.desktop' plus 'not the default handler'",
              _line(o, "default: ") is not None and "firefox.desktop" in _line(o, "default: ") and "not the default handler" in o, o)
        check(f"{_VI} status is read-only: no xdg-mime default, no files changed",
              all(c[1][:1] != ["default"] for c in fx.calls()[n_before:] if c[0] == "xdg-mime"))
    finally:
        fx.close("ac8-linux")


# ── AC9 ──────────────────────────────────────────────────────────────────────
def test_vli_ac9_template():
    print(f"\n{_VI} AC9 applet template")
    ok = _TEMPLATE.is_file()
    check(f"{_VI} devcontainer/link/VibeLink.applescript is committed", ok, str(_TEMPLATE))
    if not ok:
        return
    t = _TEMPLATE.read_text()
    lines = t.split("\n")
    shell = [l for l in lines if "do shell script" in l]
    want = '\tdo shell script (quoted form of "@@VIBE@@") & " link-open " & (quoted form of theURL) & " </dev/null >/dev/null 2>&1 &"'
    check(f"{_VI} exactly one 'do shell script' line, byte for byte the design line", shell == [want], str(shell))
    check(f"{_VI} exactly one @@VIBE@@ placeholder", t.count("@@VIBE@@") == 1)
    stray = [l for l in lines if "theURL" in l and "quoted form of theURL" not in l and "on open location theURL" not in l]
    check(f"{_VI} URL text only appears as (quoted form of theURL)", stray == [] and t.count("theURL") == 2, str(stray))
    check(f"{_VI} control: has both handlers (open location and run)", "on open location theURL" in t and "\non run\n" in "\n" + t)
    check(f"{_VI} no other shell/eval-like constructs", t.count("run script") == 0 and t.count("osascript") == 0)


# ── AC10 ─────────────────────────────────────────────────────────────────────
def test_vli_ac10_usage_and_help():
    print(f"\n{_VI} AC10 usage and help")
    for os_name in ("Darwin", "Linux"):
        fx = _IFx(os_name)
        try:
            before = _world(fx)
            for args in (["--install", "extra"], ["--install", "--uninstall"], ["--bogus"], ["--status", "x"]):
                res = fx.link(*args)
                o = _out(res)
                check(f"{_VI} {os_name} vibe link {' '.join(args)}: exit 1 'Usage: vibe link' naming all three options",
                      res.returncode == 1 and "Usage: vibe link" in o and all(f in o for f in ("--install", "--uninstall", "--status")),
                      f"rc={res.returncode} {o[:200]}")
            check(f"{_VI} {os_name} usage errors create nothing and run no tool", _world(fx) == before and fx.names() == [], str(fx.names()))
        finally:
            fx.close("ac10-" + os_name)
    fx = _IFx("Darwin")
    try:
        res = fx.vibe("--help")
        o = res.stdout + res.stderr
        n = len(res.stdout.rstrip("\n").split("\n"))
        check(f"{_VI} vibe --help: exit 0, at most 78 lines (got {n})", res.returncode == 0 and n <= 78, f"rc={res.returncode}")
        check(f"{_VI} vibe --help contains 'vibe link --install' and not 'is next'", "vibe link --install" in o and "is next" not in o)
    finally:
        fx.close("ac10-help")


# ── AC11 ─────────────────────────────────────────────────────────────────────
def test_vli_ac11_docs():
    print(f"\n{_VI} AC11 docs")
    check(f"{_VI} README contains 'vibe link --install'", "vibe link --install" in (REPO / "README.md").read_text())
    mt = (REPO / "MANUAL-TESTS.md").read_text()
    m = re.search(r"^### Test 68\b.*?(?=^### Test |\Z)", mt, re.S | re.M)
    check(f"{_VI} MANUAL-TESTS Test 68 section exists", m is not None)
    sec = m.group(0) if m else ""
    check(f"{_VI} Test 68 mentions --status", "--status" in sec)
    check(f"{_VI} Test 68 mentions install, uninstall and a Linux xdg-open step",
          "--install" in sec and "--uninstall" in sec and "xdg-open" in sec)
    cl = (REPO / "CHANGELOG.md").read_text()
    check(f"{_VI} CHANGELOG mentions 'vibe link --install'", "vibe link --install" in cl)
    check(f"{_VI} no sha pin in this test file", not re.search(r"git (show|diff) [0-9a-f]{7,40}\b", Path(__file__).read_text().replace("[0-9a-f]", "")))


# ── cycle 2 (Rev 4 addendum): AC12–AC20 ─────────────────────────────────────
_LSR_FALLBACK = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"


def _lsr_shim(fx: _IFx) -> None:
    """lsregister shim that also answers `-dump` from <root>/lsdump."""
    p = fx.bin / "lsregister"
    p.write_text("#!/bin/sh\n"
                 f"{{ printf '@@ lsregister\\n'; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> '{fx.log}'\n"
                 "[ \"$SHIM_FAIL\" = lsregister ] && exit 1\n"
                 f"[ \"$1\" = -dump ] && {{ cat '{fx.root}/lsdump' 2>/dev/null; exit 0; }}\nexit 0\n")
    p.chmod(0o755)


def _mv_shim(fx: _IFx) -> None:
    """mv shim: logs, fails on the Nth call when SHIM_MV_FAIL_N is set, else delegates."""
    p = fx.bin / "mv"
    cnt = fx.root / "mvcount"
    p.write_text("#!/bin/sh\n"
                 f"{{ printf '@@ mv\\n'; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> '{fx.log}'\n"
                 "[ \"$SHIM_FAIL\" = mv ] && exit 1\n"
                 f"n=$(cat '{cnt}' 2>/dev/null || echo 0); n=$((n+1)); echo $n > '{cnt}'\n"
                 "[ -n \"$SHIM_MV_FAIL_N\" ] && [ \"$n\" = \"$SHIM_MV_FAIL_N\" ] && exit 1\n"
                 "exec /bin/mv \"$@\"\n")
    p.chmod(0o755)


def _registered(fx: _IFx) -> bool:
    """Replay lsregister -u/-f calls on the target: initially registered."""
    st = True
    for c in fx.calls("lsregister"):
        a = c[1]
        if a == ["-u", str(fx.target)]:
            st = False
        elif a == ["-f", str(fx.target)]:
            st = True
    return st


def _leftovers(fx: _IFx) -> list:
    return sorted(p.name for p in fx.apps.iterdir() if p.name != "Vibe Link.app") if fx.apps.is_dir() else []


def _dump(*entries) -> str:
    """Crafted lsregister -dump text: one record per (path, bundle id, claims-vibe) tuple."""
    out = []
    for path, bid, vibe in entries:
        out.append("-" * 80 + f"\nbundle id:      {bid}\npath:           {path} (0x1234)\n"
                   f"bindings:       {'ftp:, vibe:' if vibe else 'ftp:, https:'}\n")
    return "".join(out)


def test_vli_ac12_reinstall_safe():
    print(f"\n{_VI} AC12 reinstall never loses the working handler")
    fx = _IFx("Darwin")
    try:
        _mv_shim(fx)
        fx.make_bundle(_MY_ID)
        res = fx.link("--install")
        n = fx.names()
        mvs = fx.calls("mv")
        lr = [c[1] for c in fx.calls("lsregister")]
        tgt = str(fx.target)
        check(f"{_VI} success: exit 0, new bundle in place, marker gone, no .new-/.old- sibling left",
              res.returncode == 0 and (fx.target / "Contents" / "Info.plist").is_file() and not (fx.target / "marker.txt").exists()
              and _leftovers(fx) == [], f"rc={res.returncode} {_out(res)[:200]} {_leftovers(fx)}")
        check(f"{_VI} success: first mv targets a '.Vibe Link.app.new-<pid>' sibling in ~/Applications",
              len(mvs) >= 3 and mvs[0][1][-1].startswith(str(fx.apps) + "/.Vibe Link.app.new-"), str(mvs[:1]))
        check(f"{_VI} success: second mv renames the old bundle to '.Vibe Link.app.old-<pid>'",
              len(mvs) >= 3 and mvs[1][1][-2] == tgt and mvs[1][1][-1].startswith(str(fx.apps) + "/.Vibe Link.app.old-"), str(mvs[1:2]))
        check(f"{_VI} success: last mv renames the sibling onto the target",
              len(mvs) >= 3 and mvs[-1][1][-2].startswith(str(fx.apps) + "/.Vibe Link.app.new-") and mvs[-1][1][-1] == tgt, str(mvs[-1:]))
        # interleaving: mv#1, lsregister -u, mv#2, mv#3, lsregister -f
        seq = [x for x in n if x in ("mv", "lsregister")]
        check(f"{_VI} success order: mv (to sibling), lsregister -u, mv (old aside), mv (into place), lsregister -f",
              seq == ["mv", "lsregister", "mv", "mv", "lsregister"] and lr == [["-u", tgt], ["-f", tgt]], f"{seq} {lr}")
    finally:
        fx.close("ac12-ok")
    for label, extra in [("SHIM_FAIL=mv (first move fails)", dict(SHIM_FAIL="mv")),
                         ("second mv fails (after lsregister -u)", dict(SHIM_MV_FAIL_N="2"))]:
        fx = _IFx("Darwin")
        try:
            _mv_shim(fx)
            fx.make_bundle(_MY_ID)
            before = _tree(fx.target)
            res = fx.link("--install", **extra)
            check(f"{_VI} {label}: exit 1 'refused:'", res.returncode == 1 and "refused:" in _out(res), f"rc={res.returncode} {_out(res)[:200]}")
            check(f"{_VI} {label}: old bundle byte-identical at the target", _tree(fx.target) == before, "changed")
            check(f"{_VI} {label}: old bundle still registered per the lsregister log", _registered(fx), str(fx.calls("lsregister")))
            check(f"{_VI} {label}: no .new-/.old- sibling left and temp dir gone",
                  _leftovers(fx) == [] and list(fx.tmp.iterdir()) == [], f"{_leftovers(fx)} {list(fx.tmp.iterdir())}")
        finally:
            fx.close("ac12-fail")
    src = VIBE.read_text()
    check(f"{_VI} source names the '.Vibe Link.app.new-' and '.old-' siblings (pid-suffixed)",
          ".Vibe Link.app.new-" in src and ".Vibe Link.app.old-" in src)


def test_vli_ac13_14_plist_quoting():
    print(f"\n{_VI} AC13/AC14 plist values quoted; one source for dry and real")
    fx = _IFx("Darwin", tools=())
    try:
        copy = fx.stage("sp ace dir")
        lp = str(copy.resolve())
        res = fx.link("--install", launcher=copy, VIBE_LINK_DRY_RUN="1")
        dry = [b[1][1:] for b in _dry_blocks(res.stdout) if b[0] == "plistbuddy"]
        dcs = [d[1] for d in dry]
        dry_root = fx.root
        check(f"{_VI} dry run: exit 0 and 9 plistbuddy blocks", res.returncode == 0 and len(dry) == 9, f"rc={res.returncode} {_out(res)[:200]}")
        check(f"{_VI} dry run argv shows Set :CFBundleName \"Vibe Link\" (quoted)", 'Set :CFBundleName "Vibe Link"' in dcs, str(dcs))
        check(f"{_VI} dry run argv shows Add :VibeLauncherPath string \"<path with space>\" (quoted)",
              f'Add :VibeLauncherPath string "{lp}"' in dcs and " " in lp, str(dcs[-1:]))
        check(f"{_VI} control: the unquoted old form is gone", "Set :CFBundleName Vibe Link" not in dcs
              and f"Add :VibeLauncherPath string {lp}" not in dcs)
    finally:
        fx.close("ac13-dry")
    fx = _IFx("Darwin")
    try:
        copy = fx.stage("sp ace dir")
        res = fx.link("--install", launcher=copy)
        real = [c[1][1] for c in fx.calls("PlistBuddy")]
        check(f"{_VI} AC14 real-run -c strings identical to the dry-run strings (same order, same text)",
              res.returncode == 0 and [x.replace(str(fx.root), "<R>") for x in real] == [x.replace(str(dry_root), "<R>") for x in dcs], f"rc={res.returncode} real={real} dry={dcs}")
    finally:
        fx.close("ac13-real")
    src = VIBE.read_text()
    check(f"{_VI} AC14 source: ':VibeLauncherPath string' appears once (a single array feeds both paths)",
          src.count("Add :VibeLauncherPath string") == 1, str(src.count("Add :VibeLauncherPath string")))


def test_vli_ac15_racing_directory():
    print(f"\n{_VI} AC15 no nesting when the target appears between check and move")
    fx = _IFx("Darwin")
    try:
        # codesign runs after the existence check and before the final move: it plants the squatting directory
        cs = fx.bin / "codesign"
        cs.write_text("#!/bin/sh\n"
                      f"{{ printf '@@ codesign\\n'; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> '{fx.log}'\n"
                      "[ -n \"$SHIM_RACE_DIR\" ] && mkdir -p \"$SHIM_RACE_DIR\" && echo squatter > \"$SHIM_RACE_DIR/squat.txt\"\nexit 0\n")
        cs.chmod(0o755)
        res = fx.link("--install", SHIM_RACE_DIR=str(fx.target))
        nested = list(fx.target.rglob("*.app")) if fx.target.is_dir() else []
        check(f"{_VI} target dir appeared mid-run -> exit 1 'refused:'", res.returncode == 1 and "refused:" in _out(res),
              f"rc={res.returncode} {_out(res)[:200]}")
        check(f"{_VI} no nested bundle inside the squatting directory, squatter intact",
              fx.target.is_dir() and nested == [] and (fx.target / "squat.txt").read_text() == "squatter\n"
              and not (fx.target / "Contents").exists(), str(sorted(p.name for p in fx.target.iterdir())) if fx.target.is_dir() else "gone")
        check(f"{_VI} no sibling or temp leftovers", _leftovers(fx) == [] and list(fx.tmp.iterdir()) == [],
              f"{_leftovers(fx)} {list(fx.tmp.iterdir())}")
        check(f"{_VI} no lsregister -f after the refused move", all(c[1][:1] != ["-f"] for c in fx.calls("lsregister")), str(fx.calls("lsregister")))
    finally:
        fx.close("ac15")
    fx = _IFx("Darwin")
    try:
        res = fx.link("--install")
        check(f"{_VI} control: without a racing directory the install succeeds", res.returncode == 0, _out(res)[:200])
    finally:
        fx.close("ac15-ctl")


def test_vli_ac16_macos_default_handler():
    print(f"\n{_VI} AC16 macOS --status default handler")
    v = str(VIBE.resolve())
    fx = _IFx("Darwin")
    try:
        _lsr_shim(fx)
        fx.make_bundle(_MY_ID, launcher=v)
        tgt = str(fx.target)
        other = "/Applications/Other Handler.app"
        cases = [
            ("ours first", _dump((tgt, _MY_ID, True), (other, "com.example.other", True)), "ours"),
            ("only ours claims vibe", _dump((other, "com.example.other", False), (tgt, _MY_ID, True)), "ours"),
            ("another bundle first", _dump((other, "com.example.other", True), (tgt, _MY_ID, True)), "other"),
            ("empty dump", "", "unknown"),
            ("unparsable text", "garbage without any structure\n\x00\x01 vibe\n", "unknown"),
        ]
        for label, text, want in cases:
            (fx.root / "lsdump").write_text(text)
            res = fx.link("--status")
            o = res.stdout
            d = _line(o, "default: ")
            if want == "ours":
                ok = d == f"default: {tgt}" and "not the default handler" not in o
            elif want == "other":
                ok = d is not None and "Other Handler.app" in d and "not the default handler" in o
            else:
                ok = d == "default: (unknown)" and "not the default handler" not in o
            check(f"{_VI} {label}: exit 0 and the right default: line", res.returncode == 0 and ok, f"rc={res.returncode} {o}")
        check(f"{_VI} status asked lsregister -dump (read-only: no -f/-u)",
              ["-dump"] in [c[1] for c in fx.calls("lsregister")] and all(c[1][:1] == ["-dump"] for c in fx.calls("lsregister")),
              str(fx.calls("lsregister")))
        res = fx.link("--status", SHIM_FAIL="lsregister")
        check(f"{_VI} lsregister -dump failing: exit 0 and 'default: (unknown)'",
              res.returncode == 0 and _line(res.stdout, "default: ") == "default: (unknown)", f"rc={res.returncode} {res.stdout}")
    finally:
        fx.close("ac16")


def test_vli_ac17_linux_failure_cleanup():
    print(f"\n{_VI} AC17 Linux failure after writing; uninstall refreshes the database")
    fx = _IFx("Linux")
    try:
        res = fx.link("--install", SHIM_FAIL="xdg-mime")
        left = [p.name for p in fx.desk_dir.iterdir()] if fx.desk_dir.is_dir() else []
        check(f"{_VI} xdg-mime default fails: exit 1 and no .desktop (or temp file) left",
              res.returncode == 1 and left == [], f"rc={res.returncode} {_out(res)[:200]} {left}")
        check(f"{_VI} control: without the failure the file is written", fx.link("--install").returncode == 0 and fx.desk.is_file())
        fx.log.write_text("")
        res = fx.link("--uninstall")
        check(f"{_VI} uninstall: update-desktop-database <dir> recorded",
              res.returncode == 0 and [c[1] for c in fx.calls("update-desktop-database")] == [[str(fx.desk_dir)]],
              f"rc={res.returncode} {fx.calls()}")
    finally:
        fx.close("ac17")
    fx = _IFx("Linux", tools=("xdg-mime",))
    try:
        assert fx.link("--install").returncode == 0
        res = fx.link("--uninstall")
        sys_udd = shutil.which("update-desktop-database", path="/usr/bin:/bin:/usr/local/bin")
        check(f"{_VI} uninstall without update-desktop-database: exit 0, file removed, silent",
              res.returncode == 0 and not fx.desk.exists() and (sys_udd or "update-desktop-database" not in _out(res)), _out(res)[:200])
    finally:
        fx.close("ac17-noudd")


def test_vli_ac18_docs_wording():
    print(f"\n{_VI} AC18 README / MANUAL-TESTS wording")
    rd = (REPO / "README.md").read_text()
    mt = (REPO / "MANUAL-TESTS.md").read_text()
    m = re.search(r"^### Test 68\b.*?(?=^### Test |\Z)", mt, re.S | re.M)
    sec = m.group(0) if m else ""
    for name, text in [("README", rd), ("MANUAL-TESTS Test 68", sec)]:
        check(f"{_VI} {name}: no longer says the applet needs Automation ('allow Vibe Link to control')",
              "allow Vibe Link to control" not in text and "drives the terminal through System Events" not in text)
        check(f"{_VI} {name}: mentions 'open -na' (Ghostty, kitty, WezTerm)", "open -na" in text)
    check(f"{_VI} README says the applet needs no permission / those terminals need no prompt",
          re.search(r"needs? no (permission|prompt)|no (permission|prompt)", rd) is not None)
    check(f"{_VI} README mentions the re-sign / ask-again note", re.search(r"re-?sign", rd) is not None)
    check(f"{_VI} Test 68 mentions terminals launched with open -na need no prompt",
          re.search(r"no (permission|prompt)|without a prompt|not prompt", sec) is not None)


def test_vli_ac19_20_shared_helpers():
    print(f"\n{_VI} AC19/AC20 shared launcher check; one lsregister constant")
    fx = _IFx("Darwin")
    try:
        bad = fx.stage('dq"x')
        a = fx.link("open", "vibe://open?project=demo", launcher=bad)
        b = fx.link("--install", launcher=bad)
        check(f"{_VI} bad launcher path: `link open` and `--install` both exit 7 'refused: launcher path'",
              a.returncode == 7 and b.returncode == 7 and "refused: launcher path" in _out(a) and "refused: launcher path" in _out(b),
              f"open rc={a.returncode} {_out(a)[:120]} / install rc={b.returncode} {_out(b)[:120]}")
        check(f"{_VI} the same message from both", _out(a).strip() == _out(b).strip(), f"{_out(a)!r} vs {_out(b)!r}")
        nx = fx.stage("not exec", executable=False)
        b2 = fx.link("--install", launcher=nx)
        check(f"{_VI} control: --install also exit 7 for a non-executable launcher", b2.returncode == 7, _out(b2)[:120])
    finally:
        fx.close("ac19")
    src = VIBE.read_text()
    check(f"{_VI} source: `_link_launcher_check` defined once and used by at least two callers",
          len(re.findall(r"^_link_launcher_check\(\)", src, re.M)) == 1 and len(re.findall(r"_link_launcher_check\b", src)) >= 3)
    check(f"{_VI} source: the LaunchServices lsregister path appears exactly once (in _LINK_LSREGISTER)",
          src.count(_LSR_FALLBACK) == 1 and "_LINK_LSREGISTER" in src, str(src.count(_LSR_FALLBACK)))
