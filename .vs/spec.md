# spec — task_003: prize-worthy haiku about vibe (FUZZY MODE)

## Task summary

Produce one English haiku (5/7/5 syllable form) about vibe — a single-command containerised YOLO Claude Code environment — that could plausibly win an English-language haiku prize. The haiku will land at repo root as `HAIKU.md` so it's a committed, visible artifact, but it must read as a haiku to anyone, not as a project tagline. Mode: `--fuzzy` (no mechanical tests; Sonnet Reviewer judges).

## Acceptance criteria

1. Three lines, **5 / 7 / 5 syllables** in standard English count. Reviewer counts carefully (with attention to edge cases like "fire" vs "fi-er", "every" vs "ev-ry").
2. Contains a recognizable **kireji-style pivot** — a cut or turn between the first section (line 1 or 1+2) and the last section. Not a continuous descriptive sentence.
3. Has **concrete sensory imagery** — at least one observable detail (sound, sight, motion, texture). No purely abstract nouns like "code", "container", or "session" used naked.
4. **Evokes vibe's essence by image, not by explicit naming.** Vibe's essence has four elements: (a) isolation / a small bounded space, (b) the presence of a non-human collaborator, (c) one-gesture summoning / single-command launch, (d) safety / sandboxing / what's outside cannot enter. The haiku must evoke **at least two of the four** for AC4 to pass; Reviewer states which two (or more) and why.

   **Banned words** (case-insensitive, including stems and hyphenated forms): `vibe`, `Claude`, `container`, `docker`, `AI`, `LLM`, `model`, `agent`, `sandbox`, `isolate` (and `isolation`, `isolated`), `deploy`, `launch`, `build`, `fork`, `repo`, `commit`, `runtime`, `daemon`, `shell`, `terminal`. The poem must work without any of these. Acceptable poetic vocabulary includes (but is not limited to) `door`, `room`, `key`, `garden`, `wall`, `lantern`, `whisper`, `voice`.
5. Has an **"ah" moment** — a turn or juxtaposition that creates resonance, not just clever wordplay or punning.
6. **Stands alone** — readable as a poem to a haiku-prize judge who has never heard of vibe, Claude Code, or coding agents. The poem should not require footnotes.
7. **Original** — not a substantively-known haiku (Bashō, Issa, etc.) with software words swapped in.
8. **Exactly one haiku, file-byte-strict.** `HAIKU.md` contains exactly three non-empty lines of text, each terminated by a single `\n`, plus an optional final trailing `\n`. **No** YAML front matter (`---` block), **no** HTML comments (`<!-- ... -->`), **no** title, **no** author, **no** dedication, **no** code fences, **no** blank lines between the three lines, **no** explanatory text before or after. The file's total non-whitespace content is the three haiku lines and nothing else.

## Out of scope

- Tanka (5/7/5/7/7), senryū framing, free verse.
- Multiple candidates ("here are three options").
- Author name, title, dedication, or any framing text in `HAIKU.md` beyond the three lines themselves.
- Commentary or "what this means" notes inside `HAIKU.md`.
- Image / ASCII art.
- Any other repo file changes (no README edit, no TODO entry, no CLAUDE.md note — Planner / Evaluator handle TODO and progress.md outside Generator's diff).

## Review focus

- **Syllable count exactness** — count each line separately. Flag anything that requires elision tricks.
- **Concrete vs smuggled-abstract imagery** — does line 1 actually show something, or is it dressed-up jargon?
- **Pivot integrity** — does the turn earn its keep or feel grafted on?
- **Non-vibe-reader test** — read it as if you've never heard of vibe. Does it still work as a poem? If it only works for an insider, it fails AC6.
- **Banned-word audit** — confirm none of the AC4 banned words appear (case-insensitive, stem-aware). Flag any near-miss that smuggles the same meaning by synonym.

- **File-byte audit** — open `HAIKU.md` and confirm exactly three non-empty lines, no front matter, no HTML comments, no surrounding text. AC8 is mechanical — easy fail to catch.

## Proposed budget

**2 cycles.** Generator writes one candidate; Reviewer judges. If the candidate falls short on 1–2 criteria, cycle 2 revises. A haiku doesn't deserve 3 cycles — if it can't land in two it probably can't land in this harness.
