# Spec critique — task_039 `/review`

## Concerns

1. **AC3, BLOCKING.** The literal `| no |` check will likely fail against real markdown. Table cells get padded for column alignment (e.g. `| enabled |` header forces `| no      |` in the body), so the raw file text often isn't the exact substring `| no |`. Use a regex (`\|\s*no\s*\|`) or drop the pipe-delimiters from the literal and just require the word `no` in that cell's row.

2. **AC7, BLOCKING.** README has no single "command list" section to grep. Commands are documented two ways: named in a passing intro sentence (line 12: `/sp`, `/vs`, `/vss`, `/vsss`, `/wide`, `/narrow` — but not `/budget`, `/c`, `/learn`, `/repo`) or given their own standalone prose paragraph elsewhere (e.g. `/budget` at line 132). AC7 must say which pattern `/review` follows and give the Tester a concrete substring to check, or it isn't mechanically checkable as written.

3. **AC4, BLOCKING — missing output format.** No AC defines what a `/review` run actually prints. Without pinning a schema (e.g. reuse `/vs`'s reviewer-verdict three sections: per-criterion assessment / concerns / verdict), the Generator can invent an ad hoc report and nothing catches it. Add a literal AC for the output block shape.

4. **AC2, MINOR — invocation mechanism unstated.** Nothing requires review.md to literally instruct the chair to call `Skill(skill: "code-review", args: "<level> [target]")`. Without that literal, a Generator could hand-write review logic instead of actually invoking the built-in skill, defeating the task's premise. Add the literal Skill-tool call form as a required substring.

5. **AC5/AC6, worth a recommendation (asked for one).** `--comment` writes outward to GitHub — same asymmetry class as push, which `/vss`/`/vsss`'s hard-escalate list forbids autonomously. AC5's opt-in gate is good but the spec never says whether `/review --comment` is itself hard-escalate material inside an autonomous `/vss`/`/vsss` run. Recommend one added line: "`--comment` is GitHub-outward like push; `/vss`/`/vsss` treat it as hard-escalate, never auto-fired." Silence here is a real gap since this ships alongside the `/vsss` safety floor.

6. **AC2, MINOR — `ultra` guard.** The `--level` enum already excludes `ultra`, but behaviour on `--level ultra` input is unspecified (silent clamp vs refuse). Add: "`/review` refuses `--level ultra` with one line pointing at the `code-review` skill directly."

7. **AC3, MINOR — stub honesty.** AC3's "no" values are mechanically honest, but they're buried in a table. Recommend one prominent top-level sentence in review.md itself (not just the registry): "today `/review` is Claude-only; fan-out has zero enabled slots." Protects a plain-English reader from missing the caveat in a table.

8. **AC9, MINOR — test-evasion gap.** `test_review_command_docs` asserts AC1–AC7 only; AC8 (TODO one-liner + CHANGELOG entry) is mechanically trivial to check but left untested, so a cycle could pass green without the doc-hygiene update actually landing. Fold AC8's literals in too.

9. **Word budget, MINOR.** 700 words is tight for AC3's padded table + AC4's four merge literals + AC5's four rule lines + AC6's three relation lines + (if concern 3 is adopted) an output-format block. `wide.md` (763 words) carries less literal-density and has no cap. Flag the risk; not fatal, but the Generator should be told to be terse from the first draft, not trimmed after the fact.

## Verdict

**Revise.** Concerns 1–3 are BLOCKING (untestable-as-specified or a real functional gap); 4–9 should be folded in this revision since they're one-line additions, but wouldn't alone hold up approval.
