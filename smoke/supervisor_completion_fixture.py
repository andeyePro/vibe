"""Stub-agent evidence writer for protocol tests; negative tests disable it.

This fixture is not the implementation validator. It writes a minimal audited
condition-2 claim so transport/retry tests can exercise legitimate termination.
"""
import hashlib
import json
import time
from pathlib import Path


def write_completion(event, cwd, fixture):
    if not cwd or fixture.get('autoCompletion', True) is False:
        return
    item = event.get('params', {}).get('item', {})
    message = item.get('text', '')
    if item.get('type') != 'agentMessage' or not message.rstrip().split('\n')[-1].startswith('VSSS-EXIT: '):
        return
    state_path = Path(fixture.get('statePath', str(Path(cwd) / '.vss/codex-supervisor.json')))
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    turn_id = event.get('params', {}).get('turnId')
    until = time.monotonic() + 2
    while turn_id and (state.get('unresolvedTurn') or {}).get('turnId') != turn_id and time.monotonic() < until:
        time.sleep(0.01)
        state = json.loads(state_path.read_text())
    policy = state.get('completion')
    if not policy:
        return
    reason = message.rstrip().split('\n')[-1].split(': ', 1)[1]
    audit = '# Fixture audit\n\n## Iter 1\nTests passed.\n\n## Final state\n' + reason + '\nAll fixture work verified.\nQueue examined and empty.\n'
    rel = '.vss/sessions/fixture.md'
    path = Path(cwd) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(audit)
    record = dict(version=1, turnId=turn_id, runId=policy['runId'], threadId=state['threadId'], promptHash=state['promptHash'],
                  startedAt=state['startedAt'], at=state['startedAt'], sessionFile=rel,
                  auditSha256=hashlib.sha256(audit.encode()).hexdigest(), condition=2, reason=reason,
                  evidence=['All fixture work verified.'], verification='passed', optimiser='Queue examined and empty.', remaining=[])
    Path(str(state_path) + '.completion.json').write_text(json.dumps(record))
