"""Three ways a running vibe session was ended out from under the user
(2026-09-25/26), each now closed:

1. Editing `vibe` while a launcher was running: bash reads a script as it runs
   it, so the launcher resumed at its old byte offset in the NEW file
   ("$3: unbound variable") and the /vsss auto-resume never relaunched. The
   main body is now one `{ … }` group, parsed whole before it runs.
2. The stall watchdog only knew the five_hour window. Two /vsss runs went
   quiet at a weekly limit while five_hour read 21%, and both were killed.
   The statusLine now records seven_day too, and a used-up week vetoes it.
3. A second launch of the same project saw image drift and recreated the
   container under a live session (rc=137, container=removing). A recreate now
   checks for live claude/codex sessions first.
"""
from smoke._core import *  # noqa: F401,F403

import os
import re
import subprocess
import tempfile
import time

_GUARD = '[ "${VIBE_SOURCE_ONLY:-}" = "1" ] && return 0 2>/dev/null'


def test_main_body_is_one_brace_group():
    print("\n[session-safety] the launcher's main body is parsed whole before it runs")
    lines = VIBE.read_text().splitlines()
    idx = [i for i, l in enumerate(lines) if l == _GUARD]
    check("[session-safety] exactly one VIBE_SOURCE_ONLY guard", len(idx) == 1, str(idx))
    if len(idx) != 1:
        return
    after = [l for l in lines[idx[0] + 1:] if l.strip() and not l.lstrip().startswith("#")]
    check("[session-safety] first statement after the guard opens a brace group",
          bool(after) and after[0] == "{", after[0] if after else "")
    check("[session-safety] the file's last line closes it", lines[-1] == "}", lines[-1])
    # Behaviour: a script shaped like this, rewritten mid-run, keeps running
    # what it parsed. Without the group, the same rewrite executes the new text.
    with tempfile.TemporaryDirectory() as td:
        for grouped, want in ((True, "OLD-TAIL"), (False, "NEW-TAIL")):
            s = Path(td) / f"s{int(grouped)}.sh"
            body = "sleep 1\necho OLD-TAIL\n"
            text = ("{\n" + body + "}\n") if grouped else body
            s.write_text(text)
            p = subprocess.Popen(["bash", str(s)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, text=True)
            time.sleep(0.4)
            # same length prefix, different tail: an in-place rewrite
            s.write_text(text.replace("echo OLD-TAIL", "echo NEW-TAIL"))
            out, _ = p.communicate(timeout=15)
            check(f"[session-safety] {'grouped' if grouped else 'ungrouped'} script runs {want} after a mid-run edit",
                  want in out, out)


def test_statusline_records_the_weekly_window():
    print("\n[session-safety] statusLine records the seven_day window beside five_hour")
    cmd = _statusline_command()
    check("[session-safety] statusLine command extracted", bool(cmd), "")
    if not cmd:
        return
    both = ('{"model":{"display_name":"Opus 4.8"},"rate_limits":{'
            '"five_hour":{"used_percentage":21,"resets_at":1790391600},'
            '"seven_day":{"used_percentage":100.0,"resets_at":1790600000.9}}}')
    with tempfile.TemporaryDirectory() as td:
        canary = Path(td) / "canary"
        bad = ('{"model":{"display_name":"Opus 4.8"},"rate_limits":{'
               '"five_hour":{"used_percentage":21},'
               '"seven_day":{"used_percentage":"$(touch ' + str(canary) + ')","resets_at":1}}}')
        env = {**os.environ, "VIBE_VSS_DIR": td}
        r = subprocess.run(["sh", "-c", cmd], input=both, env=env, capture_output=True,
                           text=True, timeout=15)
        check("[session-safety] display unchanged", r.returncode == 0 and r.stdout == "O · vibe · 5h 21%",
              f"rc={r.returncode} out=[{r.stdout}]")
        lines = (Path(td) / "rate-limit").read_text().splitlines()
        check("[session-safety] used7= and floored resets7= written after the five_hour lines",
              lines[1:] == ["used=21", "resets=1790391600", "used7=100", "resets7=1790600000"], str(lines))
        subprocess.run(["sh", "-c", cmd], input=bad, env=env, capture_output=True, text=True, timeout=15)
        lines = (Path(td) / "rate-limit").read_text().splitlines()
        check("[session-safety] a non-numeric seven_day reading is dropped",
              not any(l.startswith(("used7=", "resets7=")) for l in lines), str(lines))
        check("[session-safety] ... and never evaluated", not canary.exists())


def test_weekly_limit_vetoes_the_watchdog():
    print("\n[session-safety] auto_resume_native_wait: a used-up week counts as a native wait")
    snippet = (
        'r="${TMPDIR:-/tmp}/vibe-wk.$$"; now=1000000000; '
        't() { if auto_resume_native_wait "$r" "$now"; then echo "$1=[wait]"; else echo "$1=[no]"; fi; }; '
        "printf 'epoch=1\\nused=21\\nresets=1000010000\\nused7=100\\nresets7=1000300000\\n' > \"$r\"; t WEEKFULL; "
        "printf 'epoch=1\\nused=21\\nresets=1000010000\\nused7=60\\nresets7=1000300000\\n' > \"$r\"; t WEEKLOW; "
        "printf 'epoch=1\\nused=21\\nresets=1000010000\\nused7=97\\nresets7=1000300000\\n' > \"$r\"; t WEEKNEAR; "
        "printf 'epoch=1\\nused=21\\nused7=100\\nresets7=999990000\\n' > \"$r\"; t WEEKPAST; "
        "printf 'epoch=1\\nused=21\\nused7=100\\nresets7=1000700000\\n' > \"$r\"; t WEEKFAR; "
        "printf 'epoch=1\\nused=21\\nused7=100\\n' > \"$r\"; t WEEKNORESET; "
        "printf 'epoch=1\\nused=21\\nused7=100\\nresets7=08\\n' > \"$r\"; t WEEKOCTAL; "
        "printf 'epoch=1\\nused=100\\nresets=1000003600\\n' > \"$r\"; t FIVEHOUR; "
        'rm -f "$r"'
    )
    r = _source_vibe_call({}, snippet)
    check("[session-safety] detector snippet exits 0", r.returncode == 0, r.stderr)
    for tag, want in (("WEEKFULL", "wait"), ("WEEKLOW", "no"), ("WEEKNEAR", "no"), ("WEEKPAST", "no"), ("WEEKFAR", "no"),
                      ("WEEKNORESET", "no"), ("WEEKOCTAL", "no"), ("FIVEHOUR", "wait")):
        check(f"[session-safety] {tag} -> {want}", f"{tag}=[{want}]" in r.stdout, r.stdout)


def test_relaunch_countdown_waits_out_a_used_up_week():
    print("\n[session-safety] auto_resume_effective_wait honours a used-up week")
    snippet = (
        'd="${TMPDIR:-/tmp}/vibe-wkw.$$"; mkdir -p "$d"; now=1000000000; '
        'printf "active=1\\nremaining=5\\nresume_at=999990000\\n" > "$d/m"; '
        'printf "epoch=%s\\nused=21\\nresets=1000010000\\nused7=100\\nresets7=1000200000\\n" "$now" > "$d/rl"; '
        'echo "FULL=[$(auto_resume_effective_wait "$d/m" "$d/rl" "$now")]"; '
        'printf "epoch=%s\\nused=21\\nresets=1000010000\\nused7=50\\nresets7=1000200000\\n" "$now" > "$d/rl"; '
        'echo "LOW=[$(auto_resume_effective_wait "$d/m" "$d/rl" "$now")]"; '
        'rm -rf "$d"'
    )
    r = _source_vibe_call({}, snippet)
    check("[session-safety] used-up week: wait runs to its reset + grace", "FULL=[200120]" in r.stdout,
          r.stdout + r.stderr)
    check("[session-safety] week with headroom: the 120s grace is unchanged", "LOW=[120]" in r.stdout,
          r.stdout + r.stderr)


def _docker_stub(ps_output: str, exec_rc: int = 0, cid: str = "abc123") -> str:
    return (
        'docker() { case "$1" in '
        f'ps) printf "%s\\n" {shlex.quote(cid)} ;; '
        f'exec) printf "%s" {shlex.quote(ps_output)}; return {exec_rc} ;; '
        '*) return 1 ;; esac; }; '
    )


def test_live_session_count():
    print("\n[session-safety] vibe_container_live_sessions counts attached claude/codex sessions")
    claude = ("    1     0 /bin/sh -c echo Container started\n"
              "  771     0 /bin/sh\n"
              "  801     0 claude --permission-mode bypassPermissions\n"
              " 7519     1 sleep 1\n"
              " 7594   801 /bin/bash -c something claude\n")
    codex = ("    1     0 /bin/sh -c loop\n"
             "   90     0 node /usr/local/bin/codex-autonomy watch -- run --cwd /workspace\n"
             "   91    90 node /usr/local/bin/codex-supervisor run\n")
    codex_i = ("    1     0 /bin/sh -c loop\n"
               "   95     0 node /usr/local/share/npm-global/bin/codex -c agents.enabled=false\n")
    helpers = ("    1     0 /bin/sh -c loop\n"
               "   50     0 pkill -TERM -x claude\n"
               "   51     0 /bin/sh\n"
               "   52    51 claude --child-not-a-session\n")
    cases = (("CLAUDE", _docker_stub(claude), "1"),
             ("CODEX-SUPERVISED", _docker_stub(codex), "1"),
             ("CODEX-INTERACTIVE", _docker_stub(codex_i), "1"),
             ("HELPERS", _docker_stub(helpers), "0"),
             ("EXECFAIL", _docker_stub(claude, exec_rc=1), "0"),
             ("NOCONTAINER", _docker_stub(claude, cid=""), "0"))
    for tag, stub, want in cases:
        r = _source_vibe_call({}, stub + 'echo "N=[$(vibe_container_live_sessions /ws)]"')
        check(f"[session-safety] {tag} -> {want}", f"N=[{want}]" in r.stdout, r.stdout + r.stderr)


def _recreate_block() -> str:
    src = VIBE.read_text()
    m = re.search(r'^live_sessions=0\n.*?^\[ -n "\$extra_flag" \] && UP_ARGS\+=\("\$extra_flag"\)\n',
                  src, re.S | re.M)
    return m.group(0) if m else ""


def _run_recreate(live: int, rebuild: bool, other_drift: str, image_drift: str = "x") -> subprocess.CompletedProcess:
    block = _recreate_block()
    script = (
        f'vibe_container_live_sessions() {{ echo {live}; }}; '
        f'REBUILD={"true" if rebuild else "false"}; WORKSPACE=/ws; UP_ARGS=(up); '
        f'drift_marker={image_drift}; mount_drift=""; projects_drift=""; codex_drift=""; '
        f'domains_drift={shlex.quote(other_drift)}; extra_flag=--remove-existing-container; '
        + block +
        'echo "FLAG=[$extra_flag] ARGS=[${UP_ARGS[*]}] DRIFT=[$drift_marker]"'
    )
    return run(["bash", "-c", script])


def test_recreate_spares_a_live_session():
    print("\n[session-safety] a recreate never removes a container another session is using")
    check("[session-safety] recreate gate block found in the launcher", bool(_recreate_block()))
    r = _run_recreate(0, False, "")
    check("[session-safety] no live session: recreate proceeds",
          "FLAG=[--remove-existing-container] ARGS=[up --remove-existing-container]" in r.stdout, r.stdout)
    r = _run_recreate(1, False, "")
    check("[session-safety] live session + image drift only: joins the running container",
          r.returncode == 0 and "FLAG=[] ARGS=[up] DRIFT=[]" in r.stdout and "another vibe session" in r.stdout,
          r.stdout + r.stderr)
    src = VIBE.read_text()
    check("[session-safety] the other drifts are computed even when the image drifted",
          'if [ "$REBUILD" != true ]; then\n  actual_mounts=' in src)
    for img in ("x", ""):
        r = _run_recreate(1, False, "x", image_drift=img)
        check(f"[session-safety] live session + domain drift (image drift={bool(img)}): refuses",
              r.returncode == 1 and "FLAG=" not in r.stdout, r.stdout + r.stderr)
    r = _run_recreate(2, False, "x")
    check("[session-safety] live session + a drift that must not be skipped: refuses, kills nothing",
          r.returncode == 1 and "FLAG=" not in r.stdout and "2 other vibe session(s)" in r.stdout,
          r.stdout + r.stderr)
    r = _run_recreate(1, True, "")
    check("[session-safety] explicit --rebuild: proceeds and says what it ends",
          "ARGS=[up --remove-existing-container]" in r.stdout and "ending the 1 other" in r.stdout,
          r.stdout + r.stderr)
    src = VIBE.read_text()
    retry = src[src.index('if ! devcontainer "${UP_ARGS[@]}"; then'):]
    retry = retry[:retry.index("--remove-existing-container")]
    check("[session-safety] the failed-up retry checks for live sessions before removing",
          "vibe_container_live_sessions" in retry, retry[:300])
