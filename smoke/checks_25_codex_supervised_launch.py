"""Supervised launch argument and guard-boundary regression tests.

Also covers the review-fixes-2026-09-12 wave-2 launcher items (Tester brief:
scratchpad/sdd/brief-launcher-tests.md), items 3, 4, 5, 7, 8, 9, 10, 11, 12.
Every test below pins the CURRENT vibe source/behaviour only (never a saved
"vibe.orig" snapshot — that file is a session-scratch artifact used only to
hand-verify fail-before/pass-after during development, not something a
committed test should depend on). Each test targets code that is either
brand new (so it fails with "command not found" / AssertionError against the
pre-fix source) or a changed literal/condition (so a revert of the fix flips
the assertion) — see the tester's report for the literal before/after runs
against the saved vibe.orig copy.
"""
from smoke._core import *
from smoke._core import _source_vibe_call
from smoke.checks_22_codex_agent import (
    _entry_fixture, _entry_liveness_stub, CODEX_ENTRY,
    _extract_func, _extract_lines, _codex_grant_fixture,
    _agent_devcontainer_stub, _agent_calls,
)
from smoke.checks_17_delegation import _codex_git_ws, _codex_rc_call


def test_codex_supervised_parser():
    for flag, action in [("--codex-run", "run"), ("--codex-resume", "resume")]:
        r = _source_vibe_call({}, f'parse_vibe_args {flag} "brief with spaces.md"; printf "%s|%s" "$CODEX_ACTION" "$CODEX_PROMPT_ARG"')
        check(f"[supervised] {flag} preserves a spaced prompt path", r.returncode == 0 and r.stdout == f"{action}|brief with spaces.md", r.stdout + r.stderr)
    for args in ["--codex-run", "--codex-resume --help", "--codex-run a --codex-resume b"]:
        r = _source_vibe_call({}, f"parse_vibe_args {args}")
        check(f"[supervised] refuses malformed flags {args}", r.returncode != 0, r.stdout + r.stderr)


def test_codex_supervised_entry_requires_gate():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bins, login, codex, codex_log = _entry_fixture(tmp)
        entry = bins / "codex-entry"
        entry.write_text(CODEX_ENTRY.read_text())
        entry.chmod(0o755)
        supervisor = bins / "codex-supervisor"
        supervisor_log = tmp / "supervisor-argv.json"
        supervisor.write_text(f"#!{sys.executable}\nimport json,sys\nopen({str(supervisor_log)!r},'w').write(json.dumps(sys.argv[1:]))\n")
        supervisor.chmod(0o755)
        argv = ["bash", str(entry), "--root", str(root), "--bin", str(bins), "--login-dir", str(login), "--codex", str(codex), "--supervise", "--", "run", "--cwd", "/workspace", "--prompt-file", "/workspace/brief with spaces.md"]
        _entry_liveness_stub(bins, False, tmp / "gate.log")
        r = run(argv)
        check("[supervised] failed gate starts neither supervisor nor vendor", r.returncode != 0 and not supervisor_log.exists() and not codex_log.exists(), r.stdout + r.stderr)
        _entry_liveness_stub(bins, True, tmp / "gate.log")
        r = run(argv)
        check("[supervised] successful gate hands argv to supervisor exactly", r.returncode == 0 and json.loads(supervisor_log.read_text()) == argv[argv.index("--") + 1:] and not codex_log.exists(), r.stdout + r.stderr)
        supervisor_log.unlink()
        supervisor.chmod(0o644)
        r = run(argv)
        check("[supervised] missing execute permission refuses before handoff", r.returncode != 0 and not supervisor_log.exists(), r.stdout + r.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Shared fixture helpers
# ═══════════════════════════════════════════════════════════════════════════

def _path_without(tmp: Path, exclude: set) -> str:
    """Build a bin dir holding a symlink to every executable currently on
    PATH except the names in `exclude` (first match per name wins, PATH
    order preserved) — a surgical "PATH minus one or two tools" fixture, so
    a test can hide `gh`/`codex`/`npm` without hand-curating (and likely
    under-provisioning) a whole replacement toolset."""
    d = tmp / ("path-without-" + "-".join(sorted(exclude)))
    d.mkdir(parents=True, exist_ok=True)
    seen = set()
    for pdir in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(pdir)
        if not p.is_dir():
            continue
        try:
            entries = list(p.iterdir())
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name in exclude or name in seen:
                continue
            try:
                if not os.access(entry, os.X_OK):
                    continue
                (d / name).symlink_to(entry)
            except OSError:
                continue
            seen.add(name)
    return str(d)


# ═══════════════════════════════════════════════════════════════════════════
# Item 3: create_github_repo returns 0 on every decline path
# ═══════════════════════════════════════════════════════════════════════════

def test_create_github_repo_decline_paths_all_return_zero():
    print("\n[supervised] item 3: create_github_repo returns 0 on every decline path")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        ws = tmp / "ws"; ws.mkdir()
        base_env = {"HOME": str(home), "WORKSPACE": str(ws)}

        # (a)/(b) explicit "no" / "never" answers to the initial prompt.
        for answer in ("no", "never"):
            call = f"if create_github_repo <<< {shlex.quote(answer)}; then echo RC=0; else echo RC=$?; fi"
            r = _source_vibe_call(base_env, call)
            check(f"[supervised] create_github_repo({answer!r}) returns 0",
                  "RC=0" in r.stdout, r.stdout + "|" + r.stderr)

        # (c) `gh` missing entirely: answering "y" to the first prompt must
        # still return 0 once `command -v gh` fails.
        no_gh_path = _path_without(tmp, {"gh"})
        call = "if create_github_repo <<< 'y'; then echo RC=0; else echo RC=$?; fi"
        r = _source_vibe_call({**base_env, "PATH": no_gh_path}, call)
        check("[supervised] create_github_repo returns 0 when gh is missing",
              "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
        check("[supervised] create_github_repo still tells the user to install gh",
              "Install GitHub CLI" in r.stdout, r.stdout)

        # (d) gh present but the user declines the sign-in prompt. Requires
        # _vibe_interactive() to read true (real stdin here is not a tty), so
        # it is redefined post-source the same way checks_33's fixtures do.
        gh_bin = tmp / "gh-bin"; gh_bin.mkdir()
        gh_stub = gh_bin / "gh"
        gh_stub.write_text("#!/bin/bash\ncase \"$1 $2\" in\n  'auth status') exit 1 ;;\nesac\nexit 0\n")
        gh_stub.chmod(0o755)
        call = (
            "_vibe_interactive() { return 0; }\n"
            "if create_github_repo <<< $'y\\nn'; then echo RC=0; else echo RC=$?; fi\n"
        )
        r = _source_vibe_call({**base_env, "PATH": f"{gh_bin}{os.pathsep}{os.environ.get('PATH', '')}"}, call)
        check("[supervised] create_github_repo returns 0 when the user declines gh sign-in",
              "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
        check("[supervised] declined-sign-in path still tells the user it is skipping",
              "Skipping" in r.stdout, r.stdout)


def test_create_github_repo_caller_tolerates_failure():
    src = VIBE.read_text()
    check("[supervised] item 3: the sole caller is `create_github_repo || true` under set -e",
          "create_github_repo || true" in src, "")
    check("[supervised] item 3: no bare (unguarded) create_github_repo statement remains",
          "\ncreate_github_repo\n" not in src, "")


# ═══════════════════════════════════════════════════════════════════════════
# Item 4: vibe_switch_after_exit failures warn instead of exiting
# ═══════════════════════════════════════════════════════════════════════════

def test_vibe_switch_warn_prints_and_returns_zero():
    print("\n[supervised] item 4: _vibe_switch_warn warns on stderr and always returns 0")
    r = _source_vibe_call({}, 'if _vibe_switch_warn; then echo RC=0; else echo RC=$?; fi')
    check("[supervised] _vibe_switch_warn returns 0", "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
    check("[supervised] _vibe_switch_warn explains the switch did not happen, on stderr",
          "queued agent switch not applied" in r.stderr, r.stderr)


def test_vibe_switch_after_exit_callsites_no_longer_fatal():
    src = VIBE.read_text()
    lines = src.splitlines()
    callsites = [l for l in lines if "vibe_switch_after_exit ||" in l]
    check("[supervised] item 4: exactly two vibe_switch_after_exit call sites exist",
          len(callsites) == 2, str(callsites))
    for l in callsites:
        check(f"[supervised] item 4: call site falls through to _vibe_switch_warn, not exit 1: {l.strip()!r}",
              l.strip() == "vibe_switch_after_exit || _vibe_switch_warn", l)


def test_second_switch_callsite_precedes_auto_resume_loop():
    src = VIBE.read_text()
    lines = src.splitlines()
    callsite_idxs = [i for i, l in enumerate(lines) if l.strip() == "vibe_switch_after_exit || _vibe_switch_warn"]
    loop_idxs = [i for i, l in enumerate(lines) if l.startswith("while auto_resume_pending")]
    check("[supervised] item 4: found both switch call sites and the auto-resume loop",
          len(callsite_idxs) == 2 and len(loop_idxs) >= 1,
          f"callsites={callsite_idxs} loop={loop_idxs}")
    if len(callsite_idxs) == 2 and loop_idxs:
        check("[supervised] item 4: the second (unsupervised) call site precedes the auto-resume loop",
              max(callsite_idxs) < min(loop_idxs),
              f"second callsite={max(callsite_idxs)} loop starts={min(loop_idxs)}")


# ═══════════════════════════════════════════════════════════════════════════
# Item 5: _vibe_onboard_soft — host-onboarding failures no longer fatal
# ═══════════════════════════════════════════════════════════════════════════

def _bin_with_failing_python3(tmp: Path) -> str:
    d = tmp / "failing-python3"
    d.mkdir(parents=True, exist_ok=True)
    stub = d / "python3"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    return str(d)


def test_vibe_onboard_soft_survives_failing_host_onboarding():
    print("\n[supervised] item 5: _vibe_onboard_soft swallows a failing host-onboarding.py")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = tmp / "ws"; ws.mkdir()
        failing_python = _bin_with_failing_python3(tmp)
        env = {"PATH": f"{failing_python}{os.pathsep}{os.environ.get('PATH', '')}"}
        call = (
            'out="$(_vibe_onboard_soft "the queued agent switch" take-agent '
            + shlex.quote(str(ws)) + ')"\n'
            'printf "RC=%s|OUT=[%s]" "$?" "$out"\n'
        )
        r = _source_vibe_call(env, call)
        check("[supervised] _vibe_onboard_soft always returns 0 even when host-onboarding.py fails",
              "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
        check("[supervised] _vibe_onboard_soft yields empty stdout on failure",
              "OUT=[]" in r.stdout, r.stdout)
        check("[supervised] _vibe_onboard_soft prints one ⚠ line naming <what>",
              "⚠ the queued agent switch unavailable — continuing without it." in r.stderr, r.stderr)


def test_vibe_onboard_agent_survives_failing_host_onboarding():
    print("\n[supervised] item 5: vibe_onboard_agent still returns 0 and picks a sane runtime")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = tmp / "ws"; ws.mkdir()
        failing_python = _bin_with_failing_python3(tmp)
        env = {"PATH": f"{failing_python}{os.pathsep}{os.environ.get('PATH', '')}"}
        call = (
            'if vibe_onboard_agent "" ' + shlex.quote(str(ws)) + '; then RC=0; else RC=$?; fi\n'
            'printf "RC=%s|LEAD_AGENT=%s" "$RC" "$LEAD_AGENT"\n'
        )
        r = _source_vibe_call(env, call)
        check("[supervised] vibe_onboard_agent returns 0 despite every host-onboarding call failing",
              "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
        check("[supervised] vibe_onboard_agent still resolves a concrete LEAD_AGENT (claude, non-interactive default)",
              "LEAD_AGENT=claude" in r.stdout, r.stdout)
        check("[supervised] each failed host-onboarding subcommand along the way warned once",
              r.stderr.count("unavailable — continuing without it.") >= 1, r.stderr)


def test_onboarding_hard_failure_callsites_unchanged():
    print("\n[supervised] item 5: git-check / source-check / check call sites are still deliberately fatal")
    src = VIBE.read_text()
    for line in [
        '  _vibe_host_onboarding git-check "$ws" || return 1',
        '  _vibe_host_onboarding source-check "$source" || return 1',
        '  _vibe_host_onboarding check "$ws" "${VIBE_EXTRA_DOMAINS:-}" "$source" || return 1',
    ]:
        check(f"[supervised] still-fatal onboarding call site unchanged: {line.strip()}", line in src, line)


# ═══════════════════════════════════════════════════════════════════════════
# Item 7: WORKSPACE canonicalisation for `vibe <name>` via PROJECTS_DIR
# ═══════════════════════════════════════════════════════════════════════════

def test_resolve_workspace_symlinked_projects_dir_is_canonicalised():
    print("\n[supervised] item 7: `vibe <name>` canonicalises a symlinked PROJECTS_DIR entry")
    src = VIBE.read_text()
    block = _extract_lines(src, 'if [ -z "$PROJECT_ARG" ]; then', "fi")
    check("[supervised] item 7: extracted block contains the new canonicalisation branch",
          'WORKSPACE="$(cd "$WORKSPACE" && pwd -P)"' in block, block)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real_root = tmp / "real-projects"; real_root.mkdir()
        proj = real_root / "myproj"; proj.mkdir()
        link_root = tmp / "link-root"
        link_root.symlink_to(real_root)
        cwd = tmp / "elsewhere"; cwd.mkdir()
        script = (
            'PROJECT_ARG=myproj\n'
            f'PROJECTS_DIR={shlex.quote(str(link_root))}\n'
            f'{block}\n'
            'printf "WORKSPACE=%s|PROJECT_NAME=%s" "$WORKSPACE" "$PROJECT_NAME"\n'
        )
        r = run(["bash", "-c", script], cwd=cwd)
        expected_ws = str(proj.resolve())
        check("[supervised] item 7: WORKSPACE resolves to the real (non-symlinked) path",
              r.returncode == 0 and f"WORKSPACE={expected_ws}|" in r.stdout,
              r.stdout + "|" + r.stderr + f"\nexpected {expected_ws}")
        check("[supervised] item 7: PROJECT_NAME is re-derived from the canonical path",
              "PROJECT_NAME=myproj" in r.stdout, r.stdout)


def test_codex_allowed_matches_only_the_canonical_registry_path():
    print("\n[supervised] item 7 (defect proof): codex_allowed is a literal-line match, so an "
          "un-canonicalised WORKSPACE (the pre-fix bug) would miss a grant recorded at the "
          "canonical path")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real = tmp / "real"; real.mkdir()
        link = tmp / "link"
        link.symlink_to(real)
        home = tmp / "home"; home.mkdir()
        registry_dir = home / ".vibe"; registry_dir.mkdir()
        registry = registry_dir / "codex-allow"
        # `vibe codex allow` on the host always records the canonical (pwd -P) path.
        registry.write_text(str(real.resolve()) + "\n")
        registry.chmod(0o600)
        env = {"HOME": str(home)}
        r_sym = _source_vibe_call(env, f'if codex_allowed {shlex.quote(str(link))}; then echo RC=0; else echo RC=$?; fi')
        r_real = _source_vibe_call(env, f'if codex_allowed {shlex.quote(str(real.resolve()))}; then echo RC=0; else echo RC=$?; fi')
        check("[supervised] codex_allowed refuses the symlinked (non-canonical) workspace path",
              "RC=0" not in r_sym.stdout, r_sym.stdout + "|" + r_sym.stderr)
        check("[supervised] codex_allowed accepts the exact canonical path recorded in the registry",
              "RC=0" in r_real.stdout, r_real.stdout + "|" + r_real.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Item 8: --codex-run/--codex-resume no longer persists LEAD_AGENT via onboarding
# ═══════════════════════════════════════════════════════════════════════════

def test_codex_run_skips_persistent_agent_onboarding():
    print("\n[supervised] item 8: a supervised run no longer reassigns this folder's remembered runtime")
    src = VIBE.read_text()
    check("[supervised] item 8: the _onboard_flag=codex plumbing is gone",
          "_onboard_flag" not in src, "")
    check("[supervised] item 8: LEAD_AGENT=codex is still pinned on the CODEX_ACTION path",
          "LEAD_AGENT=codex" in src, "")
    guarded = (
        '  if [ -z "$CODEX_ACTION" ]; then\n'
        '    vibe_onboard_agent "$AGENT_ARG" "$WORKSPACE" || exit 1\n'
        '  fi'
    )
    check("[supervised] item 8: vibe_onboard_agent is only called when CODEX_ACTION is empty",
          guarded in src, src)


# ═══════════════════════════════════════════════════════════════════════════
# Item 9: model selection / Fable gate keyed on the resolved LEAD_AGENT
# ═══════════════════════════════════════════════════════════════════════════

def test_model_selection_moved_after_lead_agent_resolution():
    print("\n[supervised] item 9: model-selection banner now sits after LEAD_AGENT is resolved")
    src = VIBE.read_text()
    lines = src.splitlines()

    def idx(text):
        try:
            return lines.index(text)
        except ValueError:
            return -1

    i_resolve = idx('LEAD_AGENT="$(_agent_resolve "$AGENT_ARG" "$WORKSPACE")"')
    i_onboard_git = idx('  vibe_onboard_git "$WORKSPACE" || exit 1')
    i_model = idx('# ── Model selection: config default + Fable billing gate ─────────────────────')
    check("[supervised] found the LEAD_AGENT resolve line, the onboarding block and the model banner",
          i_resolve != -1 and i_onboard_git != -1 and i_model != -1,
          f"resolve={i_resolve} onboard_git={i_onboard_git} model={i_model}")
    check("[supervised] item 9: model banner now appears after LEAD_AGENT resolution",
          i_resolve != -1 and i_model != -1 and i_resolve < i_model,
          f"resolve={i_resolve} model={i_model}")
    check("[supervised] item 9: model banner now appears after the interactive onboarding block",
          i_onboard_git != -1 and i_model != -1 and i_onboard_git < i_model,
          f"onboard_git={i_onboard_git} model={i_model}")


def test_model_and_fable_gates_key_on_lead_agent_not_codex_action():
    print("\n[supervised] item 9: the model-default and Fable gates test LEAD_AGENT, not CODEX_ACTION")
    src = VIBE.read_text()
    count = src.count('if [ "$LEAD_AGENT" != codex ]')
    check("[supervised] exactly two gates test LEAD_AGENT != codex (model default, Fable billing)",
          count == 2, f"count={count}")
    check("[supervised] the old CODEX_ACTION-only model-default gate is gone",
          'if [ -z "$CODEX_ACTION" ] && [ -z "$MODEL_ARG" ] && [ -n "${VIBE_MODEL:-}" ]; then' not in src, "")
    check("[supervised] the old CODEX_ACTION-only Fable gate is gone",
          'if [ -z "$CODEX_ACTION" ] && [ "$MODEL_ARG" = "$FABLE_MODEL_ID" ]; then' not in src, "")


def test_claude_only_flags_refused_for_codex_lead():
    print("\n[supervised] item 9: --continue/--resume/--model are refused for a Codex-led launch")
    src = VIBE.read_text()
    block = _extract_lines(src, 'if [ "$LEAD_AGENT" = codex ] \\', "fi")
    check("[supervised] extracted the new Claude-only-flags refusal block",
          "Claude-only" in block, block)

    def run_case(lead, continue_, resume_, model):
        script = (
            f'LEAD_AGENT={shlex.quote(lead)}\n'
            f'CONTINUE={shlex.quote(continue_)}\n'
            f'RESUME={shlex.quote(resume_)}\n'
            f'MODEL_ARG={shlex.quote(model)}\n'
            f'{block}\n'
            'echo NOT_REFUSED\n'
        )
        return run(["bash", "-c", script])

    r1 = run_case("codex", "true", "false", "")
    check("[supervised] codex lead + --continue is refused",
          r1.returncode == 1 and "NOT_REFUSED" not in r1.stdout, r1.stdout + "|" + r1.stderr)
    check("[supervised] refusal names --continue, --resume and --model",
          all(f in r1.stderr for f in ("--continue", "--resume", "--model")), r1.stderr)

    r2 = run_case("codex", "false", "true", "")
    check("[supervised] codex lead + --resume is refused",
          r2.returncode == 1 and "NOT_REFUSED" not in r2.stdout, r2.stdout + "|" + r2.stderr)

    r3 = run_case("codex", "false", "false", "claude-sonnet-5")
    check("[supervised] codex lead + --model is refused",
          r3.returncode == 1 and "NOT_REFUSED" not in r3.stdout, r3.stdout + "|" + r3.stderr)

    r4 = run_case("claude", "true", "false", "")
    check("[supervised] claude lead + --continue is NOT refused",
          r4.returncode == 0 and "NOT_REFUSED" in r4.stdout, r4.stdout + "|" + r4.stderr)

    r5 = run_case("codex", "false", "false", "")
    check("[supervised] codex lead with no Claude-only flags set is NOT refused",
          r5.returncode == 0 and "NOT_REFUSED" in r5.stdout, r5.stdout + "|" + r5.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Item 10: --new-run flag — parse, validate, reach the supervisor argv
# ═══════════════════════════════════════════════════════════════════════════

def test_new_run_flag_parsing_and_default():
    print("\n[supervised] item 10: --new-run parses into CODEX_NEW_RUN, default false")
    r = _source_vibe_call({}, 'parse_vibe_args --codex-run brief.md --new-run; printf "%s|%s" "$CODEX_ACTION" "$CODEX_NEW_RUN"')
    check("[supervised] --new-run after --codex-run sets CODEX_NEW_RUN=true",
          r.returncode == 0 and r.stdout == "run|true", r.stdout + "|" + r.stderr)
    r2 = _source_vibe_call({}, 'parse_vibe_args --codex-run brief.md; printf "%s|%s" "$CODEX_ACTION" "$CODEX_NEW_RUN"')
    check("[supervised] CODEX_NEW_RUN defaults to false when --new-run is absent",
          r2.returncode == 0 and r2.stdout == "run|false", r2.stdout + "|" + r2.stderr)
    r3 = _source_vibe_call({}, 'parse_vibe_args --codex-resume brief.md --new-run; printf "%s|%s" "$CODEX_ACTION" "$CODEX_NEW_RUN"')
    check("[supervised] --new-run also parses after --codex-resume (validation refuses it separately)",
          r3.returncode == 0 and r3.stdout == "resume|true", r3.stdout + "|" + r3.stderr)


def test_new_run_refused_without_codex_run_action():
    print("\n[supervised] item 10: --new-run is refused unless CODEX_ACTION is run")
    src = VIBE.read_text()
    guard = _extract_lines(src, 'if [ "$CODEX_NEW_RUN" = true ] && [ "$CODEX_ACTION" != run ]; then', "fi")
    check("[supervised] extracted the --new-run validation guard",
          "--new-run only applies to --codex-run" in guard, guard)
    cases = [
        ("--new-run", True),
        ("--codex-resume x --new-run", True),
        ("--codex-run brief.md --new-run", False),
        ("--codex-run brief.md", False),
    ]
    for args, should_refuse in cases:
        call = f'parse_vibe_args {args}\n{guard}\necho NOT_REFUSED'
        r = _source_vibe_call({}, call)
        if should_refuse:
            check(f"[supervised] `{args}` is refused",
                  r.returncode == 1 and "NOT_REFUSED" not in r.stdout and
                  "--new-run only applies to --codex-run." in r.stderr,
                  r.stdout + "|" + r.stderr)
        else:
            check(f"[supervised] `{args}` is accepted",
                  r.returncode == 0 and "NOT_REFUSED" in r.stdout,
                  r.stdout + "|" + r.stderr)


def test_new_run_flag_reaches_supervisor_argv():
    print("\n[supervised] item 10: --new-run reaches the codex-entry supervisor argv via launch_codex")
    src = VIBE.read_text()
    launch_codex_body = _extract_func(src, "launch_codex")
    check("[supervised] launch_codex now builds a CODEX_SUPERVISE_EXTRA argv tail",
          "CODEX_SUPERVISE_EXTRA" in launch_codex_body, launch_codex_body)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bindir = tmp / "bin"
        log = tmp / "devcontainer.log"
        _agent_devcontainer_stub(bindir, log)
        ws = tmp / "ws"; ws.mkdir()
        env = {"HOME": str(tmp), "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}

        def run_launch(new_run: bool):
            if log.exists():
                log.unlink()
            call = (
                f'WORKSPACE={shlex.quote(str(ws))}\n'
                'OVERRIDE_CONFIG=/tmp/fixture-override.json\n'
                'CODEX_ACTION=run\n'
                'CODEX_PROMPT_REL=brief.md\n'
                f'CODEX_NEW_RUN={"true" if new_run else "false"}\n'
                f'{launch_codex_body}\n'
                'launch_codex\n'
            )
            return _source_vibe_call(env, call)

        r_on = run_launch(True)
        calls_on = _agent_calls(log)
        check("[supervised] --new-run appends a literal --new-run to the supervisor argv",
              len(calls_on) == 1 and bool(calls_on[0]) and calls_on[0][-1] == "--new-run",
              str(calls_on) + "|" + r_on.stdout + r_on.stderr)

        r_off = run_launch(False)
        calls_off = _agent_calls(log)
        check("[supervised] without --new-run, the supervisor argv carries no --new-run",
              len(calls_off) == 1 and bool(calls_off[0]) and "--new-run" not in calls_off[0],
              str(calls_off) + "|" + r_off.stdout + r_off.stderr)


def test_help_documents_new_run_flag():
    src = VIBE.read_text()
    check("[supervised] item 10: header doc block documents --new-run",
          "#   vibe --codex-run <file> --new-run  # archive any saved supervisor state first" in src, "")


# ═══════════════════════════════════════════════════════════════════════════
# Item 11: the final Codex gate names its refusal reason, stderr not suppressed
# ═══════════════════════════════════════════════════════════════════════════

def test_codex_gate_no_longer_suppresses_stderr():
    print("\n[supervised] item 11: the final Codex gate keeps _codex_desired_source's stderr")
    src = VIBE.read_text()
    check("[supervised] the gate's _codex_desired_source call is unredirected",
          'if [ "$LEAD_AGENT" = "codex" ] && [ -z "$(_codex_desired_source "$WORKSPACE")" ]; then' in src, "")
    check("[supervised] the old 2>/dev/null-suppressed gate condition is gone",
          'if [ "$LEAD_AGENT" = "codex" ] && [ -z "$(_codex_desired_source "$WORKSPACE" 2>/dev/null)" ]; then' not in src,
          "")


def test_codex_gate_reason_branches():
    print("\n[supervised] item 11: the gate names the exact refusal reason for each failure mode")
    src = VIBE.read_text()
    gate = _extract_lines(src, 'if [ "$LEAD_AGENT" = "codex" ] && [ -z "$(_codex_desired_source "$WORKSPACE")" ]; then', "fi")
    check("[supervised] extracted the LEAD_AGENT=codex final gate (task_045), not an unrelated block",
          "needs the Codex login mount" in gate, gate)

    def run_gate(env_extra, ws):
        call = (
            'LEAD_AGENT=codex\n'
            f'WORKSPACE={shlex.quote(str(ws))}\n'
            f'{gate}\n'
            'echo NOT_REACHED\n'
        )
        return _source_vibe_call(env_extra, call)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ws = tmp / "ws"; ws.mkdir()

        home_a = tmp / "home-a"; home_a.mkdir()
        r = run_gate({"HOME": str(home_a), "VIBE_CODEX_PATH": "off"}, ws)
        check("[supervised] gate reason (a): VIBE_CODEX_PATH=off",
              r.returncode == 1 and "NOT_REACHED" not in r.stdout and
              "VIBE_CODEX_PATH=off in ~/.vibe/config disables the Codex login mount" in r.stderr and
              "needs the Codex login mount" in r.stderr,
              r.stdout + "|" + r.stderr)

        home_b = tmp / "home-b"; home_b.mkdir()
        missing_dir = tmp / "no-such-codex-dir"
        r = run_gate({"HOME": str(home_b), "VIBE_CODEX_PATH": str(missing_dir)}, ws)
        check("[supervised] gate reason (b): missing Codex login directory names the path",
              r.returncode == 1 and "NOT_REACHED" not in r.stdout and
              f"no Codex login directory at {missing_dir}" in r.stderr,
              r.stdout + "|" + r.stderr)

        home_c = tmp / "home-c"; home_c.mkdir()
        codex_dir_c = home_c / ".codex"; codex_dir_c.mkdir()
        ws_c = tmp / "ws-c"; ws_c.mkdir()
        r = run_gate({"HOME": str(home_c), "VIBE_CODEX_PATH": str(codex_dir_c)}, ws_c)
        check("[supervised] gate reason (c): missing .vibe-allow-codex marker",
              r.returncode == 1 and "NOT_REACHED" not in r.stdout and
              "this project has no .vibe-allow-codex marker" in r.stderr,
              r.stdout + "|" + r.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Item 12: file-stored Codex login counts as logged-in without a host CLI
# ═══════════════════════════════════════════════════════════════════════════

def test_codex_auth_file_login_truth_table():
    print("\n[supervised] item 12: _codex_auth_file_login truth table")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        good = tmp / "good"; good.mkdir()
        (good / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x"}}))

        good_id = tmp / "good-id"; good_id.mkdir()
        (good_id / "auth.json").write_text(json.dumps({"tokens": {"id_token": "y"}}))

        missing = tmp / "missing"; missing.mkdir()

        malformed = tmp / "malformed"; malformed.mkdir()
        (malformed / "auth.json").write_text("{not json")

        empty_tokens = tmp / "empty-tokens"; empty_tokens.mkdir()
        (empty_tokens / "auth.json").write_text(json.dumps({"tokens": {}}))

        tokens_not_obj = tmp / "tokens-not-obj"; tokens_not_obj.mkdir()
        (tokens_not_obj / "auth.json").write_text(json.dumps({"tokens": "nope"}))

        cases = [
            ("well-formed access_token", good, True),
            ("well-formed id_token", good_id, True),
            ("missing auth.json", missing, False),
            ("malformed JSON", malformed, False),
            ("tokens is an empty object", empty_tokens, False),
            ("tokens is not an object", tokens_not_obj, False),
        ]
        for label, d, expect_true in cases:
            r = _codex_rc_call(tmp, f'_codex_auth_file_login {shlex.quote(str(d))}')
            ok = ("RC=0" in r.stdout) if expect_true else ("RC=0" not in r.stdout)
            check(f"[supervised] _codex_auth_file_login: {label} -> {expect_true}",
                  ok, r.stdout + "|" + r.stderr)

        r = _codex_rc_call(tmp, f'_codex_auth_file_login {shlex.quote(str(tmp / "does-not-exist"))}')
        check("[supervised] _codex_auth_file_login: nonexistent codex-home directory -> false",
              "RC=0" not in r.stdout, r.stdout + "|" + r.stderr)
        r = _codex_rc_call(tmp, "_codex_auth_file_login ''")
        check("[supervised] _codex_auth_file_login: empty path argument -> false",
              "RC=0" not in r.stdout, r.stdout + "|" + r.stderr)


def test_npm_install_only_when_login_still_needed():
    src = VIBE.read_text()
    check('[supervised] item 12: npm-install branch requires BOTH no host CLI and no login yet',
          'if [ "$have_cli" != 1 ] && [ "$logged" != 1 ]; then' in src, "")
    check('[supervised] item 12: the old have_cli-only npm-install guard is gone',
          'if [ "$have_cli" != 1 ]; then' not in src, "")


def test_onboard_codex_treats_file_login_as_logged_in_without_host_cli():
    print("\n[supervised] item 12: vibe_onboard_codex treats a file-stored login as logged-in "
          "when the host has no codex CLI, and skips both the consent prompt and npm-install")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, ws = _codex_grant_fixture(tmp)
        (home / ".codex" / "auth.json").write_text(json.dumps({"tokens": {"access_token": "tok"}}))
        no_codex_path = _path_without(tmp, {"codex", "npm"})
        call = (
            "_vibe_interactive() { return 0; }\n"
            "_vibe_host_onboarding() { return 0; }\n"
            'if vibe_onboard_codex ' + shlex.quote(str(ws)) + '; then echo RC=0; else echo "RC=$?"; fi\n'
        )
        env = {
            "HOME": str(home),
            "PATH": no_codex_path,
            "VIBE_EXTRA_DOMAINS": "chatgpt.com auth.openai.com api.openai.com",
        }
        r = _source_vibe_call(env, call)
        check("[supervised] vibe_onboard_codex returns 0 (already ready) with a file-stored login and no host CLI",
              "RC=0" in r.stdout, r.stdout + "|" + r.stderr)
        check("[supervised] no 'Set up Codex' consent prompt was needed",
              "Set up Codex here?" not in (r.stdout + r.stderr), r.stdout + "|" + r.stderr)
        check("[supervised] npm-install was never attempted (no npm/node install error surfaced)",
              "Install Node.js/npm" not in r.stderr, r.stderr)
