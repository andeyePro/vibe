#!/usr/bin/env python3
"""Host-only onboarding storage. No credential file contents are inspected.

CLI: memory-get WS; memory-set WS AGENT; check|setup WS FALLBACK SOURCE;
source-check SOURCE; host-check; git-check WS. check is read-only; setup requires the caller's TTY consent.
All project writes use pinned directory descriptors and no-follow opens.
"""
import fcntl
import hashlib
import json
import os
import pwd
import secrets
import stat
import subprocess
import sys

DOMAINS = ('chatgpt.com', 'auth.openai.com', 'api.openai.com')


def docker_ready():
    try:
        return subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=8).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def start_mac_docker():
    """Start an identifiable local backend, never change Docker's target."""
    if sys.platform != 'darwin' or not (os.isatty(0) and os.isatty(1)):
        return False
    try:
        account_home = pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return False
    if os.environ.get('HOME') != account_home:
        return False
    endpoint = os.environ.get('DOCKER_HOST', '')
    if endpoint and (endpoint != 'unix:///var/run/docker.sock' or os.environ.get('DOCKER_CONTEXT')):
        return False  # Explicit custom/remote connections belong to the user.
    try:
        result = subprocess.run(['docker', 'context', 'show'], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode:
        return False
    context = result.stdout.strip()
    apps = {'orbstack': '/Applications/OrbStack.app', 'desktop-linux': '/Applications/Docker.app'}
    if context in apps:
        app = apps[context]
    elif context == 'default':
        available = [app for app in apps.values() if os.path.isdir(app)]
        if len(available) != 1:
            return False
        app = available[0]
    else:
        return False
    if not os.path.isdir(app):
        return False
    # Context names are mutable labels: validate the selected endpoint too.
    try:
        inspected = subprocess.run(
            ['docker', 'context', 'inspect', context, '--format', '{{.Endpoints.docker.Host}}'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if inspected.returncode:
        return False
    selected_endpoint = endpoint or inspected.stdout.strip()
    expected = {'unix:///var/run/docker.sock'}
    if app == apps['orbstack']:
        expected.add('unix://' + os.path.join(account_home, '.orbstack/run/docker.sock'))
    else:
        expected.add('unix://' + os.path.join(account_home, '.docker/run/docker.sock'))
    if selected_endpoint not in expected:
        return False
    print('  Starting ' + os.path.basename(app) + ' for Docker...', flush=True)
    try:
        return subprocess.run(['/usr/bin/open', '-a', app], stdin=subprocess.DEVNULL,
                              timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def host():
    if (os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')
            or os.environ.get('REMOTE_CONTAINERS') or os.environ.get('VIBE_CONTAINER')):
        raise ValueError('host onboarding must run on the host, outside a container')
    for name in ('/proc/1/cgroup', '/proc/self/mountinfo'):
        try:
            with open(name) as f:
                if any(x in f.read() for x in ('/docker/', '/kubepods/', '/lxc/')):
                    raise ValueError('host onboarding must run outside a container')
        except FileNotFoundError:
            pass


def directory(path, create=False):
    """Walk without symlinks; never chmod existing directories."""
    path = os.path.abspath(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.split('/')[1:]:
            if not part:
                continue
            try:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass  # A concurrent creator still has to pass no-follow/ownership checks.
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            s = os.fstat(fd)
            if s.st_uid not in (0, os.getuid()) or (s.st_mode & 0o022 and not
                    (s.st_uid == 0 and s.st_mode & stat.S_ISVTX)):
                raise ValueError('unsafe directory ancestor: ' + path)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(fd, name, private=False):
    try:
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(f, 'rb') as stream:
        s = os.fstat(stream.fileno())
        if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid()
                or s.st_mode & 0o022 or (private and s.st_mode & 0o077)):
            raise ValueError('unsafe regular file: ' + name)
        if s.st_size > 1048576:
            raise ValueError('onboarding file exceeds 1 MiB: ' + name)
        data = stream.read(1048577)
        if len(data) > 1048576:
            raise ValueError('onboarding file exceeds 1 MiB: ' + name)
        return data


def atomic(fd, name, data, private=False):
    read_file(fd, name, private)  # fail before mutation; refuse unrelated unsafe files
    tmp = '.onboarding-' + secrets.token_hex(16)
    f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(f, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(tmp, dir_fd=fd)
        except FileNotFoundError:
            pass


def canonical(ws):
    ws = os.path.realpath(ws)
    if not os.path.isdir(ws) or any(ord(c) < 32 for c in ws):
        raise ValueError('project must be an existing folder with a single-line path')
    return ws


def storage(ws, create=False):
    home = os.path.abspath(os.environ['HOME'])
    root = home + '/.vibe'
    # Host state must never sit inside the project or the standard extra mounts.
    mounts = [ws, home + '/.claude', os.environ.get('VIBE_CODEX_PATH', home + '/.codex'), home + '/.ssh',
              os.environ.get('VIBE_PROJECTS_DIR', home + '/Projects'),
              os.environ.get('VIBE_BRAIN2_PATH', home + '/brain2'),
              os.environ.get('VIBE_ZOTERO_PATH', home + '/Zotero/storage')]
    try:
        checkfd = directory(root)
    except FileNotFoundError:
        checkfd = None
    if checkfd is not None:
        try:
            shared = read_file(checkfd, 'repos', True)
            if shared:
                for line in shared.decode().splitlines():
                    if '=' in line and not line.lstrip().startswith('#'):
                        mounts.append(line.split('=', 1)[1])
        finally:
            os.close(checkfd)
    for mount in mounts:
        if mount != 'off' and os.path.commonpath([os.path.realpath(root), os.path.realpath(mount)]) == os.path.realpath(mount):
            raise ValueError('host onboarding state would be exposed by a container mount')
    return directory(root, create)


def git(ws, *args):
    return subprocess.run(['git', '-C', ws, *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout


def exclude_onboarding(ws):
    """Keep generated local consent out of the shared initial-commit flow."""
    target = os.path.abspath(os.path.join(ws, os.fsdecode(git(ws, 'rev-parse', '--git-path', 'info/exclude')).strip()))
    fd = directory(os.path.dirname(target), True)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = read_file(fd, os.path.basename(target)) or b''
        top = os.fsdecode(git(ws, 'rev-parse', '--show-toplevel')).strip()
        relative = os.path.relpath(ws, top)
        prefix = '' if relative == '.' else relative + '/'
        paths = ('.vibe-allow-codex', '.vibe/domains', '.vibe/next-agent')
        patterns = []
        for path in paths:
            pattern = '/' + ''.join('\\' + c if c in '\\?*[]!# ' else c for c in prefix + path)
            if pattern.encode() not in raw.splitlines():
                patterns.append(pattern + '\n')
        if patterns:
            atomic(fd, os.path.basename(target), raw + (b'\n' if raw and not raw.endswith(b'\n') else b'') + ''.join(patterns).encode())
        for path in paths:
            # A higher-priority project ignore rule can negate info/exclude.
            git(ws, 'check-ignore', '--no-index', '--quiet', '--', path)
    finally:
        os.close(fd)


def project_files(ws):
    if git(ws, 'rev-parse', '--is-inside-work-tree').strip() != b'true':
        raise ValueError('a local Git work tree is required')
    for name in ('.vibe-allow-codex', '.vibe/domains'):
        if git(ws, 'ls-files', '--', ':(icase)' + name):
            raise ValueError(name + ' is tracked; refusing onboarding')
    root = directory(ws)
    marker = read_file(root, '.vibe-allow-codex')
    try:
        config = directory(ws + '/.vibe')
    except FileNotFoundError:
        config = None
    domains = read_file(config, 'domains') if config is not None else None
    return root, config, marker, domains


def source_check(source):
    if not os.path.isabs(source):
        raise ValueError('VIBE_CODEX_PATH must be absolute for host login')
    # Check the whole existing chain without creating it or reading auth/config.
    path = source
    while not os.path.lexists(path):
        path = os.path.dirname(path)
    fd = directory(path)
    os.close(fd)
    if os.path.isdir(source):
        fd = directory(source)
        try:
            for name in ('auth.json', 'config.toml'):
                try:
                    s = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid()
                        or s.st_mode & (0o077 if name == 'auth.json' else 0o022)):
                    raise ValueError('unsafe Codex ' + name)
        finally:
            os.close(fd)


def switch_ready(ws):
    try:
        fd = directory(ws + '/.vss')
    except FileNotFoundError:
        return
    try:
        marker = read_file(fd, 'auto-resume') or b''
        if b'active=1' in marker.splitlines():
            raise ValueError('finish or stop the active autonomous run before switching agents')
        try:
            os.stat('codex-supervisor.json.lock', dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('stop and reconcile the Codex supervisor before switching agents')
        state = read_file(fd, 'codex-supervisor.json')
        if state:
            record = json.loads(state)
            if not isinstance(record, dict) or record.get('unresolvedTurn') or record.get('activeTurn'):
                raise ValueError('reconcile the interrupted Codex turn before switching agents')
    finally:
        os.close(fd)


def agent_request(ws, agent=None):
    """Container-writable runtime request, never a credential grant."""
    if agent is not None and agent not in ('claude', 'codex'):
        raise ValueError('choose claude or codex')
    try:
        fd = directory(ws + '/.vibe', agent is not None)
    except FileNotFoundError:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = read_file(fd, 'next-agent', True)
        if agent is None and raw is None:
            return
        if git(ws, 'ls-files', '--', ':(icase).vibe/next-agent'):
            raise ValueError('agent request must be untracked')
        switch_ready(ws)
        if agent is not None:
            exclude_onboarding(ws)
            atomic(fd, 'next-agent', json.dumps({'agent': agent}).encode() + b'\n', True)
            print('Switch queued to ' + agent + '. Exit this session normally to reopen with it. Conversation history stays with its original agent.')
            return
        record = json.loads(raw)
        if not isinstance(record, dict) or set(record) != {'agent'} or record['agent'] not in ('claude', 'codex'):
            raise ValueError('invalid agent switch request')
        # Called only by the host: persist the choice before consuming the
        # request, so a crash cannot lose the requested next runtime.
        target = storage(ws, True)
        try:
            fcntl.flock(target, fcntl.LOCK_EX)
            name = 'runtime-' + hashlib.sha256(os.fsencode(ws)).hexdigest() + '.json'
            atomic(target, name, json.dumps({'workspace': ws, 'agent': record['agent']}).encode() + b'\n', True)
        finally:
            os.close(target)
        os.unlink('next-agent', dir_fd=fd)
        os.fsync(fd)
        print(record['agent'])
    finally:
        os.close(fd)


def main():
    action, *args = sys.argv[1:]
    if action == 'request-agent':
        if len(args) != 2:
            raise ValueError('Usage: request-agent PROJECT claude|codex')
        agent_request(canonical(args[0]), args[1])
        return
    if action == 'docker-ready':
        if not docker_ready():
            raise ValueError('Docker is not ready')
        return
    host()
    if action == 'docker-start':
        if not start_mac_docker():
            raise ValueError('start the Docker backend selected by your host configuration, then run vibe again')
        return
    if action == 'host-check':
        return
    if action == 'source-check':
        source_check(args[0])
        return
    ws = canonical(args[0])
    if action == 'cancel-agent':
        try:
            fd = directory(ws + '/.vibe')
        except FileNotFoundError:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = read_file(fd, 'next-agent', True)
            if raw is not None:
                if git(ws, 'ls-files', '--', ':(icase).vibe/next-agent'):
                    raise ValueError('refusing to cancel a tracked agent request')
                os.unlink('next-agent', dir_fd=fd)
                os.fsync(fd)
        finally:
            os.close(fd)
        return
    if action == 'take-agent':
        agent_request(ws)
        return
    if action == 'git-check':
        fd = directory(ws)
        try:
            try:
                os.stat('.git', dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise ValueError('existing .git is not a usable work tree; refusing git init')
        finally:
            os.close(fd)
    if action in ('memory-get', 'memory-set'):
        try:
            fd = storage(ws, action == 'memory-set')
        except FileNotFoundError:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            name = 'runtime-' + hashlib.sha256(os.fsencode(ws)).hexdigest() + '.json'
            raw = read_file(fd, name, True)
            if raw is not None:
                record = json.loads(raw)
                if (not isinstance(record, dict) or set(record) != {'workspace', 'agent'}
                        or record.get('workspace') != ws or record.get('agent') not in ('claude', 'codex')):
                    raise ValueError('invalid runtime record or canonical path binding')
            if action == 'memory-get':
                if raw is not None:
                    print(record['agent'])
            else:
                if args[1] not in ('claude', 'codex'):
                    raise ValueError('invalid runtime')
                atomic(fd, name, json.dumps(dict(workspace=ws, agent=args[1])).encode() + b'\n', True)
        finally:
            os.close(fd)
        return
    if action not in ('check', 'setup'):
        raise ValueError('unknown operation')
    if action == 'setup' and not (os.isatty(0) and os.isatty(1)):
        raise ValueError('credential setup requires an interactive host terminal')
    fallback, source = args[1:]
    source_check(source)
    if os.path.commonpath([ws, os.path.realpath(source)]) == ws:
        raise ValueError('Codex login source must be outside the project')
    root, config, marker, domains = project_files(ws)
    # Validate host destinations BEFORE project mutations, including absent parents.
    try:
        fd = storage(ws)
        fcntl.flock(fd, fcntl.LOCK_EX)
        registry = read_file(fd, 'codex-allow', True)
    except FileNotFoundError:
        fd, registry = None, None
    if registry:
        for line in registry.splitlines():
            if not line.startswith(b'/') or any(c < 32 for c in line):
                raise ValueError('invalid host consent registry; refusing to modify it')
    raw = domains if domains is not None else fallback.encode()
    tokens = b' '.join(line.split(b'#', 1)[0] for line in raw.splitlines()).replace(b',', b' ').split()
    missing = [d for d in DOMAINS if d.encode() not in tokens]
    if len(set(tokens) | {d.encode() for d in DOMAINS}) > int(os.environ.get('EXTRA_DOMAINS_MAX', '32')):
        raise ValueError('domain list would exceed the firewall limit; refusing to drop effective entries')
    if action == 'setup':
        exclude_onboarding(ws)
        if config is None:
            config = directory(ws + '/.vibe', True)
        if missing or domains is None:
            content = raw + (b'\n' if raw and not raw.endswith(b'\n') else b'')
            content += ''.join(d + '\n' for d in missing).encode()
            atomic(config, 'domains', content)
        if marker is None:
            atomic(root, '.vibe-allow-codex', b'')
        if fd is None:
            fd = storage(ws, True)
            fcntl.flock(fd, fcntl.LOCK_EX)
        registry = read_file(fd, 'codex-allow', True) or b''
        if os.fsencode(ws) not in registry.splitlines():
            atomic(fd, 'codex-allow', registry + (b'\n' if registry and not registry.endswith(b'\n') else b'') + os.fsencode(ws) + b'\n', True)
    for f in (root, config, fd):
        if f is not None:
            os.close(f)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('vibe host onboarding: ' + str(exc), file=sys.stderr)
        sys.exit(1)
