# /learn — capture a cross-org learning into /learnings

## What this does

`/learn <pattern>` captures a cross-org learning entry into `/learnings/` using
the same filename and body format as the host-side `vibe learn` command. Because
a PreToolUse hook guards every write to `/learnings`, you will see a permission
prompt before the file is created — this is by design and is the security boundary.

## Usage

```
/learn <pattern>
```

`<pattern>` is the learning you want to capture. It can be multi-line — embedded
newlines pass through to the body as-is.

## How it works

When `/learn <pattern>` is invoked, the model:

1. **Checks that `/learnings` exists as a directory.** If it does not, responds
   with the following message and stops — no Write is issued:

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
   and a single trailing newline.

4. **Prints a preview** to the user showing the proposed file path and the
   complete entry body BEFORE issuing the Write tool call, so the hook prompt's
   context is clear.

5. **Issues a single Write tool call** to `/learnings/${ts}-${rand}.md` with
   the formatted body. The PreToolUse hook fires at this point and prompts you
   to confirm the write.

6. **After the Write succeeds**, informs you that the entry is saved locally.
   Pushing to git (for public-mode libraries) is host-only — run:

   ```bash
   vibe learn --push
   ```

   on your Mac shell when ready (note: `--push` is not yet built; it is a
   separate upcoming task). Alternatively, push manually:

   ```bash
   cd $VIBE_LEARNING_PATH && git add . && git commit -m "learn: <pattern>" && git push
   ```

## Multi-line patterns

Multi-line patterns are supported. Newlines in the pattern body pass through
unchanged into the learning entry file. Example:

```
/learn Use env dashes (–) not em dashes (—).
Always surround en dashes with spaces.
```

## Security note

The `/learnings` bind-mount is read-write on macOS regardless of the `readonly`
flag in the devcontainer config (Docker Desktop / OrbStack `fakeowner` quirk).
The PreToolUse hook on Write/Edit/MultiEdit tool calls is the security boundary —
it intercepts every write under `/learnings` and requires your explicit confirmation.
Do not bypass the hook prompt.
