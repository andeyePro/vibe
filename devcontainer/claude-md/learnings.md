# Learning library (cross-org pattern reference)

If a directory at `/learnings` exists inside the vibe container, it is the
user's read-only cross-org learning library, mounted in by the host-side
`vibe learn --init` setup. This rule tells you how to use it.

## What `/learnings` is

The user has set up a learning library on their host machine - a
collection of timestamped notes capturing patterns, preferences, or
recurring decisions they've found worth remembering across all of their
vibe projects. Each entry is a single Markdown file inside `/learnings`,
named with an ISO timestamp plus a 6-character random hex suffix
(for example `2026-04-23T09:24:19Z-346594.md`). The file body has the
form:

    # 2026-04-23T09:24:19Z

    <pattern body, free-form prose>

The library is intended to be read-only from inside the container.
Modifications happen host-side via `vibe learn "<pattern>"`, which the
user runs on their Mac shell, not inside the container.

## When to consult `/learnings`

Before starting work on a task that has cross-project relevance - a
choice about coding style, a tool preference, a security stance, a
naming convention, a build-system convention, a recurring debugging
pattern - check whether the user has captured guidance on it:

- `ls /learnings` to see all entries.
- Grep across all entries: `grep -r "<topic>" /learnings`.
- Read a specific entry to see the full pattern body.

If a relevant entry exists, follow it. If you are uncertain whether an
entry applies to the current situation, ask the user before acting on
it.

## When NOT to consult `/learnings`

- When `/learnings` does not exist (the user has not run
  `vibe learn --init`, or has opted this project out via a `.no-learn`
  marker). Do not surface the absence of `/learnings` to the user as a
  concern - it is opt-in.
- For project-specific facts already captured in the project's
  `CLAUDE.md`, `TODO.md`, or repository documentation. Those are
  authoritative for the current project; `/learnings` is for patterns
  the user wants to apply ACROSS projects.
- For ephemeral session notes - those belong in your conversational
  memory, not in `/learnings`.

## How to recommend a new learning

If you observe a pattern, preference, or correction the user has made
that they might want to apply across other projects, you can suggest
it to them:

> "This seems like a cross-project pattern. To capture it, run
> `vibe learn \"<short description>\"` on your Mac shell from any
> project directory."

Do not run `vibe learn` yourself - it is a host-only command and is
not available inside the container.

## Why this rule exists

By default Claude inside a vibe container has no idea `/learnings` is
mounted, even when it is. This rule is the bridge between the
host-side opt-in capture system and the container-side reference.
Without it, the library is invisible from your side and the user's
accumulated patterns go unused.
