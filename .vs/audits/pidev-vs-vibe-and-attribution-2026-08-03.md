# pi.dev vs vibe, and the "made with X" attribution question

Research deliverable for the TODO item raised 2026-07-29 (Martin via Gerrit).
Compiled 2026-08-03 by two opus research agents + Fable synthesis, inside a
vibe container. **Provenance discipline**: most primary sources (pi.dev,
codeberg.org, blog posts) are outside the container firewall — claims rest on
GitHub source files (fetched directly, authoritative) plus WebSearch result
summaries. Anything marked *[search-only]* was never read at its primary
source; **no quotation here should be treated as verbatim** unless re-fetched
from a browser. Source URLs are in the per-section citations.

---

## (a) What pi.dev is, honestly compared against vibe's invariants

**Identity.** pi ("Pi Coding Agent", pi.dev, repo `earendil-works/pi`) is a
minimal, MIT-licensed terminal coding agent by Mario Zechner (libGDX author),
started Aug 2025; since April 2026 owned by Earendil Inc., a venture-backed
public benefit corporation co-founded by Armin Ronacher (Flask/Jinja2).
~70–83k GitHub stars as of Aug 2026 — a major project, not a curiosity.
Design thesis is the opposite of a harness: 4 built-in tools (read/write/
edit/bash), a <1,000-token system prompt, no MCP/sub-agents/plan-mode/
permission-popups by default, everything else via a typed TypeScript
extension system. Open-core: the core is committed to MIT (RFC 0015
*[search-only]*), with Fair Source / hosted layers reserved on top; first
commercial product is "Lefos" (email interface for agents, waitlist).

**Model access.** BYO, very broad: OAuth subscription login (Claude Pro/Max,
ChatGPT, Copilot, xAI, OpenRouter), 30+ API-key providers, or local models
via llama.cpp. This is pi's genuine structural advantage over vibe — Gerrit
can run his non-Anthropic agents in it, and a local-model story exists.

**Against vibe's four invariants:**

| Invariant | pi.dev | Verdict |
|---|---|---|
| Subscription auth, never API keys | Supports Claude Pro/Max OAuth *and* API keys *and* 30+ providers — a menu, not an enforced property; docs' own Docker pattern injects `ANTHROPIC_API_KEY` | Better reach (multi-provider, local models); **worse as a guarantee** — no enforcement point, no spend cap |
| Per-repo fine-grained PAT (one-repo blast radius) | **No equivalent anywhere in its docs** — runs as the invoking user, inherits ALL of the user's git credentials; every repo you can push, the agent can push | **vibe clearly better — this is vibe's strongest differentiator** |
| Fail-closed firewall + guard hooks (safe bypassPermissions) | **None by default, by design**: host execution, full user permissions, one trust-prompt per folder, no network control. Opt-in ceiling is real though: Gondolin (Earendil's experimental QEMU micro-VM with programmable egress allowlist and a placeholder-token trick where the real secret never enters the guest) and community Docker sandboxes (`pi-docker-sandbox`: no network by default) | **vibe much better as shipped** (backstop is the only way to run); pi's assembled ceiling is arguably higher (micro-VM > shared-kernel container; credential substitution) but experimental and DIY |
| Single-command launch | `pi` in any dir after `npm i -g`; lighter than vibe (no Docker daemon). But that command carries **zero isolation** — vibe's claim is launch-*with-containment* in one command, which pi cannot do | Bare launch: pi better. Contained launch: **vibe better** |

**Radicle: NOT native.** The integration Gerrit sees is `rad-pi` (GitHub user
`deanh`, MIT): a third-party pi package providing a Radicle skill, Plan/
Context COBs (Radicle collaborative objects recording *how* work was done),
and an autonomy layer (worktree worker agents). It *feels* native because
rad-pi is itself distributed over Radicle (`pi install
git:seed.radicle.garden/….git`) — but that's pi's generic `git:` package
source accepting a seed's HTTP endpoint, not Radicle-aware code in pi.
Relevant to our own open Radicle decision: the COB pattern (plan/context as
replicated forge objects) is genuinely interesting prior art for what
"/vs audit trail on Radicle" could look like.

**Honest bottom line.** pi and vibe are not really rivals: pi is a
*harness-minimalist agent* betting the model needs no scaffolding; vibe is a
*safety-and-rigor wrapper* betting the environment does. pi wins on model
freedom, ecosystem energy and extension flexibility; vibe wins on every
shipped safety property — and "safe by default, one command" remains a claim
pi cannot make without an experimental assembly job. The uncomfortable read:
pi has ~80k stars and Ronacher's halo; vibe's differentiators are real but
niche-narrated. The defensible positioning is exactly the current tagline —
verification and blast-radius, not agent features.

## (b) The German forge ban — it's Codeberg, and it's narrower than reported

**What actually happened** (all Codeberg detail *[search-only]* — primary
pages unreachable from the container; verify at
`blog.codeberg.org/protecting-our-floss-commons-from-llms.html` and
`codeberg.org/Codeberg/org/pulls/1253` before quoting anywhere public):

- **Codeberg e.V.** (Berlin non-profit running codeberg.org) amended its
  Terms of Use by **members' vote at the 2026 general assembly** — 358 for /
  144 against / 14 abstentions (~71%, ~50% turnout), closed **22 July 2026**.
- The new §7 (prohibited content) clause, as reproduced in coverage: you must
  not share projects that **"mostly consist of code written by 'generative
  AI'-tools (including services such as Claude, OpenAI Codex)"** — grounded
  in unclear copyright status and harmful-code safeguards. A separate motion
  added a **no-LLM-training pledge** for the forge itself; a third (PR #1254)
  banned cryptocurrency projects.
- **Scope: a HOSTING rule, not a contribution rule.** It bans repos that are
  mostly AI-written ("LLM-extrusions"); it does NOT ban AI-assisted
  contributions to human-maintained projects, does not impose disclosure,
  and leaves per-project acceptance policy to maintainers. Reported
  carve-outs: AI-assisted additions inside human-maintained codebases,
  established pre-LLM projects, small low-resource experiments.
- **Enforcement**: complaint-driven, manual, no automated detection, no
  immediate mass-deletion; removal then account suspension for repeat
  violations. "Mostly" is undefined — the main criticism (Ronacher, of
  Earendil/pi: "a very bad move" *[search-only]*).
- **⚠ Unresolved in sources**: whether human review of AI output exempts a
  repo. The clause text as reproduced is a pure composition test with no
  human-review carve-out; the softer "lacking human oversight" framing comes
  from the blog post, not the ToU sentence. Needs the primary source.

**The wider landscape matters more than Codeberg** for a project shipping AI
attribution:

- **Outright-ban ecosystems** (a disclosed AI trailer is a self-declared
  rejection trigger): **Forgejo** — ironically stricter than Codeberg, its
  own host — plus Zig, Gentoo, QEMU, NetBSD, SDL, GIMP, SourceHut's own
  upstream.
- **Disclosure-expected ecosystems** (vibe's convention is an *asset*, just
  under the wrong key): **Linux kernel** — mandates
  `Assisted-by: AGENT:MODEL` and forbids AI `Signed-off-by:` — plus Fedora
  (`Assisted-by:`), Apache (`Generated-by:` + provenance file), Rocky, Gitea
  (disclosure required; undisclosed AI is what gets PRs closed).
- **Undecided**: Debian GR vote_002/2026 (five options, hard ban → 
  disclosure; result unpublished at research time — re-check).
  **Radicle: no policy found**, and structurally nowhere to put one
  (per-delegate judgement).
- **Precedent on defaults**: Microsoft shipped a default Copilot
  `Co-authored-by` trailer in VS Code (Apr 2026) and reverted it within
  three weeks under backlash *[search-only]*.

## (c) Feeding the naming/attribution decision (Martin-gated — options only)

Three separable decisions, currently fused in the trailer
`Co-authored-by: Claude <model> using vibe.andeye.com`:

1. **The trailer KEY.** The ecosystem is converging on `Assisted-by:`
   (kernel, Fedora) or `Generated-by:` (Apache), with several projects
   explicitly saying `Co-authored-by:` is wrong for AI (an AI is not a
   co-author; VS Code's revert reinforced this). Options: (a) keep
   `Co-authored-by:` (GitHub renders a badge-ish co-author, familiar);
   (b) switch to `Assisted-by: Claude:<model> [vibe.andeye.com]` — matches
   the kernel's documented format, reads as provenance not authorship, and
   is the portable-upstream choice; (c) dual-trailer
   (`Coding-Agent:` + `Model:` per the community proposal). Note: the
   content-guard's built-in trailer exemption covers `Co-authored-by:`/
   `Signed-off-by:` — any switch must extend that allowlist first, or every
   commit fails the guard.
2. **Naming the MODEL VENDOR in the trailer.** Codeberg's clause literally
   names "Claude" in its prohibited-tools examples — a trailer string-matching
   the ToU example list is cosmetically bad even where substantively fine.
   "made with pi.dev sounds less scary than made with vibe" (Martin's
   observation) generalises: harness-name-only attribution
   (`Assisted-by: vibe.andeye.com agents`) discloses honestly without
   handing a grep-able "Claude" to a hostile reporter. Counter-argument:
   model-level provenance is exactly what the kernel format wants.
3. **Fight vs rebrand "vibe".** Data points for the brain2 decision: the
   word is now embedded in *policy discourse* ("vibe-coded projects" is the
   Register's headline language for what Codeberg banned) — the sentiment
   direction is souring in FLOSS-governance circles while simultaneously
   normalising in product circles (pi, OpenCode etc. never use the word;
   their culture is "harness"/"agent"). vibe's tagline ("vibe coding,
   verified") is a *reclaim* strategy and the research supports its
   coherence: the banned thing is unreviewed composition, and vibe's whole
   product is review. No new fact forces the rebrand; the risk is
   association, not policy breach.

**Exposure summary for vibe itself**: hosting on GitHub/GitLab — no issue.
Hosting a mirror on Codeberg — carve-out territory (human-maintained,
reviewed), but the attribution history is the single most efficient evidence
a bad-faith reporter could grep, and enforcement is complaint-driven with an
undefined threshold. Contributing vibe-attributed patches to Forgejo/Zig/
Gentoo/QEMU/NetBSD/SDL/GIMP — refused on disclosure alone. Kernel/Fedora/
Apache/Gitea — welcomed, if the trailer key is changed to their format.

*Offered, not written: a brain2 note distilling (c) into the existing
fight-vs-rebrand decision item.*
