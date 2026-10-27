import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_accounts import FakeClaude, FakeThurbox
from thurbox_accounts.accounts import Accounts, Profiles
from thurbox_accounts.thurbox import Thurbox

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = Profiles(self.root/'accounts')
        self.store.add('work')
        self.tb = FakeThurbox()
        self.accounts = Accounts(self.store,FakeClaude(),self.tb)
        self.accounts.claude.executable = '/bin/claude'
        self.accounts.status('work')
        self.row = dict(id='owned',name='Work',agent='claude',agent_session_id='33333333-3333-4333-8333-333333333333',cwd=str(self.root),stopped=False)
        self.tb.sessions['owned'] = self.row
        self.store.write('bindings.json',{'owned':dict(profile='work',agent_session_id=self.row['agent_session_id'],cwd=str(self.root),identity=self.store.get('work')['identity'])})

    def adapter(self):
        from thurbox_accounts.desktop import Desktop
        return Desktop(self.accounts)

    def test_only_owned_local_sessions_are_listed(self):
        foreign = dict(self.row,id='foreign')
        remote = dict(self.row,id='remote',host='elsewhere')
        self.store.write('bindings.json',{'owned':dict(profile='work'),'remote':dict(profile='work')})
        with patch.object(self.tb,'call',return_value={'sessions':[self.row,foreign,remote]}):
            result = self.adapter().state()
        self.assertEqual([row['id'] for row in result['conversations']],['owned'])
        self.assertEqual(result['profiles'][0]['name'],'work')

    def test_foreign_and_stopped_sessions_cannot_receive_input(self):
        with self.assertRaisesRegex(ValueError,'owned'):
            self.adapter().send('foreign','hello')
        self.row['stopped'] = True
        with self.assertRaisesRegex(ValueError,'stopped'):
            self.adapter().send('owned','hello')
        self.assertFalse(any(call[:2] == ('session','send') for call in self.tb.calls))

    def test_literal_prompt_and_native_key_allowlist(self):
        def call(*args):
            self.tb.calls.append(args)
            if args[:2] == ('session','get'): return self.row
            if args[:2] == ('session','capture'):
                return dict(output='native',foreground_process='claude',foreground_command='/bin/claude')
            return {'submitted':True}
        with patch.object(self.tb,'call',side_effect=call):
            self.adapter().send('owned','--literal\nnext line')
            self.adapter().key('owned','enter')
            with self.assertRaisesRegex(ValueError,'key'):
                self.adapter().key('owned','arbitrary-command')
        self.assertIn(('session','send','--strict','owned','--','--literal\nnext line'),self.tb.calls)

    def test_shell_foreground_refuses_input(self):
        def call(*args):
            if args[:2] == ('session','get'): return self.row
            if args[:2] == ('session','capture'):
                return dict(foreground_process='zsh',foreground_command='zsh')
            self.fail('must not send')
        with patch.object(self.tb,'call',side_effect=call):
            with self.assertRaisesRegex(ValueError,'foreground'):
                self.adapter().send('owned','do not execute')

    def test_transport_normalizes_session_array_and_keeps_json_before_literal_delimiter(self):
        result = dict(status='PASS',truncated=False,stdout='[]',stderr='')
        with patch('thurbox_accounts.thurbox.execute',return_value=result) as execute:
            self.assertEqual(Thurbox().call('session','list'),{'sessions':[]})
            result['stdout'] = '{"submitted":true}'
            Thurbox().call('session','send','owned','--','--literal')
            argv = execute.call_args.args[0]
            self.assertLess(argv.index('--json'),argv.index('--'))
            self.assertEqual(argv[-1],'--literal')

    def test_enrolled_original_cannot_start_or_receive_input(self):
        self.store.write('shared-' + self.row['agent_session_id'] + '.json',dict(
            conversation=self.row['agent_session_id'],allowed_session='new-owner',original_session='owned',is_probe=False))
        for action,args in [('start',()),('send',('hello',)),('key',('enter',))]:
            with self.subTest(action=action), self.assertRaisesRegex(ValueError,'shared'):
                getattr(self.adapter(),action)('owned',*args)
        self.assertFalse(any(call[:2] in {('session','start'),('session','send'),('session','key')} for call in self.tb.calls))

    def test_multiple_unreserved_failures_remain_visible_for_recovery(self):
        for identifier in ('33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444'):
            self.store.write('shared-' + identifier + '.json',dict(conversation=identifier,allowed_session='',
                original_session='owned',profiles=['work'],index=0,cwd=str(self.root),phase='failed'))
        with patch.object(self.tb,'call',return_value={'sessions':[]}):
            result = self.adapter().state()
        self.assertEqual(len(result['conversations']),2)
        self.assertEqual(len({row['id'] for row in result['conversations']}),2)
        self.assertTrue(all(row['phase']=='failed' for row in result['conversations']))

    def test_desktop_deadline_cleans_up_native_auth_child_before_returning(self):
        import os
        import subprocess
        import sys
        native = self.root/'slow-native'
        pidfile = self.root/'child.pid'
        native.write_text('#!' + sys.executable + '\nimport os,time\nfrom pathlib import Path\nPath(' + repr(str(pidfile)) + ').write_text(str(os.getpid()))\ntime.sleep(60)\n')
        native.chmod(0o700)
        command = [sys.executable,'-m','thurbox_accounts','--accounts-dir',str(self.store.root),
            '--claude',str(native),'--desktop-deadline','2','status','work']
        result = subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('deadline',result.stderr)
        pid = int(pidfile.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid,0)

    def test_resume_holds_enrollment_transition_lock_during_preflight(self):
        def preflight(profile):
            with self.assertRaisesRegex(ValueError,'progress'):
                with self.store.lock('transition-' + self.row['agent_session_id']):
                    pass
        self.accounts.check_launch = preflight
        self.adapter().start('owned')
        self.assertIn(('session','start','owned'),self.tb.calls)

    def test_unconfirmed_submission_warns_without_retrying_delivery(self):
        def call(*args):
            self.tb.calls.append(args)
            if args[:2] == ('session','get'): return self.row
            if args[:2] == ('session','capture'):
                return dict(foreground_process='claude',foreground_command='/bin/claude')
            raise RuntimeError('Thurbox session send failed: submission could not be confirmed')
        with patch.object(self.tb,'call',side_effect=call):
            result = self.adapter().send('owned','one explicit request')
        self.assertIsNone(result['submitted'])
        self.assertIn('Check the console',result['notice'])
        self.assertEqual(sum(call[:2] == ('session','send') for call in self.tb.calls),1)
