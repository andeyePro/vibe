"""Docker hygiene: post-rebuild pruning, stale-container reaping, `vibe clean`.

Context (task_059): before this, `devcontainer up` never removed a container
and vibe never pruned anything, so every rebuild left the previous image
pinned or dangling and its build cache behind. On 2026-09-17 that filled a
926 GB Mac — Docker.raw at 245 GB, ~20 vibe containers across ~18 distinct
images — and the recovery (deleting Docker.raw) took the vibe-claude-config
volume, and with it the Claude login and every session history.

Two properties matter most here and are asserted from several angles:
  1. Nothing in this code path can ever remove a VOLUME.
  2. Nothing can remove a RUNNING container.
"""
from smoke._core import *  # noqa: F401,F403

import re
import shlex

DOCKERFILE = REPO / "devcontainer" / "Dockerfile"


# ── A stubbed docker, so none of this touches the real daemon ────────────────

# Default fleet the stub reports for `docker ps -a`, as
# id / image / devcontainer.local_folder label / com.andeye.vibe.image label:
#   c1  a container on the current vibe-dev tag        (in scope always)
#   c2  a labelled vibe container whose image is gone  (in scope always)
#   c3  a devcontainer whose image is gone, unlabelled (in scope under --all)
#   c4  an unrelated postgres container                (never in scope)
_PS_A_ROWS = (
    "c1\tvibe-dev:latest\t/Users/x/projA\t\n"
    "c2\tsha256:deadbeef\t/Users/x/projB\tvibe-dev\n"
    "c3\tsha256:cafe\t/Users/x/projC\t\n"
    "c4\tpostgres:16\t\t\n"
)

# Doubled %% on purpose: this string is embedded in the stub's `printf`
# format, where a bare % would be read as a conversion spec and eat the rest.
_SYSTEM_DF = (
    "Images\\t12.5GB (58%%)\\n"
    "Containers\\t2GB (100%%)\\n"
    "Local Volumes\\t40GB (100%%)\\n"
    "Build Cache\\t30GB (100%%)\\n"
)


def _hygiene_script(body: str, ps_aq: str = "aaa111\nbbb222\n",
                    ps_a: str = _PS_A_ROWS, log: str = "") -> str:
    """Source vibe with a docker() stub that logs every invocation.

    The stub shadows PATH, so no test here can reach a real Docker daemon.
    Every call is appended to $DOCKER_LOG, which the assertions then read —
    that log is how "never removes a volume" is proven rather than assumed.
    """
    return f"""
set -euo pipefail
source {shlex.quote(str(VIBE))}
DOCKER_LOG={shlex.quote(log)}
docker() {{
  [ -n "$DOCKER_LOG" ] && printf '%s\\n' "$*" >> "$DOCKER_LOG"
  case "$1 ${{2:-}}" in
    "info ")    return 0 ;;
    "ps -aq")   printf '%s' {shlex.quote(ps_aq)} ;;
    "ps -a")    printf '%s' {shlex.quote(ps_a)} ;;
    "system df") printf '{_SYSTEM_DF}' ;;
    "image prune")   printf 'Total reclaimed space: 3.2GB\\n' ;;
    "builder prune") printf 'Total reclaimed space: 1.5GB\\n' ;;
    "rm "*|"rm") return 0 ;;
    *) return 0 ;;
  esac
}}
{body}
"""


def _hyg(body: str, env_extra: dict | None = None, **kw):
    env = _isolate_extras_env(dict(os.environ))
    env["VIBE_SOURCE_ONLY"] = "1"
    env["VIBE_CONFIG"] = "/tmp/vibe-no-config-for-tests"
    if env_extra:
        env.update(env_extra)
    return run(["bash", "-c", _hygiene_script(body, **kw)], env=env)


# ── Size parsing ─────────────────────────────────────────────────────────────

def test_hygiene_size_parser_decimal_and_binary() -> None:
    """Docker prints decimal sizes (245GB = 245e9 bytes), and vibe must not
    read them as binary — a 7% overstatement at GB scale would make the
    advisory threshold fire early and train the user to ignore it."""
    cases = [
        ("245GB", 233650),      # decimal GB
        ("1.5GiB", 1536),       # explicit binary
        ("1GiB", 1024),
        ("0B", 0),
        ("12.5GB (58%)", 11921),  # `docker system df` Reclaimable form
        ("", 0),                  # unparseable degrades to 0, never an error
        ("junk", 0),
    ]
    body = "\n".join(
        f'printf "%s\\n" "$(_vibe_size_to_mib {shlex.quote(raw)})"' for raw, _ in cases
    )
    r = _hyg(body)
    got = r.stdout.strip().splitlines()
    check("[hygiene] _vibe_size_to_mib exits 0 on every input", r.returncode == 0, r.stderr)
    for (raw, want), actual in zip(cases, got):
        check(f"[hygiene] _vibe_size_to_mib({raw!r}) == {want} MiB",
              actual.strip() == str(want), f"got {actual!r}")


def test_hygiene_reclaimable_excludes_volumes() -> None:
    """Docker counts an unused volume as reclaimable, but vibe never reclaims
    one — so counting it would warn about space `vibe clean` will not free."""
    r = _hyg('_vibe_docker_reclaimable_mib')
    total = r.stdout.strip()
    # Images 12.5GB + Containers 2GB + Build Cache 30GB = 44.5GB decimal,
    # and emphatically NOT the 40GB of Local Volumes on top.
    check("[hygiene] reclaimable total excludes Local Volumes",
          total.isdigit() and 42000 < int(total) < 43000, f"got {total!r}")


# ── Post-build prune ─────────────────────────────────────────────────────────

def test_hygiene_prune_after_build_is_scoped() -> None:
    """A bare `docker image prune -f` would delete other projects' dangling
    images, and a bare `docker builder prune -f` their warm cache. vibe's
    automatic post-rebuild prune must be scoped to its own label and to cache
    older than a week."""
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        r = _hyg("vibe_prune_after_build", log=log)
        calls = Path(log).read_text()
        check("[hygiene] post-build prune reports what it reclaimed",
              "reclaimed" in r.stdout, r.stdout + r.stderr)
        check("[hygiene] post-build image prune is label-scoped",
              "image prune -f --filter label=com.andeye.vibe.image" in calls, calls)
        check("[hygiene] post-build builder prune is age-scoped",
              "builder prune -f --filter until=168h" in calls, calls)
        check("[hygiene] post-build prune never passes --volumes",
              "--volumes" not in calls and " -v" not in calls, calls)


def test_hygiene_prune_silent_when_nothing_reclaimed() -> None:
    """Zero reclaimed must print nothing: a launch-time line that always fires
    is a line users stop reading."""
    body = """
docker() { printf 'Total reclaimed space: 0B\\n'; }
vibe_prune_after_build
"""
    r = _hyg(body)
    check("[hygiene] prune prints nothing when it reclaimed nothing",
          r.stdout.strip() == "" and r.returncode == 0, repr(r.stdout))


def test_hygiene_helpers_survive_a_broken_docker() -> None:
    """Every helper runs under `set -euo pipefail` on the launch path. A
    docker that errors must degrade to a defined answer, never abort a
    launch."""
    body = """
docker() { return 1; }
printf 'reclaim=%s\\n' "$(_vibe_docker_reclaimable_mib)"
printf 'stale=[%s]\\n' "$(vibe_workspace_stale_containers /w)"
printf 'removed=%s\\n' "$(vibe_remove_stale_workspace_containers /w)"
vibe_prune_after_build
vibe_hygiene_check /nonexistent-marker
printf 'survived\\n'
"""
    r = _hyg(body)
    check("[hygiene] helpers survive a failing docker without aborting",
          r.returncode == 0 and "survived" in r.stdout, r.stdout + r.stderr)
    check("[hygiene] broken docker yields 0 reclaimable", "reclaim=0" in r.stdout, r.stdout)
    check("[hygiene] broken docker yields 0 removed", "removed=0" in r.stdout, r.stdout)


# ── Stale workspace containers ───────────────────────────────────────────────

def test_hygiene_stale_container_query_excludes_running() -> None:
    """Only exited/created/dead containers are ever in scope — the reaper must
    not be able to see a running container in the first place."""
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        _hyg('vibe_workspace_stale_containers /Users/x/projA', log=log)
        calls = Path(log).read_text()
        check("[hygiene] stale query filters on the workspace label",
              "label=devcontainer.local_folder=/Users/x/projA" in calls, calls)
        for status in ("exited", "created", "dead"):
            check(f"[hygiene] stale query includes status={status}",
                  f"status={status}" in calls, calls)
        check("[hygiene] stale query never asks for running containers",
              "status=running" not in calls, calls)


def test_hygiene_stale_container_removal_never_forces_or_takes_volumes() -> None:
    """`docker rm` with no flags, always: -f would reach a running container
    and -v would delete its anonymous volumes."""
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        r = _hyg('vibe_remove_stale_workspace_containers /Users/x/projA', log=log)
        calls = Path(log).read_text()
        check("[hygiene] stale removal reports the count", r.stdout.strip() == "2", r.stdout)
        check("[hygiene] stale removal issues a plain docker rm per container",
              "rm aaa111" in calls and "rm bbb222" in calls, calls)
        check("[hygiene] stale removal never passes -f", " -f" not in calls, calls)
        check("[hygiene] stale removal never passes -v", " -v" not in calls, calls)
        check("[hygiene] stale removal never touches a volume",
              "volume" not in calls, calls)


def test_hygiene_stale_removal_wired_into_the_recreate_path() -> None:
    """The reaper is only worth anything if the launch path calls it. It must
    run when (and only when) a recreate is already happening, so a normal
    launch never removes anything."""
    text = VIBE.read_text()
    idx_flag = text.find('extra_flag="$(remove_existing_flag')
    idx_reap = text.find('vibe_remove_stale_workspace_containers "$WORKSPACE"')
    idx_up = text.find('if ! devcontainer "${UP_ARGS[@]}"; then')
    check("[hygiene] launch path reaps stale containers", idx_reap != -1, "call not found")
    check("[hygiene] reaping is gated on the recreate decision",
          idx_flag != -1 and idx_flag < idx_reap, f"{idx_flag} !< {idx_reap}")
    check("[hygiene] reaping happens before `devcontainer up`",
          idx_up != -1 and idx_reap < idx_up, f"{idx_reap} !< {idx_up}")
    gate = text[idx_flag:idx_reap]
    check("[hygiene] reaping runs only when extra_flag is set",
          'if [ -n "$extra_flag" ]; then' in gate, gate[-400:])


def test_hygiene_prune_wired_after_each_build() -> None:
    """Both the base and the profile build must prune afterwards — a profile
    rebuild orphans an image just as a base rebuild does."""
    text = VIBE.read_text()
    check("[hygiene] base build prunes afterwards",
          'if [ "$BASE_REBUILT" = true ]; then\n  vibe_prune_after_build || true' in text,
          "base prune wiring not found")
    profile_block = text[text.find('Building profile image'):]
    profile_block = profile_block[:profile_block.find('\nfi\n')]
    check("[hygiene] profile build prunes inside its own if-block",
          "vibe_prune_after_build" in profile_block, profile_block)


# ── `vibe clean` ─────────────────────────────────────────────────────────────

def test_clean_scope_default_and_all() -> None:
    """Default scope: vibe's own leftovers only. --all additionally sweeps
    devcontainers whose image is gone. An unrelated container (postgres, no
    devcontainer label) is out of scope in both."""
    r = _hyg('_clean_stopped_containers')
    default_ids = [ln.split("\t")[0] for ln in r.stdout.strip().splitlines() if ln.strip()]
    check("[clean] default scope takes the tagged vibe container", "c1" in default_ids, r.stdout)
    check("[clean] default scope takes a labelled container whose image is gone",
          "c2" in default_ids, r.stdout)
    check("[clean] default scope leaves an unlabelled dangling devcontainer alone",
          "c3" not in default_ids, r.stdout)
    check("[clean] default scope never touches an unrelated container",
          "c4" not in default_ids, r.stdout)

    r_all = _hyg('_clean_stopped_containers all')
    all_ids = [ln.split("\t")[0] for ln in r_all.stdout.strip().splitlines() if ln.strip()]
    check("[clean] --all adds the unlabelled dangling devcontainer",
          {"c1", "c2", "c3"} <= set(all_ids), r_all.stdout)
    check("[clean] --all still never touches an unrelated container",
          "c4" not in all_ids, r_all.stdout)


def test_clean_dry_run_removes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        r = _hyg('clean_handle_subcommand clean --dry-run', log=log)
        calls = Path(log).read_text()
        check("[clean] --dry-run exits 0", r.returncode == 0, r.stdout + r.stderr)
        check("[clean] --dry-run lists the containers it would remove",
              "c1" in r.stdout and "c2" in r.stdout, r.stdout)
        check("[clean] --dry-run issues no rm", "\nrm " not in "\n" + calls, calls)
        check("[clean] --dry-run issues no prune", "prune" not in calls, calls)
        check("[clean] --dry-run says nothing was removed",
              "nothing removed" in r.stdout.lower(), r.stdout)


def test_clean_without_a_tty_refuses_rather_than_deleting() -> None:
    """A piped or cron-driven `vibe clean` must not delete what it was never
    told to delete; --yes is the deliberate non-interactive consent."""
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        r = _hyg('clean_handle_subcommand clean', log=log)
        calls = Path(log).read_text()
        check("[clean] non-interactive run removes nothing without --yes",
              "\nrm " not in "\n" + calls and "prune" not in calls, calls)
        check("[clean] non-interactive run names --yes as the way to consent",
              "--yes" in r.stdout + r.stderr, r.stdout + r.stderr)
        check("[clean] non-interactive refusal is not an error", r.returncode == 0,
              f"rc={r.returncode}")


def test_clean_yes_removes_containers_and_prunes_scoped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        r = _hyg('clean_handle_subcommand clean --yes', log=log)
        calls = Path(log).read_text()
        check("[clean] --yes removes the in-scope containers",
              "rm c1" in calls and "rm c2" in calls, calls)
        check("[clean] --yes leaves out-of-scope containers alone",
              "rm c3" not in calls and "rm c4" not in calls, calls)
        check("[clean] --yes prunes images label-scoped",
              "image prune -f --filter label=com.andeye.vibe.image" in calls, calls)
        check("[clean] --yes prunes build cache age-scoped",
              "builder prune -f --filter until=168h" in calls, calls)
        check("[clean] --yes reports what it removed", "removed" in r.stdout.lower(), r.stdout)


def test_clean_all_widens_both_sweeps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "docker.log")
        _hyg('clean_handle_subcommand clean --yes --all', log=log)
        calls = Path(log).read_text()
        check("[clean] --all removes the dangling devcontainer too", "rm c3" in calls, calls)
        check("[clean] --all still spares an unrelated container", "rm c4" not in calls, calls)
        check("[clean] --all prunes every dangling image",
              re.search(r"^image prune -f$", calls, re.M) is not None, calls)
        check("[clean] --all prunes cache of any age",
              re.search(r"^builder prune -f$", calls, re.M) is not None, calls)


def test_clean_never_removes_a_volume_in_any_mode() -> None:
    """The load-bearing invariant. Asserted against the actual docker call log
    of every mode, not against a reading of the source."""
    for mode in ("--dry-run", "--yes", "--yes --all"):
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "docker.log")
            _hyg(f'clean_handle_subcommand clean {mode}', log=log)
            calls = Path(log).read_text()
            check(f"[clean] `vibe clean {mode}` issues no volume command",
                  "volume" not in calls, calls)
            check(f"[clean] `vibe clean {mode}` never passes --volumes or -v",
                  "--volumes" not in calls and " -v " not in f" {calls} ", calls)


def test_clean_rejects_unknown_arguments() -> None:
    r = _hyg('clean_handle_subcommand clean --nuke-everything')
    check("[clean] an unknown argument is rejected", r.returncode != 0, r.stdout)
    check("[clean] the rejection points at --help",
          "--help" in r.stdout + r.stderr, r.stdout + r.stderr)


def test_clean_usage_promises_volume_safety() -> None:
    r = _hyg('clean_handle_subcommand clean --help')
    out = r.stdout
    check("[clean] --help states volumes are never removed",
          "NEVER" in out and "volume" in out.lower(), out)
    check("[clean] --help names the two volumes by name",
          "vibe-claude-config" in out and "vibe-bash-history" in out, out)
    check("[clean] --help explains why a stopped container matters",
          "pins the image" in out, out)


def test_clean_is_dispatched_before_flag_parsing() -> None:
    """Like learn/repos/audit/pat: `vibe clean --all` must not fall through to
    the flag parser and be read as a project name."""
    text = VIBE.read_text()
    idx_clean = text.find('if [ "${1:-}" = "clean" ]; then')
    # rfind, not find: the function's own doc comment names it first.
    idx_parse = text.rfind('\nparse_vibe_args "$@"')
    check("[clean] clean has a top-level dispatch", idx_clean != -1, "dispatch not found")
    check("[clean] dispatch precedes parse_vibe_args",
          idx_parse != -1 and idx_clean < idx_parse, f"{idx_clean} !< {idx_parse}")


# ── Preflight warning ────────────────────────────────────────────────────────

def test_hygiene_check_warns_and_throttles() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        marker = str(Path(tmp) / "hygiene-marker")
        env = {"VIBE_DISK_WARN_GIB": "999999", "VIBE_DOCKER_RECLAIM_WARN_GIB": "1"}
        first = _hyg(f'vibe_hygiene_check {shlex.quote(marker)}', env_extra=env)
        check("[hygiene] low free space warns", "free on this disk" in first.stderr, first.stderr)
        check("[hygiene] the warning names vibe clean", "vibe clean" in first.stderr, first.stderr)
        check("[hygiene] the warning names the Docker disk usage limit",
              "Disk usage limit" in first.stderr, first.stderr)
        check("[hygiene] high reclaimable space warns",
              "reclaimable" in first.stderr, first.stderr)
        check("[hygiene] warning never fails the launch", first.returncode == 0, first.stderr)
        check("[hygiene] the throttle marker is created", Path(marker).exists(), marker)

        second = _hyg(f'vibe_hygiene_check {shlex.quote(marker)}', env_extra=env)
        check("[hygiene] the docker half is throttled by the fresh marker",
              "reclaimable" not in second.stderr, second.stderr)


def test_hygiene_check_can_be_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        marker = str(Path(tmp) / "m")
        r = _hyg(f'vibe_hygiene_check {shlex.quote(marker)}',
                 env_extra={"VIBE_HYGIENE": "0", "VIBE_DISK_WARN_GIB": "999999"})
        check("[hygiene] VIBE_HYGIENE=0 silences the check", r.stderr.strip() == "", r.stderr)


def test_hygiene_check_wired_into_preflight() -> None:
    text = VIBE.read_text()
    idx_pre = text.find("vibe_docker_preflight || exit 1")
    idx_hyg = text.find("vibe_hygiene_check || true")
    check("[hygiene] preflight runs the hygiene check", idx_hyg != -1, "call not found")
    check("[hygiene] it runs after docker is known to be up",
          idx_pre != -1 and idx_pre < idx_hyg, f"{idx_pre} !< {idx_hyg}")
    check("[hygiene] it can never fail a launch",
          "vibe_hygiene_check || true" in text, "not guarded with || true")


# ── Label agreement across launcher, Dockerfile and ps format ────────────────

def test_image_label_agrees_everywhere() -> None:
    """Three places name the label. If they drift, the post-build prune stops
    matching vibe's own images and silently reclaims nothing."""
    text = VIBE.read_text()
    m = re.search(r'^VIBE_IMAGE_LABEL="([^"]+)"', text, re.M)
    check("[hygiene] VIBE_IMAGE_LABEL is defined in the launcher", m is not None, "not found")
    if not m:
        return
    label = m.group(1)
    dockerfile = DOCKERFILE.read_text()
    check(f"[hygiene] devcontainer/Dockerfile stamps {label}",
          re.search(rf'^LABEL {re.escape(label)}=', dockerfile, re.M) is not None, label)
    check("[hygiene] the docker ps format reads the same label",
          f'{{{{.Label "{label}"}}}}' in text, label)


def test_image_label_is_the_last_dockerfile_instruction() -> None:
    """Placed last on purpose: an earlier LABEL would invalidate the whole
    build cache for every user on the next rebuild."""
    lines = [ln.strip() for ln in DOCKERFILE.read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    check("[hygiene] the vibe image LABEL is the Dockerfile's last instruction",
          lines[-1].startswith("LABEL com.andeye.vibe.image="), lines[-1])


def test_launcher_has_no_volume_removal_anywhere() -> None:
    """Whole-file invariant: the launcher must contain no code that can delete
    a Docker volume. vibe-claude-config holds the Claude login and every
    session history; losing it once (2026-09-17) was enough."""
    text = VIBE.read_text()
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    offenders = [ln.strip() for ln in code
                 if re.search(r'docker\s+volume\s+(rm|prune)', ln)
                 or re.search(r'docker\s+system\s+prune[^\n]*--volumes', ln)
                 or re.search(r'docker\s+rm\b[^\n|#]*\s-\w*v', ln)]
    check("[hygiene] the launcher never removes a docker volume",
          not offenders, "; ".join(offenders))
