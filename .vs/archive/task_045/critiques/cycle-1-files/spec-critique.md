# Spec Critique — task_045 codex-allow registry

## Concerns

1. **AC4 — BLOCKING.** `VIBE_ASSUME_YES` does not exist anywhere in `vibe`
   today, and `ask_yes_no` (line 188) has no non-TTY branch — bare `read
   -rp`. The AC doesn't say *where* the new skip-the-prompt logic lives: if
   added inside `ask_yes_no` itself it silently changes every other caller
   (e.g. `_repos_remove`'s "Also delete the stored token?", line 2513,
   default `n`) to auto-answer under CI/non-interactive runs — a scope leak
   "Out of scope" never names. Must scope this to `codex deny`'s call site,
   not shared infra, or explicitly bless the blast radius.

2. **AC9 — BLOCKING, wrong helper named.** `_isolate_extras_env`
   (`smoke/_core.py:95`) is purpose-built for `install-claude-extras.sh`
   (git-config + gh-meta-cache isolation); no existing `_codex_opted_in`
   test uses it. Every such test sources via `_source_vibe_call`, which
   defaults to `**os.environ` (the REAL `$HOME`) unless the caller
   explicitly overrides `HOME` per-call, as `checks_01` does by hand.
   Following AC9 literally risks tests reading/writing the developer's real
   `~/.vibe/codex-allow` — the exact bug class task_035/gh-meta-cache was
   already fixed for. Say "manual `HOME` override" instead.

3. **AC2 — BLOCKING, unspecified portability.** "mode grants group/other any
   bit" needs an octal-permission check with no precedent in this file: the
   only permission-adjacent code is the dual `stat -f %m / stat -c %Y`
   mtime fallback (line 4498) for BSD-vs-GNU `stat`, and vibe's own header
   says macOS is primary. `stat -f '%Lp'` vs `stat -c '%a'`, and `find
   -perm`, all diverge BSD-vs-GNU too. Name the portable idiom or this AC
   can't be implemented consistently on the project's own two targets.

4. **AC1 — BLOCKING, message-precedence ambiguity.** `_codex_opted_in`
   already has three `⚠` branches when the marker itself fails verification
   (non-worktree, committed, unverifiable — lines 1626-1641). The new
   "Marker-only" message must fire *only* when those three pass and just
   the registry is missing, but "marker-only" reads equally as "the marker
   file merely exists" — a committed-marker+no-registry case could wrongly
   emit "run vibe codex allow" instead of the existing COMMITTED warning.
   State explicitly: existing branches short-circuit before `codex_allowed`
   is even consulted.

5. **AC8 — BLOCKING, TODO closure over-broad.** TODO.md line 81 bundles four
   follow-ups: the host-side registry (this task), unguarded `auth.json`
   reads, missing hardened-idiom coverage for `/learnings`/`/zotero`, and
   extending marker-deny to `/repos/*/.vibe-allow-codex`. "closed in the
   same commit" licenses deleting the whole bullet though three payloads go
   untouched. Require splitting: close only the registry clause, re-file
   the rest as its own still-open line.

6. **AC2/AC4/AC5 — MINOR, asymmetric hardening.** `codex_allowed` fails
   closed on a symlinked/insecure registry file, but AC5 (`list`) doesn't
   say it applies the same guard before enumerating — a user could see an
   entry `codex_allowed` silently refuses, making `list` an unreliable
   audit surface. AC4 (`deny`)'s remove-rewrite also isn't told to refuse a
   symlinked file first. Low real risk (`~/.vibe` is host-only), but worth
   naming rather than leaving silent.

7. **AC4 — MINOR, wording.** `docker ps -aq` (no status filter) matches
   stopped containers too, so "Stop the running container now" can fire on
   one already stopped. Harmless (`docker stop` no-ops) but the prompt text
   is then false; say "the container".

8. **AC9 — MINOR, coverage gap.** The fixture matrix never exercises
   "committed marker + registry present" or "non-worktree marker + registry
   present" — exactly where concern 4's ambiguity would regress silently.

## Verdict

**revise**
