# Spec Critique — task_027 (cycle 1, iteration 2)

Re-verified empirically against the real repo: `VIBE_REPO_DIR` derivation (vibe ~75-83) and its
position relative to `usage()` (~120) and the new call-site window (~2959-2984); the exact anchor
comment lines (`# ── GitHub setup` / `# ── Build the image`, confirmed unique in the file, box-drawing
`─` U+2500 bytes checked with `cat -A`); the pinned `_usage_text()` capture mechanism run live under
the exact `bash -c "source <path>; ..."` convention `smoke-test.py` uses (`_source_vibe_call`,
smoke-test.py:1020-1029, confirms `VIBE` always points at the real `/workspace/vibe` file, never a
temp copy); the per-op fail-soft guard idiom run live against a chmod-500 `meta/` dir under
`set -euo pipefail`; the `install_claude_md_fragments` special-case list in
`install-claude-extras.sh` (ssh-discipline.md / brain2.md / shared-repos.md, confirmed `vibe-cli`
string absent today); and the `meta/<tool>-operation.md` + brain2-trust-discipline convention against
the real `brain2.md` fragment.

## Concerns

1. **minor — "usage()'s two emission steps" underdescribes the function body.** `usage()` (vibe
   ~120-125) has three statements before `exit 0` (the `grep|grep|sed` pipeline, `echo ""`, and
   `echo "vibe $(_vibe_version)"`), not two. Cosmetic only — the operative instruction ("hold
   everything but the exit; grep `$VIBE_REPO_DIR/vibe` instead of `$0`; `usage()` becomes exactly
   `_usage_text` + `exit 0`, byte-identical output") is unambiguous and I verified it produces
   byte-identical output to the current `usage()` when run non-sourced (`--help` tests at
   smoke-test.py:99-105, 1085-1089, 1319-1323, 2166, 2402-2432 are execution-path, so `$0` and
   `$VIBE_REPO_DIR/vibe` already resolve to the same file — no regression risk). Not
   implementation-blocking; just tighten the prose count if touched again.

2. **minor — AC6's "nowhere else in the file except its own definition" is slightly ambiguous about what counts as "its own definition."** If Generator follows this codebase's dense same-region-commenting habit (e.g. the `_learning_capture` idiom is named in a comment 25 lines away from its own body, vibe ~415-421) and adds a doc comment near the call site that names `refresh_brain2_vibe_note` in prose (not as the literal `refresh_brain2_vibe_note || true` call), a literal-string Tester grep could either false-flag a legitimate explanatory comment or, if scoped only to the exact call pattern, silently allow multiple prose mentions the AC's stricter reading intends to forbid. Low risk — nothing in the spec's own call-site language invites such a comment, and a competent Tester will grep for the call pattern specifically — but worth a one-clause tightening ("the literal call `refresh_brain2_vibe_note || true`" vs "the string `refresh_brain2_vibe_note`") if this AC gets reused as a template for other anchor-pinned wiring checks.

## Verification of the two BLOCKING fixes (cycle-1 iteration 1)

- **Fix 1 (`_usage_text()` factor).** Reproduced the exact failure mode from iteration 1 first
  (`$0` under `bash -c "source ...; usage"` resolves to `bash`, producing the useless 11-char
  fallback plus a `grep: bash: No such file or directory` stderr line), then reproduced the fix:
  sourcing vibe under `VIBE_SOURCE_ONLY=1` and defining a stand-in `_usage_text()` that greps
  `"$VIBE_REPO_DIR/vibe"` returns the full 68,993-char help text (`Usage:` × 1, `vibe pat` × 6) with
  zero stderr. `VIBE_REPO_DIR` (vibe ~83) is a top-level unconditional assignment, defined long
  before `usage()` (~120) and long before the anchor window (~2959-2984) — no ordering hazard for
  either the definition site or the call site. The out-of-scope line now correctly carves out this
  exact reshape from the "don't touch `usage()`" ban, resolving the self-contradiction iteration 1
  flagged. AC3/AC4/AC10 are mechanically achievable as specified.

- **Fix 2 (per-op fail-soft guards).** Reproduced the iteration-1 kill-shot first (an unguarded
  write into a chmod-500 dir under `bash -c 'source ...'` with `set -euo pipefail` terminates the
  whole sourced shell, rc 1, no "still alive" line). Then reproduced the pinned guard shape
  (`mkdir -p ... 2>/dev/null || return 0`; `[ -w ... ] || return 0`; `mktemp ... || return 0`;
  write `2>/dev/null || return 0`; `mv ... 2>/dev/null || return 0`) against the same chmod-500
  fixture: function returns 0, outer sourced shell survives, rc 0. This idiom is also consistent
  with the codebase's existing `if ! cmd; then ...; fi` pattern used for the same
  set-e-under-sourcing hazard (`rotate_token`'s guarded `read`, vibe ~415-421, explicitly
  cross-referenced by the spec). AC5 is mechanically achievable as specified.

## Minors from iteration 1, re-checked

- AC6 placement anchor — now pinned to the two exact `# ── GitHub setup` / `# ── Build the image`
  comment lines; both confirmed to exist verbatim and exactly once each in `vibe` (grep count = 1
  apiece; byte-level check confirms the U+2500 box-drawing character matches). Resolved.
- AC7 framing — now states the accurate, narrower claim ("directory glob with named special-cases
  like ssh-discipline… `vibe-cli.md` is not among them") rather than the sweeping "no special-casing
  anywhere" claim. Verified against the real `install_claude_md_fragments` loop
  (`install-claude-extras.sh` ~91-132): exactly three filename special-cases exist
  (`ssh-discipline.md`, `brain2.md`, `shared-repos.md`), `vibe-cli.md` is not one of them, and the
  string `vibe-cli` does not appear anywhere in the file today. Resolved.
- Brain2-trust line — fragment content requirements now include the line noting that prose outside
  the managed block is ordinary brain2 content under the normal trust discipline, consistent with
  the real `brain2.md` fragment's own framing and the `meta/<tool>-operation.md` convention (mirrors
  the shipped `zotero-operation.md` pattern). Resolved.

## Things verified as sound (no concern, stated for the record)

- `_brain2_source` (vibe ~1463) performs no directory-existence check — it only special-cases the
  literal string `"off"` — confirming the spec correctly assigns the `[ -d "$p" ]` gate to
  `refresh_brain2_vibe_note` itself rather than assuming `_brain2_source` already does it.
- The managed-block marker strings, awk strip/reappend portability, and AC1/AC2 regex behaviour
  (unchanged from iteration 1) remain correct on re-check; no regression from this revision's edits.
- No naming collision: no pre-existing `_usage_text` symbol anywhere in `vibe`.

## Verdict

**pass** — both iteration-1 BLOCKING concerns are genuinely fixed and independently reproduced
against the real repo, not just asserted. Two minor residuals (#1, #2 above) are accepted:
both are prose-precision nits with no mechanical effect on AC verifiability as specified, and
neither blocks Generator or Tester from implementing/testing the pinned contract correctly.
