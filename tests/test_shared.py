import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
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

    def test_enrollment_requires_consent_but_no_paid_probe(self):
        with self.assertRaisesRegex(ValueError,'consent'):
            self.shared.enroll('source',['a','b'],consent=False)
        with patch('thurbox_accounts.shared_probe.verify', side_effect=AssertionError('no paid checks')):
            record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        self.assertEqual(record['history_consent'],self.shared.proof_contract(['a','b']))
        self.assertFalse(self.store.read('shared-proof.json'))
        self.assertEqual(self.shared.require_consent(record),record['history_consent'])
        self.accounts.claude.fingerprint=lambda:'changed-build'
        with self.assertRaisesRegex(ValueError,'changed'):
            self.shared.require_consent(record)

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
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        with patch.object(self.accounts.claude,'fingerprint',return_value='upgrade'):
            with self.assertRaisesRegex(ValueError,'changed'):
                self.shared.require_consent(record)

    def test_pending_reservation_blocks_old_managed_owner(self):
        from thurbox_accounts.guard import authorize
        record=dict(allowed_session='new',phase='switching',reservation='nonce')
        with self.assertRaisesRegex(ValueError,'owner'):
            authorize(record,'old','nonce')
        with self.assertRaisesRegex(ValueError,'reservation'):
            authorize(record,'new','wrong')
        authorize(record,'new','nonce')

    def test_retirement_soft_deletes_only_stopped_predecessor_and_preserves_history(self):
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='destination',retire_pending=['source'])
        record['primary_cwd']=str(self.root)+'/'
        self.store.write('runtime-'+self.uuid+'.json',dict(owner='destination',phase='running'))
        content=Path(record['transcript']).read_bytes()
        original=self.tb.call
        def call(*args):
            if args[:2]==('session','delete'):
                self.tb.calls.append(args); return {'soft':True}
            return original(*args)
        with patch.object(self.tb,'call',side_effect=call):
            self.assertFalse(self.shared.retire_previous(record))
        self.assertIn(('session','delete','source','--soft'),self.tb.calls)
        self.assertEqual(record['retire_pending'],[])
        self.assertEqual(Path(record['transcript']).read_bytes(),content)

    def test_retirement_keeps_running_source_and_never_deletes_current_owner(self):
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='destination',retire_pending=['source','destination'])
        self.store.write('runtime-'+self.uuid+'.json',dict(owner='destination',phase='running'))
        self.tb.sessions['source']['stopped']=False
        self.assertTrue(self.shared.retire_previous(record))
        self.assertFalse(any(c[:2]==('session','delete') for c in self.tb.calls))

    def test_retirement_failure_is_a_notice_after_a_successful_launch(self):
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='destination',retire_pending=['source'])
        self.store.write('runtime-'+self.uuid+'.json',dict(owner='destination',phase='running'))
        original=self.tb.call
        def call(*args):
            if args[:2]==('session','delete'): raise RuntimeError('database unavailable')
            return original(*args)
        with patch.object(self.tb,'call',side_effect=call):
            self.assertTrue(self.shared.retire_previous(record))
        self.assertEqual(record['phase'],'active')
        self.assertEqual(record['retire_pending'],['source'])

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

    def test_explicit_failed_session_reboot_repair_preserves_uuid_and_history(self):
        self.proof()
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(allowed_session='source',phase='active')
        self.shared.save(record)
        self.tb.sessions['source'].update(agent='claude-accounts',stopped=False,state='failed',
                                         launch_failure=dict(reason='exited'))
        state=dict(owner='source',phase='running',native_pid=99999999,tools=['old'],background_tools={'bg':'task'})
        self.store.write('runtime-'+self.uuid+'.json',state)
        before=Path(record['transcript']).read_bytes()
        with self.assertRaisesRegex(ValueError,'confirm-reboot'):
            self.shared.repair_after_reboot('source')
        boot=dict(id='22222222-2222-4222-8222-222222222222',started_ns=time.time_ns()+1_000_000_000)
        with patch('thurbox_accounts.guard.boot_identity',return_value=boot), \
                patch('thurbox_accounts.guard.os.kill',side_effect=ProcessLookupError):
            result=self.shared.repair_after_reboot('source',confirm=True)
        self.assertTrue(result['repaired'])
        self.assertEqual(result['conversation'],self.uuid)
        self.assertEqual(json.loads(Path(result['backup']).read_text()),state)
        self.assertEqual(Path(record['transcript']).read_bytes(),before)
        self.assertFalse(any(call[:2] in {('session','create'),('session','restart'),('session','stop')} for call in self.tb.calls))

    def test_reboot_repair_refuses_a_running_or_foreign_session(self):
        self.proof()
        record=self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(allowed_session='source',phase='active')
        self.shared.save(record)
        self.tb.sessions['source'].update(agent='claude-accounts',stopped=False,state='working')
        with self.assertRaisesRegex(ValueError,'Stop the affected'):
            self.shared.repair_after_reboot('source',confirm=True)
        self.assertFalse(self.store.read('runtime-'+self.uuid+'.json'))
        record['allowed_session']='other'; self.shared.save(record)
        with self.assertRaisesRegex(ValueError,'current managed'):
            self.shared.repair_after_reboot('source',confirm=True)

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
            if args[:2] == ('session','get'):
                return self.tb.sessions.get(args[2], {})
            if args[:2] == ('session','delete'):
                return {'soft':True}
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

    def test_successful_launch_retires_only_the_stopped_old_row_after_creation(self):
        result=self.launch_fixture()
        create=next(i for i,c in enumerate(self.tb.calls) if c[:2]==('session','create'))
        deletes=[(i,c) for i,c in enumerate(self.tb.calls) if c[:2]==('session','delete')]
        self.assertEqual(len(deletes),1)
        self.assertGreater(deletes[0][0],create)
        self.assertEqual(deletes[0][1],('session','delete','source','--soft'))
        self.assertNotEqual(result['session'],'source')
        self.assertEqual(self.shared.load(self.uuid)['retire_pending'],[])

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

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux guardian worker ownership')
    def test_switch_cancels_native_with_stale_task_markers_before_releasing_history(self):
        from thurbox_accounts.guard import supervise, update, writer_available
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='owner')
        self.shared.save(record)
        original = Path(record['transcript']).read_bytes()
        # A killed/rebooted old guardian left its PID and task ledger behind.
        self.store.write('runtime-' + self.uuid + '.json',dict(owner='owner',phase='running',
            native_pid=99999999,tools=['pre-reboot-tool'],background_tools={'pre-reboot':'task'},
            boot=dict(id='11111111-1111-4111-8111-111111111111')))
        self.tb.sessions['owner'] = dict(self.tb.sessions['source'], id='owner', stopped=False)
        script = self.root / 'synthetic_claude.py'
        native_args = self.root / 'native-args.json'
        detached_pid = self.root / 'detached-worker'
        hook_start = self.root / 'start-hook'
        hook_ready = self.root / 'hook-lock-held'
        hook = ('import fcntl,os,pathlib,time\n'
                f'while not pathlib.Path({str(hook_start)!r}).exists(): time.sleep(.01)\n'
                f'fd=open({str(self.store.root / ("events-" + self.uuid + ".lock"))!r},"a")\n'
                'fcntl.flock(fd,fcntl.LOCK_EX)\n'
                f'pathlib.Path({str(hook_ready)!r}).write_text(str(os.getpid()))\n'
                'time.sleep(.3)\n'
                'fcntl.flock(fd,fcntl.LOCK_UN)\n'
                'time.sleep(60)\n')
        middle = ('import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],'
                  f'start_new_session=True); open({str(detached_pid)!r},"w").write(str(p.pid))')
        script.write_text('import json,subprocess,sys,time\n'
                          f'open({str(native_args)!r},"w").write(json.dumps(sys.argv[1:]))\n'
                          f'subprocess.run([sys.executable,"-c",{middle!r}],check=True)\n'
                          f'subprocess.Popen([sys.executable,"-c",{hook!r}])\n'
                          'time.sleep(60)\n')
        supervisor = multiprocessing.get_context('fork').Process(target=supervise,
            args=(self.shared, record, 'owner', self.a, sys.executable,
                  [str(script),'--session-id',self.uuid], Path('/test-launcher')))
        supervisor.start()
        def cleanup():
            if supervisor.is_alive():
                supervisor.terminate()
            supervisor.join(timeout=3)
            if supervisor.is_alive():
                supervisor.kill(); supervisor.join()
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 3
        while (self.shared._runtime(self.uuid).get('phase') != 'running'
               or self.shared._runtime(self.uuid).get('native_pid') == 99999999) and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(self.shared._runtime(self.uuid).get('phase'), 'running')
        archives=list(self.store.root.glob('runtime-before-boot-' + self.uuid + '-*.json'))
        self.assertEqual(len(archives),1)
        self.assertEqual(json.loads(archives[0].read_text())['tools'],['pre-reboot-tool'])
        while not detached_pid.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(detached_pid.exists())
        recovered_args=json.loads(native_args.read_text())
        self.assertEqual(recovered_args[recovered_args.index('--resume')+1],self.uuid)
        self.assertNotIn('--session-id',recovered_args)
        worker_pid = int(detached_pid.read_text())
        def cleanup_worker():
            try:
                os.kill(worker_pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.addCleanup(cleanup_worker)
        from thurbox_accounts.processes import snapshot
        self.assertEqual(snapshot()[worker_pid]['parent'],supervisor.pid)
        update(self.store,self.uuid,turn='quota',tools=['missed-post-tool'],
               background_tools={'old-tool':'old-task'},scheduled_work=[{'id':'old-wakeup'}],
               subagents=['old-agent'],scheduled_work_unknown=True)
        hook_start.touch()
        deadline = time.monotonic() + 3
        while not hook_ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(hook_ready.exists())
        hook_pid = int(hook_ready.read_text())
        self.accounts.claude.executable = sys.executable
        original_call = self.tb.call
        def call(*args):
            if args[:2] == ('session','stop'):
                self.tb.sessions[args[2]]['stopped'] = True
            return original_call(*args)
        errors = []
        def pause():
            try:
                self.shared._pause(record,allow_idle=True)
            except Exception as error:
                errors.append(error)
        with patch.object(self.tb,'call',side_effect=call):
            controller = threading.Thread(target=pause,daemon=True)
            controller.start()
            controller.join(timeout=5)
            blocked = controller.is_alive()
            if blocked:
                # Release a frozen hook's lock so a regressed implementation
                # fails this test without leaving synthetic processes behind.
                os.kill(hook_pid,signal.SIGKILL)
                controller.join(timeout=3)
            self.assertFalse(blocked, 'Shutdown froze a hook holding its required events lock')
            if errors:
                raise errors[0]
        supervisor.join(timeout=2)
        self.assertFalse(supervisor.is_alive())
        self.assertTrue(writer_available(self.store,self.uuid))
        state = self.shared._runtime(self.uuid)
        self.assertEqual(state['stop_result'], 'cancelled')
        self.assertTrue(state['shutdown_evidence']['confirmed'])
        self.assertIn(worker_pid,{p['pid'] for p in state['shutdown_evidence']['processes']})
        self.assertIn(hook_pid,{p['pid'] for p in state['shutdown_evidence']['processes']})
        self.assertEqual(state['cancelled_work']['background_tools'], {'old-tool':'old-task'})
        self.assertEqual(state['last_shutdown']['cancelled_work'],state['cancelled_work'])
        self.assertEqual(state['last_shutdown']['processes'],state['shutdown_evidence']['processes'])
        for key in ('tools','subagents','background_tools','scheduled_work','uncertain','error'):
            self.assertFalse(state.get(key), key)
        self.assertEqual(Path(record['transcript']).read_bytes(), original)
        self.assertTrue(self.tb.sessions['owner']['stopped'])
        self.assertFalse(any(call[:2] == ('session','create') for call in self.tb.calls))

    def test_unconfirmed_cancellation_preserves_task_evidence_and_does_not_launch(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record.update(phase='active',allowed_session='owner')
        self.shared.save(record)
        self.accounts.claude.executable = sys.executable
        state = dict(owner='owner',phase='running',native_pid=99999999,tools=['tool'])
        self.store.write('runtime-' + self.uuid + '.json',state)
        with patch.object(self.shared,'_launch') as launch:
            with self.assertRaisesRegex(ValueError,'verify'):
                self.shared.switch(self.uuid)
        launch.assert_not_called()
        self.assertEqual(self.shared._runtime(self.uuid),state)
        self.assertFalse(any(call[:2] == ('session','stop') for call in self.tb.calls))

    def test_completed_aliases_recover_after_enrollment_controller_crash(self):
        self.proof()
        record = self.shared.enroll('source',['a','b'],consent=True,launch=False)
        record['phase'] = 'enrolling'
        self.shared.save(record)
        with patch.object(self.shared,'_launch',return_value={'recovered':True}) as launch:
            self.assertEqual(self.shared.recover(self.uuid),{'recovered':True})
        self.assertEqual(launch.call_args.args[1],0)

class BackgroundShellTests(unittest.TestCase):
    def test_async_bash_is_not_safe_at_quota_until_matching_native_completion(self):
        from thurbox_accounts.guard import apply_event, safe_state
        state={}
        apply_event(state,'PreToolUse',dict(tool_use_id='bash-1',tool_name='Bash',tool_input={'run_in_background':True}))
        apply_event(state,'PostToolUse',dict(tool_use_id='bash-1',tool_name='Bash',tool_input={'run_in_background':True},tool_response={'backgroundTaskId':'task-1'}))
        apply_event(state,'StopFailure',dict(error='rate_limit'))
        self.assertFalse(safe_state(state),'A background shell still owns work after its launch tool returns')
        apply_event(state,'PostToolUse',dict(tool_use_id='read',tool_name='TaskOutput',tool_input={'task_id':'other'},
            tool_response={'retrieval_status':'success','task':{'task_id':'other','status':'completed'}}))
        self.assertFalse(safe_state(state))
        apply_event(state,'PostToolUse',dict(tool_use_id='read',tool_name='TaskOutput',tool_input={'task_id':'task-1'},
            tool_response={'retrieval_status':'success','task':{'task_id':'task-1','status':'completed'}}))
        self.assertTrue(safe_state(state))

    def test_automatic_background_response_and_failed_background_launch_stay_unconfirmed(self):
        from thurbox_accounts.guard import apply_event, safe_state
        for event,response in [('PostToolUse',{'backgroundTaskId':'auto-task'}),('PostToolUseFailure',{})]:
            with self.subTest(event=event):
                state={}
                apply_event(state,'PreToolUse',dict(tool_use_id='bash',tool_name='Bash',tool_input={'run_in_background':True}))
                apply_event(state,event,dict(tool_use_id='bash',tool_name='Bash',tool_response=response))
                apply_event(state,'StopFailure',dict(error='rate_limit'))
                self.assertFalse(safe_state(state))

    def test_native_stop_registry_can_confirm_completion_without_guessing_output_text(self):
        from thurbox_accounts.guard import apply_event, safe_state
        state={}
        apply_event(state,'PreToolUse',dict(tool_use_id='bg',tool_name='Bash',tool_input={'run_in_background':True}))
        apply_event(state,'PostToolUse',dict(tool_use_id='bg',tool_name='Bash'))
        apply_event(state,'Stop',dict(background_tasks=[{'id':'live-shell','type':'shell','status':'running'}]))
        apply_event(state,'StopFailure',dict(error='rate_limit'))
        self.assertFalse(safe_state(state))
        apply_event(state,'Stop',dict(background_tasks=[]))
        apply_event(state,'StopFailure',dict(error='rate_limit'))
        self.assertTrue(safe_state(state))
