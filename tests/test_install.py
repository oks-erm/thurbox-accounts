import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from thurbox_accounts.cli import main


class InstallTests(unittest.TestCase):
    def test_install_action_available_and_missing_cli_has_actionable_error(self):
        from thurbox_accounts.cli import parser
        self.assertEqual(parser().parse_args(['install']).account_action, 'install')
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = main(['--thurbox-cli', '/missing/thurbox-cli', 'install'])
        self.assertEqual(code, 1)
        self.assertIn('Cannot find Thurbox CLI', errors.getvalue())
        self.assertNotIn('Traceback', errors.getvalue())

    def fixture(self, root):
        source = root / 'source'
        source.mkdir()
        (source / 'extension.toml').write_text('name="thurbox-accounts"')
        home = root / 'installed'
        (home / 'bin').mkdir(parents=True)
        launcher = home / 'bin/thurbox-accounts'
        launcher.write_text('#!/bin/sh\nexit 0\n')
        launcher.chmod(0o755)
        (home / 'bin/thurbox-accounts-agent').write_text('#!/bin/sh\nexit 0\n')
        registry = root / 'agents.toml'
        registry.write_text('config_version=1\ndefault="claude"\n[[agents]]\nname="claude"\ncommand="claude"\n')
        ui = root / 'live-ui'
        ui.mkdir()
        calls = []
        def call(*args):
            calls.append(args)
            if args[:2] == ('extension', 'install'):
                self.assertEqual(args[2], str(source))
                self.assertNotIn('git+', args[2])
                return {'home': str(home)}
            if args == ('config','show'):
                return {'paths':{'agents_toml':str(registry)}}
            if args == ('plugin', 'dir'):
                return {'dir': str(ui)}
            if args == ('plugin', 'new', 'accounts'):
                (ui / 'layout.lua').write_text('materialized')
                (ui / 'lib').mkdir()
                return {'ok': True}
            return {'ok': True}
        return source, home, launcher, ui, calls, call

    def test_local_install_materializes_ui_links_safely_and_reruns(self):
        from thurbox_accounts.install import install_checkout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, home, launcher, ui, calls, call = self.fixture(root)
            result = {'status': 'PASS', 'truncated': False, 'stdout': json.dumps({'checked': {'ok': True}})}
            with patch('thurbox_accounts.install.Thurbox') as adapter, patch('thurbox_accounts.install.execute', return_value=result):
                adapter.return_value.call.side_effect = call
                first = install_checkout('/bin/sh', root / 'data', 'claude', root / 'bin', source=source)
                self.assertEqual((root / 'bin/thurbox-accounts').resolve(), launcher)
                self.assertIn(('plugin', 'new', 'accounts'), calls)
                second = install_checkout('/bin/sh', root / 'data', 'claude', root / 'bin', source=source)
                self.assertEqual(first['launcher'], second['launcher'])
                self.assertEqual(calls.count(('plugin', 'new', 'accounts')), 1)

    def test_failed_first_stage_stops_with_clear_phase_and_does_not_touch_link(self):
        from thurbox_accounts.install import install_checkout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, home, launcher, ui, calls, call = self.fixture(root)
            with patch('thurbox_accounts.install.Thurbox') as adapter:
                adapter.return_value.call.side_effect = RuntimeError('installer returned failure')
                with self.assertRaisesRegex(RuntimeError, 'Install runtime files.*installer returned failure'):
                    install_checkout('/bin/sh', root / 'data', 'claude', root / 'bin', source=source)
                self.assertEqual(adapter.return_value.call.call_count, 1)
            self.assertFalse((root / 'bin').exists())

    def test_link_collision_is_preserved_with_installed_launcher_recovery(self):
        from thurbox_accounts.install import install_checkout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, home, launcher, ui, calls, call = self.fixture(root)
            (root / 'bin').mkdir()
            occupied = root / 'bin/thurbox-accounts'
            occupied.write_text('user command')
            result = {'status': 'PASS', 'truncated': False, 'stdout': json.dumps({'checked': {'ok': True}})}
            with patch('thurbox_accounts.install.Thurbox') as adapter, patch('thurbox_accounts.install.execute', return_value=result):
                adapter.return_value.call.side_effect = call
                with self.assertRaisesRegex(RuntimeError, 'Link account command failed.*already exists.*preserved'):
                    install_checkout('/bin/sh', root / 'data', 'claude', root / 'bin', source=source)
            self.assertEqual(occupied.read_text(), 'user command')

    def test_rerun_accepts_only_native_hook_patch_not_custom_agent_args(self):
        from thurbox_accounts.agent_install import register
        from thurbox_accounts.thurbox import Thurbox
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, home, launcher, ui, calls, call = self.fixture(root)
            guard = home/'bin/thurbox-accounts-agent'
            adapter = Thurbox()
            with patch.object(adapter,'call',side_effect=call):
                register(adapter,guard)
                native = root/'hooks/claude.json'
                native.parent.mkdir()
                native.write_text('{"hooks":{}}')
                registry = root/'agents.toml'
                text = registry.read_text().replace('\nargs = []\n','\nargs = ' + json.dumps(['--settings',str(native)]) + '\n')
                registry.write_text(text)
                self.assertFalse(register(adapter,guard)['added'])
                registry.write_text(text.replace(str(native),str(root/'custom.json')))
                with self.assertRaisesRegex(ValueError,'custom edits'):
                    register(adapter,guard)
