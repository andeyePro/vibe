from smoke._core import *  # noqa: F401,F403




def test_ac4_remove_existing_flag_no_rebuild_no_drift() -> None:
    """AC4d: (false, "") → empty."""
    print("\n[task_015 AC4d: (false, '') → empty]")
    r = _source_vibe_call({}, 'remove_existing_flag "false" ""')
    check("AC4d exits 0", r.returncode == 0, r.stderr)
    check("AC4d emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5a_docker_all_fail() -> None:
    """AC5a: All docker calls fail → emit nothing, no abort."""
    print("\n[task_015 AC5a: all docker calls fail → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="",
        ps_rc=1,  # docker ps fails
        cref_output="",
        cref_rc=1,  # docker inspect fails
        tag_id_output="",
        tag_id_rc=1,  # tag inspect fails
        ref_id_output="",
        ref_id_rc=1,  # ref inspect fails
    )
    check("AC5a exits 0 (no abort)", r.returncode == 0, r.stderr)
    check("AC5a emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5b_ps_ok_inspect_fails() -> None:
    """AC5b: docker ps ok, docker inspect fails → emit nothing."""
    print("\n[task_015 AC5b: ps ok, inspect fails → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="",  # inspect (container ref) returns empty
        cref_rc=1,
        tag_id_output="sha256:abc",
        tag_id_rc=0,
        ref_id_output="",
        ref_id_rc=0,
    )
    check("AC5b exits 0", r.returncode == 0, r.stderr)
    check("AC5b emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5c_ps_inspect_ok_tag_fails() -> None:
    """AC5c: ps+inspect ok, tag image inspect fails → emit nothing."""
    print("\n[task_015 AC5c: ps+inspect ok, tag inspect fails → emit nothing]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-digest",
        cref_rc=0,
        tag_id_output="",  # tag inspect returns empty
        tag_id_rc=1,
        ref_id_output="sha256:old-digest",
        ref_id_rc=0,
    )
    check("AC5c exits 0", r.returncode == 0, r.stderr)
    check("AC5c emits nothing", r.stdout.strip() == "", f"output: {r.stdout}")


def test_ac5d_ps_inspect_ok_ref_inspect_fails() -> None:
    """AC5d: ps+inspect ok, current tag ok, but container ref inspect fails → emit '1'."""
    print("\n[task_015 AC5d: ref inspect fails (image pruned) → emit '1']")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-id-xyz",
        ps_rc=0,
        cref_output="sha256:old-digest",
        cref_rc=0,
        tag_id_output="sha256:new-digest",
        tag_id_rc=0,
        ref_id_output="",  # ref inspect returns empty - source image pruned
        ref_id_rc=1,
    )
    check("AC5d exits 0", r.returncode == 0, r.stderr)
    check("AC5d emits '1'", r.stdout.strip() == "1", f"output: {r.stdout}")


def test_ac6_multiple_containers_uses_first() -> None:
    """AC6: Multiple containers → uses first line only."""
    print("\n[task_015 AC6: multiple containers uses first]")
    r = _image_drift_call_with_docker_stub(
        workspace="/workspace",
        image_tag="vibe-dev:latest",
        ps_output="container-1\ncontainer-2\ncontainer-3",  # multiple lines
        ps_rc=0,
        cref_output="sha256:old-image",  # inspecting first container
        cref_rc=0,
        tag_id_output="sha256:new-image",
        tag_id_rc=0,
        ref_id_output="sha256:old-image",
        ref_id_rc=0,
    )
    check("AC6 exits 0", r.returncode == 0, r.stderr)
    check("AC6 emits '1' (drifted, uses first)", r.stdout.strip() == "1",
          f"output: {r.stdout}")


def test_ac8_comment_present() -> None:
    """AC8: Comment containing 'drift' or 'superseded' present in vibe source."""
    print("\n[task_015 AC8: comment mentions drift/superseded]")
    content = VIBE.read_text()
    # Look for a comment line (first non-space char is #) containing drift or superseded
    has_drift_comment = False
    for line in content.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            if 'drift' in stripped.lower() or 'superseded' in stripped.lower():
                has_drift_comment = True
                break
    check("AC8 comment present", has_drift_comment,
          "no comment with 'drift' or 'superseded' found in vibe source")


# ── Runner ────────────────────────────────────────────────────────────────────


# ── Learning library tests ───────────────────────────────────────────────────


def test_learning_config_format() -> None:
    """AC1: Config file format with all 4 keys, strict parsing."""
    print("\n[learning AC1: config format + strict parse]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            'VIBE_LEARNING_ENABLED="true"\n'
            'VIBE_LEARNING_PATH="/tmp/learning"\n'
            'VIBE_LEARNING_VISIBILITY="private"\n'
            'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            "learning_load; "
            "echo ENABLED=$VIBE_LEARNING_ENABLED; "
            "echo PATH=$VIBE_LEARNING_PATH; "
            "echo VIS=$VIBE_LEARNING_VISIBILITY; "
            "echo REMOTE=$VIBE_LEARNING_GIT_REMOTE"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC1 exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC1 ENABLED='true'", "ENABLED=true" in r.stdout, r.stdout)
        check("[learn] AC1 PATH='/tmp/learning'", "PATH=/tmp/learning" in r.stdout, r.stdout)
        check("[learn] AC1 VIS='private'", "VIS=private" in r.stdout, r.stdout)
        check("[learn] AC1 REMOTE='origin'", "REMOTE=origin" in r.stdout, r.stdout)


def test_learning_strict_parser_no_injection() -> None:
    """AC2: Strict parser rejects shell injection via config."""
    print("\n[learning AC2: strict parser, no shell injection]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        # Inject a command that would touch a file if eval'd
        canary = home / "vibe-injection-canary"
        cfg.write_text(
            'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="/tmp"; touch {canary}\n'
            'VIBE_LEARNING_VISIBILITY="private"\n'
            'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = f"source {shlex.quote(str(VIBE))}; learning_load"
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC2 no injection exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC2 canary file NOT created", not canary.exists(),
              f"canary exists: {canary}")


def test_learning_init_interactive() -> None:
    """AC3: vibe learn --init interactive flow, chmod 600, --reinit path."""
    print("\n[learning AC3: --init interactive + reinit]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib_path = home / "mylib"
        lib_path.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # Simulate user input: absolute path (no mkdir needed), private, no remote.
        input_str = f"{lib_path}\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC3 --init exits 0", r.returncode == 0,
              f"stderr={r.stderr[:300]}")
        check("[learn] AC3 config created", cfg.exists(), str(cfg))
        if cfg.exists():
            mode = cfg.stat().st_mode & 0o777
            check("[learn] AC3 config chmod 600", mode == 0o600,
                  f"mode={oct(mode)}")
            content = cfg.read_text()
            check("[learn] AC3 config has ENABLED=true", "ENABLED=\"true\"" in content,
                  content)


def test_learning_init_mkdir_offer() -> None:
    """AC3: --init offers to create missing path."""
    print("\n[learning AC3: --init mkdir offer]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib_path = home / "newlib"
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # User provides non-existent path; say yes to mkdir; then private.
        input_str = f"{lib_path}\ny\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC3 mkdir exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC3 mkdir created path", lib_path.exists(), str(lib_path))


def test_learning_init_reinit_path() -> None:
    """AC3: --reinit overwrites existing enabled config."""
    print("\n[learning AC3: --reinit overwrites]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib1 = home / "lib1"
        lib2 = home / "lib2"
        lib1.mkdir()
        lib2.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # First init
        input_str = f"{lib1}\nprivate\n"
        r1 = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str)
        check("[learn] AC3 first init exit 0", r1.returncode == 0, r1.stderr)
        # Second init without --reinit should fail
        input_str2 = f"{lib2}\nprivate\n"
        r2 = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str2)
        check("[learn] AC3 second init fails without --reinit", r2.returncode == 1,
              r2.stdout)
        # With --reinit should succeed
        r3 = run(["bash", str(VIBE), "learn", "--reinit"], env=env, input=input_str2)
        check("[learn] AC3 --reinit succeeds", r3.returncode == 0, r3.stderr)
        content = cfg.read_text()
        check("[learn] AC3 --reinit updated path", str(lib2) in content, content)


def test_learning_default_off_no_config() -> None:
    """AC4: Default-off: with no config, learning_is_enabled exits 1."""
    print("\n[learning AC4: default-off behavior]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = f"source {shlex.quote(str(VIBE))}; learning_is_enabled || echo NOT_ENABLED"
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC4 no config not enabled", "NOT_ENABLED" in r.stdout, r.stdout)


def test_learning_learn_without_init() -> None:
    """AC4: vibe learn without init exits 1 with message."""
    print("\n[learning AC4: learn without init refusal]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "test"], env=env)
        check("[learn] AC4 learn without init exits 1", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] AC4 error message present", "not initialized" in r.stderr,
              r.stderr)


def test_render_devcontainer_with_mounts_learning() -> None:
    """AC5/AC6: Generated override config has readonly /learnings mount."""
    print("\n[learning AC5: mount via override config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        src_cfg = REPO / "devcontainer" / "devcontainer.json"
        dst = Path(td) / "override.json"
        lib = Path(td) / "learnings"
        lib.mkdir()
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"render_devcontainer_with_mounts {shlex.quote(str(src_cfg))} "
            f"{shlex.quote(str(dst))} {shlex.quote(str(lib))} /learnings 1"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC5 render exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC5 output file created", dst.exists(), str(dst))
        if dst.exists():
            data = json.loads(dst.read_text())
            mounts = data.get("mounts", [])
            learning_mount = None
            for m in mounts:
                # mounts are objects (dicts) in the output from render_devcontainer_with_mounts
                if isinstance(m, dict) and m.get("target") == "/learnings":
                    learning_mount = m
                    break
            check("[learn] AC5 learning mount present", learning_mount is not None,
                  f"mounts={mounts}")
            if learning_mount:
                check("[learn] AC6 readonly=true", learning_mount.get("readonly") is True,
                      str(learning_mount))


def test_learning_dispatch_no_docker_required() -> None:
    """AC7: vibe learn --init works without docker on PATH."""
    print("\n[learning AC7: learn dispatch before preflight]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        env = _isolate_extras_env({**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"})
        # Run vibe learn --init with docker removed from PATH.
        # If it tries to call docker, this will fail. If it dispatches correctly, it works.
        input_str = f"{lib}\nprivate\n"
        r = run(["bash", str(VIBE), "learn", "--init"], env=env, input=input_str)
        check("[learn] AC7 learn --init works without docker", r.returncode == 0,
              f"stderr={r.stderr[:300]}")


def test_learning_capture_confirm_flow() -> None:
    """AC8: vibe learn '<pattern>' capture with confirm."""
    print("\n[learning AC8: capture confirm flow]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # Run vibe learn with 'y' confirmation
        r = run(
            ["bash", str(VIBE), "learn", "test pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC8 capture with 'y' exits 0", r.returncode == 0, r.stderr)
        # Check that a file was created in lib
        files = list(lib.glob("*.md"))
        check("[learn] AC8 entry file created", len(files) == 1, f"files={files}")
        if files:
            content = files[0].read_text()
            check("[learn] AC8 file contains pattern", "test pattern" in content, content)


def test_learning_capture_eof_cancel() -> None:
    """AC8: EOF on stdin defaults to cancel, no write."""
    print("\n[learning AC8: EOF cancel]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # Empty input triggers EOF
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="")
        check("[learn] AC8 EOF exits 0", r.returncode == 0, r.stderr)
        check("[learn] AC8 cancelled message", "cancelled" in r.stderr, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC8 EOF no write", len(files) == 0, f"files={files}")


def test_learning_capture_confirm_yes_word() -> None:
    """Confirm accepts 'yes' (full word), not just 'y'."""
    print("\n[learning: capture confirm 'yes']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "yes-word pattern"], env=env, input="yes\n")
        check("[learn] confirm 'yes' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'yes' wrote file", len(files) == 1, f"files={files}")


def test_learning_capture_confirm_uppercase_y() -> None:
    """Confirm accepts 'Y' (uppercase) - case-insensitive."""
    print("\n[learning: capture confirm 'Y']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "uppercase-Y pattern"], env=env, input="Y\n")
        check("[learn] confirm 'Y' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'Y' wrote file", len(files) == 1, f"files={files}")


def test_learning_capture_confirm_uppercase_yes() -> None:
    """Confirm accepts 'YES' (uppercase, full word)."""
    print("\n[learning: capture confirm 'YES']")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "uppercase-YES pattern"], env=env, input="YES\n")
        check("[learn] confirm 'YES' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] confirm 'YES' wrote file", len(files) == 1, f"files={files}")


def test_learnings_md_fragment_present() -> None:
    """devcontainer/claude-md/learnings.md ships and references /learnings."""
    print("\n[learnings.md fragment: present + content]")
    p = REPO / "devcontainer" / "claude-md" / "learnings.md"
    check("[learnings.md] file exists", p.exists())
    if not p.exists():
        return
    body = p.read_text()
    check("[learnings.md] mentions /learnings path", "/learnings" in body, body[:200])
    check("[learnings.md] explains read-only nature", "read-only" in body, body[:200])
    check("[learnings.md] references vibe learn host command", "vibe learn" in body, body[:200])
    nonblank = sum(1 for line in body.splitlines() if line.strip())
    check("[learnings.md] >= 30 non-blank lines (substantive)", nonblank >= 30, f"non-blank={nonblank}")


def test_learning_capture_confirm_no() -> None:
    """AC8: Answering 'n' to confirm cancels with no write."""
    print("\n[learning AC8: confirm 'n' cancels]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="n\n")
        check("[learn] AC8 confirm 'n' exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC8 'n' no write", len(files) == 0, f"files={files}")


def test_learning_public_mode_push_prompt() -> None:
    """AC9: Public mode shows push prompt and processes git on 'y'."""
    print("\n[learning AC9: public mode push]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="public"\n'
            f'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # Confirm capture + push (will fail because lib is not a git repo, but entry saved locally)
        r = run(
            ["bash", str(VIBE), "learn", "test pattern"],
            env=env,
            input="y\ny\n",
        )
        check("[learn] AC9 public mode exits 0 even with git failure",
              r.returncode == 0, f"stderr={r.stderr[:300]}")
        check("[learn] AC9 push prompt shown", "Push to" in r.stderr, r.stderr)
        # Check entry was written locally (git failure doesn't prevent saving)
        files = list(lib.glob("*.md"))
        check("[learn] AC9 entry saved locally despite git failure",
              len(files) == 1, f"files={files}")


def test_learning_public_mode_git_failure_survives() -> None:
    """AC9: Git failure doesn't delete local entry."""
    print("\n[learning AC9: git failure survives locally]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="public"\n'
            f'VIBE_LEARNING_GIT_REMOTE="origin"\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # git will fail because lib is not a git repo
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\ny\n",
        )
        check("[learn] AC9 git failure exits 0", r.returncode == 0, r.stderr)
        files = list(lib.glob("*.md"))
        check("[learn] AC9 entry saved despite git failure", len(files) == 1,
              f"files={files}")


def test_learning_private_mode_no_git() -> None:
    """AC10: Private mode skips git operations."""
    print("\n[learning AC10: private mode skips git]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        # Use a fake git that records calls
        fake_git_dir = home / "fake-bin"
        fake_git_dir.mkdir()
        git_log = home / "git-calls.log"
        git_script = (
            "#!/bin/bash\n"
            f'echo "$@" >> "{git_log}"\n'
            "exit 0\n"
        )
        git_path = fake_git_dir / "git"
        git_path.write_text(git_script)
        git_path.chmod(0o755)
        env["PATH"] = f"{fake_git_dir}:{env.get('PATH', '')}"
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC10 private mode exits 0", r.returncode == 0, r.stderr)
        check("[learn] AC10 no git calls in private mode",
              not git_log.exists() or git_log.read_text().strip() == "",
              git_log.read_text() if git_log.exists() else "")


def test_learning_marker_blocks_capture() -> None:
    """AC11: .vibe-no-learn marker blocks capture."""
    print("\n[learning AC11: marker blocks capture]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        # Create a project with marker
        proj = home / "project"
        proj.mkdir()
        (proj / ".vibe-no-learn").write_text("")
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
            cwd=proj,
        )
        check("[learn] AC11 marker blocks capture", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] AC11 opted out message", "opted out" in r.stderr, r.stderr)


def test_learning_marker_walk_stops_at_home() -> None:
    """AC11: Marker walk stops at $HOME, doesn't walk above."""
    print("\n[learning AC11: marker walk stops at $HOME]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        # Place marker above $HOME (at /tmp)
        parent = home.parent
        (parent / ".vibe-no-learn").write_text("")
        try:
            env = _isolate_extras_env({**os.environ, "HOME": str(home)})
            r = run(
                ["bash", str(VIBE), "learn", "pattern"],
                env=env,
                input="y\n",
            )
            check("[learn] AC11 walk stops at $HOME, marker above doesn't block",
                  r.returncode == 0, f"stderr={r.stderr[:300]}")
        finally:
            (parent / ".vibe-no-learn").unlink()


def test_learning_home_unset_fails_safe() -> None:
    """AC11: $HOME unset is fail-safe (no write)."""
    print("\n[learning AC11: $HOME unset fail-safe]")
    with tempfile.TemporaryDirectory() as td:
        lib = Path(td) / "lib"
        lib.mkdir()
        cfg = Path(td) / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = _isolate_extras_env({**os.environ})
        # Unset HOME
        if "HOME" in env:
            del env["HOME"]
        # Run vibe learn with HOME unset
        r = run(
            ["bash", str(VIBE), "learn", "pattern"],
            env=env,
            input="y\n",
        )
        check("[learn] AC11 $HOME unset fails safe", r.returncode == 1,
              f"exit={r.returncode}")


def test_learning_help_lists_commands() -> None:
    """AC12: vibe --help lists learn commands."""
    print("\n[learning AC12: help mentions learn]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td}
        r = run(["bash", str(VIBE), "--help"], env=env)
        check("[learn] AC12 help exit 0", r.returncode == 0, r.stderr)
        check("[learn] AC12 help mentions 'learn \"<pattern>\"'",
              'learn "<pattern>"' in r.stdout, r.stdout)
        check("[learn] AC12 help mentions 'learn --init'",
              "learn --init" in r.stdout, r.stdout)


def test_learning_banner_with_optins() -> None:
    """AC12: Banner shows learn line when opted in and not blocked."""
    print("\n[learning AC12: banner with opt-in]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"learning_should_mount {shlex.quote(str(home))} && echo Y || echo N"
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] AC12 learning_should_mount returns 0 when opted in",
              r.returncode == 0, r.stderr)


def test_learning_chmod_600_verified() -> None:
    """AC13: Config created with chmod 600."""
    print("\n[learning AC13: chmod 600 on config]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"
        lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        input_str = f"{lib}\nprivate\n"
        r = run(
            ["bash", str(VIBE), "learn", "--init"],
            env=env,
            input=input_str,
        )
        check("[learn] AC13 init success", r.returncode == 0, r.stderr)
        if cfg.exists():
            mode = cfg.stat().st_mode & 0o777
            check("[learn] AC13 config is chmod 600", mode == 0o600,
                  f"mode={oct(mode)}")


def test_learning_helpers_exist() -> None:
    """AC14: All 10 helpers defined."""
    print("\n[learning AC14: 10 helpers present]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        helpers = [
            "learning_config_path",
            "learning_load",
            "learning_is_enabled",
            "learning_project_opted_out",
            "learning_should_mount",
            "learning_entry_path",
            "learning_format_entry",
            "learning_commit_message",
            "render_devcontainer_with_mounts",
            "learning_handle_subcommand",
        ]
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            "declare -F | awk '{print $3}'"
        )
        r = run(["bash", "-c", script], env=env)
        declared = r.stdout.split()
        for helper in helpers:
            check(f"[learn] AC14 helper '{helper}' exists",
                  helper in declared, f"declared={declared}")


def test_learning_entry_path_composition() -> None:
    """Helper function test: learning_entry_path."""
    print("\n[learning helper: entry_path composition]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_entry_path "/home/user/lib" "2025-04-23T12:34:56Z" "abc123" | '
            'grep -q "/home/user/lib/2025-04-23T12:34:56Z-abc123.md" && echo OK'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] entry_path composition", "OK" in r.stdout, r.stdout)


def test_learning_format_entry() -> None:
    """Helper function test: learning_format_entry."""
    print("\n[learning helper: format_entry]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_format_entry "2025-04-23T12:00:00Z" "my pattern"'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] format_entry has timestamp", "2025-04-23T12:00:00Z" in r.stdout,
              r.stdout)
        check("[learn] format_entry has pattern", "my pattern" in r.stdout, r.stdout)


def test_learning_commit_message() -> None:
    """Helper function test: learning_commit_message."""
    print("\n[learning helper: commit_message]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'learning_commit_message "short pattern" | grep -q "^learn: short pattern"'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] commit_message formats correctly", r.returncode == 0, r.stdout)


def test_learning_config_path_helper() -> None:
    """Helper function test: learning_config_path."""
    print("\n[learning helper: config_path]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": str(td), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f'learning_config_path | grep -q "{td}/.vibe/learning.config" && echo OK'
        )
        r = run(["bash", "-c", script], env=env)
        check("[learn] config_path helper", "OK" in r.stdout, r.stdout)


def test_learning_code_check_clean() -> None:
    """AC15: python3 code-check.py passes on vibe."""
    print("\n[learning AC15: code-check.py passes]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[learn] AC15 code-check passes", r.returncode == 0,
          f"exit={r.returncode} output={r.stdout[-300:]}")


def test_learning_short_marker_blocks() -> None:
    """New short .no-learn marker blocks capture (same semantics as legacy)."""
    print("\n[learning rename: .no-learn blocks capture]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        (proj / ".no-learn").write_text("")
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "pattern"], env=env, input="y\n", cwd=proj)
        check("[learn] short .no-learn marker blocks capture",
              r.returncode == 1, f"exit={r.returncode} stderr={r.stderr}")


def test_learning_exclude_creates_marker() -> None:
    """vibe learn --exclude creates .no-learn in cwd; idempotent."""
    print("\n[learning --exclude]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=proj)
        check("[learn] --exclude exits 0", r.returncode == 0, r.stderr)
        check("[learn] --exclude creates .no-learn", (proj / ".no-learn").exists())
        # Idempotent: second call still exits 0
        r2 = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=proj)
        check("[learn] --exclude idempotent", r2.returncode == 0, r2.stderr)
        check("[learn] --exclude says already excluded",
              "already excluded" in r2.stdout, r2.stdout)


def test_learning_include_removes_marker() -> None:
    """vibe learn --include removes .no-learn (and legacy .vibe-no-learn)."""
    print("\n[learning --include]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        proj = home / "project"; proj.mkdir()
        (proj / ".no-learn").write_text("")
        (proj / ".vibe-no-learn").write_text("")  # legacy marker too
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "--include"], env=env, cwd=proj)
        check("[learn] --include exits 0", r.returncode == 0, r.stderr)
        check("[learn] --include removes .no-learn", not (proj / ".no-learn").exists())
        check("[learn] --include removes legacy .vibe-no-learn",
              not (proj / ".vibe-no-learn").exists())
        # Idempotent: second call exits 0 with no-marker message
        r2 = run(["bash", str(VIBE), "learn", "--include"], env=env, cwd=proj)
        check("[learn] --include idempotent", r2.returncode == 0, r2.stderr)
        check("[learn] --include says was not excluded",
              "was not excluded" in r2.stdout, r2.stdout)


def test_learning_exclude_refuses_in_home() -> None:
    """vibe learn --exclude refuses when cwd is $HOME."""
    print("\n[learning --exclude refuses $HOME]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        lib = home / "lib"; lib.mkdir()
        _learning_optin_config(home, lib)
        env = _isolate_extras_env({**os.environ, "HOME": str(home)})
        r = run(["bash", str(VIBE), "learn", "--exclude"], env=env, cwd=home)
        check("[learn] --exclude refuses in $HOME", r.returncode == 1,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[learn] --exclude $HOME error mentions refusing",
              "refusing" in r.stderr, r.stderr)
        check("[learn] --exclude $HOME left no marker",
              not (home / ".no-learn").exists())


def test_learning_help_mentions_exclude_include() -> None:
    """vibe --help mentions --exclude and --include."""
    print("\n[learning --help mentions exclude/include]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("[learn] --help mentions --exclude", "--exclude" in r.stdout, r.stdout[:600])
    check("[learn] --help mentions --include", "--include" in r.stdout, r.stdout[:600])


def test_learning_help_says_host_only() -> None:
    """vibe --help makes clear `vibe learn` subcommands run on the host."""
    print("\n[learning --help says host-only]")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("[learn] --help mentions 'on the HOST shell'",
          "HOST shell" in r.stdout or "host shell" in r.stdout, r.stdout[:900])
    check("[learn] --help warns 'not available inside the container'",
          "not available inside the container" in r.stdout
          or "not inside the container" in r.stdout, r.stdout[:900])


def test_learning_bare_learn_usage_says_host_only() -> None:
    """`vibe learn` (no args) emits usage that tells users to run on the host."""
    print("\n[learning bare-learn usage says host-only]")
    with tempfile.TemporaryDirectory() as td:
        env = _isolate_extras_env({**os.environ, "HOME": td})
        r = run(["bash", str(VIBE), "learn"], env=env)
    check("[learn] bare-learn exits 1", r.returncode == 1,
          f"exit={r.returncode} stderr={r.stderr[:400]}")
    check("[learn] bare-learn usage mentions host shell",
          "host shell" in r.stderr or "on the host" in r.stderr,
          r.stderr[:600])


def test_learning_banner_state_three_way() -> None:
    """learning_banner_state → silent / excluded / enabled per documented rules."""
    print("\n[learning banner_state: silent / excluded / enabled]")

    def call_state(home: Path, workspace: Path) -> str:
        env = {**os.environ, "HOME": str(home), "VIBE_SOURCE_ONLY": "1"}
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            f"learning_load; "
            f"learning_banner_state {shlex.quote(str(workspace))}"
        )
        r = run(["bash", "-c", script], env=env)
        return r.stdout.strip()

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        ws = home / "proj"
        ws.mkdir()

        # State 1: no config at all → silent
        check("[learn] banner_state silent when no config",
              call_state(home, ws) == "silent", call_state(home, ws))

        # State 2: config present + opted in → enabled
        lib = home / "lib"; lib.mkdir()
        cfg = home / ".vibe" / "learning.config"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            f'VIBE_LEARNING_ENABLED="true"\n'
            f'VIBE_LEARNING_PATH="{lib}"\n'
            f'VIBE_LEARNING_VISIBILITY="private"\n'
            f'VIBE_LEARNING_GIT_REMOTE=""\n'
        )
        check("[learn] banner_state enabled when opted in",
              call_state(home, ws) == "enabled", call_state(home, ws))

        # State 3: .no-learn marker → excluded
        (ws / ".no-learn").touch()
        check("[learn] banner_state excluded when .no-learn present",
              call_state(home, ws) == "excluded", call_state(home, ws))

        # Also legacy marker should read as excluded.
        (ws / ".no-learn").unlink()
        (ws / ".vibe-no-learn").touch()
        check("[learn] banner_state excluded when legacy .vibe-no-learn present",
              call_state(home, ws) == "excluded", call_state(home, ws))


def test_learning_banner_parent_shell_load() -> None:
    """Regression: main-block banner must load learning config in the parent
    shell, not rely on exports from the $( _build_override_config )
    subshell — exports don't cross subshell boundaries, so without a parent-
    shell learning_load the banner line silently disappears even when
    /learnings is correctly mounted."""
    print("\n[learning banner: parent-shell load before override-config subshell]")
    src = Path(VIBE).read_text()
    # The banner block uses the learning_banner_state case dispatch.
    banner_marker = 'case "$(learning_banner_state'
    subshell_marker = "OVERRIDE_CONFIG=$(_build_override_config"
    parent_load_marker = "learning_load"
    banner_idx = src.find(banner_marker)
    subshell_idx = src.find(subshell_marker)
    check("[learn] banner marker present in source",
          banner_idx != -1, banner_marker)
    check("[learn] override-config subshell present in source",
          subshell_idx != -1, subshell_marker)
    if banner_idx == -1 or subshell_idx == -1:
        return
    # learning_load must appear between the end of the helper definitions and
    # the override-config subshell, in the parent shell's main block.
    # The helpers end at the VIBE_SOURCE_ONLY return; search AFTER that.
    source_guard = src.find('[ "${VIBE_SOURCE_ONLY:-}" = "1" ]')
    check("[learn] VIBE_SOURCE_ONLY guard present", source_guard != -1)
    if source_guard == -1:
        return
    # Find the first parent-shell learning_load call after the guard and
    # before the override-config subshell.
    parent_load_idx = src.find(parent_load_marker, source_guard)
    check("[learn] parent-shell learning_load call exists",
          parent_load_idx != -1 and parent_load_idx < subshell_idx,
          f"parent_load_idx={parent_load_idx} subshell_idx={subshell_idx}")


# ── vibe-copy tests ───────────────────────────────────────────────────────────

def test_vibe_copy_stdin_roundtrip() -> None:
    """AC4: stdin input round-trip — base64 payload decodes to input bytes."""
    print("\n[vibe-copy AC4: stdin roundtrip]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"hello world\n"
        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] stdin roundtrip exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        tty_output = tty.read_bytes()
        expected_prefix = b"\x1b]52;c;"
        expected_suffix = b"\x07"
        check("[copy] stdin OSC 52 prefix", tty_output.startswith(expected_prefix),
              repr(tty_output[:20]))
        check("[copy] stdin OSC 52 suffix", tty_output.endswith(expected_suffix),
              repr(tty_output[-10:]))

        if tty_output.startswith(expected_prefix) and tty_output.endswith(expected_suffix):
            payload = tty_output[len(expected_prefix):-len(expected_suffix)]
            decoded = base64.b64decode(payload)
            check("[copy] stdin base64 decodes to input", decoded == input_bytes,
                  f"decoded={decoded!r} input={input_bytes!r}")


def test_vibe_copy_file_arg_roundtrip() -> None:
    """AC4: file argument round-trip — base64 payload decodes to file bytes."""
    print("\n[vibe-copy AC4: file arg roundtrip]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"hello world\n"
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] file arg exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        tty_output = tty.read_bytes()
        expected_prefix = b"\x1b]52;c;"
        expected_suffix = b"\x07"
        check("[copy] file arg OSC 52 prefix", tty_output.startswith(expected_prefix),
              repr(tty_output[:20]))
        check("[copy] file arg OSC 52 suffix", tty_output.endswith(expected_suffix),
              repr(tty_output[-10:]))

        if tty_output.startswith(expected_prefix) and tty_output.endswith(expected_suffix):
            payload = tty_output[len(expected_prefix):-len(expected_suffix)]
            decoded = base64.b64decode(payload)
            check("[copy] file arg base64 decodes to input", decoded == input_bytes,
                  f"decoded={decoded!r} input={input_bytes!r}")


def test_vibe_copy_scratch_file_written() -> None:
    """AC5: scratch file write — copy-latest.txt contains exact input bytes."""
    print("\n[vibe-copy AC5: scratch file write]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"test content\n"
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] scratch write exit 0", r.returncode == 0, f"exit={r.returncode}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] scratch file exists", scratch_file.exists(), str(scratch_file))
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] scratch file matches input", content == input_bytes,
                  f"got {len(content)} bytes, expected {len(input_bytes)}")


def test_vibe_copy_empty_input_stdin() -> None:
    """AC9: empty input — emits valid empty OSC 52, writes zero-byte scratch, exit 0."""
    print("\n[vibe-copy AC9: empty input]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=b"")

        check("[copy] empty input exit 0", r.returncode == 0, f"exit={r.returncode}")

        tty_output = tty.read_bytes()
        expected = b"\x1b]52;c;\x07"
        check("[copy] empty input emits correct OSC 52", tty_output == expected,
              f"got {tty_output!r} expected {expected!r}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] empty input scratch exists", scratch_file.exists())
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] empty input scratch is zero bytes", len(content) == 0,
                  f"got {len(content)} bytes")

        check("[copy] empty input stderr empty", r.stderr == b"",
              f"stderr: {r.stderr!r}")


def test_vibe_copy_warn_at_8kib_plus_one() -> None:
    """AC6: 8 KiB warn — input > 8192 bytes emits warning but still emits OSC 52."""
    print("\n[vibe-copy AC6: 8 KiB warn]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"x" * 8193
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] 8k+1 exit 0", r.returncode == 0, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] 8k+1 warns 8193 bytes", "vibe-copy: warning: input is 8193 bytes" in stderr_str,
              f"stderr: {stderr_str}")
        check("[copy] 8k+1 mentions 8192 threshold", "8192 bytes" in stderr_str,
              f"stderr: {stderr_str}")

        tty_output = tty.read_bytes()
        check("[copy] 8k+1 still emits OSC 52", tty_output.startswith(b"\x1b]52;c;") and tty_output.endswith(b"\x07"),
              f"tty output: {tty_output[:30]!r}...{tty_output[-10:]!r}")

        if tty_output.startswith(b"\x1b]52;c;") and tty_output.endswith(b"\x07"):
            payload = tty_output[len(b"\x1b]52;c;"):-len(b"\x07")]
            decoded = base64.b64decode(payload)
            check("[copy] 8k+1 payload matches input", decoded == input_bytes,
                  f"decoded size {len(decoded)} vs input size {len(input_bytes)}")

        scratch_file = scratch / "copy-latest.txt"
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] 8k+1 scratch written", content == input_bytes,
                  f"got {len(content)} bytes")
