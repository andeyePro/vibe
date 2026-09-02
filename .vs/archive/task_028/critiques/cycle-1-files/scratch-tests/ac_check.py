#!/usr/bin/env python3
"""Generator scratch checks for /vs task_028 — AC1-AC4, AC6-AC9, AC12-AC13.

Mechanical only. AC5 (code-check + smoke-test) and AC10/AC11 are run/judged
separately. Exit 0 = all green.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/workspace")
CM = REPO / "devcontainer" / "claude-md"
CMD = REPO / "devcontainer" / "commands"
BASE = "c68707d"

FAILS: list[str] = []
PASSES = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSES
    if ok:
        PASSES += 1
        print(f"  ok   {label}")
    else:
        FAILS.append(label)
        print(f"  FAIL {label}" + (f"  [{detail}]" if detail else ""))


def words(p: Path) -> int:
    return len(p.read_text().split())


DELETED = ["learn-hook.md", "feedback-auto-promote.md", "conversation-history.md"]

# ---------------------------------------------------------------- AC1
print("\n[AC1] fragment inventory")
frags = sorted(q.name for q in CM.glob("*.md"))
check("exactly 13 .md fragments", len(frags) == 13, f"{len(frags)}: {frags}")
for d in DELETED:
    check(f"{d} deleted", not (CM / d).exists())
for k in ("learnings.md", "auto-memory-scope.md", "content-guard.md"):
    check(f"{k} exists", (CM / k).exists())
base_frags = set(
    subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", BASE,
                    "devcontainer/claude-md/"], capture_output=True, text=True,
                   check=True).stdout.split()
)
base_names = {Path(x).name for x in base_frags}
check("no fragment added/renamed", set(frags) <= base_names,
      str(set(frags) - base_names))

# ---------------------------------------------------------------- AC2
print("\n[AC2] fragment word budget")
total = sum(words(p) for p in sorted(CM.glob("*.md")))
check(f"cat *.md | wc -w <= 6160 (got {total})", total <= 6160)

# ---------------------------------------------------------------- AC3
print("\n[AC3] content-guard.md size + pointer")
cg = CM / "content-guard.md"
if cg.exists():
    w = words(cg)
    check(f"400 <= wc -w <= 600 (got {w})", 400 <= w <= 600)
    body = cg.read_text()
    check("contains 'README.md'", "README.md" in body)
    check("contains 'Content guard'", "Content guard" in body)
else:
    check("content-guard.md exists", False)

# ---------------------------------------------------------------- AC4
print("\n[AC4] sentinel strings")
SENTINELS = {
    "learnings.md": [
        "/learnings", "vibe learn --init", ".no-learn", "grep -r", 'vibe learn "',
        "/learn", "permissionDecision", "ask", "realpath -m", "guard-fs.sh",
        "guard-bash.sh", "bypass the hook", "VIBE_AUTO_PROMOTE",
        "Y / n / never-ask", "YES:", "NO:", "cross-repo", "One prompt per",
        "vibe learn --push", "VIBE_LEARNING_PATH",
    ],
    "auto-memory-scope.md": [
        "task_014", "~/.vibe/projects/", "/home/node/.claude/projects/",
        "--continue", "/learnings", "*.jsonl", "-workspace", "jq -r",
        'type=="user"', 'type=="assistant"', "tool_result", "thinking",
        "tool_use", "ls -t", "vibe-claude-config", "Do not duplicate",
    ],
    "content-guard.md": [
        "BLOCK", "WARN", "commit-identity", "users.noreply.github.com",
        "VIBE_CONTENT_GUARD=off", "VIBE_ALLOW_COMMIT=1", "--no-verify",
        ".vibe-content-guard-off", ".vibe-content-allow", "path-warn:",
        "vibe audit", "--history", "--staged", "Co-Authored-By", "pre-push",
    ],
}
for name, sents in SENTINELS.items():
    p = CM / name
    body = p.read_text() if p.exists() else ""
    missing = [s for s in sents if s not in body]
    check(f"{name}: all {len(sents)} sentinels present", not missing, str(missing))

# ---------------------------------------------------------------- AC12
print("\n[AC12] per-file floors")
for name, floor in (("learnings.md", 650), ("auto-memory-scope.md", 450)):
    p = CM / name
    w = words(p) if p.exists() else 0
    check(f"{name} >= {floor} words (got {w})", w >= floor)

# ---------------------------------------------------------------- AC13
print("\n[AC13] ten untouched fragments byte-identical")
UNTOUCHED = ["web-research", "ssh-discipline", "brain2", "shared-repos",
             "harness-routing", "output-consolidation", "project-hygiene",
             "todo-changelog", "vibe-cli", "workspace-is-the-repo"]
for name in UNTOUCHED:
    rel = f"devcontainer/claude-md/{name}.md"
    old = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE}:{rel}"],
                         capture_output=True, check=True).stdout
    new = (REPO / rel).read_bytes()
    check(f"{name}.md byte-identical to {BASE}", old == new)
    txt = new.decode()
    check(f"{name}.md has no deleted-fragment reference",
          not any(d in txt for d in DELETED))

# ---------------------------------------------------------------- AC7
print("\n[AC7] Fable grant defined once")
vs = (CMD / "vs.md").read_text()
vss = (CMD / "vss.md").read_text()
vsss = (CMD / "vsss.md").read_text()

# locate § Model economy body (up to next '## ' heading)
m = re.search(r"^## Model economy\s*$(.*?)(?=^## )", vs, re.M | re.S)
check("vs.md has a § Model economy section", m is not None)
econ = m.group(1) if m else ""
sub = re.search(r"^#{3,}[^\n]*Fable grant[^\n]*$(.*?)(?=^#{2,3} |\Z)", econ, re.M | re.S)
check("§ Model economy has a 'Fable grant' subsection", sub is not None)
subbody = sub.group(0) if sub else ""
for s in ["--fable-subagents", "--fable", "permits", "never forces",
          "mechanical roles", "vibe --fable", "chair"]:
    check(f"Fable grant subsection contains {s!r}", s in subbody)

for fname, txt in (("vss.md", vss), ("vsss.md", vsss)):
    n = txt.count("--fable-subagents")
    check(f"{fname}: --fable-subagents occurs <= 3 (got {n})", n <= 3)
    bad = [ln for ln in txt.splitlines()
           if "--fable-subagents" in ln and "/vs § Model economy" not in ln]
    check(f"{fname}: every --fable-subagents line points at /vs § Model economy",
          not bad, str(bad)[:200])
    for s in ["never forces", "mechanical roles", "sets only the chair",
              "chair model only", "authorises no subagent spend"]:
        check(f"{fname}: {s!r} occurs zero times", s not in txt)

flagline = [ln for ln in vs.splitlines()
            if ln.lstrip().startswith("- `/vs --fable-subagents")]
check("vs.md § Flags has a --fable-subagents bullet", len(flagline) == 1,
      str(flagline)[:200])
if len(flagline) == 1:
    fl = flagline[0]
    check(f"§ Flags bullet <= 40 words (got {len(fl.split())})", len(fl.split()) <= 40)
    check("§ Flags bullet contains '§ Model economy'", "§ Model economy" in fl)

# vsss persistence clause must survive
check("vsss.md keeps the auto-resume persistence clause",
      "PERSISTS across auto-resume relaunches" in vsss)

# ---------------------------------------------------------------- AC8
print("\n[AC8] vs+vss+vsss word budget")
cmd_total = sum(len((CMD / f).read_text().split())
                for f in ("vs.md", "vss.md", "vsss.md"))
check(f"combined wc -w <= 12700 (got {cmd_total})", cmd_total <= 12700)

# ---------------------------------------------------------------- AC9
print("\n[AC9] doc references")
line13 = (REPO / "CLAUDE.md").read_text().splitlines()[12]
check("CLAUDE.md line 13 fragment list drops 'learn-hook'", "learn-hook" not in line13,
      line13[:160])
for doc in ("README.md", "ONBOARDING.md", "CONTRIBUTING.md", "CLAUDE.md",
            "MANUAL-TESTS.md"):
    txt = (REPO / doc).read_text()
    hits = [d for d in DELETED if d in txt]
    check(f"{doc}: no deleted-fragment filename", not hits, str(hits))
dev_hits = subprocess.run(
    ["grep", "-rln", "-e", "learn-hook.md", "-e", "feedback-auto-promote.md",
     "-e", "conversation-history.md", str(REPO / "devcontainer")],
    capture_output=True, text=True).stdout.split()
check("devcontainer/: no deleted-fragment filename", not dev_hits, str(dev_hits))
st = (REPO / "smoke-test.py").read_text()
const_hits = [ln for ln in st.splitlines()
              if re.match(r"^\s*[A-Z_]+\s*=", ln) and any(d in ln for d in DELETED)]
check("smoke-test.py: no constant points at a deleted file", not const_hits,
      str(const_hits))

# ---------------------------------------------------------------- AC6
print("\n[AC6] sandboxed installer run")
with tempfile.TemporaryDirectory() as tmp:
    T = Path(tmp)
    env = os.environ.copy()
    env["HOME"] = str(T)
    env["CLAUDE_CONFIG_DIR"] = str(T / ".claude")
    env["GIT_CONFIG_GLOBAL"] = str(T / ".gitconfig")
    env["VIBE_AUTO_GITIGNORE"] = "0"
    env["VIBE_EXTRAS_SRC_ROOT"] = str(REPO / "devcontainer")
    env.pop("VIBE_SSH_AUTO", None)
    r = subprocess.run(["bash", str(REPO / "devcontainer" / "install-claude-extras.sh")],
                       env=env, capture_output=True, text=True)
    check(f"installer exits 0 (rc={r.returncode})", r.returncode == 0,
          r.stderr[-300:])
    md = T / ".claude" / "CLAUDE.md"
    check("T/.claude/CLAUDE.md written", md.exists())
    if md.exists():
        body = md.read_text()
        blk = re.search(r"vibe-managed.*?vibe-managed", body, re.S)
        inner = blk.group(0) if blk else body
        for name in ("learnings.md", "auto-memory-scope.md", "content-guard.md"):
            check(f"marker <!-- vibe-md: {name} --> inside managed block",
                  f"<!-- vibe-md: {name} -->" in inner)
        for d in DELETED:
            check(f"installed CLAUDE.md free of {d!r}", d not in body)

print(f"\n=== {PASSES} passed, {len(FAILS)} failed ===")
for f in FAILS:
    print(f"  FAILED: {f}")
sys.exit(1 if FAILS else 0)
