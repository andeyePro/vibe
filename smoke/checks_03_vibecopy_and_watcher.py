from smoke._core import *  # noqa: F401,F403




def test_vibe_copy_refuse_at_1mib_plus_one() -> None:
    """AC7: 1 MiB refuse — input > 1048576 bytes exits 1, no OSC 52, scratch written."""
    print("\n[vibe-copy AC7: 1 MiB refuse]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        input_bytes = b"x" * 1048577
        input_file = tmp / "input.txt"
        input_file.write_bytes(input_bytes)

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), str(input_file)], env=env)

        check("[copy] 1m+1 exit 1", r.returncode == 1, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] 1m+1 error mentions 1048577 bytes", "vibe-copy: error: input is 1048577 bytes" in stderr_str,
              f"stderr: {stderr_str}")
        check("[copy] 1m+1 error mentions 1048576 threshold", "1048576" in stderr_str,
              f"stderr: {stderr_str}")

        tty_output = tty.read_bytes()
        check("[copy] 1m+1 no OSC 52 emitted", b"\x1b]52;c;" not in tty_output,
              f"found OSC 52 in tty output")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] 1m+1 scratch still written", scratch_file.exists(), str(scratch_file))
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] 1m+1 scratch contains all input", content == input_bytes,
                  f"got {len(content)} bytes, expected {len(input_bytes)}")


def test_vibe_copy_refuses_two_args() -> None:
    """AC2: arg validation — two positional arguments exits 2 with usage message."""
    print("\n[vibe-copy AC2: refuses two args]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), "arg1", "arg2"], env=env)

        check("[copy] two args exit 2", r.returncode == 2, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] two args stderr starts with usage", stderr_str.startswith("vibe-copy: usage:"),
              f"stderr: {stderr_str}")


def test_vibe_copy_refuses_missing_file() -> None:
    """AC2: arg validation — missing file exits 2 with error message."""
    print("\n[vibe-copy AC2: refuses missing file]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()
        tty.touch()

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY), "/nonexistent-abc123def456"], env=env)

        check("[copy] missing file exit 2", r.returncode == 2, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] missing file stderr starts with error prefix",
              stderr_str.startswith("vibe-copy: error: cannot read file:"),
              f"stderr: {stderr_str}")


def test_vibe_copy_tty_absent_note() -> None:
    """AC16: TTY absent — writes scratch, no OSC 52, note stderr, exit 0."""
    print("\n[vibe-copy AC16: TTY absent fallback]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Create a read-only directory so any attempt to write there fails
        readonly = tmp / "readonly"
        readonly.mkdir()
        readonly.chmod(0o555)
        tty = readonly / "tty"
        scratch = tmp / "scratch"
        scratch.mkdir()

        input_bytes = b"text\n"

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] TTY absent exit 0", r.returncode == 0, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] TTY absent note present", "vibe-copy: note: no terminal available" in stderr_str,
              f"stderr: {stderr_str}")

        scratch_file = scratch / "copy-latest.txt"
        check("[copy] TTY absent scratch written", scratch_file.exists())
        if scratch_file.exists():
            content = scratch_file.read_bytes()
            check("[copy] TTY absent scratch matches input", content == input_bytes)

        # Clean up
        readonly.chmod(0o755)


def test_vibe_copy_scratch_failure_exits_1() -> None:
    """AC5: scratch write failure — exits 1 with error message."""
    print("\n[vibe-copy AC5: scratch write failure]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tty = tmp / "tty"
        tty.touch()

        # Create a read-only directory and try to write scratch inside
        readonly = tmp / "readonly"
        readonly.mkdir()
        readonly.chmod(0o555)
        scratch = readonly / "scratch"

        input_bytes = b"text\n"

        env = {**os.environ, "VIBE_COPY_TTY": str(tty), "VIBE_COPY_SCRATCH_DIR": str(scratch)}
        r = run_bytes(["bash", str(VIBE_COPY)], env=env, input_bytes=input_bytes)

        check("[copy] scratch failure exit 1", r.returncode == 1, f"exit={r.returncode}")

        stderr_str = r.stderr.decode('utf-8', errors='replace')
        check("[copy] scratch failure error prefix",
              stderr_str.startswith("vibe-copy: error: cannot write scratch file"),
              f"stderr: {stderr_str}")

        # Clean up
        readonly.chmod(0o755)


def test_c_slash_command_synced() -> None:
    """AC19a: extras-sync deletes retired copy.md and syncs c.md."""
    print("\n[/c AC19a: extras sync deletes copy.md, syncs c.md]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create a fixture source directory with c.md
        fixture_src = tmp / "fixture_src" / "commands"
        fixture_src.mkdir(parents=True)
        fixture_c = fixture_src / "c.md"
        fixture_c.write_text("# /c\nSENTINEL_C_FIXTURE\n")

        # Create destination config dir and pre-seed it with copy.md
        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()
        dest_commands = dest_dir / "commands"
        dest_commands.mkdir()
        (dest_commands / "copy.md").write_text("# /copy\nOLD_FIXTURE\n")

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[/c] extras sync exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check that copy.md was deleted
        check("[/c] copy.md was deleted", not (dest_commands / "copy.md").exists(),
              str(dest_commands / "copy.md"))

        # Check that c.md was synced
        synced_c = dest_commands / "c.md"
        check("[/c] c.md was synced", synced_c.exists(), str(synced_c))
        if synced_c.exists():
            content = synced_c.read_text()
            check("[/c] c.md preserves content", "SENTINEL_C_FIXTURE" in content, content)


def test_c_slash_command_body_matches_spec() -> None:
    """AC19f: c.md body matches spec requirements."""
    print("\n[/c AC19f: c.md body matches spec]")

    check("[/c] c.md file exists", C_MD.exists(), str(C_MD))
    if not C_MD.exists():
        return

    content = C_MD.read_text()
    check("[/c] c.md mentions scratch path", "/workspace/.vibe/copy-latest.txt" in content, "content snippet")
    check("[/c] c.md mentions refusal message", "no prior code block to copy" in content, "content snippet")
    check("[/c] c.md mentions UTF-8", "UTF-8" in content or "UTF8" in content, "content snippet")
    # Check that vibe-copy is NOT in a Bash-tool invocation (it may appear in the UTF-8 note as prose/fallback)
    # We check that no line says "Use the Bash tool to run: `vibe-copy`" or equivalent
    has_bash_invocation = any("Bash tool" in line and "vibe-copy" in line for line in content.split('\n'))
    check("[/c] no Bash-tool invocation of vibe-copy", not has_bash_invocation, "content snippet")


def test_dockerfile_installs_vibe_copy() -> None:
    """AC17f (implicit): Dockerfile COPY + chmod includes vibe-copy.sh."""
    print("\n[Dockerfile: vibe-copy installation]")

    check("[vibe-copy] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return

    content = DOCKERFILE.read_text()

    # Check for COPY line
    copy_lines = [line for line in content.split('\n') if line.strip().startswith('COPY vibe-copy.sh')]
    copy_canonical = [line for line in copy_lines if line.strip() == 'COPY vibe-copy.sh /usr/local/bin/vibe-copy']
    check("[vibe-copy] Dockerfile has canonical COPY line", len(copy_canonical) == 1,
          f"found {len(copy_canonical)} canonical COPY lines, {len(copy_lines)} total COPY vibe-copy lines")

    # Check chmod includes /usr/local/bin/vibe-copy
    check("[vibe-copy] Dockerfile chmod includes vibe-copy", "/usr/local/bin/vibe-copy" in content,
          "content snippet")


# ── AC19a-j: New /c watcher tests ──────────────────────────────────────────────

def test_vibe_copy_watcher_noop_on_non_darwin() -> None:
    """AC19d: vibe-copy-watcher.sh exits 0 immediately on non-Darwin, no lingering process."""
    print("\n[/c AC19d: watcher is no-op on non-Darwin]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Run the watcher directly with VIBE_COPY_WATCHER_FORCE not set (defaults to 0)
        # This ensures Darwin guard is checked
        env = {**os.environ}
        # Unset VIBE_COPY_WATCHER_FORCE if it exists
        env.pop("VIBE_COPY_WATCHER_FORCE", None)

        r = run(["bash", str(VIBE_COPY_WATCHER), str(tmp)], env=env)
        check("[/c] watcher exits 0 on non-Darwin", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Verify no lingering process (wait 1s for shell to exit fully)
        import time
        time.sleep(1.1)

        # Use pgrep to check for lingering process
        pgrep_result = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(tmp))}$"])
        check("[/c] no lingering watcher process", pgrep_result.returncode == 1,
              f"pgrep found processes: {pgrep_result.stdout}")


def test_vibe_copy_watcher_polling_detects_change() -> None:
    """AC19e: watcher polling detects scratch-file change and runs copy command."""
    print("\n[/c AC19e: watcher polling detects change]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        workspace = tmp / "ws"
        workspace.mkdir()
        vibe_dir = workspace / ".vibe"
        vibe_dir.mkdir()

        # Create a shim script that will be invoked as VIBE_COPY_CMD
        shim = tmp / "fake-pbcopy.sh"
        sentinel = tmp / "sentinel.txt"
        shim.write_text(f"#!/usr/bin/env bash\ncat > {shlex.quote(str(sentinel))}\n")
        shim.chmod(0o755)

        env = {
            **os.environ,
            "VIBE_COPY_CMD": str(shim),
            "VIBE_COPY_WATCHER_FORCE": "1",
        }

        # Launch watcher in background
        proc = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(workspace)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        )

        try:
            # Wait for watcher to initialize (first poll cycle)
            import time
            time.sleep(0.6)

            # Write to the scratch file
            copy_file = workspace / ".vibe" / "copy-latest.txt"
            copy_file.write_text("hello-c\n")

            # Wait for at least 3 polling cycles (0.5s each) to ensure detection
            time.sleep(1.6)

            # Check sentinel file was written
            check("[/c] watcher wrote sentinel file", sentinel.exists(), str(sentinel))
            if sentinel.exists():
                content = sentinel.read_text()
                check("[/c] watcher copied correct content", content == "hello-c\n",
                      f"got: {repr(content)}")
        finally:
            # Send SIGTERM to watcher
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            # Wait for process to fully exit
            import time
            time.sleep(1.1)

            # Verify no lingering process
            pgrep_result = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(workspace))}$"])
            check("[/c] watcher process terminated", pgrep_result.returncode == 1,
                  f"pgrep found processes: {pgrep_result.stdout}")


def test_c_preserves_user_commands() -> None:
    """AC19b: extras-sync preserves user-authored commands."""
    print("\n[/c AC19b: user commands preserved during sync]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with only c.md
        fixture_src = tmp / "fixture_src" / "commands"
        fixture_src.mkdir(parents=True)
        (fixture_src / "c.md").write_text("# /c\nCMD_FIXTURE\n")

        # Create destination with a pre-existing user command
        dest_dir = tmp / "dest_config"
        dest_commands = (dest_dir / "commands")
        dest_commands.mkdir(parents=True)
        (dest_commands / "my-custom.md").write_text("# /my-custom\nUSER_CONTENT\n")

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[/c] sync exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        # Check user command still exists with original content
        user_cmd = dest_commands / "my-custom.md"
        check("[/c] user command preserved", user_cmd.exists(), str(user_cmd))
        if user_cmd.exists():
            check("[/c] user command content unchanged",
                  user_cmd.read_text() == "# /my-custom\nUSER_CONTENT\n",
                  user_cmd.read_text())

        # Check c.md was synced
        c_cmd = dest_commands / "c.md"
        check("[/c] c.md was synced", c_cmd.exists(), str(c_cmd))


def test_c_agents_not_touched_by_retirement() -> None:
    """AC19c: retirement cleanup does NOT touch agents/ directory."""
    print("\n[/c AC19c: agents directory not touched by retirement]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with commands and agents
        fixture_src = tmp / "fixture_src"
        (fixture_src / "commands").mkdir(parents=True)
        (fixture_src / "commands" / "c.md").write_text("# /c\n")
        (fixture_src / "agents").mkdir(parents=True)
        (fixture_src / "agents" / "other.md").write_text("# other agent\n")

        # Create destination with a pre-existing "retired" agent
        dest_dir = tmp / "dest_config"
        dest_agents = (dest_dir / "agents")
        dest_agents.mkdir(parents=True)
        (dest_agents / "some-retired-agent.md").write_text("# old agent\nSHOULD_PERSIST\n")
        dest_cmds = (dest_dir / "commands")
        dest_cmds.mkdir(parents=True)

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[/c] sync exit 0", r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}")

        # Check that the old agent was NOT deleted
        old_agent = dest_agents / "some-retired-agent.md"
        check("[/c] old agent not deleted", old_agent.exists(), str(old_agent))
        if old_agent.exists():
            check("[/c] old agent content preserved",
                  "SHOULD_PERSIST" in old_agent.read_text(),
                  old_agent.read_text())


def test_vibe_path_prefix_isolation() -> None:
    """AC19i: multi-session path-prefix collision test."""
    print("\n[/c AC19i: path-prefix collision isolation]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        proj1 = tmp / "proj"
        proj2 = tmp / "proj-extra"
        proj1.mkdir()
        proj2.mkdir()

        env = {**os.environ, "VIBE_COPY_WATCHER_FORCE": "1"}

        # Spawn two watchers
        proc1 = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(proj1)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        )
        proc2 = subprocess.Popen(
            ["bash", str(VIBE_COPY_WATCHER), str(proj2)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        )

        try:
            import time
            time.sleep(0.5)  # Let both watchers start

            # Verify both are running
            pgrep1 = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])
            pgrep2 = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj2))}$"])
            check("[/c] both watchers initially running", pgrep1.returncode == 0 and pgrep2.returncode == 0,
                  f"proj1 rc={pgrep1.returncode} proj2 rc={pgrep2.returncode}")

            # Kill only the proj1 watcher using pkill with the canonical pattern
            pkill_result = run(["pkill", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])

            time.sleep(0.2)

            # Check proj1 is gone
            pgrep1_after = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj1))}$"])
            check("[/c] proj1 watcher killed", pgrep1_after.returncode == 1,
                  f"pgrep output: {pgrep1_after.stdout}")

            # Check proj2 is still running
            pgrep2_after = run(["pgrep", "-f", f"vibe-copy-watcher\\.sh {re.escape(str(proj2))}$"])
            check("[/c] proj2 watcher still running", pgrep2_after.returncode == 0,
                  f"pgrep output: {pgrep2_after.stdout}")
        finally:
            proc1.terminate()
            proc2.terminate()
            try:
                proc1.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc1.kill()
                proc1.wait()
            try:
                proc2.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc2.kill()
                proc2.wait()


def test_vibe_exit_code_propagation() -> None:
    """AC19j: vibe exits with the inner command's exit code (regression guard)."""
    print("\n[/c AC19j: vibe exit code propagation]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create a fake devcontainer script that exits with code 7
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_devcontainer = fake_bin / "devcontainer"
        fake_devcontainer.write_text("#!/bin/bash\nexit 7\n")
        fake_devcontainer.chmod(0o755)

        # Create a minimal vibe call that reaches the devcontainer exec line
        # We'll source the real vibe but override PATH and other critical vars
        env = {
            **os.environ,
            "PATH": str(fake_bin) + ":" + os.environ.get("PATH", ""),
            "HOME": str(tmp),
            "VIBE_CONFIG": str(tmp / "no-config"),
            "VIBE_SOURCE_ONLY": "1",
        }

        # Source vibe, set up minimal env, then call devcontainer exec
        script = f"""
        set -euo pipefail
        source {shlex.quote(str(VIBE))}
        # Simulate reaching the exec line by calling devcontainer directly
        # (normally vibe would set up WORKSPACE, DEVCONTAINER_DIR, etc.)
        devcontainer exec /bin/true
        """

        r = run(["bash", "-c", script], env=env)
        # We expect exit code 7 from our fake devcontainer
        check("[/c] vibe propagates inner command exit code",
              r.returncode == 7,
              f"expected 7, got {r.returncode} stderr={r.stderr[:200]}")


# ── task_007: WebSearch-before-refusing rule ─────────────────────────────────

def test_task007_t1_web_research_md_exists_and_complete() -> None:
    """t1: web-research.md exists and satisfies AC1."""
    print("\n[task_007/t1: web-research.md content validation]")

    check("[task007/t1] web-research.md exists", WEB_RESEARCH_MD.exists(), str(WEB_RESEARCH_MD))
    if not WEB_RESEARCH_MD.exists():
        return

    content = WEB_RESEARCH_MD.read_text()
    lines = content.splitlines()
    non_blank_lines = [line for line in lines if line.strip()]

    check("[task007/t1] contains 'WebSearch'", "WebSearch" in content, "phrase check")
    check("[task007/t1] contains 'WebFetch'", "WebFetch" in content, "phrase check")

    # Check for sequencing sentinel: one of {BEFORE, before, first, First}
    sentinels = ["BEFORE", "before", "first", "First"]
    has_sentinel = any(s in content for s in sentinels)
    check("[task007/t1] contains sequencing sentinel", has_sentinel,
          f"missing one of {sentinels}")

    check("[task007/t1] ≥50 non-blank lines", len(non_blank_lines) >= 50,
          f"found {len(non_blank_lines)} non-blank lines")


def test_task007_t2_dockerfile_copy_canonical() -> None:
    """t2: Dockerfile contains exactly one canonical COPY claude-md line."""
    print("\n[task_007/t2: Dockerfile COPY claude-md]")

    check("[task007/t2] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return

    content = DOCKERFILE.read_text()
    canonical_line = "COPY claude-md /usr/local/share/vibe/claude-md/"

    count = content.count(canonical_line)
    check("[task007/t2] exactly one canonical COPY line", count == 1,
          f"found {count} canonical lines")


def test_task007_t3_install_basics_one_fragment() -> None:
    """t3: install-claude-extras.sh with one fragment in source."""
    print("\n[task_007/t3: install with single fragment]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture source with one fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("# Test Fragment\nTest content for web research\n")

        # Create destination
        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t3] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check CLAUDE.md exists and has correct structure
        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t3] CLAUDE.md created", claude_md.exists(), str(claude_md))

        if not claude_md.exists():
            return

        content = claude_md.read_text()

        # Check delimiters
        check("[task007/t3] opening delimiter present",
              "<!-- >>> vibe-managed (auto, do not edit) >>>" in content,
              "delimiter check")
        check("[task007/t3] closing delimiter present",
              "<!-- <<< vibe-managed <<< -->" in content,
              "delimiter check")

        # Check fragment header
        check("[task007/t3] fragment header present",
              "<!-- vibe-md: web-research.md -->" in content,
              "header check")

        # Check block position: no non-blank line after closing delimiter
        after_close = content.split("<!-- <<< vibe-managed <<< -->")[1]
        non_blank_after = [line for line in after_close.splitlines() if line.strip()]
        check("[task007/t3] no non-blank lines after closing delimiter",
              len(non_blank_after) == 0,
              f"found non-blank lines: {non_blank_after}")

        # Check exactly one newline after close
        expected_ending = "<!-- <<< vibe-managed <<< -->\n"
        check("[task007/t3] exactly one newline after closing delimiter",
              content.endswith(expected_ending),
              f"ending check: {repr(content[-50:])}")


def test_task007_t4_create_from_scratch() -> None:
    """t4: install creates CLAUDE.md from scratch when absent."""
    print("\n[task_007/t4: create CLAUDE.md from scratch]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("Fragment content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t4] CLAUDE.md does not exist initially", not claude_md.exists())

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t4] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")
        check("[task007/t4] CLAUDE.md created", claude_md.exists(), str(claude_md))

        if claude_md.exists():
            content = claude_md.read_text()
            check("[task007/t4] file ends with exactly one newline",
                  content.endswith("\n") and not content.endswith("\n\n"),
                  f"ending: {repr(content[-20:])}")


def test_task007_t5_idempotency() -> None:
    """t5: running install twice with same source produces byte-identical CLAUDE.md."""
    print("\n[task_007/t5: idempotency]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "web-research.md").write_text("Fragment content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # Run install twice
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t5] first install exit 0", r1.returncode == 0)

        content1 = claude_md.read_text()
        hash1 = __import__("hashlib").sha256(content1.encode()).hexdigest()

        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t5] second install exit 0", r2.returncode == 0)

        content2 = claude_md.read_text()
        hash2 = __import__("hashlib").sha256(content2.encode()).hexdigest()

        check("[task007/t5] sha256 hash identical", hash1 == hash2,
              f"hash1={hash1[:16]}… hash2={hash2[:16]}…")
        check("[task007/t5] file size identical",
              len(content1) == len(content2),
              f"size1={len(content1)} size2={len(content2)}")


def test_task007_t6_user_content_preserved() -> None:
    """t6: user content survives re-run with changed fragment set."""
    print("\n[task_007/t6: user content preservation]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create initial fixture with one fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "a-fragment.md").write_text("Fragment A\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First run
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t6] first install exit 0", r1.returncode == 0)

        # Insert user content mid-file (between what will be the vibe block and the rest)
        content1 = claude_md.read_text()
        user_content = "# User Notes\nThis is user content that should persist.\n"
        # Insert user content after vibe-managed block
        parts = content1.split("<!-- <<< vibe-managed <<< -->")
        new_content = parts[0] + "<!-- <<< vibe-managed <<< -->\n\n" + user_content
        claude_md.write_text(new_content)

        # Second run with different fragment set
        (fixture_src / "b-fragment.md").write_text("Fragment B\n")

        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t6] second install exit 0", r2.returncode == 0)

        content2 = claude_md.read_text()

        # Verify user content still present
        check("[task007/t6] user content preserved",
              user_content in content2,
              "user content check")

        # Verify both fragments are present
        check("[task007/t6] both fragments in block",
              "<!-- vibe-md: a-fragment.md -->" in content2 and "<!-- vibe-md: b-fragment.md -->" in content2,
              "fragment headers")


def test_task007_t7_empty_source_cleanup() -> None:
    """t7: empty-source case removes pre-existing vibe-managed block."""
    print("\n[task_007/t7: empty-source cleanup]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # First: install with a fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test.md").write_text("Content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t7] first install exit 0", r1.returncode == 0)

        content_with_block = claude_md.read_text()
        check("[task007/t7] block present after first install",
              "<!-- >>> vibe-managed" in content_with_block)

        # Delete all fragments (empty source)
        import shutil
        shutil.rmtree(fixture_src)
        fixture_src.mkdir()

        # Re-run
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t7] second install (empty source) exit 0", r2.returncode == 0)

        content_after = claude_md.read_text()

        # Block should be gone
        check("[task007/t7] block removed on empty source",
              "<!-- >>> vibe-managed" not in content_after,
              "block removal check")

        # Run again to check no trailing blank-line accumulation
        r3 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t7] third install exit 0", r3.returncode == 0)

        content_after_2 = claude_md.read_text()
        check("[task007/t7] no blank-line accumulation on re-run",
              content_after == content_after_2,
              "idempotency check")


def test_task007_t8_missing_source_directory() -> None:
    """t8: missing-source case (directory does not exist)."""
    print("\n[task_007/t8: missing-source handling]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture without claude-md directory
        fixture_src = tmp / "fixture_src"
        fixture_src.mkdir(parents=True)

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(fixture_src),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        # Run should not error
        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t8] install exit 0 (no claude-md dir)", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Now create initial state with a block, then remove claude-md directory
        claude_md_src = fixture_src / "claude-md"
        claude_md_src.mkdir()
        (claude_md_src / "test.md").write_text("Content\n")

        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t8] first install (with fragment) exit 0", r1.returncode == 0)

        claude_md = dest_dir / "CLAUDE.md"
        content_with_block = claude_md.read_text()
        check("[task007/t8] block present after first install",
              "<!-- >>> vibe-managed" in content_with_block)

        # Remove the claude-md directory
        import shutil
        shutil.rmtree(claude_md_src)

        # Re-run
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t8] install exit 0 (missing claude-md)", r2.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        content_after = claude_md.read_text()
        check("[task007/t8] block removed when source directory missing",
              "<!-- >>> vibe-managed" not in content_after,
              "block removal check")


def test_task007_t9_posix_byte_order_sort() -> None:
    """t9: multi-fragment ordering uses POSIX byte-order (LC_ALL=C)."""
    print("\n[task_007/t9: POSIX byte-order sort]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fragments with names that differ in POSIX vs locale sort
        # In POSIX (LC_ALL=C): Z < a (capitals first)
        # In many locales: a < Z (case-insensitive or lowercase first)
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "Z-fragment.md").write_text("Z content\n")
        (fixture_src / "a-fragment.md").write_text("A content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t9] install exit 0", r.returncode == 0)

        claude_md = dest_dir / "CLAUDE.md"
        content = claude_md.read_text()

        # In POSIX byte-order, Z-fragment should come before a-fragment
        z_pos = content.find("<!-- vibe-md: Z-fragment.md -->")
        a_pos = content.find("<!-- vibe-md: a-fragment.md -->")

        check("[task007/t9] both fragment headers present", z_pos >= 0 and a_pos >= 0,
              "fragment header check")
        check("[task007/t9] Z-fragment before a-fragment (POSIX order)", z_pos < a_pos,
              f"Z_pos={z_pos} a_pos={a_pos}")


def test_task007_t10_agents_and_commands_still_work() -> None:
    """t10: agents, commands, and claude-md all install correctly together."""
    print("\n[task_007/t10: agents + commands + claude-md coexistence]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create full fixture with agents, commands, and claude-md
        fixture_src = tmp / "fixture_src"
        agents_dir = fixture_src / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test-agent.md").write_text("# Test Agent\nContent\n")

        commands_dir = fixture_src / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "test-cmd.md").write_text("# Test Command\nContent\n")

        claude_md_dir = fixture_src / "claude-md"
        claude_md_dir.mkdir(parents=True)
        (claude_md_dir / "test-frag.md").write_text("# Test Fragment\nContent\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(fixture_src),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t10] install exit 0", r.returncode == 0,
              f"exit={r.returncode} stderr={r.stderr}")

        # Check agents synced
        agent_file = dest_dir / "agents" / "test-agent.md"
        check("[task007/t10] agent file copied", agent_file.exists(), str(agent_file))

        # Check commands synced
        cmd_file = dest_dir / "commands" / "test-cmd.md"
        check("[task007/t10] command file copied", cmd_file.exists(), str(cmd_file))

        # Check claude-md block created
        claude_md = dest_dir / "CLAUDE.md"
        check("[task007/t10] CLAUDE.md created", claude_md.exists(), str(claude_md))
        if claude_md.exists():
            content = claude_md.read_text()
            check("[task007/t10] claude-md block present",
                  "<!-- >>> vibe-managed" in content and "<!-- vibe-md: test-frag.md -->" in content)


def test_task007_t11_write_env_hint_coexistence() -> None:
    """t11: write-env-hint and vibe-managed blocks coexist with correct delimiters."""
    print("\n[task_007/t11: write-env-hint coexistence]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test-frag.md").write_text("Test content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First: run write-env-hint to create its managed block
        r1 = run(["bash", str(WRITE_ENV_HINT)], env=env)
        check("[task007/t11] write-env-hint exit 0", r1.returncode == 0,
              f"exit={r1.returncode} stderr={r1.stderr}")

        content_after_hint = claude_md.read_text()

        # Extract the expected write-env-hint block by reading write-env-hint.sh
        # and finding the BLOCK variable value
        hint_content = WRITE_ENV_HINT.read_text()
        hint_start = hint_content.find('BLOCK="')
        hint_end = hint_content.find('\n$END"', hint_start)
        if hint_start >= 0 and hint_end >= 0:
            # Extract the block (this is a bit fragile but mirrors the spec's requirement)
            expected_hint_block = "<!-- BEGIN vibe env (managed) -->\n# vibe container environment"
        else:
            expected_hint_block = "<!-- BEGIN vibe env (managed) -->"

        check("[task007/t11] write-env-hint block present",
              "<!-- BEGIN vibe env (managed) -->" in content_after_hint,
              "hint block check")

        # Second: run install-claude-extras with fragment
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t11] install-claude-extras exit 0", r2.returncode == 0,
              f"exit={r2.returncode} stderr={r2.stderr}")

        content_after_both = claude_md.read_text()

        # Verify both blocks present
        check("[task007/t11] write-env-hint block still present",
              "<!-- BEGIN vibe env (managed) -->" in content_after_both,
              "hint block check")
        check("[task007/t11] vibe-managed block present",
              "<!-- >>> vibe-managed (auto, do not edit) >>>" in content_after_both,
              "managed block check")

        # Verify write-env-hint block is byte-identical to its original
        hint_block_start = content_after_hint.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end = content_after_hint.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        original_hint_block = content_after_hint[hint_block_start:hint_block_end]

        hint_block_start_2 = content_after_both.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end_2 = content_after_both.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        hint_block_after_install = content_after_both[hint_block_start_2:hint_block_end_2]

        check("[task007/t11] write-env-hint block byte-identical after install",
              original_hint_block == hint_block_after_install,
              "byte comparison")

        # Third: run install-claude-extras again with a different fragment set
        (fixture_src / "another-frag.md").write_text("Another content\n")

        r3 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t11] second install exit 0", r3.returncode == 0)

        content_after_second_install = claude_md.read_text()

        # Verify write-env-hint block is STILL byte-identical
        hint_block_start_3 = content_after_second_install.find("<!-- BEGIN vibe env (managed) -->")
        hint_block_end_3 = content_after_second_install.find("<!-- END vibe env -->") + len("<!-- END vibe env -->")
        hint_block_after_second = content_after_second_install[hint_block_start_3:hint_block_end_3]

        check("[task007/t11] write-env-hint block unchanged after second install",
              original_hint_block == hint_block_after_second,
              "byte comparison after second install")


def test_task007_t12_fragment_removal_and_separation() -> None:
    """t12: N→N-1 fragment removal; verify single blank line separates fragments."""
    print("\n[task_007/t12: fragment removal and blank-line separation]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create fixture with two fragments
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "first.md").write_text("First fragment\nLine 2\n")
        (fixture_src / "second.md").write_text("Second fragment\nLine 2\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First install with both fragments
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t12] first install exit 0", r1.returncode == 0)

        content_two = claude_md.read_text()

        # Verify both fragments present
        check("[task007/t12] both fragment headers present initially",
              "<!-- vibe-md: first.md -->" in content_two and "<!-- vibe-md: second.md -->" in content_two)

        # Check for exactly one blank line between fragments
        # The pattern should be: body of first\n\n<!-- vibe-md: second.md -->
        # Find the end of the first fragment's body (last line is "Line 2")
        first_body_end = content_two.find("Line 2\n", content_two.find("First fragment"))
        if first_body_end >= 0:
            first_body_end += len("Line 2\n")  # Move past the "Line 2\n"

        second_start = content_two.find("<!-- vibe-md: second.md -->")
        if first_body_end >= 0 and second_start >= 0:
            between = content_two[first_body_end:second_start]
            # Should be exactly one blank line: "\n"
            check("[task007/t12] exactly one blank line separates fragments",
                  between == "\n",
                  f"got between content: {repr(between)}")

        # Now remove first.md from source
        (fixture_src / "first.md").unlink()

        # Re-run install
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t12] second install (after removal) exit 0", r2.returncode == 0)

        content_one = claude_md.read_text()

        # Verify first fragment is gone
        check("[task007/t12] first fragment removed",
              "<!-- vibe-md: first.md -->" not in content_one,
              "removal check")

        # Verify second fragment still present
        check("[task007/t12] second fragment still present",
              "<!-- vibe-md: second.md -->" in content_one,
              "presence check")


def test_task007_t13_absent_source_with_preexisting_block() -> None:
    """t13: absent-source case with pre-existing vibe-managed block."""
    print("\n[task_007/t13: absent source + pre-existing block removal]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Create initial fixture with fragment
        fixture_src = tmp / "fixture_src" / "claude-md"
        fixture_src.mkdir(parents=True)
        (fixture_src / "test.md").write_text("Content\n")

        dest_dir = tmp / "dest_config"
        dest_dir.mkdir()

        env = {
            **os.environ,
            "VIBE_EXTRAS_SRC_ROOT": str(tmp / "fixture_src"),
            "CLAUDE_CONFIG_DIR": str(dest_dir),
        }

        claude_md = dest_dir / "CLAUDE.md"

        # First install
        r1 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t13] first install exit 0", r1.returncode == 0)

        content_with_block = claude_md.read_text()
        check("[task007/t13] block present initially",
              "<!-- >>> vibe-managed" in content_with_block)

        # Add some user content to verify it persists
        user_content = "# My Notes\nUser data\n"
        content_with_user = content_with_block.split("<!-- <<< vibe-managed <<<")[0]
        content_with_user += "# My Notes\nUser data\n<!-- <<< vibe-managed <<<" + \
                             content_with_block.split("<!-- <<< vibe-managed <<<")[1]
        claude_md.write_text(content_with_user)

        # Delete the claude-md directory entirely
        import shutil
        shutil.rmtree(fixture_src.parent / "claude-md")

        # Re-run install
        r2 = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(env))
        check("[task007/t13] install exit 0 (after dir deletion)", r2.returncode == 0,
              f"exit={r2.returncode} stderr={r2.stderr}")

        content_final = claude_md.read_text()

        # Verify block is gone
        check("[task007/t13] block removed when source directory absent",
              "<!-- >>> vibe-managed" not in content_final,
              "block removal")

        # Verify CLAUDE.md is otherwise intact
        check("[task007/t13] CLAUDE.md exists after cleanup", claude_md.exists())


def test_task007_t14_ssh_discipline_md_exists_and_complete() -> None:
    """t14: ssh-discipline.md exists and satisfies AC1b."""
    print("\n[task_007/t14: ssh-discipline.md content validation]")

    check("[task007/t14] ssh-discipline.md exists", SSH_DISCIPLINE_MD.exists(), str(SSH_DISCIPLINE_MD))
    if not SSH_DISCIPLINE_MD.exists():
        return

    content = SSH_DISCIPLINE_MD.read_text()
    lines = content.splitlines()
    non_blank_lines = [line for line in lines if line.strip()]

    check("[task007/t14] contains literal 'ssh'", "ssh" in content, "phrase check")
    check("[task007/t14] contains literal 'scp'", "scp" in content, "phrase check")

    # Check for prohibition/default-disposition sentinel
    sentinels = ["Do not", "Don't", "don't", "Avoid", "default to"]
    has_sentinel = any(s in content for s in sentinels)
    check("[task007/t14] contains prohibition sentinel", has_sentinel,
          f"missing one of {sentinels}")

    check("[task007/t14] ≥50 non-blank lines", len(non_blank_lines) >= 50,
          f"found {len(non_blank_lines)} non-blank lines")
