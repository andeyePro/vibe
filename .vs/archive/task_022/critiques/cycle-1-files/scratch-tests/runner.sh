#!/usr/bin/env bash
# Differential harness: old scanner vs new scanner, byte-identical finding
# sets (LC_ALL=C sort) across --blob-stdin, --message, --staged, --range,
# --messages-stdin. Exit 0 iff every mode matches.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OLD="$HERE/old-scanner.sh"
NEW="/workspace/devcontainer/git-hooks/vibe-content-scan.sh"
CORPUS="$HERE/corpus.txt"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAILED=0
report() { # <name> <oldfile> <newfile>
  local name="$1" of="$2" nf="$3"
  LC_ALL=C sort "$of" > "$of.s"; LC_ALL=C sort "$nf" > "$nf.s"
  if diff -q "$of.s" "$nf.s" >/dev/null; then
    echo "PASS  $name  ($(wc -l < "$of.s" | tr -d ' ') findings)"
  else
    echo "FAIL  $name"
    echo "----- diff (old < / new >) -----"
    diff "$of.s" "$nf.s"
    echo "--------------------------------"
    FAILED=1
  fi
}

# ---- fixture repo with an allowlist ----
FX="$WORK/fx"; mkdir -p "$FX"; ( cd "$FX" && git init -q && git config user.email a@users.noreply.github.com && git config user.name t )
printf '%s\n' '^ALLOWLISTED_192\.168\.5\.5' > "$FX/.vibe-content-allow"

# ---- 1. blob-stdin: corpus as +lines under a commit header ----
{ echo "commit deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"; sed 's/^/+/' "$CORPUS"; } > "$WORK/blob.in"
( cd "$FX" && "bash" "$OLD" --blob-stdin < "$WORK/blob.in" ) 2> "$WORK/blob.old" 1>/dev/null || true
( cd "$FX" && "bash" "$NEW" --blob-stdin < "$WORK/blob.in" ) 2> "$WORK/blob.new" 1>/dev/null || true
report "blob-stdin" "$WORK/blob.old" "$WORK/blob.new"

# ---- 1b. blob-stdin --tier block ----
( cd "$FX" && "bash" "$OLD" --blob-stdin --tier block < "$WORK/blob.in" ) 2> "$WORK/blk.old" 1>/dev/null || true
( cd "$FX" && "bash" "$NEW" --blob-stdin --tier block < "$WORK/blob.in" ) 2> "$WORK/blk.new" 1>/dev/null || true
report "blob-stdin --tier block" "$WORK/blk.old" "$WORK/blk.new"

# ---- 2. message: corpus as a message file ----
( cd "$FX" && "bash" "$OLD" --message "$CORPUS" ) 2> "$WORK/msg.old" 1>/dev/null || true
( cd "$FX" && "bash" "$NEW" --message "$CORPUS" ) 2> "$WORK/msg.new" 1>/dev/null || true
report "message" "$WORK/msg.old" "$WORK/msg.new"

# ---- 3. staged: corpus committed baseline, corpus staged as new file ----
FX2="$WORK/fx2"; mkdir -p "$FX2"; ( cd "$FX2" && git init -q && git config user.email a@users.noreply.github.com && git config user.name t )
printf '%s\n' '^ALLOWLISTED_192\.168\.5\.5' > "$FX2/.vibe-content-allow"
cp "$CORPUS" "$FX2/data.txt"
( cd "$FX2" && git add data.txt )
( cd "$FX2" && VIBE_CONTENT_GUARD=off "bash" "$OLD" --staged ) 2> "$WORK/stg.old" 1>/dev/null || true
( cd "$FX2" && VIBE_CONTENT_GUARD=off "bash" "$NEW" --staged ) 2> "$WORK/stg.new" 1>/dev/null || true
report "staged" "$WORK/stg.old" "$WORK/stg.new"

# ---- 4. range: commit1 empty, commit2 adds corpus ----
FX3="$WORK/fx3"; mkdir -p "$FX3"; ( cd "$FX3" && git init -q && git config user.email a@users.noreply.github.com && git config user.name t )
( cd "$FX3" && echo base > base.txt && git add base.txt && git commit --no-verify -qm base )
cp "$CORPUS" "$FX3/data.txt"
( cd "$FX3" && git add data.txt && git commit --no-verify -qm add )
A=$( cd "$FX3" && git rev-parse HEAD~1 ); B=$( cd "$FX3" && git rev-parse HEAD )
( cd "$FX3" && "bash" "$OLD" --range "$A" "$B" ) 2> "$WORK/rng.old" 1>/dev/null || true
( cd "$FX3" && "bash" "$NEW" --range "$A" "$B" ) 2> "$WORK/rng.new" 1>/dev/null || true
report "range" "$WORK/rng.old" "$WORK/rng.new"

# ---- 5. messages-stdin (NEW only; parity vs old per-commit --message loop) ----
# Build a fixture repo whose commit messages carry findings incl a body line
# starting with "commit ...". Old path: per-commit --message + awk relabel.
FX4="$WORK/fx4"; mkdir -p "$FX4"; ( cd "$FX4" && git init -q && git config user.email a@users.noreply.github.com && git config user.name t )
( cd "$FX4" && echo x > f1 && git add f1 && git commit --no-verify -qm "$(printf 'secret_key = "abcdefghijklmnop1234"\ncommit deadbeef body line\nline three')" )
( cd "$FX4" && echo y > f2 && git add f2 && git commit --no-verify -qm "$(printf 'ip 192.168.0.35 here\nCo-authored-by: X <x@corp.com>')" )
( cd "$FX4" && echo z > f3 && git add f3 && git commit --no-verify -qm "empty-ish body no findings" )
# OLD path emulation (mirrors vibe _audit_history pass 2 exactly):
: > "$WORK/mstd.old"
MSGF="$WORK/msgf"
while IFS= read -r sha; do
  [ -n "$sha" ] || continue
  ( cd "$FX4" && git log -1 --format=%B "$sha" ) > "$MSGF" 2>/dev/null || true
  ( cd "$FX4" && "bash" "$OLD" --message "$MSGF" ) 2>&1 1>/dev/null \
    | awk -F'\t' -v sha="$sha" 'BEGIN{OFS="\t"} NF>=4{$2="commit " sha; print}' \
    >> "$WORK/mstd.old" || true
done < <( cd "$FX4" && git log --all --format=%H )
# NEW path:
( cd "$FX4" && git log --all -z --format='%H%n%B' | "bash" "$NEW" --messages-stdin ) 2> "$WORK/mstd.new" 1>/dev/null || true
report "messages-stdin (vs old --message loop)" "$WORK/mstd.old" "$WORK/mstd.new"

echo
if [ "$FAILED" -eq 0 ]; then echo "ALL MODES BYTE-IDENTICAL"; else echo "DIFFERENTIAL FAILED"; fi
exit "$FAILED"
