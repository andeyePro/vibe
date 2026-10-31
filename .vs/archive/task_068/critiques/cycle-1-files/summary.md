smoke/checks_65_codex_allow_hardening.py (425 lines, registered in runner): AC1-AC5, AC7 plus helper reason codes; 0 failures vs Generator's vibe. checks_17/48/49/56 and code-check.py exit 0.
Full `python3 smoke-test.py` exit 1: only 3 failures, all brain2 byte-identity checks (taskandi-v23 AC16 x2, taskandi-propose AC14), files untouched by task_068 (environmental drift in /brain2).
task_068 test_status set to "failing" strictly because AC8 requires full smoke exit 0; Evaluator should judge whether the 3 brain2 failures are pre-existing.
