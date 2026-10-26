"""Additive live-interface delivery; never grants capabilities or edits ui.json."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import time

from .core import atomic_write
from .thurbox import Thurbox


def install(command: str, accounts_dir: Path, claude: str):
    from .accounts import Profiles
    profiles = Profiles(accounts_dir)
    thurbox = Thurbox([command])
    directory = Path(thurbox.call('plugin', 'dir')['dir'])
    if not directory.is_absolute() or not (directory / 'layout.lua').is_file():
        raise ValueError('Thurbox has no materialized interface; run thurbox-cli plugin new accounts first')
    # Reuse the existing center switch slot; no layout or shared library edits.
    launcher = Path(__file__).resolve().parents[1] / 'bin/thurbox-accounts'
    if not launcher.is_file():
        executable = shutil.which('thurbox-accounts')
        if not executable:
            raise ValueError('Cannot find the standalone thurbox-accounts launcher')
        launcher = Path(executable).resolve()
    args = ['--accounts-dir', str(accounts_dir), '--claude', claude, '--thurbox-cli', command]
    template = Path(__file__).with_name('ui') / 'accounts.lua'
    text = template.read_text().replace('@BASE@', json.dumps(shlex.join([str(launcher), *args]), ensure_ascii=False))
    text = text.replace('@EXECUTABLE@', json.dumps(str(launcher), ensure_ascii=False)).replace('@ARGS@',
        '{ ' + ', '.join(json.dumps(item, ensure_ascii=False) for item in args) + ' }')
    destination = directory / 'plugins/90_accounts.lua'
    if destination.is_symlink():
        raise ValueError('Accounts pane must not be a symlink')
    delivered = profiles.read('ui-install.json')
    prior = delivered.get(str(destination))
    backup = None
    if destination.exists() and destination.read_text() != text:
        current = destination.read_text()
        if not (current.startswith('-- A starting point.') or
                prior == hashlib.sha256(current.encode()).hexdigest()):
            raise ValueError('Existing Accounts pane has custom edits; preserve it and install manually')
        backup = destination.with_name(destination.name + '.bak.' + str(time.time_ns()))
        shutil.copy2(destination, backup)
    if not destination.exists() or destination.read_text() != text:
        atomic_write(destination, text)
    delivered[str(destination)] = hashlib.sha256(text.encode()).hexdigest()
    profiles.write('ui-install.json', delivered)
    check = thurbox.call('plugin', 'check')
    return dict(pane=str(destination), backup=str(backup) if backup else None, checked=check,
                next='Alt+F7 opens Accounts. Grant run/program in Ctrl+, → ] → t. No capabilities were granted.')
