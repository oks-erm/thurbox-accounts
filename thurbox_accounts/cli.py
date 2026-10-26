"""Standalone account-switching command line."""
import argparse
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
    installer.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
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
    profiles = Profiles(args.accounts_dir)
    service = Accounts(profiles, Claude(args.claude), Thurbox([args.thurbox_cli]))
    verb = args.account_action
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
    if args.text and verb == 'list':
        print('\n'.join(profile['name'] + ' — ' + profile['label'] + ' — ' +
              profile.get('identity', {}).get('email', 'login required') for profile in result['profiles']) or 'No profiles. Add one with Alt+a or thurbox-accounts add NAME.')
    else:
        print(dumps(result))
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(redact(str(error)), file=sys.stderr)
        return 1
