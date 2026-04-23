#!/usr/bin/env bash
# vibe-copy — OSC 52 clipboard bridge for the vibe container.
# Reads stdin or a single file path; emits an OSC 52 escape sequence to the
# controlling terminal and writes a scratch file for terminals that lack OSC 52
# support (e.g. Apple Terminal.app).
#
# Exit codes:
#   0 — success (with possible stderr warning or note)
#   1 — payload too large OR scratch write failed
#   2 — argument validation error
#
# Env overrides (for testing):
#   VIBE_COPY_TTY         — filesystem path to write the OSC 52 sequence to
#                           (default: /dev/tty)
#   VIBE_COPY_SCRATCH_DIR — directory for copy-latest.txt scratch file
#                           (default: /workspace/.vibe)
set -euo pipefail

WARN_THRESHOLD=8192
REFUSE_THRESHOLD=1048576

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
if [[ $# -gt 1 ]]; then
  printf 'vibe-copy: usage: vibe-copy [FILE]; accepts stdin or a single file path\n' >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  if [[ ! -e "$1" || ! -r "$1" ]]; then
    printf 'vibe-copy: error: cannot read file: %s\n' "$1" >&2
    exit 2
  fi
  input_file="$1"
else
  # Slurp stdin into a temp file to preserve exact bytes (incl. trailing newlines).
  tmp_input=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f '$tmp_input'" EXIT
  cat > "$tmp_input"
  input_file="$tmp_input"
fi

# ---------------------------------------------------------------------------
# Size check — stat the file for exact byte count
# ---------------------------------------------------------------------------
byte_count=$(wc -c < "$input_file")

# ---------------------------------------------------------------------------
# Scratch file write (done on all paths that reach here — not on exit-2 paths)
# ---------------------------------------------------------------------------
scratch_dir="${VIBE_COPY_SCRATCH_DIR:-/workspace/.vibe}"
scratch_file="$scratch_dir/copy-latest.txt"

if ! mkdir -p "$scratch_dir" 2>/dev/null; then
  printf 'vibe-copy: error: cannot write scratch file at %s: %s\n' \
    "$scratch_file" "cannot create directory" >&2
  exit 1
fi

if ! cp -- "$input_file" "$scratch_file" 2>/dev/null; then
  printf 'vibe-copy: error: cannot write scratch file at %s: %s\n' \
    "$scratch_file" "write failed" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1 MiB refuse — scratch written above; do NOT emit OSC 52
# ---------------------------------------------------------------------------
if [[ $byte_count -gt $REFUSE_THRESHOLD ]]; then
  printf 'vibe-copy: error: input is %d bytes; refusing to emit OSC 52 for payloads larger than 1048576 bytes (1 MiB); scratch file written to %s\n' \
    "$byte_count" "$scratch_file" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 8 KiB warning (still emits + exits 0)
# ---------------------------------------------------------------------------
if [[ $byte_count -gt $WARN_THRESHOLD ]]; then
  printf 'vibe-copy: warning: input is %d bytes; some terminals truncate OSC 52 payloads larger than 8192 bytes\n' \
    "$byte_count" >&2
fi

# ---------------------------------------------------------------------------
# Base64 encode (RFC 4648 standard alphabet, no line breaks)
# ---------------------------------------------------------------------------
b64=$(base64 < "$input_file" | tr -d '\n')

# ---------------------------------------------------------------------------
# Emit OSC 52 sequence or note TTY absence
# ---------------------------------------------------------------------------
# Strategy:
#   1. If VIBE_COPY_TTY is set, attempt to write there.
#   2. Else if /dev/tty is writable, write there.
#   3. Otherwise emit the "no terminal available" note and exit 0.

osc52_written=0

if [[ -n "${VIBE_COPY_TTY:-}" ]]; then
  if (printf '\033]52;c;%s\007' "$b64" > "${VIBE_COPY_TTY}") 2>/dev/null; then
    osc52_written=1
  fi
elif [[ -w /dev/tty ]]; then
  printf '\033]52;c;%s\007' "$b64" > /dev/tty
  osc52_written=1
fi

if [[ $osc52_written -eq 0 ]]; then
  printf 'vibe-copy: note: no terminal available for OSC 52 write; scratch file written to %s\n' \
    "$scratch_file" >&2
fi

exit 0
