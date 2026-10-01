"""The stall watchdog stands aside while Claude Code waits out a 5-hour limit
itself (autoContinueAtUsageLimit, on by default since Claude Code 2.1.234).

The watchdog kills a claude whose heartbeat has gone stale, because older
Claude Code blocked forever at the usage-limit picker. Current Claude Code
waits for the reset and carries on by itself — the heartbeat is just as stale
during that wait. The statusLine now records the five_hour window's
resets_at, and auto_resume_native_wait vetoes the kill while the last reading
shows the window used up and its reset still ahead (plus grace).
"""
from smoke._core import *  # noqa: F401,F403

import os
import subprocess
import tempfile


def test_statusline_records_the_window_reset():
    print("\n[native-wait] statusLine records resets= when Claude Code supplies it")
    cmd = _statusline_command()
    check("[native-wait] statusLine command extracted", bool(cmd), "")
    if not cmd:
        return
    with_reset = ('{"model":{"display_name":"Opus 4.8"},'
                  '"rate_limits":{"five_hour":{"used_percentage":97.2,"resets_at":1790316587.4}}}')
    with tempfile.TemporaryDirectory() as td:
        canary = Path(td) / "canary"
        bad_reset = ('{"model":{"display_name":"Opus 4.8"},'
                     '"rate_limits":{"five_hour":{"used_percentage":97,"resets_at":"$(touch ' + str(canary) + ')"}}}')
        env = {**os.environ, "VIBE_VSS_DIR": td}
        r = subprocess.run(["sh", "-c", cmd], input=with_reset, env=env, capture_output=True,
                           text=True, timeout=15)
        check("[native-wait] display unchanged by the extra field",
              r.returncode == 0 and r.stdout == "O · vibe · 5h 97%", f"rc={r.returncode} out=[{r.stdout}]")
        lines = (Path(td) / "rate-limit").read_text().splitlines() if (Path(td) / "rate-limit").exists() else []
        check("[native-wait] reading carries used= and a floored resets=",
              len(lines) == 3 and lines[1] == "used=97" and lines[2] == "resets=1790316587", str(lines))
        r = subprocess.run(["sh", "-c", cmd], input=bad_reset, env=env, capture_output=True,
                           text=True, timeout=15)
        lines = (Path(td) / "rate-limit").read_text().splitlines()
        check("[native-wait] a non-numeric resets_at is dropped, not written",
              len(lines) == 2 and not any(l.startswith("resets=") for l in lines), str(lines))
        check("[native-wait] ... and never evaluated", not canary.exists())


def test_native_wait_detector():
    print("\n[native-wait] auto_resume_native_wait: used-up window with its reset still ahead")
    snippet = (
        'r="${TMPDIR:-/tmp}/vibe-nw.$$"; now=1000000000; '
        't() { if auto_resume_native_wait "$r" "$now"; then echo "$1=[wait]"; else echo "$1=[no]"; fi; }; '
        "printf 'epoch=999999000\\nused=100\\nresets=1000003600\\n' > \"$r\"; t FULL; "
        "printf 'epoch=999999000\\nused=92\\nresets=1000003600\\n' > \"$r\"; t NEAR; "
        "printf 'epoch=999999000\\nused=60\\nresets=1000003600\\n' > \"$r\"; t LOW; "
        "printf 'epoch=999999000\\nused=100\\nresets=999999500\\n' > \"$r\"; t GRACE; "
        "printf 'epoch=999999000\\nused=100\\nresets=999990000\\n' > \"$r\"; t PAST; "
        "printf 'epoch=999999000\\nused=100\\n' > \"$r\"; t NORESET; "
        "printf 'epoch=999999000\\nused=100\\nresets=soon; rm -rf /\\n' > \"$r\"; t GARBAGE; "
        "printf 'epoch=999999000\\nused=100\\nresets=01000003600\\n' > \"$r\"; t LEADZERO; "
        "printf 'epoch=999999000\\nused=100\\nresets=08\\n' > \"$r\"; t OCTALBAIT; "
        "printf 'epoch=999999000\\nused=100\\nresets=1000030000\\n' > \"$r\"; t FARFUTURE; "
        "printf 'epoch=999999000\\nused=100\\nresets=1000003600000\\n' > \"$r\"; t MILLIS; "
        "printf 'epoch=999999000\\nresets=1000003600\\n' > \"$r\"; t NOUSED; "
        "printf 'epoch=999999000\\nused=100\\nresets=999999100\\n' > \"$r\"; t EDGE; "
        "printf 'epoch=999999000\\nused=100\\nresets=999999099\\n' > \"$r\"; t PASTEDGE; "
        'rm -f "$r"; t MISSING; '
        "printf 'epoch=999999000\\nused=85\\nresets=1000003600\\n' > \"$r\"; "
        'echo "KNOB=[$(VIBE_NATIVE_WAIT_USED_MIN=80; auto_resume_native_wait "$r" "$now" && echo wait || echo no)]"; '
        'rm -f "$r"'
    )
    r = _source_vibe_call({}, snippet)
    check("[native-wait] detector snippet exits 0", r.returncode == 0, r.stderr)
    for tag, want in (("FULL", "wait"), ("NEAR", "wait"), ("LOW", "no"), ("GRACE", "wait"),
                      ("PAST", "no"), ("NORESET", "no"), ("GARBAGE", "no"), ("MISSING", "no"),
                      ("LEADZERO", "wait"), ("OCTALBAIT", "no"), ("FARFUTURE", "no"), ("MILLIS", "no"),
                      ("NOUSED", "no"), ("EDGE", "wait"), ("PASTEDGE", "no")):
        check(f"[native-wait] {tag} -> {want}", f"{tag}=[{want}]" in r.stdout, r.stdout)
    check("[native-wait] VIBE_NATIVE_WAIT_USED_MIN honoured", "KNOB=[wait]" in r.stdout, r.stdout)


def _watchdog_snippet(resets_expr: str) -> str:
    return (
        'set +e; '
        'd="${TMPDIR:-/tmp}/stall-nw.$$"; mkdir -p "$d"; '
        'marker="$d/marker"; hb="$d/hb"; killfile="$d/killfile"; '
        'vibe_container_kill_claude() { echo "killed" > "$killfile"; }; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$marker"; '
        f'printf "epoch=%s\\nused=100\\nresets=%s\\n" "$(date +%s)" "{resets_expr}" > "$d/rate-limit"; '
        'echo "$(($(date +%s) - 2000))" > "$hb"; '
        'sleep 12 & fake_pid=$!; '
        'VIBE_STALL_POLL_SECS=1 VIBE_STALL_GRACE_SECS=1 VIBE_STALL_SECS=1 VIBE_STALL_KILL_PAUSE_SECS=0 '
        'vibe_stall_watchdog "$fake_pid" "$marker" "$hb" "-" 2>/dev/null & wd_pid=$!; '
        'for _ in 1 2 3 4 5 6 7 8; do [ -f "$killfile" ] && break; sleep 1; done; '
        'if [ -f "$killfile" ]; then echo "KILLFILE=[yes]"; else echo "KILLFILE=[no]"; fi; '
        'kill "$fake_pid" "$wd_pid" 2>/dev/null; wait "$fake_pid" 2>/dev/null; wait "$wd_pid" 2>/dev/null; '
        'rm -rf "$d"; set -e'
    )


def test_watchdog_stands_aside_during_a_native_wait():
    print("\n[native-wait] the stall watchdog does not kill a native usage-limit wait")
    r = _source_vibe_call({}, _watchdog_snippet("$(( $(date +%s) + 3600 ))"))
    check("[native-wait] reset an hour ahead: no kill despite a stale heartbeat",
          "KILLFILE=[no]" in r.stdout, r.stdout + r.stderr)
    r = _source_vibe_call({}, _watchdog_snippet("$(( $(date +%s) - 7200 ))"))
    check("[native-wait] positive control: reset long past, stale heartbeat -> killed",
          "KILLFILE=[yes]" in r.stdout, r.stdout + r.stderr)


def test_relaunch_gate_ignores_the_native_wait():
    print("\n[native-wait] the relaunch gate after claude exits is NOT vetoed by a used-up reading")
    # After credit exhaustion claude exits with a used>=90 reading and a future
    # reset on disk; the relaunch loop's _vibe_stall_armed gate must still arm.
    snippet = (
        'd="${TMPDIR:-/tmp}/vibe-nwr.$$"; mkdir -p "$d"; '
        'printf "active=1\\nremaining=2\\nresume_at=1751600000\\n" > "$d/marker"; '
        'printf "epoch=%s\\nused=100\\nresets=%s\\n" "$(date +%s)" "$(( $(date +%s) + 3600 ))" > "$d/rate-limit"; '
        'if _vibe_stall_armed "$d/marker" "-"; then echo "ARMED=[yes]"; else echo "ARMED=[no]"; fi; '
        'rm -rf "$d"'
    )
    r = _source_vibe_call({}, snippet)
    check("[native-wait] relaunch gate still arms with a used-up reading on disk",
          "ARMED=[yes]" in r.stdout, r.stdout + r.stderr)
