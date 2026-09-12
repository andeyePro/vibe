#!/usr/bin/env node
/**
 * Installed by an administrator outside the checkout as sshd's ForceCommand.
 * It accepts only protocol v1 snapshots; it never accepts a command or cwd.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readBoundedFile, withCheckedPath, safeRelativePath, LIMITS, ProtocolError, digestFiles, parseRequest, response } from './mac-build-protocol.mjs';

const hostAbort = new AbortController();
const MAX_LOG = 4 * 1024 * 1024;
const allowed = new Set(['doctor', 'build', 'test', 'screenshot']);
const plainObject = x => x && typeof x === 'object' && !Array.isArray(x);
function bad(message) { throw new ProtocolError(message); }
async function secureFile(file, label, uid) {
  const stat = await fs.lstat(file);
  if (!stat.isFile() || stat.isSymbolicLink()) bad(`${label} must be a regular file`);
  if ((stat.mode & 0o022) !== 0 || (uid !== undefined && stat.uid !== uid)) bad(`${label} has unsafe ownership or permissions`);
}
async function secureAncestors(file, label, uid = 0) {
  let cursor = path.resolve(file);
  while (true) {
    cursor = path.dirname(cursor);
    const stat = await fs.lstat(cursor);
    if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== uid || (stat.mode & 0o022) !== 0) bad(`${label} has an unsafe parent directory`);
    if (cursor === path.dirname(cursor)) return;
  }
}
async function secureTrustedFile(file, label) { await secureAncestors(file, label); await secureFile(file, label, 0); }
async function loadHostConfig(file = process.env.MAC_BUILD_HOST_CONFIG || '/etc/mac-build-host.json', { trustCheck = true } = {}) {
  if (trustCheck) await secureFile(file, 'host config', 0);
  let cfg;
  try {
    cfg = JSON.parse((await readBoundedFile(file, 65536, 'host config')).bytes.toString('utf8'));
  } catch {
    bad('host config is unreadable JSON');
  }
  return validateConfig(cfg);
}
async function validateConfig(input) {
  const cfg = { ...input };
  if (!plainObject(cfg) || typeof cfg.root !== 'string' || typeof cfg.receiptsRoot !== 'string' || !plainObject(cfg.commands)) bad('invalid host config');
  for (const [operation, argv] of Object.entries(cfg.commands)) {
    if (!allowed.has(operation) || !Array.isArray(argv) || !argv.length ||
        argv.some(arg => typeof arg !== 'string' || !arg.length || arg.includes('\0')) ||
        !path.isAbsolute(argv[0]) || path.normalize(argv[0]) !== argv[0]) {
      bad('invalid approved command');
    }
  }
  if (!cfg.commands.doctor || !cfg.commands.build || !cfg.commands.test) {
    bad('doctor/build/test commands required');
  }
  cfg.timeoutMs = Number.isInteger(cfg.timeoutMs)
    ? Math.min(Math.max(cfg.timeoutMs, 1_000), 600_000) : 600_000;
  cfg.lockName = cfg.lockName === undefined ? '.mac-build.lock' : cfg.lockName;
  if (typeof cfg.lockName !== 'string' || !/^[A-Za-z0-9._-]+$/.test(cfg.lockName) ||
      ['.', '..'].includes(cfg.lockName)) bad('invalid configured lock name');
  cfg.artifacts = cfg.artifacts === undefined ? [] : cfg.artifacts;
  if (!Array.isArray(cfg.artifacts)) bad('invalid artifact config');
  for (const artifact of cfg.artifacts) {
    if (!plainObject(artifact) || !safeRelativePath(artifact.path) ||
        !Number.isSafeInteger(artifact.maxBytes) || artifact.maxBytes < 0 ||
        artifact.maxBytes > LIMITS.maxFileBytes) bad('invalid artifact config');
  }
  cfg.commands = Object.fromEntries(Object.entries(cfg.commands).map(([key, argv]) => [key, [...argv]]));
  cfg.artifacts = cfg.artifacts.map(artifact => ({ ...artifact }));
  const roots = [cfg.root, cfg.receiptsRoot];
  for (const root of roots) {
    if (!path.isAbsolute(root) || path.resolve(root) !== root || root === '/') {
      bad('state roots must be absolute normalized directories');
    }
  }
  if (roots[0] === roots[1] || roots[0].startsWith(roots[1] + path.sep) ||
      roots[1].startsWith(roots[0] + path.sep)) bad('state roots must be distinct and non-overlapping');
  for (const root of roots) await validateStateRoot(root);
  return cfg;
}
async function validateStateRoot(root) {
  const uid = process.getuid();
  let cursor = path.dirname(root);
  while (true) {
    await withCheckedPath(cursor, true, async (_handle, stat) => {
      const trustedSticky = stat.uid === 0 && (stat.mode & 0o1777) === 0o1777;
      if (![0, uid].includes(stat.uid) || ((stat.mode & 0o022) && !trustedSticky)) {
        bad('state root has unsafe ancestor ownership or permissions');
      }
    });
    if (cursor === path.dirname(cursor)) break;
    cursor = path.dirname(cursor);
  }
  await fs.mkdir(root, { mode: 0o700 }).catch(error => {
    if (error.code !== 'EEXIST') throw error;
  });
  await withCheckedPath(root, true, async (_handle, stat) => {
    if (await fs.realpath(root) !== root) bad('state root must use its canonical path');
    if (stat.uid !== uid || (stat.mode & 0o777) !== 0o700) {
      bad('state root must be owned by the service account with mode 0700');
    }
  });
}
async function validateInstallation(configFile) {
  await secureTrustedFile(process.execPath, 'Node interpreter');
  await secureTrustedFile(fileURLToPath(import.meta.url), 'forced-command entrypoint');
  await secureTrustedFile(fileURLToPath(new URL('./mac-build-protocol.mjs', import.meta.url)), 'imported protocol');
  await secureTrustedFile(configFile || process.env.MAC_BUILD_HOST_CONFIG || '/etc/mac-build-host.json', 'host config');
  const wrapper = process.env.MAC_BUILD_FORCED_WRAPPER;
  if (!wrapper || !path.isAbsolute(wrapper)) bad('forced-command wrapper identity is unavailable');
  await secureTrustedFile(wrapper, 'forced-command wrapper');
}
function assertForcedInvocation() {
  // SSH_CONNECTION is supplied by sshd. The marker is set by the root-owned ForceCommand wrapper.
  if (!process.env.SSH_CONNECTION || process.env.MAC_BUILD_FORCED_COMMAND !== '1') bad('mac-build-host only runs as the configured SSH forced command');
}
async function readStdin() {
  let bytes = 0;
  const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > LIMITS.maxWireBytes) bad('request exceeds wire limit');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, bytes).toString('utf8');
}
async function exists(file) {
  try {
    await fs.lstat(file);
    return true;
  } catch (error) {
    if (error.code === 'ENOENT') return false;
    throw error;
  }
}
async function atomicMkdir(file) {
  try {
    await fs.mkdir(file, { mode: 0o700 });
    return true;
  } catch (error) {
    if (error.code === 'EEXIST') return false;
    throw error;
  }
}
async function writeSnapshot(stage, request) {
  for (const item of request.files) {
    const target = path.join(stage, item.path);
    if (!target.startsWith(stage + path.sep)) bad('snapshot path escape');
    await fs.mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
    await fs.writeFile(target, Buffer.from(item.content, 'base64'), { mode: item.mode, flag: 'wx' });
    await fs.chmod(target, item.mode);
  }
}
async function rereadDigest(stage, files) {
  const actual = [];
  for (const item of files) {
    const target = path.resolve(stage, item.path);
    if (!target.startsWith(stage + path.sep)) bad('staged path escape');
    const { bytes, stat } = await readBoundedFile(target, LIMITS.maxFileBytes, 'staged source');
    if ((stat.mode & 0o777) !== item.mode) bad('snapshot changed type or mode');
    actual.push({ path: item.path, mode: item.mode, content: bytes.toString('base64') });
  }
  return digestFiles(actual);
}
export function runApproved(argv, { cwd, env, timeoutMs, spawnImpl = spawn, signal: abortSignal = hostAbort.signal } = {}) {
  if (abortSignal?.aborted) return Promise.resolve({ exit: null, stdout: '', stderr: 'operation cancelled', cancelled: true, timedOut: false, overflow: false });
  return new Promise(resolve => {
    const child = spawnImpl(argv[0], argv.slice(1), {
      cwd, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '', stderr = '', timedOut = false, overflow = false, cancelled = false;
    let drainTimer;
    let cleanupFailed = false;
    let settled = false;
    const killGroup = () => {
      if (!Number.isInteger(child.pid) || child.pid <= 0) return;
      try { process.kill(-child.pid, 'SIGKILL'); } catch (error) {
        if (error.code !== 'ESRCH') {
          cleanupFailed = true;
          stderr += `process-group cleanup: ${error.message}`;
        }
      }
    };
    const finish = (code, signal) => {
      if (settled) return;
      settled = true;
      killGroup();
      clearTimeout(timer);
      clearTimeout(drainTimer);
      abortSignal?.removeEventListener('abort', cancel);
      resolve({ exit: code, signal, stdout, stderr, timedOut, overflow, cleanupFailed, cancelled });
    };
    const stop = () => {
      killGroup();
      // Escaped descendants may retain pipes. Do not wait indefinitely for EOF.
      drainTimer ??= setTimeout(() => {
        child.stdout.destroy();
        child.stderr.destroy();
      }, 1000);
    };
    const append = (which, data) => {
      const text = data.toString();
      if (Buffer.byteLength(stdout) + Buffer.byteLength(stderr) + Buffer.byteLength(text) > MAX_LOG) {
        overflow = true;
        stop();
        return;
      }
      if (which === 'out') stdout += text;
      else stderr += text;
    };
    const cancel = () => { cancelled = true; stop(); };
    abortSignal?.addEventListener('abort', cancel, { once: true });
    child.stdout.on('data', data => append('out', data));
    child.stderr.on('data', data => append('err', data));
    const timer = setTimeout(() => { timedOut = true; stop(); }, timeoutMs);
    // exit fires before close if descendants retain inherited pipes.
    child.on('exit', stop);
    child.on('error', error => { stderr += error.message; finish(null, null); });
    child.on('close', finish);
  });
}
async function collectArtifacts(stage, cfg) {
  const result = [];
  let encodedTotal = 0;
  for (const artifact of cfg.artifacts) {
    const file = path.resolve(stage, artifact.path);
    if (!file.startsWith(stage + path.sep) || !await exists(file)) continue;
    try {
      const { bytes } = await readBoundedFile(file, artifact.maxBytes, 'artifact');
      const content = bytes.toString('base64');
      if (encodedTotal + Buffer.byteLength(content) > LIMITS.maxWireBytes / 2) {
        bad('artifact aggregate exceeds size limit');
      }
      encodedTotal += Buffer.byteLength(content);
      result.push({ path: artifact.path, available: true, bytes: bytes.length, content });
    } catch {
      result.push({ path: artifact.path, available: false, reason: 'unsafe_or_too_large' });
    }
  }
  return result;
}
async function syncDirectory(directory) {
  await withCheckedPath(directory, true, handle => handle.sync());
}
const snapshotBytes = request => request.files.reduce((total, file) => total + Buffer.byteLength(file.content, 'base64'), 0);
function scrubbedEnv(stage) { return { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: stage, TMPDIR: path.join(stage, '.tmp'), LANG: 'C', LC_ALL: 'C' }; }
export async function execute(request, cfg, { runner = runApproved } = {}) {
  // The public import entrypoint receives exactly the same validation as stdin.
  request = parseRequest(JSON.stringify(request));
  cfg = await validateConfig(cfg);
  const bytes = snapshotBytes(request);
  const identity = {
    version: request.version, jobId: request.jobId,
    operation: request.operation, digest: request.digest,
  };
  const envelope = {
    operation: request.operation, jobId: request.jobId,
    fingerprint: request.digest, snapshotBytes: bytes,
  };
  const receipt = path.join(cfg.receiptsRoot, `${request.jobId}.json`);
  const replay = async () => {
    const { bytes: stored, stat } = await readBoundedFile(receipt, LIMITS.maxWireBytes, 'receipt');
    if (stat.uid !== process.getuid() || (stat.mode & 0o777) !== 0o600) bad('unsafe receipt permissions');
    const saved = JSON.parse(stored.toString('utf8'));
    if (!saved.identity || Object.keys(identity).some(key => saved.identity[key] !== identity[key])) {
      return { ...envelope, outcome: 'rejected', error: 'job ID identity mismatch' };
    }
    if (saved.state === 'terminal' && saved.result &&
        Object.keys(envelope).every(key => saved.result[key] === envelope[key])) return saved.result;
    return { ...envelope, outcome: 'unknown', error: 'administrator reconciliation required; do not resubmit under a new UUID' };
  };
  try {
    const handle = await fs.open(receipt, 'wx', 0o600);
    try {
      await handle.writeFile(JSON.stringify({ state: 'unknown-running', identity }));
      await handle.sync();
    } finally { await handle.close(); }
    await syncDirectory(cfg.receiptsRoot);
  } catch (error) {
    if (error.code === 'EEXIST') return replay();
    throw error;
  }
  const terminal = async result => {
    const temporary = `${receipt}.${process.pid}.${crypto.randomUUID()}.tmp`;
    const handle = await fs.open(temporary, 'wx', 0o600);
    try {
      await handle.writeFile(JSON.stringify({ state: 'terminal', identity, result }));
      await handle.sync();
    } finally { await handle.close(); }
    await fs.rename(temporary, receipt);
    await syncDirectory(cfg.receiptsRoot);
    return result;
  };
  const lock = path.join(cfg.receiptsRoot, cfg.lockName);
  let locked = false;
  let stage;
  let completedResult;
  try {
    if (!cfg.commands[request.operation]) {
      return terminal({ ...envelope, outcome: 'rejected', error: 'operation is not configured' });
    }
    locked = await atomicMkdir(lock);
    if (!locked) {
      return terminal({
        ...envelope, outcome: 'busy',
        error: 'build resource is locked; administrator must reconcile an abandoned lock',
      });
    }
    await fs.writeFile(path.join(lock, 'owner.json'), JSON.stringify({ identity, pid: process.pid }), {
      flag: 'wx', mode: 0o600,
    });
    stage = await fs.mkdtemp(path.join(cfg.root, `job-${request.jobId}-`));
    await fs.mkdir(path.join(stage, '.tmp'), { mode: 0o700 });
    await writeSnapshot(stage, request);
    const before = await rereadDigest(stage, request.files);
    if (before !== request.digest) bad('staged source fingerprint mismatch before command');
    const result = await runner(cfg.commands[request.operation], {
      cwd: stage, env: scrubbedEnv(stage), timeoutMs: cfg.timeoutMs,
    });
    const after = await rereadDigest(stage, request.files);
    const outcome = result.exit === 0 && !result.timedOut && !result.overflow &&
      !result.cleanupFailed && !result.cancelled && after === request.digest ? 'success' : 'failure';
    // Configuration evidence, not a claim that the account is sandboxed.
    const toolAvailability = request.operation === 'doctor' ? {
      config: true,
      xcode: { configured: Boolean(cfg.commands.doctor), available: result.exit === 0 },
      simulator: {
        configured: Boolean(cfg.commands.screenshot), available: false,
        evidence: 'not_attested_by_xcode_version',
      },
    } : { config: true };
    completedResult = {
      ...envelope, actualFingerprintBefore: before, actualFingerprintAfter: after,
      toolAvailability, outcome, exit: result.exit, signal: result.signal || null,
      timedOut: result.timedOut, outputTruncated: result.overflow,
      cleanupFailed: Boolean(result.cleanupFailed),
      logs: { stdout: result.stdout, stderr: result.stderr },
      artifacts: await collectArtifacts(stage, cfg),
    };
  } catch (error) {
    completedResult = { ...envelope, outcome: 'failure', error: error.message };
  }
  // Recursive removal is isolated in a bounded owned child. No terminal receipt
  // can claim success while cleanup is unfinished; ambiguous cleanup keeps lock.
  try {
    if (stage) {
      const cleanup = await runApproved([process.execPath, '-e',
        'require("node:fs").rmSync(process.argv[1], {recursive:true,force:true})', stage],
      { cwd: cfg.root, env: scrubbedEnv(cfg.root), timeoutMs: 10000, signal: null });
      if (cleanup.exit !== 0 || cleanup.timedOut || cleanup.overflow || cleanup.cleanupFailed || await exists(stage)) {
        throw new Error('bounded staging cleanup failed');
      }
    }
    if (locked) {
      await fs.unlink(path.join(lock, 'owner.json'));
      await fs.rmdir(lock);
    }
  } catch (error) {
    return { ...envelope, outcome: 'unknown', cleanupFailed: true,
      error: `${error.message}; receipt remains unknown and administrator reconciliation is required` };
  }
  return terminal(completedResult);
}
export async function serve({ configFile, trustCheck = true, runner } = {}) {
  assertForcedInvocation();
  if (trustCheck) await validateInstallation(configFile);
  const cfg = await loadHostConfig(configFile, { trustCheck: false });
  if (trustCheck) {
    const commandRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), 'commands');
    for (const argv of Object.values(cfg.commands)) {
      if (!argv[0].startsWith(commandRoot + path.sep)) bad('approved commands must be administrator-owned wrappers under the installation commands directory');
      await secureTrustedFile(argv[0], 'approved command wrapper');
    }
  }
  const request = parseRequest(await readStdin());
  if (hostAbort.signal.aborted) bad('operation cancelled before execution');
  return execute(request, cfg, { runner });
}
async function main() {
  const stop = () => hostAbort.abort();
  for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, stop);
  process.stdout.on('error', () => { process.exitCode = 1; });
  try {
    console.log(response(await serve()));
  } catch (error) {
    console.log(response({ outcome: 'failure', error: error.message, code: error.code || 'host_error' }));
    process.exitCode = 1;
  } finally {
    for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.off(signal, stop);
  }
}
if (import.meta.url === `file://${process.argv[1]}`) main();
