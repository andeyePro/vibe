# Spec — task_030: everyday-launch hero deck (site content) + first-time / quarterly chips

## Task summary
vibe.andeye.com's journey deck (`site/src/content/home.md` frontmatter `journey.groups`) opens with a FIRST launch: PAT prompt, image build, the other chips locked until it runs. That is the worst everyday advert — a fine-grained PAT is set once per expiry (90-day default, `vibe pat` rotates in place, no rebuild) and Claude sign-in is rarely repeated. Rework the deck content: the hero Launch chip becomes the everyday reused-container launch (banner exactly as the launcher prints it, firewall verification, sign-in already valid, ready); a demoted "First time" group carries the moved PAT + image-build lines verbatim; a "Once a quarter" chip shows `vibe pat`. `site-check.mjs` is the mechanical test surface: the Tester rewrites its launch guards; the Generator edits `home.md` only. Not in this task: the asciinema pipeline (roadmap item 3b, next iteration). Baseline commit: 8305ab3.

## Acceptance criteria (all checked against the built `site/dist/index.html` unless stated)
- AC1 `journey.groups` in `home.md` contains, after the existing hero Launch group, a group titled `First time` with one chip `id: first-launch` and a group titled `Once a quarter` with one chip `id: pat`; total chips = 13 (`data-step="` occurrences in the built HTML) and `<ol class="steps">` count === chip count. The hero chip keeps `id: launch`; `journey.locked_note` is unchanged; no server-rendered `class="dstep locked"`.
- AC2 The built HTML contains `id="step-launch"`, `id="step-first-launch"`, `id="step-pat"`.
- AC3 Launch chip banner quotes the launcher in the launcher's own order (`project`, `path`, `github`, `hooks`, `extras` — vibe:~3691-3695; the `path    : ` line is NEW content, not present on the current deck, and must sit between project and github): each of `🚀 vibe session starting`, `project : `, `path    : `, `github  : `, `hooks   : tool-call guards + idle bell`, `extras  : /diet · /feast · /vs · shellcheck-fixer · security-review` appears in the built HTML AND in `/workspace/vibe` (site-check's `inBoth` after its `norm()` dash-folding; the Tester confirms each string's exact form in the launcher first and may adjust spacing to the launcher's actual output).
- AC4 Launch chip keeps the firewall pin `Firewall verification passed - unable to reach https://example.com as expected` (inBoth vs `devcontainer/init-firewall.sh`), a sign-in line containing `your Claude subscription` (this line is descriptive site copy, NOT a launcher quote — vibe prints nothing about an already-valid Claude sign-in; the copy must not pretend to be tool output, e.g. render it as a checklist/tone line rather than a terminal line), and a ready line; its checklist contains `short allowlist`.
- AC4b The current launch checklist bullet 1 ("finds your project and its GitHub remote, then asks once for a fine-grained PAT – scoped to that one repo") is split: the everyday Launch chip keeps only the repo-discovery half (e.g. "finds your project and its GitHub remote, and reuses the PAT you set once"); the PAT-prompt half moves to the first-launch chip's checklist.
- AC5 Scoped negatives: within the `step-launch` chip's HTML block and within the `launch` entry of the embedded lines map, none of `fine-grained PAT`, `Token saved`, `Building vibe container image`, `Only select repositories`, `sandboxed container` appears. (Whole-page absence is NOT required — these strings legitimately appear on other chips.)
- AC6 First-launch chip carries, each pinned by inBoth vs `/workspace/vibe`: `No GitHub token found for`, `Only select repositories`, `Token saved - you won't be asked again for this repo`, `Building vibe container image`; its checklist mentions `fine-grained PAT` and `sandboxed container`.
- AC7 `pat` chip has `cmd: vibe pat` and lines pinned by inBoth vs `/workspace/vibe`: `90 days is a good default` and `Takes effect on the next vibe launch (no rebuild needed)` (Tester verifies the exact launcher wording and pins what is actually there).
- AC8 Every chip's `step: N` values are contiguous 1..len(checklist) for that chip (the launch chip is renumbered after its PAT/build lines move out); site-check asserts this from the embedded lines map, INCLUDING `tone` lines (they carry `step` today, e.g. the curl/leak chips' `tone: fail` line has `step: 1`).
- AC9 All pre-existing site-check guards not about the launch checklist still pass unchanged (red-team, Radicle, /vss, /vsss, /budget, /c, no raw email, viewport-bounded terminal, CTA hrefs).
- AC10 `cd /workspace/site && npm run check` exits 0 with the Tester's rewritten guards; `npm run build` alone exits 0 on the Generator's deck before the Tester runs.
- AC11 Scope lock (cycle-time, chair-verified, not a permanent test): changes only in `site/src/content/home.md`, `site/site-check.mjs`, `CHANGELOG.md`, `TODO.md`, `.vs/`, `.vss/`. `site/src/pages/index.astro` is NOT edited (its lock gate keys on `step-launch`, which is kept).
- AC12 Copy accuracy beyond the pins (Evaluator reads the whole Launch chip holistically — a paraphrased first-launch implication such as 'asks permission for your repo' fails this AC even though AC5's literal bans pass): no line on any chip claims something the launcher does not do (Evaluator-read); the everyday Launch chip must not show a PAT prompt, a build, or a sign-in prompt — sign-in is shown as already valid.

## Known limitation (not a defect of this task)
index.astro's lock gate is `d.id !== 'step-launch'`, so the new `first-launch` and `pat` chips render locked until Launch is clicked once, though they describe things that precede it; index.astro is out of scope here (roadmap item 3b may drop the gate).

## Out of scope
- The asciinema recording/player pipeline, `site/demo/*`, any new dependency, any change to `index.astro`, CSS, or the deck's JS driver.
- Rewording the other groups (Build / Red team / Ship / Also in the box) beyond nothing.
- Branding (Vibe&I) — separate Martin decision.
- Permanent site-check assertions that pin whole-page absence of strings that other chips legitimately use.

## Test location
`site/site-check.mjs` — Tester-owned. The Tester rewrites the launch-checklist guard into an everyday-launch guard + a first-launch guard, adds chip-presence guards for `step-first-launch` and `step-pat`, an inBoth guard for the `vibe pat` expiry copy, a `chipBlock(id)` helper that extracts the chip's block attribute-agnostically — Astro injects `data-astro-cid-*` after the id, so match `id="step-<id>"[^>]*>` and take the text up to the chip's closing `</div>` (or the next `id="step-`), never a literal `id="step-<id>">` and a scoper for the embedded lines map entry, and a contiguous-`step:` check. Generator edits `site/src/content/home.md` only (plus CHANGELOG.md) and must not touch `site-check.mjs`.

## Proposed budget
3 cycles.

## Model plan
- Planner + Evaluator: session model (Fable 5.1 chair).
- Spec Critic: sonnet.
- Generator: sonnet, ceiling opus (verbatim launcher quoting + YAML deck structure).
- Tester: sonnet (writes JS guards, not mechanical greps), ceiling opus.
- Fable rung: pre-authorised (--fable-subagents, user prose grant), not indicated.
