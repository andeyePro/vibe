# Spec Critique — task_032 (iteration 2)

## Concerns

1. **Resolved (AC9).** `const COPY = {...}` preservation is now explicit and pinned to `id="cast"`. No issue.

2. **Resolved (AC4).** Chip markers + `<chip>:<n>` step markers now cover per-item ticking, with a stated count (`n = 1..len(checklist)`) and a cast-side `"m"` event requirement. Resolves the prior contradiction.

3. **Resolved (AC11, Test location).** AC11 is now explicitly Tester-owned in `site-check.mjs` with concrete literal assertions (option strings, `IntersectionObserver`, dynamic `import(`, `seek({marker`, load-before-click wiring). No mechanical-owner gap remains.

4. **Resolved (AC8/AC12).** `build` now runs `node scripts/vendor-player.mjs && astro build` and `check` runs `npm run build && node site-check.mjs`, so vendoring fires on the actual gate path. The `prebuild`-doesn't-fire-for-`check` reasoning is gone (it's now inlined into `build` directly, cleaner than relying on the lifecycle hook at all).

5. **Resolved (MINOR, AC10).** Structural guards (`.term-body` clamp, exact-13-chips, `stepsContiguous`) are now named alongside the inBoth guards, with the Tester required to list any that changed.

6. **MINOR (AC11 robustness).** `controls:false` / `poster:"npt:0:0"` / etc. are specified as literal-string matches against "the emitted script." Astro's build may minify/bundle the inline script (e.g. via esbuild), which can reorder object keys, strip quotes from identifier-like keys inconsistently, or collapse whitespace in ways a plain string search still survives — but a minifier could also rewrite `controls:false` to `controls:!1` under aggressive optimization, or the key could get renamed if it's not treated as a string literal in an object passed to an external API. Worth a one-line steer to the Tester: match with a whitespace-tolerant regex (`/controls\s*:\s*false/`) rather than an exact substring, and confirm in a Generator/Tester round whether Astro's inline-script minification is even active for this project (if not, drop the concern). Low severity since it's self-correcting within the cycle if the Tester's first assertion fails against real output.

7. **MINOR (markers.json `label`).** AC4 requires `label` = the id for every entry, which is redundant with `id` itself (no consumer use of `label` is specified anywhere — chip click and marker-tick logic are described as using `id`/`time`). Harmless but dead weight; not blocking, could be dropped or left as a self-documenting cast-viewer convenience (asciinema-player's own marker overlay does display `label` text, which likely IS the reason — leave as-is, not a real defect).

8. **Non-blocking note.** Step-marker synthesis for the *placeholder* cast (`make-placeholder-cast.mjs`) isn't explicitly told to emit `<chip>:<n>` markers per checklist item, only AC4 constrains the final `markers.json` shape. Confirm the placeholder synthesiser is in scope for step markers too, not just chip markers — likely already implied by AC1/AC4 but worth the Generator not missing it.

## Verdict
**pass**
