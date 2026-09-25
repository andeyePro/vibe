"""Automatic Claude Code + Codex updates, and the Codex compatibility gate.

Martin (2026-09-25): "I want all the latest codex updates while having to do
as little as possible to get them." Both CLIs are baked into the image, so the
launcher checks npm at most once a day and rebuilds when either moved; Codex
follows latest only if the new version passes codex-compat-check at build
time, else the build falls back to the last version that passed.

The build-path tests splice the launcher's real block (from the daily check to
the end of the base build) and run it against stub `docker` and `npm`.
"""
from smoke._core import *  # noqa: F401,F403

import os
import subprocess
import tempfile

GATE = REPO / "devcontainer" / "codex-compat-check.sh"


def _block() -> str:
    src = VIBE.read_text()
    start = src.index("# Daily update check (see cli_latest_version above)")
    end = src.index("  BASE_REBUILT=true\nfi\n", start) + len("  BASE_REBUILT=true\nfi\n")
    return src[start:end]


def _stubs(td: Path, npm_claude: str = "2.2.0", npm_codex: str = "0.158.0", failing_codex: str = "",
           image_exists: bool = True, other_failure: bool = False, npm: bool = True) -> Path:
    bindir = td / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "npm").write_text(
        "#!/bin/bash\n"
        + ("" if npm else "exit 1\n")
        + f"case \"$2\" in @anthropic-ai/claude-code) echo '{npm_claude}' ;; @openai/codex) echo '{npm_codex}' ;; esac\n")
    (bindir / "docker").write_text(
        "#!/bin/bash\n"
        f"echo \"docker $*\" >> {td}/docker.log\n"
        f"[ \"$1 $2\" = 'image inspect' ] && exit {0 if image_exists else 1}\n"
        f"if [ \"$1\" = build ] && [ -n '{failing_codex}' ] && [[ \"$*\" == *'CODEX_VERSION={failing_codex}'* ]]; then\n"
        "  echo 'codex-compat-check: FAIL multi_agent is ON' >&2; exit 1; fi\n"
        + ("[ \"$1\" = build ] && { echo 'network unreachable' >&2; exit 1; }\n" if other_failure else "")
        + "exit 0\n")
    for f in ("npm", "docker"):
        (bindir / f).chmod(0o755)
    return bindir


def _run_block(td: Path, bindir: Path, env_extra: dict | None = None, rebuild: str = "false",
               requested: str = "false"):
    home = td / "home"
    (home / ".vibe").mkdir(parents=True, exist_ok=True)
    call = (f"REBUILD={rebuild}\nREBUILD_REQUESTED={requested}\nBASE_TAG=vibe-dev:latest\n"
            f"IMAGE_MARKER={home}/.vibe/.image-built\n"
            f"IMAGE_VERSIONS={home}/.vibe/.image-versions\nUPDATE_STAMP={home}/.vibe/.update-check\n"
            + _block() + "\necho \"REBUILT=[$BASE_REBUILT]\"\n")
    env = {"HOME": str(home), "PATH": f"{bindir}:{os.environ.get('PATH', '')}", **(env_extra or {})}
    return _source_vibe_call(env, call), home


def test_auto_update_helpers():
    print("\n[update] cli_latest_version, image_version, update_check_due, dockerfile_codex_default")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm_codex="0.157.0; rm -rf /")
        home = td / "home"
        (home / ".vibe").mkdir(parents=True)
        (home / ".vibe" / ".image-versions").write_text("claude-code=2.1.281\ncodex=0.156.1\ncodex-good=0.156.1\nbad=$(id)\n")
        snippet = (
            f'IMAGE_VERSIONS={home}/.vibe/.image-versions; UPDATE_STAMP={home}/.vibe/.update-check; '
            'echo "CLAUDE=[$(cli_latest_version @anthropic-ai/claude-code)]"; '
            'echo "CODEX=[$(cli_latest_version @openai/codex)]"; '
            'echo "IV=[$(image_version codex)] [$(image_version bad)] [$(image_version missing)]"; '
            'update_check_due 1000 && echo DUE1=yes || echo DUE1=no; '
            'echo 990 > "$UPDATE_STAMP"; update_check_due 1000 && echo DUE2=yes || echo DUE2=no; '
            'update_check_due 100000 && echo DUE3=yes || echo DUE3=no; '
            '(VIBE_AUTO_UPDATE=0; update_check_due 100000 && echo DUE4=yes || echo DUE4=no); '
            'echo "DEF=[$(dockerfile_codex_default)]"'
        )
        r = _source_vibe_call({"HOME": str(home), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"}, snippet)
        out = r.stdout
        check("[update] latest Claude Code read from npm", "CLAUDE=[2.2.0]" in out, out)
        check("[update] a shell-shaped npm answer is dropped", "CODEX=[]" in out, out)
        check("[update] recorded versions read; injection-shaped and missing values empty", "IV=[0.156.1] [] []" in out, out)
        check("[update] no stamp -> check due", "DUE1=yes" in out, out)
        check("[update] checked 10s ago -> not due", "DUE2=no" in out, out)
        check("[update] a day later -> due", "DUE3=yes" in out, out)
        check("[update] VIBE_AUTO_UPDATE=0 -> never", "DUE4=no" in out, out)
        default = (REPO / "devcontainer/Dockerfile").read_text().split("ARG CODEX_VERSION=", 1)[1].split("\n", 1)[0]
        check("[update] the Dockerfile's pinned Codex is the fallback", f"DEF=[{default}]" in out, out)


def test_auto_update_rebuilds_when_either_cli_moved():
    print("\n[update] a newer Claude Code or Codex on npm rebuilds the image with them, once a day")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td)
        (td / "home" / ".vibe").mkdir(parents=True)
        (td / "home" / ".vibe" / ".image-versions").write_text("claude-code=2.1.281\ncodex=0.156.1\ncodex-good=0.156.1\n")
        r, home = _run_block(td, bindir)
        log = (td / "docker.log").read_text() if (td / "docker.log").exists() else ""
        check("[update] announces the update", "update available: Claude Code 2.2.0, Codex 0.158.0" in r.stdout, r.stdout + r.stderr)
        check("[update] builds with both latest versions",
              "CLAUDE_CODE_VERSION=2.2.0" in log and "CODEX_VERSION=0.158.0" in log and "REBUILT=[true]" in r.stdout, log)
        versions = (home / ".vibe" / ".image-versions").read_text()
        check("[update] records what the image now holds", "claude-code=2.2.0" in versions and "codex=0.158.0" in versions
              and "codex-good=0.158.0" in versions, versions)
        (td / "docker.log").unlink()
        r, home = _run_block(td, bindir)
        check("[update] the same day: no second check, no rebuild",
              "REBUILT=[false]" in r.stdout and "docker build" not in ((td / "docker.log").read_text() if (td / "docker.log").exists() else ""), r.stdout)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm_claude="2.1.281", npm_codex="0.156.1")
        (td / "home" / ".vibe").mkdir(parents=True)
        (td / "home" / ".vibe" / ".image-versions").write_text("claude-code=2.1.281\ncodex=0.156.1\ncodex-good=0.156.1\n")
        r, home = _run_block(td, bindir)
        check("[update] nothing newer -> no rebuild", "REBUILT=[false]" in r.stdout and "update available" not in r.stdout, r.stdout)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td)
        r, home = _run_block(td, bindir, {"VIBE_AUTO_UPDATE": "0"})
        check("[update] VIBE_AUTO_UPDATE=0 -> no check, no rebuild", "REBUILT=[false]" in r.stdout, r.stdout)


def test_auto_update_falls_back_when_codex_fails_the_gate():
    print("\n[update] a Codex that fails the build-time gate falls back to the last good one, and is not retried")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm_codex="0.158.0", failing_codex="0.158.0")
        (td / "home" / ".vibe").mkdir(parents=True)
        (td / "home" / ".vibe" / ".image-versions").write_text("claude-code=2.2.0\ncodex=0.157.0\ncodex-good=0.157.0\n")
        r, home = _run_block(td, bindir)
        log = (td / "docker.log").read_text()
        check("[update] first build tried the new Codex, then retried with the last good one",
              log.count("docker build") == 2 and log.index("CODEX_VERSION=0.158.0") < log.index("CODEX_VERSION=0.157.0"), log)
        check("[update] the fallback is announced", "building with Codex 0.157.0, the last version that passed" in r.stderr, r.stderr)
        versions = (home / ".vibe" / ".image-versions").read_text()
        check("[update] records the failure and keeps the good version", "codex-failed=0.158.0" in versions
              and "codex-good=0.157.0" in versions, versions)
        (home / ".vibe" / ".update-check").write_text("1\n")
        (td / "docker.log").unlink()
        r, home = _run_block(td, bindir)
        check("[update] a version that already failed does not trigger another rebuild",
              "REBUILT=[false]" in r.stdout, r.stdout + r.stderr)
        # A later rebuild for another reason (say a Claude Code update) must
        # keep the record, or the failed Codex comes back the day after.
        (td / "docker.log").unlink(missing_ok=True)
        r, home = _run_block(td, bindir, rebuild="true")
        log = (td / "docker.log").read_text()
        versions = (home / ".vibe" / ".image-versions").read_text()
        check("[update] an unrelated rebuild skips the failed Codex and keeps the record",
              "CODEX_VERSION=0.158.0" not in log and "codex-failed=0.158.0" in versions, log + versions)
        (td / "docker.log").unlink()
        r, home = _run_block(td, bindir, rebuild="true", requested="true")
        log = (td / "docker.log").read_text()
        check("[update] vibe --rebuild retries the failed Codex (the manual way out)",
              "CODEX_VERSION=0.158.0" in log, log)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm_codex="0.157.0", failing_codex="0.157.0")
        (td / "home" / ".vibe").mkdir(parents=True)
        (td / "home" / ".vibe" / ".image-versions").write_text("codex=0.157.0\ncodex-good=0.157.0\n")
        r, home = _run_block(td, bindir, rebuild="true")
        check("[update] a failing build with no different fallback still stops the launcher",
              r.returncode != 0 and "image build failed" in r.stderr, r.stdout + r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm_codex="0.158.0", other_failure=True)
        (td / "home" / ".vibe").mkdir(parents=True)
        (td / "home" / ".vibe" / ".image-versions").write_text("codex=0.157.0\ncodex-good=0.157.0\n")
        r, home = _run_block(td, bindir, rebuild="true")
        log = (td / "docker.log").read_text()
        check("[update] a non-gate build failure (network) is not blamed on Codex: no fallback, no record, launcher stops",
              r.returncode != 0 and log.count("docker build") == 1
              and "codex-failed" not in (home / ".vibe" / ".image-versions").read_text(), log + r.stderr)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        bindir = _stubs(td, npm=False)
        r, home = _run_block(td, bindir, rebuild="true")
        log = (td / "docker.log").read_text()
        default = (REPO / "devcontainer/Dockerfile").read_text().split("ARG CODEX_VERSION=", 1)[1].split("\n", 1)[0]
        check("[update] npm unavailable: builds with the Dockerfile's pinned Codex and Claude 'latest'",
              r.returncode == 0 and f"CODEX_VERSION={default}" in log and "CLAUDE_CODE_VERSION=latest" in log, log + r.stderr)


def test_codex_compat_gate_is_wired_and_passes_the_installed_codex():
    print("\n[update] codex-compat-check: in the image build, and passing for the installed Codex")
    dockerfile = (REPO / "devcontainer/Dockerfile").read_text()
    check("[update] the gate is installed root-owned and run during the build",
          "COPY --chown=root:root codex-compat-check.sh /usr/local/bin/codex-compat-check" in dockerfile
          and "RUN chmod 0755 /usr/local/bin/codex-compat-check && /usr/local/bin/codex-compat-check" in dockerfile)
    check("[update] the gate runs after the managed policy is copied in",
          dockerfile.index("COPY --chown=root:root codex/ /etc/codex/") < dockerfile.index("&& /usr/local/bin/codex-compat-check"))
    import shutil
    if shutil.which("codex") and Path("/etc/codex/requirements.toml").exists():
        cfg = str(REPO / "devcontainer/codex/config.toml")
        r = subprocess.run(["bash", str(GATE), "--config", cfg], capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        check("[update] the installed Codex passes the gate under the repo's policy",
              r.returncode == 0 and "is compatible" in r.stdout and "no native sub-agents" in r.stdout, r.stdout + r.stderr)
        empty = Path(tempfile.mkdtemp()) / "config.toml"
        empty.write_text("# no [agents] section\n")
        r = subprocess.run(["bash", str(GATE), "--config", str(empty)], capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        check("[update] the gate is behavioural: a policy without [agents] enabled=false is refused on an older image, "
              "or passes only because /etc/codex already has it",
              ("FAIL the model is offered native sub-agents" in r.stderr)
              or "[agents]" in Path("/etc/codex/config.toml").read_text(), r.stdout + r.stderr)
    with tempfile.TemporaryDirectory() as t:
        stub = Path(t) / "codex"
        rows = "\n".join(f"feature_{i}  stable  false" for i in range(12))
        stub.write_text("#!/bin/bash\n[ \"$1\" = --version ] && echo 'codex-cli 9.9.9' && exit 0\n"
                        f"[ \"$1 $2\" = 'features list' ] && printf '%s\\n' '{rows}' 'multi_agent  stable  true' && exit 0\nexit 1\n")
        stub.chmod(0o755)
        r = subprocess.run(["bash", str(GATE), "--codex", str(stub)], capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        check("[update] a Codex that turns multi_agent back on fails the gate",
              r.returncode != 0 and "multi_agent is ON" in r.stderr, r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as t:
        stub = Path(t) / "codex"
        stub.write_text("#!/bin/bash\n[ \"$1\" = --version ] && echo 'codex-cli 9.9.9' && exit 0\n"
                        "[ \"$1 $2\" = 'features list' ] && echo 'Feature list moved to the web UI' && exit 0\nexit 1\n")
        stub.chmod(0o755)
        r = subprocess.run(["bash", str(GATE), "--codex", str(stub)], capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        check("[update] an unparseable features list fails the gate (absence would prove nothing)",
              r.returncode != 0 and "cannot be trusted" in r.stderr, r.stdout + r.stderr)
        stub.write_text("#!/bin/bash\n[ \"$1\" = --version ] && echo 'codex-cli 0.100.0' && exit 0\nexit 1\n")
        r = subprocess.run(["bash", str(GATE), "--codex", str(stub)], capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        check("[update] a Codex below the policy floor fails the gate", r.returncode != 0 and "floor" in r.stderr, r.stderr)
