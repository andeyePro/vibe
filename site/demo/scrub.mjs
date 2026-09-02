#!/usr/bin/env node
// scrub.mjs — normalise, redact and mark up an asciinema recording for the
// vibe.andeye.com demo pane. Reads an asciicast v2 OR v3 file, produces a v2
// cast (site/public/demo/vibe.cast) plus a markers file
// (site/public/demo/markers.json) that CastPlayer.astro passes straight to
// AsciinemaPlayer.create()'s `markers` option.
//
// Usage:
//   node site/demo/scrub.mjs <in.cast> [--out FILE] [--markers FILE] [--record FILE]
//
// Defaults: --out site/public/demo/vibe.cast, --markers site/public/demo/markers.json,
// --record site/demo/record.md (the recording script — see there for the
// exact text each marker is matched against).
//
// All the interesting logic is exported so it can be unit-tested (see
// site/demo/scrub.test.mjs) without shelling out.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import yaml from 'js-yaml';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = path.resolve(HERE, '..');

export const DEFAULT_OUT = path.join(SITE_ROOT, 'public/demo/vibe.cast');
export const DEFAULT_MARKERS = path.join(SITE_ROOT, 'public/demo/markers.json');
export const DEFAULT_RECORD = path.join(HERE, 'record.md');
export const DEFAULT_HOME = path.join(SITE_ROOT, 'src/content/home.md');

// ---------------------------------------------------------------------------
// Cast parsing / v3 -> v2 normalisation
// ---------------------------------------------------------------------------

// Real recordings and machine-generated ones alike are newline-delimited
// JSON: header line, then one [time, code, data] tuple per line. Blank
// trailing lines are tolerated.
export function parseCast(raw) {
  const lines = raw.split('\n').filter((l) => l.trim().length > 0);
  if (lines.length === 0) throw new Error('empty cast file');
  const header = JSON.parse(lines[0]);
  const events = lines.slice(1).map((l) => JSON.parse(l));
  return { header, events };
}

// Event codes the demo pane's player actually needs (AC2). asciicast v3 can
// carry an "x" (exit code) event; we drop anything outside this set rather
// than propagate a code the v2 player/spec doesn't expect.
const KEEP_CODES = new Set(['o', 'i', 'm', 'r']);

function round(n) {
  // asciicast times are seconds with fractional precision; keep enough
  // precision for sub-frame markers without accumulating float noise.
  return Math.round(n * 1e6) / 1e6;
}

// Normalise a parsed {header, events} to asciicast v2 shape. v2 in, v2 out
// (a copy). v3 in: header.term.{cols,rows} -> flat width/height, and event
// times are deltas-from-previous -> absolute-from-start (v2's convention).
export function normaliseToV2(header, events) {
  if (header.version === 2) {
    const newHeader = { version: 2, width: header.width, height: header.height };
    if (header.timestamp !== undefined) newHeader.timestamp = header.timestamp;
    if (header.env !== undefined) newHeader.env = header.env;
    if (header.placeholder) newHeader.placeholder = true;
    if (header.title !== undefined) newHeader.title = header.title;
    const newEvents = events
      .filter((e) => KEEP_CODES.has(e[1]))
      .map((e) => [round(e[0]), e[1], e[2]]);
    return { header: newHeader, events: newEvents };
  }
  if (header.version === 3) {
    const width = header.term?.cols;
    const height = header.term?.rows;
    let t = 0;
    const newEvents = [];
    for (const e of events) {
      t += e[0];
      if (!KEEP_CODES.has(e[1])) continue;
      newEvents.push([round(t), e[1], e[2]]);
    }
    const newHeader = { version: 2, width, height };
    if (header.timestamp !== undefined) newHeader.timestamp = header.timestamp;
    if (header.env !== undefined) newHeader.env = header.env;
    if (header.placeholder) newHeader.placeholder = true;
    if (header.title !== undefined) newHeader.title = header.title;
    return { header: newHeader, events: newEvents };
  }
  throw new Error(`unsupported cast version: ${header.version}`);
}

// ---------------------------------------------------------------------------
// Redaction (AC5)
// ---------------------------------------------------------------------------

// Known real org names that must never survive into the shipped cast. The
// generic github-slug patterns below catch the common *contexts* the deck's
// own transcript uses (a launcher banner field, a github.com URL); this
// list is the belt-and-braces catch-all site-check.mjs actually greps for.
const KNOWN_REAL_ORGS = ['andeyePro', 'Aqueum'];

const REDACTIONS = [
  // GitHub PATs — the replacement must not itself match the detecting
  // pattern (a redaction that still reads as "ghp_<alnum>{6,}" is no
  // redaction at all), so these deliberately don't keep the token prefix.
  [/ghp_[A-Za-z0-9]{6,}/g, '[redacted-token]'],
  [/github_pat_[A-Za-z0-9_]*/g, '[redacted-token]'],
  // email addresses — same reasoning: no "@...\.tld" shape left behind.
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/gi, '[redacted-email]'],
  // macOS home paths
  [/\/Users\/[^/ ]+/g, '~'],
  // RFC1918 / link-local IPs
  // 203.0.113.0/24 is RFC 5737 TEST-NET-3 — documentation-only, never a
  // real private address, so it can't itself re-trigger this same rule.
  [/\b(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b/g, '203.0.113.1'],
  // shell prompt prefixes: user@host at line start, or hostname: at line start
  [/^\S+@\S+(?=[:$#\s])/gm, 'you@yourmac'],
  [/^[A-Za-z0-9._-]+:(?=[~/])/gm, 'yourmac:'],
];

function redactRepoSlugs(text) {
  let out = text;
  for (const org of KNOWN_REAL_ORGS) {
    out = out.replace(new RegExp(`\\b${org}\\/[\\w.-]+`, 'g'), 'you/yourproject');
  }
  // "github.com/<owner>/<repo>" URL context (push output, PAT-setup URL)
  out = out.replace(/github\.com\/([\w.-]+)\/([\w.-]+)/g, (m, o, r) =>
    o === 'you' && r === 'yourproject' ? m : 'github.com/you/yourproject');
  // "github  : <owner>/<repo>" launcher banner context
  out = out.replace(/(github\s*:\s*)([\w.-]+)\/([\w.-]+)/g, (m, pre, o, r) =>
    o === 'you' && r === 'yourproject' ? m : `${pre}you/yourproject`);
  return out;
}

// Redacts a single string payload. Exported so scrub.test.mjs can target
// one redaction class at a time without round-tripping a whole cast.
export function redactText(text) {
  let out = redactRepoSlugs(text);
  for (const [re, replacement] of REDACTIONS) out = out.replace(re, replacement);
  return out;
}

// Redacts every "o" (and "i", for good measure — it's still terminal I/O)
// payload in an event list. "r" (resize, "COLSxROWS") and "m" (our own
// markers) are left alone.
export function redactEvents(events) {
  return events.map((e) => {
    const [time, code, data] = e;
    if ((code === 'o' || code === 'i') && typeof data === 'string') {
      return [time, code, redactText(data)];
    }
    return e;
  });
}

// ---------------------------------------------------------------------------
// record.md parsing — extracts, per chip id, the literal text the recording
// procedure says to type. Section format (see record.md):
//   ### N. `id` — Label
//   Type ...:
//   ```
//   literal text
//   ```
// The first fenced code block after a heading is taken as that section's
// prompt text (first non-empty line, trimmed — sections are one-liners).
// ---------------------------------------------------------------------------
export function parseRecordSections(md) {
  const sections = [];
  const headingRe = /^###\s+\d+\.\s+`([a-z0-9-]+)`/gm;
  const headings = [...md.matchAll(headingRe)];
  for (let i = 0; i < headings.length; i++) {
    const id = headings[i][1];
    const start = headings[i].index;
    const end = i + 1 < headings.length ? headings[i + 1].index : md.length;
    const body = md.slice(start, end);
    const fence = body.match(/```[^\n]*\n([\s\S]*?)```/);
    if (!fence) continue;
    const firstLine = fence[1].split('\n').map((l) => l.trim()).find((l) => l.length > 0);
    if (firstLine) sections.push({ id, text: firstLine });
  }
  return sections;
}

// ---------------------------------------------------------------------------
// home.md parsing — the deck's own chip order and, per chip, the lines that
// carry `step: n`, in order.
// ---------------------------------------------------------------------------
export function parseHomeChips(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---/);
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

// ---------------------------------------------------------------------------
// Marker insertion (AC4 / AC7)
// ---------------------------------------------------------------------------

// Finds the first "o" event, at or after `fromIndex`, whose payload
// contains `text` as a substring. Returns the event index, or -1.
function findEventContaining(events, text, fromIndex = 0) {
  for (let i = fromIndex; i < events.length; i++) {
    const [, code, data] = events[i];
    if (code === 'o' && typeof data === 'string' && data.includes(text)) return i;
  }
  return -1;
}

// Returns true if an "m" event with this exact label already exists —
// scrub.mjs must be idempotent on an already-marked (placeholder) cast.
function markerExists(events, label) {
  return events.some(([, code, data]) => code === 'm' && data === label);
}

// insertMarkers: given already-normalised+redacted v2 events, the chip
// order + prompt text (from record.md) and each chip's step lines (from
// home.md), inserts "m" events for every chip and step marker that doesn't
// already exist, and returns { events, markers } where markers is the
// [{id, time, label}] array for markers.json (chip markers in deck order,
// each immediately followed by its own step markers).
export function insertMarkers(events, recordSections, homeChips) {
  const out = events.slice();
  const markers = [];
  const warnings = [];

  const bySection = new Map(recordSections.map((s) => [s.id, s.text]));

  // cursor: chip prompts are matched in deck order, each search starting
  // after the previous chip's marker, so an identical prompt typed twice in a
  // real recording (launch and first-launch both type `cd yourproject && vibe`)
  // lands on its own occurrence instead of both collapsing onto the first.
  let cursor = 0;
  for (const chip of homeChips) {
    const promptText = bySection.get(chip.id);
    let chipTime;
    let chipEventIdx = -1;

    if (markerExists(out, chip.id)) {
      const idx = out.findIndex(([, code, data]) => code === 'm' && data === chip.id);
      chipTime = out[idx][0];
      chipEventIdx = idx;
    } else if (promptText) {
      chipEventIdx = findEventContaining(out, promptText, cursor);
      if (chipEventIdx === -1) {
        warnings.push(`chip "${chip.id}": prompt text not found in cast output — skipped chip marker`);
      } else {
        chipTime = out[chipEventIdx][0];
        out.splice(chipEventIdx + 1, 0, [chipTime, 'm', chip.id]);
        chipEventIdx += 1; // point at the marker we just inserted
      }
    } else {
      warnings.push(`chip "${chip.id}": no record.md section found — skipped chip marker`);
    }

    if (chipTime !== undefined) markers.push({ id: chip.id, time: chipTime, label: chip.id });
    if (chipEventIdx >= 0) cursor = chipEventIdx + 1;

    // step markers: search forward from the chip marker (or from the start
    // of the cast, if the chip marker itself is missing) so identical step
    // text in an earlier chip can't be matched by mistake.
    const searchFrom = chipEventIdx >= 0 ? chipEventIdx : 0;
    const stepLines = chip.lines.filter((l) => l && typeof l.step === 'number');
    for (const line of stepLines) {
      const n = line.step;
      const label = `${chip.id}:${n}`;
      if (markerExists(out, label)) {
        const idx = out.findIndex(([, code, data]) => code === 'm' && data === label);
        markers.push({ id: label, time: out[idx][0], label });
        continue;
      }
      const idx = findEventContaining(out, line.text, searchFrom);
      if (idx === -1) {
        const fallbackTime = round((chipTime ?? 0) + 0.01 * n);
        warnings.push(`chip "${chip.id}" step ${n}: line text not found in cast output — placed at chip time + ${0.01 * n}s`);
        out.push([fallbackTime, 'm', label]);
        markers.push({ id: label, time: fallbackTime, label });
      } else {
        const t = out[idx][0];
        out.splice(idx + 1, 0, [t, 'm', label]);
        markers.push({ id: label, time: t, label });
      }
    }
  }

  out.sort((a, b) => a[0] - b[0]);
  markers.sort((a, b) => a.time - b.time);
  return { events: out, markers, warnings };
}

// ---------------------------------------------------------------------------
// Serialisation
// ---------------------------------------------------------------------------
export function serialiseCast(header, events) {
  const lines = [JSON.stringify(header)];
  for (const e of events) lines.push(JSON.stringify(e));
  return lines.join('\n') + '\n';
}

// ---------------------------------------------------------------------------
// End-to-end pipeline, used by both the CLI and make-placeholder-cast.mjs.
// ---------------------------------------------------------------------------
export function scrub(rawCastText, { recordMd, homeMd }) {
  const parsed = parseCast(rawCastText);
  const { header, events: v2Events } = normaliseToV2(parsed.header, parsed.events);
  const redacted = redactEvents(v2Events);
  const recordSections = parseRecordSections(recordMd);
  const homeChips = parseHomeChips(homeMd);
  const { events: finalEvents, markers, warnings } = insertMarkers(redacted, recordSections, homeChips);
  return { header, events: finalEvents, markers, warnings };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------
function usage() {
  return [
    'Usage: node site/demo/scrub.mjs <in.cast> [--out FILE] [--markers FILE] [--record FILE]',
    '',
    'Reads an asciicast v2 or v3 recording, normalises it to v2, redacts',
    'secrets/PII, and inserts "m" markers by matching site/demo/record.md\'s',
    'per-chip prompts and site/src/content/home.md\'s per-line step markers',
    'against the recorded output.',
    '',
    'Options:',
    `  --out FILE      cast output path (default ${path.relative(process.cwd(), DEFAULT_OUT)})`,
    `  --markers FILE  markers.json output path (default ${path.relative(process.cwd(), DEFAULT_MARKERS)})`,
    `  --record FILE   record.md to match prompts against (default ${path.relative(process.cwd(), DEFAULT_RECORD)})`,
    '  --help          show this message',
  ].join('\n');
}

function parseArgs(argv) {
  const args = { out: DEFAULT_OUT, markers: DEFAULT_MARKERS, record: DEFAULT_RECORD, input: null };
  const rest = [...argv];
  while (rest.length) {
    const a = rest.shift();
    if (a === '--help' || a === '-h') { args.help = true; continue; }
    if (a === '--out') { args.out = rest.shift(); continue; }
    if (a === '--markers') { args.markers = rest.shift(); continue; }
    if (a === '--record') { args.record = rest.shift(); continue; }
    if (!args.input) { args.input = a; continue; }
  }
  return args;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    process.exit(0);
  }
  if (!args.input) {
    console.error(usage());
    process.exit(1);
  }
  if (!existsSync(args.input)) {
    console.error(`input cast not found: ${args.input}`);
    process.exit(1);
  }

  const rawCastText = readFileSync(args.input, 'utf8');
  const recordMd = readFileSync(args.record, 'utf8');
  const homeMd = readFileSync(DEFAULT_HOME, 'utf8');

  const { header, events, markers, warnings } = scrub(rawCastText, { recordMd, homeMd });

  for (const w of warnings) console.warn(`warn: ${w}`);

  mkdirSync(path.dirname(args.out), { recursive: true });
  mkdirSync(path.dirname(args.markers), { recursive: true });
  writeFileSync(args.out, serialiseCast(header, events));
  writeFileSync(args.markers, JSON.stringify(markers, null, 2) + '\n');

  console.log(`wrote ${args.out} (${events.length} events)`);
  console.log(`wrote ${args.markers} (${markers.length} markers)`);
  if (header.placeholder) {
    console.log('note: input cast is a placeholder — this is expected until a real recording lands.');
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
