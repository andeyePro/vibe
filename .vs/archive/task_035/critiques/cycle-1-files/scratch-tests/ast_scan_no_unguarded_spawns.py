#!/usr/bin/env python3
"""Scratch proof (task_035 generator pass): AST scan across smoke/*.py proving
zero unguarded subprocess spawns remain. Not a permanent test — the Tester
writes the real AC3 lint (test_harness_spawns_never_inherit_stdin). This is
scaffolding evidence the sweep in deliverable 2 actually closed every site,
run with stdin=subprocess.DEVNULL itself per the Generator's own rule.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
assert REPO.name == "workspace" or (REPO / "smoke").is_dir(), REPO

SPAWN_NAMES = {"run", "Popen", "check_output", "call"}


def find_unguarded(path: Path) -> list[tuple[int, str]]:
    src = path.read_text()
    tree = ast.parse(src, filename=str(path))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in SPAWN_NAMES):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        kwnames = {kw.arg for kw in node.keywords if kw.arg}
        has_input = "input" in kwnames or "input_bytes" in kwnames
        has_stdin = "stdin" in kwnames
        if not (has_input or has_stdin):
            bad.append((node.lineno, f"subprocess.{func.attr}"))
    return bad


def main() -> int:
    files = sorted((REPO / "smoke").glob("*.py"))
    assert files, "expected smoke/*.py to exist"
    total_spawns = 0
    total_bad = 0
    for f in files:
        src = f.read_text()
        tree = ast.parse(src, filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr in SPAWN_NAMES
                        and isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                    total_spawns += 1
        bad = find_unguarded(f)
        if bad:
            total_bad += len(bad)
            for lineno, name in bad:
                print(f"UNGUARDED {f.relative_to(REPO)}:{lineno} {name}")
    print(f"total subprocess.* spawns scanned: {total_spawns}")
    print(f"total unguarded: {total_bad}")
    ok = total_bad == 0 and total_spawns >= 40
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    # Demonstrate our own subprocess-spawn hygiene while at it: a trivial
    # child run with stdin explicitly closed, matching the rule under test.
    subprocess.run(["true"], stdin=subprocess.DEVNULL, check=False)
    sys.exit(main())
