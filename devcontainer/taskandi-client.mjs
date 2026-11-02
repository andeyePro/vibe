#!/usr/bin/env node
/** Narrow, project-opt-in Task&I client: MCP (contracts v1, v2.1) or, under a descriptor binding, the browser-agent HTTP API (contract v2.2, or the v2.3 family: v2.3, v2.4, v2.5). Node built-ins only. */
import { createHash, randomUUID } from 'node:crypto';
import http from 'node:http';
import https from 'node:https';
import { closeSync, constants, existsSync, fchmodSync, fstatSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const MCP_REVISION = '2025-11-25';
export const CONTRACT_REVISION = 'vibe-agent-exchange-v2.1';
export const LEGACY_CONTRACT_REVISION = 'vibe-action-window-fixture-v1';
export const LIMITS = Object.freeze({ stdin: 256 * 1024, response: 1024 * 1024, text: 8000, body: 32000, option: 1000, options: 50, id: 200 });
const CONFIG_KEYS = new Set(['endpoint', 'task', 'contractRevision']);
const USAGE = 'usage: taskandi-client.mjs enqueue ask|comment|record_usage|record_time --key ID [--task REF] | flush | poll | status | next-task --agent claude|codex --session ID | complete --task REF --summary TEXT | release --task REF --reason TEXT | usage --transcript FILE --session ID --account ID --cost-estimate N [--task REF] | reconcile --key ID --action done|retry --evidence TEXT';
// Per-revision tool contract: every property must be required or optional, `required` must hold every required name, and types must match.
const toolSpec = (required, optional = {}) => Object.freeze({ required: Object.keys(required), optional: Object.keys(optional), types: { ...required, ...optional } });
const USAGE_FIELDS = { account: 'string', model: 'string', input: 'integer', output: 'integer', cache_read: 'integer', cache_write: 'integer', cost_estimate: 'number', source: 'string', source_ref: 'string' };
const TOOL_SPECS = Object.freeze({
  [LEGACY_CONTRACT_REVISION]: Object.freeze({
    ask: toolSpec({ task: 'string', to: 'string', question: 'string', default: 'string' }, { options: 'array' }),
    record_usage: toolSpec(USAGE_FIELDS),
    list_asks: toolSpec({ task: 'string', answered: 'boolean', since: 'object' }),
  }),
  [CONTRACT_REVISION]: Object.freeze({
    next_task: toolSpec({ task: 'string', agent: 'string', session: 'string' }),
    ask: toolSpec({ task: 'string', question: 'string', default: 'string', order: 'integer', estimate_minutes: 'integer', remaining_minutes: 'integer', reversible: 'boolean', blocking: 'boolean' }, { options: 'array', in_reply_to: 'string' }),
    list_asks: toolSpec({ task: 'string', since: 'object' }),
    comment: toolSpec({ task: 'string', text: 'string' }),
    record_usage: toolSpec({ task: 'string', ...USAGE_FIELDS }),
    record_time: toolSpec({ task: 'string', seconds: 'integer', started_at: 'string', actor: 'string' }),
    complete: toolSpec({ task: 'string', summary: 'string' }),
    release: toolSpec({ task: 'string', reason: 'string' }),
  }),
});
const TASK_REF = /^(?:[A-Za-z][A-Za-z0-9]*-[0-9]+|taskandeye:\/\/node\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12})$/;
const FALLBACK = Object.freeze({ bound: false, channel: 'file-fallback' });
const revisionOf = config => config?.contractRevision ?? CONTRACT_REVISION;
function requireV2(config, what) { if (revisionOf(config) !== CONTRACT_REVISION) fail(`${what} requires contract ${CONTRACT_REVISION}`); }

function fail(message, code = 'INVALID') { const error = new Error(message); error.code = code; throw error; }
function ownObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(`${label} must be a JSON object`);
  return value;
}
function exactKeys(value, allowed, label) {
  for (const key of Object.keys(value)) if (!allowed.has(key)) fail(`${label} contains unknown key ${key}`);
}
function text(value, name, max = LIMITS.text, empty = false) {
  if (typeof value !== 'string' || (!empty && value.length === 0) || value.length > max) fail(`${name} must be a${empty ? '' : ' non-empty'} string of at most ${max} characters`);
  return value;
}
function safeCount(value, name) {
  if (!Number.isSafeInteger(value) || value < 0) fail(`${name} must be a nonnegative safe integer`);
  return value;
}
function safeCost(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) fail('cost_estimate must be a finite nonnegative number');
  return value;
}
function taskRef(value, name = 'task') {
  text(value, name, LIMITS.id);
  if (!TASK_REF.test(value)) fail(`${name} must be a task reference`);
  return value;
}
function utcTimestamp(value, name) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/.test(value)) fail(`${name} must be a UTC timestamp`);
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 19) !== value.slice(0, 19)) fail(`${name} must be a valid UTC timestamp`);
  return value;
}
function boolean(value, name) { if (typeof value !== 'boolean') fail(`${name} must be a boolean`); return value; }
function stableKey(value) {
  text(value, 'key', LIMITS.id);
  if (!/^[A-Za-z0-9][A-Za-z0-9._:@/-]*$/.test(value)) fail('key contains unsupported characters');
  return value;
}
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
function digest(value) { return createHash('sha256').update(canonical(value)).digest('hex'); }

// File rules shared by every config file: regular, single link, not a symlink, owned by the user, optionally owner-only.
function fileRules(st, description, { ownerOnly = false, modeHint = '' } = {}) {
  if (st.isSymbolicLink && st.isSymbolicLink()) fail(`${description} must be a regular non-symlink file (it is a symlink)`);
  if (!st.isFile()) fail(`${description} must be a regular non-symlink file`);
  if (st.nlink !== 1) fail(`${description} must be a regular non-symlink file with a single link (no hard links)`);
  if (typeof process.getuid === 'function' && st.uid !== process.getuid()) fail(`${description} must be owned by the current user`);
  if (ownerOnly && (st.mode & 0o077) !== 0) fail(`${description} permissions must deny group and other access${modeHint}`);
  return st;
}
function assertRegular(path, description, options = {}) {
  let st;
  try { st = lstatSync(path); } catch (error) { if (error.code === 'ENOENT') fail(`${description} is missing`, 'MISSING'); throw error; }
  return fileRules(st, description, options);
}
function readBounded(path, limit, description, options = {}) {
  let fd;
  try { fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK); }
  catch (error) { if (error.code === 'ELOOP') fail(`${description} must be a regular non-symlink file`); if (error.code === 'ENOENT') fail(`${description} is missing`, 'MISSING'); throw error; }
  try {
    const st = fileRules(fstatSync(fd), description, options);
    if (st.size > limit) fail(`${description} exceeds ${limit} bytes`);
    const buffer = Buffer.alloc(limit + 1); let size = 0;
    for (;;) {
      const count = readSync(fd, buffer, size, buffer.length - size, null);
      if (!count) return buffer.subarray(0, size).toString('utf8');
      size += count; if (size > limit) fail(`${description} exceeds ${limit} bytes`);
    }
  } finally { closeSync(fd); }
}
function trackedCaseInsensitive(cwd, absolutePath) {
  const top = spawnSync('git', ['-C', cwd, 'rev-parse', '--show-toplevel'], { encoding: 'utf8', maxBuffer: 64 * 1024, timeout: 10000, input: '' });
  if (top.error || top.status !== 0) fail('could not locate the git worktree for config validation');
  const root = top.stdout.trim(); const wantedPath = relative(root, absolutePath);
  if (!wantedPath || wantedPath === '..' || wantedPath.startsWith(`..${process.platform === 'win32' ? '\\' : '/'}`)) return false;
  const result = spawnSync('git', ['-C', root, 'ls-files', '-z'], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 10000, input: '' });
  if (result.error || result.status !== 0) fail('could not verify that config is untracked');
  const wanted = wantedPath.replaceAll('\\', '/').toLowerCase();
  return result.stdout.split('\0').some(path => path.toLowerCase() === wanted);
}
function projectRoot(cwd) {
  const top = spawnSync('git', ['-C', resolve(cwd), 'rev-parse', '--show-toplevel'], { encoding: 'utf8', timeout: 10000, maxBuffer: 65536, input: '' });
  if (top.error || top.status !== 0) fail('could not locate the git worktree for config validation');
  return resolve(top.stdout.replace(/\n$/, ''));
}
function taskReference(value) {
  if (!TASK_REF.test(value)) fail('invalid per-launch task reference');
  return value;
}
// Shared by both binding kinds: the project's .vibe directory, and the optional untracked .vibe/taskandi-task mapping.
function checkVibeDir(cwd) {
  const vibeStat = lstatSync(join(cwd, '.vibe'));
  if (vibeStat.isSymbolicLink() || !vibeStat.isDirectory() || vibeStat.uid !== process.getuid() || (vibeStat.mode & 0o022)) fail('.vibe must be a non-symlink directory');
}
function mappedTask(cwd, parse) {
  const mappingPath = join(cwd, '.vibe/taskandi-task');
  if (!existsSync(mappingPath)) return undefined;
  if (trackedCaseInsensitive(cwd, mappingPath)) fail('Task&I node mapping must be untracked');
  return parse(readBounded(mappingPath, 1024, 'Task&I node mapping').trim());
}
export function loadConfig(cwd = process.cwd()) {
  cwd = projectRoot(cwd);
  const relative = '.vibe/taskandi.json';
  const path = join(cwd, relative);
  if (lexists(join(cwd, DESCRIPTOR))) { if (lexists(path)) fail('two Task&I bindings; keep one'); return loadDescriptor(cwd); }
  if (!existsSync(path)) {
    if (process.env.VIBE_TASK_BINDING && process.env.VIBE_TASK_BINDING !== 'unbound') fail('pinned task binding changed');
    return { bound: false, reason: 'missing-config', cwd };
  }
  checkVibeDir(cwd);
  assertRegular(path, 'Task&I config');
  if (trackedCaseInsensitive(cwd, path)) fail('Task&I config is tracked by git (case-insensitive match refused)');
  let value;
  try { value = ownObject(JSON.parse(readBounded(path, 32 * 1024, 'Task&I config')), 'config'); } catch (error) { if (error instanceof SyntaxError) fail('Task&I config is not valid JSON'); throw error; }
  exactKeys(value, CONFIG_KEYS, 'config');
  text(value.endpoint, 'endpoint', 2048);
  let task = mappedTask(cwd, taskReference) ?? value.task;
  if (process.env.VIBE_TASK_REF) task = taskReference(process.env.VIBE_TASK_REF);
  text(task, 'task', LIMITS.id);
  if (value.contractRevision !== undefined && value.contractRevision !== CONTRACT_REVISION && value.contractRevision !== LEGACY_CONTRACT_REVISION) fail(`contractRevision must exactly equal ${CONTRACT_REVISION} or ${LEGACY_CONTRACT_REVISION}`);
  let endpoint;
  try { endpoint = new URL(value.endpoint); } catch { fail('endpoint is not a valid absolute URL'); }
  const authority = value.endpoint.match(/^[A-Za-z][A-Za-z0-9+.-]*:\/\/([^/]*)/)?.[1] || '';
  if (authority.includes('@') || value.endpoint.includes('?') || value.endpoint.includes('#')) fail('endpoint must not contain userinfo, query, or fragment');
  const host = endpoint.hostname.toLowerCase();
  const loopback = host === 'localhost' || host === 'host.docker.internal' || host === '127.0.0.1' || host === '[::1]';
  if (endpoint.protocol !== 'https:' && !(endpoint.protocol === 'http:' && loopback)) fail('endpoint must use HTTPS (HTTP is limited to loopback or host.docker.internal)');
  if (!['https:', 'http:'].includes(endpoint.protocol)) fail('unsupported endpoint protocol');
  const config = { bound: true, cwd, endpoint: endpoint.href, origin: endpoint.origin, task, contractRevision: value.contractRevision ?? CONTRACT_REVISION };
  if (process.env.VIBE_TASK_BINDING && process.env.VIBE_TASK_BINDING !== bindingFingerprint(config)) fail('pinned task binding changed');
  return config;
}

// The one binding digest (fingerprint, job binding and answer binding) for both binding kinds. The descriptor digest
// leaves out token, connection and the origin's port, so a reconnect keeps queued jobs, stored answers and a pinned
// supervisor fingerprint valid; the origin's scheme and host are in it, so a different service is a different binding.
function bindingDigest(config) {
  if (config.kind === HTTP_KIND) return digest({ kind: HTTP_KIND, workspace: config.workspace, task: config.task, contractRevision: config.contractRevision, originHost: config.originHost });
  return digest({ endpoint: config.endpoint, task: config.task, contractRevision: config.contractRevision });
}
export function bindingFingerprint(config) {
  return config.bound ? bindingDigest(config) : 'unbound';
}

function ensurePrivateDir(path) {
  mkdirSync(path, { recursive: true, mode: 0o700 });
  const st = lstatSync(path);
  if (st.isSymbolicLink() || !st.isDirectory()) fail(`${path} must be a non-symlink directory`);
  if (typeof process.getuid === 'function' && st.uid !== process.getuid()) fail(`${path} must be owned by the current user`);
  if ((st.mode & 0o077) !== 0) fail(`${path} permissions must deny group and other access`);
}
function ensureBaseDir(path) {
  mkdirSync(path, { recursive: true, mode: 0o700 });
  const st = lstatSync(path);
  if (st.isSymbolicLink() || !st.isDirectory()) fail(`${path} must be a non-symlink directory`);
  if (typeof process.getuid === 'function' && st.uid !== process.getuid()) fail(`${path} must be owned by the current user`);
}
function atomicJson(path, value) {
  ensurePrivateDir(dirname(path));
  if (Array.isArray(value?.jobs)) pruneJobs(value);
  const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
  const encoded = `${JSON.stringify(value, null, 2)}\n`;
  if (Buffer.byteLength(encoded) > 4 * 1024 * 1024) fail('outbox capacity exceeded; archive completed records before adding data');
  const fd = openSync(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { writeFileSync(fd, encoded); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(tmp, path);
  const dfd = openSync(dirname(path), constants.O_RDONLY); try { fsyncSync(dfd); } finally { closeSync(dfd); }
}
// Outbox pruning: on every state write, done jobs beyond the KEEP_DONE most recent (by doneAtMs) are dropped. queued,
// dispatching, uncertain and refused jobs are never pruned, nor a `budget-<task>` job, nor an ask job behind an open ask.
// A pruned job leaves a tombstone {key, kind, digest, doneAtMs}, so enqueue still deduplicates (or refuses) its key;
// tombstones older than TOMBSTONE_MS are dropped. The clock is the client's (state[NOW], set by withState).
const KEEP_DONE = 2000;
const TOMBSTONE_MS = 90 * 24 * 60 * 60 * 1000;
const NOW = Symbol('now');
const doneMs = job => (Number.isSafeInteger(job.doneAtMs) ? job.doneAtMs : Number.isFinite(Date.parse(job.doneAt)) ? Date.parse(job.doneAt) : null);
const ledger = (state, name) => (Array.isArray(state[name]) ? state[name] : []);
// A `resolved` entry from before task_065 cycle 3 may say `as: parked`; that never closed an ask, so it is ignored.
const isResolved = (state, task, askId) => ledger(state, 'resolved').some(item => item.task === task && item.ask_id === askId && item.as !== 'parked');
// The one open-ask predicate (pruning, decide, the reclaim guard): a done ask job on the task with a result.ask_id, no
// stored owner answer with the same task and ask_id, and not resolved. An answer stored without a task, or without
// ownerAnswer: true, never closes an ask (an open ask is never hidden by a record that cannot prove it answers it).
function isOpenAsk(state, job, task = job.payload?.task) {
  if (job.kind !== 'ask' || job.state !== 'done' || job.payload?.task !== task || typeof job.result?.ask_id !== 'string') return false;
  const askId = job.result.ask_id;
  return !state.answers.some(item => item.id === askId && item.task === task && item.ownerAnswer === true) && !isResolved(state, task, askId);
}
const isBudgetJob = job => typeof job.payload?.task === 'string' && job.key === `budget-${job.payload.task}`;
const tombstoneOf = (state, key) => ledger(state, 'tombstones').find(item => item.key === key);
function pruneJobs(state) {
  const at = typeof state[NOW] === 'function' ? state[NOW]() : Date.now();
  const before = ledger(state, 'tombstones');
  const tombstones = before.filter(item => Number.isSafeInteger(item?.doneAtMs) && at - item.doneAtMs <= TOMBSTONE_MS);
  let changed = tombstones.length !== before.length;
  // The created ledger (task_067) is never pruned with the jobs; only its entries older than 180 days are dropped, and
  // never an `assign: "agent"` entry (it is what keeps vibe from working its own proposal, AC24).
  if (Array.isArray(state.created)) {
    const kept = state.created.filter(item => item?.assign === 'agent' || !(Number.isSafeInteger(item?.at) && at - item.at > CREATED_MS));
    if (kept.length !== state.created.length) state.created = kept;
  }
  const done = state.jobs.filter(job => job.state === 'done');
  if (done.length > KEEP_DONE) {
    const keep = new Set(done.sort((a, b) => (doneMs(b) ?? at) - (doneMs(a) ?? at)).slice(0, KEEP_DONE));
    state.jobs = state.jobs.filter(job => {
      if (job.state !== 'done' || keep.has(job) || isBudgetJob(job) || isOpenAsk(state, job)) return true;
      const doneAtMs = doneMs(job) ?? at;
      if (at - doneAtMs <= TOMBSTONE_MS) tombstones.push({ key: job.key, kind: job.kind, digest: job.digest, doneAtMs });
      changed = true; return false;
    });
  }
  if (changed) state.tombstones = tombstones;
}
function initialState() { return { version: 1, jobs: [], reconciliationLog: [], cursor: null, answers: [], conflicts: [] }; }
function paths(cwd) { const dir = join(resolve(cwd), '.vibe/taskandi-outbox'); return { dir, state: join(dir, 'state.json'), lock: join(dir, '.lock') }; }
function lockOutbox(cwd) {
  const p = paths(cwd); ensureBaseDir(join(resolve(cwd), '.vibe')); ensurePrivateDir(p.dir);
  let fd;
  const token = randomUUID();
  try { fd = openSync(p.lock, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600); }
  catch (error) {
    if (error.code === 'EEXIST') fail('outbox ownership is live or ambiguous; confirm the prior invocation has ended, then explicitly reconcile its lock', 'LOCKED');
    throw error;
  }
  writeFileSync(fd, token); fsyncSync(fd);
  return { ...p, release() {
    // Never unlink a replacement owner's lock: unlink only while the path is still our own file (same inode), checked
    // through the open descriptor rather than by reopening the lock.
    const mine = fstatSync(fd); closeSync(fd);
    try { const current = lstatSync(p.lock); if (current.ino === mine.ino && current.dev === mine.dev) unlinkSync(p.lock); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  } };

}
function readState(path) {
  if (!existsSync(path)) return initialState();
  let state; try { state = ownObject(JSON.parse(readBounded(path, 4 * 1024 * 1024, 'outbox state', { ownerOnly: true })), 'outbox state'); } catch (error) { if (error instanceof SyntaxError) fail('outbox state is corrupt'); throw error; }
  if (state.version !== 1 || !Array.isArray(state.jobs) || !Array.isArray(state.answers) || !Array.isArray(state.conflicts) || !Array.isArray(state.reconciliationLog)) fail('outbox state has an unsupported shape');
  // Ledgers added by task_065: absent in older files (read as empty), and written only when used.
  for (const name of ['resolved', 'parked', 'repolls', 'tombstones', 'created']) if (state[name] !== undefined && !Array.isArray(state[name])) fail('outbox state has an unsupported shape');
  for (const name of ['windowsUsed', 'polls', 'usageImports']) if (state[name] !== undefined && !plainObject(state[name])) fail('outbox state has an unsupported shape');
  return state;
}
// The one answer-binding check; `bind` also records the binding (callers persist it).
function bindAnswers(state, config, bind = true) {
  const binding = bindingDigest(config);
  if (state.answerBinding && state.answerBinding !== binding) fail('answer binding changed; archive the prior outbox before polling another task');
  if (!state.answerBinding && (state.cursor || state.cursors || state.answers.length || state.conflicts.length)) fail('existing answers have no binding evidence; reconcile before polling');
  if (state.cursors !== undefined && !plainObject(state.cursors)) fail('outbox state has an unsupported cursor shape');
  if (bind) state.answerBinding = binding;
}
// A job found dispatching was in flight when an invocation ended. One sent to a v2.3-family server carries its frozen
// sentBody and request_id, so it goes back to queued (an outcome-unknown attempt) and the next v2.3 flush resends it;
// any other is uncertain.
const MAX_ATTEMPTS = 5;
function recoverDispatching(state) {
  let changed = false;
  for (const job of state.jobs) {
    if (job.state !== 'dispatching') continue;
    changed = true;
    if (isV23(job.sentRevision) && typeof job.sentBody === 'string') {
      job.attempts = (Number.isSafeInteger(job.attempts) ? job.attempts : 0) + 1;
      job.state = job.attempts >= MAX_ATTEMPTS ? 'uncertain' : 'queued';
      job.lastError = `previous invocation ended while dispatching${job.state === 'queued' ? '; the next v2.3 flush resends the same body and request_id' : ` (${MAX_ATTEMPTS} attempts)`}`;
    } else { job.state = 'uncertain'; job.lastError = 'previous invocation ended while dispatching'; }
  }
  return changed;
}
async function withState(cwd, now, fn) {
  const locked = lockOutbox(cwd);
  try {
    const state = readState(locked.state); Object.defineProperty(state, NOW, { value: now, enumerable: false }); if (recoverDispatching(state)) atomicJson(locked.state, state);
    return await fn(state, locked.state);
  } finally { locked.release(); }
}

export function validatePayload(kind, input, config, key) {
  input = ownObject(input, `${kind} payload`);
  const v1 = revisionOf(config) === LEGACY_CONTRACT_REVISION;
  if (v1 && (kind === 'comment' || kind === 'record_time')) requireV2(config, `enqueue ${kind}`);
  const options = () => {
    if (!Array.isArray(input.options) || input.options.length > LIMITS.options) fail(`options must be an array of at most ${LIMITS.options} strings`);
    return input.options.map((item, i) => text(item, `options[${i}]`, LIMITS.option));
  };
  const target = () => (input.task === undefined ? text(config.task, 'task', LIMITS.id) : taskRef(input.task));
  if (kind === 'ask' && v1) {
    exactKeys(input, new Set(['to', 'question', 'default', 'options']), 'ask payload');
    const payload = { task: text(config.task, 'task', LIMITS.id), to: text(input.to, 'to', LIMITS.id), question: text(input.question, 'question'), default: text(input.default, 'default') };
    if (input.options !== undefined) payload.options = options();
    return payload;
  }
  if (kind === 'ask') {
    exactKeys(input, new Set(['question', 'default', 'options', 'order', 'estimate_minutes', 'remaining_minutes', 'reversible', 'blocking', 'in_reply_to', 'task']), 'ask payload');
    const payload = { task: target(), question: text(input.question, 'question'), default: text(input.default, 'default'), order: safeCount(input.order, 'order'), estimate_minutes: safeCount(input.estimate_minutes, 'estimate_minutes'), remaining_minutes: safeCount(input.remaining_minutes, 'remaining_minutes'), reversible: boolean(input.reversible, 'reversible'), blocking: input.blocking === undefined ? true : boolean(input.blocking, 'blocking') };
    if (input.options !== undefined) payload.options = options();
    if (input.in_reply_to !== undefined) payload.in_reply_to = text(input.in_reply_to, 'in_reply_to', LIMITS.id);
    return payload;
  }
  if (kind === 'comment') {
    exactKeys(input, new Set(['text', 'task']), 'comment payload');
    return { task: target(), text: text(input.text, 'text') };
  }
  if (kind === 'record_time') {
    exactKeys(input, new Set(['seconds', 'started_at', 'task']), 'record_time payload');
    return { task: target(), seconds: safeCount(input.seconds, 'seconds'), started_at: utcTimestamp(input.started_at, 'started_at'), actor: 'agent' };
  }
  if (kind === 'record_usage') {
    exactKeys(input, new Set(['account', 'model', 'input', 'output', 'cache_read', 'cache_write', 'cost_estimate', ...(v1 ? [] : ['task'])]), 'record_usage payload');
    const usage = { account: text(input.account, 'account', LIMITS.id), model: text(input.model, 'model', LIMITS.id), input: safeCount(input.input, 'input'), output: safeCount(input.output, 'output'), cache_read: safeCount(input.cache_read, 'cache_read'), cache_write: safeCount(input.cache_write, 'cache_write'), cost_estimate: safeCost(input.cost_estimate), source: 'vibe', source_ref: stableKey(key) };
    return v1 ? usage : { task: target(), ...usage };
  }
  fail(`unsupported enqueue kind ${kind}`);
}

function validateTool(tool, expectedName, revision = CONTRACT_REVISION) {
  if (!tool || tool.name !== expectedName) fail(`expected tool ${expectedName} is missing`, 'PREDISPATCH');
  const contract = TOOL_SPECS[revision]?.[expectedName];
  if (!contract) fail(`${expectedName} is not part of contract ${revision}`, 'PREDISPATCH');
  const schema = ownObject(tool.inputSchema, `${expectedName} inputSchema`);
  if (schema.type !== 'object' || !schema.properties || typeof schema.properties !== 'object' || Array.isArray(schema.properties)) fail(`${expectedName} has an unsupported input schema`, 'PREDISPATCH');
  const allowed = new Set([...contract.required, ...contract.optional]);
  const properties = Object.keys(schema.properties);
  const required = Array.isArray(schema.required) ? schema.required : [];
  if (properties.some(key => !allowed.has(key)) || required.some(key => !allowed.has(key))) fail(`${expectedName} schema contains fields outside the narrow contract`, 'PREDISPATCH');
  if (contract.required.some(key => !properties.includes(key) || !required.includes(key))) fail(`${expectedName} schema does not require the fixture contract fields`, 'PREDISPATCH');
  if (properties.some(key => schema.properties[key]?.type !== contract.types[key])) fail(`${expectedName} schema has incompatible field types`, 'PREDISPATCH');
  if (expectedName === 'ask' && properties.includes('options') && schema.properties.options.items?.type !== 'string') fail('ask options schema must contain string items', 'PREDISPATCH');
  return tool;
}
function parseRpc(body, expectedId) {
  const value = ownObject(body, 'MCP response');
  if (value.jsonrpc !== '2.0' || value.id !== expectedId) fail('MCP response has a mismatched JSON-RPC id');
  if (value.error) { const error = new Error('MCP server returned a JSON-RPC error'); error.rpcError = value.error; throw error; }
  if (!Object.hasOwn(value, 'result')) fail('MCP response has neither result nor error');
  return value.result;
}
function parseSse(source) {
  const events = source.split(/\r?\n\r?\n/); let json = null;
  for (const event of events) {
    const data = event.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!data || data === '[DONE]') continue;
    if (json !== null) fail('multiple JSON SSE data events are unsupported');
    try { json = JSON.parse(data); } catch { fail('SSE data is not valid JSON'); }
  }
  if (json === null) fail('SSE response did not contain JSON data');
  return json;
}
function headerValue(headers, name) {
  if (!headers) return null;
  if (typeof headers.get === 'function') return headers.get(name);
  const found = Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase());
  return found ? String(found[1]) : null;
}

export async function fetchTransport({ url, origin, headers, body, timeoutMs = 30000 }) {
  if (new URL(url).origin !== origin) fail('transport target left the configured origin');
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { method: 'POST', redirect: 'manual', headers, body: JSON.stringify(body), signal: controller.signal });
    if (response.status >= 300 && response.status < 400) fail('MCP redirects are refused');
    const declared = Number(response.headers.get('content-length'));
    if (Number.isFinite(declared) && declared > LIMITS.response) fail('MCP response exceeds size limit');
    const chunks = []; let size = 0;
    if (response.body) {
      const reader = response.body.getReader();
      for (;;) {
        const { done, value } = await reader.read(); if (done) break;
        size += value.byteLength;
        if (size > LIMITS.response) { await reader.cancel(); fail('MCP response exceeds size limit'); }
        chunks.push(Buffer.from(value));
      }
    }
    return { status: response.status, headers: response.headers, contentType: response.headers.get('content-type') || '', body: Buffer.concat(chunks, size).toString('utf8') };
  } finally { clearTimeout(timer); }
}

export function createMcp(config, transport = fetchTransport) {
  let id = 0; let session = null;
  async function send(method, params, notification = false) {
    const rpcId = notification ? undefined : ++id;
    const message = { jsonrpc: '2.0', ...(notification ? {} : { id: rpcId }), method, ...(params === undefined ? {} : { params }) };
    const headers = { 'content-type': 'application/json', accept: 'application/json, text/event-stream' };
    headers['mcp-protocol-version'] = MCP_REVISION;
    if (session) headers['mcp-session-id'] = session;
    const response = await transport({ url: config.endpoint, origin: config.origin, headers, body: message, timeoutMs: 30000 });
    if (!response || !Number.isInteger(response.status)) fail('transport returned an invalid response');
    if (response.status < 200 || response.status >= 300) fail(`MCP HTTP request failed with status ${response.status}`);
    const receivedSession = headerValue(response.headers, 'mcp-session-id');
    if (receivedSession) {
      if (/[\r\n]/.test(receivedSession) || receivedSession.length > 1024) fail('invalid MCP session header');
      session = receivedSession;
    }
    if (typeof response.body !== 'string' || Buffer.byteLength(response.body) > LIMITS.response) fail('transport returned an invalid or oversized body');
    if (notification) return null;
    const contentType = (response.contentType || headerValue(response.headers, 'content-type') || '').toLowerCase();
    if (!contentType.includes('application/json') && !contentType.includes('text/event-stream')) fail('unsupported MCP response content type');
    let parsed; try { parsed = contentType.includes('text/event-stream') ? parseSse(response.body) : JSON.parse(response.body); } catch (error) { if (error instanceof SyntaxError) fail('MCP response is not valid JSON'); throw error; }
    return parseRpc(parsed, rpcId);
  }
  return {
    async discover() {
      const initialized = await send('initialize', { protocolVersion: MCP_REVISION, capabilities: {}, clientInfo: { name: 'vibe-taskandi', version: '0.1.0' } });
      if (!initialized || initialized.protocolVersion !== MCP_REVISION) fail(`server did not negotiate MCP revision ${MCP_REVISION}`);
      await send('notifications/initialized', undefined, true);
      const listed = await send('tools/list', {});
      if (!listed || !Array.isArray(listed.tools)) fail('tools/list returned an unsupported shape');
      return listed.tools;
    },
    async call(name, args) {
      const result = await send('tools/call', { name, arguments: args });
      if (!result || typeof result !== 'object' || Array.isArray(result) || result.isError === true || (!Array.isArray(result.content) && !result.structuredContent)) { const error = new Error(`MCP tool ${name} reported an error`); error.toolError = true; throw error; }
      return result;
    },
  };
}

function toolJson(result) {
  if (result.structuredContent !== undefined) return ownObject(result.structuredContent, 'tool structuredContent');
  if (!Array.isArray(result.content) || result.content.length !== 1 || result.content[0]?.type !== 'text' || typeof result.content[0].text !== 'string') fail('tool result must contain one JSON text item or structuredContent');
  if (Buffer.byteLength(result.content[0].text) > LIMITS.response) fail('tool result exceeds size limit');
  try { return ownObject(JSON.parse(result.content[0].text), 'tool JSON result'); } catch (error) { if (error instanceof SyntaxError) fail('tool text result is not JSON'); throw error; }
}
function validateCursor(value, label) {
  value = ownObject(value, label); exactKeys(value, new Set(['sequence', 'value']), label);
  safeCount(value.sequence, `${label}.sequence`); text(value.value, `${label}.value`, LIMITS.id, true); return value;
}
function validatePollResult(result, prior, revision = CONTRACT_REVISION) {
  const value = toolJson(result); exactKeys(value, new Set(['since', 'cursor', 'answers']), 'list_asks result');
  const since = validateCursor(value.since, 'list_asks result since'); const cursor = validateCursor(value.cursor, 'list_asks result cursor');
  if (since.sequence !== prior.sequence || since.value !== prior.value) fail('list_asks response does not echo the requested cursor');
  if (cursor.sequence < prior.sequence) fail('list_asks cursor regressed');
  if (cursor.sequence === prior.sequence && cursor.value !== prior.value) fail('list_asks cursor is noncomparable');
  if (!Array.isArray(value.answers) || value.answers.length > 1000) fail('list_asks answers has an unsupported shape');
  if (revision === LEGACY_CONTRACT_REVISION) {
    const answers = value.answers.map((item, index) => { item = ownObject(item, `answer[${index}]`); exactKeys(item, new Set(['id', 'content']), `answer[${index}]`); return { id: text(item.id, `answer[${index}].id`, LIMITS.id), content: text(item.content, `answer[${index}].content`, LIMITS.text, true) }; });
    return { cursor, answers };
  }
  const keys = ['ask_id', 'answer', 'owner_answer', 'seen_at', 'answered_at'];
  const seen = new Set();
  const answers = value.answers.map((item, index) => {
    const label = `answer[${index}]`; item = ownObject(item, label); exactKeys(item, new Set(keys), label);
    for (const name of keys) if (!Object.hasOwn(item, name)) fail(`${label}.${name} is required`);
    const id = text(item.ask_id, `${label}.ask_id`, LIMITS.id);
    if (seen.has(id)) fail(`${label}.ask_id repeats an earlier answer`); seen.add(id);
    return { id, content: text(item.answer, `${label}.answer`, LIMITS.text, true), ownerAnswer: boolean(item.owner_answer, `${label}.owner_answer`), seenAt: item.seen_at === null ? null : utcTimestamp(item.seen_at, `${label}.seen_at`), answeredAt: utcTimestamp(item.answered_at, `${label}.answered_at`) };
  });
  return { cursor, answers };
}
const count = (value, name) => safeCount(value, name);
function strictObject(value, keys, optional, label) {
  value = ownObject(value, label); exactKeys(value, new Set([...keys, ...optional]), label);
  for (const key of keys) if (!Object.hasOwn(value, key)) fail(`${label}.${key} is required`);
  return value;
}
function validateNextTask(value) {
  value = ownObject(value, 'next_task result');
  if (Object.hasOwn(value, 'task') && value.task === null) { exactKeys(value, new Set(['task']), 'next_task result'); return { task: null }; }
  strictObject(value, ['task', 'title', 'body', 'priority', 'effective_priority', 'allowance', 'spent', 'owner', 'lease'], ['hardDeadline', 'latest_start', 'estimate_minutes'], 'next_task result');
  const allowance = strictObject(value.allowance, [], ['windows', 'tokens'], 'next_task allowance'); const spent = strictObject(value.spent, ['windows', 'tokens'], [], 'next_task spent'); const lease = strictObject(value.lease, ['until', 'session'], [], 'next_task lease');
  const out = { task: taskRef(value.task), title: text(value.title, 'title'), body: text(value.body, 'body', LIMITS.body, true), priority: count(value.priority, 'priority'), effective_priority: count(value.effective_priority, 'effective_priority'), allowance: {}, spent: { windows: count(spent.windows, 'spent.windows'), tokens: count(spent.tokens, 'spent.tokens') } };
  for (const key of ['windows', 'tokens']) if (allowance[key] !== undefined) out.allowance[key] = count(allowance[key], `allowance.${key}`);
  if (value.hardDeadline !== undefined) out.hardDeadline = utcTimestamp(value.hardDeadline, 'hardDeadline');
  if (value.latest_start !== undefined) out.latest_start = utcTimestamp(value.latest_start, 'latest_start');
  if (value.estimate_minutes !== undefined) out.estimate_minutes = count(value.estimate_minutes, 'estimate_minutes');
  out.owner = text(value.owner, 'owner', LIMITS.id); out.lease = { until: utcTimestamp(lease.until, 'lease.until'), session: text(lease.session, 'lease.session', LIMITS.id) };
  return out;
}
function validateAskResult(value) {
  value = ownObject(value, 'ask result'); exactKeys(value, new Set(['ask_id', 'placed']), 'ask result');
  const result = { ask_id: text(value.ask_id, 'ask_id', LIMITS.id) };
  if (value.placed !== 'subtask' && value.placed !== 'thread') fail('placed must be subtask or thread');
  result.placed = value.placed; return result;
}
function validateComplete(value) {
  value = ownObject(value, 'complete result');
  if (value.completed === true) { exactKeys(value, new Set(['completed', 'state']), 'complete result'); if (value.state !== 'done-provisional') fail('state must be done-provisional'); return { completed: true, state: 'done-provisional' }; }
  if (value.completed !== false) fail('completed must be a boolean');
  exactKeys(value, new Set(['completed', 'open_children']), 'complete result');
  if (!Array.isArray(value.open_children) || value.open_children.length < 1 || value.open_children.length > 200) fail('open_children must hold 1 to 200 items');
  return { completed: false, open_children: value.open_children.map((item, i) => { item = strictObject(item, ['task', 'title'], [], `open_children[${i}]`); return { task: taskRef(item.task, `open_children[${i}].task`), title: text(item.title, `open_children[${i}].title`) }; }) };
}
function validateRelease(value) {
  value = ownObject(value, 'release result'); exactKeys(value, new Set(['released']), 'release result');
  if (value.released !== true) fail('released must be true');
  return { released: true };
}

// ---- Contract v2.2: Task&I's browser-agent HTTP API, selected by .vibe/taskandi-descriptor.json ----
// Plain `POST <origin>/api/browser-agent` on node:http(s) (never fetch: it cannot set Host). Wire facts:
// /brain2/andeye/Task&I-agent-exchange-fixtures/README.md "Wire details"; fixtures in smoke/fixtures/taskandi-v22/.
// HTTP_CONTRACT_REVISION stays the descriptor binding's protocol pin: it is the literal in the binding digest, so queued
// jobs, stored answers and pinned fingerprints survive a v2.2<->v2.3 switch. The negotiated revision (capabilities.contract,
// one of HTTP_CONTRACT_REVISIONS) decides the wire rules per invocation; v2.4 and v2.5 follow every v2.3 rule (the
// "v2.3 family") and add create_task/update_task (v2.4) and repeat (v2.5), which are gated per job (task_067).
export const HTTP_CONTRACT_REVISION = 'vibe-agent-exchange-v2.2';
export const HTTP_CONTRACT_V23 = 'vibe-agent-exchange-v2.3';
export const HTTP_CONTRACT_REVISIONS = Object.freeze([HTTP_CONTRACT_REVISION, HTTP_CONTRACT_V23, 'vibe-agent-exchange-v2.4', 'vibe-agent-exchange-v2.5']);
const V23_FAMILY = new Set(HTTP_CONTRACT_REVISIONS.slice(1));
export const isV23 = contract => V23_FAMILY.has(contract);
// v2.3 capabilities.limits: these twelve keys must be present (unit and id_unit fixed strings, the rest positive integers);
// from v2.4 on title, next_action and notes are required too (SERVER_LIMIT_KEYS_V24). Other extra keys are ignored.
export const SERVER_LIMIT_KEYS = Object.freeze(['unit', 'id', 'id_unit', 'request_bytes', 'question', 'default', 'options', 'option', 'ask_post', 'comment', 'summary', 'reason']);
export const HTTP_PROTOCOL = 'taskandeye-browser-agent-v1';
export const HTTP_LIMITS = Object.freeze({ response: 16 * 1024 * 1024, timeoutMs: 15000, body: 65536, descriptor: 32 * 1024, id: 200, question: 8000, default: 2000, options: 20, option: 500, post: 8000, comment: 8000, summary: 7950, reason: 2000, answer: 8000, seconds: 604800, shortText: 2000 });
const HTTP_KIND = 'descriptor-http';
const DESCRIPTOR = '.vibe/taskandi-descriptor.json';
const DESCRIPTOR_KEYS = ['protocol', 'origin', 'connection', 'workspace', 'root', 'token'];
const USABLE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;
const DESCRIPTOR_WORD = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$/;
const ABBR_REF = /^[A-Za-z][A-Za-z0-9]*-[0-9]+$/;
const UUID_SHAPE = /^[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$/;
const PRINTABLE_CODE = /^[a-z][a-z_]{0,63}$/;
const NO_BOUND_TASK = 'no bound task: the connection covers the whole workspace; claim one with next-task';
const NEEDS_CLAIM = 'complete/release needs the session that claimed the task; run next-task first';
const UNUSABLE_TASK = 'task id not usable by vibe: rename it in Task&I or recreate the task';
const REVOKED = 'the Task&I connection was revoked or replaced; copy a fresh descriptor (More → Connect Codex) into .vibe/taskandi-descriptor.json';
const HTTP_USAGE = 'usage (Task&I descriptor binding): taskandi-client.mjs enqueue ask|comment|record_usage|record_time --key ID [--task ID] | enqueue create_task --key ID [--session STAMP] | enqueue update_task --key ID [--session STAMP] | created [--task ID] [--all] | flush | poll [--task ID] | ask-status [--task ID] | status | next-task --agent claude|codex --session ID [--task ID] [--body-max-chars N] | decide [--no-other-work] [--remaining-minutes N] [--windows-used N] | decide --resolve KEY --as proceeded | complete [--task ID] --summary TEXT | release [--task ID] --reason TEXT [--parked-asks ID,ID] [--budget-stopped] | usage --transcript FILE --session ID --account ID --cost-estimate N [--task ID] | reconcile --key ID --action done|retry --evidence TEXT [--task-id ID] | reconcile --direct complete|release --task ID --action done|retry --evidence TEXT';
// Every error class in one table. Codes not listed here (and every malformed, unexpected or lost response) are outcome unknown.
// later = not applied, may succeed unchanged later; rejected = not applied, the request itself is refused.
const HTTP_ERRORS = Object.freeze({
  connection_unavailable: 'unknown', connection_revoked: 'unknown',
  stale_context: 'later', sync_required: 'later', lease_held: 'later', wrong_origin: 'later', connection_scope: 'later',
  use_native_connection: 'rejected', scope_missing: 'rejected', invalid_request: 'rejected', wrong_scope: 'rejected', wrong_thread: 'rejected', unknown_ask: 'rejected', not_assigned: 'rejected', receipt_collision: 'rejected', body_too_large: 'rejected',
});
// Exactly-formed non-200 bodies: status -> the one code that status may carry (409 carries any code).
const ERROR_STATUS = Object.freeze({ 409: null, 400: 'invalid_request', 421: 'wrong_origin', 403: 'connection_scope' });
// v2.3 family: every exchange call runs in one transaction after the revocation check, so every 409 (and every
// exactly-formed 400/403/405/421, answered before the transport) means nothing was applied by that send. On a resend
// only RESEND_PROOF_CODES prove the same of earlier attempts (AC29). receipt_collision is classified by the caller.
const HTTP_ERRORS_V23 = Object.freeze({
  connection_unavailable: 'later', connection_revoked: 'later', stale_context: 'later', sync_required: 'later', lease_held: 'later',
  wrong_origin: 'later', connection_scope: 'later', method_not_allowed: 'later',
  use_native_connection: 'rejected', scope_missing: 'rejected', invalid_request: 'rejected', wrong_scope: 'rejected', wrong_thread: 'rejected', unknown_ask: 'rejected', not_assigned: 'rejected', receipt_collision: 'rejected', body_too_large: 'rejected',
});
const ERROR_STATUS_V23 = Object.freeze({ ...ERROR_STATUS, 405: 'method_not_allowed' });

const codePoints = value => [...value].length;
const plainObject = value => !!value && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
function wireText(value, name, max) {
  if (typeof value !== 'string' || !value.isWellFormed() || value.trim() === '' || codePoints(value) > max) fail(`${name} must be well-formed, non-blank text of at most ${max} code points`);
  return value;
}
function wireId(value, name) {
  if (typeof value !== 'string' || !value.isWellFormed() || value.trim() === '' || value.length > HTTP_LIMITS.id) fail(`${name} must be well-formed, non-blank text of 1-${HTTP_LIMITS.id} UTF-16 code units`);
  return value;
}
// A task ref under a descriptor binding: a usable id or taskandeye://node/<usable id>; a UUID-shaped user-typed id is lower-cased once.
export function descriptorTaskRef(value, name = 'task') {
  if (typeof value !== 'string') fail(`${name} must be a Task&I task id`);
  if (ABBR_REF.test(value)) fail('Task&I descriptor bindings take task ids, not ABBR-N references');
  return normaliseTaskId(value, name);
}
// The one task-id normaliser (--task, parent, update_task.task, reconcile --task-id, created --task): the
// taskandeye://node/ prefix is stripped, the rest must be a usable id, and a UUID-shaped id is lower-cased. Ids that
// Task&I itself returned (a created ledger's ids) may look like ABBR-N, so only --task refuses that shape.
export function normaliseTaskId(value, name = 'task') {
  if (typeof value !== 'string') fail(`${name} must be a Task&I task id`);
  const id = value.startsWith('taskandeye://node/') ? value.slice('taskandeye://node/'.length) : value;
  if (!USABLE_ID.test(id)) fail(`${name} must be a Task&I task id: 1-200 characters of A-Z a-z 0-9 . _ : - starting with a letter or digit`);
  return UUID_SHAPE.test(id) ? id.toLowerCase() : id;
}
function lexists(path) {
  try { lstatSync(path); return true; } catch (error) { if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return false; throw error; }
}
function descriptorOrigin(origin) {
  let url; try { url = new URL(origin); } catch { fail('descriptor origin is not a valid URL'); }
  if (url.origin !== origin) fail('descriptor origin must be a bare origin: no path, query, fragment, userinfo or trailing slash');
  if (url.protocol === 'https:') return origin;
  const port = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(origin)?.[1];
  if (!port || Number(port) > 65535) fail('descriptor origin must be https, or exactly http://127.0.0.1:<port 1-65535>');
  return origin;
}
function loadDescriptor(cwd) {
  const path = join(cwd, DESCRIPTOR);
  const rules = { ownerOnly: true, modeHint: ': run chmod 600 .vibe/taskandi-descriptor.json' };
  checkVibeDir(cwd);
  assertRegular(path, 'Task&I descriptor', rules);
  if (trackedCaseInsensitive(cwd, path)) fail('Task&I descriptor is tracked by git (case-insensitive match refused)');
  let value;
  try { value = JSON.parse(readBounded(path, HTTP_LIMITS.descriptor, 'Task&I descriptor', rules)); } catch (error) { if (error instanceof SyntaxError) fail('Task&I descriptor is not valid JSON'); throw error; }
  if (!plainObject(value)) fail('Task&I descriptor must be a JSON object');
  if (Object.keys(value).some(key => !DESCRIPTOR_KEYS.includes(key))) fail(`Task&I descriptor has a key outside ${DESCRIPTOR_KEYS.join(', ')}`);
  for (const key of DESCRIPTOR_KEYS) if (!Object.hasOwn(value, key)) fail(`Task&I descriptor key ${key} is required`);
  if (value.protocol !== HTTP_PROTOCOL) fail(`Task&I descriptor protocol must be ${HTTP_PROTOCOL}`);
  for (const key of ['origin', 'connection', 'workspace']) if (typeof value[key] !== 'string' || !DESCRIPTOR_WORD.test(value[key])) fail(`Task&I descriptor ${key} must be 1-200 characters of A-Z a-z 0-9 . _ : @ / - starting with a letter or digit`);
  descriptorOrigin(value.origin);
  if (value.root !== null && (typeof value.root !== 'string' || !USABLE_ID.test(value.root))) fail('Task&I descriptor root must be a usable task id or null');
  if (typeof value.token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(value.token)) fail('Task&I descriptor token must be exactly 43 characters of A-Z a-z 0-9 _ -');
  // Effective task: VIBE_TASK_REF > .vibe/taskandi-task > root (null: the connection covers the whole workspace).
  let task = mappedTask(cwd, ref => descriptorTaskRef(ref, '.vibe/taskandi-task')) ?? value.root;
  if (process.env.VIBE_TASK_REF) task = descriptorTaskRef(process.env.VIBE_TASK_REF, 'VIBE_TASK_REF');
  const config = { bound: true, kind: HTTP_KIND, cwd, protocol: value.protocol, root: value.root, task, contractRevision: HTTP_CONTRACT_REVISION };
  // Secrets and identifiers stay off every printable surface: non-enumerable, so no JSON.stringify of a config shows them.
  const url = new URL(value.origin);
  const hidden = { origin: value.origin, originHost: `${url.protocol}//${url.hostname}`, connection: value.connection, workspace: value.workspace, token: value.token };
  for (const [key, item] of Object.entries(hidden)) Object.defineProperty(config, key, { value: item, enumerable: false });
  if (process.env.VIBE_TASK_BINDING && process.env.VIBE_TASK_BINDING !== bindingFingerprint(config)) fail('pinned task binding changed');
  return config;
}
function containerMode() { return process.env.VIBE_CONTAINER === '1' || (process.env.VIBE_CONTAINER !== '0' && existsSync('/.dockerenv')); }

function httpFailure(httpClass, wire, detail = '') {
  const printable = PRINTABLE_CODE.test(wire) ? wire : 'unknown_error';
  const lead = { unknown: 'Task&I outcome unknown', later: 'Task&I refused for now', rejected: 'Task&I refused', not_sent: 'Task&I request not sent' }[httpClass] ?? 'Task&I';
  const error = new Error(`${lead}: ${printable}${!detail ? '' : httpClass === 'not_sent' ? `; ${detail}` : ` (${detail})`}`);
  error.code = { unknown: 'OUTCOME_UNKNOWN', later: 'TRY_LATER', rejected: 'REFUSED', not_sent: 'NOT_SENT', open_children: 'OPEN_CHILDREN' }[httpClass];
  error.httpClass = httpClass; error.wire = printable;
  if (printable === 'connection_revoked') error.preface = [REVOKED];
  return error;
}
// The v2.2 transport. The connect target is the descriptor host, or for http://127.0.0.1:<P> in container mode host.docker.internal:<P>
// (IPv4 only: the firewall allows only the IPv4 host gateway) with Host kept as 127.0.0.1:<P>, which the service requires.
// `connect` is the createClient httpConnect test seam (127.0.0.1 or ::1, http origins only); it is never read from env or argv.
export function httpTransport({ origin, token, body, container = false, connect = null, timeoutMs = HTTP_LIMITS.timeoutMs }) {
  const url = new URL(origin); const secure = url.protocol === 'https:';
  if (connect && (secure || (connect.host !== '127.0.0.1' && connect.host !== '::1'))) fail('the httpConnect test seam takes 127.0.0.1 or ::1, and only for http origins');
  // A string body is sent byte for byte (a frozen v2.3 body); an object is serialized here.
  const payload = Buffer.from(typeof body === 'string' ? body : JSON.stringify(body), 'utf8');
  const common = { 'content-type': 'application/json', authorization: `Bearer ${token}`, 'content-length': payload.length, connection: 'close' };
  let options, where;
  if (secure) { options = { host: url.hostname, port: url.port || 443, rejectUnauthorized: true, headers: common }; where = ''; }
  else {
    const port = Number(url.port);
    const target = connect ?? (container ? { host: 'host.docker.internal', port } : { host: '127.0.0.1', port });
    options = { host: target.host, port: target.port, family: target.host === '::1' ? 6 : 4, setHost: false, headers: { host: `127.0.0.1:${port}`, ...common } };
    where = container && !connect ? ' (via host.docker.internal)' : ' (on this machine)';
  }
  return new Promise((resolvePromise, reject) => {
    let sent = false, settled = false;
    const req = (secure ? https : http).request({ ...options, method: 'POST', path: '/api/browser-agent', agent: false }, res => {
      const status = res.statusCode;
      if (status >= 300 && status < 400) return finish(httpFailure('unknown', 'redirect', 'redirects are refused'));
      const declared = res.headers['content-length'];
      if (declared !== undefined && !(Number(declared) <= HTTP_LIMITS.response)) return finish(httpFailure('unknown', 'response_too_large', 'over 16 MiB'));
      const chunks = []; let size = 0;
      res.on('data', chunk => { size += chunk.length; if (size > HTTP_LIMITS.response) return finish(httpFailure('unknown', 'response_too_large', 'over 16 MiB')); chunks.push(chunk); });
      res.on('end', () => finish(null, { status, body: Buffer.concat(chunks).toString('utf8') }));
      res.on('aborted', () => finish(httpFailure('unknown', 'connection_lost')));
      res.on('error', () => finish(httpFailure('unknown', 'connection_lost')));
    });
    // The one timeout: a hard timer over the whole exchange.
    const timer = setTimeout(() => finish(lost('timeout')), timeoutMs);
    function finish(error, value) {
      if (settled) return; settled = true; clearTimeout(timer);
      if (error) { req.destroy(); reject(error); } else resolvePromise(value);
    }
    // Connected (for https: the TLS handshake verified) counts as sent: from then on a failure leaves the outcome unknown.
    function lost(what) { return sent ? httpFailure('unknown', what) : httpFailure('not_sent', what === 'connection_lost' ? 'connect_failed' : what, `could not reach the Task&I service${where}`); }
    req.on('socket', socket => {
      if (secure) socket.once('secureConnect', () => { sent = true; });
      else if (!socket.connecting) sent = true; else socket.once('connect', () => { sent = true; });
    });
    req.on('error', () => finish(lost(sent ? 'connection_lost' : 'connect_failed')));
    req.end(payload);
  });
}
// A non-200 body is interpreted when it is a JSON object whose `error` is a string (any other key is ignored and never
// printed, except `children` of open_children, which is validated); 400/403/421 must carry their one code.
function interpretHttp(action, response, contract = HTTP_CONTRACT_REVISION) {
  const v23 = isV23(contract); const statuses = v23 ? ERROR_STATUS_V23 : ERROR_STATUS; const classes = v23 ? HTTP_ERRORS_V23 : HTTP_ERRORS;
  let parsed; try { parsed = JSON.parse(response.body); } catch { parsed = undefined; }
  if (response.status === 200) { if (!plainObject(parsed)) throw httpFailure('unknown', 'malformed_response', 'not a JSON object'); return parsed; }
  if (!Object.hasOwn(statuses, response.status)) throw httpFailure('unknown', 'unexpected_status', `HTTP ${response.status}`);
  const only = statuses[response.status];
  if (!plainObject(parsed) || typeof parsed.error !== 'string' || (only !== null && parsed.error !== only)) throw httpFailure('unknown', 'unrecognised_response', `HTTP ${response.status}`);
  if (response.status === 409 && action === 'complete' && parsed.error === 'open_children') {
    let value;
    try { value = conform(RESPONSE_SCHEMA.open_children, { children: parsed.children }, 'open_children', {}); }
    catch (error) { if (error.code === 'MALFORMED') throw httpFailure('unknown', 'unrecognised_response', 'HTTP 409'); throw error; }
    const error = httpFailure('open_children', 'open_children'); error.status = 409; error.children = value.children.map(({ task, title }) => ({ task, title })); throw error;
  }
  const printable = PRINTABLE_CODE.test(parsed.error) ? parsed.error : 'unknown_error';
  // v2.3: a 409 with a code this table does not know still applied nothing, so it is try-later rather than unknown.
  const error = httpFailure(Object.hasOwn(classes, printable) ? classes[printable] : v23 && response.status === 409 ? 'later' : 'unknown', printable);
  error.status = response.status;
  // create_task/update_task: an invalid_request may name the field at fault (`repeat`) or an unsupported one (v2.4's
  // `unsupported: "repeat"`); a printable field name is kept for lastError, anything else is dropped.
  if (printable === 'invalid_request' && isProposeKind(action)) {
    for (const name of ['repeat', 'unsupported']) if (typeof parsed[name] === 'string' && /^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(parsed[name])) { error.detail = `${name}: ${parsed[name]}`; break; }
  }
  throw error;
}
// AC29: on a v2.3 resend only these HTTP 409 codes prove nothing was ever applied. They come from inside the exchange
// transaction, after the replay lookup; every other answer to a resend (connection_revoked, connection_unavailable,
// 400/403/405/421, any other 409 code, any other status) is outcome unknown, because it may have been decided before
// the replay lookup and so says nothing about an earlier attempt.
const RESEND_PROOF_CODES = Object.freeze(['stale_context', 'sync_required', 'lease_held', 'use_native_connection', 'scope_missing', 'invalid_request', 'wrong_scope', 'wrong_thread', 'unknown_ask', 'not_assigned', 'open_children']);
const resendProof = error => error?.status === 409 && RESEND_PROOF_CODES.includes(error?.wire);

// Response schemas: every v2.2 response, including all next_task and list_asks rules, lives in this one constant.
// A string names a scalar check; obj(required, optional, rule) is an exact-key object; [s] an array of s.
const obj = (k, o = {}, rule = null) => ({ k, o, rule });
const nullable = schema => ({ nullable: schema });
const oneOf = (...values) => ({ oneOf: values });
const SPENT = obj({ windows: 'count', tokens: 'count' });
const CAPS_V22 = obj({ protocol: 'str', contract: 'str', grade: 'short', calls: ['str'] });
const RESPONSE_SCHEMA = Object.freeze({
  // A v2.3-family answer adds limits and id_pattern (checked in open()); any other answer has exactly the v2.2 keys.
  capabilities: { when: value => plainObject(value) && isV23(value.contract), then: obj({ protocol: 'str', contract: 'str', grade: 'short', calls: ['str'], limits: 'object', id_pattern: 'str' }), else: CAPS_V22 },
  next_task: { when: value => plainObject(value) && value.task === null, then: obj({ task: oneOf(null) }), else: obj({
    task: 'str', title: 'short', body: 'str', priority: nullable('int'), effective_priority: nullable('int'),
    allowance: nullable(obj({}, { windows: 'count', tokens: 'count' })), spent: SPENT, owner: 'short',
    lease: obj({ until: 'ms', session: 'id' }), defaults_allowed: 'bool',
  }, { hardDeadline: 'ms', estimate_minutes: 'count', latest_start: 'ms' }) },
  ask: obj({ ask_id: 'id', placed: oneOf('subtask', 'thread') }),
  list_asks: obj({ task: 'task', now: 'ms', asks: [obj({
    ask_id: 'id', task: 'task', question: 'str', default: 'str', subtask_id: nullable('str'), placed: oneOf('subtask', 'thread'),
    options: ['str'], order: 'count', estimate_minutes: 'count', remaining_minutes: 'count', reversible: 'bool', blocking: 'bool',
    in_reply_to: nullable('str'), agent: oneOf('claude', 'codex'), created_at: 'ms', seen_at: 'ms', answered_at: 'ms',
    answer: 'str', answered_by: 'short', owner_answer: 'bool',
  }, {}, ask => ((ask.placed === 'subtask') !== (ask.subtask_id !== null) ? 'subtask_id does not match placed' : codePoints(ask.answer) > HTTP_LIMITS.answer ? `answer over ${HTTP_LIMITS.answer} code points` : null))] },
  {}, (page, ctx) => (page.now < ctx.since ? 'now is before the requested since' : new Set(page.asks.map(ask => ask.ask_id)).size !== page.asks.length ? 'an ask_id repeats' : null)),
  ask_status: obj({ task: 'task', asks: [obj({ ask_id: 'id', seen_at: nullable('ms'), deferred: 'bool', answered: 'bool' })] }),
  comment: obj({ task: 'task', comment_id: 'id' }),
  record_usage: obj({ task: 'task', spent: SPENT }),
  record_time: obj({ entry_id: 'id', task: 'task', start: 'ms', end: 'ms', actor: oneOf('agent') }),
  complete: obj({ task: 'task', state: oneOf('provisional'), completion_id: 'id' }),
  release: obj({ task: 'task', released: oneOf(true), comment_id: 'id' }),
  open_children: obj({ children: { list: obj({ task: 'id', title: 'short' }), min: 1, max: 200 } }),
});
// v2.3 family: the responses that changed. next_task gains action, cache_read and fractional allowances, and with a
// requested task (ctx.requested) answers a claim or {task:null, reason}; list_asks is the seq cursor page.
export const CLAIM_REFUSALS = Object.freeze(['unsafe_id', 'not_assigned', 'closed', 'provisional', 'on_hold', 'blocked', 'open_children', 'waiting_on_ask', 'over_budget', 'leased']);
const SPENT_V23 = obj({ windows: 'count', tokens: 'count', cache_read: 'count' });
const ASK_V22 = RESPONSE_SCHEMA.list_asks.k.asks[0];
const RESPONSE_SCHEMA_V23 = Object.freeze({
  ...RESPONSE_SCHEMA,
  next_task: { when: value => plainObject(value) && value.task === null, then: obj({ task: oneOf(null) }, { reason: oneOf(...CLAIM_REFUSALS) }, (value, ctx) => (ctx.requested !== undefined && value.reason === undefined ? 'a claim refusal has no reason' : ctx.requested === undefined && value.reason !== undefined ? 'a reason without a requested task' : null)), else: obj({
    task: 'str', title: 'short', body: 'str', action: 'short', priority: nullable('int'), effective_priority: nullable('int'),
    allowance: nullable(obj({}, { windows: 'num', tokens: 'num' })), spent: SPENT_V23, owner: 'short',
    lease: obj({ until: 'ms', session: 'id' }), defaults_allowed: 'bool',
  }, { hardDeadline: 'ms', estimate_minutes: 'count', latest_start: 'ms' }) },
  list_asks: obj({ task: 'task', seq: 'count', asks: [obj({ ...ASK_V22.k, seq: 'pos' }, {}, ASK_V22.rule)] }, {}, (page, ctx) => {
    let last = ctx.since;
    for (const ask of page.asks) { if (ask.seq <= last) return ask.seq <= ctx.since ? 'an ask seq is not above since' : 'ask seqs do not strictly increase'; last = ask.seq; }
    if (page.seq !== last) return page.asks.length ? 'seq is not the last ask seq' : 'seq of an empty page is not since';
    return new Set(page.asks.map(ask => ask.ask_id)).size !== page.asks.length ? 'an ask_id repeats' : null;
  }),
  record_usage: obj({ task: 'task', spent: SPENT_V23 }),
  // v2.4+: exactly these keys; ids must be usable (a replay returns the original answer, so provisional is history).
  create_task: obj({ task_id: 'id', provisional: oneOf(true) }, {}, value => (USABLE_ID.test(value.task_id) ? null : 'task_id is not a usable id')),
  update_task: obj({ task: 'task', update_id: 'id' }, {}, value => (USABLE_ID.test(value.update_id) ? null : 'update_id is not a usable id')),
});
const schemaFor = (action, contract) => (isV23(contract) ? RESPONSE_SCHEMA_V23 : RESPONSE_SCHEMA)[action];
const SCALARS = Object.freeze({
  ms: value => Number.isSafeInteger(value) && value >= 0, count: value => Number.isSafeInteger(value) && value >= 0, int: value => Number.isSafeInteger(value),
  pos: value => Number.isSafeInteger(value) && value > 0, num: value => typeof value === 'number' && Number.isFinite(value) && value >= 0, object: value => plainObject(value),
  bool: value => typeof value === 'boolean', str: value => typeof value === 'string',
  short: value => typeof value === 'string' && codePoints(value) <= HTTP_LIMITS.shortText,
  id: value => typeof value === 'string' && value.length >= 1 && value.length <= HTTP_LIMITS.id && value.isWellFormed(),
  task: (value, ctx) => typeof value === 'string' && value === ctx.task,
});
// Messages name schema paths only, never a server-supplied key or value.
function conform(schema, value, path, ctx) {
  const bad = why => fail(`${path}: ${why}`, 'MALFORMED');
  if (typeof schema === 'string') { if (!SCALARS[schema](value, ctx)) bad(schema === 'task' ? 'does not echo the requested task' : schema === 'short' ? `is not a string of at most ${HTTP_LIMITS.shortText} code points` : `is not ${schema}`); return value; }
  if (Array.isArray(schema)) { if (!Array.isArray(value)) bad('is not an array'); value.forEach((item, i) => conform(schema[0], item, `${path}[${i}]`, ctx)); return value; }
  if (schema.when) return conform(schema.when(value) ? schema.then : schema.else, value, path, ctx);
  if (schema.nullable) return value === null ? null : conform(schema.nullable, value, path, ctx);
  if (schema.oneOf) { if (!schema.oneOf.includes(value)) bad('has an unexpected value'); return value; }
  if (schema.list) { if (!Array.isArray(value) || value.length < schema.min || value.length > schema.max) bad(`must hold ${schema.min}-${schema.max} items`); value.forEach((item, i) => conform(schema.list, item, `${path}[${i}]`, ctx)); return value; }
  if (!plainObject(value)) bad('is not an object');
  if (Object.keys(value).some(key => !Object.hasOwn(schema.k, key) && !Object.hasOwn(schema.o, key))) bad('has an unexpected key');
  for (const key of Object.keys(schema.k)) { if (!Object.hasOwn(value, key)) bad(`is missing ${key}`); conform(schema.k[key], value[key], `${path}.${key}`, ctx); }
  for (const key of Object.keys(schema.o)) if (Object.hasOwn(value, key)) conform(schema.o[key], value[key], `${path}.${key}`, ctx);
  const broken = schema.rule?.(value, ctx); if (broken) bad(broken);
  return value;
}

// Enqueue payload under a descriptor binding: limits are checked here, before anything is queued.
const HTTP_PAYLOAD_KEYS = Object.freeze({
  ask: ['question', 'default', 'options', 'order', 'estimate_minutes', 'remaining_minutes', 'reversible', 'blocking', 'in_reply_to', 'task'],
  comment: ['text', 'task'], record_time: ['seconds', 'started_at', 'task'],
  record_usage: ['account', 'model', 'input', 'output', 'cache_read', 'cache_write', 'cost_estimate', 'at', 'task'],
});
export function validateHttpPayload(kind, input, key, now = Date.now()) {
  input = ownObject(input, `${kind} payload`);
  for (const name of ['action', 'connection', 'agent', 'session']) if (Object.hasOwn(input, name)) fail(`${kind} payload must not set ${name}; the client supplies it`);
  if (!Object.hasOwn(HTTP_PAYLOAD_KEYS, kind)) fail(`unsupported enqueue kind ${kind}`);
  exactKeys(input, new Set(HTTP_PAYLOAD_KEYS[kind]), `${kind} payload`);
  if (kind === 'ask') {
    const out = { question: wireText(input.question, 'question', HTTP_LIMITS.question), default: wireText(input.default, 'default', HTTP_LIMITS.default), order: safeCount(input.order, 'order'), estimate_minutes: safeCount(input.estimate_minutes, 'estimate_minutes'), remaining_minutes: safeCount(input.remaining_minutes, 'remaining_minutes'), reversible: boolean(input.reversible, 'reversible'), blocking: input.blocking === undefined ? true : boolean(input.blocking, 'blocking') };
    if (input.options !== undefined) {
      if (!Array.isArray(input.options) || input.options.length > HTTP_LIMITS.options) fail(`options must be an array of at most ${HTTP_LIMITS.options} entries`);
      out.options = input.options.map((item, i) => wireText(item, `options[${i}]`, HTTP_LIMITS.option));
    }
    if (input.in_reply_to !== undefined) out.in_reply_to = wireId(input.in_reply_to, 'in_reply_to');
    // Placement (subtask or thread) cannot be predicted, so the composed thread post must fit too.
    const post = `Question: ${out.question}\nDefault: ${out.default}${out.options?.length ? `\nOptions: ${out.options.join(' / ')}` : ''}`;
    if (codePoints(post) > HTTP_LIMITS.post) fail(`ask would post more than ${HTTP_LIMITS.post} code points as a thread reply (Question, Default and Options lines together)`);
    return out;
  }
  if (kind === 'comment') return { text: wireText(input.text, 'text', HTTP_LIMITS.comment) };
  if (kind === 'record_time') {
    if (!Number.isSafeInteger(input.seconds) || input.seconds < 1 || input.seconds > HTTP_LIMITS.seconds) fail(`seconds must be an integer from 1 to ${HTTP_LIMITS.seconds}`);
    const startedAt = Date.parse(utcTimestamp(input.started_at, 'started_at'));
    if (startedAt + input.seconds * 1000 > now) fail('record_time must not end in the future');
    return { seconds: input.seconds, started_at: startedAt };
  }
  // at (ms since epoch, optional): when the usage happened. It is in the payload but not in the job's identity (jobDigest);
  // it is never sent to v2.2, and the first v2.3 dispatch drops it when over 29 days old or clamps it when in the future.
  const at = input.at === undefined ? {} : { at: safeCount(input.at, 'at') };
  return { model: wireId(input.model, 'model'), input: safeCount(input.input, 'input'), output: safeCount(input.output, 'output'), cache_read: safeCount(input.cache_read, 'cache_read'), cache_write: safeCount(input.cache_write, 'cache_write'), cost_estimate: safeCost(input.cost_estimate), windows: 0, account: wireId(input.account, 'account'), ...at, source: 'vibe', source_ref: wireId(stableKey(key), 'source_ref') };
}
// ---- v2.4/v2.5: create_task and update_task (task_067). Wire: the fixtures README "v2.4 changes", "v2.5 changes". ----
export const PROPOSE_KINDS = Object.freeze(['create_task', 'update_task']);
const isProposeKind = kind => PROPOSE_KINDS.includes(kind);
export const TASK_TEXT_LIMITS = Object.freeze({ title: 500, next_action: 2000, notes: 8000 });
const ESTIMATE_MAX = 1000000, MS_MAX = 253402300799999;
const CREATE_KEYS = ['title', 'estimate_minutes', 'assign', 'parent', 'next_action', 'notes', 'priority', 'hardDeadline', 'due', 'repeat'];
const UPDATE_FIELDS = ['title', 'next_action', 'notes', 'estimate_minutes', 'repeat'];
const RESERVED_KEYS = ['action', 'connection', 'agent', 'session', 'request_id'];
// The rank of a negotiated revision (v2.2 -> 2 ... v2.5 -> 5), and the rank a job needs: create/update need v2.4, repeat v2.5.
const contractRank = contract => { const at = HTTP_CONTRACT_REVISIONS.indexOf(contract); return at < 0 ? 0 : at + 2; };
const neededRank = job => (!isProposeKind(job.kind) ? 2 : plainObject(job.payload) && Object.hasOwn(job.payload, 'repeat') ? 5 : 4);
const NEEDS = rank => `needs_contract_v2.${rank}`;
function estimateMinutes(value) {
  if (!Number.isSafeInteger(value) || value < 1 || value > ESTIMATE_MAX) fail(`estimate_minutes must be an integer from 1 to ${ESTIMATE_MAX}`);
  return value;
}
function msField(value, name) {
  if (!Number.isSafeInteger(value) || value < 0 || value > MS_MAX) fail(`${name} must be an integer number of ms since the epoch, from 0 to ${MS_MAX}`);
  return value;
}
// The v2.5 repeat object, checked exactly and never filled in (the server fills every, starts, weekdays and monthDay at
// call time). Faults are named in contract field order, after any unknown key; the message is `invalid repeat: <field>`.
const REPEAT_KEYS = ['every', 'unit', 'weekdays', 'monthDay', 'nthWeekday', 'time', 'endTime', 'timeZone', 'starts', 'ends'];
const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const PRINTABLE_KEY = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const TZ_NAME = /^[A-Za-z][A-Za-z0-9_+-]*(\/[A-Za-z0-9_+-]+)*$/;
const intIn = (value, lo, hi) => typeof value === 'number' && Number.isInteger(value) && value >= lo && value <= hi;
function realDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const date = new Date(Date.UTC(2000, 0, 1)); date.setUTCFullYear(y, m - 1, d);
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}
const badRepeat = (field, why = '') => fail(`invalid repeat: ${field}${why ? ` (${why})` : ''}`, 'INVALID_REPEAT');
function timeZoneFault(value) {
  if (typeof value !== 'string') return 'not a string';
  if (value === 'UTC') return null;
  if (!TZ_NAME.test(value)) return 'an IANA time-zone name such as Europe/London; numeric offsets are refused';
  let resolved;
  try { resolved = new Intl.DateTimeFormat('en', { timeZone: value }).resolvedOptions().timeZone; }
  catch { return "unknown to this host's tzdata, which may be older than the server's"; }
  if (resolved !== value && resolved.toLowerCase() === value.toLowerCase()) return `write it exactly as ${resolved}`;
  return null;
}
export function validateRepeat(value) {
  if (!plainObject(value)) badRepeat('repeat', 'must be a JSON object');
  // An unknown key is named only when it is a plain identifier (terminal-safe); anything else is just `unknown key`.
  for (const key of Object.keys(value)) if (!REPEAT_KEYS.includes(key)) { if (PRINTABLE_KEY.test(key)) badRepeat(key, 'not a repeat field'); badRepeat('unknown key'); }
  const has = key => Object.hasOwn(value, key);
  if (has('every') && !intIn(value.every, 1, 1000)) badRepeat('every', 'an integer from 1 to 1000');
  if (!['day', 'week', 'month'].includes(value.unit)) badRepeat('unit', 'day, week or month');
  if (has('weekdays')) {
    const days = value.weekdays;
    if (value.unit !== 'week') badRepeat('weekdays', 'only with unit week');
    if (!Array.isArray(days) || days.length === 0 || days.some(day => !WEEKDAYS.includes(day)) || new Set(days).size !== days.length) badRepeat('weekdays', 'a non-empty list of distinct mon..sun');
  }
  if (has('monthDay')) {
    if (value.unit !== 'month') badRepeat('monthDay', 'only with unit month');
    if (has('nthWeekday')) badRepeat('monthDay', 'not together with nthWeekday');
    if (!(intIn(value.monthDay, 1, 31) || value.monthDay === -1)) badRepeat('monthDay', 'an integer from 1 to 31, or -1');
  }
  if (has('nthWeekday')) {
    const nth = value.nthWeekday;
    if (value.unit !== 'month') badRepeat('nthWeekday', 'only with unit month');
    if (!plainObject(nth) || Object.keys(nth).length !== 2 || !Object.hasOwn(nth, 'n') || !Object.hasOwn(nth, 'weekday') || ![1, 2, 3, 4, 5, -1].includes(nth.n) || !WEEKDAYS.includes(nth.weekday)) badRepeat('nthWeekday', 'exactly {n: 1..5 or -1, weekday: mon..sun}');
  }
  if (typeof value.time !== 'string' || !HHMM.test(value.time)) badRepeat('time', 'HH:MM, 24-hour');
  if (has('endTime') && (typeof value.endTime !== 'string' || !HHMM.test(value.endTime))) badRepeat('endTime', 'HH:MM, 24-hour');
  const zone = timeZoneFault(value.timeZone); if (zone) badRepeat('timeZone', zone);
  if (has('starts') && !realDate(value.starts)) badRepeat('starts', 'a real YYYY-MM-DD date');
  if (has('ends')) {
    const ends = value.ends;
    if (!plainObject(ends) || Object.keys(ends).length !== 1) badRepeat('ends', 'exactly one of {on} or {after}');
    if (Object.hasOwn(ends, 'on')) { if (!realDate(ends.on)) badRepeat('ends', 'on must be a real YYYY-MM-DD date'); if (has('starts') && ends.on < value.starts) badRepeat('ends', 'on is before starts'); }
    else if (Object.hasOwn(ends, 'after')) { if (!intIn(ends.after, 1, 1000)) badRepeat('ends', 'after must be an integer from 1 to 1000'); }
    else badRepeat('ends', 'exactly one of {on} or {after}');
  }
  return value;
}
// AC25: the content guard's BLOCK-tier secret patterns (devcontainer/git-hooks/vibe-content-scan.sh: github-pat,
// openai-key, aws-access-key, private-key), copied rather than shelled out to, plus gho_ OAuth tokens. A proposal's title,
// next_action or notes carrying one is refused at enqueue and nothing is queued.
export const SECRET_PATTERNS = Object.freeze([
  /ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}/,
  /sk-[A-Za-z0-9-]{20,}/,
  /AKIA[0-9A-Z]{16}/,
  /-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----/,
]);
function noSecret(value, name) {
  if (SECRET_PATTERNS.some(pattern => pattern.test(value))) fail(`contains_secret: ${name}`, 'SECRET');
  return value;
}
// The offline payload checks for create_task / update_task (no state): text is checked and sent untrimmed.
export function validateProposal(kind, input) {
  input = ownObject(input, `${kind} payload`);
  for (const name of RESERVED_KEYS) if (Object.hasOwn(input, name)) fail(`${kind} payload must not set ${name}; the client supplies it`);
  const textField = name => noSecret(wireText(input[name], name, TASK_TEXT_LIMITS[name]), name);
  if (kind === 'create_task') {
    exactKeys(input, new Set(CREATE_KEYS), 'create_task payload');
    for (const name of ['title', 'estimate_minutes', 'assign']) if (!Object.hasOwn(input, name)) fail(`create_task payload needs ${name}`);
    const out = {};
    for (const key of Object.keys(input)) {
      if (key === 'title' || key === 'next_action' || key === 'notes') out[key] = textField(key);
      else if (key === 'estimate_minutes') out[key] = estimateMinutes(input[key]);
      else if (key === 'assign') { if (input.assign !== 'owner' && input.assign !== 'agent') fail('assign must be exactly "owner" or "agent"'); out[key] = input.assign; }
      else if (key === 'priority') { if (!['now', 'next', 'later'].includes(input.priority)) fail('priority must be "now", "next" or "later" (words, not numbers)'); out[key] = input.priority; }
      else if (key === 'hardDeadline' || key === 'due') out[key] = msField(input[key], key);
      else if (key === 'parent') out[key] = normaliseTaskId(input.parent, 'parent');
      else if (key === 'repeat') out[key] = validateRepeat(input.repeat);
    }
    return out;
  }
  if (kind === 'update_task') {
    exactKeys(input, new Set(['task', ...UPDATE_FIELDS]), 'update_task payload');
    if (!Object.hasOwn(input, 'task')) fail('update_task payload needs task');
    if (!UPDATE_FIELDS.some(name => Object.hasOwn(input, name))) fail(`update_task payload needs at least one of ${UPDATE_FIELDS.join(', ')}`);
    const out = { task: normaliseTaskId(input.task, 'task') };
    for (const key of Object.keys(input)) {
      if (key === 'title' || key === 'next_action' || key === 'notes') out[key] = textField(key);
      else if (key === 'estimate_minutes') out[key] = estimateMinutes(input[key]);
      else if (key === 'repeat') out[key] = input.repeat === null ? null : validateRepeat(input.repeat);
    }
    return out;
  }
  fail(`unsupported enqueue kind ${kind}`);
}
// The created ledger's title key: lower-cased, whitespace collapsed, leading and trailing punctuation removed.
export function titleNorm(title) { return title.toLowerCase().replace(/\s+/gu, ' ').replace(/^[\p{P}\s]+|[\p{P}\s]+$/gu, ''); }
const DAY_MS = 24 * 60 * 60 * 1000;
const CREATED_MS = 180 * DAY_MS;
const CAPS = Object.freeze({ session: 3, day: 10, repeat: 3 });
const SELF_CREATED = 'vibe does not work tasks it proposed until the owner assigns it';
const RETRY_CREATE = 'retry sends this create_task again under a fresh request_id; if the first attempt was applied, the owner may now see two proposals';
// Both kinds exist only on the browser-agent API; the message names the kind asked for.
const PROPOSE_NEEDS_DESCRIPTOR = kind => `${kind} needs a Task&I descriptor binding`;
// A ledger entry with assign "agent" blocks next-task (an "owner" entry the owner reassigned to the agent does not).
const selfCreated = (state, task) => ledger(state, 'created').some(item => item.task_id === task && item.assign === 'agent');
// AC24: an offer whose title normalises to that of an `assign: "agent"` creation still in flight (queued, dispatching or
// uncertain, so its task id is not known yet) may be that very task, so it is treated as self-created too.
const selfCreatedTitle = (state, title) => typeof title === 'string' && createJobs(state).some(job => job.payload.assign === 'agent' && liveJob(job) && titleNorm(job.payload.title) === titleNorm(title));
const hasRepeat = payload => plainObject(payload) && plainObject(payload.repeat);
// The created ledger entry for a done create_task job (written in the same state write as `done`).
function createdEntry(job, taskId, at) {
  return { key: job.key, task_id: taskId, title: job.payload.title, titleNorm: titleNorm(job.payload.title), assign: job.payload.assign, parent: job.payload.parent ?? null, agent: job.agent === 'codex' ? 'codex' : 'claude', repeat: hasRepeat(job.payload), session: typeof job.sessionStamp === 'string' ? job.sessionStamp : null, at, gone: false };
}
function recordCreated(state, job, taskId, at, extra = {}) {
  state.created = [...ledger(state, 'created').filter(item => item.key !== job.key), { ...createdEntry(job, taskId, at), ...extra }];
}
function markGone(state, taskId) {
  let changed = false;
  for (const item of ledger(state, 'created')) if (item.task_id === taskId && item.gone !== true) { item.gone = true; changed = true; }
  return changed;
}
// ---- task_067 cycle 2: the local proposal rules (AC15-AC21, AC24) ----
// A ledger entry vibe may act on as its own proposal: present, not gone, and not written by reconcile (a reconciled
// entry never widens the update_task or next-task --task allowances, AC21).
const ownEntry = (state, task) => ledger(state, 'created').find(item => item.task_id === task && item.gone !== true && item.reconciled !== true);
const liveJob = job => job.state === 'queued' || job.state === 'dispatching' || job.state === 'uncertain';
const createJobs = state => state.jobs.filter(job => job.kind === 'create_task' && plainObject(job.payload) && typeof job.payload.title === 'string');
// Outstanding repeats (repeat_cap): ledger entries that repeat and are not gone, create jobs not yet in the ledger and not
// refused that carry one, and live update jobs that add a repeat to a task that has none (one per task). `key` is left out.
function outstandingRepeats(state, key) {
  const created = ledger(state, 'created'); const inLedger = new Set(created.map(item => item.key));
  const repeating = new Set(created.filter(item => item.repeat === true && item.gone !== true).map(item => item.task_id));
  const creates = createJobs(state).filter(job => job.key !== key && !inLedger.has(job.key) && job.state !== 'refused' && hasRepeat(job.payload)).length;
  const added = new Set(state.jobs.filter(job => job.kind === 'update_task' && job.key !== key && liveJob(job) && hasRepeat(job.payload) && typeof job.payload.task === 'string' && !repeating.has(job.payload.task)).map(job => job.payload.task));
  return created.filter(item => item.repeat === true && item.gone !== true).length + creates + added.size;
}
// The creations the caps count: every ledger entry, every create job not yet in the ledger and not refused, and every
// earlier attempt of a retried creation (AC20: a retry counts as a new creation). No stamp counts toward no session.
function countedCreations(state) {
  const created = ledger(state, 'created'); const inLedger = new Set(created.map(item => item.key));
  const stampOf = job => (typeof job.sessionStamp === 'string' ? job.sessionStamp : null);
  const out = created.map(item => ({ at: item.at, session: typeof item.session === 'string' ? item.session : null }));
  for (const job of createJobs(state)) {
    if (!inLedger.has(job.key) && job.state !== 'refused') out.push({ at: Number.isSafeInteger(job.createdAtMs) ? job.createdAtMs : Date.parse(job.createdAt), session: stampOf(job) });
    if (Array.isArray(job.priorAttempts)) for (const at of job.priorAttempts) if (Number.isSafeInteger(at)) out.push({ at, session: stampOf(job) });
  }
  return out;
}
// The create_task checks after dedupe and KEY_CONFLICT (also re-run by reconcile --action retry): duplicate_proposal
// (the ledger, gone entries included, and create jobs not in the ledger; never the job's own key or a refused job), then
// the per-session cap (only with a stamp), the rolling 24-hour cap and repeat_cap.
function creationChecks(state, { key, payload, stamp, at }) {
  const norm = titleNorm(payload.title); const parent = payload.parent ?? null;
  const created = ledger(state, 'created'); const inLedger = new Set(created.map(item => item.key));
  const same = created.find(item => item.key !== key && item.titleNorm === norm && (item.parent ?? null) === parent)
    ?? createJobs(state).find(job => job.key !== key && !inLedger.has(job.key) && job.state !== 'refused' && titleNorm(job.payload.title) === norm && (job.payload.parent ?? null) === parent);
  if (same) fail(`duplicate_proposal: ${same.task_id ? `task ${same.task_id} (key ${same.key})` : `key ${same.key}`} already proposes this title${parent ? ` under ${parent}` : ''}${same.gone === true ? '; the owner removed it' : ''}`, 'DUPLICATE');
  const counted = countedCreations(state);
  const oldest = list => new Date(Math.min(...list.map(item => item.at))).toISOString();
  if (stamp !== null) {
    const inSession = counted.filter(item => item.session === stamp);
    if (inSession.length >= CAPS.session) fail(`proposal_cap: at most ${CAPS.session} proposals per session (${stamp}); the oldest counted was at ${oldest(inSession)}`, 'CAP');
  }
  const inDay = counted.filter(item => Number.isSafeInteger(item.at) && at - item.at < DAY_MS);
  if (inDay.length >= CAPS.day) fail(`proposal_cap: at most ${CAPS.day} proposals in any 24 hours; the oldest counted was at ${oldest(inDay)}`, 'CAP');
  if (hasRepeat(payload) && outstandingRepeats(state, key) >= CAPS.repeat) fail(`repeat_cap: at most ${CAPS.repeat} outstanding repeating proposals`, 'CAP');
}
const OWNER_TASK_ONLY = "on the owner's task vibe may only change next_action";
// The update_task target rules (all local, zero requests), in order: not created yet; repeat only on vibe's own
// proposal; the target must be the claimed task or this persona's own entry; on the claimed task that is not vibe's own
// proposal only next_action; repeat_cap for an update that adds a repeat; one update job per target per session stamp.
function updateChecks(state, { key, payload, stamp, agent, claim }) {
  const target = payload.task; const created = ledger(state, 'created');
  const createJob = state.jobs.find(job => job.kind === 'create_task' && job.key === target);
  const entry = created.find(item => item.task_id === target);
  const entryJob = entry ? state.jobs.find(job => job.kind === 'create_task' && job.key === entry.key) : undefined;
  if ((createJob && createJob.state !== 'done' && !entry) || (entryJob && entryJob.state !== 'done')) fail('update_task: not created yet; flush, then read the task id from created', 'USAGE');
  const own = ownEntry(state, target);
  if (Object.hasOwn(payload, 'repeat') && !own) fail('update_task: repeat only on your own proposals', 'USAGE');
  const claimed = !!claim && claim.task === target;
  if (!claimed && !(own && own.agent === agent)) fail('update_task: not your task (only a task this persona proposed, or the claimed task)', 'USAGE');
  if (claimed && !own && Object.keys(payload).some(name => name !== 'task' && name !== 'next_action')) fail(`update_task: ${OWNER_TASK_ONLY}`, 'USAGE');
  if (hasRepeat(payload) && own.repeat !== true && outstandingRepeats(state, key) >= CAPS.repeat) fail(`repeat_cap: at most ${CAPS.repeat} outstanding repeating proposals`, 'CAP');
  if (stamp !== null && state.jobs.some(job => job.kind === 'update_task' && job.key !== key && job.state !== 'refused' && job.payload?.task === target && job.sessionStamp === stamp)) fail(`update_cap: at most one update per task per session (${target}, ${stamp})`, 'CAP');
}
// AC15: a done update_task on a ledger entry keeps the entry true, in the same state write as `done`.
function applyUpdate(state, job) {
  if (job.kind !== 'update_task' || !plainObject(job.payload)) return;
  for (const item of ledger(state, 'created')) {
    if (item.task_id !== job.payload.task) continue;
    if (typeof job.payload.title === 'string') { item.title = job.payload.title; item.titleNorm = titleNorm(job.payload.title); }
    if (Object.hasOwn(job.payload, 'repeat')) item.repeat = job.payload.repeat !== null;
  }
}
const WORST = 'x'.repeat(HTTP_LIMITS.id);
const textBytes = value => Buffer.byteLength(value, 'utf8');
// A request_id placeholder of the real length, for size checks made before one is chosen.
const SOME_REQUEST_ID = '00000000-0000-4000-8000-000000000000';
// The one claimed-task accessor (both binding kinds).
const claimOf = state => (plainObject(state.claimed) && typeof state.claimed.task === 'string' ? state.claimed : null);
// Target resolution: --task, else the claimed task, else the effective task.
function targetFrom(state, config, explicit, { claimOnly = false } = {}) {
  const claim = claimOf(state);
  const task = explicit ?? claim?.task ?? config.task;
  if (task === null || task === undefined) fail(NO_BOUND_TASK, 'USAGE');
  if (claimOnly && task !== claim?.task) fail(NEEDS_CLAIM, 'USAGE');
  if (explicit !== undefined && config.task !== null && explicit !== config.task && explicit !== claim?.task) fail('task is neither the bound task nor the claimed task', 'USAGE');
  return { task, claim, session: claim && claim.task === task && typeof claim.session === 'string' ? claim.session : undefined };
}
// Exact payload keys of each queued job kind, re-checked at dispatch (with the digest) so an edited state.json cannot send.
const JOB_SHAPES = Object.freeze({
  ask: [['task', 'question', 'default', 'order', 'estimate_minutes', 'remaining_minutes', 'reversible', 'blocking'], ['options', 'in_reply_to']],
  comment: [['task', 'text'], []],
  record_time: [['task', 'seconds', 'started_at'], []],
  record_usage: [['task', 'model', 'input', 'output', 'cache_read', 'cache_write', 'cost_estimate', 'windows', 'account', 'source', 'source_ref'], ['at']],
  create_task: [['title', 'estimate_minutes', 'assign'], ['parent', 'next_action', 'notes', 'priority', 'hardDeadline', 'due', 'repeat']],
  update_task: [['task'], ['title', 'next_action', 'notes', 'estimate_minutes', 'repeat']],
});
// A job's identity (the dedupe digest) under a descriptor binding. A usage row's `at` is not part of it: a re-import that
// derives `at` for a key queued without one (or with another) deduplicates, and the stored payload keeps the first `at`.
function jobDigest(kind, payload) {
  if (kind !== 'record_usage' || !Object.hasOwn(payload, 'at')) return digest({ kind, payload });
  const { at: _at, ...rest } = payload; return digest({ kind, payload: rest });
}
function jobIntact(job) {
  if (typeof job.kind !== 'string' || !Object.hasOwn(JOB_SHAPES, job.kind) || !plainObject(job.payload)) return false;
  const [required, optional] = JOB_SHAPES[job.kind];
  if (Object.keys(job.payload).some(key => !required.includes(key) && !optional.includes(key)) || required.some(key => !Object.hasOwn(job.payload, key))) return false;
  if (job.payload.at !== undefined && !Number.isSafeInteger(job.payload.at)) return false;
  return jobDigest(job.kind, job.payload) === job.digest;
}
// The wire fields of a queued job at dispatch: agent was resolved at enqueue, session comes from the current claim.
// `at` (record_usage) is never sent to v2.2.
function jobFields(job, claim, contract = HTTP_CONTRACT_REVISION) {
  const fields = { ...job.payload };
  if (!isV23(contract)) delete fields.at;
  if (job.kind === 'ask' || job.kind === 'comment' || isProposeKind(job.kind)) fields.agent = job.agent === 'codex' ? 'codex' : 'claude';
  // create_task carries the session whenever a claim exists (whatever its parent); every other kind only for the claimed task.
  // A create/update carries it only when the claim's agent is the job's persona (AC22): a session never vouches for another.
  const sameAgent = !isProposeKind(job.kind) || claim?.agent === (job.agent === 'codex' ? 'codex' : 'claude');
  if (claim && typeof claim.session === 'string' && sameAgent && (job.kind === 'create_task' || claim.task === job.payload.task)) fields.session = claim.session;
  return fields;
}
// ---- v2.3 family: frozen wire bodies, request_id and server limits ----
const AT_MAX_AGE = 29 * 24 * 60 * 60 * 1000, AT_MAX_AHEAD = 30 * 1000;
const DOWNGRADED = 'attempted on v2.3; the server now speaks v2.2, so a resend could duplicate';
const COLLIDED = 'receipt_collision on a resend: Task&I holds another body under this request_id, so the stored body was changed or mismatched; check Task&I, then reconcile --action done (never retried)';
// Task&I replays a request_id's original answer only for the same body from the same connection: a body frozen on a
// connection that has since been replaced (a re-grant) can never be resent safely.
const REPLAY_LOST = 'sent on a previous Task&I connection; replay is unavailable — check Task&I, then reconcile';
const RETRY_LOST = 'this sends a new write on the current connection; Task&I cannot tell it from the earlier one, so check it was not applied';
// The one wire-body builder (AC27): first sends, size checks and server-limit checks all use its {object, text}; a resend
// sends a stored text unchanged. request_id is added only on a v2.3-family write.
function wireBody(action, fields, connection, requestId) {
  const object = { ...fields, ...(requestId === undefined ? {} : { request_id: requestId }), action, connection };
  return { object, text: JSON.stringify(object) };
}
// A queued job's body for `contract`: fields, session resolved now, agent, request_id (v2.3), action and connection. On v2.3
// `at` older than 29 days is left out (with a notice when `notices` is given), more than 30 s ahead is clamped to now + 30 s.
function jobBody(job, claim, config, contract, at, notices = null) {
  const fields = jobFields(job, claim, contract);
  if (fields.at !== undefined) {
    if (fields.at < at - AT_MAX_AGE) { delete fields.at; notices?.push(`usage row ${job.key}: at older than 29 days, sent without it`); }
    else if (fields.at > at + AT_MAX_AHEAD) fields.at = at + AT_MAX_AHEAD;
  }
  return wireBody(job.kind, fields, config.connection, isV23(contract) ? job.requestId : undefined);
}
// The frozen-body fields of a job; cleared whenever an answer proves no attempt was applied (or the send never left).
const FROZEN = ['sentBody', 'sentSession', 'frozenAt'];
const unfreeze = job => { for (const name of FROZEN) delete job[name]; };
function frozenConnection(text) { try { const body = JSON.parse(text); return plainObject(body) && typeof body.connection === 'string' ? body.connection : null; } catch { return null; } }
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
// A stored sentBody must still be the job's payload plus the permitted extras, with the session recorded at freeze time,
// a known agent and an `at` inside the window applied at freeze time, so an edited state.json cannot send.
function sentBodyIntact(job) {
  if (job.sentBody === undefined) return true;
  if (typeof job.sentBody !== 'string' || !isV23(job.sentRevision) || typeof job.requestId !== 'string' || !UUID_V4.test(job.requestId)) return false;
  let body; try { body = JSON.parse(job.sentBody); } catch { return false; }
  if (!plainObject(body) || body.action !== job.kind || body.request_id !== job.requestId || typeof body.connection !== 'string') return false;
  const extras = ['action', 'connection', 'request_id', 'agent', 'session'];
  if (Object.keys(body).some(key => !extras.includes(key) && !Object.hasOwn(job.payload, key))) return false;
  if (Object.hasOwn(body, 'session') && (typeof job.sentSession !== 'string' || body.session !== job.sentSession)) return false;
  if (Object.hasOwn(body, 'agent') && body.agent !== 'claude' && body.agent !== 'codex') return false;
  for (const [key, value] of Object.entries(job.payload)) {
    if (key === 'at') {
      // Exactly what the window applied at freeze time gives: left out when too old, else the payload's at, clamped.
      if (!Number.isSafeInteger(job.frozenAt) || !Number.isSafeInteger(value)) return false;
      const expected = value < job.frozenAt - AT_MAX_AGE ? undefined : Math.min(value, job.frozenAt + AT_MAX_AHEAD);
      if (body.at !== expected) return false;
      continue;
    }
    if (canonical(body[key]) !== canonical(value)) return false;
  }
  return true;
}
// The server's published limits against a final body (code points for text, UTF-16 units for ids, bytes for the body).
// Returns the name of the first limit exceeded, or null. Enqueue already applied the client's own limits.
function overServerLimit(limits, action, body, bodyText) {
  if (!limits) return null;
  const cp = value => (typeof value === 'string' ? codePoints(value) : 0);
  if (Buffer.byteLength(bodyText, 'utf8') > limits.request_bytes) return 'request_bytes';
  for (const name of ['task', 'in_reply_to', 'parent']) if (typeof body[name] === 'string' && body[name].length > limits.id) return 'id';
  if (isProposeKind(action)) for (const name of ['title', 'next_action', 'notes']) if (Number.isSafeInteger(limits[name]) && cp(body[name]) > limits[name]) return name;
  if (action === 'ask') {
    if (cp(body.question) > limits.question) return 'question';
    if (cp(body.default) > limits.default) return 'default';
    const options = Array.isArray(body.options) ? body.options : [];
    if (options.length > limits.options) return 'options';
    if (options.some(option => cp(option) > limits.option)) return 'option';
    if (cp(`Question: ${body.question}\nDefault: ${body.default}${options.length ? `\nOptions: ${options.join(' / ')}` : ''}`) > limits.ask_post) return 'ask_post';
  }
  if (action === 'comment' && cp(body.text) > limits.comment) return 'comment';
  if (action === 'complete' && cp(body.summary) > limits.summary) return 'summary';
  if (action === 'release' && cp(body.reason) > limits.reason) return 'reason';
  return null;
}
// The limit keys a revision must publish: the twelve v2.3 keys, plus title, next_action and notes from v2.4 on.
export const SERVER_LIMIT_KEYS_V24 = Object.freeze([...SERVER_LIMIT_KEYS, 'title', 'next_action', 'notes']);
const limitKeysFor = contract => (contractRank(contract) >= 4 ? SERVER_LIMIT_KEYS_V24 : SERVER_LIMIT_KEYS);
function checkServerLimits(limits, contract = HTTP_CONTRACT_V23) {
  const keys = limitKeysFor(contract);
  if (!plainObject(limits)) return 'limits is not an object';
  for (const key of keys) if (!Object.hasOwn(limits, key)) return `limits is missing ${key}`;
  if (limits.unit !== 'code_points') return 'limits.unit is not code_points';
  if (limits.id_unit !== 'utf16_code_units') return 'limits.id_unit is not utf16_code_units';
  for (const key of keys) if (key !== 'unit' && key !== 'id_unit' && !(Number.isSafeInteger(limits[key]) && limits[key] > 0)) return `limits.${key} is not a positive integer`;
  return null;
}
// The revision a claim was made under (decide's token count follows it): claim.contract, else the last negotiated, else v2.2.
const claimContract = (state, claim) => (HTTP_CONTRACT_REVISIONS.includes(claim?.contract) ? claim.contract : HTTP_CONTRACT_REVISIONS.includes(state.lastContract) ? state.lastContract : HTTP_CONTRACT_REVISION);
// The revision whose counting rule produced claim.spent (next-task, a renewal, or a record_usage response), else as above.
const spentContractOf = (state, claim) => (HTTP_CONTRACT_REVISIONS.includes(claim?.spentContract) ? claim.spentContract : claimContract(state, claim));
const httpClassOf = error => (error?.code === 'TRY_LATER' || error?.code === 'NOT_SENT' ? 'later' : error?.code === 'REFUSED' ? 'rejected' : 'unknown');
function withNotices(result, notices) { Object.defineProperty(result, 'notices', { value: notices, enumerable: false }); return result; }
// complete/release: after the request may have been sent, an unknown outcome keeps the claim and says so.
function sentWriteFailure(error, v23 = false, force = false) {
  if (!force && httpClassOf(error) !== 'unknown') return error;
  const wrapped = new Error(`outcome unknown; ${v23 ? 'repeat the same command to resend it safely, or ' : ''}check the task in Task&I: ${error?.wire ?? 'unknown_error'}`); wrapped.code = 'OUTCOME_UNKNOWN'; wrapped.preface = error?.preface; return wrapped;
}
const DIRECT_CALLS = ['complete', 'release'];
// A complete/release whose outcome is unknown stays recorded in state.pendingDirect ({call, task, at: ms}) until
// reconcile --direct clears it. Only the same call on the same task is blocked by it; a record for a different call or
// task that arrives while one is held goes to state.pendingDirectMore, so no unknown outcome is ever overwritten.
const pendingList = state => [state.pendingDirect, ...(Array.isArray(state.pendingDirectMore) ? state.pendingDirectMore : [])].filter(item => item !== undefined);
const samePending = (item, call, task) => plainObject(item) && item.call === call && item.task === task;
function refusePendingDirect(state, call, task) {
  if (!pendingList(state).some(item => samePending(item, call, task))) return;
  fail(`an earlier ${call} for ${task} has an unknown outcome; check Task&I, then run reconcile --direct ${call} --task ${task} --action done|retry --evidence TEXT`, 'PENDING');
}
// A v2.3 record also carries {requestId, sentRevision, fieldsDigest, sentBody}: the same command (same task and text)
// resends sentBody byte for byte with that request_id instead of being blocked.
const isV23Pending = item => plainObject(item) && isV23(item.sentRevision) && typeof item.sentBody === 'string' && typeof item.requestId === 'string';
const directText = call => (call === 'complete' ? 'summary' : 'reason');
function samePendingText(item, call, task, value) {
  let body; try { body = JSON.parse(item.sentBody); } catch { return false; }
  return plainObject(body) && body.action === call && body.request_id === item.requestId && body.task === task && body[directText(call)] === value && item.fieldsDigest === digest({ task, [directText(call)]: value });
}
function addPendingDirect(state, call, task, extra = {}) {
  const record = { call, task, at: Date.now(), ...extra };
  if (state.pendingDirect === undefined) state.pendingDirect = record;
  else state.pendingDirectMore = [...(Array.isArray(state.pendingDirectMore) ? state.pendingDirectMore : []), record];
}
function clearPendingDirect(state, call, task) {
  const rest = pendingList(state).filter(item => !samePending(item, call, task));
  delete state.pendingDirect; delete state.pendingDirectMore;
  if (rest.length) state.pendingDirect = rest[0];
  if (rest.length > 1) state.pendingDirectMore = rest.slice(1);
}

// Parking ledger (task_065): one `parked` entry per task, written by a release that names --parked-asks/--budget-stopped
// in the same state write that drops the claim; cleared when the task completes or an ask on it is proceeded on.
// openAskIds is every open blocking ask on the task at that write (AC36), not the --parked-asks list itself.
function recordParked(state, task, park, at) {
  state.parked = [...ledger(state, 'parked').filter(item => item.task !== task), { task, openAskIds: openBlockingAskIds(state, task), budgetStopped: park.budgetStopped === true, allowance: park.allowance ?? null, at }];
}
function clearParked(state, task) { if (ledger(state, 'parked').some(item => item.task === task)) state.parked = state.parked.filter(item => item.task !== task); }
const parkFields = park => (park ? { parkedAsks: [...park.parkedAsks], budgetStopped: park.budgetStopped === true, allowance: park.allowance ?? null } : {});
const BODY_FILE = '.vibe/taskandi-body.txt';
// The full task body, owner-only and untracked, replaced on each claim (never through a symlink).
function writeBodyFile(cwd, body) {
  ensureBaseDir(join(cwd, '.vibe'));
  const path = join(cwd, BODY_FILE);
  if (trackedCaseInsensitive(cwd, path)) fail(`${BODY_FILE} must be untracked`);
  const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
  const fd = openSync(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { fchmodSync(fd, 0o600); writeFileSync(fd, body); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(tmp, path);
  return path;
}
// A next-task with no task removes a stale body file (the link itself if it is one; never what it points at). Only
// inside a real .vibe directory; a failure to remove it is ignored (the claim is already gone).
function removeBodyFile(cwd) {
  try { const dir = lstatSync(join(cwd, '.vibe')); if (!dir.isDirectory() || dir.isSymbolicLink()) return; unlinkSync(join(cwd, BODY_FILE)); } catch { /* nothing to remove */ }
}
const DECIDE_NEEDS_CLAIM = 'decide needs the claimed task; run next-task first';
const DECIDE_NEEDS_DESCRIPTOR = 'decide needs a Task&I descriptor binding';
const BUDGET_KNOB = 'VIBE_TASKANDI_BUDGET_ASK';
function budgetThreshold() {
  const raw = process.env[BUDGET_KNOB];
  if (raw === undefined) return 0.8;
  const value = Number(raw);
  if (!/^(?:\d+\.?\d*|\.\d+)$/.test(raw) || !(value > 0 && value < 1)) fail(`${BUDGET_KNOB} must be a decimal strictly between 0 and 1 (default 0.8)`);
  return value;
}
// Open asks on a task, as decide judges them: the open-ask predicate, minus the task's budget ask (judged by budget).
const openAskJobs = (state, task) => state.jobs.filter(job => job.key !== `budget-${task}` && isOpenAsk(state, job, task));
// The ask ids a park records: every open blocking ask on the task, whatever decide's action for it at park time.
const openBlockingAskIds = (state, task) => openAskJobs(state, task).filter(job => job.payload?.blocking !== false).map(job => job.result.ask_id);
// v2.2 counts cache_read against an allowance; the v2.3 family does not (tokens = input + output + cache_write).
const usageTokens = (payload, v23 = false) => payload.input + payload.output + (v23 ? 0 : payload.cache_read) + payload.cache_write;
const capOf = (allowance, key) => (!plainObject(allowance) || allowance[key] === undefined ? Infinity : allowance[key]);

function createHttpClient(cwd, httpConnect, now = Date.now) {
  const descriptorConfig = () => { const config = loadConfig(cwd); if (config.kind !== HTTP_KIND) fail('not a Task&I descriptor binding'); return config; };
  // Opens a session: exactly one capabilities request, gated on protocol, contract and the calls about to be made.
  // v2.4+ limits.title/next_action/notes are required only when a create_task/update_task job is about to be sent (AC23):
  // open() records a missing one as send.proposeLimitsFault, flush keeps such a job queued, and every other command
  // accepts a v2.4+ server without them.
  async function open(config, calls) {
    if (httpConnect && new URL(config.origin).protocol !== 'http:') fail('the httpConnect test seam is refused for https origins');
    // Until capabilities answers, the v2.2 rules apply (the capabilities request itself is the same in every revision).
    let contract = HTTP_CONTRACT_REVISION;
    // transmit sends a body string byte for byte (a body from wireBody, or a frozen one); send builds one with no request_id
    // (reads, and the capabilities request itself).
    const transmit = async (action, bodyText, ctx) => {
      if (textBytes(bodyText) > HTTP_LIMITS.body) { const error = httpFailure('rejected', 'body_too_large', `request body over ${HTTP_LIMITS.body} bytes`); error.notSent = true; throw error; }
      const response = await httpTransport({ origin: config.origin, token: config.token, body: bodyText, container: containerMode(), connect: httpConnect ? { host: httpConnect.host, port: httpConnect.port } : null, timeoutMs: httpConnect?.timeoutMs ?? HTTP_LIMITS.timeoutMs });
      const value = interpretHttp(action, response, contract);
      try { return conform(schemaFor(action, contract), value, action, ctx); } catch (error) { if (error.code === 'MALFORMED') throw httpFailure('unknown', 'malformed_response', error.message); throw error; }
    };
    const send = (action, fields, ctx) => transmit(action, wireBody(action, fields, config.connection).text, ctx);
    send.raw = transmit;
    const caps = await send('capabilities', {}, {});
    if (caps.protocol !== config.protocol) fail('Task&I capabilities: protocol does not match the descriptor', 'PREDISPATCH');
    if (!HTTP_CONTRACT_REVISIONS.includes(caps.contract)) fail(`Task&I capabilities: contract is not one of ${HTTP_CONTRACT_REVISIONS.join(', ')}`, 'PREDISPATCH');
    if (isV23(caps.contract)) {
      const broken = checkServerLimits(caps.limits, HTTP_CONTRACT_V23);
      if (broken) fail(`Task&I capabilities: ${broken}`, 'PREDISPATCH');
      send.proposeLimitsFault = contractRank(caps.contract) >= 4 ? checkServerLimits(caps.limits, caps.contract) : null;
      if (caps.id_pattern !== USABLE_ID.source) fail('Task&I capabilities: id_pattern differs from the task ids this client accepts', 'PREDISPATCH');
    }
    for (const call of calls) if (!caps.calls.includes(call)) fail(`Task&I capabilities do not offer ${call}`, 'PREDISPATCH');
    contract = caps.contract;
    // lastContract: every successful answer records the negotiated revision (absent only before the first call).
    await withState(cwd, now, async (state, statePath) => { state.lastGrade = caps.grade; state.lastContract = caps.contract; atomicJson(statePath, state); });
    send.calls = caps.calls; send.contract = caps.contract; send.v23 = isV23(caps.contract);
    send.limits = send.v23 ? Object.fromEntries(limitKeysFor(caps.contract).filter(key => Object.hasOwn(caps.limits, key)).map(key => [key, caps.limits[key]])) : null;
    send.rank = contractRank(caps.contract);
    return send;
  }
  const parseTask = task => (task === undefined ? undefined : descriptorTaskRef(task, '--task'));
  // Shared by complete/release: only the claiming session may send them; success clears the claim. pendingDirect is
  // written before the request and cleared on a definite answer, so an unknown outcome survives the process.
  // `park` ({parkedAsks, budgetStopped}, release only) also writes a `parked` entry with the claim's current allowance.
  // v2.3: a pending record from a v2.3 send is resent (same text, same connection) or refused (other text, or a body
  // frozen on a replaced connection, which Task&I cannot replay) instead of blocking; the order is: resolve the target and
  // check the pending record (each refusal sends nothing), then capabilities, then send.
  async function finish(action, task, extra, shape, park = null) {
    const config = descriptorConfig(); const explicit = parseTask(task); const value0 = extra[directText(action)];
    const target = await withState(cwd, now, async state => {
      const resolved = targetFrom(state, config, explicit, { claimOnly: true });
      const pending = pendingList(state).find(item => samePending(item, action, resolved.task));
      if (pending && !isV23Pending(pending)) refusePendingDirect(state, action, resolved.task);
      if (pending && !samePendingText(pending, action, resolved.task, value0)) fail(`an earlier ${action} for ${resolved.task} with different text has an unknown outcome; repeat it with the same text to resend it safely, or check Task&I and run reconcile --direct ${action} --task ${resolved.task} --action done|retry --evidence TEXT`, 'PENDING');
      return { ...resolved, pending: pending ? structuredClone(pending) : null };
    });
    const resend = target.pending !== null;
    if (resend && frozenConnection(target.pending.sentBody) !== config.connection) fail(`the earlier ${action} for ${target.task} was ${REPLAY_LOST} --direct ${action} --task ${target.task} --action done|retry --evidence TEXT`, 'PENDING');
    // A resend reuses the record's parking data rather than recomputing it.
    if (resend) park = Array.isArray(target.pending.parkedAsks) || target.pending.budgetStopped === true ? { parkedAsks: Array.isArray(target.pending.parkedAsks) ? target.pending.parkedAsks : [], budgetStopped: target.pending.budgetStopped === true, allowance: target.pending.allowance ?? null } : null;
    else if (park) park = { ...park, allowance: target.claim?.allowance ?? null };
    const fields = { task: target.task, ...extra, session: target.session };
    const tooBig = text => textBytes(text) > HTTP_LIMITS.body && fail(`${action} would exceed the ${HTTP_LIMITS.body}-byte request body limit`);
    if (!resend) tooBig(wireBody(action, fields, config.connection).text);
    const send = await open(config, [action]);
    if (resend && !send.v23) fail(`an earlier ${action} for ${target.task} was ${DOWNGRADED}; check Task&I, then run reconcile --direct ${action} --task ${target.task} --action done|retry --evidence TEXT`, 'PENDING');
    // A resend sends the stored body unchanged (the server decides; no limit is re-checked). A first send is built once,
    // with its request_id on v2.3, and checked for size and against the server's limits before anything is recorded.
    const body = resend ? { object: null, text: target.pending.sentBody } : wireBody(action, fields, config.connection, send.v23 ? randomUUID() : undefined);
    if (!resend) {
      tooBig(body.text);
      const over = send.v23 ? overServerLimit(send.limits, action, body.object, body.text) : null;
      if (over) fail(`${action} is over the Task&I server's ${over} limit (over_server_limit); nothing was sent`);
    }
    await withState(cwd, now, async (state, statePath) => {
      const current = pendingList(state).find(item => samePending(item, action, target.task));
      if (resend) { if (!current || current.requestId !== target.pending.requestId) fail(`the pending ${action} for ${target.task} changed while this ran; run it again`, 'PENDING'); return; }
      refusePendingDirect(state, action, target.task);
      const sent = send.v23 ? { requestId: body.object.request_id, sentRevision: send.contract, fieldsDigest: digest({ task: target.task, [directText(action)]: value0 }), sentBody: body.text } : {};
      addPendingDirect(state, action, target.task, { ...sent, ...parkFields(park) }); atomicJson(statePath, state);
    });
    const settle = clearClaim => withState(cwd, now, async (state, statePath) => {
      clearPendingDirect(state, action, target.task);
      if (clearClaim && claimOf(state)?.task === target.task) delete state.claimed;
      if (clearClaim && park) recordParked(state, target.task, park, now());
      if (clearClaim && action === 'complete') clearParked(state, target.task);
      atomicJson(statePath, state);
    });
    let value;
    try { value = await send.raw(action, body.text, { task: target.task }); }
    catch (error) {
      const notSent = error?.code === 'NOT_SENT' || error?.notSent === true;
      // AC29: on a v2.3 resend only an in-transaction 409 proof code settles the record (open_children is one: it is
      // decided after the replay lookup); any other answer (receipt_collision has its own message below) is outcome unknown.
      if (send.v23 && resend && !notSent && error?.wire !== 'receipt_collision' && !resendProof(error)) throw sentWriteFailure(error, true, true);
      if (error?.code === 'OPEN_CHILDREN') { await settle(false); return { bound: true, completed: false, open_children: error.children }; }
      // On a resend, receipt_collision means Task&I holds another body under this request_id: the pending record is kept.
      if (send.v23 && resend && error?.wire === 'receipt_collision') { const kept = new Error(`the earlier ${action} for ${target.task} may have been applied (receipt_collision on the resend: Task&I holds another body under its request_id); the pending record is kept: check Task&I, then run reconcile --direct ${action} --task ${target.task} --action done|retry --evidence TEXT`); kept.code = 'REFUSED'; throw kept; }
      // A definite answer (a proof code, on a resend) to the same connection proves nothing was applied (an applied first send would have been
      // replayed), so it settles the record; a resend that never left the client proves nothing, so the record stays.
      if (httpClassOf(error) !== 'unknown' && !(resend && notSent)) await settle(false);
      throw sentWriteFailure(error, send.v23);
    }
    await settle(true);
    return { bound: true, ...shape(value) };
  }
  // create_task / update_task enqueue (task_067): the offline payload checks (secrets included), then under the lock, in
  // this order (AC17): the idempotent re-enqueue (same key and digest), KEY_CONFLICT, and only then, for create_task,
  // duplicate_proposal and the caps; for update_task the local target rules and update_cap. A refused enqueue writes
  // nothing (and so counts toward no cap).
  async function enqueueProposals(kind, items, options, config) {
    if (options.task !== undefined) fail(`${kind} takes no --task (${kind === 'create_task' ? 'use parent in the payload' : 'name the task in the payload'})`, 'USAGE');
    const envStamp = process.env.VIBE_SESSION_STAMP ? stableKey(process.env.VIBE_SESSION_STAMP) : null;
    const prepared = items.map(({ key, input }) => ({ key: stableKey(key), payload: validateProposal(kind, input) }));
    return withState(cwd, now, async (state, statePath) => {
      const results = []; let changed = false; const at = now();
      for (const { key, payload } of prepared) {
        if (textBytes(wireBody(kind, { ...payload, agent: WORST, session: WORST }, WORST, SOME_REQUEST_ID).text) > HTTP_LIMITS.body) fail(`${kind} would exceed the ${HTTP_LIMITS.body}-byte request body limit`);
        const hash = jobDigest(kind, payload);
        const found = state.jobs.find(job => job.key === key) ?? tombstoneOf(state, key);
        if (found && found.digest === hash) { results.push({ enqueued: false, deduplicated: true, key, state: found.state ?? 'done', bound: true }); continue; }
        if (found) fail('same key was already used with a different payload (KEY_CONFLICT)', 'KEY_CONFLICT');
        const claim = claimOf(state);
        const envAgent = process.env.VIBE_AGENT === 'codex' || process.env.VIBE_AGENT === 'claude' ? process.env.VIBE_AGENT : 'claude';
        const claimAgent = claim && (claim.agent === 'claude' || claim.agent === 'codex') ? claim.agent : null;
        let agent, stamp;
        if (kind === 'create_task') {
          // The persona: the claim's (a create carries the claim's session), else VIBE_AGENT, else claude.
          agent = claimAgent ?? envAgent;
          stamp = options.session !== undefined ? stableKey(options.session) : envStamp;
          creationChecks(state, { key, payload, stamp, at });
        } else {
          const target = payload.task;
          // The stamp an update counts under: --session, else VIBE_SESSION_STAMP, else the claim's session.
          stamp = options.session !== undefined ? stableKey(options.session) : envStamp ?? (claim && typeof claim.session === 'string' ? claim.session : null);
          agent = claim && claim.task === target && claimAgent ? claimAgent : envAgent;
          updateChecks(state, { key, payload, stamp, agent, claim });
        }
        state.jobs.push({ key, kind, digest: hash, payload, agent, sessionStamp: stamp, createdAtMs: at, requestId: randomUUID(), binding: bindingDigest(config), channel: 'taskandi-http', state: 'queued', createdAt: new Date().toISOString() });
        changed = true; results.push({ enqueued: true, deduplicated: false, key, state: 'queued', bound: true });
      }
      if (changed) atomicJson(statePath, state);
      return results;
    });
  }
  // Enqueue under one lock: every item is validated first, and nothing is written unless all of them are accepted.
  async function enqueueAll(kind, items, options = {}) {
    const config = descriptorConfig();
    const optionTask = options.task !== undefined ? parseTask(options.task) : undefined;
    if (isProposeKind(kind)) return enqueueProposals(kind, items, options, config);
    const prepared = items.map(({ key, input }) => {
      key = stableKey(key); input = ownObject(input, `${kind} payload`);
      if (options.task !== undefined && input.task !== undefined) fail('task given both in the payload and as --task');
      const explicit = optionTask ?? (input.task !== undefined ? descriptorTaskRef(input.task, 'task') : undefined);
      return { key, explicit, fields: validateHttpPayload(kind, Object.fromEntries(Object.entries(input).filter(([name]) => name !== 'task')), key) };
    });
    return withState(cwd, now, async (state, statePath) => {
      const results = []; let changed = false;
      for (const { key, explicit, fields } of prepared) {
        const { task, claim } = targetFrom(state, config, explicit);
        const payload = { task, ...fields };
        if (textBytes(wireBody(kind, { ...payload, agent: WORST, session: WORST }, WORST, SOME_REQUEST_ID).text) > HTTP_LIMITS.body) fail(`${kind} would exceed the ${HTTP_LIMITS.body}-byte request body limit`);
        const hash = jobDigest(kind, payload);
        const found = state.jobs.find(job => job.key === key) ?? tombstoneOf(state, key);
        if (found) { if (found.digest !== hash) fail('same key was already used with a different payload (KEY_CONFLICT)', 'KEY_CONFLICT'); results.push({ enqueued: false, deduplicated: true, key, state: found.state ?? 'done', bound: true }); continue; }
        // agent: the claim's when this is the claimed task, else VIBE_AGENT, else claude. Kept outside payload and digest.
        const agent = kind === 'ask' || kind === 'comment' ? (claim && claim.task === task && (claim.agent === 'claude' || claim.agent === 'codex') ? claim.agent : process.env.VIBE_AGENT === 'codex' || process.env.VIBE_AGENT === 'claude' ? process.env.VIBE_AGENT : 'claude') : undefined;
        // requestId: the v2.3 request_id, generated once per intended write; outside payload and digest.
        state.jobs.push({ key, kind, digest: hash, payload, ...(agent ? { agent } : {}), requestId: randomUUID(), binding: bindingDigest(config), channel: 'taskandi-http', state: 'queued', createdAt: new Date().toISOString() });
        changed = true; results.push({ enqueued: true, deduplicated: false, key, state: 'queued', bound: true });
      }
      // `mark` (the usage importer's ledger update) lands in the same state write as the jobs it accounts for.
      if (options.mark) { options.mark(state); changed = true; }
      if (changed) atomicJson(statePath, state);
      return results;
    });
  }
  return {
    async resolveTask(task) {
      const config = descriptorConfig(); const explicit = parseTask(task);
      return withState(cwd, now, async state => targetFrom(state, config, explicit).task);
    },
    async enqueue(kind, key, input, options = {}) { return (await enqueueAll(kind, [{ key, input }], options))[0]; },
    enqueueAll,
    async flush() {
      const config = descriptorConfig(); const notices = [];
      const out = { bound: true, dispatched: 0, done: 0, uncertain: 0, refused: 0, requeued: 0 };
      const isQueued = job => job.state === 'queued' && job.channel !== 'file-fallback';
      const refuse = (job, code) => { job.state = 'refused'; job.refusedCode = code; job.lastError = `Task&I refused: ${code}`; out.refused++; notices.push(`${job.key}: Task&I refused: ${code}`); };
      const intact = job => jobIntact(job) && sentBodyIntact(job);
      // Before the revision is known the v2.2 body (the smaller) is measured; the exact body is measured again below.
      const sizeOf = (job, claim) => textBytes(typeof job.sentBody === 'string' ? job.sentBody : jobBody(job, claim, config, HTTP_CONTRACT_REVISION, now()).text);
      // A body frozen on a connection that has since been replaced cannot be replayed: uncertain, nothing sent (AC18).
      const replayLost = job => typeof job.sentBody === 'string' && frozenConnection(job.sentBody) !== config.connection;
      const loseReplay = job => { job.state = 'uncertain'; job.replayLost = true; job.lastError = REPLAY_LOST; out.uncertain++; notices.push(`${job.key}: ${REPLAY_LOST}`); };
      // Binding, job integrity and final body size are checked before any request, so a flush with nothing sendable sends nothing.
      const kinds = await withState(cwd, now, async (state, statePath) => {
        const queued = state.jobs.filter(isQueued);
        for (const job of queued) if (job.binding !== bindingDigest(config)) fail(`queued job binding changed; reconcile explicitly before delivery (${job.key})`, 'BINDING_CHANGED');
        let changed = false;
        for (const job of queued) {
          if (!intact(job)) { refuse(job, 'tampered_job'); changed = true; }
          else if (replayLost(job)) { loseReplay(job); changed = true; }
          else if (sizeOf(job, claimOf(state)) > HTTP_LIMITS.body) { refuse(job, 'body_too_large'); changed = true; }
        }
        if (changed) atomicJson(statePath, state);
        return [...new Set(state.jobs.filter(isQueued).map(job => job.kind))];
      });
      if (!kinds.length) return withNotices(out, notices);
      // create_task/update_task are gated per job below (task_067), so an older server never fails the whole flush.
      const send = await open(config, kinds.filter(kind => !isProposeKind(kind))); const { contract, v23 } = send;
      const offered = job => send.rank >= neededRank(job) && send.calls.includes(job.kind);
      return withState(cwd, now, async (state, statePath) => {
        for (const job of state.jobs.filter(isQueued)) {
          if (job.binding !== bindingDigest(config)) fail(`queued job binding changed; reconcile explicitly before delivery (${job.key})`, 'BINDING_CHANGED');
          if (!intact(job)) { refuse(job, 'tampered_job'); atomicJson(statePath, state); continue; }
          if (replayLost(job)) { loseReplay(job); atomicJson(statePath, state); continue; }
          // Downgrade: a job attempted on v2.3 may have been applied; a v2.2 server cannot deduplicate a resend.
          if (!v23 && job.sentBody !== undefined) { job.state = 'uncertain'; job.lastError = DOWNGRADED; out.uncertain++; notices.push(`${job.key}: ${DOWNGRADED}`); atomicJson(statePath, state); continue; }
          if (isProposeKind(job.kind) && !offered(job)) {
            // Sent before to a newer server: this one cannot replay it, so a resend could duplicate. Never sent: it waits,
            // queued, for a server that speaks the revision it needs.
            if (job.sentBody !== undefined) { const why = `attempted on ${job.sentRevision}; the server now speaks ${contract}, which cannot replay it, so a resend could duplicate`; job.state = 'uncertain'; job.lastError = why; out.uncertain++; notices.push(`${job.key}: ${why}`); atomicJson(statePath, state); continue; }
            const need = NEEDS(neededRank(job));
            if (job.lastError !== need) { job.lastError = need; atomicJson(statePath, state); }
            notices.push(`${job.key}: ${need} (the server speaks ${contract}); kept queued, nothing sent`); continue;
          }
          // AC23: a server that does not publish the proposal limits gets no first send of a proposal; it waits, queued.
          if (isProposeKind(job.kind) && job.sentBody === undefined && send.proposeLimitsFault) {
            const why = `Task&I capabilities: ${send.proposeLimitsFault}`;
            if (job.lastError !== why) { job.lastError = why; atomicJson(statePath, state); }
            notices.push(`${job.key}: ${why}; kept queued, nothing sent`); continue;
          }
          const claim = claimOf(state); const resend = job.sentBody !== undefined;
          let bodyText;
          // A resend sends sentBody byte for byte; it may have been applied, so no limit is re-checked: the server decides.
          if (resend) bodyText = job.sentBody;
          else {
            // Jobs queued before request_id existed get one now, frozen with the body.
            if (v23 && !(typeof job.requestId === 'string' && UUID_V4.test(job.requestId))) job.requestId = randomUUID();
            const frozenAt = now(); const atNotices = [];
            const body = jobBody(job, claim, config, contract, frozenAt, atNotices);
            // The exact body, request_id and at included, is measured here; an oversized or over-limit body is never frozen.
            if (textBytes(body.text) > HTTP_LIMITS.body) { refuse(job, 'body_too_large'); atomicJson(statePath, state); continue; }
            const over = v23 ? overServerLimit(send.limits, job.kind, body.object, body.text) : null;
            if (over) { refuse(job, 'over_server_limit'); job.lastError += ` (server limit ${over})`; atomicJson(statePath, state); continue; }
            notices.push(...atNotices);
            if (v23) Object.assign(job, { sentBody: body.text, sentSession: typeof body.object.session === 'string' ? body.object.session : null, frozenAt });
            job.sentRevision = contract; bodyText = body.text;
          }
          job.state = 'dispatching'; job.dispatchedAt = new Date().toISOString(); atomicJson(statePath, state); out.dispatched++;
          try {
            job.result = await send.raw(job.kind, bodyText, { task: job.payload.task });
            // AC24: a created task_id that is already known (a ledger id, the claimed or the effective task) is malformed.
            if (job.kind === 'create_task') {
              const id = job.result.task_id;
              if (ledger(state, 'created').some(item => item.key !== job.key && item.task_id === id) || id === claimOf(state)?.task || id === config.task) { delete job.result; throw httpFailure('unknown', 'malformed_response', 'task_id names a task that already exists'); }
            }
            const at = now(); job.state = 'done'; job.doneAt = new Date(at).toISOString(); job.doneAtMs = at; delete job.lastError; out.done++;
            // The latest spent on the claimed task: every record_usage response carries the server's roll-up, counted the
            // way this revision counts it (spentContract).
            const current = claimOf(state);
            if (job.kind === 'record_usage' && current && job.result.task === current.task) { current.spent = { ...job.result.spent }; current.spentContract = contract; current.spentAt = at; }
            // The created ledger entry lands in the same state write as `done`.
            if (job.kind === 'create_task') recordCreated(state, job, job.result.task_id, at);
            applyUpdate(state, job);
            atomicJson(statePath, state);
          } catch (error) {
            const notSent = error?.code === 'NOT_SENT' || error?.notSent === true;
            // AC29: an answer to a resend proves nothing unless it is an in-transaction 409 proof code.
            const unknownResend = v23 && resend && !notSent && error?.wire !== 'receipt_collision' && !resendProof(error);
            const httpClass = unknownResend ? 'unknown' : httpClassOf(error);
            if (notSent) out.dispatched--;
            if (v23 && !notSent && error?.wire === 'receipt_collision') {
              // First send: the request_id is already taken and nothing was applied; a fresh one is issued. Resend: Task&I
              // holds another body under it, which only a changed or mismatched stored body explains.
              if (!resend) { unfreeze(job); job.requestId = randomUUID(); refuse(job, 'receipt_collision'); atomicJson(statePath, state); continue; }
              job.state = 'uncertain'; job.noRetry = true; job.lastError = COLLIDED; out.uncertain++;
              notices.push(`${job.key}: ${COLLIDED}`); atomicJson(statePath, state); break;
            }
            // A definite answer (on a resend, only a proof code) from the same connection proves no attempt was applied (an
            // applied one would have been replayed), so the frozen body is dropped and the next attempt is rebuilt with the same request_id. A send
            // that never left the client freezes nothing, but a resend's earlier attempts may still apply: keep its body.
            if (v23 && httpClass !== 'unknown' && !(notSent && resend)) unfreeze(job);
            // create_task/update_task: a 200 that is not exactly the documented result may still have created or changed
            // the task, and a resend would only replay it, so it is uncertain at once.
            if (isProposeKind(job.kind) && error?.wire === 'malformed_response') {
              job.state = 'uncertain'; job.lastError = `Task&I answered ${job.kind} with an unexpected result (${error.message}); the ${job.kind === 'create_task' ? 'task may exist' : 'update may be applied'}: check Task&I, then reconcile${job.kind === 'create_task' ? ' (--action done --task-id <id>)' : ''}`;
              out.uncertain++; notices.push(`${job.key}: ${job.lastError}`); atomicJson(statePath, state); break;
            }
            if (httpClass === 'rejected') {
              refuse(job, error.wire);
              if (error.detail) { job.lastError += ` (${error.detail})`; notices[notices.length - 1] += ` (${error.detail})`; }
              // wrong_scope: the task (an update's target, or a create's ledger parent) is gone for this agent.
              if (error.wire === 'wrong_scope') { const gone = job.kind === 'update_task' ? job.payload.task : job.kind === 'create_task' ? job.payload.parent : undefined; if (typeof gone === 'string') markGone(state, gone); }
              atomicJson(statePath, state); continue;
            }
            if (httpClass === 'later') { job.state = 'queued'; job.lastError = error.message; out.requeued++; notices.push(...(error?.preface ?? []), `${job.key}: ${error.message}`); atomicJson(statePath, state); break; }
            const detail = !error?.wire ? 'unexpected client error' : unknownResend && error.httpClass !== 'unknown' ? `Task&I outcome unknown on a resend: ${error.wire}${error.status ? ` (HTTP ${error.status})` : ''}` : error.message;
            if (v23) {
              // Safe to resend: the next v2.3 flush sends sentBody again with the same request_id, up to MAX_ATTEMPTS.
              job.attempts = (Number.isSafeInteger(job.attempts) ? job.attempts : 0) + 1;
              if (job.attempts >= MAX_ATTEMPTS) { job.state = 'uncertain'; job.lastError = `outcome unknown after ${MAX_ATTEMPTS} attempts; reconcile explicitly: ${detail}`; out.uncertain++; }
              else { job.state = 'queued'; job.lastError = `outcome unknown; the next flush resends the same body and request_id: ${detail}`; out.requeued++; }
              notices.push(...(error?.preface ?? []), `${job.key}: ${job.lastError}`); atomicJson(statePath, state); break;
            }
            // No v2.2 write is idempotent: an uncertain job is never retried automatically.
            job.state = 'uncertain'; job.lastError = `outcome unknown; reconcile explicitly: ${detail}`; out.uncertain++;
            notices.push(...(error?.preface ?? []), `${job.key}: ${job.lastError}`); atomicJson(statePath, state); break;
          }
        }
        return withNotices(out, notices);
      });
    },
    // next-task --task REF (v2.3 family): claim that task or print the server's refusal reason. REF must be the
    // effective or the claimed task, or, on a whole-workspace connection (no effective task), any usable id (usage error,
    // no request, otherwise). A v2.2 server cannot claim a named task.
    async nextTask({ agent, session, bodyMaxChars = 20000, task: requested }) {
      const config = descriptorConfig();
      if (!Number.isSafeInteger(bodyMaxChars) || bodyMaxChars < 0) fail('--body-max-chars must be a nonnegative integer');
      let claimedBefore = null;
      if (requested !== undefined) {
        requested = parseTask(requested);
        const found = await withState(cwd, now, async state => {
          const claimed = claimOf(state)?.task ?? null;
          if (selfCreated(state, requested)) return { claimed, self: true };
          // A task vibe proposed (a non-gone ledger entry, owner-assigned; never a reconciled one) may be named too: once
          // the owner reassigns it to the agent, that is how vibe is asked to work it.
          const proposed = !!ownEntry(state, requested);
          if (config.task !== null && requested !== config.task && requested !== claimed && !proposed) fail('--task is neither the effective task nor the claimed task', 'USAGE');
          return { claimed, self: false };
        });
        // A task vibe proposed for its own queue is not worked until the owner assigns it (T94 default): no claim is sent.
        if (found.self) return { bound: true, channel: 'taskandi-http', task: null, reason: 'self_created' };
        claimedBefore = found.claimed;
      }
      const send = await open(config, ['next_task']);
      if (requested !== undefined && !send.v23) return { bound: true, channel: 'taskandi-http', task: null, reason: 'contract_v2_2' };
      // A lease the client will not keep goes straight back rather than being held for 90 minutes.
      const handBack = async (id, reason, message) => {
        const error = new Error(message); error.code = 'INVALID';
        try {
          if (!send.calls.includes('release')) throw httpFailure('not_sent', 'release_not_offered');
          const fields = { task: id, reason, session };
          await send.raw('release', wireBody('release', fields, config.connection, send.v23 ? randomUUID() : undefined).text, { task: id });
        } catch (failure) {
          error.preface = [`could not release the lease on the ${message === UNUSABLE_TASK ? 'unusable' : 'returned'} task (${failure?.wire ?? 'unexpected client error'}); it lapses on its own`];
        }
        throw error;
      };
      const task = await send('next_task', { agent, session, ...(requested !== undefined ? { task: requested } : {}) }, requested !== undefined ? { requested } : {});
      // A refusal of the requested task: the claim (on any task) and the body file stay exactly as they were.
      if (task.task === null && task.reason !== undefined) return { bound: true, channel: 'taskandi-http', task: null, reason: task.reason };
      // The server answered with this client's own current claim: that lease is ours, so it is not handed back.
      if (requested !== undefined && task.task !== null && task.task !== requested && task.task === claimedBefore) fail('the server returned your current claim instead');
      if (requested !== undefined && task.task !== null && task.task !== requested) await handBack(task.task, 'vibe asked for another task', 'Task&I answered with another task than the one requested; it was released and nothing was claimed');
      // A-mode offer of a task vibe proposed for its own queue: hand the lease back and claim nothing (the stored claim and
      // the body file stay as they were).
      if (requested === undefined && task.task !== null && await withState(cwd, now, async state => selfCreated(state, task.task) || selfCreatedTitle(state, task.title))) {
        const notices = [];
        try {
          if (!send.calls.includes('release')) throw httpFailure('not_sent', 'release_not_offered');
          await send.raw('release', wireBody('release', { task: task.task, reason: SELF_CREATED, session }, config.connection, send.v23 ? randomUUID() : undefined).text, { task: task.task });
        } catch (failure) { notices.push(`could not release the lease on the self-created task (${failure?.wire ?? 'unexpected client error'}); it lapses on its own`); }
        return withNotices({ bound: true, channel: 'taskandi-http', task: null, reason: 'self_created' }, notices);
      }
      if (task.task !== null && !USABLE_ID.test(task.task)) await handBack(task.task, 'Task id not usable by vibe; rename it in Task&I.', UNUSABLE_TASK);
      // The claim is stored before the body file is written (AC39): a body-file failure never loses the lease.
      await withState(cwd, now, async (state, statePath) => {
        if (task.task === null) { delete state.claimed; atomicJson(statePath, state); return; }
        // A renewal of the same task keeps the first claim's time; spent takes, per dimension, the larger of the stored
        // and the returned value (spent only grows, so the larger is the newer), and spentAt becomes the renewal time.
        // spentContract records the revision whose counting rule produced spent (v2.2 and v2.3 count tokens differently):
        // the merge only compares like with like, and a stored spent counted the other way is replaced.
        const prior = claimOf(state); const at = now();
        const renewal = prior && prior.task === task.task && Number.isSafeInteger(prior.claimedAtMs) ? prior : null;
        const claimedAtMs = renewal ? renewal.claimedAtMs : at;
        const spent = { ...task.spent };
        const sameCount = renewal && isV23(spentContractOf(state, renewal)) === send.v23;
        if (sameCount && plainObject(renewal.spent)) for (const [name, value] of Object.entries(renewal.spent)) if (Number.isSafeInteger(value) && !(value <= spent[name])) spent[name] = value;
        state.claimed = { task: task.task, agent, session, contract: send.contract, lease: { ...task.lease }, claimedAt: new Date(at).toISOString(), claimedAtMs, allowance: task.allowance === null ? null : { ...task.allowance }, spent, spentContract: send.contract, spentAt: at, defaults_allowed: task.defaults_allowed };
        for (const name of ['hardDeadline', 'latest_start', 'estimate_minutes']) if (task[name] !== undefined) state.claimed[name] = task[name];
        atomicJson(statePath, state);
      });
      if (task.task === null) { removeBodyFile(cwd); return { bound: true, channel: 'taskandi-http', task: null }; }
      let bodyFile = null, bodyFileError = null;
      try { bodyFile = writeBodyFile(cwd, task.body); } catch (error) { bodyFileError = String(error?.message ?? error); }
      const failed = bodyFileError === null ? {} : { body_file: null, body_file_error: bodyFileError };
      const chars = codePoints(task.body);
      if (chars <= bodyMaxChars) return { bound: true, channel: 'taskandi-http', task: { ...task, ...failed } };
      return { bound: true, channel: 'taskandi-http', task: { ...task, body: [...task.body].slice(0, bodyMaxChars).join(''), body_truncated: true, body_chars: chars, body_file: bodyFile, ...failed } };
    },
    async complete(task, summary) {
      wireText(summary, 'summary', HTTP_LIMITS.summary);
      return finish('complete', task, { summary }, value => ({ completed: true, state: 'provisional', completion_id: value.completion_id }));
    },
    async release(task, reason, { parkedAsks, budgetStopped = false } = {}) {
      wireText(reason, 'reason', HTTP_LIMITS.reason);
      const park = parkedAsks !== undefined || budgetStopped ? { parkedAsks: parkedAsks ?? [], budgetStopped } : null;
      return finish('release', task, { reason }, value => ({ released: true, comment_id: value.comment_id }), park);
    },
    async reconcileDirect(call, task, action, evidence) {
      if (!DIRECT_CALLS.includes(call)) fail('reconcile --direct takes complete or release');
      task = descriptorTaskRef(task, '--task');
      if (!['done', 'retry'].includes(action)) fail('reconcile action must be done or retry'); text(evidence, 'evidence', LIMITS.text);
      return withState(cwd, now, async (state, statePath) => {
        const record = pendingList(state).find(item => samePending(item, call, task));
        if (!record) fail(`no earlier ${call} for ${task} has an unknown outcome`);
        // done: the call was applied, so its claim is spent; retry: one more send is allowed.
        clearPendingDirect(state, call, task);
        if (action === 'done' && claimOf(state)?.task === task) delete state.claimed;
        if (action === 'done' && call === 'release' && (Array.isArray(record.parkedAsks) || record.budgetStopped === true)) recordParked(state, task, { parkedAsks: Array.isArray(record.parkedAsks) ? record.parkedAsks : [], budgetStopped: record.budgetStopped === true, allowance: record.allowance ?? null }, now());
        if (action === 'done' && call === 'complete') clearParked(state, task);
        state.reconciliationLog.push({ direct: call, task, action, evidence, at: new Date().toISOString() }); atomicJson(statePath, state);
        return { direct: call, task, action, reconciled: true };
      });
    },
    async poll({ task } = {}) {
      const config = descriptorConfig(); const explicit = parseTask(task);
      // The stored per-task cursor is {now} (v2.2) or {seq} (v2.3 family); each revision ignores the other's and starts over
      // (since 0 on v2.3), and the (task, ask_id) dedupe absorbs the repeats.
      const target = await withState(cwd, now, async state => {
        const resolved = targetFrom(state, config, explicit); bindAnswers(state, config, false);
        return { ...resolved, stored: canonical(state.cursors?.[resolved.task] ?? null), priorNow: state.cursors?.[resolved.task]?.now ?? null, priorSeq: state.cursors?.[resolved.task]?.seq ?? null };
      });
      const send = await open(config, ['list_asks']);
      // v2.2: `now` is wall-clock and the server filters answered_at > since, so re-read a 2 s overlap. v2.3: since is the
      // stored seq exactly.
      const since = send.v23 ? (Number.isSafeInteger(target.priorSeq) && target.priorSeq >= 0 ? target.priorSeq : 0) : target.priorNow === null ? 0 : Math.max(0, target.priorNow - 2000);
      const page = await send('list_asks', { task: target.task, since, ...(target.session ? { session: target.session } : {}) }, { task: target.task, since });
      const cursor = send.v23 ? { seq: page.seq } : { now: page.now };
      return withState(cwd, now, async (state, statePath) => {
        bindAnswers(state, config);
        state.cursors ??= {};
        if (canonical(state.cursors[target.task] ?? null) !== target.stored) fail('poll cursor changed concurrently; response was not applied');
        const added = [], changed = []; let ignored = 0;
        for (const ask of page.asks) {
          const existing = state.answers.find(item => item.task === target.task && item.id === ask.ask_id);
          if (!existing) {
            state.answers.push({ task: target.task, id: ask.ask_id, content: ask.answer, ownerAnswer: ask.owner_answer, seenAt: ask.seen_at, answeredAt: ask.answered_at, answeredBy: ask.answered_by, receivedAt: new Date().toISOString() });
            if (ask.owner_answer) added.push({ ask_id: ask.ask_id, answer: ask.answer, seen_at: ask.seen_at, answered_at: ask.answered_at }); else ignored++;
          } else if (existing.content !== ask.answer) {
            const priorDigest = digest(existing.content), newDigest = digest(ask.answer);
            if (!state.conflicts.some(item => item.task === target.task && item.id === ask.ask_id && item.priorDigest === priorDigest && item.newDigest === newDigest)) { state.conflicts.push({ task: target.task, id: ask.ask_id, priorDigest, newDigest, content: ask.answer, detectedAt: new Date().toISOString() }); changed.push(ask.ask_id); }
          }
        }
        atomicJson(statePath, state); // answers are durable before the cursor advances
        state.cursors[target.task] = cursor;
        // Polls per task, so decide can tell "answered, not yet polled" from "polled since, still no owner answer".
        state.polls = { ...(state.polls ?? {}), [target.task]: (Number.isSafeInteger(state.polls?.[target.task]) ? state.polls[target.task] : 0) + 1 };
        atomicJson(statePath, state);
        return { bound: true, channel: 'taskandi-http', task: target.task, newAnswers: added.length, answers: added, ignored, conflicts: changed, cursor };
      });
    },
    async askStatus({ task } = {}) {
      const config = descriptorConfig(); const explicit = parseTask(task);
      const target = await withState(cwd, now, async state => targetFrom(state, config, explicit));
      const send = await open(config, ['ask_status']);
      const value = await send('ask_status', { task: target.task, ...(target.session ? { session: target.session } : {}) }, { task: target.task });
      return { bound: true, channel: 'taskandi-http', task: target.task, asks: value.asks };
    },
    // decide (task_065): judges the claimed task's open asks and budget. No request unless an ask is open; then exactly
    // one capabilities and one ask_status (which renews the lease). Rules: docs/taskandi-client.md "Harness integration".
    async decide({ noOtherWork = false, remainingMinutes, windowsUsed } = {}) {
      const config = descriptorConfig(); const threshold = budgetThreshold();
      const first = await withState(cwd, now, async (state, statePath) => {
        const claim = claimOf(state); if (!claim) fail(DECIDE_NEEDS_CLAIM, 'USAGE');
        if (windowsUsed !== undefined) {
          const stored = Number.isSafeInteger(state.windowsUsed?.[claim.task]) ? state.windowsUsed[claim.task] : 0;
          if (state.windowsUsed?.[claim.task] !== Math.max(stored, windowsUsed)) { state.windowsUsed = { ...(state.windowsUsed ?? {}), [claim.task]: Math.max(stored, windowsUsed) }; atomicJson(statePath, state); }
        }
        return { task: claim.task, session: claim.session, open: openAskJobs(state, claim.task).length };
      });
      let status = null, degraded = false;
      if (first.open) {
        const send = await open(config, ['ask_status']); // a capabilities failure is exit 1
        try { status = (await send('ask_status', { task: first.task, ...(typeof first.session === 'string' ? { session: first.session } : {}) }, { task: first.task })).asks; }
        catch { degraded = true; }
      }
      return withState(cwd, now, async (state, statePath) => {
        const claim = claimOf(state);
        if (!claim || claim.task !== first.task) fail('the claim changed while decide ran; run decide again');
        const task = claim.task; const at = now(); const budgetKey = `budget-${task}`;
        const polls = Number.isSafeInteger(state.polls?.[task]) ? state.polls[task] : 0;
        let repoll = false, wroteRepoll = false;
        const asks = openAskJobs(state, task).map(job => {
          const { payload } = job; const askId = job.result.ask_id;
          const candidates = [];
          if (Number.isSafeInteger(claim.latest_start)) candidates.push(claim.latest_start);
          if (Number.isSafeInteger(claim.hardDeadline) && Number.isSafeInteger(payload.remaining_minutes)) candidates.push(claim.hardDeadline - payload.remaining_minutes * 60000);
          const latest = candidates.length ? Math.max(...candidates) : null;
          const out = { ask_id: askId, key: job.key, question: payload.question, default: payload.default, blocking: payload.blocking !== false, reversible: payload.reversible === true, action: 'wait', why: null, latest_start_used: latest };
          if (payload.blocking === false) return { ...out, action: 'continue', why: 'non-blocking' };
          const seen = degraded ? null : status.find(item => item.ask_id === askId);
          let why = null;
          if (degraded) why = 'status-unavailable';
          else if (!seen) why = 'unknown-ask';
          else if (seen.answered === true) {
            const prior = ledger(state, 'repolls').find(item => item.task === task && item.ask_id === askId);
            if (prior && polls > prior.pollSeq) why = 'answered-by-non-owner';
            else {
              why = 'answered-not-yet-polled'; repoll = true;
              if (!prior) { state.repolls = [...ledger(state, 'repolls'), { task, ask_id: askId, at, pollSeq: polls }]; wroteRepoll = true; }
            }
          }
          else if (seen.seen_at === null && seen.deferred !== true) why = 'unseen';
          else if (latest === null) why = 'no-deadline';
          else if (at < latest) why = 'before-latest-start';
          else if (claim.defaults_allowed !== true) why = 'defaults-off';
          else if (payload.reversible !== true) why = 'irreversible';
          if (why === null) return { ...out, action: 'proceed', why: 'default-allowed' };
          // A missing or not-yet-polled status never parks: it may clear by itself.
          const action = why === 'status-unavailable' || why === 'answered-not-yet-polled' ? 'wait' : noOtherWork ? 'park' : 'wait';
          return { ...out, action, why };
        });
        if (wroteRepoll) atomicJson(statePath, state);
        const unjudged = state.jobs.filter(job => job.kind === 'ask' && job.payload?.task === task && ['queued', 'uncertain', 'refused'].includes(job.state)).map(job => ({ key: job.key, state: job.state }));
        // Budget: Task&I's spent (claim, or the latest record_usage response) plus this task's undelivered usage.
        const allowance = plainObject(claim.allowance) ? claim.allowance : null;
        const spent = plainObject(claim.spent) ? claim.spent : { windows: 0, tokens: 0 };
        const v23Count = isV23(spentContractOf(state, claim));
        const pending = state.jobs.filter(job => job.kind === 'record_usage' && job.payload?.task === task && (job.state === 'queued' || job.state === 'uncertain')).reduce((sum, job) => sum + usageTokens(job.payload, v23Count), 0);
        const budget = { allowance, spent, pending_tokens: pending, ratio: null, unmetered: [], action: 'continue', why: 'no-allowance' };
        if (allowance !== null) {
          const ratios = []; let zero = false;
          if (allowance.tokens !== undefined) { if (allowance.tokens === 0) zero = true; else ratios.push(((spent.tokens ?? 0) + pending) / allowance.tokens); }
          if (allowance.windows !== undefined) {
            if (windowsUsed === undefined) budget.unmetered.push('windows');
            const used = Math.max(spent.windows ?? 0, windowsUsed === undefined ? 0 : Math.max(windowsUsed, state.windowsUsed?.[task] ?? 0));
            if (allowance.windows === 0) zero = true; else ratios.push(used / allowance.windows);
          }
          const raw = zero ? Math.max(1, ...ratios) : ratios.length ? Math.max(...ratios) : null;
          budget.ratio = raw === null ? null : Math.min(1, Math.max(0, raw));
          const asked = state.jobs.some(job => job.key === budgetKey);
          if (allowance.tokens === undefined && allowance.windows === undefined) budget.why = 'no-limits';
          else if (zero) Object.assign(budget, { action: 'stop', why: 'zero-allowance' });
          else if (raw >= 1) Object.assign(budget, { action: 'stop', why: 'cap' });
          else if (raw >= threshold && remainingMinutes > 0 && !asked) Object.assign(budget, { action: 'ask', why: 'most-spent', key: budgetKey });
          else budget.why = remainingMinutes === 0 ? 'nothing-outstanding' : 'under-threshold';
        }
        // Reclaim guard: Task&I handed back a task vibe parked, and nothing it was parked on has changed.
        const parked = ledger(state, 'parked').filter(item => item.task === task).at(-1);
        let reclaimed = false;
        if (parked) {
          // "Unchanged": the open blocking asks are exactly the ones it was parked on (an answer or a new ask changes it).
          const openIds = new Set(asks.filter(item => item.blocking).map(item => item.ask_id));
          const ids = new Set(Array.isArray(parked.openAskIds) ? parked.openAskIds : []);
          if (ids.size && ids.size === openIds.size && [...ids].every(id => openIds.has(id))) reclaimed = true;
          if (parked.budgetStopped === true && !['windows', 'tokens'].some(key => capOf(allowance, key) > capOf(parked.allowance, key))) reclaimed = true;
        }
        const next = (budget.why === 'cap' || budget.why === 'zero-allowance') && !reclaimed ? 'stop'
          : asks.some(item => item.action === 'proceed') ? 'proceed' : reclaimed ? 'release-again' : asks.some(item => item.action === 'park') ? 'park-task' : 'work';
        return { bound: true, task, now: at, next, asks, unjudged, budget, reclaimed_parked: reclaimed, repoll, ...(degraded ? { degraded: 'ask_status' } : {}) };
      });
    },
    // decide --resolve: offline; records that the harness proceeded on an ask's default. A park is recorded by
    // release --parked-asks alone.
    async resolve(key, as) {
      descriptorConfig(); key = stableKey(key);
      if (as !== 'proceeded') fail(HTTP_USAGE, 'USAGE');
      return withState(cwd, now, async (state, statePath) => {
        const claim = claimOf(state); if (!claim) fail(DECIDE_NEEDS_CLAIM, 'USAGE');
        const job = state.jobs.find(item => item.key === key);
        if (!job || job.kind !== 'ask' || job.state !== 'done' || job.payload?.task !== claim.task || typeof job.result?.ask_id !== 'string') fail(`decide --resolve takes the key of a done ask job on the claimed task (${key} is not one)`);
        const askId = job.result.ask_id; const existing = ledger(state, 'resolved').find(item => item.task === claim.task && item.ask_id === askId);
        if (existing && existing.as !== as) fail(`ask ${key} is already resolved as ${existing.as}`);
        if (!existing) state.resolved = [...ledger(state, 'resolved'), { task: claim.task, ask_id: askId, as, at: now() }];
        clearParked(state, claim.task);
        atomicJson(statePath, state);
        return { bound: true, channel: 'taskandi-http', task: claim.task, resolved: { key, ask_id: askId, as } };
      });
    },
    // A present but invalid descriptor is an error (exit 1), never a file-fallback report.
    async status() {
      const config = descriptorConfig();
      return withState(cwd, now, async state => {
        const counts = { queued: 0, dispatching: 0, done: 0, uncertain: 0, refused: 0 }; for (const job of state.jobs) if (Object.hasOwn(counts, job.state)) counts[job.state]++;
        const staleBindingKeys = state.jobs.filter(job => job.state === 'queued' && job.channel !== 'file-fallback' && job.binding !== bindingDigest(config)).map(job => job.key);
        return { bound: true, channel: 'taskandi-http', counts, uncertaintyIds: state.jobs.filter(job => job.state === 'uncertain').map(job => job.key), staleBindingKeys, refusedKeys: state.jobs.filter(job => job.state === 'refused').map(job => ({ key: job.key, code: job.refusedCode ?? 'unknown_error' })), claimedTask: claimOf(state)?.task ?? null, answerCount: state.answers.length, conflictIds: [...new Set(state.conflicts.map(item => item.id))], cursorSequence: state.cursor?.sequence ?? 0, lastGrade: typeof state.lastGrade === 'string' ? state.lastGrade : null, lastContract: typeof state.lastContract === 'string' ? state.lastContract : typeof state.lastGrade === 'string' ? HTTP_CONTRACT_REVISION : null, gatedKeys: state.jobs.filter(job => job.state === 'queued' && typeof job.lastError === 'string' && /^needs_contract_v2\.[45]$/.test(job.lastError)).map(job => ({ key: job.key, reason: job.lastError })) };
      });
    },
    // created [--task REF] [--all] (task_067): offline; the created ledger, non-gone entries unless --all, and with --task
    // only the entries whose parent is REF.
    async created({ task, all = false } = {}) {
      descriptorConfig();
      const parent = task === undefined ? undefined : normaliseTaskId(task, '--task');
      return withState(cwd, now, async state => ({ bound: true, created: ledger(state, 'created').filter(item => (all || item.gone !== true) && (parent === undefined || item.parent === parent)).map(item => ({ key: item.key, task_id: item.task_id, title: item.title, assign: item.assign, parent: item.parent ?? null, repeat: item.repeat === true, gone: item.gone === true, at: item.at })) }));
    },
  };
}

// The usage importer's ledger (AC33): per session and transcript file, {offset, prefixLen, prefixSha, tailIds} (see
// taskandi-usage.mjs). `entries` maps each file to the entry the import read (`before`) and its new one (`after`); an
// entry that changed since the import read it means another import raced this one.
function markImported(state, session, entries) {
  const sessions = { ...(state.usageImports ?? {}) }; const bySession = { ...(plainObject(sessions[session]) ? sessions[session] : {}) };
  for (const [file, { before, after }] of Object.entries(entries)) {
    if (canonical(bySession[file] ?? null) !== canonical(before ?? null)) fail('usage import raced another import; run usage again');
    bySession[file] = after;
  }
  sessions[session] = bySession; state.usageImports = sessions;
}

export function createClient({ cwd = process.cwd(), transport = fetchTransport, httpConnect, clock } = {}) {
  cwd = projectRoot(cwd);
  // clock () => ms is the decide test seam (task_065); never read from env or argv.
  if (clock !== undefined && typeof clock !== 'function') fail('clock must be a function returning milliseconds');
  const now = clock ? () => { const value = clock(); if (!Number.isSafeInteger(value) || value < 0) fail('clock must return nonnegative integer milliseconds'); return value; } : Date.now;
  // httpConnect {host, port, timeoutMs?} is the v2.2 test seam: tests point the transport at a loopback listener with it
  // (127.0.0.1 or ::1 only; refused for https origins).
  if (httpConnect !== undefined && (!plainObject(httpConnect) || (httpConnect.host !== '127.0.0.1' && httpConnect.host !== '::1') || !Number.isInteger(httpConnect.port) || httpConnect.port < 1 || httpConnect.port > 65535 || (httpConnect.timeoutMs !== undefined && !(Number.isInteger(httpConnect.timeoutMs) && httpConnect.timeoutMs > 0)))) fail('httpConnect must be {host: 127.0.0.1 or ::1, port, timeoutMs?}');
  const h = createHttpClient(cwd, httpConnect, now);
  const viaHttp = () => lexists(join(cwd, DESCRIPTOR));
  function guardedMcp(config) {
    const tokenPath = join(cwd, '.vibe/taskandi-token');
    if (trackedCaseInsensitive(cwd, tokenPath)) fail('Task&I token must be untracked');
    const token = readBounded(tokenPath, 16 * 1024, 'Task&I token', { ownerOnly: true }).trim();
    if (!token || /[\r\n]/.test(token)) fail('Task&I token is empty or contains newlines');
    return createMcp(config, request => {
      if (new URL(request.url).origin !== config.origin) fail('credential target left configured origin', 'PREDISPATCH');
      return Promise.resolve(transport({ ...request, headers: { ...request.headers, authorization: `Bearer ${token}` } }))
        .catch(error => fail(`MCP transport failed: ${error?.message ?? error}`, error?.code === 'PREDISPATCH' ? 'PREDISPATCH' : 'TRANSPORT'));
    });
  }
  async function toolMcp(config, name) {
    const mcp = guardedMcp(config); const tools = await mcp.discover();
    validateTool(tools.find(tool => tool?.name === name), name, revisionOf(config));
    return mcp;
  }
  // After the request is sent, a failure leaves the outcome unknown; before it (PREDISPATCH) nothing changed.
  async function sentCall(mcp, name, args, parse, unknownOutcome) {
    try { return parse(toolJson(await mcp.call(name, args))); }
    catch (error) {
      if (!unknownOutcome || error?.code === 'PREDISPATCH') throw error;
      const wrapped = new Error(`outcome unknown; check the task in Task&I: ${error.message}`); wrapped.code = 'OUTCOME_UNKNOWN'; throw wrapped;
    }
  }
  const claimedTask = state => claimOf(state)?.task ?? null;
  async function checkTarget(config, task) {
    if (task === config.task) return;
    if (task !== await withState(cwd, now, async state => claimedTask(state))) fail('task is neither the bound task nor the claimed task');
  }
  // Shared by complete/release: argv, config, revision gate, targeting, discovery, call, result, claim update.
  async function targeted(name, tool, task, extra, parse, apply) {
    taskRef(task);
    const config = loadConfig(cwd); if (!config.bound) return { ...FALLBACK };
    requireV2(config, name);
    await checkTarget(config, task);
    const mcp = await toolMcp(config, tool);
    const value = await sentCall(mcp, tool, { task, ...extra }, parse, true);
    await withState(cwd, now, async (state, statePath) => { if (apply(state, value)) atomicJson(statePath, state); });
    return { bound: true, ...value };
  }
  // MCP / file-fallback enqueue: every item is validated first, then one lock and one state write for all of them.
  async function fileEnqueueAll(kind, items, options = {}) {
    const config = loadConfig(cwd);
    const binding = config.bound ? config : { task: `file:${digest(cwd).slice(0, 32)}` };
    const prepared = items.map(({ key, input }) => {
      key = stableKey(key); input = ownObject(input, `${kind} payload`);
      if (options.task !== undefined) {
        if (config.bound) requireV2(config, 'enqueue --task');
        if (input.task !== undefined) fail('task given both in the payload and as --task');
        input = { ...input, task: options.task };
      }
      const payload = validatePayload(kind, input, binding, key);
      return { key, payload, hash: digest({ kind, payload }) };
    });
    return withState(cwd, now, async (state, statePath) => {
      const results = []; let changed = false;
      for (const { key, payload, hash } of prepared) {
        if (config.bound && payload.task !== undefined && payload.task !== config.task && payload.task !== claimedTask(state)) fail('task is neither the bound task nor the claimed task');
        const found = state.jobs.find(job => job.key === key) ?? tombstoneOf(state, key);
        if (found) { if (found.digest !== hash) fail('same key was already used with a different payload (KEY_CONFLICT)', 'KEY_CONFLICT'); results.push({ enqueued: false, deduplicated: true, key, state: found.state ?? 'done', bound: config.bound }); continue; }
        state.jobs.push({ key, kind, digest: hash, payload, binding: config.bound ? bindingDigest(config) : null, channel: config.bound ? 'taskandi-mcp' : 'file-fallback', state: 'queued', createdAt: new Date().toISOString() });
        changed = true; results.push({ enqueued: true, deduplicated: false, key, state: 'queued', bound: config.bound });
      }
      if (options.mark) { options.mark(state); changed = true; }
      if (changed) atomicJson(statePath, state);
      return results;
    });
  }
  return {
    config() { return loadConfig(cwd); },
    descriptor() { return viaHttp(); },
    async resolveTask(task) {
      if (viaHttp()) return h.resolveTask(task);
      taskRef(task); const config = loadConfig(cwd); if (!config.bound) return task;
      requireV2(config, 'usage --task'); await checkTarget(config, task); return task;
    },
    async enqueue(kind, key, input, options = {}) {
      if (viaHttp()) return h.enqueue(kind, key, input, options);
      if (isProposeKind(kind)) fail(PROPOSE_NEEDS_DESCRIPTOR(kind));
      return (await fileEnqueueAll(kind, [{ key, input }], options))[0];
    },
    // Many jobs of one kind under one config load and one outbox lock; `mark` (the usage importer's ledger update) lands
    // in the same state write as the jobs, on either path.
    async enqueueBatch(kind, items, options = {}) {
      if (viaHttp()) return h.enqueueAll(kind, items, options);
      if (isProposeKind(kind)) fail(PROPOSE_NEEDS_DESCRIPTOR(kind));
      return fileEnqueueAll(kind, items, options);
    },
    // The imported-message ledger of one session (read-only snapshot) and its update, for the usage importer.
    async usageImported(session) { return withState(cwd, now, async state => structuredClone(plainObject(state.usageImports?.[session]) ? state.usageImports[session] : {})); },
    importMarker(session, entries) { return state => markImported(state, session, entries); },
    // Every record_usage key the outbox still knows (live jobs and tombstones), for a usage import that re-reads a file.
    async usageKeys() { return withState(cwd, now, async state => [...state.jobs, ...ledger(state, 'tombstones')].filter(item => item.kind === 'record_usage').map(item => item.key)); },
    async decide(options = {}) {
      if (viaHttp()) return h.decide(options);
      const config = loadConfig(cwd); if (!config.bound) return { ...FALLBACK };
      fail(DECIDE_NEEDS_DESCRIPTOR);
    },
    async resolveAsk(key, as) {
      if (viaHttp()) return h.resolve(key, as);
      const config = loadConfig(cwd); if (!config.bound) return { ...FALLBACK };
      fail(DECIDE_NEEDS_DESCRIPTOR);
    },
    async flush() {
      if (viaHttp()) return h.flush();
      const config = loadConfig(cwd); if (!config.bound) return { bound: false, channel: 'file-fallback', dispatched: 0 };
      const mcp = guardedMcp(config); const tools = await mcp.discover();
      const byName = new Map(tools.map(tool => [tool?.name, tool]));
      const revision = revisionOf(config);
      const queuedKinds = await withState(cwd, now, async state => [...new Set(state.jobs.filter(job => job.state === 'queued' && job.channel !== 'file-fallback').map(job => job.kind))]);
      for (const kind of queuedKinds) validateTool(byName.get(kind), kind, revision);
      return withState(cwd, now, async (state, statePath) => {
        let dispatched = 0, done = 0, uncertain = 0;
        const queued = state.jobs.filter(item => item.state === 'queued' && item.channel !== 'file-fallback');
        for (const job of queued) if (job.binding !== bindingDigest(config)) fail(`queued job binding changed; reconcile explicitly before delivery (${job.key})`, 'BINDING_CHANGED');
        for (const job of queued) {
          validateTool(byName.get(job.kind), job.kind, revision);
          job.state = 'dispatching'; job.dispatchedAt = new Date().toISOString(); atomicJson(statePath, state); dispatched++;
          // Item 24: `dispatched` reflects whether the request genuinely reached the
          // transport, decided from the caught error itself (a 'PREDISPATCH'-coded
          // error - the same code validateTool already uses - means it never went
          // out) rather than a flag pre-set to true before the call. A failure that
          // never reached the transport takes the pre-dispatch branch (job stays
          // queued, safe to retry); anything else is genuinely uncertain. Either way
          // the original error's own message survives into lastError.
          try {
            const result = await mcp.call(job.kind, job.payload);
            if (job.kind === 'ask' && revision === CONTRACT_REVISION) job.result = validateAskResult(toolJson(result));
            job.state = 'done'; job.doneAt = new Date().toISOString(); delete job.lastError; done++;
          }
          catch (error) {
            const reachedTransport = error?.code !== 'PREDISPATCH';
            job.state = reachedTransport ? 'uncertain' : 'queued';
            job.lastError = reachedTransport ? `outcome unknown; reconcile explicitly: ${error.message}` : `pre-dispatch failure: ${error.message}`;
            if (reachedTransport) uncertain++;
            atomicJson(statePath, state);
            if (reachedTransport) break;
            throw error;
          }
          atomicJson(statePath, state);
        }
        return { bound: true, dispatched, done, uncertain };
      });
    },
    async reconcile(key, action, evidence, { taskId } = {}) {
      key = stableKey(key); if (!['done', 'retry'].includes(action)) fail('reconcile action must be done or retry'); text(evidence, 'evidence', LIMITS.text);
      if (taskId !== undefined) taskId = normaliseTaskId(taskId, '--task-id');
      return withState(cwd, now, async (state, statePath) => {
        const job = state.jobs.find(item => item.key === key); if (!job) fail('reconcile key was not found');
        // create_task (task_067): done needs the task id read from Task&I, which the ledger records; --task-id is for nothing else.
        if (taskId !== undefined && !(job.kind === 'create_task' && action === 'done')) fail('--task-id is only for reconcile --action done on a create_task job');
        if (job.kind === 'create_task' && action === 'done' && taskId === undefined && job.state === 'uncertain') fail('reconcile --action done on a create_task job needs --task-id <id>: read the created task\'s id in Task&I');
        // refused (v2.2 only): the server did not apply it, so it can be requeued but never marked done.
        if (job.state === 'refused' && job.channel === 'taskandi-http') { if (action === 'done') fail('a refused job was not applied; only --action retry can requeue it'); delete job.refusedCode; }
        else if (job.state !== 'uncertain') fail('only uncertain jobs can be reconciled');
        // A receipt_collision on a v2.3 resend proves the first send was applied: it is never retried (for a create_task,
        // only --action done --task-id can reconcile it, AC20).
        if (action === 'retry' && job.noRetry === true) fail(`this job was applied by its first send (receipt_collision on a resend); only --action done${job.kind === 'create_task' ? ' --task-id <id>' : ''} can reconcile it`);
        // A create_task retry is a new creation: the duplicate and cap checks run again, and the earlier attempt (it may
        // have been applied) keeps counting toward the caps (AC20).
        if (action === 'retry' && job.kind === 'create_task') creationChecks(state, { key: job.key, payload: job.payload, stamp: typeof job.sessionStamp === 'string' ? job.sessionStamp : null, at: now() });
        // done --task-id: the id must be new to this client (AC21); the entry it writes is marked reconciled.
        if (taskId !== undefined && (taskId === claimOf(state)?.task || taskId === loadConfig(cwd).task || ledger(state, 'created').some(item => item.task_id === taskId && item.key !== job.key))) fail('--task-id names the claimed task, the effective task or a task already in the created ledger; read the created task\'s own id in Task&I');
        // retry: a job with a frozen sentBody resends it (same request_id) on the next v2.3 flush, with a fresh attempt count;
        // one frozen on a replaced connection (replay unavailable) is rebuilt and sent afresh instead.
        const notices = [];
        if (action === 'retry' && job.replayLost === true) { unfreeze(job); notices.push(`${key}: ${RETRY_LOST}`); }
        // A create_task retry is a new write under a fresh request_id: Task&I cannot tell it from the earlier attempt.
        if (action === 'retry' && job.kind === 'create_task') {
          if (job.state === 'uncertain') { job.priorAttempts = [...(Array.isArray(job.priorAttempts) ? job.priorAttempts : []), Number.isSafeInteger(job.createdAtMs) ? job.createdAtMs : now()]; job.createdAtMs = now(); }
          unfreeze(job); job.requestId = randomUUID(); notices.push(`${key}: ${RETRY_CREATE}`);
        }
        job.state = action === 'done' ? 'done' : 'queued'; delete job.lastError; delete job.attempts; delete job.replayLost;
        if (action === 'done') job.doneAtMs = now();
        if (action === 'done' && job.kind === 'create_task' && taskId !== undefined) { job.result = { task_id: taskId, provisional: true }; recordCreated(state, job, taskId, job.doneAtMs, { reconciled: true }); }
        if (action === 'done') applyUpdate(state, job);
        state.reconciliationLog.push({ key, action, evidence, at: new Date().toISOString() }); atomicJson(statePath, state);
        return withNotices({ key, state: job.state, reconciled: true }, notices);
      });
    },
    async nextTask({ agent, session, bodyMaxChars, task: requested }) {
      if (agent !== 'claude' && agent !== 'codex') fail('--agent must be claude or codex');
      session = stableKey(session);
      if (viaHttp()) return h.nextTask({ agent, session, ...(bodyMaxChars === undefined ? {} : { bodyMaxChars }), ...(requested === undefined ? {} : { task: requested }) });
      const config = loadConfig(cwd); if (!config.bound) return { ...FALLBACK };
      if (requested !== undefined) fail(USAGE, 'USAGE');
      requireV2(config, 'next-task');
      const mcp = await toolMcp(config, 'next_task');
      const task = await sentCall(mcp, 'next_task', { task: config.task, agent, session }, validateNextTask, false);
      await withState(cwd, now, async (state, statePath) => {
        if (task.task === null) delete state.claimed;
        else state.claimed = { task: task.task, agent, session, lease: { ...task.lease }, claimedAt: new Date().toISOString() };
        atomicJson(statePath, state);
      });
      return { bound: true, task: task.task === null ? null : task };
    },
    complete(task, summary) {
      if (viaHttp()) return h.complete(task, summary);
      text(summary, 'summary');
      return targeted('complete', 'complete', task, { summary }, validateComplete, (state, value) => { if (!value.completed || claimedTask(state) !== task) return false; delete state.claimed; return true; });
    },
    release(task, reason, park) {
      if (viaHttp()) return h.release(task, reason, park);
      text(reason, 'reason');
      return targeted('release', 'release', task, { reason }, validateRelease, state => { if (claimedTask(state) !== task) return false; delete state.claimed; return true; });
    },
    async poll(options = {}) {
      if (viaHttp()) return h.poll(options);
      const config = loadConfig(cwd); if (!config.bound) return { bound: false, channel: 'file-fallback', newAnswers: 0, conflicts: [] };
      const revision = revisionOf(config); const legacy = revision === LEGACY_CONTRACT_REVISION;
      const mcp = await toolMcp(config, 'list_asks');
      const prior = await withState(cwd, now, async (state, statePath) => { bindAnswers(state, config); atomicJson(statePath, state); return state.cursor ?? { sequence: 0, value: '' }; });
      const result = await mcp.call('list_asks', legacy ? { task: config.task, answered: true, since: prior } : { task: config.task, since: prior }); const page = validatePollResult(result, prior, revision);
      return withState(cwd, now, async (state, statePath) => {
        bindAnswers(state, config);
        const current = state.cursor ?? { sequence: 0, value: '' };
        if (current.sequence !== prior.sequence || current.value !== prior.value) fail('poll cursor changed concurrently; response was not applied');
        const added = [], changed = []; let ignored = 0;
        for (const answer of page.answers) {
          const existing = state.answers.find(item => item.id === answer.id);
          if (!existing) {
            const receivedAt = new Date().toISOString();
            state.answers.push(legacy ? { id: answer.id, content: answer.content, receivedAt } : { ...answer, receivedAt });
            if (legacy) added.push({ id: answer.id, content: answer.content });
            else if (answer.ownerAnswer) added.push({ ask_id: answer.id, answer: answer.content, seen_at: answer.seenAt, answered_at: answer.answeredAt });
            else ignored++;
          }
          else if (existing.content !== answer.content) {
            const priorDigest = digest(existing.content), newDigest = digest(answer.content);
            if (!state.conflicts.some(item => item.id === answer.id && item.priorDigest === priorDigest && item.newDigest === newDigest)) { state.conflicts.push({ id: answer.id, priorDigest, newDigest, content: answer.content, detectedAt: new Date().toISOString() }); changed.push(answer.id); }
          }
        }
        atomicJson(statePath, state); // answers are durable before the cursor advances
        state.cursor = page.cursor; atomicJson(statePath, state);
        return legacy ? { bound: true, newAnswers: added.length, answers: added, conflicts: changed, cursor: page.cursor } : { bound: true, newAnswers: added.length, answers: added, ignored, conflicts: changed, cursor: page.cursor };
      });
    },
    async reconcileDirect(call, task, action, evidence) {
      if (!viaHttp()) fail('reconcile --direct needs a Task&I descriptor binding (.vibe/taskandi-descriptor.json)');
      return h.reconcileDirect(call, task, action, evidence);
    },
    async created(options = {}) {
      if (viaHttp()) return h.created(options);
      const config = loadConfig(cwd); if (!config.bound) return { ...FALLBACK };
      fail('created needs a Task&I descriptor binding');
    },
    async askStatus(options = {}) {
      if (!viaHttp()) fail('ask-status needs a Task&I descriptor binding (.vibe/taskandi-descriptor.json)');
      return h.askStatus(options);
    },
    async status() {
      if (viaHttp()) return h.status();
      let config; try { config = loadConfig(cwd); } catch (error) { config = { bound: false, reason: 'invalid-config', error: error.message }; }
      return withState(cwd, now, async state => {
        const counts = { queued: 0, dispatching: 0, done: 0, uncertain: 0 }; for (const job of state.jobs) if (Object.hasOwn(counts, job.state)) counts[job.state]++;
        const staleBindingKeys = config.bound ? state.jobs.filter(job => job.state === 'queued' && job.channel !== 'file-fallback' && job.binding !== bindingDigest(config)).map(job => job.key) : [];
        return { bound: config.bound, channel: config.bound ? 'taskandi-mcp' : 'file-fallback', reason: config.reason, configError: config.error, counts, uncertaintyIds: state.jobs.filter(job => job.state === 'uncertain').map(job => job.key), staleBindingKeys, claimedTask: claimedTask(state), answerCount: state.answers.length, conflictIds: [...new Set(state.conflicts.map(item => item.id))], cursorSequence: state.cursor?.sequence ?? 0 };
      });
    },
  };
}

async function readStdinBytes() {
  const chunks = []; let size = 0; const buffer = Buffer.alloc(64 * 1024);
  for (;;) { const count = readSync(0, buffer, 0, buffer.length, null); if (count === 0) break; size += count; if (size > LIMITS.stdin) fail(`stdin exceeds ${LIMITS.stdin} bytes`); chunks.push(Buffer.from(buffer.subarray(0, count))); }
  return Buffer.concat(chunks);
}
async function readStdinJson() {
  const raw = await readStdinBytes();
  try { return JSON.parse(raw.toString('utf8')); } catch { fail('stdin is not valid JSON'); }
}
function argValue(args, name) { const index = args.indexOf(name); if (index < 0 || index + 1 >= args.length) fail(`${name} is required`); return args[index + 1]; }
// Item 26: `Number('')` and `Number('  ')` are both 0, so an empty or
// whitespace `--cost-estimate` used to silently become a zero cost estimate
// instead of a usage error. Require a non-empty decimal string.
function costEstimateValue(raw) {
  if (typeof raw !== 'string' || !/^\d+(\.\d+)?$/.test(raw)) fail(`--cost-estimate must be a non-negative decimal number (e.g. 0.125), got ${JSON.stringify(raw)}`);
  return Number(raw);
}
// Strict flag parsing for the v2.1 commands: exact set, no repeats, every flag has a value, except `booleans`: valueless
// flags (true when present), refused if repeated; a value after one is read as an unknown flag and refused.
function strictFlags(args, required, optional = [], booleans = []) {
  const out = {};
  for (let i = 0; i < args.length;) {
    const flag = args[i];
    if (booleans.includes(flag)) { if (Object.hasOwn(out, flag)) fail(USAGE); out[flag] = true; i += 1; continue; }
    if (!(required.includes(flag) || optional.includes(flag)) || Object.hasOwn(out, flag) || i + 1 >= args.length) fail(USAGE);
    out[flag] = args[i + 1]; i += 2;
  }
  if (required.some(flag => !Object.hasOwn(out, flag))) fail(USAGE);
  return out;
}
const wholeNumber = (raw, name, max = Number.MAX_SAFE_INTEGER) => { if (typeof raw !== 'string' || !/^\d{1,16}$/.test(raw) || Number(raw) > max) fail(`${name} must be a nonnegative integer`); return Number(raw); };
function parkedAskIds(raw) {
  const ids = raw.split(',');
  if (!raw || ids.length > 200 || ids.some(id => !USABLE_ID.test(id)) || new Set(ids).size !== ids.length) fail('--parked-asks must be a comma-separated list of 1-200 distinct ask ids');
  return ids;
}
// Descriptor-binding argv, parsed with no binding, claim or state access: shared by the CLI and --check-argv, so the
// check validates exactly what a real run parses. --task is optional (target resolution) and takes Task&I task ids.
function parseDescriptorArgv(argv) {
  const command = argv[0]; const taskFlag = flags => (flags['--task'] === undefined ? undefined : descriptorTaskRef(flags['--task'], '--task'));
  const flags = (args, required, optional = [], booleans = []) => { try { return strictFlags(args, required, optional, booleans); } catch { fail(HTTP_USAGE); } };
  if (command === 'enqueue') {
    if (!['ask', 'comment', 'record_usage', 'record_time', ...PROPOSE_KINDS].includes(argv[1])) fail(HTTP_USAGE);
    // create_task and update_task take an optional --session (the session stamp the caps and update_cap count by); update_task names its task in the payload.
    if (argv[1] === 'create_task') { const parsed = flags(argv.slice(2), ['--key'], ['--session']); return { command, kind: argv[1], key: stableKey(parsed['--key']), session: parsed['--session'] === undefined ? undefined : stableKey(parsed['--session']), stdin: true }; }
    if (argv[1] === 'update_task') { const parsed = flags(argv.slice(2), ['--key'], ['--session']); return { command, kind: argv[1], key: stableKey(parsed['--key']), session: parsed['--session'] === undefined ? undefined : stableKey(parsed['--session']), stdin: true }; }
    const parsed = flags(argv.slice(2), ['--key'], ['--task']);
    return { command, kind: argv[1], key: stableKey(parsed['--key']), task: taskFlag(parsed), stdin: true };
  }
  if (command === 'created') { const parsed = flags(argv.slice(1), [], ['--task'], ['--all']); return { command, task: parsed['--task'] === undefined ? undefined : normaliseTaskId(parsed['--task'], '--task'), all: parsed['--all'] === true }; }
  if (command === 'flush' || command === 'status') { if (argv.length !== 1) fail(HTTP_USAGE); return { command }; }
  if (command === 'poll' || command === 'ask-status') return { command, task: taskFlag(flags(argv.slice(1), [], ['--task'])) };
  if (command === 'next-task') {
    const parsed = flags(argv.slice(1), ['--agent', '--session'], ['--body-max-chars', '--task']);
    if (parsed['--agent'] !== 'claude' && parsed['--agent'] !== 'codex') fail(HTTP_USAGE);
    return { command, agent: parsed['--agent'], session: stableKey(parsed['--session']), bodyMaxChars: parsed['--body-max-chars'] === undefined ? undefined : wholeNumber(parsed['--body-max-chars'], '--body-max-chars'), task: taskFlag(parsed) };
  }
  if (command === 'decide') {
    if (argv.includes('--resolve')) {
      const parsed = flags(argv.slice(1), ['--resolve', '--as']);
      if (parsed['--as'] !== 'proceeded') fail(HTTP_USAGE);
      return { command, resolve: stableKey(parsed['--resolve']), as: parsed['--as'] };
    }
    const parsed = flags(argv.slice(1), [], ['--remaining-minutes', '--windows-used'], ['--no-other-work']);
    return { command, noOtherWork: parsed['--no-other-work'] === true, remainingMinutes: parsed['--remaining-minutes'] === undefined ? undefined : wholeNumber(parsed['--remaining-minutes'], '--remaining-minutes'), windowsUsed: parsed['--windows-used'] === undefined ? undefined : wholeNumber(parsed['--windows-used'], '--windows-used') };
  }
  if (command === 'complete') { const parsed = flags(argv.slice(1), ['--summary'], ['--task']); return { command, task: taskFlag(parsed), summary: wireText(parsed['--summary'], 'summary', HTTP_LIMITS.summary) }; }
  if (command === 'release') {
    const parsed = flags(argv.slice(1), ['--reason'], ['--task', '--parked-asks'], ['--budget-stopped']);
    return { command, task: taskFlag(parsed), reason: wireText(parsed['--reason'], 'reason', HTTP_LIMITS.reason), park: { ...(parsed['--parked-asks'] === undefined ? {} : { parkedAsks: parkedAskIds(parsed['--parked-asks']) }), budgetStopped: parsed['--budget-stopped'] === true } };
  }
  if (command === 'usage') {
    const parsed = flags(argv.slice(1), ['--transcript', '--session', '--account', '--cost-estimate'], ['--task']);
    text(parsed['--transcript'], '--transcript', 4096); text(parsed['--account'], '--account', LIMITS.id);
    return { command, transcript: parsed['--transcript'], session: text(parsed['--session'], '--session', LIMITS.id), account: parsed['--account'], costEstimate: costEstimateValue(parsed['--cost-estimate']), task: taskFlag(parsed) };
  }
  if (command === 'reconcile' && argv.includes('--direct')) {
    // Values are checked by the client, which names each one.
    const parsed = flags(argv.slice(1), ['--direct', '--task', '--action', '--evidence']);
    return { command, direct: parsed['--direct'], task: parsed['--task'], action: parsed['--action'], evidence: parsed['--evidence'] };
  }
  if (command === 'reconcile') {
    const parsed = flags(argv.slice(1), ['--key', '--action', '--evidence'], ['--task-id']);
    return { command, key: parsed['--key'], action: parsed['--action'], evidence: parsed['--evidence'], taskId: parsed['--task-id'] === undefined ? undefined : normaliseTaskId(parsed['--task-id'], '--task-id') };
  }
  fail(HTTP_USAGE);
}
// --check-argv: syntax only (argv, and an enqueue's stdin payload when one is piped). No config, binding, claim, state or network.
async function checkArgv(argv) {
  const plan = parseDescriptorArgv(argv);
  // An empty stdin (or a terminal) checks the argv alone; a piped payload is checked as enqueue would check it.
  const raw = plan.stdin && !process.stdin.isTTY ? await readStdinBytes() : Buffer.alloc(0);
  if (raw.length) {
    let input; try { input = JSON.parse(raw.toString('utf8')); } catch { fail('stdin is not valid JSON'); }
    input = ownObject(input, `${plan.kind} payload`);
    if (isProposeKind(plan.kind)) validateProposal(plan.kind, input);
    else {
      if (input.task !== undefined) { if (plan.task !== undefined) fail('task given both in the payload and as --task'); descriptorTaskRef(input.task, 'task'); }
      validateHttpPayload(plan.kind, Object.fromEntries(Object.entries(input).filter(([name]) => name !== 'task')), plan.key);
    }
  }
  return { ok: true };
}
async function descriptorMain(client, argv) {
  const plan = parseDescriptorArgv(argv);
  switch (plan.command) {
    case 'enqueue': return client.enqueue(plan.kind, plan.key, await readStdinJson(), isProposeKind(plan.kind) ? { session: plan.session } : { task: plan.task });
    case 'created': return client.created({ task: plan.task, all: plan.all });
    case 'flush': return client.flush();
    case 'status': return client.status();
    case 'poll': return client.poll({ task: plan.task });
    case 'ask-status': return client.askStatus({ task: plan.task });
    case 'next-task': return client.nextTask({ agent: plan.agent, session: plan.session, bodyMaxChars: plan.bodyMaxChars, task: plan.task });
    case 'decide': return plan.resolve !== undefined ? client.resolveAsk(plan.resolve, plan.as) : client.decide({ noOtherWork: plan.noOtherWork, remainingMinutes: plan.remainingMinutes, windowsUsed: plan.windowsUsed });
    case 'complete': return client.complete(plan.task, plan.summary);
    case 'release': return client.release(plan.task, plan.reason, plan.park);
    case 'usage': { const { enqueueTranscriptUsage } = await import('./taskandi-usage.mjs'); return enqueueTranscriptUsage(client, plan.transcript, { session: plan.session, account: plan.account, costEstimate: plan.costEstimate, task: plan.task }); }
    default: return plan.direct ? client.reconcileDirect(plan.direct, plan.task, plan.action, plan.evidence) : client.reconcile(plan.key, plan.action, plan.evidence, { taskId: plan.taskId });
  }
}
// Server strings reach stdout as JSON; C1 and bidi controls are escaped as \uXXXX so they cannot steer a terminal.
const TERMINAL_UNSAFE = /[\u0080-\u009f\u202a-\u202e\u2066-\u2069]/g;
export function terminalSafeJson(value) { return JSON.stringify(value).replace(TERMINAL_UNSAFE, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`); }
// clientOptions reach createClient (tests pass the httpConnect seam); the CLI itself never sets them.
export async function main(argv = process.argv.slice(2), clientOptions = {}) {
  // --check-argv (first argument, or first after the command name) runs before any config, stdin config or state read.
  if (argv[0] === '--check-argv' || argv[1] === '--check-argv') {
    const rest = argv[0] === '--check-argv' ? argv.slice(1) : [argv[0], ...argv.slice(2)];
    process.stdout.write(`${JSON.stringify(await checkArgv(rest))}\n`); return;
  }
  const client = createClient(clientOptions); const command = argv[0]; let result;
  const descriptor = client.descriptor();
  if (descriptor) result = await descriptorMain(client, argv);
  else if (command === 'enqueue') {
    // create_task/update_task speak only the browser-agent API (contract v2.4+).
    if (isProposeKind(argv[1])) fail(PROPOSE_NEEDS_DESCRIPTOR(argv[1]));
    if (!['ask', 'comment', 'record_usage', 'record_time'].includes(argv[1])) fail(USAGE);
    const flags = strictFlags(argv.slice(2), ['--key'], ['--task']);
    if (flags['--task'] !== undefined) taskRef(flags['--task'], '--task');
    result = await client.enqueue(argv[1], flags['--key'], await readStdinJson(), { task: flags['--task'] });
  }
  else if (command === 'flush') result = await client.flush();
  else if (command === 'created') { const plan = parseDescriptorArgv(argv); result = await client.created({ task: plan.task, all: plan.all }); }
  else if (command === 'poll') result = await client.poll();
  else if (command === 'status') result = await client.status();
  else if (command === 'next-task') {
    // --task (claim a named task) exists only under a descriptor binding: unbound it reports file-fallback, MCP refuses it.
    const flags = strictFlags(argv.slice(1), ['--agent', '--session'], ['--task']);
    if (flags['--agent'] !== 'claude' && flags['--agent'] !== 'codex') fail(USAGE);
    stableKey(flags['--session']);
    result = await client.nextTask({ agent: flags['--agent'], session: flags['--session'], ...(flags['--task'] === undefined ? {} : { task: flags['--task'] }) });
  }
  else if (command === 'complete') { const flags = strictFlags(argv.slice(1), ['--task', '--summary']); taskRef(flags['--task'], '--task'); text(flags['--summary'], '--summary'); result = await client.complete(flags['--task'], flags['--summary']); }
  else if (command === 'release') { const flags = strictFlags(argv.slice(1), ['--task', '--reason']); taskRef(flags['--task'], '--task'); text(flags['--reason'], '--reason'); result = await client.release(flags['--task'], flags['--reason']); }
  else if (command === 'usage') {
    const { enqueueTranscriptUsage } = await import('./taskandi-usage.mjs');
    const taskIndex = argv.indexOf('--task');
    const task = taskIndex < 0 ? undefined : taskRef(argValue(argv, '--task'), '--task');
    result = await enqueueTranscriptUsage(client, argValue(argv, '--transcript'), {
      session: argValue(argv, '--session'), account: argValue(argv, '--account'),
      costEstimate: costEstimateValue(argValue(argv, '--cost-estimate')), task,
    });
  }
  else if (command === 'reconcile') result = await client.reconcile(argValue(argv, '--key'), argValue(argv, '--action'), argValue(argv, '--evidence'));
  else if (command === 'decide') {
    // Same argv rules as under a descriptor binding; an unbound project then reports file-fallback, an MCP binding is refused.
    const plan = parseDescriptorArgv(argv);
    result = plan.resolve !== undefined ? await client.resolveAsk(plan.resolve, plan.as) : await client.decide(plan);
  }
  else fail(USAGE);
  process.stdout.write(`${descriptor ? terminalSafeJson(result) : JSON.stringify(result)}\n`);
  for (const notice of result?.notices ?? []) process.stderr.write(`taskandi-client: ${notice}\n`);
}
// The CLI entry: stdout from main, every failure as `taskandi-client: <message>` lines on stderr and exit code 1.
export async function cli(argv = process.argv.slice(2), clientOptions = {}) {
  try { await main(argv, clientOptions); return 0; }
  catch (error) {
    for (const line of error?.preface ?? []) process.stderr.write(`taskandi-client: ${line}\n`);
    process.stderr.write(`taskandi-client: ${error?.message ?? error}\n`); process.exitCode = 1; return 1;
  }
}

function invokedDirectly() {
  try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); }
  catch { return false; }
}
if (invokedDirectly()) cli();
