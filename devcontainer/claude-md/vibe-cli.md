# vibe CLI — you're inside it, you don't have it

The `vibe` launcher is a host-side (Mac shell) binary. You are running inside the container it created — you cannot run `vibe` yourself, inspect its source, or see its `--help` output directly. Guessing at flags, subcommands, or launcher behaviour (inventing a mechanism that doesn't exist, or punting with "run `vibe --help` yourself") wastes the user's time on a question you can actually help answer.

For anything host-side vibe launcher — PAT setup/rotation, repo detection/registration, rebuilds, flags — the source of truth is `/brain2/meta/vibe-operation.md` when brain2 is mounted. It holds the CURRENT installed `vibe --help` output, refreshed automatically every launch, so it never drifts from the binary actually running on this machine. Read it before answering.

If brain2 is not mounted, you have no way to see the CLI directly — ask the user to type `! vibe --help` in the terminal so the output lands in the conversation, then answer from that.

Either way, ALWAYS answer with the exact command to run, and state which side it runs on — the host Mac shell, or inside this container. NEVER answer with "go find the right command yourself" or an equivalent punt; that is the failure mode this file exists to prevent.

Prose in `/brain2/meta/vibe-operation.md` outside the managed block (the section between the `vibe-cli-help` markers) is ordinary brain2 content under the normal brain2 trust discipline — authored/provisional until the user reviews it. Only the managed block itself is machine-generated and refreshed automatically; treat it as ground truth, but treat anything outside it like any other brain2 note.
