"""Codex-only continuation: behavioural negative controls and owned recovery."""
from smoke._core import *
from smoke import checks_19_codex_supervisor as s
from smoke import checks_35_vsss_stop_guard as g
import hashlib
import signal
import time

MODULE = REPO / 'devcontainer/codex-completion.mjs'
RUNNER = REPO / 'devcontainer/codex-autonomy.mjs'
GUARD = REPO / 'devcontainer/codex-stop-guard.mjs'


def _run_case(tmp, turns, *, proof=True, prompt='$vsss go', extra=(), snapshot=None, watch=False):
    _, _, ws, env = s._supervisor_fixture(tmp)
    fixture = {'turns': [{'events': events} for events in turns], 'autoCompletion': proof}
    if snapshot is not None:
        fixture['threadRead'] = snapshot
    stub = s._write_stub(tmp / 'stub', fixture)
    brief = tmp / 'prompt.txt'; brief.write_text(prompt)
    clock = tmp / 'clock'; clock.write_text('1800000000')
    args = ['run', '--cwd', str(ws), '--prompt-file', str(brief), '--codex-bin', str(stub), '--now-source', str(clock), *extra]
    if watch:
        r = run(['node', str(RUNNER), 'watch', '--', *args], env=env)
    else:
        r = s._run_supervisor(args, env)
    return r, ws, s._in_messages(tmp / 'stub')


def test_codex_evidence_required_for_every_exit():
    for reason in ['natural milestone reached', 'perfection gate: waiting for Martin', 'user budget cap reached']:
        with tempfile.TemporaryDirectory() as td:
            r, ws, messages = _run_case(Path(td), [s._DONE_TURN_EVENTS('end', reason)] * 2, proof=False, extra=['--max-turns', '2'])
            state = s._read_state(ws)
            starts = [m for m in messages if m.get('method') == 'turn/start']
            check('[continuation] unsupported claim never succeeds: ' + reason,
                  r.returncode == 3 and 'exitReason' not in state and len(starts) == 2, r.stderr)
            check('[continuation] next turn explains missing evidence',
                  'completion was not accepted' in starts[1]['params']['input'][0]['text'], str(starts))
    with tempfile.TemporaryDirectory() as td:
        r, ws, _ = _run_case(Path(td), [s._DONE_TURN_EVENTS('end', 'perfection gate: verified')])
        check('[continuation] audited matching completion succeeds', r.returncode == 0 and s._read_state(ws).get('completionAccepted', {}).get('condition') == 2, r.stderr)


def _validation(tmp, mutation=None, *, condition=2, budget=None, elapsed=10, audit_extra=''):
    root = tmp / 'ws'; (root / '.vss/sessions').mkdir(parents=True)
    state_path = root / '.vss/codex-supervisor.json'
    state = dict(cwd=str(root), threadId='thread', promptHash='hash', startedAt=1000, unresolvedTurn={'turnId': 'turn'},
                 completion=dict(version=1, runId='run', budgetSeconds=budget))
    audit = '# Audit\n' + audit_extra + '\n## Final state\nReason\nTests passed.\nQueue verified empty.\nQuestion 1: approve SSH.\n'
    (root / '.vss/sessions/test.md').write_text(audit)
    c = dict(version=1, runId='run', threadId='thread', turnId='turn', promptHash='hash', startedAt=1000, at=1001,
             condition=condition, reason='Reason', sessionFile='.vss/sessions/test.md', auditSha256=hashlib.sha256(audit.encode()).hexdigest(),
             evidence=['Tests passed.'], verification='passed', optimiser='Queue verified empty.', remaining=[], questions=['Question 1: approve SSH.'],
             trigger='ssh', destructiveState='unrecoverable conflict')
    if mutation: mutation(c, state, root)
    Path(str(state_path) + '.completion.json').write_text(json.dumps(c))
    script = f"import {{validateCompletion}} from {json.dumps(str(MODULE))}; console.log(JSON.stringify(validateCompletion({json.dumps(str(state_path))}, {json.dumps(state)}, {1000+elapsed})));"
    r = run(['node', '--input-type=module', '-e', script])
    return json.loads(r.stdout)


def test_codex_completion_identity_and_condition_validation():
    for key, value in [('runId','other'), ('threadId','other'), ('turnId','old'), ('promptHash','other'), ('startedAt',999), ('condition',6), ('at',999), ('auditSha256','changed'), ('sessionFile','../escape'), ('evidence',[]), ('verification','failed'), ('remaining',['unfinished']), ('optimiser','unsupported')]:
        with tempfile.TemporaryDirectory() as td:
            result = _validation(Path(td), lambda c, s0, r: c.update({key:value}))
            check('[continuation] reject mismatched/unsupported ' + key, not result['ok'], str(result))
    with tempfile.TemporaryDirectory() as td:
        def invalid_utf8(c, state, root):
            path = root / c['sessionFile']
            raw = b'\xff' + path.read_bytes()
            path.write_bytes(raw)
            c['auditSha256'] = hashlib.sha256(raw.decode('utf8', errors='replace').encode()).hexdigest()
        check('[continuation] invalid UTF-8 cannot reuse a decoded-text hash', not _validation(Path(td), invalid_utf8)['ok'])
    for condition in (1, 2, 5):
        with tempfile.TemporaryDirectory() as td:
            check(f'[continuation] valid condition {condition}', _validation(Path(td), condition=condition)['ok'])
    for budget, elapsed, expected in [(None,100,False),(60,59,False),(60,60,True)]:
        with tempfile.TemporaryDirectory() as td:
            check('[continuation] cap needs original authority and elapsed time', _validation(Path(td),condition=3,budget=budget,elapsed=elapsed)['ok'] == expected)
    for count in (2,3):
        with tempfile.TemporaryDirectory() as td:
            audit = ''.join(f'## Iter {i}\nOutcome: no-op\nCommits: none\n' for i in range(count))
            check('[continuation] no-op count is evidenced', _validation(Path(td),condition=4,audit_extra=audit)['ok'] == (count == 3))
    with tempfile.TemporaryDirectory() as td:
        def symlink(c, state, root):
            p = root / c['sessionFile']; original=p.read_text(); p.unlink()
            target = root / 'outside.md'; target.write_text(original); p.symlink_to(target)
        check('[continuation] symlink audit rejected', not _validation(Path(td),symlink)['ok'])


def test_codex_transients_reset_but_telemetry_accumulates():
    failed = [s._turn_started_event(), s._turn_completed_event('failed', {'codexErrorInfo':'serverOverloaded', 'message':'overload'})]
    ok = [s._turn_started_event(), s._agent_message_event('ok','working'), s._turn_completed_event('completed')]
    with tempfile.TemporaryDirectory() as td:
        r, ws, _ = _run_case(Path(td), [failed,ok]*8 + [s._DONE_TURN_EVENTS('end','verified')])
        state = s._read_state(ws)
        check('[continuation] eight separated transients survive default six limit', r.returncode == 0 and state['transientRetries'] == 8 and state['consecutiveTransientRetries'] == 0, r.stderr)
        waits = [w['seconds'] for w in state['waits'] if w.get('reason') == 'transient']
        check('[continuation] successful turns reset backoff', waits == [60]*8, str(waits))
    with tempfile.TemporaryDirectory() as td:
        r, ws, _ = _run_case(Path(td), [failed]*6)
        check('[continuation] six consecutive transients still stop', r.returncode == 3 and s._read_state(ws)['consecutiveTransientRetries'] == 6, r.stderr)


def test_codex_stop_guard_is_separate_and_has_no_fourth_escape():
    with tempfile.TemporaryDirectory() as td:
        root = g._guard_fixture(Path(td), final=True)
        payload = {**g._payload(), 'cwd':str(root)}
        results = [run(['node',str(GUARD)],input=json.dumps(payload)) for _ in range(5)]
        check('[continuation] five Codex stop attempts with Final heading stay blocked', all(g._blocked(r) for r in results), str(results))
        check('[continuation] Claude Final-heading allowance unchanged', g._allowed(g._run_guard(root,g._payload())))
        payload['session_id']='someone-else'
        check('[continuation] unrelated Codex conversation never trapped', g._allowed(run(['node',str(GUARD)],input=json.dumps(payload))))
        state_path = root/'.vss/codex-supervisor.json'
        state_path.write_text(json.dumps({'threadId':g.SID,'cwd':str(root)}))
        Path(str(state_path)+'.lock').write_text(json.dumps({'version':1,'token':'11111111-1111-1111-1111-111111111111'}))
        check('[continuation] supervised turn hands completion to supervisor', g._allowed(run(['node',str(GUARD)],input=json.dumps({**payload,'session_id':g.SID}))))


def test_codex_outer_runner_and_foreign_lock():
    with tempfile.TemporaryDirectory() as td:
        r, ws, messages = _run_case(Path(td), [s._DONE_TURN_EVENTS('end','verified')], watch=True)
        check('[continuation] outer runner drives one audited thread', r.returncode == 0 and len([m for m in messages if m.get('method') == 'thread/start']) == 1, r.stderr)
        check('[continuation] owned locks released after child-tree shutdown', not list((ws/'.vss').glob('*.lock')))
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
        state=ws/'.vss/codex-supervisor.json'; state.parent.mkdir()
        lock=Path(str(state)+'.lock'); lock.write_text('foreign owner')
        brief=tmp/'prompt'; brief.write_text('$vsss go')
        r=run(['node',str(RUNNER),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief)],env=env)
        check('[continuation] foreign lock never stolen', r.returncode != 0 and lock.read_text() == 'foreign owner',r.stderr)


def test_codex_known_completed_turn_recovery_never_replays():
    for outcome in ('completed','inProgress','failed'):
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
            brief=tmp/'prompt'; brief.write_text('$vsss go')
            state_path=ws/'.vss/codex-supervisor.json'; state_path.parent.mkdir()
            state=dict(threadId='11111111-1111-1111-1111-111111111111',cwd=str(ws),promptHash=hashlib.sha256(brief.read_bytes()).hexdigest(),
                       startedAt=1800000000,turns=[],turnsStarted=1,resumes=0,quotaWaits=0,transientRetries=0,turnFailures=0,waits=[],turnSafetyVersion=1,
                       unresolvedTurn={'threadId':'11111111-1111-1111-1111-111111111111','turnId':'old-turn'},
                       completion={'version':1,'runId':'11111111-1111-1111-1111-111111111111','budgetSeconds':None})
            state_path.write_text(json.dumps(state))
            item={'type':'agentMessage','text':'VSSS-EXIT: recovered verified'}
            # An independent fixture writer produces the exact old-turn evidence.
            from smoke.supervisor_completion_fixture import write_completion
            write_completion({'params':{'item':item,'turnId':'old-turn'}},str(ws),{})
            stub=s._write_stub(tmp/'stub',{'threadRead':{'thread':{'id':state['threadId'],'turns':[{'id':'old-turn','status':outcome,'items':[item]}]}},'turns':[]})
            clock=tmp/'clock'; clock.write_text('1800000010')
            r=s._run_supervisor(['run','--cwd',str(ws),'--prompt-file',str(brief),'--codex-bin',str(stub),'--now-source',str(clock),'--recover-completed'],env)
            methods=[m.get('method') for m in s._in_messages(tmp/'stub')]
            check('[continuation] recovery reads without any turn replay: '+outcome,'thread/read' in methods and 'turn/start' not in methods,str(methods))
            check('[continuation] only completed outcome accepted: '+outcome,(r.returncode==0)==(outcome=='completed'),r.stderr)
            if outcome!='completed': check('[continuation] unresolved effects remain checkpointed',s._read_state(ws).get('unresolvedTurn') is not None)



def test_codex_new_run_never_discards_unresolved_effects():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
        state=ws/'.vss/codex-supervisor.json'; state.parent.mkdir()
        state.write_text(json.dumps({'unresolvedTurn':{'turnId':'pending'}}))
        original=state.read_bytes()
        brief=tmp/'prompt'; brief.write_text('$vsss next task')
        r=run(['node',str(RUNNER),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief),'--new-run'],env=env)
        check('[continuation] new-run plus recovery refuses unresolved checkpoint',r.returncode!=0 and state.read_bytes()==original and not list(state.parent.glob('*.archive.json')),r.stderr)


def test_codex_outer_runner_recovers_owned_supervisor_crash():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
        brief=tmp/'prompt'; brief.write_text('$vsss original only once')
        fixture={'turns':[{'events':s._DONE_TURN_EVENTS('end','perfection gate: recovered')}]}
        stub=s._write_stub(tmp/'stub',fixture)
        source=stub.read_text().replace('                send(event)\n', '''                if event.get("method") == "item/completed" and not (HERE / "crashed").exists():
                    (HERE / "crashed").write_text("yes")
                    fixture["threadRead"] = {"thread": {"id":thread_id,"turns":[{"id":tid,"status":"completed","items":[event["params"]["item"]]}]}}
                    fixture["turns"] = []
                    (HERE / "fixture.json").write_text(json.dumps(fixture))
                    # Supervisor is parent of the app-server's directly owned reaper.
                    reaper = os.getppid()
                    parent = int(Path(f"/proc/{reaper}/stat").read_text().split(") ",1)[1].split()[1])
                    os.kill(parent, 9)
                    time.sleep(30)
                send(event)
''')
        stub.write_text(source)
        clock=tmp/'clock'; clock.write_text('1800000000')
        r=run(['node',str(RUNNER),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief),'--codex-bin',str(stub),'--now-source',str(clock)],env=env)
        messages=s._in_messages(tmp/'stub'); methods=[m.get('method') for m in messages]
        check('[continuation] killed supervisor recovers to audited completion',r.returncode==0 and s._read_state(ws).get('exitReason')=='perfection gate: recovered',r.stderr)
        check('[continuation] crash recovery reads old turn and never replays input',methods.count('turn/start')==1 and methods.count('thread/start')==1 and 'thread/read' in methods,str(methods))
        check('[continuation] crash tree and own abandoned locks cleaned',not list((ws/'.vss').glob('*.lock')))


def _installed_runner_fixture(tmp, events):
    _,_,ws,env=s._supervisor_fixture(tmp)
    bins=tmp/'bin'; bins.mkdir()
    for installed, source in [('codex-autonomy','codex-autonomy.mjs'),('codex-supervisor','codex-supervisor.mjs'),
                              *[(n,n) for n in ['codex-errors.mjs','codex-rpc.mjs','codex-completion.mjs','supervisor-control.mjs','taskandi-client.mjs']]]:
        path=bins/installed; path.write_text((REPO/'devcontainer'/source).read_text()); path.chmod(0o755)
    stub=s._write_stub(tmp/'stub',{'turns':[{'events':events}]})
    # The gate itself is exercised independently by checks_25; this fixture
    # emulates the post-gate entry with an installed extensionless layout.
    entry=bins/'codex-entry'
    entry.write_text(f'#!{sys.executable}\nimport os,sys\nos.execvp("node", ["node", {str(bins/"codex-autonomy")!r}, "watch", "--", *sys.argv[3:], "--codex-bin", {str(stub)!r}])\n')
    entry.chmod(0o755)
    return bins,ws,env


def test_codex_detached_handoff_context_conflict_and_stop():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        bins,ws,env=_installed_runner_fixture(tmp,[s._turn_started_event(),{'sleep':3},s._agent_message_event('end','VSSS-EXIT: verified'),s._turn_completed_event('completed')])
        helper=bins/'codex-autonomy'; brief=tmp/'brief'; brief.write_text('$vsss private task ; $(no-shell)')
        r=run(['node',str(helper),'start','--cwd',str(ws),'--prompt-file',str(brief)],env=env)
        check('[continuation] detached installed-layout handoff acknowledged',r.returncode==0 and 'acknowledged' in r.stdout,r.stderr)
        state_path=ws/'.vss/codex-supervisor.json'
        until=time.monotonic()+5
        while time.monotonic()<until and (not state_path.exists() or not s._read_state(ws).get('threadId')): time.sleep(.05)
        state=s._read_state(ws)
        context=run(['node',str(helper),'context','--cwd',str(ws)],env={**env,'CODEX_THREAD_ID':state['threadId']})
        check('[continuation] owned worker detects itself without nesting',json.loads(context.stdout)['supervised'] is True,context.stderr)
        again=run(['node',str(helper),'start','--cwd',str(ws),'--prompt-file',str(brief)],env=env)
        check('[continuation] second handoff refused, saved prompt unchanged',again.returncode!=0 and Path(str(state_path)+'.prompt.txt').read_text()==brief.read_text(),again.stderr)
        ignored=run(['git','-C',str(ws),'check-ignore',str(state_path)+'.prompt.txt'],env=env)
        check('[continuation] saved private prompt is ignored even in a fresh repo',ignored.returncode==0,ignored.stderr)
        status=run(['node',str(helper),'status','--cwd',str(ws)],env=env)
        check('[continuation] status works after initiating process ended and redacts prompt',json.loads(status.stdout)['running'] is True and 'private task' not in status.stdout,status.stdout)
        stop=run(['node',str(helper),'stop','--cwd',str(ws)],env=env)
        check('[continuation] detached runner accepts stop',stop.returncode==0,stop.stderr)
        until=time.monotonic()+15
        while time.monotonic()<until and Path(str(state_path)+'.runner.lock').exists(): time.sleep(.1)
        check('[continuation] stop releases owned runner without restart',not Path(str(state_path)+'.runner.lock').exists() and len([m for m in s._in_messages(tmp/'stub') if m.get('method')=='thread/start'])==1)


def test_codex_runner_bounds_failures_without_completed_progress():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); bins,ws,env=_installed_runner_fixture(tmp,[])
        child=bins/'codex-supervisor'; source=child.read_text()
        start=source.index('if (invokedDirectly()) {')
        source=source[:start]+'''if (invokedDirectly()) {
  const options = parseArgs(process.argv.slice(2));
  let state; try { state = JSON.parse(readRegular(options.state)); } catch { state = { threadId:'fixture', turns:[] }; }
  state.turns.push({ status:'failed' });
  atomicWrite(options.state, JSON.stringify(state));
  process.exit(1);
}
'''
        child.write_text(source)
        brief=tmp/'brief'; brief.write_text('$vsss task')
        r=run(['node',str(bins/'codex-autonomy'),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief)],env=env)
        state=s._read_state(ws)
        check('[continuation] failed-turn telemetry cannot reset process failure cap',r.returncode==1 and len(state['turns'])==3,r.stderr+str(state))


def test_codex_original_budget_policy_and_retry_deadline():
    prompts=['$vsss task mentions --hours 1', '$vsss --budget 30m task', '$vsss --wide 4 --budget 2h --hours 0.5 task', '$vsss --hours 0 task']
    script=f"import {{completionPolicy}} from {json.dumps(str(MODULE))}; console.log(JSON.stringify({json.dumps(prompts)}.map(p => {{try {{return completionPolicy(p);}} catch {{return 'invalid';}}}})));"
    r=run(['node','--input-type=module','-e',script]); policies=json.loads(r.stdout)
    check('[continuation] original cap grammar ignores task prose, honours units/precedence and rejects zero',
          [p.get('budgetSeconds') if isinstance(p,dict) else p for p in policies]==[None,1800,1800,'invalid'],r.stdout)
    failed=[s._turn_started_event(),s._turn_completed_event('failed',{'codexErrorInfo':'serverOverloaded','message':'retry'})]
    with tempfile.TemporaryDirectory() as td:
        r,ws,messages=_run_case(Path(td),[failed,s._DONE_TURN_EVENTS('end','not reached')],prompt='$vsss --budget 1m task')
        check('[continuation] explicit original cap terminates retry without false completion',r.returncode==3 and 'user budget cap' in r.stderr and 'exitReason' not in s._read_state(ws) and len([m for m in messages if m.get('method')=='turn/start'])==1,r.stderr)


def test_codex_runner_does_not_mistake_old_completion_for_new_success():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
        state=ws/'.vss/codex-supervisor.json'; state.parent.mkdir()
        state.write_text(json.dumps({'threadId':'previous','exitReason':'old completed task'}))
        original=state.read_bytes()
        brief=tmp/'brief'; brief.write_text('$vsss --hours 0 new task')
        r=run(['node',str(RUNNER),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief),'--new-run'],env=env)
        check('[continuation] invalid new run stays failed despite an old terminal file',r.returncode!=0 and state.read_bytes()==original and 'invalid --hours cap' in r.stderr,r.stderr)


def test_codex_direct_watch_cannot_race_prompt_publication():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td); _,_,ws,env=s._supervisor_fixture(tmp)
        state=ws/'.vss/codex-supervisor.json'; state.parent.mkdir()
        lock=Path(str(state)+'.handoff.lock'); lock.write_text(json.dumps({'version':1,'token':'11111111-1111-1111-1111-111111111111'}))
        brief=Path(str(state)+'.prompt.txt'); brief.write_text('$vsss first task')
        stub=s._write_stub(tmp/'stub',{'turns':[{'events':s._DONE_TURN_EVENTS('end','done')}]})
        r=run(['node',str(RUNNER),'watch','--','run','--cwd',str(ws),'--prompt-file',str(brief),'--codex-bin',str(stub)],env=env)
        check('[continuation] direct watch cannot enter during detached prompt publication',r.returncode!=0 and not state.exists() and not (tmp/'stub/meta.json').exists() and brief.read_text()=='$vsss first task',r.stderr)
        check('[continuation] publication owner remains untouched',lock.exists() and json.loads(lock.read_text())['token']=='11111111-1111-1111-1111-111111111111')
