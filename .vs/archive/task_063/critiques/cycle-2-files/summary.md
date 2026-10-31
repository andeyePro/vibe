Added AC12-AC20 tests (7 new test functions, checks_56 now 1,071 lines, registered in runner.py); updated cycle-1 checks for quoted plist strings, new reinstall order and the Automation wording.
checks_56 + checks_48 + checks_49: 0 failures; code-check.py exit 0; full smoke-test.py exit 0.
Note: AC16 tests use column-0 `bindings:` lines (what the implementation parses); a real dump with only tab-indented claim bindings would yield `(unknown)`.
