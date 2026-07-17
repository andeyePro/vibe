# Spec Critique — task_024 (hunk-aware diff parsing)

All claims below were checked with real `git` (2.39.5) in a scratch repo, not read off the spec. Repro commands are given so the Generator/Tester can rerun them.

## Concerns

### 1. BLOCKING — a genuinely empty context line (not merely "starts with a space") breaks the counting invariant and re-creates the exact file-misattribution bug this task exists to close (AC1, AC5, AC7, design bullet on context lines)

The design says: "a line starting with a space (context) decrements BOTH." I confirmed with `cat -A` that in the *default* case a context blank line does render as a single leading space (`" $"`). But git also has a documented, live config knob, `diff.suppressBlankEmpty`, that when true renders a context blank line as a **zero-byte line** (`"$"`, no space at all):

```
git -c diff.suppressBlankEmpty=true diff -U3 --no-color -- fileA.txt fileB.txt
```

That output line matches none of the spec's four prefix classes (`+`, `-`, ` `, `\`). Under any straightforward bash-`case`-style implementation (the pattern the rest of the file already uses), an unmatched line falls to the catch-all and is silently ignored — counters are **not** decremented. That under-consumes the hunk's declared budget by one unit, so `old_remaining+new_remaining` stays `>0` after what should have been the hunk's last line.

I built and ran the full exploit chain, not just the theory. Two-file diff, file A's hunk ends on a blank context line, file B carries a `ghp_…` secret:

```
printf 'A\nB\nC\n\nD\nE\n' > fileA.txt; printf 'secretfile\n' > fileB.txt
git add fileA.txt fileB.txt && git commit -qm setup
printf 'A\nB\nCHANGED\n\nD\nE\n' > fileA.txt
printf 'secretfile\nghp_1234567890123456789012345678901234\n' > fileB.txt
git -c diff.suppressBlankEmpty=true diff -U3 --no-color -- fileA.txt fileB.txt
```

Tracing a spec-faithful state machine through the output: the blank line leaks 1 unit of budget on each side, so when the stream reaches fileB's real `--- a/fileB.txt` / `+++ b/fileB.txt` headers, the parser is still (falsely) "inside" fileA's hunk. Both lines start with `-`/`+` respectively, so per the spec's own rule ("a line starting `-` decrements old_remaining… a line starting `+` decrements new_remaining AND is scanned as content") they get swallowed as fake hunk content instead of being classified as headers — `current_file` is **never updated to fileB.txt**. The secret is still found (good — doesn't fail open on the finding itself) but is reported against `fileA.txt` with a stale line number. That is precisely the "wrong file path" failure mode AC1 is written to rule out, just triggered by a different mechanism (blank-context suppression, not added-line shape spoofing).

Scope: this only reaches `scan_blob_stdin` (`--blob-stdin`, i.e. `vibe audit --history`, which runs `git log -p --all` at default U3 context — confirmed via `grep -n "log -p" vibe`). It does **not** reach `scan_diff_stream` (`--staged`/`--range`), because both call sites use `-U0`, which never emits context lines at all — confirmed no config in this container currently sets `diff.suppressBlankEmpty`, so it's latent here, but it's a real, live, user-configurable git behavior (not a hypothetical), and `vibe audit --history` runs with whatever git config the operator's machine has.

AC7 claims "Context lines (U3) handled" but as written only needs ordinary non-empty context lines to pass — it doesn't require a zero-byte context-line fixture. Given the entire point of this task is to close state-leak-across-boundary bugs, this needs: (a) an explicit design rule for a zero-length line inside a hunk (e.g. "an empty read is context iff `old_remaining>0 && new_remaining>0`, decrement both, unconditionally — checked *before* prefix matching, since `""` cannot match a `-`/`+`/`\` case pattern"), and (b) a fixture using `git -c diff.suppressBlankEmpty=true` (or a hand-built stream with a literal empty line) proving file/line attribution survives it.

### 2. BLOCKING — the "malformed `@@` = fail safe" design commitment has zero AC coverage (design bullet 4, relates to AC8)

Design bullet 4 makes a specific security claim: an unparseable `@@` line must not crash (`set -euo pipefail` is live, so an unguarded `$(( ))` on a non-numeric capture is an immediate hard failure) and must not enter an unbounded "inside hunk" state. No AC (1–10) constructs a malformed/hostile `@@` header (e.g. `@@ -abc,def +xyz @@`, or a truncated `@@ -5,` with no closing `@@`) to prove either half of that claim. Recommend folding a malformed-header fixture into AC8, asserting both that the scanner doesn't crash and that scanning after the malformed line resumes normal header classification (not stuck "inside" indefinitely).

Related, and worth naming even though I confirmed it's safe by construction: a hostile ADDED line whose *content* begins `@@ -99,5 +99,5 @@ evil` renders as `+@@ -99,5 +99,5 @@ evil` (verified with a real diff) — the leading `+` means it can never case-match a real hunk header, so it cannot re-arm `old_remaining`/`new_remaining` to attacker-chosen values (which would be a strictly worse bug than the one in scope — a forged budget, not just a forged file/tier flag). This is the single most dangerous theoretical forgery vector in the whole design and currently has no regression fixture. Suggest adding it to AC3/AC4's fixture set for future-proofing, even though today's design is provably safe against it.

### 3. Minor — AC6's carve-out has no objective oracle (AC6)

"the Tester confirms the new classification is correct" is a judgment call with no expected-findings baseline to check against, on a real, uncontrolled slice of actual repo history. AC6 does require listing every differing line, which is good, but the pass/fail decision itself is subjective in a way ACs 1–5/7 aren't. Given concern #1 above, a real (non-crafted) difference could show up in this exact differential on an operator whose git config sets `diff.suppressBlankEmpty` — worth tightening AC6 to say explicitly that any difference NOT traceable to a spoof-shaped line (per the AC's own carve-out) is an automatic `revise`, not something the Tester can wave through.

### 4. Minor — "pre-change-sha" (AC5, implicitly AC6) is named but never pinned (AC5, AC6)

AC5's differential is "vs the OLD scanner (`git show <pre-change-sha>`)" but nothing in the spec says how that sha gets captured or where it's recorded. With a 2-cycle budget, cycle 2 could silently diff against a different baseline than cycle 1 used, without anyone noticing. Recommend requiring the Generator/Tester to capture `git rev-parse HEAD` to a file (e.g. `.vs/cycle-N/pre-change-sha.txt`) before the first edit of cycle 1, and reuse that value for every later differential run.

### 5. Minor — binary-file diff sections are an unstated invariant in the fixture corpus (AC5)

Confirmed empirically: `Binary files a/x and b/x differ` appears with **no** `+++`/`---`/`@@` lines at all (just `diff --git` + `index` + that one line). Harmless today only because a binary section never emits a `+`-prefixed line to scan under stale attribution — but it's exactly the kind of line that, during a leaked "inside hunk" window (concern #1), has no defined classification either and would silently extend the leak. AC5's fixture list ("file boundaries, new files, deleted files, multiple hunks, -U0 zero-count hunks, `\ No newline`") doesn't name binary files; recommend adding one to the corpus to pin the "carries over harmlessly" property explicitly rather than leaving it implicit.

### 6. Minor — mode-change-only diff sections aren't named in the AC5 fixture list (AC5)

Confirmed empirically: a pure `chmod`-only change emits only `diff --git …` + `old mode`/`new mode` — no `index`/`---`/`+++`/`@@` at all. Same reasoning as concern #5: harmless today, unstated in the ACs, cheap to add to the corpus by name.

## Verified-safe (no concern, listed so the Tester doesn't re-litigate)

- `++ /dev/null` → renders `+++ /dev/null` (AC1) — confirmed.
- `++ b/.vs/x` → renders `+++ b/.vs/x` (AC2) — confirmed.
- `++ token: ghp_…` → renders `+++ token: ghp_…`, and old `scan_blob_stdin` genuinely drops it as header noise today (AC3) — confirmed both the render and the old-parser drop.
- `-- a/x` deleted + `++ b/evil` added, same hunk, adjacent lines → renders `--- a/x` / `+++ b/evil` (AC4) — confirmed, single-hunk two-line dance reproduces exactly as described.
- `-U0` omitted-count defaults to 1 on both the `-` side and `+` side independently, and explicit `,0` occurs on either side (e.g. `@@ -1,0 +2 @@`, `@@ -2 +1,0 @@`) — confirmed both directions.
- Merge commits show no diff at all by default in `git log -p` (commit header directly followed by the next `commit` line, no hunk ever opened) — confirmed, not a leak risk since counters never leave 0.
- Empty commits (`--allow-empty`) show only commit metadata, no diff section — confirmed, same reasoning.
- CRLF file content: added-line content carries a trailing `\r` into `scan_line`, but this doesn't touch the `@@` header parse (git's own headers are always LF) — not a new risk from this task.

## Verdict

**revise**
