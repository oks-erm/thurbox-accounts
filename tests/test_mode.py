"""Current-conversation mode: source provenance, snapshots and policy gates."""
import hashlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from thurbox_accounts.accounts import Accounts, Profiles
from thurbox_accounts.shared import Shared
from test_accounts import FakeClaude, FakeThurbox

UUID = '88888888-8888-4888-8888-888888888888'

class SourceClaude(FakeClaude):
    executable = sys.executable
    def status(self, profile):
        result = super().status(profile)
        if profile['name'] == 'source':
            result.update(email='a@example.invalid',orgId='a')
        return result

class ModeThurbox(FakeThurbox):
    def __init__(self, directory):
        super().__init__(); self.directory = str(directory)
    def call(self, *args):
        if args[:2] == ('agent','launch-args'):
            return dict(command=sys.executable,env={'CLAUDE_CONFIG_DIR':self.directory})
        if args[:2] == ('session','list'): return dict(sessions=list(self.sessions.values()))
        return super().call(*args)

class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.origin = self.root/'native'; self.origin.mkdir(mode=0o700)
        self.tb = ModeThurbox(self.origin)
        self.store = Profiles(self.root/'accounts')
        self.accounts = Accounts(self.store,SourceClaude(),self.tb)
        self.store.add('a','Work A'); self.store.add('b','Work B')
        for name in ['a','b']: self.accounts.status(name)
        self.launch = patch.object(self.accounts,'check_launch'); self.launch.start(); self.addCleanup(self.launch.stop)
        self.path = self.origin/'projects/-project'/(UUID+'.jsonl'); self.path.parent.mkdir(parents=True)
        self.path.write_text('{"type":"user","sessionId":"'+UUID+'","message":{"content":"original"}}\n')
        self.sidecars = self.path.with_suffix(''); self.sidecars.mkdir(); (self.sidecars/'worker.json').write_text('original worker')
        self.tb.sessions['ordinary'] = dict(id='ordinary',name='My project',agent='claude',host=None,
            backend_type='tmux',stopped=True,cwd=str(self.root),agent_session_id=UUID,transcript_path=str(self.path))
        self.store.write('shared-proof.json',Shared(self.accounts).proof_contract(['a','b']))

    def mode(self):
        from thurbox_accounts.mode import Mode
        return Mode(self.accounts)

    def enable(self, token):
        def launch(record,index,**kwargs):
            record.update(phase='active',allowed_session='managed')
            record['mode']['active_index']=index
            Shared(self.accounts).save(record)
            self.tb.sessions['managed']=dict(id='managed',agent='claude-accounts',agent_session_id=UUID,cwd=str(self.root),stopped=True)
            self.store.write('runtime-'+UUID+'.json',dict(owner='managed',phase='stopped',tools=[],subagents=[],native_pid=None))
            return dict(session='managed',conversation=UUID,profile=record['profiles'][index])
        with patch.object(Shared,'_launch',side_effect=launch):
            return self.mode().enable(token,consent=True)

    def test_ordinary_adoption_preserves_original_and_only_snapshots_selected_history(self):
        mode = self.mode(); original = self.path.read_bytes()
        (self.path.parent/'other.jsonl').write_text('unrelated')
        plan = mode.preview('ordinary',['a','b'])
        self.assertEqual(plan['source_profile'],'a')
        self.enable(plan['id'])
        record = Shared(self.accounts).load(UUID)
        self.assertEqual(record['conversation'],UUID)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(Path(record['transcript']).read_bytes(),original)
        self.assertEqual((Path(record['sidecars'])/'worker.json').read_text(),'original worker')
        self.assertFalse((Path(record['transcript']).parent/'other.jsonl').exists())
        Shared(self.accounts).validate(record)
        self.assertEqual(record['name'],'My project (switchable)')

    def test_preview_refuses_live_source_and_does_not_stop_it(self):
        self.tb.sessions['ordinary']['stopped']=False
        with self.assertRaisesRegex(ValueError,'stop|Stop'): self.mode().preview('ordinary',['a','b'])
        self.assertFalse(any(c[:2]==('session','stop') for c in self.tb.calls))

    def test_wrong_native_identity_and_directory_are_refused(self):
        with patch.object(self.accounts.claude,'status',return_value=dict(loggedIn=True,authMethod='claude.ai',configDirectory=str(self.origin),email='alien',orgId='other')):
            with self.assertRaises(ValueError): self.mode().preview('ordinary',['a','b'])
        self.tb.directory=str(self.root/'somewhere-else')
        with self.assertRaises((ValueError,OSError)): self.mode().preview('ordinary',['a','b'])

    def test_source_changed_or_restarted_after_preview_cannot_be_enrolled(self):
        for restart in [False,True]:
            with self.subTest(restart=restart):
                self.tb.sessions['ordinary']['stopped']=True
                plan=self.mode().preview('ordinary',['a','b'])
                if restart: self.tb.sessions['ordinary']['stopped']=False
                else: self.path.write_text(self.path.read_text()+'changed\n')
                with self.assertRaises(ValueError): self.enable(plan['id'])
                self.assertFalse((self.store.root/('shared-'+UUID+'.json')).exists())

    def test_preview_rejects_sidecar_symlinks_and_target_collisions(self):
        link=self.sidecars/'foreign'; link.symlink_to(self.path)
        with self.assertRaises(ValueError): self.mode().preview('ordinary',['a','b'])
        link.unlink()
        target=Path(self.store.get('b')['directory'])/'projects/-project'/(UUID+'.jsonl')
        target.parent.mkdir(parents=True); target.write_text('keep')
        plan=self.mode().preview('ordinary',['a','b'])
        with self.assertRaises(ValueError): self.enable(plan['id'])
        self.assertEqual(target.read_text(),'keep'); self.assertFalse(self.path.is_symlink())

    def test_missing_proof_is_not_run_implicitly_and_source_stays_untouched(self):
        self.store.write('shared-proof.json',{})
        plan=self.mode().preview('ordinary',['a','b'])
        self.assertFalse(plan['proof_ready'])
        with self.assertRaisesRegex(ValueError,'verify|compatibility'): self.enable(plan['id'])
        self.assertFalse(self.path.is_symlink())

    def test_consent_expiration_and_one_use_are_enforced(self):
        plan=self.mode().preview('ordinary',['a','b'])
        with self.assertRaisesRegex(ValueError,'consent'): self.mode().enable(plan['id'],consent=False)
        with patch('thurbox_accounts.mode.time.time',return_value=plan['expires_at']+1):
            with self.assertRaisesRegex(ValueError,'expired'): self.enable(plan['id'])
        self.enable(plan['id'])
        with self.assertRaises(ValueError): self.enable(plan['id'])

    def test_off_blocks_cli_switch_without_stopping_active_writer_and_on_restores(self):
        self.enable(self.mode().preview('ordinary',['a','b'])['id'])
        self.mode().set_enabled('managed',False)
        with self.assertRaisesRegex(ValueError,'Off|off|disabled'): Shared(self.accounts).switch(UUID)
        self.assertFalse(any(c[:2]==('session','stop') for c in self.tb.calls))
        self.mode().set_enabled('managed',True)
        self.assertTrue(Shared(self.accounts).load(UUID)['mode']['enabled'])

    def test_failed_cross_account_recovery_is_refused_while_off(self):
        self.enable(self.mode().preview('ordinary',['a','b'])['id'])
        shared=Shared(self.accounts); record=shared.load(UUID)
        record.update(phase='failed',index=1); record['mode']['enabled']=False; shared.save(record)
        with self.assertRaisesRegex(ValueError,'Off|off|disabled'): shared.recover(UUID)
        with self.assertRaisesRegex(ValueError,'recover|Recover'): self.mode().set_enabled('managed',False)

    def test_original_remains_ineligible_for_desktop_resume(self):
        from thurbox_accounts.desktop import Desktop
        self.enable(self.mode().preview('ordinary',['a','b'])['id'])
        with self.assertRaisesRegex(ValueError,'original'): Desktop(self.accounts).start('ordinary')

    def test_stopped_source_with_known_background_work_is_refused(self):
        self.tb.sessions['ordinary']['background_work']={'shells':1}
        with self.assertRaisesRegex(ValueError,'background'): self.mode().preview('ordinary',['a','b'])

    def test_already_owned_source_uses_existing_enrollment_with_mode_guard(self):
        import shutil
        directory=Path(self.store.get('a')['directory'])
        path=directory/'projects/-project'/(UUID+'.jsonl'); path.parent.mkdir(parents=True)
        shutil.copyfile(self.path,path)
        self.tb.directory=str(directory); self.tb.sessions['ordinary']['transcript_path']=str(path)
        self.store.write('bindings.json',{'ordinary':dict(profile='a',identity=self.store.get('a')['identity'],cwd=str(self.root),agent_session_id=UUID)})
        plan=self.mode().preview('ordinary',['a','b'])
        self.enable(plan['id'])
        record=Shared(self.accounts).load(UUID)
        self.assertTrue(record['mode']['enabled']); self.assertTrue(path.is_symlink())
        Shared(self.accounts).validate(record)

    def test_group_or_build_change_after_preview_cannot_be_confirmed(self):
        plan=self.mode().preview('ordinary',['a','b'])
        with patch.object(self.accounts.claude,'fingerprint',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'verify|changed'): self.enable(plan['id'])
        self.assertFalse((self.store.root/('shared-'+UUID+'.json')).exists())

    def test_failed_launch_projection_does_not_claim_target_is_current(self):
        from thurbox_accounts.desktop import Desktop
        self.enable(self.mode().preview('ordinary',['a','b'])['id'])
        shared=Shared(self.accounts); record=shared.load(UUID)
        record.update(phase='failed',index=1); shared.save(record)
        state=Desktop(self.accounts).state()
        self.assertEqual(state['conversations'][0]['profile'],'a')

    def test_mode_change_is_serialized_with_switch_transition(self):
        self.enable(self.mode().preview('ordinary',['a','b'])['id'])
        with self.store.lock('transition-'+UUID):
            with self.assertRaisesRegex(ValueError,'progress'): self.mode().set_enabled('managed',False)
        self.assertTrue(Shared(self.accounts).load(UUID)['mode']['enabled'])

    def test_owned_source_restart_and_sidecar_change_during_slow_checks_refuse_before_move(self):
        import shutil
        directory=Path(self.store.get('a')['directory'])
        path=directory/'projects/-project'/(UUID+'.jsonl'); path.parent.mkdir(parents=True)
        shutil.copyfile(self.path,path); path.with_suffix('').mkdir()
        self.tb.directory=str(directory); self.tb.sessions['ordinary']['transcript_path']=str(path)
        self.store.write('bindings.json',{'ordinary':dict(profile='a',identity=self.store.get('a')['identity'],cwd=str(self.root),agent_session_id=UUID)})
        plan=self.mode().preview('ordinary',['a','b']); calls=0
        def change(profile):
            nonlocal calls
            calls+=1
            if calls==3:
                self.tb.sessions['ordinary']['stopped']=False
                (path.with_suffix('')/'unsafe').symlink_to(self.path)
        with patch.object(self.accounts,'check_launch',side_effect=change), patch.object(Shared,'_launch') as launch:
            with self.assertRaises(ValueError): self.mode().enable(plan['id'],consent=True)
            launch.assert_not_called()
        self.assertTrue(path.is_file()); self.assertFalse(path.is_symlink())
        self.assertFalse((self.store.root/'shared'/UUID/'main.jsonl').exists())

    def test_untracked_restart_during_final_launch_check_never_creates_managed_session(self):
        plan=self.mode().preview('ordinary',['a','b'])
        def change(profile):
            record=self.store.read('shared-'+UUID+'.json')
            if record.get('phase')=='stopped': self.tb.sessions['ordinary']['stopped']=False
        def runtime(native):
            record=self.store.read('shared-'+native+'.json')
            return dict(owner=record.get('allowed_session'),phase='running') if record.get('allowed_session') else {}
        with patch.object(self.accounts,'check_launch',side_effect=change), patch.object(Shared,'_runtime',side_effect=runtime):
            with self.assertRaises(ValueError): self.mode().enable(plan['id'],consent=True)
        self.assertFalse(any(c[:2]==('session','create') for c in self.tb.calls))
        self.assertTrue(self.path.is_file()); self.assertFalse(self.path.is_symlink())
