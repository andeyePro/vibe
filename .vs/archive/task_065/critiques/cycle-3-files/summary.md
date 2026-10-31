Added checks_57 (AC32-AC40), updated checks_52 (AC40 hash pins), checks_53 (--as parked, parked entry from state), checks_54 (new skip string, word cap 60 -> 75 since the exact string is 50 words + 21 pointer). Registered in runner.py.
Exit 0: checks_28/29/47/50/52/53/54/55 and code-check. Exit 1: checks_57 and the full smoke-test, with the same 2 failures.
Both are AC38 (legacy answer without `task`): client counts it for the job's task (`item.task ?? task`), the addendum says "same task and ask_id" so it must not; spec ambiguity, Generator or Chair decides. test_status=fail.
