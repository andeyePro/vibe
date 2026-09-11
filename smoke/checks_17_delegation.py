"""Phase 1a: real helper processes against fake vendor CLIs, no network/auth.

Positive controls capture exact argv/stdin, JSON and usage. Negative controls
must make zero paid calls or reject malformed output, never pass vacuously.
"""
from smoke._core import *
from smoke._core import _isolate_extras_env, _source_vibe_call

DELEGATE = REPO / "devcontainer/vibe-delegate.mjs"


def _delegate_fixture(root):
    home = root / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    bins = root / "bin"
    bins.mkdir()
    workspace = root / "repo"
    workspace.mkdir()
    (workspace / ".vibe").mkdir()
    env = _isolate_extras_env({**os.environ, "HOME": str(home),
        "PATH": str(bins) + os.pathsep + os.environ["PATH"]})
    # Real git sees only this throwaway repo; vendor stubs see no host credentials.
    run(["git", "init", "-q", str(workspace)], env=env)
    stub = r'''
import json, os, sys
from pathlib import Path
home = Path(os.environ["HOME"])
fixture = json.loads((home / "fixture.json").read_text())
args = sys.argv[1:]
vendor = Path(sys.argv[0]).name
data = sys.stdin.read()
with (home / "calls.jsonl").open("a") as f:
    f.write(json.dumps({"vendor": vendor, "args": args, "input": data,
        "cwd": os.getcwd(), "env": dict(os.environ)}) + "\n")
# A --settings value that is a FILE is private to the helper's scratch dir and
# gone after the call: snapshot it while it exists so tests can inspect it.
if "--settings" in args:
    _sp = args[args.index("--settings") + 1]
    if os.path.isfile(_sp):
        (home / "settings-seen.json").write_text(Path(_sp).read_text())
if vendor == "codex" and args == ["--version"]:
    print(fixture.get("version", "codex-cli 0.154.0"))
    sys.exit(0)
if vendor == "codex" and "status" in args:
    print(fixture.get("login", "Logged in using ChatGPT"), file=sys.stderr)
    sys.exit(fixture.get("login_exit", 0))
if fixture.get("exit"):
    print("PRIVATE_PROVIDER_ERROR", file=sys.stderr)
    sys.exit(fixture["exit"])
if vendor == "codex":
    schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
    (home / "schema.json").write_text(json.dumps(schema))
    answer = fixture.get("answer", {"answer": "A useful answer"})
    Path(args[args.index("--output-last-message") + 1]).write_text(
        answer if isinstance(answer, str) else json.dumps(answer))
    for event in fixture.get("events", [
        {"type": "turn.completed", "usage": {
            "input_tokens": 5000, "cached_input_tokens": 1000, "output_tokens": 44}}]):
        print(event if isinstance(event, str) else json.dumps(event))
else:
    response = fixture.get("response", {"type": "result", "subtype": "success",
        "is_error": False, "result": "Claude answer", "modelUsage": {"served-fixture": {}},
        "usage": {"input_tokens": 100, "cache_creation_input_tokens": 20000,
            "cache_read_input_tokens": 7000, "output_tokens": 30,
            "cache_creation": {"ephemeral_5m_input_tokens": 40}}})
    print(response if isinstance(response, str) else json.dumps(response))
'''
    for name in ("codex", "claude"):
        path = bins / name
        path.write_text(f"#!{sys.executable}\n" + stub)
        path.chmod(0o755)
    (home / "fixture.json").write_text("{}")
    return workspace, home, env


def _delegate_call(workspace, home, env, args, fixture=None, payload="Task\nlarge payload\n", cwd=None):
    (home / "fixture.json").write_text(json.dumps(fixture or {}))
    (home / "calls.jsonl").write_text("")
    result = run(["node", str(DELEGATE), *args], cwd=cwd or workspace, env=env, input=payload)
    calls = [json.loads(line) for line in (home / "calls.jsonl").read_text().splitlines()]
    return result, calls


def test_delegate_astra_contract():
    print("\n[delegate] Astra CLI boundary, schema and token accounting")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        env.update({k: "DO_NOT_FORWARD" for k in (
            "OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
            "GEMINI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE")})
        payload = 'Explain these bulk logs: $(touch INJECTION); `echo unsafe`\n"quoted"\n'
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"], payload=payload)
        check("[delegate] Astra succeeds", r.returncode == 0, r.stderr)
        if r.returncode:
            return
        result = json.loads(r.stdout)
        check("[delegate] exact answer and actual tokens (cache not double counted)",
              result["answer"] == "A useful answer" and result["usage"]["total_tokens"] == 5044, r.stdout)
        check("[delegate] version floor, one login probe, exactly one exec",
              len(calls) == 3 and calls[0]["args"] == ["--version"], str(calls))
        call = calls[-1]
        argv = call["args"]
        check("[delegate] exact requested model, structured response and JSON events",
              argv[:3] == ["exec", "-m", "gpt-6-astra"] and
              all(flag in argv for flag in ("--output-schema", "--json", "--ephemeral")), str(argv))
        check("[delegate] schema closed and answer required",
              json.loads((home / "schema.json").read_text()) == {
                  "type": "object", "properties": {"answer": {"type": "string"}},
                  "required": ["answer"], "additionalProperties": False}, "")
        check("[delegate] tools restricted; no bypass or session resume",
              all(x in argv for x in ("--ignore-user-config", "read-only", 'approval_policy="never"',
                  'forced_login_method="chatgpt"', 'agents.enabled=false', 'web_search="disabled"',
                  "shell_tool", "unified_exec", "apps", "multi_agent")) and
              not any("bypass" in x or x == "resume" for x in argv), str(argv))
        check("[delegate] payload literal on stdin, absent from argv",
              call["input"].endswith(payload) and payload not in argv and
              not (workspace / "INJECTION").exists(), "")
        check("[delegate] private cwd outside repo and cleaned up",
              call["cwd"] != str(workspace) and not Path(call["cwd"]).exists(), call["cwd"])
        check("[delegate] credentials/env never forwarded across vendors",
              "DO_NOT_FORWARD" not in json.dumps(calls) and
              call["env"]["CODEX_HOME"] == str(home / ".codex"), "")


def test_delegate_failures():
    print("\n[delegate] refusals, bad JSON, usage and billing errors fail closed")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        cases = [
            ("API login", {"login": "Logged in using an API key: PRIVATE_KEY"}),
            ("no login", {"login_exit": 1}),
            ("old CLI", {"version": "codex-cli 0.153.4"}),
            ("unparseable version", {"version": "codex-cli"}),
            ("CLI failure", {"exit": 1}),
            ("prose answer", {"answer": "Sorry, unable to review"}),
            ("wrong answer shape", {"answer": {"findings": []}}),
            ("missing usage", {"events": [{"type": "turn.completed"}]}),
            ("no completion", {"events": [{"type": "turn.started"}]}),
            ("bad event", {"events": ["not JSON"]}),
            ("failed event", {"events": [{"type": "turn.failed"}]}),
            ("invalid counts", {"events": [{"type": "turn.completed", "usage": {
                "input_tokens": 2, "output_tokens": -1, "cached_input_tokens": 0}}]}),
        ]
        for label, fixture in cases:
            r, calls = _delegate_call(workspace, home, env, ["ask", "astra"], fixture)
            check(f"[delegate] {label} rejected", r.returncode != 0 and not r.stdout, r.stdout)
            check(f"[delegate] {label} diagnostics do not leak vendor output",
                  "PRIVATE_" not in r.stderr, r.stderr)
            if label in ("API login", "no login"):
                check(f"[delegate] {label} invokes no model", len(calls) == 2, str(calls))
            if label in ("old CLI", "unparseable version"):
                check(f"[delegate] {label} stops before the login probe", len(calls) == 1, str(calls))
        # No login dir at all (project not opted in): name the opt-in, make no call.
        import shutil
        shutil.rmtree(home / ".codex", ignore_errors=True)
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] unmounted login dir names the per-project opt-in and makes no call",
              r.returncode != 0 and not calls and ".vibe-allow-codex" in r.stderr, r.stderr)
        (home / ".codex").mkdir()
        for args, payload in [(["ask", "unknown"], "task"), (["ask", "astra"], ""),
                              (["ask", "astra", "--bypass"], "task")]:
            r, calls = _delegate_call(workspace, home, env, args, payload=payload)
            check("[delegate] invalid invocation makes no call", r.returncode != 0 and not calls, r.stderr)


def test_delegate_claude_routes():
    print("\n[delegate] Claude rungs, per-task consent, configurable billing")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        env["VIBE_FABLE_CREDITS_OK"] = "1"
        env["CLAUDECODE"] = "nested-session"
        for model in ("opus", "sonnet", "haiku"):
            r, calls = _delegate_call(workspace, home, env, ["ask", model])
            check(f"[delegate] {model} one-shot succeeds", r.returncode == 0 and len(calls) == 1, r.stderr)
            if r.returncode:
                continue
            result = json.loads(r.stdout)
            args = calls[0]["args"]
            check(f"[delegate] {model} fixed CLI contract",
                  args[:5] == ["-p", "--model", model, "--output-format", "json"] and
                  args[args.index("--tools") + 1] == "" and "--safe-mode" in args and
                  "--strict-mcp-config" in args and "--no-session-persistence" in args and
                  "CLAUDECODE" not in calls[0]["env"], str(args))
            check(f"[delegate] {model} includes all cache components and served model",
                  result["usage"]["total_tokens"] == 27130 and
                  result["usage"]["ephemeral_5m_input_tokens"] == 40 and
                  result["served_models"] == ["served-fixture"], r.stdout)
        r, calls = _delegate_call(workspace, home, env, ["ask", "fable"])
        check("[delegate] standing launch consent cannot authorise Fable", r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(workspace, home, env, ["ask", "fable", "--consent-credits"])
        check("[delegate] explicit task consent permits Fable", r.returncode == 0 and len(calls) == 1, r.stderr)
        for billing in ("credits", "api"):
            paid_env = {**env, "VIBE_CLAUDE_P_BILLING": billing,
                        "VIBE_CLAUDE_P_SETTINGS": str(home / "route.json"),
                        "VIBE_CLAUDE_P_CONFIG_DIR": str(home / "paid-config")}
            r, calls = _delegate_call(workspace, home, paid_env, ["ask", "opus"])
            check(f"[delegate] {billing} blocked without task consent", r.returncode != 0 and not calls, r.stderr)
            r, calls = _delegate_call(workspace, home, paid_env, ["ask", "opus", "--consent-credits"])
            check(f"[delegate] {billing} configured without code or credential handling",
                  r.returncode == 0 and len(calls) == 1 and str(home / "route.json") in calls[0]["args"] and
                  calls[0]["env"]["CLAUDE_CONFIG_DIR"] == str(home / "paid-config"), r.stderr)
        for response in ("prose", {"type": "result", "is_error": True, "result": "quota exceeded"},
                         {"type": "result", "subtype": "success", "is_error": False, "result": "answer"}):
            r, _ = _delegate_call(workspace, home, env, ["ask", "haiku"], {"response": response})
            check("[delegate] Claude bad/error/missing-usage result rejected", r.returncode != 0 and not r.stdout, r.stdout)


def test_delegate_review_policy():
    print("\n[delegate] per-project policy and JSON review contract")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        policy = workspace / ".vibe/review-slots"
        for content, expected in [(None, {"gemini": True, "codex": True}),
                ("# local overrides\ncodex=off\n", {"gemini": True, "codex": False}),
                ("gemini=off\ncodex=on\n", {"gemini": False, "codex": True}),
                ("\n# defaults\n", {"gemini": True, "codex": True})]:
            if content is not None:
                policy.write_text(content)
            r, calls = _delegate_call(workspace, home, env, ["slots"])
            check("[delegate] policy defaults/override", r.returncode == 0 and json.loads(r.stdout) == expected and not calls, r.stderr)
        policy.write_text("codex=off\n")
        r, calls = _delegate_call(workspace, home, env, ["review", "codex"])
        check("[delegate] disabled explicit reviewer launches nothing", r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] explicit ask independent of review policy", r.returncode != 0 and not calls and not r.stdout and ".vibe/review-slots" in r.stderr and "codex=off" in r.stderr, r.stderr)
        # The policy is resolved from the git ROOT: invoked from a subdirectory
        # it must still be found (fail-open one directory down was the bug).
        sub = workspace / "sub"; sub.mkdir(exist_ok=True)
        r, calls = _delegate_call(workspace, home, env, ["slots"], cwd=sub)
        check("[delegate] policy honoured from a subdirectory",
              r.returncode == 0 and json.loads(r.stdout) == {"gemini": True, "codex": False} and not calls, r.stderr)
        r, calls = _delegate_call(workspace, home, env, ["review", "codex"], cwd=sub)
        check("[delegate] disabled reviewer stays disabled from a subdirectory", r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(workspace, home, env, ["slots"], cwd=home)
        check("[delegate] outside a git work tree the policy call refuses", r.returncode != 0 and not calls, r.stderr)
        for content in ("codex=off\ncodex=on\n", "claude=off\n", "codex=yes\n"):
            policy.write_text(content)
            r, calls = _delegate_call(workspace, home, env, ["slots"])
            check("[delegate] malformed/duplicate policy fails closed", r.returncode != 0 and not calls, r.stderr)
        policy.write_text("codex=on\n")
        run(["git", "-C", str(workspace), "add", ".vibe/review-slots"], env=env)
        r, calls = _delegate_call(workspace, home, env, ["slots"])
        check("[delegate] tracked policy refused", r.returncode != 0 and not calls, r.stderr)
        run(["git", "-C", str(workspace), "rm", "--cached", ".vibe/review-slots"], env=env)
        policy.unlink()
        policy.symlink_to(home / "fixture.json")
        r, calls = _delegate_call(workspace, home, env, ["slots"])
        check("[delegate] symlink policy refused", r.returncode != 0 and not calls, r.stderr)
        policy.unlink()
        good = {"verdict": "FAIL", "summary": "A correctness bug", "findings": [
            {"severity": "BLOCKING", "file": "file.py", "line": 7, "message": "Missing return"}]}
        r, calls = _delegate_call(workspace, home, env, ["review", "codex"], {"answer": good}, payload="SAVED TARGET DIFF")
        check("[delegate] review preserves structured findings and supplied target",
              r.returncode == 0 and json.loads(r.stdout)["findings"] == good["findings"] and
              calls[-1]["input"].endswith("SAVED TARGET DIFF"), r.stderr)
        for answer in ({**good, "verdict": "PASS"}, {**good, "findings": [{"message": "bad shape"}]},
                       "BLOCKING file.py:7 - prose", {**good, "verdict": "UNKNOWN"}):
            r, _ = _delegate_call(workspace, home, env, ["review", "codex"], {"answer": answer})
            check("[delegate] invalid review never becomes PASS", r.returncode != 0 and not r.stdout, r.stdout)


def test_delegate_ask_policy_and_argv():
    print("\n[delegate] ask astra policy enforcement and Claude argv golden")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        policy = workspace / ".vibe/review-slots"
        
        # AC2a: codex=off leaves ask haiku/sonnet/opus unaffected
        policy.write_text("codex=off\n")
        for model in ("haiku", "sonnet", "opus"):
            r, calls = _delegate_call(workspace, home, env, ["ask", model])
            check(f"[delegate] {model} works with codex=off", r.returncode == 0 and len(calls) == 1, r.stderr)
        
        # AC2b: gemini=off alone, empty policy, no policy file all leave ask astra working
        policy.write_text("gemini=off\n")
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra works with gemini=off alone", r.returncode == 0 and len(calls) == 3, r.stderr)
        
        policy.write_text("\n")
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra works with empty policy", r.returncode == 0 and len(calls) == 3, r.stderr)
        
        policy.unlink()
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra works with no policy file", r.returncode == 0 and len(calls) == 3, r.stderr)
        
        # AC2c: policy failures (tracked, symlink, duplicate, unknown) make ask astra fail with zero calls
        policy.write_text("codex=on\n")
        run(["git", "-C", str(workspace), "add", ".vibe/review-slots"], env=env)
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra fails with tracked policy", r.returncode != 0 and not calls, r.stderr)
        run(["git", "-C", str(workspace), "rm", "-q", "--cached", ".vibe/review-slots"], env=env)
        
        policy.unlink()
        policy.symlink_to(home / "fixture.json")
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra fails with symlinked policy", r.returncode != 0 and not calls, r.stderr)
        
        policy.unlink()
        policy.write_text("codex=on\ncodex=off\n")
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra fails with duplicate policy entries", r.returncode != 0 and not calls, r.stderr)
        
        policy.write_text("unknown=value\n")
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"])
        check("[delegate] ask astra fails with unknown policy entry", r.returncode != 0 and not calls, r.stderr)
        
        # AC3a: ask astra outside git work tree exits non-zero with zero calls
        policy.unlink()
        r, calls = _delegate_call(workspace, home, env, ["ask", "astra"], cwd=home)
        check("[delegate] ask astra fails outside git work tree", r.returncode != 0 and not calls, r.stderr)
        
        # AC3b: ask haiku outside git work tree is unchanged (exit 0)
        r, calls = _delegate_call(workspace, home, env, ["ask", "haiku"], cwd=home)
        check("[delegate] ask haiku works outside git work tree", r.returncode == 0 and len(calls) == 1, r.stderr)
        
        # AC4: Claude leg argv is pinned as golden in subscription and billed modes
        # Subscription mode: check the exact argv
        if policy.exists():
            policy.unlink()  # Ensure no policy file interference
        r, calls = _delegate_call(workspace, home, env, ["ask", "haiku"])
        check("[delegate] ask haiku makes one call", r.returncode == 0 and len(calls) == 1, r.stderr)
        if calls:
            argv = calls[0]["args"]
            golden = ['-p', '--model', 'haiku', '--output-format', 'json', '--safe-mode',
                      '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                      '--setting-sources', 'user', '--permission-mode', 'plan',
                      '--permission-prompts', 'none', '--no-session-persistence',
                      '--disable-slash-commands', '--settings', '{"forceLoginMethod":"claudeai"}']
            check("[delegate] subscription claude argv equals the golden vector exactly", argv == golden, str(argv))
            check("[delegate] golden has no dontAsk and no disableAllHooks",
                  "dontAsk" not in argv and "disableAllHooks" not in str(argv), str(argv))

        # Billed mode: check argv with settings path
        paid_env = {**env, "VIBE_CLAUDE_P_BILLING": "credits",
                    "VIBE_CLAUDE_P_SETTINGS": str(home / "route.json"),
                    "VIBE_CLAUDE_P_CONFIG_DIR": str(home / "paid-config")}
        r, calls = _delegate_call(workspace, home, paid_env, ["ask", "opus", "--consent-credits"])
        check("[delegate] billed opus makes one call", r.returncode == 0 and len(calls) == 1, r.stderr)
        if calls:
            argv = calls[0]["args"]
            golden_billed = ['-p', '--model', 'opus', '--output-format', 'json', '--safe-mode',
                             '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                             '--setting-sources', 'user', '--permission-mode', 'plan',
                             '--permission-prompts', 'none', '--no-session-persistence',
                             '--disable-slash-commands', '--settings', str(home / "route.json")]
            check("[delegate] billed claude argv equals the golden vector with the settings path", argv == golden_billed, str(argv))


def test_codex_dir_mode_warning() -> None:
    """AC5: launcher exposes _codex_dir_mode_warning function that warns when
    the Codex login directory is readable by group or others."""
    print("\n[codex] directory mode warning for readable .codex dir")
    
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"
        home.mkdir()
        
        # Create test directories with different modes
        for mode_val, should_warn in [
            (0o700, False),   # rwx------
            (0o755, True),    # rwxr-xr-x
            (0o750, True),    # rwxr-x---
            (0o705, True),    # rwx--r-x
            (0o704, True),    # rwx--r--
            (0o701, True),    # rwx-----x
            (0o702, True),    # rwx-----w
        ]:
            codex_dir = home / f"codex_{oct(mode_val)}"
            codex_dir.mkdir()
            codex_dir.chmod(mode_val)
            
            env = _t14_env(home)
            r = _source_vibe_call(env, f'_codex_dir_mode_warning "{codex_dir}"')
            
            if should_warn:
                check(f"[codex] mode {oct(mode_val)} warns",
                      r.returncode == 0 and "chmod 700" in r.stderr and str(codex_dir) in r.stderr,
                      f"rc={r.returncode} stderr={r.stderr}")
            else:
                check(f"[codex] mode {oct(mode_val)} is silent",
                      r.returncode == 0 and "chmod" not in r.stderr,
                      f"rc={r.returncode} stderr={r.stderr}")
            
            # Mode should not be changed
            import stat
            actual_mode = stat.S_IMODE(codex_dir.stat().st_mode)
            check(f"[codex] mode {oct(mode_val)} unchanged after warning",
                  actual_mode == mode_val,
                  f"was {oct(mode_val)}, now {oct(actual_mode)}")
        
        # Four-digit modes: judge on last three digits
        four_digit_dir = home / "codex_four_digit"
        four_digit_dir.mkdir()
        four_digit_dir.chmod(0o1755)  # stickybit + rwxr-xr-x
        
        env = _t14_env(home)
        r = _source_vibe_call(env, f'_codex_dir_mode_warning "{four_digit_dir}"')
        check("[codex] four-digit mode 1755 warns (last three digits have group/others perms)",
              r.returncode == 0 and "chmod 700" in r.stderr,
              f"stderr={r.stderr}")
        
        four_digit_silent = home / "codex_four_digit_silent"
        four_digit_silent.mkdir()
        four_digit_silent.chmod(0o4700)  # setuid + rwx------
        
        r = _source_vibe_call(env, f'_codex_dir_mode_warning "{four_digit_silent}"')
        check("[codex] four-digit mode 4700 is silent (last three digits are 700)",
              r.returncode == 0 and "chmod" not in r.stderr,
              f"stderr={r.stderr}")
        
        # Non-existent path is silent
        nonexistent = home / "nonexistent"
        # Astra review (iter 2): a symlink to a mode-700 directory must be judged
        # by the target's mode, not the link's own 777.
        link_target = Path(td) / "real-codex"; link_target.mkdir(); link_target.chmod(0o700)
        link = Path(td) / "link-codex"; link.symlink_to(link_target)
        r = _source_vibe_call(env, f'_codex_dir_mode_warning "{link}"')
        check("[codex] symlink to a 0700 dir is silent (stat -L)", r.returncode == 0 and "chmod 700" not in r.stderr, r.stderr)
        link_target.chmod(0o755)
        r = _source_vibe_call(env, f'_codex_dir_mode_warning "{link}"')
        check("[codex] symlink to a 0755 dir warns (stat -L)", "chmod 700" in r.stderr, r.stderr)
        link_target.chmod(0o700)
        r = _source_vibe_call(env, f'_codex_dir_mode_warning "{nonexistent}"')
        check("[codex] non-existent path is silent",
              r.returncode == 0 and not r.stderr,
              f"stderr={r.stderr}")
    
    # SOURCE-TEXT adjacency: check that the banner call is wired correctly
    vibe_text = VIBE.read_text()
    lines = vibe_text.splitlines()
    
    # Find the line echoing the codex header
    codex_header_line = None
    for i, line in enumerate(lines):
        if 'echo' in line and 'codex   : /home/node/.codex (rw, ChatGPT login)' in line:
            codex_header_line = i
            break
    
    check("[codex] launcher has codex header line", codex_header_line is not None, "")
    
    if codex_header_line is not None:
        # Find the _codex_dir_mode_warning call within 5 lines after the header
        call_found = False
        for i in range(codex_header_line, min(codex_header_line + 6, len(lines))):
            if '_codex_dir_mode_warning "$_codex_banner"' in lines[i]:
                call_found = True
                break
        
        check("[codex] _codex_dir_mode_warning called within 5 lines of header",
              call_found, "")
        
        # Check that it's inside the _codex_banner conditional
        in_if_block = False
        for i in range(0, codex_header_line):
            if 'if [ -n "$_codex_banner" ]' in lines[i]:
                in_if_block = True
                if_start = i
        
        if in_if_block:
            # Find the matching fi
            depth = 0
            for i in range(if_start, len(lines)):
                if 'if [ -n "$_codex_banner" ]' in lines[i]:
                    depth += 1
                elif lines[i].strip().startswith('fi'):
                    depth -= 1
                    if depth == 0:
                        if_end = i
                        break
            
            call_in_if = False
            for i in range(if_start, if_end + 1):
                if '_codex_dir_mode_warning "$_codex_banner"' in lines[i]:
                    call_in_if = True
                    break
            
            check("[codex] _codex_dir_mode_warning inside _codex_banner if block",
                  call_in_if, "")


# ── task_045: host-side Codex opt-in registry (~/.vibe/codex-allow) ──────────
# Independent of checks_01's test_codex_container_plumbing (mount rendering)
# and test_codex_mount_drift (pure comparator, arbitrary strings): these cover
# the registry gate itself (_codex_opted_in / codex_allowed /
# codex_registry_usable), AC7's drift-through-_codex_desired_source case, and
# the `vibe codex allow|deny|list` subcommands against the REAL launcher.
# Every sourced call passes an EXPLICIT HOME to a fixture dir (never the real
# ~/.vibe), following checks_01's existing codex fixtures.

def _codex_git_ws(root, name="workspace"):
    """A throwaway git work tree, same recipe as checks_01's git_ws."""
    ws = root / name
    ws.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@users.noreply.github.com"],
                 ["config", "user.name", "T"], ["config", "core.hooksPath", "/dev/null"]):
        run(["git", "-C", str(ws), *args])
    return ws


def _codex_rc_call(home, func_call):
    """Source vibe with HOME=home, run func_call inside `if ... ; then/else`
    (so a non-zero return from the function under test does not itself
    trigger the sourced script's `set -e`), and report RC=0/RC=<n> on stdout.
    Returns the CompletedProcess; stderr carries the function's own ⚠ lines."""
    return _source_vibe_call(
        {"HOME": str(home)},
        f'if {func_call}; then echo "RC=0"; else echo "RC=$?"; fi')


def _codex_docker_stub(bindir, log):
    """A `docker` stub shadowing PATH: logs every invocation's argv to `log`
    (one line per call) and, for `ps`, prints $DOCKER_STUB_PS_OUTPUT (a fake
    container id, or empty for "no container") so _codex_deny's stop path can
    be exercised without a real Docker daemon."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "docker"
    stub.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
        # `ps -aq` = discovery (all containers); `ps -q` = the post-stop
        # verification (running only); `stop` honours DOCKER_STUB_STOP_EXIT;
        # DOCKER_STUB_PS_EXIT makes discovery itself fail (daemon down).
        'if [ "$1" = "ps" ] && [ "${DOCKER_STUB_PS_EXIT:-0}" != "0" ]; then exit "${DOCKER_STUB_PS_EXIT}"; fi\n'
        'if [ "$1" = "ps" ] && [ "$2" = "-aq" ]; then printf \'%s\\n\' "${DOCKER_STUB_PS_OUTPUT:-}"; fi\n'
        'if [ "$1" = "ps" ] && [ "$2" = "-q" ]; then printf \'%s\\n\' "${DOCKER_STUB_PS_RUNNING_OUTPUT:-}"; fi\n'
        'if [ "$1" = "stop" ]; then exit "${DOCKER_STUB_STOP_EXIT:-0}"; fi\n'
        "exit 0\n")
    stub.chmod(0o755)
    return stub


def test_codex_registry_gates():
    """AC1/AC2/AC9: _codex_opted_in's registry gate, and codex_allowed /
    codex_registry_usable directly, across the full precedence matrix."""
    print("\n[codex] ~/.vibe/codex-allow gate matrix (_codex_opted_in, codex_allowed, codex_registry_usable)")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        ws = _codex_git_ws(root)
        marker = ws / ".vibe-allow-codex"
        registry = home / ".vibe" / "codex-allow"

        def set_marker(present):
            if present:
                marker.write_text("")
            elif marker.exists():
                marker.unlink()

        def set_registry(lines):
            registry.parent.mkdir(parents=True, exist_ok=True)
            if registry.exists() or registry.is_symlink():
                registry.unlink()
            if lines is None:
                return
            registry.write_text("".join(line + "\n" for line in lines))
            registry.chmod(0o600)

        def opted_in(path=None):
            return _codex_rc_call(home, f'_codex_opted_in {shlex.quote(str(path or ws))}')

        # Neither marker nor registry: refused silently (nothing to warn about).
        set_marker(False); set_registry(None)
        r = opted_in()
        check("[codex] neither marker nor registry: RC=1, silent",
              r.returncode == 0 and "RC=1" in r.stdout and r.stderr == "", repr(r.stderr))

        # Registry-only: refused silently. No marker means no request was made.
        set_marker(False); set_registry([str(ws)])
        r = opted_in()
        check("[codex] registry-only (no marker): RC=1, silent",
              r.returncode == 0 and "RC=1" in r.stdout and r.stderr == "", repr(r.stderr))

        # Marker-only: refused, ONE ⚠ line naming `vibe codex allow`.
        set_marker(True); set_registry(None)
        r = opted_in()
        check("[codex] marker-only: RC=1, one ⚠ line naming vibe codex allow",
              r.returncode == 0 and "RC=1" in r.stdout and
              r.stderr.count("⚠") == 1 and "vibe codex allow" in r.stderr, r.stderr)

        # Both: opted in.
        set_marker(True); set_registry([str(ws)])
        r = opted_in()
        check("[codex] marker + registry: RC=0",
              r.returncode == 0 and "RC=0" in r.stdout and r.stderr == "", repr(r.stderr))

        # Committed marker + registry: the COMMITTED line fires, not the
        # allow hint — the three marker branches are checked BEFORE the
        # registry, so a malformed request is diagnosed as malformed even
        # when the registry would otherwise have granted it.
        run(["git", "-C", str(ws), "add", "-f", ".vibe-allow-codex"])
        r = opted_in()
        check("[codex] committed marker + registry: COMMITTED line, not the allow hint",
              r.returncode == 0 and "RC=1" in r.stdout and
              "COMMITTED" in r.stderr and "vibe codex allow" not in r.stderr, r.stderr)
        run(["git", "-C", str(ws), "rm", "-q", "--cached", ".vibe-allow-codex"])

        # Non-work-tree marker + registry: the work-tree line fires.
        plain = root / "plain"; plain.mkdir()
        (plain / ".vibe-allow-codex").write_text("")
        set_registry([str(plain)])
        r = opted_in(plain)
        check("[codex] non-work-tree marker + registry: work-tree line",
              r.returncode == 0 and "RC=1" in r.stdout and
              "verifiable git work tree" in r.stderr, r.stderr)

        # Symlinked registry: codex_registry_usable/codex_allowed treat it as
        # ABSENT with exactly one ⚠ line (fail closed) when called directly.
        set_marker(True)
        target = home / "real-file"; target.write_text(str(ws) + "\n")
        set_registry(None)
        registry.symlink_to(target)
        r = _codex_rc_call(home, "codex_registry_usable")
        check("[codex] symlinked registry: codex_registry_usable RC=1, one ⚠ line",
              r.returncode == 0 and "RC=1" in r.stdout and
              r.stderr.count("⚠") == 1 and "symlink" in r.stderr, r.stderr)
        r = _codex_rc_call(home, f"codex_allowed {shlex.quote(str(ws))}")
        check("[codex] symlinked registry: codex_allowed RC=1, one ⚠ line",
              r.returncode == 0 and "RC=1" in r.stdout and
              r.stderr.count("⚠") == 1 and "symlink" in r.stderr, r.stderr)
        r = opted_in()
        check("[codex] symlinked registry + marker: _codex_opted_in RC=1, warns",
              r.returncode == 0 and "RC=1" in r.stdout and "⚠" in r.stderr, r.stderr)
        registry.unlink()

        # Mode-644 registry: same fail-closed treatment, one ⚠ line.
        set_registry([str(ws)])
        registry.chmod(0o644)
        r = _codex_rc_call(home, "codex_registry_usable")
        check("[codex] mode-644 registry: codex_registry_usable RC=1, one ⚠ line",
              r.returncode == 0 and "RC=1" in r.stdout and
              r.stderr.count("⚠") == 1 and "chmod 600" in r.stderr, r.stderr)
        r = opted_in()
        check("[codex] mode-644 registry + marker: _codex_opted_in RC=1, warns",
              r.returncode == 0 and "RC=1" in r.stdout and "⚠" in r.stderr, r.stderr)
        registry.chmod(0o600)

        # Canonicalisation: the registry holds the real (pwd -P) path; a
        # launch from a SYMLINKED path is a different literal string, so
        # grep -qxF does not match it and the launch is refused exactly like
        # an unregistered project (the allow hint, not a distinct message).
        set_registry([str(ws)])
        set_marker(True)
        symlinked_ws = root / "workspace-link"
        symlinked_ws.symlink_to(ws)
        r = opted_in(symlinked_ws)
        check("[codex] canonicalisation: launch from a symlinked path is refused",
              r.returncode == 0 and "RC=1" in r.stdout and "vibe codex allow" in r.stderr, r.stderr)


def test_codex_mount_drift_with_desired_source():
    """AC7: codex_mount_drift fed the OUTPUT of _codex_desired_source (not a
    literal string) sees the registry line's removal/restoration as drift."""
    print("\n[codex] AC7 drift: codex_mount_drift(_codex_desired_source(ws), ...)")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        codex_dir = home / ".codex"; codex_dir.mkdir()
        ws = _codex_git_ws(root)
        (ws / ".vibe-allow-codex").write_text("")
        registry = home / ".vibe" / "codex-allow"
        actual = f"/home/node/.codex\t{codex_dir}\trw"

        def drift():
            call = (f'desired="$(_codex_desired_source {shlex.quote(str(ws))})"; '
                    f'printf "%s" "$(codex_mount_drift "$desired" "$(printf %s {shlex.quote(actual)})")"')
            return _source_vibe_call({"HOME": str(home)}, call)

        # Marker present, registry line removed: desired is empty, but the
        # mount is still bound -> drift.
        if registry.exists():
            registry.unlink()
        r = drift()
        check("[codex] AC7: marker present, registry line removed -> drift '1'",
              r.returncode == 0 and r.stdout == "1", f"stdout={r.stdout!r} stderr={r.stderr[:200]!r}")

        # Both present: desired matches the actual bind -> no drift.
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(str(ws) + "\n")
        registry.chmod(0o600)
        r = drift()
        check("[codex] AC7: marker + registry both present, matching bind -> no drift",
              r.returncode == 0 and r.stdout == "", f"stdout={r.stdout!r} stderr={r.stderr[:200]!r}")


def test_codex_allow_subcommand():
    """AC3: `vibe codex allow` against the real launcher — idempotent, mode
    600, refuses a non-directory and a non-git path."""
    print("\n[codex] `vibe codex allow` subcommand")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        ws = _codex_git_ws(root)
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config"}
        registry = home / ".vibe" / "codex-allow"

        r = run(["bash", str(VIBE), "codex", "allow"], env=env, cwd=ws)
        check("[codex] allow: exit 0, pinned ✓ line, marker reminder",
              r.returncode == 0 and
              f"✓ {ws} allowed to mount the Codex login (~/.vibe/codex-allow)" in r.stdout and
              ".vibe-allow-codex" in r.stdout, r.stdout + r.stderr)
        check("[codex] allow: registry mode 600",
              oct(registry.stat().st_mode)[-3:] == "600", oct(registry.stat().st_mode))
        check("[codex] allow: never creates the marker itself",
              not (ws / ".vibe-allow-codex").exists(), "")

        r2 = run(["bash", str(VIBE), "codex", "allow"], env=env, cwd=ws)
        check("[codex] allow twice: still exit 0",
              r2.returncode == 0, r2.stdout + r2.stderr)
        lines = [l for l in registry.read_text().splitlines() if l]
        check("[codex] allow twice: exactly one line, no duplicate",
              lines == [str(ws)], lines)

        missing = root / "does-not-exist"
        r3 = run(["bash", str(VIBE), "codex", "allow", str(missing)], env=env)
        check("[codex] allow: non-directory path refused, exit 1",
              r3.returncode == 1 and "is not a directory" in r3.stderr, r3.stderr)

        plain = root / "plain-not-git"; plain.mkdir()
        r4 = run(["bash", str(VIBE), "codex", "allow", str(plain)], env=env)
        check("[codex] allow: non-git-work-tree path refused, exit 1",
              r4.returncode == 1 and "not a git work tree" in r4.stderr, r4.stderr)
        check("[codex] allow: refused path never recorded",
              str(plain) not in registry.read_text(), registry.read_text())

        # Astra re-review (iter 3): a directory whose NAME ends in a newline
        # canonicalises, through `$(...)`, to its newline-less sibling — the
        # grant (or a revocation) would land on the wrong project. Both the
        # argument and the canonical result are refused when they carry one.
        before = registry.read_text()
        twin = Path(str(ws) + "\n"); twin.mkdir()
        run(["git", "init", "-q", str(twin)])
        r5 = run(["bash", str(VIBE), "codex", "allow", str(twin)], env=env)
        check("[codex] allow: newline-suffixed twin directory refused, exit 1",
              r5.returncode == 1 and "newline" in r5.stderr, r5.stdout + r5.stderr)
        check("[codex] allow: registry unchanged after the newline refusal",
              registry.read_text() == before, registry.read_text())
        r6 = run(["bash", str(VIBE), "codex", "allow", f"{root}/evil\n{ws}"], env=env)
        check("[codex] allow: embedded-newline argument refused, exit 1, nothing recorded",
              r6.returncode == 1 and registry.read_text() == before, r6.stderr)
        r7 = run(["bash", str(VIBE), "codex", "deny", str(twin)], env=env, input="")
        check("[codex] deny: newline-suffixed twin directory refused, sibling's line kept",
              r7.returncode == 1 and "newline" in r7.stderr and registry.read_text() == before, r7.stdout + r7.stderr)


def test_codex_deny_subcommand():
    """AC4: `vibe codex deny` against the real launcher — removes the line,
    idempotent ('already absent'), refuses a symlinked registry, and stops a
    running container unconditionally when stdin is not a TTY."""
    print("\n[codex] `vibe codex deny` subcommand")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        ws = _codex_git_ws(root)
        registry = home / ".vibe" / "codex-allow"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(str(ws) + "\n")
        registry.chmod(0o600)

        bindir = root / "bin"
        log = root / "docker.log"
        _codex_docker_stub(bindir, log)
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config",
               "PATH": str(bindir) + os.pathsep + os.environ["PATH"]}

        # A container "exists" for this workspace (stub ps returns an id).
        # stdin is not a TTY (empty-string input -> DEVNULL per run()'s own
        # discipline), so the stop must run WITHOUT the ask_yes_no prompt.
        deny_env = {**env, "DOCKER_STUB_PS_OUTPUT": "fakecontainerid"}
        r = run(["bash", str(VIBE), "codex", "deny"], env=deny_env, cwd=ws, input="")
        check("[codex] deny: exit 0, pinned ✓ removal line",
              r.returncode == 0 and
              f"✓ {ws} removed from ~/.vibe/codex-allow" in r.stdout, r.stdout + r.stderr)
        check("[codex] deny: line actually removed",
              str(ws) not in (registry.read_text() if registry.exists() else ""), "")
        check("[codex] deny: stdin not a TTY -> stop runs unconditionally, no prompt text",
              "ps -aq --filter label=devcontainer.local_folder=" + str(ws) in log.read_text() and
              "stop fakecontainerid" in log.read_text(), log.read_text())
        check("[codex] deny: never docker rm",
              " rm " not in log.read_text() and not log.read_text().splitlines()[-1].startswith("rm"), log.read_text())

        # Idempotent: removing again says "already absent", still exit 0.
        log.write_text("")
        r2 = run(["bash", str(VIBE), "codex", "deny"], env=env, cwd=ws, input="")
        check("[codex] deny: idempotent, 'already absent', exit 0",
              r2.returncode == 0 and "already absent" in r2.stdout, r2.stdout + r2.stderr)

        # Symlinked registry: refused outright, exit 1, never rewritten.
        target = home / "real-file"; target.write_text(str(ws) + "\n")
        if registry.exists() or registry.is_symlink():
            registry.unlink()
        registry.symlink_to(target)
        r3 = run(["bash", str(VIBE), "codex", "deny"], env=env, cwd=ws, input="")
        check("[codex] deny: symlinked registry refused, exit 1",
              r3.returncode == 1 and "unusable" in r3.stderr, r3.stderr)
        check("[codex] deny: symlinked registry left untouched (still a symlink)",
              registry.is_symlink(), "")

        # Astra review (iter 3): a failed or unverified stop must never be
        # reported as success — the container would still hold the login.
        registry.unlink()
        registry.write_text(str(ws) + "\n"); registry.chmod(0o600)
        log.write_text("")
        r4 = run(["bash", str(VIBE), "codex", "deny"], cwd=ws, input="",
                 env={**deny_env, "DOCKER_STUB_STOP_EXIT": "1"})
        check("[codex] deny: docker stop failure -> exit 1, ⚠ names the container as still holding the login",
              r4.returncode == 1 and "STILL holds" in r4.stderr and "no longer mounted" not in r4.stdout, r4.stdout + r4.stderr)
        registry.write_text(str(ws) + "\n"); registry.chmod(0o600)
        r5 = run(["bash", str(VIBE), "codex", "deny"], cwd=ws, input="",
                 env={**deny_env, "DOCKER_STUB_PS_RUNNING_OUTPUT": "fakecontainerid"})
        check("[codex] deny: container still listed as running after stop -> exit 1, not reported as unmounted",
              r5.returncode == 1 and "could not confirm" in r5.stderr and "no longer mounted" not in r5.stdout, r5.stdout + r5.stderr)
        registry.write_text(str(ws) + "\n"); registry.chmod(0o600)
        r6 = run(["bash", str(VIBE), "codex", "deny"], cwd=ws, input="",
                 env={**deny_env, "DOCKER_STUB_PS_EXIT": "1"})
        check("[codex] deny: docker discovery failure is visible (exit 1, ⚠), registry line still removed",
              r6.returncode == 1 and "docker ps failed" in r6.stderr and str(ws) not in registry.read_text(), r6.stdout + r6.stderr)

        # Astra review (iter 3): the registry is line-based; a path with an
        # embedded newline must never match, be recorded, or be removed.
        registry.write_text(str(ws) + "\n"); registry.chmod(0o600)
        evil = f"{root}/evil\n{ws}"
        r7 = _codex_rc_call(home, f'codex_allowed {shlex.quote(evil)}')
        check("[codex] newline-in-path never matches another project's grant", "RC=1" in r7.stdout, r7.stdout + r7.stderr)
        r8 = _codex_rc_call(home, f'codex_allow_record {shlex.quote(evil)}')
        check("[codex] newline-in-path is refused by codex_allow_record, registry unchanged",
              "RC=1" in r8.stdout and registry.read_text() == str(ws) + "\n", r8.stdout + r8.stderr)
        r9 = _codex_rc_call(home, f'codex_allow_remove {shlex.quote(evil)}')
        check("[codex] newline-in-path is refused by codex_allow_remove, registry unchanged",
              "RC=1" in r9.stdout and registry.read_text() == str(ws) + "\n", r9.stdout + r9.stderr)


def test_codex_list_subcommand():
    """AC5: `vibe codex list` status suffixes and the empty-registry case."""
    print("\n[codex] `vibe codex list` subcommand")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config"}

        r0 = run(["bash", str(VIBE), "codex", "list"], env=env, cwd=home)
        check("[codex] list: empty registry prints (none), exit 0",
              r0.returncode == 0 and r0.stdout.strip() == "(none)", r0.stdout)

        with_marker = _codex_git_ws(root, "with-marker")
        (with_marker / ".vibe-allow-codex").write_text("")
        no_marker = _codex_git_ws(root, "no-marker")
        gone = root / "gone-ws"; gone.mkdir()

        registry = home / ".vibe" / "codex-allow"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(f"{with_marker}\n{no_marker}\n{gone}\n")
        registry.chmod(0o600)
        import shutil
        shutil.rmtree(gone)

        r = run(["bash", str(VIBE), "codex", "list"], env=env, cwd=home)
        check("[codex] list: exit 0", r.returncode == 0, r.stderr)
        check("[codex] list: marker present",
              f"{with_marker} (marker present)" in r.stdout, r.stdout)
        check("[codex] list: no marker – not mounted",
              f"{no_marker} (no marker – not mounted)" in r.stdout, r.stdout)
        check("[codex] list: path missing",
              f"{gone} (path missing)" in r.stdout, r.stdout)


def test_codex_usage_and_help():
    """AC6: `vibe codex` / `vibe codex bogus` print usage on stderr and exit
    1; `vibe --help` names the three subcommands."""
    print("\n[codex] `vibe codex` usage and `vibe --help`")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{home}/no-config"}

        for args in (["codex"], ["codex", "bogus"]):
            r = run(["bash", str(VIBE), *args], env=env, cwd=home)
            check(f"[codex] {' '.join(args)}: usage on stderr, exit 1, no stdout",
                  r.returncode == 1 and
                  "Usage: vibe codex allow|deny|list [path]" in r.stderr and not r.stdout,
                  r.stdout + "|" + r.stderr)

        r = run(["bash", str(VIBE), "--help"], env=env)
        check("[codex] vibe --help mentions vibe codex allow|deny|list",
              "vibe codex allow|deny|list" in r.stdout, r.stdout[:2000])


def test_codex_allow_docs():
    """AC8: README/MANUAL-TESTS/TODO carry the registry's documentation.
    Whitespace-normalised (single spaces) before substring checks so a
    reflow of the source markdown's line wrapping can't break the test."""
    print("\n[codex] AC8 docs: README, MANUAL-TESTS Test 54 step 1, TODO re-filed follow-ups")

    def flat(text):
        return " ".join(text.split())

    readme = README_MD.read_text()
    check("[codex] README names `vibe codex allow`", "`vibe codex allow`" in readme, "")
    check("[codex] README names the registry as the reason a container cannot opt itself in",
          "a container cannot opt itself in" in readme, "")
    readme_flat = flat(readme)
    check("[codex] README describes the three-step opt-in (log in, marker, allow)",
          "1. **Log in**" in readme_flat and
          "2. **`touch .vibe-allow-codex`**" in readme_flat and
          "3. **`vibe codex allow`**" in readme_flat, "")

    manual = MANUAL_TESTS_MD.read_text()
    m = re.search(r"### Test 54:.*?(?=\n### Test \d+:|\Z)", manual, re.DOTALL)
    check("[codex] MANUAL-TESTS.md has a Test 54 section", m is not None, "")
    test54_flat = flat(m.group(0)) if m else ""
    step1_flat = flat(m.group(0).split("\n2.", 1)[0]) if m else ""
    check("[codex] Test 54 step 1 mentions `vibe codex allow`",
          "vibe codex allow" in step1_flat, step1_flat[:400])
    check("[codex] Test 54 negative case (d): marker present but not allowed on this machine",
          "(d) the marker present but the project NOT allowed on this machine" in test54_flat, "")
    check("[codex] Test 54 case (d) expects NO mount and exactly ONE warning naming vibe codex allow",
          "exactly ONE warning line, naming `vibe codex allow`" in test54_flat, "")

    todo = (REPO / "TODO.md").read_text()
    check("[codex] TODO.md closes the registry clause of the container-writable-filesystem entry",
          "SHIPPED (task_045, CHANGELOG)" in todo, "")
    check("[codex] TODO.md re-files the three still-open guard-gated follow-ups",
          "auth.json" in todo and "/learnings" in todo and "/zotero" in todo and
          "/repos/*/.vibe-allow-codex" in todo, "")
