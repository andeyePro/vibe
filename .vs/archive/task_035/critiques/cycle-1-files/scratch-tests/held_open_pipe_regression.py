#!/usr/bin/env python3
"""Scratch proof (task_035 generator pass): run one spawn-heavy smoke test
in a CHILD python process whose own stdin is a pipe that is never written
and never closed (the shape of a backgrounded/detached invocation with no
controlling TTY), and confirm it completes well under 60s.

Before the deliverable-1/2 fix, any bare subprocess.run/Popen call inside
the test tree that inherited stdin (the parent's own stdin fd, itself an
open never-written pipe here) would hang the moment a sourced script tried
to `read` from it. This is the regression check that proves the fix; the
Tester's real AC4 test (test_harness_survives_open_stdin) supersedes this.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
assert (REPO / "smoke").is_dir(), REPO

CHILD_SCRIPT = (
    "import sys; sys.path.insert(0, %r)\n"
    "from smoke import _core, checks_11_patrotation_and_firewall as c11\n"
    "c11.test_gh_meta_rate_limit_and_cache_fallback()\n"
    "print('CHILD_DONE failures=', len(_core.FAILURES))\n"
) % str(REPO)


def main() -> int:
    start = time.monotonic()
    # stdin=subprocess.PIPE with no write + no close: an open, empty,
    # never-terminated pipe -- exactly the "background run, no TTY"
    # shape. We deliberately do NOT pass input=/close stdin ourselves;
    # the child's own DEVNULL-guarded spawns must be what keeps it from
    # ever trying to read from this.
    proc = subprocess.Popen(
        [sys.executable, "-c", CHILD_SCRIPT],
        cwd=str(REPO),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        out, err = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        elapsed = time.monotonic() - start
        print(f"RESULT: FAIL (timed out after {elapsed:.1f}s)")
        print("stdout tail:", out[-500:] if out else "")
        print("stderr tail:", err[-500:] if err else "")
        return 1
    elapsed = time.monotonic() - start
    ok = proc.returncode == 0 and "CHILD_DONE failures= 0" in out and elapsed < 60
    print(f"elapsed={elapsed:.2f}s returncode={proc.returncode}")
    print("stdout tail:", out[-300:] if out else "")
    if err.strip():
        print("stderr tail:", err[-300:])
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
