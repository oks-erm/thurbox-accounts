"""Verified cancellation of one native Claude process and its captured workers.

Read process metadata/argv only, never environments or credentials. Keep process
start identities throughout shutdown so a reused PID cannot become a kill target.
"""
import os
import ctypes
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time


def snapshot():
    try:
        result = subprocess.run(['ps', '-axo', 'pid=,ppid=,uid=,stat=,lstart='],
                                capture_output=True, text=True, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Cannot inspect native process shutdown; target was not launched') from error
    rows = {}
    for line in result.stdout.splitlines():
        pid, parent, uid, status, started = line.split(None, 4)
        pid, parent, uid = int(pid), int(parent), int(uid)
        if sys.platform.startswith('linux') and uid == os.getuid():
            try:
                # /proc start ticks are finer than ps's one-second timestamp.
                stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                started, status, parent = stat[19], stat[0], int(stat[1])
            except FileNotFoundError:
                continue
        rows[pid] = dict(pid=pid, parent=parent, uid=uid, start=started, status=status)
    return rows


def same(left, right):
    return right and all(left[key] == right[key] for key in ('pid', 'uid', 'start'))


def alive(identities, table=None):
    table = snapshot() if table is None else table
    return {p['pid']: table[p['pid']] for p in identities
            if same(p, table.get(p['pid'])) and not table[p['pid']]['status'].startswith('Z')}


def _signal(identity, signum):
    # Recheck immediately before each signal, including escalation and unfreeze.
    if alive([identity]):
        try:
            os.kill(identity['pid'], signum)
        except ProcessLookupError:
            pass


def _argv(pid):
    if sys.platform.startswith('linux'):
        return Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    value = subprocess.run(['ps', '-p', str(pid), '-o', 'args='],
                           capture_output=True, text=True, timeout=3, check=True)
    return shlex.split(value.stdout.strip())


def _executable(pid):
    if sys.platform.startswith('linux'):
        return Path(f'/proc/{pid}/exe').resolve()
    return None


def _supervisor_identity(root, native, conversation, launcher, writer):
    """Native Claude replaces its Linux argv with its title after startup.

    In that case require its real executable AND its direct guardian's pinned
    UUID/launcher and open writer lease. Do not inspect process environments.
    """
    if not sys.platform.startswith('linux') or not launcher or not writer:
        return False
    binary = shutil.which(native)
    if not binary or _executable(root['pid']) != Path(binary).resolve():
        return False
    parent = snapshot().get(root['parent'])
    if not parent or parent['uid'] != os.getuid():
        return False
    args = _argv(parent['pid'])
    if not any(args[i] in ('--resume','-r','--session-id') and args[i+1] == conversation
               for i in range(len(args)-1)):
        return False
    if not Path(launcher).is_file():
        return False  # Old console-script guardians need recorded launch identity.
    expected = Path(launcher).read_bytes()
    matches = False
    for arg in args[:3]:  # Python interpreter/options followed by guardian script.
        candidate = Path(arg)
        if (candidate.name == Path(launcher).name and candidate.is_file()
                and candidate.stat().st_uid == os.getuid() and candidate.stat().st_size == len(expected)
                and candidate.read_bytes() == expected):
            matches = True
    if not matches:
        return False
    lease = Path(writer).stat()
    for fd in Path(f'/proc/{parent["pid"]}/fd').iterdir():
        try:
            opened = fd.stat()
            if (opened.st_dev, opened.st_ino) == (lease.st_dev, lease.st_ino):
                return same(parent, snapshot().get(parent['pid']))
        except FileNotFoundError:
            continue
    return False


def worker_scope(conversation, owner):
    """Linux guardians adopt double-forked workers instead of losing ancestry."""
    if not sys.platform.startswith('linux'):
        return None
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Could not establish native worker ownership')
    scope = snapshot()[os.getpid()]
    return dict(scope,conversation=conversation,owner=owner,subreaper=True)


def stop_tree(pid, native, conversation, settings, *, prepared=None, launcher=None, writer=None,
              identity=None, scope=None):
    """Cancel only a matching guarded launch; return proof after every PID exits.

    Freeze the tree before shutdown to capture workers before parents can exit
    and reparent them. Terminate without resuming: exit handlers must not fork
    additional, detached workers while the controller is stopping this tree.
    A missing/unverifiable root is not evidence that its old workers have exited.
    """
    table = snapshot()
    root = table.get(pid)
    if not isinstance(pid, int) or not root or root['uid'] != os.getuid() or pid <= 1:
        raise ValueError('Cannot verify the native Claude process; target was not launched')
    executable = shutil.which(native)
    # New supervisors pin the kernel start identity at launch, before Claude
    # overwrites argv with its title. This also avoids flattened ps argv on macOS.
    matched = (identity and same(identity,root) and executable
               and identity.get('command') == str(Path(executable).resolve())
               and identity.get('conversation') == conversation
               and identity.get('settings') == str(settings))
    if not matched:
        args = _argv(pid)
        actual = shutil.which(args[0]) if args else None
        def argument(flag, value):
            return any(args[i] == flag and args[i+1] == str(value) for i in range(len(args)-1))
        matched = (executable and actual and Path(executable).resolve() == Path(actual).resolve()
                   and any(argument(flag, conversation) for flag in ('--resume', '-r', '--session-id'))
                   and argument('--settings', settings))
    if not matched and not _supervisor_identity(root,native,conversation,launcher,writer):
        raise ValueError('Native Claude process identity changed; no process was stopped')
    if not same(root, snapshot().get(pid)):
        raise ValueError('Cannot verify native process start identity; target was not launched')
    tracked = {pid: root}
    frozen = {}
    forced = []
    if scope and (not scope.get('subreaper') or scope.get('conversation') != conversation
                  or scope.get('pid') != root['parent'] or not same(scope,table.get(scope['pid']))):
        raise ValueError('Native worker guardian identity changed; shutdown is unconfirmed')

    def collect(table):
        parents = set(alive(tracked.values(), table))
        if scope:
            if not same(scope,table.get(scope['pid'])):
                raise ValueError('Native worker guardian exited before capture; shutdown is unconfirmed')
            parents.add(scope['pid'])
        while True:
            children = {p['pid']: p for p in table.values()
                        if p['parent'] in parents and p['pid'] not in parents}
            if not children:
                break
            if any(p['uid'] != os.getuid() for p in children.values()):
                raise ValueError('A native worker has a different owner; shutdown is unconfirmed')
            if os.getpid() in children:
                raise ValueError('The switch controller is inside the source process tree')
            for child, identity in children.items():
                previous = tracked.get(child)
                if previous and not same(previous, identity):
                    raise ValueError('A worker PID was reused during shutdown')
                tracked.setdefault(child,identity)
            parents.update(children)

    try:
        # Preserve descendants from the initial snapshot, including any which
        # reparent before the native root acknowledges SIGSTOP.
        collect(table)
        if os.getpid() in tracked:
            raise ValueError('The switch controller is inside the source process tree')
        frozen[pid] = root
        _signal(root, signal.SIGSTOP)
        deadline = time.monotonic() + 3
        root_stopped = False
        observed_stopped = set()
        stable = None
        while True:
            table = snapshot()
            current_root = alive([root],table).get(pid)
            if not root_stopped:
                if not current_root:
                    raise ValueError('Native process exited before its workers could be captured; shutdown is unconfirmed')
                root_stopped = current_root['status'].startswith('T')
            collect(table)
            running = alive(tracked.values(), table)
            for child, identity in tracked.items():
                if child in running and running[child]['status'].startswith('T'):
                    observed_stopped.add(child)
                elif (not scope and child not in running and child not in observed_stopped
                      and not identity['status'].startswith('Z')):
                    raise ValueError('A native worker exited before its descendants could be captured; shutdown is unconfirmed')
            if root_stopped and all(p['status'].startswith('T') for p in running.values()):
                # ps enumeration and /proc status reads are separate operations.
                # Scan again after all observed processes are stopped, including
                # workers newly reparented to the subreaper during that scan.
                if stable == set(tracked):
                    break
                stable = set(tracked)
                continue
            stable = None
            if time.monotonic() > deadline:
                raise TimeoutError('Could not pause all native workers; target was not launched')
            for child, identity in running.items():
                frozen[child] = identity
                _signal(identity, signal.SIGSTOP)
            time.sleep(.02)
        evidence = dict(processes=list(tracked.values()), forced=forced)
        if prepared:
            prepared(evidence)
        for child, identity in reversed(list(running.items())):
            _signal(identity, signal.SIGKILL)
            forced.append(child)
        deadline = time.monotonic() + 3
        while alive(tracked.values()):
            if time.monotonic() >= deadline:
                raise TimeoutError('Native workers did not stop; target was not launched')
            time.sleep(.05)
        return dict(processes=list(tracked.values()), forced=forced)
    finally:
        for identity in frozen.values():
            _signal(identity, signal.SIGCONT)
