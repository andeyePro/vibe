---
title: Vibe andeye
tagline: vibe coding, verified
description: Adversarial agentic models plan, build, test and review each other's work in a secure sandbox, so you ship code you can trust.
hero:
  eyebrow: andeye · agentic coding on your own Mac
  h1:
    - vibe coding
    - verified
  lede: Adversarial agentic models plan, build, test and review each other's work in a secure sandbox – so you ship code you can trust.
  cta_how_label: See how it works
  cta_andeye_label: More from andeye
  sub_default: This very page was planned, built, tested and reviewed by a vibe session.
  sub_how: One rule underneath it all – the model that writes the code never marks its own homework.
  sub_andeye: From the maker of Time&I – automatic time tracking for your Mac.
  fineprint: In development – built on the same open-core values as everything andeye makes.
demo:
  title: vibe – yourproject
  caption: A vibe session at a glance – separate models, separate incentives, one shared spec.
  lines:
    - role: you
      text: vibe "add CSV export to the monthly report"
    - role: planner
      text: spec drafted – six acceptance criteria, two questions for you first
    - role: critic
      text: criterion 4 can't be tested as written – tightened before any code
    - role: builder
      text: three files changed – export sits behind the existing report menu
    - role: tester
      tone: fail
      text: 14 checks run – 13 passed, 1 failed on the empty-report case
    - role: builder
      text: fixed – an empty report now exports its headers only
    - role: tester
      tone: pass
      text: 14 checks run – 14 passed, 0 failed
    - role: reviewer
      text: no objections left – the diff is ready for your review
flow:
  eyebrow: How it works
  h2: Nobody marks their own homework
  lede: The model that writes the code never judges it. Spec critics, testers and reviewers are separate agents with an incentive to find fault.
  default_line: A planner drafts the spec, a critic attacks it, a builder writes the code – and independent testers and reviewers decide when it holds up.
  nodes:
    - label: Plan
      body: A planner turns your idea into a spec with real acceptance criteria – and a spec critic attacks the spec before any code is written.
    - label: Build
      body: A generator writes code to the spec. It never gets to decide whether its own work is finished.
    - label: Test
      body: Work is gated on real, runnable acceptance criteria wherever they exist – claims without passing checks don't count.
    - label: Review
      body: Where criteria can't be mechanical, an independent expert reviewer judges the result – looking for reasons to say no.
sandbox:
  eyebrow: The sandbox
  h2: Your machine stays yours
  lede: Agents work in an isolated container with a firewalled network and per-action permission gates – they can build your project, not wander your machine.
  claims:
    - head: An isolated container
      body: Each session runs in a container with only your project mounted – the rest of your Mac simply isn't there.
    - head: A firewalled network
      body: Outbound traffic is limited to an allowlist – package registries, GitHub, the model API – so nothing phones anywhere else.
    - head: Per-action permission gates
      body: Anything that reaches beyond the sandbox asks first – permission is granted per action, not once for everything.
who:
  eyebrow: Who it's for
  h2: For developers first
  lede: Vibe is for developers first – but we'd also welcome feedback from non-coding experts who know exactly what they want.
status: In development – built on the same open-core values as everything andeye makes.
footer: andeye Ltd, Scotland
---

**Letting an AI write your code shouldn't mean accepting whatever it produces.** Vibe andeye puts adversarial agentic models between your idea and your codebase: one plans, one builds, and independent critics, testers and reviewers attack the result until it actually holds up.
