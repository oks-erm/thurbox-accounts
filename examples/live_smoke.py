"""Real Thurbox/tmux control-plane smoke with synthetic Claude; no real login or LLM calls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thurbox-cli', default='thurbox-cli')
    args = parser.parse_args()
    binary = shutil.which(args.thurbox_cli)
    if not binary:
        parser.error('Thurbox CLI not found')
    root = Path(tempfile.mkdtemp(prefix='tbx-account-smoke-', dir='/tmp')).resolve()
    config = root / 'config'
    config.mkdir()
    os.environ['THURBOX_CONFIG_DIR'] = str(config)
    os.environ['THURBOX_DATA_DIR'] = str(root / 'data')
    os.environ['THURBOX_SOCKET'] = 'tbx-accounts-' + uuid.uuid4().hex[:12]
    (config / 'settings.toml').write_text('[features]\nauto_update=false\nversion_check=false\nautomations=false\nnotifications=false\n')
    synthetic = root / 'synthetic-claude'
    synthetic.write_text('#!' + sys.executable + '\n' + '''import json, os, sys, time, uuid
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
with path.open('a') as stream:
    stream.write(json.dumps(dict(type='user',sessionId=identifier,message=dict(role='user',content='NATIVE-FORK-OK'))) + '\\n')
print('NATIVE-FORK-OK', flush=True)
if '-p' not in args: time.sleep(600)
''')
    synthetic.chmod(0o700)
    (config / 'agents.toml').write_text('config_version=1\ndefault="claude"\n[[agents]]\nname="claude"\ncommand=' +
        json.dumps(str(synthetic)) + '\nnew_session_args=["--session-id","{id}"]\nresume_args=["--resume","{id}"]\nhook_schema="claude"\n')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from thurbox_accounts.accounts import Accounts, Claude, Profiles
    from thurbox_accounts.thurbox import Thurbox
    from thurbox_accounts.core import atomic_write, dumps
    tb = Thurbox([binary])
    store = Profiles(root / 'accounts')
    service = Accounts(store, Claude(str(synthetic)), tb)
    store.add('enterprise-a')
    store.add('enterprise-b')
    sessions = []
    try:
        service.verify_handoff('enterprise-b')
        source = service.start('enterprise-a', root, 'synthetic-source')
        sessions.append(source['id'])
        for _ in range(50):
            row = tb.call('session', 'get', source['id'])
            if row.get('transcript_path'):
                break
            time.sleep(0.1)
        tb.call('session', 'stop', source['id'])
        row = tb.call('session', 'get', source['id'])
        transcript = Path(row['transcript_path'])
        original = transcript.read_bytes()
        plan = service.preview(source['id'], 'enterprise-b')
        result = service.confirm(plan['id'])
        sessions.append(result['destination'])
        tb.call('session', 'restart', result['destination'])
        launch = tb.call('agent', 'launch-args', 'claude', '--session', result['destination'])
        target = tb.call('session', 'get', result['destination'])
        assert launch['env']['CLAUDE_CONFIG_DIR'] == store.get('enterprise-b')['directory']
        assert target['agent_session_id'] == result['conversation']
        assert target.get('agent_args') == []
        assert transcript.read_bytes() == original
        assert tb.call('session', 'get', source['id'])['stopped']
        summary = dict(real_thurbox=True, synthetic_claude=True, native_enterprise_auth_verified=False,
            fork_restart_uuid=True, isolated_profile_env=True, original_unchanged=True, artifacts=str(root))
        atomic_write(root / 'summary.json', dumps(summary))
        print(dumps(summary))
    finally:
        for session in sessions:
            tb.call('session', 'stop', session)
        tb.call('runtime', 'stop')


if __name__ == '__main__':
    main()
