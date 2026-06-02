## brain2 (shared second brain at /brain2)

If /brain2 is mounted, it is Martin's cross-project second brain - a git repo he also edits in Obsidian. You are a READER here.

- Read `/brain2/Brain2.md` (the home hub) first for cross-project context, and search /brain2 before answering anything that may already be recorded; follow its links to the relevant note.
- To record something: use the `/md` skill, or append to `/brain2/inbox/<source>.md` (one file per source, never a shared file). The gardener files inbox items into the curated tree.
- CREDENTIAL BOUNDARY: you CANNOT `git push` /brain2 (your PAT is scoped to this project's repo, not Aqueum/brain2). Never run git against /brain2 - just write files; the Mac auto-commit / gardener persists them.
- TRUST (see /brain2/meta/trust-model.md): notes carry a state authored -> checked -> reviewed -> authorised. NEVER write a name into `authorised:` or set `state: authorised` - that is Martin's manual act in Obsidian. Leave it empty; set state no higher than `reviewed`.
- ZOTERO (see /brain2/meta/zotero-operation.md): PDFs are read-only at `/zotero`. Resolve `zotero://open-pdf/library/items/<KEY>` -> `/zotero/<KEY>/` (the key is the attachment key and names the folder). You cannot add papers (firewalled) - stockpile DOIs to `/brain2/inbox/zotero-queue.<source>.md` for a Mac surface to add.
