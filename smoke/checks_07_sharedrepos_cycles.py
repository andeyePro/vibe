from smoke._core import *  # noqa: F401,F403




def test_task017_ac2_shared_repo_ensure_signals_creates_sidecar() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: creates sidecar]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'if shared_repo_ensure_signals "{checkout}"; then '
            f'  if [ -d "{checkout}/.vibe-signals" ]; then echo "SIDECAR_OK"; fi; '
            'else echo "ENSURE_FAILED"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("creates sidecar", "SIDECAR_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_adds_gitignore() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: adds gitignore]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'shared_repo_ensure_signals "{checkout}"; '
            f'if grep -qx ".vibe-signals/" "{checkout}/.gitignore" 2>/dev/null; then '
            'echo "GITIGNORE_OK"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("adds to .gitignore", "GITIGNORE_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_idempotent() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: idempotent]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'shared_repo_ensure_signals "{checkout}"; '
            f'COUNT1=$(grep -c ".vibe-signals/" "{checkout}/.gitignore"); '
            f'shared_repo_ensure_signals "{checkout}"; '
            f'COUNT2=$(grep -c ".vibe-signals/" "{checkout}/.gitignore"); '
            'if [ "$COUNT1" = "$COUNT2" ] && [ "$COUNT1" -eq 1 ]; then '
            'echo "IDEMPOTENT_OK"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("idempotent", "IDEMPOTENT_OK" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_ensure_signals_unwritable_dir() -> None:
    print("\n[task_017 AC2: shared_repo_ensure_signals: fails soft on unwritable dir]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        checkout.chmod(0o000)
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            f'if shared_repo_ensure_signals "{checkout}"; then '
            'echo "SHOULD_FAIL"; else echo "FAILED_SOFT"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("fails soft", "FAILED_SOFT" in r.stdout, r.stdout)
        checkout.chmod(0o755)  # restore for cleanup


def test_task017_ac6_ensure_project_gitignore_has_vibe_signals() -> None:
    print("\n[task_017 AC6: ensure_project_gitignore contains .vibe-signals/]")
    vibe_src = VIBE.read_text()
    # Find the ensure_project_gitignore function
    if "ensure_project_gitignore" in vibe_src:
        check("function exists", True)
        # Check that the managed block includes .vibe-signals/
        if ".vibe-signals/" in vibe_src:
            check(".vibe-signals/ mentioned", True)
        else:
            check(".vibe-signals/ mentioned", False, "not found in vibe script")
    else:
        check("function exists", False, "ensure_project_gitignore not found")


def test_task017_ac1_repos_dispatch_before_parse_vibe_args() -> None:
    print("\n[task_017 AC1: repos dispatch block placement]")
    vibe_src = VIBE.read_text()
    # Find the dispatch blocks
    # Look for the repos_handle_subcommand call within the dispatch
    repos_dispatch_idx = vibe_src.find('repos_handle_subcommand')
    # Look for the parse_vibe_args call (not definition)
    parse_vibe_args_call_idx = vibe_src.rfind('parse_vibe_args "$@"')
    # Make sure we get the actual call, not the definition
    if parse_vibe_args_call_idx > 0:
        # Verify it's not in a comment by checking what comes before
        line_start = vibe_src.rfind('\n', 0, parse_vibe_args_call_idx) + 1
        line_text = vibe_src[line_start:parse_vibe_args_call_idx + 20]
        if line_text.strip().startswith('#'):
            # This is in a comment, search earlier
            parse_vibe_args_call_idx = vibe_src.find('parse_vibe_args "$@"', 1800*50)

    check("repos dispatch found", repos_dispatch_idx != -1)
    check("parse_vibe_args call found", parse_vibe_args_call_idx != -1)
    if repos_dispatch_idx != -1 and parse_vibe_args_call_idx != -1:
        check("repos dispatch before parse_vibe_args", repos_dispatch_idx < parse_vibe_args_call_idx)


def test_task017_delta_scan_m_full_valid_chain() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — M: fully valid chain]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        expected = f"M andeyePro ro andeyePro/andeyePro {checkout}"
        check("emits exactly one M line, correctly shaped",
              r.stdout.strip() == expected, r.stdout)
        check("sidecar mkdir'd as a scan side effect",
              (checkout / ".vibe-signals").is_dir(), "sidecar missing")


def test_task017_delta_scan_n_never_registered_is_silent() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — N: never registered, total silence]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("someorg/somerepo ro\n", encoding="utf-8")
        # No registry file at all — community-contributor case.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("emits exactly 'N <slug>' and NOTHING else",
              r.stdout.strip() == "N someorg/somerepo", r.stdout)


def test_task017_delta_scan_u_unacked_no_sidecar_writes() -> None:
    print("\n[task_017 delta AC3/AC4: shared_repos_scan — U: registered+token but unacked]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        # Deliberately NO repos-acks file — the consent layer is absent.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("emits exactly 'U <slug>'",
              r.stdout.strip() == "U andeyePro/andeyePro", r.stdout)
        check("NO sidecar created for an unacked repo (consent contract)",
              not (checkout / ".vibe-signals").exists(),
              "sidecar was written despite no ack")


def test_task017_delta_scan_b_path_missing() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: registered path missing/.git absent]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        ghost_path = td / "does-not-exist"
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={ghost_path}\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: path missing / not a git checkout",
              r.stdout.strip() == f"B andeyePro/andeyePro path missing or not a git checkout ({ghost_path})",
              r.stdout)


def test_task017_delta_scan_b_token_absent() -> None:
    # AMENDED by the chair at C4 under the spec's sanctioned frozen-test
    # amendment (C4 preamble): AC18 governs from C4 — a missing token for an
    # acked+registered ro repo is a WARNING, not a mount-blocker (an ro bind
    # of a local checkout needs no token; only fetch/push do). The C1-era
    # assertion (B: no token configured) tested the stricter interim
    # behaviour; the scan now mounts, and the no-PAT nudge lives in
    # `vibe repos list` (covered below) and the launch token-export loop.
    print("\n[task_017 delta AC3->AC18: shared_repos_scan — token absent: warn, still mount ro]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # No tokens file at all.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("tokenless repo still mounts (M, ro)",
              r.stdout.strip() == f"M andeyePro ro andeyePro/andeyePro {checkout}",
              r.stdout)
        # And the list surface carries the no-PAT nudge for the same fixture.
        r2 = _source_vibe_call(env, f'cd {shlex.quote(str(ws))} && _repos_list')
        check("list notes the missing PAT",
              "no PAT staged" in r2.stdout and "vibe repos add andeyePro/andeyePro" in r2.stdout,
              r2.stdout)


def test_task017_delta_scan_b_sidecar_unwritable() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: sidecar mkdir fails soft]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # r-x only: .git stays visible/statable, but mkdir of .vibe-signals
        # under checkout fails for lack of the write bit on the parent dir
        # (chmod 000 would ALSO hide .git's existence, misfiring as the
        # "path missing" B reason instead — 555 isolates the sidecar-mkdir
        # failure specifically).
        checkout.chmod(0o555)
        try:
            env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
            r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        finally:
            checkout.chmod(0o755)
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: sidecar unwritable",
              r.stdout.strip() == f"B andeyePro/andeyePro sidecar unwritable ({checkout}/.vibe-signals)",
              r.stdout)


def test_task017_delta_scan_b_reserved_dot_prefix_basename() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: reserved dot-prefixed basename]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, _ = _repos_delta_fixture(td)
        # Valid slug charset, dot-prefixed repo basename — simulates a
        # hand-edited .vibe-repos that slipped past `vibe repos add`'s own
        # rejection of this at registration time.
        (ws / ".vibe-repos").write_text("owner/.hidden ro\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        check("classified B: reserved dot-prefixed name, no registry lookup needed",
              r.stdout.strip() == "B owner/.hidden reserved dot-prefixed name '.hidden'",
              r.stdout)


def test_task017_delta_scan_b_basename_collision() -> None:
    print("\n[task_017 delta AC3: shared_repos_scan — B: basename collision vs an already-mounted repo]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout_a = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text(
            "orgA/widget ro\norgB/widget ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"orgA/widget={checkout_a}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("orgA/widget=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"orgA/widget={ws}\n", encoding="utf-8")
        # orgB/widget is declared only — never registered — but the basename
        # collision check fires before registry lookup, against orgA/widget
        # which DID resolve to a real mount.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'shared_repos_scan {shlex.quote(str(ws))}')
        check("exits 0", r.returncode == 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        check("first repo mounts (M)", lines[0] == f"M widget ro orgA/widget {checkout_a}", r.stdout)
        check("second repo demoted to B: basename collision",
              lines[1] == "B orgB/widget basename 'widget' collides with another declared repo",
              r.stdout)


def test_task017_delta_ack_exact_pair_semantics() -> None:
    print("\n[task_017 delta AC2: shared_repo_acked/ack — exact (slug, workspace) pair only]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'shared_repo_ack "org/repo" "/ws/a"; '
            'if shared_repo_acked "org/repo" "/ws/a"; then echo "RIGHT_PAIR=Y"; else echo "RIGHT_PAIR=N"; fi; '
            'if shared_repo_acked "org/repo" "/ws/b"; then echo "WRONG_WS=Y"; else echo "WRONG_WS=N"; fi; '
            'if shared_repo_acked "org/other" "/ws/a"; then echo "WRONG_SLUG=Y"; else echo "WRONG_SLUG=N"; fi'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("right slug + right workspace -> true", "RIGHT_PAIR=Y" in r.stdout, r.stdout)
        check("right slug + wrong workspace -> false", "WRONG_WS=N" in r.stdout, r.stdout)
        check("wrong slug + right workspace -> false", "WRONG_SLUG=N" in r.stdout, r.stdout)


def test_task017_delta_ack_idempotent_and_chmod_600() -> None:
    print("\n[task_017 delta AC2: shared_repo_ack — idempotent double-ack, chmod 600]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'shared_repo_ack "org/repo" "/ws/a"; '
            'shared_repo_ack "org/repo" "/ws/a"; '
            'shared_repo_ack "org/repo" "/ws/a"; '
            'wc -l < "$HOME/.vibe/repos-acks"; '
            '(stat -c %a "$HOME/.vibe/repos-acks" 2>/dev/null || stat -f %Lp "$HOME/.vibe/repos-acks")'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        out_lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
        check("three acks of the same pair -> exactly one line",
              len(out_lines) >= 2 and out_lines[0] == "1", r.stdout)
        check("repos-acks is chmod 600",
              len(out_lines) >= 2 and out_lines[1] == "600", r.stdout)


def test_task017_delta_fixedstring_repos_registry_lookup_regex_danger() -> None:
    print("\n[task_017 delta security-review regression: repos_registry_lookup is fixed-string, not regex]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        vibe_dir = home / ".vibe"; vibe_dir.mkdir()
        (vibe_dir / "repos").write_text("myorg/secret=/real/registered/path\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'GOOD=$(repos_registry_lookup "myorg/secret"); '
            'BAD=$(repos_registry_lookup "myor./secret"); '
            'echo "GOOD=[$GOOD]"; echo "BAD=[$BAD]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("exact slug resolves", "GOOD=[/real/registered/path]" in r.stdout, r.stdout)
        check("regex-dangerous-but-charset-valid slug does NOT resolve the other entry",
              "BAD=[]" in r.stdout, r.stdout)


def test_task017_delta_fixedstring_lookup_token_regex_danger() -> None:
    print("\n[task_017 delta security-review regression: lookup_token is fixed-string, not regex]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"; home.mkdir()
        vibe_dir = home / ".vibe"; vibe_dir.mkdir()
        (vibe_dir / "tokens").write_text("myorg/secret=ghp_thetoken\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config"}
        snippet = (
            'GOOD=$(lookup_token "myorg/secret"); '
            'BAD=$(lookup_token "myor./secret"); '
            'echo "GOOD=[$GOOD]"; echo "BAD=[$BAD]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("exact slug resolves the token", "GOOD=[ghp_thetoken]" in r.stdout, r.stdout)
        check("regex-dangerous-but-charset-valid slug does NOT resolve the token",
              "BAD=[]" in r.stdout, r.stdout)


def test_task017_delta_fixedstring_decl_remove_prefix_discipline() -> None:
    print("\n[task_017 delta security-review regression: _vibe_repos_decl_remove is prefix-safe]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        decl.write_text("a/b ro\na/bb ro\naxb ro\n", encoding="utf-8")
        env = {**os.environ, "VIBE_CONFIG": f"{td}/no-config"}
        r = _source_vibe_call(env, f'_vibe_repos_decl_remove {shlex.quote(str(decl))} "a/b"')
        check("exits 0", r.returncode == 0, r.stderr)
        remaining = decl.read_text().splitlines()
        check("removes the exact 'a/b' line", "a/b ro" not in remaining, remaining)
        check("does NOT remove 'a/bb' (longer slug sharing the prefix)",
              "a/bb ro" in remaining, remaining)
        check("does NOT remove 'axb' (no slash, shares no real prefix)",
              "axb ro" in remaining, remaining)


def test_task017_delta_override_config_two_binds_when_acked() -> None:
    print("\n[task_017 delta AC3: _build_override_config — acked repo contributes code+sidecar binds]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        # Blank OP MCP creds (leak in from the real container env) and disable
        # brain2/zotero so the only mounts in play are the shared-repo binds
        # under test — mirrors test_build_override_config_brain2_and_zotero's
        # gating discipline.
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        check("override generated under HOME/.vibe/run",
              out.startswith(str(home / ".vibe" / "run")), out)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        mounts = [m for m in cfg.get("mounts", []) if isinstance(m, dict)]
        code_mount = next((m for m in mounts if m.get("target") == "/repos/andeyePro"), None)
        sidecar_mount = next((m for m in mounts if m.get("target") == "/repos/.signals/andeyePro"), None)
        check("code bind at /repos/<name> present", code_mount is not None, str(mounts))
        if code_mount:
            check("code bind is readonly", code_mount.get("readonly") is True, str(code_mount))
            check("code bind source is the registered checkout",
                  code_mount.get("source") == str(checkout), str(code_mount))
        check("sidecar bind at /repos/.signals/<name> present", sidecar_mount is not None, str(mounts))
        if sidecar_mount:
            check("sidecar bind is rw (no readonly key)",
                  "readonly" not in sidecar_mount, str(sidecar_mount))
            check("sidecar bind source is <checkout>/.vibe-signals",
                  sidecar_mount.get("source") == str(checkout / ".vibe-signals"), str(sidecar_mount))


def test_task017_delta_override_config_no_binds_when_unacked() -> None:
    print("\n[task_017 delta AC3: _build_override_config — unacked repo contributes NEITHER bind]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        # No repos-acks file — unacked.
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        tgts = [m.get("target") for m in cfg.get("mounts", []) if isinstance(m, dict)]
        check("neither code nor sidecar bind present when unacked",
              "/repos/andeyePro" not in tgts and "/repos/.signals/andeyePro" not in tgts,
              str(tgts))


def test_task017_delta_manifest_lines_mixed_tags() -> None:
    print("\n[task_017 delta AC5: shared_repos_manifest_lines — M+B+N+U mix emits only M lines]")
    scan_output = "\n".join([
        "M repoA ro orgA/repoA /path/to/a",
        "B orgB/repoB path missing or not a git checkout (/nowhere)",
        "N orgC/repoC",
        "U orgD/repoD",
        "M repoE rw orgE/repoE /path/to/e",
    ])
    r = _source_vibe_call({}, f'shared_repos_manifest_lines {shlex.quote(scan_output)}')
    check("exits 0", r.returncode == 0, r.stderr)
    expected = "repoA ro orgA/repoA\nrepoE rw orgE/repoE"
    check("emits exactly the M repos' 'name mode slug' lines, in order",
          r.stdout.strip() == expected, r.stdout)


def test_task017_delta_header_case_arms_present() -> None:
    print("\n[task_017 delta AC4: launch header — M/B/N/U case arms, N silent, U names the remedy]")
    vibe_src = VIBE.read_text()
    start = vibe_src.find('if [ -n "$SHARED_REPOS_SCAN" ]; then')
    end = vibe_src.find('UP_BASE_ARGS=(', start) if start != -1 else -1
    check("header block located between the scan gate and UP_BASE_ARGS", start != -1 and end != -1 and end > start)
    block = vibe_src[start:end] if (start != -1 and end != -1 and end > start) else ""
    check("M case arm present (mounted -> ◆ line)", "M\\ *)" in block and "◆ shared repo:" in block, block[:500])
    check("B case arm present (broken -> ⚠ line)", "B\\ *)" in block and "BROKEN:" in block, block[:500])
    check("N case arm is a no-op comment (deliberate silence)",
          "N\\ *) ;;" in block, block[:500])
    check("U case arm present and loud, naming the remedy",
          "U\\ *)" in block and "not authorised" in block and "vibe repos add" in block,
          block[:500])


# ── task_017 AC8-AC11: rw intent + single-writer lock (Cycle 2) ──────────────
# Haiku Tester. Lock helpers take a bare <checkout> path and are otherwise
# HOME-independent, so most of these skip the full _repos_delta_fixture and
# just use a bare tempdir. Real processes (backgrounded `sleep`) stand in for
# "another launcher" per the task_016 watchdog-test precedent — never timing
# alone: every negative samples a live PID or asserts on a persisted meta
# file, and every positive is checked against evidence a broken implementation
# could not produce by accident.

def test_task017_c2_lock_acquire_writes_meta_and_holder_reads_digits() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — success writes meta; holder reads digits-only]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA 424242; echo "ACQ=[$?]"; '
            f'shared_repo_lock_holder {shlex.quote(str(checkout))}'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("acquire returns 0 (acquired)", "ACQ=[0]" in r.stdout, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        holder_line = lines[-1] if lines else ""
        check("holder echoes 'projA 424242 <digits-only-epoch>'",
              re.match(r'^projA 424242 \d+$', holder_line) is not None, holder_line)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("meta file created", meta.is_file(), "meta missing")
        if meta.is_file():
            text = meta.read_text()
            check("meta: project=projA", "project=projA" in text, text)
            check("meta: pid=424242", "pid=424242" in text, text)
            check("meta: since=<digits>", re.search(r'(?m)^since=\d+$', text) is not None, text)


def test_task017_c2_lock_contend_live_holder_refused_and_not_reclaimed() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — contend: different project, live holder pid -> refused, holder named, lock untouched]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            'sleep 60 & holder_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} holderProj "$holder_pid" >/dev/null; '
            f'out=$(shared_repo_lock_acquire {shlex.quote(str(checkout))} otherProj "$$"); rc=$?; '
            'echo "RC=[$rc]"; '
            'echo "HOLDEROUT=[$out]"; '
            'kill "$holder_pid" 2>/dev/null; wait "$holder_pid" 2>/dev/null; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("contended acquire refused (rc=1)", "RC=[1]" in r.stdout, r.stdout)
        check("refusal echoes the ORIGINAL holder's details (holderProj, not otherProj)",
              re.search(r'HOLDEROUT=\[holderProj \d+ \d+\]', r.stdout) is not None, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock meta still names the original live holder (never reclaimed while pid alive)",
              meta.is_file() and "project=holderProj" in meta.read_text(), meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_stale_reclaim_dead_holder_succeeds() -> None:
    print("\n[task_017 AC9: shared_repo_lock_acquire — stale-reclaim: dead holder pid reclaimed exactly once]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            '(sleep 0.2) & dead_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} oldProj "$dead_pid" >/dev/null; echo "SETUP_RC=[$?]"; '
            'wait "$dead_pid" 2>/dev/null; '
            # Confirm the pid is provably dead before we rely on that in the assertion.
            'if kill -0 "$dead_pid" 2>/dev/null; then echo "STILL_ALIVE=[yes]"; else echo "STILL_ALIVE=[no]"; fi; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} newProj "$$"; echo "RECLAIM_RC=[$?]"; '
            f'shared_repo_lock_holder {shlex.quote(str(checkout))}; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("initial acquire (as the soon-to-die holder) succeeded", "SETUP_RC=[0]" in r.stdout, r.stdout)
        check("holder pid is provably dead before reclaim", "STILL_ALIVE=[no]" in r.stdout, r.stdout)
        check("reclaim by a new project/pid succeeds (rc=0)", "RECLAIM_RC=[0]" in r.stdout, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        check("post-reclaim holder is the NEW project/pid, not the dead one",
              re.match(r'^newProj \d+ \d+$', lines[-1]) is not None, lines[-1] if lines else "")


def test_task017_c2_lock_release_matching_owner_removes_lock() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — matching project+pid removes the lock]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$" >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} projA "$$"; echo "REL=[$?]"'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release returns 0", "REL=[0]" in r.stdout, r.stdout)
        lock_dir = checkout / ".vibe-signals" / "rw-lock.d"
        check("lock directory is gone after a matching release", not lock_dir.exists(), str(lock_dir))


def test_task017_c2_lock_release_wrong_project_refused_intact() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — wrong project refused, lock intact]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$" >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} wrongProj "$$"; echo "REL=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release with wrong project refused (rc=1)", "REL=[1]" in r.stdout, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock left intact (still projA)", meta.is_file() and "project=projA" in meta.read_text(),
              meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_release_wrong_pid_refused_intact() -> None:
    print("\n[task_017 AC9: shared_repo_lock_release — wrong pid refused, lock intact]")
    with tempfile.TemporaryDirectory() as td:
        checkout = Path(td) / "checkout"
        checkout.mkdir()
        snippet = (
            'set +e; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA 999999 >/dev/null; '
            f'shared_repo_lock_release {shlex.quote(str(checkout))} projA "$$"; echo "REL=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("release with wrong pid refused (rc=1)", "REL=[1]" in r.stdout, r.stdout)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("lock left intact (still pid=999999)", meta.is_file() and "pid=999999" in meta.read_text(),
              meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_lock_torn_meta_never_stolen_no_crash() -> None:
    print("\n[task_017 AC9: torn meta (empty/garbage pid) — never stolen, never crashes]")
    for label, meta_body in (
        ("empty pid", "project=ghost\npid=\nsince=\n"),
        ("garbage pid", "project=ghost\npid=notanumber\nsince=notanumber\n"),
    ):
        with tempfile.TemporaryDirectory() as td:
            checkout = Path(td) / "checkout"
            lockdir = checkout / ".vibe-signals" / "rw-lock.d"
            lockdir.mkdir(parents=True)
            (lockdir / "meta").write_text(meta_body, encoding="utf-8")
            snippet = (
                'set +e; '
                f'shared_repo_lock_acquire {shlex.quote(str(checkout))} projA "$$"; echo "RC=[$?]"; '
                'set -e'
            )
            r = _source_vibe_call({}, snippet)
            check(f"[{label}] script exits 0 (no crash)", r.returncode == 0, r.stderr)
            check(f"[{label}] acquire refused rather than stealing a torn lock (rc=1)",
                  "RC=[1]" in r.stdout, r.stdout)
            check(f"[{label}] meta left byte-for-byte untouched",
                  (lockdir / "meta").read_text() == meta_body, (lockdir / "meta").read_text())


def test_task017_c2_rw_free_lock_grants_rw() -> None:
    print("\n[task_017 AC8: rw declared + free lock + apply_rw_intents run -> scan emits 'M <name> rw ...']")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projA"}
        # Read the meta file INSIDE the same script, before it exits — a real
        # launch registers lock release as an EXIT hook (AC10), so checking
        # the filesystem from Python after the process has already exited
        # would only ever see the lock gone, regardless of whether it was
        # ever correctly acquired.
        meta_path = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}; '
            f'echo "META=[$(cat {shlex.quote(str(meta_path))} 2>/dev/null | tr "\\n" ";")]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        m_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("M ")]
        expected = f"M andeyePro rw andeyePro/andeyePro {checkout}"
        check("scan emits rw bindmode when the lock is free", m_lines == [expected], r.stdout)
        meta_m = re.search(r"META=\[(.*)\]", r.stdout)
        meta_line = meta_m.group(1) if meta_m else ""
        check("lock acquired and held by the requesting project (read while still held, pre-exit-release)",
              "project=projA;" in meta_line and "pid=" in meta_line, meta_line)


def test_task017_c2_rw_contended_falls_back_ro_with_warning() -> None:
    print("\n[task_017 AC8: rw declared, lock held by another LIVE process -> scan falls back to ro + named contention warning]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projB"}
        snippet = (
            'set +e; '
            'sleep 60 & holder_pid=$!; '
            f'shared_repo_lock_acquire {shlex.quote(str(checkout))} otherProj "$holder_pid" >/dev/null; '
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projB "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}; '
            'echo "WARNINGS=[${VIBE_SHARED_REPO_WARNINGS[*]}]"; '
            'kill "$holder_pid" 2>/dev/null; wait "$holder_pid" 2>/dev/null; '
            'set -e'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        m_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("M ")]
        check("scan falls back to ro bindmode (lock held elsewhere)",
              m_lines == [f"M andeyePro ro andeyePro/andeyePro {checkout}"], r.stdout)
        warn_line = next((ln for ln in r.stdout.splitlines() if ln.startswith("WARNINGS=[")), "")
        check("contention warning names the holder project ('otherProj')", "otherProj" in warn_line, warn_line)
        check("contention warning names the repo slug", "andeyePro/andeyePro" in warn_line, warn_line)
        meta = checkout / ".vibe-signals" / "rw-lock.d" / "meta"
        check("original holder's lock is untouched by the refused contender",
              meta.is_file() and "project=otherProj" in meta.read_text(), meta.read_text() if meta.is_file() else "meta missing")


def test_task017_c2_ro_declared_never_acquires_lock() -> None:
    print("\n[task_017 AC8: a declared-ro repo never touches the lock (no lock dir created)]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro ro\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config", "PROJECT_NAME": "projA"}
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'shared_repos_scan {shlex.quote(str(ws))}'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        expected = f"M andeyePro ro andeyePro/andeyePro {checkout}"
        check("scan reports ro for a declared-ro repo", r.stdout.strip() == expected, r.stdout)
        lock_dir = checkout / ".vibe-signals" / "rw-lock.d"
        check("lock directory was NEVER created for a ro-declared repo (a broken impl that always "
              "locks would fail this)", not lock_dir.exists(), str(lock_dir))


def test_task017_c2_declaration_set_mode_flips_ro_to_rw() -> None:
    print("\n[task_017 AC8: shared_repo_declaration_set_mode — flips ro->rw in-place, other lines untouched (vibe repos add --rw, helper level)]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        decl.write_text("andeyePro/andeyePro ro\n# a comment\nother/repo ro\n", encoding="utf-8")
        r = _source_vibe_call(
            {}, f'shared_repo_declaration_set_mode {shlex.quote(str(decl))} andeyePro/andeyePro rw; echo "RC=[$?]"')
        check("exits 0", r.returncode == 0, r.stderr)
        check("helper returns 0", "RC=[0]" in r.stdout, r.stdout)
        text = decl.read_text()
        check("target slug flipped to rw", "andeyePro/andeyePro rw" in text, text)
        check("target slug's old ro line is gone", "andeyePro/andeyePro ro" not in text, text)
        check("comment line preserved verbatim", "# a comment" in text, text)
        check("unrelated declaration untouched", "other/repo ro" in text, text)


def test_task017_c2_declaration_set_mode_rejects_bad_mode() -> None:
    print("\n[task_017 AC8: shared_repo_declaration_set_mode — rejects an invalid mode, no file created]")
    with tempfile.TemporaryDirectory() as td:
        decl = Path(td) / ".vibe-repos"
        snippet = (
            'set +e; '
            f'shared_repo_declaration_set_mode {shlex.quote(str(decl))} foo/bar bogus; echo "RC=[$?]"; '
            'set -e'
        )
        r = _source_vibe_call({}, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("helper refuses an invalid mode (rc=1)", "RC=[1]" in r.stdout, r.stdout)
        check("no file created on rejection", not decl.exists(), "file was unexpectedly created")


def test_task017_c2_exit_dispatcher_survives_refusing_hook() -> None:
    print("\n[task_017 AC10: exit dispatcher — a refusing FIRST hook does not suppress later hooks]")
    with tempfile.TemporaryDirectory() as td:
        ev2 = Path(td) / "ev2"
        ev3 = Path(td) / "ev3"
        snippet = (
            'vibe_exit_hook_add "false"; '
            f'vibe_exit_hook_add "touch {shlex.quote(str(ev2))}"; '
            f'vibe_exit_hook_add "touch {shlex.quote(str(ev3))}"'
        )
        r = _source_vibe_call({}, snippet)
        check("subshell exits 0 despite a refusing first hook (set -euo pipefail survives)",
              r.returncode == 0, r.stderr)
        check("second-registered hook ran (evidence file exists)", ev2.exists(), "ev2 missing")
        check("third-registered hook ran (evidence file exists)", ev3.exists(), "ev3 missing")


def test_task017_c2_trap_dash_p_shows_single_dispatcher() -> None:
    print("\n[task_017 AC10: trap -p EXIT shows exactly the vibe_on_exit dispatcher]")
    r = _source_vibe_call({}, 'vibe_exit_hook_add "true"; trap -p EXIT')
    check("exits 0", r.returncode == 0, r.stderr)
    check("trap -p EXIT names vibe_on_exit as the (sole) EXIT handler",
          "vibe_on_exit" in r.stdout and "EXIT" in r.stdout, r.stdout)


def test_task017_c2_no_raw_exit_trap_outside_dispatcher() -> None:
    print("\n[task_017 AC10: exactly one literal 'trap ... EXIT' in the whole script (the dispatcher installer)]")
    src = VIBE.read_text()
    lines = src.splitlines()
    trap_exit_re = re.compile(r'^\s*trap\s+\S.*\bEXIT\b')
    matches = [ln for ln in lines if trap_exit_re.match(ln)]
    check("exactly one literal EXIT-trap installation site in the script",
          len(matches) == 1, str(matches))
    if matches:
        check("that one site is 'trap vibe_on_exit EXIT' (inside vibe_exit_hook_add, the sanctioned installer)",
              matches[0].strip() == 'trap vibe_on_exit EXIT', matches[0])
    # INT/TERM traps (e.g. the /learn tempfile cleanup) are a separate slot and
    # must NOT also claim EXIT.
    int_term = [ln for ln in lines if re.match(r'^\s*trap\s+\S.*\bINT\b.*\bTERM\b', ln)
                or re.match(r'^\s*trap\s+\S.*\bTERM\b.*\bINT\b', ln)]
    check("at least one dedicated INT/TERM trap exists (separate from the EXIT dispatcher)",
          len(int_term) >= 1, str(int_term))
    check("no INT/TERM trap line also mentions EXIT",
          all("EXIT" not in ln for ln in int_term), str(int_term))


def test_task017_c2_clipboard_and_learn_tempfile_migrated_to_hooks() -> None:
    print("\n[task_017 AC10: Darwin clipboard-flush body and /learn tempfile cleanup both migrated into vibe_exit_hook_add registrations]")
    src = VIBE.read_text()
    clip_hook_open = "vibe_exit_hook_add 'if [ -s \"$CLIP\" ]"
    check("clipboard-flush body is registered via vibe_exit_hook_add (not a raw trap)",
          clip_hook_open in src, "expected substring not found")
    check("clipboard-flush body text is intact: drains to pbcopy",
          'pbcopy < "$CLIP"' in src, "substring not found")
    check("clipboard-flush body text is intact: reaps the watcher",
          'kill "$WATCHER_PID" 2>/dev/null || true' in src, "substring not found")
    learn_hook = 'vibe_exit_hook_add "rm -f \'$msg_tmp\'"'
    check("vibe learn's tempfile cleanup is ALSO registered via vibe_exit_hook_add",
          learn_hook in src, "expected substring not found")
    check("vibe learn keeps a direct INT/TERM trap for the same tempfile (dispatcher owns only EXIT)",
          'trap "rm -f \'$msg_tmp\'" INT TERM' in src, "substring not found")


def test_task017_c2_mode_coherence_rw_manifest_and_override_agree() -> None:
    print("\n[task_017 mode coherence: rw granted -> manifest says rw AND override JSON code bind has readonly absent while sidecar stays rw]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = _repos_delta_fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        (home / ".vibe" / "repos").write_text(f"andeyePro/andeyePro={checkout}\n", encoding="utf-8")
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        (home / ".vibe" / "repos-acks").write_text(f"andeyePro/andeyePro={ws}\n", encoding="utf-8")
        env = {**os.environ,
               "OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": "",
               "HOME": str(home), "VIBE_CONFIG": f"{td}/no-config",
               "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off",
               "PROJECT_NAME": "projA"}
        snippet = (
            f'shared_repos_apply_rw_intents {shlex.quote(str(ws / ".vibe-repos"))} projA "$$"; '
            f'echo "MANIFEST=[$(shared_repos_manifest_lines "$(shared_repos_scan {shlex.quote(str(ws))})")]"; '
            f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"'
        )
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        manifest_m = re.search(r"MANIFEST=\[(.*)\]", r.stdout)
        manifest = manifest_m.group(1) if manifest_m else ""
        check("manifest line reports rw for the granted repo",
              manifest.strip() == "andeyePro rw andeyePro/andeyePro", r.stdout)
        out = _read_override_out(r)
        cfg = json.loads(Path(out).read_text()) if out and Path(out).exists() else {"mounts": []}
        mounts = [m for m in cfg.get("mounts", []) if isinstance(m, dict)]
        code_mount = next((m for m in mounts if m.get("target") == "/repos/andeyePro"), None)
        sidecar_mount = next((m for m in mounts if m.get("target") == "/repos/.signals/andeyePro"), None)
        check("code bind present", code_mount is not None, str(mounts))
        if code_mount:
            check("code bind's readonly key is ABSENT (rw granted agrees with the manifest)",
                  "readonly" not in code_mount, str(code_mount))
        check("sidecar bind present and rw regardless (no readonly key)",
              sidecar_mount is not None and "readonly" not in sidecar_mount, str(sidecar_mount))


def test_task017_c2_repos_add_rw_flag_cli_level() -> None:
    print("\n[task_017 AC8: vibe repos add --rw at the CLI level — fresh-add-rw, upgrade-in-place, no-silent-downgrade, position-agnostic]")

    def fixture(td: Path):
        home, ws, checkout = _repos_delta_fixture(td)
        # Pre-seed the token so _repos_add never reaches the interactive
        # setup_token flow; every call below passes the path arg so the
        # read -rp prompt is never hit either.
        (home / ".vibe" / "tokens").write_text("andeyePro/andeyePro=ghp_faketoken\n", encoding="utf-8")
        return home, ws, checkout

    def run_add(home: Path, ws: Path, args: str):
        # _repos_add ends in `exit 0` (and exits non-zero on validation
        # failure), so run it in a subshell and capture its status; cd into
        # the temp project first — the declaration path comes from pwd -P.
        env = {**os.environ, "HOME": str(home), "VIBE_CONFIG": "/tmp/vibe-no-config-for-tests"}
        snippet = (
            'set +e; '
            f'cd {shlex.quote(str(ws))} && ( _repos_add {args} ) >/dev/null 2>&1; echo "RC=[$?]"; '
            'set -e'
        )
        return _source_vibe_call(env, snippet)

    # 1. Fresh add with --rw BEFORE the slug -> declaration lands as rw.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'--rw andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[fresh-add-rw] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[fresh-add-rw] fresh declaration line is 'slug rw'",
              "andeyePro/andeyePro rw" in decl, decl)
        check("[fresh-add-rw] no ro line was written",
              "andeyePro/andeyePro ro" not in decl, decl)

    # 2. Upgrade in place: slug already declared ro; add --rw flips it to rw
    #    on the SAME line (no duplicate entry).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        (ws / ".vibe-repos").write_text("# keep me\nandeyePro/andeyePro ro\nother/repo ro\n", encoding="utf-8")
        r = run_add(home, ws, f'--rw andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[upgrade] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text()
        check("[upgrade] existing declaration upgraded to rw in place",
              "andeyePro/andeyePro rw" in decl and "andeyePro/andeyePro ro" not in decl, decl)
        check("[upgrade] exactly one line for the slug (no duplicate append)",
              decl.count("andeyePro/andeyePro") == 1, decl)
        check("[upgrade] comment and unrelated declaration untouched",
              "# keep me" in decl and "other/repo ro" in decl, decl)

    # 3. No silent downgrade: slug already declared rw; plain add (no --rw)
    #    must leave the rw intent alone. A broken implementation that always
    #    rewrites the line with its parsed default 'ro' fails this.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        (ws / ".vibe-repos").write_text("andeyePro/andeyePro rw\n", encoding="utf-8")
        r = run_add(home, ws, f'andeyePro/andeyePro {shlex.quote(str(checkout))}')
        check("[no-downgrade] exits 0", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text()
        check("[no-downgrade] plain re-add does NOT downgrade an existing rw declaration",
              "andeyePro/andeyePro rw" in decl and "andeyePro/andeyePro ro" not in decl, decl)

    # 4. Position-agnostic: --rw AFTER the slug works too (trailing and
    #    slug --rw path both parse).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'andeyePro/andeyePro {shlex.quote(str(checkout))} --rw')
        check("[position] exits 0 with trailing --rw", r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[position] trailing --rw still declares rw",
              "andeyePro/andeyePro rw" in decl, decl)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        home, ws, checkout = fixture(td)
        r = run_add(home, ws, f'andeyePro/andeyePro --rw {shlex.quote(str(checkout))}')
        check("[position] exits 0 with mid-position --rw (slug --rw path)",
              r.returncode == 0 and "RC=[0]" in r.stdout, r.stdout + r.stderr)
        decl = (ws / ".vibe-repos").read_text() if (ws / ".vibe-repos").is_file() else ""
        check("[position] mid-position --rw still declares rw",
              "andeyePro/andeyePro rw" in decl, decl)

    check("[usage] usage line documents the --rw flag",
          "vibe repos add [--rw] <owner/repo> [path]" in VIBE.read_text(), "usage string not found")


# ── task_017 AC12-AC15: Cycle 3 tests (claim/handoff, /repo command, fragment) ─
# Append-only per /vs rules: C1/C2 tests above are frozen. Everything below is
# new for Cycle 3; the C1/C2 test bodies above are untouched.

def test_task017_c3_repo_md_shape() -> None:
    """AC12: /repo command file shape, mirroring the vss.md file-shape tests
    (frontmatter, description, documented subcommands, host/container
    boundary guidance, claim file shape, relaunch notes) plus a regression
    guard that the file never instructs writing INTO ~/.vibe from inside the
    container (only ever describes it as out of reach)."""
    print("\n[task_017 AC12: /repo command file shape]")
    check("[c3-repo-md] repo.md exists", REPO_MD.exists(), str(REPO_MD))
    if not REPO_MD.exists():
        return
    content = REPO_MD.read_text()

    check("[c3-repo-md] frontmatter open delimiter", content.startswith("---\n"), "first 4 chars")
    check("[c3-repo-md] description: in frontmatter",
          "description:" in content.split("---\n")[1] if "---\n" in content else False, "")

    check("[c3-repo-md] documents /repo add", "/repo add <owner/repo>" in content, "")
    check("[c3-repo-md] documents /repo remove", "/repo remove <owner/repo>" in content, "")
    check("[c3-repo-md] documents /repo claim", "/repo claim <name>" in content, "")

    check("[c3-repo-md] states the container cannot touch ~/.vibe on the host",
          "cannot touch `~/.vibe` on the host" in content, "exact phrase not found")

    check("[c3-repo-md] claim documents the rw-request path under the signals sidecar",
          "${VIBE_REPOS_DIR:-/repos}/.signals/<name>/rw-request" in content, "")
    check("[c3-repo-md] claim documents KEY=VALUE project= field",
          "project=<this project's name>" in content, "")
    check("[c3-repo-md] claim documents KEY=VALUE since= field",
          "since=<epoch seconds" in content, "")

    check("[c3-repo-md] relaunch note present for add",
          content.count("Relaunch required") >= 2, f"count={content.count('Relaunch required')}")

    # Regression guard: every mention of ~/.vibe must sit in a negation
    # context (out-of-reach / cannot / untouched) — never an instruction to
    # write there from inside the container. Windowed check survives line
    # wraps in the source markdown.
    flat = re.sub(r"\s+", " ", content)
    negation_cues = ("cannot", "can't", "untouched", "out of reach", "does not", "host-only")
    bad_windows = []
    for m in re.finditer(r"~/\.vibe", flat):
        window = flat[max(0, m.start() - 80): m.end() + 80].lower()
        if not any(cue in window for cue in negation_cues):
            bad_windows.append(window)
    check("[c3-repo-md] no ~/.vibe mention lacks a negation cue (never instructs writing there from the container)",
          not bad_windows, str(bad_windows))


def test_task017_c3_statusline_structural_unchanged() -> None:
    """AC13: the settings heredoc still parses as JSON, and the
    forceLoginMethod/defaultMode/guard-bash.sh/guard-fs.sh entries the C1
    era AC4-style structural tests assert on are all still present and
    unchanged by the AC13 statusLine edit. Inline re-assertion (does not
    touch the frozen test_vibe_statusline or test_task009_settings_json_updated
    functions above)."""
    print("\n[task_017 AC13: settings heredoc structural regressions unchanged]")
    config, cmd = _extract_statusline()
    check("[c3-status-struct] heredoc still parses as valid JSON", bool(config), "config empty/unparseable")
    if not config:
        return
    check("[c3-status-struct] forceLoginMethod is claudeai",
          config.get("forceLoginMethod") == "claudeai", str(config.get("forceLoginMethod")))
    check("[c3-status-struct] permissions.defaultMode is bypassPermissions",
          config.get("permissions", {}).get("defaultMode") == "bypassPermissions",
          str(config.get("permissions")))
    pretool = config.get("hooks", {}).get("PreToolUse", [])
    bash_matcher = next((h for h in pretool if h.get("matcher") == "Bash"), None)
    fs_matcher = next((h for h in pretool if h.get("matcher") == "Write|Edit|MultiEdit"), None)
    check("[c3-status-struct] guard-bash.sh hook present under the Bash matcher",
          bash_matcher is not None
          and any("guard-bash.sh" in h.get("command", "") for h in bash_matcher.get("hooks", [])),
          str(bash_matcher))
    check("[c3-status-struct] guard-fs.sh hook present under the Write|Edit|MultiEdit matcher",
          fs_matcher is not None
          and any("guard-fs.sh" in h.get("command", "") for h in fs_matcher.get("hooks", [])),
          str(fs_matcher))
    check("[c3-status-struct] statusLine.type is still 'command'",
          config.get("statusLine", {}).get("type") == "command", "")
    check("[c3-status-struct] command still reads model.display_name",
          ".model.display_name" in cmd, "")
    check("[c3-status-struct] the best-effort bell escape is present in the command source",
          "\\a" in cmd, cmd[:200])


def test_task017_c3_statusline_no_signals_byte_identical() -> None:
    """AC13(a): with VIBE_REPOS_DIR pointed at an empty temp dir (no .signals
    tree at all), output is byte-identical to the frozen fixtures' exact
    expectations. Spot-checks two of test_vibe_statusline's fixtures
    (Fable-full and empty-JSON) without touching that frozen function."""
    print("\n[task_017 AC13(a): no signals tree -> byte-identical to frozen fixtures]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-a] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "VIBE_REPOS_DIR": td, "VIBE_PROJECT_NAME": "irrelevant-project"}
        fixtures = [
            ('{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":42.7},'
             '"rate_limits":{"five_hour":{"used_percentage":63}}}',
             "F · vibe · ctx 42% · 5h 63%"),
            ("{}", "? · vibe"),
        ]
        for stdin_json, expected in fixtures:
            r = subprocess.run(["sh", "-c", cmd], input=stdin_json, env=env,
                                capture_output=True, text=True, timeout=15)
            check(f"[c3-status-a] {expected!r} byte-identical with no .signals tree present",
                  r.returncode == 0 and r.stdout == expected,
                  f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")


def test_task017_c3_statusline_rw_segment_present_when_holder_and_requested() -> None:
    """AC13(b): this session holds the lock (meta project= matches
    VIBE_PROJECT_NAME) AND a rw-request exists -> the segment appears,
    naming the requester."""
    print("\n[task_017 AC13(b): holder + pending request -> rw segment shown]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-b] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="thisproject", requester_project="moneyandeye")
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-b] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-b] output contains the rw warning segment naming the requester",
              " · ⚠ rw:moneyandeye" in r.stdout, r.stdout)
        check("[c3-status-b] output is exactly the base segment plus the rw segment (no extra drift)",
              r.stdout == "O · vibe · ⚠ rw:moneyandeye", r.stdout)


def test_task017_c3_statusline_rw_segment_absent_when_not_holder() -> None:
    """AC13(c): a rw-request exists but the lock's meta names a DIFFERENT
    holder project (not us) -> segment ABSENT. We're not the holder, so
    there's nothing for our statusLine to surrender."""
    print("\n[task_017 AC13(c): request present but WE are not the holder -> segment absent]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-c] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="otherproject", requester_project="moneyandeye")
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-c] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-c] no rw warning segment leaks when we are not the lock holder",
              "⚠ rw:" not in r.stdout, r.stdout)
        check("[c3-status-c] output is exactly the base segment, unchanged",
              r.stdout == "O · vibe", r.stdout)


def test_task017_c3_statusline_rw_segment_absent_when_no_request() -> None:
    """AC13(d): lock held by us but NO rw-request file exists -> segment
    absent (nothing to surface)."""
    print("\n[task_017 AC13(d): we hold the lock but no request exists -> segment absent]")
    _, cmd = _extract_statusline()
    if not cmd:
        check("[c3-status-d] statusLine command extracted", False, "heredoc marker not found")
        return
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write_signals_fixture(td_path / ".signals", "andeyePro",
                                holder_project="thisproject", requester_project=None)
        env = {**os.environ, "VIBE_REPOS_DIR": str(td_path), "VIBE_PROJECT_NAME": "thisproject"}
        r = subprocess.run(["sh", "-c", cmd], input='{"model":{"display_name":"Opus 4.8"}}',
                            env=env, capture_output=True, text=True, timeout=15)
        check("[c3-status-d] exits 0", r.returncode == 0, r.stderr[:200])
        check("[c3-status-d] no rw warning segment when there is no pending request",
              "⚠ rw:" not in r.stdout, r.stdout)
        check("[c3-status-d] output is exactly the base segment, unchanged",
              r.stdout == "O · vibe", r.stdout)


def test_task017_c3_shared_repos_md_shape() -> None:
    """AC14: shared-repos.md fragment shape, mirroring the existing fragment
    shape tests (e.g. test_brain2_md_fragment_content) — proprietary/
    never-copy seam language, manifest path, ro etiquette, claim etiquette."""
    print("\n[task_017 AC14: shared-repos.md fragment shape]")
    check("[c3-fragment] shared-repos.md exists", SHARED_REPOS_MD.exists(), str(SHARED_REPOS_MD))
    if not SHARED_REPOS_MD.exists():
        return
    body = SHARED_REPOS_MD.read_text()
    check("[c3-fragment] documents the runtime manifest path",
          "/workspace/.vibe/shared-repos.manifest" in body, "")
    check("[c3-fragment] states never copy code from /repos/*",
          "never copy" in body.lower() and "/repos/*" in body, "")
    check("[c3-fragment] names the seam/interface/feature-flag consumption discipline",
          any(term in body.lower() for term in ("seam", "interface", "feature-flag")), "")
    check("[c3-fragment] documents ro etiquette: commit/push happens elsewhere",
          "ro" in body.lower() and "commit" in body.lower() and "elsewhere" in body.lower(), "")
    check("[c3-fragment] documents /repo claim etiquette",
          "/repo claim" in body, "")
    check("[c3-fragment] documents the ⚠ rw: statusLine segment to the holder",
          "⚠ rw:" in body, "")


def test_task017_c3_install_extras_shared_repos_md_gated() -> None:
    """AC14/AC15: install-claude-extras.sh includes shared-repos.md ONLY when
    VIBE_SHARED_REPOS_MANIFEST is a non-empty file, mirroring
    test_install_extras_brain2_md_gated's technique (temp CLAUDE_CONFIG_DIR,
    env override, before/after presence check in the installed managed
    block)."""
    print("\n[task_017 AC14/AC15: install-claude-extras.sh gates shared-repos.md on the manifest]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: manifest path doesn't exist at all -> excluded ([ ! -s ] is
        # true for a missing file).
        dest_off = tmp_path / "off"; dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off["VIBE_SHARED_REPOS_MANIFEST"] = str(tmp_path / "does-not-exist-manifest")
        r_off = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env_off), capture_output=True, text=True)
        check("[c3-gate] install exits 0 (missing manifest)", r_off.returncode == 0, r_off.stderr[:200])
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md ABSENT when manifest file is missing",
              "<!-- vibe-md: shared-repos.md -->" not in md_off, "leaked with missing manifest")
        check("[c3-gate] other fragments still present (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "loop didn't run")

        # Pass 2: manifest exists but is empty -> also excluded ([ ! -s ] is
        # true for a zero-byte file too).
        dest_empty = tmp_path / "empty"; dest_empty.mkdir()
        empty_manifest = tmp_path / "empty-manifest"
        empty_manifest.write_text("", encoding="utf-8")
        env_empty = env_base.copy()
        env_empty["CLAUDE_CONFIG_DIR"] = str(dest_empty)
        env_empty["VIBE_SHARED_REPOS_MANIFEST"] = str(empty_manifest)
        r_empty = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env_empty), capture_output=True, text=True)
        check("[c3-gate] install exits 0 (empty manifest)", r_empty.returncode == 0, r_empty.stderr[:200])
        md_empty = (dest_empty / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md ABSENT when manifest file is empty",
              "<!-- vibe-md: shared-repos.md -->" not in md_empty, "leaked with empty manifest")

        # Pass 3: manifest non-empty -> included.
        dest_on = tmp_path / "on"; dest_on.mkdir()
        manifest = tmp_path / "shared-repos.manifest"
        manifest.write_text("andeyePro rw andeyePro/andeyePro\n", encoding="utf-8")
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_SHARED_REPOS_MANIFEST"] = str(manifest)
        r_on = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env_on), capture_output=True, text=True)
        check("[c3-gate] install exits 0 (non-empty manifest)", r_on.returncode == 0, r_on.stderr[:200])
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[c3-gate] shared-repos.md PRESENT when manifest is non-empty",
              "<!-- vibe-md: shared-repos.md -->" in md_on, "missing with non-empty manifest")
        check("[c3-gate] installed body mentions the manifest path",
              "/workspace/.vibe/shared-repos.manifest" in md_on, "manifest path not documented in installed body")
