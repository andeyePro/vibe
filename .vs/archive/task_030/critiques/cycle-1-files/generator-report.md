# Generator report — task_030, cycle 1

## What changed

`site/src/content/home.md` — `journey.groups` only:

1. **`launch` chip (hero, id kept)** rewritten to the everyday reused-container
   launch:
   - `lines` now quote the launcher's banner verbatim, in the launcher's own
     print order: `🚀 vibe session starting`, `project : `, a NEW `path    : `
     line, `github  : `, `hooks   : tool-call guards + idle bell`,
     `extras  : /diet · /feast · /vs · shellcheck-fixer · security-review`.
   - Firewall pin kept verbatim: `Firewall verification passed - unable to
     reach https://example.com as expected`.
   - Added a `{ role: claude, tone: note, ... }` sign-in line — "already
     signed in with your Claude subscription – nothing to re-enter" — marked
     with `tone: note` so it renders distinctly from a literal terminal
     capture (per spec AC4's "render it as a checklist/tone line rather than
     a terminal line").
   - Added a stepped "ready" line.
   - Removed the PAT-prompt line (`No GitHub token found for…`), the
     `✓ Token saved…` line, and the `Building vibe container image…` line —
     moved verbatim to the new `first-launch` chip.
   - Checklist rewritten to 4 bullets, `step:` renumbered contiguously 1-4:
     1. "finds your project and its GitHub remote, and reuses the PAT you
        set once" (repo-discovery half of the old compound bullet 1 — the
        PAT-prompt half moved to `first-launch`)
     2. firewall / "short allowlist" bullet (unchanged text)
     3. sign-in bullet (unchanged text, still true — no prompt claimed)
     4. new "ready in seconds – the container's already built, the PAT's
        already on file" bullet
   - Dropped the old "announces the session" bullet — the spec's rewrite
     instruction enumerated exactly 4 target bullet categories (repo
     discovery+PAT reuse / firewall / sign-in / ready) and didn't include it;
     the banner lines it described are still shown in `lines`, just no
     longer separately itemised in the checklist.

2. **New group "First time"**, chip `id: first-launch`, `cmd: vibe`: carries
   the moved PAT-prompt + build lines verbatim, checklist mentions
   `fine-grained PAT` and `sandboxed container` (3 bullets, `step:` 1-3).

3. **New group "Once a quarter"**, chip `id: pat`, `cmd: vibe pat`: lines
   built around `rotate_token()`'s real output (`Repo: `, `stored token
   found — it will be replaced`, the PAT-creation-page URL, the final
   `✓ Token saved for … Takes effect on the next vibe launch (no rebuild
   needed).`) plus a line quoting `90 days is a good default` (the same
   expiry advice `setup_token` gives when creating a token on GitHub, framed
   honestly as "same advice as first launch" rather than claiming
   `rotate_token` itself prints it). 3-bullet checklist (rotate-in-place /
   90-day expiry / no rebuild), `step:` 1-3.

4. Every other group/chip (`Build`, `Red team`, `Ship`, `Also in the box`)
   untouched. `journey.locked_note` untouched. Total chips: 11 → 13.

`CHANGELOG.md` — one `[x]` entry added at the top of `## 2026-09-02`.

`.vs/tasks.json` — task_030 `implementation_status`: `"pending"` →
`"complete"` (textual value only, nothing else touched).

## Launcher strings pinned, with source line numbers

All read directly from `/workspace/vibe` and `/workspace/devcontainer/init-firewall.sh` this session:

| String | Found at |
|---|---|
| `🚀 vibe session starting` | vibe:3689 |
| `     project : $PROJECT_NAME` | vibe:3691 |
| `     path    : $WORKSPACE` | vibe:3692 (this is the NEW field — did not exist on the old deck) |
| `     github  : $GITHUB_REPO` | vibe:3693 |
| `     hooks   : tool-call guards + idle bell` | vibe:3694 |
| `     extras  : /diet · /feast · /vs · shellcheck-fixer · security-review` | vibe:3695 |
| `Firewall verification passed - unable to reach https://example.com as expected` | devcontainer/init-firewall.sh:315 |
| `No GitHub token found for $repo.` | vibe:409 |
| `2. Set an expiry (90 days is a good default)` | vibe:414 |
| `3. Under 'Repository access' → 'Only select repositories'` | vibe:415 |
| `✓ Token saved — you won't be asked again for this repo.` | vibe:437 |
| `Building vibe container image ($IMAGE_TAG, claude-code=${CLAUDE_CC_VERSION})...` | vibe:3411 |
| `stored token found — it will be replaced` | vibe:459 |
| `echo "Repo: $repo"` | vibe:455 |
| `✓ Token saved for $repo. Takes effect on the next vibe launch (no rebuild needed).` | vibe:490 |
| `https://github.com/settings/personal-access-tokens` (rotate_token's URL) | vibe:463 |

Note: the launcher prints `—` (em dash) in "Token saved — you won't be asked
again…"; `home.md` (both the pre-existing launch chip and the moved
first-launch chip) uses `–` (en dash), matching the file's existing house
style. `site-check.mjs`'s `norm()` folds `–`/`—`/`-` to `-` before comparing,
so this is not a mismatch under the mechanical test; my own scratch check
initially had a tautological bug asserting raw (non-normalised) equality
here — fixed in the scratch script, not a home.md defect (see below).

## Build result

`cd /workspace/site && npm run build` — **exit 0** (Astro, `home.md`
frontmatter parses cleanly, 1 page built).

`npm run check` (informational — the Tester owns rewriting this) currently
also exits 0 on this deck: its existing launch-checklist guard (site-check.mjs
line 37) checks whole-page `html.includes(s)` for `fine-grained PAT` /
`sandboxed container` / etc., not scoped to `step-launch`, and those strings
now legitimately live on the new `first-launch` chip elsewhere on the same
page — so the old guard passes by coincidence rather than by being correct.
Per the spec, this guard still needs the Tester's chip-scoped rewrite; I did
not touch `site-check.mjs`.

## Scratch TDD results

`.vs/cycle-1/scratch-tests/check_task_030.mjs` (node, no deps) checks AC1-AC8
and mechanical proxies for AC12 against `site/dist/index.html` and
`site/src/content/home.md`.

- **Red** (`git stash` of just the `home.md` edit, rebuilt, ran the check):
  19 of 31 checks failed, as expected (no `first-launch`/`pat` chips, 11
  chips not 13, old banner/PAT copy still on the launch chip, etc.).
- **Green** (stash popped, rebuilt, ran the check again): 1 failure surfaced
  from a bug in my own test (a tautological raw-string-vs-normalised-string
  equality comparison for the moved `Token saved` line) — not a content
  defect; fixed the assertion to use the same dash-normalising `inBoth`/`norm`
  approach as the rest of the suite. Final run: **31/31 passing, exit 0**.

AC9-AC11 (the rest of the permanent guard suite, scope lock, `npm run check`
exit 0 with the Tester's rewritten guards) and AC12's full holistic read are
the Tester's / Evaluator's to verify — out of my remit as Generator.

## Files touched

- `/workspace/site/src/content/home.md`
- `/workspace/CHANGELOG.md`
- `/workspace/.vs/tasks.json` (implementation_status value only)
- `/workspace/.vs/cycle-1/scratch-tests/check_task_030.mjs` (new, scratch)
- `/workspace/.vs/cycle-1/generator-report.md` (this file)
- `/workspace/.vs/cycle-1/diff.patch` (generated)

`site/site-check.mjs`, `site/src/pages/index.astro`, and everything else are
untouched.
