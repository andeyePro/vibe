# /vs spec draft — language-profile presets (Tier 2)

**Status:** draft, not for execution. Source: `TODO.md` Open ("language-profile presets, à la ClaudeBox"); roadmap Tier 2, "biggest new-user win". Evidence at `5125e3c`.

## Shape

**A profile is a thin child image built `FROM` the unchanged base.** `devcontainer/profiles/<name>/Dockerfile` opens `ARG BASE=vibe-dev:latest` / `FROM ${BASE}` and adds one `RUN` layer; the launcher runs `docker build --build-arg BASE="$IMAGE_TAG" -t vibe-dev:<name> devcontainer/profiles/<name>`.

Not a single Dockerfile with `ARG PROFILE` and a conditional `RUN`: that adds a layer to the base's graph, so **every existing user rebuilds** on next launch, and the conditional collapses all profiles onto one cache key. The child image keeps the base byte-identical for profile-less users, shares its layers, and self-invalidates — a base rebuild changes the `FROM` digest.

**Build-time, not postStart.** Installs run before `init-firewall.sh` executes at postStart, so pypi / crates.io / static.rust-lang.org need **no allowlist entry**; a postStart install would need firewall holes in every container, profiled or not. Strongest argument for the shape; say so in the README.

**Scope boundary:** a profile ships a *toolchain* (interpreter, compiler, package manager, formatter, LSP), never project dependencies — those change per commit and are the project's job.

## Selection

Precedence, first hit wins: `vibe --profile <name>` → `.vibe/profile` (one line, gitignored with the rest of `.vibe/`) → `VIBE_PROFILE` in `~/.vibe/config` → base.

**No auto-detect in v1.** Detecting `package.json` and silently swapping the image would change the container under every existing user — what "base unchanged for everyone else" forbids. Detection is a *suggestion*: one stderr line, once per machine per project (marker under `~/.vibe/`), naming the flag.

Custom profiles resolve after the shipped set: `~/.vibe/profiles/<name>/Dockerfile`, machine-local, same tags. An unknown name is a hard error listing what exists — never a silent fall-through.

## Launcher changes

- `IMAGE_TAG` becomes profile-aware (`vibe-dev:latest` | `vibe-dev:<name>`); `IMAGE_MARKER` gains the same suffix, so base and profile staleness track separately. Profile stale = its dir newer than its marker, **or** base rebuilt this launch.
- `devcontainer.json` hard-codes `"image": "vibe-dev:latest"` — `render_devcontainer_with_mounts` sets `cfg["image"]` from a new `VIBE_IMAGE_TAG` env, beside `VIBE_OP_ADDHOST`.
- **Container reuse is the trap.** Switching profile changes the image, but a plain relaunch reuses the container — task_030's mount-drift bug in a new costume. Extend the drift comparator to `docker inspect`'s `Config.Image`, auto-appending `--remove-existing-container`.
- The launch header names the profile.

## First profiles

`node` is not worth shipping — the base is `FROM node:20` (`Dockerfile:9`), so the layer would be near-empty. **Swift is not a real profile**: the Linux toolchain is ~1.5 GB and cannot build Apple targets. Recommend **python** (3.12 + uv + ruff + mypy, ~250 MB), **rust** (rustup + clippy + rustfmt, ~1.2 GB), **go** (~450 MB).

## Acceptance criteria

1. `code-check.py` clean; `smoke-test.py` green, no test deleted.
2. **Base unchanged:** `devcontainer/Dockerfile` gains no `ARG`, `RUN` or `COPY`; a literal golden of the pre-change file asserts byte-identity.
3. No profile selected: tag `vibe-dev:latest`, marker `~/.vibe/.image-built`, no `image` key added — output byte-identical to pre-change.
4. Precedence resolves flag > `.vibe/profile` > `VIBE_PROFILE` > none: one test per rung, one for the ladder.
5. Unknown profile exits non-zero listing available names; `--profile none` pins base and suppresses the suggestion.
6. Rendered override sets `"image": "vibe-dev:<name>"` when profiled; mounts/`runArgs`/`remoteEnv` otherwise unchanged.
7. Drift comparator returns recreate when `Config.Image` differs from the resolved tag, reuse when it matches, mounts constant.
8. Profile staleness fires when its dir is newer than its marker, and when base rebuilt this launch; silent otherwise.
9. Each profile Dockerfile passes `docker build --check` and declares `ARG BASE` / `FROM ${BASE}`; a test asserts none reaches a host outside the declared build-time set.
10. **[M]** Live: `vibe --profile python` builds, tools on PATH, firewall unchanged; relaunching without the flag recreates onto base. → MANUAL-TESTS.

## The one question for Martin

**Which three profiles ship first, and what incremental image size is acceptable per profile?** Recommend python, rust, go — dropping node (already the base) and Swift (Linux Swift cannot target Apple platforms). Budget: 500 MB incremental, enforced by a build-time size check, rust exempted at ~1.2 GB. If the answer is "nothing over 500 MB", rust ships slim (no docs, no `rust-analyzer`) or waits.
