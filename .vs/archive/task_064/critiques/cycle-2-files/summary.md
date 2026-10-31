checks_50 (284), checks_52 (181), checks_55 (176, new, AC19-AC30): all exit 0; checks_28/29/48/49 exit 0; code-check exit 0.
checks_47 and smoke-test exit 1, each on one cause: checks_47 AC10 (3 checks) pins an uncommitted-diff shape of checks_29, which the chair-authorised AC19 edit to checks_29 breaks.
Test edits: checks_50 core() ignores pendingDirect; checks_52 AC16 recomputes job digest, AC14 git-diff check removed; checks_29/49 launch-ref refusals turned into acceptances.
