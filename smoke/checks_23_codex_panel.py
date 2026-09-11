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
"""
import shutil

from smoke._core import *  # noqa: F401,F403
from smoke._core import _isolate_extras_env
from smoke.checks_17_delegation import _delegate_fixture, _delegate_call, _codex_git_ws

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
