## Shared repos (`/repos/<name>` mounts)

If `/workspace/.vibe/shared-repos.manifest` is non-empty, this project has one
or more shared repos mounted this launch. Read it before touching anything
under `/repos/` — `cat /workspace/.vibe/shared-repos.manifest`; one line per
mount, `name mode slug` (e.g. `andeyePro rw andeyePro/andeyePro`). It tells you
what's mounted and whether you're allowed to write (`rw`) or only read (`ro`)
— the launch header printed the same information when this session started,
and `vibe repos list` (host-side) shows the same status plus anything broken.

- **Every `/repos/<name>` is a separate repo with its own licence and its own
  git history — not this project's code.** Some are proprietary
  (e.g. `andeyePro/andeyePro`), some are just separately-licensed; treat them
  all the same way: reference material from `/workspace`'s point of view,
  never a source to copy from.
- **Never copy code from `/repos/*` into `/workspace`.** Not a function, not
  a snippet, not "just this one helper". If `/workspace` needs shared
  behaviour, consume it only through the project's declared interface or
  feature-flag seam — whatever `/workspace` already exposes for calling into
  the shared repo — never by importing or pasting the shared repo's
  internals directly into this project's source tree. If no seam exists yet
  for what you need, that's a design decision for Martin, not something to
  route around by copying.
- **A `ro` mount means commit/push for that repo happens elsewhere.** If you
  find yourself wanting to edit files under `/repos/<name>`, stop — that
  repo has its own vibe project (on this machine or another) where its
  commits belong. This container's git identity and PAT are scoped to the
  `/workspace` repo only; even where a mount happens to be `rw`, that's a
  filesystem write permission for cross-repo development, not licence to
  treat `/repos/<name>` as this project's own commit history.
- **`rw` intent is a per-project declaration, refereed by a single-writer
  lock.** `/workspace/.vibe-repos`'s `rw` mode for a slug is a request, not
  a guarantee — the launch header says whether this session actually got
  the lock (`rw`) or fell back to `ro` because another project's session
  holds it, naming the current holder and since-time. The statusLine also
  shows a `⚠ rw:<requesting-project>` segment to the CURRENT holder when
  someone else has filed a claim.
- **`/repo claim <name>`** is the etiquette for "I need rw and someone else
  has it": it leaves a named, timestamped request visible to the current
  holder's statusLine. It does not interrupt them, force a release, or grant
  you anything — it's a polite tap on the shoulder, not a lock override. Use
  it once, then wait for the holder to exit on their own schedule; don't
  retry-loop it.
- **Declaring a repo (`/repo add`) only edits this project's committed
  `.vibe-repos` file.** It does not register where the checkout lives on
  this machine, mint its token, or take effect this session. See the `/repo`
  command's own file for the host-side step (`vibe repos add` on the Mac)
  and the relaunch requirement — mounts are fixed at container creation.
