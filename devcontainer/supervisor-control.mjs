// Ownership is fail-closed: never infer ownership or kill from a recorded PID.
import { constants, openSync, closeSync, readFileSync, writeFileSync, fstatSync,
  futimesSync, fchmodSync, fsyncSync, lstatSync, realpathSync, mkdirSync, unlinkSync, renameSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname, basename, resolve, join } from 'node:path';
import { randomUUID } from 'node:crypto';

export function canonicalPath(path, create = false) {
  path = resolve(path);
  if (create) mkdirSync(dirname(path), { recursive: true });
  const parent = realpathSync(dirname(path));
  const result = join(parent, basename(path));
  try {
    const st = lstatSync(result);
    if (!st.isFile() || st.nlink !== 1) throw new Error('must be an ordinary, unlinked file');
  } catch (e) { if (e.code !== 'ENOENT') throw new Error(`Unsafe path ${result}: ${e.message}`); }
  return result;
}

export function readRegular(path) {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const st = fstatSync(fd);
    if (!st.isFile() || st.nlink !== 1 || st.size > 16 * 1024 * 1024) throw new Error('unsafe control file');
    return readFileSync(fd, 'utf8');
  } finally { closeSync(fd); }
}

export function atomicWrite(path, value) {
  canonicalPath(path);
  const tmp = `${path}.${randomUUID()}.tmp`;
  try {
    const fd = openSync(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    try { writeFileSync(fd, value); fsyncSync(fd); } finally { closeSync(fd); }
    renameSync(tmp, path);
    const parent = openSync(dirname(path), constants.O_RDONLY | constants.O_DIRECTORY);
    try { fsyncSync(parent); } finally { closeSync(parent); }
  } finally { try { unlinkSync(tmp); } catch {} }
}

export function acquire(path) {
  const lock = `${path}.lock`;
  const token = randomUUID();
  let fd;
  try { fd = openSync(lock, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600); }
  catch { throw new Error(`Ownership lock exists or is unsafe: ${lock}. No stale lock is stolen. Confirm the previous owner and its children have ended, then explicitly remove this lock and its token-specific stop file before resuming.`); }
  try { writeFileSync(fd, JSON.stringify({ version: 1, token })); }
  catch (e) { closeSync(fd); throw e; }
  const heartbeat = setInterval(() => { try { const now = new Date(); futimesSync(fd, now, now); } catch {} }, 100);
  const stopPath = `${path}.stop.${token}`;
  return {
    token,
    retain() {
      clearInterval(heartbeat);
      closeSync(fd);
      // The lock remains for explicit reconciliation, without a false heartbeat.
    },
    stopped() {
      try { return readRegular(stopPath).trim() === token; }
      catch (e) { if (e.code === 'ENOENT') return false; throw e; }
    },
    release() {
      clearInterval(heartbeat);
      closeSync(fd);
      try {
        if (JSON.parse(readRegular(lock)).token !== token) return;
        try { if (readRegular(stopPath).trim() === token) unlinkSync(stopPath); } catch {}
        unlinkSync(lock);
      } catch {} // An altered/ambiguous lock must be explicitly reconciled.
    },
  };
}

export function requestStop(path) {
  const lock = JSON.parse(readRegular(`${path}.lock`));
  if (lock.version !== 1 || !/^[0-9a-f-]{36}$/.test(lock.token)) throw new Error('Ambiguous ownership lock; reconcile it explicitly');
  const stopPath = `${path}.stop.${lock.token}`;
  try { writeFileSync(stopPath, lock.token, { flag: 'wx', mode: 0o600 }); }
  catch (e) { if (e.code !== 'EEXIST' || readRegular(stopPath) !== lock.token) throw e; }
}

// A Linux subreaper owns even double-forked/setsid descendants. Only this
// helper can acknowledge an empty child tree; an exit or timeout alone cannot.
// No extra files, shell evaluation, Codex flags, or environment entries.
const REAPER = String.raw`
import ctypes, os, signal, sys, time
ack = 3
os.set_inheritable(ack, False)
def empty():
    os.write(ack, b'empty\n')
    os.close(ack)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    empty()
    sys.exit('cannot establish child subreaper')
stopping = False
def stop(signum, frame):
    global stopping
    stopping = True
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
root = os.fork()
if root == 0:
    os.close(ack)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        os.execvpe(sys.argv[1], [sys.argv[1], 'app-server'], os.environ)
    except Exception as error:
        print(str(error), file=sys.stderr)
        os._exit(127)
result = 1
while True:
    try:
        pid, status = os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        empty()
        sys.exit(result)
    if pid:
        if pid == root:
            result = os.waitstatus_to_exitcode(status)
            if result < 0:
                result = 128 - result
            stopping = True
        continue
    if stopping:
        # Children cannot have their PIDs reused until this sole reaper waits.
        # Kill parents first; orphaned descendants are then adopted and killed.
        with open('/proc/self/task/%d/children' % os.getpid()) as children:
            for child in children.read().split():
                try:
                    os.kill(int(child), signal.SIGKILL)
                except ProcessLookupError:
                    pass
    time.sleep(0.02)
`;

export function spawnOwnedServer(binary, env) {
  if (process.platform !== 'linux') throw new Error('Owned process-tree cleanup requires Linux');
  const child = spawn('/usr/bin/python3', ['-I', '-c', REAPER, binary], {
    env, stdio: ['pipe', 'pipe', 'pipe', 'pipe'],
  });
  child.treeEmpty = false;
  let evidence = '';
  child.stdio[3].setEncoding('utf8');
  child.stdio[3].on('data', chunk => { evidence += chunk; });
  child.stdio[3].on('end', () => { child.treeEmpty ||= evidence === 'empty\n'; });
  child.on('error', () => {
    // A failed spawn with no PID never created a process tree.
    if (child.pid === undefined) child.treeEmpty = true;
  });
  return child;
}

export async function closeServer(server) {
  if (!server) return;
  server.closeStdin();
  const child = server.child;
  const wait = async (ms) => {
    const end = Date.now() + ms;
    while (!confirmed() && Date.now() < end) {
      await new Promise(r => setTimeout(r, 50));
    }
  };
  const confirmed = () => child.treeEmpty === true
    && (child.pid === undefined || child.exitCode !== null || child.signalCode !== null);
  await wait(7000);
  // SIGTERM asks the reaper to SIGKILL and reap the entire tree. Killing the
  // reaper itself would destroy the only evidence that containment is empty.
  if (!confirmed() && child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
  await wait(2000);
  server.shutdown();
  if (!confirmed()) throw new Error('Process-tree termination unconfirmed; ownership lock retained. Confirm all previous descendants have ended before removing the lock.');
}

export function ownershipFresh(path) {
  try {
    const value = JSON.parse(readRegular(`${path}.lock`));
    return value.version === 1 && /^[0-9a-f-]{36}$/.test(value.token)
      && Date.now() - lstatSync(`${path}.lock`).mtimeMs < 1000;
  } catch { return false; }
}

export function appendRegular(path, text) {
  const fd = openSync(path, constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | constants.O_NOFOLLOW | constants.O_NONBLOCK, 0o600);
  try {
    const st = fstatSync(fd);
    if (!st.isFile() || st.nlink !== 1 || typeof process.geteuid !== 'function' || st.uid !== process.geteuid()) throw new Error('unsafe log file');
    fchmodSync(fd, 0o600);
    const privateStat = fstatSync(fd);
    if ((privateStat.mode & 0o7777) !== 0o600 || privateStat.nlink !== 1 || privateStat.uid !== process.geteuid()) throw new Error('unsafe log permissions');
    writeFileSync(fd, text);
  } finally { closeSync(fd); }
}
