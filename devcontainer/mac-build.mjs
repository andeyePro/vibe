#!/usr/bin/env node
/** Client: immutable source snapshots sent only to a fixed SSH forced command. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { readBoundedFile, withCheckedPath, LIMITS, ProtocolError, assertSnapshotPathSet, comparePaths, digestFiles, parseRequest, safeRelativePath } from './mac-build-protocol.mjs';

const deny = new Set(['.git', '.vibe', '.vss', '.build', 'node_modules']);
const SSH_TIMEOUT_MS = 630_000;
const fail = message => { throw new ProtocolError(message); };
const within = (root, target) => target === root || target.startsWith(root + path.sep);
async function readBounded(file, maximum, label) {
  return (await readBoundedFile(file, maximum, label)).bytes;
}
async function ordinaryContained(root, relative, label) {
  if (!safeRelativePath(relative)) fail(`unsafe ${label} path: ${relative}`);
  const target = path.resolve(root, relative);
  if (!within(root, target)) fail(`unsafe ${label} path: ${relative}`);
  return withCheckedPath(target, false, async (_handle, stat) => ({
    target, stat, resolved: target,
  }));
}
function git(root, args) {
  return new Promise((resolve, reject) => {
    const child = spawn('git', args, { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
    const chunks = [];
    child.stdout.on('data', item => chunks.push(item));
    child.stderr.resume();
    child.on('error', reject);
    child.on('close', code => resolve({ code, stdout: Buffer.concat(chunks) }));
  });
}
async function loadConfig(suppliedRoot) {
  const root = await fs.realpath(path.resolve(suppliedRoot));
  const repo = await git(root, ['rev-parse', '--is-inside-work-tree']);
  if (repo.code !== 0 || repo.stdout.toString().trim() !== 'true') {
    fail('mac-build requires a working git repository');
  }
  const info = await ordinaryContained(root, '.vibe/mac-build.json', 'config');
  const listed = await git(root, ['ls-files', '-z', '--cached']);
  if (listed.code !== 0) fail('unable to list tracked files');
  const tracked = new Set(listed.stdout.toString().split('\0').filter(Boolean).map(item => item.toLowerCase()));
  if (tracked.has('.vibe/mac-build.json')) fail('.vibe/mac-build.json must be untracked');
  let config;
  try {
    config = JSON.parse((await readBounded(info.target, 65536, 'config')).toString());
  } catch {
    fail('invalid mac-build config JSON');
  }
  const keys = new Set(['account', 'identityFile', 'knownHosts', 'includeRoots']);
  if (!config || typeof config !== 'object' || Array.isArray(config) ||
      Object.keys(config).some(key => !keys.has(key)) || config.account !== 'claude' ||
      !Array.isArray(config.includeRoots) || !config.includeRoots.length) {
    fail('config requires account "claude" and includeRoots');
  }
  for (const item of config.includeRoots) {
    if (!safeRelativePath(item) || item.split('/').some(part => deny.has(part))) {
      fail('invalid include root');
    }
  }
  const vibeRoot = path.join(root, '.vibe');
  for (const key of ['identityFile', 'knownHosts']) {
    if (typeof config[key] !== 'string' || !config[key].startsWith('.vibe/')) {
      fail(`${key} must be under .vibe`);
    }
    const file = await ordinaryContained(root, config[key], key);
    if (/[\x00-\x1f\x7f%$]/.test(file.resolved)) fail(`${key} path contains unsupported SSH expansion characters`);
    if (!within(vibeRoot, file.resolved)) fail(`${key} escapes .vibe`);
    if (tracked.has(config[key].toLowerCase())) fail(`${key} must be untracked`);
    if (key === 'identityFile' && (file.stat.mode & 0o077)) {
      fail('identityFile must have owner-only permissions');
    }
    config[key] = file.resolved;
  }
  return { config, root };
}
async function snapshot(root, roots) {
  const found = new Map();
  const explicit = new Set(roots);
  let total = 0;
  async function visit(relative) {
    if (!safeRelativePath(relative) || relative.split('/').some(part => deny.has(part))) return;
    const target = path.resolve(root, relative);
    if (!within(root, target)) fail(`unsafe source path: ${relative}`);
    // This decides traversal only. All data access independently opens and
    // validates no-follow descriptors, including every ancestor component.
    const stat = await fs.lstat(target);
    if (stat.isDirectory()) {
      const entries = await withCheckedPath(target, true, () => fs.readdir(target));
      for (const entry of entries) {
        const child = `${relative}/${entry}`;
        if (entry.startsWith('.') && !explicit.has(child) &&
            ![...explicit].some(item => item.startsWith(child + '/'))) continue;
        await visit(child);
      }
      return;
    }
    if (!stat.isFile()) fail(`snapshot rejects non-ordinary entry: ${relative}`);
    if (found.has(relative)) fail(`duplicate source file: ${relative}`);
    if (found.size >= LIMITS.maxFiles) fail('too many source files');
    const { bytes, stat: openedStat } = await readBoundedFile(
      target, Math.min(LIMITS.maxFileBytes, LIMITS.maxDecodedBytes - total),
      `source file ${relative}`,
    );
    total += bytes.length;
    found.set(relative, {
      path: relative, mode: (openedStat.mode & 0o111) ? 493 : 420,
      content: bytes.toString('base64'),
    });
  }
  for (const item of roots) await visit(item);
  assertSnapshotPathSet([...found.keys()]);
  return [...found.values()].sort((a, b) => comparePaths(a.path, b.path));
}
export async function makeRequest({ root = process.cwd(), operation }) {
  if (!['doctor', 'build', 'test', 'screenshot'].includes(operation)) fail('invalid operation');
  const loaded = await loadConfig(root);
  const files = await snapshot(loaded.root, loaded.config.includeRoots);
  return {
    config: loaded.config,
    request: { version: 1, jobId: crypto.randomUUID(), operation, files, digest: digestFiles(files) },
  };
}
export function sshTransport({ config, request, spawnImpl = spawn, timeoutMs = SSH_TIMEOUT_MS, signal } = {}) {
  return new Promise((resolve, reject) => {
    // -o values have their own OpenSSH parser even though no shell is used.
    const knownHosts = '"' + config.knownHosts.replaceAll('\\', '\\\\').replaceAll('"', '\\"') + '"';
    const args = [
      '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
      '-o', 'IdentityAgent=none', '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'UpdateHostKeys=no',
      '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
      '-o', 'PermitLocalCommand=no', '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
      '-o', 'RequestTTY=no', '-o', 'StrictHostKeyChecking=yes',
      '-o', `UserKnownHostsFile=${knownHosts}`, '-i', config.identityFile,
      `${config.account}@host.docker.internal`, 'mac-build-host',
    ];
    let child;
    let output = '';
    let error = '';
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancelled);
      fn(value);
    };
    const cancelled = () => {
      if (child) child.kill('SIGKILL');
      finish(reject, new Error('ssh operation cancelled'));
    };
    const timer = setTimeout(() => {
      if (child) child.kill('SIGKILL');
      finish(reject, new Error('ssh whole-operation timeout'));
    }, timeoutMs);
    if (signal?.aborted) { cancelled(); return; }
    signal?.addEventListener('abort', cancelled, { once: true });
    try {
      child = spawnImpl('ssh', args, { stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (err) {
      finish(reject, err);
      return;
    }
    child.stdout.on('data', data => {
      output += data;
      if (Buffer.byteLength(output) > LIMITS.maxWireBytes) {
        child.kill('SIGKILL');
        finish(reject, new Error('host response exceeds wire limit'));
      }
    });
    child.stderr.on('data', data => {
      if (Buffer.byteLength(error) < 8192) {
        error += data.toString().slice(0, 8192 - Buffer.byteLength(error));
      }
    });
    child.stdin.on('error', err => finish(reject, new Error(`ssh stdin failed: ${err.message}`)));
    child.on('error', err => finish(reject, err));
    child.on('close', code => {
      if (settled) return;
      if (code !== 0) return finish(reject, new Error(`ssh failed (${code}): ${error}`));
      try {
        const result = JSON.parse(output);
        const snapshotBytes = request.files.reduce(
          (total, file) => total + Buffer.byteLength(file.content, 'base64'), 0,
        );
        if (!result || result.version !== 1 || result.jobId !== request.jobId ||
            result.operation !== request.operation || result.fingerprint !== request.digest ||
            result.snapshotBytes !== snapshotBytes || typeof result.outcome !== 'string') {
          throw new Error('host response identity or outcome is invalid');
        }
        finish(resolve, result);
      } catch (err) {
        finish(reject, err.message === 'host response identity or outcome is invalid'
          ? err : new Error('host returned invalid JSON'));
      }
    });
    try {
      child.stdin.end(JSON.stringify(request));
    } catch (err) {
      finish(reject, err);
    }
  });
}
function requestBinding(config) {
  return crypto.createHash('sha256').update(JSON.stringify([config.account, config.identityFile, config.knownHosts])).digest('hex');
}
async function requestDirectory(root) {
  const dir = path.join(await fs.realpath(root), '.vibe', 'mac-build-requests');
  await fs.mkdir(dir, { mode: 0o700 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
  await withCheckedPath(dir, true, async (_handle, stat) => {
    if (stat.uid !== process.getuid() || (stat.mode & 0o777) !== 0o700) fail('request directory must be owned and private');
  });
  return dir;
}
async function saveRequest(root, config, request) {
  const dir = await requestDirectory(root);
  const file = path.join(dir, `${request.jobId}.json`);
  const handle = await fs.open(file, 'wx', 0o600);
  try { await handle.writeFile(JSON.stringify({ binding: requestBinding(config), request })); await handle.sync(); }
  finally { await handle.close(); }
  await withCheckedPath(dir, true, handle => handle.sync());
  return file;
}
async function deliver(config, request, file, options) {
  try {
    const result = await options.transport({ config, request, timeoutMs: options.timeoutMs, signal: options.signal });
    const temporary = `${file}.${crypto.randomUUID()}.tmp`;
    const handle = await fs.open(temporary, 'wx', 0o600);
    try { await handle.writeFile(JSON.stringify(result)); await handle.sync(); }
    finally { await handle.close(); }
    await fs.rename(temporary, `${file}.result.json`);
    await withCheckedPath(path.dirname(file), true, handle => handle.sync());
    if (result.outcome !== 'success') throw new Error(`host operation failed: ${result.outcome}${result.error ? `: ${result.error}` : ''}`);
    return result;
  } catch (error) {
    throw new Error(`${error.message}; retained request ${request.jobId} at ${file}, received evidence at ${file}.result.json when available. Do not retry under a new job ID; reconcile and explicitly replay the retained request.`);
  }
}
export async function run({ root = process.cwd(), operation, transport = sshTransport, timeoutMs, signal } = {}) {
  const { config, request } = await makeRequest({ root, operation });
  const file = await saveRequest(root, config, request);
  return deliver(config, request, file, { transport, timeoutMs, signal });
}
export async function replay({ root = process.cwd(), jobId, transport = sshTransport, timeoutMs, signal } = {}) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(jobId)) fail('invalid retained job ID');
  const { config } = await loadConfig(root);
  const file = path.join(await requestDirectory(root), `${jobId}.json`);
  const { bytes, stat } = await readBoundedFile(file, LIMITS.maxWireBytes + 1024, 'retained request');
  if (stat.uid !== process.getuid() || (stat.mode & 0o777) !== 0o600) fail('retained request must be owned and private');
  const saved = JSON.parse(bytes.toString('utf8'));
  const request = parseRequest(JSON.stringify(saved.request));
  if (saved.binding !== requestBinding(config) || request.jobId !== jobId) fail('retained request binding changed');
  return deliver(config, request, file, { transport, timeoutMs, signal });
}
async function main() {
  const operation = process.argv[2];
  const controller = new AbortController();
  const interrupt = () => { process.exitCode = 130; controller.abort(); };
  const terminate = () => { process.exitCode = 143; controller.abort(); };
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  try {
    if (operation === 'replay' && process.argv.length === 4) {
      console.log(JSON.stringify(await replay({ jobId: process.argv[3], signal: controller.signal })));
      return;
    }
    if (!['doctor', 'build', 'test', 'screenshot'].includes(operation) || process.argv.length !== 3) {
      throw new Error('usage: mac-build.mjs doctor|build|test|screenshot | replay UUID');
    }
    console.log(JSON.stringify(await run({ operation, signal: controller.signal })));
  } finally {
    process.off('SIGINT', interrupt);
    process.off('SIGTERM', terminate);
  }
}
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => { console.error(error.message); process.exitCode ||= 1; });
}
