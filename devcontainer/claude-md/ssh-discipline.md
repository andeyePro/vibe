# SSH Discipline: Offer Inline, Don't Force Paste-Back

You are running inside a vibe container. Vibe ships with `~/.ssh` mirrored
from the user's Mac, the firewall allowlists outbound SSH to `.local` hosts
and GitHub, and the user opens vibe specifically BECAUSE it can reach their
LAN. Treat SSH-out as a normal capability of the tooling.

## Default Pattern

When SSH (or scp / rsync-over-ssh / sftp) is the right way to make
progress:

1. State the concrete action you'd take. One line, with the literal
   command. Example: `ssh pi02.local 'tail -n 50 /var/log/syslog'`.
2. Ask permission inline. Light touch — "OK?", "shall I?", "want me to
   run this?". Same turn, same message.
3. If the user says yes (or any clear permission word — "y", "go", "do
   it", "yep", "ok"), run it.
4. If the user says no, or prefers to run it themselves, give the
   command and let them paste output back.

Do NOT default to "here is a command, please run it on your Mac and
paste back the output". That is the fallback for a `no`, not the
opening move. The user is in vibe to avoid that round-trip; serving it
to them by default is friction theater.

## Why Ask at All

The container runs with `--permission-mode bypassPermissions`. SSH out
extends that "no sandbox" reach to every host the user's keys touch.
The target host has no equivalent of vibe's firewall or tool hooks.
Mistakes there — overwriting a config, killing a service — are not
reversible by you. So the user grants permission per action, but the
ASK is your job, not theirs.

The firewall allowing port 22 is network permission. Per-action
permission is the behavioural layer on top.

## Project-Level Opt-Out of the Ask

If `VIBE_SSH_AUTO=1` is set in the environment (passed in via
`~/.vibe/config` on the host) OR the file `/workspace/.vibe-allow-ssh`
exists, this rule is omitted entirely — the user has pre-authorised
autonomous SSH for this project and accepts the blast-radius
trade-off. Just SSH, no per-action ask.

If neither is set, default to the offer-and-ask pattern above.

## Read Pure / Write Cautious

The user's risk tolerance scales with what the SSH op does:

- **Read-only inspection** (cat, ls, tail, ps, systemctl status,
  journalctl, df, free, uptime, dmesg, etc.): the ask can be very
  light. "Want me to ssh in and tail the log?" is enough.
- **Idempotent / reversible changes** (start/stop a service, restart a
  daemon, edit a non-critical config with a documented revert):
  explicit one-line ask with the command shown.
- **Destructive or hard-to-reverse** (rm, dd, parted, systemctl
  disable, package removal, drive operations, writes to /etc on a
  production host): show the command, name the risk, ask explicitly.
  Do not proceed on an ambiguous yes.

The default pattern above always applies. This sub-rule just tunes
how cautious the ask should sound.

## What Counts as Permission

- "yes" / "y" / "yep" / "ok" / "go" / "do it" / "go ahead" / "run it"
  — clear yes for the action you proposed.
- "no" / "n" / "I'll do it myself" / "give me the command" — fall
  back to paste-back.
- Anything else (silence, ambiguous follow-up, different topic) — do
  NOT proceed. Re-ask if the SSH op is still relevant.

Permission is per-ask. A yes for one action is not authorisation for
the next. Multi-step SSH plans get one ask per step, unless the user
explicitly says something like "go ahead and do all three".

(If the opt-out flag is set, this whole section is moot. Just SSH.)

## Scope

This rule covers ssh / scp / rsync-over-ssh / sftp / any command that
tunnels over SSH or uses the user's SSH keys.

It does NOT cover git fetch / push / pull to GitHub (scoped to the
project's PAT, not shell access — proceed normally).

It does NOT cover the user running ssh themselves on their host shell
when they prefer to (encourage that path on `no`).

## Do Not Modify SSH Config or Firewall

This rule governs your disposition. Do not touch `init-firewall.sh`,
`~/.ssh/known_hosts`, `~/.ssh/config`, or SSH key permissions in
response to it. If the user asks for those changes, treat it as a
separate explicit request.

## Tone

Helpful, not arsey. The user opened vibe so they wouldn't have to
copy-paste commands between two shells. Match that intent. A clean
"I can do X — OK?" beats a paragraph about why you can't.
