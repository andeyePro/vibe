# Check your capabilities before saying you can't

Before telling the user you can't see, run, build, render or reach something ("I can't view the output", "I have no browser"), run `vibe-capabilities`. It lists:

- **Available now**: use it. The common case is a dedicated **Mac account** (the `claude` account on `host.docker.internal` when declared). That is how you *see*: `vibe-shot <url|folder|file>` renders it there and prints a PNG path; open it with the Read tool.
- **Could be switched on**: give the user its one-line step, then carry on with other work. Never stop at "I can't".
- **Genuinely not here**: say so, with its workaround.

SSH to that account keeps the per-action ask unless the project pre-authorises it. Setup for users: `vibe-capabilities --setup mac-account`.
