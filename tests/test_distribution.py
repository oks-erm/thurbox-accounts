import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class DistributionTests(unittest.TestCase):
    def test_cli_only_offers_account_actions(self):
        result = subprocess.run([sys.executable, '-m', 'thurbox_accounts', '--help'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for action in ('login', 'start', 'handoff', 'ui-install'):
            self.assertIn(action, result.stdout)
        self.assertNotIn('adversarial', result.stdout)
        self.assertNotIn('debate', result.stdout)

    def test_payload_runs_independently_and_keeps_legacy_profile_store(self):
        manifest = tomllib.loads((ROOT / 'extension.toml').read_text())
        self.assertEqual(manifest['name'], 'thurbox-accounts')
        self.assertFalse(any('thurbox_loop' in item['path'] for item in manifest['files']))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            for item in manifest['files']:
                target = root / item['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / item.get('source', item['path']), target)
                if item.get('executable'):
                    target.chmod(0o755)
            result = subprocess.run([str(root / 'bin/thurbox-accounts'), '--accounts-dir', str(root / 'state'), 'add', 'enterprise'], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertTrue(Path(value['directory']).is_relative_to(root / 'state'))
        from thurbox_accounts.cli import parser
        self.assertEqual(parser().parse_args(['list']).accounts_dir, Path.home() / '.local/share/thurbox-loop/accounts')

    def test_no_workflow_modules_or_imports(self):
        files = list((ROOT / 'thurbox_accounts').rglob('*.py'))
        self.assertTrue(files)
        for path in files:
            text = path.read_text()
            self.assertNotIn('thurbox_loop', text, str(path))
            self.assertNotIn('from .adversarial', text, str(path))
            self.assertNotIn('class ThurboxAgent', text, str(path))
