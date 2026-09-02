#!/usr/bin/env node
// make-placeholder-cast.mjs — synthesises a v2 asciicast straight from
// site/src/content/home.md's own `journey` deck lines, so the demo pane has
// something clearly-labelled to play before Martin records the real thing
// (site/demo/record.md). Per chip, in deck order: the chip's own "cmd:true"
// line is echoed at a "$ " prompt with an "m" chip marker at its own event,
// then every remaining line is emitted as its own "o" event, with an "m"
// step marker `<chip>:<n>` on any line carrying `step: n`.
//
// Usage:
//   node site/demo/make-placeholder-cast.mjs [--out FILE]
// With no --out, writes the cast to stdout (so it can be piped straight
// into scrub.mjs, which is idempotent on an already-clean cast like this
// one and will just confirm the markers it finds rather than duplicate
// them).

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import yaml from 'js-yaml';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = path.resolve(HERE, '..');
const HOME_MD = path.join(SITE_ROOT, 'src/content/home.md');

const WIDTH = 96;
const HEIGHT = 28;
const TITLE = 'vibe demo (placeholder — replace with a real recording, see site/demo/record.md)';

// Fixed per-event gap: enough for a marker-driven seek to land somewhere
// sane, short enough that the whole placeholder cast stays brief.
const GAP = 0.6;

export function loadChips(homeMdText) {
  const m = homeMdText.match(/^---\n([\s\S]*?)\n---/);
  if (!m) throw new Error('home.md: no frontmatter found');
  const fm = yaml.load(m[1]);
  const chips = [];
  for (const g of fm.journey.groups) {
    for (const s of g.steps) {
      chips.push({ id: s.id, lines: s.lines || [] });
    }
  }
  return chips;
}

// Builds the full [header, events] pair for the placeholder cast.
export function buildPlaceholderCast(chips) {
  const events = [];
  let t = 0;

  for (const chip of chips) {
    const [cmdLine, ...rest] = chip.lines;
    if (!cmdLine) continue;

    // the typed command, echoed at a shell-style prompt
    events.push([t, 'o', `$ ${cmdLine.text}\r\n`]);
    events.push([t, 'm', chip.id]);
    t = Math.round((t + GAP) * 1e6) / 1e6;

    for (const line of rest) {
      events.push([t, 'o', `${line.text}\r\n`]);
      if (typeof line.step === 'number') {
        events.push([t, 'm', `${chip.id}:${line.step}`]);
      }
      t = Math.round((t + GAP) * 1e6) / 1e6;
    }
  }

  const header = { version: 2, width: WIDTH, height: HEIGHT, placeholder: true, title: TITLE };
  return { header, events };
}

export function serialise(header, events) {
  const lines = [JSON.stringify(header)];
  for (const e of events) lines.push(JSON.stringify(e));
  return lines.join('\n') + '\n';
}

function usage() {
  return [
    'Usage: node site/demo/make-placeholder-cast.mjs [--out FILE]',
    '',
    'Synthesises a placeholder asciicast v2 recording from the journey deck',
    "in site/src/content/home.md. Writes to stdout by default; pipe or",
    '--out into site/demo/scrub.mjs to produce the shipped',
    'site/public/demo/vibe.cast + markers.json.',
  ].join('\n');
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(usage());
    process.exit(0);
  }
  const outIdx = argv.indexOf('--out');
  const outFile = outIdx !== -1 ? argv[outIdx + 1] : null;

  const homeMdText = readFileSync(HOME_MD, 'utf8');
  const chips = loadChips(homeMdText);
  const { header, events } = buildPlaceholderCast(chips);
  const text = serialise(header, events);

  if (outFile) {
    mkdirSync(path.dirname(outFile), { recursive: true });
    writeFileSync(outFile, text);
    console.error(`wrote ${outFile} (${events.length} events, ${chips.length} chips)`);
  } else {
    process.stdout.write(text);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
