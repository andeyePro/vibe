"""task_050: `codex-panel run --n <N> [--verify] [--out <dir>]` — N independent
tool-less `codex exec` reviewers for `/vs --panel` under Codex (plan item 8).
Tester-authored, independent read of `.vs/spec.md` end-to-end; no generator
report/diff/scratch-tests consulted.

Covers every AC7 assertion: AC1 exit codes with exact vendor-process counts;
AC2 ordered ship/verify argv pin against `vibe-delegate.mjs review codex`'s
own recorded golden (via checks_17's `_delegate_fixture`/`_delegate_call`,
never modified) plus distinct/cleaned-up cwds; AC3 blind stdin (instruction +
`PANEL-NONCE:` + diff, no sibling's nonce) and concurrency overlap; AC4
collection JSON shape, schema/semantic failure -> `{k, error}` excluded from
the tally, exit 1 for an incomplete panel; AC5 verify-mode `thread_id`
recording and all four `nonce_check` outcomes, `retention` field; AC6 doc
strings; no writes under the repo; env never forwards secrets.

This file installs its OWN `codex` stub (distinct from checks_17's
`_delegate_fixture` stub, which is imported read-only for the golden-argv
capture only): it additionally records start/end timestamps and a stable
per-call arrival index, sleeps 0.5s per `exec` call, and — in verify
scenarios — writes a fake rollout file under `$CODEX_HOME/sessions/...`
using the nonces the fixture dictates, so the panel's OWN rollout-search and
nonce-proof logic runs against real files on disk.

review-fixes-2026-09-12 wave 1, items 13-18 (codex-supervisor.mjs) and 19
(codex-panel.mjs): per the dispatch's explicit override of the brief's file
list, ALL SEVEN regression tests for this wave live in THIS file (not split
across checks_21_codex_supervisor_c2.py) — reusing checks_19's real stub
app-server, fixture and invocation helpers read-only, never modifying them.
"""
import shutil
import signal
import time

from smoke._core import *  # noqa: F401,F403
from smoke._core import _isolate_extras_env
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call, _codex_git_ws
from smoke.checks_19_codex_supervisor import (
    SUPERVISOR,
    _DONE_TURN_EVENTS,
    _in_messages,
    _read_state,
    _run_supervisor,
    _stub_log_lines,
    _supervisor_fixture,
    _turn_completed_event,
    _turn_started_event,
    _write_stub,
)

CODEX_PANEL = REPO / "devcontainer" / "codex-panel.mjs"
CODEX_INTEGRATION_PLAN_MD = REPO / "docs" / "codex-integration-plan.md"

HAS_ZSTD = shutil.which("zstd") is not None

# The literal rollout template from the spec/task summary, with the FIXED
# date the task pins (independent of any real "today"): the panel's own
# glob (`sessions/*/*/*/rollout-*-<thread_id>...`) matches any Y/M/D, so a
# fixed literal date exercises the real path shape without coupling the test
# to the calendar.
ROLLOUT_YMD = ("2026", "09", "11")
ROLLOUT_STAMP = "2026-09-11T12-00-00"

# ── the panel's own stub: records argv/stdin/env/cwd/timestamps, sleeps
# 0.5s per `exec` call, and writes fake rollouts from fixture.json ─────────
_PANEL_STUB_SRC = r'''
import json, os, re, subprocess, sys, time, uuid
from pathlib import Path

home = Path(os.environ["HOME"])
fixture = json.loads((home / "fixture.json").read_text())
args = sys.argv[1:]
data = sys.stdin.read()


def record(extra):
    payload = {"args": args, "input": data, "cwd": os.getcwd(), "env": dict(os.environ)}
    payload.update(extra)
    (home / "calls" / (uuid.uuid4().hex + ".json")).write_text(json.dumps(payload))


def next_idx():
    d = home / "exec-order"
    i = 1
    while True:
        try:
            fd = os.open(str(d / str(i)), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return i
        except FileExistsError:
            i += 1


if args == ["--version"]:
    t = time.time()
    record({"start": t, "end": t, "kind": "version"})
    print(fixture.get("version", "codex-cli 0.154.0"))
    sys.exit(0)

if args[:1] == ["-c"] and "login" in args and "status" in args:
    t = time.time()
    record({"start": t, "end": t, "kind": "login"})
    print(fixture.get("login", "Logged in using ChatGPT"), file=sys.stderr)
    sys.exit(fixture.get("login_exit", 0))

if args[:1] == ["exec"]:
    m = re.search(r"PANEL-NONCE:\s*([0-9a-f]{32})", data)
    own_nonce = m.group(1) if m else None
    idx = next_idx()
    if own_nonce:
        with (home / "nonces-seen.log").open("a") as f:
            f.write(f"{idx} {own_nonce}\n")
    start = time.time()
    time.sleep(0.5)
    bad = fixture.get("bad_indices", {}).get(str(idx))
    thread_id = f"th{idx}{own_nonce or 'none'}"
    exitcode = 0
    events_out = []
    if bad == "exit_nonzero":
        exitcode = 1
    else:
        schema_path = args[args.index("--output-schema") + 1]
        output_path = args[args.index("--output-last-message") + 1]
        good_answer = fixture.get("answer_good", {"verdict": "PASS", "summary": "ok", "findings": []})
        if bad == "schema":
            answer = {"bad": "shape"}
        elif bad == "pass_blocking":
            answer = {"verdict": "PASS", "summary": "ok", "findings": [
                {"severity": "BLOCKING", "file": "f.py", "line": 1, "message": "x"}]}
        else:
            answer = good_answer
        Path(output_path).write_text(json.dumps(answer))
        events_out = [
            {"type": "thread.started", "thread_id": thread_id},
            {"type": "turn.completed", "usage": {
                "input_tokens": 5000, "cached_input_tokens": 1000, "output_tokens": 44}},
        ]
    end = time.time()
    record({"start": start, "end": end, "kind": "exec", "idx": idx,
             "nonce": own_nonce, "thread_id": thread_id})

    if fixture.get("verify") and own_nonce:
        mode = fixture.get("rollout_modes", {}).get(str(idx), "own-only")
        sessions_dir = Path(os.environ["CODEX_HOME"]) / "sessions" / "/".join(fixture["ymd"])
        sessions_dir.mkdir(parents=True, exist_ok=True)
        if mode != "none":
            foreign_nonce = None
            if mode == "foreign":
                for line in (home / "nonces-seen.log").read_text().splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[0] != str(idx):
                        foreign_nonce = parts[1]
                        break
            lines = [f"PANEL-NONCE: {own_nonce}"]
            if foreign_nonce:
                lines.append(f"PANEL-NONCE: {foreign_nonce}")
            content = "\n".join(lines) + "\n"
            stamp = fixture["stamp"]
            if mode == "compressed":
                tmp = sessions_dir / f"rollout-{stamp}-{thread_id}.jsonl.tmp"
                tmp.write_text(content)
                zst = sessions_dir / f"rollout-{stamp}-{thread_id}.jsonl.zst"
                subprocess.run(["zstd", "-q", "-f", "-o", str(zst), str(tmp)], check=False)
                tmp.unlink(missing_ok=True)
            elif mode == "rollout_id_variant":
                (sessions_dir / f"rollout-{stamp}-{thread_id}_rev1.jsonl").write_text(content)
            else:
                (sessions_dir / f"rollout-{stamp}-{thread_id}.jsonl").write_text(content)

    if exitcode:
        print("STUB_EXEC_FAILURE", file=sys.stderr)
        sys.exit(exitcode)
    for e in events_out:
        print(json.dumps(e))
    sys.exit(0)

t = time.time()
record({"start": t, "end": t, "kind": "unknown"})
sys.exit(1)
'''


def _panel_fixture(root):
    """A throwaway git workspace + fake CODEX_HOME + PATH-shimmed `codex`
    stub, matching checks_17's `_delegate_fixture` recipe but with the
    panel's own richer stub (timestamps, arrival order, fake rollouts)."""
    home = root / "home"
    home.mkdir()
    (home / ".codex").mkdir()
    bins = root / "bin"
    bins.mkdir()
    ws = _codex_git_ws(root, "workspace")
    env = _isolate_extras_env({**os.environ, "HOME": str(home),
        "PATH": str(bins) + os.pathsep + os.environ["PATH"]})
    stub = bins / "codex"
    stub.write_text(f"#!{sys.executable}\n" + _PANEL_STUB_SRC)
    stub.chmod(0o755)
    (home / "fixture.json").write_text("{}")
    (home / "calls").mkdir()
    (home / "nonces-seen.log").write_text("")
    (home / "exec-order").mkdir()
    return ws, home, env


def _panel_call(workspace, home, env, args, fixture=None, diff="A reviewable diff\n", cwd=None):
    full_fixture = {"ymd": list(ROLLOUT_YMD), "stamp": ROLLOUT_STAMP, **(fixture or {})}
    (home / "fixture.json").write_text(json.dumps(full_fixture))
    shutil.rmtree(home / "calls", ignore_errors=True)
    (home / "calls").mkdir()
    (home / "nonces-seen.log").write_text("")
    shutil.rmtree(home / "exec-order", ignore_errors=True)
    (home / "exec-order").mkdir()
    result = run(["node", str(CODEX_PANEL), *args], cwd=cwd or workspace, env=env, input=diff)
    calls = [json.loads(p.read_text()) for p in sorted((home / "calls").glob("*.json"))]
    return result, calls


def _normalize_scratch_paths(argv):
    """Both the delegate and the panel mkdtemp their OWN private scratch dir
    per process, so `--output-schema`/`--output-last-message`'s VALUES can
    never be byte-identical between the two golden captures. Normalise just
    those two values to a fixed placeholder so the comparison is exactly
    what AC2 asks for: same flags, same order, same count, same values
    everywhere else."""
    out = list(argv)
    for flag in ("--output-schema", "--output-last-message"):
        if flag in out:
            out[out.index(flag) + 1] = "<SCRATCH_PATH>"
    return out


def _execs(calls):
    return [c for c in calls if c.get("kind") == "exec"]


def _probes(calls):
    return [c for c in calls if c.get("kind") in ("version", "login")]


# ── AC1: exit codes with exact vendor-process counts ────────────────────

def test_codex_panel_usage_exit2_zero_calls():
    print("\n[codex-panel] AC1: usage errors (exit 2), zero vendor processes")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)

        for label, args in [
            ("missing --n", ["run"]),
            ("non-numeric --n", ["run", "--n", "three"]),
            ("--n below floor", ["run", "--n", "1"]),
            ("--n above ceiling", ["run", "--n", "6"]),
        ]:
            r, calls = _panel_call(ws, home, env, args)
            check(f"[codex-panel] {label}: exit 2, zero calls",
                  r.returncode == 2 and not calls, f"rc={r.returncode} calls={calls} stderr={r.stderr}")

        r, calls = _panel_call(ws, home, env, ["run", "--n", "2"], diff="")
        check("[codex-panel] empty stdin: exit 2, zero calls",
              r.returncode == 2 and not calls, f"rc={r.returncode} stderr={r.stderr}")

        oversized = "x" * (8 * 1024 * 1024 + 10)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2"], diff=oversized)
        check("[codex-panel] oversized stdin (>8MiB): exit 2, zero calls",
              r.returncode == 2 and not calls, f"rc={r.returncode} stderr={r.stderr}")

        r, calls = _panel_call(ws, home, env, ["run", "--n", "2"], cwd=home)
        check("[codex-panel] outside a git work tree: exit 2, zero calls",
              r.returncode == 2 and not calls, f"rc={r.returncode} stderr={r.stderr}")

        policy = ws / ".vibe" / "review-slots"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text("codex=off\n")
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2"])
        check("[codex-panel] .vibe/review-slots codex=off: exit 2, zero calls",
              r.returncode == 2 and not calls, f"rc={r.returncode} stderr={r.stderr}")
        policy.unlink()


def test_codex_panel_readiness_failure_exactly_two_probes():
    print("\n[codex-panel] AC1: readiness failure -> exit 1 after exactly 2 probe calls")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)

        for label, fixture in [
            ("old CLI version", {"version": "codex-cli 0.153.4"}),
            ("login probe fails", {"login_exit": 1}),
        ]:
            r, calls = _panel_call(ws, home, env, ["run", "--n", "2"], fixture=fixture)
            check(f"[codex-panel] {label}: exit 1", r.returncode == 1, r.stderr)
            check(f"[codex-panel] {label}: exactly 2 probe calls, no reviewer spawned",
                  len(_probes(calls)) == 2 and not _execs(calls), str(calls))


def test_codex_panel_complete_run_exactly_2_plus_n():
    print("\n[codex-panel] AC1: complete run -> exit 0, exactly 2 + N codex processes")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        for n in (2, 3, 5):
            r, calls = _panel_call(ws, home, env, ["run", "--n", str(n)])
            check(f"[codex-panel] n={n}: exit 0", r.returncode == 0, r.stderr)
            check(f"[codex-panel] n={n}: exactly 2 + N ({2 + n}) codex processes",
                  len(calls) == 2 + n and len(_probes(calls)) == 2 and len(_execs(calls)) == n,
                  str(calls))


def test_codex_panel_incomplete_panel_exit1():
    print("\n[codex-panel] AC1/AC4: incomplete panel (schema/semantic failure) -> exit 1")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)

        for label, bad_mode in [("schema violation", "schema"), ("PASS with BLOCKING", "pass_blocking")]:
            r, calls = _panel_call(ws, home, env, ["run", "--n", "2"],
                                    fixture={"bad_indices": {"1": bad_mode}})
            check(f"[codex-panel] {label}: exit 1", r.returncode == 1, r.stderr)
            if r.returncode != 1:
                continue
            report = json.loads(r.stdout)
            errored = [rv for rv in report["reviewers"] if "error" in rv]
            ok = [rv for rv in report["reviewers"] if "error" not in rv]
            check(f"[codex-panel] {label}: exactly one reviewer errored, one succeeded",
                  len(errored) == 1 and len(ok) == 1, json.dumps(report))
            check(f"[codex-panel] {label}: error entry is exactly {{k, error}}",
                  errored and set(errored[0].keys()) == {"k", "error"}, str(errored))
            check(f"[codex-panel] {label}: errored reviewer excluded from tally",
                  sum(report["tally"].values()) == 1, json.dumps(report["tally"]))


# ── AC2: argv pin against the delegate's own recorded golden ────────────

def test_codex_panel_argv_pin_against_delegate_golden():
    print("\n[codex-panel] AC2: ship/verify argv pinned against the delegate's recorded golden")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        droot = root / "delegate"; droot.mkdir()
        proot = root / "panel"; proot.mkdir()

        # Golden: vibe-delegate.mjs's OWN stub, unmodified (checks_17).
        dws, dhome, denv = _delegate_fixture(droot)
        good = {"verdict": "PASS", "summary": "ok", "findings": []}
        r, dcalls = _delegate_call(dws, dhome, denv, ["review", "codex"], {"answer": good}, payload="diff\n")
        check("[codex-panel] delegate golden call succeeds (version probe, login probe, exec)",
              r.returncode == 0 and len(dcalls) == 3, r.stderr)
        if r.returncode != 0:
            return
        golden = _normalize_scratch_paths(dcalls[-1]["args"])
        check("[codex-panel] golden carries exactly one --ephemeral",
              golden.count("--ephemeral") == 1, str(golden))

        # Panel's own stub, ship mode.
        pws, phome, penv = _panel_fixture(proot)
        r, calls = _panel_call(pws, phome, penv, ["run", "--n", "2"])
        check("[codex-panel] ship-mode run succeeds", r.returncode == 0, r.stderr)
        execs = _execs(calls)
        check("[codex-panel] ship-mode: N reviewer argvs recorded", len(execs) == 2, str(len(execs)))
        for c in execs:
            check("[codex-panel] ship-mode argv EQUALS the delegate golden exactly",
                  _normalize_scratch_paths(c["args"]) == golden, str(c["args"]))

        # Panel's own stub, verify mode.
        r, calls = _panel_call(pws, phome, penv, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True, "rollout_modes": {"1": "own-only", "2": "own-only"}})
        execs = _execs(calls)
        expected_verify = [a for a in golden if a != "--ephemeral"]
        for c in execs:
            check("[codex-panel] verify-mode argv EQUALS golden minus the single --ephemeral",
                  _normalize_scratch_paths(c["args"]) == expected_verify, str(c["args"]))


def test_codex_panel_cwds_distinct_outside_repo_and_removed():
    print("\n[codex-panel] AC2: N distinct private temp cwds outside the repo, removed after")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "3"])
        check("[codex-panel] run succeeds", r.returncode == 0, r.stderr)
        execs = _execs(calls)
        cwds = [c["cwd"] for c in execs]
        check("[codex-panel] 3 distinct cwds", len(set(cwds)) == 3, str(cwds))
        check("[codex-panel] no cwd is inside the repo workspace",
              all(not Path(c).is_relative_to(ws) for c in cwds), str(cwds))
        check("[codex-panel] all reviewer cwds removed after the run",
              all(not Path(c).exists() for c in cwds), str(cwds))


# ── AC3: blind stdin + concurrency ───────────────────────────────────────

def test_codex_panel_stdin_isolation():
    print("\n[codex-panel] AC3: stdin = instruction + PANEL-NONCE + diff; no sibling's nonce")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        diff_text = "diff --git a/x b/x\n+added line\n"
        r, calls = _panel_call(ws, home, env, ["run", "--n", "3"], diff=diff_text)
        check("[codex-panel] run succeeds", r.returncode == 0, r.stderr)
        execs = _execs(calls)
        nonces = [c["nonce"] for c in execs]
        check("[codex-panel] 3 distinct 32-hex nonces",
              len(set(nonces)) == 3 and all(re.fullmatch(r"[0-9a-f]{32}", n) for n in nonces), str(nonces))
        for c in execs:
            own = c["nonce"]
            check("[codex-panel] stdin carries a PANEL-NONCE line with the reviewer's own nonce",
                  f"PANEL-NONCE: {own}" in c["input"], c["input"][:200])
            check("[codex-panel] stdin carries the diff", diff_text in c["input"], c["input"][-200:])
            others = [n for n in nonces if n != own]
            check("[codex-panel] stdin carries NO other reviewer's nonce",
                  all(o not in c["input"] for o in others), "")


def test_codex_panel_concurrency_overlap():
    print("\n[codex-panel] AC3: reviewers overlap (every start precedes every end)")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "4"])
        check("[codex-panel] run succeeds", r.returncode == 0, r.stderr)
        execs = _execs(calls)
        starts = [c["start"] for c in execs]
        ends = [c["end"] for c in execs]
        check("[codex-panel] every reviewer sleeps ~0.5s",
              all(e - s >= 0.45 for s, e in zip(starts, ends)), str(list(zip(starts, ends))))
        check("[codex-panel] true overlap: latest start precedes earliest end",
              max(starts) < min(ends), f"starts={starts} ends={ends}")


# ── AC4: collection shape ────────────────────────────────────────────────

def test_codex_panel_collection_shape_and_tally():
    print("\n[codex-panel] AC4: stdout JSON shape and tally")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "3"])
        check("[codex-panel] run succeeds", r.returncode == 0, r.stderr)
        report = json.loads(r.stdout)
        check("[codex-panel] top-level shape",
              report["n"] == 3 and report["mode"] == "ship" and
              isinstance(report["reviewers"], list) and isinstance(report["tally"], dict), r.stdout)
        check("[codex-panel] no retention field in ship mode", "retention" not in report, r.stdout)
        for rv in report["reviewers"]:
            check("[codex-panel] each reviewer has the full field set",
                  set(rv.keys()) == {"k", "nonce", "thread_id", "verdict", "summary", "findings", "usage"},
                  str(rv))
        check("[codex-panel] tally sums to N and matches PASS count",
              report["tally"] == {"PASS": 3, "FAIL": 0, "SPLIT": 0}, str(report["tally"]))
        check("[codex-panel] stdout is exactly one JSON object (no extra output)",
              r.stdout.strip().count("\n") == 0, repr(r.stdout))


# ── AC5: verify mode — thread_id, rollout lookup, all nonce_check outcomes ──

def test_codex_panel_verify_own_only():
    print("\n[codex-panel] AC5: verify mode, both reviewers prove own-only, retention present")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True, "rollout_modes": {"1": "own-only", "2": "own-only"}})
        check("[codex-panel] own-only both: exit 0", r.returncode == 0, r.stderr)
        report = json.loads(r.stdout)
        check("[codex-panel] mode is verify", report["mode"] == "verify", r.stdout)
        check("[codex-panel] retention field present in verify mode",
              report.get("retention") == "rollouts kept under $CODEX_HOME/sessions", r.stdout)
        for rv in report["reviewers"]:
            check("[codex-panel] thread_id recorded", isinstance(rv.get("thread_id"), str) and rv["thread_id"], str(rv))
            check("[codex-panel] nonce_check == own-only", rv.get("nonce_check") == "own-only", str(rv))


def test_codex_panel_verify_foreign_nonce_found():
    print("\n[codex-panel] AC5: verify mode, one reviewer's rollout carries a sibling's nonce")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True, "rollout_modes": {"1": "own-only", "2": "foreign"}})
        check("[codex-panel] foreign nonce present: exit 1", r.returncode == 1, r.stderr)
        report = json.loads(r.stdout)
        checks = {rv["nonce"]: rv.get("nonce_check") for rv in report["reviewers"] if "error" not in rv}
        check("[codex-panel] one reviewer sees foreign-nonce-found, the other own-only",
              sorted(checks.values()) == ["foreign-nonce-found", "own-only"], str(checks))


def test_codex_panel_verify_rollout_not_found():
    print("\n[codex-panel] AC5: verify mode, one reviewer's rollout never written")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True, "rollout_modes": {"1": "own-only", "2": "none"}})
        check("[codex-panel] rollout missing: exit 1", r.returncode == 1, r.stderr)
        report = json.loads(r.stdout)
        checks = {rv["nonce"]: rv.get("nonce_check") for rv in report["reviewers"] if "error" not in rv}
        check("[codex-panel] one reviewer sees rollout-not-found, the other own-only",
              sorted(checks.values()) == ["own-only", "rollout-not-found"], str(checks))


def test_codex_panel_verify_rollout_id_variant():
    print("\n[codex-panel] AC5: verify mode, the <thread_id>_<rollout_id> filename variant matches")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True,
                                         "rollout_modes": {"1": "rollout_id_variant", "2": "own-only"}})
        check("[codex-panel] rollout_id variant: exit 0", r.returncode == 0, r.stderr)
        report = json.loads(r.stdout)
        check("[codex-panel] every reviewer resolves own-only via the _<rollout_id> filename too",
              all(rv.get("nonce_check") == "own-only" for rv in report["reviewers"]), json.dumps(report))


def test_codex_panel_verify_compressed_rollout():
    print("\n[codex-panel] AC5: verify mode, .jsonl.zst-only rollout")
    if not HAS_ZSTD:
        check("[codex-panel] compressed-rollout case skipped: zstd not installed on this host", True)
        return
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                                fixture={"verify": True,
                                         "rollout_modes": {"1": "compressed", "2": "own-only"}})
        check("[codex-panel] compressed rollout: exit 0", r.returncode == 0, r.stderr)
        report = json.loads(r.stdout)
        check("[codex-panel] compressed rollout decompresses to own-only",
              all(rv.get("nonce_check") == "own-only" for rv in report["reviewers"]), json.dumps(report))


# ── no writes under the repo; env never forwards secrets ────────────────

def _list_tree(base):
    return sorted(str(p.relative_to(base)) for p in base.rglob("*"))


def test_codex_panel_no_writes_under_repo():
    print("\n[codex-panel] no files are ever written under the reviewed repo")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        before = _list_tree(ws)
        r, _ = _panel_call(ws, home, env, ["run", "--n", "2"])
        check("[codex-panel] ship run succeeds", r.returncode == 0, r.stderr)
        after = _list_tree(ws)
        check("[codex-panel] repo tree unchanged after a ship run", before == after,
              f"before={before} after={after}")
        r, _ = _panel_call(ws, home, env, ["run", "--n", "2", "--verify"],
                            fixture={"verify": True, "rollout_modes": {"1": "own-only", "2": "own-only"}})
        after_verify = _list_tree(ws)
        check("[codex-panel] repo tree unchanged after a verify run", before == after_verify,
              f"before={before} after={after_verify}")


def test_codex_panel_env_never_forwards_secrets():
    print("\n[codex-panel] env never forwards non-Codex credentials")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        env = dict(env)
        env.update({k: "DO_NOT_FORWARD" for k in (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
            "GEMINI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE")})
        r, calls = _panel_call(ws, home, env, ["run", "--n", "2"])
        check("[codex-panel] run succeeds", r.returncode == 0, r.stderr)
        check("[codex-panel] DO_NOT_FORWARD never reaches a vendor process",
              "DO_NOT_FORWARD" not in json.dumps(calls), "")
        for c in calls:
            check("[codex-panel] child env is exactly PATH/HOME/CODEX_HOME/LANG",
                  set(c["env"].keys()) == {"PATH", "HOME", "CODEX_HOME", "LANG"}, str(sorted(c["env"].keys())))


# ── AC6: docs ─────────────────────────────────────────────────────────────

def test_codex_panel_docs_strings():
    print("\n[codex-panel] AC6: doc strings in vs.md, README, and the plan's D6")
    vs_md = VS_MD.read_text()
    check("[codex-panel] vs.md names `codex-panel run --n`", "codex-panel run --n" in vs_md, "")
    check("[codex-panel] vs.md § Step 5c gets a Running under Codex note",
          "Running under Codex" in vs_md, "")

    readme = README_MD.read_text()
    check("[codex-panel] README names codex-panel", "codex-panel" in readme, "")

    plan = CODEX_INTEGRATION_PLAN_MD.read_text()
    m = re.search(r"- D6 .*?(?=\n- D7 |\Z)", plan, re.DOTALL)
    check("[codex-panel] plan has a D6 item", m is not None, "")
    if m:
        check("[codex-panel] plan's D6 names codex-panel.mjs and the rollout- template",
              "codex-panel.mjs" in m.group(0) and "rollout-" in m.group(0), m.group(0)[:400])


def test_codex_panel_dockerfile_copy_and_chmod():
    print("\n[codex-panel] Dockerfile: COPY --chown=root:root and chmod +x for codex-panel")
    dockerfile = DOCKERFILE.read_text()
    check("[codex-panel] Dockerfile COPYs codex-panel.mjs with --chown=root:root",
          "COPY --chown=root:root codex-panel.mjs /usr/local/bin/codex-panel" in dockerfile, "")
    chmod_lines = [l for l in dockerfile.splitlines() if l.strip().startswith("RUN chmod +x")]
    check("[codex-panel] a chmod +x line includes /usr/local/bin/codex-panel",
          any("/usr/local/bin/codex-panel" in l for l in chmod_lines), "\n".join(chmod_lines))


# ═══════════════════════════════════════════════════════════════════════
# review-fixes-2026-09-12 wave 1, items 13-18: devcontainer/codex-supervisor.mjs
#
# Drives the REAL supervisor through checks_19's stub app-server, fixture and
# invocation helpers (imported read-only, never modified). Time-dependent
# cases (14, 16) use --now-source / a pure-function call instead of the real
# clock; item 17's bounded drain is a short REAL-wall-time grace window
# (2s), so its tests use real sleeps in the stub script, well inside the
# communicate() timeouts below.
# ═══════════════════════════════════════════════════════════════════════

def test_codex_supervisor_review13_exit_code_never_a_string():
    print("\n[codex-supervisor] review item 13: a raw fs error's string .code never reaches "
          "process.exit (ENOENT --prompt-file exits cleanly, no ERR_INVALID_ARG_TYPE crash)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        missing_prompt = tmp / "does-not-exist.txt"
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(missing_prompt),
                              "--codex-bin", "/bin/true"], env)
        check("[codex-supervisor] missing --prompt-file exits 1 (EXIT_FAIL), not a Node crash code",
              r.returncode == 1, f"rc={r.returncode} stderr={r.stderr}")
        check("[codex-supervisor] stderr is the clean ENOENT message, never a process.exit crash trace",
              "ENOENT" in r.stderr and "ERR_INVALID_ARG_TYPE" not in r.stderr and "TypeError" not in r.stderr,
              r.stderr)


def test_codex_supervisor_review14_stale_resets_at_reread_and_floor():
    print("\n[codex-supervisor] review item 14: a resetsAt already in the past is re-read, "
          "never trusted as a zero-second wait")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go review14")
        stub_dir = tmp / "stub"
        now_source = tmp / "now.txt"
        T0 = 1700000000
        now_source.write_text(str(T0))
        fixture = {
            "rateLimits": [{"primary": {"usedPercent": 100, "windowDurationMins": 300,
                                         "resetsAt": T0 - 500}, "secondary": None}],
            "turns": [
                {"events": [_turn_started_event(),
                            _turn_completed_event("failed", {"message": "usage limit hit",
                                                              "codexErrorInfo": "usageLimitExceeded"})]},
                {"events": _DONE_TURN_EVENTS("i2", "done")},
            ],
        }
        stub_path = _write_stub(stub_dir, fixture)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path), "--now-source", str(now_source)], env)
        check("[codex-supervisor] stale-resetsAt run exits 0", r.returncode == 0, r.stderr)
        state = _read_state(workspace)
        waits = state.get("waits", [])
        check("[codex-supervisor] exactly one wait recorded, quota, floored to 30s (never 0)",
              len(waits) == 1 and waits[0].get("reason") == "quota" and waits[0].get("seconds") == 30,
              str(waits))
        msgs = _in_messages(stub_dir)
        rl_reads = [m for m in msgs if m.get("method") == "account/rateLimits/read"]
        check("[codex-supervisor] the stale reading triggers a fresh account/rateLimits/read "
              "beyond just the initial startup read",
              len(rl_reads) > 1, str(rl_reads))


def test_codex_supervisor_review15_sighup_cooperative_stop():
    print("\n[codex-supervisor] review item 15: SIGHUP is a cooperative-stop signal, not a silent "
          "kill (checkpoint saved, lock released, exit 130)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go review15")
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [
            _turn_started_event(), {"sleep": 6}, _turn_completed_event("completed")]}]}
        stub_path = _write_stub(stub_dir, fixture)
        proc = subprocess.Popen(
            ["node", str(SUPERVISOR), "run", "--cwd", str(workspace), "--prompt-file", str(prompt),
             "--codex-bin", str(stub_path)],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.time() + 15
        saw_turn_start = False
        while time.time() < deadline:
            log_text = "\n".join(_stub_log_lines(stub_dir)).replace(" ", "")
            if ('"method":"turn/start"' in log_text
                    and (_read_state(workspace).get("unresolvedTurn") or {}).get("turnId")):
                saw_turn_start = True
                break
            time.sleep(0.1)
        check("[codex-supervisor] review15: reached turn/start before the signal", saw_turn_start, "")

        proc.send_signal(signal.SIGHUP)
        try:
            _, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        check("[codex-supervisor] SIGHUP exits 130 (cooperative stop), not killed by the OS default",
              proc.returncode == 130, f"rc={proc.returncode} stderr={stderr}")
        lock_path = workspace / ".vss" / "codex-supervisor.json.lock"
        check("[codex-supervisor] SIGHUP releases the ownership lock (no stale lock left behind)",
              not lock_path.exists(), "")
        state = _read_state(workspace)
        check("[codex-supervisor] SIGHUP checkpoint: state carries a recovery reason",
              state.get("recoveryReason") == "stop-requested", str(state))


def test_codex_supervisor_review16_binding_resets_at_prefers_soonest():
    print("\n[codex-supervisor] review item 16: bindingResetsAt prefers the SOONEST reset when no "
          "window is fully exhausted, and the LATEST when both are")
    script = (
        "import('" + SUPERVISOR.as_posix() + "').then(m => {"
        "const cases = ["
        "{primary: {usedPercent: 99, resetsAt: 5000}, secondary: {usedPercent: 40, resetsAt: 999999}},"
        "{primary: {usedPercent: 100, resetsAt: 100}, secondary: {usedPercent: 100, resetsAt: 200}},"
        "{primary: null, secondary: null},"
        "];"
        "console.log(JSON.stringify(cases.map(c => m.bindingResetsAt(c))));"
        "});"
    )
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                        stdin=subprocess.DEVNULL, timeout=30)
    check("[codex-supervisor] node import for bindingResetsAt succeeds", r.returncode == 0, r.stderr)
    if r.returncode != 0:
        return
    try:
        results = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        check("[codex-supervisor] bindingResetsAt output is valid JSON", False, f"{exc}: {r.stdout}")
        return
    if not check("[codex-supervisor] bindingResetsAt returned exactly 3 results", len(results) == 3, str(results)):
        return
    check("[codex-supervisor] near-100% window (99%) beats a far-future exhausted-looking secondary: "
          "picks the SOONEST reset, not the latest",
          results[0] == 5000, str(results))
    check("[codex-supervisor] both windows exhausted: picks the LATER of the two (unchanged behaviour)",
          results[1] == 200, str(results))
    check("[codex-supervisor] neither window has a known resetsAt: null",
          results[2] is None, str(results))


def test_codex_supervisor_review17_stop_mid_turn_drains_before_message():
    print("\n[codex-supervisor] review item 17: a cooperative stop mid-turn drains for the turn "
          "boundary before choosing the 'resume' vs 'reconcile' instruction")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        def run_scenario(label, sleep_s, status):
            sub = tmp / label
            sub.mkdir()
            home, codex_home, workspace, env = _supervisor_fixture(sub)
            prompt = sub / "prompt.txt"
            prompt.write_text(f"/vsss go {label}")
            stub_dir = sub / "stub"
            fixture = {"turns": [{"events": [
                _turn_started_event(), {"sleep": sleep_s}, _turn_completed_event(status)]}]}
            stub_path = _write_stub(stub_dir, fixture)
            proc = subprocess.Popen(
                ["node", str(SUPERVISOR), "run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                 "--codex-bin", str(stub_path)],
                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            deadline = time.time() + 15
            saw = False
            while time.time() < deadline:
                log_text = "\n".join(_stub_log_lines(stub_dir)).replace(" ", "")
                if ('"method":"turn/start"' in log_text
                        and (_read_state(workspace).get("unresolvedTurn") or {}).get("turnId")):
                    saw = True
                    break
                time.sleep(0.05)
            check(f"[codex-supervisor] review17 {label}: reached turn/start before the signal", saw, "")
            proc.send_signal(signal.SIGTERM)
            try:
                _, stderr = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate()
            check(f"[codex-supervisor] review17 {label}: exits 130", proc.returncode == 130,
                  f"rc={proc.returncode} stderr={stderr}")
            return stderr, _read_state(workspace)

        # Fast: the stub answers turn/completed(interrupted) at 0.5s, well
        # inside the 2s drain bound — the turn boundary IS reached.
        stderr_fast, state_fast = run_scenario("drained", 0.5, "interrupted")
        check("[codex-supervisor] review17 drained: message says RESUME (the boundary was confirmed)",
              "resume with the same run arguments" in stderr_fast, stderr_fast)
        check("[codex-supervisor] review17 drained: state has NO unresolved turn",
              state_fast.get("unresolvedTurn") is None, str(state_fast))

        # Slow: the stub does not answer within the 6s sleep — well past the
        # 2s drain bound — so the boundary is NEVER reached during the drain.
        stderr_slow, state_slow = run_scenario("notdrained", 6, "completed")
        check("[codex-supervisor] review17 not-drained: message says RECONCILE, never the bare "
              "resume instruction the state machine would refuse",
              "reconcile --state" in stderr_slow and "resume with the same run arguments" not in stderr_slow,
              stderr_slow)
        check("[codex-supervisor] review17 not-drained: state STILL has the unresolved turn "
              "(consistent with what the message says)",
              (state_slow.get("unresolvedTurn") or {}).get("turnId") is not None, str(state_slow))


def test_codex_supervisor_review18_interrupted_confirms_boundary():
    print("\n[codex-supervisor] review item 18: a spontaneously-interrupted turn confirms the "
          "boundary before throwing, and names the recovery reason correctly")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        home, codex_home, workspace, env = _supervisor_fixture(tmp)
        prompt = tmp / "prompt.txt"
        prompt.write_text("/vsss go review18")
        stub_dir = tmp / "stub"
        fixture = {"turns": [{"events": [_turn_started_event(), _turn_completed_event("interrupted")]}]}
        stub_path = _write_stub(stub_dir, fixture)
        r = _run_supervisor(["run", "--cwd", str(workspace), "--prompt-file", str(prompt),
                              "--codex-bin", str(stub_path)], env)
        check("[codex-supervisor] interrupted-turn run exits 1", r.returncode == 1, r.stderr)
        check("[codex-supervisor] stderr names the interruption",
              "turn interrupted by someone else" in r.stderr, r.stderr)
        state = _read_state(workspace)
        check("[codex-supervisor] the turn boundary IS confirmed (unresolvedTurn cleared)",
              state.get("unresolvedTurn") is None, str(state))
        check("[codex-supervisor] recoveryReason correctly names an interrupted turn",
              state.get("recoveryReason") == "turn-interrupted", str(state))


# ═══════════════════════════════════════════════════════════════════════
# review-fixes-2026-09-12 wave 1, item 19: devcontainer/codex-panel.mjs
#
# A CJS --require preload monkeypatches fs.mkdtempSync to succeed N times
# then throw — proven live (node --require + ESM named import DOES see a
# CJS-patched builtin in this Node) before being relied on here. Call order
# is: 1) main()'s own probeCwd mkdtemp, 2) reviewer 1's cwd, 3) reviewer 2's
# cwd — FAIL_AT=3 makes reviewer 1 the "already started" reviewer the fix
# must kill and clean up, exactly the scenario item 19 describes.
# ═══════════════════════════════════════════════════════════════════════

_MKDTEMP_FAIL_PRELOAD_SRC = r'''
const fs = require("fs");
const orig = fs.mkdtempSync;
const failAt = Number(process.env.PANEL_TEST_MKDTEMP_FAIL_AT || 0);
const logPath = process.env.PANEL_TEST_MKDTEMP_LOG;
let n = 0;
fs.mkdtempSync = function(...args) {
  n += 1;
  if (failAt && n >= failAt) {
    const err = new Error("injected mkdtemp failure (test)");
    err.code = "ENOSPC";
    throw err;
  }
  const dir = orig.apply(fs, args);
  if (logPath) fs.appendFileSync(logPath, dir + "\n");
  return dir;
};
'''


def test_codex_panel_review19_partial_startup_failure_cleans_up():
    print("\n[codex-panel] review item 19: a mid-startup mkdtempSync failure kills already-started "
          "reviewers and removes their temp dirs before rethrowing")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, home, env = _panel_fixture(root)
        preload = root / "mkdtemp-fail-preload.cjs"
        preload.write_text(_MKDTEMP_FAIL_PRELOAD_SRC)
        mkdtemp_log = root / "mkdtemp-created.log"
        test_env = dict(env)
        test_env["PANEL_TEST_MKDTEMP_FAIL_AT"] = "3"
        test_env["PANEL_TEST_MKDTEMP_LOG"] = str(mkdtemp_log)
        (home / "fixture.json").write_text(json.dumps({"ymd": list(ROLLOUT_YMD), "stamp": ROLLOUT_STAMP}))

        proc = subprocess.Popen(
            ["node", "--require", str(preload), str(CODEX_PANEL), "run", "--n", "3"],
            cwd=ws, env=test_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        try:
            _, stderr = proc.communicate(input="a reviewable diff\n", timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            check("[codex-panel] review19: partial-startup-failure run does not hang", False, "timed out")
            return
        check("[codex-panel] review19: exit 1, a clean thrown error, not a crash/hang",
              proc.returncode == 1, f"rc={proc.returncode} stderr={stderr}")
        check("[codex-panel] review19: stderr names the injected failure",
              "injected mkdtemp failure" in stderr, stderr)

        created = mkdtemp_log.read_text().splitlines() if mkdtemp_log.exists() else []
        reviewer_dirs = [d for d in created if "codex-panel-probe-" not in d]
        check("[codex-panel] review19: exactly one reviewer cwd was created before the failure",
              len(reviewer_dirs) == 1, str(created))
        if reviewer_dirs:
            check("[codex-panel] review19: the started reviewer's temp dir was removed (no leak)",
                  not Path(reviewer_dirs[0]).exists(), reviewer_dirs[0])
        calls = [json.loads(p.read_text()) for p in sorted((home / "calls").glob("*.json"))]
        check("[codex-panel] review19: the started reviewer's codex process was killed before it "
              "could record a completed exec call (never left running to finish)",
              not _execs(calls), str(calls))
