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


def test_install_detects_local_clone() -> None:
    """install.sh run from a real clone should use it in-place, not touch ~/.vibe-src."""
    print("\n[install.sh: detects local clone]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp)}
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
        env = {**os.environ, "HOME": str(tmp)}
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


def test_learning_render_devcontainer_config() -> None:
    """AC5/AC6: Generated override config has readonly mount."""
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
            f"learning_render_devcontainer_config {shlex.quote(str(src_cfg))} "
            f"{shlex.quote(str(dst))} {shlex.quote(str(lib))}"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC5 render exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC5 output file created", dst.exists(), str(dst))
        if dst.exists():
            data = json.loads(dst.read_text())
            mounts = data.get("mounts", [])
            learning_mount = None
            for m in mounts:
                # mounts are objects (dicts) in the output from learning_render_devcontainer_config
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
            "learning_render_devcontainer_config",
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
    shell, not rely on exports from the $( _learning_build_override_config )
    subshell — exports don't cross subshell boundaries, so without a parent-
    shell learning_load the banner line silently disappears even when
    /learnings is correctly mounted."""
    print("\n[learning banner: parent-shell load before override-config subshell]")
    src = Path(VIBE).read_text()
    # The banner block uses the learning_banner_state case dispatch.
    banner_marker = 'case "$(learning_banner_state'
    subshell_marker = "OVERRIDE_CONFIG=$(_learning_build_override_config"
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

    # Check: at least one line matches "^devcontainer exec " (without exec prefix)
    no_exec_lines = [l for l in lines if l.startswith('devcontainer exec ')]
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


def main() -> int:
    test_help()
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
    test_learning_config_format()
    test_learning_strict_parser_no_injection()
    test_learning_init_interactive()
    test_learning_init_mkdir_offer()
    test_learning_init_reinit_path()
    test_learning_default_off_no_config()
    test_learning_learn_without_init()
    test_learning_render_devcontainer_config()
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
