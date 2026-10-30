import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class CreationUiTests(unittest.TestCase):
    def test_only_recognized_template_is_adapted_and_owns_exact_output(self):
        from thurbox_accounts.creation_ui import adapt
        source='local function agents()\n  return (thurbox and thurbox.agents) or {}\nend\nreturn frame("Coding Agent", height + 4, {})\n'
        with patch('thurbox_accounts.creation_ui.PRISTINE',{hashlib.sha256(source.encode()).hexdigest()}):
            output=adapt(source)
            self.assertIn('Claude — ',output)
            self.assertIn('claude-accounts',output)
            self.assertIn('Agent / account',output)
            with self.assertRaisesRegex(ValueError,'custom|unsupported'):
                adapt(source+'-- custom\n')

    def test_custom_creation_pane_prevents_any_other_ui_file_update(self):
        from thurbox_accounts.accounts_ui import install
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); (root/'plugins').mkdir(); (root/'layout.lua').write_text('layout')
            pane=root/'plugins/70_new_session.lua'; pane.write_text('-- custom creation flow')
            with patch('thurbox_accounts.accounts_ui.Thurbox') as adapter:
                adapter.return_value.call.side_effect=lambda *a: {'dir':str(root)} if a==('plugin','dir') else {'ok':True}
                with self.assertRaisesRegex(ValueError,'custom|unsupported'):
                    install('thurbox-cli',root/'state','claude')
            self.assertEqual(pane.read_text(),'-- custom creation flow')
            self.assertFalse((root/'plugins/90_accounts.lua').exists())
