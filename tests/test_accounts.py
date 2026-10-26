import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from thurbox_accounts.accounts import Accounts, Profiles, Claude, account_env


class FakeClaude:
    def status(self, profile):
        return dict(loggedIn=True, authMethod='claude.ai', configDirectory=profile['directory'],
                    email=profile['name'] + '@example.invalid', orgId=profile['name'])

    def fingerprint(self):
        return 'native-test-build'


class FakeThurbox:
    def __init__(self):
        self.calls = []
        self.sessions = {}

    def call(self, *args):
        self.calls.append(args)
        if args[:2] == ('session', 'create'):
            value = dict(id='new-session', cwd=args[args.index('--repo-path') + 1], agent='claude',
                         agent_session_id='22222222-2222-4222-8222-222222222222', stopped=False)
            self.sessions[value['id']] = value
            return value
        if args[:2] == ('session', 'get'):
            return dict(self.sessions[args[2]])
        return {}


class AccountFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profiles = Profiles(self.root / 'accounts')
        self.a = self.profiles.add('work-a', 'Enterprise A')
        self.b = self.profiles.add('work-b', 'Enterprise B')
        self.tb = FakeThurbox()
        self.service = Accounts(self.profiles, FakeClaude(), self.tb)
        self.launch_check = patch.object(self.service, 'check_launch')
        self.launch_check.start()
        self.addCleanup(self.launch_check.stop)

    def source(self):
        self.service.start('work-a', self.root, 'Source')
        row = self.tb.sessions['new-session']
        row['stopped'] = True
        path = Path(self.a['directory']) / 'projects' / '-test' / (row['agent_session_id'] + '.jsonl')
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(type='user', sessionId=row['agent_session_id'],
              message=dict(role='user', content='Only this conversation'))) + '\n')
        row['transcript_path'] = str(path)
        self.service.status('work-b')
        self.profiles.write('compatibility.json', {'work-b': dict(fingerprint='native-test-build',
            identity=self.profiles.get('work-b')['identity'])})
        return row, path



class AccountTests(AccountFixture):
    def test_profiles_private_distinct_and_no_overwrite(self):
        self.assertNotEqual(self.a['directory'], self.b['directory'])
        self.assertEqual(Path(self.a['directory']).stat().st_mode & 0o777, 0o700)
        with self.assertRaises(ValueError):
            self.profiles.add('work-a', 'Again')
        for bad in ['../escape', 'Work A', '-option', '', 'a/b']:
            with self.assertRaises(ValueError):
                self.profiles.add(bad, 'bad')

    def test_symlinked_profile_refused(self):
        Path(self.a['directory']).rmdir()
        Path(self.a['directory']).symlink_to(Path(self.b['directory']), target_is_directory=True)
        with self.assertRaises(ValueError):
            self.profiles.get('work-a')

    def test_conflicting_auth_fails_without_exposing_value(self):
        for key in ['ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_BASE_URL',
                    'CLAUDE_CODE_USE_BEDROCK', 'ANTHROPIC_AUTH_TOKEN']:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key) as error:
                account_env(self.a, {key: 'private-value'})
            self.assertNotIn('private-value', str(error.exception))
        self.assertEqual(account_env(self.a, {})['CLAUDE_CONFIG_DIR'], self.a['directory'])

    def test_status_rejects_other_profile_and_pins_identity(self):
        self.service.status('work-a')
        with patch.object(self.service.claude, 'status', return_value=dict(loggedIn=True,
                authMethod='claude.ai', configDirectory=self.b['directory'], email='wrong')):
            with self.assertRaises(ValueError):
                self.service.status('work-a')
        with patch.object(self.service.claude, 'status', return_value=dict(loggedIn=True,
                authMethod='claude.ai', configDirectory=self.a['directory'], email='changed', orgId='work-a')):
            with self.assertRaises(ValueError):
                self.service.status('work-a')

    def test_new_session_persists_profile_env_and_binding(self):
        result = self.service.start('work-a', self.root, 'Enterprise session')
        create = self.tb.calls[0]
        self.assertIn('CLAUDE_CONFIG_DIR=' + self.a['directory'], create)
        self.assertEqual(result['id'], 'new-session')
        self.assertEqual(self.profiles.read('bindings.json')['new-session']['profile'], 'work-a')

    def test_handoff_requires_native_proof_before_any_copy(self):
        with self.assertRaisesRegex(ValueError, 'verify-handoff'):
            self.service.preview('new-session', 'work-b')
        self.assertFalse((self.profiles.root / 'snapshots').exists())

    def test_preview_copies_nothing_and_active_source_is_refused(self):
        row, path = self.source()
        row['stopped'] = False
        with self.assertRaisesRegex(ValueError, 'stop'):
            self.service.preview('new-session', 'work-b')
        row['stopped'] = True
        plan = self.service.preview('new-session', 'work-b')
        self.assertFalse((self.profiles.root / 'snapshots').exists())
        self.assertEqual(plan['target'], 'work-b')
        self.assertEqual(path.read_text().count('Only this'), 1)

    def test_stale_expired_and_single_use_confirmation(self):
        row, path = self.source()
        plan = self.service.preview('new-session', 'work-b')
        path.write_text(path.read_text() + '{}\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.confirm(plan['id'])
        with self.assertRaises(ValueError):
            self.service.confirm(plan['id'])
        plan = self.service.preview('new-session', 'work-b')
        with patch('thurbox_accounts.accounts.time.time', return_value=plan['expires'] + 1):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.service.confirm(plan['id'])

    def test_native_auth_output_is_whitelisted(self):
        value = dict(loggedIn=False, authMethod='none', configDirectory=self.a['directory'], secret='private')
        with patch('thurbox_accounts.accounts.execute', return_value=dict(status='FAIL', exit_code=1,
                stdout=json.dumps(value), truncated=False)):
            result = Claude('/fake/claude').status(self.a)
        self.assertNotIn('secret', result)


class ConfirmationTests(AccountFixture):
    def test_confirm_forks_natively_then_resumes_uuid_without_replaying_snapshot(self):
        row, source = self.source()
        original = source.read_bytes()
        plan = self.service.preview('new-session', 'work-b')
        def create(*args):
            if args[:2] == ('session', 'create'):
                self.tb.calls.append(args)
                return dict(id='destination', agent_session_id=args[args.index('--resume') + 1])
            return FakeThurbox.call(self.tb, *args)
        with patch.object(self.service, 'native_fork') as fork, patch.object(self.tb, 'call', side_effect=create):
            result = self.service.confirm(plan['id'])
        self.assertEqual(result['state'], 'created')
        self.assertEqual(source.read_bytes(), original)
        self.assertNotIn('--agent-arg', self.tb.calls[-1])
        snapshot = fork.call_args.args[1]
        self.assertEqual(snapshot.read_bytes(), original)
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o400)
        with self.assertRaisesRegex(ValueError, 'consumed'):
            self.service.confirm(plan['id'])

    def test_failed_native_fork_preserves_source_and_recovery(self):
        row, source = self.source()
        plan = self.service.preview('new-session', 'work-b')
        with patch.object(self.service, 'native_fork', side_effect=ValueError('native refusal')):
            with self.assertRaisesRegex(ValueError, 'native refusal'):
                self.service.confirm(plan['id'])
        operation = self.profiles.read('operation-' + plan['id'] + '.json')
        self.assertEqual(operation['state'], 'failed')
        self.assertEqual(operation['recovery'], ['thurbox-cli', 'session', 'start', 'new-session'])
        self.assertTrue(row['stopped'])

    def test_auth_or_build_change_invalidates_compatibility(self):
        self.source()
        with patch.object(self.service.claude, 'fingerprint', return_value='updated'):
            with self.assertRaisesRegex(ValueError, 'verify-handoff'):
                self.service.preview('new-session', 'work-b')

    def test_per_session_lock_refuses_competing_confirmation(self):
        self.source()
        plan = self.service.preview('new-session', 'work-b')
        with self.profiles.lock('session-new-session'):
            with self.assertRaisesRegex(ValueError, 'progress'):
                self.service.confirm(plan['id'])

class LaunchChecks(AccountFixture):
    def test_actual_check_refuses_tmux_session_auth_even_with_clean_global_env(self):
        self.launch_check.stop()
        self.service.claude.executable = '/bin/sh'
        def call(*args):
            if args[:2] == ('agent', 'launch-args'):
                return dict(command='/bin/sh', env={})
            return dict(tmux_socket='fixture', tmux_tmpdir='/private/tmp/socket-fixture')
        def execute(argv, cwd, **kwargs):
            self.assertEqual(kwargs['env']['TMUX_TMPDIR'], '/private/tmp/socket-fixture')
            return dict(status='PASS', truncated=False, stdout=(
                '$0\n' if 'list-sessions' in argv else
                'ANTHROPIC_API_KEY=private-value\n' if '-t' in argv else 'PATH=/bin\n'))
        with patch.object(self.tb, 'call', side_effect=call), patch('thurbox_accounts.accounts.execute', side_effect=execute):
            with self.assertRaisesRegex(ValueError, 'ANTHROPIC_API_KEY') as error:
                self.service.check_launch(self.a)
        self.assertNotIn('private-value', str(error.exception))

    def test_launch_registry_binary_mismatch_is_refused(self):
        self.launch_check.stop()
        self.service.claude.executable = '/bin/sh'
        with patch.object(self.tb, 'call', return_value=dict(command='/bin/ls', env={})):
            with self.assertRaisesRegex(ValueError, 'differs'):
                self.service.check_launch(self.a)

    def test_registry_lock_is_held_before_spawn(self):
        def create(*args):
            if args[:2] == ('session', 'create'):
                with self.assertRaisesRegex(ValueError, 'progress'):
                    with self.profiles.lock():
                        pass
                return dict(id='locked-spawn')
            return {}
        with patch.object(self.tb, 'call', side_effect=create):
            self.service.start('work-a', self.root, 'locked')
        self.assertIn('locked-spawn', self.profiles.read('bindings.json'))


if __name__ == '__main__':
    unittest.main()

class AccountCliTests(unittest.TestCase):
    def test_cli_add_list_and_private_environment_failure(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'accounts'
            command = [sys.executable, '-m', 'thurbox_accounts', '--accounts-dir', str(root)]
            first = subprocess.run([*command, 'add', 'work', '--label', 'Company'], capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            listed = subprocess.run([*command, 'list', '--text'], capture_output=True, text=True)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn('work — Company', listed.stdout)
            failed = subprocess.run([*command, 'status', 'work'], capture_output=True, text=True,
                env=dict(os.environ, ANTHROPIC_API_KEY='private-api-value'))
            self.assertEqual(failed.returncode, 1)
            self.assertIn('ANTHROPIC_API_KEY', failed.stderr)
            self.assertNotIn('private-api-value', failed.stderr + failed.stdout)
