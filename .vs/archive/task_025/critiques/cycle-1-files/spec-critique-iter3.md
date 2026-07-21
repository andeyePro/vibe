# Spec Critique — task_025 (cycle 1, iteration 3)

Verdict: **pass**

## Resolution check (iter-2 BLOCKING concern)

Iter-2 flagged three IndexError-or-silent-wrong-answer paths in the interpreter-resolution algorithm: `#!/usr/bin/env` alone, `#!/usr/bin/env -S bash -x` (misclassified `False` instead of `True`), and bare `#!`. The revised "Named shebang predicate" bullet now reads: zero-token guard first (`[]` after split → `False`, covers bare `#!` and whitespace-only `#!   `); then `first = basename(tokens[0])`; if `first != "env"` → literal interpreter; if `first == "env"` → scan `tokens[1:]` for the first token not starting with `-`, basename it, and `False` if none exists.

Hand-traced all four AC2 degenerate cases against this text:
- `#!/usr/bin/env -S bash -x` → tokens `["…/env","-S","bash","-x"]`, first="env", scan `tokens[1:]`: `-S` skipped (starts with `-`), `bash` taken → `True`. Matches AC2.
- `#!/usr/bin/env` alone → tokens `["…/env"]`, first="env", `tokens[1:]` empty, no non-`-` token found → `False`. Matches AC2. No IndexError (empty-list scan doesn't index).
- bare `#!` → remainder `""` → zero tokens → `False` via the explicit zero-token guard, before `tokens[0]` is ever read. Matches AC2. No IndexError.
- `#!   ` (whitespace-only) → remainder `"   "` → whitespace split (either `.split()` or `.split(' ')` variant — both converge to the same outcome here, see note below) → zero or empty-string tokens → `False` either via the zero-token guard or via an empty-string basename never matching the whitelist. Matches AC2.

All four previously-blocking paths are now guarded before any indexing occurs, and the algorithm's stated result matches AC2's expected value in every case, including the previously-wrong `-S bash -x` → `True`. The BLOCKING concern is resolved. No regression to the seven iter-1 items (already closed in iter-2, untouched by this revision).

**Split-whitespace note (verified non-issue):** the spec says "split the remainder on whitespace" without pinning `.split()` vs `.split(' ')`. These differ on empty/whitespace-only input (`.split()` → `[]`, `.split(' ')` on `""` → `['']`), but the divergence is inert: an empty-string token's basename is `""`, which is never in the whitelist and never equals `"env"`, so both interpretations land on `False` for every AC2 case. Not a live ambiguity — no action needed.

## New adversarial pass (fresh, on the revised text only)

No new blocking findings. One non-blocking internal-consistency gap, newly introduced by this iteration's fix text itself:

- **Prose/mechanical-rule mismatch on bundled `-S<command>`.** The descriptive sentence says the algorithm should, "for `-S`/`--split-string`, treat the rest of that same token if it bundles the command" (i.e. extract `bash` out of a single bundled token like `-Sbash`). The immediately following "concretely" restatement — the operative, mechanically-testable rule, and the one a Generator will actually code against — is simply "take the FIRST token in `tokens[1:]` that does not start with `-`." That rule has no mechanism to look inside a `-`-prefixed token; it would skip `-Sbash` entirely like any other flag. For input `#!/usr/bin/env -Sbash -x` (bundled, no space — a real GNU-getopt-legal form, though not the form GNU env's own docs use in shebang examples), the "concretely" rule yields `False` for a script that is genuinely bash, contradicting the prose's promise. This is a spec self-contradiction, not a crash risk (`False` is a safe, non-raising answer) and not AC-relevant — no AC2 case exercises a bundled `-S<cmd>` token, only the spaced form `-S bash -x`, which both the prose and the concrete rule agree gives `True`. Since Generator builds to the labeled-operative "concretely" clause and Tester's AC2 doesn't touch the bundled form, this won't cause a build failure or Generator/Tester divergence on any tested input. Recommend tightening the prose (drop the bundled-token sentence, or fold it into the concrete rule) for spec hygiene, but not blocking.

## Minor / trivia carried forward (unchanged, not re-litigated)

The two iter-2 minor items (unbounded `readline()` on a truly binary no-newline file; trailing-slash interpreter path `#!/bin/sh/` → `False`) stand as previously assessed — not blocking, no new interaction with this iteration's changes.
