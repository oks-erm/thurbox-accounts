"""Opt-in native shared-history proof using synthetic data and scoped tools only."""
import json
import os
from pathlib import Path
import time
import uuid

from .accounts import account_env, private_dir
from .guard import writer, update
from .runtime import execute
from .shared import Shared, real_directory
from .thurbox import strict_json


def verify(accounts, names):
    shared = Shared(accounts)
    contract = shared.proof_contract(names)
    profiles = [accounts.profiles.get(name) for name in names]
    store = accounts.profiles
    conversation, owner = str(uuid.uuid4()), str(uuid.uuid4())
    folder = store.root / 'probes' / conversation
    private_dir(folder)
    launcher = Path(__file__).resolve().parents[1] / 'bin/thurbox-accounts-agent'
    if not launcher.is_file():
        raise ValueError('Native shared proof requires the source or installed guarded launcher')
    marker = 'SHARED-PROOF-' + uuid.uuid4().hex
    base = [accounts.claude.executable,'-p','--strict-mcp-config','--max-budget-usd','0.25']
    stage = 'initial synthetic conversation'
    record = None
    def run(profile, extra, prompt, *, settings=None):
        env = account_env(profile)
        env.update(THURBOX_ACCOUNTS_ROOT=str(store.root),THURBOX_ACCOUNTS_CONVERSATION=conversation,
            THURBOX_ACCOUNTS_PROFILE=profile['name'],THURBOX_ACCOUNTS_CLAUDE=accounts.claude.executable,
            THURBOX_ACCOUNTS_RESERVATION='probe',THURBOX_SESSION=owner)
        argv = [*base,*extra]
        if record:
            record['index'] = names.index(profile['name'])
            shared.save(record)
            argv = [str(launcher),*base[1:],*extra]
        result = execute([*argv,prompt],folder,env=env,timeout=120,limit=65536)
        if result['status'] != 'PASS' or result['truncated']:
            raise ValueError(f'Native shared proof failed at {stage}; account data unchanged. Synthetic evidence: {folder}')
        if record:
            shared.validate(record)
        return result['stdout']
    try:
        output = run(profiles[0],['--session-id',conversation,'--tools',''],
                     'Synthetic compatibility check. Remember ' + marker + '. Reply exactly with that marker.')
        paths = list((Path(profiles[0]['directory'])/'projects').glob('*/' + conversation + '.jsonl'))
        if len(paths) != 1 or marker not in output:
            raise ValueError('Initial native transcript/marker could not be verified')
        source = paths[0]
        canonical = store.root/'shared'/conversation
        private_dir(canonical)
        transcript, sidecars = canonical/'main.jsonl',canonical/'session'
        aliases = []
        for profile in profiles:
            directory = Path(profile['directory'])/'projects'/source.parent.name
            real_directory(directory)
            aliases.append(dict(profile=profile['name'],transcript=str(directory/(conversation+'.jsonl')),
                                sidecars=str(directory/conversation)))
        os.rename(source,transcript)
        if source.with_suffix('').exists():
            os.rename(source.with_suffix(''),sidecars)
        else:
            sidecars.mkdir(mode=0o700)
        for alias in aliases:
            Path(alias['transcript']).symlink_to(transcript)
            Path(alias['sidecars']).symlink_to(sidecars,target_is_directory=True)
        record = dict(conversation=conversation,project=source.parent.name,cwd=str(folder),
            transcript=str(transcript),sidecars=str(sidecars),aliases=aliases,profiles=names,proof=contract,
            index=0,phase='active',allowed_session=owner,reservation='probe',is_probe=True)
        shared.save(record)
        update(store,conversation,owner=owner,phase='stopped',turn='unknown',tools=[],subagents=[],blocked=False)
        settings = True  # Post-enrollment probes use the actual guarded launcher.
        stage = 'managed writer contention'
        with writer(store,conversation):
            try:
                run(profiles[0],['--resume',conversation,'--tools',''],'Must not reach the model')
            except ValueError:
                pass
            else:
                raise ValueError('A competing guarded writer was not refused')
        stage = 'failed managed launch and same-owner recovery'
        try:
            run(profiles[0],['--resume',str(uuid.uuid4()),'--tools',''],'Must not reach the model')
        except ValueError:
            pass
        else:
            raise ValueError('Invalid managed launch was not refused')
        for profile in [*profiles[1:],profiles[0]]:
            stage = 'same-UUID resume under ' + profile['name']
            size = transcript.stat().st_size
            output = run(profile,['--resume',conversation,'--tools',''],
                         'Reply exactly with the synthetic marker from the prior conversation.',settings=settings)
            state = store.read('runtime-' + conversation + '.json')
            if marker not in output or transcript.stat().st_size <= size or state.get('turn') != 'idle':
                raise ValueError('Native resume/append/Stop hook proof was incomplete')
        # Require an actual native subagent transcript and lifecycle callbacks.
        stage = 'native subagent sidecars'
        agents = json.dumps({'shared-probe':dict(description='Synthetic sharing probe',
            prompt='Return the exact marker supplied by the parent. Do not use tools.',tools=[])})
        run(profiles[0],['--resume',conversation,'--tools','Agent','--allowedTools','Agent','--agents',agents],
            'Use the shared-probe subagent exactly once to repeat ' + marker + ', then repeat its answer.',settings=settings)
        state = store.read('runtime-' + conversation + '.json')
        if not state.get('events',{}).get('SubagentStart') or not state.get('events',{}).get('SubagentStop'):
            raise ValueError('Native subagent lifecycle hooks were not observed')
        if not list(sidecars.glob('subagents/*.jsonl')):
            raise ValueError('Native subagent sidecar discovery was not proven; shared switching remains disabled')
        # Enough harmless fixture context for native compaction; synthetic only.
        records = [strict_json(line) for line in transcript.read_text().splitlines() if line.strip()]
        user = next(value for value in reversed(records) if value.get('type') == 'user')
        extra = dict(user,uuid=str(uuid.uuid4()),parentUuid=records[-1].get('uuid'),sessionId=conversation)
        extra['message'] = dict(role='user',content=('Synthetic compaction fixture. ' * 2500) + marker)
        with transcript.open('a') as stream:
            stream.write(json.dumps(extra)+'\n')
        stage = 'native compaction without alias replacement'
        run(profiles[1],['--resume',conversation,'--tools',''],
            '/compact Preserve the synthetic marker and summarize the repeated fixture.',settings=settings)
        values = [strict_json(line) for line in transcript.read_text().splitlines() if line.strip()]
        if not any(value.get('subtype') == 'compact_boundary' for value in values):
            raise ValueError('Native compact_boundary was not observed; shared switching remains disabled')
        stage = 'resume after compaction under original account'
        output = run(profiles[0],['--resume',conversation,'--tools',''],
                     'Reply exactly with the synthetic marker.',settings=settings)
        state = store.read('runtime-' + conversation + '.json')
        if marker not in output or state.get('tools') or state.get('subagents') or state.get('blocked'):
            raise ValueError('Native post-compaction/worker lifecycle proof failed')
        if shared.proof_contract(names) != contract:
            raise ValueError('Account identity or native build changed during verification')
        shared.remember_proof(contract)
        return dict(verified=True,profiles=names,same_uuid=True,append=True,sidecars=True,
                    compaction=True,original_account_resume=True,evidence=str(folder))
    finally:
        if record:
            record['phase'] = 'probe-complete'
            shared.save(record)
