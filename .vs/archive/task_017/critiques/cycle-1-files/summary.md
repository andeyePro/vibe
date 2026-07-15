# Cycle 1 test summary

Totals: 1189 checks, 0 failures (smoke-test.py) + shellcheck clean across 15 files (code-check.py).
Regressions: none — all pre-existing checks (including the haiku Tester's 57 task_017 checks) still green.
Key note: sonnet delta added 17 new test functions (39 checks) covering what the haiku Tester skipped as "not unit-testable" — the shared_repos_scan M/B/N/U state machine (incl. every pinned B reason), shared_repo_acked/ack exact-pair + idempotency + chmod 600, the security-review fixed-string-lookup regression for repos_registry_lookup/lookup_token/_vibe_repos_decl_remove, the _build_override_config two-bind (code+sidecar) JSON shape for acked vs unacked repos, shared_repos_manifest_lines, and the AC4 header's M/B/N/U case-arm text.
