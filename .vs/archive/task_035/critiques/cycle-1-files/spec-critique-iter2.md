# Spec Critique — task_035, cycle 1, iteration 2

Both BLOCKING items are resolved: AC10 now decides open-stdin survival via AC4's single targeted spawn (60s bound), leaving the full-suite run to the `< /dev/null` (safe-direction) clause only; AC6 names `checks_11`'s `test_gh_meta_rate_limit_and_cache_fallback` as the offender and mandates `ast.walk`-based `Call`/keyword detection. All three MINORs are resolved: AC5 requires a per-call-unique `GH_META_CACHE` (builder-issued or `_fw_run`-overridden-after); AC9 explicitly keeps `site/.gitignore`'s three un-anchored lines rather than treating them as duplicates; AC3 mandates AST parsing with the floor raised to 40 (comfortably under today's 48).

## Concerns

1. **AC6 — new ambiguity, "routed through" is undefined for AST.** The lint must decide whether an `env=` keyword's *value* was produced by `_isolate_extras_env`/`_fw_run`, not just whether that name appears somewhere in the function. Real call sites build `env` incrementally (`env = {**os.environ, ...}` then later `env["X"] = ...`, or `env = _isolate_extras_env({...})` then a post-override) — the spec doesn't say what counts as "routed through" for the walker (assignment-target tracing? call-adjacency? textual co-occurrence?). An under-specified rule here risks exactly the false-positive/false-negative pair AC3 was tightened to avoid, just one level indirected through data flow instead of keyword presence. Suggest the spec pin a concrete, checkable rule (e.g., "the `env=` argument's originating assignment must itself be, or start from, a call to `_isolate_extras_env`/`_fw_run`").

2. **AC10 — minor, full-suite decisive check has no timeout accommodation.** `python3 smoke-test.py < /dev/null` remains a decisive check, and CLAUDE.md's own text plus the spec's cycle-1 estimate put this at 4–25 minutes under load — potentially exceeding the Bash tool's 600s hard cap for reasons unrelated to correctness. The spec doesn't direct the Tester to run this in background or otherwise budget for it.

## Verdict

**ship** — no blocking issues; concern 1 is worth a one-line spec tightening but not cycle-blocking, concern 2 is procedural.
