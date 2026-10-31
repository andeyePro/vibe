Cycle 2 Tester: added smoke/checks_60_taskandi_v23_review.py (AC17-AC26, AC28; 73 checks) and per-connection replay plus a stop-listening control in the fake server.
Test-side fixes made per ruling: v2.2 capsAdd in the server, M2 now clears spentContract, AC26 controls freeze with drop-before-apply; Rev 4 margins replace the 30-day/60 s ones in checks_59.
Gates all exit 0: checks_58/59/60, 28/29/47/50/52/53/54/55/57, code-check, smoke-test. AC27 (single body builder) is white-box and untested.
