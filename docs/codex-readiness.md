# Project-agnostic Codex readiness

Vibe supports Codex development in Git repositories independently of Task&I. The default path uses container tools, project instructions and local file replies. Native Mac builds and external task services are optional. This environment does not promise unrestricted host access or every toolchain preinstalled: discover required tools and use the existing project profile/domain configuration.

| Capability | Source evidence | Live status |
| --- | --- | --- |
| Launch in another repo | Guided host login/consent, local Git excludes and per-folder runtime memory; smoke 33 plus existing agent/opt-in fixtures | Rebuilt image must be launched on the host; this container has no Docker binary/socket |
| In-session switch | Private project request, host-only preference update and clean-exit relaunch; active/ambiguous runs refuse | Rebuilt host switch remains to observe |
| Generic context and FM2C | Smoke 24: fresh Git repo, no integration config, default channels, nested cwd and installed symlink | Source exercised locally; fresh rebuilt startup remains to observe |
| Guarded vendor runtime | Smoke 18/22/32; source checks vendor ownership and managed hooks before launch | Active installation predates source ownership fixes; do not bypass its refusal |
| Useful development | Real subscription delegation worked in Vibe's repo; normal project tests and diffs remain the acceptance measure | A separate disposable Git repo received a real Terra-generated change; chair ran its four passing Node tests. Rebuilt host launch remains open |
| Autonomous recovery | Smoke 19/21/25/27/30; explicit supervised launch, checkpoint and reconciliation | Actual rebuilt app-server stop/resume acceptance remains open |
| Optional Mac builds | Smoke 26/31; [agent-led setup](mac-build-setup.md) | No configured project connection here; native checks remain open only for projects needing them |
| Optional external task service | Existing opt-in client and smoke 28/29 retained | No service required or called for default startup; Task&I integration/conformance belongs in that project |

Use [the quickstart](codex-quickstart.md) for the next repository. Record the source revision, guard result, `codex-context` output, model response, changed files and test result there. For unattended acceptance, also run an isolated bounded supervisor task, stop it at a confirmed boundary, and resume the same state. Preserve ambiguous effects for reconciliation. MANUAL-TESTS Test 57 covers first launch and switching; Test 56 covers supervision and optional integrations. Skip unconfigured integration sections.

The earlier [Task&I matrix](codex-taskandi-readiness.md) records the initial implementation history. Its native Task&I scenario is no longer Vibe's completion gate. Martin authorised live activation in FM2C; unavailable host execution is the remaining constraint, not an unanswered approval request.
