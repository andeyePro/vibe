// Scratch TDD checks for site/demo/scrub.mjs — Generator-owned, not the
// Tester's site/demo/scrub.test.mjs (AC7). Run with:
//   node --test .vs/cycle-1/scratch-tests/scrub.scratch.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseCast, normaliseToV2, redactText, redactEvents,
  parseRecordSections, parseHomeChips, insertMarkers, serialiseCast,
} from '../../../site/demo/scrub.mjs';

test('parseCast: header + tuples', () => {
  const raw = '{"version":2,"width":80,"height":24}\n[0.1,"o","hi"]\n[0.2,"o","there"]\n';
  const { header, events } = parseCast(raw);
  assert.equal(header.version, 2);
  assert.equal(events.length, 2);
  assert.deepEqual(events[0], [0.1, 'o', 'hi']);
});

test('normaliseToV2: v2 in -> v2 out unchanged shape', () => {
  const { header, events } = normaliseToV2({ version: 2, width: 96, height: 28 }, [[0.1, 'o', 'x']]);
  assert.equal(header.version, 2);
  assert.equal(header.width, 96);
  assert.equal(header.height, 28);
  assert.deepEqual(events, [[0.1, 'o', 'x']]);
});

test('normaliseToV2: v3 relative times -> v2 absolute times', () => {
  const v3header = { version: 3, term: { cols: 96, rows: 28 } };
  const v3events = [
    [0.5, 'o', 'a'],
    [1.0, 'o', 'b'],
    [0.25, 'm', 'label'],
  ];
  const { header, events } = normaliseToV2(v3header, v3events);
  assert.equal(header.version, 2);
  assert.equal(header.width, 96);
  assert.equal(header.height, 28);
  assert.deepEqual(events, [
    [0.5, 'o', 'a'],
    [1.5, 'o', 'b'],
    [1.75, 'm', 'label'],
  ]);
});

test('normaliseToV2: drops unsupported v3 event codes (e.g. "x")', () => {
  const { events } = normaliseToV2({ version: 3, term: { cols: 80, rows: 24 } }, [
    [0.1, 'o', 'a'],
    [0.1, 'x', '0'],
  ]);
  assert.equal(events.length, 1);
  assert.equal(events[0][1], 'o');
});

test('normaliseToV2: rejects unknown version', () => {
  assert.throws(() => normaliseToV2({ version: 99 }, []));
});

// -------- redaction: one test per class (mirrors AC5/AC7) --------

test('redact: GitHub PAT (ghp_...)', () => {
  const out = redactText('token=ghp_<fixture-redacted> in use');
  assert.doesNotMatch(out, /ghp_[A-Za-z0-9]{6,}/);
});

test('redact: GitHub PAT (github_pat_...)', () => {
  const out = redactText('token=<fixture-token-redacted>');
  assert.doesNotMatch(out, /github_pat_[A-Za-z0-9_]{5,}/);
});

test('redact: email address', () => {
  const out = redactText('contact martin@amybo.org for help');
  assert.doesNotMatch(out, /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/i);
});

test('redact: macOS home path', () => {
  const out = redactText('cd /Users/martin/code/vibe && vibe');
  assert.doesNotMatch(out, /\/Users\/[^/ ]+/);
});

test('redact: RFC1918 IPs (all three ranges)', () => {
  for (const ip of ['10.0.1.5', '192.168.0.42', '172.16.5.9', '172.31.255.1']) {
    const out = redactText(`connect to ${ip} now`);
    assert.doesNotMatch(out, /\b(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b/, `ip ${ip} leaked`);
  }
});

test('redact: real repo slugs other than you/yourproject', () => {
  const out1 = redactText('github  : andeyePro/vibe');
  assert.ok(!out1.includes('andeyePro/'));
  const out2 = redactText('To https://github.com/Aqueum/somerepo.git');
  assert.ok(!out2.includes('Aqueum/'));
  // the placeholder slug survives untouched
  const out3 = redactText('github  : you/yourproject');
  assert.ok(out3.includes('you/yourproject'));
});

test('redact: prompt prefixes (user@host, hostname:)', () => {
  const out1 = redactText('martin@Mac-mini ~/code/vibe $ vibe');
  assert.ok(!out1.startsWith('martin@Mac-mini'));
  const out2 = redactText('pi02:~/project$ vibe');
  assert.ok(!out2.startsWith('pi02:'));
});

test('redactEvents: only touches o/i payloads, leaves r/m alone', () => {
  const events = [
    [0, 'r', '80x24'],
    [0.1, 'o', 'martin@amybo.org'],
    [0.2, 'm', 'martin@amybo.org'], // marker labels are never real emails in practice, but prove we don't touch "m"
  ];
  const out = redactEvents(events);
  assert.equal(out[0][2], '80x24');
  assert.ok(!out[1][2].includes('martin@amybo.org'));
  assert.equal(out[2][2], 'martin@amybo.org');
});

// -------- record.md / home.md parsing --------

const FIXTURE_RECORD = `
### 1. \`launch\` — Launch

Type:
\`\`\`
cd yourproject && vibe
\`\`\`
Wait for: ready prompt.

### 2. \`pat\` — Rotate the PAT

Type:
\`\`\`
vibe pat
\`\`\`
Wait for: token saved.
`;

test('parseRecordSections: extracts id + literal typed text in order', () => {
  const sections = parseRecordSections(FIXTURE_RECORD);
  assert.deepEqual(sections, [
    { id: 'launch', text: 'cd yourproject && vibe' },
    { id: 'pat', text: 'vibe pat' },
  ]);
});

const FIXTURE_HOME = `---
journey:
  groups:
    - label: G1
      steps:
        - id: launch
          cmd: vibe
          lines:
            - { cmd: true, text: "cd yourproject && vibe" }
            - { role: vibe, text: "hello", step: 1 }
            - { role: vibe, text: "world", step: 2 }
---
body
`;

test('parseHomeChips: chip order + step lines', () => {
  const chips = parseHomeChips(FIXTURE_HOME);
  assert.equal(chips.length, 1);
  assert.equal(chips[0].id, 'launch');
  assert.equal(chips[0].lines.filter((l) => l.step).length, 2);
});

// -------- marker insertion (AC4 / AC7) --------

test('insertMarkers: chip marker at first o-event containing record.md prompt; step markers at their own lines', () => {
  const events = [
    [0, 'o', '$ cd yourproject && vibe\r\n'],
    [0.5, 'o', 'vibe session starting\r\n'],
    [1.0, 'o', 'hello\r\n'],
    [1.5, 'o', 'world\r\n'],
  ];
  const recordSections = [{ id: 'launch', text: 'cd yourproject && vibe' }];
  const homeChips = [{ id: 'launch', lines: [
    { cmd: true, text: 'cd yourproject && vibe' },
    { role: 'vibe', text: 'hello', step: 1 },
    { role: 'vibe', text: 'world', step: 2 },
  ] }];
  const { events: out, markers, warnings } = insertMarkers(events, recordSections, homeChips);
  assert.deepEqual(warnings, []);
  assert.deepEqual(markers.map((m) => m.id), ['launch', 'launch:1', 'launch:2']);
  assert.equal(markers[0].time, 0);
  assert.equal(markers[1].time, 1.0);
  assert.equal(markers[2].time, 1.5);
  // matching "m" events actually landed in the cast at those times
  const mEvents = out.filter((e) => e[1] === 'm');
  assert.equal(mEvents.length, 3);
  for (const m of markers) {
    assert.ok(mEvents.some((e) => e[0] === m.time && e[2] === m.label));
  }
});

test('insertMarkers: missing step-line text falls back to chip time + 0.01*n and warns', () => {
  const events = [[0, 'o', '$ vibe pat\r\n']];
  const recordSections = [{ id: 'pat', text: 'vibe pat' }];
  const homeChips = [{ id: 'pat', lines: [
    { cmd: true, text: 'vibe pat' },
    { role: 'vibe', text: 'this line never appears in the cast', step: 1 },
  ] }];
  const { markers, warnings } = insertMarkers(events, recordSections, homeChips);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /step 1/);
  const step1 = markers.find((m) => m.id === 'pat:1');
  assert.equal(step1.time, 0.01);
});

test('insertMarkers: idempotent — running twice does not duplicate markers', () => {
  const events = [
    [0, 'o', '$ vibe\r\n'],
    [0.5, 'o', 'hello\r\n'],
  ];
  const recordSections = [{ id: 'launch', text: 'vibe' }];
  const homeChips = [{ id: 'launch', lines: [
    { cmd: true, text: 'vibe' },
    { role: 'vibe', text: 'hello', step: 1 },
  ] }];
  const once = insertMarkers(events, recordSections, homeChips);
  const twice = insertMarkers(once.events, recordSections, homeChips);
  const mCountOnce = once.events.filter((e) => e[1] === 'm').length;
  const mCountTwice = twice.events.filter((e) => e[1] === 'm').length;
  assert.equal(mCountOnce, 2);
  assert.equal(mCountTwice, 2);
  assert.deepEqual(twice.warnings, []);
});

test('serialiseCast: line 1 header, later lines are [time,code,data] tuples', () => {
  const text = serialiseCast({ version: 2, width: 10, height: 10 }, [[0, 'o', 'a'], [0.1, 'm', 'x']]);
  const lines = text.trim().split('\n');
  assert.equal(lines.length, 3);
  assert.deepEqual(JSON.parse(lines[0]), { version: 2, width: 10, height: 10 });
  assert.deepEqual(JSON.parse(lines[1]), [0, 'o', 'a']);
});
