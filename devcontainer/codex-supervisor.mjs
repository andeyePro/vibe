#!/usr/bin/env node
// codex-supervisor — drives ONE unattended Codex thread through
// `codex app-server` on stdio, so `$vsss` can run across quota windows
// without a human turn (docs/codex-integration-plan.md D7, task_048).
//
// Wire format is newline-delimited JSON, NOT JSON-RPC 2.0: no `jsonrpc`
// field is sent or expected (codex-rs/app-server-transport/src/transport/
// stdio.rs, app-server-protocol/src/rpc.rs at tag rust-v0.154.0).
//
// Safety contract (AC8): never passes `--dangerously-bypass-approvals-and-
// sandbox`, never sets `-c`, never reads or copies `auth.json`, writes only
// the state, adjacent ownership/stop files and log, and sends no prompt other than the
// user's (prefix-rewritten) text and the literal `continue`.
import { loadConfig, bindingFingerprint } from './taskandi-client.mjs';
import { acquire, canonicalPath, readRegular, atomicWrite, requestStop, closeServer, ownershipFresh, appendRegular, spawnOwnedServer } from './supervisor-control.mjs';
import { spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import {
  existsSync, mkdirSync, readFileSync, realpathSync,
  renameSync, statSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// --- constants ---------------------------------------------------------

export const EXIT_OK = 0;
export const EXIT_FAIL = 1;
export const EXIT_USAGE = 2;
export const EXIT_CEILING = 3;
export const EXIT_SIGNAL = 130;

// AC2: only an exact, case-sensitive FIRST token is rewritten. `/vss:foo`,
// `/vssx` and `/VS` are other tokens and travel unchanged.
export const REWRITES = { '/vs': '$vs', '/vss': '$vss', '/vsss': '$vsss' };

export const CLIENT_NAME = 'vibe-codex-supervisor';
const HANDSHAKE_TIMEOUT_MS = 30000;
const REQUEST_TIMEOUT_MS = 30000;
// AC5 transient back-off ladder and AC6 blind-quota ladder, both capped.
const TRANSIENT_BACKOFF = [60, 120, 240, 480, 960, 1920];
const QUOTA_BACKOFF = [300, 600, 1200, 2400];
const BACKOFF_CAP = 3600;
const QUOTA_GRACE_SECONDS = 120;
// Externally-tagged CodexErrorInfo (protocol/v2/shared.rs:70-113): unit
// variants are bare strings, struct variants single-key objects.
const QUOTA_ERRORS = new Set(['usageLimitExceeded', 'rateLimitExceeded']);
const FATAL_ERRORS = new Set(['sessionBudgetExceeded', 'contextWindowExceeded']);
const TRANSIENT_ERRORS = new Set([
  'serverOverloaded', 'responseStreamConnectionFailed',
  'responseStreamDisconnected', 'responseTooManyFailedAttempts',
]);
const DEFAULTS = {
  maxTurns: 50,
  maxResumes: 20,
  maxQuotaWaits: 12,
  maxTransientRetries: 6,
  maxTurnFailures: 3,
  maxWallSeconds: 36000,
};
const USAGE = [
  'Usage:',
  '  codex-supervisor run --cwd <abs workspace> --prompt-file <file>',
  '      [--state <file>] [--max-turns N] [--max-resumes N]',
  '      [--max-quota-waits N] [--max-transient-retries N]',
  '      [--max-turn-failures N] [--max-wall-seconds N] [--model <id>]',
  '      [--codex-bin <path>] [--now-source <file>] [--new-run]',
  '  codex-supervisor status --state <file>',
  '  codex-supervisor stop --state <file>',
  '  codex-supervisor reconcile --state <file> --evidence-file <file>',
  'Reconciliation requires a private JSON record: stateHash (SHA-256 of the exact state file),',
  'threadId, turnId (null only for not-started), outcome (completed/failed/interrupted/not-started),',
  'effectsReviewed: true, safeToContinue: true, and evidence (nonempty observation/reference).',
  'Idle detection: wall deadline is the safe bound; tool silence is not an idle stall.',
].join('\n');

// --- small helpers -----------------------------------------------------

class SupervisorError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
const usageError = (m) => new SupervisorError(EXIT_USAGE, m);
const failError = (m) => new SupervisorError(EXIT_FAIL, m);
const ceilingError = (m) => new SupervisorError(EXIT_CEILING, m);

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function rewritePrompt(text) {
  const index = text.search(/\s/);
  const token = index === -1 ? text : text.slice(0, index);
  if (Object.prototype.hasOwnProperty.call(REWRITES, token)) {
    return REWRITES[token] + text.slice(token.length);
  }
  return text;
}

// The image has no copy of the repo's VERSION file, so fall back through the
// in-repo layout (which is what the offline tests exercise) to the shipped
// location, then to a placeholder — never to an invalid clientInfo.version,
// which initialize_processor.rs rejects as an HTTP header value.
function vibeVersion() {
  const here = dirname(fileURLToPath(import.meta.url));
  for (const candidate of [join(here, '..', 'VERSION'), '/usr/local/share/vibe/VERSION']) {
    try {
      const text = readFileSync(candidate, 'utf8').trim();
      if (/^[\x21-\x7e]+$/.test(text)) return text;
    } catch { /* try the next candidate */ }
  }
  return '0.0.0';
}

function insideGitWorkTree(dir) {
  const result = spawnSync('git', ['-C', dir, 'rev-parse', '--is-inside-work-tree'],
    { encoding: 'utf8', input: '', timeout: 10000 });
  return !result.error && result.status === 0 && result.stdout.trim() === 'true';
}

function isDirectory(path) {
  try { return statSync(path).isDirectory(); } catch { return false; }
}

// --- clock (real, or a file the tests own) -----------------------------

class Clock {
  constructor(sourcePath) {
    this.sourcePath = sourcePath || null;
    this.offset = 0;
    this.last = null;
    if (this.sourcePath) this.last = this.readSource();
  }

  readSource() {
    const raw = readFileSync(this.sourcePath, 'utf8').trim();
    const value = Number(raw);
    if (!Number.isFinite(value)) throw usageError(`--now-source: not a unix timestamp: ${raw}`);
    return value;
  }

  now() {
    if (!this.sourcePath) return Math.floor(Date.now() / 1000);
    try { this.last = this.readSource(); } catch { /* keep the last good read */ }
    return Math.floor(this.last + this.offset);
  }

  // AC6: under --now-source every sleep is a no-op, but the computed
  // duration still elapses on the virtual clock, so a wall-clock ceiling
  // can be reached inside a quota wait.
  async sleep(seconds) {
    if (this.sourcePath) { this.offset += seconds; return; }
    if (seconds <= 0) return;
    const end = Date.now() + seconds * 1000;
    while (Date.now() < end) {
      this.checkStop?.();
      await new Promise(resolve => setTimeout(resolve, Math.min(100, end - Date.now())));
    }
  }
}

// --- app-server client -------------------------------------------------

class AppServer {
  constructor(child, log) {
    this.child = child;
    this.log = log;
    this.buffer = '';
    this.pending = new Map();
    this.queue = [];
    this.waiter = null;
    this.nextId = 1;
    this.closed = false;
    this.exitNote = null;
    this.stdinOpen = true;

    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => this.onData(chunk));
    child.stdout.on('end', () => {
      this.exitNote ||= 'app-server connection closed (stdout EOF)';
      this.shutdown();
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => this.log(`[server-stderr] ${String(chunk).trimEnd()}`));
    child.stdin.on('error', () => { this.stdinOpen = false; });
    child.on('exit', (code, signal) => {
      this.exitNote = `app-server exited (code ${code}, signal ${signal})`;
      this.shutdown();
    });
    child.on('error', (error) => {
      this.exitNote = `app-server could not be started: ${error.message}`;
      this.shutdown();
    });
  }

  shutdown() {
    this.closed = true;
    for (const [, entry] of this.pending) {
      clearTimeout(entry.timer);
      entry.reject(failError(this.exitNote || 'app-server connection closed'));
    }
    this.pending.clear();
    if (this.waiter) { const w = this.waiter; this.waiter = null; w.wake(); }
  }

  onData(chunk) {
    this.buffer += chunk;
    let index = this.buffer.indexOf('\n');
    while (index !== -1) {
      const line = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 1);
      this.onLine(line);
      index = this.buffer.indexOf('\n');
    }
  }

  onLine(line) {
    if (!line.trim()) return;
    let message;
    try { message = JSON.parse(line); } catch {
      this.log(`[warn] unparseable line from app-server: ${line.slice(0, 200)}`);
      return;
    }
    if (!isRecord(message)) return;
    const hasId = message.id !== undefined && message.id !== null;
    if (typeof message.method === 'string' && hasId) {
      // Server→client request. An unattended supervisor has nobody to ask,
      // so every one is declined at once and never blocks the turn.
      this.log(`[declined] ${message.method} (id ${message.id})`);
      this.write({ id: message.id, error: { code: -32601, message: 'unattended' } });
      return;
    }
    if (typeof message.method === 'string') { this.push(message); return; }
    if (!hasId) return;
    const entry = this.pending.get(message.id);
    if (!entry) { this.log(`[warn] response for unknown id ${message.id}`); return; }
    this.pending.delete(message.id);
    clearTimeout(entry.timer);
    if (message.error !== undefined && message.error !== null) {
      const detail = isRecord(message.error) ? (message.error.message || JSON.stringify(message.error))
        : String(message.error);
      entry.reject(failError(`${entry.label} failed: ${detail}`));
      return;
    }
    entry.resolve(message.result);
  }

  push(notification) {
    this.queue.push(notification);
    if (this.waiter) { const w = this.waiter; this.waiter = null; w.wake(); }
  }

  write(object) {
    if (!this.stdinOpen) return;
    try { this.child.stdin.write(`${JSON.stringify(object)}\n`); }
    catch { this.stdinOpen = false; }
  }

  // `onTimeout`, when given, builds the rejection error in place of the
  // plain `failError` — AC7a's wall-deadline bounding needs a request that
  // timed out because the wall budget ran out to reject with a ceiling
  // error (exit 3), never the ordinary protocol-timeout `failError` (exit 1).
  request(method, params, { timeoutMs = REQUEST_TIMEOUT_MS, timeoutMessage = null, onTimeout = null } = {}) {
    if (this.closed) return Promise.reject(failError(this.exitNote || 'app-server connection closed'));
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(onTimeout ? onTimeout() : failError(timeoutMessage || `${method} timeout`));
      }, timeoutMs);
      if (typeof timer.unref === 'function') timer.unref();
      this.pending.set(id, { resolve, reject, timer, label: method });
      // Key order here is the wire order asserted by the tests (AC3).
      this.write({ id, method, params });
    });
  }

  // A request whose response we will not wait for (AC7a's `turn/interrupt`,
  // sent as the supervisor is on its way out).
  send(method, params) {
    const id = this.nextId;
    this.nextId += 1;
    this.write({ id, method, params });
    return id;
  }

  async nextNotification() {
    for (;;) {
      if (this.queue.length) return this.queue.shift();
      if (this.closed) throw failError(this.exitNote || 'app-server connection closed');
      await new Promise((resolve) => { this.waiter = { wake: resolve }; });
    }
  }

  closeStdin() {
    if (!this.stdinOpen) return;
    this.stdinOpen = false;
    // stdio mode is single-client: EOF on stdin shuts the server down
    // (app-server/src/lib.rs:1042,1061-1064). No signal or RPC needed.
    try { this.child.stdin.end(); } catch { /* already gone */ }
  }
}

// --- rate limits -------------------------------------------------------

function mergeWindow(previous, update) {
  if (update === undefined || update === null) return previous === undefined ? null : previous;
  return update;
}

// AC5: `account/rateLimits/updated` is a sparse rolling update — merge it
// into the last snapshot rather than replacing it, per window.
export function mergeRateLimits(previous, update) {
  if (!isRecord(update)) return previous ?? null;
  const merged = isRecord(previous) ? { ...previous } : {};
  for (const [key, value] of Object.entries(update)) {
    if (value !== null && value !== undefined) merged[key] = value;
  }
  merged.primary = mergeWindow(isRecord(previous) ? previous.primary : undefined, update.primary);
  merged.secondary = mergeWindow(isRecord(previous) ? previous.secondary : undefined, update.secondary);
  return merged;
}

// AC6: the binding window is the exhausted one (the later reset if both are
// exhausted), otherwise the window that resets later. Returns its resetsAt
// in unix SECONDS, or null when no reset time is known.
export function bindingResetsAt(snapshot) {
  const windows = [];
  if (isRecord(snapshot?.primary)) windows.push(snapshot.primary);
  if (isRecord(snapshot?.secondary)) windows.push(snapshot.secondary);
  const exhausted = windows.filter((w) => Number(w.usedPercent) >= 100);
  const pool = exhausted.length ? exhausted : windows;
  let latest = null;
  for (const window of pool) {
    // `resetsAt` is Option<i64> on the wire: an absent window reset arrives
    // as null, and Number(null) is 0 — never treat that as a reset time.
    if (window.resetsAt === null || window.resetsAt === undefined) continue;
    const resets = Number(window.resetsAt);
    if (Number.isFinite(resets) && (latest === null || resets > latest)) latest = resets;
  }
  return latest;
}

export function backoffSeconds(ladder, index) {
  const capped = Math.min(index, ladder.length - 1);
  return Math.min(ladder[capped < 0 ? 0 : capped], BACKOFF_CAP);
}

// --- error classification ---------------------------------------------

// `codexErrorInfo` is externally tagged: `"usageLimitExceeded"` for a unit
// variant, `{"httpConnectionFailed":{"httpStatusCode":429}}` for a struct one.
export function classifyError(info) {
  if (typeof info === 'string') {
    if (QUOTA_ERRORS.has(info)) return { kind: 'quota', name: info };
    if (FATAL_ERRORS.has(info)) return { kind: 'fatal', name: info };
    if (TRANSIENT_ERRORS.has(info)) return { kind: 'transient', name: info };
    return { kind: 'other', name: info };
  }
  if (isRecord(info)) {
    const keys = Object.keys(info);
    if (keys.length === 1) {
      const name = keys[0];
      const body = info[name];
      if (QUOTA_ERRORS.has(name)) return { kind: 'quota', name };
      if (FATAL_ERRORS.has(name)) return { kind: 'fatal', name };
      if (TRANSIENT_ERRORS.has(name)) return { kind: 'transient', name };
      if (name === 'httpConnectionFailed' && Number(isRecord(body) ? body.httpStatusCode : NaN) === 429) {
        return { kind: 'transient', name };
      }
      return { kind: 'other', name };
    }
  }
  return { kind: 'other', name: 'unknown' };
}

// AC7: the exit line must stand alone at the start of a line.
export function exitReasonFrom(text) {
  if (typeof text !== 'string') return null;
  const lines = text.trimEnd().split(/\r?\n/);
  let fence = null;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const marker = /^ {0,3}(\`{3,}|~{3,})(.*)$/.exec(line);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
      continue;
    }
    if (i === lines.length - 1 && !fence) {
      const match = /^VSSS-EXIT: +(.+)$/.exec(line);
      return match && match[1].trim() ? match[1].trim() : null;
    }
  }
  return null;
}

function lastAgentMessageText(turn) {
  const items = Array.isArray(turn?.items) ? turn.items : [];
  let text = null;
  for (const item of items) {
    if (isRecord(item) && item.type === 'agentMessage' && typeof item.text === 'string') text = item.text;
  }
  return text;
}

// --- argument parsing --------------------------------------------------

const STRING_FLAGS = {
  '--cwd': 'cwd',
  '--prompt-file': 'promptFile',
  '--state': 'state',
  '--model': 'model',
  '--codex-bin': 'codexBin',
  '--now-source': 'nowSource',
  '--evidence-file': 'evidenceFile',
};
const NUMBER_FLAGS = {
  '--max-turns': 'maxTurns',
  '--max-resumes': 'maxResumes',
  '--max-quota-waits': 'maxQuotaWaits',
  '--max-transient-retries': 'maxTransientRetries',
  '--max-turn-failures': 'maxTurnFailures',
  '--max-wall-seconds': 'maxWallSeconds',
};

export function parseArgs(argv) {
  const command = argv[0];
  if (command === undefined || command === '--help' || command === '-h' || command === 'help') {
    throw usageError(USAGE);
  }
  if (!['run', 'status', 'stop', 'reconcile'].includes(command)) throw usageError(`unknown command: ${command}\n${USAGE}`);
  const options = { command, newRun: false, ...DEFAULTS };
  for (let i = 1; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === '--new-run') { options.newRun = true; continue; }
    const stringKey = STRING_FLAGS[flag];
    const numberKey = NUMBER_FLAGS[flag];
    if (!stringKey && !numberKey) throw usageError(`unknown argument: ${flag}\n${USAGE}`);
    const value = argv[i + 1];
    if (value === undefined || value.startsWith('--')) throw usageError(`${flag} needs a value`);
    i += 1;
    if (stringKey) { options[stringKey] = value; continue; }
    // AC7 (Astra review): every ceiling must be ≥ 1 — a 0 ceiling would be
    // breached before the first turn and is always a mistake, not a request.
    if (!/^\d+$/.test(value)) throw usageError(`${flag} needs a positive integer, got: ${value}`);
    if (!Number.isSafeInteger(Number(value)) || Number(value) < 1) throw usageError(`${flag} must be at least 1, got: ${value}`);
    options[numberKey] = Number(value);
  }
  if (command === 'reconcile') {
    if (!options.state || !options.evidenceFile) throw usageError(USAGE);
    if (argv.slice(1).some((value, i) => i % 2 === 0 && !['--state', '--evidence-file'].includes(value))) throw usageError('reconcile takes only --state and --evidence-file');
    return options;
  }
  if (options.evidenceFile) throw usageError('--evidence-file is only valid for reconcile');
  if (command === 'status' || command === 'stop') {
    if (!options.state) throw usageError('status needs --state <file>');
    if (options.cwd || options.promptFile || options.newRun) {
      throw usageError('status takes only --state');
    }
    return options;
  }
  if (!options.cwd) throw usageError('run needs --cwd <abs workspace>');
  if (!options.promptFile) throw usageError('run needs --prompt-file <file>');
  if (!isAbsolute(options.cwd)) throw usageError(`--cwd must be an absolute path: ${options.cwd}`);
  if (!isDirectory(options.cwd)) throw usageError(`--cwd is not a directory: ${options.cwd}`);
  if (!insideGitWorkTree(options.cwd)) throw usageError(`--cwd is not inside a git work tree: ${options.cwd}`);
  options.cwd = realpathSync(options.cwd);
  if (!options.state) options.state = join(options.cwd, '.vss', 'codex-supervisor.json');
  if (!options.codexBin) options.codexBin = 'codex';
  if (options.nowSource && !existsSync(options.nowSource)) {
    throw usageError(`--now-source file not found: ${options.nowSource}`);
  }
  return options;
}

// --- state -------------------------------------------------------------

function freshState(threadId, cwd, promptHash, startedAt) {
  return {
    threadId,
    cwd,
    promptHash,
    startedAt,
    turns: [],
    turnsStarted: 0,
    resumes: 0,
    quotaWaits: 0,
    transientRetries: 0,
    turnFailures: 0,
    lastRateLimits: null,
    waits: [],
    turnSafetyVersion: 1,
    unresolvedTurn: null,
  };
}

// AC4: every counter change lands on disk, and it lands atomically —
// a torn state file would strand the next resume.
function writeStateFile(path, state) {
  atomicWrite(path, `${JSON.stringify(state, null, 2)}\n`);
}

function needsTurnReconciliation(state) {
  return state.unresolvedTurn != null || state.activeTurn != null
    || ['turn/start', 'turn'].includes(state.operation)
    || (state.turnSafetyVersion !== 1 && Number(state.turnsStarted || 0) > (state.turns?.length || 0));
}

// Explicit operator evidence, bound to the exact checkpoint under its lock.
// This operation sends no RPC and never replays the ambiguous input.
function reconcileTurn(options) {
  const path = canonicalPath(options.state);
  if (/\.(log|lock)$/.test(path) || /\.stop\./.test(path)) throw usageError('state path conflicts with a reserved log/control path');
  const owner = acquire(path);
  try {
    const raw = readRegular(path);
    const state = JSON.parse(raw);
    if (!isRecord(state) || !needsTurnReconciliation(state)) throw usageError('no unresolved turn to reconcile');
    if (state.statePath !== undefined && state.statePath !== path) throw usageError('state path binding mismatch');
    const evidence = JSON.parse(readRegular(options.evidenceFile));
    if (!isRecord(evidence)
      || evidence.stateHash !== createHash('sha256').update(raw).digest('hex')
      || typeof state.threadId !== 'string' || !state.threadId || evidence.threadId !== state.threadId
      || !['completed', 'failed', 'interrupted', 'not-started'].includes(evidence.outcome)
      || evidence.effectsReviewed !== true || evidence.safeToContinue !== true
      || typeof evidence.evidence !== 'string' || !evidence.evidence.trim()) {
      throw usageError('reconciliation requires matching checkpoint evidence and explicit review of effects; see help');
    }
    const knownId = state.unresolvedTurn?.turnId ?? state.activeTurn;
    if (evidence.outcome === 'not-started'
      ? evidence.turnId !== null || knownId != null
      : typeof evidence.turnId !== 'string' || !evidence.turnId || (knownId != null && evidence.turnId !== knownId)) {
      throw usageError('reconciliation turn identity/outcome mismatch');
    }
    if (!Array.isArray(state.reconciliations ?? [])) throw usageError('invalid reconciliation history');
    if (state.turnsStarted === undefined && Array.isArray(state.turns)) state.turnsStarted = state.turns.length;
    if (!Array.isArray(state.turns) || !Number.isSafeInteger(state.turnsStarted)
      || state.turnsStarted < state.turns.length || !Number.isSafeInteger(state.turnFailures)
      || state.turnFailures < 0) throw usageError('invalid persisted turn counters');
    state.reconciliations = [...(state.reconciliations || []), {
      at: Math.floor(Date.now() / 1000), unresolvedTurn: state.unresolvedTurn ?? null, ...evidence,
    }];
    if (evidence.outcome === 'completed' && !state.turns.some(turn => turn.turnId === evidence.turnId)) {
      state.turns.push({ turnId: evidence.turnId, status: 'completed', at: Math.floor(Date.now() / 1000) });
    }
    if (evidence.outcome === 'failed') state.turnFailures += 1;
    // A resolved attempt still consumed the initial prompt slot: even evidence
    // of non-start does not authorize automatic replay of that prompt.
    state.turnsStarted = Math.max(1, Number(state.turnsStarted || 0), state.turns?.length || 0);
    state.turnSafetyVersion = 1;
    state.unresolvedTurn = null;
    delete state.activeTurn;
    state.operation = 'turn-boundary';
    state.lifecycle = 'checkpointed';
    state.recoveryReason = 'turn-reconciled';
    writeStateFile(path, state);
    process.stdout.write('turn reconciled; no turn submitted\n');
    return EXIT_OK;
  } finally { owner.release(); }
}

// --- the supervisor ----------------------------------------------------

class Supervisor {
  constructor(options) {
    this.options = options;
    this.statePath = canonicalPath(options.state, true);
    options.state = this.statePath;
    if (/\.(log|lock)$/.test(this.statePath) || /\.stop\./.test(this.statePath)) throw usageError('state path conflicts with a reserved log/control path');
    this.stateDir = dirname(this.statePath);
    this.logPath = join(this.stateDir, 'codex-supervisor.log');
    if (!this.statePath.endsWith('/codex-supervisor.json')) this.logPath = `${this.statePath}.log`;
    canonicalPath(this.logPath);
    const inputs = [options.promptFile, options.nowSource].filter(Boolean).map(p => realpathSync(p));
    if ([this.statePath, this.logPath, `${this.statePath}.lock`].some(p => inputs.includes(p))) throw usageError('state/log/control paths must be distinct from input files');
    this.clock = new Clock(options.nowSource);
    this.clock.checkStop = () => this.checkStop();
    this.state = null;
    this.server = null;
    this.quotaBlindIndex = 0;
  }

  log(line) {
    const stamp = new Date(this.clock.now() * 1000).toISOString();
    try { appendRegular(this.logPath, `\n[${stamp}] ${line}\n`); } catch { /* logging is best effort */ }
  }

  logRaw(text) {
    try { appendRegular(this.logPath, text); } catch { /* logging is best effort */ }
  }

  persist() {
    this.state.statePath = this.statePath;
    this.state.lifecycle = this.state.exitReason !== undefined ? 'complete' : (this.finishing ? 'checkpointed' : 'running');
    this.state.operation = this.operation || 'starting';
    writeStateFile(this.statePath, this.state);
  }

  checkStop() {
    if (this.stopRequested || this.owner?.stopped()) {
      this.stopRequested = true;
      if (this.activeTurn && this.server) this.server.send('turn/interrupt', { threadId: this.state.threadId, turnId: this.activeTurn });
      throw new SupervisorError(EXIT_SIGNAL, 'stop requested; checkpoint saved; resume with the same run arguments');
    }
  }

  async cancellable(promise) {
    this.checkStop();
    let timer;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timer = setInterval(() => { try { this.checkStop(); } catch (e) { reject(e); } }, 100);
      })]);
    } finally { clearInterval(timer); }
  }

  async sleep(seconds) {
    this.checkStop();
    await this.cancellable(this.clock.sleep(seconds));
  }


  // The instant the wall ceiling bites, in the clock's own units. Every
  // deadline decision (awaiting a turn, capping a wait, honouring an
  // outstanding one) is expressed against this single value. Before
  // `this.state` exists — during the pre-thread-start handshake and the
  // initial `account/rateLimits/read` (AC7a) — it falls back to
  // `startedAtAnchor`, set once at the top of `run()` (the original
  // `startedAt` on a resumed run, `now()` on a fresh one).
  deadline(state = this.state) {
    const startedAt = state ? state.startedAt : this.startedAtAnchor;
    return Number(startedAt) + this.options.maxWallSeconds;
  }

  // AC7a (Astra re-review): every outstanding request — initialize,
  // account/rateLimits/read, thread/start, thread/resume, turn/start — is
  // bounded by the SMALLER of its own limit and the remaining wall budget.
  // When the wall budget is what actually cuts the wait short, a timeout
  // ends the run with exit 3 naming max-wall-seconds — never the ordinary
  // exit 1 protocol timeout, which still applies when the request's own
  // limit is the binding one.
  async boundedRequest(method, params, { timeoutMs = REQUEST_TIMEOUT_MS, timeoutMessage = null } = {}) {
    const remainingMs = Math.max(0, (this.deadline() - this.clock.now()) * 1000);
    const wallBound = remainingMs < timeoutMs;
    this.checkStop();
    this.operation = method;
    if (this.state) this.persist();
    return this.cancellable(this.server.request(method, params, {
      timeoutMs: Math.min(timeoutMs, remainingMs),
      onTimeout: () => (wallBound
        ? ceilingError(`ceiling reached: max-wall-seconds (${this.options.maxWallSeconds}) `
          + `while awaiting ${method}`)
        : failError(timeoutMessage || `${method} timeout`)),
    }));
  }

  // AC7: every ceiling is checked at every decision point.
  checkGates(state = this.state) {
    this.checkStop();
    const o = this.options;
    if (state.turns.length >= o.maxTurns) throw ceilingError(`ceiling reached: max-turns (${o.maxTurns})`);
    if (state.resumes >= o.maxResumes) throw ceilingError(`ceiling reached: max-resumes (${o.maxResumes})`);
    if (state.quotaWaits >= o.maxQuotaWaits) {
      throw ceilingError(`ceiling reached: max-quota-waits (${o.maxQuotaWaits})`);
    }
    if (state.transientRetries >= o.maxTransientRetries) {
      throw ceilingError(`ceiling reached: max-transient-retries (${o.maxTransientRetries})`);
    }
    // AC7 (Astra review): without this gate a resumed run could carry an
    // already-exhausted turnFailures count straight back into the loop.
    if (Number(state.turnFailures) >= o.maxTurnFailures) {
      throw ceilingError(`ceiling reached: max-turn-failures (${o.maxTurnFailures})`);
    }
    const elapsed = this.clock.now() - Number(state.startedAt);
    if (elapsed >= o.maxWallSeconds) {
      throw ceilingError(`ceiling reached: max-wall-seconds (${o.maxWallSeconds}, elapsed ${elapsed}s)`);
    }
  }

  spawnServer() {
    const env = {
      PATH: process.env.PATH || '/usr/local/bin:/usr/bin:/bin',
      HOME: process.env.HOME || homedir(),
      CODEX_HOME: this.codexHome,
      LANG: process.env.LANG || 'C.UTF-8',
      ...(this.taskRef ? { VIBE_TASK_REF: this.taskRef } : {}),
      VIBE_TASK_BINDING: this.taskBinding,
    };
    // argv is exactly ['app-server']: no `-c`, so the image's system
    // requirements and managed hooks apply unmodified. The server's working
    // directory is deliberately left alone — the workspace travels in
    // `thread/start.cwd`.
    const child = spawnOwnedServer(this.options.codexBin, env);
    this.server = new AppServer(child, (line) => this.log(line));
  }

  async handshake() {
    const params = {
      clientInfo: { name: CLIENT_NAME, version: vibeVersion() },
      capabilities: {},
    };
    await this.boundedRequest('initialize', params, {
      timeoutMs: HANDSHAKE_TIMEOUT_MS, timeoutMessage: 'handshake timeout',
    });
    this.log('initialize acknowledged');
  }

  async readRateLimits() {
    const result = await this.boundedRequest('account/rateLimits/read', {});
    if (isRecord(result) && result.rateLimits !== undefined) {
      this.applyRateLimits(result.rateLimits);
    }
  }

  applyRateLimits(snapshot) {
    const merged = mergeRateLimits(this.state ? this.state.lastRateLimits : null, snapshot);
    if (this.state) {
      this.state.lastRateLimits = merged;
      this.persist();
    } else {
      this.pendingRateLimits = merged;
    }
  }

  loadState() {
    if (!existsSync(this.statePath)) return null;
    let parsed;
    try { parsed = JSON.parse(readRegular(this.statePath)); }
    catch { parsed = null; }
    if (!isRecord(parsed)) {
      if (this.options.newRun) return { corrupt: true };
      throw usageError(`state file is not readable JSON: ${this.statePath} (pass --new-run to start fresh)`);
    }
    return parsed;
  }

  archiveState(previous) {
    const startedAt = Number(previous?.startedAt);
    const stamp = Number.isFinite(startedAt) ? startedAt : this.clock.now();
    const archive = this.statePath.endsWith('/codex-supervisor.json')
      ? join(this.stateDir, `codex-supervisor.${stamp}.json`)
      : `${this.statePath}.${stamp}.archive.json`;
    if (existsSync(archive)) throw usageError(`archive already exists: ${archive}; reconcile explicitly`);
    renameSync(this.statePath, archive);
    this.log(`--new-run: archived previous state to ${archive}`);
    return archive;
  }

  // AC4: a state file only resumes when BOTH cwd and promptHash match.
  adoptState(previous, promptHash) {
    if (!previous) return null;
    if (needsTurnReconciliation(previous)) throw failError('unresolved turn: review prior effects and use reconcile --state <file> --evidence-file <file> before run or --new-run');
    if (this.options.newRun) { this.archiveState(previous.corrupt ? null : previous); return null; }
    if (previous.cwd !== this.options.cwd) {
      throw usageError(`state file cwd mismatch: state has ${previous.cwd}, --cwd is ${this.options.cwd} `
        + '(pass --new-run to archive it and start fresh)');
    }
    if ((previous.taskBinding || 'unbound') !== this.taskBinding) throw usageError('effective Task&I binding changed; resume with the original endpoint and node mapping');
    if ((previous.taskRef || '') !== this.taskRef) throw usageError('state task binding mismatch; resume with the original --task reference');
    if (previous.promptHash !== promptHash) {
      throw usageError(`state file promptHash mismatch: state has ${previous.promptHash}, prompt hashes to `
        + `${promptHash} (pass --new-run to archive it and start fresh)`);
    }
    if (typeof previous.threadId !== 'string' || !previous.threadId) {
      throw usageError(`state file has no threadId: ${this.statePath} (reconcile the unconfirmed thread/start in Codex before explicitly using --new-run)`);
    }
    if (previous.statePath !== undefined && previous.statePath !== this.statePath) throw usageError('state path binding mismatch');
    if (!Number.isSafeInteger(previous.startedAt) || previous.startedAt < 0 || !Array.isArray(previous.turns) || !Array.isArray(previous.waits)) throw usageError('invalid persisted state');
    for (const key of ['resumes', 'quotaWaits', 'transientRetries', 'turnFailures']) {
      if (!Number.isSafeInteger(previous[key]) || previous[key] < 0) throw usageError(`invalid persisted counter: ${key}`);
    }
    // Legacy snapshots predate turnsStarted. Completed turns are a conservative lower bound.
    if (previous.turnsStarted === undefined) previous.turnsStarted = previous.turns.length;
    if (!Number.isSafeInteger(previous.turnsStarted) || previous.turnsStarted < previous.turns.length) throw usageError('invalid persisted turnsStarted');
    for (const wait of previous.waits) {
      if (!isRecord(wait) || !Number.isFinite(wait.until) || !Number.isFinite(wait.seconds) || wait.seconds < 0) throw usageError('invalid persisted wait');
    }
    const state = freshState(previous.threadId, previous.cwd, previous.promptHash,
      previous.startedAt);
    state.turns = Array.isArray(previous.turns) ? previous.turns : [];
    state.waits = Array.isArray(previous.waits) ? previous.waits : [];
    for (const key of ['turnsStarted', 'resumes', 'quotaWaits', 'transientRetries', 'turnFailures']) {
      state[key] = Number.isFinite(Number(previous[key])) ? Number(previous[key]) : 0;
    }
    state.lastRateLimits = previous.lastRateLimits ?? null;
    state.reconciliations = previous.reconciliations ?? [];
    // AC4 (Astra review): `exitReason` makes the state TERMINAL. It must
    // survive adoption, or a finished run would silently start over.
    if (previous.exitReason !== undefined && (typeof previous.exitReason !== 'string' || !previous.exitReason.trim())) throw usageError('invalid persisted terminal reason');
    if (previous.exitReason !== undefined && previous.exitReason !== null) {
      state.exitReason = previous.exitReason;
    }
    return state;
  }

  // AC4 (Astra review): a wait recorded before the process went away is
  // still owed. Honour what is left of it before touching the server —
  // re-sending a turn into an exhausted quota window just burns a failure.
  async honourOutstandingWait(state) {
    const waits = Array.isArray(state.waits) ? state.waits : [];
    const last = waits.length ? waits[waits.length - 1] : null;
    if (!isRecord(last)) return;
    const until = Number(last.until);
    if (!Number.isFinite(until)) return;
    const now = this.clock.now();
    if (until <= now) return;
    const deadline = this.deadline(state);
    if (until > deadline) {
      throw ceilingError(`ceiling reached: max-wall-seconds (${this.options.maxWallSeconds}): the `
        + `outstanding ${last.reason} wait ends ${until - deadline}s past the ceiling; not sleeping`);
    }
    this.log(`honouring the outstanding ${last.reason} wait: ${until - now}s left until `
      + `${new Date(until * 1000).toISOString()}`);
    await this.sleep(until - now);
  }

  async startThread(promptHash) {
    const params = {
      cwd: this.options.cwd,
      approvalPolicy: 'never',
      sandbox: 'danger-full-access',
      ephemeral: false,
    };
    if (this.options.model) params.model = this.options.model;
    this.state.recoveryReason = 'thread-start-unconfirmed';
    this.persist();
    const result = await this.boundedRequest('thread/start', params);
    const threadId = result?.thread?.id;
    if (typeof threadId !== 'string' || !threadId) throw failError('thread/start returned no thread id');
    this.state.threadId = threadId;
    delete this.state.recoveryReason;
    if (this.pendingRateLimits !== undefined) this.state.lastRateLimits = this.pendingRateLimits;
    this.persist();
    this.log(`thread/start → ${threadId}`);
  }

  async resumeThread(state) {
    this.state = state;
    // AC4 (Astra re-review): the snapshot read at the start of THIS run is
    // merged into the adopted lastRateLimits per window — the persisted
    // copy is never preferred over the fresher one, even when it is
    // non-null (a stale persisted resetsAt in the past would otherwise
    // produce repeated zero-second quota waits).
    if (this.pendingRateLimits !== undefined) {
      this.state.lastRateLimits = mergeRateLimits(this.state.lastRateLimits, this.pendingRateLimits);
    }
    // Gates first: a run that is already over a ceiling must not touch the
    // server at all.
    this.checkGates(state);
    this.state.resumes += 1;
    this.persist();
    const result = await this.boundedRequest('thread/resume', { threadId: state.threadId });
    if (result?.thread?.id !== state.threadId) throw failError('thread/resume returned a mismatched thread');
    this.log(`thread/resume → ${state.threadId} (resume ${this.state.resumes})`);
  }

  // AC7(a): awaiting a turn is the one place the supervisor could otherwise
  // block for ever — a silent server, or one that retries internally without
  // ever completing the turn. Race the next notification against the wall
  // deadline. With a real clock one timer suffices; with `--now-source` the
  // clock only moves when the file does, so poll it (cheaply, unref'd) and
  // fire as soon as an observation lands past the deadline.
  async nextNotificationOrDeadline() {
    const deadline = this.deadline();
    if (this.clock.now() >= deadline) return { expired: true };
    let timer = null;
    const expiry = new Promise((resolve) => {
      if (this.clock.sourcePath) {
        timer = setInterval(() => { if (this.clock.now() >= deadline) resolve(); }, 100);
      } else {
        timer = setInterval(() => { if (this.clock.now() >= deadline) resolve(); }, 100);
      }
      if (typeof timer.unref === 'function') timer.unref();
    });
    try {
      return await this.cancellable(Promise.race([
        this.server.nextNotification().then((message) => ({ message })),
        expiry.then(() => ({ expired: true })),
      ]));
    } finally {
      clearTimeout(timer);
      clearInterval(timer);
    }
  }

  // AC7(a): interrupt the turn, close the server's stdin (it exits on EOF),
  // write the state, and leave with the ceiling exit code.
  expireDuringTurn(turnId) {
    const elapsed = this.clock.now() - Number(this.state.startedAt);
    this.log(`wall deadline reached while awaiting turn ${turnId || '(no id)'}: interrupting`);
    if (turnId) this.server.send('turn/interrupt', { threadId: this.state.threadId, turnId });
    this.server.closeStdin();
    try { this.persist(); } catch { /* best effort */ }
    throw ceilingError(`ceiling reached: max-wall-seconds (${this.options.maxWallSeconds}, elapsed `
      + `${elapsed}s) while awaiting a turn; sent turn/interrupt`);
  }

  // One turn: start it, then drain notifications until its `turn/completed`.
  async runTurn(text) {
    if (needsTurnReconciliation(this.state)) throw failError('unresolved turn requires explicit reconciliation');
    // AC4 (cycle-2 Tester finding): incremented and persisted ATOMICALLY
    // immediately before every `turn/start` — including re-sends after a
    // quota/transient/turn-failure wait — so a turn killed mid-flight
    // (leaving `turns` empty) is still distinguishable on resume from a
    // turn that was never started.
    this.state.turnsStarted = Number(this.state.turnsStarted || 0) + 1;
    this.state.unresolvedTurn = {
      attemptId: randomUUID(), threadId: this.state.threadId,
      turnId: null, at: this.clock.now(),
    };
    this.persist();
    const result = await this.boundedRequest('turn/start', {
      threadId: this.state.threadId,
      input: [{ type: 'text', text }],
    });
    const turnId = typeof result?.turn?.id === 'string' ? result.turn.id : null;
    if (!turnId) throw failError('turn/start returned no turn id; resume requires reconciliation');
    this.activeTurn = turnId;
    this.state.unresolvedTurn.turnId = turnId;
    this.operation = 'turn';
    this.persist();
    this.log(`turn/start → ${turnId || '(no id)'}`);
    let lastAgentMessage = null;
    for (;;) {
      const next = await this.nextNotificationOrDeadline();
      if (next.expired) this.expireDuringTurn(turnId);
      const message = next.message;
      const params = isRecord(message.params) ? message.params : {};
      if (['turn/completed', 'item/completed'].includes(message.method) && params.threadId !== this.state.threadId) continue;
      if (params.threadId !== undefined && params.threadId !== this.state.threadId) continue;
      const sameTurn = params.turnId === turnId;
      switch (message.method) {
        case 'turn/completed': {
          const turn = isRecord(params.turn) ? params.turn : {};
          if (turn.id !== turnId || (params.turnId !== undefined && !sameTurn)) {
            this.log(`[warn] turn/completed for another turn (${turn.id})`);
            break;
          }
          this.activeTurn = null;
          const text0 = lastAgentMessageText(turn) ?? lastAgentMessage;
          return { turn, turnId: turnId || turn.id || null, agentMessage: text0 };
        }
        case 'item/completed': {
          const item = isRecord(params.item) ? params.item : {};
          if (sameTurn && item.type === 'agentMessage' && typeof item.text === 'string') {
            lastAgentMessage = item.text;
          }
          break;
        }
        case 'item/agentMessage/delta': {
          if (typeof params.delta === 'string') this.logRaw(params.delta);
          break;
        }
        case 'error': {
          const willRetry = params.willRetry === true;
          const detail = isRecord(params.error) ? params.error.message : '';
          this.log(`[server-error] willRetry=${willRetry} ${detail || ''}`.trimEnd());
          break;
        }
        case 'account/rateLimits/updated': {
          this.applyRateLimits(params.rateLimits);
          break;
        }
        default:
          break;
      }
    }
  }

  // AC7(b): a wait is only ever taken if it ends inside the wall budget. The
  // wait that WOULD have been taken is still recorded — the state file is
  // the record of why the run stopped — and then the ceiling fires instead
  // of a sleep that could never have been useful.
  recordWait(reason, seconds, detail) {
    const until = this.clock.now() + seconds;
    this.operation = `${reason}-wait`;
    this.state.waits.push({ reason, seconds, until });
    this.persist();
    this.log(`wait ${seconds}s (${reason}${detail ? `: ${detail}` : ''}) until `
      + `${new Date(until * 1000).toISOString()}`);
    const deadline = this.deadline();
    if (until > deadline) {
      throw ceilingError(`ceiling reached: max-wall-seconds (${this.options.maxWallSeconds}): a `
        + `${seconds}s ${reason} wait would end ${until - deadline}s past the ceiling; not sleeping`);
    }
  }

  async quotaWait(name) {
    this.checkGates();
    const resetsAt = bindingResetsAt(this.state.lastRateLimits);
    let seconds;
    let blind = false;
    if (resetsAt === null) {
      blind = true;
      seconds = backoffSeconds(QUOTA_BACKOFF, this.quotaBlindIndex);
      this.quotaBlindIndex += 1;
    } else {
      seconds = Math.max(0, (resetsAt + QUOTA_GRACE_SECONDS) - this.clock.now());
    }
    this.state.quotaWaits += 1;
    this.persist();
    this.recordWait('quota', seconds, name);
    await this.sleep(seconds);
    // A blind wait learns nothing from the clock, so re-read the snapshot
    // before the next attempt (AC6).
    if (blind) await this.readRateLimits();
  }

  async transientWait(name) {
    this.checkGates();
    const seconds = backoffSeconds(TRANSIENT_BACKOFF, this.state.transientRetries);
    this.state.transientRetries += 1;
    this.persist();
    this.recordWait('transient', seconds, name);
    await this.sleep(seconds);
  }

  confirmTurnBoundary() {
    const unresolved = this.state.unresolvedTurn;
    this.state.unresolvedTurn = null;
    this.operation = 'turn-boundary';
    try { this.persist(); }
    catch (error) {
      this.state.unresolvedTurn = unresolved;
      throw error;
    }
  }

  async loop(firstText) {
    let text = firstText;
    for (;;) {
      this.checkGates();
      const { turn, turnId, agentMessage } = await this.runTurn(text);
      // AC5 (Astra re-review): the user's rewritten prompt is sent EXACTLY
      // ONCE per thread — for the very first `turn/start` only. `runTurn`
      // has now sent whatever `text` held, so every `turn/start` after this
      // point in this run — after a completed turn, a quota wait, a
      // transient back-off or a turn failure — is the literal `continue`;
      // the thread already holds the prompt and whatever was done, so
      // re-sending it could repeat actions.
      text = 'continue';
      const status = turn.status;
      if (status === 'completed') {
        this.state.turns.push({
          turnId: turnId || null,
          status: 'completed',
          at: this.clock.now(),
        });
        const reason = exitReasonFrom(agentMessage);
        if (reason !== null) this.state.exitReason = reason;
        this.confirmTurnBoundary();
        if (reason !== null) {
          this.log(`VSSS-EXIT: ${reason}`);
          return EXIT_OK;
        }
        this.quotaBlindIndex = 0;
        continue;
      }
      if (status === 'interrupted') {
        throw failError('turn interrupted by someone else; not restarting');
      }
      if (status !== 'failed') {
        throw failError(`unexpected turn status: ${String(status)}`);
      }
      this.confirmTurnBoundary();
      const error = isRecord(turn.error) ? turn.error : {};
      const info = classifyError(error.codexErrorInfo);
      const detail = typeof error.message === 'string' ? error.message : '';
      this.log(`turn failed: ${info.name} (${info.kind})${detail ? ` — ${detail}` : ''}`);
      if (info.kind === 'fatal') {
        this.state.recoveryReason = info.name === 'contextWindowExceeded' ? 'context-exhausted' : 'budget-exhausted';
        throw failError(`turn failed: ${info.name}; checkpoint saved. Resume this thread after compacting context or resolving its budget; ceilings are preserved.`);
      }
      if (info.kind === 'quota') { await this.quotaWait(info.name); continue; }
      if (info.kind === 'transient') { await this.transientWait(info.name); continue; }
      this.state.turnFailures += 1;
      this.persist();
      if (this.state.turnFailures >= this.options.maxTurnFailures) {
        throw failError(`turn failed ${this.state.turnFailures} times (max-turn-failures `
          + `${this.options.maxTurnFailures}); last message: ${detail || info.name}`);
      }
    }
  }

  async run() {
    const options = this.options;
    let promptRaw;
    try { promptRaw = readFileSync(options.promptFile, 'utf8'); }
    catch { throw usageError(`--prompt-file cannot be read: ${options.promptFile}`); }
    this.taskRef = process.env.VIBE_TASK_REF || '';
    if (this.taskRef && !/^(?:[A-Za-z][A-Za-z0-9]*-[0-9]+|taskandeye:\/\/node\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/.test(this.taskRef)) throw usageError('invalid launch task binding');
    this.taskBinding = bindingFingerprint(loadConfig(options.cwd));
    const promptHash = createHash('sha256').update(promptRaw).digest('hex');
    const promptText = rewritePrompt(promptRaw.replace(/\s+$/, ''));
    if (!promptText) throw usageError(`--prompt-file is empty: ${options.promptFile}`);

    this.codexHome = process.env.CODEX_HOME || join(process.env.HOME || homedir(), '.codex');
    if (!isDirectory(this.codexHome)) {
      throw usageError(`CODEX_HOME does not exist: ${this.codexHome}`);
    }

    mkdirSync(this.stateDir, { recursive: true });
    const previous = this.loadState();
    const resumed = this.adoptState(previous, promptHash);
    // AC4 (Astra review): a state file that records an exitReason is done.
    // Re-running it would restart a completed job; `--new-run` is the only
    // way to start over, and it has already archived this file if passed.
    if (resumed && resumed.exitReason !== undefined) {
      process.stdout.write(`already complete: ${resumed.exitReason}\n`);
      return EXIT_OK;
    }
    if (resumed) {
      this.state = resumed;
      this.state.taskRef = this.taskRef;
      this.state.taskBinding = this.taskBinding;
      // Gates BEFORE anything is sent, then any wait the previous process
      // still owed — both without spawning a server we may never use.
      this.checkGates(resumed);
      await this.honourOutstandingWait(resumed);
      this.checkGates(resumed);
    }
    // AC7a: anchors the wall deadline for the pre-thread-start requests
    // (initialize, the initial account/rateLimits/read, and thread/start
    // itself) before `this.state` exists. A resumed run reuses the
    // ORIGINAL startedAt; a fresh run anchors to now, and startThread()
    // persists this same instant as the new state's startedAt.
    this.startedAtAnchor = resumed ? Number(resumed.startedAt) : this.clock.now();

    if (!this.state) {
      this.state = freshState(null, options.cwd, promptHash, this.startedAtAnchor);
      this.state.taskRef = this.taskRef;
      this.state.taskBinding = this.taskBinding;
      this.state.recoveryReason = 'thread-start-unconfirmed';
      this.persist();
    }
    this.spawnServer();

    try {
      await this.handshake();
      await this.readRateLimits();
      let firstText = promptText;
      if (resumed) {
        await this.resumeThread(resumed);
        // AC4 (cycle-2 Tester finding): `turns.length` alone can't tell
        // "killed in flight" from "never started" — a turn that never
        // reached `turn/completed` leaves `turns` empty either way. The
        // persisted `turnsStarted` counter (incremented atomically right
        // before every `turn/start`) is authoritative: any turn ever
        // started means the thread has already seen the prompt, so the
        // resume nudges it with the literal `continue`; only a thread
        // that never got a `turn/start` at all gets the rewritten prompt.
        if (Number(resumed.turnsStarted || 0) >= 1) firstText = 'continue';
      } else {
        await this.startThread(promptHash);
      }
      for (;;) {
        try { return await this.loop(firstText); }
        catch (error) {
          // Only a confirmed turn boundary permits automatic restart. A lost
          // turn/start reply or active turn is ambiguous and is never replayed.
          if (!this.server.closed || this.activeTurn || needsTurnReconciliation(this.state) || this.stopRequested) throw error;
          this.state.recoveryReason = 'connection-lost-at-turn-boundary';
          this.persist();
          await closeServer(this.server);
          await this.transientWait('connection-lost');
          this.checkGates();
          this.spawnServer();
          await this.handshake();
          await this.readRateLimits();
          await this.resumeThread(this.state);
          firstText = 'continue';
        }
      }
    } finally {
      if (this.state) { try { this.persist(); } catch { /* best effort */ } }
      this.server.closeStdin();
    }
  }
}

// --- signals -----------------------------------------------------------

function installSignalHandlers(supervisor) {
  const handler = () => { supervisor.stopRequested = true; };
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, handler);
  return () => { for (const signal of ['SIGTERM', 'SIGINT']) process.off(signal, handler); };
}

// --- status ------------------------------------------------------------

function stamp(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return '-';
  return new Date(value * 1000).toISOString();
}

export function statusReport(state) {
  // Explicit allowlist: never print model text, paths, IDs, errors, or rate-limit metadata.
  const complete = state.exitReason !== undefined;
  const allowed = new Set(['starting', 'turn', 'turn-boundary', 'initialize', 'thread/start', 'thread/resume', 'turn/start', 'account/rateLimits/read', 'quota-wait', 'transient-wait', 'stopped']);
  const rows = [
    ['state', complete ? 'complete' : state.lifecycle === 'running' ? 'running' : 'checkpointed'],
    ['operation', complete ? 'complete' : allowed.has(state.operation) ? state.operation : 'stopped'],
    ['thread', typeof state.threadId === 'string' ? 'recorded' : 'unknown'],
    ['unresolved turn', needsTurnReconciliation(state) ? 'reconciliation required' : 'none'],
  ];
  for (const key of ['turnsStarted', 'resumes', 'quotaWaits', 'transientRetries', 'turnFailures']) {
    rows.push([key, Number.isSafeInteger(state[key]) ? state[key] : 'unknown']);
  }
  rows.push(['turns', Array.isArray(state.turns) ? state.turns.length : 0]);
  if (complete) {
    // Only fixed, benign completion vocabulary is public. Arbitrary agent
    // explanations can contain credentials, so they remain in private state.
    const summaries = new Set(['done', 'complete', 'completed', 'all good', 'success', 'successful']);
    const summary = typeof state.exitReason === 'string' ? state.exitReason.trim().toLowerCase() : '';
    rows.push(['exit reason', summaries.has(summary) ? summary : 'terminal marker recorded']);
  }
  else {
    const reasons = new Set(['stop-requested', 'ceiling-reached', 'connection-or-protocol-failure', 'context-exhausted', 'budget-exhausted', 'thread-start-unconfirmed', 'connection-lost-at-turn-boundary']);
    rows.push(['checkpoint reason', reasons.has(state.recoveryReason) ? state.recoveryReason : 'owner-ended-or-unconfirmed']);
    rows.push(['recovery', needsTurnReconciliation(state)
      ? 'review prior effects, then use reconcile --state <file> --evidence-file <file>; reconcile any stale ownership lock first'
      : 'resume using the same run arguments; reconcile any stale ownership lock first']);
  }
  return rows.map(([key, value]) => `${key}  ${value}`).join('\n');
}

function runStatus(options) {
  if (!existsSync(options.state)) {
    process.stdout.write('no run\n');
    return EXIT_FAIL;
  }
  let state;
  try { state = JSON.parse(readRegular(options.state)); }
  catch { process.stdout.write('no run\n'); return EXIT_FAIL; }
  if (!isRecord(state)) { process.stdout.write('no run\n'); return EXIT_FAIL; }
  if (state.lifecycle === 'running' && !ownershipFresh(options.state)) state.lifecycle = 'checkpointed';
  process.stdout.write(`${statusReport(state)}\n`);
  return EXIT_OK;
}

// --- entry point -------------------------------------------------------

export async function main(argv) {
  let options;
  try { options = parseArgs(argv); }
  catch (error) {
    process.stderr.write(`${error.message}\n`);
    return error.code ?? EXIT_USAGE;
  }
  if (options.command === 'status') {
    try { return runStatus(options); }
    catch (error) {
      process.stderr.write(`${error.message}\n`);
      return error.code ?? EXIT_FAIL;
    }
  }
  let supervisor;
  let removeSignals;
  try {
    if (options.command === 'reconcile') return reconcileTurn(options);
    if (options.command === 'stop') {
      requestStop(canonicalPath(options.state));
      process.stdout.write('stop requested\n');
      return EXIT_OK;
    }
    supervisor = new Supervisor(options);
    supervisor.owner = acquire(supervisor.statePath);
    removeSignals = installSignalHandlers(supervisor);
    return await supervisor.run();
  } catch (error) {
    const code = error.code ?? EXIT_FAIL;
    process.stderr.write(`${error.message}\n`);
    if (supervisor?.state) supervisor.state.recoveryReason ||= supervisor.stopRequested ? 'stop-requested' : code === EXIT_CEILING ? 'ceiling-reached' : 'connection-or-protocol-failure';
    try { if (supervisor?.owner) supervisor.log(`exit ${code}: ${error.message}`); } catch { /* best effort */ }
    return code;
  } finally {
    if (supervisor?.owner) {
      supervisor.finishing = true;
      if (supervisor.state) { try { supervisor.persist(); } catch {} }
      try {
        await closeServer(supervisor.server);
        supervisor.owner.release();
      } catch (error) {
        supervisor.owner.retain();
        removeSignals?.();
        process.stderr.write(`${error.message}\n`);
        return EXIT_FAIL;
      }
    }
    removeSignals?.();
  }
}

function invokedDirectly() {
  const entry = process.argv[1];
  if (!entry) return false;
  const self = fileURLToPath(import.meta.url);
  if (entry === self) return true;
  try { return realpathSync(entry) === realpathSync(self); } catch { return false; }
}

if (invokedDirectly()) {
  main(process.argv.slice(2)).then((code) => { process.exit(code); }, (error) => {
    process.stderr.write(`${error && error.stack ? error.stack : String(error)}\n`);
    process.exit(EXIT_FAIL);
  });
}
