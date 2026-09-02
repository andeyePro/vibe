#!/bin/bash
# vibe installer.
#
# End users (install fresh from GitHub):
#   bash <(curl -fsSL https://raw.githubusercontent.com/andeyePro/vibe/main/install.sh)
#   → clones vibe to ~/.vibe-src and symlinks ~/bin/vibe into it.
#
# Developers (running install.sh from inside an existing clone):
#   ./install.sh
#   → uses the clone in-place as the source. ~/bin/vibe points at your
#     working tree, so edits take effect immediately with no git pull.
set -euo pipefail

REPO_URL="https://github.com/andeyePro/vibe.git"
DEFAULT_SRC_DIR="$HOME/.vibe-src"
CONFIG_DIR="$HOME/.vibe"
BIN_DIR="$HOME/bin"

echo "vibe installer"
echo ""

# ── Platform detection (task_034) ─────────────────────────────────────────────
# vibe supports macOS (primary) and Linux (reference: Ubuntu 24.04 LTS + Docker
# Engine, NOT Docker Desktop). Everything platform-specific below branches on
# VIBE_OS; the Darwin path is byte-identical to the pre-Linux installer.
# VIBE_OS / VIBE_PKG are overridable so the smoke suite can exercise each
# platform's hint text without a matching host.
# `uname` itself can be absent (the smoke suite runs this script with an empty
# PATH to exercise the all-deps-missing path), and `set -e` would abort on a
# failed command substitution. Degrade to Darwin: that is exactly the
# pre-Linux-support behaviour, so an unknown platform keeps the old output.
VIBE_OS="${VIBE_OS:-$(uname -s 2>/dev/null || true)}"
[ -n "$VIBE_OS" ] || VIBE_OS="Darwin"

# vibe_linux_pkg — echo the package-manager family for this Linux box, from
# /etc/os-release ID / ID_LIKE. "apt" for Debian/Ubuntu, "dnf" for Fedora/RHEL,
# "" when neither is recognised (hints then stay generic rather than wrong).
vibe_linux_pkg() {
  local id="" like=""
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091  # runtime host file, not shipped in this repo
    id="$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-}")"
    like="$(. /etc/os-release 2>/dev/null && printf '%s' "${ID_LIKE:-}")"
  fi
  case " $id $like " in
    *" debian "*|*" ubuntu "*) printf 'apt' ;;
    *" fedora "*|*" rhel "*|*" centos "*) printf 'dnf' ;;
    *) printf '' ;;
  esac
}
VIBE_PKG="${VIBE_PKG:-}"
if [ "$VIBE_OS" != "Darwin" ] && [ -z "$VIBE_PKG" ]; then
  VIBE_PKG="$(vibe_linux_pkg)"
fi

# vibe_dep_hint <cmd> — echo the platform-appropriate remedy for a missing dep.
vibe_dep_hint() {
  if [ "$VIBE_OS" = "Darwin" ]; then
    case "$1" in
      git)          echo "  ✗ git missing — xcode-select --install" ;;
      docker)       echo "  ✗ docker missing — brew install --cask orbstack  (or Docker Desktop: https://www.docker.com/products/docker-desktop/)" ;;
      node)         echo "  ✗ node missing — brew install node" ;;
      devcontainer) echo "  ✗ devcontainer missing — npm install -g @devcontainers/cli" ;;
      gh)           echo "  ✗ gh missing — brew install gh  (then: gh auth login)" ;;
    esac
    return 0
  fi
  # Linux. Docker gets the docker-ce repo, never the distro's stale docker.io.
  case "$VIBE_PKG:$1" in
    apt:git)    echo "  ✗ git missing — sudo apt-get install -y git" ;;
    dnf:git)    echo "  ✗ git missing — sudo dnf install -y git" ;;
    *:git)      echo "  ✗ git missing — install git with your distro's package manager" ;;
    apt:docker) echo "  ✗ docker missing — install Docker Engine from the docker-ce repo: https://docs.docker.com/engine/install/ubuntu/" ;;
    dnf:docker) echo "  ✗ docker missing — install Docker Engine from the docker-ce repo: https://docs.docker.com/engine/install/fedora/" ;;
    *:docker)   echo "  ✗ docker missing — install Docker Engine: https://docs.docker.com/engine/install/" ;;
    apt:node)   echo "  ✗ node missing — sudo apt-get install -y nodejs npm  (or nodesource for a current LTS)" ;;
    dnf:node)   echo "  ✗ node missing — sudo dnf install -y nodejs npm" ;;
    *:node)     echo "  ✗ node missing — install Node.js 18+ with your distro's package manager" ;;
    *:devcontainer) echo "  ✗ devcontainer missing — npm install -g @devcontainers/cli" ;;
    apt:gh)     echo "  ✗ gh missing — sudo apt-get install -y gh  (then: gh auth login)" ;;
    dnf:gh)     echo "  ✗ gh missing — sudo dnf install -y gh  (then: gh auth login)" ;;
    *:gh)       echo "  ✗ gh missing — install the GitHub CLI: https://cli.github.com  (then: gh auth login)" ;;
  esac
}

# ── Preflight: required dependencies ──────────────────────────────────────────
# Check everything a vibe session needs BEFORE cloning or touching ~/bin, so a
# fresh machine gets one actionable list instead of a half-finished install and
# a launcher that can't run. No-op (silent) when every dependency is present.
preflight_deps() {
  local cmd missing=0
  for cmd in git docker node devcontainer gh; do
    command -v "$cmd" >/dev/null 2>&1 && continue
    missing=1
    vibe_dep_hint "$cmd"
  done
  if [ "$missing" -ne 0 ]; then
    echo ""
    echo "  Install the missing dependencies above, then re-run this installer."
    echo "  (A Claude Pro or Max subscription is also required to launch a session.)"
    exit 1
  fi
}
preflight_deps

# ── Linux-only preflight: daemon reachable + docker group (task_034) ──────────
# Runs AFTER preflight_deps, so `docker` is known to exist. Both checks WARN
# and continue: rootless Docker legitimately fails the group check, and a
# daemon that is merely stopped is a one-command fix, not a reason to refuse
# to install the launcher. macOS output is unaffected (function returns early).
preflight_linux() {
  [ "$VIBE_OS" = "Darwin" ] && return 0
  if ! docker info >/dev/null 2>&1; then
    echo "  ⚠  docker daemon not reachable — start it with:"
    echo "       sudo systemctl enable --now docker"
    echo "     (then re-run this installer to re-check)"
  fi
  if ! id -nG 2>/dev/null | grep -qw docker; then
    echo "  ⚠  $(id -un 2>/dev/null || echo you) is not in the 'docker' group — vibe would need sudo for every"
    echo "     container command. Fix with:"
    echo "       sudo usermod -aG docker \$USER"
    echo "     then log out and back in (or: newgrp docker). Harmless to ignore if"
    echo "     you run rootless Docker, which does not use that group."
  fi
}
preflight_linux

# Detect whether we're being run from a real vibe clone. If so, use it
# in-place instead of maintaining a separate ~/.vibe-src. A "real" clone
# has install.sh sitting next to vibe + devcontainer/devcontainer.json
# inside a git working tree — curl-piped and process-substitution runs
# don't satisfy this and fall through to the default.
SELF="${BASH_SOURCE[0]:-$0}"
if [ -f "$SELF" ]; then
  SELF_DIR="$(cd "$(dirname "$SELF")" && pwd -P)"
else
  SELF_DIR=""
fi

if [ -n "$SELF_DIR" ] \
   && [ -f "$SELF_DIR/vibe" ] \
   && [ -f "$SELF_DIR/devcontainer/devcontainer.json" ] \
   && [ -d "$SELF_DIR/.git" ]; then
  SRC_DIR="$SELF_DIR"
  echo "  Using existing clone at $SRC_DIR (skipping clone/pull)."
else
  SRC_DIR="$DEFAULT_SRC_DIR"
  if [ -d "$SRC_DIR/.git" ]; then
    echo "  Updating $SRC_DIR..."
    git -C "$SRC_DIR" pull --ff-only
  else
    echo "  Cloning vibe to $SRC_DIR..."
    git clone "$REPO_URL" "$SRC_DIR"
  fi
fi

# Symlink vibe onto PATH. If the user previously installed from a different
# SRC_DIR (e.g. switching from ~/.vibe-src to a dev clone), ln -sf replaces
# the old symlink in place.
mkdir -p "$BIN_DIR"
ln -sf "$SRC_DIR/vibe" "$BIN_DIR/vibe"
echo "  ✓ Linked $BIN_DIR/vibe → $SRC_DIR/vibe"

# Remove legacy devcontainer copy (vibe now reads from $SRC_DIR directly).
# Prior installs cp -R'd devcontainer/ into $CONFIG_DIR, which went stale the
# moment anyone edited the repo. Clean up so nothing drifts from the clone.
if [ -d "$CONFIG_DIR/devcontainer" ] && [ ! -L "$CONFIG_DIR/devcontainer" ]; then
  rm -rf "$CONFIG_DIR/devcontainer"
  echo "  ✓ Removed legacy $CONFIG_DIR/devcontainer (now read from $SRC_DIR/devcontainer)"
fi
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/config" ]; then
  read -rp "  Projects directory [$HOME/Projects]: " proj_dir
  proj_dir="${proj_dir:-$HOME/Projects}"
  cat > "$CONFIG_DIR/config" <<EOF
VIBE_PROJECTS_DIR="$proj_dir"
EOF
  echo "  ✓ Wrote $CONFIG_DIR/config"
fi


echo ""
echo "  Dependencies:"

for cmd in docker devcontainer gh node; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "    ✓ $cmd"
  else
    echo "    ✗ $cmd  (missing)"
  fi
done

if [ "$VIBE_OS" = "Darwin" ]; then
cat <<'EOF'

  Next steps:
    - Ensure ~/bin is on your PATH
    - Missing deps? Install:
        OrbStack:        https://orbstack.dev
        devcontainer:    npm install -g @devcontainers/cli
        gh (GitHub CLI): brew install gh
        gh auth login
    - Then: cd <a project> && vibe
EOF
elif [ "$VIBE_PKG" = "dnf" ]; then
cat <<'EOF'

  Next steps:
    - Ensure ~/bin is on your PATH
    - Missing deps? Install:
        Docker Engine:   https://docs.docker.com/engine/install/fedora/
        devcontainer:    npm install -g @devcontainers/cli
        gh (GitHub CLI): sudo dnf install -y gh
        gh auth login
    - Add yourself to the docker group: sudo usermod -aG docker $USER  (then re-login)
    - Then: cd <a project> && vibe
EOF
else
cat <<'EOF'

  Next steps:
    - Ensure ~/bin is on your PATH
    - Missing deps? Install:
        Docker Engine:   https://docs.docker.com/engine/install/ubuntu/
        devcontainer:    npm install -g @devcontainers/cli
        gh (GitHub CLI): sudo apt-get install -y gh
        gh auth login
    - Add yourself to the docker group: sudo usermod -aG docker $USER  (then re-login)
    - Then: cd <a project> && vibe
EOF
fi
