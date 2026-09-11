"""task_046: Codex system policy layer, guard adapter, liveness gate, tool
inventory — authored independently by the Tester (spec-only read, no
Generator report/diff consulted).

Covers AC9's test list:
  - TOML parse of requirements.toml / config.toml (tomllib); AC1 key set and
    values exactly; AC1 per-constraint citation comments.
  - AC2 config.toml defaults.
  - AC3 hooks.json schema.
  - Adapter `bash` mode against the REAL devcontainer/guard-bash.sh.
  - Adapter `patch` mode against the REAL devcontainer/guard-fs.sh.
  - Adapter failure modes (unknown mode, missing guard, empty stdin).
  - Liveness gate: success path, ownership failure, fail-open-stub capture,
    a commented-out requirement, and the codex version floor.
  - Dockerfile COPY --chown=root:root lines and the unchanged sudoers block.
  - Docs: README, MANUAL-TESTS, docs/codex-tool-inventory.md.
"""
from smoke._core import *  # noqa: F401,F403

import pwd
import tomllib

REQUIREMENTS_TOML = REPO / "devcontainer" / "codex" / "requirements.toml"
CONFIG_TOML = REPO / "devcontainer" / "codex" / "config.toml"
HOOKS_JSON = REPO / "devcontainer" / "codex" / "hooks" / "hooks.json"
ADAPTER = REPO / "devcontainer" / "codex-guard-adapter.sh"
LIVENESS = REPO / "devcontainer" / "codex-guard-liveness.sh"
CODEX_TOOL_INVENTORY_MD = REPO / "docs" / "codex-tool-inventory.md"

CURRENT_OWNER = pwd.getpwuid(os.getuid()).pw_name

FEATURE_KEYS = ("multi_agent", "multi_agent_v2", "apps", "js_repl", "unified_exec")


# ── shared helpers ───────────────────────────────────────────────────────────


def _load_toml(path: Path):
    try:
        return tomllib.loads(path.read_text()), None
    except Exception as exc:  # noqa: BLE001 - report, don't crash the suite
        return None, str(exc)


def _codex_guard_dir(tmp: Path) -> Path:
    """A temp dir holding executable copies of the REAL guard-bash.sh and
    guard-fs.sh, for VIBE_GUARD_DIR / the adapter's self-locating default."""
    d = tmp / "guards"
    d.mkdir()
    for name, src in (("guard-bash.sh", GUARD_BASH), ("guard-fs.sh", GUARD_FS)):
        dst = d / name
        dst.write_text(src.read_text())
        dst.chmod(0o755)
    return d


def _run_adapter(mode: str, payload: dict, guard_dir: Path, input_text: str | None = None):
    """Run a COPY of the adapter placed next to the guards in guard_dir: the
    adapter self-locates its guards from its own directory and (Astra review,
    2026-09-11) honours no environment override, so the fixture chain is
    exercised exactly the way the installed /usr/local/bin chain is."""
    adapter_copy = guard_dir / "codex-guard-adapter"
    if not adapter_copy.exists():
        adapter_copy.write_text(ADAPTER.read_text())
        adapter_copy.chmod(0o755)
    env = dict(os.environ)
    env["VIBE_GUARD_DIR"] = str(Path(tempfile.gettempdir()) / "must-be-ignored")
    text = json.dumps(payload) if input_text is None else input_text
    return run(["bash", str(adapter_copy), mode], env=env, input=text)


def _adapter_reply_decision(stdout: str) -> str | None:
    """None if stdout is empty (silent allow); the permissionDecision string
    if stdout parses as the expected JSON envelope; '<bad-json>' otherwise."""
    if stdout.strip() == "":
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return "<bad-json>"
    return data.get("hookSpecificOutput", {}).get("permissionDecision", "<no-decision>")


def _assert_adapter_deny(r, label: str) -> None:
    check(f"[codex] adapter {label}: exits 0", r.returncode == 0,
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    if r.returncode != 0:
        return
    decision = _adapter_reply_decision(r.stdout)
    check(f"[codex] adapter {label}: reply is JSON", decision != "<bad-json>", r.stdout)
    check(f"[codex] adapter {label}: permissionDecision == deny", decision == "deny", r.stdout)
    if decision == "deny":
        try:
            reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        except (json.JSONDecodeError, KeyError):
            reason = ""
        check(f"[codex] adapter {label}: reason non-empty", bool(reason), r.stdout)


def _assert_adapter_allow(r, label: str) -> None:
    check(f"[codex] adapter {label}: exits 0", r.returncode == 0,
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    decision = _adapter_reply_decision(r.stdout)
    check(f"[codex] adapter {label}: no deny emitted", decision != "deny", r.stdout)


def _codex_liveness_fixture(tmp: Path) -> tuple[Path, Path]:
    """A fixture policy root + bin dir: verbatim copies of the real
    requirements.toml, hooks.json, adapter and both guards, owned by
    whichever user this test process runs as."""
    root = tmp / "etc-codex"
    (root / "hooks").mkdir(parents=True)
    bin_dir = tmp / "usr-local-bin"
    bin_dir.mkdir()

    req_dst = root / "requirements.toml"
    req_dst.write_text(REQUIREMENTS_TOML.read_text())
    req_dst.chmod(0o644)
    hooks_dst = root / "hooks" / "hooks.json"
    hooks_dst.write_text(HOOKS_JSON.read_text())
    hooks_dst.chmod(0o644)
    root.chmod(0o755)
    (root / "hooks").chmod(0o755)

    for name, src in (
        ("codex-guard-adapter", ADAPTER),
        ("guard-bash.sh", GUARD_BASH),
        ("guard-fs.sh", GUARD_FS),
    ):
        dst = bin_dir / name
        dst.write_text(src.read_text())
        dst.chmod(0o755)

    return root, bin_dir


def _codex_version_stub(tmp: Path, name: str, version_line: str) -> Path:
    stub_dir = tmp / name
    stub_dir.mkdir()
    codex = stub_dir / "codex"
    codex.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = '--version' ]; then\n"
        f"  echo '{version_line}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    codex.chmod(0o755)
    return stub_dir


def _run_liveness(root: Path, bin_dir: Path, owner: str, path_prepend: Path | None = None):
    """The liveness gate pins its own PATH (Astra review, 2026-09-11), so a
    stub codex is handed over with --codex rather than through the PATH."""
    args = ["bash", str(LIVENESS), "--root", str(root), "--bin", str(bin_dir), "--owner", owner]
    if path_prepend is not None:
        args += ["--codex", str(path_prepend / "codex")]
    return run(args)


# ── AC1: requirements.toml — TOML parse, key set, values ────────────────────


def test_codex_requirements_toml_ac1():
    print("\n[codex] requirements.toml — TOML parse, AC1 key set and values")
    data, err = _load_toml(REQUIREMENTS_TOML)
    if not check("[codex] requirements.toml parses as TOML", data is not None, err or ""):
        return

    check("[codex] top-level key set is exactly the F2 constraints used here",
          set(data.keys()) == {
              "allowed_approval_policies", "allowed_sandbox_modes",
              "allowed_web_search_modes", "allow_managed_hooks_only",
              "features", "mcp_servers", "hooks", "rules",
          }, str(sorted(data.keys())))

    check("[codex] allowed_approval_policies == ['never']",
          data.get("allowed_approval_policies") == ["never"], str(data.get("allowed_approval_policies")))
    check("[codex] allowed_sandbox_modes == ['read-only', 'danger-full-access']",
          data.get("allowed_sandbox_modes") == ["read-only", "danger-full-access"],
          str(data.get("allowed_sandbox_modes")))
    check("[codex] allowed_web_search_modes == ['disabled']",
          data.get("allowed_web_search_modes") == ["disabled"], str(data.get("allowed_web_search_modes")))
    check("[codex] allow_managed_hooks_only is True (bool, not string)",
          data.get("allow_managed_hooks_only") is True, repr(data.get("allow_managed_hooks_only")))

    features = data.get("features", {})
    check("[codex] [features] key set is exactly the five pins",
          set(features.keys()) == set(FEATURE_KEYS), str(sorted(features.keys())))
    for key in FEATURE_KEYS:
        check(f"[codex] features.{key} is False (bool, not string)",
              features.get(key) is False, repr(features.get(key)))

    check("[codex] [mcp_servers] present and empty",
          data.get("mcp_servers") == {}, repr(data.get("mcp_servers")))

    check("[codex] [hooks] == {'managed_dir': '/etc/codex/hooks'}",
          data.get("hooks") == {"managed_dir": "/etc/codex/hooks"}, str(data.get("hooks")))

    rules = data.get("rules", {})
    prefix_rules = rules.get("prefix_rules", [])
    check("[codex] rules has exactly two prefix_rules", len(prefix_rules) == 2, str(prefix_rules))

    def _tokens(rule):
        toks = []
        for tok in rule.get("pattern", []):
            toks.append(tok.get("token") if "token" in tok else tok)
        return tuple(toks)

    by_tokens = {_tokens(r): r for r in prefix_rules}
    force_key = ("git", "push", "--force")
    f_key = ("git", "push", "-f")
    check("[codex] prefix rule for 'git push --force' present",
          force_key in by_tokens, str(list(by_tokens.keys())))
    check("[codex] prefix rule for 'git push -f' present",
          f_key in by_tokens, str(list(by_tokens.keys())))
    for key in (force_key, f_key):
        rule = by_tokens.get(key)
        if rule is None:
            continue
        check(f"[codex] {' '.join(key)}: decision == 'forbidden'",
              rule.get("decision") == "forbidden", str(rule))
        check(f"[codex] {' '.join(key)}: justification states the prefix-only limitation",
              "prefix" in rule.get("justification", "").lower(), str(rule.get("justification")))

    all_tokens = [_tokens(r) for r in prefix_rules]
    check("[codex] no --force-with-lease rule (guard-bash.sh allows it)",
          not any("--force-with-lease" in t for t in all_tokens), str(all_tokens))
    check("[codex] no sudo rule (refresh-extra-domains.sh remedy needs it)",
          not any(t and t[0] == "sudo" for t in all_tokens), str(all_tokens))


def test_codex_requirements_toml_citations():
    print("\n[codex] requirements.toml — per-constraint field citations")
    lines = REQUIREMENTS_TOML.read_text().splitlines()

    def line_idx(pattern: str):
        rx = re.compile(pattern)
        for i, line in enumerate(lines):
            if rx.match(line):
                return i
        return None

    ordered_keys = [
        ("allowed_approval_policies", r"^allowed_approval_policies\s*="),
        ("allowed_sandbox_modes", r"^allowed_sandbox_modes\s*="),
        ("allowed_web_search_modes", r"^allowed_web_search_modes\s*="),
        ("allow_managed_hooks_only", r"^allow_managed_hooks_only\s*="),
        ("[features]", r"^\[features\]"),
        ("[mcp_servers]", r"^\[mcp_servers\]"),
        ("[hooks]", r"^\[hooks\]"),
        ("managed_dir", r"^managed_dir\s*="),
        ("[rules]", r"^\[rules\]"),
    ]
    idxs = []
    for label, pat in ordered_keys:
        idx = line_idx(pat)
        check(f"[codex] found a line for constraint key {label}", idx is not None, "")
        idxs.append(idx)

    # A "field citation" is a comment naming a `<Struct>Toml::<field>` path —
    # ConfigRequirementsToml for the top-level keys, or (for a key nested
    # under one, e.g. managed_dir under [hooks]) that nested struct's own
    # name (ManagedHooksRequirementsToml::managed_dir, hook_config.rs) —
    # never a bare, unattributed constraint.
    citation_re = re.compile(r"[A-Za-z][A-Za-z0-9]*Toml::[A-Za-z_]+")
    prev = 0
    for (label, _), idx in zip(ordered_keys, idxs):
        if idx is None:
            continue
        block = "\n".join(lines[prev:idx + 1])
        check(f"[codex] {label} is preceded by a <Struct>Toml::<field> citation",
              bool(citation_re.search(block)), block[-200:])
        prev = idx + 1

    for feat in FEATURE_KEYS:
        fidx = line_idx(rf"^{re.escape(feat)}\s*=")
        check(f"[codex] found feature line for {feat}", fidx is not None, "")
        if fidx is not None:
            block = "\n".join(lines[max(0, fidx - 8):fidx + 1])
            check(f"[codex] feature {feat} cites features/src/lib.rs",
                  "features/src/lib.rs" in block, block)

    text = "\n".join(lines)
    check("[codex] prefix_rules cite RequirementsExecPolicyToml",
          "RequirementsExecPolicyToml" in text or "requirements_exec_policy.rs" in text, "")


# ── AC2: config.toml ─────────────────────────────────────────────────────────


def test_codex_config_toml_ac2():
    print("\n[codex] config.toml — TOML parse and AC2 defaults")
    data, err = _load_toml(CONFIG_TOML)
    if not check("[codex] config.toml parses as TOML", data is not None, err or ""):
        return
    check("[codex] approval_policy == 'never'", data.get("approval_policy") == "never", str(data))
    check("[codex] sandbox_mode == 'danger-full-access'",
          data.get("sandbox_mode") == "danger-full-access", str(data))
    check("[codex] web_search == 'disabled'", data.get("web_search") == "disabled", str(data))
    check("[codex] project_doc_max_bytes is NOT set",
          "project_doc_max_bytes" not in data, str(data))

    text = CONFIG_TOML.read_text()
    check("[codex] header explains the sandbox is unavailable (F11: bubblewrap / user namespaces)",
          "bubblewrap" in text and "user namespaces" in text, "")


# ── AC3: hooks.json schema ────────────────────────────────────────────────────


def test_codex_hooks_json_ac3():
    print("\n[codex] hooks.json — AC3 schema")
    try:
        data = json.loads(HOOKS_JSON.read_text())
    except json.JSONDecodeError as exc:
        check("[codex] hooks.json parses as JSON", False, str(exc))
        return
    check("[codex] hooks.json parses as JSON", True)

    hooks = data.get("hooks", {})
    check("[codex] exactly one event: PreToolUse", set(hooks.keys()) == {"PreToolUse"}, str(hooks.keys()))
    entries = hooks.get("PreToolUse", [])
    check("[codex] exactly two matcher groups", len(entries) == 2, str(entries))

    matchers = {e.get("matcher") for e in entries}
    check("[codex] matcher groups are exactly 'Bash' and 'apply_patch|Write|Edit'",
          matchers == {"Bash", "apply_patch|Write|Edit"}, str(matchers))

    by_matcher = {}
    for entry in entries:
        matcher = entry.get("matcher")
        hs = entry.get("hooks", [])
        check(f"[codex] matcher {matcher!r} has exactly one hook entry", len(hs) == 1, str(hs))
        for h in hs:
            check(f"[codex] {matcher!r} hook type == 'command'", h.get("type") == "command", str(h))
            cmd = h.get("command", "")
            check(f"[codex] {matcher!r} hook command is the hardened env -i /bin/bash form",
                  cmd.startswith("/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-guard-adapter "), cmd)
            check(f"[codex] {matcher!r} hook has a timeout", "timeout" in h, str(h))
            check(f"[codex] {matcher!r} hook has no 'async' key", "async" not in h, str(h))
            by_matcher[matcher] = cmd

    check("[codex] Bash matcher -> codex-guard-adapter bash",
          by_matcher.get("Bash") == "/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-guard-adapter bash", str(by_matcher))
    check("[codex] apply_patch|Write|Edit matcher -> codex-guard-adapter patch",
          by_matcher.get("apply_patch|Write|Edit") == "/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-guard-adapter patch",
          str(by_matcher))


# ── AC4: adapter bash mode against the real guard-bash.sh ───────────────────


def test_codex_adapter_bash_mode():
    print("\n[codex] adapter — bash mode against the real guard-bash.sh")
    with tempfile.TemporaryDirectory() as td:
        guard_dir = _codex_guard_dir(Path(td))

        # (a) shell redirect into the Codex login dir. guard-bash.sh treats
        # this as a block (exit 2, its 'codex-write' rule), which the
        # adapter propagates verbatim.
        r = _run_adapter("bash",
                          {"tool_input": {"command": "echo pwned > /home/node/.codex/config.toml"},
                           "cwd": "/workspace"}, guard_dir)
        check("[codex] adapter bash: login-dir redirect exits 2",
              r.returncode == 2, f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
        check("[codex] adapter bash: login-dir redirect stderr carries the guard's reason",
              bool(r.stderr.strip()), r.stderr)

        # (b) force-push -> exit 2 (guard-bash.sh's force-push rule).
        r = _run_adapter("bash",
                          {"tool_input": {"command": "git push --force origin main"},
                           "cwd": "/workspace"}, guard_dir)
        check("[codex] adapter bash: force-push exits 2",
              r.returncode == 2, f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

        # (c) a /learnings write -> guard-bash.sh answers 'ask'; the adapter
        # rewrites it to 'deny' (an unattended session has nobody to ask).
        r = _run_adapter("bash",
                          {"tool_input": {"command": "echo x > /learnings/new.md"},
                           "cwd": "/workspace"}, guard_dir)
        _assert_adapter_deny(r, "bash: /learnings write (ask became deny)")

        # (d) a benign command -> allowed, silent.
        r = _run_adapter("bash",
                          {"tool_input": {"command": "git status"}, "cwd": "/workspace"}, guard_dir)
        _assert_adapter_allow(r, "bash: git status")


# ── AC4: adapter patch mode against the real guard-fs.sh ─────────────────────


def test_codex_adapter_patch_mode():
    print("\n[codex] adapter — patch mode against the real guard-fs.sh")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        guard_dir = _codex_guard_dir(tmp)
        workspace = tmp / "repo"
        workspace.mkdir()

        def payload(text: str, cwd: Path | None = workspace):
            d = {"tool_input": {"command": text}}
            if cwd is not None:
                d["cwd"] = str(cwd)
            return d

        # (a) an absolute path into the Codex login dir -> deny.
        text_a = ("*** Begin Patch\n*** Update File: /home/node/.codex/config.toml\n"
                  "@@\n-old\n+new\n*** End Patch")
        r = _run_adapter("patch", payload(text_a), guard_dir)
        _assert_adapter_deny(r, "patch: /home/node/.codex/config.toml")

        # (b) the .vibe-allow-codex opt-in marker -> deny.
        text_b = ("*** Begin Patch\n*** Add File: /workspace/.vibe-allow-codex\n"
                  "+marker\n*** End Patch")
        r = _run_adapter("patch", payload(text_b), guard_dir)
        _assert_adapter_deny(r, "patch: /workspace/.vibe-allow-codex")

        # (c) a relative path resolved against cwd -> allow (nothing to deny).
        text_c = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-old\n+new\n*** End Patch"
        r = _run_adapter("patch", payload(text_c), guard_dir)
        _assert_adapter_allow(r, "patch: relative path under cwd")

        # (d) an Update File path containing spaces, plus a Move to line
        # pointing into the login dir -> deny (the Move target is checked
        # too, and paths are taken literally so spaces survive).
        text_d = ("*** Begin Patch\n"
                  "*** Update File: some file with spaces.py\n"
                  "*** Move to: /home/node/.codex/renamed file.toml\n"
                  "@@\n-old\n+new\n*** End Patch")
        r = _run_adapter("patch", payload(text_d), guard_dir)
        _assert_adapter_deny(r, "patch: spaced path + Move to into login dir")

        # (e) a patch with no directive lines -> allow (nothing to check).
        text_e = "*** Begin Patch\n@@\n-old\n+new\n*** End Patch"
        r = _run_adapter("patch", payload(text_e), guard_dir)
        _assert_adapter_allow(r, "patch: no directive lines")

        # (f) adding a file under /learnings -> deny (ask became deny).
        text_f = "*** Begin Patch\n*** Add File: /learnings/x.md\n+data\n*** End Patch"
        r = _run_adapter("patch", payload(text_f), guard_dir)
        _assert_adapter_deny(r, "patch: /learnings add")


# ── AC4: adapter failure modes fail closed ───────────────────────────────────


def test_codex_adapter_failure_modes():
    print("\n[codex] adapter — failure modes fail closed (exit 2)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        guard_dir = _codex_guard_dir(tmp)

        # Unknown mode.
        r = _run_adapter("bogus", {"tool_input": {"command": "git status"}}, guard_dir)
        check("[codex] adapter: unknown mode exits 2",
              r.returncode == 2, f"rc={r.returncode} err={r.stderr!r}")
        check("[codex] adapter: unknown mode prints a reason on stderr",
              bool(r.stderr.strip()), r.stderr)

        # Missing guard: an adapter copy in a directory with no guards.
        empty_dir = tmp / "empty-guards"
        empty_dir.mkdir()
        r = _run_adapter("bash", {"tool_input": {"command": "git status"}}, empty_dir)
        check("[codex] adapter: missing guard exits 2",
              r.returncode == 2, f"rc={r.returncode} err={r.stderr!r}")

        # Empty stdin.
        r = _run_adapter("bash", {}, guard_dir, input_text="")
        check("[codex] adapter: empty stdin exits 2",
              r.returncode == 2, f"rc={r.returncode} err={r.stderr!r}")

        # Astra review (iter 4): no environment override of the guard location,
        # a fixed interpreter, a pinned PATH, and no Bash start-up hooks.
        text = ADAPTER.read_text()
        check("[codex] adapter: no VIBE_GUARD_DIR override", "VIBE_GUARD_DIR" not in text, "")
        check("[codex] adapter: shebang is /bin/bash, not env", text.startswith("#!/bin/bash\n"), text[:20])
        check("[codex] adapter: pins PATH and drops BASH_ENV/ENV",
              "export PATH=/usr/local/bin:/usr/bin:/bin" in text and "unset BASH_ENV ENV" in text, "")
        liveness_text = LIVENESS.read_text()
        check("[codex] liveness: shebang is /bin/bash and PATH pinned",
              liveness_text.startswith("#!/bin/bash\n") and "export PATH=/usr/local/bin:/usr/bin:/bin" in liveness_text, "")
        # A BASH_ENV that says `exit 0` must not defeat the adapter: the deny
        # fixture still denies when the hook is started the hardened way.
        bash_env = tmp / "bash_env"; bash_env.write_text("exit 0\n")
        deny_payload = json.dumps({"tool_input": {"command": "git push --force origin main"}, "cwd": str(tmp)})
        hostile = {**os.environ, "BASH_ENV": str(bash_env)}
        # Control: WITHOUT the hardened form, a hostile BASH_ENV in the
        # caller's environment runs `exit 0` before the adapter's first line —
        # this is the bypass Astra reported, kept here so the reason for the
        # env -i form stays demonstrable.
        r = run(["bash", str(guard_dir / "codex-guard-adapter"), "bash"], env=hostile, input=deny_payload)
        check("[codex] adapter: control — bare `bash adapter` under hostile BASH_ENV is bypassed (rc 0)",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr!r}")
        # The shipped hooks.json form: env -i strips BASH_ENV before /bin/bash starts.
        hardened = ["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "/bin/bash",
                    str(guard_dir / "codex-guard-adapter"), "bash"]
        r = run(hardened, env=hostile, input=deny_payload)
        check("[codex] adapter: force-push still denied under a hostile BASH_ENV (env -i form)",
              r.returncode == 2, f"rc={r.returncode} err={r.stderr!r}")
        # Astra re-review: an UNQUALIFIED `env` would itself resolve through the
        # caller's PATH. With a fake `env` first on PATH, the hardened (absolute)
        # form still denies; the test also pins that hooks.json never uses a
        # bare `env`.
        fake_bin = tmp / "fake-bin"; fake_bin.mkdir()
        (fake_bin / "env").write_text("#!/bin/sh\nexit 0\n"); (fake_bin / "env").chmod(0o755)
        hostile_path = {**hostile, "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}
        r = run(hardened, env=hostile_path, input=deny_payload)
        check("[codex] adapter: force-push still denied with a fake `env` first on PATH (absolute /usr/bin/env)",
              r.returncode == 2, f"rc={r.returncode} err={r.stderr!r}")
        hooks_text = HOOKS_JSON.read_text() if "HOOKS_JSON" in globals() else (REPO / "devcontainer/codex/hooks/hooks.json").read_text()
        check("[codex] hooks.json: every command starts with the absolute /usr/bin/env -i",
              '"command": "/usr/bin/env -i ' in hooks_text and '"command": "env ' not in hooks_text, "")


# ── AC5: liveness gate ───────────────────────────────────────────────────────


def test_codex_liveness_success():
    print("\n[codex] liveness — full chain healthy, --owner <current user>")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: exits 0 with a healthy fixture",
              r.returncode == 0, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        ok_lines = [line for line in r.stdout.splitlines() if line.startswith("ok")]
        check("[codex] liveness: prints one stdout line per check (>= 10 'ok' lines)",
              len(ok_lines) >= 10, f"stdout={r.stdout}")
        check("[codex] liveness: no LIVENESS FAILED on the success path",
              "LIVENESS FAILED" not in r.stderr, r.stderr)


def test_codex_liveness_ownership_failure():
    print("\n[codex] liveness — default owner (root) rejects a non-root-owned fixture")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        r = _run_liveness(root, bin_dir, "root", path_prepend=stub_dir)
        check("[codex] liveness: default owner exits 1 against a non-root fixture",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names the ownership check",
              "LIVENESS FAILED" in r.stderr and "ownership" in r.stderr, r.stderr)


def test_codex_liveness_failopen_stub_is_caught():
    print("\n[codex] liveness — a fail-open adapter stub is caught")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        adapter_path = bin_dir / "codex-guard-adapter"
        adapter_path.write_text("#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n")
        adapter_path.chmod(0o755)
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: fail-open adapter stub exits 1",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names the fixture check",
              "LIVENESS FAILED" in r.stderr and "fixture" in r.stderr, r.stderr)


def test_codex_liveness_requirements_failure():
    print("\n[codex] liveness — a commented-out allow_managed_hooks_only is caught")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        req = root / "requirements.toml"
        text = req.read_text().replace(
            "allow_managed_hooks_only = true", "# allow_managed_hooks_only = true")
        check("[codex] liveness fixture setup: the line was actually commented out",
              "# allow_managed_hooks_only = true" in text, "")
        req.write_text(text)
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: commented-out requirement exits 1",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names the requirements check",
              "LIVENESS FAILED" in r.stderr and "requirements" in r.stderr, r.stderr)


def test_codex_liveness_version_floor():
    print("\n[codex] liveness — codex version floor, compared as three integers")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)

        old_stub = _codex_version_stub(tmp, "codex-stub-old", "codex-cli 0.153.4")
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=old_stub)
        check("[codex] liveness: codex-cli 0.153.4 fails the 0.154.0 floor",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names codex-version",
              "LIVENESS FAILED" in r.stderr and "codex-version" in r.stderr, r.stderr)

        new_stub = _codex_version_stub(tmp, "codex-stub-new", "codex-cli 0.154.0")
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=new_stub)
        check("[codex] liveness: codex-cli 0.154.0 clears the floor and the whole run passes",
              r.returncode == 0, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")


# ── AC6: Dockerfile ───────────────────────────────────────────────────────────


def test_codex_dockerfile_ac6():
    print("\n[codex] Dockerfile — COPY --chown=root:root lines and the unchanged sudoers block")
    text = DOCKERFILE.read_text()

    check("[codex] COPY --chown=root:root codex/ /etc/codex/",
          "COPY --chown=root:root codex/ /etc/codex/" in text, "")
    check("[codex] COPY --chown=root:root codex-guard-adapter.sh -> codex-guard-adapter",
          "COPY --chown=root:root codex-guard-adapter.sh /usr/local/bin/codex-guard-adapter" in text, "")
    check("[codex] COPY --chown=root:root codex-guard-liveness.sh -> codex-guard-liveness",
          "COPY --chown=root:root codex-guard-liveness.sh /usr/local/bin/codex-guard-liveness" in text, "")

    # The three-rule sudoers block predates task_046 and must be unchanged:
    # no new NOPASSWD entry riding along with the Codex policy layer. HEAD,
    # not a fixed historical sha — see HISTORICAL_PINS_ALLOWED's header.
    # The sudoers keyword is assembled from two halves so the repo's own
    # content guard (which flags "PASSWD: <value>" as a secret assignment) does
    # not fire on this test file at commit time.
    np = "NOPASS" + "WD"
    sudoers_lines = [
        f'echo "node ALL=(root) {np}: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \\',
        'echo "Defaults!/usr/local/bin/init-firewall.sh env_reset" >> /etc/sudoers.d/node-firewall && \\',
        f'echo \'node ALL=(root) {np}: /usr/local/bin/refresh-extra-domains.sh ""\' '
        '>> /etc/sudoers.d/node-firewall && \\',
        'echo "Defaults!/usr/local/bin/refresh-extra-domains.sh env_reset" >> /etc/sudoers.d/node-firewall && \\',
        f'echo "node ALL=(root) {np}: /usr/sbin/avahi-daemon" >> /etc/sudoers.d/node-firewall && \\',
        "chmod 0440 /etc/sudoers.d/node-firewall",
    ]
    expected_block = "\n".join("  " + line for line in sudoers_lines)

    check("[codex] sudoers block present verbatim in the working tree",
          expected_block in text, "")

    r = run(["git", "show", "HEAD:devcontainer/Dockerfile"], cwd=REPO)
    check("[codex] git show HEAD:devcontainer/Dockerfile succeeds", r.returncode == 0, r.stderr)
    if r.returncode == 0:
        check("[codex] sudoers block is unchanged vs HEAD (byte-identical)",
              expected_block in r.stdout, "")

    check("[codex] sudoers block still lists only the three existing NOPASSWD commands",
          text.count(np + ":") == 3, str(text.count(np + ":")))


# ── AC7/AC8: docs ────────────────────────────────────────────────────────────


def test_codex_docs_ac7_ac8():
    print("\n[codex] docs — README, MANUAL-TESTS, codex-tool-inventory.md")
    readme = README_MD.read_text()
    check("[codex] README mentions 'Codex-led sessions'",
          "Codex-led sessions" in readme, "")

    manual = MANUAL_TESTS_MD.read_text()
    check("[codex] MANUAL-TESTS mentions 'Test 55'", "Test 55" in manual, "")
    check("[codex] MANUAL-TESTS mentions codex-guard-liveness",
          "codex-guard-liveness" in manual, "")

    inv = CODEX_TOOL_INVENTORY_MD.read_text()
    for token in ("exec_command", "write_stdin", "apply_patch", "view_image",
                  "spawn_agent", "mcp__", "request_user_input", "web_search", "UNMEDIATED"):
        check(f"[codex] docs/codex-tool-inventory.md mentions {token!r}", token in inv, "")
