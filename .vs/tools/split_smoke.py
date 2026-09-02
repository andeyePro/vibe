#!/usr/bin/env python3
"""One-shot splitter: smoke-test.py (single file) -> smoke/ package.

Re-runnable from the single-file source. Splits the ~14.5k line
smoke-test.py into:

  smoke/__init__.py                empty
  smoke/_core.py                   every top-level import, assignment,
                                    non-test def, and the stray top-level
                                    if/for, in original source order, plus
                                    a generated __all__ (computed by
                                    executing the module and diffing its
                                    namespace, so underscore names are
                                    re-exported by `import *` too)
  smoke/checks_NN_<theme>.py       contiguous runs of test_* functions,
                                    byte-identical slices (by ast lineno /
                                    end_lineno), each carrying its
                                    preceding comment/blank lines
  smoke/runner.py                  main() verbatim, plus the imports it
                                    needs to see every test_* name and the
                                    shared FAILURES list
  smoke-test.py                    new thin entrypoint (<=30 lines)

Usage: python3 .vs/tools/split_smoke.py [source_file] [dest_dir]
Defaults: source_file=smoke-test.py, dest_dir=. (repo root, i.e. writes
./smoke/ and overwrites ./smoke-test.py in place).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Number of test_* functions (in original source order) that go into each
# smoke/checks_NN_<theme>.py file. Sums to 487 test functions. Chosen by a
# greedy bin-pack (budget ~1200 lines/file) over the original file's test
# function slices, so each resulting file lands well under the 1,500-line
# review budget. The theme names are derived from the dominant "# ── ... ──"
# section header(s) each group spans.
GROUPS: list[tuple[str, int]] = [
    ("01_launcher_basics_and_codecheck", 66),
    ("02_image_drift_and_learning", 52),
    ("03_vibecopy_and_watcher", 28),
    ("04_hooks_guards", 42),
    ("05_numbering_hook", 35),
    ("06_autoresume_and_sharedrepos", 38),
    ("07_sharedrepos_cycles", 49),
    ("08_credential_and_contentscan", 47),
    ("09_openproject_and_scanner", 31),
    ("10_pathwarn_and_hunkdiff", 48),
    ("11_patrotation_and_firewall", 51),
]


def slice_lines(lines: list[str], start: int, end: int) -> str:
    """1-indexed, inclusive-inclusive, ast-style (end_lineno inclusive)."""
    return "".join(lines[start - 1 : end])


def main() -> int:
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("smoke-test.py")
    dest_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    src = src_path.read_text()
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src, filename=str(src_path))

    core_slices: list[tuple[int, int]] = []
    main_slice: tuple[int, int] | None = None
    test_slices: list[tuple[int, int, str]] = []

    prev_end = 0
    for node in tree.body:
        start = prev_end + 1
        end = node.end_lineno
        prev_end = end
        is_test_def = isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        is_main_def = isinstance(node, ast.FunctionDef) and node.name == "main"
        is_trailing_guard = isinstance(node, ast.If) and node is tree.body[-1]
        if is_test_def:
            test_slices.append((start, end, node.name))
        elif is_main_def:
            main_slice = (start, end)
        elif is_trailing_guard:
            # Reconstructed by hand in the new entrypoint; original text is
            # `if __name__ == "__main__": sys.exit(main())` verbatim, so
            # nothing is lost. Any blank lines just before it are dropped.
            pass
        else:
            core_slices.append((start, end))

    if sum(n for _, n in GROUPS) != len(test_slices):
        raise SystemExit(
            f"GROUPS accounts for {sum(n for _, n in GROUPS)} tests, "
            f"source has {len(test_slices)} test_* functions — update GROUPS."
        )
    if main_slice is None:
        raise SystemExit("no top-level `def main()` found")

    smoke_dir = dest_dir / "smoke"
    smoke_dir.mkdir(exist_ok=True)

    # ---- smoke/__init__.py ----
    (smoke_dir / "__init__.py").write_text("")

    # ---- smoke/_core.py ----
    core_body = "".join(slice_lines(lines, s, e) for s, e in core_slices)
    # REPO must resolve to the repo root. In the original single file, REPO
    # was `Path(__file__).resolve().parent` because smoke-test.py itself sat
    # at the repo root. _core.py now sits one level down, in smoke/, so this
    # is the one line that must change to keep every derived path constant
    # (VIBE, INSTALL, ...) correct — everything else in _core.py is an
    # untouched, reordered-nothing concatenation of the original slices.
    old_repo_line = "REPO = Path(__file__).resolve().parent\n"
    new_repo_line = "REPO = Path(__file__).resolve().parent.parent\n"
    if old_repo_line not in core_body:
        raise SystemExit("expected REPO assignment line not found verbatim in core body")
    core_body = core_body.replace(old_repo_line, new_repo_line, 1)

    core_path = smoke_dir / "_core.py"
    core_path.write_text(core_body)

    # Compute __all__ by executing the module in isolation and diffing the
    # namespace against a pristine `exec` baseline — this reliably captures
    # every bound name (including underscore names and for-loop leaked
    # names) without hand-enumerating assignment targets.
    baseline_ns: dict = {"__name__": "smoke._core", "__file__": str(core_path.resolve())}
    exec(compile("", "<baseline>", "exec"), baseline_ns)
    full_ns = dict(baseline_ns)
    exec(compile(core_body, str(core_path), "exec"), full_ns)
    new_names = sorted(k for k in full_ns if k not in baseline_ns and k != "__builtins__")
    all_block = (
        "\n\n__all__ = [\n"
        + "".join(f"    {n!r},\n" for n in new_names)
        + "]\n"
    )
    core_path.write_text(core_body.rstrip("\n") + "\n" + all_block)

    # ---- smoke/checks_NN_<theme>.py ----
    idx = 0
    group_modules: list[str] = []
    for theme, count in GROUPS:
        group = test_slices[idx : idx + count]
        idx += count
        body = "".join(slice_lines(lines, s, e) for s, e, _ in group)
        modname = f"checks_{theme}"
        group_modules.append(modname)
        header = "from smoke._core import *  # noqa: F401,F403\n\n\n"
        (smoke_dir / f"{modname}.py").write_text(header + body)
    assert idx == len(test_slices)

    # ---- smoke/runner.py ----
    main_body = slice_lines(lines, *main_slice)
    runner_imports = "from smoke._core import *\n" + "".join(
        f"from smoke.{m} import *\n" for m in group_modules
    )
    (smoke_dir / "runner.py").write_text(runner_imports + "\n\n" + main_body)

    # ---- smoke-test.py entrypoint ----
    entry_imports = "".join(f"from smoke.{m} import *\n" for m in group_modules)
    entry = (
        "#!/usr/bin/env python3\n"
        '"""Entrypoint for the vibe smoke suite (split across smoke/).\n\n'
        "See smoke/_core.py, smoke/checks_*.py and smoke/runner.py for the\n"
        "actual content — this file only wires them together so\n"
        "`python3 smoke-test.py` and importlib.util.spec_from_file_location\n"
        'loads of it keep working unchanged."""\n'
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n\n"
        "from smoke._core import *\n"
        + entry_imports
        + "from smoke.runner import main\n\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    (dest_dir / "smoke-test.py").write_text(entry)

    print(f"wrote smoke/_core.py ({core_body.count(chr(10))} lines + __all__)")
    print(f"wrote {len(group_modules)} smoke/checks_*.py files")
    print("wrote smoke/runner.py")
    print("wrote smoke-test.py entrypoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
