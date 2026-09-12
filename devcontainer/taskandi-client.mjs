#!/usr/bin/env node
/** Narrow, project-opt-in Task&I MCP client. Node built-ins only. */
import { createHash, randomUUID } from 'node:crypto';
import { closeSync, constants, existsSync, fstatSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const MCP_REVISION = '2025-11-25';
export const CONTRACT_REVISION = 'vibe-action-window-fixture-v1';
export const LIMITS = Object.freeze({ stdin: 256 * 1024, response: 1024 * 1024, text: 8000, option: 1000, options: 50, id: 200 });
const CONFIG_KEYS = new Set(['endpoint', 'task', 'contractRevision']);
const TOOL_CONTRACT = Object.freeze({
  ask: { required: ['task', 'to', 'question', 'default'], optional: ['options'] },
  record_usage: { required: ['account', 'model', 'input', 'output', 'cache_read', 'cache_write', 'cost_estimate', 'source', 'source_ref'], optional: [] },
  list_asks: { required: ['task', 'answered', 'since'], optional: [] },
});
const TOOL_TYPES = Object.freeze({
  ask: { task: 'string', to: 'string', question: 'string', default: 'string', options: 'array' },
  record_usage: { account: 'string', model: 'string', input: 'integer', output: 'integer', cache_read: 'integer', cache_write: 'integer', cost_estimate: 'number', source: 'string', source_ref: 'string' },
  list_asks: { task: 'string', answered: 'boolean', since: 'object' },
});

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

function assertRegular(path, description, { ownerOnly = false } = {}) {
  let st;
  try { st = lstatSync(path); } catch (error) { if (error.code === 'ENOENT') fail(`${description} is missing`, 'MISSING'); throw error; }
  if (st.isSymbolicLink() || !st.isFile() || st.nlink !== 1) fail(`${description} must be a regular non-symlink file`);
  if (typeof process.getuid === 'function' && st.uid !== process.getuid()) fail(`${description} must be owned by the current user`);
  if (ownerOnly && (st.mode & 0o077) !== 0) fail(`${description} permissions must deny group and other access`);
  return st;
}
function readBounded(path, limit, description, { ownerOnly = false } = {}) {
  let fd;
  try { fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK); }
  catch (error) { if (error.code === 'ELOOP') fail(`${description} must be a regular non-symlink file`); if (error.code === 'ENOENT') fail(`${description} is missing`, 'MISSING'); throw error; }
  try {
    const st = fstatSync(fd);
    if (!st.isFile() || st.nlink !== 1) fail(`${description} must be a regular non-symlink file`);
    if (typeof process.getuid === 'function' && st.uid !== process.getuid()) fail(`${description} must be owned by the current user`);
    if (ownerOnly && (st.mode & 0o077) !== 0) fail(`${description} permissions must deny group and other access`);
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
  if (!/^(?:[A-Za-z][A-Za-z0-9]*-[0-9]+|taskandeye:\/\/node\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/.test(value)) fail('invalid per-launch task reference');
  return value;
}
export function loadConfig(cwd = process.cwd()) {
  cwd = projectRoot(cwd);
  const relative = '.vibe/taskandi.json';
  const path = join(cwd, relative);
  if (!existsSync(path)) {
    if (process.env.VIBE_TASK_BINDING && process.env.VIBE_TASK_BINDING !== 'unbound') fail('pinned task binding changed');
    return { bound: false, reason: 'missing-config', cwd };
  }
  const vibeDir = join(cwd, '.vibe');
  const vibeStat = lstatSync(vibeDir);
  if (vibeStat.isSymbolicLink() || !vibeStat.isDirectory() || vibeStat.uid !== process.getuid() || (vibeStat.mode & 0o022)) fail('.vibe must be a non-symlink directory');
  assertRegular(path, 'Task&I config');
  if (trackedCaseInsensitive(cwd, path)) fail('Task&I config is tracked by git (case-insensitive match refused)');
  let value;
  try { value = ownObject(JSON.parse(readBounded(path, 32 * 1024, 'Task&I config')), 'config'); } catch (error) { if (error instanceof SyntaxError) fail('Task&I config is not valid JSON'); throw error; }
  exactKeys(value, CONFIG_KEYS, 'config');
  text(value.endpoint, 'endpoint', 2048);
  const mappingPath = join(cwd, '.vibe/taskandi-task');
  let task = value.task;
  if (existsSync(mappingPath)) {
    if (trackedCaseInsensitive(cwd, mappingPath)) fail('Task&I node mapping must be untracked');
    task = taskReference(readBounded(mappingPath, 1024, 'Task&I node mapping').trim());
  }
  if (process.env.VIBE_TASK_REF) task = taskReference(process.env.VIBE_TASK_REF);
  text(task, 'task', LIMITS.id);
  if (value.contractRevision !== undefined && value.contractRevision !== CONTRACT_REVISION) fail(`contractRevision must exactly equal ${CONTRACT_REVISION}`);
  let endpoint;
  try { endpoint = new URL(value.endpoint); } catch { fail('endpoint is not a valid absolute URL'); }
  const authority = value.endpoint.match(/^[A-Za-z][A-Za-z0-9+.-]*:\/\/([^/]*)/)?.[1] || '';
  if (authority.includes('@') || value.endpoint.includes('?') || value.endpoint.includes('#')) fail('endpoint must not contain userinfo, query, or fragment');
  const host = endpoint.hostname.toLowerCase();
  const loopback = host === 'localhost' || host === 'host.docker.internal' || host === '127.0.0.1' || host === '[::1]';
  if (endpoint.protocol !== 'https:' && !(endpoint.protocol === 'http:' && loopback)) fail('endpoint must use HTTPS (HTTP is limited to loopback or host.docker.internal)');
  if (!['https:', 'http:'].includes(endpoint.protocol)) fail('unsupported endpoint protocol');
  const config = { bound: true, cwd, endpoint: endpoint.href, origin: endpoint.origin, task, contractRevision: value.contractRevision ?? null };
  if (process.env.VIBE_TASK_BINDING && process.env.VIBE_TASK_BINDING !== bindingFingerprint(config)) fail('pinned task binding changed');
  return config;
}

export function bindingFingerprint(config) {
  return config.bound ? digest({ endpoint: config.endpoint, task: config.task, contractRevision: config.contractRevision }) : 'unbound';
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
  const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
  const encoded = `${JSON.stringify(value, null, 2)}\n`;
  if (Buffer.byteLength(encoded) > 4 * 1024 * 1024) fail('outbox capacity exceeded; archive completed records before adding data');
  const fd = openSync(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { writeFileSync(fd, encoded); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(tmp, path);
  const dfd = openSync(dirname(path), constants.O_RDONLY); try { fsyncSync(dfd); } finally { closeSync(dfd); }
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
    closeSync(fd);
    // Never unlink a replacement owner's lock.
    try { if (readBounded(p.lock, 100, 'outbox lock', { ownerOnly: true }) === token) unlinkSync(p.lock); }
    catch (error) { if (error.code !== 'MISSING') throw error; }
  } };

}
function readState(path) {
  if (!existsSync(path)) return initialState();
  let state; try { state = ownObject(JSON.parse(readBounded(path, 4 * 1024 * 1024, 'outbox state', { ownerOnly: true })), 'outbox state'); } catch (error) { if (error instanceof SyntaxError) fail('outbox state is corrupt'); throw error; }
  if (state.version !== 1 || !Array.isArray(state.jobs) || !Array.isArray(state.answers) || !Array.isArray(state.conflicts) || !Array.isArray(state.reconciliationLog)) fail('outbox state has an unsupported shape');
  return state;
}
function bindAnswers(state, config) {
  const binding = digest({ endpoint: config.endpoint, task: config.task, contractRevision: config.contractRevision });
  if (state.answerBinding && state.answerBinding !== binding) fail('answer binding changed; archive the prior outbox before polling another task');
  if (!state.answerBinding && (state.cursor || state.answers.length || state.conflicts.length)) fail('existing answers have no binding evidence; reconcile before polling');
  state.answerBinding = binding;
}
function recoverDispatching(state) {
  let changed = false;
  for (const job of state.jobs) if (job.state === 'dispatching') { job.state = 'uncertain'; job.lastError = 'previous invocation ended while dispatching'; changed = true; }
  return changed;
}
async function withState(cwd, fn) {
  const locked = lockOutbox(cwd);
  try { const state = readState(locked.state); if (recoverDispatching(state)) atomicJson(locked.state, state); return await fn(state, locked.state); } finally { locked.release(); }
}

export function validatePayload(kind, input, config, key) {
  input = ownObject(input, `${kind} payload`);
  if (kind === 'ask') {
    exactKeys(input, new Set(['to', 'question', 'default', 'options']), 'ask payload');
    const payload = { task: text(config.task, 'task', LIMITS.id), to: text(input.to, 'to', LIMITS.id), question: text(input.question, 'question'), default: text(input.default, 'default') };
    if (input.options !== undefined) {
      if (!Array.isArray(input.options) || input.options.length > LIMITS.options) fail(`options must be an array of at most ${LIMITS.options} strings`);
      payload.options = input.options.map((item, i) => text(item, `options[${i}]`, LIMITS.option));
    }
    return payload;
  }
  if (kind === 'record_usage') {
    exactKeys(input, new Set(['account', 'model', 'input', 'output', 'cache_read', 'cache_write', 'cost_estimate']), 'record_usage payload');
    return { account: text(input.account, 'account', LIMITS.id), model: text(input.model, 'model', LIMITS.id), input: safeCount(input.input, 'input'), output: safeCount(input.output, 'output'), cache_read: safeCount(input.cache_read, 'cache_read'), cache_write: safeCount(input.cache_write, 'cache_write'), cost_estimate: safeCost(input.cost_estimate), source: 'vibe', source_ref: stableKey(key) };
  }
  fail(`unsupported enqueue kind ${kind}`);
}

function validateTool(tool, expectedName) {
  if (!tool || tool.name !== expectedName) fail(`expected tool ${expectedName} is missing`, 'PREDISPATCH');
  const schema = ownObject(tool.inputSchema, `${expectedName} inputSchema`);
  if (schema.type !== 'object' || !schema.properties || typeof schema.properties !== 'object' || Array.isArray(schema.properties)) fail(`${expectedName} has an unsupported input schema`, 'PREDISPATCH');
  const contract = TOOL_CONTRACT[expectedName];
  const allowed = new Set([...contract.required, ...contract.optional]);
  const properties = Object.keys(schema.properties);
  const required = Array.isArray(schema.required) ? schema.required : [];
  if (properties.some(key => !allowed.has(key)) || required.some(key => !allowed.has(key))) fail(`${expectedName} schema contains fields outside the narrow contract`, 'PREDISPATCH');
  if (contract.required.some(key => !properties.includes(key) || !required.includes(key))) fail(`${expectedName} schema does not require the fixture contract fields`, 'PREDISPATCH');
  if (properties.some(key => schema.properties[key]?.type !== TOOL_TYPES[expectedName][key])) fail(`${expectedName} schema has incompatible field types`, 'PREDISPATCH');
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
function validatePollResult(result, prior) {
  const value = toolJson(result); exactKeys(value, new Set(['since', 'cursor', 'answers']), 'list_asks result');
  const since = validateCursor(value.since, 'list_asks result since'); const cursor = validateCursor(value.cursor, 'list_asks result cursor');
  if (since.sequence !== prior.sequence || since.value !== prior.value) fail('list_asks response does not echo the requested cursor');
  if (cursor.sequence < prior.sequence) fail('list_asks cursor regressed');
  if (cursor.sequence === prior.sequence && cursor.value !== prior.value) fail('list_asks cursor is noncomparable');
  if (!Array.isArray(value.answers) || value.answers.length > 1000) fail('list_asks answers has an unsupported shape');
  const answers = value.answers.map((item, index) => { item = ownObject(item, `answer[${index}]`); exactKeys(item, new Set(['id', 'content']), `answer[${index}]`); return { id: text(item.id, `answer[${index}].id`, LIMITS.id), content: text(item.content, `answer[${index}].content`, LIMITS.text, true) }; });
  return { cursor, answers };
}

export function createClient({ cwd = process.cwd(), transport = fetchTransport } = {}) {
  cwd = projectRoot(cwd);
  return {
    config() { return loadConfig(cwd); },
    async enqueue(kind, key, input) {
      key = stableKey(key);
      const config = loadConfig(cwd);
      const binding = config.bound ? config : { task: `file:${digest(cwd).slice(0, 32)}` };
      const payload = validatePayload(kind, input, binding, key); const hash = digest({ kind, payload });
      return withState(cwd, async (state, statePath) => {
        const found = state.jobs.find(job => job.key === key);
        if (found) { if (found.digest !== hash) fail('same key was already used with a different payload', 'KEY_CONFLICT'); return { enqueued: false, deduplicated: true, key, state: found.state, bound: config.bound }; }
        state.jobs.push({ key, kind, digest: hash, payload, binding: config.bound ? digest({ endpoint: config.endpoint, task: config.task, contractRevision: config.contractRevision }) : null, channel: config.bound ? 'taskandi-mcp' : 'file-fallback', state: 'queued', createdAt: new Date().toISOString() }); atomicJson(statePath, state);
        return { enqueued: true, deduplicated: false, key, state: 'queued', bound: config.bound };
      });
    },
    async flush() {
      const config = loadConfig(cwd); if (!config.bound) return { bound: false, channel: 'file-fallback', dispatched: 0 };
      const tokenPath = join(cwd, '.vibe/taskandi-token');
      if (trackedCaseInsensitive(cwd, tokenPath)) fail('Task&I token must be untracked');
      const token = readBounded(tokenPath, 16 * 1024, 'Task&I token', { ownerOnly: true }).trim();
      if (!token || /[\r\n]/.test(token)) fail('Task&I token is empty or contains newlines');
      const guardedTransport = request => {
        if (new URL(request.url).origin !== config.origin) fail('credential target left configured origin');
        return Promise.resolve(transport({ ...request, headers: { ...request.headers, authorization: `Bearer ${token}` } })).catch(() => fail('MCP transport failed'));
      };
      const mcp = createMcp(config, guardedTransport); const tools = await mcp.discover();
      const byName = new Map(tools.map(tool => [tool?.name, tool]));
      const queuedKinds = await withState(cwd, async state => [...new Set(state.jobs.filter(job => job.state === 'queued' && job.channel !== 'file-fallback').map(job => job.kind))]);
      for (const kind of queuedKinds) validateTool(byName.get(kind), kind);
      return withState(cwd, async (state, statePath) => {
        let dispatched = 0, done = 0, uncertain = 0;
        for (const job of state.jobs.filter(item => item.state === 'queued' && item.channel !== 'file-fallback')) {
          if (job.binding !== digest({ endpoint: config.endpoint, task: config.task, contractRevision: config.contractRevision })) fail('queued job binding changed; reconcile explicitly before delivery', 'BINDING_CHANGED');
          validateTool(byName.get(job.kind), job.kind);
          job.state = 'dispatching'; job.dispatchedAt = new Date().toISOString(); atomicJson(statePath, state); dispatched++;
          let sent = false;
          try { sent = true; await mcp.call(job.kind, job.payload); job.state = 'done'; job.doneAt = new Date().toISOString(); delete job.lastError; done++; }
          catch (error) { job.state = sent ? 'uncertain' : 'queued'; job.lastError = sent ? 'outcome unknown; reconcile explicitly' : 'pre-dispatch failure'; if (sent) uncertain++; atomicJson(statePath, state); if (sent) break; throw error; }
          atomicJson(statePath, state);
        }
        return { bound: true, dispatched, done, uncertain };
      });
    },
    async reconcile(key, action, evidence) {
      key = stableKey(key); if (!['done', 'retry'].includes(action)) fail('reconcile action must be done or retry'); text(evidence, 'evidence', LIMITS.text);
      return withState(cwd, async (state, statePath) => {
        const job = state.jobs.find(item => item.key === key); if (!job) fail('reconcile key was not found'); if (job.state !== 'uncertain') fail('only uncertain jobs can be reconciled');
        job.state = action === 'done' ? 'done' : 'queued'; delete job.lastError;
        state.reconciliationLog.push({ key, action, evidence, at: new Date().toISOString() }); atomicJson(statePath, state);
        return { key, state: job.state, reconciled: true };
      });
    },
    async poll() {
      const config = loadConfig(cwd); if (!config.bound) return { bound: false, channel: 'file-fallback', newAnswers: 0, conflicts: [] };
      const tokenPath = join(cwd, '.vibe/taskandi-token');
      if (trackedCaseInsensitive(cwd, tokenPath)) fail('Task&I token must be untracked'); const token = readBounded(tokenPath, 16 * 1024, 'Task&I token', { ownerOnly: true }).trim();
      if (!token || /[\r\n]/.test(token)) fail('Task&I token is empty or contains newlines');
      const mcp = createMcp(config, request => {
        if (new URL(request.url).origin !== config.origin) fail('credential target left configured origin');
        return Promise.resolve(transport({ ...request, headers: { ...request.headers, authorization: `Bearer ${token}` } })).catch(() => fail('MCP transport failed'));
      });
      const tools = await mcp.discover(); validateTool(tools.find(tool => tool?.name === 'list_asks'), 'list_asks');
      const prior = await withState(cwd, async (state, statePath) => { bindAnswers(state, config); atomicJson(statePath, state); return state.cursor ?? { sequence: 0, value: '' }; });
      const result = await mcp.call('list_asks', { task: config.task, answered: true, since: prior }); const page = validatePollResult(result, prior);
      return withState(cwd, async (state, statePath) => {
        bindAnswers(state, config);
        const current = state.cursor ?? { sequence: 0, value: '' };
        if (current.sequence !== prior.sequence || current.value !== prior.value) fail('poll cursor changed concurrently; response was not applied');
        const added = [], changed = [];
        for (const answer of page.answers) {
          const existing = state.answers.find(item => item.id === answer.id);
          if (!existing) { state.answers.push({ ...answer, receivedAt: new Date().toISOString() }); added.push(answer); }
          else if (existing.content !== answer.content) {
            const priorDigest = digest(existing.content), newDigest = digest(answer.content);
            if (!state.conflicts.some(item => item.id === answer.id && item.priorDigest === priorDigest && item.newDigest === newDigest)) { state.conflicts.push({ id: answer.id, priorDigest, newDigest, content: answer.content, detectedAt: new Date().toISOString() }); changed.push(answer.id); }
          }
        }
        atomicJson(statePath, state); // answers are durable before the cursor advances
        state.cursor = page.cursor; atomicJson(statePath, state);
        return { bound: true, newAnswers: added.length, answers: added, conflicts: changed, cursor: page.cursor };
      });
    },
    async status() {
      let config; try { config = loadConfig(cwd); } catch (error) { config = { bound: false, reason: 'invalid-config', error: error.message }; }
      return withState(cwd, async state => {
        const counts = { queued: 0, dispatching: 0, done: 0, uncertain: 0 }; for (const job of state.jobs) if (Object.hasOwn(counts, job.state)) counts[job.state]++;
        return { bound: config.bound, channel: config.bound ? 'taskandi-mcp' : 'file-fallback', reason: config.reason, configError: config.error, counts, uncertaintyIds: state.jobs.filter(job => job.state === 'uncertain').map(job => job.key), answerCount: state.answers.length, conflictIds: [...new Set(state.conflicts.map(item => item.id))], cursorSequence: state.cursor?.sequence ?? 0 };
      });
    },
  };
}

async function readStdinJson() {
  const chunks = []; let size = 0; const buffer = Buffer.alloc(64 * 1024);
  for (;;) { const count = readSync(0, buffer, 0, buffer.length, null); if (count === 0) break; size += count; if (size > LIMITS.stdin) fail(`stdin exceeds ${LIMITS.stdin} bytes`); chunks.push(Buffer.from(buffer.subarray(0, count))); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('stdin is not valid JSON'); }
}
function argValue(args, name) { const index = args.indexOf(name); if (index < 0 || index + 1 >= args.length) fail(`${name} is required`); return args[index + 1]; }
export async function main(argv = process.argv.slice(2)) {
  const client = createClient(); const command = argv[0]; let result;
  if (command === 'enqueue') result = await client.enqueue(argv[1], argValue(argv, '--key'), await readStdinJson());
  else if (command === 'flush') result = await client.flush();
  else if (command === 'poll') result = await client.poll();
  else if (command === 'status') result = await client.status();
  else if (command === 'usage') {
    const { enqueueTranscriptUsage } = await import('./taskandi-usage.mjs');
    result = await enqueueTranscriptUsage(client, argValue(argv, '--transcript'), {
      session: argValue(argv, '--session'), account: argValue(argv, '--account'),
      costEstimate: Number(argValue(argv, '--cost-estimate')),
    });
  }
  else if (command === 'reconcile') result = await client.reconcile(argValue(argv, '--key'), argValue(argv, '--action'), argValue(argv, '--evidence'));
  else fail('usage: taskandi-client.mjs enqueue ask|record_usage --key ID | flush | poll | status | reconcile --key ID --action done|retry --evidence TEXT');
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

function invokedDirectly() {
  try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); }
  catch { return false; }
}
if (invokedDirectly()) main().catch(error => { process.stderr.write(`taskandi-client: ${error.message}\n`); process.exitCode = 1; });
