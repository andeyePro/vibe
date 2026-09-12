/** Version 1, deliberately small, wire protocol shared by client and host. */
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';

export const VERSION = 1;
export const LIMITS = Object.freeze({
  maxFiles: 10_000, maxFileBytes: 8 * 1024 * 1024,
  maxDecodedBytes: 32 * 1024 * 1024, maxWireBytes: 48 * 1024 * 1024,
});
export class ProtocolError extends Error {
  constructor(message, code = 'invalid_request') {
    super(message);
    this.code = code;
  }
}
export const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
export const safeRelativePath = value => typeof value === 'string' && value.length > 0 && value.length <= 1024 &&
  !/[^\x20-\x7e]/.test(value) && !value.startsWith('/') && !value.includes('\\') && !value.split('/').some(x => !x || x === '.' || x === '..' || x.includes('\0'));
export function comparePaths(a, b) { return Buffer.compare(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8')); }
export function assertSnapshotPathSet(paths) {
  const ordered = [...paths].sort(comparePaths);
  const folded = new Set();
  const foldPath = value => value.normalize('NFD').toLowerCase();
  const exact = new Set(ordered.map(foldPath));
  for (let index = 0; index < ordered.length; index += 1) {
    const entry = ordered[index];
    const fold = foldPath(entry);
    if (folded.has(fold)) throw new ProtocolError('case-insensitive snapshot path collision');
    folded.add(fold);
    for (let parent = entry.indexOf('/'); parent !== -1; parent = entry.indexOf('/', parent + 1)) {
      if (exact.has(foldPath(entry.slice(0, parent)))) throw new ProtocolError('snapshot file-parent collision');
    }
  }
  return ordered;
}
export function decodeBase64(value) {
  if (typeof value !== 'string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) throw new ProtocolError('content is not canonical base64');
  const out = Buffer.from(value, 'base64');
  if (out.toString('base64') !== value) throw new ProtocolError('content is not canonical base64');
  return out;
}
export function canonicalFiles(files) {
  if (!Array.isArray(files) || files.length > LIMITS.maxFiles) throw new ProtocolError('invalid file count');
  const seen = new Set();
  let total = 0;
  const out = files.map(file => {
    if (!file || typeof file !== 'object' || !safeRelativePath(file.path) || ![420, 493].includes(file.mode)) throw new ProtocolError('invalid snapshot path or mode');
    if (seen.has(file.path)) throw new ProtocolError('duplicate snapshot path');
    seen.add(file.path);
    const content = decodeBase64(file.content);
    if (content.length > LIMITS.maxFileBytes) throw new ProtocolError('snapshot file too large');
    total += content.length;
    if (total > LIMITS.maxDecodedBytes) throw new ProtocolError('snapshot too large');
    return { path: file.path, mode: file.mode, content: file.content };
  });
  assertSnapshotPathSet(out.map(file => file.path));
  return out.sort((a, b) => comparePaths(a.path, b.path));
}
// The on-wire definition uses triples, rather than object key ordering, to be language-neutral.
export function digestFiles(files) {
  const triples = canonicalFiles(files).map(file => [file.path, file.mode, file.content]);
  return sha256(Buffer.from(JSON.stringify(triples), 'utf8'));
}
export function parseRequest(input) {
  if (Buffer.byteLength(input, 'utf8') > LIMITS.maxWireBytes) throw new ProtocolError('request exceeds wire limit', 'too_large');
  let req;
  try {
    req = JSON.parse(input);
  } catch {
    throw new ProtocolError('request is not JSON');
  }
  if (!req || typeof req !== 'object' || req.version !== VERSION || typeof req.jobId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(req.jobId) ||
      !['doctor', 'build', 'test', 'screenshot'].includes(req.operation) || typeof req.digest !== 'string' || !/^[0-9a-f]{64}$/i.test(req.digest)) throw new ProtocolError('invalid request envelope');
  if (Object.keys(req).some(k => !['version', 'jobId', 'operation', 'files', 'digest'].includes(k))) throw new ProtocolError('unsupported request field');
  const files = canonicalFiles(req.files);
  if (digestFiles(files) !== req.digest.toLowerCase()) throw new ProtocolError('snapshot digest mismatch');
  return { version: VERSION, jobId: req.jobId, operation: req.operation, files, digest: req.digest.toLowerCase() };
}
export function response(fields) { return JSON.stringify({ version: VERSION, ...fields }); }

// Node exposes no openat: retain and check each component's descriptor, then
// recheck pathname identities before releasing data. This mitigates swaps; it
// cannot defeat an adversary that repeatedly swaps and restores ancestors.
export async function withCheckedPath(file, directory, action) {
  if (!path.isAbsolute(file) || path.resolve(file) !== file) {
    throw new ProtocolError('path must be absolute and normalized');
  }
  const opened = [];
  const same = (a, b) => a.dev === b.dev && a.ino === b.ino;
  const verify = async () => {
    for (const entry of opened) {
      const current = await fs.lstat(entry.name);
      const descriptor = await entry.handle.stat();
      if (current.isSymbolicLink() || !same(current, entry.stat) ||
          !same(descriptor, entry.stat)) {
        throw new ProtocolError('path identity changed during access');
      }
    }
  };
  try {
    const components = file.split(path.sep).filter(Boolean);
    let name = path.parse(file).root;
    for (let index = -1; index < components.length; index += 1) {
      if (index >= 0) name = path.join(name, components[index]);
      const isDirectory = index < components.length - 1 || directory;
      const before = await fs.lstat(name);
      if (before.isSymbolicLink() ||
          !(isDirectory ? before.isDirectory() : before.isFile())) {
        throw new ProtocolError('path contains a symlink or non-ordinary entry');
      }
      const handle = await fs.open(name, constants.O_RDONLY | constants.O_NOFOLLOW |
        constants.O_NONBLOCK | (isDirectory ? constants.O_DIRECTORY : 0));
      const entry = { name, handle };
      opened.push(entry);
      const stat = await handle.stat();
      entry.stat = stat;
      if (!same(before, stat) || !(isDirectory ? stat.isDirectory() : stat.isFile())) {
        throw new ProtocolError('path changed while opening');
      }
    }
    await verify();
    const leaf = opened.at(-1);
    const value = await action(leaf.handle, leaf.stat);
    await verify();
    return value;
  } finally {
    await Promise.all(opened.map(entry => entry.handle.close()));
  }
}

export async function readBoundedFile(file, maximum, label = 'file') {
  return withCheckedPath(file, false, async (handle, stat) => {
    if (stat.nlink !== 1) throw new ProtocolError(`${label} must not be hardlinked`);
    if (stat.size > maximum) throw new ProtocolError(`${label} exceeds its size limit`);
    const chunks = [];
    let total = 0;
    while (true) {
      const buffer = Buffer.alloc(Math.min(65536, maximum - total + 1));
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null);
      if (!bytesRead) break;
      total += bytesRead;
      if (total > maximum) throw new ProtocolError(`${label} exceeds its size limit`);
      chunks.push(buffer.subarray(0, bytesRead));
    }
    const after = await handle.stat();
    if (stat.size !== after.size || stat.mtimeMs !== after.mtimeMs ||
        stat.ctimeMs !== after.ctimeMs) throw new ProtocolError(`${label} changed during read`);
    return { bytes: Buffer.concat(chunks, total), stat };
  });
}
