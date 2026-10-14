"""Model routing policy (2026-10-14): latest-in-class, the lead's cost
ceiling, older-model pins, the Claude subagent hook, the supervisor's run
model, and default-on remote control in the launcher.

Triggered by a night where a Codex-led /vsss ran on an old Astra thread and
dispatched `sol` as a hard-coded gpt-5.6-sol while the user had GPT-6.1-Sol
selected. Every refusal here must make ZERO vendor calls.
"""
from smoke._core import *
from smoke._core import _source_vibe_call
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call, FIXTURE_CATALOG
import smoke.checks_19_codex_supervisor as sup

MODELS = REPO / "devcontainer/vibe-models.mjs"
_ROLE_DONE = {"answer": {"report": "fixture report", "status": "done"}}
_HOUR = 3600
_T0 = 1_800_000_000


def _models(args, env, cwd, input=""):
    return run(["node", str(MODELS), *args], env=env, cwd=cwd, input=input)


def test_model_policy_latest_in_class_and_ceiling():
    print("\n[model-policy] latest model per class; lead cost ceiling; consent and grants")
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead="claude-opus-5-5")
        st = _models(["status"], env, ws)
        status = json.loads(st.stdout) if st.returncode == 0 else {}
        check("[model-policy] status: newest LISTED model per class (hidden gpt-7-sol and older versions ignored)",
              status.get("latest", {}).get("sol") == "gpt-6.1-sol" and status["latest"].get("luna") == "gpt-6-luna"
              and status["latest"].get("terra") == "gpt-5.6-terra" and status["latest"].get("astra") == "gpt-6-astra",
              st.stdout + st.stderr)
        check("[model-policy] status: an Opus lead may use Sol/Luna/Terra and Opus/Sonnet/Haiku unasked, never Astra/Fable",
              sorted(status.get("allowedWithoutAsking", [])) == sorted(["terra", "luna", "sol", "haiku", "sonnet", "opus"]),
              str(status.get("allowedWithoutAsking")))

        r, calls = _delegate_call(ws, home, env, ["role", "reviewer", "--model", "sol", "--cwd", str(ws)], _ROLE_DONE)
        check("[model-policy] Opus lead: role sol dispatches the newest Sol",
              r.returncode == 0 and calls and calls[-1]["args"][:3] == ["exec", "-m", "gpt-6.1-sol"], r.stderr + str(calls[-1:]))

        r, calls = _delegate_call(ws, home, env, ["role", "reviewer", "--model", "astra", "--cwd", str(ws)], _ROLE_DONE)
        check("[model-policy] Opus lead: Astra refused without permission, zero vendor calls",
              r.returncode != 0 and not calls and "explicit permission" in r.stderr, r.stderr + str(calls))
        r, calls = _delegate_call(ws, home, env, ["ask", "astra"])
        check("[model-policy] Opus lead: ask astra refused too, zero vendor calls",
              r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(ws, home, env, ["ask", "fable"])
        check("[model-policy] Opus lead: ask fable refused without consent", r.returncode != 0 and not calls, r.stderr)

        r, calls = _delegate_call(ws, home, env, ["role", "reviewer", "--model", "astra", "--cwd", str(ws), "--consent-model"], _ROLE_DONE)
        check("[model-policy] --consent-model authorises Astra for that one call",
              r.returncode == 0 and calls[-1]["args"][:3] == ["exec", "-m", "gpt-6-astra"], r.stderr)
        r, calls = _delegate_call(ws, home, env, ["ask", "fable", "--consent-credits"])
        check("[model-policy] --consent-credits also clears Fable's tier", r.returncode == 0 and calls, r.stderr)

        tenv = {**env, "VIBE_MODELS_NOW": str(_T0)}
        g = _models(["grant", "astra", "--for", "2h"], tenv, ws)
        check("[model-policy] grant needs no vendor and records to .vibe/model-policy.json",
              g.returncode == 0 and (ws / ".vibe/model-policy.json").exists(), g.stderr)
        r, calls = _delegate_call(ws, home, {**tenv, "VIBE_MODELS_NOW": str(_T0 + _HOUR)},
                                  ["role", "reviewer", "--model", "astra", "--cwd", str(ws)], _ROLE_DONE)
        check("[model-policy] a live grant authorises Astra", r.returncode == 0 and calls, r.stderr)
        r, calls = _delegate_call(ws, home, {**tenv, "VIBE_MODELS_NOW": str(_T0 + 3 * _HOUR)},
                                  ["role", "reviewer", "--model", "astra", "--cwd", str(ws)], _ROLE_DONE)
        check("[model-policy] an expired grant no longer does", r.returncode != 0 and not calls, r.stderr)
        g = _models(["grant", "astra"], tenv, ws)
        check("[model-policy] grant without --for is refused", g.returncode != 0 and "--for" in g.stderr, g.stderr)


def test_model_policy_review_slot_and_unknown_lead():
    print("\n[model-policy] /review codex slot stays within the lead's tier; unknown lead fails closed")
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead="claude-opus-5-5")
        review = {"answer": {"verdict": "PASS", "summary": "ok", "findings": []}}
        r, calls = _delegate_call(ws, home, env, ["review", "codex"], review, payload="diff --git a/x b/x\n")
        check("[model-policy] Opus lead: /review codex uses the newest Sol, not Astra",
              r.returncode == 0 and calls[-1]["args"][:3] == ["exec", "-m", "gpt-6.1-sol"], r.stderr + str(calls[-1:]))
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead="claude-sonnet-5-5")
        r, calls = _delegate_call(ws, home, env, ["role", "reviewer", "--model", "opus", "--cwd", str(ws)])
        check("[model-policy] Sonnet lead: Opus subagent refused, zero calls", r.returncode != 0 and not calls, r.stderr)
        r, calls = _delegate_call(ws, home, env, ["role", "reviewer", "--model", "luna", "--cwd", str(ws)], _ROLE_DONE)
        check("[model-policy] Sonnet lead: Luna (same tier) allowed", r.returncode == 0 and calls, r.stderr)
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead=None)
        r, calls = _delegate_call(ws, home, env, ["ask", "haiku"])
        check("[model-policy] no detectable lead: refused, zero calls",
              r.returncode != 0 and not calls and "leading this conversation" in r.stderr, r.stderr)
        r, calls = _delegate_call(ws, home, {**env, "VIBE_LEAD_MODEL": "mystery-model"}, ["ask", "haiku"])
        check("[model-policy] unknown lead model: refused, zero calls", r.returncode != 0 and not calls, r.stderr)


def test_model_policy_lead_detection_from_transcripts():
    print("\n[model-policy] lead = the asking conversation's own latest turn model")
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead=None)
        thread = "01a121ee-3e8f-79a0-b0d1-014fe8ca0e26"
        day = home / ".codex/sessions/2026/10/14"; day.mkdir(parents=True)
        lines = [{"type": "session_meta", "payload": {"id": thread}},
                 {"type": "turn_context", "payload": {"model": "gpt-6-astra"}},
                 {"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}]
        (day / f"rollout-2026-10-14T08-00-00-{thread}.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
        other = home / ".codex/sessions/2026/10/13"; other.mkdir(parents=True)
        (other / "rollout-2026-10-13T08-00-00-ffffffff-0000-0000-0000-000000000000.jsonl").write_text(
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra"}}) + "\n")
        r = _models(["lead"], {**env, "CODEX_THREAD_ID": thread}, ws)
        check("[model-policy] Codex: the thread's LAST turn model (user switched Astra -> Sol), not another thread's",
              r.stdout.strip() == "gpt-6.1-sol", r.stdout + r.stderr)

        sid = "57d36eee-f728-456c-9914-d8aa0b10e3e6"
        proj = Path(env["CLAUDE_CONFIG_DIR"]) / "projects/-workspace" if env.get("CLAUDE_CONFIG_DIR") else home / ".claude/projects/-workspace"
        proj.mkdir(parents=True, exist_ok=True)
        recs = [{"type": "assistant", "message": {"model": "claude-sonnet-5-5"}},
                {"type": "assistant", "message": {"model": "claude-opus-5-5"}},
                {"type": "assistant", "message": {"model": "<synthetic>"}}]
        (proj / f"{sid}.jsonl").write_text("\n".join(json.dumps(x) for x in recs) + "\n")
        r = _models(["lead"], {**env, "CLAUDE_CODE_SESSION_ID": sid}, ws)
        check("[model-policy] Claude: the session's last real assistant model", r.stdout.strip() == "claude-opus-5-5",
              r.stdout + r.stderr)


def test_model_policy_older_model_pins():
    print("\n[model-policy] older models only on request; 8-hour reconfirmation; expiry")
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead="gpt-6.1-sol")
        e0 = {**env, "VIBE_MODELS_NOW": str(_T0)}
        r = _models(["pin", "sol", "gpt-6-sol"], e0, ws)
        check("[model-policy] pin without --for refused (ask how long)", r.returncode != 0 and "--for" in r.stderr, r.stderr)
        r = _models(["pin", "sol", "gpt-6-luna", "--for", "2d"], e0, ws)
        check("[model-policy] pin must name a model of that class", r.returncode != 0, r.stderr)
        r = _models(["pin", "sol", "gpt-6-sol", "--for", "2d"], e0, ws)
        check("[model-policy] pin recorded", r.returncode == 0, r.stderr)
        args = ["role", "reviewer", "--model", "sol", "--cwd", str(ws)]
        r, calls = _delegate_call(ws, home, {**env, "VIBE_MODELS_NOW": str(_T0 + _HOUR)}, args, _ROLE_DONE)
        check("[model-policy] a pinned class dispatches the requested older model",
              r.returncode == 0 and calls[-1]["args"][:3] == ["exec", "-m", "gpt-6-sol"], r.stderr)
        r, calls = _delegate_call(ws, home, {**env, "VIBE_MODELS_NOW": str(_T0 + 8 * _HOUR)}, args, _ROLE_DONE)
        check("[model-policy] 8 hours unconfirmed: refused with a reconfirm instruction, zero calls",
              r.returncode != 0 and not calls and "still stands" in r.stderr, r.stderr)
        r = _models(["resolve", "sol"], {**env, "VIBE_MODELS_NOW": str(_T0 + 8 * _HOUR)}, ws)
        check("[model-policy] resolve exits 3 when reconfirmation is due", r.returncode == 3, f"rc={r.returncode}")
        r = _models(["confirm", "sol"], {**env, "VIBE_MODELS_NOW": str(_T0 + 9 * _HOUR)}, ws)
        r2, calls = _delegate_call(ws, home, {**env, "VIBE_MODELS_NOW": str(_T0 + 10 * _HOUR)}, args, _ROLE_DONE)
        check("[model-policy] after confirm the pin resolves again",
              r.returncode == 0 and r2.returncode == 0 and calls[-1]["args"][2] == "gpt-6-sol", r.stderr + r2.stderr)
        r, calls = _delegate_call(ws, home, {**env, "VIBE_MODELS_NOW": str(_T0 + 49 * _HOUR)}, args, _ROLE_DONE)
        check("[model-policy] an expired pin falls back to the newest model",
              r.returncode == 0 and calls[-1]["args"][2] == "gpt-6.1-sol", r.stderr)
        r = _models(["confirm", "sol"], {**env, "VIBE_MODELS_NOW": str(_T0 + 49 * _HOUR)}, ws)
        check("[model-policy] confirming an expired pin says it expired instead of recording",
              r.returncode != 0 and "expired" in r.stderr and "recorded" not in r.stdout, r.stdout + r.stderr)
        (ws / ".vibe/model-policy.json").write_text(json.dumps({"pins": {"sol": {"model": "gpt-6-sol", "until": _T0 + 99 * _HOUR}}, "grants": {}}))
        r, calls = _delegate_call(ws, home, {**env, "VIBE_MODELS_NOW": str(_T0)}, args, _ROLE_DONE)
        check("[model-policy] a pin with no confirmation time is due for reconfirmation, not standing for ever",
              r.returncode != 0 and not calls and "still stands" in r.stderr, r.stderr)
        (ws / ".vibe/model-policy.json").write_text("{not json")
        r, calls = _delegate_call(ws, home, env, args, _ROLE_DONE)
        check("[model-policy] a corrupt policy file fails closed", r.returncode != 0 and not calls, r.stderr)


def test_model_policy_claude_agent_hook():
    print("\n[model-policy] Claude Code PreToolUse hook on Agent/Task")
    with tempfile.TemporaryDirectory() as td:
        ws, home, env = _delegate_fixture(Path(td), lead=None)
        transcript = Path(td) / "t.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5"}}) + "\n")

        def hook(model, extra_env=None):
            payload = {"tool_name": "Agent", "cwd": str(ws), "transcript_path": str(transcript),
                       "tool_input": {"prompt": "x", **({"model": model} if model else {})}}
            r = _models(["hook"], {**env, **(extra_env or {})}, ws, input=json.dumps(payload))
            return r, (json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "allow")

        r, d = hook("fable")
        check("[model-policy] hook: Fable under an Opus lead is denied", d == "deny" and r.returncode == 0, r.stdout)
        check("[model-policy] hook: the denial offers a grant, not a --consent-model flag Agent calls can't pass",
              "vibe-models grant fable" in r.stdout and "--consent-model" not in r.stdout, r.stdout)
        check("[model-policy] hook: no model (inherits the lead) is allowed", hook(None)[1] == "allow", "")
        check("[model-policy] hook: sonnet is allowed", hook("sonnet")[1] == "allow", "")
        check("[model-policy] hook: opus (same tier) is allowed", hook("opus")[1] == "allow", "")
        check("[model-policy] hook: unknown model is denied", hook("gpt-4o")[1] == "deny", "")
        _models(["pin", "opus", "claude-opus-4-1", "--for", "1d"], env, ws)
        r, d = hook("opus")
        check("[model-policy] hook: a pinned class steers to the requested older model",
              d == "deny" and "claude-opus-4-1" in r.stdout, r.stdout)
        check("[model-policy] hook: the pinned id itself is allowed", hook("claude-opus-4-1")[1] == "allow", "")

        # No `model` on the call: the agent definition's own `model:` line counts.
        agents = ws / ".claude/agents"; agents.mkdir(parents=True)
        (agents / "pricey.md").write_text("---\nname: pricey\nmodel: fable\n---\nbody\n")
        (agents / "plain.md").write_text("---\nname: plain\nmodel: inherit\n---\nbody\n")
        def hook_type(t):
            payload = {"tool_name": "Agent", "cwd": str(ws), "transcript_path": str(transcript),
                       "tool_input": {"prompt": "x", "subagent_type": t}}
            r = _models(["hook"], env, ws, input=json.dumps(payload))
            return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "allow"
        check("[model-policy] hook: an agent definition pinning a dearer model is denied", hook_type("pricey") == "deny", "")
        check("[model-policy] hook: `model: inherit` is allowed", hook_type("plain") == "allow", "")
        check("[model-policy] hook: a built-in type with no definition file is allowed", hook_type("general-purpose") == "allow", "")
        transcript.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5-5"}}) + "\n"
                              + json.dumps({"type": "assistant", "isSidechain": True, "message": {"model": "claude-opus-5-5"}}) + "\n")
        check("[model-policy] hook: a subagent's sidechain turn never raises the lead (Sonnet lead, opus denied)",
              hook("opus")[1] == "deny", "")
    src = VIBE.read_text()
    check("[model-policy] launcher registers the hook on Agent|Task",
          '"matcher": "Agent|Task"' in src and "/usr/local/bin/vibe-models hook" in src, "")
    dockerfile = (REPO / "devcontainer/Dockerfile").read_text()
    check("[model-policy] image installs vibe-models beside vibe-delegate, with the CLI symlink",
          "COPY --chown=root:root vibe-models.mjs /usr/local/bin/vibe-models.mjs" in dockerfile
          and "ln -sf vibe-models.mjs /usr/local/bin/vibe-models" in dockerfile, "")


def test_model_policy_supervisor_pins_run_model():
    print("\n[model-policy] supervised runs name their model on start, every resume and every turn")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, codex_home, workspace, env = sup._supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"; prompt.write_text("/vsss go")
        stub1 = sup._write_stub(tmp / "stub1", {"turns": [{"events": [
            sup._turn_started_event(), sup._agent_message_event("i1", "no exit line here"),
            sup._turn_completed_event("completed")]}]})
        r = sup._run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                                 "--codex-bin", str(stub1), "--max-turns", "1", "--model", "gpt-6-luna"], env)
        msgs = sup._in_messages(tmp / "stub1")
        starts = [m for m in msgs if m.get("method") == "thread/start"]
        turns = [m for m in msgs if m.get("method") == "turn/start"]
        state = sup._read_state(workspace)
        check("[model-policy] --model wins over config.toml, recorded in state",
              r.returncode == 3 and state.get("model") == "gpt-6-luna", f"rc={r.returncode} {state.get('model')} {r.stderr}")
        check("[model-policy] thread/start and turn/start both carry the run model",
              starts and starts[0]["params"].get("model") == "gpt-6-luna"
              and turns and all(t["params"].get("model") == "gpt-6-luna" for t in turns), str(starts + turns))

        def resume(stub_name):
            stub = sup._write_stub(tmp / stub_name, {"threadId": state["threadId"],
                                                     "turns": [{"events": sup._DONE_TURN_EVENTS("i2", "done")}]})
            rr = sup._run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                                      "--codex-bin", str(stub), "--max-turns", "5"], env)
            m = sup._in_messages(tmp / stub_name)
            return rr, [x for x in m if x.get("method") == "thread/resume"], [x for x in m if x.get("method") == "turn/start"]

        snapshot = (workspace / ".vss/codex-supervisor.json").read_text()
        rr, res, ts = resume("stub2")
        check("[model-policy] resume keeps the recorded run model, not the thread's or config's",
              rr.returncode == 0 and res and res[0]["params"].get("model") == "gpt-6-luna"
              and ts and all(t["params"].get("model") == "gpt-6-luna" for t in ts), rr.stderr + str(res + ts))

        legacy = json.loads(snapshot); legacy.pop("model", None)
        (workspace / ".vss/codex-supervisor.json").write_text(json.dumps(legacy))
        rr, res, ts = resume("stub3")
        check("[model-policy] a pre-policy checkpoint resumes on the user's Codex default, never the old thread's model",
              rr.returncode == 0 and res and res[0]["params"].get("model") == "gpt-6.1-sol"
              and sup._read_state(workspace).get("model") == "gpt-6.1-sol", rr.stderr + str(res))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _, codex_home, workspace, env = sup._supervisor_fixture(tmp)
        (codex_home / "config.toml").write_text("[profiles.x]\nmodel = \"gpt-6-astra\"\n")
        prompt = tmp / "prompt.txt"; prompt.write_text("/vsss go")
        stub = sup._write_stub(tmp / "stub", {"turns": [{"events": sup._DONE_TURN_EVENTS("i1", "done")}]})
        r = sup._run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt), "--codex-bin", str(stub)], env)
        check("[model-policy] no --model, no recorded model, no top-level default: refused before any server",
              r.returncode != 0 and "no model for this run" in r.stderr and not sup._in_messages(tmp / "stub"), r.stderr)


def test_launcher_remote_control_default_on():
    print("\n[remote] remote control is on by default for Claude and Codex; VIBE_REMOTE=0 turns it off")
    def call(env, fn):
        r = _source_vibe_call(env, fn)
        return r.stdout.strip(), r
    out, r = call({}, "build_claude_remote_args")
    check("[remote] Claude: --remote-control by default", out == "--remote-control", r.stderr)
    for off in ("0", "off", "no", "false"):
        out, r = call({"VIBE_REMOTE": off}, "build_claude_remote_args")
        check(f"[remote] Claude: VIBE_REMOTE={off} turns it off", out == "", r.stderr)
    out, r = call({}, "codex_remote_on && echo on || echo off")
    check("[remote] Codex: on by default", out == "on", r.stderr)
    out, r = call({"VIBE_REMOTE": "0"}, "codex_remote_on && echo on || echo off")
    check("[remote] Codex: VIBE_REMOTE=0 turns it off", out == "off", r.stderr)
    out, r = call({"VIBE_CODEX_REMOTE": "0"}, "codex_remote_on && echo on || echo off")
    check("[remote] Codex: the older VIBE_CODEX_REMOTE=0 still turns it off", out == "off", r.stderr)
    out, r = call({"VIBE_CODEX_REMOTE": "0"}, "build_claude_remote_args")
    check("[remote] VIBE_CODEX_REMOTE=0 leaves Claude's remote control alone", out == "--remote-control", r.stderr)
    src = VIBE.read_text()
    check("[remote] launch_claude places the flag before --permission-mode (its optional name arg stays empty)",
          "${CLAUDE_REMOTE_ARGS:+$CLAUDE_REMOTE_ARGS }--permission-mode bypassPermissions" in src, "")
