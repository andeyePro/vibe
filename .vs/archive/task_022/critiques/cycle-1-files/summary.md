# task_022 Tester summary — cycle 1

Total checks: 1610 (full `smoke-test.py` incl. 68 new task_022 checks across 12 new test functions) + `code-check.py` (15 files) — 1610 passed, 0 failed, exit 0 both. One-offs: AC1 real-history slice (12k lines) byte-identical old-vs-new (35/35 findings, old ~98.8s / new ~4.3s); AC4 `vibe audit --history` 21.9s real (<60s gate, baseline was >280s timeout).

Regressions: none — full pre-existing `smoke-test.py` suite and `code-check.py` both green against the modified scanner/vibe files.

AC coverage: AC1 one-off PASS, AC2 corpus (message/blob-stdin/staged/range + clean-block + allowlist) PASS, AC3 parity+attribution PASS, AC4 one-off PASS, AC5 (all modes + 3 malformed --messages-stdin shapes) PASS, AC6 override/opt-out PASS, AC7 static shape checks (a+b) PASS. No gaps identified.
