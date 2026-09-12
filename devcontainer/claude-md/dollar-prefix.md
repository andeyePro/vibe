# `$` prefix — Claude Code's alias for `/vs`, `/vss`, `/vsss`

Codex's own terminal uses `$vs`, `$vss` and `$vsss` as native skills; typing `/vs` there hits a slash command that is not a vibe-owned file at all (`docs/codex-integration-plan.md` D3). Claude Code has no native form for this, so this fragment supplies it by instruction instead.

When a prompt's FIRST whitespace-delimited token is exactly `$vs`, `$vss` or `$vsss` — case-sensitive, exact match only (`$vss:foo`, `$vssx`, `$VS` are NOT aliases) — treat it as an invocation of that matching slash command, with everything after that first token passed verbatim as its arguments: `$vsss --hours 2 fix the build` is `/vsss --hours 2 fix the build`.

Flags and the hard-escalate list are unchanged — this alias only changes which literal string invokes the command, never what the command then does.

This is an instructional route, not a deterministic one: it depends on the lead noticing and following it, unlike a `UserPromptSubmit` hook (Martin-gated — see `TODO.md`).
