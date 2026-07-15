# task_017 Cycle 1 — Generator report

Scope: AC1–AC7 (registry + declaration + mounts + header) plus the relevant
Pinned-names items. Cycles 2–4 (rw lock, claim/`/repo`, credentials) untouched.
No test files touched (Tester-owned, append-only per `/vs` convention — the
Cycle-1 smoke checks for AC1–AC5 land in the Tester's pass, not this one).

## Per-AC what/where

**AC1 — `vibe repos` subcommand** (`vibe`)
- Dispatch block placed immediately after the existing `learn` dispatch
  block, still before `parse_vibe_args "$@"` (mirrors vibe:1401's exact
  placement/shape): `if [ "${1:-}" = "repos" ]; then repos_handle_subcommand
  "$@"; exit $?; fi`.
- `repos_handle_subcommand` routes `add` / `remove` / `list` / empty /
  unknown to `_repos_add` / `_repos_remove` / `_repos_list` / usage, all of
  which call `exit` themselves on every path (mirrors `learning_handle_
  subcommand`'s contract).
- `_repos_add <slug> [path]`: validates slug charset, rejects a
  dot-prefixed basename, rejects a basename or sanitised-env-name collision
  against any OTHER already-registered slug (reads `~/.vibe/repos` inline),
  resolves/validates the checkout path (prompts if omitted; requires
  `.git`), writes the registry entry (`repos_registry_save`), calls
  `shared_repo_ensure_signals`, appends the declaration line to the current
  project's `.vibe-repos` (dedup via `_vibe_repos_decl_has`/`_append`), mints
  a token via the existing `setup_token` if none is stored, prints a
  relaunch reminder. Exits 1 with a one-line reason on every validation
  failure.
- `_repos_remove <slug> [--purge]`: removes the declaration line only by
  default; `--purge` also drops the registry entry and offers (via the
  existing `ask_yes_no`) to delete the token via new `remove_token`.
- `_repos_list`: single pass over `shared_repos_scan`'s M/B/N output,
  printing `mounted <ro|rw> at /repos/<name>` / `BROKEN: <reason>` / `not
  configured on this machine`.

**AC2 — parse/lookup helpers** (`vibe`, all before the `VIBE_SOURCE_ONLY`
guard): `shared_repos_parse` (charset + mode validation, warns-and-skips
malformed lines by number, comment/blank skip via `read`'s own whitespace
split), `repos_registry_lookup` (mirrors `lookup_token`'s fail-safe shape,
plus path-validity checks — absolute, no embedded newline/quote),
`shared_repo_env_name` (uppercase + `tr -c 'A-Z0-9' '_'`, echoes the FULL
`VIBE_SHARED_TOKEN_*` name, not just the suffix — read literally against
AC2's naming). Also added (not explicitly named in AC2 but load-bearing):
`is_valid_repo_slug` (shared charset predicate), `shared_repo_basename`,
`repos_registry_save`/`repos_registry_remove`, `remove_token`,
`_vibe_repos_decl_has`/`_append`/`_remove`.

**AC3 — mount assembly** (`_build_override_config` in `vibe`): a new block
between the Zotero mount and the OpenProject-MCP host resolution calls
`shared_repos_scan "$workspace"` and, for each `M` line, appends TWO mount
triples — checkout (ro flag from `bindmode`, hard-pinned `"ro"` in cycle 1
regardless of the declared mode) at `/repos/<name>`, and `<checkout>/.vibe-
signals` (always rw) at `/repos/.signals/<name>`. Unresolvable-and-
unregistered repos never reach an `M`/`B` line that adds mounts (`N` tag,
silently skipped by the `case`). Registered-but-broken repos (path
missing/not-git, no token, sidecar unwritable, dot-prefix, basename
collision) contribute no mounts and are recorded as `B` lines for the header.
Verified end-to-end with a fixture workspace (see Gate outputs below):
`_build_override_config` emitted exactly the two expected mount objects,
code mount `readonly: true` even though the declaration said `rw` (C1
hard-pin confirmed).

**AC4 — launch header** (`vibe` main block, after the Zotero banner): loops
over `SHARED_REPOS_SCAN`, printing `  ◆ shared repo: <slug> at /repos/<name>
(<ro|rw>)` for `M`, `  ⚠ shared repo <slug> BROKEN: <reason>` for `B`, and a
literal no-op `N\ *) ;;` arm for never-registered — the empty arm is the
structural distinction AC4 asks for (a test can grep for the dedicated `N)`
branch, not just infer silence from absence of output).

**AC5 — runtime manifest**: `SHARED_REPOS_SCAN` is captured once right after
`OVERRIDE_CONFIG=$(_build_override_config "$WORKSPACE")`, then `shared_repos_
manifest_lines` (pure filter, no re-scan) writes `$WORKSPACE/.vibe/shared-
repos.manifest` via unconditional `>` (truncates to empty with zero shared
repos) — all of this executes before the `devcontainer "${UP_ARGS[@]}"` call
further down.

**AC6 — git ergonomics** (`devcontainer/install-claude-extras.sh`): new
`ensure_shared_repos_safe_directory`, wired in at the bottom alongside the
other `ensure_*`/`check_*` calls. Reads the manifest (path overridable via
`VIBE_SHARED_REPOS_MANIFEST` for tests), resolves the mount root via
`${VIBE_REPOS_DIR:-/repos}`, and adds one literal `git config --global --add
safe.directory <root>/<name>` per manifest line, de-duplicated via `git
config --get-all` first (verified idempotent across two calls — see Gate
outputs). `GIT_OPTIONAL_LOCKS=0` shipped as a plain constant in `devcontainer/
devcontainer.json`'s `containerEnv` AND `remoteEnv` (mirroring how every
other constant there — `NODE_OPTIONS`, `CLAUDE_CONFIG_DIR`, etc. — is
duplicated across both keys already); applied container-wide rather than
scoped per-checkout, documented as a deliberate simplification (it's a
read-path optimisation toggle, never a correctness concern).

**Pinned "Gitignore additions"**: `ensure_project_gitignore`'s managed block
(`install-claude-extras.sh`) gains a `.vibe-signals/` line (owner a).
`shared_repo_ensure_signals` (owner b) directly ensures the same line in the
shared checkout's own `.gitignore` at registration/mount-assembly time.
`.vibe-repos` is untouched by both — committed by design. Also manually
synced `/workspace/.gitignore`'s own already-installed managed block (this
repo dogfoods itself; `ensure_project_gitignore` is idempotent-once-present
so a stale in-repo block would otherwise silently drift from the shipped
fragment).

**AC7 — gates**: see below. README (`## What you get` bullet, Host-side
state table row for `~/.vibe/repos`, a `vibe repos add` usage line) +
CHANGELOG (2026-07-11 heading, new entry) landed in this diff.

## Deviations from the spec, with rationale

1. **Dot-prefix and basename-collision folded into the `B` (broken) tag,
   not left as stderr-only warnings.** The Pinned-names section describes
   dot-prefix as "skipped-with-warning" without specifying whether `vibe
   repos list`/the header should also see it as a discrete state. I made it
   a `B` line (in addition to an immediate stderr warning) so `list` and the
   header report an accurate reason instead of silently misclassifying it as
   "not configured on this machine" (which would be actively misleading —
   the repo IS potentially registered, just permanently unmountable while
   named that way). Same treatment for basename collisions detected at scan
   time (add-time rejection is the primary defence; this is the defensive
   re-check for a hand-edited `.vibe-repos`).
2. **`shared_repos_scan` also emits an explicit `N <slug>` line for
   never-registered declarations**, rather than producing zero output for
   that branch. The header's `N)` arm is a literal no-op, so the AC4-
   mandated silence is unchanged in practice, but every consumer
   (`list`, header, manifest) now shares one struct format instead of two
   ("N" is the third tag alongside the spec's explicit M/B) — chosen for
   single-source-of-truth consistency (a mis-scan can't make `list` and the
   header disagree) and because a dedicated no-op branch is more directly
   testable than "absence of a line."
3. **`GIT_OPTIONAL_LOCKS=0` applied container-wide**, not scoped to ro
   checkouts specifically. AC6 explicitly leaves the exact mechanism to the
   Generator's choice, provided it's documented (done, both in the shell
   comment and here). A per-repo scoped version would need its own
   ro/rw-aware plumbing; since the variable only ever disables an
   optimisation (never changes correctness), the blanket approach is safe
   and simpler, with room to narrow it in a later cycle if that changes.
4. No deviation on the C1 hard-pin: mounts are always `ro` regardless of a
   declared `rw` line, per the task brief's explicit instruction — confirmed
   in the `_build_override_config` fixture run below (declaration said `rw`,
   emitted mount was `"readonly": true`).

## Gate outputs

- `python3 code-check.py` → `✓ shellcheck clean across 15 files` (two
  findings fixed during development: SC2318 same-line dependent `local`
  assignment in `shared_repos_scan`; SC2034 unused `mode`/`slug` in
  `ensure_shared_repos_safe_directory`'s positional `read`, silenced with a
  scoped `# shellcheck disable=SC2034` comment, matching the file's existing
  `SC2120`/`SC2064` precedent).
- `python3 smoke-test.py` → `✓ smoke tests passed`, 1080/1080 checks, 0
  failures (pre-existing suite; no Tester checks for task_017 exist yet by
  design). One regression caught and fixed during development:
  `test_learning_banner_parent_shell_load` failed because a new doc comment
  inside `_build_override_config` happened to contain the literal substring
  the test uses as its `OVERRIDE_CONFIG=$(_build_override_config` marker,
  shifting the test's byte-offset search — reworded the comment, re-ran,
  green.
- Manual end-to-end verification (sourcing `vibe` with `VIBE_SOURCE_ONLY=1`
  against temp fixtures, not committed as tests — Tester's job): slug
  validation/injection-rejection, `shared_repos_parse` malformed-line
  warnings, registry save/lookup round-trip, `shared_repo_ensure_signals`
  idempotency + sidecar/gitignore creation, `shared_repos_scan`'s M/B/N
  output across registered+tokened / registered+no-token / never-registered
  cases, `vibe repos add/remove` end-to-end (including dedup-on-re-add and
  bad-slug rejection), `_build_override_config`'s full JSON output (two
  mount objects, ro hard-pin confirmed), and `ensure_shared_repos_safe_
  directory`'s de-duplication across two runs (global git config cleaned up
  afterward).

## Scope discipline

Did not touch: `smoke-test.py`, `guard-bash.sh`, `guard-fs.sh`,
`init-firewall.sh`, the `settings.local.json` heredoc, `credential-helper.sh`.
No cycle-2/3/4 mechanics implemented (lock dir, `rw-request`, `/repo`
command, remoteEnv token plumbing, credential-helper changes) — the
declaration's `rw` field parses but is inert for mounting purposes, exactly
as scoped.
