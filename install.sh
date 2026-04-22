#!/bin/bash
# vibe installer.
#
# End users (install fresh from GitHub):
#   bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
#   → clones vibe to ~/.vibe-src and symlinks ~/bin/vibe into it.
#
# Developers (running install.sh from inside an existing clone):
#   ./install.sh
#   → uses the clone in-place as the source. ~/bin/vibe points at your
#     working tree, so edits take effect immediately with no git pull.
set -euo pipefail

REPO_URL="https://github.com/Aqueum/vibe.git"
DEFAULT_SRC_DIR="$HOME/.vibe-src"
CONFIG_DIR="$HOME/.vibe"
BIN_DIR="$HOME/bin"

echo "vibe installer"
echo ""

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
