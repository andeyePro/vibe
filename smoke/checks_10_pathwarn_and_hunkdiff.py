from smoke._core import *  # noqa: F401,F403




def test_task023_ac3_block_fires_range_under_pathwarn() -> None:
    """AC3: same via --range (already block-tier — also pins that path-warn
    never accidentally RAISES a tier)."""
    print("\n[task_023 AC3: BLOCK still fires under path-warn — range]")
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:fixtures/*\n")
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "secret.txt").write_text("base\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        (repo / "fixtures" / "secret.txt").write_text(f"leaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "add secret"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)
        check("[task_023 AC3 range] exit 1", r.returncode == 1, r.stderr)
        check("[task_023 AC3 range] BLOCK finding present", "BLOCK" in r.stderr, r.stderr)


def test_task023_ac3b_no_ere_double_parse_fullline_literal() -> None:
    """AC3b: with path-warn:smoke-test.py in the allowlist, a BLOCK secret
    staged in a NON-matching file on a line that also contains the literal
    text 'smoke-test.py' still fires — proving the glob remainder never
    reaches grep -E as a content pattern (it would otherwise act as a live
    literal-substring suppressor for ANY finding, including BLOCK, on any
    line merely mentioning the filename)."""
    print("\n[task_023 AC3b: no ERE double-parse — literal 'smoke-test.py' on the flagged line]")
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:smoke-test.py\n")
        (repo / "other.txt").write_text(f"see smoke-test.py for the leaked {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC3b fullline] exit 1 (not suppressed)", r.returncode == 1, r.stderr)
        check("[task_023 AC3b fullline] BLOCK finding present", "BLOCK" in r.stderr, r.stderr)


def test_task023_ac3b_no_ere_double_parse_stripped_prefix_literal() -> None:
    """AC3b variant: the flagged line contains the literal text
    'path-warn:smoke-test.py' (the WHOLE entry, prefix included) — still
    fires. Covers both the glob-remainder-as-ERE and whole-line-as-ERE
    failure modes."""
    print("\n[task_023 AC3b: no ERE double-parse — literal 'path-warn:smoke-test.py' on the flagged line]")
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:smoke-test.py\n")
        (repo / "other.txt").write_text(f"entry is path-warn:smoke-test.py leaked {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC3b stripped] exit 1 (not suppressed)", r.returncode == 1, r.stderr)
        check("[task_023 AC3b stripped] BLOCK finding present", "BLOCK" in r.stderr, r.stderr)


def test_task023_ac3c_range_idempotent_with_and_without_pathwarn() -> None:
    """AC3c: --range output is byte-identical with and without path-warn
    entries present in the allowlist — tier demotion is a one-way floor and
    --range is already block-tier, so path-warn entries must be a pure
    no-op there (regression-pins the floor property)."""
    print("\n[task_023 AC3c: --range idempotency with/without path-warn entries]")
    ip = _t23_ip()
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "f.txt").write_text("base\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        (repo / "fixtures" / "f.txt").write_text(f"Server ip {ip} today, leaked {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "dirty"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        r_without = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)

        (repo / ".vibe-content-allow").write_text("path-warn:fixtures/*\n")
        r_with = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)

        check("[task_023 AC3c] exit codes match", r_without.returncode == r_with.returncode,
              f"{r_without.returncode} vs {r_with.returncode}")
        check("[task_023 AC3c] stderr byte-identical",
              r_without.stderr == r_with.stderr,
              f"without={r_without.stderr!r} with={r_with.stderr!r}")


def test_task023_ac4_message_mode_unaffected_by_pathwarn() -> None:
    """AC4: --message output is byte-identical whether or not path-warn
    entries are present in the allowlist — no file path exists in this
    mode, so path-warn must be invisible there."""
    print("\n[task_023 AC4: --message unaffected by path-warn entries]")
    ip = _t23_ip()
    with tempfile.TemporaryDirectory() as td:
        msg_file = Path(td) / "msg.txt"
        msg_file.write_text(f"Server ip {ip} today, mentions smoke-test.py and .vs/spec.md\n")
        r_without = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        (Path(td) / ".vibe-content-allow").write_text("path-warn:*\n")
        r_with = run(["bash", str(VIBE_CONTENT_SCANNER), "--message", str(msg_file)], cwd=td)
        check("[task_023 AC4 message] byte-identical stderr",
              r_without.stderr == r_with.stderr, f"{r_without.stderr!r} vs {r_with.stderr!r}")
        check("[task_023 AC4 message] byte-identical exit code",
              r_without.returncode == r_with.returncode, "")


def test_task023_ac4_blob_stdin_unaffected_by_pathwarn() -> None:
    """AC4: same parity check for --blob-stdin."""
    print("\n[task_023 AC4: --blob-stdin unaffected by path-warn entries]")
    ip = _t23_ip_alt()
    stream = f"commit deadbeefcafefeedfacefeeddeadbeefcafefeed\n+Server ip {ip} today\n"
    with tempfile.TemporaryDirectory() as td:
        r_without = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        (Path(td) / ".vibe-content-allow").write_text("path-warn:*\n")
        r_with = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        check("[task_023 AC4 blob-stdin] byte-identical stderr",
              r_without.stderr == r_with.stderr, f"{r_without.stderr!r} vs {r_with.stderr!r}")
        check("[task_023 AC4 blob-stdin] byte-identical exit code",
              r_without.returncode == r_with.returncode, "")


def test_task023_ac4_messages_stdin_unaffected_by_pathwarn() -> None:
    """AC4: same parity check for --messages-stdin."""
    print("\n[task_023 AC4: --messages-stdin unaffected by path-warn entries]")
    ip = _t23_ip()
    sha = "3333333333333333333333333333333333cccc"
    stream = sha.encode() + b"\nServer ip " + ip.encode() + b" today\x00"
    with tempfile.TemporaryDirectory() as td:
        r_without = subprocess.run(["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
                                    input=stream, capture_output=True, cwd=td)
        (Path(td) / ".vibe-content-allow").write_text("path-warn:*\n")
        r_with = subprocess.run(["bash", str(VIBE_CONTENT_SCANNER), "--messages-stdin"],
                                 input=stream, capture_output=True, cwd=td)
        check("[task_023 AC4 messages-stdin] byte-identical stderr",
              r_without.stderr == r_with.stderr, f"{r_without.stderr!r} vs {r_with.stderr!r}")
        check("[task_023 AC4 messages-stdin] byte-identical exit code",
              r_without.returncode == r_with.returncode, "")


def test_task023_ac4_identity_unaffected_by_pathwarn() -> None:
    """AC4: same parity check for --identity."""
    print("\n[task_023 AC4: --identity unaffected by path-warn entries]")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        run(["git", "config", "user.email", "real" + "@" + "example.com"], cwd=repo)
        r_without = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        (repo / ".vibe-content-allow").write_text("path-warn:*\n")
        r_with = run(["bash", str(VIBE_CONTENT_SCANNER), "--identity"], cwd=repo)
        check("[task_023 AC4 identity] byte-identical stderr",
              r_without.stderr == r_with.stderr, f"{r_without.stderr!r} vs {r_with.stderr!r}")
        check("[task_023 AC4 identity] byte-identical exit code",
              r_without.returncode == r_with.returncode, "")


def test_task023_ac5_self_clean_fixture_simulation() -> None:
    """AC5: fixture-repo simulation of vibe's own tree shape with the
    shipped path-warn entries — staging WARN-class example literals in a
    .vs/*-shaped file and a smoke-test.py-shaped file produces NO findings
    and exit 0 (no override needed); planting a runtime-built secret in
    EACH of those same files still exits 1 with BLOCK findings located in
    both files."""
    print("\n[task_023 AC5: self-clean end-to-end fixture simulation]")
    ip = _t23_ip()
    email = _t23_email()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text(
            "path-warn:.vs/*\npath-warn:smoke-test.py\n"
        )
        (repo / ".vs").mkdir()
        (repo / ".vs" / "spec.md").write_text(f"Example WARN IP: {ip}\n")
        (repo / "smoke-test.py").write_text(f"# fixture literal: {email}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC5 clean] exit 0", r.returncode == 0, r.stderr)
        check("[task_023 AC5 clean] no findings, no override needed", len(r.stderr.strip()) == 0, r.stderr)
        run(["git", "commit", "-m", "clean baseline"], cwd=repo)

        token1 = _t23_ghp()
        token2 = "AKIA" + "D" * 16
        (repo / ".vs" / "spec.md").write_text(f"Example WARN IP: {ip}\nleaked: {token1}\n")
        (repo / "smoke-test.py").write_text(f"# fixture literal: {email}\nleaked: {token2}\n")
        run(["git", "add", "-A"], cwd=repo)
        r2 = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        check("[task_023 AC5 secret] exit 1", r2.returncode == 1, r2.stderr)
        check("[task_023 AC5 secret] BLOCK finding present", "BLOCK" in r2.stderr, r2.stderr)
        findings = _task022_parse_findings(r2.stderr)
        check("[task_023 AC5 secret] BLOCK finding in .vs/spec.md",
              any(f[0] == "BLOCK" and f[1].startswith(".vs/spec.md:") for f in findings), str(findings))
        check("[task_023 AC5 secret] BLOCK finding in smoke-test.py",
              any(f[0] == "BLOCK" and f[1].startswith("smoke-test.py:") for f in findings), str(findings))


def test_task023_ac7_pathwarn_functions_no_forks() -> None:
    """AC7: the new path-warn glob-matching functions (load_path_warn_globs,
    file_is_path_warn) introduce no external-command invocation — bash
    case/pattern match only, same no-fork discipline as task_022's hot-path
    guard."""
    print("\n[task_023 AC7: path-warn functions have no forks]")
    src = VIBE_CONTENT_SCANNER.read_text(encoding="utf-8")
    forbidden_names = ["grep", "sed", "awk", "head", "cut", "tr"]
    for name in ["load_path_warn_globs", "file_is_path_warn"]:
        body = _task022_extract_function_body(src, name)
        bad = [n for n in forbidden_names if re.search(r'\b' + n + r'\b', body)]
        check(f"[task_023 AC7] {name}: no forbidden external-command names", bad == [], str(bad))
        check(f"[task_023 AC7] {name}: no $( command substitution", "$(" not in body, body)
        check(f"[task_023 AC7] {name}: no backtick command substitution", "`" not in body, body)


def test_task023_ac7_scan_diff_stream_still_shape_clean() -> None:
    """AC7: scan_diff_stream (which now calls file_is_path_warn per +++
    header) was not in task_022's original hot-path fork-check list —
    verify directly here that the per-file tier-demotion addition didn't
    introduce a fork on that path either."""
    print("\n[task_023 AC7: scan_diff_stream shape guard]")
    src = VIBE_CONTENT_SCANNER.read_text(encoding="utf-8")
    body = _task022_extract_function_body(src, "scan_diff_stream")
    forbidden_names = ["grep", "sed", "awk", "head", "cut", "tr"]
    bad = [n for n in forbidden_names if re.search(r'\b' + n + r'\b', body)]
    check("[task_023 AC7] scan_diff_stream: no forbidden external-command names", bad == [], str(bad))


def test_task023_pathwarn_star_repo_wide_accepted() -> None:
    """Design note: path-warn:* (repo-wide WARN-off) is ACCEPTED — same
    trust model as an already-possible overbroad ERE entry. Verify it
    behaves exactly as documented: suppresses WARN in every file at any
    depth, BLOCK still fires everywhere."""
    print("\n[task_023: path-warn:* repo-wide accepted]")
    ip = _t23_ip()
    token = _t23_ghp()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:*\n")
        (repo / "anywhere" / "deep").mkdir(parents=True)
        (repo / "anywhere" / "deep" / "f.txt").write_text(f"Server ip {ip} today\n")
        (repo / "top.txt").write_text(f"leaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_023 path-warn:*] exit 1 (BLOCK still fires)", r.returncode == 1, r.stderr)
        check("[task_023 path-warn:*] no WARN finding anywhere",
              all(f[0] != "WARN" for f in findings), str(findings))
        check("[task_023 path-warn:*] BLOCK finding present", any(f[0] == "BLOCK" for f in findings), str(findings))


def test_task023_glob_metachar_question_mark_semantics() -> None:
    """Glob metacharacter sanity: `?` matches exactly one character in a
    bash case-style pattern — path-warn:fixtures/?.txt suppresses WARN in
    fixtures/a.txt (one char) but NOT in fixtures/ab.txt (two chars),
    proving the glob is matched as a genuine case pattern, not a literal
    substring or an ERE."""
    print("\n[task_023: glob metacharacter ? semantics]")
    ip = _t23_ip_alt()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t23_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:fixtures/?.txt\n")
        (repo / "fixtures").mkdir()
        (repo / "fixtures" / "a.txt").write_text(f"Server ip {ip} today\n")
        (repo / "fixtures" / "ab.txt").write_text(f"Server ip {ip} today\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_023 glob ?] exit 1 (ab.txt still WARNs)", r.returncode == 1, r.stderr)
        check("[task_023 glob ?] a.txt (one char) suppressed",
              all(not f[1].startswith("fixtures/a.txt:") for f in findings), str(findings))
        check("[task_023 glob ?] ab.txt (two chars) still WARNs",
              any(f[1].startswith("fixtures/ab.txt:") for f in findings), str(findings))


def test_task024_ac1_spoof_neutralised_skip_state_staged() -> None:
    """AC1: an added line whose content is '++ /dev/null' (rendering
    '+++ /dev/null' inside a real hunk) does NOT set skip_file — a
    runtime-built BLOCK secret added in the SAME hunk right after it is
    still found, attributed to the correct real file path, exit 1. Staged
    variant. Pre-task_024 this spoof made the scanner treat the rest of the
    file as a deleted-file no-op, silently dropping the secret."""
    print("\n[task_024 AC1: ++ /dev/null skip-state spoof neutralised — staged]")
    token = _t24_ghp("A")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "secret.txt").write_text(f"++ /dev/null\nleaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC1 staged] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC1 staged] BLOCK finding attributed to secret.txt (correct path)",
              any(f[0] == "BLOCK" and f[1].startswith("secret.txt:") for f in findings), str(findings))
        check("[task_024 AC1 staged] exactly 1 finding (spoof line itself yields none)",
              len(findings) == 1, str(findings))


def test_task024_ac1_spoof_neutralised_skip_state_range() -> None:
    """AC1: same spoof via --range (block-tier, two committed shas)."""
    print("\n[task_024 AC1: ++ /dev/null skip-state spoof neutralised — range]")
    token = _t24_ghp("B")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "secret.txt").write_text("base\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        (repo / "secret.txt").write_text(f"base\n++ /dev/null\nleaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "add spoof+secret"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC1 range] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC1 range] BLOCK finding attributed to secret.txt (correct path)",
              any(f[0] == "BLOCK" and f[1].startswith("secret.txt:") for f in findings), str(findings))
        check("[task_024 AC1 range] exactly 1 finding", len(findings) == 1, str(findings))


def test_task024_ac2_spoof_neutralised_tier_file_flip() -> None:
    """AC2: an added line whose content is '++ b/.vs/x' (rendering
    '+++ b/.vs/x' inside a real hunk of a NON-path-warn file) does not flip
    current_file/current_file_tier — a runtime-built WARN-class RFC1918 IP
    added right after it in the SAME hunk still fires, attributed to the
    REAL file. A path-warn:.vs/* allowlist entry is present specifically to
    prove the demotion-to-block-tier the spoof would have triggered (had it
    been misparsed as a real header) never happens."""
    print("\n[task_024 AC2: ++ b/.vs/x tier/file-flip spoof neutralised]")
    ip = _t24_ip(("192", "168", "44", "5"))
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / ".vibe-content-allow").write_text("path-warn:.vs/*\n")
        (repo / "notes.txt").write_text(f"++ b/.vs/x\nServer ip {ip} today\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC2] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC2] WARN finding attributed to notes.txt (real path, not .vs/x)",
              any(f[0] == "WARN" and f[1].startswith("notes.txt:") and f[2] == "rfc1918-ip"
                  for f in findings), str(findings))
        check("[task_024 AC2] no finding located in .vs/x (the spoofed path)",
              all(not f[1].startswith(".vs/x") for f in findings), str(findings))


def test_task024_ac3_spoofed_content_scanned_staged() -> None:
    """AC3: an added line whose content is '++ token: <ghp_ shape>'
    (rendering '+++ token: ghp_…') is itself scanned as content and fires
    BLOCK — the deliberate MORE-findings change. Same fixture set includes
    the forged-budget probe: an added line beginning literally
    '@@ -99,5 +99,5 @@' (rendering '+@@ …') is scanned as ordinary content
    (no finding of its own) and does NOT re-arm the hunk counters — proven
    by a SECOND file's real secret still being attributed to its own
    correct path afterward."""
    print("\n[task_024 AC3: spoofed content scanned as content — staged]")
    token1 = _t24_ghp("H")
    token2 = _t24_akia("N")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "spoofed.txt").write_text(
            f"++ token: {token1}\n"
            "@@ -99,5 +99,5 @@ trailing junk\n"
        )
        (repo / "zzz_real.txt").write_text(f"leaked: {token2}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC3 staged] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC3 staged] BLOCK finding(s) in spoofed.txt for the spoofed token",
              any(f[0] == "BLOCK" and f[1].startswith("spoofed.txt:") for f in findings), str(findings))
        check("[task_024 AC3 staged] BLOCK finding in zzz_real.txt (correct attribution AFTER the forged-budget probe)",
              any(f[0] == "BLOCK" and f[1].startswith("zzz_real.txt:") for f in findings), str(findings))
        check("[task_024 AC3 staged] no finding attributed to a bogus '99' line/location from the forged header",
              all(":99" not in f[1] for f in findings), str(findings))


def test_task024_ac3_spoofed_content_scanned_blob_stdin() -> None:
    """AC3: same spoof + forged-budget probe via --blob-stdin, where the
    OLD parser dropped a '+++ token: …'-shaped added line entirely as
    header noise (never scanned at all). Hand-built stream, single hunk
    with declared budget new_remaining=2 consumed exactly by the two added
    lines."""
    print("\n[task_024 AC3: spoofed content scanned as content — blob-stdin]")
    token1 = _t24_ghp("H")
    stream = (
        "commit deadbeefcafefeedfacefeeddeadbeefcafefeed\n"
        "diff --git a/x b/x\n"
        "--- a/x\n"
        "+++ b/x\n"
        "@@ -0,0 +1,2 @@\n"
        f"+++ token: {token1}\n"
        "+@@ -99,5 +99,5 @@ trailing junk\n"
    )
    with tempfile.TemporaryDirectory() as td:
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC3 blob-stdin] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC3 blob-stdin] BLOCK finding present for the spoofed content",
              any(f[0] == "BLOCK" for f in findings), str(findings))
        check("[task_024 AC3 blob-stdin] finding attributed to the commit (old parser dropped this line entirely)",
              any(f[1] == "commit deadbeefcafefeedfacefeeddeadbeefcafefeed" for f in findings), str(findings))
        check("[task_024 AC3 blob-stdin] forged-budget probe line produced no finding of its own "
              "(exactly the github-pat + secret-assignment pair from the token line, nothing extra)",
              {f[2] for f in findings} <= {"github-pat", "secret-assignment"}, str(findings))


def test_task024_ac3b_zero_byte_context_line_suppressblankempty() -> None:
    """AC3b (the Spec Critic's live exploit): a two-file
    `git -c diff.suppressBlankEmpty=true diff -U3` stream where file A's
    hunk contains a genuinely zero-byte (no leading space) blank context
    line, followed by file B adding a runtime-built BLOCK secret. Without
    the empty-line-decrements-both rule, one unit of hunk budget leaks per
    side and the parser is still (falsely) "inside" file A's hunk when file
    B's real headers arrive — swallowing them as fake content instead of
    recognising them as headers. Asserts the secret is found, exit 1, and
    attributed to the SAME commit the fixture actually used (scan_blob_stdin
    tracks commit-level location only, not per-file paths — this fixture
    exercises the exact repro from the spec's Critic, at commit
    granularity, which is the attribution unit this parser has)."""
    print("\n[task_024 AC3b: zero-byte suppressBlankEmpty context-line exploit]")
    token = _t24_ghp("Z")
    sha = "cafed00dcafed00dcafed00dcafed00dcafed00"
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "fileA.txt").write_text("A\nB\nC\n\nD\nE\n")
        (repo / "fileB.txt").write_text("secretfile\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "setup"], cwd=repo)
        (repo / "fileA.txt").write_text("A\nB\nCHANGED\n\nD\nE\n")
        (repo / "fileB.txt").write_text(f"secretfile\n{token}\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "trigger"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        diffout = run(["git", "-c", "diff.suppressBlankEmpty=true", "diff", "-U3", "--no-color",
                       f"{sha2}~1", sha2, "--", "fileA.txt", "fileB.txt"], cwd=repo).stdout
        # A zero-byte context line must actually be present (no leading space) —
        # pin the fixture's own shape before trusting the scanner's verdict on it.
        check("[task_024 AC3b] fixture genuinely contains a zero-byte context line",
              "\n\n" in diffout, repr(diffout))
        stream = f"commit {sha}\n" + diffout
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC3b] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC3b] BLOCK github-pat finding present",
              any(f[0] == "BLOCK" and f[2] == "github-pat" for f in findings), str(findings))
        check("[task_024 AC3b] finding correctly attributed to the commit (budget did not leak across the file boundary)",
              any(f[1] == f"commit {sha}" for f in findings), str(findings))
        check("[task_024 AC3b] exactly one BLOCK finding (no duplicate/misfired scans from a leaked window)",
              len([f for f in findings if f[0] == "BLOCK"]) == 1, str(findings))


def test_task024_ac4_deleted_line_forgery_two_line_dance() -> None:
    """AC4: a hunk deleting a line whose content is '-- a/x' (rendering
    '--- a/x') immediately followed by an added line '++ b/evil' (rendering
    '+++ b/evil') — the two-line dance that defeats a naive "header must
    follow --- " rule — does NOT flip current_file. A real secret added
    later in the SAME staged change stays attributed to the real file
    (orig.txt), never to 'evil'."""
    print("\n[task_024 AC4: deleted-line + added-line two-line dance bounded]")
    token = _t24_ghp("E")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "orig.txt").write_text("keep1\n-- a/x\nkeep2\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        (repo / "orig.txt").write_text(f"keep1\n++ b/evil\nkeep2\nleaked: {token}\n")
        run(["git", "add", "-A"], cwd=repo)
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC4] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC4] BLOCK finding attributed to orig.txt (current_file never flipped to evil)",
              any(f[0] == "BLOCK" and f[1].startswith("orig.txt:") for f in findings), str(findings))
        check("[task_024 AC4] no finding attributed to a file named evil",
              all("evil" not in f[1] for f in findings), str(findings))


def test_task024_ac5_real_headers_corpus_frozen_findings() -> None:
    """AC5: a real multi-shape corpus (file boundary, new file via
    '--- /dev/null', deleted file via '+++ /dev/null' with a non-secret
    decoy string that must never be scanned, multiple hunks in one file,
    -U0 zero-count hunks with EXPLICIT ',0' on both the old side
    (zerocount_del.txt, a pure deletion: '@@ -1,3 +0,0 @@') and the new
    side (insertonly.txt, a pure insertion: '@@ -1,0 +2,2 @@'), a
    '\\ No newline at end of file' annotation, a BINARY-file section
    ('Binary files … differ', no @@ at all), and a mode-change-only section
    ('old mode'/'new mode', no hunks)) parses via --range EXACTLY as
    before: pinned exact finding set, no crash, no misattribution. This is
    the freeze half of AC5 — the differential against the OLD scanner on
    this exact corpus is a one-off, logged separately."""
    print("\n[task_024 AC5: real-header corpus — frozen findings via --range]")
    token = _t24_ghp("K")
    ip = _t24_ip(("192", "168", "77", "9"))
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "modme.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\n")
        (repo / "todelete.txt").write_text("some content\nleaked-like-marker\n")
        (repo / "modechange.txt").write_text("static content\n")
        (repo / "nonewline.txt").write_text("content without trailing newline")
        (repo / "zerocount_del.txt").write_text("line1\nline2\nline3\n")
        (repo / "insertonly.txt").write_text("start\nend\n")
        (repo / "binaryfile.bin").write_bytes(b"BIN\x00DATA\x01\x02")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        sha1 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        (repo / "modme.txt").write_text(
            f"one\nTWO-CHANGED\nthree\nfour\nfive\nsix\nSEVEN-CHANGED {token}\neight\n"
        )
        run(["git", "rm", "-q", "todelete.txt"], cwd=repo)
        (repo / "modechange.txt").chmod(0o755)
        (repo / "nonewline.txt").write_text("content still no trailing newline CHANGED")
        (repo / "zerocount_del.txt").write_text("")
        (repo / "insertonly.txt").write_text("start\nNEWLINE1\nNEWLINE2\nend\n")
        (repo / "binaryfile.bin").write_bytes(b"BIN\x00DATA-CHANGED\x01\x02\x03")
        (repo / "newfile.txt").write_text(f"Server ip {ip} today\n")
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "second"], cwd=repo)
        sha2 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--range", sha1, sha2], cwd=repo)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC5] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC5] exactly 1 finding (--range is block-tier only; the WARN in newfile.txt is skipped)",
              len(findings) == 1, str(findings))
        check("[task_024 AC5] BLOCK github-pat in modme.txt at the SECOND hunk's real line (multi-hunk attribution)",
              findings == [("BLOCK", "modme.txt:7", "github-pat", token)], str(findings))

        # Same corpus via --staged (both-tier) additionally proves the new-file
        # WARN fires and the deleted-file decoy string never gets scanned.
        r2 = run(["bash", str(VIBE_CONTENT_SCANNER), "--staged"], cwd=repo)
        findings2 = _task022_parse_findings(r2.stderr)
        check("[task_024 AC5 staged-tier] no finding ever attributed to todelete.txt (deleted file skipped)",
              all(not f[1].startswith("todelete.txt") for f in findings2), str(findings2))
        check("[task_024 AC5 staged-tier] no finding from modechange.txt/binaryfile.bin/nonewline.txt/zerocount_del.txt",
              all(not any(f[1].startswith(p) for p in
                          ("modechange.txt", "binaryfile.bin", "nonewline.txt", "zerocount_del.txt"))
                  for f in findings2), str(findings2))


def test_task024_ac7_context_lines_u3_handled_blob_stdin() -> None:
    """AC7: a git-log--p-style fixture (default U3 context) confirms a
    context line decrements BOTH counters and is NEVER scanned — a
    WARN-shaped RFC1918 IP planted on an UNCHANGED context line produces no
    finding, while a genuine secret on the adjacent ADDED line in the same
    hunk still fires. Unchanged behaviour: only '+' lines are scanned."""
    print("\n[task_024 AC7: U3 context lines decrement both, not scanned]")
    token = _t24_ghp("Y")
    ip = _t24_ip(("192", "168", "9", "9"))
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _t24_init_repo(repo)
        (repo / "f.txt").write_text(
            f"line1\nContext with ip {ip} here\nline3\nline4\nline5\nline6\nline7\n"
        )
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "base"], cwd=repo)
        (repo / "f.txt").write_text(
            f"line1\nContext with ip {ip} here\nCHANGED3 {token}\nline4\nline5\nline6\nline7\n"
        )
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", "second"], cwd=repo)
        logout = run(["git", "log", "-p", "-1", "--no-color", "--", "f.txt"], cwd=repo).stdout
        check("[task_024 AC7] fixture's hunk genuinely carries U3 context (leading-space) lines",
              "\n Context with ip" in logout, repr(logout))
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=logout)
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC7] exit 1", r.returncode == 1, r.stderr)
        check("[task_024 AC7] exactly one finding — the added-line secret",
              len(findings) == 1 and findings[0][0] == "BLOCK" and findings[0][2] == "github-pat",
              str(findings))
        check("[task_024 AC7] no WARN finding from the context line's IP (context never scanned)",
              all(f[0] != "WARN" for f in findings), str(findings))


def test_task024_ac8_malformed_hunk_header_failsafe() -> None:
    """AC8: a malformed '@@ -abc,def +xyz @@' header (non-numeric counts)
    and a truncated '@@ -5,' header (no closing '@@', no new-side count) —
    neither crashes the scanner (no set -e death, exit stays 0/1) nor
    wedges it "inside" a hunk (lines following each malformed header, which
    are outside any hunk at that point, are harmless). A real, well-formed
    hunk header AFTER both malformed lines is classified as a header again
    and a genuine secret inside IT is found and correctly reported — proof
    that header classification resumed, not more content wrongly consumed
    from a phantom unbounded hunk."""
    print("\n[task_024 AC8: malformed @@ header fail-safe]")
    token = _t24_ghp("D")
    stream = (
        "commit deadbeefcafefeedfacefeeddeadbeefcafefeed\n"
        "diff --git a/x b/x\n"
        "--- a/x\n"
        "+++ b/x\n"
        "@@ -abc,def +xyz @@\n"
        "+harmless added line, no secret here\n"
        "diff --git a/y b/y\n"
        "--- a/y\n"
        "+++ b/y\n"
        "@@ -5,\n"
        "+another harmless line\n"
        "diff --git a/z b/z\n"
        "--- a/z\n"
        "+++ b/z\n"
        "@@ -1,1 +1,1 @@\n"
        "-old real content\n"
        f"+leaked {token}\n"
    )
    with tempfile.TemporaryDirectory() as td:
        r = run(["bash", str(VIBE_CONTENT_SCANNER), "--blob-stdin"], cwd=td, input=stream)
        check("[task_024 AC8] no crash: exit code is 0 or 1, not a bash/set -e death",
              r.returncode in (0, 1), f"rc={r.returncode} stderr={r.stderr!r}")
        findings = _task022_parse_findings(r.stderr)
        check("[task_024 AC8] exit 1 (the real secret after the malformed headers is found)",
              r.returncode == 1, r.stderr)
        check("[task_024 AC8] exactly one finding: the real secret, nothing from either malformed-header region",
              findings == [("BLOCK", "commit deadbeefcafefeedfacefeeddeadbeefcafefeed", "github-pat", token)],
              str(findings))


def test_task024_ac8_new_hunk_logic_no_forks_in_scan_blob_stdin() -> None:
    """AC8/design: the new per-hunk count-parsing + inside-hunk
    classification logic added to scan_blob_stdin introduces no external-
    command invocation (task_022's no-fork hot-path discipline extended to
    the new logic). scan_blob_stdin retains ONE pre-existing, documented,
    out-of-scope fork (the 'commit ' header's trailing-annotation trim via
    `awk '{print $1}'`, predating task_024) — this test excludes exactly
    that one known line and asserts the REMAINDER of the function body is
    fork-free, so a fork silently reappearing in the new counting/
    classification code would be caught."""
    print("\n[task_024 AC8: no forks in scan_blob_stdin's new hunk-parsing logic]")
    src = VIBE_CONTENT_SCANNER.read_text(encoding="utf-8")
    body = _task022_extract_function_body(src, "scan_blob_stdin")
    lines = [ln for ln in body.splitlines() if "awk '{print $1}'" not in ln]
    remainder = "\n".join(lines)
    forbidden_names = ["grep", "sed", "awk", "head", "cut", "tr"]
    bad = [n for n in forbidden_names if re.search(r'\b' + n + r'\b', remainder)]
    check("[task_024 AC8] scan_blob_stdin (minus the one documented pre-existing awk line): "
          "no forbidden external-command names", bad == [], str(bad))
    check("[task_024 AC8] the one documented pre-existing awk line is actually still there "
          "(proves the exclusion above is discriminating, not accidentally matching nothing)",
          "awk '{print $1}'" in body, body)


def test_task024_ac10_changelog_entry_present() -> None:
    """AC10: CHANGELOG.md carries a 2026-07-17 task_024 entry documenting
    the hunk-aware fix (bookkeeping half of AC10 — same commit as the code
    change per repo convention)."""
    print("\n[task_024 AC10: CHANGELOG.md entry present]")
    check("[task_024 AC10] CHANGELOG.md exists", CHANGELOG_MD.exists(), str(CHANGELOG_MD))
    if CHANGELOG_MD.exists():
        c = CHANGELOG_MD.read_text(encoding="utf-8")
        check("[task_024 AC10] CHANGELOG.md mentions task_024", "task_024" in c, "")
        check("[task_024 AC10] CHANGELOG.md mentions hunk-aware parsing", "hunk-aware" in c, "")


def test_task024_ac10_todo_hardening_item_ticked() -> None:
    """AC10: the 2026-07-17 TODO.md hardening item this task exists to
    close ('harden scan_diff_stream against added-line header spoofing')
    must be ticked off ([x]) or removed — an open '- [ ]' entry describing
    work this very task just landed is a stale backlog item that will
    confuse a future maintainer into re-doing it."""
    print("\n[task_024 AC10: TODO.md hardening item ticked/removed]")
    todo_md = REPO / "TODO.md"
    check("[task_024 AC10] TODO.md exists", todo_md.exists(), str(todo_md))
    if todo_md.exists():
        t = todo_md.read_text(encoding="utf-8")
        open_marker = "- [ ] **content-guard scanner: harden `scan_diff_stream` against added-line header spoofing**"
        check("[task_024 AC10] the hardening item is no longer open ('- [ ]') in TODO.md — "
              "either ticked to [x] or removed entirely now that task_024 has landed the fix",
              open_marker not in t, "still present as an open TODO item" if open_marker in t else "")


def test_task026_ac1_arg_parsing_too_many() -> None:
    print("\n[task_026 AC1: vibe pat a b c — too many args]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        script = f"set -e; source {shlex.quote(str(VIBE))}; pat_handle_subcommand pat a b c"
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, r.stderr)
        check("error on stderr", "Usage:" in r.stderr, r.stderr)
        check("no stdout", r.stdout == "", r.stdout)


def test_task026_ac1_arg_parsing_invalid_slug() -> None:
    print("\n[task_026 AC1: vibe pat not-a-slug — invalid slug]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        script = f"set -e; source {shlex.quote(str(VIBE))}; pat_handle_subcommand pat not-a-slug"
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, r.stderr)
        check("error on stderr", "isn't a valid owner/repo slug" in r.stderr, r.stderr)


def test_task026_ac1_arg_parsing_help() -> None:
    print("\n[task_026 AC1: vibe pat --help]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        script = f"source {shlex.quote(str(VIBE))}; pat_handle_subcommand pat --help"
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("usage on stdout", "Usage:" in r.stdout, r.stdout)
        check("mentions HOST shell", "HOST shell" in r.stdout, r.stdout)


def test_task026_ac2_token_overwrite_existing() -> None:
    print("\n[task_026 AC2: overwrite existing token]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        # Pre-populate token store with an existing token and other keys
        tokens_file = tmp / ".vibe" / "tokens"
        tokens_file.parent.mkdir(parents=True)
        tokens_file.write_text("owner/repo=ghp_old_token\nZOTERO_API_KEY=zotero123=\nOPENPROJECT_MCP_BEARER=proj123=\n")
        tokens_file.chmod(0o600)

        script = f"""
set +e
source {shlex.quote(str(VIBE))}
echo ghp_task026_fixture_token | rotate_token owner/repo
set -e
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 0", r.returncode == 0, r.stderr)
        check("first line is Repo:", "Repo: owner/repo" in r.stdout, r.stdout)
        check("second line mentions existing token", "stored token found" in r.stdout, r.stdout)
        check("✓ Token saved in stdout", "✓ Token saved" in r.stdout, r.stdout)

        # Verify token store was updated correctly
        new_content = tokens_file.read_text()
        check("new token saved", "owner/repo=ghp_task026_fixture_token" in new_content, new_content)
        check("other keys preserved", "ZOTERO_API_KEY=zotero123=" in new_content, new_content)
        check("other keys preserved (openproject)", "OPENPROJECT_MCP_BEARER=proj123=" in new_content, new_content)
        check("file still chmod 600", oct(tokens_file.stat().st_mode)[-3:] == "600",
              oct(tokens_file.stat().st_mode))
        check("fixture token absent from process stdout+stderr", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_ac3_empty_input_eof() -> None:
    print("\n[task_026 AC3: empty input — EOF (closed stdin)]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        tokens_file = tmp / ".vibe" / "tokens"
        tokens_file.parent.mkdir(parents=True)
        tokens_file.write_text("owner/repo=ghp_existing\n")
        orig_content = tokens_file.read_text()

        script = f"""
source {shlex.quote(str(VIBE))}
rotate_token owner/repo < /dev/null
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, f"returncode={r.returncode}")
        check("abort message on stderr", "aborted — token store unchanged" in r.stderr, r.stderr)
        check("token store unchanged", tokens_file.read_text() == orig_content,
              f"before: {orig_content}, after: {tokens_file.read_text()}")


def test_task026_ac3_empty_input_newline() -> None:
    print("\n[task_026 AC3: empty input — lone newline]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        tokens_file = tmp / ".vibe" / "tokens"
        tokens_file.parent.mkdir(parents=True)
        tokens_file.write_text("owner/repo=ghp_existing\n")
        orig_content = tokens_file.read_text()

        script = f"""
source {shlex.quote(str(VIBE))}
rotate_token owner/repo <<< ""
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, f"returncode={r.returncode}")
        check("abort message on stderr", "aborted — token store unchanged" in r.stderr, r.stderr)
        check("token store unchanged", tokens_file.read_text() == orig_content,
              f"before: {orig_content}, after: {tokens_file.read_text()}")


def test_task026_ac4_auto_detect_repo_no_git() -> None:
    print("\n[task_026 AC4: auto-detect repo with no git checkout]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
cd {shlex.quote(str(tmp))}
source {shlex.quote(str(VIBE))}
pat_handle_subcommand pat < /dev/null
"""
        r = run(["bash", "-c", script], env=env)
        check("exit 1", r.returncode == 1, f"returncode={r.returncode}")
        # Stream-precise: the spec pins this as a stderr message, not "output
        # somewhere" — assert on r.stderr alone, not stdout+stderr combined.
        check("error message about detection on stderr", "couldn't detect" in r.stderr, r.stderr)
        check("nothing on stdout", r.stdout == "", r.stdout)


def test_task026_ac4_auto_detect_repo_with_git() -> None:
    """AC4's git-checkout half: 'vibe pat' with no arg, in a git checkout
    with an origin remote, prints 'Repo: <slug>' (via rotate_token, reached
    through detect_github_repo) and — since the test feeds closed stdin —
    terminates via the AC3 abort path rather than blocking at the hidden
    prompt. A prior version of this test called detect_github_repo directly
    and only checked the raw slug appeared in stdout, which exercises git
    remote parsing alone and never proves the pat subcommand's own
    auto-detect wiring (pat_handle_subcommand -> detect_github_repo ->
    rotate_token) actually calls it; that's what this rewrite drives instead."""
    print("\n[task_026 AC4: auto-detect repo from git checkout via vibe pat]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        checkout = tmp / "checkout"
        checkout.mkdir()
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        # Set up git repo with origin remote pointing to GitHub
        run(["git", "init"], cwd=checkout, env=env)
        run(["git", "config", "core.hooksPath", "/dev/null"], cwd=checkout, env=env)
        run(["git", "remote", "add", "origin", "https://github.com/owner/repo.git"], cwd=checkout, env=env)

        script = f"""
cd {shlex.quote(str(checkout))}
source {shlex.quote(str(VIBE))}
pat_handle_subcommand pat < /dev/null
"""
        r = run(["bash", "-c", script], env=env)
        check("prints Repo: owner/repo (detected slug) on stdout", "Repo: owner/repo" in r.stdout, r.stdout)
        check("terminates via AC3 abort path (exit 1)", r.returncode == 1, f"returncode={r.returncode}")
        check("abort message on stderr", "aborted — token store unchanged" in r.stderr, r.stderr)


def test_task026_ac5_stored_token_rejected_401() -> None:
    print("\n[task_026 AC5: stored_token_rejected returns 0 (true) for 401]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        new_path, _, _ = _setup_curl_shim(tmp, response_code="401")
        env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_SOURCE_ONLY": "1"}

        # NOTE: `set +e` must come AFTER `source vibe`, not before — vibe
        # itself runs `set -euo pipefail` unconditionally near its top, which
        # re-arms errexit in this same shell and clobbers an earlier `set +e`.
        # Placing it before sourcing was tried and silently broke this test:
        # a non-zero return from the bare `stored_token_rejected` call below
        # would abort the script before `echo RC=$?` ever ran, leaving stdout
        # empty instead of containing the expected marker.
        script = f"source {shlex.quote(str(VIBE))}; set +e; stored_token_rejected owner/repo ghp_task026_fixture_token; echo RC=$?"
        r = run(["bash", "-c", script], env=env)
        check("returns 0 (true)", "RC=0" in r.stdout, r.stdout)
        check("fixture token absent from output", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_ac5_stored_token_rejected_200() -> None:
    print("\n[task_026 AC5: stored_token_rejected returns 1 (false) for 200]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        new_path, _, _ = _setup_curl_shim(tmp, response_code="200")
        env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_SOURCE_ONLY": "1"}

        # set +e AFTER source — see note in test_task026_ac5_stored_token_rejected_401.
        script = f"source {shlex.quote(str(VIBE))}; set +e; stored_token_rejected owner/repo ghp_task026_fixture_token; echo RC=$?"
        r = run(["bash", "-c", script], env=env)
        check("returns 1 (false)", "RC=1" in r.stdout, r.stdout)
        check("fixture token absent from output", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_ac5_stored_token_rejected_404_000_exit() -> None:
    print("\n[task_026 AC5: stored_token_rejected returns 1 for 404, 000, and curl exit]")
    for code, desc in [("404", "404"), ("000", "000"), ("", "curl-exit")]:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            exit_code = 1 if code == "" else 0
            new_path, _, _ = _setup_curl_shim(tmp, response_code=code, exit_code=exit_code)
            env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_SOURCE_ONLY": "1"}

            # set +e AFTER source — see note in test_task026_ac5_stored_token_rejected_401.
            script = f"source {shlex.quote(str(VIBE))}; set +e; stored_token_rejected owner/repo ghp_task026_fixture_token; echo RC=$?"
            r = run(["bash", "-c", script], env=env)
            check(f"returns 1 for {desc}", "RC=1" in r.stdout, r.stdout)
            check(f"fixture token absent from output ({desc})", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_ac6_curl_arg_logging() -> None:
    print("\n[task_026 AC6: curl argv and stdin logging]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        new_path, argv_log, stdin_log = _setup_curl_shim(tmp, response_code="200")
        env = {**os.environ, "HOME": str(tmp), "PATH": new_path, "VIBE_SOURCE_ONLY": "1"}

        script = f"source {shlex.quote(str(VIBE))}; stored_token_rejected owner/repo ghp_task026_fixture_token >/dev/null"
        r = run(["bash", "-c", script], env=env)

        argv_content = argv_log.read_text() if argv_log.exists() else ""
        stdin_content = stdin_log.read_text() if stdin_log.exists() else ""

        check("curl argv contains api.github.com/repos/owner/repo", "api.github.com/repos/owner/repo" in argv_content, argv_content)
        check("curl argv contains -s", "-s" in argv_content.split(), argv_content)
        check("curl argv contains -K", "-K" in argv_content, argv_content)
        check("curl argv does NOT contain fixture token", "ghp_task026_fixture_token" not in argv_content, argv_content)
        check("curl stdin contains Authorization header", "Authorization: Bearer ghp_task026_fixture_token" in stdin_content, stdin_content)
        check("fixture token absent from process stdout+stderr", "ghp_task026_fixture_token" not in (r.stdout + r.stderr), r.stdout + r.stderr)


def test_task026_ac7_no_token_in_output() -> None:
    print("\n[task_026 AC7: fixture token never appears in output]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}
        tokens_file = tmp / ".vibe" / "tokens"
        tokens_file.parent.mkdir(parents=True)

        script = f"""
source {shlex.quote(str(VIBE))}
echo ghp_task026_fixture_token | rotate_token owner/repo 2>&1
"""
        r = run(["bash", "-c", script], env=env)
        combined = r.stdout + r.stderr
        check("fixture token not in output", "ghp_task026_fixture_token" not in combined, combined[:200])


def test_task026_ac8_maybe_reprompt_vibe_pat_check_zero() -> None:
    print("\n[task_026 AC8(a): maybe_reprompt_stored_token with VIBE_PAT_CHECK=0]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config",
               "VIBE_SOURCE_ONLY": "1", "VIBE_PAT_CHECK": "0"}

        # Stub stored_token_rejected and setup_token to verify they're not called
        script = f"""
set -e
source {shlex.quote(str(VIBE))}

probe_called=0
setup_called=0

stored_token_rejected() {{ probe_called=1; return 1; }}
setup_token() {{ setup_called=1; }}

set +e
maybe_reprompt_stored_token owner/repo ghp_token
RC=$?
set -e

echo "RC=$RC"
echo "PROBE=$probe_called"
echo "SETUP=$setup_called"
"""
        r = run(["bash", "-c", script], env=env)
        check("returns 0", "RC=0" in r.stdout, r.stdout)
        check("probe not called", "PROBE=0" in r.stdout, r.stdout)
        check("setup not called", "SETUP=0" in r.stdout, r.stdout)


def test_task026_ac8_maybe_reprompt_empty_token() -> None:
    print("\n[task_026 AC8(b): maybe_reprompt_stored_token with empty token]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
set -e
source {shlex.quote(str(VIBE))}

probe_called=0
setup_called=0

stored_token_rejected() {{ probe_called=1; return 1; }}
setup_token() {{ setup_called=1; }}

set +e
maybe_reprompt_stored_token owner/repo ""
RC=$?
set -e

echo "RC=$RC"
echo "PROBE=$probe_called"
echo "SETUP=$setup_called"
"""
        r = run(["bash", "-c", script], env=env)
        check("returns 0", "RC=0" in r.stdout, r.stdout)
        check("probe not called", "PROBE=0" in r.stdout, r.stdout)
        check("setup not called", "SETUP=0" in r.stdout, r.stdout)


def test_task026_ac8_maybe_reprompt_rejected() -> None:
    print("\n[task_026 AC8(c): maybe_reprompt_stored_token with rejection]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
set -e
source {shlex.quote(str(VIBE))}

probe_called=0
setup_called=0
setup_repo=""

stored_token_rejected() {{ probe_called=1; return 0; }}
setup_token() {{ setup_called=1; setup_repo="$1"; }}

set +e
maybe_reprompt_stored_token owner/repo ghp_token 2>&1
RC=$?
set -e

echo "RC=$RC"
echo "PROBE=$probe_called"
echo "SETUP=$setup_called"
echo "REPO=$setup_repo"
"""
        r = run(["bash", "-c", script], env=env)
        check("returns 0", "RC=0" in r.stdout, r.stdout)
        check("probe called", "PROBE=1" in r.stdout, r.stdout)
        check("setup called", "SETUP=1" in r.stdout, r.stdout)
        check("setup called with correct repo", "REPO=owner/repo" in r.stdout, r.stdout)
        check("warning message printed", "was rejected by GitHub" in r.stdout, r.stdout)


def test_task026_ac8_maybe_reprompt_not_rejected() -> None:
    print("\n[task_026 AC8(d): maybe_reprompt_stored_token with non-rejection]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config", "VIBE_SOURCE_ONLY": "1"}

        script = f"""
set -e
source {shlex.quote(str(VIBE))}

probe_called=0
setup_called=0

stored_token_rejected() {{ probe_called=1; return 1; }}
setup_token() {{ setup_called=1; }}

set +e
maybe_reprompt_stored_token owner/repo ghp_token
RC=$?
set -e

echo "RC=$RC"
echo "PROBE=$probe_called"
echo "SETUP=$setup_called"
"""
        r = run(["bash", "-c", script], env=env)
        check("returns 0", "RC=0" in r.stdout, r.stdout)
        check("probe called", "PROBE=1" in r.stdout, r.stdout)
        check("setup NOT called", "SETUP=0" in r.stdout, r.stdout)


def test_task026_ac8_maybe_reprompt_placement() -> None:
    """AC8's static placement assertion. Must be genuinely placement-aware —
    a prior version of this test located the call line, then scanned
    backwards for a nearby 'GITHUB_TOKEN=' assignment but never actually
    used the result of that scan to fail anything: the `check()` call only
    asserted the call line's bare text presence anywhere in the file, so an
    unconditional call site placed right after the `elif` block, or inside
    the EMPTY-token ('then') branch — exactly the case AC8 calls out as
    "would probe a freshly-pasted token" — would have passed just as easily.
    This rewrite finds the specific `if [...GITHUB_TOKEN...]` branch nearest
    the stored-token lookup, tracks bash if/fi keyword depth to locate that
    branch's own matching `else` and `fi` (elif/else don't shift depth,
    since they don't open a new if), and requires the call site to sit
    strictly between them — i.e. inside the non-empty-token else-branch,
    not the then-branch, and not after the fi (unconditional)."""
    print("\n[task_026 AC8: launch-path call placement check]")
    lines = VIBE.read_text().split("\n")
    call_marker = 'maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"'

    call_idx = next((i for i, line in enumerate(lines) if call_marker in line), None)
    check("call site exists in vibe", call_idx is not None, "not found in vibe")
    if call_idx is None:
        return

    # Nearest preceding "GITHUB_TOKEN=$(lookup_token" assignment — establishes
    # we're looking at the stored-token lookup context, not some unrelated
    # GITHUB_TOKEN assignment elsewhere in the file (e.g. inside setup_token).
    assign_idx = next(
        (i for i in range(call_idx - 1, -1, -1) if "GITHUB_TOKEN=$(lookup_token" in lines[i]),
        None,
    )
    check("a preceding 'GITHUB_TOKEN=$(lookup_token' assignment exists before the call site",
          assign_idx is not None, "not found")
    if assign_idx is None:
        return

    # Nearest "if ... GITHUB_TOKEN ..." line between that assignment and the call site.
    if_idx = None
    for i in range(assign_idx + 1, call_idx + 1):
        tokens = lines[i].strip().split()
        if tokens and tokens[0] == "if" and "GITHUB_TOKEN" in lines[i]:
            if_idx = i
            break
    check("a GITHUB_TOKEN-testing 'if' branch exists between the assignment and the call site",
          if_idx is not None, "not found")
    if if_idx is None:
        return

    # Walk forward from the if, tracking if/fi depth (elif/else are distinct
    # tokens from "if"/"fi" so they don't perturb the count), to find this
    # branch's own "else" (at depth 1, i.e. not inside a nested if) and its
    # matching "fi" (where depth returns to 0).
    depth = 0
    else_idx = None
    fi_idx = None
    for i in range(if_idx, len(lines)):
        tokens = lines[i].strip().split()
        for tok in tokens:
            if tok == "if":
                depth += 1
            elif tok == "fi":
                depth -= 1
                if depth == 0:
                    fi_idx = i
                    break
        if fi_idx is not None:
            break
        if depth == 1 and "else" in tokens and else_idx is None:
            else_idx = i

    check("the branch has a matching 'fi'", fi_idx is not None, "no matching fi found")
    check("the branch has an 'else'", else_idx is not None, "no else found")
    if fi_idx is None or else_idx is None:
        return

    check("call site sits inside the non-empty-token else-branch (between its 'else' and 'fi') "
          "— NOT the empty-token then-branch, and NOT placed unconditionally after the fi",
          else_idx < call_idx < fi_idx,
          f"if_idx={if_idx} else_idx={else_idx} call_idx={call_idx} fi_idx={fi_idx}")


def test_task026_ac9_help_mentions_pat() -> None:
    print("\n[task_026 AC9: vibe --help mentions vibe pat]")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = {**os.environ, "HOME": str(tmp), "VIBE_CONFIG": f"{tmp}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
        check("--help contains vibe pat", "vibe pat" in r.stdout, r.stdout[:500])
        check("help text contains HOST shell", "HOST shell" in r.stdout, r.stdout)


def test_task026_ac9_regression_gate() -> None:
    """AC9's code-check.py clause. Deliberately does NOT spawn smoke-test.py
    from within smoke-test.py — a prior attempt at this test did exactly
    that and produced unbounded self-recursion (a runaway process tree that
    had to be killed). code-check.py is fast (shellcheck only) and
    non-recursive, so it's safe to run in-process here. AC9's other clause
    — "every pre-existing smoke-test.py test function still passes" — is
    evidenced by the single full top-level `python3 smoke-test.py` run that
    produces test-output.log for this cycle (see .vs/cycle-1/test-output.log),
    not by anything this function does."""
    print("\n[task_026 AC9: regression gate — code-check.py passes]")
    r = run(["python3", str(REPO / "code-check.py")], cwd=REPO)
    check("code-check.py exits 0", r.returncode == 0, r.stdout + r.stderr)


def test_task026_ac10_readme_documents_pat() -> None:
    print("\n[task_026 AC10: README.md documents vibe pat and 401]")
    readme = (REPO / "README.md").read_text()
    check("README contains 'vibe pat'", "vibe pat" in readme, "")
    check("README contains '401'", "401" in readme, "")


def test_task026_ac10_manual_tests_documents_pat() -> None:
    print("\n[task_026 AC10: MANUAL-TESTS.md documents vibe pat and VIBE_PAT_CHECK=0]")
    manual = (REPO / "MANUAL-TESTS.md").read_text()
    check("MANUAL-TESTS contains 'vibe pat'", "vibe pat" in manual, "")
    check("MANUAL-TESTS contains 'VIBE_PAT_CHECK=0'", "VIBE_PAT_CHECK=0" in manual, "")
