# Spec Critique — iteration 2 — task_038 `--aux` model slot

## Prior blocking items — verified resolved
All five: AC1 env mechanism now pins top-level export + `remoteEnv` `${localEnv:NAME}` (never `containerEnv`), matching `GITHUB_TOKEN`/`ZOTERO_API_KEY` verbatim (confirmed against `/workspace/vibe` lines ~3621, ~3676–3687) with a byte-identical-render smoke test; `~/.vibe/aux` mode-600/ownership refusal is stated; AC5 re-embed design is explicit and honest (0.85 cosine, no index, "tens of entries"); AC5b silent degrade (exit 3 / fallback text / `aux unavailable`) is present; AC6 specifies a stubbed-curl argv+stdin capture, not `ps`. All four MINORs (drift test, CLAUDE.md consent sentence, AC4 low-confidence wording, two-half budget) are also in place. Good revision.

## New weaknesses

1. **Misleading precedent (AC1).** "the same rule `~/.vibe/tokens` gets" is not accurate — `TOKENS_FILE` is `chmod 600`'d only at *write* time (`save_token`); nothing in `/workspace/vibe` today refuses to *read* a loosened-permission tokens file. This would be a genuinely new check, not a mirrored one. Martin will read this as "matches an existing safeguard" when it doesn't yet exist — reword to "new check, modeled on how `TOKENS_FILE` is written" and note it needs portable mode/owner detection (the script already forks `stat -f`/`stat -c` for BSD vs GNU elsewhere; AC1 doesn't say which for mode/ownership).

2. **Internal contradiction (AC5 × AC5b).** Re-embedding "every existing entry on each run" is N+1 sequential `vibe-aux embed` calls, each with its own 20s timeout. If the endpoint accepts connections but hangs (not "unreachable"), a run can block for tens of entries × 20s — minutes — before any fallback fires, contradicting AC5b's "never a hang" guarantee. Spec should say: abort re-embedding and fall back on the *first* non-zero exit, not per-entry.

## Verdict
**revise**
