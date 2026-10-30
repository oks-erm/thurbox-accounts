"""Additive live-interface delivery; never grants capabilities or edits ui.json."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import time

from .core import atomic_write
from .thurbox import Thurbox

# Exact unedited `plugin new accounts` starter shipped by Thurbox 2.75/2.76.
_STARTER_SHA256 = "d5e0023d8ab5091c21afeb121b3415bd2e13cffde6561fb79f3290ed8d7cfed7"


def install(command: str, accounts_dir: Path, claude: str):
    from .accounts import Profiles
    profiles = Profiles(accounts_dir)
    thurbox = Thurbox([command])
    directory = Path(thurbox.call('plugin', 'dir')['dir'])
    if not directory.is_absolute() or not (directory / 'layout.lua').is_file():
        raise ValueError('Thurbox has no materialized interface; run thurbox-cli plugin new accounts first')
    # Reuse center and the public automatic strips loop; no layout/library edits.
    launcher = Path(__file__).resolve().parents[1] / 'bin/thurbox-accounts'
    if not launcher.is_file():
        executable = shutil.which('thurbox-accounts')
        if not executable:
            raise ValueError('Cannot find the standalone thurbox-accounts launcher')
        launcher = Path(executable).resolve()
    args = ['--accounts-dir', str(accounts_dir), '--claude', claude, '--thurbox-cli', command]
    delivered = profiles.read('ui-install.json')
    pending = []
    # Preflight both owned files before writing either; preserve custom panes.
    for template_name, filename in [('accounts.lua', '90_accounts.lua'),
                                    ('account_status.lua', '91_account_status.lua')]:
        template = Path(__file__).with_name('ui') / template_name
        text = template.read_text().replace('@BASE@', json.dumps(shlex.join([str(launcher), *args]), ensure_ascii=False))
        text = text.replace('@EXECUTABLE@', json.dumps(str(launcher), ensure_ascii=False)).replace('@ARGS@',
            '{ ' + ', '.join(json.dumps(item, ensure_ascii=False) for item in args) + ' }')
        destination = directory / 'plugins' / filename
        if destination.is_symlink():
            raise ValueError('Accounts pane must not be a symlink')
        current = destination.read_text() if destination.exists() else None
        if current is not None and current != text:
            digest = hashlib.sha256(current.encode()).hexdigest()
            starter = filename == '90_accounts.lua' and digest == _STARTER_SHA256
            if not (starter or delivered.get(str(destination)) == digest):
                raise ValueError('Existing Accounts pane has custom edits; preserve it and install manually')
        pending.append((destination, text, current))
    backups = {}
    for destination, text, current in pending:
        if current is not None and current != text:
            backup = destination.with_name(destination.name + '.bak.' + str(time.time_ns()))
            shutil.copy2(destination, backup)
            backups[str(destination)] = str(backup)
        if current != text:
            atomic_write(destination, text)
        delivered[str(destination)] = hashlib.sha256(text.encode()).hexdigest()
    profiles.write('ui-install.json', delivered)
    destination = pending[0][0]
    check = thurbox.call('plugin', 'check')
    return dict(pane=str(destination), indicator=str(pending[1][0]), backup=backups.get(str(destination)),
                backups=backups, checked=check,
                next='F10 reloads; F7 opens Accounts. Allow run/program for Accounts and run for account-status in Settings → Interface. No capabilities were granted.')
