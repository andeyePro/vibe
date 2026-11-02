#!/bin/bash
# vibe-shot — installed as /usr/local/bin/vibe-shot.
#
# One command for "look at it": render a URL or a local page on the Mac
# account that vibe-capabilities reports, in a headless Chromium (Playwright),
# and bring the PNG back into the container so the agent can view it (Claude:
# the Read tool displays images). It exists because the capability alone was
# not enough — an agent reminded that it CAN see, but left to hand-roll an
# SSH + Playwright + scp script per project, still says "I can't".
#
#   vibe-shot https://example.org               a page the Mac can reach
#   vibe-shot http://localhost:3000             a server running ON THE MAC
#   vibe-shot site/dist                         a built folder: uploads it,
#                                               opens its index.html
#   vibe-shot site/dist --path about/index.html   another page in the folder
#   vibe-shot page.html                         a single file (only that file
#                                               is uploaded; use the folder
#                                               form when it needs its CSS)
#   vibe-shot --sim [--open com.example.app]   the iOS Simulator (boots an
#                                               iPhone if none is running)
#   vibe-shot --screen [--app "App Name"]       the Mac account's own screen
#                                               (needs it logged in on the
#                                               Mac's display, see --check)
#   options: --viewport WxH (default 1280x800; 390x844 is a phone)
#            --full-page   --wait-for CSS_SELECTOR   --out PATH
#            --check       report which of web / Simulator / screen are
#                          ready on the Mac, and how to fix the rest
#   file:// URLs are paths ON THE MAC. A folder upload leaves out .git,
#   node_modules, .vibe, .vss and .env*; symlinks travel as links (not
#   followed), so links pointing outside the folder break there.
#
# Running it IS an SSH action on the Mac account: the SSH discipline's
# per-action ask applies unless the project pre-authorises SSH.
#
# One SSH connection per run. The remote script and its arguments travel
# base64-encoded inside the command (the Mac's login shell never parses a
# user-supplied string); an uploaded folder travels as a tar on stdin; the
# PNG comes back base64 between markers on stdout. The remote side works in
# a fresh mktemp directory and removes it on exit.
set -uo pipefail

die() { printf 'vibe-shot: %s\n' "$1" >&2; exit "${2:-1}"; }
need_value() { [ "$1" -ge 2 ] || die "$2 needs a value" 2; }

mac_host=${VIBE_CAP_MAC_HOST:-host.docker.internal}
home=${HOME:-/home/node}
ssh_config=${VIBE_CAP_SSH_CONFIG:-$home/.ssh/config}
ws=${VIBE_CAP_WORKSPACE:-/workspace}

target="" viewport="1280x800" full=0 wait_for="" out="" subpath="index.html" check=0
native="" native_arg="" native_flag=""
while [ $# -gt 0 ]; do
  case "$1" in
    --viewport) need_value $# "$1"; viewport=$2; shift 2 ;;
    --full-page) full=1; shift ;;
    --wait-for) need_value $# "$1"; wait_for=$2; shift 2 ;;
    --out) need_value $# "$1"; out=$2; shift 2 ;;
    --path) need_value $# "$1"; subpath=$2; shift 2 ;;
    --check) check=1; shift ;;
    --sim | --screen)
      [ -z "$native" ] || [ "$native" = "${1#--}" ] || die "--sim and --screen are separate captures; pick one" 2
      native=${1#--}; shift ;;
    --open | --app)
      need_value $# "$1"
      [ -z "$native_flag" ] || [ "$native_flag" = "$1" ] || die "--open and --app belong to different captures" 2
      native_flag=$1; native_arg=$2; shift 2 ;;
    -h | --help) sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1 (try --help)" 2 ;;
    *) [ -z "$target" ] || die "one target only" 2; target=$1; shift ;;
  esac
done

case "$viewport" in
  [0-9]*x[0-9]*) width=${viewport%x*}; height=${viewport#*x} ;;
  *) die "--viewport must be WIDTHxHEIGHT, e.g. 390x844" 2 ;;
esac
case "$width$height" in *[!0-9]*) die "--viewport must be WIDTHxHEIGHT" 2 ;; esac
[ "$width" -ge 100 ] && [ "$width" -le 4000 ] && [ "$height" -ge 100 ] && [ "$height" -le 4000 ] ||
  die "--viewport sides must be 100-4000 pixels" 2

user=${VIBE_MAC_USER:-}
if [ -z "$user" ] && [ -r "$ssh_config" ]; then
  user=$(awk -v target="$mac_host" '
    tolower($1) == "host" { inblock = 0; for (i = 2; i <= NF; i++) if ($i == target) inblock = 1; next }
    inblock && tolower($1) == "user" { print $2; exit }' "$ssh_config" 2>/dev/null)
fi
case "$user" in "" | *[!A-Za-z0-9._-]*)
  die "no Mac account is declared for $mac_host. Setup: vibe-capabilities --setup mac-account" ;;
esac

# ── the script that runs on the Mac ──────────────────────────────────────────
# Arguments arrive as base64 lines in $1: mode, url, width, height, full,
# wait, and the native argument (--open bundle id / --app name).
remote_script='set -u
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
dec() { base64 -D 2>/dev/null || base64 -d; }
args=$(printf "%s" "$1" | dec) || { echo "vibe-shot(mac): bad arguments" >&2; exit 2; }
mode=$(printf "%s\n" "$args" | sed -n 1p); url=$(printf "%s\n" "$args" | sed -n 2p)
w=$(printf "%s\n" "$args" | sed -n 3p); h=$(printf "%s\n" "$args" | sed -n 4p)
full=$(printf "%s\n" "$args" | sed -n 5p); wait=$(printf "%s\n" "$args" | sed -n 6p)
native=$(printf "%s\n" "$args" | sed -n 7p)
fail() { echo "vibe-shot(mac): $1" >&2; exit "${2:-4}"; }
web_fix="npm i -g playwright && npx playwright install chromium (and brew install node if node is missing)"
sim_fix="install Xcode and an iOS simulator runtime (Xcode > Settings > Components), open Xcode once as this account to accept its licence, and if only the Command Line Tools are selected: sudo xcode-select -s /Applications/Xcode.app"
screen_fix="make $(id -un) the active user on the Mac display (a session switched to the background cannot be captured) and allow Screen Recording for sshd-keygen-wrapper in System Settings > Privacy & Security"
web_ready() { command -v node >/dev/null 2>&1 || return 1; NODE_PATH=$(npm root -g 2>/dev/null); export NODE_PATH; node -e "require(\"playwright\")" 2>/dev/null; }
UDID_RE="[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
first_iphone() { xcrun simctl list devices "$1" 2>/dev/null | grep iPhone | grep -oE "$UDID_RE" | head -n 1; }
sim_ready() { command -v xcrun >/dev/null 2>&1 && xcrun simctl help >/dev/null 2>&1 && [ -n "$(first_iphone available)" ]; }
# Screen Recording cannot be approved over SSH; without it screencapture still
# "succeeds" with wallpaper only. Preflight it when the Mac can say (an error
# here is "unknown", not "no").
screen_permitted() { [ "$(osascript -l JavaScript -e "ObjC.import(\"CoreGraphics\"); \$.CGPreflightScreenCaptureAccess()" 2>/dev/null)" != false ]; }
screen_ready() { command -v screencapture >/dev/null 2>&1 && [ "$( (stat -f %Su /dev/console) 2>/dev/null)" = "$(id -un)" ] && screen_permitted; }
if [ "$mode" = check ]; then
  any=0
  if web_ready; then echo "vibe-shot(mac): web pages: ready" >&2; any=1; else echo "vibe-shot(mac): web pages: not ready: $web_fix" >&2; fi
  if sim_ready; then echo "vibe-shot(mac): iOS Simulator: ready" >&2; any=1; else echo "vibe-shot(mac): iOS Simulator: not ready: $sim_fix" >&2; fi
  if screen_ready; then echo "vibe-shot(mac): screen: ready" >&2; any=1; else echo "vibe-shot(mac): screen: not ready: $screen_fix" >&2; fi
  [ "$any" = 1 ] && exit 0
  exit 4
fi
tmp=$(mktemp -d "${TMPDIR:-/tmp}/vibe-shot.XXXXXX") || exit 5
trap "rm -rf \"$tmp\"" EXIT
if [ "$mode" = sim ]; then
  sim_ready || fail "iOS Simulator not ready: $sim_fix"
  # Only a booted iPhone counts (a booted watch or iPad would be the wrong
  # screen), and every later command names it by id rather than "booted".
  dev=$(first_iphone booted)
  if [ -z "$dev" ]; then
    dev=$(first_iphone available)
    [ -n "$dev" ] || fail "no iPhone simulator is installed: $sim_fix"
    xcrun simctl boot "$dev" >&2 || fail "could not boot simulator $dev" 5
    xcrun simctl bootstatus "$dev" -b >/dev/null || fail "simulator $dev did not finish booting" 5
  fi
  if [ -n "$native" ]; then
    xcrun simctl launch --terminate-running-process "$dev" "$native" >&2 ||
      fail "could not launch $native (is it installed on simulator $dev?)" 5
    sleep 3
  fi
  xcrun simctl io "$dev" screenshot "$tmp/shot.png" >&2 || fail "simulator screenshot failed" 5
elif [ "$mode" = screen ]; then
  screen_ready || fail "screen not ready: $screen_fix"
  if [ -n "$native" ]; then open -a "$native" >&2 || fail "could not open $native" 5; sleep 3; fi
  screencapture -x "$tmp/shot.png" >&2 || fail "screencapture failed: $screen_fix" 5
  echo "vibe-shot(mac): if the image shows only the wallpaper and menu bar, Screen Recording is not allowed; if it shows the lock screen, the display is locked" >&2
else
  web_ready || fail "web pages not ready: $web_fix"
  if [ "$mode" = upload ]; then
    mkdir "$tmp/site" && tar -xf - -C "$tmp/site" || fail "upload failed" 5
    url="file://$tmp/site/$url"
  fi
node - "$url" "$tmp/shot.png" "$w" "$h" "$full" "$wait" >&2 <<'"'"'JS'"'"' || exit $?
const { chromium } = require("playwright");
const [url, out, w, h, full, wait] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: Number(w), height: Number(h) } });
    await page.goto(url, { waitUntil: "load", timeout: 45000 });
    await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
    if (wait) await page.waitForSelector(wait, { timeout: 15000 });
    await page.screenshot({ path: out, fullPage: full === "1" });
  } finally { await browser.close(); }
})().catch((e) => { console.error("vibe-shot(mac): " + e.message); process.exit(3); });
JS
fi
[ -s "$tmp/shot.png" ] || fail "the capture produced no image" 3
# Retina and 5K captures are huge; the viewer downscales anyway.
sips -Z 2400 "$tmp/shot.png" >/dev/null 2>&1 || true
printf "\nVIBE-SHOT-PNG-BEGIN\n"
base64 < "$tmp/shot.png"
printf "\nVIBE-SHOT-PNG-END\n"'

b64() { base64 | tr -d '\n'; }

upload_dir=""
mode=url url=""
if [ "$check" = 1 ]; then
  [ -z "$native$native_flag$target" ] || die "--check takes no other target or capture option" 2
  mode=check
elif [ -n "$native" ]; then
  [ -z "$target" ] || die "--$native takes no URL, folder or file" 2
  mode=$native
  if [ -n "$native_flag" ]; then
    [ "$native/$native_flag" = sim/--open ] || [ "$native/$native_flag" = screen/--app ] ||
      die "--open goes with --sim, --app with --screen" 2
  fi
  case "$native_arg" in *$'\n'* | *[!A-Za-z0-9._\ -]*) die "--open / --app take a bundle id or an app name (letters, digits, space, . _ -)" 2 ;; esac
  if [ "$native" = sim ]; then case "$native_arg" in *[!A-Za-z0-9.-]*) die "--open takes a bundle id, e.g. com.example.app" 2 ;; esac; fi
elif [ -n "$native_arg" ]; then
  die "--open goes with --sim, --app with --screen" 2
elif [ -z "$target" ]; then
  die "give a URL, a folder or a file (try --help)" 2
else
  case "$target" in
    http://* | https://* | file://*) url=$target ;;
    *)
      [ -e "$target" ] || die "no such file or folder: $target" 2
      mode=upload
      if [ -d "$target" ]; then
        upload_dir=$target; url=$subpath upload_only=""
        case "/$url/" in //* | */../*) die "--path must be a relative path inside the folder" 2 ;; esac
        [ -e "$upload_dir/$url" ] || die "$upload_dir has no $url (use --path)" 2
      else
        upload_dir=$(dirname -- "$target"); url=$(basename -- "$target"); upload_only=$url
      fi
      ;;
  esac
fi
case "$url$wait_for" in *$'\n'*) die "newlines are not allowed in the URL or selector" 2 ;; esac

args=$(printf '%s\n%s\n%s\n%s\n%s\n%s\n%s\n' "$mode" "$url" "$width" "$height" "$full" "$wait_for" "$native_arg" | b64)
remote="/bin/bash -c \"\$(echo $(printf '%s' "$remote_script" | b64) | { base64 -D 2>/dev/null || base64 -d; })\" vibe-shot $args"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)
work=$(mktemp -d "${TMPDIR:-/tmp}/vibe-shot-local.XXXXXX") || die "cannot create a temp dir"
trap 'rm -rf "$work"' EXIT
stdin_file=/dev/null
if [ "$mode" = upload ]; then
  # Built to a file first: its real size is what is checked, and a tar
  # failure is reported as a local failure, not blamed on the Mac.
  if [ -n "${upload_only:-}" ]; then
    tar -C "$upload_dir" -cf "$work/upload.tar" -- "$upload_only" || die "could not package $target"
  else
    tar -C "$upload_dir" --exclude=./.git --exclude=node_modules --exclude=./.vibe --exclude=./.vss \
      --exclude='./.env*' -cf "$work/upload.tar" . || die "could not package $upload_dir"
  fi
  max_kb=${VIBE_SHOT_MAX_KB:-204800}
  case "$max_kb" in '' | *[!0-9]*) max_kb=204800 ;; esac
  size_kb=$(( $(wc -c < "$work/upload.tar") / 1024 ))
  [ "$size_kb" -le "$max_kb" ] || die "the upload is ${size_kb} KB (limit ${max_kb} KB); point at the built output folder" 2
  stdin_file=$work/upload.tar
fi
response=$(ssh "${ssh_opts[@]}" "$user@$mac_host" "$remote" < "$stdin_file")
rc=$?
[ "$rc" -eq 0 ] || die "the Mac side failed (exit $rc); see the message above. Readiness: vibe-shot --check" "$rc"
[ "$mode" = check ] && { echo "vibe-shot: the Mac account $user@$mac_host is ready (details above)"; exit 0; }

if [ -z "$out" ]; then
  mkdir -p "$ws/.vibe/shots" 2>/dev/null || die "cannot create $ws/.vibe/shots"
  case "$mode" in
    sim | screen) out="$ws/.vibe/shots/shot-$(date -u +%Y%m%dT%H%M%SZ)-$mode.png" ;;
    *) out="$ws/.vibe/shots/shot-$(date -u +%Y%m%dT%H%M%SZ)-${width}x${height}.png" ;;
  esac
fi
printf '%s\n' "$response" | awk '/^VIBE-SHOT-PNG-END$/{f=0} f{print} /^VIBE-SHOT-PNG-BEGIN$/{f=1}' > "$work/png.b64"
base64 -d < "$work/png.b64" > "$work/shot.png" 2>/dev/null || die "the image that came back does not decode"
[ "$(head -c 8 "$work/shot.png" | od -An -tx1 | tr -d ' \n')" = 89504e470d0a1a0a ] || die "no PNG came back"
mv -f -- "$work/shot.png" "$out" || die "cannot write $out"
echo "$out"
