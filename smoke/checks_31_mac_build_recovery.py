"""Offline recovery and fail-closed checks for the mac-build public imports."""
from smoke._core import *  # noqa: F401,F403

MAC_CLIENT = REPO / "devcontainer" / "mac-build.mjs"
MAC_HOST = REPO / "devcontainer" / "mac-build-host.mjs"
MAC_PROTOCOL = REPO / "devcontainer" / "mac-build-protocol.mjs"


def _node(script: str, args: list[str] | None = None):
    return run(["node", "--input-type=module", "-e", script, *(args or [])])


def _mod(file: Path) -> str:
    return file.resolve().as_uri()


def _workspace(root: Path):
    ws = root / "project"; ws.mkdir()
    check("[mac-build recovery fixture] git init", run(["git", "init", "-q"], cwd=ws).returncode == 0)
    check("[mac-build recovery fixture] identity", run(["git", "config", "user.email", "fixture@example.invalid"], cwd=ws).returncode == 0)
    (ws / "Sources").mkdir(); (ws / "Sources" / "main.swift").write_text("let x = 1\n")
    vibe = ws / ".vibe"; vibe.mkdir()
    (vibe / "key").write_text("fixture"); (vibe / "key").chmod(0o600)
    (vibe / "known_hosts").write_text("fixture host key")
    (vibe / "mac-build.json").write_text(json.dumps({"account": "claude", "includeRoots": ["Sources"], "identityFile": ".vibe/key", "knownHosts": ".vibe/known_hosts"}))
    return ws


def test_client_retains_snapshot_and_private_evidence_across_disconnect_and_replay():
    print("\n[mac-build recovery] client retained request, evidence, and explicit replay")
    with tempfile.TemporaryDirectory() as td:
        ws = _workspace(Path(td))
        script = f'''import fs from 'node:fs/promises'; import {{ run, replay }} from {_mod(MAC_CLIENT)!r};
const root=process.argv[1]; let disconnect='';
try {{ await run({{root,operation:'build',transport:async()=>{{throw new Error('connection dropped')}}}}) }} catch (e) {{ disconnect=e.message }}
const dir=root+'/.vibe/mac-build-requests'; const names=await fs.readdir(dir); const requestFile=dir+'/'+names.find(x=>x.endsWith('.json'));
const saved=JSON.parse(await fs.readFile(requestFile,'utf8')); const requestMode=(await fs.stat(requestFile)).mode&0o777; const dirMode=(await fs.stat(dir)).mode&0o777;
let replayed; const calls=[]; replayed=await replay({{root,jobId:saved.request.jobId,transport:async x=>{{calls.push(x.request); return {{version:1,jobId:x.request.jobId,operation:x.request.operation,fingerprint:x.request.digest,snapshotBytes:x.request.files.reduce((n,f)=>n+Buffer.from(f.content,'base64').length,0),outcome:'success'}}}}}});
const evidence=requestFile+'.result.json'; const evidenceMode=(await fs.stat(evidence)).mode&0o777;
let hostFailure=''; try {{ await run({{root,operation:'test',transport:async x=>({{version:1,jobId:x.request.jobId,operation:x.request.operation,fingerprint:x.request.digest,snapshotBytes:x.request.files.reduce((n,f)=>n+Buffer.from(f.content,'base64').length,0),outcome:'failure',error:'fixture failure'}})}}) }} catch(e) {{ hostFailure=e.message }}
const failureFile=(await fs.readdir(dir)).find(x=>x.endsWith('.result.json') && dir+'/'+x !== evidence); const failureEvidence=JSON.parse(await fs.readFile(dir+'/'+failureFile,'utf8')); const failureMode=(await fs.stat(dir+'/'+failureFile)).mode&0o777;
await fs.writeFile(root+'/.vibe/key2','fixture'); await fs.chmod(root+'/.vibe/key2',0o600);
const cfg=JSON.parse(await fs.readFile(root+'/.vibe/mac-build.json','utf8')); cfg.identityFile='.vibe/key2'; await fs.writeFile(root+'/.vibe/mac-build.json',JSON.stringify(cfg));
let mismatch=''; try {{ await replay({{root,jobId:saved.request.jobId,transport:async()=>{{throw new Error('must not transport')}}}}) }} catch(e) {{ mismatch=e.message }}
console.log(JSON.stringify({{disconnect,names,requestMode,dirMode,replayed,calls,evidenceMode,hostFailure,failureEvidence,failureMode,mismatch}}));'''
        result = _node(script, [str(ws)])
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        check("[mac-build] disconnect keeps the original request before transport without silently retrying",
              result.returncode == 0 and "connection dropped" in data.get("disconnect", "") and len(data.get("names", [])) == 1, result.stderr + result.stdout)
        check("[mac-build] explicit replay sends the exact saved UUID and snapshot",
              len(data.get("calls", [])) == 1 and data.get("calls", [{}])[0].get("jobId") == data.get("replayed", {}).get("jobId"), str(data))
        check("[mac-build] retained request directory, request, and success evidence are private",
              data.get("dirMode") == 0o700 and data.get("requestMode") == 0o600 and data.get("evidenceMode") == 0o600, str(data))
        check("[mac-build] a returned host failure is retained as private response evidence",
              "host operation failed: failure" in data.get("hostFailure", "") and data.get("failureEvidence", {}).get("error") == "fixture failure" and data.get("failureMode") == 0o600, str(data))
        check("[mac-build] replay refuses a changed key binding before transport", data.get("mismatch") == "retained request binding changed", str(data))


def test_host_receipt_identity_unknown_recovery_and_config_rejection():
    print("\n[mac-build recovery] receipts and complete host configuration validation")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        script = f'''import fs from 'node:fs/promises'; import {{ execute }} from {_mod(MAC_HOST)!r}; import {{ digestFiles }} from {_mod(MAC_PROTOCOL)!r};
const base=process.argv[1], file={{path:'a',mode:420,content:'eA=='}};
const req={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174101',operation:'build',files:[file],digest:digestFiles([file])}};
const cfg={{root:base+'/stages',receiptsRoot:base+'/receipts',commands:{{doctor:['/usr/bin/true'],build:['/usr/bin/true'],test:['/usr/bin/true']}}}};
let calls=0; const runner=async()=>{{calls++; return {{exit:0,stdout:'',stderr:'',timedOut:false,overflow:false}}}};
const first=await execute(req,cfg,{{runner}}); const changed={{...req,operation:'test'}}; const mismatch=await execute(changed,cfg,{{runner}});
const unknownId='123e4567-e89b-42d3-a456-426614174102', unknown={{...req,jobId:unknownId}};
await fs.writeFile(base+'/receipts/'+unknownId+'.json',JSON.stringify({{state:'unknown-running',identity:{{version:1,jobId:unknownId,operation:'build',digest:unknown.digest}}}}),{{mode:0o600}});
const recovered=await execute(unknown,cfg,{{runner}});
const malformed=[]; for (const bad of [{{...cfg,commands:{{...cfg.commands,build:['build']}}}},{{...cfg,root:'relative'}},{{...cfg,artifacts:[{{path:'../escape',maxBytes:1}}]}}]) {{ try {{await execute(req,bad,{{runner}}); malformed.push(false)}} catch {{malformed.push(true)}} }}
console.log(JSON.stringify({{first,mismatch,recovered,calls,malformed}}));'''
        result = _node(script, [str(root)])
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        check("[mac-build] same UUID with a different operation rejects and never reruns", data.get("mismatch", {}).get("outcome") == "rejected" and data.get("calls") == 1, result.stderr + result.stdout)
        check("[mac-build] an unknown receipt returns recovery guidance and never executes", data.get("recovered", {}).get("outcome") == "unknown" and data.get("calls") == 1, str(data))
        check("[mac-build] relative command, nonabsolute state root, and traversal artifact configurations fail closed", data.get("malformed") == [True, True, True], str(data))


def test_symlink_descriptors_and_detached_child_cleanup():
    print("\n[mac-build recovery] descriptor-path and local process-group defenses")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); ws = _workspace(root)
        (ws / ".vibe" / "key").unlink(); (ws / ".vibe" / "real-key").write_text("fixture"); (ws / ".vibe" / "real-key").chmod(0o600)
        (ws / ".vibe" / "key").symlink_to("real-key")
        client = f'''import {{ makeRequest }} from {_mod(MAC_CLIENT)!r}; await makeRequest({{root:process.argv[1],operation:'build'}});'''
        rejected = _node(client, [str(ws)])
        marker = root / "escaped-child-ran"
        runner = f'''import {{ runApproved }} from {_mod(MAC_HOST)!r};
const marker=process.argv[1]; const program=`const {{spawn}}=require('node:child_process'); const fs=require('node:fs'); spawn(process.execPath,['-e',\\`setTimeout(()=>require('node:fs').writeFileSync(${json.dumps(str(marker))},'bad'),250)\\`],{{stdio:'ignore'}}); setTimeout(()=>process.exit(0),20)`;
const result=await runApproved([process.execPath,'-e',program],{{timeoutMs:2000}}); await new Promise(resolve=>setTimeout(resolve,500)); console.log(JSON.stringify({{result,exists:await (await import('node:fs/promises')).access(marker).then(()=>true,()=>false)}}));'''
        cleanup = _node(runner, [str(marker)])
        data = json.loads(cleanup.stdout) if cleanup.returncode == 0 else {}
        check("[mac-build] symlinked key descriptor path is refused", rejected.returncode != 0 and "symlink" in rejected.stderr, rejected.stderr)
        check("[mac-build] runApproved kills an ordinary detached descendant group", cleanup.returncode == 0 and data.get("exists") is False and data.get("result", {}).get("cleanupFailed") is False, cleanup.stderr + cleanup.stdout)


def test_cleanup_failure_retains_unknown_receipt_and_cancellation_is_bounded():
    with tempfile.TemporaryDirectory() as td:
        script = f'''import fs from 'node:fs/promises';
import {{execute,runApproved}} from {_mod(MAC_HOST)!r};
import {{digestFiles}} from {_mod(MAC_PROTOCOL)!r};
const base=process.argv[1], files=[{{path:'source',mode:420,content:'eA=='}}];
const request={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174000',operation:'build',files,digest:digestFiles(files)}};
const cfg={{root:base+'/stage',receiptsRoot:base+'/receipts',commands:{{doctor:['/bin/true'],build:['/bin/true'],test:['/bin/true']}}}};
const original=process.execPath; process.execPath=base+'/missing-cleanup-interpreter';
const result=await execute(request,cfg,{{runner:async()=>({{exit:0,stdout:'built',stderr:'',timedOut:false,overflow:false}})}});
process.execPath=original;
const receipt=JSON.parse(await fs.readFile(cfg.receiptsRoot+'/'+request.jobId+'.json','utf8'));
const lock=await fs.stat(cfg.receiptsRoot+'/.mac-build.lock').then(()=>true,()=>false);
const controller=new AbortController(), start=Date.now();
setTimeout(()=>controller.abort(),100);
const cancelled=await runApproved(['/bin/sh','-c','sleep 10'],{{cwd:base,env:{{PATH:'/usr/bin:/bin'}},timeoutMs:20000,signal:controller.signal}});
console.log(JSON.stringify({{result,receipt,lock,cancelled,elapsed:Date.now()-start}}));'''
        result = _node(script, [td])
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        check("[mac-build] failed cleanup cannot commit terminal success or release ownership",
              data.get("result", {}).get("outcome") == "unknown" and
              data.get("receipt", {}).get("state") == "unknown-running" and data.get("lock") is True,
              result.stdout + result.stderr)
        check("[mac-build] cancellation ends the owned group within a bounded interval",
              data.get("cancelled", {}).get("cancelled") is True and data.get("elapsed", 99999) < 3000,
              result.stdout + result.stderr)


def test_ssh_config_parser_preserves_spaced_and_quoted_known_host_path():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = _workspace(root)
        moved = root / 'project with spaces'; ws.rename(moved); ws = moved
        known = ws / '.vibe' / 'known "hosts"'; known.write_text('fixture')
        config_file = ws / '.vibe/mac-build.json'
        config = json.loads(config_file.read_text())
        config['knownHosts'] = '.vibe/known "hosts"'
        config_file.write_text(json.dumps(config))
        script = f'''import {{EventEmitter}} from 'node:events';
import {{makeRequest,sshTransport}} from {_mod(MAC_CLIENT)!r};
const {{config,request}}=await makeRequest({{root:process.argv[1],operation:'build'}});
let captured;
await sshTransport({{config,request,spawnImpl:(bin,args)=>{{
 captured=args; const child=new EventEmitter();
 child.stdin=new EventEmitter(); child.stdin.end=()=>{{}};
 child.stdout=new EventEmitter(); child.stderr=new EventEmitter();
 queueMicrotask(()=>{{child.stdout.emit('data',JSON.stringify({{version:1,jobId:request.jobId,operation:request.operation,fingerprint:request.digest,snapshotBytes:request.files.reduce((n,f)=>n+Buffer.byteLength(f.content,'base64'),0),outcome:'success'}}));child.emit('close',0)}});
 return child;
}}}});
console.log(JSON.stringify(captured));'''
        result = _node(script, [str(ws)])
        check('[mac-build] spaced project and quoted host-key path produce valid request argv',
              result.returncode == 0, result.stdout + result.stderr)
        if result.returncode != 0:
            return
        # -G evaluates configuration and exits. It never opens a connection;
        # -F /dev/null excludes user configuration and all data here is fixture.
        parsed = subprocess.run(['ssh', '-G', *json.loads(result.stdout)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        line = next((line for line in parsed.stdout.splitlines() if line.startswith('userknownhostsfile ')), '')
        check('[mac-build] real offline OpenSSH parser preserves the entire known-host pathname',
              parsed.returncode == 0 and str(known) in line, parsed.stderr + line)
        for name in ['known%h', 'known${HOME}']:
            (ws / '.vibe' / name).write_text('fixture')
            config['knownHosts'] = '.vibe/' + name
            config_file.write_text(json.dumps(config))
            rejected = _node(script, [str(ws)])
            check('[mac-build] SSH expansion tokens in configured key paths are refused',
                  rejected.returncode != 0 and 'unsupported SSH expansion' in rejected.stderr,
                  rejected.stdout + rejected.stderr)


def main():
    test_client_retains_snapshot_and_private_evidence_across_disconnect_and_replay()
    test_host_receipt_identity_unknown_recovery_and_config_rejection()
    test_symlink_descriptors_and_detached_child_cleanup()
    test_cleanup_failure_retains_unknown_receipt_and_cancellation_is_bounded()
    test_ssh_config_parser_preserves_spaced_and_quoted_known_host_path()
    if FAILURES:
        print("\\nFAILURES:")
        for name, detail in FAILURES: print(f"- {{name}}: {{detail}}")
        raise SystemExit(1)


if __name__ == '__main__':
    main()
