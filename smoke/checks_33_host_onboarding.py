"""Independent offline acceptance checks for host onboarding and switching."""
from smoke._core import *  # noqa: F401,F403

import contextlib
import importlib.util
import io
import json
import stat

HOST_ONBOARDING = REPO / "devcontainer" / "host-onboarding.py"
VIBE_AGENT_WRAPPER = REPO / "devcontainer" / "vibe-agent.sh"


def _load():
    spec = importlib.util.spec_from_file_location("host_onboarding_fixture", HOST_ONBOARDING)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _env(tmp: Path, **updates: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(HOME=str(tmp / "home"), GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
               GIT_CONFIG_NOSYSTEM="1")
    env.update(updates)
    return env


@contextlib.contextmanager
def _sandbox_env(tmp: Path):
    home = tmp / "home"
    home.mkdir(mode=0o700)
    replacements = {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"),
                    "GIT_CONFIG_NOSYSTEM": "1"}
    previous = {key: os.environ.get(key) for key in replacements}
    os.environ.update(replacements)
    try:
        yield home
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def _unit_fixture(tmp: Path):
    """Override host/TTY guards only for isolated direct-unit calls."""
    module = _load()
    with _sandbox_env(tmp) as home:
        old_host, old_tty = module.host, module.os.isatty
        module.host = lambda: None
        module.os.isatty = lambda _fd: True
        try:
            yield module, home
        finally:
            module.host, module.os.isatty = old_host, old_tty


def _repo(tmp: Path, name: str = "project with spaces") -> Path:
    ws = tmp / name
    ws.mkdir()
    result = run(["git", "init", str(ws)], env=_env(tmp))
    assert result.returncode == 0, result.stderr
    return ws


def _main(module, *argv: str) -> str:
    old, out = sys.argv, io.StringIO()
    sys.argv = ["host-onboarding.py", *argv]
    try:
        with contextlib.redirect_stdout(out):
            module.main()
    finally:
        sys.argv = old
    return out.getvalue()


def _setup(module, ws: Path, source: Path, domains: str = "custom.test\n"):
    _main(module, "setup", str(ws), domains, str(source))


def _refuses(call) -> bool:
    try:
        call()
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError):
        return True
    return False


def _launcher_call(tmp: Path, body: str, path: str | None = None):
    (tmp / "home").mkdir(mode=0o700, exist_ok=True)
    env = _env(tmp, VIBE_CONFIG=str(tmp / "config"), VIBE_SOURCE_ONLY="1",
               VIBE_CODEX_PATH=str(tmp / "codex"))
    if path is not None:
        env["PATH"] = path
    return run(["/bin/bash", "-c", f"set -e; source {shlex.quote(str(VIBE))}; {body}"],
               env=env)


def test_host_cli_refuses_explicit_container_marker_portably():
    print("\n[host-onboarding] real CLI host refusal")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        result = run([sys.executable, str(HOST_ONBOARDING), "host-check"],
                     env=_env(tmp, VIBE_CONTAINER="1"))
        check("[host-onboarding] explicit container marker denies host CLI",
              result.returncode != 0 and "outside a container" in result.stderr,
              result.stdout + result.stderr)
        check("[host-onboarding] refusal creates no HOME state",
              not (tmp / "home").exists(), str(tmp))


def test_memory_binding_spaces_private_and_unsafe_file_refusals():
    print("\n[host-onboarding] runtime memory safety")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            ws = _repo(tmp)
            _main(module, "memory-set", str(ws), "codex")
            out = _main(module, "memory-get", str(ws))
            runtime = next((home / ".vibe").glob("runtime-*.json"))
            check("[host-onboarding] memory binds canonical spaced path",
                  out.strip() == "codex" and json.loads(runtime.read_text()) ==
                  {"workspace": str(ws.resolve()), "agent": "codex"}, out)
            check("[host-onboarding] runtime record is private",
                  stat.S_IMODE(runtime.stat().st_mode) == 0o600, oct(runtime.stat().st_mode))
            runtime.chmod(0o644)
            check("[host-onboarding] non-private memory refuses",
                  _refuses(lambda: _main(module, "memory-get", str(ws))))
            runtime.chmod(0o600)
            hard = tmp / "hard"; os.link(runtime, hard)
            check("[host-onboarding] hard-linked memory refuses",
                  _refuses(lambda: _main(module, "memory-get", str(ws))))
            hard.unlink(); runtime.unlink()
            target = tmp / "target"; target.write_text('{}\n'); runtime.symlink_to(target)
            check("[host-onboarding] symlinked memory refuses",
                  _refuses(lambda: _main(module, "memory-get", str(ws))))


def test_setup_preserves_domains_creates_consent_and_is_idempotent():
    print("\n[host-onboarding] setup and consent")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            ws, source = _repo(tmp), tmp / "codex-home"
            source.mkdir(mode=0o700)
            auth = source / "auth.json"; auth.write_text("opaque\n"); auth.chmod(0o600)
            (ws / ".vibe").mkdir(); (ws / ".vibe" / "domains").write_text("custom.test # keep\n")
            _setup(module, ws, source)
            domains = (ws / ".vibe" / "domains").read_text()
            registry = (home / ".vibe" / "codex-allow").read_text()
            expected = "custom.test # keep\nchatgpt.com\nauth.openai.com\napi.openai.com\n"
            check("[host-onboarding] domains preserved and completed", domains == expected, domains)
            check("[host-onboarding] marker plus per-project host consent created",
                  (ws / ".vibe-allow-codex").exists() and registry == str(ws.resolve()) + "\n",
                  registry)
            _setup(module, ws, source)
            check("[host-onboarding] setup idempotent",
                  (ws / ".vibe" / "domains").read_text() == domains and
                  (home / ".vibe" / "codex-allow").read_text() == registry)


def test_read_only_overlap_and_unsafe_setup_controls_refuse_before_writes():
    print("\n[host-onboarding] pre-mutation refusals")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            ws, source = _repo(tmp), tmp / "source"; source.mkdir(mode=0o700)
            _main(module, "check", str(ws), "custom.test", str(source))
            check("[host-onboarding] check is read-only",
                  not (home / ".vibe").exists() and not (ws / ".vibe").exists())
            before = sorted(str(p.relative_to(tmp)) for p in tmp.rglob("*"))
            old = os.environ.get("VIBE_PROJECTS_DIR"); os.environ["VIBE_PROJECTS_DIR"] = str(home)
            try:
                refused = _refuses(lambda: _setup(module, ws, source))
            finally:
                os.environ.pop("VIBE_PROJECTS_DIR", None) if old is None else os.environ.__setitem__("VIBE_PROJECTS_DIR", old)
            after = sorted(str(p.relative_to(tmp)) for p in tmp.rglob("*"))
            check("[host-onboarding] overlap refuses before all writes", refused and before == after,
                  f"before={before}\nafter={after}")
            tracked = _repo(tmp, "tracked")
            (tracked / ".vibe-allow-codex").write_text("")
            run(["git", "-C", str(tracked), "add", ".vibe-allow-codex"], env=_env(tmp))
            check("[host-onboarding] tracked marker refuses without host state",
                  _refuses(lambda: _setup(module, tracked, source)) and not (home / ".vibe").exists())
            linked = _repo(tmp, "linked"); (linked / ".vibe").mkdir()
            target = tmp / "domains"; target.write_text("chatgpt.com\n")
            (linked / ".vibe" / "domains").symlink_to(target)
            check("[host-onboarding] symlinked domains refuse",
                  _refuses(lambda: _setup(module, linked, source)))


def test_initial_git_add_after_setup_stages_only_user_files():
    print("\n[host-onboarding] initial staging")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, _home):
            ws, source = _repo(tmp), tmp / "source"; source.mkdir(mode=0o700)
            _setup(module, ws, source)
            (ws / "README").write_text("user file\n")
            added = run(["git", "-C", str(ws), "add", "-A"], env=_env(tmp))
            staged = run(["git", "-C", str(ws), "diff", "--cached", "--name-only"],
                         env=_env(tmp)).stdout.splitlines()
            check("[host-onboarding] first add after setup stages exactly user file",
                  added.returncode == 0 and staged == ["README"], repr(staged))


def test_container_request_is_private_local_exact_and_has_no_host_authority():
    print("\n[host-onboarding] container request boundary")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Keep the source host guard intact: agent_request itself is the
        # deliberately container-callable API and must not need a bypass.
        with _sandbox_env(tmp) as home:
            module = _load()
            ws = _repo(tmp); module.agent_request(str(ws), "codex")
            request = ws / ".vibe" / "next-agent"
            tracked = run(["git", "-C", str(ws), "ls-files", "--", ".vibe/next-agent"], env=_env(tmp))
            ignored = run(["git", "-C", str(ws), "check-ignore", "--", ".vibe/next-agent"], env=_env(tmp))
            check("[host-onboarding] request exact private untracked and ignored",
                  json.loads(request.read_text()) == {"agent": "codex"} and
                  stat.S_IMODE(request.stat().st_mode) == 0o600 and
                  tracked.stdout == "" and ignored.returncode == 0, request.read_text())
            check("[host-onboarding] request cannot create host registry or memory",
                  not (home / ".vibe").exists())
            bad = _repo(tmp, "invalid")
            check("[host-onboarding] exact agent names only",
                  all(_refuses(lambda value=value: module.agent_request(str(bad), value))
                      for value in ("", "Codex", "codex ", "other")) and
                  not (bad / ".vibe").exists())


def test_take_agent_host_only_consumes_and_persists_canonical_memory():
    print("\n[host-onboarding] host take-agent")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            ws = _repo(tmp); module.agent_request(str(ws), "codex")
            request = ws / ".vibe" / "next-agent"
            denied_home = tmp / "denied"; denied_home.mkdir(mode=0o700)
            env = _env(tmp, VIBE_CONTAINER="1"); env["HOME"] = str(denied_home)
            denied = run([sys.executable, str(HOST_ONBOARDING), "take-agent", str(ws)], env=env)
            check("[host-onboarding] real take-agent is host-only",
                  denied.returncode != 0 and "outside a container" in denied.stderr and
                  request.exists() and not (denied_home / ".vibe").exists(), denied.stderr)
            out = _main(module, "take-agent", str(ws))
            runtime = next((home / ".vibe").glob("runtime-*.json"))
            check("[host-onboarding] host take consumes and persists canonical memory",
                  out.strip() == "codex" and not request.exists() and
                  json.loads(runtime.read_text()) == {"workspace": str(ws.resolve()), "agent": "codex"} and
                  stat.S_IMODE(runtime.stat().st_mode) == 0o600, out)


def test_fresh_folder_no_request_needs_no_git_and_autonomy_refuses():
    print("\n[host-onboarding] empty and autonomous request states")
    cases = {"auto-resume": ("auto-resume", "active=1\n"),
             "lock": ("codex-supervisor.json.lock", "x\n"),
             "unresolved": ("codex-supervisor.json", '{"unresolvedTurn":{"id":"x"}}\n')}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            fresh = tmp / "fresh"; fresh.mkdir()
            out = _main(module, "take-agent", str(fresh))
            check("[host-onboarding] no request returns without Git", out == "" and
                  not (fresh / ".vibe").exists() and not (home / ".vibe").exists())
            results = []
            for i, (label, (name, content)) in enumerate(cases.items()):
                ws = _repo(tmp, f"blocked-{i}"); (ws / ".vss").mkdir()
                (ws / ".vss" / name).write_text(content)
                results.append((label, _refuses(lambda ws=ws: module.agent_request(str(ws), "codex")) and
                                not (ws / ".vibe" / "next-agent").exists()))
            check("[host-onboarding] active auto-resume lock unresolved turn refuse",
                  all(ok for _, ok in results), repr(results))
            check("[host-onboarding] autonomy refusal creates no host state", not (home / ".vibe").exists())


def test_tracked_linked_and_malformed_requests_refuse():
    print("\n[host-onboarding] unsafe requests")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, home):
            results = []
            tracked = _repo(tmp, "tracked-request"); module.agent_request(str(tracked), "codex")
            run(["git", "-C", str(tracked), "add", "-f", ".vibe/next-agent"], env=_env(tmp))
            results.append(("tracked", _refuses(lambda: _main(module, "take-agent", str(tracked)))))
            linked = _repo(tmp, "linked-request"); module.agent_request(str(linked), "claude")
            os.link(linked / ".vibe" / "next-agent", tmp / "hard")
            results.append(("linked", _refuses(lambda: _main(module, "take-agent", str(linked)))))
            symlinked = _repo(tmp, "symlink-request"); (symlinked / ".vibe").mkdir()
            target = tmp / "request-target"; target.write_text('{"agent":"codex"}\n')
            (symlinked / ".vibe" / "next-agent").symlink_to(target)
            results.append(("symlink", _refuses(lambda: _main(module, "take-agent", str(symlinked)))))
            malformed = _repo(tmp, "malformed"); (malformed / ".vibe").mkdir()
            bad = malformed / ".vibe" / "next-agent"; bad.write_text('{"agent":"codex","x":1}\n'); bad.chmod(0o600)
            results.append(("malformed", _refuses(lambda: _main(module, "take-agent", str(malformed)))))
            check("[host-onboarding] tracked linked symlinked malformed requests refuse",
                  all(ok for _, ok in results), repr(results))
            check("[host-onboarding] unsafe requests create no host memory", not (home / ".vibe").exists())


def test_wrapper_targets_launched_workspace_from_nested_cwd():
    print("\n[host-onboarding] wrapper launch-workspace resolution")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); ws = _repo(tmp); nested = ws / "a" / "b"; nested.mkdir(parents=True)
        capture, helper = tmp / "capture", tmp / "helper"
        helper.write_text('#!/bin/sh\nset -eu\nprintf \'%s\\n\' "$@" > "$CAPTURE"\n'); helper.chmod(0o700)
        original = VIBE_AGENT_WRAPPER.read_text()
        pinned = "exec /usr/bin/python3 -I /usr/local/share/vibe/host-onboarding.py"
        wrapper = tmp / "vibe-agent"
        wrapper.write_text(original.replace(pinned, 'exec "$VIBE_AGENT_TEST_HELPER"')); wrapper.chmod(0o700)
        env = _env(tmp, CAPTURE=str(capture), VIBE_AGENT_TEST_HELPER=str(helper))
        result = run([str(wrapper), "codex"], env=env, cwd=nested)
        args = capture.read_text().splitlines() if capture.exists() else []
        invalid = run([str(wrapper), "Codex"], env=env, cwd=nested)
        check("[host-onboarding] wrapper has one pinned helper call", original.count(pinned) == 1)
        config = json.loads((REPO / "devcontainer/devcontainer.json").read_text())
        check("[host-onboarding] nested cwd targets the actual launcher mount, not monorepo root",
              result.returncode == 0 and args == ["request-agent", config["workspaceFolder"], "codex"] and
              "target=" + config["workspaceFolder"] in config["workspaceMount"], repr(args))
        check("[host-onboarding] wrapper exact agents only before helper",
              invalid.returncode != 0 and capture.read_text().splitlines() == args, invalid.stderr)


def test_plain_launcher_consent_and_remembered_precedence():
    print("\n[host-onboarding] plain launch consent and precedence")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); ws = _repo(tmp); (ws / ".vibe").mkdir(); (ws / ".vibe" / "agent").write_text("claude\n")
        stub = """
_vibe_interactive() { test "$INTERACTIVE" = 1; }
_vibe_host_onboarding() { printf 'host:%s\\n' "$1" >> "$CALLS"; return 0; }
resolve_extra_domains() { EXTRA_DOMAINS_RESOLVED='chatgpt.com auth.openai.com api.openai.com'; }
ask_yes_no() { echo ask >> "$CALLS"; return "$ASK"; }
vibe_codex_login_status() { echo status >> "$CALLS"; return 0; }
_codex_desired_source() { [ "$READY" = 1 ] && echo "$VIBE_CODEX_PATH"; }
codex() { echo login >> "$CALLS"; }
"""
        consent = f'CALLS={shlex.quote(str(tmp / "calls"))}; : > "$CALLS"; INTERACTIVE=1; ASK=0; READY=0; {stub} vibe_onboard_codex {shlex.quote(str(ws))}; grep -qx host:setup "$CALLS"; ! grep -qx login "$CALLS"'
        healthy = f'CALLS={shlex.quote(str(tmp / "healthy"))}; : > "$CALLS"; INTERACTIVE=1; ASK=0; READY=1; {stub} vibe_onboard_codex {shlex.quote(str(ws))}; grep -qx host:check "$CALLS"; ! grep -Eq "ask|host:setup|login" "$CALLS"'
        denied = f'CALLS={shlex.quote(str(tmp / "denied"))}; : > "$CALLS"; INTERACTIVE=0; ASK=0; READY=0; {stub} vibe_onboard_codex {shlex.quote(str(ws))}; test ! -s "$CALLS"'
        results = [_launcher_call(tmp, consent), _launcher_call(tmp, healthy), _launcher_call(tmp, denied)]
        check("[host-onboarding] shared login still needs per-project consent via plain setup",
              results[0].returncode == 0, results[0].stdout + results[0].stderr)
        check("[host-onboarding] healthy consent reuses login and noninteractive cannot grant",
              results[1].returncode == 0 and results[2].returncode == 0,
              "\n".join(r.stderr for r in results[1:]))
        memory = tmp / "memory"
        body = f'''MEMORY={shlex.quote(str(memory))}
_vibe_host_onboarding() {{ case "$1" in take-agent) return 0;; memory-get) [ ! -f "$MEMORY" ] || cat "$MEMORY";; memory-set) printf '%s\\n' "$3" > "$MEMORY";; esac; }}
_vibe_interactive() {{ return 1; }}; VIBE_AGENT=claude
vibe_onboard_agent codex {shlex.quote(str(ws))}; test "$LEAD_AGENT" = codex; grep -qx codex "$MEMORY"
LEAD_AGENT=; vibe_onboard_agent '' {shlex.quote(str(ws))}; test "$LEAD_AGENT" = codex
vibe_onboard_agent claude {shlex.quote(str(ws))}; test "$LEAD_AGENT" = claude; grep -qx claude "$MEMORY"
printf codex > "$MEMORY"; LEAD_AGENT=; vibe_onboard_agent '' {shlex.quote(str(ws))}; test "$LEAD_AGENT" = codex'''
        precedence = _launcher_call(tmp, body)
        check("[host-onboarding] flag then remembered choice override local env and default",
              precedence.returncode == 0, precedence.stdout + precedence.stderr)


def test_switch_after_exit_clean_unsupervised_cleanup_then_plain_reexec():
    print("\n[host-onboarding] clean-exit switch")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); ws = _repo(tmp); calls = tmp / "switch-calls"; bindir = tmp / "bin"; bindir.mkdir()
        bash_stub = bindir / "bash"
        bash_stub.write_text('#!/bin/sh\nprintf reexec >> "$CALLS"\nfor a in "$@"; do printf "|%s" "$a" >> "$CALLS"; done\nprintf "\\n" >> "$CALLS"\n')
        bash_stub.chmod(0o700)
        common = f'''CALLS={shlex.quote(str(calls))}; export CALLS; WS={shlex.quote(str(ws))}; VR={shlex.quote(str(REPO))}; : > "$CALLS"
_vibe_host_onboarding() {{ echo take >> "$CALLS"; echo codex; }}; vibe_on_exit() {{ echo cleanup >> "$CALLS"; }}
WORKSPACE="$WS"; VIBE_REPO_DIR="$VR"; PROFILE=python'''
        gated = common + '''
_vibe_interactive() { return 1; }; CLAUDE_EXIT=0; CODEX_ACTION=; vibe_switch_after_exit
_vibe_interactive() { return 0; }; CLAUDE_EXIT=2; vibe_switch_after_exit
CLAUDE_EXIT=0; CODEX_ACTION=run; vibe_switch_after_exit; test ! -s "$CALLS"'''
        clean = common + '''
_vibe_interactive() { return 0; }; CLAUDE_EXIT=0; CODEX_ACTION=
CONTINUE=true; RESUME=true; MODEL_ARG=forbidden; vibe_switch_after_exit'''
        path = str(bindir) + os.pathsep + os.environ.get("PATH", "")
        denied, applied = _launcher_call(tmp, gated, path), _launcher_call(tmp, clean, path)
        lines = calls.read_text().splitlines() if calls.exists() else []
        expected = ["take", "cleanup", f"reexec|{REPO / 'vibe'}|{ws}|--agent|codex"]
        check("[host-onboarding] noninteractive abnormal supervised exits do not take", denied.returncode == 0,
              denied.stdout + denied.stderr)
        check("[host-onboarding] clean exit cleans before exact reexec without bypass flags",
              applied.returncode == 0 and lines == expected and
              not any(x in lines[-1] for x in ("--continue", "--resume", "--model", "--codex-run")),
              applied.stdout + applied.stderr + repr(lines))


def test_source_check_rejects_unsafe_auth_metadata():
    print("\n[host-onboarding] source metadata")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _unit_fixture(tmp) as (module, _home):
            source = tmp / "source"; source.mkdir(mode=0o700)
            auth = source / "auth.json"; auth.write_text("opaque\n"); auth.chmod(0o600)
            module.source_check(str(source)); auth.chmod(0o644)
            check("[host-onboarding] group-readable auth metadata refuses",
                  _refuses(lambda: module.source_check(str(source))))


# Targeted manually by the harness; runner wiring belongs to the integrator.


def test_missing_host_cli_installs_only_after_consent_and_reuses_login():
    print("\n[host-onboarding] first host CLI installation")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); ws = _repo(tmp)
        common = f'''CALLS={shlex.quote(str(tmp / 'install-calls'))}; INSTALLED_FILE={shlex.quote(str(tmp / 'installed'))}; : > "$CALLS"
_vibe_interactive() {{ return 0; }}
_vibe_host_onboarding() {{ echo "host:$1" >> "$CALLS"; }}
resolve_extra_domains() {{ EXTRA_DOMAINS_RESOLVED='chatgpt.com auth.openai.com api.openai.com'; }}
_codex_desired_source() {{ return 0; }}
command() {{ if [ "$*" = '-v codex' ]; then test -f "$INSTALLED_FILE"; elif [ "$*" = '-v npm' ]; then return 0; else builtin command "$@"; fi; }}
ask_yes_no() {{ echo consent >> "$CALLS"; return "$DECLINE"; }}
npm() {{ echo install >> "$CALLS"; [ "$INSTALL_FAIL" = 0 ] || return 1; : > "$INSTALLED_FILE"; }}
vibe_codex_login_status() {{ echo status >> "$CALLS"; return 0; }}
codex() {{ echo login >> "$CALLS"; }}
'''
        for label, decline, fail in (("declined", 1, 0), ("failed", 0, 1), ("accepted", 0, 0)):
            body = common + f'DECLINE={decline}; INSTALL_FAIL={fail}; vibe_onboard_codex {shlex.quote(str(ws))}'
            result = _launcher_call(tmp, body)
            events = (tmp / 'install-calls').read_text().splitlines()
            if label == "declined":
                ok = result.returncode != 0 and "install" not in events and "host:setup" not in events
            elif label == "failed":
                ok = result.returncode != 0 and "install" in events and "host:setup" not in events
            else:
                ok = (result.returncode == 0 and events.index("consent") < events.index("install") < events.index("host:setup")
                      and "login" not in events)
            check(f"[host-onboarding] missing CLI {label}: consent, failure and existing-login boundaries", ok, result.stderr + repr(events))


def test_concurrent_setup_retains_both_project_grants():
    print("\n[host-onboarding] concurrent initial host state")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); (tmp / "home").mkdir(mode=0o700)
        first, second = _repo(tmp, "first"), _repo(tmp, "second")
        source = tmp / "source"; source.mkdir(mode=0o700)
        script = '''import importlib.util, os, sys
spec=importlib.util.spec_from_file_location("fixture", sys.argv[1])
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.host=lambda:None; m.os.isatty=lambda fd:True
sys.argv=["fixture","setup",sys.argv[2],"custom.test",sys.argv[3]]
m.main()
'''
        children = [subprocess.Popen([sys.executable, "-c", script, str(HOST_ONBOARDING), str(ws), str(source)],
                                    env=_env(tmp), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True) for ws in (first, second)]
        try:
            reports = [child.communicate(timeout=15) for child in children]
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill(); child.communicate(timeout=5)
        registry = tmp / "home/.vibe/codex-allow"
        entries = registry.read_text().splitlines() if registry.exists() else []
        check("[host-onboarding] concurrent setup loses neither project grant",
              all(child.returncode == 0 for child in children) and set(entries) == {str(first), str(second)},
              repr(reports) + repr(entries))


def test_docker_preflight_is_shared_and_mac_start_preserves_target():
    print("\n[host-onboarding] shared host Docker readiness")
    from unittest.mock import patch
    module = _load()
    calls = []
    selected_context = 'orbstack'
    selected_endpoint = 'unix:///var/run/docker.sock'
    def vendor(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ['context', 'show']:
            return subprocess.CompletedProcess(argv, 0, selected_context + '\n')
        if argv[1:3] == ['context', 'inspect']:
            return subprocess.CompletedProcess(argv, 0, selected_endpoint + '\n')
        return subprocess.CompletedProcess(argv, 0)
    with patch.object(module.subprocess, 'run', side_effect=vendor):
        check("[host-onboarding] Docker readiness is a bounded read-only probe", module.docker_ready() and calls == [['docker', 'info', '--format', '{{.ServerVersion}}']])
        calls.clear()
        with patch.object(module.sys, 'platform', 'darwin'), patch.object(module.os, 'isatty', return_value=True), patch.object(module.os.path, 'isdir', return_value=True), patch.dict(os.environ, {'DOCKER_HOST': ''}):
            check("[host-onboarding] selected installed Mac backend starts without context change", module.start_mac_docker() and calls == [['docker', 'context', 'show'], ['docker', 'context', 'inspect', 'orbstack', '--format', '{{.Endpoints.docker.Host}}'], ['/usr/bin/open', '-a', '/Applications/OrbStack.app']])
            for selected_context in ('default', 'orbstack', 'desktop-linux'):
                for selected_endpoint in ('tcp://fixture.invalid:2376', 'ssh://fixture.invalid', 'unix:///tmp/custom.sock'):
                    calls.clear()
                    with patch.object(module.os.path, 'isdir', side_effect=lambda p: p == ('/Applications/Docker.app' if selected_context == 'desktop-linux' else '/Applications/OrbStack.app')):
                        check('[host-onboarding] custom endpoint refused for ' + selected_context + ' ' + selected_endpoint,
                              not module.start_mac_docker() and not any(c[0] == '/usr/bin/open' for c in calls))
            calls.clear()
            with patch.dict(os.environ, {'HOME': '/tmp/custom-home'}):
                check('[host-onboarding] overridden HOME cannot bless a custom Docker socket', not module.start_mac_docker() and calls == [])
            with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://fixture.invalid:2376'}):
                check("[host-onboarding] explicit remote Docker target never starts a local backend", not module.start_mac_docker() and calls == [])
            with patch.object(module.os, 'isatty', return_value=False):
                check("[host-onboarding] noninteractive Docker startup has no side effects", not module.start_mac_docker() and calls == [])
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        body = '''_vibe_host_onboarding() { test "$1" = docker-ready; }
_vibe_interactive() { return 1; }
LEAD_AGENT=claude; vibe_docker_preflight
LEAD_AGENT=codex; vibe_docker_preflight'''
        result = _launcher_call(tmp, body)
        check("[host-onboarding] both runtimes share the same ready-engine path", result.returncode == 0, result.stderr)
