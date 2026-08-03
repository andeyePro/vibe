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

// the old sections are gone but their live anchors still land somewhere
check('legacy #how / #sandbox anchors preserved',
  html.includes('<span id="how"') && html.includes('<span id="sandbox"'));

// andeye sites rule: no raw email addresses ever
check('no mailto: and no raw email addresses',
  !html.includes('mailto:') && !/[\w.+-]+@[\w-]+\.[a-z]{2,}/i.test(html.replace(/[\w.+-]+%40/g, '')));

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall site checks passed');
