# task_049 Tester summary (cycle 1)

- Added `smoke/checks_22_codex_agent.py` (16 test functions, 87 `check()` assertions) covering AC7: `_agent_resolve` precedence + file-rung failure modes, parser usage errors, real-source golden argv for `--agent codex` (granted/denied) and `--agent claude`/no-flag, `launch_codex_plain`/`launch_codex` source shape, `launch_claude` byte-identity vs HEAD, `codex-entry.sh` offline refusals/success, and the Dockerfile/liveness/.gitignore/README/MANUAL-TESTS/plan doc checks; wired into `smoke/runner.py`.
- `python3 code-check.py`: clean, shellcheck across 23 files including `devcontainer/codex-entry.sh`.
- `python3 smoke-test.py < /dev/null`: exit 0, **4245 checks passed, 0 failed** (full suite, including the 87 new ones).
- Not covered, with reason: the live Codex TUI trial (approval policy, denied `.codex/config.toml` write, `git push --force` denial) is explicitly out of scope — it needs a real Docker daemon and is Martin's MANUAL-TESTS Test 55 run; nothing in the offline suite has ever started a real Codex session, per the task's own framing.
