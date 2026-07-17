# Spec Critique — task_023 (path-scoped WARN allowlisting), cycle 1

Verdict: **revise**

## Concerns

1. **BLOCKING — path-warn lines are not excluded from `line_is_allowlisted`'s ERE loop; this is a live BLOCK-suppression hole, demonstrated, not hypothetical.** (AC1, AC3, AC4)

   `line_is_allowlisted` (git-hooks/vibe-content-scan.sh:71-84) reads every non-comment, non-blank line of `.vibe-content-allow` and tests it as a `grep -E` pattern against the flagged content — for every class, including BLOCK (`check_rule` calls `line_is_allowlisted` unconditionally at line 115, before emitting any finding, BLOCK rules included). The spec's Design section says "all other lines keep today's ERE semantics" and AC1 says "every non-`path-warn:` line keeps exact ERE whole-line semantics" — but neither ever states that `path-warn:` lines themselves must be *excluded* from that ERE loop. That's the actual requirement, and it's currently unstated, so an implementation could satisfy AC1's literal wording while still feeding path-warn lines into `line_is_allowlisted` as EREs.

   I verified this is not academic. The two entries the spec ships are `path-warn:.vs/*` and `path-warn:smoke-test.py`. As bare ERE text, `smoke-test.py` is effectively a literal substring match (only the `.` is regex-special, and it just means "any char"). I ran it:

   ```
   $ printf '%s\n' 'token: ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA  # ref smoke-test.py' | grep -qE -- "smoke-test.py" && echo MATCH
   MATCH
   ```

   If `line_is_allowlisted` isn't explicitly updated to skip `path-warn:`-prefixed lines, then the moment `path-warn:smoke-test.py` lands in `.vibe-content-allow`, **any line anywhere in a diff — commit message, code comment, unrelated file — that merely contains the substring `smoke-test.py` has every finding on it silently suppressed, including a real BLOCK secret on that same line.** This is exactly the "double-parse hazard" the task brief asked me to scrutinise, and it's worse than WARN-only: it's a BLOCK bypass triggerable by an innocuous string co-occurring with a secret, not by any adversarial glob.

   Required fix: an explicit design/AC statement that `path-warn:` lines are structurally removed from the ERE-candidate set before `line_is_allowlisted` ever runs (not just "other lines are unaffected" — the path-warn lines themselves must never be handed to `grep -E`). Add a mandatory test: stage a BLOCK-shaped secret on a line that also contains the literal text of a shipped `path-warn` glob (e.g. `smoke-test.py`) in a **non-matching** file path, confirm the BLOCK finding still fires.

2. **BLOCKING — the spec's own "Back-compat" claim is false for the shipped entries, and that falseness is a live transitional-safety bug, not just an editorial slip.** (Design § Back-compat, AC1)

   "An older scanner reading a new allowlist treats a `path-warn:` line as an ERE that matches nothing meaningful — harmless." I tested this against the actual pre-task_023 scanner logic:

   ```
   $ printf '%s\n' 'error: bad key AKIAABCDEFGHIJKLMNOP found near smoke-test.py fixture line 42' | grep -qE -- "smoke-test.py" && echo MATCH
   MATCH
   ```

   `smoke-test.py` is not "nothing meaningful" as an ERE — it's a highly meaningful literal substring, and it will match any line that happens to mention the filename. So the OLD scanner reading the NEW allowlist (the exact state that exists during any rollout window — a container that hasn't re-synced `devcontainer/git-hooks/*` yet, or any other consumer of this same `.vibe-content-allow` file) will silently over-suppress the instant these two lines are appended, independent of whether the NEW scanner is implemented correctly. This directly undercuts the justification for co-locating `path-warn:` entries in the same file as ERE entries without a version/namespace guard. At minimum the spec must retract the "harmless" claim and either (a) accept and document the transitional-suppression risk explicitly, or (b) require the rollout order to land the new scanner before the new allowlist lines (commit ordering constraint), or (c) pick glob text that isn't ERE-dangerous as a fallback (doesn't fix the general case, just the two shipped entries).

3. **BLOCKING — glob-crosses-`/` semantics are unstated, and the real repo shape needs it to be true.** (AC2, AC5)

   The spec says "a bash glob matched against the repo-relative file path" without saying whether `*` matches across `/`. I checked empirically: an **unquoted** variable used as a bash `case` pattern (`case "$path" in $glob) ... esac`) DOES cross `/` (`a/*` matches `a/b/c`), but if an implementation naively quotes the variable (`"$glob"`) — a very common shell-scripting reflex — `*` becomes a literal character and the whole feature silently breaks (nothing except a file literally named `.vs/*` would ever match). The real `.vs/` tree already has 3-level nesting (`.vs/archive/task_022/critiques/*.md`), and `.vs/cycle-1/` (where this critique itself lives) is one level deep — both are exactly the kind of file the shipped `path-warn:.vs/*` entry must cover for the feature to do its job past this cycle. AC2's example fixture (`path-warn:fixtures/*` against a same-level file) never exercises a nested path, and AC5's "fixture-repo simulation of the vibe tree shape" doesn't specify that a nested-directory case is required. Required fix: state explicitly in Design that `*` is a substring-style match crossing `/` (unanchored case-pattern glob, not pathname-expansion glob), and add a mandatory nested-path test case (e.g. a staged `.vs/archive/task_099/critiques/foo.md` edit against `path-warn:.vs/*`) to AC2 or AC5.

4. **BLOCKING — degenerate glob forms are undecided.** (AC1, AC7, new)

   Two unresolved cases the task brief flagged and the spec doesn't answer: an empty glob (`path-warn:` with nothing after the prefix — does it silently match nothing, or does it need explicit `continue`-and-skip handling?), and a bare wildcard (`path-warn:*`, matching every file, which would demote the ENTIRE staged diff to BLOCK-only — i.e. disable all WARN checking repo-wide). The existing ERE mechanism already permits an equivalently broad entry (a lone `.` as an ERE matches almost anything), so this isn't a new *class* of risk, but the spec explicitly frames path-warn as "known-deliberate narrow suppression" and ships only two narrow entries — it should say outright whether `path-warn:*` is accepted (same trust model as an overbroad ERE entry, both are PR-reviewable) or must be rejected/flagged. Silence here means a Tester and a Generator can each independently guess, and guess differently.

5. **Minor — AC8's "code-check.py clean" doesn't actually exercise the changed file.** (AC8)

   TODO.md's 2026-07-15 item states `code-check.py`'s `scripts()` cannot be extended to cover `devcontainer/git-hooks/`, and this spec's own Out-of-scope section defers `code-check.py` as "a separate queue item." So AC8 as worded gives false assurance — `vibe-content-scan.sh` won't actually be shellchecked by the command AC8 names. Task_019's header comment for this same file says it was "verified directly + by a task_019 AC" — that's the right precedent. AC8 should add an explicit `shellcheck devcontainer/git-hooks/vibe-content-scan.sh` (or equivalent direct invocation) line rather than relying on `code-check.py` to catch a regression it structurally cannot see.

6. **Minor — `--range` idempotency under path-warn is provable but untested.** (AC3, AC6)

   `--range` already runs at tier `block` (scan_diff_stream "block"). Path-warn demotion, per the spec, can only ever set tier to `block`, never promote it — so applying path-warn logic to `--range` is a no-op by construction, and I don't think this is a real risk. But it's exactly the kind of shared-code-path invariant that's cheap to pin down explicitly and easy to silently break in a refactor (e.g. if a future edit makes tier demotion additive/settable rather than a one-way floor). Recommend one explicit regression line in AC3 or AC6: "`--range` output is byte-identical with and without path-warn entries present in the allowlist," so a future change that breaks the one-way-floor property fails loudly.

7. **Minor — rename-diff path attribution is now suppression-relevant, not just cosmetic.** (Design § Mechanism)

   `scan_diff_stream` derives `current_file` from `+++ b/<path>` with no `-M`/rename-detection awareness (pre-existing, task_019/022 behaviour). Previously a path mislabel only affected a finding's *location string*. Now it also decides whether WARN fires at all for that hunk's added lines. The realistic exposure is low (default `git diff` rename detection is off; the shipped entries and AC5's fixtures aren't rename scenarios) but the spec should say a sentence acknowledging the dependency has changed in kind, so a future reader doesn't assume path attribution is still "just cosmetic."

8. **Minor — glob metacharacter escaping in a literal path is undocumented.** (Design § Syntax)

   If a real repo path ever contains `[`, `]`, or `?` (glob-special in `case` matching), a `path-warn:` entry can't target it literally without escaping, and the spec doesn't mention this. Low real-world likelihood (no such paths exist in vibe's tree today) — flagging for completeness only, not blocking.

## Verdict

**revise.** Concerns 1–4 are blocking: two are demonstrated correctness/security gaps (the ERE double-parse hazard, which reaches BLOCK-tier suppression, not just WARN, plus a factually wrong back-compat claim), and two are under-specification that will produce a Generator/Tester mismatch (glob `/`-crossing semantics, degenerate-glob legality) on exactly the paths (`.vs/archive/…`, `.vs/cycle-1/…`) this task exists to fix. None require a redesign — all four are pin-down-the-existing-design fixes to the spec text plus one or two new AC lines.
