"""task_049: `vibe --agent codex` — a Codex-led container launch behind the
liveness gate (plan item 7). Tester-authored, independent read of
.vs/spec.md end-to-end; no generator report/diff/scratch-tests consulted.

AC7 test list covered here:
  - _agent_resolve precedence matrix (flag > file > env > default) plus the
    file rung's failure modes (malformed content, tracked, symlinked file,
    symlinked .vibe dir) — each a single ⚠ line with fall-through.
  - parser: `--agent bogus` / bare `--agent` -> usage + exit 1, zero
    devcontainer calls.
  - argv golden tests: `--agent codex` granted -> the AC3 devcontainer exec
    argv exactly, the Claude-only pre-launch line, and the AC5 agent header
    line; `--agent codex` denied -> the AC2 refusal, zero devcontainer
    calls; `--agent claude` / no flag -> the unchanged launch_claude argv,
    with the codex mount banner (when granted) but NO agent line.
  - source-shape: launch_codex_plain has `&`/`wait`, no vibe_stall_watchdog;
    launch_claude is byte-for-byte unchanged vs HEAD.
  - codex-entry.sh offline: missing requirements.toml, missing login-dir,
    liveness failure (pass-through text), success (exec's the stub with the
    args after `--`); no `dangerously`, no ` -c ` anywhere in the script.
  - static/doc shape: Dockerfile COPY --chown=root:root + chmod +x,
    codex-guard-liveness.sh's ownership list, the managed .gitignore block,
    README's Codex-led sessions section, MANUAL-TESTS Test 55's codex-led
    block, docs/codex-integration-plan.md item 7.

The launcher's post-VIBE_SOURCE_ONLY-guard code (launch_claude, launch_codex,
launch_codex_plain, the AC2 gate, the AC5 header block) is never reached by
sourcing vibe with VIBE_SOURCE_ONLY=1 (the guard returns before it, and no
existing test in this suite runs the full launcher end-to-end through image
build/GitHub setup to reach it either). So the argv/header/pre-launch-line
tests below extract those exact snippets from the CURRENT vibe source text
(same technique smoke's own _task022_extract_function_body already uses
elsewhere in this suite, just executed rather than only shape-checked) and
run them for real against a devcontainer PATH stub, with the real
_agent_resolve/_codex_desired_source/_codex_dir_mode_warning sourced from
vibe itself (VIBE_SOURCE_ONLY=1) so the fixture's registry/marker/config
plumbing is exercised through the production functions, not reimplemented.
"""
from smoke._core import *  # noqa: F401,F403
from smoke._core import _source_vibe_call
from smoke.checks_17_delegation import _codex_git_ws, _codex_rc_call, _codex_docker_stub

CODEX_ENTRY = REPO / "devcontainer" / "codex-entry.sh"
LIVENESS_SH = REPO / "devcontainer" / "codex-guard-liveness.sh"
CODEX_INTEGRATION_PLAN_MD = REPO / "docs" / "codex-integration-plan.md"
REQUIREMENTS_TOML = REPO / "devcontainer" / "codex" / "requirements.toml"


def _flat(text: str) -> str:
    return " ".join(text.split())


# ── extraction helpers: pull exact snippets out of the CURRENT vibe source ──
# so the golden-argv tests exercise the real production text, not a
# hand-copied reimplementation of it.

def _extract_func(src: str, name: str) -> str:
    """Same technique as checks_06's test_vibe_supervised_launch_text /
    checks_10's _task022_extract_function_body, generalised: the literal text
    from '<name>() {' to the first subsequent line that is exactly '}'."""
    m = re.search(r'^' + re.escape(name) + r'\(\) \{(.+?)^\}', src, re.MULTILINE | re.DOTALL)
    if not m:
        raise AssertionError(f"{name}() {{ ... }} not found in vibe source")
    return f"{name}() {{{m.group(1)}}}"


def _extract_lines(src: str, start_line: str, end_line: str = "fi") -> str:
    """The literal text from the line matching start_line exactly (no
    leading/trailing whitespace stripped — callers pass the exact top-level
    line) to the first subsequent line that is exactly end_line."""
    lines = src.splitlines()
    start = next((i for i, l in enumerate(lines) if l == start_line), None)
    if start is None:
        raise AssertionError(f"start marker not found: {start_line!r}")
    end = next((j for j in range(start, len(lines)) if lines[j] == end_line), None)
    if end is None:
        raise AssertionError(f"end marker not found after start: {end_line!r}")
    return "\n".join(lines[start:end + 1])


GATE_START = 'if [ "$LEAD_AGENT" = "codex" ] && [ -z "$(_codex_desired_source "$WORKSPACE" 2>/dev/null)" ]; then'
HEADER_START = '_codex_banner="$(_codex_desired_source "$WORKSPACE" 2>/dev/null)"'


def _agent_devcontainer_stub(bindir, log) -> None:
    """A `devcontainer` PATH stub: records argv[1:] as one JSON line per call
    (so the golden-argv assertions compare exact lists, never reconstructed
    shell-quoting)."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "devcontainer"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
    )
    stub.chmod(0o755)


def _agent_calls(log) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line]


def _agent_composed_call(home, ws, bindir, agent_arg: str, body: str):
    """Source vibe (VIBE_SOURCE_ONLY=1) with HOME=home and PATH prefixed with
    bindir, set up WORKSPACE/LEAD_AGENT/OVERRIDE_CONFIG/CLAUDE_MODEL_ARGS,
    then run `body` (extracted vibe snippets, spliced in verbatim)."""
    call = (
        f'WORKSPACE={shlex.quote(str(ws))}\n'
        f'LEAD_AGENT="$(_agent_resolve {shlex.quote(agent_arg)} "$WORKSPACE")"\n'
        'OVERRIDE_CONFIG=/tmp/fixture-override.json\n'
        'CLAUDE_MODEL_ARGS=""\n'
        f'{body}\n'
    )
    env = {"HOME": str(home), "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
    return _source_vibe_call(env, call)


# ═══════════════════════════════════════════════════════════════════════════
# AC1: _agent_resolve precedence matrix
# ═══════════════════════════════════════════════════════════════════════════

def _agent_write_file(ws, content: str):
    (ws / ".vibe").mkdir(parents=True, exist_ok=True)
    f = ws / ".vibe" / "agent"
    f.write_text(content)
    return f


def _agent_resolve_call(home, flag: str, ws, vibe_config=None):
    env = {"HOME": str(home)}
    if vibe_config is not None:
        env["VIBE_CONFIG"] = str(vibe_config)
    call = f'printf "%s" "$(_agent_resolve {shlex.quote(flag)} {shlex.quote(str(ws))})"'
    return _source_vibe_call(env, call)


def test_agent_resolve_precedence_matrix():
    print("\n[agent] AC1: _agent_resolve precedence — flag > file > env > default, "
          "and the file rung's fail-closed cases")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        ws = _codex_git_ws(root)

        # Nothing set at all -> the hard default, silently.
        r = _agent_resolve_call(home, "", ws)
        check("[agent] nothing set -> default 'claude', silent",
              r.returncode == 0 and r.stdout == "claude" and r.stderr == "",
              repr(r.stdout) + "|" + r.stderr)

        # VIBE_AGENT alone (no file, no flag) -> env beats default.
        cfg = home / ".vibe" / "config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("VIBE_AGENT=codex\n")
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] VIBE_AGENT=codex alone -> 'codex' (env beats default)",
              r.returncode == 0 and r.stdout == "codex" and r.stderr == "",
              repr(r.stdout) + "|" + r.stderr)

        # Untracked file 'claude' beats VIBE_AGENT=codex.
        _agent_write_file(ws, "claude\n")
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] untracked file 'claude' beats VIBE_AGENT=codex (file beats env)",
              r.returncode == 0 and r.stdout == "claude" and r.stderr == "",
              repr(r.stdout) + "|" + r.stderr)

        # Flag beats file ('claude') AND env ('codex') outright, either way.
        r = _agent_resolve_call(home, "codex", ws, vibe_config=cfg)
        check("[agent] --agent codex beats file 'claude' and VIBE_AGENT=codex",
              r.returncode == 0 and r.stdout == "codex" and r.stderr == "",
              repr(r.stdout) + "|" + r.stderr)
        r2 = _agent_resolve_call(home, "claude", ws, vibe_config=cfg)
        check("[agent] --agent claude wins outright too",
              r2.returncode == 0 and r2.stdout == "claude" and r2.stderr == "",
              repr(r2.stdout) + "|" + r2.stderr)

        # Comment + blank lines are skipped; first real content line wins.
        _agent_write_file(ws, "# pick codex for this project\n\ncodex\n")
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] file's leading comment/blank lines are skipped -> 'codex'",
              r.returncode == 0 and r.stdout == "codex" and r.stderr == "",
              repr(r.stdout) + "|" + r.stderr)

        # Malformed content -> ONE warning, falls through to env (codex).
        _agent_write_file(ws, "bogus\n")
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] malformed file content -> one ⚠, falls through to VIBE_AGENT (codex)",
              r.returncode == 0 and r.stdout == "codex" and r.stderr.count("⚠") == 1 and
              "its first content line is 'bogus'" in r.stderr,
              repr(r.stdout) + "|" + r.stderr)

        # Tracked file -> ONE warning (COMMITTED), falls through.
        _agent_write_file(ws, "codex\n")
        run(["git", "-C", str(ws), "add", "-f", ".vibe/agent"])
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] tracked file -> one ⚠ (COMMITTED), falls through to VIBE_AGENT (codex)",
              r.returncode == 0 and r.stdout == "codex" and r.stderr.count("⚠") == 1 and
              "COMMITTED" in r.stderr, repr(r.stdout) + "|" + r.stderr)
        run(["git", "-C", str(ws), "rm", "-q", "--cached", ".vibe/agent"])

        # Symlinked FILE -> ONE warning (symlink), falls through.
        (ws / ".vibe" / "agent").unlink()
        real_val = root / "real-agent-value"
        real_val.write_text("codex\n")
        (ws / ".vibe" / "agent").symlink_to(real_val)
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] symlinked file -> one ⚠ ('it is a symlink'), falls through",
              r.returncode == 0 and r.stdout == "codex" and r.stderr.count("⚠") == 1 and
              "it is a symlink" in r.stderr, repr(r.stdout) + "|" + r.stderr)
        (ws / ".vibe" / "agent").unlink()

        # Symlinked .vibe DIRECTORY itself -> ONE warning ('.vibe is a
        # symlink'), even though the file it resolves to is a plain file.
        real_dir = root / "real-vibe-dir"; real_dir.mkdir()
        (real_dir / "agent").write_text("codex\n")
        import shutil
        shutil.rmtree(ws / ".vibe")
        (ws / ".vibe").symlink_to(real_dir)
        r = _agent_resolve_call(home, "", ws, vibe_config=cfg)
        check("[agent] symlinked .vibe dir -> one ⚠ ('.vibe is a symlink'), falls through",
              r.returncode == 0 and r.stdout == "codex" and r.stderr.count("⚠") == 1 and
              ".vibe is a symlink" in r.stderr, repr(r.stdout) + "|" + r.stderr)
        (ws / ".vibe").unlink()

        # A bogus --agent flag value warns and falls through too (not fatal
        # here — parse_vibe_args, tested separately below, is what makes an
        # actually-invalid CLI flag a hard usage error before this is ever
        # reached).
        r = _agent_resolve_call(home, "bogus", ws, vibe_config=cfg)
        check("[agent] bogus flag value -> one ⚠, falls through (no file now) to VIBE_AGENT (codex)",
              r.returncode == 0 and r.stdout == "codex" and r.stderr.count("⚠") == 1 and
              "neither 'claude' nor 'codex'" in r.stderr, repr(r.stdout) + "|" + r.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# AC1: parser — `--agent bogus` / bare `--agent` -> usage + exit 1
# ═══════════════════════════════════════════════════════════════════════════

def test_agent_parser_errors_no_devcontainer_call():
    print("\n[agent] AC1: `vibe --agent bogus` / bare `--agent` -> usage on stderr, "
          "exit 1, zero devcontainer calls")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        bindir = tmp / "bin"
        log = tmp / "devcontainer.log"
        _agent_devcontainer_stub(bindir, log)
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config",
               "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
        for args in (["--agent", "bogus"], ["--agent"]):
            r = run(["bash", str(VIBE), *args], env=env, cwd=home)
            label = " ".join(args)
            check(f"[agent] vibe {label}: exit 1", r.returncode == 1, r.stdout + "|" + r.stderr)
            check(f"[agent] vibe {label}: usage message on stderr, nothing on stdout",
                  "--agent needs 'claude' or 'codex', got:" in r.stderr and not r.stdout,
                  r.stdout + "|" + r.stderr)
            check(f"[agent] vibe {label}: no devcontainer call", not log.exists(), "")


# ═══════════════════════════════════════════════════════════════════════════
# AC1 help text
# ═══════════════════════════════════════════════════════════════════════════

def test_agent_help_mentions_flag():
    print("\n[agent] AC1: `vibe --help` documents --agent")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
        check("[agent] vibe --help exits 0", r.returncode == 0, r.stderr[:300])
        check("[agent] vibe --help documents --agent <claude|codex>",
              "--agent <claude|codex>" in r.stdout, r.stdout[:2000])


# ═══════════════════════════════════════════════════════════════════════════
# AC2/AC3/AC5: real-launcher-text argv golden tests
# ═══════════════════════════════════════════════════════════════════════════

def _codex_grant_fixture(root):
    """A throwaway git ws with the marker, registry line and fixture
    ~/.codex present — everything _codex_desired_source needs to be
    non-empty."""
    home = root / "home"; home.mkdir()
    ws = _codex_git_ws(root)
    (ws / ".vibe-allow-codex").write_text("")
    registry = home / ".vibe" / "codex-allow"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(str(ws) + "\n")
    registry.chmod(0o600)
    codex_dir = home / ".codex"; codex_dir.mkdir(); codex_dir.chmod(0o700)
    return home, ws


def test_agent_codex_argv_granted():
    print("\n[agent] AC3/AC5: --agent codex, mount granted -> exact devcontainer "
          "exec argv, the Claude-only pre-launch line, the agent header line")
    vibe_src = VIBE.read_text()
    gate = _extract_lines(vibe_src, GATE_START)
    header = _extract_lines(vibe_src, HEADER_START)
    launch_codex = _extract_func(vibe_src, "launch_codex")
    launch_codex_plain = _extract_func(vibe_src, "launch_codex_plain")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home, ws = _codex_grant_fixture(root)
        bindir = root / "bin"
        log = root / "devcontainer.log"
        _agent_devcontainer_stub(bindir, log)
        _codex_docker_stub(bindir, root / "docker.log")

        body = (
            f'{gate}\n'
            f'{header}\n'
            f'{launch_codex}\n'
            f'{launch_codex_plain}\n'
            'CLAUDE_EXIT=0\n'
            'exec 9<&0\n'
            'if [ "$LEAD_AGENT" = "codex" ]; then\n'
            '  launch_codex_plain\n'
            '  exit "$CLAUDE_EXIT"\n'
            'fi\n'
            'echo GATE_DID_NOT_ROUTE_TO_CODEX\n'
        )
        r = _agent_composed_call(home, ws, bindir, "codex", body)
        check("[agent] granted --agent codex: exits 0", r.returncode == 0, r.stdout + "|" + r.stderr)
        check("[agent] granted --agent codex: routed through the codex branch",
              "GATE_DID_NOT_ROUTE_TO_CODEX" not in r.stdout, r.stdout)
        check("[agent] granted --agent codex: AC5 header line printed",
              "     agent   : codex (policy: /etc/codex, gate: codex-guard-liveness)" in r.stdout,
              r.stdout)
        check("[agent] granted --agent codex: codex mount banner also printed",
              f"@ {home / '.codex'}" in r.stdout, r.stdout)
        check("[agent] granted --agent codex: interactive supervision hint printed",
              "codex-led session: interactive; use --codex-run <prompt-file> for supervised work" in r.stdout,
              r.stdout)
        calls = _agent_calls(log)
        check("[agent] granted --agent codex: exactly one devcontainer call", len(calls) == 1, str(calls))
        if calls:
            expected = [
                "exec", "--workspace-folder", str(ws), "--override-config", "/tmp/fixture-override.json",
                # Astra review (iter 7): both Bash interpreters start with BASH_ENV/ENV
                # removed and a pinned PATH, so no inherited start-up file can run
                # before codex-entry does.
                "/usr/bin/env", "-u", "BASH_ENV", "-u", "ENV",
                "/bin/bash", "--noprofile", "--norc", "-c",
                "exec /usr/bin/env -u BASH_ENV -u ENV PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/share/npm-global/bin "
                "SHELL=/bin/bash LC_ALL=C.UTF-8 LANG=C.UTF-8 CODEX_HOME=/home/node/.codex "
                "/usr/local/bin/codex-entry",
            ]
            check("[agent] granted --agent codex: devcontainer exec argv equals AC3 exactly",
                  calls[0] == expected, str(calls[0]))


def test_agent_codex_argv_denied():
    print("\n[agent] AC2: --agent codex, mount NOT granted -> the AC2 refusal, "
          "zero devcontainer calls, before any launch code runs")
    vibe_src = VIBE.read_text()
    gate = _extract_lines(vibe_src, GATE_START)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        ws = _codex_git_ws(root)  # no marker, no registry, no ~/.codex
        bindir = root / "bin"
        log = root / "devcontainer.log"
        _agent_devcontainer_stub(bindir, log)

        body = f'{gate}\necho GATE_DID_NOT_REFUSE\n'
        r = _agent_composed_call(home, ws, bindir, "codex", body)
        check("[agent] denied --agent codex: exit 1", r.returncode == 1, r.stdout + "|" + r.stderr)
        check("[agent] denied --agent codex: exact AC2 message on stderr",
              "  ✗ --agent codex needs the Codex login mount: create the untracked "
              ".vibe-allow-codex marker in the project and run 'vibe codex allow' on the Mac, "
              "then relaunch" in r.stderr, r.stderr)
        check("[agent] denied --agent codex: nothing on stdout, gate actually exited",
              r.stdout == "", r.stdout)
        check("[agent] denied --agent codex: zero devcontainer calls", not log.exists(), "")


def test_agent_claude_argv_default_and_flag():
    print("\n[agent] AC3/AC5: --agent claude and no flag -> unchanged launch_claude argv, "
          "no agent header line even when the codex mount is granted")
    vibe_src = VIBE.read_text()
    gate = _extract_lines(vibe_src, GATE_START)
    header = _extract_lines(vibe_src, HEADER_START)
    launch_claude = _extract_func(vibe_src, "launch_claude")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Codex mount IS granted here on purpose (AC5: "when claude, nothing
        # new is printed" must hold even though the codex banner itself is
        # unrelated to LEAD_AGENT and still shows).
        home, ws = _codex_grant_fixture(root)
        bindir = root / "bin"

        # _agent_resolve must land on 'claude' both ways before we even look
        # at the launch/header text.
        for flag in ("", "claude"):
            r = _agent_resolve_call(home, flag, ws)
            check(f"[agent] _agent_resolve({flag!r}) -> 'claude'",
                  r.returncode == 0 and r.stdout == "claude", repr(r.stdout) + "|" + r.stderr)

        for flag in ("", "claude"):
            log = root / f"devcontainer-{flag or 'default'}.log"
            _agent_devcontainer_stub(bindir, log)
            body = (
                f'{gate}\n'
                f'{header}\n'
                f'{launch_claude}\n'
                'launch_claude "" ""\n'
            )
            r = _agent_composed_call(home, ws, bindir, flag, body)
            label = flag or "(no flag)"
            check(f"[agent] --agent {label}: exits 0", r.returncode == 0, r.stdout + "|" + r.stderr)
            check(f"[agent] --agent {label}: codex mount banner still printed (AC5 unrelated to agent)",
                  f"@ {home / '.codex'}" in r.stdout, r.stdout)
            check(f"[agent] --agent {label}: NO agent header line",
                  "agent   :" not in r.stdout, r.stdout)
            calls = _agent_calls(log)
            check(f"[agent] --agent {label}: exactly one devcontainer call", len(calls) == 1, str(calls))
            if calls:
                expected = [
                    "exec", "--workspace-folder", str(ws), "--override-config",
                    "/tmp/fixture-override.json", "/bin/bash", "--noprofile", "--norc", "-c",
                    "exec env SHELL=/bin/bash LC_ALL=C.UTF-8 LANG=C.UTF-8 claude "
                    "--permission-mode bypassPermissions",
                ]
                check(f"[agent] --agent {label}: launch_claude argv is the unchanged golden string",
                      calls[0] == expected, str(calls[0]))


# ═══════════════════════════════════════════════════════════════════════════
# AC3: source-shape — launch_codex_plain / launch_codex, launch_claude vs HEAD
# ═══════════════════════════════════════════════════════════════════════════

def test_launch_codex_source_shape():
    print("\n[agent] AC3 source shape: launch_codex mirrors launch_claude's exec "
          "shape; launch_codex_plain backgrounds+waits with no supervision")
    vibe_src = VIBE.read_text()
    launch_codex = _extract_func(vibe_src, "launch_codex")
    check("[agent] launch_codex body has 'exec devcontainer exec'",
          "exec devcontainer exec" in launch_codex, launch_codex)
    check("[agent] launch_codex takes no model/approval/sandbox flags (no CLAUDE_MODEL_ARGS)",
          "CLAUDE_MODEL_ARGS" not in launch_codex and "--model" not in launch_codex and
          "approval" not in launch_codex and "sandbox" not in launch_codex, launch_codex)
    check("[agent] launch_codex starts /usr/local/bin/codex-entry with CODEX_HOME set",
          "CODEX_HOME=/home/node/.codex /usr/local/bin/codex-entry" in launch_codex, launch_codex)

    plain = _extract_func(vibe_src, "launch_codex_plain")
    check("[agent] launch_codex_plain body contains '&' (backgrounded)",
          re.search(r'launch_codex\b.*&', plain) is not None, plain)
    check("[agent] launch_codex_plain body contains 'wait'",
          re.search(r'\bwait\b', plain) is not None, plain)
    check("[agent] launch_codex_plain body has NO vibe_stall_watchdog",
          "vibe_stall_watchdog" not in plain, plain)
    check("[agent] launch_codex_plain has NO heartbeat/marker seeding",
          "AUTO_RESUME_MARKER" not in plain and "auto_resume_heartbeat_write" not in plain, plain)
    check("[agent] launch_codex_plain sets CLAUDE_EXIT",
          "CLAUDE_EXIT=" in plain, plain)
    check("[agent] launch_codex_plain prints the explicit supervision hint",
          "use --codex-run <prompt-file> for supervised work" in plain, plain)


def test_launch_claude_unchanged_vs_head():
    print("\n[agent] AC3: launch_claude is byte-for-byte unchanged vs HEAD (no pinned sha)")
    r = run(["git", "show", "HEAD:vibe"], cwd=REPO)
    check("[agent] git show HEAD:vibe succeeds", r.returncode == 0, r.stderr)
    if r.returncode != 0:
        return
    head_func = _extract_func(r.stdout, "launch_claude")
    working_func = _extract_func(VIBE.read_text(), "launch_claude")
    # Task binding adds one opt-in argv prefix. Its empty/default expansion and
    # validated bound value are exercised behaviourally in checks_29; the
    # existing Claude invocation must otherwise remain byte-identical.
    without_binding = lambda value: value.replace('"${TASK_BIND_ENV[@]}" ', '')
    check("[agent] launch_claude unchanged apart from optional task-binding argv",
          without_binding(head_func) == without_binding(working_func),
          f"HEAD:\n{head_func}\n---\nworking tree:\n{working_func}")


# ═══════════════════════════════════════════════════════════════════════════
# AC4: devcontainer/codex-entry.sh, offline
# ═══════════════════════════════════════════════════════════════════════════

def _entry_fixture(tmp):
    root = tmp / "etc-codex"; root.mkdir()
    root_req = root / "requirements.toml"
    root_req.write_text(REQUIREMENTS_TOML.read_text())
    bindir = tmp / "bin"; bindir.mkdir()
    login_dir = tmp / "login"; login_dir.mkdir()
    codex_stub = bindir / "codex"
    argv_log = tmp / "codex-argv.log"
    codex_stub.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"open({str(argv_log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
        "print('CODEX STUB RAN')\n"
    )
    codex_stub.chmod(0o755)
    return root, bindir, login_dir, codex_stub, argv_log


def _entry_liveness_stub(bindir, ok: bool, log):
    p = bindir / "codex-guard-liveness"
    body = "#!/bin/bash\n" + f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
    if ok:
        body += "printf 'ok stub-check\\n'\nexit 0\n"
    else:
        body += "printf 'LIVENESS FAILED: fixture\\n' >&2\nexit 1\n"
    p.write_text(body)
    p.chmod(0o755)
    return p


def _run_entry(root, bindir, login_dir, codex_path, extra_args=(), entry_dir=None):
    """Run a COPY of codex-entry placed in `bindir` (or `entry_dir`): after
    Astra's re-review the entry only trusts a gate that is a regular file in
    its OWN directory, so the fixture chain must hold the entry and its stub
    gate side by side, exactly like /usr/local/bin in the image."""
    home = Path(entry_dir or bindir)
    entry_copy = home / "codex-entry"
    if not entry_copy.exists():
        entry_copy.write_text(CODEX_ENTRY.read_text())
        entry_copy.chmod(0o755)
    args = ["--root", str(root), "--bin", str(bindir), "--login-dir", str(login_dir),
            "--codex", str(codex_path), "--", *extra_args]
    return run(["bash", str(entry_copy), *args])


def test_codex_entry_offline_refusals_and_success():
    print("\n[agent] AC4: codex-entry.sh offline — refusals and the success path")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, login_dir, codex_stub, argv_log = _entry_fixture(tmp)
        liveness_log = tmp / "liveness-argv.log"

        # (a) missing requirements.toml
        (root / "requirements.toml").unlink()
        r = _run_entry(root, bindir, login_dir, codex_stub)
        check("[agent] entry: missing requirements.toml -> exit 1",
              r.returncode == 1, r.stdout + "|" + r.stderr)
        check("[agent] entry: missing requirements.toml -> named reason",
              "codex-led session refused:" in r.stderr and "requirements.toml is missing" in r.stderr,
              r.stderr)
        (root / "requirements.toml").write_text(REQUIREMENTS_TOML.read_text())

        # (a) missing login dir
        import shutil
        shutil.rmtree(login_dir)
        r = _run_entry(root, bindir, login_dir, codex_stub)
        check("[agent] entry: missing login dir -> exit 1", r.returncode == 1, r.stdout + "|" + r.stderr)
        check("[agent] entry: missing login dir -> named reason (vibe codex allow)",
              "codex-led session refused:" in r.stderr and "is not a directory" in r.stderr and
              "vibe codex allow" in r.stderr, r.stderr)
        login_dir.mkdir()

        # (a) liveness gate fails -> its own stderr passed through, THEN the refusal
        _entry_liveness_stub(bindir, ok=False, log=liveness_log)
        r = _run_entry(root, bindir, login_dir, codex_stub)
        check("[agent] entry: liveness failure -> exit 1", r.returncode == 1, r.stdout + "|" + r.stderr)
        check("[agent] entry: liveness failure -> stub's own text passed through unchanged",
              "LIVENESS FAILED: fixture" in r.stderr, r.stderr)
        check("[agent] entry: liveness failure -> the entry's own refusal line follows",
              "codex-led session refused: the guard chain did not prove itself" in r.stderr, r.stderr)
        check("[agent] entry: liveness failure -> codex never executed", not argv_log.exists(), "")

        # (b) success: liveness passes -> exec's codex with args after `--`
        _entry_liveness_stub(bindir, ok=True, log=liveness_log)
        r = _run_entry(root, bindir, login_dir, codex_stub, extra_args=["--flag", "value"])
        check("[agent] entry: success -> exit 0", r.returncode == 0, r.stdout + "|" + r.stderr)
        check("[agent] entry: success -> liveness's own 'ok' output passed through",
              "ok stub-check" in r.stdout, r.stdout)
        check("[agent] entry: success -> the proven line printed before exec",
              "codex-led session: guard chain proven, starting codex" in r.stdout, r.stdout)
        calls = [json.loads(l) for l in argv_log.read_text().splitlines()] if argv_log.exists() else []
        check("[agent] entry: success -> codex exec'd exactly once with the args after --",
              calls == [["--flag", "value"]], str(calls))
        check("[agent] entry: success -> liveness invoked with --root/--bin and our --codex",
              liveness_log.exists() and str(root) in liveness_log.read_text() and
              str(bindir) in liveness_log.read_text() and str(codex_stub) in liveness_log.read_text(),
              liveness_log.read_text() if liveness_log.exists() else "<no log>")

        # Astra review (iter 7): the gate named by --bin is AUTHENTICATED before it
        # is believed — same owner as the entry script and not group/other-writable.
        # A writable gate is refused before it runs, even though it would exit 0.
        writable = _entry_liveness_stub(bindir, ok=True, log=liveness_log)
        writable.chmod(0o775)
        if argv_log.exists():
            argv_log.unlink()
        r = _run_entry(root, bindir, login_dir, codex_stub, ("--x",))
        check("[agent] entry: a group-writable liveness gate is refused, exit 1",
              r.returncode == 1 and "group- or other-writable" in r.stderr, r.stdout + "|" + r.stderr)
        check("[agent] entry: refused gate -> codex never exec'd", not argv_log.exists(), "")
        writable.chmod(0o755)

        # Astra re-review: identity, not just ownership. A symlinked gate (even
        # to a root-owned 0755 binary) and a gate that is not beside the entry
        # point are both refused before anything runs.
        gate = bindir / "codex-guard-liveness"
        gate.unlink()
        gate.symlink_to("/usr/bin/true")
        r = _run_entry(root, bindir, login_dir, codex_stub, ("--x",))
        check("[agent] entry: a symlinked gate is refused, exit 1",
              r.returncode == 1 and "symlink" in r.stderr, r.stdout + "|" + r.stderr)
        check("[agent] entry: symlinked gate -> codex never exec'd", not argv_log.exists(), "")
        gate.unlink()
        _entry_liveness_stub(bindir, ok=True, log=liveness_log)
        elsewhere = tmp / "elsewhere"; elsewhere.mkdir()
        r = _run_entry(root, bindir, login_dir, codex_stub, ("--x",), entry_dir=elsewhere)
        check("[agent] entry: --bin naming a directory other than the entry's own is refused, exit 1",
              r.returncode == 1 and "beside this entry point" in r.stderr, r.stdout + "|" + r.stderr)
        check("[agent] entry: foreign --bin -> codex never exec'd", not argv_log.exists(), "")


def test_codex_entry_no_dangerously_no_dash_c():
    print("\n[agent] AC4: codex-entry.sh never spells --dangerously... or a literal ` -c `")
    src = CODEX_ENTRY.read_text()
    check("[agent] codex-entry.sh contains no 'dangerously'", "dangerously" not in src, "")
    check("[agent] codex-entry.sh contains no literal ' -c '", " -c " not in src, "")


# ═══════════════════════════════════════════════════════════════════════════
# Static/doc shape: Dockerfile, liveness ownership list, .gitignore, docs
# ═══════════════════════════════════════════════════════════════════════════

def test_dockerfile_codex_entry_copy_and_chmod():
    print("\n[agent] AC4 Dockerfile: codex-entry COPY --chown=root:root + chmod +x")
    src = DOCKERFILE.read_text()
    check("[agent] Dockerfile COPYs codex-entry.sh --chown=root:root to /usr/local/bin/codex-entry",
          "COPY --chown=root:root codex-entry.sh /usr/local/bin/codex-entry" in src, "")
    chmod_lines = [l for l in src.splitlines() if "chmod +x" in l]
    check("[agent] codex-entry is in a chmod +x list",
          any("/usr/local/bin/codex-entry" in l for l in chmod_lines), "\n".join(chmod_lines))


def test_liveness_checks_codex_entry_ownership():
    print("\n[agent] AC4: codex-guard-liveness.sh's ownership list includes codex-entry")
    src = LIVENESS_SH.read_text()
    check("[agent] liveness gate checks bin/codex-entry ownership",
          'check_owned "$bin/codex-entry"' in src, "")


def test_gitignore_and_managed_block_have_vibe_agent():
    print("\n[agent] AC1: .vibe/agent joins the managed .gitignore block")
    gi = (REPO / ".gitignore").read_text()
    check("[agent] repo .gitignore has .vibe/agent", ".vibe/agent" in gi, "")
    extras_src = INSTALL_EXTRAS.read_text()
    check("[agent] install-claude-extras.sh managed block emits .vibe/agent",
          'echo ".vibe/agent"' in extras_src, "")


def test_readme_codex_led_sessions_section():
    print("\n[agent] AC6: README has a Codex-led sessions subsection")
    readme = README_MD.read_text()
    check("[agent] README has a 'Codex-led sessions' heading",
          "Codex-led sessions" in readme, "")
    check("[agent] README documents the --agent <claude|codex> flag",
          "`vibe --agent <claude|codex>`" in readme, "")
    check("[agent] README states Claude Code remains the default lead",
          "Claude Code remains the default lead" in readme, "")
    check("[agent] README documents explicit Codex supervision",
          "--codex-run" in readme and "--codex-resume" in readme, "")


def test_manual_tests_55_codex_led_block():
    print("\n[agent] AC6: MANUAL-TESTS Test 55 has the codex-led launch block")
    manual = MANUAL_TESTS_MD.read_text()
    m = re.search(r"### Test 55:.*?(?=\n### Test \d+:|\Z)", manual, re.DOTALL)
    check("[agent] MANUAL-TESTS.md has a Test 55 section", m is not None, "")
    body = m.group(0) if m else ""
    flat = _flat(body)
    check("[agent] Test 55 documents the Codex-led launch itself",
          "The Codex-led launch itself" in flat and "vibe --agent codex" in flat, "")
    check("[agent] Test 55 step: guard chain proven line",
          "guard chain proven, starting codex" in flat, "")
    check("[agent] Test 55 step: denied Codex login-dir config.toml write",
          "config.toml" in flat and "deny" in flat.lower(), "")
    check("[agent] Test 55 step: allowed git status, denied git push --force",
          "git status" in flat and "git push --force" in flat, "")
    check("[agent] Test 55 step: back to Claude on next plain launch",
          "Claude Code must lead again" in flat, "")
    check("[agent] Test 55 negative case: refused before any Docker build/container creation",
          "needs the Codex login mount" in flat and
          "before** any Docker build or container creation" in flat, "")


def test_codex_integration_plan_item7_delivered():
    print("\n[agent] AC6: docs/codex-integration-plan.md item 7 marked delivered-pending-live-trial")
    check("[agent] plan doc exists", CODEX_INTEGRATION_PLAN_MD.exists(), "")
    if not CODEX_INTEGRATION_PLAN_MD.exists():
        return
    plan = CODEX_INTEGRATION_PLAN_MD.read_text()
    check("[agent] item 7 row marked DELIVERED, pending live trial (task_049)",
          "DELIVERED, pending live trial (task_049)" in plan, "")
    check("[agent] item 7 row names the live trial as MANUAL-TESTS Test 55's Codex-led block",
          "MANUAL-TESTS Test 55" in plan, "")
