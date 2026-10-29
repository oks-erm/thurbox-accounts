import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote
from unittest.mock import patch

from test_accounts import FakeClaude, FakeThurbox
from thurbox_accounts.accounts import Accounts, Profiles

class PaneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Profiles(Path(self.temp.name).resolve()/'accounts')
        self.service = Accounts(self.store,FakeClaude(),FakeThurbox())

    def test_friendly_names_derive_ids_and_do_not_overwrite(self):
        from thurbox_accounts.pane import add
        first = add(self.store,'Work Enterprise')
        self.assertEqual(first['name'],'work-enterprise')
        self.assertEqual(first['label'],'Work Enterprise')
        with self.assertRaisesRegex(ValueError,'already'):
            add(self.store,'work enterprise')
        second = add(self.store,'Work—Enterprise')
        self.assertNotEqual(second['name'],first['name'])
        with self.assertRaises(ValueError): add(self.store,'\n\t')

    def test_read_model_encodes_tabs_newlines_and_unicode_without_auth_calls(self):
        from thurbox_accounts.pane import snapshot
        self.store.add('work','Work 東京')
        values = self.store.read('profiles.json')
        values['work']['label'] = 'Work\t東京\nA'
        self.store.write('profiles.json',values)
        with patch.object(self.service.thurbox,'call',return_value={'sessions':[]}), patch.object(self.service.claude,'status',side_effect=AssertionError('must not authenticate on refresh')):
            output = snapshot(self.service)
        fields = output.splitlines()[0].split('\t')
        self.assertEqual(fields[0],'account')
        self.assertEqual(unquote(fields[2]),'Work\t東京\nA')
        self.assertEqual(len(fields),5)

    def test_friendly_receipts_distinguish_signed_out_and_uncertain_delivery(self):
        from thurbox_accounts.pane import receipt
        self.assertIn('Log in',receipt('status',dict(loggedIn=False)))
        self.assertNotIn('{',receipt('pane-add',dict(name='work',label='Work')))
        self.assertIn('check',receipt('desktop-send',dict(notice='check before retrying',submitted=None)))

    def test_ui_operation_wrapper_reuses_backend_and_suppresses_json(self):
        from thurbox_accounts.cli import main
        import contextlib, io
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['--accounts-dir',str(self.store.root),'pane-run','pane-add','Work A']),0)
        self.assertIn('Log in',output.getvalue())
        self.assertEqual(self.store.get('work-a')['label'],'Work A')
        self.assertNotIn('"directory"',output.getvalue())

    def test_current_untracked_session_is_visible_without_auth_or_binding(self):
        from thurbox_accounts.pane import snapshot
        row=dict(id='existing',name='Existing project',agent='claude',host=None,backend_type='tmux',
                 cwd='/project',stopped=False,agent_session_id='88888888-8888-4888-8888-888888888888')
        def call(*args):
            return {'sessions':[row]} if args[:2]==('session','list') else row
        with patch.object(self.service.thurbox,'call',side_effect=call), patch.object(self.service.claude,'status',side_effect=AssertionError('refresh must not authenticate')):
            output=snapshot(self.service,session='existing')
        rows=[[unquote(v) for v in line.split('\t')] for line in output.splitlines()]
        current=[r for r in rows if r[0]=='current'][0]
        conversation=[r for r in rows if r[0]=='conversation'][0]
        self.assertEqual(current[1],'existing')
        self.assertEqual(conversation[2],'Existing project')
        self.assertEqual(conversation[-2:],['off','external'])

    def test_mode_cli_parser_and_frozen_receipt(self):
        from thurbox_accounts.cli import parser
        from thurbox_accounts.pane import receipt
        self.assertEqual(parser().parse_args(['mode-off','--session','existing']).session,'existing')
        output=receipt('mode-preview',dict(id='token',session='s',conversation='uuid',name='Existing',
            expires_at=123,proof_ready=False,profiles=['a','b'],source_profile='a',
            contract={'profiles':[dict(name='a',identity=dict(email='a@example.invalid',orgId='org-a'))]},
            accounts=[dict(name='a',label='Work A',email='a@example.invalid',orgId='org-a')]))
        self.assertIn('mode-plan\t',output)
        self.assertIn('mode-account\t',output)
        self.assertNotIn('{',output)

    def test_unsupported_current_agent_is_explained_without_claiming_switchable(self):
        from thurbox_accounts.pane import snapshot
        row=dict(id='codex',name='Other provider',agent='codex',host=None,backend_type='tmux',cwd='/project')
        def call(*args): return {'sessions':[]} if args[:2]==('session','list') else row
        with patch.object(self.service.thurbox,'call',side_effect=call): output=snapshot(self.service,session='codex')
        self.assertIn('unsupported\tcodex',output)
        self.assertNotIn('conversation\tcodex',output)
