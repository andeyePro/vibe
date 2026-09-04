from smoke._core import *  # noqa: F401,F403





def test_task028_fragment_merges_and_fable_grant() -> None:
    """task_028 AC1-AC10, AC12, AC13: fragment merges, word counts, sentinels, Fable grant."""
    print("\n[task_028: CLAUDE.md fragment merges + single Fable-grant definition]")
    
    # AC1: Exactly 13 .md files in devcontainer/claude-md/
    # Three deleted absent: learn-hook.md, feedback-auto-promote.md, conversation-history.md
    # Three survivors present: learnings.md, auto-memory-scope.md, content-guard.md
    # Ten untouched: web-research, ssh-discipline, brain2, shared-repos, harness-routing,
    #                output-consolidation, project-hygiene, todo-changelog, vibe-cli, workspace-is-the-repo
    claude_md_dir = REPO / "devcontainer" / "claude-md"
    all_md_files = sorted([f.name for f in claude_md_dir.glob("*.md")])
    check("[ac1] exactly 13 .md files in claude-md/", len(all_md_files) == 13, f"found {len(all_md_files)}")
    
    deleted_names = ["learn-hook.md", "feedback-auto-promote.md", "conversation-history.md"]
    for name in deleted_names:
        check(f"[ac1] {name} does not exist", not (claude_md_dir / name).exists(), "")
    
    required_names = ["learnings.md", "auto-memory-scope.md", "content-guard.md"]
    for name in required_names:
        check(f"[ac1] {name} exists", (claude_md_dir / name).exists(), "")
    
    expected_names = {
        "web-research.md", "ssh-discipline.md", "brain2.md", "shared-repos.md",
        "harness-routing.md", "output-consolidation.md", "project-hygiene.md",
        "todo-changelog.md", "vibe-cli.md", "workspace-is-the-repo.md",
        "learnings.md", "auto-memory-scope.md", "content-guard.md"
    }
    check("[ac1] all expected fragment names present", set(all_md_files) == expected_names,
          f"diff: {set(all_md_files).symmetric_difference(expected_names)}")
    
    # AC2: Total words <= 6400
    all_text = "".join((claude_md_dir / f).read_text() for f in all_md_files)
    total_words = len(all_text.split())
    check("[ac2] total fragment words <= 6400", total_words <= 6400, f"found {total_words}")
    
    # AC3: content-guard.md 400-600 words, contains "README.md" and "Content guard"
    content_guard_text = (claude_md_dir / "content-guard.md").read_text()
    cg_words = len(content_guard_text.split())
    check("[ac3] content-guard.md word count 400-600", 400 <= cg_words <= 600, f"found {cg_words}")
    check("[ac3] content-guard.md contains 'README.md'", "README.md" in content_guard_text, "")
    check("[ac3] content-guard.md contains 'Content guard'", "Content guard" in content_guard_text, "")
    
    # AC4: Sentinel strings survive
    learnings_text = (claude_md_dir / "learnings.md").read_text()
    learnings_sentinels = [
        "/learnings", "vibe learn --init", ".no-learn", "grep -r", 'vibe learn "',
        "/learn", "permissionDecision", "ask", "realpath -m", "guard-fs.sh",
        "guard-bash.sh", "bypass the hook", "VIBE_AUTO_PROMOTE", "Y / n / never-ask",
        "YES:", "NO:", "cross-repo", "One prompt per", "vibe learn --push", "VIBE_LEARNING_PATH"
    ]
    for sentinel in learnings_sentinels:
        check(f"[ac4] learnings.md contains '{sentinel}'", sentinel in learnings_text, "")
    
    auto_memory_text = (claude_md_dir / "auto-memory-scope.md").read_text()
    auto_memory_sentinels = [
        "task_014", "~/.vibe/projects/", "/home/node/.claude/projects/", "--continue",
        "/learnings", "*.jsonl", "-workspace", "jq -r", 'type=="user"', 'type=="assistant"',
        "tool_result", "thinking", "tool_use", "ls -t", "vibe-claude-config", "Do not duplicate"
    ]
    for sentinel in auto_memory_sentinels:
        check(f"[ac4] auto-memory-scope.md contains '{sentinel}'", sentinel in auto_memory_text, "")
    
    cg_sentinels = [
        "BLOCK", "WARN", "commit-identity", "users.noreply.github.com",
        "VIBE_CONTENT_GUARD=off", "VIBE_ALLOW_COMMIT=1", "--no-verify",
        ".vibe-content-guard-off", ".vibe-content-allow", "path-warn:",
        "vibe audit", "--history", "--staged", "Co-Authored-By", "pre-push"
    ]
    for sentinel in cg_sentinels:
        check(f"[ac4] content-guard.md contains '{sentinel}'", sentinel in content_guard_text, "")
    
    # AC5: code-check.py exits 0 (will be run at end with full suite)
    # (This is checked when we run the full suite)
    
    # AC6: Sandboxed installer test
    with tempfile.TemporaryDirectory() as td:
        sandbox_env = {
            **os.environ,
            "HOME": td,
            "CLAUDE_CONFIG_DIR": str(Path(td) / ".claude"),
            "GIT_CONFIG_GLOBAL": str(Path(td) / ".gitconfig"),
            "VIBE_AUTO_GITIGNORE": "0",
            "VIBE_EXTRAS_SRC_ROOT": str(REPO / "devcontainer"),
        }
        r = run(["bash", str(INSTALL_EXTRAS)], env=_isolate_extras_env(sandbox_env))
        check("[ac6] installer exits 0", r.returncode == 0, r.stderr)
        
        claude_md = Path(td) / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            installer_claude_md = claude_md.read_text()
            check("[ac6] installer output contains learnings.md marker",
                  "<!-- vibe-md: learnings.md -->" in installer_claude_md, "")
            check("[ac6] installer output contains auto-memory-scope.md marker",
                  "<!-- vibe-md: auto-memory-scope.md -->" in installer_claude_md, "")
            check("[ac6] installer output contains content-guard.md marker",
                  "<!-- vibe-md: content-guard.md -->" in installer_claude_md, "")
            check("[ac6] installer output does not contain 'learn-hook.md'",
                  "learn-hook.md" not in installer_claude_md, "")
            check("[ac6] installer output does not contain 'feedback-auto-promote.md'",
                  "feedback-auto-promote.md" not in installer_claude_md, "")
            check("[ac6] installer output does not contain 'conversation-history.md'",
                  "conversation-history.md" not in installer_claude_md, "")
        else:
            check("[ac6] installer creates CLAUDE.md", False, f"not found at {claude_md}")
    
    # AC7: Fable grant defined once in vs.md § Model economy
    vs_text = VS_MD.read_text()
    vs_lines = vs_text.split('\n')
    
    # Find "Fable grant" heading in vs.md
    fable_grant_idx = None
    for i, line in enumerate(vs_lines):
        if "Fable grant" in line and line.startswith("#"):
            fable_grant_idx = i
            break
    check("[ac7] vs.md has heading with 'Fable grant'", fable_grant_idx is not None, "")
    
    if fable_grant_idx is not None:
        # Find next ## heading
        next_heading_idx = None
        for i in range(fable_grant_idx + 1, len(vs_lines)):
            if vs_lines[i].startswith("## "):
                next_heading_idx = i
                break
        if next_heading_idx is None:
            next_heading_idx = len(vs_lines)
        
        # Check sentinels in section
        section_text = "\n".join(vs_lines[fable_grant_idx:next_heading_idx])
        required_in_section = [
            "--fable-subagents", "--fable", "permits", "never forces",
            "mechanical roles", "vibe --fable", "chair"
        ]
        for sentinel in required_in_section:
            check(f"[ac7] vs.md § Model economy contains '{sentinel}'",
                  sentinel in section_text, "")
    
    # Check vss.md and vsss.md: every line with --fable-subagents also has /vs § Model economy
    vss_text = VSS_MD.read_text()
    vss_lines = vss_text.split('\n')
    vss_fable_count = 0
    for line in vss_lines:
        if "--fable-subagents" in line:
            vss_fable_count += 1
            check(f"[ac7] vss.md line with --fable-subagents also has '/vs § Model economy'",
                  "/vs § Model economy" in line, f"line: {line[:80]}")
    check("[ac7] vss.md --fable-subagents count <= 3", vss_fable_count <= 3, f"found {vss_fable_count}")
    
    vsss_text = VSSS_MD.read_text()
    vsss_lines = vsss_text.split('\n')
    vsss_fable_count = 0
    for line in vsss_lines:
        if "--fable-subagents" in line:
            vsss_fable_count += 1
            check(f"[ac7] vsss.md line with --fable-subagents also has '/vs § Model economy'",
                  "/vs § Model economy" in line, f"line: {line[:80]}")
    check("[ac7] vsss.md --fable-subagents count <= 3", vsss_fable_count <= 3, f"found {vsss_fable_count}")
    
    # Check forbidden phrases occur zero times in vss and vsss
    forbidden_in_vss_vsss = [
        "never forces", "mechanical roles", "sets only the chair",
        "chair model only", "authorises no subagent spend"
    ]
    for phrase in forbidden_in_vss_vsss:
        vss_count = vss_text.count(phrase)
        vsss_count = vsss_text.count(phrase)
        check(f"[ac7] vss.md has zero '{phrase}'", vss_count == 0, f"found {vss_count}")
        check(f"[ac7] vsss.md has zero '{phrase}'", vsss_count == 0, f"found {vsss_count}")
    
    # Check vs.md § Flags entry for --fable-subagents is <= 40 words and contains § Model economy
    flags_section_idx = None
    for i, line in enumerate(vs_lines):
        if line.startswith("## Flags"):
            flags_section_idx = i
            break
    check("[ac7] vs.md has '## Flags' section", flags_section_idx is not None, "")
    
    if flags_section_idx is not None:
        fable_flag_line = None
        for i in range(flags_section_idx, len(vs_lines)):
            if vs_lines[i].startswith("- `") and "--fable-subagents" in vs_lines[i]:
                fable_flag_line = vs_lines[i]
                break
        check("[ac7] vs.md Flags has --fable-subagents bullet", fable_flag_line is not None, "")
        
        if fable_flag_line:
            words = len(fable_flag_line.split())
            check("[ac7] vs.md --fable-subagents flag line <= 40 words", words <= 40, f"found {words}")
            check("[ac7] vs.md --fable-subagents flag line contains '§ Model economy'",
                  "§ Model economy" in fable_flag_line, f"line: {fable_flag_line[:80]}")
    
    # AC8: vs.md+vss.md+vsss.md total words <= 14300 (bumped from 14000 by task_037 for --TDD; 13500->14000 was task_036 for --spec-first; 12900->13500 was task_033 for /wide)
    vs_vss_vsss_text = vs_text + vss_text + vsss_text
    vs_vss_vsss_words = len(vs_vss_vsss_text.split())
    check("[ac8] vs+vss+vsss total words <= 14300", vs_vss_vsss_words <= 14300, f"found {vs_vss_vsss_words}")
    
    # AC9: grep deleted filenames - only permitted in CHANGELOG.md and test names/labels in smoke-test.py
    deleted_filenames = ["learn-hook.md", "feedback-auto-promote.md", "conversation-history.md"]
    search_files = [
        REPO / "README.md",
        REPO / "ONBOARDING.md",
        REPO / "CONTRIBUTING.md",
        REPO / "CLAUDE.md",
        REPO / "MANUAL-TESTS.md",
        REPO / "CHANGELOG.md"
    ]
    
    # For code files, check in whole tree
    for deleted in deleted_filenames:
        # Check if it appears in README, ONBOARDING, CONTRIBUTING, CLAUDE, MANUAL-TESTS
        for search_file in search_files:
            if search_file == REPO / "CHANGELOG.md":
                continue  # CHANGELOG is allowed
            if search_file.exists():
                content = search_file.read_text()
                if deleted in content:
                    check(f"[ac9] {search_file.name} does not mention {deleted}",
                          False, f"found in {search_file.name}")
    
    # Check devcontainer/ and smoke-test.py for deleted filenames
    # In devcontainer, they should not appear
    devcontainer_path = REPO / "devcontainer"
    for root, dirs, files in __import__('os').walk(devcontainer_path):
        for fname in files:
            if fname.endswith(('.sh', '.md', '.json')):
                fpath = Path(root) / fname
                try:
                    content = fpath.read_text()
                    for deleted in deleted_filenames:
                        check(f"[ac9] {fpath.relative_to(REPO)} does not mention {deleted}",
                              deleted not in content, f"found in {fpath.relative_to(REPO)}")
                except:
                    pass
    
    # For smoke-test.py, deleted names are allowed in test function context
    # (AC9 permits mentions in test functions and check labels)
    
    # AC10 (scope lock against the c68707d baseline) was a cycle-time gate,
    # not a regression pin: diffing the whole tree against a fixed historical
    # sha fails on the first unrelated commit. Verified at cycle 1; removed
    # from the permanent suite by the chair (2026-09-02).

    # AC12: Word count floors
    learnings_words = len(learnings_text.split())
    auto_memory_words = len(auto_memory_text.split())
    check("[ac12] learnings.md >= 650 words", learnings_words >= 650, f"found {learnings_words}")
    check("[ac12] auto-memory-scope.md >= 450 words", auto_memory_words >= 450, f"found {auto_memory_words}")
    
    # AC13: the ten untouched fragments carry no reference to the deleted files
    untouched_fragments = [
        "web-research.md", "ssh-discipline.md", "brain2.md", "shared-repos.md",
        "harness-routing.md", "output-consolidation.md", "project-hygiene.md",
        "todo-changelog.md", "vibe-cli.md", "workspace-is-the-repo.md"
    ]
    
    for frag_name in untouched_fragments:
        frag_path = claude_md_dir / frag_name
        current_content = frag_path.read_text()
        
        # Byte-identity against the c68707d baseline was likewise a
        # cycle-time gate (it would freeze these ten fragments forever);
        # verified at cycle 1, dropped from the permanent suite by the chair.
        # Check no deleted filenames appear
        for deleted in deleted_filenames:
            check(f"[ac13] {frag_name} does not contain '{deleted}'",
                  deleted not in current_content, "")



def test_task019_ac16_audit_history_reports_warn_pii() -> None:
    """AC16: vibe audit --history reports WARN PII findings (exit 0)."""
    print("\n[task_019 AC16: audit reports WARN findings]")
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

        # Commit 1: add home path (/.local URL in a URL is not a trailer, so won't be suppressed)
        test_file = repo / "config.txt"
        test_file.write_text("Path to config: /Users/myname/project\n")
        run(["git", "add", "config.txt"], cwd=repo)
        run(["git", "commit", "-m", "Config"], cwd=repo)

        # Get commit sha
        r_sha = run(["git", "rev-parse", "HEAD"], cwd=repo)
        commit_sha = r_sha.stdout.strip()

        # Commit 2: delete path
        test_file.unlink()
        run(["git", "add", "-u"], cwd=repo)
        run(["git", "commit", "-m", "Clean"], cwd=repo)

        # Audit should find WARN but exit 0
        r = run(["bash", str(VIBE)] + ["audit", "--history"], cwd=repo)
        check("[task_019 AC16] audit exit 0 on WARN-only", r.returncode == 0, r.stdout + r.stderr)
        check("[task_019 AC16] WARN finding reported", "WARN" in r.stdout, r.stdout)
        check("[task_019 AC16] commit sha in output", commit_sha[:8] in r.stdout, r.stdout)


def test_task019_ac17_new_branch_push_blocks_only_block_tier() -> None:
    """AC17: pre-push on new branch scans BLOCK tier only; WARN-only commit pushes."""
    print("\n[task_019 AC17: pre-push BLOCK-tier-only on new branch]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()

        # Setup local repo
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Create local bare remote
        bare_remote = Path(td) / "remote.git"
        bare_remote.mkdir()
        run(["git", "init", "--bare"], cwd=bare_remote)
        run(["git", "remote", "add", "origin", str(bare_remote)], cwd=repo)

        # Install hooks
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        for name in ["pre-push"]:
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

        # Create initial commit on master to establish a branch
        initial_file = repo / "README.md"
        initial_file.write_text("# Test repo\n")
        run(["git", "add", "README.md"], cwd=repo)
        run(["git", "commit", "-m", "Initial commit"], cwd=repo)
        run(["git", "push", "-u", "origin", "master"], cwd=repo)

        # Pin hook discovery to the dir we populated (see AC10): left at
        # /dev/null, the pre-push hook under test would never run and the
        # pushes below would pass vacuously.
        run(["git", "config", "core.hooksPath", str(hooks_dir)], cwd=repo)

        # Commit with WARN-tier PII (RFC1918 IP) on a new branch
        run(["git", "checkout", "-b", "feature"], cwd=repo)
        test_file = repo / "config.txt"
        test_file.write_text("Server at 192.168.0.99\n")
        run(["git", "add", "config.txt"], cwd=repo)
        run(["git", "commit", "-m", "Add config with IP"], cwd=repo)

        # Push new branch should succeed (pre-push scans BLOCK tier only, so WARN is allowed)
        r = run(["git", "push", "-u", "origin", "feature"], cwd=repo)
        check("[task_019 AC17] new branch push succeeds", r.returncode == 0, r.stderr)


def test_prepush_no_walk_ignores_already_pushed_history() -> None:
    """Regression (2026-08-30): the pre-push new-branch scan must diff ONLY
    the commits absent from the remote. `git log -p <shas...>` treats
    positional args as revision TIPS and walks ALL reachable history —
    an O(history) scan (8+ min on a large repo) plus false BLOCK hits on
    old, already-pushed commits. --no-walk pins the scan to the listed
    commits."""
    print("\n[pre-push --no-walk: remote-history secret must not block a clean new branch]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()

        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.email", "123+tester@users.noreply.github.com"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        bare_remote = Path(td) / "remote.git"
        bare_remote.mkdir()
        run(["git", "init", "--bare"], cwd=bare_remote)
        run(["git", "remote", "add", "origin", str(bare_remote)], cwd=repo)

        # History commit carrying a BLOCK-tier secret, pushed while hooks are
        # neutralised — models legacy/vendored content already on the remote.
        token = "ghp_" + ("C" * 36)
        (repo / "legacy.txt").write_text(f"Token: {token}\n")
        run(["git", "add", "legacy.txt"], cwd=repo)
        run(["git", "commit", "-m", "Legacy commit"], cwd=repo)
        run(["git", "push", "-u", "origin", "master"], cwd=repo)

        # Install pre-push + scanner, then pin hook discovery to them.
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        for name in ["pre-push", "vibe-content-scan.sh"]:
            src = REPO / "devcontainer" / "git-hooks" / name
            dst = hooks_dir / name
            shutil.copy2(src, dst)
            dst.chmod(0o755)
        run(["git", "config", "core.hooksPath", str(hooks_dir)], cwd=repo)

        # Clean commit on a new branch: the legacy secret is reachable from
        # the tip but already on the remote — push must succeed.
        run(["git", "checkout", "-b", "feature"], cwd=repo)
        (repo / "clean.txt").write_text("nothing to see\n")
        run(["git", "add", "clean.txt"], cwd=repo)
        run(["git", "commit", "-m", "Clean commit"], cwd=repo)
        r = run(["git", "push", "-u", "origin", "feature"], cwd=repo)
        check("[pre-push --no-walk] clean new branch pushes despite remote-history secret",
              r.returncode == 0, r.stderr)

        # Control: a NEW secret commit on another new branch must still block
        # (--no-walk must not skip the listed commits themselves).
        run(["git", "checkout", "-b", "feature2", "master"], cwd=repo)
        token2 = "ghp_" + ("D" * 36)
        (repo / "fresh-secret.txt").write_text(f"Token: {token2}\n")
        run(["git", "add", "fresh-secret.txt"], cwd=repo)
        run(["git", "commit", "-m", "Fresh secret"], cwd=repo)  # no pre-commit installed here
        r2 = run(["git", "push", "-u", "origin", "feature2"], cwd=repo)
        check("[pre-push --no-walk] new-branch secret still blocks",
              r2.returncode != 0, r2.stderr)


def test_task021_ac1_identity_mode_warns_on_real_email() -> None:
    """AC1: scanner --identity WARNs (exit 1) on a non-noreply user.email,
    passes noreply forms, and respects the per-repo allowlist."""
    print("\n[task_021 AC1: --identity mode]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)

        # Real personal email -> WARN, exit 1
        run(["git", "config", "user.email", "someone@example.com"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_021 AC1] real email exits 1", r.returncode == 1, r.stderr)
        check("[task_021 AC1] rule is commit-identity", "commit-identity" in r.stderr, r.stderr)

        # ID-form noreply -> clean
        run(["git", "config", "user.email", "6342315+Aqueum@users.noreply.github.com"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_021 AC1] ID-form noreply exits 0", r.returncode == 0, r.stderr)

        # Username-form noreply -> clean
        run(["git", "config", "user.email", "Aqueum@users.noreply.github.com"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_021 AC1] username-form noreply exits 0", r.returncode == 0, r.stderr)

        # Explicit value argument (audit path) -> WARN on real email
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity", "boss@corp.com"], cwd=repo)
        check("[task_021 AC1] explicit value exits 1", r.returncode == 1, r.stderr)

        # Allowlisted deliberate identity -> clean
        run(["git", "config", "user.email", "someone@example.com"], cwd=repo)
        (repo / ".vibe-content-allow").write_text("^someone@example\\.com$\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_021 AC1] allowlisted email exits 0", r.returncode == 0, r.stderr)


def test_task021_ac2_precommit_warns_on_real_email_identity() -> None:
    """AC2: real pre-commit hook rejects a commit made as a non-noreply
    identity even when the diff itself is clean; passes after switching
    the repo's user.email to a noreply form."""
    print("\n[task_021 AC2: pre-commit identity gate]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        hooks_dir = repo / ".git" / "hooks"
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "someone@example.com"], cwd=repo)

        hooks_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        for name in ["pre-commit", "vibe-content-scan.sh"]:
            src = REPO / "devcontainer" / "git-hooks" / name
            dst = hooks_dir / name
            shutil.copy2(src, dst)
            dst.chmod(0o755)

        # Pin hook discovery (see task_019 AC10): environment-level
        # core.hooksPath must not bypass the hooks under test.
        run(["git", "config", "core.hooksPath", str(hooks_dir)], cwd=repo)

        (repo / "good.txt").write_text("Hello world\n")
        run(["git", "add", "good.txt"], cwd=repo)
        r_bad = run(["git", "commit", "-m", "Good commit"], cwd=repo)
        check("[task_021 AC2] commit as real email fails", r_bad.returncode != 0, r_bad.stderr)
        check("[task_021 AC2] names commit-identity", "commit-identity" in r_bad.stderr, r_bad.stderr)

        run(["git", "config", "user.email", "123+tester@users.noreply.github.com"], cwd=repo)
        r_ok = run(["git", "commit", "-m", "Good commit"], cwd=repo)
        check("[task_021 AC2] commit as noreply succeeds", r_ok.returncode == 0, r_ok.stderr)


def test_task021_ac3_audit_history_reports_identities() -> None:
    """AC3: vibe audit --history lists non-noreply author/committer
    identities from history as WARN commit-identity findings (exit 0)."""
    print("\n[task_021 AC3: audit identities pass]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "hidden@personal.net"], cwd=repo)
        (repo / "a.txt").write_text("clean content\n")
        run(["git", "add", "a.txt"], cwd=repo)
        run(["git", "commit", "-m", "Clean"], cwd=repo)

        r = run(["bash", str(VIBE), "audit", "--history"], cwd=repo)
        check("[task_021 AC3] WARN-only exits 0", r.returncode == 0, r.stdout + r.stderr)
        check("[task_021 AC3] commit-identity reported", "commit-identity" in r.stdout, r.stdout)
        check("[task_021 AC3] email named", "hidden@personal.net" in r.stdout, r.stdout)


def test_task020_ac1_default_opted_out() -> None:
    print("\n[task_020 AC1: default (no signal) -> OP opted OUT]")
    res = _op_opted_in_result({}, 'git -C "$WS" init -q')
    check("[task_020 AC1] no VIBE_OP_AUTO + no marker -> OUT", res == "OUT", res)


def test_task020_ac2_global_auto_opts_in() -> None:
    print("\n[task_020 AC2: VIBE_OP_AUTO=1 -> opted IN]")
    res = _op_opted_in_result({"VIBE_OP_AUTO": "1"}, 'git -C "$WS" init -q')
    check("[task_020 AC2] VIBE_OP_AUTO=1 -> IN", res == "IN", res)


def test_task020_ac3_untracked_marker_opts_in() -> None:
    print("\n[task_020 AC3: untracked .vibe-allow-op -> opted IN]")
    res = _op_opted_in_result({}, 'git -C "$WS" init -q; touch "$WS/.vibe-allow-op"')
    check("[task_020 AC3] untracked marker -> IN", res == "IN", res)


def test_task020_ac4_committed_marker_refused() -> None:
    print("\n[task_020 AC4: COMMITTED .vibe-allow-op refused (forge-resistant)]")
    setup = (
        'git -C "$WS" init -q; git -C "$WS" config user.email t@t; '
        'git -C "$WS" config user.name t; '
        'git -C "$WS" config core.hooksPath /dev/null; '
        'touch "$WS/.vibe-allow-op"; '
        'git -C "$WS" add .vibe-allow-op; git -C "$WS" commit -qm x'
    )
    res = _op_opted_in_result({}, setup)
    check("[task_020 AC4] committed marker -> OUT (refused)", res == "OUT", res)


def test_task020_ac6_non_git_workspace_refused() -> None:
    print("\n[task_020 AC6: marker in a NON-git workspace refused (fail closed)]")
    # No `git init` — bare dir with a marker (mimics a ZIP/tarball download).
    res = _op_opted_in_result({}, 'touch "$WS/.vibe-allow-op"')
    check("[task_020 AC6] non-git marker -> OUT (fail closed)", res == "OUT", res)


def test_task020_ac5_cred_load_gated() -> None:
    print("\n[task_020 AC5: OP cred load is gated on _op_opted_in]")
    src = VIBE.read_text(encoding="utf-8")
    check("[task_020 AC5] cred load guarded by _op_opted_in",
          'if _op_opted_in "$WORKSPACE"; then' in src
          and 'OPENPROJECT_MCP_URL=$(lookup_token "OPENPROJECT_MCP_URL")' in src, "")
    # And the guard precedes the export/forwarder (creds empty when opted out)
    guarded = src.split('if _op_opted_in "$WORKSPACE"; then', 1)
    check("[task_020 AC5] opted-out branch empties the creds",
          len(guarded) == 2 and 'OPENPROJECT_MCP_URL=""' in guarded[1][:400], "")


def test_task022_ac2_corpus_message_mode() -> None:
    """AC2: frozen expected-findings corpus via --message (canonical, one
    location per finding — 'message'). Every rule id, mdns boundary cases,
    email exemptions, both trailer exemption shapes, and the nocasematch-leak
    probe are exercised; exact (class, rule) multiset is pinned."""
    print("\n[task_022 AC2: corpus via --message]")
    with tempfile.TemporaryDirectory() as td:
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text("\n".join(l for l, _ in TASK022_CORPUS) + "\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        findings = _task022_parse_findings(r.stderr)
        actual = _task022_counts(findings)
        check("[task_022 AC2 msg] exit 1 (BLOCK findings present)", r.returncode == 1, r.stderr)
        check("[task_022 AC2 msg] finding multiset matches frozen corpus",
              actual == TASK022_EXPECTED_ALL,
              f"expected={TASK022_EXPECTED_ALL} actual={actual}")
        check("[task_022 AC2 msg] total finding count == 17", len(findings) == 17, str(len(findings)))
        # A2 leftmost-match parity: exact snippet for a couple of rules.
        gh = [f for f in findings if f[2] == "github-pat"]
        check("[task_022 AC2 msg] github-pat snippet exact",
              bool(gh) and gh[0][3] == "ghp_" + "A" * 36, str(gh))
        # nocasematch-leak proof: only 3 mdns-local findings total (the leak
        # probe line's uppercase FOO.LOCAL must not add a 4th).
        mdns = [f for f in findings if f[2] == "mdns-local"]
        check("[task_022 AC2 msg] exactly 3 mdns-local (no leak from icase probe)",
              len(mdns) == 3, str(mdns))


def test_task022_ac2_corpus_blob_stdin_mode() -> None:
    """AC2: same corpus via --blob-stdin (git log -p shape: 'commit <sha>'
    header + '+'-prefixed content lines) — same frozen multiset."""
    print("\n[task_022 AC2: corpus via --blob-stdin]")
    with tempfile.TemporaryDirectory() as td:
        stream = "commit deadbeefcafefeedfacefeeddeadbeefcafefeed\n"
        stream += "\n".join("+" + l for l, _ in TASK022_CORPUS) + "\n"
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        findings = _task022_parse_findings(r.stderr)
        actual = _task022_counts(findings)
        check("[task_022 AC2 blob] exit 1", r.returncode == 1, r.stderr)
        check("[task_022 AC2 blob] finding multiset matches frozen corpus",
              actual == TASK022_EXPECTED_ALL,
              f"expected={TASK022_EXPECTED_ALL} actual={actual}")


def test_task022_ac2_corpus_staged_mode() -> None:
    """AC2: same corpus via --staged on a fixture repo (tier=both, diff-based
    file:line location tracking) — same frozen multiset."""
    print("\n[task_022 AC2: corpus via --staged]")
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
        f = repo / "corpus.txt"
        f.write_text("\n".join(l for l, _ in TASK022_CORPUS) + "\n")
        run(["git", "add", "corpus.txt"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        actual = _task022_counts(findings)
        check("[task_022 AC2 staged] exit 1", r.returncode == 1, r.stderr)
        check("[task_022 AC2 staged] finding multiset matches frozen corpus",
              actual == TASK022_EXPECTED_ALL,
              f"expected={TASK022_EXPECTED_ALL} actual={actual}")
        check("[task_022 AC2 staged] locations are file:line",
              all(f[1].startswith("corpus.txt:") for f in findings), str(findings[:3]))


def test_task022_ac2_corpus_range_block_tier_only() -> None:
    """AC2: same corpus via --range on a fixture repo — tier=block, so ONLY
    BLOCK-tier rules may fire; every WARN-tier corpus line must be silent.
    This is the direct proof of the tier-block path the other three entry
    points don't exercise."""
    print("\n[task_022 AC2: corpus via --range (BLOCK tier only)]")
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
        f = repo / "corpus.txt"
        f.write_text("placeholder\n")
        run(["git", "add", "corpus.txt"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        f.write_text("\n".join(l for l, _ in TASK022_CORPUS) + "\n")
        run(["git", "add", "corpus.txt"], cwd=repo)
        run(["git", "commit", "-m", "add corpus"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        actual = _task022_counts(findings)
        check("[task_022 AC2 range] exit 1 (BLOCK findings present)", r.returncode == 1, r.stderr)
        check("[task_022 AC2 range] finding multiset == BLOCK-only subset",
              actual == TASK022_EXPECTED_BLOCK_ONLY,
              f"expected={TASK022_EXPECTED_BLOCK_ONLY} actual={actual}")
        check("[task_022 AC2 range] no WARN finding leaked through tier=block",
              all(f[0] != "WARN" for f in findings), str(findings))


def test_task022_ac2_clean_block_no_crash() -> None:
    """AC2/A2b: a block of lines matching no rule at all must exit 0 with
    zero findings — the direct set -e survival proof (a bare unguarded
    `[[ =~ ]]` would die on the first clean line)."""
    print("\n[task_022 AC2: clean block exits 0, no crash]")
    with tempfile.TemporaryDirectory() as td:
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text("\n".join(TASK022_CLEAN_LINES) + "\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_022 AC2 clean] exit 0", r.returncode == 0, r.stderr)
        check("[task_022 AC2 clean] no findings", len(r.stderr.strip()) == 0, r.stderr)


def test_task022_ac2_allowlist_suppression() -> None:
    """AC2: .vibe-content-allow suppresses a corpus-shaped finding under the
    new primitives; without the allowlist the same content still fires."""
    print("\n[task_022 AC2: allowlist suppression]")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".vibe-content-allow").write_text(r"10\.0\.0\.5" + "\n")
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text("Server ip 10.0.0.5 today\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_022 AC2 allow] exit 0 with allowlist", r.returncode == 0, r.stderr)
        check("[task_022 AC2 allow] no findings", len(r.stderr.strip()) == 0, r.stderr)

    with tempfile.TemporaryDirectory() as td:
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text("Server ip 10.0.0.5 today\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_022 AC2 allow] exit 1 without allowlist", r.returncode == 1, r.stderr)


def test_task022_ac3_messages_stdin_parity_and_attribution() -> None:
    """AC3: for a fixture repo with a secret commit, a PII commit, a
    Co-authored-by trailer, and a body line starting with 'commit deadbeef',
    the new --messages-stdin pass produces a byte-identical sorted finding
    set to the old per-commit --message+relabel loop, with correct per-sha
    attribution (never misattributed to the literal 'deadbeef' text)."""
    print("\n[task_022 AC3: message parity + attribution]")
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

        (repo / "a.txt").write_text("x\n")
        run(["git", "add", "a.txt"], cwd=repo)
        run(["git", "commit", "-m",
             "Add AWS creds AKIAABCD1234EFGH5678 by mistake\n\n"
             "Co-authored-by: Claude <noreply@anthropic.com>"], cwd=repo)
        sha_a = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        (repo / "a.txt").write_text("y\n")
        run(["git", "add", "a.txt"], cwd=repo)
        run(["git", "commit", "-m", "PII drop: server at 192.168.7.7"], cwd=repo)
        sha_b = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        (repo / "a.txt").write_text("z\n")
        run(["git", "add", "a.txt"], cwd=repo)
        run(["git", "commit", "-m",
             "commit deadbeef was reverted, token: ABCDEFGHIJKLMNOPQRSTUVWX1234"], cwd=repo)
        sha_c = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        # OLD-style: per-commit --message, then relabel 'message' -> 'commit <sha>'.
        shas = run(["git", "log", "--all", "--format=%H"], cwd=repo).stdout.split()
        old_lines = []
        for sha in shas:
            body = run(["git", "show", "-s", "--format=%B", sha], cwd=repo).stdout
            mf = Path(td) / f"msg-{sha}.txt"
            mf.write_text(body)
            r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(mf)], cwd=repo)
            for line in r.stderr.splitlines():
                parts = line.split("\t")
                if len(parts) == 4 and parts[1] == "message":
                    parts[1] = f"commit {sha}"
                    old_lines.append("\t".join(parts))
        old_sorted = sorted(old_lines)

        # NEW: single --messages-stdin pipe.
        logp = run(["git", "log", "--all", "-z", "--format=%H%n%B"], cwd=repo)
        r_new = subprocess.run(
            ["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
            input=logp.stdout.encode(), capture_output=True, cwd=repo,
        )
        new_stderr = r_new.stderr.decode()
        new_lines = [l for l in new_stderr.splitlines() if l.count("\t") == 3]
        new_sorted = sorted(new_lines)

        check("[task_022 AC3] old vs new sorted finding sets byte-identical",
              old_sorted == new_sorted, f"old={old_sorted} new={new_sorted}")
        check("[task_022 AC3] exactly 3 findings", len(new_lines) == 3, str(new_lines))

        locs = [l.split("\t")[1] for l in new_lines]
        check("[task_022 AC3] every location attributed to a real commit sha",
              all(loc in (f"commit {sha_a}", f"commit {sha_b}", f"commit {sha_c}") for loc in locs),
              str(locs))
        check("[task_022 AC3] no misattribution to the literal 'deadbeef' text",
              all("deadbeef" not in loc for loc in locs), str(locs))
        check("[task_022 AC3] aws-access-key attributed to sha_a",
              f"commit {sha_a}" in [l.split("\t")[1] for l in new_lines if "aws-access-key" in l], str(new_lines))
        check("[task_022 AC3] rfc1918-ip attributed to sha_b",
              f"commit {sha_b}" in [l.split("\t")[1] for l in new_lines if "rfc1918-ip" in l], str(new_lines))
        check("[task_022 AC3] secret-assignment (in the 'commit deadbeef' body line) attributed to sha_c",
              f"commit {sha_c}" in [l.split("\t")[1] for l in new_lines if "secret-assignment" in l], str(new_lines))


def test_task022_ac5_messages_stdin_malformed_inputs() -> None:
    """AC5: --messages-stdin must not crash (set -euo pipefail is active) and
    must not misattribute findings on three malformed shapes in one stream:
    an empty record, a body-only record with no sha line, a normal valid
    record, and — with no trailing NUL — a truncated final record."""
    print("\n[task_022 AC5: --messages-stdin malformed inputs]")
    sha1 = "1111111111111111111111111111111111aaaa"
    sha2 = "2222222222222222222222222222222222bbbb"

    record_empty = b""
    record_bodyonly = b"\nBody text sk-" + b"C" * 24  # no sha line -> skip
    record_valid = sha1.encode() + b"\nSecret: token=" + b"B" * 20
    record_truncated = sha2.encode() + b"\nAWS key: AKIA" + b"Z" * 16  # no trailing NUL

    stream = (record_empty + b"\x00" + record_bodyonly + b"\x00"
              + record_valid + b"\x00" + record_truncated)

    r = subprocess.run(["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
                        input=stream, capture_output=True)
    check("[task_022 AC5 malformed] does not crash (exit 0 or 1, never 2)",
          r.returncode in (0, 1), str(r.returncode))
    check("[task_022 AC5 malformed] exit 1 (the two valid records both fire)",
          r.returncode == 1, r.stderr.decode())
    check("[task_022 AC5 malformed] stdout empty", r.stdout == b"", str(r.stdout))

    stderr = r.stderr.decode()
    findings = [l for l in stderr.splitlines() if l.count("\t") == 3]
    check("[task_022 AC5 malformed] exactly 2 findings (malformed records silently skipped)",
          len(findings) == 2, str(findings))
    locs = [l.split("\t")[1] for l in findings]
    check("[task_022 AC5 malformed] valid record attributed to sha1",
          f"commit {sha1}" in locs, str(locs))
    check("[task_022 AC5 malformed] truncated final record (no trailing NUL) still processed, attributed to sha2",
          f"commit {sha2}" in locs, str(locs))
    check("[task_022 AC5 malformed] no finding attributed to an empty/malformed location",
          all(loc in (f"commit {sha1}", f"commit {sha2}") for loc in locs), str(locs))


def test_task022_ac5_exit_codes_all_modes() -> None:
    """AC5: every scanner mode retains (or, for --messages-stdin, establishes)
    correct 0/1 exit-code behaviour on crafted clean + dirty fixtures."""
    print("\n[task_022 AC5: exit codes across all modes]")
    token = "ghp_" + "A" * 36

    # --staged
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
        (repo / "clean.txt").write_text("hello world\n")
        run(["git", "add", "clean.txt"], cwd=repo)
        r_clean = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_022 AC5 --staged] clean exits 0", r_clean.returncode == 0, r_clean.stderr)
        (repo / "dirty.txt").write_text(f"{token}\n")
        run(["git", "add", "dirty.txt"], cwd=repo)
        r_dirty = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_022 AC5 --staged] dirty exits 1", r_dirty.returncode == 1, r_dirty.stderr)

    # --message
    with tempfile.TemporaryDirectory() as td:
        clean_f = Path(td) / "clean.txt"
        clean_f.write_text("hello world\n")
        r_clean = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(clean_f)], cwd=td)
        check("[task_022 AC5 --message] clean exits 0", r_clean.returncode == 0, r_clean.stderr)
        dirty_f = Path(td) / "dirty.txt"
        dirty_f.write_text(f"{token}\n")
        r_dirty = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(dirty_f)], cwd=td)
        check("[task_022 AC5 --message] dirty exits 1", r_dirty.returncode == 1, r_dirty.stderr)

    # --messages-stdin
    clean_stream = b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nnothing sensitive here\x00"
    r_clean = subprocess.run(["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
                              input=clean_stream, capture_output=True)
    check("[task_022 AC5 --messages-stdin] clean exits 0", r_clean.returncode == 0, r_clean.stderr.decode())
    dirty_stream = ("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n" + token + "\x00").encode()
    r_dirty = subprocess.run(["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
                              input=dirty_stream, capture_output=True)
    check("[task_022 AC5 --messages-stdin] dirty exits 1", r_dirty.returncode == 1, r_dirty.stderr.decode())

    # --blob-stdin (+ --tier block)
    clean_blob = "commit aaaa\n+nothing sensitive here\n"
    r_clean = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], input=clean_blob)
    check("[task_022 AC5 --blob-stdin] clean exits 0", r_clean.returncode == 0, r_clean.stderr)
    dirty_blob = f"commit bbbb\n+{token}\n"
    r_dirty = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], input=dirty_blob)
    check("[task_022 AC5 --blob-stdin] dirty exits 1", r_dirty.returncode == 1, r_dirty.stderr)
    r_dirty_block = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin", "--tier", "block"], input=dirty_blob)
    check("[task_022 AC5 --blob-stdin --tier block] dirty (BLOCK rule) exits 1",
          r_dirty_block.returncode == 1, r_dirty_block.stderr)
    warn_blob = "commit cccc\n+Server at 192.168.0.99\n"
    r_warn_block = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin", "--tier", "block"], input=warn_blob)
    check("[task_022 AC5 --blob-stdin --tier block] WARN-only content exits 0 (tier gate)",
          r_warn_block.returncode == 0, r_warn_block.stderr)

    # --range
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
        (repo / "f.txt").write_text("base\n")
        run(["git", "add", "f.txt"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        (repo / "f.txt").write_text("base\nhello world\n")
        run(["git", "add", "f.txt"], cwd=repo)
        run(["git", "commit", "-m", "clean add"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        r_clean = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)
        check("[task_022 AC5 --range] clean exits 0", r_clean.returncode == 0, r_clean.stderr)
        (repo / "f.txt").write_text(f"base\nhello world\n{token}\n")
        run(["git", "add", "f.txt"], cwd=repo)
        run(["git", "commit", "-m", "dirty add"], cwd=repo)
        sha3 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        r_dirty = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha2, sha3], cwd=repo)
        check("[task_022 AC5 --range] dirty exits 1", r_dirty.returncode == 1, r_dirty.stderr)

    # --identity
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        run(["git", "init"], cwd=repo)
        # Fixture repo: neutralise the machine-global content-guard hooks at
        # local scope so fixture commits (some deliberately carry secrets/PII)
        # are deterministic; hook-exercising tests re-pin their own hooksPath.
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "123+tester@users.noreply.github.com"], cwd=repo)
        r_clean = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_022 AC5 --identity] noreply exits 0", r_clean.returncode == 0, r_clean.stderr)
        run(["git", "config", "user.email", "real@example.com"], cwd=repo)
        r_dirty = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_022 AC5 --identity] real email exits 1", r_dirty.returncode == 1, r_dirty.stderr)


def test_task022_ac6_override_and_optout_new_primitives() -> None:
    """AC6: VIBE_CONTENT_GUARD=off still exits 0 with the loud override line
    naming skipped rules, and .vibe-content-guard-off still short-circuits to
    0 — both re-verified against the new bash-native match primitives."""
    print("\n[task_022 AC6: override + opt-out under new primitives]")
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
        token = "ghp_" + "A" * 36
        (repo / "secret.txt").write_text(f"My secret is {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)

        env = {**os.environ, "VIBE_CONTENT_GUARD": "off"}
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo, env=env)
        check("[task_022 AC6] override exits 0", r.returncode == 0, r.stderr)
        check("[task_022 AC6] override logs OVERRIDE line", "OVERRIDE" in r.stderr, r.stderr)
        check("[task_022 AC6] override names github-pat", "github-pat" in r.stderr, r.stderr)

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
        (repo / ".vibe-content-guard-off").write_text("")
        token = "ghp_" + "A" * 36
        (repo / "secret.txt").write_text(f"My secret is {token}\n")
        run(["git", "add", "secret.txt"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_022 AC6] opt-out marker exits 0", r.returncode == 0, r.stderr)
        check("[task_022 AC6] opt-out marker: no stderr output", len(r.stderr.strip()) == 0, r.stderr)


def test_task022_ac7_no_bash4_constructs() -> None:
    """AC7(a): the scanner contains no bash-4+ constructs (associative
    arrays, ${var,,}/${var^^} case conversion, mapfile/readarray) and no \\b
    (or other GNU-only regex escapes) inside [[ =~ ]] patterns — the
    portability gate for macOS bash 3.2 + BSD regcomp."""
    print("\n[task_022 AC7a: no bash-4+ constructs, no \\b escapes]")
    src = VIBE_CONTENT_SCANNER.read_text(encoding="utf-8")
    check("[task_022 AC7a] no literal \\b anywhere in the scanner", "\\b" not in src, "")
    check("[task_022 AC7a] no declare -A (associative arrays)", "declare -A" not in src, "")
    check("[task_022 AC7a] no mapfile", "mapfile" not in src, "")
    check("[task_022 AC7a] no readarray", "readarray" not in src, "")
    case_conv = re.search(r'\$\{[^}]*(,,|\^\^)[^}]*\}', src)
    check("[task_022 AC7a] no ${var,,} / ${var^^} case-conversion expansion",
          case_conv is None, str(case_conv))


def test_task022_ac7_no_perline_forks_in_hot_path_functions() -> None:
    """AC7(b), A2c: the five named hot-path functions' bodies (extracted per
    the spec's pinned method: '^name() {' to the first subsequent '^}')
    contain no external-command invocation of grep/sed/awk/head/cut/tr in any
    form (piped, command-substituted, herestring/heredoc-fed, or bare), and
    no $( or backtick command substitution at all. line_is_allowlisted is
    exempt (A3: it keeps grep -qE, off the hot path). This is the permanent
    guard against the fork-storm quietly reappearing."""
    print("\n[task_022 AC7b: no per-line subprocess forks in hot-path functions]")
    src = VIBE_CONTENT_SCANNER.read_text(encoding="utf-8")
    forbidden_names = ["grep", "sed", "awk", "head", "cut", "tr"]
    hot_path_funcs = [
        "check_rule", "check_email_rule", "check_home_path_rule",
        "is_named_trailer", "is_trailer_line",
    ]
    for name in hot_path_funcs:
        body = _task022_extract_function_body(src, name)
        bad = [n for n in forbidden_names if re.search(r'\b' + n + r'\b', body)]
        check(f"[task_022 AC7b] {name}: no forbidden external-command names", bad == [], str(bad))
        check(f"[task_022 AC7b] {name}: no $( command substitution", "$(" not in body, body)
        check(f"[task_022 AC7b] {name}: no backtick command substitution", "`" not in body, body)

    # line_is_allowlisted is the documented exemption (A3) — confirm it still
    # legitimately uses grep -qE, proving the check above is discriminating
    # and not just accidentally silent everywhere.
    allow_body = _task022_extract_function_body(src, "line_is_allowlisted")
    check("[task_022 AC7b] line_is_allowlisted still uses grep -qE (A3 exemption intact)",
          "grep -qE" in allow_body, allow_body)


def test_task023_ac1_ere_allowlist_regression_with_pathwarn_lines_interspersed() -> None:
    """AC1: every non-path-warn allowlist line keeps exact whole-line ERE
    suppression semantics even when path-warn: lines (including a malformed
    whitespace-only one) are interspersed in the same file — the parser
    split must not disturb the pre-existing ERE loop for ordinary entries.
    Converse: with ONLY a path-warn:* entry present (no ERE entry at all),
    --message (no file path) is completely unaffected — proving path-warn
    entries are structurally invisible to the ERE loop in both directions."""
    print("\n[task_023 AC1: ERE regression corpus with path-warn lines interspersed]")
    ip = _t23_ip()
    with tempfile.TemporaryDirectory() as td:
        allow = Path(td) / ".vibe-content-allow"
        allow.write_text(
            "# a comment\n"
            "\n"
            "path-warn:some/other/glob/*\n"
            + ip.replace(".", r"\.") + "\n"
            "path-warn:  \n"
        )
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text(f"Server ip {ip} today\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_023 AC1] ERE entry still suppresses despite interspersed path-warn lines",
              r.returncode == 0 and len(r.stderr.strip()) == 0, r.stderr)

    with tempfile.TemporaryDirectory() as td:
        allow = Path(td) / ".vibe-content-allow"
        allow.write_text("path-warn:*\n")
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text(f"Server ip {ip} today\n")
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_023 AC1] path-warn entries have zero effect on --message (ERE loop only sees ERE lines)",
              r.returncode == 1 and "rfc1918-ip" in r.stderr, r.stderr)


def test_task023_ac1_pathwarn_prefix_whitespace_tolerant() -> None:
    """AC1: path-warn:<glob> is recognised with arbitrary internal
    whitespace after the prefix (leading/trailing trimmed off the glob
    before the case-pattern match)."""
    print("\n[task_023 AC1: path-warn prefix whitespace tolerance]")
    ip = _t23_ip_alt()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:   fixtures/*   \n")
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "f.txt").write_text(f"Server ip {ip} today\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC1] whitespace-padded glob still suppresses WARN",
              r.returncode == 0 and len(r.stderr.strip()) == 0, r.stderr)


def test_task023_ac2_staged_suppression_matching_vs_nonmatching() -> None:
    """AC2: all four WARN-class categories (RFC1918 IP, non-noreply email,
    /Users|home/<name>/ path, mdns .local hostname) in a path-warn-matched
    file produce NO finding under --staged; the identical content in a
    non-matching file in the SAME commit still produces the normal WARN
    findings and exit 1."""
    print("\n[task_023 AC2: staged suppression — all 4 WARN categories, matching vs non-matching]")
    ip = _t23_ip()
    email = _t23_email()
    mdns = _t23_mdns()
    homepath_line = _t23_homepath_line()
    content = (
        f"Server ip {ip} today\n"
        f"Contact {email} please\n"
        f"{homepath_line}\n"
        f"Host {mdns} is up\n"
    )
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:fixtures/*\n")
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "warn.txt").write_text(content)
        (repo / "other.txt").write_text(content)
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_023 AC2] exit 1 (non-matching file still WARNs)", r.returncode == 1, r.stderr)
        check("[task_023 AC2] no finding located in fixtures/warn.txt",
              all(not f[1].startswith("fixtures/warn.txt:") for f in findings), str(findings))
        other_rules = {f[2] for f in findings if f[1].startswith("other.txt:")}
        check("[task_023 AC2] other.txt still fires all 4 WARN rules",
              other_rules == {"rfc1918-ip", "email-address", "home-path", "mdns-local"},
              str(other_rules))


def test_task023_ac2_nested_path_glob_crosses_slash() -> None:
    """AC2: `*` in a path-warn glob crosses `/` — path-warn:.vs/* must
    suppress a WARN 3 levels deep under .vs/, catching a quoted-glob
    implementation (which would silently kill the feature)."""
    print("\n[task_023 AC2: nested-path glob (3 levels deep)]")
    email = _t23_email()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:.vs/*\n")
        nested = repo / ".vs" / "archive" / "task_099" / "critiques"
        nested.mkdir(parents=True)
        (nested / "foo.md").write_text(f"Contact {email} for details\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC2] 3-level nested path suppressed: exit 0", r.returncode == 0, r.stderr)
        check("[task_023 AC2] 3-level nested path suppressed: no findings", len(r.stderr.strip()) == 0, r.stderr)


def test_task023_ac2_empty_glob_no_crash_no_matchall() -> None:
    """AC2: `path-warn:` with an empty/whitespace-only glob is malformed —
    skipped, matches nothing (never treated as match-all across the whole
    repo)."""
    print("\n[task_023 AC2: empty-glob path-warn line is inert]")
    ip = _t23_ip_alt()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:\npath-warn:   \n")
        (repo / "anything.txt").write_text(f"Server ip {ip} today\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC2] empty-glob does not crash: exit 1 (still WARNs)", r.returncode == 1, r.stderr)
        check("[task_023 AC2] empty-glob is not match-all", "rfc1918-ip" in r.stderr, r.stderr)


def test_task023_ac3_block_fires_staged_under_pathwarn() -> None:
    """AC3: a runtime-built BLOCK secret added to a path-warn-matched file
    in --staged still produces the BLOCK finding + exit 1 — path never
    suppresses a secret."""
    print("\n[task_023 AC3: BLOCK still fires under path-warn — staged]")
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:fixtures/*\n")
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "secret.txt").write_text(f"leaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC3 staged] exit 1", r.returncode == 1, r.stderr)
        check("[task_023 AC3 staged] BLOCK finding present", "BLOCK" in r.stderr, r.stderr)
        check("[task_023 AC3 staged] github-pat rule named", "github-pat" in r.stderr, r.stderr)
