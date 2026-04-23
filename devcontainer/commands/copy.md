---
description: Copy the most recent fenced code block from Claude's prior turn to the Mac clipboard via OSC 52, with a scratch-file fallback for non-OSC-52 terminals.
---

# /copy — clipboard bridge

Copy a code block from the prior assistant turn to the clipboard.

## Behaviour

1. **Identify the target block.** Look at the immediately-prior assistant turn (not any tool output, not the human turn — Claude's own message).
   - If `$ARGUMENTS` is non-empty, select the fenced code block whose language tag or first non-blank line best matches `$ARGUMENTS`.
   - Otherwise, select the most recent fenced code block in that turn.
   - If there is no prior assistant turn, or the prior assistant turn contains no fenced code block, respond with exactly:
     `no prior code block to copy`
     and stop — do not invoke any tools.

2. **Extract raw bytes.** Take the content between the opening and closing fence lines, excluding the fence lines themselves and the language tag line (the line immediately after the opening fence that contains only an identifier like `python`, `bash`, `json`, etc.). The extracted bytes are the literal characters of the code, including all internal newlines and any trailing newline before the closing fence.

3. **Write to a temp file.** Use the Write tool to write those bytes verbatim to `/tmp/copy-<ISO8601>.txt` (substitute the current UTC timestamp in ISO 8601 basic format, e.g. `20260423T143000Z`). This is a UTF-8 write; see the note below.

4. **Invoke vibe-copy.** Use the Bash tool to run:
   ```
   vibe-copy /tmp/copy-<ISO8601>.txt
   ```
   (Same timestamp-based filename as Step 3.)

5. **Report success.** Tell the user:
   - The byte count of the extracted block.
   - The scratch file path where the content was also written:
     - If `$VIBE_COPY_SCRATCH_DIR` is set: `$VIBE_COPY_SCRATCH_DIR/copy-latest.txt`
     - Otherwise: `/workspace/.vibe/copy-latest.txt`

## UTF-8 note

`/copy` targets UTF-8 text code blocks. The Write tool round-trips UTF-8 cleanly; non-UTF-8 byte sequences (binary data, other encodings) are NOT reliably preserved through the Write-tool hop. For binary-safe copy, use `vibe-copy <file>` directly in Bash — the shell helper is fully byte-safe.

## Example

If the prior assistant turn contained:

````
```python
def hello():
    print("hello world")
```
````

Running `/copy` (or `/copy python`) extracts:

```
def hello():
    print("hello world")
```

writes it to `/tmp/copy-<timestamp>.txt`, invokes `vibe-copy /tmp/copy-<timestamp>.txt`, and reports the byte count plus the scratch path `/workspace/.vibe/copy-latest.txt`.
