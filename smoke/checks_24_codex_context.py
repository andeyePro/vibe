"""Independent smoke coverage for the Codex context and role boundaries."""
from smoke._core import *  # noqa: F401,F403
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call

import json


CONTEXT = REPO / "devcontainer/codex-context.mjs"
PREFIX = REPO / "devcontainer/codex-prompt-prefix.sh"
DELEGATE = REPO / "devcontainer/vibe-delegate.mjs"


def _context_fixture(tmp):
    root = tmp / "project"
    root.mkdir()
    (root / ".vibe").mkdir()
    run(["git", "init", "-q", str(root)])
    sub = root / "nested"
    sub.mkdir()
    return root, sub


def _discover(cwd, bin_dir=None):
    args = ["node", str(CONTEXT), str(cwd)]
    if bin_dir is not None:
        # The CLI accepts only the project directory; use an import wrapper for
        # the helper-path assertion while keeping discovery itself real.
        script = "import {discover} from %s; console.log(JSON.stringify(discover(process.argv[1], process.argv[2])))" % json.dumps(CONTEXT.as_uri())
        args = ["node", "--input-type=module", "-e", script, str(cwd), str(bin_dir)]
    result = run(args)
    return result, json.loads(result.stdout) if result.returncode == 0 else None


def test_codex_context_discovery_defaults_and_git_root():
    print("\n[codex-context] defaults, configured paths, and root-relative resolution")
    with tempfile.TemporaryDirectory() as td:
        root, sub = _context_fixture(Path(td))
        (root / "AGENTS.md").write_text("PRIVATE REFERENCED CONTENT")
        (root / "docs").mkdir()
        config = {"references": ["AGENTS.md", "custom.md"], "questions": ".vibe/questions", "answers": "answers.md", "archive": ".vibe/archive", "build": ".vibe/build.json"}
        (root / ".vibe/codex-context.json").write_text(json.dumps(config))
        (root / "custom.md").write_text("SECRET CUSTOM CONTENT")
        result, data = _discover(sub)
        check("[codex-context] discovers git root from a subdirectory", result.returncode == 0 and data["root"] == str(root), result.stderr)
        paths = {item["path"] for item in data["references"]}
        check("[codex-context] includes defaults and configured references once", paths == {str(root / x) for x in ("AGENTS.md", "CLAUDE.md", "TODO.md", "docs/spec", ".vss/sessions", "custom.md")}, str(paths))
        check("[codex-context] reports channels/build relative to git root", data["channels"]["questions"]["path"] == str(root / ".vibe/questions") and data["build"]["path"] == str(root / ".vibe/build.json"), str(data))
        check("[codex-context] does not read referenced contents", "PRIVATE REFERENCED CONTENT" not in result.stdout and "SECRET CUSTOM CONTENT" not in result.stdout, result.stdout)


def test_codex_context_config_constraints():
    print("\n[codex-context] config size, shape, tracking, and symlink rejection")
    with tempfile.TemporaryDirectory() as td:
        root, _ = _context_fixture(Path(td))
        config_path = root / ".vibe/codex-context.json"
        invalid = [
            ({"unknown": "x"}, "unknown key"),
            ({"references": ["x"] * 51}, "too many references"),
            ({"references": [1]}, "non-string reference"),
            ({"questions": "   "}, "blank channel"),
            ("not-json", "malformed JSON"),
        ]
        for value, label in invalid:
            config_path.write_text(value if isinstance(value, str) else json.dumps(value))
            result, _ = _discover(root)
            check(f"[codex-context] rejects {label}", result.returncode != 0, result.stderr)
        prefix, suffix = '{"references":["', '"]}'
        config_path.write_text(prefix + "x" * (65536 - len(prefix) - len(suffix)) + suffix)
        result, _ = _discover(root)
        check("[codex-context] accepts config exactly 64 KiB", result.returncode == 0, result.stderr)
        config_path.write_text(json.dumps({"references": ["x"]}) + " " * 65536)
        result, _ = _discover(root)
        check("[codex-context] rejects config over 64 KiB", result.returncode != 0, result.stderr)
        config_path.write_text(json.dumps({"references": ["x"]}))
        run(["git", "add", ".vibe/codex-context.json"], cwd=root)
        result, _ = _discover(root)
        check("[codex-context] rejects tracked config", result.returncode != 0, result.stderr)
        run(["git", "reset", "-q", "HEAD", "--", ".vibe/codex-context.json"], cwd=root)
        config_path.unlink()
        config_path.mkdir()
        result, _ = _discover(root)
        check("[codex-context] rejects non-regular config", result.returncode != 0, result.stderr)
        config_path.rmdir()
        config_path.symlink_to(root / "target.json")
        (root / "target.json").write_text("{}")
        result, _ = _discover(root)
        check("[codex-context] rejects symlink config", result.returncode != 0, result.stderr)


def test_codex_context_missing_helpers_are_false():
    print("\n[codex-context] helper availability is reported, not assumed")
    with tempfile.TemporaryDirectory() as td:
        root, _ = _context_fixture(Path(td))
        result, data = _discover(root, Path(td) / "empty-bin")
        check("[codex-context] discovery succeeds with an empty helper bin", result.returncode == 0, result.stderr)
        check("[codex-context] missing executable helpers report false", data is not None and all(not x["executable"] for x in data["installedHelpers"]), str(data))
        check("[codex-context] unconfigured project has local FM2C paths", data is not None and data["channels"]["answers"]["path"] == str(root / ".vss/fromMartin-toCodex.md") and data["channels"]["questions"]["path"] == str(root / ".vss/fromCodex.md") and data["channels"]["archive"]["path"] == str(root / ".vss/Codex-Q&A-archive.md"), str(data))
        check("[codex-context] discovery does not create channels or require integration", not (root / ".vss").exists() and not (root / ".vibe/taskandi.json").exists(), "")
        installed = Path(td) / "codex-context"
        installed.symlink_to(CONTEXT)
        linked = run(["node", str(installed)], cwd=root / "nested")
        linked_data = json.loads(linked.stdout) if linked.stdout.strip() else {}
        check("[codex-context] installed symlink discovers another repo from nested cwd", linked.returncode == 0 and linked_data.get("root") == str(root), linked.stderr)
        invalid = run(["node", str(installed), str(root), "extra"], cwd=root)
        check("[codex-context] installed symlink rejects invalid arguments", invalid.returncode != 0 and "Usage:" in invalid.stderr, invalid.stderr)


def _prefix(payload):
    return run(["bash", str(PREFIX)], input=json.dumps(payload) + "\n")


def test_codex_context_prompt_prefix_routes_session_and_fm2c():
    print("\n[codex-context] prompt-prefix SessionStart, no-op, and FM2C routes")
    session = _prefix({"hook_event_name": "SessionStart"})
    check("[codex-context] SessionStart emits context-document instruction", session.returncode == 0 and "codex-context.md" in session.stdout and "additionalContext" in session.stdout, session.stderr)
    unrelated = _prefix({"hook_event_name": "UserPromptSubmit", "prompt": "ordinary project question"})
    check("[codex-context] unrelated prompt stays empty", unrelated.returncode == 0 and unrelated.stdout == "", unrelated.stderr)
    for phrase in ("help", " HELP? ", "commands", "?", "What can you do?"):
        help_result = _prefix({"hook_event_name": "UserPromptSubmit", "prompt": phrase})
        check(f"[codex-context] {phrase!r} delivers help without invoking a task", help_result.returncode == 0 and "$vsss" in help_result.stdout and "Do not execute a harness" in help_result.stdout, help_result.stderr)

    fm2c = _prefix({"hook_event_name": "UserPromptSubmit", "prompt": "please fm2c now"})
    check("[codex-context] FM2C is case-insensitive and names answer channel", fm2c.returncode == 0 and "vibe-fromMartin-toCodex.md" in fm2c.stdout and "codex-context.md" in fm2c.stdout, fm2c.stderr)


def test_codex_context_docker_installs_delegate():
    dockerfile = (REPO / "devcontainer/Dockerfile").read_text()
    check("[codex-context] Dockerfile copies vibe-delegate to /usr/local/bin", "COPY vibe-delegate.mjs /usr/local/bin/vibe-delegate" in dockerfile, "")
    check("[codex-context] Dockerfile marks vibe-delegate executable", "/usr/local/bin/vibe-delegate" in next((line for line in dockerfile.splitlines() if line.strip().startswith("RUN chmod +x")), ""), "")


def test_codex_context_openai_roles_route_usage_and_policy():
    print("\n[codex-context] OpenAI role IDs, usage, refusal, and codex=off")
    expected = {"astra": "gpt-6-astra", "terra": "gpt-5.6-terra", "sol": "gpt-5.6-sol", "luna": "gpt-5.6-luna"}
    with tempfile.TemporaryDirectory() as td:
        root, home, env = _delegate_fixture(Path(td))
        for role, model_id in expected.items():
            result, calls = _delegate_call(root, home, env, ["role", "reviewer", "--model", role, "--cwd", str(root)], {"answer": {"report": "fixture report", "status": "done"}})
            check(f"[codex-context] {role} routes to exact OpenAI model", result.returncode == 0 and calls[-1]["args"][2] == model_id, str(calls))
            if result.returncode == 0:
                output = json.loads(result.stdout)
                check(f"[codex-context] {role} usage matches selected call", output["model"] == model_id and output["usage"]["total_tokens"] == 5044, result.stdout)
        result, calls = _delegate_call(root, home, env, ["role", "reviewer", "--model", "unknown", "--cwd", str(root)])
        check("[codex-context] unknown model refuses before vendor calls", result.returncode != 0 and not calls, result.stderr)
        (root / ".vibe/review-slots").write_text("codex=off\n")
        result, calls = _delegate_call(root, home, env, ["role", "reviewer", "--model", "astra", "--cwd", str(root)])
        check("[codex-context] codex=off blocks OpenAI role with zero calls", result.returncode != 0 and not calls, result.stderr)
