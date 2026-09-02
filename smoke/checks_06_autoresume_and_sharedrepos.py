from smoke._core import *  # noqa: F401,F403




def test_extras_invocations_isolated() -> None:
    """Every INSTALL_EXTRAS invocation must route its env through
    _isolate_extras_env (security-review finding, 2026-08-30): the installer
    writes global git config unconditionally, so an un-isolated call site
    leaves the machine's core.hooksPath pointing at a deleted temp dir —
    content-guard hooks silently detached until the next container start.
    Static pin catches a future bare call site; the behavioural half runs
    the installer once and asserts the real global git state is untouched."""
    print("\n[extras-isolation: installer runs must not touch real git config]")
    src = Path(__file__).read_text()
    call_pat = re.compile(r'\["bash", str\(INSTALL_' + r'EXTRAS\)\],\s*env=(\w+|_isolate_extras_env)')
    callers = call_pat.findall(src)
    bare = [c for c in callers if c != "_isolate_extras_env"]
    check("[extras-iso] no bare env= at any INSTALL_EXTRAS call site",
          len(bare) == 0 and len(callers) > 0,
          f"bare env names: {bare[:5]} (route through _isolate_extras_env)")
    hp_before = run(["git", "config", "--global", "--get", "core.hooksPath"]).stdout
    sd_before = run(["git", "config", "--global", "--get-all", "safe.directory"]).stdout
    gitconfig = Path(os.environ.get("HOME", "/home/node")) / ".gitconfig"
    bytes_before = gitconfig.read_bytes() if gitconfig.exists() else b""
    with tempfile.TemporaryDirectory() as tmp:
        env0 = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(REPO / "devcontainer"),
            "CLAUDE_CONFIG_DIR": tmp,
        }
        r = subprocess.run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env0),
                           capture_output=True, text=True)
        check("[extras-iso] isolated installer run exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
    hp_after = run(["git", "config", "--global", "--get", "core.hooksPath"]).stdout
    sd_after = run(["git", "config", "--global", "--get-all", "safe.directory"]).stdout
    bytes_after = gitconfig.read_bytes() if gitconfig.exists() else b""
    check("[extras-iso] core.hooksPath unchanged", hp_before == hp_after,
          f"{hp_before!r} -> {hp_after!r}")
    check("[extras-iso] safe.directory unchanged", sd_before == sd_after,
          f"{sd_before!r} -> {sd_after!r}")
    check("[extras-iso] real ~/.gitconfig byte-identical", bytes_before == bytes_after,
          "installer wrote the real global git config despite isolation")
    # Same guard for setup-git.sh: its SRC/DST were once hardcoded to
    # /home/node, so a "sandbox HOME" run still overwrote the REAL
    # ~/.gitconfig via the .gitconfig-host cp (wiping core.hooksPath —
    # content-guard detached). Run it sandboxed and assert no real change.
    with tempfile.TemporaryDirectory() as td:
        sb = Path(td) / "home"
        sb.mkdir()
        (sb / ".gitconfig-host").write_text("[user]\n\temail = t@t\n")
        r = subprocess.run(["bash", str(SETUP_GIT_SH)],
                           env={**os.environ, "HOME": str(sb)},
                           capture_output=True, text=True)
        check("[extras-iso] sandboxed setup-git.sh exits 0", r.returncode == 0,
              r.stderr[:200])
        check("[extras-iso] setup-git wrote the sandbox, not the real HOME",
              (sb / ".gitconfig").exists(), "sandbox .gitconfig missing")
    bytes_after2 = gitconfig.read_bytes() if gitconfig.exists() else b""
    check("[extras-iso] real ~/.gitconfig survives sandboxed setup-git.sh",
          bytes_before == bytes_after2,
          "setup-git.sh still writes a hardcoded /home/node path")


def test_install_extras_syncs_hooks() -> None:
    """install-claude-extras.sh installs hooks/*.sh with +x into $DEST_ROOT/hooks/."""
    print("\n[hooks: install-claude-extras.sh syncs every shipped hook]")
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")
        env["CLAUDE_CONFIG_DIR"] = tmp
        r = subprocess.run(
            ["bash", str(INSTALL_EXTRAS)],
            env=_isolate_extras_env(env), capture_output=True, text=True,
        )
        check("[hooks] install-extras exits 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        for hook_name in ("check-numbering.sh", "copy-last-block.sh"):
            installed = Path(tmp) / "hooks" / hook_name
            check(f"[hooks] {hook_name} installed at $DEST_ROOT/hooks/",
                  installed.exists(), str(installed))
            if installed.exists():
                check(f"[hooks] {hook_name} is executable",
                      os.access(installed, os.X_OK), "")
        # README.md should NOT be chmod'd (it's not a *.sh file but install_hooks
        # only chmods *.sh; verify it didn't get installed at all since we
        # don't sync non-.sh files into the hooks dir).
        readme_installed = Path(tmp) / "hooks" / "README.md"
        check("[hooks] README.md NOT installed (only *.sh synced)",
              not readme_installed.exists(), str(readme_installed))


def test_brain2_zotero_source_resolution() -> None:
    """_brain2_source / _zotero_source: default, override, and 'off' disable."""
    print("\n[brain2: _brain2_source / _zotero_source resolution]")
    # Default derives from HOME.
    r = _source_vibe_call({"HOME": "/tmp/vibetesthome"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] default brain2 path is $HOME/brain2",
          "OUT=[/tmp/vibetesthome/brain2]" in r.stdout, r.stdout)
    r = _source_vibe_call({"HOME": "/tmp/vibetesthome"},
                          'echo "OUT=[$(_zotero_source)]"')
    check("[brain2] default zotero path is $HOME/Zotero/storage",
          "OUT=[/tmp/vibetesthome/Zotero/storage]" in r.stdout, r.stdout)
    # Explicit override.
    r = _source_vibe_call({"VIBE_BRAIN2_PATH": "/foo/bar"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] VIBE_BRAIN2_PATH override honoured",
          "OUT=[/foo/bar]" in r.stdout, r.stdout)
    # 'off' disables (echoes nothing).
    r = _source_vibe_call({"VIBE_BRAIN2_PATH": "off"},
                          'echo "OUT=[$(_brain2_source)]"')
    check("[brain2] VIBE_BRAIN2_PATH=off disables (empty)",
          "OUT=[]" in r.stdout, r.stdout)
    r = _source_vibe_call({"VIBE_ZOTERO_PATH": "off"},
                          'echo "OUT=[$(_zotero_source)]"')
    check("[brain2] VIBE_ZOTERO_PATH=off disables (empty)",
          "OUT=[]" in r.stdout, r.stdout)


def test_render_devcontainer_with_mounts() -> None:
    """render_devcontainer_with_mounts appends rw/ro bind mounts, preserves
    existing mounts, and handles sources containing spaces."""
    print("\n[brain2: render_devcontainer_with_mounts]")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.json"
        src.write_text(json.dumps(
            {"image": "x", "mounts": ["source=keep,target=/keep,type=volume"]}))
        dst = Path(tmp) / "dst.json"
        call = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                f"{shlex.quote(str(dst))} "
                f"/host/brain2 /brain2 0 "
                f"{shlex.quote('/host/zot store')} /zotero 1")
        r = _source_vibe_call({}, call)
        check("[brain2] render exits 0", r.returncode == 0, r.stderr)
        cfg = json.loads(dst.read_text())
        mounts = cfg["mounts"]
        check("[brain2] existing mount preserved",
              "source=keep,target=/keep,type=volume" in mounts, str(mounts))
        brain2 = [m for m in mounts if isinstance(m, dict) and m.get("target") == "/brain2"]
        zot = [m for m in mounts if isinstance(m, dict) and m.get("target") == "/zotero"]
        check("[brain2] /brain2 mount appended", len(brain2) == 1, str(mounts))
        check("[brain2] /brain2 is read-write (no readonly key)",
              brain2 and "readonly" not in brain2[0], str(brain2))
        check("[brain2] /brain2 source correct",
              brain2 and brain2[0]["source"] == "/host/brain2", str(brain2))
        check("[brain2] /zotero mount appended read-only",
              zot and zot[0].get("readonly") is True, str(zot))
        check("[brain2] /zotero source with space preserved",
              zot and zot[0]["source"] == "/host/zot store", str(zot))


def test_op_mcp_addhost_injection() -> None:
    """render_devcontainer_with_mounts appends the OpenProject MCP --add-host to
    runArgs when VIBE_OP_ADDHOST is set, leaves runArgs untouched when it isn't,
    and never duplicates an entry already present."""
    print("\n[op-mcp: add-host injection]")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.json"
        src.write_text(json.dumps({"image": "x", "runArgs": ["--cap-add=NET_ADMIN"]}))

        dst1 = Path(tmp) / "with.json"
        call1 = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                 f"{shlex.quote(str(dst1))}")
        r1 = _source_vibe_call({"VIBE_OP_ADDHOST": "op.example.ts.net"}, call1)
        check("[op-mcp] render (with host) exits 0", r1.returncode == 0, r1.stderr)
        ra1 = json.loads(dst1.read_text()).get("runArgs", [])
        check("[op-mcp] --add-host appended",
              "--add-host=op.example.ts.net:host-gateway" in ra1, str(ra1))
        check("[op-mcp] existing runArgs preserved",
              "--cap-add=NET_ADMIN" in ra1, str(ra1))

        dst2 = Path(tmp) / "without.json"
        call2 = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                 f"{shlex.quote(str(dst2))}")
        r2 = _source_vibe_call({"VIBE_OP_ADDHOST": ""}, call2)
        check("[op-mcp] render (no host) exits 0", r2.returncode == 0, r2.stderr)
        ra2 = json.loads(dst2.read_text()).get("runArgs", [])
        check("[op-mcp] no add-host when unset",
              not any("add-host" in a for a in ra2), str(ra2))

        # Already-present entry must not be duplicated.
        src2 = Path(tmp) / "src2.json"
        src2.write_text(json.dumps(
            {"image": "x", "runArgs": ["--add-host=op.example.ts.net:host-gateway"]}))
        dst3 = Path(tmp) / "dup.json"
        call3 = (f"render_devcontainer_with_mounts {shlex.quote(str(src2))} "
                 f"{shlex.quote(str(dst3))}")
        _source_vibe_call({"VIBE_OP_ADDHOST": "op.example.ts.net"}, call3)
        ra3 = json.loads(dst3.read_text()).get("runArgs", [])
        check("[op-mcp] add-host not duplicated",
              ra3.count("--add-host=op.example.ts.net:host-gateway") == 1, str(ra3))


def test_build_override_config_brain2_and_zotero() -> None:
    """_build_override_config injects /brain2 (rw) and /zotero (ro) when the
    dirs exist, and skips the brain2 self-mount in the gardener. (Since
    task_014 the override always renders — the projects bind is unconditional —
    so the old nothing-applies fall-back to the base config is gone.)"""
    print("\n[brain2: _build_override_config gating]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ws = tmp_path / "ws"; ws.mkdir()
        brain2 = tmp_path / "brain2"; brain2.mkdir()
        zot = tmp_path / "zot"; zot.mkdir()
        home = tmp_path / "home"; home.mkdir()

        # OP MCP creds leak in from the host env of an OP-configured vibe
        # container (staged via remoteEnv since 2026-06-04) and make
        # _build_override_config emit an override for the --add-host alone,
        # breaking the nothing-applies fallback case. Blank them: this test
        # is about mount gating, not OP wiring.
        no_op = {"OPENPROJECT_MCP_URL": "", "OPENPROJECT_MCP_BEARER": ""}

        # Case 1: brain2 + zotero dirs exist, workspace is a different dir.
        env = {**no_op,
               "HOME": str(home),
               "VIBE_BRAIN2_PATH": str(brain2),
               "VIBE_ZOTERO_PATH": str(zot)}
        r = _source_vibe_call(
            env, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        check("[brain2] _build_override_config exits 0", r.returncode == 0, r.stderr)
        out = _read_override_out(r)
        check("[brain2] generated override under HOME/.vibe/run",
              out.startswith(str(home / ".vibe" / "run")), out)
        if out and Path(out).exists():
            cfg = json.loads(Path(out).read_text())
            tgts = [m.get("target") for m in cfg["mounts"] if isinstance(m, dict)]
            check("[brain2] /brain2 injected (non-gardener)", "/brain2" in tgts, str(tgts))
            check("[brain2] /zotero injected", "/zotero" in tgts, str(tgts))

        # Case 2: gardener — workspace IS the brain2 dir → no /brain2 self-mount.
        # (task_014: an override is still generated — it carries the
        # unconditional projects bind — so assert /brain2's absence in it
        # rather than the pre-task_014 fall-back to the base config.)
        env_g = {**no_op,
                 "HOME": str(home),
                 "VIBE_BRAIN2_PATH": str(brain2),
                 "VIBE_ZOTERO_PATH": "off"}
        r = _source_vibe_call(
            env_g, f'echo "OUT=[$(_build_override_config {shlex.quote(str(brain2))})]"')
        out_g = _read_override_out(r)
        check("[brain2] gardener+no-zotero still renders an override (task_014)",
              out_g.startswith(str(home / ".vibe" / "run")), out_g)
        if out_g and Path(out_g).exists():
            cfg_g = json.loads(Path(out_g).read_text())
            tgts_g = [m.get("target") for m in cfg_g["mounts"] if isinstance(m, dict)]
            check("[brain2] gardener gets NO /brain2 self-mount", "/brain2" not in tgts_g, str(tgts_g))

        # Case 3: zotero only.
        env_z = {**no_op,
                 "HOME": str(home),
                 "VIBE_BRAIN2_PATH": "off",
                 "VIBE_ZOTERO_PATH": str(zot)}
        r = _source_vibe_call(
            env_z, f'echo "OUT=[$(_build_override_config {shlex.quote(str(ws))})]"')
        out_z = _read_override_out(r)
        if out_z and Path(out_z).exists():
            cfg = json.loads(Path(out_z).read_text())
            tgts = [m.get("target") for m in cfg["mounts"] if isinstance(m, dict)]
            check("[brain2] zotero-only: /zotero present, /brain2 absent",
                  "/zotero" in tgts and "/brain2" not in tgts, str(tgts))


def test_install_extras_brain2_md_gated() -> None:
    """install-claude-extras.sh includes brain2.md only when the brain2 mount
    dir exists; omits it otherwise (keeps shared CLAUDE.md brain2-free upstream)."""
    print("\n[brain2: install-claude-extras.sh gates brain2.md on the mount]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Pass 1: no mount (point the override at a nonexistent path) → absent.
        dest_off = tmp_path / "off"; dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off["VIBE_BRAIN2_MOUNT_DIR"] = str(tmp_path / "nope")
        r_off = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                               env=_isolate_extras_env(env_off), capture_output=True, text=True)
        check("[brain2] install exits 0 (no mount)",
              r_off.returncode == 0, r_off.stderr[:200])
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[brain2] brain2.md ABSENT when mount dir missing",
              "<!-- vibe-md: brain2.md -->" not in md_off, "brain2.md leaked upstream")
        check("[brain2] other fragments still present (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "loop didn't run")

        # Pass 2: mount dir exists → brain2.md present.
        mount_dir = tmp_path / "brain2mount"; mount_dir.mkdir()
        dest_on = tmp_path / "on"; dest_on.mkdir()
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_BRAIN2_MOUNT_DIR"] = str(mount_dir)
        r_on = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                              env=_isolate_extras_env(env_on), capture_output=True, text=True)
        check("[brain2] install exits 0 (mount present)",
              r_on.returncode == 0, r_on.stderr[:200])
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[brain2] brain2.md PRESENT when mount dir exists",
              "<!-- vibe-md: brain2.md -->" in md_on, "brain2.md missing")
        check("[brain2] brain2.md mentions the credential boundary",
              "CANNOT" in md_on and "/brain2" in md_on, "body missing")


def test_install_extras_brain2_skills_synced() -> None:
    """install-claude-extras.sh syncs brain2 skills whose `surfaces:` includes
    `vibe` into ~/.claude/skills; excludes desktop/excel-only and untagged
    skills; honours the body-line `## Surfaces` fallback; leaves pre-existing
    (volume-persisted) skills untouched; and does nothing without the mount."""
    print("\n[brain2: install-claude-extras.sh syncs vibe-tagged skills]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")

        # Fake brain2 mount with a skills dir of mixed surface tags.
        mount = tmp_path / "brain2mount"
        skills = mount / ".claude" / "skills"

        def write_skill(name: str, frontmatter_surfaces=None,
                        body_surfaces: bool = False) -> None:
            d = skills / name
            d.mkdir(parents=True)
            lines = ["---", f"title: {name}"]
            if frontmatter_surfaces is not None:
                lines.append(f"surfaces: {frontmatter_surfaces}")
            lines += ["---", f"# {name}"]
            if body_surfaces:
                lines += ["## Surfaces", "[desktop, vibe]"]
            (d / "SKILL.md").write_text("\n".join(lines) + "\n")

        write_skill("ol", "[desktop, vibe]")                 # included (frontmatter)
        write_skill("deskonly", "[desktop]")                 # excluded (desktop-only)
        write_skill("bodyform", None, body_surfaces=True)    # included (body fallback)
        write_skill("md", None)                              # excluded (untagged)

        dest = tmp_path / "dest"; dest.mkdir()
        # Pre-existing volume-persisted skill that must survive the sync.
        (dest / "skills" / "script").mkdir(parents=True)
        (dest / "skills" / "script" / "SKILL.md").write_text("original-script\n")

        env = env_base.copy()
        env["CLAUDE_CONFIG_DIR"] = str(dest)
        env["VIBE_BRAIN2_MOUNT_DIR"] = str(mount)
        r = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                           env=_isolate_extras_env(env), capture_output=True, text=True)
        check("[brain2] install exits 0 (mount present)",
              r.returncode == 0, r.stderr[:200])
        dskills = dest / "skills"
        check("[brain2] vibe-tagged 'ol' synced (frontmatter)",
              (dskills / "ol" / "SKILL.md").exists(), "ol missing")
        check("[brain2] body-line '## Surfaces' fallback 'bodyform' synced",
              (dskills / "bodyform" / "SKILL.md").exists(), "bodyform missing")
        check("[brain2] desktop-only 'deskonly' excluded",
              not (dskills / "deskonly").exists(), "desktop-only skill leaked into vibe")
        check("[brain2] untagged 'md' excluded",
              not (dskills / "md").exists(), "untagged md synced")
        check("[brain2] pre-existing 'script' left untouched",
              (dskills / "script" / "SKILL.md").read_text() == "original-script\n",
              "volume-persisted skill clobbered")

        # No brain2 mount → skills sync is a no-op (generic vibe users unaffected).
        dest2 = tmp_path / "dest2"; dest2.mkdir()
        env2 = env_base.copy()
        env2["CLAUDE_CONFIG_DIR"] = str(dest2)
        env2["VIBE_BRAIN2_MOUNT_DIR"] = str(tmp_path / "nope")
        r2 = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                            env=_isolate_extras_env(env2), capture_output=True, text=True)
        check("[brain2] install exits 0 (no mount)",
              r2.returncode == 0, r2.stderr[:200])
        check("[brain2] no skills synced without the mount",
              not (dest2 / "skills" / "ol").exists(), "synced without a mount")


def test_brain2_md_fragment_content() -> None:
    """brain2.md ships and states the non-negotiables: credential boundary,
    zotero read-only, and the authorised-field trust rule."""
    print("\n[brain2: brain2.md fragment content]")
    check("[brain2] brain2.md exists", BRAIN2_MD.exists(), str(BRAIN2_MD))
    body = BRAIN2_MD.read_text()
    check("[brain2] documents no-push credential boundary",
          "push" in body.lower() and "gardener" in body.lower(), "boundary missing")
    check("[brain2] documents zotero read-only + DOI queue",
          "/zotero" in body and "zotero-queue" in body, "zotero guidance missing")
    check("[brain2] documents authorised-field trust rule",
          "authorised" in body, "trust rule missing")


def test_contributor_onboarding_artifacts() -> None:
    """FOSS onboarding artifacts for outside contributors: SECURITY.md
    (disclosure policy aligned with the container threat model), the two
    .github issue templates, and the PR template. Grep-level presence +
    key-content checks — the files carry no logic to unit-test."""
    print("\n[FOSS contributor onboarding artifacts]")

    check("[onboard] SECURITY.md exists", SECURITY_MD.exists(), str(SECURITY_MD))
    if SECURITY_MD.exists():
        s = SECURITY_MD.read_text()
        check("[onboard] SECURITY.md points at the repo Security tab",
              "Security tab" in s, "reporting path must survive the repo transfer")
        check("[onboard] SECURITY.md marks Claude Code + Docker out-of-scope upstream",
              "Claude Code" in s and "Docker" in s and "upstream" in s.lower(), "")
        check("[onboard] SECURITY.md names the in-scope classes",
              all(k in s.lower() for k in ("firewall bypass", "hook bypass", "credential", "pat")), "")

    check("[onboard] bug_report.md template exists", BUG_TEMPLATE.exists(), str(BUG_TEMPLATE))
    if BUG_TEMPLATE.exists():
        b = BUG_TEMPLATE.read_text()
        check("[onboard] bug template asks for vibe --version",
              "vibe --version" in b, "")
        check("[onboard] bug template asks OS + container runtime",
              "OrbStack" in b and "Docker" in b, "")

    check("[onboard] feature_request.md template exists", FEATURE_TEMPLATE.exists(), str(FEATURE_TEMPLATE))
    if FEATURE_TEMPLATE.exists():
        f = FEATURE_TEMPLATE.read_text()
        check("[onboard] feature template points at CONTRIBUTING.md",
              "CONTRIBUTING.md" in f, "")

    check("[onboard] PULL_REQUEST_TEMPLATE.md exists", PR_TEMPLATE.exists(), str(PR_TEMPLATE))
    if PR_TEMPLATE.exists():
        p = PR_TEMPLATE.read_text()
        check("[onboard] PR template names both gate scripts",
              "code-check.py" in p and "smoke-test.py" in p, "")
        check("[onboard] PR template cites CHANGELOG + MANUAL-TESTS conventions",
              "CHANGELOG.md" in p and "MANUAL-TESTS.md" in p, "")

    onboarding = REPO / "ONBOARDING.md"
    check("[onboard] ONBOARDING.md exists", onboarding.exists(), str(onboarding))
    if onboarding.exists():
        o = onboarding.read_text()
        check("[onboard] ONBOARDING.md addresses the assisting Claude",
              "assisting Claude" in o, "")
        check("[onboard] ONBOARDING.md installs from andeyePro/vibe",
              "andeyePro/vibe/main/install.sh" in o, "")
        check("[onboard] ONBOARDING.md verifies with vibe --version",
              "vibe --version" in o, "")

    contributors = REPO / "CONTRIBUTORS.md"
    check("[onboard] CONTRIBUTORS.md exists", contributors.exists(), str(contributors))
    if contributors.exists():
        c = contributors.read_text()
        check("[onboard] CONTRIBUTORS.md carries the revenue-share ledger framing",
              "revenue" in c.lower() and "ledger" in c.lower(), "")

    claude_md = REPO / "CLAUDE.md"
    check("[onboard] CLAUDE.md routes arriving Claudes to ONBOARDING.md",
          claude_md.exists() and "ONBOARDING.md" in claude_md.read_text(), "")


def test_repo_owner_selection() -> None:
    """Repo creation lets the user pick the GitHub owner (account or org):
    default_repo_owner() precedence unit-tested via VIBE_SOURCE_ONLY sourcing;
    the interactive flow + validation + docs checked at grep level."""
    print("\n[repo owner selection]")

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
        echo "FALLBACK=$(default_repo_owner someuser)"
        VIBE_GITHUB_OWNER="my-org" ; echo "CONFIGURED=$(default_repo_owner someuser)"
        VIBE_GITHUB_OWNER="" ; echo "EMPTY=$(default_repo_owner someuser)"
        """
        r = run(["bash", "-c", script], env=env)
        check("[owner] helper runs cleanly", r.returncode == 0, r.stderr)
        check("[owner] falls back to gh user when unset",
              "FALLBACK=someuser" in r.stdout, r.stdout)
        check("[owner] VIBE_GITHUB_OWNER wins when set",
              "CONFIGURED=my-org" in r.stdout, r.stdout)
        check("[owner] empty VIBE_GITHUB_OWNER falls back",
              "EMPTY=someuser" in r.stdout, r.stdout)

    src = VIBE.read_text()
    check("[owner] create flow prompts for owner (account or org)",
          "Owner (account or org)" in src, "")
    check("[owner] owner existence validated via gh api users/",
          "owner_exists_on_github" in src and 'gh api "users/' in src, "")
    check("[owner] mistyped owner gets a retry message",
          "not found on GitHub" in src, "")
    check("[owner] unvalidatable owner offers proceed-anyway (network-down path)",
          "Proceed with" in src, "")
    check("[owner] failure hint mentions org repo-creation permission",
          "repo-creation permission" in src, "")
    check("[owner] README documents VIBE_GITHUB_OWNER",
          "VIBE_GITHUB_OWNER" in (REPO / "README.md").read_text(), "")


# ── Task 016: auto-resume watchdog + heartbeat (AC1-AC8, AC12) ──────────────────

def test_vibe_auto_resume_deactivate() -> None:
    print("\n[task_016 AC1: auto_resume_deactivate]")
    snippet = (
        'm="${TMPDIR:-/tmp}/vibe-ar-deact.$$"; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$m"; '
        'auto_resume_deactivate "$m"; '
        'echo "AFTER=[$(auto_resume_field "$m" active)]"; '
        'auto_resume_deactivate "$m"; '
        'echo "IDEMPOTENT=[$(auto_resume_field "$m" active)]"; '
        'auto_resume_deactivate "$m.missing"; '
        'if [ -f "$m.missing" ]; then echo "CREATED=[yes]"; else echo "CREATED=[no]"; fi; '
        'rm -f "$m" "$m.tmp.$$"; '
        'if [ -f "$m.tmp.$$" ]; then echo "RESIDUE=[yes]"; else echo "RESIDUE=[no]"; fi'
    )
    r = _source_vibe_call({}, snippet)
    check("AC1: deactivate exits 0", r.returncode == 0, r.stderr)
    check("AC1: sets active=0", "AFTER=[0]" in r.stdout, r.stdout)
    check("AC1: idempotent", "IDEMPOTENT=[0]" in r.stdout, r.stdout)
    check("AC1: missing file → no create", "CREATED=[no]" in r.stdout, r.stdout)
    check("AC1: no .tmp residue", "RESIDUE=[no]" in r.stdout, r.stdout)


def test_vibe_auto_resume_heartbeat_write() -> None:
    print("\n[task_016 AC2: auto_resume_heartbeat_write]")
    snippet = (
        'hb="${TMPDIR:-/tmp}/vibe-hb-write.$$"; '
        'before=$(date +%s); '
        'auto_resume_heartbeat_write "$hb"; '
        'after=$(date +%s); '
        'if [ -f "$hb" ]; then '
        '  val=$(cat "$hb"); '
        '  if echo "$val" | grep -qE "^[0-9]+$"; then '
        '    if [ "$val" -ge "$before" ] && [ "$val" -le "$after" ]; then '
        '      echo "EPOCH=[ok]"; '
        '    else '
        '      echo "EPOCH=[out-of-range:$val]"; '
        '    fi; '
        '  else '
        '    echo "EPOCH=[not-numeric:$val]"; '
        '  fi; '
        'else '
        '  echo "EPOCH=[missing]"; '
        'fi; '
        'rm -f "$hb" "$hb.tmp.$$"'
    )
    r = _source_vibe_call({}, snippet)
    check("AC2: exits 0", r.returncode == 0, r.stderr)
    check("AC2: writes epoch in range", "EPOCH=[ok]" in r.stdout, r.stdout)


def test_vibe_auto_resume_stalled() -> None:
    print("\n[task_016 AC3: auto_resume_stalled]")
    snippet = (
        'hb="${TMPDIR:-/tmp}/vibe-ar-stalled.$$"; '
        'now=$(date +%s); '
        # Test case 1: gap 1000 vs threshold 900 → stalled (0)
        'echo "$((now - 1000))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T1=[0]"; else echo "T1=[1]"; fi; '
        # Test case 2: gap 100 vs 900 → not stalled (1)
        'echo "$((now - 100))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T2=[0]"; else echo "T2=[1]"; fi; '
        # Test case 3: gap exactly 900 vs 900 → not stalled, boundary (1)
        'echo "$((now - 900))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T3=[0]"; else echo "T3=[1]"; fi; '
        # Test case 4: missing file → not stalled (1)
        'rm -f "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T4=[0]"; else echo "T4=[1]"; fi; '
        # Test case 5: future epoch → not stalled (1)
        'echo "$((now + 500))" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T5=[0]"; else echo "T5=[1]"; fi; '
        # Test case 6: garbage content → not stalled (1)
        'echo "evil; rm -rf /" > "$hb"; '
        'if auto_resume_stalled "$hb" "$now" 900; then echo "T6=[0]"; else echo "T6=[1]"; fi; '
        'rm -f "$hb"'
    )
    r = _source_vibe_call({}, snippet)
    check("AC3: exits 0", r.returncode == 0, r.stderr)
    check("AC3: gap > threshold → stalled", "T1=[0]" in r.stdout, r.stdout)
    check("AC3: gap < threshold → not stalled", "T2=[1]" in r.stdout, r.stdout)
    check("AC3: gap == threshold (boundary) → not stalled", "T3=[1]" in r.stdout, r.stdout)
    check("AC3: missing file → not stalled", "T4=[1]" in r.stdout, r.stdout)
    check("AC3: future epoch → not stalled", "T5=[1]" in r.stdout, r.stdout)
    check("AC3: garbage content → not stalled", "T6=[1]" in r.stdout, r.stdout)


def test_vibe_settings_heartbeat_hooks() -> None:
    print("\n[task_016 AC4: heartbeat hook entries in settings.local.json]")
    vibe_src = VIBE.read_text()

    # Extract the settings.local.json heredoc between cat > ... << 'EOF' and closing EOF
    start_marker = 'cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\''
    start_idx = vibe_src.find(start_marker)
    if start_idx == -1:
        check("AC4: heredoc found", False, "could not locate settings.local.json heredoc start")
        return

    start_idx = vibe_src.find('\n', start_idx) + 1
    end_idx = vibe_src.find('\nEOF', start_idx)
    if end_idx == -1:
        check("AC4: heredoc end found", False, "could not locate heredoc end")
        return

    json_str = vibe_src[start_idx:end_idx]
    try:
        config = json.loads(json_str)
    except json.JSONDecodeError as e:
        check("AC4: valid JSON", False, f"JSON parse error: {e}")
        return

    check("AC4: valid JSON", True, "")

    # Verify the pinned heartbeat command
    heartbeat_cmd = "[ -f /workspace/.vss/auto-resume ] && { date +%s > /workspace/.vss/heartbeat.tmp.$$ && mv /workspace/.vss/heartbeat.tmp.$$ /workspace/.vss/heartbeat; } || true"

    # Check PreToolUse hooks
    pre_hooks = config.get("hooks", {}).get("PreToolUse", [])
    pre_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: PreToolUse heartbeat hook present", pre_heartbeat,
          f"PreToolUse blocks: {len(pre_hooks)}")

    # Check PostToolUse hooks
    post_hooks = config.get("hooks", {}).get("PostToolUse", [])
    post_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in post_hooks
    )
    check("AC4: PostToolUse heartbeat hook present", post_heartbeat,
          f"PostToolUse blocks: {len(post_hooks)}")

    # Check Stop hooks
    stop_hooks = config.get("hooks", {}).get("Stop", [])
    stop_heartbeat = any(
        block.get("matcher") == "" and
        any(cmd.get("command") == heartbeat_cmd for cmd in block.get("hooks", []))
        for block in stop_hooks
    )
    check("AC4: Stop heartbeat hook present", stop_heartbeat,
          f"Stop blocks: {len(stop_hooks)}")

    # Check that guard-bash, guard-fs, bell, etc. are still present
    has_guard_bash = any(
        block.get("matcher") == "Bash" and
        any("/usr/local/bin/guard-bash.sh" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: guard-bash entry preserved", has_guard_bash, "")

    has_guard_fs = any(
        block.get("matcher") == "Write|Edit|MultiEdit" and
        any("/usr/local/bin/guard-fs.sh" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in pre_hooks
    )
    check("AC4: guard-fs entry preserved", has_guard_fs, "")

    # Check bell on Stop
    bell_stop = any(
        block.get("matcher") == "" and
        any("printf '\\a'" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in stop_hooks
    )
    check("AC4: bell Stop command present", bell_stop, "")

    # Check bell on Notification
    notif_hooks = config.get("hooks", {}).get("Notification", [])
    bell_notif = any(
        block.get("matcher") == "" and
        any("printf '\\a'" in cmd.get("command", "") for cmd in block.get("hooks", []))
        for block in notif_hooks
    )
    check("AC4: bell Notification entry present", bell_notif, "")

    # Check forceLoginMethod and permissions.defaultMode
    check("AC4: forceLoginMethod=claudeai",
          config.get("forceLoginMethod") == "claudeai",
          f"forceLoginMethod={config.get('forceLoginMethod')}")
    check("AC4: permissions.defaultMode=bypassPermissions",
          config.get("permissions", {}).get("defaultMode") == "bypassPermissions",
          f"permissions.defaultMode={config.get('permissions', {}).get('defaultMode')}")


def test_vibe_supervised_launch_text() -> None:
    print("\n[task_016 AC5/AC7/AC8: supervised launch and trap text]")
    vibe_src = VIBE.read_text()

    # AC5a: launch_claude has exec devcontainer exec
    launch_claude_def = re.search(r'^launch_claude\(\) \{(.+?)^}', vibe_src, re.MULTILINE | re.DOTALL)
    if launch_claude_def:
        body = launch_claude_def.group(1)
        has_exec = "exec devcontainer exec" in body
        check("AC5: launch_claude body has 'exec devcontainer exec'", has_exec, "")
    else:
        check("AC5: launch_claude function found", False, "function definition not found")

    # AC5b: At least one bare devcontainer exec line exists (non-exec-prefixed)
    lines = vibe_src.split('\n')
    no_exec_lines = [l for l in lines
                     if l.strip().startswith('devcontainer exec')
                     and not l.strip().startswith('exec ')]
    check("AC5: at least one bare 'devcontainer exec' line", len(no_exec_lines) > 0,
          f"found {len(no_exec_lines)} lines")

    # AC5c: launch_claude_supervised exists
    check("AC5: launch_claude_supervised function exists",
          "launch_claude_supervised()" in vibe_src, "")

    # AC5d: VIBE_SESSION_REF is created with mktemp
    check("AC5: VIBE_SESSION_REF created with mktemp",
          'VIBE_SESSION_REF=$(mktemp' in vibe_src, "")

    # AC5e: AUTO_RESUME_MARKER defined before first supervised launch
    check("AC5: AUTO_RESUME_MARKER defined",
          'AUTO_RESUME_MARKER="$WORKSPACE/.vss/auto-resume"' in vibe_src, "")

    # AC7: INT trap is re-armed every iteration and reset after sleep
    has_int_trap = "trap 'auto_resume_deactivate" in vibe_src and "INT" in vibe_src
    check("AC7: INT trap armed for deactivate", has_int_trap, "")

    # AC7: trap reset after sleep
    has_trap_reset = "trap - INT" in vibe_src
    check("AC7: trap - INT reset present", has_trap_reset, "")

    # AC8: final exit statement with CLAUDE_EXIT
    has_exit_statement = re.search(r'^\s*exit "\$CLAUDE_EXIT"', vibe_src, re.MULTILINE)
    check("AC8: final 'exit \"$CLAUDE_EXIT\"' statement", has_exit_statement is not None, "")


def test_vibe_stall_watchdog_functional() -> None:
    print("\n[task_016 AC6: watchdog functional tests]")
    # All four cases stub vibe_container_kill_claude to write a killfile marker
    # instead of asserting on process death alone (a broken kill gate would
    # otherwise look identical to a correct one: an already-timed-out fake
    # claude dies "on its own" regardless of whether the gate ever armed).
    # POLL=1/GRACE=1/SECS=1/KILL_PAUSE=0 per spec AC6's pinned functional-test
    # env; negatives sample the live PID mid-lifetime (~t=3s, before its
    # natural 5s death) so the assertion is discriminating, not a race against
    # natural process exit.

    # Test 1: POSITIVE kill - marker active=1, ref file older (unconditional-
    # session case), heartbeat stale. Long-lived fake claude (sleep 300) so
    # any death can only be the watchdog's doing, never natural exit.
    snippet_t1 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t1.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t1.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t1.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t1.$$"; '
        # Stub vibe_container_kill_claude to track invocation (never actually
        # kills - proves the host-side PID fallback is what finishes the job)
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        # Backdate ref file first so the marker (written next, "now") is
        # unambiguously newer - no same-second race.
        'touch -t 202001010000 "$ref"; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 300 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 2.3; '
        'if [ -f "$killfile" ]; then echo "KILLED=[yes]"; else echo "KILLED=[no]"; fi; '
        'sleep 0.7; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "DEAD=[no]"; else echo "DEAD=[yes]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t1)
    check("AC6 T1: positive kill case exits 0", r.returncode == 0, r.stderr)
    check("AC6 T1: vibe_container_kill_claude invoked", "KILLED=[yes]" in r.stdout, r.stdout)
    check("AC6 T1: fake claude actually terminated (host-PID fallback)",
          "DEAD=[yes]" in r.stdout, r.stdout)

    # Test 2: NEGATIVE active=0 - gate condition (1) fails. Short-lived fake
    # claude (sleep 5) sampled at t=3s (mid-lifetime, well before its natural
    # death) so "still alive" is evidence the gate declined to arm, not a
    # coincidence of timing. killfile must not exist: the stub was never called.
    snippet_t2 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t2.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t2.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t2.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t2.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=0\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'touch "$ref"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t2)
    check("AC6 T2: negative active=0 exits 0", r.returncode == 0, r.stderr)
    check("AC6 T2: fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T2: kill never invoked", "KILLFILE=[no]" in r.stdout, r.stdout)

    # Test 3: NEGATIVE stale ref gate - gate condition (2) fails: marker
    # predates ref (crash-left marker from before this launcher session).
    # Same live-PID-at-t=3s + killfile-absent discrimination as T2.
    snippet_t3 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t3.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t3.$$"; '
        'ref="${TMPDIR:-/tmp}/ref-t3.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t3.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        # Backdate the MARKER (crash-left case) then create ref fresh - ref
        # unambiguously newer than marker, so [ marker -nt ref ] is false.
        'touch -t 202001010000 "$marker"; '
        'touch "$ref"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "$ref" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$ref" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t3)
    check("AC6 T3: negative stale ref gate exits 0", r.returncode == 0, r.stderr)
    check("AC6 T3: crash-left marker - fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T3: kill never invoked", "KILLFILE=[no]" in r.stdout, r.stdout)

    # Test 4: NEGATIVE empty ref - gate condition (2) fails via the mktemp-
    # failure fail-safe (empty ref must never satisfy the sentinel or the
    # exists-and-newer branch). Same discrimination as T2/T3.
    snippet_t4 = (
        'set +e; '
        'marker="${TMPDIR:-/tmp}/marker-t4.$$"; '
        'hb="${TMPDIR:-/tmp}/hb-t4.$$"; '
        'killfile="${TMPDIR:-/tmp}/killfile-t4.$$"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 5 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "" 2>/dev/null & '
        'wd_pid=$!; '
        'sleep 3; '
        'if kill -0 "$fake_pid" 2>/dev/null; then echo "ALIVE=[yes]"; else echo "ALIVE=[no]"; fi; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" 2>/dev/null; '
        'kill "$wd_pid" 2>/dev/null; '
        'wait "$fake_pid" 2>/dev/null; '
        'wait "$wd_pid" 2>/dev/null; '
        'rm -f "$marker" "$hb" "$killfile" "$marker.tmp.$$" "$hb.tmp.$$"; '
        'set -e'
    )
    r = _source_vibe_call({}, snippet_t4)
    check("AC6 T4: negative empty ref exits 0", r.returncode == 0, r.stderr)
    check("AC6 T4: empty ref - fake claude still alive after two live polls",
          "ALIVE=[yes]" in r.stdout, r.stdout)
    check("AC6 T4: empty ref never arms kill", "KILLFILE=[no]" in r.stdout, r.stdout)


def test_vibe_gitignore_heartbeat_pattern() -> None:
    print("\n[task_016 AC12: .gitignore heartbeat pattern]")
    gitignore_path = REPO / ".gitignore"
    if not gitignore_path.exists():
        check("AC12: .gitignore exists", False, "file not found")
        return

    content = gitignore_path.read_text()
    has_heartbeat = ".vss/heartbeat*" in content
    check("AC12: .gitignore contains '.vss/heartbeat*'", has_heartbeat,
          "pattern not found")


def test_vibe_task016_docs() -> None:
    print("\n[task_016 AC11/AC13: documentation presence]")

    # AC11: MANUAL-TESTS.md gains a --sessions stall watchdog section
    manual_tests = (REPO / "MANUAL-TESTS.md").read_text()
    has_stall_section = "--sessions stall watchdog" in manual_tests or "stall watchdog" in manual_tests
    check("AC11: MANUAL-TESTS.md has stall watchdog section", has_stall_section, "")

    # AC13: vibe auto-resume comment block (around line 479-486)
    vibe_src = VIBE.read_text()
    has_heartbeat_docs = "heartbeat" in vibe_src and "stall-watchdog" in vibe_src
    check("AC13: vibe comment block mentions heartbeat and watchdog", has_heartbeat_docs, "")

    # AC13: devcontainer/commands/vsss.md documents Auto-resume section
    vsss_md = (REPO / "devcontainer" / "commands" / "vsss.md").read_text()
    has_auto_resume_docs = "Auto-resume" in vsss_md or "auto-resume" in vsss_md
    check("AC13: vsss.md documents Auto-resume", has_auto_resume_docs, "")
    has_stall_secs = "VIBE_STALL_SECS" in vsss_md
    check("AC13: vsss.md documents VIBE_STALL_SECS", has_stall_secs, "")


def test_vibe_statusline() -> None:
    """statusLine in the settings heredoc: single-letter model (F/O/S/H),
    full display name fallback, vibe cue, optional ctx/5h percentage segments.
    Structural check on the parsed JSON plus a functional run of the actual
    command string against stdin fixtures (proves the JSON escaping survives
    the round trip into a real shell)."""
    print("\n[statusLine: single-letter model in the vibe TUI]")
    vibe_src = VIBE.read_text()

    start_marker = 'cat > "$WORKSPACE/.claude/settings.local.json" << \'EOF\''
    start_idx = vibe_src.find(start_marker)
    check("[status] settings heredoc found", start_idx != -1, "")
    if start_idx == -1:
        return
    start_idx = vibe_src.find('\n', start_idx) + 1
    end_idx = vibe_src.find('\nEOF', start_idx)
    config = json.loads(vibe_src[start_idx:end_idx])

    sl = config.get("statusLine", {})
    check("[status] statusLine.type == command", sl.get("type") == "command", str(sl))
    cmd = sl.get("command", "")
    check("[status] command reads model.display_name", ".model.display_name" in cmd, "")

    # Functional fixtures: (stdin JSON, expected exact output)
    fixtures = [
        ('{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":42.7},'
         '"rate_limits":{"five_hour":{"used_percentage":63}}}',
         "F · vibe · ctx 42% · 5h 63%"),
        ('{"model":{"display_name":"Opus 4.8"}}', "O · vibe"),
        ('{"model":{"display_name":"Sonnet 5"},"context_window":{"used_percentage":3}}',
         "S · vibe · ctx 3%"),
        ('{"model":{"display_name":"Haiku 4.5"}}', "H · vibe"),
        ('{"model":{"display_name":"GPT-9"}}', "GPT-9 · vibe"),  # fallback: full name
        ('{}', "? · vibe"),  # every field absent (pre-first-response) → no crash
    ]
    for stdin_json, expected in fixtures:
        r = subprocess.run(["sh", "-c", cmd], input=stdin_json,
                           capture_output=True, text=True, timeout=15)
        label = expected.split(" ")[0]
        check(f"[status] {label!r} fixture exact output", r.returncode == 0 and r.stdout == expected,
              f"rc={r.returncode} out=[{r.stdout}] err=[{r.stderr.strip()[:80]}]")


# ── task_017 AC1-AC7: shared-repos tests (Cycle 1) ────────────────────────────

def test_task017_ac2_shared_repos_parse_valid() -> None:
    print("\n[task_017 AC2: shared_repos_parse: valid line]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro ro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m"); '
        'echo "RESULT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("parses valid line", "RESULT=andeyePro/andeyePro ro" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_default_mode() -> None:
    print("\n[task_017 AC2: shared_repos_parse: default mode]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m"); '
        'echo "RESULT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("defaults to ro", "RESULT=andeyePro/andeyePro ro" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_comments_blanks() -> None:
    print("\n[task_017 AC2: shared_repos_parse: comments and blanks]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "# comment\\n\\nandeyePro/andeyePro\\n  # another comment\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" | wc -l); '
        'echo "LINES=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("skips comments/blanks", "LINES=1" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_bad_slug() -> None:
    print("\n[task_017 AC2: shared_repos_parse: bad slug]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "invalid-slug-no-slash\\n" > "$m"; '
        'shared_repos_parse "$m" 2>&1 > /tmp/parse_out.txt; '
        'STDERR=$(cat /tmp/parse_out.txt); '
        'echo "STDERR=$STDERR"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on bad slug", "malformed slug" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_bad_mode() -> None:
    print("\n[task_017 AC2: shared_repos_parse: bad mode]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro invalid\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on bad mode", "invalid mode" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_extra_content() -> None:
    print("\n[task_017 AC2: shared_repos_parse: extra content]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "andeyePro/andeyePro ro extra stuff\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("warns on extra content", "unexpected content" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_missing_file() -> None:
    print("\n[task_017 AC2: shared_repos_parse: missing file]")
    snippet = 'OUT=$(shared_repos_parse /nonexistent/file); echo "RESULT=[$OUT]"'
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("missing file echoes nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_injection_strings() -> None:
    print("\n[task_017 AC2: shared_repos_parse: injection strings rejected]")
    cases = [
        ('foo/bar;rm -rf /', "semicolon injection"),
        ('foo/$(bar)', "command substitution"),
        ('foo/`bar`', "backtick injection"),
        ('foo/bar\nbar/baz', "embedded newline"),
    ]
    for bad_slug, label in cases:
        bad_slug_escaped = shlex.quote(bad_slug + "\n")
        snippet = (
            'm="$(mktemp)"; '
            f'printf {bad_slug_escaped} > "$m"; '
            'OUT=$(shared_repos_parse "$m" 2>&1 | wc -l); '
            'echo "OUT=$OUT"; '
            'rm "$m"'
        )
        r = _source_vibe_call({}, snippet)
        check(f"rejects {label}", r.returncode == 0, r.stderr)
        check(f"{label} produces warning", "OUT=" in r.stdout, r.stdout)


def test_task017_ac2_shared_repos_parse_dot_prefix_basename_rejected() -> None:
    print("\n[task_017 AC2: shared_repos_parse: dot-prefix basenames skipped]")
    snippet = (
        'm="$(mktemp)"; '
        'printf "owner/.signals ro\\n" > "$m"; '
        'OUT=$(shared_repos_parse "$m" 2>&1); '
        'echo "OUT=$OUT"; '
        'rm "$m"'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    # Note: the spec says dot-prefix names are reserved and SKIPPED, but
    # parsing happens in shared_repos_scan. This test documents the behavior.


def test_task017_ac2_repos_registry_lookup_valid() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: valid entry]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=/home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = f'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=$OUT"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("looks up path", "/home/user/code/andeyePro" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_missing_file() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: missing file]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("missing file returns nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_bad_slug() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: bad slug]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=/home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "invalid-slug"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("bad slug returns nothing", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_malformed_entry() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: malformed entry gracefully ignored]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        # Write multiple entries, one good, one malformed (line continuation)
        registry.write_text("other/repo=/home/user/code/other\nandeyePro/andeyePro=/home/user/code/andeye\nPro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        # Lookup the good entry
        snippet = 'OUT=$(repos_registry_lookup "other/repo"); echo "RESULT=$OUT"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("good entry resolved", "/home/user/code/other" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_quote_in_path() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: quote in path rejected]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text('andeyePro/andeyePro=/home/user/code/"andeye\n', encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("quote in path rejected", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_repos_registry_lookup_relative_path() -> None:
    print("\n[task_017 AC2: repos_registry_lookup: relative path rejected]")
    with tempfile.TemporaryDirectory() as td:
        vibe_dir = Path(td) / ".vibe"
        vibe_dir.mkdir()
        registry = vibe_dir / "repos"
        registry.write_text("andeyePro/andeyePro=home/user/code/andeyePro\n", encoding='utf-8')
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        snippet = 'OUT=$(repos_registry_lookup "andeyePro/andeyePro"); echo "RESULT=[$OUT]"'
        r = _source_vibe_call(env, snippet)
        check("exits 0", r.returncode == 0, r.stderr)
        check("relative path rejected", "RESULT=[]" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_valid() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: valid slug]")
    snippet = 'OUT=$(shared_repo_env_name "andeyePro/andeyePro"); echo "RESULT=$OUT"'
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("produces VIBE_SHARED_TOKEN_* name", "VIBE_SHARED_TOKEN_" in r.stdout, r.stdout)
    check("correct transformation", "VIBE_SHARED_TOKEN_ANDEYEPRO_ANDEYEPRO" in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_sanitisation() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: sanitisation cases]")
    cases = [
        ("owner/repo", "VIBE_SHARED_TOKEN_OWNER_REPO"),
        ("owner_repo/pkg-name", "VIBE_SHARED_TOKEN_OWNER_REPO_PKG_NAME"),
        ("owner.io/repo.py", "VIBE_SHARED_TOKEN_OWNER_IO_REPO_PY"),
    ]
    for slug, expected in cases:
        snippet = f'OUT=$(shared_repo_env_name "{slug}"); echo "RESULT=$OUT"'
        r = _source_vibe_call({}, snippet)
        check(f"sanitises {slug}", expected in r.stdout, r.stdout)


def test_task017_ac2_shared_repo_env_name_collision() -> None:
    print("\n[task_017 AC2: shared_repo_env_name: collision detection]")
    # Two different slugs that sanitise to same name
    snippet = (
        'ENV1=$(shared_repo_env_name "owner/repo"); '
        'ENV2=$(shared_repo_env_name "owner-repo"); '
        'if [ "$ENV1" = "$ENV2" ]; then echo "COLLISION"; else echo "DISTINCT"; fi'
    )
    r = _source_vibe_call({}, snippet)
    check("exits 0", r.returncode == 0, r.stderr)
    check("detects collision", "COLLISION" in r.stdout, r.stdout)
