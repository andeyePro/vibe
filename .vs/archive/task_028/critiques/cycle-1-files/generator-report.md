# Generator report — task_028, cycle 1

Baseline: `c68707d`. Branch `main`. No commits, no pushes, no ssh, no `vibe` invocations.

## What I did

### 1. Fragment merges (`devcontainer/claude-md/`)

- **`learnings.md`** now carries the whole `/learnings` subsystem: the library
  reference (old `learnings.md`), the write-confirm hook trust model (old
  `learn-hook.md`) and cross-repo auto-promotion (old
  `feedback-auto-promote.md`). Three H2/H3 sections, first line still a `# ` H1.
- **`auto-memory-scope.md`** now carries per-project memory scope (old file)
  plus transcript search (old `conversation-history.md`), including all three
  `jq` recipes and the `ls -t` newest-first note.
- **`content-guard.md`** rewritten as a 502-word operating summary that names
  `README.md`'s `### Content guard` section for rationale and worked examples.
  Every rule and knob kept — see the inventory below. Only *rationale* was
  delegated, and only where README actually covers it (I read README's section
  first: it covers the two tiers, the non-zero exits, the three clearing
  mechanisms, the built-in allowlist and `vibe audit --history`; it does NOT
  cover commit-identity, `path-warn:` or the stale-scanner caveat, so those
  stayed in full in the fragment).
- `learn-hook.md`, `feedback-auto-promote.md`, `conversation-history.md`
  deleted (`git rm`). Directory now holds exactly 13 `.md` files; the other ten
  fragments are byte-identical to `c68707d` (verified by hash comparison in the
  scratch check).

### 2. Single Fable-grant definition

- New `### Fable grant (\`--fable-subagents\`)` subsection inside `vs.md`
  § Model economy — the one full definition: permits/never forces, Model plan
  records `Fable rung: pre-authorised (--fable-subagents)`, ladder may take the
  rung without a fresh ask, never Fable for mechanical roles (Tester, Spec
  Critic, cost admin) or scoped small generations, `--fable-gen` forces a start
  and still quotes estimated credits, and the `vibe --fable` LAUNCHER flag is
  distinct (chair/session model only, no subagent spend).
- `vs.md` § Flags `--fable-subagents` bullet cut 131 → 19 words, still naming
  `§ Model economy`. Escalation-ladder bullet, Step-2 Model-plan bullet and the
  standalone "Honor `--fable-subagents` at spec-writing time" paragraph (the
  last deleted outright) are now pointers.
- `vss.md` lines 21 and 92 and `vsss.md` line 27 replaced with pointers. Every
  line mentioning `--fable-subagents` in those two files also contains
  `/vs § Model economy`; `never forces` / `mechanical roles` / `sets only the
  chair` / `chair model only` / `authorises no subagent spend` occur zero times
  in either; `--fable-subagents` occurs twice in `vss.md`, once in `vsss.md`.
  vsss's "The grant PERSISTS across auto-resume relaunches … the recorded
  Initial-plan grant IS the authority; never demand a fresh flag mid-run"
  clause survives verbatim in substance.
- To reach AC8's 12,700-word ceiling I also had to compress two adjacent
  restatements that are not strictly Fable-grant text (flagged here for the
  Evaluator): the `/vsss --sessions X` bullet, whose long restatement of
  § Auto-resume across halts became a pointer to that section (which is
  untouched and still holds every rule, including the `X-1` arithmetic the
  smoke suite pins), and a handful of one-to-three-word tightenings inside
  vs.md § Model economy / § Cost. No rule changed in either.

### 3. `smoke-test.py`

- Constants renamed and repointed: `FEEDBACK_AUTO_PROMOTE_MD` → `LEARNINGS_MD`
  (`learnings.md`), `CONVERSATION_HISTORY_MD` → `AUTO_MEMORY_SCOPE_MD`
  (`auto-memory-scope.md`), `LEARN_HOOK_MD` → `LEARN_HOOK_RULES_MD`
  (`learnings.md`). No constant points at a deleted file; the three deleted
  filenames appear nowhere in `smoke-test.py`.
- `test_task009_learn_hook_md_exists`, `test_feedback_auto_promote_fragment`,
  `test_conversation_history_fragment` keep every assertion (same sentinels,
  same intent) and now read the merged fragments; docstrings/labels updated to
  say where the rules moved. `test_learn_docs_no_host_stage_all_footgun`
  needed no edit (it iterates over the constants) and still passes:
  `learnings.md` contains neither `git add .` nor `$VIBE_LEARNING_PATH`.
  `test_workspace_is_the_repo_fragment` untouched. No `test_task028_*` added.
- **One unavoidable extra edit, flagged for the Evaluator:**
  `test_fable_subagents_flag_docs` hard-coded literals that AC7 now *forbids* —
  most sharply `"chair model only, no subagent authorisation" in vss` and
  `"per-invocation consent, not a default" in vss`, plus several vs/vsss
  wordings that moved into the new subsection. I rewrote that one pre-existing
  test to pin the new single-definition structure: it still asserts every rule
  it asserted before (grant recorded in Model plan, never mechanical roles,
  permits/never forces, permission-not-routing, ask-gate unchanged, ladder
  honours the standing grant, launcher distinction, `--fable-gen` forces,
  Step-2 point-of-use, vsss propagation + audit note + persistence), and adds
  two structural checks that vss.md and vsss.md only ever point at
  `/vs § Model economy`. This is the same class of necessary edit as the
  deleted-fragment constants: the spec's AC7 and the old literals cannot both
  hold.

### 4. Docs

- `CLAUDE.md` line 13 fragment list: `learn-hook` removed; now
  `(web-research, ssh-discipline, learnings, auto-memory-scope, content-guard,
  vibe-cli, workspace-is-the-repo, …)`.
- Grep of `README.md ONBOARDING.md CONTRIBUTING.md MANUAL-TESTS.md
  devcontainer/` for the three filenames: zero hits before and after (only
  CHANGELOG.md's historical entries mention them, which AC9 permits).
- `CHANGELOG.md`: new `[x] **task_028 …**` entry at the top of `## 2026-09-02`.
- `TODO.md` not ticked by me (the chair closes it on pass). It shows as
  modified in `git status` because the chair added the task_028 backlog line
  before this cycle started.

## Rule inventory (AC11 pre-check)

### `git show c68707d:devcontainer/claude-md/learn-hook.md` → `learnings.md`

| Rule from the deleted file | Where it lives now |
| --- | --- |
| Mount is read-write despite `readonly` (Docker/OrbStack `fakeowner`, task_009) — trust comes from a hook, not the mount | § The write-confirm hook — do not bypass the hook, ¶1 |
| PreToolUse hook on Write/Edit/MultiEdit; `file_path` under `/learnings` ⇒ `permissionDecision: ask`; user prompt; yes proceeds, no blocks | same ¶1 (`permissionDecisionReason` named; the literal JSON sample dropped — illustration, not a rule) |
| No path traversal; hook normalises with `realpath -m`; `/learnings/../etc/passwd` recognised as outside | bullet 1 |
| Do not split one logical write into smaller operations; each Write/Edit/MultiEdit checked independently | bullet 2 |
| Never suggest disabling/removing `guard-fs.sh`; security boundary, not a convenience filter; respecting it is not optional | bullet 3 |
| `guard-bash.sh` best-effort over shell write idioms (full 13-idiom list) and its blind spots (variable-indirection, `python3 -c`/`perl -e`/`node -e`, `eval`/`bash -c`) | ¶ after the bullets |
| `guard-fs.sh` is the primary gate (reads `tool_input.file_path`) | same ¶ |
| `/learn` flow: verify mount → host-format filename → preview → Write that triggers the prompt | ¶ `/learn <pattern>` |
| Push is host-only; matters only for a git-backed public-mode library; auto-syncing library needs nothing; `vibe learn --push` is the dedicated path (not built yet); manual fallback stages only the single new entry file, never the whole tree | same ¶ |
| Never paste a `VIBE_LEARNING_PATH` variable into a Mac shell (unset there ⇒ `$HOME`) | same ¶ |
| "Why this is strictly stronger than before" | dropped — pure rationale, contains no imperative |

### `git show c68707d:devcontainer/claude-md/feedback-auto-promote.md` → `learnings.md`

| Rule | Where |
| --- | --- |
| Always active in every vibe container | implicit: the fragment is injected unconditionally |
| Per-project memory does not propagate; `/learnings` is the cross-project store; offer to promote on a `feedback` save | § Auto-promote cross-repo feedback memories, ¶1 |
| Propose only when ALL four criteria hold | ### When to propose promotion, items 1–4 |
| Behavioural-rule-not-project-fact criterion with YES/NO example lists | item 1 (two YES examples trimmed for budget; the YES/NO discrimination and its shape are intact) |
| Applies regardless of project (what travels vs what doesn't) | item 2 |
| Not already promoted — scan `/learnings` first; duplicates degrade signal-to-noise | item 3 |
| User has not opted out ("stop asking me…" or `VIBE_AUTO_PROMOTE=0` via `~/.vibe/config`) | item 4 |
| Ask in the SAME response, ONE line, no preamble; exact prompt `Cross-repo applicable - save to /learnings?  Y / n / never-ask` | ¶ + fenced block |
| `Y` → `/learn <distillation>`; the PreToolUse hook prompts again — trust boundary, not redundancy | ¶ after the block |
| `n` → drop it; memory stays per-project | same ¶ |
| `never-ask` → session suppression + surface `echo VIBE_AUTO_PROMOTE=0 >> ~/.vibe/config` | same ¶ |
| Do NOT auto-write to `/learnings` without proposing | final ¶ |
| Do NOT promote project-specific memories; default to NOT promoting when unsure | final ¶ |
| One prompt per cross-repo-applicable memory save; never batch | final ¶ |
| Do NOT propose if the user asked you not to memorise this turn | final ¶ |
| "Pairs with" three-layer note (trigger / quality gate / security boundary) | dropped — descriptive; each of the three roles is still stated at its own point of use |

### `git show c68707d:devcontainer/claude-md/conversation-history.md` → `auto-memory-scope.md`

| Rule | Where |
| --- | --- |
| Search the on-disk transcripts before saying "I have no record" | § Search the transcripts…, ¶1 |
| Path `~/.claude/projects/<slug>/<session-uuid>.jsonl`; vibe slug `-workspace`; glob `~/.claude/projects/-workspace/*.jsonl` | ¶2 |
| Persist in the `vibe-claude-config` Docker volume across restarts; do NOT travel between machines; not in the repo; cross-machine persistence via `/learnings`, TODO.md, CHANGELOG.md, committed code | ¶2 |
| Schema: user prompts are `type: "user"` with string `message.content`; `tool_result`-list records are tool output — filter out; assistant text is `type: "assistant"` → blocks of `type: "text"`; skip `thinking` and `tool_use` | ¶3 |
| Three `jq -r` recipes (prompts by keyword, assistant text by keyword, ordered single-file replay) | fenced bash block |
| `ls -t … | head -5` newest-first, because the UUID filename carries no time order | same block |
| Search when the reference is greppable; ask for clarification when it isn't | ¶4 |
| Summarise concisely; quote at most 1–2 short lines for attribution | ¶4 |
| Do not duplicate into a parallel committed log — the transcripts already are the log; only on an explicit cross-machine request use `/learnings`, `TODO.md` or a fresh markdown file, never a transcript clone | final ¶ |

### `git show c68707d:devcontainer/claude-md/content-guard.md` → rewritten `content-guard.md`

Every rule/knob below is present in the 502-word rewrite:
BLOCK class and its five secret shapes · WARN class and its four PII shapes ·
`commit-identity` WARN, the four exempt noreply-class addresses, the
`git config user.email` fix, allowlisting it, and `vibe audit --history`
scanning all history identities · WARN is a severity label, both tiers exit
non-zero, both clear the same way · `pre-commit`/`commit-msg` scan both tiers,
`pre-push` re-scans BLOCK only on the outgoing range and why ·
`--no-verify` bypasses git-natively · `VIBE_CONTENT_GUARD=off` /
`VIBE_ALLOW_COMMIT=1` one-invocation override, never silent, loud stderr naming
the override and skipped rule ids, preferred over disabling ·
`.vibe-content-guard-off` repo-root marker, no scanning at all, for
end-to-end-private repos · `.vibe-content-allow` ERE-per-line, comments/blanks
ignored, case-sensitive, whole-flagged-line match · built-in allowlist
(`Co-Authored-By:`/`Signed-off-by:`, `noreply@anthropic.com`,
`*.users.noreply.github.com`) · `path-warn:<glob>` is a different entry kind,
bash `case` glob on the repo-relative path, structurally excluded from the
`grep -E` loop, `--staged`/`--range` only, BLOCK-tier-only scanning with
**BLOCK rules always still fire**, `*` crosses `/`, escape `[`/`]`/`?`
yourself, empty `path-warn:` inert and never match-all, `path-warn:*` accepted
deliberately, message/history modes have no path, stale pre-task_023 scanner
caveat with the two "never rely / never co-locate" rules, vibe's two shipped
entries · `vibe audit` host-side from the project dir, `--history` default
both tiers incl. deleted content, exit 1 only on BLOCK, WARN-only exits 0 but
still lists, `--staged` on demand, only reports and never rewrites history
(`git filter-repo` / BFG separate).

Delegated to `README.md` § `Content guard` (rationale README already carries):
why non-interactive commits make both tiers exit non-zero, and the worked
examples. Dropped as illustration, not rule: the list of example literals
vibe's own `.vibe-content-allow` covers (`/Users/martin`, the example IPs,
`mcomz.local`/`pi02.local`, the SECURITY.md maintainer link) and the aside that
brain2 reader containers never commit brain2.

## Word counts

| | before (`c68707d`) | after |
| --- | --- | --- |
| `cat devcontainer/claude-md/*.md \| wc -w` | 8,060 | **6,149** (limit 6,160) |
| `learnings.md` | 469 (+610 learn-hook +652 auto-promote = 1,731) | **709** (floor 650) |
| `auto-memory-scope.md` | 225 (+509 conversation-history = 734) | **489** (floor 450) |
| `content-guard.md` | 1,146 | **502** (band 400–600) |
| fragment files | 16 | **13** |
| `cat vs.md vss.md vsss.md \| wc -w` | 13,062 | **12,696** (limit 12,700) |
| — `vs.md` | 5,933 | 5,746 |
| — `vss.md` | 2,084 | 1,995 |
| — `vsss.md` | 5,045 | 4,955 |

Injected-context saving: 1,911 words off every session's `~/.claude/CLAUDE.md`
managed block (≈2.5k tokens), plus 366 words off the `/vs` family.

## Verification

- `python3 .vs/cycle-1/scratch-tests/ac_check.py` (my own mechanical check of
  AC1–AC4, AC6–AC9, AC12–AC13): **RED first** — 45 passed / 36 failed on the
  untouched baseline. **GREEN after** — `81 passed, 0 failed`, exit `0`.
- `python3 code-check.py` → exit **0** ("shellcheck clean across 19 files").
- `python3 smoke-test.py` → **`✓ smoke tests passed`**, exit `0`
  (2,174 checks; run log kept out of the repo).
  - An earlier run of the same suite, before I unwrapped the new § Fable grant
    paragraph, failed 6 checks: 4 were the fable-flag literals (the paragraph
    was hard-wrapped, so multi-word literals straddled newlines — fixed by
    writing the subsection as one long line, matching vs.md's house style), and
    2 were **pre-existing flakes unrelated to this task** under heavy machine
    load (`AC6 T1: vibe_container_kill_claude invoked`, a watchdog timing test,
    and `task_027 AC4 idempotent output`, a two-run byte-comparison of a
    generated block). Both passed on the clean re-run; neither touches a file
    in this change set.

## Scope

`git diff --name-only c68707d` lists exactly:
`.vs/tasks.json`, `CHANGELOG.md`, `CLAUDE.md`, `TODO.md`,
`devcontainer/claude-md/{auto-memory-scope,content-guard,learnings}.md`,
the three deletions under `devcontainer/claude-md/`,
`devcontainer/commands/{vs,vss,vsss}.md`, `smoke-test.py`. All inside AC10's
allow-list. `install-claude-extras.sh` untouched. The index is left clean
(nothing staged). My own artifacts live under `.vs/cycle-1/`, which
`.gitignore` excludes (`/.vs/cycle-*/`), so they never appear in the diff.

`git add -A -n` additionally reports the chair's own untracked files
(`.vs/briefs/`, `.vs/spec.md`, `.vss/sessions/2026-09-02T16-04-16Z.md`) — not
mine, not staged, and untracked so they do not appear in
`git diff --name-only c68707d`.

## Snags worth the Evaluator's eye

1. **AC8 is tight.** 12,696 of 12,700, and 6,149 of 6,160 on the fragments.
   Reaching the 362-word cut needed more than the eight Fable lines held; see
   §2 above for the two adjacent compressions I took, and shout if either is
   over the line — there is no headroom left to restore words without
   re-opening one of those cuts.
2. **`test_fable_subagents_flag_docs` had to be rewritten** (§3). AC7 and the
   old literals are mutually exclusive.
3. **Recoverable mistake, disclosed:** while updating `.vs/tasks.json` I first
   rewrote it with `json.dump`, which reflowed the whole file; `git checkout`
   to undo that also reverted the chair's *uncommitted* task_028 entry. I
   restored the entry byte-for-byte from the copy I had read (same field order,
   same description, same 1-space indent, no trailing newline), then applied
   only the `implementation_status: pending → complete` change plus a
   `last_modified` bump. The diff is now `9 insertions(+)` and nothing else.

## Final state (re-verified after the last edit)

- `python3 code-check.py` → exit `0`
- `python3 smoke-test.py` → exit `0` (`✓ smoke tests passed`)
- `python3 .vs/cycle-1/scratch-tests/ac_check.py` → exit `0` (81/81)
- `git diff c68707d > .vs/cycle-1/diff.patch` → 1,167 lines; index reset, nothing staged.

`implementation_status` for task_028 in `.vs/tasks.json` set to `complete`
(status-field mutation plus a `last_modified` bump; nothing else in that file
changed).
