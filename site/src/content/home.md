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
  cta_install_label: Install from GitHub
  cta_install_href: "https://github.com/andeyePro/vibe#install"
  cta_register_label: Register interest
  cta_register_href: "https://contact.andeye.com/?source=vibe.andeye.com&subject=vibe%20waitlist&message=Please%20email%20me%20when%20vibe%20andeye%20goes%20live."
  cta_andeye_label: More from andeye
  sub_default: This very page was planned, built, tested and reviewed by a vibe session.
  sub_install: Free and open source. Clone it, run vibe, and the README walks you through the rest.
  sub_register: Not a developer? We'll email you when vibe arrives as a ready-to-run app.
  sub_andeye: From the maker of Time&I – automatic time tracking for your Mac.
  fineprint: In development – built on the same open-core values as everything andeye makes.
  see_demo_label: "▾ watch a session run – click the commands yourself"
journey:
  eyebrow: The demo
  h2: Drive a session yourself
  lede: Click a command on the left and watch the terminal play out exactly what vibe does. The checklist under each command ticks off as it happens – and clicking again replays it.
  term_title: yourproject — vibe — 96×28
  hint: click a command to run it
  locked_note: run Launch first – everything starts there
  running_note: running…
  caption: That transcript is the real shape of a vibe session – and this very page shipped from one.
  groups:
    - label: Launch
      steps:
        - id: launch
          cmd: vibe
          label: Launch
          desc: one command, from any project folder
          checklist:
            - finds your project and its GitHub remote
            - checks the repo's own fine-grained PAT – it reaches this repo, and only repos this session declares
            - builds the sandboxed container (once – reused in seconds after that)
            - verifies the firewall – outbound on a short allowlist
            - signs Claude Code in with your Claude subscription – no API key
          lines:
            - { cmd: true, sh: true, text: "cd yourproject && vibe" }
            - { role: vibe, text: "✓ GitHub repo detected: you/yourproject", step: 1 }
            - { role: vibe, text: "✓ fine-grained PAT found – scoped to this repo; only declared repos are reachable", step: 2 }
            - { role: vibe, text: "✓ container ready (built once, reused in 3s after that)", step: 3 }
            - { role: vibe, text: "✓ firewall verified – outbound allowlist: GitHub · npm · Anthropic (+ ssh)", step: 4 }
            - { role: vibe, text: "🚀 vibe session starting" }
            - { role: vibe, text: "   project : yourproject" }
            - { role: vibe, text: "   github  : you/yourproject" }
            - { role: vibe, text: "   hooks   : tool-call guards + idle bell" }
            - { role: vibe, text: "   extras  : /diet · /feast · /vs · shellcheck-fixer · security-review" }
            - { role: claude, text: "✓ signed in with your Claude subscription – no API key anywhere", step: 5 }
            - { role: claude, text: "ready – what shall we build?" }
    - label: Build
      steps:
        - id: vs
          cmd: /vs "add CSV export to the monthly report"
          label: Build, adversarially
          desc: nobody marks their own homework
          checklist:
            - a planner turns your ask into a spec with real acceptance criteria
            - a spec critic attacks the spec before any code
            - a builder writes the code
            - an independent tester runs every check
            - fail means fix and re-test – claims don't count, passes do
            - a reviewer hunts for reasons to say no
          lines:
            - { cmd: true, text: "/vs \"add CSV export to the monthly report\"" }
            - { role: planner, text: "spec drafted – six acceptance criteria, two questions for you first", step: 1 }
            - { role: critic, text: "criterion 4 can't be tested as written – tightened before any code", step: 2 }
            - { role: builder, text: "three files changed – export sits behind the existing report menu", step: 3 }
            - { role: tester, tone: fail, text: "14 checks run – 13 passed, 1 failed on the empty-report case", step: 4 }
            - { role: builder, text: "fixed – an empty report now exports its headers only", step: 5 }
            - { role: tester, tone: pass, text: "14 checks run – 14 passed, 0 failed" }
            - { role: reviewer, text: "no objections left – the diff is ready for your review", step: 6 }
        - id: vss
          cmd: /vss
          label: One task, solo
          desc: no arguments – it finds its own work
          checklist:
            - reads your TODO.md backlog
            - picks the highest-leverage open item itself
            - runs the whole adversarial loop unattended
            - commits with a full audit trail for your review
          lines:
            - { cmd: true, text: "/vss" }
            - { role: planner, text: "TODO.md read – 7 open items", step: 1 }
            - { role: planner, text: "picked: \"CSV export – empty-state copy\" (small, unblocked, user-visible)", step: 2 }
            - { role: builder, text: "two files changed", step: 3 }
            - { role: tester, tone: pass, text: "9 checks run – 9 passed" }
            - { role: vibe, text: "committed – audit trail in .vss/sessions/ for your review", step: 4 }
        - id: vsss
          cmd: /vsss --sessions 2
          label: Overnight loop
          desc: burn the rest of your session productively
          checklist:
            - loops the solo run, item after item
            - questions go to your notes – it never stops to wait
            - commits keep landing while you sleep
            - rolls into a fresh credit window when one runs out
            - stops itself at the perfection gate
          lines:
            - { cmd: true, text: "/vsss --sessions 2" }
            - { role: vibe, text: "23:12 iter 1 – report export shipped ✓ committed", step: 1 }
            - { role: vibe, text: "23:58 iter 2 – flaky date test pinned ✓ committed" }
            - { role: vibe, text: "00:41 a question for you parked to your notes – moving on, not waiting", step: 2 }
            - { role: vibe, text: "02:15 iter 5 – docs caught up with the code ✓ committed", step: 3 }
            - { role: vibe, text: "03:05 credit window exhausted – relaunching into window 2 of 2", step: 4 }
            - { role: vibe, text: "06:40 nothing left worth doing – perfection gate, loop closed", step: 5 }
            - { role: claude, text: "while you slept: 9 commits, 1 question waiting, audit trail ready" }
    - label: Red team
      steps:
        - id: curl
          cmd: curl https://sketchy.example
          label: Try to phone out
          desc: traffic off the allowlist
          checklist:
            - every outbound connection is checked against a short allowlist
            - GitHub, npm, Anthropic and a few named extras are allowed – the rest is refused
          lines:
            - { cmd: true, sh: true, text: "curl https://sketchy.example" }
            - { role: guard, tone: fail, text: "curl: (7) Failed to connect to sketchy.example port 443 – refused at the network layer", step: 1 }
            - { role: vibe, text: "the firewall fails closed: if the allowlist can't be built, nothing gets out", step: 2 }
        - id: leak
          cmd: git commit (with a pasted API key)
          label: Try to leak a secret
          desc: the content guard reads every diff first
          checklist:
            - staged diffs and commit messages scanned before every commit
            - secrets and personal data both stop the commit – secrets as BLOCK, personal data as WARN
            - pushes re-scan the outgoing range for secrets before anything leaves
          lines:
            - { cmd: true, sh: true, text: "git commit -m \"wip\"   # config.js still holds a pasted API key" }
            - { role: guard, tone: fail, text: "BLOCK config.js:12 anthropic-key – commit stopped before it existed", step: 1 }
            - { role: guard, text: "WARN fires the same way on private IPs, home paths and email addresses", step: 2 }
            - { role: vibe, text: "git push re-scans the outgoing range – belt and braces", step: 3 }
    - label: Ship
      steps:
        - id: push
          cmd: git push
          label: Ship it
          desc: out through the one-repo PAT
          checklist:
            - pushes with the repo's own fine-grained PAT
            - lands on GitHub – Radicle support is on the way
            - docs and CHANGELOG travel in the same commit
          lines:
            - { cmd: true, sh: true, text: "git push" }
            - { role: vibe, text: "content-guard: outgoing range clean" }
            - { role: out, text: "To github.com/you/yourproject   main → main", step: 1 }
            - { role: vibe, text: "(Radicle peers: on the way)", step: 2 }
            - { role: claude, text: "the CHANGELOG entry rode in the same commit – reviewers can follow the story", step: 3 }
    - label: Also in the box
      steps:
        - id: budget
          cmd: /budget
          label: /budget
          desc: what this month cost
          checklist:
            - month-to-date model spend, across every vibe on this Mac
          lines:
            - { cmd: true, text: "/budget" }
            - { role: vibe, text: "this month: sonnet 62% · opus 31% · haiku 7% of your subscription – credit spend itemised separately", step: 1 }
        - id: learn
          cmd: /learn
          label: /learn
          desc: lessons that travel
          checklist:
            - captures a cross-project lesson to your learning library (with your say-so)
          lines:
            - { cmd: true, text: "/learn \"lead with the literal command\"" }
            - { role: vibe, text: "saved to your learning library – every future session in every project sees it", step: 1 }
        - id: copy
          cmd: /c
          label: /c
          desc: container → Mac clipboard
          checklist:
            - copies Claude's last code block straight to your Mac clipboard
          lines:
            - { cmd: true, text: "/c" }
            - { role: vibe, text: "last code block copied – paste it anywhere on your Mac", step: 1 }
        - id: diet
          cmd: /diet
          label: /diet · /feast
          desc: token thrift on demand
          checklist:
            - lean mode – fewer subagents, terser output; /feast turns it back
          lines:
            - { cmd: true, text: "/diet" }
            - { role: vibe, text: "lean mode on – say /feast when you want the full spread back", step: 1 }
who:
  eyebrow: Who it's for
  h2: For developers first
  lede: Vibe is for developers first – but we'd also welcome feedback from non-coding experts who know exactly what they want.
status: In development – built on the same open-core values as everything andeye makes.
footer: andeye Ltd, Scotland
---

**Letting an AI write your code shouldn't mean accepting whatever it produces.** Vibe andeye puts adversarial agentic models between your idea and your codebase: one plans, one builds, and independent critics, testers and reviewers attack the result until it actually holds up.
