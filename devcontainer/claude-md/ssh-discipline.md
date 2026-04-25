# SSH Discipline Rule: Don't Run ssh/scp/rsync Without Explicit User Authorisation

This rule applies to every turn in every vibe session. It is always active.
It is a disposition rule - it governs your default behaviour, not the
firewall. The firewall permitting outbound SSH to a host does NOT mean you
have behavioural permission to run ssh or scp to that host.

## The Core Rule

Do not run ssh, scp, rsync-over-ssh, or any other SSH-tunnelled command
without explicit per-turn user authorisation. Your default disposition is to
give the user the command to run on their host shell, not to run it yourself.

When you need to inspect a remote host, copy a file to/from a remote host,
or execute a command on a remote host, the correct pattern is:

1. Identify the ssh or scp or rsync command that would accomplish the goal.
2. Show that command to the user in a fenced code block.
3. Ask the user to run it on their host shell and paste back the output.

Do NOT proceed to step 3 and run the command yourself unless the user
explicitly says something like "go ahead and run it", "ssh out and check",
"do it for me", or otherwise grants per-turn authorisation within the current
message or a message in the same turn.

## Why This Matters: Blast Radius

The vibe container runs with `--permission-mode bypassPermissions`. This is
intentional and safe for operations within the container - the firewall and
tool hooks are the backstops.

However, SSH-out from a bypassPermissions container is a different threat
model. When you run ssh to a target host:

- You inherit the user's SSH keys (mounted from the host at container start).
- You can execute arbitrary commands on the target with the same privileges
  as the user's SSH key.
- The target host has NO equivalent of the vibe firewall or the container's
  tool hooks.
- Mistakes on the target host - overwriting files, stopping services,
  corrupting config - are NOT sandboxed.

In other words: bypassPermissions in the container extends to bypassPermissions
on every SSH-reachable host if you run ssh yourself. That is a much larger
blast radius than the user signed up for when they launched vibe.

The user's SSH keys give you network-layer access. They do not give you
behavioural permission to exercise that access autonomously.

## Firewall Permission is Not Behavioural Approval

The vibe init-firewall.sh allowlist permits outbound SSH (port 22, port 443
for git-over-SSH) to .local mDNS names and to GitHub. This is a NETWORK
LAYER permission - it ensures the container can reach remote hosts for
purposes like git push and git fetch, and for the user to pull a command
output on their LAN.

It is not an instruction for you to use that SSH access proactively. A door
being unlocked is not the same as being invited in.

Treat the firewall allowlist as: "SSH traffic will not be blocked" - not as
"SSH out freely whenever it would be helpful."

## What Explicit Authorisation Looks Like

Explicit authorisation is a clear per-turn statement from the user such as:
- "Go ahead and ssh in and check the log"
- "Run that scp command yourself"
- "SSH out to mcomz.local and restart the service"
- "You can use ssh for this, I trust you to do it"

Implicit authorisation is NOT sufficient:
- The user mentioning a remote host's name
- The user saying "check what's on the Pi"
- The user asking a question about a remote resource
- The user having previously given you SSH authorisation in a different turn
  or a different session

Per-turn means per-turn. Authorisation from a prior message does not carry
over. If you are in doubt about whether the user has authorised ssh-out for
the current step, default to showing the command and asking them to run it.

## Scope: Commands Covered

This rule covers:
- ssh (direct shell access or command execution)
- scp (file copy over SSH)
- rsync with ssh transport (rsync -e ssh, rsync over SSH URLs)
- sftp
- Any other command that tunnels over SSH or uses the user's SSH keys to
  authenticate to a remote host

This rule does NOT cover:
- git fetch / git push / git pull to GitHub or other git hosts (these use
  SSH transport but are scoped git operations, not shell access - proceed
  normally)
- The user running ssh themselves on their host shell and pasting output back
  to you (that is the intended pattern - encourage it)

## Do Not Modify Firewall or SSH Config

This rule is purely about your behavioural disposition. Do not:
- Modify init-firewall.sh or its allowlist in response to this rule
- Add or remove entries from ~/.ssh/known_hosts or ~/.ssh/config
- Change SSH key permissions
- Do anything that affects the firewall, hook, or permission infrastructure

If a user asks you to modify the firewall or SSH config, treat that as a
separate explicit request, not an implication of this rule.

## Default Pattern to Follow

When you find yourself about to run ssh, scp, or rsync:

Stop. Write out the command in a fenced code block. Tell the user:
"Run this on your host shell and paste back the output."

This pattern:
- Keeps the user in control of their remote hosts
- Gives them visibility into exactly what is happening
- Preserves their ability to review before executing
- Does not extend vibe's blast radius to their LAN

It is slightly more friction than doing it yourself. That friction is by
design.

## In-Session Application

If a user asks you to "check the Pi" or "look at what's on mcomz.local" or
"copy that file to the server" - your first response should be the command
they need to run, not you running it. Show them the ssh or scp command.

If they then say "just do it" - that is explicit authorisation for that
specific action in that turn. Proceed with only that action.

Authorisation does not generalise. "Just do it for this one thing" does not
mean "ssh out freely for the rest of the session."
