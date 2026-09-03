# /vs spec draft — Linux host support (Tier 2)

**Status:** draft; not for execution now. Source: `/brain2/andeye/vibe-roadmap-2026-09.md` answer 1, Tier 2. Evidence at `5125e3c`.

## Task summary

Make a Linux box a first-class vibe host (reference: **Ubuntu 24.04 LTS + Docker Engine**, not Docker Desktop). Two real gaps: `host.docker.internal` does not exist on native Docker Engine, and `.local` mDNS depends on the host resolver. The rest is Mac-only ergonomics (clipboard, installer hints) and missing Linux test coverage — BSD/GNU paths are already dual (`vibe:799, 1264, 1457, 2702`), the image multi-arch. **Every change additive or `uname`-guarded; the Darwin path stays byte-identical.**

## Changes

### (a) Unconditional `--add-host=host.docker.internal:host-gateway`

`runArgs` are assembled in one place: the embedded Python in `render_devcontainer_with_mounts` (`vibe:1499-1556`), called once from `_build_override_config` (`vibe:2922-2924`), rendering `$HOME/.vibe/run/devcontainer-<sha1>.json` from `devcontainer/devcontainer.json` (base `runArgs` `:4-7`). That override always renders, so add the flag to the base JSON and keep the Python's `if flag not in cfg["runArgs"]` guard (`vibe:1531`) against doubling up with the `/op` injection.

Safety confirmed: `host-gateway` is Docker Engine 20.10+ and universal since; OrbStack accepts it (≥0.6.0); and **vibe already ships a `:host-gateway` add-host on the Mac** whenever `/op` is configured (`vibe:1530`), with `init-firewall.sh:275-291` recording it resolving in production. On Docker Desktop/OrbStack the extra `/etc/hosts` line names the same gateway the embedded DNS returns — a no-op; on Linux it is the only way the name exists. `init-firewall.sh:280` uses `getent hosts`, so it copes either way, and `setup-ssh.sh:67`'s `ssh-keyscan` seed then succeeds on Linux.

### (b) `uname`-guarded clipboard; host-watcher no-op on Linux

Add `vibe_clipboard_cmd()` **above** the `VIBE_SOURCE_ONLY` guard (`vibe:3182`) so tests can source it: `pbcopy` on Darwin, else the first of `wl-copy` → `xclip -selection clipboard` → `xsel --clipboard --input` (bare `xclip`/`xsel` write the X11 PRIMARY selection, not the clipboard) present, else empty. At `vibe:3847` keep the Darwin branch **verbatim** (its exit-hook body is byte-pinned at `smoke/checks_04_hooks_guards.py (test_task008_ac3_block_scoping, test_task008_ac11_direct_read, test_clipboard_drain_on_exit) and smoke/checks_07_sharedrepos_cycles.py:803-804`) and add a separate `else` branch exporting `VIBE_COPY_CMD`, which `vibe-copy-watcher.sh:11` already honours; relax the watcher gate (`:8`) to "Darwin **or** `VIBE_COPY_CMD` set". Headless Linux → watcher never starts, `/c` falls back to the scratch file, and `smoke/checks_04_hooks_guards.py (test_clipboard_drain_on_exit)` stays green. mtime reads are already dual.

### (c) `install.sh` apt/dnf hints + Linux preflight

`preflight_deps` (`install.sh:26-45`) hard-codes `brew`/`xcode-select`. Branch on `uname -s`, and on Linux on `/etc/os-release` `ID`/`ID_LIKE`: apt (`apt-get install -y git nodejs gh`, Docker Engine via the `docker-ce` repo) or dnf. Three Linux-only checks: daemon reachable (`docker info`); user in the `docker` group (`id -nG | grep -qw docker`; remedy `sudo usermod -aG docker $USER` + re-login — **warn, don't exit**, rootless Docker legitimately fails it); `devcontainer` on PATH. macOS output byte-identical. Same for the "Next steps" heredoc (`install.sh:110-124`).

### (d) mDNS

The image carries `avahi-daemon`/`libnss-mdns` and rewrites nsswitch (`Dockerfile:37-44`), started by `postStartCommand`, but on a Linux host the bridge NATs multicast, so `.local` may not resolve. Document: the **host** needs systemd-resolved with `MulticastDNS=yes` or `avahi-daemon`; in-container the supported path to the host is `host.docker.internal`. Add a once-per-machine Linux launch probe (marker `~/.vibe/mdns-probe`): if `getent hosts "$(hostname).local"` fails, warn once, naming the remedy. **Bug found while auditing:** the `Dockerfile:44` sed is not idempotent — this container's live nsswitch reads `mdns4_minimal [NOTFOUND=return]` twice. Guard it.

### (e) Docs

`README.md:24` ("Linux untested") → a Linux subsection: Ubuntu 24.04 LTS + Docker Engine, docker group, apt deps, the `.local` caveat, `host.docker.internal` as the host path. Mark the build bridge (`README.md:70-79`) macOS-only. `ONBOARDING.md` steps 2-4 fork for apt (no Homebrew/`xcode-select`).

### (f) MANUAL-TESTS

New `## Linux host (Ubuntu 24.04 LTS)` section, Tests 44-50, each naming the Mac test it mirrors: 44 fresh install + preflight without Docker; 45 first launch (build, PAT prompt, banner); 46 firewall (Test 28 fail-closed, plus `getent hosts host.docker.internal`); 47 SSH to a LAN host by IP **and** `.local`; 48 `/c` under Wayland, X11, headless; 49 auto-rebuild (Test 16); 50 history bind + brain2/Zotero mounts (Tests 42, 29).

### (g) Smoke tests (in-container, no Docker)

All via `_source_vibe_call` with `VIBE_SOURCE_ONLY=1` and a fixture `uname` shim first on `PATH`: exactly-one `--add-host=host.docker.internal:host-gateway` in the rendered override, `/op` on and off; `vibe_clipboard_cmd` precedence under Darwin/Linux/no-tool shims; watcher exit-0 without `VIBE_COPY_CMD`; `install.sh` hint text per platform (plus `bash -n`); the Darwin-invariance diff (AC4).

## Acceptance criteria

1. `python3 code-check.py` clean.
2. `python3 smoke-test.py` green, no test deleted.
3. Rendered override carries exactly one `host.docker.internal:host-gateway`, `/op` on and off.
4. **Mac path unchanged (except the one intended line):** the test embeds a LITERAL golden of the pre-change rendered override for a fixed fixture input (captured from the current launcher before this task and pasted into the test as a string — never derived from the post-change or current `devcontainer.json`); under a Darwin `uname` shim the newly rendered override must equal that golden plus exactly the one `--add-host=host.docker.internal:host-gateway` line and nothing else. (Critique: a golden computed from current sources would be tautological.)
5. Exit-hook literal `pbcopy < "$CLIP"` unchanged; the three clipboard pins in `smoke/checks_04_hooks_guards.py` green.
6. `vibe_clipboard_cmd`: `pbcopy` (Darwin), `wl-copy`>`xclip`>`xsel` (Linux), empty (none).
7. Watcher exits 0 on Linux with no clipboard tool; runs with `VIBE_COPY_CMD`.
8. `install.sh` Darwin output byte-identical to pre-change.
9. Linux preflight names apt/dnf, docker group, `devcontainer`; group failure warns, exits 0.
10. `Dockerfile` nsswitch edit idempotent (twice-applied ⇒ one `mdns4_minimal`). Existing images already carry the duplicate line (verified in a live container 2026-09-02): the fix only lands on a real rebuild — README/CHANGELOG say `vibe --rebuild` (cache-busted) is required, and MANUAL-TESTS gets a check that `/etc/nsswitch.conf` has exactly one `mdns4_minimal` after rebuild.
11. README + ONBOARDING Linux sections exist; build bridge marked macOS-only.
12. **[L]** Fresh Ubuntu 24.04: install, launch, firewall fail-closed, `host.docker.internal` resolves.
13. **[L]** Container SSH to a LAN host by IP and `.local`; mDNS probe warns once on failure.
14. **[L]** `/c` copies under Wayland and X11; Mac `/c` unchanged.

`[L]` = needs a real Linux box → MANUAL-TESTS 44-50, not the smoke suite.

## Out of scope

Windows/WSL2 (`vibe.cmd`); the multi-target build bridge (`.vibe/targets`, `vibe targets`, `vibe-build`); arm64/Pi 5; Homebrew tap and tagged releases.

## Model plan

Spec Critic **sonnet**. Generator **sonnet** for (a), (c)-(f); **opus** for (b), which touches byte-pinned exit-hook strings. Tester **haiku**: `code-check.py`, `smoke-test.py`, fixture shims. No credit-billed rung.

## Risks

**Breaking the Mac path is the only real risk.** Mitigations: every edit additive or `uname`-guarded; AC4's golden byte-diff; AC5's pinned-string assertion; the `/op` precedent proves `host-gateway` already works on Mac Docker. Residual: `/etc/hosts` now shadows Docker Desktop's embedded DNS for that name (same IP — verify on the Mac before merge); rootless Docker fails the group check (warn only); no clipboard tool on minimal server installs (silent no-op by design).


## Critique-driven amendments (2026-09-02)
- Clipboard: the `pbcopy` flush and `vibe-copy-watcher.sh` run HOST-side in the launcher, never in the container; the Linux fallback chain (`wl-copy` → `xclip -selection clipboard` → `xsel --clipboard --input`) is wired in the launcher's host-side branch only. The watcher gate becomes a 3-way OR: Darwin, OR `VIBE_COPY_CMD` set, OR `VIBE_COPY_WATCHER_FORCE` set (the existing `test_vibe_path_prefix_isolation` relies on FORCE alone) — no existing test deleted or weakened.
- The `uname` PATH shim is new test infrastructure: the Generator's first scratch test proves the shim shadows the real `uname` (`uname -s` prints the fixture value) before any assertion relies on it.
- `/op`'s existing `--add-host=<op_host>:host-gateway` is a different hostname; no dedup logic needed, only an "exactly one host.docker.internal entry" assertion.
- Re-verification on real Docker Desktop and OrbStack after shipping goes to MANUAL-TESTS (a Mac-side check that `getent hosts host.docker.internal` inside the container still resolves).

- Iteration-2 amendments: test citations point at the split layout (smoke/); AC6 uses the flagged `xclip -selection clipboard` / `xsel --clipboard --input` invocations everywhere.
