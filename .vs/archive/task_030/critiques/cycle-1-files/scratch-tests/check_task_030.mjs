// Scratch TDD check for task_030 (Generator side). Mirrors the spec's AC1-AC8
// (mechanical parts only — AC9-AC12 are the Tester/Evaluator's job) against
// the built site/dist/index.html and the raw home.md source. Run red first
// (before the edit), then green (after).
import { readFileSync, existsSync } from 'node:fs';

const root = new URL('../../../', import.meta.url); // -> /workspace/
const distPath = new URL('site/dist/index.html', root);
const homePath = new URL('site/src/content/home.md', root);
const vibePath = new URL('vibe', root);
const firewallPath = new URL('devcontainer/init-firewall.sh', root);

if (!existsSync(distPath)) {
  console.error('dist/index.html not found — run `npm run build` in site/ first.');
  process.exit(1);
}

const html = readFileSync(distPath, 'utf8').replace(/&(amp|#38);/g, '&');
const home = readFileSync(homePath, 'utf8');
const launcher = readFileSync(vibePath, 'utf8');
const firewall = readFileSync(firewallPath, 'utf8');

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? 'ok ' : 'FAIL'}  ${name}`);
  if (!ok) failures++;
};

const norm = (s) => s.replace(/[–—]/g, '-').replace(/…/g, '...');
const H = norm(html);
const inBoth = (s, source) => H.includes(norm(s)) && norm(source).includes(norm(s));

// --- AC1: group/chip presence + counts ---
check('AC1: home.md has a "First time" group with id: first-launch',
  /label:\s*First time[\s\S]{0,200}id:\s*first-launch/.test(home));
check('AC1: home.md has a "Once a quarter" group with id: pat',
  /label:\s*Once a quarter[\s\S]{0,200}id:\s*pat/.test(home));
check('AC1: hero chip keeps id: launch', /id:\s*launch\b/.test(home));
check('AC1: journey.locked_note unchanged',
  /locked_note:\s*run Launch first – everything starts there/.test(home));

const chips = html.match(/data-step="/g) || [];
check(`AC1: total chips === 13 (found ${chips.length})`, chips.length === 13);
const checklists = html.match(/<ol class="steps"/g) || [];
check(`AC1: <ol class="steps"> count === chip count (${checklists.length} vs ${chips.length})`,
  checklists.length === chips.length);
check('AC1: no server-rendered class="dstep locked"', !html.includes('class="dstep locked"'));

// --- AC2: step ids present ---
check('AC2: id="step-launch" present', html.includes('id="step-launch"'));
check('AC2: id="step-first-launch" present', html.includes('id="step-first-launch"'));
check('AC2: id="step-pat" present', html.includes('id="step-pat"'));

// --- helper: extract a chip's block (attribute-agnostic on the id) ---
function chipBlock(id) {
  const re = new RegExp(`id="step-${id}"[^>]*>`);
  const m = re.exec(html);
  if (!m) return '';
  const start = m.index + m[0].length;
  const rest = html.slice(start);
  const nextIdx = rest.search(/id="step-/);
  const closeIdx = rest.indexOf('</div>');
  const end = nextIdx === -1 ? closeIdx : Math.min(nextIdx, closeIdx === -1 ? Infinity : closeIdx);
  return rest.slice(0, end === -1 ? undefined : end);
}

// --- helper: extract the raw home.md YAML block for one step id ---
function homeStepBlock(id) {
  const re = new RegExp(`- id: ${id}\\n([\\s\\S]*?)(?=\\n {8}- id: |\\n {4}- label: |$)`);
  const m = re.exec(home);
  return m ? m[1] : '';
}

// --- AC3: launch banner fields, in launcher order, pinned to vibe itself ---
const launchStr = homeStepBlock('launch');
const bannerFields = [
  '🚀 vibe session starting', 'project : ', 'path    : ', 'github  : ',
  'hooks   : tool-call guards + idle bell',
  'extras  : /diet · /feast · /vs · shellcheck-fixer · security-review',
];
check('AC3: all banner fields present in launch chip HTML and in vibe',
  bannerFields.every((s) => inBoth(s, launcher)));
check('AC3: path line is new (was not on old deck) and sits between project and github',
  (() => {
    const order = ['project :', 'path    :', 'github  :'];
    const idxs = order.map((s) => launchStr.indexOf(s));
    return idxs.every((i) => i !== -1) && idxs[0] < idxs[1] && idxs[1] < idxs[2];
  })());

// --- AC4 / AC4b ---
check('AC4: firewall line verbatim, pinned to init-firewall.sh',
  inBoth('Firewall verification passed - unable to reach https://example.com as expected', firewall));
check('AC4: sign-in line present, contains "your Claude subscription"',
  launchStr.includes('your Claude subscription'));
check('AC4: sign-in line is a tone line (not a bare terminal quote)',
  /tone:\s*note[\s\S]{0,80}your Claude subscription/.test(launchStr) ||
  /your Claude subscription[\s\S]{0,80}tone:\s*note/.test(launchStr));
check('AC4: a ready line exists in launch chip', /ready/i.test(launchStr));
check('AC4: launch checklist contains "short allowlist"', launchStr.includes('short allowlist'));
check('AC4b: launch checklist bullet keeps repo-discovery half, reuses PAT (not "asks once for" a fresh one)',
  launchStr.includes('reuses the PAT you set once'));
check('AC4b: launch checklist no longer contains the PAT-prompt half',
  !/asks once for a (fine-grained )?PAT/.test(launchStr));

// --- AC5: scoped negatives on the launch chip only ---
const launchChipHtml = chipBlock('launch');
const banned = ['fine-grained PAT', 'Token saved', 'Building vibe container image',
  'Only select repositories', 'sandboxed container'];
check('AC5: none of the first-launch/build strings leak into step-launch HTML block',
  banned.every((s) => !launchChipHtml.includes(s)));
check('AC5: none of those strings leak into the launch lines-map entry in home.md',
  banned.every((s) => !launchStr.includes(s)));

// --- AC6: first-launch chip carries the moved lines verbatim ---
const firstLaunchStr = homeStepBlock('first-launch');
const firstLaunchNeeded = [
  'No GitHub token found for', 'Only select repositories',
  "Token saved - you won't be asked again for this repo", 'Building vibe container image',
];
check('AC6: first-launch chip has all 4 pinned launcher strings (inBoth vs vibe, dash-normalised)',
  firstLaunchNeeded.every((s) => inBoth(s, launcher) && norm(firstLaunchStr).includes(norm(s))));
check('AC6: first-launch checklist mentions "fine-grained PAT"', firstLaunchStr.includes('fine-grained PAT'));
check('AC6: first-launch checklist mentions "sandboxed container"', firstLaunchStr.includes('sandboxed container'));

// --- AC7: pat chip ---
const patStr = homeStepBlock('pat');
check('AC7: pat chip cmd is "vibe pat"', /- id: pat\s*\n\s*cmd:\s*vibe pat/.test(home));
check('AC7: pat chip has "90 days is a good default" (inBoth)',
  inBoth('90 days is a good default', launcher) && norm(patStr).includes(norm('90 days is a good default')));
check('AC7: pat chip has "Takes effect on the next vibe launch (no rebuild needed)" (inBoth)',
  inBoth('Takes effect on the next vibe launch (no rebuild needed)', launcher) &&
  norm(patStr).includes(norm('Takes effect on the next vibe launch (no rebuild needed)')));

// --- AC8: contiguous step numbering per chip (including tone lines) ---
function stepsOf(block) {
  const nums = [];
  const re = /step:\s*(\d+)/g;
  let m;
  while ((m = re.exec(block))) nums.push(Number(m[1]));
  return nums;
}
function isContiguous(nums) {
  if (nums.length === 0) return true;
  const sorted = [...nums].sort((a, b) => a - b);
  return sorted.every((n, i) => n === i + 1) && sorted.length === Math.max(...sorted);
}
for (const id of ['launch', 'first-launch', 'pat']) {
  const block = homeStepBlock(id);
  const nums = stepsOf(block);
  check(`AC8: step: values contiguous 1..${nums.length} for chip "${id}" (found ${JSON.stringify(nums)})`,
    isContiguous(nums));
}

// --- AC12 (best-effort mechanical proxy; full holistic read is the Evaluator's job) ---
check('AC12: launch chip block does not contain a PAT-prompt line',
  !/asks once for a (fine-grained )?PAT|No GitHub token found for/.test(launchChipHtml));
check('AC12: launch chip block does not contain a build line',
  !/Building vibe container image/.test(launchChipHtml));

console.log('');
console.log(failures === 0 ? `ALL GREEN (0 failures)` : `${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
