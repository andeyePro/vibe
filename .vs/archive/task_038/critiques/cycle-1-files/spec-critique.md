# Spec Critique — task_038 `--aux` model slot

## Concerns

1. **BLOCKING (AC1)** — No env-injection mechanism named. The codebase has a hard rule for anything secret: cross into the container via `remoteEnv` + a `${localEnv:NAME}` passthrough, with the export done at **top-level shell scope**, never inside `_build_override_config`'s `$(...)` subshell (exports there die with it — the exact trap the file documents three times), and never `containerEnv` (that bakes the literal value into the rendered JSON on disk). This is the established pattern for `GITHUB_TOKEN`/`ZOTERO_API_KEY`/`OPENPROJECT_MCP_BEARER`. AC1 just says "set … in the container env." A Generator following AC1 literally could pick `containerEnv` or export inside the subshell and both would be silent failures (one leaks the key to disk, the other makes the var vanish). Spec must pin: `remoteEnv` passthrough via `render_devcontainer_with_mounts`, top-level export, mirroring `ZOTERO_API_KEY` exactly.

2. **BLOCKING (AC1, security)** — `~/.vibe/aux` carries a bearer key but is hand-edited by the user (unlike `TOKENS_FILE`, which is only ever written programmatically via `save_token` + `chmod 600`). AC1 says "file created chmod 600" without saying who enforces that on a user-authored file. The spec needs an explicit permission check/warn-or-refuse on read, matching the trust bar already applied to `~/.vibe/tokens`.

3. **BLOCKING (AC5, scope honesty)** — "uses `vibe-aux embed` for the semantic check" doesn't compose with the Out-of-scope line ruling out an embedding index/store. One embed call on the *new* entry can't detect contradictions/duplicates against N existing entries without either indexing them (excluded) or re-embedding all of them every run (not "the single call shape," and slow at scale). As written this AC will ship as a no-op or theatre call. Either scope AC5 down to "the call is wired, dedupe logic is unchanged this cycle" (honest, deferred value) or drop the `/learn` consumer from task_038.

4. **BLOCKING (missing AC)** — no behaviour for "configured but unreachable mid-run." AC2 only covers `VIBE_AUX_URL` unset (exit 2). A live-but-dead endpoint (Ollama not started, LAN drop, 20s timeout) has no stated fallback for AC4/AC5 callers. Add an AC: any `vibe-aux` non-zero exit/timeout is caught by `learn.md`/`vs.md` and degrades to "aux unavailable this run" — never blocks `/learn`'s Write or fails a `/vs` cycle.

5. **BLOCKING (AC6, testability)** — "key never appears in argv" verified via "`ps`-visible argv" is a race: a fast curl call can finish before `ps` samples it, so this isn't mechanical. Specify a deterministic check instead — stub `curl` on `PATH` during the test to dump its received argv to a file, then assert no bearer/key substring appears.

6. **MINOR (AC3, duplication risk)** — the host-side launcher parsing domain names out of `init-firewall.sh`'s shell arrays (split across a `MUST_HAVE_DOMAINS` var and a separate multi-line optional list) duplicates data that can silently desync on a future firewall edit. Either add a drift-detection smoke test tying the two together, or narrow AC3 to the IP-shape check alone (RFC1918/loopback/`host.docker.internal`) and drop the domain-list cross-reference.

7. **MINOR (AC7 / Non-goals)** — the added CLAUDE.md sentence should say explicitly that creating `~/.vibe/aux` (or passing `--aux`) **is** the consent act required by "features that need an API key with no consent gate stay out of core," and that no default endpoint ships — currently that's only implicit in the task summary.

8. **MINOR (AC4, honesty)** — the roadmap explicitly flags local 7–30B models as far below Sonnet for judgment. `vs.md`'s `--aux-review` docs should say plainly this is a low-confidence extra signal, not a peer reviewer, so it isn't mistaken for review-equivalent quality.

9. **MINOR (budget)** — 8 ACs across a hot-file launcher edit, a new bash helper, two harness-doc edits, a new fixture server, and 3 docs is a lot for 3 cycles even at Opus tier; flag as risk for the Planner, not a blocker.

## Verdict

**revise**
