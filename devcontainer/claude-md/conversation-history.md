# Searching Past Conversations

When the user references something discussed in an earlier conversation
("we talked about X last week", "didn't I tell you to Y?", "what was
the name of the thing we decided on?"), and you cannot find it in your
auto-memory or in project files, do not say "I have no record" without
first searching the on-disk session transcripts.

## Where the transcripts live

Claude Code writes a JSONL file per conversation at:

```
~/.claude/projects/<slug>/<session-uuid>.jsonl
```

Inside vibe, the slug for `/workspace` is `-workspace`. The full glob
pattern is:

```
~/.claude/projects/-workspace/*.jsonl
```

These files persist in the `vibe-claude-config` Docker volume across
container restarts on this Mac. They do NOT travel between machines
and are NOT in the git repo — for cross-machine persistence the user
relies on `/learnings`, TODO.md, CHANGELOG.md, and committed code.

## Schema (the parts you'll grep)

Each line is one JSON record. Many record types exist (`last-prompt`,
`permission-mode`, `attachment`, internal bookkeeping); the two you
care about are:

- **User prompts** — records with `type: "user"` AND
  `message.content` of JSON type string. (Records where
  `message.content` is a list of `tool_result` blocks are also
  `type: "user"` but are tool outputs, not user prompts — filter them
  out.)
- **Assistant final text** — records with `type: "assistant"` whose
  `message.content` is a list; the user-visible reply lives in the
  blocks where `type: "text"` (extract `.text`). Skip blocks of type
  `thinking` and `tool_use`.

## Practical grep recipes

User prompts containing a keyword:

```bash
jq -r 'select(.type=="user" and (.message.content | type) == "string") | .message.content' \
   ~/.claude/projects/-workspace/*.jsonl | grep -i "<keyword>"
```

Assistant text containing a keyword:

```bash
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' \
   ~/.claude/projects/-workspace/*.jsonl | grep -i "<keyword>"
```

Both prompt and final text from one file, in order:

```bash
jq -r '
  if .type=="user" and (.message.content | type) == "string" then
    "USER: " + .message.content
  elif .type=="assistant" then
    (.message.content[]? | select(.type=="text") | "CLAUDE: " + .text)
  else empty end
' ~/.claude/projects/-workspace/<uuid>.jsonl
```

Sort files newest-first when scanning chronologically:

```bash
ls -t ~/.claude/projects/-workspace/*.jsonl | head -5
```

(The UUID filename has no time ordering; use mtime.)

## When to search vs when to ask

Search when the user's reference is specific enough to produce a
useful grep ("the proxy vote ESG screen", "the codestral audit", "the
discussion about pi02 boot"). Ask for clarification when the
reference is too vague to grep usefully ("that thing we did last
week"). One round of clarification beats grepping the entire history
for "thing".

When the search returns hits, summarise concisely — the user wants
the answer, not a transcript dump. Quote at most 1-2 short lines
verbatim if needed for attribution.

## What this rule replaces

The user's intuition was to write a separate verbatim conversation
log. The transcripts already are that log — this rule just teaches
you to read them. Do not duplicate the data into a parallel committed
file unless the user specifically asks for cross-machine persistence
(in which case `/learnings`, `TODO.md`, or a fresh markdown file are
the right tools, not a transcript clone).
