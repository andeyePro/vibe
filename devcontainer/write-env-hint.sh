#!/bin/bash
# Writes a short environment hint to Claude Code's user-level CLAUDE.md inside
# the container, so Claude knows SSH works and what the firewall allows without
# being told every session. Uses a managed block so it can be safely re-run
# and coexists with any other content the user adds to the file.

set -euo pipefail

TARGET="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md"
START="<!-- BEGIN vibe env (managed) -->"
END="<!-- END vibe env -->"

BLOCK="$START
# vibe container environment
You are running in a vibe container on the user's Mac. Outbound SSH is allowed and ~/.ssh is populated from the host (sanitised for Linux) — \`ssh\`, \`scp\`, and rsync-over-ssh work for any host the user already has keys for, including \`.local\` mDNS names on the Mac's LAN. Other outbound traffic is restricted to an allowlist (GitHub, npm, Anthropic, VS Code marketplace); arbitrary HTTP to other sites will fail by design, not by accident.
$END"

mkdir -p "$(dirname "$TARGET")"
touch "$TARGET"

# Strip any existing managed block, then trim leading/trailing blank lines so
# repeated runs don't accumulate whitespace.
REMAINING=$(awk -v start="$START" -v end="$END" '
  $0 == start { inblock = 1; next }
  $0 == end && inblock { inblock = 0; next }
  !inblock { lines[++n] = $0 }
  END {
    first = 0; last = 0
    for (i = 1; i <= n; i++) if (lines[i] != "") { first = i; break }
    for (i = n; i >= 1; i--) if (lines[i] != "") { last = i; break }
    if (first) for (i = first; i <= last; i++) print lines[i]
  }
' "$TARGET")

if [ -n "$REMAINING" ]; then
  printf "%s\n\n%s\n" "$BLOCK" "$REMAINING" > "$TARGET.tmp"
else
  printf "%s\n" "$BLOCK" > "$TARGET.tmp"
fi
mv "$TARGET.tmp" "$TARGET"
