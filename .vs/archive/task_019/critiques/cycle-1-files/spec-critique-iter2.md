# Spec Critique — iteration 2 — task_019: regrettable-content git guard

Audited: `/workspace/.vs/spec.md` (revised) against the 5 BLOCKING concerns from
`/workspace/.vs/cycle-1/spec-critique.md` (iteration 1), plus `guard-bash.sh`,
`install-claude-extras.sh`, and the `smoke-test.py` convention.

## Resolution of prior BLOCKERs

**1. Trailer/noreply email false-positive — RESOLVED.**
§ Scanner contract's built-in default allowlist (spec line 21) hardcodes, at the
scanner level (not per-repo, not opt-in): exemption of `Co-Authored-By:`/`Signed-off-by:`
trailers and the literal `noreply@anthropic.com` / `*.users.noreply.github.com`
addresses, plus a generic rule exempting email/IP findings on any line matching
`^[A-Z][A-Za-z-]+:\s`. AC11 pins a real trailer-bearing commit message scanning
clean. This is exactly the fix iteration 1 asked for (scanner-level, not a
per-repo file), and it ships to every repo by construction.

**2. `vibe audit --history` HEAD-only blind spot — RESOLVED.**
Component 7 now scans `git log -p --all` through `--blob-stdin`, plus
`git log --all --format=%B` for messages — genuine full-history content, not
a HEAD-tree snapshot. AC9 pins the exact iteration-1 scenario (secret committed
then deleted in a later commit) and requires exit 1 + a clean-history control
case exiting 0. The mechanical gap iteration 1 flagged is closed. (See New
concern 1 below, though — a different gap was introduced by tier-scoping.)

**3. Dogfooding bootstrap gap — RESOLVED.**
§ Dogfooding is new and directly answers this: fixtures are runtime-constructed
by concatenation (`"ghp_" + "A"*36`) into throwaway temp repos so no contiguous
secret pattern is ever staged in vibe's own tree, any unavoidable literal in
docs gets a matching `.vibe-content-allow` entry, and `VIBE_CONTENT_GUARD=off`
is named as a fallback for the landing commit if needed. AC1/AC2/AC9 all
reference runtime-built fixtures consistent with this.

**4. pre-push zero-SHA stdin→range mechanics — RESOLVED.**
Component 2 now states the rule explicitly: local-sha-all-zero (delete) → skip;
remote-sha-all-zero (new branch) → `git rev-list <localsha> --not --remotes`;
otherwise → `<remotesha>..<localsha>`; empty range → exit 0. Checked the
new-branch case for a container that has cloned (so `refs/remotes/origin/*`
already populated) and for a truly fresh repo (no remote-tracking refs at all,
so `--not --remotes` filters nothing and the full local history is scanned) —
both resolve correctly, no fail-open on a real new-branch push with content.
AC10 exercises this specific path end-to-end. Minor unaddressed edge case
noted in New concerns.

**5. No AC exercises the installed hooks end-to-end — RESOLVED.**
AC10 is new and explicit: installs hooks via `core.hooksPath`, then drives a
real `git commit` (clean passes, BLOCK content fails via the real `pre-commit`
wrapper) and a real `git push` of a new branch with a secret (fails via the
real `pre-push` wrapper, exercising the zero-SHA rule from concern 4). This is
exactly the integration-level check iteration 1 asked for.

All 5 prior BLOCKERs are resolved as written, with pinned mechanisms and ACs
that would catch a regression in each.

## New concerns

**1. [BLOCKING, § Scanner contract line 20 / component 7 / AC9] `vibe audit` inherits pre-push's "BLOCK tier only for file content" rule, which guts its own headline purpose.**
The rationale given for BLOCK-only file-content scanning ("PII already
committed has been seen by the commit-time gate; re-flagging it on every push
is the cries-wolf failure") is specific to *pre-push*, which is incremental
and re-runs on every push of the same branch. `vibe audit --history` is a
one-shot, deliberately-invoked, full-history scan with no repeat-nag problem —
the same rationale doesn't hold. But the spec text bundles both under one rule:
"`--range` ... and `vibe audit` scan BLOCK tier only for file content." The
practical effect: WARN-tier PII (RFC1918 IPs, `/Users/<name>/` paths, `.local`
hostnames — literally the `project-hygiene.md` source list) sitting in
*historical file content* is never surfaced by `vibe audit`, full stop —
whether the repo predates the guard's installation or not. That's precisely
the class of content the task summary names as the actual pain in "Time&I's
Private→Public flip" (PII and private-machine specifics, not just raw
secrets). AC9 only exercises the BLOCK-tier case (a `ghp_` token), so this gap
is untested and would ship silently. Fix: scope the BLOCK-only restriction to
`--range` (pre-push) only; have `vibe audit --history` scan both tiers against
file content (it has no crying-wolf problem to solve), and add an AC proving
audit catches a WARN-tier PII string (e.g. a `192.168.x.x` IP) sitting in a
historical file that was later removed.

**2. [MEDIUM, § Scanner contract / component 1 / component 7] `--blob-stdin` location semantics are underspecified for the multi-commit audit stream.**
Component 1 describes `--blob-stdin` simply as "raw content on stdin." But
component 7 feeds it the entire `git log -p --all` output — a single stream
containing many commits' patches back-to-back. The location contract (line 18)
lists `commit <sha>` as a valid non-file location, implying the scanner must
parse the interleaved `commit <sha>` header lines from `git log -p` output to
attribute a finding to the right commit; nothing pins this. AC9 doesn't assert
on location content (only exit code + "reports the finding"), so a Generator
could satisfy AC9 with a scanner that reports every audit finding as
`location: stdin` — technically passing, practically useless for a human
deciding what to purge. Fix: either pin that `--blob-stdin` in audit mode must
track the most recent `commit <sha>` header it has seen and use it as location,
or add an AC asserting the reported location names a specific commit SHA.

**3. [MEDIUM, § Scanner contract / AC10] No AC proves the pre-push "cries wolf" fix actually holds under a real push.**
The whole point of the BLOCK-only-for-file-content rule at pre-push (once
correctly scoped per concern 1) is that a WARN finding already committed
doesn't re-fire on every subsequent push of the same branch. AC10 only drives
a BLOCK-tier secret through a real push. Nothing exercises: commit a WARN-only
change (e.g. an IP address) through pre-commit (which does scan both tiers and
would exit non-zero unless overridden), then push it and confirm pre-push does
*not* re-block on that same WARN content. Without this AC a Generator could
implement pre-push scanning both tiers for file content (contradicting the
spec) and nothing would catch it — AC3 tests `--staged` only, not `--range`.
Fix: add an AC that pushes a commit whose only finding is WARN-tier file
content and asserts `git push` succeeds through the real `pre-push` wrapper.

**4. [LOW, component 6 vs § Dogfooding] Residual wording implies committed literal fixtures need allowlisting, contradicting § Dogfooding rule 1.**
Component 6 (line 38) says vibe's shipped `.vibe-content-allow` covers "...the
exact fixture strings any committed test data uses." § Dogfooding rule 1 is
explicit that fixtures are runtime-constructed specifically so nothing
contiguous is ever staged in vibe's tree — i.e., there should be no "committed
test data" with literal secret-shaped strings requiring an allowlist entry at
all. This is leftover phrasing from before § Dogfooding was added and could
lead a Generator to believe both an allowlist entry *and* runtime construction
are needed for the same fixtures. Fix: drop the "test data fixture strings"
clause from component 6, or clarify it refers only to doc/fragment literals
(the docs/SECURITY.md/hygiene-doc examples), not test fixtures.

**5. [LOW, component 2] `--not --remotes` scopes across all configured remotes, not just the one being pushed to.**
For the standard vibe single-`origin` setup this is correct. In a rare
multi-remote container (e.g. pushing the same branch to a second remote for
the first time), `--not --remotes` would incorrectly exclude commits already
known via a *different* remote's tracking refs, even though they're new to
the remote actually being pushed to — a narrow scanning gap. Not worth a
dedicated AC given vibe's one-remote-per-container model, but worth a one-line
spec note acknowledging the limitation rather than leaving it implicit.

**6. [LOW, § Scanner contract line 20 wording] "scan both tiers' rules against any *new* commit messages" doesn't parse cleanly for `vibe audit`.**
The word "new" is meaningful for pre-push (incremental — only the commits
being pushed) but `vibe audit --history` isn't incremental; it scans every
commit message that has ever existed. Component 7 separately says "plus every
commit message" (both tiers implied, no BLOCK-only carve-out for messages),
which is the right behaviour — but the shared sentence in the Scanner contract
should be reworded to avoid implying audit only checks messages on "new"
commits. Cosmetic, but a Generator skimming only the Scanner contract section
could misread it.

## Verdict

**revise**

The 5 iteration-1 BLOCKERs are all genuinely resolved with pinned mechanisms
and ACs that would catch a regression. But the revision's fix for pre-push's
"cries wolf" problem (BLOCK-tier-only file-content scanning) was applied
uniformly to `vibe audit` as well, and that silently defeats audit's purpose
for exactly the WARN-tier PII case the task was built to catch (New concern
1). That needs a one-line scope fix (BLOCK-only stays pre-push-specific; audit
scans both tiers for file content) plus a matching AC before Generator starts,
or the shipped `vibe audit` will pass every AC while missing the Private→Public
scenario it exists for.
