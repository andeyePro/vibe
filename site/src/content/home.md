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
            - finds your project and its GitHub remote, then asks once for a fine-grained PAT – scoped to that one repo
            - builds the sandboxed container image (first launch only – reused in seconds after that)
            - announces the session – project, repo, hooks, extras – the blast radius on one screen
            - brings up the firewall and proves it – outbound on a short allowlist, verified before work starts
            - signs Claude Code in with your Claude subscription – no API key
          lines:
            - { cmd: true, sh: true, text: "cd yourproject && vibe" }
            - { role: vibe, text: "No GitHub token found for you/yourproject – opening GitHub: Repository access → Only select repositories → yourproject" }
            - { role: vibe, text: "✓ Token saved – you won't be asked again for this repo.", step: 1 }
            - { role: vibe, text: "Building vibe container image (claude-code=latest)...", step: 2 }
            - { role: vibe, text: "🚀 vibe session starting" }
            - { role: vibe, text: "   project : yourproject" }
            - { role: vibe, text: "   github  : you/yourproject", step: 3 }
            - { role: vibe, text: "   hooks   : tool-call guards + idle bell" }
            - { role: vibe, text: "   extras  : /diet · /feast · /vs · shellcheck-fixer · security-review" }
            - { role: guard, text: "Firewall verification passed - unable to reach https://example.com as expected", step: 4 }
            - { role: claude, text: "signed in with your Claude subscription – no API key anywhere", step: 5 }
            - { role: claude, text: "ready – what shall we build?" }
    - label: Build
      steps:
        - id: vs
          cmd: /vs "add CSV export to the monthly report"
          label: Build, adversarially
          desc: nobody marks their own homework
          checklist:
            - a planner drafts the spec – acceptance criteria plus a model plan (which tier does what)
            - a spec critic attacks the spec before any code – then you approve it
            - a builder writes the code to the locked spec
            - an independent tester writes and runs the tests – it never sees the builder's diff
            - fail means fix and re-test – the tests are immutable, claims don't count
            - a final evaluator reads the raw test log itself – default-fail on ambiguity
          lines:
            - { cmd: true, text: "/vs \"add CSV export to the monthly report\"" }
            - { role: planner, text: "spec drafted – 7 acceptance criteria · model plan: builder sonnet, tester haiku, Fable rung not pre-authorised", step: 1 }
            - { role: critic, text: "revise: criterion 4 isn't mechanically testable as written" }
            - { role: planner, text: "tightened – spec critic: pass after 2 iterations; spec shown for your approval", step: 2 }
            - { role: builder, text: "three files changed – export sits behind the existing report menu", step: 3 }
            - { role: tester, text: "14 tests written from the spec alone – the builder's diff stays unseen", step: 4 }
            - { role: tester, tone: fail, text: "14 checks run – 13 passed, 1 failed on the empty-report case" }
            - { role: builder, text: "fixed – an empty report now exports its headers only", step: 5 }
            - { role: tester, tone: pass, text: "14 checks run – 14 passed · pre-existing suite still green" }
            - { role: reviewer, text: "raw test log read, diff checked against out-of-scope – pass; ready for your review", step: 6 }
        - id: vss
          cmd: /vss
          label: One task, solo
          desc: no arguments – it finds its own work
          checklist:
            - reads your TODO.md backlog and picks the first bounded open item
            - announces the pick and rings the bell – you get a window to redirect it
            - runs the work unattended, acting as you would – a hard-escalate list stops what needs your hands
            - commits locally with a full audit trail – never pushes; you review, you push
          lines:
            - { cmd: true, text: "/vss" }
            - { role: planner, text: "TODO.md read – 7 open items; first bounded one: \"CSV export – empty-state copy\"", step: 1 }
            - { role: planner, text: "type go to proceed now, anything else redirects – silence for 270s = auto-proceed", step: 2 }
            - { role: builder, text: "two files changed", step: 3 }
            - { role: tester, tone: pass, text: "9 checks run – 9 passed" }
            - { role: vibe, text: "committed – audit trail in .vss/sessions/ · not pushed until you've reviewed", step: 4 }
        - id: vsss
          cmd: /vsss --sessions 2
          label: Overnight loop
          desc: burn the rest of your session productively
          checklist:
            - loops the solo run, item after item
            - questions park to your notes – it never stops to wait
            - commits keep landing while you sleep – locally, nothing pushed
            - rolls into a fresh credit window when one runs out
            - stops itself at the perfection gate
          lines:
            - { cmd: true, text: "/vsss --sessions 2" }
            - { role: vibe, text: "23:12 iter 1 – report export shipped ✓ committed", step: 1 }
            - { role: vibe, text: "23:58 iter 2 – flaky date test pinned ✓ committed" }
            - { role: vibe, text: "00:41 a question for you parked to your notes – moving on, not waiting", step: 2 }
            - { role: vibe, text: "02:15 iter 5 – docs caught up with the code ✓ committed", step: 3 }
            - { role: vibe, text: "03:05 window exhausted – auto-resume: relaunching claude --continue (window 2 of 2)", step: 4 }
            - { role: vibe, text: "06:40 optimiser: stop the loop – perfection gate, nothing left adds value", step: 5 }
            - { role: claude, text: "while you slept: 9 commits, 1 question waiting – not pushed; review the session audit, then git push" }
    - label: Red team
      steps:
        - id: curl
          cmd: curl https://sketchy.example
          label: Try to phone out
          desc: traffic off the allowlist
          checklist:
            - every outbound connection is checked against a short allowlist
            - GitHub, npm, Anthropic and a few named extras are allowed – the rest is rejected at the network layer
            - and it fails closed – if the allowlist can't be built, nothing gets out
          lines:
            - { cmd: true, sh: true, text: "curl https://sketchy.example" }
            - { role: guard, tone: fail, text: "curl: (7) Failed to connect to sketchy.example port 443: No route to host", step: 1 }
            - { role: vibe, text: "outbound is REJECTed unless the destination is allowlisted – GitHub · npm · Anthropic · a few named extras", step: 2 }
            - { role: vibe, text: "and the firewall fails closed – if the allowlist can't be built, nothing gets out", step: 3 }
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
            - { role: guard, tone: fail, text: "BLOCK  config.js:12  secret-assignment  api_key = sk-live-…", step: 1 }
            - { role: vibe, text: "commit stopped – the secret never entered history" }
            - { role: guard, text: "WARN fires the same way on private IPs, home paths and email addresses", step: 2 }
            - { role: vibe, text: "git push re-scans the outgoing range for secrets – belt and braces", step: 3 }
    - label: Ship
      steps:
        - id: push
          cmd: git push
          label: Ship it
          desc: out through the one-repo PAT
          checklist:
            - the pre-push guard re-scans the outgoing range for secrets on the way out
            - pushes with the repo's own fine-grained PAT – one repo per token is the whole blast radius
            - docs and CHANGELOG travel in the same commit
          lines:
            - { cmd: true, sh: true, text: "git push" }
            - { role: guard, text: "outgoing range re-scanned for secrets – the guard only speaks when it finds something", step: 1 }
            - { role: out, text: "To https://github.com/you/yourproject.git" }
            - { role: out, text: "   a1b2c3d..f4e5d6a  main -> main", step: 2 }
            - { role: claude, text: "the CHANGELOG entry rode in the same commit – reviewers can follow the story", step: 3 }
            - { role: vibe, text: "peers beyond GitHub? Radicle's seed node is already on the firewall allowlist" }
    - label: Also in the box
      steps:
        - id: budget
          cmd: /budget
          label: /budget
          desc: what this month cost
          checklist:
            - month-to-date tokens per model, across every vibe session on this Mac – plus estimated credit spend
          lines:
            - { cmd: true, text: "/budget" }
            - { role: vibe, text: "month to date – sonnet 41M · opus 12M · haiku 3M tokens (subscription quota)", step: 1 }
            - { role: vibe, text: "fable 0 tokens ≈ $0.00 credits – estimates, not invoices; the console is authoritative" }
        - id: learn
          cmd: /learn
          label: /learn
          desc: lessons that travel
          checklist:
            - captures a cross-project lesson to your learning library – the write needs your yes, every time
          lines:
            - { cmd: true, text: "/learn \"lead with the literal command\"" }
            - { role: guard, text: "vibe: modifying the learning library – confirm to proceed" }
            - { role: vibe, text: "saved – every future session in every project sees it", step: 1 }
        - id: copy
          cmd: /c
          label: /c
          desc: container → Mac clipboard
          checklist:
            - copies Claude's last code block to your Mac clipboard – via a watched scratch file
          lines:
            - { cmd: true, text: "/c" }
            - { role: claude, text: "wrote 214 bytes to .vibe/copy-latest.txt" }
            - { role: vibe, text: "the Mac-side watcher pbcopys it within a second – paste it anywhere", step: 1 }
        - id: diet
          cmd: /diet
          label: /diet · /feast
          desc: token thrift on demand
          checklist:
            - lean mode – no subagents, terse replies, cheaper-model suggestions; /feast turns it back
          lines:
            - { cmd: true, text: "/diet" }
            - { role: claude, text: "lean mode on – no subagents, terse replies; the rest looks mechanical, suggest /model sonnet" }
            - { role: claude, text: "say /feast when you want the full spread back", step: 1 }
who:
  eyebrow: Who it's for
  h2: For developers first
  lede: Vibe is for developers first – but we'd also welcome feedback from non-coding experts who know exactly what they want.
status: In development – built on the same open-core values as everything andeye makes.
footer: andeye Ltd, Scotland
---

**Letting an AI write your code shouldn't mean accepting whatever it produces.** Vibe andeye puts adversarial agentic models between your idea and your codebase: one plans, one builds, and independent critics, testers and reviewers attack the result until it actually holds up.
