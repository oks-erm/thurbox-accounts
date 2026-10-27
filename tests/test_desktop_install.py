import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class DesktopInstallTests(unittest.TestCase):
    def test_build_preserves_unrelated_bundle_and_config_has_only_paths(self):
        from thurbox_accounts.desktop_install import install
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app = root/'Thurbox Accounts.app'
            app.mkdir()
            (app/'personal').write_text('preserve')
            with self.assertRaisesRegex(ValueError,'unrelated'):
                install(root,root/'accounts','/bin/sh','/bin/sh')
            self.assertEqual((app/'personal').read_text(),'preserve')

    def test_build_and_rerun_backup_owned_bundle_without_secrets(self):
        from thurbox_accounts.desktop_install import install
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def execute(argv,cwd,**kwargs):
                if '-o' in argv:
                    binary = Path(argv[argv.index('-o')+1]); binary.write_text('native executable'); binary.chmod(0o755)
                return dict(status='PASS',truncated=False,stderr='',stdout='')
            with patch('thurbox_accounts.desktop_install.execute',side_effect=execute):
                first = install(root,root/'accounts','/bin/sh','/bin/sh')
                second = install(root,root/'accounts','/bin/sh','/bin/sh')
            self.assertIsNone(first['backup'])
            self.assertTrue(Path(second['backup']).is_dir())
            config = json.loads((Path(second['app'])/'Contents/Resources/backend.json').read_text())
            self.assertEqual(set(config),{'argv'})
            self.assertIn(str(root/'accounts'),config['argv'])
