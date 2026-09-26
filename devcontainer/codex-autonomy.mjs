#!/usr/bin/env node
// Codex-only durable runner. The reaper is our child: only its empty-tree
// acknowledgement permits removing OUR child's abandoned lock and retrying.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, openSync, closeSync, realpathSync, unlinkSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { completionPolicy } from './codex-completion.mjs';
import { acquire, atomicWrite, canonicalPath, readRegular, requestStop, ownershipFresh, spawnOwnedProcess, closeServer, appendRegular } from './supervisor-control.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const supervisor = existsSync(join(here, 'codex-supervisor')) ? join(here, 'codex-supervisor') : join(here, 'codex-supervisor.mjs');
const { parseArgs } = await import(supervisor);
const pause = ms => new Promise(r => setTimeout(r, ms));
const read = p => JSON.parse(readRegular(p));
export async function watch(args) {
  const options = parseArgs(args);
  if (options.command !== 'run' || options.runnerToken) throw new Error('runner requires an ordinary run command');
  const statePath = canonicalPath(options.state, true);
  // Direct watch and detached start share the publication mutex. Only the
  // child carrying start's live handoff nonce may inherit that transfer.
  let publication = null;
  const handoffId = process.env.VIBE_CODEX_HANDOFF_ID;
  if (handoffId) {
    if (!ownershipFresh(`${statePath}.handoff`) || read(`${statePath}.handoff.lock`).token !== handoffId) throw new Error('handoff ownership unconfirmed');
  } else publication = acquire(`${statePath}.handoff`);
  let owner;
  try { owner = acquire(`${statePath}.runner`); }
  finally { publication?.release(); }
  let stopping = false, child = null, empty = true;
  const onSignal = () => { stopping = true; };
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(sig, onSignal);
  const log = message => appendRegular(`${statePath}.runner.log`, `${new Date().toISOString()} ${message}\n`);
  let failures = 0, lastProgress = -1;
  try {
    if (process.env.VIBE_CODEX_HANDOFF_ID) atomicWrite(`${statePath}.runner.ack.json`, JSON.stringify({ handoffId: process.env.VIBE_CODEX_HANDOFF_ID, owner: owner.token }));
    for (;;) {
      if (stopping || owner.stopped()) return 130;
      if (existsSync(`${statePath}.lock`)) throw new Error('existing supervisor lock requires explicit reconciliation');
      const argv = [...args, '--runner-token', owner.token];
      if (existsSync(statePath)) argv.push('--recover-completed');
      child = spawnOwnedProcess(process.execPath, [supervisor, ...argv], process.env);
      empty = false;
      child.stdin.end();
      child.stdout.pipe(process.stdout, { end: false });
      child.stderr.pipe(process.stderr, { end: false });
      const ended = new Promise((resolveExit, reject) => { child.once('exit', code => resolveExit(code)); child.once('error', reject); });
      let stopAt = null;
      const poll = setInterval(() => {
        try {
          if (stopping || owner.stopped()) {
            stopping = true;
            stopAt ??= Date.now();
            if (existsSync(`${statePath}.lock`)) requestStop(statePath);
            // Cooperative first, then terminate only our owned child tree.
            if (Date.now() - stopAt > 10000) child.kill('SIGTERM');
          }
        } catch { stopping = true; child.kill('SIGTERM'); }
      }, 100);
      let code;
      try { code = await ended; }
      finally { clearInterval(poll); }
      await closeServer({ child, closeStdin() {}, shutdown() {} });
      empty = true;
      // A SIGKILLed supervisor cannot release its own token. Never touch a
      // foreign token, even after proving this child's descendants ended.
      const lockPath = `${statePath}.lock`;
      if (existsSync(lockPath)) {
        if (read(lockPath).token !== owner.token) throw new Error('foreign supervisor lock; recovery refused');
        unlinkSync(lockPath);
        const stopPath = `${statePath}.stop.${owner.token}`;
        if (existsSync(stopPath)) { stopping = true; if (readRegular(stopPath).trim() === owner.token) unlinkSync(stopPath); }
      }
      if (stopping || owner.stopped() || code === 130) return 130;
      if (code === 0 || code === 2 || code === 3) return code;
      if (!existsSync(statePath)) throw new Error('supervisor ended before a recoverable checkpoint');
      const state = read(statePath);
      // A terminal file may belong to the preceding invocation (--new-run
      // can fail before archiving it). Never turn a child failure into success.
      if (state.exitReason !== undefined) return 1;
      if (!state.threadId || ['stop-requested', 'turn-interrupted', 'budget-exhausted', 'context-exhausted', 'ceiling-reached'].includes(state.recoveryReason)) return 1;
      const progress = Array.isArray(state.turns) ? state.turns.filter(turn => turn.status === 'completed').length : 0;
      if (progress > lastProgress) { failures = 0; lastProgress = progress; }
      if (++failures >= 3) { log('process failure ceiling; checkpoint retained'); return 1; }
      log(`owned tree empty; restart ${failures}; completed-turn reconciliation required if unresolved`);
      // --new-run is a one-shot operation; it must never archive on recovery.
      args = args.filter(a => a !== '--new-run');
      const until = Date.now() + failures * 1000;
      while (Date.now() < until) { if (stopping || owner.stopped()) return 130; await pause(100); }
    }
  } finally {
    try {
      if (!empty && child) {
        child.kill('SIGTERM');
        await closeServer({ child, closeStdin() {}, shutdown() {} });
        empty = true;
      }
    } finally {
      if (empty) owner.release(); else owner.retain();
      for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.off(sig, onSignal);
    }
  }
}

async function main(args) {
  if (args[0] === 'watch' && args[1] === '--') return watch(args.slice(2));
  const command = args.shift();
  const options = {};
  while (args.length) {
    const key = args.shift();
    if (!['--cwd', '--prompt-file', '--state'].includes(key) || !args.length) throw new Error('expected --cwd and --prompt-file');
    options[key] = args.shift();
  }
  const cwd = realpathSync(options['--cwd'] || process.cwd());
  const statePath = options['--state'] ? canonicalPath(resolve(options['--state'])) : join(cwd, '.vss/codex-supervisor.json');
  if (options['--state'] && command === 'start') throw new Error('start uses the default checkout state; use watch for custom paths');
  if (command === 'context') {
    const state = existsSync(statePath) ? read(statePath) : null;
    const owned = !!process.env.CODEX_THREAD_ID && state?.threadId === process.env.CODEX_THREAD_ID && state.cwd === cwd && ownershipFresh(statePath);
    process.stdout.write(JSON.stringify({ supervised: owned, statePath, threadId: owned ? state.threadId : null }) + '\n');
    return 0;
  }
  if (command === 'stop') { requestStop(`${statePath}.runner`); return 0; }
  if (command === 'status') {
    const state = existsSync(statePath) ? read(statePath) : null;
    process.stdout.write(JSON.stringify({ running: ownershipFresh(`${statePath}.runner`), lifecycle: ['running', 'checkpointed', 'complete'].includes(state?.lifecycle) ? state.lifecycle : 'unknown', statePath, log: `${statePath}.runner.output.log` }) + '\n');
    return 0;
  }
  if (command !== 'start' || !options['--prompt-file']) throw new Error('usage: codex-autonomy start --cwd <repo> --prompt-file <brief> | context | status | stop [--cwd <repo>]');
  if (canonicalPath(statePath, true) !== statePath) throw new Error('symlinked state directory');
  const git = spawnSync('git', ['-C', cwd, 'rev-parse', '--show-toplevel', '--git-path', 'info/exclude'], { encoding:'utf8', input:'', timeout:10000 });
  if (git.status !== 0) throw new Error('handoff requires a Git checkout');
  const [top, excludeRel] = git.stdout.trim().split('\n');
  if (realpathSync(top) !== cwd) throw new Error('handoff cwd must be the checkout root');
  const exclude = resolve(cwd, excludeRel);
  const privatePattern = '/.vss/codex-supervisor*';
  let ignored = ''; try { ignored = readRegular(exclude); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  if (!ignored.split('\n').includes(privatePattern)) atomicWrite(exclude, `${ignored}\n${privatePattern}\n`);
  const handoff = acquire(`${statePath}.handoff`);
  let acknowledged = false, spawned = false, daemon = null;
  try {
    if (existsSync(`${statePath}.runner.lock`) || existsSync(`${statePath}.lock`)) throw new Error('existing owner: use status/stop; never start a second writer');
    if (existsSync(statePath) && read(statePath).exitReason === undefined) throw new Error('unfinished checkpoint: resume with the original prompt using vibe --codex-resume');
    const prompt = readRegular(resolve(options['--prompt-file']));
    if (!/^\s*\$vsss(?:\s|$)/.test(prompt)) throw new Error('handoff brief must start with $vsss');
    completionPolicy(prompt); // reject invalid original caps before detaching
    const promptPath = `${statePath}.prompt.txt`;
    atomicWrite(promptPath, prompt.trimStart());
    const outPath = `${statePath}.runner.output.log`;
    appendRegular(outPath, 'Codex supervised handoff requested\n');
    const fd = openSync(outPath, 'a');
    try {
      daemon = spawn(join(here, 'codex-entry'), ['--supervise', '--', 'run', '--cwd', cwd, '--prompt-file', promptPath,
        ...(existsSync(statePath) ? ['--new-run'] : [])], { cwd, detached: true, env: { ...process.env, VIBE_CODEX_HANDOFF_ID: handoff.token }, stdio: ['ignore', fd, fd] });
      await new Promise((res, rej) => { daemon.once('spawn', res); daemon.once('error', rej); });
      spawned = true;
      daemon.unref();
    } finally { closeSync(fd); }
    const until = Date.now() + 30000;
    while (Date.now() < until) {
      try { acknowledged = read(`${statePath}.runner.ack.json`).handoffId === handoff.token; } catch {}
      if (acknowledged || daemon.exitCode !== null) break;
      await pause(100);
    }
    if (!acknowledged) throw new Error(`handoff not acknowledged; inspect ${outPath} and reconcile handoff ownership before retrying`);
    process.stdout.write(`Supervised Codex handoff acknowledged. Stop editing while it runs. Use codex-autonomy status. State: ${statePath}; log: ${outPath}\n`);
    return 0;
  } finally {
    if (acknowledged || !spawned || daemon?.exitCode !== null) handoff.release(); else handoff.retain();
  }
}
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(code => { process.exitCode = code; }, e => { process.stderr.write(`codex-autonomy: ${e.message}\n`); process.exitCode = 1; });
}
