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
        if 'echo' in line and 'codex' in line and ':' in line:
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
