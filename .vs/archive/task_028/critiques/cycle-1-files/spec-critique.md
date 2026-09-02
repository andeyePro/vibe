# Spec Critique — task_028 (cycle 1)

## Concerns

1. **AC4, BLOCKING.** Sentinel `Do not bypass` does not exist verbatim (case-sensitive) anywhere today — `learn-hook.md:35` has `## do not bypass the hook` (lowercase). Satisfying it requires Generator to recapitalize the heading during merge — a cosmetic fix, not a rule change, but the spec should say so explicitly so it isn't disputed as "reinterpreting a rule" (banned out-of-scope).

2. **AC6, BLOCKING.** `_isolate_extras_env` sets only `HOME`, `GIT_CONFIG_GLOBAL`, `VIBE_AUTO_GITIGNORE` — never `CLAUDE_CONFIG_DIR`. `DEST_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"` prefers `CLAUDE_CONFIG_DIR` when set, and it IS set ambiently in this container (`/home/node/.claude`). Every existing installer test compensates by also setting `env["CLAUDE_CONFIG_DIR"]` to a fresh tmp dir alongside `HOME` — AC6's recipe omits this. Followed literally, the run writes into the REAL `~/.claude/CLAUDE.md` (live-session pollution) while the check against `$HOME/.claude/CLAUDE.md` reads a file never written, and false-fails. AC6 must add: also set/pop `CLAUDE_CONFIG_DIR` to the same fresh temp dir.

3. **AC6, informational (not a flaw).** The marker form is `<!-- vibe-md: <basename> -->` per fragment (e.g. `<!-- vibe-md: learnings.md -->`), inside an outer `<!-- >>> vibe-managed ... >>> / <!-- <<< vibe-managed <<< -->` block. Tester should assert those literal per-fragment strings present for the three survivors and absent for the three deleted files.

4. **AC7, MINOR.** vs.md's current `--fable-subagents` Flags bullet is 130 words; the AC caps it at ≤40. Tight but doable — flag so Generator doesn't drop the "never Fable for mechanical roles / scoped small generations" caveat while compressing (must survive somewhere per AC11).

5. **AC7, MINOR.** vss.md already has 4 occurrences of `--fable-subagents` pre-merge; the post-merge ceiling is 3 — Generator must actively delete one, not just add pointer text.

6. **AC7, feasible, MINOR.** vsss.md's grant paragraph (the resumption-persistence rule the brief worried about) contains none of the five banned phrases, and since it's one long physical line, the required `/vs § Model economy` string only needs to appear once anywhere on that line to satisfy both its `--fable-subagents` occurrences — so it can survive verbatim within budget. Worth a named AC11 check since it's the clause most likely to get compressed away by accident.

7. **AC2/AC3, MINOR (budget realism).** Arithmetic checks out (8060−1900=6160=AC2; content-guard.md savings of 546–746 leaves ~1,150–1,350 of the required 1,900 from collapsing the other three files, 1,771 words). But AC4's sentinels show nearly all of feedback-auto-promote.md's/conversation-history.md's substantive content must survive wholesale — real savings can only come from cutting genuinely restated connective prose. Achievable but tighter than "≥1,900 words" implies; risk of cycle-2 shortfall if content-guard.md lands at 600 rather than nearer 400.

8. **AC10, MINOR/wording.** "the commit after `vs: archive task_027`" is ambiguous — `c68707d` (that archive commit) IS current HEAD, no child exists. Resolve as: baseline = HEAD at task start.

9. **AC11, MINOR — add a sentinel.** AC4's substring checks don't prove explanatory prose around them survives — a lazy merge could keep bare mentions of `guard-fs.sh`/`realpath -m` while gutting the "why". Propose a per-file word-count floor (`learnings.md` ≥700w, `auto-memory-scope.md` ≥500w) alongside AC2's aggregate ceiling.

10. **Out-of-scope, MINOR loophole.** AC10's scope lock checks changed files only, not whether an untouched fragment references the three deleted filenames. Recommend Tester grep the 10 untouched fragments for those filenames too (AC9 covers docs, not sibling fragments).

## Verdict

**revise** — concern 2 (AC6 CLAUDE_CONFIG_DIR gap) is a genuine BLOCKING correctness bug in the test recipe that risks corrupting the live session's real CLAUDE.md; concern 1 (AC4 case-sensitivity) is a cheap fix but must be acknowledged before Tester writes an unwinnable assertion.
