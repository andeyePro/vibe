# FOSS release + non-coder install — design

2026-07-08. Scope: how a non-developer gets from "heard about vibe" to "running a vibe session", and how vibe releases as a FOSS product under the andeye umbrella. Decision-support doc; nothing here ships without Martin's sign-off on the gated list at the end.

## Current reality

Install today is a developer flow:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
```

Prerequisites the user must already have, none installed by vibe:

- Docker Desktop or OrbStack (the container runtime).
- Node.js plus `npm install -g @devcontainers/cli`.
- GitHub CLI (`gh`), authenticated via `gh auth login`.
- A Claude Pro or Max subscription.
- A terminal, and enough comfort to paste a curl-into-bash line and answer prompts.

`install.sh` clones to `~/.vibe-src`, symlinks `~/bin/vibe`, and asks for a projects directory. It prints a dependency table but does not install or hard-gate on anything.

## The gap for non-coders

A domain expert who isn't a developer hits four walls before the first session: (1) no terminal fluency; (2) Docker/OrbStack is a manual GUI install with its own onboarding; (3) `gh auth login` is a device-flow they've never seen; (4) the whole thing assumes they know what a shell, a PATH and a repo are. The curl bootstrap is fine for developers and a non-starter for the "non-coding expert" audience the vibe.andeye.com copy names as the direction of travel.

## Options

### A. Homebrew formula/cask

`brew install --cask vibe` pulls vibe and can declare Docker/gh as cask dependencies.

- Effort: medium. Author + maintain a formula; either a tap (`andeye/tap`) or submission to homebrew-cask.
- Invariant risk: low. Doesn't touch auth, PAT scope, or the firewall/hooks. Homebrew can install Docker Desktop and gh as deps, which closes two walls.
- Limit: still terminal-first, still assumes Homebrew is installed. Helps developers-adjacent users, not true non-coders.

### B. curl | bash bootstrap with preflight (partial — shippable now)

Keep the curl line but make `install.sh` check every dependency up front and refuse to proceed with actionable one-line install hints when something is missing.

- Effort: low. Add a preflight block near the top of `install.sh`.
- Invariant risk: none. It only reads `command -v` and prints; behaviour when all deps are present is unchanged.
- Limit: improves the honesty and hand-holding of the existing flow; does not remove the terminal requirement. This is the safe slice and ships in this same change.

### C. Mac .app wrapper

A notarised `.app` that bundles the preflight, runs the install, and opens a session — double-click, no terminal.

- Effort: high. Apple Developer signing + notarisation (andeye Ltd account conversion is in flight anyway), a wrapper that shells out to the same install/launch logic, its own update path, and a GUI for the projects-dir + login steps that are currently terminal prompts.
- Invariant risk: medium. The `.app` becomes a second launch surface that must preserve subscription-only auth, one-repo PAT scope, and bypassPermissions-behind-firewall. Every invariant now has two enforcement points to keep in sync.
- Payoff: the only option that genuinely removes the terminal for a non-coder.

### D. Guided first-run in the launcher

Make `vibe` itself detect a cold machine and walk the user through installing Docker, gh, and logging in, interactively, on first run.

- Effort: medium. Extend the launcher's first-run path with detect-and-guide branches.
- Invariant risk: medium. The launcher grows a lot of conditional install logic; the more it does automatically (e.g. installing Docker), the closer it drifts to the "system-modifying script without consent" anti-pattern — every auto-install step needs an explicit show-then-confirm gate.
- Limit: still terminal-hosted. Better onboarding, same front door.

## Recommendation

Ship B now (it's free, zero-risk, and already in this change), then pursue C (the Mac .app) as the real non-coder answer — but only after the Apple Developer org conversion to andeye Ltd lands, since C depends on notarisation under that account.

Strongest counter-argument against C, named explicitly: a `.app` doubles the launch surface, and every vibe invariant (subscription-only spend, one-repo PAT, firewall+hooks make bypassPermissions safe) now has to hold in two places that can drift apart. The container security model is the whole product; a GUI wrapper that gets the PAT scope or the firewall wiring subtly wrong ships an insecure vibe to exactly the users least able to notice. If C is taken, the wrapper must call the same launcher code path, never reimplement it — the `.app` is a double-click over `vibe`, not a parallel `vibe`.

A is a reasonable low-cost middle rung (developer-adjacent reach) and composes with B; D is the weakest — most launcher complexity for the least reach, and the most invariant exposure per unit benefit.

## Martin-gated decisions

- Repo transfer `Aqueum/vibe` → `andeyePro/vibe` (andeye org). Confirmed in brain2 coordination.md 2026-07-07 but not executed in the repo.
- Relicence MIT → AGPL-3.0 + CLA. Confirmed in brain2 (Martin, 2026-07-07, "tidy-up/consistency, not a strategic protect-move") but the repo's LICENSE and README still say MIT; needs the actual LICENSE swap + a CLA in force.
- DNS + deploy of vibe.andeye.com (page copy drafted at `web/vibe-andeye.md`, awaiting approval).
- Non-coder installer path: approve B-now + C-later, or pick a different rung.
- Brand/disclosure prominence: how loudly vibe.andeye.com says andeye apps are "vibe coded" (brain2 records Pro's take — transparent everywhere, headlined to customers nowhere; open on the dev surface always paired with the rigor). Not yet Martin-decided.
- "vibe" naming: fight for the word (reclaim "vibe coding done right") vs rebrand while keeping a short CLI verb. Open in brain2, undecided.
