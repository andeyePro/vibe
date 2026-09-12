# Use Codex in any project

Open the project folder in your host terminal and type:

```bash
vibe
```

On first use, choose Codex when Vibe asks. Follow its project authorisation prompt; Vibe installs the host Codex CLI if needed and opens its login. Vibe remembers your runtime for that folder and reuses your login next time. Local Git setup and GitHub access use the launcher flow; Task&I and native Mac builds are optional.

If you already use Claude in that folder, select Codex with `vibe --agent codex`. This becomes the remembered choice and replaces any queued in-session switch. Use `vibe --agent claude` to switch back. Inside either agent, ask it to switch, or run `vibe-agent claude` / `vibe-agent codex` in the container shell. Exit the current TUI normally and Vibe reopens with your choice. Finish or stop autonomous runs first; conversations stay separate. A switch reloads saved project configuration and carries explicit profile/task overrides, without carrying vendor-specific model or resume flags. Your first Codex grant explains that this project's container can read your file-stored ChatGPT login; confirm only for a project you trust. Vibe does not use an API billing fallback.

Once Codex opens, type `help` to see the workflow, or describe what you want to build. For autonomous adversarial work use `$vs`, `$vss`, or `$vsss` followed by the task. A bare `/vs` may be rejected by Codex's composer before Vibe sees it; one leading space (` /vs …`) reaches Vibe's hook, while the `$` form is reliable. Interactive `$vsss` cannot survive process exits automatically; [supervised launch](codex-development.md) is available for unattended runs.

Say “use FM2C for my replies” to use `.vss/fromMartin-toCodex.md`, with questions in `.vss/fromCodex.md`. Codex checks replies between tasks. Neither these files nor a brain2 mount is required for ordinary chat.

If Vibe is not installed, follow [onboarding](../ONBOARDING.md). Vibe checks host Docker and starts an identifiable installed Mac backend if needed. If a prerequisite is missing or the backend is ambiguous, Vibe names the next action. Native Apple projects can ask the agent to follow [Mac setup](mac-build-setup.md); other work can start without it.

For testing unpublished Vibe changes, the host `vibe` command must resolve to the checkout containing them. The launcher uses the `devcontainer` beside its own source; installing a published release will not include unpushed work. Stop active work in the target repo before `vibe --rebuild`. The guard gate must pass, then verify a real model response, one useful change and its relevant tests. A TUI alone is not a development pass.

To withdraw this repo's login access, run `vibe codex deny` on the host and accept its offer to stop the container. Retain source and recovery state. See [readiness](codex-readiness.md) for the remaining rebuilt-host checks.
