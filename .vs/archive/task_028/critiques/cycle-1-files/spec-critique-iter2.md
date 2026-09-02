# Spec Critique — task_028 (cycle 1, iteration 2)

## Iteration-1 concerns: resolution check

All addressed correctly, verified against current source:

- **1 (sentinel case)**: AC4 now uses `bypass the hook` (all-lowercase) — confirmed a verbatim substring of `learn-hook.md:35` (`## do not bypass the hook`). Fixed.
- **2 (AC6 CLAUDE_CONFIG_DIR)**: AC6 now explicitly adds `CLAUDE_CONFIG_DIR=T/.claude` alongside the `_isolate_extras_env` vars. Confirmed `DEST_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"` in `install-claude-extras.sh:9` — the fix is correct and necessary. Fixed.
- **3 (marker form)**: AC6 states `<!-- vibe-md: <basename> -->`, matching `install-claude-extras.sh:199,202` exactly. Fixed.
- **4/5 (AC7 Flags-entry cap, vss.md occurrence drop)**: both now explicitly noted in AC7 prose. Fixed.
- **6 (vsss.md line)**: AC11 now names this clause explicitly with the same-line caveat. Fixed.
- **8 (AC10 baseline)**: `c68707d` is confirmed current HEAD — no longer ambiguous. Fixed.
- **9 (AC12 floors)**: added (650/450, lower than the critic's proposed 700/500 but present and arithmetically sound — see below). Fixed.
- **10 (AC13)**: now requires byte-identity for all ten untouched fragments, stronger than the requested grep. Fixed.

## Sentinel verification (AC4)

Checked all sentinel strings against the current pre-merge source files (`learnings.md`, `learn-hook.md`, `feedback-auto-promote.md`, `auto-memory-scope.md`, `conversation-history.md`, `content-guard.md`) with case-sensitive literal grep. **Every sentinel listed in AC4 exists verbatim in at least one of the files being merged into its target.** None missing.

## New observations

1. **AC12/AC2 arithmetic, informational (not blocking).** With the ten untouched fragments fixed at 4,449 words (byte-identical), AC2's ≤6,160 ceiling leaves ≤1,711 words for `learnings.md` + `auto-memory-scope.md` + `content-guard.md` combined. Floors (650+450+400=1,500) fit under that with only 211 words of slack — consistent, not contradictory, but confirms iteration-1 concern 7's "tight" read still holds at the floor level.

2. **AC8, MINOR (new, budget realism).** Measured current per-line word counts: vs.md:73 (Flags bullet) = 131w, vs.md:63/195/197 ≈ 155w combined, vss.md:21 = 93w, vss.md:92 = 63w, vsss.md:27 = 141w (must gain `/vs § Model economy` text it currently lacks, per grep — it has neither occurrence today). Realistic compression of these lines alone yields roughly 250–350 words of the required ≥360, before accounting for vsss.md's line needing to *add* words to satisfy AC7's pointer requirement. Achievable but tight, same character as concern 7; flag as cycle-2 risk if Generator only touches the AC7-named lines and doesn't also trim vs.md:63/195/197 (permitted under "relocating the Fable-grant text").

3. **AC9, MINOR (new, wording defect).** The exclusion clause "zero hits outside smoke-test.py's own test names and CHANGELOG.md" references two files that are **not in AC9's own grep target list** (`README.md ONBOARDING.md CONTRIBUTING.md CLAUDE.md MANUAL-TESTS.md devcontainer/`). Confirmed: `smoke-test.py` currently has `LEARN_HOOK_MD`, `FEEDBACK_AUTO_PROMOTE_MD`, `CONVERSATION_HISTORY_MD` constants and matching test names — real content Generator must clean up per the Test-location section — but AC9 as literally written never scans `smoke-test.py` to verify it, and never scans `CHANGELOG.md` either. Vacuous exclusion; add both files to the grep target list so the named exceptions do real work.

## Verdict

**pass** — all iteration-1 concerns are correctly resolved and verified against source, no sentinel is missing, and no new BLOCKING issue was found. Two new MINOR items (AC8 tightness, AC9 dead exclusion clause) are worth a one-line tweak but do not warrant another revision cycle.
