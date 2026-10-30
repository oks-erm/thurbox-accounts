"""Standalone account-switching command line."""
import argparse
import contextlib
import io
import math
import signal
import sys
from pathlib import Path
from .accounts import Profiles, Claude, Accounts
from .core import dumps, redact
from .thurbox import Thurbox

def parser():
    parser = argparse.ArgumentParser(prog='thurbox-accounts', description='Isolated Claude Enterprise browser/SSO profiles')
    parser.add_argument('--accounts-dir', type=Path, default=Path.home() / '.local/share/thurbox-loop/accounts')
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--thurbox-cli', default='thurbox-cli')
    parser.add_argument('--desktop-deadline',type=float,help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest='account_action', required=True)
    for verb in ('add', 'login', 'status', 'start', 'verify-handoff'):
        command = commands.add_parser(verb)
        command.add_argument('name')
        if verb == 'add':
            command.add_argument('--label')
        if verb == 'start':
            command.add_argument('--repo', type=Path, required=True)
            command.add_argument('--name', dest='session_name', required=True)
    installer = commands.add_parser('install', help='Install this cloned checkout, command and Accounts pane')
    desktop_install = commands.add_parser('desktop-install', help='Build/install the native macOS companion (requires Swift command-line tools)')
    desktop_install.add_argument('--app-dir', type=Path, default=Path.home() / 'Applications')
    installer.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    verification = commands.add_parser('verify-shared', help='Native shared-history proof; synthetic model requests up to $0.25 each')
    verification.add_argument('profiles', nargs='+')
    enrollment = commands.add_parser('enable-shared', help='Approve one selected stopped conversation for ordered account profiles')
    enrollment.add_argument('--session', required=True)
    enrollment.add_argument('--profile', action='append', required=True)
    enrollment.add_argument('--consent', action='store_true')
    for action in ('switch','shared-status','recover-shared'):
        command = commands.add_parser(action)
        command.add_argument('conversation', nargs='?')
        command.add_argument('--session')
        if action == 'switch':
            command.add_argument('--expected-profile')
    commands.add_parser('sync-accounts')
    simple_preview=commands.add_parser('simple-preview')
    simple_preview.add_argument('--session',required=True); simple_preview.add_argument('--to',required=True)
    simple_confirm=commands.add_parser('simple-confirm')
    simple_confirm.add_argument('token'); simple_confirm.add_argument('--consent',action='store_true')
    pane_state = commands.add_parser('pane-state')
    pane_state.add_argument('--session')
    mode_preview = commands.add_parser('mode-preview',help='Review switching mode for an existing stopped local conversation')
    mode_preview.add_argument('--session',required=True)
    mode_preview.add_argument('--profile',action='append',required=True)
    mode_enable = commands.add_parser('mode-enable')
    mode_enable.add_argument('token')
    mode_enable.add_argument('--consent',action='store_true')
    for action in ('mode-on','mode-off'):
        mode_toggle = commands.add_parser(action)
        mode_toggle.add_argument('--session',required=True)
    pane_add = commands.add_parser('pane-add')
    pane_add.add_argument('label')
    pane_run = commands.add_parser('pane-run')
    pane_run.add_argument('operation',nargs=argparse.REMAINDER)
    commands.add_parser('desktop-state')
    for action in ('desktop-capture','desktop-send','desktop-key','desktop-stop','desktop-start'):
        command = commands.add_parser(action)
        command.add_argument('session')
        if action in {'desktop-send','desktop-key'}:
            command.add_argument('value')
    commands.add_parser('list')
    handoff = commands.add_parser('handoff')
    handoff.add_argument('--session')
    handoff.add_argument('--to')
    handoff.add_argument('--confirm')
    commands.add_parser('ui-install')
    # JSON is the stable automation output; --text gives compact human output.
    for command in commands.choices.values():
        command.add_argument('--json', action='store_true')
        command.add_argument('--text', action='store_true')

    return parser


def run(args):
    if args.account_action == 'install':
        from .install import install_checkout
        print(dumps(install_checkout(args.thurbox_cli, args.accounts_dir, args.claude, args.bin_dir)))
        return 0
    if args.account_action == 'desktop-install':
        from .desktop_install import install
        print(dumps(install(args.app_dir,args.accounts_dir,args.claude,args.thurbox_cli)))
        return 0
    profiles = Profiles(args.accounts_dir)
    service = Accounts(profiles, Claude(args.claude), Thurbox([args.thurbox_cli]))
    verb = args.account_action
    if verb in {'pane-state','pane-add','pane-run'}:
        from .pane import OPERATIONS, add, receipt, snapshot
        if verb == 'pane-state':
            print(snapshot(service,args.session))
        elif verb == 'pane-add':
            print(dumps(add(profiles,args.label)))
        else:
            operation = args.operation
            if not operation or operation[0] not in OPERATIONS:
                raise ValueError('Unsupported Accounts pane operation')
            prefix = ['--accounts-dir',str(profiles.root),'--claude',args.claude,'--thurbox-cli',args.thurbox_cli]
            target = parser().parse_args([*prefix,*operation])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run(target)
            from .thurbox import strict_json
            print(receipt(operation[0],strict_json(output.getvalue())))
        return 0
    if verb == 'sync-accounts':
        from .agent_install import register_profiles
        print(dumps(register_profiles(service,Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent')))
        return 0
    if verb.startswith('simple-'):
        from .simple import Simple
        simple=Simple(service)
        value=simple.preview(args.session,args.to) if verb=='simple-preview' else simple.confirm(args.token,consent=args.consent)
        print(dumps(value)); return 0
    if verb.startswith('mode-'):
        from .mode import Mode
        mode = Mode(service)
        if verb == 'mode-preview': result = mode.preview(args.session,args.profile)
        elif verb == 'mode-enable': result = mode.enable(args.token,consent=args.consent)
        else: result = mode.set_enabled(args.session,verb=='mode-on')
        print(dumps(result))
        return 0
    if verb.startswith('desktop-'):
        from .desktop import Desktop
        desktop = Desktop(service)
        action = verb.removeprefix('desktop-')
        result = desktop.state() if action == 'state' else getattr(desktop,action)(args.session,*([args.value] if hasattr(args,'value') else []))
        print(dumps(result))
        return 0
    if verb in {'verify-shared','enable-shared','switch','shared-status','recover-shared'}:
        from .shared import Shared
        shared = Shared(service)
        if verb == 'verify-shared':
            from .shared_probe import verify
            result = verify(service,args.profiles)
        elif verb == 'enable-shared':
            result = shared.enroll(args.session,args.profile,consent=args.consent)
        else:
            conversation = args.conversation
            if args.session and not conversation:
                row = service.thurbox.call('session','get',args.session)
                conversation = row.get('agent_session_id')
                record = shared.load(conversation)
                if verb == 'switch' and row.get('id') != record['allowed_session']:
                    raise ValueError('Select the current managed session before switching')
            elif not conversation or args.session:
                raise ValueError('Specify a conversation UUID or --session REF')
            if verb == 'switch':
                result = shared.switch(conversation,expected_profile=args.expected_profile)
            elif verb == 'recover-shared':
                result = shared.recover(conversation)
            else:
                result = shared.load(conversation)
                result['runtime'] = shared._runtime(conversation)
                result['next_profile'] = result['profiles'][(result['index']+1)%len(result['profiles'])]
        print(dumps(result))
        return 0
    if verb == 'add':
        result = profiles.add(args.name, args.label)
    elif verb == 'list':
        result = {'profiles': [profiles.get(name) for name in profiles.read('profiles.json')]}
    elif verb == 'login':
        code = service.claude.login(profiles.get(args.name))
        if code:
            return code
        result = service.status(args.name)
    elif verb == 'status':
        result = service.status(args.name)
    elif verb == 'start':
        result = service.start(args.name, args.repo, args.session_name)
    elif verb == 'verify-handoff':
        result = service.verify_handoff(args.name)
    elif verb == 'handoff':
        if args.confirm and not (args.session or args.to):
            result = service.confirm(args.confirm)
        elif args.session and args.to and not args.confirm:
            result = service.preview(args.session, args.to)
        else:
            raise ValueError('Use --session SOURCE --to PROFILE to preview, or --confirm PLAN_ID')
    else:
        from .accounts_ui import install
        result = install(args.thurbox_cli, profiles.root, args.claude)
    if verb in {'status','login'} and result.get('loggedIn'):
        from .agent_install import register_profiles
        register_profiles(service,Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent')
    if args.text and verb == 'list':
        print('\n'.join(profile['name'] + ' — ' + profile['label'] + ' — ' +
              profile.get('identity', {}).get('email', 'login required') for profile in result['profiles']) or 'No profiles. Click Add account in Accounts or run thurbox-accounts add NAME.')
    else:
        print(dumps(result))
    return 0


@contextlib.contextmanager
def desktop_deadline(seconds):
    if seconds is None:
        yield
        return
    if not math.isfinite(seconds) or not 0 < seconds <= 3600:
        raise ValueError('Desktop deadline must be between 0 and 3600 seconds')
    def interrupt(signum, frame):
        # Raising through runtime.execute runs its process-group cleanup before
        # the desktop can accept another operation. Never retry a mutation here.
        raise TimeoutError('Desktop operation deadline/cancellation reached; child cleanup completed. Inspect session state before retrying.')
    old_alarm = signal.signal(signal.SIGALRM,interrupt)
    old_term = signal.signal(signal.SIGTERM,interrupt)
    previous = signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,*previous)
        signal.signal(signal.SIGALRM,old_alarm)
        signal.signal(signal.SIGTERM,old_term)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        with desktop_deadline(args.desktop_deadline):
            return run(args)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(redact(str(error)), file=sys.stderr)
        return 1
