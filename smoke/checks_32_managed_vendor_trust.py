"""Independent smoke checks for the managed vendor prefix and trust boundary.

These checks are deliberately offline.  They reuse the established Codex
chain fixtures, but copy the liveness script into a temporary npm prefix so
its production-prefix find/ownership logic is exercised without touching
/usr/local/share.
"""
from smoke._core import *  # noqa: F401,F403
from smoke.checks_18_codex_runtime import (
    CURRENT_OWNER,
    CODEX_ENTRY,
    LIVENESS,
    _codex_liveness_fixture,
)
from smoke.checks_22_codex_agent import (
    _entry_fixture,
    _entry_liveness_stub,
)

import pwd


def _docker_lines() -> list[str]:
    return DOCKERFILE.read_text().splitlines()


def test_docker_install_hardens_vendor_and_shared_tree_before_final_user():
    print("\n[managed-vendor] Docker installation ownership and ordering")
    lines = _docker_lines()
    npm = [i for i, line in enumerate(lines) if "npm install -g" in line]
    harden = [i for i, line in enumerate(lines)
              if "chown -R root:root /usr/local/share/npm-global /usr/local/share/vibe" in line]
    user_node = [i for i, line in enumerate(lines) if line.strip() == "USER node"]
    check("[managed-vendor] both vendor npm installs are present", len(npm) == 2, str(npm))
    check("[managed-vendor] one final hardening RUN is present", len(harden) == 1, str(harden))
    check("[managed-vendor] final USER node exists", bool(user_node), str(user_node))
    if npm and harden and user_node:
        check("[managed-vendor] hardening follows npm install and precedes final USER node",
              max(npm) < harden[0] < user_node[-1],
              f"npm={npm}, harden={harden[0]}, USER node={user_node[-1]}")

    hardening = lines[harden[0]] if harden else ""
    if harden:
        hardening = "\n".join(lines[harden[0]:min(len(lines), harden[0] + 4)])
    check("[managed-vendor] npm-global and shared vibe tree are root-owned",
          "chown -R root:root /usr/local/share/npm-global /usr/local/share/vibe" in hardening,
          hardening)
    check("[managed-vendor] managed trees are not group/other writable",
          "chmod -R go-w /usr/local/share/npm-global /usr/local/share/vibe" in hardening,
          hardening)
    check("[managed-vendor] shared /usr/local/share ancestor is root-owned and protected",
          "chown root:root /usr/local/share" in hardening and
          "chmod go-w /usr/local/share" in hardening, hardening)

    early = "\n".join(lines[:npm[0]]) if npm else ""
    early_chowns = [line.strip() for line in early.splitlines() if "chown" in line]
    check("[managed-vendor] early chown is confined to npm-global",
          bool(early_chowns) and early_chowns[0] == "chown -R node:node /usr/local/share/npm-global",
          "\n".join(early_chowns))


def _managed_liveness_fixture(tmp: Path):
    root, bindir = _codex_liveness_fixture(tmp)
    prefix = tmp / "npm-global"
    (prefix / "bin").mkdir(parents=True)
    dependency = prefix / "node_modules" / "fixture-vendor" / "index.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("module.exports = 'protected fixture';\n")
    dependency.chmod(0o644)

    # Preserve the gate's fixed-prefix and find/ownership predicates while
    # relocating only their production absolute paths into this disposable
    # fixture.  The gate's canonical hook paths remain contractual strings.
    gate = tmp / "codex-guard-liveness"
    source = LIVENESS.read_text()
    source = source.replace("/usr/local/share/npm-global", str(prefix))
    source = source.replace("check_owned /usr/local root", f"check_owned {prefix.parent} {CURRENT_OWNER}")
    source = source.replace("check_owned /usr/local/share root", f"check_owned {prefix.parent} {CURRENT_OWNER}")
    gate.write_text(source)
    gate.chmod(0o755)

    log = tmp / "vendor-env.json"
    codex = prefix / "bin" / "codex"
    codex.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps({{k: os.environ.get(k) for k in ('NODE_OPTIONS', 'NODE_PATH')}}) + chr(10))\n"
        "print('codex-cli 0.154.0')\n"
    )
    codex.chmod(0o755)
    return root, bindir, prefix, dependency, gate, codex, log


def _run_managed_liveness(gate, root, bindir, owner, codex, env=None):
    args = ["bash", str(gate), "--root", str(root), "--bin", str(bindir)]
    if owner is not None:
        args += ["--owner", owner]
    args += ["--codex", str(codex)]
    return run(args, env=env)


def test_liveness_managed_prefix_protected_fixture_and_mutability_refusals():
    print("\n[managed-vendor] liveness checks the complete disposable npm prefix")
    check("[managed-vendor] liveness default owner is root", "owner=root" in LIVENESS.read_text(), "")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, prefix, dependency, gate, codex, log = _managed_liveness_fixture(tmp)
        env = {**os.environ, "NODE_OPTIONS": "--require=caller-controlled", "NODE_PATH": str(tmp / "attacker")}

        if os.geteuid() == 0:
            default = _run_managed_liveness(gate, root, bindir, None, codex, env)
            check("[managed-vendor] omitted liveness owner defaults to root",
                  default.returncode == 0, default.stdout + default.stderr)
            log.unlink()
        good = _run_managed_liveness(gate, root, bindir, CURRENT_OWNER, codex, env)
        check("[managed-vendor] protected CLI and imported dependency pass liveness",
              good.returncode == 0, good.stdout + good.stderr)
        calls = log.read_text().splitlines() if log.exists() else []
        check("[managed-vendor] liveness invokes the trusted CLI exactly once after checks",
              len(calls) == 1, str(calls))
        if calls:
            observed = json.loads(calls[-1])
            check("[managed-vendor] liveness does not forward NODE_OPTIONS/NODE_PATH",
                  observed.get("NODE_OPTIONS") is None and observed.get("NODE_PATH") is None,
                  repr({k: observed.get(k) for k in ("NODE_OPTIONS", "NODE_PATH")}))

        dependency.chmod(0o664)
        if log.exists():
            log.unlink()
        mutable = _run_managed_liveness(gate, root, bindir, CURRENT_OWNER, codex, env)
        check("[managed-vendor] writable imported dependency is rejected before CLI invocation",
              mutable.returncode != 0 and "mutable managed CLI dependency" in mutable.stderr,
              mutable.stdout + mutable.stderr)
        check("[managed-vendor] mutable dependency refusal invokes no CLI",
              not log.exists(), log.read_text() if log.exists() else "")

        dependency.chmod(0o644)
        codex.chmod(0o774)
        mutable_cli = _run_managed_liveness(gate, root, bindir, CURRENT_OWNER, codex, env)
        check("[managed-vendor] writable CLI is rejected before it can attest its version",
              mutable_cli.returncode != 0 and not log.exists(), mutable_cli.stdout + mutable_cli.stderr)
        codex.chmod(0o755)
        if os.geteuid() == 0:
            nobody = pwd.getpwnam("nobody").pw_name
            owner_change = run(["chown", nobody, str(dependency)])
            check("[managed-vendor] fixture can create a non-owner dependency case",
                  owner_change.returncode == 0, owner_change.stderr)
            if owner_change.returncode == 0:
                nonowner = _run_managed_liveness(gate, root, bindir, CURRENT_OWNER, codex, env)
                check("[managed-vendor] non-owner imported dependency is rejected",
                      nonowner.returncode != 0 and "mutable managed CLI dependency" in nonowner.stderr,
                      nonowner.stdout + nonowner.stderr)
        else:
            check("[managed-vendor] liveness source rejects non-owner files",
                  "! -user \"$owner\"" in LIVENESS.read_text(),
                  LIVENESS.read_text())


def test_entry_clears_caller_node_environment_before_cli():
    print("\n[managed-vendor] entry clears caller-controlled Node environment")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bindir, login, codex, argv_log = _entry_fixture(tmp)
        entry = bindir / "codex-entry"
        entry.write_text(CODEX_ENTRY.read_text())
        entry.chmod(0o755)
        env_log = tmp / "entry-env.json"
        codex.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            f"open({str(env_log)!r}, 'w').write(json.dumps({{k: os.environ.get(k) for k in ('NODE_OPTIONS', 'NODE_PATH')}}))\n"
            f"open({str(argv_log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
        )
        codex.chmod(0o755)
        _entry_liveness_stub(bindir, ok=True, log=tmp / "entry-liveness.log")
        env = {**os.environ, "NODE_OPTIONS": "--require=caller-controlled", "NODE_PATH": str(tmp / "attacker")}
        # Run through the same entry seam with polluted caller values.
        result = run(["bash", str(bindir / "codex-entry"), "--root", str(root), "--bin", str(bindir),
                      "--login-dir", str(login), "--codex", str(codex), "--", "--fixture"], env=env)
        check("[managed-vendor] entry starts the trusted CLI", result.returncode == 0, result.stdout + result.stderr)
        observed = json.loads(env_log.read_text()) if env_log.exists() else {}
        check("[managed-vendor] entry does not forward NODE_OPTIONS/NODE_PATH",
              observed.get("NODE_OPTIONS") is None and observed.get("NODE_PATH") is None,
              repr({k: observed.get(k) for k in ("NODE_OPTIONS", "NODE_PATH")}))
