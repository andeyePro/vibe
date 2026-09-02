#!/usr/bin/env python3
"""Entrypoint for the vibe smoke suite (split across smoke/).

See smoke/_core.py, smoke/checks_*.py and smoke/runner.py for the
actual content — this file only wires them together so
`python3 smoke-test.py` and importlib.util.spec_from_file_location
loads of it keep working unchanged."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke._core import *
from smoke.checks_01_launcher_basics_and_codecheck import *
from smoke.checks_02_image_drift_and_learning import *
from smoke.checks_03_vibecopy_and_watcher import *
from smoke.checks_04_hooks_guards import *
from smoke.checks_05_numbering_hook import *
from smoke.checks_06_autoresume_and_sharedrepos import *
from smoke.checks_07_sharedrepos_cycles import *
from smoke.checks_08_credential_and_contentscan import *
from smoke.checks_09_openproject_and_scanner import *
from smoke.checks_10_pathwarn_and_hunkdiff import *
from smoke.checks_11_patrotation_and_firewall import *
from smoke.runner import main

if __name__ == "__main__":
    sys.exit(main())
