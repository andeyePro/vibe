#!/usr/bin/env python3
"""Offline behavioural smoke checks for the provisional Task&I fixture contract.

This is deliberately a fixture-only test: it imports the local client and
injects a fake MCP transport.  It makes no Task&I network or authentication
request and does not assert live-server compatibility.  The fixture contract
tag is ``vibe-action-window-fixture-v1``; the MCP protocol revision remains
``2025-11-25``.

Run only this module with:
    python3 smoke/checks_28_taskandi_client.py
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CLIENT = REPO / "devcontainer" / "taskandi-client.mjs"


HARNESS = r'''
import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

// argv[1] is a harmless runner label: importing the CLI must not invoke main.
const mod = await import(pathToFileURL(process.argv[2]).href);
const { CONTRACT_REVISION, LIMITS, createClient, fetchTransport, loadConfig, validatePayload } = mod;
const root = mkdtempSync(join(tmpdir(), 'taskandi-fixture-'));
const run = (...args) => execFileSync(args[0], args.slice(1), { cwd: root, stdio: 'ignore' });
run('git', 'init', '-q'); run('git', 'config', 'user.email', 'fixture@example.invalid'); run('git', 'config', 'user.name', 'fixture');
const vibe = join(root, '.vibe'); mkdirSync(vibe, { mode: 0o700 });
const configPath = join(vibe, 'taskandi.json'); const tokenPath = join(vibe, 'taskandi-token');
const cfg = (task = 'task-1', endpoint = 'https://fixture.invalid/mcp') => ({ endpoint, task, contractRevision: CONTRACT_REVISION });
const writeConfig = (value = cfg()) => writeFileSync(configPath, JSON.stringify(value));
const writeToken = () => { writeFileSync(tokenPath, 'fixture-token'); chmodSync(tokenPath, 0o600); };
const rejected = async (fn, needle) => { await assert.rejects(fn, error => String(error.message).includes(needle)); };
const throws = (fn, needle) => assert.throws(fn, error => String(error.message).includes(needle));
const state = () => JSON.parse(readFileSync(join(vibe, 'taskandi-outbox', 'state.json')));

// AC1: unbound remains a file channel and cannot initiate fixture transport.
let calls = 0;
const unbound = createClient({ cwd: root, transport: async () => { calls++; throw Error('network'); } });
assert.deepEqual(await unbound.flush(), { bound: false, channel: 'file-fallback', dispatched: 0 });
assert.equal(calls, 0);
assert.equal((await unbound.enqueue('ask', 'unbound-1', { to: 'owner', question: 'q', default: 'd' })).bound, false);

// Config is deliberately hostile: unknown/tracked/symlink/invalid values refuse.
writeConfig({ ...cfg(), extra: true }); throws(() => loadConfig(root), 'unknown key');
writeConfig(cfg()); run('git', 'add', '.vibe/taskandi.json'); throws(() => loadConfig(root), 'tracked'); run('git', 'rm', '--cached', '-q', '.vibe/taskandi.json');
writeConfig(cfg('task-1', 'https://user:pass@fixture.invalid/mcp')); throws(() => loadConfig(root), 'userinfo');
writeConfig(cfg('task-1', 'http://fixture.invalid/mcp')); throws(() => loadConfig(root), 'HTTPS');
writeConfig(cfg('task-1', 'https://fixture.invalid/mcp?secret=x')); throws(() => loadConfig(root), 'query');
writeConfig(cfg());
const realConfig = join(root, 'real-config'); writeFileSync(realConfig, JSON.stringify(cfg()));
run('rm', configPath); symlinkSync(realConfig, configPath); throws(() => loadConfig(root), 'non-symlink'); run('rm', configPath); writeConfig(cfg());
writeToken(); chmodSync(tokenPath, 0o644); await rejected(() => createClient({ cwd: root }).flush(), 'permissions'); chmodSync(tokenPath, 0o600);

// Fixture-only MCP handshake.  Schemas intentionally describe only the narrow allowed fields.
const schema = (properties, required) => ({ type: 'object', properties: Object.fromEntries(properties.map(([k, type]) => [k, type === 'array' ? { type, items: { type: 'string' } } : { type }])), required });
const tools = [
  { name: 'ask', inputSchema: schema([['task','string'],['to','string'],['question','string'],['default','string'],['options','array']], ['task','to','question','default']) },
  { name: 'record_usage', inputSchema: schema([['account','string'],['model','string'],['input','integer'],['output','integer'],['cache_read','integer'],['cache_write','integer'],['cost_estimate','number'],['source','string'],['source_ref','string']], ['account','model','input','output','cache_read','cache_write','cost_estimate','source','source_ref']) },
  { name: 'list_asks', inputSchema: schema([['task','string'],['answered','boolean'],['since','object']], ['task','answered','since']) },
];
let requests = []; let failCall = false; let pollPage = null;
const transport = async request => {
  requests.push(request); assert.equal(new URL(request.url).origin, 'https://fixture.invalid');
  assert.equal(request.headers.authorization, 'Bearer fixture-token');
  const message = request.body;
  let result = {};
  if (message.method === 'initialize') result = { protocolVersion: '2025-11-25' };
  else if (message.method === 'tools/list') result = { tools };
  else if (message.method === 'tools/call' && message.params.name === 'list_asks') result = pollPage;
  else if (message.method === 'tools/call' && failCall) return { status: 200, headers: {}, contentType: 'application/json', body: JSON.stringify({ jsonrpc: '2.0', id: message.id, error: { code: -1 } }) };
  else if (message.method === 'tools/call') result = { structuredContent: {} };
  return { status: 200, headers: { 'mcp-session-id': 'fixture-session' }, contentType: 'application/json', body: JSON.stringify({ jsonrpc: '2.0', id: message.id, result }) };
};
const client = createClient({ cwd: root, transport });

// AC2: bounded payload, stable dedup/conflict and narrow source-ref injection.
throws(() => validatePayload('record_usage', { account:'a', model:'m', input:-1, output:0, cache_read:0, cache_write:0, cost_estimate:0 }, cfg(), 'k'), 'nonnegative');
throws(() => validatePayload('ask', { to:'x', question:'q'.repeat(LIMITS.text + 1), default:'d' }, cfg(), 'k'), 'at most');
await client.enqueue('ask', 'ask-1', { to: 'owner', question: 'question', default: 'default', options: ['yes'] });
assert.equal((await client.enqueue('ask', 'ask-1', { to: 'owner', question: 'question', default: 'default', options: ['yes'] })).deduplicated, true);
await rejected(() => client.enqueue('ask', 'ask-1', { to: 'owner', question: 'changed', default: 'default' }), 'different payload');
await client.enqueue('record_usage', 'usage-1', { account:'acct', model:'model', input:1, output:2, cache_read:3, cache_write:4, cost_estimate:0 });
assert.equal((await client.flush()).done, 2);
assert.equal(requests.some(r => r.body.method === 'notifications/initialized'), true);
assert.equal(requests.filter(r => r.body.method === 'tools/call').every(r => ['ask','record_usage'].includes(r.body.params.name)), true);
assert.equal(state().jobs.find(j => j.key === 'usage-1').payload.source, 'vibe');

// A changed binding never sends the queued record; a sent RPC error is uncertain, never auto-retried.
await client.enqueue('ask', 'binding-1', { to:'o', question:'q', default:'d' }); writeConfig(cfg('task-2'));
await rejected(() => client.flush(), 'binding changed'); assert.equal(state().jobs.find(j => j.key === 'binding-1').state, 'queued');
writeConfig(cfg());
await client.enqueue('ask', 'uncertain-1', { to:'o', question:'q', default:'d' }); failCall = true;
assert.equal((await client.flush()).uncertain, 1); assert.equal(state().jobs.find(j => j.key === 'binding-1').state, 'uncertain');
const before = requests.length; failCall = false; await client.flush(); assert.equal(requests.length > before, true); assert.equal(state().jobs.find(j => j.key === 'binding-1').state, 'uncertain');
await client.reconcile('binding-1', 'retry', 'fixture operator evidence'); assert.equal(state().jobs.find(j => j.key === 'binding-1').state, 'queued');
// Schema drift is pre-dispatch: discovery may occur, but the queued job is not sent.
tools[0].inputSchema.properties.unapproved = { type: 'string' };
const callCount = requests.filter(r => r.body.method === 'tools/call').length;
await rejected(() => client.flush(), 'outside the narrow contract');
assert.equal(state().jobs.find(j => j.key === 'binding-1').state, 'queued');
assert.equal(requests.filter(r => r.body.method === 'tools/call').length, callCount);
delete tools[0].inputSchema.properties.unapproved;

// Crash recovery and existing/ambiguous locks fail closed.
const crashedState = state(); crashedState.jobs.push({ key:'crashed', kind:'ask', digest:'x', payload:{}, binding:null, channel:'taskandi-mcp', state:'dispatching' });
writeFileSync(join(vibe, 'taskandi-outbox', 'state.json'), JSON.stringify(crashedState));
await client.status(); assert.equal(state().jobs.find(j => j.key === 'crashed').state, 'uncertain');
writeFileSync(join(vibe, 'taskandi-outbox', '.lock'), 'unknown-owner'); chmodSync(join(vibe, 'taskandi-outbox', '.lock'), 0o600);
await rejected(() => client.status(), 'ownership is live or ambiguous'); run('rm', join(vibe, 'taskandi-outbox', '.lock'));
const renderedStatus = JSON.stringify(await client.status()); assert.equal(renderedStatus.includes('fixture-token'), false); assert.equal(renderedStatus.includes('question'), false);

// AC4 fixture page: duplicate equal content applies once; changed content becomes conflict; malformed cursor does not advance.
pollPage = { structuredContent: { since:{sequence:0,value:''}, cursor:{sequence:1,value:'a'}, answers:[{id:'a1',content:'one'},{id:'a1',content:'one'}] } };
assert.equal((await client.poll()).newAnswers, 1);
pollPage = { structuredContent: { since:{sequence:1,value:'a'}, cursor:{sequence:1,value:'a'}, answers:[{id:'a1',content:'one'}] } };
assert.equal((await client.poll()).newAnswers, 0);
pollPage = { structuredContent: { since:{sequence:1,value:'a'}, cursor:{sequence:2,value:'b'}, answers:[{id:'a1',content:'changed'}] } };
assert.deepEqual((await client.poll()).conflicts, ['a1']);
const cursorBefore = state().cursor;
pollPage = { structuredContent: { since:{sequence:2,value:'b'}, cursor:{sequence:1,value:'x'}, answers:[] } };
await rejected(() => client.poll(), 'regressed'); assert.deepEqual(state().cursor, cursorBefore);

// Transport itself refuses redirects and target-origin changes; no credential is injected here.
const savedFetch = globalThis.fetch;
globalThis.fetch = async (_url, init) => ({ status:302, headers:new Headers(), body:null });
await rejected(() => fetchTransport({ url:'https://fixture.invalid/mcp', origin:'https://fixture.invalid', headers:{}, body:{} }), 'redirects');
await rejected(() => fetchTransport({ url:'https://other.invalid/mcp', origin:'https://fixture.invalid', headers:{}, body:{} }), 'left the configured origin');
globalThis.fetch = savedFetch;
console.log('fixture contract checks passed');
'''


def test_taskandi_fixture_contract() -> None:
    """AC1–AC5 against a fake, exact-origin transport only (never live Task&I)."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(HARNESS), "fixture-runner", str(CLIENT)],
        cwd=REPO,
        input="",
        text=True,
        capture_output=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    try:
        test_taskandi_fixture_contract()
    except Exception as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: Task&I fixture contract smoke checks")
