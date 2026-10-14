#!/usr/bin/env node
// vibe-models: which model a vibe delegate may use (2026-10-14, Martin's
// model-routing policy). Four rules, one place:
//
//   1. Latest in class. A class name (astra, sol, luna, terra; fable, opus,
//      sonnet, haiku) always means the newest model of that class. OpenAI
//      classes resolve from Codex's own model catalog (highest gpt-<N>-<class>
//      version the account lists); Claude classes stay as Claude Code's
//      aliases, which already track the newest model. Never a hard-coded id:
//      the hard-coded `sol` -> gpt-5.6-sol mapping is what ran two releases
//      behind on 2026-10-13.
//   2. The lead is the model the user picked for the conversation. Read from
//      that conversation's own transcript (Codex: CODEX_THREAD_ID's rollout;
//      Claude Code: the session transcript), never from a resumed thread's
//      history or a launcher default.
//   3. Cost ceiling. Per-token cost order, Martin 2026-10-14:
//      Astra > Sol > Luna > Terra and Fable > Opus > Sonnet > Haiku. A
//      delegate in a dearer tier than the lead needs the user's current,
//      explicit authorisation: a --consent-model flag on the one call, or a
//      time-boxed `vibe-models grant`. Cross-vendor, tiers compare by
//      position (Astra~Fable, Sol~Opus, Luna~Sonnet, Terra~Haiku); that
//      pairing is vibe's assumption, not a published price comparison.
//   4. Older models only on request. `vibe-models pin <class> <model> --for
//      <duration>` records the user's request for an older model and how long
//      it stands. A pin unconfirmed for 8 wall-hours stops resolving until the
//      user re-confirms it (`vibe-models confirm <class>`); an expired pin
//      drops back to latest.
//
// Like --consent-credits, grants and pins are a convention the lead follows
// after asking the user: the lead can run the command itself. The value is
// that every escalation is an explicit, logged, time-boxed step rather than a
// silent default. State: <repo>/.vibe/model-policy.json (vibe's managed
// .gitignore block already excludes .vibe/).
import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, readFileSync, readdirSync, renameSync, writeFileSync, mkdirSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

export const CLASSES = Object.freeze({
  terra: { vendor: 'openai', tier: 0 }, luna: { vendor: 'openai', tier: 1 },
  sol: { vendor: 'openai', tier: 2 }, astra: { vendor: 'openai', tier: 3 },
  haiku: { vendor: 'claude', tier: 0 }, sonnet: { vendor: 'claude', tier: 1 },
  opus: { vendor: 'claude', tier: 2 }, fable: { vendor: 'claude', tier: 3 },
});
export const RECONFIRM_SECONDS = 8 * 3600;
const OPENAI_ID = /^gpt-(\d+(?:\.\d+)*)-(astra|sol|luna|terra)$/;
const CLAUDE_ID = /^claude-(fable|opus|sonnet|haiku)(?:-|$)/;

export class PolicyError extends Error {
  constructor(message, code = 'policy') { super(message); this.code = code; }
}

// Class of a model id or alias; null when vibe does not know it (unknown ids
// never pass the ceiling check).
export function classOf(model) {
  if (typeof model !== 'string') return null;
  const id = model.trim().toLowerCase().replace(/\[.*\]$/, '');
  if (Object.hasOwn(CLASSES, id)) return id;
  const openai = OPENAI_ID.exec(id);
  if (openai) return openai[2];
  const claude = CLAUDE_ID.exec(id);
  return claude ? claude[1] : null;
}

function compareVersions(a, b) {
  const x = a.split('.').map(Number), y = b.split('.').map(Number);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] || 0) - (y[i] || 0);
    if (d) return d;
  }
  return 0;
}

// Highest listed gpt-<version>-<class> per OpenAI class. Hidden catalog
// entries are skipped: they are not offered to the account.
export function latestOpenAI(models) {
  const best = {};
  for (const m of Array.isArray(models) ? models : []) {
    if (!m || typeof m.slug !== 'string' || (m.visibility && m.visibility !== 'list')) continue;
    const match = OPENAI_ID.exec(m.slug);
    if (!match) continue;
    const [, version, cls] = match;
    if (!best[cls] || compareVersions(version, best[cls].version) > 0) best[cls] = { version, slug: m.slug };
  }
  return Object.fromEntries(Object.entries(best).map(([k, v]) => [k, v.slug]));
}

function codexHome(env) { return env.CODEX_HOME || join(env.HOME || homedir(), '.codex'); }

// Codex keeps the account's catalog in $CODEX_HOME/models_cache.json and
// refreshes it itself; `codex debug models` renders the same catalog and is
// the fallback when the cache is absent.
export function loadCatalog(env = process.env) {
  try {
    const cache = JSON.parse(readFileSync(join(codexHome(env), 'models_cache.json'), 'utf8'));
    if (Array.isArray(cache?.models) && cache.models.length) return cache.models;
  } catch { /* fall through */ }
  const r = spawnSync('codex', ['debug', 'models'], { env, input: '', encoding: 'utf8', timeout: 30000 });
  if (!r.error && r.status === 0) {
    try {
      const out = JSON.parse(r.stdout);
      const models = Array.isArray(out) ? out : out?.models;
      if (Array.isArray(models) && models.length) return models;
    } catch { /* fall through */ }
  }
  throw new PolicyError('cannot read the Codex model catalog (no models_cache.json and `codex debug models` failed); refusing to guess a model id', 'catalog');
}

function lastJsonl(path, pick) {
  let found = null;
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try { const v = pick(JSON.parse(line)); if (v) found = v; } catch { /* torn line */ }
  }
  return found;
}

function findRollout(dir, threadId, depth = 0) {
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return null; }
  // Date-named directories: newest first, so the live thread is found fast.
  entries.sort((a, b) => b.name.localeCompare(a.name));
  for (const e of entries) {
    if (e.isFile() && e.name.startsWith('rollout-') && e.name.endsWith(`-${threadId}.jsonl`)) return join(dir, e.name);
  }
  if (depth >= 3) return null;
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const hit = findRollout(join(dir, e.name), threadId, depth + 1);
    if (hit) return hit;
  }
  return null;
}

const codexTurnModel = (r) => (r?.type === 'turn_context' && typeof r.payload?.model === 'string' ? r.payload.model : null);
const claudeTurnModel = (r) => {
  // Sidechain records are subagents' turns, never the lead's.
  const m = r?.type === 'assistant' && !r.isSidechain ? r.message?.model : null;
  return typeof m === 'string' && !m.startsWith('<') ? m : null;
};

// The model of the conversation that is asking. Order: an explicit
// VIBE_LEAD_MODEL (an operator override, and tests);
// a hook's transcript_path; the Codex thread's rollout; the Claude session
// transcript. Returns null when none can be read; callers fail closed.
export function detectLead(env = process.env, { transcriptPath } = {}) {
  if (env.VIBE_LEAD_MODEL) return env.VIBE_LEAD_MODEL;
  if (transcriptPath && isAbsolute(transcriptPath) && existsSync(transcriptPath)) {
    const m = lastJsonl(transcriptPath, (r) => claudeTurnModel(r) || codexTurnModel(r));
    if (m) return m;
  }
  if (env.CODEX_THREAD_ID && /^[0-9a-f-]{8,}$/i.test(env.CODEX_THREAD_ID)) {
    const rollout = findRollout(join(codexHome(env), 'sessions'), env.CODEX_THREAD_ID);
    const m = rollout && lastJsonl(rollout, codexTurnModel);
    if (m) return m;
  }
  if (env.CLAUDE_CODE_SESSION_ID && /^[0-9a-f-]{8,}$/i.test(env.CLAUDE_CODE_SESSION_ID)) {
    const projects = join(env.CLAUDE_CONFIG_DIR || join(env.HOME || homedir(), '.claude'), 'projects');
    let dirs = [];
    try { dirs = readdirSync(projects); } catch { /* none */ }
    for (const d of dirs) {
      const p = join(projects, d, `${env.CLAUDE_CODE_SESSION_ID}.jsonl`);
      if (existsSync(p)) { const m = lastJsonl(p, claudeTurnModel); if (m) return m; }
    }
  }
  return null;
}

// --- per-project policy state -------------------------------------------

export function policyPath(cwd) {
  const r = spawnSync('git', ['-C', cwd, 'rev-parse', '--show-toplevel'], { input: '', encoding: 'utf8', timeout: 10000 });
  const root = r.status === 0 && r.stdout.trim() ? r.stdout.trim() : cwd;
  return join(root, '.vibe', 'model-policy.json');
}

export function readPolicy(path) {
  try {
    if (lstatSync(path).isSymbolicLink()) throw new PolicyError(`${path} is a symlink; refusing it`);
  } catch (e) { if (e instanceof PolicyError) throw e; return { pins: {}, grants: {} }; }
  let data;
  try { data = JSON.parse(readFileSync(path, 'utf8')); } catch { throw new PolicyError(`${path} is not valid JSON; fix or delete it`); }
  return { pins: data?.pins && typeof data.pins === 'object' ? data.pins : {},
    grants: data?.grants && typeof data.grants === 'object' ? data.grants : {} };
}

function writePolicy(path, policy) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp.${process.pid}`;
  writeFileSync(tmp, JSON.stringify(policy, null, 2) + '\n', { mode: 0o600 });
  renameSync(tmp, path);
}

export function parseDuration(text) {
  const m = /^(\d+)([mhd])$/.exec(text || '');
  if (!m || Number(m[1]) <= 0) throw new PolicyError('duration must look like 30m, 8h or 2d');
  return Number(m[1]) * { m: 60, h: 3600, d: 86400 }[m[2]];
}

const nowSeconds = (env) => Number(env.VIBE_MODELS_NOW) || Math.floor(Date.now() / 1000);

// Model id to dispatch for a class, applying any older-model pin.
export function resolveModel(cls, { env = process.env, policy = { pins: {} }, catalog } = {}) {
  if (!Object.hasOwn(CLASSES, cls)) throw new PolicyError(`unknown model class: ${cls}`);
  const now = nowSeconds(env);
  const pin = policy.pins?.[cls];
  if (pin && !(Number(pin.until) <= now)) {
    // A pin with a missing or non-numeric time (hand-edited file) is treated
    // as due for reconfirmation, never as standing for ever.
    if (!Number.isFinite(Number(pin.until)) || !Number.isFinite(Number(pin.confirmed))
        || now - Number(pin.confirmed) >= RECONFIRM_SECONDS) {
      throw new PolicyError(`the older-model instruction for ${cls} (${pin.model}) was last confirmed over 8 hours ago: ` +
        `ask the user whether it still stands, then run \`vibe-models confirm ${cls}\` or \`vibe-models unpin ${cls}\``, 'reconfirm');
    }
    return pin.model;
  }
  if (CLASSES[cls].vendor === 'claude') return cls;
  const latest = latestOpenAI(catalog || loadCatalog(env))[cls];
  if (!latest) throw new PolicyError(`no ${cls} model is listed in this account's Codex catalog`, 'catalog');
  return latest;
}

// Throws unless `cls` is within the lead's tier or currently authorised.
export function checkCeiling(cls, lead, { env = process.env, policy = { grants: {} }, consent = false } = {}) {
  const leadClass = classOf(lead);
  if (!leadClass) {
    throw new PolicyError(lead
      ? `lead model ${lead} is not a class vibe knows, so the cost ceiling cannot be applied; refusing`
      : 'cannot tell which model is leading this conversation, so the cost ceiling cannot be applied; refusing (set VIBE_LEAD_MODEL to the conversation\'s model)', 'lead');
  }
  if (CLASSES[cls].tier <= CLASSES[leadClass].tier) return { leadClass, authorisedBy: 'ceiling' };
  if (consent) return { leadClass, authorisedBy: 'consent-flag' };
  const grant = policy.grants?.[cls];
  if (grant && Number(grant.until) > nowSeconds(env)) return { leadClass, authorisedBy: 'grant' };
  throw new PolicyError(`${cls} costs more per token than the lead (${lead}, class ${leadClass}); ` +
    `ask the user for explicit permission first, then pass --consent-model on this call or run \`vibe-models grant ${cls} --for <duration>\``, 'ceiling');
}

// --- CLI ----------------------------------------------------------------

function deny(reason) {
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse',
    permissionDecision: 'deny', permissionDecisionReason: `vibe-models: ${reason}` } }) + '\n');
}

// The `model:` an agent definition pins in its frontmatter, or null when it
// inherits the lead (no line, or `inherit`). Project definitions shadow user
// ones, as in Claude Code. Throws when a definition exists but can't be read.
function agentDefinitionModel(type, cwd, env) {
  if (typeof type !== 'string' || !/^[A-Za-z0-9._-]+$/.test(type)) return null;
  const dirs = [join(cwd, '.claude', 'agents'),
    join(env.CLAUDE_CONFIG_DIR || join(env.HOME || homedir(), '.claude'), 'agents')];
  for (const dir of dirs) {
    const path = join(dir, `${type}.md`);
    if (!existsSync(path)) continue;
    let text;
    try { text = readFileSync(path, 'utf8'); } catch { throw new PolicyError(`cannot read the ${type} agent definition to check its model`); }
    const front = /^---\n([\s\S]*?)\n---/.exec(text);
    const line = front && /^model:\s*["']?([^"'\s#]+)/m.exec(front[1]);
    return line && line[1] !== 'inherit' ? line[1] : null;
  }
  return null;
}

// Claude Code PreToolUse hook on Agent/Task: the same ceiling and pin rules
// for Claude's own subagent dispatch, which never goes through vibe-delegate.
// The model is the call's `model`, else the agent definition's `model:`;
// neither means the subagent inherits the lead's model: allowed.
function hook() {
  let input;
  try { input = JSON.parse(readFileSync(0, 'utf8')); } catch { return; }
  const cwd0 = typeof input?.cwd === 'string' && isAbsolute(input.cwd) ? input.cwd : process.cwd();
  let model = input?.tool_input?.model;
  if (typeof model !== 'string' || !model.trim()) {
    try { model = agentDefinitionModel(input?.tool_input?.subagent_type, cwd0, process.env); }
    catch (e) { deny(e.message); return; }
    if (!model) return;
  }
  const cls = classOf(model);
  if (!cls) { deny(`unknown subagent model ${model}; use opus, sonnet, haiku or fable`); return; }
  try {
    const cwd = typeof input.cwd === 'string' && isAbsolute(input.cwd) ? input.cwd : process.cwd();
    const policy = readPolicy(policyPath(cwd));
    const lead = detectLead(process.env, { transcriptPath: input.transcript_path });
    checkCeiling(cls, lead, { policy });
    const pinned = policy.pins?.[cls];
    if (pinned) {
      const want = resolveModel(cls, { policy });
      if (want !== cls && model !== want) deny(`the user asked for ${want} for ${cls} work; dispatch with model "${want}"`);
    }
  } catch (e) { deny(e.message); }
}

function usage() {
  return 'usage: vibe-models status | lead | resolve <class> | pin <class> <model-id> --for <dur> | confirm <class> | ' +
    'unpin <class> | grant <class> --for <dur> | revoke <class> | hook   [--cwd <dir>]';
}

function main(argv) {
  const args = [...argv];
  let cwd = process.cwd();
  const ci = args.indexOf('--cwd');
  if (ci !== -1) { cwd = args[ci + 1]; args.splice(ci, 2); if (!cwd || !isAbsolute(cwd)) throw new PolicyError('--cwd needs an absolute path'); }
  let forSeconds = null;
  const fi = args.indexOf('--for');
  if (fi !== -1) { forSeconds = parseDuration(args[fi + 1]); args.splice(fi, 2); }
  const [cmd, cls, model] = args;
  if (cmd === 'hook') { hook(); return 0; }
  const path = policyPath(cwd);
  const policy = readPolicy(path);
  const now = nowSeconds(process.env);
  const needClass = () => { if (!Object.hasOwn(CLASSES, cls || '')) throw new PolicyError(`unknown model class: ${cls}\n${usage()}`); };
  switch (cmd) {
    case 'lead': {
      const lead = detectLead();
      if (!lead) throw new PolicyError('cannot tell which model is leading this conversation', 'lead');
      process.stdout.write(`${lead}\n`);
      return 0;
    }
    case 'resolve':
      needClass();
      process.stdout.write(`${resolveModel(cls, { policy })}\n`);
      return 0;
    case 'status': {
      const lead = detectLead();
      const leadClass = classOf(lead);
      let latest = {};
      let catalogError = null;
      try { latest = latestOpenAI(loadCatalog()); } catch (e) { catalogError = e.message; }
      const allowed = leadClass ? Object.keys(CLASSES).filter((c) => CLASSES[c].tier <= CLASSES[leadClass].tier) : [];
      process.stdout.write(JSON.stringify({ lead, leadClass, allowedWithoutAsking: allowed,
        latest: { ...latest, opus: 'opus', sonnet: 'sonnet', haiku: 'haiku', fable: 'fable' },
        catalogError, pins: policy.pins, grants: policy.grants, policyFile: path, now }, null, 2) + '\n');
      return 0;
    }
    case 'pin':
      needClass();
      if (!model || classOf(model) !== cls) throw new PolicyError(`pin needs a ${cls} model id, e.g. vibe-models pin ${cls} <id> --for 8h`);
      if (!forSeconds) throw new PolicyError('pin needs --for <duration>: ask the user how long the older model should be used');
      policy.pins[cls] = { model, granted: now, confirmed: now, until: now + forSeconds };
      break;
    case 'confirm':
      needClass();
      if (!policy.pins[cls]) throw new PolicyError(`no older-model instruction is recorded for ${cls}`);
      policy.pins[cls].confirmed = now;
      break;
    case 'unpin': needClass(); delete policy.pins[cls]; break;
    case 'grant':
      needClass();
      if (!forSeconds) throw new PolicyError('grant needs --for <duration> matching what the user authorised');
      policy.grants[cls] = { granted: now, until: now + forSeconds };
      break;
    case 'revoke': needClass(); delete policy.grants[cls]; break;
    default: throw new PolicyError(usage());
  }
  writePolicy(path, policy);
  process.stdout.write(`${cmd} ${cls}: recorded in ${path}\n`);
  return 0;
}

const self = fileURLToPath(import.meta.url);
if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(self)) {
  try { process.exitCode = main(process.argv.slice(2)); } catch (e) {
    process.stderr.write(`vibe-models: ${e.message}\n`);
    process.exitCode = e.code === 'reconfirm' ? 3 : e.code === 'ceiling' ? 4 : 1;
  }
}
