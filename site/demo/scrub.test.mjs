// scrub.test.mjs — unit tests for site/demo/scrub.mjs (AC7). Run with:
//   node --test site/demo/scrub.test.mjs
// Imports scrub.mjs's exported functions directly rather than shelling out,
// so each redaction class, the v3->v2 normalisation, and marker insertion
// can be tested against small in-memory fixtures.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  redactText,
  normaliseToV2,
  parseRecordSections,
  insertMarkers,
} from './scrub.mjs';

// ---------------------------------------------------------------------------
// AC5 redaction classes — one test per pattern in site-check.mjs's AC5_PATTERNS
// plus the known-real-repo-slug redaction AC5 also requires.
// ---------------------------------------------------------------------------

test('redacts a classic GitHub PAT (ghp_ prefix)', () => {
  const input = 'export GITHUB_TOKEN=ghp_ABCDEFGHIJ0123456789';
  const output = redactText(input);
  assert.ok(!/ghp_[A-Za-z0-9]{6,}/.test(output), `still matches ghp_ pattern: ${output}`);
});

test('redacts a fine-grained GitHub PAT (github_pat_ prefix)', () => {
  const input = 'token: github_pat_11ABCDEFG0123456789abcdefghij';
  const output = redactText(input);
  assert.ok(!/github_pat_/.test(output), `still matches github_pat_ pattern: ${output}`);
});

test('redacts email addresses', () => {
  const input = 'ping someone.dev+test@example.com for access';
  const output = redactText(input);
  assert.ok(
    !/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/i.test(output),
    `still matches email pattern: ${output}`,
  );
});

test('redacts macOS home paths', () => {
  const input = 'wrote config to /Users/alice/code/project/config.json';
  const output = redactText(input);
  assert.ok(!/\/Users\/[^/ ]+/.test(output), `still matches home-path pattern: ${output}`);
});

test('redacts RFC1918 / link-local private IPs', () => {
  const input = 'reachable at 192.168.1.42 and 10.0.0.5 and 172.20.3.9';
  const output = redactText(input);
  const ipPattern = /\b(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b/;
  assert.ok(!ipPattern.test(output), `still matches private-IP pattern: ${output}`);
});

test('redacts known real repo slugs (andeyePro/ and Aqueum/) to you/yourproject', () => {
  const input = 'cloned andeyePro/vibe and also touched Aqueum/legacy-app today';
  const output = redactText(input);
  assert.ok(!output.includes('andeyePro/'), `still contains andeyePro/: ${output}`);
  assert.ok(!output.includes('Aqueum/'), `still contains Aqueum/: ${output}`);
  assert.ok(output.includes('you/yourproject'), `redaction did not substitute you/yourproject: ${output}`);
});

// ---------------------------------------------------------------------------
// v3 -> v2 normalisation
// ---------------------------------------------------------------------------

test('normalises asciicast v3 (delta times, term.cols/rows) to v2 (absolute times, flat width/height)', () => {
  const v3Header = { version: 3, term: { cols: 96, rows: 28 } };
  const v3Events = [
    [0, 'o', 'hello'],
    [1.5, 'o', 'world'],
    [0.25, 'x', 0], // v3 exit-code event — not in KEEP_CODES, must be dropped
  ];
  const { header, events } = normaliseToV2(v3Header, v3Events);
  assert.strictEqual(header.version, 2);
  assert.strictEqual(header.width, 96);
  assert.strictEqual(header.height, 28);
  assert.deepStrictEqual(events, [
    [0, 'o', 'hello'],
    [1.5, 'o', 'world'],
  ]);
});

test('normalises asciicast v2 input to a v2 copy unchanged in shape', () => {
  const v2Header = { version: 2, width: 80, height: 24 };
  const v2Events = [
    [0, 'o', 'a'],
    [1, 'i', 'b'],
    [2, 'x', 'dropped'],
  ];
  const { header, events } = normaliseToV2(v2Header, v2Events);
  assert.strictEqual(header.version, 2);
  assert.strictEqual(header.width, 80);
  assert.strictEqual(header.height, 24);
  assert.deepStrictEqual(events, [
    [0, 'o', 'a'],
    [1, 'i', 'b'],
  ]);
});

// ---------------------------------------------------------------------------
// Marker insertion (AC4 / AC7): a record.md fixture's prompt text should
// produce an "m" event at the first "o" event containing that text.
// ---------------------------------------------------------------------------

test('inserts a chip "m" marker at the first "o" event containing the record.md prompt text', () => {
  const recordMd = [
    '### 1. `launch` — Launch',
    '',
    'Type:',
    '```',
    'cd yourproject && vibe',
    '```',
    'Wait for: the ready prompt.',
  ].join('\n');
  const recordSections = parseRecordSections(recordMd);
  assert.deepStrictEqual(recordSections, [{ id: 'launch', text: 'cd yourproject && vibe' }]);

  const homeChips = [{ id: 'launch', lines: [{ text: 'ready to go', step: 1 }] }];
  const events = [
    [0, 'o', 'noise before\r\n'],
    [1, 'o', '$ cd yourproject && vibe\r\n'],
    [2, 'o', 'ready to go\r\n'],
  ];

  const { events: outEvents, markers } = insertMarkers(events, recordSections, homeChips);

  const chipMarker = markers.find((m) => m.id === 'launch');
  assert.ok(chipMarker, 'expected a chip marker for "launch"');
  assert.strictEqual(chipMarker.time, 1, 'chip marker should land at the event containing the prompt text');
  assert.strictEqual(chipMarker.label, 'launch');
  assert.ok(
    outEvents.some((e) => e[1] === 'm' && e[0] === 1 && e[2] === 'launch'),
    'expected an "m" event inserted at time 1 with label "launch"',
  );

  const stepMarker = markers.find((m) => m.id === 'launch:1');
  assert.ok(stepMarker, 'expected a step marker for "launch:1"');
  assert.strictEqual(stepMarker.time, 2, 'step marker should land at the event containing the step line text');
  assert.ok(
    outEvents.some((e) => e[1] === 'm' && e[0] === 2 && e[2] === 'launch:1'),
    'expected an "m" event inserted at time 2 with label "launch:1"',
  );
});

test('a prompt typed twice (launch, then first-launch) gets two chip markers on two occurrences', () => {
  const recordMd = [
    '### 1. `launch` — Launch', '', 'Type:', '```', 'cd yourproject && vibe', '```', 'Wait for: ready.',
    '', '### 2. `first-launch` — First launch', '', 'Type:', '```', 'cd yourproject && vibe', '```', 'Wait for: Token saved.',
  ].join('\n');
  const recordSections = parseRecordSections(recordMd);
  const homeChips = [
    { id: 'launch', lines: [{ text: 'ready', step: 1 }] },
    { id: 'first-launch', lines: [{ text: 'Token saved', step: 1 }] },
  ];
  const events = [
    [1, 'o', '$ cd yourproject && vibe\r\n'],
    [2, 'o', 'ready\r\n'],
    [5, 'o', '$ cd yourproject && vibe\r\n'],
    [6, 'o', 'Token saved\r\n'],
  ];
  const { markers } = insertMarkers(events, recordSections, homeChips);
  const launch = markers.find((m) => m.id === 'launch');
  const first = markers.find((m) => m.id === 'first-launch');
  assert.strictEqual(launch.time, 1);
  assert.strictEqual(first.time, 5, 'second chip must land on the SECOND occurrence, not collapse onto the first');
  assert.strictEqual(markers.find((m) => m.id === 'first-launch:1').time, 6);
});
