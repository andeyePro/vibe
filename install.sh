#!/bin/bash
# vibe installer. Run with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
set -euo pipefail

REPO_URL="https://github.com/Aqueum/vibe.git"
SRC_DIR="$HOME/.vibe-src"
CONFIG_DIR="$HOME/.vibe"
BIN_DIR="$HOME/bin"

echo "vibe installer"
echo ""

# 1. Clone or update source
if [ -d "$SRC_DIR/.git" ]; then
  echo "  Updating $SRC_DIR..."
  git -C "$SRC_DIR" pull --ff-only
else
  echo "  Cloning vibe to $SRC_DIR..."
  git clone "$REPO_URL" "$SRC_DIR"
fi

# 2. Symlink vibe onto PATH
mkdir -p "$BIN_DIR"
ln -sf "$SRC_DIR/vibe" "$BIN_DIR/vibe"
echo "  ✓ Linked $BIN_DIR/vibe → $SRC_DIR/vibe"

# 3. Remove legacy devcontainer copy (vibe now reads from $SRC_DIR directly).
#    Prior installs cp -R'd devcontainer/ into $CONFIG_DIR, which went stale the
#    moment anyone edited the repo. Clean up so nothing drifts from the clone.
if [ -d "$CONFIG_DIR/devcontainer" ] && [ ! -L "$CONFIG_DIR/devcontainer" ]; then
  rm -rf "$CONFIG_DIR/devcontainer"
  echo "  ✓ Removed legacy $CONFIG_DIR/devcontainer (now read from $SRC_DIR/devcontainer)"
fi
mkdir -p "$CONFIG_DIR"

# 4. Write default config if absent
if [ ! -f "$CONFIG_DIR/config" ]; then
  read -rp "  Projects directory [$HOME/Projects]: " proj_dir
  proj_dir="${proj_dir:-$HOME/Projects}"
  cat > "$CONFIG_DIR/config" <<EOF
VIBE_PROJECTS_DIR="$proj_dir"
EOF
  echo "  ✓ Wrote $CONFIG_DIR/config"
fi

# 5. Dependency check
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
