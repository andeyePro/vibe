# Generator report — task_026, cycle 1

## What changed

- `vibe`:
  - New functions in the Token helpers section (after `setup_token`, before
    the Docker config helpers block): `rotate_token`, `stored_token_rejected`,
    `maybe_reprompt_stored_token`, `_pat_usage`, `pat_handle_subcommand`.
  - New dispatch block `if [ "${1:-}" = "pat" ]; then pat_handle_subcommand
    "$@"; exit $?; fi`, placed after the `audit` dispatch block and before
    `parse_vibe_args`, mirroring `learn`/`repos`/`audit`.
  - Launch-path integration: the `elif GITHUB_REPO=$(detect_github_repo);
    then ... fi` block's inner `if [ -z "$GITHUB_TOKEN" ]; then setup_token
    ...` now has an `else` branch containing the single call
    `maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"`.
  - Top-of-file header comment (`usage()`'s source): added a `vibe pat
    [owner/repo]` line and a sentence stating it runs on the "HOST shell",
    right after the existing `vibe learn` block.
  - Reused the existing `is_valid_repo_slug` (vibe ~1594) for explicit-slug
    validation rather than reinventing the regex — it already implements
    exactly the pinned charset/one-slash rule.
- `README.md`: folded the rotation + 401 auto-reprompt sentence into the
  existing `~/.vibe/tokens` row of the Host-side state table (contains both
  `vibe pat` and `401`).
- `MANUAL-TESTS.md`: new `### Test 37: vibe pat PAT rotation + launch-time
  401 reprompt (task_026)` with three sub-cases (37a manual rotation, 37b
  end-to-end revoked-PAT reprompt, 37c `VIBE_PAT_CHECK=0` suppression),
  following the existing numbered-test/checklist format.
- `TODO.md`: task_026 line ticked `[ ]` → `[x]`, prefixed narrative with
  `DONE 2026-07-21 (/vs cycle 1)`.
- `CHANGELOG.md`: new `## 2026-07-21` heading (didn't exist; added at the
  top, above `## 2026-07-17`) with a full task_026 entry.
- `.vs/tasks.json`: task_026 `implementation_status` → `complete` (status
  field only; JSON validated after edit).
- Scratch tests (gitignored, not in diff): `.vs/cycle-1/scratch-tests/test_task026.py`
  — 80 assertions covering AC1–AC10, run standalone with
  `python3 .vs/cycle-1/scratch-tests/test_task026.py`. All green.

## How each AC is met

1. **Arg parsing** — `pat_handle_subcommand` checks `--help`/`-h` first
   (before any `$#`-based validation), then dispatches on `$#`: 0 → detect,
   1 → slug-validate, else → one-line `Usage: vibe pat [owner/repo]` on
   stderr, exit 1. Verified: 3-arg and bad-slug cases exit 1 on stderr,
   nothing created in the token store; `--help`/`-h` exit 0 on stdout.
2. **Overwrite + preserve** — `rotate_token` calls the existing `save_token`
   unchanged, which already does the filter-then-append-then-`mv`+`chmod 600`
   dance; verified a 3-line fixture (repo line, `ZOTERO_API_KEY=`,
   `OPENPROJECT_MCP_BEARER=...=` with trailing `=`) survives with only the
   target line replaced, still 3 lines, still 600.
3. **Empty stdin (both ways)** — the errexit-guarded `if ! IFS= read -rsp
   ... token; then token=""; fi` funnels both EOF (read fails) and a lone
   newline (read succeeds with empty string) into the same `[ -z "$token"
   ]` check, which prints `aborted — token store unchanged` to stderr and
   exits 1 before any `save_token` call — store proven byte-identical both
   ways.
4. **No-arg detect** — a non-git dir gets the stderr hint and exit 1; a real
   git checkout with an `origin` remote (`someowner/somerepo`) prints `Repo:
   someowner/somerepo` before hitting the same empty-stdin abort path (fed
   closed stdin so the test terminates without blocking at the prompt).
5/6. **`stored_token_rejected` + argv/stdin shape** — one `curl -s -o
   /dev/null -w '%{http_code}' --max-time 5 -K - <url>` call, fed the
   config line via a here-string (avoids a two-process pipe, so `set -e`'s
   pipefail can't misattribute a downstream failure); `code=$(...) || true`
   absorbs a non-zero curl exit without aborting the sourced script, then
   `[ "$code" = "401" ]` is the sole decision. Shims for `401`/`200`/`404`/
   `000`/non-zero-exit-empty-output all returned the spec'd verdict; argv
   logging confirmed `api.github.com/repos/owner/repo` and `-K` present,
   fixture token absent; stdin logging confirmed the `Authorization: Bearer
   ghp_task026_fixture_token` line.
7. **No token bytes in output** — checked across every AC2/3/5/6 run
   (stdout+stderr combined); none contained the fixture token.
8. **`maybe_reprompt_stored_token` branches** — sourced with
   `stored_token_rejected`/`setup_token` overridden by logging stubs
   post-source: (a) `VIBE_PAT_CHECK=0` and (b) empty token both skip both
   stubs and return 0; (c) rejection stub returning 0 emits the pinned
   warning, calls the `setup_token` stub once with the repo arg, and
   returns 0; (d) rejection stub returning 1 calls neither, returns 0. A
   static placement check greps the launch path and confirms the call line
   sits between the `else` (of the non-empty-token branch) and its `fi`,
   and is absent from the empty-token/fresh-paste branch above it.
9. **Help + regression gate** — `vibe --help` output contains both `vibe
   pat` and the phrase `HOST shell` (added to the top comment block, not
   just `_pat_usage`'s own text, so it's visible from the top-level
   `--help` the AC actually names). `python3 code-check.py`: 19 files,
   clean. Full pre-existing `python3 smoke-test.py`: exit 0, "✓ smoke tests
   passed", no regressions (only substring hits on "fail"/"✗" inside
   passing-test names, no actual failures — checked by grepping for
   FAIL/✗ lines and confirming they're all "✓ ..." lines that happen to
   mention "fail" in their description).
10. **Docs content** — `README.md` contains `vibe pat` and `401`;
    `MANUAL-TESTS.md` contains `vibe pat` and `VIBE_PAT_CHECK=0`.

## Verification output tails

`python3 code-check.py`:
```
→ shellcheck devcontainer/git-hooks/vibe-content-scan.sh

✓ shellcheck clean across 19 files
```

`python3 smoke-test.py`:
```
[task_024 AC10: TODO.md hardening item ticked/removed]
  ✓ [task_024 AC10] TODO.md exists
  ✓ [task_024 AC10] the hardening item is no longer open ('- [ ]') in TODO.md — either ticked to [x] or removed entirely now that task_024 has landed the fix

✓ smoke tests passed
```
(exit code 0; full-suite scratch grep for `FAIL`/`✗` found only "✓ ..." lines
whose *description text* contains "fail" as a substring, e.g. "all docker
calls fail → emit nothing" — no actual assertion failures.)

Scratch harness (`.vs/cycle-1/scratch-tests/test_task026.py`), final line:
```
80 passed, 0 failed
```

## Spec ambiguity encountered and how it was resolved

- **Where exactly must `HOST shell` appear for AC9?** AC9 says "`vibe --help`
  output contains ... the phrase `HOST shell` within the pat help text".
  `vibe --help` (via `usage()`) only ever prints the top-of-file `#`-comment
  header, not `_pat_usage`'s own text (that's reached only via `vibe pat
  --help`, a separate invocation). To satisfy the AC literally — the phrase
  showing up in `vibe --help`'s actual output — I added the `HOST shell`
  sentence to the top header comment block itself (next to the new `vibe
  pat [owner/repo]` line), mirroring how the existing `vibe learn` block
  already does this. `_pat_usage` (for `vibe pat --help`) also independently
  contains the phrase, which can't hurt and keeps both surfaces consistent.
- **Exact leading whitespace on pinned strings.** The spec's pinned strings
  (`Repo: <owner/repo>`, `stored token found — it will be replaced`, `no
  stored token yet`, `aborted — token store unchanged`, the `✓ Token saved
  for ...` line) are written in the spec with no leading indentation, unlike
  most other vibe user-facing lines (which use a `  ` two-space convention).
  The one pinned string that DOES show leading whitespace is the
  `maybe_reprompt_stored_token` warning (`  ⚠ Stored PAT for ...`). I matched
  each string's pinned form exactly, including the indentation difference
  between the two groups, rather than normalising them to vibe's usual
  two-space style.
- **curl invocation shape.** The spec allows "heredoc/pipe" for feeding the
  `-K -` config. I used a here-string (`<<<`) rather than a two-process pipe
  so the whole thing is a single command substitution — `code=$(curl ...
  <<< "...") || true` cleanly absorbs a non-zero curl exit under
  `set -euo pipefail` without pipefail's multi-stage attribution ambiguity.
  Satisfies "one curl invocation" and "ignore curl's own exit status
  entirely" without extra plumbing.

No blocks hit; implementation completed within budget on the first attempt.
