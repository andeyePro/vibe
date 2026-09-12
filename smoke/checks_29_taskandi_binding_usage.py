#!/usr/bin/env python3
"""Focused offline checks for the Task&I launcher binding and usage importer.

Run with ``python3 smoke/checks_29_taskandi_binding_usage.py``.  Every fixture
is local; no Task&I transport or vendor credential is contacted or read.
"""
from __future__ import annotations

import subprocess
import tempfile
import shutil
import json
import textwrap
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
VIBE = REPO / "vibe"
CLIENT = REPO / "devcontainer" / "taskandi-client.mjs"
USAGE = REPO / "devcontainer" / "taskandi-usage.mjs"


HARNESS = r'''
import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const clientMod = await import(pathToFileURL(process.argv[2]).href);
const usageMod = await import(pathToFileURL(process.argv[3]).href);
const { CONTRACT_REVISION, createClient, loadConfig } = clientMod;
const { usageRecords, enqueueTranscriptUsage } = usageMod;
const root = mkdtempSync(join(tmpdir(), 'taskandi-29-'));
const run = (...args) => execFileSync(args[0], args.slice(1), { cwd: root, stdio: 'ignore' });
run('git', 'init', '-q'); run('git', 'config', 'user.email', 'fixture@example.invalid'); run('git', 'config', 'user.name', 'fixture');
const vibe = join(root, '.vibe'); mkdirSync(vibe, { mode: 0o700 });
const configPath = join(vibe, 'taskandi.json');
const mappingPath = join(vibe, 'taskandi-task');
const tokenPath = join(vibe, 'taskandi-token');
const config = (task = 'TE-1') => ({ endpoint: 'https://fixture.invalid/mcp', task, contractRevision: CONTRACT_REVISION });
const writeConfig = (task = 'TE-1') => writeFileSync(configPath, JSON.stringify(config(task)));
writeConfig();

// Config is rooted at the worktree, while the token remains a separate file.
mkdirSync(join(root, 'sub', 'deep'), { recursive: true });
writeFileSync(tokenPath, 'token-only'); chmodSync(tokenPath, 0o600);
writeFileSync(mappingPath, 'MAP-7\n');
assert.equal(loadConfig(join(root, 'sub', 'deep')).task, 'MAP-7');
const oldRef = process.env.VIBE_TASK_REF;
process.env.VIBE_TASK_REF = 'ENV-8';
assert.equal(loadConfig(join(root, 'sub')).task, 'ENV-8');
if (oldRef === undefined) delete process.env.VIBE_TASK_REF; else process.env.VIBE_TASK_REF = oldRef;
run('git', 'add', '.vibe/taskandi-task');
assert.throws(() => loadConfig(root), /untracked/);
run('git', 'reset', '-q', '.vibe/taskandi-task');
assert.equal(loadConfig(root).task, 'MAP-7');

// Fake transport for the binding change test. It records only local requests.
const tools = [{ name: 'list_asks', inputSchema: {
  type: 'object', properties: { task: {type:'string'}, answered: {type:'boolean'}, since: {type:'object'} },
  required: ['task', 'answered', 'since']
} }];
let listCalls = 0;
const transport = async request => {
  const message = request.body;
  let result = {};
  if (message.method === 'initialize') result = { protocolVersion: '2025-11-25' };
  else if (message.method === 'tools/list') result = { tools };
  else if (message.method === 'tools/call') {
    listCalls++;
    result = { structuredContent: { since: message.params.arguments.since,
      cursor: { sequence: 1, value: 'one' }, answers: [{ id: 'a1', content: 'old answer' }] } };
  }
  return { status: 200, headers: {'mcp-session-id':'local'}, contentType: 'application/json',
    body: JSON.stringify({ jsonrpc:'2.0', id:message.id, result }) };
};
const client = createClient({ cwd: root, transport });
await client.poll();
writeFileSync(mappingPath, 'MAP-8\n');
const before = listCalls;
await assert.rejects(() => client.poll(), /answer binding changed/);
assert.equal(listCalls, before, 'a changed binding must not request or apply old answers');
const saved = JSON.parse(readFileSync(join(vibe, 'taskandi-outbox', 'state.json')));
assert.deepEqual(saved.answers.map(item => item.content), ['old answer']);

// Transcript parser: model identity, equal snapshots, exact deltas, explicit cost.
const line = (event) => JSON.stringify(event) + '\n';
const model = line({ type:'turn_context', payload:{ model:'gpt-fixture' } });
const snap = (input, cached, write, output) => line({ type:'event_msg', payload:{ type:'token_count', info:{ total_token_usage:
  { input_tokens:input, cached_input_tokens:cached, cache_write_input_tokens:write, output_tokens:output } } } });
const records = usageRecords((model + snap(10, 2, 1, 3) + snap(10, 2, 1, 3) + snap(15, 4, 2, 8)).trim().split('\n'),
  { session:'session-1', account:'acct', costEstimate: 0.125 });
assert.equal(records.length, 2);
assert.deepEqual(records.map(r => r.payload), [
  { account:'acct', model:'gpt-fixture', input:10, output:3, cache_read:2, cache_write:1, cost_estimate:0.125 },
  { account:'acct', model:'gpt-fixture', input:5, output:5, cache_read:2, cache_write:1, cost_estimate:0.125 },
]);
assert.throws(() => usageRecords((snap(1,0,0,1)).trim().split('\n'), {session:'s',account:'a',costEstimate:1}), /no preceding model/);
assert.throws(() => usageRecords((model + snap(10,0,0,1) + snap(9,0,0,1)).trim().split('\n'), {session:'s',account:'a',costEstimate:1}), /regressing/);
assert.deepEqual(usageRecords([model.trim(), JSON.stringify({type:'event_msg', payload:{type:'token_count'}})], {session:'s',account:'a',costEstimate:1}), []);
assert.throws(() => usageRecords([model.trim(), snap(1,2,0,0).trim()], {session:'s',account:'a',costEstimate:1}), /cached input/);
assert.throws(() => usageRecords([model.trim()], {session:'s',account:'a',costEstimate:undefined}), /explicit/);

// Importer snapshots only complete JSONL records and refuses symlinks.
const transcript = join(root, 'transcript.jsonl');
writeFileSync(transcript, model + snap(4,1,0,2) + '{"unfinished":');
const enqueueCalls = [];
const fakeClient = { enqueue: async (...args) => { enqueueCalls.push(args); return { enqueued:true }; } };
const imported = await enqueueTranscriptUsage(fakeClient, transcript, {session:'s2', account:'acct', costEstimate:2});
assert.equal(imported.enqueued, 1); assert.equal(enqueueCalls.length, 1);
assert.equal(enqueueCalls[0][2].cost_estimate, 2);
const link = join(root, 'transcript-link'); symlinkSync(transcript, link);
await assert.rejects(() => enqueueTranscriptUsage(fakeClient, link, {session:'s3', account:'a', costEstimate:1}));
console.log('taskandi binding/usage checks passed');
'''


def test_launcher_parser_and_task_binding() -> None:
    script = textwrap.dedent(f"""
        set -e
        export VIBE_SOURCE_ONLY=1
        source {VIBE}
        parse_vibe_args "$@"
        printf 'TASK_REF=[%s] ENV_COUNT=[%s]\\n' "$TASK_REF_ARG" "${{#TASK_BIND_ENV[@]}}"
        if [ "${{#TASK_BIND_ENV[@]}}" -gt 0 ]; then
            /usr/bin/env "${{TASK_BIND_ENV[@]}}" python3 -c 'import os; print("CHILD_REF=[" + os.environ.get("VIBE_TASK_REF", "") + "]")'
        else
            env | grep '^VIBE_TASK_REF=' && exit 9 || true
        fi
    """)
    good = ["AB-42", "taskandeye://node/12345678-1234-1234-1234-123456789abc"]
    for ref in good:
        result = subprocess.run(["bash", "-c", script, "probe", "--task", ref], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"TASK_REF=[{ref}]" in result.stdout
        assert "ENV_COUNT=[2]" in result.stdout
        assert f"CHILD_REF=[{ref}]" in result.stdout
    for bad in ["AB-0;touch /tmp/pwn", "taskandeye://node/not-a-uuid", "--continue", "AB", "AB-1\nX"]:
        result = subprocess.run(["bash", "-c", script, "probe", "--task", bad], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        assert result.returncode != 0, f"accepted malformed/injection ref: {bad!r}"
    duplicate = subprocess.run(["bash", "-c", script, "probe", "--task", "AB-1", "--task", "CD-2"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert duplicate.returncode != 0 and "Only one --task" in duplicate.stderr
    absent = subprocess.run(["bash", "-c", script, "probe"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert absent.returncode == 0, absent.stdout + absent.stderr
    assert "TASK_REF=[]" in absent.stdout and "ENV_COUNT=[0]" in absent.stdout


def test_client_binding_and_usage() -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(HARNESS), "taskandi-29", str(CLIENT), str(USAGE)],
        cwd=REPO, capture_output=True, text=True, timeout=30,
     stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stdout + result.stderr


def test_installed_taskandi_symlink_executes_commands():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init", "-q", str(root)], check=True, stdin=subprocess.DEVNULL)
        binary = root / "bin"; binary.mkdir()
        for source in [CLIENT, USAGE]:
            shutil.copy2(source, binary / source.name)
        (binary / CLIENT.name).chmod(0o755)
        executable = binary / "taskandi-client"
        executable.symlink_to(CLIENT.name)
        response = subprocess.run([str(executable), "enqueue", "ask", "--key", "symlink-test"],
                                  input=json.dumps({"to": "fixture", "question": "q", "default": "d"}),
                                  cwd=root, text=True, capture_output=True, timeout=10)
        assert response.returncode == 0, response.stderr
        assert json.loads(response.stdout)["enqueued"] is True
        state = json.loads((root / ".vibe/taskandi-outbox/state.json").read_text())
        assert state["jobs"][0]["key"] == "symlink-test"
        invalid = subprocess.run([str(executable), "not-a-command"], cwd=root,
                                 text=True, capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
        assert invalid.returncode != 0 and "usage:" in invalid.stderr


if __name__ == "__main__":
    try:
        test_launcher_parser_and_task_binding()
        test_client_binding_and_usage()
        test_installed_taskandi_symlink_executes_commands()
    except Exception as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: Task&I binding and usage smoke checks")
