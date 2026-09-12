# Fix the 32 confirmed findings from the max-effort review of `vsss/codex-taskandi-environment`

Review run 2026-09-12 (`/code-review max main..vsss/codex-taskandi-environment`).
Every finding below was independently verified against the checked-out branch, most with a
live reproduction. Verifier repro scripts and diff slices are in this session's scratchpad:
`/tmp/claude-1000/-workspace/1417810d-964b-4a96-865c-2889fa117334/scratchpad/`
(`cands/*.json` = raw candidates, `verdicts/*.txt` = verdict index, `repro*`, `a1-8/`, `a5-6/`, `a57/`).

## Constraints

- Subscription models only (haiku/sonnet/opus). **Never dispatch Fable** for any rung.
- Work on the current branch `vsss/codex-taskandi-environment`. Do not push. Do not touch `main`.
- Keep vibe's invariants (CLAUDE.md): bypassPermissions safety, single-repo PAT, no credit spend by default.
- `python3 code-check.py` must stay clean. `python3 smoke-test.py < /dev/null` must pass in-container.
- Every fix gets a regression test in the matching `smoke/checks_NN_*.py` (≤1,500 lines per file; split if needed).
- Group commits by subsystem (launcher / host-onboarding / supervisor / mac-build / taskandi / smoke), each with a CHANGELOG.md entry in the same commit. Commit trailer per `~/.claude/CLAUDE.md`.
- macOS bash 3.2 rules apply to `vibe` (no `declare -A`, no `${x,,}`, no `mapfile`; `${arr[@]+"${arr[@]}"}` for empty arrays under `set -u`).
- Fix the class, not the instance, where the finding names siblings (e.g. every `communicate(timeout=)` in checks_27, every main-module guard).

## A. Launch-breakers (fix first)

1. `devcontainer/host-onboarding.py:124` — `directory()` rejects any user-owned ancestor with group/other write bits; called on every interactive launch via take-agent under `|| exit 1`. umask-002 hosts (0775 `~/Projects`) cannot launch. Only refuse when the ancestor is writable by a *different* non-root uid, or warn and continue.
2. `devcontainer/host-onboarding.py:181` — `storage()` lists `VIBE_PROJECTS_DIR` as a "container mount" and refuses `~/.vibe` under it. The launcher never mounts PROJECTS_DIR (see `_build_override_config`, vibe:3276-3399). Remove it from the mount list.
3. `vibe:343` — `create_github_repo` returns non-zero when gh is missing, sign-in fails, or the user answers `n` (bare `return` carries status 1); sole caller vibe:4613 is a bare statement under `set -e`. Declining GitHub must still launch. Make the function return 0 on decline and have the caller tolerate failure.
4. `vibe:5432` — `vibe_switch_after_exit || exit 1` runs before the /vsss auto-resume loop; a queued agent switch during an active `.vss/auto-resume` marker makes take-agent raise, killing the launcher so the run is never auto-resumed. A refused switch must warn and fall through to the resume loop.
5. `vibe:4261` — general form of 1-4: every host-onboarding call in the interactive path is `|| return 1` → `|| exit 1`. Any ValueError becomes a silent launch abort. Decide per call which failures are fatal; the rest degrade with a printed warning.
6. `devcontainer/Dockerfile:195` — npm-global re-chowned root:root with no `DISABLE_AUTOUPDATER=1` (or `autoUpdates=false`) anywhere, so Claude Code's self-updater hits EACCES every session and suggests `claude migrate-installer`. Set the env in the Dockerfile/devcontainer.json and assert it in smoke.

## B. Launcher (`vibe`)

7. `vibe:1721` — `codex_allowed` greps the registry for raw `$WORKSPACE`; writers record `pwd -P` / realpath; the `vibe <name>` form (vibe:4489) never canonicalises. Canonicalise once before the lookup.
8. `vibe:4543` — interactive `--codex-run/--codex-resume` is handed to `vibe_onboard_agent` as an explicit `codex` flag, which cancels queued requests and persists `codex` as the remembered runtime. A one-off supervised run must not change folder memory.
9. `vibe:4456` — Fable consent gate and VIBE_MODEL default are skipped only on `CODEX_ACTION`; LEAD_AGENT resolves later (4520). Codex-led interactive launches get the Fable prompt and silently drop `--continue/--resume/--model`. Resolve LEAD_AGENT before the gate; refuse Claude-only flags for any Codex lead.
10. `vibe:5308` — `--codex-run` and `--codex-resume` build identical supervisor argv; `--new-run` cannot be passed (`Unknown flag`). Either thread `--new-run` through or make `--codex-run` imply it when the existing state is complete/mismatched.
11. `vibe:4660` — final Codex gate calls `_codex_desired_source … 2>/dev/null` and prints one fixed message. Surface the specific `⚠` reason (committed marker, unrecorded marker, VIBE_CODEX_PATH=off).
12. `vibe:4334` — `vibe_onboard_codex` short-circuits on `have_cli` before checking login, so a valid `~/.codex/auth.json` with no host CLI forces an npm install or aborts. Check the auth file directly when the CLI is absent; the container ships its own codex.

## C. Supervisor (`devcontainer/codex-supervisor.mjs`, `codex-panel.mjs`)

13. `codex-supervisor.mjs:1274` — `error.code ?? EXIT_FAIL` passes string fs codes to `process.exit`, crashing with ERR_INVALID_ARG_TYPE. Only use numeric SupervisorError codes; map everything else to EXIT_FAIL and print the message.
14. `codex-supervisor.mjs:1000` — a known `resetsAt` already in the past yields a 0 s wait and never re-reads rate limits, burning `max-quota-waits` in 0.3 s. Treat past/zero waits as blind: re-read, then back off with a floor (e.g. 30 s).
15. `codex-supervisor.mjs:1187` — SIGHUP not handled; supervisor dies without persisting or releasing the lock. Add SIGHUP to the cooperative-stop set.
16. `codex-supervisor.mjs:332` — `bindingResetsAt` only counts `usedPercent >= 100` as exhausted; 99 falls to the later (weekly) window and hits the max-wall-seconds ceiling. When nothing is at 100, prefer the window that resets soonest, or treat ≥ a high threshold as exhausted.
17. `codex-supervisor.mjs:605` — cooperative stop mid-turn throws before draining to `turn/completed`, so the printed "resume with the same run arguments" is refused. Drain (bounded) after `turn/interrupt`, or print the reconcile instruction instead.
18. `codex-supervisor.mjs:1061` — `turn/completed{status:'interrupted'}` throws without `confirmTurnBoundary()`, unlike completed/failed. Confirm the boundary first; fix the `recoveryReason` mislabel.
19. `codex-panel.mjs:421` — `nonces.map(startReviewer)` sits outside the try/finally; a setup throw at reviewer k leaks reviewers 1..k-1 (metered `codex exec`) and their temp dirs. Start inside the try and kill/clean whatever started.

## D. Mac build bridge (`devcontainer/mac-build.mjs`, `mac-build-host.mjs`)

20. `mac-build.mjs:277` (and `mac-build-host.mjs:392`) — main-module guard compares percent-encoded `import.meta.url` with raw argv; paths with spaces exit 0 silently. Use `realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))` as taskandi-client.mjs:467 already does.
21. `mac-build-host.mjs:304` — lock-busy is committed as a `terminal` receipt, so the jobId can never execute after the lock clears. Do not persist busy as terminal (or persist as a non-terminal state the replay path treats as never-accepted).
22. `mac-build.mjs:181` — non-zero ssh exit discards the host's JSON failure body on stdout. Parse stdout when present and surface `error`/`code`; fall back to stderr text.
23. `mac-build.mjs:166` — raw Buffer chunks concatenated into a string corrupt split UTF-8. Collect Buffers and decode once (or `setEncoding('utf8')`) while keeping the byte-length cap correct.

## E. Task&I client (`devcontainer/taskandi-client.mjs`, `taskandi-usage.mjs`)

24. `taskandi-client.mjs:386` — `sent = true` precedes `mcp.call`, so every failure is 'uncertain', the real error is discarded, and the pre-dispatch branch is dead. Set `sent` only once the request has actually been handed to the transport; keep the original error message in `lastError`.
25. `taskandi-usage.mjs:19` — one regressing cumulative count (a compaction) throws and discards every delta; the session is then permanently un-importable. Treat a regression as a new baseline (or skip that line) and record the event, instead of aborting.
26. `taskandi-client.mjs:458` — `Number('')` makes `--cost-estimate` 0. Require a non-empty decimal string matching `/^\d+(\.\d+)?$/`; reject otherwise.

## F. Smoke suite

27. `smoke/runner.py:57` (checks_19/21/27/30) — 55 supervisor tests exec the real supervisor, which throws 'requires Linux' off-Linux; no platform skip, and at least one then raises uncaught (checks_19:816). Skip the class on non-Linux with a printed notice, and make the state-reading tests fail via `check()` rather than subscript.
28. `smoke/checks_29_taskandi_binding_usage.py:145` — the `absent` probe inherits the real env and exits 9 when `VIBE_TASK_REF` is set; bare assert aborts the suite. Build the env with `_isolate_extras_env`-style sanitising and report via `check()`.
29. `smoke/checks_28_taskandi_client.py:155`, `smoke/checks_33_host_onboarding.py:66,124,250` — bare `assert` / `next(glob())` raise instead of `check()`. Convert.
30. `smoke/checks_27_supervisor_control.py:99` (also :55, :140) — real-clock 5000 s quota wait with unguarded `communicate(timeout=15)`. Use `--now-source` and the try/except-kill pattern from checks_19:781.
31. `smoke/checks_22_codex_agent.py:477` — normaliser targets the pre-23ae4c4 spelling; HEAD:vibe equals the working tree, so the check compares the file to itself. Compare against a documented golden fragment or drop the test and register the sha in `HISTORICAL_PINS_ALLOWED` only if a pin is truly needed.
32. `smoke/checks_13_spec_first.py:864,880` and `smoke/checks_17_delegation.py:462` — assertions nested under `if <regex match>:` vanish silently; DOTALL missing on the 'explicitly works' regex; banner-block scanner keyed on exact spelling. Add `check(match is not None)` guards and fix the regexes.

## Not in scope

- Refuted by verification: mac-build.mjs:190 identity check (masked by item 22); vibe-delegate.mjs:67 usage-loss claim (usage is preserved; existing test covers it).
- Dropped as low/plausible: taskandi-client usage string omits the `usage` subcommand (one-line fix, do it if touching the file); `_codex_dir_mode_warning` unguarded `stat` (vibe:1827) — add the `|| mode=""` guard if touching the function.
- 32 unverified quality-only candidates (duplication, altitude, efficiency) in scratchpad `cands/{ALTITUDE,EFFICIENCY,REUSE,SIMPLIFY}.json`. Advisory; not part of this task.

## Acceptance

- Each numbered item has a failing-then-passing regression test.
- `python3 code-check.py` clean; full smoke suite green in-container.
- CHANGELOG.md entries per commit; TODO.md untouched except to close any entry these fixes resolve.
- No push.
