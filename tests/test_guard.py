import unittest
from thurbox_accounts.guard import apply_event, safe_state, guarded_settings
from pathlib import Path

class GuardTests(unittest.TestCase):
    def test_stale_foreground_marker_clears_only_after_full_snapshot_and_later_idle(self):
        state={}
        apply_event(state,'PreToolUse',{'tool_use_id':'orphan'})
        apply_event(state,'StopFailure',{'error':'rate_limit'})
        apply_event(state,'Notification',{'notification_type':'idle_prompt'})
        self.assertEqual(state['tools'],['orphan'])
        apply_event(state,'Stop',{'background_tasks':[],'session_crons':[]})
        self.assertEqual(state['tools'],['orphan'])
        apply_event(state,'Notification',{'notification_type':'idle_prompt'})
        self.assertEqual(state['tools'],[])
        self.assertTrue(safe_state(state,allow_idle=True))

    def test_idle_never_discharges_background_work_or_a_new_tool_after_snapshot(self):
        for change in [dict(tool_use_id='new'),dict(tool_use_id='bg',tool_name='Bash',tool_input={'run_in_background':True})]:
            state={}
            apply_event(state,'Stop',{'background_tasks':[],'session_crons':[]})
            apply_event(state,'PreToolUse',change)
            apply_event(state,'Notification',{'notification_type':'idle_prompt'})
            self.assertTrue(state['tools'])
            self.assertFalse(safe_state(state,allow_idle=True))
        state={}
        apply_event(state,'PreToolUse',{'tool_use_id':'orphan'})
        apply_event(state,'Stop',{'background_tasks':[{'id':'background-job'}],'session_crons':[]})
        apply_event(state,'Notification',{'notification_type':'idle_prompt'})
        self.assertEqual(state['tools'],['orphan'])
        self.assertFalse(safe_state(state,allow_idle=True))

    def test_null_quota_registry_cannot_reuse_an_older_idle_snapshot(self):
        state={}
        apply_event(state,'Stop',{'background_tasks':[],'session_crons':[]})
        apply_event(state,'PreToolUse',{'tool_use_id':'pending'})
        apply_event(state,'StopFailure',{'error':'rate_limit','background_tasks':[],'session_crons':None})
        apply_event(state,'Notification',{'notification_type':'idle_prompt'})
        self.assertEqual(state['tools'],['pending'])
        self.assertFalse(safe_state(state,allow_idle=True))

    def test_busy_permission_and_background_workers_prevent_switch(self):
        state = dict(turn='unknown')
        self.assertFalse(safe_state(state))
        apply_event(state,'UserPromptSubmit',{})
        apply_event(state,'PreToolUse',{'tool_use_id':'t'})
        apply_event(state,'PreToolUse',{'tool_use_id':'t'})
        apply_event(state,'PermissionRequest',{})
        apply_event(state,'Stop',{})
        self.assertFalse(safe_state(state))
        apply_event(state,'PostToolUse',{'tool_use_id':'t'})
        apply_event(state,'SubagentStart',{'agent_id':'a'})
        self.assertFalse(safe_state(state))
        apply_event(state,'SubagentStop',{'agent_id':'a'})
        self.assertFalse(safe_state(state))
        apply_event(state,'UserPromptSubmit',{})
        self.assertFalse(safe_state(state))
        apply_event(state,'StopFailure',{'error':'rate_limit'})
        self.assertTrue(safe_state(state))
        state['uncertain'] = True
        self.assertFalse(safe_state(state))

    def test_registry_settings_are_preserved_or_refused_never_weakened(self):
        args,settings = guarded_settings(['--resume','id','--settings','{"hooks":{"Stop":[{"hooks":[]}]}}'],Path('/absolute/guard'))
        self.assertEqual(args,['--resume','id'])
        self.assertEqual(len(settings['hooks']['Stop']),2)
        with self.assertRaisesRegex(ValueError,'policy overrides'):
            guarded_settings(['--settings','{"permissions":{"defaultMode":"plan"}}'],Path('/absolute/guard'))
