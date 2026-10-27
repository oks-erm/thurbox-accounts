import unittest
from thurbox_accounts.guard import apply_event, safe_state, guarded_settings
from pathlib import Path

class GuardTests(unittest.TestCase):
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
