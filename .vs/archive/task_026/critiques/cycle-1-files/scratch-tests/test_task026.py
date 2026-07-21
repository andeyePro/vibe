#!/usr/bin/env python3
"""Scratch red/green tests for task_026 (vibe pat rotation + 401 reprompt).

Not committed, not Tester-owned. Exercises the pinned behaviours before/while
implementing rotate_token, stored_token_rejected, maybe_reprompt_stored_token,
and vibe pat subcommand parsing. Run: python3 .vs/cycle-1/scratch-tests/test_task026.py
"""
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

VIBE = Path(__file__).resolve().parents[3] / "vibe"
FIXTURE_TOKEN = "ghp_task026_fixture_token"

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")
        if detail:
            print(textwrap.indent(str(detail)[-1500:], "       "))


def run(cmd, env=None, cwd=None, input_bytes=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, input=input_bytes)


def base_env(home):
    return {
        **os.environ,
        "HOME": str(home),
        "VIBE_CONFIG": f"{home}/no-config",
    }


# ── AC1: too many args / bad slug / --help ──────────────────────────────────
def test_ac1_arg_parsing():
    print("\n[AC1: vibe pat arg parsing]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)

        r = run(["bash", str(VIBE), "pat", "a", "b", "c"], env=env, cwd=td)
        check("too many args exits 1", r.returncode == 1, r)
        check("too many args: usage on stderr", "Usage" in r.stderr, r.stderr)
        check("nothing on stdout", r.stdout.strip() == "", r.stdout)

        r = run(["bash", str(VIBE), "pat", "not-a-slug"], env=env, cwd=td)
        check("bad slug exits 1", r.returncode == 1, r)
        check("bad slug: error on stderr", r.stderr.strip() != "", r.stderr)

        r = run(["bash", str(VIBE), "pat", "--help"], env=env, cwd=td)
        check("--help exits 0", r.returncode == 0, r)
        check("--help prints to stdout", "vibe pat" in r.stdout, r.stdout)

        r = run(["bash", str(VIBE), "pat", "-h"], env=env, cwd=td)
        check("-h exits 0", r.returncode == 0, r)

        # token store untouched
        check("no tokens file created", not (home / ".vibe" / "tokens").exists())


# ── AC2: overwrite existing line, preserve others, chmod 600 ───────────────
def test_ac2_overwrite_preserves():
    print("\n[AC2: vibe pat owner/repo overwrite + preserve]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        tokens_dir = home / ".vibe"
        tokens_dir.mkdir(parents=True)
        tokens_file = tokens_dir / "tokens"
        tokens_file.write_text(
            "owner/repo=ghp_old_token\n"
            "ZOTERO_API_KEY=zotero123\n"
            "OPENPROJECT_MCP_BEARER=YmFzZTY0dG9rZW4=\n"
        )
        os.chmod(tokens_file, 0o600)

        r = run(["bash", str(VIBE), "pat", "owner/repo"], env=env, cwd=td,
                 input_bytes=FIXTURE_TOKEN + "\n")
        check("exits 0", r.returncode == 0, r)
        check("stdout has Repo: line", "Repo: owner/repo" in r.stdout, r.stdout)
        check("stdout has saved line", "✓ Token saved" in r.stdout, r.stdout)
        check("stored token found line",
              "stored token found — it will be replaced" in r.stdout, r.stdout)

        content = tokens_file.read_text()
        check("owner/repo overwritten", f"owner/repo={FIXTURE_TOKEN}" in content, content)
        check("old token gone", "ghp_old_token" not in content, content)
        check("ZOTERO_API_KEY preserved", "ZOTERO_API_KEY=zotero123" in content, content)
        check("OPENPROJECT_MCP_BEARER preserved (trailing =)",
              "OPENPROJECT_MCP_BEARER=YmFzZTY0dG9rZW4=" in content, content)
        check("still 3 lines", len(content.splitlines()) == 3, content)

        mode = stat.S_IMODE(os.stat(tokens_file).st_mode)
        check("chmod 600", oct(mode) == "0o600", oct(mode))


# ── AC3: empty stdin (both ways) aborts, store byte-identical ──────────────
def test_ac3_empty_stdin_aborts():
    print("\n[AC3: empty stdin aborts, byte-identical store]")
    for label, stdin_bytes in [("closed/EOF", b""), ("lone newline", b"\n")]:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            env = base_env(home)
            tokens_dir = home / ".vibe"
            tokens_dir.mkdir(parents=True)
            tokens_file = tokens_dir / "tokens"
            original = "owner/repo=ghp_existing\n"
            tokens_file.write_text(original)
            os.chmod(tokens_file, 0o600)

            r = subprocess.run(["bash", str(VIBE), "pat", "owner/repo"],
                                capture_output=True, env=env, cwd=td,
                                input=stdin_bytes)
            check(f"[{label}] exits 1", r.returncode == 1, r)
            check(f"[{label}] abort line on stderr",
                  b"aborted \xe2\x80\x94 token store unchanged" in r.stderr, r.stderr)
            check(f"[{label}] store byte-identical",
                  tokens_file.read_text() == original, tokens_file.read_text())


# ── AC4: no-arg form, detect_github_repo success/failure ───────────────────
def test_ac4_no_arg_detect():
    print("\n[AC4: vibe pat no-arg detect_github_repo]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        nogit_dir = Path(td) / "nogit"
        nogit_dir.mkdir()
        r = run(["bash", str(VIBE), "pat"], env=env, cwd=str(nogit_dir), input_bytes="")
        check("no-git dir: exits 1", r.returncode == 1, r)
        check("no-git dir: stderr hint", r.stderr.strip() != "", r.stderr)

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        repo_dir = Path(td) / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
        subprocess.run(["git", "remote", "add", "origin",
                         "https://github.com/someowner/somerepo.git"],
                        cwd=repo_dir, check=True)
        r = run(["bash", str(VIBE), "pat"], env=env, cwd=str(repo_dir), input_bytes="")
        check("git checkout: exits 1 (empty stdin -> abort path)", r.returncode == 1, r)
        check("git checkout: prints Repo: someowner/somerepo",
              "Repo: someowner/somerepo" in r.stdout, r.stdout)


# ── AC5/AC6: stored_token_rejected via curl shim ────────────────────────────
def make_shim(shim_dir: Path, name: str, body: str):
    shim_dir.mkdir(parents=True, exist_ok=True)
    p = shim_dir / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(0o755)
    return p


def source_and_call_rejected(env, repo, token, cwd):
    script = f"""
    set +e
    export VIBE_SOURCE_ONLY=1
    source {shlex.quote(str(VIBE))}
    if stored_token_rejected {shlex.quote(repo)} {shlex.quote(token)}; then
      echo "REJECTED=1"
    else
      echo "REJECTED=0"
    fi
    """
    return run(["bash", "-c", script], env=env, cwd=cwd)


def test_ac5_ac6_stored_token_rejected():
    print("\n[AC5/AC6: stored_token_rejected via curl shim]")
    cases = [
        ("401", '#!/bin/bash\necho -n "401"\nexit 0\n', True),
        ("200", '#!/bin/bash\necho -n "200"\nexit 0\n', False),
        ("404", '#!/bin/bash\necho -n "404"\nexit 0\n', False),
        ("000", '#!/bin/bash\necho -n "000"\nexit 7\n', False),
        ("nonzero-empty", '#!/bin/bash\nexit 1\n', False),
    ]
    for label, shim_body, expect_rejected in cases:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            env = base_env(home)
            shim_dir = Path(td) / "shimbin"
            argv_log = Path(td) / "argv.log"
            stdin_log = Path(td) / "stdin.log"
            body = shim_body.replace(
                "#!/bin/bash\n",
                f'#!/bin/bash\nprintf \'%s\\n\' "$*" > {shlex.quote(str(argv_log))}\ncat > {shlex.quote(str(stdin_log))}\n',
                1,
            )
            make_shim(shim_dir, "curl", body)
            env["PATH"] = f"{shim_dir}:{env['PATH']}"
            r = source_and_call_rejected(env, "owner/repo", FIXTURE_TOKEN, td)
            got_rejected = "REJECTED=1" in r.stdout
            check(f"[{label}] rejected={expect_rejected}", got_rejected == expect_rejected, r)

            if argv_log.exists():
                argv = argv_log.read_text()
                check(f"[{label}] argv has api.github.com/repos/owner/repo",
                      "api.github.com/repos/owner/repo" in argv, argv)
                check(f"[{label}] argv has -K", "-K" in argv, argv)
                check(f"[{label}] argv lacks fixture token", FIXTURE_TOKEN not in argv, argv)
            if stdin_log.exists():
                stdin_content = stdin_log.read_text()
                check(f"[{label}] stdin has Authorization header",
                      f"Authorization: Bearer {FIXTURE_TOKEN}" in stdin_content, stdin_content)

            # AC7: fixture token never in captured stdout/stderr
            check(f"[{label}] token absent from stdout+stderr",
                  FIXTURE_TOKEN not in (r.stdout + r.stderr), r.stdout + r.stderr)


# ── AC8: maybe_reprompt_stored_token branches ───────────────────────────────
def call_wrapper(env, cwd, extra_setup, call_args):
    script = f"""
    set +e
    export VIBE_SOURCE_ONLY=1
    source {shlex.quote(str(VIBE))}
    {extra_setup}
    if maybe_reprompt_stored_token {call_args}; then
      echo "WRAPPER_RET=0"
    else
      echo "WRAPPER_RET=$?"
    fi
    """
    return run(["bash", "-c", script], env=env, cwd=cwd)


def test_ac8_wrapper():
    print("\n[AC8: maybe_reprompt_stored_token]")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        env["VIBE_PAT_CHECK"] = "0"
        setup = """
        stored_token_rejected() { echo "STUB_REJECTED_CALLED" >&2; return 0; }
        setup_token() { echo "STUB_SETUP_CALLED $1" >&2; }
        """
        r = call_wrapper(env, td, setup, f'owner/repo {FIXTURE_TOKEN}')
        check("(a) VIBE_PAT_CHECK=0: neither stub called",
              "STUB_REJECTED_CALLED" not in r.stderr and "STUB_SETUP_CALLED" not in r.stderr, r)
        check("(a) returns 0", "WRAPPER_RET=0" in r.stdout, r.stdout)

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        setup = """
        stored_token_rejected() { echo "STUB_REJECTED_CALLED" >&2; return 0; }
        setup_token() { echo "STUB_SETUP_CALLED $1" >&2; }
        """
        r = call_wrapper(env, td, setup, 'owner/repo ""')
        check("(b) empty token: neither stub called",
              "STUB_REJECTED_CALLED" not in r.stderr and "STUB_SETUP_CALLED" not in r.stderr, r)
        check("(b) returns 0", "WRAPPER_RET=0" in r.stdout, r.stdout)

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        setup = """
        stored_token_rejected() { return 0; }
        setup_token() { echo "STUB_SETUP_CALLED $1" >&2; }
        """
        r = call_wrapper(env, td, setup, f'owner/repo {FIXTURE_TOKEN}')
        check("(c) rejection=0: warning emitted",
              "was rejected by GitHub" in r.stderr, r.stderr)
        check("(c) setup_token stub called with repo",
              "STUB_SETUP_CALLED owner/repo" in r.stderr, r.stderr)
        check("(c) returns 0", "WRAPPER_RET=0" in r.stdout, r.stdout)

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        env = base_env(home)
        setup = """
        stored_token_rejected() { return 1; }
        setup_token() { echo "STUB_SETUP_CALLED $1" >&2; }
        """
        r = call_wrapper(env, td, setup, f'owner/repo {FIXTURE_TOKEN}')
        check("(d) rejection=1: setup_token NOT called",
              "STUB_SETUP_CALLED" not in r.stderr, r.stderr)
        check("(d) no warning", "was rejected by GitHub" not in r.stderr, r.stderr)
        check("(d) returns 0", "WRAPPER_RET=0" in r.stdout, r.stdout)


def test_ac8_static_placement():
    print("\n[AC8: static placement of call site]")
    text = VIBE.read_text()
    idx_start = text.find('GITHUB_TOKEN=$(lookup_token "$GITHUB_REPO")')
    check("found lookup_token call site", idx_start != -1)
    # find the enclosing if/else/fi block
    snippet = text[idx_start:idx_start + 800]
    idx_else = snippet.find("else")
    idx_fi = snippet.find("\nfi", idx_else)
    check("has else before fi", idx_else != -1 and idx_fi != -1, snippet)
    between = snippet[idx_else:idx_fi]
    check("call line inside else..fi (stored-token branch)",
          'maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"' in between, between)
    idx_if_empty = snippet.find('if [ -z "$GITHUB_TOKEN" ]')
    before_else = snippet[idx_if_empty:idx_else]
    check("call NOT in the empty-token (fresh-paste) branch",
          'maybe_reprompt_stored_token' not in before_else, before_else)


# ── AC9: vibe --help contains vibe pat + HOST shell ────────────────────────
def test_ac9_help_and_regressions():
    print("\n[AC9: vibe --help content]")
    env = {**os.environ}
    r = run(["bash", str(VIBE), "--help"], env=env)
    check("--help exits 0", r.returncode == 0, r)
    check("--help has vibe pat line", "vibe pat" in r.stdout, r.stdout)
    check("--help has HOST shell phrase", "HOST shell" in r.stdout, r.stdout)


# ── AC10: README / MANUAL-TESTS content ─────────────────────────────────────
def test_ac10_docs():
    print("\n[AC10: doc content]")
    readme = (VIBE.parent / "README.md").read_text()
    check("README has vibe pat", "vibe pat" in readme)
    check("README has 401", "401" in readme)
    manual = (VIBE.parent / "MANUAL-TESTS.md").read_text()
    check("MANUAL-TESTS has vibe pat", "vibe pat" in manual)
    check("MANUAL-TESTS has VIBE_PAT_CHECK=0", "VIBE_PAT_CHECK=0" in manual)


if __name__ == "__main__":
    if not shutil.which("bash"):
        print("bash not found")
        sys.exit(1)
    test_ac1_arg_parsing()
    test_ac2_overwrite_preserves()
    test_ac3_empty_stdin_aborts()
    test_ac4_no_arg_detect()
    test_ac5_ac6_stored_token_rejected()
    test_ac8_wrapper()
    test_ac8_static_placement()
    test_ac9_help_and_regressions()
    test_ac10_docs()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
