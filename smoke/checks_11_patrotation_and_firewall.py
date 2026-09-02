from smoke._core import *  # noqa: F401,F403




# ── task_026 cycle-2: three security fixes ──────────────────────────────────
# (1) maybe_reprompt_stored_token must survive a REAL setup_token call under
#     `set -euo pipefail` + closed stdin — setup_token has unguarded `read`s
#     (out of scope to change) that return non-zero on EOF; the call site
#     wraps it `setup_token "$repo" || true` so those failures can't abort
#     the launcher.
# (2) Slug trust boundary: maybe_reprompt_stored_token must fail open (no
#     probe) for a repo string that fails is_valid_repo_slug, since
#     detect_github_repo's regex is looser and can hand it something
#     is_valid_repo_slug rejects (e.g. a `+` in a path segment); `vibe pat`
#     with no arg must likewise refuse a detected slug that fails
#     is_valid_repo_slug, rather than trust it into rotate_token/save_token.
# (3) rotate_token must refuse to save a pasted token containing `"`, `\`,
#     whitespace, or a control character — those would break the unescaped
#     `header = "Authorization: Bearer <token>"` -K config line consumed by
#     stored_token_rejected.

def test_task026_c2_maybe_reprompt_real_setup_token_survives_closed_stdin() -> None:
    """Fix (1): stub ONLY stored_token_rejected (forced rejection); let the
    real setup_token run, under `set -euo pipefail`, with stdin closed. Its
    unguarded `read -rp` (open-browser prompt) and `read -rsp` (token paste)
    both fail on EOF, and `open` isn't installed in this container either —
    none of that may abort the script. Assert rc=0 AND a sentinel printed
    after the call actually executes (proof the script survived, not just
    that the final exit code happened to be 0)."""
    print("\n[task_026 c2 fix-1: real setup_token survives closed stdin under set -euo pipefail]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
set -euo pipefail
source {shlex.quote(str(VIBE))}

stored_token_rejected() {{ return 0; }}

maybe_reprompt_stored_token owner/repo ghp_task026_fixture_token < /dev/null
echo SENTINEL_SURVIVED_C2A
"""
        r = run(["bash", "-c", script], env=env)
        check("rc=0", r.returncode == 0, f"returncode={r.returncode} stderr={r.stderr}")
        check("sentinel printed after the call (script survived)", "SENTINEL_SURVIVED_C2A" in r.stdout, r.stdout)
        check("fixture token absent from output", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_c2_maybe_reprompt_invalid_slug_never_probes() -> None:
    """Fix (2), wrapper half: an invalid slug (fails is_valid_repo_slug, e.g.
    a `+` that detect_github_repo's looser regex would tolerate) must make
    maybe_reprompt_stored_token return 0 WITHOUT ever invoking the curl
    probe. Real stored_token_rejected (not stubbed) + a logging curl shim —
    the shim's log files must stay entirely absent/empty, proving the probe
    was never reached."""
    print("\n[task_026 c2 fix-2: maybe_reprompt_stored_token never probes an invalid slug]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        new_path, argv_log, stdin_log = _setup_curl_shim(tmp, response_code="401")
        env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
set +e
maybe_reprompt_stored_token "owner/re+po" ghp_task026_fixture_token
RC=$?
set -e
echo "RC=$RC"
"""
        r = run(["bash", "-c", script], env=env)
        check("returns 0", "RC=0" in r.stdout, r.stdout)
        check("curl shim argv log never created (probe never ran)", not argv_log.exists(),
              argv_log.read_text() if argv_log.exists() else "")
        check("curl shim stdin log never created (probe never ran)", not stdin_log.exists(),
              stdin_log.read_text() if stdin_log.exists() else "")
        check("fixture token absent from output", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_c2_pat_no_arg_refuses_invalid_detected_slug() -> None:
    """Fix (2), `vibe pat` half: a git checkout whose 'origin' remote yields
    a slug that detect_github_repo accepts but is_valid_repo_slug rejects
    (a `+` in the owner segment) must make `vibe pat` (no arg) exit 1 with
    a stderr refusal — never reaching rotate_token/save_token (verified via
    curl shim logs). Sanctioned C2 amendment: checks for specific slug and
    'is not a valid' message removed; tests now verify exit 1, empty stdout,
    stderr error mentioning 'vibe pat', and curl probe never invoked."""
    print("\n[task_026 c2 fix-2: vibe pat (no arg) refuses an is_valid_repo_slug-failing detected slug]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        new_path, argv_log, stdin_log = _setup_curl_shim(tmp, response_code="200")
        checkout = tmp / "checkout"
        checkout.mkdir()
        env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        run(["git", "init"], cwd=checkout, env=env)
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=checkout, env=env)
        run(["git", "remote", "add", "origin", "https://github.com/ow+ner/repo.git"], cwd=checkout, env=env)

        script = f"""
cd {shlex.quote(str(checkout))}
source {shlex.quote(str(VIBE))}
pat_handle_subcommand pat < /dev/null
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, f"returncode={r.returncode}")
        check("nothing on stdout", r.stdout == "", r.stdout)
        check("stderr error mentions vibe pat", "vibe pat" in r.stderr, r.stderr)
        check("curl shim argv log never created (probe never ran)", not argv_log.exists(),
              argv_log.read_text() if argv_log.exists() else "")
        check("curl shim stdin log never created (probe never ran)", not stdin_log.exists(),
              stdin_log.read_text() if stdin_log.exists() else "")


def test_task026_c2_rotate_token_rejects_bad_charset() -> None:
    """Fix (3): a pasted token containing a `"`, or containing whitespace,
    must be refused — pinned stderr message, exit 1, token store
    byte-identical to before the call. A clean fixture-token paste in the
    same store must still save normally (proves the charset check isn't
    over-broad)."""
    print("\n[task_026 c2 fix-3: rotate_token refuses tokens with disallowed characters]")

    for label, bad_token_hstring in [
        ("embedded double-quote", '"bad\\"token"'),
        ("embedded space", '"bad token"'),
    ]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
            tokens_file = tmp / ".vibe" / "tokens"
            tokens_file.parent.mkdir(parents=True)
            tokens_file.write_text("owner/repo=ghp_existing\n")
            orig_content = tokens_file.read_text()

            # rotate_token always calls `exit` (never `return`), so its exit
            # code IS the subprocess's returncode — check that directly, the
            # same way test_task026_ac3_empty_input_eof does, rather than an
            # `echo RC=$?` that would never run.
            script = f"""
source {shlex.quote(str(VIBE))}
rotate_token owner/repo <<< {bad_token_hstring}
"""
            r = run(["bash", "-c", script], env=env)
            check(f"exit 1 ({label})", r.returncode == 1, f"returncode={r.returncode}")
            check(f"pinned refusal message on stderr ({label})",
                  "vibe pat: token contains characters no GitHub PAT uses — not saved" in r.stderr, r.stderr)
            check(f"token store byte-identical ({label})", tokens_file.read_text() == orig_content,
                  f"before: {orig_content!r}, after: {tokens_file.read_text()!r}")

    # Clean token in the same shape of store still saves — the charset check
    # isn't accidentally rejecting valid PAT charset bytes.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        tokens_file = tmp / ".vibe" / "tokens"
        tokens_file.parent.mkdir(parents=True)
        tokens_file.write_text("owner/repo=ghp_existing\n")

        script = f"""
source {shlex.quote(str(VIBE))}
echo ghp_task026_fixture_token | rotate_token owner/repo
"""
        r = run(["bash", "-c", script], env=env)
        check("clean token: exit 0", r.returncode == 0, f"returncode={r.returncode} stderr={r.stderr}")
        check("clean token: saved", "owner/repo=ghp_task026_fixture_token" in tokens_file.read_text(),
              tokens_file.read_text())
        check("clean token: fixture token absent from process output", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


# ── task_027: detect_github_repo dotted-repo fix + brain2 vibe-operation note ──

def test_task027_ac1_dotted_repo_https_with_git() -> None:
    """AC1: detect_github_repo in tmp git repo handles dotted repo names.
    URL: https://github.com/andeyePro/andeye.com.git → slug: andeyePro/andeye.com"""
    print("\n[task_027 AC1a: detect_github_repo https://.../.git]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/andeyePro/andeye.com.git"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs andeyePro/andeye.com", r.stdout.strip() == "andeyePro/andeye.com", r.stdout)


def test_task027_ac1_dotted_repo_https_no_git() -> None:
    """AC1: detect_github_repo handles URL without .git suffix.
    URL: https://github.com/andeyePro/andeye.com → slug: andeyePro/andeye.com"""
    print("\n[task_027 AC1b: detect_github_repo https://... (no .git)]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/andeyePro/andeye.com"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs andeyePro/andeye.com", r.stdout.strip() == "andeyePro/andeye.com", r.stdout)


def test_task027_ac1_ssh_format_with_git() -> None:
    """AC1: detect_github_repo handles SSH format.
    URL: git@github.com:owner/repo.git → slug: owner/repo"""
    print("\n[task_027 AC1c: detect_github_repo git@github.com:owner/repo.git]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "git@github.com:owner/repo.git"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs owner/repo", r.stdout.strip() == "owner/repo", r.stdout)


def test_task027_ac1_ssh_protocol_with_git() -> None:
    """AC1: detect_github_repo handles SSH protocol format.
    URL: ssh://git@github.com/owner/repo.git → slug: owner/repo"""
    print("\n[task_027 AC1d: detect_github_repo ssh://git@github.com/owner/repo.git]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "ssh://git@github.com/owner/repo.git"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs owner/repo", r.stdout.strip() == "owner/repo", r.stdout)


def test_task027_ac1_https_regression_standard_repo() -> None:
    """AC1: detect_github_repo regression check.
    URL: https://github.com/owner/repo.git → slug: owner/repo"""
    print("\n[task_027 AC1e: detect_github_repo https://github.com/owner/repo.git (regression)]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/owner/repo.git"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs owner/repo", r.stdout.strip() == "owner/repo", r.stdout)


def test_task027_ac1_trailing_slash() -> None:
    """AC1: detect_github_repo handles trailing slash.
    URL: https://github.com/owner/repo/ (trailing slash) → slug: owner/repo"""
    print("\n[task_027 AC1f: detect_github_repo trailing slash]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/owner/repo/"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs owner/repo", r.stdout.strip() == "owner/repo", r.stdout)


def test_task027_ac1_double_git_suffix() -> None:
    """AC1: detect_github_repo strips exactly one .git suffix.
    URL: https://github.com/owner/foo.git.git → slug: foo.git"""
    print("\n[task_027 AC1g: detect_github_repo foo.git.git strips one .git]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/owner/foo.git.git"
source {shlex.quote(str(VIBE))}
detect_github_repo
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("outputs owner/foo.git", r.stdout.strip() == "owner/foo.git", r.stdout)


def test_task027_ac2_no_remote() -> None:
    """AC2: detect_github_repo returns rc 1 for repo with no remote."""
    print("\n[task_027 AC2a: detect_github_repo no remote returns 1]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
source {shlex.quote(str(VIBE))}
set +e
detect_github_repo
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", "RC=1" in r.stdout, r.stdout)
        check("no output before RC=1", r.stdout.strip().endswith("RC=1"), r.stdout)


def test_task027_ac2_non_github_remote() -> None:
    """AC2: detect_github_repo returns rc 1 for non-GitHub remote."""
    print("\n[task_027 AC2b: detect_github_repo non-GitHub remote returns 1]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://gitlab.com/o/r.git"
source {shlex.quote(str(VIBE))}
set +e
detect_github_repo
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", "RC=1" in r.stdout, r.stdout)
        check("no output before RC=1", r.stdout.strip().endswith("RC=1"), r.stdout)


def test_task027_ac2_invalid_slug() -> None:
    """AC2: detect_github_repo returns rc 1 when slug fails is_valid_repo_slug."""
    print("\n[task_027 AC2c: detect_github_repo invalid slug (contains %20) returns 1]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
git init >/dev/null 2>&1
git remote add origin "https://github.com/owner/repo%20name.git"
source {shlex.quote(str(VIBE))}
set +e
detect_github_repo
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", "RC=1" in r.stdout, r.stdout)
        check("no output before RC=1", r.stdout.strip().endswith("RC=1"), r.stdout)


def test_task027_ac3_brain2_creates_file_with_content() -> None:
    """AC3: refresh_brain2_vibe_note creates meta/vibe-operation.md with heading,
    exact markers, Generated line, and help content including Usage: and vibe pat."""
    print("\n[task_027 AC3: refresh_brain2_vibe_note creates file with heading and markers]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        brain2_dir = tmp / "brain2"
        brain2_dir.mkdir()
        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": str(brain2_dir), "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", "RC=0" in r.stdout, r.stdout)

        note_file = brain2_dir / "meta" / "vibe-operation.md"
        check("file created", note_file.exists(), str(note_file))

        if note_file.exists():
            content = note_file.read_text()
            check("contains heading", "# vibe — CLI operation (auto-maintained)" in content, content[:200])
            check("contains open marker", "<!-- >>> vibe-cli-help (auto, do not edit) >>>" in content, "marker not found")
            check("contains close marker", "<!-- <<< vibe-cli-help <<< -->" in content, "marker not found")
            check("contains Generated by line", "Generated by vibe" in content, content[:500])
            check("contains Usage: from help", "Usage:" in content, content[:500])
            check("contains vibe pat command", "vibe pat" in content, content[:500])


def test_task027_ac4_idempotence_preserves_user_content() -> None:
    """AC4: refresh_brain2_vibe_note run twice preserves user content above markers,
    the managed block is present and idempotent, returns 0 both times."""
    print("\n[task_027 AC4: refresh_brain2_vibe_note idempotence and user content preservation]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        brain2_dir = tmp / "brain2"
        brain2_dir.mkdir()
        note_file = brain2_dir / "meta" / "vibe-operation.md"
        note_file.parent.mkdir(parents=True)

        user_content = "# My operational notes\nFoo bar.\n"
        note_file.write_text(user_content)

        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": str(brain2_dir), "VIBE_SOURCE_ONLY": "1"}

        # First run
        script1 = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
echo "RC=$?"
"""
        r1 = run(["bash", "-c", script1], env=env)
        check("first run exit 0", "RC=0" in r1.stdout, r1.stdout)

        content_after_first = note_file.read_text()
        check("user content preserved after first run", "My operational notes" in content_after_first, content_after_first[:300])
        # Verify managed block is present (opening and closing markers exist and are properly nested)
        open_marker = "<!-- >>> vibe-cli-help (auto, do not edit) >>>"
        close_marker = "<!-- <<< vibe-cli-help <<< -->"
        check("open marker present", open_marker in content_after_first, "marker not found")
        check("close marker present", close_marker in content_after_first, "marker not found")
        open_idx = content_after_first.find(open_marker)
        close_idx = content_after_first.find(close_marker)
        check("close marker after open marker", open_idx < close_idx, f"open at {open_idx}, close at {close_idx}")

        # Second run
        r2 = run(["bash", "-c", script1], env=env)
        check("second run exit 0", "RC=0" in r2.stdout, r2.stdout)

        content_after_second = note_file.read_text()
        # The managed block carries a seconds-resolution "Generated by vibe
        # <version> at <ISO>" line, so two runs straddling a second boundary
        # differ by design (flaky under load, seen 2026-09-02). Compare with
        # that one line normalised; everything else must be byte-identical.
        _gen = re.compile(r"^Generated by vibe .* at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", re.M)
        check("idempotent output",
              _gen.sub("Generated by vibe <v> at <t>", content_after_first)
              == _gen.sub("Generated by vibe <v> at <t>", content_after_second),
              "content differs between runs beyond the Generated-at timestamp")
        check("user content still preserved", "My operational notes" in content_after_second, content_after_second[:300])


def test_task027_ac5_fail_soft_vibe_brain2_path_off() -> None:
    """AC5: VIBE_BRAIN2_PATH=off causes refresh_brain2_vibe_note to return 0, create nothing."""
    print("\n[task_027 AC5a: refresh_brain2_vibe_note with VIBE_BRAIN2_PATH=off]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": "off", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", "RC=0" in r.stdout, r.stdout)

        note_file = Path(tmp) / "brain2" / "meta" / "vibe-operation.md"
        check("no file created", not note_file.exists(), str(note_file))


def test_task027_ac5_fail_soft_nonexistent_dir() -> None:
    """AC5: VIBE_BRAIN2_PATH pointing to nonexistent dir returns 0, creates nothing."""
    print("\n[task_027 AC5b: refresh_brain2_vibe_note with nonexistent brain2 dir]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        nonexistent = tmp / "does" / "not" / "exist"
        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": str(nonexistent), "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", "RC=0" in r.stdout, r.stdout)
        check("no dir created", not nonexistent.exists(), str(nonexistent))


def test_task027_ac5_fail_soft_unwritable_meta() -> None:
    """AC5: brain2 dir with unwritable meta/ returns 0, never aborts under set -euo pipefail."""
    print("\n[task_027 AC5c: refresh_brain2_vibe_note with unwritable meta/ (chmod 500)]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        brain2_dir = tmp / "brain2"
        brain2_dir.mkdir()
        meta_dir = brain2_dir / "meta"
        meta_dir.mkdir()
        meta_dir.chmod(0o500)  # read+execute only, no write

        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": str(brain2_dir), "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
echo "RC=$?"
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0 (fail-soft)", "RC=0" in r.stdout, r.stdout)

        # Restore permissions for cleanup
        meta_dir.chmod(0o755)

        note_file = meta_dir / "vibe-operation.md"
        check("no file created in unwritable dir", not note_file.exists(), str(note_file))


def test_task027_ac6_anchor_placement() -> None:
    """AC6: refresh_brain2_vibe_note call site appears between
    '# ── GitHub setup' and '# ── Build the image' and nowhere else in vibe."""
    print("\n[task_027 AC6: refresh_brain2_vibe_note call site placement]")
    vibe_content = VIBE.read_text()

    # Find the markers
    github_setup_idx = vibe_content.find("# ── GitHub setup")
    build_image_idx = vibe_content.find("# ── Build the image")

    check("GitHub setup marker exists", github_setup_idx >= 0, "marker not found")
    check("Build the image marker exists", build_image_idx >= 0, "marker not found")

    if github_setup_idx >= 0 and build_image_idx >= 0:
        # Count how many times the call appears in the entire file
        call_count = vibe_content.count("refresh_brain2_vibe_note || true")
        check("call appears exactly once in vibe", call_count == 1, f"found {call_count} occurrences")

        # Verify it appears between the markers
        call_idx = vibe_content.find("refresh_brain2_vibe_note || true")
        check("call is between markers", github_setup_idx < call_idx < build_image_idx,
              f"GitHub setup at {github_setup_idx}, call at {call_idx}, Build image at {build_image_idx}")


def test_task027_ac7_vibe_cli_fragment_exists() -> None:
    """AC7: devcontainer/claude-md/vibe-cli.md exists and contains required strings."""
    print("\n[task_027 AC7: vibe-cli.md fragment exists and contains required content]")
    vibe_cli_md = REPO / "devcontainer" / "claude-md" / "vibe-cli.md"
    check("vibe-cli.md exists", vibe_cli_md.exists(), str(vibe_cli_md))

    if vibe_cli_md.exists():
        content = vibe_cli_md.read_text()
        check("contains 'vibe-operation.md'", "vibe-operation.md" in content, content[:500])
        check("contains '! vibe --help'", "! vibe --help" in content, content[:500])
        check("contains 'exact command'", "exact command" in content, content[:500])


def test_task027_ac7_vibe_cli_in_glob_not_manifest() -> None:
    """AC7: vibe-cli.md rides the sorted directory glob in install_claude_extras.sh,
    not a manifest edit (verify 'vibe-cli' does not appear in install-claude-extras.sh)."""
    print("\n[task_027 AC7: vibe-cli.md auto-collected via glob, no manifest edit]")
    install_extras_content = INSTALL_EXTRAS.read_text()
    check("'vibe-cli' not in install-claude-extras.sh", "vibe-cli" not in install_extras_content,
          "string 'vibe-cli' found in manifest")


def test_task027_ac9_readme_mentions_vibe_operation() -> None:
    """AC9: README.md contains 'vibe-operation.md'."""
    print("\n[task_027 AC9a: README.md mentions vibe-operation.md]")
    readme = REPO / "README.md"
    check("README.md exists", readme.exists())
    if readme.exists():
        content = readme.read_text()
        check("contains 'vibe-operation.md'", "vibe-operation.md" in content, content[:2000])


def test_task027_ac9_manual_tests_mentions_vibe_operation() -> None:
    """AC9: MANUAL-TESTS.md contains 'vibe-operation.md'."""
    print("\n[task_027 AC9b: MANUAL-TESTS.md mentions vibe-operation.md]")
    manual_tests = REPO / "MANUAL-TESTS.md"
    check("MANUAL-TESTS.md exists", manual_tests.exists())
    if manual_tests.exists():
        content = manual_tests.read_text()
        check("contains 'vibe-operation.md'", "vibe-operation.md" in content, content[:2000])


def test_task027_ac10_no_secrets_in_note() -> None:
    """AC10: No token/secret material in help note — no ghp_ substrings."""
    print("\n[task_027 AC10: help note contains no secrets]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        brain2_dir = tmp / "brain2"
        brain2_dir.mkdir()
        env = {**os.environ, "HOME": str(tmp), "VIBE_BRAIN2_PATH": str(brain2_dir), "VIBE_SOURCE_ONLY": "1"}

        script = f"""
source {shlex.quote(str(VIBE))}
refresh_brain2_vibe_note
"""
        r = run(["bash", "-c", script], env=env)
        check("runs silently (no stdout)", r.stdout == "", r.stdout)
        check("no secrets in stderr", "ghp_" not in r.stderr, r.stderr[:500])

        note_file = brain2_dir / "meta" / "vibe-operation.md"
        if note_file.exists():
            content = note_file.read_text()
            check("note contains no ghp_ tokens", "ghp_" not in content, "secret found in help text")


def test_task028_ac1_source_only_no_side_effects() -> None:
    """VIBE_FIREWALL_SOURCE_ONLY exposes the helpers and touches nothing."""
    print("\n[task_028 AC1: source-only test hook]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r, calls = _fw_run(tmp, "exit 1", 'type -t fetch_gh_ranges')
        check("sources cleanly", r.returncode == 0, r.stderr[:400])
        check("fetch_gh_ranges defined", "function" in r.stdout, r.stdout)
        check("no curl call on source", calls == 0, f"calls={calls}")
        check("no iptables output", "iptables" not in r.stderr, r.stderr[:400])


def test_task028_ac2_retries_then_succeeds() -> None:
    """A transient failure is retried, not fatal -- the live 2026-07-29 case."""
    print("\n[task_028 AC2: retry recovers a transient failure]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        body = f'if [ "$n" -lt 3 ]; then exit 28; fi\necho \'{_FW_GOOD_JSON}\''
        r, calls = _fw_run(tmp, body, 'fetch_gh_ranges; echo "RC=$?"')
        check("succeeds after retrying", "RC=0" in r.stdout, r.stdout[:400])
        check("made 3 attempts", calls == 3, f"calls={calls}")
        check("emits the payload", '"web"' in r.stdout, r.stdout[:400])
        check("warns on each failed attempt",
              r.stderr.count("WARNING") == 2, r.stderr[:400])


def test_task028_ac3_all_attempts_fail_returns_nonzero() -> None:
    """Exhausted retries must still fail, so the trap locks the box down."""
    print("\n[task_028 AC3: exhausted retries stay fatal]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Mirrors the real call site's `if ! gh_ranges=$(fetch_gh_ranges)`;
        # a bare call would be killed by the script's own `set -e` first.
        r, calls = _fw_run(
            tmp, "exit 28",
            'if ! fetch_gh_ranges >/dev/null; then echo "RC=1"; else echo "RC=0"; fi')
        check("returns non-zero", "RC=1" in r.stdout, r.stdout[:400])
        check("stopped at the attempt cap", calls == 3, f"calls={calls}")


def test_gh_meta_rate_limit_and_cache_fallback() -> None:
    """2026-09-02: the anonymous /meta limit was exhausted by a day of container
    starts and every launch failed closed. fetch_gh_ranges now (a) sends the
    container's PAT, (b) stops retrying on a rate-limit body, (c) caches the
    last good body and (d) serves the cache when the fetch fails; (e) with no
    cache the fail-closed path is unchanged."""
    print("\n[gh-meta: rate-limit fast path, PAT auth, cached-ranges fallback]")
    rate_limited = '{"message":"API rate limit exceeded for 203.0.113.1. (But here is the good news)"}'
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cache = tmp / "cache" / "gh-meta-cache.json"
        base_env = {"GH_META_CACHE": str(cache)}
        # (b)+(e): rate-limit body -> exactly one call, RC=1 without a cache
        log = tmp / "curl.log"; log.write_text("")
        env = {**os.environ, "PATH": _fw_stub_curl(tmp, script_body=f"echo '{rate_limited}'"),
               "STUB_LOG": str(log), "VIBE_FIREWALL_SOURCE_ONLY": "1", "GH_FETCH_BACKOFF": "0",
               "GH_FETCH_ATTEMPTS": "3", **base_env}
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n"
                 'if ! fetch_gh_ranges >/dev/null; then echo "RC=1"; else echo "RC=0"; fi'], env=env)
        calls = len([ln for ln in log.read_text().splitlines() if ln.strip()])
        check("[gh-meta] rate-limited body stops after ONE attempt", calls == 1, f"calls={calls}")
        check("[gh-meta] no cache -> still fails (fail-closed path unchanged)", "RC=1" in r.stdout, r.stdout[:300])
        check("[gh-meta] rate-limit warning names the condition", "rate-limited" in r.stderr, r.stderr[:300])
        # (c): a good fetch writes the cache
        log.write_text("")
        env["PATH"] = _fw_stub_curl(tmp, script_body=f"echo '{_FW_GOOD_JSON}'")
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nfetch_gh_ranges >/dev/null; echo RC=$?"], env=env)
        check("[gh-meta] good fetch succeeds", "RC=0" in r.stdout, r.stdout[:200])
        check("[gh-meta] good fetch writes the cache", cache.is_file() and json.loads(cache.read_text())["web"] == ["1.2.3.0/24"], str(cache))
        # (d): fetch fails (curl rc 28) -> cache served, RC=0, body == cache
        log.write_text("")
        env["PATH"] = _fw_stub_curl(tmp, script_body="exit 28")
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nfetch_gh_ranges; echo; echo RC=$?"], env=env)
        check("[gh-meta] cache served when every attempt fails", "RC=0" in r.stdout and '"1.2.3.0/24"' in r.stdout, r.stdout[:300])
        check("[gh-meta] cache fallback is announced on stderr", "cached IP ranges" in r.stderr, r.stderr[:300])
        # corrupt cache -> not served
        cache.write_text("not json")
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n"
                 'if ! fetch_gh_ranges >/dev/null; then echo "RC=1"; else echo "RC=0"; fi'], env=env)
        check("[gh-meta] a corrupt cache is ignored (fails closed)", "RC=1" in r.stdout, r.stdout[:300])
        # (a): the PAT rides along as a bearer header; absent when unset
        argslog = tmp / "args.log"; argslog.write_text("")
        # The stub records argv AND stdin (curl -K - reads its config there).
        # Only drain stdin when curl was given `-K -` (config on stdin) — an
        # unconditional `cat` would block on an inherited, never-closed stdin.
        body = (f"echo \"ARGV: $@\" >> {shlex.quote(str(argslog))}\n"
                f"case \" $* \" in *' -K '*) cat >> {shlex.quote(str(argslog))};; esac\necho '{_FW_GOOD_JSON}'")
        env["PATH"] = _fw_stub_curl(tmp, script_body=body); env["GITHUB_TOKEN"] = "ghp_fixture_not_a_real_token"
        run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nfetch_gh_ranges >/dev/null"], env=env)
        rec = argslog.read_text()
        check("[gh-meta] PAT sent as Authorization: Bearer via curl config on stdin",
              'header = "Authorization: Bearer ghp_fixture_not_a_real_token"' in rec, rec[:400])
        check("[gh-meta] PAT never appears in curl's argv", "ghp_fixture_not_a_real_token" not in [ln for ln in rec.splitlines() if ln.startswith("ARGV:")].__str__(), rec[:400])
        argslog.write_text("")
        env["GH_META_URL"] = "https://evil.example/meta"
        run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nfetch_gh_ranges >/dev/null"], env=env)
        check("[gh-meta] token withheld when GH_META_URL is not api.github.com", "ghp_fixture" not in argslog.read_text(), argslog.read_text()[:300])
        env.pop("GH_META_URL", None); argslog.write_text(""); env.pop("GITHUB_TOKEN", None)
        run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nfetch_gh_ranges >/dev/null"], env=env)
        check("[gh-meta] no Authorization header without a token", "Authorization" not in argslog.read_text(), argslog.read_text()[:300])
        # stdin token path used by postStartCommand (printf token | sudo init-firewall.sh)
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\nprintf 'ghp_from_stdin' | {{ _gh_meta_token_from_stdin; echo \"TOK=$GH_META_TOKEN\"; }}"], env=env)
        check("[gh-meta] token read from stdin when piped", "TOK=ghp_from_stdin" in r.stdout, r.stdout[:200] + r.stderr[:200])
        # cache hygiene: wrong dir mode, symlinked file, stale file are all ignored
        cache.parent.mkdir(parents=True, exist_ok=True); cache.parent.chmod(0o700)
        cache.write_text(_FW_GOOD_JSON); cache.chmod(0o600)
        env["PATH"] = _fw_stub_curl(tmp, script_body="exit 28")
        probe = 'if ! fetch_gh_ranges >/dev/null; then echo "RC=1"; else echo "RC=0"; fi'
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n{probe}"], env=env)
        check("[gh-meta] well-owned 0700 dir + 0600 file is served", "RC=0" in r.stdout, r.stdout[:200])
        cache.parent.chmod(0o755)
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n{probe}"], env=env)
        check("[gh-meta] cache dir not 0700 -> ignored", "RC=1" in r.stdout, r.stdout[:200])
        cache.parent.chmod(0o700); cache.chmod(0o644)
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n{probe}"], env=env)
        check("[gh-meta] cache file not 0600 -> ignored", "RC=1" in r.stdout, r.stdout[:200])
        cache.chmod(0o600); real = tmp / "elsewhere.json"; real.write_text(_FW_GOOD_JSON); real.chmod(0o600)
        cache.unlink(); cache.symlink_to(real)
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n{probe}"], env=env)
        check("[gh-meta] symlinked cache file -> ignored", "RC=1" in r.stdout, r.stdout[:200])
        cache.unlink(); cache.write_text(_FW_GOOD_JSON); cache.chmod(0o600)
        os.utime(cache, (1, 1))  # epoch 1970: far older than the 30-day limit
        r = run(["bash", "-c", f"source {shlex.quote(str(INIT_FIREWALL))}\n{probe}"], env=env)
        check("[gh-meta] cache older than the max age -> ignored", "RC=1" in r.stdout, r.stdout[:200])
        # public-CIDR validator
        good = ["140.82.112.0/20", "192.30.252.0/22", "185.199.108.0/22", "20.201.28.151/32"]
        bad = ["0.0.0.0/0", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "100.64.0.0/10", "8.0.0.0/7", "256.1.1.1/24", "1.2.3.4", "9.0.0.0/8", "11.0.0.0/12", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24"]
        script = f"source {shlex.quote(str(INIT_FIREWALL))}\nfor c in {' '.join(good)}; do _public_ipv4_cidr \"$c\" && echo \"OK $c\"; done\nfor c in {' '.join(bad)}; do _public_ipv4_cidr \"$c\" || echo \"REJ $c\"; done"
        r = run(["bash", "-c", script], env=env)
        for c in good: check(f"[gh-meta] validator accepts {c}", f"OK {c}" in r.stdout, r.stdout[:400])
        for c in bad: check(f"[gh-meta] validator rejects {c}", f"REJ {c}" in r.stdout, r.stdout[:400])


def test_task028_ac4_no_needless_retry_on_first_success() -> None:
    """A healthy fetch costs exactly one call -- no added boot latency."""
    print("\n[task_028 AC4: clean path unchanged]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r, calls = _fw_run(tmp, f"echo '{_FW_GOOD_JSON}'",
                           'fetch_gh_ranges >/dev/null; echo "RC=$?"')
        check("succeeds", "RC=0" in r.stdout, r.stdout[:400])
        check("exactly one attempt", calls == 1, f"calls={calls}")
        check("no warnings", "WARNING" not in r.stderr, r.stderr[:400])


def test_task028_ac5_unusable_body_is_retried() -> None:
    """An error body parses as JSON but lacks .web/.api/.git -- retry it.
    (A RATE-LIMIT body is deliberately NOT retried any more — see
    test_gh_meta_rate_limit_and_cache_fallback — so the fixture here is a
    generic server-error JSON, the half-ready-network case.)"""
    print("\n[task_028 AC5: unusable response retried, not accepted]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        unusable = '{"message":"Server Error"}'
        body = (f'if [ "$n" -lt 2 ]; then echo \'{unusable}\'; exit 0; fi\n'
                f"echo '{_FW_GOOD_JSON}'")
        r, calls = _fw_run(tmp, body, 'fetch_gh_ranges; echo "RC=$?"')
        check("does not accept the unusable body",
              "Server Error" not in r.stdout, r.stdout[:400])
        check("retries to a good response", "RC=0" in r.stdout, r.stdout[:400])
        check("made 2 attempts", calls == 2, f"calls={calls}")
        check("warning logs a snippet of the unusable body",
              "body starts:" in r.stderr and "Server Error" in r.stderr,
              r.stderr[:400])


def test_task028_ac6_empty_body_is_retried() -> None:
    """curl exiting 0 with an empty body must not be treated as success."""
    print("\n[task_028 AC6: empty body retried]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        body = f'if [ "$n" -lt 2 ]; then exit 0; fi\necho \'{_FW_GOOD_JSON}\''
        r, calls = _fw_run(tmp, body, 'fetch_gh_ranges >/dev/null; echo "RC=$?"')
        check("retries past the empty body", "RC=0" in r.stdout, r.stdout[:400])
        check("made 2 attempts", calls == 2, f"calls={calls}")


def test_task030_mount_drift() -> None:
    """shared_repos_mount_drift: recreate iff the desired /repos mount set
    (dest+source+mode) differs from the container's actual mounts."""
    print("\n[task_030: shared-repo mount drift comparator]")

    def drift(scan: str, actual: str) -> str:
        r = _source_vibe_call(
            {}, f'printf "%s" "$(shared_repos_mount_drift {shlex.quote(scan)} {shlex.quote(actual)})"')
        check("comparator exits 0", r.returncode == 0, r.stderr[:300])
        return r.stdout.strip()

    scan = ("M timeandeye ro andeyePro/timeandeye /Users/m/Projects/timeandeye\n"
            "M andeyePro rw andeyePro/andeyePro /Users/m/andeye Dropbox/Projects/andeyePro")
    matching = ("/workspace\t/Users/m/proj\trw\n"
                "/repos/timeandeye\t/Users/m/Projects/timeandeye\tro\n"
                "/repos/.signals/timeandeye\t/Users/m/Projects/timeandeye/.vibe-signals\trw\n"
                "/repos/andeyePro\t/Users/m/andeye Dropbox/Projects/andeyePro\trw\n"
                "/brain2\t/Users/m/brain2\trw\n")
    check("matching set (spaces in path, extra non-/repos mounts) -> no drift",
          drift(scan, matching) == "", "")
    check("no container sentinel -> no drift", drift(scan, "NONE") == "", "")
    check("declared repo missing from container -> drift",
          drift(scan, "/repos/andeyePro\t/Users/m/andeye Dropbox/Projects/andeyePro\trw\n") == "1", "")
    check("container carries a no-longer-declared repo -> drift",
          drift("", "/repos/old\t/x\tro\n") == "1", "")
    check("registry path moved -> drift",
          drift(scan, matching.replace("/Users/m/Projects/timeandeye\tro",
                                       "/Users/m/elsewhere/timeandeye\tro")) == "1", "")
    check("effective mode flipped (lock handoff) -> drift",
          drift(scan, matching.replace("andeyePro\trw", "andeyePro\tro")) == "1", "")
    check("signals sidecar alone never counts",
          drift("", "/repos/.signals/foo\t/x/.vibe-signals\trw\n") == "", "")


def test_task031_terminal_restore_and_exit_note() -> None:
    """restore_terminal must cover every mouse-tracking encoding claude can
    leave enabled, and claude_exit_note must be quiet on clean/interrupt
    exits but log abnormal ones."""
    print("\n[task_031: terminal hygiene + crash forensics]")
    src = VIBE.read_text()
    for mode in ("1000l", "1002l", "1003l", "1006l", "1015l", "1004l", "2004l", "1049l", "25h"):
        check(f"restore sequence disables ?{mode}", f"?{mode}" in src, "")
    check("supervised launch calls restore_terminal",
          "restore_terminal || true" in src.split("launch_claude_supervised()")[1].split("\n}")[0], "")
    check("supervised launch calls claude_exit_note",
          "claude_exit_note" in src.split("launch_claude_supervised()")[1].split("\n}")[0], "")
    check("exit hook registered", "vibe_exit_hook_add 'restore_terminal || true'" in src, "")
    # functional: sourced, no tty — must no-op cleanly and return 0
    r = _source_vibe_call({}, 'restore_terminal < /dev/null; echo "RC=$?"')
    check("restore_terminal no-tty exits 0", "RC=0" in r.stdout, r.stdout[:200] + r.stderr[:200])
    r = _source_vibe_call({}, 'claude_exit_note 0 /tmp/nonexistent-vibe-ws; echo "RC=$?"')
    check("exit-note silent on rc=0", "RC=0" in r.stdout and "⚠" not in r.stdout, r.stdout[:300])
    r = _source_vibe_call({}, 'claude_exit_note 130 /tmp/nonexistent-vibe-ws; echo "RC=$?"')
    check("exit-note silent on rc=130 (Ctrl-C)", "RC=0" in r.stdout and "⚠" not in r.stdout, r.stdout[:300])
    with tempfile.TemporaryDirectory() as td:
        r = _source_vibe_call({}, f'claude_exit_note 137 {shlex.quote(td)}; echo "RC=$?"')
        check("exit-note logs rc=137", "RC=0" in r.stdout and "rc=137" in r.stdout, r.stdout[:300])
        check("signal hint printed", "signal 9" in r.stdout, r.stdout[:300])
        log = Path(td) / ".vibe" / "last-exit.log"
        check("last-exit.log written", log.exists() and "rc=137" in log.read_text(), "")


def test_task029_default_patience() -> None:
    """The shipped attempt cap must cover a cold Docker Desktop container
    (observed 2026-08-03: 3x2s was not enough; 6 x linear-2s = ~30s is)."""
    print("\n[task_029: default fetch patience]")
    src = INIT_FIREWALL.read_text()
    check("default GH_FETCH_ATTEMPTS is 6",
          'GH_FETCH_ATTEMPTS="${GH_FETCH_ATTEMPTS:-6}"' in src, "")
    check("unusable-body warning carries the body snippet",
          "body starts:" in src, "")


def test_task028_ac7_fetch_has_timeouts() -> None:
    """An unbounded curl would hang postStart instead of failing to the retry."""
    print("\n[task_028 AC7: fetch is time-bounded]")
    src = INIT_FIREWALL.read_text()
    fn = src.split("fetch_gh_ranges()", 1)[1].split("\n}", 1)[0]
    check("--connect-timeout set", "--connect-timeout" in fn, fn[:300])
    check("--max-time set", "--max-time" in fn, fn[:300])


def test_task028_ac8_policy_reset_after_flush() -> None:
    """The policy reset must sit after the flush and before the GitHub fetch."""
    print("\n[task_028 AC8: policy reset placement]")
    src = INIT_FIREWALL.read_text()
    for chain in ("INPUT", "FORWARD", "OUTPUT"):
        check(f"resets {chain} to ACCEPT",
              f"iptables -P {chain} ACCEPT" in src, "missing reset")
    i_flush = src.index("iptables -F")
    i_reset = src.index("iptables -P OUTPUT ACCEPT")
    i_fetch = src.index("Fetching GitHub IP ranges")
    check("reset comes after the flush", i_flush < i_reset)
    check("reset comes before the fetch", i_reset < i_fetch)


def test_task028_ac9_still_locks_down_at_the_end() -> None:
    """Regression guard: the reset must not have displaced the final DROP."""
    print("\n[task_028 AC9: fail-closed posture intact]")
    src = INIT_FIREWALL.read_text()
    i_reset = src.index("iptables -P OUTPUT ACCEPT")
    for chain in ("INPUT", "FORWARD", "OUTPUT"):
        check(f"re-establishes {chain} DROP",
              f"iptables -P {chain} DROP" in src[i_reset:], "missing DROP")
    check("final REJECT rule intact",
          "-j REJECT --reject-with icmp-admin-prohibited" in src)
    check("fail_closed trap still installed", "trap fail_closed EXIT" in src)
    check("trap installed after the source-only hook",
          src.index("VIBE_FIREWALL_SOURCE_ONLY") < src.index("trap fail_closed EXIT"))
    check("hard fetch failure still exits 1",
          "Failed to fetch usable GitHub IP ranges" in src)


def test_task028_ac10_changelog_entry_present() -> None:
    print("\n[task_028 AC10: CHANGELOG]")
    content = CHANGELOG_MD.read_text()
    check("CHANGELOG mentions the firewall self-heal fix",
          "init-firewall" in content and "self-heal" in content.lower(),
          "no task_028 entry")


def test_task014_ac1_sha1_helper() -> None:
    """AC1: vibe_workspace_sha1 — 40-char lowercase hex, deterministic,
    distinct for distinct inputs, exposed under VIBE_SOURCE_ONLY."""
    print("\n[task_014 AC1: vibe_workspace_sha1 helper]")
    r1 = _source_vibe_call({}, 'vibe_workspace_sha1 /Users/m/projA')
    check("[task014] AC1 helper exposed + exits 0", r1.returncode == 0, r1.stderr[:300])
    h1 = r1.stdout.strip()
    check("[task014] AC1a output length is exactly 40", len(h1) == 40, h1)
    check("[task014] AC1b output matches ^[0-9a-f]{40}$",
          re.fullmatch(r"[0-9a-f]{40}", h1) is not None, h1)
    r2 = _source_vibe_call({}, 'vibe_workspace_sha1 /Users/m/projA')
    check("[task014] AC1c same input twice -> identical output",
          r2.stdout.strip() == h1, r2.stdout)
    r3 = _source_vibe_call({}, 'vibe_workspace_sha1 /Users/m/projB')
    check("[task014] AC1d distinct inputs -> distinct outputs",
          r3.stdout.strip() != h1, r3.stdout)
    check("[task014] AC1 output equals reference sha1 of the exact path bytes",
          h1 == _t14_sha1("/Users/m/projA"), f"{h1} != {_t14_sha1('/Users/m/projA')}")


def test_task014_ac2_bind_path_helper() -> None:
    """AC2: vibe_projects_bind_path echoes $HOME/.vibe/projects/<sha1>,
    fully resolved (respects an overridden $HOME)."""
    print("\n[task_014 AC2: vibe_projects_bind_path helper]")
    with tempfile.TemporaryDirectory() as td:
        ws = "/Users/m/projA"
        r = _source_vibe_call({"HOME": td}, f'vibe_projects_bind_path {shlex.quote(ws)}')
        check("[task014] AC2 helper exposed + exits 0", r.returncode == 0, r.stderr[:300])
        expected = f"{td}/.vibe/projects/{_t14_sha1(ws)}"
        check("[task014] AC2 path is exactly $HOME/.vibe/projects/<sha1-of-workspace>",
              r.stdout.strip() == expected, f"{r.stdout.strip()} != {expected}")


def test_task014_ac3_mkdir_before_up_static() -> None:
    """AC3: static — the launcher mkdir -p's the per-project bind path (via
    vibe_projects_bind_path, assigned-then-passed) before `devcontainer up`."""
    print("\n[task_014 AC3: mkdir -p before devcontainer up (static)]")
    src = VIBE.read_text()
    assign = 'projects_dir="$(vibe_projects_bind_path "$workspace")"'
    check("[task014] AC3 bind path assigned from vibe_projects_bind_path",
          assign in src, "assignment not found")
    mkdir_call = 'mkdir -p "$projects_dir"'
    check("[task014] AC3 mkdir -p on the assigned bind path",
          mkdir_call in src, "mkdir not found")
    check("[task014] AC3 no bare $HOME/.vibe/projects/ mkdir (needs sha1 component)",
          'mkdir -p "$HOME/.vibe/projects/"' not in src
          and "mkdir -p $HOME/.vibe/projects/\n" not in src, "bare-prefix mkdir found")
    i_up = src.index("UP_BASE_ARGS=(")
    check("[task014] AC3 mkdir sits before UP_BASE_ARGS construction",
          src.index(mkdir_call) < i_up, "")
    check("[task014] AC3 override build (which runs the mkdir) precedes UP_BASE_ARGS",
          src.index("OVERRIDE_CONFIG=$(_build_override_config") < i_up, "")


def test_task014_ac4_override_always_exists() -> None:
    """AC4: with learning fully disabled (clean tmp HOME, no learning.config)
    the builder still renders a real override: 4 base mounts preserved verbatim
    + the projects bind object = 5 mounts."""
    print("\n[task_014 AC4: override JSON exists unconditionally]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        ws = tmp / "ws"; ws.mkdir()
        cfg = _t14_build(home, ws)
        base_mounts = json.loads(
            (REPO / "devcontainer" / "devcontainer.json").read_text())["mounts"]
        mounts = cfg.get("mounts", [])
        for bm in base_mounts:
            check(f"[task014] AC4 base mount preserved verbatim: {bm.split(',')[1]}",
                  bm in mounts, str(mounts))
        proj = next((m for m in mounts if isinstance(m, dict)
                     and m.get("target") == "/home/node/.claude/projects"), None)
        check("[task014] AC4 projects bind object present", proj is not None, str(mounts))
        if proj:
            expected_src = str(home / ".vibe" / "projects" / _t14_sha1(str(ws)))
            check("[task014] AC4 projects bind source is $HOME/.vibe/projects/<sha1>",
                  proj.get("source") == expected_src, str(proj))
            check("[task014] AC4 projects bind is type=bind",
                  proj.get("type") == "bind", str(proj))
            check("[task014] AC4 projects bind is rw (no readonly key)",
                  "readonly" not in proj, str(proj))
        check("[task014] AC4 exactly 5 mounts with /learnings disabled",
              len(mounts) == len(base_mounts) + 1, str(mounts))


def test_task014_ac5_compose_with_learnings() -> None:
    """AC5: learning enabled + valid path + no opt-out → override carries BOTH
    the projects bind AND the /learnings bind (readonly). 6 mounts. Exercises
    the FULL builder (gating via learning_should_mount), not the renderer."""
    print("\n[task_014 AC5: composition with /learnings enabled]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; (home / ".vibe").mkdir(parents=True)
        ws = tmp / "ws"; ws.mkdir()
        lib = tmp / "library"; lib.mkdir()
        (home / ".vibe" / "learning.config").write_text(
            f'VIBE_LEARNING_ENABLED="true"\nVIBE_LEARNING_PATH="{lib}"\n'
            'VIBE_LEARNING_VISIBILITY="private"\n')
        cfg = _t14_build(home, ws)
        mounts = cfg.get("mounts", [])
        obj = [m for m in mounts if isinstance(m, dict)]
        proj = next((m for m in obj if m.get("target") == "/home/node/.claude/projects"), None)
        learn = next((m for m in obj if m.get("target") == "/learnings"), None)
        check("[task014] AC5 projects bind present alongside /learnings",
              proj is not None, str(mounts))
        check("[task014] AC5 /learnings bind present", learn is not None, str(mounts))
        if learn:
            check("[task014] AC5 /learnings bind readonly",
                  learn.get("readonly") is True, str(learn))
            check("[task014] AC5 /learnings source is the configured library",
                  learn.get("source") == str(lib), str(learn))
        check("[task014] AC5 exactly 6 mounts with /learnings enabled",
              len(mounts) == 6, str(mounts))


def test_task014_ac6_learning_config_absent() -> None:
    """AC6 sub-case 1: no learning.config at all → projects bind present,
    no /learnings mount."""
    print("\n[task_014 AC6a: learning config absent]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        ws = tmp / "ws"; ws.mkdir()
        cfg = _t14_build(home, ws)
        tgts = [_t14_mount_target(m) for m in cfg.get("mounts", [])]
        check("[task014] AC6a projects bind present",
              "/home/node/.claude/projects" in tgts, str(tgts))
        check("[task014] AC6a no /learnings mount", "/learnings" not in tgts, str(tgts))


def test_task014_ac6_learning_disabled() -> None:
    """AC6 sub-case 2: VIBE_LEARNING_ENABLED="false" → projects bind present,
    no /learnings mount."""
    print("\n[task_014 AC6b: learning ENABLED=false]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; (home / ".vibe").mkdir(parents=True)
        ws = tmp / "ws"; ws.mkdir()
        lib = tmp / "library"; lib.mkdir()
        (home / ".vibe" / "learning.config").write_text(
            f'VIBE_LEARNING_ENABLED="false"\nVIBE_LEARNING_PATH="{lib}"\n')
        cfg = _t14_build(home, ws)
        tgts = [_t14_mount_target(m) for m in cfg.get("mounts", [])]
        check("[task014] AC6b projects bind present",
              "/home/node/.claude/projects" in tgts, str(tgts))
        check("[task014] AC6b no /learnings mount", "/learnings" not in tgts, str(tgts))


def test_task014_ac6_no_learn_marker() -> None:
    """AC6 sub-case 3: learning enabled globally but a .no-learn marker in the
    workspace → projects bind present, no /learnings mount."""
    print("\n[task_014 AC6c: .no-learn marker]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; (home / ".vibe").mkdir(parents=True)
        ws = tmp / "ws"; ws.mkdir()
        lib = tmp / "library"; lib.mkdir()
        (home / ".vibe" / "learning.config").write_text(
            f'VIBE_LEARNING_ENABLED="true"\nVIBE_LEARNING_PATH="{lib}"\n')
        (ws / ".no-learn").touch()
        cfg = _t14_build(home, ws)
        tgts = [_t14_mount_target(m) for m in cfg.get("mounts", [])]
        check("[task014] AC6c projects bind present despite opt-out",
              "/home/node/.claude/projects" in tgts, str(tgts))
        check("[task014] AC6c no /learnings mount", "/learnings" not in tgts, str(tgts))


def test_task014_ac7_mount_order() -> None:
    """AC7: the /home/node/.claude volume entry (string format) indexes
    strictly below the /home/node/.claude/projects bind (object format), so
    the bind nests on top of the mounted volume. Parses BOTH entry formats."""
    print("\n[task_014 AC7: mount order — volume before nested bind]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        ws = tmp / "ws"; ws.mkdir()
        cfg = _t14_build(home, ws)
        tgts = [_t14_mount_target(m) for m in cfg.get("mounts", [])]
        check("[task014] AC7 /home/node/.claude volume entry found (string parse works)",
              "/home/node/.claude" in tgts, str(tgts))
        check("[task014] AC7 projects bind entry found",
              "/home/node/.claude/projects" in tgts, str(tgts))
        if "/home/node/.claude" in tgts and "/home/node/.claude/projects" in tgts:
            check("[task014] AC7 volume index strictly below projects-bind index",
                  tgts.index("/home/node/.claude") < tgts.index("/home/node/.claude/projects"),
                  str(tgts))


def test_task014_ac8_hash_determinism() -> None:
    """AC8: two distinct workspace paths → distinct bind dirs; the same path
    twice → the same bind dir."""
    print("\n[task_014 AC8: bind-dir determinism]")
    with tempfile.TemporaryDirectory() as td:
        env = {"HOME": td}
        a1 = _source_vibe_call(env, 'vibe_projects_bind_path /Users/m/projA').stdout.strip()
        a2 = _source_vibe_call(env, 'vibe_projects_bind_path /Users/m/projA').stdout.strip()
        b = _source_vibe_call(env, 'vibe_projects_bind_path /Users/m/projB').stdout.strip()
        check("[task014] AC8 same path -> same bind dir", a1 == a2 and a1 != "", f"{a1} vs {a2}")
        check("[task014] AC8 distinct paths -> distinct bind dirs", a1 != b, f"{a1} vs {b}")


def test_task014_bind_dir_created() -> None:
    """Mechanism 3: building the override creates the per-project host dir
    (idempotently) with owner-only permissions."""
    print("\n[task_014: bind dir created on build]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home = tmp / "home"; home.mkdir()
        ws = tmp / "ws"; ws.mkdir()
        _t14_build(home, ws)
        bind_dir = home / ".vibe" / "projects" / _t14_sha1(str(ws))
        check("[task014] bind dir exists after build", bind_dir.is_dir(), str(bind_dir))
        check("[task014] bind dir is chmod 700",
              (bind_dir.stat().st_mode & 0o777) == 0o700, oct(bind_dir.stat().st_mode))
        # Idempotent across a second build.
        _t14_build(home, ws)
        check("[task014] second build is idempotent (dir still there)",
              bind_dir.is_dir(), str(bind_dir))


def test_task014_ac14_no_cksum_in_builder() -> None:
    """AC14: _build_override_config's body carries no cksum fallback any more —
    it derives its run-dir sha1 from vibe_workspace_sha1 (the same helper that
    names the bind dir), so the two hashes can never diverge."""
    print("\n[task_014 AC14: cksum removed from _build_override_config]")
    src = VIBE.read_text()
    body = src.split("_build_override_config() {", 1)[1].split("\n}", 1)[0]
    check("[task014] AC14 no cksum token in _build_override_config",
          "cksum" not in body, "cksum still present")
    check("[task014] AC14 builder calls vibe_workspace_sha1",
          "vibe_workspace_sha1" in body, "helper not called")
    check("[task014] AC14 builder calls vibe_projects_bind_path",
          "vibe_projects_bind_path" in body, "bind-path helper not called")


def test_task014_projects_bind_mount_drift() -> None:
    """Drift comparator: a pre-existing container without (or with a stale)
    /home/node/.claude/projects bind must trigger a recreate; a matching bind
    or no container must not."""
    print("\n[task_014: projects-bind mount drift comparator]")

    desired = "/Users/m/.vibe/projects/" + _t14_sha1("/Users/m/projA")

    def drift(actual: str) -> str:
        r = _source_vibe_call(
            {}, f'printf "%s" "$(projects_bind_mount_drift {shlex.quote(desired)} {shlex.quote(actual)})"')
        check("[task014] drift comparator exits 0", r.returncode == 0, r.stderr[:300])
        return r.stdout.strip()

    matching = (f"/workspace\t/Users/m/projA\trw\n"
                f"/home/node/.claude\t/var/lib/docker/volumes/vibe-claude-config/_data\trw\n"
                f"/home/node/.claude/projects\t{desired}\trw\n")
    check("[task014] matching bind -> no drift", drift(matching) == "", "")
    check("[task014] no container sentinel -> no drift", drift("NONE") == "", "")
    check("[task014] pre-task_014 container (bind absent) -> drift",
          drift("/workspace\t/Users/m/projA\trw\n"
                "/home/node/.claude\t/var/lib/docker/volumes/vibe-claude-config/_data\trw\n") == "1", "")
    check("[task014] bind source moved -> drift",
          drift(matching.replace(desired + "\trw", "/Users/m/.vibe/projects/other\trw")) == "1", "")
    check("[task014] bind flipped to ro -> drift",
          drift(matching.replace(desired + "\trw", desired + "\tro")) == "1", "")
    # Wiring: the launch flow folds projects_drift into remove_existing_flag.
    src = VIBE.read_text()
    check("[task014] launch flow computes projects_bind_mount_drift",
          'projects_drift="$(projects_bind_mount_drift "$(vibe_projects_bind_path "$WORKSPACE")" "$actual_mounts")"' in src, "")
    check("[task014] projects_drift feeds remove_existing_flag",
          '${drift_marker}${mount_drift}${projects_drift}' in src, "")
