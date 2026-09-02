import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadChips, buildPlaceholderCast, serialise } from '../../../site/demo/make-placeholder-cast.mjs';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const HOME_MD = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../../site/src/content/home.md');

test('loadChips: 13 chips, in deck order', () => {
  const chips = loadChips(readFileSync(HOME_MD, 'utf8'));
  assert.deepEqual(chips.map((c) => c.id), [
    'launch', 'first-launch', 'pat', 'vs', 'vss', 'vsss',
    'curl', 'leak', 'push', 'budget', 'learn', 'copy', 'diet',
  ]);
});

test('buildPlaceholderCast: header has placeholder:true and 96x28', () => {
  const chips = loadChips(readFileSync(HOME_MD, 'utf8'));
  const { header } = buildPlaceholderCast(chips);
  assert.equal(header.version, 2);
  assert.equal(header.width, 96);
  assert.equal(header.height, 28);
  assert.equal(header.placeholder, true);
});

test('buildPlaceholderCast: every chip gets a chip marker + one step marker per checklist step', () => {
  const chips = loadChips(readFileSync(HOME_MD, 'utf8'));
  const { events } = buildPlaceholderCast(chips);
  const markerLabels = events.filter((e) => e[1] === 'm').map((e) => e[2]);
  for (const chip of chips) {
    assert.ok(markerLabels.includes(chip.id), `missing chip marker for ${chip.id}`);
    const steps = chip.lines.filter((l) => typeof l.step === 'number').map((l) => l.step);
    for (const n of steps) {
      assert.ok(markerLabels.includes(`${chip.id}:${n}`), `missing step marker ${chip.id}:${n}`);
    }
  }
});

test('buildPlaceholderCast: times are non-decreasing', () => {
  const chips = loadChips(readFileSync(HOME_MD, 'utf8'));
  const { events } = buildPlaceholderCast(chips);
  for (let i = 1; i < events.length; i++) {
    assert.ok(events[i][0] >= events[i - 1][0], `time went backwards at index ${i}`);
  }
});

test('serialise: parses back as valid header + tuples', () => {
  const chips = loadChips(readFileSync(HOME_MD, 'utf8'));
  const { header, events } = buildPlaceholderCast(chips);
  const text = serialise(header, events);
  const lines = text.trim().split('\n');
  const parsedHeader = JSON.parse(lines[0]);
  assert.equal(parsedHeader.version, 2);
  for (const l of lines.slice(1)) {
    const tuple = JSON.parse(l);
    assert.equal(tuple.length, 3);
    assert.ok(['o', 'i', 'm', 'r'].includes(tuple[1]));
    assert.equal(typeof tuple[0], 'number');
  }
});
