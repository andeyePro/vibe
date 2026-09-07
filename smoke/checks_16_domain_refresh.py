"""task_042: reactive re-resolve for CDN-fronted extra allowlist domains.

The problem task_041 shipped with: `init-firewall.sh` resolves the project's
extra domains ONCE, at container start, and pins those addresses into the
`allowed-domains` ipset. Hosts behind a CDN (Akamai, Cloudflare, Fastly) move
to a different edge within the hour, so an allowlisted host silently stops
being reachable mid-session — DNS still resolves, the packet is REJECTed, and
the launch header still (truthfully, of boot time) says the host is allowed.
Observed 2026-09-06 against api.xero.com in moneyandeye.

Martin's design call (2026-09-07): REACTIVE, not a timer. A vibe left open for
weeks must not re-resolve thousands of times for nothing, so the fix is a
small additive script plus a CLAUDE.md fragment that teaches every session to
run it when a request fails in the shape a stale pin produces.

Functions/artefacts under test:
  - devcontainer/refresh-extra-domains.sh (new; argv-less, additive only)
  - init-firewall.sh's extra-domain state file write
  - devcontainer/Dockerfile COPY + chmod + sudoers entry
  - devcontainer/claude-md/extra-domains-refresh.md + its install gate

Acceptance criteria:
  AC1  the script exists, is executable, and is a bash script
  AC2  it takes NO argv (never reads $1) - a caller cannot widen the allowlist
  AC3  init-firewall.sh writes the validated list to the state file, one/line
  AC4  no extras this launch -> the state file is REMOVED, not left stale
  AC5  Dockerfile COPYs it, chmods it, and grants an argv-less NOPASSWD rule
  AC6  additive only: no ipset flush/destroy/del, no iptables, no /meta fetch
  AC7  valid domains -> `ipset -exist add` for every resolved A record
  AC8  an invalid state-file entry is dropped with a warning; siblings survive
  AC9  absent/empty state file -> exit 0, no ipset mutation
  AC10 the ipset not existing -> exit 1 and a "not initialised" message
  AC11 every domain failing to resolve -> exit 1 (a real failure)
  AC12 partial resolution -> exit 0 (the caller's domain may be the good one)
  AC13 entries capped at EXTRA_DOMAINS_MAX
  AC14 the CLAUDE.md fragment names the exact command and forbids the timer
  AC15 the fragment installs only when VIBE_EXTRA_DOMAINS is non-empty
  AC16 docs: README, MANUAL-TESTS, CHANGELOG
  AC17 the state file's provenance is checked before it is trusted (security
       review): a symlink, a non-regular file, or one not owned by the uid
       running the script is refused, because this is root-read input that
       widens the firewall - the same argument init-firewall.sh makes for
       GH_META_CACHE
  AC18 numeric env knobs are validated before reaching an arithmetic context:
       `$(( ))` evaluates a variable's CONTENTS recursively, so a non-numeric
       value is root RCE by any route that carries the environment
"""
import os
import subprocess
import tempfile
from pathlib import Path

from smoke._core import *  # noqa: F401,F403

REFRESH_SH = REPO / "devcontainer" / "refresh-extra-domains.sh"
DOCKERFILE = REPO / "devcontainer" / "Dockerfile"
FRAGMENT_MD = REPO / "devcontainer" / "claude-md" / "extra-domains-refresh.md"
README_MD = REPO / "README.md"
MANUAL_TESTS_MD = REPO / "MANUAL-TESTS.md"
CHANGELOG_MD = REPO / "CHANGELOG.md"

EXTRA_DOMAINS_MAX = 32

# A stub `dig` that answers for good*.example.com and is silent for dead ones,
# and a stub `ipset` that records every add. Both are written into a tmp bin
# dir put at the FRONT of PATH, so the script under test never touches the
# real resolver or the real firewall.
_STUB_DIG = """#!/bin/bash
d="${!#}"
case "$d" in
  good.example.com)  echo "good.example.com. 20 IN A 2.21.15.114"
                     echo "good.example.com. 20 IN A 2.21.15.130" ;;
  other.example.com) echo "other.example.com. 20 IN A 23.45.67.89" ;;
  cap*.example.com)  echo "$d. 20 IN A 10.0.0.1" ;;
  bogusip.example.com) echo "bogusip.example.com. 20 IN A 999.1.1.1" ;;
  *) : ;;
esac
"""

_STUB_IPSET_PRESENT = """#!/bin/bash
case "$1" in
  list) echo "allowed-domains"; echo "unrelated-set" ;;
  -exist) printf '%s\\n' "$*" >> "$ADDS_LOG" ;;
esac
exit 0
"""

_STUB_IPSET_ABSENT = """#!/bin/bash
case "$1" in
  list) echo "unrelated-set" ;;
  -exist) printf '%s\\n' "$*" >> "$ADDS_LOG" ;;
esac
exit 0
"""


def _refresh_run(tmp: Path, state_lines, ipset_present: bool = True, env_extra=None):
    """Run refresh-extra-domains.sh against a stubbed dig/ipset and a state
    file built from `state_lines`. Returns (CompletedProcess, [add-args])."""
    binn = tmp / "bin"
    binn.mkdir(exist_ok=True)
    (binn / "dig").write_text(_STUB_DIG)
    (binn / "ipset").write_text(
        _STUB_IPSET_PRESENT if ipset_present else _STUB_IPSET_ABSENT)
    for f in ("dig", "ipset"):
        (binn / f).chmod(0o755)
    state = tmp / "extra-domains"
    state.write_text("".join(l + "\n" for l in state_lines))
    adds = tmp / "adds.log"
    adds.write_text("")

    env = _isolate_extras_env(dict(os.environ))
    env["PATH"] = f"{binn}:{env.get('PATH', '')}"
    env["ADDS_LOG"] = str(adds)
    env["VIBE_EXTRA_DOMAINS_STATE"] = str(state)
    env["REFRESH_DNS_ATTEMPTS"] = "1"
    env["REFRESH_DNS_BACKOFF"] = "0"
    if env_extra:
        env.update(env_extra)
    r = run(["bash", str(REFRESH_SH)], env=env)
    added = [ln for ln in adds.read_text().splitlines() if ln.strip()]
    return r, added


# ── AC1/AC2/AC6: shape of the script ────────────────────────────────────────

def test_refresh_ac1_ac2_ac6_script_shape() -> None:
    print("\n[domain-refresh] AC1/AC2/AC6: argv-less, additive-only script")
    check("[domain-refresh] AC1: refresh-extra-domains.sh exists",
          REFRESH_SH.is_file(), str(REFRESH_SH))
    if not REFRESH_SH.is_file():
        return
    src = REFRESH_SH.read_text()
    check("[domain-refresh] AC1: executable bit set in the repo",
          os.access(REFRESH_SH, os.X_OK), "chmod +x devcontainer/refresh-extra-domains.sh")
    check("[domain-refresh] AC1: bash shebang + strict mode",
          src.startswith("#!/bin/bash") and "set -euo pipefail" in src, src[:80])

    # AC2: no positional parameter is ever consulted. `$1`/`$@`/`$*` inside the
    # two helpers is fine (they take named args); what must not appear is a
    # read of the SCRIPT's own argv at top level.
    body = "\n".join(
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#"))
    top_level_argv = [
        ln for ln in body.splitlines()
        if ('"${1:-}"' in ln or ln.strip().startswith("EXTRA_DOMAINS=$1"))
    ]
    check("[domain-refresh] AC2: script never reads its own argv",
          not top_level_argv, "\n".join(top_level_argv))

    # AC6: additive only. Any of these would make the script capable of
    # tearing down a working firewall, which is the whole thing it exists to
    # avoid (init-firewall.sh already does the destructive rebuild).
    for forbidden, why in [
        ("ipset flush", "would strip the live allowlist"),
        ("ipset destroy", "would delete the set out from under the session"),
        ("ipset del", "would remove addresses"),
        ("iptables", "policy is init-firewall.sh's job alone"),
        ("api.github.com", "must never re-fetch /meta"),
        ("GITHUB_TOKEN", "must never want the PAT"),
    ]:
        check(f"[domain-refresh] AC6: no `{forbidden}` ({why})",
              forbidden not in body, forbidden)
    check("[domain-refresh] AC6: the only mutation is `ipset -exist add`",
          "-exist add" in body, "additive add missing")


# ── AC3/AC4: init-firewall.sh writes the state file ─────────────────────────

def test_refresh_ac3_ac4_state_file_written() -> None:
    print("\n[domain-refresh] AC3/AC4: init-firewall.sh persists the list")
    src = INIT_FIREWALL.read_text()
    check("[domain-refresh] AC3: state path defined",
          "/run/vibe" in src and "extra-domains" in src, "")
    check("[domain-refresh] AC3: validated list written one host per line",
          'printf \'%s\\n\' "$EXTRA_DOMAINS" > "$EXTRA_DOMAINS_STATE"' in src, "")
    check("[domain-refresh] AC4: empty list removes a stale state file",
          'rm -f "$EXTRA_DOMAINS_STATE"' in src, "")

    # The write must sit AFTER the VIBE_FIREWALL_SOURCE_ONLY guard: sourcing
    # the script for a unit test must not create /run/vibe on the host.
    guard = src.index("VIBE_FIREWALL_SOURCE_ONLY:-}\" ]; then")
    write = src.index("EXTRA_DOMAINS_STATE=")
    check("[domain-refresh] AC3: write is below the source-only guard",
          write > guard, f"guard@{guard} write@{write}")
    # ...and BEFORE the resolve loop, so it always mirrors what was allowed.
    loop = src.index("for domain in \\")
    check("[domain-refresh] AC3: write is above the resolve loop",
          write < loop, f"write@{write} loop@{loop}")


# ── AC5: Dockerfile wiring ──────────────────────────────────────────────────

def test_refresh_ac5_dockerfile_and_sudoers() -> None:
    print("\n[domain-refresh] AC5: COPY + chmod + argv-less sudoers rule")
    df = DOCKERFILE.read_text()
    check("[domain-refresh] AC5: COPY into /usr/local/bin",
          "COPY refresh-extra-domains.sh /usr/local/bin/" in df, "")
    check("[domain-refresh] AC5: chmod +x in the build",
          "/usr/local/bin/refresh-extra-domains.sh" in df.split("RUN chmod +x")[1][:600], "")
    check("[domain-refresh] AC5: NOPASSWD sudoers entry",
          'node ALL=(root) NOPASSWD: /usr/local/bin/refresh-extra-domains.sh' in df, "")
    check("[domain-refresh] AC5: env_reset on that entry",
          'Defaults!/usr/local/bin/refresh-extra-domains.sh env_reset' in df, "")
    # The rule must FORBID arguments, and in sudoers that is spelt as a
    # trailing `""`. A command listed with no argument list at all permits ANY
    # arguments — the opposite of what this grant wants, and the exact mistake
    # the first cut of this test enshrined (caught in security review). Without
    # it, `node` could hand hostnames to a root script whose purpose is
    # widening the firewall.
    rules = [ln for ln in df.splitlines()
             if "NOPASSWD: /usr/local/bin/refresh-extra-domains.sh" in ln]
    check("[domain-refresh] AC5: exactly one sudoers rule for the script",
          len(rules) == 1, str(rules))
    for ln in rules:
        rule = ln.split("'")[1] if "'" in ln else ln
        check("[domain-refresh] AC5: sudoers rule forbids arguments (trailing \"\")",
              rule.rstrip().endswith('refresh-extra-domains.sh ""'), rule)
        check("[domain-refresh] AC5: no wildcard in the sudoers rule",
              "*" not in rule, rule)
    # The sudoers file must still be a single 0440 file with the old entries
    # intact — this change adds, never replaces.
    check("[domain-refresh] AC5: init-firewall.sh rule untouched",
          'node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh' in df, "")
    check("[domain-refresh] AC5: sudoers file still 0440",
          "chmod 0440 /etc/sudoers.d/node-firewall" in df, "")


# ── AC7/AC8/AC13: the resolve-and-add loop ──────────────────────────────────

def test_refresh_ac7_ac8_resolve_and_add() -> None:
    print("\n[domain-refresh] AC7/AC8: adds resolved addresses, drops junk")
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(
            Path(tmp), ["good.example.com", "not a hostname", "other.example.com"])
        check("[domain-refresh] AC7: exits 0", r.returncode == 0, r.stderr[:300])
        joined = " | ".join(added)
        check("[domain-refresh] AC7: both A records for good.example.com added",
              "add allowed-domains 2.21.15.114" in joined
              and "add allowed-domains 2.21.15.130" in joined, joined)
        check("[domain-refresh] AC7: the second valid domain is added too",
              "add allowed-domains 23.45.67.89" in joined, joined)
        check("[domain-refresh] AC8: invalid entry warned about",
              "not a plain DNS hostname" in r.stderr, r.stderr[:300])
        check("[domain-refresh] AC8: invalid entry never reached dig/ipset",
              "not a hostname" not in joined, joined)
        check("[domain-refresh] AC7: every add is `-exist` (idempotent)",
              all(a.startswith("-exist add") for a in added), joined)


def test_refresh_ac7_rejects_malformed_dns_answer() -> None:
    print("\n[domain-refresh] AC7: a non-IPv4 DNS answer is not allowlisted")
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(Path(tmp), ["bogusip.example.com"])
        check("[domain-refresh] AC7: 999.1.1.1 never reaches the ipset",
              "999.1.1.1" not in " ".join(added), " | ".join(added))
        check("[domain-refresh] AC7: and it says so",
              "invalid IP" in r.stderr, r.stderr[:300])


def test_refresh_ac13_cap() -> None:
    print("\n[domain-refresh] AC13: entries capped at EXTRA_DOMAINS_MAX")
    with tempfile.TemporaryDirectory() as tmp:
        many = [f"cap{i}.example.com" for i in range(EXTRA_DOMAINS_MAX + 5)]
        r, added = _refresh_run(Path(tmp), many)
        check("[domain-refresh] AC13: cap warning emitted",
              "capped at" in r.stderr, r.stderr[:300])
        check("[domain-refresh] AC13: no more than the cap were resolved",
              len(added) <= EXTRA_DOMAINS_MAX, f"{len(added)} adds")


# ── AC9/AC10/AC11/AC12: exit-code contract ──────────────────────────────────

def test_refresh_ac9_no_state_file() -> None:
    print("\n[domain-refresh] AC9: nothing configured -> clean no-op")
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(Path(tmp), [])
        check("[domain-refresh] AC9: empty state file exits 0",
              r.returncode == 0, r.stderr[:300])
        check("[domain-refresh] AC9: no ipset mutation",
              added == [], " | ".join(added))
        check("[domain-refresh] AC9: says how to configure extras",
              ".vibe/domains" in r.stdout and "VIBE_EXTRA_DOMAINS" in r.stdout,
              r.stdout[:300])

        # An absent file behaves like an empty one, never like an error.
        binn = Path(tmp) / "bin"
        env = _isolate_extras_env(dict(os.environ))
        env["PATH"] = f"{binn}:{env.get('PATH', '')}"
        env["ADDS_LOG"] = str(Path(tmp) / "adds.log")
        env["VIBE_EXTRA_DOMAINS_STATE"] = str(Path(tmp) / "does-not-exist")
        r2 = run(["bash", str(REFRESH_SH)], env=env)
        check("[domain-refresh] AC9: absent state file exits 0 too",
              r2.returncode == 0, r2.stderr[:300])


def test_refresh_ac10_missing_ipset() -> None:
    print("\n[domain-refresh] AC10: no allowlist to add to -> refuse")
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(Path(tmp), ["good.example.com"], ipset_present=False)
        check("[domain-refresh] AC10: exits 1", r.returncode == 1, r.stderr[:300])
        check("[domain-refresh] AC10: names the missing set",
              "allowed-domains" in r.stderr and "not initialised" in r.stderr,
              r.stderr[:300])
        check("[domain-refresh] AC10: does NOT try to build a firewall",
              added == [], " | ".join(added))


def test_refresh_ac11_ac12_exit_contract() -> None:
    print("\n[domain-refresh] AC11/AC12: total failure vs partial success")
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(Path(tmp), ["dead.example.com"])
        check("[domain-refresh] AC11: every domain unresolvable -> exit 1",
              r.returncode == 1, f"rc={r.returncode} {r.stderr[:200]}")
        check("[domain-refresh] AC11: names what failed",
              "dead.example.com" in r.stderr, r.stderr[:300])
    with tempfile.TemporaryDirectory() as tmp:
        r, added = _refresh_run(Path(tmp), ["dead.example.com", "good.example.com"])
        check("[domain-refresh] AC12: partial resolution -> exit 0",
              r.returncode == 0, f"rc={r.returncode} {r.stderr[:200]}")
        check("[domain-refresh] AC12: the good domain was still added",
              "2.21.15.114" in " ".join(added), " | ".join(added))


# ── AC14/AC15: the CLAUDE.md fragment that makes it automatic ───────────────

def test_refresh_ac14_fragment_content() -> None:
    print("\n[domain-refresh] AC14: the fragment teaches the reactive fix")
    check("[domain-refresh] AC14: fragment exists", FRAGMENT_MD.is_file(), str(FRAGMENT_MD))
    if not FRAGMENT_MD.is_file():
        return
    body = FRAGMENT_MD.read_text()
    check("[domain-refresh] AC14: names the exact command",
          "sudo /usr/local/bin/refresh-extra-domains.sh" in body, "")
    check("[domain-refresh] AC14: describes the failure shape to react to",
          "000" in body and ("refused" in body or "timeout" in body), "")
    check("[domain-refresh] AC14: says retry once, then report the real error",
          "retry" in body.lower(), "")
    check("[domain-refresh] AC14: forbids a timer/loop (Martin's call)",
          "timer" in body.lower() and "loop" in body.lower(), "")
    check("[domain-refresh] AC14: warns off re-running init-firewall.sh",
          "init-firewall.sh" in body, "")


def test_refresh_ac15_fragment_gated_on_extra_domains() -> None:
    """The fragment is noise for a project with no extra domains: nothing can
    go stale, so it must not reach the shared CLAUDE.md. Mirrors the brain2.md
    and shared-repos.md mount gates."""
    print("\n[domain-refresh] AC15: fragment gated on VIBE_EXTRA_DOMAINS")
    marker = "<!-- vibe-md: extra-domains-refresh.md -->"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_base = os.environ.copy()
        env_base["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")
        env_base["HOME"] = str(tmp_path)
        env_base["GIT_CONFIG_GLOBAL"] = str(tmp_path / "gitconfig")
        env_base["VIBE_AUTO_GITIGNORE"] = "0"

        # Pass 1: no extra domains → fragment absent.
        dest_off = tmp_path / "off"; dest_off.mkdir()
        env_off = env_base.copy()
        env_off["CLAUDE_CONFIG_DIR"] = str(dest_off)
        env_off.pop("VIBE_EXTRA_DOMAINS", None)
        r_off = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                               env=_isolate_extras_env(env_off),
                               capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
        check("[domain-refresh] AC15: install exits 0 (no extras)",
              r_off.returncode == 0, r_off.stderr[:200])
        md_off = (dest_off / "CLAUDE.md").read_text()
        check("[domain-refresh] AC15: fragment ABSENT with no extra domains",
              marker not in md_off, "fragment leaked into a plain vibe")
        check("[domain-refresh] AC15: other fragments still present (sanity)",
              "<!-- vibe-md: web-research.md -->" in md_off, "loop didn't run")

        # Pass 2: extra domains configured → fragment present.
        dest_on = tmp_path / "on"; dest_on.mkdir()
        env_on = env_base.copy()
        env_on["CLAUDE_CONFIG_DIR"] = str(dest_on)
        env_on["VIBE_EXTRA_DOMAINS"] = "api.xero.com identity.xero.com"
        r_on = subprocess.run(["bash", str(INSTALL_EXTRAS)],
                              env=_isolate_extras_env(env_on),
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)
        check("[domain-refresh] AC15: install exits 0 (extras set)",
              r_on.returncode == 0, r_on.stderr[:200])
        md_on = (dest_on / "CLAUDE.md").read_text()
        check("[domain-refresh] AC15: fragment PRESENT with extra domains",
              marker in md_on, "fragment missing when it is needed")
        check("[domain-refresh] AC15: the command survives into CLAUDE.md",
              "sudo /usr/local/bin/refresh-extra-domains.sh" in md_on, "")


# ── AC16: documentation ─────────────────────────────────────────────────────

def test_refresh_ac16_docs() -> None:
    print("\n[domain-refresh] AC16: README / MANUAL-TESTS / CHANGELOG")
    readme = README_MD.read_text()
    check("[domain-refresh] AC16: README explains the staleness + the fix",
          "refresh-extra-domains.sh" in readme, "")
    check("[domain-refresh] AC16: MANUAL-TESTS has an end-to-end entry",
          "refresh-extra-domains" in MANUAL_TESTS_MD.read_text(), "")
    check("[domain-refresh] AC16: CHANGELOG entry",
          "refresh-extra-domains" in CHANGELOG_MD.read_text(), "")


# ── AC17: the state file is root-read input, so check where it came from ────

def test_refresh_ac17_state_file_provenance() -> None:
    print("\n[domain-refresh] AC17: a planted state file is refused")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Build a normal fixture first so the stubs exist and the happy path is
        # known-good, then subvert only the state file.
        r_ok, added_ok = _refresh_run(tmp_path, ["good.example.com"])
        check("[domain-refresh] AC17: baseline still works",
              r_ok.returncode == 0 and added_ok, r_ok.stderr[:200])

        # A symlink where the list belongs: the classic plant. Even pointing at
        # a file with valid content, the reader must refuse rather than follow.
        real = tmp_path / "planted"
        real.write_text("evil.example.com\n")
        state = tmp_path / "extra-domains"
        state.unlink()
        state.symlink_to(real)
        binn = tmp_path / "bin"
        adds = tmp_path / "adds.log"
        adds.write_text("")
        env = _isolate_extras_env(dict(os.environ))
        env["PATH"] = f"{binn}:{env.get('PATH', '')}"
        env["ADDS_LOG"] = str(adds)
        env["VIBE_EXTRA_DOMAINS_STATE"] = str(state)
        env["REFRESH_DNS_ATTEMPTS"] = "1"
        r = run(["bash", str(REFRESH_SH)], env=env)
        check("[domain-refresh] AC17: symlinked state file -> exit 1",
              r.returncode == 1, f"rc={r.returncode} {r.stderr[:200]}")
        check("[domain-refresh] AC17: says why",
              "refusing to read" in r.stderr, r.stderr[:300])
        check("[domain-refresh] AC17: the planted host never reached the ipset",
              "evil" not in adds.read_text(), adds.read_text())

        # A directory in the file's place is equally not a list.
        state.unlink()
        state.mkdir()
        r2 = run(["bash", str(REFRESH_SH)], env=env)
        check("[domain-refresh] AC17: non-regular state path -> exit 1",
              r2.returncode == 1, f"rc={r2.returncode} {r2.stderr[:200]}")


# ── AC18: no arithmetic evaluation of attacker-controlled strings ────────────

def test_refresh_ac18_numeric_env_validated() -> None:
    """`sleep "$(( BACKOFF * attempt ))"` evaluates BACKOFF's CONTENTS, so
    `x[$(cmd)]` would run cmd as root. env_reset keeps this off the sudo path,
    but the script must not depend on its caller for that."""
    print("\n[domain-refresh] AC18: non-numeric env knobs cannot inject")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        canary = tmp_path / "pwned"
        # dead.example.com forces the retry path, which is the only place the
        # backoff reaches an arithmetic context.
        payload = f"x[$(touch {canary})]"
        r, _ = _refresh_run(
            tmp_path, ["dead.example.com"],
            env_extra={"REFRESH_DNS_ATTEMPTS": "2", "REFRESH_DNS_BACKOFF": payload})
        check("[domain-refresh] AC18: the payload never executed",
              not canary.exists(), f"canary created by {payload}")
        check("[domain-refresh] AC18: the bad value is reported",
              "non-numeric" in r.stderr, r.stderr[:300])
        # And it still does its job with the default substituted in.
        check("[domain-refresh] AC18: script still ran to completion",
              "re-resolved" in r.stdout or r.returncode == 1, r.stdout[:200])
