<!-- DRAFT – pending Martin review – not for publication -->
---
title: vibe
tagline: Vibe coding, verified.
site: vibe.andeye.com
logo: white winking andeye, circle iris containing ">", white-on-black
status: draft
---

# vibe

Vibe coding done right.

One command opens a sandboxed Claude Code session on your project. Adversarial review, real tests and a security pass are baked in, so what comes out is code you can actually ship – not slop.

vibe is the tool every andeye app is built and assured with. We ship it because we use it.

## What it is

`cd your-project && vibe`

It launches Claude Code inside an isolated container, pre-authenticated against your own Claude Pro or Max subscription – no API key, no per-token billing, no surprise invoice. Your subscription is the only thing it spends.

GitHub access is a fine-grained token scoped to the one repo you're in. If a session goes wrong, the blast radius is that repo and nothing else.

The container runs wide open on the inside so Claude never stops to ask permission mid-task, and that's safe because the walls are real: an outbound firewall allowlists only the handful of hosts a coding session needs, and tool-call hooks gate the destructive shell moves. You get autonomy inside the box without handing over the keys to your machine.

## Why we build with it

andeye apps handle people's money, time and data. That bar doesn't leave room for guessed-at code.

Vibe leads with rigor. `/vs` runs your request through an adversarial harness – an independent critic checks the spec before a line is written, a generator and a tester work without seeing each other's output, and an evaluator has to read the real test log before it calls anything done. Producer and judge are never the same agent. That's how "vibe coded" stops meaning "hope for the best" and starts meaning "reviewed, tested and signed off".

We're fighting for the reputation of the vibe verb. You don't know every nuance of how your car drives – that doesn't make you a sloppy driver. You haven't reviewed every binary digit of your machine code – that doesn't make you a sloppy coder. Working at a higher level of abstraction was never the problem; shipping unreviewed guesses was. Vibe keeps the abstraction and deletes the guessing.

We're open about the method. Vibe was open sourced and public from day one. We openly invite input and contributions – start a [discussion](https://github.com/andeyePro/vibe/discussions), raise an [issue](https://github.com/andeyePro/vibe/issues), or read the [contributor guide](https://github.com/andeyePro/vibe/blob/main/CONTRIBUTING.md).

## Who it's for

Developers today. You'll need Docker Desktop or OrbStack, a terminal and a Claude Pro or Max subscription. If that's you, you're five minutes from your first session.

Non-coding experts too, with a Claude holding your hand. Ask your Claude to look at [our CLAUDE.md](https://github.com/andeyePro/vibe/blob/main/CLAUDE.md) and take you through the vibe onboarding process – it will walk you from an empty Mac to your first session, one step at a time. A friendlier packaged app, training and support are on the roadmap. [Let us know](mailto:vibe@andeye.com) if you're a non-coding expert in your field and interested in being a guinea pig for the non-coder releases, or if you'd like an email when it's all ready.

## Get started

Install (clones vibe and links it onto your PATH):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/andeyePro/vibe/main/install.sh)
```

You'll also need Docker Desktop or OrbStack, the `@devcontainers/cli` npm package, and the GitHub CLI (`gh auth login`). The installer checks for these and tells you exactly what's missing.

Then, in any project:

```bash
cd your-project
vibe
```

First run walks you through repo detection/creation, the per-repo token, and the one-time Pro/Max login. Nothing to read up on first.

## Contribute

vibe is built with vibe, and you're welcome to help build it the same way. Clone it, point your `vibe` at the clone, and open a pull request from inside a vibe session. If this ever develops to include features that cost us money (hence we need to charge for a pro tier) major contributors will earn a share of revenue scaled by the value they add – but we promise no per-customer extraction, and no enshittification, ever. [CONTRIBUTING.md](https://github.com/andeyePro/vibe/blob/main/CONTRIBUTING.md) is the how; [CONTRIBUTORS.md](https://github.com/andeyePro/vibe/blob/main/CONTRIBUTORS.md) is the who – the public ledger that revenue-share promise operates on.

## Licence

vibe is MIT. Use it, embed it, fork it, ship it – nothing to sign. We looked at AGPL plus a contributor licence agreement and set it aside: for a dev tool, the freedom to adopt matters more than the protection.

---

Built in Scotland, with vibe.
