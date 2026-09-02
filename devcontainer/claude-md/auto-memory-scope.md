# Auto-memory is per-project — and past conversations are on disk

## Per-project scope (since task_014)

Each host project gets its own Claude history and auto-memory: the launcher
binds `~/.vibe/projects/<sha1-of-project-path>/` over
`/home/node/.claude/projects/`, so the auto-memory at
`/home/node/.claude/projects/-workspace/memory/` is scoped to THIS project
only. The rest of `~/.claude` (login, settings, agents, commands) stays
shared across containers.

The isolation is deliberate: `vibe X --continue` resumes project X's most
recent conversation, not the globally-most-recent one, and project-specific
memory cannot pollute unrelated work. It prevents cross-contamination; it
does not lose information.

So: project-specific facts (task state, repo conventions not in its docs,
entity facts) → auto-memory, as normal. Cross-project facts (preferences,
voice, work style, recurring corrections) will NOT travel via auto-memory —
propose them for `/learnings` (the `/learn` flow, hook-gated).

If a memory you expect is missing it may predate the split: anything recorded
before task_014 lives in the old shared volume, shadowed by the new bind — ask
the user rather than assume it never existed.

## Search the transcripts before saying "I have no record"

When the user references an earlier conversation ("we talked about X last
week", "didn't I tell you to Y?") and neither auto-memory nor project files
have it, search the on-disk transcripts before saying you have no record of
it.

Claude Code writes one JSONL file per conversation at
`~/.claude/projects/<slug>/<session-uuid>.jsonl`; in vibe the slug for
`/workspace` is `-workspace`, so the glob is
`~/.claude/projects/-workspace/*.jsonl`. They persist in the
`vibe-claude-config` Docker volume across container restarts on this Mac, do
NOT travel between machines, and are not in the repo — cross-machine
persistence relies on `/learnings`, TODO.md, CHANGELOG.md and committed code.

Schema: each line is one record, of many types. User prompts are
`type: "user"` with `message.content` of JSON type string — records whose
`message.content` is a list of `tool_result` blocks are also `type: "user"`
but are tool outputs, so filter them out. Assistant text is
`type: "assistant"` with a list `message.content`: take blocks of
`type: "text"`, skip `thinking` and `tool_use`.

```bash
P=~/.claude/projects/-workspace                          # prompts by keyword
jq -r 'select(.type=="user" and (.message.content|type)=="string") | .message.content' \
   $P/*.jsonl | grep -i "<keyword>"
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' \
   $P/*.jsonl | grep -i "<keyword>"                # assistant text by keyword
jq -r 'if .type=="user" and (.message.content|type)=="string" then "USER: " + .message.content
       elif .type=="assistant" then (.message.content[]? | select(.type=="text") | "CLAUDE: " + .text)
       else empty end' $P/<uuid>.jsonl                  # one file, in order
ls -t $P/*.jsonl | head -5      # newest first (UUID names carry no time order)
```

Search when the reference is specific enough to grep usefully; ask for
clarification when it is not ("that thing we did last week"). Summarise hits;
quote 1-2 short lines at most.

Do not duplicate this data into a parallel committed conversation log: the
transcripts already are that log. Only if the user explicitly asks for
cross-machine persistence are `/learnings`, `TODO.md` or a fresh markdown
file the right tools — never a transcript clone.
