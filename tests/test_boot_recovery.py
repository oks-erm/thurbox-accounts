import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from thurbox_accounts.accounts import Profiles
from thurbox_accounts import guard


class BootRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Profiles(Path(self.temp.name) / 'state')
        self.conversation = '33333333-3333-4333-8333-333333333333'
        self.key = 'runtime-' + self.conversation + '.json'
        self.boot = dict(id='22222222-2222-4222-8222-222222222222',started_ns=time.time_ns()-1_000_000_000)
        self.previous_id='11111111-1111-4111-8111-111111111111'
        self.state = dict(owner='owner',phase='running',native_pid=12345,tools=['unconfirmed-tool'],
                          background_tools={'old':'task'},subagents=['agent'],scheduled_work=[{'id':'cron'}],
                          blocked=True,uncertain=True,error='old hook error')

    def reconcile(self, **kwargs):
        with patch.object(guard,'boot_identity',return_value=self.boot):
            return guard.reconcile_boot(self.store,self.conversation,'owner',**kwargs)

    def test_previous_boot_is_archived_and_no_longer_blocks_resume(self):
        previous = dict(self.state,boot=dict(id=self.previous_id))
        self.store.write(self.key,previous)
        history = self.store.root / 'main.jsonl'
        history.write_bytes(b'conversation history stays here\n')
        result = self.reconcile()
        self.assertEqual(result['phase'],'stopped')
        self.assertIsNone(result['native_pid'])
        for key in ('tools','background_tools','subagents','scheduled_work','blocked','uncertain','error'):
            self.assertFalse(result[key],key)
        self.assertEqual(result['last_shutdown']['reason'],'system-reboot')
        backup = self.store.root / result['last_shutdown']['backup']
        self.assertEqual(json.loads(backup.read_text()),previous)
        self.assertEqual(history.read_bytes(),b'conversation history stays here\n')
        self.assertEqual(self.reconcile(),result)
        self.assertEqual(len(list(self.store.root.glob('runtime-before-boot-*'))),1)

    def test_legacy_old_file_dates_require_explicit_reboot_confirmation(self):
        self.store.write(self.key,self.state)
        self.boot['started_ns'] = time.time_ns()+1_000_000_000
        self.assertEqual(self.reconcile(),self.state)
        with patch.object(guard.os,'kill',side_effect=ProcessLookupError):
            self.assertEqual(self.reconcile(confirm_legacy=True)['stop_result'],'rebooted')

    def test_same_boot_or_post_boot_legacy_record_keeps_orphan_evidence(self):
        for state in (self.state,dict(self.state,boot=self.boot)):
            self.store.write(self.key,state)
            self.assertEqual(self.reconcile(),state)
        self.assertFalse(list(self.store.root.glob('runtime-before-boot-*')))

    def test_unknown_boot_never_clears_a_saved_pid(self):
        self.store.write(self.key,self.state)
        with patch.object(guard,'boot_identity',return_value=None):
            self.assertEqual(guard.reconcile_boot(self.store,self.conversation,'owner'),self.state)

    def test_current_writer_or_different_owner_prevents_repair(self):
        previous = dict(self.state,boot=dict(id=self.previous_id))
        self.store.write(self.key,previous)
        with guard.writer(self.store,self.conversation):
            with self.assertRaisesRegex(ValueError,'progress'):
                self.reconcile()
        self.assertEqual(self.store.read(self.key),previous)
        self.store.write(self.key,dict(previous,owner='different-owner'))
        self.assertEqual(self.reconcile(),dict(previous,owner='different-owner'))

    def test_malformed_boot_id_never_proves_a_reboot(self):
        for value in ('unknown','',None,0):
            self.store.write(self.key,dict(self.state,boot=dict(id=value)))
            self.boot['started_ns'] = time.time_ns()+1_000_000_000
            before=self.store.read(self.key)
            self.assertEqual(self.reconcile(),before)
            self.assertEqual(self.reconcile(confirm_legacy=True),before)

    def test_manual_legacy_repair_refuses_a_present_pid(self):
        self.store.write(self.key,self.state)
        self.boot['started_ns'] = time.time_ns()+1_000_000_000
        with patch.object(guard.os,'kill',return_value=None), self.assertRaisesRegex(ValueError,'PID still exists'):
            self.reconcile(confirm_legacy=True)
        self.assertEqual(self.store.read(self.key),self.state)

    def test_confirmation_cannot_override_a_valid_same_boot_id(self):
        self.store.write(self.key,dict(self.state,boot=self.boot))
        self.boot['started_ns'] = time.time_ns()+1_000_000_000
        before=self.store.read(self.key)
        self.assertEqual(self.reconcile(confirm_legacy=True),before)
