from smoke._core import *  # noqa: F401,F403




# ── Tests ─────────────────────────────────────────────────────────────────────


def test_codex_container_plumbing():
    """Phase 1a: binary, writable directory bind, empty pre-login host home."""
    print("\n[codex] image and subscription mount")
    cfg = json.loads((REPO / "devcontainer/devcontainer.json").read_text())
    mount = "source=${localEnv:HOME}/.codex,target=/home/node/.codex,type=bind"
    check("[codex] whole auth directory mounted read-write", mount in cfg["mounts"], "")
    dockerfile = DOCKERFILE.read_text()
    check("[codex] pinned vendor binary installed in image",
          "ARG CODEX_VERSION=0.154.0" in dockerfile and
          "npm install -g @openai/codex@${CODEX_VERSION}" in dockerfile, "")
    check("[codex] delegate helper shipped",
          "COPY vibe-delegate.mjs /usr/local/bin/vibe-delegate" in dockerfile, "")
    for name in ("VIBE_CLAUDE_P_BILLING", "VIBE_CLAUDE_P_SETTINGS", "VIBE_CLAUDE_P_CONFIG_DIR"):
        check(f"[codex] {name} routing only in remoteEnv",
              cfg["remoteEnv"].get(name) == "${localEnv:" + name + "}" and
              name not in cfg["containerEnv"], "")
    check("[codex] no OpenAI or Claude API keys plumbed",
          not any(key in cfg[section] for section in ("remoteEnv", "containerEnv")
                  for key in ("CODEX_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")), "")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        workspace = root / "workspace"
        workspace.mkdir()
        env = {"HOME": str(root / "home"), "VIBE_BRAIN2_PATH": "off", "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(env, f'_build_override_config {shlex.quote(str(workspace))}')
        check("[codex] no existing login required to render config",
              r.returncode == 0 and (root / "home/.codex").is_dir(), r.stderr)
        if r.returncode == 0:
            rendered = json.loads(Path(r.stdout.strip().splitlines()[-1]).read_text())
            check("[codex] rendered config retains writable auth bind", mount in rendered["mounts"], "")


def test_help() -> None:
    print("\n[vibe --help]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("exit 0", r.returncode == 0, r.stderr)
    check("header present", "vibe" in r.stdout, r.stdout[:200])
    check("usage section present", "Usage:" in r.stdout, r.stdout[:200])


def test_help_is_header_only() -> None:
    """2026-09-04: `vibe --help` prints ONLY the header comment block, not
    every column-1 `#` comment in the launcher (it printed 1,270 lines before
    the fix, with the flag reference buried at the top)."""
    print("\n[vibe --help is the header block only]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    lines = r.stdout.splitlines()
    check("[help] exit 0", r.returncode == 0, r.stderr)
    check("[help] under 80 lines", len(lines) < 80, f"{len(lines)} lines")
    check("[help] no shebang line", not any(l.startswith("!/") for l in lines), r.stdout[:120])
    for lit in ("Usage:", "--profile <name>", "vibe repos add", "vibe audit [--history|--staged]",
                "vibe pat", 'learn "<pattern>"', "any order", "8 Jul"):
        check(f"[help] keeps {lit!r}", lit in r.stdout, r.stdout[:400])
    for banner in ("Language profiles (", "image_drift_needs_recreate", "Content-guard audit",
                   "Configuration", "resolve_profile <flag_value>"):
        check(f"[help] drops body comment {banner!r}", banner not in r.stdout, "")
    check("[help] ends with the version line",
          lines[-1].startswith("vibe ") and lines[-2] == "", r.stdout[-80:])


def test_version() -> None:
    print("\n[vibe --version]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--version"], env=env)
    check("--version exit 0", r.returncode == 0, r.stderr)
    out = r.stdout.strip()
    check("--version prints 'vibe <semver>' single line",
          re.fullmatch(r"vibe \d+\.\d+\.\d+", out) is not None, repr(r.stdout))
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r2 = run(["bash", str(VIBE), "-V"], env=env)
    check("-V exit 0", r2.returncode == 0, r2.stderr)
    check("-V matches --version", r2.stdout.strip() == out, r2.stdout)
    check("VERSION file exists", VERSION_FILE.is_file(), str(VERSION_FILE))
    if VERSION_FILE.is_file():
        ver = VERSION_FILE.read_text().strip()
        check("VERSION file is bare semver", re.fullmatch(r"\d+\.\d+\.\d+", ver) is not None, ver)
        check("VERSION matches --version output", out == f"vibe {ver}", f"{out!r} vs vibe {ver}")


def test_vibe_andeye_page_draft() -> None:
    print("\n[web/vibe-andeye.md]")
    check("page exists", WEB_VIBE_ANDEYE_MD.is_file(), str(WEB_VIBE_ANDEYE_MD))
    if not WEB_VIBE_ANDEYE_MD.is_file():
        return
    txt = WEB_VIBE_ANDEYE_MD.read_text()
    first = txt.splitlines()[0] if txt.splitlines() else ""
    check("first line is a DRAFT sentinel comment",
          first.startswith("<!--") and "DRAFT" in first, first)
    check("sentinel says not for publication",
          "not for publication" in first.lower(), first)


def test_install_preflight() -> None:
    print("\n[install.sh preflight]")
    src = INSTALL.read_text()
    check("preflight_deps function present", "preflight_deps()" in src, "")
    check("preflight invoked before clone",
          re.search(r"\npreflight_deps\n", src) is not None
          and src.index("preflight_deps\n") < src.index("git clone"), "")
    # Functional: strip PATH so every dep is absent -> exit 1, no clone/link.
    # /bin/bash is absolute so the outer invocation works with an empty PATH.
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "emptybin"
        empty.mkdir()
        env = {**os.environ, "HOME": td, "PATH": str(empty)}
        r = run(["/bin/bash", str(INSTALL)], env=env)
    out = r.stdout + r.stderr
    check("preflight exits non-zero when deps missing", r.returncode != 0, out)
    check("preflight prints the re-run guidance",
          "Install the missing dependencies" in out, out)
    check("preflight did not reach the symlink step", "Linked" not in out, out)


def test_licence_state() -> None:
    """Martin never confirmed the AGPL move (brain2 misrecording, corrected
    2026-07-08); the drafts are gone and vibe is plainly MIT."""
    print("\n[licence state]")
    lic = REPO / "LICENSE"
    check("active LICENSE is MIT", lic.is_file() and "MIT License" in lic.read_text(), "")
    check("AGPL draft removed", not (REPO / "LICENSE-AGPL3-DRAFT").exists(), "")
    check("CLA draft removed", not (REPO / "CLA-DRAFT.md").exists(), "")
    for name in ("README.md", "CONTRIBUTING.md", "web/vibe-andeye.md"):
        # web/vibe-andeye.md is a superseded draft slated for deletion at
        # Martin's word — a missing file is fine, not a crash.
        path = REPO / name
        if not path.is_file():
            continue
        check(f"{name} does not announce an AGPL move",
              "settled on moving" not in path.read_text(), name)


def test_env_hint_fresh() -> None:
    print("\n[write-env-hint.sh: fresh file]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        r = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("CLAUDE.md created", target.exists())
        if not target.exists():
            return
        content = target.read_text()
        check("has start marker", "BEGIN vibe env (managed)" in content)
        check("has end marker", "END vibe env" in content)
        check("mentions SSH", "SSH" in content)
        check("mentions firewall allowlist", "allowlist" in content)


def test_env_hint_idempotent() -> None:
    print("\n[write-env-hint.sh: idempotent]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        run(["bash", str(WRITE_ENV_HINT)], env=env)
        first = target.read_text()
        run(["bash", str(WRITE_ENV_HINT)], env=env)
        second = target.read_text()
        check("stable across re-runs", first == second,
              f"first len={len(first)} second len={len(second)}")


def test_env_hint_preserves_user_content() -> None:
    print("\n[write-env-hint.sh: preserves user content]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "CLAUDE_CONFIG_DIR": str(tmp)}
        target = tmp / "CLAUDE.md"
        target.write_text("# My personal notes\nAlways use tabs.\n")
        r = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        content = target.read_text()
        check("user content survives", "Always use tabs" in content)
        check("vibe block present", "BEGIN vibe env (managed)" in content)


def test_docker_hints_fresh() -> None:
    print("\n[ensure_docker_hints_off: no config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        cfg = home / ".docker" / "config.json"
        check("config created", cfg.exists())
        if cfg.exists():
            data = json.loads(cfg.read_text())
            check("hints is string 'false'", data.get("features", {}).get("hints") == "false",
                  cfg.read_text())


def test_docker_hints_heals_bool() -> None:
    print("\n[ensure_docker_hints_off: heals legacy bool]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": {"hints": False, "other": True},
                                   "credsStore": "osxkeychain"}))
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("hints coerced to string", data["features"]["hints"] == "false", cfg.read_text())
        check("other bool coerced", data["features"]["other"] == "true", cfg.read_text())
        check("unrelated field preserved", data.get("credsStore") == "osxkeychain",
              cfg.read_text())


def test_docker_hints_respects_user_string() -> None:
    print("\n[ensure_docker_hints_off: respects user choice]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": {"hints": "true"}}, indent=2) + "\n")
        mtime_before = cfg.stat().st_mtime_ns
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("hints='true' preserved", data["features"]["hints"] == "true", cfg.read_text())
        check("file not rewritten", cfg.stat().st_mtime_ns == mtime_before,
              "mtime changed — should have been a no-op")


def test_docker_hints_malformed_json() -> None:
    print("\n[ensure_docker_hints_off: malformed JSON is left alone]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{not valid json")
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        check("malformed file untouched", cfg.read_text() == "{not valid json")


def test_docker_hints_non_dict_features() -> None:
    print("\n[ensure_docker_hints_off: features field is not a dict]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".docker" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"features": True}))
        r = _run_ensure_docker_hints_off(home)
        check("exit 0", r.returncode == 0, r.stderr)
        data = json.loads(cfg.read_text())
        check("features reset to dict with hints='false'",
              data.get("features") == {"hints": "false"}, cfg.read_text())


def test_install_detects_local_clone() -> None:
    """install.sh run from a real clone should use it in-place, not touch ~/.vibe-src."""
    print("\n[install.sh: detects local clone]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "PATH": _stub_dep_bin(tmp)}
        # Pre-seed config so the installer doesn't prompt for a projects dir.
        (tmp / ".vibe").mkdir()
        (tmp / ".vibe" / "config").write_text(f'VIBE_PROJECTS_DIR="{tmp}/Projects"\n')
        r = run(["bash", str(INSTALL)], env=env, cwd=REPO)
        check("exit 0", r.returncode == 0, r.stderr)
        check("announces in-place use", "Using existing clone" in r.stdout, r.stdout)
        check("did NOT create ~/.vibe-src", not (tmp / ".vibe-src").exists())
        link = tmp / "bin" / "vibe"
        check("bin/vibe symlink created", link.is_symlink())
        if link.is_symlink():
            check("symlink points at repo checkout",
                  Path(os.readlink(link)) == VIBE,
                  f"readlink={os.readlink(link)}")


def test_install_falls_back_to_vibe_src() -> None:
    """install.sh run as a standalone script (not inside a clone) should clone ~/.vibe-src.

    We can't exercise the real clone path without network, so just assert the
    detection correctly rejects a non-clone directory by checking the script
    tries to run `git clone` (which will fail fast with no network / bad URL).
    """
    print("\n[install.sh: non-clone falls through to ~/.vibe-src path]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        standalone = tmp / "install.sh"
        standalone.write_text(INSTALL.read_text())
        env = {**os.environ, "HOME": str(tmp), "PATH": _stub_dep_bin(tmp)}
        (tmp / ".vibe").mkdir()
        (tmp / ".vibe" / "config").write_text(f'VIBE_PROJECTS_DIR="{tmp}/Projects"\n')
        r = run(["bash", str(standalone)], env=env, cwd=tmp)
        combined = r.stdout + r.stderr
        check("took clone/pull path (not in-place)",
              "Using existing clone" not in r.stdout, r.stdout)
        check("attempted to clone to ~/.vibe-src",
              "Cloning vibe to" in combined, combined[-400:])


def test_token_helpers() -> None:
    """save_token / lookup_token round-trip against a tmp $HOME."""
    print("\n[vibe token helpers]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        save_token "owner/repo" "ghp_test123"
        echo "FOUND=$(lookup_token owner/repo)"
        save_token "owner/repo" "ghp_test456"
        echo "FOUND2=$(lookup_token owner/repo)"
        echo "LINES=$(wc -l < "$HOME/.vibe/tokens" | tr -d ' ')"
        echo "PERMS=$(stat -c '%a' "$HOME/.vibe/tokens" 2>/dev/null || stat -f '%Lp' "$HOME/.vibe/tokens")"
        """
        r = run(["bash", "-c", script], env=env)
        check("helpers run cleanly", r.returncode == 0, r.stderr)
        check("lookup returns saved token",
              "FOUND=ghp_test123" in r.stdout, r.stdout)
        check("save replaces on second call",
              "FOUND2=ghp_test456" in r.stdout, r.stdout)
        check("tokens file has one entry",
              "LINES=1" in r.stdout, r.stdout)
        check("tokens file chmod 600",
              "PERMS=600" in r.stdout, r.stdout)


def test_op_mcp_creds_lookup() -> None:
    """lookup_token returns OPENPROJECT_MCP_URL/BEARER whole — including a
    bearer with a trailing '=' (base64 padding), via the `cut -d= -f2-` fix —
    and slash-free OP keys don't collide with `owner/repo` PAT lines."""
    print("\n[vibe: OpenProject MCP creds lookup]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {
            **os.environ,
            "HOME": str(tmp),
            "VIBE_CONFIG": f"{tmp}/no-config",
            "VIBE_SOURCE_ONLY": "1",
        }
        script = f"""
        set -e
        source {shlex.quote(str(VIBE))}
        save_token "amybo/vibe" "ghp_repo"
        save_token "OPENPROJECT_MCP_URL" "https://openproject-mcp.tail09c06e.ts.net"
        save_token "OPENPROJECT_MCP_BEARER" "YmFzZTY0dG9rZW4="
        echo "URL=$(lookup_token OPENPROJECT_MCP_URL)"
        echo "BEARER=$(lookup_token OPENPROJECT_MCP_BEARER)"
        echo "REPO=$(lookup_token amybo/vibe)"
        """
        r = run(["bash", "-c", script], env=env)
        check("helpers run cleanly", r.returncode == 0, r.stderr)
        check("OP URL resolves whole (keeps ://)",
              "URL=https://openproject-mcp.tail09c06e.ts.net" in r.stdout, r.stdout)
        check("bearer keeps trailing '=' (cut -f2- fix)",
              "BEARER=YmFzZTY0dG9rZW4=" in r.stdout, r.stdout)
        check("repo PAT still resolves (no slash-free collision)",
              "REPO=ghp_repo" in r.stdout, r.stdout)


# AC1 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_clean_exit_and_valid_json() -> None:
    """AC1: --json exits 0 on clean repo, stdout is valid JSON."""
    print("\n[json AC1: clean exit + valid JSON]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    check("[json] AC1 exit-0 on clean repo", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    try:
        data = json.loads(r.stdout)
        check("[json] AC1 stdout is valid JSON", True)
    except json.JSONDecodeError as exc:
        check("[json] AC1 stdout is valid JSON", False, str(exc))
        data = {}
    check("[json] AC1 no findings on clean repo",
          isinstance(data.get("findings"), list) and len(data.get("findings", [])) == 0,
          str(data))


# AC2 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_top_level_keys() -> None:
    """AC2: top-level keys present with correct types."""
    print("\n[json AC2: top-level keys + types]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        check("[json] AC2 parse for schema check", False, r.stdout[:200])
        return
    check("[json] AC2 key 'tool' == 'shellcheck'", data.get("tool") == "shellcheck",
          str(data.get("tool")))
    check("[json] AC2 key 'shellcheck_version' is str",
          isinstance(data.get("shellcheck_version"), str) and data.get("shellcheck_version", "") != "",
          str(data.get("shellcheck_version")))
    check("[json] AC2 key 'files_checked' is list",
          isinstance(data.get("files_checked"), list), str(type(data.get("files_checked"))))
    check("[json] AC2 key 'findings' is list",
          isinstance(data.get("findings"), list), str(type(data.get("findings"))))
    summary = data.get("summary", {})
    check("[json] AC2 key 'summary' is dict", isinstance(summary, dict), str(type(summary)))
    check("[json] AC2 summary.files is int", isinstance(summary.get("files"), int),
          str(type(summary.get("files"))))
    check("[json] AC2 summary.files_with_issues is int",
          isinstance(summary.get("files_with_issues"), int),
          str(type(summary.get("files_with_issues"))))
    check("[json] AC2 summary.total_findings is int",
          isinstance(summary.get("total_findings"), int),
          str(type(summary.get("total_findings"))))


# AC3 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_finding_schema() -> None:
    """AC3: each finding has required keys with correct types; code is int."""
    print("\n[json AC3: finding schema]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bad = REPO / "_smoke_test_bad_script.sh"
        try:
            _make_bad_script(bad)
            target, ccenv = _patched_code_check(tmp, [bad])
            r = run(["python3", str(target), "--json"], env=ccenv, cwd=REPO)
            # Exit 1 expected (findings present)
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC3 parse findings JSON", False, r.stdout[:200])
                return
            findings = data.get("findings", [])
            check("[json] AC3 at least one finding present", len(findings) > 0,
                  f"findings={findings}")
            if findings:
                f = findings[0]
                check("[json] AC3 finding has 'file' str", isinstance(f.get("file"), str),
                      str(f))
                check("[json] AC3 finding has 'line' int", isinstance(f.get("line"), int),
                      str(f))
                check("[json] AC3 finding has 'column' int", isinstance(f.get("column"), int),
                      str(f))
                check("[json] AC3 finding has 'level' str", isinstance(f.get("level"), str),
                      str(f))
                check("[json] AC3 finding 'code' is int (not str)",
                      isinstance(f.get("code"), int) and not isinstance(f.get("code"), bool),
                      f"code={f.get('code')!r} type={type(f.get('code'))}")
                check("[json] AC3 finding has 'message' str",
                      isinstance(f.get("message"), str), str(f))
                check("[json] AC3 finding 'level' value in allowed set",
                      f.get("level") in {"error", "warning", "info", "style"}, str(f))
        finally:
            if bad.exists():
                bad.unlink()


# AC4 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_findings_exit1_and_count() -> None:
    """AC4: with findings, exit 1 and total_findings == len(findings) > 0."""
    print("\n[json AC4: findings → exit 1 + count matches]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bad = REPO / "_smoke_test_bad_ac4.sh"
        try:
            _make_bad_script(bad, varname="myunused")
            target, ccenv = _patched_code_check(tmp, [bad])
            r = run(["python3", str(target), "--json"], env=ccenv, cwd=REPO)
            check("[json] AC4 exit 1 when findings present", r.returncode == 1,
                  f"exit={r.returncode} stderr={r.stderr[:200]}")
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC4 parse JSON on exit-1", False, r.stdout[:200])
                return
            findings = data.get("findings", [])
            total = data.get("summary", {}).get("total_findings", -1)
            check("[json] AC4 total_findings > 0", total > 0, f"total_findings={total}")
            check("[json] AC4 total_findings == len(findings)",
                  total == len(findings), f"total_findings={total} len={len(findings)}")
        finally:
            if bad.exists():
                bad.unlink()


# AC5 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_stdout_only_json() -> None:
    """AC5: --json stdout is exactly one JSON object, no progress lines."""
    print("\n[json AC5: stdout is exactly one JSON object]")
    r = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    stdout = r.stdout
    # Must parse as a single JSON object from the whole stdout
    try:
        data = json.loads(stdout)
        check("[json] AC5 stdout parses as single JSON object", isinstance(data, dict),
              f"type={type(data)}")
    except json.JSONDecodeError as exc:
        check("[json] AC5 stdout parses as single JSON object", False, str(exc))
        return
    # Must not contain progress arrows (→ shellcheck) in stdout
    check("[json] AC5 no '→ shellcheck' progress lines in stdout",
          "→ shellcheck" not in stdout, stdout[:300])
    # Must not contain human summary line
    check("[json] AC5 no '✓ shellcheck clean' human line in stdout",
          "✓ shellcheck clean" not in stdout, stdout[:300])
    check("[json] AC5 no '✗ shellcheck' human line in stdout",
          "✗ shellcheck" not in stdout, stdout[:300])
    # Stdout should decode to exactly one object (no trailing text after the JSON)
    stripped = stdout.strip()
    # Verify that after the JSON object there is no extra content
    try:
        decoder = json.JSONDecoder()
        obj, idx = decoder.raw_decode(stripped)
        check("[json] AC5 no extra text after JSON object",
              idx == len(stripped), f"extra text: {stripped[idx:idx+80]!r}")
    except json.JSONDecodeError as exc:
        check("[json] AC5 no extra text after JSON object", False, str(exc))


# AC6 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_human_mode_unchanged() -> None:
    """AC6: without --json, human-readable output is preserved (arrows + summary)."""
    print("\n[json AC6: human mode output unchanged]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[json] AC6 human mode exits 0 on clean repo", r.returncode == 0,
          f"exit={r.returncode}")
    check("[json] AC6 human mode has '→ shellcheck' progress lines",
          "→ shellcheck" in r.stdout, r.stdout[:300])
    check("[json] AC6 human mode has '✓ shellcheck clean' summary",
          "✓ shellcheck clean" in r.stdout, r.stdout[:300])
    # Confirm --json mode does NOT have these
    rj = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    check("[json] AC6 --json mode has NO '→ shellcheck' lines",
          "→ shellcheck" not in rj.stdout, rj.stdout[:300])
    check("[json] AC6 --json mode has NO '✓ shellcheck clean' line",
          "✓ shellcheck clean" not in rj.stdout, rj.stdout[:300])


# AC7 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_missing_shellcheck() -> None:
    """AC7: missing shellcheck + --json → JSON error object on stdout, exit 2."""
    print("\n[json AC7: missing shellcheck → JSON error object]")
    with tempfile.TemporaryDirectory() as td:
        fake_bin = Path(td) / "bin"
        fake_bin.mkdir()
        # Symlink python3 into fake_bin but do NOT include shellcheck.
        python3_src = Path("/usr/bin/python3")
        (fake_bin / "python3").symlink_to(python3_src)
        env = {**os.environ, "PATH": str(fake_bin)}
        # Run code-check.py via absolute python3 path to avoid PATH lookup for python3.
        r = subprocess.run(
            [str(python3_src), str(CODE_CHECK), "--json"],
            capture_output=True, text=True, env=env, cwd=str(REPO),
        stdin=subprocess.DEVNULL,
        )
        check("[json] AC7 exit 2 when shellcheck missing", r.returncode == 2,
              f"exit={r.returncode}")
        try:
            data = json.loads(r.stdout)
            check("[json] AC7 stdout is valid JSON error object", isinstance(data, dict),
                  f"type={type(data)}")
        except json.JSONDecodeError as exc:
            check("[json] AC7 stdout is valid JSON error object", False,
                  f"{exc} stdout={r.stdout[:200]}")
            return
        check("[json] AC7 error object has 'error' key == 'shellcheck-not-installed'",
              data.get("error") == "shellcheck-not-installed", str(data))
        check("[json] AC7 error object has 'tool' key == 'shellcheck'",
              data.get("tool") == "shellcheck", str(data))


# AC8 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_help_mentions_flag() -> None:
    """AC8: --help exits 0 and help text mentions --json."""
    print("\n[json AC8: --help mentions --json]")
    r = run(["python3", str(CODE_CHECK), "--help"], cwd=REPO)
    check("[json] AC8 --help exits 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:200]}")
    combined = r.stdout + r.stderr  # argparse may write to stderr on some versions
    check("[json] AC8 help text mentions '--json'", "--json" in combined, combined[:500])


# AC9 ─────────────────────────────────────────────────────────────────────────

def test_code_check_json_summary_counts() -> None:
    """AC9: summary.files == len(files_checked); summary.files_with_issues matches."""
    print("\n[json AC9: summary counts accuracy]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 3 files: 2 bad, 1 good — all must live inside REPO for relative_to to work
        bad1 = REPO / "_smoke_ac9_bad1.sh"
        bad2 = REPO / "_smoke_ac9_bad2.sh"
        good = REPO / "_smoke_ac9_good.sh"
        try:
            _make_bad_script(bad1, varname="unused_one")
            _make_bad_script(bad2, varname="unused_two")
            _make_good_script(good)
            target, ccenv = _patched_code_check(tmp, [bad1, bad2, good])
            r = run(["python3", str(target), "--json"], env=ccenv, cwd=REPO)
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                check("[json] AC9 parse JSON", False, r.stdout[:200])
                return
            files_checked = data.get("files_checked", [])
            findings = data.get("findings", [])
            summary = data.get("summary", {})
            check("[json] AC9 summary.files == len(files_checked)",
                  summary.get("files") == len(files_checked),
                  f"summary.files={summary.get('files')} len(files_checked)={len(files_checked)}")
            check("[json] AC9 files_checked has 3 entries", len(files_checked) == 3,
                  str(files_checked))
            distinct_files_with_issues = len({f["file"] for f in findings})
            check("[json] AC9 summary.files_with_issues matches distinct finding files",
                  summary.get("files_with_issues") == distinct_files_with_issues,
                  f"summary.files_with_issues={summary.get('files_with_issues')} "
                  f"distinct={distinct_files_with_issues}")
            check("[json] AC9 files_with_issues == 2 (two bad scripts)",
                  summary.get("files_with_issues") == 2,
                  f"files_with_issues={summary.get('files_with_issues')}")
        finally:
            for p in [bad1, bad2, good]:
                if p.exists():
                    p.unlink()


# AC10 ────────────────────────────────────────────────────────────────────────

def test_code_check_json_same_target_list() -> None:
    """AC10: --json and human mode scan identical target lists."""
    print("\n[json AC10: same target list with/without --json]")
    # Human mode: extract file paths from '→ shellcheck <path>' lines
    r_human = run(["python3", str(CODE_CHECK)], cwd=REPO)
    human_paths = set()
    for line in r_human.stdout.splitlines():
        line = line.strip()
        if line.startswith("→ shellcheck "):
            path_part = line[len("→ shellcheck "):].strip()
            human_paths.add(path_part)
    check("[json] AC10 human mode produced at least one path", len(human_paths) > 0,
          r_human.stdout[:300])
    # JSON mode: extract files_checked
    r_json = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    try:
        data = json.loads(r_json.stdout)
    except json.JSONDecodeError:
        check("[json] AC10 parse --json output", False, r_json.stdout[:200])
        return
    json_paths = set(data.get("files_checked", []))
    check("[json] AC10 --json files_checked == human mode paths",
          json_paths == human_paths,
          f"json_paths={sorted(json_paths)} human_paths={sorted(human_paths)}")


def test_task025_ac1_git_hooks_in_default_set() -> None:
    """AC1: default scripts() (CODE_CHECK_SCRIPTS unset) includes all four
    devcontainer/git-hooks/ files, by repo-relative path, via --json
    files_checked."""
    print("\n[task_025 AC1: git-hooks covered by default]")
    env = os.environ.copy()
    env.pop("CODE_CHECK_SCRIPTS", None)
    r = run(["python3", str(CODE_CHECK), "--json"], env=env, cwd=REPO)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        check("[task025] AC1 parse --json output", False, r.stdout[:200])
        return
    files_checked = set(data.get("files_checked", []))
    expected = {
        "devcontainer/git-hooks/vibe-content-scan.sh",
        "devcontainer/git-hooks/commit-msg",
        "devcontainer/git-hooks/pre-commit",
        "devcontainer/git-hooks/pre-push",
    }
    check("[task025] AC1 default set includes all 4 git-hooks files",
          expected.issubset(files_checked),
          f"missing={expected - files_checked} files_checked={sorted(files_checked)}")


def test_task025_ac2_is_shell_script_predicate() -> None:
    """AC2: is_shell_script resolves every pinned shebang case, and never
    raises on binary/nonexistent input."""
    print("\n[task_025 AC2: is_shell_script predicate]")
    module = _load_code_check_module()
    is_shell_script = module.is_shell_script

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cases: list[tuple[str, bytes, bool]] = [
            ("env-bash-no-ext", b"#!/usr/bin/env bash\necho hi\n", True),
            ("bin-sh", b"#!/bin/sh\necho hi\n", True),
            ("bin-bash", b"#!/bin/bash\necho hi\n", True),
            ("env-zsh", b"#!/usr/bin/env zsh\necho hi\n", True),
            ("env-fish", b"#!/usr/bin/env fish\necho hi\n", False),
            ("python3-shebang", b"#!/usr/bin/python3\nprint('hi')\n", False),
            ("no-shebang", b"echo hi\n", False),
            ("empty-file", b"", False),
            ("env-dash-S-bash-x", b"#!/usr/bin/env -S bash -x\necho hi\n", True),
            ("env-alone", b"#!/usr/bin/env\necho hi\n", False),
            ("bare-bang", b"#!\necho hi\n", False),
            ("whitespace-only", b"#!   \necho hi\n", False),
        ]
        for label, content, expected in cases:
            p = tmp / f"case-{label}"
            p.write_bytes(content)
            got = is_shell_script(p)
            check(f"[task025] AC2 {label} -> {expected}", got is expected,
                  f"got={got!r} expected={expected!r}")

        # Non-UTF-8 / binary first line -> False, no exception raised.
        binary_path = tmp / "case-binary"
        binary_path.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x01, 0x02, 0x03] * 8))
        raised = False
        got = None
        try:
            got = is_shell_script(binary_path)
        except Exception:  # noqa: BLE001 - the defensive no-raise contract under test
            raised = True
        check("[task025] AC2 binary first line -> False, no exception",
              (not raised) and got is False, f"raised={raised} got={got!r}")

        # Nonexistent path -> False, no exception (OSError swallowed).
        missing_path = tmp / "does-not-exist"
        raised = False
        got = None
        try:
            got = is_shell_script(missing_path)
        except Exception:  # noqa: BLE001
            raised = True
        check("[task025] AC2 nonexistent path -> False, no exception",
              (not raised) and got is False, f"raised={raised} got={got!r}")


def test_task025_ac3_env_seam_exact_list() -> None:
    """AC3: CODE_CHECK_SCRIPTS set to two os.pathsep-separated paths (one
    nonexistent) -> scripts() returns exactly those two Paths, in order, no
    globbing/dedup/.exists() filter. The override is subprocess-scoped only
    (never mutates this process's os.environ), so it cannot leak into the
    two frozen bare-run tests later in main()'s fixed sequence."""
    print("\n[task_025 AC3: env seam exact-list, subprocess-scoped]")
    check("[task025] AC3 parent os.environ has no CODE_CHECK_SCRIPTS before test",
          "CODE_CHECK_SCRIPTS" not in os.environ,
          f"present={os.environ.get('CODE_CHECK_SCRIPTS')!r}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real = tmp / "real-script.sh"
        real.write_text("#!/bin/bash\necho hi\n")
        missing = tmp / "does-not-exist.sh"  # deliberately never created

        env = os.environ.copy()
        env["CODE_CHECK_SCRIPTS"] = os.pathsep.join([str(real), str(missing)])

        script = (
            "import importlib.util, json\n"
            f"spec = importlib.util.spec_from_file_location('cc', {str(CODE_CHECK)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "print(json.dumps([str(p) for p in m.scripts()]))\n"
        )
        r = run(["python3", "-c", script], env=env, cwd=REPO)
        check("[task025] AC3 subprocess exits 0", r.returncode == 0, r.stderr[:300])
        try:
            got = json.loads(r.stdout.strip())
        except json.JSONDecodeError:
            check("[task025] AC3 parse subprocess JSON output", False, r.stdout[:300])
            return
        check("[task025] AC3 exact 2-entry list, order preserved, no filter",
              got == [str(real), str(missing)], f"got={got}")

    check("[task025] AC3 parent os.environ has no CODE_CHECK_SCRIPTS after test",
          "CODE_CHECK_SCRIPTS" not in os.environ,
          f"present={os.environ.get('CODE_CHECK_SCRIPTS')!r}")


def test_task025_ac4_unset_and_empty_env_falls_through_to_default() -> None:
    """AC4: CODE_CHECK_SCRIPTS unset OR set to the empty string both fall
    through to the same default set (AC1's git-hooks-inclusive set)."""
    print("\n[task_025 AC4: unset/empty env -> default]")
    script = (
        "import importlib.util, json\n"
        f"spec = importlib.util.spec_from_file_location('cc', {str(CODE_CHECK)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "print(json.dumps(sorted(str(p) for p in m.scripts())))\n"
    )
    env_unset = os.environ.copy()
    env_unset.pop("CODE_CHECK_SCRIPTS", None)
    r_unset = run(["python3", "-c", script], env=env_unset, cwd=REPO)
    check("[task025] AC4 unset-env subprocess exits 0", r_unset.returncode == 0,
          r_unset.stderr[:300])

    env_empty = os.environ.copy()
    env_empty["CODE_CHECK_SCRIPTS"] = ""
    r_empty = run(["python3", "-c", script], env=env_empty, cwd=REPO)
    check("[task025] AC4 empty-env subprocess exits 0", r_empty.returncode == 0,
          r_empty.stderr[:300])

    try:
        got_unset = json.loads(r_unset.stdout.strip())
        got_empty = json.loads(r_empty.stdout.strip())
    except json.JSONDecodeError:
        check("[task025] AC4 parse both subprocess outputs", False,
              f"unset={r_unset.stdout[:200]} empty={r_empty.stdout[:200]}")
        return

    check("[task025] AC4 unset and empty produce the identical default set",
          got_unset == got_empty, f"unset={got_unset} empty={got_empty}")

    default_names = {Path(p).name for p in got_unset}
    check("[task025] AC4 default set includes all 4 git-hooks files",
          {"vibe-content-scan.sh", "commit-msg", "pre-commit", "pre-push"} <= default_names,
          f"names={default_names}")


def test_task025_ac5_real_run_green_and_larger_set() -> None:
    """AC5: python3 code-check.py exits 0; --json is a single valid object;
    summary.files reflects the larger (git-hooks-inclusive) default set."""
    print("\n[task_025 AC5: real run green + larger summary.files]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[task025] AC5 human mode exits 0 (all git-hooks files clean)",
          r.returncode == 0, f"exit={r.returncode} output={r.stdout[-300:]}")

    rj = run(["python3", str(CODE_CHECK), "--json"], cwd=REPO)
    check("[task025] AC5 --json exits 0", rj.returncode == 0,
          f"exit={rj.returncode} stderr={rj.stderr[:200]}")
    try:
        data = json.loads(rj.stdout)
        check("[task025] AC5 --json stdout is a single valid JSON object",
              isinstance(data, dict), f"type={type(data)}")
    except json.JSONDecodeError as exc:
        check("[task025] AC5 --json stdout is a single valid JSON object", False, str(exc))
        return

    files_checked = data.get("files_checked", [])
    summary = data.get("summary", {})
    check("[task025] AC5 summary.files == len(files_checked)",
          summary.get("files") == len(files_checked),
          f"summary.files={summary.get('files')} len={len(files_checked)}")
    git_hooks_in_set = [f for f in files_checked if f.startswith("devcontainer/git-hooks/")]
    check("[task025] AC5 summary.files includes the 4 git-hooks files",
          len(git_hooks_in_set) == 4, f"git_hooks_in_set={git_hooks_in_set}")


def test_task025_ac7_no_scripts_source_text_replace() -> None:
    """AC7: _patched_code_check (however reshaped) contains no `.replace(`
    call keyed on scripts()'s source text."""
    print("\n[task_025 AC7: no source-text .replace() on scripts()]")
    import inspect
    found = _patched_code_check_has_scripts_source_replace()
    check("[task025] AC7 _patched_code_check has no scripts()-source .replace() call",
          not found, inspect.getsource(_patched_code_check))


def test_task025_ac8_code_check_py_compile() -> None:
    """AC8: code-check.py passes python3 -m py_compile (its lint gate,
    since shellcheck itself doesn't cover Python)."""
    print("\n[task_025 AC8: code-check.py py_compile]")
    r = run(["python3", "-m", "py_compile", str(CODE_CHECK)], cwd=REPO)
    check("[task025] AC8 py_compile exits 0", r.returncode == 0,
          f"exit={r.returncode} stderr={r.stderr[:300]}")


def test_vibe_resume_args_fresh() -> None:
    print("\n[vibe build_claude_resume_args: fresh]")
    r = _source_vibe_call({}, 'echo "OUT=[$(build_claude_resume_args)]"')
    check("fresh exits 0", r.returncode == 0, r.stderr)
    check("fresh emits empty arg fragment", "OUT=[]" in r.stdout, r.stdout)


def test_vibe_resume_args_continue() -> None:
    print("\n[vibe build_claude_resume_args: --continue]")
    r = _source_vibe_call({"CONTINUE": "true"},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--continue exits 0", r.returncode == 0, r.stderr)
    check("--continue emits '--continue'", "OUT=[--continue]" in r.stdout, r.stdout)


def test_vibe_resume_args_resume_picker() -> None:
    print("\n[vibe build_claude_resume_args: --resume (picker)]")
    r = _source_vibe_call({"RESUME": "true"},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--resume exits 0", r.returncode == 0, r.stderr)
    check("--resume emits '--resume'", "OUT=[--resume]" in r.stdout, r.stdout)


def test_vibe_resume_args_resume_uid() -> None:
    print("\n[vibe build_claude_resume_args: --resume <uuid>]")
    uid = "12345678-1234-1234-1234-123456789abc"
    r = _source_vibe_call({"RESUME": "true", "RESUME_UID": uid},
                          'echo "OUT=[$(build_claude_resume_args)]"')
    check("--resume <uid> exits 0", r.returncode == 0, r.stderr)
    check("--resume <uid> emits '--resume <uid>'",
          f"OUT=[--resume {uid}]" in r.stdout, r.stdout)


def test_vibe_is_uuid() -> None:
    print("\n[vibe is_uuid]")
    cases = [
        ("12345678-1234-1234-1234-123456789abc", True, "valid lowercase"),
        ("ABCDEF12-3456-7890-ABCD-EF1234567890", True, "valid uppercase"),
        ("not-a-uuid", False, "obvious non-uuid"),
        ("", False, "empty string"),
        ("12345678-1234-1234-1234-123456789ab", False, "too short"),
        ("12345678-1234-1234-1234-123456789abcd", False, "too long"),
        ("--continue", False, "looks like a flag"),
        ("my-project", False, "project name"),
    ]
    for value, expected, label in cases:
        r = _source_vibe_call({}, f'is_uuid {shlex.quote(value)} && echo Y || echo N')
        observed = "Y" in r.stdout
        check(f"is_uuid '{value}' → {expected} ({label})",
              observed == expected, r.stdout + r.stderr)


def test_vibe_help_mentions_continue_and_resume() -> None:
    print("\n[vibe --help mentions --continue and --resume]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("--help exits 0", r.returncode == 0, r.stderr)
    check("help mentions --continue", "--continue" in r.stdout, r.stdout[:400])
    check("help mentions --resume", "--resume" in r.stdout, r.stdout[:400])
    check("help notes positional+flag any-order",
          "any order" in r.stdout, r.stdout[:600])


def test_parse_args_no_args() -> None:
    print("\n[parse_vibe_args: no args → all defaults]")
    r = _parse_args_probe([])
    check("exits 0", r.returncode == 0, r.stderr)
    check("REBUILD=false", "REBUILD=[false]" in r.stdout, r.stdout)
    check("CONTINUE=false", "CONTINUE=[false]" in r.stdout, r.stdout)
    check("RESUME=false", "RESUME=[false]" in r.stdout, r.stdout)
    check("RESUME_UID empty", "RESUME_UID=[]" in r.stdout, r.stdout)
    check("PROJECT_ARG empty", "PROJECT_ARG=[]" in r.stdout, r.stdout)


def test_parse_args_leading_continue() -> None:
    print("\n[parse_vibe_args: --continue (no project)]")
    r = _parse_args_probe(["--continue"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("CONTINUE=true", "CONTINUE=[true]" in r.stdout, r.stdout)
    check("PROJECT_ARG empty", "PROJECT_ARG=[]" in r.stdout, r.stdout)


def test_parse_args_project_only() -> None:
    print("\n[parse_vibe_args: vibe (project only)]")
    r = _parse_args_probe(["vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=false", "CONTINUE=[false]" in r.stdout, r.stdout)


def test_parse_args_project_then_continue() -> None:
    print("\n[parse_vibe_args: vibe --continue (regression: was silently dropped)]")
    r = _parse_args_probe(["vibe", "--continue"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=true (the fix)", "CONTINUE=[true]" in r.stdout, r.stdout)


def test_parse_args_continue_then_project() -> None:
    print("\n[parse_vibe_args: --continue vibe (leading-flag form, must still work)]")
    r = _parse_args_probe(["--continue", "vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("CONTINUE=true", "CONTINUE=[true]" in r.stdout, r.stdout)


def test_parse_args_project_then_resume_uid() -> None:
    print("\n[parse_vibe_args: vibe --resume <uuid>]")
    uid = "12345678-1234-1234-1234-123456789abc"
    r = _parse_args_probe(["vibe", "--resume", uid])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("RESUME=true", "RESUME=[true]" in r.stdout, r.stdout)
    check(f"RESUME_UID={uid}", f"RESUME_UID=[{uid}]" in r.stdout, r.stdout)


def test_parse_args_project_then_resume_picker() -> None:
    print("\n[parse_vibe_args: vibe --resume (no uuid → picker)]")
    r = _parse_args_probe(["vibe", "--resume"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("RESUME=true", "RESUME=[true]" in r.stdout, r.stdout)
    check("RESUME_UID empty", "RESUME_UID=[]" in r.stdout, r.stdout)


def test_parse_args_project_then_rebuild() -> None:
    print("\n[parse_vibe_args: vibe --rebuild]")
    r = _parse_args_probe(["vibe", "--rebuild"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("REBUILD=true", "REBUILD=[true]" in r.stdout, r.stdout)


def test_parse_args_two_positionals_rejected() -> None:
    print("\n[parse_vibe_args: two positionals rejected]")
    r = _parse_args_probe(["vibe", "other"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions extra", "extra argument" in r.stderr, r.stderr)


def test_parse_args_unknown_flag_rejected() -> None:
    print("\n[parse_vibe_args: unknown trailing flag rejected]")
    r = _parse_args_probe(["vibe", "--bogus"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions unknown", "Unknown flag" in r.stderr, r.stderr)


# ── Model selection tests (--fable / --model / billing gate helpers) ──────────


def test_parse_args_fable() -> None:
    print("\n[parse_vibe_args: vibe --fable → MODEL_ARG=claude-fable-5]")
    r = _parse_args_probe(["vibe", "--fable"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)
    check("MODEL_ARG=claude-fable-5",
          "MODEL_ARG=[claude-fable-5]" in r.stdout, r.stdout)


def test_parse_args_model_explicit() -> None:
    print("\n[parse_vibe_args: --model claude-opus-4-8]")
    r = _parse_args_probe(["--model", "claude-opus-4-8", "vibe"])
    check("exits 0", r.returncode == 0, r.stderr)
    check("MODEL_ARG=claude-opus-4-8",
          "MODEL_ARG=[claude-opus-4-8]" in r.stdout, r.stdout)
    check("PROJECT_ARG=vibe", "PROJECT_ARG=[vibe]" in r.stdout, r.stdout)


def test_parse_args_model_missing_value_rejected() -> None:
    print("\n[parse_vibe_args: --model with no value rejected]")
    r = _parse_args_probe(["--model"])
    check("exits 1", r.returncode == 1, r.stdout + r.stderr)
    check("error mentions model id", "model id" in r.stderr, r.stderr)


def test_parse_args_model_injection_rejected() -> None:
    print("\n[parse_vibe_args: --model with shell metachars rejected]")
    for bad in ["claude; rm -rf /", "a b", "$(whoami)", "claude`x`", "--continue"]:
        r = _parse_args_probe(["--model", bad])
        check(f"--model {bad!r} exits 1", r.returncode == 1,
              r.stdout + r.stderr)


def test_vibe_is_model_id() -> None:
    print("\n[vibe is_model_id]")
    cases = [
        ("claude-fable-5", True, "fable id"),
        ("claude-opus-4-8", True, "opus id"),
        ("claude-3-5-haiku-20241022", True, "dated id"),
        ("opus", True, "alias"),
        ("", False, "empty"),
        ("a b", False, "space"),
        ("a;b", False, "semicolon"),
        ("$(x)", False, "command substitution"),
        ("a`b`", False, "backticks"),
        ("a'b", False, "quote"),
    ]
    for value, expected, label in cases:
        r = _source_vibe_call({}, f'is_model_id {shlex.quote(value)} && echo Y || echo N')
        observed = "Y" in r.stdout
        check(f"is_model_id '{value}' → {expected} ({label})",
              observed == expected, r.stdout + r.stderr)


def test_vibe_model_args_fresh() -> None:
    print("\n[vibe build_claude_model_args: no model → empty]")
    r = _source_vibe_call({}, 'echo "OUT=[$(build_claude_model_args)]"')
    check("exits 0", r.returncode == 0, r.stderr)
    check("emits empty fragment", "OUT=[]" in r.stdout, r.stdout)


def test_vibe_model_args_set() -> None:
    print("\n[vibe build_claude_model_args: MODEL_ARG set]")
    r = _source_vibe_call({"MODEL_ARG": "claude-fable-5"},
                          'echo "OUT=[$(build_claude_model_args)]"')
    check("exits 0", r.returncode == 0, r.stderr)
    check("emits '--model claude-fable-5'",
          "OUT=[--model claude-fable-5]" in r.stdout, r.stdout)


def test_vibe_fable_billing_phase() -> None:
    print("\n[vibe fable_billing_phase: free until 7 Jul 2026, credits after]")
    cases = [
        ("20260609", "free", "launch day"),
        ("20260707", "free", "last free day"),
        ("20260708", "credits", "cutover day"),
        ("20270101", "credits", "well after"),
    ]
    for date, expected, label in cases:
        r = _source_vibe_call({}, f'echo "OUT=[$(fable_billing_phase {date})]"')
        check(f"{date} → {expected} ({label})",
              f"OUT=[{expected}]" in r.stdout, r.stdout + r.stderr)


def test_vibe_auto_resume_helpers() -> None:
    print("\n[vibe auto-resume marker helpers]")
    snippet = (
        'm="${TMPDIR:-/tmp}/vibe-ar-test.$$"; '
        "printf 'active=1\\nremaining=2\\nresume_at=1751600000\\n' > \"$m\"; "
        'echo "FIELD=[$(auto_resume_field "$m" remaining)]"; '
        'echo "BADKEY=[$(auto_resume_field "$m" nope)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING=[yes]"; else echo "PENDING=[no]"; fi; '
        'auto_resume_decrement "$m"; auto_resume_decrement "$m"; '
        'echo "AFTER=[$(auto_resume_field "$m" remaining)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING2=[yes]"; else echo "PENDING2=[no]"; fi; '
        "printf 'active=1\\nremaining=evil; rm -rf /\\n' > \"$m\"; "
        'echo "EVIL=[$(auto_resume_field "$m" remaining)]"; '
        'if auto_resume_pending "$m"; then echo "PENDING3=[yes]"; else echo "PENDING3=[no]"; fi; '
        'if auto_resume_pending "$m.missing"; then echo "PENDING4=[yes]"; else echo "PENDING4=[no]"; fi; '
        'rm -f "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("numeric field read", "FIELD=[2]" in r.stdout, r.stdout)
    check("missing key → empty", "BADKEY=[]" in r.stdout, r.stdout)
    check("pending when active + remaining", "PENDING=[yes]" in r.stdout, r.stdout)
    check("decrement twice → 0", "AFTER=[0]" in r.stdout, r.stdout)
    check("not pending at remaining=0", "PENDING2=[no]" in r.stdout, r.stdout)
    check("non-numeric value rejected", "EVIL=[]" in r.stdout, r.stdout)
    check("not pending on malformed marker", "PENDING3=[no]" in r.stdout, r.stdout)
    check("not pending on missing file", "PENDING4=[no]" in r.stdout, r.stdout)


def test_vibe_help_mentions_fable_and_model() -> None:
    print("\n[vibe --help mentions --fable and --model]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("--help exits 0", r.returncode == 0, r.stderr)
    check("help mentions --fable", "--fable" in r.stdout, r.stdout[:800])
    check("help mentions --model", "--model" in r.stdout, r.stdout[:800])
    check("help mentions the credits cutover",
          "8 Jul" in r.stdout, r.stdout)


def test_ac1_no_container() -> None:
    """AC1: No container → no-op."""
    print("\n[task_015 AC1: no container → no-op]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="",  # empty - no containers
        ps_rc=0,
        cref_output="",
        cref_rc=0,
        tag_id_output="sha256:abc123",
        tag_id_rc=0,
        ref_id_output="",
        ref_id_rc=0,
    )
    check("AC1 exits 0", r.returncode == 0, r.stderr)
    check("AC1 emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac2_matching_image() -> None:
    """AC2: Matching image → no-op."""
    print("\n[task_015 AC2: matching image → no-op]")
    # Both normalised ids are the same
    shared_id = "sha256:abc123def456"
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:abc123def456",  # container ref
        cref_rc=0,
        tag_id_output=shared_id,  # tag normalised id
        tag_id_rc=0,
        ref_id_output=shared_id,  # container ref normalised to same id
        ref_id_rc=0,
    )
    check("AC2 exits 0", r.returncode == 0, r.stderr)
    check("AC2 emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac3_drifted_image() -> None:
    """AC3: Drifted image → emit '1'."""
    print("\n[task_015 AC3: drifted image → emit '1']")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-image-digest",
        cref_rc=0,
        tag_id_output="sha256:new-image-digest",  # current image is different
        tag_id_rc=0,
        ref_id_output="sha256:old-image-digest",  # container's old image normalised
        ref_id_rc=0,
    )
    check("AC3 exits 0", r.returncode == 0, r.stderr)
    check("AC3 emits '1'", r.stdout.strip() == "1", f"output: {r.stdout}")


def test_ac4_remove_existing_flag_rebuild_true_drift_marker() -> None:
    """AC4a: (true, "1") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4a: (true, '1') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "true" "1"')
    check("AC4a exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]  # filter empty lines
    check("AC4a emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4a token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_ac4_remove_existing_flag_rebuild_true_no_drift() -> None:
    """AC4b: (true, "") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4b: (true, '') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "true" ""')
    check("AC4b exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]
    check("AC4b emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4b token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_ac4_remove_existing_flag_no_rebuild_drift_marker() -> None:
    """AC4c: (false, "1") → exactly one --remove-existing-container."""
    print("\n[task_015 AC4c: (false, '1') → one token]")
    r = _source_vibe_call({}, 'remove_existing_flag "false" "1"')
    check("AC4c exits 0", r.returncode == 0, r.stderr)
    lines = r.stdout.strip().split('\n')
    lines = [l for l in lines if l]
    check("AC4c emits exactly one line", len(lines) == 1, f"lines: {lines}")
    if len(lines) == 1:
        check("AC4c token is --remove-existing-container",
              lines[0] == "--remove-existing-container", f"got: {lines[0]}")


def test_task034_linux_host() -> None:
    """task_034 (Linux host support): every non-[L] acceptance criterion.
    AC1/AC2 (code-check.py / smoke-test.py themselves green) are asserted by
    the harness's own separate runs, not re-asserted here. AC12-14 are [L]
    (MANUAL-TESTS 44-50, need a real Linux box). Fixture builders live in
    smoke/_core.py (_task034_*) per the split-suite convention."""
    print("\n[task_034: Linux host support]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ── uname PATH shim proof (iteration-2 amendment) ───────────────────
        darwin_shim = _make_uname_shim(tmp, "Darwin")
        linux_shim = _make_uname_shim(tmp / "linux_side", "Linux")
        r = run(["bash", "-c", "uname -s"],
                env={**os.environ, "PATH": f"{darwin_shim}{os.pathsep}{os.environ.get('PATH', '')}"})
        check("[task034] uname shim shadows real uname (Darwin fixture)",
              r.stdout.strip() == "Darwin", r.stdout)
        r = run(["bash", "-c", "uname -s"],
                env={**os.environ, "PATH": f"{linux_shim}{os.pathsep}{os.environ.get('PATH', '')}"})
        check("[task034] uname shim shadows real uname (Linux fixture)",
              r.stdout.strip() == "Linux", r.stdout)

        # ── AC3 + AC4: render_devcontainer_with_mounts under the Darwin shim ──
        devcontainer_json = REPO / "devcontainer" / "devcontainer.json"
        mount_args = ["/host/brain2", "/brain2", "0", "/host/zotero", "/zotero", "1"]

        def _render(env_extra: dict, tag: str) -> dict:
            dst = tmp / f"out-{tag}.json"
            call = (f"render_devcontainer_with_mounts {shlex.quote(str(devcontainer_json))} "
                    f"{shlex.quote(str(dst))} " + " ".join(shlex.quote(a) for a in mount_args))
            env = {"PATH": f"{darwin_shim}{os.pathsep}{os.environ.get('PATH', '')}", **env_extra}
            r = _source_vibe_call(env, call)
            check(f"[task034] render ({tag}) exits 0", r.returncode == 0, r.stderr)
            return json.loads(dst.read_text()) if dst.exists() else {}

        cfg_off = _render({}, "op-off")
        run_args_off = cfg_off.get("runArgs", [])
        check("[task034 AC3] exactly one host.docker.internal add-host (/op off)",
              run_args_off.count("--add-host=host.docker.internal:host-gateway") == 1,
              str(run_args_off))

        cfg_on = _render({"VIBE_OP_ADDHOST": "op.example.ts.net"}, "op-on")
        run_args_on = cfg_on.get("runArgs", [])
        check("[task034 AC3] exactly one host.docker.internal add-host (/op on)",
              run_args_on.count("--add-host=host.docker.internal:host-gateway") == 1,
              str(run_args_on))
        check("[task034 AC3] /op's own add-host still present when configured",
              "--add-host=op.example.ts.net:host-gateway" in run_args_on, str(run_args_on))

        check("[task034 AC4] golden carries no host.docker.internal (contamination check)",
              "host.docker.internal" not in TASK034_GOLDEN_DEVCONTAINER_RENDER_OP_OFF,
              "golden constant is contaminated")
        golden_cfg = json.loads(TASK034_GOLDEN_DEVCONTAINER_RENDER_OP_OFF)
        expected_cfg = dict(golden_cfg)
        expected_cfg["runArgs"] = golden_cfg["runArgs"] + ["--add-host=host.docker.internal:host-gateway"]
        check("[task034 AC4] current Darwin render == golden + exactly one add-host line",
              cfg_off == expected_cfg,
              f"current runArgs={run_args_off}\nexpected runArgs={expected_cfg['runArgs']}")

        # ── AC5: Darwin exit-hook block byte-identical to baseline ──────────
        base_vibe, base_vibe_rc = _task034_baseline_text("vibe")
        check("[task034] git show 3b23b19:vibe exits 0", base_vibe_rc == 0, base_vibe[:200])
        cur_vibe = VIBE.read_text()
        start_anchor = 'if [[ "$(uname)" == "Darwin" ]] && command -v pbcopy >/dev/null 2>&1; then'
        end_anchor = 'kill "$WATCHER_PID" 2>/dev/null || true\''

        def _extract(src: str) -> str:
            i = src.find(start_anchor)
            if i == -1:
                return ""
            j = src.find(end_anchor, i)
            return src[i:j + len(end_anchor)] if j != -1 else ""

        base_block, cur_block = _extract(base_vibe), _extract(cur_vibe)
        check("[task034 AC5] Darwin exit-hook block found in both baseline and current",
              bool(base_block) and bool(cur_block), "")
        check("[task034 AC5] Darwin exit-hook block byte-identical to baseline",
              base_block == cur_block, "blocks differ")

        # ── AC6: vibe_clipboard_cmd precedence ───────────────────────────────
        mac_pbcopy = _task034_tool_dir(tmp, "mac_pbcopy", ["pbcopy"])
        mac_nopbcopy = _task034_tool_dir(tmp, "mac_nopbcopy", [])
        check("[task034 AC6] Darwin + pbcopy present -> 'pbcopy'",
              _task034_clipboard_cmd(darwin_shim, [mac_pbcopy]) == "pbcopy", "")
        check("[task034 AC6] Darwin + no pbcopy -> empty",
              _task034_clipboard_cmd(darwin_shim, [mac_nopbcopy]) == "", "")

        all_three = _task034_tool_dir(tmp, "linux_all3", ["wl-copy", "xclip", "xsel"])
        check("[task034 AC6] Linux wl-copy beats xclip/xsel -> 'wl-copy'",
              _task034_clipboard_cmd(linux_shim, [all_three]) == "wl-copy", "")
        xclip_xsel = _task034_tool_dir(tmp, "linux_xclip_xsel", ["xclip", "xsel"])
        check("[task034 AC6] Linux xclip (no wl-copy) beats xsel -> flagged clipboard invocation",
              _task034_clipboard_cmd(linux_shim, [xclip_xsel]) == "xclip -selection clipboard", "")
        xsel_only = _task034_tool_dir(tmp, "linux_xsel_only", ["xsel"])
        check("[task034 AC6] Linux xsel only -> flagged clipboard invocation",
              _task034_clipboard_cmd(linux_shim, [xsel_only]) == "xsel --clipboard --input", "")
        no_tools = _task034_tool_dir(tmp, "linux_none", [])
        check("[task034 AC6] Linux with no clipboard tool -> empty",
              _task034_clipboard_cmd(linux_shim, [no_tools]) == "", "")

        # ── AC7: watcher's 3-way gate (Darwin OR VIBE_COPY_CMD OR FORCE) ────
        env_quiet = {**os.environ, "PATH": f"{linux_shim}{os.pathsep}{os.environ.get('PATH', '')}"}
        env_quiet.pop("VIBE_COPY_WATCHER_FORCE", None)
        env_quiet.pop("VIBE_COPY_CMD", None)
        r = run(["bash", str(VIBE_COPY_WATCHER), str(tmp / "watcher-ws-quiet")], env=env_quiet)
        check("[task034 AC7] Linux, no FORCE, no VIBE_COPY_CMD -> exits 0 immediately",
              r.returncode == 0, f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
        # Mechanics-required: FORCE alone keeps it running (mirrors
        # test_vibe_path_prefix_isolation's reliance on FORCE alone).
        check("[task034 AC7] watcher (FORCE only) does not exit immediately",
              _task034_watcher_alive_after({"VIBE_COPY_WATCHER_FORCE": "1"},
                                            tmp / "watcher-ws-force", linux_shim), "")
        check("[task034 AC7] watcher (VIBE_COPY_CMD set, the Linux path) does not exit immediately",
              _task034_watcher_alive_after({"VIBE_COPY_CMD": "true"},
                                            tmp / "watcher-ws-copycmd", linux_shim), "")

        # ── AC8: install.sh Darwin output byte-identical to pre-change ─────
        base_install, base_install_rc = _task034_baseline_text("install.sh")
        check("[task034] git show 3b23b19:install.sh exits 0", base_install_rc == 0, base_install[:200])
        out_base = _task034_run_install(base_install, tmp / "install-base-home", darwin_shim)
        out_cur = _task034_run_install(INSTALL.read_text(), tmp / "install-cur-home", darwin_shim)
        check("[task034 AC8] install.sh Darwin output byte-identical to pre-change",
              out_base == out_cur, f"--- baseline ---\n{out_base}\n--- current ---\n{out_cur}")

        # ── AC9: Linux preflight — apt/dnf hints, docker group, devcontainer ─
        install_src = INSTALL.read_text()
        for literal in ("preflight_linux", "vibe_linux_pkg", "docker info",
                         "id -nG", "usermod -aG docker", "docker-ce", "devcontainer missing"):
            check(f"[task034 AC9] install.sh mentions {literal!r}", literal in install_src, "")

        r = _task034_run_install_linux("apt", in_group=False, home=tmp / "install-linux-nogroup")
        out = r.stdout + r.stderr
        check("[task034 AC9] docker-group warning fires when not in group",
              "is not in the 'docker' group" in out, out)
        check("[task034 AC9] docker-group warning names the remedy",
              "usermod -aG docker" in out, out)
        check("[task034 AC9] docker-group warning is non-fatal (exit 0)",
              r.returncode == 0, f"rc={r.returncode}\n{out}")

        r2 = _task034_run_install_linux("dnf", in_group=True, home=tmp / "install-linux-group")
        out2 = r2.stdout + r2.stderr
        check("[task034 AC9] no docker-group warning when already in group",
              "is not in the 'docker' group" not in out2, out2)
        check("[task034 AC9] dnf hints present for Fedora/RHEL", "sudo dnf install" in out2, out2)

        # set -e safety amendment: empty PATH must not abort the script.
        empty_home = tmp / "install-empty-path-home"
        empty_home.mkdir()
        empty_bin = tmp / "empty-path-bin"
        empty_bin.mkdir()
        r3 = run(["/bin/bash", str(INSTALL)], env={"HOME": str(empty_home), "PATH": str(empty_bin)})
        out3 = r3.stdout + r3.stderr
        check("[task034] empty-PATH run reaches the preflight failure message (no early abort)",
              "Install the missing dependencies" in out3, out3)
        check("[task034] empty-PATH run falls back to Darwin hints, not a crash",
              "xcode-select" in out3 or "brew install" in out3, out3)

        # ── AC10: Dockerfile nsswitch sed is idempotent ─────────────────────
        dockerfile_src = DOCKERFILE.read_text()
        m = re.search(r"sed -i '([^']+)' /etc/nsswitch\.conf", dockerfile_src)
        check("[task034 AC10] Dockerfile nsswitch sed expression found", m is not None, dockerfile_src[:2000])
        if m:
            sed_expr = m.group(1)
            nss = tmp / "nsswitch.conf"
            nss.write_text("hosts:          files dns\n")
            r = run(["sed", "-i", sed_expr, str(nss)])
            check("[task034 AC10] first sed application exits 0", r.returncode == 0, r.stderr)
            check("[task034 AC10] one mdns4_minimal entry after first apply",
                  nss.read_text().count("mdns4_minimal") == 1, nss.read_text())
            r = run(["sed", "-i", sed_expr, str(nss)])
            check("[task034 AC10] second sed application exits 0", r.returncode == 0, r.stderr)
            check("[task034 AC10] still exactly one mdns4_minimal entry after second apply (idempotent)",
                  nss.read_text().count("mdns4_minimal") == 1, nss.read_text())

        # ── mDNS probe: warns once with the spec's literal, then stays silent ─
        mdns_bin = _task034_tool_dir(tmp, "mdns_bin", [])
        (mdns_bin / "getent").write_text("#!/bin/sh\nexit 1\n")
        (mdns_bin / "getent").chmod(0o755)
        (mdns_bin / "hostname").write_text("#!/bin/sh\necho testhost\n")
        (mdns_bin / "hostname").chmod(0o755)
        marker = tmp / "mdns-marker"
        env_probe = {
            "VIBE_MDNS_MARKER": str(marker),
            "PATH": f"{linux_shim}{os.pathsep}{mdns_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        r = _source_vibe_call(env_probe, "vibe_mdns_probe")
        check("[task034] mDNS probe function exists and runs cleanly", r.returncode == 0, r.stderr)
        check("[task034] mDNS probe warns with the spec's literal on failure",
              "mDNS: this host cannot resolve" in r.stdout, r.stdout)
        check("[task034] mDNS probe names the host.docker.internal fallback",
              "host.docker.internal" in r.stdout, r.stdout)
        check("[task034] mDNS probe drops a marker after warning", marker.exists(), "")
        r2m = _source_vibe_call(env_probe, "vibe_mdns_probe")
        check("[task034] mDNS probe is silent on the second (marker-gated) call",
              "mDNS" not in r2m.stdout, r2m.stdout)

        # ── Docs: README / ONBOARDING / MANUAL-TESTS ────────────────────────
        readme = (REPO / "README.md").read_text()
        check("[task034] README has a Linux hosts section", "## Linux hosts" in readme, "")
        check("[task034] README names the reference platform",
              "Ubuntu 24.04 LTS with Docker Engine" in readme, "")
        check("[task034] README documents the host.docker.internal add-host",
              "--add-host=host.docker.internal:host-gateway" in readme, "")
        check("[task034] README marks the build bridge macOS-only", "macOS-only" in readme, "")

        onboarding = (REPO / "ONBOARDING.md").read_text()
        check("[task034] ONBOARDING forks steps by platform",
              "Mac only" in onboarding and "Linux only" in onboarding, "")
        check("[task034] ONBOARDING names Ubuntu 24.04 LTS with Docker Engine",
              "Ubuntu 24.04 LTS with Docker Engine" in onboarding, "")

        manual_tests = (REPO / "MANUAL-TESTS.md").read_text()
        check("[task034] MANUAL-TESTS has the Linux host section",
              "## Linux host (Ubuntu 24.04 LTS)" in manual_tests, "")
        check("[task034] MANUAL-TESTS names the [L] acceptance criteria",
              "`[L]` acceptance criteria" in manual_tests, "")
        for n in range(44, 51):
            check(f"[task034] MANUAL-TESTS has Test {n}", f"### Test {n}:" in manual_tests, "")
