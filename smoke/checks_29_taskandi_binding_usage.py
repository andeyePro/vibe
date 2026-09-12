#!/usr/bin/env python3
"""Focused offline checks for the Task&I launcher binding and usage importer.

Run with ``python3 smoke/checks_29_taskandi_binding_usage.py``.  Every fixture
is local; no Task&I transport or vendor credential is contacted or read.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import shutil
import json
import textwrap
from pathlib import Path

# Allow both `python3 smoke/checks_29_taskandi_binding_usage.py` (this
# module's own documented standalone entry point) and package import via
# runner.py: a direct script invocation puts smoke/ on sys.path[0], not the
# repo root, so `import smoke` would otherwise fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smoke._core import check, FAILURES


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
// Item 25: a regressing cumulative count (a legitimate context-compaction
// reset) must start a fresh baseline instead of throwing and discarding
// every delta already computed - both the pre-regression and
// post-regression deltas must survive, and the regression is still
// recorded (to stderr) so it stays visible even though the import keeps
// going rather than aborting.
{
  const stderrChunks = [];
  const savedStderrWrite = process.stderr.write.bind(process.stderr);
  process.stderr.write = chunk => { stderrChunks.push(String(chunk)); return true; };
  let regressed;
  try { regressed = usageRecords((model + snap(10,0,0,1) + snap(9,0,0,1)).trim().split('\n'), {session:'s',account:'a',costEstimate:1}); }
  finally { process.stderr.write = savedStderrWrite; }
  assert.equal(regressed.length, 2);
  assert.equal(regressed[0].payload.input, 10);
  assert.equal(regressed[1].payload.input, 9);
  assert.equal(stderrChunks.some(chunk => /regressed/i.test(chunk)), true, stderrChunks.join(''));
}
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
        check(f"[taskandi] --task {ref!r} parses and exits 0", result.returncode == 0, result.stdout + result.stderr)
        check(f"[taskandi] --task {ref!r} echoes TASK_REF", f"TASK_REF=[{ref}]" in result.stdout, result.stdout)
        check(f"[taskandi] --task {ref!r} binds exactly 2 env args", "ENV_COUNT=[2]" in result.stdout, result.stdout)
        check(f"[taskandi] --task {ref!r} forwards VIBE_TASK_REF to the child", f"CHILD_REF=[{ref}]" in result.stdout, result.stdout)
    for bad in ["AB-0;touch /tmp/pwn", "taskandeye://node/not-a-uuid", "--continue", "AB", "AB-1\nX"]:
        result = subprocess.run(["bash", "-c", script, "probe", "--task", bad], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(f"[taskandi] malformed/injection ref refused: {bad!r}", result.returncode != 0, result.stdout + result.stderr)
    duplicate = subprocess.run(["bash", "-c", script, "probe", "--task", "AB-1", "--task", "CD-2"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    check("[taskandi] duplicate --task refused with a clear message",
          duplicate.returncode != 0 and "Only one --task" in duplicate.stderr, duplicate.stderr)
    # AC28: the absent-flag probe must see no ambient VIBE_TASK_REF regardless
    # of what the real environment running this test suite happens to carry
    # (e.g. a nested vibe session, or this very test run under a bound
    # task) — otherwise the probe's own `env | grep ... && exit 9` fires and
    # a bare assert on returncode used to abort the whole suite instead of
    # failing just this one check.
    sanitized_env = {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")}
    absent = subprocess.run(["bash", "-c", script, "probe"], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, env=sanitized_env)
    check("[taskandi] no --task and no ambient VIBE_TASK_REF exits 0", absent.returncode == 0, absent.stdout + absent.stderr)
    check("[taskandi] no --task leaves TASK_REF/ENV_COUNT empty",
          "TASK_REF=[]" in absent.stdout and "ENV_COUNT=[0]" in absent.stdout, absent.stdout)


def test_client_binding_and_usage() -> None:
    # An ambient VIBE_TASK_* in the parent (a nested vibe session, or this
    # very suite running under a bound task) must not change what loadConfig()
    # resolves inside the child - see AC28's sanitized_env below for the
    # same reasoning applied to the launcher probe.
    sanitized_env = {k: v for k, v in os.environ.items() if not k.startswith("VIBE_TASK_")}
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(HARNESS), "taskandi-29", str(CLIENT), str(USAGE)],
        cwd=REPO, capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL, env=sanitized_env)
    check("[taskandi] binding/usage node harness passes", result.returncode == 0, result.stdout + result.stderr)


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
        if check("[taskandi] symlinked client enqueue exits 0", response.returncode == 0, response.stderr):
            try:
                enqueued = json.loads(response.stdout).get("enqueued")
            except json.JSONDecodeError:
                enqueued = None
            check("[taskandi] symlinked client reports enqueued: true", enqueued is True, response.stdout)
            state_path = root / ".vibe" / "taskandi-outbox" / "state.json"
            try:
                state = json.loads(state_path.read_text())
            except (OSError, json.JSONDecodeError):
                state = {}
            jobs = state.get("jobs") or []
            key = jobs[0].get("key") if jobs else None
            check("[taskandi] queued job carries the symlink-test key", key == "symlink-test", str(state))
        invalid = subprocess.run([str(executable), "not-a-command"], cwd=root,
                                 text=True, capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
        check("[taskandi] unknown subcommand refuses with usage text",
              invalid.returncode != 0 and "usage:" in invalid.stderr, invalid.stderr)


# ── wave0 review-fix regression guards (items 27/28/29/30) ───────────────
#
# These are harness-robustness guards, not behavioural tests: each one fails
# against the pre-wave0 source and passes against the post-wave0 source.
# See /workspace/.vs/briefs/review-fixes-2026-09-12.md section F.

_SMOKE_DIR = Path(__file__).resolve().parent
_HARDENED_FILES = [
    "checks_27_supervisor_control.py",
    "checks_28_taskandi_client.py",
    "checks_29_taskandi_binding_usage.py",
    "checks_33_host_onboarding.py",
]


def test_wave0_no_bare_assert_in_hardened_smoke_files() -> None:
    """Items 28/29: none of the four smoke files hardened in this wave may
    contain a bare Python ``assert`` statement outside the embedded node.js
    HARNESS fixture strings (those are JS ``assert`` calls, out of scope). A
    bare assert raises AssertionError uncaught and aborts the entire smoke
    suite instead of failing one check()."""
    assert_re = re.compile(r'^\s*assert(\s|\()')
    offenders: list[str] = []
    for name in _HARDENED_FILES:
        path = _SMOKE_DIR / name
        in_js = False
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("HARNESS = r'''") or stripped.startswith("HARNESS = '''"):
                in_js = True
                continue
            if in_js:
                if stripped == "'''":
                    in_js = False
                continue
            if assert_re.match(line):
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    check("[wave0] no bare `assert` statement survives in the item-28/29 hardened smoke files",
          not offenders, "; ".join(offenders) if offenders else "none found")


def test_wave0_checks27_communicate_calls_guarded() -> None:
    """Item 30: every ``.communicate(timeout=...)`` call in
    checks_27_supervisor_control.py must route through the
    ``_communicate_or_kill`` helper (the try/except-kill pattern already
    used at smoke/checks_19_codex_supervisor.py:781), never a raw call that
    can let subprocess.TimeoutExpired escape uncaught and abort the suite."""
    target = _SMOKE_DIR / "checks_27_supervisor_control.py"
    text = target.read_text()
    tree = ast.parse(text)
    helper = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_communicate_or_kill"), None)
    if not check("[wave0] checks_27 defines the _communicate_or_kill guard helper", helper is not None, str(target)):
        return
    lo, hi = helper.lineno, helper.end_lineno
    lines = text.splitlines()
    stray = [f"{target.name}:{i}: {line.strip()}"
             for i, line in enumerate(lines, 1)
             if ".communicate(timeout=" in line and not (lo <= i <= hi)]
    check("[wave0] every communicate(timeout=) call site in checks_27 routes through the guarded helper",
          not stray, "; ".join(stray) if stray else "none found outside the helper")
    helper_src = "\n".join(lines[lo - 1:hi])
    check("[wave0] the guarded helper wraps communicate(timeout=) in try/except with kill()",
          "try:" in helper_src and "except subprocess.TimeoutExpired" in helper_src and ".kill()" in helper_src,
          helper_src)


def test_wave0_item28_absent_probe_survives_ambient_task_ref() -> None:
    """Item 28: re-run the launcher parser/binding test with VIBE_TASK_REF
    set in the parent environment (simulating a nested vibe session, or this
    very suite running under a bound task) and confirm it still reports
    success through check() rather than inheriting the ambient var and
    tripping the probe's `exit 9` behind a bare assert."""
    old = os.environ.get("VIBE_TASK_REF")
    os.environ["VIBE_TASK_REF"] = "AMBIENT-999"
    try:
        before = len(FAILURES)
        test_launcher_parser_and_task_binding()
        new_failures = FAILURES[before:]
    finally:
        if old is None:
            os.environ.pop("VIBE_TASK_REF", None)
        else:
            os.environ["VIBE_TASK_REF"] = old
    check("[wave0] launcher parser/binding checks still pass with VIBE_TASK_REF set in the parent",
          not new_failures, "; ".join(f"{n}: {d}" for n, d in new_failures) if new_failures else "none")


def test_wave0_supervisor_state_reads_no_bare_double_subscript() -> None:
    """Item 27 (check()-half): none of the supervisor state-reading smoke
    files may chain a bare double subscript
    ``["unresolvedTurn"]["turnId"]`` off freshly-parsed supervisor state -
    that raised KeyError (missing key) or TypeError (unresolvedTurn is
    None) and aborted the suite whenever the supervisor did not write what
    the test expected. The converted sites read through a pre-defaulted
    ``.get("unresolvedTurn") or {}`` first."""
    targets = [
        "checks_19_codex_supervisor.py",
        "checks_21_codex_supervisor_c2.py",
        "checks_27_supervisor_control.py",
        "checks_30_supervisor_reconciliation.py",
    ]
    needle = '["unresolvedTurn"]["turnId"]'
    offenders = []
    for name in targets:
        path = _SMOKE_DIR / name
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if needle in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    check("[wave0] no bare chained subscript into parsed supervisor state remains",
          not offenders, "; ".join(offenders) if offenders else "none found")


if __name__ == "__main__":
    test_launcher_parser_and_task_binding()
    test_client_binding_and_usage()
    test_installed_taskandi_symlink_executes_commands()
    test_wave0_no_bare_assert_in_hardened_smoke_files()
    test_wave0_checks27_communicate_calls_guarded()
    test_wave0_item28_absent_probe_survives_ambient_task_ref()
    test_wave0_supervisor_state_reads_no_bare_double_subscript()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        raise SystemExit(1)
    print("PASS: Task&I binding and usage smoke checks")
