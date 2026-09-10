"""task_041: per-project extra firewall domains.

Tester-owned, spec-only tests — written against the acceptance criteria, NOT
against an implementation (expect failures until the launcher/firewall lands).

The problem: `devcontainer/init-firewall.sh`'s domain loop is vibe's PUBLIC
default allowlist — every container, every user. A single project needing one
extra host (a private accounting API, an internal registry) must not widen
that shipped default. This adds a per-project channel instead:

    <workspace>/.vibe/domains     one host per line, UNTRACKED  (per-project)
    VIBE_EXTRA_DOMAINS            in ~/.vibe/config             (machine-wide)

Precedence mirrors resolve_profile (checks_14): the workspace file wins, the
config var is the fallback. The untracked requirement mirrors _op_opted_in
(checks_09): a `.vibe/domains` COMMITTED to a repo is refused, so a malicious
PR cannot widen its own container's firewall.

Functions under test:
  - resolve_extra_domains <workspace> <config_value>   (in `vibe`, above the
    VIBE_SOURCE_ONLY guard so _source_vibe_call can reach it)
  - init-firewall.sh's $1 handling + validate_extra_domain

Acceptance criteria:
  AC1  untracked <ws>/.vibe/domains -> its hosts, one per line
  AC2  no file -> VIBE_EXTRA_DOMAINS config value (comma/space separated)
  AC3  file wins over config value
  AC4  comments (#) and blank lines ignored; entries trimmed
  AC5  COMMITTED .vibe/domains refused (warns, falls back to config)
  AC6  file present but not a verifiable git work tree -> refused (fail closed)
  AC7  invalid hostnames dropped with a warning; valid siblings survive
  AC8  duplicates de-duped, first-seen order preserved
  AC9  more than EXTRA_DOMAINS_MAX accepted entries -> capped, warns
  AC10 init-firewall.sh resolves $1 hosts at the OPTIONAL tier only
  AC11 init-firewall.sh re-validates $1 (never digs an unvalidated token)
  AC12 empty/absent $1 -> shipped domain loop unchanged
  AC13 devcontainer.json plumbs VIBE_EXTRA_DOMAINS to init-firewall.sh argv
  AC14 launcher exports VIBE_EXTRA_DOMAINS from resolve_extra_domains
  AC15 docs: README, MANUAL-TESTS, CHANGELOG, .gitignore
"""
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from smoke._core import *  # noqa: F401,F403

DEVCONTAINER_JSON = REPO / "devcontainer" / "devcontainer.json"
README_MD = REPO / "README.md"
MANUAL_TESTS_MD = REPO / "MANUAL-TESTS.md"
CHANGELOG_MD = REPO / "CHANGELOG.md"

EXTRA_DOMAINS_MAX = 32


def test_codex_extra_domains():
    """Phase 1a hosts use the existing local opt-in and CDN refresh path."""
    print("\n[codex] per-project domain plumbing")
    hosts = ["chatgpt.com", "api.openai.com", "auth.openai.com"]
    setup = 'printf "chatgpt.com\\napi.openai.com\\nauth.openai.com\\n" > "$WS/.vibe/domains"'
    out, err, rc = _resolve(_git_ws(setup))
    check("[codex] all hosts resolve through local .vibe/domains", rc == 0 and out == hosts, err)
    out, err, rc = _resolve(_git_ws(setup + '; git -C "$WS" add .vibe/domains'))
    check("[codex] tracked OpenAI allowlist refused", out == [] and "COMMITTED" in err, err)
    firewall = INIT_FIREWALL.read_text()
    for host in hosts:
        check(f"[codex] {host} never added to shipped firewall", host not in firewall, "")
        check(f"[codex] {host} documented for project setup", host in README_MD.read_text(), "")


def _resolve(setup: str, config_value: str = "", env_vars: dict | None = None):
    """Build a fixture workspace, run `setup` against it, then source vibe and
    call `resolve_extra_domains "$WS" "<config_value>"`.

    Returns (stdout_lines, stderr_text, returncode)."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        pre = f'WS={shlex.quote(str(ws))}; {setup}; ' if setup else f'WS={shlex.quote(str(ws))}; '
        call = pre + f'resolve_extra_domains "$WS" {shlex.quote(config_value)}'
        r = _source_vibe_call(env_vars or {}, call)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        return lines, r.stderr, r.returncode


def _git_ws(extra: str = "") -> str:
    """Setup snippet: a real git work tree with an identity, plus `extra`."""
    base = ('git -C "$WS" init -q; '
            'git -C "$WS" config user.email t@users.noreply.github.com; '
            'git -C "$WS" config user.name T; '
            'git -C "$WS" config core.hooksPath /dev/null; '
            'mkdir -p "$WS/.vibe"')
    return base + ("; " + extra if extra else "")


# ── AC1: untracked workspace file is the per-project source ──────────────────

def test_extra_domains_ac1_untracked_file_is_read() -> None:
    print("\n[extra-domains] AC1: untracked <ws>/.vibe/domains is read")
    out, err, rc = _resolve(_git_ws(
        'printf "login.xero.com\\napi.xero.com\\n" > "$WS/.vibe/domains"'))
    check("[extra-domains] AC1: rc 0", rc == 0, err)
    check("[extra-domains] AC1: both hosts returned in order",
          out == ["login.xero.com", "api.xero.com"], repr(out) + err)


# ── AC2: config fallback ─────────────────────────────────────────────────────

def test_extra_domains_ac2_config_fallback() -> None:
    print("\n[extra-domains] AC2: no file -> config value, comma or space split")
    out, err, _ = _resolve(_git_ws(), "login.xero.com, api.xero.com")
    check("[extra-domains] AC2: comma-separated config parsed",
          out == ["login.xero.com", "api.xero.com"], repr(out) + err)
    out2, err2, _ = _resolve(_git_ws(), "a.example.com b.example.com")
    check("[extra-domains] AC2: space-separated config parsed",
          out2 == ["a.example.com", "b.example.com"], repr(out2) + err2)
    out3, _, _ = _resolve(_git_ws(), "")
    check("[extra-domains] AC2: empty config -> no output", out3 == [], repr(out3))


# ── AC3: precedence ──────────────────────────────────────────────────────────

def test_extra_domains_ac3_file_wins_over_config() -> None:
    print("\n[extra-domains] AC3: workspace file beats config value")
    out, err, _ = _resolve(
        _git_ws('printf "from-file.example.com\\n" > "$WS/.vibe/domains"'),
        "from-config.example.com")
    check("[extra-domains] AC3: file wins",
          out == ["from-file.example.com"], repr(out) + err)


# ── AC4: comments, blanks, whitespace ────────────────────────────────────────

def test_extra_domains_ac4_comments_and_blanks_ignored() -> None:
    print("\n[extra-domains] AC4: # comments, blank lines, surrounding space")
    body = ('# Xero, for moneyandeye\\n'
            '\\n'
            '   login.xero.com   \\n'
            'api.xero.com  # inline comment\\n'
            '\\t\\n')
    out, err, _ = _resolve(_git_ws(f'printf "{body}" > "$WS/.vibe/domains"'))
    check("[extra-domains] AC4: only the two hosts survive, trimmed",
          out == ["login.xero.com", "api.xero.com"], repr(out) + err)


# ── AC5: a COMMITTED file cannot widen the firewall ──────────────────────────

def test_extra_domains_ac5_committed_file_refused() -> None:
    print("\n[extra-domains] AC5: committed .vibe/domains refused (PR forgery)")
    setup = _git_ws(
        'printf "evil.example.com\\n" > "$WS/.vibe/domains"; '
        'git -C "$WS" add -f .vibe/domains; '
        'git -C "$WS" commit -q -m add')
    out, err, rc = _resolve(setup, "safe.example.com")
    check("[extra-domains] AC5: committed host NOT allowlisted",
          "evil.example.com" not in out, repr(out))
    check("[extra-domains] AC5: warns that the file is committed",
          "COMMITTED" in err, err)
    check("[extra-domains] AC5: falls back to the config value",
          out == ["safe.example.com"], repr(out) + err)
    check("[extra-domains] AC5: rc still 0 (advisory, not fatal)", rc == 0, err)


# ── AC6: fail closed outside a verifiable work tree ──────────────────────────

def test_extra_domains_ac6_non_git_workspace_refused() -> None:
    print("\n[extra-domains] AC6: file in a non-git dir refused (fail closed)")
    out, err, _ = _resolve(
        'mkdir -p "$WS/.vibe"; printf "evil.example.com\\n" > "$WS/.vibe/domains"')
    check("[extra-domains] AC6: host from an unverifiable tree not allowlisted",
          out == [], repr(out))
    check("[extra-domains] AC6: warns about the git work tree",
          "work tree" in err, err)


# ── AC7: hostname validation ─────────────────────────────────────────────────

def test_extra_domains_ac7_invalid_hostnames_dropped() -> None:
    """The list format is whitespace/comma separated, so a token CONTAINING
    whitespace is by definition two entries — `api.xero.com;curl evil.sh` is
    the entry `api.xero.com;curl` (rejected) plus the entry `evil.sh` (a
    syntactically valid host the user typed). What must never happen is a
    non-hostname reaching `dig`, or any of this reaching a shell; that is what
    these single-token cases pin down, and what the injection test below
    proves by side effect."""
    print("\n[extra-domains] AC7: invalid entries dropped, valid siblings kept")
    bad = [
        "api.xero.com;curl",              # command separator
        "$(id)",                          # command substitution
        "`id`",                           # backtick substitution
        "api.xero.com/../../etc",         # path traversal
        "https://api.xero.com",           # URL, not a hostname
        "-leading-dash.example.com",      # label starts with a dash
        "no-dot-host",                    # not a FQDN
        "1.2.3.4",                        # bare IP, not a name
        "*.xero.com",                     # wildcard
        "a..example.com",                 # empty label
    ]
    for token in bad:
        out, err, rc = _resolve(_git_ws(), f"good.example.com {token}")
        check(f"[extra-domains] AC7: {token!r} dropped",
              out == ["good.example.com"], repr(out) + err)
        check(f"[extra-domains] AC7: {token!r} warned about",
              "ignor" in err.lower() or "invalid" in err.lower(), err)
        check(f"[extra-domains] AC7: {token!r} rc still 0", rc == 0, err)


def test_extra_domains_ac7_valid_hostnames_accepted() -> None:
    print("\n[extra-domains] AC7: legitimate hostnames accepted")
    good = ["login.xero.com", "api.xero.com", "identity.xero.com",
            "a-b.example.co.uk", "x1.y2.example.com"]
    out, err, _ = _resolve(_git_ws(), " ".join(good))
    check("[extra-domains] AC7: all valid hosts kept", out == good, repr(out) + err)


def test_extra_domains_ac7_no_shell_evaluation() -> None:
    """The entries are split by the shell but never EVALUATED by it: a
    command-substitution entry must leave no side effect on disk. This is the
    property that makes it safe for init-firewall.sh — running as root — to
    take the list as argv."""
    print("\n[extra-domains] AC7: entries are never evaluated by a shell")
    with tempfile.TemporaryDirectory() as td:
        canary = Path(td) / "pwned"
        payload = f"$(touch {canary}) `touch {canary}` good.example.com"
        out, err, rc = _resolve(_git_ws(), payload)
        check("[extra-domains] AC7: no command substitution executed",
              not canary.exists(), f"canary {canary} was created")
        check("[extra-domains] AC7: only the real host survives",
              out == ["good.example.com"], repr(out) + err)
        check("[extra-domains] AC7: rc 0", rc == 0, err)


# ── AC8: de-duplication ──────────────────────────────────────────────────────

def test_extra_domains_ac8_deduped_first_seen_order() -> None:
    print("\n[extra-domains] AC8: duplicates collapsed, first-seen order kept")
    out, err, _ = _resolve(_git_ws(), "b.example.com a.example.com b.example.com")
    check("[extra-domains] AC8: deduped in first-seen order",
          out == ["b.example.com", "a.example.com"], repr(out) + err)


# ── AC9: bounded boot cost ───────────────────────────────────────────────────

def test_extra_domains_ac9_capped() -> None:
    print(f"\n[extra-domains] AC9: capped at {EXTRA_DOMAINS_MAX} entries")
    many = " ".join(f"h{i}.example.com" for i in range(EXTRA_DOMAINS_MAX + 5))
    out, err, rc = _resolve(_git_ws(), many)
    check(f"[extra-domains] AC9: at most {EXTRA_DOMAINS_MAX} returned",
          len(out) == EXTRA_DOMAINS_MAX, f"{len(out)} entries")
    check("[extra-domains] AC9: cap is warned about", "cap" in err.lower(), err)
    check("[extra-domains] AC9: rc still 0", rc == 0, err)


# ── AC10-AC12: init-firewall.sh side ─────────────────────────────────────────

def test_extra_domains_ac10_firewall_optional_tier_only() -> None:
    print("\n[extra-domains] AC10: extra domains never join the must-have tier")
    src = INIT_FIREWALL.read_text()
    check("[extra-domains] AC10: MUST_HAVE_DOMAINS is still only Anthropic",
          'MUST_HAVE_DOMAINS="api.anthropic.com"' in src, "")
    check("[extra-domains] AC10: EXTRA_DOMAINS never appended to MUST_HAVE_DOMAINS",
          "MUST_HAVE_DOMAINS=\"${MUST_HAVE_DOMAINS}" not in src
          and "MUST_HAVE_DOMAINS+=" not in src, "")


def test_extra_domains_ac11_firewall_revalidates_argv() -> None:
    print("\n[extra-domains] AC11: init-firewall.sh re-validates its argv")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        snippet = (
            'for t in "api.xero.com;id" "\\$(id)" "-x.example.com" "no-dot" '
            '"1.2.3.4" "*.example.com" "a b.example.com"; do '
            '  if validate_extra_domain "$t"; then echo "ACCEPTED=[$t]"; fi; '
            'done; '
            'for t in login.xero.com api.xero.com a-b.example.co.uk; do '
            '  validate_extra_domain "$t" || echo "REJECTED=[$t]"; '
            'done; echo DONE')
        r, _ = _fw_run(tmp, "exit 1", snippet)
        check("[extra-domains] AC11: validate_extra_domain exists",
              "DONE" in r.stdout, r.stdout + r.stderr)
        check("[extra-domains] AC11: no malicious token accepted",
              "ACCEPTED=" not in r.stdout, r.stdout)
        check("[extra-domains] AC11: no legitimate host rejected",
              "REJECTED=" not in r.stdout, r.stdout)


def _fw_argv(argv: str, tmp: Path):
    """Source init-firewall.sh WITH an argv, under the script's own real shell
    options. Deliberately not _fw_run: that sources with no arguments, and the
    whole point here is $1 — and `IFS=$'\\n\\t'` (init-firewall.sh line 3),
    which removes the SPACE from word splitting and is exactly what a
    space-separated allowlist has to survive."""
    env = _isolate_extras_env(dict(os.environ))
    env.update({"VIBE_FIREWALL_SOURCE_ONLY": "1", "GH_META_CACHE": str(tmp / "c.json")})
    script = (f"source {shlex.quote(str(INIT_FIREWALL))} {shlex.quote(argv)}\n"
              'printf "TOKEN=[%s]\\n" $EXTRA_DOMAINS\n')
    return run(["bash", "-c", script], env=env)


def test_extra_domains_ac11_argv_splits_under_script_ifs() -> None:
    """A space-separated list must reach the resolve loop as SEPARATE tokens.
    init-firewall.sh runs under `IFS=$'\\n\\t'`, so any list joined on spaces
    silently collapses into one unresolvable token — the allowlist would look
    configured and quietly allow nothing."""
    print("\n[extra-domains] AC11: argv splits into tokens under the strict IFS")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _fw_argv("login.xero.com api.xero.com", tmp)
        toks = re.findall(r"TOKEN=\[(.*?)\]", r.stdout)
        check("[extra-domains] AC11: space-separated argv -> two tokens",
              toks == ["login.xero.com", "api.xero.com"], repr(toks) + r.stdout + r.stderr)
        r = _fw_argv("login.xero.com,api.xero.com", tmp)
        toks = re.findall(r"TOKEN=\[(.*?)\]", r.stdout)
        check("[extra-domains] AC11: comma-separated argv -> two tokens",
              toks == ["login.xero.com", "api.xero.com"], repr(toks) + r.stdout + r.stderr)
        r = _fw_argv("good.example.com bad;token *.glob 1.2.3.4", tmp)
        toks = re.findall(r"TOKEN=\[(.*?)\]", r.stdout)
        check("[extra-domains] AC11: invalid tokens dropped, valid one kept",
              toks == ["good.example.com"], repr(toks) + r.stdout + r.stderr)
        r = _fw_argv("", tmp)
        toks = re.findall(r"TOKEN=\[(.*?)\]", r.stdout)
        check("[extra-domains] AC11: empty argv -> no tokens",
              toks in ([], [""]), repr(toks) + r.stdout)


def test_extra_domains_ac12_shipped_loop_unchanged() -> None:
    print("\n[extra-domains] AC12: shipped default allowlist is unchanged")
    src = INIT_FIREWALL.read_text()
    for host in ("registry.npmjs.org", "api.anthropic.com", "api.zotero.org",
                 "seed.radicle.garden", "download.swift.org", "sentry.io",
                 "statsig.com", "marketplace.visualstudio.com",
                 "vscode.blob.core.windows.net", "update.code.visualstudio.com"):
        check(f"[extra-domains] AC12: {host} still shipped",
              f'"{host}"' in src, "")
    check("[extra-domains] AC12: no vendor host hardcoded into the shipped loop",
          "xero.com" not in src.lower(), "Xero must never reach the public allowlist")


# ── AC13-AC14: plumbing ──────────────────────────────────────────────────────

def test_extra_domains_ac13_devcontainer_plumbing() -> None:
    print("\n[extra-domains] AC13: devcontainer.json passes the list as argv")
    cfg = json.loads(DEVCONTAINER_JSON.read_text())
    psc = cfg.get("postStartCommand", "")
    check("[extra-domains] AC13: init-firewall.sh receives VIBE_EXTRA_DOMAINS",
          'init-firewall.sh "${VIBE_EXTRA_DOMAINS:-}"' in psc, psc)
    check("[extra-domains] AC13: GITHUB_TOKEN still piped on stdin",
          'printf %s "${GITHUB_TOKEN:-}" | sudo /usr/local/bin/init-firewall.sh' in psc, psc)
    # containerEnv, NOT remoteEnv: remoteEnv is applied by the devcontainer CLI
    # when it runs commands and never lands in the container's own config, so
    # `docker inspect` cannot see it — and without that, extra_domains_drift
    # has nothing to compare and a changed domain list would silently reuse a
    # container whose firewall was built from the OLD list. Safe here only
    # because this value is not a secret (unlike GITHUB_TOKEN/ZOTERO_API_KEY,
    # which stay in remoteEnv precisely to keep them out of the container config).
    check("[extra-domains] AC13: containerEnv passthrough present",
          cfg.get("containerEnv", {}).get("VIBE_EXTRA_DOMAINS")
          == "${localEnv:VIBE_EXTRA_DOMAINS}", str(cfg.get("containerEnv")))
    check("[extra-domains] AC13: not in remoteEnv (docker inspect must see it)",
          "VIBE_EXTRA_DOMAINS" not in cfg.get("remoteEnv", {}),
          str(cfg.get("remoteEnv")))


def test_extra_domains_ac14_launcher_exports() -> None:
    print("\n[extra-domains] AC14: launcher resolves and exports the list")
    src = VIBE.read_text()
    check("[extra-domains] AC14: resolve_extra_domains defined",
          "resolve_extra_domains()" in src, "")
    check("[extra-domains] AC14: reached from the launch path via the wrapper",
          'vibe_resolve_extra_domains_for_launch "$WORKSPACE"' in src, "")
    check("[extra-domains] AC14: the wrapper calls the resolver in-shell",
          'resolve_extra_domains "$ws" "$config" >/dev/null' in src, "")
    check("[extra-domains] AC14: VIBE_EXTRA_DOMAINS exported for ${localEnv:}",
          "export VIBE_EXTRA_DOMAINS" in src, "")
    guard = src.index('[ "${VIBE_SOURCE_ONLY:-}" = "1" ] && return 0')
    check("[extra-domains] AC14: defined above the VIBE_SOURCE_ONLY guard",
          src.index("resolve_extra_domains()") < guard, "")


# ── AC16: CRLF line endings ──────────────────────────────────────────────────

def test_extra_domains_ac16_crlf_file_is_accepted() -> None:
    """A .vibe/domains saved by a Windows editor (or pasted through one) must
    work. Without a CR trim the LDH validator rejects `api.example.com\r` and
    tells the user their own correctly-spelled hostname is invalid, with
    nothing on screen to explain why. resolve_profile trims CR for exactly
    this reason."""
    print("\n[extra-domains] AC16: CRLF file parses, no bogus 'invalid' warning")
    out, err, _ = _resolve(_git_ws(
        r'printf "a.example.com\r\nb.example.com\r\n" > "$WS/.vibe/domains"'))
    check("[extra-domains] AC16: both CRLF hosts resolved",
          out == ["a.example.com", "b.example.com"], repr(out) + err)
    check("[extra-domains] AC16: no invalid-domain warning",
          "ignoring invalid" not in err, err)


def test_extra_domains_ac16_firewall_strips_cr() -> None:
    print("\n[extra-domains] AC16: init-firewall.sh strips CR from its argv")
    with tempfile.TemporaryDirectory() as td:
        r = _fw_argv("a.example.com\r b.example.com", Path(td))
        toks = re.findall(r"TOKEN=\[(.*?)\]", r.stdout)
        check("[extra-domains] AC16: CR-bearing token still valid",
              toks == ["a.example.com", "b.example.com"], repr(toks) + r.stdout)


# ── AC17: launch-header attribution ──────────────────────────────────────────

def test_extra_domains_ac17_source_attribution() -> None:
    """The launch header names WHERE a firewall hole came from, and is the
    documented blast-radius announcement — so it must not credit a file the
    launcher just refused. EXTRA_DOMAINS_SOURCE is set by the same code path
    that decides which source to read, never re-derived from `[ -f ]`."""
    print("\n[extra-domains] AC17: header attributes the list to the real source")

    def _src(setup: str, config: str = "") -> str:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"; ws.mkdir()
            call = (f'WS={shlex.quote(str(ws))}; {setup}; '
                    f'resolve_extra_domains "$WS" {shlex.quote(config)} >/dev/null; '
                    'echo "SRC=[$EXTRA_DOMAINS_SOURCE]"')
            r = _source_vibe_call({}, call)
            m = re.search(r"SRC=\[(.*?)\]", r.stdout)
            return m.group(1) if m else f"<no match: {r.stdout}{r.stderr}>"

    check("[extra-domains] AC17: untracked file -> .vibe/domains",
          _src(_git_ws('printf "a.example.com\n" > "$WS/.vibe/domains"'))
          == ".vibe/domains", "")
    check("[extra-domains] AC17: config only -> VIBE_EXTRA_DOMAINS",
          _src(_git_ws(), "a.example.com") == "VIBE_EXTRA_DOMAINS", "")
    # The bug this pins: a COMMITTED file is refused and the config value is
    # used, but the header credited the rejected file because it re-tested
    # `[ -f "$WORKSPACE/.vibe/domains" ]` instead of asking what was read.
    check("[extra-domains] AC17: committed file refused -> credits the config",
          _src(_git_ws('printf "evil.example.com\n" > "$WS/.vibe/domains"; '
                       'git -C "$WS" add -f .vibe/domains; '
                       'git -C "$WS" commit -q -m x'),
               "safe.example.com") == "VIBE_EXTRA_DOMAINS", "")


def test_extra_domains_ac17_call_site_pattern_under_set_u() -> None:
    """Reproduce the LAUNCHER's own call sequence, not the function in
    isolation. AC17 above called resolve_extra_domains directly, so its global
    survived; the launcher assigned through `$(...)`, a SUBSHELL, which throws
    EXTRA_DOMAINS_SOURCE away — and `set -u` then killed the launch at the
    header line with `EXTRA_DOMAINS_SOURCE: unbound variable`, after the image
    had already built. The contract this pins: after the launcher's own
    sequence, in the PARENT shell, both the list and its source are set."""
    print("\n[extra-domains] AC17: launcher call site keeps both outputs (set -u)")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"; ws.mkdir()
        setup = _git_ws('printf "a.example.com\nb.example.com\n" > "$WS/.vibe/domains"')
        call = (f'WS={shlex.quote(str(ws))}; {setup}; '
                'WORKSPACE="$WS"; '
                # verbatim from the launcher, including `set -u` being active
                'set -u; '
                'vibe_resolve_extra_domains_for_launch "$WORKSPACE" "${VIBE_EXTRA_DOMAINS:-}"; '
                'echo "LIST=[$VIBE_EXTRA_DOMAINS]"; '
                'echo "SRC=[$EXTRA_DOMAINS_SOURCE]"')
        r = _source_vibe_call({}, call)
        check("[extra-domains] AC17: call site exits 0 under set -u",
              r.returncode == 0, r.stdout + r.stderr)
        check("[extra-domains] AC17: no unbound-variable error",
              "unbound variable" not in r.stderr, r.stderr)
        check("[extra-domains] AC17: list survives as a space-separated string",
              "LIST=[a.example.com b.example.com]" in r.stdout, r.stdout + r.stderr)
        check("[extra-domains] AC17: source survives into the parent shell",
              "SRC=[.vibe/domains]" in r.stdout, r.stdout + r.stderr)


def test_extra_domains_ac17_header_never_unbound() -> None:
    """With no domains configured at all — the case every existing project is
    in — the header block must not reference an unset variable under `set -u`."""
    print("\n[extra-domains] AC17: header block is safe with nothing configured")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"; ws.mkdir()
        call = (f'WS={shlex.quote(str(ws))}; {_git_ws()}; WORKSPACE="$WS"; set -u; '
                'vibe_resolve_extra_domains_for_launch "$WORKSPACE" "${VIBE_EXTRA_DOMAINS:-}"; '
                'if [ -n "$VIBE_EXTRA_DOMAINS" ]; then '
                '  echo "     domains : firewall also allows ${VIBE_EXTRA_DOMAINS} (via ${EXTRA_DOMAINS_SOURCE})"; '
                'fi; echo OK')
        r = _source_vibe_call({}, call)
        check("[extra-domains] AC17: header block runs clean with no domains",
              r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr)
        check("[extra-domains] AC17: no unbound-variable error",
              "unbound variable" not in r.stderr, r.stderr)


def test_extra_domains_ac17_launcher_uses_the_wrapper() -> None:
    """The launcher must not reintroduce the subshell: no `$(resolve_extra_domains`
    anywhere in `vibe`."""
    print("\n[extra-domains] AC17: launcher does not call the resolver in a subshell")
    src = VIBE.read_text()
    # Comment lines are exempt — the wrapper's own docstring quotes the broken
    # form on purpose, so that the next person to touch this reads why.
    offenders = [ln for ln in src.splitlines()
                 if "$(resolve_extra_domains" in ln and not ln.lstrip().startswith("#")]
    check("[extra-domains] AC17: no command-substitution call site",
          offenders == [], repr(offenders))
    check("[extra-domains] AC17: wrapper defined",
          "vibe_resolve_extra_domains_for_launch()" in src, "")
    check("[extra-domains] AC17: wrapper is what the launch path calls",
          'vibe_resolve_extra_domains_for_launch "$WORKSPACE"' in src, "")


# ── AC18: changing the list must recreate the container ──────────────────────

def test_extra_domains_ac18_drift_comparator() -> None:
    """extra_domains_drift is the sibling of shared_repos_mount_drift /
    projects_bind_mount_drift: a pure comparator emitting "1" iff reusing the
    running container would keep a firewall built from a STALE domain list.
    Without it, editing .vibe/domains and relaunching prints a header claiming
    the host is allowed while the container's ipset still says otherwise."""
    print("\n[extra-domains] AC18: drift comparator forces a recreate")

    def _drift(desired: str, actual: str) -> str:
        r = _source_vibe_call({}, f'extra_domains_drift {shlex.quote(desired)} '
                                  f'{shlex.quote(actual)}')
        return r.stdout.strip()

    check("[extra-domains] AC18: no container (NONE) is never drift",
          _drift("a.example.com", "NONE") == "", "")
    check("[extra-domains] AC18: unchanged list -> no drift",
          _drift("a.example.com b.example.com", "a.example.com b.example.com") == "", "")
    check("[extra-domains] AC18: added domain -> drift",
          _drift("a.example.com b.example.com", "a.example.com") == "1", "")
    check("[extra-domains] AC18: removed domain -> drift",
          _drift("a.example.com", "a.example.com b.example.com") == "1", "")
    check("[extra-domains] AC18: both empty -> no drift", _drift("", "") == "", "")
    check("[extra-domains] AC18: list added to a container that had none -> drift",
          _drift("a.example.com", "") == "1", "")
    check("[extra-domains] AC18: list removed entirely -> drift",
          _drift("", "a.example.com") == "1", "")


def test_extra_domains_ac18_drift_wired_into_launch() -> None:
    print("\n[extra-domains] AC18: drift folded into the recreate decision")
    src = VIBE.read_text()
    check("[extra-domains] AC18: extra_domains_drift defined",
          "extra_domains_drift()" in src, "")
    check("[extra-domains] AC18: container_env_value reads Config.Env",
          "container_env_value()" in src and ".Config.Env" in src, "")
    check("[extra-domains] AC18: drift feeds remove_existing_flag",
          "${drift_marker}${mount_drift}${projects_drift}${domains_drift}" in src, "")
    check("[extra-domains] AC18: recreate is announced to the user",
          "extra firewall domains changed" in src, "")


# ── AC15: documentation ──────────────────────────────────────────────────────

def test_extra_domains_ac15_docs() -> None:
    print("\n[extra-domains] AC15: README / MANUAL-TESTS / CHANGELOG / gitignore")
    readme = README_MD.read_text()
    check("[extra-domains] AC15: README documents the workspace file",
          ".vibe/domains" in readme, "")
    check("[extra-domains] AC15: README documents the config var",
          "VIBE_EXTRA_DOMAINS" in readme, "")
    check("[extra-domains] AC15: README states the untracked requirement",
          "untracked" in readme.lower(), "")
    check("[extra-domains] AC15: MANUAL-TESTS has an end-to-end entry",
          "VIBE_EXTRA_DOMAINS" in MANUAL_TESTS_MD.read_text()
          or ".vibe/domains" in MANUAL_TESTS_MD.read_text(), "")
    check("[extra-domains] AC15: CHANGELOG entry",
          ".vibe/domains" in CHANGELOG_MD.read_text(), "")
    gitignore = (REPO / ".gitignore").read_text()
    check("[extra-domains] AC15: .vibe/domains gitignored so it stays untracked",
          ".vibe/domains" in gitignore, gitignore)
