from smoke._core import *  # noqa: F401,F403




def test_task017_c3_repo_claim_documented_flow_runnable() -> None:
    """AC12: /repo claim has NO sourced vibe helper backing it — it is pure
    documentation (Claude runs Bash per repo.md's prose); confirmed by
    grepping vibe's source for a claim-writing function and finding none.
    Since there is no fenced literal command to extract, this instead
    substitutes concrete values for repo.md's placeholders (path template +
    KEY=VALUE content template, both quoted verbatim from the file) and
    proves the resulting mkdir+write is syntactically runnable and produces
    the pinned KEY=VALUE shape, plus the pinned last-claim-wins overwrite
    semantics."""
    print("\n[task_017 AC12: /repo claim's documented request-file flow is syntactically runnable]")
    vibe_src = VIBE.read_text()
    check("[c3-claim] no sourced vibe helper implements /repo claim (pure documentation)",
          "shared_repo_claim" not in vibe_src and "repo_claim_write" not in vibe_src, "")

    body = REPO_MD.read_text() if REPO_MD.exists() else ""
    check("[c3-claim] repo.md documents the exact rw-request path template",
          "${VIBE_REPOS_DIR:-/repos}/.signals/<name>/rw-request" in body, "")
    check("[c3-claim] repo.md pins unconditional overwrite (last-claim-wins)",
          "Overwrite unconditionally" in body and "last-claim-wins" in body, "")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        name = "andeyePro"
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path)}
        req_file = td_path / ".signals" / name / "rw-request"

        def file_claim(project: str) -> subprocess.CompletedProcess:
            # Path + content shape taken verbatim from repo.md's `/repo claim`
            # section, placeholders substituted with concrete values.
            snippet = (
                f'mkdir -p "${{VIBE_REPOS_DIR:-/repos}}/.signals/{name}" && '
                f'printf \'project=%s\\nsince=%s\\n\' {shlex.quote(project)} "$(date -u +%s)" '
                f'> "${{VIBE_REPOS_DIR:-/repos}}/.signals/{name}/rw-request"'
            )
            return subprocess.run(["sh", "-c", snippet], env=env,
                                   capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)

        r1 = file_claim("moneyandeye")
        check("[c3-claim] documented mkdir+write runs cleanly (syntactically valid)",
              r1.returncode == 0, r1.stderr[:200])
        check("[c3-claim] rw-request file created at the documented path",
              req_file.is_file(), str(req_file))
        if req_file.is_file():
            content = req_file.read_text()
            check("[c3-claim] rw-request content matches KEY=VALUE project=<name>",
                  re.search(r"^project=moneyandeye$", content, re.MULTILINE) is not None, content)
            check("[c3-claim] rw-request content matches KEY=VALUE since=<digits>",
                  re.search(r"^since=\d+$", content, re.MULTILINE) is not None, content)

        r2 = file_claim("otherclaimant")
        check("[c3-claim] second claim overwrite runs cleanly", r2.returncode == 0, r2.stderr[:200])
        content2 = req_file.read_text() if req_file.is_file() else ""
        check("[c3-claim] last-claim-wins: newest claimant fully replaces the old request",
              "project=otherclaimant" in content2 and "project=moneyandeye" not in content2, content2)


def test_task017_c3_vibe_project_name_export_plumbing() -> None:
    """AC13/AC18-style plumbing check scoped to VIBE_PROJECT_NAME: the
    launcher exports it as a top-level (not command-substitution-internal)
    statement, before the _build_override_config command substitution that
    would otherwise swallow the export; and devcontainer.json's remoteEnv
    (never containerEnv) carries it through so ${localEnv:VIBE_PROJECT_NAME}
    resolves in-container."""
    print("\n[task_017 AC13: VIBE_PROJECT_NAME export site + remoteEnv plumbing]")
    src = VIBE.read_text()
    lines = src.splitlines()
    export_lines = [i for i, ln in enumerate(lines) if ln.strip() == "export VIBE_PROJECT_NAME"]
    check("[c3-plumb] exactly one literal 'export VIBE_PROJECT_NAME' line in the script",
          len(export_lines) == 1, str(export_lines))
    if export_lines:
        idx = export_lines[0]
        check("[c3-plumb] export line sits at column 0 (top-level scope, not inside a function body)",
              lines[idx] == "export VIBE_PROJECT_NAME", repr(lines[idx]))
        assign_line = lines[idx - 1] if idx > 0 else ""
        check("[c3-plumb] preceding line assigns VIBE_PROJECT_NAME=\"$PROJECT_NAME\" (plain assignment, "
              "not inside a command substitution)",
              assign_line.strip() == 'VIBE_PROJECT_NAME="$PROJECT_NAME"', repr(assign_line))
        override_call_idx = next(
            (i for i, ln in enumerate(lines) if "OVERRIDE_CONFIG=$(_build_override_config" in ln), None)
        check("[c3-plumb] export happens BEFORE the _build_override_config command-substitution call "
              "(exports inside $(...) die with the subshell)",
              override_call_idx is not None and idx < override_call_idx,
              f"export_idx={idx} override_call_idx={override_call_idx}")

    devcontainer_json = json.loads((REPO / "devcontainer" / "devcontainer.json").read_text())
    remote_env = devcontainer_json.get("remoteEnv", {})
    container_env = devcontainer_json.get("containerEnv", {})
    check("[c3-plumb] devcontainer.json remoteEnv carries VIBE_PROJECT_NAME via ${localEnv:...}",
          remote_env.get("VIBE_PROJECT_NAME") == "${localEnv:VIBE_PROJECT_NAME}",
          str(remote_env.get("VIBE_PROJECT_NAME")))
    check("[c3-plumb] VIBE_PROJECT_NAME is NOT in containerEnv (remoteEnv-only, mirrors GITHUB_TOKEN discipline)",
          "VIBE_PROJECT_NAME" not in container_env, str(container_env))


def test_task017_c4_ac16_project_slug_exact_match_serves_project_token() -> None:
    print("\n[task_017 C4 AC16: project slug exact match -> $GITHUB_TOKEN]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="andeyePro/vibe"))
    _c4_assert_served("project exact match", r, "ghp_project")


def test_task017_c4_ac16_shared_slug_match_with_valid_twin_serves_shared_token() -> None:
    print("\n[task_017 C4 AC16: configured shared slug (twin verified) -> its OWN token, never $GITHUB_TOKEN]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_served("shared match", r, "ghp_shared")
    check("shared match: NEVER serves the project token instead",
          "ghp_project" not in r.stdout, r.stdout)


def test_task017_c4_ac16_unknown_repo_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: unconfigured repo -> NOTHING (central invariant)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="someone-else/unrelated-repo"))
    _c4_assert_silent("unknown repo", r)


def test_task017_c4_ac16_nopath_no_shared_tokens_serves_project_token_compat() -> None:
    print("\n[task_017 C4 AC17 no-path compat: no path + no shared repos configured -> $GITHUB_TOKEN]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path=None))
    _c4_assert_served("no-path compat", r, "ghp_project")


def test_task017_c4_ac16_nopath_shared_tokens_configured_serves_nothing() -> None:
    print("\n[task_017 C4 AC17 no-path fail-closed: no path + a shared repo IS configured -> NOTHING]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path=None))
    _c4_assert_silent("no-path + shared configured (mis-set useHttpPath must not widen)", r)


def test_task017_c4_ac16_dot_git_suffix_shared_match() -> None:
    print("\n[task_017 C4 AC16: '.git' suffix on a shared slug still matches]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro.git"))
    _c4_assert_served(".git suffix", r, "ghp_shared")


def test_task017_c4_ac16_subdir_suffix_shared_match() -> None:
    print("\n[task_017 C4 AC16: useHttpPath subdir suffix (owner/repo/info/refs) still matches]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro/info/refs"))
    _c4_assert_served("subdir suffix", r, "ghp_shared")


def test_task017_c4_ac16_trailing_slash_only_unmatched_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: trailing-slash-only path on an UNCONFIGURED repo -> still NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="someone-else/unrelated-repo/"))
    _c4_assert_silent("trailing-slash-only, unmatched", r)


def test_task017_c4_ac16_trailing_slash_project_slug_still_matches() -> None:
    """Documents (doesn't just attack): the same subpath-discard rule that
    lets owner/repo/info/refs through also lets a bare trailing slash on the
    PROJECT's own slug through. Not a leak — it's still an exact owner/repo
    match against GITHUB_REPO_SLUG, just with a trailing empty segment
    discarded, same as any other subpath suffix."""
    print("\n[task_017 C4 AC16: trailing-slash-only on the PROJECT's own slug still matches (documented, not a leak)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="andeyePro/vibe/"))
    _c4_assert_served("trailing-slash on project's own slug", r, "ghp_project")


def test_task017_c4_ac16_case_difference_project_slug_never_matches() -> None:
    print("\n[task_017 C4 AC16: differently-cased project slug must NOT match (case-sensitive)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path="AndeyePro/Vibe"))
    _c4_assert_silent("case-differing project slug", r)


def test_task017_c4_ac16_traversal_segments_serve_nothing() -> None:
    print("\n[task_017 C4 AC16: '..' traversal segments -> NOTHING even when it resolves to a configured slug]")
    san = _c4_sanitise("other/repo")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared",
         f"VIBE_SHARED_SLUG_{san}": "other/repo"},
        _c4_cred_stdin(path="andeyePro/../other/repo"))
    _c4_assert_silent("traversal segments", r)


def test_task017_c4_ac16_embedded_control_char_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: embedded control byte (CR) in an otherwise-matching path -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(raw_path="path=andeyePro/vibe\r"))
    _c4_assert_silent("embedded CR", r)


def test_task017_c4_ac16_injection_string_serves_nothing_and_does_not_execute() -> None:
    print("\n[task_017 C4 AC16: shell-metacharacter injection string in path -> NOTHING, no execution]")
    sentinel = Path(tempfile.gettempdir()) / f"vibe-c4-injection-sentinel-{os.getpid()}"
    if sentinel.exists():
        sentinel.unlink()
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(path=f"foo/bar; touch {sentinel} #"))
    _c4_assert_silent("injection string", r)
    check("injection string: no side-effect execution (sentinel file NOT created)",
          not sentinel.exists(), str(sentinel))
    if sentinel.exists():
        sentinel.unlink()


def test_task017_c4_ac16_sanitisation_collision_twin_mismatch_serves_nothing() -> None:
    """The gate-discriminating fixture (security-review C4 LOW, closed):
    sanitisation is lossy — foo-bar/baz and foo/bar-baz both sanitise to
    ..._FOO_BAR_BAZ. If the twin var holds the OTHER slug, a request for
    the colliding one must get NOTHING even though its env-name lookup would
    otherwise succeed. Pre-hardening this would have leaked the shared token
    to the wrong repo."""
    print("\n[task_017 C4 AC16: sanitisation-collision, twin mismatch -> NOTHING (post-security-review hardening)]")
    san = _c4_sanitise("foo/bar-baz")
    assert san == _c4_sanitise("foo-bar/baz"), "fixture assumption: both slugs must collide"
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared_for_foo_bar_baz",
         f"VIBE_SHARED_SLUG_{san}": "foo/bar-baz"},
        _c4_cred_stdin(path="foo-bar/baz"))
    _c4_assert_silent("sanitisation-collision, twin holds the OTHER slug", r)


def test_task017_c4_ac16_sanitisation_collision_twin_match_serves_correct_token() -> None:
    print("\n[task_017 C4 AC16: sanitisation-collision, twin MATCHES the request -> its token served]")
    san = _c4_sanitise("foo/bar-baz")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared_for_foo_bar_baz",
         f"VIBE_SHARED_SLUG_{san}": "foo/bar-baz"},
        _c4_cred_stdin(path="foo/bar-baz"))
    _c4_assert_served("sanitisation-collision, twin matches the request", r, "ghp_shared_for_foo_bar_baz")


def test_task017_c4_ac16_twin_unset_serves_nothing_even_with_token_set() -> None:
    print("\n[task_017 C4 AC16: twin var entirely unset (stale container/launcher mismatch) -> NOTHING]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "ghp_shared"},
        # deliberately no VIBE_SHARED_SLUG_<san> at all
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_silent("twin var unset", r)


def test_task017_c4_ac16_non_get_operation_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: non-'get' git credential ops (store/erase) -> NOTHING]")
    for op in ("store", "erase"):
        r = _c4_run_cred_helper(
            {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
            _c4_cred_stdin(path="andeyePro/vibe"), op=op)
        _c4_assert_silent(f"op={op}", r)


def test_task017_c4_ac16_non_github_host_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: non-github.com host -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(host="gitlab.com", path="andeyePro/vibe"))
    _c4_assert_silent("non-github host", r)


def test_task017_c4_ac16_lookalike_subdomain_host_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: lookalike host (github.com.evil.com) -> NOTHING (exact host match only)]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(host="github.com.evil.com", path="andeyePro/vibe"))
    _c4_assert_silent("lookalike subdomain host", r)


def test_task017_c4_ac16_http_not_https_serves_nothing() -> None:
    print("\n[task_017 C4 AC16: http (not https) -> NOTHING]")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"},
        _c4_cred_stdin(protocol="http", path="andeyePro/vibe"))
    _c4_assert_silent("http not https", r)


def test_task017_c4_ac16_empty_shared_token_never_served() -> None:
    print("\n[task_017 C4 AC16: matched shared slug but its token var is EMPTY -> NOTHING, never falls back]")
    san = _c4_sanitise("andeyePro/andeyePro")
    r = _c4_run_cred_helper(
        {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project",
         f"VIBE_SHARED_TOKEN_{san}": "",
         f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"},
        _c4_cred_stdin(path="andeyePro/andeyePro"))
    _c4_assert_silent("empty shared token", r)


def test_task017_c4_ac16_never_widen_attack_battery() -> None:
    """THE central invariant, attacked from many angles at once: no fixture
    here is the project's own slug, yet every env has GITHUB_TOKEN staged.
    None of these may ever put 'ghp_project' on stdout."""
    print("\n[task_017 C4 AC16: never-widen attack battery — $GITHUB_TOKEN must NEVER appear for a non-project path]")
    base_env = {"GITHUB_REPO_SLUG": "andeyePro/vibe", "GITHUB_TOKEN": "ghp_project"}
    san_shared = _c4_sanitise("andeyePro/andeyePro")
    attacks = [
        ("plain unrelated repo", {}, _c4_cred_stdin(path="totally/unrelated")),
        ("shared repo configured, wrong twin", {
            f"VIBE_SHARED_TOKEN_{san_shared}": "ghp_shared",
            f"VIBE_SHARED_SLUG_{san_shared}": "different/slug",
        }, _c4_cred_stdin(path="andeyePro/andeyePro")),
        ("traversal into project-adjacent path", {}, _c4_cred_stdin(path="andeyePro/../vibe")),
        ("case-flipped project slug", {}, _c4_cred_stdin(path="ANDEYEPRO/VIBE")),
        ("project slug with control byte suffix", {}, _c4_cred_stdin(raw_path="path=andeyePro/vibe\x01")),
        ("empty path key present but blank", {}, _c4_cred_stdin(raw_path="path=")),
        ("non-github host claiming project path", {}, _c4_cred_stdin(host="notgithub.com", path="andeyePro/vibe")),
        ("http claiming project path", {}, _c4_cred_stdin(protocol="http", path="andeyePro/vibe")),
    ]
    for name, extra_env, stdin_text in attacks:
        env = {**base_env, **extra_env}
        r = _c4_run_cred_helper(env, stdin_text)
        check(f"[never-widen] {name}: $GITHUB_TOKEN never appears on stdout",
              "ghp_project" not in r.stdout, r.stdout)


def test_task017_c4_ac17_usehttppath_same_scope_as_helper_registration() -> None:
    print("\n[task_017 C4 AC17: credential.useHttpPath set at the SAME scope as credential.helper registration]")
    src = SETUP_GIT_SH.read_text()
    helper_line = next((ln for ln in src.splitlines() if "credential.helper" in ln and "git config" in ln), None)
    usehttppath_line = next((ln for ln in src.splitlines() if "credential.useHttpPath" in ln and "git config" in ln), None)
    check("[ac17] setup-git.sh sets credential.helper", helper_line is not None, src)
    check("[ac17] setup-git.sh sets credential.useHttpPath", usehttppath_line is not None, src)
    if helper_line and usehttppath_line:
        check("[ac17] credential.helper registered at --global scope",
              "--global" in helper_line, helper_line)
        check("[ac17] credential.useHttpPath set at --global scope (same as the helper)",
              "--global" in usehttppath_line, usehttppath_line)
        check("[ac17] useHttpPath value is literally 'true'",
              usehttppath_line.strip().endswith("true"), usehttppath_line)


def test_task017_c4_ac17_setup_git_functional_in_sandbox_home() -> None:
    print("\n[task_017 C4 AC17: setup-git.sh is runnable in a sandbox HOME and produces both settings]")
    with tempfile.TemporaryDirectory() as td:
        sandbox_home = Path(td) / "home"
        sandbox_home.mkdir()
        env = _isolate_extras_env({**os.environ, "HOME": str(sandbox_home)})
        r = run(["bash", str(SETUP_GIT_SH)], env=env)
        check("[ac17] setup-git.sh exits 0 in a fresh sandbox HOME (no ~/.gitconfig-host present)",
              r.returncode == 0, r.stderr)
        helper_r = run(["git", "config", "--global", "--get", "credential.helper"], env=env)
        usehttppath_r = run(["git", "config", "--global", "--get", "credential.useHttpPath"], env=env)
        check("[ac17] resulting ~/.gitconfig has credential.helper = vibe-credential-helper",
              helper_r.stdout.strip() == "/usr/local/bin/vibe-credential-helper", helper_r.stdout)
        check("[ac17] resulting ~/.gitconfig has credential.useHttpPath = true",
              usehttppath_r.stdout.strip() == "true", usehttppath_r.stdout)


def test_setup_git_strips_host_credential_helpers() -> None:
    print("\n[setup-git.sh strips host-only credential helpers (gh / osxkeychain) — no 'gh: not found' per push]")
    host_cfg = (
        "[user]\n\tname = Fixture\n"
        "[credential \"https://github.com\"]\n\thelper = \n\thelper = !/opt/homebrew/bin/gh auth git-credential\n"
        "[credential \"https://gist.github.com\"]\n\thelper = \n\thelper = !/opt/homebrew/bin/gh auth git-credential\n"
        "[credential]\n\thelper = osxkeychain\n"
    )
    with tempfile.TemporaryDirectory() as td:
        sandbox_home = Path(td) / "home"
        sandbox_home.mkdir()
        (sandbox_home / ".gitconfig-host").write_text(host_cfg)
        env = _isolate_extras_env({**os.environ, "HOME": str(sandbox_home)})
        # setup-git.sh's `git config --global` writes are meant to land in
        # this already-sandboxed $HOME/.gitconfig (copied from
        # .gitconfig-host) — that's exactly what this test inspects. The
        # builder's GIT_CONFIG_GLOBAL default would redirect every
        # `--global` read/write (this script's and this test's) to an
        # unrelated scratch file instead, so the host_cfg-seeded user.name
        # would never show up there. Drop the override: HOME here is
        # already a fresh sandbox, not the real one, so the builder's
        # GIT_CONFIG_GLOBAL isolation isn't needed for safety in this test.
        del env["GIT_CONFIG_GLOBAL"]
        r = run(["bash", str(SETUP_GIT_SH)], env=env)
        check("[cred-strip] setup-git.sh exits 0 with a gh/osxkeychain host config", r.returncode == 0, r.stderr)
        all_helpers = run(["git", "config", "--global", "--get-regexp", r"^credential\..*helper$"], env=env).stdout
        check("[cred-strip] only vibe's helper remains across every credential.*helper key",
              all_helpers.strip() == "credential.helper /usr/local/bin/vibe-credential-helper", all_helpers)
        check("[cred-strip] host user.name survives the strip",
              run(["git", "config", "--global", "--get", "user.name"], env=env).stdout.strip() == "Fixture")
        # Behavioural: git's resolved helper list for a github.com URL must be vibe's alone.
        probe = run(["git", "-c", "credential.helper=", "config", "--global", "--get-all",
                     "credential.https://github.com.helper"], env=env)
        check("[cred-strip] no URL-scoped github.com helper entries left", probe.stdout.strip() == "", probe.stdout)


def test_task017_c4_ac18_top_level_exports_outside_build_override_config() -> None:
    print("\n[task_017 C4 AC18: GITHUB_REPO_SLUG / VIBE_SHARED_TOKEN_* / VIBE_SHARED_SLUG_* exports sit "
          "OUTSIDE _build_override_config (top-level scope; exports inside $(...) die with the subshell)]")
    lines = VIBE.read_text().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln == "_build_override_config() {"), None)
    check("[ac18] _build_override_config function start found", start is not None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == "}"), None)
    check("[ac18] _build_override_config function end found", end is not None)
    if end is None:
        return
    span = range(start, end + 1)

    export_slug_idx = next((i for i, ln in enumerate(lines) if ln.strip() == 'export GITHUB_REPO_SLUG="$GITHUB_REPO"'), None)
    export_shared_tok_idx = next((i for i, ln in enumerate(lines) if ln.strip() == 'export "$_env_name"="$_shared_tok"'), None)
    export_shared_slug_idx = next(
        (i for i, ln in enumerate(lines)
         if 'export "VIBE_SHARED_SLUG_' in ln), None)

    check("[ac18] 'export GITHUB_REPO_SLUG' line found", export_slug_idx is not None)
    check("[ac18] shared-token export line found", export_shared_tok_idx is not None)
    check("[ac18] shared-slug-twin export line found", export_shared_slug_idx is not None)

    if export_slug_idx is not None:
        check("[ac18] GITHUB_REPO_SLUG export is OUTSIDE _build_override_config",
              export_slug_idx not in span, f"line {export_slug_idx}: {lines[export_slug_idx]!r}")
        check("[ac18] GITHUB_REPO_SLUG export is at column 0 (top-level, not inside any function)",
              lines[export_slug_idx] == lines[export_slug_idx].lstrip(), repr(lines[export_slug_idx]))
    if export_shared_tok_idx is not None:
        check("[ac18] shared-token export is OUTSIDE _build_override_config",
              export_shared_tok_idx not in span, f"line {export_shared_tok_idx}: {lines[export_shared_tok_idx]!r}")
    if export_shared_slug_idx is not None:
        check("[ac18] shared-slug-twin export is OUTSIDE _build_override_config",
              export_shared_slug_idx not in span, f"line {export_shared_slug_idx}: {lines[export_shared_slug_idx]!r}")

    override_call_idx = next(
        (i for i, ln in enumerate(lines) if "OVERRIDE_CONFIG=$(_build_override_config" in ln), None)
    check("[ac18] _build_override_config command-substitution call site found", override_call_idx is not None)
    if export_slug_idx is not None and override_call_idx is not None:
        check("[ac18] GITHUB_REPO_SLUG export happens BEFORE the command-substitution call",
              export_slug_idx < override_call_idx,
              f"export_idx={export_slug_idx} override_call_idx={override_call_idx}")
    if export_shared_tok_idx is not None and override_call_idx is not None:
        check("[ac18] shared-token export loop happens BEFORE the command-substitution call",
              export_shared_tok_idx < override_call_idx,
              f"export_idx={export_shared_tok_idx} override_call_idx={override_call_idx}")


def test_task017_c4_ac18_remoteenv_shared_token_and_twin_injection() -> None:
    print("\n[task_017 C4 AC18: override-config generator injects matching VIBE_SHARED_TOKEN_*/"
          "VIBE_SHARED_SLUG_* remoteEnv passthroughs]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        san = _c4_sanitise("andeyePro/andeyePro")
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off",
               # Simulates what the top-level export block (tested structurally
               # above) would have produced for this declared repo.
               "VIBE_SHARED_ENV_NAMES": f"VIBE_SHARED_TOKEN_{san}",
               f"VIBE_SHARED_TOKEN_{san}": "ghp_faketoken",
               f"VIBE_SHARED_SLUG_{san}": "andeyePro/andeyePro"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("[ac18] exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {}
        remote_env = cfg.get("remoteEnv", {})
        container_env = cfg.get("containerEnv", {})
        check(f"[ac18] remoteEnv carries VIBE_SHARED_TOKEN_{san} -> ${{localEnv:...}} passthrough",
              remote_env.get(f"VIBE_SHARED_TOKEN_{san}") == f"${{localEnv:VIBE_SHARED_TOKEN_{san}}}",
              str(remote_env))
        check(f"[ac18] remoteEnv ALSO carries the VIBE_SHARED_SLUG_{san} twin passthrough",
              remote_env.get(f"VIBE_SHARED_SLUG_{san}") == f"${{localEnv:VIBE_SHARED_SLUG_{san}}}",
              str(remote_env))
        check("[ac18] neither the token nor the twin land in containerEnv (remoteEnv-only, mirrors GITHUB_TOKEN)",
              f"VIBE_SHARED_TOKEN_{san}" not in container_env and f"VIBE_SHARED_SLUG_{san}" not in container_env,
              str(container_env))


def test_task017_c4_ac19_claude_md_invariant_text_amended() -> None:
    print("\n[task_017 C4 AC19: CLAUDE.md invariant text amended for per-repo tokens / launch-header blast radius]")
    src = (REPO / "CLAUDE.md").read_text()
    check("[ac19] CLAUDE.md still says each PAT stays scoped to one repo",
          "one repo" in src or "single-repo" in src, "one repo / single-repo phrase not found")
    check("[ac19] CLAUDE.md ties blast radius to the launch header",
          "blast radius" in src and "launch header" in src, "blast radius / launch header phrasing not found")
    check("[ac19] CLAUDE.md explicitly rules out a multi-repo token",
          "never a multi-repo token" in src or "never one token reused across repos" in src,
          "no explicit multi-repo-token prohibition found")


def test_task017_c4_ac19_readme_security_section_consistent() -> None:
    print("\n[task_017 C4 AC19: README security section consistent with the amended invariant]")
    src = (REPO / "README.md").read_text()
    check("[ac19] README says every fine-grained PAT stays scoped to a single repo",
          "single repo" in src, "single repo phrase not found in README")
    check("[ac19] README ties blast radius to the launch header",
          "blast radius" in src and "launch header" in src, "blast radius / launch header phrasing not found in README")
    check("[ac19] README explicitly rules out a multi-repo token",
          "never a multi-repo token" in src, "no explicit multi-repo-token prohibition found in README")


def test_vibe_statusline_rate_limit_side_effect() -> None:
    """statusLine side effect: when .rate_limits.five_hour.used_percentage is
    present AND ${VIBE_VSS_DIR:-/workspace/.vss} exists, the command atomically
    drops an epoch=/used= reading into <dir>/rate-limit for the launcher's
    rate-limit-aware auto-resume countdown. Display output must be byte-
    identical whether or not the side effect fires; no file appears when the
    field is missing or the dir doesn't exist."""
    print("\n[statusLine: rate-limit side-effect file]")
    cmd = _statusline_command()
    check("[status-rl] command extracted", bool(cmd), "")
    if not cmd:
        return
    check("[status-rl] command honours VIBE_VSS_DIR", "VIBE_VSS_DIR" in cmd, cmd[:200])

    with_rl = ('{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":42.7},'
               '"rate_limits":{"five_hour":{"used_percentage":63}}}')
    with_rl_frac = ('{"model":{"display_name":"Opus 4.8"},'
                    '"rate_limits":{"five_hour":{"used_percentage":4.9}}}')
    without_rl = '{"model":{"display_name":"Opus 4.8"}}'

    def run_cmd(stdin_json: str, vss_dir: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "VIBE_VSS_DIR": vss_dir}
        return subprocess.run(["sh", "-c", cmd], input=stdin_json, env=env,
                              capture_output=True, text=True, timeout=15)

    with tempfile.TemporaryDirectory() as td:
        # rate_limits present + dir exists → file written, display unchanged
        r = run_cmd(with_rl, td)
        rl_path = Path(td) / "rate-limit"
        check("[status-rl] display exact with side effect",
              r.returncode == 0 and r.stdout == "F · vibe · ctx 42% · 5h 63%",
              f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")
        check("[status-rl] rate-limit file written", rl_path.is_file(), str(list(Path(td).iterdir())))
        if rl_path.is_file():
            lines = rl_path.read_text().splitlines()
            check("[status-rl] exactly two KEY=VALUE lines", len(lines) == 2, str(lines))
            check("[status-rl] epoch= is a plausible current epoch",
                  len(lines) == 2 and re.fullmatch(r"epoch=\d{10,}", lines[0]) is not None,
                  str(lines))
            check("[status-rl] used= carries the floored percent",
                  len(lines) == 2 and lines[1] == "used=63", str(lines))
        check("[status-rl] no tmp file left behind",
              not list(Path(td).glob("rate-limit.tmp.*")), str(list(Path(td).iterdir())))

        # fractional percentage → floored integer in the file
        r = run_cmd(with_rl_frac, td)
        check("[status-rl] fractional display exact",
              r.returncode == 0 and r.stdout == "O · vibe · 5h 4%",
              f"rc={r.returncode} out=[{r.stdout}]")
        check("[status-rl] fractional used= floored",
              rl_path.is_file() and "used=4" in rl_path.read_text().splitlines(),
              rl_path.read_text() if rl_path.is_file() else "missing")

        # field missing → no file (fresh dir so the earlier write can't mask it)
        sub = Path(td) / "no-field"
        sub.mkdir()
        r = run_cmd(without_rl, str(sub))
        check("[status-rl] no rate_limits → display exact",
              r.returncode == 0 and r.stdout == "O · vibe",
              f"rc={r.returncode} out=[{r.stdout}]")
        check("[status-rl] no rate_limits → no file written",
              not (sub / "rate-limit").exists(), str(list(sub.iterdir())))

        # dir doesn't exist → no file, display still byte-identical to the
        # dir-exists run of the same fixture (side effect changes NOTHING visible)
        gone = str(Path(td) / "does-not-exist")
        r = run_cmd(with_rl, gone)
        check("[status-rl] missing dir → display identical",
              r.returncode == 0 and r.stdout == "F · vibe · ctx 42% · 5h 63%",
              f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")
        check("[status-rl] missing dir → nothing created",
              not Path(gone).exists(), "")


def test_vibe_auto_resume_effective_wait() -> None:
    """auto_resume_effective_wait + auto_resume_rate_headroom: the resume_at
    base estimate is capped at the 120s grace ONLY for a fresh, low-usage
    rate-limit reading; every malformed/stale/absent input keeps the
    conservative base wait. Fixed epochs so the cases are deterministic:
    now=1000000000, resume_at=now+7200 → base wait 7320."""
    print("\n[vibe auto_resume_effective_wait: rate-limit-aware countdown]")
    snippet = (
        'm="${TMPDIR:-/tmp}/vibe-arw-m.$$"; r="${TMPDIR:-/tmp}/vibe-arw-r.$$"; now=1000000000; '
        "printf 'active=1\\nremaining=2\\nresume_at=1000007200\\n' > \"$m\"; "
        # fresh (age 10) + low (4) → cap at 120; headroom echoes the used%
        "printf 'epoch=999999990\\nused=4\\n' > \"$r\"; "
        'echo "CAP=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        'echo "USED=[$(auto_resume_rate_headroom "$r" "$now")]"; '
        # fresh + high (51 > default 50) → uncapped
        "printf 'epoch=999999990\\nused=51\\n' > \"$r\"; "
        'echo "HIGH=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # stale (age 2000 > default 1800) + low → uncapped
        "printf 'epoch=999998000\\nused=4\\n' > \"$r\"; "
        'echo "STALE=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # missing file → uncapped (also the resume_at-future base-preserved case)
        'echo "MISSING=[$(auto_resume_effective_wait "$m" "$r.missing" "$now")]"; '
        # garbage epoch → uncapped
        "printf 'epoch=notanumber\\nused=4\\n' > \"$r\"; "
        'echo "GEPOCH=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # garbage (injection-shaped) used → uncapped
        "printf 'epoch=999999990\\nused=evil; rm -rf /\\n' > \"$r\"; "
        'echo "GUSED=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # env knob: tighter max age (60 < age 100) → uncapped
        "printf 'epoch=999999900\\nused=4\\n' > \"$r\"; "
        'echo "KNOBAGE=[$(VIBE_RATE_READING_MAX_AGE=60; auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # env knob: looser used max (80 >= used 70, default 50 would refuse) → capped
        "printf 'epoch=999999990\\nused=70\\n' > \"$r\"; "
        'echo "KNOBUSED=[$(VIBE_RESUME_USED_MAX=80; auto_resume_effective_wait "$m" "$r" "$now")]"; '
        'echo "DEFUSED=[$(auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # garbage knob value collapses to the default (fresh+low → still capped)
        "printf 'epoch=999999990\\nused=4\\n' > \"$r\"; "
        'echo "GKNOB=[$(VIBE_RATE_READING_MAX_AGE=bogus; auto_resume_effective_wait "$m" "$r" "$now")]"; '
        # resume_at already past → 120 grace regardless of any reading
        "printf 'active=1\\nremaining=2\\nresume_at=999999000\\n' > \"$m\"; "
        'echo "PAST=[$(auto_resume_effective_wait "$m" "$r.missing" "$now")]"; '
        # grace knob: past resume_at with a 5s override → 5 (MANUAL-TESTS 32)
        'echo "KNOBGRACE=[$(VIBE_RESUME_PAST_GRACE_SECS=5; auto_resume_effective_wait "$m" "$r.missing" "$now")]"; '
        # garbage grace knob collapses to the 120 default
        'echo "GGRACE=[$(VIBE_RESUME_PAST_GRACE_SECS="evil; rm -rf /"; auto_resume_effective_wait "$m" "$r.missing" "$now")]"; '
        # no usable resume_at → 1800 default
        "printf 'active=1\\nremaining=2\\n' > \"$m\"; "
        'echo "NORA=[$(auto_resume_effective_wait "$m" "$r.missing" "$now")]"; '
        'rm -f "$m" "$r"'
    )
    r = _source_vibe_call({}, snippet)
    check("[eff-wait] exits 0", r.returncode == 0, r.stderr)
    check("[eff-wait] fresh + low → capped at 120", "CAP=[120]" in r.stdout, r.stdout)
    check("[eff-wait] headroom echoes used%", "USED=[4]" in r.stdout, r.stdout)
    check("[eff-wait] fresh + high(51) → uncapped", "HIGH=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] stale + low → uncapped", "STALE=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] missing file → base wait preserved", "MISSING=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] garbage epoch → uncapped", "GEPOCH=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] garbage used → uncapped", "GUSED=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] VIBE_RATE_READING_MAX_AGE honoured", "KNOBAGE=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] VIBE_RESUME_USED_MAX honoured", "KNOBUSED=[120]" in r.stdout, r.stdout)
    check("[eff-wait] default refuses what the knob allowed", "DEFUSED=[7320]" in r.stdout, r.stdout)
    check("[eff-wait] garbage knob → default behaviour", "GKNOB=[120]" in r.stdout, r.stdout)
    check("[eff-wait] resume_at past → 120 grace", "PAST=[120]" in r.stdout, r.stdout)
    check("[eff-wait] VIBE_RESUME_PAST_GRACE_SECS honoured", "KNOBGRACE=[5]" in r.stdout, r.stdout)
    check("[eff-wait] garbage grace knob → 120 default", "GGRACE=[120]" in r.stdout, r.stdout)
    check("[eff-wait] no resume_at → 1800 default", "NORA=[1800]" in r.stdout, r.stdout)


# ── task_019: regrettable-content guard (secrets/PII pre-commit + pre-push block + audit) ───────


def test_task019_ac1_staged_ghp_token_blocks() -> None:
    """AC1: vibe-content-scan.sh --staged with runtime-built GHP token exits 1, emits BLOCK line."""
    print("\n[task_019 AC1: staged GHP token blocks]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Create a file with a runtime-constructed token (no literal secret in this code)
        token = "ghp_" + ("A" * 36)
        test_file = repo / "secret.txt"
        test_file.write_text(f"My secret is {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_019 AC1] exit 1", r.returncode == 1, r.stderr[:200])
        check("[task_019 AC1] BLOCK in stderr", "BLOCK" in r.stderr, r.stderr)
        check("[task_019 AC1] github-pat rule named", "github-pat" in r.stderr, r.stderr)


def test_task019_ac2_message_private_key_blocks() -> None:
    """AC2: vibe-content-scan.sh --message with runtime-built private key marker exits 1."""
    print("\n[task_019 AC2: message with private key blocks]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()

        # Runtime-constructed private key marker
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text("-----BEGIN " + "OPENSSH PRIVATE KEY-----\n")

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=repo)
        check("[task_019 AC2] exit 1", r.returncode == 1, r.stderr[:200])
        check("[task_019 AC2] BLOCK in stderr", "BLOCK" in r.stderr, r.stderr)
        check("[task_019 AC2] private-key rule named", "private-key" in r.stderr, r.stderr)


def test_task019_ac3_staged_rfc1918_ip_warns() -> None:
    """AC3: vibe-content-scan.sh --staged with RFC1918 IP exits 1, emits WARN line."""
    print("\n[task_019 AC3: staged RFC1918 IP warns]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        test_file = repo / "config.txt"
        test_file.write_text("Server at 192.168.0.99\n")
        run(["git", "add", "config.txt"], cwd=repo)

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_019 AC3] exit 1", r.returncode == 1, r.stderr[:200])
        check("[task_019 AC3] WARN in stderr", "WARN" in r.stderr, r.stderr)
        check("[task_019 AC3] rfc1918-ip rule named", "rfc1918-ip" in r.stderr, r.stderr)


def test_task019_ac4_clean_diff_passes() -> None:
    """AC4: vibe-content-scan.sh --staged on ordinary code exits 0, no findings."""
    print("\n[task_019 AC4: clean diff passes]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        test_file = repo / "code.py"
        test_file.write_text("def hello():\n    print('world')\n")
        run(["git", "add", "code.py"], cwd=repo)

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_019 AC4] exit 0", r.returncode == 0, r.stderr)
        check("[task_019 AC4] no findings", len(r.stderr.strip()) == 0, r.stderr)


def test_task019_ac5_override_bypasses_and_logs() -> None:
    """AC5: VIBE_CONTENT_GUARD=off bypasses scan, exits 0, logs loudly."""
    print("\n[task_019 AC5: override bypasses and logs]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        token = "ghp_" + ("A" * 36)
        test_file = repo / "secret.txt"
        test_file.write_text(f"My secret is {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)

        env = {**os.environ, "VIBE_CONTENT_GUARD": "off"}
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo, env=env)
        check("[task_019 AC5] exit 0", r.returncode == 0, r.stderr)
        check("[task_019 AC5] logs OVERRIDE", "OVERRIDE" in r.stderr, r.stderr)
        check("[task_019 AC5] names rule(s)", "github-pat" in r.stderr, r.stderr)


def test_task019_ac6_allowlist_suppresses_finding() -> None:
    """AC6: .vibe-content-allow suppresses findings matching its regex."""
    print("\n[task_019 AC6: allowlist suppresses]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Create allowlist that matches the IP
        (repo / ".vibe-content-allow").write_text("192\\.168\\.0\\.99\n")

        test_file = repo / "config.txt"
        test_file.write_text("Server at 192.168.0.99\n")
        run(["git", "add", "config.txt"], cwd=repo)

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_019 AC6] exit 0 with allowlist", r.returncode == 0, r.stderr)
        check("[task_019 AC6] no findings", len(r.stderr.strip()) == 0, r.stderr)

        # Without allowlist, same content should fail
        repo2 = Path(td) / "repo2"
        repo2.mkdir()
        run(["git", "init"], cwd=repo2)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo2)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo2)
        run(["git", "config", "user.name", "Test User"], cwd=repo2)

        test_file2 = repo2 / "config.txt"
        test_file2.write_text("Server at 192.168.0.99\n")
        run(["git", "add", "config.txt"], cwd=repo2)

        r2 = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo2)
        check("[task_019 AC6] exit 1 without allowlist", r2.returncode == 1, r2.stderr)


def test_task019_ac7_guard_off_marker_skips_scan() -> None:
    """AC7: .vibe-content-guard-off marker makes scanner exit 0 immediately."""
    print("\n[task_019 AC7: guard-off marker skips]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Create opt-out marker
        (repo / ".vibe-content-guard-off").write_text("")

        token = "ghp_" + ("A" * 36)
        test_file = repo / "secret.txt"
        test_file.write_text(f"My secret is {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_019 AC7] exit 0 with marker", r.returncode == 0, r.stderr)
        check("[task_019 AC7] no stderr output", len(r.stderr.strip()) == 0, r.stderr)


def test_task019_ac8_install_hooks() -> None:
    """AC8: install-claude-extras.sh installs hooks + sets core.hooksPath."""
    print("\n[task_019 AC8: install hooks]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        claude_dir = home / ".claude"

        gitconfig = home / ".gitconfig"

        env = {
            **os.environ,
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(claude_dir),
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "VIBE_EXTRAS_SRC_ROOT": str(REPO / "devcontainer"),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env), cwd=REPO)
        check("[task_019 AC8] install exits 0", r.returncode == 0, r.stderr[:200])

        hooks_dir = claude_dir / "vibe-git-hooks"
        check("[task_019 AC8] hooks dir created", hooks_dir.is_dir(), str(hooks_dir))
        if hooks_dir.is_dir():
            check("[task_019 AC8] scanner executable", (hooks_dir / "vibe-content-scan.sh").is_file(), str(hooks_dir))
            check("[task_019 AC8] pre-commit executable", (hooks_dir / "pre-commit").is_file(), str(hooks_dir))
            check("[task_019 AC8] commit-msg executable", (hooks_dir / "commit-msg").is_file(), str(hooks_dir))
            check("[task_019 AC8] pre-push executable", (hooks_dir / "pre-push").is_file(), str(hooks_dir))

        # Verify git config set
        r2 = run(["git", "config", "--global", "core.hooksPath"], env=env)
        check("[task_019 AC8] core.hooksPath set", str(hooks_dir) in r2.stdout.strip() if r2.stdout.strip() else False, r2.stdout)


def test_task019_ac9_audit_history_finds_deleted_secret() -> None:
    """AC9: vibe audit --history finds secrets deleted in later commits."""
    print("\n[task_019 AC9: audit finds deleted secret]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Commit 1: add secret
        token = "ghp_" + ("A" * 36)
        test_file = repo / "secret.txt"
        test_file.write_text(f"Secret: {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)
        run(["git", "commit", "-m", "Add secret"], cwd=repo)

        # Get the commit sha
        r_sha = run(["git", "rev-parse", "HEAD"], cwd=repo)
        commit_sha = r_sha.stdout.strip()

        # Commit 2: delete secret
        test_file.unlink()
        run(["git", "add", "-u"], cwd=repo)
        run(["git", "commit", "-m", "Remove secret"], cwd=repo)

        # Audit should find the deleted secret
        r = run(["bash", str(VIBE)] + ["audit", "--history"], cwd=repo)
        check("[task_019 AC9] audit exit 1", r.returncode == 1, r.stdout + r.stderr)
        check("[task_019 AC9] BLOCK finding reported", "BLOCK" in r.stdout, r.stdout)
        check("[task_019 AC9] commit sha in output", commit_sha[:8] in r.stdout, r.stdout)


def test_task019_ac10_real_hooks_block_commit() -> None:
    """AC10: Real pre-commit hook blocks git commit of BLOCK content."""
    print("\n[task_019 AC10: real hooks block commit]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        hooks_dir = repo / ".git" / "hooks"

        run(["git", "init"], cwd=repo)

        # Fixture repo: neutralise the machine-global content-guard hooks at

        # local scope so fixture commits (some deliberately carry secrets/PII)

        # are deterministic; hook-exercising tests re-pin their own hooksPath.

        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        # noreply form: the task_021 identity gate in pre-commit must stay
        # quiet here so this test exercises only the content scan.
        run(["git", "config", "user.email", "123+tester@users.noreply.github.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Install hooks locally
        hooks_dir.mkdir(parents=True, exist_ok=True)
        for name in ["pre-commit", "commit-msg", "pre-push"]:
            src = REPO / "devcontainer" / "git-hooks" / name
            dst = hooks_dir / name
            if src.exists():
                import shutil
                shutil.copy2(src, dst)
                dst.chmod(0o755)

        # Copy scanner
        src = REPO / "devcontainer" / "git-hooks" / "vibe-content-scan.sh"
        dst = hooks_dir / "vibe-content-scan.sh"
        if src.exists():
            import shutil
            shutil.copy2(src, dst)
            dst.chmod(0o755)

        # Pin hook discovery to the dir we populated: an environment-level
        # core.hooksPath (e.g. GitHub's hosted runners) would otherwise
        # silently bypass .git/hooks and the hook under test never runs.
        run(["git", "config", "core.hooksPath", str(hooks_dir)], cwd=repo)

        # Try to commit clean content first — should succeed
        test_file = repo / "good.txt"
        test_file.write_text("Hello world\n")
        run(["git", "add", "good.txt"], cwd=repo)
        r_clean = run(["git", "commit", "-m", "Good commit"], cwd=repo)
        check("[task_019 AC10] clean commit succeeds", r_clean.returncode == 0, r_clean.stderr)

        # Try to commit secret — should fail
        token = "ghp_" + ("B" * 36)
        secret_file = repo / "secret.txt"
        secret_file.write_text(f"Token: {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)
        r_bad = run(["git", "commit", "-m", "Add secret"], cwd=repo)
        check("[task_019 AC10] secret commit fails", r_bad.returncode != 0, r_bad.stderr)


def test_task019_ac11_coauthored_by_trailer_clean() -> None:
    """AC11: Commit message with Co-Authored-By trailer scans clean."""
    print("\n[task_019 AC11: Co-Authored-By trailer exempt]")
    with tempfile.TemporaryDirectory() as td:
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text(
            "Fix something\n"
            "\n"
            "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n"
        )

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_019 AC11] exit 0", r.returncode == 0, r.stderr)
        check("[task_019 AC11] no findings", len(r.stderr.strip()) == 0, r.stderr)


def test_task019_ac13_shellcheck_passes() -> None:
    """AC13: code-check.py (shellcheck) passes on new shell files."""
    print("\n[task_019 AC13: shellcheck clean]")
    r = run(["python3", str(REPO / "code-check.py")], cwd=REPO)
    check("[task_019 AC13] shellcheck exits 0", r.returncode == 0, r.stderr[:200])


def test_task019_ac15_content_guard_md_exists() -> None:
    """AC15: content-guard.md fragment exists and names key concepts."""
    print("\n[task_019 AC15: content-guard.md exists]")
    check("[task_019 AC15] file exists", CONTENT_GUARD_MD.is_file(), str(CONTENT_GUARD_MD))
    if CONTENT_GUARD_MD.is_file():
        content = CONTENT_GUARD_MD.read_text()
        check("[task_019 AC15] mentions BLOCK tier", "BLOCK" in content, "")
        check("[task_019 AC15] mentions WARN tier", "WARN" in content, "")
        check("[task_019 AC15] mentions override", "VIBE_CONTENT_GUARD=off" in content, "")
        check("[task_019 AC15] mentions allowlist", ".vibe-content-allow" in content, "")
        check("[task_019 AC15] mentions opt-out", ".vibe-content-guard-off" in content, "")
        check("[task_019 AC15] mentions vibe audit", "vibe audit" in content, "")


def test_workspace_is_the_repo_fragment() -> None:
    """workspace-is-the-repo.md ships and teaches the bind-mount fact + the no-pull rule."""
    print("\n[workspace-is-the-repo.md: /workspace is a bind mount of the launch folder — no git pull for in-container work]")
    check("[ws-repo] fragment exists", WORKSPACE_IS_THE_REPO_MD.is_file(), str(WORKSPACE_IS_THE_REPO_MD))
    if WORKSPACE_IS_THE_REPO_MD.is_file():
        content = WORKSPACE_IS_THE_REPO_MD.read_text()
        check("[ws-repo] names the bind mount", "bind mount" in content, "")
        check("[ws-repo] cites the devcontainer.json workspaceMount source", "localWorkspaceFolder" in content, "")
        check("[ws-repo] states the no-pull rule", "git pull" in content and "Already up to date" in content, "")
        check("[ws-repo] distinguishes relaunch/rebuild from pull", "vibe --rebuild" in content, "")
        check("[ws-repo] covers the vibe-on-vibe symlink case", "readlink ~/bin/vibe" in content, "")
        check("[ws-repo] covers Mac test bridges", "bridge" in content, "")
    # The claim must stay true: devcontainer.json binds the launch folder to /workspace.
    dc = (REPO / "devcontainer" / "devcontainer.json").read_text()
    check("[ws-repo] devcontainer.json still binds ${localWorkspaceFolder} to /workspace",
          "source=${localWorkspaceFolder},target=/workspace,type=bind" in dc, "")
