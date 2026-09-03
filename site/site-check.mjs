// Post-build assertions for vibe.andeye.com — run via `npm run check` (which
// builds first) or `node site-check.mjs` against an existing dist/. Guards the
// invariants the page copy has been reviewed against; exits 1 on failure.
import { readFileSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

const distPath = new URL('./dist/index.html', import.meta.url);
if (!existsSync(distPath)) {
  console.error('dist/index.html not found — run `npm run build` first (or `npm run check`).');
  process.exit(1);
}
// normalise entity-encoded ampersands so href checks survive Astro/minifier
// encoding choices (&amp; / &#38; / raw & are all the same URL)
const html = readFileSync(distPath, 'utf8').replace(/&(amp|#38);/g, '&');
let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? 'ok ' : 'FAIL'}  ${name}`);
  if (!ok) failures++;
};

// hero CTAs: coders get the repo, non-coders get the prefilled contact form
check('install CTA links the README install section',
  html.includes('https://github.com/andeyePro/vibe#install'));
check('register CTA uses the contact.andeye.com prefill convention',
  html.includes('contact.andeye.com/?source=vibe.andeye.com')
  && html.includes('subject=vibe%20waitlist'));
check('no "one-click install" promise anywhere', !/one.click install/i.test(html));

// the journey: deck chips + checklists present, in launcher order
const chips = html.match(/data-step="/g) || [];
check(`command deck has exactly 13 chips (found ${chips.length})`, chips.length === 13);
const checklists = html.match(/<ol class="steps"/g) || [];
check(`every chip carries a checklist (found ${checklists.length})`, checklists.length === chips.length);
// the deck must ship UNLOCKED server-side — lock states are script-applied,
// so a dead script degrades to plain readable chips, not dimmed dead ones
check('no server-rendered locked state on any chip', !/class="dstep[^"]*\blocked\b/.test(html));
check('launch chip present', /id="step-launch"/.test(html));
check('journey.locked_note copy is unchanged ("run Launch first" still renders)',
  html.includes('run Launch first'));

// -----------------------------------------------------------------------
// task_030 chip helpers: extract one chip's own built HTML fragment, and
// the chip's own entries from the embedded lines map, without depending on
// Astro's generated `data-astro-cid-*` attribute order.
// -----------------------------------------------------------------------

// chipBlock(id): the chip's rendered <div class="dstep" id="step-<id>" ...>
// fragment, up to (but not including) the next chip's dstep div — or to the
// end of the deck for the last chip. Matches the id attribute-agnostically
// (Astro injects `data-astro-cid-*` right after it), never a literal
// `id="step-<id>">`.
function chipBlock(id) {
  const startRe = new RegExp(`<div class="dstep"[^>]*\\bid="step-${id}"[^>]*>`);
  const m = html.match(startRe);
  if (!m) return '';
  const rest = html.slice(m.index + m[0].length);
  const nextIdx = rest.search(/<div class="dstep"[^>]*\bid="step-/);
  return nextIdx === -1 ? rest : rest.slice(0, nextIdx);
}

// The embedded lines map: index.astro's define:vars block serialises
// `stepLines` (chip id -> lines array) as a JSON object literal assigned to
// `const COPY = {...}` inside an inline <script>. Parse that JSON rather
// than regexing text, so `step` / `tone` / `text` come back as real fields.
function parseCopy() {
  const marker = 'const COPY = ';
  const i = html.indexOf(marker);
  if (i === -1) throw new Error('embedded COPY data (const COPY = {...}) not found in built HTML');
  const start = i + marker.length;
  const tail = html.slice(start);
  const end = tail.indexOf('};');
  if (end === -1) throw new Error('could not find the end of the embedded COPY data');
  return JSON.parse(tail.slice(0, end + 1));
}
const COPY_DATA = parseCopy();

// linesFor(id): this chip's entry from the embedded lines map (COPY.lines).
function linesFor(id) {
  return (COPY_DATA.lines && COPY_DATA.lines[id]) || [];
}
// All of a chip's line `text` values, newline-joined, for substring checks.
const linesText = (id) => linesFor(id).map((l) => l.text).join('\n');

// chipCmd(id): the chip's own top command, as rendered in its chip-cmd span
// (the `cmd:` YAML field — distinct from a line's `cmd: true` marker, which
// flags that line as an echoed shell command inside the terminal transcript).
function chipCmd(id) {
  const m = chipBlock(id).match(/<span class="chip-cmd"[^>]*>([^<]*)<\/span>/);
  return m ? m[1] : null;
}

// checklistLength(id): number of <li> items in this chip's built checklist.
// Astro injects a data-astro-cid-* attribute on both <ol class="steps"> and
// each <li>, so match both attribute-agnostically rather than assuming the
// literal closing `>` follows immediately.
function checklistLength(id) {
  const m = chipBlock(id).match(/<ol class="steps"[^>]*>([\s\S]*?)<\/ol>/);
  return m ? (m[1].match(/<li[^>]*>/g) || []).length : 0;
}
check('red-team chips present (firewall + content guard)',
  html.includes('id="step-curl"') && html.includes('id="step-leak"'));
check('firewall copy names the extras rather than claiming a closed trio',
  html.includes('a few named extras') && !html.includes('everything else is refused'));
check('content-guard copy says WARN also stops the commit',
  html.includes('both stop the commit'));

// sticky-terminal height must stay viewport-bounded (short desktop windows
// would otherwise pin the terminal's bottom out of reach) and the hero must
// point at the demo section
check('terminal height is viewport-bounded, not a bare fixed px',
  /\.term-body[^{]*\{[^}]*height:\s*clamp\(/.test(html));
check('hero links to #demo', html.includes('href="#demo"'));

// the old sections are gone but their live anchors still land somewhere
check('legacy #how / #sandbox anchors preserved',
  html.includes('<span id="how"') && html.includes('<span id="sandbox"'));

// ---------------------------------------------------------------------------
// demo fidelity: the interactive transcript quotes the real product. Pin the
// demo's key strings to the launcher / firewall / content-guard / command
// sources so the demo can't silently drift from what vibe actually prints.
// Dashes are normalised (site copy uses " – ", sources vary) before matching.
const src = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const launcher = src('../vibe');
const firewall = src('../devcontainer/init-firewall.sh');
const scanner = src('../devcontainer/git-hooks/vibe-content-scan.sh');
const vssCmd = src('../devcontainer/commands/vss.md');
const vsssCmd = src('../devcontainer/commands/vsss.md');
const budgetCmd = src('../devcontainer/commands/budget.md');
const cCmd = src('../devcontainer/commands/c.md');
const norm = (s) => s.replace(/[–—]/g, '-').replace(/…/g, '...');
const H = norm(html);
const inBoth = (s, source) => H.includes(norm(s)) && norm(source).includes(norm(s));
// scoped variant of inBoth: the string must appear in the given text block
// (a chip's lines-map text, or its rendered HTML block) AND in the
// launcher/firewall source — used by the per-chip guards below instead of
// matching against the whole page (H).
const inBothIn = (s, text, source) => norm(text).includes(norm(s)) && norm(source).includes(norm(s));

// -----------------------------------------------------------------------
// task_030: the hero Launch chip is now the everyday reused-container path
// (banner, firewall check, sign-in already valid, ready); the PAT-prompt /
// image-build lines it used to carry moved to a demoted "First time" chip,
// and a new "Once a quarter" chip carries `vibe pat`. Replaces the single
// "launch checklist covers repo → PAT → container → firewall → Claude
// sign-in" guard that used to live here.
// -----------------------------------------------------------------------

// (a) everyday-launch guard
const launchBlock = chipBlock('launch');
const launchLines = linesText('launch');
const launchLinesJSON = JSON.stringify(linesFor('launch'));
check('everyday-launch banner quotes the launcher, in its own field order (project/path/github/hooks/extras)',
  ['\u{1F680} vibe session starting', 'project : ', 'path    : ', 'github  : ',
   'hooks   : tool-call guards + idle bell',
   'extras  : 12 commands (/vs /vss /vsss /wide /learn /budget …) · 5 agents']
    .every((s) => inBothIn(s, launchLines, launcher)));
check('everyday-launch chip keeps the firewall verification pin, verbatim from init-firewall.sh',
  inBothIn('Firewall verification passed - unable to reach https://example.com as expected', launchLines, firewall));
check('everyday-launch chip shows Claude sign-in already valid, not a prompt',
  launchLines.includes('your Claude subscription'));
check('everyday-launch checklist keeps the short-allowlist line',
  launchBlock.includes('short allowlist'));
check('everyday-launch chip carries no first-launch-only content (PAT prompt / image build / token-saved)',
  ['fine-grained PAT', 'Token saved', 'Building vibe container image', 'Only select repositories', 'sandboxed container']
    .every((s) => !launchBlock.includes(s) && !launchLinesJSON.includes(s)));

// (b) first-launch guard
check('first-launch chip present', /id="step-first-launch"/.test(html));
const firstLaunchLines = linesText('first-launch');
check('first-launch chip carries the PAT-prompt / image-build lines verbatim from the launcher',
  ['No GitHub token found for', 'Only select repositories',
   "Token saved - you won't be asked again for this repo", 'Building vibe container image']
    .every((s) => inBothIn(s, firstLaunchLines, launcher)));
check('first-launch checklist mentions the fine-grained PAT and the sandboxed container',
  chipBlock('first-launch').includes('fine-grained PAT') && chipBlock('first-launch').includes('sandboxed container'));

// (c) pat guard
check('pat chip present with cmd `vibe pat`', /id="step-pat"/.test(html) && chipCmd('pat') === 'vibe pat');
const patLines = linesText('pat');
check('pat chip quotes the launcher\'s expiry / no-rebuild wording',
  ['90 days is a good default', 'Takes effect on the next vibe launch (no rebuild needed)']
    .every((s) => inBothIn(s, patLines, launcher)));

// AC8: every chip's line `step` values (tone lines included) are contiguous
// 1..N, where N is that chip's own built checklist length.
function stepsContiguous(id) {
  const len = checklistLength(id);
  const steps = linesFor(id).map((l) => l.step).filter((s) => s !== undefined).sort((a, b) => a - b);
  const expected = Array.from({ length: len }, (_, i) => i + 1);
  return steps.length === expected.length && steps.every((v, i) => v === expected[i]);
}
const chipIds = Object.keys(COPY_DATA.lines || {});
check(`every chip's line "step" values are contiguous 1..checklist length (${chipIds.length} chips checked)`,
  chipIds.every(stepsContiguous));

check('launch banner fields are the launcher\'s own (project/github/hooks/extras)',
  ['\u{1F680} vibe session starting', 'project : ', 'github  : ',
   'hooks   : tool-call guards + idle bell',
   'extras  : 12 commands (/vs /vss /vsss /wide /learn /budget …) · 5 agents']
    .every((s) => inBoth(s, launcher)));
check('PAT wording quotes the launcher (Token saved / not asked again)',
  inBoth("Token saved - you won't be asked again for this repo", launcher));
check('container build line quotes the launcher',
  inBoth('Building vibe container image', launcher));
check('firewall verification line is verbatim from init-firewall.sh',
  inBoth('Firewall verification passed - unable to reach https://example.com as expected', firewall));
check('firewall allowlist domains the demo names exist in init-firewall.sh',
  ['api.github.com', 'registry.npmjs.org', 'api.anthropic.com'].every((d) => firewall.includes(d)));
check('fail-closed claim is real (init-firewall.sh fails CLOSED)',
  /fails closed/.test(H) && firewall.includes('failing CLOSED'));
check('Radicle claim pinned to the allowlist (seed.radicle.garden)',
  H.includes('Radicle') && firewall.includes('seed.radicle.garden'));
check('content-guard rule id in the demo is a real BLOCK rule',
  H.includes('secret-assignment') && scanner.includes('"BLOCK" "secret-assignment"'));
check('no invented content-guard rule ids', !H.includes('anthropic-key'));
check('/vss redirect window matches the spec (270s + auto-proceed)',
  inBoth('270s', vssCmd) && inBoth('auto-proceed', vssCmd));
check('/vss audit-trail path matches the spec (.vss/sessions/)',
  inBoth('.vss/sessions/', vssCmd));
check('/vsss relaunch string matches the launcher (claude --continue)',
  H.includes('claude --continue') && launcher.includes('Relaunching claude --continue'));
check('no-autonomous-push claim matches the /vsss exit report',
  H.includes('not pushed') && vsssCmd.includes('not pushed'));
check('/budget honesty line quotes budget.md (estimates, not invoices)',
  inBoth('estimates, not invoices', budgetCmd));
check('/c scratch path matches c.md (copy-latest.txt)',
  inBoth('copy-latest.txt', cCmd));

// andeye sites rule: no raw email addresses ever
check('no mailto: and no raw email addresses',
  !html.includes('mailto:') && !/[\w.+-]+@[\w-]+\.[a-z]{2,}/i.test(html.replace(/[\w.+-]+%40/g, '')));

// ---------------------------------------------------------------------------
// task_032: asciinema pipeline — cast fidelity (AC2/AC3), markers/chip
// mapping (AC4), redaction (AC5), launcher/firewall fidelity over the cast
// text (AC6), vendored bundle size (AC8), player-mount markup + the COPY
// fallback data (AC9), and the lazy-load client script shape (AC11).
//
// AC10 (fallback) needs no new guards here: every existing guard ABOVE this
// section — the copy-accuracy inBoth() guards, the exact-13-chips count, the
// .term-body clamp regex, stepsContiguous, and the chip-scoped
// launch/first-launch/pat guards — still runs unchanged against the same
// dist/index.html shape and still passes. No existing guard above had to
// change for this task.
// ---------------------------------------------------------------------------
const distDir = new URL('./dist/', import.meta.url);
const distExists = (p) => existsSync(new URL(p, distDir));
const readDistText = (p) => readFileSync(new URL(p, distDir), 'utf8');
const readDistBuf = (p) => readFileSync(new URL(p, distDir));

// --- AC2: dist/demo/vibe.cast parses ---------------------------------------
let castHeader = null;
let castEvents = [];
let castParseError = null;
try {
  const raw = readDistText('demo/vibe.cast');
  const lines = raw.split('\n').filter((l) => l.trim().length > 0);
  if (lines.length === 0) throw new Error('empty cast file');
  castHeader = JSON.parse(lines[0]);
  castEvents = lines.slice(1).map((l) => JSON.parse(l));
} catch (e) {
  castParseError = e;
}
check('dist/demo/vibe.cast parses as newline-delimited JSON (header + events)', !castParseError);
check('cast header is version 2 with integer width/height',
  !!castHeader && castHeader.version === 2
  && Number.isInteger(castHeader.width) && Number.isInteger(castHeader.height));

const CAST_CODES = new Set(['o', 'i', 'm', 'r']);
function castEventsWellFormed(events) {
  let prevTime = -Infinity;
  for (const e of events) {
    if (!Array.isArray(e) || e.length !== 3) return false;
    const [t, code] = e;
    if (typeof t !== 'number' || Number.isNaN(t) || !CAST_CODES.has(code) || t < prevTime) return false;
    prevTime = t;
  }
  return true;
}
check(`every cast line is a [time, code, data] 3-tuple with code in o/i/m/r and numeric non-decreasing time (${castEvents.length} events)`,
  castEventsWellFormed(castEvents));

// --- AC3: placeholder advisory — printed (not a failure) only while the
// cast header carries "placeholder": true; nothing printed when it's absent.
if (castHeader && castHeader.placeholder) {
  console.log("advisory: dist/demo/vibe.cast is a synthetic placeholder — awaiting Martin's real recording (see site/demo/record.md)");
}

// --- AC4: markers.json shape + chip <-> marker mapping ---------------------
let markersData = [];
let markersParseError = null;
try {
  markersData = JSON.parse(readDistText('demo/markers.json'));
} catch (e) {
  markersParseError = e;
}
check('dist/demo/markers.json parses as an array of {id, time, label}',
  !markersParseError && Array.isArray(markersData)
  && markersData.every((m) => m && typeof m.id === 'string' && typeof m.time === 'number' && typeof m.label === 'string'));

const deckStepIds = [...html.matchAll(/data-step="([a-z0-9-]+)"/g)].map((m) => m[1]);
const chipMarkers = markersData.filter((m) => !m.id.includes(':'));
check('chip-marker ids, in order, equal the 13 data-step ids in dist/index.html',
  JSON.stringify(chipMarkers.map((m) => m.id)) === JSON.stringify(deckStepIds));

check('every checklist step of every chip has its <chip>:<n> step marker',
  chipIds.every((id) => {
    const len = checklistLength(id);
    for (let n = 1; n <= len; n++) {
      if (!markersData.some((m) => m.id === `${id}:${n}`)) return false;
    }
    return true;
  }));

check('every markers.json entry has a matching "m" cast event at the same time with label = id',
  !markersParseError && !castParseError
  && markersData.every((m) => castEvents.some((e) => e[1] === 'm' && e[0] === m.time && e[2] === m.label)));

// --- AC5: redaction over the concatenated, ANSI-stripped "o" payloads ------
const ansiStrip = (s) => s.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
const castOText = ansiStrip(
  castEvents.filter((e) => e[1] === 'o' && typeof e[2] === 'string').map((e) => e[2]).join(''));

const AC5_PATTERNS = [
  /ghp_[A-Za-z0-9]{6,}/,
  /github_pat_/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/,
  /\/Users\/[^/ ]+/,
  /\b(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b/,
];
check('cast text matches none of the AC5 redaction patterns (tokens/emails/home paths/private IPs)',
  AC5_PATTERNS.every((re) => !re.test(castOText)));
check('cast text contains no real repo slug (andeyePro/ or Aqueum/)',
  !castOText.includes('andeyePro/') && !castOText.includes('Aqueum/'));

// --- AC6: fidelity — launcher/firewall strings appear in the cast text AND
// in the sources they're pinned against --------------------------------
check('cast fidelity: launcher/firewall strings appear in the cast text and in their sources',
  ['vibe session starting', 'github  : ', 'Firewall verification passed', 'Token saved',
   'Building vibe container image', '90 days is a good default']
    .every((s) => castOText.includes(s) && (launcher.includes(s) || firewall.includes(s))));

// --- AC8: vendoring — devDependency pin, build/check scripts, gitignore,
// and the vendored bundle's actual gzip size after a real build ------------
const pkgJson = JSON.parse(src('./package.json'));
check('site/package.json pins asciinema-player 3.17.0 as a devDependency',
  !!pkgJson.devDependencies && pkgJson.devDependencies['asciinema-player'] === '3.17.0');
check('build vendors the player before astro build; check runs build then site-check',
  pkgJson.scripts.build === 'node scripts/vendor-player.mjs && astro build'
  && pkgJson.scripts.check === 'npm run build && node site-check.mjs');
check('site/public/vendor/ is gitignored',
  src('./.gitignore').split('\n').some((l) => l.trim().replace(/^\//, '') === 'public/vendor/'));
check('dist/vendor/asciinema-player.min.js exists and gzips to <= 75000 B',
  distExists('vendor/asciinema-player.min.js')
  && gzipSync(readDistBuf('vendor/asciinema-player.min.js')).length <= 75000);
check('dist/vendor/asciinema-player.css exists and gzips to <= 6000 B',
  distExists('vendor/asciinema-player.css')
  && gzipSync(readDistBuf('vendor/asciinema-player.css')).length <= 6000);

// --- AC9: player mount markup; legacy typed-transcript markup is gone; the
// embedded COPY blob (the fallback transcript's data source) still parses
// with its lines/subs/notes shape intact ------------------------------------
check('player mount has id="cast" and /demo/vibe.cast is referenced',
  html.includes('id="cast"') && html.includes('/demo/vibe.cast'));
check('legacy typed-transcript markup is gone (class="trole" / id="termLive")',
  !html.includes('class="trole"') && !html.includes('id="termLive"'));
check('embedded COPY blob still parses via parseCopy(), with its lines/subs/notes shape intact',
  !!COPY_DATA && !!COPY_DATA.lines && !!COPY_DATA.subs && !!COPY_DATA.notes);

// --- AC11: lazy load — nothing in <head> references the player; the client
// script IntersectionObserver-loads it, dynamically imports the vendored
// path, passes the spec's options, wires seek()/marker events, and loads
// before seeking on an early chip click --------------------------------
const headEnd = html.indexOf('</head>');
const headHtml = headEnd === -1 ? html : html.slice(0, headEnd);
check('nothing in <head> references asciinema-player (no script src / preload / modulepreload)',
  !/asciinema-player/.test(headHtml));
check('client script lazily loads the player via IntersectionObserver + a dynamic import of the vendored bundle',
  /IntersectionObserver/.test(html)
  && /import\(\s*VENDOR_JS\s*\)|import\(\s*['"`][^'"`]*asciinema-player\.min\.js['"`]\s*\)/.test(html));
check("player is created with the spec's options, matched minifier-tolerantly",
  [/controls\s*:\s*(false|!1)/, /npt:0:0/, /idleTimeLimit\s*:\s*2\b/,
   /fit\s*:\s*["']width["']/, /terminalLineHeight\s*:\s*1\.7/, /terminalFontFamily/]
    .every((re) => re.test(html)));
check('marker seek/listen wiring is present (seek({marker...}) and a "marker" event listener)',
  /seek\(\{\s*marker/.test(html) && /addEventListener\(\s*["']marker["']/.test(html));
check('a chip click before the player has loaded triggers the load then seeks (loadPlayer referenced from the click handler)',
  /function\s+loadPlayer/.test(html) && /loadPlayer\(\)\.then/.test(html) && html.includes('vibeCast.seekChip(id)'));

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall site checks passed');
