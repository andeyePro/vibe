Cycle 3 Tester: added test_v23_ac29_non_proof_answers to checks_60 (non-proof answers on a resend for jobs and pending complete/release, all ten proof codes, the full lost-response/revoked/fresh-descriptor sequence, AC30 message).
Changed only the AC19 loops that used connection_unavailable/connection_revoked as try-later proof; the rejected-code list now covers all seven proof codes.
Gates all exit 0: checks_58/59/60, 28/29/47/50/52/53/54/55/57, code-check, smoke-test; test_status set to passing.
