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
# probe failure degrades to "unknown", never to an error. Under Codex the
# hooks run with `env -i`, so the env overrides (VIBE_SSH_AUTO, VIBE_MAC_USER,
# VIBE_CAP_*) do not reach them there: the file-based signals (the SSH config,
# .vibe-allow-ssh) are the ones that hold in both runtimes.
#
# Usage: vibe-capabilities            full inventory (Markdown)
#        vibe-capabilities --brief    one line per available capability
#        vibe-capabilities --setup mac-account
#                                     the steps to give agents a Mac account
#        vibe-capabilities --stop-hook
#                                     Stop hook (Claude Code and Codex): when
#                                     the turn's final message says "I can't
#                                     see / run / build …" or hands the user a
#                                     job the agent could do itself, send it
#                                     back ONCE with this inventory. Silent
#                                     (allow) on everything else, on a second
#                                     stop in the same chain (stop_hook_active)
#                                     and on any failure of its own.
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
  --stop-hook) mode=stop-hook ;;
  --setup)
    case "${2:-}" in
      mac-account) mode=setup-mac ;;
      *) echo "vibe-capabilities: --setup takes: mac-account" >&2; exit 2 ;;
    esac ;;
  -h | --help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "vibe-capabilities: unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

# ── stop-hook mode (runs before any probe: it must stay cheap on every turn) ──
if [ "$mode" = stop-hook ]; then
  command -v jq >/dev/null 2>&1 || exit 0
  payload=$(cat 2>/dev/null) || exit 0
  [ -n "$payload" ] || exit 0
  [ "$(printf '%s' "$payload" | jq -r '.stop_hook_active // false' 2>/dev/null)" = true ] && exit 0
  message=$(printf '%s' "$payload" | jq -r '.last_assistant_message // empty' 2>/dev/null) || exit 0
  [ -n "$message" ] || exit 0
  session=$(printf '%s' "$payload" | jq -r '.session_id // "unknown"' 2>/dev/null | tr -cd 'A-Za-z0-9_-' | cut -c1-80)
  # Fenced code, quoted lines and inline code are the agent quoting, not
  # claiming. Curly apostrophes (common in GPT output) are normalised.
  prose=$(printf '%s\n' "$message" | awk '/^[[:space:]]*(```|~~~)/ { f = !f; next } !f && !/^[[:space:]]*>/' \
    | sed -e "s/\`[^\`]*\`//g" -e "s/’/'/g" | tr '\n' ' ' | tr '[:upper:]' '[:lower:]')
  # Visual and build/run verbs only: "I can't reach the Pi" or "I can't test
  # on Windows" are honest limits, not missed capabilities.
  verbs="see|view|look at|observe|render|screenshot|open|run|build|launch|display|browse|preview"
  denial_re="(^|[^a-z])((i|we) (can'?t|cannot|can not|have no way to|don'?t have (a way|any way|the ability) to)|(i'?m|i am|we'?re|we are) (unable|not able) to) ($verbs)([^a-z]|$)"
  offload_re="(^|[^a-z])((you('ll| will)? need to|please|could you|can you) (take|send|share|paste|attach) (me )?(a |the )?screenshot|(i|we) (have|'ve got) no (browser|display|gui|screen|eyes)|(i|we) don'?t have (a browser|a display|a gui|eyes|visual access)|you('ll| will) need to (look at|view|eyeball|check) (it|this|that|the (page|layout|screen|ui|output|rendering|app|result)))([^a-z]|$)"
  match=$(printf '%s' "$prose" | grep -oE "$denial_re|$offload_re" | head -n1 | sed -e 's/^[^a-z]*//' -e 's/[^a-z]*$//')
  [ -n "$match" ] || exit 0
  # Own loop guard, independent of the runtime's stop_hook_active: at most one
  # nudge per session per 10 minutes.
  stamp="${TMPDIR:-/tmp}/vibe-cap-nudge.$session"
  now=$(date +%s)
  if [ -f "$stamp" ] && [ ! -L "$stamp" ]; then
    last=$(head -c 20 "$stamp" 2>/dev/null | tr -cd '0-9')
    [ -n "$last" ] && [ $((now - last)) -lt 600 ] && exit 0
  fi
  { printf '%s\n' "$now" > "$stamp"; } 2>/dev/null || exit 0
  inventory=$(VIBE_CAP_NO_PROBE=1 bash "$0" --brief 2>/dev/null | head -n 12)
  if [ "${VIBE_SSH_AUTO:-}" = 1 ] || [ -f "$ws/.vibe-allow-ssh" ]; then
    act="do it now (SSH is pre-authorised in this project)"
  else
    act="offer it to the user in one line with the exact command (for example: I can check this on the Mac account: ssh <account>@host.docker.internal '...' - OK?) instead of saying you can't"
  fi
  reason="vibe capability check: your reply says \"$match\". This container may be able to do that (\`vibe-capabilities\` has the full list):
$inventory
If one of these covers it (for anything visual: vibe-shot <url|folder|file> renders it on the Mac account and prints a PNG path to view - Claude: the Read tool; Codex: the image file), $act. If none does, give the user the one-line step from \`vibe-capabilities\` under \"Could be switched on\". If you already checked and it genuinely cannot be done here, say so in one line and finish."
  jq -n --arg reason "$reason" '{decision: "block", reason: $reason}' 2>/dev/null || exit 0
  exit 0
fi

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
  case "$mac_host" in
    *[!A-Za-z0-9.-]*) mac_port=unknown ;;
    *) if timeout 2 bash -c '</dev/tcp/$1/22' _ "$mac_host" 2>/dev/null; then mac_port=open; else mac_port=closed; fi ;;
  esac
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
  printf 'Mac account `%s@%s` (declared by %s; port 22 %s): anything that needs eyes or a Mac runs there — render a page in a headless browser and screenshot it, build and launch a Mac/iOS app, reach URLs the container firewall blocks. To look at a page: `vibe-shot <url|folder|file> [--viewport 390x844]` renders it there and prints the PNG path; open it (Claude: the Read tool displays images; Codex: view the image file). SSH %s.' \
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
5. Once, logged in as that user: \`brew install node\` if needed, then
   \`npm i -g playwright && npx playwright install chromium\` so agents can
   render pages with \`vibe-shot\`.
6. Optional: let agents use it without asking each time — in a project,
   \`touch .vibe-allow-ssh\` (untracked) and relaunch vibe.

Check: inside any vibe session run \`vibe-shot --check\` (one SSH call) and
\`vibe-capabilities\`; the first line of
"Available now" should name the account on \`$mac_host\` with port 22 open.
Status on THIS container: $([ -n "$mac_user" ] && echo "declared as $mac_user (port 22 $mac_port)" || echo "not declared yet (step 3)").
EOF
  exit 0
fi

if [ "$mode" = brief ]; then
  [ -n "$mac_user" ] && echo "- $(mac_line)"
  [ "$mac_build" = yes ] && echo "- mac-build doctor|build|test|screenshot (this project's Mac build bridge)"
  echo "- view images: Claude's Read tool displays PNG/JPG; Codex can view image files"
  echo "- web: search tools route outside the firewall; direct HTTP only to GitHub, npm, Anthropic, VS Code marketplace${extra_domains:+ and $extra_domains}"
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
echo "- Web: WebSearch/WebFetch-style tools route outside the container firewall. Direct HTTP from the shell reaches only GitHub, npm, Anthropic, the VS Code marketplace${extra_domains:+ and the project extra domains $extra_domains}."
[ -d "$brain2" ] && echo "- \`$brain2\`: the user's second brain (read; start at \`$brain2/Brain2.md\`, search it before asking)."
[ -d "$zotero" ] && echo "- \`$zotero\`: Zotero PDFs, read-only."
[ -d "$learnings" ] && echo "- \`$learnings\`: cross-project learning library (read)."
[ -n "$shared_repos" ] && echo "- Shared repos under /repos: $shared_repos"
echo "- Helpers: parallel subagents (Claude's Agent tool; under Codex, \`vibe-delegate role\`), \`/ask sonnet|opus|haiku\` for a one-shot second model on the subscription, \`/review\` for a code review, \`/vs\` for an adversarial build."
[ "$codex_login" = yes ] && echo "- Codex login mounted: \`/ask astra\`, the \`/review\` codex slot, \`vibe-delegate\`."
[ -n "${GEMINI_API_KEY:-}" ] && echo "- Gemini key present: \`/review\` adds a Gemini opinion (when \`generativelanguage.googleapis.com\` is in the project's domains)."
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
[ -z "${GEMINI_API_KEY:-}" ] && echo "- A Gemini second opinion in \`/review\`: put \`GEMINI_API_KEY=<key>\` in \`~/.vibe/tokens\` on the host and add \`generativelanguage.googleapis.com\` to \`.vibe/domains\`."
echo
echo "## Genuinely not here (and what to do instead)"
echo
echo "- A browser or display inside the container: none can be installed through the firewall.$([ -n "$mac_user" ] && echo " Use the Mac account above." || echo " Ask for the Mac account (above).")"
echo "- Arbitrary outbound HTTP from the shell: use web search, the Mac account, or ask for the domain."
echo "- The user's own Mac login, files or keychain: never; the agent account is separate on purpose."
