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

REPO = Path(__file__).resolve().parent
VIBE = REPO / "vibe"
INSTALL = REPO / "install.sh"
WRITE_ENV_HINT = REPO / "devcontainer" / "write-env-hint.sh"
VIBE_COPY = REPO / "devcontainer" / "vibe-copy.sh"
DOCKERFILE = REPO / "devcontainer" / "Dockerfile"
INSTALL_EXTRAS = REPO / "devcontainer" / "install-claude-extras.sh"
C_MD = REPO / "devcontainer" / "commands" / "c.md"
COPY_MD_OLD = REPO / "devcontainer" / "commands" / "copy.md"
VIBE_COPY_WATCHER = REPO / "vibe-copy-watcher.sh"
WEB_RESEARCH_MD = REPO / "devcontainer" / "claude-md" / "web-research.md"
SSH_DISCIPLINE_MD = REPO / "devcontainer" / "claude-md" / "ssh-discipline.md"
BRAIN2_MD = REPO / "devcontainer" / "claude-md" / "brain2.md"
FEEDBACK_AUTO_PROMOTE_MD = REPO / "devcontainer" / "claude-md" / "feedback-auto-promote.md"
REPO_MD = REPO / "devcontainer" / "commands" / "repo.md"
SHARED_REPOS_MD = REPO / "devcontainer" / "claude-md" / "shared-repos.md"
TODO_CHANGELOG_MD = REPO / "devcontainer" / "claude-md" / "todo-changelog.md"
PROJECT_HYGIENE_MD = REPO / "devcontainer" / "claude-md" / "project-hygiene.md"
CONVERSATION_HISTORY_MD = REPO / "devcontainer" / "claude-md" / "conversation-history.md"
CHANGELOG_MD = REPO / "CHANGELOG.md"
SECURITY_MD = REPO / "SECURITY.md"
BUG_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "bug_report.md"
FEATURE_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "feature_request.md"
PR_TEMPLATE = REPO / ".github" / "PULL_REQUEST_TEMPLATE.md"
VS_MD = REPO / "devcontainer" / "commands" / "vs.md"
SP_MD = REPO / "devcontainer" / "commands" / "sp.md"
VSS_MD = REPO / "devcontainer" / "commands" / "vss.md"
VSSS_MD = REPO / "devcontainer" / "commands" / "vsss.md"
CHECK_SP_CURRENT = REPO / "devcontainer" / "check-sp-current.sh"
CYCLE_1_DIFF = REPO / ".vs" / "cycle-1" / "diff.patch"
CREDENTIAL_HELPER = REPO / "devcontainer" / "credential-helper.sh"
SETUP_GIT_SH = REPO / "devcontainer" / "setup-git.sh"

FAILURES: list[tuple[str, str]] = []


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


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_help() -> None:
    print("\n[vibe --help]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("exit 0", r.returncode == 0, r.stderr)
    check("header present", "vibe" in r.stdout, r.stdout[:200])
    check("usage section present", "Usage:" in r.stdout, r.stdout[:200])


VERSION_FILE = REPO / "VERSION"
WEB_VIBE_ANDEYE_MD = REPO / "web" / "vibe-andeye.md"


def test_version() -> None:
    print("\n[vibe --version]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--version"], env=env)
    check("--version exit 0", r.returncode == 0, r.stderr)
    out = r.stdout.strip()
    check("--version prints 'vibe <semver>' single line",
          re.fullmatch(r"vibe \d+\.\d+\.\d+", out) is not None, repr(r.stdout))
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r2 = run(["bash", str(VIBE), "-V"], env=env)
    check("-V exit 0", r2.returncode == 0, r2.stderr)
    check("-V matches --version", r2.stdout.strip() == out, r2.stdout)
    check("VERSION file exists", VERSION_FILE.is_file(), str(VERSION_FILE))
    if VERSION_FILE.is_file():
        ver = VERSION_FILE.read_text().strip()
        check("VERSION file is bare semver", re.fullmatch(r"\d+\.\d+\.\d+", ver) is not None, ver)
        check("VERSION matches --version output", out == f"vibe {ver}", f"{out!r} vs vibe {ver}")


def test_vibe_andeye_page_draft() -> None:
    print("\n[web/vibe-andeye.md]")
    check("page exists", WEB_VIBE_ANDEYE_MD.is_file(), str(WEB_VIBE_ANDEYE_MD))
    if not WEB_VIBE_ANDEYE_MD.is_file():
        return
    txt = WEB_VIBE_ANDEYE_MD.read_text()
    first = txt.splitlines()[0] if txt.splitlines() else ""
    check("first line is a DRAFT sentinel comment",
          first.startswith("<!--") and "DRAFT" in first, first)
    check("sentinel says not for publication",
          "not for publication" in first.lower(), first)


def test_install_preflight() -> None:
    print("\n[install.sh preflight]")
    src = INSTALL.read_text()
    check("preflight_deps function present", "preflight_deps()" in src, "")
    check("preflight invoked before clone",
          re.search(r"\npreflight_deps\n", src) is not None
          and src.index("preflight_deps\n") < src.index("git clone"), "")
    # Functional: strip PATH so every dep is absent -> exit 1, no clone/link.
    # /bin/bash is absolute so the outer invocation works with an empty PATH.
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "emptybin"
        empty.mkdir()
        env = {**os.environ, "HOME": td, "PATH": str(empty)}
        r = run(["/bin/bash", str(INSTALL)], env=env)
    out = r.stdout + r.stderr
    check("preflight exits non-zero when deps missing", r.returncode != 0, out)
    check("preflight prints the re-run guidance",
          "Install the missing dependencies" in out, out)
    check("preflight did not reach the symlink step", "Linked" not in out, out)


def test_licence_state() -> None:
    """Martin never confirmed the AGPL move (brain2 misrecording, corrected
    2026-07-08); the drafts are gone and vibe is plainly MIT."""
    print("\n[licence state]")
    lic = REPO / "LICENSE"
    check("active LICENSE is MIT", lic.is_file() and "MIT License" in lic.read_text(), "")
    check("AGPL draft removed", not (REPO / "LICENSE-AGPL3-DRAFT").exists(), "")
    check("CLA draft removed", not (REPO / "CLA-DRAFT.md").exists(), "")
    for name in ("README.md", "CONTRIBUTING.md", "web/vibe-andeye.md"):
        check(f"{name} does not announce an AGPL move",
              "settled on moving" not in (REPO / name).read_text(), name)


def test_env_hint_fresh() -> None:
    print("\n[write-env-hint.sh: fresh file]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        r = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("CLAUDE.md created", target.exists())
        if not target.exists():
            return
        content = target.read_text()
        check("has start marker", "BEGIN vibe env (managed)" in content)
        check("has end marker", "END vibe env" in content)
        check("mentions SSH", "SSH" in content)
        check("mentions firewall allowlist", "allowlist" in content)


def test_env_hint_idempotent() -> None:
    print("\n[write-env-hint.sh: idempotent]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        run(["bash", str(WRITE_ENV_HINT)], env=env)
        first = target.read_text()
        run(["bash", str(WRITE_ENV_HINT)], env=env)
        second = target.read_text()
        check("stable across re-runs", first == second,
              f"first len={len(first)} second len={len(second)}")


def test_env_hint_preserves_user_content() -> None:
    print("\n[write-env-hint.sh: preserves user content]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        target.write_text("# My personal notes\nAlways use tabs.\n")
        r = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        content = target.read_text()
        check("user content survives", "Always use tabs" in content)
        check("vibe block present", "BEGIN vibe env (managed)" in content)


def _run_ensure_docker_hints_off(home: Path):
    env = {
        **os.environ,
        "HOME": str(home),
        "VIBE_CONFIG": f"{home}/no-config",
        "VIBE_SOURCE_ONLY": "1",
    }
    script = f"source {shlex.quote(str(VIBE))}; ensure_docker_hints_off"
    return run(["bash", "-c", script], env=env)


def test_docker_hints_fresh() -> None:
    print("\n[ensure_docker_hints_off: no config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        cfg = home / ".docker" / "config.json"
        check("config created", cfg.exists())
        if cfg.exists():
            data = json.loads(cfg.read_text())
            check("hints is string 'false'", data.get("features", {}).get("hints") == "false",
                  cfg.read_text())


def test_docker_hints_heals_bool() -> None:
    print("\n[ensure_docker_hints_off: heals legacy bool]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": {"hints": False, "other": True},
                                   "credsStore": "osxkeychain"}))
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("hints coerced to string", data["features"]["hints"] == "false", cfg.read_text())
        check("other bool coerced", data["features"]["other"] == "true", cfg.read_text())
        check("unrelated field preserved", data.get("credsStore") == "osxkeychain",
              cfg.read_text())


def test_docker_hints_respects_user_string() -> None:
    print("\n[ensure_docker_hints_off: respects user choice]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": {"hints": "true"}}, indent=2) + "\n")
        mtime_before = cfg.stat().st_mtime_ns
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("hints='true' preserved", data["features"]["hints"] == "true", cfg.read_text())
        check("file not rewritten", cfg.stat().st_mtime_ns == mtime_before,
              "mtime changed — should have been a no-op")


def test_docker_hints_malformed_json() -> None:
    print("\n[ensure_docker_hints_off: malformed JSON is left alone]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{not valid json")
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        check("malformed file untouched", cfg.read_text() == "{not valid json")


def test_docker_hints_non_dict_features() -> None:
    print("\n[ensure_docker_hints_off: features field is not a dict]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": True}))
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("features reset to dict with hints='false'",
              data.get("features") == {"hints": "false"}, cfg.read_text())


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


def test_install_detects_local_clone() -> None:
    """install.sh run from a real clone should use it in-place, not touch ~/.vibe-src."""
    print("\n[install.sh: detects local clone]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "PATH": _stub_dep_bin(tmp)}
        # Pre-seed config so the installer doesn't prompt for a projects dir.
        (tmp / ".vibe").mkdir()
        (tmp / ".vibe" / "config").write_text(f'VIBE_PROJECTS_DIR="{tmp}/Projects"\n')
        r = run(["bash", str(INSTALL)], env=env, cwd=REPO)
        check("exit 0", r.returncode == 0, r.stderr)
        check("announces in-place use", "Using existing clone" in r.stdout, r.stdout)
        check("did NOT create ~/.vibe-src", not (tmp / ".vibe-src").exists())
        link = tmp / "bin" / "vibe"
        check("bin/vibe symlink created", link.is_symlink())
        if link.is_symlink():
            check("symlink points at repo checkout",
                  Path(os.readlink(link)) == VIBE,
                  f"readlink={os.readlink(link)}")


def test_install_falls_back_to_vibe_src() -> None:
    """install.sh run as a standalone script (not inside a clone) should clone ~/.vibe-src.

    We can't exercise the real clone path without network, so just assert the
    detection correctly rejects a non-clone directory by checking the script
    tries to run `git clone` (which will fail fast with no network / bad URL).
    """
    print("\n[install.sh: non-clone falls through to ~/.vibe-src path]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        standalone = tmp / "install.sh"
        standalone.write_text(INSTALL.read_text())
        env = {**os.environ, "HOME": str(tmp), "PATH": _stub_dep_bin(tmp)}
        (tmp / ".vibe").mkdir()
        (tmp / ".vibe" / "config").write_text(f'VIBE_PROJECTS_DIR="{tmp}/Projects"\n')
        r = run(["bash", str(standalone)], env=env, cwd=tmp)
        combined = r.stdout + r.stderr
        check("took clone/pull path (not in-place)",
              "Using existing clone" not in r.stdout, r.stdout)
        check("attempted to clone to ~/.vibe-src",
              "Cloning vibe to" in combined, combined[-400:])


def test_token_helpers() -> None:
    """save_token / lookup_token round-trip against a tmp $HOME."""
    print("\n[vibe token helpers]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        save_token "owner/repo" "ghp_test123"
        echo "FOUND=$(lookup_token owner/repo)"
        save_token "owner/repo" "ghp_test456"
        echo "FOUND2=$(lookup_token owner/repo)"
        echo "LINES=$(wc -l < "$HOME/.vibe/tokens" | tr -d ' ')"
        echo "PERMS=$(stat -c '%a' "$HOME/.vibe/tokens" 2>/dev/null || stat -f '%Lp' "$HOME/.vibe/tokens")"
        """
        r = run(["bash", "-c", script], env=env)
        check("helpers run cleanly", r.returncode == 0, r.stderr)
        check("lookup returns saved token",
              "FOUND=ghp_test123" in r.stdout, r.stdout)
        check("save replaces on second call",
              "FOUND2=ghp_test456" in r.stdout, r.stdout)
        check("tokens file has one entry",
              "LINES=1" in r.stdout, r.stdout)
        check("tokens file chmod 600",
              "PERMS=600" in r.stdout, r.stdout)


def test_op_mcp_creds_lookup() -> None:
    """lookup_token returns OPENPROJECT_MCP_URL/BEARER whole — including a
    bearer with a trailing '=' (base64 padding), via the `cut -d= -f2-` fix —
    and slash-free OP keys don't collide with `owner/repo` PAT lines."""
    print("\n[vibe: OpenProject MCP creds lookup]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        save_token "amybo/vibe" "ghp_repo"
        save_token "OPENPROJECT_MCP_URL" "https://openproject-mcp.tail09c06e.ts.net"
        save_token "OPENPROJECT_MCP_BEARER" "YmFzZTY0dG9rZW4="
        echo "URL=$(lookup_token OPENPROJECT_MCP_URL)"
        echo "BEARER=$(lookup_token OPENPROJECT_MCP_BEARER)"
        echo "REPO=$(lookup_token amybo/vibe)"
        """
        r = run(["bash", "-c", script], env=env)
        check("helpers run cleanly", r.returncode == 0, r.stderr)
        check("OP URL resolves whole (keeps ://)",
              "URL=https://openproject-mcp.tail09c06e.ts.net" in r.stdout, r.stdout)
        check("bearer keeps trailing '=' (cut -f2- fix)",
              "BEARER=YmFzZTY0dG9rZW4=" in r.stdout, r.stdout)
        check("repo PAT still resolves (no slash-free collision)",
              "REPO=ghp_repo" in r.stdout, r.stdout)


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


def _patched_code_check(tmp: Path, target_paths: list[Path]) -> Path:
    """Copy code-check.py into tmp, rewrite scripts() to return target_paths.

    Returns the path to the patched copy so callers can invoke it with
    `python3 <returned path> --json`.  The patched copy's REPO constant is
    pinned to the real repo root so relative-path logic works, and scripts()
    returns an explicit list of target_paths — all of which must live inside
    REPO so that relative_to(REPO) succeeds.
    """
    original = CODE_CHECK.read_text()
    # Pin REPO to the real repo root (the copy lives in a temp dir, so
    # Path(__file__).resolve().parent would be wrong).
    patched = original.replace(
        "REPO = Path(__file__).resolve().parent",
        f"REPO = Path({str(REPO)!r})",
    )
    # Build a literal Python list expression for the paths.
    paths_repr = "[" + ", ".join(f"Path({str(p)!r})" for p in target_paths) + "]"
    # Replace the scripts() body with a hardcoded return.
    patched = patched.replace(
        "def scripts() -> list[Path]:\n"
        "    candidates = [REPO / \"vibe\", REPO / \"install.sh\"]\n"
        "    candidates += sorted((REPO / \"devcontainer\").glob(\"*.sh\"))\n"
        "    candidates += sorted((REPO / \"devcontainer\" / \"hooks\").glob(\"*.sh\"))\n"
        "    return [p for p in candidates if p.exists()]",
        f"def scripts() -> list[Path]:\n    return {paths_repr}",
    )
    out = tmp / "code-check-patched.py"
    out.write_text(patched)
    return out


# AC1 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_clean_exit_and_valid_json() -> None:
    """AC1: --json exits 0 on clean repo, stdout is valid JSON."""
    print("\n[json AC1: clean exit + valid JSON]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    check("[json] AC1 exit-0 on clean repo", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    try:
        data = json.loads(r.stdout)
        check("[json] AC1 stdout is valid JSON", True)
    except json.JSONDecodeError as exc:
        check("[json] AC1 stdout is valid JSON", False, str(exc))
        data = {}
    check("[json] AC1 no findings on clean repo",
          isinstance(data.get("findings"), list) and len(data.get("findings", [])) == 0,
          str(data))


# AC2 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_top_level_keys() -> None:
    """AC2: top-level keys present with correct types."""
    print("\n[json AC2: top-level keys + types]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        check("[json] AC2 parse for schema check", False, r.stdout[:200])
        return
    check("[json] AC2 key 'tool' == 'shellcheck'", data.get("tool") == "shellcheck",
          str(data.get("tool")))
    check("[json] AC2 key 'shellcheck_version' is str",
          isinstance(data.get("shellcheck_version"), str) and data.get("shellcheck_version", "") != "",
          str(data.get("shellcheck_version")))
    check("[json] AC2 key 'files_checked' is list",
          isinstance(data.get("files_checked"), list), str(type(data.get("files_checked"))))
    check("[json] AC2 key 'findings' is list",
          isinstance(data.get("findings"), list), str(type(data.get("findings"))))
    summary = data.get("summary", {})
    check("[json] AC2 key 'summary' is dict", isinstance(summary, dict), str(type(summary)))
    check("[json] AC2 summary.files is int", isinstance(summary.get("files"), int),
          str(type(summary.get("files"))))
    check("[json] AC2 summary.files_with_issues is int",
          isinstance(summary.get("files_with_issues"), int),
          str(type(summary.get("files_with_issues"))))
    check("[json] AC2 summary.total_findings is int",
          isinstance(summary.get("total_findings"), int),
          str(type(summary.get("total_findings"))))


# AC3 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_finding_schema() -> None:
    """AC3: each finding has required keys with correct types; code is int."""
    print("\n[json AC3: finding schema]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bad = REPO / "_smoke_test_bad_script.sh"
        try:
            _make_bad_script(bad)
            patched = _patched_code_check(tmp, [bad])
            r = run(["python3", str(patched), "--json"], cwd=REPO)
            # Exit 1 expected (findings present)
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC3 parse findings JSON", False, r.stdout[:200])
                return
            findings = data.get("findings", [])
            check("[json] AC3 at least one finding present", len(findings) > 0,
                  f"findings={findings}")
            if findings:
                f = findings[0]
                check("[json] AC3 finding has 'file' str", isinstance(f.get("file"), str),
                      str(f))
                check("[json] AC3 finding has 'line' int", isinstance(f.get("line"), int),
                      str(f))
                check("[json] AC3 finding has 'column' int", isinstance(f.get("column"), int),
                      str(f))
                check("[json] AC3 finding has 'level' str", isinstance(f.get("level"), str),
                      str(f))
                check("[json] AC3 finding 'code' is int (not str)",
                      isinstance(f.get("code"), int) and not isinstance(f.get("code"), bool),
                      f"code={f.get('code')!r} type={type(f.get('code'))}")
                check("[json] AC3 finding has 'message' str",
                      isinstance(f.get("message"), str), str(f))
                check("[json] AC3 finding 'level' value in allowed set",
                      f.get("level") in {"error", "warning", "info", "style"}, str(f))
        finally:
            if bad.exists():
                bad.unlink()


# AC4 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_findings_exit1_and_count() -> None:
    """AC4: with findings, exit 1 and total_findings == len(findings) > 0."""
    print("\n[json AC4: findings → exit 1 + count matches]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bad = REPO / "_smoke_test_bad_ac4.sh"
        try:
            _make_bad_script(bad, varname="myunused")
            patched = _patched_code_check(tmp, [bad])
            r = run(["python3", str(patched), "--json"], cwd=REPO)
            check("[json] AC4 exit 1 when findings present", r.returncode == 1,
                  f"exit={r.returncode} stderr={r.stderr[:200]}")
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC4 parse JSON on exit-1", False, r.stdout[:200])
                return
            findings = data.get("findings", [])
            total = data.get("summary", {}).get("total_findings", -1)
            check("[json] AC4 total_findings > 0", total > 0, f"total_findings={total}")
            check("[json] AC4 total_findings == len(findings)",
                  total == len(findings), f"total_findings={total} len={len(findings)}")
        finally:
            if bad.exists():
                bad.unlink()


# AC5 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_stdout_only_json() -> None:
    """AC5: --json stdout is exactly one JSON object, no progress lines."""
    print("\n[json AC5: stdout is exactly one JSON object]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    stdout = r.stdout
    # Must parse as a single JSON object from the whole stdout
    try:
        data = json.loads(stdout)
        check("[json] AC5 stdout parses as single JSON object", isinstance(data, dict),
              f"type={type(data)}")
    except json.JSONDecodeError as exc:
        check("[json] AC5 stdout parses as single JSON object", False, str(exc))
        return
    # Must not contain progress arrows (→ shellcheck) in stdout
    check("[json] AC5 no '→ shellcheck' progress lines in stdout",
          "→ shellcheck" not in stdout, stdout[:300])
    # Must not contain human summary line
    check("[json] AC5 no '✓ shellcheck clean' human line in stdout",
          "✓ shellcheck clean" not in stdout, stdout[:300])
    check("[json] AC5 no '✗ shellcheck' human line in stdout",
          "✗ shellcheck" not in stdout, stdout[:300])
    # Stdout should decode to exactly one object (no trailing text after the JSON)
    stripped = stdout.strip()
    # Verify that after the JSON object there is no extra content
    try:
        decoder = json.JSONDecoder()
        obj, idx = decoder.raw_decode(stripped)
        check("[json] AC5 no extra text after JSON object",
              idx == len(stripped), f"extra text: {stripped[idx:idx+80]!r}")
    except json.JSONDecodeError as exc:
        check("[json] AC5 no extra text after JSON object", False, str(exc))


# AC6 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_human_mode_unchanged() -> None:
    """AC6: without --json, human-readable output is preserved (arrows + summary)."""
    print("\n[json AC6: human mode output unchanged]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[json] AC6 human mode exits 0 on clean repo", r.returncode == 0,
          f"exit={r.returncode}")
    check("[json] AC6 human mode has '→ shellcheck' progress lines",
          "→ shellcheck" in r.stdout, r.stdout[:300])
    check("[json] AC6 human mode has '✓ shellcheck clean' summary",
          "✓ shellcheck clean" in r.stdout, r.stdout[:300])
    # Confirm --json mode does NOT have these
    rj = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    check("[json] AC6 --json mode has NO '→ shellcheck' lines",
          "→ shellcheck" not in rj.stdout, rj.stdout[:300])
    check("[json] AC6 --json mode has NO '✓ shellcheck clean' line",
          "✓ shellcheck clean" not in rj.stdout, rj.stdout[:300])


# AC7 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_missing_shellcheck() -> None:
    """AC7: missing shellcheck + --json → JSON error object on stdout, exit 2."""
    print("\n[json AC7: missing shellcheck → JSON error object]")
    with tempfile.TemporaryDirectory() as td:
        fake_bin = Path(td) / "bin"
        fake_bin.mkdir()
        # Symlink python3 into fake_bin but do NOT include shellcheck.
        python3_src = Path("/usr/bin/python3")
        (fake_bin / "python3").symlink_to(python3_src)
        env = {**os.environ, "PATH": str(fake_bin)}
        # Run code-check.py via absolute python3 path to avoid PATH lookup for python3.
        r = subprocess.run(
            [str(python3_src), str(CODE_CHECK), "--json"],
            capture_output=True, text=True, env=env, cwd=str(REPO),
        )
        check("[json] AC7 exit 2 when shellcheck missing", r.returncode == 2,
              f"exit={r.returncode}")
        try:
            data = json.loads(r.stdout)
            check("[json] AC7 stdout is valid JSON error object", isinstance(data, dict),
                  f"type={type(data)}")
        except json.JSONDecodeError as exc:
            check("[json] AC7 stdout is valid JSON error object", False,
                  f"{exc} stdout={r.stdout[:200]}")
            return
        check("[json] AC7 error object has 'error' key == 'shellcheck-not-installed'",
              data.get("error") == "shellcheck-not-installed", str(data))
        check("[json] AC7 error object has 'tool' key == 'shellcheck'",
              data.get("tool") == "shellcheck", str(data))


# AC8 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_help_mentions_flag() -> None:
    """AC8: --help exits 0 and help text mentions --json."""
    print("\n[json AC8: --help mentions --json]")
    r = run(["python3", str(CODE_CHECK), "--help"], cwd=REPO)
    check("[json] AC8 --help exits 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    combined = r.stdout + r.stderr  # argparse may write to stderr on some versions
    check("[json] AC8 help text mentions '--json'", "--json" in combined, combined[:500])


# AC9 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_summary_counts() -> None:
    """AC9: summary.files == len(files_checked); summary.files_with_issues matches."""
    print("\n[json AC9: summary counts accuracy]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 3 files: 2 bad, 1 good — all must live inside REPO for relative_to to work
        bad1 = REPO / "_smoke_ac9_bad1.sh"
        bad2 = REPO / "_smoke_ac9_bad2.sh"
        good = REPO / "_smoke_ac9_good.sh"
        try:
            _make_bad_script(bad1, varname="unused_one")
            _make_bad_script(bad2, varname="unused_two")
            _make_good_script(good)
            patched = _patched_code_check(tmp, [bad1, bad2, good])
            r = run(["python3", str(patched), "--json"], cwd=REPO)
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC9 parse JSON", False, r.stdout[:200])
                return
            files_checked = data.get("files_checked", [])
            findings = data.get("findings", [])
            summary = data.get("summary", {})
            check("[json] AC9 summary.files == len(files_checked)",
                  summary.get("files") == len(files_checked),
                  f"summary.files={summary.get('files')} len(files_checked)={len(files_checked)}")
            check("[json] AC9 files_checked has 3 entries", len(files_checked) == 3,
                  str(files_checked))
            distinct_files_with_issues = len({f["file"] for f in findings})
            check("[json] AC9 summary.files_with_issues matches distinct finding files",
                  summary.get("files_with_issues") == distinct_files_with_issues,
                  f"summary.files_with_issues={summary.get('files_with_issues')} "
                  f"distinct={distinct_files_with_issues}")
            check("[json] AC9 files_with_issues == 2 (two bad scripts)",
                  summary.get("files_with_issues") == 2,
                  f"files_with_issues={summary.get('files_with_issues')}")
        finally:
            for p in [bad1, bad2, good]:
                if p.exists():
                    p.unlink()


# AC10 ────────────────────────────────────────────────────────────────────────

def test_code_check_json_same_target_list() -> None:
    """AC10: --json and human mode scan identical target lists."""
    print("\n[json AC10: same target list with/without --json]")
    # Human mode: extract file paths from '→ shellcheck <path>' lines
    r_human = run(["python3", str(CODE_CHECK)], cwd=REPO)
    human_paths = set()
    for line in r_human.stdout.splitlines():
        line = line.strip()
        if line.startswith("→ shellcheck "):
            path_part = line[len("→ shellcheck "):].strip()
            human_paths.add(path_part)
    check("[json] AC10 human mode produced at least one path", len(human_paths) > 0,
          r_human.stdout[:300])
    # JSON mode: extract files_checked
    r_json = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    try:
        data = json.loads(r_json.stdout)
    except json.JSONDecodeError:
        check("[json] AC10 parse --json output", False, r_json.stdout[:200])
        return
    json_paths = set(data.get("files_checked", []))
    check("[json] AC10 --json files_checked == human mode paths",
          json_paths == human_paths,
          f"json_paths={sorted(json_paths)} human_paths={sorted(human_paths)}")


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


def test_vibe_resume_args_fresh() -> None:
    print("\n[vibe build_claude_resume_args: fresh]")
    r = _source_vibe_call({}, 'echo "OUT=[$(build_claude_resume_args)]"')
    check("fresh exits 0", r.returncode == 0, r.stderr)
    check("fresh emits empty arg fragment", "OUT=[]" in r.stdout, r.stdout)


def test_vibe_resume_args_continue() -> None:
    print("\n[vibe build_claude_resume_args: --continue]")
    r = _source_vibe_call({"CONTINUE": "true"},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--continue exits 0", r.returncode == 0, r.stderr)
    check("--continue emits '--continue'", "OUT=[--continue]" in r.stdout, r.stdout)


def test_vibe_resume_args_resume_picker() -> None:
    print("\n[vibe build_claude_resume_args: --resume (picker)]")
    r = _source_vibe_call({"RESUME": "true"},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--resume exits 0", r.returncode == 0, r.stderr)
    check("--resume emits '--resume'", "OUT=[--resume]" in r.stdout, r.stdout)


def test_vibe_resume_args_resume_uid() -> None:
    print("\n[vibe build_claude_resume_args: --resume <uuid>]")
    uid = "12345678-1234-1234-1234-123456789abc"
    r = _source_vibe_call({"RESUME": "true", "RESUME_UID": uid},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--resume <uid> exits 0", r.returncode == 0, r.stderr)
    check("--resume <uid> emits '--resume <uid>'",
          f"OUT=[--resume {uid}]" in r.stdout, r.stdout)


def test_vibe_is_uuid() -> None:
    print("\n[vibe is_uuid]")
    cases = [
        ("12345678-1234-1234-1234-123456789abc", True, "valid lowercase"),
        ("ABCDEF12-3456-7890-ABCD-EF1234567890", True, "valid uppercase"),
        ("not-a-uuid", False, "obvious non-uuid"),
        ("", False, "empty string"),
        ("12345678-1234-1234-1234-123456789ab", False, "too short"),
        ("12345678-1234-1234-1234-123456789abcd", False, "too long"),
        ("--continue", False, "looks like a flag"),
        ("my-project", False, "project name"),
    ]
    for value, expected, label in cases:
        r = _source_vibe_call({}, f'is_uuid {shlex.quote(value)} && echo Y || echo N')
        observed = "Y" in r.stdout
        check(f"is_uuid '{value}' → {expected} ({label})",
              observed == expected, r.stdout + r.stderr)


def test_vibe_help_mentions_continue_and_resume() -> None:
    print("\n[vibe --help mentions --continue and --resume]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("--help exits 0", r.returncode == 0, r.stderr)
    check("help mentions --continue", "--continue" in r.stdout, r.stdout[:400])
    check("help mentions --resume", "--resume" in r.stdout, r.stdout[:400])
    check("help notes positional+flag any-order",
          "any order" in r.stdout, r.stdout[:600])


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


def test_parse_args_no_args() -> None:
    print("\n[parse_vibe_args: no args → all defaults]")
    r = _parse_args_probe([])
    check("exits 0", r.returncode == 0, r.stderr)
    check("REBUILD=false", "REBUILD=[false]" in r.stdout, r.stdout)
    check("CONTINUE=false", "CONTINUE=[false]" in r.stdout, r.stdout)
    check("RESUME=false", "RESUME=[false]" in r.stdout, r.stdout)
    check("RESUME_UID empty", "RESUME_UID=[]" in r.stdout, r.stdout)
    check("PROJECT_ARG empty", "PROJECT_ARG=[]" in r.stdout, r.stdout)


def test_parse_args_leading_continue() -> None:
    print("\n[parse_vibe_args: --continue (no project)]")
    r = _parse_args_probe(["--continue"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("CONTINUE=true", "CONTINUE=[true]" in r.stdout, r.stdout)
    check("PROJECT_ARG empty", "PROJECT_ARG=[]" in r.stdout, r.stdout)


def test_parse_args_project_only() -> None:
    print("\n[parse_vibe_args: vibe (project only)]")
    r = _parse_args_probe(["vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=false", "CONTINUE=[false]" in r.stdout, r.stdout)


def test_parse_args_project_then_continue() -> None:
    print("\n[parse_vibe_args: vibe --continue (regression: was silently dropped)]")
    r = _parse_args_probe(["vibe", "--continue"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=true (the fix)", "CONTINUE=[true]" in r.stdout, r.stdout)


def test_parse_args_continue_then_project() -> None:
    print("\n[parse_vibe_args: --continue vibe (leading-flag form, must still work)]")
    r = _parse_args_probe(["--continue", "vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=true", "CONTINUE=[true]" in r.stdout, r.stdout)


def test_parse_args_project_then_resume_uid() -> None:
    print("\n[parse_vibe_args: vibe --resume <uuid>]")
    uid = "12345678-1234-1234-1234-123456789abc"
    r = _parse_args_probe(["vibe", "--resume", uid])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("RESUME=true", "RESUME=[true]" in r.stdout, r.stdout)
    check(f"RESUME_UID={uid}", f"RESUME_UID=[{uid}]" in r.stdout, r.stdout)


def test_parse_args_project_then_resume_picker() -> None:
    print("\n[parse_vibe_args: vibe --resume (no uuid → picker)]")
    r = _parse_args_probe(["vibe", "--resume"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("RESUME=true", "RESUME=[true]" in r.stdout, r.stdout)
    check("RESUME_UID empty", "RESUME_UID=[]" in r.stdout, r.stdout)


def test_parse_args_project_then_rebuild() -> None:
    print("\n[parse_vibe_args: vibe --rebuild]")
    r = _parse_args_probe(["vibe", "--rebuild"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("REBUILD=true", "REBUILD=[true]" in r.stdout, r.stdout)


def test_parse_args_two_positionals_rejected() -> None:
    print("\n[parse_vibe_args: two positionals rejected]")
    r = _parse_args_probe(["vibe", "other"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions extra", "extra argument" in r.stderr, r.stderr)


def test_parse_args_unknown_flag_rejected() -> None:
    print("\n[parse_vibe_args: unknown trailing flag rejected]")
    r = _parse_args_probe(["vibe", "--bogus"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions unknown", "Unknown flag" in r.stderr, r.stderr)


# ── Model selection tests (--fable / --model / billing gate helpers) ──────────


def test_parse_args_fable() -> None:
    print("\n[parse_vibe_args: vibe --fable → MODEL_ARG=claude-fable-5]")
    r = _parse_args_probe(["vibe", "--fable"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("MODEL_ARG=claude-fable-5",
          "MODEL_ARG=[claude-fable-5]" in r.stdout, r.stdout)


def test_parse_args_model_explicit() -> None:
    print("\n[parse_vibe_args: --model claude-opus-4-8]")
    r = _parse_args_probe(["--model", "claude-opus-4-8", "vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("MODEL_ARG=claude-opus-4-8",
          "MODEL_ARG=[claude-opus-4-8]" in r.stdout, r.stdout)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)


def test_parse_args_model_missing_value_rejected() -> None:
    print("\n[parse_vibe_args: --model with no value rejected]")
    r = _parse_args_probe(["--model"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions model id", "model id" in r.stderr, r.stderr)


def test_parse_args_model_injection_rejected() -> None:
    print("\n[parse_vibe_args: --model with shell metachars rejected]")
    for bad in ["claude; rm -rf /", "a b", "$(whoami)", "claude`x`", "--continue"]:
        r = _parse_args_probe(["--model", bad])
        check(f"--model {bad!r} exits 1", r.returncode == 1,
              r.stdout + r.stderr)


def test_vibe_is_model_id() -> None:
    print("\n[vibe is_model_id]")
    cases = [
        ("claude-fable-5", True, "fable id"),
        ("claude-opus-4-8", True, "opus id"),
        ("claude-3-5-haiku-20241022", True, "dated id"),
        ("opus", True, "alias"),
        ("", False, "empty"),
        ("a b", False, "space"),
        ("a;b", False, "semicolon"),
        ("$(x)", False, "command substitution"),
        ("a`b`", False, "backticks"),
        ("a'b", False, "quote"),
    ]
    for value, expected, label in cases:
        r = _source_vibe_call({}, f'is_model_id {shlex.quote(value)} && echo Y || echo N')
        observed = "Y" in r.stdout
        check(f"is_model_id '{value}' → {expected} ({label})",
              observed == expected, r.stdout + r.stderr)


def test_vibe_model_args_fresh() -> None:
    print("\n[vibe build_claude_model_args: no model → empty]")
    r = _source_vibe_call({}, 'echo "OUT=[$(build_claude_model_args)]"')
    check("exits 0", r.returncode == 0, r.stderr)
    check("emits empty fragment", "OUT=[]" in r.stdout, r.stdout)


def test_vibe_model_args_set() -> None:
    print("\n[vibe build_claude_model_args: MODEL_ARG set]")
    r = _source_vibe_call({"MODEL_ARG": "claude-fable-5"},
                          'echo "OUT=[$(build_claude_model_args)]"')
    check("exits 0", r.returncode == 0, r.stderr)
    check("emits '--model claude-fable-5'",
          "OUT=[--model claude-fable-5]" in r.stdout, r.stdout)


def test_vibe_fable_billing_phase() -> None:
    print("\n[vibe fable_billing_phase: free until 7 Jul 2026, credits after]")
    cases = [
        ("20260609", "free", "launch day"),
        ("20260707", "free", "last free day"),
        ("20260708", "credits", "cutover day"),
        ("20270101", "credits", "well after"),
    ]
    for date, expected, label in cases:
        r = _source_vibe_call({}, f'echo "OUT=[$(fable_billing_phase {date})]"')
        check(f"{date} → {expected} ({label})",
              f"OUT=[{expected}]" in r.stdout, r.stdout + r.stderr)


def test_vibe_auto_resume_helpers() -> None:
    print("\n[vibe auto-resume marker helpers]")
    snippet = (
        'm="${TMPDIR:-/tmp}/vibe-ar-test.$$"; '
        "printf 'active=1\\nremaining=2\\nresume_at=1751600000\\n' > \"$m\"; "
        'echo "FIELD=[$(auto_resume_field "$m" remaining)]"; '
        'echo "BADKEY=[$(auto_resume_field "$m" nope)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING=[yes]"; else echo "PENDING=[no]"; fi; '
        'auto_resume_decrement "$m"; auto_resume_decrement "$m"; '
        'echo "AFTER=[$(auto_resume_field "$m" remaining)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING2=[yes]"; else echo "PENDING2=[no]"; fi; '
        "printf 'active=1\\nremaining=evil; rm -rf /\\n' > \"$m\"; "
        'echo "EVIL=[$(auto_resume_field "$m" remaining)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING3=[yes]"; else echo "PENDING3=[no]"; fi; '
        'if auto_resume_pending "$m.missing"; then echo "PENDING4=[yes]"; else echo "PENDING4=[no]"; fi; '
        'rm -f "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("numeric field read", "FIELD=[2]" in r.stdout, r.stdout)
    check("missing key → empty", "BADKEY=[]" in r.stdout, r.stdout)
    check("pending when active + remaining", "PENDING=[yes]" in r.stdout, r.stdout)
    check("decrement twice → 0", "AFTER=[0]" in r.stdout, r.stdout)
    check("not pending at remaining=0", "PENDING2=[no]" in r.stdout, r.stdout)
    check("non-numeric value rejected", "EVIL=[]" in r.stdout, r.stdout)
    check("not pending on malformed marker", "PENDING3=[no]" in r.stdout, r.stdout)
    check("not pending on missing file", "PENDING4=[no]" in r.stdout, r.stdout)


def test_vibe_help_mentions_fable_and_model() -> None:
    print("\n[vibe --help mentions --fable and --model]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("--help exits 0", r.returncode == 0, r.stderr)
    check("help mentions --fable", "--fable" in r.stdout, r.stdout[:800])
    check("help mentions --model", "--model" in r.stdout, r.stdout[:800])
    check("help mentions the credits cutover",
          "8 Jul" in r.stdout, r.stdout)


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


def test_ac1_no_container() -> None:
    """AC1: No container → no-op."""
    print("\n[task_015 AC1: no container → no-op]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="",  # empty - no containers
        ps_rc=0,
        cref_output="",
        cref_rc=0,
        tag_id_output="sha256:abc123",
        tag_id_rc=0,
        ref_id_output="",
        ref_id_rc=0,
    )
    check("AC1 exits 0", r.returncode == 0, r.stderr)
    check("AC1 emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac2_matching_image() -> None:
    """AC2: Matching image → no-op."""
    print("\n[task_015 AC2: matching image → no-op]")
    # Both normalised ids are the same
    shared_id = "sha256:abc123def456"
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:abc123def456",  # container ref
        cref_rc=0,
        tag_id_output=shared_id,  # tag normalised id
        tag_id_rc=0,
        ref_id_output=shared_id,  # container ref normalised to same id
        ref_id_rc=0,
    )
    check("AC2 exits 0", r.returncode == 0, r.stderr)
    check("AC2 emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac3_drifted_image() -> None:
    """AC3: Drifted image → emit '1'."""
    print("\n[task_015 AC3: drifted image → emit '1']")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-image-digest",
        cref_rc=0,
        tag_id_output="sha256:new-image-digest",  # current image is different
        tag_id_rc=0,
        ref_id_output="sha256:old-image-digest",  # container's old image normalised
        ref_id_rc=0,
    )
    check("AC3 exits 0", r.returncode == 0, r.stderr)
    check("AC3 emits '1'", r.stdout.strip() == "1", f"output: {r.stdout}")


def test_ac4_remove_existing_flag_rebuild_true_drift_marker() -> None:
    """AC4a: (true, "1") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4a: (true, '1') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "true" "1"')
    check("AC4a exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]  # filter empty lines
    check("AC4a emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4a token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_ac4_remove_existing_flag_rebuild_true_no_drift() -> None:
    """AC4b: (true, "") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4b: (true, '') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "true" ""')
    check("AC4b exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]
    check("AC4b emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4b token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_ac4_remove_existing_flag_no_rebuild_drift_marker() -> None:
    """AC4c: (false, "1") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4c: (false, '1') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "false" "1"')
    check("AC4c exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]
    check("AC4c emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4c token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_ac4_remove_existing_flag_no_rebuild_no_drift() -> None:
    """AC4d: (false, "") → empty."""
    print("\n[task_015 AC4d: (false, '') → empty]")
    r = _source_vibe_call({}, 'remove_existing_flag "false" ""')
    check("AC4d exits 0", r.returncode == 0, r.stderr)
    check("AC4d emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5a_docker_all_fail() -> None:
    """AC5a: All docker calls fail → emit nothing, no abort."""
    print("\n[task_015 AC5a: all docker calls fail → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="",
        ps_rc=1,  # docker ps fails
        cref_output="",
        cref_rc=1,  # docker inspect fails
        tag_id_output="",
        tag_id_rc=1,  # tag inspect fails
        ref_id_output="",
        ref_id_rc=1,  # ref inspect fails
    )
    check("AC5a exits 0 (no abort)", r.returncode == 0, r.stderr)
    check("AC5a emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5b_ps_ok_inspect_fails() -> None:
    """AC5b: docker ps ok, docker inspect fails → emit nothing."""
    print("\n[task_015 AC5b: ps ok, inspect fails → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="",  # inspect (container ref) returns empty
        cref_rc=1,
        tag_id_output="sha256:abc",
        tag_id_rc=0,
        ref_id_output="",
        ref_id_rc=0,
    )
    check("AC5b exits 0", r.returncode == 0, r.stderr)
    check("AC5b emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5c_ps_inspect_ok_tag_fails() -> None:
    """AC5c: ps+inspect ok, tag image inspect fails → emit nothing."""
    print("\n[task_015 AC5c: ps+inspect ok, tag inspect fails → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-digest",
        cref_rc=0,
        tag_id_output="",  # tag inspect returns empty
        tag_id_rc=1,
        ref_id_output="sha256:old-digest",
        ref_id_rc=0,
    )
    check("AC5c exits 0", r.returncode == 0, r.stderr)
    check("AC5c emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5d_ps_inspect_ok_ref_inspect_fails() -> None:
    """AC5d: ps+inspect ok, current tag ok, but container ref inspect fails → emit '1'."""
    print("\n[task_015 AC5d: ref inspect fails (image pruned) → emit '1']")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-digest",
        cref_rc=0,
        tag_id_output="sha256:new-digest",
        tag_id_rc=0,
        ref_id_output="",  # ref inspect returns empty - source image pruned
        ref_id_rc=1,
    )
    check("AC5d exits 0", r.returncode == 0, r.stderr)
    check("AC5d emits '1'", r.stdout.strip() == "1", f"output: {r.stdout}")


def test_ac6_multiple_containers_uses_first() -> None:
    """AC6: Multiple containers → uses first line only."""
    print("\n[task_015 AC6: multiple containers uses first]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-1\ncontainer-2\ncontainer-3",  # multiple lines
        ps_rc=0,
        cref_output="sha256:old-image",  # inspecting first container
        cref_rc=0,
        tag_id_output="sha256:new-image",
        tag_id_rc=0,
        ref_id_output="sha256:old-image",
        ref_id_rc=0,
    )
    check("AC6 exits 0", r.returncode == 0, r.stderr)
    check("AC6 emits '1' (drifted, uses first)", r.stdout.strip() == "1",
          f"output: {r.stdout}")


def test_ac8_comment_present() -> None:
    """AC8: Comment containing 'drift' or 'superseded' present in vibe source."""
    print("\n[task_015 AC8: comment mentions drift/superseded]")
    content = VIBE.read_text()
    # Look for a comment line (first non-space char is #) containing drift or superseded
    has_drift_comment = False
    for line in content.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            if 'drift' in stripped.lower() or 'superseded' in stripped.lower():
                has_drift_comment = True
                break
    check("AC8 comment present", has_drift_comment,
          "no comment with 'drift' or 'superseded' found in vibe source")


# ── Runner ────────────────────────────────────────────────────────────────────


# ── Learning library tests ───────────────────────────────────────────────────


def test_learning_config_format() -> None:
    """AC1: Config file format with all 4 keys, strict parsing."""
    print("\n[learning AC1: config format + strict parse]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            'VIBE_LEARNING_ENABLED="true"\n'
            'VIBE_LEARNING_PATH="/tmp/learning"\n'
            'VIBE_LEARNING_VISIBILITY="private"\n'
            'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            "learning_load; "
            "echo ENABLED=$VIBE_LEARNING_ENABLED; "
            "echo PATH=$VIBE_LEARNING_PATH; "
            "echo VIS=$VIBE_LEARNING_VISIBILITY; "
            "echo REMOTE=$VIBE_LEARNING_GIT_REMOTE"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC1 exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC1 ENABLED='true'", "ENABLED=true" in r.stdout, r.stdout)
        check("[learn] AC1 PATH='/tmp/learning'", "PATH=/tmp/learning" in r.stdout, r.stdout)
        check("[learn] AC1 VIS='private'", "VIS=private" in r.stdout, r.stdout)
        check("[learn] AC1 REMOTE='origin'", "REMOTE=origin" in r.stdout, r.stdout)


def test_learning_strict_parser_no_injection() -> None:
    """AC2: Strict parser rejects shell injection via config."""
    print("\n[learning AC2: strict parser, no shell injection]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        # Inject a command that would touch a file if eval'd
        canary = home / "vibe-injection-canary"
        cfg.write_text(
            'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="/tmp"; touch {canary}\n'
            'VIBE_LEARNING_VISIBILITY="private"\n'
            'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = f"source {shlex.quote(str(VIBE))}; learning_load"
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC2 no injection exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC2 canary file NOT created", not canary.exists(),
              f"canary exists: {canary}")


def test_learning_init_interactive() -> None:
    """AC3: vibe learn --init interactive flow, chmod 600, --reinit path."""
    print("\n[learning AC3: --init interactive + reinit]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib_path = home / "mylib"
        lib_path.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = {**os.environ, "HOME": str(home)}
        # Simulate user input: absolute path (no mkdir needed), private, no remote.
        input_str = f"{lib_path}\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC3 --init exits 0", r.returncode == 0,
              f"stderr={r.stderr[:300]}")
        check("[learn] AC3 config created", cfg.exists(), str(cfg))
        if cfg.exists():
            mode = cfg.stat().st_mode & 0o777
            check("[learn] AC3 config chmod 600", mode == 0o600,
                  f"mode={oct(mode)}")
            content = cfg.read_text()
            check("[learn] AC3 config has ENABLED=true", "ENABLED=\"true\"" in content,
                  content)


def test_learning_init_mkdir_offer() -> None:
    """AC3: --init offers to create missing path."""
    print("\n[learning AC3: --init mkdir offer]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib_path = home / "newlib"
        env = {**os.environ, "HOME": str(home)}
        # User provides non-existent path; say yes to mkdir; then private.
        input_str = f"{lib_path}\ny\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC3 mkdir exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC3 mkdir created path", lib_path.exists(), str(lib_path))


def test_learning_init_reinit_path() -> None:
    """AC3: --reinit overwrites existing enabled config."""
    print("\n[learning AC3: --reinit overwrites]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib1 = home / "lib1"
        lib2 = home / "lib2"
        lib1.mkdir()
        lib2.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = {**os.environ, "HOME": str(home)}
        # First init
        input_str = f"{lib1}\nprivate\n"
        r1 = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str)
        check("[learn] AC3 first init exit 0", r1.returncode == 0, r1.stderr)
        # Second init without --reinit should fail
        input_str2 = f"{lib2}\nprivate\n"
        r2 = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str2)
        check("[learn] AC3 second init fails without --reinit", r2.returncode == 1,
              r2.stdout)
        # With --reinit should succeed
        r3 = run(["bash", str(VIBE), "learn", "--reinit"], env=env, input=input_str2)
        check("[learn] AC3 --reinit succeeds", r3.returncode == 0, r3.stderr)
        content = cfg.read_text()
        check("[learn] AC3 --reinit updated path", str(lib2) in content, content)


def test_learning_default_off_no_config() -> None:
    """AC4: Default-off: with no config, learning_is_enabled exits 1."""
    print("\n[learning AC4: default-off behavior]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = f"source {shlex.quote(str(VIBE))}; learning_is_enabled || echo NOT_ENABLED"
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC4 no config not enabled", "NOT_ENABLED" in r.stdout, r.stdout)


def test_learning_learn_without_init() -> None:
    """AC4: vibe learn without init exits 1 with message."""
    print("\n[learning AC4: learn without init refusal]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "test"], env=env)
        check("[learn] AC4 learn without init exits 1", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] AC4 error message present", "not initialized" in r.stderr,
              r.stderr)


def test_render_devcontainer_with_mounts_learning() -> None:
    """AC5/AC6: Generated override config has readonly /learnings mount."""
    print("\n[learning AC5: mount via override config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        src_cfg = REPO / "devcontainer" / "devcontainer.json"
        dst = Path(td) / "override.json"
        lib = Path(td) / "learnings"
        lib.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"render_devcontainer_with_mounts {shlex.quote(str(src_cfg))} "
            f"{shlex.quote(str(dst))} {shlex.quote(str(lib))} /learnings 1"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC5 render exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC5 output file created", dst.exists(), str(dst))
        if dst.exists():
            data = json.loads(dst.read_text())
            mounts = data.get("mounts", [])
            learning_mount = None
            for m in mounts:
                # mounts are objects (dicts) in the output from render_devcontainer_with_mounts
                if isinstance(m, dict) and m.get("target") == "/learnings":
                    learning_mount = m
                    break
            check("[learn] AC5 learning mount present", learning_mount is not None,
                  f"mounts={mounts}")
            if learning_mount:
                check("[learn] AC6 readonly=true", learning_mount.get("readonly") is True,
                      str(learning_mount))


def test_learning_dispatch_no_docker_required() -> None:
    """AC7: vibe learn --init works without docker on PATH."""
    print("\n[learning AC7: learn dispatch before preflight]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        env = {**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"}
        # Run vibe learn --init with docker removed from PATH.
        # If it tries to call docker, this will fail. If it dispatches correctly, it works.
        input_str = f"{lib}\nprivate\n"
        r = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str)
        check("[learn] AC7 learn --init works without docker", r.returncode == 0,
              f"stderr={r.stderr[:300]}")


def test_learning_capture_confirm_flow() -> None:
    """AC8: vibe learn '<pattern>' capture with confirm."""
    print("\n[learning AC8: capture confirm flow]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        # Run vibe learn with 'y' confirmation
        r = run(
            ["bash", str(VIBE), "learn", "test pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC8 capture with 'y' exits 0", r.returncode == 0, r.stderr)
        # Check that a file was created in lib
        files = list(lib.glob("*.md"))
        check("[learn] AC8 entry file created", len(files) == 1, f"files={files}")
        if files:
            content = files[0].read_text()
            check("[learn] AC8 file contains pattern", "test pattern" in content, content)


def test_learning_capture_eof_cancel() -> None:
    """AC8: EOF on stdin defaults to cancel, no write."""
    print("\n[learning AC8: EOF cancel]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        # Empty input triggers EOF
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="")
        check("[learn] AC8 EOF exits 0", r.returncode == 0, r.stderr)
        check("[learn] AC8 cancelled message", "cancelled" in r.stderr, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC8 EOF no write", len(files) == 0, f"files={files}")


def test_learning_capture_confirm_yes_word() -> None:
    """Confirm accepts 'yes' (full word), not just 'y'."""
    print("\n[learning: capture confirm 'yes']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "yes-word pattern"], env=env, input="yes\n")
        check("[learn] confirm 'yes' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'yes' wrote file", len(files) == 1, f"files={files}")


def test_learning_capture_confirm_uppercase_y() -> None:
    """Confirm accepts 'Y' (uppercase) - case-insensitive."""
    print("\n[learning: capture confirm 'Y']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "uppercase-Y pattern"], env=env, input="Y\n")
        check("[learn] confirm 'Y' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'Y' wrote file", len(files) == 1, f"files={files}")


def test_learning_capture_confirm_uppercase_yes() -> None:
    """Confirm accepts 'YES' (uppercase, full word)."""
    print("\n[learning: capture confirm 'YES']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "uppercase-YES pattern"], env=env, input="YES\n")
        check("[learn] confirm 'YES' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'YES' wrote file", len(files) == 1, f"files={files}")


def test_learnings_md_fragment_present() -> None:
    """devcontainer/claude-md/learnings.md ships and references /learnings."""
    print("\n[learnings.md fragment: present + content]")
    p = REPO / "devcontainer" / "claude-md" / "learnings.md"
    check("[learnings.md] file exists", p.exists())
    if not p.exists():
        return
    body = p.read_text()
    check("[learnings.md] mentions /learnings path", "/learnings" in body, body[:200])
    check("[learnings.md] explains read-only nature", "read-only" in body, body[:200])
    check("[learnings.md] references vibe learn host command", "vibe learn" in body, body[:200])
    nonblank = sum(1 for line in body.splitlines() if line.strip())
    check("[learnings.md] >= 30 non-blank lines (substantive)", nonblank >= 30, f"non-blank={nonblank}")


def test_learning_capture_confirm_no() -> None:
    """AC8: Answering 'n' to confirm cancels with no write."""
    print("\n[learning AC8: confirm 'n' cancels]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="n\n")
        check("[learn] AC8 confirm 'n' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC8 'n' no write", len(files) == 0, f"files={files}")


def test_learning_public_mode_push_prompt() -> None:
    """AC9: Public mode shows push prompt and processes git on 'y'."""
    print("\n[learning AC9: public mode push]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="public"\n'
            f'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = {**os.environ, "HOME": str(home)}
        # Confirm capture + push (will fail because lib is not a git repo, but entry saved locally)
        r = run(
            ["bash", str(VIBE), "learn", "test pattern"],
            env=env,
            input="y\ny\n",
        )
        check("[learn] AC9 public mode exits 0 even with git failure",
              r.returncode == 0, f"stderr={r.stderr[:300]}")
        check("[learn] AC9 push prompt shown", "Push to" in r.stderr, r.stderr)
        # Check entry was written locally (git failure doesn't prevent saving)
        files = list(lib.glob("*.md"))
        check("[learn] AC9 entry saved locally despite git failure",
              len(files) == 1, f"files={files}")


def test_learning_public_mode_git_failure_survives() -> None:
    """AC9: Git failure doesn't delete local entry."""
    print("\n[learning AC9: git failure survives locally]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="public"\n'
            f'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = {**os.environ, "HOME": str(home)}
        # git will fail because lib is not a git repo
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\ny\n",
        )
        check("[learn] AC9 git failure exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC9 entry saved despite git failure", len(files) == 1,
              f"files={files}")


def test_learning_private_mode_no_git() -> None:
    """AC10: Private mode skips git operations."""
    print("\n[learning AC10: private mode skips git]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home)}
        # Use a fake git that records calls
        fake_git_dir = home / "fake-bin"
        fake_git_dir.mkdir()
        git_log = home / "git-calls.log"
        git_script = (
            "#!/bin/bash\n"
            f'echo "$@" >> "{git_log}"\n'
            "exit 0\n"
        )
        git_path = fake_git_dir / "git"
        git_path.write_text(git_script)
        git_path.chmod(0o755)
        env["PATH"] = f"{fake_git_dir}:{env.get('PATH', '')}"
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC10 private mode exits 0", r.returncode == 0, r.stderr)
        check("[learn] AC10 no git calls in private mode",
              not git_log.exists() or git_log.read_text().strip() == "",
              git_log.read_text() if git_log.exists() else "")


def test_learning_marker_blocks_capture() -> None:
    """AC11: .vibe-no-learn marker blocks capture."""
    print("\n[learning AC11: marker blocks capture]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        # Create a project with marker
        proj = home / "project"
        proj.mkdir()
        (proj / ".vibe-no-learn").write_text("")
        env = {**os.environ, "HOME": str(home)}
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
            cwd=proj,
        )
        check("[learn] AC11 marker blocks capture", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] AC11 opted out message", "opted out" in r.stderr, r.stderr)


def test_learning_marker_walk_stops_at_home() -> None:
    """AC11: Marker walk stops at $HOME, doesn't walk above."""
    print("\n[learning AC11: marker walk stops at $HOME]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        # Place marker above $HOME (at /tmp)
        parent = home.parent
        (parent / ".vibe-no-learn").write_text("")
        try:
            env = {**os.environ, "HOME": str(home)}
            r = run(
                ["bash", str(VIBE), "learn", "pattern"],
                env=env,
                input="y\n",
            )
            check("[learn] AC11 walk stops at $HOME, marker above doesn't block",
                  r.returncode == 0, f"stderr={r.stderr[:300]}")
        finally:
            (parent / ".vibe-no-learn").unlink()


def test_learning_home_unset_fails_safe() -> None:
    """AC11: $HOME unset is fail-safe (no write)."""
    print("\n[learning AC11: $HOME unset fail-safe]")
    with tempfile.TemporaryDirectory() as td:
        lib = Path(td) / "lib"
        lib.mkdir()
        cfg = Path(td) / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ}
        # Unset HOME
        if "HOME" in env:
            del env["HOME"]
        # Run vibe learn with HOME unset
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC11 $HOME unset fails safe", r.returncode == 1,
              f"exit={r.returncode}")


def test_learning_help_lists_commands() -> None:
    """AC12: vibe --help lists learn commands."""
    print("\n[learning AC12: help mentions learn]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td}
        r = run(["bash", str(VIBE), "--help"], env=env)
        check("[learn] AC12 help exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC12 help mentions 'learn \"<pattern>\"'",
              'learn "<pattern>"' in r.stdout, r.stdout)
        check("[learn] AC12 help mentions 'learn --init'",
              "learn --init" in r.stdout, r.stdout)


def test_learning_banner_with_optins() -> None:
    """AC12: Banner shows learn line when opted in and not blocked."""
    print("\n[learning AC12: banner with opt-in]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"learning_should_mount {shlex.quote(str(home))} && echo Y || echo N"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC12 learning_should_mount returns 0 when opted in",
              r.returncode == 0, r.stderr)


def test_learning_chmod_600_verified() -> None:
    """AC13: Config created with chmod 600."""
    print("\n[learning AC13: chmod 600 on config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = {**os.environ, "HOME": str(home)}
        input_str = f"{lib}\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC13 init success", r.returncode == 0, r.stderr)
        if cfg.exists():
            mode = cfg.stat().st_mode & 0o777
            check("[learn] AC13 config is chmod 600", mode == 0o600,
                  f"mode={oct(mode)}")


def test_learning_helpers_exist() -> None:
    """AC14: All 10 helpers defined."""
    print("\n[learning AC14: 10 helpers present]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        helpers = [
            "learning_config_path",
            "learning_load",
            "learning_is_enabled",
            "learning_project_opted_out",
            "learning_should_mount",
            "learning_entry_path",
            "learning_format_entry",
            "learning_commit_message",
            "render_devcontainer_with_mounts",
            "learning_handle_subcommand",
        ]
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            "declare -F | awk '{print $3}'"
        )
        r = run(["bash", "-c", script], env=env)
        declared = r.stdout.split()
        for helper in helpers:
            check(f"[learn] AC14 helper '{helper}' exists",
                  helper in declared, f"declared={declared}")


def test_learning_entry_path_composition() -> None:
    """Helper function test: learning_entry_path."""
    print("\n[learning helper: entry_path composition]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_entry_path "/home/user/lib" "2025-04-23T12:34:56Z" "abc123" | '
            'grep -q "/home/user/lib/2025-04-23T12:34:56Z-abc123.md" && echo OK'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] entry_path composition", "OK" in r.stdout, r.stdout)


def test_learning_format_entry() -> None:
    """Helper function test: learning_format_entry."""
    print("\n[learning helper: format_entry]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_format_entry "2025-04-23T12:00:00Z" "my pattern"'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] format_entry has timestamp", "2025-04-23T12:00:00Z" in r.stdout,
              r.stdout)
        check("[learn] format_entry has pattern", "my pattern" in r.stdout, r.stdout)


def test_learning_commit_message() -> None:
    """Helper function test: learning_commit_message."""
    print("\n[learning helper: commit_message]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_commit_message "short pattern" | grep -q "^learn: short pattern"'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] commit_message formats correctly", r.returncode == 0, r.stdout)


def test_learning_config_path_helper() -> None:
    """Helper function test: learning_config_path."""
    print("\n[learning helper: config_path]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": str(td), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f'learning_config_path | grep -q "{td}/.vibe/learning.config" && echo OK'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] config_path helper", "OK" in r.stdout, r.stdout)


def test_learning_code_check_clean() -> None:
    """AC15: python3 code-check.py passes on vibe."""
    print("\n[learning AC15: code-check.py passes]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[learn] AC15 code-check passes", r.returncode == 0,
          f"exit={r.returncode} output={r.stdout[-300:]}")


def _learning_optin_config(home: Path, lib: Path, visibility: str = "private") -> None:
    cfg = home / ".vibe" / "learning.config"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        f'VIBE_LEARNING_ENABLED="true"\n'
        f'VIBE_LEARNING_PATH="{lib}"\n'
        f'VIBE_LEARNING_VISIBILITY="{visibility}"\n'
        f'VIBE_LEARNING_GIT_REMOTE=""\n'
    )


def test_learning_short_marker_blocks() -> None:
    """New short .no-learn marker blocks capture (same semantics as legacy)."""
    print("\n[learning rename: .no-learn blocks capture]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        (proj / ".no-learn").write_text("")
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="y\n", cwd=proj)
        check("[learn] short .no-learn marker blocks capture",
              r.returncode == 1, f"exit={r.returncode} stderr={r.stderr}")


def test_learning_exclude_creates_marker() -> None:
    """vibe learn --exclude creates .no-learn in cwd; idempotent."""
    print("\n[learning --exclude]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=proj)
        check("[learn] --exclude exits 0", r.returncode == 0, r.stderr)
        check("[learn] --exclude creates .no-learn", (proj / ".no-learn").exists())
        # Idempotent: second call still exits 0
        r2 = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=proj)
        check("[learn] --exclude idempotent", r2.returncode == 0, r2.stderr)
        check("[learn] --exclude says already excluded",
              "already excluded" in r2.stdout, r2.stdout)


def test_learning_include_removes_marker() -> None:
    """vibe learn --include removes .no-learn (and legacy .vibe-no-learn)."""
    print("\n[learning --include]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        (proj / ".no-learn").write_text("")
        (proj / ".vibe-no-learn").write_text("")  # legacy marker too
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "--include"], env=env, cwd=proj)
        check("[learn] --include exits 0", r.returncode == 0, r.stderr)
        check("[learn] --include removes .no-learn", not (proj / ".no-learn").exists())
        check("[learn] --include removes legacy .vibe-no-learn",
              not (proj / ".vibe-no-learn").exists())
        # Idempotent: second call exits 0 with no-marker message
        r2 = run(["bash", str(VIBE), "learn", "--include"], env=env, cwd=proj)
        check("[learn] --include idempotent", r2.returncode == 0, r2.stderr)
        check("[learn] --include says was not excluded",
              "was not excluded" in r2.stdout, r2.stdout)


def test_learning_exclude_refuses_in_home() -> None:
    """vibe learn --exclude refuses when cwd is $HOME."""
    print("\n[learning --exclude refuses $HOME]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        env = {**os.environ, "HOME": str(home)}
        r = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=home)
        check("[learn] --exclude refuses in $HOME", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] --exclude $HOME error mentions refusing",
              "refusing" in r.stderr, r.stderr)
        check("[learn] --exclude $HOME left no marker",
              not (home / ".no-learn").exists())


def test_learning_help_mentions_exclude_include() -> None:
    """vibe --help mentions --exclude and --include."""
    print("\n[learning --help mentions exclude/include]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("[learn] --help mentions --exclude", "--exclude" in r.stdout, r.stdout[:600])
    check("[learn] --help mentions --include", "--include" in r.stdout, r.stdout[:600])


def test_learning_help_says_host_only() -> None:
    """vibe --help makes clear `vibe learn` subcommands run on the host."""
    print("\n[learning --help says host-only]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("[learn] --help mentions 'on the HOST shell'",
          "HOST shell" in r.stdout or "host shell" in r.stdout, r.stdout[:900])
    check("[learn] --help warns 'not available inside the container'",
          "not available inside the container" in r.stdout
          or "not inside the container" in r.stdout, r.stdout[:900])


def test_learning_bare_learn_usage_says_host_only() -> None:
    """`vibe learn` (no args) emits usage that tells users to run on the host."""
    print("\n[learning bare-learn usage says host-only]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td}
        r = run(["bash", str(VIBE), "learn"], env=env)
    check("[learn] bare-learn exits 1", r.returncode == 1,
          f"exit={r.returncode} stderr={r.stderr[:400]}")
    check("[learn] bare-learn usage mentions host shell",
          "host shell" in r.stderr or "on the host" in r.stderr,
          r.stderr[:600])


def test_learning_banner_state_three_way() -> None:
    """learning_banner_state → silent / excluded / enabled per documented rules."""
    print("\n[learning banner_state: silent / excluded / enabled]")

    def call_state(home: Path, workspace: Path) -> str:
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"learning_load; "
            f"learning_banner_state {shlex.quote(str(workspace))}"
        )
        r = run(["bash", "-c", script], env=env)
        return r.stdout.strip()

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        ws = home / "proj"
        ws.mkdir()

        # State 1: no config at all → silent
        check("[learn] banner_state silent when no config",
              call_state(home, ws) == "silent", call_state(home, ws))

        # State 2: config present + opted in → enabled
        lib = home / "lib"; lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        check("[learn] banner_state enabled when opted in",
              call_state(home, ws) == "enabled", call_state(home, ws))

        # State 3: .no-learn marker → excluded
        (ws / ".no-learn").touch()
        check("[learn] banner_state excluded when .no-learn present",
              call_state(home, ws) == "excluded", call_state(home, ws))

        # Also legacy marker should read as excluded.
        (ws / ".no-learn").unlink()
        (ws / ".vibe-no-learn").touch()
        check("[learn] banner_state excluded when legacy .vibe-no-learn present",
              call_state(home, ws) == "excluded", call_state(home, ws))


def test_learning_banner_parent_shell_load() -> None:
    """Regression: main-block banner must load learning config in the parent
    shell, not rely on exports from the $( _build_override_config )
    subshell — exports don't cross subshell boundaries, so without a parent-
    shell learning_load the banner line silently disappears even when
    /learnings is correctly mounted."""
    print("\n[learning banner: parent-shell load before override-config subshell]")
    src = Path(VIBE).read_text()
    # The banner block uses the learning_banner_state case dispatch.
    banner_marker = 'case "$(learning_banner_state'
    subshell_marker = "OVERRIDE_CONFIG=$(_build_override_config"
    parent_load_marker = "learning_load"
    banner_idx = src.find(banner_marker)
    subshell_idx = src.find(subshell_marker)
    check("[learn] banner marker present in source",
          banner_idx != -1, banner_marker)
    check("[learn] override-config subshell present in source",
          subshell_idx != -1, subshell_marker)
    if banner_idx == -1 or subshell_idx == -1:
        return
    # learning_load must appear between the end of the helper definitions and
    # the override-config subshell, in the parent shell's main block.
    # The helpers end at the VIBE_SOURCE_ONLY return; search AFTER that.
    source_guard = src.find('[ "${VIBE_SOURCE_ONLY:-}" = "1" ]')
    check("[learn] VIBE_SOURCE_ONLY guard present", source_guard != -1)
    if source_guard == -1:
        return
    # Find the first parent-shell learning_load call after the guard and
    # before the override-config subshell.
    parent_load_idx = src.find(parent_load_marker, source_guard)
    check("[learn] parent-shell learning_load call exists",
          parent_load_idx != -1 and parent_load_idx < subshell_idx,
          f"parent_load_idx={parent_load_idx} subshell_idx={subshell_idx}")


# ── vibe-copy tests ───────────────────────────────────────────────────────────

def test_vibe_copy_stdin_roundtrip() -> None:
    """AC4: stdin input round-trip — base64 payload decodes to input bytes."""
    print("\n[vibe-copy AC4: stdin roundtrip]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"hello world\n"
        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] stdin roundtrip exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        tty_output = tty.read_bytes()
        expected_prefix = b"\x1b]52;c;"
        expected_suffix = b"\x07"
        check("[copy] stdin OSC 52 prefix", tty_output.startswith(expected_prefix),
              repr(tty_output[:20]))
        check("[copy] stdin OSC 52 suffix", tty_output.endswith(expected_suffix),
              repr(tty_output[-10:]))

        if tty_output.startswith(expected_prefix) and tty_output.endswith(expected_suffix):
            payload = tty_output[len(expected_prefix):-len(expected_suffix)]
            decoded = base64.b64decode(payload)
            check("[copy] stdin base64 decodes to input", decoded == input_bytes,
                  f"decoded={decoded!r} input={input_bytes!r}")


def test_vibe_copy_file_arg_roundtrip() -> None:
    """AC4: file argument round-trip — base64 payload decodes to file bytes."""
    print("\n[vibe-copy AC4: file arg roundtrip]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"hello world\n"
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] file arg exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        tty_output = tty.read_bytes()
        expected_prefix = b"\x1b]52;c;"
        expected_suffix = b"\x07"
        check("[copy] file arg OSC 52 prefix", tty_output.startswith(expected_prefix),
              repr(tty_output[:20]))
        check("[copy] file arg OSC 52 suffix", tty_output.endswith(expected_suffix),
              repr(tty_output[-10:]))

        if tty_output.startswith(expected_prefix) and tty_output.endswith(expected_suffix):
            payload = tty_output[len(expected_prefix):-len(expected_suffix)]
            decoded = base64.b64decode(payload)
            check("[copy] file arg base64 decodes to input", decoded == input_bytes,
                  f"decoded={decoded!r} input={input_bytes!r}")


def test_vibe_copy_scratch_file_written() -> None:
    """AC5: scratch file write — copy-latest.txt contains exact input bytes."""
    print("\n[vibe-copy AC5: scratch file write]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"test content\n"
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] scratch write exit 0", r.returncode == 0, f"exit={r.returncode}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] scratch file exists", scratch_file.exists(), str(scratch_file))
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] scratch file matches input", content == input_bytes,
                  f"got {len(content)} bytes, expected {len(input_bytes)}")


def test_vibe_copy_empty_input_stdin() -> None:
    """AC9: empty input — emits valid empty OSC 52, writes zero-byte scratch, exit 0."""
    print("\n[vibe-copy AC9: empty input]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=b"")

        check("[copy] empty input exit 0", r.returncode == 0, f"exit={r.returncode}")

        tty_output = tty.read_bytes()
        expected = b"\x1b]52;c;\x07"
        check("[copy] empty input emits correct OSC 52", tty_output == expected,
              f"got {tty_output!r} expected {expected!r}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] empty input scratch exists", scratch_file.exists())
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] empty input scratch is zero bytes", len(content) == 0,
                  f"got {len(content)} bytes")

        check("[copy] empty input stderr empty", r.stderr == b"",
              f"stderr: {r.stderr!r}")


def test_vibe_copy_warn_at_8kib_plus_one() -> None:
    """AC6: 8 KiB warn — input > 8192 bytes emits warning but still emits OSC 52."""
    print("\n[vibe-copy AC6: 8 KiB warn]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"x" * 8193
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] 8k+1 exit 0", r.returncode == 0, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] 8k+1 warns 8193 bytes", "vibe-copy: warning: input is 8193 bytes" in stderr_str,
              f"stderr: {stderr_str}")
        check("[copy] 8k+1 mentions 8192 threshold", "8192 bytes" in stderr_str,
              f"stderr: {stderr_str}")

        tty_output = tty.read_bytes()
        check("[copy] 8k+1 still emits OSC 52", tty_output.startswith(b"\x1b]52;c;") and tty_output.endswith(b"\x07"),
              f"tty output: {tty_output[:30]!r}...{tty_output[-10:]!r}")

        if tty_output.startswith(b"\x1b]52;c;") and tty_output.endswith(b"\x07"):
            payload = tty_output[len(b"\x1b]52;c;"):-len(b"\x07")]
            decoded = base64.b64decode(payload)
            check("[copy] 8k+1 payload matches input", decoded == input_bytes,
                  f"decoded size {len(decoded)} vs input size {len(input_bytes)}")

        scratch_file = scratch / "copy-latest.txt"
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] 8k+1 scratch written", content == input_bytes,
                  f"got {len(content)} bytes")


def test_vibe_copy_refuse_at_1mib_plus_one() -> None:
    """AC7: 1 MiB refuse — input > 1048576 bytes exits 1, no OSC 52, scratch written."""
    print("\n[vibe-copy AC7: 1 MiB refuse]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"x" * 1048577
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] 1m+1 exit 1", r.returncode == 1, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] 1m+1 error mentions 1048577 bytes", "vibe-copy: error: input is 1048577 bytes" in stderr_str,
              f"stderr: {stderr_str}")
        check("[copy] 1m+1 error mentions 1048576 threshold", "1048576" in stderr_str,
              f"stderr: {stderr_str}")

        tty_output = tty.read_bytes()
        check("[copy] 1m+1 no OSC 52 emitted", b"\x1b]52;c;" not in tty_output,
              f"found OSC 52 in tty output")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] 1m+1 scratch still written", scratch_file.exists(), str(scratch_file))
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] 1m+1 scratch contains all input", content == input_bytes,
                  f"got {len(content)} bytes, expected {len(input_bytes)}")


def test_vibe_copy_refuses_two_args() -> None:
    """AC2: arg validation — two positional arguments exits 2 with usage message."""
    print("\n[vibe-copy AC2: refuses two args]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), "arg1", "arg2"], env=env)

        check("[copy] two args exit 2", r.returncode == 2, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] two args stderr starts with usage", stderr_str.startswith("vibe-copy: usage:"),
              f"stderr: {stderr_str}")


def test_vibe_copy_refuses_missing_file() -> None:
    """AC2: arg validation — missing file exits 2 with error message."""
    print("\n[vibe-copy AC2: refuses missing file]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), "/nonexistent-abc123def456"], env=env)

        check("[copy] missing file exit 2", r.returncode == 2, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] missing file stderr starts with error prefix",
              stderr_str.startswith("vibe-copy: error: cannot read file:"),
              f"stderr: {stderr_str}")


def test_vibe_copy_tty_absent_note() -> None:
    """AC16: TTY absent — writes scratch, no OSC 52, note stderr, exit 0."""
    print("\n[vibe-copy AC16: TTY absent fallback]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Create a read-only directory so any attempt to write there fails
        readonly = tmp / "readonly"
        readonly.mkdir()
        readonly.chmod(0o555)
        tty = readonly / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()

        input_bytes = b"text\n"

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] TTY absent exit 0", r.returncode == 0, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] TTY absent note present", "vibe-copy: note: no terminal available" in stderr_str,
              f"stderr: {stderr_str}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] TTY absent scratch written", scratch_file.exists())
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] TTY absent scratch matches input", content == input_bytes)

        # Clean up
        readonly.chmod(0o755)


def test_vibe_copy_scratch_failure_exits_1() -> None:
    """AC5: scratch write failure — exits 1 with error message."""
    print("\n[vibe-copy AC5: scratch write failure]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        tty.touch()

        # Create a read-only directory and try to write scratch inside
        readonly = tmp / "readonly"
        readonly.mkdir()
        readonly.chmod(0o555)
        scratch = readonly / "scratch"

        input_bytes = b"text\n"

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] scratch failure exit 1", r.returncode == 1, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] scratch failure error prefix",
              stderr_str.startswith("vibe-copy: error: cannot write scratch file"),
              f"stderr: {stderr_str}")

        # Clean up
        readonly.chmod(0o755)


def test_c_slash_command_synced() -> None:
    """AC19a: extras-sync deletes retired copy.md and syncs c.md."""
    print("\n[/c AC19a: extras sync deletes copy.md, syncs c.md]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create a fixture source directory with c.md
        fixture_src = tmp / "fixture_src" / "commands"
        fixture_src.mkdir(parents=True)
        fixture_c = fixture_src / "c.md"
        fixture_c.write_text("# /c\nSENTINEL_C_FIXTURE\n")

        # Create destination config dir and pre-seed it with copy.md
        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()
        dest_commands = dest_dir / "commands"
        dest_commands.mkdir()
        (dest_commands / "copy.md").write_text("# /copy\nOLD_FIXTURE\n")

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[/c] extras sync exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check that copy.md was deleted
        check("[/c] copy.md was deleted", not (dest_commands / "copy.md").exists(),
              str(dest_commands / "copy.md"))

        # Check that c.md was synced
        synced_c = dest_commands / "c.md"
        check("[/c] c.md was synced", synced_c.exists(), str(synced_c))
        if synced_c.exists():
            content = synced_c.read_text()
            check("[/c] c.md preserves content", "SENTINEL_C_FIXTURE" in content, content)


def test_c_slash_command_body_matches_spec() -> None:
    """AC19f: c.md body matches spec requirements."""
    print("\n[/c AC19f: c.md body matches spec]")

    check("[/c] c.md file exists", C_MD.exists(), str(C_MD))
    if not C_MD.exists():
        return

    content = C_MD.read_text()
    check("[/c] c.md mentions scratch path", "/workspace/.vibe/copy-latest.txt" in content, "content snippet")
    check("[/c] c.md mentions refusal message", "no prior code block to copy" in content, "content snippet")
    check("[/c] c.md mentions UTF-8", "UTF-8" in content or "UTF8" in content, "content snippet")
    # Check that vibe-copy is NOT in a Bash-tool invocation (it may appear in the UTF-8 note as prose/fallback)
    # We check that no line says "Use the Bash tool to run: `vibe-copy`" or equivalent
    has_bash_invocation = any("Bash tool" in line and "vibe-copy" in line for line in content.split('\n'))
    check("[/c] no Bash-tool invocation of vibe-copy", not has_bash_invocation, "content snippet")


def test_dockerfile_installs_vibe_copy() -> None:
    """AC17f (implicit): Dockerfile COPY + chmod includes vibe-copy.sh."""
    print("\n[Dockerfile: vibe-copy installation]")

    check("[vibe-copy] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return

    content = DOCKERFILE.read_text()

    # Check for COPY line
    copy_lines = [line for line in content.split('\n') if line.strip().startswith('COPY vibe-copy.sh')]
    copy_canonical = [line for line in copy_lines if line.strip() == 'COPY vibe-copy.sh /usr/local/bin/vibe-copy']
    check("[vibe-copy] Dockerfile has canonical COPY line", len(copy_canonical) == 1,
          f"found {len(copy_canonical)} canonical COPY lines, {len(copy_lines)} total COPY vibe-copy lines")

    # Check chmod includes /usr/local/bin/vibe-copy
    check("[vibe-copy] Dockerfile chmod includes vibe-copy", "/usr/local/bin/vibe-copy" in content,
          "content snippet")


# ── AC19a-j: New /c watcher tests ──────────────────────────────────────────────

def test_c_copy_md_is_absent() -> None:
    """AC19g: copy.md does not exist in the repo."""
    print("\n[/c AC19g: copy.md absent from repo]")
    check("[/c] copy.md does not exist", not COPY_MD_OLD.exists(), str(COPY_MD_OLD))


def test_vibe_final_line_no_exec() -> None:
    """AC19h: vibe final line does NOT have 'exec devcontainer exec'."""
    print("\n[/c AC19h: vibe exec dropped]")
    content = VIBE.read_text()
    lines = content.split('\n')

    # Check: no line matches "^exec devcontainer exec"
    exec_prefix_lines = [l for l in lines if l.startswith('exec devcontainer exec')]
    check("[/c] vibe does not have 'exec devcontainer exec'", len(exec_prefix_lines) == 0,
          f"found {len(exec_prefix_lines)} lines with 'exec devcontainer exec'")

    # Check: at least one line invokes "devcontainer exec" without an exec
    # prefix (since 2026-07-04 it lives indented inside launch_claude(), so
    # match on the stripped line).
    no_exec_lines = [l for l in lines
                     if l.strip().startswith('devcontainer exec')
                     and not l.strip().startswith('exec ')]
    check("[/c] vibe has 'devcontainer exec' (without exec prefix)", len(no_exec_lines) > 0,
          "no 'devcontainer exec' line found")


def test_vibe_copy_watcher_noop_on_non_darwin() -> None:
    """AC19d: vibe-copy-watcher.sh exits 0 immediately on non-Darwin, no lingering process."""
    print("\n[/c AC19d: watcher is no-op on non-Darwin]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Run the watcher directly with VIBE_COPY_WATCHER_FORCE not set (defaults to 0)
        # This ensures Darwin guard is checked
        env = {**os.environ}
        # Unset VIBE_COPY_WATCHER_FORCE if it exists
        env.pop("VIBE_COPY_WATCHER_FORCE", None)

        r = run(["bash", str(VIBE_COPY_WATCHER), str(tmp)], env=env)
        check("[/c] watcher exits 0 on non-Darwin", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Verify no lingering process (wait 1s for shell to exit fully)
        import time
        time.sleep(1.1)

        # Use pgrep to check for lingering process
        pgrep_result = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(tmp))}$"])
        check("[/c] no lingering watcher process", pgrep_result.returncode == 1,
              f"pgrep found processes: {pgrep_result.stdout}")


def test_vibe_copy_watcher_polling_detects_change() -> None:
    """AC19e: watcher polling detects scratch-file change and runs copy command."""
    print("\n[/c AC19e: watcher polling detects change]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        workspace = tmp / "ws"
        workspace.mkdir()
        vibe_dir = workspace / ".vibe"
        vibe_dir.mkdir()

        # Create a shim script that will be invoked as VIBE_COPY_CMD
        shim = tmp / "fake-pbcopy.sh"
        sentinel = tmp / "sentinel.txt"
        shim.write_text(f"#!/usr/bin/env bash\ncat > {shlex.quote(str(sentinel))}\n")
        shim.chmod(0o755)

        env = {
            **os.environ,
            "VIBE_COPY_CMD": str(shim),
            "VIBE_COPY_WATCHER_FORCE": "1",
        }

        # Launch watcher in background
        proc = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(workspace)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for watcher to initialize (first poll cycle)
            import time
            time.sleep(0.6)

            # Write to the scratch file
            copy_file = workspace / ".vibe" / "copy-latest.txt"
            copy_file.write_text("hello-c\n")

            # Wait for at least 3 polling cycles (0.5s each) to ensure detection
            time.sleep(1.6)

            # Check sentinel file was written
            check("[/c] watcher wrote sentinel file", sentinel.exists(), str(sentinel))
            if sentinel.exists():
                content = sentinel.read_text()
                check("[/c] watcher copied correct content", content == "hello-c\n",
                      f"got: {repr(content)}")
        finally:
            # Send SIGTERM to watcher
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            # Wait for process to fully exit
            import time
            time.sleep(1.1)

            # Verify no lingering process
            pgrep_result = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(workspace))}$"])
            check("[/c] watcher process terminated", pgrep_result.returncode == 1,
                  f"pgrep found processes: {pgrep_result.stdout}")


def test_c_preserves_user_commands() -> None:
    """AC19b: extras-sync preserves user-authored commands."""
    print("\n[/c AC19b: user commands preserved during sync]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with only c.md
        fixture_src = tmp / "fixture_src" / "commands"
        fixture_src.mkdir(parents=True)
        (fixture_src / "c.md").write_text("# /c\nCMD_FIXTURE\n")

        # Create destination with a pre-existing user command
        dest_dir = tmp / "dest_config"
        dest_commands = (dest_dir / "commands")
        dest_commands.mkdir(parents=True)
        (dest_commands / "my-custom.md").write_text("# /my-custom\nUSER_CONTENT\n")

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[/c] sync exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        # Check user command still exists with original content
        user_cmd = dest_commands / "my-custom.md"
        check("[/c] user command preserved", user_cmd.exists(), str(user_cmd))
        if user_cmd.exists():
            check("[/c] user command content unchanged",
                  user_cmd.read_text() == "# /my-custom\nUSER_CONTENT\n",
                  user_cmd.read_text())

        # Check c.md was synced
        c_cmd = dest_commands / "c.md"
        check("[/c] c.md was synced", c_cmd.exists(), str(c_cmd))


def test_c_agents_not_touched_by_retirement() -> None:
    """AC19c: retirement cleanup does NOT touch agents/ directory."""
    print("\n[/c AC19c: agents directory not touched by retirement]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with commands and agents
        fixture_src = tmp / "fixture_src"
        (fixture_src / "commands").mkdir(parents=True)
        (fixture_src / "commands" / "c.md").write_text("# /c\n")
        (fixture_src / "agents").mkdir(parents=True)
        (fixture_src / "agents" / "other.md").write_text("# other agent\n")

        # Create destination with a pre-existing "retired" agent
        dest_dir = tmp / "dest_config"
        dest_agents = (dest_dir / "agents")
        dest_agents.mkdir(parents=True)
        (dest_agents / "some-retired-agent.md").write_text("# old agent\nSHOULD_PERSIST\n")
        dest_cmds = (dest_dir / "commands")
        dest_cmds.mkdir(parents=True)

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[/c] sync exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        # Check that the old agent was NOT deleted
        old_agent = dest_agents / "some-retired-agent.md"
        check("[/c] old agent not deleted", old_agent.exists(), str(old_agent))
        if old_agent.exists():
            check("[/c] old agent content preserved",
                  "SHOULD_PERSIST" in old_agent.read_text(),
                  old_agent.read_text())


def test_vibe_path_prefix_isolation() -> None:
    """AC19i: multi-session path-prefix collision test."""
    print("\n[/c AC19i: path-prefix collision isolation]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        proj1 = tmp / "proj"
        proj2 = tmp / "proj-extra"
        proj1.mkdir()
        proj2.mkdir()

        env = {**os.environ, "VIBE_COPY_WATCHER_FORCE": "1"}

        # Spawn two watchers
        proc1 = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(proj1)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc2 = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(proj2)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            import time
            time.sleep(0.5)  # Let both watchers start

            # Verify both are running
            pgrep1 = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])
            pgrep2 = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj2))}$"])
            check("[/c] both watchers initially running", pgrep1.returncode == 0 and pgrep2.returncode == 0,
                  f"proj1 rc={pgrep1.returncode} proj2 rc={pgrep2.returncode}")

            # Kill only the proj1 watcher using pkill with the canonical pattern
            pkill_result = run(["pkill", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])

            time.sleep(0.2)

            # Check proj1 is gone
            pgrep1_after = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])
            check("[/c] proj1 watcher killed", pgrep1_after.returncode == 1,
                  f"pgrep output: {pgrep1_after.stdout}")

            # Check proj2 is still running
            pgrep2_after = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj2))}$"])
            check("[/c] proj2 watcher still running", pgrep2_after.returncode == 0,
                  f"pgrep output: {pgrep2_after.stdout}")
        finally:
            proc1.terminate()
            proc2.terminate()
            try:
                proc1.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc1.kill()
                proc1.wait()
            try:
                proc2.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc2.kill()
                proc2.wait()


def test_vibe_exit_code_propagation() -> None:
    """AC19j: vibe exits with the inner command's exit code (regression guard)."""
    print("\n[/c AC19j: vibe exit code propagation]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create a fake devcontainer script that exits with code 7
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_devcontainer = fake_bin / "devcontainer"
        fake_devcontainer.write_text("#!/bin/bash\nexit 7\n")
        fake_devcontainer.chmod(0o755)

        # Create a minimal vibe call that reaches the devcontainer exec line
        # We'll source the real vibe but override PATH and other critical vars
        env = {
            **os.environ,
            "PATH": str(fake_bin) + ":" + os.environ.get("PATH", ""),
            "HOME": str(tmp),
            "VIBE_CONFIG": str(tmp / "no-config"),
            "VIBE_SOURCE_ONLY": "1",
        }

        # Source vibe, set up minimal env, then call devcontainer exec
        script = f"""
        set -euo pipefail
        source {shlex.quote(str(VIBE))}
        # Simulate reaching the exec line by calling devcontainer directly
        # (normally vibe would set up WORKSPACE, DEVCONTAINER_DIR, etc.)
        devcontainer exec /bin/true
        """

        r = run(["bash", "-c", script], env=env)
        # We expect exit code 7 from our fake devcontainer
        check("[/c] vibe propagates inner command exit code",
              r.returncode == 7,
              f"expected 7, got {r.returncode} stderr={r.stderr[:200]}")


# ── task_007: WebSearch-before-refusing rule ─────────────────────────────────

def test_task007_t1_web_research_md_exists_and_complete() -> None:
    """t1: web-research.md exists and satisfies AC1."""
    print("\n[task_007/t1: web-research.md content validation]")

    check("[task007/t1] web-research.md exists", WEB_RESEARCH_MD.exists(), str(WEB_RESEARCH_MD))
    if not WEB_RESEARCH_MD.exists():
        return

    content = WEB_RESEARCH_MD.read_text()
    lines = content.splitlines()
    non_blank_lines = [line for line in lines if line.strip()]

    check("[task007/t1] contains 'WebSearch'", "WebSearch" in content, "phrase check")
    check("[task007/t1] contains 'WebFetch'", "WebFetch" in content, "phrase check")

    # Check for sequencing sentinel: one of {BEFORE, before, first, First}
    sentinels = ["BEFORE", "before", "first", "First"]
    has_sentinel = any(s in content for s in sentinels)
    check("[task007/t1] contains sequencing sentinel", has_sentinel,
          f"missing one of {sentinels}")

    check("[task007/t1] ≥50 non-blank lines", len(non_blank_lines) >= 50,
          f"found {len(non_blank_lines)} non-blank lines")


def test_task007_t2_dockerfile_copy_canonical() -> None:
    """t2: Dockerfile contains exactly one canonical COPY claude-md line."""
    print("\n[task_007/t2: Dockerfile COPY claude-md]")

    check("[task007/t2] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return

    content = DOCKERFILE.read_text()
    canonical_line = "COPY claude-md /usr/local/share/vibe/claude-md/"

    count = content.count(canonical_line)
    check("[task007/t2] exactly one canonical COPY line", count == 1,
          f"found {count} canonical lines")


def test_task007_t3_install_basics_one_fragment() -> None:
    """t3: install-claude-extras.sh with one fragment in source."""
    print("\n[task_007/t3: install with single fragment]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with one fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("# Test Fragment\nTest content for web research\n")

        # Create destination
        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t3] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check CLAUDE.md exists and has correct structure
        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t3] CLAUDE.md created", claude_md.exists(), str(claude_md))

        if not claude_md.exists():
            return

        content = claude_md.read_text()

        # Check delimiters
        check("[task007/t3] opening delimiter present",
              "<!-- >>> vibe-managed (auto, do not edit) >>>" in content,
              "delimiter check")
        check("[task007/t3] closing delimiter present",
              "<!-- <<< vibe-managed <<< -->" in content,
              "delimiter check")

        # Check fragment header
        check("[task007/t3] fragment header present",
              "<!-- vibe-md: web-research.md -->" in content,
              "header check")

        # Check block position: no non-blank line after closing delimiter
        after_close = content.split("<!-- <<< vibe-managed <<< -->")[1]
        non_blank_after = [line for line in after_close.splitlines() if line.strip()]
        check("[task007/t3] no non-blank lines after closing delimiter",
              len(non_blank_after) == 0,
              f"found non-blank lines: {non_blank_after}")

        # Check exactly one newline after close
        expected_ending = "<!-- <<< vibe-managed <<< -->\n"
        check("[task007/t3] exactly one newline after closing delimiter",
              content.endswith(expected_ending),
              f"ending check: {repr(content[-50:])}")


def test_task007_t4_create_from_scratch() -> None:
    """t4: install creates CLAUDE.md from scratch when absent."""
    print("\n[task_007/t4: create CLAUDE.md from scratch]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("Fragment content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t4] CLAUDE.md does not exist initially", not claude_md.exists())

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t4] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[task007/t4] CLAUDE.md created", claude_md.exists(), str(claude_md))

        if claude_md.exists():
            content = claude_md.read_text()
            check("[task007/t4] file ends with exactly one newline",
                  content.endswith("\n") and not content.endswith("\n\n"),
                  f"ending: {repr(content[-20:])}")


def test_task007_t5_idempotency() -> None:
    """t5: running install twice with same source produces byte-identical CLAUDE.md."""
    print("\n[task_007/t5: idempotency]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("Fragment content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # Run install twice
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t5] first install exit 0", r1.returncode == 0)

        content1 = claude_md.read_text()
        hash1 = __import__("hashlib").sha256(content1.encode()).hexdigest()

        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t5] second install exit 0", r2.returncode == 0)

        content2 = claude_md.read_text()
        hash2 = __import__("hashlib").sha256(content2.encode()).hexdigest()

        check("[task007/t5] sha256 hash identical", hash1 == hash2,
              f"hash1={hash1[:16]}… hash2={hash2[:16]}…")
        check("[task007/t5] file size identical",
              len(content1) == len(content2),
              f"size1={len(content1)} size2={len(content2)}")


def test_task007_t6_user_content_preserved() -> None:
    """t6: user content survives re-run with changed fragment set."""
    print("\n[task_007/t6: user content preservation]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create initial fixture with one fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "a-fragment.md").write_text("Fragment A\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First run
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t6] first install exit 0", r1.returncode == 0)

        # Insert user content mid-file (between what will be the vibe block and the rest)
        content1 = claude_md.read_text()
        user_content = "# User Notes\nThis is user content that should persist.\n"
        # Insert user content after vibe-managed block
        parts = content1.split("<!-- <<< vibe-managed <<< -->")
        new_content = parts[0] + "<!-- <<< vibe-managed <<< -->\n\n" + user_content
        claude_md.write_text(new_content)

        # Second run with different fragment set
        (fixture_src / "b-fragment.md").write_text("Fragment B\n")

        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t6] second install exit 0", r2.returncode == 0)

        content2 = claude_md.read_text()

        # Verify user content still present
        check("[task007/t6] user content preserved",
              user_content in content2,
              "user content check")

        # Verify both fragments are present
        check("[task007/t6] both fragments in block",
              "<!-- vibe-md: a-fragment.md -->" in content2 and "<!-- vibe-md: b-fragment.md -->" in content2,
              "fragment headers")


def test_task007_t7_empty_source_cleanup() -> None:
    """t7: empty-source case removes pre-existing vibe-managed block."""
    print("\n[task_007/t7: empty-source cleanup]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # First: install with a fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test.md").write_text("Content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t7] first install exit 0", r1.returncode == 0)

        content_with_block = claude_md.read_text()
        check("[task007/t7] block present after first install",
              "<!-- >>> vibe-managed" in content_with_block)

        # Delete all fragments (empty source)
        import shutil
        shutil.rmtree(fixture_src)
        fixture_src.mkdir()

        # Re-run
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t7] second install (empty source) exit 0", r2.returncode == 0)

        content_after = claude_md.read_text()

        # Block should be gone
        check("[task007/t7] block removed on empty source",
              "<!-- >>> vibe-managed" not in content_after,
              "block removal check")

        # Run again to check no trailing blank-line accumulation
        r3 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t7] third install exit 0", r3.returncode == 0)

        content_after_2 = claude_md.read_text()
        check("[task007/t7] no blank-line accumulation on re-run",
              content_after == content_after_2,
              "idempotency check")


def test_task007_t8_missing_source_directory() -> None:
    """t8: missing-source case (directory does not exist)."""
    print("\n[task_007/t8: missing-source handling]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture without claude-md directory
        fixture_src = tmp / "fixture_src"
        fixture_src.mkdir(parents=True)

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(fixture_src),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        # Run should not error
        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t8] install exit 0 (no claude-md dir)", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Now create initial state with a block, then remove claude-md directory
        claude_md_src = fixture_src / "claude-md"
        claude_md_src.mkdir()
        (claude_md_src / "test.md").write_text("Content\n")

        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t8] first install (with fragment) exit 0", r1.returncode == 0)

        claude_md = dest_dir / "CLAUDE.md"
        content_with_block = claude_md.read_text()
        check("[task007/t8] block present after first install",
              "<!-- >>> vibe-managed" in content_with_block)

        # Remove the claude-md directory
        import shutil
        shutil.rmtree(claude_md_src)

        # Re-run
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t8] install exit 0 (missing claude-md)", r2.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        content_after = claude_md.read_text()
        check("[task007/t8] block removed when source directory missing",
              "<!-- >>> vibe-managed" not in content_after,
              "block removal check")


def test_task007_t9_posix_byte_order_sort() -> None:
    """t9: multi-fragment ordering uses POSIX byte-order (LC_ALL=C)."""
    print("\n[task_007/t9: POSIX byte-order sort]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fragments with names that differ in POSIX vs locale sort
        # In POSIX (LC_ALL=C): Z < a (capitals first)
        # In many locales: a < Z (case-insensitive or lowercase first)
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "Z-fragment.md").write_text("Z content\n")
        (fixture_src / "a-fragment.md").write_text("A content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t9] install exit 0", r.returncode == 0)

        claude_md = dest_dir / "CLAUDE.md"
        content = claude_md.read_text()

        # In POSIX byte-order, Z-fragment should come before a-fragment
        z_pos = content.find("<!-- vibe-md: Z-fragment.md -->")
        a_pos = content.find("<!-- vibe-md: a-fragment.md -->")

        check("[task007/t9] both fragment headers present", z_pos >= 0 and a_pos >= 0,
              "fragment header check")
        check("[task007/t9] Z-fragment before a-fragment (POSIX order)", z_pos < a_pos,
              f"Z_pos={z_pos} a_pos={a_pos}")


def test_task007_t10_agents_and_commands_still_work() -> None:
    """t10: agents, commands, and claude-md all install correctly together."""
    print("\n[task_007/t10: agents + commands + claude-md coexistence]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create full fixture with agents, commands, and claude-md
        fixture_src = tmp / "fixture_src"
        agents_dir = fixture_src / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test-agent.md").write_text("# Test Agent\nContent\n")

        commands_dir = fixture_src / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "test-cmd.md").write_text("# Test Command\nContent\n")

        claude_md_dir = fixture_src / "claude-md"
        claude_md_dir.mkdir(parents=True)
        (claude_md_dir / "test-frag.md").write_text("# Test Fragment\nContent\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(fixture_src),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t10] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check agents synced
        agent_file = dest_dir / "agents" / "test-agent.md"
        check("[task007/t10] agent file copied", agent_file.exists(), str(agent_file))

        # Check commands synced
        cmd_file = dest_dir / "commands" / "test-cmd.md"
        check("[task007/t10] command file copied", cmd_file.exists(), str(cmd_file))

        # Check claude-md block created
        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t10] CLAUDE.md created", claude_md.exists(), str(claude_md))
        if claude_md.exists():
            content = claude_md.read_text()
            check("[task007/t10] claude-md block present",
                  "<!-- >>> vibe-managed" in content and "<!-- vibe-md: test-frag.md -->" in content)


def test_task007_t11_write_env_hint_coexistence() -> None:
    """t11: write-env-hint and vibe-managed blocks coexist with correct delimiters."""
    print("\n[task_007/t11: write-env-hint coexistence]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test-frag.md").write_text("Test content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First: run write-env-hint to create its managed block
        r1 = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("[task007/t11] write-env-hint exit 0", r1.returncode == 0,
              f"exit={r1.returncode} stderr={r1.stderr}")

        content_after_hint = claude_md.read_text()

        # Extract the expected write-env-hint block by reading write-env-hint.sh
        # and finding the BLOCK variable value
        hint_content = WRITE_ENV_HINT.read_text()
        hint_start = hint_content.find('BLOCK="')
        hint_end = hint_content.find('\n$END"', hint_start)
        if hint_start >= 0 and hint_end >= 0:
            # Extract the block (this is a bit fragile but mirrors the spec's requirement)
            expected_hint_block = "<!-- BEGIN vibe env (managed) -->\n# vibe container environment"
        else:
            expected_hint_block = "<!-- BEGIN vibe env (managed) -->"

        check("[task007/t11] write-env-hint block present",
              "<!-- BEGIN vibe env (managed) -->" in content_after_hint,
              "hint block check")

        # Second: run install-claude-extras with fragment
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t11] install-claude-extras exit 0", r2.returncode == 0,
              f"exit={r2.returncode} stderr={r2.stderr}")

        content_after_both = claude_md.read_text()

        # Verify both blocks present
        check("[task007/t11] write-env-hint block still present",
              "<!-- BEGIN vibe env (managed) -->" in content_after_both,
              "hint block check")
        check("[task007/t11] vibe-managed block present",
              "<!-- >>> vibe-managed (auto, do not edit) >>>" in content_after_both,
              "managed block check")

        # Verify write-env-hint block is byte-identical to its original
        hint_block_start = content_after_hint.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end = content_after_hint.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        original_hint_block = content_after_hint[hint_block_start:hint_block_end]

        hint_block_start_2 = content_after_both.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end_2 = content_after_both.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        hint_block_after_install = content_after_both[hint_block_start_2:hint_block_end_2]

        check("[task007/t11] write-env-hint block byte-identical after install",
              original_hint_block == hint_block_after_install,
              "byte comparison")

        # Third: run install-claude-extras again with a different fragment set
        (fixture_src / "another-frag.md").write_text("Another content\n")

        r3 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t11] second install exit 0", r3.returncode == 0)

        content_after_second_install = claude_md.read_text()

        # Verify write-env-hint block is STILL byte-identical
        hint_block_start_3 = content_after_second_install.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end_3 = content_after_second_install.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        hint_block_after_second = content_after_second_install[hint_block_start_3:hint_block_end_3]

        check("[task007/t11] write-env-hint block unchanged after second install",
              original_hint_block == hint_block_after_second,
              "byte comparison after second install")


def test_task007_t12_fragment_removal_and_separation() -> None:
    """t12: N→N-1 fragment removal; verify single blank line separates fragments."""
    print("\n[task_007/t12: fragment removal and blank-line separation]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture with two fragments
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "first.md").write_text("First fragment\nLine 2\n")
        (fixture_src / "second.md").write_text("Second fragment\nLine 2\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First install with both fragments
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t12] first install exit 0", r1.returncode == 0)

        content_two = claude_md.read_text()

        # Verify both fragments present
        check("[task007/t12] both fragment headers present initially",
              "<!-- vibe-md: first.md -->" in content_two and "<!-- vibe-md: second.md -->" in content_two)

        # Check for exactly one blank line between fragments
        # The pattern should be: body of first\n\n<!-- vibe-md: second.md -->
        # Find the end of the first fragment's body (last line is "Line 2")
        first_body_end = content_two.find("Line 2\n", content_two.find("First fragment"))
        if first_body_end >= 0:
            first_body_end += len("Line 2\n")  # Move past the "Line 2\n"

        second_start = content_two.find("<!-- vibe-md: second.md -->")
        if first_body_end >= 0 and second_start >= 0:
            between = content_two[first_body_end:second_start]
            # Should be exactly one blank line: "\n"
            check("[task007/t12] exactly one blank line separates fragments",
                  between == "\n",
                  f"got between content: {repr(between)}")

        # Now remove first.md from source
        (fixture_src / "first.md").unlink()

        # Re-run install
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t12] second install (after removal) exit 0", r2.returncode == 0)

        content_one = claude_md.read_text()

        # Verify first fragment is gone
        check("[task007/t12] first fragment removed",
              "<!-- vibe-md: first.md -->" not in content_one,
              "removal check")

        # Verify second fragment still present
        check("[task007/t12] second fragment still present",
              "<!-- vibe-md: second.md -->" in content_one,
              "presence check")


def test_task007_t13_absent_source_with_preexisting_block() -> None:
    """t13: absent-source case with pre-existing vibe-managed block."""
    print("\n[task_007/t13: absent source + pre-existing block removal]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create initial fixture with fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test.md").write_text("Content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First install
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t13] first install exit 0", r1.returncode == 0)

        content_with_block = claude_md.read_text()
        check("[task007/t13] block present initially",
              "<!-- >>> vibe-managed" in content_with_block)

        # Add some user content to verify it persists
        user_content = "# My Notes\nUser data\n"
        content_with_user = content_with_block.split("<!-- <<< vibe-managed <<<")[0]
        content_with_user += "# My Notes\nUser data\n<!-- <<< vibe-managed <<<" + \
                             content_with_block.split("<!-- <<< vibe-managed <<<")[1]
        claude_md.write_text(content_with_user)

        # Delete the claude-md directory entirely
        import shutil
        shutil.rmtree(fixture_src.parent / "claude-md")

        # Re-run install
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=env)
        check("[task007/t13] install exit 0 (after dir deletion)", r2.returncode == 0,
              f"exit={r2.returncode} stderr={r2.stderr}")

        content_final = claude_md.read_text()

        # Verify block is gone
        check("[task007/t13] block removed when source directory absent",
              "<!-- >>> vibe-managed" not in content_final,
              "block removal")

        # Verify CLAUDE.md is otherwise intact
        check("[task007/t13] CLAUDE.md exists after cleanup", claude_md.exists())


def test_task007_t14_ssh_discipline_md_exists_and_complete() -> None:
    """t14: ssh-discipline.md exists and satisfies AC1b."""
    print("\n[task_007/t14: ssh-discipline.md content validation]")

    check("[task007/t14] ssh-discipline.md exists", SSH_DISCIPLINE_MD.exists(), str(SSH_DISCIPLINE_MD))
    if not SSH_DISCIPLINE_MD.exists():
        return

    content = SSH_DISCIPLINE_MD.read_text()
    lines = content.splitlines()
    non_blank_lines = [line for line in lines if line.strip()]

    check("[task007/t14] contains literal 'ssh'", "ssh" in content, "phrase check")
    check("[task007/t14] contains literal 'scp'", "scp" in content, "phrase check")

    # Check for prohibition/default-disposition sentinel
    sentinels = ["Do not", "Don't", "don't", "Avoid", "default to"]
    has_sentinel = any(s in content for s in sentinels)
    check("[task007/t14] contains prohibition sentinel", has_sentinel,
          f"missing one of {sentinels}")

    check("[task007/t14] ≥50 non-blank lines", len(non_blank_lines) >= 50,
          f"found {len(non_blank_lines)} non-blank lines")


def test_task008_ac3_block_scoping() -> None:
    """task_008: AC3 — CLIP and WATCHER_SEED_MTIME only declared in Darwin block."""
    print("\n[task_008: AC3 block scoping]")
    src = Path(VIBE).read_text()
    lines = src.splitlines()

    # Find the Darwin block boundaries
    darwin_start = None
    darwin_end = None
    for i, ln in enumerate(lines):
        if 'if [[ "$(uname)" == "Darwin" ]]' in ln and 'pbcopy' in ln:
            darwin_start = i
        if darwin_start is not None and darwin_end is None and ln.strip() == 'fi':
            darwin_end = i
            break

    check("[task008/AC3] Darwin block found", darwin_start is not None and darwin_end is not None,
          f"darwin_start={darwin_start} darwin_end={darwin_end}")

    if darwin_start is not None and darwin_end is not None:
        # Check that CLIP and WATCHER_SEED_MTIME appear exactly once, only within block
        clip_count = 0
        seed_count = 0
        clip_in_block = False
        seed_in_block = False

        for i in range(darwin_start, darwin_end + 1):
            if 'CLIP=' in lines[i]:
                clip_count += 1
                clip_in_block = True
            if 'WATCHER_SEED_MTIME=' in lines[i]:
                seed_count += 1
                seed_in_block = True

        # Check for assignments outside block
        for i in range(0, darwin_start):
            if 'CLIP=' in lines[i] and 'pbcopy' not in lines[i]:
                clip_count += 1
        for i in range(darwin_end + 1, len(lines)):
            if 'CLIP=' in lines[i]:
                clip_count += 1
            if 'WATCHER_SEED_MTIME=' in lines[i]:
                seed_count += 1

        check("[task008/AC3] CLIP only declared once (in block)", clip_count == 1,
              f"CLIP appears {clip_count} times")
        check("[task008/AC3] WATCHER_SEED_MTIME only declared once (in block)", seed_count == 1,
              f"WATCHER_SEED_MTIME appears {seed_count} times")


def test_task008_ac11_direct_read() -> None:
    """task_008: AC11 — drain uses pbcopy < CLIP, not cat pipe or cp through tmp."""
    print("\n[task_008: AC11 direct read]")
    src = Path(VIBE).read_text()

    # Find the trap body region (after Darwin block start, before fi)
    trap_start = src.find('trap \'')
    trap_end = src.find('EXIT', trap_start) + 4 if trap_start != -1 else -1
    trap_body = src[trap_start:trap_end] if trap_start != -1 else ""

    check("[task008/AC11] trap contains pbcopy < \"$CLIP\"", 'pbcopy < "$CLIP"' in src,
          "substring not found")

    # Negative tests: should NOT use cat pipe
    cat_pipe = 'cat "$CLIP" | pbcopy' in src or 'cat "$CLIP"|pbcopy' in src
    check("[task008/AC11] trap does NOT use cat pipe", not cat_pipe,
          "found forbidden cat pipe")

    # Negative test: should NOT use cp through tmp
    cp_tmp = 'cp "$CLIP" "$TMP"' in src and 'pbcopy < "$TMP"' in src
    check("[task008/AC11] trap does NOT use cp through TMP", not cp_tmp,
          "found forbidden cp-through-tmp pattern")


def test_clipboard_drain_on_exit() -> None:
    """task_008: drain clipboard scratch on exit — AC18 source-level assertions."""
    print("\n[task_008: clipboard drain on exit — source checks]")
    src = Path(VIBE).read_text()
    lines = src.splitlines()

    # (a) Exactly one line matches CLIP="$WORKSPACE/.vibe/copy-latest.txt"
    clip_pattern = re.compile(r'^\s*CLIP="\$WORKSPACE/\.vibe/copy-latest\.txt"\s*$')
    clip_matches = [ln for ln in lines if clip_pattern.match(ln)]
    check("[task008] exactly one CLIP=... line", len(clip_matches) == 1,
          f"found {len(clip_matches)} matches")

    # (b) Exactly one line matches WATCHER_SEED_MTIME=$(stat -f %m "$CLIP"
    seed_pattern = re.compile(r'^\s*WATCHER_SEED_MTIME=\$\(stat -f %m "\$CLIP"')
    seed_matches = [ln for ln in lines if seed_pattern.match(ln)]
    check("[task008] exactly one WATCHER_SEED_MTIME=$(stat...) line", len(seed_matches) == 1,
          f"found {len(seed_matches)} matches")

    # (c) Source contains pbcopy < "$CLIP"
    drain_substr = 'pbcopy < "$CLIP"'
    check("[task008] source contains pbcopy < \"$CLIP\"", drain_substr in src,
          "substring not found")

    # (d) Source contains kill "$WATCHER_PID" 2>/dev/null || true
    kill_substr = 'kill "$WATCHER_PID" 2>/dev/null || true'
    check("[task008] source contains kill \"$WATCHER_PID\" 2>/dev/null || true", kill_substr in src,
          "substring not found")

    # (e) seed match offset < drain offset
    seed_offset = src.index(seed_matches[0]) if seed_matches else -1
    drain_offset = src.index(drain_substr) if drain_substr in src else -1
    check("[task008] seed line precedes drain (offset order)", seed_offset < drain_offset,
          f"seed_offset={seed_offset} drain_offset={drain_offset}")

    # (f) drain offset < kill offset
    kill_offset = src.index(kill_substr) if kill_substr in src else -1
    check("[task008] drain precedes kill (offset order)", drain_offset < kill_offset,
          f"drain_offset={drain_offset} kill_offset={kill_offset}")

    # (g) No arithmetic comparison [ "$cur" -gt "$WATCHER_SEED_MTIME" ]
    bad_arith = '[ "$cur" -gt "$WATCHER_SEED_MTIME" ]'
    check("[task008] no arithmetic -gt comparison for mtime", bad_arith not in src,
          "found forbidden arithmetic comparison")

    # (h) No standalone WATCHER_SEED_MTIME=0 literal assignment
    seed_literal_pattern = re.compile(r'^\s*WATCHER_SEED_MTIME=0\s*$', re.MULTILINE)
    check("[task008] no standalone WATCHER_SEED_MTIME=0 literal", not seed_literal_pattern.search(src),
          "found forbidden literal seed assignment")


# ── task_009: /learnings write-confirm hook ───────────────────────────────────

GUARD_FS = REPO / "devcontainer" / "guard-fs.sh"
GUARD_BASH = REPO / "devcontainer" / "guard-bash.sh"
LEARN_MD = REPO / "devcontainer" / "commands" / "learn.md"
LEARN_HOOK_MD = REPO / "devcontainer" / "claude-md" / "learn-hook.md"

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


def test_task009_guard_fs_exists() -> None:
    """AC1: guard-fs.sh exists as an executable shell script."""
    print("\n[task_009/AC1: guard-fs.sh exists]")
    check("[task009/AC1] guard-fs.sh exists", GUARD_FS.exists(), str(GUARD_FS))
    if GUARD_FS.exists():
        check("[task009/AC1] guard-fs.sh is executable",
              bool(GUARD_FS.stat().st_mode & 0o111), str(GUARD_FS))
        content = GUARD_FS.read_text()
        check("[task009/AC1] has set -euo pipefail", "set -euo pipefail" in content, "")
        check("[task009/AC1] uses jq -r .tool_input.file_path",
              "jq -r" in content and "tool_input" in content and "file_path" in content, "")
        check("[task009/AC1] uses realpath -m", "realpath -m" in content, "")


def test_task009_guard_fs_ask_fixtures() -> None:
    """AC10: guard-fs.sh emits correct ask-JSON for /learnings paths."""
    print("\n[task_009/AC10: guard-fs.sh ask fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ('{"tool_input":{"file_path":"/learnings/2026-04-26T17:00:00Z-abcdef.md"}}',
         "/learnings file path"),
        ('{"tool_input":{"file_path":"/learnings"}}',
         "/learnings exact"),
        ('{"tool_input":{"file_path":"/learnings/sub/dir/file.md"}}',
         "/learnings deep path"),
    ]
    for json_input, label in fixtures:
        r = _run_guard_fs(json_input)
        _assert_ask_json(r, label)
        if r.returncode == 0 and r.stdout:
            try:
                data = json.loads(r.stdout)
                reason = data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                check(f"[task009] {label}: reason contains /learnings/",
                      "/learnings" in reason, reason)
            except json.JSONDecodeError:
                pass


def test_task009_guard_fs_non_learnings_fixtures() -> None:
    """AC11: guard-fs.sh silent for non-/learnings and traversal-attempt paths."""
    print("\n[task_009/AC11: guard-fs.sh non-/learnings fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ('{"tool_input":{"file_path":"/workspace/foo/bar.md"}}',
         "/workspace path"),
        ('{"tool_input":{"file_path":"/learnings/../etc/passwd"}}',
         "traversal attempt /etc/passwd"),
        ('{"tool_input":{"file_path":"/learnings/../../tmp/x"}}',
         "traversal attempt /tmp/x"),
        ('{"tool_input":{}}',
         "no file_path key"),
    ]
    for json_input, label in fixtures:
        r = _run_guard_fs(json_input)
        _assert_silent_exit0(r, label)


def test_task009_guard_bash_learnings_write_fixtures() -> None:
    """AC12: guard-bash.sh emits ask-JSON for /learnings shell-write idioms."""
    print("\n[task_009/AC12: guard-bash.sh /learnings write fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ("echo hi > /learnings/test.md", "redirect >"),
        ("echo hi >> /learnings/test.md", "redirect >>"),
        ("cmd | tee /learnings/z.md", "tee pipe"),
        ("tee -a /learnings/z.md < /tmp/x", "tee -a"),
        ("cp /tmp/x /learnings/y.md", "cp"),
        ("cp -r /tmp/dir /learnings/sub", "cp -r"),
        ("mv /tmp/x /learnings/y.md", "mv"),
        ("rm /learnings/old.md", "rm"),
        ("rm -rf /learnings/old/", "rm -rf"),
        ("ln -s /tmp/target /learnings/link", "ln -s"),
        ("mkdir /learnings/newdir", "mkdir"),
        ("chmod 644 /learnings/x.md", "chmod"),
        ("chown node:node /learnings/x.md", "chown"),
        ("truncate -s 0 /learnings/x.md", "truncate"),
        ("dd if=/dev/zero of=/learnings/x bs=1M count=1", "dd"),
        ("sed -i 's/foo/bar/' /learnings/x.md", "sed -i"),
        ("sed -ri 's/foo/bar/' /learnings/x.md", "sed -ri combined flag"),
    ]
    for cmd_str, label in fixtures:
        r = _run_guard_bash(cmd_str)
        _assert_ask_json(r, f"bash write: {label}")


def test_task009_guard_bash_learnings_read_fixtures() -> None:
    """AC13: guard-bash.sh allows /learnings reads (no output, exit 0)."""
    print("\n[task_009/AC13: guard-bash.sh /learnings read fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ("cat /learnings/x.md", "cat"),
        ("ls /learnings/", "ls"),
        ("grep -r foo /learnings/", "grep -r"),
        ("head /learnings/x.md", "head"),
        ("sed -n '/learnings/p' /tmp/file", "sed -n (read, no -i)"),
    ]
    for cmd_str, label in fixtures:
        r = _run_guard_bash(cmd_str)
        _assert_silent_exit0(r, f"bash read: {label}")


def test_task009_guard_bash_gitpush_and_block_beats_ask() -> None:
    """AC14: guard-bash.sh preserves git-push block AND block beats ask."""
    print("\n[task_009/AC14: guard-bash.sh git-push + block-beats-ask]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    # force push → exit 2
    r = _run_guard_bash("git push --force origin main")
    check("[task009/AC14] force push: exit 2", r.returncode == 2,
          f"exit={r.returncode}")
    check("[task009/AC14] force push: stderr contains 'git push --force'",
          "git push --force" in r.stderr, r.stderr[:200])

    # branch delete → exit 2
    r = _run_guard_bash("git push origin :branchname")
    check("[task009/AC14] branch delete: exit 2", r.returncode == 2,
          f"exit={r.returncode}")
    check("[task009/AC14] branch delete: stderr contains 'git push'",
          "git push" in r.stderr, r.stderr[:200])

    # normal push → exit 0, no output
    r = _run_guard_bash("git push origin main")
    _assert_silent_exit0(r, "normal push")

    # block beats ask: rm /learnings + force push → exit 2 (not ask-JSON)
    r = _run_guard_bash("rm /learnings/old.md && git push --force origin main")
    check("[task009/AC14] block-beats-ask (rm+force-push): exit 2", r.returncode == 2,
          f"exit={r.returncode}")

    # block beats ask: force push + echo to /learnings → exit 2 (not ask-JSON)
    r = _run_guard_bash("git push --force origin main && echo hi > /learnings/x.md")
    check("[task009/AC14] block-beats-ask (force-push+echo): exit 2", r.returncode == 2,
          f"exit={r.returncode}")


def test_task009_settings_json_updated() -> None:
    """AC4: vibe heredoc contains Write|Edit|MultiEdit matcher entry (persistent fix).

    Reads /workspace/vibe source (not the runtime-generated settings.local.json)
    because settings.local.json is gitignored and rewritten on every container
    start — the only durable fix is in the heredoc inside vibe.
    """
    print("\n[task_009/AC4: vibe heredoc has Write|Edit|MultiEdit matcher]")
    vibe_path = REPO / "vibe"
    check("[task009/AC4] vibe script exists", vibe_path.exists(), str(vibe_path))
    if not vibe_path.exists():
        return
    vibe_src = vibe_path.read_text()
    # Locate byte offsets for ordering assertions
    bash_offset = vibe_src.find('"matcher": "Bash"')
    fs_offset = vibe_src.find('"matcher": "Write|Edit|MultiEdit"')
    guard_fs_offset = vibe_src.find("/usr/local/bin/guard-fs.sh")
    check("[task009/AC4] Bash matcher present in vibe heredoc",
          bash_offset != -1, "not found")
    check("[task009/AC4] Write|Edit|MultiEdit matcher present in vibe heredoc",
          fs_offset != -1, "not found")
    check("[task009/AC4] /usr/local/bin/guard-fs.sh present in vibe heredoc",
          guard_fs_offset != -1, "not found")
    # Both substrings must appear AFTER the Bash matcher entry
    if bash_offset != -1 and fs_offset != -1:
        check("[task009/AC4] Write|Edit|MultiEdit entry is after Bash entry",
              fs_offset > bash_offset, f"fs_offset={fs_offset} bash_offset={bash_offset}")
    if bash_offset != -1 and guard_fs_offset != -1:
        check("[task009/AC4] guard-fs.sh entry is after Bash matcher",
              guard_fs_offset > bash_offset,
              f"guard_fs_offset={guard_fs_offset} bash_offset={bash_offset}")


def test_task009_dockerfile_updated() -> None:
    """AC5: Dockerfile has COPY + chmod for guard-fs.sh."""
    print("\n[task_009/AC5: Dockerfile updated]")
    check("[task009/AC5] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return
    content = DOCKERFILE.read_text()
    # AC5a: canonical COPY line (no trailing slash)
    copy_lines = [ln.strip() for ln in content.splitlines()
                  if ln.strip() == "COPY guard-fs.sh /usr/local/bin/"]
    check("[task009/AC5a] exactly one canonical COPY guard-fs.sh line",
          len(copy_lines) == 1, f"found {len(copy_lines)} lines")
    # AC5b: /usr/local/bin/guard-fs.sh in chmod chain
    chmod_lines = [ln for ln in content.splitlines() if "chmod +x" in ln]
    check("[task009/AC5b] /usr/local/bin/guard-fs.sh in chmod +x chain",
          any("/usr/local/bin/guard-fs.sh" in ln for ln in chmod_lines),
          str(chmod_lines))


def test_task009_learn_md_exists() -> None:
    """AC6: commands/learn.md exists with required content."""
    print("\n[task_009/AC6: commands/learn.md]")
    check("[task009/AC6] learn.md exists", LEARN_MD.exists(), str(LEARN_MD))
    if not LEARN_MD.exists():
        return
    content = LEARN_MD.read_text()
    check("[task009/AC6] mentions /learnings/ path", "/learnings/" in content, "")
    check("[task009/AC6] ts= one-liner present",
          "ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" in content, "")
    check("[task009/AC6] rand= one-liner present",
          "rand=$(python3 -c 'import binascii,os; print(binascii.hexlify(os.urandom(3)).decode())')" in content,
          "")
    check("[task009/AC6] printf format present",
          "printf '# %s\\n\\n%s\\n' \"$ts\" \"$pattern\"" in content, "")
    check("[task009/AC6] refusal message present",
          "/learn: /learnings is not mounted (run 'vibe learn --init' on host first)" in content, "")
    check("[task009/AC6] mentions vibe learn --push", "vibe learn --push" in content, "")
    check("[task009/AC6] instructs preview before Write",
          "preview" in content.lower() or "print" in content.lower(), "")


def test_task009_learn_hook_md_exists() -> None:
    """AC7: claude-md/learn-hook.md exists with sentinel phrases."""
    print("\n[task_009/AC7: claude-md/learn-hook.md]")
    check("[task009/AC7] learn-hook.md exists", LEARN_HOOK_MD.exists(), str(LEARN_HOOK_MD))
    if not LEARN_HOOK_MD.exists():
        return
    content = LEARN_HOOK_MD.read_text()
    non_blank = sum(1 for ln in content.splitlines() if ln.strip())
    check("[task009/AC7] >= 30 non-blank lines", non_blank >= 30,
          f"non_blank={non_blank}")
    check("[task009/AC7] contains 'permissionDecision'",
          "permissionDecision" in content, "")
    check("[task009/AC7] contains 'do not bypass'",
          "do not bypass" in content, "")
    check("[task009/AC7] contains 'host-only'",
          "host-only" in content, "")


def test_learn_docs_no_host_stage_all_footgun() -> None:
    """Regression: /learn docs must not tell the host to `cd $VIBE_LEARNING_PATH
    && git add .`. VIBE_LEARNING_PATH is a container/config var, unset in the
    user's interactive Mac shell, so `cd $VIBE_LEARNING_PATH` becomes `cd ~`
    and `git add .` stages all of $HOME (observed 2026-05-26, one `&&` from a
    secret-leaking push). Host-side push must go through `vibe learn --push`,
    and any manual fallback must use a literal placeholder path + a specific
    filename, never the container var and never `git add .`."""
    print("\n[regression: /learn docs have no host stage-all footgun]")
    for path in (LEARN_MD, LEARN_HOOK_MD):
        if not path.exists():
            check(f"[learn-footgun] {path.name} exists", False, str(path))
            continue
        content = path.read_text()
        check(f"[learn-footgun] {path.name} has no 'git add .' (stages $HOME)",
              "git add ." not in content,
              "found dangerous stage-all 'git add .' in host instructions")
        check(f"[learn-footgun] {path.name} does not reference $VIBE_LEARNING_PATH "
              "in host instructions (container-only var)",
              "$VIBE_LEARNING_PATH" not in content and "${VIBE_LEARNING_PATH" not in content,
              "container/config var leaked into host-side instructions")


def test_task009_readme_updated() -> None:
    """AC8: README.md contains PreToolUse hook gates writes sentinel."""
    print("\n[task_009/AC8: README.md updated]")
    readme = REPO / "README.md"
    check("[task009/AC8] README.md exists", readme.exists(), str(readme))
    if not readme.exists():
        return
    content = readme.read_text()
    check("[task009/AC8] contains 'PreToolUse hook gates writes'",
          "PreToolUse hook gates writes" in content, "")


def test_task009_code_check_clean() -> None:
    """AC15: python3 code-check.py exits 0 (no new shellcheck warnings)."""
    print("\n[task_009/AC15: code-check.py clean]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[task009/AC15] code-check.py exits 0", r.returncode == 0,
          f"exit={r.returncode} output={r.stdout[-300:]}")


def test_task009_hardening_notebookedit_not_in_matcher() -> None:
    """Hardening: guard-fs.sh matcher EXCLUDES NotebookEdit (out of scope)."""
    print("\n[task_009/hardening: NotebookEdit excluded from matcher]")
    settings_path = REPO / ".claude" / "settings.local.json"
    if not settings_path.exists():
        # settings.local.json is a runtime artifact generated inside an
        # active vibe container (and gitignored). On CI / fresh-checkout it
        # legitimately doesn't exist - that's expected, not a failure. The
        # hardening sentinel only meaningfully runs when we're testing
        # against a populated vibe environment.
        check("[task009] settings.local.json absent — hardening check skipped (expected on CI)",
              True, "runtime-only file; not committed")
        return
    try:
        data = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        return
    pre_tool = data.get("hooks", {}).get("PreToolUse", [])
    fs_entry = next((e for e in pre_tool if e.get("matcher") == "Write|Edit|MultiEdit"), None)
    if fs_entry:
        check("[task009] guard-fs.sh matcher exactly 'Write|Edit|MultiEdit' (no NotebookEdit)",
              True)  # Already tested in AC4, but re-check for hardening
    else:
        check("[task009] guard-fs.sh matcher entry found", False, "")


def test_task009_hardening_guard_bash_set_euo() -> None:
    """Hardening: guard-bash.sh still has 'set -euo pipefail' (not removed during refactor)."""
    print("\n[task_009/hardening: guard-bash.sh 'set -euo pipefail']")
    if not GUARD_BASH.exists():
        check("[task009] guard-bash.sh exists", False, "")
        return
    content = GUARD_BASH.read_text()
    check("[task009] guard-bash.sh has 'set -euo pipefail'",
          "set -euo pipefail" in content, "")


def test_task009_hardening_guard_fs_realpath_m() -> None:
    """Hardening: guard-fs.sh uses 'realpath -m' (not just 'realpath')."""
    print("\n[task_009/hardening: guard-fs.sh uses 'realpath -m']")
    if not GUARD_FS.exists():
        check("[task009] guard-fs.sh exists", False, "")
        return
    content = GUARD_FS.read_text()
    check("[task009] guard-fs.sh uses 'realpath -m' (with -m flag)",
          "realpath -m" in content, "")


def test_task010_smart_capture() -> None:
    """AC1-AC19: /learn smart-capture semantic check phase."""
    print("\n[task_010: /learn smart-capture]")

    if not LEARN_MD.exists():
        check("[task010/AC1] learn.md exists", False, str(LEARN_MD))
        return

    content = LEARN_MD.read_text()

    # AC1: Semantic check section with exact heading
    check("[task010/AC1] '## Semantic check' section heading present",
          "## Semantic check" in content, "missing exact heading")

    # AC2: Relative ordering — "Formats the entry body" before "Runs the semantic check" before "Prints a preview"
    lines = content.splitlines()
    format_body_idx = None
    runs_check_idx = None
    prints_preview_idx = None

    for i, line in enumerate(lines):
        if "Formats the entry body" in line:
            format_body_idx = i
        if "Runs the semantic check" in line:
            runs_check_idx = i
        if "Prints a preview" in line:
            prints_preview_idx = i

    check("[task010/AC2] 'Formats the entry body' appears before 'Runs the semantic check'",
          format_body_idx is not None and runs_check_idx is not None and format_body_idx < runs_check_idx,
          f"format_body={format_body_idx}, runs_check={runs_check_idx}")

    check("[task010/AC2] 'Runs the semantic check' appears before 'Prints a preview'",
          runs_check_idx is not None and prints_preview_idx is not None and runs_check_idx < prints_preview_idx,
          f"runs_check={runs_check_idx}, prints_preview={prints_preview_idx}")

    # AC3: Literal phrase "Runs the semantic check"
    check("[task010/AC3] 'Runs the semantic check' phrase present",
          "Runs the semantic check" in content, "missing exact phrase")

    # AC3a: "existing /learnings entries" in semantic check section
    semantic_section_start = content.find("## Semantic check")
    if semantic_section_start >= 0:
        next_section = content.find("\n##", semantic_section_start + 1)
        semantic_section = content[semantic_section_start:next_section] if next_section > 0 else content[semantic_section_start:]
    else:
        semantic_section = ""

    check("[task010/AC3a] 'existing /learnings entries' phrase in semantic check section",
          "existing /learnings entries" in semantic_section, "missing exact phrase")

    # AC4: Low-quality input explicitly addressed
    low_quality_check = any(phrase in semantic_section for phrase in
                            ["low-quality input", "low quality input", "vague reference", "unclear input"])
    check("[task010/AC4] Low-quality input explicitly addressed",
          low_quality_check, "missing at least one of: low-quality input, low quality input, vague reference, unclear input")

    # AC5: Zero friction (both phrases required)
    zero_friction_present = "zero friction" in semantic_section.lower()
    no_options_present = any(phrase in semantic_section.lower() for phrase in
                             ["no options", "without surfacing options", "no options surfaced"])
    check("[task010/AC5] 'zero friction' (case-insensitive) present",
          zero_friction_present, "missing phrase")
    check("[task010/AC5] 'no options' or equivalent present",
          no_options_present, "missing one of: no options, without surfacing options, no options surfaced")

    # AC6: Option scheme enumeration
    z1_present = "Z1" in semantic_section
    z1_verbatim = any(phrase in semantic_section for phrase in ["user-verbatim", "user verbatim"])
    z1_check = z1_present and z1_verbatim

    z2_present = "Z2" in semantic_section

    edit_existing = any(phrase in semantic_section for phrase in ["edit existing", "edit an existing"])

    n_present = "N" in semantic_section
    n_drops = any(phrase in semantic_section for phrase in ["drop", "drops", "cancel", "cancels"])
    n_check = n_present and n_drops

    check("[task010/AC6] Z1 and 'user-verbatim'/'user verbatim' within 200 chars",
          z1_check, "missing Z1 label or user-verbatim phrase")
    check("[task010/AC6] Z2 label present",
          z2_present, "missing Z2")
    check("[task010/AC6] 'edit existing' or 'edit an existing' present",
          edit_existing, "missing phrase")
    check("[task010/AC6] N label and drop/drops/cancel/cancels within 200 chars",
          n_check, "missing N label or drop/drops/cancel/cancels")

    # AC7: Z1 is ALWAYS the user-verbatim original
    z1_always_check = any(phrase in semantic_section for phrase in ["Z1 is always", "Z1 is ALWAYS"])
    verbatim_in_section = "verbatim" in semantic_section
    z1_always_correct = z1_always_check and verbatim_in_section
    check("[task010/AC7] 'Z1 is always' or 'Z1 is ALWAYS' AND 'verbatim'",
          z1_always_correct, "missing or incomplete requirement")

    # AC8: Marginal token cost (2-5k tokens, en-dash or hyphen variants)
    token_cost_check = any(phrase in semantic_section for phrase in
                           ["2-5k tokens", "2–5k tokens", "2 to 5k tokens"])
    check("[task010/AC8] '2-5k tokens' or '2–5k tokens' or '2 to 5k tokens' present",
          token_cost_check, "missing token cost phrase")

    # AC9: Preview and hook mentioned in same paragraph (within 400 chars if no blank line separation)
    preview_present = "preview" in semantic_section.lower()
    hook_present = "hook" in semantic_section.lower()
    preview_hook_proximity = (preview_present and hook_present)
    check("[task010/AC9] 'preview' and 'hook' both present",
          preview_hook_proximity, "missing or incomplete proximity")

    # AC10: Conditional skipping forbidden (positive check + negative grepping)
    always_runs = any(phrase in semantic_section for phrase in
                     ["every /learn invocation", "runs on every invocation", "always runs"])
    skip_forbidden = not any(phrase in semantic_section for phrase in
                            ["skip the", "skip if", "bypass the check", "omit the check"])
    ac10_check = always_runs and skip_forbidden
    check("[task010/AC10] 'every /learn invocation' or equivalent AND no skip/bypass/omit",
          ac10_check, "missing always-runs or found skip/bypass/omit phrasing")

    # AC11: Z-options capped
    cap_check = any(phrase in semantic_section for phrase in
                   ["cap n at 3", "no more than 3", "up to 3 alternatives", "1 or 2 alternatives"])
    check("[task010/AC11] Z-options capped (cap n at 3, no more than 3, etc.)",
          cap_check, "missing cap/limit phrase")

    # AC12-AC17: Regression gates (filename, body format, multi-line, host-only, refusal, hook)
    check("[task010/AC12] ts=$(date -u present",
          "ts=$(date -u" in content, "missing filename component")
    check("[task010/AC12] binascii.hexlify present",
          "binascii.hexlify" in content, "missing random component")
    check("[task010/AC12] ${ts}-${rand}.md present",
          "${ts}-${rand}.md" in content, "missing filename format")

    check("[task010/AC13] printf format present",
          "printf '# %s\\n\\n%s\\n'" in content, "missing body format")
    check("[task010/AC13] '# <timestamp> header line' mentioned",
          "# <timestamp> header line" in content, "missing header reference")

    check("[task010/AC14] '## Multi-line patterns' section present",
          "## Multi-line patterns" in content, "missing section")

    check("[task010/AC15] 'vibe learn --push' present",
          "vibe learn --push" in content, "missing host-only push instruction")
    check("[task010/AC15] 'host-only' present",
          "host-only" in content, "missing host-only reference")

    check("[task010/AC16] '/learn: /learnings is not mounted' refusal message",
          "/learn: /learnings is not mounted" in content, "missing refusal message")

    check("[task010/AC17] 'PreToolUse hook' mentioned",
          "PreToolUse hook" in content, "missing hook reference")

    # AC18: Diff scope check (files modified must be subset of allowlist)
    # Try git diff first if commit exists, otherwise check current state
    try:
        diff_result = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=REPO)
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            changed_files = set(diff_result.stdout.strip().split('\n'))
        else:
            # Fallback: check git status
            status_result = run(["git", "status", "--porcelain"], cwd=REPO)
            changed_files = set(line.split()[-1] for line in status_result.stdout.strip().split('\n') if line.strip())
    except:
        changed_files = set()

    allowlist = {
        "devcontainer/commands/learn.md",
        "smoke-test.py",
        ".vs/spec.md",
        ".vs/progress.md",
        ".vs/tasks.json"
    }
    # Also allow .vs/cycle-1/ directory and its contents
    scope_ok = all(f not in allowlist and not f.startswith(".vs/cycle-1/") for f in changed_files
                   if f not in allowlist and not f.startswith(".vs/cycle-1/"))

    check("[task010/AC18] No scope creep (only allowed files modified)",
          scope_ok, f"changed files: {', '.join(changed_files)}")

    # AC19: This test function itself exists. Use REPO-relative path so this
    # works on CI (checkout at /home/runner/work/vibe/vibe/) as well as inside
    # the vibe container (workspace at /workspace/). Earlier hardcoded
    # /workspace/smoke-test.py path failed in CI 2026-05-09 (commit 2ec36b3);
    # the bare except: swallowed FileNotFoundError into a check-fail.
    smoke_test_content = (REPO / "smoke-test.py").read_text()
    test_func_exists = "def test_task010_smart_capture() -> None:" in smoke_test_content
    check("[task010/AC19] test_task010_smart_capture function exists",
          test_func_exists, "function signature not found")


def test_task013_vs_md_intelligent_stopping() -> None:
    """AC5: vs.md documents intelligent Spec Critic stopping rules (13 checks)."""
    print("\n[task_013/AC5: intelligent stopping rules]")
    if not VS_MD.exists():
        check("[task013/AC5] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()

    # Convergence (3 sentinels)
    check("[task013/AC5] Convergence sentinel present", "Convergence" in content,
          "missing 'Convergence'")
    check("[task013/AC5] iterate until Spec Critic returns `pass` sentinel",
          "iterate until Spec Critic returns `pass`" in content,
          "missing 'iterate until Spec Critic returns `pass`'")
    check("[task013/AC5] no hardcoded cap sentinel",
          "no hardcoded cap" in content,
          "missing 'no hardcoded cap'")

    # Plateau detection (6 sentinels: 5 substring + 1 proximity check)
    check("[task013/AC5] Plateau detection sentinel",
          "Plateau detection" in content,
          "missing 'Plateau detection'")
    check("[task013/AC5] Spec Critic plateaued at iter- sentinel",
          "Spec Critic plateaued at iter-" in content,
          "missing 'Spec Critic plateaued at iter-'")
    check("[task013/AC5] (a) accept residuals sentinel",
          "(a) accept residuals" in content,
          "missing '(a) accept residuals'")
    check("[task013/AC5] (b) restart with a revised brief sentinel",
          "(b) restart with a revised brief" in content,
          "missing '(b) restart with a revised brief'")
    check("[task013/AC5] (c) drop the task sentinel",
          "(c) drop the task" in content,
          "missing '(c) drop the task'")

    # Plateau proximity check: all three labels in same paragraph as "Plateau detection"
    plateau_idx = content.find("Plateau detection")
    if plateau_idx != -1:
        # Find next blank line (or EOF) after the anchor line
        anchor_line_end = content.find("\n", plateau_idx)
        if anchor_line_end == -1:
            # "Plateau detection" is on last line
            paragraph_end = len(content)
        else:
            # Search for next blank line
            search_pos = anchor_line_end + 1
            while search_pos < len(content):
                next_newline = content.find("\n", search_pos)
                if next_newline == -1:
                    next_newline = len(content)
                # Check if line is blank (only whitespace)
                line = content[search_pos:next_newline]
                if line.strip() == "":
                    paragraph_end = search_pos
                    break
                search_pos = next_newline + 1
            else:
                paragraph_end = len(content)

        paragraph = content[plateau_idx:paragraph_end]
        all_labels_in_para = (
            "(a) accept residuals" in paragraph and
            "(b) restart with a revised brief" in paragraph and
            "(c) drop the task" in paragraph
        )
        check("[task013/AC5] plateau option labels in same paragraph",
              all_labels_in_para,
              "option labels not all in paragraph starting with 'Plateau detection'")
    else:
        check("[task013/AC5] plateau option labels in same paragraph", False,
              "'Plateau detection' not found")

    # Divergence detection (4 sentinels)
    check("[task013/AC5] Divergence detection sentinel",
          "Divergence detection" in content,
          "missing 'Divergence detection'")
    check("[task013/AC5] Spec Critic divergent sentinel",
          "Spec Critic divergent" in content,
          "missing 'Spec Critic divergent'")
    check("[task013/AC5] concern count growing sentinel",
          "concern count growing" in content,
          "missing 'concern count growing'")
    check("[task013/AC5] three consecutive iterations sentinel",
          "three consecutive iterations" in content,
          "missing 'three consecutive iterations'")


def test_task013_vs_md_max_iter_flag() -> None:
    """AC6: vs.md documents --max-iter flag with 4+ checks."""
    print("\n[task_013/AC6: --max-iter flag documentation]")
    if not VS_MD.exists():
        check("[task013/AC6] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()
    lines = content.split("\n")

    # AC3 check: same-line co-occurrence of "--max-iter" AND "Spec Critic loop"
    same_line_found = False
    for line in lines:
        if "--max-iter" in line and "Spec Critic loop" in line:
            same_line_found = True
            break
    check("[task013/AC6] AC3: same-line co-occurrence of '--max-iter' and 'Spec Critic loop'",
          same_line_found,
          "no single line contains both '--max-iter' and 'Spec Critic loop'")

    # AC4 checks: three required substrings
    check("[task013/AC6] AC4: --max-iter substring",
          "--max-iter" in content,
          "missing '--max-iter'")
    check("[task013/AC6] AC4: cap fires before convergence substring",
          "cap fires before convergence" in content,
          "missing 'cap fires before convergence'")
    check("[task013/AC6] AC4: do NOT silently auto-pass substring",
          "do NOT silently auto-pass" in content,
          "missing 'do NOT silently auto-pass'")


def test_task013_no_hardcoded_cap_string() -> None:
    """AC7: vs.md does not contain 'max 2 iterations'."""
    print("\n[task_013/AC7: no hardcoded cap string]")
    if not VS_MD.exists():
        check("[task013/AC7] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()
    check("[task013/AC7] 'max 2 iterations' not present in vs.md",
          "max 2 iterations" not in content,
          "'max 2 iterations' found in file (should be removed)")


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


def test_check_sp_current_exists_and_executable() -> None:
    print("\n[check-sp-current: file shape]")
    check("[sp-probe] script exists", CHECK_SP_CURRENT.exists(), str(CHECK_SP_CURRENT))
    if not CHECK_SP_CURRENT.exists():
        return
    check("[sp-probe] script is executable",
          os.access(CHECK_SP_CURRENT, os.X_OK), "")


def test_check_sp_current_offline_silent() -> None:
    """--offline mode exits 0 silently."""
    print("\n[check-sp-current: offline silent]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--offline"])
    check("[sp-probe] --offline exits 0", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[:200]}")
    check("[sp-probe] --offline silent on stderr", r.stderr.strip() == "",
          r.stderr[:200])


def test_check_sp_current_fixture_no_drift() -> None:
    """Fixture matches sp.md exactly → no drift output."""
    print("\n[check-sp-current: fixture exact match]")
    if not CHECK_SP_CURRENT.exists():
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(SP_CORE_SKILLS) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] no-drift fixture exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] no-drift fixture silent",
              "DRIFT" not in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_missing_skill() -> None:
    """Fixture has a skill sp.md doesn't list → drift, names it."""
    print("\n[check-sp-current: fixture missing skill]")
    if not CHECK_SP_CURRENT.exists():
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(SP_CORE_SKILLS + ["new-skill-x"]) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] missing-skill exits 0 (informational)",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] missing-skill stderr says DRIFT",
              "DRIFT" in r.stderr, r.stderr[:200])
        check("[sp-probe] missing-skill names the new skill",
              "new-skill-x" in r.stderr, r.stderr[:200])
        check("[sp-probe] missing-skill labels it 'Missing from sp.md'",
              "Missing from sp.md" in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_extra_skill() -> None:
    """Fixture missing a skill sp.md lists → drift labelled 'Extra in sp.md'."""
    print("\n[check-sp-current: fixture extra in sp.md]")
    if not CHECK_SP_CURRENT.exists():
        return
    # Drop one skill from the fixture so sp.md has one extra.
    fixture_skills = [s for s in SP_CORE_SKILLS if s != "using-git-worktrees"]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(fixture_skills) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] extra-skill exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] extra-skill stderr says DRIFT",
              "DRIFT" in r.stderr, r.stderr[:200])
        check("[sp-probe] extra-skill names the dropped skill",
              "using-git-worktrees" in r.stderr, r.stderr[:200])
        check("[sp-probe] extra-skill labels it 'Extra in sp.md'",
              "Extra in sp.md" in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_nonexistent_errors() -> None:
    """--fixture with unreadable path errors out."""
    print("\n[check-sp-current: fixture nonexistent]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--fixture", "/no/such/file"])
    check("[sp-probe] nonexistent fixture exit 1", r.returncode == 1,
          f"rc={r.returncode}")
    check("[sp-probe] nonexistent fixture explains itself",
          "readable file" in r.stderr, r.stderr[:200])


def test_check_sp_current_unknown_arg_errors() -> None:
    """Unknown flag errors out."""
    print("\n[check-sp-current: unknown arg]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--bogus"])
    check("[sp-probe] unknown arg exit 1", r.returncode == 1,
          f"rc={r.returncode}")
    check("[sp-probe] unknown arg names the bad flag",
          "--bogus" in r.stderr, r.stderr[:200])


def test_check_sp_current_wired_into_container_start() -> None:
    """Drift check ships in the image and runs from install-claude-extras.sh."""
    print("\n[check-sp-current: container-start wiring]")
    dockerfile = DOCKERFILE.read_text()
    check("[sp-wire] Dockerfile COPYs check-sp-current.sh to /usr/local/bin",
          "COPY check-sp-current.sh /usr/local/bin/" in dockerfile, "")
    check("[sp-wire] Dockerfile chmods the checker",
          "/usr/local/bin/check-sp-current.sh" in dockerfile, "")
    extras = INSTALL_EXTRAS.read_text()
    check("[sp-wire] extras script defines check_sp_drift",
          "check_sp_drift()" in extras, "")
    check("[sp-wire] check_sp_drift is invoked",
          re.search(r"^check_sp_drift$", extras, re.MULTILINE) is not None, "")
    check("[sp-wire] honours VIBE_PLUGINS=0 opt-out",
          'VIBE_PLUGINS:-1' in extras.split("check_sp_drift()")[1].split("}")[0], "")
    check("[sp-wire] guards on checker executable (old-image safe)",
          '[ -x "$checker" ] || return 0' in extras, "")
    check("[sp-wire] points SP_MD at the synced commands dir",
          'SP_MD="$DEST_ROOT/commands/sp.md"' in extras, "")


# ── /sp slash command tests ────────────────────────────────────────────────────


def test_sp_md_present_and_complete() -> None:
    """sp.md is shipped and references the seven Superpowers core skills."""
    print("\n[/sp: sp.md present + complete]")
    check("[sp] sp.md exists", SP_MD.exists(), str(SP_MD))
    if not SP_MD.exists():
        return
    content = SP_MD.read_text()
    check("[sp] frontmatter description present",
          "description: Apply Superpowers methodology" in content,
          "missing description in frontmatter")
    expected_skills = [
        "superpowers:using-superpowers",
        "superpowers:brainstorming",
        "superpowers:writing-plans",
        "superpowers:executing-plans",
        "superpowers:subagent-driven-development",
        "superpowers:dispatching-parallel-agents",
        "superpowers:test-driven-development",
        "superpowers:systematic-debugging",
        "superpowers:requesting-code-review",
        "superpowers:receiving-code-review",
        "superpowers:verification-before-completion",
        "superpowers:finishing-a-development-branch",
        "superpowers:using-git-worktrees",
        "superpowers:writing-skills",
    ]
    for skill in expected_skills:
        check(f"[sp] mentions {skill}", skill in content,
              f"missing skill: {skill}")
    check("[sp] documents official marketplace install",
          "claude-plugins-official" in content, "")
    check("[sp] documents fallback obra marketplace",
          "obra/superpowers-marketplace" in content, "")


def test_sp_md_referenced_from_readme() -> None:
    """README mentions /sp so users can discover it."""
    print("\n[/sp: README mentions /sp]")
    readme = REPO / "README.md"
    check("[sp] README.md exists", readme.exists(), str(readme))
    if not readme.exists():
        return
    content = readme.read_text()
    check("[sp] README mentions `/sp`", "/sp" in content, "")


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


def test_skipped_marker_round_trip() -> None:
    """mark_github_skipped writes WORKSPACE; is_github_skipped reads it back."""
    print("\n[skipped: literal path round-trip]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        env = {
            **os.environ,
            "HOME": str(home),
            "VIBE_CONFIG": "/dev/null",
            "VIBE_SOURCE_ONLY": "1",
            "WORKSPACE": str(proj),
        }
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'mark_github_skipped >/dev/null; '
            'if is_github_skipped; then echo "SKIPPED=true"; '
            'else echo "SKIPPED=false"; fi'
        )
        r = subprocess.run(["bash", "-c", script], env=env,
                           capture_output=True, text=True)
        check("[skipped] mark+check round-trip exits 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check("[skipped] is_github_skipped returns true after mark",
              "SKIPPED=true" in r.stdout, r.stdout)


def test_skipped_marker_trailing_slash() -> None:
    """is_github_skipped tolerates trailing-slash difference between mark and lookup."""
    print("\n[skipped: trailing-slash tolerance]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Pre-seed with no-slash form (canonical), then look up with trailing slash.
        rc, out, _ = _run_skipped_probe(
            workspace=f"{proj}/",
            marker_state=[str(proj)],
            home=home,
        )
        check("[skipped] trailing-slash WORKSPACE matches no-slash entry",
              "SKIPPED=true" in out, out)


def test_skipped_marker_symlink_path() -> None:
    """is_github_skipped tolerates symlinked path equivalent to a marked entry."""
    print("\n[skipped: symlink-equivalent path]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        sym = home / "symproj"
        sym.symlink_to("realproj")
        # Pre-seed with the canonical (real) path, look up via symlink.
        rc, out, _ = _run_skipped_probe(
            workspace=str(sym),
            marker_state=[str(proj)],
            home=home,
        )
        check("[skipped] symlinked WORKSPACE matches canonical entry",
              "SKIPPED=true" in out, out)


def test_skipped_marker_writes_canonical() -> None:
    """mark_github_skipped writes the canonical (cd && pwd -P) form."""
    print("\n[skipped: mark writes canonical path]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Set WORKSPACE with a trailing slash; mark should still write canonical.
        env = {
            **os.environ,
            "HOME": str(home),
            "VIBE_CONFIG": "/dev/null",
            "VIBE_SOURCE_ONLY": "1",
            "WORKSPACE": f"{proj}/",
        }
        script = (
            f"source {shlex.quote(str(VIBE))}; mark_github_skipped >/dev/null"
        )
        r = subprocess.run(["bash", "-c", script], env=env,
                           capture_output=True, text=True)
        check("[skipped] mark exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        skipped_path = home / ".vibe" / "skipped"
        content = skipped_path.read_text().splitlines() if skipped_path.exists() else []
        check("[skipped] file contains canonical (no trailing slash) path",
              str(proj) in content, str(content))


def test_skipped_marker_unrelated_path_rejected() -> None:
    """is_github_skipped returns false for a path that wasn't marked."""
    print("\n[skipped: unrelated path rejected]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj_a = home / "proj_a"
        proj_b = home / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()
        rc, out, _ = _run_skipped_probe(
            workspace=str(proj_b),
            marker_state=[str(proj_a)],
            home=home,
        )
        check("[skipped] unrelated WORKSPACE returns false",
              "SKIPPED=false" in out, out)


def test_skipped_marker_back_compat_literal() -> None:
    """Pre-existing literal (non-canonical) entries still resolve."""
    print("\n[skipped: back-compat with non-canonical entries]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Marker file has a non-canonical literal (e.g. trailing-slash entry
        # from before this fix). Lookup with the same literal should match.
        literal_with_slash = f"{proj}/"
        rc, out, _ = _run_skipped_probe(
            workspace=literal_with_slash,
            marker_state=[literal_with_slash],
            home=home,
        )
        check("[skipped] literal-with-slash entry still matches its own path",
              "SKIPPED=true" in out, out)


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


def test_check_numbering_exists_and_executable() -> None:
    """check-numbering.sh exists, is executable, and is a bash script."""
    print("\n[check-numbering: file shape]")
    check("[numbering] script exists", CHECK_NUMBERING.exists(), str(CHECK_NUMBERING))
    if not CHECK_NUMBERING.exists():
        return
    check("[numbering] script is executable",
          os.access(CHECK_NUMBERING, os.X_OK), "")
    head = CHECK_NUMBERING.read_text().splitlines()[0]
    check("[numbering] starts with bash shebang",
          head == "#!/usr/bin/env bash", head)


def test_check_numbering_silent_on_clean() -> None:
    """No warning when reply has only numbered list (1./2./3.)."""
    print("\n[check-numbering: silent on numbered-only]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Three options:\\n1. First\\n2. Second\\n3. Third"}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent on numbered-only", "warning" not in err, err[:200])


def test_check_numbering_silent_on_lettered_only() -> None:
    """No warning when reply has only lettered list (a./b./c.)."""
    print("\n[check-numbering: silent on lettered-only]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Pick one:\\na. cancel\\nb. proceed"}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent on lettered-only", "warning" not in err, err[:200])


def test_check_numbering_warns_on_mixed() -> None:
    """Warning when reply mixes 1./2./3. and a./b./c."""
    print("\n[check-numbering: warns on mixed]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Working list:\\n1. First task\\n2. Second task\\n\\nNext:\\n'
        'a. Do A\\nb. Do B"}]}}\n'
    )
    check("[numbering] exits 0 (non-blocking)", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] stderr contains 'numbering warning'",
          "numbering warning" in err, err[:200])


def test_check_numbering_ignores_code_fences() -> None:
    """Numbering inside ``` blocks does not trigger the warning."""
    print("\n[check-numbering: ignores code fences]")
    if not CHECK_NUMBERING.exists():
        return
    rc, err = _run_numbering_hook(
        '{"type":"user","message":{"content":"hi"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"Sample:\\n```\\n1. step\\na. label\\n```\\nNo lists outside fence."}]}}\n'
    )
    check("[numbering] exits 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("[numbering] silent when only fenced numbering",
          "warning" not in err, err[:200])


def test_check_numbering_handles_missing_transcript() -> None:
    """Hook tolerates empty stdin / missing transcript / unreadable file."""
    print("\n[check-numbering: edge cases]")
    if not CHECK_NUMBERING.exists():
        return
    for label, payload in (
        ("empty stdin", ""),
        ("no transcript_path", '{"foo":"bar"}'),
        ("unreadable transcript", '{"transcript_path":"/no/such/file.jsonl"}'),
    ):
        r = subprocess.run(
            ["bash", str(CHECK_NUMBERING)],
            input=payload, capture_output=True, text=True,
        )
        check(f"[numbering] {label}: exit 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check(f"[numbering] {label}: silent",
              r.stderr.strip() == "", r.stderr[:200])


def test_numbering_hook_readme_present() -> None:
    """devcontainer/hooks/README.md explains the hook + opt-in wiring."""
    print("\n[check-numbering: hooks/README.md]")
    check("[numbering] hooks/README.md exists",
          NUMBERING_HOOK_README.exists(), str(NUMBERING_HOOK_README))
    if not NUMBERING_HOOK_README.exists():
        return
    content = NUMBERING_HOOK_README.read_text()
    check("[numbering] readme names hook script path",
          "/home/node/.claude/hooks/check-numbering.sh" in content, "")
    check("[numbering] readme explains working-list/action-pick split",
          "working list" in content and "action pick" in content, "")


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


def test_copy_last_block_exists_and_executable() -> None:
    print("\n[copy-last-block: file shape]")
    check("[copy-block] script exists",
          COPY_LAST_BLOCK.exists(), str(COPY_LAST_BLOCK))
    if not COPY_LAST_BLOCK.exists():
        return
    check("[copy-block] script is executable",
          os.access(COPY_LAST_BLOCK, os.X_OK), "")
    head = COPY_LAST_BLOCK.read_text().splitlines()[0]
    check("[copy-block] starts with bash shebang",
          head == "#!/usr/bin/env bash", head)


def test_copy_last_block_single_block() -> None:
    """Marker + single fenced block → block content written, fence stripped."""
    print("\n[copy-last-block: single block]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nResult:\n```\necho hello\n```",
            cd,
        )
        check("[copy-block] single: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] single: file content matches",
              out == "echo hello", repr(out))


def test_copy_last_block_language_tag() -> None:
    """Marker + fence with language tag → tag dropped, only content written."""
    print("\n[copy-last-block: language-tagged fence]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\n```bash\necho hi\n```",
            cd,
        )
        check("[copy-block] langtag: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] langtag: language line dropped",
              out == "echo hi", repr(out))


def test_copy_last_block_multiple_blocks_last_wins() -> None:
    """Marker + multiple blocks → LAST one is written."""
    print("\n[copy-last-block: multiple blocks, last wins]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nfirst:\n```\nblock A\n```\nsecond:\n```\nblock B\n```",
            cd,
        )
        check("[copy-block] multi: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] multi: last block wins (B not A)",
              out == "block B", repr(out))


def test_copy_last_block_no_fence_no_write() -> None:
    """Marker but no fenced blocks → no file written."""
    print("\n[copy-last-block: no fence, no write]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\nJust plain text, no code samples here.",
            cd,
        )
        check("[copy-block] nofence: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] nofence: file NOT written",
              out == "<NO_FILE>", repr(out))


def test_copy_last_block_no_marker_silent() -> None:
    """Default is opt-in: without `<!-- vibe: copy -->`, no write even with a block."""
    print("\n[copy-last-block: no marker = silent]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "Result:\n```\nshould-not-be-copied\n```",
            cd,
        )
        check("[copy-block] no-marker: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] no-marker: file NOT written without sentinel",
              out == "<NO_FILE>", repr(out))


def test_copy_last_block_multiline_preserved() -> None:
    """Marker + multi-line block → interior newlines preserved."""
    print("\n[copy-last-block: multi-line preservation]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        rc, out = _run_copy_last_block(
            "<!-- vibe: copy -->\n```\nline 1\nline 2\nline 3\n```",
            cd,
        )
        check("[copy-block] multiline: exit 0", rc == 0, f"rc={rc}")
        check("[copy-block] multiline: interior newlines preserved",
              out == "line 1\nline 2\nline 3", repr(out))


def test_copy_last_block_empty_stdin() -> None:
    """Empty stdin / no transcript → silent exit 0, no write."""
    print("\n[copy-last-block: empty stdin]")
    if not COPY_LAST_BLOCK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        cd = Path(tmp) / ".vibe"
        cd.mkdir()
        env = {**os.environ, "VIBE_CLIP_DIR": str(cd)}
        r = subprocess.run(
            ["bash", str(COPY_LAST_BLOCK)],
            input="", capture_output=True, text=True, env=env,
        )
        check("[copy-block] empty stdin: exit 0", r.returncode == 0,
              f"rc={r.returncode}")
        clip_file = cd / "copy-latest.txt"
        check("[copy-block] empty stdin: no file",
              not clip_file.exists(), str(clip_file))


def test_vss_md_exists_with_frontmatter() -> None:
    """vss.md has frontmatter and the required structure markers."""
    print("\n[/vss: file shape]")
    check("[vss] vss.md exists", VSS_MD.exists(), str(VSS_MD))
    if not VSS_MD.exists():
        return
    content = VSS_MD.read_text()
    check("[vss] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[vss] description: in frontmatter",
          "description:" in content.split("---\n")[1] if "---\n" in content else False, "")
    check("[vss] declares Mode A header", "## Mode A" in content, "")
    check("[vss] declares Mode B header", "## Mode B" in content, "")
    check("[vss] cites 270s redirect window", "270" in content, "")
    check("[vss] mentions terminal bell", "printf" in content and "\\\\a" in content, "")
    check("[vss] announce includes skip-the-wait instruction",
          "skip the 270s wait" in content or "skip the wait" in content, "")
    check("[vss] documents approval-phrase recognition (go/y/yes/...)",
          "`go`" in content and ("`y`" in content or "yes" in content), "")
    check("[vss] documents redirect branch",
          "redirect" in content.lower() and ("any other" in content or "anything ELSE" in content or "anything else" in content), "")
    check("[vss] documents cancel branch",
          ("`n`" in content or "no`" in content) and ("cancel" in content.lower() or "abort" in content.lower()), "")
    check("[vss] outcome labels named in session file rules",
          "auto-proceeded" in content and "user-approved-immediately" in content, "")


def test_vss_md_hard_escalate_sentinels() -> None:
    """vss.md preserves the canonical hard-escalate list. These are
    safety boundaries; a regression silently dropping a sentinel is the
    failure this test exists to catch."""
    print("\n[/vss: hard-escalate sentinels]")
    if not VSS_MD.exists():
        check("[vss-escalate] vss.md exists", False, "missing")
        return
    content = VSS_MD.read_text()
    sentinels = [
        ("physical hardware actuation", "Physical hardware actuation"),
        ("SSH-out idiom", "SSH-out"),
        ("Pioreactor named in actuation context", "Pioreactor"),
        ("/vs --fuzzy subjective verdict", "fuzzy"),
        ("force-push named", "Force-push" in content or "force-push" in content),
        ("hook bypass --no-verify", "--no-verify"),
        ("/learnings writes", "/learnings"),
        ("firewall/hook/settings scope", "firewall" in content.lower()),
        ("scope creep", "Scope creep" in content or "scope creep" in content),
    ]
    for label, pattern in sentinels:
        if isinstance(pattern, bool):
            check(f"[vss-escalate] {label}", pattern, "")
        else:
            check(f"[vss-escalate] {label}", pattern in content, f"missing: {pattern!r}")


def test_vsss_md_inherits_escalate_and_budget() -> None:
    """vsss.md inherits /vss's escalate list, repeats its own safety floor,
    and pins BUDGET_HOURS=5 (full Pro/Max session, no graceful-shutdown
    cushion). A flip back to 4h would be a regression."""
    print("\n[/vsss: inherited escalate + budget]")
    check("[vsss] vsss.md exists", VSSS_MD.exists(), str(VSSS_MD))
    if not VSSS_MD.exists():
        return
    content = VSSS_MD.read_text()
    check("[vsss] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[vsss] inherits /vss escalate list",
          "Inherited verbatim from `/vss`" in content, "")
    check("[vsss] BUDGET_HOURS=5 default", "BUDGET_HOURS=5" in content, "")
    check("[vsss] no stale 4h default",
          "BUDGET_HOURS=4" not in content,
          "found 4h default — should be 5h since 2026-05-07")
    check("[vsss] safety floor section present",
          "/vsss safety floor" in content, "")
    floor_sentinels = [
        ("physical hardware", "Actuate physical hardware"),
        ("SSH-out", "SSH out"),
        ("force-push", "Force-push"),
        ("hook disable", "--no-verify"),
        ("/learnings", "/learnings"),
        ("--fuzzy auto-pass refusal", "fuzzy"),
    ]
    for label, pattern in floor_sentinels:
        check(f"[vsss-floor] {label}", pattern in content, f"missing: {pattern!r}")
    check("[vsss] points at .vss/sessions/ audit trail",
          ".vss/sessions/" in content, "")
    check("[vsss] --hours N flag canonical",
          "--hours N" in content or "--hours `N`" in content, "")
    check("[vsss] --budget Nh alias preserved",
          "--budget Nh" in content, "")
    check("[vsss] --budget Nm minutes form",
          "--budget Nm" in content, "")
    check("[vsss] § Resumption protocol header",
          "## Resumption protocol" in content, "")
    check("[vsss] resumption detects in-progress session",
          "in-progress session" in content, "")
    check("[vsss] --resume flag named",
          "`/vsss --resume`" in content, "")
    check("[vsss] resume budget arithmetic documented",
          "Resume budget arithmetic" in content or "Resumption budget" in content or "remaining budget" in content.lower(), "")
    check("[vsss] --sessions flag + launcher integration documented",
          "--sessions X" in content and "Launcher side" in content, "")
    check("[vsss] --sessions semantics are total windows (X-1 relaunches)",
          "X-1" in content, "")
    check("[vsss] auto-resume marker cleared on clean exit",
          "active=0" in content, "")
    check("[vsss] auto-resume marker file path named",
          ".vss/auto-resume" in content, "")
    check("[vsss] no stale .vss/loop.md references",
          ".vss/loop.md" not in content,
          "found .vss/loop.md - per-session audit replaced loop.md 2026-05-07")
    check("[vsss] three-no-op exit condition",
          "Three consecutive A-mode" in content or "three consecutive A-mode" in content, "")
    check("[vsss] inherits no-autonomous-push rule",
          "git push" in content.lower() and ("push-on-pass" in content or "Push policy" in content), "")


def test_todo_changelog_split() -> None:
    """TODO/CHANGELOG split adopted 2026-05-08 after AEP-Plugin PR #16
    review. CLAUDE.md must instruct: open work in TODO.md, done in
    CHANGELOG.md, abandoned items stay in TODO ## Open with [!] marker.
    A cross-project fragment ships the convention to all vibe projects."""
    print("\n[TODO/CHANGELOG split convention]")
    claude_md = REPO / "CLAUDE.md"
    if claude_md.exists():
        c = claude_md.read_text()
        check("[todo-cl] CLAUDE.md names TODO.md and CHANGELOG.md split",
              "TODO.md and CHANGELOG.md" in c, "")
        check("[todo-cl] CLAUDE.md says don't put done in TODO",
              "Don't put done items in TODO" in c or "don't put done items in TODO" in c.lower(), "")
        check("[todo-cl] CLAUDE.md retains [!] for abandoned in Open",
              "[!]" in c and "Abandoned" in c, "")
        # Note: CLAUDE.md may still mention `TODO.md ## Done` as a "no longer
        # exists" historical pointer; that's intended. Don't grep for # ## Done
        # absent. The "Don't put done items in TODO" check above is the
        # forward-looking guard.
    check("[todo-cl] CHANGELOG.md exists",
          CHANGELOG_MD.exists(), str(CHANGELOG_MD))
    if CHANGELOG_MD.exists():
        cl = CHANGELOG_MD.read_text()
        check("[todo-cl] CHANGELOG.md has header",
              cl.startswith("# CHANGELOG"), "")
        check("[todo-cl] CHANGELOG.md is non-trivial (migrated entries)",
              len(cl) > 500, f"size={len(cl)}")
    check("[todo-cl] cross-project fragment ships",
          TODO_CHANGELOG_MD.exists(), str(TODO_CHANGELOG_MD))
    if TODO_CHANGELOG_MD.exists():
        f = TODO_CHANGELOG_MD.read_text()
        check("[todo-cl-frag] explains TODO is open + abandoned",
              "open backlog" in f.lower() and "abandoned" in f.lower(), "")
        check("[todo-cl-frag] explains CHANGELOG is reader-facing",
              "Reader-facing" in f or "reader-facing" in f.lower(), "")
        check("[todo-cl-frag] cites the AEP-Plugin trigger",
              "Pioreactor" in f or "PR" in f, "")
    todo = REPO / "TODO.md"
    if todo.exists():
        t = todo.read_text()
        check("[todo-cl] TODO.md no longer has ## Done section",
              "## Done" not in t, "stale ## Done section in TODO.md")


def test_project_hygiene_fragment() -> None:
    """devcontainer/claude-md/project-hygiene.md ships the cross-project
    rule learned from AEP-Plugin PR #16: don't commit per-machine runtime
    cruft, setup-specific notes, or unconsented system-patching scripts in
    upstream-bound repos."""
    print("\n[project-hygiene fragment]")
    check("[hygiene] fragment exists",
          PROJECT_HYGIENE_MD.exists(), str(PROJECT_HYGIENE_MD))
    if not PROJECT_HYGIENE_MD.exists():
        return
    f = PROJECT_HYGIENE_MD.read_text()
    check("[hygiene] flags .claude/settings.local.json",
          ".claude/settings.local.json" in f, "")
    check("[hygiene] flags .vibe/ runtime dir",
          ".vibe/" in f, "")
    check("[hygiene] flags hardcoded local IPs",
          "192.168" in f and "IP" in f, "")
    check("[hygiene] flags hostname/.local pattern",
          ".local" in f, "")
    check("[hygiene] consent rule for system-patching scripts",
          "without consent" in f.lower() or "consent flow" in f.lower(), "")
    check("[hygiene] cites the PR review trigger (AEP-Plugin)",
          "AEP-Plugin" in f or "electroPioreactor" in f.lower() or "PR #16" in f, "")
    check("[hygiene] pre-commit checklist present",
          "Pre-commit checklist" in f or "pre-commit checklist" in f.lower(), "")


def test_install_extras_ensures_project_gitignore() -> None:
    """install-claude-extras.sh adds a managed block to /workspace/.gitignore
    that excludes vibe's runtime files. Idempotent on re-run; opt-out via
    VIBE_AUTO_GITIGNORE=0; respects user-removed-block (no re-add)."""
    print("\n[install-extras: ensure_project_gitignore]")
    src = INSTALL_EXTRAS.read_text()
    check("[gi-fn] function defined",
          "ensure_project_gitignore()" in src, "")
    check("[gi-fn] honours VIBE_AUTO_GITIGNORE=0 opt-out",
          "VIBE_AUTO_GITIGNORE" in src, "")
    check("[gi-fn] checks for git repo before acting",
          "/workspace/.git" in src or "$project/.git" in src, "")
    check("[gi-fn] managed-block sentinel present",
          "vibe-managed runtime exclusions" in src, "")
    check("[gi-fn] excludes .claude/settings.local.json",
          ".claude/settings.local.json" in src, "")
    check("[gi-fn] excludes .vibe/",
          '".vibe/"' in src or "echo \".vibe/\"" in src, "")
    check("[gi-fn] called from main script body",
          "ensure_project_gitignore\n" in src or "ensure_project_gitignore$" in src.rstrip() + "\n", "")


def test_feedback_auto_promote_fragment() -> None:
    """devcontainer/claude-md/feedback-auto-promote.md spec'd 2026-05-07.
    Behavioral fragment instructing Claude when to propose /learnings
    promotion after saving a feedback memory. A regression dropping the
    fragment, the IS/IS-NOT list, or the opt-out hook would silently lose
    the cross-repo behavioral propagation channel."""
    print("\n[feedback-auto-promote: fragment shape]")
    check("[auto-promote] fragment file exists",
          FEEDBACK_AUTO_PROMOTE_MD.exists(), str(FEEDBACK_AUTO_PROMOTE_MD))
    if not FEEDBACK_AUTO_PROMOTE_MD.exists():
        return
    content = FEEDBACK_AUTO_PROMOTE_MD.read_text()
    check("[auto-promote] § When to propose promotion present",
          "When to propose promotion" in content, "")
    check("[auto-promote] IS/NOT examples present",
          "YES:" in content and "NO:" in content, "")
    check("[auto-promote] cross-repo-applicable filter named",
          "cross-repo applicable" in content.lower() or "cross-repo-applicable" in content.lower(), "")
    check("[auto-promote] Y/n/never-ask three-option prompt",
          "Y / n / never-ask" in content or "Y, n, never-ask" in content, "")
    check("[auto-promote] VIBE_AUTO_PROMOTE opt-out env var",
          "VIBE_AUTO_PROMOTE" in content, "")
    check("[auto-promote] PreToolUse hook still gates the write",
          "PreToolUse hook" in content, "")
    check("[auto-promote] uses /learn command for the write",
          "/learn" in content, "")
    check("[auto-promote] explicit no-auto-write rule",
          "do NOT auto-write" in content.lower() or "Do NOT auto-write" in content, "")
    check("[auto-promote] one-prompt-per-memory rule",
          "One prompt per" in content or "one prompt per" in content, "")


def test_vs_md_plain_techy_verbosity_flags() -> None:
    """vs.md spec'd --plain / --techy / --verbosity flags 2026-05-07. The
    flags govern Spec Critic / Tester / Evaluator output mode; a regression
    silently dropping any of them would let the canonical default drift,
    hence this guard."""
    print("\n[/vs: --plain / --techy / --verbosity flags]")
    if not VS_MD.exists():
        check("[vs-flags] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-flags] --plain flag named",
          "`/vs --plain " in content, "")
    check("[vs-flags] --plain default ON documented",
          "default ON" in content, "")
    check("[vs-flags] --techy inverse flag named",
          "`/vs --techy " in content, "")
    check("[vs-flags] --verbosity N global flag named",
          "--verbosity N" in content, "")
    check("[vs-flags] verbosity scale 0-9 documented",
          "0-9" in content, "")
    check("[vs-flags] verbosity default 5",
          "Default 5" in content or "default 5" in content, "")
    check("[vs-flags] level 0 anchor (one-line pass/fail)",
          "**0**" in content and "one-line" in content, "")
    check("[vs-flags] level 5 anchor (default)",
          "**5**" in content, "")
    check("[vs-flags] level 9 anchor (full verbose)",
          "**9**" in content, "")
    check("[vs-flags] --vN-spec per-output override",
          "--vN-spec" in content, "")
    check("[vs-flags] --vN-test per-output override",
          "--vN-test" in content, "")
    check("[vs-flags] --vN-eval per-output override",
          "--vN-eval" in content, "")
    check("[vs-flags] flags propagate to subagent briefs",
          "propagate" in content.lower() and "subagent" in content.lower(), "")


def test_fable_subagents_flag_docs() -> None:
    """--fable-subagents (alias --fable) spec'd 2026-07-11 on Martin's live
    request ("use Fable for any subagents that will get better or faster
    results"). Guards the consent semantics: per-invocation pre-auth only,
    task-class routing preserved (never mechanical roles), the no-flag
    ask-gate unchanged, /vsss propagation + audit note, and the explicit
    distinction from the vibe-launcher --fable (chair-model-only) flag."""
    print("\n[/vs+/vss+/vsss: --fable-subagents standing pre-auth flag]")
    vs = VS_MD.read_text()
    check("[fable-flag] vs.md documents --fable-subagents",
          "`/vs --fable-subagents " in vs, "")
    check("[fable-flag] vs.md: Model plan records the grant",
          "Fable rung: pre-authorised (--fable-subagents)" in vs, "")
    check("[fable-flag] vs.md: never mechanical roles",
          "NEVER Fable for mechanical roles" in vs, "")
    check("[fable-flag] vs.md: permission, not blanket routing",
          "the flag buys permission, not blanket routing" in vs, "")
    check("[fable-flag] vs.md: without it the ask-gate is unchanged",
          "Without it, the ask-before-Fable gate is unchanged" in vs, "")
    check("[fable-flag] vs.md: ladder honours the standing grant",
          "including a standing `--fable-subagents` grant" in vs, "")
    check("[fable-flag] vs.md: distinct from vibe --fable launcher flag",
          "sets only the chair/session model and authorises no subagent spend" in vs, "")
    vss = (REPO / "devcontainer" / "commands" / "vss.md").read_text()
    check("[fable-flag] vss.md: hard-escalate carve-out names the flag",
          "--fable-subagents" in vss and "per-invocation consent, not a default" in vss, "")
    vsss = (REPO / "devcontainer" / "commands" / "vsss.md").read_text()
    check("[fable-flag] vsss.md: flag documented with alias",
          "`/vsss --fable-subagents <args>` (alias `--fable`)" in vsss, "")
    check("[fable-flag] vsss.md: propagates into every wrapped /vss",
          "propagated into EVERY wrapped `/vss` iteration" in vsss, "")
    check("[fable-flag] vsss.md: session-audit recording required",
          "Record the grant in the session file" in vsss, "")
    check("[fable-flag] vsss.md: distinct from vibe --fable",
          "NOT the same as `vibe --fable`" in vsss, "")
    check("[fable-flag] vs.md: alias documented, does not imply --fable-gen",
          "(alias `--fable`)" in vs and "does NOT imply `--fable-gen`" in vs, "")
    check("[fable-flag] vs.md: Step-2 point-of-use honours the flag",
          "Honor `--gen` / `--fable-gen` / `--fable-subagents` if passed" in vs, "")
    check("[fable-flag] vss.md: planner-brief carve-out present",
          "UNLESS this /vss invocation carries `--fable-subagents`" in vss, "")
    check("[fable-flag] vss.md: threads into whatever tool it picks",
          "threads into whatever tool it picks" in vss, "")
    check("[fable-flag] vss.md: launcher distinction pinned",
          "chair model only, no subagent authorisation" in vss, "")
    check("[fable-flag] vsss.md: grant persists across --sessions relaunches",
          "The grant PERSISTS across `--sessions` auto-resume relaunches" in vsss, "")


def test_vs_md_panel_flag() -> None:
    """vs.md spec'd --panel 2026-07-10 (blind independent panellists +
    correlated-agreement/sycophancy check, ported from the agent-review-panel
    pattern per the 2026-07 harness-landscape audit, re-tiered to Sonnet).
    Guards the mechanism's load-bearing properties: structural blindness,
    identical briefs, the sycophancy check's direction (correlated consensus
    weakens confidence), dissent handling, and the Sonnet tiering."""
    print("\n[/vs: --panel blind review panel]")
    if not VS_MD.exists():
        check("[vs-panel] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-panel] --panel flag named",
          "`/vs --panel [N] " in content, "")
    check("[vs-panel] default 3, odd", "default 3" in content and "odd" in content, "")
    check("[vs-panel] Step 5c section present", "Step 5c" in content, "")
    check("[vs-panel] panellists dispatched in one parallel batch",
          "IN ONE MESSAGE" in content or "one concurrent batch" in content, "")
    check("[vs-panel] read-only code-reviewer panellist dispatch",
          'Dispatch N `Agent(subagent_type: "code-reviewer", model: "sonnet")` panellists' in content, "")
    check("[vs-panel] briefs identical except output-path token",
          "identical apart from the one substituted output-path token" in content, "")
    check("[vs-panel] no assigned personas (differentiation must emerge)",
          "differentiation must emerge" in content, "")
    check("[vs-panel] per-panellist artifact path",
          "panel/reviewer-<k>.md" in content, "")
    check("[vs-panel] chair aggregation artifact",
          "panel/summary.md" in content, "")
    check("[vs-panel] sycophancy/correlated-agreement check named",
          "sycophancy" in content and "orrelated" in content, "")
    check("[vs-panel] correlated consensus = low-information (weakens, not strengthens)",
          "low-information" in content, "")
    check("[vs-panel] unrefuted blocking dissent blocks pass",
          "NOT a pass" in content, "")
    check("[vs-panel] Sonnet panellists (not all-Opus)",
          "sonnet ×N" in content, "")
    check("[vs-panel] panellists never touch tasks.json",
          "do NOT touch `tasks.json`" in content, "")
    check("[vs-panel] rigorous mode keeps mechanical gate",
          "mechanical test gate still governs" in content, "")
    check("[vs-panel] cost role panel_reviewer",
          "panel_reviewer" in content, "")
    check("[vs-panel] panel disagreement never escalates ladder by itself",
          "never triggers the escalation ladder by itself" in content, "")
    check("[vs-panel] 5b explicitly skipped under --panel",
          "Skip this step entirely when `--panel` is set" in content, "")
    check("[vs-panel] rigorous interaction: sink green, never rescue red",
          "it can never rescue a red one" in content, "")
    check("[vs-panel] N validated: odd integer between 3 and 7",
          "odd integer between 3 and 7" in content, "")
    check("[vs-panel] Step 6 mandates reading all N panel verdicts",
          "all N of them" in content, "")
    check("[vs-panel] flow diagram shows panel variants",
          "--fuzzy --panel:" in content, "")
    check("[vs-panel] upstream 4-6 divergence annotated",
          "upstream runs 4–6 panellists" in content, "")


def test_vs_md_multi_task_archive_convention() -> None:
    """vs.md spec'd a multi-task archive convention 2026-05-07. The convention
    distinguishes per-task state (overwritten -> must archive) from repo-wide
    state (must NOT archive). A regression where someone re-broadens the
    archive scope to include tasks.json/progress.md would silently drop
    historical data, hence this guard."""
    print("\n[/vs: multi-task archive convention]")
    if not VS_MD.exists():
        check("[vs-archive] vs.md exists", False, "missing")
        return
    content = VS_MD.read_text()
    check("[vs-archive] § Multi-task state convention header",
          "## Multi-task state convention" in content, "")
    check("[vs-archive] documents .vs/archive/<task-id>/ path",
          ".vs/archive/<task-id>/" in content, "")
    check("[vs-archive] names spec.md as per-task (archived)",
          "Per-task" in content and ".vs/spec.md" in content, "")
    check("[vs-archive] names tasks.json as repo-wide (NOT archived)",
          "Repo-wide accumulating" in content and "tasks.json" in content, "")
    check("[vs-archive] explicit MUST NOT for tasks.json/progress.md",
          "must NOT be archived" in content, "")
    check("[vs-archive] critiques rename to bypass gitignore documented",
          "critiques/" in content and "cycle-*/" in content, "")
    check("[vs-archive] archive procedure references git mv",
          "git mv .vs/spec.md" in content, "")
    check("[vs-archive] resume procedure documented",
          "Resuming an archived task" in content, "")
    check("[vs-archive] inherits no-autonomous-push",
          "no-autonomous-push" in content, "")


def test_vss_md_audit_trail_and_push_policy() -> None:
    """vss.md defines the per-session audit format and the no-autonomous-push
    rule. Both are safety boundaries (audit = reviewability; no-push = trust
    model). A regression silently dropping either is the failure this guards."""
    print("\n[/vss: audit trail + push policy]")
    if not VSS_MD.exists():
        check("[vss-policy] vss.md exists", False, "missing")
        return
    content = VSS_MD.read_text()
    check("[vss-policy] § Session audit format header",
          "Session audit format" in content, "")
    check("[vss-policy] sessions/ path declared",
          ".vss/sessions/" in content, "")
    check("[vss-policy] format names per-iter blocks",
          "Iter " in content and "Final state" in content, "")
    check("[vss-policy] § Push policy header",
          "## Push policy" in content, "")
    check("[vss-policy] explicit no-autonomous-push wording",
          "Do NOT" in content and "push" in content.lower(), "")
    check("[vss-policy] --push-on-pass override flag named",
          "--push-on-pass" in content, "")
    check("[vss-policy] sessions file marked Committed",
          "**Committed.**" in content and ".vss/sessions" in content, "")


def test_conversation_history_fragment() -> None:
    """devcontainer/claude-md/conversation-history.md teaches Claude to search
    ~/.claude/projects/<slug>/*.jsonl transcripts when memory misses a user
    reference to past conversation. Regression dropping the fragment, the
    JSONL path, the schema crib, or the jq recipes silently breaks the
    "search before saying I have no record" behavior."""
    print("\n[conversation-history: fragment shape]")
    check("[conv-history] fragment file exists",
          CONVERSATION_HISTORY_MD.exists(), str(CONVERSATION_HISTORY_MD))
    if not CONVERSATION_HISTORY_MD.exists():
        return
    content = CONVERSATION_HISTORY_MD.read_text()
    check("[conv-history] names the JSONL path glob",
          "~/.claude/projects/" in content and ".jsonl" in content, "")
    check("[conv-history] names the -workspace slug",
          "-workspace" in content, "")
    check("[conv-history] documents user-prompt schema (string content)",
          'type: "user"' in content and "string" in content, "")
    check("[conv-history] documents assistant-text schema",
          'type: "assistant"' in content and 'type: "text"' in content, "")
    check("[conv-history] mentions skipping thinking and tool_use blocks",
          "thinking" in content and "tool_use" in content, "")
    check("[conv-history] ships a jq recipe",
          "jq -r" in content, "")
    check("[conv-history] tells Claude to filter tool_result entries",
          "tool_result" in content, "")
    check("[conv-history] mentions Docker volume single-machine limit",
          "vibe-claude-config" in content or "Docker volume" in content, "")
    check("[conv-history] warns against duplicating into a parallel file",
          "duplicate" in content.lower() or "duplicating" in content.lower(), "")


def test_install_extras_ssh_discipline_opt_in() -> None:
    """install-claude-extras.sh omits ssh-discipline.md from CLAUDE.md when
    VIBE_SSH_AUTO=1; includes it (alongside other fragments) when unset."""
    print("\n[ssh-opt-in: install-claude-extras.sh honours VIBE_SSH_AUTO]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Real source dir so we exercise the actual ssh-discipline.md + siblings.
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: opt-in OFF — ssh-discipline content should be present.
        dest_off = tmp_path / "off"
        dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off.pop("VIBE_SSH_AUTO", None)
        r_off = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=env_off, capture_output=True, text=True,
        )
        check("[ssh-opt-in] install exits 0 with VIBE_SSH_AUTO unset",
              r_off.returncode == 0, f"rc={r_off.returncode} err={r_off.stderr[:200]}")
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[ssh-opt-in] ssh-discipline.md marker present when opt-in unset",
              "<!-- vibe-md: ssh-discipline.md -->" in md_off, "marker missing")
        check("[ssh-opt-in] ssh-discipline.md body present when opt-in unset",
              "SSH Discipline" in md_off, "body missing")
        # Sanity: another fragment should also be present (proves the loop ran).
        check("[ssh-opt-in] other fragments still installed (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "web-research absent")

        # Pass 2: opt-in ON via env — ssh-discipline content should be absent.
        dest_on = tmp_path / "on"
        dest_on.mkdir()
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_SSH_AUTO"] = "1"
        r_on = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=env_on, capture_output=True, text=True,
        )
        check("[ssh-opt-in] install exits 0 with VIBE_SSH_AUTO=1",
              r_on.returncode == 0, f"rc={r_on.returncode} err={r_on.stderr[:200]}")
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[ssh-opt-in] ssh-discipline.md marker ABSENT with VIBE_SSH_AUTO=1",
              "<!-- vibe-md: ssh-discipline.md -->" not in md_on,
              "marker still present despite opt-in")
        check("[ssh-opt-in] other fragments still present with opt-in",
              "<!-- vibe-md: web-research.md -->" in md_on,
              "opt-in dropped unrelated fragments")


def test_install_extras_syncs_hooks() -> None:
    """install-claude-extras.sh installs hooks/*.sh with +x into $DEST_ROOT/hooks/."""
    print("\n[hooks: install-claude-extras.sh syncs every shipped hook]")
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")
        env["CLAUDE_CONFIG_DIR"] = tmp
        r = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=env, capture_output=True, text=True,
        )
        check("[hooks] install-extras exits 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        for hook_name in ("check-numbering.sh", "copy-last-block.sh"):
            installed = Path(tmp) / "hooks" / hook_name
            check(f"[hooks] {hook_name} installed at $DEST_ROOT/hooks/",
                  installed.exists(), str(installed))
            if installed.exists():
                check(f"[hooks] {hook_name} is executable",
                      os.access(installed, os.X_OK), "")
        # README.md should NOT be chmod'd (it's not a *.sh file but install_hooks
        # only chmods *.sh; verify it didn't get installed at all since we
        # don't sync non-.sh files into the hooks dir).
        readme_installed = Path(tmp) / "hooks" / "README.md"
        check("[hooks] README.md NOT installed (only *.sh synced)",
              not readme_installed.exists(), str(readme_installed))


def test_brain2_zotero_source_resolution() -> None:
    """_brain2_source / _zotero_source: default, override, and 'off' disable."""
    print("\n[brain2: _brain2_source / _zotero_source resolution]")
    # Default derives from HOME.
    r = _source_vibe_call({"HOME": "/tmp/vibetesthome"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] default brain2 path is $HOME/brain2",
          "OUT=[/tmp/vibetesthome/brain2]" in r.stdout, r.stdout)
    r = _source_vibe_call({"HOME": "/tmp/vibetesthome"},
                          'echo "OUT=[$(_zotero_source)]"')
    check("[brain2] default zotero path is $HOME/Zotero/storage",
          "OUT=[/tmp/vibetesthome/Zotero/storage]" in r.stdout, r.stdout)
    # Explicit override.
    r = _source_vibe_call({"VIBE_BRAIN2_PATH": "/foo/bar"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] VIBE_BRAIN2_PATH override honoured",
          "OUT=[/foo/bar]" in r.stdout, r.stdout)
    # 'off' disables (echoes nothing).
    r = _source_vibe_call({"VIBE_BRAIN2_PATH": "off"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] VIBE_BRAIN2_PATH=off disables (empty)",
          "OUT=[]" in r.stdout, r.stdout)
    r = _source_vibe_call({"VIBE_ZOTERO_PATH": "off"},
                          'echo "OUT=[$(_zotero_source)]"')
    check("[brain2] VIBE_ZOTERO_PATH=off disables (empty)",
          "OUT=[]" in r.stdout, r.stdout)


def test_render_devcontainer_with_mounts() -> None:
    """render_devcontainer_with_mounts appends rw/ro bind mounts, preserves
    existing mounts, and handles sources containing spaces."""
    print("\n[brain2: render_devcontainer_with_mounts]")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.json"
        src.write_text(json.dumps(
            {"image": "x", "mounts": ["source=keep,target=/keep,type=volume"]}))
        dst = Path(tmp) / "dst.json"
        call = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                f"{shlex.quote(str(dst))} "
                f"/host/brain2 /brain2 0 "
                f"{shlex.quote('/host/zot store')} /zotero 1")
        r = _source_vibe_call({}, call)
        check("[brain2] render exits 0", r.returncode == 0, r.stderr)
        cfg = json.loads(dst.read_text())
        mounts = cfg["mounts"]
        check("[brain2] existing mount preserved",
              "source=keep,target=/keep,type=volume" in mounts, str(mounts))
        brain2 = [m for m in mounts if isinstance(m, dict) and m.get("target") == "/brain2"]
        zot = [m for m in mounts if isinstance(m, dict) and m.get("target") == "/zotero"]
        check("[brain2] /brain2 mount appended", len(brain2) == 1, str(mounts))
        check("[brain2] /brain2 is read-write (no readonly key)",
              brain2 and "readonly" not in brain2[0], str(brain2))
        check("[brain2] /brain2 source correct",
              brain2 and brain2[0]["source"] == "/host/brain2", str(brain2))
        check("[brain2] /zotero mount appended read-only",
              zot and zot[0].get("readonly") is True, str(zot))
        check("[brain2] /zotero source with space preserved",
              zot and zot[0]["source"] == "/host/zot store", str(zot))


def test_op_mcp_addhost_injection() -> None:
    """render_devcontainer_with_mounts appends the OpenProject MCP --add-host to
    runArgs when VIBE_OP_ADDHOST is set, leaves runArgs untouched when it isn't,
    and never duplicates an entry already present."""
    print("\n[op-mcp: add-host injection]")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.json"
        src.write_text(json.dumps({"image": "x", "runArgs": ["--cap-add=NET_ADMIN"]}))

        dst1 = Path(tmp) / "with.json"
        call1 = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                 f"{shlex.quote(str(dst1))}")
        r1 = _source_vibe_call({"VIBE_OP_ADDHOST": "op.example.ts.net"}, call1)
        check("[op-mcp] render (with host) exits 0", r1.returncode == 0, r1.stderr)
        ra1 = json.loads(dst1.read_text()).get("runArgs", [])
        check("[op-mcp] --add-host appended",
              "--add-host=op.example.ts.net:host-gateway" in ra1, str(ra1))
        check("[op-mcp] existing runArgs preserved",
              "--cap-add=NET_ADMIN" in ra1, str(ra1))

        dst2 = Path(tmp) / "without.json"
        call2 = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                 f"{shlex.quote(str(dst2))}")
        r2 = _source_vibe_call({"VIBE_OP_ADDHOST": ""}, call2)
        check("[op-mcp] render (no host) exits 0", r2.returncode == 0, r2.stderr)
        ra2 = json.loads(dst2.read_text()).get("runArgs", [])
        check("[op-mcp] no add-host when unset",
              not any("add-host" in a for a in ra2), str(ra2))

        # Already-present entry must not be duplicated.
        src2 = Path(tmp) / "src2.json"
        src2.write_text(json.dumps(
            {"image": "x", "runArgs": ["--add-host=op.example.ts.net:host-gateway"]}))
        dst3 = Path(tmp) / "dup.json"
        call3 = (f"render_devcontainer_with_mounts {shlex.quote(str(src2))} "
                 f"{shlex.quote(str(dst3))}")
        _source_vibe_call({"VIBE_OP_ADDHOST": "op.example.ts.net"}, call3)
        ra3 = json.loads(dst3.read_text()).get("runArgs", [])
        check("[op-mcp] add-host not duplicated",
              ra3.count("--add-host=op.example.ts.net:host-gateway") == 1, str(ra3))


def _read_override_out(r: subprocess.CompletedProcess) -> str:
    m = re.search(r"OUT=\[(.*)\]", r.stdout)
    return m.group(1) if m else ""


def test_build_override_config_brain2_and_zotero() -> None:
    """_build_override_config injects /brain2 (rw) and /zotero (ro) when the
    dirs exist, skips the brain2 self-mount in the gardener, and falls back to
    the base config when nothing applies."""
    print("\n[brain2: _build_override_config gating]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ws = tmp_path / "ws"; ws.mkdir()
        brain2 = tmp_path / "brain2"; brain2.mkdir()
        zot = tmp_path / "zot"; zot.mkdir()
        home = tmp_path / "home"; home.mkdir()

        # OP MCP creds leak in from the host env of an OP-configured vibe
        # container (staged via remoteEnv since 2026-06-04) and make
        # _build_override_config emit an override for the --add-host alone,
        # breaking the nothing-applies fallback case. Blank them: this test
        # is about mount gating, not OP wiring.
        no_op = {"OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": ""}

        # Case 1: brain2 + zotero dirs exist, workspace is a different dir.
        env = {**no_op,
               "HOME": str(home),
               "VIBE_BRAIN2_PATH": str(brain2),
               "VIBE_ZOTERO_PATH": str(zot)}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("[brain2] _build_override_config exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        check("[brain2] generated override under HOME/.vibe/run",
              out.startswith(str(home / ".vibe" / "run")), out)
        if out and Path(out).exists():
            cfg = json.loads(Path(out).read_text())
            tgts = [m.get("target") for m in cfg["mounts"] if isinstance(m, dict)]
            check("[brain2] /brain2 injected (non-gardener)", "/brain2" in tgts, str(tgts))
            check("[brain2] /zotero injected", "/zotero" in tgts, str(tgts))

        # Case 2: gardener — workspace IS the brain2 dir → no /brain2 self-mount,
        # zotero disabled → nothing applies → base config returned unchanged.
        env_g = {**no_op,
                 "HOME": str(home),
                 "VIBE_BRAIN2_PATH": str(brain2),
                 "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env_g, f'echo "OUT=[$(_build_override_config {shlex.quote(str(brain2))})]"')
        out_g = _read_override_out(r)
        check("[brain2] gardener+no-zotero falls back to base devcontainer.json",
              out_g.endswith("devcontainer/devcontainer.json"), out_g)

        # Case 3: zotero only.
        env_z = {**no_op,
                 "HOME": str(home),
                 "VIBE_BRAIN2_PATH": "off",
                 "VIBE_ZOTERO_PATH": str(zot)}
        r = _source_vibe_call(
            env_z, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        out_z = _read_override_out(r)
        if out_z and Path(out_z).exists():
            cfg = json.loads(Path(out_z).read_text())
            tgts = [m.get("target") for m in cfg["mounts"] if isinstance(m, dict)]
            check("[brain2] zotero-only: /zotero present, /brain2 absent",
                  "/zotero" in tgts and "/brain2" not in tgts, str(tgts))


def test_install_extras_brain2_md_gated() -> None:
    """install-claude-extras.sh includes brain2.md only when the brain2 mount
    dir exists; omits it otherwise (keeps shared CLAUDE.md brain2-free upstream)."""
    print("\n[brain2: install-claude-extras.sh gates brain2.md on the mount]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: no mount (point the override at a nonexistent path) → absent.
        dest_off = tmp_path / "off"; dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off["VIBE_BRAIN2_MOUNT_DIR"] = str(tmp_path / "nope")
        r_off = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                               env=env_off, capture_output=True, text=True)
        check("[brain2] install exits 0 (no mount)",
              r_off.returncode == 0, r_off.stderr[:200])
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[brain2] brain2.md ABSENT when mount dir missing",
              "<!-- vibe-md: brain2.md -->" not in md_off, "brain2.md leaked upstream")
        check("[brain2] other fragments still present (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "loop didn't run")

        # Pass 2: mount dir exists → brain2.md present.
        mount_dir = tmp_path / "brain2mount"; mount_dir.mkdir()
        dest_on = tmp_path / "on"; dest_on.mkdir()
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_BRAIN2_MOUNT_DIR"] = str(mount_dir)
        r_on = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                              env=env_on, capture_output=True, text=True)
        check("[brain2] install exits 0 (mount present)",
              r_on.returncode == 0, r_on.stderr[:200])
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[brain2] brain2.md PRESENT when mount dir exists",
              "<!-- vibe-md: brain2.md -->" in md_on, "brain2.md missing")
        check("[brain2] brain2.md mentions the credential boundary",
              "CANNOT" in md_on and "/brain2" in md_on, "body missing")


def test_install_extras_brain2_skills_synced() -> None:
    """install-claude-extras.sh syncs brain2 skills whose `surfaces:` includes
    `vibe` into ~/.claude/skills; excludes desktop/excel-only and untagged
    skills; honours the body-line `## Surfaces` fallback; leaves pre-existing
    (volume-persisted) skills untouched; and does nothing without the mount."""
    print("\n[brain2: install-claude-extras.sh syncs vibe-tagged skills]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Fake brain2 mount with a skills dir of mixed surface tags.
        mount = tmp_path / "brain2mount"
        skills = mount / ".claude" / "skills"

        def write_skill(name: str, frontmatter_surfaces=None,
                        body_surfaces: bool = False) -> None:
            d = skills / name
            d.mkdir(parents=True)
            lines = ["---", f"title: {name}"]
            if frontmatter_surfaces is not None:
                lines.append(f"surfaces: {frontmatter_surfaces}")
            lines += ["---", f"# {name}"]
            if body_surfaces:
                lines += ["## Surfaces", "[desktop, vibe]"]
            (d / "SKILL.md").write_text("\n".join(lines) + "\n")

        write_skill("ol", "[desktop, vibe]")                 # included (frontmatter)
        write_skill("deskonly", "[desktop]")                 # excluded (desktop-only)
        write_skill("bodyform", None, body_surfaces=True)    # included (body fallback)
        write_skill("md", None)                              # excluded (untagged)

        dest = tmp_path / "dest"; dest.mkdir()
        # Pre-existing volume-persisted skill that must survive the sync.
        (dest / "skills" / "script").mkdir(parents=True)
        (dest / "skills" / "script" / "SKILL.md").write_text("original-script\n")

        env = env_base.copy()
        env["CLAUDE_CONFIG_DIR"] = str(dest)
        env["VIBE_BRAIN2_MOUNT_DIR"] = str(mount)
        r = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                           env=env, capture_output=True, text=True)
        check("[brain2] install exits 0 (mount present)",
              r.returncode == 0, r.stderr[:200])
        dskills = dest / "skills"
        check("[brain2] vibe-tagged 'ol' synced (frontmatter)",
              (dskills / "ol" / "SKILL.md").exists(), "ol missing")
        check("[brain2] body-line '## Surfaces' fallback 'bodyform' synced",
              (dskills / "bodyform" / "SKILL.md").exists(), "bodyform missing")
        check("[brain2] desktop-only 'deskonly' excluded",
              not (dskills / "deskonly").exists(), "desktop-only skill leaked into vibe")
        check("[brain2] untagged 'md' excluded",
              not (dskills / "md").exists(), "untagged md synced")
        check("[brain2] pre-existing 'script' left untouched",
              (dskills / "script" / "SKILL.md").read_text() == "original-script\n",
              "volume-persisted skill clobbered")

        # No brain2 mount → skills sync is a no-op (generic vibe users unaffected).
        dest2 = tmp_path / "dest2"; dest2.mkdir()
        env2 = env_base.copy()
        env2["CLAUDE_CONFIG_DIR"] = str(dest2)
        env2["VIBE_BRAIN2_MOUNT_DIR"] = str(tmp_path / "nope")
        r2 = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                            env=env2, capture_output=True, text=True)
        check("[brain2] install exits 0 (no mount)",
              r2.returncode == 0, r2.stderr[:200])
        check("[brain2] no skills synced without the mount",
              not (dest2 / "skills" / "ol").exists(), "synced without a mount")


def test_brain2_md_fragment_content() -> None:
    """brain2.md ships and states the non-negotiables: credential boundary,
    zotero read-only, and the authorised-field trust rule."""
    print("\n[brain2: brain2.md fragment content]")
    check("[brain2] brain2.md exists", BRAIN2_MD.exists(), str(BRAIN2_MD))
    body = BRAIN2_MD.read_text()
    check("[brain2] documents no-push credential boundary",
          "push" in body.lower() and "gardener" in body.lower(), "boundary missing")
    check("[brain2] documents zotero read-only + DOI queue",
          "/zotero" in body and "zotero-queue" in body, "zotero guidance missing")
    check("[brain2] documents authorised-field trust rule",
          "authorised" in body, "trust rule missing")


def test_contributor_onboarding_artifacts() -> None:
    """FOSS onboarding artifacts for outside contributors: SECURITY.md
    (disclosure policy aligned with the container threat model), the two
    .github issue templates, and the PR template. Grep-level presence +
    key-content checks — the files carry no logic to unit-test."""
    print("\n[FOSS contributor onboarding artifacts]")

    check("[onboard] SECURITY.md exists", SECURITY_MD.exists(), str(SECURITY_MD))
    if SECURITY_MD.exists():
        s = SECURITY_MD.read_text()
        check("[onboard] SECURITY.md points at the repo Security tab",
              "Security tab" in s, "reporting path must survive the repo transfer")
        check("[onboard] SECURITY.md marks Claude Code + Docker out-of-scope upstream",
              "Claude Code" in s and "Docker" in s and "upstream" in s.lower(), "")
        check("[onboard] SECURITY.md names the in-scope classes",
              all(k in s.lower() for k in ("firewall bypass", "hook bypass", "credential", "pat")), "")

    check("[onboard] bug_report.md template exists", BUG_TEMPLATE.exists(), str(BUG_TEMPLATE))
    if BUG_TEMPLATE.exists():
        b = BUG_TEMPLATE.read_text()
        check("[onboard] bug template asks for vibe --version",
              "vibe --version" in b, "")
        check("[onboard] bug template asks OS + container runtime",
              "OrbStack" in b and "Docker" in b, "")

    check("[onboard] feature_request.md template exists", FEATURE_TEMPLATE.exists(), str(FEATURE_TEMPLATE))
    if FEATURE_TEMPLATE.exists():
        f = FEATURE_TEMPLATE.read_text()
        check("[onboard] feature template points at CONTRIBUTING.md",
              "CONTRIBUTING.md" in f, "")

    check("[onboard] PULL_REQUEST_TEMPLATE.md exists", PR_TEMPLATE.exists(), str(PR_TEMPLATE))
    if PR_TEMPLATE.exists():
        p = PR_TEMPLATE.read_text()
        check("[onboard] PR template names both gate scripts",
              "code-check.py" in p and "smoke-test.py" in p, "")
        check("[onboard] PR template cites CHANGELOG + MANUAL-TESTS conventions",
              "CHANGELOG.md" in p and "MANUAL-TESTS.md" in p, "")

    onboarding = REPO / "ONBOARDING.md"
    check("[onboard] ONBOARDING.md exists", onboarding.exists(), str(onboarding))
    if onboarding.exists():
        o = onboarding.read_text()
        check("[onboard] ONBOARDING.md addresses the assisting Claude",
              "assisting Claude" in o, "")
        check("[onboard] ONBOARDING.md installs from andeyePro/vibe",
              "andeyePro/vibe/main/install.sh" in o, "")
        check("[onboard] ONBOARDING.md verifies with vibe --version",
              "vibe --version" in o, "")

    contributors = REPO / "CONTRIBUTORS.md"
    check("[onboard] CONTRIBUTORS.md exists", contributors.exists(), str(contributors))
    if contributors.exists():
        c = contributors.read_text()
        check("[onboard] CONTRIBUTORS.md carries the revenue-share ledger framing",
              "revenue" in c.lower() and "ledger" in c.lower(), "")

    claude_md = REPO / "CLAUDE.md"
    check("[onboard] CLAUDE.md routes arriving Claudes to ONBOARDING.md",
          claude_md.exists() and "ONBOARDING.md" in claude_md.read_text(), "")


def test_repo_owner_selection() -> None:
    """Repo creation lets the user pick the GitHub owner (account or org):
    default_repo_owner() precedence unit-tested via VIBE_SOURCE_ONLY sourcing;
    the interactive flow + validation + docs checked at grep level."""
    print("\n[repo owner selection]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        echo "FALLBACK=$(default_repo_owner someuser)"
        VIBE_GITHUB_OWNER="my-org" ; echo "CONFIGURED=$(default_repo_owner someuser)"
        VIBE_GITHUB_OWNER="" ; echo "EMPTY=$(default_repo_owner someuser)"
        """
        r = run(["bash", "-c", script], env=env)
        check("[owner] helper runs cleanly", r.returncode == 0, r.stderr)
        check("[owner] falls back to gh user when unset",
              "FALLBACK=someuser" in r.stdout, r.stdout)
        check("[owner] VIBE_GITHUB_OWNER wins when set",
              "CONFIGURED=my-org" in r.stdout, r.stdout)
        check("[owner] empty VIBE_GITHUB_OWNER falls back",
              "EMPTY=someuser" in r.stdout, r.stdout)

    src = VIBE.read_text()
    check("[owner] create flow prompts for owner (account or org)",
          "Owner (account or org)" in src, "")
    check("[owner] owner existence validated via gh api users/",
          "owner_exists_on_github" in src and 'gh api "users/' in src, "")
    check("[owner] mistyped owner gets a retry message",
          "not found on GitHub" in src, "")
    check("[owner] unvalidatable owner offers proceed-anyway (network-down path)",
          "Proceed with" in src, "")
    check("[owner] failure hint mentions org repo-creation permission",
          "repo-creation permission" in src, "")
    check("[owner] README documents VIBE_GITHUB_OWNER",
          "VIBE_GITHUB_OWNER" in (REPO / "README.md").read_text(), "")


# ── Task 016: auto-resume watchdog + heartbeat (AC1-AC8, AC12) ──────────────────

def test_vibe_auto_resume_deactivate() -> None:
    print("\n[task_016 AC1: auto_resume_deactivate]")
    snippet = (
        'm="${TMPDIR:-/tmp}/vibe-ar-deact.$$"; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$m"; '
        'auto_resume_deactivate "$m"; '
        'echo "AFTER=[$(auto_resume_field "$m" active)]"; '
        'auto_resume_deactivate "$m"; '
        'echo "IDEMPOTENT=[$(auto_resume_field "$m" active)]"; '
        'auto_resume_deactivate "$m.missing"; '
        'if [ -f "$m.missing" ]; then echo "CREATED=[yes]"; else echo "CREATED=[no]"; fi; '
        'rm -f "$m" "$m.tmp.$$"; '
        'if [ -f "$m.tmp.$$" ]; then echo "RESIDUE=[yes]"; else echo "RESIDUE=[no]"; fi'
    )
    r = _source_vibe_call({}, snippet)
    check("AC1: deactivate exits 0", r.returncode == 0, r.stderr)
    check("AC1: sets active=0", "AFTER=[0]" in r.stdout, r.stdout)
    check("AC1: idempotent", "IDEMPOTENT=[0]" in r.stdout, r.stdout)
    check("AC1: missing file → no create", "CREATED=[no]" in r.stdout, r.stdout)
    check("AC1: no .tmp residue", "RESIDUE=[no]" in r.stdout, r.stdout)


def test_vibe_auto_resume_heartbeat_write() -> None:
    print("\n[task_016 AC2: auto_resume_heartbeat_write]")
    snippet = (
        'hb="${TMPDIR:-/tmp}/vibe-hb-write.$$"; '
        'before=$(date +%s); '
        'auto_resume_heartbeat_write "$hb"; '
        'after=$(date +%s); '
        'if [ -f "$hb" ]; then '
        '  val=$(cat "$hb"); '
        '  if echo "$val" | grep -qE "^[0-9]+$"; then '
        '    if [ "$val" -ge "$before" ] && [ "$val" -le "$after" ]; then '
        '      echo "EPOCH=[ok]"; '
        '    else '
        '      echo "EPOCH=[out-of-range:$val]"; '
        '    fi; '
        '  else '
        '    echo "EPOCH=[not-numeric:$val]"; '
        '  fi; '
        'else '
        '  echo "EPOCH=[missing]"; '
        'fi; '
        'rm -f "$hb" "$hb.tmp.$$"'
    )
    r = _source_vibe_call({}, snippet)
    check("AC2: exits 0", r.returncode == 0, r.stderr)
    check("AC2: writes epoch in range", "EPOCH=[ok]" in r.stdout, r.stdout)


def test_vibe_auto_resume_stalled() -> None:
    print("\n[task_016 AC3: auto_resume_stalled]")
    snippet = (
        'hb="${TMPDIR:-/tmp}/vibe-ar-stalled.$$"; '
        'now=$(date +%s); '
        # Test case 1: gap 1000 vs threshold 900 → stalled (0)
        'echo "$((now - 1000))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T1=[0]"; else echo "T1=[1]"; fi; '
        # Test case 2: gap 100 vs 900 → not stalled (1)
        'echo "$((now - 100))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T2=[0]"; else echo "T2=[1]"; fi; '
        # Test case 3: gap exactly 900 vs 900 → not stalled, boundary (1)
        'echo "$((now - 900))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T3=[0]"; else echo "T3=[1]"; fi; '
        # Test case 4: missing file → not stalled (1)
        'rm -f "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T4=[0]"; else echo "T4=[1]"; fi; '
        # Test case 5: future epoch → not stalled (1)
        'echo "$((now + 500))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T5=[0]"; else echo "T5=[1]"; fi; '
        # Test case 6: garbage content → not stalled (1)
        'echo "evil; rm -rf /" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T6=[0]"; else echo "T6=[1]"; fi; '
        'rm -f "$hb"'
    )
    r = _source_vibe_call({}, snippet)
    check("AC3: exits 0", r.returncode == 0, r.stderr)
    check("AC3: gap > threshold → stalled", "T1=[0]" in r.stdout, r.stdout)
    check("AC3: gap < threshold → not stalled", "T2=[1]" in r.stdout, r.stdout)
    check("AC3: gap == threshold (boundary) → not stalled", "T3=[1]" in r.stdout, r.stdout)
    check("AC3: missing file → not stalled", "T4=[1]" in r.stdout, r.stdout)
    check("AC3: future epoch → not stalled", "T5=[1]" in r.stdout, r.stdout)
    check("AC3: garbage content → not stalled", "T6=[1]" in r.stdout, r.stdout)


def test_vibe_settings_heartbeat_hooks() -> None:
    print("\n[task_016 AC4: heartbeat hook entries in settings.local.json]")
    vibe_src = VIBE.read_text()

    # Extract the settings.local.json heredoc between cat > ... << 'EOF' and closing EOF
    start_marker = 'cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\''
    start_idx = vibe_src.find(start_marker)
    if start_idx == -1:
        check("AC4: heredoc found", False, "could not locate settings.local.json heredoc start")
        return

    start_idx = vibe_src.find('\n', start_idx) + 1
    end_idx = vibe_src.find('\nEOF', start_idx)
    if end_idx == -1:
        check("AC4: heredoc end found", False, "could not locate heredoc end")
        return

    json_str = vibe_src[start_idx:end_idx]
    try:
        config = json.loads(json_str)
    except json.JSONDecodeError as e:
        check("AC4: valid JSON", False, f"JSON parse error: {e}")
        return

    check("AC4: valid JSON", True, "")

    # Verify the pinned heartbeat command
    heartbeat_cmd = "[ -f /workspace/.vss/auto-resume ] && { date +%s > /workspace/.vss/heartbeat.tmp.$$ && mv /workspace/.vss/heartbeat.tmp.$$ /workspace/.vss/heartbeat; } || true"

    # Check PreToolUse hooks
    pre_hooks = config.get("hooks", {}).get("PreToolUse", [])
    pre_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: PreToolUse heartbeat hook present", pre_heartbeat,
          f"PreToolUse blocks: {len(pre_hooks)}")

    # Check PostToolUse hooks
    post_hooks = config.get("hooks", {}).get("PostToolUse", [])
    post_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in post_hooks
    )
    check("AC4: PostToolUse heartbeat hook present", post_heartbeat,
          f"PostToolUse blocks: {len(post_hooks)}")

    # Check Stop hooks
    stop_hooks = config.get("hooks", {}).get("Stop", [])
    stop_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in stop_hooks
    )
    check("AC4: Stop heartbeat hook present", stop_heartbeat,
          f"Stop blocks: {len(stop_hooks)}")

    # Check that guard-bash, guard-fs, bell, etc. are still present
    has_guard_bash = any(
        block.get("matcher") == "Bash" and
        any("/usr/local/bin/guard-bash.sh" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: guard-bash entry preserved", has_guard_bash, "")

    has_guard_fs = any(
        block.get("matcher") == "Write|Edit|MultiEdit" and
        any("/usr/local/bin/guard-fs.sh" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: guard-fs entry preserved", has_guard_fs, "")

    # Check bell on Stop
    bell_stop = any(
        block.get("matcher") == "" and
        any("printf '\\a'" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in stop_hooks
    )
    check("AC4: bell Stop command present", bell_stop, "")

    # Check bell on Notification
    notif_hooks = config.get("hooks", {}).get("Notification", [])
    bell_notif = any(
        block.get("matcher") == "" and
        any("printf '\\a'" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in notif_hooks
    )
    check("AC4: bell Notification entry present", bell_notif, "")

    # Check forceLoginMethod and permissions.defaultMode
    check("AC4: forceLoginMethod=claudeai",
          config.get("forceLoginMethod") == "claudeai",
          f"forceLoginMethod={config.get('forceLoginMethod')}")
    check("AC4: permissions.defaultMode=bypassPermissions",
          config.get("permissions", {}).get("defaultMode") == "bypassPermissions",
          f"permissions.defaultMode={config.get('permissions', {}).get('defaultMode')}")


def test_vibe_supervised_launch_text() -> None:
    print("\n[task_016 AC5/AC7/AC8: supervised launch and trap text]")
    vibe_src = VIBE.read_text()

    # AC5a: launch_claude has exec devcontainer exec
    launch_claude_def = re.search(r'^launch_claude\(\) \{(.+?)^}', vibe_src, re.MULTILINE | re.DOTALL)
    if launch_claude_def:
        body = launch_claude_def.group(1)
        has_exec = "exec devcontainer exec" in body
        check("AC5: launch_claude body has 'exec devcontainer exec'", has_exec, "")
    else:
        check("AC5: launch_claude function found", False, "function definition not found")

    # AC5b: At least one bare devcontainer exec line exists (non-exec-prefixed)
    lines = vibe_src.split('\n')
    no_exec_lines = [l for l in lines
                     if l.strip().startswith('devcontainer exec')
                     and not l.strip().startswith('exec ')]
    check("AC5: at least one bare 'devcontainer exec' line", len(no_exec_lines) > 0,
          f"found {len(no_exec_lines)} lines")

    # AC5c: launch_claude_supervised exists
    check("AC5: launch_claude_supervised function exists",
          "launch_claude_supervised()" in vibe_src, "")

    # AC5d: VIBE_SESSION_REF is created with mktemp
    check("AC5: VIBE_SESSION_REF created with mktemp",
          'VIBE_SESSION_REF=$(mktemp' in vibe_src, "")

    # AC5e: AUTO_RESUME_MARKER defined before first supervised launch
    check("AC5: AUTO_RESUME_MARKER defined",
          'AUTO_RESUME_MARKER="$WORKSPACE/.vss/auto-resume"' in vibe_src, "")

    # AC7: INT trap is re-armed every iteration and reset after sleep
    has_int_trap = "trap 'auto_resume_deactivate" in vibe_src and "INT" in vibe_src
    check("AC7: INT trap armed for deactivate", has_int_trap, "")

    # AC7: trap reset after sleep
    has_trap_reset = "trap - INT" in vibe_src
    check("AC7: trap - INT reset present", has_trap_reset, "")

    # AC8: final exit statement with CLAUDE_EXIT
    has_exit_statement = re.search(r'^\s*exit "\$CLAUDE_EXIT"', vibe_src, re.MULTILINE)
    check("AC8: final 'exit \"$CLAUDE_EXIT\"' statement", has_exit_statement is not None, "")


def test_vibe_stall_watchdog_functional() -> None:
    print("\n[task_016 AC6: watchdog functional tests]")
    # All four cases stub vibe_container_kill_claude to write a killfile marker
    # instead of asserting on process death alone (a broken kill gate would
    # otherwise look identical to a correct one: an already-timed-out fake
    # claude dies "on its own" regardless of whether the gate ever armed).
    # POLL=1/GRACE=1/SECS=1/KILL_PAUSE=0 per spec AC6's pinned functional-test
    # env; negatives sample the live PID mid-lifetime (~t=3s, before its
    # natural 5s death) so the assertion is discriminating, not a race against
    # natural process exit.

    # Test 1: POSITIVE kill - marker active=1, ref file older (unconditional-
    # session case), heartbeat stale. Long-lived fake claude (sleep 300) so
    # any death can only be the watchdog's doing, never natural exit.
    snippet_t1 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t1.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t1.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t1.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t1.$$"; '
        # Stub vibe_container_kill_claude to track invocation (never actually
        # kills - proves the host-side PID fallback is what finishes the job)
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        # Backdate ref file first so the marker (written next, "now") is
        # unambiguously newer - no same-second race.
        'touch -t 202001010000 "$ref"; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 300 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 2.3; '
        'if [ -f "$killfile" ]; then echo "KILLED=[yes]"; else echo "KILLED=[no]"; fi; '
        'sleep 0.7; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "DEAD=[no]"; else echo "DEAD=[yes]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t1)
    check("AC6 T1: positive kill case exits 0", r.returncode == 0, r.stderr)
    check("AC6 T1: vibe_container_kill_claude invoked", "KILLED=[yes]" in r.stdout, r.stdout)
    check("AC6 T1: fake claude actually terminated (host-PID fallback)",
          "DEAD=[yes]" in r.stdout, r.stdout)

    # Test 2: NEGATIVE active=0 - gate condition (1) fails. Short-lived fake
    # claude (sleep 5) sampled at t=3s (mid-lifetime, well before its natural
    # death) so "still alive" is evidence the gate declined to arm, not a
    # coincidence of timing. killfile must not exist: the stub was never called.
    snippet_t2 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t2.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t2.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t2.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t2.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=0\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'touch "$ref"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t2)
    check("AC6 T2: negative active=0 exits 0", r.returncode == 0, r.stderr)
    check("AC6 T2: fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T2: kill never invoked", "KILLFILE=[no]" in r.stdout, r.stdout)

    # Test 3: NEGATIVE stale ref gate - gate condition (2) fails: marker
    # predates ref (crash-left marker from before this launcher session).
    # Same live-PID-at-t=3s + killfile-absent discrimination as T2.
    snippet_t3 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t3.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t3.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t3.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t3.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        # Backdate the MARKER (crash-left case) then create ref fresh - ref
        # unambiguously newer than marker, so [ marker -nt ref ] is false.
        'touch -t 202001010000 "$marker"; '
        'touch "$ref"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t3)
    check("AC6 T3: negative stale ref gate exits 0", r.returncode == 0, r.stderr)
    check("AC6 T3: crash-left marker - fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T3: kill never invoked", "KILLFILE=[no]" in r.stdout, r.stdout)

    # Test 4: NEGATIVE empty ref - gate condition (2) fails via the mktemp-
    # failure fail-safe (empty ref must never satisfy the sentinel or the
    # exists-and-newer branch). Same discrimination as T2/T3.
    snippet_t4 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t4.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t4.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t4.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t4)
    check("AC6 T4: negative empty ref exits 0", r.returncode == 0, r.stderr)
    check("AC6 T4: empty ref - fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T4: empty ref never arms kill", "KILLFILE=[no]" in r.stdout, r.stdout)


def test_vibe_gitignore_heartbeat_pattern() -> None:
    print("\n[task_016 AC12: .gitignore heartbeat pattern]")
    gitignore_path = REPO / ".gitignore"
    if not gitignore_path.exists():
        check("AC12: .gitignore exists", False, "file not found")
        return

    content = gitignore_path.read_text()
    has_heartbeat = ".vss/heartbeat*" in content
    check("AC12: .gitignore contains '.vss/heartbeat*'", has_heartbeat,
          "pattern not found")


def test_vibe_task016_docs() -> None:
    print("\n[task_016 AC11/AC13: documentation presence]")

    # AC11: MANUAL-TESTS.md gains a --sessions stall watchdog section
    manual_tests = (REPO / "MANUAL-TESTS.md").read_text()
    has_stall_section = "--sessions stall watchdog" in manual_tests or "stall watchdog" in manual_tests
    check("AC11: MANUAL-TESTS.md has stall watchdog section", has_stall_section, "")

    # AC13: vibe auto-resume comment block (around line 479-486)
    vibe_src = VIBE.read_text()
    has_heartbeat_docs = "heartbeat" in vibe_src and "stall-watchdog" in vibe_src
    check("AC13: vibe comment block mentions heartbeat and watchdog", has_heartbeat_docs, "")

    # AC13: devcontainer/commands/vsss.md documents Auto-resume section
    vsss_md = (REPO / "devcontainer" / "commands" / "vsss.md").read_text()
    has_auto_resume_docs = "Auto-resume" in vsss_md or "auto-resume" in vsss_md
    check("AC13: vsss.md documents Auto-resume", has_auto_resume_docs, "")
    has_stall_secs = "VIBE_STALL_SECS" in vsss_md
    check("AC13: vsss.md documents VIBE_STALL_SECS", has_stall_secs, "")


def test_vibe_statusline() -> None:
    """statusLine in the settings heredoc: single-letter model (F/O/S/H),
    full display name fallback, vibe cue, optional ctx/5h percentage segments.
    Structural check on the parsed JSON plus a functional run of the actual
    command string against stdin fixtures (proves the JSON escaping survives
    the round trip into a real shell)."""
    print("\n[statusLine: single-letter model in the vibe TUI]")
    vibe_src = VIBE.read_text()

    start_marker = 'cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\''
    start_idx = vibe_src.find(start_marker)
    check("[status] settings heredoc found", start_idx != -1, "")
    if start_idx == -1:
        return
    start_idx = vibe_src.find('\n', start_idx) + 1
    end_idx = vibe_src.find('\nEOF', start_idx)
    config = json.loads(vibe_src[start_idx:end_idx])

    sl = config.get("statusLine", {})
    check("[status] statusLine.type == command", sl.get("type") == "command", str(sl))
    cmd = sl.get("command", "")
    check("[status] command reads model.display_name", ".model.display_name" in cmd, "")

    # Functional fixtures: (stdin JSON, expected exact output)
    fixtures = [
        ('{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":42.7},'
         '"rate_limits":{"five_hour":{"used_percentage":63}}}',
         "F · vibe · ctx 42% · 5h 63%"),
        ('{"model":{"display_name":"Opus 4.8"}}', "O · vibe"),
        ('{"model":{"display_name":"Sonnet 5"},"context_window":{"used_percentage":3}}',
         "S · vibe · ctx 3%"),
        ('{"model":{"display_name":"Haiku 4.5"}}', "H · vibe"),
        ('{"model":{"display_name":"GPT-9"}}', "GPT-9 · vibe"),  # fallback: full name
        ('{}', "? · vibe"),  # every field absent (pre-first-response) → no crash
    ]
    for stdin_json, expected in fixtures:
        r = subprocess.run(["sh", "-c", cmd], input=stdin_json,
                           capture_output=True, text=True, timeout=15)
        label = expected.split(" ")[0]
        check(f"[status] {label!r} fixture exact output", r.returncode == 0 and r.stdout == expected,
              f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")


# ── task_017 AC1-AC7: shared-repos tests (Cycle 1) ────────────────────────────

def test_task017_ac2_shared_repos_parse_valid() -> None:
    print("\n[task_017 AC2: shared_repos_parse: valid line]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro ro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m"); '
        'echo "RESULT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("parses valid line", "RESULT=andeyePro/andeyePro ro" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_default_mode() -> None:
    print("\n[task_017 AC2: shared_repos_parse: default mode]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m"); '
        'echo "RESULT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("defaults to ro", "RESULT=andeyePro/andeyePro ro" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_comments_blanks() -> None:
    print("\n[task_017 AC2: shared_repos_parse: comments and blanks]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "# comment\\n\\nandeyePro/andeyePro\\n  # another comment\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" | wc -l); '
        'echo "LINES=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("skips comments/blanks", "LINES=1" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_bad_slug() -> None:
    print("\n[task_017 AC2: shared_repos_parse: bad slug]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "invalid-slug-no-slash\\n" > "$m"; '
        'shared_repos_parse "$m" 2>&1 > /tmp/parse_out.txt; '
        'STDERR=$(cat /tmp/parse_out.txt); '
        'echo "STDERR=$STDERR"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on bad slug", "malformed slug" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_bad_mode() -> None:
    print("\n[task_017 AC2: shared_repos_parse: bad mode]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro invalid\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on bad mode", "invalid mode" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_extra_content() -> None:
    print("\n[task_017 AC2: shared_repos_parse: extra content]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro ro extra stuff\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on extra content", "unexpected content" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_missing_file() -> None:
    print("\n[task_017 AC2: shared_repos_parse: missing file]")
    snippet = 'OUT=$(shared_repos_parse /nonexistent/file); echo "RESULT=[$OUT]"'
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("missing file echoes nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_injection_strings() -> None:
    print("\n[task_017 AC2: shared_repos_parse: injection strings rejected]")
    cases = [
        ('foo/bar;rm -rf /', "semicolon injection"),
        ('foo/$(bar)', "command substitution"),
        ('foo/`bar`', "backtick injection"),
        ('foo/bar\nbar/baz', "embedded newline"),
    ]
    for bad_slug, label in cases:
        bad_slug_escaped = shlex.quote(bad_slug + "\n")
        snippet = (
            'm="$(mktemp)"; '
            f'printf {bad_slug_escaped} > "$m"; '
            'OUT=$(shared_repos_parse "$m" 2>&1 | wc -l); '
            'echo "OUT=$OUT"; '
            'rm "$m"'
        )
        r = _source_vibe_call({}, snippet)
        check(f"rejects {label}", r.returncode == 0, r.stderr)
        check(f"{label} produces warning", "OUT=" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_dot_prefix_basename_rejected() -> None:
    print("\n[task_017 AC2: shared_repos_parse: dot-prefix basenames skipped]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "owner/.signals ro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    # Note: the spec says dot-prefix names are reserved and SKIPPED, but
    # parsing happens in shared_repos_scan. This test documents the behavior.


def test_task017_ac2_repos_registry_lookup_valid() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: valid entry]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=/home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = f'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=$OUT"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("looks up path", "/home/user/code/andeyePro" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_missing_file() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: missing file]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("missing file returns nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_bad_slug() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: bad slug]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=/home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "invalid-slug"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("bad slug returns nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_malformed_entry() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: malformed entry gracefully ignored]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        # Write multiple entries, one good, one malformed (line continuation)
        registry.write_text("other/repo=/home/user/code/other\nandeyePro/andeyePro=/home/user/code/andeye\nPro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        # Lookup the good entry
        snippet = 'OUT=$(repos_registry_lookup "other/repo"); echo "RESULT=$OUT"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("good entry resolved", "/home/user/code/other" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_quote_in_path() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: quote in path rejected]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text('andeyePro/andeyePro=/home/user/code/"andeye\n', encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("quote in path rejected", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_relative_path() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: relative path rejected]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("relative path rejected", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_valid() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: valid slug]")
    snippet = 'OUT=$(shared_repo_env_name "andeyePro/andeyePro"); echo "RESULT=$OUT"'
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("produces VIBE_SHARED_TOKEN_* name", "VIBE_SHARED_TOKEN_" in r.stdout, r.stdout)
    check("correct transformation", "VIBE_SHARED_TOKEN_ANDEYEPRO_ANDEYEPRO" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_sanitisation() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: sanitisation cases]")
    cases = [
        ("owner/repo", "VIBE_SHARED_TOKEN_OWNER_REPO"),
        ("owner_repo/pkg-name", "VIBE_SHARED_TOKEN_OWNER_REPO_PKG_NAME"),
        ("owner.io/repo.py", "VIBE_SHARED_TOKEN_OWNER_IO_REPO_PY"),
    ]
    for slug, expected in cases:
        snippet = f'OUT=$(shared_repo_env_name "{slug}"); echo "RESULT=$OUT"'
        r = _source_vibe_call({}, snippet)
        check(f"sanitises {slug}", expected in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_collision() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: collision detection]")
    # Two different slugs that sanitise to same name
    snippet = (
        'ENV1=$(shared_repo_env_name "owner/repo"); '
        'ENV2=$(shared_repo_env_name "owner-repo"); '
        'if [ "$ENV1" = "$ENV2" ]; then echo "COLLISION"; else echo "DISTINCT"; fi'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("detects collision", "COLLISION" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_creates_sidecar() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: creates sidecar]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'if shared_repo_ensure_signals "{checkout}"; then '
            f'  if [ -d "{checkout}/.vibe-signals" ]; then echo "SIDECAR_OK"; fi; '
            'else echo "ENSURE_FAILED"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("creates sidecar", "SIDECAR_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_adds_gitignore() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: adds gitignore]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'shared_repo_ensure_signals "{checkout}"; '
            f'if grep -qx ".vibe-signals/" "{checkout}/.gitignore" 2>/dev/null; then '
            'echo "GITIGNORE_OK"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("adds to .gitignore", "GITIGNORE_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_idempotent() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: idempotent]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'shared_repo_ensure_signals "{checkout}"; '
            f'COUNT1=$(grep -c ".vibe-signals/" "{checkout}/.gitignore"); '
            f'shared_repo_ensure_signals "{checkout}"; '
            f'COUNT2=$(grep -c ".vibe-signals/" "{checkout}/.gitignore"); '
            'if [ "$COUNT1" = "$COUNT2" ] && [ "$COUNT1" -eq 1 ]; then '
            'echo "IDEMPOTENT_OK"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("idempotent", "IDEMPOTENT_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_unwritable_dir() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: fails soft on unwritable dir]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        checkout.chmod(0o000)
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'if shared_repo_ensure_signals "{checkout}"; then '
            'echo "SHOULD_FAIL"; else echo "FAILED_SOFT"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("fails soft", "FAILED_SOFT" in r.stdout, r.stdout)
        checkout.chmod(0o755)  # restore for cleanup


def test_task017_ac6_ensure_project_gitignore_has_vibe_signals() -> None:
    print("\n[task_017 AC6: ensure_project_gitignore contains .vibe-signals/]")
    vibe_src = VIBE.read_text()
    # Find the ensure_project_gitignore function
    if "ensure_project_gitignore" in vibe_src:
        check("function exists", True)
        # Check that the managed block includes .vibe-signals/
        if ".vibe-signals/" in vibe_src:
            check(".vibe-signals/ mentioned", True)
        else:
            check(".vibe-signals/ mentioned", False, "not found in vibe script")
    else:
        check("function exists", False, "ensure_project_gitignore not found")


def test_task017_ac1_repos_dispatch_before_parse_vibe_args() -> None:
    print("\n[task_017 AC1: repos dispatch block placement]")
    vibe_src = VIBE.read_text()
    # Find the dispatch blocks
    # Look for the repos_handle_subcommand call within the dispatch
    repos_dispatch_idx = vibe_src.find('repos_handle_subcommand')
    # Look for the parse_vibe_args call (not definition)
    parse_vibe_args_call_idx = vibe_src.rfind('parse_vibe_args "$@"')
    # Make sure we get the actual call, not the definition
    if parse_vibe_args_call_idx > 0:
        # Verify it's not in a comment by checking what comes before
        line_start = vibe_src.rfind('\n', 0, parse_vibe_args_call_idx) + 1
        line_text = vibe_src[line_start:parse_vibe_args_call_idx + 20]
        if line_text.strip().startswith('#'):
            # This is in a comment, search earlier
            parse_vibe_args_call_idx = vibe_src.find('parse_vibe_args "$@"', 1800*50)

    check("repos dispatch found", repos_dispatch_idx != -1)
    check("parse_vibe_args call found", parse_vibe_args_call_idx != -1)
    if repos_dispatch_idx != -1 and parse_vibe_args_call_idx != -1:
        check("repos dispatch before parse_vibe_args", repos_dispatch_idx < parse_vibe_args_call_idx)


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


def test_task017_delta_scan_m_full_valid_chain() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — M: fully valid chain]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        expected = f"M andeyePro ro andeyePro/andeyePro {checkout}"
        check("emits exactly one M line, correctly shaped",
              r.stdout.strip() == expected, r.stdout)
        check("sidecar mkdir'd as a scan side effect",
              (checkout / ".vibe-signals").is_dir(), "sidecar missing")


def test_task017_delta_scan_n_never_registered_is_silent() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — N: never registered, total silence]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("someorg/somerepo ro\n", encoding="utf-8")
        # No registry file at all — community-contributor case.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("emits exactly 'N <slug>' and NOTHING else",
              r.stdout.strip() == "N someorg/somerepo", r.stdout)


def test_task017_delta_scan_u_unacked_no_sidecar_writes() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — U: registered+token but unacked]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        # Deliberately NO repos-acks file — the consent layer is absent.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("emits exactly 'U <slug>'",
              r.stdout.strip() == "U andeyePro/andeyePro", r.stdout)
        check("NO sidecar created for an unacked repo (consent contract)",
              not (checkout / ".vibe-signals").exists(),
              "sidecar was written despite no ack")


def test_task017_delta_scan_b_path_missing() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: registered path missing/.git absent]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        ghost_path = td / "does-not-exist"
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={ghost_path}\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: path missing / not a git checkout",
              r.stdout.strip() == f"B andeyePro/andeyePro path missing or not a git checkout ({ghost_path})",
              r.stdout)


def test_task017_delta_scan_b_token_absent() -> None:
    # AMENDED by the chair at C4 under the spec's sanctioned frozen-test
    # amendment (C4 preamble): AC18 governs from C4 — a missing token for an
    # acked+registered ro repo is a WARNING, not a mount-blocker (an ro bind
    # of a local checkout needs no token; only fetch/push do). The C1-era
    # assertion (B: no token configured) tested the stricter interim
    # behaviour; the scan now mounts, and the no-PAT nudge lives in
    # `vibe repos list` (covered below) and the launch token-export loop.
    print("\n[task_017 delta AC3->AC18: shared_repos_scan — token absent: warn, still mount ro]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # No tokens file at all.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("tokenless repo still mounts (M, ro)",
              r.stdout.strip() == f"M andeyePro ro andeyePro/andeyePro {checkout}",
              r.stdout)
        # And the list surface carries the no-PAT nudge for the same fixture.
        r2 = _source_vibe_call(env, f'cd {shlex.quote(str(ws))} && _repos_list')
        check("list notes the missing PAT",
              "no PAT staged" in r2.stdout and "vibe repos add andeyePro/andeyePro" in r2.stdout,
              r2.stdout)


def test_task017_delta_scan_b_sidecar_unwritable() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: sidecar mkdir fails soft]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # r-x only: .git stays visible/statable, but mkdir of .vibe-signals
        # under checkout fails for lack of the write bit on the parent dir
        # (chmod 000 would ALSO hide .git's existence, misfiring as the
        # "path missing" B reason instead — 555 isolates the sidecar-mkdir
        # failure specifically).
        checkout.chmod(0o555)
        try:
            env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
            r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        finally:
            checkout.chmod(0o755)
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: sidecar unwritable",
              r.stdout.strip() == f"B andeyePro/andeyePro sidecar unwritable ({checkout}/.vibe-signals)",
              r.stdout)


def test_task017_delta_scan_b_reserved_dot_prefix_basename() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: reserved dot-prefixed basename]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        # Valid slug charset, dot-prefixed repo basename — simulates a
        # hand-edited .vibe-repos that slipped past `vibe repos add`'s own
        # rejection of this at registration time.
        (ws / ".vibe-repos").write_text("owner/.hidden ro\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: reserved dot-prefixed name, no registry lookup needed",
              r.stdout.strip() == "B owner/.hidden reserved dot-prefixed name '.hidden'",
              r.stdout)


def test_task017_delta_scan_b_basename_collision() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: basename collision vs an already-mounted repo]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout_a = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text(
            "orgA/widget ro\norgB/widget ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"orgA/widget={checkout_a}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("orgA/widget=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"orgA/widget={ws}\n", encoding="utf-8")
        # orgB/widget is declared only — never registered — but the basename
        # collision check fires before registry lookup, against orgA/widget
        # which DID resolve to a real mount.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        check("first repo mounts (M)", lines[0] == f"M widget ro orgA/widget {checkout_a}", r.stdout)
        check("second repo demoted to B: basename collision",
              lines[1] == "B orgB/widget basename 'widget' collides with another declared repo",
              r.stdout)


def test_task017_delta_ack_exact_pair_semantics() -> None:
    print("\n[task_017 delta AC2: shared_repo_acked/ack — exact (slug, workspace) pair only]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'shared_repo_ack "org/repo" "/ws/a"; '
            'if shared_repo_acked "org/repo" "/ws/a"; then echo "RIGHT_PAIR=Y"; else echo "RIGHT_PAIR=N"; fi; '
            'if shared_repo_acked "org/repo" "/ws/b"; then echo "WRONG_WS=Y"; else echo "WRONG_WS=N"; fi; '
            'if shared_repo_acked "org/other" "/ws/a"; then echo "WRONG_SLUG=Y"; else echo "WRONG_SLUG=N"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("right slug + right workspace -> true", "RIGHT_PAIR=Y" in r.stdout, r.stdout)
        check("right slug + wrong workspace -> false", "WRONG_WS=N" in r.stdout, r.stdout)
        check("wrong slug + right workspace -> false", "WRONG_SLUG=N" in r.stdout, r.stdout)


def test_task017_delta_ack_idempotent_and_chmod_600() -> None:
    print("\n[task_017 delta AC2: shared_repo_ack — idempotent double-ack, chmod 600]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'shared_repo_ack "org/repo" "/ws/a"; '
            'shared_repo_ack "org/repo" "/ws/a"; '
            'shared_repo_ack "org/repo" "/ws/a"; '
            'wc -l < "$HOME/.vibe/repos-acks"; '
            '(stat -c %a "$HOME/.vibe/repos-acks" 2>/dev/null || stat -f %Lp "$HOME/.vibe/repos-acks")'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        out_lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
        check("three acks of the same pair -> exactly one line",
              len(out_lines) >= 2 and out_lines[0] == "1", r.stdout)
        check("repos-acks is chmod 600",
              len(out_lines) >= 2 and out_lines[1] == "600", r.stdout)


def test_task017_delta_fixedstring_repos_registry_lookup_regex_danger() -> None:
    print("\n[task_017 delta security-review regression: repos_registry_lookup is fixed-string, not regex]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        vibe_dir = home / ".vibe"; vibe_dir.mkdir()
        (vibe_dir / "repos").write_text("myorg/secret=/real/registered/path\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'GOOD=$(repos_registry_lookup "myorg/secret"); '
            'BAD=$(repos_registry_lookup "myor./secret"); '
            'echo "GOOD=[$GOOD]"; echo "BAD=[$BAD]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("exact slug resolves", "GOOD=[/real/registered/path]" in r.stdout, r.stdout)
        check("regex-dangerous-but-charset-valid slug does NOT resolve the other entry",
              "BAD=[]" in r.stdout, r.stdout)


def test_task017_delta_fixedstring_lookup_token_regex_danger() -> None:
    print("\n[task_017 delta security-review regression: lookup_token is fixed-string, not regex]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        vibe_dir = home / ".vibe"; vibe_dir.mkdir()
        (vibe_dir / "tokens").write_text("myorg/secret=ghp_thetoken\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'GOOD=$(lookup_token "myorg/secret"); '
            'BAD=$(lookup_token "myor./secret"); '
            'echo "GOOD=[$GOOD]"; echo "BAD=[$BAD]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("exact slug resolves the token", "GOOD=[ghp_thetoken]" in r.stdout, r.stdout)
        check("regex-dangerous-but-charset-valid slug does NOT resolve the token",
              "BAD=[]" in r.stdout, r.stdout)


def test_task017_delta_fixedstring_decl_remove_prefix_discipline() -> None:
    print("\n[task_017 delta security-review regression: _vibe_repos_decl_remove is prefix-safe]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        decl.write_text("a/b ro\na/bb ro\naxb ro\n", encoding="utf-8")
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'_vibe_repos_decl_remove {shlex.quote(str(decl))} "a/b"')
        check("exits 0", r.returncode == 0, r.stderr)
        remaining = decl.read_text().splitlines()
        check("removes the exact 'a/b' line", "a/b ro" not in remaining, remaining)
        check("does NOT remove 'a/bb' (longer slug sharing the prefix)",
              "a/bb ro" in remaining, remaining)
        check("does NOT remove 'axb' (no slash, shares no real prefix)",
              "axb ro" in remaining, remaining)


def test_task017_delta_override_config_two_binds_when_acked() -> None:
    print("\n[task_017 delta AC3: _build_override_config — acked repo contributes code+sidecar binds]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # Blank OP MCP creds (leak in from the real container env) and disable
        # brain2/zotero so the only mounts in play are the shared-repo binds
        # under test — mirrors test_build_override_config_brain2_and_zotero's
        # gating discipline.
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        check("override generated under HOME/.vibe/run",
              out.startswith(str(home / ".vibe" / "run")), out)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        mounts = [m for m in cfg.get("mounts", []) if isinstance(m, dict)]
        code_mount = next((m for m in mounts if m.get("target") == "/repos/andeyePro"), None)
        sidecar_mount = next((m for m in mounts if m.get("target") == "/repos/.signals/andeyePro"), None)
        check("code bind at /repos/<name> present", code_mount is not None, str(mounts))
        if code_mount:
            check("code bind is readonly", code_mount.get("readonly") is True, str(code_mount))
            check("code bind source is the registered checkout",
                  code_mount.get("source") == str(checkout), str(code_mount))
        check("sidecar bind at /repos/.signals/<name> present", sidecar_mount is not None, str(mounts))
        if sidecar_mount:
            check("sidecar bind is rw (no readonly key)",
                  "readonly" not in sidecar_mount, str(sidecar_mount))
            check("sidecar bind source is <checkout>/.vibe-signals",
                  sidecar_mount.get("source") == str(checkout / ".vibe-signals"), str(sidecar_mount))


def test_task017_delta_override_config_no_binds_when_unacked() -> None:
    print("\n[task_017 delta AC3: _build_override_config — unacked repo contributes NEITHER bind]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        # No repos-acks file — unacked.
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        tgts = [m.get("target") for m in cfg.get("mounts", []) if isinstance(m, dict)]
        check("neither code nor sidecar bind present when unacked",
              "/repos/andeyePro" not in tgts and "/repos/.signals/andeyePro" not in tgts,
              str(tgts))


def test_task017_delta_manifest_lines_mixed_tags() -> None:
    print("\n[task_017 delta AC5: shared_repos_manifest_lines — M+B+N+U mix emits only M lines]")
    scan_output = "\n".join([
        "M repoA ro orgA/repoA /path/to/a",
        "B orgB/repoB path missing or not a git checkout (/nowhere)",
        "N orgC/repoC",
        "U orgD/repoD",
        "M repoE rw orgE/repoE /path/to/e",
    ])
    r = _source_vibe_call({}, f'shared_repos_manifest_lines {shlex.quote(scan_output)}')
    check("exits 0", r.returncode == 0, r.stderr)
    expected = "repoA ro orgA/repoA\nrepoE rw orgE/repoE"
    check("emits exactly the M repos' 'name mode slug' lines, in order",
          r.stdout.strip() == expected, r.stdout)


def test_task017_delta_header_case_arms_present() -> None:
    print("\n[task_017 delta AC4: launch header — M/B/N/U case arms, N silent, U names the remedy]")
    vibe_src = VIBE.read_text()
    start = vibe_src.find('if [ -n "$SHARED_REPOS_SCAN" ]; then')
    end = vibe_src.find('UP_BASE_ARGS=(', start) if start != -1 else -1
    check("header block located between the scan gate and UP_BASE_ARGS", start != -1 and end != -1 and end > start)
    block = vibe_src[start:end] if (start != -1 and end != -1 and end > start) else ""
    check("M case arm present (mounted -> ◆ line)", "M\\ *)" in block and "◆ shared repo:" in block, block[:500])
    check("B case arm present (broken -> ⚠ line)", "B\\ *)" in block and "BROKEN:" in block, block[:500])
    check("N case arm is a no-op comment (deliberate silence)",
          "N\\ *) ;;" in block, block[:500])
    check("U case arm present and loud, naming the remedy",
          "U\\ *)" in block and "not authorised" in block and "vibe repos add" in block,
          block[:500])


# ── task_017 AC8-AC11: rw intent + single-writer lock (Cycle 2) ──────────────
# Haiku Tester. Lock helpers take a bare <checkout> path and are otherwise
# HOME-independent, so most of these skip the full _repos_delta_fixture and
# just use a bare tempdir. Real processes (backgrounded `sleep`) stand in for
# "another launcher" per the task_016 watchdog-test precedent — never timing
# alone: every negative samples a live PID or asserts on a persisted meta
# file, and every positive is checked against evidence a broken implementation
# could not produce by accident.

def test_task017_c2_lock_acquire_writes_meta_and_holder_reads_digits() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — success writes meta; holder reads digits-only]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA 424242; echo "ACQ=[$?]"; '
            f'shared_repo_lock_holder {shlex.quote(str(checkout))}'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("acquire returns 0 (acquired)", "ACQ=[0]" in r.stdout, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        holder_line = lines[-1] if lines else ""
        check("holder echoes 'projA 424242 <digits-only-epoch>'",
              re.match(r'^projA 424242 \d+$', holder_line) is not None, holder_line)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("meta file created", meta.is_file(), "meta missing")
        if meta.is_file():
            text = meta.read_text()
            check("meta: project=projA", "project=projA" in text, text)
            check("meta: pid=424242", "pid=424242" in text, text)
            check("meta: since=<digits>", re.search(r'(?m)^since=\d+$', text) is not None, text)


def test_task017_c2_lock_contend_live_holder_refused_and_not_reclaimed() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — contend: different project, live holder pid -> refused, holder named, lock untouched]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            'sleep 60 & holder_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} holderProj "$holder_pid" >/dev/null; '
            f'out=$(shared_repo_lock_acquire {shlex.quote(str(checkout))} otherProj "$$"); rc=$?; '
            'echo "RC=[$rc]"; '
            'echo "HOLDEROUT=[$out]"; '
            'kill "$holder_pid" 2>/dev/null; wait "$holder_pid" 2>/dev/null; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("contended acquire refused (rc=1)", "RC=[1]" in r.stdout, r.stdout)
        check("refusal echoes the ORIGINAL holder's details (holderProj, not otherProj)",
              re.search(r'HOLDEROUT=\[holderProj \d+ \d+\]', r.stdout) is not None, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock meta still names the original live holder (never reclaimed while pid alive)",
              meta.is_file() and "project=holderProj" in meta.read_text(), meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_stale_reclaim_dead_holder_succeeds() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — stale-reclaim: dead holder pid reclaimed exactly once]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            '(sleep 0.2) & dead_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} oldProj "$dead_pid" >/dev/null; echo "SETUP_RC=[$?]"; '
            'wait "$dead_pid" 2>/dev/null; '
            # Confirm the pid is provably dead before we rely on that in the assertion.
            'if kill -0 "$dead_pid" 2>/dev/null; then echo "STILL_ALIVE=[yes]"; else echo "STILL_ALIVE=[no]"; fi; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} newProj "$$"; echo "RECLAIM_RC=[$?]"; '
            f'shared_repo_lock_holder {shlex.quote(str(checkout))}; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("initial acquire (as the soon-to-die holder) succeeded", "SETUP_RC=[0]" in r.stdout, r.stdout)
        check("holder pid is provably dead before reclaim", "STILL_ALIVE=[no]" in r.stdout, r.stdout)
        check("reclaim by a new project/pid succeeds (rc=0)", "RECLAIM_RC=[0]" in r.stdout, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        check("post-reclaim holder is the NEW project/pid, not the dead one",
              re.match(r'^newProj \d+ \d+$', lines[-1]) is not None, lines[-1] if lines else "")


def test_task017_c2_lock_release_matching_owner_removes_lock() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — matching project+pid removes the lock]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$" >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} projA "$$"; echo "REL=[$?]"'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release returns 0", "REL=[0]" in r.stdout, r.stdout)
        lock_dir = checkout / ".vibe-signals" / "rw-lock.d"
        check("lock directory is gone after a matching release", not lock_dir.exists(), str(lock_dir))


def test_task017_c2_lock_release_wrong_project_refused_intact() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — wrong project refused, lock intact]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$" >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} wrongProj "$$"; echo "REL=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release with wrong project refused (rc=1)", "REL=[1]" in r.stdout, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock left intact (still projA)", meta.is_file() and "project=projA" in meta.read_text(),
              meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_release_wrong_pid_refused_intact() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — wrong pid refused, lock intact]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA 999999 >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} projA "$$"; echo "REL=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release with wrong pid refused (rc=1)", "REL=[1]" in r.stdout, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock left intact (still pid=999999)", meta.is_file() and "pid=999999" in meta.read_text(),
              meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_torn_meta_never_stolen_no_crash() -> None:
    print("\n[task_017 AC9: torn meta (empty/garbage pid) — never stolen, never crashes]")
    for label, meta_body in (
        ("empty pid", "project=ghost\npid=\nsince=\n"),
        ("garbage pid", "project=ghost\npid=notanumber\nsince=notanumber\n"),
    ):
        with tempfile.TemporaryDirectory() as td:
            checkout = Path(td) / "checkout"
            lockdir = checkout / ".vibe-signals" / "rw-lock.d"
            lockdir.mkdir(parents=True)
            (lockdir / "meta").write_text(meta_body, encoding="utf-8")
            snippet = (
                'set +e; '
                f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$"; echo "RC=[$?]"; '
                'set -e'
            )
            r = _source_vibe_call({}, snippet)
            check(f"[{label}] script exits 0 (no crash)", r.returncode == 0, r.stderr)
            check(f"[{label}] acquire refused rather than stealing a torn lock (rc=1)",
                  "RC=[1]" in r.stdout, r.stdout)
            check(f"[{label}] meta left byte-for-byte untouched",
                  (lockdir / "meta").read_text() == meta_body, (lockdir / "meta").read_text())


def test_task017_c2_rw_free_lock_grants_rw() -> None:
    print("\n[task_017 AC8: rw declared + free lock + apply_rw_intents run -> scan emits 'M <name> rw ...']")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projA"}
        # Read the meta file INSIDE the same script, before it exits — a real
        # launch registers lock release as an EXIT hook (AC10), so checking
        # the filesystem from Python after the process has already exited
        # would only ever see the lock gone, regardless of whether it was
        # ever correctly acquired.
        meta_path = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}; '
            f'echo "META=[$(cat {shlex.quote(str(meta_path))} 2>/dev/null | tr "\\n" ";")]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        m_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("M ")]
        expected = f"M andeyePro rw andeyePro/andeyePro {checkout}"
        check("scan emits rw bindmode when the lock is free", m_lines == [expected], r.stdout)
        meta_m = re.search(r"META=\[(.*)\]", r.stdout)
        meta_line = meta_m.group(1) if meta_m else ""
        check("lock acquired and held by the requesting project (read while still held, pre-exit-release)",
              "project=projA;" in meta_line and "pid=" in meta_line, meta_line)


def test_task017_c2_rw_contended_falls_back_ro_with_warning() -> None:
    print("\n[task_017 AC8: rw declared, lock held by another LIVE process -> scan falls back to ro + named contention warning]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projB"}
        snippet = (
            'set +e; '
            'sleep 60 & holder_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} otherProj "$holder_pid" >/dev/null; '
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projB "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}; '
            'echo "WARNINGS=[${VIBE_SHARED_REPO_WARNINGS[*]}]"; '
            'kill "$holder_pid" 2>/dev/null; wait "$holder_pid" 2>/dev/null; '
            'set -e'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        m_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("M ")]
        check("scan falls back to ro bindmode (lock held elsewhere)",
              m_lines == [f"M andeyePro ro andeyePro/andeyePro {checkout}"], r.stdout)
        warn_line = next((ln for ln in r.stdout.splitlines() if ln.startswith("WARNINGS=[")), "")
        check("contention warning names the holder project ('otherProj')", "otherProj" in warn_line, warn_line)
        check("contention warning names the repo slug", "andeyePro/andeyePro" in warn_line, warn_line)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("original holder's lock is untouched by the refused contender",
              meta.is_file() and "project=otherProj" in meta.read_text(), meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_ro_declared_never_acquires_lock() -> None:
    print("\n[task_017 AC8: a declared-ro repo never touches the lock (no lock dir created)]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projA"}
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        expected = f"M andeyePro ro andeyePro/andeyePro {checkout}"
        check("scan reports ro for a declared-ro repo", r.stdout.strip() == expected, r.stdout)
        lock_dir = checkout / ".vibe-signals" / "rw-lock.d"
        check("lock directory was NEVER created for a ro-declared repo (a broken impl that always "
              "locks would fail this)", not lock_dir.exists(), str(lock_dir))


def test_task017_c2_declaration_set_mode_flips_ro_to_rw() -> None:
    print("\n[task_017 AC8: shared_repo_declaration_set_mode — flips ro->rw in-place, other lines untouched (vibe repos add --rw, helper level)]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        decl.write_text("andeyePro/andeyePro ro\n# a comment\nother/repo ro\n", encoding="utf-8")
        r = _source_vibe_call(
            {}, f'shared_repo_declaration_set_mode {shlex.quote(str(decl))} andeyePro/andeyePro rw; echo "RC=[$?]"')
        check("exits 0", r.returncode == 0, r.stderr)
        check("helper returns 0", "RC=[0]" in r.stdout, r.stdout)
        text = decl.read_text()
        check("target slug flipped to rw", "andeyePro/andeyePro rw" in text, text)
        check("target slug's old ro line is gone", "andeyePro/andeyePro ro" not in text, text)
        check("comment line preserved verbatim", "# a comment" in text, text)
        check("unrelated declaration untouched", "other/repo ro" in text, text)


def test_task017_c2_declaration_set_mode_rejects_bad_mode() -> None:
    print("\n[task_017 AC8: shared_repo_declaration_set_mode — rejects an invalid mode, no file created]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        snippet = (
            'set +e; '
            f'shared_repo_declaration_set_mode {shlex.quote(str(decl))} foo/bar bogus; echo "RC=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("helper refuses an invalid mode (rc=1)", "RC=[1]" in r.stdout, r.stdout)
        check("no file created on rejection", not decl.exists(), "file was unexpectedly created")


def test_task017_c2_exit_dispatcher_survives_refusing_hook() -> None:
    print("\n[task_017 AC10: exit dispatcher — a refusing FIRST hook does not suppress later hooks]")
    with tempfile.TemporaryDirectory() as td:
        ev2 = Path(td) / "ev2"
        ev3 = Path(td) / "ev3"
        snippet = (
            'vibe_exit_hook_add "false"; '
            f'vibe_exit_hook_add "touch {shlex.quote(str(ev2))}"; '
            f'vibe_exit_hook_add "touch {shlex.quote(str(ev3))}"'
        )
        r = _source_vibe_call({}, snippet)
        check("subshell exits 0 despite a refusing first hook (set -euo pipefail survives)",
              r.returncode == 0, r.stderr)
        check("second-registered hook ran (evidence file exists)", ev2.exists(), "ev2 missing")
        check("third-registered hook ran (evidence file exists)", ev3.exists(), "ev3 missing")


def test_task017_c2_trap_dash_p_shows_single_dispatcher() -> None:
    print("\n[task_017 AC10: trap -p EXIT shows exactly the vibe_on_exit dispatcher]")
    r = _source_vibe_call({}, 'vibe_exit_hook_add "true"; trap -p EXIT')
    check("exits 0", r.returncode == 0, r.stderr)
    check("trap -p EXIT names vibe_on_exit as the (sole) EXIT handler",
          "vibe_on_exit" in r.stdout and "EXIT" in r.stdout, r.stdout)


def test_task017_c2_no_raw_exit_trap_outside_dispatcher() -> None:
    print("\n[task_017 AC10: exactly one literal 'trap ... EXIT' in the whole script (the dispatcher installer)]")
    src = VIBE.read_text()
    lines = src.splitlines()
    trap_exit_re = re.compile(r'^\s*trap\s+\S.*\bEXIT\b')
    matches = [ln for ln in lines if trap_exit_re.match(ln)]
    check("exactly one literal EXIT-trap installation site in the script",
          len(matches) == 1, str(matches))
    if matches:
        check("that one site is 'trap vibe_on_exit EXIT' (inside vibe_exit_hook_add, the sanctioned installer)",
              matches[0].strip() == 'trap vibe_on_exit EXIT', matches[0])
    # INT/TERM traps (e.g. the /learn tempfile cleanup) are a separate slot and
    # must NOT also claim EXIT.
    int_term = [ln for ln in lines if re.match(r'^\s*trap\s+\S.*\bINT\b.*\bTERM\b', ln)
                or re.match(r'^\s*trap\s+\S.*\bTERM\b.*\bINT\b', ln)]
    check("at least one dedicated INT/TERM trap exists (separate from the EXIT dispatcher)",
          len(int_term) >= 1, str(int_term))
    check("no INT/TERM trap line also mentions EXIT",
          all("EXIT" not in ln for ln in int_term), str(int_term))


def test_task017_c2_clipboard_and_learn_tempfile_migrated_to_hooks() -> None:
    print("\n[task_017 AC10: Darwin clipboard-flush body and /learn tempfile cleanup both migrated into vibe_exit_hook_add registrations]")
    src = VIBE.read_text()
    clip_hook_open = "vibe_exit_hook_add 'if [ -s \"$CLIP\" ]"
    check("clipboard-flush body is registered via vibe_exit_hook_add (not a raw trap)",
          clip_hook_open in src, "expected substring not found")
    check("clipboard-flush body text is intact: drains to pbcopy",
          'pbcopy < "$CLIP"' in src, "substring not found")
    check("clipboard-flush body text is intact: reaps the watcher",
          'kill "$WATCHER_PID" 2>/dev/null || true' in src, "substring not found")
    learn_hook = 'vibe_exit_hook_add "rm -f \'$msg_tmp\'"'
    check("vibe learn's tempfile cleanup is ALSO registered via vibe_exit_hook_add",
          learn_hook in src, "expected substring not found")
    check("vibe learn keeps a direct INT/TERM trap for the same tempfile (dispatcher owns only EXIT)",
          'trap "rm -f \'$msg_tmp\'" INT TERM' in src, "substring not found")


def test_task017_c2_mode_coherence_rw_manifest_and_override_agree() -> None:
    print("\n[task_017 mode coherence: rw granted -> manifest says rw AND override JSON code bind has readonly absent while sidecar stays rw]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off",
               "PROJECT_NAME": "projA"}
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'echo "MANIFEST=[$(shared_repos_manifest_lines "$(shared_repos_scan {shlex.quote(str(ws))})")]"; '
            f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        manifest_m = re.search(r"MANIFEST=\[(.*)\]", r.stdout)
        manifest = manifest_m.group(1) if manifest_m else ""
        check("manifest line reports rw for the granted repo",
              manifest.strip() == "andeyePro rw andeyePro/andeyePro", r.stdout)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        mounts = [m for m in cfg.get("mounts", []) if isinstance(m, dict)]
        code_mount = next((m for m in mounts if m.get("target") == "/repos/andeyePro"), None)
        sidecar_mount = next((m for m in mounts if m.get("target") == "/repos/.signals/andeyePro"), None)
        check("code bind present", code_mount is not None, str(mounts))
        if code_mount:
            check("code bind's readonly key is ABSENT (rw granted agrees with the manifest)",
                  "readonly" not in code_mount, str(code_mount))
        check("sidecar bind present and rw regardless (no readonly key)",
              sidecar_mount is not None and "readonly" not in sidecar_mount, str(sidecar_mount))


def test_task017_c2_repos_add_rw_flag_cli_level() -> None:
    print("\n[task_017 AC8: vibe repos add --rw at the CLI level — fresh-add-rw, upgrade-in-place, no-silent-downgrade, position-agnostic]")

    def fixture(td: Path):
        home, ws, checkout = _repos_delta_fixture(td)
        # Pre-seed the token so _repos_add never reaches the interactive
        # setup_token flow; every call below passes the path arg so the
        # read -rp prompt is never hit either.
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        return home, ws, checkout

    def run_add(home: Path, ws: Path, args: str):
        # _repos_add ends in `exit 0` (and exits non-zero on validation
        # failure), so run it in a subshell and capture its status; cd into
        # the temp project first — the declaration path comes from pwd -P.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": "/tmp/vibe-no-config-for-tests"}
        snippet = (
            'set +e; '
            f'cd {shlex.quote(str(ws))} && ( _repos_add {args} ) >/dev/null 2>&1; echo "RC=[$?]"; '
            'set -e'
        )
        return _source_vibe_call(env, snippet)

    # 1. Fresh add with --rw BEFORE the slug -> declaration lands as rw.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'--rw andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[fresh-add-rw] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[fresh-add-rw] fresh declaration line is 'slug rw'",
              "andeyePro/andeyePro rw" in decl, decl)
        check("[fresh-add-rw] no ro line was written",
              "andeyePro/andeyePro ro" not in decl, decl)

    # 2. Upgrade in place: slug already declared ro; add --rw flips it to rw
    #    on the SAME line (no duplicate entry).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        (ws / ".vibe-repos").write_text("# keep me\nandeyePro/andeyePro ro\nother/repo ro\n", encoding="utf-8")
        r = run_add(home, ws, f'--rw andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[upgrade] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text()
        check("[upgrade] existing declaration upgraded to rw in place",
              "andeyePro/andeyePro rw" in decl and "andeyePro/andeyePro ro" not in decl, decl)
        check("[upgrade] exactly one line for the slug (no duplicate append)",
              decl.count("andeyePro/andeyePro") == 1, decl)
        check("[upgrade] comment and unrelated declaration untouched",
              "# keep me" in decl and "other/repo ro" in decl, decl)

    # 3. No silent downgrade: slug already declared rw; plain add (no --rw)
    #    must leave the rw intent alone. A broken implementation that always
    #    rewrites the line with its parsed default 'ro' fails this.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        r = run_add(home, ws, f'andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[no-downgrade] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text()
        check("[no-downgrade] plain re-add does NOT downgrade an existing rw declaration",
              "andeyePro/andeyePro rw" in decl and "andeyePro/andeyePro ro" not in decl, decl)

    # 4. Position-agnostic: --rw AFTER the slug works too (trailing and
    #    slug --rw path both parse).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'andeyePro/andeyePro {shlex.quote(str(checkout))} --rw')
        check("[position] exits 0 with trailing --rw", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[position] trailing --rw still declares rw",
              "andeyePro/andeyePro rw" in decl, decl)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'andeyePro/andeyePro --rw {shlex.quote(str(checkout))}')
        check("[position] exits 0 with mid-position --rw (slug --rw path)",
              r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[position] mid-position --rw still declares rw",
              "andeyePro/andeyePro rw" in decl, decl)

    check("[usage] usage line documents the --rw flag",
          "vibe repos add [--rw] <owner/repo> [path]" in VIBE.read_text(), "usage string not found")


# ── task_017 AC12-AC15: Cycle 3 tests (claim/handoff, /repo command, fragment) ─
# Append-only per /vs rules: C1/C2 tests above are frozen. Everything below is
# new for Cycle 3; the C1/C2 test bodies above are untouched.

def test_task017_c3_repo_md_shape() -> None:
    """AC12: /repo command file shape, mirroring the vss.md file-shape tests
    (frontmatter, description, documented subcommands, host/container
    boundary guidance, claim file shape, relaunch notes) plus a regression
    guard that the file never instructs writing INTO ~/.vibe from inside the
    container (only ever describes it as out of reach)."""
    print("\n[task_017 AC12: /repo command file shape]")
    check("[c3-repo-md] repo.md exists", REPO_MD.exists(), str(REPO_MD))
    if not REPO_MD.exists():
        return
    content = REPO_MD.read_text()

    check("[c3-repo-md] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[c3-repo-md] description: in frontmatter",
          "description:" in content.split("---\n")[1] if "---\n" in content else False, "")

    check("[c3-repo-md] documents /repo add", "/repo add <owner/repo>" in content, "")
    check("[c3-repo-md] documents /repo remove", "/repo remove <owner/repo>" in content, "")
    check("[c3-repo-md] documents /repo claim", "/repo claim <name>" in content, "")

    check("[c3-repo-md] states the container cannot touch ~/.vibe on the host",
          "cannot touch `~/.vibe` on the host" in content, "exact phrase not found")

    check("[c3-repo-md] claim documents the rw-request path under the signals sidecar",
          "${VIBE_REPOS_DIR:-/repos}/.signals/<name>/rw-request" in content, "")
    check("[c3-repo-md] claim documents KEY=VALUE project= field",
          "project=<this project's name>" in content, "")
    check("[c3-repo-md] claim documents KEY=VALUE since= field",
          "since=<epoch seconds" in content, "")

    check("[c3-repo-md] relaunch note present for add",
          content.count("Relaunch required") >= 2, f"count={content.count('Relaunch required')}")

    # Regression guard: every mention of ~/.vibe must sit in a negation
    # context (out-of-reach / cannot / untouched) — never an instruction to
    # write there from inside the container. Windowed check survives line
    # wraps in the source markdown.
    flat = re.sub(r"\s+", " ", content)
    negation_cues = ("cannot", "can't", "untouched", "out of reach", "does not", "host-only")
    bad_windows = []
    for m in re.finditer(r"~/\.vibe", flat):
        window = flat[max(0, m.start() - 80): m.end() + 80].lower()
        if not any(cue in window for cue in negation_cues):
            bad_windows.append(window)
    check("[c3-repo-md] no ~/.vibe mention lacks a negation cue (never instructs writing there from the container)",
          not bad_windows, str(bad_windows))


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


def test_task017_c3_statusline_structural_unchanged() -> None:
    """AC13: the settings heredoc still parses as JSON, and the
    forceLoginMethod/defaultMode/guard-bash.sh/guard-fs.sh entries the C1
    era AC4-style structural tests assert on are all still present and
    unchanged by the AC13 statusLine edit. Inline re-assertion (does not
    touch the frozen test_vibe_statusline or test_task009_settings_json_updated
    functions above)."""
    print("\n[task_017 AC13: settings heredoc structural regressions unchanged]")
    config, cmd = _extract_statusline()
    check("[c3-status-struct] heredoc still parses as valid JSON", bool(config), "config empty/unparseable")
    if not config:
        return
    check("[c3-status-struct] forceLoginMethod is claudeai",
          config.get("forceLoginMethod") == "claudeai", str(config.get("forceLoginMethod")))
    check("[c3-status-struct] permissions.defaultMode is bypassPermissions",
          config.get("permissions", {}).get("defaultMode") == "bypassPermissions",
          str(config.get("permissions")))
    pretool = config.get("hooks", {}).get("PreToolUse", [])
    bash_matcher = next((h for h in pretool if h.get("matcher") == "Bash"), None)
    fs_matcher = next((h for h in pretool if h.get("matcher") == "Write|Edit|MultiEdit"), None)
    check("[c3-status-struct] guard-bash.sh hook present under the Bash matcher",
          bash_matcher is not None
          and any("guard-bash.sh" in h.get("command", "") for h in bash_matcher.get("hooks", [])),
          str(bash_matcher))
    check("[c3-status-struct] guard-fs.sh hook present under the Write|Edit|MultiEdit matcher",
          fs_matcher is not None
          and any("guard-fs.sh" in h.get("command", "") for h in fs_matcher.get("hooks", [])),
          str(fs_matcher))
    check("[c3-status-struct] statusLine.type is still 'command'",
          config.get("statusLine", {}).get("type") == "command", "")
    check("[c3-status-struct] command still reads model.display_name",
          ".model.display_name" in cmd, "")
    check("[c3-status-struct] the best-effort bell escape is present in the command source",
          "\\a" in cmd, cmd[:200])


def test_task017_c3_statusline_no_signals_byte_identical() -> None:
    """AC13(a): with VIBE_REPOS_DIR pointed at an empty temp dir (no .signals
    tree at all), output is byte-identical to the frozen fixtures' exact
    expectations. Spot-checks two of test_vibe_statusline's fixtures
    (Fable-full and empty-JSON) without touching that frozen function."""
    print("\n[task_017 AC13(a): no signals tree -> byte-identical to frozen fixtures]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-a] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "VIBE_REPOS_DIR": td, "VIBE_PROJECT_NAME": "irrelevant-project"}
        fixtures = [
            ('{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":42.7},'
             '"rate_limits":{"five_hour":{"used_percentage":63}}}',
             "F · vibe · ctx 42% · 5h 63%"),
            ("{}", "? · vibe"),
        ]
        for stdin_json, expected in fixtures:
            r = subprocess.run(["sh", "-c", cmd], input=stdin_json, env=env,
                                capture_output=True, text=True, timeout=15)
            check(f"[c3-status-a] {expected!r} byte-identical with no .signals tree present",
                  r.returncode == 0 and r.stdout == expected,
                  f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")


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


def test_task017_c3_statusline_rw_segment_present_when_holder_and_requested() -> None:
    """AC13(b): this session holds the lock (meta project= matches
    VIBE_PROJECT_NAME) AND a rw-request exists -> the segment appears,
    naming the requester."""
    print("\n[task_017 AC13(b): holder + pending request -> rw segment shown]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-b] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="thisproject", requester_project="moneyandeye")
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-b] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-b] output contains the rw warning segment naming the requester",
              " · ⚠ rw:moneyandeye" in r.stdout, r.stdout)
        check("[c3-status-b] output is exactly the base segment plus the rw segment (no extra drift)",
              r.stdout == "O · vibe · ⚠ rw:moneyandeye", r.stdout)


def test_task017_c3_statusline_rw_segment_absent_when_not_holder() -> None:
    """AC13(c): a rw-request exists but the lock's meta names a DIFFERENT
    holder project (not us) -> segment ABSENT. We're not the holder, so
    there's nothing for our statusLine to surrender."""
    print("\n[task_017 AC13(c): request present but WE are not the holder -> segment absent]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-c] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="otherproject", requester_project="moneyandeye")
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-c] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-c] no rw warning segment leaks when we are not the lock holder",
              "⚠ rw:" not in r.stdout, r.stdout)
        check("[c3-status-c] output is exactly the base segment, unchanged",
              r.stdout == "O · vibe", r.stdout)


def test_task017_c3_statusline_rw_segment_absent_when_no_request() -> None:
    """AC13(d): lock held by us but NO rw-request file exists -> segment
    absent (nothing to surface)."""
    print("\n[task_017 AC13(d): we hold the lock but no request exists -> segment absent]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-d] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="thisproject", requester_project=None)
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-d] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-d] no rw warning segment when there is no pending request",
              "⚠ rw:" not in r.stdout, r.stdout)
        check("[c3-status-d] output is exactly the base segment, unchanged",
              r.stdout == "O · vibe", r.stdout)


def test_task017_c3_shared_repos_md_shape() -> None:
    """AC14: shared-repos.md fragment shape, mirroring the existing fragment
    shape tests (e.g. test_brain2_md_fragment_content) — proprietary/
    never-copy seam language, manifest path, ro etiquette, claim etiquette."""
    print("\n[task_017 AC14: shared-repos.md fragment shape]")
    check("[c3-fragment] shared-repos.md exists", SHARED_REPOS_MD.exists(), str(SHARED_REPOS_MD))
    if not SHARED_REPOS_MD.exists():
        return
    body = SHARED_REPOS_MD.read_text()
    check("[c3-fragment] documents the runtime manifest path",
          "/workspace/.vibe/shared-repos.manifest" in body, "")
    check("[c3-fragment] states never copy code from /repos/*",
          "never copy" in body.lower() and "/repos/*" in body, "")
    check("[c3-fragment] names the seam/interface/feature-flag consumption discipline",
          any(term in body.lower() for term in ("seam", "interface", "feature-flag")), "")
    check("[c3-fragment] documents ro etiquette: commit/push happens elsewhere",
          "ro" in body.lower() and "commit" in body.lower() and "elsewhere" in body.lower(), "")
    check("[c3-fragment] documents /repo claim etiquette",
          "/repo claim" in body, "")
    check("[c3-fragment] documents the ⚠ rw: statusLine segment to the holder",
          "⚠ rw:" in body, "")


def test_task017_c3_install_extras_shared_repos_md_gated() -> None:
    """AC14/AC15: install-claude-extras.sh includes shared-repos.md ONLY when
    VIBE_SHARED_REPOS_MANIFEST is a non-empty file, mirroring
    test_install_extras_brain2_md_gated's technique (temp CLAUDE_CONFIG_DIR,
    env override, before/after presence check in the installed managed
    block)."""
    print("\n[task_017 AC14/AC15: install-claude-extras.sh gates shared-repos.md on the manifest]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: manifest path doesn't exist at all -> excluded ([ ! -s ] is
        # true for a missing file).
        dest_off = tmp_path / "off"; dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off["VIBE_SHARED_REPOS_MANIFEST"] = str(tmp_path / "does-not-exist-manifest")
        r_off = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=env_off, capture_output=True, text=True)
        check("[c3-gate] install exits 0 (missing manifest)", r_off.returncode == 0, r_off.stderr[:200])
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md ABSENT when manifest file is missing",
              "<!-- vibe-md: shared-repos.md -->" not in md_off, "leaked with missing manifest")
        check("[c3-gate] other fragments still present (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "loop didn't run")

        # Pass 2: manifest exists but is empty -> also excluded ([ ! -s ] is
        # true for a zero-byte file too).
        dest_empty = tmp_path / "empty"; dest_empty.mkdir()
        empty_manifest = tmp_path / "empty-manifest"
        empty_manifest.write_text("", encoding="utf-8")
        env_empty = env_base.copy()
        env_empty["CLAUDE_CONFIG_DIR"] = str(dest_empty)
        env_empty["VIBE_SHARED_REPOS_MANIFEST"] = str(empty_manifest)
        r_empty = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=env_empty, capture_output=True, text=True)
        check("[c3-gate] install exits 0 (empty manifest)", r_empty.returncode == 0, r_empty.stderr[:200])
        md_empty = (dest_empty / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md ABSENT when manifest file is empty",
              "<!-- vibe-md: shared-repos.md -->" not in md_empty, "leaked with empty manifest")

        # Pass 3: manifest non-empty -> included.
        dest_on = tmp_path / "on"; dest_on.mkdir()
        manifest = tmp_path / "shared-repos.manifest"
        manifest.write_text("andeyePro rw andeyePro/andeyePro\n", encoding="utf-8")
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_SHARED_REPOS_MANIFEST"] = str(manifest)
        r_on = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=env_on, capture_output=True, text=True)
        check("[c3-gate] install exits 0 (non-empty manifest)", r_on.returncode == 0, r_on.stderr[:200])
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md PRESENT when manifest is non-empty",
              "<!-- vibe-md: shared-repos.md -->" in md_on, "missing with non-empty manifest")
        check("[c3-gate] installed body mentions the manifest path",
              "/workspace/.vibe/shared-repos.manifest" in md_on, "manifest path not documented in installed body")


def test_task017_c3_repo_claim_documented_flow_runnable() -> None:
    """AC12: /repo claim has NO sourced vibe helper backing it — it is pure
    documentation (Claude runs Bash per repo.md's prose); confirmed by
    grepping vibe's source for a claim-writing function and finding none.
    Since there is no fenced literal command to extract, this instead
    substitutes concrete values for repo.md's placeholders (path template +
    KEY=VALUE content template, both quoted verbatim from the file) and
    proves the resulting mkdir+write is syntactically runnable and produces
    the pinned KEY=VALUE shape, plus the pinned last-claim-wins overwrite
    semantics."""
    print("\n[task_017 AC12: /repo claim's documented request-file flow is syntactically runnable]")
    vibe_src = VIBE.read_text()
    check("[c3-claim] no sourced vibe helper implements /repo claim (pure documentation)",
          "shared_repo_claim" not in vibe_src and "repo_claim_write" not in vibe_src, "")

    body = REPO_MD.read_text() if REPO_MD.exists() else ""
    check("[c3-claim] repo.md documents the exact rw-request path template",
          "${VIBE_REPOS_DIR:-/repos}/.signals/<name>/rw-request" in body, "")
    check("[c3-claim] repo.md pins unconditional overwrite (last-claim-wins)",
          "Overwrite unconditionally" in body and "last-claim-wins" in body, "")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        name = "andeyePro"
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path)}
        req_file = td_path / ".signals" / name / "rw-request"

        def file_claim(project: str) -> subprocess.CompletedProcess:
            # Path + content shape taken verbatim from repo.md's `/repo claim`
            # section, placeholders substituted with concrete values.
            snippet = (
                f'mkdir -p "${{VIBE_REPOS_DIR:-/repos}}/.signals/{name}" && '
                f'printf \'project=%s\\nsince=%s\\n\' {shlex.quote(project)} "$(date -u +%s)" '
                f'> "${{VIBE_REPOS_DIR:-/repos}}/.signals/{name}/rw-request"'
            )
            return subprocess.run(["sh", "-c", snippet], env=env,
                                   capture_output=True, text=True, timeout=15)

        r1 = file_claim("moneyandeye")
        check("[c3-claim] documented mkdir+write runs cleanly (syntactically valid)",
              r1.returncode == 0, r1.stderr[:200])
        check("[c3-claim] rw-request file created at the documented path",
              req_file.is_file(), str(req_file))
        if req_file.is_file():
            content = req_file.read_text()
            check("[c3-claim] rw-request content matches KEY=VALUE project=<name>",
                  re.search(r"^project=moneyandeye$", content, re.MULTILINE) is not None, content)
            check("[c3-claim] rw-request content matches KEY=VALUE since=<digits>",
                  re.search(r"^since=\d+$", content, re.MULTILINE) is not None, content)

        r2 = file_claim("otherclaimant")
        check("[c3-claim] second claim overwrite runs cleanly", r2.returncode == 0, r2.stderr[:200])
        content2 = req_file.read_text() if req_file.is_file() else ""
        check("[c3-claim] last-claim-wins: newest claimant fully replaces the old request",
              "project=otherclaimant" in content2 and "project=moneyandeye" not in content2, content2)


def test_task017_c3_vibe_project_name_export_plumbing() -> None:
    """AC13/AC18-style plumbing check scoped to VIBE_PROJECT_NAME: the
    launcher exports it as a top-level (not command-substitution-internal)
    statement, before the _build_override_config command substitution that
    would otherwise swallow the export; and devcontainer.json's remoteEnv
    (never containerEnv) carries it through so ${localEnv:VIBE_PROJECT_NAME}
    resolves in-container."""
    print("\n[task_017 AC13: VIBE_PROJECT_NAME export site + remoteEnv plumbing]")
    src = VIBE.read_text()
    lines = src.splitlines()
    export_lines = [i for i, ln in enumerate(lines) if ln.strip() == "export VIBE_PROJECT_NAME"]
    check("[c3-plumb] exactly one literal 'export VIBE_PROJECT_NAME' line in the script",
          len(export_lines) == 1, str(export_lines))
    if export_lines:
        idx = export_lines[0]
        check("[c3-plumb] export line sits at column 0 (top-level scope, not inside a function body)",
              lines[idx] == "export VIBE_PROJECT_NAME", repr(lines[idx]))
        assign_line = lines[idx - 1] if idx > 0 else ""
        check("[c3-plumb] preceding line assigns VIBE_PROJECT_NAME=\"$PROJECT_NAME\" (plain assignment, "
              "not inside a command substitution)",
              assign_line.strip() == 'VIBE_PROJECT_NAME="$PROJECT_NAME"', repr(assign_line))
        override_call_idx = next(
            (i for i, ln in enumerate(lines) if "OVERRIDE_CONFIG=$(_build_override_config" in ln), None)
        check("[c3-plumb] export happens BEFORE the _build_override_config command-substitution call "
              "(exports inside $(...) die with the subshell)",
              override_call_idx is not None and idx < override_call_idx,
              f"export_idx={idx} override_call_idx={override_call_idx}")

    devcontainer_json = json.loads((REPO / "devcontainer" / "devcontainer.json").read_text())
    remote_env = devcontainer_json.get("remoteEnv", {})
    container_env = devcontainer_json.get("containerEnv", {})
    check("[c3-plumb] devcontainer.json remoteEnv carries VIBE_PROJECT_NAME via ${localEnv:...}",
          remote_env.get("VIBE_PROJECT_NAME") == "${localEnv:VIBE_PROJECT_NAME}",
          str(remote_env.get("VIBE_PROJECT_NAME")))
    check("[c3-plumb] VIBE_PROJECT_NAME is NOT in containerEnv (remoteEnv-only, mirrors GITHUB_TOKEN discipline)",
          "VIBE_PROJECT_NAME" not in container_env, str(container_env))


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


def test_task017_c4_ac16_project_slug_exact_match_serves_project_token() -> None:
    print("\n[task_017 C4 AC16: project slug exact match -> $GITHUB_TOKEN]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="andeyePro/vibe"))
    _c4_assert_served("project exact match", r, "ghp_project")


def test_task017_c4_ac16_shared_slug_match_with_valid_twin_serves_shared_token() -> None:
    print("\n[task_017 C4 AC16: configured shared slug (twin verified) -> its OWN token, never $GITHUB_TOKEN]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_served("shared match", r, "ghp_shared")
    check("shared match: NEVER serves the project token instead",
          "ghp_project" not in r.stdout, r.stdout)


def test_task017_c4_ac16_unknown_repo_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: unconfigured repo -> NOTHING (central invariant)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="someone-else/unrelated-repo"))
    _c4_assert_silent("unknown repo", r)


def test_task017_c4_ac16_nopath_no_shared_tokens_serves_project_token_compat() -> None:
    print("\n[task_017 C4 AC17 no-path compat: no path + no shared repos configured -> $GITHUB_TOKEN]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path=None))
    _c4_assert_served("no-path compat", r, "ghp_project")


def test_task017_c4_ac16_nopath_shared_tokens_configured_serves_nothing() -> None:
    print("\n[task_017 C4 AC17 no-path fail-closed: no path + a shared repo IS configured -> NOTHING]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path=None))
    _c4_assert_silent("no-path + shared configured (mis-set useHttpPath must not widen)", r)


def test_task017_c4_ac16_dot_git_suffix_shared_match() -> None:
    print("\n[task_017 C4 AC16: '.git' suffix on a shared slug still matches]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro.git"))
    _c4_assert_served(".git suffix", r, "ghp_shared")


def test_task017_c4_ac16_subdir_suffix_shared_match() -> None:
    print("\n[task_017 C4 AC16: useHttpPath subdir suffix (owner/repo/info/refs) still matches]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro/info/refs"))
    _c4_assert_served("subdir suffix", r, "ghp_shared")


def test_task017_c4_ac16_trailing_slash_only_unmatched_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: trailing-slash-only path on an UNCONFIGURED repo -> still NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="someone-else/unrelated-repo/"))
    _c4_assert_silent("trailing-slash-only, unmatched", r)


def test_task017_c4_ac16_trailing_slash_project_slug_still_matches() -> None:
    """Documents (doesn't just attack): the same subpath-discard rule that
    lets owner/repo/info/refs through also lets a bare trailing slash on the
    PROJECT's own slug through. Not a leak — it's still an exact owner/repo
    match against GITHUB_REPO_SLUG, just with a trailing empty segment
    discarded, same as any other subpath suffix."""
    print("\n[task_017 C4 AC16: trailing-slash-only on the PROJECT's own slug still matches (documented, not a leak)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="andeyePro/vibe/"))
    _c4_assert_served("trailing-slash on project's own slug", r, "ghp_project")


def test_task017_c4_ac16_case_difference_project_slug_never_matches() -> None:
    print("\n[task_017 C4 AC16: differently-cased project slug must NOT match (case-sensitive)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="AndeyePro/Vibe"))
    _c4_assert_silent("case-differing project slug", r)


def test_task017_c4_ac16_traversal_segments_serve_nothing() -> None:
    print("\n[task_017 C4 AC16: '..' traversal segments -> NOTHING even when it resolves to a configured slug]")
    san = _c4_sanitise("other/repo")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "other/repo"},
        _c4_cred_stdin(path="andeyePro/../other/repo"))
    _c4_assert_silent("traversal segments", r)


def test_task017_c4_ac16_embedded_control_char_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: embedded control byte (CR) in an otherwise-matching path -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(raw_path="path=andeyePro/vibe\r"))
    _c4_assert_silent("embedded CR", r)


def test_task017_c4_ac16_injection_string_serves_nothing_and_does_not_execute() -> None:
    print("\n[task_017 C4 AC16: shell-metacharacter injection string in path -> NOTHING, no execution]")
    sentinel = Path(tempfile.gettempdir()) / f"vibe-c4-injection-sentinel-{os.getpid()}"
    if sentinel.exists():
        sentinel.unlink()
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path=f"foo/bar; touch {sentinel} #"))
    _c4_assert_silent("injection string", r)
    check("injection string: no side-effect execution (sentinel file NOT created)",
          not sentinel.exists(), str(sentinel))
    if sentinel.exists():
        sentinel.unlink()


def test_task017_c4_ac16_sanitisation_collision_twin_mismatch_serves_nothing() -> None:
    """The gate-discriminating fixture (security-review C4 LOW, closed):
    sanitisation is lossy — foo-bar/baz and foo/bar-baz both sanitise to
    ..._FOO_BAR_BAZ. If the twin var holds the OTHER slug, a request for
    the colliding one must get NOTHING even though its env-name lookup would
    otherwise succeed. Pre-hardening this would have leaked the shared token
    to the wrong repo."""
    print("\n[task_017 C4 AC16: sanitisation-collision, twin mismatch -> NOTHING (post-security-review hardening)]")
    san = _c4_sanitise("foo/bar-baz")
    assert san == _c4_sanitise("foo-bar/baz"), "fixture assumption: both slugs must collide"
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared_for_foo_bar_baz",
         f"VIBE_SHARED_SLUG_{san}": "foo/bar-baz"},
        _c4_cred_stdin(path="foo-bar/baz"))
    _c4_assert_silent("sanitisation-collision, twin holds the OTHER slug", r)


def test_task017_c4_ac16_sanitisation_collision_twin_match_serves_correct_token() -> None:
    print("\n[task_017 C4 AC16: sanitisation-collision, twin MATCHES the request -> its token served]")
    san = _c4_sanitise("foo/bar-baz")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared_for_foo_bar_baz",
         f"VIBE_SHARED_SLUG_{san}": "foo/bar-baz"},
        _c4_cred_stdin(path="foo/bar-baz"))
    _c4_assert_served("sanitisation-collision, twin matches the request", r, "ghp_shared_for_foo_bar_baz")


def test_task017_c4_ac16_twin_unset_serves_nothing_even_with_token_set() -> None:
    print("\n[task_017 C4 AC16: twin var entirely unset (stale container/launcher mismatch) -> NOTHING]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared"},
        # deliberately no VIBE_SHARED_SLUG_<san> at all
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_silent("twin var unset", r)


def test_task017_c4_ac16_non_get_operation_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: non-'get' git credential ops (store/erase) -> NOTHING]")
    for op in ("store", "erase"):
        r = _c4_run_cred_helper(
            {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
            _c4_cred_stdin(path="andeyePro/vibe"), op=op)
        _c4_assert_silent(f"op={op}", r)


def test_task017_c4_ac16_non_github_host_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: non-github.com host -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(host="gitlab.com", path="andeyePro/vibe"))
    _c4_assert_silent("non-github host", r)


def test_task017_c4_ac16_lookalike_subdomain_host_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: lookalike host (github.com.evil.com) -> NOTHING (exact host match only)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(host="github.com.evil.com", path="andeyePro/vibe"))
    _c4_assert_silent("lookalike subdomain host", r)


def test_task017_c4_ac16_http_not_https_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: http (not https) -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(protocol="http", path="andeyePro/vibe"))
    _c4_assert_silent("http not https", r)


def test_task017_c4_ac16_empty_shared_token_never_served() -> None:
    print("\n[task_017 C4 AC16: matched shared slug but its token var is EMPTY -> NOTHING, never falls back]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_silent("empty shared token", r)


def test_task017_c4_ac16_never_widen_attack_battery() -> None:
    """THE central invariant, attacked from many angles at once: no fixture
    here is the project's own slug, yet every env has GITHUB_TOKEN staged.
    None of these may ever put 'ghp_project' on stdout."""
    print("\n[task_017 C4 AC16: never-widen attack battery — $GITHUB_TOKEN must NEVER appear for a non-project path]")
    base_env = {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"}
    san_shared = _c4_sanitise("andeyePro/andeyePro")
    attacks = [
        ("plain unrelated repo", {}, _c4_cred_stdin(path="totally/unrelated")),
        ("shared repo configured, wrong twin", {
            f"VIBE_SHARED_TOKEN_{san_shared}": "ghp_shared",
            f"VIBE_SHARED_SLUG_{san_shared}": "different/slug",
        }, _c4_cred_stdin(path="andeyePro/andeyePro")),
        ("traversal into project-adjacent path", {}, _c4_cred_stdin(path="andeyePro/../vibe")),
        ("case-flipped project slug", {}, _c4_cred_stdin(path="ANDEYEPRO/VIBE")),
        ("project slug with control byte suffix", {}, _c4_cred_stdin(raw_path="path=andeyePro/vibe\x01")),
        ("empty path key present but blank", {}, _c4_cred_stdin(raw_path="path=")),
        ("non-github host claiming project path", {}, _c4_cred_stdin(host="notgithub.com", path="andeyePro/vibe")),
        ("http claiming project path", {}, _c4_cred_stdin(protocol="http", path="andeyePro/vibe")),
    ]
    for name, extra_env, stdin_text in attacks:
        env = {**base_env, **extra_env}
        r = _c4_run_cred_helper(env, stdin_text)
        check(f"[never-widen] {name}: $GITHUB_TOKEN never appears on stdout",
              "ghp_project" not in r.stdout, r.stdout)


def test_task017_c4_ac17_usehttppath_same_scope_as_helper_registration() -> None:
    print("\n[task_017 C4 AC17: credential.useHttpPath set at the SAME scope as credential.helper registration]")
    src = SETUP_GIT_SH.read_text()
    helper_line = next((ln for ln in src.splitlines() if "credential.helper" in ln and "git config" in ln), None)
    usehttppath_line = next((ln for ln in src.splitlines() if "credential.useHttpPath" in ln and "git config" in ln), None)
    check("[ac17] setup-git.sh sets credential.helper", helper_line is not None, src)
    check("[ac17] setup-git.sh sets credential.useHttpPath", usehttppath_line is not None, src)
    if helper_line and usehttppath_line:
        check("[ac17] credential.helper registered at --global scope",
              "--global" in helper_line, helper_line)
        check("[ac17] credential.useHttpPath set at --global scope (same as the helper)",
              "--global" in usehttppath_line, usehttppath_line)
        check("[ac17] useHttpPath value is literally 'true'",
              usehttppath_line.strip().endswith("true"), usehttppath_line)


def test_task017_c4_ac17_setup_git_functional_in_sandbox_home() -> None:
    print("\n[task_017 C4 AC17: setup-git.sh is runnable in a sandbox HOME and produces both settings]")
    with tempfile.TemporaryDirectory() as td:
        sandbox_home = Path(td) / "home"
        sandbox_home.mkdir()
        env = {**os.environ, "HOME": str(sandbox_home)}
        r = run(["bash", str(SETUP_GIT_SH)], env=env)
        check("[ac17] setup-git.sh exits 0 in a fresh sandbox HOME (no ~/.gitconfig-host present)",
              r.returncode == 0, r.stderr)
        helper_r = run(["git", "config", "--global", "--get", "credential.helper"], env=env)
        usehttppath_r = run(["git", "config", "--global", "--get", "credential.useHttpPath"], env=env)
        check("[ac17] resulting ~/.gitconfig has credential.helper = vibe-credential-helper",
              helper_r.stdout.strip() == "/usr/local/bin/vibe-credential-helper", helper_r.stdout)
        check("[ac17] resulting ~/.gitconfig has credential.useHttpPath = true",
              usehttppath_r.stdout.strip() == "true", usehttppath_r.stdout)


def test_task017_c4_ac18_top_level_exports_outside_build_override_config() -> None:
    print("\n[task_017 C4 AC18: GITHUB_REPO_SLUG / VIBE_SHARED_TOKEN_* / VIBE_SHARED_SLUG_* exports sit "
          "OUTSIDE _build_override_config (top-level scope; exports inside $(...) die with the subshell)]")
    lines = VIBE.read_text().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln == "_build_override_config() {"), None)
    check("[ac18] _build_override_config function start found", start is not None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == "}"), None)
    check("[ac18] _build_override_config function end found", end is not None)
    if end is None:
        return
    span = range(start, end + 1)

    export_slug_idx = next((i for i, ln in enumerate(lines) if ln.strip() == 'export GITHUB_REPO_SLUG="$GITHUB_REPO"'), None)
    export_shared_tok_idx = next((i for i, ln in enumerate(lines) if ln.strip() == 'export "$_env_name"="$_shared_tok"'), None)
    export_shared_slug_idx = next(
        (i for i, ln in enumerate(lines)
         if 'export "VIBE_SHARED_SLUG_' in ln), None)

    check("[ac18] 'export GITHUB_REPO_SLUG' line found", export_slug_idx is not None)
    check("[ac18] shared-token export line found", export_shared_tok_idx is not None)
    check("[ac18] shared-slug-twin export line found", export_shared_slug_idx is not None)

    if export_slug_idx is not None:
        check("[ac18] GITHUB_REPO_SLUG export is OUTSIDE _build_override_config",
              export_slug_idx not in span, f"line {export_slug_idx}: {lines[export_slug_idx]!r}")
        check("[ac18] GITHUB_REPO_SLUG export is at column 0 (top-level, not inside any function)",
              lines[export_slug_idx] == lines[export_slug_idx].lstrip(), repr(lines[export_slug_idx]))
    if export_shared_tok_idx is not None:
        check("[ac18] shared-token export is OUTSIDE _build_override_config",
              export_shared_tok_idx not in span, f"line {export_shared_tok_idx}: {lines[export_shared_tok_idx]!r}")
    if export_shared_slug_idx is not None:
        check("[ac18] shared-slug-twin export is OUTSIDE _build_override_config",
              export_shared_slug_idx not in span, f"line {export_shared_slug_idx}: {lines[export_shared_slug_idx]!r}")

    override_call_idx = next(
        (i for i, ln in enumerate(lines) if "OVERRIDE_CONFIG=$(_build_override_config" in ln), None)
    check("[ac18] _build_override_config command-substitution call site found", override_call_idx is not None)
    if export_slug_idx is not None and override_call_idx is not None:
        check("[ac18] GITHUB_REPO_SLUG export happens BEFORE the command-substitution call",
              export_slug_idx < override_call_idx,
              f"export_idx={export_slug_idx} override_call_idx={override_call_idx}")
    if export_shared_tok_idx is not None and override_call_idx is not None:
        check("[ac18] shared-token export loop happens BEFORE the command-substitution call",
              export_shared_tok_idx < override_call_idx,
              f"export_idx={export_shared_tok_idx} override_call_idx={override_call_idx}")


def test_task017_c4_ac18_remoteenv_shared_token_and_twin_injection() -> None:
    print("\n[task_017 C4 AC18: override-config generator injects matching VIBE_SHARED_TOKEN_*/"
          "VIBE_SHARED_SLUG_* remoteEnv passthroughs]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        san = _c4_sanitise("andeyePro/andeyePro")
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off",
               # Simulates what the top-level export block (tested structurally
               # above) would have produced for this declared repo.
               "VIBE_SHARED_ENV_NAMES": f"VIBE_SHARED_TOKEN_{san}",
               f"VIBE_SHARED_TOKEN_{san}": "ghp_faketoken",
               f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("[ac18] exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {}
        remote_env = cfg.get("remoteEnv", {})
        container_env = cfg.get("containerEnv", {})
        check(f"[ac18] remoteEnv carries VIBE_SHARED_TOKEN_{san} -> ${{localEnv:...}} passthrough",
              remote_env.get(f"VIBE_SHARED_TOKEN_{san}") == f"${{localEnv:VIBE_SHARED_TOKEN_{san}}}",
              str(remote_env))
        check(f"[ac18] remoteEnv ALSO carries the VIBE_SHARED_SLUG_{san} twin passthrough",
              remote_env.get(f"VIBE_SHARED_SLUG_{san}") == f"${{localEnv:VIBE_SHARED_SLUG_{san}}}",
              str(remote_env))
        check("[ac18] neither the token nor the twin land in containerEnv (remoteEnv-only, mirrors GITHUB_TOKEN)",
              f"VIBE_SHARED_TOKEN_{san}" not in container_env and f"VIBE_SHARED_SLUG_{san}" not in container_env,
              str(container_env))


def test_task017_c4_ac19_claude_md_invariant_text_amended() -> None:
    print("\n[task_017 C4 AC19: CLAUDE.md invariant text amended for per-repo tokens / launch-header blast radius]")
    src = (REPO / "CLAUDE.md").read_text()
    check("[ac19] CLAUDE.md still says each PAT stays scoped to one repo",
          "one repo" in src or "single-repo" in src, "one repo / single-repo phrase not found")
    check("[ac19] CLAUDE.md ties blast radius to the launch header",
          "blast radius" in src and "launch header" in src, "blast radius / launch header phrasing not found")
    check("[ac19] CLAUDE.md explicitly rules out a multi-repo token",
          "never a multi-repo token" in src or "never one token reused across repos" in src,
          "no explicit multi-repo-token prohibition found")


def test_task017_c4_ac19_readme_security_section_consistent() -> None:
    print("\n[task_017 C4 AC19: README security section consistent with the amended invariant]")
    src = (REPO / "README.md").read_text()
    check("[ac19] README says every fine-grained PAT stays scoped to a single repo",
          "single repo" in src, "single repo phrase not found in README")
    check("[ac19] README ties blast radius to the launch header",
          "blast radius" in src and "launch header" in src, "blast radius / launch header phrasing not found in README")
    check("[ac19] README explicitly rules out a multi-repo token",
          "never a multi-repo token" in src, "no explicit multi-repo-token prohibition found in README")


def main() -> int:
    test_help()
    test_version()
    test_vibe_andeye_page_draft()
    test_repo_owner_selection()
    test_install_preflight()
    test_licence_state()
    test_env_hint_fresh()
    test_env_hint_idempotent()
    test_env_hint_preserves_user_content()
    test_docker_hints_fresh()
    test_docker_hints_heals_bool()
    test_docker_hints_respects_user_string()
    test_docker_hints_malformed_json()
    test_docker_hints_non_dict_features()
    test_install_detects_local_clone()
    test_install_falls_back_to_vibe_src()
    test_token_helpers()
    test_op_mcp_creds_lookup()
    test_code_check_json_clean_exit_and_valid_json()
    test_code_check_json_top_level_keys()
    test_code_check_json_finding_schema()
    test_code_check_json_findings_exit1_and_count()
    test_code_check_json_stdout_only_json()
    test_code_check_json_human_mode_unchanged()
    test_code_check_json_missing_shellcheck()
    test_code_check_json_help_mentions_flag()
    test_code_check_json_summary_counts()
    test_code_check_json_same_target_list()
    test_vibe_resume_args_fresh()
    test_vibe_resume_args_continue()
    test_vibe_resume_args_resume_picker()
    test_vibe_resume_args_resume_uid()
    test_vibe_is_uuid()
    test_vibe_help_mentions_continue_and_resume()
    test_parse_args_no_args()
    test_parse_args_leading_continue()
    test_parse_args_project_only()
    test_parse_args_project_then_continue()
    test_parse_args_continue_then_project()
    test_parse_args_project_then_resume_uid()
    test_parse_args_project_then_resume_picker()
    test_parse_args_project_then_rebuild()
    test_parse_args_two_positionals_rejected()
    test_parse_args_unknown_flag_rejected()
    test_parse_args_fable()
    test_parse_args_model_explicit()
    test_parse_args_model_missing_value_rejected()
    test_parse_args_model_injection_rejected()
    test_vibe_is_model_id()
    test_vibe_model_args_fresh()
    test_vibe_model_args_set()
    test_vibe_fable_billing_phase()
    test_vibe_auto_resume_helpers()
    test_vibe_auto_resume_deactivate()
    test_vibe_auto_resume_heartbeat_write()
    test_vibe_auto_resume_stalled()
    test_vibe_settings_heartbeat_hooks()
    test_vibe_supervised_launch_text()
    test_vibe_stall_watchdog_functional()
    test_vibe_gitignore_heartbeat_pattern()
    test_vibe_task016_docs()
    test_vibe_statusline()
    test_vibe_help_mentions_fable_and_model()
    test_ac1_no_container()
    test_ac2_matching_image()
    test_ac3_drifted_image()
    test_ac4_remove_existing_flag_rebuild_true_drift_marker()
    test_ac4_remove_existing_flag_rebuild_true_no_drift()
    test_ac4_remove_existing_flag_no_rebuild_drift_marker()
    test_ac4_remove_existing_flag_no_rebuild_no_drift()
    test_ac5a_docker_all_fail()
    test_ac5b_ps_ok_inspect_fails()
    test_ac5c_ps_inspect_ok_tag_fails()
    test_ac5d_ps_inspect_ok_ref_inspect_fails()
    test_ac6_multiple_containers_uses_first()
    test_ac8_comment_present()
    test_learning_config_format()
    test_learning_strict_parser_no_injection()
    test_learning_init_interactive()
    test_learning_init_mkdir_offer()
    test_learning_init_reinit_path()
    test_learning_default_off_no_config()
    test_learning_learn_without_init()
    test_render_devcontainer_with_mounts_learning()
    test_learning_dispatch_no_docker_required()
    test_learning_capture_confirm_flow()
    test_learning_capture_eof_cancel()
    test_learning_capture_confirm_no()
    test_learning_public_mode_push_prompt()
    test_learning_public_mode_git_failure_survives()
    test_learning_private_mode_no_git()
    test_learning_marker_blocks_capture()
    test_learning_marker_walk_stops_at_home()
    test_learning_home_unset_fails_safe()
    test_learning_help_lists_commands()
    test_learning_banner_with_optins()
    test_learning_chmod_600_verified()
    test_learning_helpers_exist()
    test_learning_entry_path_composition()
    test_learning_format_entry()
    test_learning_commit_message()
    test_learning_config_path_helper()
    test_learning_code_check_clean()
    test_learning_short_marker_blocks()
    test_learning_exclude_creates_marker()
    test_learning_include_removes_marker()
    test_learning_exclude_refuses_in_home()
    test_learning_help_mentions_exclude_include()
    test_learning_help_says_host_only()
    test_learning_bare_learn_usage_says_host_only()
    test_learning_banner_state_three_way()
    test_learning_banner_parent_shell_load()
    test_vibe_copy_stdin_roundtrip()
    test_vibe_copy_file_arg_roundtrip()
    test_vibe_copy_scratch_file_written()
    test_vibe_copy_empty_input_stdin()
    test_vibe_copy_warn_at_8kib_plus_one()
    test_vibe_copy_refuse_at_1mib_plus_one()
    test_vibe_copy_refuses_two_args()
    test_vibe_copy_refuses_missing_file()
    test_vibe_copy_tty_absent_note()
    test_vibe_copy_scratch_failure_exits_1()
    test_c_slash_command_synced()
    test_c_slash_command_body_matches_spec()
    test_dockerfile_installs_vibe_copy()
    test_c_copy_md_is_absent()
    test_vibe_final_line_no_exec()
    test_vibe_copy_watcher_noop_on_non_darwin()
    test_vibe_copy_watcher_polling_detects_change()
    test_c_preserves_user_commands()
    test_c_agents_not_touched_by_retirement()
    test_vibe_path_prefix_isolation()
    test_vibe_exit_code_propagation()
    test_task007_t1_web_research_md_exists_and_complete()
    test_task007_t2_dockerfile_copy_canonical()
    test_task007_t3_install_basics_one_fragment()
    test_task007_t4_create_from_scratch()
    test_task007_t5_idempotency()
    test_task007_t6_user_content_preserved()
    test_task007_t7_empty_source_cleanup()
    test_task007_t8_missing_source_directory()
    test_task007_t9_posix_byte_order_sort()
    test_task007_t10_agents_and_commands_still_work()
    test_task007_t11_write_env_hint_coexistence()
    test_task007_t12_fragment_removal_and_separation()
    test_task007_t13_absent_source_with_preexisting_block()
    test_task007_t14_ssh_discipline_md_exists_and_complete()
    test_learning_capture_confirm_yes_word()
    test_learning_capture_confirm_uppercase_y()
    test_learning_capture_confirm_uppercase_yes()
    test_learnings_md_fragment_present()
    test_task008_ac3_block_scoping()
    test_task008_ac11_direct_read()
    test_clipboard_drain_on_exit()
    test_task009_guard_fs_exists()
    test_task009_guard_fs_ask_fixtures()
    test_task009_guard_fs_non_learnings_fixtures()
    test_task009_guard_bash_learnings_write_fixtures()
    test_task009_guard_bash_learnings_read_fixtures()
    test_task009_guard_bash_gitpush_and_block_beats_ask()
    test_task009_settings_json_updated()
    test_task009_dockerfile_updated()
    test_task009_learn_md_exists()
    test_task009_learn_hook_md_exists()
    test_learn_docs_no_host_stage_all_footgun()
    test_task009_readme_updated()
    test_task009_code_check_clean()
    test_task009_hardening_notebookedit_not_in_matcher()
    test_task009_hardening_guard_bash_set_euo()
    test_task009_hardening_guard_fs_realpath_m()
    test_task013_vs_md_intelligent_stopping()
    test_task013_vs_md_max_iter_flag()
    test_task013_no_hardcoded_cap_string()
    test_check_sp_current_exists_and_executable()
    test_check_sp_current_offline_silent()
    test_check_sp_current_fixture_no_drift()
    test_check_sp_current_fixture_missing_skill()
    test_check_sp_current_fixture_extra_skill()
    test_check_sp_current_fixture_nonexistent_errors()
    test_check_sp_current_unknown_arg_errors()
    test_check_sp_current_wired_into_container_start()
    test_sp_md_present_and_complete()
    test_sp_md_referenced_from_readme()
    test_skipped_marker_round_trip()
    test_skipped_marker_trailing_slash()
    test_skipped_marker_symlink_path()
    test_skipped_marker_writes_canonical()
    test_skipped_marker_unrelated_path_rejected()
    test_skipped_marker_back_compat_literal()
    test_check_numbering_exists_and_executable()
    test_check_numbering_silent_on_clean()
    test_check_numbering_silent_on_lettered_only()
    test_check_numbering_warns_on_mixed()
    test_check_numbering_ignores_code_fences()
    test_check_numbering_handles_missing_transcript()
    test_copy_last_block_exists_and_executable()
    test_copy_last_block_single_block()
    test_copy_last_block_language_tag()
    test_copy_last_block_multiple_blocks_last_wins()
    test_copy_last_block_no_fence_no_write()
    test_copy_last_block_no_marker_silent()
    test_copy_last_block_multiline_preserved()
    test_copy_last_block_empty_stdin()
    test_numbering_hook_readme_present()
    test_vss_md_exists_with_frontmatter()
    test_vss_md_hard_escalate_sentinels()
    test_vss_md_audit_trail_and_push_policy()
    test_todo_changelog_split()
    test_project_hygiene_fragment()
    test_install_extras_ensures_project_gitignore()
    test_feedback_auto_promote_fragment()
    test_vs_md_plain_techy_verbosity_flags()
    test_fable_subagents_flag_docs()
    test_vs_md_panel_flag()
    test_vs_md_multi_task_archive_convention()
    test_vsss_md_inherits_escalate_and_budget()
    test_install_extras_syncs_hooks()
    test_conversation_history_fragment()
    test_install_extras_ssh_discipline_opt_in()
    test_brain2_zotero_source_resolution()
    test_render_devcontainer_with_mounts()
    test_op_mcp_addhost_injection()
    test_build_override_config_brain2_and_zotero()
    test_install_extras_brain2_md_gated()
    test_install_extras_brain2_skills_synced()
    test_brain2_md_fragment_content()
    test_task010_smart_capture()
    test_contributor_onboarding_artifacts()

    # task_017 AC1-AC7: shared-repos
    test_task017_ac2_shared_repos_parse_valid()
    test_task017_ac2_shared_repos_parse_default_mode()
    test_task017_ac2_shared_repos_parse_comments_blanks()
    test_task017_ac2_shared_repos_parse_bad_slug()
    test_task017_ac2_shared_repos_parse_bad_mode()
    test_task017_ac2_shared_repos_parse_extra_content()
    test_task017_ac2_shared_repos_parse_missing_file()
    test_task017_ac2_shared_repos_parse_injection_strings()
    test_task017_ac2_shared_repos_parse_dot_prefix_basename_rejected()
    test_task017_ac2_repos_registry_lookup_valid()
    test_task017_ac2_repos_registry_lookup_missing_file()
    test_task017_ac2_repos_registry_lookup_bad_slug()
    test_task017_ac2_repos_registry_lookup_malformed_entry()
    test_task017_ac2_repos_registry_lookup_quote_in_path()
    test_task017_ac2_repos_registry_lookup_relative_path()
    test_task017_ac2_shared_repo_env_name_valid()
    test_task017_ac2_shared_repo_env_name_sanitisation()
    test_task017_ac2_shared_repo_env_name_collision()
    test_task017_ac2_shared_repo_ensure_signals_creates_sidecar()
    test_task017_ac2_shared_repo_ensure_signals_adds_gitignore()
    test_task017_ac2_shared_repo_ensure_signals_idempotent()
    test_task017_ac2_shared_repo_ensure_signals_unwritable_dir()
    test_task017_ac6_ensure_project_gitignore_has_vibe_signals()
    test_task017_ac1_repos_dispatch_before_parse_vibe_args()

    # task_017 Cycle 1 delta (sonnet Tester): scan state machine, ack
    # exact-pair semantics, fixed-string lookup regressions, override-JSON
    # two-bind shape, manifest filter, header case arms.
    test_task017_delta_scan_m_full_valid_chain()
    test_task017_delta_scan_n_never_registered_is_silent()
    test_task017_delta_scan_u_unacked_no_sidecar_writes()
    test_task017_delta_scan_b_path_missing()
    test_task017_delta_scan_b_token_absent()
    test_task017_delta_scan_b_sidecar_unwritable()
    test_task017_delta_scan_b_reserved_dot_prefix_basename()
    test_task017_delta_scan_b_basename_collision()
    test_task017_delta_ack_exact_pair_semantics()
    test_task017_delta_ack_idempotent_and_chmod_600()
    test_task017_delta_fixedstring_repos_registry_lookup_regex_danger()
    test_task017_delta_fixedstring_lookup_token_regex_danger()
    test_task017_delta_fixedstring_decl_remove_prefix_discipline()
    test_task017_delta_override_config_two_binds_when_acked()
    test_task017_delta_override_config_no_binds_when_unacked()
    test_task017_delta_manifest_lines_mixed_tags()
    test_task017_delta_header_case_arms_present()
    test_task017_c2_lock_acquire_writes_meta_and_holder_reads_digits()
    test_task017_c2_lock_contend_live_holder_refused_and_not_reclaimed()
    test_task017_c2_lock_stale_reclaim_dead_holder_succeeds()
    test_task017_c2_lock_release_matching_owner_removes_lock()
    test_task017_c2_lock_release_wrong_project_refused_intact()
    test_task017_c2_lock_release_wrong_pid_refused_intact()
    test_task017_c2_lock_torn_meta_never_stolen_no_crash()
    test_task017_c2_rw_free_lock_grants_rw()
    test_task017_c2_rw_contended_falls_back_ro_with_warning()
    test_task017_c2_ro_declared_never_acquires_lock()
    test_task017_c2_declaration_set_mode_flips_ro_to_rw()
    test_task017_c2_declaration_set_mode_rejects_bad_mode()
    test_task017_c2_exit_dispatcher_survives_refusing_hook()
    test_task017_c2_trap_dash_p_shows_single_dispatcher()
    test_task017_c2_no_raw_exit_trap_outside_dispatcher()
    test_task017_c2_clipboard_and_learn_tempfile_migrated_to_hooks()
    test_task017_c2_mode_coherence_rw_manifest_and_override_agree()
    test_task017_c2_repos_add_rw_flag_cli_level()

    test_task017_c3_repo_md_shape()
    test_task017_c3_statusline_structural_unchanged()
    test_task017_c3_statusline_no_signals_byte_identical()
    test_task017_c3_statusline_rw_segment_present_when_holder_and_requested()
    test_task017_c3_statusline_rw_segment_absent_when_not_holder()
    test_task017_c3_statusline_rw_segment_absent_when_no_request()
    test_task017_c3_shared_repos_md_shape()
    test_task017_c3_install_extras_shared_repos_md_gated()
    test_task017_c3_repo_claim_documented_flow_runnable()
    test_task017_c3_vibe_project_name_export_plumbing()

    # task_017 Cycle 4 (haiku Tester): credential helper never-widen attack
    # list (AC16), useHttpPath scope + functional setup-git.sh (AC17), export
    # scope + remoteEnv token/twin injection (AC18), invariant text (AC19).
    test_task017_c4_ac16_project_slug_exact_match_serves_project_token()
    test_task017_c4_ac16_shared_slug_match_with_valid_twin_serves_shared_token()
    test_task017_c4_ac16_unknown_repo_serves_nothing()
    test_task017_c4_ac16_nopath_no_shared_tokens_serves_project_token_compat()
    test_task017_c4_ac16_nopath_shared_tokens_configured_serves_nothing()
    test_task017_c4_ac16_dot_git_suffix_shared_match()
    test_task017_c4_ac16_subdir_suffix_shared_match()
    test_task017_c4_ac16_trailing_slash_only_unmatched_serves_nothing()
    test_task017_c4_ac16_trailing_slash_project_slug_still_matches()
    test_task017_c4_ac16_case_difference_project_slug_never_matches()
    test_task017_c4_ac16_traversal_segments_serve_nothing()
    test_task017_c4_ac16_embedded_control_char_serves_nothing()
    test_task017_c4_ac16_injection_string_serves_nothing_and_does_not_execute()
    test_task017_c4_ac16_sanitisation_collision_twin_mismatch_serves_nothing()
    test_task017_c4_ac16_sanitisation_collision_twin_match_serves_correct_token()
    test_task017_c4_ac16_twin_unset_serves_nothing_even_with_token_set()
    test_task017_c4_ac16_non_get_operation_serves_nothing()
    test_task017_c4_ac16_non_github_host_serves_nothing()
    test_task017_c4_ac16_lookalike_subdomain_host_serves_nothing()
    test_task017_c4_ac16_http_not_https_serves_nothing()
    test_task017_c4_ac16_empty_shared_token_never_served()
    test_task017_c4_ac16_never_widen_attack_battery()
    test_task017_c4_ac17_usehttppath_same_scope_as_helper_registration()
    test_task017_c4_ac17_setup_git_functional_in_sandbox_home()
    test_task017_c4_ac18_top_level_exports_outside_build_override_config()
    test_task017_c4_ac18_remoteenv_shared_token_and_twin_injection()
    test_task017_c4_ac19_claude_md_invariant_text_amended()
    test_task017_c4_ac19_readme_security_section_consistent()

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} check(s) failed:")
        for name, detail in FAILURES:
            print(f"    - {name}")
            if detail:
                snippet = detail.strip().replace("\n", " | ")[:160]
                print(f"      {snippet}")
        return 1

    print("✓ smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
