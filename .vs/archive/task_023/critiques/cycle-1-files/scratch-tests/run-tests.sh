#!/usr/bin/env bash
# task_023 scratch test driver — red/green TDD harness for path-warn:<glob>.
# NOT committed (scratch-tests is gitignored via .vs/cycle-*/). Ad hoc, not
# a smoke-test.py replacement — permanent tests land in smoke-test.py
# (Tester's job per spec, append-only, Generator never touches it).
#
# Uses `git -C "$FX"` throughout (never a bare `cd`) so the driver's own
# cwd never moves — avoids the deleted-cwd-inode class of bug entirely.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCANNER="/workspace/devcontainer/git-hooks/vibe-content-scan.sh"
OLD_SCANNER="$HERE/old-scanner.sh"
FX="$HERE/fixture-repo"

PASS=0
FAIL=0

ok() { echo "  OK  $1"; PASS=$((PASS+1)); }
bad() { echo "FAIL  $1"; FAIL=$((FAIL+1)); }

reset_fixture() {
  rm -rf "$FX"
  mkdir -p "$FX/fixtures" "$FX/.vs/archive/task_099/critiques"
  git -C "$FX" init -q
  git -C "$FX" config user.email "placeholder@vibe.local"
  git -C "$FX" config user.name "fixture"
  echo "seed" > "$FX/README.md"
  git -C "$FX" add README.md
  git -C "$FX" commit -q -m seed
}

write_allow() {
  # write_allow <content...> — replaces fixture-repo/.vibe-content-allow
  printf '%s\n' "$@" > "$FX/.vibe-content-allow"
}

run_scanner() {
  # run_scanner <scanner-path> <mode-args...> — invoked with cwd=$FX via a
  # subshell (does not affect the driver's own cwd).
  local bin="$1"; shift
  ( cd "$FX" && "$bin" "$@" 2>&1; echo "EXIT:$?" )
}

# ── AC1: parser differential (allowlist WITHOUT path-warn entries) ─────────
echo "== AC1: differential, no path-warn entries =="
reset_fixture
write_allow "# plain allowlist, no path-warn" "test@example\\.com"
cat > "$FX/fixtures/plain.txt" <<'EOF'
contact me at 192.168.1.50 or someone@example.org
home path /Users/martin/stuff
mdns box.local reachable
EOF
git -C "$FX" add fixtures/plain.txt
old_out=$(run_scanner "$OLD_SCANNER" --staged)
new_out=$(run_scanner "$SCANNER" --staged)
if [ "$(printf '%s' "$old_out" | LC_ALL=C sort)" = "$(printf '%s' "$new_out" | LC_ALL=C sort)" ]; then
  ok "AC1 byte-identical (no path-warn entries) sorted match"
else
  bad "AC1 differential mismatch"
  echo "--- old ---"; echo "$old_out"
  echo "--- new ---"; echo "$new_out"
fi

# ── AC2: --staged suppression + nested path + empty glob ───────────────────
echo "== AC2: staged suppression =="
reset_fixture
write_allow "path-warn:fixtures/*" "path-warn:.vs/*" "path-warn:"
cat > "$FX/fixtures/warn.txt" <<'EOF'
box at 192.168.1.77 for testing
EOF
git -C "$FX" add fixtures/warn.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:0$" && ! printf '%s' "$out" | grep -q "WARN"; then
  ok "AC2 path-warn glob suppresses WARN in matching file, exit 0"
else
  bad "AC2 matching-file suppression (out=$out)"
fi

reset_fixture
write_allow "path-warn:fixtures/*"
cat > "$FX/other.txt" <<'EOF'
box at 192.168.1.77 for testing
EOF
git -C "$FX" add other.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "rfc1918-ip"; then
  ok "AC2 non-matching file still WARNs, exit 1"
else
  bad "AC2 non-matching-file control (out=$out)"
fi

# nested path 3 levels deep
reset_fixture
write_allow "path-warn:.vs/*"
cat > "$FX/.vs/archive/task_099/critiques/foo.md" <<'EOF'
example ip 10.1.2.3 in critique notes
EOF
git -C "$FX" add ".vs/archive/task_099/critiques/foo.md"
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:0$" && ! printf '%s' "$out" | grep -q "WARN"; then
  ok "AC2 nested-path glob (.vs/* matches 3-levels-deep) suppresses"
else
  bad "AC2 nested-path glob (out=$out)"
fi

# empty glob line: no crash, no match-all
reset_fixture
write_allow "path-warn:"
cat > "$FX/anything.txt" <<'EOF'
box at 192.168.1.77 for testing
EOF
git -C "$FX" add anything.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "rfc1918-ip"; then
  ok "AC2 empty path-warn glob matches nothing (no crash, no match-all)"
else
  bad "AC2 empty-glob (out=$out)"
fi

# ── AC3: BLOCK still fires under path-warn (--staged and --range) ──────────
echo "== AC3: BLOCK never suppressed by path-warn =="
TOKEN="ghp_$(printf 'A%.0s' $(seq 1 36))"

reset_fixture
write_allow "path-warn:fixtures/*"
printf 'token %s\n' "$TOKEN" > "$FX/fixtures/secret.txt"
git -C "$FX" add fixtures/secret.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "github-pat"; then
  ok "AC3 --staged BLOCK fires in path-warn-matched file"
else
  bad "AC3 --staged BLOCK (out=$out)"
fi

reset_fixture
write_allow "path-warn:fixtures/*"
printf 'seed2\n' >> "$FX/README.md"
git -C "$FX" add README.md
git -C "$FX" commit -q -m seed2
printf 'token %s\n' "$TOKEN" > "$FX/fixtures/secret.txt"
git -C "$FX" add fixtures/secret.txt
git -C "$FX" commit -q -m secret
A=$(git -C "$FX" rev-parse HEAD~1); B=$(git -C "$FX" rev-parse HEAD)
out=$(run_scanner "$SCANNER" --range "$A" "$B")
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "github-pat"; then
  ok "AC3 --range BLOCK fires in path-warn-matched file"
else
  bad "AC3 --range BLOCK (out=$out)"
fi

# ── AC3b: no ERE double-parse ────────────────────────────────────────────
echo "== AC3b: path-warn lines never reach the ERE loop =="
reset_fixture
write_allow "path-warn:smoke-test.py"
printf 'see smoke-test.py for token %s\n' "$TOKEN" > "$FX/other2.txt"
git -C "$FX" add other2.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "github-pat"; then
  ok "AC3b literal 'smoke-test.py' in content doesn't suppress BLOCK"
else
  bad "AC3b literal filename mention (out=$out)"
fi

reset_fixture
write_allow "path-warn:smoke-test.py"
printf 'allowlist entry path-warn:smoke-test.py near token %s\n' "$TOKEN" > "$FX/other3.txt"
git -C "$FX" add other3.txt
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "github-pat"; then
  ok "AC3b literal 'path-warn:smoke-test.py' text doesn't suppress BLOCK"
else
  bad "AC3b literal path-warn: prefix text mention (out=$out)"
fi

# ── AC3c: --range idempotency (tier demotion is a one-way floor) ───────────
echo "== AC3c: --range idempotency with/without path-warn entries =="
reset_fixture
write_allow "# no path-warn"
printf 'seed2\n' >> "$FX/README.md"; git -C "$FX" add README.md; git -C "$FX" commit -q -m seed2
cat > "$FX/fixtures/dirty.txt" <<EOF
ip 192.168.1.9 email x@example.org token $TOKEN
EOF
git -C "$FX" add fixtures/dirty.txt; git -C "$FX" commit -q -m dirty
A=$(git -C "$FX" rev-parse HEAD~1); B=$(git -C "$FX" rev-parse HEAD)
out_without=$(run_scanner "$SCANNER" --range "$A" "$B")
write_allow "path-warn:fixtures/*"
out_with=$(run_scanner "$SCANNER" --range "$A" "$B")
if [ "$out_without" = "$out_with" ]; then
  ok "AC3c --range byte-identical with/without path-warn entries"
else
  bad "AC3c --range mismatch"
  echo "--- without ---"; echo "$out_without"
  echo "--- with ---"; echo "$out_with"
fi

# ── AC4: non-diff modes unaffected (byte-identical to old scanner) ────────
echo "== AC4: non-diff modes byte-identical with path-warn entries present =="
reset_fixture
write_allow "path-warn:*" "path-warn:fixtures/*"

# --message
msgfile="$FX/msg.txt"
printf 'contact 192.168.1.5 someone@example.org see fixtures/x for detail\n' > "$msgfile"
old_out=$("$OLD_SCANNER" --message "$msgfile" 2>&1; echo "EXIT:$?")
new_out=$("$SCANNER" --message "$msgfile" 2>&1; echo "EXIT:$?")
[ "$old_out" = "$new_out" ] && ok "AC4 --message byte-identical" || { bad "AC4 --message mismatch"; echo "$old_out"; echo "---"; echo "$new_out"; }

# --blob-stdin
blob_in=$'commit deadbeef\n+contact 192.168.1.5 someone@example.org\n'
old_out=$(printf '%s' "$blob_in" | "$OLD_SCANNER" --blob-stdin 2>&1; echo "EXIT:$?")
new_out=$(printf '%s' "$blob_in" | "$SCANNER" --blob-stdin 2>&1; echo "EXIT:$?")
[ "$old_out" = "$new_out" ] && ok "AC4 --blob-stdin byte-identical" || { bad "AC4 --blob-stdin mismatch"; echo "$old_out"; echo "---"; echo "$new_out"; }

# --messages-stdin (NUL-delimited: sha\nbody)
msgs_in=$(printf 'deadbeef\ncontact 192.168.1.5 someone@example.org\0')
old_out=$(printf '%s' "$msgs_in" | "$OLD_SCANNER" --messages-stdin 2>&1; echo "EXIT:$?")
new_out=$(printf '%s' "$msgs_in" | "$SCANNER" --messages-stdin 2>&1; echo "EXIT:$?")
[ "$old_out" = "$new_out" ] && ok "AC4 --messages-stdin byte-identical" || { bad "AC4 --messages-stdin mismatch"; echo "$old_out"; echo "---"; echo "$new_out"; }

# --identity
old_out=$(git -C "$FX" log -0 >/dev/null 2>&1; "$OLD_SCANNER" --identity "someone@example.org" 2>&1; echo "EXIT:$?")
new_out=$("$SCANNER" --identity "someone@example.org" 2>&1; echo "EXIT:$?")
[ "$old_out" = "$new_out" ] && ok "AC4 --identity byte-identical" || { bad "AC4 --identity mismatch"; echo "$old_out"; echo "---"; echo "$new_out"; }

# ── AC5: self-clean end-to-end (fixture simulation of vibe tree shape) ─────
echo "== AC5: self-clean end-to-end =="
reset_fixture
write_allow "path-warn:.vs/*" "path-warn:smoke-test.py"
cat > "$FX/.vs/spec.md" <<'EOF'
example WARN literal: 192.168.0.96 and mcomz.local and /Users/martin/foo
EOF
cat > "$FX/smoke-test.py" <<'EOF'
FIXTURE_IP = "192.168.1.44"  # example literal for test assertions
EOF
git -C "$FX" add .vs/spec.md smoke-test.py
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:0$" && ! printf '%s' "$out" | grep -q "WARN"; then
  ok "AC5 shipped entries: WARN literals in .vs/ and smoke-test.py clean, no override"
else
  bad "AC5 self-clean WARN (out=$out)"
fi

reset_fixture
write_allow "path-warn:.vs/*" "path-warn:smoke-test.py"
printf 'planted secret %s\n' "$TOKEN" > "$FX/.vs/spec.md"
printf 'planted secret %s\n' "$TOKEN" > "$FX/smoke-test.py"
git -C "$FX" add .vs/spec.md smoke-test.py
out=$(run_scanner "$SCANNER" --staged)
if printf '%s' "$out" | grep -q "^EXIT:1$" && printf '%s' "$out" | grep -q "github-pat"; then
  ok "AC5 planted PAT in shipped-entry files still exit 1"
else
  bad "AC5 self-clean BLOCK (out=$out)"
fi

echo
echo "=================================================="
echo "PASS=$PASS FAIL=$FAIL"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
