# Generator report — task_034 cycle 1 (Linux host support)

Worktree `/workspace/.claude/worktrees/task034`, branch `vsss/task034-linux-host`,
baseline `3b23b19`. No commit, no push, no `vibe`, no ssh. CHANGELOG.md and
TODO.md deliberately untouched (chair writes them on main at merge).

## Gate results

| Gate | Command | Exit | Result |
|---|---|---|---|
| shellcheck | `python3 code-check.py` | **0** | ✓ clean across 19 files |
| smoke suite | `python3 smoke-test.py` | **1** | 2 failures, both **pre-existing environment** (proof below) |
| scratch proof (red) | `scratch_test_task034.py --head` | 0 | 19 failed / 31 passed — every code AC red pre-change |
| scratch proof (green) | `scratch_test_task034.py` | **0** | **50 passed, 0 failed** |

### The two smoke failures are environment, not regression

`- announces in-place use` and `- symlink points at repo checkout`
(`smoke/checks_01_launcher_basics_and_codecheck.py`). Cause: `install.sh:63`
gates in-place-clone detection on `[ -d "$SELF_DIR/.git" ]`, and in **any** git
worktree `.git` is a *file*, not a directory, so the installer falls through to
the clone branch.

Proved by stashing all eight changed files and re-running the suite on
unmodified HEAD sources in this same worktree: **the identical two checks
fail**, with the same `readlink=/tmp/…/.vibe-src/vibe`. Do not "fix" these.

## The AC4 golden — capture procedure and location

AC4 is the anti-tautology criterion, so ordering was load-bearing. Sequence
actually followed, before a single source byte changed:

1. Built a Darwin `uname` shim at
   `.vs/cycle-1/scratch-tests/shimbin-darwin/uname`.
2. **Proved the shim shadows the real `uname` before relying on it** (spec
   amendment 2): real `uname -s` → `Linux`; under the shimmed PATH → `Darwin`;
   `command -v uname` → the fixture path. Re-asserted every run as scratch test
   `[0]`.
3. Verified the tree was clean at `3b23b19` (`git status --porcelain` showed
   only untracked `.vs/spec.md`; `md5sum` recorded for `vibe` and
   `devcontainer/devcontainer.json`).
4. Ran `.vs/cycle-1/scratch-tests/capture_golden.sh`, which sources the
   **pre-change** launcher with `VIBE_SOURCE_ONLY=1` under the Darwin shim and
   calls `render_devcontainer_with_mounts` (the function the spec names) on a
   fixed fixture input: `devcontainer/devcontainer.json` plus three literal
   mount triples (`/fixture/host/projects`→`/home/node/.claude/projects` rw,
   `/fixture/host/brain2`→`/brain2` rw, `/fixture/host/zotero`→`/zotero` ro),
   once with `VIBE_OP_ADDHOST=""` and once with `VIBE_OP_ADDHOST=op.example.invalid`.

Goldens live at (committed as new files, `git add -N`'d):

- `.vs/cycle-1/fixtures/golden-override-op-off.json` — 83 lines, md5 `56e1b54a…`
- `.vs/cycle-1/fixtures/golden-override-op-on.json` — 84 lines, md5 `ab7ccd95…`
- `.vs/cycle-1/fixtures/golden-install-darwin.txt` — AC8 golden (below)
- `.vs/cycle-1/fixtures/install.sh.prechange` — `git show HEAD:install.sh`, the
  source the AC8 golden was rendered from

The AC4 assertion does **not** diff loosely. It parses the literal golden,
applies the *only* permitted transform (insert the one `--add-host` after the
`--cap-add=` entries), re-serialises exactly as the launcher's embedded Python
does (`json.dumps(indent=2)` + trailing newline), and demands **byte equality**
with the freshly rendered override. It also asserts the golden itself contains
no `host.docker.internal` — a contamination check against a tautological golden.

## Changes, by spec item

### (a) Unconditional `--add-host=host.docker.internal:host-gateway`

- `devcontainer/devcontainer.json:7` — added to base `runArgs`.

The embedded Python's `if flag not in cfg["runArgs"]` guard (now `vibe:1531`)
is untouched. `/op`'s injection uses a *different* hostname, so no dedup logic
was needed — only the "exactly one `host.docker.internal` entry" assertion,
verified `/op` on and off (AC3).

### (b) `uname`-guarded clipboard; watcher no-op on headless Linux

- `vibe:3136` `vibe_clipboard_cmd()` — **above** the `VIBE_SOURCE_ONLY` guard
  (now `vibe:3247`) so the suite can source it. `pbcopy` on Darwin (only if
  actually present), else `wl-copy` → `xclip -selection clipboard` →
  `xsel --clipboard --input`, else empty. The explicit selection flags are the
  point: bare `xclip`/`xsel` write PRIMARY, not CLIPBOARD.
- `vibe:3931` — a new `elif` branch after the Darwin block. **The Darwin branch
  is byte-identical**; the `elif` deliberately assigns neither `CLIP=` nor
  `WATCHER_SEED_MTIME=`, because `test_task008_ac3_block_scoping` scans from the
  Darwin `if` to the *first* `fi` and pins each to exactly one occurrence — an
  `elif` keeps that range intact while an inner `fi` + new `if` would not. It
  exports `VIBE_COPY_CMD`, starts the same watcher, and registers a
  kill-only exit hook *after* the pinned drain (preserving the
  seed < drain < kill offset ordering that `test_clipboard_drain_on_exit` (e)/(f)
  asserts).
- `vibe-copy-watcher.sh:13` — gate is now the **3-way OR**: Darwin, OR
  `VIBE_COPY_CMD` set, OR `VIBE_COPY_WATCHER_FORCE`. `test_vibe_path_prefix_isolation`
  relies on FORCE alone and still passes; no test deleted or weakened.

All three byte-pinned clipboard checks in `smoke/checks_04_hooks_guards.py` and
the pin in `smoke/checks_07_sharedrepos_cycles.py:803` are green (AC5).

### (c) `install.sh` Linux preflight + apt/dnf hints

- `install.sh:32-33` — `VIBE_OS` detection. **Regression found and fixed here:**
  the first cut used a bare `$(uname -s)`, which is fatal under `set -e` in
  `test_install_preflight`, whose whole point is running the script with an
  *empty* `PATH` (no `uname`). It now degrades to `Darwin`, which is exactly the
  pre-Linux behaviour, so that test's semantics are preserved.
- `install.sh:38` `vibe_linux_pkg()` — apt/dnf family from `/etc/os-release`
  `ID`/`ID_LIKE`; unrecognised → generic hints rather than wrong ones.
- `install.sh:57` `vibe_dep_hint()` — the Darwin arm at `:58` holds the five
  original strings **verbatim**; the Linux arm points Docker at the `docker-ce`
  repo, never `docker.io`.
- `install.sh:111` `preflight_linux()` — returns early on Darwin. Three Linux
  checks: `docker info` reachable, `id -nG | grep -qw docker`, and
  `devcontainer` on PATH (via `preflight_deps`). Both new checks **warn and
  continue** — rootless Docker legitimately has no `docker` group (AC9).
- `install.sh:194/206` — "Next steps" heredoc forked three ways; the Darwin
  heredoc is unchanged.

AC8 is asserted as **byte equality** against `golden-install-darwin.txt`,
rendered from `install.sh.prechange` under a Darwin shim with all five deps
absent.

### (d) mDNS

- `devcontainer/Dockerfile:51` — nsswitch `sed` made idempotent by skipping the
  substitution when the `hosts:` line already mentions `mdns4_minimal`. Proven:
  applied three times to a clean fixture, exactly one entry, still before `dns`.
- `vibe:3156` `vibe_mdns_probe_needed()` / `vibe:3166` `vibe_mdns_probe()`,
  called at `vibe:3378` in the preflight block. Linux-only, once per machine
  (marker `~/.vibe/mdns-probe`, overridable via `VIBE_MDNS_MARKER` for testing).
  The marker is written **before** the probe runs, so even a hang or an odd
  resolver can't produce a warning on every launch. Never fails the launch.

### (e) Docs

- `README.md:24` — "Linux untested" replaced with a link to the new section.
- `README.md:30` — `## Linux hosts`: Ubuntu 24.04 LTS + Docker Engine, apt
  deps, docker group, `host.docker.internal` as the supported host path, the
  `.local` caveat and its remedy, and the **cache-busted `vibe --rebuild`**
  paragraph AC10 requires, with `grep -c mdns4_minimal` as the confirmation.
- `README.md:117` — build bridge retitled and flagged **macOS-only**.
- `ONBOARDING.md` — steps 2–4 forked: `:37` step 2 marked Mac-only, `:49` new
  step 2L (apt index, explicitly no Homebrew/`xcode-select`), `:73` new step 3L
  (Docker Engine, `systemctl enable --now docker`, `usermod -aG docker`, with a
  `docker run hello-world` **without sudo** check), `:91` step 4 forked.

### (f) MANUAL-TESTS — the `[L]` criteria, as tests not code

`MANUAL-TESTS.md:1109` `## Linux host (Ubuntu 24.04 LTS)`, Tests 44–50, each
naming the Mac test it mirrors, each with exact commands and expected output:

- **44** fresh install + preflight without Docker (mirrors 1) — asserts no
  `brew`/`xcode-select` in Linux output, and that the group warning **exits 0**
- **45** first launch: build, PAT prompt, banner (mirrors 2)
- **46** firewall fail-closed + `getent hosts host.docker.internal` (mirrors 28),
  plus `docker inspect … ExtraHosts` for exactly-one, plus the **Mac
  re-verification** on Docker Desktop *and* OrbStack the spec's residual risk asks for
- **47** SSH by IP **and** `.local`; mDNS probe warns exactly once (mirrors 43)
- **48** `/c` under Wayland, X11 (clipboard selection, **not** PRIMARY) and
  headless; Mac `/c` unchanged (mirrors 12)
- **49** auto-rebuild (mirrors 16), carrying the AC10 post-rebuild
  `grep -c mdns4_minimal /etc/nsswitch.conf` == 1 check
- **50** history bind + brain2/Zotero mounts (mirrors 42, 29), incl. the
  Linux-specific direct uid/gid mapping risk

### (g) Smoke tests

Per the brief these belong to the **Tester**; I wrote none into `smoke/`. My
proof is `.vs/cycle-1/scratch-tests/scratch_test_task034.py` (50 assertions,
red against `--head`, green against the working tree) plus the golden fixtures
the spec assigns to the Generator.

## Unsatisfied / flagged for the Evaluator

1. **AC12–14 are `[L]`** — Tests 44–50, not executable here. No real Linux
   *host* is available (this container is not a Docker host), so
   `--add-host` reaching the container, `.local` over the bridge, and Wayland/X11
   `/c` are argued from the `/op` precedent, not observed.
2. **Residual Mac risk, unchanged from the spec.** On Docker Desktop/OrbStack the
   new `/etc/hosts` line now shadows the embedded DNS answer for
   `host.docker.internal`. Same IP by construction, but *verify on the Mac before
   merge* — booked as the Mac re-verification in Test 46.
3. **AC10 only lands on rebuild.** Existing images keep the duplicate
   `mdns4_minimal`; the source is fixed and idempotent, but nothing verifies the
   live image until someone runs a cache-busted `vibe --rebuild`. Documented in
   README and Test 49.
4. `preflight_linux` runs a real `docker info` with no timeout. Fast against a
   live or absent socket; a *hung* daemon socket would stall the installer. Left
   as-is to match how `docker info` behaves elsewhere in the tree — flagging it
   rather than adding an unrequested `timeout` dependency.
5. `smoke/checks_01`'s two in-place-detection tests remain red in any worktree
   (`.git` is a file). Pre-existing; explicitly not fixed.

## Handoff note for the Tester — where the golden actually lives

`.gitignore:21` ignores `.vs/cycle-*/`, so the cycle-1 fixtures are **not**
committable and correctly do not appear in `diff.patch`. That matches AC4's own
wording — the golden is to be *"pasted into the test as a string"*, not shipped
as a repo fixture.

Paste-ready literals: **`.vs/cycle-1/fixtures/goldens_literal.py`**, exporting
`GOLDEN_OVERRIDE_OP_OFF`, `GOLDEN_OVERRIDE_OP_ON` and
`GOLDEN_INSTALL_DARWIN_OUTPUT`, with the capture procedure in its header
comment. Round-trip-verified byte-identical to the captured `.json`/`.txt`.

Do **not** regenerate these from the current tree — that is exactly the
tautology the criterion exists to prevent. `.vs/cycle-1/fixtures/install.sh.prechange`
(`git show HEAD:install.sh`) is kept so the AC8 golden can be re-derived from
pre-change source if ever needed.
