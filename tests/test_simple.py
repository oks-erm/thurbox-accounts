"""Named creation and inline switching contracts; synthetic identities only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_accounts import FakeClaude, FakeThurbox
from thurbox_accounts.accounts import Accounts, Profiles
from thurbox_accounts.shared import Shared


class SimpleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); self.store=Profiles(self.root/'accounts')
        for name in ('a','b','c'): self.store.add(name,'Work '+name.upper())
        self.tb=FakeThurbox(); native=FakeClaude(); native.executable='/bin/true'
        self.accounts=Accounts(self.store,native,self.tb); self.accounts.check_launch=lambda p: None
        for name in ('a','b','c'): self.accounts.status(name)
        self.uuid='33333333-3333-4333-8333-333333333333'
        self.owner='44444444-4444-4444-8444-444444444444'
        self.tb.sessions[self.owner]=dict(id=self.owner,name='Project',agent='Claude — Work A',
            agent_session_id=self.uuid,cwd=str(self.root),backend_type='tmux',stopped=False)

    def simple(self):
        from thurbox_accounts.simple import Simple
        return Simple(self.accounts)

    def bootstrap(self):
        return self.simple().bootstrap('a',['--session-id',self.uuid],self.owner,self.root)

    def test_single_account_creation_records_identity_without_cross_account_proof(self):
        record=self.bootstrap()
        self.assertEqual(record['kind'],'single')
        self.assertEqual(record['profiles'],['a'])
        self.assertEqual(record['allowed_session'],self.owner)
        self.assertEqual(self.store.read('bindings.json')[self.owner]['profile'],'a')
        Shared(self.accounts).validate(record)
        self.assertFalse(self.store.read('shared-proof.json'))
        resumed=self.simple().bootstrap('a',['--resume',self.uuid],self.owner,self.root)
        self.assertEqual(resumed,record)
        with self.assertRaisesRegex(ValueError,'profile|identity'):
            self.simple().bootstrap('b',['--resume',self.uuid],self.owner,self.root)
        self.tb.sessions[self.owner]['agent_session_id']='55555555-5555-4555-8555-555555555555'
        with self.assertRaisesRegex(ValueError,'identity|UUID'):
            self.bootstrap()

    def test_stale_single_owner_cannot_restart_after_shared_enrollment(self):
        record=self.bootstrap(); record.update(kind='shared',allowed_session='new-owner')
        Shared(self.accounts).save(record)
        with self.assertRaisesRegex(ValueError,'owner|shared'):
            self.bootstrap()

    def test_single_history_is_not_shared_before_explicit_confirmation(self):
        self.bootstrap()
        plan=self.simple().preview(self.owner,'b')
        self.assertEqual(plan['profiles'],['a','b'])
        self.assertFalse(plan['proof_ready'])
        self.assertEqual([p['label'] for p in plan['accounts']],['Work A','Work B'])
        with self.assertRaisesRegex(ValueError,'consent'):
            self.simple().confirm(plan['id'])
        with self.assertRaisesRegex(ValueError,'verify|compatibility'):
            self.simple().confirm(plan['id'],consent=True)
        self.assertFalse(any(c[:2]==('session','stop') for c in self.tb.calls))
        self.assertFalse((Path(self.store.get('b')['directory'])/'projects').exists())

    def test_source_owner_or_identity_changes_invalidate_confirmation_before_pause(self):
        record=self.bootstrap(); shared=Shared(self.accounts)
        self.store.write('shared-proof.json',shared.proof_contract(['a','b']))
        plan=self.simple().preview(self.owner,'b')
        record['allowed_session']='different'; shared.save(record)
        with self.assertRaisesRegex(ValueError,'changed|owner'):
            self.simple().confirm(plan['id'],consent=True)
        self.assertFalse(any(c[:2]==('session','stop') for c in self.tb.calls))

    def test_registered_account_agents_are_additive_owned_and_idempotent(self):
        from thurbox_accounts.agent_install import register_profiles
        registry=self.root/'agents.toml'
        registry.write_text('config_version=1\ndefault="claude"\n[[agents]]\nname="claude"\ncommand="claude"\n')
        before=registry.read_text(); launcher=Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent'
        def call(*args):
            return {'paths':{'agents_toml':str(registry)}} if args==('config','show') else {}
        with patch.object(self.tb,'call',side_effect=call):
            result=register_profiles(self.accounts,launcher)
            self.assertEqual(len(result['agents']),3)
            text=registry.read_text(); self.assertTrue(text.startswith(before))
            register_profiles(self.accounts,launcher)
            self.assertEqual(registry.read_text(),text)
            registry.write_text(text.replace('"--account-profile", "a"','"--account-profile", "wrong"'))
            with self.assertRaisesRegex(ValueError,'custom edits'):
                register_profiles(self.accounts,launcher)

    def test_confirmed_idle_switch_policy_still_refuses_background_or_unknown_work(self):
        from thurbox_accounts.guard import safe_state
        self.assertTrue(safe_state(dict(turn='idle'),allow_idle=True))
        self.assertFalse(safe_state(dict(turn='idle')))
        for extra in [dict(tools=['x']),dict(subagents=['x']),dict(background_tools={'x':'task'}),dict(blocked=True),dict(uncertain=True),dict(error='bad')]:
            self.assertFalse(safe_state(dict(turn='idle',**extra),allow_idle=True))
        self.assertFalse(safe_state(dict(turn='unknown'),allow_idle=True))

    def history(self):
        path=Path(self.store.get('a')['directory'])/'projects/-project'/(self.uuid+'.jsonl')
        path.parent.mkdir(parents=True); path.write_text('{"type":"user","sessionId":"'+self.uuid+'","message":{"role":"user","content":"context"}}\n')
        self.tb.sessions[self.owner]['transcript_path']=str(path)
        return path

    def test_confirm_safely_enrolls_single_history_and_launches_chosen_target(self):
        self.bootstrap(); path=self.history(); shared=Shared(self.accounts)
        self.store.write('shared-proof.json',shared.proof_contract(['a','b']))
        plan=self.simple().preview(self.owner,'b')
        def pause(record,allow_idle=False):
            self.assertTrue(allow_idle)
            self.tb.sessions[self.owner]['stopped']=True
            self.store.write('runtime-'+self.uuid+'.json',dict(owner=self.owner,phase='stopped',native_pid=None,turn='idle'))
        with patch.object(Shared,'_pause',side_effect=pause), patch.object(Shared,'_launch',return_value={'profile':'b'}) as launch:
            result=self.simple().confirm(plan['id'],consent=True)
        self.assertEqual(result['profile'],'b')
        record,index=launch.call_args.args
        self.assertEqual(index,1); self.assertEqual(record['conversation'],self.uuid)
        self.assertTrue(path.is_symlink()); self.assertEqual(record['profiles'],['a','b'])
        self.assertEqual(record['mode']['active_index'],0)
        with self.assertRaisesRegex(ValueError,'used'):
            self.simple().confirm(plan['id'],consent=True)
        with self.assertRaisesRegex(ValueError,'owner|shared'):
            self.bootstrap()

    def test_expired_and_collision_plans_never_pause_source(self):
        self.bootstrap(); path=self.history(); shared=Shared(self.accounts)
        self.store.write('shared-proof.json',shared.proof_contract(['a','b']))
        plan=self.simple().preview(self.owner,'b')
        value=self.store.read('simple-plan-'+plan['id']+'.json'); value['expires_at']=0
        self.store.write('simple-plan-'+plan['id']+'.json',value)
        with self.assertRaisesRegex(ValueError,'expired'):
            self.simple().confirm(plan['id'],consent=True)
        plan=self.simple().preview(self.owner,'b')
        target=Path(self.store.get('b')['directory'])/'projects'/path.parent.name/path.name
        target.parent.mkdir(parents=True); target.write_text('other history')
        with patch.object(Shared,'_pause') as pause, self.assertRaisesRegex(ValueError,'already has'):
            self.simple().confirm(plan['id'],consent=True)
        pause.assert_not_called(); self.assertEqual(target.read_text(),'other history')

    def test_named_history_can_be_found_when_thurbox_does_not_publish_wrapper_config(self):
        record=self.bootstrap(); path=self.history()
        self.tb.sessions[self.owner]['transcript_path']=None
        self.assertEqual(self.simple().transcript(record),path)
        other=path.parent.parent/'-another'/path.name
        other.parent.mkdir(); other.write_text('collision')
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            self.simple().transcript(record)

    def test_stopped_named_session_resumes_same_account_without_multi_account_proof(self):
        from thurbox_accounts.desktop import Desktop
        self.bootstrap(); self.tb.sessions[self.owner]['stopped']=True
        Desktop(self.accounts).start(self.owner)
        self.assertIn(('session','start',self.owner),self.tb.calls)
        self.assertFalse(any(c[:2]==('session','create') for c in self.tb.calls))
