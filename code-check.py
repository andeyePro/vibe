#!/usr/bin/env python3
"""Static analysis for vibe shell scripts.

Runs shellcheck over every shell script in the repo. Exits non-zero if any
file has warnings or errors so CI and local pre-commit can both call this.

Usage:
    python3 code-check.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def scripts() -> list[Path]:
    candidates = [REPO / "vibe", REPO / "install.sh"]
    candidates += sorted((REPO / "devcontainer").glob("*.sh"))
    return [p for p in candidates if p.exists()]


def main() -> int:
    if shutil.which("shellcheck") is None:
        print("ERROR: shellcheck not installed.")
        print("  macOS:  brew install shellcheck")
        print("  Linux:  sudo apt-get install shellcheck")
        return 2

    targets = scripts()
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
