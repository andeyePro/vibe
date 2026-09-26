#!/usr/bin/env node
// Codex alone. Supervised turns are allowed to finish: the supervisor,
// rather than a model-side loop of Stop refusals, owns continuation.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readRegular, ownershipFresh } from './supervisor-control.mjs';
const block = reason => process.stdout.write(JSON.stringify({ decision: 'block', reason }) + '\n');
try {
  const payload = JSON.parse(readFileSync(0, 'utf8'));
  if (payload.hook_event_name && payload.hook_event_name !== 'Stop') process.exit(0);
  const root = payload.cwd || '/workspace';
  const path = join(root, '.vss/codex-supervisor.json');
  const sid = payload.session_id;
  if (typeof sid !== 'string' || !sid) process.exit(0);
  const supervised = candidate => {
    try {
      const state = JSON.parse(readRegular(candidate));
      return state.threadId === sid && state.cwd === root && ownershipFresh(candidate);
    } catch { return false; }
  };
  if (supervised(path)) process.exit(0);
  const marker = Object.fromEntries(readRegular(join(root, '.vss/auto-resume')).trim().split('\n').map(l => {
    const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)];
  }));
  if (marker.active !== '1' || marker.owner !== sid) process.exit(0);
  if (marker.supervisor_state && supervised(marker.supervisor_state)) process.exit(0);
  // No refusal count or Final-state escape. Explicit user stop deactivates
  // the owned marker; ordinary questions are parked while work continues.
  block('This Codex vsss session is active but not supervised. Follow /usr/local/share/vibe/codex-vsss.md: checkpoint and hand off with codex-autonomy start, then yield the workspace. Do not treat a Final state heading or a fourth stop attempt as completion. If the user explicitly asked to stop, set this owned marker active=0 and stop.');
} catch (error) {
  // Missing marker/unrelated ordinary conversations must never be trapped.
  if (error.code !== 'ENOENT') process.stderr.write('codex-stop-guard: ownership could not be read; inspect run status\n');
}
