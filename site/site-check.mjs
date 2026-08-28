// Post-build assertions for vibe.andeye.com — run via `npm run check` (which
// builds first) or `node site-check.mjs` against an existing dist/. Guards the
// invariants the page copy has been reviewed against; exits 1 on failure.
import { readFileSync, existsSync } from 'node:fs';

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
check(`command deck has at least 10 chips (found ${chips.length})`, chips.length >= 10);
const checklists = html.match(/<ol class="steps"/g) || [];
check(`every chip carries a checklist (found ${checklists.length})`, checklists.length === chips.length);
// the deck must ship UNLOCKED server-side — lock states are script-applied,
// so a dead script degrades to plain readable chips, not dimmed dead ones
check('no server-rendered locked state on any chip', !/class="dstep[^"]*\blocked\b/.test(html));
check('launch chip present', /id="step-launch"/.test(html));
check('launch checklist covers repo → PAT → container → firewall → Claude sign-in',
  ['its GitHub remote', 'fine-grained PAT', 'sandboxed container', 'short allowlist',
   'your Claude subscription'].every((s) => html.includes(s)));
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

check('launch banner fields are the launcher\'s own (project/github/hooks/extras)',
  ['\u{1F680} vibe session starting', 'project : ', 'github  : ',
   'hooks   : tool-call guards + idle bell',
   'extras  : /diet · /feast · /vs · shellcheck-fixer · security-review']
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

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall site checks passed');
