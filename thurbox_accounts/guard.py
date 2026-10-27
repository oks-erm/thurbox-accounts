"""Managed native supervisor: lifetime writer lease, turn hooks, safe switch stop."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

from .accounts import Accounts, Claude, Profiles, account_env
from .core import atomic_write, dumps, redact
from .shared import Shared, identifier
from .thurbox import Thurbox, strict_json

EVENTS = ('UserPromptSubmit','PreToolUse','PostToolUse','PostToolUseFailure',
          'PermissionRequest','SubagentStart','SubagentStop','Stop','StopFailure')


def authorize(record, owner, reservation):
    if not owner or record['allowed_session'] != owner:
        raise ValueError('This session is no longer the authorized shared writer owner')
    if record['phase'] == 'switching':
        if not reservation or reservation != record['reservation']:
            raise ValueError('Shared transition reservation does not match')
    elif record['phase'] != 'active':
        raise ValueError('Shared conversation requires recovery before launch')


@contextlib.contextmanager
def writer(store, conversation):
    with store.lock('writer-' + identifier(conversation)):
        yield


def writer_available(store, conversation):
    try:
        with writer(store, conversation):
            return True
    except ValueError:
        return False


@contextlib.contextmanager
def events_lock(store, conversation):
    fd = os.open(store.root / ('events-' + identifier(conversation) + '.lock'),
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def update(store, conversation, **fields):
    with events_lock(store, conversation):
        name = 'runtime-' + conversation + '.json'
        current = store.read(name)
        current.update(fields)
        store.write(name, current)
        return current


def apply_event(state, event, payload):
    tools, agents = set(state.get('tools', [])), set(state.get('subagents', []))
    tool = payload.get('tool_use_id')
    agent = payload.get('agent_id')
    if event == 'UserPromptSubmit':
        state.update(turn='working',blocked=False)
    elif event == 'PreToolUse':
        if not isinstance(tool,str) or not tool:
            raise ValueError('Native tool hook has no stable tool id')
        tools.add(tool)
        state['turn'] = 'working'
    elif event in {'PostToolUse','PostToolUseFailure'}:
        tools.discard(tool)
        state['blocked'] = False
    elif event == 'PermissionRequest':
        state['blocked'] = True
    elif event == 'SubagentStart':
        if not isinstance(agent,str) or not agent:
            raise ValueError('Native subagent hook has no stable agent id')
        agents.add(agent)
    elif event == 'SubagentStop':
        agents.discard(agent)
    elif event in {'Stop','StopFailure'}:
        # Stop hooks can themselves request another turn. An API rate-limit
        # StopFailure is notification-only and cannot keep that turn running.
        quota = event == 'StopFailure' and payload.get('error') == 'rate_limit'
        state.update(turn='quota' if quota else 'idle',blocked=False,last_stop=time.time())
    counts = dict(state.get('events',{}))
    counts[event] = counts.get(event,0) + 1
    state.update(tools=sorted(tools),subagents=sorted(agents),events=counts)
    return state


def safe_state(state):
    return (state.get('turn') == 'quota' and not state.get('tools') and not state.get('subagents')
            and not state.get('blocked') and not state.get('uncertain') and not state.get('error'))


def hook(store, shared, conversation, owner, event):
    if event not in EVENTS:
        raise ValueError('Unknown shared guard hook')
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Native hook payload exceeds the supported bound')
    payload = strict_json(raw.decode())
    if not isinstance(payload,dict) or payload.get('session_id') != conversation:
        # Subagent-native hooks do not describe the main conversation; the
        # parent's SubagentStart/Stop events already keep it protected.
        return 0
    record = shared.load(conversation)
    authorize(record,owner,os.environ.get('THURBOX_ACCOUNTS_RESERVATION',''))
    shared.validate(record)
    with events_lock(store,conversation):
        name = 'runtime-' + conversation + '.json'
        state = store.read(name)
        if state.get('owner') != owner:
            raise ValueError('Stale native hook owner')
        state = apply_event(state,event,payload)
        store.write(name,state)
    return 0


def guarded_settings(args, launcher):
    """Preserve hook-only registry patches, append owned safety callbacks.

    Other --settings overrides are refused rather than silently dropping policy.
    Native profile/project/managed settings retain their normal precedence.
    """
    native, inherited = [], {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith('--settings='):
            raise ValueError('Use a separate --settings argument for guarded sessions')
        if arg == '--settings':
            if index + 1 >= len(args):
                raise ValueError('Missing native settings argument')
            value = args[index+1]
            if value.lstrip().startswith('{'):
                settings = strict_json(value)
            else:
                path = Path(value)
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                    raise ValueError('Guarded registry settings must be a regular JSON file under 2 MB')
                settings = strict_json(path.read_text())
            if not isinstance(settings,dict) or set(settings) - {'hooks'}:
                raise ValueError('Shared guard supports hook-only registry --settings; custom policy overrides were preserved and launch refused')
            inherited = settings.get('hooks',{})
            index += 2
        else:
            native.append(arg)
            index += 1
    if not isinstance(inherited,dict):
        raise ValueError('Native hooks must be an object')
    hooks = {key:list(value) for key,value in inherited.items() if isinstance(value,list)}
    for event in EVENTS:
        entry = dict(hooks=[dict(type='command',command=shlex.join([str(launcher),'--event',event]),timeout=10,onFailure='block')])
        hooks[event] = [*hooks.get(event,[]),entry]
    return native,dict(hooks=hooks)


def supervise(shared, record, owner, profile, native, args, launcher):
    store, conversation = shared.store,record['conversation']
    transition = None
    if record['phase'] != 'switching':
        transition = store.lock('transition-' + conversation)
        transition.__enter__()
    try:
        with writer(store,conversation):
            record = shared.load(conversation)
            authorize(record,owner,os.environ.get('THURBOX_ACCOUNTS_RESERVATION',''))
            if transition:
                transition.__exit__(None,None,None)
                transition = None
            shared.validate(record)
            if '--fork-session' in args or '--continue' in args or '-c' in args:
                raise ValueError('Shared sessions must resume the canonical UUID without fork/continue')
            for flag in ('--resume','-r','--session-id'):
                if flag in args and args[args.index(flag)+1] != conversation:
                    raise ValueError('Native conversation UUID differs from shared history')
            prior = shared._runtime(conversation)
            if prior.get('native_pid') or prior.get('phase') in {'starting','running'}:
                raise ValueError('Previous native shutdown is unconfirmed; inspect shared status before recovery')
            if prior.get('tools') or prior.get('subagents') or prior.get('blocked') or prior.get('uncertain'):
                raise ValueError('Previous worker activity or hook failure is unconfirmed')
            args, settings = guarded_settings(args,launcher)
            settings_path = Path(record['transcript']).parent / ('hooks-' + owner + '.json')
            atomic_write(settings_path,dumps(settings))
            update(store,conversation,owner=owner,phase='starting',native_pid=None,
                   turn='unknown',tools=[],subagents=[],blocked=False,error=None,uncertain=False,request=None,stop_result=None)
            child = None
            try:
                child = subprocess.Popen([native,*args,'--settings',str(settings_path)],
                                         env=account_env(profile),cwd=record['cwd'])
                update(store,conversation,phase='running',native_pid=child.pid)
                def forward(signum, _frame):
                    # Terminal SIGINT reaches our shared foreground group and
                    # therefore the child already; forwarding would double it.
                    if signum != signal.SIGINT and child.poll() is None:
                        child.send_signal(signum)
                previous = {sig:signal.signal(sig,forward) for sig in (signal.SIGHUP,signal.SIGTERM,signal.SIGINT)}
                try:
                    while child.poll() is None:
                        shared.validate(record)
                        control = store.read('control-' + conversation + '.json')
                        state = store.read('runtime-' + conversation + '.json')
                        if control.get('owner') == owner and control.get('request') != state.get('request') and control.get('action') == 'stop':
                            # Freeze only our own child. PreToolUse hooks complete
                            # before tools start; active tools/subagents stay marked.
                            child.send_signal(signal.SIGSTOP)
                            time.sleep(0.05)
                            state = store.read('runtime-' + conversation + '.json')
                            if safe_state(state):
                                update(store,conversation,request=control['request'],stop_result='stopping')
                                # Completed turn, no active workers: terminate the
                                # frozen parent without reopening a prompt race.
                                child.kill()
                                child.wait()
                                break
                            child.send_signal(signal.SIGCONT)
                            update(store,conversation,request=control['request'],stop_result='busy')
                        time.sleep(0.1)
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig,handler)
                shared.validate(record)
                return child.returncode
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait()
                update(store,conversation,phase='stopped',native_pid=None)
    finally:
        if transition:
            transition.__exit__(None,None,None)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    store = conversation = owner = None
    try:
        store = Profiles(Path(os.environ['THURBOX_ACCOUNTS_ROOT']))
        conversation = identifier(os.environ['THURBOX_ACCOUNTS_CONVERSATION'])
        owner = os.environ['THURBOX_SESSION']
        native = os.environ['THURBOX_ACCOUNTS_CLAUDE']
        profile_name = os.environ['THURBOX_ACCOUNTS_PROFILE']
        accounts = Accounts(store,Claude(native),Thurbox())
        shared = Shared(accounts)
        if argv[:1] == ['--event']:
            return hook(store,shared,conversation,owner,argv[1])
        record = shared.load(conversation)
        authorize(record,owner,os.environ.get('THURBOX_ACCOUNTS_RESERVATION',''))
        profile = store.get(profile_name)
        account_env(profile)  # Validate the persisted managed launch environment.
        # Auth-status checks for other selected profiles must run with their
        # own config directory, rather than inherit this process's account.
        os.environ.pop('CLAUDE_CONFIG_DIR',None)
        if record.get('is_probe'):
            if record.get('proof') != shared.proof_contract(record['profiles']):
                raise ValueError('Native proof identity/build changed')
        else:
            shared.require_proof(record['profiles'])
        profile = accounts.authenticated(profile_name)
        if record['profiles'][record['index']] != profile_name:
            raise ValueError('Managed account profile does not match the reserved owner')
        launcher = Path(sys.argv[0]).absolute()
        return supervise(shared,record,owner,profile,native,argv,launcher)
    except (OSError,ValueError,RuntimeError,TimeoutError,KeyError,IndexError) as error:
        message = redact(str(error))
        if store and conversation and owner:
            try:
                # Never let an unauthorized competing process overwrite the
                # active owner's runtime status.
                state = store.read('runtime-' + conversation + '.json')
                if argv[:1] == ['--event'] and state.get('owner') == owner:
                    update(store,conversation,turn='unknown',uncertain=True,error=message)
                elif (state.get('owner') in (None,owner) and not state.get('native_pid')
                      and state.get('phase') not in {'starting','running'} and writer_available(store,conversation)):
                    update(store,conversation,owner=owner,phase='stopped',native_pid=None,error=message)
            except (OSError,ValueError):
                pass
        print('Shared Claude launch refused: ' + message,file=sys.stderr)
        return 2 if argv[:1] == ['--event'] else 1
