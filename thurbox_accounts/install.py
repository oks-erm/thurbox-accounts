"""Install a cloned checkout through Thurbox's working local-directory API."""
import os
from pathlib import Path
import shutil
import sys

from .agent_install import register
from .runtime import execute
from .thurbox import Thurbox, strict_json


def install_checkout(command, accounts_dir, claude, bin_dir, *, source=None):
    executable = shutil.which(command)
    if not executable:
        raise ValueError('Cannot find Thurbox CLI. Use --thurbox-cli /absolute/path/to/thurbox-cli before install.')
    executable = str(Path(executable).absolute())
    accounts_dir = accounts_dir.expanduser().absolute()
    if '/' in claude:
        claude = str(Path(claude).expanduser().absolute())
    source = (source or Path(__file__).resolve().parents[1]).resolve()
    if not (source / 'extension.toml').is_file():
        raise ValueError('Run install from the cloned checkout: ./bin/thurbox-accounts install')
    stage = 'Install runtime files'
    try:
        print('[1/4] Install runtime files from local checkout…', file=sys.stderr, flush=True)
        thurbox = Thurbox([executable])
        report = thurbox.call('extension', 'install', str(source))
        home = Path(report.get('home', ''))
        launcher = home / 'bin/thurbox-accounts'
        if not home.is_absolute() or not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise ValueError('Thurbox did not return a usable installed launcher')

        stage = 'Prepare and validate Accounts pane'
        print('[2/4] Prepare and validate Accounts pane…', file=sys.stderr, flush=True)
        directory = Path(thurbox.call('plugin', 'dir')['dir'])
        if not directory.is_absolute():
            raise ValueError('Thurbox returned a non-absolute interface directory')
        if not (directory / 'layout.lua').is_file() or not (directory / 'lib').is_dir():
            # Public scaffolding materializes Thurbox's bundled interface without
            # starting its TUI, touching credentials or granting capabilities.
            thurbox.call('plugin', 'new', 'accounts')
        result = execute([str(launcher), '--accounts-dir', str(accounts_dir), '--claude', claude,
                          '--thurbox-cli', executable, 'ui-install'], home, timeout=60)
        if result['status'] != 'PASS' or result['truncated']:
            raise RuntimeError((result.get('stderr') or result.get('stdout') or
                                'UI installer returned no diagnostic').strip())
        pane = strict_json(result['stdout'])
        if pane.get('checked', {}).get('ok') is not True:
            raise ValueError('Accounts pane did not pass plugin check')

        stage = 'Register guarded account agent'
        print('[3/4] Register guarded account agent…', file=sys.stderr, flush=True)
        agent = register(thurbox,home / 'bin/thurbox-accounts-agent')

        stage = 'Link account command'
        print('[4/4] Link account command…', file=sys.stderr, flush=True)
        bin_dir = bin_dir.expanduser().absolute()
        bin_dir.mkdir(parents=True, exist_ok=True)
        link = bin_dir / 'thurbox-accounts'
        if link.is_symlink() and link.resolve() == launcher.resolve():
            pass
        elif link.exists() or link.is_symlink():
            raise ValueError(f'{link} already exists and points elsewhere; preserved. Use {launcher} directly.')
        else:
            link.symlink_to(launcher)
        return dict(installed='thurbox-accounts', launcher=str(launcher), command=str(link),
                    pane=pane, agent=agent, next='Installation complete. Open Thurbox and press F7. Grant Accounts capabilities yourself.')
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        raise RuntimeError(f'{stage} failed: {error}') from error
