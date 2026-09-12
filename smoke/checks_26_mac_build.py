"""Offline adversarial checks for the mac-build v1 public import APIs.

These fixtures never invoke SSH or a host build tool.  They exercise the
client through its injectable transport and the host through its injectable
runner, using disposable git worktrees and stage/receipt directories.
"""
from smoke._core import *  # noqa: F401,F403

MAC_CLIENT = REPO / "devcontainer" / "mac-build.mjs"
MAC_HOST = REPO / "devcontainer" / "mac-build-host.mjs"
MAC_PROTOCOL = REPO / "devcontainer" / "mac-build-protocol.mjs"


def _node(script: str, args: list[str] | None = None, cwd=None):
    return run(["node", "--input-type=module", "-e", script, *(args or [])], cwd=cwd)


def _mod(file: Path) -> str:
    return file.resolve().as_uri()


def _git_workspace(root: Path) -> Path:
    ws = root / "project"
    ws.mkdir()
    check("[mac-build fixture] git init", run(["git", "init", "-q"], cwd=ws).returncode == 0)
    check("[mac-build fixture] git identity", run(["git", "config", "user.email", "fixture@example.invalid"], cwd=ws).returncode == 0)
    check("[mac-build fixture] git identity name", run(["git", "config", "user.name", "Fixture"], cwd=ws).returncode == 0)
    return ws


def _config(ws: Path, roots: list[str] | None = None):
    vibe = ws / ".vibe"; vibe.mkdir(exist_ok=True)
    (vibe / "key").write_text("private fixture key")
    (vibe / "key").chmod(0o600)
    (vibe / "known_hosts").write_text("host.docker.internal ssh-ed25519 fixture")
    (vibe / "mac-build.json").write_text(json.dumps({"account": "claude", "includeRoots": roots or ["Sources"], "identityFile": ".vibe/key", "knownHosts": ".vibe/known_hosts"}))


def test_mac_build_client_snapshot_and_config_boundary():
    print("\n[mac-build] AC1/3: local config boundary and deterministic snapshot")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); ws = _git_workspace(root)
        (ws / "Sources").mkdir(); (ws / "Sources" / "main.swift").write_text("let dirty = true\n")
        (ws / "Sources" / "run.sh").write_text("#!/bin/sh\necho fixture\n"); (ws / "Sources" / "run.sh").chmod(0o755)
        (ws / "Sources" / ".explicit").write_text("hidden")
        (ws / "Sources" / ".implicit").write_text("must not appear")
        (ws / ".build").mkdir(); (ws / ".build" / "leak").write_text("no")
        _config(ws, ["Sources/.explicit", "Sources/main.swift", "Sources/run.sh"])
        script = f'''import {{ makeRequest }} from {_mod(MAC_CLIENT)!r};
const x = await makeRequest({{root:process.argv[1], operation:'build'}});
console.log(JSON.stringify(x.request));'''
        r = _node(script, [str(ws)])
        req = json.loads(r.stdout) if r.returncode == 0 else {}
        paths = [x["path"] for x in req.get("files", [])]
        modes = {x["path"]: x["mode"] for x in req.get("files", [])}
        check("[mac-build] ordinary explicit source snapshot succeeds and excludes implicit dot/build entries",
              r.returncode == 0 and paths == ["Sources/.explicit", "Sources/main.swift", "Sources/run.sh"] and modes.get("Sources/run.sh") == 493 and len(req.get("digest", "")) == 64,
              r.stderr + r.stdout)

        # A config checked into the project is an attack on the local key path.
        check("[mac-build] track config", run(["git", "add", ".vibe/mac-build.json"], cwd=ws).returncode == 0)
        r = _node(script, [str(ws)])
        check("[mac-build] tracked config is refused", r.returncode != 0 and "must be untracked" in r.stderr, r.stderr)
        check("[mac-build] untrack config", run(["git", "rm", "--cached", "-q", ".vibe/mac-build.json"], cwd=ws).returncode == 0)
        (ws / ".vibe" / "mac-build.json").unlink()
        outside = root / "outside-config"; outside.write_text("{}")
        (ws / ".vibe" / "mac-build.json").symlink_to(outside)
        r = _node(script, [str(ws)])
        check("[mac-build] symlinked config is refused", r.returncode != 0 and "symlink" in r.stderr, r.stderr)


def test_mac_build_client_git_and_symlink_ancestor_boundaries():
    print("\n[mac-build] AC1/3: git and symlink ancestor boundaries")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "not-a-repository"; ws.mkdir()
        _config(ws)
        script = f'''import {{ makeRequest }} from {_mod(MAC_CLIENT)!r};
await makeRequest({{root:process.argv[1], operation:'build'}});'''
        r = _node(script, [str(ws)])
        check("[mac-build] config outside a git worktree is refused before snapshotting",
              r.returncode != 0 and "working git repository" in r.stderr, r.stderr)

        git_root = root / "git"; git_root.mkdir()
        ws = _git_workspace(git_root)
        (ws / "Sources").mkdir(); (ws / "Sources" / "a").write_text("x")
        outside = root / "outside-vibe"; outside.mkdir()
        (outside / "mac-build.json").write_text(json.dumps({"account":"claude", "includeRoots":["Sources"], "identityFile":".vibe/key", "knownHosts":".vibe/known_hosts"}))
        (ws / ".vibe").symlink_to(outside, target_is_directory=True)
        r = _node(script, [str(ws)])
        check("[mac-build] a symlinked config ancestor is refused", r.returncode != 0 and "symlink" in r.stderr, r.stderr)


def test_mac_build_protocol_rejects_malformed_snapshot_before_stage():
    print("\n[mac-build] AC3: strict snapshot parser rejects hostile envelopes")
    script = f'''import crypto from 'node:crypto'; import {{ parseRequest, digestFiles }} from {_mod(MAC_PROTOCOL)!r};
const file = {{path:'Sources/a', mode:420, content:'eA=='}};
const good = {{version:1, jobId:'123e4567-e89b-42d3-a456-426614174000', operation:'build', files:[file], digest:digestFiles([file])}};
const rawDigest = files => crypto.createHash('sha256').update(Buffer.from(JSON.stringify(files.map(x => [x.path,x.mode,x.content])), 'utf8')).digest('hex');
const caseCollision = [{{...file,path:'Sources/A'}},{{...file,path:'Sources/a'}}];
const normalizationCollision = [{{...file,path:'Sources/e\\u0301'}},{{...file,path:'Sources/é'}}];
const fileParentCollision = [{{...file,path:'Sources/node'}},{{...file,path:'Sources/node/file'}}];
const cases = [
  {{...good, files:[{{...file,path:'../escape'}}]}},
  {{...good, files:[file,file]}},
  {{...good, files:[{{...file,content:'eA='}}]}},
  {{...good, digest:'0'.repeat(64)}},
  {{...good, command:'sh -c evil'}},
  {{...good, files:caseCollision, digest:rawDigest(caseCollision)}},
  {{...good, files:normalizationCollision, digest:rawDigest(normalizationCollision)}},
  {{...good, files:fileParentCollision, digest:rawDigest(fileParentCollision)}},
];
console.log(JSON.stringify(cases.map(x => {{ try {{ parseRequest(JSON.stringify(x)); return false }} catch {{ return true }} }})));'''
    r = _node(script)
    check("[mac-build] traversal, duplicate, noncanonical base64, bad digest, command, case, Unicode-normalization and file-parent collisions all reject",
          r.returncode == 0 and json.loads(r.stdout) == [True] * 8, r.stderr + r.stdout)


def test_mac_build_transport_fixed_argv_and_no_shell_injection():
    print("\n[mac-build] AC1: SSH transport is a fixed argv invocation")
    script = f'''import {{ EventEmitter }} from 'node:events'; import {{ sshTransport }} from {_mod(MAC_CLIENT)!r};
const req={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174020',operation:'build',digest:'a'.repeat(64),files:[]}};
let got; const fake = (bin,args,opts) => {{ got={{bin,args,opts}}; const c=new EventEmitter(); c.stdin=new EventEmitter(); c.stdin.end=()=>{{}}; c.stdout=new EventEmitter(); c.stderr=new EventEmitter(); queueMicrotask(()=>{{c.stdout.emit('data',JSON.stringify({{version:1,jobId:req.jobId,operation:req.operation,fingerprint:req.digest,snapshotBytes:0,outcome:'success'}}));c.emit('close',0)}}); return c; }};
await sshTransport({{config:{{account:'claude;touch /nope', knownHosts:'.vibe/known hosts', identityFile:'.vibe/key;xx'}},request:req,spawnImpl:fake}});
console.log(JSON.stringify(got));'''
    r = _node(script)
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    args = got.get("args", [])
    check("[mac-build] hostile values remain single argv elements; remote command is fixed",
          r.returncode == 0 and got.get("bin") == "ssh" and args[-1:] == ["mac-build-host"] and
          "claude;touch /nope@host.docker.internal" in args and "-i" in args and
          all(x not in args for x in ["sh", "-c"]), r.stderr + r.stdout)
    check("[mac-build] BatchMode, no forwarding and known-host checking are all pinned",
          all(x in args for x in ["BatchMode=yes", "ForwardAgent=no", "ClearAllForwardings=yes", "StrictHostKeyChecking=yes"]), str(args))


def test_mac_build_transport_lifecycle_and_response_binding():
    print("\n[mac-build] AC1/3: SSH lifetime and response binding")
    script = f'''import {{ EventEmitter }} from 'node:events'; import {{ sshTransport }} from {_mod(MAC_CLIENT)!r};
const req={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174021',operation:'build',digest:'b'.repeat(64),files:[{{content:'eA=='}}]}};
const silent=()=>{{const c=new EventEmitter(); c.stdin=new EventEmitter(); c.stdin.end=()=>{{}}; c.stdout=new EventEmitter(); c.stderr=new EventEmitter(); c.kill=(signal)=>{{c.killed=signal}}; return c}};
const timeout=silent(); let timeoutMessage=''; try {{ await sshTransport({{config:{{account:'claude',knownHosts:'kh',identityFile:'key'}},request:req,spawnImpl:()=>timeout,timeoutMs:5}}); }} catch(e) {{ timeoutMessage=e.message }}
const controller=new AbortController(); const cancelled=silent(); const pending=sshTransport({{config:{{account:'claude',knownHosts:'kh',identityFile:'key'}},request:req,spawnImpl:()=>cancelled,timeoutMs:1000,signal:controller.signal}}).catch(e=>e.message); controller.abort(); const cancelMessage=await pending;
const wrong=(field,value)=>{{const c=silent(); queueMicrotask(()=>{{c.stdout.emit('data',JSON.stringify({{version:1,jobId:req.jobId,operation:req.operation,fingerprint:req.digest,snapshotBytes:1,outcome:'success',[field]:value}}));c.emit('close',0)}}); return c}};
const errors=[]; for (const [field,value] of [['version',2],['jobId','123e4567-e89b-42d3-a456-426614174022'],['operation','test'],['fingerprint','c'.repeat(64)],['snapshotBytes',2]]) {{ try {{await sshTransport({{config:{{account:'claude',knownHosts:'kh',identityFile:'key'}},request:req,spawnImpl:()=>wrong(field,value)}})}} catch(e) {{errors.push(e.message)}} }}
console.log(JSON.stringify({{timeoutMessage,timeoutKilled:timeout.killed,cancelMessage,cancelKilled:cancelled.killed,errors}}));'''
    r = _node(script)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    check("[mac-build] whole SSH timeout kills fake child and rejects", data.get("timeoutMessage") == "ssh whole-operation timeout" and data.get("timeoutKilled") == "SIGKILL", r.stderr + r.stdout)
    check("[mac-build] SSH cancellation kills fake child and rejects", data.get("cancelMessage") == "ssh operation cancelled" and data.get("cancelKilled") == "SIGKILL", r.stderr + r.stdout)
    check("[mac-build] every version/job/operation/fingerprint/snapshotBytes response mismatch rejects", data.get("errors") == ["host response identity or outcome is invalid"] * 5, r.stderr + r.stdout)


def test_mac_build_host_atomic_execution_replay_and_evidence():
    print("\n[mac-build] AC3/4/5/6: host execution, receipt, lock, and evidence")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); stage_root = root / "stages"; receipts = root / "receipts"
        script = f'''import {{ execute }} from {_mod(MAC_HOST)!r}; import {{ digestFiles }} from {_mod(MAC_PROTOCOL)!r};
const base=process.argv[1], req={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174000',operation:'build',files:[{{path:'Sources/a.swift',mode:420,content:'bGV0IHg9MQo='}}],digest:''}}; req.digest=digestFiles(req.files);
const cfg={{root:base+'/stages',receiptsRoot:base+'/receipts',commands:{{doctor:['/usr/bin/true'],build:['/usr/bin/true'],test:['/usr/bin/true']}},artifacts:[{{path:'out/result.txt',maxBytes:100}}],timeoutMs:1000}};
let calls=0; const runner=async (argv,o)=>{{calls++; await (await import('node:fs/promises')).mkdir(o.cwd+'/out'); await (await import('node:fs/promises')).writeFile(o.cwd+'/out/result.txt','ok'); return {{exit:0,stdout:'built',stderr:'',timedOut:false,overflow:false}}}};
const one=await execute(req,cfg,{{runner}}); const two=await execute(req,cfg,{{runner}});
const receipt=JSON.parse(await (await import('node:fs/promises')).readFile(base+'/receipts/'+req.jobId+'.json','utf8'));
console.log(JSON.stringify({{one,two,receipt,calls}}));'''
        r = _node(script, [str(root)])
        data = json.loads(r.stdout) if r.returncode == 0 else {}
        one, two, receipt = data.get("one", {}), data.get("two", {}), data.get("receipt", {})
        check("[mac-build] successful immutable build reports both fingerprints, bounded artifact and logs",
              r.returncode == 0 and one.get("outcome") == "success" and one.get("actualFingerprintBefore") == one.get("fingerprint") == one.get("actualFingerprintAfter") and one.get("logs", {}).get("stdout") == "built" and one.get("artifacts") == [{"path":"out/result.txt","available":True,"bytes":2,"content":"b2s="}], r.stderr + r.stdout)
        check("[mac-build] identical terminal UUID replay returns the cached result without another runner call",
              two == one and data.get("calls") == 1, str(data))
        check("[mac-build] terminal receipt binds the complete request identity", receipt == {"state": "terminal", "identity": {"version": 1, "jobId": one.get("jobId"), "operation": "build", "digest": one.get("fingerprint")}, "result": one}, str(receipt))

        # Independent operation has a new job ID: fixture a lock then ensure no runner fires.
        (receipts / ".mac-build.lock").mkdir(parents=True, exist_ok=True)
        script_lock = f'''import {{ execute }} from {_mod(MAC_HOST)!r}; import {{ digestFiles }} from {_mod(MAC_PROTOCOL)!r};
const base=process.argv[1], file={{path:'a',mode:420,content:'eA=='}};
const req={{version:1,jobId:'123e4567-e89b-42d3-a456-426614174001',operation:'build',files:[file],digest:digestFiles([file])}};
const cfg={{root:base+'/stages',receiptsRoot:base+'/receipts',commands:{{doctor:['/usr/bin/true'],build:['/usr/bin/true'],test:['/usr/bin/true']}}}};
console.log(JSON.stringify(await execute(req,cfg,{{runner:async()=>{{throw new Error('runner must not run while locked')}}}})));'''
        r = _node(script_lock, [str(root)])
        locked = json.loads(r.stdout) if r.returncode == 0 else {}
        check("[mac-build] existing resource lock fails closed with cleanup guidance", locked.get("outcome") == "busy" and "administrator" in locked.get("error", ""), r.stderr + r.stdout)


def test_mac_build_host_failure_artifact_and_doctor_fixtures():
    print("\n[mac-build] AC4/5/6: hostile artifact, timeout, and doctor fixture")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        script = f'''import fs from 'node:fs/promises'; import {{ execute }} from {_mod(MAC_HOST)!r}; import {{ digestFiles }} from {_mod(MAC_PROTOCOL)!r};
const base=process.argv[1]; const f={{path:'a',mode:420,content:'eA=='}}; const mk=(id,op)=>({{version:1,jobId:id,operation:op,files:[f],digest:digestFiles([f])}});
const cfg={{root:base+'/s',receiptsRoot:base+'/r',commands:{{doctor:['/usr/bin/true'],build:['/usr/bin/true'],test:['/usr/bin/true']}},artifacts:[{{path:'out',maxBytes:1}},{{path:'links/result',maxBytes:10}}]}};
const badCfg={{...cfg,artifacts:[{{path:'../escape',maxBytes:10}}]}};
let invalidArtifact=''; try {{ await execute(mk('123e4567-e89b-42d3-a456-426614174009','build'),badCfg,{{runner:async()=>{{throw new Error('must not run')}}}}) }} catch (e) {{ invalidArtifact=e.message }}
const bad=await execute(mk('123e4567-e89b-42d3-a456-426614174010','build'),cfg,{{runner:async(a,o)=>{{await fs.writeFile(o.cwd+'/out','too big'); await fs.mkdir(o.cwd+'/real'); await fs.writeFile(o.cwd+'/real/result','ok'); await fs.symlink('real',o.cwd+'/links'); await fs.writeFile(o.cwd+'/a','mutated'); return {{exit:0,stdout:'',stderr:'',timedOut:true,overflow:false}}}}}});
const doctor=await execute(mk('123e4567-e89b-42d3-a456-426614174011','doctor'),cfg,{{runner:async()=>({{exit:1,stdout:'',stderr:'no xcode',timedOut:false,overflow:false}})}});
const healthyDoctor=await execute(mk('123e4567-e89b-42d3-a456-426614174012','doctor'),cfg,{{runner:async()=>({{exit:0,stdout:'xcode version',stderr:'',timedOut:false,overflow:false}})}});
console.log(JSON.stringify({{bad,doctor,healthyDoctor,invalidArtifact}}));'''
        r = _node(script, [str(root)])
        data = json.loads(r.stdout) if r.returncode == 0 else {}
        bad, doctor, healthy_doctor = data.get("bad", {}), data.get("doctor", {}), data.get("healthyDoctor", {})
        check("[mac-build] artifact traversal rejects the entire host configuration before execution",
              data.get("invalidArtifact") == "invalid artifact config", str(data))
        check("[mac-build] timeout or source mutation is failure with evidence; unsafe/oversize artifacts are withheld",
              bad.get("outcome") == "failure" and bad.get("timedOut") is True and bad.get("actualFingerprintAfter") != bad.get("fingerprint") and all(not a.get("available") for a in bad.get("artifacts", [])), r.stderr + r.stdout)
        check("[mac-build] an artifact reached through a symlink parent is explicitly withheld",
              any(a.get("path") == "links/result" and a.get("reason") == "unsafe_or_too_large" for a in bad.get("artifacts", [])), str(bad.get("artifacts")))
        check("[mac-build] doctor fixture reports unavailable Xcode rather than claiming a live host", doctor.get("outcome") == "failure" and doctor.get("toolAvailability", {}).get("xcode", {}).get("available") is False and "no xcode" in doctor.get("logs", {}).get("stderr", ""), r.stderr + r.stdout)
        check("[mac-build] doctor success alone does not attest simulator availability", healthy_doctor.get("toolAvailability", {}).get("simulator", {}).get("available") is False, str(healthy_doctor))


def main():
    test_mac_build_client_snapshot_and_config_boundary()
    test_mac_build_client_git_and_symlink_ancestor_boundaries()
    test_mac_build_protocol_rejects_malformed_snapshot_before_stage()
    test_mac_build_transport_fixed_argv_and_no_shell_injection()
    test_mac_build_transport_lifecycle_and_response_binding()
    test_mac_build_host_atomic_execution_replay_and_evidence()
    test_mac_build_host_failure_artifact_and_doctor_fixtures()
    if FAILURES:
        print("\\nFAILURES:")
        for name, detail in FAILURES: print(f"- {name}: {detail}")
        raise SystemExit(1)


if __name__ == '__main__':
    main()
