# TODO.md and CHANGELOG.md convention

Two canonical files for tracking work. Don't conflate them.

## TODO.md — open backlog + abandoned items

- Maintainer-facing.
- Append open work under `## Open` with `[ ]` markers.
- Abandoned/parked items STAY in `## Open` with `[!]` and a one-line failure note. Don't move them to CHANGELOG.
- Failure notes are the point — they prevent re-attempting the same dead end.

## CHANGELOG.md — done-work audit log

- Reader-facing. A future PR reviewer or upstream maintainer should be able to scan it without reading the Open backlog.
- Append `[x] **<title>** — <narrative>` entries when a task closes successfully.
- Date headings (`## YYYY-MM-DD`) group same-day commits.
- Reverse-chronological: newest at top.
- Include commit SHA, what changed, why. Bullet-sized but informative.

## Why split

If TODO.md mixes Open and Done, an external reviewer can't tell whether the file is a TODO or a CHANGELOG, and either signal dilutes the other. The convention was triggered 2026-05-08 by an upstream reviewer's confusion on a Pioreactor-plugin PR ("Why is this file called TODO.md? It looks more like a CHANGELOG?").

## Both files commit alongside the code change

Don't add to TODO.md or CHANGELOG.md in a separate commit. Same commit as the code → history stays paired and bisects cleanly.

## When CHANGELOG.md doesn't exist yet

Don't auto-create it. The first time you close a successful task, create CHANGELOG.md with a header line and the entry; in subsequent closes, append.

## Distinct from in-session TaskCreate

`TaskCreate` and similar in-conversation todo lists are ephemeral scratchpad. They don't live in TODO.md or CHANGELOG.md.
