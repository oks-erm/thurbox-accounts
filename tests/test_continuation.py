import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import sys
import time
import unittest
import uuid
from unittest.mock import patch

from test_accounts import FakeClaude, FakeThurbox
from thurbox_accounts.accounts import Accounts, Profiles
from thurbox_accounts.simple import Simple
from thurbox_accounts import continuation


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.store=Profiles(self.root/'accounts')
        for name in ('a','b'): self.store.add(name,'Work '+name.upper())
        self.tb=FakeThurbox(); self.native=FakeClaude(); self.native.executable='/bin/true'
        self.accounts=Accounts(self.store,self.native,self.tb); self.accounts.check_launch=lambda p:None
        for name in ('a','b'): self.accounts.status(name)
        self.owner='44444444-4444-4444-8444-444444444444'
        self.native_id='33333333-3333-4333-8333-333333333333'
        self.tb.sessions[self.owner]=dict(id=self.owner,name='Useful work',agent='Claude — Work A',
            agent_session_id=self.native_id,cwd=str(self.root),backend_type='tmux',stopped=False,state='failed')
        Simple(self.accounts).bootstrap('a',['--session-id',self.native_id],self.owner,self.root)
        self.history=Path(self.store.get('a')['directory'])/'projects/-project'/(self.native_id+'.jsonl')
        self.history.parent.mkdir(parents=True)
        self.history.write_text('\n'.join(json.dumps(dict(type=role,message=dict(role=role,content=text)))
            for role,text in [('user','Finish the important feature'),('assistant','The API is ready; UI remains')])+'\n')
        self.store.write('runtime-'+self.native_id+'.json',dict(owner=self.owner,phase='running',native_pid=123,
            turn='quota',tools=['stale'],background_tools={'unknown':'old-job'}))
        self.original_call=self.tb.call; self.starts=[]
        self.authenticated=self.accounts.authenticated

    def fake_launch(self,*args):
        if args[:2]==('session','create'):
            owner=args[args.index('--id')+1]
            native=str(uuid.uuid4())
            profile=next(name for name in ('a','b') if args[args.index('--agent')+1]=='Claude — '+self.store.get(name)['label'])
            self.tb.sessions[owner]=dict(id=owner,name=args[args.index('--name')+1],agent=args[args.index('--agent')+1],
                agent_session_id=native,cwd=str(self.root),stopped=False,backend_type='tmux')
            record=Simple(self.accounts).bootstrap(profile,['--session-id',native],owner,self.root)
            token=next(a.split('=',1)[1] for a in args if a.startswith('THURBOX_ACCOUNTS_CONTINUATION='))
            with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
                native_args=continuation.startup_args(self.store,record,owner,self.store.get(profile),['--session-id',native])
            self.starts.append((record,native_args,token))
            from thurbox_accounts.guard import boot_identity
            self.store.write('runtime-'+native+'.json',dict(owner=owner,phase='running',native_pid=999,boot=boot_identity()))
            return dict(id=owner,created=True,agent_session_id=native)
        return self.original_call(*args)

    def select(self,**kwargs):
        with patch.object(self.tb,'call',side_effect=self.fake_launch):
            return continuation.Continuations(self.accounts).select(self.owner,'b',consent=True,**kwargs)

    def test_continues_without_source_auth_quota_or_shutdown(self):
        source_state=self.store.read('runtime-'+self.native_id+'.json')
        source_record=self.store.read('shared-'+self.native_id+'.json')
        raw=self.history.read_bytes()
        def auth(name):
            self.assertNotEqual(name,'a','Source account was asked to authenticate')
            return self.authenticated(name)
        with patch.object(self.accounts,'authenticated',side_effect=auth):
            result=self.select()
        self.assertEqual(result['profile'],'b')
        self.assertNotEqual(result['conversation'],self.native_id)
        self.assertEqual(Path(result['handoff']).with_name('history.jsonl').read_bytes(),raw)
        self.assertIn('Finish the important feature',Path(result['handoff']).with_name('recent.md').read_text())
        self.assertEqual(self.history.read_bytes(),raw)
        self.assertEqual(self.store.read('runtime-'+self.native_id+'.json'),source_state)
        self.assertEqual(self.store.read('shared-'+self.native_id+'.json'),source_record)
        self.assertFalse(any(c[:2] in {('session','stop'),('session','delete'),('session','send')} for c in self.tb.calls))
        self.assertIn('Read',self.starts[0][1][-1])
        self.assertNotIn('--resume',self.starts[0][1])

    def test_retry_reuses_destination_and_bootstrap_never_replays(self):
        result=self.select(); again=self.select()
        self.assertEqual(result['session'],again['session'])
        self.assertEqual(len(self.starts),1)
        record,args,token=self.starts[0]
        destination=Path(self.store.get('b')['directory'])/'projects/-project'/(record['conversation']+'.jsonl')
        destination.parent.mkdir(parents=True); destination.write_text('{"type":"user","message":{"content":"continued"}}\n')
        with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
            resumed=continuation.startup_args(self.store,record,record['allowed_session'],self.store.get('b'),['--resume',record['conversation']])
        self.assertFalse(any('Read the handoff' in arg for arg in resumed))
        self.assertIn('--add-dir',resumed)

    def test_missing_history_or_stale_display_identity_never_creates_destination(self):
        with self.assertRaisesRegex(ValueError,'identity'):
            self.select(expected_email='somebody-else',expected_org='wrong',expected_native=self.native_id)
        self.history.unlink()
        with self.assertRaisesRegex(ValueError,'history'):
            self.select()
        self.assertFalse(self.starts)

    def test_requires_explicit_consent(self):
        with self.assertRaisesRegex(ValueError,'consent'):
            continuation.Continuations(self.accounts).select(self.owner,'b')

    def test_preview_is_read_only_and_never_authenticates_source(self):
        before={str(p.relative_to(self.store.root)):p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        def auth(name):
            self.assertEqual(name,'b')
            return self.authenticated(name)
        with patch.object(self.accounts,'authenticated',side_effect=auth):
            result=continuation.Continuations(self.accounts).preview(self.owner,'b')
        after={str(p.relative_to(self.store.root)):p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        self.assertEqual(result['conversation'],self.native_id)
        self.assertEqual(result['source_profile'],'a')
        self.assertEqual(result['account']['name'],'b')
        # Target authentication may refresh its cached public identity only.
        self.assertEqual(before,after)
        self.assertFalse(self.starts)

    def test_selected_history_is_copied_without_other_profile_files(self):
        credentials=Path(self.store.get('a')['directory'])/'.credentials.json'
        credentials.write_text('synthetic-credential-never-copy')
        result=self.select()
        folder=Path(result['handoff']).parent
        for item in folder.iterdir():
            self.assertNotIn('synthetic-credential-never-copy',item.read_text())
        self.assertEqual(credentials.read_text(),'synthetic-credential-never-copy')

    def test_bootstrap_refuses_wrong_owner_or_modified_history(self):
        result=self.select(); record,args,token=self.starts[0]
        with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
            with self.assertRaisesRegex(ValueError,'owner'):
                continuation.startup_args(self.store,record,'another-owner',self.store.get('b'),args)
            Path(result['handoff']).with_name('history.jsonl').write_text('changed')
            with self.assertRaisesRegex(ValueError,'snapshot'):
                continuation.startup_args(self.store,record,record['allowed_session'],self.store.get('b'),args)

    def test_next_account_keeps_earlier_context_access(self):
        first=self.select(); first_record,_,first_token=self.starts[0]
        history=Path(self.store.get('b')['directory'])/'projects/-project'/(first['conversation']+'.jsonl')
        history.parent.mkdir(parents=True)
        history.write_text('{"type":"user","message":{"content":"Now finish the UI"}}\n')
        with patch.object(self.tb,'call',side_effect=self.fake_launch):
            second=continuation.Continuations(self.accounts).select(first['session'],'a',consent=True)
        record,args,token=self.starts[1]
        self.assertNotEqual(first['conversation'],second['conversation'])
        self.assertEqual(self.store.read('continuation-'+token+'.json')['ancestors'],[first_token])
        self.assertIn(str(Path(first['handoff']).parent),args)
        self.assertIn(str(Path(first['handoff']).with_name('history.jsonl')),Path(second['handoff']).read_text())
        self.assertIn('Now finish the UI',Path(second['handoff']).with_name('recent.md').read_text())

    def test_ordinary_unverified_conversation_can_continue(self):
        self.tb.sessions[self.owner].update(agent='claude',transcript_path=str(self.history))
        (self.store.root/('shared-'+self.native_id+'.json')).unlink()
        result=self.select()
        self.assertEqual(result['profile'],'b')

    def test_partial_final_write_is_preserved_but_not_parsed_as_a_message(self):
        with self.history.open('ab') as stream: stream.write(b'{"type":"assistant","message":')
        raw=self.history.read_bytes()
        result=self.select()
        self.assertEqual(Path(result['handoff']).with_name('history.jsonl').read_bytes(),raw)

    def test_uncertain_creation_retries_the_same_reserved_destination(self):
        created=[]
        def fail_create(*args):
            if args[:2]==('session','create'):
                created.append(args)
                if len(created)==1: raise TimeoutError('transport timeout')
                return self.fake_launch(*args)
            return self.original_call(*args)
        with patch.object(self.tb,'call',side_effect=fail_create):
            with self.assertRaisesRegex(ValueError,'launch is unconfirmed'):
                continuation.Continuations(self.accounts).select(self.owner,'b',consent=True)
            reserved=created[0][created[0].index('--id')+1]
            (self.store.root/('context-origin-'+reserved+'.json')).unlink()
            result=continuation.Continuations(self.accounts).select(self.owner,'b',consent=True)
        self.assertEqual(len(created),2)
        self.assertEqual(created[0][created[0].index('--id')+1],created[1][created[1].index('--id')+1])
        self.assertEqual(result['session'],self.starts[0][0]['allowed_session'])
        self.assertEqual(self.store.read('context-origin-'+reserved+'.json')['id'],self.starts[0][2])

    def test_known_exec_failure_can_retry_bootstrap_without_losing_snapshot(self):
        self.select(); record,args,token=self.starts[0]
        with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
            continuation.exec_failed(self.store,record,record['allowed_session'])
            self.assertFalse(self.store.read('continuation-'+token+'.json')['bootstrap_started'])
            retried=continuation.startup_args(self.store,record,record['allowed_session'],self.store.get('b'),['--session-id',record['conversation']])
        self.assertEqual(sum(arg.startswith('Read the handoff') for arg in retried),1)

    def test_timeout_after_creation_does_not_create_or_bootstrap_twice(self):
        created=[]
        def timeout_after_create(*args):
            if args[:2]==('session','create'):
                created.append(args); self.fake_launch(*args)
                raise TimeoutError('reply lost')
            return self.original_call(*args)
        with patch.object(self.tb,'call',side_effect=timeout_after_create):
            with self.assertRaisesRegex(ValueError,'launch is unconfirmed'):
                continuation.Continuations(self.accounts).select(self.owner,'b',consent=True)
            result=continuation.Continuations(self.accounts).select(self.owner,'b',consent=True)
        self.assertEqual(len(created),1)
        self.assertEqual(len(self.starts),1)
        self.assertEqual(result['profile'],'b')

    def test_uncertain_first_prompt_is_not_replayed_into_an_empty_session(self):
        self.select(); record,args,token=self.starts[0]
        with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
            with self.assertRaisesRegex(ValueError,'already attempted'):
                continuation.startup_args(self.store,record,record['allowed_session'],self.store.get('b'),['--session-id',record['conversation']])

    def test_stale_running_runtime_does_not_claim_failed_destination_is_ready(self):
        first=self.select()
        self.tb.sessions[first['session']].update(state='failed',launch_failure=dict(reason='exited'))
        with self.assertRaisesRegex(ValueError,'not confirmed running'):
            self.select()
        self.assertEqual(len(self.starts),1)

    def test_profile_label_with_slash_generates_a_valid_session_name(self):
        profiles=self.store.read('profiles.json'); profiles['b']['label']='Work/Team'
        self.store.write('profiles.json',profiles)
        result=self.select()
        self.assertNotIn('/',self.tb.sessions[result['session']]['name'])

    @unittest.skipUnless(sys.platform.startswith('linux'),'Synthetic POSIX guard lifecycle')
    def test_real_guard_injects_context_once_and_resume_keeps_history(self):
        from thurbox_accounts.guard import supervise
        self.native.executable=sys.executable
        captured=self.root/'captured-args.json'
        script=self.root/'synthetic-native.py'
        script.write_text('import json,pathlib,sys,time\n'
                          f'pathlib.Path({str(captured)!r}).write_text(json.dumps(sys.argv[1:]))\n'
                          'time.sleep(60)\n')
        children=[]
        def start(record,token,args):
            with patch.dict(os.environ,THURBOX_ACCOUNTS_CONTINUATION=token):
                child=multiprocessing.get_context('fork').Process(target=supervise,args=(
                    Simple(self.accounts).shared,record,record['allowed_session'],self.store.get('b'),
                    sys.executable,[str(script),*args],Path('/test-launcher')))
                child.start()
            children.append(child)
            return child
        def cleanup():
            for child in children:
                if child.is_alive(): child.terminate()
                child.join(timeout=3)
                if child.is_alive(): child.kill(); child.join()
        self.addCleanup(cleanup)
        def create(*args):
            if args[:2]!=('session','create'): return self.original_call(*args)
            owner=args[args.index('--id')+1]; native=str(uuid.uuid4())
            self.tb.sessions[owner]=dict(id=owner,name='Target',agent='Claude — Work B',
                agent_session_id=native,cwd=str(self.root),stopped=False,backend_type='tmux')
            record=Simple(self.accounts).bootstrap('b',['--session-id',native],owner,self.root)
            token=next(a.split('=',1)[1] for a in args if a.startswith('THURBOX_ACCOUNTS_CONTINUATION='))
            start(record,token,['--session-id',native])
            self.starts.append((record,[],token))
            return dict(id=owner,created=True,agent_session_id=native)
        raw=self.history.read_bytes()
        with patch.object(self.tb,'call',side_effect=create):
            result=continuation.Continuations(self.accounts).select(self.owner,'b',consent=True)
        deadline=time.monotonic()+3
        while not captured.exists() and time.monotonic()<deadline: time.sleep(.01)
        args=json.loads(captured.read_text())
        self.assertEqual(sum(arg.startswith('Read the handoff') for arg in args),1)
        self.assertIn(str(Path(result['handoff']).parent),args)
        self.assertEqual(Path(result['handoff']).with_name('history.jsonl').read_bytes(),raw)
        record,_,token=self.starts[0]
        children[0].terminate(); children[0].join(timeout=3)
        self.assertFalse(children[0].is_alive())
        destination=Path(self.store.get('b')['directory'])/'projects/-project'/(record['conversation']+'.jsonl')
        destination.parent.mkdir(parents=True); destination.write_text('{"type":"user","message":{"content":"Continued work"}}\n')
        captured.unlink()
        start(record,token,['--resume',record['conversation']])
        deadline=time.monotonic()+3
        while not captured.exists() and time.monotonic()<deadline: time.sleep(.01)
        resumed=json.loads(captured.read_text())
        self.assertIn('--resume',resumed)
        self.assertFalse(any(arg.startswith('Read the handoff') for arg in resumed))
        self.assertIn('Continued work',destination.read_text())
        self.assertEqual(self.history.read_bytes(),raw)
