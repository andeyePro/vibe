# /learn - capture a cross-org learning into /learnings

## What this does

`/learn <pattern>` captures a cross-org learning entry into `/learnings/` using
the same filename and body format as the host-side `vibe learn` command. Because
a PreToolUse hook guards every write to `/learnings`, you will see a permission
prompt before the file is created - this is by design and is the security boundary.

## Usage

```
/learn <pattern>
```

`<pattern>` is the learning you want to capture. It can be multi-line - embedded
newlines pass through to the body as-is.

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

7. **After the Write succeeds**, informs you that the entry is saved locally.
   Pushing to git (for public-mode libraries) is host-only - run:

   ```bash
   vibe learn --push
   ```

   on your Mac shell when ready (note: `--push` is not yet built; it is a
   separate upcoming task). Alternatively, push manually:

   ```bash
   cd $VIBE_LEARNING_PATH && git add . && git commit -m "learn: <pattern>" && git push
   ```

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

## Security note

The `/learnings` bind-mount is read-write on macOS regardless of the `readonly`
flag in the devcontainer config (Docker Desktop / OrbStack `fakeowner` quirk).
The PreToolUse hook on Write/Edit/MultiEdit tool calls is the security boundary -
it intercepts every write under `/learnings` and requires your explicit confirmation.
Do not bypass the hook prompt.
