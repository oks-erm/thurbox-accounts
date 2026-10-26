import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from thurbox_accounts.accounts_ui import install


class UiInstallTests(unittest.TestCase):
    def test_additive_idempotent_install_and_preserved_custom_pane(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'plugins').mkdir()
            layout = root / 'layout.lua'
            layout.write_text('untouched layout')
            calls = []
            def call(*args):
                calls.append(args)
                return {'dir': str(root)} if args == ('plugin', 'dir') else {'ok': True}
            with patch('thurbox_accounts.accounts_ui.Thurbox') as adapter:
                adapter.return_value.call.side_effect = call
                first = install('/path/with space/thurbox-cli', root / 'dátá', '/path/claude')
                pane = Path(first['pane'])
                content = pane.read_text()
                self.assertNotIn('@BASE@', content)
                self.assertNotIn('@ARGS@', content)
                self.assertNotIn(r'\u00', content)
                self.assertIn('dátá', content)
                self.assertIn('capabilities = { "run", "program" }', content)
                self.assertEqual(layout.read_text(), 'untouched layout')
                self.assertFalse((root.parent / 'ui.json').exists())
                second = install('/path/with space/thurbox-cli', root / 'dátá', '/path/claude')
                self.assertIsNone(second['backup'])
                self.assertEqual(pane.read_text(), content)
                self.assertIn(('plugin', 'check'), calls)
                pane.write_text(content + '\n-- my custom pane')
                with self.assertRaisesRegex(ValueError, 'custom edits'):
                    install('thurbox-cli', root / 'dátá', 'claude')
                self.assertEqual(pane.read_text(), content + '\n-- my custom pane')

    def test_rebinds_owned_legacy_pane_without_changing_account_metadata(self):
        import hashlib
        from thurbox_accounts.accounts import Profiles
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'plugins').mkdir()
            (root / 'layout.lua').write_text('untouched layout')
            pane = root / 'plugins/90_accounts.lua'
            legacy = '-- Thurbox Loop Accounts v1.\nreturn {}\n'
            pane.write_text(legacy)
            profiles = Profiles(root / 'private-data')
            profiles.add('existing-enterprise')
            metadata = (profiles.root / 'profiles.json').read_bytes()
            profiles.write('ui-install.json', {str(pane): hashlib.sha256(legacy.encode()).hexdigest()})
            with patch('thurbox_accounts.accounts_ui.Thurbox') as adapter:
                adapter.return_value.call.side_effect = lambda *args: {'dir': str(root)} if args == ('plugin', 'dir') else {'ok': True}
                result = install('thurbox-cli', profiles.root, 'claude')
            self.assertEqual(Path(result['backup']).read_text(), legacy)
            self.assertEqual((profiles.root / 'profiles.json').read_bytes(), metadata)
            self.assertIn('bin/thurbox-accounts', pane.read_text())
            self.assertNotIn('bin/thurbox-loop', pane.read_text())
