# Spec Critique — iteration 3 — task_022: `vibe audit --history` performance

Plain English, adversarial read of the REVISED `/workspace/.vs/spec.md`, checked against iteration-2's critique at `/workspace/.vs/cycle-1/spec-critique-iter2.md`. Default to flagging.

## Part 1 — disposition of iteration-2's carried-forward items

1. **AC1 slice not pinned to a single capture — RESOLVED.** AC1 now reads: capture the bounded stream ONCE to `slice.txt`, run both the old and new scanner binaries against that same file, and explicitly: "Never re-invoke `git log` between the two runs — commits landing mid-cycle would shift the window and fake a mismatch." This closes the two-live-invocations race cleanly; the instruction is unambiguous and matches the fix I recommended.

2. **AC7(b) extraction method unspecified — RESOLVED, but see fresh finding below.** AC7(b) now pins a mechanical boundary: `^<name>() {` to the first subsequent `^}`, and enumerates the forbidden substrings (`| grep`, `| sed`, `| awk`, `| head`, `$(grep`, `$(sed`, `$(awk`, `$(printf`), with false positives on comments accepted as fixable by rewording. I checked the current function bodies in `devcontainer/git-hooks/vibe-content-scan.sh` (lines 84-164) — all five named functions already follow the `name() {` … `}` (column-0 close) shape with no nested brace groups, so the extraction is mechanically sound against the current code. Concern 15 below is about what the pinned enumeration misses, not about the boundary-extraction method itself, which is now solid.

3. **`--message` mode + A2b guard discipline only indirectly tested — PARTIALLY RESOLVED, as expected.** AC2 now explicitly adds "via `--message` on the corpus written to a file (direct parity for the commit-msg hook's mode)" alongside `--blob-stdin`, `--staged`, `--range`. That closes the `--message`-mode half of this item — it now gets a direct old-vs-new differential like the other modes, not just an interface-level "retained unchanged" claim. The A2b guard-discipline half (every `[[ =~ ]]` must be wrapped, not bare) still has no dedicated static or unit check — only the indirect proof that a genuinely unguarded bare `[[ ]]` would crash mid-slice and blow AC1/AC2's byte-identical comparison. Iteration 2 already assessed this indirect coverage as adequate and declined to block on it; nothing in this revision changes that calculus, so I'm not reopening it. Noting it as still-partially-open, not re-flagging as a numbered concern.

## Part 2 — fresh adversarial pass (new weaknesses introduced by this revision only)

4. **BLOCKING (new) — AC7(b)'s pinned enumeration only catches forks that go through a pipe or `$(...)`; a bare `grep`/`sed`/`awk`/`head` invocation using input redirection (`<<<`, `<()`) or as a direct `if` condition slips through both the static check AND, plausibly, is not reliably caught by AC4's timing gate either.**

   The revision that closed concern 2 (iteration-2's item 13) made AC7(b) mechanical by fixing its forbidden-substring list to exactly eight literal two-token strings: `| grep`, `| sed`, `| awk`, `| head`, `$(grep`, `$(sed`, `$(awk`, `$(printf`. But A2c's own prose states the actual intent more broadly: "the five named functions … contain NO pipeline or command substitution that forks on the per-line hot path" — with an "etc." after the enumerated examples, signalling the list was meant to be illustrative, not exhaustive.

   A Generator (or a later editor) can satisfy AC7(b)'s literal check while still forking a subprocess per line, using a form the enumeration doesn't cover — for example:

   ```
   if grep -qE -- "$pattern" <<<"$content"; then
   ```

   This is a bare command invocation of `grep` guarded by an `if` (also satisfying A2b's guard-discipline requirement) with a herestring for input — no `|` before `grep`, no `$(` anywhere. None of the eight enumerated substrings appear in this line, so AC7(b)'s static check passes, even though this still forks one `grep` process per line per rule, which is exactly the fork-storm behaviour Part A exists to eliminate ("the point of the task," per A2c's own parenthetical).

   Whether AC4's 60-second timing gate would reliably catch this residual forking is not established by the spec. The recon numbers cited elsewhere (old scanner ≈0.0085s/line, ~400k+ forks across full history driving the original 280s+ timeout) describe the *fully*-forking baseline. A Generator that eliminates forking in four of the five named functions but leaves one using the herestring-`grep` idiom above would cut total fork count roughly 5-fold-ish depending on which function, which could plausibly still land under 60s on the vibe repo's current history size — there is no analysis in the spec establishing that partial fork-elimination necessarily fails AC4. So AC4 is not a dependable backstop for this specific evasion, and AC7(b) — explicitly named in the Test-location section as "the permanent guard against the fork-storm quietly returning" — would not catch it either.

   This is the same class of problem iteration 1's concern 2 raised and iteration 2 believed it had closed: a test-evasion route that satisfies the letter of the acceptance criteria while missing the substance of Part A. Pinning AC7(b) to a fixed literal-string list (done specifically to resolve the previous iteration's "unspecified extraction method" minor) is what introduced this narrower, exploitable surface — the vaguer prior wording ("etc.") at least left room for a diligent Tester to write a broader check; the now-mechanical wording locks the Tester into checking only the eight listed substrings.

   Recommend: broaden AC7(b)'s check from "the eight listed substrings" to something that also forbids bare invocation of `grep`/`sed`/`awk`/`head` as commands used for content matching within the five function bodies — e.g., forbid the regex `\b(grep|sed|awk|head)\b` appearing anywhere in the extracted body EXCEPT inside a `#`-comment, with an explicit carve-out for the legitimate output-emission `printf '...' >&2` calls already present in `check_rule`/`check_email_rule`/`check_home_path_rule` (those must stay, since finding-line emission needs them and is unrelated to matching). A plain "no bare `printf`/`grep`/`sed`/`awk` at all" rule would be too broad — it would misfire on the existing legitimate `printf '%s\t%s\t%s\t%s\n' ... >&2` finding-emission lines, which are not part of the hot-path matching this task targets and must not be touched per Part A's "keeping each function's … output format … byte-for-byte equivalent." The check needs to distinguish "grep/sed/awk/head used to match `$content`" from "printf used to emit a finding line" — the former is forbidden everywhere in the body (piped, substituted, or bare), the latter is required and must stay.

## Verdict

BLOCKING: 1 new (item 4). No new minors. All items carried from iteration 2 are resolved except the already-accepted-as-adequate A2b indirect-coverage residue (not reopened, per iteration 2's own reasoning, unchanged by this revision).

revise
</content>
</invoke>
