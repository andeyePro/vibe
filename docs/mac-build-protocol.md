# Mac build bridge protocol (v1)

`devcontainer/mac-build.mjs` snapshots explicitly selected source files and sends one JSON request to the fixed SSH forced command `mac-build-host` on host `host.docker.internal` using account `claude`. This is a provisional, fixture-only bridge requiring explicit opt-in for each selected project. Approved tools still execute project-controlled code with the dedicated Mac account’s full privileges.

## Client configuration

Create an **untracked, non-symlink** `.vibe/mac-build.json` and keep its key and known-host file under `.vibe`. Their parent directories may not be symlinks; all three resolve beneath the supplied repository root. The key must be owner-readable only, and config, key, and known-host files must not be tracked even under a case-insensitive spelling. Unknown config fields and a config over 64 KiB are rejected.

```json
{
  "account": "claude",
  "identityFile": ".vibe/mac-claude-ed25519",
  "knownHosts": ".vibe/mac-known_hosts",
  "includeRoots": ["Package.swift", "Sources", "Tests", "Resources"]
}
```

Protocol v1 accepts printable ASCII path components (including spaces); Unicode file contents are supported, but non-ASCII filenames require a future filesystem-aware protocol revision. This conservative rule avoids incomplete APFS/HFS Unicode case-fold assumptions. Each root is a relative path. Only regular files beneath those roots are transferred; dotfiles must themselves be named as an include root. `.git`, `.vibe`, `.vss`, `.build`, and `node_modules`, symlinks (including ancestor symlinks), special files, traversal, duplicate/ASCII-case-folded paths, file-parent collisions, and oversized snapshots are rejected before SSH starts. File reads use bounded reads from a single `O_NOFOLLOW` descriptor, with `fstat` type/size checks. Every ancestor is opened with no-follow directory flags and its device/inode identity is checked before and after access. Directory listings receive the same identity checks. Node has no portable `openat`: this mitigates directory swaps but cannot eliminate an adversarial swap-and-restore race. Concurrent hostile project processes must be stopped before snapshotting; these checks are not containment. SSH itself later opens the key and known-host paths, so their local account must also be trusted. The client requires a working Git repository and a successful tracked-file listing. It uses `ssh -F /dev/null`, `BatchMode`, `IdentitiesOnly`, strict known-host checking, disabled proxy/local-command/forwarding features, fixed absolute key/known-host paths, no ambient identity agent or global known-host files, disabled host-key updates, and argv rather than request-derived shell text.

Run `mac-build doctor`, `build`, `test`, or `screenshot` in the rebuilt container (or `node devcontainer/mac-build.mjs` from the source checkout). This is foreground-only; each approved host command has a maximum 600000 ms deadline and the client enforces a 630000 ms whole-operation deadline. A nonsuccess host outcome is a nonzero CLI result.

## Host installation (administrator only)

Do not install the runner or its config in an agent-writable checkout. Copy `mac-build-host.mjs` and `mac-build-protocol.mjs` to a root-owned directory on the Mac, for example `/Library/VibeMacBuild/`, mode `0755` directories and `0755` runner files. Put `/etc/mac-build-host.json` at root ownership, mode `0644` or stricter, and use a root-owned ForceCommand wrapper that exports `MAC_BUILD_FORCED_COMMAND=1` and its absolute path in `MAC_BUILD_FORCED_WRAPPER` before execing Node. Configure sshd/authorized_keys so account `claude` always reaches that wrapper. The host verifies ownership and non-writable, non-symlink ancestor directories for the Node interpreter, runner, imported protocol, config, and wrapper; a root-owned leaf below a writable parent is not trusted. It refuses ordinary direct execution.

For this example, an administrator first creates root-owned `/Library/VibeMacBuildState` (mode `0755`) and its `jobs` and `receipts` directories owned by `claude` (mode `0700`). Portable Swift example `/etc/mac-build-host.json`:

```json
{
  "root": "/Library/VibeMacBuildState/jobs",
  "receiptsRoot": "/Library/VibeMacBuildState/receipts",
  "lockName": ".swift-build-resource.lock",
  "timeoutMs": 600000,
  "commands": {
    "doctor": ["/Library/VibeMacBuild/commands/doctor"],
    "build": ["/Library/VibeMacBuild/commands/build"],
    "test": ["/Library/VibeMacBuild/commands/test"],
    "screenshot": ["/Library/VibeMacBuild/commands/screenshot"]
  },
  "artifacts": [{"path":"current.png","maxBytes":8388608}]
}
```

For production, each command must be an administrator-owned wrapper beneath the installation’s `commands` directory, with trusted ownership and ancestry checked before reading the request. Wrappers must be self-contained apart from trusted OS/developer tools and the intentional staged project inputs; do not source account-writable helper scripts or configuration. All configured command vectors, including unused operations, must have an absolute normalized executable path and nonempty, NUL-free string arguments. Arguments may be tool names or flags; they are not all filesystem paths. The administrator must ensure the fixed argv are appropriate for a fresh staged snapshot. No signing, publishing, credentials, request paths, or request commands are supported. For example, a root-owned build wrapper can contain `#!/bin/sh` followed by `exec /usr/bin/xcrun swift build`; the test and doctor wrappers can use `swift test` and `xcodebuild -version`. A screenshot wrapper using `exec /usr/bin/xcrun simctl io booted screenshot current.png` is capture-only and **unattested**: it can capture an existing booted app and does not prove it built, installed, or launched this snapshot. A trusted screenshot pipeline must use fixed argv that build, install, and launch the current staged source before capture. `doctor` never infers simulator availability from `xcodebuild -version`.

## Wire format and diagnostics

One stdin JSON object is accepted:

```json
{"version":1,"jobId":"UUID","operation":"doctor|build|test|screenshot","files":[{"path":"Sources/A.swift","mode":420,"content":"base64"}],"digest":"sha256"}
```

The digest is SHA-256 of UTF-8 `JSON.stringify` of path-sorted `[path, mode, content]` triples. Base64 is canonical. Limits are 10,000 files, 8 MiB per file, 32 MiB decoded, and 48 MiB wire. The host validates everything before staging, computes the staged digest before and after the fixed command, and rejects changed source. Same HEAD is never treated as proof of dirty-source identity.

Responses are JSON evidence with job, operation, supplied and actual fingerprints, `snapshotBytes`, outcome/exit/logs, artifact metadata/content, and timeout/output-bound indicators. The client rejects a response unless its job, operation, digest, and decoded snapshot size bind exactly to its request. Artifact reads are parent-symlink-safe, streamed within their configured cap, and withheld when their aggregate encoded content would approach the wire cap. `doctor` reports named `config`, `xcode`, and `simulator`; simulator is explicitly unattested by the Xcode version check. A dropped client SSH connection does not establish that the host stopped; its command deadline applies while the host runner remains alive; a host crash requires reconciliation. Receipts bind the protocol version, exact UUID, operation, and complete validated snapshot digest. An identical request returns its cached terminal result without execution; an identity mismatch is rejected. Existing unknown or corrupt state never authorizes execution. Initial receipts and terminal replacements are synced before proceeding, including their directory. A crash can leave `unknown-running` even when side effects completed. There are no automatic retries. Before sending, the client durably retains the request in private `.vibe/mac-build-requests/UUID.json`; received success or failure evidence goes to its `.result.json` sibling. To retrieve a lost result after reconciliation, use `mac-build replay UUID`. It sends the retained snapshot and UUID, never a new snapshot. An already completed host job returns its receipt; a never-accepted request can execute for the first time. The ordinary operation commands create fresh UUIDs and must not be used to retry an uncertain job. A live acceptance check should verify Xcode and simulator availability with `doctor`, forced-command routing, key pinning, a deliberately dirty tracked file, a relevant untracked source file, artifact bounds, timeout process-group killing, concurrent lock behavior, and recovery by explicit lock/receipt reconciliation.

## State directories and administrator reconciliation

Both roots must be absolute, canonical (no symlink components), distinct, and non-overlapping. Existing parents must be owned by root or the service UID, with no group/other write bits; a root-owned sticky temporary-directory ancestor is allowed, but the final state directories remain private. The service creates each final directory if absent and requires service ownership and mode `0700`. Provision parents first; symlink aliases such as `/var` on macOS must be replaced with their canonical paths. Receipt files require service ownership and mode `0600`. The lock is a private directory under `receiptsRoot`, outside staged builds; its name cannot be `.` or `..`. Its `owner.json` records request identity and the host PID for diagnosis. A PID is evidence, never proof of liveness or safe recovery.

Recovery is an explicit offline administrator operation, never a client operation or automatic stale-lock timeout:

1. Disable new forced-command sessions and stop the service. Identify and stop all builds and their descendants, including processes that escaped their original process group. Inspect side effects before declaring the account quiescent. Do not infer safety from lock age, a missing PID, or a disconnected SSH client.
2. Preserve a copy of the receipt, lock owner metadata, logs, and staging directory for diagnosis. Corrupt or legacy receipts without identity stay blocked. Do not delete receipts to make their UUID reusable.
3. For a known identity with `unknown-running`, atomically replace its receipt with mode `0600`, service-owned JSON containing `state: "terminal"`, the unchanged `identity` object (`version`, `jobId`, `operation`, `digest`), and a `result`. The result must contain matching `jobId`, `operation`, `fingerprint` equal to the identity digest, and `snapshotBytes` calculated from the retained validated request. Use `outcome: "unknown"` and an `error` recording the administrator decision if completion cannot be proven; use a verified terminal result only with independent evidence. Flush the file and parent directory. This records uncertainty and permits retrieval; it never re-executes the old request.
4. Only after quiescence is established, remove the abandoned lock’s `owner.json` and empty lock directory from `receiptsRoot`, and inspect/remove the corresponding staging directory. Revalidate ownership/modes before re-enabling sessions. Any new job after an unknown result requires a separate human decision about possible duplicate side effects.

## Lifecycle and limitations

The host launches a process group and sends `SIGKILL` on timeout, log overflow, cancellation and direct-child exit, before post-command validation. SIGINT, SIGTERM and SIGHUP request cancellation while the host remains alive to checkpoint and clean up. An arbitrary SIGKILL/crash can still leave unknown state requiring reconciliation. It waits for the child’s `close` event (which reaps the direct child), bounding inherited-pipe draining to one second. Node cannot reap arbitrary orphaned grandchildren; those are reaped by the OS. Descendants can escape with `setsid` and survive group killing. This is lifecycle cleanup, not a guarantee that every descendant has terminated. Robust containment and complete process-tree accounting require an OS-enforced job/process boundary, which this bridge does not implement.

The dedicated Mac account retains full privileges. Malicious opted-in code can access or modify anything that account can, including service-owned receipts, locks, staging data, credentials, and other processes. Keeping state outside the checkout and validating paths does not protect it from code running under the same UID. Administrator-owned installation files constrain routing and configuration only; they do not sandbox builds. Protecting mutable service state from builds requires a separate principal and privilege boundary beyond this implementation.

Source-level scratch checks are not installation evidence. No real SSH forced-command installation, root ownership/permissions, host configuration, macOS process behavior, Xcode availability, simulator availability, or service execution has been verified. Validate these independently on the real Mac before expanding the fixture-only opt-in contract.


### Concrete forced-command wrapper

After installing a trusted Node binary and the two reviewed modules beneath
root-owned `/Library/VibeMacBuild`, an administrator can install a root-owned
`/Library/VibeMacBuild/entry` containing:

```sh
#!/bin/sh
exec /usr/bin/env -i \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  SSH_CONNECTION="$SSH_CONNECTION" \
  MAC_BUILD_FORCED_COMMAND=1 \
  MAC_BUILD_FORCED_WRAPPER=/Library/VibeMacBuild/entry \
  /Library/VibeMacBuild/node /Library/VibeMacBuild/mac-build-host.mjs
```

Use this exact forced command for the project's authorized key, with forwarding,
PTY and user rc disabled (for example the OpenSSH `restrict,command="..."`
options where supported). Preserve other authorized keys and existing account
setup. Confirm the actual sshd configuration enforces these restrictions; a
wrapper environment marker alone is not proof of SSH enforcement. Pin the
Mac's verified host key in the project's local known-host file. Do not copy
vendor login material or signing/release secrets into this path. Installation,
key authorization, host-key verification and live probes are external host
steps; none have been performed by the source implementation run.


Recursive staging cleanup runs in its own process with a 10-second deadline.
The host releases its owned lock and verifies cleanup before committing a
terminal receipt. Failed or unconfirmed cleanup returns `unknown`, retains the
unknown receipt and any remaining lock/stage for administrator reconciliation,
and cannot count as success. The command deadline does not include all bounded
snapshot/receipt I/O; the client’s whole-operation deadline may expire first,
in which case use the retained identity rather than issuing a fresh job.

OpenSSH parses `-o` values separately from shell argv. The known-host filename is quoted for that parser, including spaces and literal quotes. Key/known-host paths containing control characters, `%` or `$` are refused to avoid SSH token/environment expansion. A local `ssh -G` fixture verifies parsing without opening a connection.
