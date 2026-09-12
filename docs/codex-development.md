# Developing with Codex in Vibe

Start with [your first Codex project](codex-quickstart.md). Vibe is project agnostic: ordinary development requires neither Task&I nor a Mac bridge. Codex works inside Vibe's container. Optional native Apple builds run under a dedicated Mac build account through the build bridge. Container isolation and account permissions are distinct boundaries; a build can execute project-controlled code with the build account's privileges.

Docker builds and rebuilds run on the host for both agents. The launcher checks Docker readiness and can start an identifiable installed Mac backend; it never mounts the unrestricted Docker socket into the coding container. A custom or ambiguous backend requires the host’s normal startup step.

## Interactive and supervised sessions

Launch interactively with `vibe`; first launch offers the runtime choice and guides Codex setup. `vibe --agent codex` switches the folder and remembers that choice for subsequent plain launches. The same host ChatGPT login is reused across authorised projects, while each project keeps its own login-mount grant. Existing GitHub setup is shared with Claude. For unattended work, save a prompt inside the project and run:

```bash
vibe --codex-run .vss/prompts/my-task.md
vibe --codex-resume .vss/prompts/my-task.md
```

Both select Codex and use the same root-owned entrypoint and liveness gate. The prompt path must resolve inside the mounted project. Its contents travel as file data, never shell code. Resume requires an existing `.vss/codex-supervisor.json` and the original prompt content; a mismatched prompt is refused. Do not edit that prompt to smuggle new work into an existing run. Supply corrections through the answer channel instead.

Inside the container, inspect the run with `codex-supervisor status --state /workspace/.vss/codex-supervisor.json`. Request a cooperative stop with `codex-supervisor stop --state /workspace/.vss/codex-supervisor.json`. The supervisor's `--help` describes its ceilings and reconciliation controls. Ordinary interactive sessions do not become supervised retroactively when `$vsss` is typed. A completed checkpoint is not automatically restarted.

The image owns the vendor CLI prefix and shared command tree; global vendor updates require rebuilding, while application dependencies can be installed locally in their projects. Entry/liveness reject mutable managed CLI code and remove Node preload environment variables.

The source changes must be installed by rebuilding/relaunching Vibe before these commands are available. Do that after reviewing the changes and stopping existing work deliberately; never rebuild an active development environment merely to test its replacement. Offline fixture results are not a live-container acceptance claim.

Recovery distinguishes a confirmed turn boundary from an interrupted or
unconfirmed turn. The latter refuses both resume and `--new-run` until effects
have been reviewed. `codex-supervisor reconcile --state <file> --evidence-file
<private-json>` records the exact checkpoint hash, thread/turn identity,
observed outcome and explicit `effectsReviewed`/`safeToContinue` statements;
see `--help` for the schema. It sends no model request and cannot itself verify
the truth of operator evidence. Reconciliation preserves counters and the
initial-prompt attempt; subsequent work uses `continue`.

Checkpoints sync their data and parent directory before dispatch. The effective Task&I endpoint/node binding, including local mappings, is pinned into the checkpoint and client environment; changing it refuses resumption or new delivery.

The supervised runtime requires Linux, isolated `/usr/bin/python3 -I` and procfs. A child subreaper
cleans up descendants, including detached grandchildren, before ownership is
released. Missing or unconfirmed cleanup retains the lock for explicit
reconciliation. This is lifecycle management within the existing container,
not protection against malicious code with the same operating-system identity.
Do not clear an ambiguous lock based only on its age or recorded PID. Healthy
tools may be silent for a long time: the wall deadline remains the safe bound,
and silence alone is not classified as a stall.

## Optional native builds and integrations

The bridge setup and account boundary are documented in
[the short assisted setup](mac-build-setup.md); implementation details are in [mac-build-protocol.md](mac-build-protocol.md). The local client uses an explicit
source allowlist and returns content fingerprints, logs and bounded artifacts.
Live host installation and a project key are separate setup steps.

The optional [Action Window client](taskandi-client.md) supports
`vibe <project> --task ABBR-123`, a local node mapping, durable asks/usage and
answer polling. Its provisional schemas require conformance verification with
the real Task&I service before activation. Unbound projects keep their file
channels and do not initiate Task&I traffic.

## Context and FM2C

Without configuration, the local answer file is `.vss/fromMartin-toCodex.md` (FM2C), with questions in `.vss/fromCodex.md` and history in `.vss/Codex-Q&A-archive.md`. Discovery reports these paths without creating files.

At startup and resumption, Codex is directed to project instructions and `codex-context`. Configure relevant references and separate Q&A files using local, untracked `.vibe/codex-context.json`:

```json
{
  "references": ["docs/spec", "docs/decisions.md"],
  "questions": ".vss/fromCodex.md",
  "answers": ".vss/fromMartin-toCodex.md",
  "archive": ".vss/Codex-Q&A-archive.md",
  "build": ".vibe/mac-build.json"
}
```

Paths resolve from the repository root and may refer to an explicitly configured mounted second brain. Discovery reports path existence and executable helper availability without reading the referenced content or credentials. It does not attest that a running model has obeyed instructions or that a policy file is enforced.

“See FM2C” means read the configured answer channel now and continue the active task with its new answers. The chair also checks between tasks. Questions describe the recommended default and the work that can proceed meanwhile. Resolved exchanges are archived before safe cleanup; ambiguous mappings or concurrent edits are preserved. Claude's separate answer channel is untouched.

## Models and independent review

Codex-led role defaults use OpenAI models through `vibe-delegate role`:

| Alias | Requested model | Starting task class |
| --- | --- | --- |
| `luna` | `gpt-5.6-luna` | Bounded mechanical tests and checks |
| `terra` | `gpt-5.6-terra` | Ordinary implementation and review |
| `sol` | `gpt-5.6-sol` | General agentic implementation |
| `astra` | `gpt-6-astra` | Difficult design, security and evaluation |

Availability is established by the actual vendor call. These defaults are task-routing choices, not verified price rankings. Failures never trigger a paid/API fallback. Usage records identify the requested model and CLI-reported tokens. Cross-vendor delegation is opt-in; Claude model examples in shared commands do not make Claude the default for a Codex role.

Read-only role calls remain tool-less, with supplied input and private temporary output. Writable roles retain guards and must have isolated workspaces and single-file ownership. Separate processes do not by themselves establish all aspects of adversarial independence; retain immutable reviewer inputs and independent test ownership.

## Documentation access

Use Vibe's existing untracked `.vibe/domains` mechanism for required documentation hosts, for example `developer.apple.com`, `www.swift.org`, and `developers.openai.com`. Keep domains project-specific; do not broaden the shipped firewall allowlist or enable hosted search merely to work around it. A domain entry requires relaunch to apply, and DNS/CDN reachability still needs verification. No network policy is activated by editing documentation.

## Verification and rollout

Review [generic readiness](codex-readiness.md) for per-capability evidence and remaining live checks. The earlier Task&I matrix is historical, not a prerequisite for another project. Run the shell and smoke checks, then verify the rebuilt container on a disposable project before relying on overnight operation. Confirm actual tools, helper permissions, guard denials, resumption and cancellation. Test the Mac account and any Task&I endpoint separately with isolated development data. Keep the previous image/source revision available for rollback; preserve supervisor and Q&A state when changing versions.
