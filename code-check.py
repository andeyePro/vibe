#!/usr/bin/env python3
"""Static analysis for vibe shell scripts.

Runs shellcheck over every shell script in the repo. Exits non-zero if any
file has warnings or errors so CI and local pre-commit can both call this.

Usage:
    python3 code-check.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

KNOWN_SHELLS = {"sh", "bash", "dash", "ksh", "zsh", "ash"}


def is_shell_script(path: Path) -> bool:
    """True iff path's first line is a shebang resolving to a known shell.

    Defensive: any read failure (missing file, permission, non-UTF-8 bytes)
    or an empty/first-lineless file returns False, never raises.
    """
    try:
        with open(path, "r", errors="ignore") as f:
            first_line = f.readline()
    except (OSError, UnicodeError):
        return False

    if not first_line.startswith("#!"):
        return False

    tokens = first_line[2:].split()
    if not tokens:
        return False

    first = Path(tokens[0]).name
    if first != "env":
        interpreter = first
    else:
        interpreter = None
        for tok in tokens[1:]:
            if tok.startswith("-"):
                continue
            interpreter = Path(tok).name
            break
        if interpreter is None:
            return False

    return interpreter in KNOWN_SHELLS


def scripts() -> list[Path]:
    override = os.environ.get("CODE_CHECK_SCRIPTS")
    if override:
        return [Path(p) for p in override.split(os.pathsep)]

    candidates = [REPO / "vibe", REPO / "install.sh"]
    candidates += sorted((REPO / "devcontainer").glob("*.sh"))
    candidates += sorted((REPO / "devcontainer" / "hooks").glob("*.sh"))
    candidates += sorted(
        p
        for p in (REPO / "devcontainer" / "git-hooks").iterdir()
        if p.is_file() and is_shell_script(p)
    )
    return [p for p in candidates if p.exists()]


def get_shellcheck_version() -> str:
    result = subprocess.run(
        ["shellcheck", "--version"],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def run_json_mode(targets: list[Path]) -> int:
    version = get_shellcheck_version()
    files_checked: list[str] = []
    all_findings: list[dict] = []

    for script in targets:
        rel = str(script.relative_to(REPO).as_posix())
        files_checked.append(rel)
        result = subprocess.run(
            [
                "shellcheck",
                "--shell=bash",
                "--severity=warning",
                "-f",
                "json",
                str(script),
            ],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            raw_findings = json.loads(result.stdout)
            for item in raw_findings:
                all_findings.append(
                    {
                        "file": str(
                            Path(item["file"]).relative_to(REPO).as_posix()
                        ),
                        "line": item["line"],
                        "column": item["column"],
                        "level": item["level"],
                        "code": int(item["code"]),
                        "message": item["message"],
                    }
                )

    files_with_issues = len({f["file"] for f in all_findings})
    output = {
        "tool": "shellcheck",
        "shellcheck_version": version,
        "files_checked": files_checked,
        "findings": all_findings,
        "summary": {
            "files": len(files_checked),
            "files_with_issues": files_with_issues,
            "total_findings": len(all_findings),
        },
    }
    print(json.dumps(output))
    return 1 if all_findings else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run shellcheck over vibe shell scripts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="  --json  emit findings as machine-readable JSON instead of"
        " human output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as a single JSON object on stdout (machine-readable)",
    )
    args = parser.parse_args()

    if shutil.which("shellcheck") is None:
        if args.json:
            print(
                json.dumps(
                    {"error": "shellcheck-not-installed", "tool": "shellcheck"}
                )
            )
        else:
            print("ERROR: shellcheck not installed.")
            print("  macOS:  brew install shellcheck")
            print("  Linux:  sudo apt-get install shellcheck")
        return 2

    targets = scripts()

    if args.json:
        return run_json_mode(targets)

    failed: list[Path] = []
    for script in targets:
        rel = script.relative_to(REPO)
        print(f"→ shellcheck {rel}")
        result = subprocess.run(
            ["shellcheck", "--shell=bash", "--severity=warning", str(script)],
        )
        if result.returncode != 0:
            failed.append(script)

    print()
    if failed:
        print(f"✗ shellcheck found issues in {len(failed)} file(s):")
        for f in failed:
            print(f"    {f.relative_to(REPO)}")
        return 1

    print(f"✓ shellcheck clean across {len(targets)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
