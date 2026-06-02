# Shared second brain at /brain (and Zotero at /zotero)

This container has a shared second-brain repo bind-mounted at `/brain` (read-write) and, when configured, a Zotero store at `/zotero` (read-only). This fragment is only installed when `/brain` is actually mounted, so if you are reading it the brain is live. It is how every vibe instance — across all your projects — collaborates through one knowledge base.

`/brain` is NOT this container's `/workspace`. Claude Code does not auto-load `/brain/CLAUDE.md`, so the conventions you need are here.

## Filing notes

- Prefer the `/md` skill if it is registered — it places and trust-stamps notes correctly in the brain's hub structure rather than dumping loose files.
- When adding raw cross-project facts without the skill, append to `/brain/inbox/<source>.md` — one file per source (the source being this project / agent). Append, don't overwrite; the gardener reconciles the inbox into the hub later.
- Follow any conventions documented under `/brain/meta/` if present — in particular `/brain/meta/trust-model.md` and `/brain/meta/zotero-operation.md`.

## Credential boundary — read/write files, but do NOT push

A non-gardener container's GitHub PAT is scoped to ITS OWN repo, not the brain's. So:

- You CAN read and write files under `/brain` freely.
- You CANNOT `git commit && push` the brain from here — the push will fail (wrong scope). Do not try, and do not surface the failure as a problem to solve.
- Only the **gardener** (the vibe instance whose `/workspace` IS the brain repo) or the user on the host commits and pushes the brain. Your writes sit in `/brain/inbox/` until the gardener sweeps them.

## Zotero is read-only at /zotero

- Resolve a `zotero://open-pdf/library/items/<KEY>` link to the on-disk PDF at `/zotero/<KEY>/`.
- You cannot add papers to Zotero from a container. When you find a paper that should be in the library, stockpile its DOI in `/brain/inbox/zotero-queue.<source>.md` for the user to import host-side.
- `readonly` on the mount is advisory on macOS (Docker Desktop's fakeowner overlay silently drops the flag). Treat `/zotero` as read-only by discipline regardless of whether a write would physically succeed.

## Trust — `authorised:` is the human's act, never yours

Never write a name into a note's `authorised:` field, and never set a note's `state:` to `authorised`. Promoting a note to authorised is the user's manual act of trust. You draft and propose; you do not self-authorise. See `/brain/meta/trust-model.md`.
