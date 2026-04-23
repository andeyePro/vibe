---
description: Copy the most recent fenced code block from Claude's prior turn to the Mac clipboard via the host-side watcher, with a scratch-file fallback.
---

# /c — clipboard bridge

Copy a code block from the prior assistant turn to the clipboard.

## Behaviour

1. **Identify the target block.** Look at the immediately-prior assistant turn (not any tool output, not the human turn — Claude's own message).
   - If `$ARGUMENTS` is non-empty, select the fenced code block whose language tag or first non-blank line best matches `$ARGUMENTS`.
   - Otherwise, select the most recent fenced code block in that turn.
   - If there is no prior assistant turn, or the prior assistant turn contains no fenced code block, respond with exactly:
     `no prior code block to copy`
     and stop — do not invoke any tools.

2. **Extract raw bytes.** Take the content between the opening and closing fence lines, excluding the fence lines themselves and the language tag line (the line immediately after the opening fence that contains only an identifier like `python`, `bash`, `json`, etc.). The extracted bytes are the literal characters of the code, including all internal newlines and any trailing newline before the closing fence.

3. **Write to the scratch file.** Use the Write tool to write those bytes verbatim to `/workspace/.vibe/copy-latest.txt`. This is a UTF-8 write; see the note below.

4. **Report success.** Tell the user:
   - The byte count of the extracted block.
   - The scratch file path: `/workspace/.vibe/copy-latest.txt`
   - That the host-side watcher will copy it to the Mac clipboard automatically (if running on macOS via vibe).

## UTF-8 note

`/c` targets UTF-8 text code blocks. The Write tool round-trips UTF-8 cleanly; non-UTF-8 byte sequences (binary data, other encodings) are NOT reliably preserved through the Write-tool hop. For binary-safe copy, use `!vibe-copy <file>` directly in the host shell — the shell helper is fully byte-safe.

## Example

If the prior assistant turn contained:

````
```python
def hello():
    print("hello world")
```
````

Running `/c` (or `/c python`) extracts:

```
def hello():
    print("hello world")
```

writes it to `/workspace/.vibe/copy-latest.txt`, and reports the byte count plus the scratch path. On macOS via vibe, the host-side watcher picks up the file change and runs `pbcopy` automatically within one second.
