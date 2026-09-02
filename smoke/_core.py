#!/usr/bin/env python3
"""Fast smoke tests for vibe — no docker, no network.

Covers host-side behaviours that don't require spinning up a container:
  - vibe --help parses and prints usage
  - devcontainer/write-env-hint.sh manages its block correctly
  - vibe token helpers round-trip through ~/.vibe/tokens with chmod 600

End-to-end tests (container lifecycle, firewall, SSH, auto-rebuild) live in
MANUAL-TESTS.md because they need a real Docker daemon.

Usage:
    python3 smoke-test.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VIBE = REPO / "vibe"
INSTALL = REPO / "install.sh"
WRITE_ENV_HINT = REPO / "devcontainer" / "write-env-hint.sh"
VIBE_COPY = REPO / "devcontainer" / "vibe-copy.sh"
DOCKERFILE = REPO / "devcontainer" / "Dockerfile"
INSTALL_EXTRAS = REPO / "devcontainer" / "install-claude-extras.sh"
C_MD = REPO / "devcontainer" / "commands" / "c.md"
VIBE_COPY_WATCHER = REPO / "vibe-copy-watcher.sh"
WEB_RESEARCH_MD = REPO / "devcontainer" / "claude-md" / "web-research.md"
SSH_DISCIPLINE_MD = REPO / "devcontainer" / "claude-md" / "ssh-discipline.md"
BRAIN2_MD = REPO / "devcontainer" / "claude-md" / "brain2.md"
LEARNINGS_MD = REPO / "devcontainer" / "claude-md" / "learnings.md"
REPO_MD = REPO / "devcontainer" / "commands" / "repo.md"
SHARED_REPOS_MD = REPO / "devcontainer" / "claude-md" / "shared-repos.md"
TODO_CHANGELOG_MD = REPO / "devcontainer" / "claude-md" / "todo-changelog.md"
PROJECT_HYGIENE_MD = REPO / "devcontainer" / "claude-md" / "project-hygiene.md"
AUTO_MEMORY_SCOPE_MD = REPO / "devcontainer" / "claude-md" / "auto-memory-scope.md"
CHANGELOG_MD = REPO / "CHANGELOG.md"
SECURITY_MD = REPO / "SECURITY.md"
BUG_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "bug_report.md"
FEATURE_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "feature_request.md"
PR_TEMPLATE = REPO / ".github" / "PULL_REQUEST_TEMPLATE.md"
VS_MD = REPO / "devcontainer" / "commands" / "vs.md"
SP_MD = REPO / "devcontainer" / "commands" / "sp.md"
VSS_MD = REPO / "devcontainer" / "commands" / "vss.md"
VSSS_MD = REPO / "devcontainer" / "commands" / "vsss.md"
WIDE_MD = REPO / "devcontainer" / "commands" / "wide.md"
NARROW_MD = REPO / "devcontainer" / "commands" / "narrow.md"
DIET_MD = REPO / "devcontainer" / "commands" / "diet.md"
FEAST_MD = REPO / "devcontainer" / "commands" / "feast.md"
README_MD = REPO / "README.md"
MANUAL_TESTS_MD = REPO / "MANUAL-TESTS.md"
CHECK_SP_CURRENT = REPO / "devcontainer" / "check-sp-current.sh"
CYCLE_1_DIFF = REPO / ".vs" / "cycle-1" / "diff.patch"
CREDENTIAL_HELPER = REPO / "devcontainer" / "credential-helper.sh"
SETUP_GIT_SH = REPO / "devcontainer" / "setup-git.sh"
VIBE_CONTENT_SCANNER = REPO / "devcontainer" / "git-hooks" / "vibe-content-scan.sh"
CONTENT_GUARD_MD = REPO / "devcontainer" / "claude-md" / "content-guard.md"
WORKSPACE_IS_THE_REPO_MD = REPO / "devcontainer" / "claude-md" / "workspace-is-the-repo.md"
INIT_FIREWALL = REPO / "devcontainer" / "init-firewall.sh"

FAILURES: list[tuple[str, str]] = []


_EXTRAS_SCRATCH_HOME: str | None = None


def _isolate_extras_env(env: dict) -> dict:
    """Make an install-claude-extras.sh invocation harmless to the real
    environment (security-review finding, 2026-08-30): the installer
    unconditionally writes global git config — `core.hooksPath` to a path
    under CLAUDE_CONFIG_DIR (a deleted TemporaryDirectory after teardown,
    which silently detaches the content-guard pre-commit/commit-msg/pre-push
    scanners until the next container start) and safe.directory entries —
    and ensure_project_gitignore writes the real /workspace/.gitignore.
    Redirects HOME (when it is still the real one) and GIT_CONFIG_GLOBAL to
    a session-scoped scratch dir, and defaults VIBE_AUTO_GITIGNORE=0.
    Respects overrides a test set deliberately. Every INSTALL_EXTRAS call
    site MUST route its env through this helper —
    test_extras_invocations_isolated pins that statically."""
    global _EXTRAS_SCRATCH_HOME
    if _EXTRAS_SCRATCH_HOME is None:
        _EXTRAS_SCRATCH_HOME = tempfile.mkdtemp(prefix="vibe-extras-home.")
    env = dict(env)
    if env.get("HOME") == os.environ.get("HOME"):
        env["HOME"] = _EXTRAS_SCRATCH_HOME
    # The installer's DEST_ROOT prefers CLAUDE_CONFIG_DIR over $HOME/.claude,
    # and vibe sets CLAUDE_CONFIG_DIR ambiently in-container — so a sandboxed
    # HOME alone still let installer runs rewrite the LIVE ~/.claude/CLAUDE.md
    # managed block with test-fixture gates (observed 2026-09-02: shared-repos
    # fragment injected, brain2 fragment dropped, mid-session). Pin it to the
    # scratch HOME unless the caller chose its own sandbox.
    if env.get("CLAUDE_CONFIG_DIR") == os.environ.get("CLAUDE_CONFIG_DIR"):
        env["CLAUDE_CONFIG_DIR"] = str(Path(_EXTRAS_SCRATCH_HOME) / ".claude")
    env.setdefault("GIT_CONFIG_GLOBAL",
                   str(Path(_EXTRAS_SCRATCH_HOME) / "gitconfig"))
    env.setdefault("VIBE_AUTO_GITIGNORE", "0")
    return env


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  {'✓' if cond else '✗'} {name}")
    if not cond:
        FAILURES.append((name, detail))
    return cond


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None, input: str = ""):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env if env is not None else os.environ.copy(),
        cwd=cwd,
        input=input if input else None,
    )


def run_bytes(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None, input_bytes: bytes = b""):
    """Run a subprocess and return stdout/stderr/returncode as bytes."""
    return subprocess.run(
        cmd,
        capture_output=True,
        env=env if env is not None else os.environ.copy(),
        cwd=cwd,
        input=input_bytes if input_bytes else None,
    )


VERSION_FILE = REPO / "VERSION"
WEB_VIBE_ANDEYE_MD = REPO / "web" / "vibe-andeye.md"


def _run_ensure_docker_hints_off(home: Path):
    env = {
        **os.environ,
        "HOME": str(home),
        "VIBE_CONFIG": f"{home}/no-config",
        "VIBE_SOURCE_ONLY": "1",
    }
    script = f"source {shlex.quote(str(VIBE))}; ensure_docker_hints_off"
    return run(["bash", "-c", script], env=env)


def _stub_dep_bin(tmp: Path) -> str:
    """A bin dir of no-op stubs for vibe's runtime deps, prepended to PATH so
    install.sh's dependency preflight passes regardless of what the host has
    installed. For tests that exercise post-preflight behaviour (clone
    detection, symlink) rather than the preflight itself."""
    stub = tmp / "stubbin"
    stub.mkdir()
    for cmd in ("git", "docker", "node", "devcontainer", "gh"):
        p = stub / cmd
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    return f"{stub}:{os.environ.get('PATH', '')}"


# ── code-check.py --json tests ─────────────────────────────────────────────────

CODE_CHECK = REPO / "code-check.py"


def _make_bad_script(path: Path, varname: str = "unused_var") -> None:
    """Write a shell script with a shellcheck warning (unused variable)."""
    path.write_text(f'#!/bin/bash\n{varname}=value\necho "hello"\n')
    path.chmod(0o755)


def _make_good_script(path: Path) -> None:
    """Write a minimal shell script with no shellcheck warnings."""
    path.write_text('#!/bin/bash\necho "hello"\n')
    path.chmod(0o755)


def _patched_code_check(tmp: Path, target_paths: list[Path]) -> tuple[Path, dict[str, str]]:
    """Point code-check.py's scripts() env seam at exactly target_paths.

    Returns (CODE_CHECK, env) — callers invoke the REAL code-check.py with
    `run(["python3", str(target), "--json"], env=env, cwd=REPO)`. This
    drives scripts() via the CODE_CHECK_SCRIPTS env seam (os.pathsep-
    separated, exact list, no globbing, no .exists() filter) rather than
    source-text-replacing scripts()'s body, so future edits to scripts()
    can never silently no-op this fixture again.

    The override is subprocess-scoped only: it is built into a fresh copy
    of os.environ and returned for the caller to pass via run(env=...). It
    never touches this process's own os.environ, so it cannot leak into
    later tests in main()'s fixed sequence (`tmp` is accepted for call-site
    compatibility but unused now — no temp file is written).
    """
    del tmp  # no longer needed: no patched copy is written to disk
    env = os.environ.copy()
    env["CODE_CHECK_SCRIPTS"] = os.pathsep.join(str(p) for p in target_paths)
    return CODE_CHECK, env


# ── task_025: git-hooks shellcheck coverage + CODE_CHECK_SCRIPTS env seam ──────


def _load_code_check_module():
    """Import code-check.py as a module (its filename isn't a valid Python
    module name, hence importlib.util.spec_from_file_location) so
    is_shell_script can be called directly for AC2. Safe: the module's only
    top-level side effect is defining names — main() runs solely under
    `if __name__ == "__main__":`, which is false for an imported module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("code_check_module", CODE_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patched_code_check_has_scripts_source_replace() -> bool:
    """True iff _patched_code_check's source contains a `.replace(` call
    whose argument text includes the substring `def scripts()`
    (AST-proven) — the regression guard AC7 targets: the PATTERN (a
    .replace keyed on scripts()'s source), not one literal string."""
    import ast
    import inspect

    src = inspect.getsource(_patched_code_check)
    tree = ast.parse(src)
    target = "def scripts()"
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "replace"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if target in arg.value:
                        return True
    return False


# ── vibe --continue / --resume flag tests ──────────────────────────────────────


def _source_vibe_call(env_vars: dict[str, str], call: str) -> subprocess.CompletedProcess:
    """Source vibe with VIBE_SOURCE_ONLY=1, set env, run a single call. Returns CompletedProcess."""
    env = {
        **os.environ,
        "VIBE_CONFIG": "/tmp/vibe-no-config-for-tests",
        "VIBE_SOURCE_ONLY": "1",
        **env_vars,
    }
    script = f"set -e; source {shlex.quote(str(VIBE))}; {call}"
    return run(["bash", "-c", script], env=env)


# parse_vibe_args: flags-and-positional-in-any-order parser. The bug it fixes:
# pre-2026-04-29 the parser was a leading-only `while [[ "${1:-}" == --* ]]`
# loop, so `vibe vibe --continue` silently dropped --continue (project name as
# $1 ended the loop before --continue at $2 was ever read). New parser accepts
# flags and the positional in any order so `vibe vibe --continue` and
# `vibe --continue vibe` are equivalent.

def _parse_args_probe(argv: list[str]) -> subprocess.CompletedProcess:
    """Source vibe, call parse_vibe_args, echo resulting globals."""
    quoted = " ".join(shlex.quote(a) for a in argv)
    call = (
        f'parse_vibe_args {quoted}; '
        'echo "REBUILD=[$REBUILD]"; '
        'echo "CONTINUE=[$CONTINUE]"; '
        'echo "RESUME=[$RESUME]"; '
        'echo "RESUME_UID=[$RESUME_UID]"; '
        'echo "PROJECT_ARG=[$PROJECT_ARG]"; '
        'echo "MODEL_ARG=[$MODEL_ARG]"'
    )
    return _source_vibe_call({}, call)


# ── Image drift detection tests (task_015 AC1-AC6, AC8) ─────────────────────────

def _image_drift_call_with_docker_stub(
    workspace: str,
    image_tag: str,
    ps_output: str,
    ps_rc: int,
    cref_output: str,
    cref_rc: int,
    tag_id_output: str,
    tag_id_rc: int,
    ref_id_output: str,
    ref_id_rc: int,
) -> subprocess.CompletedProcess:
    """
    Source vibe with a stubbed docker() function and call image_drift_needs_recreate.
    Returns CompletedProcess with the function's output/exit code.
    """
    env = {
        **os.environ,
        "VIBE_CONFIG": "/tmp/vibe-no-config-for-tests",
        "VIBE_SOURCE_ONLY": "1",
    }
    # Bash script that defines a docker() stub shadowing PATH, then calls the helper.
    # The stub branches on $1 (ps/inspect/image) and distinguishes the two
    # docker image inspect calls by the target argument (${@: -1}).
    script = f"""
set -euo pipefail
source {shlex.quote(str(VIBE))}

docker() {{
  case "$1" in
    ps)
      printf '%s\\n' {shlex.quote(ps_output)}
      return {ps_rc}
      ;;
    inspect)
      # docker inspect --format '{{{{.Image}}}}' <cid>
      printf '%s\\n' {shlex.quote(cref_output)}
      return {cref_rc}
      ;;
    image)
      # docker image inspect --format '{{{{.Id}}}}' <target>
      # Distinguish by the target argument (last arg)
      case "${{@: -1}}" in
        {shlex.quote(image_tag)})
          printf '%s\\n' {shlex.quote(tag_id_output)}
          return {tag_id_rc}
          ;;
        *)
          # container ref target
          printf '%s\\n' {shlex.quote(ref_id_output)}
          return {ref_id_rc}
          ;;
      esac
      ;;
  esac
}}

image_drift_needs_recreate {shlex.quote(workspace)} {shlex.quote(image_tag)}
"""
    return run(["bash", "-c", script], env=env)


def _learning_optin_config(home: Path, lib: Path, visibility: str = "private") -> None:
    cfg = home / ".vibe" / "learning.config"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        f'VIBE_LEARNING_ENABLED="true"\n'
        f'VIBE_LEARNING_PATH="{lib}"\n'
        f'VIBE_LEARNING_VISIBILITY="{visibility}"\n'
        f'VIBE_LEARNING_GIT_REMOTE=""\n'
    )


# ── task_009: /learnings write-confirm hook ───────────────────────────────────

GUARD_FS = REPO / "devcontainer" / "guard-fs.sh"
GUARD_BASH = REPO / "devcontainer" / "guard-bash.sh"
LEARN_MD = REPO / "devcontainer" / "commands" / "learn.md"
# task_028 merged the standalone hook fragment into learnings.md.
LEARN_HOOK_RULES_MD = REPO / "devcontainer" / "claude-md" / "learnings.md"

# Pre-check: jq and bash available on host (needed for hook script tests).
_HAS_JQ = subprocess.run(["which", "jq"], capture_output=True).returncode == 0
_HAS_BASH = subprocess.run(["which", "bash"], capture_output=True).returncode == 0
_HOOK_SKIP = not (_HAS_JQ and _HAS_BASH)

if _HOOK_SKIP:
    print("WARNING: jq or bash not found — hook-fixture tests will be skipped", file=sys.stderr)


def _run_guard_fs(json_input: str) -> "subprocess.CompletedProcess[str]":
    """Feed json_input to guard-fs.sh and return the result."""
    return subprocess.run(
        ["bash", str(GUARD_FS)],
        input=json_input,
        capture_output=True,
        text=True,
    )


def _run_guard_bash(cmd_str: str) -> "subprocess.CompletedProcess[str]":
    """Feed a Bash tool JSON envelope to guard-bash.sh and return the result."""
    payload = json.dumps({"tool_input": {"command": cmd_str}})
    return subprocess.run(
        ["bash", str(GUARD_BASH)],
        input=payload,
        capture_output=True,
        text=True,
    )


def _assert_ask_json(r: "subprocess.CompletedProcess[str]", label: str) -> None:
    """Assert the subprocess output is a valid ask-JSON envelope."""
    check(f"[task009] {label}: exit 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    try:
        data = json.loads(r.stdout)
        ok = True
    except json.JSONDecodeError as exc:
        check(f"[task009] {label}: stdout is valid JSON", False, str(exc))
        return
    check(f"[task009] {label}: stdout is valid JSON", ok)
    hso = data.get("hookSpecificOutput", {})
    check(f"[task009] {label}: hookEventName == PreToolUse",
          hso.get("hookEventName") == "PreToolUse", str(hso))
    check(f"[task009] {label}: permissionDecision == ask",
          hso.get("permissionDecision") == "ask", str(hso))
    reason = hso.get("permissionDecisionReason", "")
    check(f"[task009] {label}: permissionDecisionReason non-empty",
          bool(reason), str(hso))


def _assert_silent_exit0(r: "subprocess.CompletedProcess[str]", label: str) -> None:
    """Assert the subprocess emitted nothing to stdout and exited 0."""
    check(f"[task009] {label}: exit 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    check(f"[task009] {label}: empty stdout", r.stdout == "",
          f"stdout={r.stdout[:200]}")


def _assert_deny_json(r: "subprocess.CompletedProcess[str]", label: str) -> None:
    """Assert the subprocess output is a valid deny-JSON envelope."""
    check(f"[zotero] {label}: exit 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        check(f"[zotero] {label}: stdout is valid JSON", False, str(exc))
        return
    check(f"[zotero] {label}: stdout is valid JSON", True)
    hso = data.get("hookSpecificOutput", {})
    check(f"[zotero] {label}: hookEventName == PreToolUse",
          hso.get("hookEventName") == "PreToolUse", str(hso))
    check(f"[zotero] {label}: permissionDecision == deny",
          hso.get("permissionDecision") == "deny", str(hso))
    check(f"[zotero] {label}: reason non-empty",
          bool(hso.get("permissionDecisionReason", "")), str(hso))


def _guard_fs_variant(tmpdir: str, mount_path: str) -> str:
    """Copy guard-fs.sh with the /zotero mount path rewritten to mount_path.

    The deny branch is gated on `[ -d /zotero ]`, which is false on a host
    with no Zotero mount (i.e. every machine smoke-test.py runs on). Rewriting
    the literal lets both the mount-present and mount-absent cases be exercised
    deterministically, on any host.
    """
    src = GUARD_FS.read_text().replace("/zotero", mount_path)
    dst = os.path.join(tmpdir, "guard-fs-variant.sh")
    Path(dst).write_text(src)
    return dst


def _run_guard_fs_variant(script: str, path: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        ["bash", script],
        input=json.dumps({"tool_input": {"file_path": path}}),
        capture_output=True, text=True,
    )


# test_task013_diff_scope retired 2026-05-07 (/vsss session) — was an over-
# scoped freeze guard anchored to live working tree's .vs/cycle-1/diff.patch
# with task_013's specific allowlist {vs.md, smoke-test.py, TODO.md}
# hard-coded. The next /vs cycle that wrote a diff.patch (task_010 cycle 1)
# tripped it on legitimate files. This is exactly the pattern memory
# feedback_vs_tester_no_file_freeze_guards documents: hardening tests
# Tester adds for AC scope must be cycle-anchored (HEAD~1 HEAD on the
# cycle's commit) or PR-level CI, not live-working-tree freezes that
# block unrelated future tasks. test_task008_ac15_no_scope_drift was
# retired for the same reason 2026-04-26.


# ── check-sp-current.sh upstream drift probe tests ─────────────────────────────


SP_CORE_SKILLS = sorted([
    "using-superpowers",
    "brainstorming",
    "writing-plans",
    "executing-plans",
    "subagent-driven-development",
    "dispatching-parallel-agents",
    "test-driven-development",
    "systematic-debugging",
    "requesting-code-review",
    "receiving-code-review",
    "verification-before-completion",
    "finishing-a-development-branch",
    "using-git-worktrees",
    "writing-skills",
])


def _run_sp_probe(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(CHECK_SP_CURRENT), *args],
        capture_output=True, text=True,
    )


# ── ~/.vibe/skipped persistence tests ──────────────────────────────────────────


def _run_skipped_probe(workspace: str, marker_state: list[str], home: Path) -> tuple[int, str, list[str]]:
    """Source vibe with VIBE_SOURCE_ONLY=1 and HOME=<temp>, set WORKSPACE,
    optionally pre-seed $HOME/.vibe/skipped from marker_state, then call
    is_github_skipped and report the boolean result + post-run file content."""
    skipped_path = home / ".vibe" / "skipped"
    skipped_path.parent.mkdir(parents=True, exist_ok=True)
    if marker_state:
        skipped_path.write_text("\n".join(marker_state) + "\n")
    elif skipped_path.exists():
        skipped_path.unlink()
    env = {
        **os.environ,
        "HOME": str(home),
        "VIBE_CONFIG": "/dev/null",
        "VIBE_SOURCE_ONLY": "1",
        "WORKSPACE": workspace,
    }
    script = (
        f"source {shlex.quote(str(VIBE))}; "
        'if is_github_skipped; then echo "SKIPPED=true"; '
        'else echo "SKIPPED=false"; fi'
    )
    r = subprocess.run(["bash", "-c", script], env=env,
                       capture_output=True, text=True)
    content = skipped_path.read_text().splitlines() if skipped_path.exists() else []
    return r.returncode, r.stdout, content


# ── check-numbering.sh Stop hook tests ─────────────────────────────────────────

CHECK_NUMBERING = REPO / "devcontainer" / "hooks" / "check-numbering.sh"
COPY_LAST_BLOCK = REPO / "devcontainer" / "hooks" / "copy-last-block.sh"
NUMBERING_HOOK_README = REPO / "devcontainer" / "hooks" / "README.md"


def _run_numbering_hook(transcript_jsonl: str) -> tuple[int, str]:
    """Write transcript_jsonl to a temp file, invoke the hook with a fake
    Stop-hook payload pointing at it, return (exit_code, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp) / "t.jsonl"
        tpath.write_text(transcript_jsonl)
        payload = json.dumps({"transcript_path": str(tpath)})
        r = subprocess.run(
            ["bash", str(CHECK_NUMBERING)],
            input=payload, capture_output=True, text=True,
        )
        return r.returncode, r.stderr


def _run_copy_last_block(text: str, clip_dir: Path) -> tuple[int, str]:
    """Synthesise a transcript with one assistant message of `text`,
    invoke copy-last-block.sh with VIBE_CLIP_DIR=clip_dir, return
    (exit_code, copy-latest.txt content or '<NO_FILE>')."""
    transcript = clip_dir.parent / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": text}]}}) + "\n"
    )
    clip_file = clip_dir / "copy-latest.txt"
    if clip_file.exists():
        clip_file.unlink()
    payload = json.dumps({"transcript_path": str(transcript)})
    env = {**os.environ, "VIBE_CLIP_DIR": str(clip_dir)}
    r = subprocess.run(
        ["bash", str(COPY_LAST_BLOCK)],
        input=payload, capture_output=True, text=True, env=env,
    )
    actual = clip_file.read_text() if clip_file.exists() else "<NO_FILE>"
    return r.returncode, actual


def _ssh_marker_result(env_vars: dict, setup: str) -> tuple[str, str]:
    """Run install-claude-extras.sh against a temp workspace built by
    `setup` (bash with WS=workspace path). Returns (IN|OUT, stderr):
    IN = ssh-discipline.md omitted (opt-in honoured), OUT = fragment kept."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ws = tmp_path / "ws"
        ws.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["bash", "-c", f'WS="{ws}"; {setup}'],
                       capture_output=True, text=True)
        env = os.environ.copy()
        env.pop("VIBE_SSH_AUTO", None)
        env["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")
        env["CLAUDE_CONFIG_DIR"] = str(dest)
        env["VIBE_SSH_MARKER_WS"] = str(ws)
        env["VIBE_SMOKE"] = "1"  # gates the marker-ws override
        # Keep the real environment untouched: the installer writes global
        # git config (core.hooksPath at a throwaway path!) and would add the
        # managed gitignore block to the real /workspace.
        env["HOME"] = str(tmp_path)
        env["GIT_CONFIG_GLOBAL"] = str(tmp_path / "gitconfig")
        env["VIBE_AUTO_GITIGNORE"] = "0"
        env.update(env_vars)
        r = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                           env=_isolate_extras_env(env), capture_output=True, text=True)
        if r.returncode != 0:
            return (f"ERR(rc={r.returncode})", r.stderr)
        md = (dest / "CLAUDE.md").read_text()
        state = "IN" if "<!-- vibe-md: ssh-discipline.md -->" not in md else "OUT"
        return (state, r.stderr)


def _review_due_result(setup: str) -> str:
    """Source vibe, build a fixture library via `setup` (bash, LIB=path),
    run learning_review_due "$LIB", echo DUE/NOT. Returns 'DUE'/'NOT'."""
    call = (
        'LIB=$(mktemp -d); ' + setup +
        '; if learning_review_due "$LIB"; then echo RESULT=DUE; else echo RESULT=NOT; fi; '
        'rm -rf "$LIB"'
    )
    r = _source_vibe_call({}, call)
    if "RESULT=DUE" in r.stdout:
        return "DUE"
    if "RESULT=NOT" in r.stdout:
        return "NOT"
    return f"ERR({r.stdout}{r.stderr})"


def _read_override_out(r: subprocess.CompletedProcess) -> str:
    m = re.search(r"OUT=\[(.*)\]", r.stdout)
    return m.group(1) if m else ""


# ── task_017 Cycle 1 — sonnet Tester delta ──────────────────────────────────
# Coverage the haiku Tester wrongly skipped as "not unit-testable": the
# shared_repos_scan M/B/N/U state machine, the ack helpers' exact-pair
# semantics, the fixed-string lookup discipline (security-review regression),
# the two-bind override JSON shape, and shared_repos_manifest_lines. All of
# these ARE testable via the same VIBE_SOURCE_ONLY sourcing pattern used
# above, with temp HOME/workspace/checkout fixtures. Header rendering (AC4)
# is inline in the launcher's main body (after the VIBE_SOURCE_ONLY guard),
# so it's covered at the text level here plus behaviourally via the scan
# fixtures below (one code path feeds both).


def _repos_delta_fixture(td: Path):
    """Build a temp HOME + workspace + checkout triple for shared-repos scan
    tests. Returns (home, ws, checkout). Caller populates
    ws/.vibe-repos, home/.vibe/repos, home/.vibe/tokens, home/.vibe/repos-acks
    as each scenario needs."""
    home = td / "home"; home.mkdir()
    (home / ".vibe").mkdir(parents=True)
    ws = td / "ws"; ws.mkdir()
    checkout = td / "checkout"; checkout.mkdir()
    (checkout / ".git").mkdir()
    return home, ws, checkout


def _extract_statusline() -> tuple[dict, str]:
    """Re-extract the settings.local.json heredoc's statusLine command using
    the same technique as the frozen test_vibe_statusline. Returns
    (parsed_config, command_string); (empty dict, "") if the heredoc marker
    is missing (caller must check and report)."""
    vibe_src = VIBE.read_text()
    start_marker = 'cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\''
    start_idx = vibe_src.find(start_marker)
    if start_idx == -1:
        return {}, ""
    start_idx = vibe_src.find("\n", start_idx) + 1
    end_idx = vibe_src.find("\nEOF", start_idx)
    config = json.loads(vibe_src[start_idx:end_idx])
    return config, config.get("statusLine", {}).get("command", "")


def _statusline_command() -> str:
    """Extract just the statusLine command string (rate-limit tests)."""
    _, cmd = _extract_statusline()
    return cmd


def _write_signals_fixture(sig_root: Path, name: str, holder_project: str | None,
                            requester_project: str | None) -> None:
    """Build <sig_root>/<name>/rw-lock.d/meta (holder_project, if given) and
    <sig_root>/<name>/rw-request (requester_project, if given), matching the
    Pinned-names KEY=VALUE shapes the statusLine command parses."""
    d = sig_root / name
    if holder_project is not None:
        lock = d / "rw-lock.d"
        lock.mkdir(parents=True, exist_ok=True)
        (lock / "meta").write_text(
            f"project={holder_project}\npid=99999\nsince=1000000\n", encoding="utf-8")
    else:
        d.mkdir(parents=True, exist_ok=True)
    if requester_project is not None:
        (d / "rw-request").write_text(
            f"project={requester_project}\nsince=1000100\n", encoding="utf-8")


# ── task_017 Cycle 4 (haiku Tester): credential helper, useHttpPath, token ──
# plumbing, invariant text. Independent read of .vs/spec.md end-to-end;
# no generator reports consulted. AC16's helper is a pure stdin->stdout
# filter — driven directly here, never through the launcher.

def _c4_sanitise(slug: str) -> str:
    """Python twin of credential-helper.sh's _sanitise_slug / vibe's
    shared_repo_env_name: uppercase, then every non [A-Z0-9] byte -> '_'."""
    return re.sub(r"[^A-Z0-9]", "_", slug.upper())


def _c4_cred_stdin(protocol: str | None = "https", host: str | None = "github.com",
                    path: str | None = None, raw_path: str | None = None) -> str:
    """Build a git-credential-protocol stdin blob. raw_path, if given, is
    spliced in verbatim (post encoding) instead of a plain path= line, for
    control-character/injection fixtures that can't round-trip through a
    plain python str formatted the normal way."""
    lines = []
    if protocol is not None:
        lines.append(f"protocol={protocol}")
    if host is not None:
        lines.append(f"host={host}")
    if raw_path is not None:
        lines.append(raw_path)
    elif path is not None:
        lines.append(f"path={path}")
    return "\n".join(lines) + "\n\n"


def _c4_run_cred_helper(env_overrides: dict[str, str], stdin_text: str,
                         op: str = "get") -> subprocess.CompletedProcess:
    """Run credential-helper.sh directly (it's a standalone executable filter,
    not a vibe-sourced function) against a MINIMAL env (PATH only) plus the
    given overrides, so no ambient GITHUB_TOKEN/VIBE_SHARED_TOKEN_* in the
    test runner's own environment can contaminate a security assertion."""
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(env_overrides)
    return run(["bash", str(CREDENTIAL_HELPER), op], env=env, input=stdin_text)


def _c4_assert_silent(check_name: str, r: subprocess.CompletedProcess) -> None:
    check(f"{check_name}: exits 0", r.returncode == 0, r.stderr)
    check(f"{check_name}: emits NOTHING on stdout", r.stdout == "", repr(r.stdout))


def _c4_assert_served(check_name: str, r: subprocess.CompletedProcess, token: str) -> None:
    check(f"{check_name}: exits 0", r.returncode == 0, r.stderr)
    check(f"{check_name}: serves username=x-access-token",
          "username=x-access-token" in r.stdout, r.stdout)
    check(f"{check_name}: serves password={token}",
          f"password={token}" in r.stdout, r.stdout)


# ── task_020: per-project OpenProject MCP opt-in gate ──────────────────────────
def _op_opted_in_result(env_vars: dict, setup: str) -> str:
    """Source vibe, build a temp workspace via `setup` (bash setting WS=path),
    run _op_opted_in "$WS", echo IN/OUT. Returns 'IN' or 'OUT'."""
    call = (
        'WS=$(mktemp -d); ' + setup +
        '; if _op_opted_in "$WS"; then echo RESULT=IN; else echo RESULT=OUT; fi; '
        'rm -rf "$WS"'
    )
    r = _source_vibe_call(env_vars, call)
    if "RESULT=IN" in r.stdout:
        return "IN"
    if "RESULT=OUT" in r.stdout:
        return "OUT"
    return f"ERR({r.stdout}{r.stderr})"


# ── task_022: scanner match-primitive swap + --messages-stdin + audit perf ──
# Tester-authored (independent of the Generator's cycle-1 diff/report — spec
# only). Permanent suite members per .vs/spec.md "Test location": the AC2
# corpus re-expressed as fixed expected-findings assertions, the AC3/AC5
# fixture-repo tests, and the AC7 static shape checks. AC1 (real-history
# slice differential) and AC4 (60s timing gate) are one-offs and live in the
# Tester's log, not here — a permanent test must not depend on the vibe
# repo's own mutable history.

TASK022_CLEAN_LINES = [
    "Just a normal line of code here",
    "def hello(): pass",
    "This has numbers 12345 but nothing sensitive at all",
    "# a comment explaining the algorithm in plain English",
    "x = 1 + 2  # simple arithmetic",
]

# (line, [(class, rule), ...]) — every rule id, mdns boundary cases, email
# exemptions, both trailer exemption shapes, and the nocasematch-leak probe
# (mixed-case secret-assignment trigger + uppercase FOO.LOCAL on one line —
# the case-sensitive mdns-local rule must NOT fire, which it would iff
# nocasematch leaked out of check_rule's icase branch). Clean lines are
# appended so the corpus also proves A2b (set -e survival: a bare unguarded
# `[[ =~ ]]` would die on the first clean line — clean lines are scattered
# through this file, not only trailing).
TASK022_CORPUS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Just a normal line of code here", []),
    ("GitHub PAT sample ghp_" + "A" * 36 + " end", [("BLOCK", "github-pat")]),
    ("def hello(): pass", []),
    ("OpenAI API sample sk-ABCDEFGHIJKLMNOPQRSTUVWX end", [("BLOCK", "openai-key")]),
    ("AWS access sample AKIAABCD1234EFGH5678 end", [("BLOCK", "aws-access-key")]),
    ("-----BEGIN OPENSSH PRIVATE KEY-----", [("BLOCK", "private-key")]),
    ("This has numbers 12345 but nothing sensitive at all", []),
    ("Config token: ABCDEFGHIJKLMNOPQRSTUVWX1234", [("BLOCK", "secret-assignment")]),
    # nocasematch-leak probe (AC2): secret-assignment fires (icase); mdns-local
    # (case-sensitive) must NOT fire on the uppercase FOO.LOCAL in the same line.
    ("MyPaSsWoRd: abcdefghijklmnopqrstuvwxyz1234 seen near FOO.LOCAL host",
     [("BLOCK", "secret-assignment")]),
    ("# a comment explaining the algorithm in plain English", []),
    ("Server ip 10.0.0.5 today", [("WARN", "rfc1918-ip")]),
    ("Server ip 172.20.5.9 today", [("WARN", "rfc1918-ip")]),
    ("Server ip 192.168.50.7 today", [("WARN", "rfc1918-ip")]),
    ("Server ip 169.254.1.2 today", [("WARN", "rfc1918-ip")]),
    ("Path is /Users/martin/project file", [("WARN", "home-path")]),
    ("Path is /home/alice/project file", [("WARN", "home-path")]),
    ("Path is /home/node/project file", []),  # node excluded
    ("Path is /Users/root/project file", []),  # root excluded
    ("x = 1 + 2  # simple arithmetic", []),
    ("Host foo.local is up", [("WARN", "mdns-local")]),
    ("Host foo.localhost is up", []),  # word char after .local: must NOT match
    ("Host foo.local. end", [("WARN", "mdns-local")]),  # trailing non-word char
    ("Host at foo.local", [("WARN", "mdns-local")]),  # end-of-line boundary
    ("Contact me at test@example.com please", [("WARN", "email-address")]),
    ("noreply@anthropic.com", []),  # built-in noreply exemption
    ("backup contact x@y.users.noreply.github.com here", []),  # github noreply exemption
    # Named-trailer full exemption (Co-authored-by/Signed-off-by): suppresses
    # EVERY rule on the line, including a non-exempt email + an RFC1918 IP.
    ("Co-authored-by: Real Name <someone@example.com> 192.168.9.9", []),
    ("Signed-off-by: Someone <bob@example.org> 10.1.2.3", []),
    # Generic trailer-shaped line (not a named trailer): suppresses email/ip
    # ONLY (built-in allowlist (b)) — no BLOCK-tier trigger here, so clean.
    ("Reviewed-by: bob@example.org 192.168.4.4", []),
    # Same generic trailer shape, but with a BLOCK-tier trigger: proves the
    # generic-trailer suppression does NOT extend to BLOCK findings, unlike
    # the named-trailer full exemption above.
    ("Reviewed-by: token=ABCDEFGHIJKLMNOPQRSTUVWX1234", [("BLOCK", "secret-assignment")]),
] + [(l, []) for l in TASK022_CLEAN_LINES]

TASK022_EXPECTED_ALL: dict = {}
for _line, _exp in TASK022_CORPUS:
    for _c, _r in _exp:
        TASK022_EXPECTED_ALL[(_c, _r)] = TASK022_EXPECTED_ALL.get((_c, _r), 0) + 1
TASK022_EXPECTED_BLOCK_ONLY = {k: v for k, v in TASK022_EXPECTED_ALL.items() if k[0] == "BLOCK"}


def _task022_parse_findings(stderr: str) -> list[tuple[str, str, str, str]]:
    """Parse tab-separated <CLASS>\\t<location>\\t<rule>\\t<snippet> finding
    lines out of scanner stderr, ignoring any non-finding lines (e.g. the
    OVERRIDE banner)."""
    out = []
    for line in stderr.splitlines():
        parts = line.split("\t")
        if len(parts) == 4 and parts[0] in ("BLOCK", "WARN"):
            out.append((parts[0], parts[1], parts[2], parts[3]))
    return out


def _task022_counts(findings: list[tuple[str, str, str, str]]) -> dict:
    counts: dict = {}
    for f in findings:
        key = (f[0], f[2])
        counts[key] = counts.get(key, 0) + 1
    return counts


def _task022_extract_function_body(src: str, name: str) -> str:
    """AC7-pinned extraction: the text from the line matching '^name() {' to
    the first subsequent line matching '^}'."""
    lines = src.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line == f"{name}() {{":
            start = i
            break
    if start is None:
        raise AssertionError(f"function {name}() {{ not found in scanner source")
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j] == "}":
            end = j
            break
    if end is None:
        raise AssertionError(f"no closing }} found for {name}")
    return "\n".join(lines[start:end + 1])


# ── task_023: path-warn:<glob> allowlist entries — per-file WARN-tier
# demotion in --staged/--range so vibe's own repo is self-clean under its
# own content guard ──────────────────────────────────────────────────────
# Tester-authored (independent of the Generator's cycle-1 diff/report —
# spec only). Permanent suite members per .vs/spec.md "Test location": AC1
# parser + ERE-regression, AC2 (all 4 WARN categories, 3-level nested path,
# empty-glob skip), AC3 (BLOCK under path-warn, staged + range), AC3b (no
# ERE double-parse, both literal shapes), AC3c (--range idempotency), AC4
# (non-diff-mode byte-parity with path-warn present), AC5 (self-clean
# end-to-end fixture simulation), AC7 (path-warn-specific no-fork shape
# guards), plus path-warn:* accepted and glob-metacharacter sanity. The
# differential against the OLD (pre-task_023) scanner and the audit
# --history timing gate are one-offs and live in the Tester's log only, not
# here — a permanent test must not depend on the vibe repo's own mutable
# history. WARN/BLOCK-shaped literals below are assembled at runtime
# (string concatenation / join), never embedded as raw dotted-quad IPs,
# emails, .local hostnames, or ghp_/AKIA-shaped tokens — so this file's own
# fixtures never masquerade as real findings independent of the feature
# under test, regardless of this repo's own path-warn:smoke-test.py entry.

def _t23_ip() -> str:
    return ".".join(["192", "168", "50", "7"])


def _t23_ip_alt() -> str:
    return ".".join(["10", "1", "2", "3"])


def _t23_email() -> str:
    return "warnuser" + "@" + "example" + "." + "com"


def _t23_mdns() -> str:
    return "buildhost" + ".local"


def _t23_homepath_line() -> str:
    return "Path is /" + "Users" + "/" + "alice" + "/project file"


def _t23_ghp() -> str:
    return "ghp_" + "B" * 36


def _t23_init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=repo)
    # Fixture repo: neutralise the machine-global content-guard hooks at
    # local scope so fixture commits (some deliberately carry secrets/PII)
    # are deterministic; hook-exercising tests re-pin their own hooksPath.
    run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
    run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    run(["git", "config", "user.name", "Test User"], cwd=repo)


# ── task_024: hunk-aware diff parsing — close the added-line header-spoof
# hole in scan_diff_stream (--staged/--range) and scan_blob_stdin
# (--blob-stdin) ─────────────────────────────────────────────────────────
# Tester-authored (independent of the Generator's cycle-1 diff/report —
# spec only), verified against the live scanner with real git before being
# written down here (not guessed). Permanent suite members per .vs/spec.md
# "Test location": AC1 (skip-state spoof neutralised, staged+range), AC2
# (tier/file-flip spoof neutralised), AC3 (spoofed content itself scanned,
# staged+blob-stdin, plus the forged-budget probe), AC3b (the
# diff.suppressBlankEmpty zero-byte context-line exploit), AC4 (deleted-
# line/added-line two-line dance bounded), AC5 (real-header corpus frozen —
# multi-file/new/deleted/multi-hunk/-U0 zero-count/no-newline/binary/mode-
# change, exact findings pinned), AC7 (U3 context decrements both, only `+`
# scanned), AC8 (malformed `@@` fail-safe, no crash/no wedge), AC10 (TODO/
# CHANGELOG bookkeeping). The spoof-free differential (AC5) and the
# full-history objective-oracle differential (AC6) are one-offs and live in
# the Tester's log only, not here — a permanent test must not depend on the
# vibe repo's own mutable history. All BLOCK/WARN-shaped literals below are
# assembled at runtime (string concatenation), never embedded raw.

def _t24_ghp(c: str = "M") -> str:
    return "ghp_" + c * 36


def _t24_akia(c: str = "Q") -> str:
    return "AKIA" + c * 16


def _t24_ip(parts: tuple = ("192", "168", "44", "5")) -> str:
    return ".".join(parts)


def _t24_init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=repo)
    # Fixture repo: neutralise the machine-global content-guard hooks at
    # local scope so fixture commits (some deliberately carry secrets/PII)
    # are deterministic; hook-exercising tests re-pin their own hooksPath.
    run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
    run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    run(["git", "config", "user.name", "Test User"], cwd=repo)


# ── task_026: `vibe pat [repo]` PAT rotation + launch-time 401 reprompt ─────────

def _setup_curl_shim(tmp: Path, response_code: str = "200", response_stdin: str = "", exit_code: int = 0) -> tuple[str, Path, Path]:
    """Create a PATH-shimmable curl stub that logs argv and stdin. Returns (new_PATH, argv_log, stdin_log)."""
    stub_dir = tmp / "stubbin"
    stub_dir.mkdir()
    curl_stub = stub_dir / "curl"
    argv_log = tmp / "curl-argv.log"
    stdin_log = tmp / "curl-stdin.log"

    # Shim that logs all argv and stdin, then outputs response_code.
    # NOTE: no `shift` here — when a script runs via its shebang, "$@" already
    # holds exactly the arguments the caller passed to it (curl's own argv0
    # is NOT among them), so a leading `shift` silently drops the shim's
    # first real argument (curl's `-s` in this project's invocation). A
    # prior version of this shim shifted regardless, which happened not to
    # break AC6's assertions (they don't check for `-s`) but was still wrong
    # and would have masked a regression in exactly that position.
    curl_stub.write_text(f"""#!/bin/bash
echo "$@" >> {shlex.quote(str(argv_log))}

# Log stdin
cat >> {shlex.quote(str(stdin_log))}

# Output the response code to stdout (for curl's -w)
echo -n "{response_code}"

# Exit with the specified code
exit {exit_code}
""")
    curl_stub.chmod(0o755)
    new_path = f"{stub_dir}:{os.environ.get('PATH', '')}"
    return new_path, argv_log, stdin_log


# ── task_028: init-firewall self-heal (GitHub meta retry + policy reset) ──────
#
# Triggered live 2026-07-29: a container sat unreachable ("Unable to connect to
# API (ConnectionRefused)") across repeated reboots. Two compounding defects:
#   1. `curl https://api.github.com/meta` had no retry, so one transient blip
#      hit the fail_closed trap and locked the container down for good --
#      `vibe` reuses a running container without re-running postStartCommand.
#   2. `iptables -F` flushes rules but NOT default policies, so the DROP left
#      by that failure blocked the very fetch the next run needed. Re-running
#      init-firewall.sh in place could only ever re-fail.
# These tests are host-side: no Docker, no iptables, no network.


def _fw_stub_curl(tmp: Path, *, script_body: str) -> str:
    """A bin dir whose `curl` is a scripted stub, prepended to PATH.

    The stub appends one line to $STUB_LOG per invocation so tests can assert
    on the exact attempt count (a retry loop that never stops early is as much
    a bug as one that never retries).
    """
    stub = tmp / "fwbin"
    stub.mkdir(exist_ok=True)
    p = stub / "curl"
    p.write_text("#!/bin/bash\n"
                 'echo "call" >> "$STUB_LOG"\n'
                 f"n=$(wc -l < \"$STUB_LOG\" | tr -d ' ')\n"
                 f"{script_body}\n")
    p.chmod(0o755)
    return f"{stub}:{os.environ.get('PATH', '')}"


def _fw_run(tmp: Path, stub_body: str, snippet: str):
    """Source init-firewall.sh with the helpers exposed but no side effects,
    against a stubbed curl, then run `snippet`."""
    log = tmp / "curl.log"
    log.write_text("")
    env = {
        **os.environ,
        "PATH": _fw_stub_curl(tmp, script_body=stub_body),
        "STUB_LOG": str(log),
        "VIBE_FIREWALL_SOURCE_ONLY": "1",
        "GH_FETCH_BACKOFF": "0",
        # Pin the attempt cap so these tests exercise the retry MECHANISM,
        # not the shipped default (which task_029 raised and asserts
        # separately in AC11).
        "GH_FETCH_ATTEMPTS": "3",
        # Never let a stubbed fetch write the LIVE ~/.claude/gh-meta-cache.json
        # (a fixture cache served on a real boot would allowlist 1.2.3.0/24
        # instead of GitHub) and never let a live cache rescue a test that
        # expects fail-closed.
        "GH_META_CACHE": str(tmp / "gh-meta-cache.json"),
    }
    script = f"source {shlex.quote(str(INIT_FIREWALL))}\n{snippet}\n"
    r = run(["bash", "-c", script], env=env)
    calls = len([ln for ln in log.read_text().splitlines() if ln.strip()])
    return r, calls


_FW_GOOD_JSON = '{"web":["1.2.3.0/24"],"api":["4.5.6.0/24"],"git":["7.8.9.0/24"]}'


# ── task_014: per-project Claude projects/ bind ────────────────────────────────


def _t14_sha1(path: str) -> str:
    """Reference sha1 (hex) of a workspace path, matching printf '%s' input."""
    import hashlib
    return hashlib.sha1(path.encode()).hexdigest()


def _t14_mount_target(entry) -> str:
    """Target of a mount entry in EITHER format: object ({'target': ...}) or
    docker string ('source=...,target=...,type=...'). Never silently skips
    string entries (spec AC7)."""
    if isinstance(entry, dict):
        return entry.get("target", "")
    if isinstance(entry, str):
        for part in entry.split(","):
            if part.startswith("target="):
                return part[len("target="):]
    return ""


def _t14_env(home, extra=None) -> dict:
    """Clean-HOME env for _build_override_config runs: OP creds blanked,
    brain2/zotero off, so only the mounts under test are in play."""
    env = {"HOME": str(home),
           "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
           "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off",
           "VIBE_SHARED_ENV_NAMES": ""}
    if extra:
        env.update(extra)
    return env


def _t14_build(home, ws) -> dict:
    """Run _build_override_config for ws under a clean HOME; return the parsed
    override JSON (checks that the file renders and parses on the way)."""
    r = _source_vibe_call(
        _t14_env(home), f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
    check("[task014] _build_override_config exits 0", r.returncode == 0, r.stderr[:300])
    out = _read_override_out(r)
    check("[task014] override rendered under HOME/.vibe/run",
          out.startswith(str(Path(home) / ".vibe" / "run")), out)
    check("[task014] override file exists and is readable",
          bool(out) and Path(out).exists(), out)
    return json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}


__all__ = [
    'AUTO_MEMORY_SCOPE_MD',
    'BRAIN2_MD',
    'BUG_TEMPLATE',
    'CHANGELOG_MD',
    'CHECK_NUMBERING',
    'CHECK_SP_CURRENT',
    'CODE_CHECK',
    'CONTENT_GUARD_MD',
    'COPY_LAST_BLOCK',
    'CREDENTIAL_HELPER',
    'CYCLE_1_DIFF',
    'C_MD',
    'DOCKERFILE',
    'FAILURES',
    'FEATURE_TEMPLATE',
    'GUARD_BASH',
    'GUARD_FS',
    'INIT_FIREWALL',
    'INSTALL',
    'INSTALL_EXTRAS',
    'LEARNINGS_MD',
    'LEARN_HOOK_RULES_MD',
    'LEARN_MD',
    'NUMBERING_HOOK_README',
    'PROJECT_HYGIENE_MD',
    'PR_TEMPLATE',
    'Path',
    'REPO',
    'REPO_MD',
    'SECURITY_MD',
    'SETUP_GIT_SH',
    'SHARED_REPOS_MD',
    'SP_CORE_SKILLS',
    'SP_MD',
    'SSH_DISCIPLINE_MD',
    'TASK022_CLEAN_LINES',
    'TASK022_CORPUS',
    'TASK022_EXPECTED_ALL',
    'TASK022_EXPECTED_BLOCK_ONLY',
    'TODO_CHANGELOG_MD',
    'VERSION_FILE',
    'VIBE',
    'VIBE_CONTENT_SCANNER',
    'VIBE_COPY',
    'VIBE_COPY_WATCHER',
    'VSSS_MD',
    'VSS_MD',
    'VS_MD',
    'WEB_RESEARCH_MD',
    'WEB_VIBE_ANDEYE_MD',
    'WORKSPACE_IS_THE_REPO_MD',
    'WRITE_ENV_HINT',
    '_EXTRAS_SCRATCH_HOME',
    '_FW_GOOD_JSON',
    '_HAS_BASH',
    '_HAS_JQ',
    '_HOOK_SKIP',
    '__annotations__',
    '__doc__',
    '_assert_ask_json',
    '_assert_deny_json',
    '_assert_silent_exit0',
    '_c',
    '_c4_assert_served',
    '_c4_assert_silent',
    '_c4_cred_stdin',
    '_c4_run_cred_helper',
    '_c4_sanitise',
    '_exp',
    '_extract_statusline',
    '_fw_run',
    '_fw_stub_curl',
    '_guard_fs_variant',
    '_image_drift_call_with_docker_stub',
    '_isolate_extras_env',
    '_learning_optin_config',
    '_line',
    '_load_code_check_module',
    '_make_bad_script',
    '_make_good_script',
    '_op_opted_in_result',
    '_parse_args_probe',
    '_patched_code_check',
    '_patched_code_check_has_scripts_source_replace',
    '_r',
    '_read_override_out',
    '_repos_delta_fixture',
    '_review_due_result',
    '_run_copy_last_block',
    '_run_ensure_docker_hints_off',
    '_run_guard_bash',
    '_run_guard_fs',
    '_run_guard_fs_variant',
    '_run_numbering_hook',
    '_run_skipped_probe',
    '_run_sp_probe',
    '_setup_curl_shim',
    '_source_vibe_call',
    '_ssh_marker_result',
    '_statusline_command',
    '_stub_dep_bin',
    '_t14_build',
    '_t14_env',
    '_t14_mount_target',
    '_t14_sha1',
    '_t23_email',
    '_t23_ghp',
    '_t23_homepath_line',
    '_t23_init_repo',
    '_t23_ip',
    '_t23_ip_alt',
    '_t23_mdns',
    '_t24_akia',
    '_t24_ghp',
    '_t24_init_repo',
    '_t24_ip',
    '_task022_counts',
    '_task022_extract_function_body',
    '_task022_parse_findings',
    '_write_signals_fixture',
    'annotations',
    'base64',
    'check',
    'json',
    'os',
    're',
    'run',
    'run_bytes',
    'shlex',
    'subprocess',
    'sys',
    'tempfile',
    'DIET_MD',
    'FEAST_MD',
    'MANUAL_TESTS_MD',
    'NARROW_MD',
    'README_MD',
    'WIDE_MD',
]
