"""Real Thurbox/tmux A→B→A sharing smoke; synthetic Claude, no login/model calls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simple',action='store_true',help='Named account creation and inline idle switching')
    parser.add_argument('--mode',action='store_true',help='Adopt an ordinary source and exercise conversation mode Off/On')
    parser.add_argument('--desktop',action='store_true',help='Also exercise desktop listing/capture/literal send')
    parser.add_argument('--thurbox-cli',default='thurbox-cli')
    args = parser.parse_args()
    binary = shutil.which(args.thurbox_cli)
    if not binary:
        parser.error('Thurbox CLI not found')
    root = Path(tempfile.mkdtemp(prefix='tbx-shared-smoke-',dir='/tmp')).resolve()
    config = root/'config'
    config.mkdir()
    os.environ.update(THURBOX_CONFIG_DIR=str(config),THURBOX_DATA_DIR=str(root/'data'),
                     THURBOX_SOCKET='tbx-shared-' + uuid.uuid4().hex[:12])
    (config/'settings.toml').write_text('[features]\nauto_update=false\nversion_check=false\nautomations=false\nnotifications=false\n')
    native = root/'synthetic-claude'
    native.write_text('#!' + sys.executable + '\n' + '''import json, os, subprocess, sys, time
from pathlib import Path
args=sys.argv[1:]
profile=Path(os.environ['CLAUDE_CONFIG_DIR'])
if args[:2]==['auth','status']:
    identity='enterprise-a' if profile.name=='untracked-native' else profile.name
    print(json.dumps(dict(loggedIn=True,authMethod='claude.ai',configDirectory=str(profile),email=identity+'@example.invalid',orgId=identity)))
    raise SystemExit(0)
def option(name): return args[args.index(name)+1]
identifier=option('--session-id') if '--session-id' in args else option('--resume')
path=profile/'projects'/'-synthetic'/(identifier+'.jsonl')
path.parent.mkdir(parents=True,exist_ok=True)
with path.open('a') as stream:
    stream.write(json.dumps(dict(type='user',sessionId=identifier,message=dict(role='user',content='SYNTHETIC-'+profile.name)))+'\\n')
if '--settings' in args and os.environ.get('THURBOX_ACCOUNTS_CONVERSATION'):
    value=option('--settings')
    settings=json.loads(value) if value.startswith('{') else json.loads(Path(value).read_text())
    for event in ('UserPromptSubmit','StopFailure'):
        payload=dict(session_id=identifier,hook_event_name=event,error='rate_limit')
        for group in settings['hooks'][event]:
            for hook in group['hooks']:
                # Only fixture-owned guard callbacks; no user hooks.
                if '--event' in hook.get('command',''):
                    subprocess.run(hook['command'],shell=True,input=json.dumps(payload),text=True,check=True)
print('SYNTHETIC READY',flush=True)
while True:
    line=sys.stdin.readline()
    if not line:
        time.sleep(0.1)
        continue
    with path.open('a') as stream:
        stream.write(json.dumps(dict(type='user',sessionId=identifier,message=dict(role='user',content=line)))+'\\n')
    print('SYNTHETIC INPUT RECEIVED',flush=True)
''')
    native.chmod(0o700)
    (config/'agents.toml').write_text('config_version=1\ndefault="claude"\n[[agents]]\nname="claude"\ncommand=' + json.dumps(str(native)) + '\nnew_session_args=["--session-id","{id}"]\nresume_args=["--resume","{id}"]\nhook_schema="claude"\n')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from thurbox_accounts.accounts import Accounts, Claude, Profiles
    from thurbox_accounts.core import atomic_write, dumps
    from thurbox_accounts.guard import writer_available
    from thurbox_accounts.install import install_checkout
    from thurbox_accounts.shared import Shared
    from thurbox_accounts.thurbox import Thurbox
    tb = Thurbox([binary])
    store = Profiles(root/'accounts')
    service = Accounts(store,Claude(str(native)),tb)
    shared = Shared(service)
    sessions = []
    def wait(predicate):
        for _ in range(100):
            if predicate():
                return
            time.sleep(0.1)
        raise AssertionError('Fixture did not become ready: ' + str(root))
    try:
        install_checkout(binary,store.root,str(native),root/'bin')
        store.add('enterprise-a')
        store.add('enterprise-b')
        # Synthetic fixture proof is bound to this synthetic executable only.
        store.write('shared-proof.json',shared.proof_contract(['enterprise-a','enterprise-b']))
        if args.simple:
            from thurbox_accounts.agent_install import register_profiles
            from thurbox_accounts.simple import Simple, agent_name
            for name in ('enterprise-a','enterprise-b'): service.status(name)
            register_profiles(service,Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent')
            source=tb.call('session','create','--name','synthetic-named','--repo-path',str(root),
                '--agent',agent_name(store.get('enterprise-a')),'--on-existing','fail')
        elif args.mode:
            origin=root/'untracked-native'; origin.mkdir(mode=0o700)
            source=tb.call('session','create','--name','synthetic-existing','--repo-path',str(root),
                '--agent','claude','--env','CLAUDE_CONFIG_DIR='+str(origin),'--on-existing','fail')
        else:
            source = service.start('enterprise-a',root,'synthetic-source')
        sessions.append(source['id'])
        if args.simple:
            wait(lambda: store.read(shared.key(source['agent_session_id'])))
            wait(lambda: Simple(service).transcript(shared.load(source['agent_session_id'])))
        else: wait(lambda: tb.call('session','get',source['id']).get('transcript_path'))
        if not args.simple: tb.call('session','stop',source['id'])
        if args.simple:
            conversation=source['agent_session_id']
            wait(lambda: shared._runtime(conversation).get('turn')=='quota')
            before=shared._runtime(conversation)['native_pid']
            # An explicit idle checkpoint, through the actual native hook bridge.
            native_env=dict(os.environ,THURBOX_ACCOUNTS_ROOT=str(store.root),THURBOX_ACCOUNTS_CONVERSATION=conversation,
                THURBOX_SESSION=source['id'],THURBOX_ACCOUNTS_CLAUDE=str(native),THURBOX_ACCOUNTS_PROFILE='enterprise-a',THURBOX_ACCOUNTS_CLI=binary)
            def simple_event(event,**payload):
                result=subprocess.run([str(Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent'),'--event',event],
                    env=native_env,input=json.dumps(dict(session_id=conversation,hook_event_name=event,**payload)),capture_output=True,text=True,timeout=15)
                assert result.returncode==0,result.stderr
            simple_event('Stop',background_tasks=[])
            simple_event('PreToolUse',tool_use_id='busy-shell',tool_name='Bash',tool_input={'run_in_background':True})
            simple_event('PostToolUse',tool_use_id='busy-shell',tool_name='Bash',tool_response={'backgroundTaskId':'busy-task'})
            simple_event('Stop')
            plan=Simple(service).preview(source['id'],'enterprise-b')
            try: Simple(service).confirm(plan['id'],consent=True)
            except ValueError as error: assert 'Background' in str(error),str(error)
            else: raise AssertionError('Named busy source was switched')
            assert shared._runtime(conversation)['native_pid']==before; os.kill(before,0)
            simple_event('Stop',background_tasks=[])
            plan=Simple(service).preview(source['id'],'enterprise-b')
            current=Simple(service).confirm(plan['id'],consent=True)
            assert current['profile']=='enterprise-b'
        elif args.mode:
            from thurbox_accounts.mode import Mode
            from thurbox_accounts.pane import snapshot
            mode=Mode(service)
            row=tb.call('session','get',source['id']); original=Path(row['transcript_path'])
            original_bytes=original.read_bytes()
            assert 'synthetic-existing' in snapshot(service,source['id'])
            plan=mode.preview(source['id'],['enterprise-a','enterprise-b'])
            current=mode.enable(plan['id'],consent=True)
            assert original.read_bytes()==original_bytes and not original.is_symlink()
            mode.set_enabled(current['session'],False)
            try: shared.switch(current['conversation'])
            except ValueError as error: assert 'Off' in str(error)
            else: raise AssertionError('Disabled mode allowed a switch')
            mode.set_enabled(current['session'],True)
            wait(lambda: shared._runtime(current['conversation']).get('turn')=='quota')
            launch=tb.call('agent','launch-args','claude-accounts','--session',current['session'])
            native_env=dict(os.environ); native_env.update(launch['env'])
            def event(name, **payload):
                payload.update(session_id=current['conversation'],hook_event_name=name)
                result=subprocess.run([str(Path(__file__).resolve().parents[1]/'bin/thurbox-accounts-agent'),'--event',name],
                    env=native_env,input=json.dumps(payload),capture_output=True,text=True,timeout=15)
                assert result.returncode==0, result.stderr
            before=shared._runtime(current['conversation'])['native_pid']
            event('PreToolUse',tool_use_id='synthetic-bg',tool_name='Bash',tool_input={'run_in_background':True})
            event('PostToolUse',tool_use_id='synthetic-bg',tool_name='Bash',tool_response={'backgroundTaskId':'synthetic-task'})
            event('StopFailure',error='rate_limit')
            try: shared.switch(current['conversation'])
            except ValueError as error: assert 'Background' in str(error)
            else: raise AssertionError('Unconfirmed background work allowed a switch')
            assert shared._runtime(current['conversation'])['native_pid']==before
            os.kill(before,0)
            assert not tb.call('session','get',current['session']).get('stopped')
            event('Stop',background_tasks=[])
            event('StopFailure',error='rate_limit')
        else:
            current = shared.enroll(source['id'],['enterprise-a','enterprise-b'],consent=True)
        conversation = current['conversation']
        sessions.append(current['session'])
        for target in (('enterprise-a',) if args.simple else ('enterprise-b','enterprise-a')):
            wait(lambda: shared._runtime(conversation).get('turn') == 'quota')
            assert not writer_available(store,conversation)
            if args.simple:
                plan=Simple(service).preview(current['session'],target)
                current=Simple(service).confirm(plan['id'],consent=True)
            else: current = shared.switch(conversation)
            sessions.append(current['session'])
            assert current['profile'] == target
            row = tb.call('session','get',current['session'])
            assert row['agent_session_id'] == conversation
            launch = tb.call('agent','launch-args','claude-accounts','--session',current['session'])
            assert launch['env']['CLAUDE_CONFIG_DIR'] == store.get(target)['directory']
        wait(lambda: shared._runtime(conversation).get('turn') == 'quota')
        record = shared.load(conversation)
        shared.validate(record)
        if args.mode: assert original.read_bytes()==original_bytes and not original.is_symlink()
        text = Path(record['transcript']).read_text()
        assert 'SYNTHETIC-enterprise-a' in text and 'SYNTHETIC-enterprise-b' in text
        if args.desktop:
            from thurbox_accounts.desktop import Desktop
            desktop = Desktop(service)
            snapshot = desktop.state()
            assert [row['id'] for row in snapshot['conversations']] == [current['session']]
            assert 'SYNTHETIC READY' in desktop.capture(current['session'])['output']
            desktop.stop(current['session'])
            desktop.start(current['session'])
            wait(lambda: shared._runtime(conversation).get('turn') == 'quota')
            desktop.send(current['session'],'--DESKTOP-LITERAL-PROOF')
            wait(lambda: '--DESKTOP-LITERAL-PROOF' in Path(record['transcript']).read_text())
            text = Path(record['transcript']).read_text()
            try:
                desktop.start(source['id'])
            except ValueError:
                pass
            else:
                raise AssertionError('Desktop restarted unguarded enrolled original')
        # A stale managed row cannot retake the writer or clobber its runtime.
        old = sessions[1]
        tb.call('session','start',old)
        time.sleep(1)
        assert shared._runtime(conversation)['owner'] == current['session']
        assert Path(record['transcript']).read_text() == text
        summary = dict(real_thurbox=True,synthetic_claude=True,native_enterprise_auth_verified=False,
            same_conversation_uuid=True,canonical_history=True,separate_profile_env=True,
            sequential_a_b_a=True,stale_writer_rejected=True,desktop_adapter_verified=args.desktop,
            ordinary_adoption_verified=args.mode,mode_off_on_verified=args.mode,
            background_switch_refusal_verified=args.mode or args.simple,named_creation_verified=args.simple,inline_idle_switch_verified=args.simple,artifacts=str(root))
        atomic_write(root/'summary.json',dumps(summary))
        print(dumps(summary))
    finally:
        for session in sessions:
            tb.call('session','stop',session)
        tb.call('runtime','stop')


if __name__ == '__main__':
    main()
