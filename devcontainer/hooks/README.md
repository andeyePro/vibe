# Vibe Stop hooks

vibe ships two opt-in Stop hooks under `/home/node/.claude/hooks/`:

- **`check-numbering.sh`** — warns when an assistant turn mixes 1./2./3. and a./b./c. lists, or restarts numbering with more than one top-level `1.` (several separate numbered lists in one reply).
- **`copy-last-block.sh`** — when the assistant's reply contains the literal sentinel `<!-- vibe: copy -->`, extracts the LAST fenced code block of that reply into `/workspace/.vibe/copy-latest.txt` so the host-side `vibe-copy-watcher.sh` can `pbcopy` it to the Mac clipboard with no slash-command round-trip. Silent on replies without the sentinel — the assistant must explicitly flag a block as paste-worthy for the clipboard to be touched.

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

It also counts top-level `1.` markers (after the same code-fence strip). More
than one means the reply restarted numbering — several separate numbered lists
— so a bare "1" from the user is ambiguous. The hook then writes:

```
vibe: numbering warning - last reply had 3 separate numbered lists (multiple "1."s); use one ordered list per reply so a bare number is unambiguous
```

This pairs with `output-consolidation.md` (one ordered list per reply).

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

Reads the most recent assistant message from the session transcript. If
the text contains the literal sentinel `<!-- vibe: copy -->` anywhere,
the hook finds the LAST fenced code block in that message (lines between
matching ` ``` ` markers — language tag on the opening fence is dropped)
and writes the block content to `/workspace/.vibe/copy-latest.txt`. The
host-side `vibe-copy-watcher.sh` (launched by `vibe` on macOS) detects
the file change and `pbcopy`s the content to the Mac clipboard.

If the sentinel is absent, the hook does nothing — your clipboard is
not touched. This is the default. The assistant must explicitly include
the sentinel on turns where it wants you to paste the block elsewhere.

Net effect: when the assistant intends a block for you to paste, the
clipboard is loaded by the time your prompt unblocks. No `/c` slash-
command round-trip required. On turns where there is nothing to paste,
nothing happens.

### Per-turn opt-in

The literal sentinel `<!-- vibe: copy -->` must appear somewhere in the
assistant's text for the hook to fire. The marker is an HTML comment so
it does not render visibly in the user's Markdown view — the assistant
should also tell you in plain text that the clipboard has been loaded.

Convention: the marker appears at the end of the reply, after the fenced
block intended for copying. The hook always copies the LAST fenced block
of the message, regardless of where the marker sits relative to it.

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

The opt-in default puts the decision on the assistant: it must remember
to include the sentinel on turns where you should paste. The previous
auto-copy-every-turn default (used until 2026-05-18) traded user-side
clipboard pollution for zero assistant-side effort. The current opt-in
default minimises clipboard noise — your clipboard is only touched on
turns where the assistant has explicitly flagged a block as paste-
worthy — at the cost of missed copies on turns where the assistant
forgets the marker. `/c <pattern>` remains available as a manual
override for those cases, and overwrites whatever the watcher most
recently picked up.

