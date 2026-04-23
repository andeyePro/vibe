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

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
VIBE = REPO / "vibe"
INSTALL = REPO / "install.sh"
WRITE_ENV_HINT = REPO / "devcontainer" / "write-env-hint.sh"

FAILURES: list[tuple[str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  {'✓' if cond else '✗'} {name}")
    if not cond:
        FAILURES.append((name, detail))
    return cond


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env if env is not None else os.environ.copy(),
        cwd=cwd,
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


# ── Runner ────────────────────────────────────────────────────────────────────


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
