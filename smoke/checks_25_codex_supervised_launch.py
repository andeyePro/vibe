"""Supervised launch argument and guard-boundary regression tests."""
from smoke._core import *
from smoke._core import _source_vibe_call
from smoke.checks_22_codex_agent import _entry_fixture, _entry_liveness_stub, CODEX_ENTRY


def test_codex_supervised_parser():
    for flag, action in [("--codex-run", "run"), ("--codex-resume", "resume")]:
        r = _source_vibe_call({}, f'parse_vibe_args {flag} "brief with spaces.md"; printf "%s|%s" "$CODEX_ACTION" "$CODEX_PROMPT_ARG"')
        check(f"[supervised] {flag} preserves a spaced prompt path", r.returncode == 0 and r.stdout == f"{action}|brief with spaces.md", r.stdout + r.stderr)
    for args in ["--codex-run", "--codex-resume --help", "--codex-run a --codex-resume b"]:
        r = _source_vibe_call({}, f"parse_vibe_args {args}")
        check(f"[supervised] refuses malformed flags {args}", r.returncode != 0, r.stdout + r.stderr)


def test_codex_supervised_entry_requires_gate():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bins, login, codex, codex_log = _entry_fixture(tmp)
        entry = bins / "codex-entry"
        entry.write_text(CODEX_ENTRY.read_text())
        entry.chmod(0o755)
        supervisor = bins / "codex-supervisor"
        supervisor_log = tmp / "supervisor-argv.json"
        supervisor.write_text(f"#!{sys.executable}\nimport json,sys\nopen({str(supervisor_log)!r},'w').write(json.dumps(sys.argv[1:]))\n")
        supervisor.chmod(0o755)
        argv = ["bash", str(entry), "--root", str(root), "--bin", str(bins), "--login-dir", str(login), "--codex", str(codex), "--supervise", "--", "run", "--cwd", "/workspace", "--prompt-file", "/workspace/brief with spaces.md"]
        _entry_liveness_stub(bins, False, tmp / "gate.log")
        r = run(argv)
        check("[supervised] failed gate starts neither supervisor nor vendor", r.returncode != 0 and not supervisor_log.exists() and not codex_log.exists(), r.stdout + r.stderr)
        _entry_liveness_stub(bins, True, tmp / "gate.log")
        r = run(argv)
        check("[supervised] successful gate hands argv to supervisor exactly", r.returncode == 0 and json.loads(supervisor_log.read_text()) == argv[argv.index("--") + 1:] and not codex_log.exists(), r.stdout + r.stderr)
        supervisor_log.unlink()
        supervisor.chmod(0o644)
        r = run(argv)
        check("[supervised] missing execute permission refuses before handoff", r.returncode != 0 and not supervisor_log.exists(), r.stdout + r.stderr)
