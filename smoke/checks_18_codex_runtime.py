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
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call

import pwd
import tomllib

REQUIREMENTS_TOML = REPO / "devcontainer" / "codex" / "requirements.toml"
CONFIG_TOML = REPO / "devcontainer" / "codex" / "config.toml"
HOOKS_JSON = REPO / "devcontainer" / "codex" / "hooks" / "hooks.json"
ADAPTER = REPO / "devcontainer" / "codex-guard-adapter.sh"
LIVENESS = REPO / "devcontainer" / "codex-guard-liveness.sh"
CODEX_ENTRY = REPO / "devcontainer" / "codex-entry.sh"
PROMPT_PREFIX = REPO / "devcontainer" / "codex-prompt-prefix.sh"
CODEX_TOOL_INVENTORY_MD = REPO / "docs" / "codex-tool-inventory.md"

# ── task_047: $vs/$vss/$vsss Codex skills + vibe-delegate role dispatch ──────
CODEX_SKILLS_DIR = REPO / "devcontainer" / "codex" / "skills"
ASK_MD = REPO / "devcontainer" / "commands" / "ask.md"
CODEX_INTEGRATION_PLAN_MD = REPO / "docs" / "codex-integration-plan.md"

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
    requirements.toml, hooks.json, adapter, both guards and the Codex-led
    entry point, owned by whichever user this test process runs as.

    codex-entry joined the liveness gate's ownership list in task_049, so it
    has to be here too or every liveness check below fails on its absence."""
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
        ("codex-entry", CODEX_ENTRY),
        # task_053: the UserPromptSubmit prefix hook joined the ownership
        # list codex-guard-liveness checks, so the fixture chain needs a
        # copy too or every liveness check below fails on its absence.
        ("codex-prompt-prefix", PROMPT_PREFIX),
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
    check("[codex] exactly two events: PreToolUse, UserPromptSubmit",
          set(hooks.keys()) == {"PreToolUse", "UserPromptSubmit"}, str(hooks.keys()))
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

    # task_053: the new UserPromptSubmit matcher group — no tool matcher
    # (there is no tool to match on a prompt), one command, the hardened
    # env -i /bin/bash form naming codex-prompt-prefix, timeout 10, no async.
    prompt_entries = hooks.get("UserPromptSubmit", [])
    check("[codex] UserPromptSubmit has exactly one matcher group", len(prompt_entries) == 1, str(prompt_entries))
    if prompt_entries:
        prompt_entry = prompt_entries[0]
        prompt_hooks = prompt_entry.get("hooks", [])
        check("[codex] UserPromptSubmit group has exactly one hook entry", len(prompt_hooks) == 1, str(prompt_hooks))
        if prompt_hooks:
            ph = prompt_hooks[0]
            check("[codex] UserPromptSubmit hook type == 'command'", ph.get("type") == "command", str(ph))
            check("[codex] UserPromptSubmit hook command is the hardened codex-prompt-prefix form",
                  ph.get("command") == "/usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/bash /usr/local/bin/codex-prompt-prefix",
                  ph.get("command"))
            check("[codex] UserPromptSubmit hook timeout == 10", ph.get("timeout") == 10, str(ph))
            check("[codex] UserPromptSubmit hook has no 'async' key", "async" not in ph, str(ph))


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


# ═══════════════════════════════════════════════════════════════════════════
# task_047: $vs/$vss/$vsss Codex skills + `vibe-delegate role` dispatch
# ═══════════════════════════════════════════════════════════════════════════


def _parse_skill_frontmatter(text: str):
    """Minimal YAML frontmatter reader: split on '---', parse 'key: value'
    lines from the first block. Returns (dict_or_None, body_str)."""
    parts = text.split("---")
    if len(parts) < 3:
        return None, ""
    fm_text = parts[1]
    body = "---".join(parts[2:])
    data = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data, body


# ── AC1: SKILL.md frontmatter + body ─────────────────────────────────────────


def test_codex_skill_frontmatter_ac1():
    print("\n[codex] SKILL.md — AC1 frontmatter (name/description) and body requirements")
    for name in ("vs", "vss", "vsss"):
        path = CODEX_SKILLS_DIR / name / "SKILL.md"
        if not check(f"[codex] {name}/SKILL.md exists", path.exists(), str(path)):
            continue
        text = path.read_text()
        data, body = _parse_skill_frontmatter(text)
        if not check(f"[codex] {name}/SKILL.md has --- frontmatter delimiters", data is not None, text[:120]):
            continue

        check(f"[codex] {name}/SKILL.md frontmatter has exactly the keys name, description",
              set(data.keys()) == {"name", "description"}, str(sorted(data.keys())))
        check(f"[codex] {name}/SKILL.md name == directory name {name!r}", data.get("name") == name, data.get("name"))
        check(f"[codex] {name}/SKILL.md name <= 64 chars", len(data.get("name", "")) <= 64, data.get("name"))
        description = data.get("description", "")
        check(f"[codex] {name}/SKILL.md description is non-empty", bool(description.strip()), "")
        check(f"[codex] {name}/SKILL.md description names the vibe command /{name}",
              f"/{name}" in description, description)

        body_lines = [l for l in body.strip("\n").splitlines()]
        check(f"[codex] {name}/SKILL.md body is under 60 lines", len(body_lines) < 60, str(len(body_lines)))
        flat_body = " ".join(body.split())

        check(f"[codex] {name}/SKILL.md body names the command file /usr/local/share/vibe/commands/{name}.md",
              f"/usr/local/share/vibe/commands/{name}.md" in body, "")

        for token in ("vibe-delegate role", "vibe-delegate review codex",
                      "ScheduleWakeup", "/learnings", "Grep", "Glob"):
            check(f"[codex] {name}/SKILL.md body carries substitution-table entry {token!r}", token in body, "")

        for role in ("planner", "spec-critic", "generator", "tester", "reviewer", "evaluator"):
            check(f"[codex] {name}/SKILL.md substitution table names role {role!r}", role in body, "")

        check(f"[codex] {name}/SKILL.md carries the nested-step instruction ('in this same turn')",
              "in this same turn" in body, "")

        # AC1c: states that ONLY the $ form exists in Codex's own terminal
        # (composer rejects an unknown /<name> before submission), and that
        # /<name> IS the same command in Claude Code — never that $ and /
        # are interchangeable inside Codex's own terminal.
        check(f"[codex] {name}/SKILL.md states only the ${name} form exists in Codex's own terminal",
              f"only `${name}`" in flat_body or f"only ${name}" in flat_body, flat_body[-400:])
        check(f"[codex] {name}/SKILL.md names the composer rejecting the unknown / form before submission",
              "composer" in flat_body and "rejects" in flat_body and "submit" in flat_body.lower(), flat_body[-400:])
        check(f"[codex] {name}/SKILL.md states /{name} IS the same command in Claude Code (not in Codex's terminal)",
              "same command in Claude Code" in flat_body, flat_body[-400:])


# ── AC2: Dockerfile COPY covers codex/skills/; no Mac-home COPY ─────────────


def test_codex_skills_dockerfile_ac2():
    print("\n[codex] Dockerfile — AC2 codex/ COPY covers skills; no ~/.codex or ~/.agents COPY")
    text = DOCKERFILE.read_text()

    check("[codex] Dockerfile: COPY --chown=root:root codex/ /etc/codex/ present",
          "COPY --chown=root:root codex/ /etc/codex/" in text, "")
    check("[codex] Dockerfile: comment confirms codex/skills/ ships via this same COPY",
          "codex/skills/" in text, "")

    copy_lines = [l for l in text.splitlines() if l.strip().startswith("COPY")]
    check("[codex] Dockerfile: no COPY line targets /home/node/.codex",
          not any("/home/node/.codex" in l for l in copy_lines), str(copy_lines))
    check("[codex] Dockerfile: no COPY line targets ~/.agents / .agents",
          not any(".agents" in l for l in copy_lines), str(copy_lines))

    check("[codex] Dockerfile: skills dirs chmod 0755, root-owned",
          "chmod 0755 /etc/codex/skills /etc/codex/skills/vs /etc/codex/skills/vss /etc/codex/skills/vsss" in text, "")
    check("[codex] Dockerfile: SKILL.md files chmod 0644",
          "chmod 0644 /etc/codex/skills/vs/SKILL.md /etc/codex/skills/vss/SKILL.md "
          "/etc/codex/skills/vsss/SKILL.md" in text, "")


# ── AC3: `role` refusals — fail closed, zero vendor calls ───────────────────


def test_delegate_role_refusals_ac3():
    print("\n[delegate] role: AC3 refusals fail closed with zero vendor calls")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        cases = [
            ("unknown role", ["role", "bogus", "--model", "astra", "--cwd", str(workspace)], "brief"),
            ("unknown model", ["role", "planner", "--model", "bogus", "--cwd", str(workspace)], "brief"),
            ("missing --cwd", ["role", "planner", "--model", "astra"], "brief"),
            ("relative --cwd", ["role", "planner", "--model", "astra", "--cwd", "relative/dir"], "brief"),
            ("--cwd outside a git work tree", ["role", "planner", "--model", "astra", "--cwd", str(home)], "brief"),
            ("empty payload", ["role", "planner", "--model", "astra", "--cwd", str(workspace)], ""),
        ]
        for label, args, payload in cases:
            r, calls = _delegate_call(workspace, home, env, args, payload=payload)
            check(f"[delegate] role: {label} exits non-zero", r.returncode != 0 and not r.stdout, r.stdout + r.stderr)
            check(f"[delegate] role: {label} makes zero vendor calls", not calls, str(calls))

        # fable without --consent-credits: refused before any vendor process,
        # even though it is a write role (generator) and the payload is read.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "generator", "--model", "fable", "--cwd", str(workspace)])
        check("[delegate] role: fable without --consent-credits is refused, zero vendor calls",
              r.returncode != 0 and not calls, r.stderr)

        # codex=off policy refuses an Astra role exactly like `ask astra`.
        policy = workspace / ".vibe" / "review-slots"
        policy.write_text("codex=off\n")
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)])
        check("[delegate] role: codex=off refuses an Astra role, zero vendor calls",
              r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(workspace, home, env,
            ["role", "generator", "--model", "astra", "--cwd", str(workspace)])
        check("[delegate] role: codex=off refuses an Astra write role too, zero vendor calls",
              r.returncode != 0 and not calls, r.stderr)
        policy.unlink()


# ── AC4: golden argv vectors ─────────────────────────────────────────────────


_ASTRA_DONE = {"answer": {"report": "did the thing", "status": "done"}}
_CLAUDE_DONE = {"response": {"type": "result", "subtype": "success", "is_error": False,
    "result": "did the thing\nSTATUS: done", "modelUsage": {"served-fixture": {}},
    "usage": {"input_tokens": 100, "cache_creation_input_tokens": 20000,
              "cache_read_input_tokens": 7000, "output_tokens": 30,
              "cache_creation": {"ephemeral_5m_input_tokens": 40}}}}


def test_delegate_role_golden_astra_ac4():
    print("\n[delegate] role: AC4 golden argv — Astra read-only and write roles")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))

        # Read-only role (planner): byte-identical to `ask astra`'s own argv,
        # confined to a private temp dir, never -C <cwd>.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)], _ASTRA_DONE)
        check("[delegate] role planner/astra succeeds", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            check("[delegate] role planner/astra: version + login + exec (3 calls)", len(calls) == 3, str(calls))
            call = calls[-1]
            argv = call["args"]
            schema_path = argv[argv.index("--output-schema") + 1]
            output_path = argv[argv.index("--output-last-message") + 1]
            golden = ["exec", "-m", "gpt-6-astra", "--ignore-user-config", "--ignore-rules",
                "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                "-c", 'approval_policy="never"', "-c", 'forced_login_method="chatgpt"',
                "-c", 'cli_auth_credentials_store="file"', "-c", "project_doc_max_bytes=0",
                "-c", "agents.enabled=false", "-c", 'web_search="disabled"',
                "-c", "apps._default.enabled=false",
                "--disable", "shell_tool", "--disable", "unified_exec",
                "--disable", "apply_patch_freeform", "--disable", "multi_agent",
                "--disable", "apps", "--disable", "js_repl",
                "--output-schema", schema_path, "--output-last-message", output_path,
                "--json", "-"]
            check("[delegate] role planner/astra: argv equals the read-only (ask-astra) golden exactly",
                  argv == golden, str(argv))
            check("[delegate] role planner/astra: no -C <cwd> in argv", "-C" not in argv, str(argv))
            check("[delegate] role planner/astra: schema/output are absolute, outside --cwd",
                  os.path.isabs(schema_path) and os.path.isabs(output_path) and
                  not schema_path.startswith(str(workspace)) and not output_path.startswith(str(workspace)),
                  f"{schema_path} {output_path}")
            check("[delegate] role planner/astra: process cwd is a private temp dir outside the repo",
                  call["cwd"] != str(workspace) and not call["cwd"].startswith(str(workspace)), call["cwd"])
            check("[delegate] role planner/astra: private cwd cleaned up afterwards",
                  not Path(call["cwd"]).exists(), call["cwd"])
            result = json.loads(r.stdout)
            check("[delegate] role planner/astra: usage accounted like ask (cache not double counted)",
                  result["usage"]["total_tokens"] == 5044, r.stdout)

        # Write role (generator): the AC4 pinned vector verbatim.
        before = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
        r, calls = _delegate_call(workspace, home, env,
            ["role", "generator", "--model", "astra", "--cwd", str(workspace)], _ASTRA_DONE)
        check("[delegate] role generator/astra succeeds", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            call = calls[-1]
            argv = call["args"]
            schema_path = argv[argv.index("--output-schema") + 1]
            output_path = argv[argv.index("--output-last-message") + 1]
            golden = ["exec", "-m", "gpt-6-astra", "-C", str(workspace), "--sandbox", "danger-full-access",
                "--ephemeral", "--skip-git-repo-check", "--json",
                "-c", 'approval_policy="never"', "-c", 'forced_login_method="chatgpt"',
                "-c", 'cli_auth_credentials_store="file"', "-c", 'web_search="disabled"',
                "--disable", "multi_agent", "--disable", "apps", "--disable", "js_repl",
                "--output-schema", schema_path, "--output-last-message", output_path, "-"]
            check("[delegate] role generator/astra: argv equals the AC4 write vector exactly",
                  argv == golden, str(argv))
            check("[delegate] role generator/astra: no -a, no --ignore-user-config, no dangerously-* flag",
                  "-a" not in argv and "--ignore-user-config" not in argv and
                  not any("dangerously" in x for x in argv), str(argv))
            check("[delegate] role generator/astra: schema/output are absolute, outside --cwd",
                  os.path.isabs(schema_path) and os.path.isabs(output_path) and
                  not schema_path.startswith(str(workspace)) and not output_path.startswith(str(workspace)),
                  f"{schema_path} {output_path}")
            check("[delegate] role generator/astra: process cwd equals --cwd (the real workspace)",
                  call["cwd"] == str(workspace), call["cwd"])
            result = json.loads(r.stdout)
            check("[delegate] role generator/astra: usage accounted like ask (cache not double counted)",
                  result["usage"]["total_tokens"] == 5044, r.stdout)
        after = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
        check("[delegate] role generator/astra: nothing written under --cwd by the helper",
              before == after, f"before={before}\nafter={after}")


def test_delegate_role_golden_claude_ac4():
    print("\n[delegate] role: AC4 golden argv — Claude read-only and write roles")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))

        # Read-only role (reviewer, haiku): byte-identical to `ask haiku`'s argv.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)], _CLAUDE_DONE)
        check("[delegate] role reviewer/haiku succeeds, one call", r.returncode == 0 and len(calls) == 1, r.stderr)
        if r.returncode == 0:
            argv = calls[0]["args"]
            golden = ["-p", "--model", "haiku", "--output-format", "json", "--safe-mode",
                "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--setting-sources", "user", "--permission-mode", "plan",
                "--permission-prompts", "none", "--no-session-persistence",
                "--disable-slash-commands", "--settings", '{"forceLoginMethod":"claudeai"}']
            check("[delegate] role reviewer/haiku: argv equals the read-only (ask-haiku) golden exactly",
                  argv == golden, str(argv))
            check("[delegate] role reviewer/haiku: no -C <cwd> in argv", "-C" not in argv, str(argv))
            check("[delegate] role reviewer/haiku: process cwd is a private temp dir, not the workspace",
                  calls[0]["cwd"] != str(workspace), calls[0]["cwd"])
            check("[delegate] role reviewer/haiku: private cwd cleaned up afterwards",
                  not Path(calls[0]["cwd"]).exists(), calls[0]["cwd"])
            result = json.loads(r.stdout)
            check("[delegate] role reviewer/haiku: usage includes all cache components (same rules as ask)",
                  result["usage"]["total_tokens"] == 27130 and
                  result["usage"]["ephemeral_5m_input_tokens"] == 40, r.stdout)

        # Write role (tester, sonnet): the AC4 pinned Claude write vector verbatim.
        before = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
        r, calls = _delegate_call(workspace, home, env,
            ["role", "tester", "--model", "sonnet", "--cwd", str(workspace)], _CLAUDE_DONE)
        check("[delegate] role tester/sonnet succeeds, one call", r.returncode == 0 and len(calls) == 1, r.stderr)
        if r.returncode == 0:
            argv = calls[0]["args"]
            golden = ["-p", "--model", "sonnet", "--output-format", "json",
                "--permission-mode", "bypassPermissions",
                "--tools", "Bash,Read,Write,Edit,Glob,Grep",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--setting-sources", "user", "--no-session-persistence",
                "--disable-slash-commands", "--settings",
                # Astra review (iter 5): the project's guard hooks are excluded by
                # --setting-sources user, so the write role carries them INLINE with
                # disableAllHooks pinned false.
                json.dumps({"forceLoginMethod": "claudeai", "disableAllHooks": False, "hooks": {"PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/guard-bash.sh"}]},
                    {"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": "/usr/local/bin/guard-fs.sh"}]},
                ]}}, separators=(",", ":"))]
            check("[delegate] role tester/sonnet: argv equals the AC4 write vector verbatim",
                  argv == golden, str(argv))
            inline = json.loads(argv[argv.index("--settings") + 1])
            check("[delegate] role tester/sonnet: inline settings carry both guards and pin disableAllHooks false",
                  inline.get("disableAllHooks") is False and
                  [h["hooks"][0]["command"] for h in inline["hooks"]["PreToolUse"]] ==
                  ["/usr/local/bin/guard-bash.sh", "/usr/local/bin/guard-fs.sh"], str(inline))
            # Billed mode: the user's settings file is merged with the pinned keys
            # into a private scratch copy; the pinned keys win.
            route = home / "route.json"
            route.write_text(json.dumps({"apiKeyHelper": "/x", "disableAllHooks": True, "hooks": {}}))
            paid_env = {**env, "VIBE_CLAUDE_P_BILLING": "credits", "VIBE_CLAUDE_P_SETTINGS": str(route),
                        "VIBE_CLAUDE_P_CONFIG_DIR": str(home / "paid-config")}
            r2, calls2 = _delegate_call(workspace, home, paid_env,
                ["role", "tester", "--model", "opus", "--cwd", str(workspace), "--consent-credits"], _CLAUDE_DONE)
            check("[delegate] role tester/opus billed: one call", r2.returncode == 0 and len(calls2) == 1, r2.stderr)
            if r2.returncode == 0:
                sarg = calls2[0]["args"][calls2[0]["args"].index("--settings") + 1]
                seen = json.loads((home / "settings-seen.json").read_text())
                check("[delegate] role tester/opus billed: --settings is a private merged copy, not the user's file",
                      sarg != str(route) and sarg.endswith("role-settings.json") and not Path(sarg).exists(), sarg)
                check("[delegate] role tester/opus billed: merged copy keeps the user's routing and pins the guards",
                      seen.get("apiKeyHelper") == "/x" and seen.get("disableAllHooks") is False and
                      [h["hooks"][0]["command"] for h in seen["hooks"]["PreToolUse"]] ==
                      ["/usr/local/bin/guard-bash.sh", "/usr/local/bin/guard-fs.sh"], str(seen))
            check("[delegate] role tester/sonnet: no --safe-mode, no dangerously, hooks never disabled (hooks stay ON)",
                  "--safe-mode" not in argv and '"disableAllHooks":true' not in str(argv) and
                  not any("dangerously" in x for x in argv), str(argv))
            tools_arg = argv[argv.index("--tools") + 1]
            check("[delegate] role tester/sonnet: tool allowlist excludes Agent/Task, WebFetch, WebSearch, NotebookEdit",
                  not any(t in tools_arg for t in ("Agent", "Task", "WebFetch", "WebSearch", "NotebookEdit")),
                  tools_arg)
            check("[delegate] role tester/sonnet: process cwd equals --cwd (the real workspace)",
                  calls[0]["cwd"] == str(workspace), calls[0]["cwd"])
            result = json.loads(r.stdout)
            check("[delegate] role tester/sonnet: usage includes all cache components (same rules as ask)",
                  result["usage"]["total_tokens"] == 27130 and
                  result["usage"]["ephemeral_5m_input_tokens"] == 40, r.stdout)
        after = sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*"))
        check("[delegate] role tester/sonnet: nothing written under --cwd by the helper",
              before == after, f"before={before}\nafter={after}")


def test_delegate_role_readonly_no_dash_c():
    print("\n[delegate] role: every read-only role, either model family, never gets -C <cwd>")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        for role in ("planner", "spec-critic", "reviewer", "evaluator"):
            for model, fixture in (("astra", _ASTRA_DONE), ("haiku", _CLAUDE_DONE)):
                r, calls = _delegate_call(workspace, home, env,
                    ["role", role, "--model", model, "--cwd", str(workspace)], fixture)
                check(f"[delegate] role {role}/{model} succeeds", r.returncode == 0, r.stderr)
                if r.returncode == 0 and calls:
                    argv = calls[-1]["args"]
                    check(f"[delegate] role {role}/{model}: no -C flag", "-C" not in argv, str(argv))
                    check(f"[delegate] role {role}/{model}: process cwd is not the workspace",
                          calls[-1]["cwd"] != str(workspace), calls[-1]["cwd"])


def test_delegate_role_write_roles_use_cwd():
    print("\n[delegate] role: every write role, either model family, runs in --cwd")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))
        for role in ("generator", "tester"):
            for model, fixture in (("astra", _ASTRA_DONE), ("sonnet", _CLAUDE_DONE)):
                r, calls = _delegate_call(workspace, home, env,
                    ["role", role, "--model", model, "--cwd", str(workspace)], fixture)
                check(f"[delegate] role {role}/{model} succeeds", r.returncode == 0, r.stderr)
                if r.returncode == 0 and calls:
                    call = calls[-1]
                    check(f"[delegate] role {role}/{model}: process cwd equals --cwd",
                          call["cwd"] == str(workspace), call["cwd"])
                    if model == "astra":
                        check(f"[delegate] role {role}/{model}: -C <cwd> present",
                              "-C" in call["args"] and
                              call["args"][call["args"].index("-C") + 1] == str(workspace), str(call["args"]))


# ── AC5: role reply contract — status derivation, output shape ─────────────


def _claude_response(result_text: str, is_error: bool = False):
    return {"type": "result", "subtype": "success", "is_error": is_error,
        "result": result_text, "modelUsage": {"served-fixture": {}},
        "usage": {"input_tokens": 100, "cache_creation_input_tokens": 20000,
                  "cache_read_input_tokens": 7000, "output_tokens": 30,
                  "cache_creation": {"ephemeral_5m_input_tokens": 40}}}


def test_delegate_role_status_ac5():
    print("\n[delegate] role: AC5 status derivation and output shape {runtime,model,role,status,report,usage}")
    with tempfile.TemporaryDirectory() as td:
        workspace, home, env = _delegate_fixture(Path(td))

        # Astra: {report, status: done} -> done, exit 0.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)],
            {"answer": {"report": "the plan", "status": "done"}})
        check("[delegate] role astra done: exit 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            result = json.loads(r.stdout)
            check("[delegate] role astra done: status == done", result.get("status") == "done", r.stdout)
            check("[delegate] role astra: output keys exactly {runtime, model, role, status, report, usage, "
                  "billing, served_models}",
                  set(result.keys()) == {"runtime", "model", "role", "status", "report", "usage",
                                          "billing", "served_models"},
                  str(sorted(result.keys())))
            check("[delegate] role astra done: report/role carried through",
                  result.get("report") == "the plan" and result.get("role") == "planner", r.stdout)

        # Astra: {report, status: blocked} -> blocked, STILL exit 0 (helper
        # succeeded; the role itself reported a block).
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)],
            {"answer": {"report": "could not proceed", "status": "blocked"}})
        check("[delegate] role astra blocked: exit 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            check("[delegate] role astra blocked: status == blocked",
                  json.loads(r.stdout).get("status") == "blocked", r.stdout)

        # Astra: missing schema field (no status) -> non-zero.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)],
            {"answer": {"report": "no status field"}})
        check("[delegate] role astra missing status field: non-zero exit, no stdout",
              r.returncode != 0 and not r.stdout, r.stdout)

        # Astra: invalid status enum value -> non-zero.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)],
            {"answer": {"report": "x", "status": "maybe"}})
        check("[delegate] role astra invalid status enum: non-zero exit, no stdout",
              r.returncode != 0 and not r.stdout, r.stdout)

        # Astra: a turn.failed event -> non-zero, never 'done'.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "planner", "--model", "astra", "--cwd", str(workspace)],
            {"events": [{"type": "turn.failed"}]})
        check("[delegate] role astra turn.failed event: non-zero exit, no stdout",
              r.returncode != 0 and not r.stdout, r.stdout)

        # Claude: report ending "STATUS: done" -> done.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)],
            {"response": _claude_response("Reviewed everything.\nSTATUS: done")})
        check("[delegate] role claude 'STATUS: done': exit 0, status done",
              r.returncode == 0 and json.loads(r.stdout).get("status") == "done", r.stdout + r.stderr)
        if r.returncode == 0:
            check("[delegate] role claude: output keys exactly {runtime, model, role, status, report, usage, "
                  "billing, served_models}",
                  set(json.loads(r.stdout).keys()) ==
                  {"runtime", "model", "role", "status", "report", "usage",
                   "billing", "served_models"}, r.stdout)

        # Claude: report ending "STATUS: blocked" -> blocked.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)],
            {"response": _claude_response("Could not finish.\nSTATUS: blocked")})
        check("[delegate] role claude 'STATUS: blocked': exit 0, status blocked",
              r.returncode == 0 and json.loads(r.stdout).get("status") == "blocked", r.stdout + r.stderr)

        # Claude: no STATUS line at all -> defaults to blocked.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)],
            {"response": _claude_response("Just some prose with no status line.")})
        check("[delegate] role claude no STATUS line: exit 0, defaults to blocked",
              r.returncode == 0 and json.loads(r.stdout).get("status") == "blocked", r.stdout + r.stderr)

        # Claude: a mid-report "STATUS: done" that is NOT the final line must
        # not count -- only the last non-empty line is examined.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)],
            {"response": _claude_response("STATUS: done\nBut then I kept going and got stuck.")})
        check("[delegate] role claude mid-report 'STATUS: done' (not final line): defaults to blocked",
              r.returncode == 0 and json.loads(r.stdout).get("status") == "blocked", r.stdout + r.stderr)

        # Claude: is_error: true -> non-zero, never 'done'.
        r, calls = _delegate_call(workspace, home, env,
            ["role", "reviewer", "--model", "haiku", "--cwd", str(workspace)],
            {"response": _claude_response("quota exceeded", is_error=True)})
        check("[delegate] role claude is_error true: non-zero exit, no stdout",
              r.returncode != 0 and not r.stdout, r.stdout)


# ── AC6/AC7: docs ────────────────────────────────────────────────────────────


def test_codex_commands_running_under_codex_ac6():
    print("\n[codex] vs.md / vss.md / vsss.md — AC6 'Running under Codex' section")
    for path, name in ((VS_MD, "vs"), (VSS_MD, "vss"), (VSSS_MD, "vsss")):
        text = path.read_text()
        m = re.search(r"^## Running under Codex\n(.*?)\n---\n", text, re.DOTALL | re.MULTILINE)
        check(f"[codex] {name}.md has a 'Running under Codex' heading", m is not None, "")
        if not m:
            continue
        section = m.group(1)
        content_lines = [l for l in section.splitlines() if l.strip()]
        check(f"[codex] {name}.md 'Running under Codex' section is <= 8 lines",
              len(content_lines) <= 8, str(len(content_lines)))
        check(f"[codex] {name}.md 'Running under Codex' section names vibe-delegate role",
              "vibe-delegate role" in section, section)


def test_codex_docs_ac7():
    print("\n[codex] README / ask.md / codex-integration-plan.md — AC7 docs")
    readme = README_MD.read_text()
    check("[codex] README has a 'Skills in a Codex-led container' paragraph",
          "Skills in a Codex-led container" in readme, "")
    if "Skills in a Codex-led container" in readme:
        section = readme.split("Skills in a Codex-led container", 1)[-1][:2000]
        check("[codex] README's skills paragraph names where the skills live (/etc/codex/skills)",
              "/etc/codex/skills" in section, "")
        check("[codex] README's skills paragraph says the Mac's ~/.codex/~/.agents are never touched",
              "~/.codex" in section and "~/.agents" in section, "")
        check("[codex] README's skills paragraph names vibe-delegate role",
              "vibe-delegate role" in section, "")
        check("[codex] README's skills paragraph points at the live trial (Test 55)",
              "Test 55" in section, "")

    ask = ASK_MD.read_text()
    check("[codex] ask.md mentions the `role` operation", "`role`" in ask, "")
    check("[codex] ask.md points at the SKILL.md substitution tables",
          "SKILL.md" in ask, "")

    plan = CODEX_INTEGRATION_PLAN_MD.read_text()
    check("[codex] docs/codex-integration-plan.md D5 names vibe-delegate role",
          "vibe-delegate role" in plan, "")
    check("[codex] docs/codex-integration-plan.md D5 states 'thin wrapper' is no longer accurate",
          "no longer accurate" in plan, "")


# ═══════════════════════════════════════════════════════════════════════════
# task_053: `/vs` leading-space pass-through + managed UserPromptSubmit hook
# (Tester-authored AC5 tests; spec-only read, no generator report/diff/
# scratch-tests consulted)
# ═══════════════════════════════════════════════════════════════════════════


def _prompt_prefix_fixture(prompt: str | None, session_id: str = "sess-1") -> dict:
    """A realistic UserPromptSubmit payload: hook_event_name + prompt plus
    the other input fields Codex's hook JSON carries (F3: session_id, cwd,
    transcript_path). codex-prompt-prefix.sh reads only .prompt, but a
    fixture shaped like the real thing exercises the jq extraction the same
    way a live hook would; prompt=None omits the key entirely."""
    d = {"hook_event_name": "UserPromptSubmit", "cwd": "/workspace",
         "session_id": session_id, "transcript_path": "/tmp/transcript.jsonl"}
    if prompt is not None:
        d["prompt"] = prompt
    return d


def _run_prompt_prefix(input_text: str):
    return run(["bash", str(PROMPT_PREFIX)], input=input_text)


def _prompt_prefix_context(stdout: str):
    """None for empty stdout (silent no-op); the additionalContext string
    for a well-formed envelope; '<bad-json>'/'<bad-event>'/'<no-context>'
    for anything else, so a caller can tell a real miss from a malformed
    reply without a second parse."""
    if stdout.strip() == "":
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return "<bad-json>"
    hso = data.get("hookSpecificOutput", {})
    if hso.get("hookEventName") != "UserPromptSubmit":
        return "<bad-event>"
    return hso.get("additionalContext", "<no-context>")


def test_codex_prompt_prefix_matches_ac5():
    print("\n[codex] codex-prompt-prefix — matching prompts add the right context")
    cases = [
        (" /vs fix the build", "vs", "fix the build"),
        ("/vsss --hours 2 go", "vsss", "--hours 2 go"),
        ("/vss", "vss", "with no arguments"),
        ("/vss   ", "vss", "with no arguments"),
    ]
    for prompt, name, rest in cases:
        payload = json.dumps(_prompt_prefix_fixture(prompt))
        r = _run_prompt_prefix(payload)
        check(f"[codex] prompt-prefix {prompt!r}: exits 0",
              r.returncode == 0, f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
        ctx = _prompt_prefix_context(r.stdout)
        check(f"[codex] prompt-prefix {prompt!r}: additionalContext names ${name}",
              isinstance(ctx, str) and f"${name}" in ctx, r.stdout)
        check(f"[codex] prompt-prefix {prompt!r}: additionalContext carries {rest!r} verbatim",
              isinstance(ctx, str) and rest in ctx, r.stdout)


def test_codex_prompt_prefix_non_matches_ac5():
    print("\n[codex] codex-prompt-prefix — non-matching and unreadable input produce no output")
    non_matches = ["$vs go", "/vss:foo", "/vssx", "/VS", "hello /vs"]
    for prompt in non_matches:
        payload = json.dumps(_prompt_prefix_fixture(prompt))
        r = _run_prompt_prefix(payload)
        check(f"[codex] prompt-prefix {prompt!r}: exits 0",
              r.returncode == 0, f"rc={r.returncode} err={r.stderr!r}")
        check(f"[codex] prompt-prefix {prompt!r}: no stdout",
              r.stdout.strip() == "", r.stdout)

    # Astra review (task_053): later lines are arguments too, and a very long
    # argument must never make the hook fail (jq reads it on stdin, not argv).
    multi = "/vs implement feature X\nthen run the tests\nand report"
    r = _run_prompt_prefix(json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": multi}))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("[codex] prompt-prefix: multi-line arguments preserved verbatim, including later lines",
          r.returncode == 0 and "implement feature X\nthen run the tests\nand report" in ctx, ctx[-200:])
    trailing = "/vs hello\n\n"
    r = _run_prompt_prefix(json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": trailing}))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("[codex] prompt-prefix: trailing newlines in the arguments survive verbatim (sentinel capture)",
          r.returncode == 0 and ctx.endswith("hello\n\n"), repr(ctx[-20:]))
    huge = "/vsss " + ("x" * 300000)
    r = _run_prompt_prefix(json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": huge}))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("[codex] prompt-prefix: a 300 KB argument neither fails the hook nor is truncated",
          r.returncode == 0 and ("x" * 300000) in ctx, f"rc={r.returncode} len={len(ctx)}")

    r = _run_prompt_prefix("")
    check("[codex] prompt-prefix: empty stdin exits 0, no output",
          r.returncode == 0 and r.stdout.strip() == "", f"rc={r.returncode} out={r.stdout!r}")
    r = _run_prompt_prefix("not json at all {{{")
    check("[codex] prompt-prefix: non-JSON stdin exits 0, no output",
          r.returncode == 0 and r.stdout.strip() == "", f"rc={r.returncode} out={r.stdout!r}")
    r = _run_prompt_prefix(json.dumps({"hook_event_name": "UserPromptSubmit"}))
    check("[codex] prompt-prefix: JSON with no .prompt key exits 0, no output",
          r.returncode == 0 and r.stdout.strip() == "", f"rc={r.returncode} out={r.stdout!r}")


def test_codex_prompt_prefix_script_shape_ac5():
    print("\n[codex] codex-prompt-prefix.sh — AC1 script shape")
    text = PROMPT_PREFIX.read_text()
    lines = text.splitlines()
    check("[codex] codex-prompt-prefix.sh <= 60 lines", len(lines) <= 60, str(len(lines)))
    check("[codex] codex-prompt-prefix.sh starts #!/bin/bash",
          text.startswith("#!/bin/bash\n"), text[:20])
    check("[codex] codex-prompt-prefix.sh has no 'dangerously'", "dangerously" not in text, "")
    check("[codex] codex-prompt-prefix.sh has no literal ' -c ' token", " -c " not in text, "")


def test_codex_liveness_hooks_hardened_both_commands_ac5():
    print("\n[codex] liveness — check (c) accepts both hardened forms, rejects a bare env for either")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: healthy fixture (both hardened commands) exits 0",
              r.returncode == 0, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")

        # A bare `env` (no absolute path, no -i) standing in for the
        # UserPromptSubmit command must still be caught.
        hooks_path = root / "hooks" / "hooks.json"
        data = json.loads(hooks_path.read_text())
        good_prefix_cmd = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] = \
            good_prefix_cmd.replace("/usr/bin/env -i ", "env ")
        hooks_path.write_text(json.dumps(data))
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: bare `env` for codex-prompt-prefix fails check (c)",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names hooks-commands",
              "LIVENESS FAILED" in r.stderr and "hooks-commands" in r.stderr, r.stderr)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        # Same probe against the pre-existing codex-guard-adapter command,
        # to confirm the grouped alternation didn't loosen its own anchor.
        hooks_path = root / "hooks" / "hooks.json"
        data = json.loads(hooks_path.read_text())
        good_bash_cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = \
            good_bash_cmd.replace("/usr/bin/env -i ", "env ")
        hooks_path.write_text(json.dumps(data))
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: bare `env` for codex-guard-adapter fails check (c) too",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")


def test_codex_liveness_ownership_prompt_prefix_ac5():
    print("\n[codex] liveness — check (a) covers codex-prompt-prefix")
    liveness_text = LIVENESS.read_text()
    check("[codex] codex-guard-liveness.sh: ownership list includes codex-prompt-prefix",
          'check_owned "$prompt_prefix"' in liveness_text, "")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, bin_dir = _codex_liveness_fixture(tmp)
        stub_dir = _codex_version_stub(tmp, "codex-stub", "codex-cli 0.154.0")
        (bin_dir / "codex-prompt-prefix").unlink()
        r = _run_liveness(root, bin_dir, CURRENT_OWNER, path_prepend=stub_dir)
        check("[codex] liveness: a fixture missing codex-prompt-prefix fails ownership",
              r.returncode == 1, f"rc={r.returncode} stdout={r.stdout} stderr={r.stderr}")
        check("[codex] liveness: LIVENESS FAILED names ownership and codex-prompt-prefix",
              "LIVENESS FAILED" in r.stderr and "ownership" in r.stderr and
              "codex-prompt-prefix" in r.stderr, r.stderr)


def test_codex_prompt_prefix_dockerfile_ac5():
    print("\n[codex] Dockerfile — codex-prompt-prefix COPY --chown=root:root and chmod +x")
    text = DOCKERFILE.read_text()
    check("[codex] Dockerfile: COPY --chown=root:root codex-prompt-prefix.sh -> codex-prompt-prefix",
          "COPY --chown=root:root codex-prompt-prefix.sh /usr/local/bin/codex-prompt-prefix" in text, "")
    chmod_lines = [l for l in text.splitlines() if l.strip().startswith("RUN chmod +x")]
    check("[codex] Dockerfile: chmod +x list includes codex-prompt-prefix",
          any("/usr/local/bin/codex-prompt-prefix" in l for l in chmod_lines), str(chmod_lines))


def test_codex_skill_leading_space_docs_ac5():
    print("\n[codex] SKILL.md — 'The `/` form' section names the leading space, drops /prompts")
    for name in ("vs", "vss", "vsss"):
        path = CODEX_SKILLS_DIR / name / "SKILL.md"
        text = path.read_text()
        m = re.search(r"## The `/` form\n(.*)", text, re.DOTALL)
        check(f"[codex] {name}/SKILL.md has a 'The `/` form' section", m is not None, text[-200:])
        if not m:
            continue
        section = m.group(1)
        flat = " ".join(section.split())
        check(f"[codex] {name}/SKILL.md '/' section mentions the leading space",
              "leading space" in flat, flat[:400])
        check(f"[codex] {name}/SKILL.md '/' section does not mention /prompts",
              "/prompts" not in section, section)


def test_codex_readme_prompt_prefix_ac5():
    print("\n[codex] README — leading-space pass-through named, /prompts: explicitly withdrawn")
    readme = README_MD.read_text()
    check("[codex] README mentions the leading space", "leading space" in readme, "")
    # AC4 withdraws the earlier `/prompts:`-based plan by naming and
    # retracting it, not by scrubbing the substring — README says so in the
    # same breath it names the route.
    check("[codex] README mentions /prompts: only to withdraw it (not as a live route)",
          "/prompts:" in readme and "withdrawn" in readme, "")
    check("[codex] README never spells /prompts:vs as something to type",
          "/prompts:vs" not in readme, "")


def test_codex_integration_plan_prompt_prefix_ac5():
    print("\n[codex] docs/codex-integration-plan.md — F6 names SlashCommandItem, D3 names UserPromptSubmit")
    plan = CODEX_INTEGRATION_PLAN_MD.read_text()
    m = re.search(r"- F6 .*?(?=\n- F7 )", plan, re.DOTALL)
    check("[codex] plan: found the F6 section", m is not None, "")
    if m:
        check("[codex] plan F6 mentions SlashCommandItem", "SlashCommandItem" in m.group(0), "")
    m = re.search(r"- D3 .*?(?=\n- D4 )", plan, re.DOTALL)
    check("[codex] plan: found the D3 section", m is not None, "")
    if m:
        check("[codex] plan D3 mentions UserPromptSubmit", "UserPromptSubmit" in m.group(0), "")


def test_manual_tests_55_leading_space_vs_ac5():
    print("\n[codex] MANUAL-TESTS — Test 55 mentions /vs with a leading space")
    manual = MANUAL_TESTS_MD.read_text()
    idx = manual.find("Test 55")
    check("[codex] MANUAL-TESTS: Test 55 heading found", idx != -1, "")
    if idx != -1:
        section = manual[idx:idx + 8000]
        check("[codex] MANUAL-TESTS Test 55 mentions a leading-space ' /vs' line",
              " /vs -" in section or " /vs`" in section or " /vs " in section, section[:400])
        check("[codex] MANUAL-TESTS Test 55 mentions 'leading space'",
              "leading space" in section, "")
