"""task_034 Linux-host support: launcher helpers behind a `uname` PATH shim.

Moved out of checks_01 (task_048 close-out) to bring that part back under the
1,500-line cap; the test body is unchanged.
"""
from smoke._core import *
from smoke._core import _isolate_extras_env, _source_vibe_call


def test_task034_linux_host() -> None:
    """task_034 (Linux host support): every non-[L] acceptance criterion.
    AC1/AC2 (code-check.py / smoke-test.py themselves green) are asserted by
    the harness's own separate runs, not re-asserted here. AC12-14 are [L]
    (MANUAL-TESTS 44-50, need a real Linux box). Fixture builders live in
    smoke/_core.py (_task034_*) per the split-suite convention."""
    print("\n[task_034: Linux host support]")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ── uname PATH shim proof (iteration-2 amendment) ───────────────────
        darwin_shim = _make_uname_shim(tmp, "Darwin")
        linux_shim = _make_uname_shim(tmp / "linux_side", "Linux")
        r = run(["bash", "-c", "uname -s"],
                env={**os.environ, "PATH": f"{darwin_shim}{os.pathsep}{os.environ.get('PATH', '')}"})
        check("[task034] uname shim shadows real uname (Darwin fixture)",
              r.stdout.strip() == "Darwin", r.stdout)
        r = run(["bash", "-c", "uname -s"],
                env={**os.environ, "PATH": f"{linux_shim}{os.pathsep}{os.environ.get('PATH', '')}"})
        check("[task034] uname shim shadows real uname (Linux fixture)",
              r.stdout.strip() == "Linux", r.stdout)

        # ── AC3 + AC4: render_devcontainer_with_mounts under the Darwin shim ──
        devcontainer_json = REPO / "devcontainer" / "devcontainer.json"
        mount_args = ["/host/brain2", "/brain2", "0", "/host/zotero", "/zotero", "1"]

        def _render(env_extra: dict, tag: str) -> dict:
            dst = tmp / f"out-{tag}.json"
            call = (f"render_devcontainer_with_mounts {shlex.quote(str(devcontainer_json))} "
                    f"{shlex.quote(str(dst))} " + " ".join(shlex.quote(a) for a in mount_args))
            env = {"PATH": f"{darwin_shim}{os.pathsep}{os.environ.get('PATH', '')}", **env_extra}
            r = _source_vibe_call(env, call)
            check(f"[task034] render ({tag}) exits 0", r.returncode == 0, r.stderr)
            return json.loads(dst.read_text()) if dst.exists() else {}

        cfg_off = _render({}, "op-off")
        run_args_off = cfg_off.get("runArgs", [])
        check("[task034 AC3] exactly one host.docker.internal add-host (/op off)",
              run_args_off.count("--add-host=host.docker.internal:host-gateway") == 1,
              str(run_args_off))

        cfg_on = _render({"VIBE_OP_ADDHOST": "op.example.ts.net"}, "op-on")
        run_args_on = cfg_on.get("runArgs", [])
        check("[task034 AC3] exactly one host.docker.internal add-host (/op on)",
              run_args_on.count("--add-host=host.docker.internal:host-gateway") == 1,
              str(run_args_on))
        check("[task034 AC3] /op's own add-host still present when configured",
              "--add-host=op.example.ts.net:host-gateway" in run_args_on, str(run_args_on))

        check("[task034 AC4] golden carries no host.docker.internal (contamination check)",
              "host.docker.internal" not in TASK034_GOLDEN_DEVCONTAINER_RENDER_OP_OFF,
              "golden constant is contaminated")
        golden_cfg = json.loads(TASK034_GOLDEN_DEVCONTAINER_RENDER_OP_OFF)
        expected_cfg = dict(golden_cfg)
        expected_cfg["runArgs"] = golden_cfg["runArgs"] + ["--add-host=host.docker.internal:host-gateway"]
        check("[task034 AC4] current Darwin render == golden + exactly one add-host line",
              cfg_off == expected_cfg,
              f"current runArgs={run_args_off}\nexpected runArgs={expected_cfg['runArgs']}")

        # ── AC5: Darwin exit-hook block byte-identical to baseline ──────────
        base_vibe, base_vibe_rc = _task034_baseline_text("vibe")
        check("[task034] git show 3b23b19:vibe exits 0", base_vibe_rc == 0, base_vibe[:200])
        cur_vibe = VIBE.read_text()
        start_anchor = 'if [[ "$(uname)" == "Darwin" ]] && command -v pbcopy >/dev/null 2>&1; then'
        end_anchor = 'kill "$WATCHER_PID" 2>/dev/null || true\''

        def _extract(src: str) -> str:
            i = src.find(start_anchor)
            if i == -1:
                return ""
            j = src.find(end_anchor, i)
            return src[i:j + len(end_anchor)] if j != -1 else ""

        base_block, cur_block = _extract(base_vibe), _extract(cur_vibe)
        check("[task034 AC5] Darwin exit-hook block found in both baseline and current",
              bool(base_block) and bool(cur_block), "")
        check("[task034 AC5] Darwin exit-hook block byte-identical to baseline",
              base_block == cur_block, "blocks differ")

        # ── AC6: vibe_clipboard_cmd precedence ───────────────────────────────
        mac_pbcopy = _task034_tool_dir(tmp, "mac_pbcopy", ["pbcopy"])
        mac_nopbcopy = _task034_tool_dir(tmp, "mac_nopbcopy", [])
        check("[task034 AC6] Darwin + pbcopy present -> 'pbcopy'",
              _task034_clipboard_cmd(darwin_shim, [mac_pbcopy]) == "pbcopy", "")
        check("[task034 AC6] Darwin + no pbcopy -> empty",
              _task034_clipboard_cmd(darwin_shim, [mac_nopbcopy]) == "", "")

        all_three = _task034_tool_dir(tmp, "linux_all3", ["wl-copy", "xclip", "xsel"])
        check("[task034 AC6] Linux wl-copy beats xclip/xsel -> 'wl-copy'",
              _task034_clipboard_cmd(linux_shim, [all_three]) == "wl-copy", "")
        xclip_xsel = _task034_tool_dir(tmp, "linux_xclip_xsel", ["xclip", "xsel"])
        check("[task034 AC6] Linux xclip (no wl-copy) beats xsel -> flagged clipboard invocation",
              _task034_clipboard_cmd(linux_shim, [xclip_xsel]) == "xclip -selection clipboard", "")
        xsel_only = _task034_tool_dir(tmp, "linux_xsel_only", ["xsel"])
        check("[task034 AC6] Linux xsel only -> flagged clipboard invocation",
              _task034_clipboard_cmd(linux_shim, [xsel_only]) == "xsel --clipboard --input", "")
        no_tools = _task034_tool_dir(tmp, "linux_none", [])
        check("[task034 AC6] Linux with no clipboard tool -> empty",
              _task034_clipboard_cmd(linux_shim, [no_tools]) == "", "")

        # ── AC7: watcher's 3-way gate (Darwin OR VIBE_COPY_CMD OR FORCE) ────
        env_quiet = {**os.environ, "PATH": f"{linux_shim}{os.pathsep}{os.environ.get('PATH', '')}"}
        env_quiet.pop("VIBE_COPY_WATCHER_FORCE", None)
        env_quiet.pop("VIBE_COPY_CMD", None)
        r = run(["bash", str(VIBE_COPY_WATCHER), str(tmp / "watcher-ws-quiet")], env=env_quiet)
        check("[task034 AC7] Linux, no FORCE, no VIBE_COPY_CMD -> exits 0 immediately",
              r.returncode == 0, f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
        # Mechanics-required: FORCE alone keeps it running (mirrors
        # test_vibe_path_prefix_isolation's reliance on FORCE alone).
        check("[task034 AC7] watcher (FORCE only) does not exit immediately",
              _task034_watcher_alive_after({"VIBE_COPY_WATCHER_FORCE": "1"},
                                            tmp / "watcher-ws-force", linux_shim), "")
        check("[task034 AC7] watcher (VIBE_COPY_CMD set, the Linux path) does not exit immediately",
              _task034_watcher_alive_after({"VIBE_COPY_CMD": "true"},
                                            tmp / "watcher-ws-copycmd", linux_shim), "")

        # ── AC8: install.sh Darwin output byte-identical to pre-change ─────
        base_install, base_install_rc = _task034_baseline_text("install.sh")
        check("[task034] git show 3b23b19:install.sh exits 0", base_install_rc == 0, base_install[:200])
        out_base = _task034_run_install(base_install, tmp / "install-base-home", darwin_shim)
        out_cur = _task034_run_install(INSTALL.read_text(), tmp / "install-cur-home", darwin_shim)
        check("[task034 AC8] install.sh Darwin output byte-identical to pre-change",
              out_base == out_cur, f"--- baseline ---\n{out_base}\n--- current ---\n{out_cur}")

        # ── AC9: Linux preflight — apt/dnf hints, docker group, devcontainer ─
        install_src = INSTALL.read_text()
        for literal in ("preflight_linux", "vibe_linux_pkg", "docker info",
                         "id -nG", "usermod -aG docker", "docker-ce", "devcontainer missing"):
            check(f"[task034 AC9] install.sh mentions {literal!r}", literal in install_src, "")

        r = _task034_run_install_linux("apt", in_group=False, home=tmp / "install-linux-nogroup")
        out = r.stdout + r.stderr
        check("[task034 AC9] docker-group warning fires when not in group",
              "is not in the 'docker' group" in out, out)
        check("[task034 AC9] docker-group warning names the remedy",
              "usermod -aG docker" in out, out)
        check("[task034 AC9] docker-group warning is non-fatal (exit 0)",
              r.returncode == 0, f"rc={r.returncode}\n{out}")

        r2 = _task034_run_install_linux("dnf", in_group=True, home=tmp / "install-linux-group")
        out2 = r2.stdout + r2.stderr
        check("[task034 AC9] no docker-group warning when already in group",
              "is not in the 'docker' group" not in out2, out2)
        check("[task034 AC9] dnf hints present for Fedora/RHEL", "sudo dnf install" in out2, out2)

        # set -e safety amendment: empty PATH must not abort the script.
        empty_home = tmp / "install-empty-path-home"
        empty_home.mkdir()
        empty_bin = tmp / "empty-path-bin"
        empty_bin.mkdir()
        r3 = run(["/bin/bash", str(INSTALL)], env={"HOME": str(empty_home), "PATH": str(empty_bin)})
        out3 = r3.stdout + r3.stderr
        check("[task034] empty-PATH run reaches the preflight failure message (no early abort)",
              "Install the missing dependencies" in out3, out3)
        check("[task034] empty-PATH run falls back to Darwin hints, not a crash",
              "xcode-select" in out3 or "brew install" in out3, out3)

        # ── AC10: Dockerfile nsswitch sed is idempotent ─────────────────────
        dockerfile_src = DOCKERFILE.read_text()
        m = re.search(r"sed -i '([^']+)' /etc/nsswitch\.conf", dockerfile_src)
        check("[task034 AC10] Dockerfile nsswitch sed expression found", m is not None, dockerfile_src[:2000])
        if m:
            sed_expr = m.group(1)
            nss = tmp / "nsswitch.conf"
            nss.write_text("hosts:          files dns\n")
            r = run(["sed", "-i", sed_expr, str(nss)])
            check("[task034 AC10] first sed application exits 0", r.returncode == 0, r.stderr)
            check("[task034 AC10] one mdns4_minimal entry after first apply",
                  nss.read_text().count("mdns4_minimal") == 1, nss.read_text())
            r = run(["sed", "-i", sed_expr, str(nss)])
            check("[task034 AC10] second sed application exits 0", r.returncode == 0, r.stderr)
            check("[task034 AC10] still exactly one mdns4_minimal entry after second apply (idempotent)",
                  nss.read_text().count("mdns4_minimal") == 1, nss.read_text())

        # ── mDNS probe: warns once with the spec's literal, then stays silent ─
        mdns_bin = _task034_tool_dir(tmp, "mdns_bin", [])
        (mdns_bin / "getent").write_text("#!/bin/sh\nexit 1\n")
        (mdns_bin / "getent").chmod(0o755)
        (mdns_bin / "hostname").write_text("#!/bin/sh\necho testhost\n")
        (mdns_bin / "hostname").chmod(0o755)
        marker = tmp / "mdns-marker"
        env_probe = {
            "VIBE_MDNS_MARKER": str(marker),
            "PATH": f"{linux_shim}{os.pathsep}{mdns_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        r = _source_vibe_call(env_probe, "vibe_mdns_probe")
        check("[task034] mDNS probe function exists and runs cleanly", r.returncode == 0, r.stderr)
        check("[task034] mDNS probe warns with the spec's literal on failure",
              "mDNS: this host cannot resolve" in r.stdout, r.stdout)
        check("[task034] mDNS probe names the host.docker.internal fallback",
              "host.docker.internal" in r.stdout, r.stdout)
        check("[task034] mDNS probe drops a marker after warning", marker.exists(), "")
        r2m = _source_vibe_call(env_probe, "vibe_mdns_probe")
        check("[task034] mDNS probe is silent on the second (marker-gated) call",
              "mDNS" not in r2m.stdout, r2m.stdout)

        # ── Docs: README / ONBOARDING / MANUAL-TESTS ────────────────────────
        readme = (REPO / "README.md").read_text()
        check("[task034] README has a Linux hosts section", "## Linux hosts" in readme, "")
        check("[task034] README names the reference platform",
              "Ubuntu 24.04 LTS with Docker Engine" in readme, "")
        check("[task034] README documents the host.docker.internal add-host",
              "--add-host=host.docker.internal:host-gateway" in readme, "")
        check("[task034] README marks the build bridge macOS-only", "macOS-only" in readme, "")

        onboarding = (REPO / "ONBOARDING.md").read_text()
        check("[task034] ONBOARDING forks steps by platform",
              "Mac only" in onboarding and "Linux only" in onboarding, "")
        check("[task034] ONBOARDING names Ubuntu 24.04 LTS with Docker Engine",
              "Ubuntu 24.04 LTS with Docker Engine" in onboarding, "")

        manual_tests = (REPO / "MANUAL-TESTS.md").read_text()
        check("[task034] MANUAL-TESTS has the Linux host section",
              "## Linux host (Ubuntu 24.04 LTS)" in manual_tests, "")
        check("[task034] MANUAL-TESTS names the [L] acceptance criteria",
              "`[L]` acceptance criteria" in manual_tests, "")
        for n in range(44, 51):
            check(f"[task034] MANUAL-TESTS has Test {n}", f"### Test {n}:" in manual_tests, "")
