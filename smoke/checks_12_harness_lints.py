"""task_035: harness-hygiene meta-lints, authored independently by the
Tester (spec-only read, no Generator report/diff consulted). Homed in a
new part per .vs/spec.md's Test location note: checks_06 was already at
1201 lines and these four AST-heavy lints would have pushed it past the
1,500-line cap.

Covers:
  - AC3 test_harness_spawns_never_inherit_stdin
  - AC4 test_harness_survives_open_stdin
  - AC6 successor test_extras_invocations_isolated (moved out of checks_06,
    which no longer defines it — see the removal note there)
  - AC7 test_no_fixed_sha_baselines
  - AC8 test_claude_md_testing_sentinels
  - AC9 test_gitignore_managed_block_and_site_gitignore
"""
from smoke._core import *  # noqa: F401,F403

import ast


SMOKE_DIR = Path(__file__).resolve().parent
SMOKE_FILES = sorted(SMOKE_DIR.glob("*.py"))

SPAWN_FUNC_NAMES = {
    "run", "run_bytes",
    "subprocess.run", "subprocess.Popen", "subprocess.check_output", "subprocess.call",
}
WRAPPER_FUNC_NAMES = {"run", "run_bytes"}
NONWRAPPER_SPAWN_FUNC_NAMES = SPAWN_FUNC_NAMES - WRAPPER_FUNC_NAMES


def _parse_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _call_func_name(node: ast.Call) -> str | None:
    """Dotted name of a Call's func: 'run' for a bare Name, 'subprocess.run'
    for a one-level Attribute — the only two shapes smoke/*.py uses to spawn
    a process."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f"{f.value.id}.{f.attr}"
    return None


def _add_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _enclosing_function(node: ast.AST):
    n = getattr(node, "parent", None)
    while n is not None and not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        n = getattr(n, "parent", None)
    return n


# ── AC3: no spawn inherits real stdin ──────────────────────────────────────


def test_harness_spawns_never_inherit_stdin() -> None:
    """AST-level lint (task_035 AC3): every subprocess.run/Popen/
    check_output/call Call node in smoke/*.py must carry an explicit
    input=/input_bytes=/stdin= keyword, UNLESS it is a call to the
    run()/run_bytes() wrapper (exempt because the wrapper enforces the same
    rule internally — checked below, on _core.py's actual source, not by
    assertion alone). No line-window regex: adjacent multi-line calls
    (e.g. checks_04 ~1131/1193) are matched by AST node, not by scanning
    nearby text, so they can't be misattributed to the wrong call."""
    print("\n[harness-lint AC3: every raw subprocess spawn pins stdin]")
    nonwrapper_spawns = 0
    all_spawns = 0
    violations: list[str] = []
    for path in SMOKE_FILES:
        tree = _parse_file(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_func_name(node)
            if name not in SPAWN_FUNC_NAMES:
                continue
            all_spawns += 1
            if name in WRAPPER_FUNC_NAMES:
                continue  # run()/run_bytes() enforce this internally
            nonwrapper_spawns += 1
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            if not ({"input", "input_bytes", "stdin"} & kw_names):
                violations.append(f"{path.name}:{node.lineno}")
    check("[lint] found >= 40 subprocess.run/Popen/check_output/call spawns "
          f"({nonwrapper_spawns} non-wrapper, {all_spawns} incl. run()/run_bytes())",
          nonwrapper_spawns >= 40, f"found {nonwrapper_spawns}")
    check("[lint] every non-wrapper spawn passes input=/input_bytes=/stdin=",
          len(violations) == 0,
          f"{len(violations)} bare spawn(s): {violations}")

    # Behavioural half: _core.py's run()/run_bytes() must each have exactly
    # two subprocess.run branches — one with input= (no stdin=), one with
    # stdin=subprocess.DEVNULL (no input=) — and never both keywords on one
    # branch (subprocess.run raises ValueError if both are given).
    core_tree = _parse_file(REPO / "smoke" / "_core.py")
    for fn_name in ("run", "run_bytes"):
        fn = next((n for n in ast.walk(core_tree)
                   if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
        check(f"[lint] _core.py defines {fn_name}()", fn is not None, "")
        if fn is None:
            continue
        branches = [n for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and _call_func_name(n) == "subprocess.run"]
        check(f"[lint] {fn_name}() has exactly two subprocess.run branches",
              len(branches) == 2, f"found {len(branches)}")
        saw_input_branch = saw_devnull_branch = False
        for c in branches:
            kw = {k.arg: k.value for k in c.keywords if k.arg}
            has_input = "input" in kw
            has_stdin = "stdin" in kw
            check(f"[lint] {fn_name}() branch never passes both input= and stdin=",
                  not (has_input and has_stdin), ast.dump(c)[:200])
            if has_input and not has_stdin:
                saw_input_branch = True
            if has_stdin and not has_input:
                v = kw["stdin"]
                is_devnull = isinstance(v, ast.Attribute) and v.attr == "DEVNULL"
                check(f"[lint] {fn_name}() no-input branch passes stdin=subprocess.DEVNULL",
                      is_devnull, ast.dump(v))
                saw_devnull_branch = True
        check(f"[lint] {fn_name}() has one input= branch and one DEVNULL branch",
              saw_input_branch and saw_devnull_branch,
              f"input_branch={saw_input_branch} devnull_branch={saw_devnull_branch}")


# ── AC4: a held-open, unwritten stdin must not hang the suite ─────────────


def test_harness_survives_open_stdin() -> None:
    """Regression test (task_035 AC4): the original failure was a background
    suite run with no controlling TTY hanging 55 minutes inside a `vibe
    learn` test, because a spawned child inherited the process's real,
    open-but-never-written stdin. Reproduces the shape directly: runs one
    spawn-heavy real test (the extras installer, which shells out to bash)
    in a child python3 process whose OWN stdin is an open pipe that this
    test never writes to and never closes early. If any spawn along that
    path forgot stdin=subprocess.DEVNULL, the innermost `bash`/`read` would
    block on that inherited pipe and the 60s bound below would trip."""
    print("\n[harness-lint AC4: suite survives a held-open, unwritten stdin]")
    entry = REPO / "smoke-test.py"
    script = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('_ac4_entry', {str(entry)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "mod.test_install_extras_syncs_hooks()\n"
        "print('AC4_DONE')\n"
    )
    timed_out = False
    r = None
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO),
            stdin=subprocess.PIPE,   # open, never written, never closed by us
            capture_output=True, text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
    check("[lint] AC4 child completes within 60s under an open, unwritten stdin",
          not timed_out,
          "child timed out — some spawn on this path inherited stdin and hung")
    if not timed_out:
        check("[lint] AC4 child exits 0", r.returncode == 0,
              f"rc={r.returncode} stderr={r.stderr[-500:]}")
        check("[lint] AC4 child actually reached the target test (AC4_DONE marker)",
              "AC4_DONE" in r.stdout, r.stdout[-300:])


# ── AC6 successor: every extras/setup-git/vibe-learn/firewall env= is routed ──

_CATEGORY_LABELS = {
    "install_extras": "INSTALL_EXTRAS",
    "setup_git": "SETUP_GIT_SH",
    "init_firewall": "INIT_FIREWALL sourcing",
    "vibe_learn": "vibe-learn argv",
}


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _strconsts_in(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _call_category(call: ast.Call) -> str | None:
    """Classify a Call by what it invokes, based ONLY on its positional
    args (never its keywords, so this can't be confused by an unrelated
    name appearing inside env=). AST-based per AC6 — never a line-window
    regex, so a call spanning several source lines is still one node."""
    names: set[str] = set()
    strs: set[str] = set()
    for a in call.args:
        names |= _names_in(a)
        strs |= _strconsts_in(a)
    if "INSTALL_EXTRAS" in names:
        return "install_extras"
    if "SETUP_GIT_SH" in names:
        return "setup_git"
    if "INIT_FIREWALL" in names:
        return "init_firewall"
    if "VIBE" in names and any("learn" in s for s in strs):
        return "vibe_learn"
    return None


def _value_is_routed(value: ast.AST) -> bool:
    """Direct half of the routed-through rule (AC5/AC6): the value is
    itself a call to _isolate_extras_env/_fw_run, or a dict/{**...} literal
    whose double-star merge target is such a call."""
    if isinstance(value, ast.Call):
        fname = value.func.id if isinstance(value.func, ast.Name) else None
        if fname in ("_isolate_extras_env", "_fw_run"):
            return True
    if isinstance(value, ast.Dict):
        for k, v in zip(value.keys, value.values):
            if k is None and _value_is_routed(v):
                return True
    return False


def _nearest_preceding_assign(fn, name: str, before_lineno: int):
    """Nearest same-function Assign whose target is the bare Name `name`,
    strictly before `before_lineno`. Subscript assignments (env["K"] = ...)
    are deliberately excluded — those are the permitted post-hoc overrides,
    not the routing assignment itself."""
    best = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and n.lineno < before_lineno:
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    if best is None or n.lineno > best.lineno:
                        best = n
    return best


def _env_is_routed(env_value: ast.AST, call_node: ast.Call) -> bool:
    if _value_is_routed(env_value):
        return True
    if isinstance(env_value, ast.Name):
        fn = _enclosing_function(call_node)
        if fn is not None:
            assign = _nearest_preceding_assign(fn, env_value.id, call_node.lineno)
            if assign is not None:
                return _value_is_routed(assign.value)
    return False


def test_extras_invocations_isolated() -> None:
    """AC6 successor (task_035): scans ALL smoke/*.py — not just this file,
    the bug in the pre-task_035 version of this test — for every invocation
    of INSTALL_EXTRAS, SETUP_GIT_SH, a vibe-learn argv, or INIT_FIREWALL
    sourcing, and — for every such call site that passes an env= keyword —
    requires that env be routed through _isolate_extras_env (or _fw_run,
    which itself routes; verified separately below). AST-based (ast.walk
    over Call nodes, keyword env), never a line-window regex. 'Routed
    through' is the concrete data-flow rule from CLAUDE.md § Testing: a
    direct call to the builder, OR a Name whose nearest preceding
    same-function assignment is such a call (or a dict/{**...} literal
    containing one) — later env["KEY"] = ... overrides after that
    assignment are permitted and do not break routing.

    Finding (recorded, not silently swallowed): this scan surfaces two
    PRE-EXISTING, out-of-task_035-scope gaps neither AC5 nor the Generator's
    diff touched — 3 SETUP_GIT_SH call sites (checks_08, task_017 C4) and
    ~25 vibe-learn argv call sites (checks_02, task_010/task_012) all build
    env as a bare `{**os.environ, "HOME": ...}` literal instead of routing
    through _isolate_extras_env. Both are already safe in practice (every
    one of them overrides HOME to a fresh temp dir, and neither setup-git.sh
    nor `vibe learn` ever touches GH_META_CACHE or install-claude-extras.sh),
    but AC6's text is unconditional ('anything else... fails') and these are
    real un-routed env= literals, so this check reports them rather than
    narrowing itself to make the count look clean. See test-output.log /
    summary.md for the exact tally — a cycle-2 fix is either (a) route
    those ~28 sites through the builder too, or (b) narrow AC6/AC5 to the
    categories that actually carry the GH_META_CACHE/global-gitconfig risk."""
    print("\n[extras-isolation: INSTALL_EXTRAS/SETUP_GIT_SH/vibe-learn/"
          "INIT_FIREWALL call sites route env= through _isolate_extras_env]")
    counts = {c: 0 for c in _CATEGORY_LABELS}
    violations: list[str] = []
    for path in SMOKE_FILES:
        tree = _parse_file(path)
        _add_parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            cat = _call_category(node)
            if cat is None:
                continue
            counts[cat] += 1
            env_kw = next((k for k in node.keywords if k.arg == "env"), None)
            if env_kw is None:
                continue
            if not _env_is_routed(env_kw.value, node):
                violations.append(f"{path.name}:{node.lineno} [{cat}]")

    for cat, label in _CATEGORY_LABELS.items():
        check(f"[extras-iso] >= 1 call site found for category '{label}' "
              f"({counts[cat]} found)",
              counts[cat] >= 1, f"all counts={counts}")
    check(f"[extras-iso] no bare env= at any tracked call site "
          f"({len(violations)} violation(s) across "
          f"{len({v.split(':')[0] for v in violations})} file(s))",
          len(violations) == 0,
          "unrouted call sites: " + ", ".join(violations) if violations else "")

    # Behavioural half (carried over from the pre-task_035 version of this
    # test, previously homed in checks_06): a real, isolated installer run
    # must not touch the actual global git config, and a real, sandboxed
    # setup-git.sh run must not touch the actual ~/.gitconfig either.
    hp_before = run(["git", "config", "--global", "--get", "core.hooksPath"]).stdout
    sd_before = run(["git", "config", "--global", "--get-all", "safe.directory"]).stdout
    gitconfig = Path(os.environ.get("HOME", "/home/node")) / ".gitconfig"
    bytes_before = gitconfig.read_bytes() if gitconfig.exists() else b""
    with tempfile.TemporaryDirectory() as tmp:
        env0 = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(REPO / "devcontainer"),
            "CLAUDE_CONFIG_DIR": tmp,
        }
        r = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env0),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check("[extras-iso] isolated installer run exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
    hp_after = run(["git", "config", "--global", "--get", "core.hooksPath"]).stdout
    sd_after = run(["git", "config", "--global", "--get-all", "safe.directory"]).stdout
    bytes_after = gitconfig.read_bytes() if gitconfig.exists() else b""
    check("[extras-iso] core.hooksPath unchanged", hp_before == hp_after,
          f"{hp_before!r} -> {hp_after!r}")
    check("[extras-iso] safe.directory unchanged", sd_before == sd_after,
          f"{sd_before!r} -> {sd_after!r}")
    check("[extras-iso] real ~/.gitconfig byte-identical", bytes_before == bytes_after,
          "installer wrote the real global git config despite isolation")
    # setup-git.sh's SRC/DST were once hardcoded to /home/node, so a
    # "sandbox HOME" run still overwrote the REAL ~/.gitconfig via the
    # .gitconfig-host cp (wiping core.hooksPath — content-guard detached).
    # Route this one through _isolate_extras_env too (it was a bare
    # {**os.environ, "HOME": ...} literal pre-task_035): since HOME here
    # already differs from the real process HOME, the builder leaves it
    # alone and only adds the GIT_CONFIG_GLOBAL/GH_META_CACHE defaults on
    # top — harmless, and it's now one of the compliant SETUP_GIT_SH sites
    # the scan above counts.
    with tempfile.TemporaryDirectory() as td:
        sb = Path(td) / "home"
        sb.mkdir()
        (sb / ".gitconfig-host").write_text("[user]\n\temail = t@t\n")
        r = subprocess.run(["bash", str(SETUP_GIT_SH)],
                           env=_isolate_extras_env({**os.environ, "HOME": str(sb)}),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check("[extras-iso] sandboxed setup-git.sh exits 0", r.returncode == 0,
              r.stderr[:200])
        check("[extras-iso] setup-git wrote the sandbox, not the real HOME",
              (sb / ".gitconfig").exists(), "sandbox .gitconfig missing")
    bytes_after2 = gitconfig.read_bytes() if gitconfig.exists() else b""
    check("[extras-iso] real ~/.gitconfig survives sandboxed setup-git.sh",
          bytes_before == bytes_after2,
          "setup-git.sh still writes a hardcoded /home/node path")


# ── AC7: no permanent test pins a fixed commit sha ─────────────────────────

_SHA_PIN_RE = re.compile(r'git show ([0-9a-f]{7,40}):|git diff ([0-9a-f]{7,40})\b')


def _scan_sha_pins(text: str) -> list[str]:
    """Every literal `git show <hex>:` / `git diff <hex>` hex token found as
    CONTIGUOUS TEXT in source (comments, docstrings, check() labels, and any
    literal string all count — the point is a hex sha token committed to the
    file, not just a live subprocess argv). Requires an actual hex run, so a
    variable name (checks_09's runtime `git show -s "$sha"` against its own
    throwaway repo) can never match: there's no literal hex substring there."""
    out = []
    for m in _SHA_PIN_RE.finditer(text):
        out.append(m.group(1) or m.group(2))
    return out


def test_no_fixed_sha_baselines() -> None:
    """AC7: a `git show <sha>:`/`git diff <sha>` literal hex token in
    smoke/*.py must be pre-registered in _core.py's HISTORICAL_PINS_ALLOWED
    — task_028/029's tests pinned a fixed commit sha as "the" baseline and
    broke on the very next commit touching the pinned path. Text-scan
    (regex), not AST: the rule is about what literal bytes are committed to
    the file, not about reconstructing subprocess argv — a sha split across
    separate quoted list elements (`["git","show", f"{sha}:{p}"]`) still
    isn't a contiguous 'git show <hex>:' text run and so isn't flagged by
    itself, but every current sha pin in this repo also appears adjacent to
    literal 'git show'/'git diff' text (a comment or a check() label), which
    this DOES catch — so the allowlist requirement is not vacuous here."""
    print("\n[harness-lint AC7: no un-registered git-show/git-diff sha pin]")
    hits: list[tuple[str, str]] = []
    for path in SMOKE_FILES:
        for sha in _scan_sha_pins(path.read_text()):
            hits.append((path.name, sha))
    unregistered = [(f, s) for f, s in hits if s not in HISTORICAL_PINS_ALLOWED]
    check(f"[lint] every git show/diff <sha> literal is registered "
          f"({len(hits)} literal(s) found, {len(unregistered)} unregistered)",
          len(unregistered) == 0, f"unregistered: {unregistered}")
    check("[lint] the sole documented entry '3b23b19' is present in the allowlist",
          "3b23b19" in HISTORICAL_PINS_ALLOWED and
          bool(HISTORICAL_PINS_ALLOWED.get("3b23b19", "").strip()),
          str(HISTORICAL_PINS_ALLOWED))

    # Positive control: a synthetic literal sha in a throwaway copy of a
    # smoke file (never the real tree) IS caught by the same scanner
    # function used above — proves the check isn't vacuously passing
    # because nothing on the current tree happens to be un-registered.
    with tempfile.TemporaryDirectory() as td:
        synth_show_sha = "dead" + "bee1"
        synth_diff_sha = "cafebabe" * 5
        fake = Path(td) / "checks_99_synthetic.py"
        # A comment-shaped baseline reference — the same textual shape the
        # real 3b23b19 pin appears in (a comment naming the commit next to
        # literal "git show"/"git diff" text) — so this is a faithful
        # positive control, not a strawman. Built from f-string interpolation
        # rather than a literal in THIS file's own source, so this file's
        # own text never contains a contiguous "git show <hex>:" run itself
        # (which would otherwise trip this very lint on itself).
        fake.write_text(
            "from smoke._core import *\n"
            f"# baseline: git show {synth_show_sha}:some/path\n"
            f"# also see: git diff {synth_diff_sha}\n"
            "def test_fake():\n"
            "    pass\n"
        )
        synth_hits = _scan_sha_pins(fake.read_text())
        check("[lint] synthetic comment-shaped 'git show <hex>:' pin IS caught",
              synth_show_sha in synth_hits, str(synth_hits))
        check("[lint] synthetic comment-shaped 'git diff <hex>' pin IS caught",
              synth_diff_sha in synth_hits, str(synth_hits))
        check("[lint] the synthetic shas would fail unregistered (not in the real allowlist)",
              synth_show_sha not in HISTORICAL_PINS_ALLOWED, "")


# ── AC8: CLAUDE.md documents the three task_035 rules ──────────────────────


def test_claude_md_testing_sentinels() -> None:
    """AC8: CLAUDE.md § Testing documents task_035's three rules, each with
    a grep-able sentinel substring, so a future reader (or drift-check) can
    find them without re-deriving the reasoning."""
    print("\n[harness-lint AC8: CLAUDE.md Testing sentinels]")
    md = (REPO / "CLAUDE.md").read_text()
    idx = md.find("## Testing")
    check("[lint] CLAUDE.md has a '## Testing' section", idx != -1, "")
    if idx == -1:
        return
    next_idx = md.find("\n## ", idx + 1)
    section = md[idx: next_idx if next_idx != -1 else len(md)]
    check("[lint] § Testing documents the stdin rule ('< /dev/null')",
          "< /dev/null" in section, "")
    check("[lint] § Testing documents the sandbox-routing rule ('_isolate_extras_env')",
          "_isolate_extras_env" in section, "")
    check("[lint] § Testing documents the sha-pin rule ('HISTORICAL_PINS_ALLOWED')",
          "HISTORICAL_PINS_ALLOWED" in section, "")


# ── AC9: .gitignore hygiene ─────────────────────────────────────────────────


def test_gitignore_managed_block_and_site_gitignore() -> None:
    """AC9: root .gitignore carries exactly one '.vibe/' and one
    '.claude/settings.local.json' line, both inside the vibe-managed block
    (no leftover hand-written duplicate above it), with the managed-block
    markers intact so install-claude-extras.sh's ensure_project_gitignore
    still finds its block and stays idempotent; site/.gitignore is exactly
    the expected 4-line content. Compared against a literal expected
    string, NOT `git show <sha>:site/.gitignore` — using a sha here would
    trip this file's own AC7 sibling lint."""
    print("\n[harness-lint AC9: .gitignore managed block + site/.gitignore]")
    root_gi = (REPO / ".gitignore").read_text()
    open_marker = "# >>> vibe-managed runtime exclusions (auto-added; do not edit body) >>>"
    close_marker = "# <<< vibe-managed <<<"
    check("[lint] managed-block open marker present", open_marker in root_gi, "")
    check("[lint] managed-block close marker present", close_marker in root_gi, "")

    lines = root_gi.splitlines()
    vibe_lines = [ln for ln in lines if ln.strip() == ".vibe/"]
    settings_lines = [ln for ln in lines if ln.strip() == ".claude/settings.local.json"]
    check("[lint] exactly one '.vibe/' line in .gitignore",
          len(vibe_lines) == 1, f"found {len(vibe_lines)}: {vibe_lines}")
    check("[lint] exactly one '.claude/settings.local.json' line in .gitignore",
          len(settings_lines) == 1, f"found {len(settings_lines)}: {settings_lines}")

    if open_marker in root_gi and close_marker in root_gi:
        block = root_gi[root_gi.index(open_marker): root_gi.index(close_marker)]
        check("[lint] '.vibe/' lives inside the managed block",
              ".vibe/" in block.splitlines(), block)
        check("[lint] '.claude/settings.local.json' lives inside the managed block",
              "settings.local.json" in block, block)

    expected_site_gi = "node_modules/\ndist/\n.astro/\npublic/vendor/\n"
    actual_site_gi = (REPO / "site" / ".gitignore").read_text()
    check("[lint] site/.gitignore is exactly the expected 4-line content",
          actual_site_gi == expected_site_gi,
          f"actual: {actual_site_gi!r} expected: {expected_site_gi!r}")
