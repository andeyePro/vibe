// Read only the explicitly supplied session transcript. No vendor auth access.
import { constants } from 'node:fs';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';

const fields = ['input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens'];
export function usageRecords(lines, { session, account, costEstimate }) {
  if (typeof session !== 'string' || !session || typeof account !== 'string' || !account || !Number.isFinite(costEstimate) || costEstimate < 0) throw new Error('session, account and explicit nonnegative per-record cost estimate are required');
  let model = null, totals = Object.fromEntries(fields.map(key => [key, 0]));
  const records = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    const event = JSON.parse(line);
    if (event.type === 'turn_context' && typeof event.payload?.model === 'string') model = event.payload.model;
    if (event.type !== 'event_msg' || event.payload?.type !== 'token_count') continue;
    const usage = event.payload.info?.total_token_usage;
    if (!usage) continue; // Missing metadata is unknown, never invented usage.
    if (!model) throw new Error('token usage has no preceding model identity');
    if (!fields.every(key => Number.isSafeInteger(usage[key]))) throw new Error('unsupported transcript usage');
    // Item 25: a regressing cumulative count is not necessarily corrupt data
    // - a context compaction legitimately resets the transcript's own
    // running counters mid-session. Aborting on one regressing line used to
    // discard every delta already computed, permanently un-importing the
    // whole session. Chosen fix: treat the regression as the start of a
    // fresh baseline (rather than skipping the line outright), so the
    // tokens already spent in the new segment are still captured instead of
    // silently undercounted; the event is still written to stderr so the
    // regression stays visible even though the import keeps going.
    if (fields.some(key => usage[key] < totals[key])) {
      process.stderr.write(`taskandi-usage: cumulative usage regressed for session ${session} (model ${model}); starting a new baseline instead of aborting the import\n`);
      totals = Object.fromEntries(fields.map(key => [key, 0]));
    }
    const delta = Object.fromEntries(fields.map(key => [key, usage[key] - totals[key]]));
    if (!fields.some(key => delta[key])) continue;
    if (delta.cached_input_tokens > delta.input_tokens) throw new Error('cached input exceeds input usage');
    const key = 'usage-' + createHash('sha256').update(JSON.stringify([session, model, fields.map(name => usage[name])])).digest('hex');
    records.push({ key, payload: { account, model, input: delta.input_tokens, output: delta.output_tokens, cache_read: delta.cached_input_tokens, cache_write: delta.cache_write_input_tokens, cost_estimate: costEstimate } });
    totals = Object.fromEntries(fields.map(key => [key, usage[key]]));
  }
  return records;
}

// Claude Code transcripts (task_065): `type: "assistant"` records carrying `message.usage`. Claude writes several records per
// message, so each distinct message.id counts once (the last record seen for it). All-zero messages (e.g. `<synthetic>`)
// are skipped; unknown usage keys are ignored; absent counts are 0.
const CLAUDE_FIELDS = [['input', 'input_tokens'], ['output', 'output_tokens'], ['cache_read', 'cache_read_input_tokens'], ['cache_write', 'cache_creation_input_tokens']];
const plain = value => !!value && typeof value === 'object' && !Array.isArray(value);
const isClaudeRecord = record => record?.type === 'assistant' && plain(record.message?.usage);
export function claudeMessages(records) {
  const byId = new Map();
  for (const record of records) {
    if (!isClaudeRecord(record)) continue;
    const { id, model, usage } = record.message; const counts = {};
    for (const [name, field] of CLAUDE_FIELDS) {
      const value = usage[field] ?? 0;
      if (!Number.isSafeInteger(value) || value < 0) throw new Error('unsupported transcript usage');
      counts[name] = value;
    }
    if (!counts.input && !counts.output && !counts.cache_read && !counts.cache_write) { byId.delete(id); continue; }
    if (typeof id !== 'string' || !id || id.length > 200 || typeof model !== 'string' || !model || model.length > 200) throw new Error('Claude usage has no message id or model');
    byId.set(id, { id, model, ...counts });
  }
  return [...byId.values()];
}
export const claudeUsageKey = (session, model, id) => 'usage-' + createHash('sha256').update(JSON.stringify([session, model, id])).digest('hex').slice(0, 16);
// One record_usage job per model per import: every not-yet-imported message summed, keyed by [session, model, last id].
// `sources` are [{file, messages}] already filtered to the messages not yet imported (see claudeSource).
export function claudeUsageRecords(sources, { session, account, costEstimate }) {
  if (typeof session !== 'string' || !session || typeof account !== 'string' || !account || !Number.isFinite(costEstimate) || costEstimate < 0) throw new Error('session, account and explicit nonnegative per-record cost estimate are required');
  const seen = new Set(); const byModel = new Map(); let count = 0;
  for (const { messages } of sources) {
    for (const message of messages) {
      if (seen.has(message.id)) continue; seen.add(message.id); count++;
      const total = byModel.get(message.model) ?? { input: 0, output: 0, cache_read: 0, cache_write: 0, last: null };
      for (const [name] of CLAUDE_FIELDS) total[name] += message[name];
      total.last = message.id; byModel.set(message.model, total);
    }
  }
  const records = [...byModel].map(([model, total]) => ({
    key: claudeUsageKey(session, model, total.last),
    payload: { account, model, input: total.input, output: total.output, cache_read: total.cache_read, cache_write: total.cache_write, cost_estimate: costEstimate },
  }));
  return { records, messages: count };
}

// The usage ledger (AC33), per session and transcript file: {offset, prefixLen, prefixSha, tailIds}. offset is the byte
// length already imported (transcripts only grow); tailIds are the counted message ids in the last 64 KiB before it, so
// a message whose records straddle the offset is not counted twice. A file that shrank, or whose first prefixLen (at
// most 4 KiB) bytes changed, is re-read from 0 (as is a file with a pre-cycle-3 id-list entry): a message counts as
// imported when it is at or before the last message whose id the old entry names, or, per model, at or before the
// last message whose one-message usage key a live job or tombstone already holds (each import keys its job by the
// last message per model, so that message marks the end of what was imported for the model).
const PREFIX_BYTES = 4096, TAIL_BYTES = 64 * 1024;
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const plainEntry = entry => plain(entry) && Number.isSafeInteger(entry.offset) && entry.offset >= 0 && Number.isSafeInteger(entry.prefixLen) && entry.prefixLen >= 0 && entry.prefixLen <= entry.offset && typeof entry.prefixSha === 'string' && Array.isArray(entry.tailIds);
export function ledgerEntry(buffer, records) {
  const offset = buffer.length; const prefixLen = Math.min(PREFIX_BYTES, offset);
  const tail = new Set();
  for (const { end, record } of records) {
    if (end < offset - TAIL_BYTES || !isClaudeRecord(record) || typeof record.message.id !== 'string') continue;
    if (claudeMessages([record]).length) tail.add(record.message.id);
  }
  return { offset, prefixLen, prefixSha: sha256(buffer.subarray(0, prefixLen)), tailIds: [...tail].sort() };
}
// The not-yet-imported messages of one file, given its ledger entry; `knownKeys()` lists live and tombstoned usage keys.
export async function claudeSource(file, buffer, records, entry, { session, knownKeys }) {
  if (plainEntry(entry) && buffer.length >= entry.offset && sha256(buffer.subarray(0, entry.prefixLen)) === entry.prefixSha) {
    const tail = new Set(entry.tailIds);
    const messages = claudeMessages(records.filter(item => item.start >= entry.offset).map(item => item.record)).filter(message => !tail.has(message.id));
    return { file, messages, entry: ledgerEntry(buffer, records), reread: false };
  }
  const all = claudeMessages(records.map(item => item.record));
  const named = new Set(Array.isArray(entry) ? entry : plainEntry(entry) ? entry.tailIds : []);
  // A first import (no entry) has nothing to deduplicate against.
  const keys = new Set(entry === undefined || entry === null ? [] : await knownKeys());
  let upTo = -1; const perModel = new Map();
  all.forEach((message, index) => {
    if (named.has(message.id)) upTo = index;
    if (keys.has(claudeUsageKey(session, message.model, message.id))) perModel.set(message.model, index);
  });
  const messages = all.filter((message, index) => index > upTo && index > (perModel.get(message.model) ?? -1));
  return { file, messages, entry: ledgerEntry(buffer, records), reread: true };
}

// One transcript snapshot: an owned regular file (never through a symlink) of at most 128 MiB, cut at its last newline
// (the final unterminated record may still be being written). Every other line must parse.
async function readTranscriptBytes(file) {
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.uid !== process.getuid() || stat.size > 128 * 1024 * 1024) throw new Error('transcript must be an owned regular file of at most 128 MiB');
    // Snapshot the known length: a live transcript may grow during a boundary.
    const buffer = Buffer.alloc(stat.size); let offset = 0;
    while (offset < buffer.length) {
      const { bytesRead } = await handle.read(buffer, offset, buffer.length - offset, offset);
      if (!bytesRead) break;
      offset += bytesRead;
    }
    const data = buffer.subarray(0, offset);
    return data.subarray(0, data.lastIndexOf(0x0a) + 1);
  } finally { await handle.close(); }
}
async function readTranscript(file) { return (await readTranscriptBytes(file)).toString('utf8').split('\n'); }
// Every complete line of a snapshot with its byte range [start, end) (end excludes the newline); blank lines skipped.
function parseRecords(buffer) {
  const out = [];
  for (let start = 0; start < buffer.length;) {
    const newline = buffer.indexOf(0x0a, start); const end = newline < 0 ? buffer.length : newline;
    const line = buffer.subarray(start, end).toString('utf8');
    if (line.trim()) out.push({ start, end, record: JSON.parse(line) });
    start = end + 1;
  }
  return out;
}
// A Claude session's subagent transcripts: every *.jsonl in <transcript without .jsonl>/subagents/, in name order.
async function subagentFiles(file) {
  if (!file.endsWith('.jsonl')) return [];
  const dir = join(file.slice(0, -'.jsonl'.length), 'subagents');
  let st; try { st = await fs.lstat(dir); } catch (error) { if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return []; throw error; }
  if (!st.isDirectory() || st.isSymbolicLink()) throw new Error('the subagents directory must be a real directory');
  return (await fs.readdir(dir)).filter(name => name.endsWith('.jsonl')).sort().map(name => join(dir, name));
}

export async function enqueueTranscriptUsage(client, file, options) {
  // Under a descriptor binding the whole import is one pass: one config load and one outbox lock (enqueueBatch resolves
  // the task itself). Otherwise resolveTask checks the task first, as before.
  const batch = typeof client.descriptor === 'function' && client.descriptor() && typeof client.enqueueBatch === 'function';
  if (!batch && options.task !== undefined) options = { ...options, task: await client.resolveTask(options.task) };
  const buffer = await readTranscriptBytes(file);
  const parsed = parseRecords(buffer); const main = parsed.map(item => item.record);
  const claude = main.some(isClaudeRecord) || (!main.some(record => record?.type === 'turn_context' || record?.type === 'event_msg') && (await subagentFiles(file)).length > 0);
  if (claude) return enqueueClaudeUsage(client, file, { buffer, records: parsed }, options, batch);
  const records = usageRecords(buffer.toString('utf8').split('\n'), options);
  let enqueued = 0, deduplicated = 0;
  if (batch) {
    // With nothing to enqueue, --task is still checked (one config load, one lock either way).
    if (!records.length && options.task !== undefined) await client.resolveTask(options.task);
    const results = records.length ? await client.enqueueBatch('record_usage', records.map(record => ({ key: record.key, input: record.payload })), { task: options.task }) : [];
    for (const result of results) { if (result.enqueued) enqueued++; else deduplicated++; }
    return { enqueued, deduplicated, source: 'explicit-session-transcript', usageAvailable: records.length > 0 };
  }
  for (const record of records) {
    const result = await client.enqueue('record_usage', record.key, options.task === undefined ? record.payload : { ...record.payload, task: options.task });
    if (result.enqueued) enqueued++;
    else deduplicated++;
  }
  return { enqueued, deduplicated, source: 'explicit-session-transcript', usageAvailable: records.length > 0 };
}

// Claude: the main transcript plus its subagents; only messages past each file's ledger entry count, and the ledger
// update lands in the same outbox write as the jobs (a racing import is refused, never double-counted).
async function enqueueClaudeUsage(client, file, main, options, batch) {
  const files = [{ file: resolve(file), ...main }];
  for (const sub of await subagentFiles(file)) { const buffer = await readTranscriptBytes(sub); files.push({ file: resolve(sub), buffer, records: parseRecords(buffer) }); }
  const imported = typeof client.usageImported === 'function' ? await client.usageImported(options.session) : {};
  let keys = null;
  const knownKeys = async () => (keys ??= typeof client.usageKeys === 'function' ? await client.usageKeys() : []);
  const sources = [];
  for (const item of files) sources.push(await claudeSource(item.file, item.buffer, item.records, imported[item.file], { session: options.session, knownKeys }));
  const { records, messages } = claudeUsageRecords(sources, options);
  if (!records.length) {
    if (batch && options.task !== undefined) await client.resolveTask(options.task);
    return { enqueued: 0, deduplicated: 0, source: 'explicit-session-transcript', usageAvailable: false, messages: 0 };
  }
  const entries = Object.fromEntries(sources.map(source => [source.file, { before: imported[source.file], after: source.entry }]));
  const items = records.map(record => ({ key: record.key, input: !batch && options.task !== undefined ? { ...record.payload, task: options.task } : record.payload }));
  const markOption = typeof client.importMarker === 'function' ? { mark: client.importMarker(options.session, entries) } : {};
  const results = await client.enqueueBatch('record_usage', items, { ...(batch ? { task: options.task } : {}), ...markOption });
  let enqueued = 0, deduplicated = 0;
  for (const result of results) { if (result.enqueued) enqueued++; else deduplicated++; }
  return { enqueued, deduplicated, source: 'explicit-session-transcript', usageAvailable: true, messages };
}
