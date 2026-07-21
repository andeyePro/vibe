#!/usr/bin/env python3
"""Scratch TDD harness for task_025 — is_shell_script() and scripts() env seam.

Not part of the shipped test suite (lives under .vs/cycle-1/, gitignored).
Run: python3 /workspace/.vs/cycle-1/scratch-tests/scratch_check.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/workspace")
CODE_CHECK_PATH = REPO / "code-check.py"

spec = importlib.util.spec_from_file_location("code_check_mod", CODE_CHECK_PATH)
code_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code_check)

failures = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# ── AC2: is_shell_script predicate ──────────────────────────────────────────

def _mk(tmp: Path, name: str, content: bytes) -> Path:
    p = tmp / name
    p.write_bytes(content)
    return p


def test_is_shell_script() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        f = _mk(tmp, "noext", b"#!/usr/bin/env bash\necho hi\n")
        check("bash-no-ext -> True", code_check.is_shell_script(f) is True)

        f = _mk(tmp, "a.sh", b"#!/bin/sh\necho hi\n")
        check("#!/bin/sh -> True", code_check.is_shell_script(f) is True)

        f = _mk(tmp, "b.sh", b"#!/bin/bash\necho hi\n")
        check("#!/bin/bash -> True", code_check.is_shell_script(f) is True)

        f = _mk(tmp, "c.sh", b"#!/usr/bin/env zsh\necho hi\n")
        check("#!/usr/bin/env zsh -> True", code_check.is_shell_script(f) is True)

        f = _mk(tmp, "d.sh", b"#!/usr/bin/env fish\necho hi\n")
        check("#!/usr/bin/env fish -> False (substring false-positive guard)",
              code_check.is_shell_script(f) is False)

        f = _mk(tmp, "e.py", b"#!/usr/bin/python3\nprint('hi')\n")
        check("#!/usr/bin/python3 -> False", code_check.is_shell_script(f) is False)

        f = _mk(tmp, "f.txt", b"not a shebang\nsecond line\n")
        check("no #! first line -> False", code_check.is_shell_script(f) is False)

        f = _mk(tmp, "empty", b"")
        check("empty file -> False", code_check.is_shell_script(f) is False)

        f = _mk(tmp, "binary", bytes([0xFF, 0xFE, 0x00, 0x01, 0x02, 0x80, 0x81]))
        try:
            result = code_check.is_shell_script(f)
            check("binary first line -> False, no raise", result is False)
        except Exception as exc:  # noqa: BLE001
            check("binary first line -> False, no raise", False, f"raised {exc!r}")

        f = _mk(tmp, "g.sh", b"#!/usr/bin/env -S bash -x\necho hi\n")
        check("#!/usr/bin/env -S bash -x -> True (skips -S option)",
              code_check.is_shell_script(f) is True)

        f = _mk(tmp, "h.sh", b"#!/usr/bin/env\necho hi\n")
        check("#!/usr/bin/env alone -> False", code_check.is_shell_script(f) is False)

        f = _mk(tmp, "i.sh", b"#!\necho hi\n")
        check("bare #! -> False", code_check.is_shell_script(f) is False)

        f = _mk(tmp, "j.sh", b"#!   \necho hi\n")
        check("#!    (whitespace only) -> False", code_check.is_shell_script(f) is False)


# ── AC3/AC4: env seam exact-list + empty/unset fallthrough ─────────────────

def test_env_seam_exact_list() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        existing = tmp / "one.sh"
        existing.write_text("#!/bin/bash\necho hi\n")
        nonexistent = tmp / "does-not-exist.sh"

        override = os.pathsep.join([str(existing), str(nonexistent)])
        # Call scripts() directly in-process for the exact-list check (the
        # pinned contract's AC3 is about scripts()'s return value, not the
        # --json subprocess path — paths outside REPO legitimately can't
        # relative_to() in run_json_mode, which is out of scope here).
        prev = os.environ.get("CODE_CHECK_SCRIPTS")
        try:
            os.environ["CODE_CHECK_SCRIPTS"] = override
            result = code_check.scripts()
        finally:
            if prev is None:
                os.environ.pop("CODE_CHECK_SCRIPTS", None)
            else:
                os.environ["CODE_CHECK_SCRIPTS"] = prev
        check("env seam returns exactly 2 Path objects in order",
              result == [Path(str(existing)), Path(str(nonexistent))],
              str(result))
        check("env seam did not leak into os.environ after restore",
              os.environ.get("CODE_CHECK_SCRIPTS") == prev)


def test_env_seam_empty_unset_falls_through() -> None:
    prev = os.environ.get("CODE_CHECK_SCRIPTS")
    try:
        os.environ.pop("CODE_CHECK_SCRIPTS", None)
        result_unset = code_check.scripts()
        os.environ["CODE_CHECK_SCRIPTS"] = ""
        result_empty = code_check.scripts()
    finally:
        if prev is None:
            os.environ.pop("CODE_CHECK_SCRIPTS", None)
        else:
            os.environ["CODE_CHECK_SCRIPTS"] = prev

    check("unset env -> default set (non-empty, contains vibe)",
          any(p.name == "vibe" for p in result_unset), str(result_unset))
    check("empty-string env -> default set (non-empty, contains vibe)",
          any(p.name == "vibe" for p in result_empty), str(result_empty))
    check("unset and empty-string produce identical default set",
          result_unset == result_empty)


# ── AC1: git-hooks covered in default set ───────────────────────────────────

def test_default_set_includes_git_hooks() -> None:
    prev = os.environ.get("CODE_CHECK_SCRIPTS")
    try:
        os.environ.pop("CODE_CHECK_SCRIPTS", None)
        result = code_check.scripts()
    finally:
        if prev is None:
            os.environ.pop("CODE_CHECK_SCRIPTS", None)
        else:
            os.environ["CODE_CHECK_SCRIPTS"] = prev

    names = {p.name for p in result}
    for expected in ("vibe-content-scan.sh", "commit-msg", "pre-commit", "pre-push"):
        check(f"default set includes git-hooks/{expected}", expected in names, str(sorted(names)))

    # Ordering: git-hooks block should be a contiguous sorted run appended
    # after the hooks/*.sh block, sorted by full path.
    git_hooks_paths = [p for p in result if p.parent.name == "git-hooks"]
    check("git-hooks block sorted", git_hooks_paths == sorted(git_hooks_paths), str(git_hooks_paths))
    check("git-hooks block has exactly 4 entries", len(git_hooks_paths) == 4, str(git_hooks_paths))


if __name__ == "__main__":
    test_is_shell_script()
    test_env_seam_exact_list()
    test_env_seam_empty_unset_falls_through()
    test_default_set_includes_git_hooks()

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        sys.exit(1)
    print("ALL SCRATCH CHECKS PASSED")
    sys.exit(0)
