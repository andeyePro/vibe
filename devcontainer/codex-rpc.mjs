// Codex stdio transport; extracted without changing protocol behavior.
import { failError, isRecord } from './codex-errors.mjs';
const REQUEST_TIMEOUT_MS = 30000;

export class AppServer {
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
      const replyError = failError(`${entry.label} failed: ${detail}`);
      // An explicit error REPLY proves the server did not act on the request,
      // unlike a timeout or a closed connection.
      replyError.replied = true;
      entry.reject(replyError);
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

