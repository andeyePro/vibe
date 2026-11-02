Tester cycle 1: about 560 new checks (checks_58/59, fake server smoke/taskandi_v23_server.mjs); 5 fail, all one defect: AC1 on the v2.2 path.
Defect: a v2.2 answer does not set state.lastContract, and a v2.2 capabilities answer carrying limits or id_pattern is accepted instead of refused (pre-dispatch, exit 1).
Exit codes: checks_58 1, checks_59 0, checks_28/29/47/50/52/53/54/55/57 0, code-check 0, smoke-test 1 (only those 5); AC15 holds. No AC untestable.
