# Spec Critique — iteration 4 — task_022: `vibe audit --history` performance

Plain English, adversarial read of the REVISED `/workspace/.vs/spec.md`, checked against iteration-3's single BLOCKING item (AC7(b) missing direct-invocation forks: herestring/bare `grep`).

## Disposition of iteration-3's BLOCKING item

**RESOLVED.** AC7(b) now reads: within the extracted function-body text, assert no occurrence of the external-command names `grep`, `sed`, `awk`, `head`, `cut`, `tr` "in ANY invocation form (piped, command-substituted, herestring/heredoc-fed, or bare)", plus a total ban on `$(` / backtick command substitution regardless of contents. Since every legal shell invocation of a bareword command *is* one of those four forms, this reduces to a mechanical, unambiguous check: does the literal command name appear as a shell token anywhere in the body text (comments included)? That directly catches iteration-3's counterexample — `if grep -qE -- "$pattern" <<<"$content"; then` — because the word `grep` appears as a token, with no `|` or `$(` needed to trigger the block. The loophole is closed.

`printf` is explicitly *not* in the forbidden six-name list, and is separately carved out ("Builtins (`printf` as a statement, `case`, `[[`) are fine; `$(printf …)` is not") — so the existing legitimate finding-emission lines (`printf '%s\t%s\t%s\t%s\n' ... >&2`, present in `check_rule`/`check_email_rule`/`check_home_path_rule` today at lines 99, 141, 161 of the current script) are correctly exempted as long as they stay bare statements and are never wrapped in `$(...)`. This is exactly the distinction iteration-3's own remedy asked for.

## Fresh check: false-positive risk against bodies the Generator will actually produce

I checked the current bodies of the five named functions (lines 84–164 of `devcontainer/git-hooks/vibe-content-scan.sh`) as a proxy for the shapes the rewritten bodies will take (variable names `content`, `location`, `pattern`, `class`, `rule`, `m`, `snippet`, `user`; function names `is_named_trailer`, `is_trailer_line`, `check_home_path_rule`) and the bash-native constructs Part A calls for (`[[ =~ ]]`, `BASH_REMATCH`, `shopt -s/-u nocasematch`, `case`). None of these produce a word-bounded match on `grep`/`sed`/`awk`/`head`/`cut`/`tr`:

- `trailer`/`is_trailer_line`/`is_named_trailer` contain `tr` only as a substring inside a longer word — a word-bounded check (`\btr\b` or equivalent) does not fire on `trailer`, `extract`, `restore`, `string`, etc., since none of those has `tr` as an isolated token.
- `header`/`headers` (used in `scan_blob_stdin`'s comment, itself outside the five-function scope) similarly does not trip `\bhead\b`.
- No plausible bash-native rewrite of these five functions needs the literal words `sed`, `awk`, `head`, or `cut` as identifiers — `BASH_REMATCH`, `shopt`, `nocasematch` don't collide.

The only realistic false-positive surface is a Generator-written *comment* that names the old tool being replaced (e.g. "was: sed fork, now: BASH_REMATCH capture group") — and the spec already anticipates and accepts exactly this: "A false positive from a comment line mentioning those strings is acceptable and fixed by rewording the comment, not by loosening the check." That is a self-correcting loop-internal cost (Tester flags, Generator rewords), not a spec defect, and it was already priced in before this revision — the revision doesn't change that calculus.

## Minor (non-blocking) residue

The spec doesn't pin the exact mechanical definition of "word boundary" (regex `\b`, `grep -w`, or shell-token splitting) for the Tester's static check implementation. In practice these converge on the same pass/fail result for real code (a bareword command token vs. a substring inside an identifier), so this is not ambiguous enough to affect the verdict — noting only for completeness, not blocking.

## Verdict

No new BLOCKING items. Iteration-3's sole BLOCKING item is resolved and does not reopen a false-positive trap against the bodies the Generator will produce or the legitimate `printf` finding-emission calls already in the script.

pass
</content>
</invoke>
