#!/usr/bin/env bash
# Scratch TDD harness for task_019 (regrettable-content guard). NOT part of
# the shipped repo — gitignored under .vs/cycle-*/. Exercises every
# mechanical AC from .vs/spec.md against the real scanner/wrappers/install
# script/launcher, using runtime-constructed fixture secrets per the spec's
# Dogfooding rule (no literal secret pattern is ever written to disk here
# as a contiguous string in this FILE's own source — each is built at
# runtime by string concatenation).
# Deliberately NOT `set -e`: nearly every check below expects a non-zero
# exit code from the tool under test and captures it via $? immediately
# after — -e would abort the whole harness on the first expected failure.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SCANNER="$REPO/devcontainer/git-hooks/vibe-content-scan.sh"
VIBE="$REPO/vibe"

PASS=0
FAIL=0

check() {
  local desc="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then
    PASS=$((PASS + 1))
    printf 'ok   %s\n' "$desc"
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL %s (got=%q want=%q)\n' "$desc" "$got" "$want"
  fi
}

check_contains() {
  local desc="$1" haystack="$2" needle="$3"
  case "$haystack" in
    *"$needle"*) PASS=$((PASS + 1)); printf 'ok   %s\n' "$desc" ;;
    *) FAIL=$((FAIL + 1)); printf 'FAIL %s (missing %q)\nGOT:\n%s\n' "$desc" "$needle" "$haystack" ;;
  esac
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

fresh_repo() {
  local name="$1"
  rm -rf "$WORK/$name"
  mkdir -p "$WORK/$name"
  (cd "$WORK/$name" && git init -q && git config user.email t@example.com && git config user.name T)
  echo "$WORK/$name"
}

GHP_TOKEN="ghp_$(printf 'A%.0s' $(seq 1 36))"
PRIVKEY_MARKER="-----BEGIN $(printf OPENSSH) PRIVATE KEY-----"

# AC1 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac1)
cd "$r"
printf 'const t = "%s";\n' "$GHP_TOKEN" > s.js
git add s.js
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC1 exit 1" "$ec" "1"
check_contains "AC1 BLOCK github-pat present" "$out" "$(printf 'BLOCK\t')"
check_contains "AC1 rule id github-pat" "$out" "github-pat"

# AC2 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac2)
cd "$r"
printf 'Add key\n\n%s\nx\n' "$PRIVKEY_MARKER" > /tmp/task019_msg.txt
out=$("$SCANNER" --message /tmp/task019_msg.txt 2>&1 1>/dev/null) ; ec=$?
check "AC2 exit 1" "$ec" "1"
check_contains "AC2 BLOCK private-key" "$out" "private-key"
rm -f /tmp/task019_msg.txt

# AC3 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac3)
cd "$r"
echo "server at 192.0.2.35" > n.md
git add n.md
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC3 exit 1" "$ec" "1"
check_contains "AC3 WARN rfc1918-ip" "$out" "$(printf 'WARN\t')n.md:1	rfc1918-ip"

# AC4 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac4)
cd "$r"
echo "function add(a,b){return a+b;}" > c.js
git add c.js
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC4 exit 0" "$ec" "0"
check "AC4 no output" "$out" ""

# AC5 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac5)
cd "$r"
printf 'const t = "%s";\n' "$GHP_TOKEN" > s.js
git add s.js
out=$(VIBE_CONTENT_GUARD=off "$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC5 exit 0 under override" "$ec" "0"
check_contains "AC5 loud override line" "$out" "OVERRIDE"
check_contains "AC5 names skipped rule" "$out" "github-pat"

# AC6 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac6)
cd "$r"
echo "server at 192.0.2.35" > n.md
git add n.md
printf '192\\.168\\.0\\.35\n' > .vibe-content-allow
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC6 exit 0 with matching allow entry" "$ec" "0"
rm .vibe-content-allow
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC6 exit 1 without allow entry" "$ec" "1"

# AC7 ────────────────────────────────────────────────────────────────────────
r=$(fresh_repo ac7)
cd "$r"
printf 'const t = "%s";\n' "$GHP_TOKEN" > s.js
git add s.js
touch .vibe-content-guard-off
out=$("$SCANNER" --staged 2>&1 1>/dev/null) ; ec=$?
check "AC7 exit 0 with guard-off marker" "$ec" "0"

# AC8 ────────────────────────────────────────────────────────────────────────
iso="$WORK/iso_home"
mkdir -p "$iso"
out=$(HOME="$iso" CLAUDE_CONFIG_DIR="$iso/.claude" GIT_CONFIG_GLOBAL="$iso/.gitconfig" \
  VIBE_EXTRAS_SRC_ROOT="$REPO/devcontainer" VIBE_PLUGINS=0 \
  bash "$REPO/devcontainer/install-claude-extras.sh" 2>&1) ; ec=$?
check "AC8 install script exit 0" "$ec" "0"
for f in vibe-content-scan.sh pre-commit commit-msg pre-push; do
  if [ -x "$iso/.claude/vibe-git-hooks/$f" ]; then
    PASS=$((PASS + 1)); printf 'ok   AC8 %s installed executable\n' "$f"
  else
    FAIL=$((FAIL + 1)); printf 'FAIL AC8 %s NOT installed executable\n' "$f"
  fi
done
hookspath=$(GIT_CONFIG_GLOBAL="$iso/.gitconfig" git config --global core.hooksPath)
check "AC8 core.hooksPath set" "$hookspath" "$iso/.claude/vibe-git-hooks"

# AC9 + AC16 (vibe audit --history) ────────────────────────────────────────────
r=$(fresh_repo ac9)
cd "$r"
printf 'const t = "%s";\n' "$GHP_TOKEN" > s.js
git add s.js
git commit -q -m "add secret then delete it"
git rm -q s.js
git commit -q -m "remove secret"
out=$(bash "$VIBE" audit --history 2>&1) ; ec=$?
check "AC9 exit 1 (secret in deleted history)" "$ec" "1"
check_contains "AC9 BLOCK names a commit sha location" "$out" "$(printf 'BLOCK\tcommit ')"

r=$(fresh_repo ac9clean)
cd "$r"
echo hi > f.txt
git add f.txt
git commit -q -m clean
out=$(bash "$VIBE" audit --history 2>&1) ; ec=$?
check "AC9 clean-history repo exits 0" "$ec" "0"

r=$(fresh_repo ac16)
cd "$r"
echo "server at 192.0.2.35" > n.md
git add n.md
git commit -q -m "add ip then delete it"
git rm -q n.md
git commit -q -m "remove ip"
out=$(bash "$VIBE" audit --history 2>&1) ; ec=$?
check "AC16 WARN-only history exits 0" "$ec" "0"
check_contains "AC16 WARN reported with commit sha" "$out" "$(printf 'WARN\tcommit ')"

# AC10 + AC17 (end-to-end via real installed hooks) ────────────────────────────
git config --global --unset-all user.email >/dev/null 2>&1 || true
export HOME="$iso" CLAUDE_CONFIG_DIR="$iso/.claude" GIT_CONFIG_GLOBAL="$iso/.gitconfig"
git config --global user.email t@example.com
git config --global user.name T
rm -rf "$WORK/bare.git" "$WORK/work"
git init -q --bare "$WORK/bare.git"
git init -q "$WORK/work"
cd "$WORK/work"
git remote add origin "$WORK/bare.git"
echo hi > README.md
git add README.md
git commit -q -m init
git push -q origin HEAD:refs/heads/main

echo "console.log(1)" > ok.js
git add ok.js
git commit -q -m "clean commit"
check "AC10 clean commit succeeds via real pre-commit" "$?" "0"

printf 'const t = "%s";\n' "$GHP_TOKEN" > bad.js
git add bad.js
git commit -q -m "bad commit" 2>/tmp/task019_commit.err
ec=$?
check "AC10 BLOCK commit refused via real pre-commit" "$ec" "1"
rm -f /tmp/task019_commit.err

VIBE_CONTENT_GUARD=off git commit -q -m "bad commit (override)"
git checkout -q -b feature/x
git push -q origin HEAD:refs/heads/feature/x 2>/tmp/task019_push.err
ec=$?
check "AC10 new-branch push with secret refused via real pre-push" "$ec" "1"
rm -f /tmp/task019_push.err

# AC17: WARN-only push succeeds with no override at push time.
git checkout -q main
echo "note: 192.0.2.77" > w.md
git add w.md
VIBE_CONTENT_GUARD=off git commit -q -m "warn note (override at commit time only)"
git checkout -q -b feature/warn
git push -q origin HEAD:refs/heads/feature/warn
ec=$?
check "AC17 WARN-only new-branch push succeeds with no override at push time" "$ec" "0"

unset HOME CLAUDE_CONFIG_DIR GIT_CONFIG_GLOBAL

# AC11 ───────────────────────────────────────────────────────────────────────
printf 'Fix bug\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n' > /tmp/task019_msg2.txt
out=$("$SCANNER" --message /tmp/task019_msg2.txt 2>&1 1>/dev/null) ; ec=$?
check "AC11 trailer message scans clean" "$ec" "0"
check "AC11 no output" "$out" ""
rm -f /tmp/task019_msg2.txt

# AC12 (guard-bash.sh unchanged) ────────────────────────────────────────────
gbout=$(printf '%s' '{"tool_input":{"command":"git push --force origin main"}}' | "$REPO/devcontainer/guard-bash.sh" 2>&1) ; gbec=$?
check "AC12 guard-bash.sh force-push still blocks (exit 2)" "$gbec" "2"

echo ""
echo "==== $PASS passed, $FAIL failed ===="
[ "$FAIL" -eq 0 ]
