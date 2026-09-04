"""task_040: language-profile mechanism (`vibe --profile <name>`) + first
profile `python`.

Tester-owned, spec-only tests (written against .vs/spec.md, NOT against the
Generator's code — expect failures until the launcher/profile lands).
Covers AC2-AC13 from .vs/spec.md. AC1 (code-check.py / smoke-test.py exit 0,
no weakened test) is enforced by the harness itself, not a test body here.

IMPORTANT: this file must never contain a `git diff <sha>`/`git show <sha>`
literal — checks_12_harness_lints.py's sha-pin lint fails the whole suite on
an unregistered sha token in any smoke/*.py file. AC2's baseline-diff check
(`git diff --name-only 6d361c2 -- devcontainer/Dockerfile
devcontainer/devcontainer.json`) is run ad hoc by the chair, outside this
file; the permanent test here asserts only the resulting property.

Functions under test (Generator-owned, in `vibe`, defined ABOVE the
`VIBE_SOURCE_ONLY` guard at ~line 3246 so `_source_vibe_call` can reach
them):
  - resolve_profile <flag_value> <workspace> <config_value>   (AC4)
  - profile_dir <name>                                        (AC5)
  - profile_is_stale <name> <marker> <base_rebuilt_bool>       (AC6)
  - base_is_stale <devcontainer_dir> <marker>                  (AC7)
  - render_devcontainer_with_mounts (VIBE_IMAGE_TAG env)       (AC8, existing fn extended)
  - profile_suggestion <workspace> <hint_marker_dir>           (AC10)
"""
import os
import time
from pathlib import Path

from smoke._core import *  # noqa: F401,F403

DEVCONTAINER_JSON = REPO / "devcontainer" / "devcontainer.json"
PYTHON_PROFILE_DOCKERFILE = REPO / "devcontainer" / "profiles" / "python" / "Dockerfile"
README_MD = REPO / "README.md"
CLAUDE_MD = REPO / "CLAUDE.md"
MANUAL_TESTS_MD = REPO / "MANUAL-TESTS.md"
TODO_MD = REPO / "TODO.md"
CHANGELOG_MD = REPO / "CHANGELOG.md"

ALLOWED_URL_HOSTS = {"pypi.org", "files.pythonhosted.org", "astral.sh", "github.com"}


# ── AC2: base Dockerfile / devcontainer.json untouched (permanent property) ──

def test_profiles_ac2_base_dockerfile_and_devcontainer_json_untouched() -> None:
    """AC2: devcontainer/Dockerfile carries no profile/PROFILE token, and
    devcontainer.json's "image" key is still "vibe-dev:latest". The runtime
    `git diff --name-only 6d361c2 -- devcontainer/Dockerfile
    devcontainer/devcontainer.json` check is ad hoc (chair-run, never in a
    committed test file) — this is the permanent property check."""
    print("\n[profiles] AC2: base Dockerfile/devcontainer.json untouched")
    dockerfile_text = DOCKERFILE.read_text()
    check("[profiles] AC2: Dockerfile has no 'profile' token (case-insensitive)",
          "profile" not in dockerfile_text.lower(), "")
    check("[profiles] AC2: Dockerfile has no 'PROFILE' token",
          "PROFILE" not in dockerfile_text, "")
    if DEVCONTAINER_JSON.exists():
        cfg = json.loads(DEVCONTAINER_JSON.read_text())
        check("[profiles] AC2: devcontainer.json image is vibe-dev:latest",
              cfg.get("image") == "vibe-dev:latest", str(cfg.get("image")))
    else:
        check("[profiles] AC2: devcontainer.json exists", False, str(DEVCONTAINER_JSON))


# ── AC3: vibe --help lists --profile ──────────────────────────────────────

def test_profiles_ac3_help_lists_profile_flag() -> None:
    """AC3: `vibe --help` lists `--profile <name>` with `none` and the
    shipped names (python); the usage comment block at the top of `vibe`
    gains the same line."""
    print("\n[profiles] AC3: --help lists --profile flag")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HOME": td, "VIBE_CONFIG": f"{td}/no-config"}
        r = run(["bash", str(VIBE), "--help"], env=env)
    check("[profiles] AC3: --help exits 0", r.returncode == 0, r.stderr)
    check("[profiles] AC3: --help mentions '--profile <name>'",
          "--profile <name>" in r.stdout, r.stdout[:400])
    check("[profiles] AC3: --help mentions 'none'",
          "none" in r.stdout, "")
    check("[profiles] AC3: --help mentions 'python'",
          "python" in r.stdout, "")

    vibe_text = VIBE.read_text()
    header = vibe_text[:4000]
    check("[profiles] AC3: usage comment block mentions '--profile'",
          "--profile" in header, header[:400])


# ── AC4: resolve_profile precedence ladder ────────────────────────────────

def test_profiles_ac4_resolve_profile_flag_rung() -> None:
    """AC4: flag_value wins when set, regardless of workspace/config."""
    print("\n[profiles] AC4: resolve_profile — flag rung")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        r = _source_vibe_call(
            {}, f'resolve_profile python {shlex.quote(str(ws))} ""')
        check("[profiles] AC4: flag rung exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC4: flag rung echoes 'python'",
              r.stdout.strip() == "python", repr(r.stdout))


def test_profiles_ac4_resolve_profile_vibeprofile_file_rung() -> None:
    """AC4: .vibe/profile (first line, trimmed) wins when flag is empty."""
    print("\n[profiles] AC4: resolve_profile — .vibe/profile rung")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        (ws / ".vibe").mkdir(parents=True)
        (ws / ".vibe" / "profile").write_text("rust\n")
        r = _source_vibe_call(
            {}, f'resolve_profile "" {shlex.quote(str(ws))} ""')
        check("[profiles] AC4: .vibe/profile rung exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC4: .vibe/profile rung echoes 'rust'",
              r.stdout.strip() == "rust", repr(r.stdout))


def test_profiles_ac4_resolve_profile_vibe_profile_env_rung() -> None:
    """AC4: VIBE_PROFILE (passed as config_value) wins when flag and
    .vibe/profile are both empty/absent."""
    print("\n[profiles] AC4: resolve_profile — VIBE_PROFILE rung")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        r = _source_vibe_call(
            {}, f'resolve_profile "" {shlex.quote(str(ws))} swift')
        check("[profiles] AC4: VIBE_PROFILE rung exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC4: VIBE_PROFILE rung echoes 'swift'",
              r.stdout.strip() == "swift", repr(r.stdout))


def test_profiles_ac4_resolve_profile_full_ladder_flag_wins() -> None:
    """AC4: with all three rungs set, the flag wins."""
    print("\n[profiles] AC4: resolve_profile — full ladder, flag wins")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        (ws / ".vibe").mkdir(parents=True)
        (ws / ".vibe" / "profile").write_text("rust\n")
        r = _source_vibe_call(
            {}, f'resolve_profile python {shlex.quote(str(ws))} swift')
        check("[profiles] AC4: full ladder exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC4: full ladder echoes 'python' (flag wins)",
              r.stdout.strip() == "python", repr(r.stdout))


def test_profiles_ac4_resolve_profile_none_at_each_rung() -> None:
    """AC4: 'none' at any rung echoes empty (base, no profile)."""
    print("\n[profiles] AC4: resolve_profile — 'none' at each rung")
    with tempfile.TemporaryDirectory() as td:
        # none via flag
        ws1 = Path(td) / "ws1"
        (ws1 / ".vibe").mkdir(parents=True)
        (ws1 / ".vibe" / "profile").write_text("rust\n")
        r1 = _source_vibe_call(
            {}, f'resolve_profile none {shlex.quote(str(ws1))} swift')
        check("[profiles] AC4: none-via-flag echoes empty",
              r1.stdout.strip() == "", repr(r1.stdout))

        # none via .vibe/profile
        ws2 = Path(td) / "ws2"
        (ws2 / ".vibe").mkdir(parents=True)
        (ws2 / ".vibe" / "profile").write_text("none\n")
        r2 = _source_vibe_call(
            {}, f'resolve_profile "" {shlex.quote(str(ws2))} swift')
        check("[profiles] AC4: none-via-.vibe/profile echoes empty",
              r2.stdout.strip() == "", repr(r2.stdout))

        # none via config value (VIBE_PROFILE)
        ws3 = Path(td) / "ws3"
        ws3.mkdir()
        r3 = _source_vibe_call(
            {}, f'resolve_profile "" {shlex.quote(str(ws3))} none')
        check("[profiles] AC4: none-via-config echoes empty",
              r3.stdout.strip() == "", repr(r3.stdout))


def test_profiles_ac4_resolve_profile_trimming() -> None:
    """AC4: whitespace/newline in .vibe/profile is trimmed — leading/trailing
    spaces and a trailing blank line are stripped, only the first line is
    used."""
    print("\n[profiles] AC4: resolve_profile — .vibe/profile trimming")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        (ws / ".vibe").mkdir(parents=True)
        (ws / ".vibe" / "profile").write_text("  python  \n\nsecondline\n")
        r = _source_vibe_call(
            {}, f'resolve_profile "" {shlex.quote(str(ws))} ""')
        check("[profiles] AC4: trimming exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC4: trimmed to 'python' (first line only, ws stripped)",
              r.stdout.strip() == "python", repr(r.stdout))


# ── AC5: profile_dir resolution ────────────────────────────────────────────

def test_profiles_ac5_profile_dir_shipped() -> None:
    """AC5: shipped profile (python) resolves under $DEVCONTAINER_DIR/profiles."""
    print("\n[profiles] AC5: profile_dir — shipped")
    r = _source_vibe_call({}, "profile_dir python")
    expected = str(REPO / "devcontainer" / "profiles" / "python")
    check("[profiles] AC5: shipped exits 0", r.returncode == 0, r.stderr)
    check("[profiles] AC5: shipped echoes $DEVCONTAINER_DIR/profiles/python",
          r.stdout.strip() == expected, f"got {r.stdout.strip()!r} want {expected!r}")


def test_profiles_ac5_profile_dir_custom() -> None:
    """AC5: a custom profile under ~/.vibe/profiles/<name>/Dockerfile resolves
    when it isn't a shipped name."""
    print("\n[profiles] AC5: profile_dir — custom (fixture HOME)")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        custom_dir = home / ".vibe" / "profiles" / "mycustom"
        custom_dir.mkdir(parents=True)
        (custom_dir / "Dockerfile").write_text("ARG BASE=vibe-dev:latest\nFROM ${BASE}\n")
        r = _source_vibe_call({"HOME": str(home)}, "profile_dir mycustom")
        check("[profiles] AC5: custom exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC5: custom echoes ~/.vibe/profiles/mycustom",
              r.stdout.strip() == str(custom_dir), f"got {r.stdout.strip()!r}")


def test_profiles_ac5_profile_dir_unknown_exits_1() -> None:
    """AC5: an unknown name exits 1 and lists available names (incl. python)
    on stderr."""
    print("\n[profiles] AC5: profile_dir — unknown exits 1")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        r = _source_vibe_call({"HOME": str(home)}, "profile_dir totally-bogus-profile-xyz")
        check("[profiles] AC5: unknown exits 1", r.returncode == 1, f"rc={r.returncode}")
        check("[profiles] AC5: unknown mentions the bad name",
              "totally-bogus-profile-xyz" in r.stderr, r.stderr)
        check("[profiles] AC5: unknown stderr has 'available:'",
              "available:" in r.stderr, r.stderr)
        check("[profiles] AC5: unknown stderr lists 'python'",
              "python" in r.stderr, r.stderr)


def test_profiles_ac5_profile_dir_shipped_beats_custom() -> None:
    """AC5: on a name clash, the shipped profile wins over a same-named
    custom profile under ~/.vibe/profiles/."""
    print("\n[profiles] AC5: profile_dir — shipped beats custom on clash")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        clash_dir = home / ".vibe" / "profiles" / "python"
        clash_dir.mkdir(parents=True)
        (clash_dir / "Dockerfile").write_text("ARG BASE=vibe-dev:latest\nFROM ${BASE}\n")
        r = _source_vibe_call({"HOME": str(home)}, "profile_dir python")
        expected = str(REPO / "devcontainer" / "profiles" / "python")
        check("[profiles] AC5: clash exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC5: clash resolves to shipped, not custom",
              r.stdout.strip() == expected, f"got {r.stdout.strip()!r} want {expected!r}")


# ── AC6: profile_is_stale ──────────────────────────────────────────────────

def _make_custom_profile(home: Path, name: str, dockerfile_mtime: float | None = None) -> Path:
    d = home / ".vibe" / "profiles" / name
    d.mkdir(parents=True)
    f = d / "Dockerfile"
    f.write_text("ARG BASE=vibe-dev:latest\nFROM ${BASE}\nRUN true\n")
    if dockerfile_mtime is not None:
        os.utime(f, (dockerfile_mtime, dockerfile_mtime))
    return d


def test_profiles_ac6_stale_marker_missing() -> None:
    """AC6: profile_is_stale echoes 1 when the marker file is missing."""
    print("\n[profiles] AC6: profile_is_stale — marker missing")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        now = time.time()
        _make_custom_profile(home, "pstale1", dockerfile_mtime=now)
        marker = Path(td) / "marker-does-not-exist"
        r = _source_vibe_call(
            {"HOME": str(home)},
            f"profile_is_stale pstale1 {shlex.quote(str(marker))} false")
        check("[profiles] AC6: marker-missing exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC6: marker-missing echoes '1'",
              r.stdout.strip() == "1", repr(r.stdout))


def test_profiles_ac6_stale_file_newer_than_marker() -> None:
    """AC6: profile_is_stale echoes 1 when a file under the profile dir is
    newer than the marker."""
    print("\n[profiles] AC6: profile_is_stale — profile file newer than marker")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        now = time.time()
        marker = Path(td) / "marker"
        marker.write_text("built\n")
        os.utime(marker, (now, now))
        _make_custom_profile(home, "pstale2", dockerfile_mtime=now + 100)
        r = _source_vibe_call(
            {"HOME": str(home)},
            f"profile_is_stale pstale2 {shlex.quote(str(marker))} false")
        check("[profiles] AC6: file-newer exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC6: file-newer echoes '1'",
              r.stdout.strip() == "1", repr(r.stdout))


def test_profiles_ac6_stale_base_rebuilt_true() -> None:
    """AC6: profile_is_stale echoes 1 when base_rebuilt_bool is 'true', even
    if the marker is newer than every profile file."""
    print("\n[profiles] AC6: profile_is_stale — base rebuilt true")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        now = time.time()
        _make_custom_profile(home, "pstale3", dockerfile_mtime=now)
        marker = Path(td) / "marker"
        marker.write_text("built\n")
        os.utime(marker, (now + 100, now + 100))
        r = _source_vibe_call(
            {"HOME": str(home)},
            f"profile_is_stale pstale3 {shlex.quote(str(marker))} true")
        check("[profiles] AC6: base-rebuilt exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC6: base-rebuilt echoes '1'",
              r.stdout.strip() == "1", repr(r.stdout))


def test_profiles_ac6_not_stale() -> None:
    """AC6: profile_is_stale echoes nothing when the marker is newer than
    every profile file and base_rebuilt_bool is 'false'."""
    print("\n[profiles] AC6: profile_is_stale — not stale")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        now = time.time()
        _make_custom_profile(home, "pstale4", dockerfile_mtime=now)
        marker = Path(td) / "marker"
        marker.write_text("built\n")
        os.utime(marker, (now + 100, now + 100))
        r = _source_vibe_call(
            {"HOME": str(home)},
            f"profile_is_stale pstale4 {shlex.quote(str(marker))} false")
        check("[profiles] AC6: not-stale exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC6: not-stale echoes nothing",
              r.stdout.strip() == "", repr(r.stdout))


# ── AC7: base_is_stale prunes profiles/ ────────────────────────────────────

def test_profiles_ac7_base_is_stale_prunes_profiles() -> None:
    """AC7: base_is_stale echoes nothing when only a file under profiles/
    is newer than the marker (a profile edit must never rebuild the base)."""
    print("\n[profiles] AC7: base_is_stale — prunes profiles/")
    with tempfile.TemporaryDirectory() as td:
        dc = Path(td) / "devcontainer"
        dc.mkdir()
        now = time.time()
        base_dockerfile = dc / "Dockerfile"
        base_dockerfile.write_text("FROM debian\n")
        marker = Path(td) / "marker"
        marker.write_text("built\n")
        os.utime(base_dockerfile, (now, now))
        os.utime(marker, (now + 50, now + 50))
        prof = dc / "profiles" / "x"
        prof.mkdir(parents=True)
        (prof / "Dockerfile").write_text("ARG BASE=vibe-dev:latest\nFROM ${BASE}\n")
        os.utime(prof / "Dockerfile", (now + 100, now + 100))  # newer than marker
        r = _source_vibe_call(
            {}, f"base_is_stale {shlex.quote(str(dc))} {shlex.quote(str(marker))}")
        check("[profiles] AC7: prune-case exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC7: prune-case echoes nothing",
              r.stdout.strip() == "", repr(r.stdout))


def test_profiles_ac7_base_is_stale_when_dockerfile_newer() -> None:
    """AC7: base_is_stale echoes 1 when the base Dockerfile itself (outside
    profiles/) is newer than the marker."""
    print("\n[profiles] AC7: base_is_stale — Dockerfile newer than marker")
    with tempfile.TemporaryDirectory() as td:
        dc = Path(td) / "devcontainer"
        dc.mkdir()
        now = time.time()
        marker = Path(td) / "marker"
        marker.write_text("built\n")
        os.utime(marker, (now, now))
        base_dockerfile = dc / "Dockerfile"
        base_dockerfile.write_text("FROM debian\n")
        os.utime(base_dockerfile, (now + 100, now + 100))  # newer than marker
        prof = dc / "profiles" / "x"
        prof.mkdir(parents=True)
        (prof / "Dockerfile").write_text("ARG BASE=vibe-dev:latest\nFROM ${BASE}\n")
        os.utime(prof / "Dockerfile", (now - 100, now - 100))  # older, irrelevant
        r = _source_vibe_call(
            {}, f"base_is_stale {shlex.quote(str(dc))} {shlex.quote(str(marker))}")
        check("[profiles] AC7: Dockerfile-newer exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC7: Dockerfile-newer echoes '1'",
              r.stdout.strip() == "1", repr(r.stdout))


# ── AC8: render_devcontainer_with_mounts + VIBE_IMAGE_TAG ─────────────────

def test_profiles_ac8_render_devcontainer_image_tag() -> None:
    """AC8: with VIBE_IMAGE_TAG set, "image" is overridden; with it
    unset/empty, output is byte-identical to a render with the var absent
    (no unintended side effects like key reordering)."""
    print("\n[profiles] AC8: render_devcontainer_with_mounts — VIBE_IMAGE_TAG")
    with tempfile.TemporaryDirectory() as td:
        src = DEVCONTAINER_JSON
        neutral_env = {"VIBE_OP_ADDHOST": "", "VIBE_SHARED_ENV_NAMES": ""}

        dst_set = Path(td) / "set.json"
        call_set = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                    f"{shlex.quote(str(dst_set))}")
        r_set = _source_vibe_call(
            {**neutral_env, "VIBE_IMAGE_TAG": "vibe-dev:python"}, call_set)
        check("[profiles] AC8: render (tag set) exits 0", r_set.returncode == 0, r_set.stderr)
        if r_set.returncode == 0:
            cfg_set = json.loads(dst_set.read_text())
            check("[profiles] AC8: image overridden to vibe-dev:python",
                  cfg_set.get("image") == "vibe-dev:python", str(cfg_set.get("image")))

        dst_absent = Path(td) / "absent.json"
        call_absent = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                       f"{shlex.quote(str(dst_absent))}")
        r_absent = _source_vibe_call(neutral_env, call_absent)
        check("[profiles] AC8: render (tag absent) exits 0",
              r_absent.returncode == 0, r_absent.stderr)

        dst_empty = Path(td) / "empty.json"
        call_empty = (f"render_devcontainer_with_mounts {shlex.quote(str(src))} "
                      f"{shlex.quote(str(dst_empty))}")
        r_empty = _source_vibe_call(
            {**neutral_env, "VIBE_IMAGE_TAG": ""}, call_empty)
        check("[profiles] AC8: render (tag empty) exits 0",
              r_empty.returncode == 0, r_empty.stderr)

        if r_absent.returncode == 0 and r_empty.returncode == 0:
            absent_text = dst_absent.read_text()
            empty_text = dst_empty.read_text()
            check("[profiles] AC8: absent vs empty render is byte-identical",
                  absent_text == empty_text,
                  f"absent={absent_text!r} empty={empty_text!r}")
            src_cfg = json.loads(src.read_text())
            absent_cfg = json.loads(absent_text)
            check("[profiles] AC8: image left at src value when tag unset",
                  absent_cfg.get("image") == src_cfg.get("image"),
                  f"{absent_cfg.get('image')!r} vs {src_cfg.get('image')!r}")


# ── AC9: python profile Dockerfile literals ────────────────────────────────

def test_profiles_ac9_python_dockerfile_literals() -> None:
    """AC9: devcontainer/profiles/python/Dockerfile shape and content."""
    print("\n[profiles] AC9: python profile Dockerfile literals")
    check("[profiles] AC9: devcontainer/profiles/python/Dockerfile exists",
          PYTHON_PROFILE_DOCKERFILE.exists(), str(PYTHON_PROFILE_DOCKERFILE))
    if not PYTHON_PROFILE_DOCKERFILE.exists():
        return
    text = PYTHON_PROFILE_DOCKERFILE.read_text()
    lines = text.splitlines()
    non_comment = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]

    check("[profiles] AC9: first non-comment line is 'ARG BASE=vibe-dev:latest'",
          len(non_comment) > 0 and non_comment[0].strip() == "ARG BASE=vibe-dev:latest",
          non_comment[:2])
    check("[profiles] AC9: second non-comment line is 'FROM ${BASE}'",
          len(non_comment) > 1 and non_comment[1].strip() == "FROM ${BASE}",
          non_comment[:2])

    run_lines = re.findall(r'^RUN\s', text, re.MULTILINE)
    check("[profiles] AC9: exactly one RUN instruction",
          len(run_lines) == 1, f"found {len(run_lines)}")

    check("[profiles] AC9: has --no-install-recommends",
          "--no-install-recommends" in text, "")
    check("[profiles] AC9: cleans apt lists (rm -rf /var/lib/apt/lists/*)",
          "rm -rf /var/lib/apt/lists/*" in text, "")

    for tok in ("python3", "python3-venv", "python3-pip"):
        check(f"[profiles] AC9: apt token '{tok}' present", tok in text, "")

    check("[profiles] AC9: 'uv tool install ruff' present",
          "uv tool install ruff" in text, "")
    check("[profiles] AC9: 'uv tool install mypy' present",
          "uv tool install mypy" in text, "")
    check("[profiles] AC9: astral.sh referenced (uv's own installer)",
          "astral.sh" in text, "")
    check("[profiles] AC9: no pipx (one mechanism only)",
          "pipx" not in text, "")

    env_path_lines = [ln for ln in lines if re.match(r'^\s*ENV\s+PATH', ln)]
    check("[profiles] AC9: has an ENV PATH line",
          len(env_path_lines) > 0, "")
    check("[profiles] AC9: ENV PATH line includes .local/bin",
          any(".local/bin" in ln for ln in env_path_lines),
          str(env_path_lines))

    user_lines = re.findall(r'^\s*USER\s+(\S+)', text, re.MULTILINE)
    check("[profiles] AC9: has at least one USER directive",
          len(user_lines) > 0, "")
    check("[profiles] AC9: last USER directive is 'node'",
          len(user_lines) > 0 and user_lines[-1] == "node", str(user_lines))

    urls = re.findall(r'https?://([^/\s"\')]+)', text)
    bad_hosts = [h for h in urls if h not in ALLOWED_URL_HOSTS]
    check("[profiles] AC9: every http(s) URL host is in the allowlist",
          len(bad_hosts) == 0, f"bad hosts: {bad_hosts} (urls: {urls})")


# ── AC10: profile_suggestion ────────────────────────────────────────────────

def test_profiles_ac10_suggestion_fires_once_and_marks() -> None:
    """AC10: profile_suggestion prints the hint once, creates a marker, and
    is silent on a second call for the same workspace."""
    print("\n[profiles] AC10: profile_suggestion — fires once, marks")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("[project]\nname='x'\n")
        hint_dir = Path(td) / "hints"
        hint_dir.mkdir()

        call = (f'profile_suggestion {shlex.quote(str(ws))} '
                f'{shlex.quote(str(hint_dir))}')
        r1 = _source_vibe_call({}, call)
        check("[profiles] AC10: first call exits 0", r1.returncode == 0, r1.stderr)
        check("[profiles] AC10: first call prints the hint",
              "vibe --profile python" in r1.stderr, r1.stderr)
        marker_files_after_first = list(hint_dir.iterdir())
        check("[profiles] AC10: first call created exactly one marker file",
              len(marker_files_after_first) == 1,
              str(marker_files_after_first))

        r2 = _source_vibe_call({}, call)
        check("[profiles] AC10: second call exits 0", r2.returncode == 0, r2.stderr)
        check("[profiles] AC10: second call is silent",
              "vibe --profile python" not in r2.stderr, r2.stderr)
        marker_files_after_second = list(hint_dir.iterdir())
        check("[profiles] AC10: second call did not create another marker",
              len(marker_files_after_second) == 1,
              str(marker_files_after_second))


def test_profiles_ac10_suggestion_silent_with_no_python_files() -> None:
    """AC10: profile_suggestion is silent, and creates no marker, when the
    workspace has neither pyproject.toml nor requirements.txt."""
    print("\n[profiles] AC10: profile_suggestion — silent, no python files")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        hint_dir = Path(td) / "hints"
        hint_dir.mkdir()
        call = (f'profile_suggestion {shlex.quote(str(ws))} '
                f'{shlex.quote(str(hint_dir))}')
        r = _source_vibe_call({}, call)
        check("[profiles] AC10: no-python-files call exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC10: no-python-files call is silent",
              "vibe --profile python" not in r.stderr, r.stderr)
        check("[profiles] AC10: no-python-files call creates no marker",
              len(list(hint_dir.iterdir())) == 0,
              str(list(hint_dir.iterdir())))


def test_profiles_ac10_suggestion_recognises_requirements_txt() -> None:
    """AC10: requirements.txt alone is also sufficient to fire the hint."""
    print("\n[profiles] AC10: profile_suggestion — requirements.txt fires it")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        (ws / "requirements.txt").write_text("requests\n")
        hint_dir = Path(td) / "hints"
        hint_dir.mkdir()
        call = (f'profile_suggestion {shlex.quote(str(ws))} '
                f'{shlex.quote(str(hint_dir))}')
        r = _source_vibe_call({}, call)
        check("[profiles] AC10: requirements.txt call exits 0", r.returncode == 0, r.stderr)
        check("[profiles] AC10: requirements.txt fires the hint",
              "vibe --profile python" in r.stderr, r.stderr)


# ── AC11: structural greps on the launcher's container-launch path ─────────

def test_profiles_ac11_launch_path_structure() -> None:
    """AC11: the profile docker build carries --build-arg "BASE=... and
    -t "$IMAGE_TAG", runs after the base build's touch "$IMAGE_MARKER" line,
    VIBE_IMAGE_TAG is exported, a '◆ profile:' header line exists, and
    resolve_profile is invoked before the image_drift_needs_recreate call."""
    print("\n[profiles] AC11: launch-path structural checks")
    text = VIBE.read_text()

    base_touch_idx = text.find('touch "$IMAGE_MARKER"')
    check("[profiles] AC11: base build touch \"$IMAGE_MARKER\" line found",
          base_touch_idx >= 0, "")

    build_arg_lines = [ln for ln in text.splitlines()
                        if "docker build" in ln and '--build-arg "BASE=' in ln]
    check("[profiles] AC11: a docker build line has --build-arg \"BASE=",
          len(build_arg_lines) >= 1, "")

    tag_lines = [ln for ln in text.splitlines()
                 if "docker build" in ln and '-t "$IMAGE_TAG"' in ln]
    check("[profiles] AC11: a docker build line has -t \"$IMAGE_TAG\"",
          len(tag_lines) >= 1, "")

    build_arg_base_and_tag_idx = -1
    for ln in text.splitlines():
        if "docker build" in ln and '--build-arg "BASE=' in ln and '-t "$IMAGE_TAG"' in ln:
            build_arg_base_and_tag_idx = text.find(ln)
            break
    check("[profiles] AC11: a single docker build line has both --build-arg \"BASE= and -t \"$IMAGE_TAG\"",
          build_arg_base_and_tag_idx >= 0, "")
    if build_arg_base_and_tag_idx >= 0 and base_touch_idx >= 0:
        check("[profiles] AC11: profile docker build line is after the base marker touch",
              build_arg_base_and_tag_idx > base_touch_idx, "")

    check("[profiles] AC11: 'export VIBE_IMAGE_TAG' present",
          "export VIBE_IMAGE_TAG" in text, "")

    check("[profiles] AC11: a '◆ profile:' header line present",
          "◆ profile:" in text, "")

    resolve_idx = text.find("resolve_profile ")
    if resolve_idx < 0:
        resolve_idx = text.find("resolve_profile(")
    drift_idx = text.find('image_drift_needs_recreate "$WORKSPACE" "$IMAGE_TAG"')
    check("[profiles] AC11: resolve_profile call found",
          resolve_idx >= 0, "")
    check("[profiles] AC11: image_drift_needs_recreate call found",
          drift_idx >= 0, "")
    if resolve_idx >= 0 and drift_idx >= 0:
        check("[profiles] AC11: resolve_profile invoked before the drift call",
              resolve_idx < drift_idx, f"resolve@{resolve_idx} drift@{drift_idx}")


# ── AC12: docs ───────────────────────────────────────────────────────────

def test_profiles_ac12_docs() -> None:
    """AC12: README, CLAUDE.md, MANUAL-TESTS, TODO, CHANGELOG all document
    the language-profile mechanism."""
    print("\n[profiles] AC12: docs")

    if README_MD.exists():
        readme_text = README_MD.read_text()
        check("[profiles] AC12: README has '### Language profiles'",
              "### Language profiles" in readme_text, "")
        check("[profiles] AC12: README mentions '--profile python'",
              "--profile python" in readme_text, "")
        check("[profiles] AC12: README mentions '.vibe/profile'",
              ".vibe/profile" in readme_text, "")
        check("[profiles] AC12: README mentions 'VIBE_PROFILE'",
              "VIBE_PROFILE" in readme_text, "")
        check("[profiles] AC12: README mentions '~/.vibe/profiles/'",
              "~/.vibe/profiles/" in readme_text, "")
        check("[profiles] AC12: README mentions node 20 / Node 20",
              "node 20" in readme_text or "Node 20" in readme_text, "")
    else:
        check("[profiles] AC12: README.md exists", False, str(README_MD))

    if CLAUDE_MD.exists():
        claude_text = CLAUDE_MD.read_text()
        check("[profiles] AC12: CLAUDE.md mentions 'devcontainer/profiles/'",
              "devcontainer/profiles/" in claude_text, "")
    else:
        check("[profiles] AC12: CLAUDE.md exists", False, str(CLAUDE_MD))

    if MANUAL_TESTS_MD.exists():
        manual_text = MANUAL_TESTS_MD.read_text()
        check("[profiles] AC12: MANUAL-TESTS.md has the profile test (Test 51)",
              "Test 51: `vibe --profile python`" in manual_text, "")
    else:
        check("[profiles] AC12: MANUAL-TESTS.md exists", False, str(MANUAL_TESTS_MD))

    if TODO_MD.exists():
        todo_text = TODO_MD.read_text()
        check("[profiles] AC12: TODO.md item 5 collapses with task_040 pointer",
              "mechanism + `python` shipped (task_040)" in todo_text, "")
    else:
        check("[profiles] AC12: TODO.md exists", False, str(TODO_MD))

    if CHANGELOG_MD.exists():
        changelog_text = CHANGELOG_MD.read_text()
        check("[profiles] AC12: CHANGELOG.md mentions task_040",
              "task_040" in changelog_text, "")
    else:
        check("[profiles] AC12: CHANGELOG.md exists", False, str(CHANGELOG_MD))


# ── AC13: .vibe/profile covered by the managed gitignore block ────────────

def test_profiles_ac13_vibe_profile_gitignored() -> None:
    """AC13: .vibe/profile is covered by the existing managed .vibe/ line —
    a fixture repo carrying the same .gitignore as this repo must ignore
    it."""
    print("\n[profiles] AC13: .vibe/profile is gitignored")
    root_gitignore = REPO / ".gitignore"
    check("[profiles] AC13: root .gitignore exists", root_gitignore.exists(), "")
    if not root_gitignore.exists():
        return
    with tempfile.TemporaryDirectory() as td:
        fixture = Path(td) / "fixture-repo"
        _t23_init_repo(fixture)
        (fixture / ".gitignore").write_text(root_gitignore.read_text())
        r = run(["git", "check-ignore", "-q", ".vibe/profile"], cwd=fixture)
        check("[profiles] AC13: git check-ignore -q .vibe/profile exits 0",
              r.returncode == 0, f"rc={r.returncode} stderr={r.stderr}")
