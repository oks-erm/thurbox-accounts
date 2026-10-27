import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_accounts import FakeClaude, FakeThurbox
from thurbox_accounts.accounts import Accounts, Profiles
from thurbox_accounts.shared import Shared


class SharedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = Profiles(self.root / 'state')
        self.a = self.store.add('a')
        self.b = self.store.add('b')
        self.tb = FakeThurbox()
        self.accounts = Accounts(self.store, FakeClaude(), self.tb)
        self.accounts.check_launch = lambda profile: None
        for name in ('a','b'):
            self.accounts.status(name)
        self.shared = Shared(self.accounts)
        self.uuid = '33333333-3333-4333-8333-333333333333'
        self.path = Path(self.a['directory']) / 'projects/-project' / (self.uuid + '.jsonl')
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"type":"user","message":{"content":"local context"}}\n')
        sidecars = self.path.with_suffix('')
        sidecars.mkdir()
        (sidecars/'worker.json').write_text('selected sidecar')
        self.tb.sessions['source'] = dict(id='source',agent='claude',agent_session_id=self.uuid,
            cwd=str(self.root),stopped=True,transcript_path=str(self.path))
        self.store.write('bindings.json', {'source':dict(profile='a',identity=self.store.get('a')['identity'],
            cwd=str(self.root),agent_session_id=self.uuid)})

    def proof(self):
        self.store.write('shared-proof.json',self.shared.proof_contract(['a','b']))

    def test_enrollment_requires_consent_and_real_proof_before_moving_history(self):
        with self.assertRaisesRegex(ValueError,'consent'):
            self.shared.enroll('source',['a','b'],consent=False)
        with self.assertRaisesRegex(ValueError,'verify-shared'):
            self.shared.enroll('source',['a','b'],consent=True)
        self.assertFalse(self.path.is_symlink())

    def test_enrollment_shares_only_selected_history_and_keeps_same_uuid(self):
        self.proof()
        other = self.path.with_name('other.jsonl')
        other.write_text('unrelated')
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        self.assertEqual(record['conversation'],self.uuid)
        for alias in record['aliases']:
            self.assertTrue(Path(alias['transcript']).is_symlink())
            self.assertEqual(Path(alias['transcript']).resolve(),Path(record['transcript']))
            self.assertTrue(Path(alias['sidecars']).is_symlink())
        self.assertEqual(other.read_text(),'unrelated')
        self.assertFalse(other.is_symlink())
        self.assertEqual((Path(record['sidecars'])/'worker.json').read_text(),'selected sidecar')

    def test_unknown_or_replaced_alias_fails_closed_without_rewriting_it(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        alias = Path(record['aliases'][1]['transcript'])
        alias.unlink()
        alias.write_text('native replacement')
        with self.assertRaisesRegex(ValueError,'reference'):
            self.shared.validate(record)
        self.assertEqual(alias.read_text(),'native replacement')

    def test_profile_identity_change_invalidates_proof(self):
        self.proof()
        with patch.object(self.accounts.claude,'fingerprint',return_value='upgrade'):
            with self.assertRaisesRegex(ValueError,'verify-shared'):
                self.shared.enroll('source',['a','b'],consent=True)

    def test_pending_reservation_blocks_old_managed_owner(self):
        from thurbox_accounts.guard import authorize
        record=dict(allowed_session='new',phase='switching',reservation='nonce')
        with self.assertRaisesRegex(ValueError,'owner'):
            authorize(record,'old','nonce')
        with self.assertRaisesRegex(ValueError,'reservation'):
            authorize(record,'new','wrong')
        authorize(record,'new','nonce')

    def test_canonical_parent_replacement_is_refused(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        folder = Path(record['transcript']).parent
        moved = folder.with_name(folder.name + '-moved')
        folder.rename(moved)
        folder.symlink_to(moved,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'parent'):
            self.shared.validate(record)

    def test_unconfirmed_workers_prevent_recovery_launch(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        self.store.write('runtime-' + self.uuid + '.json',dict(native_pid=None,tools=['pending']))
        with self.assertRaisesRegex(ValueError,'activity'):
            self.shared._launch(record,0)
        self.assertFalse(any(c[:2] == ('session','create') for c in self.tb.calls))

    def test_direct_restart_preserves_unconfirmed_orphan_evidence(self):
        from thurbox_accounts.guard import main
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(allowed_session='owner',phase='active')
        self.shared.save(record)
        state = dict(owner='owner',phase='running',native_pid=123456,tools=[],subagents=[],blocked=False)
        self.store.write('runtime-' + self.uuid + '.json',state)
        env = dict(THURBOX_ACCOUNTS_ROOT=str(self.store.root),THURBOX_ACCOUNTS_CONVERSATION=self.uuid,
            THURBOX_SESSION='owner',THURBOX_ACCOUNTS_CLAUDE='/bin/true',THURBOX_ACCOUNTS_PROFILE='a')
        with patch.dict('os.environ',env,clear=True), patch('thurbox_accounts.guard.Accounts',return_value=self.accounts), patch('thurbox_accounts.guard.subprocess.Popen') as spawn:
            self.assertEqual(main(['--resume',self.uuid]),1)
        spawn.assert_not_called()
        self.assertEqual(self.shared._runtime(self.uuid),state)

    def launch_fixture(self, *, recover=False, focus_fails=False):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        if recover:
            record.update(phase='failed',allowed_session='reserved',reservation='nonce')
            self.shared.save(record)
        self.accounts.claude.executable = '/bin/true'
        def call(*args):
            self.tb.calls.append(args)
            if args[:2] == ('session','list'):
                return {'sessions':[]}
            if args[:2] == ('session','create'):
                owner = args[args.index('--id')+1]
                self.store.write('runtime-' + self.uuid + '.json',dict(owner=owner,phase='running'))
            if args[:2] == ('session','focus') and focus_fails:
                raise RuntimeError('focus unavailable')
            return {}
        with patch.object(self.tb,'call',side_effect=call):
            result = self.shared.recover(self.uuid) if recover else self.shared._launch(record,0)
        return result

    def test_failed_focus_keeps_successful_launch_active(self):
        result = self.launch_fixture(focus_fails=True)
        self.assertIn('notice',result)
        self.assertEqual(self.shared.load(self.uuid)['phase'],'active')

    def test_recovery_creates_missing_reserved_session_without_new_uuid(self):
        result = self.launch_fixture(recover=True)
        self.assertEqual(result['session'],'reserved')
        create = next(call for call in self.tb.calls if call[:2] == ('session','create'))
        self.assertEqual(create[create.index('--resume')+1],self.uuid)
        self.assertEqual(create[create.index('--id')+1],'reserved')

    def test_active_tool_refuses_switch_without_stopping_or_launching(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='owner')
        self.shared.save(record)
        original = self.store.write
        def write(name,value):
            original(name,value)
            if name == 'control-' + self.uuid + '.json':
                original('runtime-' + self.uuid + '.json',dict(owner='owner',phase='running',
                    request=value['request'],stop_result='busy',tools=['tool']))
        with patch.object(self.store,'write',side_effect=write):
            with self.assertRaisesRegex(ValueError,'remains running'):
                self.shared.switch(self.uuid)
        self.assertFalse(any(call[:2] in {('session','stop'),('session','create')} for call in self.tb.calls))

    def test_stale_destination_or_competing_transition_cannot_switch(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='owner')
        self.shared.save(record)
        with self.assertRaisesRegex(ValueError,'changed'):
            self.shared.switch(self.uuid,expected_profile='a')
        with self.store.lock('transition-' + self.uuid):
            with self.assertRaisesRegex(ValueError,'progress'):
                self.shared.switch(self.uuid)
        self.assertFalse(self.store.read('control-' + self.uuid + '.json'))
