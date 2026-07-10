# Generator Report — task_015 cycle 1

## Files changed

| File | Region / nature |
|------|----------------|
| `/workspace/vibe` | New helpers `image_drift_needs_recreate` + `remove_existing_flag` at lines 850-908 (above VIBE_SOURCE_ONLY guard); launch-path wiring at lines 1193-1201 (replaces old line 1193) |
| `/workspace/CHANGELOG.md` | New `## 2026-05-27` heading + entry (inserted above `## 2026-05-26`) |
| `/workspace/MANUAL-TESTS.md` | New Test 26 checklist block (inserted before `## Troubleshooting`) |

## Function names and line regions (post-edit)

- `image_drift_needs_recreate` — defined at approx. vibe:862-896
- `remove_existing_flag` — defined at approx. vibe:898-907
- VIBE_SOURCE_ONLY guard — vibe:955 (unchanged; helpers are above it)
- Launch-path wiring — vibe:1192-1201 (replaces old single-line `[ "$REBUILD" = true ] && UP_ARGS+=(--remove-existing-container)`)

## AC satisfaction

| AC | Status | Evidence |
|----|--------|---------|
| AC1: no container -> no-op | satisfied | Step 1 early-return when `cid` empty; verified by manual stub smoke-check |
| AC2: matching ids -> no-op | satisfied | Step 5 emits nothing when ids equal; verified |
| AC3: drifted ids -> emit 1 | satisfied | Step 5 emits `1` when ids differ; verified |
| AC4: idempotent flag (truth table) | satisfied | `remove_existing_flag` emits at most one token; all four truth-table cases verified |
| AC5: fail-safe under set -euo pipefail | satisfied | Every docker call uses `|| var=""` on separate line from `local` (no SC2155); no `| head` pipe; sourced under pipefail with stubs; all (a)-(d) verified |
| AC6: multiple containers -> first line only | satisfied | `cid="${cids%%$'\n'*}"` takes first line of multi-line output |
| AC7: retry block preserved (inspection) | satisfied | Partial-state retry block (devcontainer "${UP_BASE_ARGS[@]}" --remove-existing-container) unchanged; diff confirms |
| AC8: comment with drift/superseded | satisfied | Many comment lines contain both words; `grep -n drift vibe` shows lines 850,856,860,884,885,889,893,898,900,1193,1198,1199 |
| AC9: shellcheck clean | satisfied | `python3 code-check.py` -> "✓ shellcheck clean across 14 files" |
| AC10: smoke tests pass | not blocked (Tester writes new tests; existing suite unbroken) |
| AC11: launch-path wiring (inspection) | satisfied | `drift_marker` / `extra_flag` wiring present; distinct status line prints when drift and not REBUILD |

## Mandated pattern compliance

- No `| head` pipe: `cid="${cids%%$'\n'*}"` used
- `local` declarations separate from assignments: confirmed (`local cids cid` then `cids=$(...)`)
- Every docker call gets `2>/dev/null` and `|| var=""` on a separate line
- Step 4 empty/non-zero -> emit 1 (pruned/superseded source): confirmed
- Step 3 empty/non-zero -> emit nothing (no current image): confirmed
- Bash 3.2 portable: no `${arr[@]: -1}`, no `mapfile`, no `declare -A`, no `&>`

## Deviations / notes

- No deviations. The spec's sketch code at "Architecture" §"Launch-path wiring" was
  followed directly. The status message uses ` - ` (ASCII hyphen with spaces) as
  specified; no em dash.
- `${@: -1}` appears in the spec's stub skeleton only (for the Tester's stub inside
  the container's bash 5.x test process); the helper itself uses no bash-4+ constructs.

## code-check.py output

```
→ shellcheck vibe
→ shellcheck install.sh
[... 12 more files ...]
✓ shellcheck clean across 14 files
```

## Manual smoke-check output (8 cases)

```
PASS: no container -> emit nothing
PASS: matching ids -> emit nothing
PASS: differing ids -> emit 1
PASS: pruned source -> emit 1
PASS: (true,1)->token
PASS: (true,"")->token
PASS: (false,1)->token
PASS: (false,"")->empty
```

## Retry attempts

1 (no retries needed).
