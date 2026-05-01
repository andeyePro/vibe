# Vibe Stop hooks

vibe ships two opt-in Stop hooks under `/home/node/.claude/hooks/`:

- **`check-numbering.sh`** — warns when an assistant turn mixes 1./2./3. and a./b./c. lists.
- **`copy-last-block.sh`** — auto-extracts the LAST fenced code block from the assistant's reply into `/workspace/.vibe/copy-latest.txt` so the host-side `vibe-copy-watcher.sh` can `pbcopy` it to the Mac clipboard with no slash-command round-trip.

Both ship to every vibe container by default (`install-claude-extras.sh` syncs them) but are silent until you wire them up in `~/.claude/settings.json`. Vibe does not auto-edit user settings.

---

## check-numbering.sh

Warns when an assistant turn mixes two list shapes that should not co-occur
in a single reply:

- `1.`, `2.`, `3.` ... — a **working list** that persists across turns. Each item
  has a stable meaning the user can reference by number ("do 2 first, then 4").
- `a.`, `b.`, `c.` ... — **per-response action picks**. The user chooses one (or
  more) options for the next step; the labels reset when the next reply arrives.

Mixing both in one reply confuses both states: the user can't tell which numbers
are stable references and which are ephemeral picks. Use ONE shape per reply.

## When the hook fires

Stop hook reads the most recent assistant message from the session transcript,
strips fenced code blocks (so code samples that contain `1.` or `a.` don't
trigger), and matches against:

- start-of-line `^[[:space:]]*[0-9]+\.[[:space:]]` (numbered)
- start-of-line `^[[:space:]]*[a-z]\.[[:space:]]` (lettered)

If both shapes are present after the strip, the hook writes:

```
vibe: numbering warning - last reply mixed 1./2./3. with a./b./c. (see feedback_numbering.md - working list vs per-reply action picks)
```

to stderr. Claude Code surfaces this to the user. The hook always exits 0 so
the warning is non-blocking.

## How the hook is enabled

The script is shipped by `install-claude-extras.sh` on every container start.
The Stop-hook reference itself lives in user-level `~/.claude/settings.json`,
which vibe does NOT auto-edit. To enable, add to settings.json:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "/home/node/.claude/hooks/check-numbering.sh" }
        ]
      }
    ]
  }
}
```

If you don't want the warning, leave the hook reference out of settings.json
(or remove an existing entry). The script being present at the path is harmless
- it only runs when wired up.

---

## copy-last-block.sh

Reads the most recent assistant message from the session transcript, finds
the LAST fenced code block (lines between matching ` ``` ` markers — language
tag on the opening fence is dropped), and writes the block content to
`/workspace/.vibe/copy-latest.txt`. The host-side `vibe-copy-watcher.sh`
(launched by `vibe` on macOS) detects the file change and `pbcopy`s the
content to the Mac clipboard.

Net effect: every assistant turn that contains a fenced code block, the
LAST block of that turn lands on your clipboard. No `/c` slash-command
round-trip required.

### Per-turn opt-out

If the assistant message contains the literal sentinel
`<!-- vibe: no-copy -->` anywhere in the text, the hook skips the write
for that turn. Useful for: long replies where the last fence is a small
example, not the actionable block; replies where the user explicitly
asked for "no clipboard pollution".

### How to enable

Add the hook to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "/home/node/.claude/hooks/copy-last-block.sh" }
        ]
      }
    ]
  }
}
```

You can wire BOTH `check-numbering.sh` and `copy-last-block.sh` as Stop
hooks in the same `hooks` array — they run sequentially per the Claude
Code hook spec.

### Trade-offs

The hook is fire-and-forget for the user but writes whatever the LAST
fenced block of the turn happens to be. If you find yourself with
inappropriate content on your clipboard, the cause is "I don't want this
turn copied" rather than "the hook is broken". Either:

- Use the `<!-- vibe: no-copy -->` sentinel on those turns.
- Re-run with `/c <pattern>` to override the file (the watcher always
  picks up the most recent change).

`/c <pattern>` (the LLM-driven copy with argument-match) remains
available and overrides the hook's auto-copy when invoked. The two
mechanisms compose: the hook keeps the clipboard fresh by default,
and `/c` lets you override when you need a specific older block.
