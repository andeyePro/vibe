# Spec Critique — task_023 (path-scoped WARN allowlisting), cycle 1, iteration 2

Verdict: **pass**

## Verification of the 4 blocking concerns from iteration 1

1. **ERE-loop exclusion of `path-warn:` lines — RESOLVED.** Design § "Syntax"/point 2 now states the make-or-break constraint explicitly: `line_is_allowlisted` (and any other consumer of the allowlist's ERE entries) "must structurally skip `path-warn:`-prefixed lines — neither the full line nor the glob remainder may ever be handed to `grep -E` as a content pattern." This is no longer implicit in "other lines are unaffected" — it names the exact function and the exact failure mode iter-1 demonstrated. AC3b is a mandatory test that pins it: a BLOCK secret in a non-matching file, on a line also containing the literal text `smoke-test.py`, and a second variant containing the literal text `path-warn:smoke-test.py`, must still fire BLOCK. That covers both halves of the original hole (bare glob remainder and full prefixed line reaching `grep -E`).

2. **Back-compat claim — RESOLVED, and now factually correct.** I read `line_is_allowlisted` (`devcontainer/git-hooks/vibe-content-scan.sh:71-84`) directly: `pattern` is bound by `IFS= read -r pattern` off the raw allowlist line, with only blank/`#`-comment lines skipped (`case "$pattern" in ""|\#*) continue ;; esac`) — no prefix-stripping, no trimming beyond what `read -r` already does. So for a `path-warn:smoke-test.py` line, the OLD scanner's `pattern` really is the whole string `path-warn:smoke-test.py`, prefix included, handed straight to `grep -E`. I verified empirically:

   ```
   $ printf 'error: bad key AKIAABCDEFGHIJKLMNOP found near smoke-test.py fixture line 42' \
       | grep -qE -- "path-warn:smoke-test.py" && echo MATCH || echo NOMATCH
   NOMATCH
   $ printf 'error: bad key AKIAABCDEFGHIJKLMNOP found near path-warn:smoke-test.py fixture line 42' \
       | grep -qE -- "path-warn:smoke-test.py" && echo MATCH
   MATCH
   ```

   A line merely mentioning the bare filename `smoke-test.py` does NOT match; only a line containing the literal substring `path-warn:smoke-test.py` does. This confirms the spec's corrected claim and shows iteration 1's own test (which used the bare glob remainder `smoke-test.py` as the grep pattern, not the full raw allowlist line) tested the wrong string — the spec's fix is the right one, not a rationalization. The revised Design § "Back-compat" now: states the accurate mechanism, names the narrow real window (a doc/commit-message line quoting the literal entry text on a pre-task_023 scanner), accepts and documents it in content-guard.md with a concrete caution, and pins same-commit rollout for vibe's own repo. This matches option (a) from iter-1's three offered remediations and is proportionate to the (now correctly characterized) risk.

3. **Glob `/`-crossing — RESOLVED.** Design § "Glob semantics pinned" now states explicitly: "the glob is used as an UNQUOTED bash `case`-style pattern against the repo-relative path — `*` crosses `/`", names the quoted-variable failure mode that would silently break the feature, and AC2 mandates a nested-path case (`.vs/archive/task_099/critiques/foo.md` against `path-warn:.vs/*`) specifically to catch that implementation bug.

4. **Degenerate globs — RESOLVED.** Design § "Degenerate globs" now decides both cases: empty/whitespace-only glob → malformed, skipped, matches nothing (AC2 requires a test: `path-warn:` alone causes no crash and no match-all); `path-warn:*` → accepted under the same trust model as an equally-overbroad ERE entry today, documented rather than policed. No ambiguity left for Generator/Tester to guess independently.

## Verification of the 4 minor concerns

- **AC8 direct shellcheck** — resolved. AC8 now reads "...AND a direct `shellcheck devcontainer/git-hooks/vibe-content-scan.sh` clean run — `code-check.py` structurally cannot see that directory... so the direct invocation is the real lint gate."
- **`--range` idempotency** — resolved. New AC3c pins byte-identical `--range` output with/without `path-warn` entries present, framed correctly as a one-way-floor regression guard.
- **Rename caveat** — resolved. Design § "Rename caveat" now states the dependency has changed in kind (previously cosmetic-only, now suppression-relevant) and accepts it as pre-existing/unchanged scope for `git diff -U0 --no-color`.
- **Metachar escaping doc note** — resolved in Design ("documented in content-guard.md, not otherwise handled"), though see minor note below on AC coverage.

## Fresh adversarial pass — revised text only

No new blocking issues found. Two very minor, non-blocking observations:

- **AC9 doesn't name glob-metachar escaping as a required doc item.** Design commits to documenting `[`, `]`, `?` escaping in content-guard.md, but AC9's enumerated doc checklist ("syntax, WARN-only, diff-modes-only, BLOCK-never-suppressed") doesn't list it, so nothing in the acceptance criteria would fail if a Generator's content-guard.md update omitted that specific sentence. Low stakes — no such path exists in vibe's tree today, and the design text itself is the durable record even if the AC doesn't gate it.
- **Recognition of the `path-warn:` prefix at line-start isn't explicit about leading whitespace.** Spec trims whitespace *around the glob* but says nothing about a line like `  path-warn:.vs/*` (leading spaces before the keyword itself). This mirrors the pre-existing convention — ordinary ERE allowlist lines aren't trimmed either — so it's consistent behavior, not a new inconsistency, but worth a one-clause mention if a future reader wonders why indented entries don't work.

Neither item changes the verdict; both are documentation-completeness nits on an already-correct design, not correctness or security gaps.

## Verdict

**pass.** All 4 blocking concerns are resolved with the actual required fix (structural exclusion, not just phrasing), verified against the real `line_is_allowlisted` code and confirmed empirically. All 4 minors are resolved. The fresh pass over the revised text surfaced only two trivial doc-completeness nits, neither blocking.
