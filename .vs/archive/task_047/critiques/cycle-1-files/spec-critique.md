# Spec Critic — task_047 `spec-draft-codex-skills.md`

## Concerns

1. **BLOCKING, AC4.** `-a never` is not a `codex exec` flag. Verified live
   against the installed 0.154.0 binary (the same release F7 cites):
   `codex exec --help` lists no `-a`/`--ask-for-approval` option, and
   `echo hi | codex exec -a never --json -` fails with
   `error: unexpected argument '-a' found`. Approval is controlled only via
   `-c approval_policy=<val>` (as the existing `codex()` already does),
   `--approve-for-me`, or `--dangerously-bypass-approvals-and-sandbox`. Every
   write-role Astra dispatch built to this vector fails to start. Also
   inconsistent with `vibe-delegate.mjs`'s own `codex()`, which never uses
   `-a`.

2. **BLOCKING, AC3/AC4.** Schema/output-file collision with the real repo.
   `codex()` today writes `schema.json`/`answer.json` via `join(cwd, ...)`
   where `cwd` is always a throwaway `mkdtempSync` scratch dir. AC4 requires
   the write roles' process `cwd` to literally *equal* `--cwd` (the
   workspace) — AC8's own test checks this against the fixture's recorded
   `os.getcwd()`. If the Generator reuses the existing plumbing unchanged,
   `schema.json`/`answer.json` land inside the user's actual git working
   tree on every Generator/Tester dispatch: untracked cruft in `git status`,
   exactly what CLAUDE.md's project-hygiene rule warns against, and nothing
   in AC2/AC7 gitignores it. AC4 never says where these two files live for
   write roles — this is a real design gap, not a doc nit.

3. **BLOCKING, AC4.** Claude write-role argv drops
   `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` (present in the
   existing `claude()`/read-only-role argv) with no stated reason, while
   keeping `--setting-sources user`. An unattended write-role subprocess can
   therefore load whatever MCP servers are configured at the user level —
   `guard-bash.sh`/`guard-fs.sh` only parse `Bash`/`Write`/`Edit`-shaped
   `tool_input` (per the Codex hook-name mapping and the guards' own known
   shapes); neither mediates `mcp__*` calls at all. This is exactly a
   capability a role subprocess could reach that the lead's own `ask`/
   `review` calls always deny, and it contradicts the task summary's "same
   hooks and firewall as the lead" framing.

4. **BLOCKING, AC4.** No `--tools` allowlist is named for the Claude write
   role at all (the vector omits `--tools ''` without naming a replacement).
   "the tools that role needs" (task summary) is never pinned down: the
   subprocess gets Claude Code's full default toolset, including `Task`
   (nested subagent spawning) and `WebFetch`/`WebSearch` — materially more
   unsupervised reach than a Generator dispatched as a genuine Claude Code
   subagent under a watched top-level session. A golden-argv test can only
   diff against what the Generator implements; it cannot catch a
   should-be-present-but-absent flag.

5. **BLOCKING, AC1(c)/AC6.** "the `$`-form and the `/`-form are the same
   command" is false for the only channel this task ships. The supervisor
   and `vibe --agent codex` (the only routes that make `/vs` reachable
   another way) are explicitly Out of scope (items 6/7). Per F7/F6 already
   in `docs/codex-integration-plan.md`, Codex's own composer rejects an
   unrecognized `/vs` before submission — the text never reaches skill
   resolution — and D3 in the same doc concludes "`/vs` in the Codex TUI
   cannot be a hook or a file vibe owns." Shipping SKILL.md text that says
   the two forms are interchangeable contradicts the plan's own verified
   finding and will mislead a user who types `/vs` straight into
   "Unrecognized command" with no pointer to `$vs`.

6. **BLOCKING, AC1/AC6, cross-cutting.** No substitution for composed
   commands. `vss.md`/`vsss.md` invoke `/vs` as a nested step ("whichever
   tool the planner picks", "run /vs Step 3b"); under Claude Code the
   harness resolves nested slash-commands, but per F3, Codex only re-scans
   the *user's originally typed* text for `$name` mentions — a skill body's
   own generated output referencing `/vs`/`$vs` mid-turn does not retrigger
   resolution. AC1's substitution table has no entry for this case, so
   `$vss`/`$vsss` under Codex reach "now run /vs" with nothing to actually
   load `vs.md`. Not covered by AC1(a)-(d), and no AC8 test pins the
   expected behavior since none is specified.

7. **MINOR, AC5.** Under-specified whether a legitimate `status: "blocked"`
   reply (a completed turn/result, not a `turn.failed`/`is_error`) exits 0
   or non-zero. AC5 only states the negative case ("never a `done`" on
   failure); it never says a clean "blocked" should still exit 0 so an
   orchestrating skill can read `report`/`status` and decide — this matters
   because the SKILL bodies (AC1) are shell-driven, not JS callers.

8. **MINOR, AC1.** "carries the substitution table below" is not
   mechanically pinned — AC8 says only "body assertions" for the SKILL.md
   files. A near-paraphrase or partially-reordered table would satisfy a
   loosely written test while failing to specify Codex's actual behavior
   for `Grep`/`Glob` (used once in `vs.md`, §288) or `TodoWrite`/
   `ScheduleWakeup`-adjacent primitives beyond the six listed — the table
   should be checked for completeness against every Claude-only primitive
   actually present in `vs.md`/`vss.md`/`vsss.md`, not assumed exhaustive.

## Verdict

**revise**
