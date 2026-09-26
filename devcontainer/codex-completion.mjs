// Codex-only completion evidence. Consistency checks, not a claim that an
// agent's account proves semantic perfection. Never used by Claude hooks.
import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { join } from 'node:path';
import { readRegular } from './supervisor-control.mjs';

const text = v => typeof v === 'string' && v.trim().length > 0;
const hash = s => createHash('sha256').update(s).digest('hex');
export function completionPolicy(prompt) {
  const tokens = prompt.trim().split(/\s+/);
  if (!['$vsss', '/vsss'].includes(tokens.shift())) return null;
  let hours = null, budget = null;
  // Only leading command options are authority, never flag-looking prose.
  while (tokens.length && tokens[0].startsWith('--')) {
    const flag = tokens.shift();
    if (['--hours', '--budget', '--sessions', '--auto-resume'].includes(flag)) {
      const value = tokens.shift();
      if (flag === '--hours' && hours === null) {
        if (!/^\d+(?:\.\d+)?$/.test(value) || Number(value) <= 0) throw new Error('invalid --hours cap');
        hours = Number(value) * 3600;
      } else if (flag === '--budget' && budget === null) {
        const m = /^(\d+(?:\.\d+)?)(h|m)$/.exec(value || '');
        if (!m || Number(m[1]) <= 0) throw new Error('invalid --budget cap');
        budget = Number(m[1]) * (m[2] === 'h' ? 3600 : 60);
      }
    } else if (flag === '--wide' && /^\d+$/.test(tokens[0] || '')) {
      tokens.shift();
    } else if (!['--resume', '--wide', '--narrow', '--spec-first', '--TDD', '--push-on-pass', '--fable', '--fable-subagents'].includes(flag)) {
      break;
    }
  }
  const budgetSeconds = hours ?? budget;
  if (budgetSeconds !== null && (!Number.isFinite(budgetSeconds) || budgetSeconds > Number.MAX_SAFE_INTEGER)) throw new Error('invalid time cap');
  return { version: 1, budgetSeconds };
}

export function completionChallenge(statePath, error) {
  return `Codex continuation: completion was not accepted (${error}). Read ${statePath} and /usr/local/share/vibe/codex-vsss.md. Continue unblocked work. If a numbered exit condition actually holds, atomically write ${statePath}.completion.json with the required run-bound evidence and session audit, then report VSSS-EXIT again. A milestone, question or context length alone is not completion. User stop always wins.`;
}

export function validateCompletion(statePath, state, now) {
  try {
    const c = JSON.parse(readRegular(`${statePath}.completion.json`));
    const policy = state.completion;
    if (!policy || c.version !== 1 || c.runId !== policy.runId || c.threadId !== state.threadId
      || c.promptHash !== state.promptHash || c.startedAt !== state.startedAt
      || !c.turnId || c.turnId !== state.unresolvedTurn?.turnId) throw new Error('completion identity mismatch');
    if (!Number.isInteger(c.condition) || c.condition < 1 || c.condition > 5 || !text(c.reason)) throw new Error('invalid exit condition/reason');
    if (!Number.isSafeInteger(c.at) || c.at < state.startedAt || c.at > now + 5) throw new Error('invalid completion time');
    if (!/^\.vss\/sessions\/[A-Za-z0-9._-]+\.md$/.test(c.sessionFile)) throw new Error('unsafe session audit path');
    const auditPath = join(state.cwd, c.sessionFile);
    if (realpathSync(auditPath) !== auditPath) throw new Error('symlinked session audit');
    const auditBytes = readRegular(auditPath, null);
    const audit = new TextDecoder('utf-8', { fatal: true }).decode(auditBytes);
    if (hash(auditBytes) !== c.auditSha256 || !/^## Final state\s*$/m.test(audit)) throw new Error('missing or changed final audit');
    if (!Array.isArray(c.evidence) || !c.evidence.length || !c.evidence.every(text)) throw new Error('missing evidence');
    // Evidence is bound to the reviewed audit, not just a second unsupported claim.
    if (![c.reason, ...c.evidence].every(line => audit.includes(line))) throw new Error('evidence absent from audit');
    if (c.condition === 2) {
      if (c.verification !== 'passed' || !text(c.optimiser) || !audit.includes(c.optimiser)
        || !Array.isArray(c.remaining) || c.remaining.length) throw new Error('perfection requires verification, optimiser and no actionable work');
    }
    if (c.condition === 3 && (policy.budgetSeconds === null || now < state.startedAt + policy.budgetSeconds)) {
      throw new Error('no expired original explicit time cap');
    }
    if (c.condition === 4) {
      const iterations = audit.split(/^## Iter /m).slice(1).map(s => s.split(/^## (?!Iter )/m)[0]);
      const last = iterations.slice(-3);
      const numbers = last.map(s => Number(/^(\d+)\b/.exec(s)?.[1]));
      if (last.length !== 3 || numbers.some((n, i) => !Number.isSafeInteger(n) || (i && n !== numbers[i-1]+1)) || !last.every(s => /^Outcome: no-op\s*$/m.test(s) && /^Commits: none\s*$/m.test(s))) {
        throw new Error('three consecutive audited no-op iterations required');
      }
      if (!Array.isArray(c.questions) || !c.questions.every(q => text(q) && audit.includes(q))) throw new Error('invalid blocked question references');
    }
    if (c.condition === 1 && !['hardware', 'ssh', 'subjective-verdict', 'destructive-git', 'learnings', 'permissions', 'paid-dispatch', 'scope', 'verification', 'explicit-authority'].includes(c.trigger)) {
      throw new Error('unknown hard-escalate trigger');
    }
    if (c.condition === 5 && !text(c.destructiveState)) throw new Error('missing destructive-state evidence');
    return { ok: true, record: c };
  } catch (e) { return { ok: false, error: e.code === 'ENOENT' ? 'completion evidence missing' : e.message }; }
}
