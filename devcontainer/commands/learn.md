# /learn - capture a cross-org learning into /learnings

## What this does

`/learn <pattern>` captures a cross-org learning entry into `/learnings/` using
the same filename and body format as the host-side `vibe learn` command. Because
a PreToolUse hook guards every write to `/learnings`, you will see a permission
prompt before the file is created - this is by design and is the security boundary.

`/learn --review` is the other half: a periodic hygiene pass over the whole
library - cluster, then propose removals, consolidations, edits and precedence
fixes one at a time, each gated by its own confirm. See
[§ Library review](#library-review---review).

## Usage

```
/learn <pattern>
/learn --review
```

`<pattern>` is the learning you want to capture. It can be multi-line - embedded
newlines pass through to the body as-is.

`--review` is recognised ONLY when it is the entire argument. `/learn --review
plus some other words` is ambiguous - is `--review` a flag, or the opening words
of a pattern? Ask which was meant and do nothing until the user answers; never
guess. A pattern whose text genuinely begins with `--review` has to be
rephrased.

## How it works

When `/learn <pattern>` is invoked, the model:

1. **Checks that `/learnings` exists as a directory.** If it does not, responds
   with the following message and stops - no Write is issued:

   ```
   /learn: /learnings is not mounted (run 'vibe learn --init' on host first)
   ```

2. **Computes the filename components** using:

   ```bash
   ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   rand=$(python3 -c 'import binascii,os; print(binascii.hexlify(os.urandom(3)).decode())')
   ```

   The full file path is: `/learnings/${ts}-${rand}.md`

3. **Formats the entry body** matching the host-side `learning_format_entry`
   output exactly:

   ```bash
   printf '# %s\n\n%s\n' "$ts" "$pattern"
   ```

   That is: a `# <timestamp>` header line, a blank line, the pattern body,
   and a single trailing newline. (For grep-able regression-test purposes:
   the entry begins with a `# <timestamp> header line`, then blank line, then body.)

4. **Runs the semantic check** — see [§ Semantic check](#semantic-check) below.
   This step runs on every `/learn` invocation before the preview or Write.

5. **Prints a preview** to the user showing the proposed file path and the
   complete entry body BEFORE issuing the Write tool call, so the hook prompt's
   context is clear.

6. **Issues a single Write tool call** to `/learnings/${ts}-${rand}.md` with
   the formatted body. The PreToolUse hook fires at this point and prompts you
   to confirm the write.

7. **After the Write succeeds**, informs you that the entry is saved locally,
   then tells you what (if anything) is needed to propagate it:

   - **If your library auto-syncs** (Dropbox, iCloud, a network share - the
     common private-mode setup): nothing to do. The file is already syncing.
   - **If your library is a git repo** (public visibility mode): pushing is
     host-only. The dedicated path is `vibe learn --push` on your Mac shell
     (note: `--push` is not built yet; it is a separate upcoming task that will
     resolve the library path and stage only the new entry for you).

   Until `--push` exists, push a git-backed library by hand from its own
   directory, staging only the new entry shown in the preview above:

   ```bash
   cd /path/to/your/learning-library && git add <new-entry-filename>.md && git commit -m "learn: <pattern>" && git push
   ```

   Stage only that one file - never the whole tree - and substitute the real
   library path. Do not paste a `VIBE_LEARNING_PATH` variable here: it is a
   container/config value, unset in your interactive Mac shell, so it would
   expand to nothing and `cd` you into `$HOME` (where a bare add-everything
   would stage your entire home directory).

## Semantic check

Before issuing the preview or Write, scan all existing /learnings entries to
detect contradictions and evaluate input quality. Marginal token cost per
invocation: 2-5k tokens. This check runs on every /learn invocation — always
runs regardless of library size, input length, or pattern complexity.

**Input quality gate:** if the new pattern is low-quality input (vague
reference, unclear input, or obvious nonsense), flag the issue and present
options even when no contradiction is found.

**Zero friction for already-good input:** when the new pattern is already
efficient, clear, and non-contradictory, apply it directly — zero friction,
no options surfaced to the user.

**When improvement is possible**, present the option scheme:

- **Z1** is always the user-verbatim original. Z1 is ALWAYS the verbatim
  user input, unchanged. Z1 is ALWAYS the opt-out from any rewrite.
- **Z2** (and optionally **Z3**) are smarter alternatives Claude constructs.
  Cap n at 3 total Z-options (1 or 2 alternatives is typical, no more than 3);
  never generate exhaustive lists.
- When a contradiction with an existing entry is detected, offer an option to
  edit an existing contradicting entry rather than add a new file. Omit this
  option when no contradiction exists.
- **N** — drops the new capture entirely; no Write is issued; existing
  entries are unchanged; the user may cancel and start over.

**Hook and preview context:** the preview still comes BEFORE the Write so the
PreToolUse hook prompt has clear context about exactly what will be written.

## Multi-line patterns

Multi-line patterns are supported. Newlines in the pattern body pass through
unchanged into the learning entry file. Example:

```
/learn use a plain ASCII hyphen ` - ` for parentheticals
and separators, not en or em dashes - keyboards only have hyphens.
```

## Library review (`--review`)

`/learn --review` is a **periodic library hygiene pass**, not a normal-session
command. It reads every entry in `/learnings`, clusters them by topic, and walks
the user through one proposed change at a time. It is deliberately heavyweight:
it pulls the whole library into context (budget a few hundred tokens per entry
plus clustering - a 40-entry library is roughly a 20-40k token pass; that is an
estimate, not a measurement) and it runs over many turns. Run it when the
library is due (see [§ When a review is due](#when-a-review-is-due)) - a handful
of times a year, deliberately, not as a warm-up to a capture.

Plain `/learn <pattern>` is untouched by any of this: capture still runs its
semantic check and still writes exactly one entry.

### Step 0 - preconditions

1. **Check `/learnings` exists as a directory.** If it does not, respond with
   the same message the capture path uses and stop - no read, no Write:

   ```
   /learn: /learnings is not mounted (run 'vibe learn --init' on host first)
   ```

2. **Count the entries:**

   ```bash
   ls -1 /learnings/*.md 2>/dev/null | wc -l
   ```

3. **Bail on a library too small to review.** Fewer than 5 entries: say so with
   the actual number and stop, no proposals, no writes - "the library has 3
   entries; there is nothing for a review pass to find yet. Capture a few more
   first." Zero entries (mounted but empty) gets the same treatment, worded for
   an empty library. This is a clean stop, not an error.

4. **State the cost and get one go-ahead.** Tell the user the entry count, the
   rough token budget, and that the pass is multi-turn, then ask whether to
   start. This is the only confirm in the whole pass that does not mutate
   anything; every later one does.

### Step 1 - read the whole library

```bash
for f in /learnings/*.md; do printf '\n===== %s =====\n' "$f"; cat "$f"; done
```

Read-only - no hook fires, nothing is written. Hold each entry's filename (its
capture timestamp is its only provenance) alongside its body for the rest of the
pass.

### Step 2 - cluster by topic

Cluster on meaning, not on shared words. Two entries about the same behaviour
belong together even when they share no vocabulary ("no em dashes" and "use a
plain ASCII hyphen for separators"); two entries that share a word but not a
subject do not. Keyword matching alone is not sufficient here - it is the reason
this pass needs a model and not a script.

Present the cluster map BEFORE any proposal: each cluster's name, its members
(filename plus a one-line gist), and a single "no action" list for entries that
are fine as they are. Then say how many proposals are coming and in what order -
highest-overlap clusters first - so the user knows the size of what they have
started before the first y/n.

### Step 3 - propose one change at a time

Each proposal is a single atomic decision: what changes, why, the exact effect
on disk, then a y/n. Never bundle two proposals into one question. Never offer
"apply all", "apply the rest", or any other batch. The four kinds:

- **Remove** - the entry no longer adds value: superseded by a later entry,
  describing a tool or workflow that no longer exists, or a one-off that never
  generalised. Quote the entry in full in the proposal; a removal is
  irreversible from in here.
- **Consolidate** - several entries cover one topic with overlap or drift.
  Propose the merged body verbatim, name every source entry that would be
  deleted, and treat the whole merge as ONE decision (write the merged entry,
  then delete its sources). If the user wants to keep one of the sources, that
  is a `n` - re-propose a narrower merge rather than negotiating mid-apply.
- **Edit** - the pattern is right but the phrasing is unclear, buried, or
  ambiguous. Propose the rewritten body verbatim, keeping the file (and so the
  capture timestamp) exactly where it is.
- **Precedence** - the entry is sound but hard to find or hard to act on. See
  [§ Precedence](#precedence-what-re-ordering-actually-means).

Answers: `y` applies it now; `n` skips it permanently for this pass - move to
the next proposal, never re-ask, never re-word the same proposal to try again;
`q` / `stop` / `abort` ends the pass (see [§ Aborting](#aborting-and-close-out)).
Anything else is not a yes: restate the proposal once, and if the next answer is
still not a clear yes or no, stop the pass and ask the user what they want.

### Step 4 - apply, one write per decision

Before applying, re-check that the target files still exist and still hold the
content that was presented. The library can be edited by another vibe container
or resynced by Dropbox/iCloud mid-pass. If a target has moved under you, drop
that proposal, say so, and continue - never apply to content you did not show.

- **Remove** - one file per command, absolute path, never a glob and never two
  removals in one command:

  ```bash
  rm '/learnings/2026-04-23T09:24:19Z-346594.md'
  ```

- **Consolidate** - compute a fresh filename exactly as the capture path does
  (`ts` and `rand` per [§ How it works](#how-it-works) step 2), Write the merged
  entry in the standard `# <timestamp>` + blank line + body shape, and end the
  body with a plain provenance sentence naming what it replaces, e.g.
  `Consolidated 2026-08-27 from entries captured 2026-04-23T09:24:19Z and
  2026-05-02T14:10:55Z.` Then remove each source file with its own `rm`. Do not
  invent a front-matter block or a machine-readable field for this - nothing in
  vibe parses one, and the library's format is a heading plus prose.
- **Edit** - a single Edit tool call against the file, touching the body only.
  Never rewrite the `# <timestamp>` header line and never rename the file: that
  timestamp is when the pattern was learned, and it is the entry's only
  provenance.

**Two gates, and they are not the same gate.** The y/n above is the user
deciding the change is right. The permission prompt that follows is the
PreToolUse hook (`guard-fs.sh` for Write/Edit, `guard-bash.sh` for `rm`)
confirming the file operation. Both must be satisfied. A denied hook prompt is a
`n` for that proposal: record it as not applied, do not retry the write, do not
reissue it in another shape, and move on. Never combine writes to reduce the
number of prompts, and never route a write through an interpreter or an
indirect path to avoid one - the hook is the security boundary, not friction.

### Precedence (what "re-ordering" actually means)

The original design called for "frequently-applied patterns first, to bias
future greps". Be honest about the mechanism: entry filenames are capture
timestamps, a shell glob sorts them oldest-first, and `grep -r` returns them in
whatever order the directory yields. There is no priority slot to move an entry
into, so renaming a file to "promote" it would falsify its capture date and
still change nothing about what a future session finds.

What actually decides whether a pattern wins a future read:

- **Lead with the rule.** `grep` prints the matching line. An entry whose first
  body line is the imperative rule in one sentence is actionable straight out of
  a grep hit; one that opens with backstory hides the rule below the fold.
  Propose this as an Edit.
- **Make it findable.** Add the words a future session would actually search
  for - tool names, filenames, error strings, the obvious synonyms. An entry
  nobody can find has no precedence at all, wherever it sits.
- **Collapse the topic to one file.** Five entries on one topic means five
  partial hits a reader has to reconcile; one merged entry is the single
  authority on it. This is the real precedence win, and it is just the
  Consolidate move above.

Re-timestamping happens only as a side effect of a consolidation - a merged
entry genuinely is written today, and its body records the dates it replaces.
Never rename an otherwise-unchanged entry to move it in a listing.

### When a review is due

At the end of a completed pass, offer (its own y/n, its own hook prompt) to
write a receipt at `/learnings/.last-review`:

```
reviewed: 2026-08-27T11:04:12Z
entries: 41
```

A dotfile, so it never matches the `*.md` globs the library's readers use. It is
optional - decline it and nothing else about the pass changes. A library due for
review is one where any of these holds: 30 or more entries, more than 90 days
since the `reviewed:` line, or more than 5 entries captured since it. A missing
receipt means "never reviewed", not an error. That is the contract a launch-time
"due for review" hint reads; keep the two lines and the filename stable.

### Aborting and close-out

`q` / `stop` / `abort` at any prompt ends the pass immediately - no further
proposals, no further writes, no "are you sure". There is no saved half-state; a
later `/learn --review` re-reads the library from disk and re-clusters from
scratch.

Whether the pass finished or was aborted, close with a summary:

- entries created, edited and removed, each by filename;
- proposals skipped or denied, in one line each;
- clusters not reached, if the pass was cut short.

Then say what is needed to propagate the changes, as the capture path does. An
auto-syncing library (Dropbox, iCloud, a network share) needs nothing - note
that removals sync too, and the only undo is the sync provider's version
history. A git-backed library is host-only: from the library's own directory,
stage exactly the files named in the summary and nothing else, substituting the
real path -

```bash
cd /path/to/your/learning-library && git add -- <new-entry>.md <edited-entry>.md && git rm -- <removed-entry>.md && git commit -m "learn: review pass" && git push
```

For a library that is not in git and not auto-syncing, say plainly that removals
are gone once applied - and say it before the first removal proposal, not in the
summary.

## Security note

The `/learnings` bind-mount is read-write on macOS regardless of the `readonly`
flag in the devcontainer config (Docker Desktop / OrbStack `fakeowner` quirk).
The PreToolUse hook on Write/Edit/MultiEdit tool calls is the security boundary -
it intercepts every write under `/learnings` and requires your explicit confirmation.
Do not bypass the hook prompt.
