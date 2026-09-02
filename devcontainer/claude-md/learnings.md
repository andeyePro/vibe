# Learning library (`/learnings`): use, write hook, auto-promotion

`/learnings` is the user's cross-org learning library, mounted into every
vibe container by the host-side `vibe learn --init` setup. Each entry is a
Markdown file `<ISO timestamp>-<6 hex>.md`, body `# <timestamp>` then
free-form prose. Treat it as read-only from in here: entries are added with
`vibe learn "<pattern>"` on the Mac shell — host-only.

## When to consult it

Before cross-project-relevant work — coding style, tool preference, security
stance, naming or build convention, a recurring debugging pattern — check for
guidance: `ls /learnings`, `grep -r "<topic>" /learnings`, read the match. If
it applies, follow it; if unsure, ask the user first.

Do NOT consult it when `/learnings` does not exist (no `vibe learn --init`,
or opted out with a `.no-learn` marker) — it is opt-in, never surface its
absence as a concern; for project-specific facts already in `CLAUDE.md`,
`TODO.md` or repo docs, authoritative here; or for ephemeral session notes,
which belong in conversational memory.

To recommend an entry, tell the user: run `vibe learn "<short description>"`
on your Mac shell from any project directory. Never run it yourself.

## The write-confirm hook — do not bypass the hook

The mount is read-write despite the config saying `readonly` (Docker's
`fakeowner` overlay drops the flag, task_009), so trust comes from a hook.
`guard-fs.sh` is a PreToolUse hook on Write/Edit/MultiEdit: when `file_path`
resolves to `/learnings` or below it emits a `permissionDecision: ask`
envelope whose `permissionDecisionReason` names the path, and Claude Code
shows its standard prompt — yes proceeds, no blocks.

- No path traversal: it normalises with `realpath -m`, so
  `/learnings/../etc/passwd` is correctly seen as outside.
- Never split one logical write into smaller operations — every Write, Edit
  and MultiEdit call is checked independently.
- Never suggest disabling `guard-fs.sh`: a security boundary, not a
  convenience filter. Respecting it is not optional.

`guard-bash.sh` adds defence-in-depth over shell write idioms (`>`, `>>`,
`tee`, `cp`, `mv`, `rm`, `ln`, `mkdir`, `chmod`, `chown`, `truncate`, `dd`,
`sed -i`) — best-effort static matching, blind to variable-indirection
redirects, interpreter-embedded writes (`python3 -c`, `perl -e`, `node -e`)
and dynamic `eval`/`bash -c`. `guard-fs.sh` is the primary gate: it reads
`tool_input.file_path`.

`/learn <pattern>` is the recommended in-container path: verify the mount,
generate a host-format filename, preview the entry, then issue the Write that
triggers the hook prompt. Pushing is host-only and matters only for a
git-backed public-mode library (auto-syncing Dropbox/iCloud needs nothing).
`vibe learn --push` is the dedicated path, not built yet;
until it lands push by hand from the library's own directory, staging only
the single new entry file, never the whole tree. Never paste a
`VIBE_LEARNING_PATH` variable into a Mac shell: a container/config value,
unset there, it expands to nothing and lands you in `$HOME`.

## Auto-promote cross-repo feedback memories

Auto-memory is per-project, so a behavioural correction saved as a `feedback`
memory never reaches another project. On saving one, offer to promote it to
`/learnings`.

### When to propose promotion

Propose only when ALL four hold:

1. Behavioural or preference rule, not a project-specific fact.
   - YES: "don't use em dashes"; "lead with the literal command"; "never
     actuate hardware without per-action permission".
   - NO: "Aqueum's accountant is Jacquelene"; "the merge freeze begins
     2026-03-05".
2. Applies regardless of project: style, communication, anti-patterns, safety
   and writing conventions travel; deadlines, ownership and in-flight task
   state do not.
3. No equivalent rule is promoted already — scan `/learnings`; duplicates
   degrade signal-to-noise.
4. The user has not opted out ("stop asking me about /learnings", or
   `VIBE_AUTO_PROMOTE=0` in their environment via `~/.vibe/config`).

In the SAME response, ask on ONE line, no preamble:

```
Cross-repo applicable - save to /learnings?  Y / n / never-ask
```

`Y` → run `/learn <one-line distillation of the rule>`; the PreToolUse hook
then prompts again at the filesystem level — the trust boundary, not
redundancy. `n` → drop it; the memory stays per-project. `never-ask` →
suppress prompts this session and surface the permanent opt-out
(`echo VIBE_AUTO_PROMOTE=0 >> ~/.vibe/config`).

Do NOT auto-write to `/learnings` without proposing — the hook would catch
it, but prompt-and-confirm is the trust contract. Do NOT promote
project-specific memories; when unsure, don't (false negatives recover, false
positives pollute). One prompt per cross-repo-applicable memory save — never
batch. Do not propose if the user asked you not to memorise this turn.
