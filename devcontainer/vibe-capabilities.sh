#!/bin/bash
# vibe-capabilities — installed as /usr/local/bin/vibe-capabilities.
#
# WHY: agents in a vibe container keep saying "I can't see that output",
# "I have no browser", "I can't build a Mac app" — when the machine they run
# on gives them a way to do exactly that (a dedicated Mac account reachable
# over SSH, a Mac build bridge, image viewing, mounted references…). None of
# it is visible from inside the container unless something says so. This
# script is that something: an inventory of what THIS container can do right
# now, what could be switched on and exactly how, and what is genuinely out of
# reach together with the workaround. The always-installed CLAUDE.md fragment
# (claude-md/capabilities.md), Codex's session-start context and the
# capability-nudge Stop hook all point here.
#
# It only LOOKS. It never connects over SSH, never reads a private key, never
# makes an HTTP request; the one network probe is a TCP connect to the Mac's
# port 22 with a 2-second timeout (skipped with VIBE_CAP_NO_PROBE=1). Every
# probe failure degrades to "unknown", never to an error.
#
# Usage: vibe-capabilities            full inventory (Markdown)
#        vibe-capabilities --brief    one line per available capability
#        vibe-capabilities --setup mac-account
#                                     the steps to give agents a Mac account
set -uo pipefail

ws=${VIBE_CAP_WORKSPACE:-/workspace}
home=${VIBE_CAP_HOME:-${HOME:-/home/node}}
ssh_config=${VIBE_CAP_SSH_CONFIG:-$home/.ssh/config}
mac_host=${VIBE_CAP_MAC_HOST:-host.docker.internal}
brain2=${VIBE_CAP_BRAIN2:-/brain2}
zotero=${VIBE_CAP_ZOTERO:-/zotero}
learnings=${VIBE_CAP_LEARNINGS:-/learnings}
run_vibe=${VIBE_CAP_RUN_DIR:-/run/vibe}

mode=full
case "${1:-}" in
  "") ;;
  --brief) mode=brief ;;
  --setup)
    case "${2:-}" in
      mac-account) mode=setup-mac ;;
      *) echo "vibe-capabilities: --setup takes: mac-account" >&2; exit 2 ;;
    esac ;;
  -h | --help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "vibe-capabilities: unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

# ── probes ───────────────────────────────────────────────────────────────────

# The User of the first `Host` block in the SSH config that names the Mac host.
# The config is mirrored from the Mac's own ~/.ssh, so one entry there declares
# the account for every vibe container on that machine.
mac_user_from_ssh_config() {
  [ -r "$ssh_config" ] || return 0
  awk -v target="$mac_host" '
    tolower($1) == "host" {
      inblock = 0
      for (i = 2; i <= NF; i++) if ($i == target) inblock = 1
      next
    }
    inblock && tolower($1) == "user" { print $2; exit }
  ' "$ssh_config" 2>/dev/null
}

mac_user=${VIBE_MAC_USER:-}
mac_user_source="VIBE_MAC_USER"
if [ -z "$mac_user" ]; then
  mac_user=$(mac_user_from_ssh_config)
  mac_user_source="the SSH config (Host $mac_host)"
fi
case "$mac_user" in *[!A-Za-z0-9._-]*) mac_user="" ;; esac

mac_port=unknown
if [ -n "$mac_user" ] && [ "${VIBE_CAP_NO_PROBE:-0}" != 1 ]; then
  if timeout 2 bash -c "</dev/tcp/$mac_host/22" 2>/dev/null; then mac_port=open; else mac_port=closed; fi
fi

ssh_auto=no
if [ "${VIBE_SSH_AUTO:-}" = 1 ] || [ -f "$ws/.vibe-allow-ssh" ]; then ssh_auto=yes; fi

other_hosts=""
if [ -r "$ssh_config" ]; then
  other_hosts=$(awk -v target="$mac_host" 'tolower($1) == "host" {
      for (i = 2; i <= NF; i++) if ($i != target && $i !~ /[*?]/ && $i != "github.com") print $i }' \
    "$ssh_config" 2>/dev/null | sort -u | tr '\n' ' ')
fi

have() { command -v "$1" >/dev/null 2>&1; }
toolchain=""
for t in node npm python3 swift go cargo rustc gcc make jq rg gh git curl uv; do
  have "$t" && toolchain="$toolchain $t"
done

mac_build=no
[ -f "$ws/.vibe/mac-build.json" ] && [ ! -L "$ws/.vibe/mac-build.json" ] && mac_build=yes
codex_login=no
[ -f "$home/.codex/auth.json" ] && codex_login=yes
extra_domains=""
[ -r "$run_vibe/extra-domains" ] && extra_domains=$(tr '\n' ' ' < "$run_vibe/extra-domains" 2>/dev/null)
shared_repos=""
[ -r "$ws/.vibe/shared-repos.manifest" ] && shared_repos=$(awk '{print $1 " (" $2 ")"}' "$ws/.vibe/shared-repos.manifest" 2>/dev/null | tr '\n' ' ')
mac_note=""
[ -f "$brain2/meta/mac-test-account.md" ] && mac_note="$brain2/meta/mac-test-account.md"

# ── output ───────────────────────────────────────────────────────────────────

mac_line() {
  # shellcheck disable=SC2016  # the backticks are Markdown, not command substitution
  printf 'Mac account `%s@%s` (declared by %s; port 22 %s): anything that needs eyes or a Mac runs there — render a page in a headless browser and screenshot it, build and launch a Mac/iOS app, reach URLs the container firewall blocks. Copy the PNG back with scp and look at it (Claude: the Read tool displays images; Codex: view the image file). SSH %s.' \
    "$mac_user" "$mac_host" "$mac_user_source" "$mac_port" \
    "$([ "$ssh_auto" = yes ] && echo 'is pre-authorised in this project' || echo 'needs a one-line per-action OK from the user unless the project allows it')"
  # shellcheck disable=SC2016  # Markdown backticks
  [ -n "$mac_note" ] && printf ' Standing permission and the screenshot recipe: `%s`.' "$mac_note"
  printf '\n'
}

if [ "$mode" = setup-mac ]; then
  cat <<EOF
# Give your vibe agents a Mac account (one-time, per Mac)

Why: a vibe container has no browser and no route to arbitrary URLs, so an
agent can read the CSS it wrote but never see the page. A dedicated macOS
account it can SSH into gives it eyes (headless browser, screenshots, the
Simulator) and a real Mac toolchain, without touching your own files.

1. On the Mac: System Settings → Users & Groups → add a Standard user named
   \`claude\` (any name works; keep it simple).
2. System Settings → General → Sharing → Remote Login: ON, and allow that
   user.
3. In your Mac's \`~/.ssh/config\`, add:

       Host $mac_host
           User claude

   Every vibe container on this Mac mirrors that file, so this one entry is
   what tells all of them the account exists.
4. Authorise a key for it: append the public key vibe containers use (your
   \`~/.ssh/id_ed25519.pub\`, or a dedicated one) to
   that account's \`~/.ssh/authorized_keys\` on the Mac.
5. Optional, once, logged in as that user: \`npm i -g playwright &&
   npx playwright install chromium\` so agents can render web pages.
6. Optional: let agents use it without asking each time — in a project,
   \`touch .vibe-allow-ssh\` (untracked) and relaunch vibe.

Check: inside any vibe session run \`vibe-capabilities\`; the first line of
"Available now" should name the account on \`$mac_host\` with port 22 open.
Status on THIS container: $([ -n "$mac_user" ] && echo "declared as $mac_user (port 22 $mac_port)" || echo "not declared yet (step 3)").
EOF
  exit 0
fi

if [ "$mode" = brief ]; then
  [ -n "$mac_user" ] && echo "- $(mac_line)"
  [ "$mac_build" = yes ] && echo "- mac-build doctor|build|test|screenshot (this project's Mac build bridge)"
  echo "- view images: Claude's Read tool displays PNG/JPG; Codex can view image files"
  echo "- web: search tools route outside the firewall; direct HTTP only to GitHub, npm, Anthropic${extra_domains:+ and $extra_domains}"
  [ -d "$brain2" ] && echo "- $brain2: the user's second brain (read; search it before asking)"
  [ -d "$zotero" ] && echo "- $zotero: Zotero PDFs (read)"
  [ "$codex_login" = yes ] && echo "- Codex login: /ask astra and the /review codex slot"
  [ -n "$other_hosts" ] && echo "- other SSH hosts (per-action ask): $other_hosts"
  echo "- toolchain:$toolchain"
  exit 0
fi

echo "# What this vibe container can do"
echo
echo "Run this before telling anyone you can't see, build, run or reach something."
echo
echo "## Available now"
echo
[ -n "$mac_user" ] && echo "- $(mac_line)"
[ "$mac_build" = yes ] && echo "- Mac build bridge: \`mac-build doctor|build|test|screenshot\` builds this project's snapshot on the Mac and returns logs and artifacts (docs/mac-build-protocol.md in the vibe repo)."
echo "- Look at images: Claude's Read tool displays PNG/JPG files; Codex can view an image file. A screenshot you fetched is something you can see."
echo "- Web: WebSearch/WebFetch-style tools route outside the container firewall. Direct HTTP from the shell reaches only GitHub, npm, Anthropic${extra_domains:+ and the project extra domains $extra_domains}."
[ -d "$brain2" ] && echo "- \`$brain2\`: the user's second brain (read; start at \`$brain2/Brain2.md\`, search it before asking)."
[ -d "$zotero" ] && echo "- \`$zotero\`: Zotero PDFs, read-only."
[ -d "$learnings" ] && echo "- \`$learnings\`: cross-project learning library (read)."
[ -n "$shared_repos" ] && echo "- Shared repos under /repos: $shared_repos"
[ "$codex_login" = yes ] && echo "- Codex login mounted: \`/ask astra\`, the \`/review\` codex slot, \`vibe-delegate\`."
[ -n "$other_hosts" ] && echo "- Other SSH hosts from ~/.ssh/config (ask per action): $other_hosts"
echo "- GitHub: pull and push this project's repo (single-repo token); \`gh\` for its issues and PRs."
echo "- Toolchain in the image:$toolchain"
echo
echo "## Could be switched on (say exactly this, then carry on with other work)"
echo
[ -z "$mac_user" ] && echo "- A Mac account for screenshots, browsers and native builds: \`vibe-capabilities --setup mac-account\` prints the one-time steps."
[ -n "$mac_user" ] && [ "$mac_port" = closed ] && echo "- The Mac account is declared but port 22 is closed: turn on Remote Login for \`$mac_user\` (System Settings → General → Sharing)."
[ -n "$mac_user" ] && [ "$ssh_auto" = no ] && echo "- Use the Mac account without asking each time: \`touch .vibe-allow-ssh\` in the project (untracked), then relaunch vibe."
[ "$mac_build" = no ] && echo "- A Mac build bridge for this project: tell the agent \"Set up native builds using Vibe's Mac setup guide\" (docs/mac-build-setup.md)."
echo "- Direct HTTP to another site: add its host to \`.vibe/domains\` (untracked) and relaunch."
[ "$codex_login" = no ] && echo "- Codex (second opinions, \`/ask astra\`): run \`vibe\`, choose Codex once, follow its login."
have uv || echo "- A Python toolchain with uv/ruff/mypy: relaunch with \`vibe --profile python\`."
echo
echo "## Genuinely not here (and what to do instead)"
echo
echo "- A browser or display inside the container: none can be installed through the firewall.$([ -n "$mac_user" ] && echo " Use the Mac account above." || echo " Ask for the Mac account (above).")"
echo "- Arbitrary outbound HTTP from the shell: use web search, the Mac account, or ask for the domain."
echo "- The user's own Mac login, files or keychain: never; the agent account is separate on purpose."
