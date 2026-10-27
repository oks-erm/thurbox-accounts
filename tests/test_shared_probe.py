"""Exercise the full guarded proof protocol without credentials or model calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from thurbox_accounts.accounts import Accounts, Claude, Profiles
from thurbox_accounts.shared_probe import verify
from thurbox_accounts.thurbox import Thurbox

SYNTHETIC = '''import json, os, re, subprocess, sys
from pathlib import Path
args=sys.argv[1:]
profile=Path(os.environ['CLAUDE_CONFIG_DIR'])
if args[:2]==['auth','status']:
    print(json.dumps(dict(loggedIn=True,authMethod='claude.ai',configDirectory=str(profile),email=profile.name+'@example.invalid',orgId=profile.name)))
    raise SystemExit(0)
def option(name): return args[args.index(name)+1]
identifier=option('--session-id') if '--session-id' in args else option('--resume')
path=profile/'projects'/'-synthetic'/(identifier+'.jsonl')
path.parent.mkdir(parents=True,exist_ok=True)
previous=path.read_text() if path.exists() else ''
marker=re.search('SHARED-PROOF-[a-f0-9]+',previous+' '.join(args)).group()
settings={}
if '--settings' in args: settings=json.loads(Path(option('--settings')).read_text())
def event(name,**fields):
    for group in settings.get('hooks',{}).get(name,[]):
        for hook in group['hooks']:
            subprocess.run(hook['command'],shell=True,input=json.dumps(dict(session_id=identifier,hook_event_name=name,**fields)),text=True,check=True)
event('UserPromptSubmit')
if '--agents' in args:
    event('PreToolUse',tool_use_id='tool')
    event('SubagentStart',agent_id='agent')
    child=path.with_suffix('')/'subagents'/'agent.jsonl'
    child.parent.mkdir(parents=True,exist_ok=True)
    child.write_text(json.dumps(dict(type='assistant',message=marker))+'\\n')
    event('SubagentStop',agent_id='agent')
    event('PostToolUse',tool_use_id='tool')
with path.open('a') as stream:
    stream.write(json.dumps(dict(type='user',uuid='user',sessionId=identifier,message=dict(role='user',content=marker)))+'\\n')
    if any(value.startswith('/compact') for value in args):
        stream.write(json.dumps(dict(type='system',subtype='compact_boundary'))+'\\n')
event('Stop')
print(marker)
'''


class SharedProbeTests(unittest.TestCase):
    def test_complete_probe_uses_guard_and_recovers_after_refused_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            native = root/'synthetic-claude'
            native.write_text('#!' + sys.executable + '\n' + SYNTHETIC)
            native.chmod(0o700)
            store = Profiles(root/'accounts')
            store.add('a')
            store.add('b')
            accounts = Accounts(store,Claude(str(native)),Thurbox())
            # A clean process environment also proves no user login is consulted.
            env = {key:value for key,value in os.environ.items() if key in {'PATH','HOME','TMPDIR','LANG'}}
            with patch.dict(os.environ,env,clear=True):
                result = verify(accounts,['a','b'])
            self.assertTrue(result['verified'])
            proof = store.read('shared-proof.json')
            self.assertEqual(proof['fingerprint'],accounts.claude.fingerprint())
            record_path = next(path for path in store.root.glob('shared-*.json') if path.name != 'shared-proof.json')
            record = json.loads(record_path.read_text())
            runtime = store.read('runtime-' + record['conversation'] + '.json')
            self.assertEqual(runtime['phase'],'stopped')
            self.assertIsNone(runtime['native_pid'])
            self.assertGreaterEqual(runtime['events']['Stop'],5)
            self.assertEqual(runtime['events']['SubagentStart'],1)
            self.assertEqual(runtime['events']['SubagentStop'],1)
            self.assertTrue(record['is_probe'])
            self.assertEqual(record['phase'],'probe-complete')
