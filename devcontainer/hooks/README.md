# Numbering rule + Stop hook

This vibe container ships a Stop hook (`/home/node/.claude/hooks/check-numbering.sh`)
that warns when an assistant turn mixes two list shapes that should not co-occur
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
