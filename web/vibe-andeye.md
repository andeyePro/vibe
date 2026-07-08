<!-- DRAFT – pending Martin review – not for publication -->
---
title: vibe
tagline: Secure, slop-free vibe coding.
site: vibe.andeye.com
logo: white winking andeye, circle iris containing ">", white-on-black
status: draft
---

# vibe

Vibe coding done right.

One command opens a sandboxed Claude Code session on your project. Adversarial review, real tests and a security pass are baked in, so what comes out is code you can actually ship – not slop.

vibe is the tool every andeye app is built and assured with. We ship it because we use it.

## What it is

`cd your-project && vibe`. That's the whole interface.

It launches Claude Code inside an isolated container, pre-authenticated against your own Claude Pro or Max subscription – no API key, no per-token billing, no surprise invoice. Your subscription is the only thing it spends.

GitHub access is a fine-grained token scoped to the one repo you're in. If a session goes wrong, the blast radius is that repo and nothing else.

The container runs wide open on the inside so Claude never stops to ask permission mid-task, and that's safe because the walls are real: an outbound firewall allowlists only the handful of hosts a coding session needs, and tool-call hooks gate the destructive shell moves. You get autonomy inside the box without handing over the keys to your machine.

## Why we build with it

andeye apps handle people's money, time and data. That bar doesn't leave room for guessed-at code.

So vibe leads with rigor. `/vs` runs your request through an adversarial harness – an independent critic checks the spec before a line is written, a generator and a tester work without seeing each other's output, and an evaluator has to read the real test log before it calls anything done. Producer and judge are never the same agent. That's how "vibe coded" stops meaning "hope for the best" and starts meaning "reviewed, tested and signed off".

We're open about the method everywhere and we headline it nowhere it doesn't belong. On a customer's buy page you care that the app is reliable, not how it was written. Here, on the developer surface, the method is the point – and it always travels with the assurance that backs it.

## Who it's for

Developers today. You'll need Docker Desktop or OrbStack, a terminal and a Claude Pro or Max subscription. If that's you, you're five minutes from your first session.

Non-coding experts soon. The long game is that someone who knows their domain cold but doesn't live in a terminal can still get top-quality, reviewed code out of vibe. We're honest that we're not there yet – the current prerequisites are real – but that's the direction of travel.

## Get started

Install (clones vibe and links it onto your PATH):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Aqueum/vibe/main/install.sh)
```

You'll also need Docker Desktop or OrbStack, the `@devcontainers/cli` npm package, and the GitHub CLI (`gh auth login`). The installer checks for these and tells you exactly what's missing.

Then, in any project:

```bash
cd your-project
vibe
```

First run walks you through repo detection, the per-repo token, and the one-time Pro/Max login. Nothing to read up on first.

## Contribute

vibe is built with vibe, and you're welcome to help build it the same way. Clone it, point your `vibe` at the clone, and open a pull request from inside a vibe session. Quality contributions earn a share of revenue scaled by the value they add – no per-customer extraction, no enshittification, ever. See CONTRIBUTING.md in the repo.

## Licence

vibe is MIT today. We've settled on moving it to AGPL-3.0 with a contributor licence agreement – so the FOSS core stays free and anyone building a competing cloud service on our code has to give their changes back – but that move and the repo's new home under the andeye org aren't done yet. Until then it's MIT, and there's nothing extra to sign.

---

Built in Scotland, with vibe.
