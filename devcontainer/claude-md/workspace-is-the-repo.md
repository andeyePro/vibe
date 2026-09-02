# /workspace IS the local repo — in-container work needs no `git pull`

`/workspace` is not a copy or a clone. It is a bind mount of the exact folder the user ran `vibe` in on their machine (`devcontainer.json`: `workspaceMount` = `${localWorkspaceFolder}` → `/workspace`). Shared checkouts under `/repos/<name>` are bind mounts of machine-local clones in the same way. One directory, one `.git`, two views of it.

Consequences — get these right, they are a recurring vibe mistake:

- **Every edit and commit you make here is already on the user's disk**, the instant you make it. `git log` in the container and `git log` in the same folder on the Mac are the same history. Telling the user to `git pull` before building, running, deploying, or rebuilding work that was done IN THIS CONTAINER is wrong: the pull is a no-op ("Already up to date") and sends them on a pointless errand.
- **A pull is only needed when the change reached the remote from somewhere else** — another machine, a GitHub web edit, CI, a different clone. Ask yourself "did the bytes land in this folder?" before ever suggesting a pull.
- **Relaunch/rebuild is a different thing from pull.** What DOES need a step is anything the container consumes at start: the Docker image (`devcontainer/` changes → the launcher auto-rebuilds on the next `vibe` launch, or `vibe --rebuild`), and the shared `~/.claude` extras it syncs on every container start (commands, agents, CLAUDE.md fragments). Say "relaunch", not "pull".
- **vibe-on-vibe corollary.** When the project is vibe itself, `~/bin/vibe` is a symlink to either an in-place dev clone (then this folder IS the launcher's source — edits take effect on the next launch, no pull) or a separate `~/.vibe-src` from a curl install (then `git -C ~/.vibe-src pull` on the Mac IS required). You cannot see which from inside; if it matters, have the user run `readlink ~/bin/vibe` and answer from that.
- **Mac test bridges are not pulls either.** A build tree that a bridge script maintains on a Mac test account (synced by tar/rsync in the script) is a separate copy fed by the script's own sync step; it never sees this folder's commits via git. Use the bridge's atomic sync+build path, never "pull then build".

The folder may live under a sync service (Dropbox, iCloud) on some machines. That changes nothing above — the container still sees the live files — though a sync client can race `.git` writes; if the user reports index corruption, that is the first suspect.
