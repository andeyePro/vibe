---
description: /repo add|remove|claim — declare or drop this project's use of a shared repo mounted at /repos/<name>, or file a write-access claim against a repo currently held read-write by another project. Editing /workspace/.vibe-repos is in-container; registering the machine-side checkout (`vibe repos add`) and relaunching are host-side steps this command cannot perform.
---

# /repo — shared-repo declaration and claim

## What this does

`/repo` edits this project's shared-repo declaration file, `/workspace/.vibe-repos`
(committed to the repo — it records WHAT this project uses, not WHERE the repo
lives on any given machine), and files write-access claims against a repo
already mounted at `/repos/<name>`. It does three things and three things only:

- `/repo add <owner/repo> [--rw]`
- `/repo remove <owner/repo>`
- `/repo claim <name>`

It CANNOT touch `~/.vibe/repos` (the machine registry), mint a PAT, or relaunch
the container — all of that lives on the host, outside this container's reach,
per vibe's blast-radius model (see `CLAUDE.md` § Invariants: fine-grained PATs
stay single-repo, and the container never gets host filesystem access beyond
its own bind mounts). Every subcommand below says explicitly what you still
owe the host side.

## `/repo add <owner/repo> [--rw]`

1. Validate `<owner/repo>` against the pinned slug charset
   `[A-Za-z0-9._-]+/[A-Za-z0-9._-]+`. Reject anything else with a one-line
   reason — no file write on a bad slug.
2. Append (or update in place, if the slug is already declared) a line in
   `/workspace/.vibe-repos`:

   ```
   <owner>/<repo> ro
   ```

   or, with `--rw`:

   ```
   <owner>/<repo> rw
   ```

   Comments and blank lines already in the file are left alone; only the
   matching slug's line is touched.
3. Tell the user, verbatim, both of the following — this command does
   **neither** of them itself:
   - **Machine-side registration** (run on the host Mac shell, NOT inside
     this container): `vibe repos add <owner/repo> [path]`. That's what
     resolves where the checkout actually lives on THIS machine, mints or
     stages its PAT if one isn't already stored, and creates the
     `.vibe-signals/` sidecar. Every machine that runs this project needs
     its own `vibe repos add` — the declaration you just wrote travels with
     the project (it's committed, in `.vibe-repos`); the registry entry does
     not (it's per-machine, `~/.vibe/repos`, chmod 600, host-only).
   - **Relaunch required.** Mounts are fixed at container creation. Nothing
     `/repo add` just did takes effect in THIS running session — exit and
     run `vibe` again from the project root.
4. **The container cannot touch `~/.vibe` on the host** — not the registry,
   not the token store, not any per-machine config. Everything under
   `~/.vibe/*` is out of reach from inside this container by design; that
   split (committed declaration vs. per-machine registry) is the whole
   reason `/repo add` and `vibe repos add` are two separate steps on two
   separate sides of the container boundary. If `/repo add` is the only
   step taken, the repo will show as "not configured on this machine" in
   `vibe repos list` until the host-side step also runs.

## `/repo remove <owner/repo>`

1. Remove the matching declaration line from `/workspace/.vibe-repos` (exact
   slug match; the `ro`/`rw` mode suffix is ignored for matching purposes).
   No match found → say so, no-op.
2. Tell the user: the machine registry entry (`~/.vibe/repos`) is
   **untouched** — other projects on this machine may still be using it.
   Dropping the registry entry too (and optionally the stored token) is
   `vibe repos remove --purge <owner/repo>`, run on the host, not this
   command.
3. **Relaunch required**, same as `add`: the mount stays live for the rest
   of this session; only the next `vibe` launch actually drops it.

## `/repo claim <name>`

`<name>` is the mount basename under `${VIBE_REPOS_DIR:-/repos}/<name>` —
**not** the full `owner/repo` slug (it's what the launch header and
`vibe repos list` both print, and what appears in the runtime manifest at
`/workspace/.vibe/shared-repos.manifest`).

1. Verify `${VIBE_REPOS_DIR:-/repos}/<name>` exists as a directory. Not
   mounted → say so, no-op — there's nothing to claim.
2. Defensively `mkdir -p` the signals directory (it should already exist
   from mount assembly, but don't assume), then write the claim request:

   ```
   ${VIBE_REPOS_DIR:-/repos}/.signals/<name>/rw-request
   ```

   with content:

   ```
   project=<this project's name>
   since=<epoch seconds, from `date -u +%s`>
   ```

   Overwrite unconditionally — last-claim-wins is the pinned semantics; the
   current rw-holder sees whichever name landed there most recently, and
   that's fine by design.
3. This works even when `/repos/<name>` itself is mounted **read-only** —
   the `.signals/<name>/` sidecar is mounted **read-write for every
   session, always**, specifically so a ro-mounted session can still file a
   claim. You do not need `--rw` in your own declaration to run `/repo
   claim`.
4. Tell the user what happens next: the CURRENT rw-holder's statusLine will
   show a `⚠ rw:<your-project-name>` segment the next time it repaints.
   There is no interrupt and no separate notification beyond the
   statusLine — the holder decides on their own schedule whether to finish
   up and exit. Handoff only actually happens at THEIR next relaunch: their
   exit releases the lock, and the next session to acquire it (which could
   be yours, if you relaunch and your declaration says `rw`) gets it via
   the normal stale-free acquire path — filing a claim never force-releases
   anything by itself.
5. `/repo claim` does **not** itself acquire the lock, relaunch anything,
   or change this session's own mount mode — it only leaves the note. If
   nobody currently holds rw (repo mounted ro because no project has
   declared `rw`, or the lock is simply free), filing a claim is a signal
   with nothing listening. Run `vibe repos list` first if you want to check
   before writing the request.

## Examples

```
/repo add andeyePro/andeyePro
/repo add andeyePro/andeyePro --rw
/repo remove andeyePro/andeyePro
/repo claim andeyePro
```

## What this command is not

- Not a way to browse or read `/repos/*` content — that's plain file tools,
  subject to the proprietary-seam discipline documented in
  `devcontainer/claude-md/shared-repos.md` (never copy shared-repo code into
  `/workspace`; consume only through the project's declared interface or
  feature-flag seam).
- Not a way to acquire the rw lock directly — the lock is acquired by the
  **launcher** at `vibe` startup, based on the declaration's `rw` mode,
  never by an in-session command.
- Not a way to see or edit the machine registry, tokens, or another
  project's signals on this machine — `~/.vibe/*` and any other project's
  `/workspace` are both out of reach from inside this container by design.
