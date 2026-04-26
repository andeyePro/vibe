# /learnings write-confirm hook — trust model

## What changed

The `/learnings` bind-mount in this container is read-write on macOS, not
read-only as the devcontainer config suggests. Docker Desktop and OrbStack
both use a `fakeowner` overlay that silently drops the `readonly` flag — a
write test (`echo > /learnings/test`) succeeds even though the config says
`readonly: true`. This was discovered and documented in task_009.

Because the mount is actually writable, a PreToolUse hook now gates every
tool call that touches the Write, Edit, or MultiEdit tools. When your
`file_path` resolves to `/learnings` or anywhere beneath it, the hook emits a
`permissionDecision: ask` envelope and Claude Code prompts the user to confirm
or deny before proceeding.

## What permissionDecision: ask means

The hook outputs JSON with the following shape:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "vibe: modifying the learning library at <path> — confirm to proceed"
  }
}
```

Claude Code renders its standard permission prompt with the reason text. The
user sees the path and a plain-English description of what is about to happen.
Answering yes allows the tool call to proceed; answering no blocks it.

## do not bypass the hook

Never attempt to circumvent the write-confirm hook. In particular:

- Do not use path traversal to write outside `/learnings` while confusing the
  hook — the hook normalizes paths with `realpath -m` before checking, so
  `/learnings/../etc/passwd` is correctly recognized as outside `/learnings`.
- Do not split a single logical write into multiple smaller operations to avoid
  triggering the hook — each Write, Edit, or MultiEdit call is independently
  checked.
- Do not suggest to the user that they disable or remove `guard-fs.sh`. It is a
  security boundary, not a convenience filter.

The hook is the agreed trust model between you and the user for `/learnings`
modifications. Respecting it is not optional.

## Bash tool: best-effort defense-in-depth

The Bash tool is also hooked (via `guard-bash.sh`) for common shell-write
idioms: output redirects (`>`, `>>`), `tee`, `cp`, `mv`, `rm`, `ln`,
`mkdir`, `chmod`, `chown`, `truncate`, `dd`, and `sed -i`. These checks are
best-effort static pattern matching — they catch obvious literal idioms but
cannot detect variable-indirection redirects, interpreter-embedded writes
(`python3 -c`, `perl -e`, `node -e`), or dynamic `eval`/`bash -c` paths.

The Write/Edit/MultiEdit hook (guard-fs.sh) is the primary gate because it
sees the structured `tool_input.file_path` value directly and is reliable.
The Bash hook is layered defense-in-depth for users who invoke shell write
commands directly.

## /learn slash command

The `/learn <pattern>` slash command is the recommended way to add entries
inside the container. It:

1. Verifies `/learnings` is mounted.
2. Generates a filename matching the host-side `vibe learn` format.
3. Previews the proposed entry to the user.
4. Issues a Write tool call, which triggers the hook prompt.

Pushing the new entry to git is host-only. Run `vibe learn --push` on your
Mac shell, or `cd $VIBE_LEARNING_PATH && git add . && git commit && git push`
manually.

## Why this is strictly stronger than before

Previously the supposed defense was the `readonly` mount flag — which turned
out to be silently ignored. Going from "no protection" to "ask the user before
every write" is strictly stronger. The hook cannot be bypassed by the
`fakeowner` overlay; it lives in the Claude Code tool-call pipeline, not in
the filesystem layer.
