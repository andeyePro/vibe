#!/usr/bin/env node
// codex-remote — talks to the vibe-owned Codex app-server that codex-entry
// starts for `vibe --agent codex` when remote control is switched on
// (VIBE_CODEX_REMOTE=1 on the Mac). Installed root-owned as
// /usr/local/bin/codex-remote.
//
// WHY vibe RUNS ITS OWN APP-SERVER (2026-10-06)
// ---------------------------------------------
// Codex's phone remote control needs the TUI to sit on a shared app-server,
// and Codex's own way to get one — the managed daemon (`codex remote-control
// start`, `codex app-server daemon start`) — is unusable inside vibe:
//   - it DROPS `-c`: the daemon process runs `app-server --managed-daemon`
//     with no overrides, so `-c agents.enabled=false` is lost and a user or
//     project config can hand the model `spawn_agent` again (verified through
//     `config/read` on 0.160.1);
//   - it installs and auto-updates its own copy of Codex under
//     $CODEX_HOME/packages, outside the image's codex-compat-check gate;
//   - it keeps its pid, lock and socket files under $CODEX_HOME, which in vibe
//     is the Mac's shared ~/.codex, where the Mac app's own daemon lives.
// A plain `codex app-server --remote-control -c agents.enabled=false --listen
// unix://<container-local path>` has none of those problems: it is the
// image's checked binary, it keeps the override, and its socket is in the
// container's own /tmp. codex-entry starts it and points the TUI at it with
// `codex --remote unix://<path>`.
//
// SUBCOMMANDS
//   status            remote-control status of the running server
//   pair              print a pairing code for the ChatGPT app, wait for the
//                     phone to claim it
//   clients           list paired phones (id, name, last seen)
//   revoke <clientId> unpair one phone
//   wait              exit 0 once the server answers initialize (codex-entry
//                     uses this before starting the TUI)
// Options: --socket <path> (default $VIBE_CODEX_REMOTE_SOCKET, which
// codex-entry sets for the session it starts), --timeout <seconds>.
//
// Pairing codes go to this process's stdout and nowhere else: nothing here
// writes a file or a log. Run `pair` from the terminal codex-entry prints it
// in, not through the agent's shell tool — a code shown there would also be
// saved in the Codex session transcript.
import { connect } from 'node:net';
import { randomBytes } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const EXIT_OK = 0;
const EXIT_FAIL = 1;
const EXIT_USAGE = 2;

// codex-entry exports the socket it started into the Codex session's
// environment; there is no fixed default, because each launch gets a fresh
// random directory (a fixed path could be pre-staged by an earlier session).
export function defaultSocket(env = process.env) {
  return env.VIBE_CODEX_REMOTE_SOCKET || '';
}

export function encodeControl(opcode, payload = Buffer.alloc(0)) {
  const mask = randomBytes(4);
  const masked = Buffer.from(payload.map((x, i) => x ^ mask[i % 4]));
  return Buffer.concat([Buffer.from([0x80 | opcode, 0x80 | masked.length]), mask, masked]);
}

// ── minimal WebSocket client over a unix socket ─────────────────────────────
// The app-server's unix:// listener speaks WebSocket (an HTTP/1.1 upgrade,
// then RFC 6455 frames carrying one JSON-RPC message each). Text frames only;
// client frames are masked as the RFC requires.

export function encodeFrame(text) {
  const payload = Buffer.from(text, 'utf8');
  const mask = randomBytes(4);
  let header;
  if (payload.length < 126) {
    header = Buffer.from([0x81, 0x80 | payload.length]);
  } else if (payload.length < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81; header[1] = 0x80 | 126; header.writeUInt16BE(payload.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81; header[1] = 0x80 | 127; header.writeBigUInt64BE(BigInt(payload.length), 2);
  }
  const masked = Buffer.alloc(payload.length);
  for (let i = 0; i < payload.length; i++) masked[i] = payload[i] ^ mask[i % 4];
  return Buffer.concat([header, mask, masked]);
}

// Returns { frames: [{opcode, payload}], rest } — rest is the unconsumed tail.
export function decodeFrames(buf) {
  const frames = [];
  let off = 0;
  for (;;) {
    if (buf.length - off < 2) break;
    const b1 = buf[off]; const b2 = buf[off + 1];
    let len = b2 & 0x7f; let hdr = 2;
    if (len === 126) {
      if (buf.length - off < 4) break;
      len = buf.readUInt16BE(off + 2); hdr = 4;
    } else if (len === 127) {
      if (buf.length - off < 10) break;
      len = Number(buf.readBigUInt64BE(off + 2)); hdr = 10;
    }
    const masked = (b2 & 0x80) !== 0;
    const maskLen = masked ? 4 : 0;
    if (buf.length - off < hdr + maskLen + len) break;
    let payload = buf.subarray(off + hdr + maskLen, off + hdr + maskLen + len);
    if (masked) {
      const m = buf.subarray(off + hdr, off + hdr + 4);
      payload = Buffer.from(payload.map((x, i) => x ^ m[i % 4]));
    }
    frames.push({ fin: (b1 & 0x80) !== 0, opcode: b1 & 0x0f, payload });
    off += hdr + maskLen + len;
  }
  return { frames, rest: buf.subarray(off) };
}

class Client {
  constructor(socketPath) {
    this.socketPath = socketPath;
    this.nextId = 1;
    this.pending = new Map();
    this.buf = Buffer.alloc(0);
    this.partial = [];
    this.upgraded = false;
    this.closed = false;
  }

  open(timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.close(); reject(new Error(`no answer from ${this.socketPath}`)); }, timeoutMs);
      this.sock = connect({ path: this.socketPath });
      this.sock.on('error', (err) => { this.closed = true; clearTimeout(timer); reject(err); this.failAll(err); });
      this.sock.on('close', () => {
        this.closed = true;
        clearTimeout(timer);
        reject(new Error('the app-server closed the connection'));
        this.failAll(new Error('the app-server closed the connection'));
      });
      this.sock.on('connect', () => {
        const key = randomBytes(16).toString('base64');
        this.sock.write(`GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n`
          + `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`);
      });
      this.sock.on('data', (chunk) => {
        this.buf = Buffer.concat([this.buf, chunk]);
        if (!this.upgraded) {
          const end = this.buf.indexOf('\r\n\r\n');
          if (end < 0) return;
          const status = this.buf.subarray(0, this.buf.indexOf('\r\n')).toString();
          this.buf = this.buf.subarray(end + 4);
          if (!/^HTTP\/1\.1 101/.test(status)) {
            clearTimeout(timer); this.close(); reject(new Error(`websocket upgrade refused: ${status}`)); return;
          }
          this.upgraded = true;
          clearTimeout(timer);
          resolve();
        }
        this.drain();
      });
    });
  }

  drain() {
    const { frames, rest } = decodeFrames(this.buf);
    this.buf = rest;
    for (const f of frames) {
      if (f.opcode === 0x8) { this.close(); return; }
      if (f.opcode === 0x9) { this.sock.write(encodeControl(0xa, f.payload)); continue; } // pong: `pair` may hold the connection for minutes
      if (f.opcode === 0xa) continue;
      if (f.opcode === 0x1 || f.opcode === 0x0) {
        this.partial.push(f.payload);
        if (!f.fin) continue;
        const text = Buffer.concat(this.partial).toString('utf8');
        this.partial = [];
        let msg;
        try { msg = JSON.parse(text); } catch { continue; }
        if (msg && msg.id !== undefined && this.pending.has(msg.id)) {
          const { resolve, reject } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
          else resolve(msg.result);
        }
      }
    }
  }

  send(obj) { this.sock.write(encodeFrame(JSON.stringify(obj))); }

  request(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      // A write to a closed socket raises nothing, so without this a request
      // after the server went away would never settle.
      if (this.closed || this.sock.destroyed) { reject(new Error('the app-server closed the connection')); return; }
      this.pending.set(id, { resolve, reject });
      this.send({ id, method, params });
    });
  }

  failAll(err) {
    for (const { reject } of this.pending.values()) reject(err);
    this.pending.clear();
  }

  close() { this.closed = true; try { this.sock.destroy(); } catch { /* already gone */ } }
}

async function session(socketPath, timeoutMs) {
  const c = new Client(socketPath);
  await c.open(timeoutMs);
  await c.request('initialize', {
    clientInfo: { name: 'vibe-codex-remote', version: '1' },
    capabilities: { experimentalApi: true },
  });
  c.send({ method: 'initialized' });
  return c;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function describeStatus(s) {
  const where = s.serverName ? ` as "${s.serverName}"` : '';
  switch (s.status) {
    case 'connected': return `connected${where}: the ChatGPT app can reach this session`;
    case 'connecting': return `connecting${where}`;
    case 'disabled': return 'disabled on this app-server';
    case 'errored': return `errored${where}: check that this container's Codex login works (run \`codex login status\`)`;
    default: return String(s.status);
  }
}

async function waitConnected(c, deadline) {
  for (;;) {
    const s = await c.request('remoteControl/status/read');
    if (s.status === 'connected' && s.environmentId) return s;
    if (Date.now() >= deadline) return s;
    await sleep(1000);
  }
}

export async function main(argv, out = process.stdout, err = process.stderr) {
  let socketPath = defaultSocket();
  let timeoutSec = null;
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--socket') { socketPath = argv[++i]; if (!socketPath) { err.write('codex-remote: --socket needs a path\n'); return EXIT_USAGE; } }
    else if (a === '--timeout') {
      timeoutSec = Number(argv[++i]);
      if (!Number.isFinite(timeoutSec) || timeoutSec <= 0) { err.write('codex-remote: --timeout needs a positive number of seconds\n'); return EXIT_USAGE; }
    } else if (a === '-h' || a === '--help') {
      out.write('usage: codex-remote [--socket <path>] [--timeout <s>] status|pair|clients|revoke <clientId>|wait\n');
      return EXIT_OK;
    } else rest.push(a);
  }
  const [cmd, ...args] = rest;
  const known = ['status', 'pair', 'clients', 'revoke', 'wait'];
  if (!known.includes(cmd)) {
    err.write(`codex-remote: expected one of ${known.join(', ')}\n`);
    return EXIT_USAGE;
  }
  if (cmd === 'revoke' && args.length !== 1) { err.write('codex-remote: revoke needs exactly one client id (see `codex-remote clients`)\n'); return EXIT_USAGE; }
  if (cmd !== 'revoke' && args.length) { err.write(`codex-remote: ${cmd} takes no arguments\n`); return EXIT_USAGE; }
  if (!socketPath) {
    err.write('codex-remote: no app-server socket: run this inside a Codex session launched with VIBE_CODEX_REMOTE=1, or pass --socket\n');
    return EXIT_FAIL;
  }

  if (cmd === 'wait') {
    const deadline = Date.now() + (timeoutSec ?? 20) * 1000;
    let last;
    while (Date.now() < deadline) {
      try { const c = await session(socketPath, 2000); c.close(); return EXIT_OK; } catch (e) { last = e; }
      await sleep(250);
    }
    err.write(`codex-remote: the vibe Codex app-server did not answer at ${socketPath}: ${last ? last.message : 'timed out'}\n`);
    return EXIT_FAIL;
  }

  let c;
  try {
    c = await session(socketPath, 5000);
  } catch (e) {
    err.write(`codex-remote: cannot reach the vibe Codex app-server at ${socketPath} (${e.message}). `
      + 'Remote control runs only in a Codex session launched with VIBE_CODEX_REMOTE=1.\n');
    return EXIT_FAIL;
  }
  try {
    if (cmd === 'status') {
      // Right after start-up the server is usually still `connecting` to the
      // relay, so --timeout waits for it rather than reporting the first read.
      const s = timeoutSec === null ? await c.request('remoteControl/status/read')
        : await waitConnected(c, Date.now() + timeoutSec * 1000);
      out.write(`remote control: ${describeStatus(s)}\n`);
      return s.status === 'connected' ? EXIT_OK : EXIT_FAIL;
    }
    const s = await waitConnected(c, Date.now() + (timeoutSec ?? 30) * 1000);
    if (s.status !== 'connected' || !s.environmentId) {
      err.write(`codex-remote: remote control is not connected (${describeStatus(s)})\n`);
      return EXIT_FAIL;
    }
    if (cmd === 'clients') {
      const r = await c.request('remoteControl/client/list', { environmentId: s.environmentId, order: 'desc' });
      const data = Array.isArray(r && r.data) ? r.data : [];
      if (!data.length) { out.write('no paired phones\n'); return EXIT_OK; }
      for (const cl of data) {
        const name = cl.displayName || cl.deviceModel || cl.platform || '';
        const seenMs = Number(cl.lastSeenAt) > 1e12 ? Number(cl.lastSeenAt) : Number(cl.lastSeenAt) * 1000;
        const seen = cl.lastSeenAt && Number.isFinite(seenMs) ? `last seen ${new Date(seenMs).toISOString()}` : '';
        out.write(`${cl.clientId}\t${name}\t${seen}\n`);
      }
      return EXIT_OK;
    }
    if (cmd === 'revoke') {
      await c.request('remoteControl/client/revoke', { environmentId: s.environmentId, clientId: args[0] });
      out.write(`unpaired ${args[0]}\n`);
      return EXIT_OK;
    }
    // pair
    const p = await c.request('remoteControl/pairing/start', { manualCode: true });
    const code = p.manualPairingCode || p.pairingCode;
    const expires = Number(p.expiresAt);
    const expiresMs = expires > 1e12 ? expires : expires * 1000;
    out.write(`\n  Pair the ChatGPT app with this Codex session ("${s.serverName}"):\n`
      + `  open Codex in the ChatGPT app, choose to connect a computer, and enter\n\n      ${code}\n\n`
      + (Number.isFinite(expiresMs) ? `  The code expires in about ${Math.max(1, Math.round((expiresMs - Date.now()) / 60000))} minutes.\n` : '')
      + '  Waiting for the phone (Ctrl-C to stop waiting; the code stays valid until it expires)...\n');
    const deadline = Number.isFinite(expiresMs) ? Math.min(expiresMs, Date.now() + 15 * 60 * 1000) : Date.now() + 10 * 60 * 1000;
    const statusParams = p.manualPairingCode ? { manualPairingCode: p.manualPairingCode } : { pairingCode: p.pairingCode };
    while (Date.now() < deadline) {
      const st = await c.request('remoteControl/pairing/status', statusParams);
      if (st && st.claimed) { out.write('  Paired.\n\n'); return EXIT_OK; }
      await sleep(2000);
    }
    err.write('codex-remote: the pairing code expired before a phone claimed it; run `codex-remote pair` again\n');
    return EXIT_FAIL;
  } catch (e) {
    err.write(`codex-remote: ${cmd} failed: ${e.message}\n`);
    return EXIT_FAIL;
  } finally {
    c.close();
  }
}

let isMain = false;
try { isMain = process.argv[1] !== undefined && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url); } catch { isMain = false; }
if (isMain) {
  main(process.argv.slice(2)).then((code) => process.exit(code), (e) => {
    process.stderr.write(`codex-remote: ${e.message}\n`);
    process.exit(EXIT_FAIL);
  });
}
