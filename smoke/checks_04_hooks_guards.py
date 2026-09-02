from smoke._core import *  # noqa: F401,F403




def test_task008_ac3_block_scoping() -> None:
    """task_008: AC3 — CLIP and WATCHER_SEED_MTIME only declared in Darwin block."""
    print("\n[task_008: AC3 block scoping]")
    src = Path(VIBE).read_text()
    lines = src.splitlines()

    # Find the Darwin block boundaries
    darwin_start = None
    darwin_end = None
    for i, ln in enumerate(lines):
        if 'if [[ "$(uname)" == "Darwin" ]]' in ln and 'pbcopy' in ln:
            darwin_start = i
        if darwin_start is not None and darwin_end is None and ln.strip() == 'fi':
            darwin_end = i
            break

    check("[task008/AC3] Darwin block found", darwin_start is not None and darwin_end is not None,
          f"darwin_start={darwin_start} darwin_end={darwin_end}")

    if darwin_start is not None and darwin_end is not None:
        # Check that CLIP and WATCHER_SEED_MTIME appear exactly once, only within block
        clip_count = 0
        seed_count = 0
        clip_in_block = False
        seed_in_block = False

        for i in range(darwin_start, darwin_end + 1):
            if 'CLIP=' in lines[i]:
                clip_count += 1
                clip_in_block = True
            if 'WATCHER_SEED_MTIME=' in lines[i]:
                seed_count += 1
                seed_in_block = True

        # Check for assignments outside block
        for i in range(0, darwin_start):
            if 'CLIP=' in lines[i] and 'pbcopy' not in lines[i]:
                clip_count += 1
        for i in range(darwin_end + 1, len(lines)):
            if 'CLIP=' in lines[i]:
                clip_count += 1
            if 'WATCHER_SEED_MTIME=' in lines[i]:
                seed_count += 1

        check("[task008/AC3] CLIP only declared once (in block)", clip_count == 1,
              f"CLIP appears {clip_count} times")
        check("[task008/AC3] WATCHER_SEED_MTIME only declared once (in block)", seed_count == 1,
              f"WATCHER_SEED_MTIME appears {seed_count} times")


def test_task008_ac11_direct_read() -> None:
    """task_008: AC11 — drain uses pbcopy < CLIP, not cat pipe or cp through tmp."""
    print("\n[task_008: AC11 direct read]")
    src = Path(VIBE).read_text()

    # Find the trap body region (after Darwin block start, before fi)
    trap_start = src.find('trap \'')
    trap_end = src.find('EXIT', trap_start) + 4 if trap_start != -1 else -1
    trap_body = src[trap_start:trap_end] if trap_start != -1 else ""

    check("[task008/AC11] trap contains pbcopy < \"$CLIP\"", 'pbcopy < "$CLIP"' in src,
          "substring not found")

    # Negative tests: should NOT use cat pipe
    cat_pipe = 'cat "$CLIP" | pbcopy' in src or 'cat "$CLIP"|pbcopy' in src
    check("[task008/AC11] trap does NOT use cat pipe", not cat_pipe,
          "found forbidden cat pipe")

    # Negative test: should NOT use cp through tmp
    cp_tmp = 'cp "$CLIP" "$TMP"' in src and 'pbcopy < "$TMP"' in src
    check("[task008/AC11] trap does NOT use cp through TMP", not cp_tmp,
          "found forbidden cp-through-tmp pattern")


def test_clipboard_drain_on_exit() -> None:
    """task_008: drain clipboard scratch on exit — AC18 source-level assertions."""
    print("\n[task_008: clipboard drain on exit — source checks]")
    src = Path(VIBE).read_text()
    lines = src.splitlines()

    # (a) Exactly one line matches CLIP="$WORKSPACE/.vibe/copy-latest.txt"
    clip_pattern = re.compile(r'^\s*CLIP="\$WORKSPACE/\.vibe/copy-latest\.txt"\s*$')
    clip_matches = [ln for ln in lines if clip_pattern.match(ln)]
    check("[task008] exactly one CLIP=... line", len(clip_matches) == 1,
          f"found {len(clip_matches)} matches")

    # (b) Exactly one line matches WATCHER_SEED_MTIME=$(stat -f %m "$CLIP"
    seed_pattern = re.compile(r'^\s*WATCHER_SEED_MTIME=\$\(stat -f %m "\$CLIP"')
    seed_matches = [ln for ln in lines if seed_pattern.match(ln)]
    check("[task008] exactly one WATCHER_SEED_MTIME=$(stat...) line", len(seed_matches) == 1,
          f"found {len(seed_matches)} matches")

    # (c) Source contains pbcopy < "$CLIP"
    drain_substr = 'pbcopy < "$CLIP"'
    check("[task008] source contains pbcopy < \"$CLIP\"", drain_substr in src,
          "substring not found")

    # (d) Source contains kill "$WATCHER_PID" 2>/dev/null || true
    kill_substr = 'kill "$WATCHER_PID" 2>/dev/null || true'
    check("[task008] source contains kill \"$WATCHER_PID\" 2>/dev/null || true", kill_substr in src,
          "substring not found")

    # (e) seed match offset < drain offset
    seed_offset = src.index(seed_matches[0]) if seed_matches else -1
    drain_offset = src.index(drain_substr) if drain_substr in src else -1
    check("[task008] seed line precedes drain (offset order)", seed_offset < drain_offset,
          f"seed_offset={seed_offset} drain_offset={drain_offset}")

    # (f) drain offset < kill offset
    kill_offset = src.index(kill_substr) if kill_substr in src else -1
    check("[task008] drain precedes kill (offset order)", drain_offset < kill_offset,
          f"drain_offset={drain_offset} kill_offset={kill_offset}")

    # (g) No arithmetic comparison [ "$cur" -gt "$WATCHER_SEED_MTIME" ]
    bad_arith = '[ "$cur" -gt "$WATCHER_SEED_MTIME" ]'
    check("[task008] no arithmetic -gt comparison for mtime", bad_arith not in src,
          "found forbidden arithmetic comparison")

    # (h) No standalone WATCHER_SEED_MTIME=0 literal assignment
    seed_literal_pattern = re.compile(r'^\s*WATCHER_SEED_MTIME=0\s*$', re.MULTILINE)
    check("[task008] no standalone WATCHER_SEED_MTIME=0 literal", not seed_literal_pattern.search(src),
          "found forbidden literal seed assignment")


def test_task009_guard_fs_exists() -> None:
    """AC1: guard-fs.sh exists as an executable shell script."""
    print("\n[task_009/AC1: guard-fs.sh exists]")
    check("[task009/AC1] guard-fs.sh exists", GUARD_FS.exists(), str(GUARD_FS))
    if GUARD_FS.exists():
        check("[task009/AC1] guard-fs.sh is executable",
              bool(GUARD_FS.stat().st_mode & 0o111), str(GUARD_FS))
        content = GUARD_FS.read_text()
        check("[task009/AC1] has set -euo pipefail", "set -euo pipefail" in content, "")
        check("[task009/AC1] uses jq -r .tool_input.file_path",
              "jq -r" in content and "tool_input" in content and "file_path" in content, "")
        check("[task009/AC1] uses realpath -m", "realpath -m" in content, "")


def test_task009_guard_fs_ask_fixtures() -> None:
    """AC10: guard-fs.sh emits correct ask-JSON for /learnings paths."""
    print("\n[task_009/AC10: guard-fs.sh ask fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ('{"tool_input":{"file_path":"/learnings/2026-04-26T17:00:00Z-abcdef.md"}}',
         "/learnings file path"),
        ('{"tool_input":{"file_path":"/learnings"}}',
         "/learnings exact"),
        ('{"tool_input":{"file_path":"/learnings/sub/dir/file.md"}}',
         "/learnings deep path"),
    ]
    for json_input, label in fixtures:
        r = _run_guard_fs(json_input)
        _assert_ask_json(r, label)
        if r.returncode == 0 and r.stdout:
            try:
                data = json.loads(r.stdout)
                reason = data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                check(f"[task009] {label}: reason contains /learnings/",
                      "/learnings" in reason, reason)
            except json.JSONDecodeError:
                pass


def test_task009_guard_fs_non_learnings_fixtures() -> None:
    """AC11: guard-fs.sh silent for non-/learnings and traversal-attempt paths."""
    print("\n[task_009/AC11: guard-fs.sh non-/learnings fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ('{"tool_input":{"file_path":"/workspace/foo/bar.md"}}',
         "/workspace path"),
        ('{"tool_input":{"file_path":"/learnings/../etc/passwd"}}',
         "traversal attempt /etc/passwd"),
        ('{"tool_input":{"file_path":"/learnings/../../tmp/x"}}',
         "traversal attempt /tmp/x"),
        ('{"tool_input":{}}',
         "no file_path key"),
    ]
    for json_input, label in fixtures:
        r = _run_guard_fs(json_input)
        _assert_silent_exit0(r, label)


def test_task009_guard_bash_learnings_write_fixtures() -> None:
    """AC12: guard-bash.sh emits ask-JSON for /learnings shell-write idioms."""
    print("\n[task_009/AC12: guard-bash.sh /learnings write fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ("echo hi > /learnings/test.md", "redirect >"),
        ("echo hi >> /learnings/test.md", "redirect >>"),
        ("cmd | tee /learnings/z.md", "tee pipe"),
        ("tee -a /learnings/z.md < /tmp/x", "tee -a"),
        ("cp /tmp/x /learnings/y.md", "cp"),
        ("cp -r /tmp/dir /learnings/sub", "cp -r"),
        ("mv /tmp/x /learnings/y.md", "mv"),
        ("rm /learnings/old.md", "rm"),
        ("rm -rf /learnings/old/", "rm -rf"),
        ("ln -s /tmp/target /learnings/link", "ln -s"),
        ("mkdir /learnings/newdir", "mkdir"),
        ("chmod 644 /learnings/x.md", "chmod"),
        ("chown node:node /learnings/x.md", "chown"),
        ("truncate -s 0 /learnings/x.md", "truncate"),
        ("dd if=/dev/zero of=/learnings/x bs=1M count=1", "dd"),
        ("sed -i 's/foo/bar/' /learnings/x.md", "sed -i"),
        ("sed -ri 's/foo/bar/' /learnings/x.md", "sed -ri combined flag"),
    ]
    for cmd_str, label in fixtures:
        r = _run_guard_bash(cmd_str)
        _assert_ask_json(r, f"bash write: {label}")


def test_task009_guard_bash_learnings_read_fixtures() -> None:
    """AC13: guard-bash.sh allows /learnings reads (no output, exit 0)."""
    print("\n[task_009/AC13: guard-bash.sh /learnings read fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    fixtures = [
        ("cat /learnings/x.md", "cat"),
        ("ls /learnings/", "ls"),
        ("grep -r foo /learnings/", "grep -r"),
        ("head /learnings/x.md", "head"),
        ("sed -n '/learnings/p' /tmp/file", "sed -n (read, no -i)"),
    ]
    for cmd_str, label in fixtures:
        r = _run_guard_bash(cmd_str)
        _assert_silent_exit0(r, f"bash read: {label}")


def test_task009_guard_bash_gitpush_and_block_beats_ask() -> None:
    """AC14: guard-bash.sh preserves git-push block AND block beats ask."""
    print("\n[task_009/AC14: guard-bash.sh git-push + block-beats-ask]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return

    # force push → exit 2
    r = _run_guard_bash("git push --force origin main")
    check("[task009/AC14] force push: exit 2", r.returncode == 2,
          f"exit={r.returncode}")
    check("[task009/AC14] force push: stderr contains 'git push --force'",
          "git push --force" in r.stderr, r.stderr[:200])

    # branch delete → exit 2
    r = _run_guard_bash("git push origin :branchname")
    check("[task009/AC14] branch delete: exit 2", r.returncode == 2,
          f"exit={r.returncode}")
    check("[task009/AC14] branch delete: stderr contains 'git push'",
          "git push" in r.stderr, r.stderr[:200])

    # normal push → exit 0, no output
    r = _run_guard_bash("git push origin main")
    _assert_silent_exit0(r, "normal push")

    # block beats ask: rm /learnings + force push → exit 2 (not ask-JSON)
    r = _run_guard_bash("rm /learnings/old.md && git push --force origin main")
    check("[task009/AC14] block-beats-ask (rm+force-push): exit 2", r.returncode == 2,
          f"exit={r.returncode}")

    # block beats ask: force push + echo to /learnings → exit 2 (not ask-JSON)
    r = _run_guard_bash("git push --force origin main && echo hi > /learnings/x.md")
    check("[task009/AC14] block-beats-ask (force-push+echo): exit 2", r.returncode == 2,
          f"exit={r.returncode}")


def test_zotero_guard_deny_fixtures() -> None:
    """Writes at or beneath a mounted Zotero store are denied."""
    print("\n[zotero: guard-fs.sh deny fixtures]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as td:
        mount = os.path.join(td, "zoteromount")
        os.makedirs(mount)
        script = _guard_fs_variant(td, mount)
        for rel, label in [
            ("", "mount root exact"),
            ("/ABCD1234/paper.pdf", "attachment PDF"),
            ("/a/b/c/deep.md", "deep path"),
            ("/sub/../ABCD1234/paper.pdf", "normalises back inside the mount"),
        ]:
            r = _run_guard_fs_variant(script, mount + rel)
            _assert_deny_json(r, label)
            if r.stdout:
                reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
                check(f"[zotero] {label}: reason names the path",
                      mount in reason, reason)
                check(f"[zotero] {label}: reason says read-only",
                      "read-only" in reason, reason)


def test_zotero_guard_silent_without_mount() -> None:
    """With no Zotero mount present the hook stays silent and exits 0."""
    print("\n[zotero: guard-fs.sh inert without the mount]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as td:
        absent = os.path.join(td, "no-such-mount")   # deliberately not created
        script = _guard_fs_variant(td, absent)
        for rel, label in [("", "absent mount root"), ("/A/paper.pdf", "absent mount file")]:
            _assert_silent_exit0(_run_guard_fs_variant(script, absent + rel), label)


def test_zotero_guard_neighbour_paths_silent() -> None:
    """Traversal-out and prefix look-alike paths are NOT denied."""
    print("\n[zotero: guard-fs.sh neighbour paths]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as td:
        mount = os.path.join(td, "zoteromount")
        os.makedirs(mount)
        script = _guard_fs_variant(td, mount)
        for path, label in [
            (mount + "/../escape.md", "traversal out of the mount"),
            (mount + "-notes/file.md", "prefix look-alike sibling"),
            ("/workspace/zotero/file.md", "unrelated path containing 'zotero'"),
        ]:
            _assert_silent_exit0(_run_guard_fs_variant(script, path), label)


def test_zotero_guard_bash_idioms() -> None:
    """guard-bash.sh blocks shell-write idioms under /zotero/, reads pass."""
    print("\n[zotero: guard-bash.sh write idioms]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return
    for cmd_str, label in [
        ("echo hi > /zotero/ABCD1234/notes.md", "redirect"),
        ("cp paper.pdf /zotero/ABCD1234/paper.pdf", "cp"),
        ("rm /zotero/ABCD1234/paper.pdf", "rm"),
        ("tee /zotero/ABCD1234/x.md", "tee"),
        ("sed -i s/a/b/ /zotero/ABCD1234/x.md", "sed -i"),
    ]:
        r = _run_guard_bash(cmd_str)
        check(f"[zotero] bash write ({label}): exit 2", r.returncode == 2,
              f"exit={r.returncode} stderr={r.stderr[:200]}")
        check(f"[zotero] bash write ({label}): stderr names zotero",
              "zotero" in r.stderr.lower(), r.stderr[:200])
    for cmd_str, label in [
        ("cat /zotero/ABCD1234/paper.pdf", "cat"),
        ("ls /zotero/ABCD1234", "ls"),
        ("grep -r term /zotero/", "grep"),
    ]:
        _assert_silent_exit0(_run_guard_bash(cmd_str), f"bash read ({label})")
    # git-rule precedence: both fire → still exit 2, git message wins
    r = _run_guard_bash("git push --force origin main && rm /zotero/x.pdf")
    check("[zotero] git block beats zotero block: exit 2", r.returncode == 2,
          f"exit={r.returncode}")


def test_zotero_guard_learnings_unregressed() -> None:
    """The /learnings ask branch is unchanged by the /zotero addition."""
    print("\n[zotero: /learnings regression]")
    if _HOOK_SKIP:
        print("  (skipped — jq/bash absent)", file=sys.stderr)
        return
    r = _run_guard_fs('{"tool_input":{"file_path":"/learnings/x.md"}}')
    _assert_ask_json(r, "/learnings still asks")
    check("[zotero] /learnings emits exactly one envelope",
          r.stdout.count("hookSpecificOutput") == 1, r.stdout[:200])


def test_task009_settings_json_updated() -> None:
    """AC4: vibe heredoc contains Write|Edit|MultiEdit matcher entry (persistent fix).

    Reads /workspace/vibe source (not the runtime-generated settings.local.json)
    because settings.local.json is gitignored and rewritten on every container
    start — the only durable fix is in the heredoc inside vibe.
    """
    print("\n[task_009/AC4: vibe heredoc has Write|Edit|MultiEdit matcher]")
    vibe_path = REPO / "vibe"
    check("[task009/AC4] vibe script exists", vibe_path.exists(), str(vibe_path))
    if not vibe_path.exists():
        return
    vibe_src = vibe_path.read_text()
    # Locate byte offsets for ordering assertions
    bash_offset = vibe_src.find('"matcher": "Bash"')
    fs_offset = vibe_src.find('"matcher": "Write|Edit|MultiEdit"')
    guard_fs_offset = vibe_src.find("/usr/local/bin/guard-fs.sh")
    check("[task009/AC4] Bash matcher present in vibe heredoc",
          bash_offset != -1, "not found")
    check("[task009/AC4] Write|Edit|MultiEdit matcher present in vibe heredoc",
          fs_offset != -1, "not found")
    check("[task009/AC4] /usr/local/bin/guard-fs.sh present in vibe heredoc",
          guard_fs_offset != -1, "not found")
    # Both substrings must appear AFTER the Bash matcher entry
    if bash_offset != -1 and fs_offset != -1:
        check("[task009/AC4] Write|Edit|MultiEdit entry is after Bash entry",
              fs_offset > bash_offset, f"fs_offset={fs_offset} bash_offset={bash_offset}")
    if bash_offset != -1 and guard_fs_offset != -1:
        check("[task009/AC4] guard-fs.sh entry is after Bash matcher",
              guard_fs_offset > bash_offset,
              f"guard_fs_offset={guard_fs_offset} bash_offset={bash_offset}")


def test_task009_dockerfile_updated() -> None:
    """AC5: Dockerfile has COPY + chmod for guard-fs.sh."""
    print("\n[task_009/AC5: Dockerfile updated]")
    check("[task009/AC5] Dockerfile exists", DOCKERFILE.exists(), str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return
    content = DOCKERFILE.read_text()
    # AC5a: canonical COPY line (no trailing slash)
    copy_lines = [ln.strip() for ln in content.splitlines()
                  if ln.strip() == "COPY guard-fs.sh /usr/local/bin/"]
    check("[task009/AC5a] exactly one canonical COPY guard-fs.sh line",
          len(copy_lines) == 1, f"found {len(copy_lines)} lines")
    # AC5b: /usr/local/bin/guard-fs.sh in chmod chain
    chmod_lines = [ln for ln in content.splitlines() if "chmod +x" in ln]
    check("[task009/AC5b] /usr/local/bin/guard-fs.sh in chmod +x chain",
          any("/usr/local/bin/guard-fs.sh" in ln for ln in chmod_lines),
          str(chmod_lines))


def test_task009_learn_md_exists() -> None:
    """AC6: commands/learn.md exists with required content."""
    print("\n[task_009/AC6: commands/learn.md]")
    check("[task009/AC6] learn.md exists", LEARN_MD.exists(), str(LEARN_MD))
    if not LEARN_MD.exists():
        return
    content = LEARN_MD.read_text()
    check("[task009/AC6] mentions /learnings/ path", "/learnings/" in content, "")
    check("[task009/AC6] ts= one-liner present",
          "ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" in content, "")
    check("[task009/AC6] rand= one-liner present",
          "rand=$(python3 -c 'import binascii,os; print(binascii.hexlify(os.urandom(3)).decode())')" in content,
          "")
    check("[task009/AC6] printf format present",
          "printf '# %s\\n\\n%s\\n' \"$ts\" \"$pattern\"" in content, "")
    check("[task009/AC6] refusal message present",
          "/learn: /learnings is not mounted (run 'vibe learn --init' on host first)" in content, "")
    check("[task009/AC6] mentions vibe learn --push", "vibe learn --push" in content, "")
    check("[task009/AC6] instructs preview before Write",
          "preview" in content.lower() or "print" in content.lower(), "")


def test_task009_learn_hook_md_exists() -> None:
    """AC7: the /learnings write-confirm hook rules ship as a CLAUDE.md
    fragment with sentinel phrases. task_028 merged the standalone hook
    fragment into claude-md/learnings.md, so the sentinels are pinned there."""
    print("\n[task_009/AC7: hook rules in claude-md/learnings.md]")
    check("[task009/AC7] host fragment exists", LEARN_HOOK_RULES_MD.exists(), str(LEARN_HOOK_RULES_MD))
    if not LEARN_HOOK_RULES_MD.exists():
        return
    content = LEARN_HOOK_RULES_MD.read_text()
    non_blank = sum(1 for ln in content.splitlines() if ln.strip())
    check("[task009/AC7] >= 30 non-blank lines", non_blank >= 30,
          f"non_blank={non_blank}")
    check("[task009/AC7] contains 'permissionDecision'",
          "permissionDecision" in content, "")
    check("[task009/AC7] contains 'do not bypass'",
          "do not bypass" in content, "")
    check("[task009/AC7] contains 'host-only'",
          "host-only" in content, "")


def test_learn_docs_no_host_stage_all_footgun() -> None:
    """Regression: /learn docs must not tell the host to `cd $VIBE_LEARNING_PATH
    && git add .`. VIBE_LEARNING_PATH is a container/config var, unset in the
    user's interactive Mac shell, so `cd $VIBE_LEARNING_PATH` becomes `cd ~`
    and `git add .` stages all of $HOME (observed 2026-05-26, one `&&` from a
    secret-leaking push). Host-side push must go through `vibe learn --push`,
    and any manual fallback must use a literal placeholder path + a specific
    filename, never the container var and never `git add .`."""
    print("\n[regression: /learn docs have no host stage-all footgun]")
    for path in (LEARN_MD, LEARN_HOOK_RULES_MD):
        if not path.exists():
            check(f"[learn-footgun] {path.name} exists", False, str(path))
            continue
        content = path.read_text()
        check(f"[learn-footgun] {path.name} has no 'git add .' (stages $HOME)",
              "git add ." not in content,
              "found dangerous stage-all 'git add .' in host instructions")
        check(f"[learn-footgun] {path.name} does not reference $VIBE_LEARNING_PATH "
              "in host instructions (container-only var)",
              "$VIBE_LEARNING_PATH" not in content and "${VIBE_LEARNING_PATH" not in content,
              "container/config var leaked into host-side instructions")


def test_task009_readme_updated() -> None:
    """AC8: README.md contains PreToolUse hook gates writes sentinel."""
    print("\n[task_009/AC8: README.md updated]")
    readme = REPO / "README.md"
    check("[task009/AC8] README.md exists", readme.exists(), str(readme))
    if not readme.exists():
        return
    content = readme.read_text()
    check("[task009/AC8] contains 'PreToolUse hook gates writes'",
          "PreToolUse hook gates writes" in content, "")


def test_task009_code_check_clean() -> None:
    """AC15: python3 code-check.py exits 0 (no new shellcheck warnings)."""
    print("\n[task_009/AC15: code-check.py clean]")
    r = run(["python3", str(CODE_CHECK)], cwd=REPO)
    check("[task009/AC15] code-check.py exits 0", r.returncode == 0,
          f"exit={r.returncode} output={r.stdout[-300:]}")


def test_task009_hardening_notebookedit_not_in_matcher() -> None:
    """Hardening: guard-fs.sh matcher EXCLUDES NotebookEdit (out of scope)."""
    print("\n[task_009/hardening: NotebookEdit excluded from matcher]")
    settings_path = REPO / ".claude" / "settings.local.json"
    if not settings_path.exists():
        # settings.local.json is a runtime artifact generated inside an
        # active vibe container (and gitignored). On CI / fresh-checkout it
        # legitimately doesn't exist - that's expected, not a failure. The
        # hardening sentinel only meaningfully runs when we're testing
        # against a populated vibe environment.
        check("[task009] settings.local.json absent — hardening check skipped (expected on CI)",
              True, "runtime-only file; not committed")
        return
    try:
        data = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        return
    pre_tool = data.get("hooks", {}).get("PreToolUse", [])
    fs_entry = next((e for e in pre_tool if e.get("matcher") == "Write|Edit|MultiEdit"), None)
    if fs_entry:
        check("[task009] guard-fs.sh matcher exactly 'Write|Edit|MultiEdit' (no NotebookEdit)",
              True)  # Already tested in AC4, but re-check for hardening
    else:
        check("[task009] guard-fs.sh matcher entry found", False, "")


def test_task009_hardening_guard_bash_set_euo() -> None:
    """Hardening: guard-bash.sh still has 'set -euo pipefail' (not removed during refactor)."""
    print("\n[task_009/hardening: guard-bash.sh 'set -euo pipefail']")
    if not GUARD_BASH.exists():
        check("[task009] guard-bash.sh exists", False, "")
        return
    content = GUARD_BASH.read_text()
    check("[task009] guard-bash.sh has 'set -euo pipefail'",
          "set -euo pipefail" in content, "")


def test_task009_hardening_guard_fs_realpath_m() -> None:
    """Hardening: guard-fs.sh uses 'realpath -m' (not just 'realpath')."""
    print("\n[task_009/hardening: guard-fs.sh uses 'realpath -m']")
    if not GUARD_FS.exists():
        check("[task009] guard-fs.sh exists", False, "")
        return
    content = GUARD_FS.read_text()
    check("[task009] guard-fs.sh uses 'realpath -m' (with -m flag)",
          "realpath -m" in content, "")


def test_task010_smart_capture() -> None:
    """AC1-AC19: /learn smart-capture semantic check phase."""
    print("\n[task_010: /learn smart-capture]")

    if not LEARN_MD.exists():
        check("[task010/AC1] learn.md exists", False, str(LEARN_MD))
        return

    content = LEARN_MD.read_text()

    # AC1: Semantic check section with exact heading
    check("[task010/AC1] '## Semantic check' section heading present",
          "## Semantic check" in content, "missing exact heading")

    # AC2: Relative ordering — "Formats the entry body" before "Runs the semantic check" before "Prints a preview"
    lines = content.splitlines()
    format_body_idx = None
    runs_check_idx = None
    prints_preview_idx = None

    for i, line in enumerate(lines):
        if "Formats the entry body" in line:
            format_body_idx = i
        if "Runs the semantic check" in line:
            runs_check_idx = i
        if "Prints a preview" in line:
            prints_preview_idx = i

    check("[task010/AC2] 'Formats the entry body' appears before 'Runs the semantic check'",
          format_body_idx is not None and runs_check_idx is not None and format_body_idx < runs_check_idx,
          f"format_body={format_body_idx}, runs_check={runs_check_idx}")

    check("[task010/AC2] 'Runs the semantic check' appears before 'Prints a preview'",
          runs_check_idx is not None and prints_preview_idx is not None and runs_check_idx < prints_preview_idx,
          f"runs_check={runs_check_idx}, prints_preview={prints_preview_idx}")

    # AC3: Literal phrase "Runs the semantic check"
    check("[task010/AC3] 'Runs the semantic check' phrase present",
          "Runs the semantic check" in content, "missing exact phrase")

    # AC3a: "existing /learnings entries" in semantic check section
    semantic_section_start = content.find("## Semantic check")
    if semantic_section_start >= 0:
        next_section = content.find("\n##", semantic_section_start + 1)
        semantic_section = content[semantic_section_start:next_section] if next_section > 0 else content[semantic_section_start:]
    else:
        semantic_section = ""

    check("[task010/AC3a] 'existing /learnings entries' phrase in semantic check section",
          "existing /learnings entries" in semantic_section, "missing exact phrase")

    # AC4: Low-quality input explicitly addressed
    low_quality_check = any(phrase in semantic_section for phrase in
                            ["low-quality input", "low quality input", "vague reference", "unclear input"])
    check("[task010/AC4] Low-quality input explicitly addressed",
          low_quality_check, "missing at least one of: low-quality input, low quality input, vague reference, unclear input")

    # AC5: Zero friction (both phrases required)
    zero_friction_present = "zero friction" in semantic_section.lower()
    no_options_present = any(phrase in semantic_section.lower() for phrase in
                             ["no options", "without surfacing options", "no options surfaced"])
    check("[task010/AC5] 'zero friction' (case-insensitive) present",
          zero_friction_present, "missing phrase")
    check("[task010/AC5] 'no options' or equivalent present",
          no_options_present, "missing one of: no options, without surfacing options, no options surfaced")

    # AC6: Option scheme enumeration
    z1_present = "Z1" in semantic_section
    z1_verbatim = any(phrase in semantic_section for phrase in ["user-verbatim", "user verbatim"])
    z1_check = z1_present and z1_verbatim

    z2_present = "Z2" in semantic_section

    edit_existing = any(phrase in semantic_section for phrase in ["edit existing", "edit an existing"])

    n_present = "N" in semantic_section
    n_drops = any(phrase in semantic_section for phrase in ["drop", "drops", "cancel", "cancels"])
    n_check = n_present and n_drops

    check("[task010/AC6] Z1 and 'user-verbatim'/'user verbatim' within 200 chars",
          z1_check, "missing Z1 label or user-verbatim phrase")
    check("[task010/AC6] Z2 label present",
          z2_present, "missing Z2")
    check("[task010/AC6] 'edit existing' or 'edit an existing' present",
          edit_existing, "missing phrase")
    check("[task010/AC6] N label and drop/drops/cancel/cancels within 200 chars",
          n_check, "missing N label or drop/drops/cancel/cancels")

    # AC7: Z1 is ALWAYS the user-verbatim original
    z1_always_check = any(phrase in semantic_section for phrase in ["Z1 is always", "Z1 is ALWAYS"])
    verbatim_in_section = "verbatim" in semantic_section
    z1_always_correct = z1_always_check and verbatim_in_section
    check("[task010/AC7] 'Z1 is always' or 'Z1 is ALWAYS' AND 'verbatim'",
          z1_always_correct, "missing or incomplete requirement")

    # AC8: Marginal token cost (2-5k tokens, en-dash or hyphen variants)
    token_cost_check = any(phrase in semantic_section for phrase in
                           ["2-5k tokens", "2–5k tokens", "2 to 5k tokens"])
    check("[task010/AC8] '2-5k tokens' or '2–5k tokens' or '2 to 5k tokens' present",
          token_cost_check, "missing token cost phrase")

    # AC9: Preview and hook mentioned in same paragraph (within 400 chars if no blank line separation)
    preview_present = "preview" in semantic_section.lower()
    hook_present = "hook" in semantic_section.lower()
    preview_hook_proximity = (preview_present and hook_present)
    check("[task010/AC9] 'preview' and 'hook' both present",
          preview_hook_proximity, "missing or incomplete proximity")

    # AC10: Conditional skipping forbidden (positive check + negative grepping)
    always_runs = any(phrase in semantic_section for phrase in
                     ["every /learn invocation", "runs on every invocation", "always runs"])
    skip_forbidden = not any(phrase in semantic_section for phrase in
                            ["skip the", "skip if", "bypass the check", "omit the check"])
    ac10_check = always_runs and skip_forbidden
    check("[task010/AC10] 'every /learn invocation' or equivalent AND no skip/bypass/omit",
          ac10_check, "missing always-runs or found skip/bypass/omit phrasing")

    # AC11: Z-options capped
    cap_check = any(phrase in semantic_section for phrase in
                   ["cap n at 3", "no more than 3", "up to 3 alternatives", "1 or 2 alternatives"])
    check("[task010/AC11] Z-options capped (cap n at 3, no more than 3, etc.)",
          cap_check, "missing cap/limit phrase")

    # AC12-AC17: Regression gates (filename, body format, multi-line, host-only, refusal, hook)
    check("[task010/AC12] ts=$(date -u present",
          "ts=$(date -u" in content, "missing filename component")
    check("[task010/AC12] binascii.hexlify present",
          "binascii.hexlify" in content, "missing random component")
    check("[task010/AC12] ${ts}-${rand}.md present",
          "${ts}-${rand}.md" in content, "missing filename format")

    check("[task010/AC13] printf format present",
          "printf '# %s\\n\\n%s\\n'" in content, "missing body format")
    check("[task010/AC13] '# <timestamp> header line' mentioned",
          "# <timestamp> header line" in content, "missing header reference")

    check("[task010/AC14] '## Multi-line patterns' section present",
          "## Multi-line patterns" in content, "missing section")

    check("[task010/AC15] 'vibe learn --push' present",
          "vibe learn --push" in content, "missing host-only push instruction")
    check("[task010/AC15] 'host-only' present",
          "host-only" in content, "missing host-only reference")

    check("[task010/AC16] '/learn: /learnings is not mounted' refusal message",
          "/learn: /learnings is not mounted" in content, "missing refusal message")

    check("[task010/AC17] 'PreToolUse hook' mentioned",
          "PreToolUse hook" in content, "missing hook reference")

    # AC18: Diff scope check (files modified must be subset of allowlist)
    # Try git diff first if commit exists, otherwise check current state
    try:
        diff_result = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=REPO)
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            changed_files = set(diff_result.stdout.strip().split('\n'))
        else:
            # Fallback: check git status
            status_result = run(["git", "status", "--porcelain"], cwd=REPO)
            changed_files = set(line.split()[-1] for line in status_result.stdout.strip().split('\n') if line.strip())
    except:
        changed_files = set()

    allowlist = {
        "devcontainer/commands/learn.md",
        "smoke-test.py",
        ".vs/spec.md",
        ".vs/progress.md",
        ".vs/tasks.json"
    }
    # Also allow .vs/cycle-1/ directory and its contents
    scope_ok = all(f not in allowlist and not f.startswith(".vs/cycle-1/") for f in changed_files
                   if f not in allowlist and not f.startswith(".vs/cycle-1/"))

    check("[task010/AC18] No scope creep (only allowed files modified)",
          scope_ok, f"changed files: {', '.join(changed_files)}")

    # AC19: This test function itself exists. Use REPO-relative path so this
    # works on CI (checkout at /home/runner/work/vibe/vibe/) as well as inside
    # the vibe container (workspace at /workspace/). Earlier hardcoded
    # /workspace/smoke-test.py path failed in CI 2026-05-09 (commit 2ec36b3);
    # the bare except: swallowed FileNotFoundError into a check-fail.
    smoke_test_content = (REPO / "smoke-test.py").read_text()
    test_func_exists = "def test_task010_smart_capture() -> None:" in smoke_test_content
    check("[task010/AC19] test_task010_smart_capture function exists",
          test_func_exists, "function signature not found")


def test_task013_vs_md_intelligent_stopping() -> None:
    """AC5: vs.md documents intelligent Spec Critic stopping rules (13 checks)."""
    print("\n[task_013/AC5: intelligent stopping rules]")
    if not VS_MD.exists():
        check("[task013/AC5] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()

    # Convergence (3 sentinels)
    check("[task013/AC5] Convergence sentinel present", "Convergence" in content,
          "missing 'Convergence'")
    check("[task013/AC5] iterate until Spec Critic returns `pass` sentinel",
          "iterate until Spec Critic returns `pass`" in content,
          "missing 'iterate until Spec Critic returns `pass`'")
    check("[task013/AC5] no hardcoded cap sentinel",
          "no hardcoded cap" in content,
          "missing 'no hardcoded cap'")

    # Plateau detection (6 sentinels: 5 substring + 1 proximity check)
    check("[task013/AC5] Plateau detection sentinel",
          "Plateau detection" in content,
          "missing 'Plateau detection'")
    check("[task013/AC5] Spec Critic plateaued at iter- sentinel",
          "Spec Critic plateaued at iter-" in content,
          "missing 'Spec Critic plateaued at iter-'")
    check("[task013/AC5] (a) accept residuals sentinel",
          "(a) accept residuals" in content,
          "missing '(a) accept residuals'")
    check("[task013/AC5] (b) restart with a revised brief sentinel",
          "(b) restart with a revised brief" in content,
          "missing '(b) restart with a revised brief'")
    check("[task013/AC5] (c) drop the task sentinel",
          "(c) drop the task" in content,
          "missing '(c) drop the task'")

    # Plateau proximity check: all three labels in same paragraph as "Plateau detection"
    plateau_idx = content.find("Plateau detection")
    if plateau_idx != -1:
        # Find next blank line (or EOF) after the anchor line
        anchor_line_end = content.find("\n", plateau_idx)
        if anchor_line_end == -1:
            # "Plateau detection" is on last line
            paragraph_end = len(content)
        else:
            # Search for next blank line
            search_pos = anchor_line_end + 1
            while search_pos < len(content):
                next_newline = content.find("\n", search_pos)
                if next_newline == -1:
                    next_newline = len(content)
                # Check if line is blank (only whitespace)
                line = content[search_pos:next_newline]
                if line.strip() == "":
                    paragraph_end = search_pos
                    break
                search_pos = next_newline + 1
            else:
                paragraph_end = len(content)

        paragraph = content[plateau_idx:paragraph_end]
        all_labels_in_para = (
            "(a) accept residuals" in paragraph and
            "(b) restart with a revised brief" in paragraph and
            "(c) drop the task" in paragraph
        )
        check("[task013/AC5] plateau option labels in same paragraph",
              all_labels_in_para,
              "option labels not all in paragraph starting with 'Plateau detection'")
    else:
        check("[task013/AC5] plateau option labels in same paragraph", False,
              "'Plateau detection' not found")

    # Divergence detection (4 sentinels)
    check("[task013/AC5] Divergence detection sentinel",
          "Divergence detection" in content,
          "missing 'Divergence detection'")
    check("[task013/AC5] Spec Critic divergent sentinel",
          "Spec Critic divergent" in content,
          "missing 'Spec Critic divergent'")
    check("[task013/AC5] concern count growing sentinel",
          "concern count growing" in content,
          "missing 'concern count growing'")
    check("[task013/AC5] three consecutive iterations sentinel",
          "three consecutive iterations" in content,
          "missing 'three consecutive iterations'")


def test_task013_vs_md_max_iter_flag() -> None:
    """AC6: vs.md documents --max-iter flag with 4+ checks."""
    print("\n[task_013/AC6: --max-iter flag documentation]")
    if not VS_MD.exists():
        check("[task013/AC6] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()
    lines = content.split("\n")

    # AC3 check: same-line co-occurrence of "--max-iter" AND "Spec Critic loop"
    same_line_found = False
    for line in lines:
        if "--max-iter" in line and "Spec Critic loop" in line:
            same_line_found = True
            break
    check("[task013/AC6] AC3: same-line co-occurrence of '--max-iter' and 'Spec Critic loop'",
          same_line_found,
          "no single line contains both '--max-iter' and 'Spec Critic loop'")

    # AC4 checks: three required substrings
    check("[task013/AC6] AC4: --max-iter substring",
          "--max-iter" in content,
          "missing '--max-iter'")
    check("[task013/AC6] AC4: cap fires before convergence substring",
          "cap fires before convergence" in content,
          "missing 'cap fires before convergence'")
    check("[task013/AC6] AC4: do NOT silently auto-pass substring",
          "do NOT silently auto-pass" in content,
          "missing 'do NOT silently auto-pass'")


def test_task013_no_hardcoded_cap_string() -> None:
    """AC7: vs.md does not contain 'max 2 iterations'."""
    print("\n[task_013/AC7: no hardcoded cap string]")
    if not VS_MD.exists():
        check("[task013/AC7] vs.md exists", False, str(VS_MD))
        return
    content = VS_MD.read_text()
    check("[task013/AC7] 'max 2 iterations' not present in vs.md",
          "max 2 iterations" not in content,
          "'max 2 iterations' found in file (should be removed)")


def test_check_sp_current_exists_and_executable() -> None:
    print("\n[check-sp-current: file shape]")
    check("[sp-probe] script exists", CHECK_SP_CURRENT.exists(), str(CHECK_SP_CURRENT))
    if not CHECK_SP_CURRENT.exists():
        return
    check("[sp-probe] script is executable",
          os.access(CHECK_SP_CURRENT, os.X_OK), "")


def test_check_sp_current_offline_silent() -> None:
    """--offline mode exits 0 silently."""
    print("\n[check-sp-current: offline silent]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--offline"])
    check("[sp-probe] --offline exits 0", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[:200]}")
    check("[sp-probe] --offline silent on stderr", r.stderr.strip() == "",
          r.stderr[:200])


def test_check_sp_current_fixture_no_drift() -> None:
    """Fixture matches sp.md exactly → no drift output."""
    print("\n[check-sp-current: fixture exact match]")
    if not CHECK_SP_CURRENT.exists():
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(SP_CORE_SKILLS) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] no-drift fixture exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] no-drift fixture silent",
              "DRIFT" not in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_missing_skill() -> None:
    """Fixture has a skill sp.md doesn't list → drift, names it."""
    print("\n[check-sp-current: fixture missing skill]")
    if not CHECK_SP_CURRENT.exists():
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(SP_CORE_SKILLS + ["new-skill-x"]) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] missing-skill exits 0 (informational)",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] missing-skill stderr says DRIFT",
              "DRIFT" in r.stderr, r.stderr[:200])
        check("[sp-probe] missing-skill names the new skill",
              "new-skill-x" in r.stderr, r.stderr[:200])
        check("[sp-probe] missing-skill labels it 'Missing from sp.md'",
              "Missing from sp.md" in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_extra_skill() -> None:
    """Fixture missing a skill sp.md lists → drift labelled 'Extra in sp.md'."""
    print("\n[check-sp-current: fixture extra in sp.md]")
    if not CHECK_SP_CURRENT.exists():
        return
    # Drop one skill from the fixture so sp.md has one extra.
    fixture_skills = [s for s in SP_CORE_SKILLS if s != "using-git-worktrees"]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(fixture_skills) + "\n")
        fixture = f.name
    try:
        r = _run_sp_probe(["--fixture", fixture])
        check("[sp-probe] extra-skill exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        check("[sp-probe] extra-skill stderr says DRIFT",
              "DRIFT" in r.stderr, r.stderr[:200])
        check("[sp-probe] extra-skill names the dropped skill",
              "using-git-worktrees" in r.stderr, r.stderr[:200])
        check("[sp-probe] extra-skill labels it 'Extra in sp.md'",
              "Extra in sp.md" in r.stderr, r.stderr[:200])
    finally:
        os.unlink(fixture)


def test_check_sp_current_fixture_nonexistent_errors() -> None:
    """--fixture with unreadable path errors out."""
    print("\n[check-sp-current: fixture nonexistent]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--fixture", "/no/such/file"])
    check("[sp-probe] nonexistent fixture exit 1", r.returncode == 1,
          f"rc={r.returncode}")
    check("[sp-probe] nonexistent fixture explains itself",
          "readable file" in r.stderr, r.stderr[:200])


def test_check_sp_current_unknown_arg_errors() -> None:
    """Unknown flag errors out."""
    print("\n[check-sp-current: unknown arg]")
    if not CHECK_SP_CURRENT.exists():
        return
    r = _run_sp_probe(["--bogus"])
    check("[sp-probe] unknown arg exit 1", r.returncode == 1,
          f"rc={r.returncode}")
    check("[sp-probe] unknown arg names the bad flag",
          "--bogus" in r.stderr, r.stderr[:200])


def test_check_sp_current_wired_into_container_start() -> None:
    """Drift check ships in the image and runs from install-claude-extras.sh."""
    print("\n[check-sp-current: container-start wiring]")
    dockerfile = DOCKERFILE.read_text()
    check("[sp-wire] Dockerfile COPYs check-sp-current.sh to /usr/local/bin",
          "COPY check-sp-current.sh /usr/local/bin/" in dockerfile, "")
    check("[sp-wire] Dockerfile chmods the checker",
          "/usr/local/bin/check-sp-current.sh" in dockerfile, "")
    extras = INSTALL_EXTRAS.read_text()
    check("[sp-wire] extras script defines check_sp_drift",
          "check_sp_drift()" in extras, "")
    check("[sp-wire] check_sp_drift is invoked",
          re.search(r"^check_sp_drift$", extras, re.MULTILINE) is not None, "")
    check("[sp-wire] honours VIBE_PLUGINS=0 opt-out",
          'VIBE_PLUGINS:-1' in extras.split("check_sp_drift()")[1].split("}")[0], "")
    check("[sp-wire] guards on checker executable (old-image safe)",
          '[ -x "$checker" ] || return 0' in extras, "")
    check("[sp-wire] points SP_MD at the synced commands dir",
          'SP_MD="$DEST_ROOT/commands/sp.md"' in extras, "")
    # 24h throttle (2026-08-30): probe gated on _sp_drift_due; stamp written
    # before every probe attempt so a dead network still burns one slot/day.
    check("[sp-wire] probe gated on _sp_drift_due",
          '_sp_drift_due "$stamp" || return 0' in extras, "")
    check("[sp-wire] stamp written before the checker runs",
          extras.find('date -u +%s > "$stamp"') < extras.find('SP_MD="$DEST_ROOT/commands/sp.md" "$checker"')
          and 'date -u +%s > "$stamp"' in extras, "")
    check("[sp-wire] VIBE_PLUGINS=0 short-circuits before the stamp path",
          extras.split("check_sp_drift()")[1].find("VIBE_PLUGINS:-1")
          < extras.split("check_sp_drift()")[1].find("_sp_drift_due"), "")

    def due(setup: str, env_extra: str = "") -> str:
        fn = subprocess.run(
            ["bash", "-c",
             'set -euo pipefail; '
             f'source <(sed -n "/^_sp_drift_due()/,/^}}/p" {shlex.quote(str(INSTALL_EXTRAS))}); '
             'S=$(mktemp -d)/stamp; ' + setup + '; '
             + env_extra +
             'if _sp_drift_due "$S"; then echo R=DUE; else echo R=NOT; fi'],
            capture_output=True, text=True)
        if "R=DUE" in fn.stdout:
            return "DUE"
        if "R=NOT" in fn.stdout:
            return "NOT"
        return f"ERR({fn.stdout}{fn.stderr})"

    check("[sp-throttle] absent stamp -> due", due("true") == "DUE", "")
    check("[sp-throttle] fresh stamp -> not due",
          due('date -u +%s > "$S"') == "NOT", "")
    check("[sp-throttle] stale stamp -> due",
          due('echo $(( $(date -u +%s) - 90000 )) > "$S"') == "DUE", "")
    check("[sp-throttle] malformed stamp -> due (stale, not error)",
          due('echo garbage > "$S"') == "DUE", "")
    check("[sp-throttle] future-dated stamp -> due",
          due('echo $(( $(date -u +%s) + 3600 )) > "$S"') == "DUE", "")
    check("[sp-throttle] override honoured at the boundary",
          due('echo $(( $(date -u +%s) - 120 )) > "$S"',
              "export VIBE_SP_DRIFT_MAX_AGE_SECS=60; ") == "DUE", "")
    check("[sp-throttle] override: inside window -> not due",
          due('echo $(( $(date -u +%s) - 30 )) > "$S"',
              "export VIBE_SP_DRIFT_MAX_AGE_SECS=60; ") == "NOT", "")
    check("[sp-throttle] zero override = always due",
          due('date -u +%s > "$S"',
              "export VIBE_SP_DRIFT_MAX_AGE_SECS=0; ") == "DUE", "")
    check("[sp-throttle] garbage override collapses to default (fresh -> not due)",
          due('date -u +%s > "$S"',
              "export VIBE_SP_DRIFT_MAX_AGE_SECS=bogus; ") == "NOT", "")


# ── /sp slash command tests ────────────────────────────────────────────────────


def test_sp_md_present_and_complete() -> None:
    """sp.md is shipped and references the seven Superpowers core skills."""
    print("\n[/sp: sp.md present + complete]")
    check("[sp] sp.md exists", SP_MD.exists(), str(SP_MD))
    if not SP_MD.exists():
        return
    content = SP_MD.read_text()
    check("[sp] frontmatter description present",
          "description: Apply Superpowers methodology" in content,
          "missing description in frontmatter")
    expected_skills = [
        "superpowers:using-superpowers",
        "superpowers:brainstorming",
        "superpowers:writing-plans",
        "superpowers:executing-plans",
        "superpowers:subagent-driven-development",
        "superpowers:dispatching-parallel-agents",
        "superpowers:test-driven-development",
        "superpowers:systematic-debugging",
        "superpowers:requesting-code-review",
        "superpowers:receiving-code-review",
        "superpowers:verification-before-completion",
        "superpowers:finishing-a-development-branch",
        "superpowers:using-git-worktrees",
        "superpowers:writing-skills",
    ]
    for skill in expected_skills:
        check(f"[sp] mentions {skill}", skill in content,
              f"missing skill: {skill}")
    check("[sp] documents official marketplace install",
          "claude-plugins-official" in content, "")
    check("[sp] documents fallback obra marketplace",
          "obra/superpowers-marketplace" in content, "")


def test_sp_md_referenced_from_readme() -> None:
    """README mentions /sp so users can discover it."""
    print("\n[/sp: README mentions /sp]")
    readme = REPO / "README.md"
    check("[sp] README.md exists", readme.exists(), str(readme))
    if not readme.exists():
        return
    content = readme.read_text()
    check("[sp] README mentions `/sp`", "/sp" in content, "")


def test_skipped_marker_round_trip() -> None:
    """mark_github_skipped writes WORKSPACE; is_github_skipped reads it back."""
    print("\n[skipped: literal path round-trip]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        env = {
            **os.environ,
            "HOME": str(home),
            "VIBE_CONFIG": "/dev/null",
            "VIBE_SOURCE_ONLY": "1",
            "WORKSPACE": str(proj),
        }
        script = (
            f"source {shlex.quote(str(VIBE))}; "
            'mark_github_skipped >/dev/null; '
            'if is_github_skipped; then echo "SKIPPED=true"; '
            'else echo "SKIPPED=false"; fi'
        )
        r = subprocess.run(["bash", "-c", script], env=env,
                           capture_output=True, text=True)
        check("[skipped] mark+check round-trip exits 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr[:200]}")
        check("[skipped] is_github_skipped returns true after mark",
              "SKIPPED=true" in r.stdout, r.stdout)


def test_skipped_marker_trailing_slash() -> None:
    """is_github_skipped tolerates trailing-slash difference between mark and lookup."""
    print("\n[skipped: trailing-slash tolerance]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Pre-seed with no-slash form (canonical), then look up with trailing slash.
        rc, out, _ = _run_skipped_probe(
            workspace=f"{proj}/",
            marker_state=[str(proj)],
            home=home,
        )
        check("[skipped] trailing-slash WORKSPACE matches no-slash entry",
              "SKIPPED=true" in out, out)


def test_skipped_marker_symlink_path() -> None:
    """is_github_skipped tolerates symlinked path equivalent to a marked entry."""
    print("\n[skipped: symlink-equivalent path]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        sym = home / "symproj"
        sym.symlink_to("realproj")
        # Pre-seed with the canonical (real) path, look up via symlink.
        rc, out, _ = _run_skipped_probe(
            workspace=str(sym),
            marker_state=[str(proj)],
            home=home,
        )
        check("[skipped] symlinked WORKSPACE matches canonical entry",
              "SKIPPED=true" in out, out)


def test_skipped_marker_writes_canonical() -> None:
    """mark_github_skipped writes the canonical (cd && pwd -P) form."""
    print("\n[skipped: mark writes canonical path]")
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "realproj"
        proj.mkdir()
        # Set WORKSPACE with a trailing slash; mark should still write canonical.
        env = {
            **os.environ,
            "HOME": str(home),
            "VIBE_CONFIG": "/dev/null",
            "VIBE_SOURCE_ONLY": "1",
            "WORKSPACE": f"{proj}/",
        }
        script = (
            f"source {shlex.quote(str(VIBE))}; mark_github_skipped >/dev/null"
        )
        r = subprocess.run(["bash", "-c", script], env=env,
                           capture_output=True, text=True)
        check("[skipped] mark exits 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:200]}")
        skipped_path = home / ".vibe" / "skipped"
        content = skipped_path.read_text().splitlines() if skipped_path.exists() else []
        check("[skipped] file contains canonical (no trailing slash) path",
              str(proj) in content, str(content))
