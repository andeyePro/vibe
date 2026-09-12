// Read only the explicitly supplied session transcript. No vendor auth access.
import { constants } from 'node:fs';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';

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
    for (const key of fields) if (!Number.isSafeInteger(usage[key]) || usage[key] < totals[key]) throw new Error('unsupported or regressing transcript usage; reconcile instead of reposting');
    const delta = Object.fromEntries(fields.map(key => [key, usage[key] - totals[key]]));
    if (!fields.some(key => delta[key])) continue;
    if (delta.cached_input_tokens > delta.input_tokens) throw new Error('cached input exceeds input usage');
    const key = 'usage-' + createHash('sha256').update(JSON.stringify([session, model, fields.map(name => usage[name])])).digest('hex');
    records.push({ key, payload: { account, model, input: delta.input_tokens, output: delta.output_tokens, cache_read: delta.cached_input_tokens, cache_write: delta.cache_write_input_tokens, cost_estimate: costEstimate } });
    totals = Object.fromEntries(fields.map(key => [key, usage[key]]));
  }
  return records;
}

export async function enqueueTranscriptUsage(client, file, options) {
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let source;
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
    source = buffer.subarray(0, offset).toString('utf8');
  } finally { await handle.close(); }
  // The final unterminated JSONL record may still be being written.
  const lines = source.slice(0, source.lastIndexOf('\n') + 1).split('\n');
  const records = usageRecords(lines, options);
  let enqueued = 0, deduplicated = 0;
  for (const record of records) {
    const result = await client.enqueue('record_usage', record.key, record.payload);
    if (result.enqueued) enqueued++;
    else deduplicated++;
  }
  return { enqueued, deduplicated, source: 'explicit-session-transcript', usageAvailable: records.length > 0 };
}
