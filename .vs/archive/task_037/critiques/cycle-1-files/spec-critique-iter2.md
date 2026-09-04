# Spec Critique — iteration 2 — task_037 (`/vs --TDD`)

## Concerns

All four BLOCKING items from iteration 1 are resolved:

1. **Independence-rule carve-out** — AC3 now requires an explicit exception sentence on Step 5a's independence rule (`under `--TDD` the Tester additionally reads `tdd-trail.md` and `diff.patch` — only to check the trail, never the Generator's report`) AND the same carve-out (`except the `--TDD` trail check`) on the Rules bullet. Both anchors (line 269, line 432) confirmed present and compatible with the added clause. Resolved.
2. **AC4 anchor** — spec's quoted old sentence now reads `` `--TDD` (when implemented) governs Step 4 only. `` with the backtick placed exactly as in the live file (verified byte-for-byte against vs.md line 249). Resolved.
3. **Per-entry `written:` timestamp** — AC2 requires an ISO-8601 `written:` field per entry; AC3 requires comparing it to the scratch file's mtime, explicitly labelled `a weak proxy, not proof`. Resolved.
4. **Summary line count** — AC3 amends the Step 5a sentence to `a 3-line summary (4 lines under `--TDD`: a `TDD trail:` line is appended)`. Resolved.

MINORs (coherence check, panel sentence, fail-line framing) all present in AC3/AC7/AC8 as required. Resolved.

**New weakness (MINOR):** the entry shape uses `|` as a field delimiter (`AC<n> | test file | command | exit | failing assertion | written:`), but a real test-run `command` can legitimately contain a pipe (e.g. `pytest test_foo.py | tee log`), which breaks naive field-splitting for the Tester's mechanical "command names the same file as test file" check. Worth a one-line note that `command` must not itself contain `|`, or that splitting is on the first/last delimiters only.

**New weakness (MINOR):** if one scratch test file backs multiple AC entries, all those entries share one mtime, so the written-vs-mtime ordering check can't distinguish which entry the mtime actually corresponds to — an acceptable gap given "weak proxy" is already disclaimed, but worth one clause acknowledging it.

## Verdict

**pass** — all prior BLOCKING and MINOR items resolved; the two new items are minor hardening suggestions, not blockers.
