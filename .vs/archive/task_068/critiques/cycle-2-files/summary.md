checks_65 (now ~620 lines) adds AC9 (775 dir, no file), AC10 (dir/FIFO/socket under 10 s timeout, link dir), AC11 (stubbed unknown/empty/weird codes plus source-level shape), AC12 (mode text); focused run of checks_65/17/48/49/56 exit 0.
code-check.py exit 0; full `python3 smoke-test.py < /dev/null` exit 0 (run started before the AC11 source test was appended; that test was run separately: 0 failures).
task_068 test_status set to "passing".
