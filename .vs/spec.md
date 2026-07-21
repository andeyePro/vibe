# Spec — task_026: `vibe pat [repo]` PAT rotation + launch-time 401 reprompt

## Task summary

vibe has no PAT rotation path: `setup_token` prompts only when a repo has NO stored token, so an expired/revoked fine-grained PAT means hand-editing `~/.vibe/tokens`. This task adds (1) a host-side `vibe pat [owner/repo]` subcommand that re-prompts (hidden input) and overwrites the stored PAT for a repo, and (2) a launch-time check that detects a definitively-rejected stored token (HTTP 401 from api.github.com) and auto-invokes the existing `setup_token` prompt at exactly the moment rotation bites. Rotation then needs no rebuild: `GITHUB_TOKEN` flows via `remoteEnv` through `devcontainer exec`, re-resolved every launch.

## Pinned contract

- **Subcommand parsing**: `vibe pat` is a host-side subcommand parsed where `vibe learn` is parsed, and like `vibe learn` it never launches a container. Accepted forms: `vibe pat` (repo inferred from the current directory via the existing `detect_github_repo`; error to stderr with a one-line hint if detection fails, exit 1) and `vibe pat <owner/repo>` (explicit slug). `vibe pat --help` or `vibe pat -h` prints a short usage block (stdout, exit 0) BEFORE slug validation. Any other argument count → one-line usage error to stderr, exit 1.
- **Slug validation**: the explicit slug must be `owner/repo` with exactly one `/` and both segments non-empty and matching `[A-Za-z0-9._-]+`. Invalid → one-line error to stderr, exit 1. Reserved slash-free token keys (`ZOTERO_API_KEY`, `OPENPROJECT_MCP_URL`, `OPENPROJECT_MCP_BEARER`) are structurally excluded by the one-`/` rule; no special handling.
- **`vibe pat` flow** (function `rotate_token <repo>`): first line of normal output is exactly `Repo: <owner/repo>`; second line is exactly `stored token found — it will be replaced` or `no stored token yet`; NEVER print any part of any token value. Print the plain line `https://github.com/settings/personal-access-tokens` before the prompt; do NOT auto-`open` a browser. Prompt via `read -rsp` (hidden input; reads stdin fine when stdin is not a tty, which is how smoke tests feed it) — and because `vibe` runs under `set -euo pipefail`, the read MUST be errexit-guarded so immediate EOF cannot abort before the message prints: use the established `_learning_capture` idiom (`if ! IFS= read -rsp "..." token; then token=""; fi` or equivalent; see vibe ~1438). Empty input — whether a lone newline OR immediate EOF/closed stdin — → `aborted — token store unchanged` to stderr, exit 1, store byte-identical. Non-empty → `save_token "$repo" "$token"`, print `✓ Token saved for <owner/repo>. Takes effect on the next vibe launch (no rebuild needed).`, exit 0.
- **401 probe** (function `stored_token_rejected <repo> <token>`): one `curl` invocation, called as plain `curl` (PATH-shimmable), of the form `curl -s -o /dev/null -w '%{http_code}' --max-time 5 -K -` with the URL `https://api.github.com/repos/<owner/repo>` in argv and the auth header supplied ONLY via the `-K -` config read from stdin (heredoc/pipe writing the single line `header = "Authorization: Bearer <token>"`), so the token never appears in curl's argv (`ps`-visible) and never touches disk. (The config line is unescaped: tokens containing `"` or `\` are out of contract — GitHub PAT charset is alphanumeric+`_`, and the fixture token complies.) Decision rule: capture the `-w` output; ignore curl's own exit status entirely; return 0 (rejected) iff the captured string is exactly `401`; every other outcome — `200`, `403`, `404`, `5xx`, `000`, curl non-zero exit, empty output — returns 1. Fail-open by design: a network flake or scope oddity must never block a launch or trigger a false reprompt.
- **Call-site wrapper** (function `maybe_reprompt_stored_token <repo> <token>`, sourceable and unit-testable): returns 0 immediately (no probe) when `VIBE_PAT_CHECK` = `0` OR when `<token>` is empty (an empty lookup result is the no-stored-token case — `setup_token` will run anyway; probing an empty bearer is a bug). Otherwise calls `stored_token_rejected`; on rejection prints exactly `  ⚠ Stored PAT for <owner/repo> was rejected by GitHub (expired or revoked) — let's replace it.` (stderr or stdout — Generator's choice, but the string is pinned) and calls `setup_token "$repo"` (existing flow: prompt, save, set `GITHUB_TOKEN`; its empty-input branch already degrades to launching without GitHub auth). On non-rejection, does nothing. The wrapper ALWAYS returns 0, whichever branch runs (never propagate `stored_token_rejected`'s status) — its bare one-line call site sits under `set -e`, and a non-zero return would turn every healthy launch into a hard failure.
- **Launch-path integration**: in the launch path, immediately after `GITHUB_TOKEN` is resolved from the token store (the branch where `lookup_token` returned a value — vibe's existing `GITHUB_TOKEN=$(lookup_token "$GITHUB_REPO")` non-empty case), insert the single call `maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"`. Never called after a fresh interactive paste (no prompt loop). All logic lives in the wrapper so smoke tests can source and drive it; the call site itself is one line.
- **Opt-out**: `VIBE_PAT_CHECK=0` (env / `~/.vibe/config`) skips the probe via the wrapper's guard (the `vibe pat` subcommand is unaffected). Any other value, or unset → check runs.
- **No token values in output**: neither the subcommand nor the probe may echo token bytes (no masked previews). No new `set -x`. Accepted residual risk, stated deliberately: the token IS present in the in-process shell variables and in the stdin pipe to curl — that is process-internal and acceptable; the `ps`-argv exposure class is eliminated by the `-K -` mechanism above.
- **Help text**: `vibe --help` gains a `vibe pat [owner/repo]` line (rotate/overwrite the stored GitHub PAT) in the style of the `vibe learn` block, and the pat help text includes the phrase `HOST shell` (the runs-on-host caveat).
- **Fixture token**: all tests use the literal `ghp_task026_fixture_token` as the token value, everywhere a token is fed.

## Files in scope

- `vibe` — `rotate_token`, `stored_token_rejected`, `maybe_reprompt_stored_token`, subcommand parsing (incl. `--help`/`-h`), one-line launch-path call site, help text.
- `README.md` — short addition where PATs/tokens are documented: rotation via `vibe pat`, and the launch-time 401 auto-reprompt (must mention `401`).
- `MANUAL-TESTS.md` — new entry: end-to-end revoked-PAT launch reprompt, and `VIBE_PAT_CHECK=0` suppressing it (must mention `VIBE_PAT_CHECK=0`). Manual because it needs live GitHub + docker.
- `TODO.md` + `CHANGELOG.md` — per repo convention, same commit as the closing change.
- NOT in scope for Generator: `smoke-test.py` `test_task026_*` functions (Tester-owned; cycle-anchored freeze per harness rule).

## Acceptance criteria

1. `vibe pat a b c` (too many args) and `vibe pat not-a-slug` each exit 1 with a one-line error on **stderr**; nothing is created or changed in the token store. `vibe pat --help` exits 0 and prints usage on stdout.
2. `vibe pat owner/repo` with `ghp_task026_fixture_token` piped on stdin overwrites an existing `owner/repo=` line in a tmp-`$HOME` token store, preserves all other lines (including a `ZOTERO_API_KEY=` line and an `OPENPROJECT_MCP_BEARER=` line with trailing `=` padding), leaves the file `chmod 600`, exits 0, and stdout contains the pinned `Repo: owner/repo` and `✓ Token saved` lines.
3. `vibe pat owner/repo` with empty stdin exits 1, emits the pinned abort line on stderr, and leaves the token store byte-identical — tested BOTH ways: immediate EOF (closed/0-byte stdin) and a lone `\n`.
4. `vibe pat` with no arg in a directory where `detect_github_repo` fails exits 1 with the stderr hint; in a git checkout with an origin remote it prints `Repo: <slug>` where `<slug>` is what `detect_github_repo` reports for that checkout (test feeds closed/empty stdin so the run terminates via the abort path rather than blocking at the prompt).
5. `stored_token_rejected` (sourced directly, tmp `$HOME`, PATH-shimmed `curl`): shim emitting `401` → returns 0; shims emitting `200`, `404`, `000`, and a shim that exits non-zero after emitting nothing → each returns 1.
6. The AC5 shim logs its argv and its stdin to files; assertions: argv contains `api.github.com/repos/owner/repo` and `-K`; stdin capture contains `Authorization: Bearer ghp_task026_fixture_token`; argv does NOT contain the fixture token.
7. For every AC2/AC3/AC5/AC6 run, the fixture token string is absent from captured stdout+stderr.
8. `maybe_reprompt_stored_token` (sourced, with `stored_token_rejected` and `setup_token` overridden by logging stubs after sourcing): (a) `VIBE_PAT_CHECK=0` → neither stub called, returns 0; (b) empty token arg → neither stub called, returns 0; (c) token present + rejection stub returns 0 → warning line emitted (pinned string), `setup_token` stub called once with the repo arg, AND the wrapper itself returns 0; (d) token present + rejection stub returns 1 → `setup_token` stub not called, no warning, AND the wrapper itself returns 0 (all four branches a–d assert return 0 — the bare `set -e` call site makes any non-zero return a launch-killer). Plus one static assertion that the `maybe_reprompt_stored_token "$GITHUB_REPO" "$GITHUB_TOKEN"` call line appears in the launch path inside the stored-token branch (i.e. between that branch's opening and its `fi` — a placement-aware grep, not bare text presence, so an unconditional placement that would probe a freshly-pasted token fails the test).
9. `vibe --help` output contains a `vibe pat` line AND the phrase `HOST shell` within the pat help text; `python3 code-check.py` passes; every pre-existing `smoke-test.py` test function (all functions other than the new `test_task026_*` additions), unchanged, still passes (regression gate).
10. `README.md` contains both `vibe pat` and `401`; `MANUAL-TESTS.md` contains both `vibe pat` and `VIBE_PAT_CHECK=0`.

## Out of scope

- Any in-container `/PAT` or chat-based token entry (deliberately rejected: transcript would hold the secret).
- Validating a freshly-pasted token (no post-paste probe; no prompt loops).
- Treating `403`/`404` as rejection, SSO handling, pre-expiry warnings, GitHub API scope introspection.
- Shared-repo (`VIBE_SHARED_TOKEN_*`) launch-time validation — `vibe pat <slug>` covers rotating their stored lines; probing every shared repo at launch is out.
- Auto-opening a browser from `vibe pat`.
- Changes to `save_token` / `lookup_token` / `remove_token` / `setup_token` semantics.

## Test location

`smoke-test.py` — Tester appends new `test_task026_*` functions (host-side, no docker, no network; PATH-shim for curl; tmp `$HOME`; source-the-functions convention per `test_token_helpers`). The sourced `vibe` carries `set -euo pipefail`, so any bare call to a function expected to return non-zero (`stored_token_rejected` in AC5, the stubs' callers in AC8) MUST be bracketed `set +e; …; set -e` (precedent: the task_017 c2 lock tests, e.g. `test_task017_c2_lock_release_wrong_project_refused_intact`) or written as `if fn; then … else … fi` — never `fn; echo $?` bare. Immutability is cycle-anchored per harness rule: once committed, `test_task026_*` functions are frozen for this task; Generator never edits them.

## Proposed budget

3 cycles — single-file bash feature with established test conventions; cycle 2+ reserved for call-site/quoting nits.

## Model plan

- Generator: sonnet, ceiling opus. Difficulty: low-medium — three small bash functions + parsing + docs, but quoting/exit-code discipline matters.
- Tester: haiku. Spec Critic: sonnet. Planner/Evaluator: session model (Fable 5 chair).
- Fable rung: not pre-authorised.
